"""
Vitar AI Core — Telegram Ops Bot (Phase 7)

A thin notification + fast-approval client of the same backend the
superadmin dashboard (Phase 6) uses. It does not replicate the dashboard
and does not implement its own approve/reject/edit logic — every action
here calls the exact same /api/v1/admin/agents/* endpoints the dashboard
calls, over HTTP inside the docker network, authenticated with a
short-lived JWT minted for the (single) superadmin user. Notifications are
read from the shared `agent_notifications` table (see
app/services/notifications.py) independently of the dashboard's
notification bell — neither triggers the other.

Restricted to a single hardcoded admin (VITAR_ADMIN_TELEGRAM_ID). Run as
its own process: `python -m app.telegram_bot.bot`.
"""
import asyncio
import html
import logging
from datetime import datetime, time as dt_time, timedelta, timezone as dt_timezone

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.utils import utcnow
from app.telegram_bot import assistant
from app.telegram_bot.api_client import call_api as _api

logger = logging.getLogger("vitar.ai_core.telegram_bot")

# Africa/Lagos has no DST, so a fixed UTC+1 offset is always correct — same
# WAT convention used elsewhere in this codebase (see booking.py/appointments.py).
WAT = dt_timezone(timedelta(hours=1))

# Rolling per-chat memory for the free-text assistant, kept in
# context.user_data (same mechanism awaiting_edit already uses) — bounds
# token growth on every call while keeping enough recent turns for
# follow-ups ("list them all", "how many days until then") to resolve.
_ASSISTANT_HISTORY_TURNS = 8

# Telegram hard-rejects any text message over 4096 chars (BadRequest, and
# with no try/except around the send it would silently drop the reply on
# the floor) — a "list everything" style answer over many drafts/leads can
# easily run past that. Split rather than truncate so nothing is lost.
_TELEGRAM_MAX_LEN = 4000


def _chunk_text(text: str, limit: int = _TELEGRAM_MAX_LEN) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks = []
    while text:
        if len(text) <= limit:
            chunks.append(text)
            break
        split_at = text.rfind("\n", 0, limit)
        if split_at <= 0:
            split_at = limit
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    return chunks

# Mirrors admin_agents.py's GOAL_TARGET_CLIENTS / GOAL_DEADLINE. GOAL_START is
# specific to the digest's pace estimate — the AI Core system doesn't record
# its own "went live" date anywhere else, so this is a fixed anchor rather
# than a derived one (update it if the real rollout date needs correcting).
GOAL_TARGET_CLIENTS = 20
GOAL_DEADLINE = "2026-12-31"
GOAL_START = "2026-08-01"

_STATUS_DOT = {"green": "\U0001F7E2", "yellow": "\U0001F7E1", "red": "\U0001F534"}
_EVENT_EMOJI = {
    "leads_found": "\U0001F3AF",
    "outreach_ready": "✍️",
    "lead_replied": "\U0001F4EC",
    "lead_trial_started": "\U0001F4EC",
    "content_ready": "\U0001F4DD",
    "health_signal": "⚠️",
    "agent_failed": "\U0001F534",
    "subscription_paid": "\U0001F4B3",
    "subscription_override": "\U0001F6E0",
    "appointment_refund_needed": "\U0001F534",
    "payout_blocked_no_bank": "\U0001F3E6",
    "booking_payment_received": "\U0001F4B0",
    "payout_sent": "✅",
}
# Only Sales Agent drafts have an /edit endpoint (Content Agent's don't per
# the Phase 4 spec) — kept here so both the keyboard builder and the
# callback handler enforce the same rule from one place.
_EDITABLE_KINDS = {"sales"}
_ENDPOINT_PREFIX = {"sales": "/admin/agents/sales", "content": "/admin/agents/content"}


def _esc(s) -> str:
    """HTML-escape any dynamic string before it goes into a message — draft
    bodies are AI-generated free text and clinic names are user-entered, so
    Markdown would be one stray `_`/`*` away from a broken/rejected send."""
    return html.escape(str(s)) if s is not None else ""


# ── Auth ─────────────────────────────────────────────────────────────────────

def _is_admin_id(user_id) -> bool:
    return bool(settings.VITAR_ADMIN_TELEGRAM_ID) and str(user_id) == str(settings.VITAR_ADMIN_TELEGRAM_ID)


def admin_only(handler):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.effective_user or not _is_admin_id(update.effective_user.id):
            if update.effective_message:
                await update.effective_message.reply_text("Not authorized.")
            return
        return await handler(update, context)

    return wrapper


# ── Commands ─────────────────────────────────────────────────────────────────

@admin_only
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("assistant_history", None)
    await update.message.reply_text(
        "Vitar Ops Bot connected.\n\n"
        "/status — agent overview + goal progress\n"
        "/pending — outreach & content drafts awaiting approval\n"
        "/leads new — newest new-status leads\n"
        "/digest — 7-day rollup (also sent automatically every Sunday 18:00 WAT)\n\n"
        "You can also just ask a question in plain English — e.g. \"when does "
        "Cedar Clinic's trial expire\" or \"which trials expire this week\" — "
        "and I'll look it up live."
    )


@admin_only
async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        data = await _api("GET", "/admin/agents/overview")
    except Exception:
        logger.exception("cmd_status: overview fetch failed")
        await update.message.reply_text("Couldn't reach the API — try again shortly.")
        return

    goal = data["goal"]
    agents = data["agents"]
    lh, sa, ca, cs = agents["lead_hunter"], agents["sales_agent"], agents["content_agent"], agents["customer_success"]

    lines = [
        "<b>Vitar AI Core — Status</b>",
        f"Goal: {goal['current']}/{goal['target']} paid clients by {_esc(goal['deadline'])}",
        "",
        f"{_STATUS_DOT.get(lh['status'], '⚪')} <b>Lead Hunter</b> — {lh['new_leads']} new leads",
        f"{_STATUS_DOT.get(sa['status'], '⚪')} <b>Sales Agent</b> — {sa['pending_approval']} pending, "
        f"{sa['conversion_rate'] * 100:.1f}% conversion",
        f"{_STATUS_DOT.get(ca['status'], '⚪')} <b>Content Agent</b> — {ca['pending_approval']} pending",
        f"{_STATUS_DOT.get(cs['status'], '⚪')} <b>Customer Success</b> — {cs['open_signals']} open signals",
    ]
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


def _draft_keyboard(kind: str, content_id: str) -> InlineKeyboardMarkup:
    buttons = [InlineKeyboardButton("✅ Approve", callback_data=f"appr:{kind}:{content_id}")]
    if kind in _EDITABLE_KINDS:
        buttons.append(InlineKeyboardButton("✏️ Edit", callback_data=f"edit:{kind}:{content_id}"))
    buttons.append(InlineKeyboardButton("❌ Reject", callback_data=f"rej:{kind}:{content_id}"))
    return InlineKeyboardMarkup([buttons])


async def _send_draft(message_target, label: str, body: str, kind: str, content_id: str):
    text = f"<b>{_esc(label)}</b>\n\n{_esc(body)}"
    await message_target.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=_draft_keyboard(kind, content_id))


@admin_only
async def cmd_pending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        sales = await _api("GET", "/admin/agents/sales/drafts", params={"status": "pending_approval", "limit": 5})
        content = await _api("GET", "/admin/agents/content/drafts", params={"status": "pending_approval", "limit": 5})
    except Exception:
        logger.exception("cmd_pending: fetch failed")
        await update.message.reply_text("Couldn't reach the API — try again shortly.")
        return

    sales_drafts = sales.get("drafts", [])
    content_drafts = content.get("drafts", [])
    if not sales_drafts and not content_drafts:
        await update.message.reply_text("Nothing pending approval right now.")
        return

    for d in sales_drafts:
        label = f"Outreach draft — {d.get('lead_clinic_name') or 'Unknown clinic'}"
        await _send_draft(update.message, label, d["body"], "sales", d["id"])
    for d in content_drafts:
        await _send_draft(update.message, "Content draft", d["body"], "content", d["id"])


@admin_only
async def cmd_leads(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status = context.args[0].lower() if context.args else "new"
    try:
        data = await _api(
            "GET", "/admin/leads/", params={"status": status, "sort_by": "created_at", "limit": 5}
        )
    except Exception:
        logger.exception("cmd_leads: fetch failed")
        await update.message.reply_text("Couldn't reach the API — try again shortly.")
        return

    leads = data.get("leads", [])
    total = data.get("total", len(leads))
    if not leads:
        await update.message.reply_text(f"No leads with status '{_esc(status)}'.")
        return

    lines = [f"<b>{total} lead(s) — status: {_esc(status)}</b>", ""]
    for l in leads:
        lines.append(f"• {_esc(l['clinic_name'])} ({_esc(l.get('city') or '—')}) — score {l['score']}")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


def _build_digest_text() -> str:
    from app.models.models import (
        Clinic, ContentQueue, ContentStatus, ContentType, Lead, LeadStatus,
        Subscription, SubscriptionStatus,
    )

    db = SessionLocal()
    try:
        cutoff = utcnow() - timedelta(days=7)

        leads_found = db.query(Lead).filter(Lead.created_at >= cutoff).all()
        by_city: dict = {}
        for l in leads_found:
            key = l.city or "Unknown"
            by_city[key] = by_city.get(key, 0) + 1

        outreach_sent = (
            db.query(ContentQueue)
            .filter(
                ContentQueue.content_type == ContentType.OUTREACH_TEMPLATE,
                ContentQueue.status == ContentStatus.PUBLISHED,
                ContentQueue.published_at >= cutoff,
            )
            .count()
        )

        # Approximation, not an event log: "moved into this stage recently"
        # is read off updated_at + current status, since the pipeline
        # doesn't keep a full stage-transition history. Deliberately
        # monotonic (paid ⊆ trial_started ⊆ replied) so the rollup stays
        # internally consistent even though it isn't perfectly precise.
        replies = db.query(Lead).filter(
            Lead.updated_at >= cutoff,
            Lead.status.in_([LeadStatus.REPLIED, LeadStatus.TRIAL_STARTED, LeadStatus.PAID]),
        ).count()
        trials = db.query(Lead).filter(
            Lead.updated_at >= cutoff,
            Lead.status.in_([LeadStatus.TRIAL_STARTED, LeadStatus.PAID]),
        ).count()
        paid = db.query(Lead).filter(
            Lead.updated_at >= cutoff,
            Lead.status == LeadStatus.PAID,
        ).count()

        paid_clients = (
            db.query(Clinic)
            .join(Subscription, Subscription.clinic_id == Clinic.id)
            .filter(Subscription.status == SubscriptionStatus.ACTIVE)
            .count()
        )
    finally:
        db.close()

    deadline = datetime.fromisoformat(GOAL_DEADLINE).replace(tzinfo=dt_timezone.utc)
    start = datetime.fromisoformat(GOAL_START).replace(tzinfo=dt_timezone.utc)
    now = datetime.now(dt_timezone.utc)
    total_days = max((deadline - start).days, 1)
    elapsed_days = max((now - start).days, 0)
    expected_clients = GOAL_TARGET_CLIENTS * min(elapsed_days / total_days, 1.0)
    pace_note = "on pace" if paid_clients >= expected_clients else "behind pace"

    if by_city:
        city_lines = "\n".join(
            f"  • {_esc(city)}: {count}" for city, count in sorted(by_city.items(), key=lambda kv: -kv[1])
        )
    else:
        city_lines = "  • none"

    return (
        "<b>Vitar AI Core — Weekly Digest</b>\n"
        f"<i>{cutoff.strftime('%d %b')} → {now.strftime('%d %b %Y')}</i>\n\n"
        f"\U0001F3AF Leads found: {len(leads_found)}\n{city_lines}\n\n"
        f"✍️ Outreach sent: {outreach_sent}\n"
        f"\U0001F4EC Replies: {replies}\n"
        f"\U0001F680 Trials started: {trials}\n"
        f"\U0001F4B0 Converted to paid: {paid}\n\n"
        f"<b>Goal:</b> {paid_clients}/{GOAL_TARGET_CLIENTS} paid clients by {GOAL_DEADLINE} — {pace_note}"
    )


@admin_only
async def cmd_digest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        text = await asyncio.to_thread(_build_digest_text)
    except Exception:
        logger.exception("cmd_digest: build failed")
        await update.message.reply_text("Couldn't build the digest — check the logs.")
        return
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


# ── Inline approve / edit / reject ──────────────────────────────────────────

async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query.from_user or not _is_admin_id(query.from_user.id):
        await query.answer("Not authorized.", show_alert=True)
        return
    await query.answer()

    parts = query.data.split(":", 2)
    action = parts[0]
    kind = parts[1] if len(parts) > 1 else None
    content_id = parts[2] if len(parts) > 2 else None
    prefix = _ENDPOINT_PREFIX.get(kind)
    if not prefix:
        return

    if action == "appr" and content_id:
        try:
            await _api("POST", f"{prefix}/approve/{content_id}")
        except Exception:
            logger.exception("on_callback: approve failed")
            await query.message.reply_text("Approve failed — check the dashboard.")
            return
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text("✅ Approved.")

    elif action == "rej" and content_id:
        try:
            await _api("POST", f"{prefix}/reject/{content_id}")
        except Exception:
            logger.exception("on_callback: reject failed")
            await query.message.reply_text("Reject failed — check the dashboard.")
            return
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text("❌ Rejected.")

    elif action == "edit" and content_id and kind in _EDITABLE_KINDS:
        context.user_data["awaiting_edit"] = {"kind": kind, "content_id": content_id}
        await query.message.reply_text("Send me the replacement text for this draft.")

    elif action == "apprall" and kind == "sales":
        try:
            drafts = await _api("GET", f"{prefix}/drafts", params={"status": "pending_approval", "limit": 100})
            draft_list = drafts.get("drafts", [])
            for d in draft_list:
                await _api("POST", f"{prefix}/approve/{d['id']}")
        except Exception:
            logger.exception("on_callback: approve-all failed")
            await query.message.reply_text("Approve All failed — check the dashboard.")
            return
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text(f"✅ Approved {len(draft_list)} draft(s).")

    elif action == "reviewall" and kind == "sales":
        try:
            drafts = await _api("GET", f"{prefix}/drafts", params={"status": "pending_approval", "limit": 10})
        except Exception:
            logger.exception("on_callback: reviewall fetch failed")
            await query.message.reply_text("Couldn't fetch drafts — check the dashboard.")
            return
        await query.edit_message_reply_markup(reply_markup=None)
        draft_list = drafts.get("drafts", [])
        if not draft_list:
            await query.message.reply_text("Nothing pending approval right now.")
            return
        for d in draft_list:
            label = f"Outreach draft — {d.get('lead_clinic_name') or 'Unknown clinic'}"
            await _send_draft(query.message, label, d["body"], "sales", d["id"])


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not _is_admin_id(update.effective_user.id):
        return
    pending = context.user_data.pop("awaiting_edit", None)
    if not pending:
        # Not mid-edit — treat this as a free-text question for the AI
        # assistant (leads, trial expiry, drafts, agent status, etc.)
        # rather than silently dropping it.
        await update.effective_chat.send_action("typing")
        history = context.user_data.get("assistant_history", [])
        question = update.message.text
        answer = await assistant.answer_question(question, history=history)
        # Store a capped copy, not the verbatim answer — a single unusually
        # long reply (the model doesn't always follow the "stay concise"
        # instruction) sitting in history is enough on its own to blow past
        # this account's Groq rate limit (8000 TPM) on the *next* question,
        # which is exactly what happened in testing. Full text was already
        # sent to the admin above; only the stored copy needs trimming.
        stored_answer = answer if len(answer) <= 800 else answer[:800] + " […]"
        history.append({"role": "user", "content": question})
        history.append({"role": "assistant", "content": stored_answer})
        context.user_data["assistant_history"] = history[-(_ASSISTANT_HISTORY_TURNS * 2):]
        for chunk in _chunk_text(answer):
            await update.message.reply_text(chunk)
        return
    prefix = _ENDPOINT_PREFIX.get(pending["kind"])
    if not prefix:
        return
    try:
        await _api("POST", f"{prefix}/edit/{pending['content_id']}", json={"body": update.message.text})
    except Exception:
        logger.exception("on_text: edit failed")
        await update.message.reply_text("Edit failed — check the dashboard.")
        return
    await update.message.reply_text("✏️ Draft updated. Approve it via /pending when ready.")


# ── Scheduled jobs ───────────────────────────────────────────────────────────

def _fetch_unpushed_notifications() -> list:
    from app.models.models import AgentNotification

    db = SessionLocal()
    try:
        rows = (
            db.query(AgentNotification)
            .filter(AgentNotification.pushed_to_telegram == False)  # noqa: E712
            .order_by(AgentNotification.created_at.asc())
            .limit(20)
            .all()
        )
        result = [
            {
                "id": r.id,
                "event_type": r.event_type.value if hasattr(r.event_type, "value") else r.event_type,
                "message": r.message,
            }
            for r in rows
        ]
        # Marked pushed BEFORE the send attempt below, not after — a bad
        # Telegram send (network blip, bad chat id) then can't retry the
        # same row forever and risk a duplicate-push storm once it does
        # succeed. A rare dropped push is a smaller problem than that.
        for r in rows:
            r.pushed_to_telegram = True
        db.commit()
        return result
    finally:
        db.close()


async def job_push_notifications(context: ContextTypes.DEFAULT_TYPE):
    if not settings.VITAR_ADMIN_TELEGRAM_ID:
        return
    try:
        notifications = await asyncio.to_thread(_fetch_unpushed_notifications)
    except Exception:
        logger.exception("job_push_notifications: fetch failed")
        return

    for n in notifications:
        emoji = _EVENT_EMOJI.get(n["event_type"], "\U0001F514")
        text = f"{emoji} {_esc(n['message'])}"
        markup = None
        if n["event_type"] == "outreach_ready":
            markup = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Approve All", callback_data="apprall:sales"),
                InlineKeyboardButton("\U0001F440 Review Individually", callback_data="reviewall:sales"),
            ]])
        try:
            await context.bot.send_message(
                chat_id=int(settings.VITAR_ADMIN_TELEGRAM_ID),
                text=text,
                parse_mode=ParseMode.HTML,
                reply_markup=markup,
            )
        except Exception:
            logger.exception("job_push_notifications: send failed for notification=%s", n["id"])


async def job_weekly_digest(context: ContextTypes.DEFAULT_TYPE):
    if not settings.VITAR_ADMIN_TELEGRAM_ID:
        return
    try:
        text = await asyncio.to_thread(_build_digest_text)
    except Exception:
        logger.exception("job_weekly_digest: build failed")
        return
    try:
        await context.bot.send_message(
            chat_id=int(settings.VITAR_ADMIN_TELEGRAM_ID), text=text, parse_mode=ParseMode.HTML
        )
    except Exception:
        logger.exception("job_weekly_digest: send failed")


# ── App wiring ───────────────────────────────────────────────────────────────

def build_application() -> Application:
    if not settings.VITAR_TELEGRAM_BOT_TOKEN:
        raise RuntimeError("VITAR_TELEGRAM_BOT_TOKEN is not set — the Telegram bot cannot start")
    if not settings.VITAR_ADMIN_TELEGRAM_ID:
        logger.warning("VITAR_ADMIN_TELEGRAM_ID is not set — the bot will reject every user")

    app = Application.builder().token(settings.VITAR_TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("pending", cmd_pending))
    app.add_handler(CommandHandler("leads", cmd_leads))
    app.add_handler(CommandHandler("digest", cmd_digest))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    app.job_queue.run_repeating(job_push_notifications, interval=15, first=10, name="ai_core_push_poller")
    # days: 0=Monday..6=Sunday (matches date.weekday()) — Sunday 18:00 WAT.
    app.job_queue.run_daily(
        job_weekly_digest, time=dt_time(hour=18, minute=0, tzinfo=WAT), days=(6,), name="ai_core_weekly_digest"
    )

    return app


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    app = build_application()
    logger.info("Vitar Telegram ops bot starting (long polling)")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
