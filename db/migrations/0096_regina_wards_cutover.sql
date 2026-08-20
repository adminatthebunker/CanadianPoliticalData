-- 0096 — Regina: adopt the City of Regina's 2024 ward boundaries, retire the
--        mirror geometry.
--
-- Run AFTER `load-boundaries --jurisdiction regina-wards`.
--
-- ★ TWO BLOCKERS CLEARED, NEITHER BY NEW RESEARCH
-- -----------------------------------------------
-- 1. The 403 does not reproduce. `www.regina.ca` was recorded as returning HTTP
--    403 to automated clients, with the browser-UA retry never attempted. It
--    returns **200 to a plain curl**. Whatever the block was, it is gone.
--
-- 2. The publisher was findable all along. The city runs its own ArcGIS Server
--    at `opengis.regina.ca`; the ward layer is reachable from the AGOL item
--    "2024 Ward Boundary Map" in org `32Z5vyJw5sI48UUM` ("City of Regina"):
--    .../CGISViewer/WardsBoundaryReview2023/MapServer/0
--
-- ⛔ How not to look for it, recorded because it will recur across Ontario's 47
-- remaining discoveries: `/sharing/rest/search` on a city's OWN AGOL host is NOT
-- scoped to that city — it queries the global index. Searching
-- `regina.maps.arcgis.com` for "ward" returns Baltimore, Montana and Washington
-- D.C., and the most plausible-looking publisher (`DCGISopendata`) is
-- Washington. Scope with `orgid:` from `/sharing/rest/portals/self`.
--
-- ★ VINTAGE: THE A8.1 TEST, RUN AND SETTLED
-- -----------------------------------------
-- The dossier could not settle this by area comparison — 12.34% error against
-- 2024 and 11.22% against 2020 — and correctly called for polygon intersection
-- per A8.1 rather than a better area metric. Run, with the comparison scoped to
-- Regina's own set:
--
--   held vs 2024 :  mean 74.94%   min 43.05%   10 of 10 below 95%
--   held vs 2020 :  mean 78.77%   min 34.16%    9 of 10 below 95%
--   2024 vs 2020 :  mean ~80%     min 31.97%   (the two known generations)
--
-- ⛔ Our geometry is not the 2024 map and not the 2020 map. A faithful copy
-- scores ~99% — Toronto did 99.70%, Edmonton 99.65%, Winnipeg 99.81%. Ours sits
-- roughly equidistant from both, which is the third-generation signature the
-- dossier suspected. Regina reviewed its wards in 2016 as well.
--
-- ⚠ Identifying WHICH generation ours is would need a file we do not have, and
-- it does not change the decision: the 2024 map is the one in force, adopted at
-- the fixed municipal election of 2024-11-13 (A10.4). Whatever ours is, it is
-- superseded, and its `effective_from = 2023-01-01` was a mirroring artefact
-- rather than a claim about any generation.
--
-- ⚠ LICENCE, STATED PRECISELY. `copyrightText` on the layer is empty, as it is
-- for the Saskatoon candidate we are NOT loading. The difference is categorical
-- and is the reason one is loaded and the other is not: attribution here rests
-- on the HOST — a city-owned domain under an AGOL org named "City of Regina" —
-- not on a metadata field. Saskatoon's candidate is an anonymous item on a
-- shared `services6.arcgis.com` tenant with `orgName: None`, which nothing
-- identifies. Recorded as `unstated-on-layer-city-owned-host`, not as "open".
--
-- ⛔ CRS: the source is EPSG:26913 (NAD83 / UTM 13N) in projected metres, and
-- its `.prj` carries no AUTHORITY clause so the code cannot be sniffed. Declared
-- explicitly; 4326 would have put Regina in the Gulf of Guinea.
--
-- Forward-only. Apply with:
--   docker exec -i sw-db psql -U sw -d sovereignwatch -v ON_ERROR_STOP=1 \
--     < db/migrations/0096_regina_wards_cutover.sql

BEGIN;

DO $$
DECLARE n int;
BEGIN
    SELECT count(*) INTO n FROM constituency_boundaries
     WHERE source_set = 'regina-wards' AND boundaries_version = '2024';
    IF n <> 10 THEN
        RAISE EXCEPTION
          'Expected 10 authoritative Regina wards, found %. Run '
          '`load-boundaries --jurisdiction regina-wards` first.', n;
    END IF;
END $$;

-- Same shape as the other municipal cutovers: only ids the new generation
-- actually replaced, so `census-subdivisions/4706027` (the city outline the
-- mayor sits on) survives.
DELETE FROM constituency_boundaries old
 USING constituency_boundaries new
 WHERE old.source_set = 'regina-wards'
   AND old.boundaries_version = 'current'
   AND new.constituency_id = old.constituency_id
   AND new.source_set = old.source_set
   AND new.boundaries_version = '2024';

DO $$
DECLARE dupes int; wards int; csd int; orphans int;
BEGIN
    SELECT count(*) INTO dupes FROM (
        SELECT constituency_id FROM constituency_boundaries
         WHERE source_set = 'regina-wards'
           AND effective_from <= CURRENT_DATE
           AND (effective_to IS NULL OR effective_to >= CURRENT_DATE)
         GROUP BY 1 HAVING count(*) > 1) d;
    IF dupes <> 0 THEN
        RAISE EXCEPTION 'Regina cutover left % ids live in two generations', dupes;
    END IF;

    SELECT count(*) INTO wards FROM constituency_boundaries
     WHERE source_set = 'regina-wards' AND boundary_kind = 'district';
    IF wards <> 10 THEN
        RAISE EXCEPTION 'Expected 10 live Regina wards, found %', wards;
    END IF;

    SELECT count(*) INTO csd FROM constituency_boundaries
     WHERE source_set = 'regina-wards'
       AND constituency_id LIKE 'census-subdivisions/%';
    IF csd <> 1 THEN
        RAISE EXCEPTION 'The Regina city-outline polygon did not survive';
    END IF;

    SELECT count(*) INTO orphans FROM politicians p
     WHERE p.is_active AND p.constituency_id LIKE 'regina-wards/%'
       AND NOT EXISTS (SELECT 1 FROM constituency_boundaries b
                        WHERE b.constituency_id = p.constituency_id);
    IF orphans <> 0 THEN
        RAISE EXCEPTION 'Regina cutover orphaned % councillors', orphans;
    END IF;

    RAISE NOTICE 'Regina: 2024 ward boundaries adopted, mirror generation retired';
END $$;

COMMIT;

SELECT refresh_map_views();
