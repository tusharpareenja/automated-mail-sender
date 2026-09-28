from functools import lru_cache
from typing import Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: Literal["development", "test", "production"] = "development"
    app_name: str = "Mail Campaign API"
    secret_key: str = Field(min_length=32)
    encryption_key: str = Field(min_length=16)
    frontend_url: str = "http://localhost:3000"

    database_url: str
    database_sync_url: str = ""
    database_ssl: bool = False

    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    cookie_secure: bool = False
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    access_token_minutes: int = 43200
    refresh_token_days: int = 30
    tracking_public_url: str = ""

    openai_api_key: str = ""
    openai_model: str = "gpt-5.6-luna"

    max_csv_bytes: int = 20 * 1024 * 1024
    global_hourly_send_limit: int = 5000

    # Hosted assets + tracking analytics
    asset_storage_dir: str = "storage/assets"
    max_asset_bytes: int = 10 * 1024 * 1024
    allowed_asset_mime_types: str = (
        "image/png,image/jpeg,image/gif,image/webp,application/pdf"
    )
    tracking_ip_hash_secret: str = ""
    tracking_request_retention_days: int = 90
    open_automated_window_seconds: int = 30

    # Azure Blob Storage (preferred when connection string is set)
    azure_storage_connection_string: str = ""
    azure_storage_container_name: str = "mindsurvey"

    @field_validator("frontend_url")
    @classmethod
    def strip_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/")

    @model_validator(mode="after")
    def normalize_database_urls(self):
        async_url, needs_ssl = to_async_database_url(self.database_url)
        self.database_url = async_url
        self.database_ssl = needs_ssl
        self.database_sync_url = to_sync_database_url(
            self.database_sync_url or async_url
        )
        return self

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def cors_origins(self) -> list[str]:
        return [self.frontend_url]

    @property
    def allowed_asset_mimes(self) -> set[str]:
        return {
            item.strip().lower()
            for item in self.allowed_asset_mime_types.split(",")
            if item.strip()
        }

    @property
    def ip_hash_secret(self) -> str:
        return self.tracking_ip_hash_secret or self.secret_key

    @property
    def use_azure_storage(self) -> bool:
        return bool(self.azure_storage_connection_string.strip())


def to_async_database_url(url: str) -> tuple[str, bool]:
    url = url.strip()
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    if url.startswith("postgresql+psycopg2://"):
        url = "postgresql+asyncpg://" + url[len("postgresql+psycopg2://") :]
    elif url.startswith("postgresql://"):
        url = "postgresql+asyncpg://" + url[len("postgresql://") :]
    return _rewrite_asyncpg_query(url)


def to_sync_database_url(url: str) -> str:
    url = url.strip()
    url = url.replace("postgresql+asyncpg://", "postgresql://", 1)
    url = url.replace("postgresql+psycopg2://", "postgresql://", 1)
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    ssl = query.pop("ssl", None)
    if ssl and "sslmode" not in query:
        query["sslmode"] = "require" if ssl in {"require", "true", "1"} else ssl
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _rewrite_asyncpg_query(url: str) -> tuple[str, bool]:
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    sslmode = query.pop("sslmode", None)
    ssl = query.pop("ssl", None)
    query.pop("channel_binding", None)
    needs_ssl = sslmode in {"require", "verify-ca", "verify-full"} or ssl in {
        "true",
        "1",
        "require",
    }
    cleaned = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
    return cleaned, needs_ssl


@lru_cache
def get_settings() -> Settings:
    return Settings()
