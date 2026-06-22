"""
Vitar QR Onboarding — Backfill Script

Run ONCE after the migration + new files are deployed, to generate QR
codes for clinics that already existed before this feature shipped.
Safe to re-run: it skips clinics that already have a qr_code_path, so
re-running after a partial failure only retries the ones that failed.

Usage (inside the API container):
    PYTHONPATH=/app python /tmp/qr_backfill.py
"""
from app.core.database import SessionLocal
from app.models.models import Clinic
from app.services.qr_service import generate_clinic_qr

db = SessionLocal()
try:
    clinics = db.query(Clinic).filter(Clinic.qr_code_path.is_(None)).all()
    print(f"Found {len(clinics)} clinic(s) without a QR code.")

    succeeded = 0
    failed = 0
    for clinic in clinics:
        try:
            clinic.qr_code_path = generate_clinic_qr(clinic)
            db.commit()
            succeeded += 1
            print(f"  OK   {clinic.slug} -> {clinic.qr_code_path}")
        except Exception as exc:
            db.rollback()
            failed += 1
            print(f"  FAIL {clinic.slug or clinic.id}: {exc}")

    print(f"\nBackfill complete: {succeeded} succeeded, {failed} failed.")
finally:
    db.close()
