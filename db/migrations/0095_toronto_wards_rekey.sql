-- 0095 — Toronto: retire `toronto-wards-2018` in favour of the generation-free
--        `toronto-wards`, loaded from the city's own CKAN dataset.
--
-- Run AFTER `load-boundaries --jurisdiction toronto-wards`.
--
-- ⓘ NOT A VINTAGE FIX. Measured against the city's file, 25 of 25 wards match at
-- mean 99.70%, minimum 99.37%, none below 95%. The geometry we held was right.
-- What was wrong is everything around it.
--
-- ★ 1. THE GENERATION WAS IN THE SET NAME. `toronto-wards-2018` puts the
-- generation in `source_set`, which rule 5 exists to prevent and which the NB
-- and BC provincial cutovers had to unpick for the same reason: the public URL
-- is `/boundaries/:source_set/:slug`, so a future ward-model change would mint a
-- second set and a second URL for the same city rather than a second version of
-- one set. Toronto's ward model has been changed by statute once already and
-- litigated to the Supreme Court, so this is not a hypothetical.
--
-- ⛔ 2. THE IN-FORCE DATE WAS AN ARTEFACT. Every held row carried
-- `effective_from = 2023-01-01`, the Open North mirroring default, which is not
-- a fact about Toronto. Nor is the file's own `DATE_EFFECTIVE` of
-- 2018-08-07T14:11:06 — that is a GIS record-creation timestamp, and it PRECEDES
-- the Royal Assent of the statute that created the 25-ward model (Better Local
-- Government Act, 2018, S.O. 2018 c. 11, assented 2018-08-14). A metadata date
-- that predates the law it reflects is A2 in miniature.
--
-- Per A10.4: 2018-10-22, the election these wards first governed.
--
-- ⚠ `DATE_EXPIRY = 3000-01-01` in the source is a sentinel, not a date, and is
-- deliberately not carried into `effective_to`.
--
-- 3. No authority and no licence note. Now `city-of-toronto`, licence recorded
-- as unspecified — CKAN reports "License not specified" for this dataset, which
-- is a fact worth storing rather than a blank.
--
-- ⚠ The `census-subdivisions/3520005` row (Toronto's city outline, which the
-- mayor sits on) moves with them. It is not superseded by a ward file and is not
-- contamination — it is the municipality TIER, and the lookup now returns the
-- tiers separately.
--
-- Forward-only. Apply with:
--   docker exec -i sw-db psql -U sw -d sovereignwatch -v ON_ERROR_STOP=1 \
--     < db/migrations/0095_toronto_wards_rekey.sql

BEGIN;

DO $$
DECLARE n int;
BEGIN
    SELECT count(*) INTO n FROM constituency_boundaries
     WHERE source_set = 'toronto-wards' AND boundaries_version = '2018';
    IF n <> 25 THEN
        RAISE EXCEPTION
          'Expected 25 authoritative Toronto wards, found %. Run '
          '`load-boundaries --jurisdiction toronto-wards` first.', n;
    END IF;
END $$;

-- ── 1. Move the roster onto the generation-free ids ─────────────────────────
UPDATE politicians
   SET constituency_id = 'toronto-wards/' || split_part(constituency_id, '/', 2),
       updated_at = now()
 WHERE constituency_id LIKE 'toronto-wards-2018/%';

UPDATE politician_terms
   SET constituency_id = 'toronto-wards/' || split_part(constituency_id, '/', 2)
 WHERE constituency_id LIKE 'toronto-wards-2018/%';

-- ── 2. Carry the city-outline row across, keeping its own id ────────────────
UPDATE constituency_boundaries
   SET source_set = 'toronto-wards'
 WHERE source_set = 'toronto-wards-2018'
   AND constituency_id LIKE 'census-subdivisions/%';

-- ── 3. Retire the mirror generation ─────────────────────────────────────────
DELETE FROM constituency_boundaries
 WHERE source_set = 'toronto-wards-2018';

DO $$
DECLARE leftover int; wards int; orphans int; attached int;
BEGIN
    SELECT count(*) INTO leftover FROM constituency_boundaries
     WHERE source_set = 'toronto-wards-2018'
        OR constituency_id LIKE 'toronto-wards-2018/%';
    IF leftover <> 0 THEN
        RAISE EXCEPTION 'toronto-wards-2018 still has % rows', leftover;
    END IF;

    SELECT count(*) INTO wards FROM constituency_boundaries
     WHERE source_set = 'toronto-wards' AND boundary_kind = 'district';
    IF wards <> 25 THEN
        RAISE EXCEPTION 'Expected 25 live Toronto wards, found %', wards;
    END IF;

    SELECT count(*) INTO orphans FROM politicians p
     WHERE p.is_active AND p.constituency_id LIKE 'toronto-wards%'
       AND NOT EXISTS (SELECT 1 FROM constituency_boundaries b
                        WHERE b.constituency_id = p.constituency_id);
    IF orphans <> 0 THEN
        RAISE EXCEPTION 'Toronto re-key orphaned % officials', orphans;
    END IF;

    SELECT count(*) INTO attached FROM constituency_boundaries b
     WHERE b.source_set = 'toronto-wards' AND b.boundary_kind = 'district'
       AND EXISTS (SELECT 1 FROM politicians p
                    WHERE p.is_active AND p.constituency_id = b.constituency_id);
    RAISE NOTICE 'Toronto: % of 25 wards resolve to a sitting councillor', attached;
END $$;

COMMIT;

SELECT refresh_map_views();
