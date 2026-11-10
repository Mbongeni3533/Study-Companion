"""Password hashing, token signing and ID helpers."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

from ..config import get_settings

_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 32


# ------------------------------------------------------------------ id utils
def _short_token(nbytes: int = 9) -> str:
    return secrets.token_urlsafe(nbytes).replace("-", "").replace("_", "")[:12]


def generate_user_id() -> str:
    return f"user_{_short_token()}"


def generate_course_id() -> str:
    return f"course_{_short_token()}"


def generate_document_id() -> str:
    return f"doc_{_short_token()}"


def generate_topic_id() -> str:
    return f"topic_{_short_token()}"


def generate_task_id() -> str:
    return f"task_{_short_token()}"


def generate_session_id() -> str:
    return f"chat_{_short_token()}"


def generate_booking_id() -> str:
    return f"cns_{_short_token()}"


# ------------------------------------------------------------------ passwords
def hash_password(password: str) -> str:
    """Hash a password with scrypt (stdlib only, no native build step)."""
    if not password:
        raise ValueError("password must not be empty")
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_SCRYPT_DKLEN,
    )
    return "scrypt${}${}${}${}${}".format(
        _SCRYPT_N,
        _SCRYPT_R,
        _SCRYPT_P,
        base64.b64encode(salt).decode("ascii"),
        base64.b64encode(derived).decode("ascii"),
    )


def verify_password(password: str, stored: str | None) -> bool:
    if not stored or not password:
        return False
    try:
        scheme, n, r, p, salt_b64, hash_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
        derived = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(expected),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(derived, expected)


# --------------------------------------------------------------------- tokens
def create_access_token(subject: str, expires_minutes: int | None = None) -> str:
    settings = get_settings()
    minutes = expires_minutes or settings.access_token_expire_minutes
    issued = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "iat": int(issued.timestamp()),
        "exp": int((issued + timedelta(minutes=minutes)).timestamp()),
        "typ": "access",
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any] | None:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError:
        return None
