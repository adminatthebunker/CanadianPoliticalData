-- 0099 — Laval and Ville de Québec: adopt the 2025 district maps, retire the
--        2021 generation the Open North mirror left behind.
--
-- Run AFTER `load-boundaries` for `laval-districts` and `quebec-city-districts`.
--
-- ★ BOTH CITIES REDISTRICTED FOR 2025-11-02 AND WE NEVER PICKED IT UP
-- --------------------------------------------------------------------
-- Laval 20 -> 22 districts, Québec 19 -> 21. Measured against the cities' own
-- CC-BY files, scoped to each city's set:
--
--   Laval   15 matched, mean 89.60%, min 67.15%, 10 of 15 below 95%
--   Québec  16 matched, mean 93.76%, min 60.62%,  3 of 16 below 95%
--
-- ⛔ LAVAL: seven districts appear and five disappear.
--   new      champfleury, duvernay, fabreville-sud, labord-a-plouffe,
--            le-carrefour, pont-viau, renaud-coursol
--   retired  concorde-bois-de-boulogne, duvernay-pont-viau, fabreville,
--            renaud, val-des-arbres
--
-- ★ The seven new names are EXACTLY the seven Laval councillors that could not
-- attach. The roster comes from MAMH and the map from the city — two different
-- bodies, agreeing. That is about as strong as source confirmation gets.
--
-- ⛔ QUÉBEC IS SUBTLER, AND THE SUBTLETY IS THE WHOLE MIGRATION. Only TWO of its
-- five "new" districts are new. The other three are the same district under a
-- name that now carries its ARTICLE:
--
--   chute-montmorency-seigneurial  ->  la-chute-montmorency-seigneurial
--   plateau                        ->  le-plateau
--   pointe-de-sainte-foy           ->  la-pointe-de-sainte-foy
--
-- Adopting the article is right — the city writes it and so does MAMH, so this
-- aligns both publishers — but it changes three ids. Left alone, the old
-- article-less rows would sit beside the new ones and every point in those three
-- districts would return two answers, with the roster still resolving and
-- nothing looking wrong. That is the `duplicate-generation` failure mode.
--
-- ⚠ SCOPED TO DISTRICTS. `quebec-districts` also holds Québec's five BOROUGH
-- polygons (`quebec-boroughs/…` ids) and the city's `census-subdivisions` outline
-- — nine of the rows the comparison reports as "we hold, authority does not". A
-- district file does not supersede a borough, and a blanket delete of the
-- superseded generation would take all nine.
--
-- ⚠ Roster rows on retired districts are NULLED, not left dangling. Re-run
-- `ingest-qc-municipal-roster` after this: the attach is idempotent and its
-- fallback handles the article difference, so those members re-derive onto the
-- 2025 districts.
--
-- ⓘ Longueuil was investigated and DELIBERATELY NOT INCLUDED. Its Données Québec
-- resource is dated 2024-03-01 and holds 15 districts — byte-for-byte the same
-- district set we already have, while its roster shows a 2025 redraw. The
-- publisher has not shipped the new map, so there is nothing to load; its six
-- unattached councillors stay unattached rather than being forced onto a
-- superseded map.
--
-- Forward-only. Apply with:
--   docker exec -i sw-db psql -U sw -d sovereignwatch -v ON_ERROR_STOP=1 \
--     < db/migrations/0099_laval_quebec_2025_districts.sql

BEGIN;

DO $$
DECLARE l int; q int;
BEGIN
    SELECT count(*) INTO l FROM constituency_boundaries
     WHERE source_set = 'laval-districts' AND boundaries_version = '2025';
    SELECT count(*) INTO q FROM constituency_boundaries
     WHERE source_set = 'quebec-districts' AND boundaries_version = '2025'
       AND boundary_kind = 'district';
    IF l <> 22 OR q <> 21 THEN
        RAISE EXCEPTION
          'Expected Laval 22 / Québec 21 authoritative districts, found % / %. '
          'Run both loads first.', l, q;
    END IF;
END $$;

-- ── 1. Detach members from districts about to be retired ────────────────────
-- Do this BEFORE the delete: the attach passes only fill NULLs, so a member left
-- pointing at a deleted id would be an orphan the re-run cannot repair.
UPDATE politicians p
   SET constituency_id = NULL, updated_at = now()
 WHERE p.is_active AND p.level = 'municipal'
   AND p.constituency_id IN (
       SELECT old.constituency_id FROM constituency_boundaries old
        WHERE old.source_set IN ('laval-districts', 'quebec-districts')
          AND old.boundary_kind = 'district'
          AND old.boundaries_version = 'current'
          AND NOT EXISTS (SELECT 1 FROM constituency_boundaries new
                           WHERE new.constituency_id = old.constituency_id
                             AND new.boundaries_version = '2025'));

UPDATE politician_terms t
   SET constituency_id = NULL
 WHERE t.constituency_id IN (
       SELECT old.constituency_id FROM constituency_boundaries old
        WHERE old.source_set IN ('laval-districts', 'quebec-districts')
          AND old.boundary_kind = 'district'
          AND old.boundaries_version = 'current'
          AND NOT EXISTS (SELECT 1 FROM constituency_boundaries new
                           WHERE new.constituency_id = old.constituency_id
                             AND new.boundaries_version = '2025'));

-- ── 2. Retire the 2021 generation — DISTRICTS ONLY ──────────────────────────
DELETE FROM constituency_boundaries
 WHERE source_set IN ('laval-districts', 'quebec-districts')
   AND boundary_kind = 'district'
   AND boundaries_version = 'current';

DO $$
DECLARE dupes int; l int; q int; boroughs int; csd int; orphans int;
BEGIN
    SELECT count(*) INTO dupes FROM (
        SELECT constituency_id FROM constituency_boundaries
         WHERE source_set IN ('laval-districts', 'quebec-districts')
           AND effective_from <= CURRENT_DATE
           AND (effective_to IS NULL OR effective_to >= CURRENT_DATE)
         GROUP BY 1 HAVING count(*) > 1) d;
    IF dupes <> 0 THEN
        RAISE EXCEPTION 'Cutover left % ids live in two generations', dupes;
    END IF;

    SELECT count(*) INTO l FROM constituency_boundaries
     WHERE source_set = 'laval-districts' AND boundary_kind = 'district';
    SELECT count(*) INTO q FROM constituency_boundaries
     WHERE source_set = 'quebec-districts' AND boundary_kind = 'district';
    IF l <> 22 OR q <> 21 THEN
        RAISE EXCEPTION 'Expected 22 Laval / 21 Québec districts, found % / %', l, q;
    END IF;

    -- ★ The nine rows the district file does not contain and must not lose.
    SELECT count(*) INTO boroughs FROM constituency_boundaries
     WHERE source_set = 'quebec-districts' AND boundary_kind = 'borough';
    SELECT count(*) INTO csd FROM constituency_boundaries
     WHERE source_set = 'quebec-districts' AND boundary_kind = 'municipality';
    IF boroughs <> 5 OR csd <> 1 THEN
        RAISE EXCEPTION
          'Québec''s 5 boroughs and 1 city outline must survive a DISTRICT '
          'cutover; found % and %', boroughs, csd;
    END IF;

    SELECT count(*) INTO orphans FROM politicians p
     WHERE p.is_active AND p.level = 'municipal' AND p.constituency_id IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM constituency_boundaries b
                        WHERE b.constituency_id = p.constituency_id);
    IF orphans <> 0 THEN
        RAISE EXCEPTION '% municipal officials orphaned by the cutover', orphans;
    END IF;

    RAISE NOTICE 'Laval 22 / Québec 21 districts live — re-run '
                 'ingest-qc-municipal-roster to attach';
END $$;

COMMIT;

SELECT refresh_map_views();
