"""
Vitar — Public Clinic Directory Endpoints

NEW FILE. Fully public, unauthenticated (same shape as booking.py's public
routes) — a patient without an account needs to reach these. Reuses the
clinics.slug that already exists (no second slug system) and the
Clinic.is_listed column as the single source of truth for visibility (see
models.Clinic and the is_listed hooks in onboarding.py / billing_service.py
/ workers/tasks.py.expire_trial_subscriptions).

Mounted at /api/v1/public/clinics. Search is additionally rate-limited via
RATE_RULES in core/middleware.py (unauthenticated + scraper-exposed).
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.models import Clinic

router = APIRouter()

SEARCH_RESULT_LIMIT = 10


@router.get("/search")
def search_clinics(
    q: Optional[str] = Query(None, min_length=1),
    city: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    query = db.query(Clinic).filter(Clinic.is_listed == True)  # noqa: E712 — explicit column filter, not a query-build shortcut
    if q:
        query = query.filter(Clinic.name.ilike(f"%{q}%"))
    if city:
        query = query.filter(Clinic.city.ilike(f"%{city}%"))
    if state:
        query = query.filter(Clinic.state.ilike(f"%{state}%"))

    clinics = query.order_by(Clinic.name.asc()).limit(SEARCH_RESULT_LIMIT).all()
    return [
        {"name": c.name, "city": c.city, "state": c.state, "slug": c.slug}
        for c in clinics
    ]


@router.get("/{slug}")
def get_clinic(slug: str, db: Session = Depends(get_db)):
    clinic = db.query(Clinic).filter(Clinic.slug == slug).first()
    # Same 404 whether the slug doesn't exist or exists but isn't listed —
    # never let the response distinguish the two (see Phase 1 spec: don't
    # leak which clinics exist but are unlisted).
    if not clinic or not clinic.is_listed:
        raise HTTPException(status_code=404, detail="Clinic not found")

    result = {
        "name": clinic.name,
        "address": clinic.address,
        "phone": clinic.phone,
    }
    if clinic.email:
        result["email"] = clinic.email
    if clinic.logo_url:
        # Clinics can already upload a logo via existing settings (see
        # clinics.py/uploads.py — the public booking page already surfaces
        # it too), not something added "later" as the phase 2 spec assumed.
        result["logo_url"] = clinic.logo_url
    if clinic.opening_hours:
        result["opening_hours"] = clinic.opening_hours
    if clinic.services:
        result["services"] = clinic.services
    return result
