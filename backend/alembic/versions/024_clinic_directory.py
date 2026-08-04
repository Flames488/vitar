"""024_clinic_directory

Public clinic directory: reuses the existing clinics.slug (already
unique/indexed/immutable, already the canonical public identifier used by
/book/{slug} and the QR code) — no new slug field or generation logic.

Adds:
  - is_listed: the single source of truth for "is this clinic publicly
    searchable / does its page resolve". Set true once onboarding
    completes AND the clinic has an active trial or paid subscription
    (see hooks in onboarding.py, billing_service.py, and the existing
    expire_trial_subscriptions Celery beat task), set false when a trial
    expires with no active subscription. This migration backfills it for
    clinics that already qualify.
  - opening_hours / services: no existing schema or onboarding flow
    captures either today (checked — Clinic has no hours/services fields,
    DoctorAvailability is per-doctor scheduling, not clinic-level hours).
    Both nullable, no backfill data exists; the public clinic page omits
    these sections when empty rather than inventing placeholder content.

Revision ID: 024_clinic_directory
Revises: 023_patient_registrations
Create Date: 2026-08-04
"""
from alembic import op
import sqlalchemy as sa

revision = "024_clinic_directory"
down_revision = "023_patient_registrations"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("clinics", sa.Column("is_listed", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("clinics", sa.Column("opening_hours", sa.Text(), nullable=True))
    op.add_column("clinics", sa.Column("services", sa.JSON(), nullable=True))
    op.create_index("ix_clinics_is_listed", "clinics", ["is_listed"])

    # One-time backfill — matches has_paid_feature_access()'s rule (active
    # trial OR active paid subscription) applied to clinics that already
    # completed onboarding as of this migration. Ongoing changes to
    # trial/subscription state after this point are handled by the hooks
    # described above, not by re-running this migration.
    op.execute("""
        UPDATE clinics
        SET is_listed = true
        WHERE onboarding_completed = true
          AND slug IS NOT NULL
          AND (
            (trial_ends_at IS NOT NULL AND trial_ends_at > NOW())
            OR EXISTS (
              SELECT 1 FROM subscriptions s
              WHERE s.clinic_id = clinics.id
                AND s.status = 'active'
                AND s.plan IN ('basic', 'pro', 'enterprise')
            )
          )
    """)


def downgrade():
    op.drop_index("ix_clinics_is_listed", "clinics")
    op.drop_column("clinics", "services")
    op.drop_column("clinics", "opening_hours")
    op.drop_column("clinics", "is_listed")
