"""
Vitar v5 - Trial Guard (HARDENED)
Fixes:
  - Enum vs string comparison (sub.plan could be enum or string depending on DB)
  - Consistent plan/status value extraction
"""

from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy.orm import Session
import logging

from app.core.utils import utcnow
from app.core.config import settings

logger = logging.getLogger(__name__)


def _plan_value(plan) -> str:
    """Safely extract string value from plan (handles both enum and raw string)."""
    return plan.value if hasattr(plan, "value") else str(plan)


def _status_value(status) -> str:
    """Safely extract string value from status."""
    return status.value if hasattr(status, "value") else str(status)


def check_trial_booking_limit(clinic, db: Session):
    sub = clinic.subscription
    if not sub:
        return  # No subscription — dev/edge case, allow

    plan = _plan_value(sub.plan)
    status = _status_value(sub.status)

    # Active paid plan = unrestricted
    if plan in ("basic", "pro", "enterprise") and status == "active":
        return

    # Trial checks
    if status == "trialing":
        now = utcnow()

        if clinic.trial_ends_at and now > clinic.trial_ends_at:
            raise HTTPException(
                status_code=402,
                detail={
                    "code": "TRIAL_EXPIRED",
                    "message": "Your 30-day free trial has ended. Upgrade to continue booking appointments.",
                    "upgrade_url": "/settings/billing",
                },
            )

        used = clinic.trial_bookings_used or 0
        if used >= settings.TRIAL_MAX_BOOKINGS:
            raise HTTPException(
                status_code=402,
                detail={
                    "code": "TRIAL_BOOKING_LIMIT",
                    "message": f"You've used all {settings.TRIAL_MAX_BOOKINGS} free trial bookings. Upgrade to continue.",
                    "used": used,
                    "limit": settings.TRIAL_MAX_BOOKINGS,
                    "upgrade_url": "/settings/billing",
                },
            )
        return

    if status in ("expired", "cancelled", "past_due"):
        raise HTTPException(
            status_code=402,
            detail={
                "code": "SUBSCRIPTION_INACTIVE",
                "message": "Your subscription is inactive. Please renew to continue.",
                "upgrade_url": "/settings/billing",
            },
        )


def check_doctor_limit(clinic, db: Session):
    from app.models.models import Doctor
    from app.services.billing_service import PLANS

    sub = clinic.subscription
    current_count = db.query(Doctor).filter(Doctor.clinic_id == clinic.id, Doctor.is_active == True).count()

    if not sub or _status_value(sub.status) == "trialing":
        limit = settings.TRIAL_MAX_DOCTORS
        if current_count >= limit:
            raise HTTPException(
                status_code=402,
                detail={
                    "code": "TRIAL_DOCTOR_LIMIT",
                    "message": f"Trial allows up to {limit} doctors. Upgrade to add more.",
                    "current": current_count, "limit": limit,
                    "upgrade_url": "/settings/billing",
                },
            )
        return

    plan_key = _plan_value(sub.plan) if sub else "basic"
    if plan_key not in PLANS:
        plan_key = "basic"

    max_doctors = PLANS[plan_key].get("max_doctors", 2)
    if max_doctors != -1 and current_count >= max_doctors:
        raise HTTPException(
            status_code=402,
            detail={
                "code": "PLAN_DOCTOR_LIMIT",
                "message": f"Your {plan_key.title()} plan supports up to {max_doctors} doctors. Upgrade to add more.",
                "current": current_count, "limit": max_doctors,
                "upgrade_url": "/settings/billing",
            },
        )


def get_trial_status(clinic) -> dict:
    sub = clinic.subscription
    now = utcnow()

    if not sub or _status_value(sub.status) != "trialing":
        return {"is_trial": False}

    trial_end = clinic.trial_ends_at
    days_left = max((trial_end - now).days, 0) if trial_end else 0
    bookings_used = clinic.trial_bookings_used or 0
    bookings_left = max(settings.TRIAL_MAX_BOOKINGS - bookings_used, 0)

    total_days = settings.TRIAL_DAYS
    days_elapsed = total_days - days_left
    show_nudge = days_elapsed in (7, 10, 13) or days_left <= 1

    return {
        "is_trial": True,
        "days_left": days_left,
        "trial_ends_at": trial_end.isoformat() if trial_end else None,
        "bookings_used": bookings_used,
        "bookings_left": bookings_left,
        "bookings_limit": settings.TRIAL_MAX_BOOKINGS,
        "doctors_limit": settings.TRIAL_MAX_DOCTORS,
        "show_upgrade_nudge": show_nudge,
        "is_expired": now > trial_end if trial_end else False,
    }
