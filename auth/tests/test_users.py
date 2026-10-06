"""Тесты пп. 2-6 ТЗ — CRUD пользователей."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


def test_create_user(client: TestClient, auth_header: dict[str, str]) -> None:
    """Создание пользователя возвращает 201 и данные."""
    resp = client.post(
        "/users",
        json={
            "username": "newuser",
            "email": "new@test.com",
            "password": "pass123",
            "firstname": "Ivan",
            "lastname": "Petrov",
            "enabled": True,
        },
        headers=auth_header,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["username"] == "newuser"
    assert body["message"] == "Пользователь создан"


def test_create_user_with_role(
    client: TestClient, auth_header: dict[str, str], db: Session
) -> None:
    """Создание пользователя с ролью возвращает эту роль."""
    from auth.models import Role

    db.add(Role(role_name="operator"))
    db.commit()

    resp = client.post(
        "/users",
        json={
            "username": "withRole",
            "email": "wr@test.com",
            "password": "pass",
            "role": "operator",
        },
        headers=auth_header,
    )
    assert resp.status_code == 201
    assert resp.json()["role"] == "operator"


def test_create_user_with_nonexistent_role_400(
    client: TestClient, auth_header: dict[str, str], db: Session
) -> None:
    """Раньше несуществующая роль молча игнорировалась.

    Пользователь создавался без роли.
    """
    resp = client.post(
        "/users",
        json={
            "username": "badrole",
            "email": "badrole@test.com",
            "password": "pass",
            "role": "no-such-role",
        },
        headers=auth_header,
    )
    assert resp.status_code == 400
    assert "Роль не найдена" in resp.json()["detail"]

    from auth.models import User

    assert db.query(User).filter(User.username == "badrole").first() is None


def test_create_user_duplicate(client: TestClient, auth_header: dict[str, str]) -> None:
    """Дублирующее имя пользователя возвращает 400."""
    client.post(
        "/users",
        json={
            "username": "dup",
            "email": "dup@test.com",
            "password": "pass",
        },
        headers=auth_header,
    )
    resp = client.post(
        "/users",
        json={
            "username": "dup",
            "email": "dup2@test.com",
            "password": "pass",
        },
        headers=auth_header,
    )
    assert resp.status_code == 400
    assert "уже существует" in resp.json()["detail"]


def test_list_users(client: TestClient, auth_header: dict[str, str]) -> None:
    """Список пользователей содержит созданных."""
    client.post(
        "/users",
        json={
            "username": "user1",
            "email": "u1@t.com",
            "password": "p",
        },
        headers=auth_header,
    )
    client.post(
        "/users",
        json={
            "username": "user2",
            "email": "u2@t.com",
            "password": "p",
        },
        headers=auth_header,
    )
    resp = client.get("/users", headers=auth_header)
    assert resp.status_code == 200
    names = [u["username"] for u in resp.json()]
    assert "testadmin" in names
    assert "user1" in names
    assert "user2" in names


def test_list_users_filter_by_username(
    client: TestClient, auth_header: dict[str, str]
) -> None:
    """Фильтр по имени пользователя возвращает одного."""
    client.post(
        "/users",
        json={
            "username": "findme",
            "email": "fm@t.com",
            "password": "p",
        },
        headers=auth_header,
    )
    resp = client.get("/users?username=findme", headers=auth_header)
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["username"] == "findme"


def test_list_users_filter_by_enabled(
    client: TestClient, auth_header: dict[str, str]
) -> None:
    """Фильтр по enabled=false возвращает только отключённых."""
    client.post(
        "/users",
        json={
            "username": "disabled1",
            "email": "d@t.com",
            "password": "p",
            "enabled": False,
        },
        headers=auth_header,
    )
    resp = client.get("/users?enabled=false", headers=auth_header)
    assert resp.status_code == 200
    assert all(not u["enabled"] for u in resp.json())


def test_get_user(client: TestClient, auth_header: dict[str, str]) -> None:
    """Получение пользователя по id возвращает данные."""
    create = client.post(
        "/users",
        json={
            "username": "getme",
            "email": "gm@t.com",
            "password": "p",
        },
        headers=auth_header,
    )
    uid = create.json()["user_id"]
    resp = client.get(f"/users/{uid}", headers=auth_header)
    assert resp.status_code == 200
    assert resp.json()["username"] == "getme"


def test_get_user_not_found(client: TestClient, auth_header: dict[str, str]) -> None:
    """Получение несуществующего пользователя возвращает 400."""
    resp = client.get("/users/9999", headers=auth_header)
    assert resp.status_code == 400


def test_update_user(client: TestClient, auth_header: dict[str, str]) -> None:
    """Обновление пользователя применяет изменения."""
    create = client.post(
        "/users",
        json={
            "username": "upd",
            "email": "upd@t.com",
            "password": "p",
        },
        headers=auth_header,
    )
    uid = create.json()["user_id"]
    resp = client.put(
        f"/users/{uid}",
        json={
            "firstname": "Updated",
            "lastname": "Name",
        },
        headers=auth_header,
    )
    assert resp.status_code == 200
    assert resp.json()["message"] == "Пользователь обновлён"

    check = client.get(f"/users/{uid}", headers=auth_header)
    assert check.json()["firstname"] == "Updated"
    assert check.json()["lastname"] == "Name"


def test_delete_user(client: TestClient, auth_header: dict[str, str]) -> None:
    """Удаление пользователя делает его недоступным."""
    create = client.post(
        "/users",
        json={
            "username": "delme",
            "email": "del@t.com",
            "password": "p",
        },
        headers=auth_header,
    )
    uid = create.json()["user_id"]
    resp = client.delete(f"/users/{uid}", headers=auth_header)
    assert resp.status_code == 200
    assert client.get(f"/users/{uid}", headers=auth_header).status_code == 400


def test_delete_user_with_roles_blocked(
    client: TestClient, auth_header: dict[str, str], db: Session
) -> None:
    """Удаление пользователя с ролями блокируется."""
    from auth.models import Role

    db.add(Role(role_name="block_role"))
    db.commit()

    create = client.post(
        "/users",
        json={
            "username": "blocked",
            "email": "bl@t.com",
            "password": "p",
            "role": "block_role",
        },
        headers=auth_header,
    )
    uid = create.json()["user_id"]
    resp = client.delete(f"/users/{uid}", headers=auth_header)
    assert resp.status_code == 400
    assert "Удалите связанные записи" in resp.json()["detail"]


def test_change_password(client: TestClient, auth_header: dict[str, str]) -> None:
    """Смена пароля пользователя возвращает успех."""
    create = client.post(
        "/users",
        json={
            "username": "pwduser",
            "email": "pwd@t.com",
            "password": "old",
        },
        headers=auth_header,
    )
    uid = create.json()["user_id"]
    resp = client.put(
        f"/users/{uid}/password", json={"password": "new123"}, headers=auth_header
    )
    assert resp.status_code == 200
    assert resp.json()["message"] == "Пароль изменён"


def test_unauthorized_access(client: TestClient) -> None:
    """Запрос без токена возвращает 401."""
    resp = client.get("/users")
    assert resp.status_code == 401
