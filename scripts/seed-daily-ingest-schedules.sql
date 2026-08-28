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
--   21:15 NU bills (Hansard pending) | 21:45 SK bills | 22:00 SK MLA roster + Hansard chain
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
-- Sub-slots: :00 bills | :15 Hansard | :20 committees | :30 votes | :45 bill events
INSERT INTO scanner_schedules (name, command, args, cron, enabled, created_by) VALUES
('Federal bills daily ingest',
 'ingest-federal-bills', '{}'::jsonb,
 '0 11 * * *', true, 'daily-ingest-rollout'),
('Federal Hansard daily ingest',
 'ingest-federal-hansard', '{}'::jsonb,
 '15 11 * * *', true, 'daily-ingest-rollout'),
('Federal committee evidence daily ingest',
 'ingest-federal-committees', '{}'::jsonb,
 '20 11 * * *', true, 'daily-ingest-rollout'),
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
-- NS presiding-officer resolver (Premier role-only Pass-3, shipped
-- 2026-05-22) slots at :45 13 — right before the votes extractor at
-- :50 13 and before the BC chain starts at :00 14.
INSERT INTO scanner_schedules (name, command, args, cron, enabled, created_by) VALUES
('NS role-only presiding/cabinet resolver',
 'resolve-role-only-presiding-officers', '{"province": "NS"}'::jsonb,
 '45 13 * * *', true, 'daily-ingest-rollout'),
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
('BC committee transcripts daily ingest',
 'ingest-bc-committees', '{}'::jsonb,
 '25 14 * * *', true, 'daily-ingest-rollout'),
-- Weekly dead-canary: surface stale BC committee seeds before they become
-- a silent ingest gap. BC has no auto-discovery API; if the operator
-- forgets to append URLs to scripts/seeds/bc-committee-meetings.json,
-- daily-cron no-ops over the same N URLs forever. Monday 13:30 UTC
-- (early enough that any email lands before North-American workday).
('BC committees freshness weekly check',
 'check-bc-committees-freshness', '{}'::jsonb,
 '30 13 * * 1', true, 'daily-ingest-rollout'),
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
('AB committee transcripts daily ingest',
 'ingest-ab-committees', '{}'::jsonb,
 '25 15 * * *', true, 'daily-ingest-rollout'),
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
-- Roster refresh runs at :50 of the prior hour (15:50 UTC) so
-- detect_retirements() lands before the daily bills/Hansard chain and
-- before v_websites_missing / v_socials_missing are next read by the
-- weekly agent enrichers. opennorth.ingest_quebec_mnas wraps
-- _ingest_set() which gates retirement detection on len(reps) < limit.
INSERT INTO scanner_schedules (name, command, args, cron, enabled, created_by) VALUES
('QC MNA roster refresh',
 'ingest-quebec-mnas', '{}'::jsonb,
 '50 15 * * *', true, 'daily-ingest-rollout'),
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
('QC date-windowed speaker resolver',
 'resolve-qc-speakers-dated', '{}'::jsonb,
 '32 16 * * *', true, 'daily-ingest-rollout'),
('QC doc-continuity speaker resolver',
 'resolve-qc-speakers-doc-continuity', '{}'::jsonb,
 '33 16 * * *', true, 'daily-ingest-rollout'),
-- Former MNAs roster refresh runs weekly (Sundays 04:20 UTC) — idempotent
-- alphabet-walk of /fr/membres/notices/index*.html. Latent gap closed
-- 2026-05-21: ingester shipped 2026-04-27 but never scheduled, and the
-- httpx client was missing the verify=False that other QC ingesters use
-- to work around assnat.qc.ca's cert chain. Known coverage gap: the
-- 16-letter alphabet listing doesn't include recent retirees (post-~2015);
-- those need a separate URL family (deferred to a future cycle).
('QC former MNAs roster refresh',
 'ingest-qc-former-mnas', '{}'::jsonb,
 '20 4 * * 0', true, 'daily-ingest-rollout'),
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
-- Roster refresh runs at :50 of the prior hour (16:50 UTC) so
-- detect_retirements() lands before the chain.
INSERT INTO scanner_schedules (name, command, args, cron, enabled, created_by) VALUES
('MB MLA roster refresh',
 'ingest-manitoba-mlas', '{}'::jsonb,
 '50 16 * * *', true, 'daily-ingest-rollout'),
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
-- Flag-less: full current-parliament re-list (8 listings + ~140 nodes,
-- ~3 min) — self-healing per the no-fixed-window rule.
('ON committee transcripts daily ingest',
 'ingest-on-committees', '{}'::jsonb,
 '25 18 * * *', true, 'daily-ingest-rollout'),
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
 'ingest-nt-hansard', '{"limit_sittings": 25}'::jsonb,
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

-- ─── SK (21:45–22:30 UTC) ───────────────────────────────────────────
-- SK has no per-MLA stable identifier; the MLA roster ingester
-- synthesises slugs from the Hansard speaker index (one HTTP call per
-- run, idempotent — daily refresh is cheap and catches cabinet
-- shuffles). SK bills come from progress-of-bills.pdf (single
-- session-scoped PDF, parsed via pdftotext -layout). Hansard discovery
-- walks the paginated archive at :15 and ingests new sittings.
-- Chain order: bills → mlas → hansard → presiding-resolver.
INSERT INTO scanner_schedules (name, command, args, cron, enabled, created_by) VALUES
('SK bills daily ingest',
 'ingest-sk-bills', '{}'::jsonb,
 '45 21 * * *', true, 'daily-ingest-rollout'),
('SK MLA roster refresh',
 'ingest-sk-mlas', '{"parliaments": "30"}'::jsonb,
 '0 22 * * *', true, 'daily-ingest-rollout'),
('SK Hansard daily ingest',
 'ingest-sk-hansard', '{"limit_sittings": 25}'::jsonb,
 '15 22 * * *', true, 'daily-ingest-rollout'),
-- Flag-less: full current-legislature re-list (~90 meetings, ~2 min) —
-- self-healing per the no-fixed-window rule; late-published transcripts
-- can never fall outside a window.
('SK committee Hansard daily ingest',
 'ingest-sk-committees', '{}'::jsonb,
 '20 22 * * *', true, 'daily-ingest-rollout'),
('SK presiding speaker resolver',
 'resolve-presiding-speakers', '{"province": "SK"}'::jsonb,
 '30 22 * * *', true, 'daily-ingest-rollout');

-- ─── Weekly agent enrichment ──────────────────────────────────────
-- The previously-scheduled Anthropic-API-backed agents
-- (agent-missing-socials / agent-missing-websites) were removed from
-- this seed when their scheduled runs were retired:
--
--   * socials enrichment is now handled by the headless Claude Code
--     cron at scripts/scheduled-tasks/run-socials-weekly.sh
--     (daily 09:07 local, subscription-billed, source='claude-code-agent').
--   * websites enrichment is now handled by the headless Claude Code
--     cron at scripts/scheduled-tasks/run-websites-weekly.sh
--     (weekly Monday 09:17 local, subscription-billed,
--     source='claude-code-agent-websites').
--
-- The Click commands (agent-missing-socials / agent-missing-websites)
-- and admin-panel whitelist entries are intentionally retained so an
-- operator can still trigger the API-backed agents manually from
-- /admin when a one-off API-billed run is wanted.

-- ─── Post-ingest cross-jurisdictional resolvers (23:30 UTC) ────────
-- Runs after every provincial chain; idempotent UPDATE-only resolver
-- that backfills politician_id on speeches whose chamber-specific
-- parser left them unattributed but whose speaker_name_raw carries an
-- inline parens-name (e.g. "The Deputy Speaker (Mr. Bas Balkissoon)").
-- Tier-2 attribution Pass 1.
INSERT INTO scanner_schedules (name, command, args, cron, enabled, created_by) VALUES
('Inline-name presiding-officer resolver',
 'resolve-inline-presiding-officers', '{}'::jsonb,
 '30 23 * * *', true, 'daily-ingest-rollout');

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
 '55 7 * * *', true, 'daily-ingest-rollout'),

-- ─── NU Hansard (21:15 UTC) ─────────────────────────────────────────
-- Drupal-9 PDF source at assembly.nu.ca/hansard. ~59 PDFs back to
-- 2021-02-24. Empty args = full listing re-scan (idempotent, cached);
-- NU publishes infrequently and with long lag, so a fixed since-window
-- would skip late-published sittings forever (see 2026-08-02 incident:
-- 2 years of transcripts silently missed under since_days=14).
('NU Hansard daily ingest',
 'ingest-nu-hansard', '{}'::jsonb,
 '15 21 * * *', true, 'daily-ingest-rollout'),

-- ─── SK votes (22:50 UTC) ───────────────────────────────────────────
-- Session-aggregated Journal PDFs at legassembly.sk.ca with structured
-- YEAS/POUR + NAYS/CONTRE grids. Default current_only=true processes
-- just the highest (legislature, session) Journal each day. Slot is
-- after ingest-sk-mlas (22:00) + ingest-sk-hansard (22:15) so the
-- speaker roster is fresh before votes attempt FK resolution.
('SK votes daily extract',
 'extract-sk-votes', '{"current_only": true}'::jsonb,
 '50 22 * * *', true, 'daily-ingest-rollout');

-- ─── Audit-driven schedule additions (2026-05-21) ────────────────────
-- `scripts/audit-schedule-gaps.py` surfaced commands registered in
-- `jobs_catalog.COMMANDS` that had no `scanner_schedules` row. After
-- categorising the gaps by "should this be scheduled?" heuristics, the
-- following 7 rows close the genuinely-latent slots. The audit script
-- excluded BC ALL-CAPS / BC-dated / federal acting-speakers as
-- one-shot / superseded — see audit-schedule-gaps.py for the categoriser.
INSERT INTO scanner_schedules (name, command, args, cron, enabled, created_by) VALUES
-- Historical-roster ingesters — weekly Sundays at 04:25-04:40 UTC,
-- continuing the QC slot (04:20) added earlier 2026-05-21. New
-- retirements trickle in across years; weekly cadence is right.
('BC former MLAs roster refresh',
 'ingest-bc-former-mlas', '{}'::jsonb,
 '25 4 * * 0', true, 'audit-2026-05-21'),
('MB former MLAs roster refresh',
 'ingest-mb-former-mlas', '{}'::jsonb,
 '30 4 * * 0', true, 'audit-2026-05-21'),
('NU former MLAs roster refresh',
 'ingest-nu-former-mlas', '{}'::jsonb,
 '35 4 * * 0', true, 'audit-2026-05-21'),
('ON former MPPs roster refresh',
 'ingest-on-former-mpps', '{}'::jsonb,
 '40 4 * * 0', true, 'audit-2026-05-21'),

-- ON parliament-keyed speaker resolver (sister of resolve-qc-speakers-dated
-- which was also unscheduled until earlier today). Slot is between
-- resolve-on-speakers (35 18) and extract-on-votes (55 18). First
-- manual run on 2026-05-21 only attributed 90/32,297 candidates because
-- the parliament-vs-source-tag matching is weaker than QC's date-window;
-- the schedule is for steady-state catch-up on new ingest.
('ON parliament-keyed speaker resolver',
 'resolve-on-speakers-dated', '{}'::jsonb,
 '40 18 * * *', true, 'audit-2026-05-21'),

-- Coverage stats + materialized-view refresh. End-of-day so they see
-- the full day's ingest. TODO line 141 explicitly calls these Always-on.
('Coverage stats refresh',
 'refresh-coverage-stats', '{}'::jsonb,
 '50 23 * * *', true, 'audit-2026-05-21'),
('Map materialized views refresh',
 'refresh-views', '{}'::jsonb,
 '55 23 * * *', true, 'audit-2026-05-21'),

-- Ingest-freshness sentinel: per jurisdiction, MAX(bill_events) vs
-- MAX(speeches) lag. Exits non-zero on breach so the run shows FAILED
-- in the admin panel. Weekly Monday — catches "succeeded, sittings=0"
-- Hansard holes (QC/NB/NU incident, 2026-08-02).
('Ingest freshness sentinel (weekly)',
 'check-ingest-freshness', '{}'::jsonb,
 '37 13 * * 1', true, 'daily-ingest-rollout'),

-- Boundary coverage sentinel. Weekly Monday, 20 minutes after the ingest
-- freshness check so the two maintenance sentinels do not overlap.
-- ⚠ Catches what a district count alone cannot: duplicate roster rows, members
-- with no district, orphaned constituency_ids, and geometry drift. Four
-- jurisdictions in the 2026 boundary programme had a PERFECT count over wrong
-- data. A member shortfall is reported as a vacancy, never failed.
-- ⛔ DAILY, not weekly, since 2026-08-27. On 2026-08-23 an Open North re-ingest
-- reverted twelve cutover migrations; this sentinel FAILED on 2026-08-24 and
-- the failure sat unread for five days because the next run was a week out. It
-- is cheap and the damage window is what matters, not the run cost.
-- ⛔ Runs 12 min BEFORE the sentinel, deliberately. A boundary cutover renames
-- the source_set and re-keys constituency_id; the roster joins on that id and
-- nothing in the cutover touches it, so every cutover silently severs its
-- council. On 2026-08-28 that was 142 sitting officials across 18 councils
-- (Calgary 14, Winnipeg 14, Welland 12, Fredericton 12, Edmonton 12, Regina 10)
-- whose ward polygon was sitting right there, unlinked.
-- ⚠ Idempotent, and it REFUSES rather than guesses: it picks a council's set
-- geographically (ST_Contains against the municipality polygon), because
-- `Ward 1`..`Ward 14` is covered identically by hamilton-wards and
-- london-wards. Scheduling it does not paper over the sentinel — a council it
-- cannot fix still surfaces as `detached-council`, and a genuinely missing
-- polygon surfaces as the `missing-district-polygon` advisory.
('Municipal roster re-attach (daily, before the sentinel)',
 'reattach-municipal-roster', '{}'::jsonb,
 '45 13 * * *', true, 'daily-ingest-rollout'),

('Boundary coverage sentinel (daily)',
 'check-boundary-coverage', '{}'::jsonb,
 '57 13 * * *', true, 'daily-ingest-rollout'),

-- Roster enrichment + slug-stamping additions (MEDIUM-bucket triage,
-- same audit cycle, later in the day). Slotted into the Sunday
-- weekly-enrichment block right after the historical-roster
-- ingesters (25-40 04 UTC) and before verify-socials (00 05 UTC).
-- Ordering within the block:
--   42 04  enrich-socials-all (largest fan-out: wikidata→openparl→masto)
--   45 04  enrich-ab-mlas      (per-MLA page fetch, ~90 MLAs × 1s delay)
--   48 04  enrich-bc-member-parliaments (single LIMS GraphQL query)
--   50 04  ingest-mb-mlas      (slug stamping from /legislature/members/info/)
--   52 04  ingest-nt-mlas      (slug stamping + ~100 former MLAs paginated)
-- `ingest-mb-mlas` is distinct from `ingest-manitoba-mlas` (Open North):
-- this one stamps the surname-slug from the Legislative Assembly so
-- sponsor / speaker resolution is an exact FK lookup. Both should run.
-- `ingest-nt-mlas` is the prereq for the daily NT Hansard chain at
-- 30 21 UTC — refreshes nt_mla_slug stamping + picks up new former MLAs.
('Socials enrichment chain (wikidata+openparl+masto)',
 'enrich-socials-all', '{}'::jsonb,
 '42 4 * * 0', true, 'audit-2026-05-21'),
('AB MLA detail enrichment (per-MID fetch)',
 'enrich-ab-mlas', '{}'::jsonb,
 '45 4 * * 0', true, 'audit-2026-05-21'),
('BC member-parliament edges enrichment',
 'enrich-bc-member-parliaments', '{}'::jsonb,
 '48 4 * * 0', true, 'audit-2026-05-21'),
('MB MLA assembly-slug stamping',
 'ingest-mb-mlas', '{}'::jsonb,
 '50 4 * * 0', true, 'audit-2026-05-21'),
('NT MLA slug stamping + former-members ingest',
 'ingest-nt-mlas', '{}'::jsonb,
 '52 4 * * 0', true, 'audit-2026-05-21');

-- ─── Weekly current-roster refresh — REMOVED 2026-08-27 ─────────────
-- ⛔ THIS BLOCK RE-ENABLED OPEN NORTH ROSTER INGESTION ON EVERY RUN.
--
-- It DELETEd by `created_by` and re-INSERTed nine schedules with
-- `enabled = true`, so re-running this seed silently reverted migration
-- 0087, which had disabled exactly those schedules when the Open North
-- mirror was retired on 2026-08-19. A migration that a routine seed can
-- undo is not a retirement.
--
-- ★ The 2026-08-23 incident did not come through here — it came from
-- `scripts/scanner-cron.sh`, a second undocumented scheduler running a
-- three-month-old image. But this block was the same failure waiting on
-- a different trigger, and it is removed for the same reason.
--
-- The commands themselves (`ingest-mps`, `ingest-mlas`, `ingest-bc-mlas`,
-- `ingest-ontario-mpps`, `ingest-new-brunswick-mlas`, `ingest-nl-mhas`,
-- `ingest-pei-mlas`, `ingest-yukon-mlas`) are gone from the job catalogue.
-- Roster refresh now belongs to each jurisdiction's own ingester; where one
-- does not exist yet the roster is FROZEN, and saying so is Stage F's job.
--
-- ⚠ `ingest-senators` was in this block and is NOT an Open North command.
-- It is preserved below.
DELETE FROM scanner_schedules WHERE created_by = 'roster-audit-2026-08-12';

INSERT INTO scanner_schedules (name, command, args, cron, enabled, created_by) VALUES
('Senate roster weekly refresh',
 'ingest-senators', '{}'::jsonb,
 '8 5 * * 0', true, 'roster-audit-2026-08-12');

-- next_run_at is computed by the worker the first time it polls; leave
-- it NULL here so croniter advances it correctly on the worker tick.

COMMIT;

-- Show what we just wrote.
SELECT name, cron, enabled, command FROM scanner_schedules
 WHERE created_by IN ('daily-ingest-rollout', 'audit-2026-05-21', 'roster-audit-2026-08-12')
 ORDER BY cron, name;
