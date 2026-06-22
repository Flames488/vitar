"""
Vitar — Hospital/Clinic QR Onboarding: Printable Poster Service

NEW FILE. Does not modify any existing service.

Generates a print-ready A4 PDF poster containing the clinic's logo (if
set), name, large QR code, and a short call-to-action. Intended to be
printed and displayed at reception desks.

Uses reportlab (pure-Python, no system dependencies) so it works in the
same container as the rest of the API without extra OS packages.
"""

import io
import os
import logging

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor
from reportlab.pdfgen import canvas

from app.core.config import settings
from app.services.qr_service import get_qr_path, generate_clinic_qr

logger = logging.getLogger("vitar.poster_service")

PRIMARY_COLOR = HexColor("#0F766E")  # teal — matches Vitar brand accent
TEXT_COLOR = HexColor("#1E293B")
MUTED_COLOR = HexColor("#64748B")


def _resolve_local_image_path(qr_path: str) -> str | None:
    """
    qr_code_path is stored as a served URL path like '/uploads/qrcodes/x.png'.
    Map it back to a real filesystem path for reportlab to read, when using
    local storage. Returns None if it's a remote (S3) URL — caller should
    fetch bytes separately in that case.
    """
    if qr_path.startswith("/uploads/"):
        relative = qr_path[len("/uploads/"):]
        return os.path.join(settings.UPLOAD_DIR, relative)
    return None  # remote URL (s3) — not a local file


def generate_clinic_poster(clinic) -> bytes:
    """
    Build an A4 PDF poster for a clinic and return the raw PDF bytes.
    Caller decides whether to stream it as a download or save it.

    If the clinic has no QR yet, generates one on the fly (does not
    persist it — that's the caller's job, same contract as qr_service).
    """
    qr_path = get_qr_path(clinic)
    local_qr_file = _resolve_local_image_path(qr_path) if qr_path else None

    if not local_qr_file or not os.path.exists(local_qr_file):
        # No QR yet, or path doesn't resolve locally (e.g. S3) — generate
        # a fresh one in memory just for this poster.
        fresh_path = generate_clinic_qr(clinic)
        local_qr_file = _resolve_local_image_path(fresh_path)

    buf = io.BytesIO()
    width, height = A4
    c = canvas.Canvas(buf, pagesize=A4)

    margin = 20 * mm
    center_x = width / 2

    # ── Header: clinic name ──────────────────────────────────────────────
    c.setFillColor(PRIMARY_COLOR)
    c.setFont("Helvetica-Bold", 28)
    c.drawCentredString(center_x, height - margin - 10 * mm, clinic.name or "")

    # ── Logo (optional) ──────────────────────────────────────────────────
    y_cursor = height - margin - 30 * mm
    if getattr(clinic, "logo_url", None):
        try:
            logo_path = _resolve_local_image_path(clinic.logo_url)
            if logo_path and os.path.exists(logo_path):
                logo_size = 30 * mm
                c.drawImage(
                    logo_path,
                    center_x - logo_size / 2,
                    y_cursor - logo_size,
                    width=logo_size,
                    height=logo_size,
                    preserveAspectRatio=True,
                    mask="auto",
                )
                y_cursor -= logo_size + 10 * mm
        except Exception as exc:
            logger.warning(f"poster_service: could not embed logo — {exc}")

    # ── QR code (large, centred) ─────────────────────────────────────────
    qr_size = 90 * mm
    qr_y = y_cursor - qr_size - 10 * mm
    if local_qr_file and os.path.exists(local_qr_file):
        c.drawImage(
            local_qr_file,
            center_x - qr_size / 2,
            qr_y,
            width=qr_size,
            height=qr_size,
        )
    else:
        logger.error("poster_service: no QR image available to embed")

    # ── Call to action ───────────────────────────────────────────────────
    text_y = qr_y - 14 * mm
    c.setFillColor(TEXT_COLOR)
    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(center_x, text_y, "Scan to:")

    items = ["✓ Register", "✓ Login", "✓ Book Appointments"]
    c.setFont("Helvetica", 13)
    for i, item in enumerate(items):
        c.drawCentredString(center_x, text_y - 8 * mm - (i * 7 * mm), item)

    # ── Footer ────────────────────────────────────────────────────────────
    c.setFillColor(MUTED_COLOR)
    c.setFont("Helvetica", 9)
    c.drawCentredString(center_x, margin, "Powered by Vitar")

    c.showPage()
    c.save()
    return buf.getvalue()
