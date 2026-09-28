from uuid import uuid4

from app.core.config import Settings, to_async_database_url, to_sync_database_url
from app.core.security import (
    create_access_token,
    decode_token,
    decrypt_secret,
    encrypt_secret,
    hash_password,
    hash_token,
    verify_password,
)


def test_postgres_url_is_converted_for_async():
    async_url, needs_ssl = to_async_database_url(
        "postgresql://user:pass@host/db?sslmode=require&channel_binding=require"
    )
    assert async_url.startswith("postgresql+asyncpg://")
    assert "sslmode" not in async_url
    assert "channel_binding" not in async_url
    assert "ssl=" not in async_url
    assert needs_ssl is True
    assert to_sync_database_url(async_url).startswith("postgresql+psycopg2://")


def test_psycopg3_style_url_uses_installed_drivers():
    url = "postgresql+psycopg://user:pass@host/db?sslmode=require"
    async_url, needs_ssl = to_async_database_url(url)
    assert async_url.startswith("postgresql+asyncpg://")
    assert needs_ssl is True
    sync_url = to_sync_database_url(url)
    assert sync_url.startswith("postgresql+psycopg2://")


def test_password_hash_roundtrip():
    hashed = hash_password("CorrectHorseBattery1")
    assert hashed != "CorrectHorseBattery1"
    assert verify_password("CorrectHorseBattery1", hashed)
    assert not verify_password("wrong-password", hashed)


def test_token_hash_is_deterministic():
    assert hash_token("abc") == hash_token("abc")
    assert hash_token("abc") != hash_token("abcd")


def test_access_token_roundtrip():
    settings = Settings(
        secret_key="test-secret-key-which-is-long-enough-1234567890",
        encryption_key="test-encryption-key-value",
        database_url="postgresql+asyncpg://x:x@localhost/x",
        database_sync_url="postgresql://x:x@localhost/x",
    )
    user_id = uuid4()
    token = create_access_token(settings, user_id)
    payload = decode_token(settings, token, "access")
    assert payload["sub"] == str(user_id)


def test_secret_encryption_roundtrip():
    settings = Settings(
        secret_key="test-secret-key-which-is-long-enough-1234567890",
        encryption_key="test-encryption-key-value",
        database_url="postgresql+asyncpg://x:x@localhost/x",
        database_sync_url="postgresql://x:x@localhost/x",
    )
    encrypted = encrypt_secret(settings, "smtp-password")
    assert "smtp-password" not in encrypted
    assert decrypt_secret(settings, encrypted) == "smtp-password"
