"""Fix patients.clinic_id FK to actually SET NULL on clinic delete

Migration 007 (patient_clinic_id_nullable) made patients.clinic_id nullable
so Wabizz-created patients could exist without a clinic link, and its
docstring claimed the delete rule was switched from CASCADE to SET NULL —
but it only ran alter_column(nullable=True). The column-level ondelete
never changed: it was declared "CASCADE" in 001_initial.py and stayed that
way in the live schema, even though app/models/models.py's Patient.clinic_id
has always declared ondelete="SET NULL". If a clinic is ever deleted, the
real constraint would CASCADE and silently destroy every one of its
patients' records (including Wabizz-created ones) instead of preserving
them with clinic_id cleared, as originally intended and as the ORM model
already promises.

Revision ID: 025_patient_clinic_fk_set_null
Revises: 024_clinic_directory
"""
from alembic import op
from sqlalchemy import text

revision = "025_patient_clinic_fk_set_null"
down_revision = "024_clinic_directory"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(text("ALTER TABLE patients DROP CONSTRAINT IF EXISTS patients_clinic_id_fkey"))
    op.execute(text(
        "ALTER TABLE patients ADD CONSTRAINT patients_clinic_id_fkey "
        "FOREIGN KEY (clinic_id) REFERENCES clinics(id) ON DELETE SET NULL"
    ))


def downgrade():
    op.execute(text("ALTER TABLE patients DROP CONSTRAINT IF EXISTS patients_clinic_id_fkey"))
    op.execute(text(
        "ALTER TABLE patients ADD CONSTRAINT patients_clinic_id_fkey "
        "FOREIGN KEY (clinic_id) REFERENCES clinics(id) ON DELETE CASCADE"
    ))
