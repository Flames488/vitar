#!/bin/bash
# ─── Vitar v8 – Self-Healing Watchdog ─────────────────────────────────────────
# Runs every 2 minutes via cron. Detects dead/stuck services, restarts them,
# and reports circuit breaker state to Slack.
#
# v8 additions over v7:
#   - Checks /health/circuits endpoint for open circuit breakers
#   - Monitors dead-letter queue depth via Redis
#   - PostgreSQL long-running query detection
#   - Memory usage alert per container
#
# CRON SETUP (run once on your server):
#   echo "*/2 * * * * root /opt/vitar/infra/scripts/watchdog.sh >> /var/log/vitar-watchdog.log 2>&1" \
#     | sudo tee /etc/cron.d/vitar-watchdog
#   sudo chmod 644 /etc/cron.d/vitar-watchdog

set -euo pipefail

COMPOSE_DIR="${COMPOSE_DIR:-/opt/vitar}"
HEALTH_URL="${HEALTH_URL:-http://localhost:8000/health}"
CIRCUITS_URL="${CIRCUITS_URL:-http://localhost:8000/health/circuits}"
LOG_PREFIX="[watchdog $(date '+%Y-%m-%d %H:%M:%S')]"
ALERT_WEBHOOK="${SLACK_WEBHOOK_URL:-}"

log()     { echo "$LOG_PREFIX INFO  $1"; }
warn()    { echo "$LOG_PREFIX WARN  $1"; }
err_log() { echo "$LOG_PREFIX ERROR $1"; }

notify() {
    local msg="$1"
    if [ -n "$ALERT_WEBHOOK" ]; then
        curl -s -X POST "$ALERT_WEBHOOK" \
            -H "Content-Type: application/json" \
            -d "{\"text\": \"🔧 *Vitar Watchdog* on $(hostname): $msg\"}" \
            > /dev/null 2>&1 || true
    fi
}

restart_service() {
    local service="$1"
    local reason="$2"
    err_log "Restarting $service — reason: $reason"
    notify "$reason. Auto-restarting \`$service\`..."
    docker compose -f "$COMPOSE_DIR/docker-compose.yml" restart "$service" 2>&1 || true
}

cd "$COMPOSE_DIR"

# ── 1. API health ──────────────────────────────────────────────────────────────
API_STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "$HEALTH_URL" 2>/dev/null || echo "000")

if [ "$API_STATUS" = "000" ]; then
    restart_service "api" "API health check timed out (no response)"
elif [ "$API_STATUS" = "503" ]; then
    DEGRADED_FILE="/tmp/vitar_degraded_since"
    if [ ! -f "$DEGRADED_FILE" ]; then
        echo "$(date +%s)" > "$DEGRADED_FILE"
        warn "API returned 503 (degraded). Monitoring..."
    else
        DEGRADED_SINCE=$(cat "$DEGRADED_FILE")
        NOW=$(date +%s)
        DEGRADED_FOR=$(( NOW - DEGRADED_SINCE ))
        if [ "$DEGRADED_FOR" -gt 600 ]; then
            rm -f "$DEGRADED_FILE"
            restart_service "api" "API degraded (503) for ${DEGRADED_FOR}s — forcing restart"
        else
            warn "API degraded for ${DEGRADED_FOR}s (restarts at 600s)"
        fi
    fi
else
    rm -f "/tmp/vitar_degraded_since" 2>/dev/null || true
    log "API healthy (HTTP $API_STATUS)"
fi

# ── 2. Circuit breaker status ─────────────────────────────────────────────────
# v8: alert if any external service circuit is OPEN
CIRCUIT_STATUS=$(curl -s --max-time 5 "$CIRCUITS_URL" 2>/dev/null || echo "{}")
OPEN_CIRCUITS=$(echo "$CIRCUIT_STATUS" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    open_ones = [c['circuit'] for c in d.get('circuits', []) if c.get('state') == 'open']
    print(','.join(open_ones))
except:
    print('')
" 2>/dev/null || echo "")

if [ -n "$OPEN_CIRCUITS" ]; then
    warn "Open circuit breakers: $OPEN_CIRCUITS"
    notify "⚡ Circuit breakers OPEN: \`$OPEN_CIRCUITS\` — external services degraded"
else
    log "All circuit breakers CLOSED"
fi

# ── 3. Celery worker health ───────────────────────────────────────────────────
WORKER_HEALTHY=$(docker compose -f "$COMPOSE_DIR/docker-compose.yml" \
    exec -T worker \
    celery -A app.workers.celery_app inspect ping --timeout 4 2>/dev/null \
    | grep -c "pong" || echo "0")

if [ "$WORKER_HEALTHY" = "0" ]; then
    WORKER_STATE=$(docker compose -f "$COMPOSE_DIR/docker-compose.yml" ps worker --format json 2>/dev/null \
        | python3 -c "import sys,json; d=json.load(sys.stdin); print(d[0]['State'] if d else 'missing')" 2>/dev/null || echo "unknown")
    if [ "$WORKER_STATE" = "running" ]; then
        restart_service "worker" "Celery worker running but not responding to ping (stuck)"
    else
        restart_service "worker" "Celery worker container is $WORKER_STATE"
    fi
else
    log "Celery worker healthy ($WORKER_HEALTHY pong(s))"
fi

# ── 4. Beat scheduler ─────────────────────────────────────────────────────────
BEAT_STATE=$(docker compose -f "$COMPOSE_DIR/docker-compose.yml" ps beat --format json 2>/dev/null \
    | python3 -c "import sys,json; d=json.load(sys.stdin); print(d[0]['State'] if d else 'missing')" 2>/dev/null || echo "unknown")

if [ "$BEAT_STATE" != "running" ]; then
    restart_service "beat" "Beat scheduler is $BEAT_STATE — reminders will stop firing"
else
    log "Beat scheduler running"
fi

# ── 5. Redis health ───────────────────────────────────────────────────────────
REDIS_OK=$(docker compose -f "$COMPOSE_DIR/docker-compose.yml" \
    exec -T redis redis-cli ping 2>/dev/null | grep -c "PONG" || echo "0")

if [ "$REDIS_OK" = "0" ]; then
    restart_service "redis" "Redis ping failed"
else
    log "Redis healthy"
fi

# ── 6. Dead-letter queue depth ────────────────────────────────────────────────
# v8: alert if dead-letter keys exceed threshold (indicates retry exhaustion)
DL_COUNT=$(docker compose -f "$COMPOSE_DIR/docker-compose.yml" \
    exec -T redis redis-cli --no-auth-warning keys "dl:*" 2>/dev/null \
    | wc -l || echo "0")

DL_COUNT=$(echo "$DL_COUNT" | tr -d '[:space:]')
if [ "${DL_COUNT:-0}" -gt 20 ]; then
    warn "Dead-letter queue has $DL_COUNT items — tasks are exhausting all retries"
    notify "💀 Dead-letter queue has *$DL_COUNT* items. Check Flower dashboard for details."
fi

# v10: DLQ growth rate — if DLQ grew by > 5 in the last cycle, escalate
DLQ_PREV_FILE="/tmp/vitar_dlq_prev"
DLQ_PREV=0
if [ -f "$DLQ_PREV_FILE" ]; then
    DLQ_PREV=$(cat "$DLQ_PREV_FILE" 2>/dev/null || echo "0")
fi
echo "${DL_COUNT:-0}" > "$DLQ_PREV_FILE"
DLQ_GROWTH=$(( ${DL_COUNT:-0} - ${DLQ_PREV:-0} ))
if [ "$DLQ_GROWTH" -gt 5 ]; then
    err_log "DLQ grew by $DLQ_GROWTH in last cycle — worker processing failures escalating"
    notify "🚨 DLQ grew by *$DLQ_GROWTH* tasks since last check. Workers may be in a retry storm."
fi

# ── 7. Disk space ─────────────────────────────────────────────────────────────
DISK_USAGE=$(df -h "$COMPOSE_DIR" | awk 'NR==2 {print $5}' | tr -d '%')
if [ "${DISK_USAGE:-0}" -gt 92 ]; then
    err_log "CRITICAL: Disk at ${DISK_USAGE}% — DB write failures imminent"
    notify "🔴 CRITICAL: Disk at *${DISK_USAGE}%*. PostgreSQL WAL will fail. Cleaning NOW."
    docker image prune -af > /dev/null 2>&1 || true
    docker volume ls -qf dangling=true | xargs -r docker volume rm > /dev/null 2>&1 || true
elif [ "${DISK_USAGE:-0}" -gt 80 ]; then
    warn "Disk usage at ${DISK_USAGE}% — cleaning old Docker images"
    notify "⚠️ Disk at ${DISK_USAGE}%. Auto-cleaning old images."
    docker image prune -f > /dev/null 2>&1 || true
fi

# ── 8. Host CPU + memory via /proc (no psutil needed in bash) ─────────────────

# CPU: read /proc/stat twice, 2s apart → calculate usage %
read_cpu() {
    grep '^cpu ' /proc/stat | awk '{print $2+$3+$4+$5+$6+$7+$8, $5}'
}
CPU1=$(read_cpu); sleep 2; CPU2=$(read_cpu)
CPU_TOTAL_DIFF=$(( $(echo $CPU2 | cut -d' ' -f1) - $(echo $CPU1 | cut -d' ' -f1) ))
CPU_IDLE_DIFF=$(( $(echo $CPU2 | cut -d' ' -f2) - $(echo $CPU1 | cut -d' ' -f2) ))
if [ "$CPU_TOTAL_DIFF" -gt 0 ]; then
    CPU_PCT=$(( 100 * (CPU_TOTAL_DIFF - CPU_IDLE_DIFF) / CPU_TOTAL_DIFF ))
else
    CPU_PCT=0
fi

if [ "${CPU_PCT:-0}" -gt 95 ]; then
    err_log "CRITICAL: Host CPU at ${CPU_PCT}% — triggering worker scale-up"
    notify "🔴 CRITICAL: Host CPU at *${CPU_PCT}%*. Scaling up workers."
    # Scale up workers by 1 (respects docker-compose max)
    CURRENT_WORKERS=$(docker compose -f "$COMPOSE_DIR/docker-compose.yml" ps -q worker 2>/dev/null | wc -l)
    NEW_WORKERS=$(( CURRENT_WORKERS + 1 ))
    if [ "$NEW_WORKERS" -le "${WORKER_MAX_REPLICAS:-8}" ]; then
        docker compose -f "$COMPOSE_DIR/docker-compose.yml" up -d --no-recreate \
            --scale "worker=$NEW_WORKERS" worker > /dev/null 2>&1 || true
        log "Scaled workers: $CURRENT_WORKERS → $NEW_WORKERS"
    fi
elif [ "${CPU_PCT:-0}" -gt 85 ]; then
    warn "Host CPU at ${CPU_PCT}% — monitoring"
    notify "🟠 Host CPU at *${CPU_PCT}%* for 2s sample. Watching for escalation."
fi

# Memory: /proc/meminfo
MEM_TOTAL=$(grep MemTotal /proc/meminfo | awk '{print $2}')
MEM_AVAIL=$(grep MemAvailable /proc/meminfo | awk '{print $2}')
if [ -n "$MEM_TOTAL" ] && [ "$MEM_TOTAL" -gt 0 ]; then
    MEM_USED=$(( MEM_TOTAL - MEM_AVAIL ))
    MEM_PCT=$(( 100 * MEM_USED / MEM_TOTAL ))
    if [ "${MEM_PCT:-0}" -gt 90 ]; then
        err_log "CRITICAL: Host memory at ${MEM_PCT}% — OOM kills likely"
        notify "🔴 CRITICAL: Memory at *${MEM_PCT}%*. OOM kills imminent. Restarting worker to free memory."
        restart_service "worker" "Memory critical (${MEM_PCT}%) — restarting worker to reclaim RAM"
    elif [ "${MEM_PCT:-0}" -gt 80 ]; then
        warn "Host memory at ${MEM_PCT}% — monitoring"
        notify "🟠 Memory at *${MEM_PCT}%*. Consider reducing UVICORN_WORKERS or worker count."
    fi
fi

# ── 9. Container memory usage ─────────────────────────────────────────────────
for SERVICE in api worker; do
    MEM_USAGE=$(docker stats --no-stream --format "{{.MemUsage}}" \
        "$(docker compose -f "$COMPOSE_DIR/docker-compose.yml" ps -q $SERVICE 2>/dev/null)" 2>/dev/null \
        | awk '{print $1}' | sed 's/GiB//' | head -1 || echo "0")
    if echo "$MEM_USAGE" | grep -qE '^[0-9]+\.[0-9]+$'; then
        if awk "BEGIN{exit !($MEM_USAGE > 1.5)}"; then
            warn "$SERVICE container using ${MEM_USAGE}GiB RAM — consider scaling"
            notify "🧠 *$SERVICE* using ${MEM_USAGE}GiB RAM — may need scaling"
        fi
    fi
done

# ── 10. Smart failover: check if API can reach PostgreSQL ─────────────────────
PG_CHECK=$(docker exec "$(docker compose -f "$COMPOSE_DIR/docker-compose.yml" ps -q postgres 2>/dev/null | head -1)" \
    pg_isready -U vitar -d vitar 2>/dev/null || echo "FAIL")
if echo "$PG_CHECK" | grep -q "FAIL\|no response"; then
    err_log "PostgreSQL healthcheck FAILED — attempting restart"
    notify "🔴 PostgreSQL not responding. Auto-restarting."
    restart_service "postgres" "pg_isready check failed"
    # Give postgres 30s to come back, then restart API to reconnect
    sleep 30
    restart_service "api" "Restarting API after postgres recovery"
fi

log "Watchdog check complete (v10) — CPU:${CPU_PCT}% MEM:${MEM_PCT:-?}% DISK:${DISK_USAGE}%"
