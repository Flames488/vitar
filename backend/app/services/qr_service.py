"""
Vitar — Hospital/Clinic QR Onboarding: QR Generation Service

NEW FILE. Does not modify any existing service.

Generates and stores a QR code per clinic that points to that clinic's
public portal page. Works for any organisation type stored in the
`clinics` table — hospital, clinic, eye clinic, lab, etc. There is no
separate "Hospital" model in Vitar; `Clinic` already represents all of
these, so this service is intentionally type-agnostic.

QR destination format:
    {FRONTEND_URL}/portal/{clinic.slug}

Storage:
    Local disk under settings.UPLOAD_DIR/qrcodes/{slug}.png  (dev/local)
    — or —
    S3 under qrcodes/{slug}.png when STORAGE_BACKEND=s3
    (reuses the existing storage backend abstraction from app.services.storage
    if present; falls back to local disk if that module doesn't exist yet,
    so this file works standalone even before storage.py is wired up).

The returned `qr_code_path` is what gets saved on Clinic.qr_code_path.
For local storage this is a path served via the existing `/uploads` static
mount in main.py (e.g. "/uploads/qrcodes/lifecare-hospital.png").
For S3 storage this is the public object URL.
"""

import os
import io
import logging

import qrcode
from qrcode.image.styledpil import StyledPilImage
from qrcode.image.styles.moduledrawers import RoundedModuleDrawer

from app.core.config import settings

logger = logging.getLogger("vitar.qr_service")

QR_SUBDIR = "qrcodes"


def _portal_url(slug: str) -> str:
    """Build the public portal URL a patient lands on after scanning."""
    base = settings.FRONTEND_URL.rstrip("/")
    return f"{base}/book/{slug}"


def _local_qr_dir() -> str:
    path = os.path.join(settings.UPLOAD_DIR, QR_SUBDIR)
    os.makedirs(path, exist_ok=True)
    return path


def _save_local(slug: str, png_bytes: bytes) -> str:
    """Save QR png to local disk, return the path served by the /uploads mount."""
    qr_dir = _local_qr_dir()
    file_path = os.path.join(qr_dir, f"{slug}.png")
    with open(file_path, "wb") as f:
        f.write(png_bytes)
    return f"/uploads/{QR_SUBDIR}/{slug}.png"


def _save_s3(slug: str, png_bytes: bytes) -> str:
    """
    Save via the existing storage backend abstraction if available.
    Falls back to local disk if app.services.storage isn't present —
    this keeps qr_service usable even if storage.py hasn't been wired
    up in this environment yet.
    """
    try:
        from app.services.storage import upload_bytes  # existing abstraction, if present
        key = f"{QR_SUBDIR}/{slug}.png"
        return upload_bytes(key, png_bytes, content_type="image/png")
    except ImportError:
        logger.warning(
            "qr_service: STORAGE_BACKEND=s3 but app.services.storage.upload_bytes "
            "not found — falling back to local disk for QR storage."
        )
        return _save_local(slug, png_bytes)


def _render_qr_png(data: str) -> bytes:
    """Render a styled QR code (rounded modules) as PNG bytes."""
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_H,  # high — survives print wear/scuffs
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)

    img = qr.make_image(
        image_factory=StyledPilImage,
        module_drawer=RoundedModuleDrawer(),
    )

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def generate_clinic_qr(clinic) -> str:
    """
    Generate a QR code for a clinic and return the storage path/URL.
    Does NOT save to the database — caller is responsible for setting
    clinic.qr_code_path and committing, so this function has no side
    effects on the ORM session.

    Works for any clinic type (hospital, clinic, eye clinic, lab, ...).
    """
    if not clinic.slug:
        raise ValueError(f"Clinic {clinic.id} has no slug — cannot generate QR")

    target_url = _portal_url(clinic.slug)
    png_bytes = _render_qr_png(target_url)

    storage_backend = getattr(settings, "STORAGE_BACKEND", "local")
    if storage_backend == "s3":
        path = _save_s3(clinic.slug, png_bytes)
    else:
        path = _save_local(clinic.slug, png_bytes)

    logger.info(
        "qr_service: generated QR",
        extra={"clinic_id": clinic.id, "slug": clinic.slug, "path": path},
    )
    return path


def regenerate_clinic_qr(clinic) -> str:
    """
    Regenerate a clinic's QR code (e.g. slug changed, or admin requested
    a fresh one). Same as generate_clinic_qr — overwrites the existing
    file at the same path since the path is derived from the slug.
    """
    return generate_clinic_qr(clinic)


def get_qr_path(clinic) -> str | None:
    """Convenience accessor — returns the stored path or None."""
    return getattr(clinic, "qr_code_path", None)
