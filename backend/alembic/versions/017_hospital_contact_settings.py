"""Add Hospital Contact Settings; un-gate doctor_details_enabled

Doctor contact visibility (email/phone/WhatsApp) is no longer a paid
feature — it's now controlled entirely by the hospital, via two new
Clinic-level toggles:

  - contact_whatsapp_enabled  (default True  = "Enable Both" out of the box)
  - contact_call_enabled      (default True)

Together these four combinations (both / whatsapp-only / call-only /
neither) satisfy the "Hospital Contact Settings" requirement without
adding a separate enum column.

`doctors.doctor_details_enabled` previously defaulted to False because it
gated a paid feature most trial clinics never got around to opting into.
Now that it's just "show this doctor's contact info publicly" with no
billing implication, we flip the default to True going forward AND
backfill existing doctors to True, so hospitals don't lose functionality
they already had (or silently gain a step they don't expect) the moment
this ships.

Revision ID: 017_hospital_contact_settings
Revises: 016_merge_doctor_heads
"""
from alembic import op
import sqlalchemy as sa

revision = "017_hospital_contact_settings"
down_revision = "016_merge_doctor_heads"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_cols = {c["name"] for c in inspector.get_columns("clinics")}

    if "contact_whatsapp_enabled" not in existing_cols:
        op.add_column(
            "clinics",
            sa.Column(
                "contact_whatsapp_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            ),
        )

    if "contact_call_enabled" not in existing_cols:
        op.add_column(
            "clinics",
            sa.Column(
                "contact_call_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            ),
        )

    # Un-gate doctor_details_enabled: change the column default for future
    # inserts, and backfill existing rows so this reads as "on" everywhere,
    # matching the new no-longer-a-paid-feature behavior.
    op.alter_column(
        "doctors",
        "doctor_details_enabled",
        server_default=sa.true(),
    )
    op.execute("UPDATE doctors SET doctor_details_enabled = true WHERE doctor_details_enabled = false")


def downgrade():
    op.drop_column("clinics", "contact_call_enabled")
    op.drop_column("clinics", "contact_whatsapp_enabled")
    op.alter_column(
        "doctors",
        "doctor_details_enabled",
        server_default=sa.false(),
    )
