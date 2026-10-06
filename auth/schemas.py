"""Pydantic-схемы запросов и ответов подсистемы аутентификации."""

from datetime import datetime

from pydantic import BaseModel


class AuthLoginResponse(BaseModel):
    """Ответ на успешный вход: JWT-токены и срок их действия."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int
    refresh_token: str | None = None


class AuthLogoutResponse(BaseModel):
    """Ответ на выход из системы."""

    username: str
    message: str = "Выход из системы выполнен"


class UserBase(BaseModel):
    """Базовые поля пользователя."""

    username: str
    email: str
    firstname: str | None = None
    lastname: str | None = None
    enabled: bool = True
    email_verified: bool = False
    temporary_password: bool = False


class UserCreate(UserBase):
    """Данные для создания пользователя (логин, пароль, опционально роль)."""

    password: str
    role: str | None = None


class UserUpdate(BaseModel):
    """Поля пользователя, доступные для обновления."""

    username: str | None = None
    email: str | None = None
    firstname: str | None = None
    lastname: str | None = None
    enabled: bool | None = None
    email_verified: bool | None = None
    temporary_password: bool | None = None


class UserPasswordUpdate(BaseModel):
    """Новый пароль пользователя."""

    password: str


class UserResponse(UserBase):
    """Представление пользователя в ответах API."""

    id: int

    class Config:
        """Конфигурация Pydantic v2: чтение атрибутов ORM-объектов."""

        from_attributes = True


class UserCreateResponse(BaseModel):
    """Ответ на создание/обновление пользователя."""

    user_id: int
    username: str
    role: str | None = None
    message: str


class RoleBase(BaseModel):
    """Базовые поля роли."""

    role_name: str


class RoleCreate(RoleBase):
    """Данные для создания роли."""


class RoleUpdate(RoleBase):
    """Данные для обновления роли."""


class RoleResponse(RoleBase):
    """Представление роли в ответах API."""

    id: int

    class Config:
        """Конфигурация Pydantic v2: чтение атрибутов ORM-объектов."""

        from_attributes = True


class SysFunctionBase(BaseModel):
    """Базовые поля системной функции."""

    func_description: str | None = None
    api_name: str


class SysFunctionResponse(SysFunctionBase):
    """Представление системной функции в ответах API."""

    id: int

    class Config:
        """Конфигурация Pydantic v2: чтение атрибутов ORM-объектов."""

        from_attributes = True


class User2RoleCreate(BaseModel):
    """Данные для назначения роли пользователю."""

    user_id: int
    role_id: int


class User2RoleResponse(BaseModel):
    """Связь пользователя и роли в ответах API."""

    user_id: int
    role_id: int

    class Config:
        """Конфигурация Pydantic v2: чтение атрибутов ORM-объектов."""

        from_attributes = True


class User2AreaCreate(BaseModel):
    """Данные для назначения зоны пользователю."""

    user_id: int
    production_area_id: int


class User2AreaResponse(BaseModel):
    """Связь пользователя и зоны в ответах API."""

    user_id: int
    production_area_id: int

    class Config:
        """Конфигурация Pydantic v2: чтение атрибутов ORM-объектов."""

        from_attributes = True


class Role2FunctionCreate(BaseModel):
    """Данные для назначения функции роли."""

    role_id: int
    function_id: int


class Role2FunctionResponse(BaseModel):
    """Связь роли и функции в ответах API."""

    role_id: int
    function_id: int

    class Config:
        """Конфигурация Pydantic v2: чтение атрибутов ORM-объектов."""

        from_attributes = True


class ProtocolEventResponse(BaseModel):
    """Событие протокола (аудита) в ответах API."""

    id: int
    created_at: datetime
    user_id: int | None = None
    username: str | None = None
    method: str
    path: str
    api_name: str | None = None
    status_code: int
    duration_ms: int | None = None
    client_ip: str | None = None
    error_detail: str | None = None

    class Config:
        """Конфигурация Pydantic v2: чтение атрибутов ORM-объектов."""

        from_attributes = True


class ProtocolSettingBase(BaseModel):
    """Базовые поля правила протоколирования."""

    api_name: str | None = None
    enabled: bool = True
    log_errors_only: bool = False


class ProtocolSettingCreate(ProtocolSettingBase):
    """Данные для создания правила протоколирования."""


class ProtocolSettingUpdate(BaseModel):
    """Поля правила протоколирования, доступные для обновления."""

    enabled: bool | None = None
    log_errors_only: bool | None = None


class ProtocolSettingResponse(ProtocolSettingBase):
    """Представление правила протоколирования в ответах API."""

    id: int

    class Config:
        """Конфигурация Pydantic v2: чтение атрибутов ORM-объектов."""

        from_attributes = True
