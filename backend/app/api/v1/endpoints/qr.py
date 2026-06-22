"""
Vitar — Hospital/Clinic QR Onboarding: Dashboard Endpoints

NEW FILE. Does not modify clinics.py, auth.py route logic, or any
existing endpoint module.

Mounted at /api/v1/qr in router.py.

All endpoints here require an authenticated clinic owner (reuses the
existing get_current_clinic dependency — see NOTE below) and operate
only on that user's own clinic. A clinic admin can never regenerate or
view another clinic's QR/poster.

NOTE: This file assumes Vitar has an existing dependency that resolves
the current authenticated clinic from the request (cookie-based JWT,
per auth.py's v11 cookie auth). The exact import path/name may differ
slightly in your codebase — if `get_current_clinic` doesn't exist under
app.core.deps, point me to the actual dependency name/location and I'll
adjust this one import line.
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_clinic
from app.models.models import Clinic
from app.services.qr_service import generate_clinic_qr, regenerate_clinic_qr, get_qr_path
from app.services.poster_service import generate_clinic_poster
from app.core.config import settings

router = APIRouter()


def _portal_url(slug: str) -> str:
    return f"{settings.FRONTEND_URL.rstrip('/')}/book/{slug}"


@router.get("/me")
def get_my_qr(
    clinic: Clinic = Depends(get_current_clinic),
    db: Session = Depends(get_db),
):
    """
    Return the current clinic's QR code path + portal URL.
    Generates one on first call if it doesn't exist yet (lazy backfill
    for clinics that registered before this feature existed).
    """
    if not clinic.qr_code_path:
        clinic.qr_code_path = generate_clinic_qr(clinic)
        db.commit()
        db.refresh(clinic)

    return {
        "qr_code_path": clinic.qr_code_path,
        "portal_url": _portal_url(clinic.slug),
        "slug": clinic.slug,
    }


@router.post("/me/regenerate")
def regenerate_my_qr(
    clinic: Clinic = Depends(get_current_clinic),
    db: Session = Depends(get_db),
):
    """Force-regenerate the QR code (e.g. after a slug change)."""
    clinic.qr_code_path = regenerate_clinic_qr(clinic)
    db.commit()
    db.refresh(clinic)
    return {
        "qr_code_path": clinic.qr_code_path,
        "portal_url": _portal_url(clinic.slug),
    }


@router.get("/me/poster")
def download_my_poster(
    clinic: Clinic = Depends(get_current_clinic),
    db: Session = Depends(get_db),
):
    """Generate and stream a print-ready A4 PDF poster for this clinic."""
    if not clinic.qr_code_path:
        clinic.qr_code_path = generate_clinic_qr(clinic)
        db.commit()
        db.refresh(clinic)

    pdf_bytes = generate_clinic_poster(clinic)
    filename = f"{clinic.slug}-poster.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
