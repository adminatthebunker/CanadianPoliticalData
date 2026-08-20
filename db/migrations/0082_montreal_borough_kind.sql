-- 0082 — Type Montréal's 18 borough polygons as boroughs.
--
-- ⛔ THE DEFECT: boundary_kind was assigned by STRING MATCHING
-- -----------------------------------------------------------
-- Migration `0061` populated `boundary_kind` with a chain of `LIKE` predicates
-- over `constituency_id`, one of which was:
--
--     WHERE constituency_id LIKE '%-boroughs/%'  ->  'borough'
--
-- That works for Québec City (`quebec-boroughs/…`, 5 rows) and Saguenay
-- (`saguenay-boroughs/…`, 3 rows). Montréal's set is named
-- `montreal-boroughs-and-districts`, so its ids read
-- `montreal-boroughs-and-districts/verdun` — no `-boroughs/` SEGMENT — and all 62
-- non-CSD rows fell through to the catch-all and were typed `district`.
--
-- So the national borough count reads 8 when the truth is 26, and Montréal's
-- three-tier structure (city ⊃ borough ⊃ district) is flattened to two in the
-- only column that records it.
--
-- ★ WHY THE SELECTOR IS THE ROSTER AND NOT GEOMETRY
-- --------------------------------------------------
-- The obvious test — "a borough is a district polygon that CONTAINS other
-- district polygons" — was measured and REJECTED. It finds 28 Montréal
-- candidates: 14 true boroughs plus 14 false positives, each of which contains
-- exactly one other district (adjacent polygons whose ST_PointOnSurface falls
-- inside a neighbour). And it MISSES 4 real boroughs outright — Anjou, Lachine,
-- Outremont and L'Île-Bizard–Sainte-Geneviève have no sub-districts at all, so
-- they contain nothing.
--
-- 14 false positives and 4 false negatives is not a discriminator. What IS exact
-- is the office: a Montréal borough is precisely a polygon with a
-- `Maire d'arrondissement`. Verified — that set is exactly 18, and every one of
-- the 14 containment-positive boroughs is in it.
--
-- ⓘ Montréal has 19 boroughs, not 18. **Ville-Marie's polygon is absent from our
-- data entirely** — no row matches it — which is a genuine gap rather than a
-- typing error. (Its borough mayor is the city mayor ex officio, so the roster
-- could not have revealed it either; its three districts Peter-McGill,
-- Sainte-Marie and Saint-Jacques ARE present.) Left for the Québec re-harvest.
--
-- ⚠ This changes no geometry and no identity — only the tier label. It is a
-- prerequisite for teaching the API that municipal polygons nest, because
-- `boundary_kind` is the only column that names the tiers and today it is wrong
-- for Montréal.
--
-- Forward-only. Apply with:
--   docker exec -i sw-db psql -U sw -d sovereignwatch -v ON_ERROR_STOP=1 \
--     < db/migrations/0082_montreal_borough_kind.sql

BEGIN;

UPDATE constituency_boundaries b
   SET boundary_kind = 'borough', updated_at = now()
 WHERE b.level = 'municipal'
   AND b.source_set = 'montreal-boroughs-and-districts'
   AND b.boundary_kind = 'district'
   AND EXISTS (
     SELECT 1 FROM politicians p
      WHERE p.is_active
        AND p.constituency_id = b.constituency_id
        AND p.elected_office = 'Maire d''arrondissement');

DO $$
DECLARE mtl int; national int; stragglers int;
BEGIN
    SELECT count(*) INTO mtl FROM constituency_boundaries
     WHERE source_set = 'montreal-boroughs-and-districts'
       AND boundary_kind = 'borough';
    IF mtl <> 18 THEN
        RAISE EXCEPTION 'Expected 18 Montréal boroughs, found %', mtl;
    END IF;

    SELECT count(*) INTO national FROM constituency_boundaries
     WHERE level = 'municipal' AND boundary_kind = 'borough';
    IF national <> 26 THEN
        RAISE EXCEPTION
          'Expected 26 municipal boroughs nationally (18 MTL + 5 QC + 3 Saguenay), found %',
          national;
    END IF;

    -- ★ The independent check: after re-typing, NO row still called a
    -- 'district' may contain two or more other districts of its own set. One
    -- containment is adjacency noise; two or more means a tier we have missed.
    -- This is the assertion the containment test earns — as a verifier, which it
    -- is good at, rather than as a selector, which it is bad at.
    SELECT count(*) INTO stragglers FROM (
        SELECT a.constituency_id
          FROM constituency_boundaries a
          JOIN constituency_boundaries c
            ON c.source_set = a.source_set
           AND c.constituency_id <> a.constituency_id
           AND c.boundary_kind = 'district'
           AND ST_Contains(a.boundary, ST_PointOnSurface(c.boundary))
         WHERE a.level = 'municipal' AND a.boundary_kind = 'district'
         GROUP BY 1 HAVING count(*) >= 2) d;
    IF stragglers <> 0 THEN
        RAISE EXCEPTION
          '% municipal rows are still typed district but contain 2+ districts — '
          'an untyped borough tier remains', stragglers;
    END IF;

    RAISE NOTICE 'municipal boroughs: 26 nationally (18 Montréal newly typed); Ville-Marie polygon still absent';
END $$;

COMMIT;
