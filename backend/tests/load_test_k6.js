/**
 * Vitar v8 — k6 Load Test
 *
 * Tests the 3 critical load paths:
 *   1. Auth token acquisition
 *   2. Appointment list (hot cached path)
 *   3. Analytics dashboard (heavy aggregation path)
 *
 * Run:
 *   k6 run --env BASE_URL=https://your-server.com \
 *          --env EMAIL=admin@clinic.com \
 *          --env PASSWORD=yourpassword \
 *          backend/tests/load_test_k6.js
 *
 * Targets from error report:
 *   20  users → must be ✅ stable
 *   50  users → must be ✅ stable
 *   100 users → target ✅ (p95 < 500ms)
 *   150 users → stretch goal
 */

import http from 'k6/http';
import { check, sleep, group } from 'k6';
import { Rate, Trend, Counter } from 'k6/metrics';

// ── Custom metrics ────────────────────────────────────────────────────────────
const errorRate        = new Rate('error_rate');
const authDuration     = new Trend('auth_duration_ms',     true);
const appointmentsDur  = new Trend('appointments_duration_ms', true);
const analyticsDur     = new Trend('analytics_duration_ms',    true);
const cacheHits        = new Counter('cache_hits');
const cacheMisses      = new Counter('cache_misses');

// ── Thresholds ────────────────────────────────────────────────────────────────
export const options = {
  thresholds: {
    'http_req_failed':            ['rate<0.01'],   // <1% errors
    'error_rate':                 ['rate<0.01'],
    'http_req_duration':          ['p(95)<800'],   // p95 under 800ms
    'appointments_duration_ms':   ['p(95)<500'],   // cached path fast
    'analytics_duration_ms':      ['p(95)<1000'],  // aggregation < 1s
    'auth_duration_ms':           ['p(95)<600'],
  },

  scenarios: {
    // Ramp: 0→20→50→100→50→0 over ~6 minutes
    load_ramp: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '30s', target: 20  },   // warm-up
        { duration: '60s', target: 20  },   // stable at 20
        { duration: '30s', target: 50  },   // ramp to 50
        { duration: '60s', target: 50  },   // stable at 50
        { duration: '30s', target: 100 },   // ramp to 100 — key gate
        { duration: '90s', target: 100 },   // sustain 100 users
        { duration: '30s', target: 0   },   // ramp down
      ],
    },

    // Spike test: sudden burst to 150
    spike: {
      executor: 'ramping-vus',
      startVUs: 0,
      startTime: '7m',
      stages: [
        { duration: '10s', target: 150 },
        { duration: '30s', target: 150 },
        { duration: '10s', target: 0   },
      ],
    },
  },
};

// ── Config ────────────────────────────────────────────────────────────────────
const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
const EMAIL    = __ENV.EMAIL    || 'test@clinic.com';
const PASSWORD = __ENV.PASSWORD || 'testpassword';

// ── Auth helper ───────────────────────────────────────────────────────────────
function login() {
  const res = http.post(
    `${BASE_URL}/api/v1/auth/login`,
    JSON.stringify({ email: EMAIL, password: PASSWORD }),
    { headers: { 'Content-Type': 'application/json' } }
  );
  authDuration.add(res.timings.duration);
  check(res, { 'login 200': r => r.status === 200 });
  errorRate.add(res.status !== 200);
  if (res.status !== 200) return null;
  return res.json('csrf_token');
}

// ── Virtual User scenario ─────────────────────────────────────────────────────
export default function () {
  const csrfToken = login();
  if (!csrfToken) { sleep(1); return; }

  const headers = {
    'Content-Type': 'application/json',
    'X-CSRF-Token': csrfToken,
  };

  group('Appointments list (cached hot path)', () => {
    const res = http.get(`${BASE_URL}/api/v1/appointments/`, { headers });
    appointmentsDur.add(res.timings.duration);
    const ok = check(res, {
      'appointments 200':       r => r.status === 200,
      'appointments has items': r => r.json('items') !== undefined,
    });
    errorRate.add(!ok);

    // Track cache header if present
    const cached = res.headers['X-Cache'] || res.json('_cached');
    if (cached) cacheHits.add(1); else cacheMisses.add(1);
  });

  sleep(0.5);

  group('Analytics dashboard (aggregation path)', () => {
    const res = http.get(`${BASE_URL}/api/v1/analytics/dashboard`, { headers });
    analyticsDur.add(res.timings.duration);
    const ok = check(res, { 'analytics 200': r => r.status === 200 });
    errorRate.add(!ok);
  });

  sleep(0.5);

  group('Health check', () => {
    const res = http.get(`${BASE_URL}/health`);
    check(res, {
      'health 200':     r => r.status === 200,
      'health ok':      r => ['healthy', 'degraded'].includes(r.json('status')),
    });
  });

  sleep(1);
}

// ── Summary handler ───────────────────────────────────────────────────────────
export function handleSummary(data) {
  const passed = Object.values(data.metrics).every(m => {
    if (!m.thresholds) return true;
    return Object.values(m.thresholds).every(t => !t.ok === false);
  });

  return {
    'stdout': JSON.stringify({
      verdict: passed ? '✅ PASSED' : '❌ FAILED',
      p95_overall_ms:       data.metrics.http_req_duration?.values?.['p(95)'],
      p95_appointments_ms:  data.metrics.appointments_duration_ms?.values?.['p(95)'],
      p95_analytics_ms:     data.metrics.analytics_duration_ms?.values?.['p(95)'],
      error_rate:           data.metrics.error_rate?.values?.rate,
      cache_hits:           data.metrics.cache_hits?.values?.count,
      cache_misses:         data.metrics.cache_misses?.values?.count,
      vus_max:              data.metrics.vus_max?.values?.value,
    }, null, 2),
    'load_test_result.json': JSON.stringify(data, null, 2),
  };
}
