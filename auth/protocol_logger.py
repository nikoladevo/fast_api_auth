"""Запись событий протокола (аудита) и проверка правил протоколирования.

Используется из AuthMiddleware — пишет по одной записи ProtocolEvent на
каждый обработанный запрос (включая отказы 401/402/403), если это не
отключено правилом ProtocolSetting для соответствующей функции.
"""

import logging

from sqlalchemy.orm import Session

from .models import ProtocolEvent, ProtocolSetting

logger = logging.getLogger(__name__)


def should_log(db: Session, api_name: str | None, status_code: int) -> bool:
    """Определяет, нужно ли писать событие протокола по правилам.

    Args:
        db: Сессия БД.
        api_name: Имя функции API (None — правило по умолчанию).
        status_code: Код ответа запроса.

    Returns:
        True, если событие нужно записать, иначе False.
    """
    rule = None
    if api_name:
        rule = (
            db.query(ProtocolSetting)
            .filter(ProtocolSetting.api_name == api_name)
            .first()
        )
    if rule is None:
        rule = (
            db.query(ProtocolSetting).filter(ProtocolSetting.api_name.is_(None)).first()
        )
    if rule is None:
        return True
    if not rule.enabled:
        return False
    return not (rule.log_errors_only and status_code < 400)


def log_event(
    db: Session,
    *,
    method: str,
    path: str,
    api_name: str | None,
    status_code: int,
    duration_ms: int,
    user_id: int | None = None,
    username: str | None = None,
    client_ip: str | None = None,
    error_detail: str | None = None,
) -> None:
    """Пишет событие протокола. Ошибка записи не должна ломать обработку запроса.

    Args:
        db: Сессия БД.
        method: HTTP-метод.
        path: Путь запроса.
        api_name: Имя функции API.
        status_code: Код ответа.
        duration_ms: Длительность обработки, мс.
        user_id: Идентификатор пользователя.
        username: Имя пользователя.
        client_ip: IP-адрес клиента.
        error_detail: Текст ошибки (если запрос отклонён).
    """
    try:
        if not should_log(db, api_name, status_code):
            return
        db.add(
            ProtocolEvent(
                method=method,
                path=path,
                api_name=api_name,
                status_code=status_code,
                duration_ms=duration_ms,
                user_id=user_id,
                username=username,
                client_ip=client_ip,
                error_detail=error_detail,
            )
        )
        db.commit()
    except Exception:
        logger.exception("Не удалось записать событие протокола")
        db.rollback()
