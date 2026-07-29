from __future__ import annotations

import base64
import hashlib
import hmac
import time

from app.config import settings

COOKIE_NAME = "sql_agent_session"


def validate_security_config() -> None:
    if not settings.allow_weak_local_password and (
        len(settings.app_password) < 12 or settings.app_password.startswith("change-this-")
    ):
        raise RuntimeError("APP_PASSWORD must be replaced with at least 12 characters")
    if len(settings.session_secret) < 32 or settings.session_secret.startswith("change-this-"):
        raise RuntimeError("SESSION_SECRET must be replaced with at least 32 characters")


def verify_login(username: str, password: str) -> bool:
    return hmac.compare_digest(username, settings.app_username) and hmac.compare_digest(password, settings.app_password)


def create_session(username: str) -> str:
    expires = int(time.time()) + settings.session_ttl_seconds
    payload = f"{username}|{expires}".encode()
    encoded = base64.urlsafe_b64encode(payload).decode().rstrip("=")
    signature = hmac.new(settings.session_secret.encode(), encoded.encode(), hashlib.sha256).hexdigest()
    return f"{encoded}.{signature}"


def read_session(token: str) -> str | None:
    try:
        encoded, signature = token.split(".", 1)
        expected = hmac.new(settings.session_secret.encode(), encoded.encode(), hashlib.sha256).hexdigest()
        payload = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        username, expires = payload.decode().rsplit("|", 1)
        if not hmac.compare_digest(signature, expected) or int(expires) < int(time.time()):
            return None
        return username
    except (ValueError, UnicodeDecodeError):
        return None
