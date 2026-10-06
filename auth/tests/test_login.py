"""Тесты п.1 ТЗ — Login."""

from fastapi.testclient import TestClient


def test_login_success(client: TestClient) -> None:
    """Успешный вход возвращает access-токен."""
    resp = client.post("/login", data={"username": "testadmin", "password": "test123"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["access_token"] == "fake-jwt-token"
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 300
    assert "refresh_token" in body


def test_login_invalid_credentials(client: TestClient, _patch_keycloak: None) -> None:
    """Вход с неверными учётными данными возвращает 401."""
    from auth.tests.conftest import _fake_kc

    _fake_kc.login.side_effect = Exception("401: Invalid user credentials")
    resp = client.post("/login", data={"username": "bad", "password": "bad"})
    assert resp.status_code == 401
    assert "Неверные учётные данные" in resp.json()["detail"]
    _fake_kc.login.side_effect = None
    _fake_kc.login.return_value = {
        "access_token": "fake-jwt-token",
        "token_type": "bearer",
        "expires_in": 300,
        "refresh_token": "fake-refresh",
    }


def test_login_missing_fields(client: TestClient) -> None:
    """Вход с пустыми полями возвращает 422."""
    resp = client.post("/login", data={"username": "", "password": ""})
    assert resp.status_code == 422
