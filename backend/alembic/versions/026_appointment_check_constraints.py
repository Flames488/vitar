"""Add missing CHECK constraints on appointments (duration_mins, no_show_risk_score)

app/models/models.py's Appointment.__table_args__ has declared chk_duration
("duration_mins > 0 AND duration_mins <= 480") and chk_risk_score
("no_show_risk_score >= 0.0 AND no_show_risk_score <= 1.0") since these
columns were introduced, but no migration ever actually created them —
001_initial.py only created the columns, with no accompanying
CheckConstraint DDL. The live DB has never enforced either invariant; only
Base.metadata.create_all() (SQLite tests) ever built them. This adds both,
matching what the model has claimed all along.

Revision ID: 026_appointment_check_constraints
Revises: 025_patient_clinic_fk_set_null
"""
from alembic import op

revision = "026_appointment_check_constraints"
down_revision = "025_patient_clinic_fk_set_null"
branch_labels = None
depends_on = None


def upgrade():
    op.create_check_constraint(
        "chk_duration",
        "appointments",
        "duration_mins > 0 AND duration_mins <= 480",
    )
    op.create_check_constraint(
        "chk_risk_score",
        "appointments",
        "no_show_risk_score >= 0.0 AND no_show_risk_score <= 1.0",
    )


def downgrade():
    op.drop_constraint("chk_risk_score", "appointments", type_="check")
    op.drop_constraint("chk_duration", "appointments", type_="check")
