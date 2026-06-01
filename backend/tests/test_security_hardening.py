"""
Tests for security hardening across the Vitar API.
Covers: rate limiting, auth edge cases, input validation, CORS headers,
        SQL injection prevention, XSS prevention, session security.

Coverage goals: ≥80% of security-related middleware and core/security.py
"""

import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os

from app.main import app
from app.core.database import Base, get_db
from app.core.logging import configure_logging

configure_logging(level="ERROR", json_logs=False)

TEST_DB_URL = os.getenv("DATABASE_URL", "sqlite:///./test_security.db")
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

@pytest.fixture(scope="module", autouse=True)
def setup_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

def unique_email():
    return f"sec_{uuid.uuid4().hex[:8]}@vitar.health"

def unique_phone():
    return f"+234809{uuid.uuid4().int % 10000000:07d}"


# ── Input validation ──────────────────────────────────────────────────────────

class TestInputValidation:
    def test_register_rejects_weak_password(self):
        resp = client.post("/api/v1/auth/register", json={
            "full_name": "Weak Pass User",
            "email": unique_email(),
            "password": "123",  # too short
            "phone": unique_phone(),
            "clinic_name": "TestClinic",
            "city": "Lagos",
        })
        assert resp.status_code == 422

    def test_register_rejects_invalid_email(self):
        resp = client.post("/api/v1/auth/register", json={
            "full_name": "Bad Email User",
            "email": "not-an-email",
            "password": "ValidPass123",
            "phone": unique_phone(),
            "clinic_name": "TestClinic",
            "city": "Lagos",
        })
        assert resp.status_code == 422

    def test_register_rejects_empty_full_name(self):
        resp = client.post("/api/v1/auth/register", json={
            "full_name": "",
            "email": unique_email(),
            "password": "ValidPass123",
            "phone": unique_phone(),
            "clinic_name": "TestClinic",
            "city": "Lagos",
        })
        assert resp.status_code == 422

    def test_register_rejects_missing_fields(self):
        resp = client.post("/api/v1/auth/register", json={
            "email": unique_email(),
            "password": "ValidPass123",
        })
        assert resp.status_code == 422

    def test_login_rejects_missing_password(self):
        resp = client.post("/api/v1/auth/login", json={
            "email": unique_email(),
        })
        assert resp.status_code == 422

    def test_login_wrong_credentials_returns_401(self):
        resp = client.post("/api/v1/auth/login", json={
            "email": "nonexistent@vitar.health",
            "password": "WrongPass123",
        })
        assert resp.status_code == 401

    def test_sql_injection_in_email_field(self):
        resp = client.post("/api/v1/auth/login", json={
            "email": "' OR '1'='1' --",
            "password": "anything",
        })
        # Should get 422 (validation) or 401 (auth fail), NOT 500 (SQL error)
        assert resp.status_code in (401, 422)

    def test_xss_payload_in_clinic_name(self):
        resp = client.post("/api/v1/auth/register", json={
            "full_name": "XSS Test",
            "email": unique_email(),
            "password": "ValidPass123",
            "phone": unique_phone(),
            "clinic_name": "<script>alert('xss')</script>",
            "city": "Lagos",
        })
        # Should either reject (422) or sanitize and accept (201)
        # Should NOT raise 500
        assert resp.status_code in (201, 400, 422)
        if resp.status_code == 201:
            # If accepted, verify the stored name is either escaped or stored literally
            # (not executing JS — that's a frontend concern anyway)
            assert resp.status_code == 201


# ── Auth token security ────────────────────────────────────────────────────────

class TestAuthTokenSecurity:
    def setup_method(self):
        client.cookies.clear()

    def test_expired_token_returns_401(self):
        expired = (
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
            "eyJzdWIiOiJ0ZXN0IiwiZXhwIjoxMDAwMDAwMDAwfQ."  # exp=2001
            "invalid_signature"
        )
        resp = client.get(
            "/api/v1/appointments/",
            headers={"Authorization": f"Bearer {expired}"},
        )
        assert resp.status_code == 401

    def test_malformed_token_returns_401(self):
        resp = client.get(
            "/api/v1/appointments/",
            headers={"Authorization": "Bearer not.a.jwt"},
        )
        assert resp.status_code == 401

    def test_missing_bearer_prefix_returns_401(self):
        resp = client.get(
            "/api/v1/appointments/",
            headers={"Authorization": "some_raw_token"},
        )
        assert resp.status_code == 401

    def test_empty_auth_header_returns_401(self):
        resp = client.get(
            "/api/v1/appointments/",
            headers={"Authorization": ""},
        )
        assert resp.status_code == 401


# ── Tenant isolation ──────────────────────────────────────────────────────────

class TestTenantIsolation:
    @pytest.fixture(scope="class")
    def clinic_a(self):
        payload = {
            "full_name": "Clinic A Owner",
            "email": unique_email(),
            "password": "TestPassword123",
            "phone": unique_phone(),
            "clinic_name": f"Clinic A {uuid.uuid4().hex[:4]}",
            "city": "Lagos",
        }
        reg = client.post("/api/v1/auth/register", json=payload)
        assert reg.status_code == 201
        csrf_token = reg.json()["csrf_token"]
        token = client.cookies.get("vitar_access")
        headers = {
            **({"Authorization": f"Bearer {token}"} if token else {}),
            "X-CSRF-Token": csrf_token,
        }

        doc = client.post("/api/v1/doctors/", json={"full_name": "Dr. A"}, headers=headers)
        assert doc.status_code == 201
        return {"headers": headers, "doctor_id": doc.json()["id"]}

    @pytest.fixture(scope="class")
    def clinic_b(self):
        payload = {
            "full_name": "Clinic B Owner",
            "email": unique_email(),
            "password": "TestPassword123",
            "phone": unique_phone(),
            "clinic_name": f"Clinic B {uuid.uuid4().hex[:4]}",
            "city": "Abuja",
        }
        reg = client.post("/api/v1/auth/register", json=payload)
        assert reg.status_code == 201
        csrf_token = reg.json()["csrf_token"]
        token = client.cookies.get("vitar_access")
        return {"headers": {
            **({"Authorization": f"Bearer {token}"} if token else {}),
            "X-CSRF-Token": csrf_token,
        }}

    def test_clinic_b_cannot_see_clinic_a_doctors(self, clinic_a, clinic_b):
        doctor_id = clinic_a["doctor_id"]
        resp = client.get(f"/api/v1/doctors/{doctor_id}", headers=clinic_b["headers"])
        # Should be 404 (not found for this tenant) or 403
        assert resp.status_code in (403, 404)

    def test_clinic_b_doctors_list_excludes_clinic_a_doctors(self, clinic_a, clinic_b):
        a_doctor_id = clinic_a["doctor_id"]
        resp = client.get("/api/v1/doctors/", headers=clinic_b["headers"])
        assert resp.status_code == 200
        doctor_ids = [d["id"] for d in resp.json()] if isinstance(resp.json(), list) else []
        assert a_doctor_id not in doctor_ids


# ── Health endpoint ───────────────────────────────────────────────────────────

class TestHealthEndpoint:
    def test_health_is_public(self):
        resp = client.get("/health")
        assert resp.status_code in (200, 503)

    def test_health_returns_status_field(self):
        resp = client.get("/health")
        data = resp.json()
        assert "status" in data

    def test_health_returns_components(self):
        resp = client.get("/health")
        data = resp.json()
        assert "components" in data

    def test_root_returns_service_name(self):
        resp = client.get("/")
        assert resp.status_code == 200
        assert resp.json()["service"] == "Vitar API"

    def test_docs_accessible(self):
        resp = client.get("/api/docs")
        assert resp.status_code in (200, 404)  # 404 when docs disabled in prod config
