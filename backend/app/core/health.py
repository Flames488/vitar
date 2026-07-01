"""
Vitar v5 - Health Check & Self-Healing Service
Detects failing components, reports status, triggers recovery actions.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any

logger = logging.getLogger(__name__)


def check_database(db) -> Dict[str, Any]:
    """
    Verify DB connection is alive and measure latency.

    Uses a raw autocommit connection (via the engine) instead of the ORM
    session so the probe costs exactly 1 round trip (SELECT 1) rather than
    3 (BEGIN → SELECT 1 → ROLLBACK).  The `db` arg is kept for API
    compatibility but is only used to reach the engine.
    """
    import time
    try:
        from sqlalchemy import text
        from app.core.database import engine

        # execution_options(isolation_level="AUTOCOMMIT") avoids the implicit
        # transaction that the ORM session always opens, cutting RTTs from 3→1.
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            t0 = time.perf_counter()
            conn.execute(text("SELECT 1"))
            latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        return {"status": "ok", "latency_ms": latency_ms}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def check_redis() -> Dict[str, Any]:
    """Verify Redis is reachable and return cache stats."""
    try:
        from app.core.cache import cache
        if not cache.ping():
            return {"status": "error", "error": "ping failed"}
        info = cache.info()
        return {"status": "ok", **info}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def check_celery() -> Dict[str, Any]:
    """Check if Celery workers are active."""
    try:
        from app.workers.celery_app import celery
        inspect = celery.control.inspect(timeout=2.0)
        active = inspect.active()
        if active:
            worker_count = len(active)
            return {"status": "ok", "workers": worker_count}
        return {"status": "warn", "workers": 0, "message": "No active workers detected"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def readiness_check(db) -> Dict[str, Any]:
    """
    Lightweight readiness probe for Docker/Nginx health checks.

    Keep this intentionally cheap: it verifies dependencies needed to serve
    requests, but avoids Celery inspection, queue scans, autoscaler status, and
    host-level psutil sampling. Those belong in the richer /health endpoint.
    """
    components = {
        "database": check_database(db),
        "redis": check_redis(),
    }
    overall = "healthy"
    for component in components.values():
        if component.get("status") != "ok":
            overall = "unhealthy"
            break
    return {
        "status": overall,
        "components": components,
        "timestamp": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
    }


def get_stuck_notifications_count(db) -> int:
    """Count notifications stuck in pending for more than 1 hour."""
    try:
        from app.models.models import Notification, NotificationStatus
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=1)
        return db.query(Notification).filter(
            Notification.status == NotificationStatus.PENDING,
            Notification.scheduled_for <= cutoff,
        ).count()
    except Exception:
        return -1


def get_failed_jobs_count(db) -> int:
    """Count permanently failed notifications in last 24h."""
    try:
        from app.models.models import Notification, NotificationStatus
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=24)
        return db.query(Notification).filter(
            Notification.status == NotificationStatus.FAILED,
            Notification.failed_at >= cutoff,
        ).count()
    except Exception:
        return -1


def full_health_check(db) -> Dict[str, Any]:
    """
    Aggregated health check — used by /health endpoint and monitoring.
    Returns overall status and per-component details.
    """
    components = {
        "database": check_database(db),
        "redis":    check_redis(),
        "celery":   check_celery(),
    }

    stuck   = get_stuck_notifications_count(db)
    failed  = get_failed_jobs_count(db)

    components["notifications"] = {
        "stuck_pending": stuck,
        "failed_24h":    failed,
        "status": "warn" if stuck > 50 or failed > 100 else "ok",
    }

    # Overall status: degraded if any critical component is down
    critical = ["database", "redis"]
    overall = "healthy"
    for comp in critical:
        if components[comp].get("status") == "error":
            overall = "unhealthy"
            break
    else:
        if any(v.get("status") == "warn" for v in components.values()):
            overall = "degraded"

    # ── Queue depths and worker heartbeats (v8) ──────────────────────────────
    try:
        from app.core.observability import get_queue_depths, get_worker_heartbeats
        components["queues"]  = get_queue_depths()
        components["workers"] = get_worker_heartbeats()
    except Exception as exc:
        components["queues"]  = {"error": str(exc)}
        components["workers"] = {}

    # ── Circuit breaker states (v9) ───────────────────────────────────────────
    try:
        from app.core.circuit_breaker import all_statuses as cb_statuses
        all_cb = cb_statuses()
        open_circuits = [c for c in all_cb if c["state"] == "open"]
        components["circuits"] = {
            "total": len(all_cb),
            "open_count": len(open_circuits),
            "open":       [c["circuit"] for c in open_circuits],
            "status":     "warn" if open_circuits else "ok",
        }
        if open_circuits and overall == "healthy":
            overall = "degraded"
    except Exception as exc:
        components["circuits"] = {"error": str(exc)}

    # ── Autoscaler status (v9) ────────────────────────────────────────────────
    try:
        from app.core.autoscaler import AutoScaler
        scaler = AutoScaler(dry_run=True)
        components["autoscaler"] = scaler.status()
    except Exception as exc:
        components["autoscaler"] = {"error": str(exc)}

    # ── DB pool status (v9) ───────────────────────────────────────────────────
    try:
        from app.core.database import pool_status, engine
        components["db_pool"] = pool_status(engine)
    except Exception as exc:
        components["db_pool"] = {"error": str(exc)}

    # ── System resource snapshot (v10) ────────────────────────────────────────
    try:
        from app.core.system_metrics import collect as collect_system
        snap = collect_system()
        if snap:
            components["system"] = snap.to_dict()
            components["system"]["status"] = snap.status
            if snap.status == "critical" and overall == "healthy":
                overall = "degraded"
            # Update circuit open gauge
            try:
                from app.core.circuit_breaker import all_statuses as _cb_statuses
                from app.core.metrics import CIRCUIT_OPEN_GAUGE
                open_count = len([c for c in _cb_statuses() if c["state"] == "open"])
                CIRCUIT_OPEN_GAUGE.set(open_count)
            except Exception:
                pass
        else:
            components["system"] = {"status": "unavailable", "note": "psutil not installed"}
    except Exception as exc:
        components["system"] = {"error": str(exc)}

    if overall != "healthy":
        logger.warning(
            "Health check degraded",
            extra={"components": components, "overall": overall}
        )

    return {
        "status":     overall,
        "version":    "9.0.0",
        "timestamp":  datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
        "components": components,
    }
