"""FastAPI-зависимости для JWT-аутентификации и авторизации по ролям/зонам."""

from collections.abc import Callable

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session as DBSession

from database import get_db

from .keycloak_service import keycloak_service
from .models import Role, Role2Function, SysFunction, User, User2Area, User2Role

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: DBSession = Depends(get_db),
) -> User:
    """Возвращает текущего пользователя по JWT-токену.

    Args:
        token: JWT-токен из заголовка Authorization.
        db: Сессия БД.

    Returns:
        Пользователь из БД.

    Raises:
        HTTPException: 401, если токен невалиден или пользователь неактивен.
    """
    try:
        payload = keycloak_service.decode_token(token)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Токен невалиден или истек",
        ) from None
    username = payload.get("preferred_username") or payload.get("sub")
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Токен невалиден или истек",
        )
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Пользователь не найден",
        )
    if not user.enabled:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Пользователь неактивен",
        )
    return user


def get_user_area_ids(user: User, db: DBSession) -> list[int]:
    """Возвращает идентификаторы производственных зон, назначенных пользователю.

    Args:
        user: Пользователь.
        db: Сессия БД.

    Returns:
        Список идентификаторов зон.
    """
    rows = (
        db.query(User2Area.production_area_id)
        .filter(User2Area.user_id == user.id)
        .all()
    )
    return [r[0] for r in rows]


def get_user_function_names(user: User, db: DBSession) -> set[str]:
    """Возвращает имена функций API, доступных пользователю через его роли.

    Args:
        user: Пользователь.
        db: Сессия БД.

    Returns:
        Множество имён функций вида 'entity.operation'.
    """
    rows = (
        db.query(SysFunction.api_name)
        .join(Role2Function, Role2Function.function_id == SysFunction.id)
        .join(Role, Role.id == Role2Function.role_id)
        .join(User2Role, User2Role.role_id == Role.id)
        .filter(User2Role.user_id == user.id)
        .all()
    )
    return {r[0] for r in rows}


def require_function(api_name: str) -> Callable[..., User]:
    """Возвращает FastAPI-зависимость, проверяющую наличие функции у пользователя.

    Args:
        api_name: Имя функции API вида 'entity.operation'.

    Returns:
        Зависимость, возвращающая текущего пользователя или 403.
    """

    def checker(
        current_user: User = Depends(get_current_user),
        db: DBSession = Depends(get_db),
    ) -> User:
        allowed = get_user_function_names(current_user, db)
        if api_name not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Нет прав на использование функции",
            )
        return current_user

    return checker


def require_area_access(production_area_id: int, user: User, db: DBSession) -> None:
    """Проверяет доступ пользователя к производственной зоне.

    Args:
        production_area_id: Идентификатор производственной зоны.
        user: Пользователь.
        db: Сессия БД.

    Raises:
        HTTPException: 403, если зона не назначена пользователю.
    """
    area_ids = get_user_area_ids(user, db)
    if production_area_id not in area_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Нет прав для работы с данными производственной зоны",
        )


def get_current_user_from_state(request: Request) -> User | None:
    """Извлекает пользователя, установленного AuthMiddleware в request.state.

    Args:
        request: HTTP-запрос.

    Returns:
        Пользователь или None, если middleware его не установил.
    """
    return getattr(request.state, "current_user", None)


def get_area_ids_from_state(
    request: Request,
    db: DBSession = Depends(get_db),
) -> list[int]:
    """Возвращает список area_ids текущего пользователя (из middleware).

    Args:
        request: HTTP-запрос.
        db: Сессия БД.

    Returns:
        Список идентификаторов зон (пустой, если пользователь не определён).
    """
    user = get_current_user_from_state(request)
    if not user:
        return []
    return get_user_area_ids(user, db)


def check_area_from_request(
    request: Request, db: DBSession, production_area_id: int | None
) -> None:
    """Проверяет доступ к зоне для пользователя из request.state.

    Args:
        request: HTTP-запрос.
        db: Сессия БД.
        production_area_id: Идентификатор зоны (проверка пропускается, если None).
    """
    if not production_area_id:
        return
    user = get_current_user_from_state(request)
    if user:
        require_area_access(production_area_id, user, db)


def resolve_area_id(
    db: DBSession, model: type, record_id: int, area_field: str = "production_area_id"
) -> int | None:
    """Загружает запись model по record_id и возвращает значение area_field.

    Args:
        db: Сессия БД.
        model: SQLAlchemy-модель записи.
        record_id: Идентификатор записи.
        area_field: Имя поля с идентификатором зоны.

    Returns:
        Идентификатор зоны или None, если запись не найдена.
    """
    if not record_id:
        return None
    record = db.query(model).filter(model.id == record_id).first()
    return getattr(record, area_field, None) if record else None
