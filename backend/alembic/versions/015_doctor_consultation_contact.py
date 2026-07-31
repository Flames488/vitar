"""015_doctor_consultation_contact

Adds Doctor.consultation_contact_enabled — a per-doctor opt-in flag that
controls whether their email/phone and a "Talk with a Doctor" option are
shown to patients on the public booking page. Access to turning this on is
separately gated in the API by app.services.trial_guard.has_doctor_contact_access
(free during trial, paid-plan-only after trial expiry) — no schema changes
needed for that part since it's derived from the existing Subscription/Clinic
trial columns.

Revision ID: 015_doctor_consultation_contact
Revises: 014_patient_phone_unique
Create Date: 2026-07-29
"""
from alembic import op
import sqlalchemy as sa


revision = "015_doctor_consultation_contact"
down_revision = "014_patient_phone_unique"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "doctors",
        sa.Column(
            "consultation_contact_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade():
    op.drop_column("doctors", "consultation_contact_enabled")
