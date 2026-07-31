from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.logging import get_logger
from app.core.security import get_current_superadmin
from app.core.utils import utcnow
from app.models.models import Clinic, HospitalBankAccount, Payout, PayoutStatus, User
from app.services.hospital_payments import hospital_payments

logger = get_logger(__name__)


router = APIRouter(prefix="/admin/payouts", tags=["Admin — Payouts"])


def serialize_payout(payout: Payout, clinic: Optional[Clinic] = None) -> dict:
    clinic = clinic or payout.clinic
    appointment = payout.appointment
    return {
        "id": payout.id,
        "appointment_id": payout.appointment_id,
        "appointment_reference": appointment.payment_provider_ref if appointment else None,
        "hospital_id": payout.hospital_id,
        "hospital_name": clinic.name if clinic else None,
        "amount": payout.amount,
        "currency": "NGN",
        "status": payout.status.value if hasattr(payout.status, "value") else payout.status,
        "paystack_transfer_code": payout.paystack_transfer_code,
        "created_at": payout.created_at.isoformat() if payout.created_at else None,
        "sent_at": payout.sent_at.isoformat() if payout.sent_at else None,
    }


async def send_payout_to_hospital(payout_id: str, db: Session) -> Payout:
    payout = db.query(Payout).filter(Payout.id == payout_id).with_for_update().first()
    if not payout:
        raise HTTPException(status_code=404, detail="Payout not found")
    if payout.status == PayoutStatus.SENT.value:
        return payout

    account = db.query(HospitalBankAccount).filter(
        HospitalBankAccount.hospital_id == payout.hospital_id,
        HospitalBankAccount.active == True,  # noqa: E712
        HospitalBankAccount.verified == True,  # noqa: E712
    ).order_by(HospitalBankAccount.created_at.desc()).first()
    if not account or not account.paystack_recipient_code:
        raise HTTPException(status_code=409, detail="Hospital has no verified payout account")

    # Deterministic, stable across retries: if a prior attempt timed out on
    # our side after Paystack had already accepted it, resending with the
    # same reference lets Paystack tell us "duplicate" instead of moving
    # money twice.
    transfer_reference = f"vitar-payout-{payout.id}"
    try:
        transfer = await hospital_payments.initiate_transfer(
            amount_kobo=payout.amount,
            recipient_code=account.paystack_recipient_code,
            reason=f"Vitar booking payout - appointment {payout.appointment_id}",
            reference=transfer_reference,
        )
    except Exception as exc:
        if "duplicate" in str(exc).lower():
            # We've already sent this exact transfer before. Find out what
            # actually happened instead of assuming failure and letting a
            # future retry pay the hospital again.
            try:
                transfer = await hospital_payments.verify_transfer(transfer_reference)
            except Exception:
                logger.error(f"Payout {payout.id}: duplicate transfer reference, status verify failed", exc_info=True)
                raise HTTPException(
                    status_code=502,
                    detail="Transfer status could not be confirmed — check Paystack dashboard before retrying",
                )
            if transfer.get("status") != "success":
                # Still pending/processing on Paystack's side. Leave the
                # payout row as-is (NOT failed) so it isn't picked up for
                # another automatic retry while the original is in flight.
                raise HTTPException(
                    status_code=409,
                    detail=f"Transfer already in progress (status: {transfer.get('status')})",
                )
        else:
            payout.status = PayoutStatus.FAILED.value
            db.commit()
            raise HTTPException(status_code=502, detail="Paystack transfer failed")

    payout.status = PayoutStatus.SENT.value
    payout.paystack_transfer_code = transfer.get("transfer_code")
    payout.sent_at = utcnow()
    db.commit()
    db.refresh(payout)
    return payout


@router.get("/")
def list_payouts(
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    admin: User = Depends(get_current_superadmin),
    db: Session = Depends(get_db),
):
    q = db.query(Payout)
    if status:
        q = q.filter(Payout.status == status)
    total = q.count()
    payouts = q.order_by(Payout.created_at.desc()).offset((page - 1) * limit).limit(limit).all()
    clinic_ids = [p.hospital_id for p in payouts]
    clinics = {c.id: c for c in db.query(Clinic).filter(Clinic.id.in_(clinic_ids)).all()} if clinic_ids else {}
    return {
        "items": [serialize_payout(p, clinics.get(p.hospital_id)) for p in payouts],
        "total": total,
        "page": page,
        "limit": limit,
    }


@router.post("/{payout_id}/send")
async def send_payout(
    payout_id: str,
    admin: User = Depends(get_current_superadmin),
    db: Session = Depends(get_db),
):
    payout = await send_payout_to_hospital(payout_id, db)
    return {"payout": serialize_payout(payout)}
