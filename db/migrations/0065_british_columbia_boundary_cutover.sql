-- 0065 — British Columbia cutover: retire the Open North mirror, adopt Elections BC.
--
-- ★ The single highest-impact change in the boundary programme. BC alone accounts
-- for **6.05 of the national 9.15 percentage-point** no-answer rate — two-thirds
-- of the measured damage. 42.3% of BC addresses currently get no provincial
-- answer at all.
--
-- Run AFTER `load-boundaries --jurisdiction british-columbia`, which inserts 93
-- rows under the generation-free prefix.
--
-- What we held, and why it is deleted rather than retired
-- -------------------------------------------------------
-- The 52 outgoing rows are NOT a valid prior generation, so end-dating them
-- would record a fiction. They are the exact name-stable intersection of the
-- 87-district 2015 order and the 93-district 2023 order, carrying **2015
-- geometry under 2023 district names** — 51 of 52 match 2015 shapes to within
-- 0.5%. There has never been a real BC generation with these 52 names and these
-- 52 shapes. Retiring them as "the 2015 generation" would assert that BC once
-- had 52 districts named this way; it did not, it had 87.
--
-- They are a corrupt mirror, and they are deleted. (If a genuine 2015 generation
-- is wanted later, the authoritative 87-district file is staged at
-- `data/boundaries/british-columbia/prior/` and can be loaded properly.)
--
-- Cause, for the record: Open North's BC *roster* was complete at 93, but 41 of
-- those representative records carried no `related.boundary_url` — so
-- `_constituency_id()` returned None and the guard at `opennorth.py:590` skipped
-- the boundary write AND left the politician's `constituency_id` NULL. One None,
-- both symptoms. Zero orphans is what proves it was never a swallowed 404.
--
-- Measured before writing this migration
-- --------------------------------------
--   authoritative vs held: mean overlap 86.46%, min 12.16%, 30 of 52 below 95%
--   worst: abbotsford-mission 12.16%, surrey-cloverdale 37.54%
-- ⚠ Unlike Ontario, this IS a geometry change and it is the point of the exercise.
-- The 22 districts above 95% are simply ones the 2022 commission barely touched.
--
-- Forward-only. Apply with:
--   docker exec -i sw-db psql -U sw -d sovereignwatch -v ON_ERROR_STOP=1 \
--     < db/migrations/0065_british_columbia_boundary_cutover.sql

BEGIN;

-- Guard: refuse to run if the authoritative load hasn't happened.
DO $$
DECLARE n int;
BEGIN
    SELECT count(*) INTO n
      FROM constituency_boundaries
     WHERE constituency_id LIKE 'british-columbia-electoral-districts/%'
       AND boundaries_version = 'bs11-2023';
    IF n <> 93 THEN
        RAISE EXCEPTION
          'Expected 93 authoritative BC rows, found %. Run '
          '`load-boundaries --jurisdiction british-columbia` first.', n;
    END IF;
END $$;

-- Repoint the roster. Same slug on both sides for the 52 name-stable districts,
-- so this is a pure prefix swap — no lookup, no fuzzy matching. The other 41
-- districts' politicians carry a NULL constituency_id today (that is the defect)
-- and are reattached by the backfill below.
UPDATE politicians
   SET constituency_id = 'british-columbia-electoral-districts/'
                       || split_part(constituency_id, '/', 2)
 WHERE constituency_id LIKE 'british-columbia-electoral-districts-2015-redistribution/%';

UPDATE politician_terms
   SET constituency_id = 'british-columbia-electoral-districts/'
                       || split_part(constituency_id, '/', 2)
 WHERE constituency_id LIKE 'british-columbia-electoral-districts-2015-redistribution/%';

-- ★ Reattach the 41 MLAs who never had a boundary to point at. Matching on the
-- district name is safe here specifically because BC district names are unique
-- within the province and we are scoping to BC provincial rows on both sides.
UPDATE politicians p
   SET constituency_id = b.constituency_id
  FROM constituency_boundaries b
 WHERE p.constituency_id IS NULL
   AND p.is_active
   AND p.level = 'provincial'
   AND p.province_territory = 'BC'
   AND b.level = 'provincial'
   AND b.province_territory = 'BC'
   AND b.boundaries_version = 'bs11-2023'
   AND lower(p.constituency_name) = lower(b.name);

-- Retire the mirror.
DELETE FROM constituency_boundaries
 WHERE constituency_id LIKE 'british-columbia-electoral-districts-2015-redistribution/%';

-- Post-conditions. Any failure rolls the whole thing back.
DO $$
DECLARE bnd int; orphans int; dupes int; attached int;
BEGIN
    SELECT count(*) INTO bnd
      FROM constituency_boundaries
     WHERE level = 'provincial' AND province_territory = 'BC'
       AND effective_from <= CURRENT_DATE
       AND (effective_to IS NULL OR effective_to >= CURRENT_DATE);
    IF bnd <> 93 THEN
        RAISE EXCEPTION 'Expected 93 current BC provincial boundaries, found %', bnd;
    END IF;

    SELECT count(*) INTO orphans
      FROM politicians p
     WHERE p.constituency_id LIKE 'british-columbia-electoral-districts%'
       AND NOT EXISTS (SELECT 1 FROM constituency_boundaries b
                        WHERE b.constituency_id = p.constituency_id);
    IF orphans <> 0 THEN
        RAISE EXCEPTION 'BC cutover left % orphaned politician rows', orphans;
    END IF;

    SELECT count(*) INTO dupes FROM (
        SELECT constituency_id FROM constituency_boundaries
         WHERE level='provincial' AND province_territory='BC'
           AND effective_from <= CURRENT_DATE
           AND (effective_to IS NULL OR effective_to >= CURRENT_DATE)
         GROUP BY 1 HAVING count(*) > 1) d;
    IF dupes <> 0 THEN
        RAISE EXCEPTION 'BC cutover left % duplicated districts', dupes;
    END IF;

    -- Informational: how many of the 93 now resolve to a sitting MLA. Not an
    -- assertion — vacancies and roster-hygiene gaps are legitimate and are not
    -- this migration's problem to fix.
    SELECT count(*) INTO attached
      FROM constituency_boundaries b
     WHERE b.level='provincial' AND b.province_territory='BC'
       AND EXISTS (SELECT 1 FROM politicians p
                    WHERE p.is_active AND p.constituency_id = b.constituency_id);
    RAISE NOTICE 'BC: % of 93 districts resolve to a sitting MLA', attached;
END $$;

COMMIT;

SELECT refresh_map_views();
