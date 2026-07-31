"""Add unique constraint on patients(clinic_id, phone) to support atomic upsert

Fixes the appointments_patient_id_fkey race: the booking endpoint used to
SELECT-then-INSERT a patient, flush, and commit later — leaving a window
where the flushed patient row could be lost (pooler reconnect / transaction
pooling edge case) before the appointment insert that references it. The
new atomic INSERT ... ON CONFLICT upsert in booking.py needs a real unique
constraint as its conflict target.

Revision ID: 014_patient_phone_unique
Revises: 013_hospital_payouts
"""
from alembic import op
import sqlalchemy as sa

revision = "014_patient_phone_unique"
down_revision = "013_hospital_payouts"
branch_labels = None
depends_on = None


def upgrade():
    # ── Step 1: dedupe existing patients that share (clinic_id, phone) ──
    # Keep the oldest row per (clinic_id, phone); re-point any appointments
    # referencing a duplicate at the surviving row, then delete the dupes.
    # Patients with clinic_id IS NULL (Wabizz-created, no clinic link yet)
    # are left untouched — Postgres treats NULL as distinct in unique
    # constraints, so they never collide with each other anyway.
    op.execute("""
        WITH ranked AS (
            SELECT id, clinic_id, phone,
                   ROW_NUMBER() OVER (
                       PARTITION BY clinic_id, phone
                       ORDER BY created_at ASC
                   ) AS rn
            FROM patients
            WHERE clinic_id IS NOT NULL
        ),
        dupes AS (
            SELECT r.id AS dupe_id, keep.id AS keep_id
            FROM ranked r
            JOIN ranked keep
              ON keep.clinic_id = r.clinic_id
             AND keep.phone = r.phone
             AND keep.rn = 1
            WHERE r.rn > 1
        )
        UPDATE appointments a
        SET patient_id = d.keep_id
        FROM dupes d
        WHERE a.patient_id = d.dupe_id;
    """)

    op.execute("""
        WITH ranked AS (
            SELECT id, clinic_id, phone,
                   ROW_NUMBER() OVER (
                       PARTITION BY clinic_id, phone
                       ORDER BY created_at ASC
                   ) AS rn
            FROM patients
            WHERE clinic_id IS NOT NULL
        )
        DELETE FROM patients
        WHERE id IN (SELECT id FROM ranked WHERE rn > 1);
    """)

    # ── Step 2: add the unique constraint (conflict target for upsert) ──
    op.create_unique_constraint(
        "uq_patient_clinic_phone",
        "patients",
        ["clinic_id", "phone"],
    )


def downgrade():
    op.drop_constraint("uq_patient_clinic_phone", "patients", type_="unique")
