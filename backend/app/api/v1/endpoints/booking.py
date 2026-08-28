"""
Vitar v5.2 - Public Booking Endpoints (HARDENED)
- SELECT FOR UPDATE SKIP LOCKED for slot conflict (no double-booking under concurrency)
- Null guards throughout
- Structured logging
- Idempotent patient upsert
- Clinic booking page cached in Redis (5-min TTL)
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import text, or_
from sqlalchemy.exc import IntegrityError
from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional
from datetime import datetime, timedelta, timezone
import secrets
import uuid

from app.core.cache import cache, TTL_MEDIUM, booking_page_key

from app.core.utils import utcnow
from app.core.database import get_db
from app.core.config import settings
from app.core.logging import get_logger, log_booking_event
from app.models.models import (
    Clinic, Doctor, Patient, Appointment, WaitingList, AppointmentStatus, PaymentStatus,
)
from app.services.trial_guard import check_trial_booking_limit, has_doctor_contact_access
from app.services.hospital_payments import hospital_payments, clinic_has_payout_destination

router = APIRouter()
logger = get_logger(__name__)


class PublicBookingRequest(BaseModel):
    doctor_id: str
    scheduled_at: datetime
    full_name: str
    phone: str
    email: Optional[EmailStr] = None
    reason: Optional[str] = None
    turnstile_token: str = ""

    @field_validator("scheduled_at")
    @classmethod
    def _normalize_scheduled_at(cls, v: datetime) -> datetime:
        # Frontend may send a timezone-aware ISO string (e.g. JS's
        # toISOString() has a 'Z' suffix). Normalize to naive UTC to match
        # utcnow() and DB storage — avoids "can't compare offset-naive and
        # offset-aware datetimes" when checked against utcnow() downstream.
        if v.tzinfo is not None:
            return v.astimezone(timezone.utc).replace(tzinfo=None)
        return v

    @field_validator("email", mode="before")
    @classmethod
    def blank_email_to_none(cls, v):
        # Frontend sends "" when the optional email field is left blank.
        # EmailStr rejects "" as an invalid address, so normalize it to None
        # before validation runs.
        return v or None


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


def _dispatch_new_booking_notify(appointment_id: str):
    try:
        from app.workers.push_tasks import notify_new_booking
        notify_new_booking.delay(appointment_id)
    except Exception as e:
        logger.error(f"Failed to dispatch new-booking notification: {e}")


# ── Endpoints ─────────────────────────────────────────────────────────────────

def _whatsapp_link(phone: Optional[str]) -> Optional[str]:
    """Builds a wa.me click-to-chat link from a phone number, or None if the
    number doesn't have enough digits to be usable."""
    if not phone:
        return None
    digits = "".join(c for c in phone if c.isdigit())
    if len(digits) < 8:
        return None
    return f"https://wa.me/{digits}"


def _call_link(phone: Optional[str]) -> Optional[str]:
    """Builds a tel: link for the 'Call Doctor' button, or None if the
    number doesn't have enough digits to be usable."""
    if not phone:
        return None
    digits = "".join(c for c in phone if c.isdigit())
    if len(digits) < 8:
        return None
    return f"tel:{phone.strip()}"


@router.get("/clinic/{slug}")
def get_clinic_booking_page(slug: str, db: Session = Depends(get_db)):
    cache_key = booking_page_key(slug)
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

    # Only advertise "payment required" when the clinic can actually be paid
    # out. Collecting a patient's money with no verified payout account on
    # file means Vitar holds funds it has no automated way to forward — a
    # trust and regulatory hazard. Mirrors the same gate in public_book_appointment.
    payment_collectable = bool(clinic.patient_payment_enabled) and clinic_has_payout_destination(db, clinic.id)

    # Doctor Contact (WhatsApp/Call) no longer appears here — moved to
    # post-booking only (see get_appointment_doctor_contact below), gated
    # by has_doctor_contact_access() + appointment ownership. Do not add
    # doctor_details/contact fields back to this pre-booking response.
    result = {
        "clinic": {
            "id": str(clinic.id),
            "name": clinic.name or "",
            "slug": clinic.slug or "",
            "phone": clinic.phone or "",
            "address": clinic.address or "",
            "city": clinic.city or "",
            "logo_url": clinic.logo_url or "",
            "patient_payment_enabled": payment_collectable,
            "currency": clinic.currency or "NGN",
            # Bank transfer details — only expose when payment is enabled
            "bank_name": clinic.paystack_bank_name if payment_collectable else None,
            "account_number": clinic.paystack_account_number if payment_collectable else None,
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


@router.get("/clinic/{slug}/doctors/{doctor_id}/available-slots")
def get_public_available_slots(slug: str, doctor_id: str, date: str, db: Session = Depends(get_db)):
    """
    Public equivalent of GET /doctors/{id}/available-slots — patients booking
    from the public page have no clinic login token, so this route only
    requires the clinic slug + doctor id to line up (no auth dependency).
    Same slot-generation logic as the staff-facing endpoint in doctors.py.
    """
    from app.models.models import DoctorAvailability

    clinic = db.query(Clinic).filter(Clinic.slug == slug, Clinic.is_active == True).first()
    if not clinic:
        raise HTTPException(status_code=404, detail="Booking page not found")

    doctor = db.query(Doctor).filter(
        Doctor.id == doctor_id,
        Doctor.clinic_id == clinic.id,
        Doctor.is_active == True,
    ).first()
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")

    try:
        target = datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=422, detail="date must be YYYY-MM-DD")
    dow = target.weekday()

    avail = db.query(DoctorAvailability).filter(
        DoctorAvailability.doctor_id == doctor_id,
        DoctorAvailability.day_of_week == dow,
        DoctorAvailability.is_available == True,
    ).first()
    if not avail:
        return {"slots": [], "date": date}

    start_h, start_m = map(int, avail.start_time.split(":"))
    end_h, end_m = map(int, avail.end_time.split(":"))
    slot_duration = avail.slot_duration_mins or 30

    current = target.replace(hour=start_h, minute=start_m, second=0, microsecond=0)
    end_dt = target.replace(hour=end_h, minute=end_m, second=0, microsecond=0)

    # FIX: exact-timestamp matching missed overlaps from longer appointments
    # (a 60-min appointment at 9:00 left the 9:30 slot showing available, which
    # then 409'd at actual booking time) and never excluded stale
    # AWAITING_PAYMENT holds, mirroring _check_double_booking's real logic.
    day_start = target
    day_end = target + timedelta(days=1)
    payment_cutoff = utcnow() - timedelta(minutes=settings.AWAITING_PAYMENT_TIMEOUT_MINUTES)
    booked = db.query(Appointment.scheduled_at, Appointment.duration_mins).filter(
        Appointment.doctor_id == doctor_id,
        Appointment.status.not_in([AppointmentStatus.CANCELLED, AppointmentStatus.NO_SHOW]),
        or_(
            Appointment.status != AppointmentStatus.AWAITING_PAYMENT,
            Appointment.created_at >= payment_cutoff,
        ),
        Appointment.scheduled_at >= day_start - timedelta(hours=8),
        Appointment.scheduled_at < day_end + timedelta(hours=8),
    ).all()
    booked_intervals = [
        (b.scheduled_at, b.scheduled_at + timedelta(minutes=b.duration_mins or 30))
        for b in booked
    ]

    # FIX: avail.start_time/end_time are clinic-entered WAT wall-clock (e.g.
    # "09:00" means 9am Lagos time), but booked_intervals/now come from
    # Appointment.scheduled_at and utcnow(), both true UTC. Comparing `current`
    # directly against them (as this loop used to) was off by exactly 1 hour —
    # same class of bug already fixed in doctors.py's slot endpoints — so a
    # doctor's real 9am-WAT booking (stored as 08:00 UTC) wouldn't overlap a
    # slot literally named "09:00", and a slot already an hour past could
    # still show as free.
    WAT_OFFSET = timedelta(hours=1)
    slots = []
    now = utcnow()
    while current < end_dt:
        slot_end = current + timedelta(minutes=slot_duration)
        current_utc = current - WAT_OFFSET
        slot_end_utc = slot_end - WAT_OFFSET
        overlaps = any(current_utc < b_end and slot_end_utc > b_start for b_start, b_end in booked_intervals)
        # status distinguishes *why* a slot can't be booked — "available" alone
        # conflated "someone else booked this" with "this time already passed
        # today", which is what let the calendar mislabel a plain past slot as
        # if it were taken. Kept "available" too for any existing consumer.
        if overlaps:
            status = "booked"
        elif current_utc <= now:
            status = "past"
        else:
            status = "free"
        slots.append({
            "time": current.strftime("%H:%M"),
            "datetime": current_utc.isoformat(),
            "available": not overlaps and current_utc > now,
            "status": status,
        })
        current += timedelta(minutes=slot_duration)

    return {"slots": slots, "date": date, "doctor_id": doctor_id}


@router.post("/clinic/{slug}/book", status_code=201)
async def public_book_appointment(
    slug: str,
    body: PublicBookingRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Book an appointment.
    Uses SELECT FOR UPDATE SKIP LOCKED on the conflicting slot to prevent
    double-booking under concurrent requests.
    """
    from app.services.turnstile import verify_turnstile

    client_ip = request.headers.get("X-Real-IP", "").strip() or (request.client.host if request.client else None)
    if not await verify_turnstile(body.turnstile_token, client_ip):
        raise HTTPException(status_code=400, detail="Bot verification failed. Please refresh and try again.")

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

    # Determine slot duration for the day actually being booked.
    # FIX: doctor.availability[0] picked whichever DoctorAvailability row the
    # relationship happened to load first, which may belong to a different
    # weekday than the one being booked (a doctor can have a different
    # slot_duration_mins per day). That undersized/oversized both the conflict
    # window above and the appointment's own duration_mins vs. what the
    # patient actually saw on the day-specific available-slots endpoint.
    # scheduled_at is naive UTC at this point (see _normalize_scheduled_at) —
    # shift back to WAT wall-clock before deriving the weekday, since
    # DoctorAvailability.day_of_week is keyed to clinic-local (WAT) days.
    slot_duration = 30
    try:
        from app.models.models import DoctorAvailability
        wat_dow = (body.scheduled_at + timedelta(hours=1)).weekday()
        avail_for_day = db.query(DoctorAvailability).filter(
            DoctorAvailability.doctor_id == doctor.id,
            DoctorAvailability.day_of_week == wat_dow,
        ).first()
        if avail_for_day and avail_for_day.slot_duration_mins:
            slot_duration = avail_for_day.slot_duration_mins
    except Exception:
        slot_duration = 30

    slot_start = body.scheduled_at
    slot_end = slot_start + timedelta(minutes=slot_duration)

    # ── CRITICAL: SELECT FOR UPDATE SKIP LOCKED ────────────────────────────
    # Locks conflicting rows so concurrent requests cannot book the same slot.
    # SKIP LOCKED means another transaction won't block — it will detect the
    # conflict immediately rather than waiting.
    #
    # A stale AWAITING_PAYMENT appointment (checkout started but abandoned)
    # stops blocking the slot once past AWAITING_PAYMENT_TIMEOUT_MINUTES —
    # otherwise an abandoned checkout occupies that slot forever, and enough
    # of them make a doctor look booked solid on every date.
    payment_cutoff = utcnow() - timedelta(minutes=settings.AWAITING_PAYMENT_TIMEOUT_MINUTES)
    not_stale_awaiting_payment = or_(
        Appointment.status != AppointmentStatus.AWAITING_PAYMENT,
        Appointment.created_at >= payment_cutoff,
    )
    try:
        conflict = (
            db.query(Appointment)
            .filter(
                Appointment.doctor_id == body.doctor_id,
                Appointment.status.not_in([AppointmentStatus.CANCELLED, AppointmentStatus.NO_SHOW]),
                not_stale_awaiting_payment,
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
            not_stale_awaiting_payment,
            Appointment.scheduled_at < slot_end,
            Appointment.scheduled_at >= slot_start - timedelta(minutes=slot_duration),
        ).first()

    if conflict:
        # Precise overlap
        conflict_end = conflict.scheduled_at + timedelta(minutes=conflict.duration_mins or 30)
        if slot_start < conflict_end and slot_end > conflict.scheduled_at:
            raise HTTPException(status_code=409, detail="This time slot is no longer available")

    # ── Patient upsert (atomic — single round trip) ───────────────────────
    # Previously this was a SELECT, then a conditional INSERT + flush(),
    # committed later together with the appointment insert. That left a
    # window where a flushed-but-uncommitted patient row could be lost
    # (e.g. a pooler-level reconnect under Supabase's transaction pooler)
    # before the appointment insert that references it ran — causing
    # "insert or update on table appointments violates foreign key
    # constraint appointments_patient_id_fkey". Doing it as one INSERT ...
    # ON CONFLICT ... RETURNING removes that window entirely: the patient
    # row and its id are guaranteed to exist before we ever build the
    # Appointment object.
    patient_row = db.execute(
        text("""
            INSERT INTO patients (id, clinic_id, full_name, phone, email)
            VALUES (:id, :clinic_id, :full_name, :phone, :email)
            ON CONFLICT (clinic_id, phone) DO UPDATE
                SET full_name = COALESCE(NULLIF(EXCLUDED.full_name, ''), patients.full_name),
                    email = COALESCE(EXCLUDED.email, patients.email)
            RETURNING id
        """),
        {
            "id": str(uuid.uuid4()),
            "clinic_id": clinic.id,
            "full_name": body.full_name or "",
            "phone": body.phone,
            "email": body.email,
        },
    ).first()
    patient_id = patient_row.id

    # Commit the patient row on its own, right now. Under PgBouncer/pooler
    # instability, a still-open (uncommitted) transaction can occasionally
    # end up split across two different backend connections between one
    # statement and the next, making an uncommitted row invisible to a
    # later statement in the "same" session — which is exactly how this
    # appointment insert was hitting appointments_patient_id_fkey even
    # though the row had just been inserted moments earlier. Committing
    # here guarantees the patient row is durable and visible to literally
    # any connection before we ever build the Appointment that references it.
    db.commit()

    payment_amount = doctor.consultation_fee or getattr(clinic, "consultation_fee", None) or 0
    # Gate collection on a working payout destination — never take a patient's
    # money the clinic can't be automatically paid out (see
    # clinic_has_payout_destination). A clinic with fees set but no verified
    # bank account simply books the appointment for free until they finish
    # payout setup.
    payment_required = bool(
        clinic.patient_payment_enabled
        and payment_amount
        and payment_amount > 0
        and clinic_has_payout_destination(db, clinic.id)
    )
    payment_reference = f"VITAR-APT-{secrets.token_urlsafe(12).replace('_', '').replace('-', '').upper()}"

    # ── Create appointment ────────────────────────────────────────────────
    appointment = Appointment(
        clinic_id=clinic.id,
        doctor_id=body.doctor_id,
        patient_id=patient_id,
        scheduled_at=body.scheduled_at,
        duration_mins=slot_duration,
        reason=body.reason or "",
        status=AppointmentStatus.AWAITING_PAYMENT if payment_required else AppointmentStatus.APPROVED,
        booked_via="booking_page",
        payment_required=payment_required,
        payment_status=PaymentStatus.PENDING if payment_required else PaymentStatus.UNPAID,
        payment_amount=payment_amount,
        payment_currency=clinic.currency or "NGN",
        payment_provider_ref=payment_reference if payment_required else None,
        confirmation_token=secrets.token_urlsafe(16),
        cancel_token=secrets.token_urlsafe(16),
    )
    db.add(appointment)

    try:
        sub = getattr(clinic, "subscription", None)
        if not sub or getattr(sub, "plan", "trial") == "trial":
            # Atomic, race-free conditional increment. A plain Python
            # read-modify-write here (clinic.trial_bookings_used += 1) let two
            # concurrent requests both read the same pre-increment count and
            # both pass check_trial_booking_limit() above, letting a trial
            # clinic exceed TRIAL_MAX_BOOKINGS. A single UPDATE ... WHERE ...
            # is atomic in Postgres regardless of concurrent callers.
            row = db.execute(
                text("""
                    UPDATE clinics
                    SET trial_bookings_used = COALESCE(trial_bookings_used, 0) + 1
                    WHERE id = :id AND COALESCE(trial_bookings_used, 0) < :limit
                    RETURNING trial_bookings_used
                """),
                {"id": clinic.id, "limit": settings.TRIAL_MAX_BOOKINGS},
            ).first()
            if row is None:
                db.rollback()
                raise HTTPException(
                    status_code=402,
                    detail={
                        "code": "TRIAL_BOOKING_LIMIT",
                        "message": f"You've used all {settings.TRIAL_MAX_BOOKINGS} free trial bookings. Upgrade to continue.",
                        "limit": settings.TRIAL_MAX_BOOKINGS,
                        "upgrade_url": "/settings/billing",
                    },
                )
        db.commit()
        db.refresh(appointment)

        # Close the loop on the waiting list: if this patient/doctor pair
        # has an open waitlist entry (joined before this slot existed, or
        # notified once one opened up), link it to the appointment they
        # just actually booked. Matched on phone, not patient_id — the
        # waitlist supports non-registered patients where patient_id is
        # never set (see WaitingList's own column comment). Best-effort:
        # this must never break a successful booking if it fails.
        try:
            from app.models.models import WaitingList
            waitlist_entry = (
                db.query(WaitingList)
                .filter(
                    WaitingList.clinic_id == clinic.id,
                    WaitingList.doctor_id == body.doctor_id,
                    WaitingList.patient_phone == body.phone,
                    WaitingList.status.in_(["waiting", "notified"]),
                )
                .order_by(WaitingList.created_at)
                .first()
            )
            if waitlist_entry:
                waitlist_entry.status = "booked"
                waitlist_entry.booked_appointment_id = appointment.id
                db.commit()
        except Exception as e:
            db.rollback()
            logger.warning(f"Waitlist linkage skipped for appointment {appointment.id}: {e}")
    except HTTPException:
        raise
    except IntegrityError as e:
        # Real conflict — e.g. the uq_doctor_slot unique constraint fired
        # because someone else booked this exact slot in the meantime.
        db.rollback()
        logger.warning(f"Booking conflict on commit: {e}")
        raise HTTPException(status_code=409, detail="This slot was just booked by someone else. Please pick another time.")
    except Exception as e:
        # Anything else (DB timeout, connection issue, etc.) — don't lie
        # to the user about the cause.
        db.rollback()
        logger.error(f"Booking commit failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Something went wrong while booking. Please try again.")

    response = {
        "appointment_id": appointment.id,
        "patient_id": appointment.patient_id,
        "confirmation_token": appointment.confirmation_token,
        "cancel_token": appointment.cancel_token,
        "scheduled_at": appointment.scheduled_at.isoformat(),
        "doctor": doctor.full_name or "",
        "clinic": clinic.name or "",
        "payment_required": payment_required,
        "status": appointment.status.value if hasattr(appointment.status, "value") else appointment.status,
        "payment_status": appointment.payment_status.value if hasattr(appointment.payment_status, "value") else appointment.payment_status,
    }

    if payment_required:
        callback_url = f"{settings.FRONTEND_URL.rstrip('/')}/book/{slug}/pay/verify?reference={payment_reference}"
        patient_email = body.email or f"{body.phone}@noemail.livevault.cloud"
        try:
            checkout = await hospital_payments.initialize_booking_transaction(
                email=patient_email,
                amount_kobo=int(round(float(appointment.payment_amount) * 100)),
                reference=payment_reference,
                metadata={"appointment_id": appointment.id, "hospital_id": clinic.id},
                callback_url=callback_url,
            )
        except Exception as e:
            appointment.payment_status = PaymentStatus.FAILED
            appointment.status = AppointmentStatus.CANCELLED
            db.commit()
            logger.error(f"Paystack booking initialize failed: {e}", exc_info=True)
            raise HTTPException(status_code=502, detail="Payment provider unavailable. Please try again.")
        response["payment_amount"] = float(appointment.payment_amount)
        response["currency"] = clinic.currency or "NGN"
        response["payment_reference"] = payment_reference
        response["payment_url"] = checkout.get("authorization_url")
        response["access_code"] = checkout.get("access_code")

    log_booking_event("public_booked", appointment.id, clinic.id, body.doctor_id, patient_id)
    if not payment_required:
        background_tasks.add_task(_dispatch_risk_and_reminders, appointment.id)
        background_tasks.add_task(_dispatch_new_booking_notify, appointment.id)

    return response


@router.get("/appointments/{appointment_id}/status")
def get_public_appointment_status(appointment_id: str, token: str, db: Session = Depends(get_db)):
    """Same ownership proof as /doctor-contact just below — Vitar has no
    patient login, so the confirmation_token (returned once, at booking
    time) is the only thing that should let a caller read this appointment's
    status. Previously took appointment_id alone with no check at all."""
    apt = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not apt or apt.confirmation_token != token:
        raise HTTPException(status_code=404, detail="Appointment not found")
    return {
        "appointment_id": apt.id,
        "status": apt.status.value if hasattr(apt.status, "value") else apt.status,
        "payment_status": apt.payment_status.value if hasattr(apt.payment_status, "value") else apt.payment_status,
        "payment_reference": apt.payment_provider_ref,
    }


@router.get("/appointments/{appointment_id}/doctor-contact")
def get_appointment_doctor_contact(appointment_id: str, token: str, db: Session = Depends(get_db)):
    """
    Doctor Contact (WhatsApp/Call), moved here from the pre-booking doctor
    list (see get_clinic_booking_page). Vitar has no patient login, so
    ownership is proven the same way Appointment.confirmation_token already
    proves it for /confirm/{token} — the patient only has this token because
    they just made this exact booking. Real authorization boundary: verify
    every check server-side, never trust appointment_id alone.
    """
    apt = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not apt or apt.confirmation_token != token:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if apt.status in (AppointmentStatus.CANCELLED, AppointmentStatus.NO_SHOW):
        raise HTTPException(status_code=409, detail="This appointment is no longer active")

    clinic = db.query(Clinic).filter(Clinic.id == apt.clinic_id).first()
    doctor = db.query(Doctor).filter(Doctor.id == apt.doctor_id).first()
    if not clinic or not doctor:
        raise HTTPException(status_code=404, detail="Not found")

    if not has_doctor_contact_access(clinic):
        raise HTTPException(status_code=402, detail="Doctor contact is not available on this clinic's current plan")
    if not doctor.doctor_details_enabled:
        raise HTTPException(status_code=404, detail="Doctor contact is not available")

    whatsapp_on = bool(clinic.contact_whatsapp_enabled)
    call_on = bool(clinic.contact_call_enabled)
    if not (whatsapp_on or call_on):
        raise HTTPException(status_code=404, detail="Doctor contact is not available")

    return {
        "doctor_name": doctor.full_name or "",
        "email": doctor.email or None,
        "phone": doctor.phone if (whatsapp_on or call_on) else None,
        "talk_with_doctor_url": _whatsapp_link(doctor.phone) if whatsapp_on else None,
        "call_url": _call_link(doctor.phone) if call_on else None,
    }


@router.get("/payments/verify/{reference}")
async def verify_booking_payment(reference: str, db: Session = Depends(get_db)):
    apt = db.query(Appointment).filter(Appointment.payment_provider_ref == reference).first()
    if not apt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    try:
        data = await hospital_payments.verify_transaction(reference)
    except Exception:
        raise HTTPException(status_code=502, detail="Unable to verify payment")
    if data.get("status") == "success" and apt.payment_status != PaymentStatus.PAID:
        from app.api.v1.endpoints.webhooks import finalize_paid_appointment
        finalize_paid_appointment(apt, data, db)
    return {
        "appointment_id": apt.id,
        "status": apt.status.value if hasattr(apt.status, "value") else apt.status,
        "payment_status": apt.payment_status.value if hasattr(apt.payment_status, "value") else apt.payment_status,
    }


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

    from app.api.v1.endpoints.webhooks import void_payout_for_cancelled_appointment
    void_payout_for_cancelled_appointment(apt, db)

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

    doctor = db.query(Doctor).filter(
        Doctor.id == body.doctor_id,
        Doctor.clinic_id == clinic.id,
        Doctor.is_active == True,
    ).first()
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")

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

