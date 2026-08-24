"""
Vitar — Admin Dashboard: Subscription & Billing Administration (high priority)

GET   /api/v1/admin/subscriptions                       List all clinic subscriptions
GET   /api/v1/admin/subscriptions/{clinic_id}            View one clinic's subscription
POST  /api/v1/admin/subscriptions/{clinic_id}/override   Apply an admin override

Reuses the existing Subscription model as-is — no schema changes. trial_guard.py
(app/services/trial_guard.py) only ever reads sub.plan / sub.status / current_period_end,
so every override type below works simply by writing to those existing columns.
Administrative notes + the reason for an override are stored in Subscription.extra_data
(already a free-form JSON column) so the latest override context is visible at a glance,
while the full history lives in AuditLog (one row per action, queryable via
GET /api/v1/admin/audit-logs?entity_type=subscription&entity_id={clinic_id}).
"""

import enum
from datetime import timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import or_
from pydantic import BaseModel, field_validator

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_superadmin
from app.core.utils import utcnow
from app.models.models import (
    User, Clinic, Subscription, SubscriptionPlan, SubscriptionStatus,
)
from app.services.audit_service import write_audit_log
from app.services.notifications import notify

router = APIRouter(prefix="/admin/subscriptions", tags=["Admin — Subscriptions"])

LIFETIME_YEARS = 100  # "lifetime" is modeled as a far-future expiration, not a new status


class OverrideAction(str, enum.Enum):
    GRANT_FREE = "grant_free"
    GRANT_TEMPORARY = "grant_temporary"
    GRANT_LIFETIME = "grant_lifetime"
    EXTEND = "extend"
    SET_EXPIRATION = "set_expiration"
    REVOKE = "revoke"


class OverrideRequest(BaseModel):
    action: OverrideAction
    plan: Optional[SubscriptionPlan] = None          # used by grant_free / grant_temporary / grant_lifetime
    duration_days: Optional[int] = None               # required for grant_temporary / extend
    expiration_date: Optional[str] = None              # ISO date, required for set_expiration
    notes: Optional[str] = None
    reason: Optional[str] = None

    @field_validator("duration_days")
    @classmethod
    def positive_duration(cls, v):
        if v is not None and v <= 0:
            raise ValueError("duration_days must be positive")
        return v


def _sub_snapshot(sub: Subscription) -> dict:
    return {
        "plan": sub.plan.value if sub.plan else None,
        "status": sub.status.value if sub.status else None,
        "current_period_end": sub.current_period_end.isoformat() if sub.current_period_end else None,
        "amount": float(sub.amount) if sub.amount is not None else None,
    }


def _installment_summary(plan_row) -> Optional[dict]:
    if not plan_row:
        return None
    return {
        "plan": plan_row.subscription_plan,
        "total_installments": plan_row.total_installments,
        "installments_paid": plan_row.installments_paid,
        "status": plan_row.status.value,
    }


def _fetch_installment_plans(clinic_ids: list, db: Session) -> dict:
    """
    One row per clinic — the clinic's ACTIVE installment plan if it has
    one, otherwise its most recently created one (completed/cancelled),
    so admins/the Telegram assistant can see "still paying it off" vs.
    "finished" vs. "never had one" at a glance.
    """
    if not clinic_ids:
        return {}
    from app.models.models import SubscriptionInstallmentPlan, InstallmentPlanStatus
    rows = (
        db.query(SubscriptionInstallmentPlan)
        .filter(SubscriptionInstallmentPlan.clinic_id.in_(clinic_ids))
        .order_by(SubscriptionInstallmentPlan.created_at.desc())
        .all()
    )
    result = {}
    for r in rows:
        current = result.get(r.clinic_id)
        if current is None or (r.status == InstallmentPlanStatus.ACTIVE and current.status != InstallmentPlanStatus.ACTIVE):
            result[r.clinic_id] = r
    return result


def _serialize(clinic: Clinic, sub: Subscription, owner: Optional[User], installment_plan: Optional[dict] = None) -> dict:
    return {
        "clinic_id": clinic.id,
        "clinic_name": clinic.name,
        "owner": {"id": owner.id, "full_name": owner.full_name, "email": owner.email} if owner else None,
        "plan": sub.plan.value,
        "status": sub.status.value,
        "amount": float(sub.amount) if sub.amount is not None else 0,
        "currency": sub.currency,
        "current_period_start": sub.current_period_start.isoformat() if sub.current_period_start else None,
        "current_period_end": sub.current_period_end.isoformat() if sub.current_period_end else None,
        "admin_override": (sub.extra_data or {}).get("admin_override"),
        "updated_at": sub.updated_at.isoformat() if sub.updated_at else None,
        # None if this clinic has never used the pay-in-installments option.
        "installment_plan": installment_plan,
    }


def _override_message(action: "OverrideAction", clinic: Clinic, sub: Subscription, body: "OverrideRequest") -> str:
    plan_display = sub.plan.value if sub.plan else "plan"
    if action == OverrideAction.GRANT_FREE:
        text = f"{clinic.name} was granted a free {plan_display} plan (admin override)."
    elif action == OverrideAction.GRANT_TEMPORARY:
        text = f"{clinic.name} was granted {body.duration_days} days of {plan_display} (admin override)."
    elif action == OverrideAction.GRANT_LIFETIME:
        text = f"{clinic.name} was granted a lifetime {plan_display} plan (admin override)."
    elif action == OverrideAction.EXTEND:
        end = sub.current_period_end.strftime("%d %b %Y") if sub.current_period_end else "—"
        text = f"{clinic.name}'s subscription was extended by {body.duration_days} days, now ends {end} (admin override)."
    elif action == OverrideAction.SET_EXPIRATION:
        end = sub.current_period_end.strftime("%d %b %Y") if sub.current_period_end else "—"
        text = f"{clinic.name}'s subscription expiration was manually set to {end} (admin override)."
    elif action == OverrideAction.REVOKE:
        text = f"{clinic.name}'s subscription was revoked (admin override)."
    else:
        text = f"{clinic.name}'s subscription was updated: {action.value} (admin override)."
    if body.reason:
        text += f" Reason: {body.reason}"
    return text


def _get_clinic_and_sub(clinic_id: str, db: Session) -> tuple[Clinic, Subscription]:
    clinic = db.query(Clinic).filter(Clinic.id == clinic_id).first()
    if not clinic:
        raise HTTPException(status_code=404, detail="Clinic not found")
    sub = db.query(Subscription).filter(Subscription.clinic_id == clinic_id).first()
    if not sub:
        raise HTTPException(status_code=404, detail="This clinic has no subscription record")
    return clinic, sub


@router.get("/")
def list_subscriptions(
    search: Optional[str] = None,
    plan: Optional[SubscriptionPlan] = None,
    status_filter: Optional[SubscriptionStatus] = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    admin: User = Depends(get_current_superadmin),
    db: Session = Depends(get_db),
):
    q = db.query(Subscription).join(Clinic, Clinic.id == Subscription.clinic_id)
    if search:
        q = q.filter(Clinic.name.ilike(f"%{search}%"))
    if plan:
        q = q.filter(Subscription.plan == plan)
    if status_filter:
        q = q.filter(Subscription.status == status_filter)

    total = q.count()
    subs = q.order_by(Subscription.updated_at.desc()).offset((page - 1) * limit).limit(limit).all()

    clinic_ids = [s.clinic_id for s in subs]
    clinics = {c.id: c for c in db.query(Clinic).filter(Clinic.id.in_(clinic_ids)).all()} if clinic_ids else {}
    owner_ids = [c.owner_id for c in clinics.values()]
    owners = {u.id: u for u in db.query(User).filter(User.id.in_(owner_ids)).all()} if owner_ids else {}
    installment_plans = _fetch_installment_plans(clinic_ids, db)

    items = []
    for s in subs:
        clinic = clinics.get(s.clinic_id)
        if not clinic:
            continue
        items.append(_serialize(
            clinic, s, owners.get(clinic.owner_id),
            _installment_summary(installment_plans.get(s.clinic_id)),
        ))
    return {"items": items, "total": total, "page": page, "limit": limit}


@router.get("/{clinic_id}")
def get_subscription(
    clinic_id: str,
    admin: User = Depends(get_current_superadmin),
    db: Session = Depends(get_db),
):
    clinic, sub = _get_clinic_and_sub(clinic_id, db)
    owner = db.query(User).filter(User.id == clinic.owner_id).first()
    installment_plans = _fetch_installment_plans([clinic_id], db)
    return _serialize(clinic, sub, owner, _installment_summary(installment_plans.get(clinic_id)))


@router.post("/reset-trials")
def reset_active_trials(
    request: Request,
    dry_run: bool = Query(False, description="Preview affected clinics without writing changes"),
    admin: User = Depends(get_current_superadmin),
    db: Session = Depends(get_db),
):
    """
    Backfill: recompute trial_ends_at = trial_started_at + TRIAL_DAYS (30) for
    every clinic still on an active trial right now. Only touches clinics with
    subscription.status == 'trialing' — expired trials and clinics already on
    a paid/overridden plan are left untouched.

    Safe to re-run: clinics already at the correct 30-day mark are skipped.
    """
    trialing = (
        db.query(Clinic, Subscription)
        .join(Subscription, Subscription.clinic_id == Clinic.id)
        .filter(Subscription.status == SubscriptionStatus.TRIALING)
        .all()
    )

    changed = []
    for clinic, sub in trialing:
        if not clinic.trial_started_at:
            continue  # no registration timestamp to recompute from — skip, don't guess
        correct_end = clinic.trial_started_at + timedelta(days=settings.TRIAL_DAYS)
        if clinic.trial_ends_at == correct_end:
            continue  # already correct
        changed.append({
            "clinic_id": clinic.id,
            "clinic_name": clinic.name,
            "old_trial_ends_at": clinic.trial_ends_at.isoformat() if clinic.trial_ends_at else None,
            "new_trial_ends_at": correct_end.isoformat(),
        })
        if not dry_run:
            old_snapshot = _sub_snapshot(sub)
            clinic.trial_ends_at = correct_end
            sub.current_period_end = correct_end
            write_audit_log(
                db,
                admin_id=admin.id,
                action="subscription.reset_trial_30_days",
                entity_type="subscription",
                entity_id=sub.id,
                clinic_id=clinic.id,
                old_data=old_snapshot,
                new_data=_sub_snapshot(sub),
                reason="Bulk trial backfill — restore correct 30-day trial",
                request=request,
            )

    if not dry_run and changed:
        db.commit()

    return {"dry_run": dry_run, "affected_count": len(changed), "clinics": changed}


@router.post("/{clinic_id}/override")
def apply_override(
    clinic_id: str,
    body: OverrideRequest,
    request: Request,
    admin: User = Depends(get_current_superadmin),
    db: Session = Depends(get_db),
):
    clinic, sub = _get_clinic_and_sub(clinic_id, db)
    old_snapshot = _sub_snapshot(sub)
    now = utcnow()

    if body.action == OverrideAction.GRANT_FREE:
        sub.plan = body.plan or sub.plan
        sub.status = SubscriptionStatus.ACTIVE
        sub.amount = 0
        # Match billing.py/billing_service.py: any (re)activation clears a
        # pending self-service cancellation, else the clinic keeps seeing
        # "Cancels at period end" despite the admin just granting access.
        sub.cancel_at_period_end = False

    elif body.action == OverrideAction.GRANT_TEMPORARY:
        if not body.duration_days:
            raise HTTPException(status_code=422, detail="duration_days is required for grant_temporary")
        sub.plan = body.plan or sub.plan
        sub.status = SubscriptionStatus.ACTIVE
        sub.current_period_start = now
        sub.current_period_end = now + timedelta(days=body.duration_days)
        sub.cancel_at_period_end = False

    elif body.action == OverrideAction.GRANT_LIFETIME:
        sub.plan = body.plan or SubscriptionPlan.ENTERPRISE
        sub.status = SubscriptionStatus.ACTIVE
        sub.amount = 0
        sub.current_period_start = now
        sub.current_period_end = now + timedelta(days=365 * LIFETIME_YEARS)
        sub.cancel_at_period_end = False

    elif body.action == OverrideAction.EXTEND:
        if not body.duration_days:
            raise HTTPException(status_code=422, detail="duration_days is required for extend")
        base = sub.current_period_end if sub.current_period_end and sub.current_period_end > now else now
        sub.current_period_end = base + timedelta(days=body.duration_days)
        sub.cancel_at_period_end = False
        if sub.status in (SubscriptionStatus.EXPIRED, SubscriptionStatus.CANCELLED, SubscriptionStatus.PAST_DUE):
            sub.status = SubscriptionStatus.ACTIVE

    elif body.action == OverrideAction.SET_EXPIRATION:
        if not body.expiration_date:
            raise HTTPException(status_code=422, detail="expiration_date is required for set_expiration")
        try:
            from datetime import datetime
            parsed = datetime.fromisoformat(body.expiration_date)
            # utcnow() (used for the comparison below and everywhere else in
            # this file) returns a naive datetime — a tz-aware value here
            # would raise TypeError on comparison instead of the intended 422.
            sub.current_period_end = parsed.replace(tzinfo=None) if parsed.tzinfo else parsed
        except ValueError:
            raise HTTPException(status_code=422, detail="expiration_date must be a valid ISO date")
        if sub.current_period_end > now and sub.status in (
            SubscriptionStatus.EXPIRED, SubscriptionStatus.CANCELLED, SubscriptionStatus.PAST_DUE
        ):
            sub.status = SubscriptionStatus.ACTIVE

    elif body.action == OverrideAction.REVOKE:
        sub.status = SubscriptionStatus.CANCELLED
        sub.cancelled_at = now
        sub.current_period_end = now

    # Keep Clinic.trial_ends_at in sync with Subscription.current_period_end.
    # trial_guard.py reads clinic.trial_ends_at (not sub.current_period_end)
    # to compute days-left/is_expired for anyone still in "trialing" status —
    # without this, an override that adjusts current_period_end while leaving
    # someone trialing (e.g. set_expiration) would silently desync the two,
    # same class of bug as the original 13-day trial report.
    if sub.status == SubscriptionStatus.TRIALING:
        clinic.trial_ends_at = sub.current_period_end
    elif body.action in (OverrideAction.GRANT_FREE, OverrideAction.GRANT_TEMPORARY,
                          OverrideAction.GRANT_LIFETIME, OverrideAction.REVOKE):
        # These move the clinic off the trial entirely — clear the trial
        # clock so trial_guard / the dashboard trial banner stop referencing it.
        clinic.trial_ends_at = None

    # Mirror the latest override context onto the subscription itself so the
    # admin UI can show "why" without a separate audit-log lookup.
    extra = dict(sub.extra_data or {})
    extra["admin_override"] = {
        "action": body.action.value,
        "granted_by": admin.id,
        "granted_by_email": admin.email,
        "granted_at": now.isoformat(),
        "reason": body.reason,
        "notes": body.notes,
    }
    sub.extra_data = extra

    write_audit_log(
        db,
        admin_id=admin.id,
        action=f"subscription.{body.action.value}",
        entity_type="subscription",
        entity_id=sub.id,
        clinic_id=clinic.id,
        old_data=old_snapshot,
        new_data=_sub_snapshot(sub),
        reason=body.reason,
        notes=body.notes,
        request=request,
    )
    db.commit()
    db.refresh(sub)

    notify(
        event_type="subscription_override",
        agent_name="billing",
        message=_override_message(body.action, clinic, sub, body),
        related_id=clinic.id,
        link_path="/admin/subscriptions",
    )

    owner = db.query(User).filter(User.id == clinic.owner_id).first()
    return _serialize(clinic, sub, owner)
