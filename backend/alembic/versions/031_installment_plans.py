"""031_installment_plans

Adds subscription_installment_plans, letting a clinic pay for an annual
subscription in several smaller bank transfers spread across months
instead of one lump sum. Also tags pending_subscription_payments with
which installment plan/number they belong to, when applicable.

Revision ID: 031_installment_plans
Revises: 030_user_marketing_opt_in
Create Date: 2026-08-24
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "031_installment_plans"
down_revision = "030_user_marketing_opt_in"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "subscription_installment_plans",
        sa.Column("id", sa.String(36), primary_key=True,
                  server_default=sa.text("gen_random_uuid()::text")),
        sa.Column("clinic_id", sa.String(36),
                  sa.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False),
        sa.Column("subscription_plan", sa.String(20), nullable=False),
        sa.Column("billing_cycle", sa.String(20), server_default="annual"),
        sa.Column("total_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(10), server_default="NGN"),
        sa.Column("total_installments", sa.Integer(), nullable=False),
        sa.Column("installments_paid", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("extra_data", postgresql.JSONB(), server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_installplan_clinic_id", "subscription_installment_plans", ["clinic_id"])
    op.create_index("ix_installplan_status", "subscription_installment_plans", ["status"])
    op.create_index("ix_installplan_clinic_status", "subscription_installment_plans", ["clinic_id", "status"])

    op.add_column(
        "pending_subscription_payments",
        sa.Column("installment_plan_id", sa.String(36),
                  sa.ForeignKey("subscription_installment_plans.id", ondelete="CASCADE"), nullable=True),
    )
    op.add_column(
        "pending_subscription_payments",
        sa.Column("installment_number", sa.Integer(), nullable=True),
    )
    op.create_index("ix_pendingsubpay_installment_plan_id", "pending_subscription_payments", ["installment_plan_id"])


def downgrade():
    op.drop_index("ix_pendingsubpay_installment_plan_id", "pending_subscription_payments")
    op.drop_column("pending_subscription_payments", "installment_number")
    op.drop_column("pending_subscription_payments", "installment_plan_id")

    op.drop_index("ix_installplan_clinic_status", "subscription_installment_plans")
    op.drop_index("ix_installplan_status", "subscription_installment_plans")
    op.drop_index("ix_installplan_clinic_id", "subscription_installment_plans")
    op.drop_table("subscription_installment_plans")
