-- 0113 — Guelph: replace the pre-2022 mirror geometry with the city's own map.
--
-- ★ A GEOMETRY REPLACEMENT, NOT A PROVENANCE UPGRADE — the third in Ontario
-- after Kawartha Lakes and the ward-count repairs. Measured overlap against the
-- authoritative map: **Ward 2 55.82%, Ward 1 68.21%, Ward 5 78.60%, Ward 3
-- 84.43%, Ward 6 90.53%**. The mirror has been serving Guelph's PRE-2022
-- boundaries, so addresses across large parts of the city — nearly half of
-- Ward 2 — have been resolving to the wrong councillor.
--
-- ⛔ GUELPH WAS HELD BACK FROM 0109 ON PURPOSE, and this is why that was right.
-- Its councillor attributes are the current 2022-2026 council, which makes the
-- layer LOOK current, but attributes update independently of geometry — exactly
-- how Calgary's perfect district count concealed a superseded map (0093). The
-- count is 6 before and after, so ruling A7 applies and nothing about the count,
-- the names or the roster could have told these two maps apart.
--
-- ★ Resolved by rendering the staged geometry against the City of Guelph's OWN
-- published "City of Guelph Ward Map", dated May 2022 on its face. Every ward
-- matches, including Ward 2's narrow northern spur, Ward 5's stepped southern
-- edge and Ward 6's angled western boundary. That is what dates it — not the
-- layer's metadata, not its attributes.
--
-- In-force 2022-10-24: after roughly thirty years unchanged, Council approved
-- an adjusted six-ward map for the 2022 election (the legislated deadline for
-- passing the by-law was 2021-12-31). The prior adjustment was 2006, which is
-- what the mirror was still carrying.
--
-- ⚠ Held rows are named "Ward N"; the source names them for saints —
-- St. Patrick's, St. George's, St. John's, St. David's, St. Andrew's,
-- St. James'. The spec builds the label from WARD and drops the saints' names,
-- because adopting them would re-key all six constituency_ids and detach the
-- council. A nicer display name is not worth an orphaned roster.
--
-- Forward-only. Apply with:
--   docker exec -i sw-db psql -U sw -d sovereignwatch -v ON_ERROR_STOP=1 \
--     < db/migrations/0113_guelph_2022_ward_map.sql

BEGIN;

DO $$
DECLARE auth int;
BEGIN
    SELECT count(*) INTO auth FROM constituency_boundaries
     WHERE source_set = 'guelph-wards' AND boundaries_version = '2022'
       AND boundary_kind = 'district';
    IF auth <> 6 THEN
        RAISE EXCEPTION 'Expected 6 authoritative Guelph wards, found % — run '
          'the load first', auth;
    END IF;
END $$;

DELETE FROM constituency_boundaries
 WHERE source_set = 'guelph-wards'
   AND boundaries_version = 'current'
   AND boundary_kind = 'district';

DO $$
DECLARE live int; csd int; orphans int; n_overlap int; total numeric; muni numeric;
BEGIN
    SELECT count(*) INTO live FROM constituency_boundaries
     WHERE source_set = 'guelph-wards' AND boundary_kind = 'district'
       AND effective_from <= CURRENT_DATE
       AND (effective_to IS NULL OR effective_to >= CURRENT_DATE);
    IF live <> 6 THEN
        RAISE EXCEPTION 'Guelph has % live wards, expected 6', live;
    END IF;

    -- ★ The wards must cover the city, the check that caught Kawartha Lakes.
    -- Keyed on a polygon this migration does not touch.
    SELECT sum(area_sqkm) INTO total FROM constituency_boundaries
     WHERE source_set = 'guelph-wards' AND boundary_kind = 'district'
       AND effective_from <= CURRENT_DATE;
    SELECT area_sqkm INTO muni FROM constituency_boundaries
     WHERE constituency_id = 'census-subdivisions/3523008';
    IF muni IS NOT NULL AND abs(total - muni) / muni > 0.02 THEN
        RAISE EXCEPTION 'Guelph wards sum to % km² against a city of % km²',
                        round(total), round(muni);
    END IF;

    SELECT count(*) INTO csd FROM constituency_boundaries
     WHERE source_set = 'guelph-wards' AND boundary_kind = 'municipality';
    IF csd <> 1 THEN RAISE EXCEPTION 'Guelph municipality polygon lost'; END IF;

    -- No generation may overlap another, at any date (the 0112 invariant).
    SELECT count(*) INTO n_overlap FROM constituency_boundaries a
      JOIN constituency_boundaries b
        ON b.source_set = a.source_set
       AND b.boundaries_version <> a.boundaries_version
       AND a.boundary_kind = 'district' AND b.boundary_kind = 'district'
       AND a.effective_from <= coalesce(b.effective_to, DATE '9999-12-31')
       AND b.effective_from <= coalesce(a.effective_to, DATE '9999-12-31')
     WHERE a.source_set = 'guelph-wards';
    IF n_overlap <> 0 THEN
        RAISE EXCEPTION 'Guelph left % overlapping generation pairs', n_overlap;
    END IF;

    SELECT count(*) INTO orphans FROM politicians p
     WHERE p.is_active AND p.constituency_id IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM constituency_boundaries b
                        WHERE b.constituency_id = p.constituency_id);
    IF orphans <> 0 THEN
        RAISE EXCEPTION 'cutover orphaned % sitting members', orphans;
    END IF;

    RAISE NOTICE 'Guelph: on the 2022 map, pre-2022 mirror geometry retired';
END $$;

COMMIT;

SELECT refresh_map_views();
