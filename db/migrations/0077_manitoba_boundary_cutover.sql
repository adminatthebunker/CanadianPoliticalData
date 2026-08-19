-- 0077 — Manitoba cutover: the first two-file load, plus a by-election we missed
--        and a duplicate the dossier misidentified.
--
-- ★ FIRST MULTI-FILE SPEC IN THE PROGRAMME
-- ----------------------------------------
-- Manitoba publishes its 57 divisions as TWO shapefiles, neither complete:
-- 25 Rural + 32 Urban. `source_path` and `zip_member` have accepted parallel
-- lists since the loader was written and no spec had ever used them.
--
-- ⚠⚠ Both outer archives are named `…_Public_Urban.zip`, and the FIRST holds the
-- *Rural* feature class:
--     2018_Final_ED_Manitoba_Public_Urban.zip -> EDBC2018_FinalBoundaries_Rural.shp   (25)
--     2018_Final_ED_Winnipeg_Public_Urban.zip -> EDBC2018_FinalBoundaries_Winnipeg.shp (32)
-- The spec names both members explicitly. A scalar `zip_member` is broadcast to
-- every path, so a single member name would be looked up in an archive that does
-- not contain it — which fails loudly rather than silently, but for the wrong
-- reason.
--
-- ✅ Our held geometry was CURRENT, and measured on both sides: 56 held rows
-- match this generation at 99.8317% mean / 99.1905% min / **0 below 95%**, and
-- match the staged 2008 generation at only 60.93% with 41 below 95%. So unlike
-- BC/SK/YT a HIGH overlap is the correct result here. Manitoba is a provenance
-- upgrade plus exactly one missing division.
--
-- What is gained: `The Pas-Kameesak`, **57 French division names** (Manitoba is
-- one of the few jurisdictions publishing them and we stored none), the
-- authoritative `Area` division numbers as authority_district_id, and the legal
-- in-force date.
--
-- ── Two roster findings, one of which corrects the research ─────────────────
--
-- ⛔ THE DOSSIER WAS WRONG ABOUT JELYNN DELA CRUZ. It recorded her as the member
-- for The Pas-Kameesak with a blank upstream constituency_name. She is not — she
-- is the MLA for **Radisson**, elected 2023, and we already hold her correctly
-- attached to Radisson with 139 speeches and 8 socials.
--
-- The unattached row is a DUPLICATE of her: `manitoba-assembly:former-mlas:
-- delacruz-jelynn`, an empty shell with 0 speeches, 0 socials, 0 terms, no party
-- and no constituency, produced by the former-MLAs scrape slugging her
-- `delacruz-jelynn` where the live path uses `delacruz`. A sitting member should
-- never have appeared in a former-members list at all.
--
-- ⚠ Deactivated rather than deleted or merged. `mb_assembly_slug` is UNIQUE and
-- the two rows carry DIFFERENT values, so this is formally a two-native-id pair
-- — the shape the Cooke rule says never to merge. The rule exists to stop two
-- distinct people being fused; here one row is demonstrably an empty artefact of
-- the same person. Deactivating threads that needle: nothing is destroyed, no id
-- is reassigned, and the row stops counting toward Manitoba's sitting members.
--
-- ★ AND THE FOURTH MISSED BY-ELECTION OF THIS PROGRAMME. The Pas-Kameesak has a
-- sitting member we have never heard of: **Jennifer Flett (NDP)**, who won the
-- by-election on **2026-07-22** for the seat left vacant when Amanda Lathlin,
-- MLA since 2015-04-22, died on 2026-03-21.
--
-- ⚠ That is now four in one sweep — Chicoutimi (QC), Chéticamp-Margarees-
-- Pleasant Bay (NS), Georgetown-Pownal (PE) and The Pas-Kameesak (MB) — none of
-- them picked up by the roster ingesters. The boundary work keeps surfacing them
-- because a district with no member is visible once the polygon exists. That is
-- a roster-pipeline problem, not a boundary one, and it deserves its own fix.
--
-- Run AFTER `load-boundaries --jurisdiction manitoba`.
--
-- Forward-only. Apply with:
--   docker exec -i sw-db psql -U sw -d sovereignwatch -v ON_ERROR_STOP=1 \
--     < db/migrations/0077_manitoba_boundary_cutover.sql

BEGIN;

DO $$
DECLARE n int;
BEGIN
    SELECT count(*) INTO n FROM constituency_boundaries
     WHERE constituency_id LIKE 'manitoba-electoral-districts/%'
       AND boundaries_version = '2018-commission';
    IF n <> 57 THEN
        RAISE EXCEPTION
          'Expected 57 authoritative MB rows, found %. Run '
          '`load-boundaries --jurisdiction manitoba` first.', n;
    END IF;
END $$;

-- ── 1. Re-key onto the generation-free prefix ───────────────────────────────
UPDATE politicians
   SET constituency_id = 'manitoba-electoral-districts/'
                       || split_part(constituency_id, '/', 2)
 WHERE constituency_id LIKE 'manitoba-electoral-districts-2018/%';

UPDATE politician_terms
   SET constituency_id = 'manitoba-electoral-districts/'
                       || split_part(constituency_id, '/', 2)
 WHERE constituency_id LIKE 'manitoba-electoral-districts-2018/%';

DELETE FROM constituency_boundaries
 WHERE constituency_id LIKE 'manitoba-electoral-districts-2018/%';

-- ── 2. Retire the empty duplicate ───────────────────────────────────────────
UPDATE politicians SET is_active = false, updated_at = now()
 WHERE source_id = 'manitoba-assembly:former-mlas:delacruz-jelynn'
   AND is_active
   -- Belt and braces: refuse if it has acquired content since this was written.
   AND NOT EXISTS (SELECT 1 FROM speeches s WHERE s.politician_id = politicians.id)
   AND NOT EXISTS (SELECT 1 FROM politician_terms t WHERE t.politician_id = politicians.id);

-- ── 3. The Pas-Kameesak's member ────────────────────────────────────────────
-- ⚠ source_id matches what Open North's ingester will mint
-- (`opennorth:{set}:{name.lower().replace(' ','-')}`), so the next
-- `ingest-mb-mlas` UPDATEs this row rather than inserting a second one — the
-- same reasoning as PEI in 0074, and the failure it avoids is BC's in 0069.
INSERT INTO politicians (
    source_id, name, first_name, last_name, level, province_territory,
    constituency_name, constituency_id, party, elected_office, is_active
)
SELECT 'opennorth:manitoba-legislature:jennifer-flett', 'Jennifer Flett',
       'Jennifer', 'Flett', 'provincial', 'MB',
       'The Pas-Kameesak', 'manitoba-electoral-districts/the-pas-kameesak',
       'New Democratic Party of Manitoba', 'MLA', true
 WHERE NOT EXISTS (
    SELECT 1 FROM politicians
     WHERE source_id = 'opennorth:manitoba-legislature:jennifer-flett');

INSERT INTO politician_changes (politician_id, change_type, new_value, severity)
SELECT p.id, 'newly_elected',
       jsonb_build_object(
         'migration', '0077_manitoba_boundary_cutover',
         'elected_at', '2026-07-22',
         'inserted_by', 'migration (not an ingester)',
         'reason', 'by-election following the death of Amanda Lathlin '
                   '(MLA 2015-04-22 to 2026-03-21); never ingested',
         'verified_against', 'CBC + CTV byelection results, Legislative '
                             'Assembly of Manitoba member listing'),
       'warning'
  FROM politicians p
 WHERE p.source_id = 'opennorth:manitoba-legislature:jennifer-flett'
   AND NOT EXISTS (SELECT 1 FROM politician_changes c
                    WHERE c.politician_id = p.id AND c.change_type = 'newly_elected');

DO $$
DECLARE bnd int; dupes int; orphans int; actives int; attached int;
        fr int; area numeric;
BEGIN
    SELECT count(*) INTO bnd FROM constituency_boundaries
     WHERE level='provincial' AND province_territory='MB'
       AND effective_from <= CURRENT_DATE
       AND (effective_to IS NULL OR effective_to >= CURRENT_DATE);
    IF bnd <> 57 THEN
        RAISE EXCEPTION 'Expected 57 current MB boundaries, found %', bnd;
    END IF;

    SELECT count(*) INTO dupes FROM (
        SELECT constituency_id FROM constituency_boundaries
         WHERE level='provincial' AND province_territory='MB'
           AND effective_from <= CURRENT_DATE
           AND (effective_to IS NULL OR effective_to >= CURRENT_DATE)
         GROUP BY 1 HAVING count(*) > 1) d;
    IF dupes <> 0 THEN
        RAISE EXCEPTION 'MB cutover left % duplicated districts', dupes;
    END IF;

    SELECT count(*) INTO orphans FROM politicians p
     WHERE p.constituency_id LIKE 'manitoba-electoral-districts%'
       AND NOT EXISTS (SELECT 1 FROM constituency_boundaries b
                        WHERE b.constituency_id = p.constituency_id);
    IF orphans <> 0 THEN
        RAISE EXCEPTION 'MB cutover left % orphaned politician rows', orphans;
    END IF;

    SELECT count(*) INTO actives FROM politicians
     WHERE province_territory='MB' AND level='provincial' AND is_active;
    SELECT count(*) INTO attached FROM politicians
     WHERE province_territory='MB' AND level='provincial' AND is_active
       AND constituency_id IS NOT NULL;
    IF actives <> 57 OR attached <> 57 THEN
        RAISE EXCEPTION
          'Expected 57 active MB MLAs all attached, got % active / % attached',
          actives, attached;
    END IF;

    SELECT count(*) INTO fr FROM constituency_boundaries
     WHERE level='provincial' AND province_territory='MB' AND name_fr IS NOT NULL;
    IF fr <> 57 THEN
        RAISE EXCEPTION 'Expected 57 French division names, found %', fr;
    END IF;

    -- ★ The two-file check, expressed as geometry rather than trust: if only one
    -- archive had loaded, the total would be far short of Manitoba's 647,797 km²
    -- (Winnipeg's 32 divisions are a rounding error in area terms, and the 25
    -- rural ones are nearly the whole province).
    SELECT sum(area_sqkm)::numeric INTO area FROM constituency_boundaries
     WHERE level='provincial' AND province_territory='MB'
       AND effective_from <= CURRENT_DATE
       AND (effective_to IS NULL OR effective_to >= CURRENT_DATE);
    IF area < 630000 OR area > 670000 THEN
        RAISE EXCEPTION
          'MB total area % km² is outside the plausible band for a 647,797 km² '
          'province — did only one of the two shapefiles load?', round(area);
    END IF;

    RAISE NOTICE 'MB: 57 of 57 divisions (25 rural + 32 urban), % km², 57 French names, 57 MLAs attached',
      round(area);
END $$;

COMMIT;

SELECT refresh_map_views();
