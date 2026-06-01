"""
Vitar v8 — Enhanced Observability

Adds:
  1. Structured alert hooks (Slack / generic webhook)
  2. Worker heartbeat tracking in Redis
  3. Queue depth monitoring
  4. SLA breach detection (p95 latency threshold alerts)
"""

import time
import logging
import threading
from typing import Optional
from datetime import datetime, timezone

logger = logging.getLogger("vitar.observability")

# ── Alert severity levels ─────────────────────────────────────────────────────
CRITICAL = "critical"
WARNING  = "warning"
INFO     = "info"


def send_alert(
    title: str,
    message: str,
    severity: str = WARNING,
    component: str = "unknown",
    extra: Optional[dict] = None,
) -> bool:
    """
    Send a structured alert to the configured webhook (Slack / PagerDuty).
    Fails silently if no webhook is configured — never crashes the app.
    Returns True if alert was dispatched.
    """
    try:
        from app.core.config import settings
        webhook_url = getattr(settings, "SLACK_WEBHOOK_URL", "") or ""
        if not webhook_url:
            logger.warning(
                f"ALERT [{severity.upper()}] {title}: {message}",
                extra={"component": component, "severity": severity, **(extra or {})},
            )
            return False

        import httpx
        emoji = {"critical": "🔴", "warning": "🟠", "info": "🔵"}.get(severity, "⚪")
        payload = {
            "text": f"{emoji} *Vitar Alert — {title}*",
            "attachments": [
                {
                    "color": {"critical": "danger", "warning": "warning", "info": "good"}.get(severity, "#cccccc"),
                    "fields": [
                        {"title": "Message",   "value": message,   "short": False},
                        {"title": "Component", "value": component, "short": True},
                        {"title": "Severity",  "value": severity,  "short": True},
                        {"title": "Host",      "value": _hostname(), "short": True},
                        {"title": "Time",      "value": datetime.now(timezone.utc).isoformat(), "short": True},
                        *([{"title": k, "value": str(v), "short": True} for k, v in (extra or {}).items()])
                    ],
                }
            ],
        }

        resp = httpx.post(webhook_url, json=payload, timeout=5)
        if resp.status_code != 200:
            logger.warning(f"Alert webhook returned {resp.status_code}")
            return False
        return True

    except Exception as exc:
        logger.warning(f"send_alert failed: {exc}")
        return False


def _hostname() -> str:
    try:
        import socket
        return socket.gethostname()
    except Exception:
        return "unknown"


# ── Worker Heartbeat ──────────────────────────────────────────────────────────

def worker_heartbeat(worker_id: str, interval_seconds: int = 30) -> None:
    """
    Write a Redis heartbeat key every `interval_seconds`.
    Call from Celery worker startup signal.
    The watchdog script checks these keys to detect dead workers without
    relying solely on Docker healthchecks.

    Key schema: heartbeat:<worker_id>   TTL: interval_seconds * 3
    """
    def _beat():
        try:
            import redis as redis_lib
            from app.core.config import settings
            r = redis_lib.from_url(settings.REDIS_URL, decode_responses=True, socket_connect_timeout=2)
            ttl = interval_seconds * 3
            while True:
                try:
                    r.set(f"heartbeat:{worker_id}", datetime.now(timezone.utc).isoformat(), ex=ttl)
                except Exception as exc:
                    logger.warning(f"Heartbeat write failed: {exc}")
                time.sleep(interval_seconds)
        except Exception as exc:
            logger.error(f"Heartbeat thread crashed: {exc}")

    t = threading.Thread(target=_beat, daemon=True, name=f"heartbeat-{worker_id}")
    t.start()
    logger.info(f"Worker heartbeat started", extra={"worker_id": worker_id, "interval": interval_seconds})


def get_worker_heartbeats() -> dict:
    """Return all active worker heartbeats from Redis."""
    try:
        import redis as redis_lib
        from app.core.config import settings
        r = redis_lib.from_url(settings.REDIS_URL, decode_responses=True, socket_connect_timeout=2)
        keys = r.keys("heartbeat:*")
        return {k.replace("heartbeat:", ""): r.get(k) for k in keys}
    except Exception as exc:
        logger.warning(f"get_worker_heartbeats failed: {exc}")
        return {}


# ── Queue Depth Monitor ───────────────────────────────────────────────────────

def get_queue_depths() -> dict:
    """
    Return Celery queue lengths from Redis.
    Used by /health endpoint and Prometheus metrics.
    """
    try:
        import redis as redis_lib
        from app.core.config import settings
        r = redis_lib.from_url(settings.REDIS_URL, decode_responses=True, socket_connect_timeout=2)
        queues = ["celery", "notifications", "reminders", "ai", "billing", "dead_letter"]
        depths = {}
        for q in queues:
            length = r.llen(q)
            depths[q] = int(length) if length is not None else 0

        # Alert if any queue is suspiciously deep
        for q, depth in depths.items():
            if depth > 500:
                send_alert(
                    title="Queue Depth Warning",
                    message=f"Queue '{q}' has {depth} pending tasks",
                    severity=CRITICAL if depth > 2000 else WARNING,
                    component=f"celery.{q}",
                    extra={"depth": depth, "queue": q},
                )
        return depths
    except Exception as exc:
        logger.warning(f"get_queue_depths failed: {exc}")
        return {}


# ── SLA Latency Tracker ───────────────────────────────────────────────────────

_latency_window: list[float] = []
_latency_lock = threading.Lock()
_LATENCY_ALERT_THRESHOLD_MS = 800.0   # p95 above this triggers alert
_LATENCY_WINDOW_SIZE = 200            # rolling window of last N requests


def record_request_latency(duration_ms: float, path: str) -> None:
    """
    Record a request duration for SLA tracking.
    Called from RequestLoggingMiddleware.
    Fires a Slack alert if rolling p95 exceeds threshold.
    """
    if path in ("/health", "/", "/metrics"):
        return

    with _latency_lock:
        _latency_window.append(duration_ms)
        if len(_latency_window) > _LATENCY_WINDOW_SIZE:
            _latency_window.pop(0)

        if len(_latency_window) >= 50:  # Only alert when we have a meaningful sample
            sorted_w = sorted(_latency_window)
            p95_idx = int(len(sorted_w) * 0.95)
            p95 = sorted_w[p95_idx]

            if p95 > _LATENCY_ALERT_THRESHOLD_MS:
                # Throttle: only fire alert once per 5 minutes
                _maybe_alert_latency(p95)


_last_latency_alert: float = 0.0


def _maybe_alert_latency(p95_ms: float) -> None:
    global _last_latency_alert
    now = time.monotonic()
    if now - _last_latency_alert < 300:  # 5 min cooldown
        return
    _last_latency_alert = now
    send_alert(
        title="API Latency SLA Breach",
        message=f"p95 response time is {p95_ms:.0f}ms (threshold: {_LATENCY_ALERT_THRESHOLD_MS:.0f}ms)",
        severity=WARNING,
        component="api.latency",
        extra={"p95_ms": round(p95_ms, 1), "window_size": len(_latency_window)},
    )
