"""Тесты пп. 10-12 ТЗ — производственные зоны пользователя."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from models import ProductionArea


def _create_area(db: Session) -> ProductionArea:
    area = ProductionArea(area_name="Zone 1", area_notes="test")
    db.add(area)
    db.commit()
    db.refresh(area)
    return area


def _create_user(
    client: TestClient, auth_header: dict[str, str], username: str = "areauser"
) -> dict[str, object]:
    return client.post(
        "/users",
        json={
            "username": username,
            "email": f"{username}@t.com",
            "password": "p",
        },
        headers=auth_header,
    ).json()


def test_add_area_to_user(
    client: TestClient, auth_header: dict[str, str], db: Session
) -> None:
    """Назначение зоны пользователю возвращает 201."""
    area = _create_area(db)
    user = _create_user(client, auth_header)

    resp = client.post(f"/users/{user['user_id']}/areas/{area.id}", headers=auth_header)
    assert resp.status_code == 201
    assert resp.json()["production_area_id"] == area.id


def test_add_area_duplicate(
    client: TestClient, auth_header: dict[str, str], db: Session
) -> None:
    """Повторное назначение зоны возвращает 400."""
    area = _create_area(db)
    user = _create_user(client, auth_header, "duparea")

    client.post(f"/users/{user['user_id']}/areas/{area.id}", headers=auth_header)
    resp = client.post(f"/users/{user['user_id']}/areas/{area.id}", headers=auth_header)
    assert resp.status_code == 400
    assert "уже назначена" in resp.json()["detail"]


def test_add_area_not_found(client: TestClient, auth_header: dict[str, str]) -> None:
    """Назначение несуществующей зоны возвращает 400."""
    user = _create_user(client, auth_header, "nozone")
    resp = client.post(f"/users/{user['user_id']}/areas/9999", headers=auth_header)
    assert resp.status_code == 400
    assert "не найдена" in resp.json()["detail"]


def test_get_user_areas(
    client: TestClient, auth_header: dict[str, str], db: Session
) -> None:
    """Список зон пользователя содержит назначенную."""
    area = _create_area(db)
    user = _create_user(client, auth_header, "getareas")
    client.post(f"/users/{user['user_id']}/areas/{area.id}", headers=auth_header)

    resp = client.get(f"/users/{user['user_id']}/areas", headers=auth_header)
    assert resp.status_code == 200
    assert any(a["area_name"] == "Zone 1" for a in resp.json())


def test_get_user_areas_empty(client: TestClient, auth_header: dict[str, str]) -> None:
    """Пустой список зон пользователя возвращает 400."""
    user = _create_user(client, auth_header, "noareas")
    resp = client.get(f"/users/{user['user_id']}/areas", headers=auth_header)
    assert resp.status_code == 400
    assert "не найдены" in resp.json()["detail"]


def test_remove_area_from_user(
    client: TestClient, auth_header: dict[str, str], db: Session
) -> None:
    """Снятие зоны с пользователя возвращает 200."""
    area = _create_area(db)
    user = _create_user(client, auth_header, "rmarea")
    client.post(f"/users/{user['user_id']}/areas/{area.id}", headers=auth_header)

    resp = client.delete(
        f"/users/{user['user_id']}/areas/{area.id}", headers=auth_header
    )
    assert resp.status_code == 200

    check = client.get(f"/users/{user['user_id']}/areas", headers=auth_header)
    assert check.status_code == 400


def test_remove_area_not_assigned(
    client: TestClient, auth_header: dict[str, str]
) -> None:
    """Снятие непривязанной зоны возвращает 400."""
    user = _create_user(client, auth_header, "rmnozone")
    resp = client.delete(f"/users/{user['user_id']}/areas/9999", headers=auth_header)
    assert resp.status_code == 400
    assert "не найдена" in resp.json()["detail"]
