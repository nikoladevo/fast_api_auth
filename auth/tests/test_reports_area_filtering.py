"""Тесты проверки зоны (production_area_id) в reports_router.

До фикса эндпоинты /reports/* принимали production_area_id/channel_id/
tracker_events_id как обычные параметры без сверки с зонами, назначенными
пользователю (auth/dependencies.py:check_area_from_request нигде не
вызывалась). Теперь каждый эндпоинт должен возвращать 403 при обращении
к чужой зоне и не блокировать доступ к своей.
"""

from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from auth.models import Role, Role2Function, SysFunction, User, User2Area, User2Role
from models import Channel, ProcessingTask, ProductionArea, RawData, Shift, TrackerEvent
from models import Session as SessionModel


def _setup_two_zones_with_reports_access(
    db: Session, seed_admin: User
) -> tuple[ProductionArea, ProductionArea]:
    """Создаёт 2 зоны, назначает пользователю только zone1, даёт reports.read.

    Returns:
        Кортеж из созданных зон (zone1, zone2).
    """
    zone1 = ProductionArea(area_name="Rep Zone 1")
    zone2 = ProductionArea(area_name="Rep Zone 2")
    db.add_all([zone1, zone2])
    db.commit()
    db.refresh(zone1)
    db.refresh(zone2)

    db.add(User2Area(user_id=seed_admin.id, production_area_id=zone1.id))

    role = Role(role_name="reports_role")
    db.add(role)
    db.commit()
    db.refresh(role)
    db.add(User2Role(user_id=seed_admin.id, role_id=role.id))

    func = SysFunction(api_name="reports.read", func_description="reports.read")
    db.add(func)
    db.commit()
    db.refresh(func)
    db.add(Role2Function(role_id=role.id, function_id=func.id))
    db.commit()

    return zone1, zone2


# ---------------------------------------------------------------------------
# facts-violations
# ---------------------------------------------------------------------------


def test_facts_violations_foreign_zone_403(
    client: TestClient, auth_header: dict[str, str], seed_admin: User, db: Session
) -> None:
    """Отчёт facts-violations по чужой зоне возвращает 403."""
    _, zone2 = _setup_two_zones_with_reports_access(db, seed_admin)
    resp = client.get(
        "/reports/facts-violations",
        params={
            "production_area_id": zone2.id,
            "start_date": "2024-01-01T00:00:00",
            "end_date": "2024-12-31T23:59:59",
        },
        headers=auth_header,
    )
    assert resp.status_code == 403


def test_facts_violations_own_zone_ok(
    client: TestClient, auth_header: dict[str, str], seed_admin: User, db: Session
) -> None:
    """Отчёт facts-violations по своей зоне возвращает 200."""
    zone1, _ = _setup_two_zones_with_reports_access(db, seed_admin)
    resp = client.get(
        "/reports/facts-violations",
        params={
            "production_area_id": zone1.id,
            "start_date": "2024-01-01T00:00:00",
            "end_date": "2024-12-31T23:59:59",
        },
        headers=auth_header,
    )
    assert resp.status_code == 200


def test_facts_violations_summary_foreign_zone_403(
    client: TestClient, auth_header: dict[str, str], seed_admin: User, db: Session
) -> None:
    """Сводка facts-violations по чужой зоне возвращает 403."""
    _, zone2 = _setup_two_zones_with_reports_access(db, seed_admin)
    resp = client.get(
        "/reports/facts-violations/summary",
        params={
            "production_area_id": zone2.id,
            "start_date": "2024-01-01T00:00:00",
            "end_date": "2024-12-31T23:59:59",
        },
        headers=auth_header,
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# facts-violations-by-shift
# ---------------------------------------------------------------------------


def test_facts_violations_by_shift_foreign_zone_403(
    client: TestClient, auth_header: dict[str, str], seed_admin: User, db: Session
) -> None:
    """Отчёт facts-violations-by-shift по чужой зоне возвращает 403."""
    _, zone2 = _setup_two_zones_with_reports_access(db, seed_admin)
    shift = Shift(production_area_id=zone2.id, shift_name="S")
    db.add(shift)
    db.commit()
    db.refresh(shift)

    resp = client.get(
        "/reports/facts-violations-by-shift",
        params={
            "production_area_id": zone2.id,
            "shift_id": shift.id,
        },
        headers=auth_header,
    )
    assert resp.status_code == 403


def test_facts_violations_by_shift_summary_foreign_zone_403(
    client: TestClient, auth_header: dict[str, str], seed_admin: User, db: Session
) -> None:
    """Сводка facts-violations-by-shift по чужой зоне возвращает 403."""
    _, zone2 = _setup_two_zones_with_reports_access(db, seed_admin)
    shift = Shift(production_area_id=zone2.id, shift_name="S")
    db.add(shift)
    db.commit()
    db.refresh(shift)

    resp = client.get(
        "/reports/facts-violations-by-shift/summary",
        params={
            "production_area_id": zone2.id,
            "shift_id": shift.id,
        },
        headers=auth_header,
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# video-data-file (зона резолвится из tracker_event → session, а не query-параметром)
# ---------------------------------------------------------------------------


def test_video_data_file_foreign_zone_403(
    client: TestClient, auth_header: dict[str, str], seed_admin: User, db: Session
) -> None:
    """Отчёт video-data-file по чужой зоне возвращает 403."""
    _, zone2 = _setup_two_zones_with_reports_access(db, seed_admin)
    sess = SessionModel(production_area_id=zone2.id)
    ch = Channel(production_area_id=zone2.id, adapter_name="cam")
    db.add_all([sess, ch])
    db.commit()
    db.refresh(sess)
    db.refresh(ch)

    pt = ProcessingTask(channel_id=ch.id)
    db.add(pt)
    db.commit()
    db.refresh(pt)

    event_time = datetime(2024, 1, 1, 12, 0, 0)
    raw = RawData(
        processing_task_id=pt.id,
        fname="video.mp4",
        dt_from=event_time - timedelta(minutes=5),
        dt_to=event_time + timedelta(minutes=5),
    )
    te = TrackerEvent(
        session_id=sess.id, start_datetime=event_time, end_datetime=event_time
    )
    db.add_all([raw, te])
    db.commit()
    db.refresh(te)

    resp = client.get(
        "/reports/video-data-file",
        params={
            "tracker_event_id": te.id,
        },
        headers=auth_header,
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# generate_area_report(+html) — скрипт-эндпоинты, зона проверяется до запуска subprocess
# ---------------------------------------------------------------------------


def test_generate_area_report_foreign_zone_403(
    client: TestClient, auth_header: dict[str, str], seed_admin: User, db: Session
) -> None:
    """Генерация отчёта по чужой зоне возвращает 403."""
    _, zone2 = _setup_two_zones_with_reports_access(db, seed_admin)
    resp = client.get(
        "/reports/generate_area_report",
        params={
            "production_area_id": zone2.id,
            "start_date": "2024-01-01",
            "end_date": "2024-01-31",
        },
        headers=auth_header,
    )
    assert resp.status_code == 403


def test_generate_area_report_own_zone_not_403(
    client: TestClient, auth_header: dict[str, str], seed_admin: User, db: Session
) -> None:
    """Своя зона не должна блокироваться проверкой доступа."""
    zone1, _ = _setup_two_zones_with_reports_access(db, seed_admin)
    resp = client.get(
        "/reports/generate_area_report",
        params={
            "production_area_id": zone1.id,
            "start_date": "2024-01-01",
            "end_date": "2024-01-31",
        },
        headers=auth_header,
    )
    assert resp.status_code != 403


def test_generate_area_report_html_foreign_zone_403(
    client: TestClient, auth_header: dict[str, str], seed_admin: User, db: Session
) -> None:
    """HTML-отчёт по чужой зоне возвращает 403."""
    _, zone2 = _setup_two_zones_with_reports_access(db, seed_admin)
    resp = client.get(
        "/reports/generate_area_report_html",
        params={
            "production_area_id": zone2.id,
            "start_date": "2024-01-01",
            "end_date": "2024-01-31",
        },
        headers=auth_header,
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# generate_channel_report(+html) — зона резолвится из channel_id
# ---------------------------------------------------------------------------


def test_generate_channel_report_foreign_zone_403(
    client: TestClient, auth_header: dict[str, str], seed_admin: User, db: Session
) -> None:
    """Отчёт по чужому каналу возвращает 403."""
    _, zone2 = _setup_two_zones_with_reports_access(db, seed_admin)
    ch = Channel(production_area_id=zone2.id, adapter_name="cam")
    db.add(ch)
    db.commit()
    db.refresh(ch)

    resp = client.get(
        "/reports/generate_channel_report",
        params={
            "channel_id": ch.id,
            "start_date": "2024-01-01",
            "end_date": "2024-01-31",
        },
        headers=auth_header,
    )
    assert resp.status_code == 403


def test_generate_channel_report_html_foreign_zone_403(
    client: TestClient, auth_header: dict[str, str], seed_admin: User, db: Session
) -> None:
    """HTML-отчёт по чужому каналу возвращает 403."""
    _, zone2 = _setup_two_zones_with_reports_access(db, seed_admin)
    ch = Channel(production_area_id=zone2.id, adapter_name="cam")
    db.add(ch)
    db.commit()
    db.refresh(ch)

    resp = client.get(
        "/reports/generate_channel_report_html",
        params={
            "channel_id": ch.id,
            "start_date": "2024-01-01",
            "end_date": "2024-01-31",
        },
        headers=auth_header,
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# generate_tracker_event_report(+html) — зона резолвится из tracker_event → session
# ---------------------------------------------------------------------------


def test_generate_tracker_event_report_foreign_zone_403(
    client: TestClient, auth_header: dict[str, str], seed_admin: User, db: Session
) -> None:
    """Отчёт по чужому tracker_event возвращает 403."""
    _, zone2 = _setup_two_zones_with_reports_access(db, seed_admin)
    sess = SessionModel(production_area_id=zone2.id)
    db.add(sess)
    db.commit()
    db.refresh(sess)
    te = TrackerEvent(session_id=sess.id)
    db.add(te)
    db.commit()
    db.refresh(te)

    resp = client.get(
        "/reports/generate_tracker_event_report",
        params={
            "tracker_events_id": te.id,
        },
        headers=auth_header,
    )
    assert resp.status_code == 403


def test_generate_tracker_event_report_html_foreign_zone_403(
    client: TestClient, auth_header: dict[str, str], seed_admin: User, db: Session
) -> None:
    """HTML-отчёт по чужому tracker_event возвращает 403."""
    _, zone2 = _setup_two_zones_with_reports_access(db, seed_admin)
    sess = SessionModel(production_area_id=zone2.id)
    db.add(sess)
    db.commit()
    db.refresh(sess)
    te = TrackerEvent(session_id=sess.id)
    db.add(te)
    db.commit()
    db.refresh(te)

    resp = client.get(
        "/reports/generate_tracker_event_report_html",
        params={
            "tracker_events_id": te.id,
        },
        headers=auth_header,
    )
    assert resp.status_code == 403
