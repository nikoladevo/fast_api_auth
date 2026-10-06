"""Тесты auth/dependencies.py — JWT-проверка, авторизация по функциям и зонам."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from auth.dependencies import (
    get_current_user,
    get_user_area_ids,
    get_user_function_names,
)


def test_get_current_user_invalid_token(db: Session) -> None:
    """Невалидный токен приводит к HTTP 401."""
    mock_kc = MagicMock()
    mock_kc.decode_token.side_effect = Exception("invalid")

    with patch("auth.dependencies.keycloak_service", mock_kc):
        with pytest.raises(HTTPException) as exc:
            get_current_user("bad-token", db)
        assert exc.value.status_code == 401


def test_get_current_user_disabled(db: Session) -> None:
    """Неактивный пользователь приводит к HTTP 401."""
    from auth.models import User

    user = User(username="disabled", password="x", email="d@t.com", enabled=False)
    db.add(user)
    db.commit()

    mock_kc = MagicMock()
    mock_kc.decode_token.return_value = {"preferred_username": "disabled"}

    with patch("auth.dependencies.keycloak_service", mock_kc):
        with pytest.raises(HTTPException) as exc:
            get_current_user("token", db)
        assert exc.value.status_code == 401
        assert "неактивен" in exc.value.detail


def test_get_user_function_names(db: Session) -> None:
    """Возвращает имена функций, привязанных к ролям пользователя."""
    from auth.models import Role, Role2Function, SysFunction, User, User2Role

    user = User(username="fn_user", password="x", email="fn@t.com", enabled=True)
    role = Role(role_name="fn_role")
    func1 = SysFunction(api_name="areas.read", func_description="Read areas")
    func2 = SysFunction(api_name="areas.write", func_description="Write areas")
    db.add_all([user, role, func1, func2])
    db.commit()

    db.add(User2Role(user_id=user.id, role_id=role.id))
    db.add(Role2Function(role_id=role.id, function_id=func1.id))
    db.add(Role2Function(role_id=role.id, function_id=func2.id))
    db.commit()

    names = get_user_function_names(user, db)
    assert names == {"areas.read", "areas.write"}


def test_get_user_function_names_empty(db: Session) -> None:
    """Возвращает пустой набор при отсутствии привязанных функций."""
    from auth.models import User

    user = User(username="no_fn", password="x", email="nf@t.com", enabled=True)
    db.add(user)
    db.commit()

    names = get_user_function_names(user, db)
    assert names == set()


def test_get_user_area_ids(db: Session) -> None:
    """Возвращает id зон, привязанных к пользователю."""
    from auth.models import User, User2Area
    from models import ProductionArea

    user = User(username="area_user", password="x", email="au@t.com", enabled=True)
    area = ProductionArea(area_name="Z1")
    db.add_all([user, area])
    db.commit()

    db.add(User2Area(user_id=user.id, production_area_id=area.id))
    db.commit()

    ids = get_user_area_ids(user, db)
    assert ids == [area.id]


def test_get_user_area_ids_empty(db: Session) -> None:
    """Возвращает пустой список при отсутствии привязанных зон."""
    from auth.models import User

    user = User(username="no_area", password="x", email="na@t.com", enabled=True)
    db.add(user)
    db.commit()

    ids = get_user_area_ids(user, db)
    assert ids == []
