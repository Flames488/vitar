"""
Vitar AI Core — Telegram Bot: free-text conversational assistant.

The bot's fixed /commands (bot.py) cover the known ops workflows. Anything
typed outside of those — "when is Cedar Clinic's trial expiring", "any new
users today", "what's going on" — comes here instead. This module gives an
LLM (Groq, via app.services.ai_provider — the same provider every other AI
Core agent uses) tool access to essentially the whole admin dashboard's read
surface (leads, drafts, agent status, clinics, subscriptions/trials, users,
revenue, payouts, health signals, audit log) via the same admin API bot.py's
commands call, so the admin can ask about anything happening in Vitar
without opening the dashboard, and answers reflect the live database rather
than a canned reply.

Read-only by design: every tool here is a GET/list against admin endpoints
or a read-only DB query. Mutating actions (approve/reject/edit/override/
disable a clinic) stay on the existing /pending + inline-button flow or the
dashboard, which have their own confirmation steps built in — a free-text
"approve the Cedar Clinic draft" is deliberately not wired up here.
"""
import asyncio
import json
import logging
from datetime import timedelta
from typing import Optional

from app.core.database import SessionLocal
from app.core.utils import utcnow
from app.services import ai_provider
from app.telegram_bot.api_client import call_api

logger = logging.getLogger("vitar.ai_core.telegram_bot.assistant")

_MAX_TOOL_ROUNDS = 6  # guards against a runaway tool-call loop; broad "what's going on" questions can span several tools

_SYSTEM_PROMPT_TEMPLATE = """You are the Vitar AI Core assistant, reachable by the admin over Telegram —
built so the admin never has to open the dashboard just to see what's going on.

Current date/time: {now} (Africa/Lagos, WAT). Use this for any relative-date
question ("how many days until X", "is that soon") — you can compute it
yourself from a date already in this conversation or from a tool result,
without calling a tool just for arithmetic.

Vitar is a healthcare-clinic SaaS. You have live, read-only tool access to
essentially the whole admin dashboard: leads, outreach/content drafts, agent
status, clinics, clinic subscriptions and trial dates, new user sign-ups and
login activity, revenue/business KPIs, hospital payouts, customer health
signals (churn/risk flags), and the system-wide audit/activity log. Always
call a tool to get current data before answering any factual question — never
guess or make up numbers, names, or dates.

For broad/open-ended questions ("what's going on", "any updates", "how are
things looking") — don't just pick one tool. Pull from a few relevant ones
(e.g. get_recent_activity + get_agents_overview + list_trials_expiring_soon)
and give a short, genuinely useful briefing rather than a single narrow fact.

Currency note: revenue/monthly_revenue figures from get_revenue_overview are
already in NGN (naira). Payout amounts from list_payouts are in kobo (1 naira
= 100 kobo) — always divide by 100 before quoting a payout amount to the admin.

Style: concise, professional, and direct — like a competent ops assistant, not
a chatbot. Reply in plain text only — Telegram will show these messages
unformatted, so never use markdown of any kind (no **bold**, no # headers, no
backticks, no [links](url)). For a list, use a plain "- " prefix per line, not
bullets or numbering markup. Dates in "DD Mon YYYY" form, money as
"₦X,XXX.XX". If a tool call finds nothing or the data doesn't answer the
question, say so plainly rather than speculating. If asked to do something
mutating (approve, reject, edit, send a payout, disable a clinic), tell the
admin to use /pending or the dashboard instead — you are read-only.

This is a continuing conversation — earlier turns are included below. Resolve
pronouns and short follow-ups ("them", "that", "list them all", "how many days
until then") against that history and any tool results already returned in
it, instead of re-asking the admin to clarify something they already told
you or you already showed them. Only ask a clarifying question when the
history genuinely doesn't disambiguate it.
"""


def _build_system_prompt() -> str:
    now = utcnow() + timedelta(hours=1)  # WAT = UTC+1, no DST — same convention as bot.py
    return _SYSTEM_PROMPT_TEMPLATE.format(now=now.strftime("%A, %d %b %Y, %H:%M"))

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_agents_overview",
            "description": "Overall AI Core status: paid-client goal progress, and each agent's "
                            "(Lead Hunter, Sales Agent, Content Agent, Customer Success) health and counts.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_leads",
            "description": "List sales leads, optionally filtered by pipeline status or city.",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": ["string", "null"],
                        "enum": ["new", "contacted", "replied", "trial_started", "paid", "lost", None],
                        "description": "Pipeline status to filter by. Omit or null to get all statuses.",
                    },
                    "city": {"type": ["string", "null"], "description": "City to filter by, e.g. Lagos. Omit or null for all."},
                    "limit": {"type": ["integer", "null"], "description": "Max rows to return, default 10, max 100. Omit or null for default."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_pending_drafts",
            "description": "Outreach and/or content drafts currently awaiting admin approval.",
            "parameters": {
                "type": "object",
                "properties": {
                    "kind": {
                        "type": ["string", "null"],
                        "enum": ["sales", "content", "all", None],
                        "description": "Which draft type to list. Default 'all'.",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_clinic_subscription",
            "description": "Look up a clinic's subscription/trial by (partial) clinic name — plan, "
                            "status, and current billing/trial period end date.",
            "parameters": {
                "type": "object",
                "properties": {
                    "search": {"type": "string", "description": "Clinic name or partial name to search for."},
                },
                "required": ["search"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_trials_expiring_soon",
            "description": "Clinics currently on an active free trial (i.e. signed up but haven't "
                            "subscribed/paid yet), sorted by soonest trial expiry first. Use this for "
                            "'which trials are expiring', 'pending clinics', 'clinics yet to "
                            "subscribe', or 'clinics not yet paying' type questions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {
                        "type": ["integer", "null"],
                        "description": "Only include trials ending within this many days. "
                                       "Omit or null to list all active trials, soonest first.",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_weekly_digest",
            "description": "The last-7-days rollup: leads found, outreach sent, replies, trials "
                            "started, conversions, and pace against the paid-client goal.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_revenue_overview",
            "description": "Business/revenue KPIs: total users, total clinics, active subscriptions, "
                            "this month's revenue (NGN), subscription plan/status breakdown, and "
                            "active-vs-inactive user counts.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_payouts",
            "description": "Hospital/clinic payouts for completed bookings — amount, status, and "
                            "when sent. Use for questions like 'any pending payouts' or 'did the "
                            "payout to X clinic go through'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": ["string", "null"],
                        "enum": ["pending_payout", "sent", "failed", None],
                        "description": "Filter by payout status. Omit or null to get all statuses.",
                    },
                    "limit": {"type": ["integer", "null"], "description": "Max rows to return, default 10, max 100. Omit or null for default."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_new_users",
            "description": "New user sign-ups in the last N days, with their clinic name and plan "
                            "if they've created one. Use for questions like 'any new users today' "
                            "(days=1) or 'new signups this week' (days=7).",
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {
                        "type": ["integer", "null"],
                        "description": "Lookback window in days. Default 1 (today/last 24h). Omit or null for default.",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_outreach_sent",
            "description": "Outreach messages actually SENT to leads (not just drafted/approved — "
                            "sent means it went out) in the last N days, with clinic name and send "
                            "time. Use for 'have we sent our lead message today', 'any outreach sent "
                            "today', or 'how many outreach messages went out this week'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {
                        "type": ["integer", "null"],
                        "description": "Lookback window in days. Default 1 (today/last 24h). Omit or null for default.",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_clinics",
            "description": "General clinic lookup/list — name, active/disabled status, onboarding "
                            "status, plan. Use for 'how many clinics do we have', 'any disabled "
                            "clinics', 'list all clinics', or general clinic info not specifically "
                            "about billing/trial dates. NOT for 'clinics that haven't subscribed yet' "
                            "or 'pending clinics' — that phrasing means still-trialing clinics, use "
                            "list_trials_expiring_soon for that instead.",
            "parameters": {
                "type": "object",
                "properties": {
                    "search": {"type": ["string", "null"], "description": "Clinic name or slug to search for. Omit or null to list all."},
                    "status": {
                        "type": ["string", "null"],
                        "enum": ["active", "disabled", None],
                        "description": "Filter by clinic active status. Omit or null for all.",
                    },
                    "limit": {"type": ["integer", "null"], "description": "Max rows to return, default 10, max 100. Omit or null for default."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_health_signals",
            "description": "Customer-success health/risk signals — things like unusual cancellations "
                            "or drop-offs flagged for a clinic. Use for 'any customers at risk' or "
                            "'anything concerning going on with customers'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": ["string", "null"],
                        "enum": ["open", "acknowledged", "resolved", None],
                        "description": "Filter by signal status. Default 'open'. Omit or null for default.",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_user",
            "description": "Look up user accounts — role, active/suspended status, their clinic, and "
                            "last login time. Use for 'did X log in today', 'is user Y still active', "
                            "or 'list all users' / 'list them all' (omit search to get everyone).",
            "parameters": {
                "type": "object",
                "properties": {
                    "search": {"type": ["string", "null"], "description": "Name or email to search for. Omit or null to list all users."},
                    "limit": {"type": ["integer", "null"], "description": "Max rows to return, default 20, max 100. Omit or null for default."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_recent_activity",
            "description": "The system-wide audit/activity log — every recent admin-visible action "
                            "(signups, subscription changes, clinic status changes, approvals, etc), "
                            "most recent first. Use this as a starting point for open-ended 'what's "
                            "going on' or 'any recent updates' questions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": ["integer", "null"], "description": "Max rows to return, default 15, max 100. Omit or null for default."},
                },
            },
        },
    },
]


def _trials_expiring_soon(days: Optional[int]) -> dict:
    from app.models.models import Clinic, Subscription, SubscriptionStatus

    db = SessionLocal()
    try:
        q = (
            db.query(Clinic, Subscription)
            .join(Subscription, Subscription.clinic_id == Clinic.id)
            .filter(Subscription.status == SubscriptionStatus.TRIALING, Clinic.trial_ends_at.isnot(None))
        )
        if days is not None:
            q = q.filter(Clinic.trial_ends_at <= utcnow() + timedelta(days=days))
        rows = q.order_by(Clinic.trial_ends_at.asc()).limit(50).all()
        return {
            "trials": [
                {
                    "clinic_id": clinic.id,
                    "clinic_name": clinic.name,
                    "trial_started_at": clinic.trial_started_at.isoformat() if clinic.trial_started_at else None,
                    "trial_ends_at": clinic.trial_ends_at.isoformat() if clinic.trial_ends_at else None,
                }
                for clinic, sub in rows
            ]
        }
    finally:
        db.close()


def _new_users_since(days: int) -> dict:
    from app.models.models import Clinic, Subscription, User

    db = SessionLocal()
    try:
        cutoff = utcnow() - timedelta(days=days)
        users = (
            db.query(User)
            .filter(User.created_at >= cutoff)
            .order_by(User.created_at.desc())
            .limit(50)
            .all()
        )
        user_ids = [u.id for u in users]
        clinics = (
            {c.owner_id: c for c in db.query(Clinic).filter(Clinic.owner_id.in_(user_ids)).all()}
            if user_ids else {}
        )
        clinic_ids = [c.id for c in clinics.values()]
        subs = (
            {s.clinic_id: s for s in db.query(Subscription).filter(Subscription.clinic_id.in_(clinic_ids)).all()}
            if clinic_ids else {}
        )
        return {
            "count": len(users),
            "users": [
                {
                    "full_name": u.full_name,
                    "email": u.email,
                    "registered_at": u.created_at.isoformat() if u.created_at else None,
                    "clinic_name": clinics[u.id].name if u.id in clinics else None,
                    "plan": (
                        subs[clinics[u.id].id].plan.value
                        if u.id in clinics and clinics[u.id].id in subs else None
                    ),
                }
                for u in users
            ],
        }
    finally:
        db.close()


def _outreach_sent_since(days: int) -> dict:
    from app.models.models import ContentQueue, ContentStatus, ContentType, Lead

    db = SessionLocal()
    try:
        cutoff = utcnow() - timedelta(days=days)
        rows = (
            db.query(ContentQueue)
            .filter(
                ContentQueue.content_type == ContentType.OUTREACH_TEMPLATE,
                ContentQueue.status == ContentStatus.PUBLISHED,
                ContentQueue.published_at >= cutoff,
            )
            .order_by(ContentQueue.published_at.desc())
            .limit(50)
            .all()
        )
        lead_ids = [r.lead_id for r in rows if r.lead_id]
        lead_names = (
            {l.id: l.clinic_name for l in db.query(Lead).filter(Lead.id.in_(lead_ids)).all()}
            if lead_ids else {}
        )
        return {
            "count": len(rows),
            "sent": [
                {
                    "clinic_name": lead_names.get(r.lead_id, "Unknown clinic"),
                    "sent_at": r.published_at.isoformat() if r.published_at else None,
                }
                for r in rows
            ],
        }
    finally:
        db.close()


async def _execute_tool(name: str, args: dict) -> dict:
    if name == "get_agents_overview":
        return await call_api("GET", "/admin/agents/overview")

    if name == "list_leads":
        params = {"limit": min(int(args.get("limit") or 10), 100)}
        if args.get("status"):
            params["status"] = args["status"]
        if args.get("city"):
            params["city"] = args["city"]
        return await call_api("GET", "/admin/leads/", params=params)

    if name == "list_pending_drafts":
        kind = (args.get("kind") or "all").lower()
        result = {}
        if kind in ("sales", "all"):
            result["sales"] = (
                await call_api("GET", "/admin/agents/sales/drafts", params={"status": "pending_approval", "limit": 10})
            ).get("drafts", [])
        if kind in ("content", "all"):
            result["content"] = (
                await call_api("GET", "/admin/agents/content/drafts", params={"status": "pending_approval", "limit": 10})
            ).get("drafts", [])
        return result

    if name == "find_clinic_subscription":
        search = args.get("search") or ""
        return await call_api("GET", "/admin/subscriptions/", params={"search": search, "limit": 10})

    if name == "list_trials_expiring_soon":
        days = args.get("days")
        return await asyncio.to_thread(_trials_expiring_soon, int(days) if days is not None else None)

    if name == "get_weekly_digest":
        from app.telegram_bot.bot import _build_digest_text
        text = await asyncio.to_thread(_build_digest_text)
        return {"digest_text": text}

    if name == "get_revenue_overview":
        overview = await call_api("GET", "/admin/analytics/overview")
        business = await call_api("GET", "/admin/analytics/business")
        return {
            "kpis": overview.get("kpis"),
            "subscription_plan_breakdown": business.get("subscription_plan_breakdown"),
            "subscription_status_breakdown": business.get("subscription_status_breakdown"),
            "active_vs_inactive_users": business.get("active_vs_inactive_users"),
        }

    if name == "list_payouts":
        params = {"limit": min(int(args.get("limit") or 10), 100)}
        if args.get("status"):
            params["status"] = args["status"]
        return await call_api("GET", "/admin/payouts/", params=params)

    if name == "list_new_users":
        days = int(args.get("days") or 1)
        return await asyncio.to_thread(_new_users_since, days)

    if name == "list_outreach_sent":
        days = int(args.get("days") or 1)
        return await asyncio.to_thread(_outreach_sent_since, days)

    if name == "list_clinics":
        params = {"limit": min(int(args.get("limit") or 10), 100)}
        if args.get("search"):
            params["search"] = args["search"]
        if args.get("status"):
            params["status"] = args["status"]
        return await call_api("GET", "/admin/clinics/", params=params)

    if name == "list_health_signals":
        params = {"status": args.get("status") or "open"}
        return await call_api("GET", "/admin/health-signals/", params=params)

    if name == "find_user":
        params = {"limit": min(int(args.get("limit") or 20), 100)}
        if args.get("search"):
            params["search"] = args["search"]
        return await call_api("GET", "/admin/users/", params=params)

    if name == "get_recent_activity":
        params = {"limit": min(int(args.get("limit") or 15), 100)}
        return await call_api("GET", "/admin/audit-logs/", params=params)

    return {"error": f"Unknown tool: {name}"}


async def answer_question(question: str, history: Optional[list] = None) -> str:
    """
    history is the prior turns of *this* Telegram chat as plain
    {"role": "user"|"assistant", "content": str} dicts (no tool-call
    scaffolding) — the caller (bot.py) owns persisting it per chat. Kept
    separate from the tool-calling messages built up below so a stale
    tool_call_id from a previous turn can never leak into this request.
    """
    messages = [{"role": "system", "content": _build_system_prompt()}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": question})

    for _ in range(_MAX_TOOL_ROUNDS):
        try:
            message = await asyncio.to_thread(
                ai_provider.chat_with_tools, messages, "telegram_assistant", TOOLS
            )
        except Exception:
            logger.exception("assistant.answer_question: LLM call failed")
            return "I couldn't reach the AI provider just now — try again shortly."

        tool_calls = getattr(message, "tool_calls", None)
        if not tool_calls:
            return (message.content or "").strip() or "I don't have an answer for that."

        messages.append(
            {
                "role": "assistant",
                "content": message.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in tool_calls
                ],
            }
        )

        for tc in tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            try:
                result = await _execute_tool(tc.function.name, args)
            except Exception as exc:
                logger.exception("assistant.answer_question: tool %s failed", tc.function.name)
                result = {"error": str(exc)}
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result, default=str),
                }
            )

    return "That took more lookups than expected — try asking a more specific question."
