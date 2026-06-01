"""
Vitar v5 - Patients Endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.core.database import get_db
from app.core.database_async import get_async_db
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from app.core.security import get_current_clinic
from app.models.models import Patient, Appointment
from app.core.cache import cache, patient_list_key, TTL_MEDIUM
from app.core.metrics import record_cache_hit, record_cache_miss
from app.middleware.api_key_auth import verify_api_key

router = APIRouter()


class PatientCreate(BaseModel):
    full_name: str
    phone: str
    email: Optional[str] = None
    date_of_birth: Optional[str] = None
    gender: Optional[str] = None
    notes: Optional[str] = None
    # FIX: clinic_id gap — Wabizz passes this from HospitalNicheConfig.vitar_clinic_id
    # so patients appear in the clinic's Vitar dashboard after WhatsApp booking.
    clinic_id: Optional[str] = None

class PatientUpdate(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    notes: Optional[str] = None
    gender: Optional[str] = None


@router.get("/")
def list_patients(
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    clinic=Depends(get_current_clinic),
    db: Session = Depends(get_db),
):
    # Only cache non-search, standard page queries to avoid key explosion
    use_cache = not search and limit == 20
    if use_cache:
        ck = patient_list_key(str(clinic.id), page)
        cached = cache.get(ck)
        if cached:
            record_cache_hit()
            return cached
        record_cache_miss()

    q = db.query(Patient).filter(Patient.clinic_id == clinic.id)
    if search:
        q = q.filter(
            Patient.full_name.ilike(f"%{search}%") |
            Patient.phone.ilike(f"%{search}%") |
            Patient.email.ilike(f"%{search}%")
        )
    total = q.count()
    patients = q.order_by(Patient.full_name).offset((page-1)*limit).limit(limit).all()
    result = {"items": [_serialize(p) for p in patients], "total": total, "page": page}

    if use_cache:
        cache.set(ck, result, ttl=TTL_MEDIUM)
    return result


@router.post("/", status_code=201)
def create_patient(
    body: PatientCreate,
    clinic=Depends(get_current_clinic),
    db: Session = Depends(get_db),
):
    # Check for duplicate phone within clinic
    existing = db.query(Patient).filter(
        Patient.clinic_id == clinic.id,
        Patient.phone == body.phone,
    ).first()
    if existing:
        return _serialize(existing)  # Idempotent - return existing patient

    from datetime import datetime
    dob = None
    if body.date_of_birth:
        try:
            dob = datetime.strptime(body.date_of_birth, "%Y-%m-%d")
        except Exception:
            pass

    patient = Patient(
        clinic_id=clinic.id,
        full_name=body.full_name,
        phone=body.phone,
        email=body.email,
        date_of_birth=dob,
        gender=body.gender,
        notes=body.notes,
    )
    db.add(patient)
    db.commit()
    db.refresh(patient)
    cache.delete_pattern(f"cache:clinic:patients:{clinic.id}:*")
    return _serialize(patient)


@router.get("/{patient_id}")
def get_patient(
    patient_id: str,
    clinic=Depends(get_current_clinic),
    db: Session = Depends(get_db),
):
    p = _get_or_404(patient_id, clinic.id, db)
    data = _serialize(p)
    # Include appointment history
    apts = db.query(Appointment).filter(
        Appointment.patient_id == patient_id,
        Appointment.clinic_id == clinic.id,
    ).order_by(Appointment.scheduled_at.desc()).limit(10).all()
    data["recent_appointments"] = [
        {"id": a.id, "scheduled_at": a.scheduled_at.isoformat(), "status": a.status.value}
        for a in apts
    ]
    return data


@router.patch("/{patient_id}")
def update_patient(
    patient_id: str,
    body: PatientUpdate,
    clinic=Depends(get_current_clinic),
    db: Session = Depends(get_db),
):
    p = _get_or_404(patient_id, clinic.id, db)
    for field, val in body.model_dump(exclude_none=True).items():
        setattr(p, field, val)
    db.commit()
    db.refresh(p)
    cache.delete_pattern(f"cache:clinic:patients:{clinic.id}:*")
    return _serialize(p)


def _get_or_404(patient_id: str, clinic_id: str, db: Session) -> Patient:
    p = db.query(Patient).filter(Patient.id == patient_id, Patient.clinic_id == clinic_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Patient not found")
    return p


def _serialize(p: Patient) -> dict:
    return {
        "id": p.id,
        "full_name": p.full_name,
        "phone": p.phone,
        "email": p.email,
        "gender": p.gender,
        "notes": p.notes,
        # FIX: include clinic_id — the Wabizz Patient TypeScript type (hospital/types.ts)
        # requires this field.  Omitting it caused type errors and undefined behaviour
        # in the intent handler when checking which clinic a patient belongs to.
        "clinic_id": p.clinic_id,
        "historical_no_show_rate": p.historical_no_show_rate,
        "total_appointments": p.total_appointments,
        "total_no_shows": p.total_no_shows,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


# ── Wabizz machine-to-machine endpoints ───────────────────────────────────────

@router.get(
    "/by-phone/{phone}",
    dependencies=[Depends(verify_api_key)],
    summary="Find patient by phone number (Wabizz integration)",
    description=(
        "Looks up a patient by their E.164 phone number. "
        "Returns 404 if no matching active patient is found. "
        "Protected by API key — browser session auth is NOT checked. "
        "Phone format expected: +2348012345678"
    ),
)
async def get_patient_by_phone(
    phone: str,
    db: AsyncSession = Depends(get_async_db),
):
    """
    Wabizz calls this endpoint to find a patient using only their WhatsApp
    phone number (E.164 format).  Uses async SQLAlchemy for non-blocking I/O.
    """
    result = await db.execute(
        select(Patient).where(
            and_(Patient.phone == phone, Patient.is_active == True)  # noqa: E712
        )
    )
    patient = result.scalar_one_or_none()

    if not patient:
        raise HTTPException(
            status_code=404,
            detail=f"No active patient found with phone {phone}",
        )

    return _serialize(patient)


# ── Additional Wabizz machine-to-machine endpoints ────────────────────────────

@router.post(
    "/wabizz",
    status_code=201,
    dependencies=[Depends(verify_api_key)],
    summary="Create patient (Wabizz integration)",
    description=(
        "Creates a new patient record without requiring a clinic browser session. "
        "Protected by API key. Wabizz calls this after GET /by-phone returns 404. "
        "Phone must be in E.164 format: +2348012345678"
    ),
)
async def wabizz_create_patient(
    body: PatientCreate,
    db: AsyncSession = Depends(get_async_db),
):
    """
    Wabizz calls this to create a patient using only data it knows from WhatsApp.
    Uses async SQLAlchemy for non-blocking I/O.
    """
    # Prevent duplicate phone across all clinics
    result = await db.execute(
        select(Patient).where(
            and_(Patient.phone == body.phone, Patient.is_active == True)  # noqa: E712
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        return _serialize(existing)

    patient = Patient(
        full_name=body.full_name,
        phone=body.phone,
        email=body.email,
        gender=body.gender,
        notes=body.notes,
        is_active=True,
        clinic_id=body.clinic_id,
    )
    db.add(patient)
    await db.commit()
    await db.refresh(patient)
    return _serialize(patient)


@router.get(
    "/wabizz/{patient_id}/appointments",
    dependencies=[Depends(verify_api_key)],
    summary="Get patient appointments (Wabizz integration)",
)
async def wabizz_get_patient_appointments(
    patient_id: str,
    db: AsyncSession = Depends(get_async_db),
):
    """Returns all appointments for a patient. Called by vitar-client.getPatientAppointments(). Uses async SQLAlchemy."""
    from app.models.models import Appointment  # local import to avoid circular

    # FIX: add joinedload(Appointment.doctor) so _apt_serialize() can access
    # apt.doctor.  Without it, async SQLAlchemy lazy-loads return None (or raise
    # MissingGreenlet), so every appointment in the history shows doctor: null.
    from sqlalchemy.orm import joinedload as _joinedload
    result = await db.execute(
        select(Appointment)
        .options(_joinedload(Appointment.doctor))
        .where(Appointment.patient_id == patient_id)
        .order_by(Appointment.scheduled_at.desc())
        .limit(20)
    )
    apts = result.scalars().all()
    return [_apt_serialize(a) for a in apts]


def _apt_serialize(apt) -> dict:
    """Minimal appointment serialization for patient history responses."""
    return {
        "id": apt.id,
        "scheduled_at": apt.scheduled_at.isoformat() if apt.scheduled_at else None,
        "status": apt.status.value if hasattr(apt.status, "value") else apt.status,
        "doctor": {
            "id": apt.doctor.id,
            "full_name": apt.doctor.full_name,
            "specialty": apt.doctor.specialty,
        } if apt.doctor else None,
    }
