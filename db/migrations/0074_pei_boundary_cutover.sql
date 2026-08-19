-- 0074 — PEI cutover: authoritative geometry at 13x the resolution, plus the
--        27th district and the MLA who represents it.
--
-- ⛔ WHY PEI'S GAP SURVIVED EVERY INTERNAL CHECK
-- ---------------------------------------------
-- Before this migration PEI held 26 boundaries, 26 active MLAs, 26 distinct
-- district names, and ZERO unattached members. Every internal consistency check
-- passed. The province has 27 seats.
--
-- Both halves were mirrored from the same Open North source, so they were wrong
-- together and agreed with each other. No amount of cross-checking our own
-- tables could find it — only the agency's published count could, which is
-- exactly why "confirm against the elections agency" is a mandatory step in this
-- programme rather than a formality.
--
-- ★ AND THE 26 WE DID HOLD WERE 13x TOO COARSE — measured, not inferred
-- ---------------------------------------------------------------------
-- The comparison showed 26 matched at 96.59% mean overlap but with six districts
-- between 82.51% and 93.96%, all of them the small Charlottetown-area ones. Two
-- explanations fit that shape — a real redraw, or resolution loss — and they
-- select different migrations, so it was measured:
--
--                        districts   total area   avg vertices
--     authoritative           27      5,641.2 km²      10,408
--     Open North mirror       26      5,172.1 km²         779
--
-- PEI's real land area is ~5,660 km². The authoritative set matches it to 0.3%;
-- the mirror loses ~470 km² of coastline BEFORE accounting for the missing
-- district, and carries one thirteenth of the vertices. So the low overlaps are
-- the mirror's own generalisation eroding small urban districts proportionally
-- hardest — not a boundary change. Nothing about PEI's districts moved; our copy
-- of them was simply blurry.
--
-- ⚠ This is also why the count check alone is insufficient. Had PEI held all 27
-- coarse polygons, every count assertion in this programme would have passed
-- while six districts still answered wrongly near their edges.
--
-- Run AFTER `load-boundaries --jurisdiction prince-edward-island`.
--
-- Forward-only. Apply with:
--   docker exec -i sw-db psql -U sw -d sovereignwatch -v ON_ERROR_STOP=1 \
--     < db/migrations/0074_pei_boundary_cutover.sql

BEGIN;

DO $$
DECLARE n int;
BEGIN
    SELECT count(*) INTO n FROM constituency_boundaries
     WHERE constituency_id LIKE 'prince-edward-island-electoral-districts/%'
       AND boundaries_version = '2017';
    IF n <> 27 THEN
        RAISE EXCEPTION
          'Expected 27 authoritative PE rows, found %. Run '
          '`load-boundaries --jurisdiction prince-edward-island` first.', n;
    END IF;
END $$;

-- ── 1. Re-key onto the generation-free prefix ───────────────────────────────
UPDATE politicians
   SET constituency_id = 'prince-edward-island-electoral-districts/'
                       || split_part(constituency_id, '/', 2)
 WHERE constituency_id LIKE 'prince-edward-island-electoral-districts-2017/%';

UPDATE politician_terms
   SET constituency_id = 'prince-edward-island-electoral-districts/'
                       || split_part(constituency_id, '/', 2)
 WHERE constituency_id LIKE 'prince-edward-island-electoral-districts-2017/%';

DELETE FROM constituency_boundaries
 WHERE constituency_id LIKE 'prince-edward-island-electoral-districts-2017/%';

-- ── 2. The 27th member ──────────────────────────────────────────────────────
-- ★ Brendan Curran (PC) won the Georgetown-Pownal (District 2) by-election on
-- 2025-12-08 and has sat since. Our roster never had him — eight months stale,
-- the same shape as Nova Scotia's Chéticamp seat. Verified against Elections PEI
-- and the Legislative Assembly member listing, not inferred from the gap.
--
-- ⚠ The source_id is deliberately the one Open North's ingester WILL mint for
-- him: `_build_source_id` is
-- `f"opennorth:{set_slug}:{rep['name'].lower().replace(' ','-')}"`, giving
-- `opennorth:pei-legislature:brendan-curran`. Using any other tag would mean the
-- next `ingest-pei-mlas` INSERTs a second row for the same person, because that
-- ingester keys solely on source_id — which is precisely how British Columbia
-- ended up serving two MLAs for five districts (see 0069). Matching the
-- predicted id makes the next upstream run an UPDATE, and keeps him inside the
-- `LIKE 'opennorth:pei-legislature:%'` scope that `detect_retirements` sweeps,
-- so he can be retired normally when he leaves.
--
-- The true provenance of this row is recorded in politician_changes below.
INSERT INTO politicians (
    source_id, name, first_name, last_name, level, province_territory,
    constituency_name, constituency_id, party, elected_office, is_active
)
SELECT 'opennorth:pei-legislature:brendan-curran', 'Brendan Curran',
       'Brendan', 'Curran', 'provincial', 'PE',
       'Georgetown - Pownal', 'prince-edward-island-electoral-districts/georgetown-pownal',
       'Progressive Conservative Party of Prince Edward Island', 'MLA', true
 WHERE NOT EXISTS (
    SELECT 1 FROM politicians
     WHERE source_id = 'opennorth:pei-legislature:brendan-curran');

INSERT INTO politician_changes (politician_id, change_type, new_value, severity)
-- ⚠ `newly_elected`, not a new change_type. politician_changes has a CHECK
-- constraint listing nine permitted values, and it rejected an invented
-- `manual_insert` — correctly. `newly_elected` is not a workaround for that
-- rejection, it is the accurate description: Curran won a by-election.
SELECT p.id, 'newly_elected',
       jsonb_build_object(
         'migration', '0074_pei_boundary_cutover',
         'elected_at', '2025-12-08',
         'inserted_by', 'migration (not an ingester)',
         'reason', 'District 2 Georgetown-Pownal had no member in the roster; '
                   'by-election 2025-12-08 was never ingested',
         'verified_against', 'Elections PEI district-2 results + assembly.pe.ca '
                             'member listing',
         'note', 'source_id matches the id Open North will mint, so the next '
                 'ingest updates rather than duplicates'),
       'warning'
  FROM politicians p
 WHERE p.source_id = 'opennorth:pei-legislature:brendan-curran'
   AND NOT EXISTS (SELECT 1 FROM politician_changes c
                    WHERE c.politician_id = p.id AND c.change_type = 'newly_elected');

DO $$
DECLARE bnd int; dupes int; orphans int; actives int; attached int; area numeric;
BEGIN
    SELECT count(*) INTO bnd FROM constituency_boundaries
     WHERE level='provincial' AND province_territory='PE'
       AND effective_from <= CURRENT_DATE
       AND (effective_to IS NULL OR effective_to >= CURRENT_DATE);
    IF bnd <> 27 THEN
        RAISE EXCEPTION 'Expected 27 current PE boundaries, found %', bnd;
    END IF;

    SELECT count(*) INTO dupes FROM (
        SELECT constituency_id FROM constituency_boundaries
         WHERE level='provincial' AND province_territory='PE'
           AND effective_from <= CURRENT_DATE
           AND (effective_to IS NULL OR effective_to >= CURRENT_DATE)
         GROUP BY 1 HAVING count(*) > 1) d;
    IF dupes <> 0 THEN
        RAISE EXCEPTION 'PE cutover left % duplicated districts', dupes;
    END IF;

    SELECT count(*) INTO orphans FROM politicians p
     WHERE p.constituency_id LIKE 'prince-edward-island-electoral-districts%'
       AND NOT EXISTS (SELECT 1 FROM constituency_boundaries b
                        WHERE b.constituency_id = p.constituency_id);
    IF orphans <> 0 THEN
        RAISE EXCEPTION 'PE cutover left % orphaned politician rows', orphans;
    END IF;

    SELECT count(*) INTO actives FROM politicians
     WHERE province_territory='PE' AND level='provincial' AND is_active;
    SELECT count(*) INTO attached FROM politicians
     WHERE province_territory='PE' AND level='provincial' AND is_active
       AND constituency_id IS NOT NULL;
    IF actives <> 27 OR attached <> 27 THEN
        RAISE EXCEPTION
          'Expected 27 active PE MLAs all attached, got % active / % attached',
          actives, attached;
    END IF;

    -- ★ The resolution check. If the coarse mirror were somehow still in place
    -- the total would sit near 5,172 km² rather than PEI's real ~5,660.
    SELECT sum(area_sqkm)::numeric INTO area FROM constituency_boundaries
     WHERE level='provincial' AND province_territory='PE'
       AND effective_from <= CURRENT_DATE
       AND (effective_to IS NULL OR effective_to >= CURRENT_DATE);
    IF area < 5500 OR area > 5800 THEN
        RAISE EXCEPTION
          'PE total area % km² is outside the plausible 5500-5800 band for a '
          '5,660 km² province — check the projection', round(area, 1);
    END IF;

    RAISE NOTICE 'PE: 27 of 27 districts, % km², all attached', round(area, 1);
END $$;

COMMIT;

SELECT refresh_map_views();
