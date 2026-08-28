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
from app.services.notifications import notify
from app.core.circuit_breaker import billing_breaker

logger = get_logger(__name__)

PLANS = {
    "basic": {
        "name": "Basic",
        "max_doctors": 2,
        "max_bookings_month": 200,
        "features": [
            "Includes up to 2 doctors", "200 bookings/month",
            "SMS & Email reminders", "Basic no-show analytics", "Public booking page",
            "Online patient registration",
        ],
    },
    "pro": {
        "name": "Pro",
        "max_doctors": 10,
        "max_bookings_month": 2000,
        "features": [
            "Includes up to 10 doctors", "2,000 bookings/month",
            "SMS, WhatsApp & Email", "AI no-show prediction",
            "Smart reminder engine", "Auto slot refill",
            "Advanced analytics", "Waiting list management", "Priority support",
            "Online patient registration",
        ],
    },
    "enterprise": {
        "name": "Enterprise",
        "max_doctors": -1,
        "max_bookings_month": -1,
        "features": [
            "Unlimited doctors", "Unlimited bookings", "All Pro features",
            "Dedicated account manager", "Custom integrations", "SLA guarantee",
            "Online patient registration",
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
        self, email: str, amount_kobo: int, reference: str, metadata: Dict, expires_at
    ) -> Dict:
        """
        Smart payment system: Paystack's "Pay with Transfer" (PwT) charge.
        Generates a dedicated, single-use virtual account for this exact
        charge, valid across any Nigerian bank/fintech app (Opay, Kuda,
        GTBank, Providus, etc. — all route over NIP to the same account
        number). Paystack fires a `charge.success` webhook automatically
        once the transfer lands — no polling of Paystack required, no
        manual admin confirmation needed.

        Docs: POST /charge with a `bank_transfer` object containing
        `account_expires_at` (ISO 8601). Paystack clamps this to a minimum
        of 15 minutes and a maximum of 8 hours from now.

        IMPORTANT — response shape: Paystack returns the account details
        FLAT on `data`, not nested under a "bank_transfer" key:
            {
              "status": true,
              "data": {
                "reference": "...",
                "status": "pending_bank_transfer",
                "account_name": "...",
                "account_number": "...",
                "bank": {"slug": "...", "name": "...", "id": ...},
                "account_expires_at": "..."
              }
            }
        Reading `inner.get("bank_transfer")` (as this used to) always
        returns None, which is why `account_number` came back empty and
        the frontend fell back to its "Bank details not configured yet"
        message.
        """
        expires_iso = expires_at.strftime("%Y-%m-%dT%H:%M:%S.000Z")
        payload = {
            "email": email,
            "amount": amount_kobo,
            "reference": reference,
            "metadata": metadata,
            "bank_transfer": {"account_expires_at": expires_iso},
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
            bank = inner.get("bank") or {}
            account_number = inner.get("account_number")

            if not account_number:
                # Paystack accepted the request (status: true) but returned
                # no account details. In practice this means Pay with
                # Transfer isn't enabled on this Paystack account yet —
                # it requires Paystack to switch it on for your business
                # (email support@paystack.com or your relationship manager,
                # confirming you're a registered NG business) — rather than
                # a code problem. Raise so the caller can clean up the
                # PendingSubscriptionPayment row and surface a clear error
                # instead of silently showing a payment window with no
                # account number in it.
                raise Exception(
                    "Paystack returned no bank transfer account details "
                    f"(status={inner.get('status')!r}, message={data.get('message')!r}). "
                    "Pay with Transfer is likely not yet enabled on this Paystack account — "
                    "contact Paystack support to enable it."
                )

            return {
                "reference": inner.get("reference", reference),
                "bank_name": bank.get("name") or bank.get("slug"),
                "account_number": account_number,
                "account_name": inner.get("account_name", "Vitar Health"),
                "account_expires_at": inner.get("account_expires_at", expires_iso),
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

    def verify_webhook(self, payload: bytes, signature: Optional[str]) -> bool:
        # Fail closed, always — no environment-based bypass. A webhook that
        # can't be verified (secret unconfigured, or signature missing) is
        # rejected regardless of ENVIRONMENT, since that value is operator-set
        # and a misconfiguration there must never turn into an auth bypass.
        if not settings.PAYSTACK_WEBHOOK_SECRET:
            logger.error("PAYSTACK_WEBHOOK_SECRET not set — rejecting Paystack webhook")
            return False
        if not signature:
            return False
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
        if not settings.STRIPE_WEBHOOK_SECRET or not signature:
            logger.error("STRIPE_WEBHOOK_SECRET or signature missing — rejecting Stripe webhook")
            return {"valid": False, "error": "Signature or secret missing"}
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

    async def _initiate_pending_bank_transfer(
        self, clinic_id, plan, billing_cycle, amount, currency, user_email, db,
        installment_plan_id=None, installment_number=None, total_installments=None,
    ) -> Dict:
        """
        Shared core of the smart-payment flow: creates one
        PendingSubscriptionPayment row (superseding any other still-pending
        attempt for this clinic) and a matching Paystack dedicated
        bank-transfer charge for `amount`. Used both for a full one-shot
        subscription payment and for a single installment of a
        SubscriptionInstallmentPlan — the two are told apart by whether
        installment_plan_id is set.
        """
        from app.models.models import PendingSubscriptionPayment, PendingPaymentStatus
        from app.core.cache import cache

        currency_symbol = "₦" if currency == "NGN" else currency

        # Supersede any still-pending attempts for this clinic. Without this,
        # clicking Upgrade / Generate New Payment / Pay Next Installment more
        # than once (e.g. after closing the modal and coming back) would
        # leave multiple live PendingSubscriptionPayment rows — and multiple
        # live Paystack dedicated virtual accounts — open for the same
        # clinic at once.
        db.query(PendingSubscriptionPayment).filter(
            PendingSubscriptionPayment.clinic_id == clinic_id,
            PendingSubscriptionPayment.status == PendingPaymentStatus.PENDING,
        ).update({"status": PendingPaymentStatus.EXPIRED}, synchronize_session=False)
        db.commit()

        ref_tag = f"-INST{installment_number}" if installment_number else ""
        reference = f"VITAR-{clinic_id[:8].upper()}-{plan.upper()}{ref_tag}-{int(utcnow().timestamp())}"
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
            installment_plan_id=installment_plan_id,
            installment_number=installment_number,
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
                    "installment_plan_id": installment_plan_id,
                    "installment_number": installment_number,
                },
                expires_at=expires_at,
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

        pending.provider_response = {**charge.get("raw", {})}
        db.commit()

        cache.set(f"payment_status:{reference}", {"status": "pending", "clinic_id": clinic_id}, ttl=35 * 60)

        log_payment_event("automated_payment_initiated", "paystack", reference, clinic_id, amount, "pending",
                          extra={"plan": plan, "installment_plan_id": installment_plan_id,
                                 "installment_number": installment_number})

        if installment_plan_id:
            instructions = (
                f"Transfer exactly {currency_symbol}{amount:,} to the account below. "
                f"This is installment {installment_number} of {total_installments} for your "
                f"{plan.capitalize()} plan. Coverage extends automatically the moment we receive it."
            )
        else:
            instructions = (
                f"Transfer exactly {currency_symbol}{amount:,} to the account below. "
                f"Your subscription activates automatically the moment we receive it — "
                f"no need to contact support."
            )

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
            # The server's own "now" at the moment this session was created.
            # The frontend uses this to correct for any clock drift between
            # this VPS and the user's device, so a skewed server clock can
            # never make a freshly-created session appear instantly expired.
            "server_time": now.isoformat(),
            "status": "pending",
            "instructions": instructions,
            "installment_plan_id": installment_plan_id,
            "installment_number": installment_number,
            "total_installments": total_installments,
        }

    async def create_automated_subscription_payment(
        self, clinic_id, plan, billing_cycle, user_email, db
    ) -> Dict:
        """
        Smart payment system: generates a Paystack dedicated bank-transfer
        charge for the clinic's chosen plan, paid in full in one transfer.
        A PendingSubscriptionPayment row tracks the session so the frontend
        can poll for status and so the webhook handler knows exactly what
        to activate once paid.
        """
        from app.models.models import Clinic

        clinic = db.query(Clinic).filter(Clinic.id == clinic_id).first()
        if not clinic:
            raise Exception("Clinic not found")

        currency = clinic.currency or "NGN"
        pricing = get_plan_pricing(plan, currency)
        amount = pricing["monthly"] if billing_cycle == "monthly" else pricing["annual"]
        if not amount:
            raise Exception(f"Plan {plan} has no fixed price for automated checkout")

        # Refer & Earn: apply this clinic's earned (unredeemed) 10% referral
        # discount, if any. No-op and safe to call unconditionally — see
        # referral_service.apply_referral_discount for the failure-safety
        # guarantee (never raises, never blocks checkout). The credit is
        # NOT marked spent here — only once this specific checkout actually
        # confirms paid (see finalize_paystack_payment's redeem_referral_
        # discount call below) — so a failed/expired/mismatched attempt
        # doesn't burn the referrer's discount for nothing.
        from app.services.referral_service import apply_referral_discount
        amount, applied_referral_id = apply_referral_discount(amount, clinic_id, db)

        result = await self._initiate_pending_bank_transfer(
            clinic_id, plan, billing_cycle, amount, currency, user_email, db,
        )

        # Merge (not overwrite) — applied_referral_id must survive this
        # assignment so finalize_paystack_payment can find it later to
        # redeem the credit once (and only once) this checkout confirms.
        from app.models.models import PendingSubscriptionPayment
        pending = db.query(PendingSubscriptionPayment).filter(
            PendingSubscriptionPayment.paystack_reference == result["reference"]
        ).first()
        pending.provider_response = {**(pending.provider_response or {}), "applied_referral_id": applied_referral_id}
        db.commit()

        return result

    MIN_INSTALLMENTS = 2
    MAX_INSTALLMENTS = 12  # annual plan split into up to 12 monthly-ish parts

    async def create_installment_subscription_payment(
        self, clinic_id, plan, installments, user_email, db
    ) -> Dict:
        """
        Lets a clinic pay for the ANNUAL price of a plan across several
        smaller bank transfers instead of one lump sum — e.g. 2, 3, or up
        to 12 installments spread across as many months as they want.
        Creates the SubscriptionInstallmentPlan agreement plus the first
        installment's bank-transfer payment session. Subsequent
        installments are billed via pay_next_installment as each one
        comes due.
        """
        from app.models.models import (
            Clinic, SubscriptionInstallmentPlan, InstallmentPlanStatus,
        )

        if installments < self.MIN_INSTALLMENTS or installments > self.MAX_INSTALLMENTS:
            raise Exception(
                f"Installments must be between {self.MIN_INSTALLMENTS} and {self.MAX_INSTALLMENTS}"
            )

        clinic = db.query(Clinic).filter(Clinic.id == clinic_id).first()
        if not clinic:
            raise Exception("Clinic not found")

        existing = db.query(SubscriptionInstallmentPlan).filter(
            SubscriptionInstallmentPlan.clinic_id == clinic_id,
            SubscriptionInstallmentPlan.status == InstallmentPlanStatus.ACTIVE,
        ).first()
        if existing:
            raise Exception(
                "You already have an active installment plan. Pay the next installment "
                "or cancel it before starting a new one."
            )

        currency = clinic.currency or "NGN"
        pricing = get_plan_pricing(plan, currency)
        total_amount = pricing["annual"]
        if not total_amount:
            raise Exception(f"Plan {plan} has no fixed annual price for installment checkout")

        # Split evenly in cents/kobo, last installment absorbs the rounding
        # remainder, so the parts always sum exactly to total_amount.
        total_amount = float(total_amount)
        base_unit = round(total_amount / installments, 2)
        amounts = [base_unit] * (installments - 1)
        amounts.append(round(total_amount - sum(amounts), 2))

        plan_row = SubscriptionInstallmentPlan(
            clinic_id=clinic_id,
            subscription_plan=plan,
            billing_cycle="annual",
            total_amount=total_amount,
            currency=currency,
            total_installments=installments,
            installments_paid=0,
            status=InstallmentPlanStatus.ACTIVE,
            extra_data={"installment_amounts": amounts},
        )
        db.add(plan_row)
        db.commit()
        db.refresh(plan_row)

        try:
            result = await self._initiate_pending_bank_transfer(
                clinic_id, plan, "annual", amounts[0], currency, user_email, db,
                installment_plan_id=plan_row.id, installment_number=1,
                total_installments=installments,
            )
        except Exception:
            db.delete(plan_row)
            db.commit()
            raise

        log_payment_event("installment_plan_started", "paystack", result["reference"], clinic_id,
                          total_amount, "pending", extra={"plan": plan, "installments": installments})

        return result

    async def pay_next_installment(self, clinic_id, user_email, db) -> Dict:
        """Bills whichever installment comes next on the clinic's active plan."""
        from app.models.models import Clinic, SubscriptionInstallmentPlan, InstallmentPlanStatus

        clinic = db.query(Clinic).filter(Clinic.id == clinic_id).first()
        if not clinic:
            raise Exception("Clinic not found")

        plan_row = db.query(SubscriptionInstallmentPlan).filter(
            SubscriptionInstallmentPlan.clinic_id == clinic_id,
            SubscriptionInstallmentPlan.status == InstallmentPlanStatus.ACTIVE,
        ).first()
        if not plan_row:
            raise Exception("No active installment plan found")

        if plan_row.installments_paid >= plan_row.total_installments:
            raise Exception("All installments have already been paid")

        amounts = (plan_row.extra_data or {}).get("installment_amounts") or []
        next_index = plan_row.installments_paid
        if next_index >= len(amounts):
            raise Exception("Installment plan is in an inconsistent state")
        amount = amounts[next_index]

        return await self._initiate_pending_bank_transfer(
            clinic_id, plan_row.subscription_plan, plan_row.billing_cycle, amount,
            plan_row.currency or "NGN", user_email, db,
            installment_plan_id=plan_row.id, installment_number=next_index + 1,
            total_installments=plan_row.total_installments,
        )

    def get_installment_plan_status(self, clinic_id, db) -> Optional[Dict]:
        """Returns the clinic's active installment plan (if any) for the Billing page."""
        from app.models.models import SubscriptionInstallmentPlan, InstallmentPlanStatus

        plan_row = db.query(SubscriptionInstallmentPlan).filter(
            SubscriptionInstallmentPlan.clinic_id == clinic_id,
            SubscriptionInstallmentPlan.status == InstallmentPlanStatus.ACTIVE,
        ).order_by(SubscriptionInstallmentPlan.created_at.desc()).first()
        if not plan_row:
            return None

        amounts = (plan_row.extra_data or {}).get("installment_amounts") or []
        next_amount = amounts[plan_row.installments_paid] if plan_row.installments_paid < len(amounts) else None

        return {
            "id": plan_row.id,
            "plan": plan_row.subscription_plan,
            "billing_cycle": plan_row.billing_cycle,
            "total_amount": float(plan_row.total_amount),
            "currency": plan_row.currency,
            "total_installments": plan_row.total_installments,
            "installments_paid": plan_row.installments_paid,
            "next_installment_amount": next_amount,
            "status": plan_row.status.value,
        }

    def cancel_installment_plan(self, clinic_id, db) -> Dict:
        """
        Stops future installments from being billed. Coverage already
        purchased through installments paid so far is not revoked — the
        clinic's subscription simply runs out at its current period end,
        same as cancelling a regular subscription.
        """
        from app.models.models import SubscriptionInstallmentPlan, InstallmentPlanStatus, PendingSubscriptionPayment, PendingPaymentStatus

        plan_row = db.query(SubscriptionInstallmentPlan).filter(
            SubscriptionInstallmentPlan.clinic_id == clinic_id,
            SubscriptionInstallmentPlan.status == InstallmentPlanStatus.ACTIVE,
        ).first()
        if not plan_row:
            raise Exception("No active installment plan found")

        plan_row.status = InstallmentPlanStatus.CANCELLED
        plan_row.cancelled_at = utcnow()

        db.query(PendingSubscriptionPayment).filter(
            PendingSubscriptionPayment.installment_plan_id == plan_row.id,
            PendingSubscriptionPayment.status == PendingPaymentStatus.PENDING,
        ).update({"status": PendingPaymentStatus.EXPIRED}, synchronize_session=False)
        db.commit()

        return {"message": "Installment plan cancelled", "installments_paid": plan_row.installments_paid}

    def get_payment_status(self, reference: str, db, clinic_id: str) -> Dict:
        """
        Polled by the Billing page every 10s. Redis-first, DB fallback.
        Lazily flips PENDING → EXPIRED once the session's time is up.

        clinic_id is required and the DB lookup is scoped to it — without this,
        any logged-in clinic owner could poll another clinic's payment
        reference and learn its status.
        """
        from app.models.models import PendingSubscriptionPayment, PendingPaymentStatus
        from app.core.cache import cache

        cached = cache.get(f"payment_status:{reference}")
        if cached and cached.get("status") != "pending" and cached.get("clinic_id") == clinic_id:
            return cached

        pending = db.query(PendingSubscriptionPayment).filter(
            PendingSubscriptionPayment.paystack_reference == reference,
            PendingSubscriptionPayment.clinic_id == clinic_id,
        ).first()
        if not pending:
            return {"status": "not_found"}

        if pending.status == PendingPaymentStatus.PENDING and utcnow() > pending.expires_at:
            pending.status = PendingPaymentStatus.EXPIRED
            db.commit()
            cache.set(f"payment_status:{reference}", {"status": "expired", "clinic_id": clinic_id}, ttl=60 * 60)

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

        # with_for_update() closes a real gap: this function's only
        # protection against a concurrent duplicate webhook delivery used
        # to be handle_payment_success's idempotency layer at the route
        # level, which itself fails open if Redis is briefly unreachable
        # (idempotency.py). Without a row lock here, two requests could
        # both read status=PENDING before either commits and both attempt
        # to activate — it happened to never double-credit only because
        # SubscriptionPayment.provider_reference has a DB-level unique
        # constraint that makes the loser's commit raise, which is an
        # accidental safety net, not a designed one. The second request now
        # simply blocks here until the first transaction commits, then sees
        # status=PAID and returns via the idempotent no-op check below.
        pending = db.query(PendingSubscriptionPayment).filter(
            PendingSubscriptionPayment.paystack_reference == reference
        ).with_for_update().first()
        if not pending:
            return False  # not part of the automated flow — let caller use legacy path

        if pending.status == PendingPaymentStatus.PAID:
            return True  # already activated — idempotent no-op

        # expires_at (35 min) only governs how long the frontend shows the
        # "waiting for transfer" UI before telling the clinic to regenerate
        # a session — it is NOT a reason to refuse real money. A Paystack
        # dedicated-account bank transfer can legitimately clear well past
        # that window (bank-app delays, interbank transfer lag), and by the
        # time charge.success arrives the money has already moved into our
        # account regardless of what our own clock thinks. Same principle
        # already applied to booking payments in
        # cancel_stale_awaiting_payment_appointments (workers/tasks.py):
        # always trust Paystack's own confirmation over our internal state;
        # a delayed webhook must not cost a clinic a subscription they
        # already paid for. We still log this case — a late activation is a
        # real signal the 35-minute window may be too tight.
        was_late = utcnow() > pending.expires_at
        if was_late:
            log_payment_event("automated_payment_late_but_valid", "paystack", reference,
                              str(pending.clinic_id), extra={"expires_at": pending.expires_at.isoformat()})

        paid_amount = float(payload.get("amount", 0)) / 100
        expected_amount = float(pending.amount)
        tolerance = max(1.0, expected_amount * 0.005)  # minimal rounding tolerance

        if abs(paid_amount - expected_amount) > tolerance:
            pending.status = PendingPaymentStatus.AMOUNT_MISMATCH
            db.commit()
            cache.set(f"payment_status:{reference}", {"status": "amount_mismatch", "clinic_id": str(pending.clinic_id)}, ttl=3600)
            log_payment_event("automated_payment_amount_mismatch", "paystack", reference,
                              str(pending.clinic_id), paid_amount, "amount_mismatch",
                              extra={"expected_amount": expected_amount})
            return False

        clinic = db.query(Clinic).filter(Clinic.id == pending.clinic_id).first()
        if not clinic:
            logger.error(f"Automated payment for unknown clinic: {pending.clinic_id}")
            return False

        # Public directory eligibility (see models.Clinic.is_listed) — an
        # active paid subscription re-qualifies a clinic whose trial had
        # already expired (unlisted by expire_trial_subscriptions). Only
        # once onboarding is actually complete, matching the same rule
        # applied at onboarding completion and in the search/detail endpoints.
        if clinic.onboarding_completed:
            clinic.is_listed = True

        now = utcnow()

        # Installment payments only ever cover a proportional slice of the
        # full billing cycle (1/total_installments of it) — a clinic that
        # stops paying partway through simply loses coverage at the point
        # they've actually paid for, same as any other unpaid renewal.
        install_plan = None
        if pending.installment_plan_id:
            from app.models.models import SubscriptionInstallmentPlan
            install_plan = db.query(SubscriptionInstallmentPlan).filter(
                SubscriptionInstallmentPlan.id == pending.installment_plan_id
            ).with_for_update().first()

        if install_plan:
            full_cycle_days = 30 if pending.billing_cycle == "monthly" else 365
            slice_days = max(1, round(full_cycle_days / install_plan.total_installments))
            period_delta = timedelta(days=slice_days)
        else:
            period_delta = timedelta(days=30 if pending.billing_cycle == "monthly" else 365)

        sub = db.query(Subscription).filter(Subscription.clinic_id == pending.clinic_id).first()
        # From the 2nd installment onward, coverage stacks onto whatever's
        # left of the current period (so paying installment 2 while
        # installment 1's slice hasn't expired yet extends from its end,
        # not from "now"). The 1st installment always starts fresh at
        # "now", same as a one-shot full payment — it must not inherit
        # any leftover free-trial time still sitting on sub.current_period_end.
        is_followup_installment = bool(install_plan) and (pending.installment_number or 1) > 1
        if is_followup_installment and sub and sub.current_period_end and sub.current_period_end > now:
            period_start = sub.current_period_start
            period_end = sub.current_period_end + period_delta
        else:
            period_start = now
            period_end = now + period_delta

        if sub:
            sub.plan = pending.subscription_plan
            sub.status = SubscriptionStatus.ACTIVE
            sub.provider = PaymentProvider.PAYSTACK
            sub.provider_subscription_id = reference
            sub.current_period_start = period_start
            sub.current_period_end = period_end
            sub.amount = paid_amount
            sub.billing_cycle = pending.billing_cycle
            sub.cancel_at_period_end = False
        else:
            sub = Subscription(
                clinic_id=pending.clinic_id, plan=pending.subscription_plan,
                status=SubscriptionStatus.ACTIVE, provider=PaymentProvider.PAYSTACK,
                provider_subscription_id=reference, current_period_start=period_start,
                current_period_end=period_end, amount=paid_amount,
                currency=pending.currency, billing_cycle=pending.billing_cycle,
            )
            db.add(sub)
        db.flush()

        if install_plan:
            install_plan.installments_paid = (install_plan.installments_paid or 0) + 1
            if install_plan.installments_paid >= install_plan.total_installments:
                from app.models.models import InstallmentPlanStatus
                install_plan.status = InstallmentPlanStatus.COMPLETED
                install_plan.completed_at = now

        # Refer & Earn: was this clinic's Subscription previously ever paid?
        # Must be captured before adding this payment's own row below.
        is_first_payment = db.query(SubscriptionPayment).filter(
            SubscriptionPayment.subscription_id == sub.id,
            SubscriptionPayment.status == PaymentStatus.PAID,
        ).count() == 0

        db.add(SubscriptionPayment(
            subscription_id=sub.id, provider=PaymentProvider.PAYSTACK,
            provider_reference=reference, amount=paid_amount, currency=pending.currency,
            status=PaymentStatus.PAID, paid_at=now,
            extra_data={
                "automated": True, "pending_payment_id": pending.id,
                "installment_plan_id": pending.installment_plan_id,
                "installment_number": pending.installment_number,
            },
        ))

        pending.status = PendingPaymentStatus.PAID
        pending.paid_at = now
        pending.provider_response = {**(pending.provider_response or {}), "webhook_payload_keys": list(payload.keys())}
        db.commit()

        cache.set(f"payment_status:{reference}", {"status": "paid", "clinic_id": str(pending.clinic_id)}, ttl=3600)
        log_payment_event("subscription_activated", "paystack", reference, str(pending.clinic_id),
                          paid_amount, "success", extra={"plan": pending.subscription_plan, "automated": True,
                                                           "installment_plan_id": pending.installment_plan_id})

        plan_name = PLANS.get(pending.subscription_plan, {}).get("name", pending.subscription_plan)
        currency_symbol = "₦" if pending.currency == "NGN" else pending.currency
        if install_plan:
            notify(
                event_type="subscription_paid",
                agent_name="billing",
                message=f"{clinic.name} paid installment {pending.installment_number}/{install_plan.total_installments} "
                        f"for the {plan_name} plan ({currency_symbol}{paid_amount:,.2f}).",
                related_id=clinic.id,
                link_path="/admin/subscriptions",
            )
        else:
            notify(
                event_type="subscription_paid",
                agent_name="billing",
                message=f"{clinic.name} just paid for the {plan_name} plan "
                        f"({currency_symbol}{paid_amount:,.2f}, {pending.billing_cycle}).",
                related_id=clinic.id,
                link_path="/admin/subscriptions",
            )

        if is_first_payment:
            from app.services.referral_service import record_referral_payment
            record_referral_payment(pending.clinic_id, db)

        # This clinic's own checkout may have had a referral discount
        # applied to it (see create_automated_subscription_payment) — now
        # that the payment is actually confirmed, mark that credit spent.
        from app.services.referral_service import redeem_referral_discount
        redeem_referral_discount((pending.provider_response or {}).get("applied_referral_id"), db)

        return True

    async def handle_payment_success(self, provider: str, payload: Dict, db) -> bool:
        from app.models.models import Clinic, Subscription, SubscriptionPayment
        from app.models.models import SubscriptionStatus, PaymentProvider, PaymentStatus
        from app.core.idempotency import check_and_mark, check_payment_reference_db, invalidate

        reference = None
        try:
            if provider == "paystack":
                # FIX: metadata key (not extra_data)
                metadata = payload.get("metadata") or payload.get("extra_data") or {}
                clinic_id = metadata.get("clinic_id")
                plan = metadata.get("plan", "basic")
                billing_cycle = metadata.get("billing_cycle", "monthly")
                amount = payload.get("amount", 0) / 100
                reference = payload.get("reference")
                sub_code = payload.get("subscription_code", "")
            else:
                metadata = payload.get("metadata", {})
                clinic_id = metadata.get("clinic_id")
                plan = metadata.get("plan", "basic")
                billing_cycle = metadata.get("billing_cycle", "monthly")
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
                # Undo the idempotency mark set above — this reference was
                # never actually processed, so a legitimate webhook retry
                # (e.g. once the clinic row exists) must not be dropped as
                # a "duplicate" for the next 24h.
                invalidate("payment", reference)
                return False

            sub = db.query(Subscription).filter(Subscription.clinic_id == clinic_id).first()
            now = utcnow()
            # Matches finalize_paystack_payment's branching — this path was
            # previously hardcoded to 30 days regardless of billing_cycle,
            # silently shortchanging annual payments routed through it.
            period_end = now + timedelta(days=30 if billing_cycle == "monthly" else 365)
            prov_enum = PaymentProvider.PAYSTACK if provider == "paystack" else PaymentProvider.STRIPE

            if sub:
                sub.plan = plan
                sub.status = SubscriptionStatus.ACTIVE
                sub.provider = prov_enum
                sub.provider_subscription_id = sub_code
                sub.current_period_start = now
                sub.current_period_end = period_end
                sub.amount = amount
                sub.billing_cycle = billing_cycle
            else:
                sub = Subscription(
                    clinic_id=clinic_id, plan=plan, status=SubscriptionStatus.ACTIVE,
                    provider=prov_enum, provider_subscription_id=sub_code,
                    current_period_start=now, current_period_end=period_end,
                    amount=amount, currency=clinic.currency, billing_cycle=billing_cycle,
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

            plan_name = PLANS.get(plan, {}).get("name", plan)
            currency_symbol = "₦" if (clinic.currency or "NGN") == "NGN" else clinic.currency
            notify(
                event_type="subscription_paid",
                agent_name="billing",
                message=f"{clinic.name} just paid for the {plan_name} plan "
                        f"({currency_symbol}{amount:,.2f}, {billing_cycle}).",
                related_id=clinic.id,
                link_path="/admin/subscriptions",
            )

            return True

        except Exception as e:
            db.rollback()
            logger.error(f"Payment success handler failed: {e}", exc_info=True)
            # Same reasoning as above: a reference marked "processed" by
            # check_and_mark() but never actually applied (we failed before
            # committing) must be released, or the payment is lost silently
            # until the 24h idempotency TTL expires.
            if reference:
                invalidate("payment", reference)
            return False


billing_service = BillingService()
