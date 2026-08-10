"""
Vitar AI Core — Sales Agent

Moves leads through the pipeline (new -> contacted -> replied ->
trial_started -> paid) with AI-drafted WhatsApp outreach, gated behind
human approval before anything actually sends.

Two Celery tasks:
  draft_outreach_for_new_leads — AI-drafts a first-contact (or follow-up)
    message for the highest-scored not-yet-exhausted leads, inserts as a
    pending_approval content_queue row. Never sends anything itself.
  send_approved_outreach — sends whatever's been approved via Wabizz
    (or the stub, if WABIZZ_OUTREACH_ENABLED=false or DRY_RUN=true), and
    separately sweeps for leads that have hit the 2-attempt cooldown limit
    with no reply, auto-flipping them to 'lost'.

Sending routes through Wabizz (getwabizz.com), not a direct Meta Cloud API
integration — Vitar's own WhatsApp Business number is connected to Wabizz
like any other Wabizz customer would be. See WABIZZ_OUTREACH_ENABLED's
docstring in config.py for why this defaults to false.
"""
import logging
import uuid
from datetime import timedelta

import httpx

from app.agents.utils import is_dry_run, log_agent_run
from app.core.config import settings
from app.core.database import SessionLocal
from app.core.utils import utcnow
from app.models.models import ContentQueue, ContentStatus, ContentType, Lead, LeadStatus
from app.services.ai_provider import generate
from app.services.notifications import notify
from app.workers.celery_app import celery

logger = logging.getLogger("vitar.ai_core.sales_agent")

# How many days an outreach attempt "counts against" a lead before a follow-up
# is allowed again — avoids messaging the same clinic every single run.
OUTREACH_COOLDOWN_DAYS = 7

# After this many actually-sent outreach attempts with no reply, a lead is
# auto-retired rather than contacted a third time.
MAX_OUTREACH_ATTEMPTS = 2

SYSTEM_PROMPT = """You are drafting a first-contact WhatsApp message on behalf of Vitar, \
a clinic/hospital management SaaS for Nigerian private clinics (livevault.cloud). Vitar \
handles appointment booking, patient records, and automated SMS/WhatsApp/email reminders \
that reduce no-shows. Billing is via Paystack in Naira. Pricing: Starter is ₦6,000/month, \
Pro is ₦15,000/month, both after a 30-day free trial with no credit card required.

Write a short, warm, professional WhatsApp message (3-5 sentences max) introducing Vitar \
to the clinic by name. Mention the free trial. Do not be pushy or use excessive emoji. \
Do not fabricate specific claims about the clinic (their patient volume, their current \
software, etc.) — you only know their name and that they're a private clinic. End with a \
soft, low-pressure question inviting a reply, not a hard call-to-action link."""


def _draft_message(clinic_name: str) -> str:
    return generate(
        prompt=f"Draft the WhatsApp message for: {clinic_name}",
        agent_name="sales_agent",
        system=SYSTEM_PROMPT,
    )


# ── Draft outreach ───────────────────────────────────────────────────────────

@celery.task(bind=True, queue="ai")
def draft_outreach_for_new_leads(self, batch_size: int = 20):
    with log_agent_run("sales_agent", "draft_outreach_for_new_leads") as run:
        db = SessionLocal()
        drafted = 0
        try:
            cooldown_cutoff = utcnow() - timedelta(days=OUTREACH_COOLDOWN_DAYS)

            # Leads eligible for a (first or follow-up) outreach draft:
            #   - status is 'new' (never contacted) or 'contacted' (no reply
            #     yet, follow-up candidate)
            #   - hasn't hit the attempt cap (that's send_approved_outreach's
            #     job to retire, not this task's job to skip silently)
            #   - no outreach_template for this lead actually SENT within
            #     the cooldown window
            recently_outreached_lead_ids = (
                db.query(ContentQueue.lead_id)
                .filter(
                    ContentQueue.content_type == ContentType.OUTREACH_TEMPLATE,
                    ContentQueue.status == ContentStatus.PUBLISHED,  # PUBLISHED = actually sent, see send_approved_outreach
                    ContentQueue.published_at >= cooldown_cutoff,
                    ContentQueue.lead_id.isnot(None),
                )
            )

            candidates = (
                db.query(Lead)
                .filter(
                    Lead.status.in_([LeadStatus.NEW, LeadStatus.CONTACTED]),
                    Lead.attempt_count < MAX_OUTREACH_ATTEMPTS,
                    ~Lead.id.in_(recently_outreached_lead_ids),
                )
                .order_by(Lead.score.desc())
                .limit(batch_size)
                .all()
            )
            run.items_processed = len(candidates)

            for lead in candidates:
                try:
                    body = _draft_message(lead.clinic_name)
                except Exception:
                    logger.error("draft_outreach_for_new_leads: generate() failed for lead=%s", lead.id, exc_info=True)
                    continue

                db.add(ContentQueue(
                    id=str(uuid.uuid4()),
                    content_type=ContentType.OUTREACH_TEMPLATE,
                    body=body,
                    status=ContentStatus.PENDING_APPROVAL,
                    created_by_agent="sales_agent",
                    lead_id=lead.id,
                ))
                drafted += 1

            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

        run.items_created = drafted
        if drafted > 0:
            notify(
                event_type="outreach_ready",
                agent_name="sales_agent",
                message=f"{drafted} outreach drafts ready for review",
                link_path="/admin/agents/sales",
            )


# ── Sending (Wabizz-routed, or stub) ────────────────────────────────────────

def _send_via_wabizz(phone: str, message: str) -> bool:
    """Real send path. Returns True on success. Raises on a hard failure —
    caller decides how to handle (this run's item is simply not marked sent)."""
    resp = httpx.post(
        f"{settings.WABIZZ_API_BASE.rstrip('/')}/api/send",
        json={"phone": phone, "message": message},
        headers={"Authorization": f"Bearer {settings.WABIZZ_API_KEY}"},
        timeout=20,
    )
    resp.raise_for_status()
    return True


def _send_outreach(phone: str, message: str) -> bool:
    """
    Routes to the real Wabizz send or the stub, per WABIZZ_OUTREACH_ENABLED
    and DRY_RUN. DRY_RUN always wins — a dry run must never send a real
    message even if Wabizz routing is otherwise live.
    """
    if is_dry_run() or not settings.WABIZZ_OUTREACH_ENABLED:
        logger.info(
            "send_outreach: %s — logging instead of sending to %s: %r",
            "DRY_RUN" if is_dry_run() else "WABIZZ_OUTREACH_ENABLED=false",
            phone, message[:80],
        )
        return True
    return _send_via_wabizz(phone, message)


@celery.task(bind=True, queue="ai")
def send_approved_outreach(self):
    with log_agent_run("sales_agent", "send_approved_outreach") as run:
        db = SessionLocal()
        sent = 0
        try:
            # ── Sweep first: retire leads that have exhausted their
            # attempts with no reply, so this run's sends below don't
            # include one that should've already been auto-flipped.
            stale_leads = (
                db.query(Lead)
                .filter(
                    Lead.status == LeadStatus.CONTACTED,
                    Lead.attempt_count >= MAX_OUTREACH_ATTEMPTS,
                )
                .all()
            )
            for lead in stale_leads:
                lead.status = LeadStatus.LOST
            if stale_leads:
                db.commit()

            approved = (
                db.query(ContentQueue)
                .filter(
                    ContentQueue.content_type == ContentType.OUTREACH_TEMPLATE,
                    ContentQueue.status == ContentStatus.APPROVED,
                )
                .all()
            )
            run.items_processed = len(approved)

            for draft in approved:
                lead = db.query(Lead).filter(Lead.id == draft.lead_id).first() if draft.lead_id else None
                if not lead or not lead.phone:
                    logger.warning("send_approved_outreach: skipping content_queue=%s — no lead/phone", draft.id)
                    continue

                try:
                    _send_outreach(lead.phone, draft.body)
                except Exception:
                    logger.error("send_approved_outreach: send failed for content_queue=%s", draft.id, exc_info=True)
                    continue

                draft.status = ContentStatus.PUBLISHED
                draft.published_at = utcnow()
                lead.attempt_count += 1
                lead.last_contacted_at = utcnow()
                if lead.status == LeadStatus.NEW:
                    lead.status = LeadStatus.CONTACTED
                sent += 1

            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

        run.items_created = sent


# ── Manual re-send trigger for an edited draft ──────────────────────────────
# (approve/reject/edit endpoints live in admin_agents.py and just flip
# ContentQueue.status directly — send_approved_outreach picks up 'approved'
# rows on its own next scheduled pass, no separate code path needed here.)
