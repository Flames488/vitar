"""merge doctor consultation contact and doctor details heads

Two migrations were both created off 014_patient_phone_unique as
down_revision, instead of one being chained after the other:

  015_doctor_consultation_contact  (adds consultation_contact_enabled)
  015_doctor_details_enabled       (adds doctor_details_enabled)

That leaves two unmerged heads. Whichever one was deployed first got
stamped as HEAD; the other was never actually run by `alembic upgrade
head` on the server, even though its column is required by the model
and endpoint code. This merge revision unifies both branches into a
single head so future `alembic upgrade head` runs pick up whichever of
the two columns is still missing on a given environment (e.g. a fresh
or out-of-sync dev/staging database) instead of silently skipping it.

No schema changes here - both add_column operations already exist in
their respective revisions. This is a pure merge point.

Revision ID: 016_merge_doctor_heads
Revises: 015_doctor_consultation_contact, 015_doctor_details_enabled
Create Date: 2026-07-29
"""
from alembic import op
import sqlalchemy as sa


revision = "016_merge_doctor_heads"
down_revision = ("015_doctor_consultation_contact", "015_doctor_details_enabled")
branch_labels = None
depends_on = None


def upgrade():
    # Pure merge point. But guard both columns defensively in case this
    # runs against an environment where alembic_version was manually
    # stamped past one branch without the column actually existing
    # (e.g. a copied/restored database) or where a column was added
    # by hand outside of alembic, as happened on production.
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_cols = {c["name"] for c in inspector.get_columns("doctors")}

    if "consultation_contact_enabled" not in existing_cols:
        op.add_column(
            "doctors",
            sa.Column(
                "consultation_contact_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )

    if "doctor_details_enabled" not in existing_cols:
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
    # No-op: downgrading either branch individually still owns the
    # drop_column for its own column. Nothing to reverse at the merge
    # point itself.
    pass
