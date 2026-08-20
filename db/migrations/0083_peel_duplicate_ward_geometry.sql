-- 0083 — Peel: remove 27 duplicated ward polygons, keep both offices.
--
-- ⛔ THE DEFECT IS DUPLICATED GEOMETRY, NOT DUPLICATED PEOPLE
-- -----------------------------------------------------------
-- `peel-wards` holds a full copy of every ward in Brampton, Caledon and
-- Mississauga alongside the city sets that already hold them. Measured overlap
-- against the city equivalent: **1.0000 for all 16 Brampton and Caledon wards**
-- and 0.9869-0.9996 for the 11 Mississauga wards (generalisation differences
-- only). 27 polygons, every one redundant.
--
-- ★ But the POLITICIANS are not redundant, and deleting them would be wrong.
-- 18 people sit on `peel-regional-council` and 17 of them also sit on a city
-- council — because that is how Peel Region works. Martin Medeiros is genuinely
-- both a Brampton city councillor and a Peel regional councillor; John Kovac is
-- both for Mississauga. Two rows for two real offices is correct modelling, and
-- an earlier read of this set as "duplicated wholesale" would have destroyed it.
--
-- So: re-point the regional councillors at the CITY ward polygon — which is
-- their actual constituency, since Peel regional seats are filled by ward — and
-- drop the duplicate geometry.
--
-- ⚠ The four non-ward rows in this set are NOT duplicates and stay:
--     census-divisions/3521        Peel Region      -> the Regional Chair
--     census-subdivisions/3521005  Mississauga  \
--     census-subdivisions/3521010  Brampton      >  the three mayors
--     census-subdivisions/3521024  Caledon      /
--
-- ── Why this also fixes a live lookup bug ───────────────────────────────────
-- `lookupBoundariesAtPoint` picks the smallest polygon per level. A Mississauga
-- address matched BOTH `mississauga-wards/ward-4` and `peel-wards/mississauga-
-- ward-4` at 12.1 km² each, and `ORDER BY area_sqkm` cannot break a tie between
-- two rows of the same size — so which `constituency_id` a caller received was
-- planner-dependent and could change between identical requests. Removing the
-- duplicate removes the tie at its source.
--
-- ⓘ NOT DONE HERE: Whitby's 4 regional councillors sit on the CSD polygon while
-- 4 ward polygons exist. It looks like the same defect but it is not fixable the
-- same way — all four carry `constituency_name = 'Whitby'`, so nothing in our
-- data says which ward each represents, and Peel only works because its names
-- read "Mississauga Ward 4". Assigning them would be invention. Deferred to the
-- Ontario roster pass after the 2026-10-26 election.
--
-- Forward-only. Apply with:
--   docker exec -i sw-db psql -U sw -d sovereignwatch -v ON_ERROR_STOP=1 \
--     < db/migrations/0083_peel_duplicate_ward_geometry.sql

BEGIN;

-- Snapshot the council BEFORE touching anything: the post-condition should
-- assert that nobody was lost, not that the council is a size I guessed. (It is
-- 22, not the 18 I first assumed — the extra four are the Regional Chair and the
-- three city mayors, who sit on the upper-tier polygons rather than on wards.)
CREATE TEMP TABLE _peel_before ON COMMIT DROP AS
SELECT count(*) AS n FROM politicians
 WHERE is_active AND source_id LIKE '%peel-regional-council%';

CREATE TEMP TABLE _peel_map ON COMMIT DROP AS
SELECT pw.constituency_id AS dup_id,
       city.constituency_id AS keep_id,
       ST_Area(ST_Intersection(city.boundary, pw.boundary))
         / ST_Area(pw.boundary) AS overlap
  FROM constituency_boundaries pw
  CROSS JOIN LATERAL (
      SELECT regexp_replace(split_part(pw.constituency_id, '/', 2),
                            '-ward-.*', '') AS city_slug,
             regexp_replace(split_part(pw.constituency_id, '/', 2),
                            '^(brampton|mississauga|caledon)-ward-', '') AS wardno
  ) parts
  JOIN constituency_boundaries city
    ON city.source_set = parts.city_slug || '-wards'
   AND city.boundary_kind = 'district'
   AND split_part(city.constituency_id, '/', 2) = 'ward-' || parts.wardno
 WHERE pw.source_set = 'peel-wards' AND pw.boundary_kind = 'district';

DO $$
DECLARE n int; worst numeric;
BEGIN
    SELECT count(*), min(overlap) INTO n, worst FROM _peel_map;
    IF n <> 27 THEN
        RAISE EXCEPTION
          'Expected all 27 Peel ward rows to map to a city equivalent, mapped %', n;
    END IF;
    -- ⛔ Refuse to delete anything that is not actually a duplicate.
    IF worst < 0.98 THEN
        RAISE EXCEPTION
          'Lowest Peel/city overlap is %, below the 0.98 duplicate threshold — '
          'these are not the same wards', round(worst, 4);
    END IF;
END $$;

UPDATE politicians p
   SET constituency_id = m.keep_id, updated_at = now()
  FROM _peel_map m
 WHERE p.constituency_id = m.dup_id;

UPDATE politician_terms t
   SET constituency_id = m.keep_id
  FROM _peel_map m
 WHERE t.constituency_id = m.dup_id;

DELETE FROM constituency_boundaries b
 USING _peel_map m
 WHERE b.constituency_id = m.dup_id;

DO $$
DECLARE remaining int; orphans int; ties int; peel_people int;
BEGIN
    SELECT count(*) INTO remaining FROM constituency_boundaries
     WHERE source_set = 'peel-wards';
    IF remaining <> 4 THEN
        RAISE EXCEPTION
          'Expected 4 rows left in peel-wards (region + 3 mayors), found %',
          remaining;
    END IF;

    SELECT count(*) INTO orphans FROM politicians p
     WHERE p.is_active AND p.constituency_id IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM constituency_boundaries b
                        WHERE b.constituency_id = p.constituency_id);
    IF orphans <> 2 THEN
        -- ⚠ 2 is the expected residue: fort-erie-wards/ward-2 and /ward-4, the
        -- only orphans in the table and a separate fix. Anything else means this
        -- migration created one.
        RAISE EXCEPTION
          'Expected exactly 2 pre-existing orphans (Fort Erie), found % — this '
          'migration orphaned someone', orphans;
    END IF;

    -- ★ No two municipal district polygons may still be near-identical in both
    -- shape and size; that is the condition that makes a smallest-first pick
    -- non-deterministic.
    SELECT count(*) INTO ties FROM constituency_boundaries a
      JOIN constituency_boundaries b
        ON b.constituency_id > a.constituency_id
       AND b.level = 'municipal' AND b.boundary_kind = 'district'
       AND ST_Intersects(a.boundary, b.boundary)
       AND ST_Area(ST_Intersection(a.boundary, b.boundary))
             / least(ST_Area(a.boundary), ST_Area(b.boundary)) >= 0.98
       AND ST_Area(a.boundary) / ST_Area(b.boundary) BETWEEN 0.98 AND 1.02
     WHERE a.level = 'municipal' AND a.boundary_kind = 'district';
    IF ties <> 0 THEN
        RAISE EXCEPTION
          '% pairs of municipal district polygons are still near-identical — a '
          'smallest-first lookup remains planner-dependent between them', ties;
    END IF;

    -- Both offices survive.
    SELECT count(*) INTO peel_people FROM politicians
     WHERE is_active AND source_id LIKE '%peel-regional-council%';
    IF peel_people <> (SELECT n FROM _peel_before) THEN
        RAISE EXCEPTION
          'Peel regional council changed size: % before, % after — this '
          'migration must move attachments, never remove members',
          (SELECT n FROM _peel_before), peel_people;
    END IF;

    RAISE NOTICE 'Peel: 27 duplicate ward polygons removed, % council members intact, 18 re-pointed at their city wards', peel_people;
END $$;

COMMIT;

SELECT refresh_map_views();
