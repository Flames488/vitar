"""Add is_active column to patients table

Fix 8: The by-phone endpoint queries Patient.is_active == True but the
column was absent from both the SQLAlchemy model and the database schema,
causing a runtime AttributeError on any call to GET /patients/by-phone/{phone}.

This migration adds the column with a server-side default of true so all
existing patient rows become active, and adds a partial index to support
the is_active filter efficiently.

Revision ID: 008_patient_is_active
Revises: 007
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision = '008_patient_is_active'
down_revision = '007'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add is_active column — server_default='true' backfills all existing rows
    op.add_column(
        'patients',
        sa.Column(
            'is_active',
            sa.Boolean(),
            nullable=False,
            server_default='true',
        )
    )

    # Partial index: only index active patients (the common case in all queries)
    # This matches the filter pattern in GET /patients/by-phone/{phone} and
    # POST /patients duplicate-check: WHERE ... AND is_active = true
    op.create_index(
        'ix_patient_is_active',
        'patients',
        ['is_active'],
        postgresql_where=text('is_active = true'),
    )

    # Standalone phone index — allows GET /patients/by-phone/{phone} to use an
    # index even when clinic_id is not in the WHERE clause. The existing composite
    # index ix_patient_clinic_phone (clinic_id, phone) cannot be used for
    # phone-only lookups (Fix 3 from audit report).
    op.create_index(
        'ix_patient_phone_active',
        'patients',
        ['phone'],
        postgresql_where=text('is_active = true'),
    )


def downgrade() -> None:
    op.drop_index('ix_patient_phone_active', table_name='patients')
    op.drop_index('ix_patient_is_active', table_name='patients')
    op.drop_column('patients', 'is_active')
