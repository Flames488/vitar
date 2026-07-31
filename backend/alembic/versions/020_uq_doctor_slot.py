"""Add real double-booking backstop: unique (doctor_id, scheduled_at)

The application-level SELECT ... FOR UPDATE conflict check only locks rows
that already exist. For a slot's first booking there's nothing to lock, so
two concurrent requests can both pass the check and both INSERT — a genuine
double-booking race. booking.py already has an IntegrityError handler that
assumes a "uq_doctor_slot" unique constraint exists and turns a violation into
a clean 409 — but the constraint itself was never created. This migration
adds it.

Excludes CANCELLED/NO_SHOW so a doctor can have any number of those at the
same slot over time. Uses CREATE INDEX CONCURRENTLY (outside the migration's
transaction, via autocommit_block) so this doesn't lock the appointments
table during deploy.

Any pre-existing duplicate active bookings for the same doctor/slot (which
could only exist because of the exact race this migration fixes) are resolved
first by keeping the earliest one and cancelling the rest, so the index
creation itself can't fail on live data.

Revision ID: 020_uq_doctor_slot
Revises: 019_notif_all_channels
"""
from alembic import op
from sqlalchemy import text

revision = "020_uq_doctor_slot"
down_revision = "019_notif_all_channels"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    conn.execute(text("""
        WITH dupes AS (
            SELECT id, ROW_NUMBER() OVER (
                PARTITION BY doctor_id, scheduled_at
                ORDER BY created_at ASC, id ASC
            ) AS rn
            FROM appointments
            WHERE status NOT IN ('CANCELLED', 'NO_SHOW')
        )
        UPDATE appointments
        SET status = 'CANCELLED',
            cancelled_reason = 'Duplicate booking auto-resolved by uq_doctor_slot migration',
            cancelled_at = NOW()
        WHERE id IN (SELECT id FROM dupes WHERE rn > 1)
    """))

    with op.get_context().autocommit_block():
        op.execute(text(
            "CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS uq_doctor_slot "
            "ON appointments (doctor_id, scheduled_at) "
            "WHERE status NOT IN ('CANCELLED', 'NO_SHOW')"
        ))


def downgrade():
    with op.get_context().autocommit_block():
        op.execute(text("DROP INDEX CONCURRENTLY IF EXISTS uq_doctor_slot"))
