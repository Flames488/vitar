"""
Vitar — Web Push Service

Sends push notifications to clinic users' browsers/PWA.
Uses pywebpush (VAPID).

Install: pip install pywebpush

Required env vars:
  VAPID_PRIVATE_KEY   — base64url-encoded VAPID private key
  VAPID_PUBLIC_KEY    — base64url-encoded VAPID public key
  VAPID_CLAIMS_EMAIL  — mailto: address for VAPID claims

Events tracked in Sentry + structured logs:
  appointment_reminder_sent
  appointment_reminder_opened   (via /api/v1/push/event endpoint)
  appointment_confirmed         (via /api/v1/push/event endpoint)
"""

import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_vapid_available = False
try:
    from pywebpush import webpush, WebPushException  # type: ignore
    _vapid_available = True
except ImportError:
    logger.warning("pywebpush not installed — push notifications disabled. Run: pip install pywebpush")


def send_push_notification(
    endpoint: str,
    p256dh: str,
    auth: str,
    payload: dict,
    vapid_private_key: str,
    vapid_public_key: str,
    vapid_claims_email: str,
) -> bool:
    """
    Send a single Web Push message.
    Returns True on success, False on failure (logs the error).
    """
    if not _vapid_available:
        logger.warning("push skipped — pywebpush not installed")
        return False

    try:
        webpush(
            subscription_info={
                "endpoint": endpoint,
                "keys": {"p256dh": p256dh, "auth": auth},
            },
            data=json.dumps(payload),
            vapid_private_key=vapid_private_key,
            vapid_claims={
                "sub": f"mailto:{vapid_claims_email}",
            },
            content_encoding="aes128gcm",
        )

        _sentry_breadcrumb("push_sent", payload)
        logger.info(
            "push_notification_sent",
            extra={"title": payload.get("title"), "endpoint_prefix": endpoint[:40]},
        )
        return True

    except WebPushException as exc:  # type: ignore
        # 410 Gone = subscription expired; caller should delete it from DB
        status = getattr(exc.response, "status_code", None) if exc.response else None
        logger.warning(
            "push_notification_failed",
            extra={"status": status, "error": str(exc)[:200]},
        )
        if status == 410:
            return False  # caller deletes subscription
        return False

    except Exception as exc:
        logger.error("push_notification_error", exc_info=exc)
        return False


def build_reminder_payload(
    patient_name: str,
    doctor_name: str,
    scheduled_at,
    clinic_name: str,
    appointment_id: str,
    frontend_url: str,
) -> dict:
    """Build the JSON payload sent to the browser SW."""
    from datetime import datetime
    if isinstance(scheduled_at, str):
        scheduled_at = datetime.fromisoformat(scheduled_at)

    date_str = scheduled_at.strftime("%a %d %b, %I:%M %p")
    return {
        "title": f"Appointment Reminder — {clinic_name}",
        "body": f"Hi {patient_name}, your appointment with {doctor_name} is on {date_str}.",
        "icon": "/icon-192x192.png",
        "badge": "/icon-72x72.png",
        "tag": f"reminder-{appointment_id}",
        "data": {
            "url": f"{frontend_url}/appointments/{appointment_id}",
            "appointment_id": appointment_id,
            "event": "appointment_reminder_opened",
        },
        "actions": [
            {"action": "confirm", "title": "✓ Confirm"},
            {"action": "dismiss", "title": "Dismiss"},
        ],
    }


def _sentry_breadcrumb(message: str, data: dict):
    try:
        import sentry_sdk
        sentry_sdk.add_breadcrumb(
            category="push_notification",
            message=message,
            data=data,
            level="info",
        )
    except Exception:
        pass
