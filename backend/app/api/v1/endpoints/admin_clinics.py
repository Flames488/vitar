"""
Vitar — Admin Dashboard: Clinic Management

GET    /api/v1/admin/clinics                      List clinics (search, filter, paginate)
GET    /api/v1/admin/clinics/{clinic_id}           View a single clinic + owner + subscription
PATCH  /api/v1/admin/clinics/{clinic_id}/status     Disable / enable a clinic
POST   /api/v1/admin/clinics/{clinic_id}/regenerate-qr   Regenerate the clinic's QR code

Reuses the existing qr_service (same function the clinic owner's own
/api/v1/qr/me endpoint calls) — no duplicate QR logic.
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import or_
from pydantic import BaseModel

from app.core.database import get_db
from app.core.security import get_current_superadmin
from app.core.config import settings
from app.models.models import User, Clinic, Subscription
from app.services.qr_service import regenerate_clinic_qr
from app.services.audit_service import write_audit_log

router = APIRouter(prefix="/admin/clinics", tags=["Admin — Clinics"])


class ClinicStatusUpdateRequest(BaseModel):
    is_active: bool
    reason: Optional[str] = None


def _portal_url(slug: str) -> str:
    return f"{settings.FRONTEND_URL.rstrip('/')}/book/{slug}"


def _serialize_row(clinic: Clinic, owner: Optional[User], sub: Optional[Subscription]) -> dict:
    return {
        "id": clinic.id,
        "name": clinic.name,
        "slug": clinic.slug,
        "qr_code_path": clinic.qr_code_path,
        "portal_url": _portal_url(clinic.slug),
        "owner": {"id": owner.id, "full_name": owner.full_name, "email": owner.email} if owner else None,
        "country": clinic.country,
        "is_active": clinic.is_active,
        "onboarding_completed": clinic.onboarding_completed,
        "subscription_plan": sub.plan.value if sub else None,
        "subscription_status": sub.status.value if sub else None,
        "created_at": clinic.created_at.isoformat() if clinic.created_at else None,
    }


def _get_or_404(clinic_id: str, db: Session) -> Clinic:
    clinic = db.query(Clinic).filter(Clinic.id == clinic_id).first()
    if not clinic:
        raise HTTPException(status_code=404, detail="Clinic not found")
    return clinic


@router.get("/")
def list_clinics(
    search: Optional[str] = None,
    status_filter: Optional[str] = Query(None, alias="status", description="'active' or 'disabled'"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    admin: User = Depends(get_current_superadmin),
    db: Session = Depends(get_db),
):
    q = db.query(Clinic)
    if search:
        q = q.filter(or_(Clinic.name.ilike(f"%{search}%"), Clinic.slug.ilike(f"%{search}%")))
    if status_filter == "active":
        q = q.filter(Clinic.is_active == True)  # noqa: E712
    elif status_filter == "disabled":
        q = q.filter(Clinic.is_active == False)  # noqa: E712

    total = q.count()
    clinics = q.order_by(Clinic.created_at.desc()).offset((page - 1) * limit).limit(limit).all()

    owner_ids = [c.owner_id for c in clinics]
    owners = {u.id: u for u in db.query(User).filter(User.id.in_(owner_ids)).all()} if owner_ids else {}
    clinic_ids = [c.id for c in clinics]
    subs = {
        s.clinic_id: s for s in db.query(Subscription).filter(Subscription.clinic_id.in_(clinic_ids)).all()
    } if clinic_ids else {}

    items = [_serialize_row(c, owners.get(c.owner_id), subs.get(c.id)) for c in clinics]
    return {"items": items, "total": total, "page": page, "limit": limit}


@router.get("/{clinic_id}")
def get_clinic(
    clinic_id: str,
    admin: User = Depends(get_current_superadmin),
    db: Session = Depends(get_db),
):
    clinic = _get_or_404(clinic_id, db)
    owner = db.query(User).filter(User.id == clinic.owner_id).first()
    sub = db.query(Subscription).filter(Subscription.clinic_id == clinic.id).first()
    return _serialize_row(clinic, owner, sub)


@router.patch("/{clinic_id}/status")
def update_clinic_status(
    clinic_id: str,
    body: ClinicStatusUpdateRequest,
    request: Request,
    admin: User = Depends(get_current_superadmin),
    db: Session = Depends(get_db),
):
    clinic = _get_or_404(clinic_id, db)
    old_value = clinic.is_active
    if old_value == body.is_active:
        owner = db.query(User).filter(User.id == clinic.owner_id).first()
        sub = db.query(Subscription).filter(Subscription.clinic_id == clinic.id).first()
        return _serialize_row(clinic, owner, sub)

    clinic.is_active = body.is_active
    write_audit_log(
        db,
        admin_id=admin.id,
        action="clinic.enable" if body.is_active else "clinic.disable",
        entity_type="clinic",
        entity_id=clinic.id,
        clinic_id=clinic.id,
        old_data={"is_active": old_value},
        new_data={"is_active": body.is_active},
        reason=body.reason,
        request=request,
    )
    db.commit()
    db.refresh(clinic)

    owner = db.query(User).filter(User.id == clinic.owner_id).first()
    sub = db.query(Subscription).filter(Subscription.clinic_id == clinic.id).first()
    return _serialize_row(clinic, owner, sub)


@router.post("/{clinic_id}/regenerate-qr")
def regenerate_qr(
    clinic_id: str,
    request: Request,
    admin: User = Depends(get_current_superadmin),
    db: Session = Depends(get_db),
):
    clinic = _get_or_404(clinic_id, db)
    old_path = clinic.qr_code_path
    clinic.qr_code_path = regenerate_clinic_qr(clinic)

    write_audit_log(
        db,
        admin_id=admin.id,
        action="clinic.regenerate_qr",
        entity_type="clinic",
        entity_id=clinic.id,
        clinic_id=clinic.id,
        old_data={"qr_code_path": old_path},
        new_data={"qr_code_path": clinic.qr_code_path},
        request=request,
    )
    db.commit()
    db.refresh(clinic)
    return {"qr_code_path": clinic.qr_code_path, "portal_url": _portal_url(clinic.slug)}
