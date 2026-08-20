-- 0094 — Winnipeg: add the councillor for Elmwood – East Kildonan.
--
-- Run AFTER 0093, which loads the ward.
--
-- ★ WHAT THE BOUNDARY LOAD EXPOSED
-- --------------------------------
-- Winnipeg City Council is a mayor plus FIFTEEN councillors. We held fourteen.
-- The Open North mirror never carried Elmwood – East Kildonan at all — not a
-- stale row, an absent one — so the gap was invisible: fourteen councillors on
-- fourteen wards reconciles perfectly with itself.
--
-- Loading the city's own ward file made it visible, because the file has 15
-- wards and names the sitting councillor in each. Cross-checked against our
-- roster: 14 of 15 match by name, and the fifteenth is Emma Durand-Wood.
--
-- ⓘ The same cross-check on the other two prairie cities came back clean —
-- Edmonton 12/12 exact, Calgary 14/14 with two rows differing only in name
-- formatting (`DJ Kelly` vs `Daniel James (DJ) Kelly`). So this is a Winnipeg
-- gap, not a systemic one.
--
-- ⚠ SOURCE TAG. `city-of-winnipeg:` rather than `opennorth:`, deliberately, and
-- for two reasons. First, provenance: this row comes from the city, and the
-- source tag is the audit primitive that makes a batch revertible with a single
-- DELETE. Second, safety: `compare_politicians.detect_retirements` sweeps
-- `opennorth:{set}:%` and deactivates anything the feed omits — which is exactly
-- what it did to a hand-verified Manitoba by-election member three hours after
-- she was added. A row the mirror has never heard of must not live inside the
-- mirror's namespace.
--
-- ⚠ The Open North ingest is retired (0087), so these fields cannot be enriched
-- from it later. Only what the city's file actually publishes is recorded:
-- name, ward, phone, and the council page. No email, no photo, no party —
-- Winnipeg's council is non-partisan.
--
-- Forward-only. Apply with:
--   docker exec -i sw-db psql -U sw -d sovereignwatch -v ON_ERROR_STOP=1 \
--     < db/migrations/0094_winnipeg_elmwood_councillor.sql

BEGIN;

DO $$
DECLARE n int;
BEGIN
    SELECT count(*) INTO n FROM constituency_boundaries
     WHERE constituency_id = 'winnipeg-wards/elmwood-east-kildonan';
    IF n <> 1 THEN
        RAISE EXCEPTION
          'Elmwood – East Kildonan boundary is not loaded — run 0093 first';
    END IF;
END $$;

INSERT INTO politicians
    (source_id, name, first_name, last_name, elected_office, level,
     province_territory, constituency_name, constituency_id, phone,
     official_url, extras, is_active)
VALUES
    ('city-of-winnipeg:winnipeg-city-council:emma-durand-wood',
     'Emma Durand-Wood', 'Emma', 'Durand-Wood', 'Councillor', 'municipal',
     'MB', 'Elmwood—East Kildonan', 'winnipeg-wards/elmwood-east-kildonan',
     '204-986-5195', 'https://winnipeg.ca/node/42612',
     jsonb_build_object(
       'source_url',
       'https://data.winnipeg.ca/api/geospatial/t4cg-yaxs?method=export&format=GeoJSON',
       'representative_set_name', 'Winnipeg City Council'),
     true)
ON CONFLICT (source_id) DO NOTHING;

-- ⚠ `newly_elected` is used rather than inventing a change type: the
-- politician_changes CHECK constrains the vocabulary, and this row IS a sitting
-- member appearing in our data for the first time.
INSERT INTO politician_changes (politician_id, change_type, old_value,
                                new_value, severity)
SELECT id, 'newly_elected', NULL,
       jsonb_build_object('source_id', source_id, 'name', name,
                          'constituency_id', constituency_id,
                          'via', 'migration-0094-winnipeg-ward-file'),
       'info'
  FROM politicians
 WHERE source_id = 'city-of-winnipeg:winnipeg-city-council:emma-durand-wood'
   AND NOT EXISTS (
       SELECT 1 FROM politician_changes c
        WHERE c.politician_id = politicians.id
          AND c.new_value->>'via' = 'migration-0094-winnipeg-ward-file');

DO $$
DECLARE councillors int; unattached int;
BEGIN
    SELECT count(*) INTO councillors FROM politicians
     WHERE is_active AND level = 'municipal' AND province_territory = 'MB'
       AND elected_office = 'Councillor';
    IF councillors <> 15 THEN
        RAISE EXCEPTION
          'Expected 15 Winnipeg councillors after the insert, found %', councillors;
    END IF;

    SELECT count(*) INTO unattached FROM constituency_boundaries b
     WHERE b.source_set = 'winnipeg-wards' AND b.boundary_kind = 'district'
       AND NOT EXISTS (SELECT 1 FROM politicians p
                        WHERE p.is_active AND p.constituency_id = b.constituency_id);
    IF unattached <> 0 THEN
        RAISE EXCEPTION
          '% Winnipeg wards still resolve to no sitting councillor', unattached;
    END IF;

    RAISE NOTICE 'Winnipeg: 15 of 15 wards now resolve to a sitting councillor';
END $$;

COMMIT;

SELECT refresh_map_views();
