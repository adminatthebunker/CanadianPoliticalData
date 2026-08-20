-- 0088 — Montréal: adopt the 2025 electoral districts, retire the 2021 ones.
--
-- ⛔ Our 44 district polygons were the 2021 map, superseded at the 2025-11-02
-- municipal general election. The Québec municipal roster was rebuilt from the
-- Ministère des Affaires municipales results the same day, and only 206 of 396
-- members could be attached — Montréal was the largest block of that gap, with
-- 27 city councillors and 2 borough mayors pointing at nothing.
--
-- The city publishes its own districts on Données Québec under CC-BY:
-- **58 districts**, against 59 in 2021 and the 44 we held. This is a genuine
-- redistribution, and the 44 were never the whole map even in 2021.
--
-- ⚠ THE SET IS MIXED, AND ONLY THE DISTRICTS ARE BEING REPLACED.
-- `montreal-boroughs-and-districts` holds three tiers:
--     1 municipality  (the CSD polygon — the mayor of Montréal)
--    18 borough       (re-typed from 'district' in 0082; the borough mayors)
--    44 district      (the 2021 map — the only rows this migration touches)
-- Deleting by source_set alone would take the boroughs and the city with it.
-- The predicate is `boundary_kind = 'district' AND boundaries_version = 'current'`.
--
-- ⓘ Ville-Marie's borough polygon is still absent — the city publishes borough
-- limits as a separate dataset. Its three districts (Peter-McGill, Sainte-Marie,
-- Saint-Jacques) are present and unaffected.
--
-- Run AFTER `load-boundaries --spec-file .../montreal-districts.py`, then re-run
-- `ingest-qc-municipal-roster` to re-attach against the new geometry.
--
-- Forward-only. Apply with:
--   docker exec -i sw-db psql -U sw -d sovereignwatch -v ON_ERROR_STOP=1 \
--     < db/migrations/0088_montreal_2025_districts.sql

BEGIN;

DO $$
DECLARE n int;
BEGIN
    SELECT count(*) INTO n FROM constituency_boundaries
     WHERE source_set = 'montreal-boroughs-and-districts'
       AND boundaries_version = '2025' AND boundary_kind = 'district';
    IF n <> 58 THEN
        RAISE EXCEPTION
          'Expected 58 Montréal 2025 districts, found %. Run the load first.', n;
    END IF;
END $$;

-- Detach anyone still pointing at a 2021 district that the 2025 map drops, so
-- the delete cannot orphan them. The roster ingest re-attaches by slug after.
UPDATE politicians p SET constituency_id = NULL, updated_at = now()
 WHERE p.constituency_id IN (
   SELECT constituency_id FROM constituency_boundaries
    WHERE source_set = 'montreal-boroughs-and-districts'
      AND boundary_kind = 'district' AND boundaries_version = 'current')
   AND NOT EXISTS (
     SELECT 1 FROM constituency_boundaries b
      WHERE b.constituency_id = p.constituency_id
        AND b.boundaries_version = '2025');

DELETE FROM constituency_boundaries
 WHERE source_set = 'montreal-boroughs-and-districts'
   AND boundary_kind = 'district'
   AND boundaries_version = 'current';

DO $$
DECLARE dist int; boro int; muni int; orphans int; dupes int;
BEGIN
    SELECT count(*) FILTER (WHERE boundary_kind = 'district'),
           count(*) FILTER (WHERE boundary_kind = 'borough'),
           count(*) FILTER (WHERE boundary_kind = 'municipality')
      INTO dist, boro, muni
      FROM constituency_boundaries
     WHERE source_set = 'montreal-boroughs-and-districts'
       AND effective_from <= CURRENT_DATE
       AND (effective_to IS NULL OR effective_to >= CURRENT_DATE);
    IF dist <> 58 OR boro <> 18 OR muni <> 1 THEN
        RAISE EXCEPTION
          'Expected 58 districts / 18 boroughs / 1 municipality, got % / % / %',
          dist, boro, muni;
    END IF;

    SELECT count(*) INTO dupes FROM (
        SELECT constituency_id FROM constituency_boundaries
         WHERE source_set = 'montreal-boroughs-and-districts'
           AND effective_from <= CURRENT_DATE
           AND (effective_to IS NULL OR effective_to >= CURRENT_DATE)
         GROUP BY 1 HAVING count(*) > 1) d;
    IF dupes <> 0 THEN
        RAISE EXCEPTION '% Montréal ids resolve to two live polygons', dupes;
    END IF;

    SELECT count(*) INTO orphans FROM politicians p
     WHERE p.is_active
       AND p.constituency_id LIKE 'montreal-boroughs-and-districts/%'
       AND NOT EXISTS (SELECT 1 FROM constituency_boundaries b
                        WHERE b.constituency_id = p.constituency_id);
    IF orphans <> 0 THEN
        RAISE EXCEPTION 'Montréal cutover left % orphaned members', orphans;
    END IF;

    RAISE NOTICE 'Montréal: 58 districts (2025) + 18 boroughs + 1 city, no orphans';
END $$;

COMMIT;

SELECT refresh_map_views();
