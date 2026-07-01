"""
Vitar — Startup Validation
Fails fast on bad config in production. Dev always passes.

FIX: moved _ERRORS / _WARNINGS inside the function so repeated calls
     (hot-reload, tests) don't accumulate stale entries.
"""

import sys
import logging
from app.core.config import settings

logger = logging.getLogger(__name__)

_KNOWN_INSECURE_VALUES = {
    "change-me-in-production-use-32-char-min",
    "change-me-generate-with-openssl-rand-hex-32",
    "jwt-secret-change-in-production",
    "vitar_grafana",
    "vitar_flower",
    "secret",
    "password",
    "changeme",
}


def _check_secret(errors: list, name: str, value: str, min_length: int = 32) -> None:
    if not value:
        errors.append(f"{name} is empty. Generate with: openssl rand -hex 32")
        return
    if value.strip().lower() in _KNOWN_INSECURE_VALUES:
        errors.append(f"{name} is still set to an insecure default value. Regenerate it.")
        return
    if len(value) < min_length:
        errors.append(
            f"{name} is too short ({len(value)} chars, minimum {min_length}). "
            "Generate with: openssl rand -hex 32"
        )


def validate_production_config() -> None:
    """
    Strict checks — only run in production.
    FIX: errors/warnings are local lists, not module-level state,
         so this function is safe to call multiple times.
    """
    errors: list[str] = []
    warnings: list[str] = []

    # Required secrets
    _check_secret(errors, "SECRET_KEY", settings.SECRET_KEY)
    _check_secret(errors, "JWT_SECRET_KEY", settings.JWT_SECRET_KEY)

    # Database
    if settings.DATABASE_URL == "postgresql://vitar:vitar@localhost:5432/vitar":
        errors.append("DATABASE_URL uses the default dev password. Set a strong POSTGRES_PASSWORD in .env")

    # CORS
    prod_origins = [o for o in settings.ALLOWED_ORIGINS if "localhost" not in o and "127.0.0.1" not in o]
    if not prod_origins:
        errors.append("ALLOWED_ORIGINS contains no production origin. Set it to your domain.")

    # Payment: at least one provider
    has_paystack = bool(settings.PAYSTACK_SECRET_KEY and not settings.PAYSTACK_SECRET_KEY.startswith("sk_test"))
    has_stripe   = bool(settings.STRIPE_SECRET_KEY and not settings.STRIPE_SECRET_KEY.startswith("sk_test"))
    has_flutter  = bool(settings.FLUTTERWAVE_SECRET_KEY)
    if not (has_paystack or has_stripe or has_flutter):
        warnings.append("No production payment provider configured.")

    # Notifications
    if not settings.SENDGRID_API_KEY:
        warnings.append("SENDGRID_API_KEY not set — transactional emails will not work.")
    if not (settings.TERMII_API_KEY or settings.TWILIO_ACCOUNT_SID):
        warnings.append("No SMS provider configured — appointment reminders via SMS will not work.")

    # Storage
    storage_backend = getattr(settings, 'STORAGE_BACKEND', 'local').lower()
    if storage_backend == 's3':
        if not settings.AWS_ACCESS_KEY_ID or not settings.AWS_SECRET_ACCESS_KEY:
            errors.append(
                "STORAGE_BACKEND=s3 but AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY are empty. "
                "Provide credentials or switch to STORAGE_BACKEND=local for dev."
            )
        if not settings.AWS_S3_BUCKET:
            errors.append("AWS_S3_BUCKET is empty. Set a bucket name.")
    elif storage_backend == 'local':
        if getattr(settings, "ALLOW_LOCAL_UPLOADS_IN_PRODUCTION", False):
            warnings.append(
                "STORAGE_BACKEND=local is enabled in production for a single-node deployment. "
                "Do not upload clinical documents or PHI here; move to S3-compatible object storage "
                "before horizontal scaling."
            )
        else:
            errors.append(
                "STORAGE_BACKEND=local is not safe for production unless explicitly accepted. "
                "Files are stored on the container filesystem and are not shared across replicas. "
                "Set STORAGE_BACKEND=s3 or ALLOW_LOCAL_UPLOADS_IN_PRODUCTION=true for a documented "
                "single-node deployment that only stores non-clinical assets."
            )
    else:
        errors.append(f"Unknown STORAGE_BACKEND={storage_backend!r}. Valid values: s3, local.")

    # Monitoring
    if not settings.SENTRY_DSN:
        warnings.append("SENTRY_DSN not set — error tracking disabled.")

    # Dashboard passwords
    if settings.GRAFANA_PASSWORD in _KNOWN_INSECURE_VALUES:
        errors.append("GRAFANA_PASSWORD is set to default. Change it.")
    if settings.FLOWER_PASSWORD in _KNOWN_INSECURE_VALUES:
        errors.append("FLOWER_PASSWORD is set to default. Change it.")

    for w in warnings:
        logger.warning(f"[startup] CONFIG WARN: {w}")

    if errors:
        logger.critical(
            f"[startup] {len(errors)} configuration error(s). "
            "Refusing to start.\n" + "\n".join(f"  ✗ {e}" for e in errors)
        )
        sys.exit(1)

    if warnings:
        logger.warning(
            f"[startup] {len(warnings)} configuration warning(s):\n"
            + "\n".join(f"  ⚠ {w}" for w in warnings)
        )

    logger.info("[startup] Configuration validated ✓")


def validate_config() -> None:
    """Entry point — strict checks only in production."""
    if settings.ENVIRONMENT == "production":
        validate_production_config()
    else:
        logger.info(f"[startup] Skipping strict config validation (ENVIRONMENT={settings.ENVIRONMENT})")
