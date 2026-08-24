"""031_pending_payment_months

Lets a clinic prepay several months of a plan in one upfront bank
transfer (e.g. pay once now to cover Sep-Dec) instead of one billing
period at a time. Adds `months` to pending_subscription_payments —
how many consecutive periods that single payment covers.

Revision ID: 031_pending_payment_months
Revises: 030_user_marketing_opt_in
Create Date: 2026-08-24
"""
from alembic import op
import sqlalchemy as sa

revision = "031_pending_payment_months"
down_revision = "030_user_marketing_opt_in"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "pending_subscription_payments",
        sa.Column("months", sa.Integer(), nullable=False, server_default="1"),
    )


def downgrade():
    op.drop_column("pending_subscription_payments", "months")
