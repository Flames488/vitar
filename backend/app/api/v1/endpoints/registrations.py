"""
Vitar — eRegistration Endpoints (Phase 1)

NEW FILE. Patient-facing electronic registration: draft/autosave, submit,
status (+ cross-clinic prefill), eligibility, and post-submission edits.

Authorization note: Vitar has no patient login — the public booking flow
(app/api/v1/endpoints/booking.py) creates Patient rows anonymously, keyed
by (clinic_id, phone). The existing precedent for letting an unauthenticated
patient act on their own record afterwards is Appointment.confirmation_token
/ cancel_token (random, single-purpose, returned once). This file follows
the same shape via PatientRegistration.registration_token rather than
assuming a session that doesn't exist in this codebase:

  - POST /registrations/draft is the one bootstrap call that identifies the
    patient by (patient_id, clinic_id) — both already known to the frontend
    immediately after booking (see booking.py's response). It mints
    registration_token on first save.
  - Every other call (restore-on-refresh, submit, patch) authenticates with
    that token instead of patient_id, so the URL a browser refresh preserves
    is the thing that has to be unguessable — same property confirmation
    links already rely on.

Feature access is gated with the existing has_paid_feature_access() from
trial_guard.py (already generic — "free during trial, then requires an
active paid plan") — no new gating table, no new trial clock.
"""
import secrets
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.utils import utcnow
from app.models.models import Clinic, Patient, PatientRegistration, RegistrationStatus
from app.services.trial_guard import has_paid_feature_access

router = APIRouter()


# ── Shared field set ────────────────────────────────────────────────────────

class RegistrationFields(BaseModel):
    full_name: Optional[str] = None
    phone_number: Optional[str] = None
    date_of_birth: Optional[datetime] = None
    gender: Optional[str] = None

    state: Optional[str] = None
    city: Optional[str] = None
    residential_address: Optional[str] = None

    emergency_contact_name: Optional[str] = None
    emergency_contact_relationship: Optional[str] = None
    emergency_contact_phone: Optional[str] = None

    # Optional health info — "unknown"/"none"/"skip" are valid stored strings,
    # never required.
    blood_group: Optional[str] = None
    genotype: Optional[str] = None
    allergies: Optional[str] = None
    existing_conditions: Optional[str] = None
    current_medications: Optional[str] = None


def _apply_fields(reg: PatientRegistration, body: BaseModel, exclude: set) -> None:
    """
    Applies only the fields the client actually sent this call (exclude_unset
    on the ORIGINAL request body). Autosave sends one step's fields at a
    time — round-tripping through a fresh RegistrationFields(**dump()) would
    mark every field "set" (Pydantic tracks what was passed to __init__, not
    whether it differs from the default), wiping previously-saved steps back
    to None on every partial save. Reading exclude_unset off body directly
    avoids that.
    """
    for key, value in body.model_dump(exclude=exclude, exclude_unset=True).items():
        setattr(reg, key, value)


def _serialize(reg: PatientRegistration, include_token: bool = False) -> dict:
    data = {
        "id": reg.id,
        "status": reg.status.value if hasattr(reg.status, "value") else reg.status,
        "full_name": reg.full_name,
        "phone_number": reg.phone_number,
        "date_of_birth": reg.date_of_birth.isoformat() if reg.date_of_birth else None,
        "gender": reg.gender,
        "state": reg.state,
        "city": reg.city,
        "residential_address": reg.residential_address,
        "emergency_contact_name": reg.emergency_contact_name,
        "emergency_contact_relationship": reg.emergency_contact_relationship,
        "emergency_contact_phone": reg.emergency_contact_phone,
        "blood_group": reg.blood_group,
        "genotype": reg.genotype,
        "allergies": reg.allergies,
        "existing_conditions": reg.existing_conditions,
        "current_medications": reg.current_medications,
        "consent_given": reg.consent_given,
        "submitted_at": reg.submitted_at.isoformat() if reg.submitted_at else None,
    }
    if include_token:
        data["registration_token"] = reg.registration_token
    return data


def _find_prefill(patient: Patient, clinic_id: str, db: Session) -> Optional[dict]:
    """
    Patient records are per-clinic in Vitar (no global patient identity), so
    "reuse info from another clinic's registration" means matching by phone
    across other patients' submitted registrations, not a shared FK.
    """
    if not patient.phone:
        return None
    other = (
        db.query(PatientRegistration)
        .join(Patient, PatientRegistration.patient_id == Patient.id)
        .filter(
            Patient.phone == patient.phone,
            PatientRegistration.clinic_id != clinic_id,
            PatientRegistration.status == RegistrationStatus.SUBMITTED,
        )
        .order_by(PatientRegistration.submitted_at.desc())
        .first()
    )
    if not other:
        return None
    return {
        "full_name": other.full_name,
        "phone_number": other.phone_number,
        "date_of_birth": other.date_of_birth.isoformat() if other.date_of_birth else None,
        "gender": other.gender,
        "state": other.state,
        "city": other.city,
        "residential_address": other.residential_address,
        "emergency_contact_name": other.emergency_contact_name,
        "emergency_contact_relationship": other.emergency_contact_relationship,
        "emergency_contact_phone": other.emergency_contact_phone,
    }


def _get_patient_in_clinic(patient_id: str, clinic_id: str, db: Session) -> Patient:
    patient = db.query(Patient).filter(Patient.id == patient_id, Patient.clinic_id == clinic_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found for this clinic")
    return patient


# ── Draft / autosave ────────────────────────────────────────────────────────

class DraftRequest(RegistrationFields):
    patient_id: str
    clinic_id: str


@router.post("/draft")
def save_draft(body: DraftRequest, db: Session = Depends(get_db)):
    _get_patient_in_clinic(body.patient_id, body.clinic_id, db)

    reg = db.query(PatientRegistration).filter(
        PatientRegistration.patient_id == body.patient_id,
        PatientRegistration.clinic_id == body.clinic_id,
    ).first()

    if reg and reg.status == RegistrationStatus.SUBMITTED:
        raise HTTPException(status_code=409, detail="Already submitted — use PATCH to edit")

    if not reg:
        reg = PatientRegistration(
            patient_id=body.patient_id,
            clinic_id=body.clinic_id,
            registration_token=secrets.token_urlsafe(16),
        )
        db.add(reg)

    _apply_fields(reg, body, exclude={"patient_id", "clinic_id"})
    db.commit()
    db.refresh(reg)
    return _serialize(reg, include_token=True)


@router.get("/draft")
def get_draft(
    clinic_id: str = Query(...),
    token: str = Query(...),
    db: Session = Depends(get_db),
):
    """Restore-on-refresh: the registration form persists `token` in its own
    URL after the first draft save (see save_draft), so a refresh can call
    back in without needing patient_id in memory."""
    reg = db.query(PatientRegistration).filter(
        PatientRegistration.clinic_id == clinic_id,
        PatientRegistration.registration_token == token,
    ).first()
    if not reg or reg.status != RegistrationStatus.DRAFT:
        raise HTTPException(status_code=404, detail="No restorable draft")
    return _serialize(reg, include_token=True)


# ── Submit ───────────────────────────────────────────────────────────────────

class SubmitRequest(RegistrationFields):
    clinic_id: str
    token: str
    consent_given: bool = False


@router.post("/submit")
def submit_registration(body: SubmitRequest, db: Session = Depends(get_db)):
    clinic = db.query(Clinic).filter(Clinic.id == body.clinic_id).first()
    if not clinic:
        raise HTTPException(status_code=404, detail="Clinic not found")

    if not has_paid_feature_access(clinic):
        raise HTTPException(
            status_code=402,
            detail={
                "code": "EREGISTRATION_UNAVAILABLE",
                "message": "Online registration isn't currently available for this clinic.",
            },
        )

    reg = db.query(PatientRegistration).filter(
        PatientRegistration.clinic_id == body.clinic_id,
        PatientRegistration.registration_token == body.token,
    ).first()
    if not reg:
        raise HTTPException(status_code=404, detail="Draft not found")
    if reg.status == RegistrationStatus.SUBMITTED:
        raise HTTPException(status_code=409, detail="Already submitted — use PATCH to edit")

    if not body.consent_given:
        raise HTTPException(status_code=422, detail="Consent is required to submit registration")

    _apply_fields(reg, body, exclude={"clinic_id", "token", "consent_given"})

    required = [reg.full_name, reg.phone_number, reg.date_of_birth, reg.gender,
                reg.state, reg.city, reg.residential_address,
                reg.emergency_contact_name, reg.emergency_contact_relationship, reg.emergency_contact_phone]
    if any(v in (None, "") for v in required):
        raise HTTPException(status_code=422, detail="Personal info, address, and emergency contact are required")

    reg.consent_given = True
    reg.consent_given_at = utcnow()
    reg.status = RegistrationStatus.SUBMITTED
    reg.submitted_at = utcnow()
    db.commit()
    db.refresh(reg)
    return _serialize(reg, include_token=True)


# ── Status (+ cross-clinic prefill) ─────────────────────────────────────────

@router.get("/status")
def get_status(
    clinic_id: str = Query(...),
    patient_id: Optional[str] = Query(None),
    token: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """
    Accepts either (patient_id, clinic_id) — the bootstrap identity available
    right after booking, before any registration/token exists — or a
    previously-issued token, e.g. from a dashboard "View/Edit" entry point.
    """
    reg = None
    if token:
        reg = db.query(PatientRegistration).filter(
            PatientRegistration.clinic_id == clinic_id,
            PatientRegistration.registration_token == token,
        ).first()
    elif patient_id:
        reg = db.query(PatientRegistration).filter(
            PatientRegistration.clinic_id == clinic_id,
            PatientRegistration.patient_id == patient_id,
        ).first()
    else:
        raise HTTPException(status_code=422, detail="patient_id or token is required")

    if reg and reg.status == RegistrationStatus.SUBMITTED:
        return {"registered": True, **_serialize(reg, include_token=True)}

    prefill = None
    if patient_id:
        patient = _get_patient_in_clinic(patient_id, clinic_id, db)
        prefill = _find_prefill(patient, clinic_id, db)

    return {
        "registered": False,
        "draft": _serialize(reg, include_token=True) if reg else None,
        "prefill": prefill,
    }


# ── Eligibility ──────────────────────────────────────────────────────────────

@router.get("/eligibility")
def get_eligibility(clinic_id: str = Query(...), db: Session = Depends(get_db)):
    clinic = db.query(Clinic).filter(Clinic.id == clinic_id).first()
    if not clinic:
        raise HTTPException(status_code=404, detail="Clinic not found")
    return {"available": has_paid_feature_access(clinic)}


# ── Edit an already-submitted registration ──────────────────────────────────

class PatchRequest(RegistrationFields):
    token: str


@router.patch("/{registration_id}")
def edit_registration(registration_id: str, body: PatchRequest, db: Session = Depends(get_db)):
    reg = db.query(PatientRegistration).filter(PatientRegistration.id == registration_id).first()
    if not reg or reg.registration_token != body.token:
        raise HTTPException(status_code=404, detail="Registration not found")
    if reg.status != RegistrationStatus.SUBMITTED:
        raise HTTPException(status_code=409, detail="Only a submitted registration can be edited — use the draft endpoints")

    # Expiry blocks new submissions, never edits to an existing registration
    # (see trial_guard.has_paid_feature_access docstring / Phase 1 spec) — no
    # eligibility check here, intentionally.
    _apply_fields(reg, body, exclude={"token"})
    db.commit()
    db.refresh(reg)
    return _serialize(reg, include_token=True)
