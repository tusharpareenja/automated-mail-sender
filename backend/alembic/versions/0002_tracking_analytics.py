"""request-level tracking and hosted assets

Revision ID: 0002_tracking_analytics
Revises: 0001_initial
Create Date: 2026-09-21
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002_tracking_analytics"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "campaign_assets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "template_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("templates.id", ondelete="SET NULL"),
        ),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("stored_filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(120), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False, server_default="other"),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("checksum_sha256", sa.String(64), nullable=False),
        sa.Column("placeholder_key", sa.String(80), nullable=False),
        sa.Column("access_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("download_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_campaign_assets_user_id", "campaign_assets", ["user_id"])
    op.create_index("ix_campaign_assets_template_id", "campaign_assets", ["template_id"])
    op.create_index(
        "ix_campaign_assets_placeholder_key",
        "campaign_assets",
        ["placeholder_key"],
        unique=True,
    )

    op.create_table(
        "asset_delivery_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "asset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("campaign_assets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "email_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("campaign_emails.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "campaign_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("campaigns.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token", sa.String(64), nullable=False),
        sa.Column("access_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("download_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("asset_id", "email_id", name="uq_asset_delivery_email"),
    )
    op.create_index("ix_asset_delivery_tokens_asset_id", "asset_delivery_tokens", ["asset_id"])
    op.create_index("ix_asset_delivery_tokens_email_id", "asset_delivery_tokens", ["email_id"])
    op.create_index("ix_asset_delivery_tokens_campaign_id", "asset_delivery_tokens", ["campaign_id"])
    op.create_index("ix_asset_delivery_tokens_token", "asset_delivery_tokens", ["token"], unique=True)

    op.create_table(
        "tracking_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "email_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("campaign_emails.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "campaign_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("campaigns.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("request_type", sa.String(40), nullable=False),
        sa.Column("classification", sa.String(40), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column(
            "classification_reasons",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("ip_hash", sa.String(64)),
        sa.Column("network_prefix", sa.String(64)),
        sa.Column("user_agent", sa.String(500)),
        sa.Column("referrer", sa.String(500)),
        sa.Column("request_method", sa.String(16), nullable=False, server_default="GET"),
        sa.Column("range_header", sa.String(120)),
        sa.Column("seconds_after_send", sa.Float()),
        sa.Column(
            "asset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("campaign_assets.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "tracked_link_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tracked_links.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "metadata",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_tracking_requests_email_id", "tracking_requests", ["email_id"])
    op.create_index("ix_tracking_requests_campaign_id", "tracking_requests", ["campaign_id"])
    op.create_index("ix_tracking_requests_user_id", "tracking_requests", ["user_id"])
    op.create_index("ix_tracking_requests_ip_hash", "tracking_requests", ["ip_hash"])
    op.create_index("ix_tracking_requests_asset_id", "tracking_requests", ["asset_id"])
    op.create_index("ix_tracking_requests_tracked_link_id", "tracking_requests", ["tracked_link_id"])
    op.create_index(
        "ix_tracking_requests_email_created",
        "tracking_requests",
        ["email_id", "created_at"],
    )

    op.add_column("email_events", sa.Column("classification", sa.String(40)))
    op.add_column("email_events", sa.Column("confidence", sa.Float()))
    op.add_column(
        "email_events",
        sa.Column(
            "classification_reasons",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column("email_events", sa.Column("ip_hash", sa.String(64)))
    op.add_column("email_events", sa.Column("network_prefix", sa.String(64)))
    op.add_column("email_events", sa.Column("user_agent", sa.String(500)))
    op.add_column("email_events", sa.Column("referrer", sa.String(500)))
    op.add_column("email_events", sa.Column("request_method", sa.String(16)))
    op.add_column("email_events", sa.Column("range_header", sa.String(120)))
    op.add_column(
        "email_events",
        sa.Column(
            "asset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("campaign_assets.id", ondelete="SET NULL"),
        ),
    )
    op.add_column(
        "email_events",
        sa.Column(
            "tracked_link_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tracked_links.id", ondelete="SET NULL"),
        ),
    )
    op.create_index("ix_email_events_asset_id", "email_events", ["asset_id"])
    op.create_index("ix_email_events_tracked_link_id", "email_events", ["tracked_link_id"])

    op.add_column(
        "tracked_links",
        sa.Column(
            "asset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("campaign_assets.id", ondelete="SET NULL"),
        ),
    )
    op.create_index("ix_tracked_links_asset_id", "tracked_links", ["asset_id"])


def downgrade() -> None:
    op.drop_index("ix_tracked_links_asset_id", table_name="tracked_links")
    op.drop_column("tracked_links", "asset_id")

    op.drop_index("ix_email_events_tracked_link_id", table_name="email_events")
    op.drop_index("ix_email_events_asset_id", table_name="email_events")
    op.drop_column("email_events", "tracked_link_id")
    op.drop_column("email_events", "asset_id")
    op.drop_column("email_events", "range_header")
    op.drop_column("email_events", "request_method")
    op.drop_column("email_events", "referrer")
    op.drop_column("email_events", "user_agent")
    op.drop_column("email_events", "network_prefix")
    op.drop_column("email_events", "ip_hash")
    op.drop_column("email_events", "classification_reasons")
    op.drop_column("email_events", "confidence")
    op.drop_column("email_events", "classification")

    op.drop_index("ix_tracking_requests_email_created", table_name="tracking_requests")
    op.drop_index("ix_tracking_requests_tracked_link_id", table_name="tracking_requests")
    op.drop_index("ix_tracking_requests_asset_id", table_name="tracking_requests")
    op.drop_index("ix_tracking_requests_ip_hash", table_name="tracking_requests")
    op.drop_index("ix_tracking_requests_user_id", table_name="tracking_requests")
    op.drop_index("ix_tracking_requests_campaign_id", table_name="tracking_requests")
    op.drop_index("ix_tracking_requests_email_id", table_name="tracking_requests")
    op.drop_table("tracking_requests")

    op.drop_index("ix_asset_delivery_tokens_token", table_name="asset_delivery_tokens")
    op.drop_index("ix_asset_delivery_tokens_campaign_id", table_name="asset_delivery_tokens")
    op.drop_index("ix_asset_delivery_tokens_email_id", table_name="asset_delivery_tokens")
    op.drop_index("ix_asset_delivery_tokens_asset_id", table_name="asset_delivery_tokens")
    op.drop_table("asset_delivery_tokens")

    op.drop_index("ix_campaign_assets_placeholder_key", table_name="campaign_assets")
    op.drop_index("ix_campaign_assets_template_id", table_name="campaign_assets")
    op.drop_index("ix_campaign_assets_user_id", table_name="campaign_assets")
    op.drop_table("campaign_assets")
