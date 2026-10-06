"""CRUD-классы для сущностей подсистемы аутентификации и авторизации."""

from datetime import datetime

from sqlalchemy.orm import Session

from . import models


class UserCRUD:
    """CRUD-операции над пользователями (таблица users)."""

    def __init__(self) -> None:
        """Инициализирует CRUD для модели User."""
        self.model = models.User

    def create(self, db: Session, **kwargs: object) -> models.User:
        """Создаёт пользователя.

        Args:
            db: Сессия БД.
            **kwargs: Поля создаваемой записи.

        Returns:
            Созданный пользователь.
        """
        db_obj = self.model(**kwargs)
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def get(self, db: Session, id: int) -> models.User | None:
        """Возвращает пользователя по id.

        Args:
            db: Сессия БД.
            id: Идентификатор пользователя.

        Returns:
            Пользователь или None, если не найден.
        """
        return db.query(self.model).filter(self.model.id == id).first()

    def get_all(
        self, db: Session, skip: int = 0, limit: int = 100
    ) -> list[models.User]:
        """Возвращает список пользователей с пагинацией.

        Args:
            db: Сессия БД.
            skip: Число пропускаемых записей.
            limit: Максимальное число записей.

        Returns:
            Список пользователей.
        """
        return db.query(self.model).offset(skip).limit(limit).all()

    def update(self, db: Session, id: int, **kwargs: object) -> models.User | None:
        """Обновляет поля пользователя по id.

        Args:
            db: Сессия БД.
            id: Идентификатор пользователя.
            **kwargs: Обновляемые поля.

        Returns:
            Обновлённый пользователь или None, если не найден.
        """
        db_obj = self.get(db, id)
        if db_obj:
            for key, value in kwargs.items():
                if hasattr(db_obj, key):
                    setattr(db_obj, key, value)
            db.commit()
            db.refresh(db_obj)
        return db_obj

    def delete(self, db: Session, id: int) -> bool:
        """Удаляет пользователя по id.

        Args:
            db: Сессия БД.
            id: Идентификатор пользователя.

        Returns:
            True, если запись удалена, иначе False.
        """
        db_obj = self.get(db, id)
        if db_obj:
            db.delete(db_obj)
            db.commit()
            return True
        return False

    def get_by_username(self, db: Session, username: str) -> models.User | None:
        """Возвращает пользователя по имени учётной записи.

        Args:
            db: Сессия БД.
            username: Имя учётной записи.

        Returns:
            Пользователь или None, если не найден.
        """
        return db.query(self.model).filter(self.model.username == username).first()

    def search_users(
        self,
        db: Session,
        username: str | None = None,
        firstname: str | None = None,
        lastname: str | None = None,
        enabled: bool | None = None,
        role_name: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[models.User]:
        """Возвращает список пользователей по фильтрам.

        Args:
            db: Сессия БД.
            username: Частичное совпадение по имени учётной записи.
            firstname: Частичное совпадение по имени.
            lastname: Частичное совпадение по фамилии.
            enabled: Фильтр по признаку активности.
            role_name: Частичное совпадение по имени роли.
            skip: Число пропускаемых записей.
            limit: Максимальное число записей.

        Returns:
            Отфильтрованный список пользователей.
        """
        query = db.query(self.model)
        if username:
            query = query.filter(self.model.username.ilike(f"%{username}%"))
        if firstname:
            query = query.filter(self.model.firstname.ilike(f"%{firstname}%"))
        if lastname:
            query = query.filter(self.model.lastname.ilike(f"%{lastname}%"))
        if enabled is not None:
            query = query.filter(self.model.enabled == enabled)
        if role_name:
            query = (
                query.join(models.User2Role)
                .join(models.Role)
                .filter(models.Role.role_name.ilike(f"%{role_name}%"))
            )
        return query.offset(skip).limit(limit).all()


class RoleCRUD:
    """CRUD-операции над ролями (таблица roles)."""

    def __init__(self) -> None:
        """Инициализирует CRUD для модели Role."""
        self.model = models.Role

    def create(self, db: Session, **kwargs: object) -> models.Role:
        """Создаёт роль.

        Args:
            db: Сессия БД.
            **kwargs: Поля создаваемой записи.

        Returns:
            Созданная роль.
        """
        db_obj = self.model(**kwargs)
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def get(self, db: Session, id: int) -> models.Role | None:
        """Возвращает роль по id.

        Args:
            db: Сессия БД.
            id: Идентификатор роли.

        Returns:
            Роль или None, если не найдена.
        """
        return db.query(self.model).filter(self.model.id == id).first()

    def get_all(
        self, db: Session, skip: int = 0, limit: int = 100
    ) -> list[models.Role]:
        """Возвращает список ролей с пагинацией.

        Args:
            db: Сессия БД.
            skip: Число пропускаемых записей.
            limit: Максимальное число записей.

        Returns:
            Список ролей.
        """
        return db.query(self.model).offset(skip).limit(limit).all()

    def update(self, db: Session, id: int, **kwargs: object) -> models.Role | None:
        """Обновляет поля роли по id.

        Args:
            db: Сессия БД.
            id: Идентификатор роли.
            **kwargs: Обновляемые поля.

        Returns:
            Обновлённая роль или None, если не найдена.
        """
        db_obj = self.get(db, id)
        if db_obj:
            for key, value in kwargs.items():
                if hasattr(db_obj, key):
                    setattr(db_obj, key, value)
            db.commit()
            db.refresh(db_obj)
        return db_obj

    def delete(self, db: Session, id: int) -> bool:
        """Удаляет роль по id.

        Args:
            db: Сессия БД.
            id: Идентификатор роли.

        Returns:
            True, если запись удалена, иначе False.
        """
        db_obj = self.get(db, id)
        if db_obj:
            db.delete(db_obj)
            db.commit()
            return True
        return False

    def get_by_name(self, db: Session, role_name: str) -> models.Role | None:
        """Возвращает роль по имени.

        Args:
            db: Сессия БД.
            role_name: Имя роли.

        Returns:
            Роль или None, если не найдена.
        """
        return db.query(self.model).filter(self.model.role_name == role_name).first()


class SysFunctionCRUD:
    """CRUD-операции над системными функциями (таблица sys_functions)."""

    def __init__(self) -> None:
        """Инициализирует CRUD для модели SysFunction."""
        self.model = models.SysFunction

    def create(self, db: Session, **kwargs: object) -> models.SysFunction:
        """Создаёт системную функцию.

        Args:
            db: Сессия БД.
            **kwargs: Поля создаваемой записи.

        Returns:
            Созданная функция.
        """
        db_obj = self.model(**kwargs)
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def get(self, db: Session, id: int) -> models.SysFunction | None:
        """Возвращает системную функцию по id.

        Args:
            db: Сессия БД.
            id: Идентификатор функции.

        Returns:
            Функция или None, если не найдена.
        """
        return db.query(self.model).filter(self.model.id == id).first()

    def get_all(
        self, db: Session, skip: int = 0, limit: int = 100
    ) -> list[models.SysFunction]:
        """Возвращает список системных функций с пагинацией.

        Args:
            db: Сессия БД.
            skip: Число пропускаемых записей.
            limit: Максимальное число записей.

        Returns:
            Список функций.
        """
        return db.query(self.model).offset(skip).limit(limit).all()

    def get_by_api_name(self, db: Session, api_name: str) -> models.SysFunction | None:
        """Возвращает системную функцию по api_name.

        Args:
            db: Сессия БД.
            api_name: Имя функции API вида 'entity.operation'.

        Returns:
            Функция или None, если не найдена.
        """
        return db.query(self.model).filter(self.model.api_name == api_name).first()


class User2RoleCRUD:
    """CRUD-операции над связями пользователь-роль (таблица users2roles)."""

    def __init__(self) -> None:
        """Инициализирует CRUD для модели User2Role."""
        self.model = models.User2Role

    def create(self, db: Session, user_id: int, role_id: int) -> models.User2Role:
        """Назначает роль пользователю.

        Args:
            db: Сессия БД.
            user_id: Идентификатор пользователя.
            role_id: Идентификатор роли.

        Returns:
            Созданная связь.
        """
        db_obj = self.model(user_id=user_id, role_id=role_id)
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def get(self, db: Session, user_id: int, role_id: int) -> models.User2Role | None:
        """Возвращает связь пользователь-роль.

        Args:
            db: Сессия БД.
            user_id: Идентификатор пользователя.
            role_id: Идентификатор роли.

        Returns:
            Связь или None, если не найдена.
        """
        return (
            db.query(self.model)
            .filter(
                self.model.user_id == user_id,
                self.model.role_id == role_id,
            )
            .first()
        )

    def get_by_user(self, db: Session, user_id: int) -> list[models.User2Role]:
        """Возвращает все связи ролей пользователя.

        Args:
            db: Сессия БД.
            user_id: Идентификатор пользователя.

        Returns:
            Список связей.
        """
        return db.query(self.model).filter(self.model.user_id == user_id).all()

    def delete(self, db: Session, user_id: int, role_id: int) -> bool:
        """Удаляет связь пользователь-роль.

        Args:
            db: Сессия БД.
            user_id: Идентификатор пользователя.
            role_id: Идентификатор роли.

        Returns:
            True, если запись удалена, иначе False.
        """
        db_obj = self.get(db, user_id, role_id)
        if db_obj:
            db.delete(db_obj)
            db.commit()
            return True
        return False


class Role2FunctionCRUD:
    """CRUD-операции над связями роль-функция (таблица roles2functions)."""

    def __init__(self) -> None:
        """Инициализирует CRUD для модели Role2Function."""
        self.model = models.Role2Function

    def create(
        self, db: Session, role_id: int, function_id: int
    ) -> models.Role2Function:
        """Назначает функцию роли.

        Args:
            db: Сессия БД.
            role_id: Идентификатор роли.
            function_id: Идентификатор функции.

        Returns:
            Созданная связь.
        """
        db_obj = self.model(role_id=role_id, function_id=function_id)
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def get(
        self, db: Session, role_id: int, function_id: int
    ) -> models.Role2Function | None:
        """Возвращает связь роль-функция.

        Args:
            db: Сессия БД.
            role_id: Идентификатор роли.
            function_id: Идентификатор функции.

        Returns:
            Связь или None, если не найдена.
        """
        return (
            db.query(self.model)
            .filter(
                self.model.role_id == role_id,
                self.model.function_id == function_id,
            )
            .first()
        )

    def get_by_role(self, db: Session, role_id: int) -> list[models.Role2Function]:
        """Возвращает все связи функций роли.

        Args:
            db: Сессия БД.
            role_id: Идентификатор роли.

        Returns:
            Список связей.
        """
        return db.query(self.model).filter(self.model.role_id == role_id).all()

    def delete(self, db: Session, role_id: int, function_id: int) -> bool:
        """Удаляет связь роль-функция.

        Args:
            db: Сессия БД.
            role_id: Идентификатор роли.
            function_id: Идентификатор функции.

        Returns:
            True, если запись удалена, иначе False.
        """
        db_obj = self.get(db, role_id, function_id)
        if db_obj:
            db.delete(db_obj)
            db.commit()
            return True
        return False


class User2AreaCRUD:
    """CRUD-операции над связями пользователь-зона (таблица user2areas)."""

    def __init__(self) -> None:
        """Инициализирует CRUD для модели User2Area."""
        self.model = models.User2Area

    def create(
        self, db: Session, user_id: int, production_area_id: int
    ) -> models.User2Area:
        """Назначает производственную зону пользователю.

        Args:
            db: Сессия БД.
            user_id: Идентификатор пользователя.
            production_area_id: Идентификатор производственной зоны.

        Returns:
            Созданная связь.
        """
        db_obj = self.model(user_id=user_id, production_area_id=production_area_id)
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def get(
        self, db: Session, user_id: int, production_area_id: int
    ) -> models.User2Area | None:
        """Возвращает связь пользователь-зона.

        Args:
            db: Сессия БД.
            user_id: Идентификатор пользователя.
            production_area_id: Идентификатор производственной зоны.

        Returns:
            Связь или None, если не найдена.
        """
        return (
            db.query(self.model)
            .filter(
                self.model.user_id == user_id,
                self.model.production_area_id == production_area_id,
            )
            .first()
        )

    def get_by_user(self, db: Session, user_id: int) -> list[models.User2Area]:
        """Возвращает все связи зон пользователя.

        Args:
            db: Сессия БД.
            user_id: Идентификатор пользователя.

        Returns:
            Список связей.
        """
        return db.query(self.model).filter(self.model.user_id == user_id).all()

    def delete(self, db: Session, user_id: int, production_area_id: int) -> bool:
        """Удаляет связь пользователь-зона.

        Args:
            db: Сессия БД.
            user_id: Идентификатор пользователя.
            production_area_id: Идентификатор производственной зоны.

        Returns:
            True, если запись удалена, иначе False.
        """
        db_obj = self.get(db, user_id, production_area_id)
        if db_obj:
            db.delete(db_obj)
            db.commit()
            return True
        return False


class ProtocolEventCRUD:
    """CRUD-операции над событиями протокола (таблица protocol_events)."""

    def __init__(self) -> None:
        """Инициализирует CRUD для модели ProtocolEvent."""
        self.model = models.ProtocolEvent

    def create(self, db: Session, **kwargs: object) -> models.ProtocolEvent:
        """Создаёт событие протокола.

        Args:
            db: Сессия БД.
            **kwargs: Поля создаваемой записи.

        Returns:
            Созданное событие.
        """
        db_obj = self.model(**kwargs)
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def get(self, db: Session, id: int) -> models.ProtocolEvent | None:
        """Возвращает событие протокола по id.

        Args:
            db: Сессия БД.
            id: Идентификатор события.

        Returns:
            Событие или None, если не найдено.
        """
        return db.query(self.model).filter(self.model.id == id).first()

    def search(
        self,
        db: Session,
        username: str | None = None,
        api_name: str | None = None,
        method: str | None = None,
        status_code: int | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[models.ProtocolEvent]:
        """Возвращает события протокола по фильтрам (в порядке убывания времени).

        Args:
            db: Сессия БД.
            username: Частичное совпадение по имени пользователя.
            api_name: Точное совпадение по имени функции API.
            method: HTTP-метод.
            status_code: Код ответа.
            date_from: Нижняя граница времени создания.
            date_to: Верхняя граница времени создания.
            skip: Число пропускаемых записей.
            limit: Максимальное число записей.

        Returns:
            Отфильтрованный список событий.
        """
        query = db.query(self.model)
        if username:
            query = query.filter(self.model.username.ilike(f"%{username}%"))
        if api_name:
            query = query.filter(self.model.api_name == api_name)
        if method:
            query = query.filter(self.model.method == method.upper())
        if status_code is not None:
            query = query.filter(self.model.status_code == status_code)
        if date_from:
            query = query.filter(self.model.created_at >= date_from)
        if date_to:
            query = query.filter(self.model.created_at <= date_to)
        return (
            query.order_by(self.model.created_at.desc()).offset(skip).limit(limit).all()
        )


class ProtocolSettingCRUD:
    """CRUD-операции над правилами протоколирования (таблица protocol_settings)."""

    def __init__(self) -> None:
        """Инициализирует CRUD для модели ProtocolSetting."""
        self.model = models.ProtocolSetting

    def create(self, db: Session, **kwargs: object) -> models.ProtocolSetting:
        """Создаёт правило протоколирования.

        Args:
            db: Сессия БД.
            **kwargs: Поля создаваемой записи.

        Returns:
            Созданное правило.
        """
        db_obj = self.model(**kwargs)
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def get(self, db: Session, id: int) -> models.ProtocolSetting | None:
        """Возвращает правило протоколирования по id.

        Args:
            db: Сессия БД.
            id: Идентификатор правила.

        Returns:
            Правило или None, если не найдено.
        """
        return db.query(self.model).filter(self.model.id == id).first()

    def get_all(
        self, db: Session, skip: int = 0, limit: int = 100
    ) -> list[models.ProtocolSetting]:
        """Возвращает список правил протоколирования с пагинацией.

        Args:
            db: Сессия БД.
            skip: Число пропускаемых записей.
            limit: Максимальное число записей.

        Returns:
            Список правил.
        """
        return db.query(self.model).offset(skip).limit(limit).all()

    def get_by_api_name(
        self, db: Session, api_name: str | None
    ) -> models.ProtocolSetting | None:
        """Возвращает правило протоколирования по api_name.

        Args:
            db: Сессия БД.
            api_name: Имя функции API (None — правило по умолчанию).

        Returns:
            Правило или None, если не найдено.
        """
        return db.query(self.model).filter(self.model.api_name == api_name).first()

    def update(
        self, db: Session, id: int, **kwargs: object
    ) -> models.ProtocolSetting | None:
        """Обновляет поля правила протоколирования по id.

        Args:
            db: Сессия БД.
            id: Идентификатор правила.
            **kwargs: Обновляемые поля.

        Returns:
            Обновлённое правило или None, если не найдено.
        """
        db_obj = self.get(db, id)
        if db_obj:
            for key, value in kwargs.items():
                if hasattr(db_obj, key):
                    setattr(db_obj, key, value)
            db.commit()
            db.refresh(db_obj)
        return db_obj

    def delete(self, db: Session, id: int) -> bool:
        """Удаляет правило протоколирования по id.

        Args:
            db: Сессия БД.
            id: Идентификатор правила.

        Returns:
            True, если запись удалена, иначе False.
        """
        db_obj = self.get(db, id)
        if db_obj:
            db.delete(db_obj)
            db.commit()
            return True
        return False


user_crud = UserCRUD()
role_crud = RoleCRUD()
sys_function_crud = SysFunctionCRUD()
user2role_crud = User2RoleCRUD()
role2function_crud = Role2FunctionCRUD()
user2area_crud = User2AreaCRUD()
protocol_event_crud = ProtocolEventCRUD()
protocol_setting_crud = ProtocolSettingCRUD()
