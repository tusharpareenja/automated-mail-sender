"""lead groups for csv imports

Revision ID: 0003_lead_groups
Revises: 0002_tracking_analytics
Create Date: 2026-09-23
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003_lead_groups"
down_revision = "0002_tracking_analytics"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "lead_groups",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "name", name="uq_lead_groups_user_name"),
    )
    op.create_index("ix_lead_groups_user_id", "lead_groups", ["user_id"])

    op.create_table(
        "lead_group_members",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "group_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("lead_groups.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "lead_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("leads.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.UniqueConstraint("group_id", "lead_id", name="uq_lead_group_member"),
    )
    op.create_index("ix_lead_group_members_group_id", "lead_group_members", ["group_id"])
    op.create_index("ix_lead_group_members_lead_id", "lead_group_members", ["lead_id"])

    op.add_column(
        "lead_imports",
        sa.Column(
            "group_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("lead_groups.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_lead_imports_group_id", "lead_imports", ["group_id"])

    op.execute(
        """
        INSERT INTO lead_groups (id, user_id, name, created_at, updated_at)
        SELECT gen_random_uuid(), user_id, 'Existing leads', now(), now()
        FROM leads
        GROUP BY user_id
        """
    )
    op.execute(
        """
        INSERT INTO lead_group_members (id, group_id, lead_id)
        SELECT gen_random_uuid(), g.id, l.id
        FROM leads l
        JOIN lead_groups g ON g.user_id = l.user_id AND g.name = 'Existing leads'
        """
    )


def downgrade() -> None:
    op.drop_index("ix_lead_imports_group_id", table_name="lead_imports")
    op.drop_column("lead_imports", "group_id")
    op.drop_index("ix_lead_group_members_lead_id", table_name="lead_group_members")
    op.drop_index("ix_lead_group_members_group_id", table_name="lead_group_members")
    op.drop_table("lead_group_members")
    op.drop_index("ix_lead_groups_user_id", table_name="lead_groups")
    op.drop_table("lead_groups")
