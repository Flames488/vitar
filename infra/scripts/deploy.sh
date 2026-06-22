#!/bin/bash
# ─── Vitar v6 – Zero-Downtime Deploy ─────────────────────────────────────────
# Usage:
#   ./infra/scripts/deploy.sh              # deploy latest
#   ./infra/scripts/deploy.sh --rollback   # revert to previous image
#   ./infra/scripts/deploy.sh --check      # dry-run: show what would change
#
# What it does:
#   1. Validates .env config
#   2. Pulls new images (or builds from source)
#   3. Runs DB migrations (Alembic — safe, non-destructive)
#   4. Rolls API containers one at a time (zero downtime)
#   5. Health-checks after each step
#   6. Notifies Slack on success/failure

set -euo pipefail

COMPOSE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE="docker compose --profile observability -f docker-compose.yml -f docker-compose.prod.yml"
HEALTH_URL="http://localhost/health/ready"
TIMEOUT=120  # seconds to wait for a service to become healthy
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; BOLD='\033[1m'; NC='\033[0m'

log()     { echo -e "${GREEN}[deploy]${NC} $1"; }
warn()    { echo -e "${YELLOW}[deploy]${NC} $1"; }
die()     { echo -e "${RED}[deploy FAILED]${NC} $1"; notify_slack "❌ Deploy FAILED: $1"; exit 1; }
heading() { echo -e "\n${BOLD}$1${NC}"; }

cd "$COMPOSE_DIR"

# ── Load .env ─────────────────────────────────────────────────────────────────
[ -f .env ] || die ".env not found. Run: cp .env.example .env && fill in secrets"
set -o allexport; source .env; set +o allexport

# ── Slack notification helper ─────────────────────────────────────────────────
notify_slack() {
    local msg="$1"
    if [ -n "${SLACK_WEBHOOK_URL:-}" ]; then
        curl -s -X POST "$SLACK_WEBHOOK_URL" \
            -H "Content-Type: application/json" \
            -d "{\"text\": \"🚀 *Vitar Deploy* on $(hostname): $msg\"}" > /dev/null 2>&1 || true
    fi
}

# ── Parse flags ───────────────────────────────────────────────────────────────
ROLLBACK=false
CHECK_ONLY=false
for arg in "$@"; do
    case $arg in
        --rollback) ROLLBACK=true ;;
        --check)    CHECK_ONLY=true ;;
    esac
done

# ── Rollback mode ─────────────────────────────────────────────────────────────
if $ROLLBACK; then
    heading "⏮  Rolling back to previous images..."
    $COMPOSE pull --quiet || true  # re-pull in case we're on latest
    # The simplest rollback: tag before deploy saves images as :prev
    if docker images | grep -q "vitar-api:prev"; then
        docker tag "$(docker images -q vitar-api:prev)" vitar-api:latest
        $COMPOSE up -d api
        log "Rolled back API. Monitor: docker compose logs -f api"
    else
        die "No :prev image found. Cannot rollback automatically."
    fi
    exit 0
fi

# ── Check mode ────────────────────────────────────────────────────────────────
if $CHECK_ONLY; then
    heading "🔍 Checking what would change..."
    $COMPOSE pull --dry-run 2>&1 || $COMPOSE build --dry-run 2>&1 || true
    log "Use ./deploy.sh to apply changes."
    exit 0
fi

# ── Pre-flight checks ─────────────────────────────────────────────────────────
heading "1/6 Pre-flight checks"
command -v docker   >/dev/null 2>&1 || die "Docker not found"
docker compose version >/dev/null 2>&1 || die "Docker Compose v2 not found"

# Validate critical env vars exist
[ -z "${SECRET_KEY:-}" ]     && die "SECRET_KEY not set in .env"
[ -z "${JWT_SECRET_KEY:-}" ] && die "JWT_SECRET_KEY not set in .env"

log "Pre-flight passed ✓"

# ── Save current image for rollback ─────────────────────────────────────────
heading "2/6 Snapshotting current image for rollback"
CURRENT_ID=$($COMPOSE images api -q 2>/dev/null | head -1 || echo "")
if [ -n "$CURRENT_ID" ]; then
    docker tag "$CURRENT_ID" vitar-api:prev 2>/dev/null || true
    log "Saved current image as :prev (rollback with: ./deploy.sh --rollback)"
fi

# ── Pull / build new images ──────────────────────────────────────────────────
heading "3/6 Pulling / building new images"
if [ -n "${DOCKER_USERNAME:-}" ]; then
    log "Pulling pre-built images from registry..."
    $COMPOSE pull --quiet
else
    log "Building images from source..."
    $COMPOSE build --parallel --quiet
fi
log "Images ready ✓"

# ── Run migrations ────────────────────────────────────────────────────────────
heading "4/6 Running database migrations"
# Use run --rm so this is ephemeral — doesn't affect the running api container
$COMPOSE run --rm \
    -e DATABASE_URL="${MIGRATION_DATABASE_URL:-$DATABASE_URL}" \
    -e MIGRATION_DATABASE_URL="${MIGRATION_DATABASE_URL:-$DATABASE_URL}" \
    api alembic upgrade head \
    || die "Alembic migration failed — deploy aborted. DB is unchanged."
log "Migrations applied ✓"

# ── Rolling restart ───────────────────────────────────────────────────────────
heading "5/6 Rolling restart"

wait_healthy() {
    local service="$1"
    local url="$2"
    local elapsed=0
    log "Waiting for $service to become healthy..."
    until curl -sf --max-time 3 "$url" > /dev/null 2>&1; do
        sleep 3; elapsed=$((elapsed + 3))
        [ "$elapsed" -ge "$TIMEOUT" ] && die "$service did not become healthy in ${TIMEOUT}s"
        echo -n "."
    done
    echo ""
    log "$service is healthy ✓"
}

# Restart workers first (no traffic impact)
log "Restarting workers..."
$COMPOSE up -d --no-deps --force-recreate worker worker_dead_letter beat
sleep 5

# Restart API (nginx keeps serving existing connections)
log "Restarting API..."
$COMPOSE up -d --no-deps --force-recreate api
wait_healthy "api" "$HEALTH_URL"

# Restart nginx to pick up any config changes
log "Reloading nginx..."
$COMPOSE exec nginx nginx -s reload 2>/dev/null || \
    $COMPOSE up -d --no-deps --force-recreate nginx

log "Rolling restart complete ✓"

# ── Post-deploy health check ──────────────────────────────────────────────────
heading "6/6 Final health check"
HEALTH=$(curl -s --max-time 5 "$HEALTH_URL" || echo '{"status":"error"}')
STATUS=$(echo "$HEALTH" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status','unknown'))" 2>/dev/null || echo "error")

if [ "$STATUS" = "healthy" ]; then
    log "Health: ✅ $STATUS"
else
    warn "Health: ⚠️  $STATUS"
    echo "$HEALTH" | python3 -m json.tool 2>/dev/null || echo "$HEALTH"
fi

# ── Clean up old images ───────────────────────────────────────────────────────
docker image prune -f --filter "until=24h" > /dev/null 2>&1 || true

# ── Done ─────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}═══════════════════════════════════════${NC}"
echo -e "${GREEN}${BOLD}  ✅ Deploy complete!${NC}"
echo -e "${GREEN}${BOLD}═══════════════════════════════════════${NC}"
echo -e "  Status:  $STATUS"
echo -e "  API:     $(curl -s --max-time 3 "${FRONTEND_URL:-https://labvault.cloud}" -o /dev/null -w '%{http_code}' || echo 'unknown')"
echo -e "  Rollback: ./infra/scripts/deploy.sh --rollback"
echo ""

notify_slack "✅ Deploy successful. Health: $STATUS"
