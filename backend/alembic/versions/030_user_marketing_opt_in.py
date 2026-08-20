"""Add users.marketing_opt_in for the weekly feature-spotlight email

Defaults to true (existing registered users are opted in), with a public
unsubscribe link in every spotlight email flipping it to false. Separate
from is_active/is_verified on purpose — this only gates the marketing
spotlight, not transactional email (welcome, receipts, reminders, etc.),
which should never be suppressible.

Revision ID: 030_user_marketing_opt_in
Revises: 029_notification_pushed_flag
"""
from alembic import op
import sqlalchemy as sa

revision = "030_user_marketing_opt_in"
down_revision = "029_notification_pushed_flag"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "users",
        sa.Column("marketing_opt_in", sa.Boolean(), nullable=False, server_default="true"),
    )


def downgrade():
    op.drop_column("users", "marketing_opt_in")
