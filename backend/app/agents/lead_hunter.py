"""
Vitar AI Core — Lead Hunter Agent

Scrapes Google Maps for Nigerian private clinics not yet using Vitar,
scores them, and stores them as leads (see app/models/models.py's Lead).

Rate-limit safety: caps each run at MAX_LISTINGS_PER_RUN, randomizes
2-5s delays between Playwright actions, and treats a captcha/block page
as a clean stop (log + notify), not something to retry immediately —
a block is a signal to back off, not hammer harder. Per the build spec's
own operator note: don't scale run frequency/volume until real proxy
rotation is in place.

Selector caveat: this environment has no way to run a live browser against
real Google Maps, so the scraping selectors below are a best-effort
implementation based on Google Maps' current DOM structure, not something
verified end-to-end here. Expect to need minor selector tweaks after the
first real (non-DRY_RUN) run — that's exactly the kind of thing DRY_RUN
mode can't catch, since it skips Playwright entirely.
"""
import logging
import random
import re
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.agents.utils import is_dry_run, log_agent_run
from app.core.config import settings
from app.core.database import SessionLocal
from app.models.models import Lead, LeadSource, LeadStatus
from app.services.notifications import notify
from app.workers.celery_app import celery

logger = logging.getLogger("vitar.ai_core.lead_hunter")

# ── Target cities, rotated one per day by hunt_leads_daily ─────────────────
TARGET_CITIES = ["Lagos", "Abuja", "Port Harcourt", "Ibadan"]

# ── Lead scoring weights ────────────────────────────────────────────────────
# Simple heuristic, not ML — tune after the first real batch once you see
# which leads actually convert (see the build spec's operator notes).
SCORE_WEIGHTS = {
    "has_phone": 20,
    "has_street_address": 15,
    "established_business": 25,  # review_count >= REVIEW_COUNT_THRESHOLD
    "tier1_city": 20,
    "other_city": 10,
}
REVIEW_COUNT_THRESHOLD = 10
TIER1_CITIES = {"Lagos", "Abuja"}

MAX_LISTINGS_PER_RUN = 40
MIN_ACTION_DELAY_S = 2.0
MAX_ACTION_DELAY_S = 5.0


class GoogleMapsBlockedError(Exception):
    """Raised when Playwright detects a captcha/block page."""


# ── Scoring ──────────────────────────────────────────────────────────────────

def _score_lead(has_phone: bool, has_street_address: bool, review_count: int, city: str) -> int:
    score = 0
    if has_phone:
        score += SCORE_WEIGHTS["has_phone"]
    if has_street_address:
        score += SCORE_WEIGHTS["has_street_address"]
    if review_count >= REVIEW_COUNT_THRESHOLD:
        score += SCORE_WEIGHTS["established_business"]
    score += SCORE_WEIGHTS["tier1_city"] if city in TIER1_CITIES else SCORE_WEIGHTS["other_city"]
    return min(score, 100)


def _looks_like_street_address(address: Optional[str]) -> bool:
    """Heuristic: a real street address usually starts with a house number."""
    if not address:
        return False
    first_token = address.strip().split(" ", 1)[0]
    return first_token[:1].isdigit()


# ── DRY_RUN fallback ─────────────────────────────────────────────────────────

def _fake_leads_for_dry_run(city: str) -> List[Dict[str, Any]]:
    """
    Realistic-looking fake leads so the rest of the pipeline (upsert,
    scoring, logging, notifications) can be exercised without ever
    launching a browser or hitting Google.
    """
    def _fake_phone() -> str:
        return f"+234{random.randint(700, 909)}{random.randint(1000000, 9999999)}"

    samples = [
        {"clinic_name": f"{city} Family Clinic", "phone": _fake_phone(),
         "address": f"12 Herbert Macaulay Way, {city}", "review_count": 24, "source_url": None},
        {"clinic_name": f"{city} Medical Centre", "phone": _fake_phone(),
         "address": f"{city} — Ikeja area", "review_count": 3, "source_url": None},
        {"clinic_name": f"{city} Wellness Hospital", "phone": None,
         "address": f"7 Awolowo Road, {city}", "review_count": 41, "source_url": None},
    ]
    return samples[:random.randint(2, 3)]


# ── Live scraping ────────────────────────────────────────────────────────────

def _extract_phone(text: str) -> Optional[str]:
    m = re.search(r"(\+?234[\d\s-]{7,}|0\d{10})", text)
    return m.group(1).strip() if m else None


def _extract_address(text: str) -> Optional[str]:
    for line in text.split("\n"):
        line = line.strip()
        if line and line[:1].isdigit() and len(line) > 8:
            return line
    return None


def _extract_review_count(text: str) -> int:
    m = re.search(r"\((\d[\d,]*)\)", text)
    if not m:
        return 0
    try:
        return int(m.group(1).replace(",", ""))
    except ValueError:
        return 0


def _random_delay() -> None:
    time.sleep(random.uniform(MIN_ACTION_DELAY_S, MAX_ACTION_DELAY_S))


def _scrape_google_maps(city: str, query: str, proxy: Optional[str]) -> List[Dict[str, Any]]:
    """
    Real Playwright scrape. Raises GoogleMapsBlockedError if a captcha/
    block page is detected. Caps results at MAX_LISTINGS_PER_RUN.
    """
    from playwright.sync_api import sync_playwright

    results: List[Dict[str, Any]] = []
    search_query = f"{query} in {city}, Nigeria"

    with sync_playwright() as p:
        launch_args: Dict[str, Any] = {"headless": True}
        if proxy:
            launch_args["proxy"] = {"server": proxy}
        browser = p.chromium.launch(**launch_args)
        try:
            page = browser.new_page()
            page.goto(
                f"https://www.google.com/maps/search/{search_query.replace(' ', '+')}",
                timeout=30000,
            )
            _random_delay()

            content = page.content()
            if "unusual traffic" in content.lower() or "recaptcha" in content.lower():
                raise GoogleMapsBlockedError("Captcha/block page detected")

            feed_selector = 'div[role="feed"]'
            try:
                page.wait_for_selector(feed_selector, timeout=15000)
            except Exception:
                raise GoogleMapsBlockedError("Results feed never loaded — likely blocked")

            # Scroll the results feed to load more listings.
            for _ in range(6):
                page.mouse.wheel(0, 2000)
                _random_delay()

            listings = page.query_selector_all(f'{feed_selector} > div > div[role="article"]')
            for listing in listings[:MAX_LISTINGS_PER_RUN]:
                try:
                    name_el = listing.query_selector("[aria-label]")
                    name = name_el.get_attribute("aria-label") if name_el else None
                    if not name:
                        continue

                    link_el = listing.query_selector("a")
                    source_url = link_el.get_attribute("href") if link_el else None

                    text_content = listing.inner_text()
                    results.append({
                        "clinic_name": name.strip(),
                        "phone": _extract_phone(text_content),
                        "address": _extract_address(text_content),
                        "source_url": source_url,
                        "review_count": _extract_review_count(text_content),
                    })
                except Exception:
                    continue  # one bad listing shouldn't kill the whole run
        finally:
            browser.close()

    return results


# ── Upsert ───────────────────────────────────────────────────────────────────

def _upsert_lead(db, lead: Dict[str, Any], city: str) -> bool:
    """
    Atomic INSERT ... ON CONFLICT (phone) DO NOTHING — same pattern as
    booking.py's patient upsert (single round trip, RETURNING to detect
    whether a row was actually inserted). Uses SQLAlchemy Core's typed
    insert() rather than raw text() so the Lead.status/source Enum
    columns (native_enum=False — see models.py) are serialized exactly
    how the ORM would, rather than needing to hand-match the uppercase
    enum-name string convention the rest of the app relies on.

    Returns True if a new row was inserted, False if it was a duplicate
    (skipped) or has no phone and this is treated as always-new.
    """
    has_phone = bool(lead.get("phone"))
    review_count = lead.get("review_count") or 0
    score = _score_lead(
        has_phone=has_phone,
        has_street_address=_looks_like_street_address(lead.get("address")),
        review_count=review_count,
        city=city,
    )

    stmt = pg_insert(Lead.__table__).values(
        id=str(uuid.uuid4()),
        clinic_name=lead["clinic_name"],
        phone=lead.get("phone"),
        address=lead.get("address"),
        city=city,
        source=LeadSource.GOOGLE_MAPS,
        source_url=lead.get("source_url"),
        status=LeadStatus.NEW,
        score=score,
    )
    if has_phone:
        stmt = stmt.on_conflict_do_nothing(
            index_elements=["phone"],
            index_where=Lead.__table__.c.phone.isnot(None),
        )
    stmt = stmt.returning(Lead.id)

    result = db.execute(stmt).first()
    return result is not None


# ── Core run logic (shared by manual trigger + daily schedule) ─────────────

def _run_hunt(city: str, query: str, proxy: Optional[str], run) -> int:
    """Returns the count of newly created leads. Updates run.items_* on the
    AgentRunHandle passed in from log_agent_run."""
    if is_dry_run():
        logger.info("hunt_leads: DRY_RUN — generating fake leads for %s instead of scraping", city)
        candidates = _fake_leads_for_dry_run(city)
    else:
        candidates = _scrape_google_maps(city, query, proxy)

    run.items_processed = len(candidates)

    db = SessionLocal()
    created = 0
    try:
        for lead in candidates:
            if _upsert_lead(db, lead, city):
                created += 1
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    run.items_created = created
    return created


# ── Celery tasks ─────────────────────────────────────────────────────────────

@celery.task(bind=True, queue="ai")
def hunt_leads(self, city: str, query: str = "private clinic", proxy: Optional[str] = None):
    """
    Manually triggered (see POST /admin/agents/lead-hunter/run) or called
    directly by hunt_leads_daily for the scheduled rotation.
    """
    proxy = proxy or (settings.SCRAPER_PROXY_URL or None)

    with log_agent_run("lead_hunter", "hunt_leads") as run:
        try:
            created = _run_hunt(city, query, proxy, run)
            if created > 0:
                notify(
                    event_type="leads_found",
                    agent_name="lead_hunter",
                    message=f"{created} new leads found in {city}",
                    link_path="/admin/agents/lead-hunter",
                )
        except GoogleMapsBlockedError as exc:
            # Fail gracefully — log clearly, notify, and stop. No
            # autoretry_for is configured on this task deliberately: a
            # block is a signal to back off, not retry within minutes.
            # The next daily scheduled run (tomorrow 06:00) or a manual
            # re-trigger once you've checked in is the right cadence.
            # Re-raising lets log_agent_run's __exit__ record this run as
            # status='failed' with the error message, matching what
            # actually happened, without Celery attempting to retry it.
            logger.error("hunt_leads blocked for city=%s: %s", city, exc)
            notify(
                event_type="agent_failed",
                agent_name="lead_hunter",
                message="Lead Hunter run failed — possible block",
                link_path="/admin/agents/lead-hunter",
            )
            raise


@celery.task(bind=True, queue="ai")
def hunt_leads_daily(self):
    """
    Beat-scheduled (see celery_app.py's beat_schedule), no args — computes
    today's target city from TARGET_CITIES by rotating one city per day
    (day-of-year modulo list length), then runs the same hunt as a manual
    trigger would. A fixed Celery beat entry can't vary its own args by
    day, so the rotation logic has to live in the scheduled task itself.
    """
    day_index = datetime.utcnow().timetuple().tm_yday
    city = TARGET_CITIES[day_index % len(TARGET_CITIES)]
    logger.info("hunt_leads_daily: today's target city = %s", city)
    return hunt_leads(city=city)
