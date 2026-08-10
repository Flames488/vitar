"""
Vitar — Admin Dashboard: AI Core Agents

POST /api/v1/admin/agents/lead-hunter/run   Manually trigger a Lead Hunter run

More endpoints (Sales Agent, Content Agent, Customer Success actions) are
added here in later AI Core build phases — this file grows incrementally
rather than being split per agent, matching how admin_clinics.py /
admin_users.py etc. are each one cohesive file per admin area.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from typing import Optional

from app.core.security import get_current_superadmin
from app.services.audit_service import write_audit_log
from app.services.notifications import notify
from app.core.database import get_db
from app.core.utils import utcnow
from sqlalchemy.orm import Session

router = APIRouter(prefix="/admin/agents", tags=["Admin — AI Agents"])

# Leads are a first-class concept of their own, not scoped under any one
# agent's namespace — separate router, same file (this file grows
# incrementally across AI Core build phases rather than being split up).
leads_router = APIRouter(prefix="/admin/leads", tags=["Admin — Leads"])


class LeadHunterRunRequest(BaseModel):
    city: str
    query: str = "private clinic"


@router.post("/lead-hunter/run", status_code=202)
def run_lead_hunter(
    body: LeadHunterRunRequest,
    request: Request,
    admin=Depends(get_current_superadmin),
    db: Session = Depends(get_db),
):
    """Enqueues a Lead Hunter run immediately — the dashboard's 'Run now' button."""
    from app.agents.lead_hunter import hunt_leads

    task = hunt_leads.delay(city=body.city, query=body.query)

    write_audit_log(
        db,
        admin_id=admin.id,
        action="ai_core.lead_hunter.run",
        entity_type="agent_run",
        new_data={"city": body.city, "query": body.query, "task_id": task.id},
        request=request,
    )
    db.commit()

    return {"status": "queued", "task_id": task.id, "city": body.city, "query": body.query}


# ── Sales Agent: draft approval ─────────────────────────────────────────────

def _get_content_or_404(content_id: str, db: Session):
    from app.models.models import ContentQueue
    row = db.query(ContentQueue).filter(ContentQueue.id == content_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Content not found")
    return row


@router.post("/sales/approve/{content_id}")
def approve_sales_draft(
    content_id: str,
    request: Request,
    admin=Depends(get_current_superadmin),
    db: Session = Depends(get_db),
):
    """Marks a draft approved — send_approved_outreach picks it up on its
    next scheduled pass (no separate 'send now' path; keeps one send code
    path instead of a dashboard-triggered duplicate of it)."""
    from app.models.models import ContentStatus

    content = _get_content_or_404(content_id, db)
    content.status = ContentStatus.APPROVED
    content.approved_by = admin.id
    write_audit_log(
        db, admin_id=admin.id, action="ai_core.sales.approve",
        entity_type="content_queue", entity_id=content_id, request=request,
    )
    db.commit()
    return {"status": "approved", "content_id": content_id}


@router.post("/sales/reject/{content_id}")
def reject_sales_draft(
    content_id: str,
    request: Request,
    admin=Depends(get_current_superadmin),
    db: Session = Depends(get_db),
):
    from app.models.models import ContentStatus

    content = _get_content_or_404(content_id, db)
    content.status = ContentStatus.REJECTED
    write_audit_log(
        db, admin_id=admin.id, action="ai_core.sales.reject",
        entity_type="content_queue", entity_id=content_id, request=request,
    )
    db.commit()
    return {"status": "rejected", "content_id": content_id}


class EditContentRequest(BaseModel):
    body: str


@router.post("/sales/edit/{content_id}")
def edit_sales_draft(
    content_id: str,
    body: EditContentRequest,
    request: Request,
    admin=Depends(get_current_superadmin),
    db: Session = Depends(get_db),
):
    """Overwrites the stored draft text — must happen before approve, since
    send_approved_outreach sends whatever text is stored at that point."""
    content = _get_content_or_404(content_id, db)
    old_body = content.body
    content.body = body.body
    write_audit_log(
        db, admin_id=admin.id, action="ai_core.sales.edit",
        entity_type="content_queue", entity_id=content_id,
        old_data={"body": old_body}, new_data={"body": body.body}, request=request,
    )
    db.commit()
    return {"status": "edited", "content_id": content_id}


# ── Leads: manual status override ───────────────────────────────────────────

class LeadStatusUpdateRequest(BaseModel):
    status: str


@leads_router.patch("/{lead_id}/status")
def update_lead_status(
    lead_id: str,
    body: LeadStatusUpdateRequest,
    request: Request,
    admin=Depends(get_current_superadmin),
    db: Session = Depends(get_db),
):
    """
    Manual fallback for stage transitions the pipeline can't detect on its
    own — trial_started and paid aren't inferrable from a WhatsApp message,
    so an admin sets those by hand even once the Wabizz reply webhook
    automates the 'replied' transition.
    """
    from app.models.models import Lead, LeadStatus

    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    try:
        # LeadStatus's values are lowercase ("new", "replied", "trial_started",
        # ...) — that's the wire format clients send, matching every other
        # status string in this API. Enum storage internally uses the
        # uppercase member NAME (see models.py's native_enum=False note),
        # but that's an ORM/DB detail this parsing step must not leak into.
        new_status = LeadStatus(body.status.lower())
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid status: {body.status}")

    old_status = lead.status
    lead.status = new_status
    lead.updated_at = utcnow()

    write_audit_log(
        db, admin_id=admin.id, action="ai_core.lead.status_update",
        entity_type="lead", entity_id=lead_id,
        old_data={"status": old_status.value if hasattr(old_status, "value") else old_status},
        new_data={"status": new_status.value},
        request=request,
    )
    db.commit()

    if new_status == LeadStatus.REPLIED:
        notify(
            event_type="lead_replied",
            agent_name="sales_agent",
            message=f"{lead.clinic_name} replied!",
            related_id=lead.id,
            link_path="/admin/agents/sales",
        )
    elif new_status == LeadStatus.TRIAL_STARTED:
        notify(
            event_type="lead_trial_started",
            agent_name="sales_agent",
            message=f"{lead.clinic_name} started a trial!",
            related_id=lead.id,
            link_path="/admin/agents/sales",
        )

    return {"status": "updated", "lead_id": lead_id, "new_status": new_status.value}


# ── Content Agent: draft approval ───────────────────────────────────────────
# Reuses _get_content_or_404 defined above (Sales Agent section) — same
# content_queue table, just a different content_type.

@router.post("/content/approve/{content_id}")
def approve_content_draft(
    content_id: str,
    request: Request,
    admin=Depends(get_current_superadmin),
    db: Session = Depends(get_db),
):
    from app.models.models import ContentStatus

    content = _get_content_or_404(content_id, db)
    content.status = ContentStatus.APPROVED
    content.approved_by = admin.id
    write_audit_log(
        db, admin_id=admin.id, action="ai_core.content.approve",
        entity_type="content_queue", entity_id=content_id, request=request,
    )
    db.commit()
    return {"status": "approved", "content_id": content_id}


@router.post("/content/reject/{content_id}")
def reject_content_draft(
    content_id: str,
    request: Request,
    admin=Depends(get_current_superadmin),
    db: Session = Depends(get_db),
):
    from app.models.models import ContentStatus

    content = _get_content_or_404(content_id, db)
    content.status = ContentStatus.REJECTED
    write_audit_log(
        db, admin_id=admin.id, action="ai_core.content.reject",
        entity_type="content_queue", entity_id=content_id, request=request,
    )
    db.commit()
    return {"status": "rejected", "content_id": content_id}
