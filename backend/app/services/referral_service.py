"""
Vitar — Referral Service (Refer & Earn)

Handles referral-code generation, signup attribution, and the discount
lifecycle: a referred clinic's first successful subscription payment
earns the referrer a 10% discount, applied to the referrer's next
invoice (capped at one discount per invoice cycle).

The three entry points called from hot paths elsewhere (signup,
checkout-amount computation, payment confirmation) never raise — a bug
here must never block registration or break subscription billing.
"""
import secrets
from typing import Optional

from sqlalchemy.orm import Session

from app.core.utils import utcnow
from app.core.logging import get_logger, log_payment_event

logger = get_logger(__name__)

REFERRAL_DISCOUNT_PCT = 0.10


def _generate_code(db: Session) -> str:
    from app.models.models import Clinic

    for _ in range(10):
        code = secrets.token_hex(4).upper()  # 8 chars, e.g. "A1B2C3D4"
        if not db.query(Clinic.id).filter(Clinic.referral_code == code).first():
            return code
    raise Exception("Could not generate a unique referral code after 10 attempts")


def get_or_create_referral_code(clinic, db: Session) -> str:
    """Returns the clinic's persistent referral code, generating one on first call."""
    if clinic.referral_code:
        return clinic.referral_code
    clinic.referral_code = _generate_code(db)
    db.commit()
    db.refresh(clinic)
    return clinic.referral_code


def _is_self_referral_by_owner(referrer_clinic, referred_clinic, db: Session) -> bool:
    from app.models.models import User

    referrer_owner = db.query(User).filter(User.id == referrer_clinic.owner_id).first()
    referred_owner = db.query(User).filter(User.id == referred_clinic.owner_id).first()
    if not referrer_owner or not referred_owner:
        return False
    if referrer_owner.email and referrer_owner.email == referred_owner.email:
        return True
    if referrer_owner.phone and referrer_owner.phone == referred_owner.phone:
        return True
    return False


def attach_referral_on_signup(referred_clinic, referral_code: Optional[str], db: Session) -> None:
    """
    Called right after a new clinic is created at registration. Looks up
    the referrer by code and records a Referral row. A missing/invalid
    code, self-referral, or any internal error just means no (usable)
    referral is attached — signup must always proceed regardless.
    """
    if not referral_code:
        return
    try:
        from app.models.models import Clinic, Referral, ReferralStatus

        code = referral_code.strip().upper()
        referrer = db.query(Clinic).filter(Clinic.referral_code == code).first()
        if not referrer or referrer.id == referred_clinic.id:
            return

        status = ReferralStatus.SIGNED_UP
        if _is_self_referral_by_owner(referrer, referred_clinic, db):
            status = ReferralStatus.EXPIRED
            logger.warning(
                "Referral blocked — self-referral detected at signup",
                extra={"referrer_clinic_id": referrer.id, "referred_clinic_id": referred_clinic.id},
            )

        db.add(Referral(
            referrer_clinic_id=referrer.id,
            referred_clinic_id=referred_clinic.id,
            referral_code=code,
            status=status,
        ))
        db.commit()
    except Exception:
        db.rollback()
        logger.error("attach_referral_on_signup failed — continuing signup without referral", exc_info=True)


def record_referral_payment(referred_clinic_id: str, db: Session) -> None:
    """
    Called from BillingService.finalize_paystack_payment right after a
    clinic's FIRST successful subscription payment is confirmed. Marks
    the referral 'paid', making a 10% discount available for the
    referrer's next invoice. Swallows all errors — must never block
    payment confirmation.
    """
    try:
        from app.models.models import Clinic, Referral, ReferralStatus

        referral = db.query(Referral).filter(
            Referral.referred_clinic_id == referred_clinic_id,
            Referral.status == ReferralStatus.SIGNED_UP,
        ).first()
        if not referral:
            return

        referrer = db.query(Clinic).filter(Clinic.id == referral.referrer_clinic_id).first()
        referred = db.query(Clinic).filter(Clinic.id == referred_clinic_id).first()

        # Payment-details self-referral check: same Paystack subaccount
        # (bank account) behind two "different" clinics.
        if (
            referrer and referred and referrer.paystack_subaccount_code
            and referrer.paystack_subaccount_code == referred.paystack_subaccount_code
        ):
            referral.status = ReferralStatus.EXPIRED
            db.commit()
            logger.warning(
                "Referral blocked — matching payment details (self-referral)",
                extra={"referral_id": referral.id},
            )
            return

        referral.status = ReferralStatus.PAID
        referral.paid_at = utcnow()
        db.commit()

        log_payment_event(
            "referral_earned", "paystack", None, referral.referrer_clinic_id,
            0, "success", extra={"referral_id": referral.id, "referred_clinic_id": referred_clinic_id},
        )
    except Exception:
        db.rollback()
        logger.error("record_referral_payment failed", exc_info=True)


def apply_referral_discount(amount, clinic_id: str, db: Session):
    """
    Called from BillingService.create_automated_subscription_payment right
    after the plan's base price is computed, before the PendingSubscription
    Payment row (and therefore the Paystack charge / exact-match target) is
    built. If this clinic (as a referrer) has an earned-but-unredeemed 10%
    discount, applies it and marks that one credit 'credited' — capped at
    one discount per invoice cycle even if multiple credits are pending
    (oldest first). Returns the (possibly discounted) amount; on any error
    returns the original amount unchanged so a bug here can never block
    checkout.
    """
    try:
        from app.models.models import Referral, ReferralStatus

        referral = (
            db.query(Referral)
            .filter(Referral.referrer_clinic_id == clinic_id, Referral.status == ReferralStatus.PAID)
            .order_by(Referral.paid_at.asc())
            .first()
        )
        if not referral:
            return amount

        discounted = round(float(amount) * (1 - REFERRAL_DISCOUNT_PCT), 2)

        referral.status = ReferralStatus.CREDITED
        referral.credited_at = utcnow()
        db.commit()

        log_payment_event(
            "referral_discount_applied", "paystack", None, clinic_id,
            discounted, "success", extra={"referral_id": referral.id, "original_amount": float(amount)},
        )
        return discounted
    except Exception:
        db.rollback()
        logger.error("apply_referral_discount failed — charging full price", exc_info=True)
        return amount
