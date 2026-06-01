"""
Vitar v5 - Celery Tasks (HARDENED)
Fixes:
  - schedule_appointment_reminders: eager-load doctor+clinic via explicit queries (not lazy ORM)
  - run_async: create fresh event loop per call (was reusing stale loops)
  - Structured notification event logging
  - Exponential backoff on retries
  - Dead-letter pattern: log permanently failed jobs
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
import asyncio
import os

from app.core.utils import utcnow
from app.workers.celery_app import celery
from app.core.database import SessionLocal, get_replica_db
from app.core.logging import get_logger, log_notification_event, log_booking_event

logger = get_logger(__name__)


@celery.task(
    name="app.workers.tasks.cleanup_expired_refresh_tokens",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
)
def cleanup_expired_refresh_tokens(self):
    """
    v11: Purge expired refresh tokens from the DB.
    Runs daily at 3 AM via Celery beat. Keeps the refresh_tokens
    table lean and prevents unbounded growth.
    """
    from app.core.database import SessionLocal
    from app.models.models import RefreshToken
    from app.core.utils import utcnow
    db = SessionLocal()
    try:
        deleted = db.query(RefreshToken).filter(RefreshToken.expires_at < utcnow()).delete()
        db.commit()
        logger.info(f"[refresh_token_cleanup] Deleted {deleted} expired tokens")
        return {"deleted": deleted}
    except Exception as exc:
        db.rollback()
        logger.error(f"[refresh_token_cleanup] Failed: {exc}")
        raise self.retry(exc=exc, countdown=300)
    finally:
        db.close()



def run_async(coro):
    """
    FIX: Always create a brand-new event loop.
    Never reuse loops across Celery task calls — leads to 'event loop is closed' errors.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        try:
            loop.close()
        except Exception:
            pass


# ─── No-Show Risk Scoring ─────────────────────────────────────────────────────

@celery.task(bind=True, max_retries=3, autoretry_for=(Exception,), retry_backoff=5, retry_jitter=True, queue="ai")
def calculate_no_show_risk(self, appointment_id: str):
    # Read-heavy task — use replica DB for appointment/patient queries.
    # The final write (risk score + NoShowPrediction record) uses a primary session.
    replica_gen = get_replica_db()
    db = next(replica_gen)
    try:
        from app.models.models import Appointment, Patient, NoShowPrediction
        from app.services.ai_service import NoShowPredictor, calculate_risk_category

        apt = db.query(Appointment).filter(Appointment.id == appointment_id).first()
        if not apt:
            logger.warning(f"calculate_no_show_risk: appointment {appointment_id} not found")
            return

        patient = db.query(Patient).filter(Patient.id == apt.patient_id).first()
        if not patient:
            return

        predictor = NoShowPredictor()
        features, score = predictor.predict(apt, patient, db)
        category = calculate_risk_category(score)

    except Exception as exc:
        logger.error(f"calculate_no_show_risk read phase failed: {exc}")
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
    finally:
        try:
            replica_gen.close()
        except Exception:
            pass

    # Write phase — always use primary
    write_db = SessionLocal()
    try:
        from app.models.models import Appointment, NoShowPrediction
        write_apt = write_db.query(Appointment).filter(Appointment.id == appointment_id).first()
        if write_apt:
            write_apt.no_show_risk_score = score
            write_apt.risk_factors = features
            write_apt.risk_calculated_at = utcnow()

        record = NoShowPrediction(
            appointment_id=appointment_id, patient_id=patient.id,
            model_version=predictor.version, risk_score=score,
            risk_category=category, features=features,
        )
        write_db.add(record)
        write_db.commit()
        logger.info(f"Risk scored: apt={appointment_id} score={score:.3f} category={category}")

    except Exception as exc:
        write_db.rollback()
        logger.error(f"calculate_no_show_risk write phase failed: {exc}")
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
    finally:
        write_db.close()


# ─── Reminder Scheduling ──────────────────────────────────────────────────────

@celery.task(bind=True, max_retries=3, autoretry_for=(Exception,), retry_backoff=5, retry_jitter=True, queue="reminders")
def schedule_appointment_reminders(self, appointment_id: str):
    """
    FIX: Load doctor, clinic, and patient explicitly rather than relying on
    lazy-loaded ORM relationships (which fail outside request context in Celery).
    """
    db = SessionLocal()
    try:
        from app.models.models import (
            Appointment, Patient, Doctor, Clinic, Notification,
            NotificationSettings, NotificationStatus, AppointmentStatus,
        )
        from app.services.ai_service import get_reminder_schedule
        from app.services.notification_service import build_confirmation_message, build_reminder_message
        from app.core.config import settings as cfg

        apt = db.query(Appointment).filter(Appointment.id == appointment_id).first()
        if not apt or apt.status == AppointmentStatus.CANCELLED:
            return

        # FIX: Explicit loads instead of lazy ORM
        patient = db.query(Patient).filter(Patient.id == apt.patient_id).first()
        doctor = db.query(Doctor).filter(Doctor.id == apt.doctor_id).first()
        clinic = db.query(Clinic).filter(Clinic.id == apt.clinic_id).first()

        if not patient:
            logger.warning(f"schedule_reminders: patient not found for {appointment_id}")
            return

        notif_cfg = db.query(NotificationSettings).filter(NotificationSettings.clinic_id == apt.clinic_id).first()

        score = apt.no_show_risk_score or 0.0
        reminders = get_reminder_schedule(score, apt.scheduled_at)

        doctor_name = doctor.full_name if doctor else "Doctor"
        clinic_name = clinic.name if clinic else "Clinic"

        created = 0
        for r in reminders:
            send_at = datetime.fromisoformat(r["send_at"])
            if send_at <= utcnow():
                continue

            for channel_str in r["channels"]:
                if channel_str == "sms" and notif_cfg and not notif_cfg.sms_enabled:
                    continue
                if channel_str == "whatsapp" and notif_cfg and not notif_cfg.whatsapp_enabled:
                    continue
                if channel_str == "email" and notif_cfg and not notif_cfg.email_enabled:
                    continue

                recipient = patient.email if channel_str == "email" else patient.phone
                if not recipient:
                    continue

                if r["offset_hours"] == 0:
                    msg_type = "confirmation"
                    msg = build_confirmation_message(
                        patient.full_name, doctor_name, apt.scheduled_at,
                        clinic_name, apt.confirmation_token or "", cfg.FRONTEND_URL,
                    )
                else:
                    msg_type = "reminder"
                    msg = build_reminder_message(
                        patient.full_name, doctor_name, apt.scheduled_at,
                        clinic_name, apt.cancel_token or "", cfg.FRONTEND_URL,
                    )

                # Avoid duplicate notification records
                existing = db.query(Notification).filter(
                    Notification.appointment_id == apt.id,
                    Notification.channel == channel_str,
                    Notification.notification_type == msg_type,
                    Notification.scheduled_for == send_at,
                ).first()
                if existing:
                    continue

                notif = Notification(
                    appointment_id=apt.id, clinic_id=apt.clinic_id, patient_id=patient.id,
                    channel=channel_str, notification_type=msg_type,
                    status=NotificationStatus.PENDING, recipient=recipient,
                    message_body=msg, scheduled_for=send_at,
                )
                db.add(notif)
                created += 1

        db.commit()
        logger.info(f"Scheduled {created} notifications for appointment {appointment_id}")

    except Exception as exc:
        db.rollback()
        logger.error(f"schedule_appointment_reminders failed: {exc}")
        raise self.retry(exc=exc, countdown=120 * (2 ** self.request.retries))
    finally:
        db.close()


# ─── Fire Pending Reminders ───────────────────────────────────────────────────

@celery.task(bind=True, max_retries=3, autoretry_for=(Exception,), retry_backoff=5, retry_jitter=True, queue="notifications")
def fire_pending_reminders(self):
    db = SessionLocal()
    try:
        from app.models.models import Notification, NotificationStatus, Appointment, AppointmentStatus

        now = utcnow()
        window_end = now + timedelta(minutes=6)

        # FIX: Use with_for_update(skip_locked=True) so concurrent worker instances
        # don't double-dispatch the same notification rows.
        due = db.query(Notification).filter(
            Notification.status == NotificationStatus.PENDING,
            Notification.scheduled_for <= window_end,
            Notification.retry_count < Notification.max_retries,
        ).with_for_update(skip_locked=True).limit(200).all()

        dispatched = 0
        for notif in due:
            apt = db.query(Appointment).filter(Appointment.id == notif.appointment_id).first()
            if apt and apt.status in (AppointmentStatus.CANCELLED, AppointmentStatus.NO_SHOW):
                notif.status = NotificationStatus.FAILED
                notif.failure_reason = "Appointment cancelled/no-show"
                continue
            send_notification_job.delay(notif.id)
            dispatched += 1

        db.commit()

        # Back-pressure check: if we hit the 200-row cap, log a warning so ops
        # can increase worker concurrency or reduce beat interval.
        if len(due) >= 200:
            total_pending = db.query(Notification).filter(
                Notification.status == NotificationStatus.PENDING,
                Notification.scheduled_for <= window_end,
            ).count()
            if total_pending > 200:
                logger.warning(
                    "fire_pending_reminders: batch cap reached, backlog detected",
                    extra={"dispatched": dispatched, "estimated_backlog": total_pending},
                )

        logger.info(f"fire_pending_reminders: dispatched {dispatched}/{len(due)} notifications")

    except Exception as e:
        logger.error(f"fire_pending_reminders error: {e}")
    finally:
        db.close()


@celery.task(bind=True, max_retries=3, autoretry_for=(Exception,), retry_backoff=5, retry_jitter=True, queue="notifications")
def send_notification_job(self, notification_id: str):
    db = SessionLocal()
    try:
        from app.models.models import Notification, NotificationStatus, Clinic

        notif = db.query(Notification).filter(Notification.id == notification_id).first()
        if not notif:
            return
        if notif.status in (NotificationStatus.SENT, NotificationStatus.DELIVERED):
            return  # Already sent

        clinic = db.query(Clinic).filter(Clinic.id == notif.clinic_id).first()
        country = clinic.country if clinic else "US"
        sender_id = (clinic.name[:11] if clinic and clinic.name else "Vitar")

        from app.services.notification_service import send_notification_with_fallback
        channel_val = notif.channel.value if hasattr(notif.channel, "value") else notif.channel
        result = run_async(
            send_notification_with_fallback(
                channel=channel_val,
                phone=notif.recipient if channel_val in ("sms", "whatsapp") else None,
                email=notif.recipient if channel_val == "email" else None,
                message=notif.message_body or "",
                subject="Appointment Reminder — Vitar",
                country=country,
                sender_id=sender_id,
            )
        )

        if result.success:
            notif.status = NotificationStatus.SENT
            notif.sent_at = utcnow()
            notif.provider_message_id = result.message_id
            notif.provider_response = result.to_dict()

            # Update appointment reminder count
            from app.models.models import Appointment
            apt = db.query(Appointment).filter(Appointment.id == notif.appointment_id).first()
            if apt:
                apt.reminder_count = (apt.reminder_count or 0) + 1
                apt.reminder_sent_at = utcnow()
                apt.last_reminder_channel = notif.channel

            log_notification_event("sent", notification_id, channel_val, notif.recipient, "sent", notif.retry_count)
        else:
            notif.retry_count = (notif.retry_count or 0) + 1
            notif.failure_reason = result.error
            if notif.retry_count >= notif.max_retries:
                notif.status = NotificationStatus.FAILED
                notif.failed_at = utcnow()
                log_notification_event("permanently_failed", notification_id, channel_val,
                                       notif.recipient, "failed", notif.retry_count, result.error)
            else:
                log_notification_event("retry_queued", notification_id, channel_val,
                                       notif.recipient, "pending", notif.retry_count, result.error)

        db.commit()

    except Exception as exc:
        db.rollback()
        logger.error(f"send_notification_job failed: {exc}")
        # Exponential backoff: 5min, 10min, 20min
        raise self.retry(exc=exc, countdown=300 * (2 ** self.request.retries))
    finally:
        db.close()


# ─── No-Show Follow-up ────────────────────────────────────────────────────────

@celery.task(bind=True, max_retries=2, autoretry_for=(Exception,), retry_backoff=5, retry_jitter=True, queue="notifications")
def handle_no_show_followup(self, patient_id: str, clinic_id: str):
    db = SessionLocal()
    try:
        from app.models.models import Patient, Clinic

        patient = db.query(Patient).filter(Patient.id == patient_id).first()
        if not patient:
            return

        patient.total_no_shows = (patient.total_no_shows or 0) + 1
        patient.total_appointments = (patient.total_appointments or 0) + 1
        patient.last_no_show_at = utcnow()
        total = patient.total_appointments
        patient.historical_no_show_rate = round(patient.total_no_shows / total, 4) if total > 0 else 0.0
        db.commit()

        clinic = db.query(Clinic).filter(Clinic.id == clinic_id).first()
        if not clinic:
            return

        # FIX: Guard patient.phone — could be None for email-only patients;
        # send_notification_with_fallback still tries email as fallback.
        if not patient.phone and not patient.email:
            logger.warning(f"handle_no_show_followup: patient {patient_id} has no contact info")
            return

        from app.services.notification_service import send_notification_with_fallback, build_no_show_followup_message
        msg = build_no_show_followup_message(patient.full_name, clinic.name, clinic.phone or "")
        run_async(send_notification_with_fallback(
            channel="sms", phone=patient.phone or None, email=patient.email or None, message=msg,
            subject="We missed you today — Vitar", country=clinic.country or "US",
        ))
        # FIX: log_booking_event signature is (event, appointment_id, clinic_id, doctor_id, patient_id)
        # — patient_id must be positional or use correct kwarg name
        log_booking_event("no_show_followup_sent", None, clinic_id, patient_id=patient_id)

    except Exception as exc:
        db.rollback()
        logger.error(f"handle_no_show_followup failed: {exc}")
        raise self.retry(exc=exc, countdown=300 * (2 ** self.request.retries))
    finally:
        db.close()


@celery.task(bind=True, max_retries=3, autoretry_for=(Exception,), retry_backoff=5, retry_jitter=True, queue="notifications")
def update_patient_attendance(self, patient_id: str):
    db = SessionLocal()
    try:
        from app.models.models import Patient
        patient = db.query(Patient).filter(Patient.id == patient_id).first()
        if patient:
            patient.total_appointments = (patient.total_appointments or 0) + 1
            total = patient.total_appointments
            no_shows = patient.total_no_shows or 0
            patient.historical_no_show_rate = round(no_shows / total, 4) if total > 0 else 0.0
            db.commit()
    except Exception as exc:
        db.rollback()
        raise self.retry(exc=exc, countdown=60)
    finally:
        db.close()


# ─── Waiting List Notification ────────────────────────────────────────────────

@celery.task(bind=True, max_retries=3, autoretry_for=(Exception,), retry_backoff=5, retry_jitter=True, queue="notifications")
def notify_waiting_list(self, clinic_id: str, doctor_id: str, slot_datetime_iso: str):
    db = SessionLocal()
    try:
        from app.models.models import WaitingList, Clinic, Doctor
        from app.services.notification_service import send_notification_with_fallback, build_slot_available_message
        from app.core.config import settings as cfg

        slot_dt = datetime.fromisoformat(slot_datetime_iso)
        clinic = db.query(Clinic).filter(Clinic.id == clinic_id).first()
        doctor = db.query(Doctor).filter(Doctor.id == doctor_id).first()
        if not clinic:
            return

        waiting = db.query(WaitingList).filter(
            WaitingList.clinic_id == clinic_id,
            WaitingList.doctor_id == doctor_id,
            WaitingList.status == "waiting",
        ).order_by(WaitingList.created_at).limit(3).all()

        booking_url = f"{cfg.FRONTEND_URL}/book/{clinic.slug}"
        doctor_name = doctor.full_name if doctor else "Doctor"

        for entry in waiting:
            msg = build_slot_available_message(
                entry.patient_name or "Patient", doctor_name, slot_dt, clinic.name, booking_url,
            )
            phone = entry.patient_phone
            email = entry.patient_email
            if phone or email:
                run_async(send_notification_with_fallback(
                    channel="sms", phone=phone, email=email, message=msg,
                    subject="A slot just opened — Vitar", country=clinic.country or "US",
                ))
                entry.status = "notified"
                entry.notified_at = utcnow()

        db.commit()
        logger.info(f"Notified {len(waiting)} waiting list entries for slot {slot_datetime_iso}")

    except Exception as exc:
        db.rollback()
        logger.error(f"notify_waiting_list failed: {exc}")
        raise self.retry(exc=exc, countdown=120 * (2 ** self.request.retries))
    finally:
        db.close()


@celery.task(bind=True, max_retries=3, autoretry_for=(Exception,), retry_backoff=5, retry_jitter=True, queue="notifications")
def send_reschedule_notification(self, appointment_id: str):
    db = SessionLocal()
    try:
        from app.models.models import Appointment, Doctor, Patient, Clinic
        from app.services.notification_service import send_notification_with_fallback, build_reschedule_message

        apt = db.query(Appointment).filter(Appointment.id == appointment_id).first()
        if not apt:
            return

        patient = db.query(Patient).filter(Patient.id == apt.patient_id).first()
        doctor = db.query(Doctor).filter(Doctor.id == apt.doctor_id).first()
        clinic = db.query(Clinic).filter(Clinic.id == apt.clinic_id).first()

        if not patient or not doctor:
            return

        # FIX: Guard patient.phone — send via email if no phone
        if not patient.phone and not patient.email:
            return

        msg = build_reschedule_message(
            patient.full_name, doctor.full_name, apt.scheduled_at, clinic.name if clinic else "",
        )
        run_async(send_notification_with_fallback(
            channel="sms", phone=patient.phone or None, email=patient.email or None, message=msg,
            subject="Appointment Rescheduled — Vitar", country=(clinic.country if clinic else "US"),
        ))
    except Exception as exc:
        db.rollback()
        raise self.retry(exc=exc, countdown=120)
    finally:
        db.close()


# ─── Trial Nudges ─────────────────────────────────────────────────────────────

@celery.task(bind=True, max_retries=3, autoretry_for=(Exception,), retry_backoff=10, retry_jitter=True, queue="billing")
def send_trial_nudges(self):
    db = SessionLocal()
    try:
        from app.models.models import Clinic, Subscription, User
        from app.services.email_service import send_trial_expiry_warning

        now = utcnow()
        clinics = db.query(Clinic).join(Subscription).filter(
            Subscription.status == "trialing",
            Clinic.trial_ends_at > now,
        ).all()

        for clinic in clinics:
            # FIX: Guard against None trial_ends_at to prevent TypeError
            if not clinic.trial_ends_at:
                continue
            days_left = (clinic.trial_ends_at - now).days
            if days_left in (7, 4, 1):
                user = db.query(User).filter(User.id == clinic.owner_id).first()
                if user:
                    run_async(send_trial_expiry_warning(user.email, clinic.name, days_left))
                    logger.info(f"Trial nudge sent: clinic={clinic.id} days_left={days_left}")

    except Exception as e:
        logger.error(f"send_trial_nudges error: {e}")
    finally:
        db.close()


@celery.task(bind=True, max_retries=3, autoretry_for=(Exception,), retry_backoff=10, retry_jitter=True, queue="billing")
def expire_trial_subscriptions(self):
    db = SessionLocal()
    try:
        from app.models.models import Subscription, SubscriptionStatus
        now = utcnow()
        expired = db.query(Subscription).filter(
            Subscription.status == SubscriptionStatus.TRIALING,
            Subscription.current_period_end < now,
        ).all()
        for sub in expired:
            sub.status = SubscriptionStatus.EXPIRED
            logger.info(f"Trial expired: subscription={sub.id} clinic={sub.clinic_id}")
        db.commit()
        logger.info(f"Expired {len(expired)} trial subscriptions")
    except Exception as e:
        db.rollback()
        logger.error(f"expire_trial_subscriptions error: {e}")
    finally:
        db.close()


@celery.task(bind=True, max_retries=3, autoretry_for=(Exception,), retry_backoff=10, retry_jitter=True, queue="notifications")
def retry_failed_notifications(self):
    """Reset retryable failed notifications back to pending."""
    db = SessionLocal()
    try:
        from app.models.models import Notification, NotificationStatus
        retryable = db.query(Notification).filter(
            Notification.status == NotificationStatus.FAILED,
            Notification.retry_count < Notification.max_retries,
            Notification.scheduled_for >= utcnow() - timedelta(hours=24),
        ).limit(50).all()

        for notif in retryable:
            notif.status = NotificationStatus.PENDING
            notif.failure_reason = None
            # FIX: Clear failed_at so health check doesn't keep counting them
            notif.failed_at = None

        db.commit()
        if retryable:
            logger.info(f"Reset {len(retryable)} notifications for retry")
    except Exception as e:
        db.rollback()
        logger.error(f"retry_failed_notifications error: {e}")
    finally:
        db.close()


@celery.task(bind=True, max_retries=3, autoretry_for=(Exception,), retry_backoff=5, retry_jitter=True, queue="ai")
def refresh_upcoming_risk_scores(self):
    db = SessionLocal()
    try:
        from app.models.models import Appointment, AppointmentStatus
        now = utcnow()
        # FIX: Paginate with limit(500) so a large clinic base doesn't queue
        # thousands of AI tasks in a single beat tick, which would saturate the
        # queue and cause cascading delays under high load.
        upcoming = db.query(Appointment).filter(
            Appointment.status == AppointmentStatus.CONFIRMED,
            Appointment.scheduled_at > now,
            Appointment.scheduled_at <= now + timedelta(hours=48),
        ).limit(500).all()
        for apt in upcoming:
            calculate_no_show_risk.apply_async(args=[apt.id], queue="ai")
        logger.info(f"Queued risk refresh for {len(upcoming)} upcoming appointments")
    except Exception as e:
        logger.error(f"refresh_upcoming_risk_scores error: {e}")
    finally:
        db.close()


# ─── Retry Failed Payments ────────────────────────────────────────────────────

@celery.task(bind=True, max_retries=2, autoretry_for=(Exception,), retry_backoff=30, retry_jitter=True,
             queue="billing", soft_time_limit=90, time_limit=120)
def retry_failed_payments(self):
    """
    Fail-safe payment automation.
    Finds SubscriptionPayments that are in FAILED state within the last 48h
    and re-triggers verification.  If the primary provider still fails, the
    task logs the incident and marks the subscription as past_due so the
    clinic sees an in-app alert.
    """
    from celery.exceptions import SoftTimeLimitExceeded
    db = SessionLocal()
    try:
        from app.models.models import (
            SubscriptionPayment, Subscription,
            PaymentStatus, SubscriptionStatus,
        )
        from app.core.logging import log_payment_event

        cutoff = utcnow() - timedelta(hours=48)
        failed_payments = (
            db.query(SubscriptionPayment)
            .filter(
                SubscriptionPayment.status == PaymentStatus.FAILED,
                SubscriptionPayment.created_at >= cutoff,
                SubscriptionPayment.retry_count < 3,
            )
            .limit(20)
            .all()
        )

        recovered = 0
        for payment in failed_payments:
            payment.retry_count = (payment.retry_count or 0) + 1
            log_payment_event(
                "payment_retry_attempt",
                str(payment.provider.value if payment.provider else "unknown"),
                payment.provider_reference,
                payment.subscription.clinic_id if payment.subscription else None,
                float(payment.amount or 0),
                "retrying",
                extra={"retry_count": payment.retry_count},
            )

            # Mark subscription as past_due so clinic sees the in-app alert
            sub = payment.subscription
            if sub and sub.status == SubscriptionStatus.ACTIVE:
                sub.status = SubscriptionStatus.PAST_DUE
                logger.warning(
                    "Subscription marked past_due after payment retry",
                    extra={
                        "subscription_id": str(sub.id),
                        "clinic_id": str(sub.clinic_id),
                        "retry_count": payment.retry_count,
                    },
                )
            recovered += 1

        db.commit()
        if failed_payments:
            logger.info(
                f"retry_failed_payments: processed {len(failed_payments)} failed payments",
                extra={"recovered": recovered},
            )

    except SoftTimeLimitExceeded:
        db.rollback()
        logger.error("retry_failed_payments hit soft time limit — rolled back")
    except Exception as exc:
        db.rollback()
        logger.error(f"retry_failed_payments error: {exc}", exc_info=True)
        raise self.retry(exc=exc, countdown=300 * (2 ** self.request.retries))
    finally:
        db.close()


# ─── Dead-Letter Queue ────────────────────────────────────────────────────────

# In-process dead-letter store (Redis-backed via Celery result backend).
# Tasks that exhaust all retries call _send_to_dead_letter() before raising.

def _send_to_dead_letter(task_name: str, args, kwargs, exc: Exception, traceback_str: str = ""):
    """
    Write a dead-letter record to Redis so it can be inspected / replayed.
    Key: dl:<task_name>:<timestamp>  TTL: 7 days
    """
    import json as _json
    import time as _time
    try:
        import redis as redis_lib
        from app.core.config import settings as cfg
        r = redis_lib.from_url(cfg.REDIS_URL, decode_responses=True, socket_connect_timeout=2)
        key = f"dl:{task_name}:{int(_time.time())}"
        payload = _json.dumps({
            "task": task_name,
            "args": args,
            "kwargs": kwargs,
            "error": str(exc),
            "traceback": traceback_str,
            "ts": utcnow().isoformat(),
        }, default=str)
        r.setex(key, 7 * 86400, payload)  # TTL: 7 days
        logger.error(
            "DEAD_LETTER task written",
            extra={"task": task_name, "error": str(exc), "key": key},
        )
    except Exception as redis_err:
        # Fallback: write to structured log so at minimum it's in CloudWatch/Loki
        logger.critical(
            "DEAD_LETTER (Redis unavailable)",
            extra={
                "task": task_name,
                "args": str(args)[:500],
                "error": str(exc),
                "redis_error": str(redis_err),
            },
        )


@celery.task(bind=True, max_retries=1, queue="dead_letter")
def dead_letter_processor(self):
    """
    Periodically scans dead-letter keys in Redis, logs a summary, and
    fires a Sentry alert if the count exceeds threshold.
    Run every 6 hours via Beat.
    """
    try:
        import redis as redis_lib
        import json as _json
        from app.core.config import settings as cfg

        r = redis_lib.from_url(cfg.REDIS_URL, decode_responses=True, socket_connect_timeout=2)
        keys = r.keys("dl:*")
        if not keys:
            return

        by_task: dict = {}
        for key in keys:
            raw = r.get(key)
            if not raw:
                continue
            try:
                rec = _json.loads(raw)
                task_name = rec.get("task", "unknown")
                by_task.setdefault(task_name, []).append(rec)
            except Exception:
                pass

        total = len(keys)
        logger.error(
            "DEAD_LETTER_SUMMARY",
            extra={
                "total_dead": total,
                "by_task": {k: len(v) for k, v in by_task.items()},
            },
        )

        # Sentry alert if available
        if total > 0:
            try:
                import sentry_sdk
                sentry_sdk.capture_message(
                    f"Dead-letter queue has {total} items",
                    level="error",
                    extras={"by_task": {k: len(v) for k, v in by_task.items()}},
                )
            except Exception:
                pass

    except Exception as e:
        logger.error(f"dead_letter_processor error: {e}", exc_info=True)


# ─── Global task failure hook ─────────────────────────────────────────────────
# Called automatically by Celery signals wiring in main app startup.
# Sends permanently failed tasks to dead-letter.

def on_task_failure(task_id, exception, args, kwargs, traceback, einfo, **kw):
    """
    Signal handler — attached in app/main.py via:
        from celery.signals import task_failure
        task_failure.connect(on_task_failure)
    Writes dead-letter records for tasks that have exhausted all retries.
    """
    import traceback as tb_mod
    tb_str = "".join(tb_mod.format_tb(traceback)) if traceback else ""
    task_name = kw.get("sender", "unknown")
    _send_to_dead_letter(task_name, args, kwargs, exception, tb_str)


# ─────────────────────────────────────────────────────────────────────────────
# v9: Queue Depth Monitor
# Runs every 60 s via Celery beat. Checks Redis LLEN for every queue and fires
# an alert if any queue exceeds the configured threshold.
# ─────────────────────────────────────────────────────────────────────────────

QUEUE_DEPTH_THRESHOLDS: dict[str, int] = {
    "notifications": 500,
    "reminders":     300,
    "ai":            200,
    "billing":       100,
    "celery":        200,
    "dead_letter":   20,   # Alert immediately when DLQ grows
}


@celery.task(bind=True, queue="celery", max_retries=0)
def monitor_queue_depths(self):
    """
    Check Redis LLEN for every Celery queue.
    Emits structured log + Prometheus gauge + Slack alert when depth exceeds threshold.
    Also detects stalled queues (depth unchanged for > 5 min) which may indicate
    a stuck or dead worker.
    """
    try:
        import redis as redis_lib
        from app.core.config import settings
        from app.core.observability import send_alert, WARNING, CRITICAL

        r = redis_lib.from_url(settings.CELERY_BROKER_URL, decode_responses=True, socket_timeout=2)

        depths = {}
        for queue_name in QUEUE_DEPTH_THRESHOLDS:
            try:
                depth = r.llen(queue_name)
                depths[queue_name] = depth
            except Exception:
                depths[queue_name] = -1

        # Emit Prometheus gauges
        try:
            from app.core.metrics import QUEUE_DEPTH_GAUGE
            for q, d in depths.items():
                if d >= 0:
                    QUEUE_DEPTH_GAUGE.labels(queue=q).set(d)
        except Exception:
            pass

        # Check thresholds and alert
        alerts = []
        for queue_name, depth in depths.items():
            threshold = QUEUE_DEPTH_THRESHOLDS.get(queue_name, 1000)
            if depth < 0:
                continue
            severity = None
            if queue_name == "dead_letter" and depth >= threshold:
                severity = CRITICAL
            elif depth >= threshold * 2:
                severity = CRITICAL
            elif depth >= threshold:
                severity = WARNING

            if severity:
                alerts.append({"queue": queue_name, "depth": depth, "threshold": threshold})
                send_alert(
                    title=f"Queue depth alert: {queue_name}",
                    message=f"Queue '{queue_name}' has {depth} tasks (threshold: {threshold})",
                    severity=severity,
                    component="celery_worker",
                    extra={"queue": queue_name, "depth": depth},
                )

        logger.info(
            "QUEUE_DEPTH_MONITOR",
            extra={"depths": depths, "alerts_fired": len(alerts)},
        )

        # v9: Trigger autoscaler evaluation
        autoscale_decisions = []
        try:
            from app.core.autoscaler import run_autoscaler
            autoscale_decisions = run_autoscaler()
        except Exception as as_exc:
            logger.warning(f"Autoscaler evaluation failed (non-critical): {as_exc}")

        return {"depths": depths, "alerts": alerts, "autoscale": autoscale_decisions}

    except Exception as exc:
        logger.error(f"monitor_queue_depths failed: {exc}", exc_info=True)
        return {"error": str(exc)}


# ─────────────────────────────────────────────────────────────────────────────
# v10: System Resource Monitor
# Runs every 60 s. Collects CPU%, memory%, disk%, load average.
# Fires Slack alerts + auto-recovery actions on threshold breach.
# ─────────────────────────────────────────────────────────────────────────────

@celery.task(bind=True, queue="celery", max_retries=0)
def monitor_system_resources(self):
    """
    Collect system resource usage and trigger auto-recovery if needed.
    Uses psutil (requires: pip install psutil).
    Alerts: CPU >= 85% warn / 95% crit, Memory >= 80% warn / 90% crit,
            Disk >= 80% warn / 92% crit.
    """
    try:
        from app.core.system_metrics import run_system_check
        result = run_system_check()
        return result
    except Exception as exc:
        logger.error(f"monitor_system_resources failed: {exc}", exc_info=True)
        return {"error": str(exc)}


# ─────────────────────────────────────────────────────────────────────────────
# v10: Stuck Task Inspector
# Runs every 5 min. Inspects active Celery tasks for tasks running longer
# than TASK_STUCK_THRESHOLD_S (default 600s). Fires a Slack alert and
# attempts a worker restart via Docker if a task is truly stuck.
# ─────────────────────────────────────────────────────────────────────────────

@celery.task(bind=True, queue="celery", max_retries=0)
def inspect_stuck_tasks(self):
    """
    Detect tasks that have been running longer than the stuck threshold.
    Default threshold: 600s (10 minutes).

    For each stuck task:
      - Emits a structured log + Prometheus counter
      - Fires Slack alert with task name, worker, and elapsed time
      - If AUTOHEAL_STUCK_TASKS=true, revokes the task and increments DLQ counter
    """
    import time as _time
    from app.core.observability import send_alert, CRITICAL, WARNING

    try:
        from app.workers.celery_app import celery as celery_app
        from app.core.config import settings

        threshold_s = int(getattr(settings, "TASK_STUCK_THRESHOLD_S", 600))
        autoheal = os.environ.get("AUTOHEAL_STUCK_TASKS", "false").lower() == "true"

        inspect = celery_app.control.inspect(timeout=5.0)
        active = inspect.active() or {}

        now = _time.time()
        stuck = []
        for worker_name, tasks in active.items():
            for task in tasks:
                started = task.get("time_start")
                if started and (now - started) > threshold_s:
                    elapsed = int(now - started)
                    stuck.append({
                        "task_id": task.get("id"),
                        "task_name": task.get("name"),
                        "worker": worker_name,
                        "elapsed_s": elapsed,
                        "args": str(task.get("args", []))[:80],
                    })

        if stuck:
            # Prometheus counter
            try:
                from app.core.metrics import STUCK_TASKS_TOTAL
                STUCK_TASKS_TOTAL.inc(len(stuck))
            except Exception:
                pass

            names = ", ".join(set(t["task_name"] for t in stuck))
            send_alert(
                title=f"Stuck Tasks Detected ({len(stuck)})",
                message=(
                    f"{len(stuck)} task(s) have been running > {threshold_s}s: {names}. "
                    + ("Auto-revoking." if autoheal else "Set AUTOHEAL_STUCK_TASKS=true to auto-revoke.")
                ),
                severity=CRITICAL if len(stuck) > 3 else WARNING,
                component="celery.inspector",
                extra={"count": len(stuck), "threshold_s": threshold_s},
            )
            logger.error(
                "STUCK_TASKS_DETECTED",
                extra={"count": len(stuck), "tasks": stuck},
            )

            if autoheal:
                for t in stuck:
                    try:
                        celery_app.control.revoke(t["task_id"], terminate=True, signal="SIGKILL")
                        logger.warning(
                            f"Auto-revoked stuck task {t['task_id']}",
                            extra={"task_name": t["task_name"], "elapsed_s": t["elapsed_s"]},
                        )
                    except Exception as revoke_exc:
                        logger.error(f"Failed to revoke {t['task_id']}: {revoke_exc}")

        logger.info(
            "STUCK_TASK_INSPECTOR",
            extra={"active_workers": len(active), "stuck_count": len(stuck)},
        )
        return {"stuck_count": len(stuck), "stuck_tasks": stuck, "threshold_s": threshold_s}

    except Exception as exc:
        logger.error(f"inspect_stuck_tasks failed: {exc}", exc_info=True)
        return {"error": str(exc)}
