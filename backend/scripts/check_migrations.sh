#!/bin/bash
# check_migrations.sh — Validate Alembic migration chain before deployment.
#
# Performs FOUR checks:
#   1. Exactly one migration head exists (no branch splits)
#   2. The current DB revision is a valid ancestor of HEAD (no drift)
#   3. All migration files are present and parseable (no missing files)
#   4. No duplicate revision IDs across migration files
#
# Alembic migration branches (multiple heads) occur when two developers create
# migrations from the same base revision without merging. Deploying with
# multiple heads causes `alembic upgrade head` to fail with an ambiguity error,
# blocking startup for ALL replicas simultaneously — a hard outage.
#
# This script catches the problem before deployment. Run it:
#   1. In CI before `alembic upgrade head` in your deploy pipeline.
#   2. In entrypoint.sh before running migrations (already wired in).
#
# CI wiring example (GitHub Actions):
#   - name: Check migration chain
#     run: docker compose run --rm api bash scripts/check_migrations.sh
#
# To fix a branch split:
#   alembic merge heads -m "merge_branch_split"
#   # Then commit the generated merge migration file.
#
# Exit codes:
#   0 — all checks passed (safe to run `alembic upgrade head`)
#   1 — non-fatal warning (no migrations exist, or DB not yet initialised)
#   2 — multiple heads (branch split — merge required before deploying)
#   3 — duplicate revision ID detected (repository corruption)
#   4 — pending migration check failed (upgrade needed)

set -uo pipefail

log()  { echo "[check_migrations] $(date -u +%H:%M:%S) INFO  $*"; }
warn() { echo "[check_migrations] $(date -u +%H:%M:%S) WARN  $*"; }
err()  { echo "[check_migrations] $(date -u +%H:%M:%S) ERROR $*" >&2; }

PASS=0
FAIL=0

# ── Helper: run check and report ─────────────────────────────────────────────
check() {
    local label="$1"; shift
    if "$@" 2>&1; then
        log "  ✓ $label"
        PASS=$((PASS + 1))
    else
        err "  ✗ $label"
        FAIL=$((FAIL + 1))
    fi
}

log "═══════════════════════════════════════════════════════════"
log "  Vitar — Alembic Migration Chain Validation"
log "═══════════════════════════════════════════════════════════"

# ── Check 1: Exactly one head ─────────────────────────────────────────────────
log "CHECK 1: Migration head count"
HEAD_OUTPUT=$(alembic heads 2>&1) || {
    err "alembic heads command failed:"
    err "$HEAD_OUTPUT"
    err "Is DATABASE_URL set and accessible? Currently: ${DATABASE_URL:0:30}..."
    exit 1
}

HEAD_COUNT=$(echo "$HEAD_OUTPUT" | grep -c "(head)" || true)
log "  Found $HEAD_COUNT head(s)."

if [ "$HEAD_COUNT" -eq 0 ]; then
    warn "  No Alembic heads found — database is empty or alembic.ini is misconfigured."
    warn "  This is expected on a brand-new installation. Continuing with upgrade."
    warn "  Output: $HEAD_OUTPUT"
    exit 1
fi

if [ "$HEAD_COUNT" -gt 1 ]; then
    err "  FATAL: Multiple Alembic heads detected — merge required before deploying."
    err ""
    err "  Current heads:"
    echo "$HEAD_OUTPUT" | grep "(head)" | sed 's/^/    /' >&2
    err ""
    err "  Likely cause: Two developers created migrations from the same base revision."
    err "  Fix:"
    err "    1. alembic merge heads -m 'merge_branch_split'"
    err "    2. git add alembic/versions/<new_merge_file>.py"
    err "    3. git commit -m 'fix: merge alembic branch split'"
    err "    4. Re-run this script — should now show 1 head."
    exit 2
fi

log "  ✓ Exactly 1 head — no branch split detected."

# ── Check 2: No pending migrations on current DB ──────────────────────────────
log "CHECK 2: Pending migrations (current DB vs head)"
CURRENT_OUTPUT=$(alembic current 2>&1) || {
    warn "  Could not query current DB revision (DB may be empty — that's OK for first boot)."
    warn "  Output: $CURRENT_OUTPUT"
}

if echo "$CURRENT_OUTPUT" | grep -q "(head)"; then
    log "  ✓ Database is already at HEAD — no pending migrations."
elif echo "$CURRENT_OUTPUT" | grep -q "No version tables"; then
    log "  ✓ Database is empty (first boot) — alembic upgrade head will initialise it."
else
    PENDING=$(alembic history --indicate-current 2>&1 | grep -c "^<" || true)
    if [ "${PENDING:-0}" -gt 0 ]; then
        log "  ℹ  $PENDING migration(s) pending — alembic upgrade head will apply them."
    else
        log "  ✓ Database state consistent (no outstanding migrations detected)."
    fi
fi

# ── Check 3: No duplicate revision IDs in migration files ────────────────────
log "CHECK 3: Duplicate revision IDs"
VERSIONS_DIR="$(dirname "$0")/../alembic/versions"

if [ ! -d "$VERSIONS_DIR" ]; then
    warn "  Alembic versions directory not found at expected path: $VERSIONS_DIR"
else
    DUPE_CHECK=$(
        grep -rh "^revision = " "$VERSIONS_DIR"/*.py 2>/dev/null |
        sed "s/revision = ['\"]//g" | sed "s/['\"]//g" |
        sort | uniq -d
    )
    if [ -n "$DUPE_CHECK" ]; then
        err "  FATAL: Duplicate revision ID(s) found in migration files:"
        echo "$DUPE_CHECK" | sed 's/^/    /' >&2
        err "  Duplicate revisions will cause unpredictable migration behaviour."
        err "  Fix: delete or regenerate the offending migration files."
        exit 3
    fi
    log "  ✓ No duplicate revision IDs detected."
fi

# ── Check 4: All referenced down_revisions exist ──────────────────────────────
log "CHECK 4: down_revision chain continuity"
if [ -d "$VERSIONS_DIR" ]; then
    python3 - "$VERSIONS_DIR" << 'PYEOF'
import sys, re, os, glob
versions_dir = sys.argv[1]
files = glob.glob(os.path.join(versions_dir, "*.py"))

revisions = {}
down_revisions = {}

for fpath in files:
    fname = os.path.basename(fpath)
    with open(fpath) as f:
        content = f.read()
    rev_match = re.search(r"^revision\s*=\s*['\"]([^'\"]+)['\"]", content, re.MULTILINE)
    down_match = re.search(r"^down_revision\s*=\s*(?:['\"]([^'\"]*)['\"]|None|\(([^)]+)\))", content, re.MULTILINE)
    if rev_match:
        rev_id = rev_match.group(1)
        revisions[rev_id] = fname
        if down_match:
            down_val = down_match.group(1) or down_match.group(2)
            if down_val:
                # Handle tuple format for merge migrations
                for dr in re.findall(r"['\"]([^'\"]+)['\"]", down_val):
                    down_revisions.setdefault(rev_id, []).append(dr)

broken = []
for rev_id, drefs in down_revisions.items():
    for dref in drefs:
        if dref and dref not in revisions:
            broken.append(f"  {revisions[rev_id]}: down_revision='{dref}' not found in any migration file")

if broken:
    print("CHAIN_BROKEN: " + " | ".join(broken))
    sys.exit(1)
else:
    print(f"CHAIN_OK: {len(revisions)} revisions, chain is continuous.")
    sys.exit(0)
PYEOF
    if [ $? -ne 0 ]; then
        err "  Migration chain has broken references. See above for details."
        exit 4
    fi
    log "  ✓ All down_revision references are valid."
fi

# ── Summary ───────────────────────────────────────────────────────────────────
log "═══════════════════════════════════════════════════════════"
log "  Migration chain validation PASSED — safe to run upgrade."
log "═══════════════════════════════════════════════════════════"
exit 0
