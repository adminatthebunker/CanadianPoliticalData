-- 0121 — Longueuil and Terrebonne: the last two Québec municipalities the
--        2025-11-02 MAMH roster proved stale. BOTH ARE REAL REDRAWS.
--
-- Run AFTER:
--   load-boundaries --jurisdiction longueuil-districts
--   load-boundaries --jurisdiction terrebonne-districts
--
-- ★ WHAT THE EVIDENCE SAID
-- ────────────────────────
--   longueuil   REAL REDRAW, 15 -> 18   → superseded generation end-dated
--   terrebonne  REAL REDRAW, 16 -> 16   → superseded generation end-dated
--
-- Both replacements are loaded, so neither municipality is left without
-- coverage. That is the difference between this migration and 0119's Brossard.
--
-- ⛔ TERREBONNE IS THE ONE THAT MATTERED, AND THE COUNT SAID NOTHING
-- ──────────────────────────────────────────────────────────────────
-- The trigger was two councillors naming districts we had no polygon for:
-- `Côte de Terrebonne-Urbanova` (we held `cote-de-terrebonne`) and
-- `La Bergeronne` (absent). Sixteen polygons, sixteen councillors — the count
-- agreed perfectly, and the obvious reading was a RENAME: patch two names,
-- keep the lines, keep the date, no new generation. That reading was wrong.
--
-- `load-boundaries --compare` against the city's own layer:
--
--     authoritative=16  held=17  matched=14
--     mean_overlap=81.7721%  min=40.9525%  below_95%=12
--     absent from our table (2): cote-de-terrebonne-urbanova, la-bergeronne
--     we hold, authority does not (3): 2464008, cote-de-terrebonne,
--                                      grand-ruisseau
--     lowest: du-ruisseau-noir 40.95%, seigneurie-ile-saint-jean 52.16%,
--             comtois-la-piniere 69.56%, charles-aubert 70.88%
--
-- TWELVE of the fourteen districts whose NAMES never changed had moved, one of
-- them keeping only 41% of its area. Règlement 929 says so itself — the city's
-- own summary is that the by-law "touche 13 des 16 districts actuels, soit les
-- districts 1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 13, 14 et 15, alors que les limites
-- existantes sont conservées pour trois (3) districts, soit les districts 10,
-- 12 et 16."
--
-- ⛔ And the two renames run the WRONG WAY for a name patch. The Urbanova
-- sector moved OUT of district 5 and INTO district 7. District 5 was renamed
-- `Grand Ruisseau` -> `La Bergeronne` BECAUSE it lost Urbanova; district 7 was
-- renamed `Côte de Terrebonne` -> `Côte de Terrebonne-Urbanova` BECAUSE it
-- gained it. Aliasing `cote-de-terrebonne-urbanova` onto `cote-de-terrebonne`
-- would have put every Urbanova address in the district that no longer contains
-- it — a confident answer, pointing at the wrong councillor. This is the
-- Vaughan lesson in a second jurisdiction: a count check cannot see a redraw
-- that preserves the count.
--
-- ⓘ `constituency_name_alias` is therefore NOT used for EITHER rename. Per the
-- gotcha, that table is for two sources spelling the SAME district differently
-- (Kirkland's `Saint-Charles`/`St-Charles`). These two districts were genuinely
-- renamed, which makes the old name stale rather than alternative.
--
-- ⚠ It IS used once, for a different and genuinely aliasable case — Longueuil's
-- `Fatima-Parcours-du-Cerf`. See step 6.
--
-- ★ LONGUEUIL: THE STAGED FILE WAS STILL STALE, AND THE CITY HAD PUBLISHED
-- ────────────────────────────────────────────────────────────────────────
-- A previous pass staged `longueuil-districts-2025.geojson` from Données
-- Québec and deliberately did not load it: the resource was dated 2024-03-01
-- and its 15 slugs were byte-identical to what we held. Re-probed 2026-08-28 —
-- that is STILL true. The Données Québec package `districts-electoraux-
-- longueuil` continues to serve the superseded 15-district map, and its
-- `CONSEILLER` field still names the 2021-25 council. The refusal was right and
-- remains right.
--
-- What changed is that the city publishes the current map elsewhere: its own
-- ArcGIS Online org (`h4XWvDXfYYyD6jNu`), item
-- `acb5405480754fd4a41734bd81fafbe6`, service `DO_DistrictElectoral`, now
-- carrying 18 districts and the 2025-elected councillors. `--compare`:
--
--     authoritative=18  held=16  matched=13
--     mean_overlap=75.8600%  min=41.0812%  below_95%=10
--     absent from our table (5): boise-fonrouge, boise-pilon,
--         croydon-iberville, longueuil-montreal-sud, ruisseau-masse
--     we hold, authority does not (3): 2458227, explorateurs, iberville
--
-- Ten of the thirteen surviving names moved below 95%; `georges-dor` kept 41%.
-- 15 -> 18 required a Charter amendment (PL 204, Loi concernant la Ville de
-- Longueuil, sanctioned 2024-02-14), so this was never going to be cosmetic.
--
-- ⓘ THE ARRONDISSEMENT TRAP DID NOT FIRE, though Longueuil was the live risk
-- for it. Sherbrooke's file mixed two tiers in one layer and a Lennoxville
-- address resolved to two districts. Longueuil's layer is ONE TIER: 18
-- districts, 10 Vieux-Longueuil / 7 Saint-Hubert / 1 Greenfield Park. District
-- 11 Greenfield Park is coterminous with its borough (hence exempt from the
-- ±15% rule at +21.03%), and the borough's 2 conseillers d'arrondissement are
-- elected borough-wide over that same polygon rather than over sub-districts.
-- So three people name `de Greenfield Park` and all three correctly resolve to
-- one polygon. No `kind_builder` needed; 20 councillors, 18 districts.
--
-- ★ THE DATES COME FROM INSTRUMENTS, AND THE INSTRUMENTS ARE NOT THE STORED DATE
-- ──────────────────────────────────────────────────────────────────────────────
--   Longueuil   Règlement CO-2024-1269, avis de motion 2024-04-16, adopted
--               2024-06-11, IN FORCE 2024-10-31. Toponyms attached later by
--               Règlement CO-2024-1293, adopted 2025-01-21, in force
--               2025-01-23.
--   Terrebonne  Règlement numéro 929, avis de motion 2024-05-07 (rés.
--               234-05-2024), zero oppositions certified 2024-05-24 against a
--               threshold of 500, adopted 2024-05-31 (rés. 262-05-2024), IN
--               FORCE 2024-10-31. CRE confirmed conformity 2024-08-23; council
--               adopted rés. 449-09-2024 on 2024-09-04 on the CRE's
--               recommendations, which forms part of the by-law (LERM art. 21).
--               R929 art. 4 expressly repeals Règlement 764 (2020-05-11) — the
--               map we held.
--
-- ⚠ BOTH IN-FORCE DATES ARE 2024-10-31 AND NEITHER IS STORED. That date is not
-- a coincidence and not a choice: LERM art. 30 fixes it by statute — "le
-- règlement divisant le territoire de la municipalité en districts électoraux
-- entre en vigueur le 31 octobre de l'année civile qui précède celle où doit
-- avoir lieu l'élection générale pour laquelle la division doit être
-- effectuée." Every Québec municipal division by-law for 2025 shares it.
-- Ruling A10.4 stores the election the map first governed instead, so both
-- generations are stamped 2025-11-02. The by-laws are what prove the redraw
-- happened and are recorded in the loader spec; they are not the stored date.
--
-- ⚠ AND IGNORE THE CITY'S OWN "19 SEPTEMBRE 2025". Longueuil's ArcGIS metadata
-- reads "en vigueur depuis le 19 septembre 2025, aux fins de l'élection du 2
-- novembre 2025". That is polling day minus 44 — the first day of the période
-- électorale (LERM art. 364) and of the nomination window named in the city's
-- own avis public d'élection. No instrument entered into force that day. It is
-- GIS shorthand, and it is exactly the kind of publisher-supplied date A10.4
-- exists to override.
--
-- ⛔ NEITHER MUNICIPALITY WENT THROUGH THE CRE ON THE MERITS. Élections Québec
-- lists four 2025 division decisions — Brossard, La Pêche, Saint-Aubert,
-- Saint-Cyrille-de-Wendover — and two public hearings; Longueuil and Terrebonne
-- are on neither list. Terrebonne's CRE contact was an administrative
-- conformity confirmation, not a hearing. So unlike Brossard, the city's own
-- delimitation is the one in force, and the city's own layer is authoritative.
--
-- ★ INDEPENDENT CORROBORATION OF TERREBONNE'S VINTAGE, without the by-law: the
-- city's ArcGIS org holds `districts_electoraux_vector_tile_archive_20251103`,
-- an archive copy cut the day after the election, and the live layer was
-- modified 2025-11-03. The publisher archived the old map and replaced it at
-- the election. Two independent bodies of evidence, same conclusion.
--
-- ⚠ ONE NAME IS TAKEN FROM THE BY-LAW, NOT THE LAYER. Terrebonne's GIS layer
-- writes district 2 as `Boisé Laurier`; Règlement 929 designates it `Du
-- Boisé-Laurier`, and so does MAMH. The loader's `_terrebonne_label` restores
-- the by-law form — which is also what keeps the district's existing id
-- `terrebonne-districts/du-boise-laurier` rather than minting a second id
-- (`boise-laurier`) for a district continuing under its own name. Confirmed by
-- the load reporting `slug_matches_existing=14` rather than 13.
--
-- ⛔ SCOPED BY SOURCE_SET, NEVER BY DISTRICT NAME. `saint-charles` is both
-- Longueuil's district and Kirkland's (aliased in 0120), and `District N`
-- exists in thirteen Québec sets. 0106 mis-counted 286 rows for scoping the
-- other way.
--
-- Forward-only. Apply with:
--   docker exec -i sw-db psql -U sw -d sovereignwatch -v ON_ERROR_STOP=1 \
--     < db/migrations/0121_longueuil_terrebonne.sql

BEGIN;

-- ── 0. The loads must have happened ─────────────────────────────────────────
DO $$
DECLARE n_lgl int; n_trb int;
BEGIN
    SELECT count(*) INTO n_lgl FROM constituency_boundaries
     WHERE source_set = 'longueuil-districts'
       AND boundaries_version = '2025' AND boundary_kind = 'district';
    IF n_lgl <> 18 THEN
        RAISE EXCEPTION 'Expected 18 authoritative Longueuil districts, found %. '
                        'Run `load-boundaries --jurisdiction longueuil-districts` '
                        'first.', n_lgl;
    END IF;

    SELECT count(*) INTO n_trb FROM constituency_boundaries
     WHERE source_set = 'terrebonne-districts'
       AND boundaries_version = '2025' AND boundary_kind = 'district';
    IF n_trb <> 16 THEN
        RAISE EXCEPTION 'Expected 16 authoritative Terrebonne districts, found %. '
                        'Run `load-boundaries --jurisdiction terrebonne-districts` '
                        'first.', n_trb;
    END IF;
END $$;

-- ── 1. Detach the members stranded on districts that no longer exist ────────
-- ⛔ MUST RUN BEFORE THE END-DATING, and must not be skipped on the reasoning
-- that `reattach-municipal-roster` will sort it out. The roster's attach passes
-- only ever fill a NULL `constituency_id` — they never overwrite one — so a
-- member left pointing at an end-dated district keeps that pointer forever and
-- silently reads as "attached".
--
-- Four members, and every one of them is a REAL 2025 councillor sitting for a
-- district that was renamed or dissolved under them:
--   longueuil-districts/explorateurs       Karl Ferraro
--   longueuil-districts/iberville          Alvaro Cueto
--   terrebonne-districts/grand-ruisseau    Claudia Abaunza
--   terrebonne-districts/cote-de-terrebonne Marie-Ève Couturier
--
-- ⚠ Marie-Ève Couturier is the sharpest illustration in this migration: the
-- city's own layer names her the councillor for `Côte de Terrebonne-Urbanova`,
-- and she was sitting attached to `cote-de-terrebonne` — the polygon that no
-- longer contains Urbanova. Right person, wrong ground.
--
-- ⓘ Scoped to ids the NEW live generation does not reproduce, so the 13
-- Longueuil and 14 Terrebonne members already on carried-over ids are left
-- alone. Their id survives the generation change; only the geometry beneath it
-- moves.
UPDATE politicians p
   SET constituency_id = NULL, updated_at = now()
 WHERE p.level = 'municipal'
   AND p.province_territory = 'QC'
   AND p.constituency_id IS NOT NULL
   AND split_part(p.constituency_id, '/', 1)
       IN ('longueuil-districts', 'terrebonne-districts')
   AND NOT EXISTS (
         SELECT 1 FROM constituency_boundaries b
          WHERE b.constituency_id = p.constituency_id
            AND b.boundaries_version = '2025');

UPDATE politician_terms t
   SET constituency_id = NULL
 WHERE t.level = 'municipal'
   AND t.province_territory = 'QC'
   AND t.constituency_id IS NOT NULL
   AND (t.ended_at IS NULL OR t.ended_at > now())
   AND split_part(t.constituency_id, '/', 1)
       IN ('longueuil-districts', 'terrebonne-districts')
   AND NOT EXISTS (
         SELECT 1 FROM constituency_boundaries b
          WHERE b.constituency_id = t.constituency_id
            AND b.boundaries_version = '2025');

-- ── 2. Retire Longueuil's mirror generation — DISTRICTS ONLY ────────────────
-- ⚠ 2025-11-01, the day before the election Règlement CO-2024-1269's map first
-- governed. END-DATED, NOT DELETED: unlike Sherbrooke in 0119 (a partial
-- ingest, whose 15 ids the new map reproduced exactly), this is a genuine
-- redraw and the old lines are a real record of the pre-2025 map. Two of them
-- (`explorateurs`, `iberville`) exist nowhere else.
-- ⚠ `boundary_kind = 'district'` protects `census-subdivisions/2458227`, the
-- StatCan city outline that lives inside this set. 0099 lost exactly this for
-- Québec's five boroughs.
UPDATE constituency_boundaries
   SET effective_to = DATE '2025-11-01', updated_at = now()
 WHERE source_set = 'longueuil-districts'
   AND boundaries_version = 'current'
   AND boundary_kind = 'district'
   AND effective_to IS NULL;

-- ── 3. Retire Terrebonne's mirror generation — DISTRICTS ONLY ───────────────
-- ⚠ Same reasoning; `census-subdivisions/2464008` is the protected outline.
UPDATE constituency_boundaries
   SET effective_to = DATE '2025-11-01', updated_at = now()
 WHERE source_set = 'terrebonne-districts'
   AND boundaries_version = 'current'
   AND boundary_kind = 'district'
   AND effective_to IS NULL;

-- ── 4. Assert exactly one live generation per municipality ──────────────────
-- ⛔ The check that would have caught a half-applied cutover. Both sets must
-- now show precisely one live district generation, of the right size. Note the
-- live-window filter — a bare count would happily pass with both generations
-- present.
DO $$
DECLARE n_lgl int; n_trb int; n_gen int;
BEGIN
    SELECT count(*) INTO n_lgl FROM constituency_boundaries
     WHERE source_set = 'longueuil-districts' AND boundary_kind = 'district'
       AND effective_from <= CURRENT_DATE
       AND (effective_to IS NULL OR effective_to >= CURRENT_DATE);
    IF n_lgl <> 18 THEN
        RAISE EXCEPTION 'Longueuil should have 18 live districts, has %', n_lgl;
    END IF;

    SELECT count(*) INTO n_trb FROM constituency_boundaries
     WHERE source_set = 'terrebonne-districts' AND boundary_kind = 'district'
       AND effective_from <= CURRENT_DATE
       AND (effective_to IS NULL OR effective_to >= CURRENT_DATE);
    IF n_trb <> 16 THEN
        RAISE EXCEPTION 'Terrebonne should have 16 live districts, has %', n_trb;
    END IF;

    SELECT count(DISTINCT boundaries_version) INTO n_gen
      FROM constituency_boundaries
     WHERE source_set IN ('longueuil-districts', 'terrebonne-districts')
       AND boundary_kind = 'district'
       AND effective_from <= CURRENT_DATE
       AND (effective_to IS NULL OR effective_to >= CURRENT_DATE);
    IF n_gen <> 1 THEN
        RAISE EXCEPTION 'Expected exactly 1 live district generation across both '
                        'sets, found %', n_gen;
    END IF;
END $$;

-- ── 5. Assert no live district polygon contains another's interior point ────
-- ⛔ THE CHECK THE COUNT AND THE OVERLAP COMPARISON BOTH MISS. Sherbrooke's
-- 2025 file shipped a borough seat whose polygon contained two district seats;
-- the count was right, every name matched, and mean overlap was 99.38%. Only a
-- point-in-polygon probe saw it. Longueuil was the live candidate for a repeat
-- (three arrondissements, one of them coterminous with a district), so the
-- assertion is made here rather than left to the session's manual run.
-- ⚠ Scoped to the two sets so this cannot be tripped by Lennoxville, which is a
-- correct two-district answer by design.
-- ⚠ `n_overlap`, never `overlaps` — that is a reserved SQL keyword.
DO $$
DECLARE n_overlap int;
BEGIN
    WITH live AS (
        SELECT constituency_id,
               ST_CollectionExtract(ST_MakeValid(boundary), 3) AS g
          FROM constituency_boundaries
         WHERE source_set IN ('longueuil-districts', 'terrebonne-districts')
           AND boundary_kind = 'district'
           AND effective_from <= CURRENT_DATE
           AND (effective_to IS NULL OR effective_to >= CURRENT_DATE)
    ), probe AS (
        SELECT constituency_id, ST_PointOnSurface(g) AS p FROM live
    )
    SELECT count(*) INTO n_overlap
      FROM probe pr
      JOIN live l ON l.constituency_id <> pr.constituency_id
                 AND ST_Contains(l.g, pr.p);
    IF n_overlap <> 0 THEN
        RAISE EXCEPTION 'Longueuil/Terrebonne districts overlap: % interior '
                        'point(s) fall inside another district', n_overlap;
    END IF;
END $$;

-- ── 6. The one genuine spelling divergence: Fatima-Parcours-du-Cerf ─────────
-- ⛔ THIS IS NOT A RENAME, AND THAT IS THE WHOLE POINT OF PUTTING IT HERE
-- rather than in the polygon's own name. The district is called
-- `Fatima-Parcours-du-Cerf` by the City of Longueuil in Règlement CO-2024-1293,
-- by the city's ArcGIS layer, and by the 15-district map we held BEFORE the
-- redraw. Its name did not change across the redistribution — both generations
-- agree. MAMH's `Elec2025_Mun.csv` alone writes it `de Fatima-du
-- Parcours-du-Cerf`, inserting an interior `du` that no municipal instrument
-- contains.
--
-- So this is two sources spelling ONE district differently, which is exactly
-- what `constituency_name_alias` is for, and it is the same shape as Montréal's
-- `Étienne-Desmarteaux`/`Étienne-Desmarteau` in 0120: the municipality is the
-- naming authority for its own districts, and the provincial CSV carries the
-- variant. Renaming the polygon to match MAMH would make our name disagree with
-- the by-law, and would re-key a district id that has been stable across a
-- redistribution.
--
-- ⚠ It also predates this cutover — Marc-Antoine Azouz was unattached under the
-- 15-district map for the same reason. Loading the correct 18-district map
-- attached five of Longueuil's six flagged councillors on the article-fallback
-- pass; this sixth one was never a geometry problem at all.
--
-- ⚠ `alias_slug` is `cpd_slugify()` of the roster's RAW spelling, article and
-- all — that is the key both `municipal_reattach` and `boundary_coverage` join
-- on, and stripping the article here would silently never match.
--
-- ⓘ DO NOTHING, not DO UPDATE: re-running must not repoint an alias an operator
-- has since corrected by hand. Same discipline as 0119's Kirkland row.
INSERT INTO constituency_name_alias (council, alias_slug, target_slug, reason)
VALUES (
  'longueuil', 'de-fatima-du-parcours-du-cerf', 'fatima-parcours-du-cerf',
  'MAMH''s Elec2025_Mun.csv writes Longueuil''s district 3 as "de Fatima-du '
  'Parcours-du-Cerf". The City of Longueuil writes it "Fatima-Parcours-du-Cerf" '
  '— in Règlement CO-2024-1293 (which designated all 18 toponyms), in its own '
  'ArcGIS open-data layer, and in the superseded 15-district map, so the name '
  'is unchanged across the 2025 redistribution and the interior "du" is MAMH''s '
  'alone. Same district: Longueuil elects 18 district councillors against our '
  '18 polygons and the other 17 names agree once the leading French article is '
  'reconciled. Aliased ONTO the city''s spelling rather than re-keying the '
  'polygon, because the municipality is the naming authority for its own '
  'districts and the id has been stable across the redraw — the Étienne-'
  'Desmarteau reasoning in 0120.')
ON CONFLICT (council, alias_slug) DO NOTHING;

COMMIT;
