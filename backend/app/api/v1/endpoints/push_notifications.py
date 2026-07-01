"""
Vitar — Push Notification Subscription Endpoints
Handles Web Push subscription storage and server-sent reminders.

POST /api/v1/push/subscribe   — save a browser push subscription
DELETE /api/v1/push/subscribe — remove subscription
GET  /api/v1/push/vapid-key   — return public VAPID key to the frontend

Tracks (via Sentry breadcrumbs + PostHog backend events):
  appointment_reminder_sent
  appointment_reminder_opened
  appointment_confirmed
"""

import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_clinic, get_current_user
from app.core.config import settings

router = APIRouter()
logger = logging.getLogger(__name__)


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class PushSubscriptionKeys(BaseModel):
    p256dh: str
    auth: str


class PushSubscribeRequest(BaseModel):
    endpoint: str
    keys: PushSubscriptionKeys
    user_agent: Optional[str] = None


class PushEventRequest(BaseModel):
    """Frontend calls this when a push notification is opened/actioned."""
    event: str          # appointment_reminder_opened | appointment_confirmed
    appointment_id: Optional[str] = None
    notification_id: Optional[str] = None


# ── VAPID public key ─────────────────────────────────────────────────────────

@router.get("/vapid-key")
def get_vapid_key():
    """Return the VAPID public key so the SW can subscribe."""
    key = getattr(settings, "VAPID_PUBLIC_KEY", "")
    if not key:
        raise HTTPException(status_code=503, detail="Push notifications not configured")
    return {"publicKey": key}


# ── Subscribe / unsubscribe ──────────────────────────────────────────────────

@router.post("/subscribe", status_code=201)
def subscribe(
    body: PushSubscribeRequest,
    request: Request,
    clinic=Depends(get_current_clinic),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Store a Web Push subscription for the current clinic user.
    Upserts on endpoint so refreshed subscriptions don't create duplicates.
    """
    from app.models.models import PushSubscription  # added via migration 011

    existing = (
        db.query(PushSubscription)
        .filter(PushSubscription.endpoint == body.endpoint)
        .first()
    )

    if existing:
        existing.p256dh = body.keys.p256dh
        existing.auth = body.keys.auth
        existing.user_agent = body.user_agent
    else:
        sub = PushSubscription(
            clinic_id=clinic.id,
            user_id=current_user.id,
            endpoint=body.endpoint,
            p256dh=body.keys.p256dh,
            auth=body.keys.auth,
            user_agent=body.user_agent,
        )
        db.add(sub)

    db.commit()
    logger.info(
        "push_subscribe",
        extra={"clinic_id": str(clinic.id), "user_id": str(current_user.id)},
    )
    return {"status": "subscribed"}


@router.delete("/subscribe")
def unsubscribe(
    body: PushSubscribeRequest,
    clinic=Depends(get_current_clinic),
    db: Session = Depends(get_db),
):
    """Remove a push subscription (called when user revokes permission)."""
    from app.models.models import PushSubscription

    db.query(PushSubscription).filter(
        PushSubscription.endpoint == body.endpoint,
        PushSubscription.clinic_id == clinic.id,
    ).delete()
    db.commit()
    return {"status": "unsubscribed"}


# ── Client-side event tracking ───────────────────────────────────────────────

@router.post("/event")
def track_push_event(
    body: PushEventRequest,
    clinic=Depends(get_current_clinic),
    db: Session = Depends(get_db),
):
    """
    Frontend reports push notification interactions back to the server.
    We log them and optionally update appointment state.

    Events:
      appointment_reminder_opened  — user tapped the push notification
      appointment_confirmed        — user confirmed via push action button
    """
    _log_push_event(body.event, body.appointment_id, body.notification_id, str(clinic.id))

    if body.event == "appointment_confirmed" and body.appointment_id:
        _confirm_appointment(body.appointment_id, clinic.id, db)

    return {"status": "ok"}


# ── Helpers ──────────────────────────────────────────────────────────────────

def _log_push_event(
    event: str,
    appointment_id: Optional[str],
    notification_id: Optional[str],
    clinic_id: str,
):
    try:
        import sentry_sdk
        sentry_sdk.add_breadcrumb(
            category="push_notification",
            message=event,
            data={"appointment_id": appointment_id, "notification_id": notification_id},
            level="info",
        )
    except Exception:
        pass

    logger.info(
        "push_event",
        extra={
            "event": event,
            "appointment_id": appointment_id,
            "notification_id": notification_id,
            "clinic_id": clinic_id,
        },
    )


def _confirm_appointment(appointment_id: str, clinic, db: Session):
    from app.models.models import Appointment, AppointmentStatus

    apt = db.query(Appointment).filter(
        Appointment.id == appointment_id,
        Appointment.clinic_id == clinic.id,
    ).first()

    if apt and apt.status == AppointmentStatus.CONFIRMED:
        # Already confirmed — idempotent
        return

    if apt and apt.status == AppointmentStatus.PENDING:
        apt.status = AppointmentStatus.CONFIRMED
        db.commit()
        logger.info(f"appointment confirmed via push: {appointment_id}")
