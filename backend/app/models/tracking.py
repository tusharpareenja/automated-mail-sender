from uuid import UUID

from sqlalchemy import Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import AssetKind, EventType, SuppressionReason
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class EmailEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "email_events"

    email_id: Mapped[UUID] = mapped_column(
        ForeignKey("campaign_emails.id", ondelete="CASCADE"), index=True, nullable=False
    )
    campaign_id: Mapped[UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, default=dict, nullable=False)
    dedupe_key: Mapped[str | None] = mapped_column(String(120))
    classification: Mapped[str | None] = mapped_column(String(40))
    confidence: Mapped[float | None] = mapped_column(Float)
    classification_reasons: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    ip_hash: Mapped[str | None] = mapped_column(String(64))
    network_prefix: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(500))
    referrer: Mapped[str | None] = mapped_column(String(500))
    request_method: Mapped[str | None] = mapped_column(String(16))
    range_header: Mapped[str | None] = mapped_column(String(120))
    asset_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("campaign_assets.id", ondelete="SET NULL"), index=True
    )
    tracked_link_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("tracked_links.id", ondelete="SET NULL"), index=True
    )


class TrackingRequest(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Every pixel, view, click, or asset access request."""

    __tablename__ = "tracking_requests"

    email_id: Mapped[UUID] = mapped_column(
        ForeignKey("campaign_emails.id", ondelete="CASCADE"), index=True, nullable=False
    )
    campaign_id: Mapped[UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    request_type: Mapped[str] = mapped_column(String(40), nullable=False)
    classification: Mapped[str] = mapped_column(String(40), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    classification_reasons: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    ip_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    network_prefix: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(500))
    referrer: Mapped[str | None] = mapped_column(String(500))
    request_method: Mapped[str] = mapped_column(String(16), default="GET", nullable=False)
    range_header: Mapped[str | None] = mapped_column(String(120))
    seconds_after_send: Mapped[float | None] = mapped_column(Float)
    asset_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("campaign_assets.id", ondelete="SET NULL"), index=True
    )
    tracked_link_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("tracked_links.id", ondelete="SET NULL"), index=True
    )
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, default=dict, nullable=False)


class TrackedLink(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "tracked_links"

    email_id: Mapped[UUID] = mapped_column(
        ForeignKey("campaign_emails.id", ondelete="CASCADE"), index=True, nullable=False
    )
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    destination_url: Mapped[str] = mapped_column(Text, nullable=False)
    click_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    asset_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("campaign_assets.id", ondelete="SET NULL"), index=True
    )


class CampaignAsset(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "campaign_assets"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    template_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("templates.id", ondelete="SET NULL"), index=True
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), default=AssetKind.OTHER.value, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    placeholder_key: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    access_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    download_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    tokens = relationship("AssetDeliveryToken", back_populates="asset")


class AssetDeliveryToken(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "asset_delivery_tokens"
    __table_args__ = (
        UniqueConstraint("asset_id", "email_id", name="uq_asset_delivery_email"),
    )

    asset_id: Mapped[UUID] = mapped_column(
        ForeignKey("campaign_assets.id", ondelete="CASCADE"), index=True, nullable=False
    )
    email_id: Mapped[UUID] = mapped_column(
        ForeignKey("campaign_emails.id", ondelete="CASCADE"), index=True, nullable=False
    )
    campaign_id: Mapped[UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), index=True, nullable=False
    )
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    access_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    download_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    asset = relationship("CampaignAsset", back_populates="tokens")


class SuppressionEntry(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "suppression_entries"
    __table_args__ = (UniqueConstraint("user_id", "email", name="uq_suppression_user_email"),)

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    email: Mapped[str] = mapped_column(String(320), index=True, nullable=False)
    reason: Mapped[str] = mapped_column(
        String(30), default=SuppressionReason.MANUAL.value, nullable=False
    )
    source: Mapped[str | None] = mapped_column(String(80))


class UnsubscribeEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "unsubscribe_events"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    email_id: Mapped[UUID | None] = mapped_column(ForeignKey("campaign_emails.id", ondelete="SET NULL"))
    campaign_id: Mapped[UUID | None] = mapped_column(ForeignKey("campaigns.id", ondelete="SET NULL"))
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    token: Mapped[str] = mapped_column(String(64), nullable=False)


# Keep EventType import used by type checkers / migrations helpers
_ = EventType
