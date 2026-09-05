"""Security primitives: Fernet encryption at rest, bcrypt password hashing,
JWT tokens, and secret masking for display.

API keys are encrypted with a Fernet key deterministically derived (SHA-256 ->
urlsafe base64) from ``SECRET_KEY``. This means the same ``SECRET_KEY`` always
decrypts the same stored keys, while losing the ``SECRET_KEY`` makes stored
keys unrecoverable. The decrypted values are only ever used server-side and are
never serialized into API responses (responses carry masked values only).
"""
from __future__ import annotations

import base64
import hashlib
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from cryptography.fernet import Fernet, InvalidToken

from ..config import get_settings

settings = get_settings()

ALGORITHM = "HS256"


# ---------------------------------------------------------------------------
# Fernet (symmetric encryption of API keys at rest)
# ---------------------------------------------------------------------------
def _fernet() -> Fernet:
    digest = hashlib.sha256(settings.secret_key.encode("utf-8")).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_secret(plaintext: str) -> str:
    """Encrypt a secret string, returning a Fernet token (str)."""
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_secret(token: str) -> str:
    """Decrypt a Fernet token back to plaintext.

    Raises ``ValueError`` on tampered/undecryptable tokens so callers can treat
    a rotated ``SECRET_KEY`` as "no credentials configured".
    """
    try:
        return _fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError) as exc:  # pragma: no cover - defensive
        raise ValueError("Unable to decrypt credential (wrong SECRET_KEY?)") from exc


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------
def create_access_token(subject: str, expires_minutes: int | None = None) -> str:
    lifetime = expires_minutes or settings.access_token_expire_minutes
    expire = datetime.now(timezone.utc) + timedelta(minutes=lifetime)
    payload = {"sub": subject, "exp": expire, "iat": datetime.now(timezone.utc)}
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])


# ---------------------------------------------------------------------------
# Masking (frontend-safe display)
# ---------------------------------------------------------------------------
def mask_key(value: str | None) -> str | None:
    """Return ``AK************1234``-style masked key. Never reveals plaintext."""
    if not value:
        return None
    if len(value) <= 8:
        return "*" * len(value)
    head = value[:2]
    tail = value[-4:]
    stars = "*" * (len(value) - len(head) - len(tail))
    return f"{head}{stars}{tail}"
