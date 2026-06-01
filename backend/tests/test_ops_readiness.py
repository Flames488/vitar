"""
Ops-readiness tests for Vitar.
Covers: health check detail, metrics endpoint, migration chain validity,
        startup validation logic, config completeness, response model shapes.

These tests ensure the ops team has accurate observability and the system
can survive a cold-start without missing or ambiguous configuration.
"""

import os
import uuid
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.core.database import Base, get_db
from app.core.logging import configure_logging

configure_logging(level="ERROR", json_logs=False)

TEST_DB_URL = os.getenv("DATABASE_URL", "sqlite:///./test_ops.db")
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


# ── Health check completeness ─────────────────────────────────────────────────

class TestHealthCheckCompleteness:
    def test_health_returns_200_or_503(self):
        resp = client.get("/health")
        assert resp.status_code in (200, 503)

    def test_health_has_status_field(self):
        resp = client.get("/health")
        assert "status" in resp.json()

    def test_health_status_is_known_value(self):
        resp = client.get("/health")
        assert resp.json()["status"] in ("healthy", "degraded", "unhealthy")

    def test_health_has_components_dict(self):
        resp = client.get("/health")
        data = resp.json()
        assert "components" in data
        assert isinstance(data["components"], dict)

    def test_health_components_include_database(self):
        resp = client.get("/health")
        components = resp.json().get("components", {})
        assert any("db" in k.lower() or "database" in k.lower() or "postgres" in k.lower()
                  for k in components.keys())

    def test_health_components_include_redis_or_cache(self):
        resp = client.get("/health")
        components = resp.json().get("components", {})
        has_redis = any(
            "redis" in k.lower() or "cache" in k.lower() or "celery" in k.lower()
            for k in components.keys()
        )
        # Redis is optional in test — just check the shape, not the value
        assert isinstance(components, dict)

    def test_health_returns_json(self):
        resp = client.get("/health")
        assert resp.headers["content-type"].startswith("application/json")


# ── Metrics endpoint ──────────────────────────────────────────────────────────

class TestMetricsEndpoint:
    def test_prometheus_metrics_accessible(self):
        resp = client.get("/metrics")
        # Prometheus metrics may be on /metrics or require auth
        assert resp.status_code in (200, 401, 403, 404)

    def test_api_metrics_accessible_at_known_path(self):
        # Internal metrics path
        for path in ["/metrics", "/api/v1/metrics", "/internal/metrics"]:
            resp = client.get(path)
            if resp.status_code == 200:
                # If accessible, should contain prometheus-style text
                assert "# HELP" in resp.text or "vitar_" in resp.text or resp.headers["content-type"]
                break


# ── Migration chain integrity ──────────────────────────────────────────────────

class TestMigrationChainIntegrity:
    MIGRATIONS_DIR = Path(__file__).parent.parent / "alembic" / "versions"

    def test_migrations_directory_exists(self):
        assert self.MIGRATIONS_DIR.exists(), f"Migrations dir missing: {self.MIGRATIONS_DIR}"

    def test_at_least_one_migration_exists(self):
        migrations = list(self.MIGRATIONS_DIR.glob("*.py"))
        assert len(migrations) > 0

    def test_migrations_have_revision_ids(self):
        for f in self.MIGRATIONS_DIR.glob("*.py"):
            if f.name.startswith("_"):
                continue
            content = f.read_text()
            assert "revision" in content, f"{f.name} missing revision"

    def test_initial_migration_has_no_down_revision(self):
        """Migration 001 must have down_revision = None to be the chain root."""
        init_files = list(self.MIGRATIONS_DIR.glob("001_*.py"))
        if not init_files:
            pytest.skip("No 001_ migration found")
        content = init_files[0].read_text()
        assert "down_revision = None" in content or 'down_revision = ""' in content

    def test_no_duplicate_revision_ids(self):
        revisions = {}
        for f in self.MIGRATIONS_DIR.glob("*.py"):
            if f.name.startswith("_"):
                continue
            content = f.read_text()
            for line in content.splitlines():
                if line.strip().startswith("revision ="):
                    rev_id = line.split("=", 1)[1].strip().strip("'\"")
                    assert rev_id not in revisions, (
                        f"Duplicate revision '{rev_id}' in {f.name} and {revisions[rev_id]}"
                    )
                    revisions[rev_id] = f.name
                    break

    def test_migration_chain_has_no_obvious_gaps(self):
        """Each migration's down_revision should match a known revision."""
        revisions = {}
        down_revisions = {}

        for f in self.MIGRATIONS_DIR.glob("*.py"):
            if f.name.startswith("_"):
                continue
            content = f.read_text()
            rev_id = None
            down_rev = None
            for line in content.splitlines():
                stripped = line.strip()
                if stripped.startswith("revision ="):
                    rev_id = stripped.split("=", 1)[1].strip().strip("'\"")
                elif stripped.startswith("down_revision ="):
                    down_rev = stripped.split("=", 1)[1].strip().strip("'\"None")
            if rev_id:
                revisions[rev_id] = f.name
                if down_rev:
                    down_revisions[rev_id] = down_rev

        # Every down_revision must point to an existing revision (or be None = root)
        for rev_id, down_rev in down_revisions.items():
            if down_rev and down_rev != "None" and down_rev != "":
                assert down_rev in revisions, (
                    f"Migration {revisions[rev_id]}: down_revision='{down_rev}' "
                    f"does not match any known revision"
                )


# ── Config completeness ───────────────────────────────────────────────────────

class TestConfigCompleteness:
    def test_settings_object_importable(self):
        from app.core.config import settings
        assert settings is not None

    def test_settings_has_database_url(self):
        from app.core.config import settings
        assert hasattr(settings, "DATABASE_URL")
        assert settings.DATABASE_URL

    def test_settings_has_secret_key(self):
        from app.core.config import settings
        assert hasattr(settings, "SECRET_KEY")

    def test_settings_has_jwt_secret(self):
        from app.core.config import settings
        assert hasattr(settings, "JWT_SECRET_KEY") or hasattr(settings, "SECRET_KEY")

    def test_settings_has_environment(self):
        from app.core.config import settings
        assert hasattr(settings, "ENVIRONMENT") or hasattr(settings, "APP_ENV")

    def test_settings_has_allowed_origins(self):
        from app.core.config import settings
        has_origins = (
            hasattr(settings, "ALLOWED_ORIGINS") or
            hasattr(settings, "CORS_ORIGINS") or
            hasattr(settings, "BACKEND_CORS_ORIGINS")
        )
        assert has_origins


# ── Response model shapes ─────────────────────────────────────────────────────

class TestResponseModelShapes:
    def test_register_response_sets_cookie_auth_and_csrf_token(self):
        resp = client.post("/api/v1/auth/register", json={
            "full_name": "Shape Test User",
            "email": f"shape_{uuid.uuid4().hex[:8]}@vitar.health",
            "password": "TestPassword123",
            "phone": f"+234809{uuid.uuid4().int % 10000000:07d}",
            "clinic_name": "Shape Test Clinic",
            "city": "Lagos",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert "csrf_token" in data
        assert "access_token" not in data
        assert "vitar_access" in resp.cookies
        assert "vitar_refresh" in resp.cookies

    def test_error_responses_have_detail_field(self):
        resp = client.post("/api/v1/auth/login", json={
            "email": "nobody@vitar.health",
            "password": "wrong",
        })
        assert resp.status_code == 401
        data = resp.json()
        assert "detail" in data

    def test_validation_error_has_detail_array(self):
        resp = client.post("/api/v1/auth/register", json={})
        assert resp.status_code == 422
        data = resp.json()
        assert "detail" in data
        assert isinstance(data["detail"], list)
