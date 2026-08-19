-- 0064 — Ontario cutover: retire the Open North mirror, adopt Elections Ontario.
--
-- The FIRST jurisdiction moved off the Open North mirror onto an authoritative,
-- licensed primary source. Ontario was chosen as the pilot because its
-- reconciliation is exact — slugifying the authoritative district names
-- reproduces all 123 existing slugs with zero fuzzy matching — so the strategy
-- can be proven without a crosswalk table confusing the result.
--
-- Run AFTER `load-boundaries --jurisdiction ontario`, which inserts 124 rows
-- under the new generation-free prefix. Until this migration runs, both
-- generations satisfy the current-date predicate and Ontario returns duplicates.
--
-- What changes
-- ------------
--   old: ontario-electoral-districts-representation-act-2015/<slug>
--        boundaries_version 'current', effective_from 2023-01-01 (fabricated —
--        opennorth.py hardcoded that date for every row in the table)
--        source_set  ontario-electoral-districts-representation-act-2015
--        123 rows, geometry mirrored from Open North, no licence inherited
--
--   new: ontario-electoral-districts/<slug>
--        boundaries_version '2018', effective_from 2018-05-08 (the legal date:
--        Representation Act, 2015 s. 2(2), first dissolution after 2016-11-30)
--        source_set  ontario-electoral-districts
--        authority   elections-ontario, authority_district_id = ED_ID (1-124)
--        124 rows incl. the previously-missing Scarborough Southwest (ED_ID 98)
--        name_fr populated, licence Open Use (redistribution permitted)
--
-- ⚠ The prefix loses its generation on purpose. `constituency_id` is
-- generation-independent by design — the unique key is
-- (constituency_id, boundaries_version) — so encoding a year forces a full
-- `politicians` UPDATE on every future redistribution. 12 of our 13 prefixes
-- still have that defect; Ontario is the first fixed.
--
-- Verified before writing this migration: the authoritative geometry overlaps
-- what we held at 99.8902% mean / 99.3706% min, zero districts below 95%. So
-- this is a provenance and licensing upgrade plus one missing district — NOT a
-- silent geometry change. (Ontario's held rows were the correct 2018 generation,
-- which is why the pilot is low-risk. BC, NB, SK and NWT are not.)
--
-- Forward-only. Apply with:
--   docker exec -i sw-db psql -U sw -d sovereignwatch -v ON_ERROR_STOP=1 \
--     < db/migrations/0064_ontario_boundary_cutover.sql

BEGIN;

-- Guard: refuse to run if the authoritative load hasn't happened. Deleting the
-- old rows without the new ones in place would blank Ontario entirely.
DO $$
DECLARE n int;
BEGIN
    SELECT count(*) INTO n
      FROM constituency_boundaries
     WHERE constituency_id LIKE 'ontario-electoral-districts/%'
       AND boundaries_version = '2018';
    IF n <> 124 THEN
        RAISE EXCEPTION
          'Expected 124 authoritative Ontario rows, found %. Run '
          '`load-boundaries --jurisdiction ontario` first.', n;
    END IF;
END $$;

-- Repoint the roster. Same slug on both sides, so this is a pure prefix swap
-- with no lookup and no fuzzy matching — the property that made Ontario the
-- pilot. Scarborough Southwest's politician rows already carry the old-prefix
-- id or none at all; the id form is what changes here, not the mapping.
UPDATE politicians
   SET constituency_id = 'ontario-electoral-districts/'
                       || split_part(constituency_id, '/', 2)
 WHERE constituency_id LIKE 'ontario-electoral-districts-representation-act-2015/%';

UPDATE politician_terms
   SET constituency_id = 'ontario-electoral-districts/'
                       || split_part(constituency_id, '/', 2)
 WHERE constituency_id LIKE 'ontario-electoral-districts-representation-act-2015/%';

-- Retire the mirror. Deleted rather than end-dated: these are not a superseded
-- *generation*, they are a worse copy of the same one. Keeping them with an
-- effective_to would imply Ontario redistributed in 2018→2026, which it did not.
DELETE FROM constituency_boundaries
 WHERE constituency_id LIKE 'ontario-electoral-districts-representation-act-2015/%';

-- Post-conditions. Any failure rolls the whole thing back.
DO $$
DECLARE
    bnd int; orphans int; dupes int;
BEGIN
    SELECT count(*) INTO bnd
      FROM constituency_boundaries
     WHERE level = 'provincial' AND province_territory = 'ON'
       AND effective_from <= CURRENT_DATE
       AND (effective_to IS NULL OR effective_to >= CURRENT_DATE);
    IF bnd <> 124 THEN
        RAISE EXCEPTION 'Expected 124 current ON provincial boundaries, found %', bnd;
    END IF;

    -- No politician may point at a boundary that no longer exists.
    SELECT count(*) INTO orphans
      FROM politicians p
     WHERE p.constituency_id LIKE 'ontario-electoral-districts%'
       AND NOT EXISTS (SELECT 1 FROM constituency_boundaries b
                        WHERE b.constituency_id = p.constituency_id);
    IF orphans <> 0 THEN
        RAISE EXCEPTION 'Ontario cutover left % orphaned politician rows', orphans;
    END IF;

    -- One current row per district.
    SELECT count(*) INTO dupes FROM (
        SELECT constituency_id FROM constituency_boundaries
         WHERE level='provincial' AND province_territory='ON'
           AND effective_from <= CURRENT_DATE
           AND (effective_to IS NULL OR effective_to >= CURRENT_DATE)
         GROUP BY 1 HAVING count(*) > 1) d;
    IF dupes <> 0 THEN
        RAISE EXCEPTION 'Ontario cutover left % duplicated districts', dupes;
    END IF;
END $$;

COMMIT;

-- Refresh the map materialized views so centroids/geometry pick up the change,
-- matching what migration 0003 does for the same reason.
SELECT refresh_map_views();
