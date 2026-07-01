"""012_pending_sub_payments

Adds the pending_subscription_payments table powering the automated
Paystack smart-payment flow (Vitar Billing — auto-activation on webhook).

Revision ID: 012_pending_sub_payments
Revises: 011_push_subscriptions
Create Date: 2026-06-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "012_pending_sub_payments"
down_revision = "011_push_subscriptions"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "pending_subscription_payments",
        sa.Column("id", sa.String(36), primary_key=True,
                  server_default=sa.text("gen_random_uuid()::text")),
        sa.Column("clinic_id", sa.String(36),
                  sa.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False),
        sa.Column("subscription_plan", sa.String(20), nullable=False),
        sa.Column("billing_cycle", sa.String(20), server_default="monthly"),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(10), server_default="NGN"),
        sa.Column("paystack_reference", sa.String(255), nullable=False, unique=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("paid_at", sa.DateTime(), nullable=True),
        sa.Column("provider_response", postgresql.JSONB(), server_default="{}"),
    )
    op.create_index("ix_pendingsubpay_clinic_id", "pending_subscription_payments", ["clinic_id"])
    op.create_index("ix_pendingsubpay_reference", "pending_subscription_payments", ["paystack_reference"])
    op.create_index("ix_pendingpay_status_expires", "pending_subscription_payments", ["status", "expires_at"])


def downgrade():
    op.drop_index("ix_pendingpay_status_expires", "pending_subscription_payments")
    op.drop_index("ix_pendingsubpay_reference", "pending_subscription_payments")
    op.drop_index("ix_pendingsubpay_clinic_id", "pending_subscription_payments")
    op.drop_table("pending_subscription_payments")
