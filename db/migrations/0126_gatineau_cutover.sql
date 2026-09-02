-- 0126 — Gatineau, 19 districts, onto the city's own geometry.
--
-- Run AFTER: load-boundaries --jurisdiction gatineau-districts
--
-- ★ The one set in this tranche that was NOT a redraw. --compare:
--
--     authoritative=19 held=19 matched=19
--     mean_overlap=98.9087% min=96.0596% below_95%=0
--     lowest: hull-wright 96.06%, parc-de-la-montagne-saint-raymond 96.54%
--
-- Zero districts below 95%, against 4 for Trois-Rivières, 8 for Lévis and 3 for
-- Saguenay in 0125. Gatineau's 2025 map is materially the map we already held,
-- and the load is a provenance upgrade rather than a correction. ⚠ Recorded
-- explicitly because the honest reading of a high overlap is usually "this
-- proves nothing" — here it is the finding, and it is only trustworthy because
-- the SAME measurement flagged four sibling cities as genuinely moved.
--
-- No re-key: all 19 ids matched name-for-name.
--
-- ⛔ `census-subdivisions/2481017` — Gatineau's municipality outline, carrying
-- the mayor — is not replaced by the new generation and must survive. The
-- predicate is scoped to boundary_kind='district'.
--
-- Date 2025-11-02 (Québec municipal general election, ruling A10.4); old
-- generation end-dated the day before.
--
-- Forward-only. Apply with:
--   docker exec -i sw-db psql -U sw -d sovereignwatch -v ON_ERROR_STOP=1 \
--     < db/migrations/0126_gatineau_cutover.sql

BEGIN;

DO $$
DECLARE n int;
BEGIN
    SELECT count(*) INTO n FROM constituency_boundaries
     WHERE source_set = 'gatineau-districts' AND boundaries_version = '2025'
       AND boundary_kind = 'district';
    IF n <> 19 THEN
        RAISE EXCEPTION 'Expected 19 authoritative Gatineau districts, found %. '
                        'Run load-boundaries --jurisdiction gatineau-districts first.', n;
    END IF;
END $$;

UPDATE constituency_boundaries
   SET effective_to = DATE '2025-11-01', updated_at = now()
 WHERE source_set = 'gatineau-districts'
   AND boundaries_version = 'current'
   AND boundary_kind = 'district'
   AND effective_to IS NULL;

DO $$
DECLARE n int;
BEGIN
    SELECT count(*) INTO n FROM constituency_boundaries
     WHERE source_set = 'gatineau-districts' AND boundary_kind = 'district'
       AND effective_from <= CURRENT_DATE
       AND (effective_to IS NULL OR effective_to >= CURRENT_DATE);
    IF n <> 19 THEN
        RAISE EXCEPTION 'expected 19 live Gatineau districts, found %', n;
    END IF;

    SELECT count(*) INTO n FROM constituency_boundaries
     WHERE source_set = 'gatineau-districts' AND boundary_kind = 'district'
       AND authority IS NULL
       AND effective_from <= CURRENT_DATE
       AND (effective_to IS NULL OR effective_to >= CURRENT_DATE);
    IF n <> 0 THEN
        RAISE EXCEPTION '% live Gatineau districts still carry no authority', n;
    END IF;

    SELECT count(*) INTO n FROM constituency_boundaries
     WHERE constituency_id = 'census-subdivisions/2481017'
       AND effective_from <= CURRENT_DATE
       AND (effective_to IS NULL OR effective_to >= CURRENT_DATE);
    IF n <> 1 THEN
        RAISE EXCEPTION 'Gatineau municipality outline was end-dated — it carries the mayor';
    END IF;

    SELECT count(*) INTO n FROM politicians p
     WHERE p.is_active AND p.constituency_id IS NOT NULL
       AND NOT EXISTS (
         SELECT 1 FROM constituency_boundaries b
          WHERE b.constituency_id = p.constituency_id
            AND b.effective_from <= CURRENT_DATE
            AND (b.effective_to IS NULL OR b.effective_to >= CURRENT_DATE));
    IF n <> 0 THEN
        RAISE EXCEPTION '% sitting member(s) orphaned corpus-wide', n;
    END IF;

    RAISE NOTICE '0126 ok: Gatineau 19 authoritative, outline preserved, 0 orphans';
END $$;

COMMIT;
