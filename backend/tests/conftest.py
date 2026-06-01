"""
Global pytest configuration and shared fixtures for Vitar backend tests.

Fixtures defined here are available in ALL test files without importing.
Scoping strategy:
  - session scope: expensive setup done once (engine creation)
  - module scope:  per-file setup (registered clinic, doctor, patient)
  - function scope: per-test isolation (transaction rollback)
"""

import os
import uuid
import pytest
from typing import Generator
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from app.main import app
from app.core.database import Base, get_db
from app.core.logging import configure_logging

# ── Silence noisy logs during tests ──────────────────────────────────────────
configure_logging(level="ERROR", json_logs=False)

# ── Test database ─────────────────────────────────────────────────────────────
TEST_DB_URL = os.getenv("DATABASE_URL", "sqlite:///./test_vitar_shared.db")

engine = create_engine(
    TEST_DB_URL,
    connect_args={"check_same_thread": False} if "sqlite" in TEST_DB_URL else {},
    # Echo SQL only in verbose test mode
    echo=os.getenv("VITAR_TEST_SQL_ECHO", "false").lower() == "true",
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db() -> Generator[Session, None, None]:
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db

# ── Global test client ────────────────────────────────────────────────────────
@pytest.fixture(scope="session")
def client() -> TestClient:
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as c:
        yield c
    Base.metadata.drop_all(bind=engine)


# ── Helper: unique values ──────────────────────────────────────────────────────
def unique_email(prefix: str = "test") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}@vitar.health"


def unique_phone() -> str:
    return f"+234809{uuid.uuid4().int % 10000000:07d}"


# ── Shared registered clinic fixture ─────────────────────────────────────────
@pytest.fixture(scope="module")
def registered_clinic(client: TestClient) -> dict:
    """Register a clinic once per test module and return auth context."""
    payload = {
        "full_name": f"Dr. Test {uuid.uuid4().hex[:6]}",
        "email": unique_email("clinic"),
        "password": "TestPassword123",
        "phone": unique_phone(),
        "clinic_name": f"Test Clinic {uuid.uuid4().hex[:4]}",
        "city": "Lagos",
    }
    resp = client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 201, f"Clinic registration failed: {resp.text}"
    csrf_token = resp.json()["csrf_token"]
    token = client.cookies.get("vitar_access")
    return {
        "token": token,
        "csrf_token": csrf_token,
        "headers": {
            **({"Authorization": f"Bearer {token}"} if token else {}),
            "X-CSRF-Token": csrf_token,
        },
        "email": payload["email"],
        "clinic_name": payload["clinic_name"],
    }


# ── Shared doctor fixture ─────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def test_doctor(client: TestClient, registered_clinic: dict) -> dict:
    """Create one doctor per test module."""
    resp = client.post(
        "/api/v1/doctors/",
        headers=registered_clinic["headers"],
        json={"full_name": f"Dr. Fixture {uuid.uuid4().hex[:4]}", "specialty": "General Medicine"},
    )
    assert resp.status_code == 201, f"Doctor creation failed: {resp.text}"
    return resp.json()


# ── Shared patient fixture ────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def test_patient(client: TestClient, registered_clinic: dict) -> dict:
    """Create one patient per test module."""
    resp = client.post(
        "/api/v1/patients/",
        headers=registered_clinic["headers"],
        json={
            "full_name": f"Patient Fixture {uuid.uuid4().hex[:4]}",
            "phone": unique_phone(),
            "email": unique_email("patient"),
        },
    )
    assert resp.status_code == 201, f"Patient creation failed: {resp.text}"
    return resp.json()


# ── Pytest markers ────────────────────────────────────────────────────────────
def pytest_configure(config):
    """Register custom markers to suppress PytestUnknownMarkWarning."""
    config.addinivalue_line("markers", "slow: slow tests (deselect with -m 'not slow')")
    config.addinivalue_line("markers", "integration: tests requiring live DB/Redis")
    config.addinivalue_line("markers", "unit: pure unit tests with no I/O")
    config.addinivalue_line("markers", "billing: billing-related tests")
    config.addinivalue_line("markers", "security: security hardening tests")
    config.addinivalue_line("markers", "ops: ops readiness tests")
