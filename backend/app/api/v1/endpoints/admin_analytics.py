"""
Vitar — Admin Dashboard: Overview KPIs, Growth Charts, Activity Feed, Business Analytics

GET /api/v1/admin/analytics/overview     KPI cards + growth charts + activity feed (Dashboard Overview module)
GET /api/v1/admin/analytics/business      Active vs inactive users, subscription trends, growth (Analytics module)
GET /api/v1/admin/analytics/export.csv    CSV export of the business analytics breakdown
"""

import csv
import io
from datetime import timedelta
from typing import Optional
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.database import get_db
from app.core.security import get_current_superadmin
from app.core.utils import utcnow
from app.models.models import (
    User, Clinic, Subscription, SubscriptionStatus, SubscriptionPayment, PaymentStatus,
    AuditLog,
)

router = APIRouter(prefix="/admin/analytics", tags=["Admin — Analytics"])


def _month_buckets(months: int) -> list[str]:
    """Returns the last N month labels as 'YYYY-MM', oldest first."""
    now = utcnow()
    labels = []
    y, m = now.year, now.month
    for _ in range(months):
        labels.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return list(reversed(labels))


def _monthly_counts(db: Session, model, months: int) -> dict[str, int]:
    buckets = {label: 0 for label in _month_buckets(months)}
    since = utcnow().replace(day=1) - timedelta(days=31 * (months - 1))
    rows = (
        db.query(func.strftime("%Y-%m", model.created_at) if _is_sqlite(db) else func.to_char(model.created_at, "YYYY-MM"))
        .filter(model.created_at >= since)
        .all()
    )
    for (label,) in rows:
        if label in buckets:
            buckets[label] += 1
    return buckets


def _is_sqlite(db: Session) -> bool:
    return db.bind.dialect.name == "sqlite"


@router.get("/overview")
def dashboard_overview(
    admin: User = Depends(get_current_superadmin),
    db: Session = Depends(get_db),
):
    now = utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    total_users = db.query(func.count(User.id)).scalar() or 0
    total_clinics = db.query(func.count(Clinic.id)).scalar() or 0
    active_subscriptions = (
        db.query(func.count(Subscription.id))
        .filter(Subscription.status == SubscriptionStatus.ACTIVE)
        .scalar() or 0
    )
    monthly_revenue = (
        db.query(func.coalesce(func.sum(SubscriptionPayment.amount), 0))
        .filter(SubscriptionPayment.status == PaymentStatus.PAID, SubscriptionPayment.created_at >= month_start)
        .scalar() or 0
    )

    user_growth = _monthly_counts(db, User, 6)
    clinic_growth = _monthly_counts(db, Clinic, 6)

    recent = (
        db.query(AuditLog)
        .order_by(AuditLog.created_at.desc())
        .limit(15)
        .all()
    )
    actor_ids = [a.user_id for a in recent if a.user_id]
    actors = {u.id: u for u in db.query(User).filter(User.id.in_(actor_ids)).all()} if actor_ids else {}
    activity_feed = [
        {
            "id": a.id,
            "action": a.action,
            "entity_type": a.entity_type,
            "entity_id": a.entity_id,
            "actor_name": actors[a.user_id].full_name if a.user_id in actors else "System",
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in recent
    ]

    return {
        "kpis": {
            "total_users": total_users,
            "total_clinics": total_clinics,
            "active_subscriptions": active_subscriptions,
            "monthly_revenue": float(monthly_revenue),
        },
        "user_growth": [{"month": k, "count": v} for k, v in user_growth.items()],
        "clinic_growth": [{"month": k, "count": v} for k, v in clinic_growth.items()],
        "activity_feed": activity_feed,
    }


@router.get("/business")
def business_analytics(
    admin: User = Depends(get_current_superadmin),
    db: Session = Depends(get_db),
):
    active_users = db.query(func.count(User.id)).filter(User.is_active == True).scalar() or 0  # noqa: E712
    inactive_users = db.query(func.count(User.id)).filter(User.is_active == False).scalar() or 0  # noqa: E712

    plan_breakdown = (
        db.query(Subscription.plan, func.count(Subscription.id))
        .group_by(Subscription.plan)
        .all()
    )
    status_breakdown = (
        db.query(Subscription.status, func.count(Subscription.id))
        .group_by(Subscription.status)
        .all()
    )

    user_growth = _monthly_counts(db, User, 12)
    clinic_growth = _monthly_counts(db, Clinic, 12)

    return {
        "active_vs_inactive_users": {"active": active_users, "inactive": inactive_users},
        "subscription_plan_breakdown": [{"plan": p.value if hasattr(p, "value") else p, "count": c} for p, c in plan_breakdown],
        "subscription_status_breakdown": [{"status": s.value if hasattr(s, "value") else s, "count": c} for s, c in status_breakdown],
        "user_growth": [{"month": k, "count": v} for k, v in user_growth.items()],
        "clinic_growth": [{"month": k, "count": v} for k, v in clinic_growth.items()],
    }


@router.get("/export.csv")
def export_business_csv(
    admin: User = Depends(get_current_superadmin),
    db: Session = Depends(get_db),
):
    data = business_analytics(admin=admin, db=db)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Metric", "Key", "Value"])
    writer.writerow(["Active Users", "", data["active_vs_inactive_users"]["active"]])
    writer.writerow(["Inactive Users", "", data["active_vs_inactive_users"]["inactive"]])
    for row in data["subscription_plan_breakdown"]:
        writer.writerow(["Subscription Plan", row["plan"], row["count"]])
    for row in data["subscription_status_breakdown"]:
        writer.writerow(["Subscription Status", row["status"], row["count"]])
    for row in data["user_growth"]:
        writer.writerow(["User Growth", row["month"], row["count"]])
    for row in data["clinic_growth"]:
        writer.writerow(["Clinic Growth", row["month"], row["count"]])
    buf.seek(0)

    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=vitar-admin-analytics.csv"},
    )
