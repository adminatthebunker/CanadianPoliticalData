-- Seed daily-ingest schedules for live jurisdictions.
--
-- Idempotent: re-running this script updates existing rows by name.
-- NS schedules pre-date this seed and are intentionally NOT touched —
-- they live on their own legacy cron offsets (12:00, 13:00, 13:30 UTC).
--
-- Cadence: staggered, one jurisdiction per UTC hour, with intra-hour
-- offsets so each chain runs bills → hansard → speaker resolvers in
-- order. Args are mostly empty {}: each ingest command auto-resolves
-- the current parliament/session from legislative_sessions (see
-- services/scanner/src/legislative/current_session.py).
--
-- Apply via:
--   docker exec -i sw-db psql -U sw -d sovereignwatch -v ON_ERROR_STOP=1 \
--     < scripts/seed-daily-ingest-schedules.sql
--
-- Slot map (UTC):
--   08:00 chunk + embed (02:00 Mountain, post-ingest, cross-jurisdictional)
--   11:00 federal  | 12:00 NS (existing) | 13:50 NS votes | 14:00 BC
--   15:00 AB       | 16:00 QC            | 17:00 MB       | 18:00 ON
--   19:00 NB       | 20:00 NL            | 21:00 NT bills + Hansard chain
--   21:15 NU bills (Hansard pending) | 22:00 SK MLA roster + Hansard chain
-- Per-province votes extraction at :50 of the Hansard hour (ON at :55 to
-- avoid collision with the ON presiding-speaker resolver).

BEGIN;

-- Helper: idempotent upsert pattern.
-- We key on `name` (no unique constraint exists today), so rely on the
-- INSERT…WHERE NOT EXISTS pattern + a follow-up UPDATE for re-runs.
-- This is wordier than ON CONFLICT but works without schema changes.

-- Strategy: DELETE-then-INSERT for the rows this seed owns. All rows
-- carry created_by='daily-ingest-rollout' to scope the delete.
DELETE FROM scanner_schedules WHERE created_by = 'daily-ingest-rollout';

-- ─── Federal (11:00 UTC) ────────────────────────────────────────────
INSERT INTO scanner_schedules (name, command, args, cron, enabled, created_by) VALUES
('Federal bills daily ingest',
 'ingest-federal-bills', '{}'::jsonb,
 '0 11 * * *', true, 'daily-ingest-rollout'),
('Federal Hansard daily ingest',
 'ingest-federal-hansard', '{}'::jsonb,
 '15 11 * * *', true, 'daily-ingest-rollout'),
('Federal votes extraction',
 'extract-federal-votes', '{}'::jsonb,
 '30 11 * * *', true, 'daily-ingest-rollout'),
('Federal bill events from LEGISinfo XML',
 'ingest-federal-bill-events', '{}'::jsonb,
 '45 11 * * *', true, 'daily-ingest-rollout');

-- ─── NS votes (13:50 UTC) ───────────────────────────────────────────
-- NS bills/hansard/resolver schedules pre-date this seed and live on legacy
-- 12:00 / 13:00 / 13:30 UTC slots that we intentionally don't touch. Adding
-- the votes extractor as a new sibling row here (created_by='daily-ingest-
-- rollout') puts it in the rollup-managed group while leaving the legacy
-- rows untouched. :50 13 sits right after the legacy 13:30 NS Hansard.
INSERT INTO scanner_schedules (name, command, args, cron, enabled, created_by) VALUES
('NS votes extraction',
 'extract-ns-votes', '{}'::jsonb,
 '50 13 * * *', true, 'daily-ingest-rollout');

-- ─── BC (14:00 UTC) ─────────────────────────────────────────────────
INSERT INTO scanner_schedules (name, command, args, cron, enabled, created_by) VALUES
('BC bills daily ingest',
 'ingest-bc-bills', '{}'::jsonb,
 '0 14 * * *', true, 'daily-ingest-rollout'),
('BC Hansard daily ingest',
 'ingest-bc-hansard', '{}'::jsonb,
 '15 14 * * *', true, 'daily-ingest-rollout'),
('BC speaker resolver',
 'resolve-bc-speakers', '{}'::jsonb,
 '30 14 * * *', true, 'daily-ingest-rollout'),
('BC presiding speaker resolver',
 'resolve-presiding-speakers', '{"province": "BC"}'::jsonb,
 '45 14 * * *', true, 'daily-ingest-rollout'),
('BC votes extraction',
 'extract-bc-votes', '{}'::jsonb,
 '50 14 * * *', true, 'daily-ingest-rollout');

-- ─── AB (15:00 UTC) ─────────────────────────────────────────────────
INSERT INTO scanner_schedules (name, command, args, cron, enabled, created_by) VALUES
('AB bills daily ingest',
 'ingest-ab-bills', '{}'::jsonb,
 '0 15 * * *', true, 'daily-ingest-rollout'),
('AB Hansard daily ingest',
 'ingest-ab-hansard', '{}'::jsonb,
 '15 15 * * *', true, 'daily-ingest-rollout'),
('AB speaker resolver',
 'resolve-ab-speakers', '{}'::jsonb,
 '30 15 * * *', true, 'daily-ingest-rollout'),
('AB presiding speaker resolver',
 'resolve-presiding-speakers', '{"province": "AB"}'::jsonb,
 '45 15 * * *', true, 'daily-ingest-rollout'),
('AB votes extraction',
 'extract-ab-votes', '{}'::jsonb,
 '50 15 * * *', true, 'daily-ingest-rollout');

-- ─── QC (16:00 UTC) ─────────────────────────────────────────────────
INSERT INTO scanner_schedules (name, command, args, cron, enabled, created_by) VALUES
('QC bills CSV daily ingest',
 'ingest-qc-bills', '{}'::jsonb,
 '0 16 * * *', true, 'daily-ingest-rollout'),
('QC bills RSS refresh',
 'ingest-qc-bills-rss', '{}'::jsonb,
 '5 16 * * *', true, 'daily-ingest-rollout'),
('QC Hansard daily ingest',
 'ingest-qc-hansard', '{}'::jsonb,
 '15 16 * * *', true, 'daily-ingest-rollout'),
('QC speaker resolver',
 'resolve-qc-speakers', '{}'::jsonb,
 '30 16 * * *', true, 'daily-ingest-rollout'),
('QC presiding speaker resolver',
 'resolve-presiding-speakers', '{"province": "QC"}'::jsonb,
 '45 16 * * *', true, 'daily-ingest-rollout'),
-- QC introduced_date fetcher: rolls up the <h3>Introduction</h3> sitting
-- date from each bill detail page onto bills.introduced_date. Steady-state
-- runs touch only newly-discovered undated bills, so this is cheap.
('QC bill introduced-dates fetcher',
 'fetch-qc-bill-introduced-dates', '{}'::jsonb,
 '35 16 * * *', true, 'daily-ingest-rollout'),
('QC votes extraction',
 'extract-qc-votes', '{}'::jsonb,
 '50 16 * * *', true, 'daily-ingest-rollout');

-- ─── MB (17:00 UTC) ─────────────────────────────────────────────────
-- MB has the longest chain — bills (HTML index), then PDF download,
-- then PDF parse, then Hansard, then 3 resolvers (sponsor + 2 speaker).
INSERT INTO scanner_schedules (name, command, args, cron, enabled, created_by) VALUES
('MB bills daily ingest',
 'ingest-mb-bills', '{}'::jsonb,
 '0 17 * * *', true, 'daily-ingest-rollout'),
('MB billstatus PDF download',
 'fetch-mb-billstatus-pdf', '{}'::jsonb,
 '5 17 * * *', true, 'daily-ingest-rollout'),
('MB bill events from PDF',
 'parse-mb-bill-events', '{}'::jsonb,
 '10 17 * * *', true, 'daily-ingest-rollout'),
('MB Hansard daily ingest',
 'ingest-mb-hansard', '{}'::jsonb,
 '15 17 * * *', true, 'daily-ingest-rollout'),
('MB bill sponsor resolver',
 'resolve-mb-bill-sponsors', '{}'::jsonb,
 '25 17 * * *', true, 'daily-ingest-rollout'),
('MB speaker resolver',
 'resolve-mb-speakers', '{}'::jsonb,
 '30 17 * * *', true, 'daily-ingest-rollout'),
('MB speaker resolver (date-windowed)',
 'resolve-mb-speakers-dated', '{}'::jsonb,
 '35 17 * * *', true, 'daily-ingest-rollout'),
('MB presiding speaker resolver',
 'resolve-presiding-speakers', '{"province": "MB"}'::jsonb,
 '45 17 * * *', true, 'daily-ingest-rollout'),
('MB votes extraction',
 'extract-mb-votes', '{}'::jsonb,
 '50 17 * * *', true, 'daily-ingest-rollout');

-- ─── ON (18:00 UTC) ─────────────────────────────────────────────────
-- ON bills: 3-step chain (discover → fetch HTML pages → parse them),
-- packed into the first 10 minutes of the hour to leave room for the
-- Hansard chain. Hansard via ola.org JSON node landed 2026-04-24.
INSERT INTO scanner_schedules (name, command, args, cron, enabled, created_by) VALUES
('ON bills discovery',
 'ingest-on-bills', '{}'::jsonb,
 '0 18 * * *', true, 'daily-ingest-rollout'),
('ON bill pages fetch',
 'fetch-on-bill-pages', '{}'::jsonb,
 '5 18 * * *', true, 'daily-ingest-rollout'),
('ON bill pages parse',
 'parse-on-bill-pages', '{}'::jsonb,
 '10 18 * * *', true, 'daily-ingest-rollout'),
('ON Hansard daily ingest',
 'ingest-on-hansard', '{}'::jsonb,
 '20 18 * * *', true, 'daily-ingest-rollout'),
('ON speaker resolver',
 'resolve-on-speakers', '{}'::jsonb,
 '35 18 * * *', true, 'daily-ingest-rollout'),
('ON presiding speaker resolver',
 'resolve-presiding-speakers', '{"province": "ON"}'::jsonb,
 '50 18 * * *', true, 'daily-ingest-rollout'),
-- :50 18 collides with the presiding-speaker resolver above; bump votes to :55.
('ON votes extraction',
 'extract-on-votes', '{}'::jsonb,
 '55 18 * * *', true, 'daily-ingest-rollout');

-- ─── NB (19:00 UTC) ─────────────────────────────────────────────────
INSERT INTO scanner_schedules (name, command, args, cron, enabled, created_by) VALUES
('NB bills daily ingest',
 'ingest-nb-bills', '{}'::jsonb,
 '0 19 * * *', true, 'daily-ingest-rollout'),
('NB Hansard daily ingest',
 'ingest-nb-hansard', '{}'::jsonb,
 '15 19 * * *', true, 'daily-ingest-rollout'),
('NB speaker resolver',
 'resolve-nb-speakers', '{}'::jsonb,
 '30 19 * * *', true, 'daily-ingest-rollout'),
('NB presiding speaker resolver',
 'resolve-presiding-speakers', '{"province": "NB"}'::jsonb,
 '45 19 * * *', true, 'daily-ingest-rollout'),
('NB votes extraction',
 'extract-nb-votes', '{}'::jsonb,
 '50 19 * * *', true, 'daily-ingest-rollout');

-- ─── NL (20:00 UTC) ─────────────────────────────────────────────────
INSERT INTO scanner_schedules (name, command, args, cron, enabled, created_by) VALUES
('NL bills daily ingest',
 'ingest-nl-bills', '{}'::jsonb,
 '0 20 * * *', true, 'daily-ingest-rollout'),
('NL Hansard daily ingest',
 'ingest-nl-hansard', '{}'::jsonb,
 '15 20 * * *', true, 'daily-ingest-rollout'),
('NL speaker resolver',
 'resolve-nl-speakers', '{}'::jsonb,
 '30 20 * * *', true, 'daily-ingest-rollout'),
('NL presiding speaker resolver',
 'resolve-presiding-speakers', '{"province": "NL"}'::jsonb,
 '45 20 * * *', true, 'daily-ingest-rollout'),
('NL votes extraction',
 'extract-nl-votes', '{}'::jsonb,
 '50 20 * * *', true, 'daily-ingest-rollout');

-- ─── NT + NU (21:00 UTC) ────────────────────────────────────────────
-- Consensus-government legislatures. NT Hansard live since 2026-04-29
-- (ntlegislativeassembly.ca slug-FK pattern). NU Hansard still gated on
-- research-handoff (multilingual EN+Inuktitut+Inuinnaqtun+FR). NT bills
-- and Hansard chain serially; NT presiding-officer resolver follows.
INSERT INTO scanner_schedules (name, command, args, cron, enabled, created_by) VALUES
('NT bills daily ingest',
 'ingest-nt-bills', '{}'::jsonb,
 '0 21 * * *', true, 'daily-ingest-rollout'),
('NT Hansard daily ingest',
 'ingest-nt-hansard', '{"limit_sittings": 5}'::jsonb,
 '30 21 * * *', true, 'daily-ingest-rollout'),
('NT presiding speaker resolver',
 'resolve-presiding-speakers', '{"province": "NT"}'::jsonb,
 '45 21 * * *', true, 'daily-ingest-rollout'),
('NT votes extraction',
 'extract-nt-votes', '{}'::jsonb,
 '50 21 * * *', true, 'daily-ingest-rollout'),
('NU bills daily ingest',
 'ingest-nu-bills', '{}'::jsonb,
 '15 21 * * *', true, 'daily-ingest-rollout');

-- ─── SK (22:00 UTC) ─────────────────────────────────────────────────
-- SK has no per-MLA stable identifier; the MLA roster ingester
-- synthesises slugs from the Hansard speaker index (one HTTP call per
-- run, idempotent — daily refresh is cheap and catches cabinet
-- shuffles). SK bills are PDF-only (deferred); no ingest-sk-bills slot
-- yet. Hansard discovery walks the paginated archive at :05 and ingests
-- new sittings at :15.
INSERT INTO scanner_schedules (name, command, args, cron, enabled, created_by) VALUES
('SK MLA roster refresh',
 'ingest-sk-mlas', '{"parliaments": "30"}'::jsonb,
 '0 22 * * *', true, 'daily-ingest-rollout'),
('SK Hansard daily ingest',
 'ingest-sk-hansard', '{"limit_sittings": 5}'::jsonb,
 '15 22 * * *', true, 'daily-ingest-rollout');

-- ─── Post-ingest semantic layer (08:00 UTC = 02:00 MDT) ─────────────
-- Cross-jurisdictional. Last per-jurisdiction Hansard ingest (NT/NU at
-- 21:15 UTC) finishes by ~22 UTC, so 08:00 UTC the next day gives a
-- comfortable buffer and lands well before the next morning's federal
-- ingest at 11:00 UTC. Single command — chunk_pending → embed_pending
-- in one process — so ordering is atomic regardless of worker
-- concurrency. Both stages are idempotent: chunk only touches speeches
-- with no chunks, embed only touches chunks with NULL embedding.
-- 02:00 Mountain (MDT/UTC-6 in summer; MST/UTC-7 in winter) means the
-- run shifts to 03:00 local in winter, but server-side cron stays
-- 08:00 UTC year-round — we don't track DST transitions in cron.
INSERT INTO scanner_schedules (name, command, args, cron, enabled, created_by) VALUES
('Chunk + embed speeches (daily)',
 'chunk-and-embed-speeches', '{}'::jsonb,
 '0 8 * * *', true, 'daily-ingest-rollout'),
-- Pure-SQL backfill of bills.introduced_date from bill_events first_reading
-- rows. Cheap (single CTE pass), cross-jurisdictional, idempotent. Runs at
-- 07:55 UTC just before the chunk+embed step, after the previous day's
-- bills chains have all completed.
('Backfill bill introduced_date from events (daily)',
 'relink-bill-introduced-dates', '{}'::jsonb,
 '55 7 * * *', true, 'daily-ingest-rollout');

-- next_run_at is computed by the worker the first time it polls; leave
-- it NULL here so croniter advances it correctly on the worker tick.

COMMIT;

-- Show what we just wrote.
SELECT name, cron, enabled, command FROM scanner_schedules
 WHERE created_by = 'daily-ingest-rollout'
 ORDER BY cron, name;
