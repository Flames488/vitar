"""
Vitar v5 - Appointments Endpoints (HARDENED)
Fixes: double-booking overlap calc, background_tasks dispatch, structured logging
"""

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.orm import Session, joinedload
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta, timezone
import secrets

from app.core.utils import utcnow
from app.core.database import get_db
from app.core.database_async import get_async_db
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from app.core.security import get_current_clinic
from app.core.logging import get_logger, log_booking_event
from app.models.models import (
    Appointment, Doctor, Patient,
    AppointmentStatus, PaymentStatus,
)
from app.services.trial_guard import check_trial_booking_limit
from app.core.cache import cache, TTL_SHORT
from app.core.metrics import record_cache_hit, record_cache_miss

router = APIRouter()
logger = get_logger(__name__)


class AppointmentCreate(BaseModel):
    doctor_id: str
    patient_id: str
    scheduled_at: datetime
    duration_mins: int = 30
    reason: Optional[str] = None
    notes: Optional[str] = None
    booked_via: str = "manual"
    payment_required: bool = False
    payment_amount: Optional[float] = None


class AppointmentUpdate(BaseModel):
    status: Optional[str] = None
    notes: Optional[str] = None
    reason: Optional[str] = None
    scheduled_at: Optional[datetime] = None


class AppointmentReschedule(BaseModel):
    new_scheduled_at: datetime
    reason: Optional[str] = None


# ── FIX: Correct overlap detection using actual duration_mins ─────────────────

def _check_double_booking(db, doctor_id, scheduled_at, duration_mins, exclude_id=None):
    end_at = scheduled_at + timedelta(minutes=duration_mins)
    # Pull candidates in a 4-hour window around the slot
    q = db.query(Appointment).filter(
        Appointment.doctor_id == doctor_id,
        Appointment.status.not_in([AppointmentStatus.CANCELLED, AppointmentStatus.NO_SHOW]),
        Appointment.scheduled_at >= (scheduled_at - timedelta(hours=4)),
        Appointment.scheduled_at < (end_at + timedelta(hours=4)),
    )
    if exclude_id:
        q = q.filter(Appointment.id != exclude_id)

    try:
        candidates = q.with_for_update(nowait=True).all()
    except Exception:
        # Lock contention — another transaction is writing this slot right now.
        # Treat conservatively as a conflict to prevent double-booking.
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail={
                "code": "SLOT_CONFLICT",
                "message": "This time slot is currently being booked. Please try again.",
            },
        )

    for existing in candidates:
        existing_end = existing.scheduled_at + timedelta(minutes=existing.duration_mins or 30)
        # True overlap: new_start < existing_end AND new_end > existing_start
        if scheduled_at < existing_end and end_at > existing.scheduled_at:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "SLOT_CONFLICT",
                    "message": "Doctor already has an appointment in this time slot.",
                    "conflicting_appointment_id": existing.id,
                },
            )




async def _async_check_double_booking(db: AsyncSession, doctor_id, scheduled_at, duration_mins, exclude_id=None):
    """Async version of _check_double_booking for Wabizz endpoints."""
    from datetime import timedelta
    end_at = scheduled_at + timedelta(minutes=duration_mins)
    stmt = select(Appointment).where(
        and_(
            Appointment.doctor_id == doctor_id,
            Appointment.status.not_in([AppointmentStatus.CANCELLED, AppointmentStatus.NO_SHOW]),
            Appointment.scheduled_at >= (scheduled_at - timedelta(hours=4)),
            Appointment.scheduled_at < (end_at + timedelta(hours=4)),
        )
    )
    if exclude_id:
        stmt = stmt.where(Appointment.id != exclude_id)
    result = await db.execute(stmt)
    candidates = result.scalars().all()
    for existing in candidates:
        existing_end = existing.scheduled_at + timedelta(minutes=existing.duration_mins or 30)
        if scheduled_at < existing_end and end_at > existing.scheduled_at:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "SLOT_CONFLICT",
                    "message": "Doctor already has an appointment in this time slot.",
                    "conflicting_appointment_id": existing.id,
                },
            )

# ── FIX: Plain wrapper functions — never pass .delay to background_tasks ──────

def _dispatch_post_create(appointment_id: str):
    try:
        from app.workers.tasks import calculate_no_show_risk, schedule_appointment_reminders
        calculate_no_show_risk.delay(appointment_id)
        schedule_appointment_reminders.delay(appointment_id)
    except Exception as e:
        logger.error(f"Failed to dispatch post-create tasks: {e}")


def _dispatch_no_show(patient_id: str, clinic_id: str):
    try:
        from app.workers.tasks import handle_no_show_followup
        handle_no_show_followup.delay(patient_id, clinic_id)
    except Exception as e:
        logger.error(f"Failed no-show dispatch: {e}")


def _dispatch_attendance(patient_id: str):
    try:
        from app.workers.tasks import update_patient_attendance
        update_patient_attendance.delay(patient_id)
    except Exception as e:
        logger.error(f"Failed attendance dispatch: {e}")


def _dispatch_reschedule_notification(appointment_id: str):
    try:
        from app.workers.tasks import send_reschedule_notification
        send_reschedule_notification.delay(appointment_id)
    except Exception as e:
        logger.error(f"Failed reschedule notification dispatch: {e}")


def _dispatch_waiting_list(clinic_id: str, doctor_id: str, slot_iso: str):
    try:
        from app.workers.tasks import notify_waiting_list
        notify_waiting_list.delay(clinic_id, doctor_id, slot_iso)
    except Exception as e:
        logger.error(f"Failed waiting-list dispatch: {e}")


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/")
def list_appointments(
    status: Optional[str] = None,
    doctor_id: Optional[str] = None,
    patient_id: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    clinic=Depends(get_current_clinic),
    db: Session = Depends(get_db),
):
    q = db.query(Appointment).options(
        joinedload(Appointment.doctor),
        joinedload(Appointment.patient),
    ).filter(Appointment.clinic_id == clinic.id)

    if status:
        q = q.filter(Appointment.status == status)
    if doctor_id:
        q = q.filter(Appointment.doctor_id == doctor_id)
    if patient_id:
        q = q.filter(Appointment.patient_id == patient_id)
    if date_from:
        q = q.filter(Appointment.scheduled_at >= date_from)
    if date_to:
        q = q.filter(Appointment.scheduled_at <= date_to)

    # Cache default (unfiltered) first-page queries for 30s — hot path for dashboard
    use_cache = not any([status, doctor_id, patient_id, date_from, date_to]) and page == 1 and limit == 20
    cache_key = f"cache:apts:{clinic.id}:p1" if use_cache else None
    if use_cache:
        cached = cache.get(cache_key)
        if cached:
            record_cache_hit()
            return cached
        record_cache_miss()

    total = q.count()
    appointments = q.order_by(Appointment.scheduled_at.desc()).offset((page - 1) * limit).limit(limit).all()
    result = {"items": [_serialize(a) for a in appointments], "total": total, "page": page, "pages": (total + limit - 1) // limit}
    if use_cache:
        cache.set(cache_key, result, ttl=TTL_SHORT)
    return result


@router.post("/", status_code=201)
def create_appointment(
    body: AppointmentCreate,
    background_tasks: BackgroundTasks,
    clinic=Depends(get_current_clinic),
    db: Session = Depends(get_db),
):
    check_trial_booking_limit(clinic, db)

    doctor = db.query(Doctor).filter(Doctor.id == body.doctor_id, Doctor.clinic_id == clinic.id, Doctor.is_active == True).first()
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")

    patient = db.query(Patient).filter(Patient.id == body.patient_id, Patient.clinic_id == clinic.id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    if body.scheduled_at < utcnow():
        raise HTTPException(status_code=400, detail="Cannot book appointments in the past")

    try:
        _check_double_booking(db, body.doctor_id, body.scheduled_at, body.duration_mins)
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Lock contention during booking: {e}")
        raise HTTPException(status_code=409, detail={"code": "SLOT_BUSY", "message": "Slot temporarily unavailable, please try again"})

    if not clinic.subscription or getattr(clinic.subscription, 'plan', 'trial') == 'trial':
        clinic.trial_bookings_used = (clinic.trial_bookings_used or 0) + 1

    appointment = Appointment(
        clinic_id=clinic.id,
        doctor_id=body.doctor_id,
        patient_id=body.patient_id,
        scheduled_at=body.scheduled_at,
        duration_mins=body.duration_mins,
        reason=body.reason,
        notes=body.notes,
        booked_via=body.booked_via,
        status=AppointmentStatus.CONFIRMED,
        payment_required=body.payment_required,
        payment_amount=body.payment_amount or doctor.consultation_fee or 0,
        payment_currency=clinic.currency,
        confirmation_token=secrets.token_urlsafe(16),
        cancel_token=secrets.token_urlsafe(16),
    )
    db.add(appointment)
    db.commit()
    db.refresh(appointment)

    log_booking_event("created", appointment.id, clinic.id, body.doctor_id, body.patient_id)
    background_tasks.add_task(_dispatch_post_create, appointment.id)
    return _serialize(appointment)


@router.get("/{appointment_id}")
def get_appointment(appointment_id: str, clinic=Depends(get_current_clinic), db: Session = Depends(get_db)):
    apt = db.query(Appointment).options(
        joinedload(Appointment.doctor), joinedload(Appointment.patient), joinedload(Appointment.notifications)
    ).filter(Appointment.id == appointment_id, Appointment.clinic_id == clinic.id).first()
    if not apt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    return _serialize(apt, include_notifications=True)


@router.patch("/{appointment_id}")
def update_appointment(
    appointment_id: str, body: AppointmentUpdate, background_tasks: BackgroundTasks,
    clinic=Depends(get_current_clinic), db: Session = Depends(get_db),
):
    apt = db.query(Appointment).filter(Appointment.id == appointment_id, Appointment.clinic_id == clinic.id).first()
    if not apt:
        raise HTTPException(status_code=404, detail="Appointment not found")

    if body.status:
        old_status = str(apt.status)
        apt.status = body.status
        if body.status in ("no_show", AppointmentStatus.NO_SHOW.value):
            background_tasks.add_task(_dispatch_no_show, apt.patient_id, apt.clinic_id)
        elif body.status in ("completed", AppointmentStatus.COMPLETED.value):
            background_tasks.add_task(_dispatch_attendance, apt.patient_id)
        log_booking_event("status_changed", apt.id, clinic.id, extra={"old": old_status, "new": body.status})

    if body.notes is not None:
        apt.notes = body.notes
    if body.reason is not None:
        apt.reason = body.reason
    if body.scheduled_at:
        _check_double_booking(db, apt.doctor_id, body.scheduled_at, apt.duration_mins, exclude_id=apt.id)
        apt.scheduled_at = body.scheduled_at

    db.commit()
    db.refresh(apt)
    return _serialize(apt)


@router.post("/{appointment_id}/reschedule")
def reschedule_appointment(
    appointment_id: str, body: AppointmentReschedule, background_tasks: BackgroundTasks,
    clinic=Depends(get_current_clinic), db: Session = Depends(get_db),
):
    apt = db.query(Appointment).filter(Appointment.id == appointment_id, Appointment.clinic_id == clinic.id).first()
    if not apt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if apt.status in [AppointmentStatus.COMPLETED, AppointmentStatus.NO_SHOW]:
        raise HTTPException(status_code=400, detail="Cannot reschedule completed or no-show appointment")
    if body.new_scheduled_at < utcnow():
        raise HTTPException(status_code=400, detail="Cannot reschedule to a past time")

    _check_double_booking(db, apt.doctor_id, body.new_scheduled_at, apt.duration_mins, exclude_id=apt.id)
    apt.scheduled_at = body.new_scheduled_at
    apt.status = AppointmentStatus.CONFIRMED
    apt.cancelled_reason = body.reason
    db.commit()
    db.refresh(apt)

    background_tasks.add_task(_dispatch_reschedule_notification, apt.id)
    log_booking_event("rescheduled", apt.id, clinic.id)
    return _serialize(apt)


@router.delete("/{appointment_id}")
def cancel_appointment(
    appointment_id: str, background_tasks: BackgroundTasks,
    reason: Optional[str] = None,
    clinic=Depends(get_current_clinic), db: Session = Depends(get_db),
):
    apt = db.query(Appointment).filter(Appointment.id == appointment_id, Appointment.clinic_id == clinic.id).first()
    if not apt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if apt.status == AppointmentStatus.CANCELLED:
        raise HTTPException(status_code=400, detail="Already cancelled")

    slot_iso = apt.scheduled_at.isoformat()
    apt.status = AppointmentStatus.CANCELLED
    apt.cancelled_reason = reason
    apt.cancelled_at = utcnow()
    db.commit()

    background_tasks.add_task(_dispatch_waiting_list, apt.clinic_id, apt.doctor_id, slot_iso)
    log_booking_event("cancelled", apt.id, clinic.id)
    return {"message": "Appointment cancelled", "id": appointment_id}


# ── Serializer ────────────────────────────────────────────────────────────────

def _serialize(apt: Appointment, include_notifications: bool = False) -> dict:
    data = {
        "id": apt.id,
        "clinic_id": apt.clinic_id,
        # FIX: include doctor_id / patient_id at top level — the Wabizz
        # Appointment TypeScript type (hospital/types.ts) expects these as
        # scalar fields, not only nested inside doctor/patient objects.
        "doctor_id": apt.doctor_id,
        "patient_id": apt.patient_id,
        "scheduled_at": apt.scheduled_at.isoformat() if apt.scheduled_at else None,
        "duration_mins": apt.duration_mins,
        "status": apt.status.value if hasattr(apt.status, "value") else apt.status,
        "reason": apt.reason,
        "notes": apt.notes,
        "booked_via": apt.booked_via,
        "payment_required": apt.payment_required,
        "payment_status": apt.payment_status.value if apt.payment_status and hasattr(apt.payment_status, "value") else apt.payment_status,
        "payment_amount": float(apt.payment_amount) if apt.payment_amount else 0,
        "no_show_risk_score": apt.no_show_risk_score,
        "risk_factors": apt.risk_factors,
        "reminder_count": apt.reminder_count,
        "confirmation_token": apt.confirmation_token,
        "cancel_token": apt.cancel_token,
        "created_at": apt.created_at.isoformat() if apt.created_at else None,
        "doctor": {"id": apt.doctor.id, "full_name": apt.doctor.full_name, "specialty": apt.doctor.specialty} if apt.doctor else None,
        "patient": {"id": apt.patient.id, "full_name": apt.patient.full_name, "phone": apt.patient.phone, "email": apt.patient.email, "no_show_rate": apt.patient.historical_no_show_rate} if apt.patient else None,
    }
    if include_notifications and apt.notifications:
        data["notifications"] = [
            {
                "id": n.id,
                "channel": n.channel.value if hasattr(n.channel, "value") else n.channel,
                "type": n.notification_type,
                "status": n.status.value if hasattr(n.status, "value") else n.status,
                "scheduled_for": n.scheduled_for.isoformat(),
                "sent_at": n.sent_at.isoformat() if n.sent_at else None,
                "retry_count": n.retry_count,
                "failure_reason": n.failure_reason,
            }
            for n in apt.notifications
        ]
    return data


# ── Wabizz machine-to-machine endpoints ───────────────────────────────────────
# These parallel the browser-auth endpoints but accept X-API-Key instead.
# Import is at top of file, adding dependency here:

from app.middleware.api_key_auth import verify_api_key as _verify_api_key


class WabizzAppointmentCreate(BaseModel):
    doctor_id: str
    patient_id: str
    scheduled_at: datetime
    duration_mins: int = 30
    reason: Optional[str] = None
    booked_via: str = "wabizz_whatsapp"
    payment_required: bool = False
    payment_amount: Optional[float] = None


@router.post(
    "/wabizz",
    status_code=201,
    dependencies=[Depends(_verify_api_key)],
    summary="Book appointment (Wabizz integration)",
)
async def wabizz_book_appointment(
    body: WabizzAppointmentCreate,
    db: AsyncSession = Depends(get_async_db),
):
    """
    Books an appointment via the Wabizz WhatsApp flow.
    Uses async SQLAlchemy for non-blocking I/O — critical for peak load.
    """
    from app.models.models import Doctor, Patient

    dr_result = await db.execute(
        select(Doctor).where(and_(Doctor.id == body.doctor_id, Doctor.is_active == True))  # noqa: E712
    )
    doctor = dr_result.scalar_one_or_none()
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")

    pt_result = await db.execute(
        select(Patient).where(and_(Patient.id == body.patient_id, Patient.is_active == True))  # noqa: E712
    )
    patient = pt_result.scalar_one_or_none()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    await _async_check_double_booking(db, body.doctor_id, body.scheduled_at, body.duration_mins)

    apt = Appointment(
        doctor_id=body.doctor_id,
        patient_id=body.patient_id,
        clinic_id=doctor.clinic_id,
        scheduled_at=body.scheduled_at,
        duration_mins=body.duration_mins,
        reason=body.reason,
        booked_via=body.booked_via,
        payment_required=body.payment_required,
        payment_amount=body.payment_amount,
        status=AppointmentStatus.CONFIRMED,
    )
    db.add(apt)
    await db.commit()

    # FIX: db.refresh() only reloads scalar columns — relationships (doctor, patient)
    # remain unloaded (None) after an async commit.  Re-fetch with joinedload so
    # _serialize() can populate the nested doctor/patient objects and the top-level
    # doctor_id / patient_id fields are present in the response.
    refreshed = await db.execute(
        select(Appointment)
        .options(joinedload(Appointment.doctor), joinedload(Appointment.patient))
        .where(Appointment.id == apt.id)
    )
    apt = refreshed.scalar_one()
    log_booking_event("booked_via_wabizz", apt.id, str(doctor.clinic_id))
    return _serialize(apt)


@router.get(
    "/wabizz/{appointment_id}",
    dependencies=[Depends(_verify_api_key)],
    summary="Get appointment (Wabizz integration)",
)
async def wabizz_get_appointment(
    appointment_id: str,
    db: AsyncSession = Depends(get_async_db),
):
    """Retrieves a single appointment by ID. Called by vitar-client.getAppointment(). Uses async SQLAlchemy."""
    # FIX: plain select() uses lazy-loading — in async sessions that raises
    # MissingGreenlet (or silently returns None).  Always use joinedload for
    # relationship columns accessed in _serialize().
    result = await db.execute(
        select(Appointment)
        .options(joinedload(Appointment.doctor), joinedload(Appointment.patient))
        .where(Appointment.id == appointment_id)
    )
    apt = result.scalar_one_or_none()
    if not apt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    return _serialize(apt)


@router.patch(
    "/wabizz/{appointment_id}",
    dependencies=[Depends(_verify_api_key)],
    summary="Update appointment status (Wabizz integration)",
)
async def wabizz_update_appointment(
    appointment_id: str,
    body: AppointmentUpdate,
    db: AsyncSession = Depends(get_async_db),
):
    """
    Updates appointment status or notes. Used by Wabizz to cancel appointments.
    Called by vitar-client.cancelAppointment() with { status: 'cancelled' }. Uses async SQLAlchemy.
    """
    # FIX: use joinedload so _serialize() can access apt.doctor / apt.patient.
    result = await db.execute(
        select(Appointment)
        .options(joinedload(Appointment.doctor), joinedload(Appointment.patient))
        .where(Appointment.id == appointment_id)
    )
    apt = result.scalar_one_or_none()
    if not apt:
        raise HTTPException(status_code=404, detail="Appointment not found")

    if body.status:
        try:
            apt.status = AppointmentStatus(body.status)
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Invalid status: {body.status}")

    if body.notes is not None:
        apt.notes = body.notes

    if body.scheduled_at:
        await _async_check_double_booking(db, apt.doctor_id, body.scheduled_at, apt.duration_mins, exclude_id=apt.id)
        apt.scheduled_at = body.scheduled_at

    await db.commit()

    # FIX: re-fetch after commit with joinedload — db.refresh() does not reload
    # relationships in async sessions, leaving apt.doctor / apt.patient as None.
    refreshed = await db.execute(
        select(Appointment)
        .options(joinedload(Appointment.doctor), joinedload(Appointment.patient))
        .where(Appointment.id == appointment_id)
    )
    apt = refreshed.scalar_one()
    return _serialize(apt)
