---
title: Dataset download
description: Download a redistributable snapshot of the Canadian Political Data corpus.
---

# Dataset download

A redistributable snapshot of the Canadian Political Data corpus is
published every week. The snapshot covers the public legislative dataset
— politicians, speeches with embeddings, bills, votes, infrastructure
scans, and projections — and **by construction excludes** user accounts,
authentication tokens, saved searches, billing data, and reports. Those
tables live in a separate database schema that the dump command never
touches.

## Download

The canonical download URL is <https://canadianpoliticaldata.org/datasets/>
— an nginx autoindex listing of every weekly snapshot. Pick the most
recent `cpd-public-*.pgcustom` file.

Each weekly artifact ships with two sidecar files in the same directory:

- `cpd-public-<timestamp>-<git-sha>.manifest.tsv` — table-by-table row counts at dump time.
- `cpd-public-<timestamp>-<git-sha>.sha256` — integrity check.

## Format

The dump is a PostgreSQL **custom-format** archive (`pg_dump --format=custom`)
compressed with **zstd**. Format details:

- One file (not a directory) — easy to mirror, hash, and host.
- Compressible: a 199 GB on-disk database compresses to ~33 GB on the wire.
- Parallel-restore friendly: `pg_restore -j N` reads multiple table data
  segments concurrently.
- Postgres 16 native (zstd custom-format dumps require a 16+ client).

## Restore

You'll need PostgreSQL 16 with extensions:

- **pgvector** ≥ 0.5 (provides the `vector` type for the embedding column)
- **PostGIS** ≥ 3.4 (riding boundaries, infrastructure-scan geography)
- **unaccent** (search normalization)

Restore is a single command:

```bash
createdb cpd

# Verify integrity first
sha256sum -c cpd-public-<timestamp>-<git-sha>.sha256

# Restore — adjust -j to taste (4 is a sane default on consumer hardware)
pg_restore --no-owner --no-privileges -d cpd -j 4 \
    cpd-public-<timestamp>-<git-sha>.pgcustom
```

The restore process **rebuilds the HNSW vector index** on
`speech_chunks.embedding` from scratch. On a 4M-row 1024-dim corpus that
takes 30-60 minutes of CPU on the consumer's machine. The dump file
itself decompresses fast; the index build is the long pole.

## Refresh cadence

The snapshot is regenerated **every Sunday at 02:00 America/Edmonton**
by the production system's cron. The autoindex listing shows all
weekly snapshots — pick the most recent for the freshest data, or pin
to a specific timestamp if you need a frozen point-in-time copy and
want to cite the exact version.

## What's in the dump

The manifest TSV tells you live row counts at dump time. As of the
latest snapshot the corpus includes:

- **Politicians** — federal MPs and provincial / territorial members,
  with terms, committees, offices, and social handles.
- **Hansard** — speech rows + chunked / embedded `speech_chunks` for
  semantic search. Federal plus 9 provincial / territorial pipelines.
- **Bills** — federal + provincial, with sponsor links, events, and
  raw HTML text.
- **Votes** — federal (with full vote_positions per MP) and 8
  provincial pipelines (consensus-shape, no per-member positions).
- **Infrastructure scans** — hosting / DNS / TLS observations for
  legislative web properties (`websites`, `infrastructure_scans`).
- **Constituency boundaries** — temporal riding geometries.
- **Semantic projections** — UMAP-3D / UMAP-2D coords + HDBSCAN
  cluster labels backing the `/explore` mind-map view.

Tables explicitly **not** in the dump: `users`, `login_tokens`,
`saved_searches`, `correction_submissions`, `credit_ledger`,
`credit_purchases`, `stripe_webhook_events`, `rate_limit_increase_requests`,
`report_jobs`, `report_bug_reports`. These hold private operator and
end-user data and live in a separate database schema (`private`) that
`pg_dump --schema=public` does not touch.

## Licence

The exact licence terms will be locked in and published alongside the
download — most likely
[Creative Commons Attribution-NonCommercial 4.0 (CC BY-NC 4.0)](https://creativecommons.org/licenses/by-nc/4.0/),
which is widely understood internationally and works under Canadian
law.

In short: free for journalism, research, education, and civic-tech
projects, with attribution. Commercial reuse requires a separate
arrangement — [contact us](../about/contact.md).

Source attribution: the underlying Hansard transcripts, bills, and vote
records come from public legislative websites (parl.ca, ola.org,
assnat.qc.ca, leg.bc.ca, and per-jurisdiction equivalents). Every
`speeches` and `bills` row carries a `source_url` pointing back to the
upstream record.

## Alternative: build your own corpus

If you'd rather have **continuously fresh data** instead of weekly
snapshots, run the ingestion pipeline locally — see
[Local installation](local-install.md) and specifically the
[Bootstrapping the dataset](local-install.md#bootstrapping-the-dataset)
section. The scanner + embedding service do the same work the
production system does, on your hardware. Useful if you're tracking
ongoing legislative activity in real time, or if you need to scope
ingestion to specific jurisdictions and skip the rest.

## Bandwidth notes

The download is hosted from a single self-hosted node — not a CDN.
Per-IP rate limits are enabled to protect the upstream from a single
client (or a viral inbound link) saturating the connection: two
simultaneous downloads per IP, 50 MB/s each. That's plenty for one
operator pulling the snapshot, but means you shouldn't expect CDN-grade
parallelism. If the primary path is unreachable or saturated, see the
[Bootstrap your own copy](#alternative-build-your-own-corpus) section
below for the run-locally path that doesn't depend on this download
URL at all.
