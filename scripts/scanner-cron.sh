#!/bin/sh
# ═══════════════════════════════════════════════════════════════════════════
# Scanner cron loop — run inside the scanner-cron container.
# Schedule:
#   - Quick pass every 6 hours (stale > 6h)
#   - Full sweep once a day at 06:00 UTC (stale > 0)
#   - (REMOVED 2026-08-27) Weekly Open North re-ingest, Sunday 02:00 UTC.
#     See the block below for why it must not come back.
#   - Weekly enrichment + socials normalization Sunday 04:00 UTC
#   - Weekly socials liveness verification Monday 03:00 UTC
#
# NOTE: `backfill-terms` is a one-time manual operation (seeds the
# politician_terms table from current holders). It is intentionally NOT
# scheduled here — run it by hand once after the schema migration lands:
#     docker compose run --rm scanner python -m src backfill-terms
# ═══════════════════════════════════════════════════════════════════════════

set -eu

log() { printf '[scanner-cron %s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }

# First boot: seed orgs (idempotent) and ingest reps if DB looks empty.
bootstrap() {
    log "Bootstrapping — seed-orgs"
    python -m src seed-orgs || log "FAILED: seed-orgs failed (will retry)"

    POLITICIAN_COUNT=$(
        python -c 'import asyncio,asyncpg,os; \
async def n():\n    c=await asyncpg.connect(os.environ["DATABASE_URL"]);\n    r=await c.fetchval("SELECT COUNT(*) FROM politicians");\n    await c.close(); print(r)\nasyncio.run(n())' 2>/dev/null || echo 0
    )
    if [ "${POLITICIAN_COUNT:-0}" -lt 10 ]; then
        log "No politicians yet — ingesting MPs, MLAs, councils"
        python -m src ingest-mps || log "FAILED: ingest-mps failed"
        python -m src ingest-mlas || log "FAILED: ingest-mlas failed"
        python -m src ingest-councils || log "FAILED: ingest-councils failed"
    fi
}

bootstrap

LAST_FULL=0
LAST_WEEKLY=0
LAST_WEEKLY_ENRICH=0
LAST_WEEKLY_VERIFY=0

while true; do
    NOW=$(date -u +%s)
    DOW=$(date -u +%u)   # 1=Mon .. 7=Sun
    HOUR=$(date -u +%H)

    # ⛔ THE WEEKLY OPEN NORTH RE-INGEST WAS REMOVED 2026-08-27. DO NOT RESTORE.
    #
    # It fired here every Sunday 02:00 UTC. On 2026-08-23 it re-created 1,926
    # mirror boundary rows and reverted twelve applied cutover migrations in one
    # pass — every jurisdiction left with two live generations, 69 sitting
    # members detached, and a downtown Toronto point returning 7 boundaries
    # instead of 4.
    #
    # ★ The Python guard added on 2026-08-20 did not stop it, and could not:
    # this container had NO `./services/scanner/src:/app/src` bind mount — alone
    # among the six scanner-family services — so it ran source baked into an
    # image built 2026-06-02. `restart: unless-stopped` kept that image alive
    # across every rebuild of everything else. A guard in the working tree is
    # not a guard on a container that never reads the working tree.
    #
    # ⚠ It also never wrote a `scanner_jobs` row and never read
    # `scanner_schedules`, so migration 0087's disabling of the 12 Open North
    # schedules had no effect on it and the run left no audit trail. That is why
    # five days passed before anyone noticed.
    #
    # The source mount has since been added, so this file now runs current code
    # and a resurrection is refused at the database by `trg_block_mirror_boundary`.
    # Roster ingestion for a jurisdiction with no replacement belongs in
    # `scanner_schedules`, where a failure surfaces as a FAILED job.

    # Weekly enrichment + socials normalization: Sunday 04:00 UTC
    # Runs 2h after the Sun 02:00 ingest so fresh social_urls JSONB is
    # available to normalize, and personal_url enrichment sees fresh rosters.
    if [ "$DOW" = "7" ] && [ "$HOUR" = "04" ] && [ $((NOW - LAST_WEEKLY_ENRICH)) -gt 86400 ]; then
        log "weekly (Sun 04:00): normalize-socials + enrich-legislatures + enrich-mps"
        python -m src normalize-socials || log "FAILED: normalize-socials failed"
        python -m src enrich-legislatures || log "FAILED: enrich-legislatures failed"
        python -m src enrich-mps || log "FAILED: enrich-mps failed"
        LAST_WEEKLY_ENRICH=$NOW
    fi

    # Weekly socials liveness verification: Monday 03:00 UTC
    # Verifies up to 5000 socials that haven't been checked in the last week.
    if [ "$DOW" = "1" ] && [ "$HOUR" = "03" ] && [ $((NOW - LAST_WEEKLY_VERIFY)) -gt 86400 ]; then
        log "weekly (Mon 03:00): verify-socials (limit=5000, stale-hours=168)"
        python -m src verify-socials --limit 5000 --stale-hours 168 \
            || log "FAILED: verify-socials failed"
        LAST_WEEKLY_VERIFY=$NOW
    fi

    # Daily: 06:00 UTC full sweep
    if [ "$HOUR" = "06" ] && [ $((NOW - LAST_FULL)) -gt 43200 ]; then
        log "daily: full scan (stale-hours=0)"
        python -m src scan --stale-hours 0 || log "FAILED: full scan failed"
        python -m src refresh-views || true
        LAST_FULL=$NOW
    else
        # Quick pass every 6h for sites not scanned in the last 6h
        log "quick scan (stale-hours=6)"
        python -m src scan --stale-hours 6 || log "FAILED: quick scan failed"
        python -m src refresh-views || true
    fi

    # Sleep 1h between loops
    sleep 3600
done
