from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import SMTPHealth
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class SMTPAccount(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "smtp_accounts"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False)
    username: Mapped[str] = mapped_column(String(255), nullable=False)
    password_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    from_email: Mapped[str] = mapped_column(String(320), nullable=False)
    from_name: Mapped[str | None] = mapped_column(String(200))
    use_tls: Mapped[bool] = mapped_column(default=True, nullable=False)
    use_ssl: Mapped[bool] = mapped_column(default=False, nullable=False)
    hourly_limit: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    daily_limit: Mapped[int] = mapped_column(Integer, default=400, nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    health_status: Mapped[str] = mapped_column(
        String(20), default=SMTPHealth.HEALTHY.value, nullable=False
    )
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)

    user = relationship("User")


class SMTPUsage(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "smtp_usage"
    __table_args__ = (
        UniqueConstraint(
            "smtp_account_id",
            "bucket_type",
            "bucket_start",
            name="uq_smtp_usage_bucket",
        ),
    )

    smtp_account_id: Mapped[UUID] = mapped_column(
        ForeignKey("smtp_accounts.id", ondelete="CASCADE"), index=True, nullable=False
    )
    bucket_type: Mapped[str] = mapped_column(String(10), nullable=False)
    bucket_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    send_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
