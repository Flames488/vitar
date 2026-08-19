"""
Vitar — Admin Dashboard: Booking Payments (+ their payout status)

GET /api/v1/admin/booking-payments   Every patient payment for a clinic
                                      appointment, platform-wide, together
                                      with the matching payout's status.

Reads PatientPayment (app/models/models.py) — the record
finalize_paid_appointment (webhooks.py) creates the moment a patient's
booking payment is confirmed — joined with its Payout (1:1 via
appointment_id, always created in the same transaction). Deliberately
merged into one view rather than split across "Booking Payments" and
"Payouts" pages: the two used to live separately and it was genuinely
confusing to see "paid" on one page and "pending payout" on another for
the same booking, with no way to tell from either page alone that they
were describing two different legs of the same transaction. One row now
tells the whole story: did the patient pay, and did the clinic get paid.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_superadmin
from app.models.models import Clinic, Patient, PatientPayment, Payout, User

router = APIRouter(prefix="/admin/booking-payments", tags=["Admin — Booking Payments"])


def _serialize(
    payment: PatientPayment,
    clinic_name: Optional[str],
    patient_name: Optional[str],
    payout: Optional[Payout],
) -> dict:
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
        "payout": {
            "id": payout.id,
            "amount": payout.amount,  # kobo — matches admin_payouts.py's serialize_payout convention
            "status": payout.status.value if hasattr(payout.status, "value") else payout.status,
            "sent_at": payout.sent_at.isoformat() if payout.sent_at else None,
        } if payout else None,
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
    appointment_ids = [r.appointment_id for r in rows]
    payouts = (
        {p.appointment_id: p for p in db.query(Payout).filter(Payout.appointment_id.in_(appointment_ids)).all()}
        if appointment_ids else {}
    )

    items = [
        _serialize(
            r,
            clinics.get(r.clinic_id).name if r.clinic_id in clinics else None,
            patients.get(r.patient_id).full_name if r.patient_id in patients else None,
            payouts.get(r.appointment_id),
        )
        for r in rows
    ]
    return {"items": items, "total": total, "page": page, "limit": limit}
