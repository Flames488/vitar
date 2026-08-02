"""
Vitar — Referrals Endpoints (Refer & Earn)

NEW FILE. Read-only from the dashboard's perspective — referral state
only changes server-side, via signup (auth.py) and the Paystack
payment-confirmation flow (billing_service.py). Mounted at
/api/v1/referrals.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_clinic
from app.core.config import settings
from app.models.models import Clinic, Referral, ReferralStatus
from app.services.referral_service import get_or_create_referral_code

router = APIRouter()


@router.get("/me")
def get_my_referral_link(
    clinic: Clinic = Depends(get_current_clinic),
    db: Session = Depends(get_db),
):
    code = get_or_create_referral_code(clinic, db)
    link = f"{settings.FRONTEND_URL.rstrip('/')}/register?ref={code}"
    return {"referral_code": code, "referral_link": link}


@router.get("/stats")
def get_referral_stats(
    clinic: Clinic = Depends(get_current_clinic),
    db: Session = Depends(get_db),
):
    referrals = db.query(Referral).filter(Referral.referrer_clinic_id == clinic.id).all()
    return {
        "sent": len(referrals),
        "converted": sum(1 for r in referrals if r.status in (ReferralStatus.PAID, ReferralStatus.CREDITED)),
        "discounts_earned": sum(1 for r in referrals if r.status == ReferralStatus.CREDITED),
        "discounts_pending": sum(1 for r in referrals if r.status == ReferralStatus.PAID),
    }
