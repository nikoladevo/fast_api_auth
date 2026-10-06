"""Заполнение справочника sys_functions на основе зарегистрированных роутеров."""

from sqlalchemy.orm import Session

from .models import SysFunction

OPERATIONS = {
    "read": "Чтение",
    "create": "Создание",
    "update": "Обновление",
    "delete": "Удаление",
}

ENTITIES = [
    "data_types",
    "ddns",
    "notifiers",
    "production_areas",
    "workers",
    "channels",
    "clients",
    "processing_tasks",
    "production_tasks",
    "raw_data",
    "regulations",
    "sessions",
    "shifts",
    "ecgs",
    "fact_types",
    "notify_lines",
    "reg2ses",
    "tracker_events",
    "messages",
    "notifications",
    "reglaments",
    "reg2production_tasks",
    "reglament_facts",
    "regstates",
    "regtransitions",
    "reg_trans_facts",
    "reports",
    "take_data",
    "users",
    "roles",
    "sys_functions",
    "protocol_events",
    "protocol_settings",
]


def seed_sys_functions(db: Session) -> int:
    """Создаёт записи sys_functions для всех entity.operation.

    Args:
        db: Сессия БД.

    Returns:
        Число созданных записей.
    """
    existing = {f.api_name for f in db.query(SysFunction.api_name).all()}
    created = 0
    for entity in ENTITIES:
        for op, desc_prefix in OPERATIONS.items():
            api_name = f"{entity}.{op}"
            if api_name in existing:
                continue
            human = entity.replace("_", " ")
            db.add(
                SysFunction(
                    api_name=api_name,
                    func_description=f"{desc_prefix} {human}",
                )
            )
            created += 1
    if created:
        db.commit()
    return created
