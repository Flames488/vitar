"""
Vitar — Production FastAPI Application
"""

import asyncio
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.core.database import engine, Base, get_db
from app.api.v1.router import api_router
from app.core.middleware import RateLimitMiddleware, RequestLoggingMiddleware
from app.core.cookie_auth import csrf_protect
from app.core.metrics import metrics_router, MetricsMiddleware, instrument_sqlalchemy
from app.core.startup_validation import validate_config

# ── Sentry (optional) ─────────────────────────────────────────────────────────
_sentry_enabled = False
try:
    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
    from sentry_sdk.integrations.celery import CeleryIntegration

    _dsn = getattr(settings, "SENTRY_DSN", "")
    if _dsn:
        sentry_sdk.init(
            dsn=_dsn,
            environment=settings.ENVIRONMENT,
            release="vitar@13.0.0",
            traces_sample_rate=0.1 if settings.ENVIRONMENT == "production" else 1.0,
            integrations=[
                FastApiIntegration(transaction_style="endpoint"),
                SqlalchemyIntegration(),
                CeleryIntegration(),
            ],
            send_default_pii=False,
        )
        _sentry_enabled = True
except ImportError:
    pass

# ── Logging first ─────────────────────────────────────────────────────────────
configure_logging(
    level="DEBUG" if settings.DEBUG else "INFO",
    json_logs=(settings.ENVIRONMENT == "production"),
)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Step 1: validate config before touching anything
    validate_config()

    logger.info(
        "Vitar API starting",
        extra={"environment": settings.ENVIRONMENT, "version": "13.0.0", "sentry": _sentry_enabled},
    )

    # Step 2: DB readiness gate — FIX: use get_running_loop() (Python 3.10+ safe)
    if "sqlite" not in settings.DATABASE_URL:
        try:
            from app.core.recovery import wait_for_db
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, wait_for_db, engine)
        except RuntimeError as exc:
            logger.error(f"DB startup gate failed: {exc}")
            raise

    # Step 3: Table creation — DEV only
    if "sqlite" in settings.DATABASE_URL:
        Base.metadata.create_all(bind=engine)

    # Instrument SQLAlchemy for slow query tracking + Prometheus metrics
    instrument_sqlalchemy(engine)

    # Step 4: Wire Celery dead-letter signal (graceful — Celery may not be running)
    try:
        from celery.signals import task_failure
        from app.workers.tasks import on_task_failure
        task_failure.connect(on_task_failure)
        logger.info("Dead-letter signal wired")
    except Exception as e:
        logger.warning(f"Dead-letter signal wiring skipped: {e}")

    logger.info("Vitar API ready", extra={"version": "13.0.0"})
    yield
    logger.info("Vitar API shutting down")


app = FastAPI(
    title="Vitar API",
    description="Healthcare Appointment Platform — AI No-Show Reduction",
    version="11.0.0",
    docs_url="/api/v1/docs" if settings.API_DOCS_ENABLED or settings.ENVIRONMENT != "production" else None,
    openapi_url="/api/v1/openapi.json" if settings.API_DOCS_ENABLED or settings.ENVIRONMENT != "production" else None,
    redoc_url=None,
    lifespan=lifespan,
)

# Serve locally stored uploads (only meaningful when STORAGE_BACKEND=local).
# When STORAGE_BACKEND=s3, this mount is harmless but unused — all URLs point to S3.
import os as _os
_upload_dir = settings.UPLOAD_DIR
_os.makedirs(_upload_dir, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=_upload_dir), name="uploads")

# ── CORS — Fix 9 ─────────────────────────────────────────────────────────────
# ALLOWED_ORIGINS must be set explicitly in .env. No automatic appending of
# *.workers.dev — that wildcard covers ALL Cloudflare Workers projects, not
# just Wabizz. An operator who forgets to set this env var gets a hard startup
# error rather than a silently over-permissive CORS policy.
#
# Set in vitar/.env:
#   ALLOWED_ORIGINS=["https://app.wabizz.com"]
#
# For local dev with Wrangler:
#   ALLOWED_ORIGINS=["http://localhost:5173","http://localhost:3000"]
_cors_origins: list[str] = list(settings.ALLOWED_ORIGINS)

if not _cors_origins:
    raise RuntimeError(
        "FATAL: ALLOWED_ORIGINS is empty. "
        "Set it in .env to the exact Wabizz production domain(s), e.g. "
        'ALLOWED_ORIGINS=[\"https://app.wabizz.com\"]. '
        "Do NOT use * or *.workers.dev — this would expose Vitar to any Cloudflare Worker."
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*", "X-CSRF-Token", "X-API-Key"],
)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(MetricsMiddleware)

if settings.ENVIRONMENT == "production":
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.ALLOWED_HOSTS)

app.include_router(api_router, prefix="/api/v1")
app.include_router(metrics_router)


@app.get("/health", tags=["System"])
def health_check(db: Session = Depends(get_db)):
    from app.core.health import full_health_check
    result = full_health_check(db)
    status_code = 200 if result["status"] in ("healthy", "degraded") else 503
    return JSONResponse(content=result, status_code=status_code)


@app.get("/health/live", tags=["System"])
def liveness_check():
    return {"status": "alive", "service": "Vitar API"}


@app.get("/health/ready", tags=["System"])
def readiness_check(db: Session = Depends(get_db)):
    from app.core.health import readiness_check as run_readiness_check
    result = run_readiness_check(db)
    status_code = 200 if result["status"] == "healthy" else 503
    return JSONResponse(content=result, status_code=status_code)


@app.get("/health/circuits", tags=["System"])
async def circuit_breaker_status():
    from app.core.recovery import all_circuit_statuses
    circuits = all_circuit_statuses()
    any_open = any(c["state"] == "open" for c in circuits)
    return JSONResponse(
        content={"status": "degraded" if any_open else "ok", "circuits": circuits},
        status_code=503 if any_open else 200,
    )


@app.get("/", tags=["System"])
async def root():
    return {"service": "Vitar API", "version": "13.0.0", "docs": "/api/docs"}


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(
        "Unhandled exception",
        exc_info=exc,
        extra={"path": request.url.path, "method": request.method},
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "detail": str(exc) if settings.DEBUG else "An unexpected error occurred",
        },
    )
