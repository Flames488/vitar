"""
Vitar v5 - Billing Endpoints
Subscription management, plan info, payment initiation.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Header
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.core.database import get_db
from app.core.security import get_current_user, get_current_clinic
from app.models.models import Clinic, Subscription, SubscriptionPlan, SubscriptionStatus
from app.services.billing_service import billing_service, get_plan_pricing, PLANS
from app.services.geo_service import get_all_plans_for_currency, get_payment_provider
from app.services.trial_guard import get_trial_status
from app.core.config import settings

router = APIRouter()


class SubscribeRequest(BaseModel):
    plan: str
    billing_cycle: str = "monthly"


class UpgradeRequest(BaseModel):
    plan: str
    billing_cycle: str = "monthly"


# ─── Paystack Webhook Compatibility Alias ────────────────────────────────────

@router.post("/webhook/paystack")
async def paystack_billing_webhook(
    request: Request,
    x_paystack_signature: str = Header(None),
    db: Session = Depends(get_db),
):
    """
    Backwards-compatible deployment URL for Paystack:
    /api/v1/billing/webhook/paystack.

    The canonical handler remains /api/v1/webhooks/paystack; this alias keeps
    the hosting guide and Paystack dashboard URL working without duplicating
    payment logic.
    """
    from app.api.v1.endpoints.webhooks import paystack_webhook

    return await paystack_webhook(
        request=request,
        x_paystack_signature=x_paystack_signature,
        db=db,
    )


# ─── Plan Listing ─────────────────────────────────────────────────────────────

@router.get("/plans")
async def get_plans(
    currency: str = "NGN",
):
    """
    Returns all plans with pricing for a given currency.
    Frontend calls this after geo detection.
    """
    plans = get_all_plans_for_currency(currency)
    return {"plans": plans, "currency": currency}


# ─── Current Subscription ─────────────────────────────────────────────────────

@router.get("/subscription")
def get_subscription(
    clinic=Depends(get_current_clinic),
    db: Session = Depends(get_db),
):
    sub = clinic.subscription
    trial = get_trial_status(clinic)

    return {
        "subscription": {
            "plan": sub.plan if sub else "trial",
            "status": sub.status if sub else "trialing",
            "current_period_end": sub.current_period_end.isoformat() if sub and sub.current_period_end else None,
            "cancel_at_period_end": sub.cancel_at_period_end if sub else False,
            "amount": float(sub.amount) if sub and sub.amount else 0,
            "currency": sub.currency if sub else clinic.currency,
        },
        "trial": trial,
        "clinic": {
            "id": clinic.id,
            "country": clinic.country,
            "currency": clinic.currency,
        },
    }


# ─── Initiate Subscription ────────────────────────────────────────────────────

@router.post("/subscribe")
async def subscribe(
    body: SubscribeRequest,
    clinic=Depends(get_current_clinic),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if body.plan not in PLANS:
        raise HTTPException(status_code=400, detail=f"Invalid plan: {body.plan}")

    if body.plan == "enterprise":
        raise HTTPException(
            status_code=400,
            detail="Enterprise plan requires contacting sales. Please email sales@vitar.health",
        )

    # Smart payment system: generates a dedicated Paystack bank-transfer
    # charge. The clinic transfers, Paystack webhooks us, and the
    # subscription activates automatically — no admin step required.
    try:
        result = await billing_service.create_automated_subscription_payment(
            clinic_id=clinic.id,
            plan=body.plan,
            billing_cycle=body.billing_cycle,
            user_email=current_user.email,
            db=db,
        )
    except Exception as exc:
        from app.core.logging import get_logger
        _log = get_logger(__name__)
        _log.error("subscribe: automated payment init failed", exc_info=exc,
                   extra={"clinic_id": str(clinic.id), "plan": body.plan})
        raise HTTPException(status_code=502, detail="Payment provider unavailable. Please try again.")
    return result


# ─── Payment Status Polling (smart payment system) ────────────────────────────

@router.get("/payment-status/{reference}")
def get_payment_status(
    reference: str,
    clinic=Depends(get_current_clinic),
    db: Session = Depends(get_db),
):
    """Polled by the Billing page every 10s while a payment is pending."""
    return billing_service.get_payment_status(reference, db)


# ─── Manual Plan Activation (superadmin only) ─────────────────────────────────

class ActivateRequest(BaseModel):
    clinic_id: str
    plan: str
    billing_cycle: str = "monthly"
    reference: Optional[str] = None

@router.post("/activate")
def activate_subscription(
    body: ActivateRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Superadmin endpoint: manually activate a clinic's plan after confirming
    their bank transfer. Called from the superadmin subscriptions panel.
    """
    from app.models.models import Subscription, SubscriptionStatus, PaymentProvider
    from app.core.utils import utcnow
    from datetime import timedelta

    # Only superadmins can activate
    if not getattr(current_user, "is_superadmin", False):
        raise HTTPException(status_code=403, detail="Superadmin only")

    clinic = db.query(Clinic).filter(Clinic.id == body.clinic_id).first()
    if not clinic:
        raise HTTPException(status_code=404, detail="Clinic not found")

    if body.plan not in PLANS:
        raise HTTPException(status_code=400, detail=f"Invalid plan: {body.plan}")

    pricing = get_plan_pricing(body.plan, clinic.currency or "NGN")
    amount = pricing["monthly"] if body.billing_cycle == "monthly" else pricing["annual"]

    now = utcnow()
    period_end = now + timedelta(days=30 if body.billing_cycle == "monthly" else 365)

    sub = db.query(Subscription).filter(Subscription.clinic_id == body.clinic_id).first()
    if sub:
        sub.plan = body.plan
        sub.status = SubscriptionStatus.ACTIVE
        sub.provider = PaymentProvider.PAYSTACK  # nominal
        sub.provider_subscription_id = body.reference or f"manual-{body.clinic_id[:8]}"
        sub.current_period_start = now
        sub.current_period_end = period_end
        sub.amount = amount
        sub.cancel_at_period_end = False
    else:
        sub = Subscription(
            clinic_id=body.clinic_id,
            plan=body.plan,
            status=SubscriptionStatus.ACTIVE,
            provider=PaymentProvider.PAYSTACK,
            provider_subscription_id=body.reference or f"manual-{body.clinic_id[:8]}",
            current_period_start=now,
            current_period_end=period_end,
            amount=amount,
            currency=clinic.currency or "NGN",
        )
        db.add(sub)

    db.commit()
    return {
        "message": f"{clinic.name} activated on {body.plan} plan",
        "plan": body.plan,
        "period_end": period_end.isoformat(),
    }


# ─── Cancel Subscription ──────────────────────────────────────────────────────

@router.post("/cancel")
async def cancel_subscription(
    clinic=Depends(get_current_clinic),
    db: Session = Depends(get_db),
):
    sub = clinic.subscription
    if not sub or sub.status != SubscriptionStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="No active subscription to cancel")

    if sub.provider and sub.provider.value == "stripe" and sub.provider_subscription_id:
        await billing_service.stripe.cancel_subscription(sub.provider_subscription_id)
    elif sub.provider and sub.provider.value == "paystack" and sub.provider_subscription_id:
        await billing_service.paystack.cancel_subscription(
            sub.provider_subscription_id, ""
        )

    sub.cancel_at_period_end = True
    db.commit()

    return {
        "message": "Subscription will cancel at end of current period",
        "period_end": sub.current_period_end.isoformat() if sub.current_period_end else None,
    }


# ─── Get Paystack Banks ────────────────────────────────────────────────────────

@router.get("/banks")
async def get_banks(
    clinic=Depends(get_current_clinic),
):
    if clinic.country != "NG":
        return {"banks": []}
    banks = await billing_service.paystack.get_banks()
    return {"banks": banks}


# ─── Create Paystack Subaccount (for patient payments) ───────────────────────

class SubaccountRequest(BaseModel):
    bank_code: str
    account_number: str

@router.post("/setup-subaccount")
async def setup_subaccount(
    body: SubaccountRequest,
    clinic=Depends(get_current_clinic),
    db: Session = Depends(get_db),
):
    if clinic.country != "NG":
        raise HTTPException(status_code=400, detail="Subaccounts only available for Nigerian clinics")

    try:
        result = await billing_service.paystack.create_subaccount(
            business_name=clinic.name,
            bank_code=body.bank_code,
            account_number=body.account_number,
            percentage_charge=1.5,
        )
    except HTTPException:
        raise
    except Exception as exc:
        from app.core.logging import get_logger
        _log = get_logger(__name__)
        _log.error("setup_subaccount: paystack error", exc_info=exc,
                   extra={"clinic_id": str(clinic.id)})
        raise HTTPException(status_code=502, detail="Payment provider unavailable. Please try again.")

    clinic.paystack_subaccount_code = result["subaccount_code"]
    clinic.paystack_bank_name = result["bank_name"]
    clinic.paystack_account_number = body.account_number
    clinic.patient_payment_enabled = True
    db.commit()

    return {"message": "Payment account configured", "subaccount_code": result["subaccount_code"]}
