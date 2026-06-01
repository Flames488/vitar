"""
Vitar v13 — File Upload Endpoints
===================================
Handles doctor avatar and clinic logo uploads.

Both endpoints:
  - Validate file type (images only) and size (≤ 5 MB)
  - Delegate to storage_service (S3 or local, based on STORAGE_BACKEND)
  - Persist the returned URL to the database
  - Delete the old file from storage before replacing it (best-effort)
  - Return the new URL so the frontend can update its state immediately

Routes
------
  POST /uploads/doctors/{doctor_id}/avatar  — multipart/form-data, field: file
  POST /uploads/clinics/me/logo             — multipart/form-data, field: file
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_clinic
from app.models.models import Doctor
from app.services.storage_service import (
    storage,
    ALLOWED_CONTENT_TYPES,
    MAX_UPLOAD_BYTES,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Shared validation helper ──────────────────────────────────────────────────

async def _read_and_validate(file: UploadFile) -> tuple[bytes, str]:
    """
    Read the upload, enforce type and size limits.
    Returns (data_bytes, content_type).
    Raises HTTPException on violation.
    """
    content_type = file.content_type or ""

    if content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=415,
            detail=(
                f"Unsupported file type: {content_type!r}. "
                f"Allowed types: {', '.join(sorted(ALLOWED_CONTENT_TYPES))}"
            ),
        )

    data = await file.read()

    if len(data) > MAX_UPLOAD_BYTES:
        mb = MAX_UPLOAD_BYTES // (1024 * 1024)
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum allowed size is {mb} MB.",
        )

    if len(data) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    return data, content_type


# ── Doctor avatar ─────────────────────────────────────────────────────────────

@router.post("/doctors/{doctor_id}/avatar")
async def upload_doctor_avatar(
    doctor_id: str,
    file: UploadFile = File(...),
    clinic=Depends(get_current_clinic),
    db: Session = Depends(get_db),
):
    """
    Upload or replace a doctor's avatar photo.

    - Accepts: image/jpeg, image/png, image/webp, image/gif
    - Max size: 5 MB
    - Field name: file (multipart/form-data)
    """
    # Authorisation: doctor must belong to the requesting clinic
    doctor = (
        db.query(Doctor)
        .filter(Doctor.id == doctor_id, Doctor.clinic_id == clinic.id)
        .first()
    )
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")

    data, content_type = await _read_and_validate(file)

    # Delete old avatar from storage (best-effort — don't block on failure)
    if doctor.avatar_url:
        await storage.delete(doctor.avatar_url)

    # Upload new avatar
    try:
        url = await storage.upload(
            data=data,
            original_filename=file.filename or "avatar",
            content_type=content_type,
            folder="avatars",
        )
    except RuntimeError as exc:
        logger.error(f"[uploads] Doctor avatar upload failed: {exc}")
        raise HTTPException(status_code=502, detail="File upload failed. Please try again.")

    # Persist URL
    doctor.avatar_url = url
    db.commit()

    logger.info(f"[uploads] Doctor {doctor_id} avatar updated → {url}")
    return {"avatar_url": url, "doctor_id": doctor_id}


# ── Clinic logo ───────────────────────────────────────────────────────────────

@router.post("/clinics/me/logo")
async def upload_clinic_logo(
    file: UploadFile = File(...),
    clinic=Depends(get_current_clinic),
    db: Session = Depends(get_db),
):
    """
    Upload or replace the clinic's logo.

    - Accepts: image/jpeg, image/png, image/webp, image/gif
    - Max size: 5 MB
    - Field name: file (multipart/form-data)
    """
    data, content_type = await _read_and_validate(file)

    # Delete old logo from storage (best-effort)
    if clinic.logo_url:
        await storage.delete(clinic.logo_url)

    # Upload new logo
    try:
        url = await storage.upload(
            data=data,
            original_filename=file.filename or "logo",
            content_type=content_type,
            folder="logos",
        )
    except RuntimeError as exc:
        logger.error(f"[uploads] Clinic logo upload failed: {exc}")
        raise HTTPException(status_code=502, detail="File upload failed. Please try again.")

    # Persist URL
    clinic.logo_url = url
    db.commit()

    logger.info(f"[uploads] Clinic {clinic.id} logo updated → {url}")
    return {"logo_url": url, "clinic_id": clinic.id}
