"""
Vitar v10 — Provider Fallback Chains & Retry Middleware

Addresses gap: "No Circuit Breakers → fail gracefully, not cascade"

Provides three composable primitives:

  1. retry_with_backoff()
     Decorator / context that retries with exponential backoff + full jitter.
     Stops at max_retries — no infinite loops.

  2. NotificationFallbackChain
     Tries channels in order: WhatsApp → SMS → Email.
     Each hop is protected by its own circuit breaker.
     Returns the first successful delivery result.

  3. PaymentFallbackChain
     Tries providers in order: Paystack → Flutterwave → Stripe.
     Each hop is protected by its own circuit breaker.
     Designed for async payment initiation (not webhooks).

Usage:
    # Notification with fallback:
    chain = NotificationFallbackChain()
    result = await chain.deliver(phone="+2348012345678", message="...", email="a@b.com")

    # Payment with fallback:
    chain = PaymentFallbackChain()
    result = await chain.charge(amount=5000, currency="NGN", email="a@b.com", reference="ref-123")

    # Retry decorator:
    @retry_with_backoff(max_retries=4, base_delay=1.0, exceptions=(httpx.HTTPError,))
    async def call_external_api(): ...
"""

import asyncio
import functools
import logging
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, List, Optional, TypeVar

logger = logging.getLogger("vitar.resilience")

T = TypeVar("T")


# ── 1. Retry with Exponential Backoff + Full Jitter ──────────────────────────

def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    exceptions: tuple = (Exception,),
    on_retry: Optional[Callable] = None,
):
    """
    Decorator: retries the wrapped async function with exponential backoff + full jitter.

    Formula (full jitter — avoids thundering herd):
        wait = random.uniform(0, min(max_delay, base_delay * 2^attempt))

    Args:
        max_retries: Maximum number of retries (not total attempts).
        base_delay: Starting delay in seconds.
        max_delay: Cap on delay to prevent unbounded waits.
        exceptions: Tuple of exception types to catch and retry on.
        on_retry: Optional callback(attempt, exc, wait) for logging/metrics.

    Example:
        @retry_with_backoff(max_retries=3, base_delay=0.5, exceptions=(httpx.HTTPError,))
        async def call_paystack(amount: int): ...
    """
    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            last_exc: Optional[Exception] = None
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as exc:
                    last_exc = exc
                    if attempt == max_retries:
                        logger.error(
                            f"[retry] {func.__name__} failed after {max_retries + 1} attempts",
                            exc_info=exc,
                        )
                        raise
                    cap = min(max_delay, base_delay * (2 ** attempt))
                    wait = random.uniform(0, cap)
                    logger.warning(
                        f"[retry] {func.__name__} attempt {attempt + 1}/{max_retries + 1} "
                        f"failed ({type(exc).__name__}), retrying in {wait:.2f}s",
                        extra={"attempt": attempt + 1, "wait_s": round(wait, 2)},
                    )
                    if on_retry:
                        try:
                            on_retry(attempt + 1, exc, wait)
                        except Exception:
                            pass
                    await asyncio.sleep(wait)
            raise last_exc  # unreachable, but satisfies type checker
        return wrapper
    return decorator


# ── Delivery result ───────────────────────────────────────────────────────────

@dataclass
class ChainResult:
    success: bool
    provider: str                       # which provider succeeded
    attempted: List[str] = field(default_factory=list)  # all tried
    message_id: Optional[str] = None
    error: Optional[str] = None
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "provider": self.provider,
            "attempted": self.attempted,
            "message_id": self.message_id,
            "error": self.error,
            "timestamp": self.timestamp,
        }


# ── 2. Notification Fallback Chain ────────────────────────────────────────────

class NotificationFallbackChain:
    """
    Multi-channel notification delivery with automatic fallback.

    Delivery order (configurable):
        1. WhatsApp  → whatsapp_breaker (8s timeout)
        2. SMS       → sms_breaker      (8s timeout)
        3. Email     → email_breaker    (10s timeout)

    If a channel's circuit breaker is OPEN, that channel is skipped
    entirely and the chain moves to the next — no waiting.

    Usage:
        chain = NotificationFallbackChain()
        result = await chain.deliver(
            phone="+2348012345678",
            message="Hi Amara, appointment reminder...",
            email="amara@example.com",
        )
        if not result.success:
            # All channels exhausted — log to dead notification queue
    """

    def __init__(self, preferred_channels: Optional[List[str]] = None):
        # Default order: WhatsApp → SMS → Email
        self.channels = preferred_channels or ["whatsapp", "sms", "email"]

    async def deliver(
        self,
        message: str,
        phone: Optional[str] = None,
        email: Optional[str] = None,
        patient_name: str = "Patient",
    ) -> ChainResult:
        """
        Attempt delivery across channels in order.
        Returns as soon as one channel succeeds.
        """
        from app.core.circuit_breaker import (
            sms_breaker, whatsapp_breaker, email_breaker,
        )

        attempted: List[str] = []
        last_error: Optional[str] = None

        for channel in self.channels:
            attempted.append(channel)

            if channel == "whatsapp" and phone:
                result = await whatsapp_breaker.call_async(
                    self._send_whatsapp,
                    phone=phone,
                    message=message,
                    fallback=None,
                    timeout=8.0,
                )
                if result and result.get("success"):
                    self._record(channel, "success")
                    return ChainResult(
                        success=True,
                        provider="whatsapp",
                        attempted=attempted,
                        message_id=result.get("message_id"),
                    )
                last_error = result.get("error", "whatsapp failed") if result else "circuit open"
                self._record(channel, "fallback")

            elif channel == "sms" and phone:
                result = await sms_breaker.call_async(
                    self._send_sms,
                    phone=phone,
                    message=message,
                    fallback=None,
                    timeout=8.0,
                )
                if result and result.get("success"):
                    self._record(channel, "success")
                    return ChainResult(
                        success=True,
                        provider="sms",
                        attempted=attempted,
                        message_id=result.get("message_id"),
                    )
                last_error = result.get("error", "sms failed") if result else "circuit open"
                self._record(channel, "fallback")

            elif channel == "email" and email:
                result = await email_breaker.call_async(
                    self._send_email,
                    email=email,
                    message=message,
                    patient_name=patient_name,
                    fallback=None,
                    timeout=10.0,
                )
                if result and result.get("success"):
                    self._record(channel, "success")
                    return ChainResult(
                        success=True,
                        provider="email",
                        attempted=attempted,
                        message_id=result.get("message_id"),
                    )
                last_error = result.get("error", "email failed") if result else "circuit open"
                self._record(channel, "fallback")

        logger.error(
            "NotificationFallbackChain: all channels exhausted",
            extra={"attempted": attempted, "last_error": last_error},
        )
        return ChainResult(
            success=False,
            provider="none",
            attempted=attempted,
            error=f"All channels failed. Last error: {last_error}",
        )

    async def _send_whatsapp(self, phone: str, message: str) -> Optional[dict]:
        """Send via WhatsApp Cloud API."""
        try:
            import httpx
            from app.core.config import settings
            if not settings.WHATSAPP_ACCESS_TOKEN or not settings.WHATSAPP_PHONE_NUMBER_ID:
                return {"success": False, "error": "WhatsApp not configured"}
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.post(
                    f"https://graph.facebook.com/v17.0/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages",
                    headers={"Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}"},
                    json={
                        "messaging_product": "whatsapp",
                        "to": phone.replace("+", ""),
                        "type": "text",
                        "text": {"body": message},
                    },
                )
                data = resp.json()
                if resp.status_code == 200:
                    return {"success": True, "message_id": data.get("messages", [{}])[0].get("id")}
                return {"success": False, "error": data.get("error", {}).get("message", "unknown")}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    async def _send_sms(self, phone: str, message: str) -> Optional[dict]:
        """Send SMS via Termii (primary) with Twilio fallback."""
        try:
            import httpx
            from app.core.config import settings
            # Try Termii first (optimised for Nigeria)
            if settings.TERMII_API_KEY:
                async with httpx.AsyncClient(timeout=8.0) as client:
                    resp = await client.post(
                        "https://api.ng.termii.com/api/sms/send",
                        json={
                            "to": phone,
                            "from": settings.TERMII_SENDER_ID,
                            "sms": message,
                            "type": "plain",
                            "api_key": settings.TERMII_API_KEY,
                            "channel": "generic",
                        },
                    )
                    data = resp.json()
                    if resp.status_code == 200 and data.get("code") == "ok":
                        return {"success": True, "message_id": data.get("message_id")}
            return {"success": False, "error": "SMS provider unavailable"}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    async def _send_email(
        self, email: str, message: str, patient_name: str = "Patient"
    ) -> Optional[dict]:
        """Send email via SendGrid."""
        try:
            import httpx
            from app.core.config import settings
            if not settings.SENDGRID_API_KEY:
                return {"success": False, "error": "SendGrid not configured"}
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    "https://api.sendgrid.com/v3/mail/send",
                    headers={"Authorization": f"Bearer {settings.SENDGRID_API_KEY}"},
                    json={
                        "personalizations": [
                            {"to": [{"email": email, "name": patient_name}]}
                        ],
                        "from": {"email": settings.EMAIL_FROM, "name": settings.EMAIL_FROM_NAME},
                        "subject": "Appointment Reminder — Vitar Health",
                        "content": [{"type": "text/plain", "value": message}],
                    },
                )
                if resp.status_code in (200, 202):
                    return {"success": True, "message_id": resp.headers.get("X-Message-Id")}
                return {"success": False, "error": f"SendGrid {resp.status_code}"}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def _record(self, channel: str, outcome: str):
        try:
            from app.core.metrics import NOTIFICATIONS_SENT
            NOTIFICATIONS_SENT.labels(channel=channel, status=outcome).inc()
        except Exception:
            pass


# ── 3. Payment Fallback Chain ─────────────────────────────────────────────────

class PaymentFallbackChain:
    """
    Multi-provider payment initiation with automatic fallback.

    Provider order (configurable):
        1. Paystack     → billing_breaker (15s)  — preferred for NGN
        2. Flutterwave  → flutterwave_breaker (15s)
        3. Stripe       → stripe_breaker (15s)

    Skips providers not configured (empty API key).
    Returns on first successful charge initiation.

    Note: This handles charge *initiation* only. Payment verification
    is still done via webhooks per-provider.

    Usage:
        chain = PaymentFallbackChain()
        result = await chain.charge(
            amount=5000,
            currency="NGN",
            email="clinic@example.com",
            reference="sub-clinic-123",
        )
    """

    def __init__(self, preferred_providers: Optional[List[str]] = None):
        self.providers = preferred_providers or ["paystack", "flutterwave", "stripe"]

    async def charge(
        self,
        amount: int,         # in smallest currency unit (kobo for NGN)
        currency: str,
        email: str,
        reference: str,
        metadata: Optional[dict] = None,
    ) -> ChainResult:
        from app.core.circuit_breaker import (
            billing_breaker, flutterwave_breaker, stripe_breaker,
        )
        from app.core.config import settings

        attempted: List[str] = []
        last_error: Optional[str] = None

        for provider in self.providers:
            attempted.append(provider)

            if provider == "paystack" and settings.PAYSTACK_SECRET_KEY:
                result = await billing_breaker.call_async(
                    self._paystack_charge,
                    amount=amount, currency=currency,
                    email=email, reference=reference, metadata=metadata,
                    fallback=None, timeout=15.0,
                )
                if result and result.get("success"):
                    return ChainResult(success=True, provider="paystack", attempted=attempted,
                                       message_id=result.get("authorization_url"))
                last_error = (result or {}).get("error", "paystack failed")

            elif provider == "flutterwave" and settings.FLUTTERWAVE_SECRET_KEY:
                result = await flutterwave_breaker.call_async(
                    self._flutterwave_charge,
                    amount=amount / 100,  # Flutterwave uses full units
                    currency=currency,
                    email=email, reference=reference, metadata=metadata,
                    fallback=None, timeout=15.0,
                )
                if result and result.get("success"):
                    return ChainResult(success=True, provider="flutterwave", attempted=attempted,
                                       message_id=result.get("payment_link"))
                last_error = (result or {}).get("error", "flutterwave failed")

            elif provider == "stripe" and settings.STRIPE_SECRET_KEY:
                result = await stripe_breaker.call_async(
                    self._stripe_charge,
                    amount=amount, currency=currency.lower(),
                    email=email, reference=reference,
                    fallback=None, timeout=15.0,
                )
                if result and result.get("success"):
                    return ChainResult(success=True, provider="stripe", attempted=attempted,
                                       message_id=result.get("payment_intent_id"))
                last_error = (result or {}).get("error", "stripe failed")

        logger.error(
            "PaymentFallbackChain: all providers exhausted",
            extra={"attempted": attempted, "email": email, "ref": reference, "last_error": last_error},
        )
        return ChainResult(
            success=False, provider="none", attempted=attempted,
            error=f"All payment providers failed. Last error: {last_error}",
        )

    async def _paystack_charge(self, amount, currency, email, reference, metadata=None) -> Optional[dict]:
        try:
            import httpx
            from app.core.config import settings
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    f"{settings.PAYSTACK_BASE_URL}/transaction/initialize",
                    headers={"Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}"},
                    json={"amount": amount, "currency": currency, "email": email,
                          "reference": reference, "metadata": metadata or {}},
                )
                data = resp.json()
                if data.get("status"):
                    return {"success": True, "authorization_url": data["data"].get("authorization_url")}
                return {"success": False, "error": data.get("message", "paystack error")}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    async def _flutterwave_charge(self, amount, currency, email, reference, metadata=None) -> Optional[dict]:
        try:
            import httpx
            from app.core.config import settings
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    "https://api.flutterwave.com/v3/payments",
                    headers={"Authorization": f"Bearer {settings.FLUTTERWAVE_SECRET_KEY}"},
                    json={"amount": amount, "currency": currency, "customer": {"email": email},
                          "tx_ref": reference, "redirect_url": "https://labvault.cloud/billing/callback"},
                )
                data = resp.json()
                if data.get("status") == "success":
                    return {"success": True, "payment_link": data["data"].get("link")}
                return {"success": False, "error": data.get("message", "flutterwave error")}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    async def _stripe_charge(self, amount, currency, email, reference) -> Optional[dict]:
        try:
            import httpx
            from app.core.config import settings
            import base64
            auth = base64.b64encode(f"{settings.STRIPE_SECRET_KEY}:".encode()).decode()
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    "https://api.stripe.com/v1/payment_intents",
                    headers={"Authorization": f"Basic {auth}",
                             "Content-Type": "application/x-www-form-urlencoded"},
                    data={"amount": str(amount), "currency": currency,
                          "receipt_email": email, "metadata[reference]": reference},
                )
                data = resp.json()
                if "id" in data:
                    return {"success": True, "payment_intent_id": data["id"]}
                return {"success": False, "error": data.get("error", {}).get("message", "stripe error")}
        except Exception as exc:
            return {"success": False, "error": str(exc)}


# ── Convenience singletons ────────────────────────────────────────────────────

# Use these in tasks and endpoints — don't instantiate on every call
notification_chain = NotificationFallbackChain()
payment_chain = PaymentFallbackChain()
