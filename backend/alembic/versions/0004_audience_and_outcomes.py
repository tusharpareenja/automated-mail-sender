"""campaign audience filters and sent/failed groups

Revision ID: 0004_audience_outcomes
Revises: 0003_lead_groups
Create Date: 2026-09-23
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004_audience_outcomes"
down_revision = "0003_lead_groups"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("leads", sa.Column("country", sa.String(80), nullable=True))
    op.add_column("leads", sa.Column("study_opportunity", sa.String(160), nullable=True))
    op.add_column(
        "leads",
        sa.Column("role_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "leads",
        sa.Column("email_kind", sa.String(20), nullable=False, server_default=""),
    )
    op.create_index("ix_leads_country", "leads", ["country"])
    op.create_index("ix_leads_study_opportunity", "leads", ["study_opportunity"])

    op.add_column(
        "lead_groups",
        sa.Column("purpose", sa.String(20), nullable=False, server_default="source"),
    )

    op.add_column(
        "campaigns",
        sa.Column(
            "audience_filters",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "campaigns",
        sa.Column("sent_group_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "campaigns",
        sa.Column("failed_group_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_campaigns_sent_group",
        "campaigns",
        "lead_groups",
        ["sent_group_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_campaigns_failed_group",
        "campaigns",
        "lead_groups",
        ["failed_group_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column(
        "campaign_emails",
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("campaign_emails", "attempt_count")
    op.drop_constraint("fk_campaigns_failed_group", "campaigns", type_="foreignkey")
    op.drop_constraint("fk_campaigns_sent_group", "campaigns", type_="foreignkey")
    op.drop_column("campaigns", "failed_group_id")
    op.drop_column("campaigns", "sent_group_id")
    op.drop_column("campaigns", "audience_filters")
    op.drop_column("lead_groups", "purpose")
    op.drop_index("ix_leads_study_opportunity", table_name="leads")
    op.drop_index("ix_leads_country", table_name="leads")
    op.drop_column("leads", "email_kind")
    op.drop_column("leads", "role_verified")
    op.drop_column("leads", "study_opportunity")
    op.drop_column("leads", "country")
