"""Add qr_code_path to clinics for QR onboarding feature

Revision ID: 009_clinic_qr_code
Revises: 008_patient_is_active
Create Date: 2026-06-16 00:00:00

Notes:
  - clinics.slug already exists (unique, indexed) from 001_initial — reused
    as-is for the public portal URL, no change needed.
  - qr_code_path is nullable: existing clinics get a NULL value until the
    backfill script (qr_backfill.py) runs and generates a QR for each one.
  - This migration ONLY adds a column. No backfill logic here — backfill is
    a separate, re-runnable script so it can be safely retried if QR
    generation fails partway through (e.g. disk full, bad logo url).
"""
from alembic import op
import sqlalchemy as sa

revision = '009_clinic_qr_code'
down_revision = '008_patient_is_active'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('clinics', sa.Column('qr_code_path', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('clinics', 'qr_code_path')
