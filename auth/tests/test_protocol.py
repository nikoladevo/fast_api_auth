"""Тесты протоколирования (аудита) — п. 3.2.2.1-3.2.2.2 ТЗ.

Проверяем: события пишутся на успешные и на отклонённые (401/402) запросы,
/protocol-events отдаёт и фильтрует записи, а правила /protocol-settings
позволяют выключать протоколирование для конкретной функции или ограничивать
его только ошибками.
"""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from auth.models import (
    ProtocolEvent,
    Role,
    Role2Function,
    SysFunction,
    User,
    User2Role,
)


def _grant(db: Session, user: User, api_names: list[str]) -> None:
    role = db.query(Role).filter(Role.role_name == "protocol_role").first()
    if not role:
        role = Role(role_name="protocol_role")
        db.add(role)
        db.commit()
        db.refresh(role)
    if not db.query(User2Role).filter_by(user_id=user.id, role_id=role.id).first():
        db.add(User2Role(user_id=user.id, role_id=role.id))
        db.commit()
    for api_name in api_names:
        func = db.query(SysFunction).filter(SysFunction.api_name == api_name).first()
        if not func:
            func = SysFunction(api_name=api_name, func_description=api_name)
            db.add(func)
            db.commit()
            db.refresh(func)
        if (
            not db.query(Role2Function)
            .filter_by(role_id=role.id, function_id=func.id)
            .first()
        ):
            db.add(Role2Function(role_id=role.id, function_id=func.id))
    db.commit()


# ---------------------------------------------------------------------------
# Запись событий middleware
# ---------------------------------------------------------------------------


def test_successful_request_is_logged(
    client: TestClient,
    auth_header: dict[str, str],
    seed_admin: User,
    db: Session,
) -> None:
    """Успешный запрос пишется в журнал протокола."""
    _grant(db, seed_admin, ["data_types.read", "protocol_events.read"])
    resp = client.get("/data-types/", headers=auth_header)
    assert resp.status_code == 200

    events = (
        db.query(ProtocolEvent)
        .filter(ProtocolEvent.api_name == "data_types.read")
        .all()
    )
    assert len(events) == 1
    assert events[0].status_code == 200
    assert events[0].username == "testadmin"
    assert events[0].method == "GET"


def test_no_token_request_is_logged_401(client: TestClient, db: Session) -> None:
    """Запрос без токена логируется с кодом 401."""
    resp = client.get("/data-types/")
    assert resp.status_code == 401

    events = db.query(ProtocolEvent).filter(ProtocolEvent.status_code == 401).all()
    assert len(events) == 1
    assert events[0].user_id is None
    assert "Токен невалиден" in events[0].error_detail


def test_no_permission_request_is_logged_402(
    client: TestClient,
    auth_header: dict[str, str],
    seed_admin: User,
    db: Session,
) -> None:
    """Запрос без прав логируется с кодом 402."""
    _grant(db, seed_admin, ["unrelated.read"])
    resp = client.get("/data-types/", headers=auth_header)
    assert resp.status_code == 402

    events = db.query(ProtocolEvent).filter(ProtocolEvent.status_code == 402).all()
    assert len(events) == 1
    assert events[0].username == "testadmin"
    assert events[0].api_name == "data_types.read"


def test_login_is_logged(client: TestClient, db: Session) -> None:
    """Вход пользователя пишется в журнал протокола."""
    resp = client.post("/login", data={"username": "testadmin", "password": "x"})
    assert resp.status_code == 200

    events = db.query(ProtocolEvent).filter(ProtocolEvent.path == "/login").all()
    assert len(events) == 1
    assert events[0].status_code == 200


def test_health_is_not_logged(client: TestClient, db: Session) -> None:
    """Проверка /health не пишется в журнал протокола."""
    assert client.get("/health").status_code == 200
    assert db.query(ProtocolEvent).count() == 0


# ---------------------------------------------------------------------------
# GET /protocol-events
# ---------------------------------------------------------------------------


def test_list_protocol_events(
    client: TestClient,
    auth_header: dict[str, str],
    seed_admin: User,
    db: Session,
) -> None:
    """Список событий протокола содержит записи о запросах."""
    _grant(db, seed_admin, ["data_types.read", "protocol_events.read"])
    client.get("/data-types/", headers=auth_header)
    client.get("/data-types/", headers=auth_header)

    resp = client.get("/protocol-events", headers=auth_header)
    assert resp.status_code == 200
    # свои же 2 запроса к /data-types/ + сам этот вызов ещё не в логе
    # (событие пишется после ответа)
    api_names = [e["api_name"] for e in resp.json()]
    assert api_names.count("data_types.read") == 2


def test_list_protocol_events_filter_by_status(
    client: TestClient,
    auth_header: dict[str, str],
    seed_admin: User,
    db: Session,
) -> None:
    """События фильтруются по коду статуса."""
    _grant(db, seed_admin, ["data_types.read", "protocol_events.read"])
    client.get("/data-types/", headers=auth_header)
    client.get(
        "/nonexistent-entity/", headers=auth_header
    )  # 402 (нет прав/не резолвится) либо 404

    resp = client.get("/protocol-events?status_code=200", headers=auth_header)
    assert resp.status_code == 200
    assert all(e["status_code"] == 200 for e in resp.json())


# ---------------------------------------------------------------------------
# /protocol-settings
# ---------------------------------------------------------------------------


def test_disabling_rule_stops_logging_for_function(
    client: TestClient,
    auth_header: dict[str, str],
    seed_admin: User,
    db: Session,
) -> None:
    """Отключение правила останавливает логирование функции."""
    _grant(db, seed_admin, ["data_types.read", "protocol_settings.create"])
    resp = client.post(
        "/protocol-settings",
        json={
            "api_name": "data_types.read",
            "enabled": False,
        },
        headers=auth_header,
    )
    assert resp.status_code == 201

    client.get("/data-types/", headers=auth_header)

    events = (
        db.query(ProtocolEvent)
        .filter(ProtocolEvent.api_name == "data_types.read")
        .all()
    )
    assert events == []


def test_log_errors_only_rule(
    client: TestClient,
    auth_header: dict[str, str],
    seed_admin: User,
    db: Session,
) -> None:
    """Правило логирования только ошибок отсекает успешные запросы."""
    _grant(db, seed_admin, ["data_types.read", "protocol_settings.create"])
    resp = client.post(
        "/protocol-settings",
        json={
            "api_name": "data_types.read",
            "enabled": True,
            "log_errors_only": True,
        },
        headers=auth_header,
    )
    assert resp.status_code == 201

    client.get("/data-types/", headers=auth_header)  # 200 — не должно залогироваться

    events = (
        db.query(ProtocolEvent)
        .filter(ProtocolEvent.api_name == "data_types.read")
        .all()
    )
    assert events == []


def test_create_protocol_setting_duplicate(
    client: TestClient,
    auth_header: dict[str, str],
    seed_admin: User,
    db: Session,
) -> None:
    """Дублирующее правило протокола возвращает 400."""
    _grant(db, seed_admin, ["protocol_settings.create"])
    client.post("/protocol-settings", json={"api_name": "x.read"}, headers=auth_header)
    resp = client.post(
        "/protocol-settings", json={"api_name": "x.read"}, headers=auth_header
    )
    assert resp.status_code == 400


def test_update_protocol_setting_not_found(
    client: TestClient,
    auth_header: dict[str, str],
    seed_admin: User,
    db: Session,
) -> None:
    """Обновление несуществующего правила возвращает 400."""
    _grant(db, seed_admin, ["protocol_settings.update"])
    resp = client.put(
        "/protocol-settings/9999", json={"enabled": False}, headers=auth_header
    )
    assert resp.status_code == 400


def test_delete_protocol_setting_not_found(
    client: TestClient,
    auth_header: dict[str, str],
    seed_admin: User,
    db: Session,
) -> None:
    """Удаление несуществующего правила возвращает 400."""
    _grant(db, seed_admin, ["protocol_settings.delete"])
    resp = client.delete("/protocol-settings/9999", headers=auth_header)
    assert resp.status_code == 400
