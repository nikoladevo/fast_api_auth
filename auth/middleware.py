"""Middleware аутентификации, авторизации по функциям и протоколирования.

Перехватывает все запросы, кроме служебных (health/docs/openapi).
Проверяет JWT-токен и права доступа к функции API, затем пишет событие
протокола (аудита) по каждому запросу — п. 3.2.2.1-3.2.2.2 ТЗ: успешные,
так и отклонённые (401/402) запросы.
"""

import logging
import re
import time
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

import database
from videopc_logging import log_authentication

from .dependencies import get_user_function_names
from .keycloak_service import keycloak_service
from .models import User
from .protocol_logger import log_event

logger = logging.getLogger(__name__)

# Полностью без протоколирования — служебные/инфраструктурные пути.
SILENT_PATHS = {
    "/",
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
}

PUBLIC_PREFIXES = (
    "/docs",
    "/redoc",
)

# Пути, требующие токен, но не требующие прав на отдельную функцию API:
# выход из системы доступен любому аутентифицированному пользователю.
NO_FUNCTION_CHECK_PATHS = {
    "/logout",
}

METHOD_TO_OPERATION = {
    "GET": "read",
    "POST": "create",
    "PUT": "update",
    "DELETE": "delete",
}

# Паттерн: /prefix, /prefix/, /prefix/{id}, /prefix/{id}/sub/...
_ROUTE_RE = re.compile(r"^/([a-z][a-z0-9\-]*)(?:/|$)")


def _resolve_api_name(method: str, path: str) -> str | None:
    """Преобразует HTTP-метод + путь в api_name вида 'entity.operation'.

    Args:
        method: HTTP-метод запроса.
        path: Путь запроса.

    Returns:
        Имя функции API или None, если путь не сопоставлен.

    Примеры:
        GET  /data-types/      → data_types.read
        POST /channels/        → channels.create
        PUT  /workers/5        → workers.update
        DELETE /shifts/3       → shifts.delete
        GET  /reports/...      → reports.read
        GET  /users/1/roles/2  → users.read  (auth-роутер)
    """
    m = _ROUTE_RE.match(path)
    if not m:
        return None
    prefix = m.group(1).replace("-", "_")
    operation = METHOD_TO_OPERATION.get(method)
    if not operation:
        return None
    return f"{prefix}.{operation}"


class AuthMiddleware(BaseHTTPMiddleware):
    """Middleware JWT-проверки, авторизации по функциям и протоколирования."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Обрабатывает запрос: проверяет JWT и права, пишет событие протокола.

        Args:
            request: HTTP-запрос.
            call_next: Следующий обработчик в цепочке middleware.

        Returns:
            Ответ запроса.
        """
        path = request.url.path
        method = request.method

        if method == "OPTIONS":
            return await call_next(request)

        if path in SILENT_PATHS or path.startswith(PUBLIC_PREFIXES):
            return await call_next(request)

        start = time.monotonic()
        api_name = (
            None if path in NO_FUNCTION_CHECK_PATHS else _resolve_api_name(method, path)
        )
        user: User | None = None
        username: str | None = None
        error_detail: str | None = None
        response = None
        client_ip = request.client.host if request.client else None

        def deny(status_code: int, detail: str) -> JSONResponse:
            nonlocal error_detail
            error_detail = detail
            # Отказ по токену — это неуспешная попытка аутентификации,
            # она регистрируется всегда, независимо от уровня логирования.
            if status_code == 401:
                log_authentication(username, False, reason=detail, client_ip=client_ip)
            return JSONResponse(status_code=status_code, content={"detail": detail})

        try:
            if path == "/login":
                # /login протоколируется как событие аутентификации,
                # но не требует токена.
                response = await call_next(request)
            else:
                auth_header = request.headers.get("Authorization")
                if not auth_header or not auth_header.startswith("Bearer "):
                    response = deny(401, "Токен невалиден или истек")
                else:
                    token = auth_header.split(" ", 1)[1]
                    try:
                        payload = keycloak_service.decode_token(token)
                        username = payload.get("preferred_username") or payload.get(
                            "sub"
                        )
                    except Exception:
                        username = None

                    if not username:
                        response = deny(401, "Токен невалиден или истек")
                    else:
                        auth_db = database.SessionLocal()
                        try:
                            user = (
                                auth_db.query(User)
                                .filter(User.username == username)
                                .first()
                            )
                            if not user:
                                response = deny(401, "Пользователь не найден")
                            elif not user.enabled:
                                response = deny(401, "Пользователь неактивен")
                            elif api_name and api_name not in get_user_function_names(
                                user, auth_db
                            ):
                                response = deny(
                                    402, "Нет прав на использование функции"
                                )
                        finally:
                            auth_db.close()

                        if response is None:
                            request.state.current_user = user
                            response = await call_next(request)
            return response
        finally:
            duration_ms = int((time.monotonic() - start) * 1000)
            log_db = database.SessionLocal()
            try:
                log_event(
                    log_db,
                    method=method,
                    path=path,
                    api_name=api_name,
                    status_code=response.status_code if response is not None else 500,
                    duration_ms=duration_ms,
                    user_id=user.id if user else None,
                    username=username,
                    client_ip=client_ip,
                    error_detail=error_detail,
                )
            finally:
                log_db.close()
