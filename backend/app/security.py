import base64
import logging
import secrets
import time
from functools import lru_cache

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.config import Settings

logger = logging.getLogger(__name__)

_hasher = PasswordHasher()
# Verified against when an email isn't found, so login takes the same time
# whether or not the account exists.
_DUMMY_HASH = _hasher.hash(secrets.token_hex(16))

MIN_PASSWORD = 8
MAX_PASSWORD = 128


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerificationError, InvalidHashError):
        return False


@lru_cache
def _random_secret() -> str:
    logger.warning(
        "Neither SECRET_KEY nor ENCRYPTION_KEY is set: using a random session key, "
        "so everyone is signed out on restart"
    )
    return secrets.token_urlsafe(32)


def session_secret(settings: Settings) -> str:
    if settings.secret_key:
        return settings.secret_key
    if settings.encryption_key:
        # A separate key derived from ENCRYPTION_KEY, so one env var covers both.
        derived = HKDF(
            algorithm=hashes.SHA256(), length=32, salt=None, info=b"webui-replica session"
        ).derive(settings.encryption_key.encode())
        return base64.urlsafe_b64encode(derived).decode()
    return _random_secret()


def create_session_token(user_id: str, session_version: int, settings: Settings) -> str:
    now = int(time.time())
    payload = {
        "sub": user_id,
        "sv": session_version,
        "iat": now,
        "exp": now + settings.session_days * 86400,
    }
    return jwt.encode(payload, session_secret(settings), algorithm="HS256")


def decode_session_token(token: str, settings: Settings) -> dict | None:
    try:
        return jwt.decode(
            token,
            session_secret(settings),
            algorithms=["HS256"],
            options={"require": ["sub", "sv", "exp"]},
        )
    except jwt.PyJWTError:
        return None
