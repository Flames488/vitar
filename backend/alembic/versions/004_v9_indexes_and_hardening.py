"""v9 performance indexes and DB hardening

Revision ID: 004
Revises: 003
Create Date: 2026-04-20

Adds indexes identified as missing for frequent query patterns. These run
inside Alembic's normal startup transaction, so they do not use
CREATE INDEX CONCURRENTLY.
"""
from alembic import op

revision = "004"
down_revision = "003_observability"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index(
        "idx_appointments_clinic_status",
        "appointments",
        ["clinic_id", "status"],
        if_not_exists=True,
    )
    op.create_index(
        "idx_appointments_scheduled_at",
        "appointments",
        ["scheduled_at"],
        if_not_exists=True,
    )
    op.create_index(
        "idx_appointments_patient_id",
        "appointments",
        ["patient_id"],
        if_not_exists=True,
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_appointments_risk_score
        ON appointments (no_show_risk_score)
        WHERE no_show_risk_score IS NOT NULL
        """
    )

    op.create_index(
        "idx_patients_clinic_id",
        "patients",
        ["clinic_id"],
        if_not_exists=True,
    )
    op.create_index(
        "idx_patients_phone",
        "patients",
        ["phone"],
        if_not_exists=True,
    )

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_notifications_pending_scheduled_for
        ON notifications (scheduled_for)
        WHERE status = 'pending'
        """
    )


def downgrade():
    op.drop_index("idx_appointments_clinic_status", table_name="appointments", if_exists=True)
    op.drop_index("idx_appointments_scheduled_at", table_name="appointments", if_exists=True)
    op.drop_index("idx_appointments_patient_id", table_name="appointments", if_exists=True)
    op.execute("DROP INDEX IF EXISTS idx_appointments_risk_score")
    op.drop_index("idx_patients_clinic_id", table_name="patients", if_exists=True)
    op.drop_index("idx_patients_phone", table_name="patients", if_exists=True)
    op.execute("DROP INDEX IF EXISTS idx_notifications_pending_scheduled_for")
