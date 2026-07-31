"""Add doctor_details_enabled column to doctors

Backs the new "Doctor Details" feature (email / contact number / "Talk with
a Doctor" WhatsApp CTA shown on the public booking page). This is a paid
feature — free for clinics on an active trial, gated behind a paid plan
once the trial ends (see app.services.trial_guard.has_paid_feature_access).

Revision ID: 015_doctor_details_enabled
Revises: 014_patient_phone_unique
"""
from alembic import op
import sqlalchemy as sa

revision = "015_doctor_details_enabled"
down_revision = "014_patient_phone_unique"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "doctors",
        sa.Column(
            "doctor_details_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade():
    op.drop_column("doctors", "doctor_details_enabled")
