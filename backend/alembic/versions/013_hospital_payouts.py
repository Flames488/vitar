"""013_hospital_payouts

Adds hospital bank account onboarding and payout tracking for patient
booking payments routed through Vitar's main Paystack balance.

Revision ID: 013_hospital_payouts
Revises: 012_pending_sub_payments
Create Date: 2026-07-07
"""
from alembic import op
import sqlalchemy as sa


revision = "013_hospital_payouts"
down_revision = "012_pending_sub_payments"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "hospital_bank_accounts",
        sa.Column("id", sa.String(36), primary_key=True, server_default=sa.text("gen_random_uuid()::text")),
        sa.Column("hospital_id", sa.String(36), sa.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False),
        sa.Column("account_number", sa.String(20), nullable=False),
        sa.Column("bank_code", sa.String(20), nullable=False),
        sa.Column("bank_name", sa.String(100), nullable=False),
        sa.Column("account_name", sa.String(255), nullable=False),
        sa.Column("paystack_recipient_code", sa.String(100), nullable=True),
        sa.Column("verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )
    op.create_index("ix_hospital_bank_accounts_hospital_id", "hospital_bank_accounts", ["hospital_id"])
    op.create_index("ix_hospital_bank_accounts_active", "hospital_bank_accounts", ["active"])
    op.create_index("ix_hospital_bank_active", "hospital_bank_accounts", ["hospital_id", "active"])

    op.create_table(
        "payouts",
        sa.Column("id", sa.String(36), primary_key=True, server_default=sa.text("gen_random_uuid()::text")),
        sa.Column("appointment_id", sa.String(36), sa.ForeignKey("appointments.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("hospital_id", sa.String(36), sa.ForeignKey("clinics.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending_payout"),
        sa.Column("paystack_transfer_code", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_unique_constraint("uq_payouts_appointment_id", "payouts", ["appointment_id"])
    op.create_index("ix_payouts_hospital_id", "payouts", ["hospital_id"])
    op.create_index("ix_payouts_status", "payouts", ["status"])
    op.create_index("ix_payouts_paystack_transfer_code", "payouts", ["paystack_transfer_code"])
    op.create_index("ix_payout_status_created", "payouts", ["status", "created_at"])


def downgrade():
    op.drop_index("ix_payout_status_created", "payouts")
    op.drop_index("ix_payouts_paystack_transfer_code", "payouts")
    op.drop_index("ix_payouts_status", "payouts")
    op.drop_index("ix_payouts_hospital_id", "payouts")
    op.drop_constraint("uq_payouts_appointment_id", "payouts", type_="unique")
    op.drop_table("payouts")

    op.drop_index("ix_hospital_bank_active", "hospital_bank_accounts")
    op.drop_index("ix_hospital_bank_accounts_active", "hospital_bank_accounts")
    op.drop_index("ix_hospital_bank_accounts_hospital_id", "hospital_bank_accounts")
    op.drop_table("hospital_bank_accounts")
