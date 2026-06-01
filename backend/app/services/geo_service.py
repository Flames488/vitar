"""
Vitar v5.2 - Geo & Currency Service
IP-based region detection + browser locale fallback.
Region-aware pricing (NOT simple FX conversion).
IP lookups are cached in Redis for 1 hour to avoid hammering ip-api.com.
"""

import httpx
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


# ─── Regional Pricing Tiers ───────────────────────────────────────────────────
# These are market-fit prices, NOT exchange-rate conversions.

PRICING_TIERS: Dict[str, Dict] = {
    "NGN": {
        "basic": {
            "monthly": 15000,     # ₦15,000/month
            "annual": 150000,     # ₦150,000/year (save 17%)
            "annual_savings_percent": 17,
        },
        "pro": {
            "monthly": 35000,     # ₦35,000/month
            "annual": 336000,     # ₦336,000/year
            "annual_savings_percent": 20,
        },
        "enterprise": {
            "monthly": None,      # Custom
            "annual": None,
            "annual_savings_percent": None,
        },
    },
    "USD": {
        "basic": {
            "monthly": 29,
            "annual": 290,
            "annual_savings_percent": 17,
        },
        "pro": {
            "monthly": 79,
            "annual": 758,
            "annual_savings_percent": 20,
        },
        "enterprise": {
            "monthly": None,
            "annual": None,
            "annual_savings_percent": None,
        },
    },
    "GBP": {
        "basic": {
            "monthly": 24,
            "annual": 230,
            "annual_savings_percent": 17,
        },
        "pro": {
            "monthly": 65,
            "annual": 624,
            "annual_savings_percent": 20,
        },
        "enterprise": {
            "monthly": None,
            "annual": None,
            "annual_savings_percent": None,
        },
    },
    "EUR": {
        "basic": {
            "monthly": 27,
            "annual": 259,
            "annual_savings_percent": 17,
        },
        "pro": {
            "monthly": 72,
            "annual": 691,
            "annual_savings_percent": 20,
        },
        "enterprise": {
            "monthly": None,
            "annual": None,
            "annual_savings_percent": None,
        },
    },
}

# Country → currency mapping
COUNTRY_CURRENCY: Dict[str, str] = {
    "NG": "NGN",
    "GH": "GHS",
    "KE": "KES",
    "ZA": "ZAR",
    "US": "USD",
    "CA": "CAD",
    "GB": "GBP",
    "DE": "EUR", "FR": "EUR", "ES": "EUR", "IT": "EUR", "NL": "EUR",
    "AU": "AUD",
    "IN": "INR",
}

# Currency display config
CURRENCY_FORMAT: Dict[str, Dict] = {
    "NGN": {"symbol": "₦", "code": "NGN", "locale": "en-NG", "decimals": 0},
    "USD": {"symbol": "$", "code": "USD", "locale": "en-US", "decimals": 2},
    "GBP": {"symbol": "£", "code": "GBP", "locale": "en-GB", "decimals": 2},
    "EUR": {"symbol": "€", "code": "EUR", "locale": "de-DE", "decimals": 2},
    "GHS": {"symbol": "₵", "code": "GHS", "locale": "en-GH", "decimals": 2},
    "KES": {"symbol": "KSh", "code": "KES", "locale": "en-KE", "decimals": 0},
    "ZAR": {"symbol": "R", "code": "ZAR", "locale": "en-ZA", "decimals": 2},
    "AUD": {"symbol": "A$", "code": "AUD", "locale": "en-AU", "decimals": 2},
    "INR": {"symbol": "₹", "code": "INR", "locale": "en-IN", "decimals": 0},
    "CAD": {"symbol": "CA$", "code": "CAD", "locale": "en-CA", "decimals": 2},
}

# Payment provider by country
PAYMENT_PROVIDERS: Dict[str, str] = {
    "NG": "paystack",
    "GH": "paystack",
    "KE": "flutterwave",
    "ZA": "stripe",
}


def get_currency_for_country(country_code: str) -> str:
    return COUNTRY_CURRENCY.get(country_code.upper(), "USD")


def get_pricing_tier(currency: str) -> str:
    """Map currency to closest supported pricing tier."""
    if currency in PRICING_TIERS:
        return currency
    # Fallback to USD for unsupported currencies
    return "USD"


def get_payment_provider(country_code: str) -> str:
    return PAYMENT_PROVIDERS.get(country_code.upper(), "stripe")


def format_currency(amount: float, currency: str) -> str:
    """Format amount with correct symbol and decimals."""
    fmt = CURRENCY_FORMAT.get(currency, CURRENCY_FORMAT["USD"])
    decimals = fmt["decimals"]
    symbol = fmt["symbol"]
    if decimals == 0:
        return f"{symbol}{int(amount):,}"
    return f"{symbol}{amount:,.{decimals}f}"


# ─── IP-based Geo Detection ───────────────────────────────────────────────────

async def detect_geo_from_ip(ip: str) -> Dict[str, Any]:
    """
    Detect country, currency, and timezone from IP address.
    Results cached in Redis for 1 hour — ip-api.com free tier is 45 req/min;
    caching ensures we never hit that ceiling in production.
    """
    if ip in ("127.0.0.1", "::1", "localhost"):
        return _default_geo()

    # Check cache first
    try:
        from app.core.cache import cache, geo_country_key, TTL_LONG
        from app.core.metrics import record_cache_hit, record_cache_miss
        ck = geo_country_key(ip)
        cached = cache.get(ck)
        if cached:
            record_cache_hit()
            return cached
        record_cache_miss()
    except Exception:
        pass  # Cache unavailable — proceed to live lookup

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(
                f"http://ip-api.com/json/{ip}?fields=status,country,countryCode,city,timezone,regionName",
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") == "success":
                    country = data.get("countryCode", "US")
                    currency = get_currency_for_country(country)
                    result = {
                        "country": country,
                        "country_name": data.get("country", ""),
                        "city": data.get("city", ""),
                        "region": data.get("regionName", ""),
                        "timezone": data.get("timezone", "UTC"),
                        "currency": currency,
                        "currency_format": CURRENCY_FORMAT.get(currency, CURRENCY_FORMAT["USD"]),
                        "payment_provider": get_payment_provider(country),
                        "pricing_tier": get_pricing_tier(currency),
                        "source": "ip-api",
                    }
                    try:
                        cache.set(ck, result, ttl=TTL_LONG)
                    except Exception:
                        pass
                    return result
    except Exception as e:
        logger.warning(f"IP geo detection failed: {e}")

    return _default_geo()


def detect_geo_from_locale(accept_language: Optional[str] = None) -> Dict[str, Any]:
    """Browser locale fallback. Parses Accept-Language header."""
    if not accept_language:
        return _default_geo()

    # e.g. "en-NG,en;q=0.9" → "NG"
    primary = accept_language.split(",")[0].strip()
    parts = primary.split("-")
    if len(parts) >= 2:
        country = parts[-1].upper()[:2]
        currency = get_currency_for_country(country)
        return {
            "country": country,
            "currency": currency,
            "currency_format": CURRENCY_FORMAT.get(currency, CURRENCY_FORMAT["USD"]),
            "payment_provider": get_payment_provider(country),
            "pricing_tier": get_pricing_tier(currency),
            "source": "locale",
        }

    return _default_geo()


def _default_geo() -> Dict[str, Any]:
    return {
        "country": "US",
        "currency": "USD",
        "currency_format": CURRENCY_FORMAT["USD"],
        "payment_provider": "stripe",
        "pricing_tier": "USD",
        "source": "default",
    }


def get_all_plans_for_currency(currency: str) -> list:
    """Return full plan list with pricing for a given currency."""
    from app.services.billing_service import PLANS, get_plan_pricing
    tier = get_pricing_tier(currency)
    result = []
    for plan_key in ("basic", "pro", "enterprise"):
        plan_data = get_plan_pricing(plan_key, tier)
        plan_data["currency_format"] = CURRENCY_FORMAT.get(tier, CURRENCY_FORMAT["USD"])
        result.append(plan_data)
    return result
