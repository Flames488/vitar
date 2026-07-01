"""011_push_subscriptions

Adds the push_subscriptions table for Web Push (PWA appointment reminders).

Revision ID: 011_push_subscriptions
Revises: 010_add_superadmin
Create Date: 2026-06-23
"""
from alembic import op
import sqlalchemy as sa

revision = "011_push_subscriptions"
down_revision = "010_add_superadmin"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "push_subscriptions",
        sa.Column("id", sa.String(36), primary_key=True,
                  server_default=sa.text("gen_random_uuid()::text")),
        sa.Column("clinic_id", sa.String(36),
                  sa.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(36),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("endpoint", sa.Text, nullable=False, unique=True),
        sa.Column("p256dh", sa.Text, nullable=False),
        sa.Column("auth", sa.String(64), nullable=False),
        sa.Column("user_agent", sa.String(512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("NOW()"), onupdate=sa.text("NOW()"), nullable=False),
    )
    op.create_index("ix_push_subscriptions_clinic_id", "push_subscriptions", ["clinic_id"])
    op.create_index("ix_push_subscriptions_user_id", "push_subscriptions", ["user_id"])


def downgrade():
    op.drop_index("ix_push_subscriptions_user_id", "push_subscriptions")
    op.drop_index("ix_push_subscriptions_clinic_id", "push_subscriptions")
    op.drop_table("push_subscriptions")
