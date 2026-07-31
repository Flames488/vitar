"""Add partial unique index enforcing one active bank account per hospital

Fixes a race in hospital_bank_accounts.py: create_bank_account and
replace_bank_account both did a SELECT (is there an active account?) then an
INSERT, with no row lock and no DB constraint backing the "only one active
account per hospital" rule. Two concurrent requests (e.g. a double-submit)
could each pass the SELECT before either committed, leaving two active rows;
payout sending then picks one non-deterministically (ORDER BY created_at DESC
LIMIT 1), risking a transfer to a stale/wrong account.

Revision ID: 018_bank_account_unique
Revises: 017_hospital_contact_settings
"""
from alembic import op
import sqlalchemy as sa

revision = "018_bank_account_unique"
down_revision = "017_hospital_contact_settings"
branch_labels = None
depends_on = None


def upgrade():
    # ── Step 1: dedupe — keep only the newest active row per hospital ──
    op.execute("""
        WITH ranked AS (
            SELECT id, hospital_id,
                   ROW_NUMBER() OVER (
                       PARTITION BY hospital_id
                       ORDER BY created_at DESC
                   ) AS rn
            FROM hospital_bank_accounts
            WHERE active = true
        )
        UPDATE hospital_bank_accounts
        SET active = false
        WHERE id IN (SELECT id FROM ranked WHERE rn > 1);
    """)

    # ── Step 2: partial unique index — the conflict target that makes the
    # "one active account per hospital" rule a real DB guarantee, not just
    # an application-level check-then-act race ──
    op.create_index(
        "uq_hospital_bank_account_active",
        "hospital_bank_accounts",
        ["hospital_id"],
        unique=True,
        postgresql_where=sa.text("active = true"),
    )


def downgrade():
    op.drop_index("uq_hospital_bank_account_active", table_name="hospital_bank_accounts")
