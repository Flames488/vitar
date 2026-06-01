"""Hardening: composite indexes, retry_count + failed_at on payments

Revision ID: 002_hardening
Revises: 001_initial
Create Date: 2026-04-19 00:00:00

Changes:
  - subscription_payments: add retry_count, failed_at, ix_subpayment_status_created
  - appointments: add ix_appointment_clinic_status_time, ix_appointment_status_time
  - notifications: add ix_notification_status_retry, ix_notification_appt_channel
"""
from alembic import op
import sqlalchemy as sa

revision = '002_hardening'
down_revision = '001_initial'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── subscription_payments ──────────────────────────────────────────────────
    op.add_column(
        'subscription_payments',
        sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'),
    )
    op.add_column(
        'subscription_payments',
        sa.Column('failed_at', sa.DateTime(), nullable=True),
    )
    op.create_index(
        'ix_subpayment_status_created',
        'subscription_payments',
        ['status', 'created_at'],
    )

    # ── appointments ──────────────────────────────────────────────────────────
    # Most common dashboard query: clinic filtered by status + time range
    op.create_index(
        'ix_appointment_clinic_status_time',
        'appointments',
        ['clinic_id', 'status', 'scheduled_at'],
    )
    # Celery beat hourly risk refresh: confirmed appointments by time
    op.create_index(
        'ix_appointment_status_time',
        'appointments',
        ['status', 'scheduled_at'],
    )

    # ── notifications ─────────────────────────────────────────────────────────
    # retry_failed_notifications task lookups
    op.create_index(
        'ix_notification_status_retry',
        'notifications',
        ['status', 'retry_count'],
    )
    # appointment_id + channel lookups from task handlers
    op.create_index(
        'ix_notification_appt_channel',
        'notifications',
        ['appointment_id', 'channel'],
    )


def downgrade() -> None:
    op.drop_index('ix_notification_appt_channel', table_name='notifications')
    op.drop_index('ix_notification_status_retry', table_name='notifications')
    op.drop_index('ix_appointment_status_time', table_name='appointments')
    op.drop_index('ix_appointment_clinic_status_time', table_name='appointments')
    op.drop_index('ix_subpayment_status_created', table_name='subscription_payments')
    op.drop_column('subscription_payments', 'failed_at')
    op.drop_column('subscription_payments', 'retry_count')
