"""
Vitar — Subscription Analytics Event Tracker

Centralised place for firing subscription lifecycle events.
These get logged structurally AND sent to Sentry as breadcrumbs/messages
so you can track them in the Sentry Issues + Performance dashboards.

Events:
  trial_started
  trial_completed
  subscription_started
  subscription_upgraded
  subscription_cancelled
  payment_failed

Usage (from webhooks.py, billing.py, tasks.py):

    from app.core.subscription_analytics import track_subscription_event
    track_subscription_event("subscription_started", clinic_id="...", plan="growth", amount=25000, currency="NGN")
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def track_subscription_event(
    event: str,
    clinic_id: Optional[str] = None,
    plan: Optional[str] = None,
    amount: Optional[float] = None,
    currency: Optional[str] = None,
    provider: Optional[str] = None,
    reason: Optional[str] = None,
    extra: Optional[dict] = None,
):
    """
    Log and optionally Sentry-capture a subscription lifecycle event.

    Supported events:
      trial_started, trial_completed, subscription_started,
      subscription_upgraded, subscription_cancelled, payment_failed
    """
    data = {
        "event": event,
        "clinic_id": clinic_id,
        "plan": plan,
        "amount": amount,
        "currency": currency,
        "provider": provider,
        "reason": reason,
        **(extra or {}),
    }

    # Structured log — picked up by Loki / CloudWatch
    logger.info("subscription_analytics_event", extra=data)

    # Sentry breadcrumb (shows in every related error's trace)
    _sentry_breadcrumb(event, data)

    # For payment_failed — also capture a Sentry message so it surfaces in Issues
    if event == "payment_failed":
        _sentry_message(
            f"Payment failed: clinic={clinic_id} plan={plan} provider={provider}",
            level="warning",
            data=data,
        )


# ── Convenience wrappers ──────────────────────────────────────────────────────

def trial_started(clinic_id: str, plan: str = "trial"):
    track_subscription_event("trial_started", clinic_id=clinic_id, plan=plan)


def trial_completed(clinic_id: str, days_used: int = 0):
    track_subscription_event("trial_completed", clinic_id=clinic_id, extra={"days_used": days_used})


def subscription_started(clinic_id: str, plan: str, amount: float, currency: str, provider: str):
    track_subscription_event(
        "subscription_started",
        clinic_id=clinic_id, plan=plan, amount=amount, currency=currency, provider=provider,
    )


def subscription_upgraded(clinic_id: str, old_plan: str, new_plan: str, provider: str):
    track_subscription_event(
        "subscription_upgraded",
        clinic_id=clinic_id, plan=new_plan, provider=provider,
        extra={"old_plan": old_plan},
    )


def subscription_cancelled(clinic_id: str, plan: str, reason: Optional[str] = None):
    track_subscription_event(
        "subscription_cancelled",
        clinic_id=clinic_id, plan=plan, reason=reason,
    )


def payment_failed(clinic_id: str, plan: str, amount: float, currency: str, provider: str, reason: str):
    track_subscription_event(
        "payment_failed",
        clinic_id=clinic_id, plan=plan, amount=amount, currency=currency,
        provider=provider, reason=reason,
    )


# ── Internal helpers ─────────────────────────────────────────────────────────

def _sentry_breadcrumb(event: str, data: dict):
    try:
        import sentry_sdk
        sentry_sdk.add_breadcrumb(
            category="subscription",
            message=event,
            data={k: v for k, v in data.items() if v is not None},
            level="info" if event != "payment_failed" else "warning",
        )
    except Exception:
        pass


def _sentry_message(message: str, level: str, data: dict):
    try:
        import sentry_sdk
        with sentry_sdk.push_scope() as scope:
            for k, v in data.items():
                if v is not None:
                    scope.set_extra(k, v)
            sentry_sdk.capture_message(message, level=level)
    except Exception:
        pass
