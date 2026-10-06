"""Сервис интеграции с Keycloak для аутентификации пользователей."""

import logging
import os

import jwt
from keycloak import KeycloakAdmin, KeycloakOpenID

logger = logging.getLogger(__name__)

KEYCLOAK_URL = os.getenv("KEYCLOAK_URL")
KEYCLOAK_REALM = os.getenv("KEYCLOAK_REALM")
KEYCLOAK_CLIENT_ID = os.getenv("KEYCLOAK_CLIENT_ID")
KEYCLOAK_CLIENT_SECRET = os.getenv("KEYCLOAK_CLIENT_SECRET")
KEYCLOAK_ADMIN_USERNAME = os.getenv("KEYCLOAK_ADMIN_USERNAME")
KEYCLOAK_ADMIN_PASSWORD = os.getenv("KEYCLOAK_ADMIN_PASSWORD")


def _get_admin() -> KeycloakAdmin:
    """Возвращает клиент администратора Keycloak для realm videopc.

    Returns:
        Сконфигурированный клиент KeycloakAdmin.
    """
    return KeycloakAdmin(
        server_url=KEYCLOAK_URL,
        username=KEYCLOAK_ADMIN_USERNAME,
        password=KEYCLOAK_ADMIN_PASSWORD,
        realm_name=KEYCLOAK_REALM,
        user_realm_name="master",
        verify=False,
    )


def _get_openid() -> KeycloakOpenID:
    """Возвращает OpenID-клиент Keycloak для входа пользователей.

    Returns:
        Сконфигурированный клиент KeycloakOpenID.
    """
    return KeycloakOpenID(
        server_url=KEYCLOAK_URL,
        realm_name=KEYCLOAK_REALM,
        client_id=KEYCLOAK_CLIENT_ID,
        client_secret_key=KEYCLOAK_CLIENT_SECRET or None,
    )


class KeycloakService:
    """Обёртка над python-keycloak для операций аутентификации."""

    def login(self, username: str, password: str) -> dict:
        """Аутентифицирует пользователя в Keycloak.

        Args:
            username: Имя учётной записи.
            password: Пароль.

        Returns:
            Словарь с access_token, token_type, expires_in и refresh_token.
        """
        openid = _get_openid()
        token = openid.token(username, password)
        return {
            "access_token": token["access_token"],
            "token_type": token.get("token_type", "bearer"),
            "expires_in": token.get("expires_in", 300),
            "refresh_token": token.get("refresh_token"),
        }

    def logout(self, refresh_token: str) -> None:
        """Завершает сессию пользователя в Keycloak по refresh-токену.

        Args:
            refresh_token: Refresh-токен, выданный при входе.
        """
        _get_openid().logout(refresh_token)

    def create_user(
        self,
        username: str,
        password: str,
        email: str,
        first_name: str = "",
        last_name: str = "",
        enabled: bool = True,
        temporary_password: bool = False,
    ) -> str:
        """Создаёт пользователя в Keycloak.

        Args:
            username: Имя учётной записи.
            password: Пароль.
            email: Электронная почта.
            first_name: Имя.
            last_name: Фамилия.
            enabled: Признак активности.
            temporary_password: Признак временного пароля.

        Returns:
            Идентификатор созданного пользователя Keycloak.
        """
        admin = _get_admin()
        user_id = admin.create_user(
            {
                "username": username,
                "email": email,
                "firstName": first_name,
                "lastName": last_name,
                "enabled": enabled,
                "credentials": [
                    {
                        "type": "password",
                        "value": password,
                        "temporary": temporary_password,
                    }
                ],
            }
        )
        return user_id

    def update_user(self, keycloak_user_id: str, **kwargs: object) -> None:
        """Обновляет поля пользователя в Keycloak.

        Args:
            keycloak_user_id: Идентификатор пользователя Keycloak.
            **kwargs: Обновляемые поля (email, first_name, last_name, enabled).
        """
        admin = _get_admin()
        payload = {}
        if "email" in kwargs:
            payload["email"] = kwargs["email"]
        if "first_name" in kwargs:
            payload["firstName"] = kwargs["first_name"]
        if "last_name" in kwargs:
            payload["lastName"] = kwargs["last_name"]
        if "enabled" in kwargs:
            payload["enabled"] = kwargs["enabled"]
        if payload:
            admin.update_user(keycloak_user_id, payload)

    def reset_password(
        self, keycloak_user_id: str, new_password: str, temporary: bool = False
    ) -> None:
        """Сбрасывает пароль пользователя в Keycloak.

        Args:
            keycloak_user_id: Идентификатор пользователя Keycloak.
            new_password: Новый пароль.
            temporary: Признак временного пароля.
        """
        admin = _get_admin()
        admin.set_user_password(keycloak_user_id, new_password, temporary)

    def delete_user(self, keycloak_user_id: str) -> None:
        """Удаляет пользователя из Keycloak.

        Args:
            keycloak_user_id: Идентификатор пользователя Keycloak.
        """
        admin = _get_admin()
        admin.delete_user(keycloak_user_id)

    def get_user_id_by_username(self, username: str) -> str | None:
        """Возвращает идентификатор пользователя Keycloak по имени.

        Args:
            username: Имя учётной записи.

        Returns:
            Идентификатор пользователя или None, если не найден.
        """
        admin = _get_admin()
        users = admin.get_users({"username": username, "exact": True})
        if users:
            return users[0]["id"]
        return None

    def decode_token(self, token: str) -> dict:
        """Декодирует JWT-токен с помощью публичного ключа Keycloak.

        Args:
            token: JWT-токен.

        Returns:
            Словарь с claims токена.
        """
        openid = _get_openid()
        public_key_pem = (
            "-----BEGIN PUBLIC KEY-----\n"
            + openid.public_key()
            + "\n-----END PUBLIC KEY-----"
        )
        return jwt.decode(
            token,
            public_key_pem,
            algorithms=["RS256"],
            options={"verify_aud": False},
        )


keycloak_service = KeycloakService()
