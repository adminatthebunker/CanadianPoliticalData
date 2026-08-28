-- 0119 — Five Québec municipalities whose held district geometry was flagged by
--        the 2025-11-02 MAMH roster. ONE of the five was a map problem.
--
-- Run AFTER `load-boundaries --jurisdiction sherbrooke-districts`.
--
-- ★ WHAT THE EVIDENCE ACTUALLY SAID, per municipality
-- ───────────────────────────────────────────────────
-- The trigger was a count mismatch between the MAMH election result and our
-- polygons. Counts are a smoke alarm, not a diagnosis, and here they pointed at
-- four different underlying faults:
--
--   sherbrooke   PARTIAL-INGEST HOLE  → fixed here, authoritative map loaded
--   kirkland     SPELLING DIVERGENCE  → fixed here, alias row, no map needed
--   brossard     REAL REDRAW          → superseded map end-dated, no replacement
--   senneville   PARTIAL-INGEST HOLE  → untouched, no publisher ships geometry
--   ste-anne     PARTIAL-INGEST HOLE  → untouched, no publisher ships geometry
--
-- ⛔ KIRKLAND WAS NEVER A MISSING POLYGON. The brief read "councillor elected for
-- `Saint-Charles`; no such polygon in our 8". The polygon is right there — the
-- mirror minted it as `kirkland-districts/st-charles` while MAMH writes the
-- district out in full, and `cpd_slugify('Saint-Charles')` is `saint-charles`.
-- Eight districts elected against eight held, all eight names agreeing once the
-- abbreviation is reconciled. Nothing about Kirkland's map is stale as far as
-- anything we can observe goes, and no authoritative Kirkland geometry exists to
-- prove otherwise, so the map is left exactly as it is and only the roster edge
-- is repaired — via `constituency_name_alias` (0120), which is what that table
-- is for.
--
-- ⚠ And note WHICH DIRECTION the alias points. `saint-charles` is one of the
-- three slugs that collide across Québec cities (Kirkland + Longueuil; the
-- others are `plateau` and `carrefour`). Aliasing the roster's `saint-charles`
-- ONTO our existing `st-charles` keeps Kirkland's id unique by construction.
-- Re-keying the polygon to `saint-charles` instead would have walked straight
-- into the 0089 failure mode — a councillor 40 km up the south shore.
--
-- ★ SHERBROOKE: 16 DISTRICTS, AND THE FIFTEEN WE HAD WERE NOT WRONG
-- ──────────────────────────────────────────────────────────────────
-- `load-boundaries --compare` against the city's own CC-BY file:
--
--     authoritative=16  held=16  matched=15
--     mean_overlap=99.3777%  min=98.7511%  below_95%=0
--     absent from our table (1): lennoxville
--     we hold, authority does not (1): 2443027   ← the CSD outline, keep it
--
-- So this is a hole, not a redraw: the mirror ingested 15 of Sherbrooke's 16
-- districts and simply never picked up 3.0 de Lennoxville. Bertrand Collins sat
-- with `constituency_id IS NULL` under BOTH the mirror roster and the 2025 MAMH
-- roster for that reason.
--
-- The date is still 2025-11-02 and still comes from an instrument, not from the
-- overlap number. **Règlement numéro 1289** *divisant le territoire des
-- arrondissements de la Ville de Sherbrooke en districts électoraux*, adopted at
-- the ordinary council sitting of 2024-05-21, approved by the Commission de la
-- représentation électorale on 2024-10-31 and in force from that date; ruling
-- A10.4 dates the map by the election it first governed. A 99.38% overlap is not
-- identity and cannot license an earlier date — 1289 was a fresh division
-- exercise ("il y a lieu de revoir la division"), and the only date we can
-- actually evidence for the map now in force is the election it governed.
--
-- ⚠ The city's web page says the by-law was adopted "le 7 mai 2024"; the by-law's
-- own first page says the sitting was 21 mai 2024. 7 May is almost certainly the
-- avis de motion. Neither is the date stored.
--
-- ⚠ DISTRICT 3.0 DE LENNOXVILLE IS THE EXACT UNION OF 3.1 D'UPLANDS AND 3.2 DE
-- FAIRVIEW, and that is Sherbrooke's real structure rather than a defect.
-- Lennoxville holds bilingual-municipality status under the Charte de la langue
-- française so its limits cannot be moved by a districting exercise; it elects
-- ONE conseiller municipal over the whole borough plus TWO conseillers
-- d'arrondissement over its halves. **A point in Lennoxville therefore returns
-- two districts, by design.** Any future "one point, one district" assertion has
-- to carve out this borough or it will fail on correct data.
--
-- ⛔ BROSSARD IS THE ONE REAL REDRAW, AND WE CANNOT REPLACE IT
-- ────────────────────────────────────────────────────────────
-- Brossard went from 10 districts to 12 for 2025-11-02. Règlement REG-478 was
-- adopted 2024-05-28; the Commission de la représentation électorale then
-- MODIFIED the City's own delimitation and announced its map 2024-12-03. Both
-- the count and the lines changed.
--
-- We hold nine polygons — a partial ingest of the superseded TEN-district map.
-- They are wrong twice over, they are stamped `effective_from 2023-01-01`, and
-- until now `/boundaries/lookup` answered every Brossard address from them.
-- Brossard publishes its 2025–2029 map as a PDF and nothing else: not on Données
-- Québec (`package_search?q=brossard` → 0), and its public ArcGIS org
-- (`Amenagement_Brossard`) holds ten items, none electoral.
--
-- ★ So they are END-DATED at 2025-11-01, not deleted. The geometry is a real
-- record of the pre-2025 map and worth keeping addressable; what is not
-- defensible is serving it as current. Honest absence over confident error —
-- the same reasoning that left Longueuil's six councillors unattached in 0099
-- rather than forcing them onto a superseded map.
-- ⓘ This does NOT move the `missing-district-polygon` advisory: MAMH gives
-- Brossard's twelve councillors no district name at all (every one reads
-- `Brossard`), so they were already counted unfixable and the sentinel's own
-- query excludes municipality outlines.
--
-- ⛔ SENNEVILLE AND SAINTE-ANNE-DE-BELLEVUE ARE LEFT ALONE, DELIBERATELY
-- ──────────────────────────────────────────────────────────────────────
-- Both elect six councillors and both hold five polygons with a GAP IN THE
-- MIDDLE of the numbering — Senneville has 1,2,4,5,6 and Sainte-Anne 1,3,4,5,6.
-- Better still, the mirror's own roster had the same gaps (five councillors
-- each, missing exactly district 3 and district 2). Two independent halves of
-- the mirror missing the same district is a partial ingest, not a five-district
-- council.
--
-- Senneville's date is established and recorded in PROVENANCE.md — By-law 500,
-- adopted 2024-05-28, in force 2024-05-30, CRE approval 2024-04-19 — and it is
-- of no use, because Article 1 delimits the six districts in CLOCKWISE PROSE
-- ("the rear boundary line of Pacific Avenue (North-East side), excluding
-- Morningside Avenue…") with no plan annexed in any vector form. Sainte-Anne's
-- division by-law was not located at all.
--
-- Neither has a proven-wrong map, only an incomplete one, so nothing here
-- touches them. Their eleven detached councillors stay detached. That is the
-- correct outcome, not a shortfall.
--
-- ⛔ ÉLECTIONS QUÉBEC IS NOT A GEOMETRY SOURCE, AND THIS COSTS AN HOUR TO LEARN.
-- Its register of divided municipalities is real and useful (a semicolon CSV
-- behind a JS table — see PROVENANCE.md for both years' URLs), and every one of
-- these five is in it for both 2021 and 2025. But the per-municipality maps it
-- links are RASTER PDFs whose only printed date is `Production : Avril 2025`, a
-- cartography run. EQ publishes no municipal district geometry anywhere.
--
-- Forward-only. Apply with:
--   docker exec -i sw-db psql -U sw -d sovereignwatch -v ON_ERROR_STOP=1 \
--     < db/migrations/0119_qc_small_five_cutover.sql

BEGIN;

-- ── 0. The load must have happened ──────────────────────────────────────────
DO $$
DECLARE n int;
BEGIN
    SELECT count(*) INTO n FROM constituency_boundaries
     WHERE source_set = 'sherbrooke-districts'
       AND boundaries_version = '2025' AND boundary_kind = 'district';
    IF n <> 16 THEN
        RAISE EXCEPTION 'Expected 16 authoritative Sherbrooke districts, found %. '
                        'Run `load-boundaries --jurisdiction sherbrooke-districts` '
                        'first.', n;
    END IF;
END $$;

-- ── 1. Retire Sherbrooke's mirror generation — DISTRICTS ONLY ───────────────
-- ⛔ Scoped by SOURCE_SET, never by district name. `Carrefour` is a Sherbrooke
-- district AND a Laval district; 0106 mis-counted 286 rows instead of 203 by
-- scoping the other way.
-- ⚠ `boundary_kind = 'district'` protects `census-subdivisions/2443027`, the
-- city outline that lives inside this set and that the district file does not
-- contain. 0099 lost this the first time round for Québec's five boroughs.
-- ⓘ No member needs detaching first: all 15 mirror ids are reproduced
-- byte-for-byte by the 2025 generation, so nothing is left pointing at a row
-- that is about to disappear. The assertion below proves it rather than
-- assuming it.
DO $$
DECLARE lost int;
BEGIN
    SELECT count(*) INTO lost
      FROM constituency_boundaries old
     WHERE old.source_set = 'sherbrooke-districts'
       AND old.boundaries_version = 'current'
       AND old.boundary_kind = 'district'
       AND NOT EXISTS (SELECT 1 FROM constituency_boundaries new
                        WHERE new.constituency_id = old.constituency_id
                          AND new.boundaries_version = '2025');
    IF lost <> 0 THEN
        RAISE EXCEPTION
          'Sherbrooke cutover would drop % constituency_id(s) the 2025 map does '
          'not reproduce — detach their members first', lost;
    END IF;
END $$;

DELETE FROM constituency_boundaries
 WHERE source_set = 'sherbrooke-districts'
   AND boundaries_version = 'current'
   AND boundary_kind = 'district';

-- ── 2. Brossard: end-date the superseded 10-district map's survivors ────────
-- ⚠ 2025-11-01, the day before the election the CRE's 12-district map first
-- governed. End-dated, NOT deleted — see the header.
UPDATE constituency_boundaries
   SET effective_to = DATE '2025-11-01', updated_at = now()
 WHERE source_set = 'brossard-districts'
   AND boundaries_version = 'current'
   AND boundary_kind = 'district'
   AND effective_to IS NULL;

-- ── 3. Kirkland: reconcile the roster's spelling with the minted id ─────────
-- ⓘ Idempotent: re-running must not error, and must not silently repoint an
-- alias an operator has since corrected by hand — hence DO NOTHING, not
-- DO UPDATE.
INSERT INTO constituency_name_alias (council, alias_slug, target_slug, reason)
VALUES (
  'kirkland', 'saint-charles', 'st-charles',
  'MAMH''s 2025 election result writes Kirkland''s district out in full as '
  '"Saint-Charles"; the Open North mirror minted the polygon as "St-Charles" '
  'and that id is what politicians and boundaries are keyed on. Same district — '
  'Kirkland elects 8 councillors against our 8 polygons and the other 7 names '
  'agree exactly. Aliased ONTO the abbreviation rather than re-keying the '
  'polygon because "saint-charles" is also Longueuil''s district slug (one of '
  'the three cross-city collisions with "plateau" and "carrefour"), and 0089 '
  'exists because that collision was resolved the wrong way once already.'
)
ON CONFLICT (council, alias_slug) DO NOTHING;

-- ── 4. Assertions ───────────────────────────────────────────────────────────
DO $$
DECLARE sherb int; csd int; dupes int; n_overlap int;
        bros_live int; bros_ended int; orphans int; alias_ok int;
BEGIN
    SELECT count(*) INTO sherb FROM constituency_boundaries
     WHERE source_set = 'sherbrooke-districts' AND boundary_kind = 'district'
       AND effective_from <= CURRENT_DATE
       AND (effective_to IS NULL OR effective_to >= CURRENT_DATE);
    IF sherb <> 16 THEN
        RAISE EXCEPTION 'Sherbrooke: % live districts after cutover, expected 16',
                        sherb;
    END IF;

    -- The city outline the district file does not carry must survive.
    SELECT count(*) INTO csd FROM constituency_boundaries
     WHERE source_set = 'sherbrooke-districts' AND boundary_kind = 'municipality';
    IF csd <> 1 THEN
        RAISE EXCEPTION 'Sherbrooke''s CSD outline must survive a DISTRICT '
                        'cutover; found %', csd;
    END IF;

    -- No id live in two generations, table-wide.
    SELECT count(*) INTO dupes FROM (
        SELECT constituency_id FROM constituency_boundaries
         WHERE effective_from <= CURRENT_DATE
           AND (effective_to IS NULL OR effective_to >= CURRENT_DATE)
         GROUP BY 1 HAVING count(*) > 1) d;
    IF dupes <> 0 THEN
        RAISE EXCEPTION '% constituency_id(s) live in two generations', dupes;
    END IF;

    -- ⛔ `overlaps` is a reserved word in plpgsql — this variable is n_overlap.
    SELECT count(*) INTO n_overlap FROM constituency_boundaries a
      JOIN constituency_boundaries b
        ON b.source_set = a.source_set
       AND b.boundaries_version <> a.boundaries_version
       AND a.boundary_kind = 'district' AND b.boundary_kind = 'district'
       AND a.effective_from <= coalesce(b.effective_to, DATE '9999-12-31')
       AND b.effective_from <= coalesce(a.effective_to, DATE '9999-12-31')
     WHERE a.level = 'municipal';
    IF n_overlap <> 0 THEN
        RAISE EXCEPTION '% overlapping municipal generation pairs table-wide',
                        n_overlap;
    END IF;

    SELECT count(*) FILTER (WHERE effective_to IS NULL),
           count(*) FILTER (WHERE effective_to = DATE '2025-11-01')
      INTO bros_live, bros_ended
      FROM constituency_boundaries
     WHERE source_set = 'brossard-districts' AND boundary_kind = 'district';
    IF bros_live <> 0 OR bros_ended <> 9 THEN
        RAISE EXCEPTION 'Brossard: expected 0 open-ended and 9 end-dated '
                        'districts, got % and %', bros_live, bros_ended;
    END IF;

    SELECT count(*) INTO alias_ok FROM constituency_name_alias
     WHERE council = 'kirkland' AND alias_slug = 'saint-charles'
       AND target_slug = 'st-charles';
    IF alias_ok <> 1 THEN
        RAISE EXCEPTION 'Kirkland alias row missing';
    END IF;

    -- ⚠ Sitting members only, and note this is what makes the Brossard
    -- end-dating safe: its nine mirror councillors are all is_active = false.
    SELECT count(*) INTO orphans FROM politicians p
     WHERE p.is_active AND p.constituency_id IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM constituency_boundaries b
                        WHERE b.constituency_id = p.constituency_id);
    IF orphans <> 0 THEN
        RAISE EXCEPTION 'cutover orphaned % sitting members', orphans;
    END IF;

    RAISE NOTICE 'Sherbrooke on Règlement 1289 (16 districts incl. Lennoxville); '
                 'Brossard''s superseded map end-dated 2025-11-01; Kirkland '
                 'aliased. Run `reattach-municipal-roster` next.';
END $$;

COMMIT;

SELECT refresh_map_views();
