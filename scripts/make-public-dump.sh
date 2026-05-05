#!/usr/bin/env bash
# scripts/make-public-dump.sh
#
# Produce a redistributable Canadian Political Data dump of the `public`
# schema only.
#
# By construction this artifact contains no user accounts, no payment
# data, no saved searches, no corrections, no reports, no login tokens,
# and no Stripe webhook payloads — those tables live in the `private`
# schema (see db/migrations/0042_private_schema.sql) and pg_dump
# --schema=public never sees them.
#
# Output location follows the same resolution chain as
# scripts/backup-database.sh: $PUBLIC_DUMP_DEST → $BACKUP_DEST/public-dumps
# → /media/bunker-admin/Internal/canadian-political-data-backups/public-dumps.
# This script does NOT write to the repo's working tree because the system
# disk is space-constrained; the dumps land on the dedicated backup volume
# alongside the daily ops snapshots.
#
# Like backup-database.sh, the actual pg_dump runs in a throwaway
# postgres:16 sidecar container attached to the compose network with the
# backup destination bind-mounted at /backup, so the dump bytes go
# directly to the external volume — they never traverse the host pipe
# or land in a tempfile on the system disk.
#
# Usage:
#   scripts/make-public-dump.sh                    # produce a dump
#   scripts/make-public-dump.sh --check            # dry run; list what would be included
#   scripts/make-public-dump.sh --dest <dir>       # override destination once
#
# Restore on a consumer machine:
#   createdb cpd
#   pg_restore --no-owner --no-privileges -d cpd -j 4 cpd-public-*.pgcustom

set -euo pipefail

SOVPRO_REPO="${SOVPRO_REPO:-/home/bunker-admin/sovpro}"

# Match backup-database.sh's env resolution: process env > $SOVPRO_REPO/.env > default.
read_env_var() {
    local key="$1" envfile="$SOVPRO_REPO/.env"
    [ -f "$envfile" ] || return 0
    grep -E "^${key}=" "$envfile" 2>/dev/null | tail -n1 | cut -d= -f2- || true
}

CHECK_ONLY=0
DEST_OVERRIDE=""
while [ $# -gt 0 ]; do
    case "$1" in
        --check) CHECK_ONLY=1; shift ;;
        --dest)  DEST_OVERRIDE="$2"; shift 2 ;;
        --help|-h)
            sed -n '2,30p' "$0" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        *)
            echo "error: unknown argument: $1" >&2
            echo "usage: $0 [--check] [--dest <dir>]" >&2
            exit 64
            ;;
    esac
done

# Resolve destination. Prefer an explicit PUBLIC_DUMP_DEST so the operator
# can park dumps in a different folder from the daily ops backups; fall
# back to ${BACKUP_DEST}/public-dumps if only BACKUP_DEST is set.
PUBLIC_DUMP_DEST="${PUBLIC_DUMP_DEST:-$(read_env_var PUBLIC_DUMP_DEST)}"
BACKUP_DEST_RESOLVED="${BACKUP_DEST:-$(read_env_var BACKUP_DEST)}"
BACKUP_DEST_RESOLVED="${BACKUP_DEST_RESOLVED:-/media/bunker-admin/Internal/canadian-political-data-backups}"
PUBLIC_DUMP_DEST="${PUBLIC_DUMP_DEST:-$BACKUP_DEST_RESOLVED/public-dumps}"
[ -n "$DEST_OVERRIDE" ] && PUBLIC_DUMP_DEST="$DEST_OVERRIDE"

CONTAINER="${SW_DB_CONTAINER:-sw-db}"
DB_USER="${SW_DB_USER:-sw}"
DB_NAME="${SW_DB_NAME:-sovereignwatch}"
COMPOSE_NETWORK="${SW_DB_NETWORK:-sovpro_sw}"

# Preflight: db container, network, .env (for password), destination drive.
if ! docker inspect "$CONTAINER" >/dev/null 2>&1; then
    echo "error: container '$CONTAINER' not running. Start with 'sovpro up'." >&2
    exit 1
fi
if ! docker network inspect "$COMPOSE_NETWORK" >/dev/null 2>&1; then
    echo "error: docker network '$COMPOSE_NETWORK' not found." >&2
    exit 1
fi
[ -f "$SOVPRO_REPO/.env" ] || { echo "error: .env not found at $SOVPRO_REPO/.env" >&2; exit 1; }
DB_PASSWORD="$(read_env_var DB_PASSWORD)"
[ -n "$DB_PASSWORD" ] || { echo "error: DB_PASSWORD missing in $SOVPRO_REPO/.env" >&2; exit 1; }

# --check is a metadata-only run; doesn't need the destination directory.
if [ "$CHECK_ONLY" -eq 1 ]; then
    # Cache the schema-only dump once instead of running pg_dump twice.
    # `head` on a pipe sends SIGPIPE upstream which `set -o pipefail`
    # treats as failure; subshell scopes the pipefail-disable narrowly.
    schema_dump_file="$(mktemp)"
    trap 'rm -f "$schema_dump_file"' EXIT
    docker exec "$CONTAINER" pg_dump \
        -U "$DB_USER" -d "$DB_NAME" \
        --schema=public --schema-only \
        --no-owner --no-privileges \
        --format=plain \
        > "$schema_dump_file"

    echo "[make-public-dump] dry run — first 40 CREATE statements that would be included"
    ( set +o pipefail; grep -E '^(CREATE TABLE|CREATE INDEX|CREATE SCHEMA)' "$schema_dump_file" | head -40 )
    echo "..."
    echo "[make-public-dump] private-table presence in --schema=public output (must be 0):"
    grep -c -E '\b(login_tokens|saved_searches|correction_submissions|credit_ledger|credit_purchases|stripe_webhook_events|rate_limit_increase_requests|report_jobs|report_bug_reports)\b' \
        "$schema_dump_file" \
        || true
    exit 0
fi

# Real run: validate destination is mounted, writable, and has headroom.
[ -d "$PUBLIC_DUMP_DEST" ] || mkdir -p "$PUBLIC_DUMP_DEST" || {
    echo "error: cannot create $PUBLIC_DUMP_DEST (is the external drive mounted?)" >&2
    exit 1
}
[ -w "$PUBLIC_DUMP_DEST" ] || { echo "error: $PUBLIC_DUMP_DEST not writable" >&2; exit 1; }

FSTYPE="$(findmnt -no FSTYPE -T "$PUBLIC_DUMP_DEST" 2>/dev/null || echo unknown)"
case "$FSTYPE" in
    vfat|msdos|exfat)
        echo "error: $PUBLIC_DUMP_DEST is on $FSTYPE — single-file 4 GB ceiling will kill the dump" >&2
        exit 1
        ;;
esac

# Headroom: refuse to start if <5 GB free (compressed public schema is well
# under 1 GB today, but custom-format compression overhead and the nightly
# ops dump sharing the volume warrant some slack).
AVAIL_KB="$(df -P -k "$PUBLIC_DUMP_DEST" | awk 'NR==2 {print $4}')"
if [ "${AVAIL_KB:-0}" -lt 5242880 ]; then
    AVAIL_GB="$((AVAIL_KB / 1024 / 1024))"
    echo "error: only ${AVAIL_GB} GB free on $PUBLIC_DUMP_DEST — need at least 5 GB" >&2
    exit 1
fi

ts="$(date -u +%Y%m%dT%H%M%SZ)"
sha="$(git -C "$SOVPRO_REPO" rev-parse --short HEAD 2>/dev/null || echo nogit)"
base="cpd-public-${ts}-${sha}"
dump_path_in_dest="$base.pgcustom"
manifest_path_in_dest="$base.manifest.tsv"
sha_path_in_dest="$base.sha256"

# Determine target uid/gid from the destination directory itself, so the
# sidecar (running as root) leaves files owned by the host operator.
DEST_UID="$(stat -c %u "$PUBLIC_DUMP_DEST")"
DEST_GID="$(stat -c %g "$PUBLIC_DUMP_DEST")"

echo "[make-public-dump] dest      = $PUBLIC_DUMP_DEST (fs=$FSTYPE)"
echo "[make-public-dump] artifact  = $dump_path_in_dest"
echo "[make-public-dump] dumping public schema via postgres:16 sidecar..."

DUMP_START="$(date -u +%s)"
docker run --rm \
    --name "sw-public-dump-$ts" \
    --network "$COMPOSE_NETWORK" \
    -v "$PUBLIC_DUMP_DEST:/backup" \
    -e PGPASSWORD="$DB_PASSWORD" \
    postgres:16 \
    pg_dump -h db -U "$DB_USER" -d "$DB_NAME" \
            --schema=public \
            --no-owner --no-privileges \
            --format=custom --compress=zstd:3 \
            -f "/backup/$dump_path_in_dest" \
    || { echo "error: pg_dump failed" >&2; rm -f "$PUBLIC_DUMP_DEST/$dump_path_in_dest"; exit 1; }
DUMP_END="$(date -u +%s)"
echo "[make-public-dump] pg_dump completed in $((DUMP_END - DUMP_START))s"

# Manifest — TSV of public.* row counts.
{
    printf "# Canadian Political Data — public dataset dump\n"
    printf "# generated: %s UTC\n" "$ts"
    printf "# git_sha: %s\n" "$sha"
    printf "# source_db: %s@%s/%s\n" "$DB_USER" "$CONTAINER" "$DB_NAME"
    printf "# table\tlive_rows\n"
    docker exec "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -At -F $'\t' -c "
        SELECT schemaname || '.' || relname, n_live_tup
          FROM pg_stat_user_tables
         WHERE schemaname = 'public'
         ORDER BY n_live_tup DESC;
    "
} > "$PUBLIC_DUMP_DEST/$manifest_path_in_dest"

# SHA256 of the artifact.
( cd "$PUBLIC_DUMP_DEST" && sha256sum "$dump_path_in_dest" > "$sha_path_in_dest" )

# Ownership fix-up for the sidecar-written file.
docker run --rm -v "$PUBLIC_DUMP_DEST:/backup" busybox \
    chown "${DEST_UID}:${DEST_GID}" "/backup/$dump_path_in_dest" \
    || echo "[make-public-dump] warning: chown sidecar failed; continuing"

# Final guardrail: refuse to publish a dump whose manifest contains any of
# the 10 known private-table names. Catches a future migration that put a
# user-data table back in `public`. Doesn't catch *novel* PII tables —
# those are caught at migration-write time by the rule in docs/gotchas.md.
if grep -E '\b(users|login_tokens|saved_searches|correction_submissions|credit_ledger|credit_purchases|stripe_webhook_events|rate_limit_increase_requests|report_jobs|report_bug_reports)\b' \
        "$PUBLIC_DUMP_DEST/$manifest_path_in_dest" \
        | grep -v '^#' | grep -q .; then
    echo "error: manifest contains a private-table name — refusing to release this dump" >&2
    echo "       inspect $PUBLIC_DUMP_DEST/$manifest_path_in_dest" >&2
    exit 2
fi

bytes="$(stat -c %s "$PUBLIC_DUMP_DEST/$dump_path_in_dest")"
human="$(numfmt --to=iec --suffix=B "$bytes" 2>/dev/null || echo "${bytes} bytes")"
echo "[make-public-dump] done. $human → $PUBLIC_DUMP_DEST/$dump_path_in_dest"
