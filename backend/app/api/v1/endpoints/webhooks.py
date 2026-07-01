"""
Vitar — Webhook Endpoints (HARDENED + Subscription Analytics)
Adds subscription lifecycle tracking to all Paystack and Stripe events.

Events tracked:
  subscription_started   — charge.success / checkout.session.completed
  subscription_upgraded  — customer.subscription.updated (plan change)
  subscription_cancelled — subscription.disable / customer.subscription.deleted
  payment_failed         — invoice.payment_failed / charge.failed
  trial_started          — customer.subscription.trial_will_end (Stripe)
  trial_completed        — trialing → active transition
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Request, HTTPException, Header, Depends
from sqlalchemy.orm import Session
import logging
import json

from app.core.utils import utcnow
from app.core.database import get_db
from app.core.logging import get_logger, log_payment_event
from app.core.idempotency import is_webhook_processed
from app.core.subscription_analytics import (
    subscription_started,
    subscription_upgraded,
    subscription_cancelled,
    payment_failed,
    trial_started,
    trial_completed,
)
from app.services.billing_service import billing_service
from app.services.email_service import send_subscription_activated_email
from app.services.geo_service import format_currency

router = APIRouter()
logger = get_logger(__name__)


# ─── Paystack Webhook ────────────────────────────────────────────────────────

@router.post("/paystack")
async def paystack_webhook(
    request: Request,
    x_paystack_signature: str = Header(None),
    db: Session = Depends(get_db),
):
    body = await request.body()

    if x_paystack_signature:
        if not billing_service.paystack.verify_webhook(body, x_paystack_signature):
            logger.warning("Paystack webhook signature mismatch", extra={"path": str(request.url)})
            raise HTTPException(status_code=400, detail="Invalid signature")
    else:
        from app.core.config import settings
        if settings.ENVIRONMENT == "production":
            logger.error("Paystack webhook received without signature in production")
            raise HTTPException(status_code=400, detail="Missing signature")

    try:
        payload = json.loads(body)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    event = payload.get("event", "")
    data = payload.get("data", {})
    event_id = data.get("id") or data.get("reference") or payload.get("id", "")

    if event_id and is_webhook_processed("paystack", f"{event}:{event_id}"):
        logger.info(f"Paystack webhook already processed: {event}:{event_id}")
        return {"status": "ok", "duplicate": True}

    logger.info("Paystack webhook received", extra={"event": event, "event_id": event_id})

    metadata = data.get("metadata") or data.get("extra_data") or {}
    clinic_id = metadata.get("clinic_id")
    plan = metadata.get("plan")
    amount = float(data.get("amount", 0)) / 100  # kobo → naira
    currency = data.get("currency", "NGN")

    if event == "charge.success":
        reference = data.get("reference", "")
        from app.models.models import PendingSubscriptionPayment
        is_automated = bool(reference) and db.query(PendingSubscriptionPayment).filter(
            PendingSubscriptionPayment.paystack_reference == reference
        ).first() is not None

        if is_automated:
            # Smart payment system: automated bank-transfer charge created via
            # /billing/subscribe. Amount/reference are verified inside.
            success = await billing_service.finalize_paystack_payment(reference, data, db)
            if success:
                await _send_activation_email(data, "paystack", db)
                subscription_started(
                    clinic_id=clinic_id or _extract_clinic_id(data, db),
                    plan=plan or "unknown",
                    amount=amount,
                    currency=currency,
                    provider="paystack",
                )
        else:
            # Legacy / manual bank-transfer flow (unchanged).
            success = await billing_service.handle_payment_success("paystack", data, db)
            if success:
                await _send_activation_email(data, "paystack", db)
                subscription_started(
                    clinic_id=clinic_id or _extract_clinic_id(data, db),
                    plan=plan or "unknown",
                    amount=amount,
                    currency=currency,
                    provider="paystack",
                )

    elif event == "subscription.create":
        log_payment_event("subscription_created", "paystack", data.get("subscription_code"), clinic_id)
        subscription_started(
            clinic_id=clinic_id,
            plan=plan or data.get("plan", {}).get("name", "unknown"),
            amount=amount,
            currency=currency,
            provider="paystack",
        )

    elif event == "subscription.disable":
        await _handle_cancellation("paystack", data.get("subscription_code"), db)
        subscription_cancelled(
            clinic_id=clinic_id,
            plan=plan or "unknown",
            reason="paystack_subscription_disabled",
        )

    elif event in ("invoice.payment_failed", "charge.failed"):
        await _handle_payment_failed("paystack", data, db)
        payment_failed(
            clinic_id=clinic_id,
            plan=plan or "unknown",
            amount=amount,
            currency=currency,
            provider="paystack",
            reason=data.get("gateway_response", "charge_failed"),
        )

    return {"status": "ok"}


# ─── Stripe Webhook ──────────────────────────────────────────────────────────

@router.post("/stripe")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(None, alias="stripe-signature"),
    db: Session = Depends(get_db),
):
    body = await request.body()

    from app.core.config import settings
    webhook_secret = getattr(settings, "STRIPE_WEBHOOK_SECRET", "")

    if stripe_signature and webhook_secret:
        try:
            import stripe  # type: ignore
            event_obj = stripe.Webhook.construct_event(body, stripe_signature, webhook_secret)
        except Exception as exc:
            logger.warning(f"Stripe webhook validation failed: {exc}")
            raise HTTPException(status_code=400, detail="Invalid Stripe signature")
    else:
        try:
            event_obj = json.loads(body)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON")

    event_type = event_obj.get("type", "") if isinstance(event_obj, dict) else event_obj.type
    event_id = (event_obj.get("id", "") if isinstance(event_obj, dict) else event_obj.id)

    if event_id and is_webhook_processed("stripe", f"{event_type}:{event_id}"):
        return {"status": "ok", "duplicate": True}

    logger.info("Stripe webhook received", extra={"event": event_type, "event_id": event_id})

    data_obj = event_obj.get("data", {}).get("object", {}) if isinstance(event_obj, dict) else event_obj.data.object
    meta = data_obj.get("metadata", {}) if isinstance(data_obj, dict) else {}
    clinic_id = meta.get("clinic_id")
    plan = meta.get("plan")

    if event_type == "checkout.session.completed":
        success = await billing_service.handle_payment_success("stripe", data_obj, db)
        if success:
            await _send_activation_email(data_obj, "stripe", db)
            amount = float(data_obj.get("amount_total", 0)) / 100
            currency = (data_obj.get("currency") or "usd").upper()
            subscription_started(
                clinic_id=clinic_id,
                plan=plan or "unknown",
                amount=amount,
                currency=currency,
                provider="stripe",
            )

    elif event_type == "customer.subscription.updated":
        # Detect plan upgrade vs cancellation flag
        prev = event_obj.get("data", {}).get("previous_attributes", {}) if isinstance(event_obj, dict) else {}
        old_plan = (prev.get("items", {}).get("data", [{}])[0]
                    .get("price", {}).get("nickname") or "unknown")
        new_plan = plan or "unknown"
        if old_plan != new_plan and old_plan != "unknown":
            subscription_upgraded(
                clinic_id=clinic_id,
                old_plan=old_plan,
                new_plan=new_plan,
                provider="stripe",
            )

    elif event_type == "customer.subscription.deleted":
        await _handle_cancellation("stripe", data_obj.get("id"), db)
        subscription_cancelled(
            clinic_id=clinic_id,
            plan=plan or "unknown",
            reason="stripe_subscription_deleted",
        )

    elif event_type == "invoice.payment_failed":
        await _handle_payment_failed("stripe", data_obj, db)
        amount = float(data_obj.get("amount_due", 0)) / 100
        currency = (data_obj.get("currency") or "usd").upper()
        payment_failed(
            clinic_id=clinic_id,
            plan=plan or "unknown",
            amount=amount,
            currency=currency,
            provider="stripe",
            reason=data_obj.get("last_payment_error", {}).get("message", "invoice_payment_failed"),
        )

    elif event_type == "customer.subscription.trial_will_end":
        # Stripe fires this 3 days before trial ends
        trial_started(clinic_id=clinic_id, plan=plan or "trial")

    return {"status": "ok"}


# ─── Shared helpers ──────────────────────────────────────────────────────────

async def _send_activation_email(data: dict, provider: str, db: Session):
    try:
        metadata = data.get("metadata") or data.get("extra_data") or {}
        clinic_id = metadata.get("clinic_id")
        if not clinic_id:
            return
        from app.models.models import Clinic, User
        clinic = db.query(Clinic).filter(Clinic.id == clinic_id).first()
        if not clinic:
            return
        user = db.query(User).filter(User.id == clinic.owner_id).first()
        if user:
            plan = metadata.get("plan", "")
            amount_raw = data.get("amount", 0)
            amount_display = format_currency(float(amount_raw) / 100, data.get("currency", "NGN"))
            await send_subscription_activated_email(user.email, clinic.name, plan, amount_display)
    except Exception as exc:
        logger.warning(f"_send_activation_email failed: {exc}")


async def _handle_cancellation(provider: str, subscription_id: str, db: Session):
    try:
        from app.models.models import Subscription, SubscriptionStatus
        sub = db.query(Subscription).filter(
            Subscription.provider_subscription_id == subscription_id
        ).first()
        if sub:
            sub.status = SubscriptionStatus.CANCELLED
            sub.cancel_at_period_end = True
            db.commit()
            log_payment_event("subscription_cancelled", provider, subscription_id, str(sub.clinic_id))
    except Exception as exc:
        logger.error(f"_handle_cancellation failed: {exc}")


async def _handle_payment_failed(provider: str, data: dict, db: Session):
    try:
        metadata = data.get("metadata") or {}
        clinic_id = metadata.get("clinic_id")
        log_payment_event("payment_failed", provider, data.get("id", ""), clinic_id)
    except Exception as exc:
        logger.error(f"_handle_payment_failed failed: {exc}")


def _extract_clinic_id(data: dict, db: Session) -> str:
    """Last-resort: look up clinic by Paystack customer email."""
    try:
        email = data.get("customer", {}).get("email", "")
        if email:
            from app.models.models import User
            user = db.query(User).filter(User.email == email).first()
            if user:
                return str(user.clinic_id or "")
    except Exception:
        pass
    return ""
