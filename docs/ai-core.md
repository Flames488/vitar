# Vitar AI Core

Internal growth system powering Vitar's own path to **20 paying clients by
December 2026** — not a feature sold to clinics. Four Celery-task agents
share one database, one AI provider layer (Groq), one run-log table
(`agent_runs`), and one notification feed (`agent_notifications`), read
independently by the superadmin dashboard and a Telegram ops bot.

## The four agents

| Agent | File | What it does | Schedule |
|---|---|---|---|
| Lead Hunter | `backend/app/agents/lead_hunter.py` | Scrapes Google Maps for Nigerian private clinics, scores and upserts them into `leads` | Daily 06:00, rotating Lagos → Abuja → Port Harcourt → Ibadan |
| Sales Agent | `backend/app/agents/sales_agent.py` | Drafts AI outreach for new leads (`draft_outreach_for_new_leads`); sends approved drafts via Wabizz/stub and retires stale leads (`send_approved_outreach`) | Draft: daily 07:00 · Send: every 15 min |
| Content Agent | `backend/app/agents/content_agent.py` | Drafts social post content for review, no auto-publish | Weekly, Monday 07:00 |
| Customer Success | `backend/app/agents/customer_success.py` | Scans paid clinics for no-login / appointment-volume-drop health signals | Daily 08:00 |

All four are registered in `backend/app/workers/celery_app.py`'s
`beat_schedule` — the production `beat` container runs the exact same
module as dev, so nothing extra needs registering per-environment.

## Manually triggering a run

- Lead Hunter: dashboard "Run now" button, or `POST /api/v1/admin/agents/lead-hunter/run` with `{"city": "Lagos", "query": "private clinic"}`
- The other three don't have manual-trigger endpoints (draft/scan tasks are cheap and safe to just wait for the schedule, or trigger from a shell: `docker compose exec worker python -c "from app.agents.sales_agent import draft_outreach_for_new_leads; draft_outreach_for_new_leads.delay()"`)
- Every run — manual or scheduled — writes one row to `agent_runs`, visible on the dashboard's Overview page and each agent's tab.

## Approval flow

Nothing sends or publishes without a human approval step:

1. Sales Agent / Content Agent draft into `content_queue` with `status='pending_approval'`.
2. Approve/reject/edit from the dashboard (`/admin/agents/*`) or the Telegram bot (`/pending`, or inline buttons on a push notification) — both call the exact same backend endpoints, so they can never drift apart.
3. `send_approved_outreach` picks up `status='approved'` outreach on its next 15-minute pass. Content Agent drafts just sit at `approved` for manual posting — no auto-publish exists yet.

**Approve every Sales Agent draft manually until you trust the tone.** Don't lean on the Telegram bot's "Approve All" until you've read enough drafts.

## Kill switch

`AI_CORE_ENABLED` (default `true`) is checked first thing inside every one
of the four agent task functions — when `false`, each task returns
immediately: no scrape, no AI call, no DB write, not even an `agent_runs`
row. To pause the whole system in an emergency:

```
# in .env
AI_CORE_ENABLED=false
```

```
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --force-recreate beat worker telegram_bot
```

Flip back to `true` and re-run the same command to resume. No redeploy, no
code change.

## DRY_RUN

`DRY_RUN=true` makes Lead Hunter skip Playwright (generates 2-3 realistic
fake leads instead) and makes Sales Agent's send always use the stub path
regardless of `WABIZZ_OUTREACH_ENABLED` — the rest of the pipeline
(scoring, upsert, drafting, approval, notifications) runs for real. Use
this for the first end-to-end run in any new environment, and any time
you're testing prompt/scoring changes without wanting a real scrape or a
real message sent to an actual clinic.

## Wabizz outreach routing

`WABIZZ_OUTREACH_ENABLED` (default `false`) gates whether
`send_approved_outreach` actually calls Wabizz (`POST {WABIZZ_API_BASE}/api/send`)
or just logs and marks the draft sent. `DRY_RUN` always wins over this flag
— a dry run never sends a real message even if Wabizz routing is live.

Only flip `WABIZZ_OUTREACH_ENABLED=true` once:
1. Wabizz's security audit is closed, **and**
2. you've manually verified one real end-to-end WhatsApp send + reply round-trip through it (a reply should land at `POST /api/v1/webhooks/wabizz-reply` and flip the lead to `replied`).

"Connectable" and "safe for real client outreach" are not the same bar — don't flip this just because credentials are in `.env`.

## Telegram ops bot

Separate process (`backend/app/telegram_bot/bot.py`, `telegram_bot`
service in `docker-compose.yml`), a thin notification + fast-approval
client — not a dashboard replacement. Restricted to one admin
(`VITAR_ADMIN_TELEGRAM_ID`); every other user gets rejected.

- `/status` — same overview data as the dashboard
- `/pending` — outreach + content drafts awaiting approval, with inline Approve/Edit/Reject
- `/leads new` — count + 5 newest `new`-status leads
- `/digest` — 7-day rollup (also fires automatically every Sunday 18:00 WAT)
- A 15-second poller pushes new `agent_notifications` rows as they appear, marking `pushed_to_telegram` (not `is_read` — that's the dashboard's separate state) so nothing pushes twice.
- Approve/Edit/Reject buttons call the same `/api/v1/admin/agents/*` endpoints the dashboard uses, authenticated with a short-lived JWT the bot mints for the (single) superadmin account — no separate approval logic exists.

To create the bot: message **@BotFather** on Telegram, `/newbot`, set
`VITAR_TELEGRAM_BOT_TOKEN` to the token it gives you. Get your own numeric
Telegram ID from **@userinfobot** and set `VITAR_ADMIN_TELEGRAM_ID`. Both
empty → the bot process refuses to start (missing token) or rejects every
user (missing admin ID) — it never silently no-ops as an "unconfigured but
running" service.

## Rate-limit / retry safety

None of the four agent tasks use Celery's `autoretry_for` or call
`self.retry()` — a captcha/block from Lead Hunter, or a failed AI call, is
logged to `agent_runs.error_message` and the task simply ends, rather than
retrying in a tight loop against a permanent failure. The next scheduled
run (or a manual re-trigger) is the retry, not an automatic backoff loop.
Lead Hunter additionally caps each run at 40 listings and randomizes
2-5s delays between Playwright actions.

**Don't scale Lead Hunter's frequency or city volume until proxy rotation
is real** (`SCRAPER_PROXY_URL` is proxy-ready but not wired to an actual
rotating pool) — scraping at scale from a single VPS IP risks that IP
getting flagged, which affects all of Vitar's traffic from it, not just
scraping.

## Tuning notes

- **Lead scoring weights** (`SCORE_WEIGHTS` in `lead_hunter.py`) are a starting heuristic. Revisit after your first real batch converts — e.g. review count may matter less than assumed, or city tier more.
- **Watch the `lost` auto-flip.** If a large share of leads hit `attempt_count=2` with no reply and auto-flip to `lost`, that's a signal the outreach message or targeting needs work, not that Lead Hunter needs to run harder. Check the Sales Agent tab's funnel numbers periodically.
- **Conversion rate (`contacted` → `trial_started`)** is the number to watch once Sales Agent is live — if it's low, the bottleneck is message quality/targeting, not lead volume.
