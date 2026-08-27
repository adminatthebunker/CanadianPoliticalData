-- 0102 — the two municipal cases 0101's same-set clause could not reach.
--
-- ⚠ 0101 deleted a municipal mirror row only where an authoritative sibling
-- already existed IN THE SAME source_set. That clause is what protected the ~782
-- legitimately un-replaced municipal rows, and it is correct — but it is blind
-- to a cutover that RENAMED the set, which is exactly what 0095 (Toronto) and
-- 0083 (Peel) did. Both were reverted by the 2026-08-23 run and both survived
-- 0101 untouched:
--
--   toronto-wards-2018  25 rows  duplicating toronto-wards      at 100% overlap
--   peel-wards          27 rows  duplicating brampton/mississauga/caledon-wards
--
-- ★ Confirmed as incident damage, not pre-existing: every one of the 52 rows
-- carries `created_at` inside the 2026-08-23 02:00 UTC burst, and all 52 carry
-- `boundary_kind IS NULL` — the mirror's fingerprint. Found geometrically
-- rather than by name, because the naming convention is the thing that broke.
--
-- ⛔ NEITHER ORIGINAL RE-RUNS VERBATIM. 0083's mapping requires
-- `pw.boundary_kind = 'district'` on the Peel side; the re-created rows have no
-- tier at all, so a verbatim re-run maps 0 of 27 and raises on its own
-- assertion. This is the same shape as the trap 0101 documents — a repair keyed
-- on a property the damaged rows do not have. Both maps below accept NULL.
--
-- ⚠ Peel keeps BOTH offices. 18 people sit on Peel Regional Council and 17 of
-- them also sit on a city council: Peel regional seats are filled by ward, so
-- Martin Medeiros really is both a Brampton city councillor and a Peel regional
-- councillor. 0083's fix was never to delete an office — it was to stop two
-- polygons claiming the same ground, which made a point-in-polygon lookup
-- planner-dependent. The regional councillor moves onto the city ward polygon.
--
-- Forward-only. Apply with:
--   docker exec -i sw-db psql -U sw -d sovereignwatch -v ON_ERROR_STOP=1 \
--     < db/migrations/0102_purge_mirror_resurrection_renamed_sets.sql

BEGIN;

-- ── Toronto: re-key 2018 → the generation-free set (0095's shape) ────────
CREATE TEMP TABLE _tor_map ON COMMIT DROP AS
SELECT dup.constituency_id AS dup_id, keep.constituency_id AS keep_id
  FROM constituency_boundaries dup
  JOIN constituency_boundaries keep
    ON keep.source_set = 'toronto-wards'
   AND split_part(keep.constituency_id, '/', 2)
     = split_part(dup.constituency_id, '/', 2)
 WHERE dup.source_set = 'toronto-wards-2018'
   AND dup.boundaries_version = 'current'
   AND dup.boundary_kind IS NULL;

-- ── Peel: regional ward → city ward (0083's shape, NULL-tolerant) ────────
CREATE TEMP TABLE _peel_map ON COMMIT DROP AS
SELECT pw.constituency_id AS dup_id,
       city.constituency_id AS keep_id,
       ST_Area(ST_Intersection(ST_MakeValid(city.boundary), ST_MakeValid(pw.boundary)))
         / ST_Area(ST_MakeValid(pw.boundary)) AS overlap
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
 WHERE pw.source_set = 'peel-wards'
   AND pw.boundaries_version = 'current'
   AND pw.boundary_kind IS NULL;

DO $$
DECLARE t int; p int; worst numeric; outside int;
BEGIN
    SELECT count(*) INTO t FROM _tor_map;
    SELECT count(*), min(overlap) INTO p, worst FROM _peel_map;
    IF t <> 25 THEN RAISE EXCEPTION 'Toronto: mapped % of 25 wards', t; END IF;
    IF p <> 27 THEN RAISE EXCEPTION 'Peel: mapped % of 27 ward rows', p; END IF;

    -- ⛔ 0083's gate, kept: refuse to delete anything that is not a duplicate.
    IF worst < 0.98 THEN
        RAISE EXCEPTION 'Lowest Peel/city overlap is % — these are not the '
          'same wards', round(worst, 4);
    END IF;

    -- The independent witness, same as 0101: all 52 must be incident rows.
    SELECT count(*) INTO outside FROM constituency_boundaries
     WHERE constituency_id IN (SELECT dup_id FROM _tor_map
                               UNION ALL SELECT dup_id FROM _peel_map)
       AND (created_at <  TIMESTAMPTZ '2026-08-23 00:00Z'
         OR created_at >= TIMESTAMPTZ '2026-08-24 00:00Z');
    IF outside <> 0 THEN
        RAISE EXCEPTION '% of the 52 rows predate the incident — they are not '
          'resurrection damage and must not be deleted here', outside;
    END IF;
END $$;

UPDATE politicians p SET constituency_id = m.keep_id, updated_at = now()
  FROM (SELECT dup_id, keep_id FROM _tor_map
        UNION ALL SELECT dup_id, keep_id FROM _peel_map) m
 WHERE p.constituency_id = m.dup_id;

UPDATE politician_terms t SET constituency_id = m.keep_id
  FROM (SELECT dup_id, keep_id FROM _tor_map
        UNION ALL SELECT dup_id, keep_id FROM _peel_map) m
 WHERE t.constituency_id = m.dup_id;

DELETE FROM constituency_boundaries b
 WHERE b.constituency_id IN (SELECT dup_id FROM _tor_map
                             UNION ALL SELECT dup_id FROM _peel_map)
   AND b.boundaries_version = 'current'
   AND b.boundary_kind IS NULL;

DO $$
DECLARE bad int; tor int; peel int;
BEGIN
    SELECT count(*) INTO bad FROM politicians p
     WHERE p.is_active AND p.constituency_id IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM constituency_boundaries b
                        WHERE b.constituency_id = p.constituency_id);
    IF bad <> 0 THEN RAISE EXCEPTION '% members orphaned by the re-key', bad; END IF;

    -- Both councils intact — the point was never to remove an office.
    SELECT count(*) INTO tor FROM politicians
     WHERE is_active AND source_id LIKE '%toronto-city-council%';
    SELECT count(*) INTO peel FROM politicians
     WHERE is_active AND source_id LIKE '%peel-regional-council%';
    IF tor < 25 THEN RAISE EXCEPTION 'Toronto council down to %', tor; END IF;
    IF peel < 18 THEN RAISE EXCEPTION 'Peel regional council down to %', peel; END IF;

    -- ⚠ Toronto's `census-subdivisions/*` municipality polygon lives inside
    -- `toronto-wards-2018` and carries the mayor. It must survive.
    IF NOT EXISTS (SELECT 1 FROM constituency_boundaries
                    WHERE source_set = 'toronto-wards-2018'
                      AND boundary_kind = 'municipality') THEN
        RAISE EXCEPTION 'Toronto mayoral polygon deleted — it was not a ward';
    END IF;

    RAISE NOTICE 'renamed-set resurrection purged: 52 rows, both councils intact';
END $$;

COMMIT;

SELECT refresh_map_views();
