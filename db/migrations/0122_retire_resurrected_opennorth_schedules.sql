-- 0122 — Disable the two Open North roster schedules that 0087 already retired,
--        and that the daily-ingest seeder silently brought back.
--
-- ⛔ WHY THIS EXISTS TWICE
-- -----------------------
-- Migration 0087 (2026-08-20) disabled every Open North roster schedule and
-- asserted, in a DO block, that zero remained enabled. It passed.
--
-- On 2026-08-28 `scripts/seed-daily-ingest-schedules.sql` was re-run and
-- INSERTed 'QC MNA roster refresh' and 'MB MLA roster refresh' as NEW daily rows
-- under created_by='daily-ingest-rollout'. The weekly rows 0087 disabled are
-- still sitting there, disabled, beside them.
--
-- ★ So the defect was never the schedule. It was that a migration's deliberate
--   decision is not durable against an idempotent seeder that does not know the
--   decision was made. This is the same SHAPE as the 2026-08-23 mirror
--   regression — an independent mechanism quietly reversing an applied one — and
--   it is why the seeder itself was edited in the same change as this migration.
--   Disabling these rows without that edit would last until the next seeder run.
--
-- Cost of the resurrection: 8 failed `ingest-quebec-mnas` runs and 11 failed
-- `ingest-manitoba-mlas` runs, every one of them a RuntimeError from the retired
-- ingester. Nothing was written — `opennorth._ingest_set` refuses without
-- OPENNORTH_ALLOW_INGEST=1 — so this cost noise, not data. The 124 QC MNA and
-- 57 MB MLA rows were already frozen and remain so; both carry native
-- legislature IDs (qc_assnat_id, mb_assembly_slug) and refresh from their own
-- pipelines, which is why the freeze metric does not count them.
--
-- ⓘ Disabled, not deleted — same posture as 0087.
--
-- Forward-only. Apply with:
--   docker exec -i sw-db psql -U sw -d sovereignwatch -v ON_ERROR_STOP=1 \
--     < db/migrations/0122_retire_resurrected_opennorth_schedules.sql

BEGIN;

UPDATE scanner_schedules
   SET enabled = false, updated_at = now()
 WHERE enabled
   AND command IN ('ingest-quebec-mnas', 'ingest-manitoba-mlas');

DO $$
DECLARE still int; n_disabled int;
BEGIN
    -- ⚠ Broader than the UPDATE on purpose. 0087 checked only the names it knew;
    -- this checks every command whose docstring says it fetches from Open North,
    -- so a THIRD resurrection under a different name fails here instead of
    -- failing silently once a day for a month.
    SELECT count(*) INTO still FROM scanner_schedules
     WHERE enabled AND command IN (
       'ingest-mps','ingest-mlas','ingest-bc-mlas','ingest-ontario-mpps',
       'ingest-quebec-mnas','ingest-manitoba-mlas','ingest-saskatchewan-mlas',
       'ingest-nova-scotia-mlas','ingest-new-brunswick-mlas','ingest-pei-mlas',
       'ingest-nl-mhas','ingest-yukon-mlas','ingest-nwt-mlas',
       'ingest-nunavut-mlas','ingest-legislatures','ingest-councils',
       'ingest-all-councils','ingest-all-legislatures','ingest-ab-extras');
    IF still <> 0 THEN
        RAISE EXCEPTION
          '% Open North schedule(s) still enabled — check scripts/seed-daily-ingest-schedules.sql',
          still;
    END IF;

    SELECT count(*) INTO n_disabled FROM scanner_schedules
     WHERE NOT enabled AND command IN ('ingest-quebec-mnas','ingest-manitoba-mlas');
    RAISE NOTICE '0122 ok: % QC/MB roster schedule rows now disabled (2 weekly from 0087 + 2 daily from the seeder)', n_disabled;
END $$;

COMMIT;
