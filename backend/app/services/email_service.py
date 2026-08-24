"""
Vitar v5 - Email Service
Transactional email templates. Sends via Resend if RESEND_API_KEY is set
(preferred — simple domain verification, no unified-login headaches),
falling back to SendGrid if only SENDGRID_API_KEY is set.
"""

import html as _html_mod
import httpx
import logging
from app.core.config import settings
from app.core.recovery import email_circuit, CircuitOpenError

logger = logging.getLogger(__name__)


def _esc(value) -> str:
    """Escape a user-controlled value before dropping it into an HTML email
    body. Every field here can originate from an unauthenticated public form
    (booking, registration) — without this, a patient's own name or "reason
    for visit" free-text field could inject HTML (e.g. a phishing link) into
    an email opened by clinic staff or another patient."""
    return _html_mod.escape(str(value)) if value else value


async def _send(to_email: str, subject: str, html: str):
    if not settings.RESEND_API_KEY and not settings.SENDGRID_API_KEY:
        logger.warning(f"No email provider configured. Would have sent: {subject} → {to_email}")
        return
    try:
        email_circuit.execute(_noop)  # check circuit state before attempting
    except CircuitOpenError:
        logger.warning(
            "Email circuit OPEN — skipping send",
            extra={"to": to_email[:4] + "***", "subject": subject},
        )
        return
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            if settings.RESEND_API_KEY:
                resp = await client.post(
                    "https://api.resend.com/emails",
                    headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
                    json={
                        "from": f"{settings.EMAIL_FROM_NAME} <{settings.EMAIL_FROM}>",
                        "to": [to_email],
                        "subject": subject,
                        "html": html,
                    },
                )
                provider = "resend"
            else:
                resp = await client.post(
                    "https://api.sendgrid.com/v3/mail/send",
                    headers={"Authorization": f"Bearer {settings.SENDGRID_API_KEY}"},
                    json={
                        "personalizations": [{"to": [{"email": to_email}]}],
                        "from": {"email": settings.EMAIL_FROM, "name": settings.EMAIL_FROM_NAME},
                        "subject": subject,
                        "content": [{"type": "text/html", "value": html}],
                    },
                )
                provider = "sendgrid"

            if resp.status_code >= 400:
                raise Exception(f"{provider} {resp.status_code}: {resp.text[:200]}")
            email_circuit._on_success()
            logger.info(
                "Email sent",
                extra={"to": to_email[:4] + "***", "subject": subject, "provider": provider},
            )
    except Exception as e:
        email_circuit._on_failure()
        logger.error(
            "Email send failed",
            extra={"to": to_email[:4] + "***", "subject": subject, "error": str(e)},
        )


def _noop():
    """Dummy function used to probe circuit state."""
    pass


def _base_template(title: str, body: str, footer_extra: str = "") -> str:
    return f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f5f5f5; margin: 0; padding: 20px; }}
    .container {{ max-width: 600px; margin: 0 auto; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
    .header {{ background: #0d9488; padding: 24px 32px; }}
    .header h1 {{ color: white; margin: 0; font-size: 22px; font-weight: 600; }}
    .content {{ padding: 32px; color: #333; line-height: 1.6; }}
    .btn {{ display: inline-block; background: #0d9488; color: white !important; text-decoration: none; padding: 12px 24px; border-radius: 6px; font-weight: 600; margin: 16px 0; }}
    .footer {{ background: #f9f9f9; padding: 16px 32px; font-size: 12px; color: #999; text-align: center; border-top: 1px solid #eee; }}
    .footer a {{ color: #999; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header"><h1>Vitar Health</h1></div>
    <div class="content">
      <h2 style="margin-top:0;color:#111;">{title}</h2>
      {body}
    </div>
    <div class="footer">
      &copy; 2025 Vitar Health. All rights reserved.<br>
      This email was sent because you registered on Vitar.
      {footer_extra}
    </div>
  </div>
</body>
</html>
"""


async def send_welcome_email(to_email: str, full_name: str, clinic_name: str):
    html = _base_template(
        f"Welcome to Vitar, {_esc(full_name.split()[0])}! 🎉",
        f"""
        <p>Your clinic <strong>{_esc(clinic_name)}</strong> is ready to go.</p>
        <p>You're on a <strong>30-day free trial</strong> with full access to:</p>
        <ul>
          <li>AI-powered no-show prediction</li>
          <li>Smart multi-channel reminders (SMS, WhatsApp, Email)</li>
          <li>Public booking page for patients</li>
          <li>Real-time analytics dashboard</li>
        </ul>
        <a href="{settings.FRONTEND_URL}/dashboard" class="btn">Go to Dashboard →</a>
        <p style="color:#666;font-size:14px;">Need help? Chat with our AI assistant directly in the app.</p>
        """,
    )
    await _send(to_email, f"Welcome to Vitar — {clinic_name} is live!", html)


async def send_verification_email(to_email: str, full_name: str, token: str):
    verify_url = f"{settings.FRONTEND_URL}/verify-email?token={token}"
    html = _base_template(
        "Verify your email address",
        f"""
        <p>Hi {_esc(full_name.split()[0]) if full_name else 'there'},</p>
        <p>Please confirm this is your email address so we can reach you about your account.</p>
        <a href="{verify_url}" class="btn">Verify Email →</a>
        <p style="color:#999;font-size:13px;">Your account already works fully in the meantime — this just confirms we can reach you.</p>
        """,
    )
    await _send(to_email, "Verify your email — Vitar", html)


async def send_password_reset_email(to_email: str, token: str, frontend_url: str):
    reset_url = f"{frontend_url}/reset-password?token={token}"
    html = _base_template(
        "Reset Your Password",
        f"""
        <p>We received a request to reset your Vitar password.</p>
        <p>Click the button below to set a new password. This link expires in <strong>1 hour</strong>.</p>
        <a href="{reset_url}" class="btn">Reset Password →</a>
        <p style="color:#999;font-size:13px;">If you didn't request this, you can safely ignore this email.</p>
        """,
    )
    await _send(to_email, "Reset your Vitar password", html)


async def send_trial_expiry_warning(to_email: str, clinic_name: str, days_left: int):
    html = _base_template(
        f"Your trial ends in {days_left} day{'s' if days_left != 1 else ''}",
        f"""
        <p>Your <strong>30-day free trial</strong> for <strong>{_esc(clinic_name)}</strong> is almost over.</p>
        <p>Upgrade now to keep your appointments, reminders, and analytics running without interruption.</p>
        <a href="{settings.FRONTEND_URL}/settings/billing" class="btn">Upgrade Now →</a>
        <p style="color:#666;font-size:14px;">
          Questions? Reply to this email or use the in-app chat.
        </p>
        """,
    )
    await _send(to_email, f"⏰ {days_left} days left on your Vitar trial", html)


async def send_appointment_confirmation_email(
    to_email: str,
    patient_name: str,
    doctor_name: str,
    clinic_name: str,
    scheduled_at_str: str,
    cancel_token: str,
):
    cancel_url = f"{settings.FRONTEND_URL}/cancel/{cancel_token}"
    html = _base_template(
        "Appointment Confirmed",
        f"""
        <p>Hi <strong>{_esc(patient_name)}</strong>,</p>
        <p>Your appointment has been confirmed:</p>
        <table style="width:100%;border-collapse:collapse;margin:16px 0;">
          <tr><td style="padding:8px;background:#f5f5f5;font-weight:600;width:40%;">Doctor</td><td style="padding:8px;">Dr. {_esc(doctor_name)}</td></tr>
          <tr><td style="padding:8px;background:#f5f5f5;font-weight:600;">Clinic</td><td style="padding:8px;">{_esc(clinic_name)}</td></tr>
          <tr><td style="padding:8px;background:#f5f5f5;font-weight:600;">Date & Time</td><td style="padding:8px;">{scheduled_at_str}</td></tr>
        </table>
        <p>Need to cancel? <a href="{cancel_url}" style="color:#0d9488;">Click here</a> (please give at least 2 hours notice).</p>
        """,
    )
    await _send(to_email, f"Appointment confirmed — {scheduled_at_str}", html)


async def send_new_booking_email(
    to_email: str,
    clinic_name: str,
    patient_name: str,
    patient_phone: str,
    doctor_name: str,
    scheduled_at_str: str,
    reason: str,
    appointment_id: str,
):
    html = _base_template(
        "New Appointment Booked",
        f"""
        <p>A new appointment was just booked at <strong>{_esc(clinic_name)}</strong>:</p>
        <table style="width:100%;border-collapse:collapse;margin:16px 0;">
          <tr><td style="padding:8px;background:#f5f5f5;font-weight:600;width:40%;">Patient</td><td style="padding:8px;">{_esc(patient_name)} ({_esc(patient_phone)})</td></tr>
          <tr><td style="padding:8px;background:#f5f5f5;font-weight:600;">Doctor</td><td style="padding:8px;">Dr. {_esc(doctor_name)}</td></tr>
          <tr><td style="padding:8px;background:#f5f5f5;font-weight:600;">Date & Time</td><td style="padding:8px;">{scheduled_at_str}</td></tr>
          {f'<tr><td style="padding:8px;background:#f5f5f5;font-weight:600;">Reason</td><td style="padding:8px;">{_esc(reason)}</td></tr>' if reason else ''}
        </table>
        <a href="{settings.FRONTEND_URL}/dashboard/appointments/{appointment_id}" class="btn">View Appointment →</a>
        """,
    )
    await _send(to_email, f"New booking: {patient_name} — {scheduled_at_str}", html)


async def send_subscription_activated_email(
    to_email: str, clinic_name: str, plan: str, amount: str, period_end_str: str = "",
):
    html = _base_template(
        "Payment Received — Subscription Activated",
        f"""
        <p>Dear {_esc(clinic_name)} Team,</p>
        <p>Thank you for your payment. This is to confirm that we have received your subscription
        payment, and your Vitar account has been upgraded accordingly.</p>
        <table style="width:100%;border-collapse:collapse;margin:16px 0;">
          <tr><td style="padding:8px;background:#f5f5f5;font-weight:600;width:40%;">Clinic</td><td style="padding:8px;">{_esc(clinic_name)}</td></tr>
          <tr><td style="padding:8px;background:#f5f5f5;font-weight:600;">Plan</td><td style="padding:8px;">{plan.title()}</td></tr>
          <tr><td style="padding:8px;background:#f5f5f5;font-weight:600;">Amount Paid</td><td style="padding:8px;">{amount}</td></tr>
          <tr><td style="padding:8px;background:#f5f5f5;font-weight:600;">Status</td><td style="padding:8px;">Active</td></tr>
          {f'<tr><td style="padding:8px;background:#f5f5f5;font-weight:600;">Renews / Expires</td><td style="padding:8px;">{_esc(period_end_str)}</td></tr>' if period_end_str else ''}
        </table>
        <p>Your {plan.title()} plan is live now — no further action is required on your end.</p>
        <a href="{settings.FRONTEND_URL}/dashboard" class="btn">Go to Dashboard →</a>
        <p style="color:#666;font-size:14px;">
          Should you have any questions about this payment or your account, please don't hesitate
          to reach us directly at {settings.EMAIL_FROM}.
        </p>
        <p style="color:#666;font-size:14px;margin-bottom:0;">
          Thank you for your continued trust in Vitar.
        </p>
        """,
    )
    await _send(to_email, f"Payment Received — Your Vitar {plan.title()} Subscription Is Active", html)


async def send_payment_received_email(
    to_email: str,
    clinic_name: str,
    patient_name: str,
    total_amount: str,
    clinic_share: str,
    paystack_fee: str,
    payout_hours: int,
    appointment_id: str,
):
    """
    Sent to the clinic the moment a patient's booking payment clears —
    distinct from notify_new_booking's generic "new appointment" alert,
    which fires for free bookings too and says nothing about money.
    """
    html = _base_template(
        "Payment Received",
        f"""
        <p>Dear {_esc(clinic_name)} Team,</p>
        <p>We are writing to confirm that a patient payment has been received for an appointment
        at <strong>{_esc(clinic_name)}</strong>.</p>
        <table style="width:100%;border-collapse:collapse;margin:16px 0;">
          <tr><td style="padding:8px;background:#f5f5f5;font-weight:600;width:40%;">Patient</td><td style="padding:8px;">{_esc(patient_name)}</td></tr>
          <tr><td style="padding:8px;background:#f5f5f5;font-weight:600;">Amount Paid</td><td style="padding:8px;">{total_amount}</td></tr>
          <tr><td style="padding:8px;background:#f5f5f5;font-weight:600;">Paystack Processing Fee</td><td style="padding:8px;">-{paystack_fee}</td></tr>
          <tr><td style="padding:8px;background:#f5f5f5;font-weight:600;">Your Payout</td><td style="padding:8px;"><strong>{clinic_share}</strong></td></tr>
        </table>
        <p>This amount will be transferred to your registered bank account within
        <strong>{payout_hours} hours</strong>. No action is required on your part.</p>
        <a href="{settings.FRONTEND_URL}/dashboard/appointments/{appointment_id}" class="btn">View Appointment →</a>
        <p style="color:#666;font-size:14px;">
          Should you have any questions about this payment or your payout, please reach us at
          {settings.EMAIL_FROM}.
        </p>
        <p style="color:#666;font-size:14px;margin-bottom:0;">
          Thank you for partnering with Vitar.
        </p>
        """,
    )
    await _send(to_email, f"Payment Received — {total_amount} for {patient_name}'s Appointment", html)


async def send_feature_spotlight_email(
    to_email: str,
    full_name: str,
    subject: str,
    headline: str,
    body_html: str,
    unsubscribe_token: str,
    closer: str = None,
):
    """Mon/Wed/Fri feature-spotlight email — see app.services.feature_spotlight
    for the rotating content list and app.workers.tasks.send_feature_spotlight
    for the send loop. `closer` is the optional short Monday-motivation /
    Friday-weekend line. footer_extra carries the unsubscribe link required
    by Resend/inbox spam policy for any recurring, non-transactional email."""
    unsubscribe_url = f"{settings.FRONTEND_URL}/unsubscribe?token={unsubscribe_token}"
    closer_html = f'<p style="color:#0d9488;font-weight:600;">{closer}</p>' if closer else ""
    html = _base_template(
        headline,
        f"""
        <p>Hi {_esc(full_name.split()[0]) if full_name else 'there'},</p>
        {body_html}
        <a href="{settings.FRONTEND_URL}/dashboard" class="btn">Open Vitar →</a>
        {closer_html}
        """,
        footer_extra=f'<br><a href="{unsubscribe_url}">Unsubscribe from these tips</a>',
    )
    await _send(to_email, subject, html)
