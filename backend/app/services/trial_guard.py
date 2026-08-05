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
import math

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


def get_doctor_limit_info(clinic, db: Session) -> dict:
    """
    Single source of truth for a clinic's doctor limit, shared by
    check_doctor_limit() (write-side enforcement) and the doctors list
    endpoint (so the frontend can proactively disable "Add Doctor" and show
    an upgrade prompt, instead of only finding out after a failed submit).
    """
    from app.models.models import Doctor
    from app.services.billing_service import PLANS

    sub = clinic.subscription
    current_count = db.query(Doctor).filter(Doctor.clinic_id == clinic.id, Doctor.is_active == True).count()

    is_trialing = not sub or _status_value(sub.status) == "trialing"
    trial_expired = bool(clinic.trial_ends_at) and utcnow() > clinic.trial_ends_at

    if is_trialing and not trial_expired:
        return {"current": current_count, "limit": -1, "plan": "trial", "at_limit": False}

    plan_key = _plan_value(sub.plan) if sub else "basic"
    if plan_key not in PLANS:
        plan_key = "basic"
    max_doctors = PLANS[plan_key].get("max_doctors", 2)

    return {
        "current": current_count,
        "limit": max_doctors,
        "plan": plan_key,
        "at_limit": max_doctors != -1 and current_count >= max_doctors,
    }


def check_doctor_limit(clinic, db: Session):
    info = get_doctor_limit_info(clinic, db)
    if info["at_limit"]:
        raise HTTPException(
            status_code=402,
            detail={
                "code": "PLAN_DOCTOR_LIMIT",
                "message": f"Your {info['plan'].title()} plan supports up to {info['limit']} doctors. Upgrade to add more.",
                "current": info["current"], "limit": info["limit"],
                "upgrade_url": "/settings/billing",
            },
        )


def has_paid_feature_access(clinic) -> bool:
    """
    Shared gate for features that are free during the trial and require a
    paid plan afterwards (e.g. Doctor Details: email/phone/"Talk with a
    Doctor"). Returns True when:
      - the clinic is on an active, non-expired trial, OR
      - the clinic has an active paid subscription (basic/pro/enterprise).
    Returns False once the trial has expired and no paid plan is active.
    """
    sub = clinic.subscription
    if not sub:
        return False

    plan = _plan_value(sub.plan)
    status = _status_value(sub.status)

    if status == "trialing":
        now = utcnow()
        if clinic.trial_ends_at and now > clinic.trial_ends_at:
            return False
        return True

    return plan in ("basic", "pro", "enterprise") and status == "active"


def has_doctor_contact_access(clinic) -> bool:
    """
    Doctor Contact (WhatsApp/Call/email, post-booking) — free during any
    active trial, then requires any paid plan (basic/pro/enterprise). Same
    "any paid plan" rule as has_paid_feature_access(); kept as a separate
    function so this feature's gate can be tuned independently later.
    """
    return has_paid_feature_access(clinic)


def get_trial_status(clinic) -> dict:
    sub = clinic.subscription
    now = utcnow()

    if not sub or _status_value(sub.status) != "trialing":
        return {"is_trial": False}

    trial_end = clinic.trial_ends_at
    days_left = max(math.ceil((trial_end - now).total_seconds() / 86400), 0) if trial_end else 0
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
        "doctors_limit": -1,  # Enterprise-level (unlimited) during trial — see check_doctor_limit
        "show_upgrade_nudge": show_nudge,
        "is_expired": now > trial_end if trial_end else False,
        "paid_features_unlocked": has_paid_feature_access(clinic),
    }
