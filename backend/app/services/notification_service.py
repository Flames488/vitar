"""
Vitar v5 - Notification Service
Multi-channel delivery: SMS → WhatsApp → Email with fallback logic.
Supports Termii (NG), Twilio (Global), WhatsApp Cloud API, SendGrid.
"""

import httpx
import logging
from datetime import datetime, timezone
from typing import Optional
from enum import Enum

from app.core.utils import utcnow
from app.core.config import settings
# v10: replaced legacy sync recovery.py circuits with async circuit_breaker.py
from app.core.circuit_breaker import sms_breaker, whatsapp_breaker, email_breaker

logger = logging.getLogger(__name__)


# ─── Channel Enums ────────────────────────────────────────────────────────────

class Channel(str, Enum):
    SMS = "sms"
    WHATSAPP = "whatsapp"
    EMAIL = "email"


class DeliveryResult:
    def __init__(self, success: bool, provider: str, message_id: Optional[str] = None, error: Optional[str] = None):
        self.success = success
        self.provider = provider
        self.message_id = message_id
        self.error = error

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "provider": self.provider,
            "message_id": self.message_id,
            "error": self.error,
            "timestamp": utcnow().isoformat(),
        }


# ─── Message Templates ────────────────────────────────────────────────────────

def build_reminder_message(patient_name: str, doctor_name: str, scheduled_at: datetime, clinic_name: str, cancel_token: str, frontend_url: str) -> str:
    date_str = scheduled_at.strftime("%A, %B %d at %I:%M %p")
    cancel_url = f"{frontend_url}/cancel/{cancel_token}"
    return (
        f"Hi {patient_name}, reminder: appointment with Dr. {doctor_name} "
        f"at {clinic_name} on {date_str}. "
        f"To cancel: {cancel_url} | Vitar"
    )


def build_confirmation_message(patient_name: str, doctor_name: str, scheduled_at: datetime, clinic_name: str, confirm_token: str, frontend_url: str) -> str:
    date_str = scheduled_at.strftime("%A, %B %d at %I:%M %p")
    confirm_url = f"{frontend_url}/confirm/{confirm_token}"
    return (
        f"Hi {patient_name}, your appointment with Dr. {doctor_name} "
        f"at {clinic_name} is confirmed for {date_str}. "
        f"Confirm: {confirm_url} | Vitar"
    )


def build_no_show_followup_message(patient_name: str, clinic_name: str, clinic_phone: str) -> str:
    return (
        f"Hi {patient_name}, we missed you at {clinic_name} today. "
        f"Please call {clinic_phone} to reschedule your appointment. | Vitar"
    )


def build_reschedule_message(patient_name: str, doctor_name: str, new_dt: datetime, clinic_name: str) -> str:
    date_str = new_dt.strftime("%A, %B %d at %I:%M %p")
    return (
        f"Hi {patient_name}, your appointment with Dr. {doctor_name} "
        f"at {clinic_name} has been rescheduled to {date_str}. | Vitar"
    )


def build_slot_available_message(patient_name: str, doctor_name: str, slot_dt: datetime, clinic_name: str, booking_url: str) -> str:
    date_str = slot_dt.strftime("%A, %B %d at %I:%M %p")
    return (
        f"Hi {patient_name}, a slot just opened with Dr. {doctor_name} "
        f"at {clinic_name} on {date_str}. Book now: {booking_url} | Vitar"
    )


# ─── SMS Providers ────────────────────────────────────────────────────────────

async def send_sms_termii(phone: str, message: str, sender_id: str = "Vitar") -> DeliveryResult:
    """Termii - Nigerian SMS provider. Protected by async sms_breaker (v10)."""
    if not settings.TERMII_API_KEY:
        return DeliveryResult(False, "termii", error="Termii API key not configured")

    async def _call():
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(
                "https://api.ng.termii.com/api/sms/send",
                json={
                    "to": phone,
                    "from": sender_id or settings.TERMII_SENDER_ID,
                    "sms": message,
                    "type": "plain",
                    "channel": "generic",
                    "api_key": settings.TERMII_API_KEY,
                },
            )
            data = resp.json()
            if resp.status_code == 200 and data.get("message_id"):
                return DeliveryResult(True, "termii", message_id=str(data["message_id"]))
            raise RuntimeError(f"Termii error: {data}")

    result = await sms_breaker.call_async(
        _call,
        fallback=DeliveryResult(False, "termii", error="SMS circuit open or timed out"),
        timeout=8.0,
    )
    return result


async def send_sms_twilio(phone: str, message: str) -> DeliveryResult:
    """Twilio - Global SMS fallback."""
    if not settings.TWILIO_ACCOUNT_SID:
        return DeliveryResult(False, "twilio", error="Twilio not configured")
    try:
        async with httpx.AsyncClient(
            auth=(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN),
            timeout=15,
        ) as client:
            resp = await client.post(
                f"https://api.twilio.com/2010-04-01/Accounts/{settings.TWILIO_ACCOUNT_SID}/Messages.json",
                data={"From": settings.TWILIO_FROM_NUMBER, "To": phone, "Body": message},
            )
            data = resp.json()
            if resp.status_code in (200, 201) and data.get("sid"):
                return DeliveryResult(True, "twilio", message_id=data["sid"])
            return DeliveryResult(False, "twilio", error=str(data.get("message")))
    except Exception as e:
        logger.error(f"Twilio SMS failed: {e}")
        return DeliveryResult(False, "twilio", error=str(e))


# ─── WhatsApp ─────────────────────────────────────────────────────────────────

async def send_whatsapp(phone: str, message: str) -> DeliveryResult:
    """WhatsApp Cloud API (Meta). Protected by async whatsapp_breaker (v10)."""
    if not settings.WHATSAPP_ACCESS_TOKEN:
        return DeliveryResult(False, "whatsapp", error="WhatsApp not configured")

    async def _call():
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(
                f"https://graph.facebook.com/v18.0/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages",
                headers={"Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}"},
                json={
                    "messaging_product": "whatsapp",
                    "to": phone.lstrip("+"),
                    "type": "text",
                    "text": {"body": message},
                },
            )
            data = resp.json()
            if resp.status_code == 200 and data.get("messages"):
                return DeliveryResult(True, "whatsapp", message_id=data["messages"][0]["id"])
            raise RuntimeError(f"WhatsApp error: {data}")

    result = await whatsapp_breaker.call_async(
        _call,
        fallback=DeliveryResult(False, "whatsapp", error="WhatsApp circuit open or timed out"),
        timeout=8.0,
    )
    return result


# ─── Email ────────────────────────────────────────────────────────────────────

async def send_email_sendgrid(to_email: str, subject: str, html_body: str, text_body: str = "") -> DeliveryResult:
    """SendGrid email delivery. Protected by async email_breaker (v10)."""
    if not settings.SENDGRID_API_KEY:
        return DeliveryResult(False, "sendgrid", error="SendGrid not configured")

    async def _call():
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                "https://api.sendgrid.com/v3/mail/send",
                headers={"Authorization": f"Bearer {settings.SENDGRID_API_KEY}"},
                json={
                    "personalizations": [{"to": [{"email": to_email}]}],
                    "from": {"email": settings.EMAIL_FROM, "name": settings.EMAIL_FROM_NAME},
                    "subject": subject,
                    "content": [
                        {"type": "text/plain", "value": text_body or html_body},
                        {"type": "text/html", "value": html_body},
                    ],
                },
            )
            if resp.status_code == 202:
                return DeliveryResult(True, "sendgrid", message_id=resp.headers.get("X-Message-Id"))
            raise RuntimeError(f"SendGrid {resp.status_code}")

    result = await email_breaker.call_async(
        _call,
        fallback=DeliveryResult(False, "sendgrid", error="Email circuit open or timed out"),
        timeout=10.0,
    )
    return result


# ─── Fallback Chain ───────────────────────────────────────────────────────────

async def send_notification_with_fallback(
    channel: str,
    phone: Optional[str],
    email: Optional[str],
    message: str,
    subject: str = "Appointment Reminder",
    country: str = "NG",
    sender_id: str = "Vitar",
) -> DeliveryResult:
    """
    Attempts delivery on requested channel.
    Falls back: SMS → WhatsApp → Email if prior channels fail.
    """
    attempted_channels = []

    async def try_sms() -> Optional[DeliveryResult]:
        if not phone:
            return None
        attempted_channels.append("sms")
        if country == "NG":
            result = await send_sms_termii(phone, message, sender_id)
            if result.success:
                return result
            logger.warning(f"Termii failed, trying Twilio: {result.error}")
        result = await send_sms_twilio(phone, message)
        return result

    async def try_whatsapp() -> Optional[DeliveryResult]:
        if not phone:
            return None
        attempted_channels.append("whatsapp")
        return await send_whatsapp(phone, message)

    async def try_email() -> Optional[DeliveryResult]:
        if not email:
            return None
        attempted_channels.append("email")
        html = f"<p>{message.replace(chr(10), '<br>')}</p>"
        return await send_email_sendgrid(email, subject, html, message)

    # Attempt primary channel
    result = None
    if channel == Channel.SMS:
        result = await try_sms()
    elif channel == Channel.WHATSAPP:
        result = await try_whatsapp()
    elif channel == Channel.EMAIL:
        result = await try_email()

    if result and result.success:
        try:
            from app.core.metrics import record_notification
            record_notification(channel if isinstance(channel, str) else channel.value, "sent")
        except Exception:
            pass
        return result

    # Fallback chain
    logger.info(f"Primary channel {channel} failed, attempting fallback chain")
    for fallback in [try_sms, try_whatsapp, try_email]:
        result = await fallback()
        if result and result.success:
            logger.info(f"Fallback succeeded via {result.provider}")
            try:
                from app.core.metrics import record_notification
                record_notification(result.provider or "fallback", "sent")
            except Exception:
                pass
            return result

    try:
        from app.core.metrics import record_notification
        record_notification(channel if isinstance(channel, str) else channel.value, "failed")
    except Exception:
        pass

    return DeliveryResult(
        False,
        "all_failed",
        error=f"All channels failed after trying: {attempted_channels}",
    )
