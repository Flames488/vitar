"""
Vitar v5 - Email Service
Transactional email templates via SendGrid.
"""

import httpx
import logging
from app.core.config import settings
from app.core.recovery import email_circuit, CircuitOpenError

logger = logging.getLogger(__name__)


async def _send(to_email: str, subject: str, html: str):
    if not settings.SENDGRID_API_KEY:
        logger.warning(f"SendGrid not configured. Would have sent: {subject} → {to_email}")
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
            if resp.status_code >= 500:
                raise Exception(f"SendGrid {resp.status_code}: {resp.text[:200]}")
            email_circuit._on_success()
    except Exception as e:
        email_circuit._on_failure()
        logger.error(
            "Email send failed",
            extra={"to": to_email[:4] + "***", "subject": subject, "error": str(e)},
        )


def _noop():
    """Dummy function used to probe circuit state."""
    pass


def _base_template(title: str, body: str) -> str:
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
    </div>
  </div>
</body>
</html>
"""


async def send_welcome_email(to_email: str, full_name: str, clinic_name: str):
    html = _base_template(
        f"Welcome to Vitar, {full_name.split()[0]}! 🎉",
        f"""
        <p>Your clinic <strong>{clinic_name}</strong> is ready to go.</p>
        <p>You're on a <strong>14-day free trial</strong> with full access to:</p>
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
        <p>Your <strong>14-day free trial</strong> for <strong>{clinic_name}</strong> is almost over.</p>
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
        <p>Hi <strong>{patient_name}</strong>,</p>
        <p>Your appointment has been confirmed:</p>
        <table style="width:100%;border-collapse:collapse;margin:16px 0;">
          <tr><td style="padding:8px;background:#f5f5f5;font-weight:600;width:40%;">Doctor</td><td style="padding:8px;">Dr. {doctor_name}</td></tr>
          <tr><td style="padding:8px;background:#f5f5f5;font-weight:600;">Clinic</td><td style="padding:8px;">{clinic_name}</td></tr>
          <tr><td style="padding:8px;background:#f5f5f5;font-weight:600;">Date & Time</td><td style="padding:8px;">{scheduled_at_str}</td></tr>
        </table>
        <p>Need to cancel? <a href="{cancel_url}" style="color:#0d9488;">Click here</a> (please give at least 2 hours notice).</p>
        """,
    )
    await _send(to_email, f"Appointment confirmed — {scheduled_at_str}", html)


async def send_subscription_activated_email(to_email: str, clinic_name: str, plan: str, amount: str):
    html = _base_template(
        "Subscription Activated 🎉",
        f"""
        <p>Payment confirmed for <strong>{clinic_name}</strong>.</p>
        <table style="width:100%;border-collapse:collapse;margin:16px 0;">
          <tr><td style="padding:8px;background:#f5f5f5;font-weight:600;width:40%;">Plan</td><td style="padding:8px;">{plan.title()}</td></tr>
          <tr><td style="padding:8px;background:#f5f5f5;font-weight:600;">Amount</td><td style="padding:8px;">{amount}</td></tr>
        </table>
        <a href="{settings.FRONTEND_URL}/dashboard" class="btn">Go to Dashboard →</a>
        """,
    )
    await _send(to_email, f"Vitar {plan.title()} plan activated", html)
