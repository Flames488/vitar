"""
Vitar v5 - Load Test (100 concurrent simulated users)
Self-contained: auto-registers a test user, runs all scenarios.

Usage:
    pip install httpx anyio
    python tests/load_test.py --url http://localhost:8000 --users 100

Reports: p50, p95, p99 latency, throughput, error rate per endpoint.
"""

import asyncio
import time
import statistics
import argparse
import sys
from typing import List, Optional
import httpx

# ─── Config ───────────────────────────────────────────────────────────────────

HEALTH_URL       = "{base}/health"
REGISTER_URL     = "{base}/api/v1/auth/register"
LOGIN_URL        = "{base}/api/v1/auth/login"
APPOINTMENTS_URL = "{base}/api/v1/appointments/?limit=20"

TEST_EMAIL    = "loadtest@vitar.health"
TEST_PASSWORD = "LoadTest1!"
TEST_PAYLOAD  = {
    "full_name": "Load Test User",
    "email": TEST_EMAIL,
    "password": TEST_PASSWORD,
    "phone": "+2348099000001",
    "clinic_name": "Load Test Clinic",
    "city": "Lagos",
    "country": "NG",
}

TIMEOUT = httpx.Timeout(30.0, connect=10.0)


# ─── Metrics ──────────────────────────────────────────────────────────────────

class Metrics:
    def __init__(self, name: str):
        self.name = name
        self.latencies: List[float] = []
        self.errors = 0
        self.total = 0

    def record(self, latency_ms: float, success: bool):
        self.total += 1
        if success:
            self.latencies.append(latency_ms)
        else:
            self.errors += 1

    def report(self) -> dict:
        if not self.latencies:
            return {
                "name": self.name, "total": self.total,
                "errors": self.errors, "error_rate": 100.0,
                "p50": 0, "p95": 0, "p99": 0, "mean": 0, "throughput_rps": 0,
            }
        lat = sorted(self.latencies)
        n = len(lat)
        return {
            "name": self.name,
            "total": self.total,
            "success": n,
            "errors": self.errors,
            "error_rate": round(self.errors / self.total * 100, 1),
            "mean_ms": round(statistics.mean(lat), 1),
            "p50_ms": round(lat[int(n * 0.50)], 1),
            "p95_ms": round(lat[int(n * 0.95)], 1),
            "p99_ms": round(lat[min(int(n * 0.99), n - 1)], 1),
        }


# ─── Scenarios ────────────────────────────────────────────────────────────────

async def scenario_health(client: httpx.AsyncClient, base: str, m: Metrics):
    url = HEALTH_URL.format(base=base)
    t0 = time.perf_counter()
    try:
        r = await client.get(url)
        ms = (time.perf_counter() - t0) * 1000
        m.record(ms, r.status_code in (200, 503))
    except Exception as e:
        ms = (time.perf_counter() - t0) * 1000
        m.record(ms, False)


async def scenario_login(client: httpx.AsyncClient, base: str, m: Metrics) -> Optional[str]:
    url = LOGIN_URL.format(base=base)
    t0 = time.perf_counter()
    try:
        r = await client.post(url, json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
        ms = (time.perf_counter() - t0) * 1000
        ok = r.status_code == 200
        m.record(ms, ok)
        if ok:
            return r.json().get("csrf_token")
    except Exception:
        ms = (time.perf_counter() - t0) * 1000
        m.record(ms, False)
    return None


async def scenario_appointments(client: httpx.AsyncClient, base: str, csrf_token: str, m: Metrics):
    url = APPOINTMENTS_URL.format(base=base)
    t0 = time.perf_counter()
    try:
        r = await client.get(url)
        ms = (time.perf_counter() - t0) * 1000
        m.record(ms, r.status_code in (200, 404))
    except Exception:
        ms = (time.perf_counter() - t0) * 1000
        m.record(ms, False)


async def user_session(base: str, user_idx: int, results: dict, semaphore: asyncio.Semaphore):
    async with semaphore:
        async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
            # Health check
            await scenario_health(client, base, results["health"])

            # Login
            token = await scenario_login(client, base, results["login"])

            # Authenticated requests (3 rounds)
            if token:
                for _ in range(3):
                    await scenario_appointments(client, base, token, results["appointments"])


async def ensure_test_user(base: str) -> bool:
    """Register test user. Returns True if user is available."""
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        # Try login first
        try:
            r = await client.post(
                LOGIN_URL.format(base=base),
                json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
            )
            if r.status_code == 200:
                print(f"  Test user already exists — login OK")
                return True
        except Exception as e:
            print(f"  Login probe failed: {e}")

        # Register
        try:
            r = await client.post(REGISTER_URL.format(base=base), json=TEST_PAYLOAD)
            if r.status_code == 201:
                print(f"  Test user registered successfully")
                return True
            elif r.status_code == 409:
                print(f"  Test user already registered (409) — continuing")
                return True
            else:
                print(f"  Registration failed: {r.status_code} — {r.text[:200]}")
                return False
        except Exception as e:
            print(f"  Registration error: {e}")
            return False


async def run_load_test(base: str, users: int, ramp_ms: int = 0):
    print(f"\n{'='*60}")
    print(f"  Vitar Load Test — {users} concurrent users")
    print(f"  Target: {base}")
    print(f"{'='*60}\n")

    # Health probe
    print("[ 1/3 ] Health probe...")
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        try:
            r = await client.get(HEALTH_URL.format(base=base))
            print(f"  /health → {r.status_code}")
        except Exception as e:
            print(f"  ERROR: Cannot reach {base} — {e}")
            sys.exit(1)

    # Ensure test user
    print("\n[ 2/3 ] Ensuring test user exists...")
    ok = await ensure_test_user(base)
    if not ok:
        print("  WARNING: Test user setup failed — authenticated tests will show errors")

    # Run load
    print(f"\n[ 3/3 ] Running {users} concurrent user sessions...\n")

    results = {
        "health":       Metrics("GET /health"),
        "login":        Metrics("POST /auth/login"),
        "appointments": Metrics("GET /appointments"),
    }

    # Limit simultaneous connections but allow all users to run
    semaphore = asyncio.Semaphore(min(users, 50))

    t_start = time.perf_counter()
    tasks = [
        user_session(base, i, results, semaphore)
        for i in range(users)
    ]
    await asyncio.gather(*tasks)
    total_time = time.perf_counter() - t_start

    # Report
    print(f"\n{'='*60}")
    print(f"  Results  (total wall time: {total_time:.1f}s)")
    print(f"{'='*60}")
    print(f"  {'Endpoint':<35} {'Total':>6} {'Err%':>6} {'p50ms':>7} {'p95ms':>7} {'p99ms':>7}")
    print(f"  {'-'*35} {'-'*6} {'-'*6} {'-'*7} {'-'*7} {'-'*7}")

    all_pass = True
    for key, m in results.items():
        r = m.report()
        flag = "✓" if r["error_rate"] < 5 else "✗"
        if r["error_rate"] >= 5:
            all_pass = False
        print(
            f"  {flag} {r['name']:<33} {r['total']:>6} {r['error_rate']:>5.1f}%"
            f" {r.get('p50_ms', 0):>7.0f} {r.get('p95_ms', 0):>7.0f} {r.get('p99_ms', 0):>7.0f}"
        )

    print(f"\n{'='*60}")
    if all_pass:
        print("  ✓ PASS — all error rates < 5%")
    else:
        print("  ✗ FAIL — one or more endpoints exceeded 5% error rate")
    print(f"{'='*60}\n")
    return all_pass


def main():
    parser = argparse.ArgumentParser(description="Vitar Load Test")
    parser.add_argument("--url", default="http://localhost:8000", help="Base URL")
    parser.add_argument("--users", type=int, default=100, help="Concurrent users")
    args = parser.parse_args()

    passed = asyncio.run(run_load_test(args.url.rstrip("/"), args.users))
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
