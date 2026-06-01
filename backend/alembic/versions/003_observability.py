"""Enable pg_stat_statements + additional patient/notification indexes

Revision ID: 003_observability
Revises: 002_hardening
Create Date: 2026-04-20 00:00:00

Changes:
  - Enable pg_stat_statements extension for slow query tracking via Postgres
  - Add ix_patient_clinic_name for patient search performance
  - Add ix_notification_scheduled_status for fire_pending_reminders query
  - Add ix_appointment_patient for patient appointment history lookups
"""
from alembic import op
import sqlalchemy as sa


revision = '003_observability'
down_revision = '002_hardening'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── pg_stat_statements — tracked by Postgres, queried for slow query reports ──
    # Requires shared_preload_libraries='pg_stat_statements' in postgres.conf.
    # The docker-compose command already sets -c shared_preload_libraries for pg 16.
    # This CREATE EXTENSION is idempotent.
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_stat_statements")

    # ── patients: clinic + name for fast ilike search ─────────────────────────
    # list_patients endpoint filters by clinic_id then sorts/searches by full_name.
    op.create_index(
        'ix_patient_clinic_name',
        'patients',
        ['clinic_id', 'full_name'],
    )

    # ── patients: clinic + phone for duplicate-check upsert ───────────────────
    # create_patient queries (clinic_id, phone) on every booking.
    # Already created by 001_initial as ix_patient_clinic_phone.

    # ── notifications: scheduled_for + status covers fire_pending_reminders ───
    # The beat task queries: status=PENDING AND scheduled_for <= now+6min
    # with a LIMIT 200 + FOR UPDATE SKIP LOCKED. This index makes that fast.
    op.create_index(
        'ix_notification_scheduled_status',
        'notifications',
        ['scheduled_for', 'status'],
    )

    # ── appointments: patient_id for appointment history lookups ──────────────
    # get_patient endpoint joins appointment history per patient.
    op.create_index(
        'ix_appointment_patient',
        'appointments',
        ['patient_id', 'scheduled_at'],
    )

    # ── appointments: doctor_id + date for booking slot queries ───────────────
    # Public booking page checks slot availability per doctor per day.
    # Already created by 001_initial as ix_appointment_doctor_time.


def downgrade() -> None:
    op.drop_index('ix_appointment_patient', table_name='appointments')
    op.drop_index('ix_notification_scheduled_status', table_name='notifications')
    op.drop_index('ix_patient_clinic_name', table_name='patients')
    # Do not drop pg_stat_statements — it may be used by other tools
