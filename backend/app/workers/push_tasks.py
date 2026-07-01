"""
Vitar — Push Notification Celery Tasks

Add these tasks to your existing tasks.py or import this module in celery_app.py.

Tasks:
  send_push_reminders(appointment_id)
    — fires Web Push to all subscribed users of the clinic owning the appointment.
    — tracks: appointment_reminder_sent

  cleanup_expired_push_subscriptions
    — runs daily; removes 410-Gone subscriptions from DB.
"""

import logging
from app.workers.celery_app import celery
from app.core.database import SessionLocal
from app.core.logging import get_logger

logger = get_logger(__name__)


@celery.task(
    name="app.workers.push_tasks.send_push_reminders",
    bind=True,
    max_retries=2,
    autoretry_for=(Exception,),
    retry_backoff=60,
    retry_jitter=True,
    queue="notifications",
)
def send_push_reminders(self, appointment_id: str):
    """
    Send Web Push reminders to all clinic users subscribed for the
    appointment's clinic. Called from schedule_appointment_reminders
    when a push channel is available.

    Tracks: appointment_reminder_sent (per subscription)
    """
    from app.core.config import settings

    vapid_private = getattr(settings, "VAPID_PRIVATE_KEY", "")
    vapid_public = getattr(settings, "VAPID_PUBLIC_KEY", "")
    vapid_email = getattr(settings, "VAPID_CLAIMS_EMAIL", "noreply@vitar.health")

    if not vapid_private or not vapid_public:
        logger.warning("send_push_reminders: VAPID keys not configured — skipping")
        return

    db = SessionLocal()
    try:
        from app.models.models import Appointment, Patient, Doctor, Clinic
        from app.models.models import PushSubscription   # added via migration 011
        from app.services.push_service import send_push_notification, build_reminder_payload
        from app.core.utils import utcnow

        apt = db.query(Appointment).filter(Appointment.id == appointment_id).first()
        if not apt:
            return

        patient = db.query(Patient).filter(Patient.id == apt.patient_id).first()
        doctor = db.query(Doctor).filter(Doctor.id == apt.doctor_id).first()
        clinic = db.query(Clinic).filter(Clinic.id == apt.clinic_id).first()

        if not patient or not clinic:
            return

        subscriptions = (
            db.query(PushSubscription)
            .filter(PushSubscription.clinic_id == apt.clinic_id)
            .all()
        )

        if not subscriptions:
            logger.info(f"send_push_reminders: no push subscriptions for clinic {apt.clinic_id}")
            return

        payload = build_reminder_payload(
            patient_name=patient.full_name,
            doctor_name=doctor.full_name if doctor else "Doctor",
            scheduled_at=apt.scheduled_at,
            clinic_name=clinic.name,
            appointment_id=str(apt.id),
            frontend_url=settings.FRONTEND_URL,
        )

        expired_ids = []
        sent = 0
        for sub in subscriptions:
            success = send_push_notification(
                endpoint=sub.endpoint,
                p256dh=sub.p256dh,
                auth=sub.auth,
                payload=payload,
                vapid_private_key=vapid_private,
                vapid_public_key=vapid_public,
                vapid_claims_email=vapid_email,
            )
            if success:
                sent += 1
                # Track appointment_reminder_sent
                _track_event("appointment_reminder_sent", {
                    "appointment_id": appointment_id,
                    "clinic_id": str(apt.clinic_id),
                    "channel": "push",
                })
            else:
                # 410-Gone or persistent failure — queue for cleanup
                expired_ids.append(sub.id)

        # Remove dead subscriptions
        if expired_ids:
            db.query(PushSubscription).filter(
                PushSubscription.id.in_(expired_ids)
            ).delete(synchronize_session=False)
            db.commit()
            logger.info(f"send_push_reminders: removed {len(expired_ids)} expired subscriptions")

        logger.info(
            f"send_push_reminders: sent {sent}/{len(subscriptions)} push notifications for apt {appointment_id}"
        )

    except Exception as exc:
        db.rollback()
        logger.error(f"send_push_reminders failed: {exc}", exc_info=True)
        raise self.retry(exc=exc)
    finally:
        db.close()


@celery.task(
    name="app.workers.push_tasks.cleanup_expired_push_subscriptions",
    bind=True,
    max_retries=1,
    queue="celery",
)
def cleanup_expired_push_subscriptions(self):
    """
    Daily task: ping each stored endpoint; remove any that return 410 Gone.
    Keeps the push_subscriptions table lean.
    """
    db = SessionLocal()
    try:
        from app.models.models import PushSubscription
        from app.core.config import settings
        from app.services.push_service import send_push_notification

        vapid_private = getattr(settings, "VAPID_PRIVATE_KEY", "")
        vapid_public = getattr(settings, "VAPID_PUBLIC_KEY", "")
        vapid_email = getattr(settings, "VAPID_CLAIMS_EMAIL", "noreply@vitar.health")

        if not vapid_private:
            return

        subs = db.query(PushSubscription).all()
        expired = []
        for sub in subs:
            # Send a silent ping (empty payload validated by VAPID)
            ok = send_push_notification(
                endpoint=sub.endpoint,
                p256dh=sub.p256dh,
                auth=sub.auth,
                payload={"type": "ping"},
                vapid_private_key=vapid_private,
                vapid_public_key=vapid_public,
                vapid_claims_email=vapid_email,
            )
            if not ok:
                expired.append(sub.id)

        if expired:
            db.query(PushSubscription).filter(
                PushSubscription.id.in_(expired)
            ).delete(synchronize_session=False)
            db.commit()
            logger.info(f"cleanup_expired_push_subscriptions: removed {len(expired)} stale subscriptions")

    except Exception as exc:
        db.rollback()
        logger.error(f"cleanup_expired_push_subscriptions error: {exc}")
    finally:
        db.close()


def _track_event(event: str, data: dict):
    """Fire a Sentry breadcrumb for server-side push event tracking."""
    try:
        import sentry_sdk
        sentry_sdk.add_breadcrumb(
            category="push_analytics",
            message=event,
            data=data,
            level="info",
        )
    except Exception:
        pass
    logger.info("push_analytics_event", extra={"event": event, **data})
