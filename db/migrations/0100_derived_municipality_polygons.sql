-- 0100 — Laval and Sainte-Anne-de-Bellevue: derive the municipality-tier polygon
--        by dissolving their districts, so their MAYORS have somewhere to sit.
--
-- ⛔ THE GAP. Of the 24 Québec municipal sets, exactly two hold no
-- municipality-tier polygon at all: `laval-districts` and
-- `sainte-anne-de-bellevue-districts`. Every other municipality has one, either
-- in its own set or as a `census-subdivisions/<code>` row.
--
-- The mayor attach requires a `boundary_kind = 'municipality'` polygon, so
-- Laval's mayor — the mayor of Québec's third-largest city — resolved to
-- nothing. Not a naming mismatch, not a stale map: there was no row.
--
-- ★ DERIVED, NOT INVENTED, and the distinction is the whole justification.
-- A municipality's electoral districts tile it exactly, so their union IS its
-- extent. Verified before deriving:
--
--   laval-districts                    22 districts  sum 266.8 km²  union 266.8 km²  1 part
--   sainte-anne-de-bellevue-districts   5 districts  sum  11.0 km²  union  10.9 km²  1 part
--
-- Sum equal to union means no overlaps; a single connected part means no holes
-- or islands lost. Laval's published area is 265.95 km² and Sainte-Anne's ~11 —
-- both land on the right number from an independent direction.
--
-- ⚠ PROVENANCE IS STATED, NOT LAUNDERED. These rows are NOT given
-- `census-subdivisions/<code>` ids, which would claim a StatCan origin they do
-- not have. They carry the derived id `<set>/<slug>`, the district file's own
-- authority, and `boundaries_version = '<version>-dissolved'` so the derivation
-- is legible in the data itself rather than only in this comment.
--
-- ⓘ Sainte-Anne-de-Bellevue's districts are the 2021 generation (its council
-- grew from 5 to 6 for 2025 and no publisher ships the new map), so its derived
-- outline is 2021-vintage too. That is fine for a MUNICIPAL boundary — the town's
-- outer limits did not change when its wards were redrawn — and it is why the
-- version label carries the source generation rather than a bare year.
--
-- Forward-only. Apply with:
--   docker exec -i sw-db psql -U sw -d sovereignwatch -v ON_ERROR_STOP=1 \
--     < db/migrations/0100_derived_municipality_polygons.sql

BEGIN;

INSERT INTO constituency_boundaries
    (constituency_id, name, level, province_territory, source_set, authority,
     boundary_kind, boundary, boundary_simple, centroid, area_sqkm,
     boundaries_version, effective_from)
SELECT src.source_set || '/' || cpd_slugify(src.display_name),
       src.display_name,
       'municipal',
       'QC',
       src.source_set,
       src.authority,
       'municipality',
       src.g,
       -- Same simplification the loader applies (SIMPLIFY_TOLERANCE = 0.005).
       ST_Multi(ST_CollectionExtract(ST_MakeValid(ST_Simplify(src.g, 0.005)), 3)),
       ST_Centroid(src.g),
       ST_Area(src.g::geography) / 1000000,
       src.version || '-dissolved',
       src.eff
  FROM (
    SELECT b.source_set,
           CASE b.source_set WHEN 'laval-districts' THEN 'Laval'
                             ELSE 'Sainte-Anne-de-Bellevue' END AS display_name,
           min(b.authority)          AS authority,
           min(b.boundaries_version) AS version,
           min(b.effective_from)     AS eff,
           ST_Multi(ST_CollectionExtract(
             ST_MakeValid(ST_UnaryUnion(ST_Collect(b.boundary))), 3)) AS g
      FROM constituency_boundaries b
     WHERE b.source_set IN ('laval-districts', 'sainte-anne-de-bellevue-districts')
       AND b.boundary_kind = 'district'
     GROUP BY b.source_set
  ) src
ON CONFLICT (constituency_id, boundaries_version) DO NOTHING;

DO $$
DECLARE n int; bad int;
BEGIN
    SELECT count(*) INTO n FROM constituency_boundaries
     WHERE boundary_kind = 'municipality'
       AND source_set IN ('laval-districts', 'sainte-anne-de-bellevue-districts');
    IF n <> 2 THEN
        RAISE EXCEPTION 'Expected 2 derived municipality polygons, found %', n;
    END IF;

    -- ⛔ The derived outline must contain every district it was built from.
    -- A union that lost a part would still look like a plausible polygon.
    SELECT count(*) INTO bad
      FROM constituency_boundaries d
      JOIN constituency_boundaries m
        ON m.source_set = d.source_set AND m.boundary_kind = 'municipality'
     WHERE d.source_set IN ('laval-districts', 'sainte-anne-de-bellevue-districts')
       AND d.boundary_kind = 'district'
       AND NOT ST_Covers(ST_Buffer(m.boundary, 0.00001), d.boundary);
    IF bad <> 0 THEN
        RAISE EXCEPTION
          '% districts are not covered by their derived municipality outline', bad;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM constituency_boundaries
                    WHERE constituency_id = 'laval-districts/laval') THEN
        RAISE EXCEPTION 'The Laval outline was not created';
    END IF;

    RAISE NOTICE 'Derived 2 municipality outlines; re-run '
                 'ingest-qc-municipal-roster to attach the mayors';
END $$;

COMMIT;

SELECT refresh_map_views();
