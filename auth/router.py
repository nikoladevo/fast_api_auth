"""Роутеры аутентификации и авторизации (пп. 1-20 ТЗ) и протокола.

Протоколирование — п. 3.2.2.1-3.2.2.2 ТЗ.
"""

from contextlib import suppress
from datetime import datetime

import bcrypt as _bcrypt
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy.orm import Session

from database import get_db
from helpers import get_or_404
from models import ProductionArea
from schemas import ProductionAreaResponse
from videopc_logging import log_authentication, log_logout

from .crud import (
    protocol_event_crud,
    protocol_setting_crud,
    role2function_crud,
    role_crud,
    sys_function_crud,
    user2area_crud,
    user2role_crud,
    user_crud,
)
from .dependencies import get_current_user
from .keycloak_service import keycloak_service
from .models import Role, SysFunction, User
from .schemas import (
    AuthLoginResponse,
    AuthLogoutResponse,
    ProtocolEventResponse,
    ProtocolSettingCreate,
    ProtocolSettingResponse,
    ProtocolSettingUpdate,
    Role2FunctionResponse,
    RoleCreate,
    RoleResponse,
    RoleUpdate,
    SysFunctionResponse,
    User2AreaResponse,
    User2RoleResponse,
    UserCreate,
    UserCreateResponse,
    UserPasswordUpdate,
    UserResponse,
    UserUpdate,
)

auth_router = APIRouter(tags=["Auth"])

# ---------------------------------------------------------------------------
# 1) Login
# ---------------------------------------------------------------------------


@auth_router.post("/login", response_model=AuthLoginResponse)
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
) -> AuthLoginResponse:
    """Аутентифицирует пользователя через Keycloak и возвращает JWT-токены.

    Returns:
        Токены доступа и обновления.

    Raises:
        HTTPException: 422 при пустых полях, 401 при неверных учётных данных,
            500 при ошибке Keycloak.
    """
    client_ip = request.client.host if request.client else None
    if not username or not password:
        log_authentication(
            username, False, reason="не переданы логин или пароль", client_ip=client_ip
        )
        raise HTTPException(status_code=422, detail="username и password обязательны")
    try:
        result = keycloak_service.login(username, password)
    except Exception as e:
        error_msg = str(e)
        log_authentication(username, False, reason=error_msg, client_ip=client_ip)
        if "401" in error_msg or "Invalid" in error_msg.lower():
            raise HTTPException(
                status_code=401, detail="Неверные учётные данные"
            ) from None
        raise HTTPException(
            status_code=500, detail=f"Ошибка аутентификации: {error_msg}"
        ) from e
    log_authentication(username, True, client_ip=client_ip)
    return AuthLoginResponse(**result)


# ---------------------------------------------------------------------------
# 1a) Logout
# ---------------------------------------------------------------------------


@auth_router.post("/logout", response_model=AuthLogoutResponse)
def logout(
    request: Request,
    refresh_token: str | None = Form(None),
    current_user: User = Depends(get_current_user),
) -> AuthLogoutResponse:
    """Выход пользователя из системы.

    Сессия в Keycloak закрывается, если передан refresh_token. Сам факт выхода
    регистрируется в логах всегда, независимо от уровня логирования.

    Returns:
        Имя пользователя, завершившего сеанс.
    """
    client_ip = request.client.host if request.client else None
    warning = None
    if refresh_token:
        try:
            keycloak_service.logout(refresh_token)
        except Exception as e:
            # Выход не отменяется: токен мог истечь или быть отозван ранее.
            warning = str(e)
    log_logout(
        current_user.username,
        client_ip=client_ip,
        extra={"keycloak_error": warning} if warning else None,
    )
    return AuthLogoutResponse(username=current_user.username)


# ---------------------------------------------------------------------------
# 2) Создание пользователя
# ---------------------------------------------------------------------------


@auth_router.post("/users", response_model=UserCreateResponse, status_code=201)
def create_user(
    data: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UserCreateResponse:
    """Создаёт пользователя в Keycloak и локальной БД, при необходимости с ролью.

    Returns:
        Идентификатор и имя созданного пользователя.

    Raises:
        HTTPException: 400, если пользователь уже существует, роль не найдена
            или создание в Keycloak завершилось ошибкой.
    """
    if user_crud.get_by_username(db, data.username):
        raise HTTPException(status_code=400, detail="Пользователь уже существует")

    role_obj = None
    if data.role:
        role_obj = role_crud.get_by_name(db, data.role)
        if not role_obj:
            raise HTTPException(status_code=400, detail=f"Роль не найдена: {data.role}")

    try:
        keycloak_service.create_user(
            username=data.username,
            password=data.password,
            email=data.email,
            first_name=data.firstname or "",
            last_name=data.lastname or "",
            enabled=data.enabled,
            temporary_password=data.temporary_password,
        )
    except Exception as e:
        raise HTTPException(
            status_code=400, detail=f"Ошибка создания в Keycloak: {e}"
        ) from e

    hashed = _bcrypt.hashpw(data.password.encode(), _bcrypt.gensalt()).decode()
    db_user = user_crud.create(
        db,
        username=data.username,
        password=hashed,
        email=data.email,
        firstname=data.firstname,
        lastname=data.lastname,
        enabled=data.enabled,
        email_verified=data.email_verified,
        temporary_password=data.temporary_password,
    )

    role_name_assigned = None
    if role_obj:
        user2role_crud.create(db, user_id=db_user.id, role_id=role_obj.id)
        role_name_assigned = data.role

    return UserCreateResponse(
        user_id=db_user.id,
        username=db_user.username,
        role=role_name_assigned,
        message="Пользователь создан",
    )


# ---------------------------------------------------------------------------
# 3) Список пользователей
# ---------------------------------------------------------------------------


@auth_router.get("/users", response_model=list[UserResponse])
def list_users(
    username: str | None = None,
    firstname: str | None = None,
    lastname: str | None = None,
    enabled: bool | None = None,
    role: str | None = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[UserResponse]:
    """Возвращает список пользователей с фильтрацией.

    Returns:
        Список пользователей.
    """
    return user_crud.search_users(
        db,
        username=username,
        firstname=firstname,
        lastname=lastname,
        enabled=enabled,
        role_name=role,
        skip=skip,
        limit=limit,
    )


# ---------------------------------------------------------------------------
# 4) Получение пользователя по id
# ---------------------------------------------------------------------------


@auth_router.get("/users/{user_id}", response_model=UserResponse)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    """Возвращает пользователя по идентификатору.

    Returns:
        Пользователь.

    Raises:
        HTTPException: 400, если пользователь не найден.
    """
    user = user_crud.get(db, user_id)
    if not user:
        raise HTTPException(status_code=400, detail="Пользователь не найден")
    return user


# ---------------------------------------------------------------------------
# 5) Изменение пользователя
# ---------------------------------------------------------------------------


@auth_router.put("/users/{user_id}", response_model=UserCreateResponse)
def update_user(
    user_id: int,
    data: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UserCreateResponse:
    """Обновляет поля пользователя в Keycloak и локальной БД.

    Returns:
        Идентификатор и имя обновлённого пользователя.

    Raises:
        HTTPException: 400, если пользователь не найден; 500 при ошибке Keycloak.
    """
    user = user_crud.get(db, user_id)
    if not user:
        raise HTTPException(status_code=400, detail="Пользователь не найден")

    update_fields = data.model_dump(exclude_unset=True)

    kc_id = keycloak_service.get_user_id_by_username(user.username)
    if kc_id:
        kc_update = {}
        if "email" in update_fields:
            kc_update["email"] = update_fields["email"]
        if "firstname" in update_fields:
            kc_update["first_name"] = update_fields["firstname"]
        if "lastname" in update_fields:
            kc_update["last_name"] = update_fields["lastname"]
        if "enabled" in update_fields:
            kc_update["enabled"] = update_fields["enabled"]
        if kc_update:
            try:
                keycloak_service.update_user(kc_id, **kc_update)
            except Exception as e:
                raise HTTPException(
                    status_code=500, detail=f"Ошибка обновления в Keycloak: {e}"
                ) from e

    updated = user_crud.update(db, user_id, **update_fields)
    return UserCreateResponse(
        user_id=updated.id,
        username=updated.username,
        role=None,
        message="Пользователь обновлён",
    )


# ---------------------------------------------------------------------------
# 6) Удаление пользователя
# ---------------------------------------------------------------------------


@auth_router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, object]:
    """Удаляет пользователя из Keycloak и локальной БД.

    Удаление блокируется, если у пользователя остались роли или зоны.

    Returns:
        Сообщение и идентификатор удалённого пользователя.

    Raises:
        HTTPException: 400, если пользователь не найден или у него есть
            связанные роли/зоны.
    """
    user = user_crud.get(db, user_id)
    if not user:
        raise HTTPException(status_code=400, detail="Пользователь не найден")

    roles = user2role_crud.get_by_user(db, user_id)
    areas = user2area_crud.get_by_user(db, user_id)
    if roles or areas:
        raise HTTPException(
            status_code=400,
            detail="Удаление записи пользователя не возможно. "
            "Удалите связанные записи по назначенным ему ролям "
            "и производственным зонам.",
        )

    kc_id = keycloak_service.get_user_id_by_username(user.username)
    if kc_id:
        with suppress(Exception):
            keycloak_service.delete_user(kc_id)

    user_crud.delete(db, user_id)
    return {"message": "Пользователь удалён", "user_id": user_id}


# ---------------------------------------------------------------------------
# 7) Роли пользователя
# ---------------------------------------------------------------------------


@auth_router.get("/users/{user_id}/roles", response_model=list[RoleResponse])
def get_user_roles(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[RoleResponse]:
    """Возвращает роли, назначенные пользователю.

    Returns:
        Список ролей.

    Raises:
        HTTPException: 400, если пользователь не найден или у него нет ролей.
    """
    user = user_crud.get(db, user_id)
    if not user:
        raise HTTPException(status_code=400, detail="Пользователь не найден")
    links = user2role_crud.get_by_user(db, user_id)
    if not links:
        raise HTTPException(status_code=400, detail="Роли пользователя не найдены")
    role_ids = [link.role_id for link in links]
    return db.query(Role).filter(Role.id.in_(role_ids)).all()


# ---------------------------------------------------------------------------
# 8) Добавление роли пользователю
# ---------------------------------------------------------------------------


@auth_router.post(
    "/users/{user_id}/roles/{role_id}",
    response_model=User2RoleResponse,
    status_code=201,
)
def add_user_role(
    user_id: int,
    role_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> User2RoleResponse:
    """Назначает роль пользователю.

    Returns:
        Созданная связь пользователя и роли.

    Raises:
        HTTPException: 400, если пользователь или роль не найдены, либо роль
            уже назначена.
    """
    if not user_crud.get(db, user_id):
        raise HTTPException(status_code=400, detail="Пользователь не найден")
    if not role_crud.get(db, role_id):
        raise HTTPException(status_code=400, detail="Роль не найдена")
    if user2role_crud.get(db, user_id, role_id):
        raise HTTPException(status_code=400, detail="Роль уже назначена пользователю")
    return user2role_crud.create(db, user_id=user_id, role_id=role_id)


# ---------------------------------------------------------------------------
# 9) Удаление роли у пользователя
# ---------------------------------------------------------------------------


@auth_router.delete("/users/{user_id}/roles/{role_id}")
def remove_user_role(
    user_id: int,
    role_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, object]:
    """Удаляет роль у пользователя.

    Returns:
        Сообщение и идентификаторы пользователя и роли.

    Raises:
        HTTPException: 400, если связь не найдена.
    """
    if not user2role_crud.get(db, user_id, role_id):
        raise HTTPException(status_code=400, detail="Роль пользователя не найдена")
    user2role_crud.delete(db, user_id, role_id)
    return {
        "message": "Роль удалена у пользователя",
        "user_id": user_id,
        "role_id": role_id,
    }


# ---------------------------------------------------------------------------
# 10) Зоны пользователя
# ---------------------------------------------------------------------------


@auth_router.get("/users/{user_id}/areas", response_model=list[ProductionAreaResponse])
def get_user_areas(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ProductionAreaResponse]:
    """Возвращает производственные зоны, назначенные пользователю.

    Returns:
        Список производственных зон.

    Raises:
        HTTPException: 400, если пользователь не найден или у него нет зон.
    """
    user = user_crud.get(db, user_id)
    if not user:
        raise HTTPException(status_code=400, detail="Пользователь не найден")
    links = user2area_crud.get_by_user(db, user_id)
    if not links:
        raise HTTPException(status_code=400, detail="Зоны пользователя не найдены")
    area_ids = [link.production_area_id for link in links]
    return db.query(ProductionArea).filter(ProductionArea.id.in_(area_ids)).all()


# ---------------------------------------------------------------------------
# 11) Добавление зоны пользователю
# ---------------------------------------------------------------------------


@auth_router.post(
    "/users/{user_id}/areas/{area_id}",
    response_model=User2AreaResponse,
    status_code=201,
)
def add_user_area(
    user_id: int,
    area_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> User2AreaResponse:
    """Назначает производственную зону пользователю.

    Returns:
        Созданная связь пользователя и зоны.

    Raises:
        HTTPException: 400, если пользователь или зона не найдены, либо зона
            уже назначена.
    """
    if not user_crud.get(db, user_id):
        raise HTTPException(status_code=400, detail="Пользователь не найден")
    if not db.query(ProductionArea).filter(ProductionArea.id == area_id).first():
        raise HTTPException(status_code=400, detail="Производственная зона не найдена")
    if user2area_crud.get(db, user_id, area_id):
        raise HTTPException(status_code=400, detail="Зона уже назначена пользователю")
    link = user2area_crud.create(db, user_id=user_id, production_area_id=area_id)
    return User2AreaResponse(
        user_id=link.user_id, production_area_id=link.production_area_id
    )


# ---------------------------------------------------------------------------
# 12) Удаление зоны у пользователя
# ---------------------------------------------------------------------------


@auth_router.delete("/users/{user_id}/areas/{area_id}")
def remove_user_area(
    user_id: int,
    area_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, object]:
    """Удаляет производственную зону у пользователя.

    Returns:
        Сообщение и идентификаторы пользователя и зоны.

    Raises:
        HTTPException: 400, если связь не найдена.
    """
    if not user2area_crud.get(db, user_id, area_id):
        raise HTTPException(status_code=400, detail="Зона у пользователя не найдена")
    user2area_crud.delete(db, user_id, area_id)
    return {
        "message": "Зона удалена у пользователя",
        "user_id": user_id,
        "production_area_id": area_id,
    }


# ---------------------------------------------------------------------------
# 13) Список ролей
# ---------------------------------------------------------------------------


@auth_router.get("/roles", response_model=list[RoleResponse])
def list_roles(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[RoleResponse]:
    """Возвращает список ролей.

    Returns:
        Список ролей.

    Raises:
        HTTPException: 400, если роли не найдены.
    """
    roles = role_crud.get_all(db)
    if not roles:
        raise HTTPException(status_code=400, detail="Роли не найдены")
    return roles


# ---------------------------------------------------------------------------
# 14) Создание роли
# ---------------------------------------------------------------------------


@auth_router.post("/roles", response_model=RoleResponse, status_code=201)
def create_role(
    data: RoleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RoleResponse:
    """Создаёт роль.

    Returns:
        Созданная роль.

    Raises:
        HTTPException: 400, если роль с таким именем уже существует.
    """
    if role_crud.get_by_name(db, data.role_name):
        raise HTTPException(status_code=400, detail="Роль уже существует")
    return role_crud.create(db, role_name=data.role_name)


# ---------------------------------------------------------------------------
# 15) Изменение роли
# ---------------------------------------------------------------------------


@auth_router.put("/roles/{role_id}", response_model=RoleResponse)
def update_role(
    role_id: int,
    data: RoleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RoleResponse:
    """Изменяет имя роли.

    Returns:
        Обновлённая роль.

    Raises:
        HTTPException: 400, если роль не найдена.
    """
    role = role_crud.get(db, role_id)
    if not role:
        raise HTTPException(status_code=400, detail="Роль не найдена")
    return role_crud.update(db, role_id, role_name=data.role_name)


# ---------------------------------------------------------------------------
# 16) Удаление роли
# ---------------------------------------------------------------------------


@auth_router.delete("/roles/{role_id}")
def delete_role(
    role_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, object]:
    """Удаляет роль.

    Удаление блокируется, если у роли остались назначенные функции.

    Returns:
        Сообщение и идентификатор удалённой роли.

    Raises:
        HTTPException: 400, если роль не найдена или у неё есть функции.
    """
    role = role_crud.get(db, role_id)
    if not role:
        raise HTTPException(status_code=400, detail="Роль не найдена")
    funcs = role2function_crud.get_by_role(db, role_id)
    if funcs:
        raise HTTPException(
            status_code=400,
            detail="Удаление записи роли не возможно. "
            "Удалите связанные записи по назначенным функциям.",
        )
    role_crud.delete(db, role_id)
    return {"message": "Роль удалена", "role_id": role_id}


# ---------------------------------------------------------------------------
# 17) Функции, назначенные роли
# ---------------------------------------------------------------------------


@auth_router.get("/roles/{role_id}/functions", response_model=list[SysFunctionResponse])
def get_role_functions(
    role_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[SysFunctionResponse]:
    """Возвращает системные функции, назначенные роли.

    Returns:
        Список системных функций.

    Raises:
        HTTPException: 400, если роль не найдена или у неё нет функций.
    """
    role = role_crud.get(db, role_id)
    if not role:
        raise HTTPException(status_code=400, detail="Роль не найдена")
    links = role2function_crud.get_by_role(db, role_id)
    if not links:
        raise HTTPException(
            status_code=400, detail="Системные функции у роли не найдены"
        )
    func_ids = [link.function_id for link in links]
    return db.query(SysFunction).filter(SysFunction.id.in_(func_ids)).all()


# ---------------------------------------------------------------------------
# 18) Добавление функции для роли
# ---------------------------------------------------------------------------


@auth_router.post(
    "/roles/{role_id}/functions/{function_id}",
    response_model=Role2FunctionResponse,
    status_code=201,
)
def add_role_function(
    role_id: int,
    function_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Role2FunctionResponse:
    """Назначает системную функцию роли.

    Returns:
        Созданная связь роли и функции.

    Raises:
        HTTPException: 400, если роль или функция не найдены, либо функция
            уже назначена.
    """
    if not role_crud.get(db, role_id):
        raise HTTPException(status_code=400, detail="Роль не найдена")
    if not sys_function_crud.get(db, function_id):
        raise HTTPException(status_code=400, detail="Функция не найдена")
    if role2function_crud.get(db, role_id, function_id):
        raise HTTPException(status_code=400, detail="Функция уже назначена роли")
    return role2function_crud.create(db, role_id=role_id, function_id=function_id)


# ---------------------------------------------------------------------------
# 19) Удаление функции у роли
# ---------------------------------------------------------------------------


@auth_router.delete("/roles/{role_id}/functions/{function_id}")
def remove_role_function(
    role_id: int,
    function_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, object]:
    """Удаляет системную функцию у роли.

    Returns:
        Сообщение и идентификаторы роли и функции.

    Raises:
        HTTPException: 400, если связь не найдена.
    """
    if not role2function_crud.get(db, role_id, function_id):
        raise HTTPException(status_code=400, detail="Функция у роли не найдена")
    role2function_crud.delete(db, role_id, function_id)
    return {
        "message": "Функция удалена у роли",
        "role_id": role_id,
        "function_id": function_id,
    }


# ---------------------------------------------------------------------------
# 20) Список системных функций
# ---------------------------------------------------------------------------


@auth_router.get("/sys-functions", response_model=list[SysFunctionResponse])
def list_sys_functions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[SysFunctionResponse]:
    """Возвращает список системных функций.

    Returns:
        Список системных функций.

    Raises:
        HTTPException: 400, если функции не найдены.
    """
    funcs = sys_function_crud.get_all(db)
    if not funcs:
        raise HTTPException(status_code=400, detail="Функции не найдены")
    return funcs


# ---------------------------------------------------------------------------
# Смена пароля (вспомогательный, для UI п.8)
# ---------------------------------------------------------------------------


@auth_router.put("/users/{user_id}/password")
def change_password(
    user_id: int,
    data: UserPasswordUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, object]:
    """Меняет пароль пользователя в Keycloak и локальной БД.

    Returns:
        Сообщение и идентификатор пользователя.

    Raises:
        HTTPException: 400, если пользователь не найден; 500 при ошибке Keycloak.
    """
    user = user_crud.get(db, user_id)
    if not user:
        raise HTTPException(status_code=400, detail="Пользователь не найден")

    kc_id = keycloak_service.get_user_id_by_username(user.username)
    if kc_id:
        try:
            keycloak_service.reset_password(kc_id, data.password)
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Ошибка смены пароля в Keycloak: {e}"
            ) from e

    hashed = _bcrypt.hashpw(data.password.encode(), _bcrypt.gensalt()).decode()
    user_crud.update(db, user_id, password=hashed)
    return {"message": "Пароль изменён", "user_id": user_id}


# ---------------------------------------------------------------------------
# Протокол (п. 3.2.2.1-3.2.2.2 ТЗ): доступ к данным протоколов
# ---------------------------------------------------------------------------


@auth_router.get("/protocol-events", response_model=list[ProtocolEventResponse])
def list_protocol_events(
    username: str | None = None,
    api_name: str | None = None,
    method: str | None = None,
    status_code: int | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ProtocolEventResponse]:
    """Возвращает события протокола с фильтрацией.

    Returns:
        Список событий протокола.
    """
    if limit > 1000:
        limit = 1000
    return protocol_event_crud.search(
        db,
        username=username,
        api_name=api_name,
        method=method,
        status_code=status_code,
        date_from=date_from,
        date_to=date_to,
        skip=skip,
        limit=limit,
    )


@auth_router.get("/protocol-events/{event_id}", response_model=ProtocolEventResponse)
def get_protocol_event(
    event_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProtocolEventResponse:
    """Возвращает событие протокола по идентификатору.

    Returns:
        Событие протокола.
    """
    return get_or_404(protocol_event_crud, db, event_id)


# ---------------------------------------------------------------------------
# Протокол: приём, хранение, предоставление настроек правил протоколирования
# ---------------------------------------------------------------------------


@auth_router.get("/protocol-settings", response_model=list[ProtocolSettingResponse])
def list_protocol_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ProtocolSettingResponse]:
    """Возвращает список правил протоколирования.

    Returns:
        Список правил протоколирования.
    """
    return protocol_setting_crud.get_all(db)


@auth_router.post(
    "/protocol-settings", response_model=ProtocolSettingResponse, status_code=201
)
def create_protocol_setting(
    data: ProtocolSettingCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProtocolSettingResponse:
    """Создаёт правило протоколирования.

    Returns:
        Созданное правило протоколирования.

    Raises:
        HTTPException: 400, если правило для функции (или правило по умолчанию)
            уже существует.
    """
    if protocol_setting_crud.get_by_api_name(db, data.api_name):
        raise HTTPException(
            status_code=400,
            detail="Правило для этой функции (или правило по умолчанию) уже существует",
        )
    return protocol_setting_crud.create(db, **data.model_dump())


@auth_router.put(
    "/protocol-settings/{setting_id}", response_model=ProtocolSettingResponse
)
def update_protocol_setting(
    setting_id: int,
    data: ProtocolSettingUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProtocolSettingResponse:
    """Обновляет правило протоколирования.

    Returns:
        Обновлённое правило протоколирования.

    Raises:
        HTTPException: 400, если правило не найдено.
    """
    if not protocol_setting_crud.get(db, setting_id):
        raise HTTPException(status_code=400, detail="Правило не найдено")
    return protocol_setting_crud.update(
        db, setting_id, **data.model_dump(exclude_unset=True)
    )


@auth_router.delete("/protocol-settings/{setting_id}")
def delete_protocol_setting(
    setting_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, object]:
    """Удаляет правило протоколирования.

    Returns:
        Сообщение и идентификатор удалённого правила.

    Raises:
        HTTPException: 400, если правило не найдено.
    """
    if not protocol_setting_crud.delete(db, setting_id):
        raise HTTPException(status_code=400, detail="Правило не найдено")
    return {"message": "Правило удалено", "id": setting_id}
