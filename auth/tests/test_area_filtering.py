"""Тесты п.21.3-21.5 ТЗ — фильтрация по зонам и проверка доступа к зонам при записи.

Для каждого area-зависимого роутера проверяем:
  - GET list: возвращает только записи из зон пользователя
  - POST: 403 при создании в чужой зоне, 201 в своей
  - PUT: 403 при обновлении записи из чужой зоны
  - DELETE: 403 при удалении записи из чужой зоны
  - 402 при отсутствии прав на функцию (вместо 403)
"""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from auth.models import Role, Role2Function, SysFunction, User, User2Area, User2Role
from models import Channel, ProcessingTask, ProductionArea

# ---------------------------------------------------------------------------
# Хелперы
# ---------------------------------------------------------------------------


def _full_setup(db: Session, seed_admin: User) -> tuple[ProductionArea, ProductionArea]:
    """Создаёт 2 зоны, назначает пользователю только zone1, даёт все функции.

    Returns:
        Кортеж из созданных зон (zone1, zone2).
    """
    zone1 = ProductionArea(area_name="Zone 1")
    zone2 = ProductionArea(area_name="Zone 2")
    db.add_all([zone1, zone2])
    db.commit()
    db.refresh(zone1)
    db.refresh(zone2)

    db.add(User2Area(user_id=seed_admin.id, production_area_id=zone1.id))
    db.commit()

    role = Role(role_name="full_access")
    db.add(role)
    db.commit()
    db.refresh(role)
    db.add(User2Role(user_id=seed_admin.id, role_id=role.id))
    db.commit()

    funcs = [
        "channels.create",
        "channels.read",
        "channels.update",
        "channels.delete",
        "sessions.create",
        "sessions.read",
        "sessions.update",
        "sessions.delete",
        "shifts.create",
        "shifts.read",
        "shifts.update",
        "shifts.delete",
        "regulations.create",
        "regulations.read",
        "regulations.update",
        "regulations.delete",
        "production_tasks.create",
        "production_tasks.read",
        "production_tasks.update",
        "production_tasks.delete",
        "processing_tasks.create",
        "processing_tasks.read",
        "processing_tasks.update",
        "processing_tasks.delete",
        "tracker_events.create",
        "tracker_events.read",
        "tracker_events.update",
        "tracker_events.delete",
        "raw_data.create",
        "raw_data.read",
        "raw_data.update",
        "raw_data.delete",
        "production_areas.create",
        "production_areas.read",
        "workers.create",
        "workers.read",
    ]
    for api_name in funcs:
        sf = SysFunction(api_name=api_name, func_description=api_name)
        db.add(sf)
    db.commit()
    for sf in db.query(SysFunction).all():
        db.add(Role2Function(role_id=role.id, function_id=sf.id))
    db.commit()

    return zone1, zone2


# ---------------------------------------------------------------------------
# Тест кода ошибки 402 (функция запрещена)
# ---------------------------------------------------------------------------


class TestErrorCode402:
    """Проверка кода 402 при запрете функции."""

    def test_function_denied_returns_402(
        self,
        client: TestClient,
        auth_header: dict[str, str],
        seed_admin: User,
        db: Session,
    ) -> None:
        """Middleware должен возвращать 402, а не 403, когда функция недоступна."""
        role = Role(role_name="limited")
        db.add(role)
        db.commit()
        db.refresh(role)
        db.add(User2Role(user_id=seed_admin.id, role_id=role.id))
        sf = SysFunction(api_name="unrelated.read", func_description="x")
        db.add(sf)
        db.commit()
        db.refresh(sf)
        db.add(Role2Function(role_id=role.id, function_id=sf.id))
        db.commit()

        resp = client.get("/channels/", headers=auth_header)
        assert resp.status_code == 402
        assert "Нет прав на использование функции" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# 1. /channels/ — прямая связь (production_area_id)
# ---------------------------------------------------------------------------


class TestChannelsAreaFiltering:
    """Фильтрация /channels/ по зонам пользователя."""

    def test_list_filtered_by_user_areas(
        self,
        client: TestClient,
        auth_header: dict[str, str],
        seed_admin: User,
        db: Session,
    ) -> None:
        """GET /channels/ возвращает только каналы из зон пользователя."""
        zone1, zone2 = _full_setup(db, seed_admin)
        h = auth_header
        client.post(
            "/channels/",
            json={"production_area_id": zone1.id, "adapter_name": "cam1"},
            headers=h,
        )
        client.post(
            "/channels/",
            json={"production_area_id": zone2.id, "adapter_name": "cam2"},
            headers=h,
        )

        resp = client.get("/channels/", headers=h)
        assert resp.status_code == 200
        names = [c["adapter_name"] for c in resp.json()]
        assert "cam1" in names
        assert "cam2" not in names

    def test_create_in_own_zone_ok(
        self,
        client: TestClient,
        auth_header: dict[str, str],
        seed_admin: User,
        db: Session,
    ) -> None:
        """Создание канала в своей зоне возвращает 201."""
        zone1, _ = _full_setup(db, seed_admin)
        resp = client.post(
            "/channels/",
            json={
                "production_area_id": zone1.id,
                "adapter_name": "ok",
            },
            headers=auth_header,
        )
        assert resp.status_code == 201

    def test_create_in_foreign_zone_403(
        self,
        client: TestClient,
        auth_header: dict[str, str],
        seed_admin: User,
        db: Session,
    ) -> None:
        """Создание канала в чужой зоне возвращает 403."""
        _, zone2 = _full_setup(db, seed_admin)
        resp = client.post(
            "/channels/",
            json={
                "production_area_id": zone2.id,
                "adapter_name": "nope",
            },
            headers=auth_header,
        )
        assert resp.status_code == 403

    def test_update_foreign_zone_403(
        self,
        client: TestClient,
        auth_header: dict[str, str],
        seed_admin: User,
        db: Session,
    ) -> None:
        """Обновление канала из чужой зоны возвращает 403."""
        _, zone2 = _full_setup(db, seed_admin)
        # Создаём канал в zone2 напрямую в БД (обходя middleware)
        ch = Channel(production_area_id=zone2.id, adapter_name="foreign")
        db.add(ch)
        db.commit()
        db.refresh(ch)
        resp = client.put(
            f"/channels/{ch.id}", json={"adapter_name": "hacked"}, headers=auth_header
        )
        assert resp.status_code == 403

    def test_delete_foreign_zone_403(
        self,
        client: TestClient,
        auth_header: dict[str, str],
        seed_admin: User,
        db: Session,
    ) -> None:
        """Удаление канала из чужой зоны возвращает 403."""
        _, zone2 = _full_setup(db, seed_admin)
        ch = Channel(production_area_id=zone2.id, adapter_name="foreign")
        db.add(ch)
        db.commit()
        db.refresh(ch)
        resp = client.delete(f"/channels/{ch.id}", headers=auth_header)
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 2. /sessions/ — прямая связь
# ---------------------------------------------------------------------------


class TestSessionsAreaFiltering:
    """Фильтрация /sessions/ по зонам пользователя."""

    def test_list_filtered(
        self,
        client: TestClient,
        auth_header: dict[str, str],
        seed_admin: User,
        db: Session,
    ) -> None:
        """GET /sessions/ возвращает только сессии из зон пользователя."""
        zone1, zone2 = _full_setup(db, seed_admin)
        h = auth_header
        client.post("/sessions/", json={"production_area_id": zone1.id}, headers=h)
        client.post("/sessions/", json={"production_area_id": zone2.id}, headers=h)

        resp = client.get("/sessions/", headers=h)
        assert resp.status_code == 200
        area_ids = [s["production_area_id"] for s in resp.json()]
        assert zone1.id in area_ids
        assert zone2.id not in area_ids

    def test_create_foreign_zone_403(
        self,
        client: TestClient,
        auth_header: dict[str, str],
        seed_admin: User,
        db: Session,
    ) -> None:
        """Создание сессии в чужой зоне возвращает 403."""
        _, zone2 = _full_setup(db, seed_admin)
        resp = client.post(
            "/sessions/", json={"production_area_id": zone2.id}, headers=auth_header
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 3. /shifts/ — прямая связь
# ---------------------------------------------------------------------------


class TestShiftsAreaFiltering:
    """Фильтрация /shifts/ по зонам пользователя."""

    def test_list_filtered(
        self,
        client: TestClient,
        auth_header: dict[str, str],
        seed_admin: User,
        db: Session,
    ) -> None:
        """GET /shifts/ возвращает только смены из зон пользователя."""
        zone1, zone2 = _full_setup(db, seed_admin)
        h = auth_header
        client.post(
            "/shifts/",
            json={"shift_name": "Day", "production_area_id": zone1.id},
            headers=h,
        )
        client.post(
            "/shifts/",
            json={"shift_name": "Night", "production_area_id": zone2.id},
            headers=h,
        )

        resp = client.get("/shifts/", headers=h)
        assert resp.status_code == 200
        names = [s["shift_name"] for s in resp.json()]
        assert "Day" in names
        assert "Night" not in names

    def test_create_foreign_zone_403(
        self,
        client: TestClient,
        auth_header: dict[str, str],
        seed_admin: User,
        db: Session,
    ) -> None:
        """Создание смены в чужой зоне возвращает 403."""
        _, zone2 = _full_setup(db, seed_admin)
        resp = client.post(
            "/shifts/",
            json={
                "shift_name": "X",
                "production_area_id": zone2.id,
            },
            headers=auth_header,
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 4. /regulations/ — прямая связь
# ---------------------------------------------------------------------------


class TestRegulationsAreaFiltering:
    """Фильтрация /regulations/ по зонам пользователя."""

    def test_list_filtered(
        self,
        client: TestClient,
        auth_header: dict[str, str],
        seed_admin: User,
        db: Session,
    ) -> None:
        """GET /regulations/ возвращает только регламенты из зон пользователя."""
        zone1, zone2 = _full_setup(db, seed_admin)
        h = auth_header
        client.post(
            "/regulations/",
            json={
                "production_area_id": zone1.id,
                "start_from": "2025-01-01T00:00:00",
                "is_active": True,
                "regulation_name": "R1",
            },
            headers=h,
        )
        client.post(
            "/regulations/",
            json={
                "production_area_id": zone2.id,
                "start_from": "2025-01-01T00:00:00",
                "is_active": True,
                "regulation_name": "R2",
            },
            headers=h,
        )

        resp = client.get("/regulations/", headers=h)
        assert resp.status_code == 200
        names = [r["regulation_name"] for r in resp.json()]
        assert "R1" in names
        assert "R2" not in names

    def test_create_foreign_zone_403(
        self,
        client: TestClient,
        auth_header: dict[str, str],
        seed_admin: User,
        db: Session,
    ) -> None:
        """Создание регламента в чужой зоне возвращает 403."""
        _, zone2 = _full_setup(db, seed_admin)
        resp = client.post(
            "/regulations/",
            json={
                "production_area_id": zone2.id,
                "start_from": "2025-01-01T00:00:00",
                "is_active": True,
                "regulation_name": "Bad",
            },
            headers=auth_header,
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 5. /production-tasks/ — прямая связь
# ---------------------------------------------------------------------------


class TestProductionTasksAreaFiltering:
    """Фильтрация /production-tasks/ по зонам пользователя."""

    def test_list_filtered(
        self,
        client: TestClient,
        auth_header: dict[str, str],
        seed_admin: User,
        db: Session,
    ) -> None:
        """GET /production-tasks/ возвращает только задачи из зон пользователя."""
        zone1, zone2 = _full_setup(db, seed_admin)
        h = auth_header
        w = client.post("/workers/", json={"personnel_number": "W1"}, headers=h).json()
        client.post(
            "/production-tasks/",
            json={
                "production_area_id": zone1.id,
                "worker_id": w["id"],
                "task_name": "T1",
            },
            headers=h,
        )
        client.post(
            "/production-tasks/",
            json={
                "production_area_id": zone2.id,
                "worker_id": w["id"],
                "task_name": "T2",
            },
            headers=h,
        )

        resp = client.get("/production-tasks/", headers=h)
        assert resp.status_code == 200
        names = [t["task_name"] for t in resp.json()]
        assert "T1" in names
        assert "T2" not in names

    def test_create_foreign_zone_403(
        self,
        client: TestClient,
        auth_header: dict[str, str],
        seed_admin: User,
        db: Session,
    ) -> None:
        """Создание задачи в чужой зоне возвращает 403."""
        _, zone2 = _full_setup(db, seed_admin)
        resp = client.post(
            "/production-tasks/",
            json={
                "production_area_id": zone2.id,
                "task_name": "Bad",
            },
            headers=auth_header,
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 6. /processing-tasks/ — транзитивная (через channel)
# ---------------------------------------------------------------------------


class TestProcessingTasksAreaFiltering:
    """Фильтрация /processing-tasks/ по зонам через channel."""

    def test_list_filtered(
        self,
        client: TestClient,
        auth_header: dict[str, str],
        seed_admin: User,
        db: Session,
    ) -> None:
        """GET /processing-tasks/ возвращает только задачи из зон пользователя."""
        zone1, zone2 = _full_setup(db, seed_admin)
        h = auth_header
        ch1 = Channel(production_area_id=zone1.id, adapter_name="ch1")
        ch2 = Channel(production_area_id=zone2.id, adapter_name="ch2")
        db.add_all([ch1, ch2])
        db.commit()
        db.refresh(ch1)
        db.refresh(ch2)

        client.post("/processing-tasks/", json={"channel_id": ch1.id}, headers=h)
        client.post("/processing-tasks/", json={"channel_id": ch2.id}, headers=h)

        resp = client.get("/processing-tasks/", headers=h)
        assert resp.status_code == 200
        channel_ids = [t["channel_id"] for t in resp.json()]
        assert ch1.id in channel_ids
        assert ch2.id not in channel_ids

    def test_create_foreign_channel_403(
        self,
        client: TestClient,
        auth_header: dict[str, str],
        seed_admin: User,
        db: Session,
    ) -> None:
        """Создание задачи с каналом из чужой зоны возвращает 403."""
        _, zone2 = _full_setup(db, seed_admin)
        ch = Channel(production_area_id=zone2.id, adapter_name="foreign")
        db.add(ch)
        db.commit()
        db.refresh(ch)
        resp = client.post(
            "/processing-tasks/", json={"channel_id": ch.id}, headers=auth_header
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 7. /tracker-events/ — транзитивная (через session)
# ---------------------------------------------------------------------------


class TestTrackerEventsAreaFiltering:
    """Фильтрация /tracker-events/ по зонам через session."""

    def test_list_filtered(
        self,
        client: TestClient,
        auth_header: dict[str, str],
        seed_admin: User,
        db: Session,
    ) -> None:
        """GET /tracker-events/ возвращает только события из зон пользователя."""
        from models import Session as SessionModel

        zone1, zone2 = _full_setup(db, seed_admin)
        s1 = SessionModel(production_area_id=zone1.id)
        s2 = SessionModel(production_area_id=zone2.id)
        db.add_all([s1, s2])
        db.commit()
        db.refresh(s1)
        db.refresh(s2)

        h = auth_header
        client.post("/tracker-events/", json={"session_id": s1.id}, headers=h)
        client.post("/tracker-events/", json={"session_id": s2.id}, headers=h)

        resp = client.get("/tracker-events/", headers=h)
        assert resp.status_code == 200
        session_ids = [e["session_id"] for e in resp.json()]
        assert s1.id in session_ids
        assert s2.id not in session_ids

    def test_create_foreign_session_403(
        self,
        client: TestClient,
        auth_header: dict[str, str],
        seed_admin: User,
        db: Session,
    ) -> None:
        """Создание события с сессией из чужой зоны возвращает 403."""
        from models import Session as SessionModel

        _, zone2 = _full_setup(db, seed_admin)
        s = SessionModel(production_area_id=zone2.id)
        db.add(s)
        db.commit()
        db.refresh(s)
        resp = client.post(
            "/tracker-events/", json={"session_id": s.id}, headers=auth_header
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 8. /raw-data/ — транзитивная (через processing_task → channel)
# ---------------------------------------------------------------------------


class TestRawDataAreaFiltering:
    """Фильтрация /raw-data/ по зонам через processing_task."""

    def test_list_filtered(
        self,
        client: TestClient,
        auth_header: dict[str, str],
        seed_admin: User,
        db: Session,
    ) -> None:
        """GET /raw-data/ возвращает только файлы из зон пользователя."""
        zone1, zone2 = _full_setup(db, seed_admin)
        ch1 = Channel(production_area_id=zone1.id, adapter_name="ch1")
        ch2 = Channel(production_area_id=zone2.id, adapter_name="ch2")
        db.add_all([ch1, ch2])
        db.commit()
        db.refresh(ch1)
        db.refresh(ch2)
        pt1 = ProcessingTask(channel_id=ch1.id)
        pt2 = ProcessingTask(channel_id=ch2.id)
        db.add_all([pt1, pt2])
        db.commit()
        db.refresh(pt1)
        db.refresh(pt2)

        h = auth_header
        client.post(
            "/raw-data/",
            json={"processing_task_id": pt1.id, "fname": "f1.mp4"},
            headers=h,
        )
        client.post(
            "/raw-data/",
            json={"processing_task_id": pt2.id, "fname": "f2.mp4"},
            headers=h,
        )

        resp = client.get("/raw-data/", headers=h)
        assert resp.status_code == 200
        fnames = [r["fname"] for r in resp.json()]
        assert "f1.mp4" in fnames
        assert "f2.mp4" not in fnames

    def test_create_foreign_chain_403(
        self,
        client: TestClient,
        auth_header: dict[str, str],
        seed_admin: User,
        db: Session,
    ) -> None:
        """Создание raw-data в чужой зоне возвращает 403."""
        _, zone2 = _full_setup(db, seed_admin)
        ch = Channel(production_area_id=zone2.id, adapter_name="foreign")
        db.add(ch)
        db.commit()
        db.refresh(ch)
        pt = ProcessingTask(channel_id=ch.id)
        db.add(pt)
        db.commit()
        db.refresh(pt)
        resp = client.post(
            "/raw-data/",
            json={
                "processing_task_id": pt.id,
                "fname": "bad.mp4",
            },
            headers=auth_header,
        )
        assert resp.status_code == 403
