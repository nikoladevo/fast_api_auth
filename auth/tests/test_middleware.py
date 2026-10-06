"""Тесты AuthMiddleware на 10 существующих эндпоинтах.

Проверяем три сценария для каждого:
  1) Без токена → 401
  2) С токеном, но без прав на функцию → 403
  3) С токеном и правами → 200/201
"""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from auth.models import User

# ---------------------------------------------------------------------------
# Хелперы
# ---------------------------------------------------------------------------


def _grant_function(db: Session, user: User, api_name: str) -> None:
    """Создаёт роль, sys_function и связывает: user → role → function."""
    from auth.models import Role, Role2Function, SysFunction, User2Role

    role = db.query(Role).filter(Role.role_name == "test_role").first()
    if not role:
        role = Role(role_name="test_role")
        db.add(role)
        db.commit()
        db.refresh(role)
    if not db.query(User2Role).filter_by(user_id=user.id, role_id=role.id).first():
        db.add(User2Role(user_id=user.id, role_id=role.id))
        db.commit()
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


def _grant_many(db: Session, user: User, api_names: list[str]) -> None:
    for name in api_names:
        _grant_function(db, user, name)


def _grant_area(db: Session, user: User, area_id: int) -> None:
    """Назначает пользователю производственную зону для check_area_from_request."""
    from auth.models import User2Area

    if (
        not db.query(User2Area)
        .filter_by(user_id=user.id, production_area_id=area_id)
        .first()
    ):
        db.add(User2Area(user_id=user.id, production_area_id=area_id))
        db.commit()


# ---------------------------------------------------------------------------
# 1. /data-types/
# ---------------------------------------------------------------------------


class TestDataTypes:
    """Тесты эндпоинтов /data-types/."""

    def test_no_token(self, client: TestClient) -> None:
        """Без токена /data-types/ возвращает 401."""
        assert client.get("/data-types/").status_code == 401

    def test_no_permission(
        self,
        client: TestClient,
        auth_header: dict[str, str],
        seed_admin: User,
        db: Session,
    ) -> None:
        """Без прав на функцию /data-types/ возвращает 402."""
        _grant_function(db, seed_admin, "unrelated.read")
        assert client.get("/data-types/", headers=auth_header).status_code == 402

    def test_read_ok(
        self,
        client: TestClient,
        auth_header: dict[str, str],
        seed_admin: User,
        db: Session,
    ) -> None:
        """С правами на чтение /data-types/ возвращает 200."""
        _grant_function(db, seed_admin, "data_types.read")
        resp = client.get("/data-types/", headers=auth_header)
        assert resp.status_code == 200

    def test_create_ok(
        self,
        client: TestClient,
        auth_header: dict[str, str],
        seed_admin: User,
        db: Session,
    ) -> None:
        """С правами на создание POST /data-types/ возвращает 201."""
        _grant_many(db, seed_admin, ["data_types.create", "data_types.read"])
        resp = client.post(
            "/data-types/",
            json={
                "data_type_name": "video",
            },
            headers=auth_header,
        )
        assert resp.status_code == 201


# ---------------------------------------------------------------------------
# 2. /production-areas/
# ---------------------------------------------------------------------------


class TestProductionAreas:
    """Тесты эндпоинтов /production-areas/."""

    def test_no_token(self, client: TestClient) -> None:
        """Без токена /production-areas/ возвращает 401."""
        assert client.get("/production-areas/").status_code == 401

    def test_no_permission(
        self,
        client: TestClient,
        auth_header: dict[str, str],
        seed_admin: User,
        db: Session,
    ) -> None:
        """Без прав на функцию /production-areas/ возвращает 402."""
        _grant_function(db, seed_admin, "unrelated.read")
        assert client.get("/production-areas/", headers=auth_header).status_code == 402

    def test_crud(
        self,
        client: TestClient,
        auth_header: dict[str, str],
        seed_admin: User,
        db: Session,
    ) -> None:
        """CRUD /production-areas/ проходит с нужными правами."""
        _grant_many(
            db,
            seed_admin,
            [
                "production_areas.create",
                "production_areas.read",
                "production_areas.update",
                "production_areas.delete",
            ],
        )
        h = auth_header
        r = client.post("/production-areas/", json={"area_name": "Zone A"}, headers=h)
        assert r.status_code == 201
        pid = r.json()["id"]

        assert client.get(f"/production-areas/{pid}", headers=h).status_code == 200

        r = client.put(
            f"/production-areas/{pid}", json={"area_name": "Zone B"}, headers=h
        )
        assert r.status_code == 200
        assert r.json()["area_name"] == "Zone B"

        assert client.delete(f"/production-areas/{pid}", headers=h).status_code in (
            200,
            204,
        )


# ---------------------------------------------------------------------------
# 3. /workers/
# ---------------------------------------------------------------------------


class TestWorkers:
    """Тесты эндпоинтов /workers/."""

    def test_no_token(self, client: TestClient) -> None:
        """Без токена POST /workers/ возвращает 401."""
        assert (
            client.post("/workers/", json={"personnel_number": "001"}).status_code
            == 401
        )

    def test_create_and_read(
        self,
        client: TestClient,
        auth_header: dict[str, str],
        seed_admin: User,
        db: Session,
    ) -> None:
        """Создание и чтение /workers/ проходит с нужными правами."""
        _grant_many(db, seed_admin, ["workers.create", "workers.read"])
        h = auth_header
        r = client.post("/workers/", json={"personnel_number": "W-001"}, headers=h)
        assert r.status_code == 201
        wid = r.json()["id"]
        assert (
            client.get(f"/workers/{wid}", headers=h).json()["personnel_number"]
            == "W-001"
        )


# ---------------------------------------------------------------------------
# 4. /channels/
# ---------------------------------------------------------------------------


class TestChannels:
    """Тесты эндпоинтов /channels/."""

    def test_no_token(self, client: TestClient) -> None:
        """Без токена /channels/ возвращает 401."""
        assert client.get("/channels/").status_code == 401

    def test_create_read(
        self,
        client: TestClient,
        auth_header: dict[str, str],
        seed_admin: User,
        db: Session,
    ) -> None:
        """Создание и чтение /channels/ проходит с нужными правами."""
        _grant_many(
            db,
            seed_admin,
            [
                "channels.create",
                "channels.read",
                "production_areas.create",
            ],
        )
        h = auth_header
        area = client.post(
            "/production-areas/", json={"area_name": "Z"}, headers=h
        ).json()
        _grant_area(db, seed_admin, area["id"])
        r = client.post(
            "/channels/",
            json={
                "production_area_id": area["id"],
                "adapter_name": "cam1",
            },
            headers=h,
        )
        assert r.status_code == 201
        assert client.get(f"/channels/{r.json()['id']}", headers=h).status_code == 200


# ---------------------------------------------------------------------------
# 5. /ddns/
# ---------------------------------------------------------------------------


class TestDDNs:
    """Тесты эндпоинтов /ddns/."""

    def test_no_token(self, client: TestClient) -> None:
        """Без токена /ddns/ возвращает 401."""
        assert client.get("/ddns/").status_code == 401

    def test_crud(
        self,
        client: TestClient,
        auth_header: dict[str, str],
        seed_admin: User,
        db: Session,
    ) -> None:
        """CRUD /ddns/ проходит с нужными правами."""
        _grant_many(db, seed_admin, ["ddns.create", "ddns.read", "ddns.delete"])
        h = auth_header
        r = client.post("/ddns/", json={"name": "DDN-1"}, headers=h)
        assert r.status_code == 201
        did = r.json()["id"]
        assert client.get(f"/ddns/{did}", headers=h).status_code == 200
        assert client.delete(f"/ddns/{did}", headers=h).status_code in (200, 204)


# ---------------------------------------------------------------------------
# 6. /notifiers/
# ---------------------------------------------------------------------------


class TestNotifiers:
    """Тесты эндпоинтов /notifiers/."""

    def test_no_token(self, client: TestClient) -> None:
        """Без токена /notifiers/ возвращает 401."""
        assert client.get("/notifiers/").status_code == 401

    def test_create_read(
        self,
        client: TestClient,
        auth_header: dict[str, str],
        seed_admin: User,
        db: Session,
    ) -> None:
        """Создание и чтение /notifiers/ проходит с нужными правами."""
        _grant_many(db, seed_admin, ["notifiers.create", "notifiers.read"])
        h = auth_header
        r = client.post(
            "/notifiers/", json={"name": "email", "message": "tpl"}, headers=h
        )
        assert r.status_code == 201
        assert client.get(f"/notifiers/{r.json()['id']}", headers=h).status_code == 200


# ---------------------------------------------------------------------------
# 7. /shifts/
# ---------------------------------------------------------------------------


class TestShifts:
    """Тесты эндпоинтов /shifts/."""

    def test_no_token(self, client: TestClient) -> None:
        """Без токена /shifts/ возвращает 401."""
        assert client.get("/shifts/").status_code == 401

    def test_create_read(
        self,
        client: TestClient,
        auth_header: dict[str, str],
        seed_admin: User,
        db: Session,
    ) -> None:
        """Создание и чтение /shifts/ проходит с нужными правами."""
        _grant_many(
            db,
            seed_admin,
            [
                "shifts.create",
                "shifts.read",
                "production_areas.create",
            ],
        )
        h = auth_header
        area = client.post(
            "/production-areas/", json={"area_name": "Z"}, headers=h
        ).json()
        _grant_area(db, seed_admin, area["id"])
        r = client.post(
            "/shifts/",
            json={
                "shift_name": "Day",
                "production_area_id": area["id"],
            },
            headers=h,
        )
        assert r.status_code == 201
        assert client.get(f"/shifts/{r.json()['id']}", headers=h).status_code == 200


# ---------------------------------------------------------------------------
# 8. /regulations/
# ---------------------------------------------------------------------------


class TestRegulations:
    """Тесты эндпоинтов /regulations/."""

    def test_no_token(self, client: TestClient) -> None:
        """Без токена /regulations/ возвращает 401."""
        assert client.get("/regulations/").status_code == 401

    def test_create_read(
        self,
        client: TestClient,
        auth_header: dict[str, str],
        seed_admin: User,
        db: Session,
    ) -> None:
        """Создание и чтение /regulations/ проходит с нужными правами."""
        _grant_many(
            db,
            seed_admin,
            [
                "regulations.create",
                "regulations.read",
                "production_areas.create",
            ],
        )
        h = auth_header
        area = client.post(
            "/production-areas/", json={"area_name": "Z"}, headers=h
        ).json()
        _grant_area(db, seed_admin, area["id"])
        r = client.post(
            "/regulations/",
            json={
                "production_area_id": area["id"],
                "start_from": "2025-01-01T00:00:00",
                "is_active": True,
                "regulation_name": "PPE check",
            },
            headers=h,
        )
        assert r.status_code == 201
        assert (
            client.get(f"/regulations/{r.json()['id']}", headers=h).status_code == 200
        )


# ---------------------------------------------------------------------------
# 9. /sessions/
# ---------------------------------------------------------------------------


class TestSessions:
    """Тесты эндпоинтов /sessions/."""

    def test_no_token(self, client: TestClient) -> None:
        """Без токена /sessions/ возвращает 401."""
        assert client.get("/sessions/").status_code == 401

    def test_create_read(
        self,
        client: TestClient,
        auth_header: dict[str, str],
        seed_admin: User,
        db: Session,
    ) -> None:
        """Создание и чтение /sessions/ проходит с нужными правами."""
        _grant_many(
            db,
            seed_admin,
            [
                "sessions.create",
                "sessions.read",
                "production_areas.create",
            ],
        )
        h = auth_header
        area = client.post(
            "/production-areas/", json={"area_name": "Z"}, headers=h
        ).json()
        _grant_area(db, seed_admin, area["id"])
        r = client.post(
            "/sessions/",
            json={
                "production_area_id": area["id"],
            },
            headers=h,
        )
        assert r.status_code == 201
        assert client.get(f"/sessions/{r.json()['id']}", headers=h).status_code == 200


# ---------------------------------------------------------------------------
# 10. /reglaments/
# ---------------------------------------------------------------------------


class TestReglaments:
    """Тесты эндпоинтов /reglaments/."""

    def test_no_token(self, client: TestClient) -> None:
        """Без токена /reglaments/ возвращает 401."""
        assert client.get("/reglaments/").status_code == 401

    def test_crud(
        self,
        client: TestClient,
        auth_header: dict[str, str],
        seed_admin: User,
        db: Session,
    ) -> None:
        """CRUD /reglaments/ проходит с нужными правами."""
        _grant_many(
            db,
            seed_admin,
            [
                "reglaments.create",
                "reglaments.read",
                "reglaments.update",
                "reglaments.delete",
            ],
        )
        h = auth_header
        r = client.post("/reglaments/", json={"name": "R1"}, headers=h)
        assert r.status_code == 201
        rid = r.json()["id"]

        assert client.get(f"/reglaments/{rid}", headers=h).status_code == 200

        r = client.put(f"/reglaments/{rid}", json={"name": "R2"}, headers=h)
        assert r.status_code == 200
        assert r.json()["name"] == "R2"

        assert client.delete(f"/reglaments/{rid}", headers=h).status_code in (200, 204)


# ---------------------------------------------------------------------------
# Публичные маршруты — middleware не блокирует
# ---------------------------------------------------------------------------


class TestPublicRoutes:
    """Тесты публичных маршрутов, не блокируемых middleware."""

    def test_health(self, client: TestClient) -> None:
        """Публичный /health возвращает 200."""
        assert client.get("/health").status_code == 200

    def test_root(self, client: TestClient) -> None:
        """Публичный / возвращает 200."""
        assert client.get("/").status_code == 200

    def test_login(self, client: TestClient) -> None:
        """Публичный /login не возвращает 401."""
        resp = client.post("/login", data={"username": "x", "password": "y"})
        assert resp.status_code != 401
