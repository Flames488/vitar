"""
Vitar v5 - Structured JSON Logger
Replaces all basic logging.getLogger() calls with structured output.
Produces JSON logs for log aggregators (CloudWatch, Datadog, Loki).
"""

import logging
import json
import sys
import traceback
from datetime import datetime, timezone
from typing import Any, Dict, Optional


class JSONFormatter(logging.Formatter):
    """Formats log records as single-line JSON for log ingestion pipelines."""

    LEVEL_MAP = {
        logging.DEBUG:    "DEBUG",
        logging.INFO:     "INFO",
        logging.WARNING:  "WARN",
        logging.ERROR:    "ERROR",
        logging.CRITICAL: "CRITICAL",
    }

    def format(self, record: logging.LogRecord) -> str:
        log: Dict[str, Any] = {
            "ts":      datetime.now(timezone.utc).isoformat(),
            "level":   self.LEVEL_MAP.get(record.levelno, record.levelname),
            "logger":  record.name,
            "msg":     record.getMessage(),
            "module":  record.module,
            "fn":      record.funcName,
            "line":    record.lineno,
        }

        # Attach extra fields passed via extra={} kwarg
        for key, val in record.__dict__.items():
            if key not in (
                "name", "msg", "args", "levelname", "levelno", "pathname",
                "filename", "module", "exc_info", "exc_text", "stack_info",
                "lineno", "funcName", "created", "msecs", "relativeCreated",
                "thread", "threadName", "processName", "process", "message",
            ):
                if not key.startswith("_"):
                    log[key] = val

        # Attach exception info if present
        if record.exc_info and record.exc_info[0] is not None:
            log["exception"] = {
                "type":  record.exc_info[0].__name__,
                "value": str(record.exc_info[1]),
                "trace": traceback.format_exception(*record.exc_info),
            }

        return json.dumps(log, default=str)


def configure_logging(level: str = "INFO", json_logs: bool = True) -> None:
    """
    Call once at application startup.
    In development: human-readable format.
    In production: JSON format.
    """
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Remove any default handlers
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(getattr(logging, level.upper(), logging.INFO))

    if json_logs:
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))

    root.addHandler(handler)

    # Silence noisy third-party loggers
    for noisy in ("uvicorn.access", "sqlalchemy.engine", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Convenience wrapper — use instead of logging.getLogger()."""
    return logging.getLogger(name)


# ── Event-specific structured log helpers ─────────────────────────────────────

_logger = get_logger("vitar.events")


def log_payment_event(
    event: str,
    provider: str,
    reference: Optional[str],
    clinic_id: Optional[str],
    amount: Optional[float] = None,
    status: str = "unknown",
    extra: Optional[Dict] = None,
):
    _logger.info(
        f"PAYMENT {event}",
        extra={
            "event_type": "payment",
            "event": event,
            "provider": provider,
            "reference": reference,
            "clinic_id": clinic_id,
            "amount": amount,
            "status": status,
            **(extra or {}),
        },
    )


def log_booking_event(
    event: str,
    appointment_id: Optional[str],
    clinic_id: Optional[str],
    doctor_id: Optional[str] = None,
    patient_id: Optional[str] = None,
    status: str = "ok",
    extra: Optional[Dict] = None,
):
    _logger.info(
        f"BOOKING {event}",
        extra={
            "event_type": "booking",
            "event": event,
            "appointment_id": appointment_id,
            "clinic_id": clinic_id,
            "doctor_id": doctor_id,
            "patient_id": patient_id,
            "status": status,
            **(extra or {}),
        },
    )


def log_notification_event(
    event: str,
    notification_id: Optional[str],
    channel: str,
    recipient: Optional[str],
    status: str,
    retry_count: int = 0,
    error: Optional[str] = None,
):
    level = logging.WARNING if status == "failed" else logging.INFO
    _logger.log(
        level,
        f"NOTIFICATION {event}",
        extra={
            "event_type": "notification",
            "event": event,
            "notification_id": notification_id,
            "channel": channel,
            "recipient": recipient[:4] + "***" if recipient and len(recipient) > 4 else recipient,
            "status": status,
            "retry_count": retry_count,
            "error": error,
        },
    )


def log_system_error(
    component: str,
    error: Exception,
    context: Optional[Dict] = None,
):
    _logger.error(
        f"SYSTEM ERROR in {component}",
        exc_info=error,
        extra={
            "event_type": "system_error",
            "component": component,
            **(context or {}),
        },
    )
