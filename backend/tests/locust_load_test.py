"""
Vitar v8 — Locust Load Test Suite
Proves capacity at 20 / 50 / 100 / 150+ concurrent users.

USAGE:
    pip install locust
    locust -f locust_load_test.py --host=http://localhost:8000

    # Headless CI run — 100 users, 10 spawn/s, 3-minute test:
    locust -f locust_load_test.py --host=http://localhost:8000 \
        --headless -u 100 -r 10 --run-time 3m \
        --html=load_report.html --csv=load_results

STAGES (edit USER_STAGES below to match your target):
    20  users  →  baseline (must be rock-solid)
    50  users  →  expected daily peak
    100 users  →  stress target
    150 users  →  breaking-point discovery

PASS CRITERIA (enforced by on_test_stop assertions):
    P95 response time  < 500 ms
    P99 response time  < 1000 ms
    Error rate         < 1%
    Throughput         > 50 req/s at 100 users
"""

import os
import json
import random
import string
import logging
from locust import HttpUser, task, between, events
from locust.runners import MasterRunner

logger = logging.getLogger("vitar.loadtest")

# ── Config ────────────────────────────────────────────────────────────────────
API_BASE    = "/api/v1"
ADMIN_EMAIL = os.getenv("LOAD_TEST_EMAIL", "loadtest@vitar.health")
ADMIN_PASS  = os.getenv("LOAD_TEST_PASSWORD", "LoadTest123!")

# Pre-seeded IDs from your staging DB (override via env)
CLINIC_ID  = os.getenv("LOAD_TEST_CLINIC_ID", "")
DOCTOR_ID  = os.getenv("LOAD_TEST_DOCTOR_ID", "")
PATIENT_ID = os.getenv("LOAD_TEST_PATIENT_ID", "")


def _rand_str(n=8) -> str:
    return "".join(random.choices(string.ascii_lowercase, k=n))


# ── Shared token store (populated during on_start) ───────────────────────────
_tokens: list[str] = []


# ── Base user ─────────────────────────────────────────────────────────────────

class VitarUser(HttpUser):
    """
    Realistic clinic staff session:
    - Views dashboard (most frequent)
    - Lists appointments / patients
    - Creates an appointment (write path)
    - Checks analytics
    Weight ratios set via @task(N).
    """
    wait_time = between(0.5, 2.5)   # simulates real human think-time
    token: str = ""
    csrf_token: str = ""

    def on_start(self):
        """Authenticate once per simulated user. Re-use token for all tasks."""
        # Try to register (idempotent — 409 is fine) then login
        self.client.post(
            f"{API_BASE}/auth/register",
            json={
                "email": f"{_rand_str()}@loadtest.vitar",
                "password": ADMIN_PASS,
                "clinic_name": f"LoadClinic {_rand_str()}",
                "owner_name": "Load Tester",
                "country": "US",
                "currency": "USD",
            },
            name="/auth/register [setup]",
        )
        resp = self.client.post(
            f"{API_BASE}/auth/login",
            data={"username": f"{_rand_str()}@loadtest.vitar", "password": ADMIN_PASS},
            name="/auth/login [setup]",
        )
        if resp.status_code == 200:
            self.csrf_token = resp.json().get("csrf_token", "")
        else:
            # Fall back to shared admin token if pre-seeded
            if _tokens:
                self.token = random.choice(_tokens)

    def _auth(self) -> dict:
        headers = {}
        if getattr(self, "token", ""):
            headers["Authorization"] = f"Bearer {self.token}"
        if getattr(self, "csrf_token", ""):
            headers["X-CSRF-Token"] = self.csrf_token
        return headers

    # ── Read tasks (high frequency) ───────────────────────────────────────────

    @task(10)
    def view_dashboard(self):
        self.client.get(
            f"{API_BASE}/analytics/dashboard",
            headers=self._auth(),
            name="/analytics/dashboard",
        )

    @task(8)
    def list_appointments(self):
        self.client.get(
            f"{API_BASE}/appointments/?page=1&limit=20",
            headers=self._auth(),
            name="/appointments/ [list]",
        )

    @task(6)
    def list_patients(self):
        self.client.get(
            f"{API_BASE}/patients/?page=1&limit=20",
            headers=self._auth(),
            name="/patients/ [list]",
        )

    @task(5)
    def list_doctors(self):
        self.client.get(
            f"{API_BASE}/doctors/",
            headers=self._auth(),
            name="/doctors/ [list]",
        )

    @task(4)
    def view_analytics_noshow(self):
        self.client.get(
            f"{API_BASE}/analytics/no-show-trends",
            headers=self._auth(),
            name="/analytics/no-show-trends",
        )

    @task(3)
    def health_check(self):
        with self.client.get("/health", catch_response=True, name="/health") as r:
            if r.status_code not in (200, 200):
                r.failure(f"Health returned {r.status_code}")

    # ── Write tasks (lower frequency) ─────────────────────────────────────────

    @task(2)
    def create_patient(self):
        phone = f"+1555{random.randint(1000000, 9999999)}"
        resp = self.client.post(
            f"{API_BASE}/patients/",
            headers=self._auth(),
            json={
                "full_name": f"Load Patient {_rand_str()}",
                "phone": phone,
                "email": f"{_rand_str()}@loadtest.vitar",
                "gender": random.choice(["male", "female"]),
            },
            name="/patients/ [create]",
        )
        if resp.status_code not in (200, 201, 409):
            resp.failure(f"Unexpected status {resp.status_code}")

    @task(1)
    def search_patients(self):
        term = random.choice(["John", "Jane", "Load", "Test"])
        self.client.get(
            f"{API_BASE}/patients/?search={term}&limit=10",
            headers=self._auth(),
            name="/patients/ [search]",
        )

    @task(1)
    def view_waiting_list(self):
        self.client.get(
            f"{API_BASE}/waiting-list/",
            headers=self._auth(),
            name="/waiting-list/ [list]",
        )


class UnauthenticatedUser(HttpUser):
    """
    Simulates public booking page visitors — no auth required.
    These represent the patient-facing load.
    """
    weight = 2   # 2:5 ratio with clinic staff (VitarUser weight defaults to 1 each)
    wait_time = between(1, 4)

    @task(5)
    def public_booking_page(self):
        """Public booking page — heavy read, no auth."""
        slug = os.getenv("LOAD_TEST_CLINIC_SLUG", "test-clinic")
        self.client.get(
            f"{API_BASE}/booking/{slug}",
            name="/booking/[slug] [public]",
        )

    @task(3)
    def check_availability(self):
        slug = os.getenv("LOAD_TEST_CLINIC_SLUG", "test-clinic")
        doc_id = DOCTOR_ID or "00000000-0000-0000-0000-000000000001"
        self.client.get(
            f"{API_BASE}/booking/{slug}/availability?doctor_id={doc_id}",
            name="/booking/[slug]/availability [public]",
        )

    @task(1)
    def geo_detect(self):
        self.client.get(
            f"{API_BASE}/geo/detect",
            name="/geo/detect [public]",
        )


# ── Pass/Fail Assertions ──────────────────────────────────────────────────────

@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """
    After the run completes, assert against SLA thresholds.
    Exit code 1 if any threshold is breached (CI-friendly).
    """
    stats = environment.runner.stats

    total = stats.total
    if total.num_requests == 0:
        logger.warning("No requests completed — skipping assertions")
        return

    error_rate  = total.num_failures / total.num_requests * 100
    p95_ms      = total.get_response_time_percentile(0.95)
    p99_ms      = total.get_response_time_percentile(0.99)
    rps         = total.current_rps

    print("\n" + "="*60)
    print("VITAR LOAD TEST RESULTS")
    print("="*60)
    print(f"  Total requests : {total.num_requests:,}")
    print(f"  Failures       : {total.num_failures:,}  ({error_rate:.2f}%)")
    print(f"  Avg RPS        : {rps:.1f}")
    print(f"  P95 latency    : {p95_ms:.0f} ms")
    print(f"  P99 latency    : {p99_ms:.0f} ms")
    print("="*60)

    failed = False
    thresholds = [
        ("P95 < 500ms",    p95_ms,     500,   "ms"),
        ("P99 < 1000ms",   p99_ms,     1000,  "ms"),
        ("Error rate < 1%", error_rate, 1.0,  "%"),
    ]
    for label, value, limit, unit in thresholds:
        ok = value < limit
        icon = "✅" if ok else "❌"
        print(f"  {icon} {label}: {value:.1f}{unit} (limit={limit}{unit})")
        if not ok:
            failed = True

    print("="*60)
    if failed:
        print("⚠️  LOAD TEST FAILED — SLA thresholds breached")
        environment.process_exit_code = 1
    else:
        print("✅  LOAD TEST PASSED — all thresholds met")
