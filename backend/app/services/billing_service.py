"""
Vitar - Billing Service
Two payment flows:
  1. Clinic subscription → Vitar owner  : bank transfer (no Paystack account needed)
  2. Patient → Clinic                   : bank transfer (built in SettingsPage)

Paystack is kept for webhook verification and future use, but the primary
subscription flow is now manual bank transfer + owner activation.
"""

import httpx
import hmac
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any

from app.core.utils import utcnow
from app.core.config import settings
from app.core.logging import get_logger, log_payment_event
from app.services.geo_service import PRICING_TIERS
from app.core.circuit_breaker import billing_breaker

logger = get_logger(__name__)

PLANS = {
    "basic": {
        "name": "Basic",
        "max_doctors": 2,
        "max_bookings_month": 200,
        "features": [
            "Up to 2 doctors", "200 bookings/month",
            "SMS & Email reminders", "Basic no-show analytics", "Public booking page",
        ],
    },
    "pro": {
        "name": "Pro",
        "max_doctors": 10,
        "max_bookings_month": 2000,
        "features": [
            "Up to 10 doctors", "2,000 bookings/month",
            "SMS, WhatsApp & Email", "AI no-show prediction",
            "Smart reminder engine", "Auto slot refill",
            "Advanced analytics", "Waiting list management", "Priority support",
        ],
    },
    "enterprise": {
        "name": "Enterprise",
        "max_doctors": -1,
        "max_bookings_month": -1,
        "features": [
            "Unlimited doctors", "Unlimited bookings", "All Pro features",
            "Dedicated account manager", "Custom integrations", "SLA guarantee",
        ],
    },
}


def get_plan_pricing(plan: str, currency: str) -> Dict[str, Any]:
    tiers = PRICING_TIERS.get(currency, PRICING_TIERS["NGN"])
    plan_price = tiers.get(plan, {})
    return {
        "plan": plan,
        "currency": currency,
        "monthly": plan_price.get("monthly", 0),
        "annual": plan_price.get("annual", 0),
        "annual_savings_percent": plan_price.get("annual_savings_percent", 17),
        **PLANS.get(plan, {}),
    }


class PaystackBilling:
    """Kept for webhook verification. Checkout is now bank transfer."""
    BASE = "https://api.paystack.co"

    def __init__(self):
        self.key = settings.PAYSTACK_SECRET_KEY
        self.headers = {"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"}

    async def initialize_transaction(self, email, amount_kobo, metadata, callback_url) -> Dict:
        """
        FIX: removed empty plan_code (Paystack rejects plan="").
        FIX: metadata key is "metadata" not "extra_data".
        """
        payload = {
            "email": email,
            "amount": amount_kobo,
            "metadata": metadata,          # ← was "extra_data" — Paystack ignores that key
            "callback_url": callback_url,
        }
        # Do NOT include "plan": "" — Paystack rejects empty plan strings
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                f"{self.BASE}/transaction/initialize",
                headers=self.headers,
                json=payload,
            )
            data = resp.json()
            if data.get("status"):
                return {
                    "authorization_url": data["data"]["authorization_url"],
                    "reference": data["data"]["reference"],
                    "access_code": data["data"]["access_code"],
                }
            raise Exception(f"Paystack initialize failed: {data.get('message')}")

    async def verify_transaction(self, reference: str, retries: int = 3) -> Dict:
        last_error = None
        for attempt in range(retries):
            try:
                async with httpx.AsyncClient(timeout=20) as client:
                    resp = await client.get(
                        f"{self.BASE}/transaction/verify/{reference}",
                        headers=self.headers,
                    )
                    data = resp.json()
                    if data.get("status") and data["data"]["status"] == "success":
                        return {"verified": True, "data": data["data"]}
                    return {"verified": False, "data": data.get("data", {})}
            except Exception as e:
                last_error = e
                if attempt < retries - 1:
                    import asyncio
                    await asyncio.sleep(2 ** attempt)
        logger.error(f"Paystack verify failed after {retries} retries: {last_error}")
        return {"verified": False, "error": str(last_error)}

    async def initiate_bank_transfer_charge(
        self, email: str, amount_kobo: int, reference: str, metadata: Dict
    ) -> Dict:
        """
        Smart payment system: Paystack's "Pay with Transfer" charge.
        Generates a dedicated, single-use virtual account for this exact
        charge. Paystack fires a `charge.success` webhook automatically
        once the transfer lands — no polling of Paystack required, no
        manual admin confirmation needed.

        Docs: POST /charge with a `bank_transfer` channel hint.
        """
        payload = {
            "email": email,
            "amount": amount_kobo,
            "reference": reference,
            "metadata": metadata,
            "bank_transfer": {},  # use Paystack defaults for account expiry
        }
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                f"{self.BASE}/charge",
                headers=self.headers,
                json=payload,
            )
            data = resp.json()
            if not data.get("status"):
                raise Exception(f"Paystack bank-transfer charge failed: {data.get('message')}")

            inner = data["data"]
            transfer = inner.get("bank_transfer") or {}
            return {
                "reference": inner.get("reference", reference),
                "bank_name": transfer.get("bank_name") or transfer.get("name"),
                "account_number": transfer.get("account_number"),
                "account_name": transfer.get("account_name", "Vitar Health"),
                "account_expires_at": transfer.get("account_expires_at"),
                "raw": inner,
            }

    async def cancel_subscription(self, subscription_code: str, token: str) -> bool:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                f"{self.BASE}/subscription/disable",
                headers=self.headers,
                json={"code": subscription_code, "token": token},
            )
            return resp.json().get("status", False)

    async def create_subaccount(self, business_name, bank_code, account_number, percentage_charge=0) -> Dict:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                f"{self.BASE}/subaccount",
                headers=self.headers,
                json={
                    "business_name": business_name,
                    "settlement_bank": bank_code,
                    "account_number": account_number,
                    "percentage_charge": percentage_charge,
                },
            )
            data = resp.json()
            if data.get("status"):
                return {
                    "subaccount_code": data["data"]["subaccount_code"],
                    "bank_name": data["data"]["settlement_bank"],
                }
            raise Exception(f"Subaccount creation failed: {data.get('message')}")

    async def get_banks(self) -> list:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(f"{self.BASE}/bank", headers=self.headers)
            data = resp.json()
            return [
                {"name": b["name"], "code": b["code"]}
                for b in data.get("data", [])
            ] if data.get("status") else []

    def verify_webhook(self, payload: bytes, signature: str) -> bool:
        if not settings.PAYSTACK_WEBHOOK_SECRET:
            logger.warning("PAYSTACK_WEBHOOK_SECRET not set — cannot verify Paystack webhook")
            return settings.ENVIRONMENT != "production"
        expected = hmac.new(
            settings.PAYSTACK_WEBHOOK_SECRET.encode(),
            payload,
            hashlib.sha512,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)


class StripeBilling:
    BASE = "https://api.stripe.com/v1"

    def __init__(self):
        self.key = settings.STRIPE_SECRET_KEY

    def _headers(self):
        import base64
        encoded = base64.b64encode(f"{self.key}:".encode()).decode()
        return {"Authorization": f"Basic {encoded}", "Content-Type": "application/x-www-form-urlencoded"}

    async def cancel_subscription(self, subscription_id: str) -> bool:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.delete(
                f"{self.BASE}/subscriptions/{subscription_id}",
                headers=self._headers(),
            )
            return resp.status_code == 200

    def verify_webhook(self, payload: bytes, signature: str) -> Dict:
        if not settings.STRIPE_WEBHOOK_SECRET:
            logger.warning("STRIPE_WEBHOOK_SECRET not set — skipping verification")
            return {"valid": True}
        try:
            import time
            parts = {p.split("=")[0]: p.split("=")[1] for p in signature.split(",")}
            ts = parts.get("t", "0")
            sig = parts.get("v1", "")
            signed_payload = f"{ts}.{payload.decode()}"
            expected = hmac.new(
                settings.STRIPE_WEBHOOK_SECRET.encode(),
                signed_payload.encode(),
                hashlib.sha256,
            ).hexdigest()
            if not hmac.compare_digest(expected, sig):
                return {"valid": False, "error": "Signature mismatch"}
            if abs(time.time() - int(ts)) > 300:
                return {"valid": False, "error": "Timestamp too old"}
            return {"valid": True}
        except Exception as e:
            return {"valid": False, "error": str(e)}


class BillingService:
    def __init__(self):
        self.paystack = PaystackBilling()
        self.stripe = StripeBilling()

    def get_owner_bank_details(self) -> Optional[Dict]:
        """
        Returns Vitar owner bank details from env vars.
        Clinics transfer their subscription fee directly to this account.
        No Paystack account required on the clinic side.
        """
        bank_name = getattr(settings, "OWNER_BANK_NAME", "")
        account_number = getattr(settings, "OWNER_ACCOUNT_NUMBER", "")
        account_name = getattr(settings, "OWNER_ACCOUNT_NAME", "Vitar Health")
        if not bank_name or not account_number:
            return None
        return {
            "bank_name": bank_name,
            "account_number": account_number,
            "account_name": account_name,
        }

    async def initiate_subscription(
        self, clinic_id, plan, billing_cycle, country, user_email, frontend_url, db
    ) -> Dict:
        """
        Returns bank transfer payment instructions for the clinic to pay Vitar.
        No external payment provider call — no failure possible.
        """
        from app.models.models import Clinic
        clinic = db.query(Clinic).filter(Clinic.id == clinic_id).first()
        if not clinic:
            raise Exception("Clinic not found")

        pricing = get_plan_pricing(plan, clinic.currency or "NGN")
        amount = pricing["monthly"] if billing_cycle == "monthly" else pricing["annual"]
        currency_symbol = "₦" if (clinic.currency or "NGN") == "NGN" else clinic.currency

        bank = self.get_owner_bank_details()

        log_payment_event(
            "bank_transfer_initiated", "bank_transfer", None,
            clinic_id, amount, "pending",
        )

        return {
            "payment_method": "bank_transfer",
            "plan": plan,
            "billing_cycle": billing_cycle,
            "amount": amount,
            "currency": clinic.currency or "NGN",
            "currency_symbol": currency_symbol,
            "bank_details": bank,
            "reference": f"VITAR-{clinic_id[:8].upper()}-{plan.upper()}",
            "instructions": (
                f"Transfer {currency_symbol}{amount:,} to the account below. "
                f"Use your reference code as the payment description. "
                f"Your plan will be activated within 24 hours of payment confirmation."
            ),
        }

    async def create_automated_subscription_payment(
        self, clinic_id, plan, billing_cycle, user_email, db
    ) -> Dict:
        """
        Smart payment system: generates a Paystack dedicated bank-transfer
        charge for the clinic's chosen plan. A PendingSubscriptionPayment
        row tracks the session so the frontend can poll for status and so
        the webhook handler knows exactly what to activate once paid.
        """
        from app.models.models import Clinic, PendingSubscriptionPayment, PendingPaymentStatus
        from app.core.cache import cache

        clinic = db.query(Clinic).filter(Clinic.id == clinic_id).first()
        if not clinic:
            raise Exception("Clinic not found")

        currency = clinic.currency or "NGN"
        pricing = get_plan_pricing(plan, currency)
        amount = pricing["monthly"] if billing_cycle == "monthly" else pricing["annual"]
        if not amount:
            raise Exception(f"Plan {plan} has no fixed price for automated checkout")
        currency_symbol = "₦" if currency == "NGN" else currency

        reference = f"VITAR-{clinic_id[:8].upper()}-{plan.upper()}-{int(utcnow().timestamp())}"
        now = utcnow()
        expires_at = now + timedelta(minutes=35)

        pending = PendingSubscriptionPayment(
            clinic_id=clinic_id,
            subscription_plan=plan,
            billing_cycle=billing_cycle,
            amount=amount,
            currency=currency,
            paystack_reference=reference,
            status=PendingPaymentStatus.PENDING,
            expires_at=expires_at,
        )
        db.add(pending)
        db.commit()

        try:
            charge = await self.paystack.initiate_bank_transfer_charge(
                email=user_email,
                amount_kobo=int(round(amount * 100)),
                reference=reference,
                metadata={
                    "clinic_id": clinic_id,
                    "plan": plan,
                    "billing_cycle": billing_cycle,
                    "pending_payment_id": pending.id,
                },
            )
        except Exception:
            db.rollback()
            pending2 = db.query(PendingSubscriptionPayment).filter(
                PendingSubscriptionPayment.id == pending.id
            ).first()
            if pending2:
                db.delete(pending2)
                db.commit()
            raise

        pending.provider_response = charge.get("raw", {})
        db.commit()

        cache.set(f"payment_status:{reference}", {"status": "pending"}, ttl=35 * 60)

        log_payment_event("automated_payment_initiated", "paystack", reference, clinic_id, amount, "pending",
                          extra={"plan": plan})

        return {
            "payment_method": "bank_transfer",
            "plan": plan,
            "billing_cycle": billing_cycle,
            "amount": float(amount),
            "currency": currency,
            "currency_symbol": currency_symbol,
            "bank_details": {
                "bank_name": charge.get("bank_name"),
                "account_number": charge.get("account_number"),
                "account_name": charge.get("account_name") or "Vitar Health",
            },
            "reference": reference,
            "expires_at": expires_at.isoformat(),
            "status": "pending",
            "instructions": (
                f"Transfer exactly {currency_symbol}{amount:,} to the account below. "
                f"Your subscription activates automatically the moment we receive it — "
                f"no need to contact support."
            ),
        }

    def get_payment_status(self, reference: str, db) -> Dict:
        """
        Polled by the Billing page every 10s. Redis-first, DB fallback.
        Lazily flips PENDING → EXPIRED once the session's time is up.
        """
        from app.models.models import PendingSubscriptionPayment, PendingPaymentStatus
        from app.core.cache import cache

        cached = cache.get(f"payment_status:{reference}")
        if cached and cached.get("status") != "pending":
            return cached

        pending = db.query(PendingSubscriptionPayment).filter(
            PendingSubscriptionPayment.paystack_reference == reference
        ).first()
        if not pending:
            return cached or {"status": "not_found"}

        if pending.status == PendingPaymentStatus.PENDING and utcnow() > pending.expires_at:
            pending.status = PendingPaymentStatus.EXPIRED
            db.commit()
            cache.set(f"payment_status:{reference}", {"status": "expired"}, ttl=60 * 60)

        return {"status": pending.status.value}

    async def finalize_paystack_payment(self, reference: str, payload: Dict, db) -> bool:
        """
        Called from the Paystack `charge.success` webhook for the automated
        smart-payment flow. Verifies the reference belongs to a tracked
        PendingSubscriptionPayment, enforces the exact-amount rule, and
        only then activates the subscription — fully unattended.

        Returns True if the subscription was activated (caller sends the
        activation email). Returns False for anything else, including the
        legacy manual bank-transfer flow, which callers should fall back
        to `handle_payment_success` for.
        """
        from app.models.models import (
            Clinic, Subscription, SubscriptionPayment, SubscriptionStatus,
            PaymentProvider, PaymentStatus, PendingSubscriptionPayment, PendingPaymentStatus,
        )
        from app.core.cache import cache

        pending = db.query(PendingSubscriptionPayment).filter(
            PendingSubscriptionPayment.paystack_reference == reference
        ).first()
        if not pending:
            return False  # not part of the automated flow — let caller use legacy path

        if pending.status == PendingPaymentStatus.PAID:
            return True  # already activated — idempotent no-op

        if utcnow() > pending.expires_at:
            pending.status = PendingPaymentStatus.EXPIRED
            db.commit()
            cache.set(f"payment_status:{reference}", {"status": "expired"}, ttl=3600)
            log_payment_event("automated_payment_expired", "paystack", reference, str(pending.clinic_id))
            return False

        paid_amount = float(payload.get("amount", 0)) / 100
        expected_amount = float(pending.amount)
        tolerance = max(1.0, expected_amount * 0.005)  # minimal rounding tolerance

        if abs(paid_amount - expected_amount) > tolerance:
            pending.status = PendingPaymentStatus.AMOUNT_MISMATCH
            db.commit()
            cache.set(f"payment_status:{reference}", {"status": "amount_mismatch"}, ttl=3600)
            log_payment_event("automated_payment_amount_mismatch", "paystack", reference,
                              str(pending.clinic_id), paid_amount, "amount_mismatch",
                              extra={"expected_amount": expected_amount})
            return False

        clinic = db.query(Clinic).filter(Clinic.id == pending.clinic_id).first()
        if not clinic:
            logger.error(f"Automated payment for unknown clinic: {pending.clinic_id}")
            return False

        now = utcnow()
        period_end = now + timedelta(days=30 if pending.billing_cycle == "monthly" else 365)

        sub = db.query(Subscription).filter(Subscription.clinic_id == pending.clinic_id).first()
        if sub:
            sub.plan = pending.subscription_plan
            sub.status = SubscriptionStatus.ACTIVE
            sub.provider = PaymentProvider.PAYSTACK
            sub.provider_subscription_id = reference
            sub.current_period_start = now
            sub.current_period_end = period_end
            sub.amount = paid_amount
            sub.billing_cycle = pending.billing_cycle
            sub.cancel_at_period_end = False
        else:
            sub = Subscription(
                clinic_id=pending.clinic_id, plan=pending.subscription_plan,
                status=SubscriptionStatus.ACTIVE, provider=PaymentProvider.PAYSTACK,
                provider_subscription_id=reference, current_period_start=now,
                current_period_end=period_end, amount=paid_amount,
                currency=pending.currency, billing_cycle=pending.billing_cycle,
            )
            db.add(sub)
        db.flush()

        db.add(SubscriptionPayment(
            subscription_id=sub.id, provider=PaymentProvider.PAYSTACK,
            provider_reference=reference, amount=paid_amount, currency=pending.currency,
            status=PaymentStatus.PAID, paid_at=now,
            extra_data={"automated": True, "pending_payment_id": pending.id},
        ))

        pending.status = PendingPaymentStatus.PAID
        pending.paid_at = now
        pending.provider_response = {**(pending.provider_response or {}), "webhook_payload_keys": list(payload.keys())}
        db.commit()

        cache.set(f"payment_status:{reference}", {"status": "paid"}, ttl=3600)
        log_payment_event("subscription_activated", "paystack", reference, str(pending.clinic_id),
                          paid_amount, "success", extra={"plan": pending.subscription_plan, "automated": True})
        return True

    async def handle_payment_success(self, provider: str, payload: Dict, db) -> bool:
        from app.models.models import Clinic, Subscription, SubscriptionPayment
        from app.models.models import SubscriptionStatus, PaymentProvider, PaymentStatus
        from app.core.idempotency import check_and_mark, check_payment_reference_db

        try:
            if provider == "paystack":
                # FIX: metadata key (not extra_data)
                metadata = payload.get("metadata") or payload.get("extra_data") or {}
                clinic_id = metadata.get("clinic_id")
                plan = metadata.get("plan", "basic")
                amount = payload.get("amount", 0) / 100
                reference = payload.get("reference")
                sub_code = payload.get("subscription_code", "")
            else:
                clinic_id = payload.get("metadata", {}).get("clinic_id")
                plan = payload.get("metadata", {}).get("plan", "basic")
                amount = payload.get("amount_total", 0) / 100
                reference = payload.get("id")
                sub_code = payload.get("subscription", "")

            if not clinic_id or not reference:
                logger.error("Payment webhook missing clinic_id or reference",
                             extra={"payload_keys": list(payload.keys())})
                return False

            if not check_and_mark("payment", reference):
                logger.info(f"Duplicate payment webhook ignored (Redis): {reference}")
                return True

            if check_payment_reference_db(reference, db):
                logger.info(f"Duplicate payment webhook ignored (DB): {reference}")
                return True

            clinic = db.query(Clinic).filter(Clinic.id == clinic_id).first()
            if not clinic:
                logger.error(f"Payment for unknown clinic: {clinic_id}")
                return False

            sub = db.query(Subscription).filter(Subscription.clinic_id == clinic_id).first()
            now = utcnow()
            period_end = now + timedelta(days=30)
            prov_enum = PaymentProvider.PAYSTACK if provider == "paystack" else PaymentProvider.STRIPE

            if sub:
                sub.plan = plan
                sub.status = SubscriptionStatus.ACTIVE
                sub.provider = prov_enum
                sub.provider_subscription_id = sub_code
                sub.current_period_start = now
                sub.current_period_end = period_end
                sub.amount = amount
            else:
                sub = Subscription(
                    clinic_id=clinic_id, plan=plan, status=SubscriptionStatus.ACTIVE,
                    provider=prov_enum, provider_subscription_id=sub_code,
                    current_period_start=now, current_period_end=period_end,
                    amount=amount, currency=clinic.currency,
                )
                db.add(sub)

            db.flush()
            payment = SubscriptionPayment(
                subscription_id=sub.id, provider=prov_enum,
                provider_reference=reference, amount=amount,
                currency=clinic.currency, status=PaymentStatus.PAID, paid_at=now,
                extra_data={"raw_payload_keys": list(payload.keys())},
            )
            db.add(payment)
            db.commit()

            log_payment_event("subscription_activated", provider, reference, clinic_id, amount, "success",
                              extra={"plan": plan})
            return True

        except Exception as e:
            db.rollback()
            logger.error(f"Payment success handler failed: {e}", exc_info=True)
            return False


billing_service = BillingService()
