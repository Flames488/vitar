"""
Vitar v5.2 - Analytics Endpoints
- Redis caching via central cache module (TTL 60–300s)
- Null guards on all aggregations
- Prometheus hit/miss recording
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, text

from app.core.utils import utcnow
from app.core.database import get_db
from app.core.security import get_current_clinic
from app.core.cache import cache, analytics_key, TTL_MEDIUM
from app.core.metrics import record_cache_hit, record_cache_miss

router = APIRouter()
logger = logging.getLogger(__name__)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/dashboard")
def analytics_dashboard(
    db: Session = Depends(get_db),
    clinic=Depends(get_current_clinic),
):
    """Aggregated dashboard metrics with 60s Redis cache."""
    clinic_id = clinic.id
    cache_key = analytics_key(str(clinic_id), "dashboard")
    cached = cache.get(cache_key)
    if cached:
        record_cache_hit()
        cached["_cached"] = True
        return cached
    record_cache_miss()

    try:
        from app.models.models import (
            Appointment, Patient, AppointmentStatus,
            Notification, NotificationStatus,
        )

        now = utcnow()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        prev_month_start = (month_start - timedelta(days=1)).replace(day=1)

        def safe_count(query) -> int:
            try:
                return query.count() or 0
            except Exception:
                return 0

        def safe_scalar(query, default=0):
            try:
                result = query.scalar()
                return float(result) if result is not None else default
            except Exception:
                return default

        # Appointment counts
        base_q = db.query(Appointment).filter(Appointment.clinic_id == clinic_id)

        total_this_month = safe_count(
            base_q.filter(Appointment.scheduled_at >= month_start)
        )
        total_prev_month = safe_count(
            base_q.filter(
                Appointment.scheduled_at >= prev_month_start,
                Appointment.scheduled_at < month_start,
            )
        )

        completed_this_month = safe_count(
            base_q.filter(
                Appointment.scheduled_at >= month_start,
                Appointment.status == AppointmentStatus.COMPLETED,
            )
        )
        no_show_this_month = safe_count(
            base_q.filter(
                Appointment.scheduled_at >= month_start,
                Appointment.status == AppointmentStatus.NO_SHOW,
            )
        )
        cancelled_this_month = safe_count(
            base_q.filter(
                Appointment.scheduled_at >= month_start,
                Appointment.status == AppointmentStatus.CANCELLED,
            )
        )

        # No-show rate (guard division by zero)
        denominator = completed_this_month + no_show_this_month
        no_show_rate = round(no_show_this_month / denominator * 100, 1) if denominator > 0 else 0.0

        # Patients
        patient_count = safe_count(
            db.query(Patient).filter(Patient.clinic_id == clinic_id)
        )

        # Average risk score (null-safe)
        avg_risk = safe_scalar(
            db.query(func.avg(Appointment.no_show_risk_score)).filter(
                Appointment.clinic_id == clinic_id,
                Appointment.no_show_risk_score.isnot(None),
                Appointment.scheduled_at >= month_start,
            )
        )

        # Notification delivery rate
        total_notifs = safe_count(
            db.query(Notification).filter(
                Notification.clinic_id == clinic_id,
                Notification.created_at >= month_start,
            )
        )
        sent_notifs = safe_count(
            db.query(Notification).filter(
                Notification.clinic_id == clinic_id,
                Notification.created_at >= month_start,
                Notification.status == NotificationStatus.SENT,
            )
        )
        notif_rate = round(sent_notifs / total_notifs * 100, 1) if total_notifs > 0 else 0.0

        # Month-over-month trend
        mom_change = 0.0
        if total_prev_month > 0:
            mom_change = round((total_this_month - total_prev_month) / total_prev_month * 100, 1)

        result = {
            "clinic_id": clinic_id,
            "period": {
                "month_start": month_start.isoformat(),
                "generated_at": now.isoformat(),
            },
            "appointments": {
                "total_this_month": total_this_month,
                "total_prev_month": total_prev_month,
                "mom_change_pct": mom_change,
                "completed": completed_this_month,
                "no_show": no_show_this_month,
                "cancelled": cancelled_this_month,
                "no_show_rate_pct": no_show_rate,
            },
            "patients": {"total": patient_count},
            "risk": {"avg_score": round(avg_risk, 3)},
            "notifications": {
                "total": total_notifs,
                "sent": sent_notifs,
                "delivery_rate_pct": notif_rate,
            },
            "_cached": False,
        }

        cache.set(cache_key, result, ttl=TTL_MEDIUM)
        return result

    except Exception as e:
        logger.error(f"analytics_dashboard error for clinic {clinic_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to generate analytics")


@router.get("/quick-summary")
def quick_summary(
    db: Session = Depends(get_db),
    clinic=Depends(get_current_clinic),
):
    """Lightweight summary — upcoming appointments today + this week."""
    clinic_id = clinic.id
    cache_key = analytics_key(str(clinic_id), "summary")
    cached = cache.get(cache_key)
    if cached:
        record_cache_hit()
        return cached
    record_cache_miss()

    try:
        from app.models.models import Appointment, AppointmentStatus

        now = utcnow()
        today_end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
        week_end = now + timedelta(days=7)

        base = db.query(Appointment).filter(
            Appointment.clinic_id == clinic_id,
            Appointment.status == AppointmentStatus.CONFIRMED,
        )

        today_count = base.filter(
            Appointment.scheduled_at >= now,
            Appointment.scheduled_at <= today_end,
        ).count() or 0

        week_count = base.filter(
            Appointment.scheduled_at >= now,
            Appointment.scheduled_at <= week_end,
        ).count() or 0

        high_risk = base.filter(
            Appointment.scheduled_at >= now,
            Appointment.scheduled_at <= week_end,
            Appointment.no_show_risk_score >= 0.6,
        ).count() or 0

        result = {
            "clinic_id": clinic_id,
            "today_appointments": today_count,
            "week_appointments": week_count,
            "high_risk_this_week": high_risk,
            "generated_at": now.isoformat(),
        }

        cache.set(cache_key, result, ttl=TTL_MEDIUM)
        return result

    except Exception as e:
        logger.error(f"quick_summary error for clinic {clinic_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get summary")


@router.get("/no-show-trends")
def no_show_trends(
    days: int = Query(30, ge=7, le=90),
    db: Session = Depends(get_db),
    clinic=Depends(get_current_clinic),
):
    """No-show trends over last N days, cached 60s."""
    clinic_id = clinic.id
    cache_key = analytics_key(str(clinic_id), f"noshow:{days}")
    cached = cache.get(cache_key)
    if cached:
        record_cache_hit()
        return cached
    record_cache_miss()

    try:
        from app.models.models import Appointment, AppointmentStatus

        now = utcnow()
        cutoff = now - timedelta(days=days)

        from sqlalchemy import case
        rows = (
            db.query(
                func.date_trunc("day", Appointment.scheduled_at).label("day"),
                func.count().label("total"),
                func.sum(
                    case(
                        (Appointment.status == AppointmentStatus.NO_SHOW, 1),
                        else_=0,
                    )
                ).label("no_shows"),
            )
            .filter(
                Appointment.clinic_id == clinic_id,
                Appointment.scheduled_at >= cutoff,
                Appointment.status.in_([
                    AppointmentStatus.COMPLETED,
                    AppointmentStatus.NO_SHOW,
                ]),
            )
            .group_by(text("day"))
            .order_by(text("day"))
            .all()
        )

        trend = []
        for row in rows:
            total = row.total or 0
            no_shows = row.no_shows or 0
            rate = round(no_shows / total * 100, 1) if total > 0 else 0.0
            trend.append({
                "date": str(row.day)[:10] if row.day else None,
                "total": total,
                "no_shows": no_shows,
                "rate_pct": rate,
            })

        result = {"clinic_id": clinic_id, "days": days, "trend": trend}
        cache.set(cache_key, result, ttl=TTL_MEDIUM)
        return result

    except Exception as e:
        logger.error(f"no_show_trends error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get trends")
