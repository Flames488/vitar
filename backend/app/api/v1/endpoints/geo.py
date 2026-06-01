"""
Vitar v5 - Geo Endpoints
IP detection + currency/pricing resolution for frontend.
"""

from fastapi import APIRouter, Request, Header
from typing import Optional
from app.services.geo_service import detect_geo_from_ip, detect_geo_from_locale, get_all_plans_for_currency

router = APIRouter()


@router.get("/detect")
async def detect_geo(
    request: Request,
    accept_language: Optional[str] = Header(None),
):
    """
    Auto-detects region from IP, falls back to Accept-Language header.
    Returns currency, pricing tier, and payment provider for frontend.
    """
    ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else "127.0.0.1")
    # Take first IP if comma-separated (proxy chain)
    ip = ip.split(",")[0].strip()

    geo = await detect_geo_from_ip(ip)

    # If IP detection failed, try locale
    if geo.get("source") == "default" and accept_language:
        locale_geo = detect_geo_from_locale(accept_language)
        if locale_geo.get("source") == "locale":
            geo = locale_geo

    # Add plans for the detected currency
    geo["plans"] = get_all_plans_for_currency(geo["currency"])

    return geo


@router.get("/plans/{currency}")
def get_plans_by_currency(currency: str):
    """Explicit currency override — e.g., ?currency=NGN."""
    plans = get_all_plans_for_currency(currency.upper())
    return {"currency": currency.upper(), "plans": plans}
