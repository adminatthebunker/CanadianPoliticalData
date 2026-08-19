-- 0072 — Federal cutover: retire the Open North mirror, adopt Elections Canada.
--
-- ⚠ URGENT WHEN WRITTEN: the authoritative load had just inserted 343 rows under
-- `federal-electoral-districts/<FED_NUM>` while the 342 mirror rows still sat
-- under `federal-electoral-districts-2023-representation-order/<FED_NUM>` with
-- effective_to NULL. Different constituency_id, same polygons, both satisfying
-- the current-date predicate — so every federal postcode lookup was returning
-- two districts until this ran.
--
-- What the comparison showed
-- -------------------------
--   authoritative 343 | held 342 | matched 342
--   mean overlap 99.9128%, min 99.5769%, **0 districts below 95%**
--   absent from our table: exactly one — 24077
--
-- So unlike BC/SK/NB this is NOT a stale generation. Our geometry was right.
-- This is a provenance upgrade plus one dropped row, the same shape as Ontario's
-- Scarborough Southwest and Quebec's Chicoutimi.
--
-- What is gained
-- --------------
--   • 24077 `Ville-Marie—Le Sud-Ouest—Île-des-Soeurs` (QC), whose neighbours
--     24076 and 24078 were both present — a single dropped mirror row.
--   • **343 French district names.** We stored none for any federal district; in
--     an officially bilingual jurisdiction that was a real gap, and the file has
--     carried ED_NAMEF all along.
--   • The correct legal in-force date. SI/2023-57 comes into force "on the first
--     dissolution of Parliament that occurs at least seven months after"
--     registration (2023-09-27); seven months lands 2024-04-22 and the first
--     dissolution after that was **2025-03-23**, the 45th general election writs.
--     ⚠ Elections Canada's own metadata says 2024-04-23 — the administrative
--     date, the day the order became CAPABLE of coming into force. Between the
--     two the 2013 order was still law and the 44th Parliament still sat its 338
--     seats, so the metadata date would assert a map that governed nothing for
--     eleven months. Both beat the fabricated 2023-01-01 the mirror carried.
--   • A generation-free `constituency_id` prefix.
--
-- Run AFTER `load-boundaries --spec-file .../federal.py`.
--
-- Forward-only. Apply with:
--   docker exec -i sw-db psql -U sw -d sovereignwatch -v ON_ERROR_STOP=1 \
--     < db/migrations/0072_federal_boundary_cutover.sql

BEGIN;

DO $$
DECLARE n int;
BEGIN
    SELECT count(*) INTO n FROM constituency_boundaries
     WHERE constituency_id LIKE 'federal-electoral-districts/%'
       AND boundaries_version = '2023-representation-order';
    IF n <> 343 THEN
        RAISE EXCEPTION
          'Expected 343 authoritative federal rows, found %. Run the federal '
          'load first.', n;
    END IF;
END $$;

-- ── 1. Re-key the roster ────────────────────────────────────────────────────
-- Pure prefix swap: both sides key the slug on FED_NUM, so there is no lookup
-- and no name matching. That is the payoff of federal ids being numeric — none
-- of Elections Canada's em-dash and apostrophe re-spellings can break the join.
UPDATE politicians
   SET constituency_id = 'federal-electoral-districts/'
                       || split_part(constituency_id, '/', 2)
 WHERE constituency_id LIKE 'federal-electoral-districts-2023-representation-order/%';

UPDATE politician_terms
   SET constituency_id = 'federal-electoral-districts/'
                       || split_part(constituency_id, '/', 2)
 WHERE constituency_id LIKE 'federal-electoral-districts-2023-representation-order/%';

-- ── 2. Attach the member of the district we never held ──────────────────────
-- ★ Marc Miller has sat for Ville-Marie—Le Sud-Ouest—Île-des-Sœurs with a NULL
-- constituency_id for as long as we have had the table, for the structural
-- reason that his district had no polygon to point at.
--
-- ⚠ Attached by FED_NUM rather than by name on purpose. Elections Canada writes
-- `Île-des-Soeurs` (oe digraph) and our roster carries `Île-des-Sœurs` (œ
-- ligature, U+0153). Those are different strings and a name join silently misses
-- — which is precisely the class of failure that keying federal ids on the
-- number avoids everywhere else.
UPDATE politicians
   SET constituency_id = 'federal-electoral-districts/24077', updated_at = now()
 WHERE level = 'federal' AND is_active AND elected_office = 'MP'
   AND constituency_id IS NULL
   AND constituency_name LIKE 'Ville-Marie%';

-- ── 3. Retire the mirror ────────────────────────────────────────────────────
-- Deleted, not end-dated: these are a worse copy of the SAME generation, not a
-- superseded one. Giving them an effective_to would assert a federal
-- redistribution between 2023 and 2026 that never happened.
DELETE FROM constituency_boundaries
 WHERE constituency_id LIKE 'federal-electoral-districts-2023-representation-order/%';

DO $$
DECLARE bnd int; dupes int; orphans int; fr int; nopt int; mps int; unattached int;
BEGIN
    SELECT count(*) INTO bnd FROM constituency_boundaries
     WHERE level='federal'
       AND effective_from <= CURRENT_DATE
       AND (effective_to IS NULL OR effective_to >= CURRENT_DATE);
    IF bnd <> 343 THEN
        RAISE EXCEPTION 'Expected 343 current federal boundaries, found %', bnd;
    END IF;

    SELECT count(*) INTO dupes FROM (
        SELECT constituency_id FROM constituency_boundaries
         WHERE level='federal'
           AND effective_from <= CURRENT_DATE
           AND (effective_to IS NULL OR effective_to >= CURRENT_DATE)
         GROUP BY 1 HAVING count(*) > 1) d;
    IF dupes <> 0 THEN
        RAISE EXCEPTION 'Federal cutover left % duplicated districts', dupes;
    END IF;

    SELECT count(*) INTO orphans FROM politicians p
     WHERE p.constituency_id LIKE 'federal-electoral-districts%'
       AND NOT EXISTS (SELECT 1 FROM constituency_boundaries b
                        WHERE b.constituency_id = p.constituency_id);
    IF orphans <> 0 THEN
        RAISE EXCEPTION 'Federal cutover left % orphaned politician rows', orphans;
    END IF;

    SELECT count(*) INTO fr FROM constituency_boundaries
     WHERE level='federal' AND name_fr IS NOT NULL;
    IF fr <> 343 THEN
        RAISE EXCEPTION 'Expected 343 French names, found %', fr;
    END IF;

    -- province_territory is derived per row from FED_NUM's first two digits
    -- (the SGC province code); no Elections Canada file carries the column.
    SELECT count(*) INTO nopt FROM constituency_boundaries
     WHERE level='federal' AND province_territory IS NULL;
    IF nopt <> 0 THEN
        RAISE EXCEPTION '% federal rows have no province_territory', nopt;
    END IF;

    -- ⚠ REPORTED, NOT ASSERTED. Federal shows 354 active MPs against 343 seats:
    -- 11 duplicate pairs, each an `opennorth:house-of-commons:*` row against an
    -- `op:*` (openparliament) row for the same district. Most are one person
    -- under two spellings (Rob/Robert Oliphant, Michelle Rempel/Rempel Garner,
    -- Shuv/Shuvaloy Majumdar), but at least two are NOT:
    --   • Scarborough Southwest holds Bill Blair AND `op:doly-begum` — Doly Begum
    --     is an Ontario MPP, misclassified as federal.
    --   • University—Rosedale holds Chrystia Freeland AND Danielle Martin, who
    --     won the by-election for the seat Freeland vacated.
    -- That is pre-existing roster drift, not something this cutover caused, and
    -- each case needs individual verification. Asserting on it here would only
    -- block a boundary fix on an unrelated problem.
    SELECT count(*) INTO mps FROM politicians
     WHERE level='federal' AND is_active AND elected_office='MP';
    SELECT count(*) INTO unattached FROM politicians
     WHERE level='federal' AND is_active AND elected_office='MP'
       AND constituency_id IS NULL;
    RAISE NOTICE 'federal: 343 districts, 343 French names; roster % MPs / 343 seats, % unattached (see comment)',
      mps, unattached;
END $$;

COMMIT;

SELECT refresh_map_views();
