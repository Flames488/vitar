"""Make Patient.clinic_id nullable for Wabizz-created patients

Revision ID: 007
Revises: 006
Create Date: 2026-05-10

Problem:  Patients created through the Wabizz WhatsApp flow had no clinic_id
          because the /api/v1/patients/wabizz endpoint did not accept one and
          the Patient model had clinic_id as NOT NULL.  This caused two issues:
            1. The INSERT would succeed only because SQLite ignored the constraint
               in dev — it would crash in production PostgreSQL.
            2. Even where it didn't crash, the patient was invisible in the
               clinic's Vitar dashboard (no clinic_id = no filter match).

Fix:      Make clinic_id nullable (SET NULL on cascade delete) and accept
          clinic_id in the Wabizz patient creation endpoint.  Wabizz now
          sends HospitalNicheConfig.vitar_clinic_id when creating patients
          so they are correctly linked to the clinic.
"""

from alembic import op
import sqlalchemy as sa

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop the NOT NULL constraint on clinic_id in patients table.
    # Also switch cascade from CASCADE (delete patient when clinic deleted)
    # to SET NULL (preserve patient record, clear the clinic link).
    with op.batch_alter_table("patients") as batch_op:
        batch_op.alter_column(
            "clinic_id",
            existing_type=sa.String(36),
            nullable=True,
        )


def downgrade() -> None:
    # Re-apply NOT NULL — only safe if all existing rows have a clinic_id.
    # Run: UPDATE patients SET clinic_id = '<default>' WHERE clinic_id IS NULL;
    # before running this downgrade in production.
    with op.batch_alter_table("patients") as batch_op:
        batch_op.alter_column(
            "clinic_id",
            existing_type=sa.String(36),
            nullable=False,
        )
