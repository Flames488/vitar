"""Add missing index on clinics.owner_id

get_current_clinic() filters Clinic.owner_id == current_user.id on every
single authenticated request across the whole API. This column had a
ForeignKey but no index since the initial migration.

Revision ID: 021_clinics_owner_index
Revises: 020_uq_doctor_slot
"""
from alembic import op
from sqlalchemy import text

revision = "021_clinics_owner_index"
down_revision = "020_uq_doctor_slot"
branch_labels = None
depends_on = None


def upgrade():
    with op.get_context().autocommit_block():
        op.execute(text(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_clinics_owner_id "
            "ON clinics (owner_id)"
        ))


def downgrade():
    with op.get_context().autocommit_block():
        op.execute(text("DROP INDEX CONCURRENTLY IF EXISTS ix_clinics_owner_id"))
