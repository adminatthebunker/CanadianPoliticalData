-- 0090 — Repair 28 self-intersecting Québec municipal borough polygons.
--
-- ⛔ THE FINDING
-- -------------
-- 28 of 1,769 rows in `constituency_boundaries` fail `ST_IsValid`. Every one is
-- `level='municipal'`, `province_territory='QC'`, and a BOROUGH — Montréal's 18,
-- Québec City's 5, Saguenay's 3, and 2 others. Every other row in the table is
-- valid, across all 14 provincial/federal jurisdictions and all 9 other
-- provinces' municipal sets.
--
-- ★ The split is not a coincidence: it is exactly the mirror/loader boundary.
-- `boundary_loader.py` wraps every insert in
-- `ST_Multi(ST_CollectionExtract(ST_MakeValid(ST_UnaryUnion(...)), 3))`, so
-- nothing it loads can be invalid. These 28 arrived through the Open North
-- ingest path, which applied no validity repair at all.
--
-- ⚠ WHY IT MATTERS: a self-intersecting polygon makes GEOS predicates throw
-- rather than return false. `ST_Intersects` between two of these raises
-- `TopologyException: side location conflict`, which is how the defect surfaced
-- — it aborted a council-cohesion query outright. Point-in-polygon happens to
-- tolerate them today, so `/boundaries/lookup` is not currently broken; this is
-- a latent fault being closed, not an outage being fixed.
--
-- ⚠ ONE MATERIAL AREA CHANGE. Repair is area-neutral for 27 of the 28 (deltas
-- under 0.07 km²), because a self-intersection at a single vertex encloses
-- almost nothing. Lachine is the exception: **22.6374 -> 20.7941 km², -8.1%**.
-- That is a self-OVERLAPPING lobe whose area was being counted twice, so the
-- smaller number is the correct one — but it is large enough to be stated rather
-- than absorbed silently, since `area_sqkm` orders the smallest-first lookup.
--
-- All three derived columns are recomputed with the loader's own formulas
-- (`boundary_loader.py:621-628`) so a repaired row is byte-comparable with a
-- loaded one. SIMPLIFY_TOLERANCE = 0.005.
--
-- Forward-only. Apply with:
--   docker exec -i sw-db psql -U sw -d sovereignwatch -v ON_ERROR_STOP=1 \
--     < db/migrations/0090_repair_invalid_municipal_geometry.sql

BEGIN;

CREATE TEMP TABLE _pre_repair ON COMMIT DROP AS
SELECT constituency_id, area_sqkm
  FROM constituency_boundaries
 WHERE NOT ST_IsValid(boundary);

UPDATE constituency_boundaries b
   SET boundary = v.g,
       boundary_simple = ST_Multi(ST_CollectionExtract(ST_MakeValid(
                           ST_Simplify(v.g, 0.005)), 3)),
       centroid = ST_Centroid(v.g),
       area_sqkm = ST_Area(v.g::geography) / 1000000,
       updated_at = now()
  FROM (
    SELECT constituency_id,
           ST_Multi(ST_CollectionExtract(ST_MakeValid(boundary), 3)) AS g
      FROM constituency_boundaries
     WHERE NOT ST_IsValid(boundary)
  ) v
 WHERE b.constituency_id = v.constituency_id;

DO $$
DECLARE invalid int; empty int; worst record;
BEGIN
    SELECT count(*) INTO invalid
      FROM constituency_boundaries WHERE NOT ST_IsValid(boundary);
    IF invalid <> 0 THEN
        RAISE EXCEPTION 'ST_MakeValid left % invalid geometries', invalid;
    END IF;

    -- ⛔ ST_CollectionExtract(...,3) discards any line/point debris MakeValid
    -- emits. If a polygon were degenerate enough to yield NO polygonal part we
    -- would have silently emptied a district.
    SELECT count(*) INTO empty
      FROM constituency_boundaries
     WHERE ST_IsEmpty(boundary) OR area_sqkm IS NULL OR area_sqkm <= 0;
    IF empty <> 0 THEN
        RAISE EXCEPTION '% boundaries are empty or zero-area after repair', empty;
    END IF;

    SELECT p.constituency_id,
           p.area_sqkm AS before_km2,
           b.area_sqkm AS after_km2
      INTO worst
      FROM _pre_repair p
      JOIN constituency_boundaries b USING (constituency_id)
     ORDER BY abs(b.area_sqkm - p.area_sqkm) DESC
     LIMIT 1;
    RAISE NOTICE 'repaired % polygons; largest area change % (% -> % km2)',
        (SELECT count(*) FROM _pre_repair),
        worst.constituency_id, round(worst.before_km2::numeric, 4),
        round(worst.after_km2::numeric, 4);
END $$;

COMMIT;

SELECT refresh_map_views();
