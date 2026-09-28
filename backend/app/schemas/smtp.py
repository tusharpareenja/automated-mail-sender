from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.schemas.common import ORMModel


class SMTPCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(ge=1, le=65535)
    username: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=500)
    from_email: EmailStr
    from_name: str | None = Field(default=None, max_length=200)
    use_tls: bool = True
    use_ssl: bool = False
    hourly_limit: int = Field(default=50, ge=1, le=100000)
    daily_limit: int = Field(default=400, ge=1, le=1000000)


class SMTPUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    host: str | None = Field(default=None, max_length=255)
    port: int | None = Field(default=None, ge=1, le=65535)
    username: str | None = None
    password: str | None = None
    from_email: EmailStr | None = None
    from_name: str | None = None
    use_tls: bool | None = None
    use_ssl: bool | None = None
    hourly_limit: int | None = Field(default=None, ge=1, le=100000)
    daily_limit: int | None = Field(default=None, ge=1, le=1000000)
    is_active: bool | None = None


class SMTPTestEmail(BaseModel):
    to_email: EmailStr


class SMTPOut(ORMModel):
    id: UUID
    name: str
    host: str
    port: int
    username: str
    from_email: str
    from_name: str | None
    use_tls: bool
    use_ssl: bool
    hourly_limit: int
    daily_limit: int
    is_active: bool
    health_status: str
    consecutive_failures: int
    last_tested_at: datetime | None
    last_error: str | None
    created_at: datetime
    has_password: bool = True
