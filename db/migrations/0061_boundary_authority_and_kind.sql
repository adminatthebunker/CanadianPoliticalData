-- 0061 — constituency_boundaries: authority keys, tier typing, and the
--        indexes/constraints the boundary rebuild depends on.
--
-- Context: docs/research/boundaries/overview.md (2026-08-18 research phase).
-- Every one of the 1,949 rows in this table was mirrored from Open North's
-- Represent API, which has been down since 2026-08-07. Measurement found 9.15%
-- of Canadian addresses get no provincial answer and 12.61% get a wrong or
-- absent one across the six jurisdictions where authoritative geometry could be
-- checked. This migration is the schema half of the fix; no data is loaded here.
--
-- Five changes, each closing a defect the research proved:
--
--   1. GIST index on `boundary`. Every point-in-polygon in the app uses the full
--      `boundary` column, but only `boundary_simple` and `centroid` are indexed
--      (db/init.sql:200) — so every lookup is a sequential scan over ~1,900
--      MultiPolygons. This is worth doing independently of the rebuild.
--
--   2. `authority` + `authority_district_id`. `constituency_id` is free text with
--      no FK on any of the three tables that carry it, and the politicians↔
--      boundaries join works only because opennorth.py mints the identical string
--      for both. These columns record the ISSUING AGENCY'S OWN key alongside it,
--      so a future re-key has a stable anchor. 23% of the table is already
--      authoritatively keyed (federal rows carry the Elections Canada FED code;
--      census-subdivision rows carry the StatCan CSD code) and is backfilled
--      below — those need metadata, not a re-key.
--
--      ⚠ `boundaries_version` MUST be in the uniqueness constraint. New Brunswick
--      proved it: its statutory `DIST_ID` points at a DIFFERENT district in 27 of
--      49 cases between the 2013 and 2023 orders. An (authority, district_id)
--      key alone would collide across generations and silently overwrite.
--
--   3. `boundary_kind` — three-valued, not two. Quebec has a real third tier:
--      arrondissement (borough) mayors are elected officials present in our own
--      data. A two-valued district/municipality column would have to be reopened
--      immediately. See overview.md § A12.
--
--   4. `name_fr`. Manitoba publishes `ED_French`, Elections Canada ships
--      `ED_NAMEF`, New Brunswick has 20 districts with a distinct French name,
--      and Quebec needs it throughout. We currently discard all of it, which in
--      an officially bilingual country is a defect rather than a simplification.
--
--   5. NOT NULL + defaults on `effective_from` / `boundaries_version`. Migration
--      0021 added both as nullable with no default, so nothing forces a writer to
--      set them — and a NULL `boundaries_version` silently defeats the
--      (constituency_id, boundaries_version) unique constraint, because NULLs
--      don't conflict in Postgres. All 1,949 existing rows already have values,
--      so this tightens without a backfill.
--
-- Forward-only. Apply with:
--   docker exec -i sw-db psql -U sw -d sovereignwatch -v ON_ERROR_STOP=1 \
--     < db/migrations/0061_boundary_authority_and_kind.sql

BEGIN;

-- ── 1. Spatial index on the column PIP actually uses ────────────────────────
-- Note: not CONCURRENTLY — that cannot run inside a transaction, and at 1,949
-- rows the exclusive lock is momentary.
CREATE INDEX IF NOT EXISTS idx_boundaries_geo_full
    ON constituency_boundaries USING GIST (boundary);

-- ── 2. Authority keys ───────────────────────────────────────────────────────
ALTER TABLE constituency_boundaries
    ADD COLUMN IF NOT EXISTS authority             TEXT,
    ADD COLUMN IF NOT EXISTS authority_district_id TEXT;

COMMENT ON COLUMN constituency_boundaries.authority IS
    'Issuing agency slug, e.g. elections-canada, elections-ontario, statcan-csd. '
    'NULL until a jurisdiction is cut over to an authoritative source.';
COMMENT ON COLUMN constituency_boundaries.authority_district_id IS
    'The agency''s own district identifier (Elections Canada FED_NUM, Elections '
    'Ontario ED_ID, StatCan CSD code, ...). Generation-scoped: NB''s DIST_ID '
    'points at a different district in 27 of 49 cases across generations, which '
    'is why boundaries_version is part of the uniqueness constraint.';

-- Partial: rows without an authority yet must not collide with each other.
CREATE UNIQUE INDEX IF NOT EXISTS idx_boundaries_authority_key
    ON constituency_boundaries (authority, authority_district_id, boundaries_version)
    WHERE authority IS NOT NULL AND authority_district_id IS NOT NULL;

-- ── 3. Tier typing ──────────────────────────────────────────────────────────
ALTER TABLE constituency_boundaries
    ADD COLUMN IF NOT EXISTS boundary_kind TEXT;

ALTER TABLE constituency_boundaries
    DROP CONSTRAINT IF EXISTS constituency_boundaries_kind_check;
ALTER TABLE constituency_boundaries
    ADD CONSTRAINT constituency_boundaries_kind_check
    CHECK (boundary_kind IS NULL
           OR boundary_kind IN ('district', 'borough', 'municipality'));

COMMENT ON COLUMN constituency_boundaries.boundary_kind IS
    'district = an electoral district/ward. borough = Quebec arrondissement '
    '(whose mayors are elected officials in our data). municipality = a whole-'
    'municipality or upper-tier polygon. ⚠ A `municipality` row is NOT '
    'contamination: all 115 census-subdivision rows carry sitting officials '
    '(326 nationally, 104 in BC alone where at-large is the statutory default '
    'and no ward polygons exist). Removable only when no officials reference it.';

-- ── 4. French names ─────────────────────────────────────────────────────────
ALTER TABLE constituency_boundaries
    ADD COLUMN IF NOT EXISTS name_fr TEXT;

-- ── 5. Tighten the temporal columns 0021 left loose ─────────────────────────
UPDATE constituency_boundaries
   SET effective_from     = COALESCE(effective_from, DATE '2023-01-01'),
       boundaries_version = COALESCE(boundaries_version, 'current')
 WHERE effective_from IS NULL OR boundaries_version IS NULL;

ALTER TABLE constituency_boundaries
    ALTER COLUMN effective_from     SET NOT NULL,
    ALTER COLUMN boundaries_version SET NOT NULL,
    ALTER COLUMN boundaries_version SET DEFAULT 'current';

-- ── Backfill: the rows that are ALREADY authoritatively keyed ───────────────
-- Federal: constituency_id suffix is the Elections Canada FED code (e.g.
-- .../35079). Verified 342/342 match a FED_NUM exactly with zero extras, so this
-- is a pure split_part with no lookup and no fuzzy matching.
UPDATE constituency_boundaries
   SET authority             = 'elections-canada',
       authority_district_id = split_part(constituency_id, '/', 2),
       boundary_kind         = 'district'
 WHERE level = 'federal'
   AND authority IS NULL
   AND split_part(constituency_id, '/', 2) ~ '^[0-9]+$';

-- Federal rows carry a NULL province_territory; the first two digits of the FED
-- code are the StatCan province code, so it is a pure function of the key.
UPDATE constituency_boundaries
   SET province_territory = CASE left(authority_district_id, 2)
        WHEN '10' THEN 'NL' WHEN '11' THEN 'PE' WHEN '12' THEN 'NS'
        WHEN '13' THEN 'NB' WHEN '24' THEN 'QC' WHEN '35' THEN 'ON'
        WHEN '46' THEN 'MB' WHEN '47' THEN 'SK' WHEN '48' THEN 'AB'
        WHEN '59' THEN 'BC' WHEN '60' THEN 'YT' WHEN '61' THEN 'NT'
        WHEN '62' THEN 'NU' END
 WHERE level = 'federal'
   AND authority = 'elections-canada'
   AND province_territory IS NULL;

-- Municipal whole-municipality polygons: the suffix is the StatCan CSD code.
UPDATE constituency_boundaries
   SET authority             = 'statcan-csd',
       authority_district_id = split_part(constituency_id, '/', 2),
       boundary_kind         = 'municipality'
 WHERE constituency_id LIKE 'census-subdivisions/%'
   AND authority IS NULL;

-- Upper-tier census divisions (Peel, Niagara, Waterloo, Lambton). Three of the
-- four are filed under a `census-subdivisions` source_set despite a
-- `census-divisions/` prefix, so match on the prefix, never on source_set.
UPDATE constituency_boundaries
   SET authority             = 'statcan-cd',
       authority_district_id = split_part(constituency_id, '/', 2),
       boundary_kind         = 'municipality'
 WHERE constituency_id LIKE 'census-divisions/%'
   AND authority IS NULL;

-- Quebec boroughs — real elected tier, mixed into `*-districts` source_sets.
UPDATE constituency_boundaries
   SET boundary_kind = 'borough'
 WHERE constituency_id LIKE '%-boroughs/%'
   AND boundary_kind IS NULL;

-- Everything else with a polygon is an electoral district/ward.
UPDATE constituency_boundaries
   SET boundary_kind = 'district'
 WHERE boundary_kind IS NULL;

COMMIT;

-- ── Verification (run after applying) ───────────────────────────────────────
-- SELECT boundary_kind, count(*) FROM constituency_boundaries GROUP BY 1;
-- SELECT authority, count(*) FROM constituency_boundaries GROUP BY 1 ORDER BY 2 DESC;
-- SELECT count(*) FROM constituency_boundaries WHERE level='federal' AND province_territory IS NULL;  -- expect 0
