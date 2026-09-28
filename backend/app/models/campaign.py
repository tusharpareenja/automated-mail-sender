from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import CampaignStatus, EmailStatus
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Campaign(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "campaigns"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    template_id: Mapped[UUID | None] = mapped_column(ForeignKey("templates.id", ondelete="SET NULL"))
    template_snapshot: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default=CampaignStatus.DRAFT.value, index=True, nullable=False
    )
    ai_enabled: Mapped[bool] = mapped_column(default=True, nullable=False)
    ai_instructions: Mapped[str | None] = mapped_column(Text)
    hourly_limit: Mapped[int] = mapped_column(Integer, default=40, nullable=False)
    daily_limit: Mapped[int] = mapped_column(Integer, default=300, nullable=False)
    delay_seconds: Mapped[int] = mapped_column(Integer, default=8, nullable=False)
    audience_filters: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    sent_group_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("lead_groups.id", ondelete="SET NULL")
    )
    failed_group_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("lead_groups.id", ondelete="SET NULL")
    )
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    total_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    queued_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sent_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    bounced_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    open_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    click_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unsubscribe_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failure_reason: Mapped[str | None] = mapped_column(Text)

    user = relationship("User")
    emails: Mapped[list["CampaignEmail"]] = relationship(back_populates="campaign")


class CampaignLead(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "campaign_leads"
    __table_args__ = (
        UniqueConstraint("campaign_id", "lead_id", name="uq_campaign_lead"),
    )

    campaign_id: Mapped[UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), index=True, nullable=False
    )
    lead_id: Mapped[UUID] = mapped_column(
        ForeignKey("leads.id", ondelete="CASCADE"), index=True, nullable=False
    )


class CampaignSMTP(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "campaign_smtp_accounts"
    __table_args__ = (
        UniqueConstraint("campaign_id", "smtp_account_id", name="uq_campaign_smtp"),
    )

    campaign_id: Mapped[UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), index=True, nullable=False
    )
    smtp_account_id: Mapped[UUID] = mapped_column(
        ForeignKey("smtp_accounts.id", ondelete="CASCADE"), index=True, nullable=False
    )


class CampaignEmail(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "campaign_emails"

    campaign_id: Mapped[UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), index=True, nullable=False
    )
    lead_id: Mapped[UUID] = mapped_column(
        ForeignKey("leads.id", ondelete="CASCADE"), index=True, nullable=False
    )
    smtp_account_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("smtp_accounts.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(
        String(20), default=EmailStatus.QUEUED.value, index=True, nullable=False
    )
    subject: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    html_body: Mapped[str] = mapped_column(Text, default="", nullable=False)
    text_body: Mapped[str] = mapped_column(Text, default="", nullable=False)
    personalization: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    tracking_token: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    message_id: Mapped[str | None] = mapped_column(String(200), unique=True)
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    claim_owner: Mapped[str | None] = mapped_column(String(80))
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    campaign: Mapped[Campaign] = relationship(back_populates="emails")
    lead = relationship("Lead")
