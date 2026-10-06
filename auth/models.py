"""SQLAlchemy-модели подсистемы аутентификации и авторизации (пп. 1-21 ТЗ).

Включает справочники пользователей, ролей и системных функций, таблицы связей
M:N, а также таблицы протоколирования (аудита) действий пользователей.
"""

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from database import Base


class User(Base):
    """Пользователь системы: учётные данные, статус и связи с ролями/зонами."""

    __tablename__ = "users"
    id = Column(BigInteger, primary_key=True, index=True, autoincrement=True)
    username = Column(String(80), unique=True, nullable=False, index=True)
    password = Column(String(256), nullable=False)
    email = Column(String(80), nullable=False)
    firstname = Column(String(80))
    lastname = Column(String(80))
    enabled = Column(Boolean, default=True, nullable=False)
    email_verified = Column(Boolean, default=False, nullable=False)
    temporary_password = Column(Boolean, default=False, nullable=False)

    roles = relationship("Role", secondary="users2roles", back_populates="users")
    areas = relationship("ProductionArea", secondary="user2areas", viewonly=True)


class Role(Base):
    """Роль пользователя (справочник)."""

    __tablename__ = "roles"
    id = Column(BigInteger, primary_key=True, index=True, autoincrement=True)
    role_name = Column(String(80), unique=True, nullable=False)

    users = relationship("User", secondary="users2roles", back_populates="roles")
    functions = relationship(
        "SysFunction", secondary="roles2functions", back_populates="roles"
    )


class User2Role(Base):
    """Связь M:N между пользователями и ролями."""

    __tablename__ = "users2roles"
    user_id = Column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role_id = Column(
        BigInteger, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )


class SysFunction(Base):
    """Системная функция API (справочник api_name вида 'entity.operation')."""

    __tablename__ = "sys_functions"
    id = Column(BigInteger, primary_key=True, index=True, autoincrement=True)
    func_description = Column(String(80))
    api_name = Column(String(80), unique=True, nullable=False)

    roles = relationship(
        "Role", secondary="roles2functions", back_populates="functions"
    )


class Role2Function(Base):
    """Связь M:N между ролями и системными функциями."""

    __tablename__ = "roles2functions"
    role_id = Column(
        BigInteger, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )
    function_id = Column(
        BigInteger, ForeignKey("sys_functions.id", ondelete="CASCADE"), primary_key=True
    )


class User2Area(Base):
    """Связь M:N между пользователями и производственными зонами."""

    __tablename__ = "user2areas"
    user_id = Column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    # production_areas.id — Integer (см. models.py), не BigInteger:
    # типы внешнего ключа должны совпадать с типом первичного ключа.
    production_area_id = Column(
        Integer, ForeignKey("production_areas.id", ondelete="CASCADE"), primary_key=True
    )


class ProtocolEvent(Base):
    """Запись протокола: кто, что и с каким результатом сделал в системе.

    Соответствует пп. 3.2.2.1-3.2.2.2 ТЗ — фиксирует успешные и отклонённые
    (401/402/403) запросы.
    """

    __tablename__ = "protocol_events"
    id = Column(BigInteger, primary_key=True, index=True, autoincrement=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    user_id = Column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    username = Column(String(80), nullable=True, index=True)
    method = Column(String(10), nullable=False)
    path = Column(String(255), nullable=False)
    api_name = Column(String(160), nullable=True, index=True)
    status_code = Column(Integer, nullable=False, index=True)
    duration_ms = Column(Integer, nullable=True)
    client_ip = Column(String(64), nullable=True)
    error_detail = Column(Text, nullable=True)


class ProtocolSetting(Base):
    """Правило протоколирования операций.

    api_name=NULL — правило по умолчанию для всех функций.
    """

    __tablename__ = "protocol_settings"
    id = Column(BigInteger, primary_key=True, index=True, autoincrement=True)
    api_name = Column(String(160), nullable=True)
    enabled = Column(Boolean, default=True, nullable=False)
    log_errors_only = Column(Boolean, default=False, nullable=False)
