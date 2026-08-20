-- 0097 — Niagara Region: adopt the Region's own ward boundaries for 11 of its
--        12 lower-tier municipalities, and close the last orphaned
--        constituency_ids in the table.
--
-- Run AFTER `load-boundaries --jurisdiction niagara-region-wards`.
--
-- ★ THE FIRST ONTARIO AGGREGATOR, and the reason it matters is structural.
-- Ontario has no provincial ward layer, because wards are created by local
-- by-law and never centrally registered — which is why the plan treats Ontario
-- as ~47 separate discoveries. But an UPPER-TIER REGION publishing a voter tool
-- covers its lower-tier municipalities in one service. This one carried 12 at
-- once. Peel, York, Durham, Halton and Waterloo are worth probing the same way
-- before treating them as individual discoveries.
--
-- ★ AND IT CLOSES THE LAST BREACH. `fort-erie-wards/ward-2` and `/ward-4` were
-- the only orphaned constituency_ids left in the table — two sitting councillors
-- pointing at boundaries that did not exist. We held 4 of Fort Erie's 6 wards;
-- the Region publishes all 6.
--
-- ⓘ VINTAGE, MEASURED RATHER THAN ASSUMED. The AGOL item's `modified` is
-- 2018-10-17 and Ontario has voted since, so this was loaded only after
-- comparing: **18 of our held wards match at mean 99.43%, min 98.45%, none below
-- 95%** — Grimsby included, which was on the list of Niagara municipalities with
-- a recent ward review and is the worst of the eighteen at 98.45%.
--
-- ⚠ Stated honestly: per the A8.1 refinement, near-perfect overlap says nothing
-- about CURRENCY when both sides may share a lineage. What it does establish is
-- that adopting this source changes no geometry we already had, so the load is
-- additive — 20 new districts and a real authority, licence and date — rather
-- than a substitution of one uncertain generation for another.
--
-- ⛔ ST. CATHARINES IS EXCLUDED, for the same reason Halifax and Cape Breton are
-- excluded from the Nova Scotia aggregator: the aggregator is WORSE than what we
-- hold. St. Catharines' six wards have NAMES — Grantham, Merritton, Port
-- Dalhousie, St. Andrew's, St. George's, St. Patrick's, two councillors each —
-- and that is what the city uses. The Region's voter tool numbers them 1..6.
-- Loading it would mint six parallel numbered rows beside six named ones and
-- orphan twelve councillors, to replace a name with an ordinal.
--
-- ⚠ Niagara Falls elects at large: its single feature carries
-- `WARD = "Councillor at Large"`, which a naive label would turn into the
-- district "Ward Councillor at Large". It loads as `at-large`.
--
-- Forward-only. Apply with:
--   docker exec -i sw-db psql -U sw -d sovereignwatch -v ON_ERROR_STOP=1 \
--     < db/migrations/0097_niagara_region_wards_cutover.sql

BEGIN;

DO $$
DECLARE n int;
BEGIN
    SELECT count(*) INTO n FROM constituency_boundaries
     WHERE authority = 'niagara-region' AND boundaries_version = '2018';
    IF n <> 38 THEN
        RAISE EXCEPTION
          'Expected 38 authoritative Niagara wards, found %. Run '
          '`load-boundaries --jurisdiction niagara-region-wards` first.', n;
    END IF;
END $$;

DELETE FROM constituency_boundaries old
 USING constituency_boundaries new
 WHERE old.boundaries_version = 'current'
   AND new.authority = 'niagara-region'
   AND new.boundaries_version = '2018'
   AND new.constituency_id = old.constituency_id
   AND new.source_set = old.source_set;

DO $$
DECLARE dupes int; forterie int; orphans int; sets int;
BEGIN
    SELECT count(*) INTO dupes FROM (
        SELECT constituency_id FROM constituency_boundaries
         WHERE level = 'municipal' AND province_territory = 'ON'
           AND effective_from <= CURRENT_DATE
           AND (effective_to IS NULL OR effective_to >= CURRENT_DATE)
         GROUP BY 1 HAVING count(*) > 1) d;
    IF dupes <> 0 THEN
        RAISE EXCEPTION 'Niagara cutover left % ids live in two generations', dupes;
    END IF;

    SELECT count(*) INTO forterie FROM constituency_boundaries
     WHERE source_set = 'fort-erie-wards' AND boundary_kind = 'district';
    IF forterie <> 6 THEN
        RAISE EXCEPTION 'Expected 6 Fort Erie wards, found %', forterie;
    END IF;

    -- ★ The whole point: zero orphaned municipal officials, nationwide.
    SELECT count(*) INTO orphans FROM politicians p
     WHERE p.is_active AND p.level = 'municipal'
       AND p.constituency_id IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM constituency_boundaries b
                        WHERE b.constituency_id = p.constituency_id);
    IF orphans <> 0 THEN
        RAISE EXCEPTION
          '% municipal officials still point at a boundary that does not exist',
          orphans;
    END IF;

    SELECT count(DISTINCT source_set) INTO sets FROM constituency_boundaries
     WHERE authority = 'niagara-region';
    RAISE NOTICE 'Niagara: % municipalities on the Region source; Fort Erie '
                 'complete at 6 wards; 0 orphaned municipal officials nationwide',
                 sets;
END $$;

COMMIT;

SELECT refresh_map_views();
