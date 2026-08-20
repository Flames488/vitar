"""
Vitar — Feature Spotlight content.

Sent Monday/Wednesday/Friday to registered clinic owners
(app.workers.tasks.send_feature_spotlight). Copy is generated fresh each
send by Groq (via app.services.ai_provider, same provider already used by
the AI Core agents) so wording never repeats verbatim, even when the same
underlying feature comes back around in the rotation.

FEATURE_FACTS is the ground truth handed to the model — short, factual
one-liners about capabilities that actually exist in the product today.
The model is instructed to write only from these facts (no invented
stats, no roadmap teasers). Which fact to spotlight still rotates
deterministically by day-ordinal, so every real feature gets fair airtime
regardless of what the model does with the wording.

If the Groq call fails or returns something unusable, FALLBACK_SPOTLIGHTS
below is the safety net — pre-written, always available, so a send never
silently skips because of an AI-provider outage.
"""
import json
import logging

logger = logging.getLogger("vitar.feature_spotlight")

FEATURE_FACTS = [
    "Vitar clinics show up in the public patient search on livevault.cloud — patients can find and book a clinic directly, with no QR code or shared link required.",
    "Patients can complete their own registration from their phone before arriving at the clinic, so the front desk isn't filling out paperwork on their behalf.",
    "Every clinic gets a public booking page that works in any browser with no app download — a patient picks a doctor, a time, and a reason for the visit in under a minute.",
    "Every booked appointment automatically gets reminders sent across WhatsApp, SMS, and email, without any staff member needing to remember to call the patient.",
    "Vitar scores each upcoming appointment's no-show risk from the patient's booking history, so front-desk staff know which patients are worth a personal follow-up call.",
    "Each clinic has its own QR code that arriving patients can scan to check themselves in instantly, instead of queuing at the front desk.",
    "Vitar's analytics dashboard automatically tracks booking volume, no-show trends, and revenue — no spreadsheet required.",
    "When a patient cancels an appointment, Vitar can automatically offer that freed-up slot to patients on the waiting list instead of it going unused.",
]

FALLBACK_SPOTLIGHTS = [
    {
        "subject": "Get found by patients searching for your clinic",
        "headline": "Patients can already search for you on Vitar",
        "body_html": "<p>Your clinic shows up in Vitar's patient search — no QR code or shared link needed. Make sure your name, address, and services are filled in under Settings so patients find you easily.</p>",
    },
    {
        "subject": "Skip the front-desk paperwork with e-registration",
        "headline": "Let patients register before they arrive",
        "body_html": "<p>Patients can fill in their registration from their phone before they get to your clinic — no clipboard, no queue at the front desk.</p>",
    },
    {
        "subject": "Your booking page needs no app download",
        "headline": "One link, zero downloads, more booked slots",
        "body_html": "<p>Your public booking page works in any browser. Share the link on WhatsApp status, Instagram bio, or signage — every extra place it's posted is another way patients find you.</p>",
    },
    {
        "subject": "Reminders are already cutting your no-shows",
        "headline": "WhatsApp, SMS, and email — automatically",
        "body_html": "<p>Every booking gets automatic reminders across WhatsApp, SMS, and email — no one on your team has to remember to call.</p>",
    },
    {
        "subject": "Vitar flags which appointments are at risk",
        "headline": "Know which patients might not show up",
        "body_html": "<p>Vitar scores each appointment's no-show risk from patient history — check your dashboard each morning for who's worth a personal follow-up.</p>",
    },
    {
        "subject": "QR check-in speeds up your waiting room",
        "headline": "Check patients in with a scan, not a queue",
        "body_html": "<p>Your clinic's QR code lets arriving patients check in instantly. Reprint it anytime under Settings → QR Code.</p>",
    },
    {
        "subject": "See your clinic's numbers at a glance",
        "headline": "Your analytics dashboard is already tracking this",
        "body_html": "<p>Booking volume, no-shows, and revenue are tracked automatically on your Analytics page — worth a quick look each week.</p>",
    },
    {
        "subject": "A full slot doesn't have to mean a lost patient",
        "headline": "The waiting list fills cancellations automatically",
        "body_html": "<p>When a patient cancels, Vitar can offer that slot to your waiting list automatically, instead of it sitting empty.</p>",
    },
]

_SYSTEM_PROMPT = """You write short marketing emails for Vitar, a clinic-management \
software product used by Nigerian healthcare clinics. Your audience is the clinic \
owner/administrator who already has an active Vitar account.

Rules:
- Write ONLY about the single fact given to you. Never invent a feature, statistic, \
or claim that isn't in that fact.
- Tone: professional, warm, concise — like a well-run SaaS product update, not a \
hard sales pitch. No hype words like "revolutionary" or "game-changing".
- Keep body_html to exactly one short paragraph (1-2 sentences), wrapped in a single \
<p> tag. No markdown, no lists, no extra HTML tags.
- subject: under 60 characters, specific, no clickbait, no emoji.
- headline: under 70 characters, a plain-language restatement of the fact's benefit.
- Respond with ONLY a raw JSON object, no markdown fences, no commentary: \
{"subject": "...", "headline": "...", "body_html": "..."}"""

_CLOSER_PROMPT = {
    0: 'Write one short, professional Monday motivational sentence (under 15 words) '
       'for a clinic owner starting their work week. No emoji, no cliches like "Monday blues". '
       'Respond with ONLY the sentence, no quotes.',
    4: 'Write one short, professional Friday sign-off sentence (under 15 words) wishing '
       'a clinic owner a good weekend. No emoji. Respond with ONLY the sentence, no quotes.',
}


def _pick_fact(day_ordinal: int) -> str:
    return FEATURE_FACTS[day_ordinal % len(FEATURE_FACTS)]


def generate_spotlight(day_ordinal: int, weekday: int) -> dict:
    """Returns {"subject", "headline", "body_html", "closer"|None}. Tries
    Groq first for unique wording every send; falls back to the static
    pool (still rotated by day_ordinal, so it stays deterministic and
    varied) if the AI call fails or returns unusable output."""
    fact = _pick_fact(day_ordinal)
    try:
        from app.services.ai_provider import generate

        raw = generate(
            prompt=f"Write the email for this fact: {fact}",
            agent_name="feature_spotlight",
            system=_SYSTEM_PROMPT,
        )
        cleaned = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        data = json.loads(cleaned)
        if not all(k in data and data[k] for k in ("subject", "headline", "body_html")):
            raise ValueError("missing required field in AI response")
        result = {
            "subject": data["subject"],
            "headline": data["headline"],
            "body_html": data["body_html"],
        }
    except Exception as exc:
        logger.warning(f"generate_spotlight: AI generation failed, using fallback — {exc}")
        result = FALLBACK_SPOTLIGHTS[day_ordinal % len(FALLBACK_SPOTLIGHTS)]

    result["closer"] = _generate_closer(weekday)
    return result


def _generate_closer(weekday: int) -> str | None:
    """weekday: Python-style, Monday=0 ... Sunday=6. Only Monday/Friday get one."""
    prompt = _CLOSER_PROMPT.get(weekday)
    if not prompt:
        return None
    try:
        from app.services.ai_provider import generate

        line = generate(prompt=prompt, agent_name="feature_spotlight").strip().strip('"')
        return line if line else _FALLBACK_CLOSERS[weekday]
    except Exception as exc:
        logger.warning(f"_generate_closer: AI generation failed, using fallback — {exc}")
        return _FALLBACK_CLOSERS[weekday]


_FALLBACK_CLOSERS = {
    0: "New week, clean slate — let's make it a good one.",
    4: "You made it — have a great weekend!",
}
