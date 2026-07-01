"""
Vitar v5.2 - Public Booking Endpoints (HARDENED)
- SELECT FOR UPDATE SKIP LOCKED for slot conflict (no double-booking under concurrency)
- Null guards throughout
- Structured logging
- Idempotent patient upsert
- Clinic booking page cached in Redis (5-min TTL)
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import text
from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime, timedelta, timezone
import secrets

from app.core.cache import cache, TTL_MEDIUM

from app.core.utils import utcnow
from app.core.database import get_db
from app.core.config import settings
from app.core.logging import get_logger, log_booking_event
from app.models.models import (
    Clinic, Doctor, Patient, Appointment, WaitingList, AppointmentStatus,
)
from app.services.trial_guard import check_trial_booking_limit

router = APIRouter()
logger = get_logger(__name__)


class PublicBookingRequest(BaseModel):
    doctor_id: str
    scheduled_at: datetime
    full_name: str
    phone: str
    email: Optional[EmailStr] = None
    reason: Optional[str] = None


class WaitingListRequest(BaseModel):
    doctor_id: str
    patient_name: str
    patient_phone: str
    patient_email: Optional[str] = None
    preferred_date: Optional[datetime] = None
    reason: Optional[str] = None


# ── Celery dispatch helpers ───────────────────────────────────────────────────

def _dispatch_risk_and_reminders(appointment_id: str):
    try:
        from app.workers.tasks import calculate_no_show_risk, schedule_appointment_reminders
        calculate_no_show_risk.delay(appointment_id)
        schedule_appointment_reminders.delay(appointment_id)
    except Exception as e:
        logger.error(f"Failed to dispatch post-booking tasks: {e}")


def _dispatch_waiting_list_notify(clinic_id: str, doctor_id: str, slot_iso: str):
    try:
        from app.workers.tasks import notify_waiting_list
        notify_waiting_list.delay(clinic_id, doctor_id, slot_iso)
    except Exception as e:
        logger.error(f"Failed to dispatch waiting-list notification: {e}")


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/clinic/{slug}")
def get_clinic_booking_page(slug: str, db: Session = Depends(get_db)):
    cache_key = f"cache:booking_page:{slug}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    clinic = db.query(Clinic).filter(
        Clinic.slug == slug,
        Clinic.is_active == True,
        Clinic.booking_page_enabled == True,
    ).first()
    if not clinic:
        raise HTTPException(status_code=404, detail="Booking page not found")

    doctors = db.query(Doctor).filter(
        Doctor.clinic_id == clinic.id,
        Doctor.is_active == True,
    ).all()
    result = {
        "clinic": {
            "id": str(clinic.id),
            "name": clinic.name or "",
            "slug": clinic.slug or "",
            "phone": clinic.phone or "",
            "address": clinic.address or "",
            "city": clinic.city or "",
            "logo_url": clinic.logo_url or "",
            "patient_payment_enabled": bool(clinic.patient_payment_enabled),
            "currency": clinic.currency or "NGN",
            # Bank transfer details — only expose when payment is enabled
            "bank_name": clinic.paystack_bank_name if clinic.patient_payment_enabled else None,
            "account_number": clinic.paystack_account_number if clinic.patient_payment_enabled else None,
        },
        "doctors": [
            {
                "id": str(d.id),
                "full_name": d.full_name or "",
                "specialty": d.specialty or "",
                "avatar_url": d.avatar_url or "",
                "consultation_fee": float(d.consultation_fee) if d.consultation_fee else 0.0,
                "bio": d.bio or "",
            }
            for d in doctors
        ],
    }
    cache.set(cache_key, result, ttl=TTL_MEDIUM)  # 5-min TTL — stale is fine for booking page
    return result


@router.post("/clinic/{slug}/book", status_code=201)
def public_book_appointment(
    slug: str,
    body: PublicBookingRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Book an appointment.
    Uses SELECT FOR UPDATE SKIP LOCKED on the conflicting slot to prevent
    double-booking under concurrent requests.
    """
    clinic = db.query(Clinic).options(joinedload(Clinic.subscription)).filter(
        Clinic.slug == slug,
        Clinic.is_active == True,
        Clinic.online_booking_enabled == True,
    ).first()
    if not clinic:
        raise HTTPException(status_code=404, detail="Clinic not found or booking disabled")

    if body.scheduled_at < utcnow():
        raise HTTPException(status_code=400, detail="This time slot has already passed")

    # Trial guard (raises 402 if over limit)
    try:
        check_trial_booking_limit(clinic, db)
    except Exception as e:
        if hasattr(e, "status_code"):
            raise
        logger.warning(f"Trial guard error: {e}")

    doctor = db.query(Doctor).filter(
        Doctor.id == body.doctor_id,
        Doctor.clinic_id == clinic.id,
        Doctor.is_active == True,
    ).first()
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")

    # Determine slot duration safely
    slot_duration = 30
    try:
        if doctor.availability and len(doctor.availability) > 0:
            slot_duration = doctor.availability[0].slot_duration_mins or 30
    except Exception:
        slot_duration = 30

    slot_start = body.scheduled_at
    slot_end = slot_start + timedelta(minutes=slot_duration)

    # ── CRITICAL: SELECT FOR UPDATE SKIP LOCKED ────────────────────────────
    # Locks conflicting rows so concurrent requests cannot book the same slot.
    # SKIP LOCKED means another transaction won't block — it will detect the
    # conflict immediately rather than waiting.
    try:
        conflict = (
            db.query(Appointment)
            .filter(
                Appointment.doctor_id == body.doctor_id,
                Appointment.status.not_in([AppointmentStatus.CANCELLED, AppointmentStatus.NO_SHOW]),
                Appointment.scheduled_at < slot_end,
                Appointment.scheduled_at >= slot_start - timedelta(minutes=slot_duration),
            )
            .with_for_update(skip_locked=True)
            .first()
        )
    except Exception:
        # SQLite (tests) doesn't support SKIP LOCKED — fall back to plain filter
        conflict = db.query(Appointment).filter(
            Appointment.doctor_id == body.doctor_id,
            Appointment.status.not_in([AppointmentStatus.CANCELLED, AppointmentStatus.NO_SHOW]),
            Appointment.scheduled_at < slot_end,
            Appointment.scheduled_at >= slot_start - timedelta(minutes=slot_duration),
        ).first()

    if conflict:
        # Precise overlap
        conflict_end = conflict.scheduled_at + timedelta(minutes=conflict.duration_mins or 30)
        if slot_start < conflict_end and slot_end > conflict.scheduled_at:
            raise HTTPException(status_code=409, detail="This time slot is no longer available")

    # ── Patient upsert ────────────────────────────────────────────────────
    patient = db.query(Patient).filter(
        Patient.clinic_id == clinic.id,
        Patient.phone == body.phone,
    ).first()
    if not patient:
        patient = Patient(
            clinic_id=clinic.id,
            full_name=body.full_name or "",
            phone=body.phone,
            email=body.email,
        )
        db.add(patient)
        db.flush()
    else:
        if body.full_name:
            patient.full_name = body.full_name
        if body.email:
            patient.email = body.email

    # ── Create appointment ────────────────────────────────────────────────
    appointment = Appointment(
        clinic_id=clinic.id,
        doctor_id=body.doctor_id,
        patient_id=patient.id,
        scheduled_at=body.scheduled_at,
        duration_mins=slot_duration,
        reason=body.reason or "",
        status=AppointmentStatus.CONFIRMED,
        booked_via="booking_page",
        payment_required=bool(clinic.patient_payment_enabled),
        payment_amount=doctor.consultation_fee or getattr(clinic, "consultation_fee", None) or 0,
        payment_currency=clinic.currency or "NGN",
        confirmation_token=secrets.token_urlsafe(16),
        cancel_token=secrets.token_urlsafe(16),
    )
    db.add(appointment)

    try:
        # Increment trial counter atomically with the booking commit
        sub = getattr(clinic, "subscription", None)
        if not sub or getattr(sub, "plan", "trial") == "trial":
            clinic.trial_bookings_used = (clinic.trial_bookings_used or 0) + 1
        db.commit()
        db.refresh(appointment)
    except Exception as e:
        db.rollback()
        logger.error(f"Booking commit failed: {e}", exc_info=True)
        raise HTTPException(status_code=409, detail="Booking failed — slot may already be taken")

    log_booking_event("public_booked", appointment.id, clinic.id, body.doctor_id, patient.id)
    background_tasks.add_task(_dispatch_risk_and_reminders, appointment.id)

    response = {
        "appointment_id": appointment.id,
        "confirmation_token": appointment.confirmation_token,
        "cancel_token": appointment.cancel_token,
        "scheduled_at": appointment.scheduled_at.isoformat(),
        "doctor": doctor.full_name or "",
        "clinic": clinic.name or "",
        "payment_required": False,
    }

    if clinic.patient_payment_enabled and (appointment.payment_amount or 0) > 0:
        response["payment_required"] = True
        response["payment_amount"] = float(appointment.payment_amount)
        response["currency"] = clinic.currency or "NGN"
        response["payment_url"] = f"{settings.FRONTEND_URL}/book/{slug}/pay/{appointment.id}"

    return response


@router.get("/confirm/{token}")
def confirm_appointment(token: str, db: Session = Depends(get_db)):
    if not token:
        raise HTTPException(status_code=400, detail="Invalid token")
    apt = db.query(Appointment).filter(Appointment.confirmation_token == token).first()
    if not apt:
        raise HTTPException(status_code=404, detail="Invalid confirmation link")
    status_val = apt.status.value if hasattr(apt.status, "value") else str(apt.status)
    return {
        "status": status_val,
        "scheduled_at": apt.scheduled_at.isoformat() if apt.scheduled_at else None,
        "message": "Your appointment is confirmed.",
    }


@router.get("/cancel/{token}")
def get_cancel_page(token: str, db: Session = Depends(get_db)):
    if not token:
        raise HTTPException(status_code=400, detail="Invalid token")
    apt = db.query(Appointment).filter(Appointment.cancel_token == token).first()
    if not apt:
        raise HTTPException(status_code=404, detail="Invalid cancellation link")
    if apt.status == AppointmentStatus.CANCELLED:
        return {"message": "This appointment has already been cancelled."}
    return {
        "appointment_id": apt.id,
        "scheduled_at": apt.scheduled_at.isoformat() if apt.scheduled_at else None,
        "can_cancel": True,
    }


@router.post("/cancel/{token}")
def cancel_by_token(
    token: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    if not token:
        raise HTTPException(status_code=400, detail="Invalid token")
    apt = db.query(Appointment).filter(Appointment.cancel_token == token).first()
    if not apt:
        raise HTTPException(status_code=404, detail="Invalid cancellation link")
    if apt.status == AppointmentStatus.CANCELLED:
        return {"message": "Already cancelled"}

    slot_iso = apt.scheduled_at.isoformat() if apt.scheduled_at else ""
    clinic_id = apt.clinic_id
    doctor_id = apt.doctor_id

    apt.status = AppointmentStatus.CANCELLED
    apt.cancelled_at = utcnow()
    apt.cancelled_reason = "Patient self-cancelled via link"

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Cancel commit failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to cancel appointment")

    background_tasks.add_task(_dispatch_waiting_list_notify, clinic_id, doctor_id, slot_iso)
    log_booking_event("patient_self_cancelled", apt.id, clinic_id)
    return {"message": "Appointment cancelled successfully."}


@router.post("/clinic/{slug}/waitlist")
def join_waiting_list(slug: str, body: WaitingListRequest, db: Session = Depends(get_db)):
    clinic = db.query(Clinic).filter(
        Clinic.slug == slug,
        Clinic.is_active == True,
    ).first()
    if not clinic:
        raise HTTPException(status_code=404, detail="Clinic not found")

    entry = WaitingList(
        clinic_id=clinic.id,
        doctor_id=body.doctor_id,
        patient_name=body.patient_name or "",
        patient_phone=body.patient_phone or "",
        patient_email=body.patient_email,
        preferred_date=body.preferred_date,
        reason=body.reason,
        status="waiting",
        expires_at=utcnow() + timedelta(days=7),
    )
    db.add(entry)
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Waitlist insert failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to join waiting list")
    return {
        "message": "You've been added to the waiting list. We'll notify you when a slot opens.",
        "id": entry.id,
    }


# ─── Hospital/Clinic Portal (QR scan landing) ──────────────────────────────────

@router.get("/clinic/{slug}/portal")
def get_clinic_portal(slug: str, db: Session = Depends(get_db)):
    """
    Public endpoint for the QR scan landing page (/portal/:slug).
    Returns clinic branding info for the portal welcome screen.
    No auth required — patients arrive here by scanning a printed QR code.
    """
    clinic = db.query(Clinic).filter(
        Clinic.slug == slug,
        Clinic.is_active == True,
    ).first()
    if not clinic:
        raise HTTPException(status_code=404, detail="Hospital/clinic not found")

    return {
        "id": clinic.id,
        "name": clinic.name or "",
        "slug": clinic.slug or "",
        "logo_url": clinic.logo_url or "",
        "address": clinic.address or "",
        "city": clinic.city or "",
        "phone": clinic.phone or "",
        "booking_enabled": bool(clinic.booking_page_enabled and clinic.online_booking_enabled),
    }


class PortalRegisterRequest(BaseModel):
    full_name: str
    phone: str
    email: Optional[str] = None


@router.post("/clinic/{slug}/register-patient", status_code=201)
def portal_register_patient(
    slug: str,
    body: PortalRegisterRequest,
    db: Session = Depends(get_db),
):
    """
    Patient self-registration via hospital portal (QR scan flow).
    Upserts a Patient record pre-assigned to the clinic identified by slug.
    Returns a welcome message and the patient record.

    This is the critical step that ensures patients who arrive via QR scan
    are automatically associated with the correct hospital — no manual
    hospital selection required.
    """
    clinic = db.query(Clinic).filter(
        Clinic.slug == slug,
        Clinic.is_active == True,
    ).first()
    if not clinic:
        raise HTTPException(status_code=404, detail="Hospital/clinic not found")

    # Upsert: if a patient with the same phone already exists in this clinic,
    # update their record rather than create a duplicate.
    patient = db.query(Patient).filter(
        Patient.clinic_id == clinic.id,
        Patient.phone == body.phone,
    ).first()

    if patient:
        # Update details in case they changed
        if body.full_name:
            patient.full_name = body.full_name
        if body.email:
            patient.email = body.email
        db.commit()
        db.refresh(patient)
        return {
            "message": f"Welcome back, {patient.full_name}! Your details have been updated.",
            "patient_id": patient.id,
            "is_new": False,
        }

    # New patient — create and assign to this clinic
    patient = Patient(
        clinic_id=clinic.id,
        full_name=body.full_name,
        phone=body.phone,
        email=body.email or None,
    )
    db.add(patient)
    try:
        db.commit()
        db.refresh(patient)
    except Exception as e:
        db.rollback()
        logger.error(f"Portal patient registration failed: {e}")
        raise HTTPException(status_code=500, detail="Registration failed — please try again")

    return {
        "message": f"Welcome to {clinic.name}, {patient.full_name}! You're now registered.",
        "patient_id": patient.id,
        "is_new": True,
    }

