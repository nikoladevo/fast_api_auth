"""Тесты пп. 17-20 ТЗ — системные функции и привязка к ролям."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from auth.models import SysFunction


def _seed_function(
    db: Session, api_name: str = "test.read", desc: str = "Test read"
) -> SysFunction:
    f = SysFunction(func_description=desc, api_name=api_name)
    db.add(f)
    db.commit()
    db.refresh(f)
    return f


def test_list_sys_functions(
    client: TestClient, auth_header: dict[str, str], db: Session
) -> None:
    """Список системных функций содержит созданные записи."""
    _seed_function(db, "a.read", "Read A")
    _seed_function(db, "b.write", "Write B")
    resp = client.get("/sys-functions", headers=auth_header)
    assert resp.status_code == 200
    names = [f["api_name"] for f in resp.json()]
    assert "a.read" in names
    assert "b.write" in names


def test_list_sys_functions_only_bootstrap(
    client: TestClient, auth_header: dict[str, str]
) -> None:
    """Без явно созданных функций видны только служебные функции admin-фикстуры.

    (deny-by-default требует, чтобы функция "sys_functions.read" существовала как
    запись в справочнике, иначе admin-фикстура не смогла бы вызвать сам этот эндпоинт).
    """
    resp = client.get("/sys-functions", headers=auth_header)
    assert resp.status_code == 200
    names = {f["api_name"] for f in resp.json()}
    assert "a.read" not in names
    assert "b.write" not in names


def test_add_function_to_role(
    client: TestClient, auth_header: dict[str, str], db: Session
) -> None:
    """Привязка функции к роли возвращает 201."""
    role = client.post("/roles", json={"role_name": "fr"}, headers=auth_header).json()
    func = _seed_function(db)

    resp = client.post(f"/roles/{role['id']}/functions/{func.id}", headers=auth_header)
    assert resp.status_code == 201
    assert resp.json()["role_id"] == role["id"]
    assert resp.json()["function_id"] == func.id


def test_add_function_duplicate(
    client: TestClient, auth_header: dict[str, str], db: Session
) -> None:
    """Повторная привязка функции к роли возвращает 400."""
    role = client.post("/roles", json={"role_name": "fdup"}, headers=auth_header).json()
    func = _seed_function(db, "dup.fn")

    client.post(f"/roles/{role['id']}/functions/{func.id}", headers=auth_header)
    resp = client.post(f"/roles/{role['id']}/functions/{func.id}", headers=auth_header)
    assert resp.status_code == 400
    assert "уже назначена" in resp.json()["detail"]


def test_add_function_role_not_found(
    client: TestClient, auth_header: dict[str, str], db: Session
) -> None:
    """Привязка к несуществующей роли возвращает 400."""
    func = _seed_function(db, "nf.fn")
    resp = client.post(f"/roles/9999/functions/{func.id}", headers=auth_header)
    assert resp.status_code == 400
    assert "Роль не найдена" in resp.json()["detail"]


def test_add_function_func_not_found(
    client: TestClient, auth_header: dict[str, str]
) -> None:
    """Привязка несуществующей функции возвращает 400."""
    role = client.post("/roles", json={"role_name": "fnf"}, headers=auth_header).json()
    resp = client.post(f"/roles/{role['id']}/functions/9999", headers=auth_header)
    assert resp.status_code == 400
    assert "Функция не найдена" in resp.json()["detail"]


def test_get_role_functions(
    client: TestClient, auth_header: dict[str, str], db: Session
) -> None:
    """Список функций роли содержит привязанную запись."""
    role = client.post("/roles", json={"role_name": "grf"}, headers=auth_header).json()
    func = _seed_function(db, "grf.read")
    client.post(f"/roles/{role['id']}/functions/{func.id}", headers=auth_header)

    resp = client.get(f"/roles/{role['id']}/functions", headers=auth_header)
    assert resp.status_code == 200
    assert any(f["api_name"] == "grf.read" for f in resp.json())


def test_get_role_functions_empty(
    client: TestClient, auth_header: dict[str, str]
) -> None:
    """Пустой список функций роли возвращает 400."""
    role = client.post(
        "/roles", json={"role_name": "nofuncs"}, headers=auth_header
    ).json()
    resp = client.get(f"/roles/{role['id']}/functions", headers=auth_header)
    assert resp.status_code == 400
    assert "не найдены" in resp.json()["detail"]


def test_remove_function_from_role(
    client: TestClient, auth_header: dict[str, str], db: Session
) -> None:
    """Удаление функции из роли возвращает 200."""
    role = client.post("/roles", json={"role_name": "rmf"}, headers=auth_header).json()
    func = _seed_function(db, "rmf.read")
    client.post(f"/roles/{role['id']}/functions/{func.id}", headers=auth_header)

    resp = client.delete(
        f"/roles/{role['id']}/functions/{func.id}", headers=auth_header
    )
    assert resp.status_code == 200

    check = client.get(f"/roles/{role['id']}/functions", headers=auth_header)
    assert check.status_code == 400


def test_remove_function_not_assigned(
    client: TestClient, auth_header: dict[str, str]
) -> None:
    """Удаление непривязанной функции возвращает 400."""
    role = client.post(
        "/roles", json={"role_name": "rmfna"}, headers=auth_header
    ).json()
    resp = client.delete(f"/roles/{role['id']}/functions/9999", headers=auth_header)
    assert resp.status_code == 400
    assert "не найдена" in resp.json()["detail"]
