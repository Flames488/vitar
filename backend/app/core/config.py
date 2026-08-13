"""
Vitar — Core Configuration
All settings are loaded from environment variables (or .env file).
No secrets are hardcoded. See .env.example for documentation.

List fields (ALLOWED_ORIGINS, ALLOWED_HOSTS) must be set as JSON arrays
in the environment, e.g.:
  ALLOWED_ORIGINS='["https://yourapp.com","https://www.yourapp.com"]'

pydantic-settings parses JSON arrays natively; bare comma-separated
strings are NOT supported for List fields.
"""

import json
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
from typing import List


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        env_ignore_empty=True,
        extra="ignore",
    )

    # ─── App ──────────────────────────────────────────────────────────────
    APP_NAME: str = "Vitar"
    ENVIRONMENT: str = "development"
    SECRET_KEY: str = "change-me-in-production-use-32-char-min"
    DEBUG: bool = False
    API_DOCS_ENABLED: bool = False

    # ─── Database ─────────────────────────────────────────────────────────
    DATABASE_URL: str = "postgresql://vitar:vitar@localhost:5432/vitar"
    DATABASE_POOL_SIZE: int = 15
    DATABASE_MAX_OVERFLOW: int = 25
    DATABASE_REPLICA_URL: str = ""

    # ─── Redis ────────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # ─── Auth ─────────────────────────────────────────────────────────────
    JWT_SECRET_KEY: str = "jwt-secret-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # ─── CORS / Hosts ─────────────────────────────────────────────────────
    ALLOWED_ORIGINS: List[str] = [
        "https://livevault.cloud",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    ALLOWED_HOSTS: List[str] = [
        "localhost", "127.0.0.1",
        "livevault.cloud", "www.livevault.cloud",
        # Internal docker-network hostname of the api service itself — the
        # Telegram bot (Phase 7) calls http://api:8000/... directly rather
        # than going out through nginx, so its Host header is "api", not
        # the public domain. Without this, TrustedHostMiddleware 400s every
        # request from the bot with "Invalid host header".
        "api",
    ]

    @field_validator("ALLOWED_ORIGINS", "ALLOWED_HOSTS", mode="before")
    @classmethod
    def _parse_list(cls, v):
        if isinstance(v, list):
            return v
        if isinstance(v, str):
            v = v.strip()
            if v.startswith("["):
                return json.loads(v)
            return [item.strip() for item in v.split(",") if item.strip()]
        return v

    # ─── Payment ──────────────────────────────────────────────────────────
    PAYSTACK_SECRET_KEY: str = ""
    PAYSTACK_PUBLIC_KEY: str = ""
    PAYSTACK_WEBHOOK_SECRET: str = ""
    PAYSTACK_BASE_URL: str = "https://api.paystack.co"
    PAYOUT_AUTO_SEND_AFTER_HOURS: int = 24
    # An AWAITING_PAYMENT appointment (patient started checkout but never
    # completed it) holds its slot as a conflict for this long, then stops
    # blocking new bookings — otherwise an abandoned checkout permanently
    # occupies that slot (and, with enough abandoned test/real attempts,
    # can make a doctor look booked solid on every date).
    AWAITING_PAYMENT_TIMEOUT_MINUTES: int = 30
    # Fraction of each patient payment Vitar retains as a payment-processing fee
    # before transferring the remainder to the clinic's bank account. Covers
    # Paystack's own charge fee (~1.5%+₦100) and transfer fee (₦10-50) with a
    # small margin. Set to 0 to pass 100% through to clinics.
    PLATFORM_PAYOUT_FEE_PCT: float = 0.02
    STRIPE_SECRET_KEY: str = ""
    STRIPE_PUBLISHABLE_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""

    # ─── Vitar Owner Bank Details (for clinic subscription payments) ───────
    # Clinics pay their subscription fee directly to this account via bank
    # transfer. No Paystack account required on the clinic side.
    # You manually activate their plan from the superadmin panel after
    # confirming the transfer in your banking app.
    OWNER_BANK_NAME: str = ""         # e.g. "GTBank"
    OWNER_ACCOUNT_NUMBER: str = ""    # e.g. "0123456789"
    OWNER_ACCOUNT_NAME: str = "Vitar Health"  # Account name as it appears

    # ─── Notifications ────────────────────────────────────────────────────
    TERMII_API_KEY: str = ""
    TERMII_SENDER_ID: str = "Vitar"
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_FROM_NUMBER: str = ""
    WHATSAPP_PHONE_NUMBER_ID: str = ""
    WHATSAPP_ACCESS_TOKEN: str = ""
    SENDGRID_API_KEY: str = ""
    RESEND_API_KEY: str = ""
    EMAIL_FROM: str = "no-reply@livevault.cloud"
    EMAIL_FROM_NAME: str = "Vitar Health"

    # ─── Web Push (VAPID) ─────────────────────────────────────────────────
    VAPID_PRIVATE_KEY: str = ""
    VAPID_PUBLIC_KEY: str = ""
    VAPID_CLAIMS_EMAIL: str = "vitarhealthcare@gmail.com"

    # ─── AI / ML ──────────────────────────────────────────────────────────
    GROQ_API_KEY: str = ""
    ML_MODEL_PATH: str = "/app/ml_models"

    # ─── Monitoring ───────────────────────────────────────────────────────
    SENTRY_DSN: str = ""

    # ─── Geo / Currency ───────────────────────────────────────────────────
    IPAPI_KEY: str = ""
    EXCHANGE_RATE_API_KEY: str = ""

    # ─── Trial ────────────────────────────────────────────────────────────
    TRIAL_DAYS: int = 30
    TRIAL_MAX_BOOKINGS: int = 50
    TRIAL_MAX_DOCTORS: int = 2

    # ─── Storage ──────────────────────────────────────────────────────────
    STORAGE_BACKEND: str = "local"
    # Explicit opt-in for single-node local-disk storage in production.
    # startup_validation.py checks this via getattr(settings, ...) — it must
    # be declared here or Pydantic silently ignores the env var and the
    # check always sees False regardless of what's set in .env.
    ALLOW_LOCAL_UPLOADS_IN_PRODUCTION: bool = False
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_S3_BUCKET: str = "vitar-uploads"
    AWS_REGION: str = "us-east-1"
    UPLOAD_DIR: str = "/app/uploads"

    # ─── Frontend ─────────────────────────────────────────────────────────
    FRONTEND_URL: str = "http://localhost:5173"
    VITE_API_URL: str = "http://localhost:8000/api/v1"

    # ─── Flower ───────────────────────────────────────────────────────────
    FLOWER_USER: str = "admin"
    FLOWER_PASSWORD: str = "vitar_flower"

    # ─── Observability ────────────────────────────────────────────────────
    GRAFANA_USER: str = "admin"
    GRAFANA_PASSWORD: str = "vitar_grafana"
    SLOW_QUERY_THRESHOLD_S: float = 0.5
    # p95 request latency (ms) above which an SLA-breach alert fires.
    # Default (800ms) assumes app and DB are in the same region. If your DB
    # is geographically distant from where the app runs (e.g. dev machine in
    # one continent, DB hosted in another), raise this via .env to avoid
    # false-positive alerts dominated by network round-trip time rather than
    # actual application slowness.
    API_LATENCY_ALERT_THRESHOLD_MS: float = 800.0

    # ─── Database hardening ───────────────────────────────────────────────
    DB_STATEMENT_TIMEOUT_MS: int = 30_000

    # ─── Autoscaling ──────────────────────────────────────────────────────
    AUTOSCALE_ENABLED: bool = False
    AUTOSCALE_DRY_RUN: bool = True
    WORKER_MIN_REPLICAS: int = 1
    WORKER_MAX_REPLICAS: int = 8
    WORKER_SCALE_UP_QUEUE_DEPTH: int = 100
    WORKER_SCALE_DOWN_QUEUE_DEPTH: int = 20
    API_MIN_REPLICAS: int = 1
    API_MAX_REPLICAS: int = 6
    API_SCALE_UP_RPS: float = 50.0
    API_SCALE_DOWN_RPS: float = 10.0

    # ─── Alerts ───────────────────────────────────────────────────────────
    SLACK_WEBHOOK_URL: str = ""
    PROMETHEUS_URL: str = "http://prometheus:9090"

    # ─── System resource thresholds ───────────────────────────────────────
    CPU_ALERT_THRESHOLD_PCT: float = 85.0
    CPU_CRITICAL_THRESHOLD_PCT: float = 95.0
    MEMORY_ALERT_THRESHOLD_PCT: float = 80.0
    MEMORY_CRITICAL_THRESHOLD_PCT: float = 90.0
    DISK_ALERT_THRESHOLD_PCT: float = 80.0
    DISK_CRITICAL_THRESHOLD_PCT: float = 92.0
    DISK_CHECK_PATH: str = "/"

    # ─── Background job safety ────────────────────────────────────────────
    TASK_STUCK_THRESHOLD_S: int = 600
    AUTOHEAL_STUCK_TASKS: bool = False
    OPS_MONITORING_ENABLED: bool = False

    # ─── AI Core (Lead Hunter / Sales / Content / Customer Success agents) ─
    # DRY_RUN: cross-cutting safety flag for the whole AI Core system. When
    # true, any agent action that touches something external or irreversible
    # (Lead Hunter's live scrape, Sales Agent's actual WhatsApp send) skips
    # the real external call, logs what it would have done, and still
    # writes normally to leads/content_queue/agent_runs — so the full
    # pipeline can be exercised end-to-end without scraping real pages or
    # sending real messages.
    DRY_RUN: bool = False
    # Kill switch for the whole AI Core system (Phase 8). When false, every
    # agent Celery task (hunt_leads/hunt_leads_daily, draft_outreach_for_
    # new_leads, send_approved_outreach, draft_weekly_content,
    # scan_customer_health) no-ops immediately on entry — no scrape, no AI
    # call, no DB write, not even an agent_runs row — so the whole system
    # can be paused instantly via .env + restart, no redeploy or code
    # change needed. Defaults true (system runs normally) — this is an
    # emergency brake, not an opt-in flag.
    AI_CORE_ENABLED: bool = True
    # Lead Hunter's Playwright scraper. Empty = no proxy (fine for early,
    # low-volume runs — see the build spec's own operator note about not
    # scaling frequency/volume until this is a real rotating proxy pool).
    SCRAPER_PROXY_URL: str = ""

    # Sales Agent's WhatsApp send, routed through Wabizz rather than a
    # direct Meta Cloud API integration. Defaults to false — flip only once
    # Wabizz's security audit is closed AND you've manually verified one
    # real end-to-end send + reply round-trip through it. Independent of
    # DRY_RUN: DRY_RUN always forces the stub path even if this is true.
    WABIZZ_OUTREACH_ENABLED: bool = False
    WABIZZ_API_BASE: str = "https://wabizz-app.emmyflames48.workers.dev"
    WABIZZ_API_KEY: str = ""
    # Shared secret Wabizz must send back on its inbound-reply webhook
    # (see POST /api/v1/webhooks/wabizz-reply) — swap for Wabizz's own
    # signature scheme once confirmed; a shared-secret header is a safe,
    # standard default in the meantime.
    WABIZZ_WEBHOOK_SECRET: str = ""

    # Telegram ops bot — a SEPARATE bot/token from any other Telegram bot
    # already in use elsewhere; Telegram allows only one active poller per
    # token, so reusing another bot's token would conflict with its own
    # connection. Empty by default: the bot process exits at startup with a
    # clear error rather than silently no-op-ing if these aren't set.
    VITAR_TELEGRAM_BOT_TOKEN: str = ""
    VITAR_ADMIN_TELEGRAM_ID: str = ""


settings = Settings()
