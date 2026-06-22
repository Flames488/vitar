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

    # ─── Database ─────────────────────────────────────────────────────────
    DATABASE_URL: str = "postgresql://vitar:vitar@localhost:5432/vitar"
    DATABASE_POOL_SIZE: int = 15
    DATABASE_MAX_OVERFLOW: int = 25
    # Optional read replica for read-heavy tasks (analytics, risk scoring, monitoring).
    # When set, get_replica_db() connects here; write tasks always use DATABASE_URL.
    # In docker-compose.yml this is set to postgresql://...@postgres-replica:5432/vitar
    # Leave unset (empty string) to fall back to the primary for all reads.
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
    # FIX: validator accepts both a JSON string env var AND a pre-parsed list,
    # so the field works whether set via .env file or real environment variable.
    ALLOWED_ORIGINS: List[str] = [
        "https://labvault.cloud",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    ALLOWED_HOSTS: List[str] = [
        "localhost", "127.0.0.1",
        "labvault.cloud", "www.labvault.cloud",
    ]

    @field_validator("ALLOWED_ORIGINS", "ALLOWED_HOSTS", mode="before")
    @classmethod
    def _parse_list(cls, v):
        """
        Accept either:
          - A real list (already parsed by pydantic from JSON in .env)
          - A JSON string: '["https://a.com","https://b.com"]'
          - A comma-separated string (convenience): "https://a.com,https://b.com"
        """
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
    FLUTTERWAVE_SECRET_KEY: str = ""
    FLUTTERWAVE_PUBLIC_KEY: str = ""
    FLUTTERWAVE_WEBHOOK_SECRET: str = ""
    STRIPE_SECRET_KEY: str = ""
    STRIPE_PUBLISHABLE_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""

    # ─── Notifications ────────────────────────────────────────────────────
    TERMII_API_KEY: str = ""
    TERMII_SENDER_ID: str = "Vitar"
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_FROM_NUMBER: str = ""
    WHATSAPP_PHONE_NUMBER_ID: str = ""
    WHATSAPP_ACCESS_TOKEN: str = ""
    SENDGRID_API_KEY: str = ""
    EMAIL_FROM: str = "no-reply@labvault.cloud"
    EMAIL_FROM_NAME: str = "Vitar Health"

    # ─── AI / ML ──────────────────────────────────────────────────────────
    GROQ_API_KEY: str = ""
    ML_MODEL_PATH: str = "/app/ml_models"

    # ─── Monitoring ───────────────────────────────────────────────────────
    SENTRY_DSN: str = ""

    # ─── Geo / Currency ───────────────────────────────────────────────────
    IPAPI_KEY: str = ""
    EXCHANGE_RATE_API_KEY: str = ""

    # ─── Trial ────────────────────────────────────────────────────────────
    TRIAL_DAYS: int = 14
    TRIAL_MAX_BOOKINGS: int = 50
    TRIAL_MAX_DOCTORS: int = 2

    # ─── Storage ──────────────────────────────────────────────────────────
    # STORAGE_BACKEND controls where uploaded files are persisted.
    # 's3'    → AWS S3. Required for multi-replica / 500-user scale.
    #           All replicas share one bucket; files survive container restarts.
    #           Requires: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_S3_BUCKET.
    # 'local' → Local filesystem under UPLOAD_DIR. Dev/single-node only.
    #           Files are NOT shared across replicas and lost on container restart.
    STORAGE_BACKEND: str = "local"
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

    # ─── PgBouncer ────────────────────────────────────────────────────────
    # v12: PgBouncer is always-on. Default True matches docker-compose.yml.
    PGBOUNCER_ENABLED: bool = True
    PGBOUNCER_URL: str = "postgresql://vitar:vitar@pgbouncer:5432/vitar"


settings = Settings()
