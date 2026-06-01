"""
Vitar v5 - Full Test Suite
Covers: auth, geo, AI service, idempotency, trial guard, notifications, currency, double-booking
"""

import pytest
import uuid
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os

TEST_DB_URL = os.getenv("DATABASE_URL", "sqlite:///./test_vitar.db")

from app.main import app
from app.core.database import Base, get_db
from app.core.logging import configure_logging

configure_logging(level="ERROR", json_logs=False)

engine = create_engine(
    TEST_DB_URL,
    connect_args={"check_same_thread": False} if "sqlite" in TEST_DB_URL else {},
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


@pytest.fixture(scope="session", autouse=True)
def setup_database():
    """Create fresh tables once per session."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


def unique_email(prefix="test"):
    """Generate a unique email for each test to avoid 409 collisions."""
    return f"{prefix}_{uuid.uuid4().hex[:8]}@vitar.health"


# ── Health ────────────────────────────────────────────────────────────────────

def test_health():
    response = client.get("/health")
    assert response.status_code in (200, 503)  # 503 if Redis/Celery down in CI
    data = response.json()
    assert "status" in data
    assert "components" in data


def test_root():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["service"] == "Vitar API"


# ── Auth ──────────────────────────────────────────────────────────────────────

def make_register_payload(email=None, clinic_name=None):
    return {
        "full_name": "Dr. Test User",
        "email": email or unique_email("register"),
        "password": "TestPassword123",
        "phone": f"+234809{uuid.uuid4().int % 10000000:07d}",
        "clinic_name": clinic_name or f"Test Clinic {uuid.uuid4().hex[:6]}",
        "city": "Lagos",
        "country": "NG",
    }


def test_register():
    payload = make_register_payload()
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201, response.text
    data = response.json()
    assert "csrf_token" in data
    assert "vitar_access" in response.cookies
    assert "vitar_refresh" in response.cookies
    assert data["user"]["email"] == payload["email"]
    assert data["clinic"]["name"] == payload["clinic_name"]
    assert data["clinic"]["currency"] == "NGN"  # NG country → NGN


def test_register_duplicate_email():
    email = unique_email("dup")
    client.post("/api/v1/auth/register", json=make_register_payload(email=email, clinic_name="Dup1"))
    response = client.post("/api/v1/auth/register", json=make_register_payload(email=email, clinic_name="Dup2"))
    assert response.status_code == 409


def test_login_success():
    payload = make_register_payload()
    client.post("/api/v1/auth/register", json=payload)
    response = client.post("/api/v1/auth/login", json={"email": payload["email"], "password": payload["password"]})
    assert response.status_code == 200
    assert "csrf_token" in response.json()
    assert "vitar_access" in response.cookies


def test_login_wrong_password():
    payload = make_register_payload()
    client.post("/api/v1/auth/register", json=payload)
    response = client.post("/api/v1/auth/login", json={"email": payload["email"], "password": "WrongPass999"})
    assert response.status_code == 401


def test_password_validation_no_uppercase():
    payload = make_register_payload()
    payload["password"] = "alllowercase1"
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 422


def test_password_validation_no_digit():
    payload = make_register_payload()
    payload["password"] = "NoDigitsHere"
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 422


def test_password_validation_too_short():
    payload = make_register_payload()
    payload["password"] = "Ab1"
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 422


def test_forgot_password_no_enumeration():
    """Always 200 even for unknown email — prevents email enumeration."""
    response = client.post("/api/v1/auth/forgot-password", json={"email": "nobody@vitar.health"})
    assert response.status_code == 200
    assert "message" in response.json()


# ── Geo / Currency ────────────────────────────────────────────────────────────

def test_geo_detect_returns_currency():
    response = client.get("/api/v1/geo/detect")
    assert response.status_code == 200
    data = response.json()
    assert "currency" in data
    assert "plans" in data
    assert len(data["plans"]) == 3


def test_geo_plans_ng():
    response = client.get("/api/v1/geo/plans/NGN")
    assert response.status_code == 200
    data = response.json()
    assert data["currency"] == "NGN"
    plans = {p["plan"]: p for p in data["plans"]}
    assert plans["basic"]["monthly"] == 15000
    assert plans["pro"]["monthly"] == 35000


def test_geo_plans_usd():
    response = client.get("/api/v1/geo/plans/USD")
    assert response.status_code == 200
    data = response.json()
    plans = {p["plan"]: p for p in data["plans"]}
    assert plans["basic"]["monthly"] == 29
    assert plans["pro"]["monthly"] == 79


def test_geo_plans_fallback_unknown_currency():
    response = client.get("/api/v1/geo/plans/XYZ")
    assert response.status_code == 200
    assert len(response.json()["plans"]) == 3


# ── AI Service Unit Tests ─────────────────────────────────────────────────────

def test_no_show_predictor_score_range():
    from app.services.ai_service import NoShowPredictor, calculate_risk_category
    from datetime import datetime, timedelta, timezone

    class FakeAppointment:
        id = "apt-test"
        scheduled_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=5)
        no_show_risk_score = 0.0
        risk_factors = {}

    class FakePatient:
        id = "pat-test"
        historical_no_show_rate = 0.6
        total_appointments = 5
        total_no_shows = 3
        total_cancellations = 1
        last_no_show_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=15)

    class FakeDB:
        def query(self, *a): return self
        def filter(self, *a): return self
        def count(self): return 2

    predictor = NoShowPredictor()
    features, score = predictor.predict(FakeAppointment(), FakePatient(), FakeDB())
    assert 0.0 <= score <= 1.0, f"Score out of range: {score}"
    assert "final_score" in features


def test_risk_categories():
    from app.services.ai_service import calculate_risk_category
    assert calculate_risk_category(0.10) == "low"
    assert calculate_risk_category(0.30) == "medium"
    assert calculate_risk_category(0.60) == "high"
    assert calculate_risk_category(0.85) == "critical"


def test_reminder_schedule_low_risk():
    from app.services.ai_service import get_reminder_schedule
    from datetime import datetime, timedelta, timezone
    apt_dt = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=30)
    reminders = get_reminder_schedule(0.1, apt_dt)
    assert len(reminders) == 1
    assert reminders[0]["offset_hours"] == 24


def test_reminder_schedule_critical_risk():
    from app.services.ai_service import get_reminder_schedule
    from datetime import datetime, timedelta, timezone
    apt_dt = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=72)
    reminders = get_reminder_schedule(0.9, apt_dt)
    assert len(reminders) > 3


# ── Idempotency ───────────────────────────────────────────────────────────────

def test_idempotency_check_and_mark():
    from app.core.idempotency import check_and_mark, invalidate
    key_id = f"test-idem-{uuid.uuid4().hex}"
    invalidate("test", key_id)
    first = check_and_mark("test", key_id)
    assert first is True
    second = check_and_mark("test", key_id)
    assert isinstance(second, bool)
    invalidate("test", key_id)


def test_db_payment_reference_check():
    from app.core.idempotency import check_payment_reference_db
    db = TestingSessionLocal()
    try:
        result = check_payment_reference_db("nonexistent-ref-xyz", db)
        assert result is False
    finally:
        db.close()


# ── Trial Guard ───────────────────────────────────────────────────────────────

def test_trial_status_active():
    from app.services.trial_guard import get_trial_status
    from datetime import datetime, timedelta, timezone

    class FakeSub:
        status = "trialing"
        plan = "trial"

    class FakeClinic:
        subscription = FakeSub()
        trial_ends_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=10)
        trial_bookings_used = 20

    result = get_trial_status(FakeClinic())
    assert result["is_trial"] is True
    assert result["days_left"] >= 9
    assert result["bookings_used"] == 20
    assert result["is_expired"] is False


def test_trial_status_expired():
    from app.services.trial_guard import get_trial_status
    from datetime import datetime, timedelta, timezone

    class FakeSub:
        status = "trialing"

    class FakeClinic:
        subscription = FakeSub()
        trial_ends_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1)
        trial_bookings_used = 50

    result = get_trial_status(FakeClinic())
    assert result["is_expired"] is True


def test_trial_guard_enum_handling():
    from app.services.trial_guard import check_trial_booking_limit
    from app.models.models import SubscriptionPlan, SubscriptionStatus
    from datetime import datetime, timedelta, timezone

    class FakeSubEnum:
        plan = SubscriptionPlan.BASIC
        status = SubscriptionStatus.ACTIVE

    class FakeClinicActive:
        subscription = FakeSubEnum()
        trial_ends_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=10)
        trial_bookings_used = 0

    db = TestingSessionLocal()
    try:
        check_trial_booking_limit(FakeClinicActive(), db)  # Should not raise
    finally:
        db.close()


# ── Notification Templates ────────────────────────────────────────────────────

def test_notification_message_templates():
    from app.services.notification_service import (
        build_reminder_message, build_confirmation_message,
        build_no_show_followup_message, build_reschedule_message,
    )
    from datetime import datetime, timezone

    dt = datetime(2025, 8, 15, 10, 0)
    reminder = build_reminder_message("John Doe", "Smith", dt, "City Clinic", "tok123", "https://vitar.health")
    assert "John" in reminder and "Smith" in reminder and "tok123" in reminder

    confirmation = build_confirmation_message("Jane", "Obi", dt, "Clinic", "conf-abc", "https://vitar.health")
    assert "Jane" in confirmation and "conf-abc" in confirmation

    followup = build_no_show_followup_message("Tom", "Health Clinic", "+2348000000000")
    assert "Tom" in followup and "Health Clinic" in followup

    reschedule = build_reschedule_message("Alice", "Jones", dt, "MedCare")
    assert "Alice" in reschedule and "Jones" in reschedule


# ── Currency Formatting ───────────────────────────────────────────────────────

def test_currency_format_ngn():
    from app.services.geo_service import format_currency
    assert format_currency(15000, "NGN") == "₦15,000"
    assert format_currency(35000, "NGN") == "₦35,000"


def test_currency_format_usd():
    from app.services.geo_service import format_currency
    assert format_currency(29.0, "USD") == "$29.00"
    assert format_currency(79.0, "USD") == "$79.00"


def test_currency_format_gbp():
    from app.services.geo_service import format_currency
    assert format_currency(24.0, "GBP") == "£24.00"


def test_country_mapping():
    from app.services.geo_service import get_currency_for_country, get_payment_provider
    assert get_currency_for_country("NG") == "NGN"
    assert get_currency_for_country("US") == "USD"
    assert get_currency_for_country("GB") == "GBP"
    assert get_currency_for_country("DE") == "EUR"
    assert get_currency_for_country("XX") == "USD"
    assert get_payment_provider("NG") == "paystack"
    assert get_payment_provider("GH") == "paystack"
    assert get_payment_provider("US") == "stripe"


# ── Double-Booking Prevention ─────────────────────────────────────────────────

def test_double_booking_detection():
    """Two simultaneous bookings for same doctor+slot → second gets 409."""
    from datetime import datetime, timedelta, timezone

    payload = make_register_payload()
    reg = client.post("/api/v1/auth/register", json=payload)
    assert reg.status_code == 201, reg.text
    csrf_token = reg.json()["csrf_token"]
    token = client.cookies.get("vitar_access")
    headers = {
        **({"Authorization": f"Bearer {token}"} if token else {}),
        "X-CSRF-Token": csrf_token,
    }

    doc = client.post("/api/v1/doctors/", json={"full_name": "Dr. Double Test"}, headers=headers)
    assert doc.status_code == 201, doc.text
    doctor_id = doc.json()["id"]

    pat = client.post("/api/v1/patients/", json={
        "full_name": "Pat Test",
        "phone": f"+234809{uuid.uuid4().int % 10000000:07d}"
    }, headers=headers)
    assert pat.status_code == 201, pat.text
    patient_id = pat.json()["id"]

    tomorrow = (datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)

    apt1 = client.post("/api/v1/appointments/", headers=headers, json={
        "doctor_id": doctor_id, "patient_id": patient_id,
        "scheduled_at": tomorrow.isoformat(), "duration_mins": 30,
    })
    assert apt1.status_code == 201, apt1.text

    apt2 = client.post("/api/v1/appointments/", headers=headers, json={
        "doctor_id": doctor_id, "patient_id": patient_id,
        "scheduled_at": tomorrow.isoformat(), "duration_mins": 30,
    })
    assert apt2.status_code == 409, apt2.text
    assert apt2.json()["detail"]["code"] == "SLOT_CONFLICT"


# ── Protected endpoints require auth ─────────────────────────────────────────

def test_appointments_requires_auth():
    client.cookies.clear()
    response = client.get("/api/v1/appointments/")
    assert response.status_code == 401


def test_doctors_requires_auth():
    client.cookies.clear()
    response = client.get("/api/v1/doctors/")
    assert response.status_code == 401


def test_patients_requires_auth():
    client.cookies.clear()
    response = client.get("/api/v1/patients/")
    assert response.status_code == 401


# ── Token refresh ─────────────────────────────────────────────────────────────

def test_token_refresh():
    payload = make_register_payload()
    reg = client.post("/api/v1/auth/register", json=payload)
    assert reg.status_code == 201

    resp = client.post("/api/v1/auth/refresh")
    assert resp.status_code == 200
    assert "csrf_token" in resp.json()
    assert "vitar_access" in resp.cookies
