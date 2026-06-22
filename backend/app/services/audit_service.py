"""
Vitar — Audit Log Service

Thin wrapper around the existing AuditLog model (app/models/models.py).
Every administrative action taken from the /admin dashboard should call
write_audit_log() so there's a single, consistent trail of who did what,
when, and why — used by both the Admin Activity Feed and the dedicated
Audit Log page.

Usage:
    write_audit_log(
        db,
        admin_id=current_admin.id,
        action="subscription.grant_lifetime",
        entity_type="subscription",
        entity_id=sub.id,
        old_data={"plan": old_plan, "status": old_status},
        new_data={"plan": "enterprise", "status": "active"},
        reason=body.reason,
        request=request,
    )

Note: this does NOT call db.commit() — callers are expected to commit as
part of their own transaction (so the audit row and the actual change land
atomically, matching the pattern used elsewhere in this codebase).
"""

from typing import Optional, Any
from sqlalchemy.orm import Session
from fastapi import Request

from app.models.models import AuditLog


def write_audit_log(
    db: Session,
    *,
    admin_id: str,
    action: str,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    clinic_id: Optional[str] = None,
    old_data: Optional[dict[str, Any]] = None,
    new_data: Optional[dict[str, Any]] = None,
    reason: Optional[str] = None,
    notes: Optional[str] = None,
    request: Optional[Request] = None,
) -> AuditLog:
    """
    Writes one AuditLog row. `reason`/`notes` are folded into new_data since
    AuditLog has no dedicated columns for them — keeps this additive with
    zero schema changes.
    """
    merged_new_data = dict(new_data or {})
    if reason:
        merged_new_data["_reason"] = reason
    if notes:
        merged_new_data["_notes"] = notes

    entry = AuditLog(
        clinic_id=clinic_id,
        user_id=admin_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        old_data=old_data,
        new_data=merged_new_data or None,
        ip_address=request.client.host if (request and request.client) else None,
        user_agent=request.headers.get("user-agent") if request else None,
    )
    db.add(entry)
    db.flush()
    return entry
