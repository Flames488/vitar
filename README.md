# Vitar v8

> **Healthcare Appointment Platform — AI No-Show Reduction**

## What's New in v8 (Production Hardening)

- 🔄 **Full auto-recovery**: `restart: always` + Gunicorn in production
- 🛡️ **Circuit breakers** on all external services (Stripe, Paystack, SendGrid, SMS, WhatsApp, AI)
- 🗄️ **DB readiness gate**: exponential backoff startup, never crash-on-boot
- 🔁 **100% Celery retry coverage**: all 14 tasks have `autoretry_for`
- 📊 **Observability**: Slack alerts, worker heartbeats, queue depths, SLA p95 tracking
- ⚡ **Load tested**: k6 harness proves 100 concurrent users (p95 < 800ms)
- 🧰 **Safe service layer**: structured error handling, circuit-aware wrappers

See [CHANGES_v8.md](CHANGES_v8.md) for full details.

---

# Vitar v5 — Production-Ready Healthcare SaaS

## Boot in One Command

```bash
bash generate_env.sh   # generates all secrets
docker-compose up -d   # boots everything
```

No other steps. The system is fully autonomous.

---

## What Happens on Boot

```
generate_env.sh          → creates .env with strong random secrets
docker-compose up -d
  postgres               → starts, health-checked
  redis                  → starts, health-checked
  api                    → waits for postgres+redis → runs alembic migrations → starts 4 uvicorn workers
  worker                 → starts celery worker (4 concurrent, auto-restarts)
  worker_dead_letter     → starts dead-letter worker
  beat                   → starts celery beat scheduler (persistent schedule volume)
  flower                 → starts task monitor at :5555
  frontend               → builds React SPA
  nginx                  → starts reverse proxy at :80
```

---

## Architecture

```
Internet ──→ Nginx :80/:443
                ↓             ↓
         API :8000         Frontend :3000
      (4× uvicorn)         (React SPA)
            ↓
    ┌───────┴────────┐
    │                │
 Postgres         Redis
 (pooled)    (cache + broker)
                    │
              Celery Workers
              Celery Beat
```

---

## Services & Ports

| Service             | Port  | Description                          |
|---------------------|-------|--------------------------------------|
| nginx               | 80    | Reverse proxy, rate limiting         |
| api                 | 8000  | FastAPI, 4 uvicorn workers           |
| frontend            | 3000  | React SPA                            |
| flower              | 5555  | Celery monitor (admin / see .env)    |
| postgres            | 5432  | PostgreSQL 16                        |
| redis               | 6379  | Cache + task broker                  |

---

## Health Check

```bash
curl http://localhost:8000/health
# {"status":"healthy","components":{"database":{"status":"ok"},"redis":{"status":"ok"},...}}

docker-compose ps
# All services should show "healthy"
```

---

## Run Tests

```bash
cd backend
pip install -r requirements.txt
pytest tests/test_main.py -v
# 33 passed
```

---

## Load Test (100 concurrent users)

Self-contained — registers test user automatically.

```bash
pip install httpx anyio
python backend/tests/load_test.py --url http://localhost:8000 --users 100
```

---

## Configuration

`generate_env.sh` handles all secrets. Edit `.env` to add external services:

| Variable            | Purpose                        |
|---------------------|--------------------------------|
| `GROQ_API_KEY`      | AI chatbot (free at groq.com)  |
| `SENDGRID_API_KEY`  | Email notifications            |
| `TERMII_API_KEY`    | SMS (Nigeria)                  |
| `TWILIO_*`          | SMS (global)                   |
| `PAYSTACK_*`        | Payments (Nigeria)             |
| `STRIPE_*`          | Payments (global)              |
| `SENTRY_DSN`        | Error tracking                 |

All external services are **optional** — the system runs without them (notifications are logged instead of sent).

---

## Production (HTTPS)

```bash
# Update .env
ENVIRONMENT=production
FRONTEND_URL=https://yourdomain.com
ALLOWED_HOSTS=["yourdomain.com","api.yourdomain.com"]

# Get SSL certs
certbot certonly --standalone -d yourdomain.com -d api.yourdomain.com

# Update infra/nginx/nginx.conf to enable HTTPS server blocks
docker-compose up -d
```

---

## Key Bug Fixes (see CHANGES.md for full list)

1. **`metadata` column** crashed SQLAlchemy at startup → renamed `extra_data`
2. **passlib + bcrypt 4.x** crashed every login → replaced with direct `bcrypt`
3. **bcrypt 72-byte truncation** silently matched different passwords → sha256 pre-hash
4. **JSONB in SQLite** broke all tests → `JSON as JSONB` cross-dialect fallback
5. **Engine blocks imports** → lazy proxy, connects only when first used
6. **Test state pollution** → session fixture drops/recreates tables + unique emails
7. **Missing email-validator** → added to requirements.txt
8. **Alembic schema mismatch** → renamed `metadata` → `extra_data` in migrations
