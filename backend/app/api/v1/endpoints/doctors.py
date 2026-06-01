"""
Vitar v5 - Doctors Endpoints
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone

from app.core.utils import utcnow
from app.core.database import get_db
from app.core.database_async import get_async_db
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from app.core.security import get_current_clinic
from app.models.models import Doctor, DoctorAvailability, DoctorBlockedTime
from app.services.trial_guard import check_doctor_limit
from app.core.cache import cache, doctor_list_key, TTL_MEDIUM
from app.core.metrics import record_cache_hit, record_cache_miss
from app.middleware.api_key_auth import verify_api_key

router = APIRouter()


class DoctorCreate(BaseModel):
    full_name: str
    specialty: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    bio: Optional[str] = None
    consultation_fee: Optional[float] = None

class DoctorUpdate(BaseModel):
    full_name: Optional[str] = None
    specialty: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    bio: Optional[str] = None
    consultation_fee: Optional[float] = None
    is_active: Optional[bool] = None

class AvailabilitySlot(BaseModel):
    day_of_week: int  # 0=Mon
    start_time: str   # "09:00"
    end_time: str     # "17:00"
    slot_duration_mins: int = 30
    is_available: bool = True

class BlockedTimeCreate(BaseModel):
    start_at: datetime
    end_at: datetime
    reason: Optional[str] = None


@router.get("/")
def list_doctors(
    clinic=Depends(get_current_clinic),
    db: Session = Depends(get_db),
):
    ck = doctor_list_key(str(clinic.id))
    cached = cache.get(ck)
    if cached:
        record_cache_hit()
        return cached
    record_cache_miss()
    doctors = db.query(Doctor).filter(
        Doctor.clinic_id == clinic.id,
        Doctor.is_active == True,
    ).order_by(Doctor.full_name).all()
    result = {"doctors": [_serialize(d) for d in doctors]}
    cache.set(ck, result, ttl=TTL_MEDIUM)
    return result


@router.post("/", status_code=201)
def create_doctor(
    body: DoctorCreate,
    clinic=Depends(get_current_clinic),
    db: Session = Depends(get_db),
):
    check_doctor_limit(clinic, db)

    doctor = Doctor(
        clinic_id=clinic.id,
        full_name=body.full_name,
        specialty=body.specialty,
        email=body.email,
        phone=body.phone,
        bio=body.bio,
        consultation_fee=body.consultation_fee or 0,
        is_active=True,
    )
    db.add(doctor)
    db.commit()
    db.refresh(doctor)
    cache.delete(doctor_list_key(str(clinic.id)))
    return _serialize(doctor)


@router.get("/{doctor_id}")
def get_doctor(
    doctor_id: str,
    clinic=Depends(get_current_clinic),
    db: Session = Depends(get_db),
):
    d = _get_or_404(doctor_id, clinic.id, db)
    data = _serialize(d)
    data["availability"] = [
        {
            "id": a.id,
            "day_of_week": a.day_of_week,
            "start_time": a.start_time,
            "end_time": a.end_time,
            "slot_duration_mins": a.slot_duration_mins,
            "is_available": a.is_available,
        }
        for a in d.availability
    ]
    return data


@router.patch("/{doctor_id}")
def update_doctor(
    doctor_id: str,
    body: DoctorUpdate,
    clinic=Depends(get_current_clinic),
    db: Session = Depends(get_db),
):
    d = _get_or_404(doctor_id, clinic.id, db)
    for field, val in body.model_dump(exclude_none=True).items():
        setattr(d, field, val)
    db.commit()
    db.refresh(d)
    cache.delete(doctor_list_key(str(clinic.id)))
    return _serialize(d)


@router.delete("/{doctor_id}")
def delete_doctor(
    doctor_id: str,
    clinic=Depends(get_current_clinic),
    db: Session = Depends(get_db),
):
    d = _get_or_404(doctor_id, clinic.id, db)
    d.is_active = False
    db.commit()
    cache.delete(doctor_list_key(str(clinic.id)))
    return {"message": "Doctor deactivated", "id": doctor_id}


@router.put("/{doctor_id}/availability")
def set_availability(
    doctor_id: str,
    slots: List[AvailabilitySlot],
    clinic=Depends(get_current_clinic),
    db: Session = Depends(get_db),
):
    d = _get_or_404(doctor_id, clinic.id, db)

    # Replace all availability
    db.query(DoctorAvailability).filter(DoctorAvailability.doctor_id == doctor_id).delete()
    for slot in slots:
        db.add(DoctorAvailability(
            doctor_id=doctor_id,
            day_of_week=slot.day_of_week,
            start_time=slot.start_time,
            end_time=slot.end_time,
            slot_duration_mins=slot.slot_duration_mins,
            is_available=slot.is_available,
        ))
    db.commit()
    return {"message": "Availability updated", "slots": len(slots)}


@router.get("/{doctor_id}/available-slots")
def get_available_slots(
    doctor_id: str,
    date: str,  # YYYY-MM-DD
    clinic=Depends(get_current_clinic),
    db: Session = Depends(get_db),
):
    """Returns available time slots for a doctor on a given date."""
    from datetime import datetime, timedelta
    from app.models.models import Appointment, AppointmentStatus

    d = _get_or_404(doctor_id, clinic.id, db)
    target = datetime.strptime(date, "%Y-%m-%d")
    dow = target.weekday()  # 0=Mon

    avail = db.query(DoctorAvailability).filter(
        DoctorAvailability.doctor_id == doctor_id,
        DoctorAvailability.day_of_week == dow,
        DoctorAvailability.is_available == True,
    ).first()

    if not avail:
        return {"slots": [], "date": date}

    # Generate all slots
    start_h, start_m = map(int, avail.start_time.split(":"))
    end_h, end_m = map(int, avail.end_time.split(":"))
    slot_duration = avail.slot_duration_mins or 30

    current = target.replace(hour=start_h, minute=start_m, second=0, microsecond=0)
    end_dt = target.replace(hour=end_h, minute=end_m, second=0, microsecond=0)

    # Existing appointments for this day
    day_start = target
    day_end = target + timedelta(days=1)
    booked = db.query(Appointment.scheduled_at).filter(
        Appointment.doctor_id == doctor_id,
        Appointment.status.not_in([AppointmentStatus.CANCELLED, AppointmentStatus.NO_SHOW]),
        Appointment.scheduled_at >= day_start,
        Appointment.scheduled_at < day_end,
    ).all()
    booked_times = {b.scheduled_at.replace(second=0, microsecond=0) for b in booked}

    slots = []
    now = utcnow()
    while current < end_dt:
        slots.append({
            "time": current.strftime("%H:%M"),
            "datetime": current.isoformat(),
            "available": current not in booked_times and current > now,
        })
        current += timedelta(minutes=slot_duration)

    return {"slots": slots, "date": date, "doctor_id": doctor_id}


@router.post("/{doctor_id}/block-time")
def block_time(
    doctor_id: str,
    body: BlockedTimeCreate,
    clinic=Depends(get_current_clinic),
    db: Session = Depends(get_db),
):
    _get_or_404(doctor_id, clinic.id, db)
    block = DoctorBlockedTime(
        doctor_id=doctor_id,
        start_at=body.start_at,
        end_at=body.end_at,
        reason=body.reason,
    )
    db.add(block)
    db.commit()
    return {"message": "Time blocked", "id": block.id}


def _get_or_404(doctor_id: str, clinic_id: str, db: Session) -> Doctor:
    d = db.query(Doctor).filter(Doctor.id == doctor_id, Doctor.clinic_id == clinic_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Doctor not found")
    return d


def _serialize(d: Doctor) -> dict:
    return {
        "id": d.id,
        "full_name": d.full_name,
        "specialty": d.specialty,
        "email": d.email,
        "phone": d.phone,
        "bio": d.bio,
        "consultation_fee": float(d.consultation_fee) if d.consultation_fee else 0,
        "is_active": d.is_active,
        "created_at": d.created_at.isoformat() if d.created_at else None,
    }

def _serialize_doctor(d: Doctor) -> dict:
    """Wabizz-specific doctor serialization — matches the Doctor interface in
    src/lib/niche/hospital/types.ts exactly so vitar-client.ts callers receive
    all expected fields without TypeScript narrowing issues."""
    return {
        "id": str(d.id),
        "full_name": d.full_name,
        "specialty": d.specialty,
        # FIX: email, phone, bio were missing — the Wabizz Doctor type declares
        # all three as optional string fields.  Omitting them caused TypeScript
        # type errors and prevented the intent handler from surfacing doctor
        # contact info in fallback messages.
        "email": d.email,
        "phone": d.phone,
        "bio": d.bio,
        "consultation_fee": float(d.consultation_fee) if d.consultation_fee else 0,
        "is_active": d.is_active,
    }


# ── Wabizz machine-to-machine endpoints ───────────────────────────────────────
# These mirror the browser-facing endpoints but accept X-API-Key instead of
# a clinic JWT.  They return data in the format vitar-client.ts expects.

@router.get(
    "/wabizz/list",
    dependencies=[Depends(verify_api_key)],
    summary="List doctors (Wabizz integration)",
)
async def wabizz_list_doctors(
    specialty: Optional[str] = None,
    db: AsyncSession = Depends(get_async_db),
):
    """
    Returns all active doctors.  Optionally filtered by specialty.
    Called by Wabizz vitar-client.getDoctors(). Uses async SQLAlchemy.
    """
    stmt = select(Doctor).where(Doctor.is_active == True)  # noqa: E712
    if specialty:
        stmt = stmt.where(Doctor.specialty.ilike(f"%{specialty}%"))
    result = await db.execute(stmt)
    doctors = result.scalars().all()
    return [_serialize_doctor(d) for d in doctors]


@router.get(
    "/wabizz/{doctor_id}/slots",
    dependencies=[Depends(verify_api_key)],
    summary="Get available slots (Wabizz integration)",
)
async def wabizz_get_slots(
    doctor_id: str,
    date: str,   # YYYY-MM-DD
    db: AsyncSession = Depends(get_async_db),
):
    """
    Returns available time slots for a doctor on a given date.
    Slots include timezone-aware ISO 8601 datetimes (Africa/Lagos = UTC+1).
    Called by Wabizz vitar-client.getAvailableSlots(). Uses async SQLAlchemy.
    """
    from datetime import datetime, timedelta, timezone as _tz
    from app.models.models import Appointment, AppointmentStatus

    result = await db.execute(
        select(Doctor).where(and_(Doctor.id == doctor_id, Doctor.is_active == True))  # noqa: E712
    )
    d = result.scalar_one_or_none()
    if not d:
        raise HTTPException(status_code=404, detail="Doctor not found")

    target = datetime.strptime(date, "%Y-%m-%d")
    dow = target.weekday()

    avail_result = await db.execute(
        select(DoctorAvailability).where(
            and_(
                DoctorAvailability.doctor_id == doctor_id,
                DoctorAvailability.day_of_week == dow,
                DoctorAvailability.is_available == True,  # noqa: E712
            )
        )
    )
    avail = avail_result.scalar_one_or_none()

    if not avail:
        return {"slots": [], "date": date, "doctor_id": doctor_id}

    start_h, start_m = map(int, avail.start_time.split(":"))
    end_h, end_m = map(int, avail.end_time.split(":"))
    slot_duration = avail.slot_duration_mins or 30

    current = target.replace(hour=start_h, minute=start_m, second=0, microsecond=0)
    end_dt = target.replace(hour=end_h, minute=end_m, second=0, microsecond=0)

    day_start = target
    day_end = target + timedelta(days=1)
    booked_result = await db.execute(
        select(Appointment.scheduled_at).where(
            and_(
                Appointment.doctor_id == doctor_id,
                Appointment.status.not_in([AppointmentStatus.CANCELLED, AppointmentStatus.NO_SHOW]),
                Appointment.scheduled_at >= day_start,
                Appointment.scheduled_at < day_end,
            )
        )
    )
    booked_times = {b.scheduled_at.replace(second=0, microsecond=0) for b in booked_result}

    # WAT = UTC+1 (Africa/Lagos, no DST)
    WAT = _tz(timedelta(hours=1))
    now_utc = utcnow()
    slots = []

    while current < end_dt:
        is_available = current not in booked_times and current > now_utc
        slot_wat = current.replace(tzinfo=WAT)
        end_wat = (current + timedelta(minutes=slot_duration)).replace(tzinfo=WAT)
        slots.append({
            "start_at": slot_wat.isoformat(),
            "end_at": end_wat.isoformat(),
            "is_available": is_available,
        })
        current += timedelta(minutes=slot_duration)

    return {"slots": slots, "date": date, "doctor_id": doctor_id}
