"""023_patient_registrations

eRegistration Phase 1: a patient_registrations table capturing personal,
address, emergency-contact, optional health info, and consent, plus a
registration_token for unauthenticated patient self-service (same shape
as Appointment.confirmation_token/cancel_token — there is no patient
login in Vitar to hang a session off of). One row per (patient_id,
clinic_id): a draft is upserted in place and becomes 'submitted' rather
than a second row being created, so the "no duplicate submitted
registration" rule is just the unique constraint.

No existing table (patients, clinics, subscriptions) is touched.

Revision ID: 023_patient_registrations
Revises: 022_referrals
Create Date: 2026-08-03
"""
from alembic import op
import sqlalchemy as sa

revision = "023_patient_registrations"
down_revision = "022_referrals"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "patient_registrations",
        sa.Column("id", sa.String(36), primary_key=True,
                  server_default=sa.text("gen_random_uuid()::text")),
        sa.Column("patient_id", sa.String(36),
                  sa.ForeignKey("patients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("clinic_id", sa.String(36),
                  sa.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),

        # Unauthenticated patient self-service token — see confirmation_token/
        # cancel_token on appointments for the existing precedent this follows.
        sa.Column("registration_token", sa.String(100), nullable=False),

        # Personal info
        sa.Column("full_name", sa.String(255), nullable=True),
        sa.Column("phone_number", sa.String(20), nullable=True),
        sa.Column("date_of_birth", sa.DateTime(), nullable=True),
        sa.Column("gender", sa.String(10), nullable=True),

        # Address
        sa.Column("state", sa.String(100), nullable=True),
        sa.Column("city", sa.String(100), nullable=True),
        sa.Column("residential_address", sa.Text(), nullable=True),

        # Emergency contact
        sa.Column("emergency_contact_name", sa.String(255), nullable=True),
        sa.Column("emergency_contact_relationship", sa.String(100), nullable=True),
        sa.Column("emergency_contact_phone", sa.String(20), nullable=True),

        # Optional health info — plain columns, no encryption-at-rest precedent
        # exists elsewhere in this schema; revisit only if a compliance review
        # requires it (see Phase 1 spec discussion).
        sa.Column("blood_group", sa.String(20), nullable=True),
        sa.Column("genotype", sa.String(20), nullable=True),
        sa.Column("allergies", sa.Text(), nullable=True),
        sa.Column("existing_conditions", sa.Text(), nullable=True),
        sa.Column("current_medications", sa.Text(), nullable=True),

        # Consent
        sa.Column("consent_given", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("consent_given_at", sa.DateTime(timezone=True), nullable=True),

        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )

    # One row per (patient, clinic) — upsert draft->submitted in place,
    # and this is what makes "no duplicate submitted registration" hold.
    op.create_unique_constraint(
        "uq_patient_registrations_patient_clinic", "patient_registrations", ["patient_id", "clinic_id"]
    )
    op.create_index(
        "ix_patient_registrations_registration_token", "patient_registrations", ["registration_token"], unique=True
    )
    op.create_index("ix_patient_registrations_clinic_id", "patient_registrations", ["clinic_id"])


def downgrade():
    op.drop_index("ix_patient_registrations_clinic_id", "patient_registrations")
    op.drop_index("ix_patient_registrations_registration_token", "patient_registrations")
    op.drop_constraint("uq_patient_registrations_patient_clinic", "patient_registrations", type_="unique")
    op.drop_table("patient_registrations")
