"""clinics.patient_payment_enabled — align default to on, make NOT NULL

The column shipped in 001_initial with server_default='false' and no NOT
NULL, while the ORM model set default=True. Result: clinics created via
the ORM got True, but the column stayed nullable and any NULL / raw-insert
row read as "free booking" in booking.py. This aligns it with the
documented "on for every clinic" intent and with contact_*_enabled:
NOT NULL, server_default true. Only NULLs are backfilled — a clinic that
explicitly chose False keeps it.

Revision ID: 034_patient_payment_default
Revises: 033_lead_area
"""
from alembic import op
import sqlalchemy as sa

revision = "034_patient_payment_default"
down_revision = "033_lead_area"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "UPDATE clinics SET patient_payment_enabled = true "
        "WHERE patient_payment_enabled IS NULL"
    )
    op.alter_column(
        "clinics",
        "patient_payment_enabled",
        existing_type=sa.Boolean(),
        nullable=False,
        server_default=sa.text("true"),
    )


def downgrade():
    op.alter_column(
        "clinics",
        "patient_payment_enabled",
        existing_type=sa.Boolean(),
        nullable=True,
        server_default=sa.text("false"),
    )
