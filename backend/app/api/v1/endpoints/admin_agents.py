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

health_signals_router = APIRouter(prefix="/admin/health-signals", tags=["Admin — Health Signals"])

# Shared notification feed for all four agents (agent_notifications table,
# see app/services/notifications.py) — the dashboard's bell (this router)
# and the Telegram bot (Phase 7) both read from it independently.
notifications_router = APIRouter(prefix="/admin/notifications", tags=["Admin — Notifications"])


class LeadHunterRunRequest(BaseModel):
    city: str
    query: str = "private clinic"
    area: Optional[str] = None


@router.post("/lead-hunter/run", status_code=202)
def run_lead_hunter(
    body: LeadHunterRunRequest,
    request: Request,
    admin=Depends(get_current_superadmin),
    db: Session = Depends(get_db),
):
    """Enqueues a Lead Hunter run immediately — the dashboard's 'Run now' button."""
    from app.agents.lead_hunter import hunt_leads

    task = hunt_leads.delay(city=body.city, query=body.query, area=body.area)

    write_audit_log(
        db,
        admin_id=admin.id,
        action="ai_core.lead_hunter.run",
        entity_type="agent_run",
        new_data={"city": body.city, "query": body.query, "area": body.area, "task_id": task.id},
        request=request,
    )
    db.commit()

    return {
        "status": "queued",
        "task_id": task.id,
        "city": body.city,
        "query": body.query,
        "area": body.area,
    }


@router.get("/{agent_name}/runs")
def list_agent_runs(
    agent_name: str,
    limit: int = 10,
    admin=Depends(get_current_superadmin),
    db: Session = Depends(get_db),
):
    """Run history for one agent's dedicated tab — last N agent_runs rows."""
    from app.models.models import AgentRun

    rows = (
        db.query(AgentRun)
        .filter(AgentRun.agent_name == agent_name)
        .order_by(AgentRun.started_at.desc())
        .limit(min(limit, 100))
        .all()
    )
    return {
        "runs": [
            {
                "id": r.id,
                "task_name": r.task_name,
                "status": r.status.value if hasattr(r.status, "value") else r.status,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "finished_at": r.finished_at.isoformat() if r.finished_at else None,
                "items_processed": r.items_processed,
                "items_created": r.items_created,
                "error_message": r.error_message,
            }
            for r in rows
        ]
    }


# ── Sales Agent: draft approval ─────────────────────────────────────────────

def _get_content_or_404(content_id: str, db: Session):
    from app.models.models import ContentQueue
    row = db.query(ContentQueue).filter(ContentQueue.id == content_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Content not found")
    return row


def _serialize_content(c, lead_clinic_name: Optional[str] = None) -> dict:
    return {
        "id": c.id,
        "content_type": c.content_type.value if hasattr(c.content_type, "value") else c.content_type,
        "body": c.body,
        "status": c.status.value if hasattr(c.status, "value") else c.status,
        "created_by_agent": c.created_by_agent,
        "lead_id": c.lead_id,
        "lead_clinic_name": lead_clinic_name,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "published_at": c.published_at.isoformat() if c.published_at else None,
    }


@router.get("/sales/drafts")
def list_sales_drafts(
    status: Optional[str] = "pending_approval",
    limit: int = 100,
    admin=Depends(get_current_superadmin),
    db: Session = Depends(get_db),
):
    from app.models.models import ContentQueue, ContentStatus, ContentType, Lead

    q = db.query(ContentQueue).filter(ContentQueue.content_type == ContentType.OUTREACH_TEMPLATE)
    if status:
        try:
            q = q.filter(ContentQueue.status == ContentStatus(status.lower()))
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Invalid status: {status}")
    rows = q.order_by(ContentQueue.created_at.desc()).limit(min(limit, 500)).all()

    lead_names = {}
    lead_ids = [r.lead_id for r in rows if r.lead_id]
    if lead_ids:
        for lead in db.query(Lead).filter(Lead.id.in_(lead_ids)).all():
            lead_names[lead.id] = lead.clinic_name

    return {"drafts": [_serialize_content(r, lead_names.get(r.lead_id)) for r in rows]}


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


# ── Leads: list + manual status override ────────────────────────────────────

@leads_router.get("/")
def list_leads(
    status: Optional[str] = None,
    city: Optional[str] = None,
    sort_by: str = "score",
    limit: int = 100,
    admin=Depends(get_current_superadmin),
    db: Session = Depends(get_db),
):
    from app.models.models import Lead, LeadStatus

    q = db.query(Lead)
    if status:
        try:
            q = q.filter(Lead.status == LeadStatus(status.lower()))
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Invalid status: {status}")
    if city:
        q = q.filter(Lead.city == city)

    sort_col = {"score": Lead.score, "created_at": Lead.created_at}.get(sort_by, Lead.score)
    q = q.order_by(sort_col.desc())

    rows = q.limit(min(limit, 500)).all()
    return {
        "leads": [
            {
                "id": l.id,
                "clinic_name": l.clinic_name,
                "phone": l.phone,
                "city": l.city,
                "area": l.area,
                "source": l.source.value if hasattr(l.source, "value") else l.source,
                "status": l.status.value if hasattr(l.status, "value") else l.status,
                "score": l.score,
                "attempt_count": l.attempt_count,
                "created_at": l.created_at.isoformat() if l.created_at else None,
                "last_contacted_at": l.last_contacted_at.isoformat() if l.last_contacted_at else None,
            }
            for l in rows
        ],
        "total": q.count(),
    }


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
# Reuses _get_content_or_404 / _serialize_content defined above (Sales Agent
# section) — same content_queue table, just a different content_type.

@router.get("/content/drafts")
def list_content_drafts(
    status: Optional[str] = None,
    limit: int = 100,
    admin=Depends(get_current_superadmin),
    db: Session = Depends(get_db),
):
    from app.models.models import ContentQueue, ContentStatus, ContentType

    q = db.query(ContentQueue).filter(ContentQueue.content_type == ContentType.SOCIAL_POST)
    if status:
        try:
            q = q.filter(ContentQueue.status == ContentStatus(status.lower()))
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Invalid status: {status}")
    rows = q.order_by(ContentQueue.created_at.desc()).limit(min(limit, 500)).all()
    return {"drafts": [_serialize_content(r) for r in rows]}


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


# ── Customer Success: health signal triage ──────────────────────────────────

@health_signals_router.get("/")
def list_health_signals(
    status: Optional[str] = "open",
    limit: int = 100,
    admin=Depends(get_current_superadmin),
    db: Session = Depends(get_db),
):
    from app.models.models import Clinic, CustomerHealthSignal, HealthSignalStatus

    q = db.query(CustomerHealthSignal)
    if status:
        try:
            q = q.filter(CustomerHealthSignal.status == HealthSignalStatus(status.lower()))
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Invalid status: {status}")
    rows = q.order_by(CustomerHealthSignal.created_at.desc()).limit(min(limit, 500)).all()

    clinic_names = {}
    clinic_ids = [r.clinic_id for r in rows]
    if clinic_ids:
        for clinic in db.query(Clinic).filter(Clinic.id.in_(clinic_ids)).all():
            clinic_names[clinic.id] = clinic.name

    return {
        "signals": [
            {
                "id": s.id,
                "clinic_id": s.clinic_id,
                "clinic_name": clinic_names.get(s.clinic_id, "Unknown"),
                "signal_type": s.signal_type.value if hasattr(s.signal_type, "value") else s.signal_type,
                "detail": s.detail,
                "status": s.status.value if hasattr(s.status, "value") else s.status,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in rows
        ]
    }


class HealthSignalUpdateRequest(BaseModel):
    status: str  # "acknowledged" or "resolved"


@health_signals_router.patch("/{signal_id}")
def update_health_signal(
    signal_id: str,
    body: HealthSignalUpdateRequest,
    request: Request,
    admin=Depends(get_current_superadmin),
    db: Session = Depends(get_db),
):
    from app.models.models import CustomerHealthSignal, HealthSignalStatus

    signal = db.query(CustomerHealthSignal).filter(CustomerHealthSignal.id == signal_id).first()
    if not signal:
        raise HTTPException(status_code=404, detail="Health signal not found")

    try:
        new_status = HealthSignalStatus(body.status.lower())
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid status: {body.status}")
    if new_status == HealthSignalStatus.OPEN:
        raise HTTPException(status_code=422, detail="Cannot manually reopen a signal to 'open'")

    old_status = signal.status
    signal.status = new_status
    write_audit_log(
        db, admin_id=admin.id, action="ai_core.health_signal.update",
        entity_type="customer_health_signal", entity_id=signal_id,
        old_data={"status": old_status.value if hasattr(old_status, "value") else old_status},
        new_data={"status": new_status.value},
        request=request,
    )
    db.commit()
    return {"status": "updated", "signal_id": signal_id, "new_status": new_status.value}


# ── Notification center (dashboard bell) ────────────────────────────────────

def _serialize_notification(n) -> dict:
    return {
        "id": n.id,
        "event_type": n.event_type.value if hasattr(n.event_type, "value") else n.event_type,
        "agent_name": n.agent_name,
        "message": n.message,
        "related_id": n.related_id,
        "link_path": n.link_path,
        "is_read": n.is_read,
        "created_at": n.created_at.isoformat() if n.created_at else None,
    }


@notifications_router.get("/")
def list_notifications(
    unread_only: bool = False,
    limit: int = 50,
    admin=Depends(get_current_superadmin),
    db: Session = Depends(get_db),
):
    from app.models.models import AgentNotification

    q = db.query(AgentNotification)
    if unread_only:
        q = q.filter(AgentNotification.is_read == False)  # noqa: E712
    rows = q.order_by(AgentNotification.created_at.desc()).limit(min(limit, 200)).all()
    return {"notifications": [_serialize_notification(n) for n in rows]}


@notifications_router.get("/unread-count")
def unread_notification_count(
    admin=Depends(get_current_superadmin),
    db: Session = Depends(get_db),
):
    from app.models.models import AgentNotification

    count = db.query(AgentNotification).filter(AgentNotification.is_read == False).count()  # noqa: E712
    return {"count": count}


@notifications_router.patch("/{notification_id}/read")
def mark_notification_read(
    notification_id: str,
    admin=Depends(get_current_superadmin),
    db: Session = Depends(get_db),
):
    from app.models.models import AgentNotification

    n = db.query(AgentNotification).filter(AgentNotification.id == notification_id).first()
    if not n:
        raise HTTPException(status_code=404, detail="Notification not found")
    n.is_read = True
    db.commit()
    return {"status": "ok"}


@notifications_router.post("/mark-all-read")
def mark_all_notifications_read(
    admin=Depends(get_current_superadmin),
    db: Session = Depends(get_db),
):
    from app.models.models import AgentNotification

    db.query(AgentNotification).filter(AgentNotification.is_read == False).update(  # noqa: E712
        {"is_read": True}, synchronize_session=False
    )
    db.commit()
    return {"status": "ok"}


# ── Agents overview (dashboard Overview page) ───────────────────────────────

# Expected run interval per agent, in hours — drives the status dot (green/
# yellow/red). Sales Agent has two tasks (draft daily, send every 15 min);
# the draft task's cadence is used here since that's the agent's primary,
# human-visible cadence.
_EXPECTED_INTERVAL_HOURS = {
    "lead_hunter": 24,
    "sales_agent": 24,
    "content_agent": 24 * 7,
    "customer_success": 24,
}
# How much slack beyond the expected interval before a silent (non-failed)
# agent counts as "overdue" rather than "green" — covers ordinary scheduling
# jitter without flagging a false alarm the moment a run is a few minutes late.
_OVERDUE_GRACE_MULTIPLIER = 1.5

# Paid-client goal this whole system exists to move — see the build spec's
# own framing ("20 paying clients by December 2026").
GOAL_TARGET_CLIENTS = 20
GOAL_DEADLINE = "2026-12-31"


def _agent_status(db, agent_name: str) -> dict:
    from app.models.models import AgentRun

    last_run = (
        db.query(AgentRun)
        .filter(AgentRun.agent_name == agent_name)
        .order_by(AgentRun.started_at.desc())
        .first()
    )
    if not last_run:
        return {"status": "yellow", "last_run": None}

    status_value = last_run.status.value if hasattr(last_run.status, "value") else last_run.status
    if status_value == "failed":
        dot = "red"
    else:
        finished = last_run.finished_at or last_run.started_at
        overdue_after = _EXPECTED_INTERVAL_HOURS.get(agent_name, 24) * _OVERDUE_GRACE_MULTIPLIER
        hours_since = (utcnow() - finished).total_seconds() / 3600
        dot = "yellow" if hours_since > overdue_after else "green"

    return {
        "status": dot,
        "last_run": {
            "task_name": last_run.task_name,
            "status": status_value,
            "started_at": last_run.started_at.isoformat() if last_run.started_at else None,
            "finished_at": last_run.finished_at.isoformat() if last_run.finished_at else None,
            "items_processed": last_run.items_processed,
            "items_created": last_run.items_created,
            "error_message": last_run.error_message,
        },
    }


@router.get("/overview")
def agents_overview(
    admin=Depends(get_current_superadmin),
    db: Session = Depends(get_db),
):
    from app.models.models import (
        Clinic, ContentQueue, ContentStatus, ContentType, CustomerHealthSignal,
        HealthSignalStatus, Lead, LeadStatus, Subscription, SubscriptionStatus,
    )

    lead_hunter = _agent_status(db, "lead_hunter")
    lead_hunter["new_leads"] = db.query(Lead).filter(Lead.status == LeadStatus.NEW).count()

    sales_agent = _agent_status(db, "sales_agent")
    sales_agent["pending_approval"] = db.query(ContentQueue).filter(
        ContentQueue.content_type == ContentType.OUTREACH_TEMPLATE,
        ContentQueue.status == ContentStatus.PENDING_APPROVAL,
    ).count()
    month_start = utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    leads_this_month = db.query(Lead).filter(Lead.created_at >= month_start).count()
    paid_this_month = db.query(Lead).filter(Lead.created_at >= month_start, Lead.status == LeadStatus.PAID).count()
    sales_agent["conversion_rate"] = round(paid_this_month / leads_this_month, 3) if leads_this_month else 0.0

    content_agent = _agent_status(db, "content_agent")
    content_agent["pending_approval"] = db.query(ContentQueue).filter(
        ContentQueue.content_type == ContentType.SOCIAL_POST,
        ContentQueue.status == ContentStatus.PENDING_APPROVAL,
    ).count()

    customer_success = _agent_status(db, "customer_success")
    customer_success["open_signals"] = db.query(CustomerHealthSignal).filter(
        CustomerHealthSignal.status == HealthSignalStatus.OPEN,
    ).count()

    paid_clients = (
        db.query(Clinic)
        .join(Subscription, Subscription.clinic_id == Clinic.id)
        .filter(Subscription.status == SubscriptionStatus.ACTIVE)
        .count()
    )

    return {
        "goal": {
            "target": GOAL_TARGET_CLIENTS,
            "current": paid_clients,
            "deadline": GOAL_DEADLINE,
        },
        "agents": {
            "lead_hunter": lead_hunter,
            "sales_agent": sales_agent,
            "content_agent": content_agent,
            "customer_success": customer_success,
        },
    }
