-- 0123 — Halifax (16) + Cape Breton (12) onto the agencies' own geometry.
--
-- The last two Nova Scotia municipal sets on Open North mirror polygons. Both
-- were reachable the whole time: Cape Breton's districts sat unread inside the
-- province-wide file `nova-scotia-municipal` already loads, excluded by a
-- `row_filter`, and Halifax's own file has been staged with a committed sha256
-- since 2026-08-17.
--
-- ★ WHY THEY NEEDED DIFFERENT SOURCES — the reason the row_filter existed.
-- Cape Breton numbers its districts, so the province-wide file's `CB07` renders
-- as "District 7" and slugs to `cape-breton-districts/district-7`, matching what
-- we hold. Halifax NAMES its districts, and our ids use those names
-- (`halifax-districts/bedford-wentworth`). The province-wide file carries only
-- `HX01`, so folding Halifax in would have renamed all 16 to "District N",
-- re-keyed every id, detached all 16 councillors and thrown away the names.
-- Halifax therefore loads from the city's own file, whose `DISTNAME` slugifies
-- to our held ids exactly — verified against the loader's own `slugify`.
--
-- ⚠ WHAT --compare FOUND, and why it was worth running.
-- Halifax: 15/16 matched, mean 99.88%, min 99.65% — a like-for-like refresh.
-- Cape Breton: several districts moved a LOT — district-9 at 34.55% overlap,
-- district-4 69.20%, district-11 70.68%, 8 below 95%. That is not error, it is
-- N.S. Reg. 150/2023: CBRM was redistricted and our mirror held the pre-2023
-- map. Those five districts were returning the wrong councillor to residents.
--
-- ⛔ ONE ID CHANGES, DELIBERATELY.
--   old: halifax-districts/hammonds-plains-upper-hammonds-plains-lucasville-middle-and-upper-sackville
--   new: halifax-districts/hammonds-plains-upper-hammonds-plains-lucasville-middle-upper-sackville
-- The publisher's name is "… Middle & Upper Sackville"; the mirror expanded `&`
-- to `and`, our slugify drops it. Same class as the `œ` divergence re-keyed in
-- 0098. The authoritative form wins and the single affected councillor is
-- re-linked by `reattach-municipal-roster`, which decides geographically.
--
-- ⛔ THE TWO ROWS THIS MUST NOT TOUCH. `census-subdivisions/1209034` (Halifax)
-- and `census-subdivisions/1217030` (Cape Breton) are filed inside these two
-- source_sets but are `boundary_kind='municipality'` — the whole-municipality
-- polygons that carry the mayor and at-large councillors. NS councils are
-- hybrid, so these are load-bearing, not contamination (ruling A12). The new
-- generation does not replace them and end-dating them would orphan those
-- members. The predicates below are scoped to `boundary_kind = 'district'` for
-- exactly this reason.
--
-- Run AFTER this migration:
--   docker compose run --rm scanner reattach-municipal-roster
--   docker compose run --rm scanner check-boundary-coverage
--   docker compose run --rm scanner boundary-progress
--
-- Forward-only. Apply with:
--   docker exec -i sw-db psql -U sw -d sovereignwatch -v ON_ERROR_STOP=1 \
--     < db/migrations/0123_halifax_cape_breton_cutover.sql

BEGIN;

-- Retire the mirror generation. effective_to is the day before the new map took
-- force (NS municipal election 2024-10-19, ruling A10.4).
UPDATE constituency_boundaries
   SET effective_to = DATE '2024-10-18', updated_at = now()
 WHERE source_set IN ('halifax-districts', 'cape-breton-districts')
   AND boundaries_version = 'current'
   AND boundary_kind = 'district'
   AND effective_to IS NULL;

DO $$
DECLARE
    n_live_hx int; n_live_cb int; n_mirror_live int;
    n_outlines int; n_dup int;
BEGIN
    -- Exactly one live generation per set, at the right size.
    SELECT count(*) INTO n_live_hx FROM constituency_boundaries
     WHERE source_set = 'halifax-districts' AND boundary_kind = 'district'
       AND effective_from <= CURRENT_DATE
       AND (effective_to IS NULL OR effective_to >= CURRENT_DATE);
    IF n_live_hx <> 16 THEN
        RAISE EXCEPTION 'expected 16 live Halifax districts, found %', n_live_hx;
    END IF;

    SELECT count(*) INTO n_live_cb FROM constituency_boundaries
     WHERE source_set = 'cape-breton-districts' AND boundary_kind = 'district'
       AND effective_from <= CURRENT_DATE
       AND (effective_to IS NULL OR effective_to >= CURRENT_DATE);
    IF n_live_cb <> 12 THEN
        RAISE EXCEPTION 'expected 12 live Cape Breton districts, found %', n_live_cb;
    END IF;

    -- No live district row may still be mirror-derived.
    SELECT count(*) INTO n_mirror_live FROM constituency_boundaries
     WHERE source_set IN ('halifax-districts', 'cape-breton-districts')
       AND boundary_kind = 'district' AND authority IS NULL
       AND effective_from <= CURRENT_DATE
       AND (effective_to IS NULL OR effective_to >= CURRENT_DATE);
    IF n_mirror_live <> 0 THEN
        RAISE EXCEPTION '% live district rows still carry no authority', n_mirror_live;
    END IF;

    -- ⛔ The load-bearing CSD outlines must have survived.
    SELECT count(*) INTO n_outlines FROM constituency_boundaries
     WHERE constituency_id IN ('census-subdivisions/1209034','census-subdivisions/1217030')
       AND effective_from <= CURRENT_DATE
       AND (effective_to IS NULL OR effective_to >= CURRENT_DATE);
    IF n_outlines <> 2 THEN
        RAISE EXCEPTION
          'the Halifax/Cape Breton municipality outlines were end-dated (% live) — they carry the mayors',
          n_outlines;
    END IF;

    -- No constituency_id may be live twice (the defect 0101/0112 existed to undo).
    SELECT count(*) INTO n_dup FROM (
        SELECT constituency_id FROM constituency_boundaries
         WHERE source_set IN ('halifax-districts','cape-breton-districts')
           AND effective_from <= CURRENT_DATE
           AND (effective_to IS NULL OR effective_to >= CURRENT_DATE)
         GROUP BY constituency_id HAVING count(*) > 1) d;
    IF n_dup <> 0 THEN
        RAISE EXCEPTION '% constituency_id(s) live in two generations', n_dup;
    END IF;

    RAISE NOTICE '0123 ok: Halifax 16 + Cape Breton 12 authoritative, mirror generation end-dated 2024-10-18, 2 CSD outlines preserved';
END $$;

COMMIT;
