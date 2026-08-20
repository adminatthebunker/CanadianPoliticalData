-- 0092 — New Brunswick municipal cutover: retire the Open North mirror's ward
--        geometry for Fredericton, Moncton and Saint John.
--
-- Run AFTER `load-boundaries` for the `new-brunswick-municipal` spec, which
-- loads 312 wards across 93 local governments and rural districts from
-- gnb.socrata.com `7zs3-pcvk` (publisher of record: GeoNB).
--
-- ⛔ WHAT NEEDS RETIRING AND WHY IT IS NOT AUTOMATIC
-- -------------------------------------------------
-- The loader's upsert key is (constituency_id, boundaries_version), so loading
-- the `2023` generation over the mirror's `current` one INSERTS beside it rather
-- than replacing it. That is deliberate — only a migration knows a generation is
-- superseded — but until this runs, 20 constituency_ids are live TWICE and every
-- point-in-polygon in those three cities returns each ward twice.
--
-- ⚠ The roster is unaffected either way: both generations carry the SAME
-- constituency_id, so the 34 NB municipal officials stay attached across the
-- cutover. Nothing to re-key.
--
-- ★ VINTAGE, MEASURED
-- -------------------
-- Against the authoritative file, our 20 held wards overlap their real
-- counterparts at a mean of 78.55%, minimum 38.38%:
--
--   fredericton-wards/ward-6   38.38%
--   fredericton-wards/ward-1   39.09%
--   fredericton-wards/ward-2   50.91%
--   fredericton-wards/ward-7   64.40%
--   fredericton-wards/ward-5   65.16%
--
-- 13 of 20 fall below 95%. That is a redistribution signature, not a drawing-
-- convention artefact — and the cause is documented: New Brunswick's 2023 Local
-- Governance Reform restructured every local government in the province.
--
-- ★ The single clearest piece of evidence is a ward we did not hold at all.
-- Fredericton's authoritative wards are 1..12 PLUS `4-Lincoln` — thirteen. We
-- held twelve. `4-Lincoln` exists because Lincoln was annexed into Fredericton
-- by the reform. A generation missing an entire ward is not a near-miss.
--
-- ⛔ DELETED, not end-dated, for the same reason as the BC/SK/NB provincial
-- cutovers: pre-reform mirror geometry under post-reform names was never a real
-- generation, so there is no history to preserve. The authoritative file is
-- staged and GeoNB publishes the prior generations if genuine history is wanted.
--
-- ⓘ Nova Scotia needs no equivalent migration. Halifax and Cape Breton are
-- excluded from that load by `row_filter` — the province's file carries no
-- district NAME field, and loading codes over 28 properly-named districts would
-- have orphaned both councils' rosters to gain nothing.
--
-- Forward-only. Apply with:
--   docker exec -i sw-db psql -U sw -d sovereignwatch -v ON_ERROR_STOP=1 \
--     < db/migrations/0092_new_brunswick_municipal_cutover.sql

BEGIN;

DO $$
DECLARE n int;
BEGIN
    SELECT count(*) INTO n FROM constituency_boundaries
     WHERE level = 'municipal' AND province_territory = 'NB'
       AND boundaries_version = '2023';
    IF n <> 312 THEN
        RAISE EXCEPTION
          'Expected 312 authoritative NB municipal wards, found %. Run '
          '`load-boundaries --spec-file .../new-brunswick-municipal.py` first.', n;
    END IF;
END $$;

-- ⚠ Scoped to ids the authoritative generation actually replaced. A blanket
-- delete of `boundaries_version = 'current'` would also take the three
-- `census-subdivisions` municipality polygons that Moncton's, Fredericton's and
-- Saint John's mayors sit on — which the authoritative ward file does not
-- contain and does not supersede.
DELETE FROM constituency_boundaries old
 WHERE old.level = 'municipal'
   AND old.province_territory = 'NB'
   AND old.boundaries_version = 'current'
   AND EXISTS (
       SELECT 1 FROM constituency_boundaries new
        WHERE new.constituency_id = old.constituency_id
          AND new.boundaries_version = '2023');

DO $$
DECLARE dupes int; attached int; mayors int;
BEGIN
    SELECT count(*) INTO dupes FROM (
        SELECT constituency_id FROM constituency_boundaries
         WHERE level = 'municipal' AND province_territory = 'NB'
           AND effective_from <= CURRENT_DATE
           AND (effective_to IS NULL OR effective_to >= CURRENT_DATE)
         GROUP BY 1 HAVING count(*) > 1) d;
    IF dupes <> 0 THEN
        RAISE EXCEPTION 'NB cutover left % ids live in two generations', dupes;
    END IF;

    -- The roster must survive untouched: same constituency_id on both sides.
    SELECT count(*) INTO attached FROM politicians
     WHERE level = 'municipal' AND province_territory = 'NB' AND is_active
       AND constituency_id IS NOT NULL;
    IF attached <> 34 THEN
        RAISE EXCEPTION
          'Expected 34 NB municipal officials still attached, found % — the '
          'cutover was supposed to be roster-neutral', attached;
    END IF;

    -- ⚠ Keyed on the constituency_id PREFIX, not on `source_set`. For these
    -- mirror rows the two disagree: the id is `census-subdivisions/1310032`
    -- while the source_set is `fredericton-wards`. That mismatch affects 93 rows
    -- table-wide and is exactly the kind of thing an assertion written against
    -- the wrong column reports as a catastrophe (it did, on the first run).
    SELECT count(*) INTO mayors FROM constituency_boundaries
     WHERE level = 'municipal' AND province_territory = 'NB'
       AND constituency_id LIKE 'census-subdivisions/%';
    IF mayors <> 3 THEN
        RAISE EXCEPTION
          'Expected the 3 NB census-subdivision polygons to survive, found %',
          mayors;
    END IF;

    RAISE NOTICE 'NB municipal: superseded mirror geometry retired; % wards live',
        (SELECT count(*) FROM constituency_boundaries
          WHERE level='municipal' AND province_territory='NB'
            AND boundary_kind='district');
END $$;

COMMIT;

SELECT refresh_map_views();
