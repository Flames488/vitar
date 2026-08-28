from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.logging import get_logger
from app.core.security import get_current_superadmin
from app.core.utils import utcnow
from app.models.models import Clinic, HospitalBankAccount, Payout, PayoutStatus, User
from app.services.hospital_payments import hospital_payments

logger = get_logger(__name__)


router = APIRouter(prefix="/admin/payouts", tags=["Admin — Payouts"])


# Paystack rejects a transfer whose reference was used before, even if that
# earlier transfer FAILED — so a failed payout can never be retried on the
# same reference. Track a per-payout attempt number: retries after a genuine
# failure get a fresh reference, while a same-attempt resend (our client
# timed out but Paystack accepted it) keeps the reference so Paystack can
# still dedupe it and we never double-pay.
_PAYOUT_ATTEMPT_TTL = 30 * 24 * 3600


def payout_transfer_reference(payout_id: str) -> str:
    from app.core.cache import cache

    attempt = cache.get(f"payout_send_attempt:{payout_id}") or 0
    return f"vitar-payout-{payout_id}" if not attempt else f"vitar-payout-{payout_id}-{attempt}"


def bump_payout_attempt(payout_id: str) -> None:
    """Call on every transition of a payout into FAILED so its next send
    uses a fresh Paystack transfer reference."""
    from app.core.cache import cache

    key = f"payout_send_attempt:{payout_id}"
    cache.set(key, (cache.get(key) or 0) + 1, ttl=_PAYOUT_ATTEMPT_TTL)


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
    # Guard against an indefinite hang: SELECT ... FOR UPDATE below has no
    # timeout by default. Confirmed live — a run of this function hung for
    # 60s+ and got hard-killed by Celery's 180s task time limit instead of
    # failing cleanly (auto_send_pending_payouts was silently eating its
    # whole time budget every hour on a payout that can never succeed —
    # see the "starter business" Paystack restriction this specific payout
    # hit). Bounding the lock wait to 10s turns a stuck lock into a normal,
    # catchable exception instead of a task timeout.
    db.execute(text("SET LOCAL statement_timeout = '10s'"))
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
        # Without this, a clinic that never set up payout banking has this
        # exact 409 raised silently, every hour, forever, by
        # auto_send_pending_payouts (workers/tasks.py) — with nothing ever
        # telling the admin money is stuck. Alert once per payout (7-day
        # cache TTL) rather than every single hourly retry.
        from app.core.cache import cache
        from app.services.notifications import notify

        alert_key = f"payout_bank_alert:{payout.id}"
        if not cache.get(alert_key):
            clinic = db.query(Clinic).filter(Clinic.id == payout.hospital_id).first()
            notify(
                event_type="payout_blocked_no_bank",
                agent_name="billing",
                message=f"A payout for {clinic.name if clinic else 'a clinic'} "
                        f"(₦{payout.amount / 100:,.2f}) is stuck — the clinic has no verified "
                        f"payout bank account on file yet.",
                related_id=payout.id,
                link_path="/admin/payouts",
            )
            cache.set(alert_key, True, ttl=7 * 24 * 3600)
        raise HTTPException(status_code=409, detail="Hospital has no verified payout account")

    # Stable within one attempt (a resend after our own client timeout keeps
    # the reference so Paystack dedupes it), fresh after a genuine failure
    # (bump_payout_attempt below) so a retry isn't rejected on the burned
    # reference.
    transfer_reference = payout_transfer_reference(payout.id)
    try:
        transfer = await hospital_payments.initiate_transfer(
            amount_kobo=payout.amount,
            recipient_code=account.paystack_recipient_code,
            reason=f"Vitar booking payout - appointment {payout.appointment_id}",
            reference=transfer_reference,
        )
    except Exception as exc:
        # Paystack's "reference already used" message has changed wording
        # over time and has never literally contained "duplicate" — match
        # the stable parts (a reference that already exists / was used
        # before) so a resend after our own client-side timeout is
        # recognised instead of being misfiled as a fresh failure and
        # retried into a double payment.
        msg = str(exc).lower()
        is_dup = "reference" in msg and any(k in msg for k in ("used", "exist", "duplicate", "already"))
        if is_dup:
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
            dup_status = (transfer.get("status") or "").lower()
            if dup_status in ("failed", "abandoned", "reversed"):
                # The earlier attempt definitively did not pay out. Mark
                # FAILED for review and bump the attempt so a retry uses a
                # fresh reference instead of colliding again.
                payout.status = PayoutStatus.FAILED.value
                db.commit()
                bump_payout_attempt(payout.id)
                raise HTTPException(status_code=502, detail=f"Earlier transfer {dup_status} — needs manual review")
            if dup_status != "success":
                # Still pending/processing on Paystack's side. Leave the
                # payout row as-is (NOT failed) so it isn't picked up for
                # another automatic retry while the original is in flight.
                raise HTTPException(
                    status_code=409,
                    detail=f"Transfer already in progress (status: {transfer.get('status')})",
                )
        else:
            # A non-duplicate error here could be a network timeout AFTER
            # Paystack accepted the transfer — do NOT bump the attempt
            # (fresh reference) or a retry could double-pay. Keep the
            # reference stable so a retry hits "duplicate" and verifies the
            # real state instead.
            payout.status = PayoutStatus.FAILED.value
            db.commit()
            raise HTTPException(status_code=502, detail="Paystack transfer failed")

    # initiate_transfer only checks Paystack's top-level `status` boolean —
    # the transfer object's OWN status still has to be inspected. With OTP
    # disabled a new transfer comes back "pending" (accepted, completes
    # async; the transfer.success webhook confirms it) or occasionally
    # "success". Anything else must NOT be recorded as paid.
    tstatus = (transfer.get("status") or "").lower()
    if tstatus == "otp":
        # Transfers OTP is still enabled on the Paystack account — this
        # transfer will never complete without an OTP-finalize step Vitar
        # does not perform. Fail loudly so it gets fixed. Do NOT bump the
        # attempt: the "otp" transfer exists on this reference and could
        # still be finalized manually in the dashboard — a fresh reference
        # could then double-pay.
        payout.status = PayoutStatus.FAILED.value
        db.commit()
        logger.error(f"Payout {payout.id}: Paystack returned status=otp — disable Transfers OTP in the Paystack dashboard")
        raise HTTPException(status_code=502, detail="Paystack Transfers OTP is enabled — disable it to allow automatic payouts")
    if tstatus in ("failed", "abandoned", "reversed"):
        payout.status = PayoutStatus.FAILED.value
        db.commit()
        bump_payout_attempt(payout.id)
        raise HTTPException(status_code=502, detail=f"Paystack transfer {tstatus}")

    payout.status = PayoutStatus.SENT.value
    payout.paystack_transfer_code = transfer.get("transfer_code")
    payout.sent_at = utcnow()
    db.commit()
    db.refresh(payout)

    try:
        from app.services.notifications import notify

        clinic = db.query(Clinic).filter(Clinic.id == payout.hospital_id).first()
        notify(
            event_type="payout_sent",
            agent_name="billing",
            message=(
                f"₦{payout.amount / 100:,.2f} was just sent to "
                f"{clinic.name if clinic else 'a clinic'}'s bank account."
            ),
            related_id=payout.id,
            link_path="/admin/payouts",
        )
    except Exception as exc:
        logger.error(f"Failed to dispatch payout-sent notification: {exc}")

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
    # serialize_payout() reads payout.appointment — eager-load it here so a
    # full page (up to 200 rows) doesn't issue one lazy-load SELECT per row.
    payouts = (
        q.options(joinedload(Payout.appointment))
        .order_by(Payout.created_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )
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
