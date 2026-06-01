#!/bin/bash
# generate-userlist.sh — Generates /etc/pgbouncer/userlist.txt at container startup.
#
# Called from the pgbouncer container entrypoint (see docker-compose.yml).
# Uses MD5 auth format: "md5" + md5(password + username)
# Compatible with pgbouncer.ini auth_type=md5, edoburu/pgbouncer, and
# standard PgBouncer deployments.
#
# Required environment variables (set in docker-compose.yml):
#   DB_USER      - PostgreSQL username (e.g. vitar)
#   DB_PASSWORD  - PostgreSQL password (from POSTGRES_PASSWORD env var)
#
# Usage: docker compose run pgbouncer /generate-userlist.sh

set -euo pipefail

USERLIST="/etc/pgbouncer/userlist.txt"
USER="${DB_USER:-vitar}"
PASS="${DB_PASSWORD:-}"

if [[ -z "$PASS" ]]; then
  echo "[generate-userlist] ERROR: DB_PASSWORD is not set. Cannot generate userlist." >&2
  exit 1
fi

# MD5 auth format for pgbouncer: "md5" + md5(password + username)
# This avoids requiring python-bcrypt in the pgbouncer container.
HASH=$(echo -n "${PASS}${USER}" | md5sum | cut -d' ' -f1)
MD5_HASH="md5${HASH}"

# pgbouncer admin user (separate password for monitoring)
PGBOUNCER_PASS="${PGBOUNCER_ADMIN_PASSWORD:-pgbouncer_$(openssl rand -hex 8)}"
PGBOUNCER_HASH=$(echo -n "${PGBOUNCER_PASS}pgbouncer" | md5sum | cut -d' ' -f1)
PGBOUNCER_MD5="md5${PGBOUNCER_HASH}"

mkdir -p "$(dirname "$USERLIST")"
cat > "$USERLIST" << EOF
"${USER}" "${MD5_HASH}"
"pgbouncer" "${PGBOUNCER_MD5}"
EOF

chmod 640 "$USERLIST"
echo "[generate-userlist] userlist.txt written for user '${USER}' (MD5 auth)."
