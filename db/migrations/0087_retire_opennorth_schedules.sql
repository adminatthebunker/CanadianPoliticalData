-- 0087 — Retire the Open North roster schedules (operator decision).
--
-- ⛔ WHY
-- ------
-- The Represent mirror is UP but unmaintained, and over a single evening it
-- undid the boundary programme three separate ways:
--
--   1. resurrected 180 deleted boundary rows in QC and MB, returning both
--      provinces to two live generations with doubled point-in-polygon answers
--      (repaired in 0084);
--   2. retired a hand-verified sitting member three hours after she was added,
--      because the feed has never heard of her (repaired in 0084);
--   3. detached 726 members across 8 jurisdictions onto deleted mirror ids and
--      resurrected the cohorts defeated in the 2025 elections — BC fell from 93
--      attached to 52, NL went back to 48 members for 40 seats (repaired in 0085).
--
-- Each had its own narrow fix. The common cause did not: a feed that is a full
-- election cycle stale in places — it still served Valérie Plante as mayor of
-- Montréal 9½ months after she left office — held write authority over columns
-- set from authoritative sources.
--
-- Code guard already applied: `opennorth._ingest_set` refuses to run unless
-- `OPENNORTH_ALLOW_INGEST=1`. This migration stops the scheduler invoking it, so
-- the nightly run stops failing rather than failing loudly ten times a week.
--
-- ⚠ WHAT THIS COSTS, STATED PLAINLY
-- ---------------------------------
-- Open North is still the source of record for roughly **840 active federal and
-- provincial rows**: 332 MPs, 124 QC MNAs, 122 ON MPPs, 93 BC, 87 AB, 60 SK,
-- 57 MB, 56 NS, 49 NB, 28 NL, 27 PE, 19 NT. Nothing is deleted — those rows
-- simply STOP REFRESHING until a per-jurisdiction replacement exists. Party
-- switches, resignations and by-elections in those chambers will go unnoticed by
-- the pipeline.
--
-- ★ That is the accepted trade: a frozen roster is wrong slowly and visibly,
-- whereas the mirror was wrong quickly and silently — and actively corrupting
-- correct data on the way. `check-boundary-coverage` reports the freeze.
--
-- Québec municipal is the first replacement (`ingest-qc-municipal-roster`, MAMH
-- election results, CC-BY) and the pattern for the rest.
--
-- ⓘ Disabled, not deleted. `enabled = false` keeps the cron expression, the name
-- and the ownership tag, so re-enabling one is a single UPDATE if a jurisdiction
-- needs a stale refresh more than it needs correctness.
--
-- Forward-only. Apply with:
--   docker exec -i sw-db psql -U sw -d sovereignwatch -v ON_ERROR_STOP=1 \
--     < db/migrations/0087_retire_opennorth_schedules.sql

BEGIN;

UPDATE scanner_schedules
   SET enabled = false, updated_at = now()
 WHERE enabled
   AND command IN (
     -- Every Click command whose body calls an opennorth.ingest_* function.
     'ingest-mps', 'ingest-mlas', 'ingest-bc-mlas', 'ingest-ontario-mpps',
     'ingest-quebec-mnas', 'ingest-manitoba-mlas', 'ingest-saskatchewan-mlas',
     'ingest-nova-scotia-mlas', 'ingest-new-brunswick-mlas', 'ingest-pei-mlas',
     'ingest-nl-mhas', 'ingest-yukon-mlas', 'ingest-nwt-mlas',
     'ingest-nunavut-mlas', 'ingest-legislatures', 'ingest-councils',
     'ingest-all-councils', 'ingest-ab-extras'
   );

DO $$
DECLARE still int; disabled int;
BEGIN
    SELECT count(*) INTO still FROM scanner_schedules
     WHERE enabled AND command IN (
       'ingest-mps','ingest-mlas','ingest-bc-mlas','ingest-ontario-mpps',
       'ingest-quebec-mnas','ingest-manitoba-mlas','ingest-saskatchewan-mlas',
       'ingest-nova-scotia-mlas','ingest-new-brunswick-mlas','ingest-pei-mlas',
       'ingest-nl-mhas','ingest-yukon-mlas','ingest-nwt-mlas',
       'ingest-nunavut-mlas','ingest-legislatures','ingest-councils',
       'ingest-all-councils','ingest-ab-extras');
    IF still <> 0 THEN
        RAISE EXCEPTION '% Open North schedules are still enabled', still;
    END IF;

    SELECT count(*) INTO disabled FROM scanner_schedules
     WHERE NOT enabled AND command LIKE 'ingest-%';
    RAISE NOTICE 'Open North schedules retired; % ingest schedules now disabled in total', disabled;
END $$;

COMMIT;
