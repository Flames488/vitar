"""022_referrals

Refer & Earn: a persistent, unique referral_code on clinics, and a new
referrals table tracking each referred signup's lifecycle (signed_up ->
paid -> credited, or expired for abuse). No existing billing table
(subscriptions, subscription_payments, pending_subscription_payments) is
touched structurally.

Revision ID: 022_referrals
Revises: 021_clinics_owner_index
Create Date: 2026-08-02
"""
from alembic import op
import sqlalchemy as sa

revision = "022_referrals"
down_revision = "021_clinics_owner_index"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("clinics", sa.Column("referral_code", sa.String(20), nullable=True))
    op.create_index("ix_clinics_referral_code", "clinics", ["referral_code"], unique=True)

    op.create_table(
        "referrals",
        sa.Column("id", sa.String(36), primary_key=True,
                  server_default=sa.text("gen_random_uuid()::text")),
        sa.Column("referrer_clinic_id", sa.String(36),
                  sa.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False),
        sa.Column("referred_clinic_id", sa.String(36),
                  sa.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("referral_code", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="signed_up"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("paid_at", sa.DateTime(), nullable=True),
        sa.Column("credited_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_referrals_referrer_clinic_id", "referrals", ["referrer_clinic_id"])
    # referred_clinic_id already gets a unique index automatically from the
    # column's unique=True above — no separate index needed.
    op.create_index("ix_referrals_referrer_status", "referrals", ["referrer_clinic_id", "status"])


def downgrade():
    op.drop_index("ix_referrals_referrer_status", "referrals")
    op.drop_index("ix_referrals_referrer_clinic_id", "referrals")
    op.drop_table("referrals")
    op.drop_index("ix_clinics_referral_code", "clinics")
    op.drop_column("clinics", "referral_code")
