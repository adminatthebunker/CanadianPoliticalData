---
title: Bulk export
description: How to download the full Canadian Political Data public dataset as a Postgres custom-format archive via the read:bulk-scoped API.
---

# Bulk export

The full public dataset (politicians, bills, speeches, votes,
projections — everything in the `public` PostgreSQL schema) is
available as weekly dump artifacts. Two ways to get them:

- **Anonymous** at [`/datasets/`](https://canadianpoliticaldata.org/datasets/) —
  nginx autoindex, generous per-IP rate limits. Best for one-off
  research downloads, journalists, students.
- **Authenticated** via the `read:bulk`-scoped public API at
  `/api/public/v1/exports/dumps` — same files, but auth-gated and
  per-key metered. Best for automated workflows that benefit from
  the rest of the API surface (key rotation, usage telemetry,
  programmatic listing).

Both surfaces serve the **identical files** produced by the weekly
`scripts/make-public-dump.sh` job. There's no difference in content
or freshness — pick whichever auth posture matches your workflow.

## What's in a dump

Each dump set is three files sharing a `cpd-public-<timestamp>-<git-sha>`
prefix:

| Suffix | Format | Purpose |
|---|---|---|
| `.pgcustom` | Postgres custom-format archive (`pg_dump -Fc`) | The data. Restorable via `pg_restore`. Compressed. Multi-GB. |
| `.sha256` | Plain text | SHA-256 checksum of the `.pgcustom`. Verify integrity. |
| `.manifest.tsv` | Tab-separated text | Per-table row counts + sizes at dump time. Quick sanity check before committing to the multi-GB download. |

Privacy boundary is enforced at dump time: `pg_dump --schema=public`
mechanically excludes everything in the `private` schema (users,
sessions, payments, saved searches, API keys). See
[CLAUDE.md convention #8](https://github.com/adminatthebunker/CanadianPoliticalData/blob/main/CLAUDE.md)
for the full discipline.

## Get a `read:bulk` key

1. Sign in at [`/account/api-keys`](https://canadianpoliticaldata.org/account/api-keys).
2. Click "+ New API key."
3. Give it a name (e.g., `dataset-mirror`).
4. **Tick the `read:bulk` checkbox** in the Scopes fieldset. This is
   what unlocks `/api/public/v1/exports/*`.
5. Click "Create key" — copy the token immediately.

Existing keys without `read:bulk` need to be **rotated** with the
checkbox ticked at create time, OR you can create a new key
specifically for bulk downloads while keeping the old one for the
rest of the API surface. Per-key scope changes-after-creation aren't
supported in v1 — the design assumes one scope set per key.

## List available dumps

```bash
curl -H 'Authorization: Bearer cpd_live_…' \
     https://canadianpoliticaldata.org/api/public/v1/exports/dumps \
  | jq '.dumps[:3]'
```

```json
[
  {
    "filename": "cpd-public-20260510T080001Z-920f851.pgcustom",
    "size_bytes": 3214567890,
    "modified_at": "2026-05-10T08:35:54.744Z",
    "kind": "pgcustom"
  },
  {
    "filename": "cpd-public-20260510T080001Z-920f851.sha256",
    "size_bytes": 111,
    "modified_at": "2026-05-10T08:35:54.744Z",
    "kind": "sha256"
  },
  {
    "filename": "cpd-public-20260510T080001Z-920f851.manifest.tsv",
    "size_bytes": 997,
    "modified_at": "2026-05-10T08:35:54.744Z",
    "kind": "manifest"
  }
]
```

Newest first. Same naming convention nginx exposes at
[`/datasets/`](https://canadianpoliticaldata.org/datasets/).

## Download a dump

```bash
KEY='cpd_live_…'
HOST='https://canadianpoliticaldata.org'
PREFIX='cpd-public-20260510T080001Z-920f851'

# 1. Inspect the manifest first so you know what you're about to pull.
curl -H "Authorization: Bearer $KEY" \
     "$HOST/api/public/v1/exports/dumps/$PREFIX.manifest.tsv"

# 2. Download the integrity checksum.
curl -H "Authorization: Bearer $KEY" -o "$PREFIX.sha256" \
     "$HOST/api/public/v1/exports/dumps/$PREFIX.sha256"

# 3. Download the data archive (multi-GB; use --output and let it stream).
curl -H "Authorization: Bearer $KEY" -o "$PREFIX.pgcustom" \
     "$HOST/api/public/v1/exports/dumps/$PREFIX.pgcustom"

# 4. Verify integrity.
sha256sum --check "$PREFIX.sha256"
```

## Restore into your own Postgres

```bash
# Create the target database.
createdb cpd_public

# Restore. -j 4 parallelizes; -O skips the original ownership; -x
# skips ACLs (you'll grant your own).
pg_restore -d cpd_public -j 4 -O -x "$PREFIX.pgcustom"
```

Tables include `politicians`, `bills`, `bill_events`, `bill_sponsors`,
`speeches`, `speech_chunks`, `speech_references`, `votes`,
`vote_positions`, `legislative_sessions`, `jurisdiction_sources`,
`websites`, `infrastructure_scans`, `constituency_boundaries`, and
the materialized views `map_politicians` + `map_organizations`. The
`speech_chunks.embedding` vector column comes through too if you've
got `pgvector` installed in the target.

## Cadence + freshness

The dump cron runs **weekly on Sunday at 02:00 local** via
`scripts/make-public-dump.sh`. The `<timestamp>` in the filename is
when the dump started; the `<git-sha>` is the codebase commit at
dump time (so you can correlate dataset state with code state).

Dumps are retained indefinitely on the canonical artifact directory;
the `/api/public/v1/exports/dumps` listing returns whatever is
currently on disk. If you want a specific historical dump that's
been pruned, file an issue — re-running `make-public-dump.sh` is
cheap, the artifact directory just isn't backfilled by default.

## Per-jurisdiction-month slicing (deferred)

The original v1.1 spec called for per-jurisdiction-month Parquet
slices alongside the full dumps — researchers wanting "Ontario
Hansard for 2025-Q4 only" without downloading the multi-GB full
archive. That layer isn't built yet (it's a separate scanner
snapshot pipeline, ~one cycle of work). When it lands, it'll mount
under `/api/public/v1/exports/slices/{table}/{jurisdiction}/{year-month}.parquet`
with the same `read:bulk` scope gate.

If you have a specific research workflow that needs a slice, file
an issue describing the use case — we'll prioritize accordingly.
