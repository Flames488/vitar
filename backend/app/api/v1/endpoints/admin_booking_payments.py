"""
Vitar — Admin Dashboard: Booking Payments

GET /api/v1/admin/booking-payments   Every patient payment for a clinic
                                      appointment, platform-wide.

Reads PatientPayment (app/models/models.py) — the record
finalize_paid_appointment (webhooks.py) creates the moment a patient's
booking payment is confirmed. This is the read side that lets the admin
see every booking payment across every clinic in one place, instead of
only finding out one exists by chasing down an individual appointment
(which is how the Aproko Nation Foundation payment was originally found).
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_superadmin
from app.models.models import Clinic, Patient, PatientPayment, User

router = APIRouter(prefix="/admin/booking-payments", tags=["Admin — Booking Payments"])


def _serialize(payment: PatientPayment, clinic_name: Optional[str], patient_name: Optional[str]) -> dict:
    return {
        "id": payment.id,
        "appointment_id": payment.appointment_id,
        "clinic_id": payment.clinic_id,
        "clinic_name": clinic_name,
        "patient_name": patient_name,
        "provider": payment.provider.value if hasattr(payment.provider, "value") else payment.provider,
        "provider_reference": payment.provider_reference,
        "total_amount": float(payment.total_amount) if payment.total_amount is not None else 0,
        "clinic_share": float(payment.clinic_share) if payment.clinic_share is not None else 0,
        "platform_share": float(payment.platform_share) if payment.platform_share is not None else 0,
        "currency": payment.currency,
        "status": payment.status.value if hasattr(payment.status, "value") else payment.status,
        "paid_at": payment.paid_at.isoformat() if payment.paid_at else None,
        "created_at": payment.created_at.isoformat() if payment.created_at else None,
    }


@router.get("/")
def list_booking_payments(
    status_filter: Optional[str] = Query(None, alias="status"),
    clinic_id: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    admin: User = Depends(get_current_superadmin),
    db: Session = Depends(get_db),
):
    q = db.query(PatientPayment)
    if status_filter:
        q = q.filter(PatientPayment.status == status_filter)
    if clinic_id:
        q = q.filter(PatientPayment.clinic_id == clinic_id)

    total = q.count()
    rows = q.order_by(PatientPayment.created_at.desc()).offset((page - 1) * limit).limit(limit).all()

    clinic_ids = [r.clinic_id for r in rows]
    clinics = {c.id: c for c in db.query(Clinic).filter(Clinic.id.in_(clinic_ids)).all()} if clinic_ids else {}
    patient_ids = [r.patient_id for r in rows]
    patients = {p.id: p for p in db.query(Patient).filter(Patient.id.in_(patient_ids)).all()} if patient_ids else {}

    items = [
        _serialize(
            r,
            clinics.get(r.clinic_id).name if r.clinic_id in clinics else None,
            patients.get(r.patient_id).full_name if r.patient_id in patients else None,
        )
        for r in rows
    ]
    return {"items": items, "total": total, "page": page, "limit": limit}
