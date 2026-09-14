-- 0129 — Québec provincial: jurisdiction_sources.seats 125 -> 127.
--
-- ⛔ DO NOT APPLY BEFORE 2026-10-05. THIS MIGRATION REFUSES IF YOU TRY.
--
-- Migration 0117 re-dated Québec's 2026 provincial map to polling day under
-- ruling A10.4 (a generation is dated to the election it first governed, not to
-- its legal date) and left this as the stated follow-up:
--
--     "⚠ FOLLOW-UP DUE 2026-10-05. jurisdiction_sources.seats for QC must go
--      125 -> 127 ... Until then 125 is correct — it is how many seats are
--      filled. Doing it early would be wrong."
--
-- That is exactly right, so this file is written in advance and left unapplied.
-- The guard below is not documentation: it counts LIVE districts, and before
-- polling day there are 125, so an early run raises and rolls back. The
-- migration cannot be applied at the wrong time even by accident.
--
-- ── WHAT HAPPENS ON THE DAY ──────────────────────────────────────────────────
-- The 2017 generation (125 districts) end-dates 2026-10-04 and the 2026
-- generation (127) takes force 2026-10-05. Both are already loaded; nothing
-- needs fetching. At that moment, without this migration:
--
--   check-boundary-coverage  ->  districts=127 seats=125  ->  BREACH
--
-- because the sentinel compares the live district count against the recorded
-- seat count, and 125 stops being the truth the instant the map flips.
--
-- ⚠ AND SIX MNAs DETACH, WHICH THIS MIGRATION DOES NOT FIX. Six sitting members
-- hold a `constituency_id` belonging to a 2017 district that has no counterpart
-- in the 2026 map — measured 2026-09-14, six exactly. Their districts are
-- dissolved, not renamed, so there is no re-key that would be correct: the
-- right answer comes from the election result, not from us. Ingest the QC
-- provincial roster for the new cycle in the same change, and expect the
-- sentinel to report those six as orphaned until you do.
--
-- ⓘ Why not fold the roster in here? Because a seat count is a fact we can
-- assert today and an election result is not. Splitting them means this file
-- can be reviewed now, applied mechanically on the day, and cannot be wrong.
--
-- Forward-only. Apply with:
--   docker exec -i sw-db psql -U sw -d sovereignwatch -v ON_ERROR_STOP=1 \
--     < db/migrations/0129_qc_provincial_seats_125_to_127.sql

BEGIN;

DO $$
DECLARE n_live int; n_incoming int;
BEGIN
    SELECT count(*) INTO n_live FROM constituency_boundaries
     WHERE source_set = 'quebec-electoral-districts'
       AND effective_from <= CURRENT_DATE
       AND (effective_to IS NULL OR effective_to >= CURRENT_DATE);

    -- ⛔ THE TIMING GUARD. 125 means the map has not flipped yet.
    IF n_live <> 127 THEN
        RAISE EXCEPTION
            'REFUSING: % live QC provincial districts, expected 127. The 2026 '
            'map takes force 2026-10-05 and today is %. Until then 125 seats is '
            'CORRECT — it is how many seats are filled — and writing 127 early '
            'makes the sentinel breach in the other direction.',
            n_live, CURRENT_DATE;
    END IF;

    -- Belt and braces: the incoming generation must be the one we think.
    SELECT count(*) INTO n_incoming FROM constituency_boundaries
     WHERE source_set = 'quebec-electoral-districts'
       AND effective_from = DATE '2026-10-05';
    IF n_incoming <> 127 THEN
        RAISE EXCEPTION 'expected 127 districts dated 2026-10-05, found %', n_incoming;
    END IF;
END $$;

UPDATE jurisdiction_sources
   SET seats = 127, updated_at = now()
 WHERE jurisdiction = 'QC' AND level = 'provincial';

DO $$
DECLARE n int; n_orphan int;
BEGIN
    SELECT seats INTO n FROM jurisdiction_sources
     WHERE jurisdiction = 'QC' AND level = 'provincial';
    IF n <> 127 THEN
        RAISE EXCEPTION 'QC provincial seats is % after the update, expected 127', n;
    END IF;

    -- Reported, not fatal. The six are a real consequence of the redistribution
    -- and the fix is the election result, not this migration.
    SELECT count(*) INTO n_orphan FROM politicians p
     WHERE p.is_active AND p.level = 'provincial' AND p.province_territory = 'QC'
       AND p.constituency_id IS NOT NULL
       AND NOT EXISTS (
         SELECT 1 FROM constituency_boundaries b
          WHERE b.constituency_id = p.constituency_id
            AND b.effective_from <= CURRENT_DATE
            AND (b.effective_to IS NULL OR b.effective_to >= CURRENT_DATE));
    RAISE NOTICE
        '0129 ok: QC provincial seats 125 -> 127. % MNA(s) now hold a dissolved '
        'district — ingest the election result to reseat them.', n_orphan;
END $$;

COMMIT;
