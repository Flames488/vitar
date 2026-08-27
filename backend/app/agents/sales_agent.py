"""
Vitar AI Core — Sales Agent

Moves leads through the pipeline (new -> contacted -> replied ->
trial_started -> paid) with AI-drafted WhatsApp outreach, gated behind
human approval before anything actually sends.

Two Celery tasks:
  draft_outreach_for_new_leads — AI-drafts a first-contact (or follow-up)
    message for the not-yet-exhausted leads closest to home first (by
    OUTREACH_PRIORITY_AREAS order, lead score breaking ties), inserts as a
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
from sqlalchemy import and_, case, func, or_

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

def _system_prompt() -> str:
    """Built at call time so OUTREACH_HOME_CITY flows into the copy — the
    message should read as coming from someone local, not a bulk sender."""
    home_city = settings.OUTREACH_HOME_CITY
    return f"""You are writing a short first-contact WhatsApp message from the Vitar team to \
the owner or manager of a private clinic in Nigeria. Vitar (livevault.cloud) is a small \
Nigerian company based in {home_city} that makes a simple tool for clinics: patients book \
appointments online instead of calling in and playing phone tag, fill in their own \
registration details on their phone before they arrive instead of re-doing the same paper \
form every visit, and get an automatic WhatsApp reminder before their appointment so fewer of \
them forget to show up. Billing is in Naira via Paystack: Starter is ₦6,000/month, Pro is \
₦15,000/month.

Write the way one person messages another on WhatsApp — warm, plain, and brief. Sound like a \
real {home_city} person reaching out, not a company broadcast. NO marketing or software words \
("solution", "platform", "SaaS", "streamline", "leverage", "revolutionise", "management \
software", "cutting-edge", "seamless"). NO grand vision talk about "transforming healthcare \
in Nigeria". Keep it to about 4-5 short sentences — clinic staff skim WhatsApp.

Cover these beats, roughly one sentence each, but vary their order and wording between \
messages:
- A friendly greeting that says who this is: a message from the Vitar team, a small \
{home_city}-based company. Use the clinic's name naturally.
- One real front-desk headache, stated as a plain fact about running any clinic (phone tag \
over bookings, re-filling the same paper form every visit, patients forgetting appointments). \
NOT a guess about this specific clinic — avoid anything that signals you're speculating about \
them ("I'm sure you...", "you probably...", "likely", "no doubt", "I bet", "I imagine", "I'd \
guess", and any other phrasing with that same guessing effect). If a sentence reads like \
you're assuming something about this clinic rather than stating a general fact, rewrite it.
- Name Vitar and pair one or two concrete things it does with what the clinic gets out of it \
(less back-and-forth for the front desk, fewer empty appointment slots) — not a feature list.
- The offer, in its own sentence: Vitar sets the whole thing up for them and the first month \
is free, then it's the normal monthly price. This is the main reason to reply, so don't bury \
it.
- A soft, low-pressure closing question. Offer a quick call or — since Vitar is local — a \
short visit to show them how it works. Not a hard call-to-action, not a link. Vary the exact \
wording of this question every message; never default to a single phrasing like "Are you open \
to exploring...".

Output ONLY the message text itself — no preamble like "Here's a draft..." or "For \
{{clinic}}, here's a message:", no meta-commentary before or after, no quotation marks \
wrapping it, no labels, no separate sign-off block. Nothing but what a real person would type \
into the chat.

Do not fabricate specific claims about the clinic (their patient volume, the software they \
use now, their size) — you only know their name and that they're a private clinic.

This message is one of several going to different clinics in the same batch. Genuinely vary \
the wording, the order of the beats, which headache and which benefit you lead with, and the \
closing question. Near-identical messages sent to many numbers are exactly what gets a \
WhatsApp number flagged as spam, so real variation between messages matters as much as the \
tone of any single one."""


def _proximity_rank_expr():
    """SQL ordering key for closest-first outreach: 0..N-1 for a lead in the
    Nth OUTREACH_PRIORITY_AREAS entry (matched on Lead.area, or the area
    name appearing in Lead.address when Lead.area is unset), then N for any
    other lead in OUTREACH_HOME_CITY, then N+1 for everything else. Lower =
    drafted/contacted sooner."""
    areas = settings.outreach_priority_areas
    whens = []
    for i, area in enumerate(areas):
        whens.append((
            or_(
                func.lower(Lead.area) == area.lower(),
                and_(Lead.area.is_(None), Lead.address.ilike(f"%{area}%")),
            ),
            i,
        ))
    whens.append((
        func.lower(Lead.city) == settings.OUTREACH_HOME_CITY.lower(),
        len(areas),
    ))
    return case(*whens, else_=len(areas) + 1)


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
        system=_system_prompt(),
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

            # Closest-first: leads in the earliest-listed priority areas are
            # drafted before anything further out, with lead score only
            # breaking ties within the same proximity band.
            candidates = (
                db.query(Lead)
                .filter(
                    Lead.status.in_([LeadStatus.NEW, LeadStatus.CONTACTED]),
                    Lead.attempt_count < MAX_OUTREACH_ATTEMPTS,
                    ~Lead.id.in_(excluded_lead_ids),
                )
                .order_by(_proximity_rank_expr().asc(), Lead.score.desc())
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
