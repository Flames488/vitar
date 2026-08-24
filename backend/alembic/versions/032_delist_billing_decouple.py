"""032_delist_billing_decouple

Public clinic directory visibility (Clinic.is_listed) used to be unset
by expire_trial_subscriptions/expire_paid_subscriptions whenever a
clinic's trial or subscription lapsed — so any active, working clinic
whose trial ran out unpaid silently dropped out of patient search, even
though nothing else about the clinic changed (it could still be taking
bookings via its QR code/direct link the whole time). That behavior is
now removed from those tasks (see workers/tasks.py) — is_listed only
tracks onboarding completion / admin enable-disable going forward.

This migration backfills is_listed=true for every clinic this new rule
now covers but the old billing-driven unlisting left at false: active,
onboarding-complete clinics. One-time catch-up; ongoing changes are
handled by the hooks in onboarding.py / billing_service.py /
admin_clinics.py, not by re-running this migration.

Revision ID: 032_delist_billing_decouple
Revises: 031_installment_plans
Create Date: 2026-08-20

Originally written as 030_delist_billing_decouple against
029_notification_pushed_flag, same as 030_user_marketing_opt_in
(-> 031_installment_plans) — both branches added a "030" independently.
Renumbered on top of both to keep a single head instead of a merge
migration.
"""
from alembic import op

revision = "032_delist_billing_decouple"
down_revision = "031_installment_plans"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        UPDATE clinics
        SET is_listed = true
        WHERE is_listed = false
          AND is_active = true
          AND onboarding_completed = true
          AND slug IS NOT NULL
    """)


def downgrade():
    # Not reversible — we no longer track which rows this flipped
    # (vs. clinics that were already true beforehand), and the prior
    # billing-driven unlisting behavior it replaces is gone from the
    # codebase too.
    pass
