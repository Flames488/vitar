"""
Vitar — Admin Dashboard: AI Core Agents

POST /api/v1/admin/agents/lead-hunter/run   Manually trigger a Lead Hunter run

More endpoints (Sales Agent, Content Agent, Customer Success actions) are
added here in later AI Core build phases — this file grows incrementally
rather than being split per agent, matching how admin_clinics.py /
admin_users.py etc. are each one cohesive file per admin area.
"""
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from typing import Optional

from app.core.security import get_current_superadmin
from app.services.audit_service import write_audit_log
from app.core.database import get_db
from sqlalchemy.orm import Session

router = APIRouter(prefix="/admin/agents", tags=["Admin — AI Agents"])


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
