"""Тесты пп. 7-9 (роли пользователя) и пп. 13-16 (CRUD ролей)."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


def test_create_role(client: TestClient, auth_header: dict[str, str]) -> None:
    """Создание роли возвращает 201 и имя."""
    resp = client.post("/roles", json={"role_name": "admin"}, headers=auth_header)
    assert resp.status_code == 201
    assert resp.json()["role_name"] == "admin"


def test_create_role_duplicate(client: TestClient, auth_header: dict[str, str]) -> None:
    """Дублирующая роль возвращает 400."""
    client.post("/roles", json={"role_name": "dup"}, headers=auth_header)
    resp = client.post("/roles", json={"role_name": "dup"}, headers=auth_header)
    assert resp.status_code == 400
    assert "уже существует" in resp.json()["detail"]


def test_list_roles(client: TestClient, auth_header: dict[str, str]) -> None:
    """Список ролей содержит созданные записи."""
    client.post("/roles", json={"role_name": "r1"}, headers=auth_header)
    client.post("/roles", json={"role_name": "r2"}, headers=auth_header)
    resp = client.get("/roles", headers=auth_header)
    assert resp.status_code == 200
    names = [r["role_name"] for r in resp.json()]
    assert "r1" in names
    assert "r2" in names


def test_update_role(client: TestClient, auth_header: dict[str, str]) -> None:
    """Обновление роли применяет новое имя."""
    create = client.post("/roles", json={"role_name": "old"}, headers=auth_header)
    rid = create.json()["id"]
    resp = client.put(f"/roles/{rid}", json={"role_name": "new"}, headers=auth_header)
    assert resp.status_code == 200
    assert resp.json()["role_name"] == "new"


def test_delete_role(client: TestClient, auth_header: dict[str, str]) -> None:
    """Удаление роли возвращает 200."""
    create = client.post("/roles", json={"role_name": "todel"}, headers=auth_header)
    rid = create.json()["id"]
    resp = client.delete(f"/roles/{rid}", headers=auth_header)
    assert resp.status_code == 200


def test_delete_role_not_found(client: TestClient, auth_header: dict[str, str]) -> None:
    """Удаление несуществующей роли возвращает 400."""
    resp = client.delete("/roles/9999", headers=auth_header)
    assert resp.status_code == 400


def test_add_role_to_user(client: TestClient, auth_header: dict[str, str]) -> None:
    """Назначение роли пользователю возвращает 201."""
    role = client.post(
        "/roles", json={"role_name": "testrole"}, headers=auth_header
    ).json()
    user = client.post(
        "/users",
        json={
            "username": "roleuser",
            "email": "ru@t.com",
            "password": "p",
        },
        headers=auth_header,
    ).json()

    resp = client.post(
        f"/users/{user['user_id']}/roles/{role['id']}", headers=auth_header
    )
    assert resp.status_code == 201
    assert resp.json()["user_id"] == user["user_id"]
    assert resp.json()["role_id"] == role["id"]


def test_add_role_duplicate(client: TestClient, auth_header: dict[str, str]) -> None:
    """Повторное назначение роли возвращает 400."""
    role = client.post(
        "/roles", json={"role_name": "duprole"}, headers=auth_header
    ).json()
    user = client.post(
        "/users",
        json={
            "username": "dupru",
            "email": "dru@t.com",
            "password": "p",
        },
        headers=auth_header,
    ).json()

    client.post(f"/users/{user['user_id']}/roles/{role['id']}", headers=auth_header)
    resp = client.post(
        f"/users/{user['user_id']}/roles/{role['id']}", headers=auth_header
    )
    assert resp.status_code == 400
    assert "уже назначена" in resp.json()["detail"]


def test_get_user_roles(client: TestClient, auth_header: dict[str, str]) -> None:
    """Список ролей пользователя содержит назначенную."""
    role = client.post(
        "/roles", json={"role_name": "getrole"}, headers=auth_header
    ).json()
    user = client.post(
        "/users",
        json={
            "username": "gruser",
            "email": "gr@t.com",
            "password": "p",
        },
        headers=auth_header,
    ).json()
    client.post(f"/users/{user['user_id']}/roles/{role['id']}", headers=auth_header)

    resp = client.get(f"/users/{user['user_id']}/roles", headers=auth_header)
    assert resp.status_code == 200
    assert any(r["role_name"] == "getrole" for r in resp.json())


def test_get_user_roles_empty(client: TestClient, auth_header: dict[str, str]) -> None:
    """Пустой список ролей пользователя возвращает 400."""
    user = client.post(
        "/users",
        json={
            "username": "noroles",
            "email": "nr@t.com",
            "password": "p",
        },
        headers=auth_header,
    ).json()
    resp = client.get(f"/users/{user['user_id']}/roles", headers=auth_header)
    assert resp.status_code == 400
    assert "не найдены" in resp.json()["detail"]


def test_remove_role_from_user(client: TestClient, auth_header: dict[str, str]) -> None:
    """Снятие роли с пользователя возвращает 200."""
    role = client.post(
        "/roles", json={"role_name": "rmrole"}, headers=auth_header
    ).json()
    user = client.post(
        "/users",
        json={
            "username": "rmuser",
            "email": "rm@t.com",
            "password": "p",
        },
        headers=auth_header,
    ).json()
    client.post(f"/users/{user['user_id']}/roles/{role['id']}", headers=auth_header)

    resp = client.delete(
        f"/users/{user['user_id']}/roles/{role['id']}", headers=auth_header
    )
    assert resp.status_code == 200

    check = client.get(f"/users/{user['user_id']}/roles", headers=auth_header)
    assert check.status_code == 400


def test_delete_role_with_functions_blocked(
    client: TestClient, auth_header: dict[str, str], db: Session
) -> None:
    """Удаление роли с привязанными функциями блокируется."""
    from auth.models import SysFunction

    role = client.post(
        "/roles", json={"role_name": "funcrole"}, headers=auth_header
    ).json()
    db.add(SysFunction(func_description="test", api_name="test.read"))
    db.commit()
    func = db.query(SysFunction).first()

    client.post(f"/roles/{role['id']}/functions/{func.id}", headers=auth_header)
    resp = client.delete(f"/roles/{role['id']}", headers=auth_header)
    assert resp.status_code == 400
    assert "Удалите связанные записи" in resp.json()["detail"]
