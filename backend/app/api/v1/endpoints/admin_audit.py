"""
Vitar — Admin Dashboard: Audit Log

GET /api/v1/admin/audit-logs   Paginated, filterable audit trail.

Reads from the existing AuditLog model (app/models/models.py) — every
admin_users.py / admin_clinics.py / admin_subscriptions.py mutation writes
here via app/services/audit_service.write_audit_log(). This endpoint is the
read side, also used to drive the Overview page's "Activity Feed".
"""

from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_superadmin
from app.models.models import User, AuditLog

router = APIRouter(prefix="/admin/audit-logs", tags=["Admin — Audit Log"])


def _serialize(entry: AuditLog, actor: Optional[User]) -> dict:
    return {
        "id": entry.id,
        "action": entry.action,
        "entity_type": entry.entity_type,
        "entity_id": entry.entity_id,
        "clinic_id": entry.clinic_id,
        "old_data": entry.old_data,
        "new_data": entry.new_data,
        "actor": {"id": actor.id, "full_name": actor.full_name, "email": actor.email} if actor else None,
        "ip_address": entry.ip_address,
        "created_at": entry.created_at.isoformat() if entry.created_at else None,
    }


@router.get("/")
def list_audit_logs(
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    clinic_id: Optional[str] = None,
    action: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    admin: User = Depends(get_current_superadmin),
    db: Session = Depends(get_db),
):
    q = db.query(AuditLog)
    if entity_type:
        q = q.filter(AuditLog.entity_type == entity_type)
    if entity_id:
        q = q.filter(AuditLog.entity_id == entity_id)
    if clinic_id:
        q = q.filter(AuditLog.clinic_id == clinic_id)
    if action:
        q = q.filter(AuditLog.action.ilike(f"%{action}%"))

    total = q.count()
    entries = q.order_by(AuditLog.created_at.desc()).offset((page - 1) * limit).limit(limit).all()

    actor_ids = [e.user_id for e in entries if e.user_id]
    actors = {u.id: u for u in db.query(User).filter(User.id.in_(actor_ids)).all()} if actor_ids else {}

    items = [_serialize(e, actors.get(e.user_id)) for e in entries]
    return {"items": items, "total": total, "page": page, "limit": limit}
