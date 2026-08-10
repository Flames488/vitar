"""
Vitar AI Core — Content Agent

Drafts marketing content (social posts) for Vitar's own growth marketing —
not outreach, Sales Agent owns that. Nothing here ever auto-publishes:
approved content just sits at status='approved', ready for manual posting
or a future publishing integration.
"""
import logging
import random
import uuid

from app.agents.utils import log_agent_run
from app.models.models import ContentQueue, ContentStatus, ContentType
from app.core.database import SessionLocal
from app.services.ai_provider import generate
from app.services.notifications import notify
from app.workers.celery_app import celery

logger = logging.getLogger("vitar.ai_core.content_agent")

# Rotated across runs via random.sample (no duplicates within a single run —
# see draft_weekly_content). Each entry is a short brief the system prompt
# expands into a full post; category prefix keeps the mix balanced across
# feature highlights, pain points, and testimonial-style posts.
TOPICS = [
    # Feature highlights
    ("feature", "the public clinic search directory — patients can find and book a clinic by name without needing a link or QR code first"),
    ("feature", "installing Vitar as a home-screen app (PWA) — no app store, works like a native app"),
    ("feature", "doctors' consultation fee and contact info being visible to patients before they book"),
    ("feature", "automated Paystack billing — clinics never have to manually track who's paid"),
    # Pain points Vitar solves
    ("pain_point", "the front-desk chaos of manually tracking appointments in a notebook or spreadsheet"),
    ("pain_point", "how much revenue a single missed reminder (and the resulting no-show) actually costs a clinic"),
    ("pain_point", "losing patient history when paper records get misplaced"),
    ("pain_point", "the back-and-forth phone tag of manual appointment confirmations"),
    # Testimonial-style (no fabricated quotes/clinics — see system prompt)
    ("testimonial_style", "what it feels like for a front-desk staff member on the first week after switching to Vitar"),
    ("testimonial_style", "the moment a clinic owner realizes their no-show rate actually dropped"),
]

SYSTEM_PROMPT = """You are drafting a short social media post (LinkedIn/Twitter style, \
2-4 sentences, no hashtag spam — at most 2 relevant hashtags) for Vitar, a clinic/hospital \
management SaaS for Nigerian private clinics (livevault.cloud). Vitar handles appointment \
booking, patient records, and automated SMS/WhatsApp/email reminders.

CRITICAL: never invent a specific testimonial quote, a named clinic, a specific statistic \
you weren't given, or any claim you can't back up. For a "testimonial-style" brief, write in \
a relatable, benefit-focused voice WITHOUT attributing it to any named person or clinic —
describe the feeling/outcome generically ("Imagine your front desk...", "Clinics using Vitar \
typically see...") rather than fabricating "Dr. X said...". Keep the tone genuine and \
specific to the brief given, not generic SaaS marketing filler."""


def _draft_post(category: str, brief: str) -> str:
    return generate(
        prompt=f"Write the post. Category: {category}. Brief: {brief}",
        agent_name="content_agent",
        system=SYSTEM_PROMPT,
    )


@celery.task(bind=True, queue="ai")
def draft_weekly_content(self, count: int = 3):
    with log_agent_run("content_agent", "draft_weekly_content") as run:
        chosen = random.sample(TOPICS, k=min(count, len(TOPICS)))
        run.items_processed = len(chosen)

        db = SessionLocal()
        drafted = 0
        try:
            for category, brief in chosen:
                try:
                    body = _draft_post(category, brief)
                except Exception:
                    logger.error("draft_weekly_content: generate() failed for topic=%r", brief, exc_info=True)
                    continue

                db.add(ContentQueue(
                    id=str(uuid.uuid4()),
                    content_type=ContentType.SOCIAL_POST,
                    body=body,
                    target_platform="social",
                    status=ContentStatus.PENDING_APPROVAL,
                    created_by_agent="content_agent",
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
                event_type="content_ready",
                agent_name="content_agent",
                message=f"{drafted} content drafts ready for review",
                link_path="/admin/agents/content",
            )
