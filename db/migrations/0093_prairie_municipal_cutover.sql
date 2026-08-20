-- 0093 — Calgary / Edmonton / Winnipeg municipal cutover: retire the Open North
--        mirror generation now that each city's own file is loaded.
--
-- Run AFTER `load-boundaries --jurisdiction {calgary,edmonton,winnipeg}-wards`.
--
-- ⛔ CALGARY IS A REPLACEMENT. THE OTHER TWO ARE PROVENANCE UPGRADES.
-- --------------------------------------------------------------------
-- Calgary, measured against the city's current file with the comparison scoped
-- to Calgary's own set: **mean overlap 92.43%, minimum 71.01%, 8 of 14 wards
-- below 95%**. Against the SUPERSEDED 2017–2021 file the dossier measured mean
-- 0.36% area error with 14/14 within 2%. No ward matches the current generation
-- better than it matches the old one.
--
-- ★ The count check passes perfectly at 14 -> 14, which is exactly A7's point:
-- a full district count proves nothing. This is the third confirmed instance,
-- after SK (61 -> 61) and NT (19/19).
--
-- ⚠ A8.1's counter-argument, noted and dismissed: Calgary is landlocked, so the
-- offshore-envelope drawing convention that makes coastal comparisons
-- unreliable cannot be what produces a 29-point overlap deficit on Ward 11.
-- Until now, addresses in that part of Ward 11 resolved to the wrong councillor.
--
-- Edmonton (mean 99.65%, min 98.26%) and Winnipeg (mean 99.81%, min 99.50%)
-- were already correct. Their cutover buys an authority, a licence note, and a
-- real in-force date in place of the mirror's `effective_from = 2023-01-01`,
-- which was never a fact about anything.
--
-- ★ WINNIPEG GAINS THE WARD WE NEVER HAD: `Elmwood – East Kildonan`, ward 14.
-- 14 held, 15 authoritative, one absent — and the absent one is a real ward with
-- a sitting councillor.
--
-- ★ AND THE MANITOBA DATE WAS NEVER BLOCKED. It had been recorded as waiting on
-- "no dossier has a Manitoba municipal election date", with a guess of late
-- October 2026. Wrong question: these are the 2018 wards and the dataset's own
-- description says so — "updated in November of 2018 to reflect the new council
-- wards". Ruling A10.4 gives 2018-10-24, in the past, not the future.
--
-- ⛔ DELETED rather than end-dated, consistent with the earlier cutovers: a
-- mirror generation carrying an invented `effective_from` is not a historical
-- record of anything. Calgary's genuine prior generation is published by the
-- city as `au4g-xjwh` and is staged under `municipal-alberta/prior/`.
--
-- ⚠ Roster-neutral by construction — both generations carry the same
-- constituency_id, so the 74 AB and 15 MB municipal officials stay attached.
--
-- Forward-only. Apply with:
--   docker exec -i sw-db psql -U sw -d sovereignwatch -v ON_ERROR_STOP=1 \
--     < db/migrations/0093_prairie_municipal_cutover.sql

BEGIN;

DO $$
DECLARE n int;
BEGIN
    SELECT count(*) INTO n FROM constituency_boundaries
     WHERE (source_set, boundaries_version) IN
           (('calgary-wards','2021'), ('edmonton-wards','2021'),
            ('winnipeg-wards','2018'));
    IF n <> 41 THEN
        RAISE EXCEPTION
          'Expected 41 authoritative rows (Calgary 14 + Edmonton 12 + '
          'Winnipeg 15), found %. Run the three loads first.', n;
    END IF;
END $$;

-- ⚠ Scoped to ids the authoritative generation actually replaced, so the three
-- `census-subdivisions/*` municipality polygons that each city's mayor sits on
-- survive. Those live INSIDE the ward source_sets (id prefix and source_set
-- disagree for 93 mirror rows table-wide) and are not superseded by a ward file.
DELETE FROM constituency_boundaries old
 USING constituency_boundaries new
 WHERE old.source_set IN ('calgary-wards','edmonton-wards','winnipeg-wards')
   AND old.boundaries_version = 'current'
   AND new.constituency_id = old.constituency_id
   AND new.source_set = old.source_set
   AND new.boundaries_version <> 'current';

DO $$
DECLARE dupes int; wards int; csds int; elmwood int; attached int;
BEGIN
    SELECT count(*) INTO dupes FROM (
        SELECT constituency_id FROM constituency_boundaries
         WHERE source_set IN ('calgary-wards','edmonton-wards','winnipeg-wards')
           AND effective_from <= CURRENT_DATE
           AND (effective_to IS NULL OR effective_to >= CURRENT_DATE)
         GROUP BY 1 HAVING count(*) > 1) d;
    IF dupes <> 0 THEN
        RAISE EXCEPTION 'Prairie cutover left % ids live in two generations', dupes;
    END IF;

    SELECT count(*) INTO wards FROM constituency_boundaries
     WHERE source_set IN ('calgary-wards','edmonton-wards','winnipeg-wards')
       AND boundary_kind = 'district';
    IF wards <> 41 THEN
        RAISE EXCEPTION 'Expected 41 live prairie wards, found %', wards;
    END IF;

    SELECT count(*) INTO csds FROM constituency_boundaries
     WHERE source_set IN ('calgary-wards','edmonton-wards','winnipeg-wards')
       AND constituency_id LIKE 'census-subdivisions/%';
    IF csds <> 3 THEN
        RAISE EXCEPTION
          'Expected the 3 mayoral census-subdivision polygons to survive, found %',
          csds;
    END IF;

    SELECT count(*) INTO elmwood FROM constituency_boundaries
     WHERE constituency_id = 'winnipeg-wards/elmwood-east-kildonan';
    IF elmwood <> 1 THEN
        RAISE EXCEPTION 'Elmwood – East Kildonan did not load';
    END IF;

    SELECT count(*) INTO attached FROM politicians
     WHERE is_active AND level = 'municipal'
       AND constituency_id LIKE ANY (ARRAY['calgary-wards/%','edmonton-wards/%',
                                           'winnipeg-wards/%'])
       AND NOT EXISTS (SELECT 1 FROM constituency_boundaries b
                        WHERE b.constituency_id = politicians.constituency_id);
    IF attached <> 0 THEN
        RAISE EXCEPTION
          'Prairie cutover orphaned % officials — it was supposed to be '
          'roster-neutral', attached;
    END IF;

    RAISE NOTICE 'Calgary/Edmonton/Winnipeg: mirror generation retired, 41 wards live';
END $$;

COMMIT;

SELECT refresh_map_views();
