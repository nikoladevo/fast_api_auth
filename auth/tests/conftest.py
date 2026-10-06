"""Фикстуры для тестов auth-пакета. Тестовая PostgreSQL БД + мок Keycloak."""

import os
import sys
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

# Добавляем каталог fastapi (для database/models/...) в sys.path.
# Корень репозитория (для videopc_logging) добавляет fastapi/conftest.py.
_fastapi_dir = str(Path(__file__).resolve().parents[2])
if _fastapi_dir not in sys.path:
    sys.path.insert(0, _fastapi_dir)

import database  # noqa: E402  # импорт после настройки sys.path
from auth.models import User  # noqa: E402
from database import Base, get_db  # noqa: E402

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")

engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Middleware использует database.SessionLocal напрямую — подменяем на тестовую.
database.SessionLocal = TestingSession


def _override_get_db() -> Iterator[Session]:
    db = TestingSession()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Мок Keycloak
# ---------------------------------------------------------------------------

_fake_kc = MagicMock()
_fake_kc.login.return_value = {
    "access_token": "fake-jwt-token",
    "token_type": "bearer",
    "expires_in": 300,
    "refresh_token": "fake-refresh",
}
_fake_kc.create_user.return_value = "fake-kc-uid"
_fake_kc.update_user.return_value = None
_fake_kc.reset_password.return_value = None
_fake_kc.delete_user.return_value = None
_fake_kc.get_user_id_by_username.return_value = "fake-kc-uid"
_fake_kc.decode_token.return_value = {"preferred_username": "testadmin"}


@pytest.fixture(autouse=True)
def _patch_keycloak() -> Iterator[None]:
    with (
        patch("auth.router.keycloak_service", _fake_kc),
        patch("auth.dependencies.keycloak_service", _fake_kc),
        patch("auth.middleware.keycloak_service", _fake_kc),
    ):
        yield


@pytest.fixture(autouse=True)
def _setup_tables() -> Iterator[None]:
    import auth.models  # noqa: F401
    import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def db() -> Iterator[Session]:
    """Предоставляет сессию тестовой БД.

    Yields:
        Сессия SQLAlchemy.
    """
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client() -> Iterator[TestClient]:
    """Предоставляет TestClient с подменённой зависимостью get_db.

    Yields:
        Клиент для выполнения тестовых HTTP-запросов.
    """
    from main import app

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def seed_admin(db: Session) -> User:
    """Создаёт пользователя с ролью, дающей доступ к users/roles/sys-functions.

    Права выданы явно (а не подразумеваются пустым набором), т.к. AuthMiddleware
    отказывает в доступе, если у пользователя нет ни одной разрешённой функции.

    Args:
        db: Сессия тестовой БД.

    Returns:
        Созданный пользователь с ролью auth_admin.
    """
    from auth.models import Role, Role2Function, SysFunction, User2Role

    user = User(
        username="testadmin",
        password="not-used",
        email="admin@test.com",
        firstname="Test",
        lastname="Admin",
        enabled=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    role = Role(role_name="auth_admin")
    db.add(role)
    db.commit()
    db.refresh(role)
    db.add(User2Role(user_id=user.id, role_id=role.id))

    api_names = [
        "users.create",
        "users.read",
        "users.update",
        "users.delete",
        "roles.create",
        "roles.read",
        "roles.update",
        "roles.delete",
        "sys_functions.read",
    ]
    for api_name in api_names:
        func = SysFunction(api_name=api_name, func_description=api_name)
        db.add(func)
        db.commit()
        db.refresh(func)
        db.add(Role2Function(role_id=role.id, function_id=func.id))
    db.commit()

    return user


@pytest.fixture()
def auth_header(seed_admin: User) -> dict[str, str]:
    """Возвращает заголовок Authorization с поддельным JWT-токеном.

    Args:
        seed_admin: Пользователь-администратор (нужен для инициализации данных).

    Returns:
        Словарь с заголовком Authorization.
    """
    return {"Authorization": "Bearer fake-jwt-token"}
