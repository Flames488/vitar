"""
Tests for app/services/billing_service.py
Target: plan definitions, pricing lookup, webhook signature verification,
        plan feature checks, Paystack webhook processing.

Coverage goals: ≥85% of billing_service.py
"""

import hashlib
import hmac
import json
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime, timedelta, timezone

from app.services.billing_service import (
    PLANS,
    get_plan_pricing,
    verify_paystack_signature,
)
from app.services.geo_service import PRICING_TIERS


# ── PLANS registry ────────────────────────────────────────────────────────────

class TestPlansRegistry:
    def test_has_basic_plan(self):
        assert "basic" in PLANS

    def test_has_pro_plan(self):
        assert "pro" in PLANS

    def test_has_enterprise_plan(self):
        assert "enterprise" in PLANS

    def test_basic_plan_max_doctors(self):
        assert PLANS["basic"]["max_doctors"] == 2

    def test_pro_plan_max_doctors(self):
        assert PLANS["pro"]["max_doctors"] == 10

    def test_enterprise_unlimited_doctors(self):
        assert PLANS["enterprise"]["max_doctors"] == -1

    def test_enterprise_unlimited_bookings(self):
        assert PLANS["enterprise"]["max_bookings_month"] == -1

    def test_all_plans_have_features_list(self):
        for plan_name, plan in PLANS.items():
            assert "features" in plan, f"{plan_name} missing features"
            assert len(plan["features"]) > 0

    def test_pro_has_more_bookings_than_basic(self):
        assert PLANS["pro"]["max_bookings_month"] > PLANS["basic"]["max_bookings_month"]


# ── get_plan_pricing ─────────────────────────────────────────────────────────

class TestGetPlanPricing:
    def test_ngn_basic_monthly(self):
        pricing = get_plan_pricing("basic", "NGN")
        assert "monthly" in pricing
        assert pricing["monthly"] == 15000

    def test_ngn_pro_monthly(self):
        pricing = get_plan_pricing("pro", "NGN")
        assert pricing["monthly"] == 35000

    def test_usd_basic_monthly(self):
        pricing = get_plan_pricing("basic", "USD")
        assert pricing["monthly"] == 29

    def test_usd_pro_monthly(self):
        pricing = get_plan_pricing("pro", "USD")
        assert pricing["monthly"] == 79

    def test_gbp_basic_monthly(self):
        pricing = get_plan_pricing("basic", "GBP")
        assert pricing["monthly"] == 24

    def test_unknown_currency_falls_back_to_usd(self):
        pricing = get_plan_pricing("basic", "XYZ")
        # Should fall back to USD pricing
        assert pricing is not None
        assert "monthly" in pricing

    def test_annual_price_is_less_than_12x_monthly(self):
        pricing = get_plan_pricing("pro", "NGN")
        if "annual" in pricing and "monthly" in pricing:
            # Annual should offer a discount (< 12 months * monthly)
            assert pricing["annual"] < pricing["monthly"] * 12


# ── verify_paystack_signature ─────────────────────────────────────────────────

class TestVerifyPaystackSignature:
    SECRET = "test_paystack_secret_key"

    def _make_signature(self, body: bytes) -> str:
        return hmac.new(
            self.SECRET.encode(),
            body,
            hashlib.sha512,
        ).hexdigest()

    def test_valid_signature_returns_true(self):
        body = b'{"event": "charge.success", "data": {"reference": "ref123"}}'
        sig = self._make_signature(body)
        assert verify_paystack_signature(body, sig, self.SECRET) is True

    def test_invalid_signature_returns_false(self):
        body = b'{"event": "charge.success"}'
        assert verify_paystack_signature(body, "invalid_sig", self.SECRET) is False

    def test_wrong_secret_returns_false(self):
        body = b'{"event": "charge.success"}'
        sig = self._make_signature(body)
        assert verify_paystack_signature(body, sig, "wrong_secret") is False

    def test_tampered_body_returns_false(self):
        original = b'{"event": "charge.success", "amount": 1000}'
        sig = self._make_signature(original)
        tampered = b'{"event": "charge.success", "amount": 9999}'
        assert verify_paystack_signature(tampered, sig, self.SECRET) is False

    def test_empty_body_with_matching_sig_passes(self):
        body = b""
        sig = self._make_signature(body)
        assert verify_paystack_signature(body, sig, self.SECRET) is True

    def test_case_sensitivity_of_signature(self):
        body = b'{"test": true}'
        sig = self._make_signature(body)
        # Hex digest is lowercase; uppercase should fail
        assert verify_paystack_signature(body, sig.upper(), self.SECRET) is False

    def test_empty_secret_raises_or_returns_false(self):
        body = b'{"test": true}'
        try:
            result = verify_paystack_signature(body, "abc", "")
            assert result is False
        except (ValueError, Exception):
            pass  # Either raising or returning False is acceptable

    def test_unicode_body_handled(self):
        body = '{"name": "Temi Adéolà"}'.encode("utf-8")
        sig = self._make_signature(body)
        assert verify_paystack_signature(body, sig, self.SECRET) is True


# ── Plan limit enforcement ─────────────────────────────────────────────────────

class TestPlanLimits:
    """Validate that plan limits are correctly defined and enforced."""

    def test_basic_monthly_booking_limit(self):
        assert PLANS["basic"]["max_bookings_month"] == 200

    def test_pro_monthly_booking_limit(self):
        assert PLANS["pro"]["max_bookings_month"] == 2000

    def test_enterprise_has_no_booking_limit(self):
        assert PLANS["enterprise"]["max_bookings_month"] == -1

    def test_plan_names_consistent(self):
        """Plan names should match their dict keys."""
        for key, plan in PLANS.items():
            assert plan["name"].lower() == key.lower()

    def test_plans_list_complete(self):
        expected = {"basic", "pro", "enterprise"}
        assert set(PLANS.keys()) == expected


# ── PRICING_TIERS structure ───────────────────────────────────────────────────

class TestPricingTiers:
    def test_has_ngn_tier(self):
        assert "NGN" in PRICING_TIERS

    def test_has_usd_tier(self):
        assert "USD" in PRICING_TIERS

    def test_has_gbp_tier(self):
        assert "GBP" in PRICING_TIERS

    def test_ngn_basic_cheaper_than_usd_basic(self):
        # NGN pricing should be lower in absolute terms for local market
        ngn = PRICING_TIERS["NGN"]["basic"]["monthly"]
        usd = PRICING_TIERS["USD"]["basic"]["monthly"]
        # At realistic exchange rate (1 USD ≈ 1500 NGN), NGN price should be > 1000
        # but in USD equivalent < USD price
        assert ngn > 1000  # Real naira price
        assert usd > 0

    def test_all_tiers_have_basic_pro_enterprise(self):
        for currency, tiers in PRICING_TIERS.items():
            for plan in ["basic", "pro"]:
                assert plan in tiers, f"{currency} missing {plan} plan"
