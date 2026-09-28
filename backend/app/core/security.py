import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import Settings

password_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)

ACCESS_COOKIE = "access_token"
REFRESH_COOKIE = "refresh_token"
CSRF_COOKIE = "csrf_token"
CSRF_HEADER = "X-CSRF-Token"


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def create_access_token(settings: Settings, user_id: UUID) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "typ": "access",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.access_token_minutes)).timestamp()),
        "jti": secrets.token_urlsafe(16),
    }
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def create_ws_token(settings: Settings, user_id: UUID) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "typ": "ws",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=5)).timestamp()),
        "jti": secrets.token_urlsafe(16),
    }
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def decode_token(settings: Settings, token: str, expected_type: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
    except jwt.ExpiredSignatureError as exc:
        raise ValueError("Token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise ValueError("Invalid token") from exc
    token_type = payload.get("typ")
    if expected_type == "ws":
        if token_type not in {"ws", "access"}:
            raise ValueError("Invalid token type")
    elif token_type != expected_type:
        raise ValueError("Invalid token type")
    return payload


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def csrf_tokens_match(cookie_value: str | None, header_value: str | None) -> bool:
    if not cookie_value or not header_value:
        return False
    return hmac.compare_digest(cookie_value, header_value)


def generate_tracking_token() -> str:
    return secrets.token_urlsafe(32)


def fernet_from_settings(settings: Settings) -> Fernet:
    key = settings.encryption_key.encode("utf-8")
    if len(key) == 44 and key.endswith(b"="):
        return Fernet(key)
    digest = hashlib.sha256(key).digest()
    import base64

    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(settings: Settings, plaintext: str) -> str:
    return fernet_from_settings(settings).encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_secret(settings: Settings, ciphertext: str) -> str:
    try:
        return fernet_from_settings(settings).decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("Unable to decrypt secret") from exc
