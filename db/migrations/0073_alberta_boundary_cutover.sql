-- 0073 — Alberta cutover: retire the mirror, and repair a live 404.
--
-- ✅ Unlike BC/SK/NB/YT, Alberta's held geometry was NOT stale, and that was
-- measured rather than assumed: 87/87 exact, 0 gaps, 0 extras, 0 name drift.
-- Re-measured immediately before this migration against the authoritative file:
-- **99.8715% mean overlap, min 99.5826%, 0 districts below 95%.** Against the
-- 2010 generation it is 81.275% with 29 unmatched, so a Saskatchewan-style
-- silent redraw is positively ruled out, not merely unobserved.
--
-- ⛔ SO WHY TOUCH IT: THE DETAIL ENDPOINT 404s FOR ALL 87 DISTRICTS
-- ----------------------------------------------------------------
-- Alberta is the only jurisdiction where `source_set` and the `constituency_id`
-- prefix disagree:
--
--     source_set       alberta-electoral-districts
--     constituency_id  alberta-electoral-districts-2017/calgary-bow
--
-- The public detail route is `/boundaries/:source_set/:slug`
-- (`routes/public/boundaries.ts`), so a client that lists boundaries and follows
-- the obvious URL asks for `/boundaries/alberta-electoral-districts/calgary-bow`
-- and gets nothing. The list endpoint returns the row; the detail endpoint
-- cannot find it. Aligning both onto the generation-free prefix fixes it and
-- satisfies the convention at the same time.
--
-- Also corrected: `boundaries_version` 'current' -> '2017-commission' (a label
-- that cannot survive a second generation existing), and `effective_from`
-- 2023-01-01 -> 2019-04-16, the 30th general election, being the first date
-- these divisions demonstrably governed anything. ⚠ Marked `needs confirmation`
-- in the dossier: three candidate dates span two years and none is unambiguous.
--
-- ⚠ Known expiry: the 2025-26 commission reported on 2026-03-23 proposing 89
-- divisions. Not enacted; no 89-division layer is published. The vintage-drift
-- half of `check-boundary-coverage` is what should catch that landing, since a
-- count check cannot see a redraw that holds the count.
--
-- Run AFTER `load-boundaries --jurisdiction alberta`.
--
-- Forward-only. Apply with:
--   docker exec -i sw-db psql -U sw -d sovereignwatch -v ON_ERROR_STOP=1 \
--     < db/migrations/0073_alberta_boundary_cutover.sql

BEGIN;

DO $$
DECLARE n int;
BEGIN
    SELECT count(*) INTO n FROM constituency_boundaries
     WHERE constituency_id LIKE 'alberta-electoral-districts/%'
       AND boundaries_version = '2017-commission';
    IF n <> 87 THEN
        RAISE EXCEPTION
          'Expected 87 authoritative AB rows, found %. Run '
          '`load-boundaries --jurisdiction alberta` first.', n;
    END IF;
END $$;

-- Pure prefix swap; the 87 slugs are identical on both sides.
UPDATE politicians
   SET constituency_id = 'alberta-electoral-districts/'
                       || split_part(constituency_id, '/', 2)
 WHERE constituency_id LIKE 'alberta-electoral-districts-2017/%';

UPDATE politician_terms
   SET constituency_id = 'alberta-electoral-districts/'
                       || split_part(constituency_id, '/', 2)
 WHERE constituency_id LIKE 'alberta-electoral-districts-2017/%';

DELETE FROM constituency_boundaries
 WHERE constituency_id LIKE 'alberta-electoral-districts-2017/%';

DO $$
DECLARE bnd int; dupes int; orphans int; mism int; actives int; attached int;
BEGIN
    SELECT count(*) INTO bnd FROM constituency_boundaries
     WHERE level='provincial' AND province_territory='AB'
       AND effective_from <= CURRENT_DATE
       AND (effective_to IS NULL OR effective_to >= CURRENT_DATE);
    IF bnd <> 87 THEN
        RAISE EXCEPTION 'Expected 87 current AB boundaries, found %', bnd;
    END IF;

    SELECT count(*) INTO dupes FROM (
        SELECT constituency_id FROM constituency_boundaries
         WHERE level='provincial' AND province_territory='AB'
           AND effective_from <= CURRENT_DATE
           AND (effective_to IS NULL OR effective_to >= CURRENT_DATE)
         GROUP BY 1 HAVING count(*) > 1) d;
    IF dupes <> 0 THEN
        RAISE EXCEPTION 'AB cutover left % duplicated districts', dupes;
    END IF;

    SELECT count(*) INTO orphans FROM politicians p
     WHERE p.constituency_id LIKE 'alberta-electoral-districts%'
       AND NOT EXISTS (SELECT 1 FROM constituency_boundaries b
                        WHERE b.constituency_id = p.constituency_id);
    IF orphans <> 0 THEN
        RAISE EXCEPTION 'AB cutover left % orphaned politician rows', orphans;
    END IF;

    -- ★ The assertion this migration exists for: the detail route builds its URL
    -- from source_set, so any row whose id does not start with its own
    -- source_set is unreachable by that route.
    SELECT count(*) INTO mism FROM constituency_boundaries
     WHERE level='provincial' AND province_territory='AB'
       AND constituency_id NOT LIKE source_set || '/%';
    IF mism <> 0 THEN
        RAISE EXCEPTION
          '% AB rows still have a constituency_id that does not match their '
          'source_set — the detail endpoint would 404 for them', mism;
    END IF;

    SELECT count(*) INTO actives FROM politicians
     WHERE province_territory='AB' AND level='provincial' AND is_active;
    SELECT count(*) INTO attached FROM politicians
     WHERE province_territory='AB' AND level='provincial' AND is_active
       AND constituency_id IS NOT NULL;
    IF actives <> 87 OR attached <> 87 THEN
        RAISE EXCEPTION
          'Expected 87 active AB MLAs all attached, got % active / % attached',
          actives, attached;
    END IF;

    RAISE NOTICE 'AB: 87 of 87 districts, source_set and constituency_id aligned';
END $$;

COMMIT;

SELECT refresh_map_views();
