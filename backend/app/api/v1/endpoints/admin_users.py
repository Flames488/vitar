"""
Vitar — Admin Dashboard: User Management

GET    /api/v1/admin/users               List users (search, filter, sort, paginate)
GET    /api/v1/admin/users/{user_id}     View a single user + their clinic/subscription
PATCH  /api/v1/admin/users/{user_id}/role        Promote/demote (grant or revoke superadmin)
PATCH  /api/v1/admin/users/{user_id}/status      Suspend / reactivate

All routes require get_current_superadmin (server-side enforced — see
app/core/security.py). Every mutating action writes an AuditLog row via
app/services/audit_service.write_audit_log().

Note on roles: the schema has a single boolean (User.is_superadmin), not a
three-tier role system. "Promote/Demote" and "Grant/Revoke Superadmin" are
therefore the same action here — both map to toggling is_superadmin. If a
real Admin tier (distinct from Superadmin) is needed later, add an is_admin
column and extend the `role` field below; nothing else needs to change.
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import or_
from pydantic import BaseModel

from app.core.database import get_db
from app.core.security import get_current_superadmin
from app.models.models import User, Clinic, Subscription
from app.services.audit_service import write_audit_log

router = APIRouter(prefix="/admin/users", tags=["Admin — Users"])


# ─── Schemas ──────────────────────────────────────────────────────────────────

class RoleUpdateRequest(BaseModel):
    is_superadmin: bool
    reason: Optional[str] = None


class StatusUpdateRequest(BaseModel):
    is_active: bool
    reason: Optional[str] = None


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _role(user: User) -> str:
    return "superadmin" if user.is_superadmin else "user"


def _serialize_row(user: User, clinic: Optional[Clinic], sub: Optional[Subscription]) -> dict:
    return {
        "id": user.id,
        "full_name": user.full_name,
        "email": user.email,
        "role": _role(user),
        "is_superadmin": user.is_superadmin,
        "is_active": user.is_active,
        "subscription_status": sub.status.value if sub else None,
        "subscription_plan": sub.plan.value if sub else None,
        "clinic_id": clinic.id if clinic else None,
        "clinic_name": clinic.name if clinic else None,
        "registered_at": user.created_at.isoformat() if user.created_at else None,
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
    }


def _get_or_404(user_id: str, db: Session) -> User:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


# ─── List ─────────────────────────────────────────────────────────────────────

@router.get("/")
def list_users(
    search: Optional[str] = None,
    role: Optional[str] = Query(None, description="'user' or 'superadmin'"),
    status_filter: Optional[str] = Query(None, alias="status", description="'active' or 'suspended'"),
    sort_by: str = Query("created_at", pattern="^(created_at|full_name|email|last_login_at)$"),
    sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    admin: User = Depends(get_current_superadmin),
    db: Session = Depends(get_db),
):
    q = db.query(User)

    if search:
        q = q.filter(or_(
            User.full_name.ilike(f"%{search}%"),
            User.email.ilike(f"%{search}%"),
        ))
    if role == "superadmin":
        q = q.filter(User.is_superadmin == True)  # noqa: E712
    elif role == "user":
        q = q.filter(User.is_superadmin == False)  # noqa: E712
    if status_filter == "active":
        q = q.filter(User.is_active == True)  # noqa: E712
    elif status_filter == "suspended":
        q = q.filter(User.is_active == False)  # noqa: E712

    total = q.count()

    sort_col = getattr(User, sort_by)
    sort_col = sort_col.desc() if sort_dir == "desc" else sort_col.asc()
    users = q.order_by(sort_col).offset((page - 1) * limit).limit(limit).all()

    # Batch-fetch clinics + subscriptions to avoid N+1 queries
    user_ids = [u.id for u in users]
    clinics = {
        c.owner_id: c for c in db.query(Clinic).filter(Clinic.owner_id.in_(user_ids)).all()
    } if user_ids else {}
    clinic_ids = [c.id for c in clinics.values()]
    subs = {
        s.clinic_id: s for s in db.query(Subscription).filter(Subscription.clinic_id.in_(clinic_ids)).all()
    } if clinic_ids else {}

    items = []
    for u in users:
        clinic = clinics.get(u.id)
        sub = subs.get(clinic.id) if clinic else None
        items.append(_serialize_row(u, clinic, sub))
    return {"items": items, "total": total, "page": page, "limit": limit}


# ─── Detail ───────────────────────────────────────────────────────────────────

@router.get("/{user_id}")
def get_user(
    user_id: str,
    admin: User = Depends(get_current_superadmin),
    db: Session = Depends(get_db),
):
    user = _get_or_404(user_id, db)
    clinic = db.query(Clinic).filter(Clinic.owner_id == user.id).first()
    sub = db.query(Subscription).filter(Subscription.clinic_id == clinic.id).first() if clinic else None

    data = _serialize_row(user, clinic, sub)
    data["clinic"] = {
        "id": clinic.id,
        "name": clinic.name,
        "slug": clinic.slug,
        "country": clinic.country,
        "is_active": clinic.is_active,
        "onboarding_completed": clinic.onboarding_completed,
        "created_at": clinic.created_at.isoformat() if clinic.created_at else None,
    } if clinic else None
    data["subscription"] = {
        "plan": sub.plan.value,
        "status": sub.status.value,
        "current_period_end": sub.current_period_end.isoformat() if sub.current_period_end else None,
        "amount": float(sub.amount) if sub.amount is not None else 0,
        "currency": sub.currency,
    } if sub else None
    return data


# ─── Role (promote / demote / grant / revoke superadmin) ─────────────────────

@router.patch("/{user_id}/role")
def update_role(
    user_id: str,
    body: RoleUpdateRequest,
    request: Request,
    admin: User = Depends(get_current_superadmin),
    db: Session = Depends(get_db),
):
    user = _get_or_404(user_id, db)

    if user.id == admin.id and not body.is_superadmin:
        raise HTTPException(status_code=400, detail="You cannot revoke your own superadmin access")

    old_value = user.is_superadmin
    if old_value == body.is_superadmin:
        return _serialize_row(user, None, None)

    user.is_superadmin = body.is_superadmin
    write_audit_log(
        db,
        admin_id=admin.id,
        action="user.grant_superadmin" if body.is_superadmin else "user.revoke_superadmin",
        entity_type="user",
        entity_id=user.id,
        old_data={"is_superadmin": old_value},
        new_data={"is_superadmin": body.is_superadmin},
        reason=body.reason,
        request=request,
    )
    db.commit()
    db.refresh(user)
    return _serialize_row(user, None, None)


# ─── Status (suspend / reactivate) ────────────────────────────────────────────

@router.patch("/{user_id}/status")
def update_status(
    user_id: str,
    body: StatusUpdateRequest,
    request: Request,
    admin: User = Depends(get_current_superadmin),
    db: Session = Depends(get_db),
):
    user = _get_or_404(user_id, db)

    if user.id == admin.id and not body.is_active:
        raise HTTPException(status_code=400, detail="You cannot suspend your own account")

    old_value = user.is_active
    if old_value == body.is_active:
        return _serialize_row(user, None, None)

    user.is_active = body.is_active
    write_audit_log(
        db,
        admin_id=admin.id,
        action="user.reactivate" if body.is_active else "user.suspend",
        entity_type="user",
        entity_id=user.id,
        old_data={"is_active": old_value},
        new_data={"is_active": body.is_active},
        reason=body.reason,
        request=request,
    )
    db.commit()
    db.refresh(user)
    return _serialize_row(user, None, None)
