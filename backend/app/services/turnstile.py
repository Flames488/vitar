"""
Vitar — Cloudflare Turnstile verification.

Bot protection for the two unauthenticated, public-facing forms most
exposed to abuse: clinic registration and patient booking. Rate limiting
(app.core.middleware) already covers volume; this covers automated
submission specifically.

If TURNSTILE_SECRET_KEY isn't set (e.g. local dev), verification is
skipped entirely rather than blocking every submission — this matches
the same "fail open when unconfigured" pattern already used for email/
WhatsApp providers elsewhere in the app.
"""
import logging
from typing import Optional

import httpx

from app.core.config import settings

logger = logging.getLogger("vitar.turnstile")

_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


async def verify_turnstile(token: str, remote_ip: Optional[str] = None) -> bool:
    if not settings.TURNSTILE_SECRET_KEY:
        return True

    if not token:
        return False

    data = {"secret": settings.TURNSTILE_SECRET_KEY, "response": token}
    if remote_ip:
        data["remoteip"] = remote_ip

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(_VERIFY_URL, data=data)
            result = resp.json()
            if not result.get("success"):
                logger.warning(
                    "Turnstile verification failed",
                    extra={"error_codes": result.get("error-codes")},
                )
            return bool(result.get("success"))
    except Exception as exc:
        # Network hiccup or Cloudflare-side outage, not a real verdict either
        # way. Booking/registration is the product's core function — failing
        # closed here would mean a transient network blip on our own side
        # blocks every clinic and patient from using Vitar at all, which is
        # a far worse outcome than a bot occasionally getting through
        # (rate limiting still applies regardless). Fail open, same pattern
        # as the email/WhatsApp provider integrations.
        logger.error(f"Turnstile verification request failed: {exc}")
        return True
