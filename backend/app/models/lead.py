from uuid import UUID

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import ImportStatus
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Lead(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "leads"
    __table_args__ = (UniqueConstraint("user_id", "email", name="uq_leads_user_email"),)

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    first_name: Mapped[str | None] = mapped_column(String(120))
    last_name: Mapped[str | None] = mapped_column(String(120))
    company: Mapped[str | None] = mapped_column(String(200))
    title: Mapped[str | None] = mapped_column(String(200))
    industry: Mapped[str | None] = mapped_column(String(160))
    website: Mapped[str | None] = mapped_column(String(400))
    country: Mapped[str | None] = mapped_column(String(80), index=True)
    study_opportunity: Mapped[str | None] = mapped_column(String(160), index=True)
    role_verified: Mapped[bool] = mapped_column(default=False, nullable=False)
    email_kind: Mapped[str] = mapped_column(String(20), default="", nullable=False)
    custom_fields: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    is_valid: Mapped[bool] = mapped_column(default=True, nullable=False)

    user = relationship("User")


class LeadGroup(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "lead_groups"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_lead_groups_user_name"),)

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    purpose: Mapped[str] = mapped_column(String(20), default="source", nullable=False)

    user = relationship("User")
    members = relationship("LeadGroupMember", back_populates="group", cascade="all, delete-orphan")


class LeadGroupMember(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "lead_group_members"
    __table_args__ = (UniqueConstraint("group_id", "lead_id", name="uq_lead_group_member"),)

    group_id: Mapped[UUID] = mapped_column(
        ForeignKey("lead_groups.id", ondelete="CASCADE"), index=True, nullable=False
    )
    lead_id: Mapped[UUID] = mapped_column(
        ForeignKey("leads.id", ondelete="CASCADE"), index=True, nullable=False
    )

    group = relationship("LeadGroup", back_populates="members")
    lead = relationship("Lead")


class LeadImport(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "lead_imports"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default=ImportStatus.PENDING.value, nullable=False
    )
    total_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    valid_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    invalid_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    column_mapping: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    error_report: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    raw_csv: Mapped[str] = mapped_column(Text, default="", nullable=False)
    group_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("lead_groups.id", ondelete="SET NULL"), index=True
    )
