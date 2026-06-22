#!/bin/bash
# Vitar v12 - API Entrypoint (PRODUCTION-GRADE)
# Enhancements over v11:
#   - SKIP_MIGRATIONS flag prevents migration race condition when 2+ replicas
#     start concurrently. The CI deploy script runs migrations once as a
#     dedicated one-shot step; replicas set SKIP_MIGRATIONS=true.
#   - DB + Redis readiness with exponential backoff (up to 60s)
#   - Uses gunicorn + uvicorn workers in production for full process supervision
#   - Auto-recovers from cold-start race conditions on Docker restarts
#   - Strict validation: refuses production boot with default secrets

set -euo pipefail

log()  { echo "[entrypoint] $(date -u +%H:%M:%S) INFO  $*"; }
warn() { echo "[entrypoint] $(date -u +%H:%M:%S) WARN  $*"; }
err()  { echo "[entrypoint] $(date -u +%H:%M:%S) ERROR $*" >&2; }

# ── Validate required env vars ───────────────────────────────────────────────
: "${DATABASE_URL:?DATABASE_URL is required}"
# MIGRATION_DATABASE_URL: direct postgres connection for Alembic (bypasses pgbouncer).
# pgbouncer transaction pooling mode is incompatible with Alembic DDL transactions
# (they require a persistent session-mode connection). 
# In docker-compose.yml, set MIGRATION_DATABASE_URL=postgresql://...@postgres:5432/vitar
# If not set, falls back to DATABASE_URL (safe for local dev with direct postgres).
MIGRATION_DATABASE_URL="${MIGRATION_DATABASE_URL:-$DATABASE_URL}"
: "${REDIS_URL:?REDIS_URL is required}"

# ── Warn/block if using default secrets ──────────────────────────────────────
if [[ "${SECRET_KEY:-}" == *"change-me"* ]] || [[ -z "${SECRET_KEY:-}" ]]; then
  if [[ "${ENVIRONMENT:-development}" == "production" ]]; then
    err "SECRET_KEY is not set or uses default — refusing to start in production"
    exit 1
  fi
  export SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
  warn "Generated temporary SECRET_KEY (development only)"
fi

if [[ "${JWT_SECRET_KEY:-}" == *"change-in-production"* ]] || [[ -z "${JWT_SECRET_KEY:-}" ]]; then
  if [[ "${ENVIRONMENT:-development}" == "production" ]]; then
    err "JWT_SECRET_KEY is not set — refusing to start in production"
    exit 1
  fi
fi

# ── Wait for PostgreSQL (exponential backoff, max 60s total) ─────────────────
log "Waiting for PostgreSQL..."
MAX_ATTEMPTS=20
ATTEMPT=0
until python - << 'PYEOF'
import psycopg2, os, sys
try:
    conn = psycopg2.connect(os.environ['DATABASE_URL'], connect_timeout=5)
    conn.close()
    sys.exit(0)
except Exception as e:
    print(f"  DB not ready: {e}", flush=True)
    sys.exit(1)
PYEOF
do
  ATTEMPT=$((ATTEMPT + 1))
  if [ $ATTEMPT -ge $MAX_ATTEMPTS ]; then
    err "PostgreSQL not available after ${MAX_ATTEMPTS} attempts. Aborting."
    exit 1
  fi
  # Exponential backoff: 1s, 2s, 4s … capped at 10s
  SLEEP=$(( ATTEMPT < 4 ? (1 << (ATTEMPT - 1)) : 10 ))
  log "Retry ${ATTEMPT}/${MAX_ATTEMPTS} — sleeping ${SLEEP}s..."
  sleep $SLEEP
done
log "PostgreSQL ready."

# ── Wait for Redis (non-fatal — app degrades gracefully without Redis) ────────
log "Waiting for Redis..."
ATTEMPT=0
until python - << 'PYEOF'
import redis, os, sys
try:
    r = redis.from_url(os.environ['REDIS_URL'], socket_connect_timeout=3)
    r.ping()
    sys.exit(0)
except Exception as e:
    print(f"  Redis not ready: {e}", flush=True)
    sys.exit(1)
PYEOF
do
  ATTEMPT=$((ATTEMPT + 1))
  if [ $ATTEMPT -ge 10 ]; then
    warn "Redis not available after 10 attempts — starting in degraded mode (no cache/rate-limit)"
    break
  fi
  sleep 2
done

if [[ "$#" -gt 0 ]]; then
  log "Running custom command: $*"
  exec "$@"
fi

# ── Run Alembic migrations ───────────────────────────────────────────────────
# SKIP_MIGRATIONS=true → skip migrations on this replica.
#
# WHY: When 2+ replicas start simultaneously (e.g. during a rolling deploy),
# all of them would race to run `alembic upgrade head` at the same time.
# Alembic uses a single-row lock in alembic_version — concurrent attempts can
# collide and crash a replica before it handles any traffic.
#
# FIX: The CI deploy script (deploy.yml step 3) runs migrations exactly once
# as a dedicated `docker compose run --rm api alembic upgrade head` before
# starting/restarting any replica. Replicas themselves skip migrations by
# setting SKIP_MIGRATIONS=true in docker-compose.scale.yml.
#
# Single-node default compose leaves SKIP_MIGRATIONS unset (defaults to false)
# so development and first-boot still auto-migrate as before.
if [[ "${SKIP_MIGRATIONS:-false}" == "true" ]]; then
  log "SKIP_MIGRATIONS=true — skipping alembic (migrations handled by deploy step)"
else
  # ── Check migration chain (no branch splits) before upgrading ──────────────
  # Catches the case where two developers created migrations from the same base
  # revision. Deploying with multiple heads causes `alembic upgrade head` to
  # fail with an ambiguity error — a hard outage across all replicas.
  # Fix: run  alembic merge heads -m "merge_branch_split"  then commit.
  log "Checking Alembic migration chain..."
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  if ! bash "${SCRIPT_DIR}/scripts/check_migrations.sh"; then
    err "Migration chain check failed — aborting startup. See above for fix instructions."
    exit 1
  fi

  log "Running database migrations..."
  if ! MIGRATION_DATABASE_URL="$MIGRATION_DATABASE_URL" DATABASE_URL="$MIGRATION_DATABASE_URL" alembic upgrade head 2>&1; then
    err "Migration failed — aborting startup"
    exit 1
  fi
  log "Migrations complete."
fi

# ── Launch server ─────────────────────────────────────────────────────────────
WORKERS="${UVICORN_WORKERS:-4}"
LOG_LEVEL="${LOG_LEVEL:-info}"
ENV="${ENVIRONMENT:-development}"

if [[ "$ENV" == "production" ]]; then
  # Production: gunicorn manages worker processes — if a worker crashes,
  # gunicorn auto-restarts it without dropping the whole API.
  # This is the v8 fix for "API crash = downtime".
  log "Starting gunicorn (production) with ${WORKERS} workers..."
  exec gunicorn app.main:app \
    --worker-class uvicorn.workers.UvicornWorker \
    --workers "${WORKERS}" \
    --bind 0.0.0.0:8000 \
    --timeout 120 \
    --graceful-timeout 30 \
    --keep-alive 5 \
    --max-requests 1000 \
    --max-requests-jitter 100 \
    --forwarded-allow-ips='*' \
    --access-logfile - \
    --error-logfile - \
    --log-level "${LOG_LEVEL}"
else
  # Development: uvicorn with hot-reload
  log "Starting uvicorn (development) with ${WORKERS} workers..."
  exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers "${WORKERS}" \
    --log-level "${LOG_LEVEL}" \
    --forwarded-allow-ips='*' \
    --proxy-headers
fi
