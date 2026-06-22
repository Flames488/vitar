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

    # Locale fallback intentionally removed — this product defaults to NG/NGN.
    # The en-US Accept-Language header (Windows default) was overriding NGN
    # with USD for all local/Nigerian users whose IP geo lookup returned the
    # _default_geo(). NGN is the correct default for this market.

    # Add plans for the detected currency
    geo["plans"] = get_all_plans_for_currency(geo["currency"])

    return geo


@router.get("/plans/{currency}")
def get_plans_by_currency(currency: str):
    """Explicit currency override — e.g., ?currency=NGN."""
    plans = get_all_plans_for_currency(currency.upper())
    return {"currency": currency.upper(), "plans": plans}
