# Vitar v5.1 — Security & Stability Audit Report

**Audited by:** Senior Software Engineer (AI-assisted)  
**Date:** April 2026  
**Test results:** 33/33 passing ✅

---

## Production Readiness Score: 6.5 → 7.5 / 10

After applying all fixes in this audit cycle.

---

## Bugs Fixed in This Release (v5.1)

### 🔴 Critical

**Bug 1 — `no_show_trends` crashes on every request**  
File: `backend/app/api/v1/endpoints/analytics.py`  
Root cause: Two compounded bugs:
- `db.bind` was removed in SQLAlchemy 2.0 → raises `AttributeError` at runtime
- `func.cast(expr, "integer")` — second argument must be a SQLAlchemy type object, not a string → raises `CompileError`

Fix: Replaced with `sqlalchemy.case()` conditional sum — the correct SA 2.0 pattern.

---

### 🟠 High

**Bug 2 — Rate limiter Redis key explosion under load**  
File: `backend/app/core/middleware.py`  
Root cause: Rate limit bucket key included the full URL path (`/api/v1/appointments/uuid-1`). Every unique resource ID created its own Redis key. With 100 concurrent users each hitting multiple resources, this creates thousands of keys per minute instead of dozens — exhausting Redis `maxmemory` budget and making per-endpoint rate limits ineffective.  
Fix: Normalise path by stripping UUIDs and numeric IDs before keying.

**Bug 3 — Password strength not enforced on `/reset-password`**  
File: `backend/app/api/v1/endpoints/auth.py`  
Root cause: `/register` enforces min-length, digit, and uppercase rules, but `/reset-password` did not — a user could reset to `"password"`.  
Fix: Added identical strength validation before processing the reset.

**Bug 4 — Trial booking counter not atomic with commit**  
File: `backend/app/api/v1/endpoints/booking.py`  
Root cause: `trial_bookings_used` was incremented on the in-memory `clinic` object before `db.commit()`. If the commit failed (e.g. race-condition slot conflict), the rollback reset the DB row but the object remained dirty — the counter was effectively lost.  
Fix: Moved the increment inside the `try` block so it is always within the same commit/rollback unit.

---

### 🟡 Medium

**Bug 5 — `_LazyEngine` not thread-safe**  
File: `backend/app/core/database.py`  
Root cause: Two threads could both evaluate `_real is None` simultaneously before either completes `_make_engine()`, resulting in two parallel engine creation attempts.  
Fix: Added `threading.Lock()` around the initialisation check.

**Bug 6 — Health check DB latency always reported as `0`**  
File: `backend/app/core/health.py`  
Root cause: `latency_ms` was hardcoded to `0` instead of measured.  
Fix: Added `perf_counter()` timing around the `SELECT 1` probe.

**Bug 7 — Missing `Content-Security-Policy` response header**  
File: `backend/app/core/middleware.py`  
Root cause: All other security headers were present (HSTS, X-Frame-Options, Referrer-Policy, etc.) but CSP was absent — no XSS mitigation layer at the HTTP level.  
Fix: Added a conservative `Content-Security-Policy` header.

---

### 🟢 Low / Housekeeping

**Bug 8 — Import before module docstring in `ai_service.py`**  
File: `backend/app/services/ai_service.py`  
Fix: Moved `from app.core.utils import utcnow` to after the docstring.

**Bug 9 — `fire_pending_reminders` silently drops backlog**  
File: `backend/app/workers/tasks.py`  
Fix: Added a back-pressure check — if the 200-row cap is hit and more items remain, a `WARNING` log is emitted so ops can scale workers or tighten the beat interval.

**Bug 10 — Orphaned `@supabase` dependencies in frontend**  
File: `frontend/package.json`  
Fix: Removed `@supabase/ssr` and `@supabase/supabase-js` (never imported anywhere in source).

**Bug 11 — `generate_env.sh` missing production domain guidance**  
File: `generate_env.sh`  
Fix: Added commented instructions for setting `ALLOWED_ORIGINS` and `ALLOWED_HOSTS` to the production domain before going live.

**Bug 12 — Beat service healthcheck too permissive**  
File: `docker-compose.yml`  
Fix: Tightened beat healthcheck to verify Celery connectivity in addition to file existence.

---

## Remaining Known Issues (Require Coordinated Refactor)

These are documented but not changed — they require deliberate architectural decisions:

| Issue | Risk | Recommended Fix |
|-------|------|-----------------|
| JWT stored in `localStorage` | High — XSS-accessible | Switch to `httpOnly SameSite=Strict` cookies + CSRF token |
| No refresh token revocation | Medium — stolen tokens valid 30 days | Store token hash in DB; invalidate on use |
| `react-query` v3 (outdated) | Low | Upgrade to `@tanstack/react-query` v5 |
| `no_show_trends` uses `date_trunc` (PG-only) | Low | Add SQLite fallback for test coverage |

---

## Scalability — 100 Concurrent Users ✅

| Component | Capacity | Status |
|-----------|----------|--------|
| PostgreSQL connections | 60 total (4 workers × 15) vs 200 max | ✅ Headroom |
| Redis rate limiter | Fixed key explosion | ✅ Fixed |
| Analytics queries | 60s Redis cache | ✅ Cached |
| Double-booking | SELECT FOR UPDATE SKIP LOCKED | ✅ Correct |
| Celery throughput | 4 workers, prefetch=1 | ✅ No starvation |
| Notification backlog | 200-job cap + backpressure warning | ✅ Observable |

