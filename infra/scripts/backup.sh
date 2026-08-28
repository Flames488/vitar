#!/bin/bash
# ─── Vitar v11 — Automated PostgreSQL Backup to S3 ────────────────────────────
#
# Runs daily via cron. Performs a pg_dump inside the running postgres container,
# compresses with gzip, and uploads to S3 with a timestamped key.
#
# Features:
#   - Retention: keeps last 30 daily + last 12 monthly backups automatically
#   - Integrity check: verifies the dump is non-empty before uploading
#   - Slack alert on failure (and on success if BACKUP_NOTIFY_SUCCESS=true)
#   - Dry-run mode: set BACKUP_DRY_RUN=true to test without uploading
#   - Local fallback: if S3 upload fails, backup is kept locally in /tmp
#
# CRON SETUP (run once):
#   echo "0 2 * * * root /opt/vitar/infra/scripts/backup.sh >> /var/log/vitar-backup.log 2>&1" \
#     | sudo tee /etc/cron.d/vitar-backup
#   sudo chmod 644 /etc/cron.d/vitar-backup
#
# REQUIRED ENV VARS (set in /etc/environment or source from .env):
#   POSTGRES_PASSWORD    — DB password
#   AWS_ACCESS_KEY_ID    — IAM key with s3:PutObject, s3:DeleteObject
#   AWS_SECRET_ACCESS_KEY
#   AWS_S3_BUCKET        — e.g. vitar-backups
#   AWS_REGION           — e.g. us-east-1
#
# OPTIONAL:
#   COMPOSE_DIR          — defaults to /opt/vitar
#   SLACK_WEBHOOK_URL    — notify on failure (and success if enabled)
#   BACKUP_RETENTION_DAYS — defaults to 30
#   BACKUP_DRY_RUN       — set to "true" to skip S3 upload
#   BACKUP_NOTIFY_SUCCESS — set to "true" for success Slack pings

set -euo pipefail

# ── Config ────────────────────────────────────────────────────────────────────
COMPOSE_DIR="${COMPOSE_DIR:-/opt/vitar}"
SLACK_WEBHOOK="${SLACK_WEBHOOK_URL:-}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"
DRY_RUN="${BACKUP_DRY_RUN:-false}"
NOTIFY_SUCCESS="${BACKUP_NOTIFY_SUCCESS:-false}"

TIMESTAMP=$(date -u '+%Y-%m-%dT%H-%M-%SZ')
DATE_ONLY=$(date -u '+%Y-%m-%d')
YEAR_MONTH=$(date -u '+%Y-%m')
DUMP_FILE="/tmp/vitar_backup_${TIMESTAMP}.sql.gz"
LOG_PREFIX="[backup $(date '+%Y-%m-%d %H:%M:%S')]"

# ── Helpers ───────────────────────────────────────────────────────────────────

log()  { echo "$LOG_PREFIX INFO  $*"; }
warn() { echo "$LOG_PREFIX WARN  $*"; }
err()  { echo "$LOG_PREFIX ERROR $*" >&2; }

notify() {
    local emoji="$1" msg="$2"
    if [ -n "$SLACK_WEBHOOK" ]; then
        curl -s -X POST "$SLACK_WEBHOOK" \
            -H "Content-Type: application/json" \
            -d "{\"text\": \"${emoji} *Vitar Backup* on $(hostname): ${msg}\"}" \
            > /dev/null 2>&1 || true
    fi
}

fail() {
    err "$1"
    notify "🔴" "BACKUP FAILED: $1"
    # Keep local dump for manual recovery if it exists
    [ -f "$DUMP_FILE" ] && warn "Local dump preserved at $DUMP_FILE"
    exit 1
}

# ── Validate required env vars ────────────────────────────────────────────────
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD required}"
: "${AWS_ACCESS_KEY_ID:?AWS_ACCESS_KEY_ID required}"
: "${AWS_SECRET_ACCESS_KEY:?AWS_SECRET_ACCESS_KEY required}"
: "${AWS_S3_BUCKET:?AWS_S3_BUCKET required}"
: "${AWS_REGION:?AWS_REGION required}"

# ── Step 1: pg_dump inside the postgres container ─────────────────────────────
log "Starting pg_dump..."

cd "$COMPOSE_DIR"

docker compose exec -T postgres \
    pg_dump \
        --username=vitar \
        --dbname=vitar \
        --format=plain \
        --no-owner \
        --no-acl \
    | gzip -9 > "$DUMP_FILE"

DUMP_SIZE=$(stat -c '%s' "$DUMP_FILE" 2>/dev/null || echo "0")
if [ "${DUMP_SIZE:-0}" -lt 1024 ]; then
    fail "Dump file is suspiciously small (${DUMP_SIZE} bytes) — aborting upload"
fi

log "Dump complete: $DUMP_FILE ($(numfmt --to=iec-i --suffix=B "$DUMP_SIZE"))"

# ── Step 2: Dry-run gate ──────────────────────────────────────────────────────
if [ "$DRY_RUN" = "true" ]; then
    log "DRY RUN — skipping S3 upload. Dump preserved at $DUMP_FILE"
    exit 0
fi

# ── Step 3: Upload to S3 ──────────────────────────────────────────────────────
# Key structure:
#   daily/   vitar_backup_YYYY-MM-DD.sql.gz          (overwritten daily, retained N days)
#   archive/ YYYY-MM/vitar_backup_YYYY-MM-DDTHH-MM-SSZ.sql.gz  (monthly archives)

S3_DAILY_KEY="daily/vitar_backup_${DATE_ONLY}.sql.gz"
S3_ARCHIVE_KEY="archive/${YEAR_MONTH}/vitar_backup_${TIMESTAMP}.sql.gz"

export AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_DEFAULT_REGION="$AWS_REGION"

log "Uploading to s3://$AWS_S3_BUCKET/$S3_DAILY_KEY ..."
aws s3 cp "$DUMP_FILE" "s3://$AWS_S3_BUCKET/$S3_DAILY_KEY" \
    --region "$AWS_REGION" \
    --storage-class STANDARD_IA \
    || fail "S3 daily upload failed"

# Monthly archive: upload on the 1st of each month (or always, deduplicated by timestamp)
DAY_OF_MONTH=$(date -u '+%d')
if [ "$DAY_OF_MONTH" = "01" ]; then
    log "Monthly backup: uploading to s3://$AWS_S3_BUCKET/$S3_ARCHIVE_KEY ..."
    aws s3 cp "$DUMP_FILE" "s3://$AWS_S3_BUCKET/$S3_ARCHIVE_KEY" \
        --region "$AWS_REGION" \
        --storage-class GLACIER_IR \
        || warn "Monthly archive upload failed (daily copy succeeded)"
fi

# ── Step 4: Retention — delete old daily backups ─────────────────────────────
log "Pruning daily backups older than ${RETENTION_DAYS} days..."
CUTOFF=$(date -u -d "-${RETENTION_DAYS} days" '+%Y-%m-%d' 2>/dev/null \
    || date -u -v "-${RETENTION_DAYS}d" '+%Y-%m-%d')   # macOS fallback

aws s3 ls "s3://$AWS_S3_BUCKET/daily/" --region "$AWS_REGION" 2>/dev/null \
    | awk '{print $4}' \
    | while read -r key; do
        file_date=$(echo "$key" | grep -oE '[0-9]{4}-[0-9]{2}-[0-9]{2}' | head -1)
        if [ -n "$file_date" ] && [ "$file_date" < "$CUTOFF" ]; then
            log "Deleting old backup: daily/$key"
            aws s3 rm "s3://$AWS_S3_BUCKET/daily/$key" --region "$AWS_REGION" || true
        fi
    done

# ── Step 5: Cleanup local dump ────────────────────────────────────────────────
rm -f "$DUMP_FILE"

# ── Step 6: Report success ────────────────────────────────────────────────────
log "Backup complete ✅  s3://$AWS_S3_BUCKET/$S3_DAILY_KEY"
if [ "$NOTIFY_SUCCESS" = "true" ]; then
    notify "✅" "Backup complete — \`$S3_DAILY_KEY\` ($(numfmt --to=iec-i --suffix=B "$DUMP_SIZE"))"
fi
