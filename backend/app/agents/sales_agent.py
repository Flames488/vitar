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
import re
import uuid
from datetime import timedelta
from typing import List, Optional

import httpx
from sqlalchemy import and_, or_

from app.agents.utils import is_ai_core_enabled, is_dry_run, log_agent_run
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

SYSTEM_PROMPT = """You are drafting a first-contact WhatsApp message on behalf of Vitar \
(livevault.cloud), a tool built for Nigerian private clinics that gets rid of front-desk \
chaos: patients can book an appointment online instead of calling in and playing phone tag, \
fill out their own registration details on their phone before they arrive instead of \
scribbling the same paper form every visit, and get an automatic reminder before their \
appointment so fewer people simply forget to show up. Billing is via Paystack in Naira. \
Pricing: Starter is ₦6,000/month, Pro is ₦15,000/month, both after a 30-day free trial, no \
card needed.

Output ONLY the WhatsApp message itself — nothing else. No preamble like "Here's a draft..." \
or "For {clinic}, here's a message:", no meta-commentary before or after, no quotation marks \
wrapping it, no labels. The clinic owner receiving this must see nothing but the message text \
a real person would send them.

Write a short WhatsApp message in plain, everyday language a busy clinic owner would actually \
read — NOT marketing or software jargon ("SaaS", "platform", "solution", "streamline", \
"management software"). Clinic staff skim WhatsApp, so don't pad it: structure it as four \
short beats, one sentence each (3-4 sentences total, no more):

1. Open with the clinic's name, then a real front-desk pain point, stated as something clinics \
generally deal with — phone tag over bookings, re-filling the same paper form every visit, \
missed appointments from forgotten bookings. State it as a plain fact about running a clinic, \
not a guess about THIS one specifically. This rules out an entire CATEGORY of wording, not \
just a fixed list of words — anything that signals you're speculating about them ("I'm sure",
"likely", "probably", "surely", "I bet", "no doubt", "I imagine", "I'd guess", etc., and any \
other phrasing with that same guessing effect, even ones not listed here). If a sentence reads \
like you're assuming something about this specific clinic rather than stating a fact about \
clinics in general, rewrite it.
2. Name Vitar explicitly, and pair one or two concrete things it does with the benefit it \
gives THEM specifically (e.g. less back-and-forth for staff, fewer missed slots) rather than \
just listing features.
3. Give the free trial (and that no card is needed) its own short sentence — it's the \
lowest-friction reason to say yes, don't bury it inside another sentence.
4. Close with a soft, low-pressure question inviting a reply — not a hard call-to-action or a \
link. Vary the actual wording of this question between messages; don't default to "Are you \
open to exploring..." (or any other single phrasing) every time.

Do not fabricate specific claims about the clinic (their patient volume, their current \
software, etc.) — you only know their name and that they're a private clinic.

This message is one of many being sent to different clinics in the same batch. Vary your \
exact wording, sentence order, and which pain point/benefit you lead with each time — including \
the closing question, not just the opener. Do not default to the same sentence structure every \
time. Near-identical messages sent to many different numbers are exactly what gets flagged as \
spam, so genuine variation between \
messages matters as much as the tone of any single one."""


def _draft_message(clinic_name: str, avoid_phrases: Optional[List[str]] = None) -> str:
    prompt = f"Draft the WhatsApp message for: {clinic_name}"
    if avoid_phrases:
        # Concrete anti-repetition signal, not just relying on sampling
        # randomness — the system prompt's "vary your wording" instruction
        # is easy for the model to ignore across independent calls since
        # each one otherwise has zero visibility into what earlier drafts
        # in this same batch actually said. Covers both the opening and
        # closing sentence — an early version of this only fed back
        # openers, and the model just converged on a repeated closing
        # question ("Are you open to exploring...") instead.
        examples = "\n".join(f"- {p}" for p in avoid_phrases)
        prompt += (
            "\n\nOpening and closing sentences already used elsewhere in this batch — do "
            "not reuse these or closely paraphrase them, phrase both differently:\n" + examples
        )
    return _strip_preamble(generate(
        prompt=prompt,
        agent_name="sales_agent",
        system=SYSTEM_PROMPT,
    ))


# The system prompt already forbids this, but LLM instruction-following isn't
# 100% reliable and this specific failure mode (a "Here's a draft..." intro
# line) has actually shown up in production output — a defensive strip here
# means it can never reach a real clinic even if the prompt-level instruction
# is ignored on some future call. Matches a leading line ending in ":" that
# reads like meta-commentary about the message rather than being part of it.
_PREAMBLE_RE = re.compile(
    r"^(here'?s?\b.{0,80}?:|sure[,!]?.{0,80}?:|for [^\n:]{1,60},?\s+here'?s?\b.{0,80}?:)\s*\n+",
    re.IGNORECASE,
)


def _strip_preamble(text: str) -> str:
    return _PREAMBLE_RE.sub("", text.strip()).strip().strip('"')


# ── Draft outreach ───────────────────────────────────────────────────────────

@celery.task(bind=True, queue="ai")
def draft_outreach_for_new_leads(self, batch_size: int = 20):
    if not is_ai_core_enabled():
        logger.info("draft_outreach_for_new_leads: AI_CORE_ENABLED=false — no-op")
        return

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
            #   - no outreach_template for this lead already sitting at
            #     pending_approval/approved — an existing undecided draft
            #     must be resolved (approved/rejected) before drafting a
            #     second one for the same lead, regardless of cooldown.
            #     Re-running this task after a rejection used to draft a
            #     duplicate for any lead with a still-approved-but-unsent
            #     draft from an earlier run.
            excluded_lead_ids = (
                db.query(ContentQueue.lead_id)
                .filter(
                    ContentQueue.content_type == ContentType.OUTREACH_TEMPLATE,
                    ContentQueue.lead_id.isnot(None),
                    or_(
                        ContentQueue.status.in_([ContentStatus.PENDING_APPROVAL, ContentStatus.APPROVED]),
                        and_(
                            ContentQueue.status == ContentStatus.PUBLISHED,
                            ContentQueue.published_at >= cooldown_cutoff,
                        ),
                    ),
                )
            )

            candidates = (
                db.query(Lead)
                .filter(
                    Lead.status.in_([LeadStatus.NEW, LeadStatus.CONTACTED]),
                    Lead.attempt_count < MAX_OUTREACH_ATTEMPTS,
                    ~Lead.id.in_(excluded_lead_ids),
                )
                .order_by(Lead.score.desc())
                .limit(batch_size)
                .all()
            )
            run.items_processed = len(candidates)

            # Opening + closing sentences from this run only (not persisted)
            # — passed to each next draft so the batch doesn't read like a
            # mail-merge template. Capped at the last 5 drafts' worth (10
            # phrases) so the prompt doesn't grow unbounded on a large batch.
            recent_phrases: List[str] = []

            for lead in candidates:
                try:
                    body = _draft_message(lead.clinic_name, avoid_phrases=recent_phrases[-10:])
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

                sentences = [s.strip() for s in body.split(".") if s.strip()]
                if sentences:
                    recent_phrases.append(sentences[0][:100])
                    if len(sentences) > 1:
                        recent_phrases.append(sentences[-1][:100])

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
    if not is_ai_core_enabled():
        logger.info("send_approved_outreach: AI_CORE_ENABLED=false — no-op")
        return

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
