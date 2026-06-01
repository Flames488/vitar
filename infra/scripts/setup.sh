#!/bin/bash
# ─── Vitar v5 – Setup & Deploy Script ─────────────────────────────────────────
# Usage:
#   chmod +x infra/scripts/setup.sh
#   ./infra/scripts/setup.sh [dev|prod]

set -euo pipefail

MODE=${1:-dev}
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'

log()  { echo -e "${GREEN}[Vitar]${NC} $1"; }
warn() { echo -e "${YELLOW}[Vitar]${NC} $1"; }
die()  { echo -e "${RED}[Vitar ERROR]${NC} $1"; exit 1; }

# ── Prerequisite checks ────────────────────────────────────────────────────────
check_deps() {
    log "Checking dependencies..."
    command -v docker   >/dev/null 2>&1 || die "Docker not found. Install: https://docs.docker.com/get-docker/"
    command -v docker   >/dev/null 2>&1 && docker compose version >/dev/null 2>&1 || die "Docker Compose v2 not found"
    log "Dependencies OK"
}

# ── Environment setup ──────────────────────────────────────────────────────────
setup_env() {
    if [ ! -f .env ]; then
        warn ".env not found, copying from .env.example"
        cp .env.example .env

        # Generate secrets automatically
        SECRET_KEY=$(openssl rand -hex 32)
        JWT_KEY=$(openssl rand -hex 32)
        DB_PASS=$(openssl rand -base64 20 | tr -d "=+/" | cut -c1-20)

        # FIX: Use a temp file and targeted replacements so SECRET_KEY and JWT_KEY are different.
        # The .env.example has the same placeholder for both — sed -i with global replace
        # would overwrite both with the same value on the first pass.
        python3 - "$SECRET_KEY" "$JWT_KEY" "$DB_PASS" << 'PYEOF'
import sys, re

secret_key, jwt_key, db_pass = sys.argv[1], sys.argv[2], sys.argv[3]

with open(".env", "r") as f:
    content = f.read()

# Replace first occurrence of the placeholder → SECRET_KEY
content = content.replace("change-me-generate-with-openssl-rand-hex-32", secret_key, 1)
# Replace second occurrence → JWT_SECRET_KEY
content = content.replace("change-me-generate-with-openssl-rand-hex-32", jwt_key, 1)
content = content.replace("change-me-strong-password", db_pass)
content = content.replace("postgresql://vitar:change-me@", f"postgresql://vitar:{db_pass}@")

with open(".env", "w") as f:
    f.write(content)
PYEOF

        log "Generated .env with random secrets"
        warn "IMPORTANT: Fill in your API keys in .env before continuing"
        echo ""
        echo "Required keys to fill in:"
        echo "  - PAYSTACK_SECRET_KEY / STRIPE_SECRET_KEY"
        echo "  - TERMII_API_KEY / TWILIO_ACCOUNT_SID"
        echo "  - SENDGRID_API_KEY"
        echo ""
        read -p "Press ENTER when .env is ready, or Ctrl+C to cancel..."
    else
        log ".env already exists"
    fi
}

# ── Build & start ──────────────────────────────────────────────────────────────
build_and_start() {
    log "Building images..."
    docker compose build --parallel

    log "Starting services..."
    docker compose up -d postgres redis

    log "Waiting for database to be ready..."
    sleep 5
    docker compose exec postgres pg_isready -U vitar || sleep 5

    log "Running database migrations..."
    docker compose run --rm api alembic upgrade head

    log "Starting all services..."
    docker compose up -d

    log "Checking service health..."
    sleep 10
    docker compose ps
}

# ── Dev mode ───────────────────────────────────────────────────────────────────
dev_setup() {
    log "Setting up for DEVELOPMENT..."

    # Override environment for dev
    export ENVIRONMENT=development
    export DEBUG=true

    docker compose -f docker-compose.yml up -d postgres redis

    log "PostgreSQL and Redis running"
    log ""
    log "To start the backend locally:"
    log "  cd backend && pip install -r requirements.txt"
    log "  alembic upgrade head"
    log "  uvicorn app.main:app --reload --port 8000"
    log ""
    log "To start the frontend locally:"
    log "  cd frontend && npm install && npm run dev"
    log ""
    log "To start Celery worker:"
    log "  cd backend && celery -A app.workers.celery_app worker --loglevel=info"
    log ""
    log "API docs: http://localhost:8000/api/docs"
    log "Frontend: http://localhost:5173"
}

# ── Production mode ────────────────────────────────────────────────────────────
prod_setup() {
    log "Setting up for PRODUCTION..."

    # Verify required prod keys are set
    source .env
    [ -z "${PAYSTACK_SECRET_KEY:-}" ] && [ -z "${STRIPE_SECRET_KEY:-}" ] && \
        die "Set at least one payment provider key (PAYSTACK_SECRET_KEY or STRIPE_SECRET_KEY)"
    [ -z "${SENDGRID_API_KEY:-}" ] && warn "SENDGRID_API_KEY not set — emails will not work"
    [ -z "${TERMII_API_KEY:-}" ] && [ -z "${TWILIO_ACCOUNT_SID:-}" ] && \
        warn "No SMS provider configured — SMS reminders will not work"

    build_and_start

    # Install self-healing watchdog cron (runs every 2 minutes)
    WATCHDOG_SCRIPT="$(pwd)/infra/scripts/watchdog.sh"
    chmod +x "$WATCHDOG_SCRIPT" infra/scripts/deploy.sh
    CRON_LINE="*/2 * * * * root COMPOSE_DIR=$(pwd) SLACK_WEBHOOK_URL=\${SLACK_WEBHOOK_URL:-} $WATCHDOG_SCRIPT >> /var/log/vitar-watchdog.log 2>&1"
    if ! grep -qF "vitar-watchdog" /etc/cron.d/vitar-watchdog 2>/dev/null; then
        echo "$CRON_LINE" | sudo tee /etc/cron.d/vitar-watchdog > /dev/null
        sudo chmod 644 /etc/cron.d/vitar-watchdog
        log "Watchdog cron installed (every 2 minutes)"
    else
        log "Watchdog cron already installed"
    fi

    log ""
    log "═══════════════════════════════════════"
    log "  Vitar v6 is LIVE!"
    log "═══════════════════════════════════════"
    log "  App + API: https://labvault.cloud"
    log "  Flower:    http://localhost:5555 (SSH tunnel only)"
    log "  Watchdog:  tail -f /var/log/vitar-watchdog.log"
    log "  Deploy:    ./infra/scripts/deploy.sh"
    log "  Rollback:  ./infra/scripts/deploy.sh --rollback"
    log "═══════════════════════════════════════"
}

# ── Main ───────────────────────────────────────────────────────────────────────
check_deps
setup_env

case $MODE in
    dev)  dev_setup ;;
    prod) prod_setup ;;
    *)    die "Unknown mode: $MODE. Use 'dev' or 'prod'" ;;
esac
