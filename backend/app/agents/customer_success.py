"""
Vitar AI Core — Customer Success Agent

Watches paying clinics for health signals (risk or opportunity) so
retention gets attention once a trial_started lead actually converts to
paid — the pipeline shouldn't stop mattering the moment a clinic starts
paying.

Support-flag signal: NOT implemented. The build spec asked to check
whether an existing support-ticket/flag system exists in this codebase
to source it from — there isn't one (no Ticket/Complaint/Issue model
anywhere in models.py), so this check is skipped entirely rather than
built against data that doesn't exist. Revisit once/if a support system
is added.
"""
import logging
import uuid
from datetime import timedelta
from typing import Optional

from app.agents.utils import is_ai_core_enabled, log_agent_run
from app.core.database import SessionLocal
from app.core.utils import utcnow
from app.models.models import (
    Appointment, Clinic, CustomerHealthSignal, HealthSignalStatus,
    HealthSignalType, Subscription, SubscriptionStatus, User,
)
from app.services.notifications import notify
from app.workers.celery_app import celery

logger = logging.getLogger("vitar.ai_core.customer_success")

NO_LOGIN_THRESHOLD_DAYS = 7
VOLUME_DROP_THRESHOLD = 0.5  # appointment count down >50% vs the prior week
# Below this, a week-over-week "drop" is noise, not a signal — a clinic
# doing 1 appointment last week and 0 this week isn't a real trend.
MIN_PRIOR_WEEK_APPOINTMENTS = 4


def _has_open_signal(db, clinic_id: str, signal_type: HealthSignalType) -> bool:
    return db.query(CustomerHealthSignal).filter(
        CustomerHealthSignal.clinic_id == clinic_id,
        CustomerHealthSignal.signal_type == signal_type,
        CustomerHealthSignal.status == HealthSignalStatus.OPEN,
    ).first() is not None


def _check_clinic(db, clinic: Clinic, now) -> Optional[str]:
    """Returns a detail string if a low_usage signal should be raised for
    this clinic, else None. Checks both no-login and volume-drop —
    either alone is enough to raise the (single) low_usage signal."""
    reasons = []

    owner = db.query(User).filter(User.id == clinic.owner_id).first()
    if owner and (not owner.last_login_at or owner.last_login_at < now - timedelta(days=NO_LOGIN_THRESHOLD_DAYS)):
        last_seen = owner.last_login_at.date().isoformat() if owner.last_login_at else "never"
        reasons.append(f"no login since {last_seen}")

    this_week_start = now - timedelta(days=7)
    prior_week_start = now - timedelta(days=14)

    this_week_count = db.query(Appointment).filter(
        Appointment.clinic_id == clinic.id,
        Appointment.created_at >= this_week_start,
        Appointment.created_at < now,
    ).count()
    prior_week_count = db.query(Appointment).filter(
        Appointment.clinic_id == clinic.id,
        Appointment.created_at >= prior_week_start,
        Appointment.created_at < this_week_start,
    ).count()

    if prior_week_count >= MIN_PRIOR_WEEK_APPOINTMENTS:
        drop = 1 - (this_week_count / prior_week_count)
        if drop > VOLUME_DROP_THRESHOLD:
            reasons.append(f"appointments down {drop:.0%} vs prior week ({this_week_count} vs {prior_week_count})")

    return "; ".join(reasons) if reasons else None


@celery.task(bind=True, queue="ai")
def scan_customer_health(self):
    if not is_ai_core_enabled():
        logger.info("scan_customer_health: AI_CORE_ENABLED=false — no-op")
        return

    with log_agent_run("customer_success", "scan_customer_health") as run:
        db = SessionLocal()
        created = 0
        try:
            paid_clinics = (
                db.query(Clinic)
                .join(Subscription, Subscription.clinic_id == Clinic.id)
                .filter(Subscription.status == SubscriptionStatus.ACTIVE)
                .all()
            )
            run.items_processed = len(paid_clinics)
            now = utcnow()

            for clinic in paid_clinics:
                detail = _check_clinic(db, clinic, now)
                if not detail:
                    continue
                if _has_open_signal(db, clinic.id, HealthSignalType.LOW_USAGE):
                    continue

                signal = CustomerHealthSignal(
                    id=str(uuid.uuid4()),
                    clinic_id=clinic.id,
                    signal_type=HealthSignalType.LOW_USAGE,
                    detail=detail,
                    status=HealthSignalStatus.OPEN,
                )
                db.add(signal)
                # Commit per-signal (not once at the end of the loop) before
                # notifying about it. notify() opens its own separate
                # session/transaction — if this ran on a flush() instead of
                # a real commit(), and a LATER clinic in this same loop
                # raised, the whole transaction (including this signal)
                # would roll back, but the notification pointing at its
                # related_id would already have fired for a row that never
                # actually ended up persisted.
                db.commit()
                created += 1

                notify(
                    event_type="health_signal",
                    agent_name="customer_success",
                    message=f"{clinic.name}: low_usage",
                    related_id=signal.id,
                    link_path="/admin/agents/customer-success",
                )
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

        run.items_created = created
