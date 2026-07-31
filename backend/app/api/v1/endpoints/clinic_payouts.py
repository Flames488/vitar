from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_clinic
from app.models.models import (
    Clinic,
    HospitalBankAccount,
    Payout,
    PayoutStatus,
    PatientPayment,
)

router = APIRouter(prefix="/clinics/me/payouts", tags=["Clinic — Payouts"])


def _masked_account(account: Optional[HospitalBankAccount]) -> Optional[dict]:
    if not account:
        return None
    number = account.account_number or ""
    masked = f"****{number[-4:]}" if len(number) >= 4 else number
    return {
        "bank_name": account.bank_name,
        "account_name": account.account_name,
        "account_number_masked": masked,
        "verified": account.verified,
    }


@router.get("/summary")
def get_payout_summary(
    clinic: Clinic = Depends(get_current_clinic),
    db: Session = Depends(get_db),
):
    """
    High-level view for the clinic dashboard: how much is waiting to be sent,
    how much has been sent so far, and where it's going.
    """
    pending_amount = db.query(func.coalesce(func.sum(Payout.amount), 0)).filter(
        Payout.hospital_id == clinic.id,
        Payout.status == PayoutStatus.PENDING_PAYOUT.value,
    ).scalar()

    sent_total = db.query(func.coalesce(func.sum(Payout.amount), 0)).filter(
        Payout.hospital_id == clinic.id,
        Payout.status == PayoutStatus.SENT.value,
    ).scalar()

    failed_count = db.query(func.count(Payout.id)).filter(
        Payout.hospital_id == clinic.id,
        Payout.status == PayoutStatus.FAILED.value,
    ).scalar()

    last_sent = db.query(Payout).filter(
        Payout.hospital_id == clinic.id,
        Payout.status == PayoutStatus.SENT.value,
    ).order_by(Payout.sent_at.desc()).first()

    account = db.query(HospitalBankAccount).filter(
        HospitalBankAccount.hospital_id == clinic.id,
        HospitalBankAccount.active == True,  # noqa: E712
    ).order_by(HospitalBankAccount.created_at.desc()).first()

    return {
        "currency": "NGN",
        "pending_amount": pending_amount / 100,
        "sent_total": sent_total / 100,
        "failed_count": failed_count,
        "last_sent_amount": (last_sent.amount / 100) if last_sent else None,
        "last_sent_at": last_sent.sent_at.isoformat() if last_sent and last_sent.sent_at else None,
        "bank_account": _masked_account(account),
        "auto_send_after_hours": settings.PAYOUT_AUTO_SEND_AFTER_HOURS,
        "platform_fee_pct": settings.PLATFORM_PAYOUT_FEE_PCT,
    }


@router.get("/")
def list_payouts(
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    clinic: Clinic = Depends(get_current_clinic),
    db: Session = Depends(get_db),
):
    """
    Per-appointment payout history for the logged-in clinic — what was
    collected, what Vitar's fee was, and whether it's been sent yet.
    """
    q = db.query(Payout).filter(Payout.hospital_id == clinic.id)
    if status:
        q = q.filter(Payout.status == status)
    total = q.count()
    payouts = q.order_by(Payout.created_at.desc()).offset((page - 1) * limit).limit(limit).all()

    appointment_ids = [p.appointment_id for p in payouts]
    payments = {}
    if appointment_ids:
        rows = db.query(PatientPayment).filter(PatientPayment.appointment_id.in_(appointment_ids)).all()
        payments = {r.appointment_id: r for r in rows}

    items = []
    for p in payouts:
        payment = payments.get(p.appointment_id)
        items.append({
            "id": p.id,
            "appointment_id": p.appointment_id,
            "total_paid_by_patient": payment.total_amount if payment else None,
            "platform_fee": payment.platform_share if payment else None,
            "amount_to_clinic": p.amount / 100,
            "currency": "NGN",
            "status": p.status,
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "sent_at": p.sent_at.isoformat() if p.sent_at else None,
        })

    return {"items": items, "total": total, "page": page, "limit": limit}
