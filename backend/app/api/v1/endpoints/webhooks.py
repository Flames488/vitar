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
from sqlalchemy.exc import IntegrityError
from pydantic import BaseModel
from typing import Optional
import logging
import json
import secrets

from app.core.utils import utcnow
from app.core.database import get_db
from app.core.logging import get_logger, log_payment_event
from app.core.idempotency import is_webhook_processed, invalidate
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


def finalize_paid_appointment(appointment, data: dict, db: Session):
    from app.core.cache import cache
    from app.models.models import (
        AppointmentStatus,
        PatientPayment,
        PaymentProvider,
        PaymentStatus,
        Payout,
        PayoutStatus,
    )

    from app.core.config import settings

    reference = data.get("reference") or appointment.payment_provider_ref
    amount_kobo = int(data.get("amount") or round(float(appointment.payment_amount or 0) * 100))
    amount = amount_kobo / 100
    now = utcnow()

    # Live discovery (2026-08-19): this used to split PLATFORM_PAYOUT_FEE_PCT
    # off the raw patient-paid amount, ignoring that Paystack takes its own
    # processing fee before anything ever reaches our settlement account.
    # Real example: patient paid ₦5,000, Paystack's cut was ₦175 (3.5%,
    # bank-transfer channel), we only netted ₦4,825 — but the old math still
    # promised the clinic 98% of the original ₦5,000 (₦4,900), which is MORE
    # than we actually received. Paystack includes its own fee on every
    # transaction payload (`fees`, in kobo) — subtract that first to get
    # what we actually netted, then split *that* between platform and
    # clinic, so the two shares can never add up to more than we were
    # actually paid.
    paystack_fee_kobo = int(data.get("fees") or 0)
    net_kobo = max(amount_kobo - paystack_fee_kobo, 0)

    fee_pct = max(0.0, min(1.0, settings.PLATFORM_PAYOUT_FEE_PCT))
    platform_share_kobo = round(net_kobo * fee_pct)
    clinic_share_kobo = net_kobo - platform_share_kobo
    platform_share = platform_share_kobo / 100
    clinic_share = clinic_share_kobo / 100

    # Cancel-then-webhook race: the patient cancelled (or a stale/duplicate
    # charge.success is being replayed) after the appointment was already
    # CANCELLED. Do NOT resurrect it to APPROVED and do NOT create/dispatch a
    # payout — that would pay a clinic for a visit that isn't happening.
    # Still record the money as received (PatientPayment PAID) and alert so
    # the patient gets refunded.
    cancelled = appointment.status in (AppointmentStatus.CANCELLED, AppointmentStatus.NO_SHOW)

    appointment.payment_status = PaymentStatus.PAID
    if not cancelled:
        appointment.status = AppointmentStatus.APPROVED
    appointment.paid_at = now
    appointment.payment_provider_ref = reference

    payment = db.query(PatientPayment).filter(PatientPayment.appointment_id == appointment.id).first()
    if not payment:
        payment = PatientPayment(
            appointment_id=appointment.id,
            clinic_id=appointment.clinic_id,
            patient_id=appointment.patient_id,
            provider=PaymentProvider.PAYSTACK,
            provider_reference=reference,
            total_amount=amount,
            clinic_share=clinic_share,
            platform_share=platform_share,
            currency=data.get("currency", appointment.payment_currency or "NGN"),
            status=PaymentStatus.PAID,
            paid_at=now,
            extra_data={"paystack_status": data.get("status")},
        )
        db.add(payment)
    else:
        payment.status = PaymentStatus.PAID
        payment.paid_at = now

    payout = db.query(Payout).filter(Payout.appointment_id == appointment.id).first()
    # clinic_share_kobo can be 0 if Paystack's fee ate the whole payment
    # (tiny amounts) — there is nothing to transfer and Paystack rejects a
    # zero-value transfer, so skip creating a payout row for it.
    if not payout and not cancelled and clinic_share_kobo > 0:
        payout = Payout(
            appointment_id=appointment.id,
            hospital_id=appointment.clinic_id,
            amount=clinic_share_kobo,
            status=PayoutStatus.PENDING_PAYOUT.value,
        )
        db.add(payout)

    try:
        db.commit()
    except IntegrityError:
        # The webhook and a patient's manual "verify payment" poll can both
        # see "no payment row yet" and both try to INSERT — the loser hits
        # PatientPayment.provider_reference's unique constraint. The payment
        # was still recorded successfully by whichever request won, so treat
        # this as success rather than surfacing a 500.
        db.rollback()
        logger.info(f"Payment finalize race for appointment {appointment.id} — already recorded by a concurrent request.")
        db.refresh(appointment)
        payout = db.query(Payout).filter(Payout.appointment_id == appointment.id).first()
        return payout
    # Capture everything the post-commit side effects need NOW, while the
    # session is known-clean. The notify blocks below don't roll back on
    # error, so a failure in one of them can leave the session in a
    # PendingRollbackError state — reading payout.status (an expired
    # attribute) after that point would raise and abort the whole webhook
    # even though the payment + payout are already durably committed.
    payout_id = payout.id if payout else None
    payout_pending = bool(payout) and (
        (payout.status if isinstance(payout.status, str) else getattr(payout.status, "value", None))
        == PayoutStatus.PENDING_PAYOUT.value
    )

    if payout_id:
        cache.set(
            "admin:payouts:latest",
            {"payout_id": payout_id, "appointment_id": appointment.id, "hospital_id": appointment.clinic_id},
            ttl=24 * 60 * 60,
        )

    # Automatic clinic payout: transfer the clinic's share to its bank the
    # moment this payment is confirmed, after a short hold window. Dispatched
    # here (not waited on) so it runs while the funds are still in Vitar's
    # Paystack balance — before Paystack's daily auto-settlement sweeps them
    # to Vitar's own bank. auto_send_pending_payouts is the hourly backstop
    # if this dispatch is lost. Only fires for a freshly-created PENDING
    # payout — a re-run of an already-sent payment skips it. Dispatched
    # before the notify blocks below so a failure there can't stop it.
    if payout_pending:
        try:
            from app.workers.tasks import send_clinic_payout

            send_clinic_payout.apply_async(
                (payout_id,),
                countdown=max(0, settings.PAYOUT_AUTO_SEND_AFTER_MINUTES * 60),
            )
        except Exception as e:
            logger.error(f"Failed to dispatch automatic payout for {payout_id}: {e}")

    if not cancelled:
        try:
            from app.workers.push_tasks import notify_new_booking
            notify_new_booking.delay(appointment.id)
        except Exception as e:
            logger.error(f"Failed to dispatch new-booking notification: {e}")

    try:
        from app.models.models import Clinic, Patient
        from app.services.notifications import notify

        clinic = db.query(Clinic).filter(Clinic.id == appointment.clinic_id).first()
        patient_row = db.query(Patient).filter(Patient.id == appointment.patient_id).first()
        if cancelled:
            notify(
                event_type="appointment_refund_needed",
                agent_name="billing",
                message=(
                    f"A payment of ₦{amount:,.2f} landed for an appointment at "
                    f"{clinic.name if clinic else 'a clinic'} that was already cancelled. "
                    f"No payout was created — the patient needs a manual refund."
                ),
                related_id=appointment.id,
                link_path="/admin/booking-payments",
            )
        else:
            notify(
                event_type="booking_payment_received",
                agent_name="billing",
                message=(
                    f"{patient_row.full_name if patient_row else 'A patient'} just paid "
                    f"₦{amount:,.2f} for an appointment at {clinic.name if clinic else 'a clinic'}.\n"
                    f"Clinic share: ₦{clinic_share:,.2f} — payout will follow automatically."
                ),
                related_id=payout_id,
                link_path="/admin/booking-payments",
            )
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to dispatch booking-payment-received notification: {e}")

    return payout


def void_payout_for_cancelled_appointment(appointment, db: Session) -> None:
    """
    Called from every appointment-cancellation path (staff-side DELETE and
    the patient's self-service cancel link) right after the appointment
    itself is cancelled. Without this, a Payout row created by
    finalize_paid_appointment() above is otherwise completely unconditional
    — it goes out to the clinic on its normal schedule regardless of
    whether the visit still happens, i.e. the clinic gets paid for a
    cancelled booking with no refund path for the patient at all.

    If the payout hasn't gone out yet, cancel it outright (the auto-send
    job only ever picks up PENDING_PAYOUT rows, so this fully stops it).
    If it already went out, the money already left Vitar's account —
    there's no safe way to auto-reverse that here, so this raises a
    Telegram alert instead of pretending to fix it silently.
    """
    from sqlalchemy import text

    from app.models.models import PaymentStatus, Payout, PayoutStatus, Clinic
    from app.services.notifications import notify

    if appointment.payment_status != PaymentStatus.PAID:
        return

    payout = db.query(Payout).filter(Payout.appointment_id == appointment.id).first()
    if not payout:
        return

    clinic = db.query(Clinic).filter(Clinic.id == appointment.clinic_id).first()
    clinic_name = clinic.name if clinic else "a clinic"

    # Race-safe stop: a single atomic UPDATE that only cancels the payout if
    # it is STILL pending. If send_payout_to_hospital already flipped it to
    # SENT (its transfer went out in the ~15 min hold window), the WHERE
    # clause won't match and we fall through to the "already went out" alert
    # — no chance of a stale read clobbering a SENT row back to CANCELLED.
    # Bound the wait so a genuinely hung send (documented pathology) doesn't
    # block the cancellation request; on timeout, hand off to a background
    # reconcile so the payout still gets stopped once the lock frees.
    try:
        db.execute(text("SET LOCAL statement_timeout = '8s'"))
        result = db.execute(
            text(
                "UPDATE payouts SET status = :cancelled "
                "WHERE id = :id AND status = :pending"
            ),
            {
                "cancelled": PayoutStatus.CANCELLED.value,
                "pending": PayoutStatus.PENDING_PAYOUT.value,
                "id": payout.id,
            },
        )
        db.commit()
        stopped = result.rowcount > 0
    except Exception as exc:
        db.rollback()
        logger.warning(f"void_payout: could not update payout {payout.id} inline ({exc}); handing to reconcile task")
        try:
            from app.workers.tasks import reconcile_cancelled_payout
            reconcile_cancelled_payout.apply_async((payout.id,), countdown=30)
        except Exception as e:
            logger.error(f"void_payout: failed to enqueue reconcile for {payout.id}: {e}")
        return

    if stopped:
        notify(
            event_type="appointment_refund_needed",
            agent_name="billing",
            message=f"A paid appointment at {clinic_name} was cancelled — payout stopped before it went "
                    f"out, but the patient already paid and needs a manual refund.",
            related_id=appointment.id,
            link_path="/admin/payouts",
        )
        return

    # Not stopped — re-read the real current status to classify.
    db.refresh(payout)
    if payout.status == PayoutStatus.SENT.value:
        notify(
            event_type="appointment_refund_needed",
            agent_name="billing",
            message=f"A paid appointment at {clinic_name} was cancelled AFTER the payout already went "
                    f"out to the clinic. Needs manual reconciliation — claw back from the clinic or "
                    f"refund the patient yourself.",
            related_id=appointment.id,
            link_path="/admin/payouts",
        )


# ─── Paystack Webhook ────────────────────────────────────────────────────────

@router.post("/paystack")
async def paystack_webhook(
    request: Request,
    x_paystack_signature: str = Header(None),
    db: Session = Depends(get_db),
):
    body = await request.body()

    # No environment-based bypass — verify_webhook fails closed on both a
    # missing signature and an unconfigured secret, regardless of ENVIRONMENT.
    if not billing_service.paystack.verify_webhook(body, x_paystack_signature):
        logger.warning("Paystack webhook signature missing or invalid", extra={"path": str(request.url)})
        raise HTTPException(status_code=400, detail="Invalid signature")

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

    try:
        if event == "charge.success":
            reference = data.get("reference", "")
            from app.models.models import Appointment
            appointment = db.query(Appointment).filter(Appointment.payment_provider_ref == reference).first()
            metadata_appointment_id = metadata.get("appointment_id")
            if not appointment and metadata_appointment_id:
                appointment = db.query(Appointment).filter(Appointment.id == metadata_appointment_id).first()

            if appointment:
                finalize_paid_appointment(appointment, data, db)
                return {"status": "ok"}

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

        elif event in ("transfer.success", "transfer.failed", "transfer.reversed"):
            from app.models.models import Payout, PayoutStatus

            # Match on the Paystack transfer_code we stored; fall back to the
            # payout id embedded in our own transfer reference
            # (vitar-payout-<id>) for the case where the row was created but
            # its transfer_code was never persisted (send timed out on our
            # side after Paystack accepted it).
            transfer_code = data.get("transfer_code")
            reference = data.get("reference") or ""
            payout = None
            if transfer_code:
                payout = db.query(Payout).filter(Payout.paystack_transfer_code == transfer_code).first()
            if not payout and reference.startswith("vitar-payout-"):
                # reference is vitar-payout-<uuid>[-<attempt>]; the uuid is a
                # fixed 36 chars right after the prefix.
                ref_payout_id = reference[len("vitar-payout-"):][:36]
                payout = db.query(Payout).filter(Payout.id == ref_payout_id).first()

            succeeded = event == "transfer.success"
            # Skip only a redundant re-delivery of success; still let a later
            # failure/reversal override a SENT row (money came back).
            if payout and not (succeeded and payout.status == PayoutStatus.SENT.value):
                payout.status = PayoutStatus.SENT.value if succeeded else PayoutStatus.FAILED.value
                if succeeded:
                    if not payout.sent_at:
                        payout.sent_at = utcnow()
                    if transfer_code and not payout.paystack_transfer_code:
                        payout.paystack_transfer_code = transfer_code
                db.commit()

                if not succeeded:
                    from app.api.v1.endpoints.admin_payouts import bump_payout_attempt
                    bump_payout_attempt(payout.id)
                    try:
                        from app.models.models import Clinic
                        from app.services.notifications import notify

                        clinic = db.query(Clinic).filter(Clinic.id == payout.hospital_id).first()
                        notify(
                            event_type="payout_send_timeout",
                            agent_name="billing",
                            message=(
                                f"A payout of ₦{payout.amount / 100:,.2f} to "
                                f"{clinic.name if clinic else 'a clinic'} was reported "
                                f"{event.split('.')[-1]} by Paystack — marked FAILED, needs manual review."
                            ),
                            related_id=payout.id,
                            link_path="/admin/payouts",
                        )
                    except Exception as e:
                        logger.error(f"Failed to dispatch transfer-failed notification: {e}")
    except Exception:
        # We already marked this event_id as processed (atomic SET NX above,
        # before dispatch) so a raw exception here — DB blip, provider SDK
        # error, etc — would otherwise get silently dropped as "duplicate"
        # on Paystack's retry, since is_webhook_processed() would now return
        # True even though nothing actually got applied. Clear the key so
        # the retry gets a real second attempt, then let the 500 through so
        # Paystack knows to retry in the first place.
        if event_id:
            invalidate("webhook", f"paystack:{event}:{event_id}")
        raise

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

    # Fail closed — no unverified fallback. A missing signature header or an
    # unconfigured secret must reject the request, not silently accept an
    # unsigned payload.
    if not webhook_secret or not stripe_signature:
        logger.warning("Stripe webhook rejected — signature or secret missing")
        raise HTTPException(status_code=400, detail="Invalid signature")

    try:
        import stripe  # type: ignore
        event_obj = stripe.Webhook.construct_event(body, stripe_signature, webhook_secret)
    except Exception as exc:
        logger.warning(f"Stripe webhook validation failed: {exc}")
        raise HTTPException(status_code=400, detail="Invalid Stripe signature")

    event_type = event_obj.get("type", "") if isinstance(event_obj, dict) else event_obj.type
    event_id = (event_obj.get("id", "") if isinstance(event_obj, dict) else event_obj.id)

    if event_id and is_webhook_processed("stripe", f"{event_type}:{event_id}"):
        return {"status": "ok", "duplicate": True}

    logger.info("Stripe webhook received", extra={"event": event_type, "event_id": event_id})

    data_obj = event_obj.get("data", {}).get("object", {}) if isinstance(event_obj, dict) else event_obj.data.object
    meta = data_obj.get("metadata", {}) if isinstance(data_obj, dict) else {}
    clinic_id = meta.get("clinic_id")
    plan = meta.get("plan")

    try:
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
    except Exception:
        # See paystack_webhook: the idempotency key was already set before
        # dispatch, so an unhandled error here must not leave the event
        # permanently marked "processed" — clear it so Stripe's retry isn't
        # silently swallowed as a duplicate.
        if event_id:
            invalidate("webhook", f"stripe:{event_type}:{event_id}")
        raise

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
    """
    Used to only log this event — nothing anywhere ever wrote a
    SubscriptionPayment row with status=FAILED, which is exactly the
    state retry_failed_payments (workers/tasks.py) scans for. That task
    has therefore never had anything to find since the day it was written
    — a failed charge produced a log line no one was watching and then
    disappeared. This now writes the row the dunning task actually needs.
    """
    try:
        from app.models.models import Subscription, SubscriptionPayment, PaymentStatus, PaymentProvider

        metadata = data.get("metadata") or data.get("extra_data") or {}
        clinic_id = metadata.get("clinic_id")
        reference = data.get("reference") or data.get("id") or ""
        amount = float(data.get("amount") or data.get("amount_due") or 0) / 100
        currency = data.get("currency", "NGN")

        log_payment_event("payment_failed", provider, reference, clinic_id)

        if not clinic_id:
            return  # no clinic to attach the failure record to

        sub = db.query(Subscription).filter(Subscription.clinic_id == clinic_id).first()
        if not sub:
            return

        prov_enum = PaymentProvider.PAYSTACK if provider == "paystack" else PaymentProvider.STRIPE
        existing = (
            db.query(SubscriptionPayment).filter(SubscriptionPayment.provider_reference == reference).first()
            if reference else None
        )
        if existing:
            existing.status = PaymentStatus.FAILED
            existing.failed_at = utcnow()
        else:
            db.add(SubscriptionPayment(
                subscription_id=sub.id,
                provider=prov_enum,
                provider_reference=reference or None,  # unique=True — never store "" for a missing ref
                amount=amount,
                currency=currency,
                status=PaymentStatus.FAILED,
                failed_at=utcnow(),
                extra_data={"raw_event_keys": list(data.keys())},
            ))
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.error(f"_handle_payment_failed failed: {exc}")


def _extract_clinic_id(data: dict, db: Session) -> str:
    """Last-resort: look up clinic by Paystack customer email."""
    try:
        email = data.get("customer", {}).get("email", "")
        if email:
            from app.models.models import User, Clinic
            user = db.query(User).filter(User.email == email).first()
            if user:
                clinic = db.query(Clinic).filter(Clinic.owner_id == user.id).first()
                if clinic:
                    return str(clinic.id)
    except Exception:
        pass
    return ""


# ── AI Core: Wabizz inbound-reply webhook (Sales Agent) ─────────────────────

class WabizzReplyPayload(BaseModel):
    phone: str
    message_text: str
    received_at: Optional[str] = None


@router.post("/wabizz-reply")
async def wabizz_reply_webhook(
    body: WabizzReplyPayload,
    request: Request,
    x_wabizz_webhook_secret: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    """
    Wabizz forwards an inbound WhatsApp message on Vitar's connected number
    here. If it matches a 'contacted' lead by phone, flips it to 'replied'
    and notifies — this is how leads move themselves along the pipeline
    without a human having to notice a WhatsApp reply and update Vitar by
    hand.

    Verified via a shared-secret header rather than Wabizz's own webhook
    signature scheme (not confirmed from this codebase) — swap for that
    once known; a shared secret is a safe, standard default meanwhile.
    Unauthenticated requests (missing/wrong secret) get a plain 401, same
    as any other webhook consumer would expect.
    """
    from app.core.config import settings

    if not settings.WABIZZ_WEBHOOK_SECRET or not x_wabizz_webhook_secret or not secrets.compare_digest(
        x_wabizz_webhook_secret, settings.WABIZZ_WEBHOOK_SECRET
    ):
        raise HTTPException(status_code=401, detail="Invalid or missing webhook secret")

    from app.models.models import Lead, LeadStatus
    from app.services.notifications import notify

    lead = db.query(Lead).filter(Lead.phone == body.phone).first()
    if not lead:
        # Not an error — Wabizz forwards every inbound message on the
        # connected number, most of which won't be from a known lead.
        return {"status": "ok", "matched": False}

    if lead.status == LeadStatus.CONTACTED:
        lead.status = LeadStatus.REPLIED
        lead.last_contacted_at = utcnow()
        lead.notes = (lead.notes + "\n\n" if lead.notes else "") + f"[Reply] {body.message_text}"
        db.commit()

        notify(
            event_type="lead_replied",
            agent_name="sales_agent",
            message=f"{lead.clinic_name} replied!",
            related_id=lead.id,
            link_path="/admin/agents/sales",
        )

    return {"status": "ok", "matched": True}
