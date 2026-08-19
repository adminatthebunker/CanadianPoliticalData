-- 0066 — Saskatchewan cutover: retire the Open North mirror, adopt Elections SK.
--
-- ★ SK is the most instructive failure in the corpus, and the reason ruling A7
-- ("a full district count proves nothing") exists.
--
-- We held 46 rows against 61 seats — and **all 46 name-matched a currently
-- existing district**, because the 2022 commission renamed 15 districts and
-- redrew the rest *while holding the count at 61*. Nothing about the names or the
-- arithmetic signalled a problem. Only geometry did:
--
--   our 46 rows vs the 2012 shapes : median 0.07% error   -> this is what we hold
--   our 46 rows vs the 2022 shapes : median 11.67% error
--   41 of 46 match 2012 ALONE; ZERO match 2022 alone.
--
-- Measured again against the authoritative file immediately before this
-- migration: mean overlap **70.74%**, minimum **1.63%**, and **42 of 46 below
-- 95%**. `Regina Wascana Plains` overlaps its authoritative counterpart by 1.63%.
--
-- ⛔ Therefore all 61 load as a new generation and all 46 are retired. This is
-- NOT a 15-row backfill. A backfill would leave 41 wrong polygons under a table
-- reading as a complete 61/61 — the exact appearance of correctness that let this
-- survive a general election.
--
-- The 46 are deleted rather than end-dated, for the same reason as BC: they are
-- 2012 geometry wearing 2024 names, which was never a real generation. The
-- authoritative 2012 file is staged at `data/boundaries/saskatchewan/prior/` if
-- genuine history is wanted later.
--
-- Run AFTER `load-boundaries --jurisdiction saskatchewan`.
--
-- Forward-only. Apply with:
--   docker exec -i sw-db psql -U sw -d sovereignwatch -v ON_ERROR_STOP=1 \
--     < db/migrations/0066_saskatchewan_boundary_cutover.sql

BEGIN;

DO $$
DECLARE n int;
BEGIN
    SELECT count(*) INTO n
      FROM constituency_boundaries
     WHERE constituency_id LIKE 'saskatchewan-electoral-districts/%'
       AND boundaries_version = '2022-representation-act';
    IF n <> 61 THEN
        RAISE EXCEPTION
          'Expected 61 authoritative SK rows, found %. Run '
          '`load-boundaries --jurisdiction saskatchewan` first.', n;
    END IF;
END $$;

-- ── Roster spelling corrections ─────────────────────────────────────────────
-- ★ These are OUR errors, not the authority's. Elections Saskatchewan is the
-- naming authority for its own districts, and our roster (sourced from
-- legassembly.sk.ca via a name-derived slug, since SK publishes no stable member
-- ID) drifted on three. Verified individually against the staged shapefile's
-- `Constituen` field; each is a single-character-class difference that a fuzzy
-- match would have papered over silently.
--
-- ⚠ Corrected here rather than special-cased in the loader, because the loader
-- must never rewrite an authoritative source to fit our data — the direction of
-- authority runs the other way.
UPDATE politicians SET constituency_name = 'Saskatoon Silverspring'
 WHERE constituency_name = 'Saskatoon Silver Springs'
   AND level = 'provincial' AND province_territory = 'SK';

UPDATE politicians SET constituency_name = 'Moosomin-Montmartre'
 WHERE constituency_name = 'Moosomin-Monmartre'
   AND level = 'provincial' AND province_territory = 'SK';

UPDATE politicians SET constituency_name = 'Saskatoon Chief Mistawasis'
 WHERE constituency_name = 'Saskatoon Chief Mistawis'
   AND level = 'provincial' AND province_territory = 'SK';

-- ── Re-key and reattach ─────────────────────────────────────────────────────
UPDATE politicians
   SET constituency_id = 'saskatchewan-electoral-districts/'
                       || split_part(constituency_id, '/', 2)
 WHERE constituency_id LIKE 'saskatchewan-electoral-districts-representation-act-2012/%';

UPDATE politician_terms
   SET constituency_id = 'saskatchewan-electoral-districts/'
                       || split_part(constituency_id, '/', 2)
 WHERE constituency_id LIKE 'saskatchewan-electoral-districts-representation-act-2012/%';

-- Attach the MLAs who never had a polygon — the 15 new districts plus the three
-- just respelled. Safe on names here: SK district names are unique within the
-- province and both sides are scoped to SK provincial.
UPDATE politicians p
   SET constituency_id = b.constituency_id
  FROM constituency_boundaries b
 WHERE p.constituency_id IS NULL
   AND p.is_active AND p.level = 'provincial' AND p.province_territory = 'SK'
   AND b.level = 'provincial' AND b.province_territory = 'SK'
   AND b.boundaries_version = '2022-representation-act'
   AND lower(p.constituency_name) = lower(b.name);

-- ⚠ Re-key stale rows whose slug came from the OLD generation and no longer
-- names a district. Left dangling they would fail the orphan assertion below.
UPDATE politicians p
   SET constituency_id = NULL
 WHERE p.constituency_id LIKE 'saskatchewan-electoral-districts/%'
   AND NOT EXISTS (SELECT 1 FROM constituency_boundaries b
                    WHERE b.constituency_id = p.constituency_id);
UPDATE politician_terms t
   SET constituency_id = NULL
 WHERE t.constituency_id LIKE 'saskatchewan-electoral-districts/%'
   AND NOT EXISTS (SELECT 1 FROM constituency_boundaries b
                    WHERE b.constituency_id = t.constituency_id);

DELETE FROM constituency_boundaries
 WHERE constituency_id LIKE 'saskatchewan-electoral-districts-representation-act-2012/%';

DO $$
DECLARE bnd int; orphans int; dupes int; attached int;
BEGIN
    SELECT count(*) INTO bnd FROM constituency_boundaries
     WHERE level='provincial' AND province_territory='SK'
       AND effective_from <= CURRENT_DATE
       AND (effective_to IS NULL OR effective_to >= CURRENT_DATE);
    IF bnd <> 61 THEN
        RAISE EXCEPTION 'Expected 61 current SK provincial boundaries, found %', bnd;
    END IF;

    SELECT count(*) INTO orphans FROM politicians p
     WHERE p.constituency_id LIKE 'saskatchewan-electoral-districts%'
       AND NOT EXISTS (SELECT 1 FROM constituency_boundaries b
                        WHERE b.constituency_id = p.constituency_id);
    IF orphans <> 0 THEN
        RAISE EXCEPTION 'SK cutover left % orphaned politician rows', orphans;
    END IF;

    SELECT count(*) INTO dupes FROM (
        SELECT constituency_id FROM constituency_boundaries
         WHERE level='provincial' AND province_territory='SK'
           AND effective_from <= CURRENT_DATE
           AND (effective_to IS NULL OR effective_to >= CURRENT_DATE)
         GROUP BY 1 HAVING count(*) > 1) d;
    IF dupes <> 0 THEN
        RAISE EXCEPTION 'SK cutover left % duplicated districts', dupes;
    END IF;

    SELECT count(*) INTO attached FROM constituency_boundaries b
     WHERE b.level='provincial' AND b.province_territory='SK'
       AND EXISTS (SELECT 1 FROM politicians p
                    WHERE p.is_active AND p.constituency_id = b.constituency_id);
    RAISE NOTICE 'SK: % of 61 districts resolve to a sitting MLA', attached;
END $$;

COMMIT;

SELECT refresh_map_views();
