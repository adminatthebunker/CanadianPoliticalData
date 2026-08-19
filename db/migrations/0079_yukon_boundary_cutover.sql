-- 0079 — Yukon: adopt the 21-district map, RETIRE the 2015 map rather than
--        delete it, and rebuild a roster that was showing a defunct legislature.
--
-- ⛔ WE WERE SERVING THE 35th ASSEMBLY, NINE MONTHS AFTER IT ENDED
-- ----------------------------------------------------------------
-- Yukon held 19 boundaries against 21 seats and **32 active members against 21
-- seats**. The cause is not our retirement logic failing — it is that Open North
-- never dropped the old members, so `detect_retirements`, which deactivates only
-- what has DISAPPEARED from the upstream feed, correctly found nothing to do.
-- The feed itself was wrong. There is no plausibility gate on that path; SK has
-- one (`SK_RETIREMENT_ROSTER_FLOOR`) and nothing equivalent guards Open North.
--
-- Meanwhile the 13 `direct:yukonassembly-ca:*` rows — the ACTUAL current members
-- — came from `fill-yukon`, a hardcoded April-2026 Python roster that appears in
-- no schedule, catalogue or whitelist and unconditionally sets is_active = true.
--
-- ★ The 2025 result was established from two independent sources that agree
-- exactly: the published general-election result of 2025-11-03, and our own
-- `direct:` scrape of yukonassembly.ca. All 13 direct rows match the winners
-- name-for-name and district-for-district.
--
-- ── The boundaries ──────────────────────────────────────────────────────────
-- 21 authoritative vs 19 held: 15 slug-match, 6 are new, 4 held districts no
-- longer exist. Overlap on the 15 that survive is 67.37% mean with a 2.16%
-- MINIMUM — `porter-creek-south` retains 2% of its old shape. ⚠ A low overlap is
-- the CORRECT result here and confirms the diagnosis; a high one would have
-- meant the spec was wrong.
--
-- ⓘ Area is 485,298 km² against Yukon's 482,443 (+0.59%), the expected small
-- excess from generalised linework along the BC / NWT / Alaska borders.
--
-- ⛔ RETIRED, NOT DELETED — and this differs from BC, SK and NB deliberately.
-- Those three held geometry that had never been a real generation (old shapes
-- under new names), so deleting recorded no fiction. Yukon's 19 rows ARE a real
-- generation: 19 districts that genuinely governed from 2016 to 2025. Deleting
-- them would erase history we correctly hold.
--
-- ★ And they may be the only public machine-readable copy left: GeoYukon
-- republished the layer IN PLACE and the open.canada.ca mirrors were delisted.
-- Retiring costs one date column; deleting is irreversible.
--
-- Their `effective_from` is corrected to 2016-10-07 (Commissioner's Order
-- 2016/01, dissolution of the 33rd Assembly) from the fabricated 2023-01-01, and
-- `effective_to` is set to 2025-10-02 — the day BEFORE the new map took force,
-- so the two generations never both satisfy the current-date predicate.
--
-- ── In-force date ───────────────────────────────────────────────────────────
-- Electoral District Boundaries Act, S.Y. 2024, c. 14, assented 2024-11-21 but
-- in force ON DISSOLUTION of the 35th Assembly: **2025-10-03**.
-- ⛔ Not the assent date. Elections Yukon's own wording: "Until the next
-- territorial election is called and the Legislative Assembly dissolved, the
-- current 19 electoral districts and the 19 Members of the Legislative Assembly
-- remain unchanged." Using assent would assert the 21-district map governed for
-- the 11 months in which Yukon demonstrably had 19 members.
--
-- Run AFTER `load-boundaries --jurisdiction yukon`.
--
-- Forward-only. Apply with:
--   docker exec -i sw-db psql -U sw -d sovereignwatch -v ON_ERROR_STOP=1 \
--     < db/migrations/0079_yukon_boundary_cutover.sql

BEGIN;

DO $$
DECLARE n int;
BEGIN
    SELECT count(*) INTO n FROM constituency_boundaries
     WHERE constituency_id LIKE 'yukon-electoral-districts/%'
       AND boundaries_version = '2025';
    IF n <> 21 THEN
        RAISE EXCEPTION
          'Expected 21 authoritative YT rows, found %. Run '
          '`load-boundaries --jurisdiction yukon` first.', n;
    END IF;
END $$;

-- ── 1. Retire the 2015 generation onto the generation-free prefix ───────────
-- ⚠ No conflict with the 21 new rows: the unique key is
-- (constituency_id, boundaries_version), and these become version '2015'.
UPDATE constituency_boundaries
   SET constituency_id = 'yukon-electoral-districts/'
                       || split_part(constituency_id, '/', 2),
       source_set = 'yukon-electoral-districts',
       boundaries_version = '2015',
       effective_from = DATE '2016-10-07',
       effective_to = DATE '2025-10-02',
       updated_at = now()
 WHERE constituency_id LIKE 'yukon-electoral-districts-2015/%';

UPDATE politicians
   SET constituency_id = 'yukon-electoral-districts/'
                       || split_part(constituency_id, '/', 2)
 WHERE constituency_id LIKE 'yukon-electoral-districts-2015/%';
UPDATE politician_terms
   SET constituency_id = 'yukon-electoral-districts/'
                       || split_part(constituency_id, '/', 2)
 WHERE constituency_id LIKE 'yukon-electoral-districts-2015/%';

-- ── 2. Three incumbents whose DISTRICT changed under them ───────────────────
-- ★ Easy to mistake for stale rows and deactivate. All three were re-elected on
-- 2025-11-03 in a district that was renamed or newly carved, and each is
-- individually confirmed:
--   Yvonne Clarke  Porter Creek Centre  -> Whistle Bend North          (new)
--   Patti McLeod   Watson Lake          -> Watson Lake-Ross River-Faro (redrawn)
--   Kate White     Takhini-Kopper King  -> Takhini                     (renamed)
-- ⚠ Yvonne Clarke matters most: `Porter Creek Centre` still EXISTS and is now
-- held by Ted Laking. Deactivating her as a "duplicate" of Laking would have
-- removed a sitting member and left Whistle Bend North empty.
UPDATE politicians SET constituency_name = 'Whistle Bend North', updated_at = now()
 WHERE source_id = 'opennorth:yukon-legislature:yvonne-clarke' AND is_active;
UPDATE politicians SET constituency_name = 'Watson Lake-Ross River-Faro', updated_at = now()
 WHERE source_id = 'opennorth:yukon-legislature:patti-mcleod' AND is_active;
UPDATE politicians SET constituency_name = 'Takhini', updated_at = now()
 WHERE source_id = 'opennorth:yukon-legislature:kate-white' AND is_active;

-- ── 3. Deactivate the 11 members of the 35th Assembly who did not return ────
-- ⚠ Verified first that NO active Yukon row holds any speeches, votes, socials
-- beyond a handle, offices or terms worth moving — so unlike BC (0069) and NWT
-- (0075), where the duplicate held all the content and deactivating would have
-- stranded it, these are clean deactivations rather than merges.
--
-- Four of them sat for districts the 2024 Act ABOLISHED outright
-- (Mount Lorne-Southern Lakes, Pelly-Nisutlin, Takhini-Kopper King, Watson Lake);
-- the rest were defeated or did not run.
UPDATE politicians SET is_active = false, updated_at = now()
 WHERE province_territory = 'YT' AND level = 'provincial' AND is_active
   AND source_id IN (
     'opennorth:yukon-legislature:sandy-silver',            -- Klondike
     'opennorth:yukon-legislature:jeremy-harper',           -- Mayo-Tatchun
     'opennorth:yukon-legislature:jeanie-mclean',           -- Mountainview
     'opennorth:yukon-legislature:john-streicker',          -- district abolished
     'opennorth:yukon-legislature:stacey-hassard',          -- district abolished
     'opennorth:yukon-legislature:geraldine-van-bibber',    -- Porter Creek North
     'opennorth:yukon-legislature:ranj-pillai',             -- Porter Creek South
     'opennorth:yukon-legislature:nils-clarke',             -- Riverdale North
     'opennorth:yukon-legislature:tracy-anne-mcphee',       -- Riverdale South
     'opennorth:yukon-legislature:annie-blake',             -- Vuntut Gwitchin
     'opennorth:yukon-legislature:richard-mostyn'           -- Whitehorse West
   );

-- ── 4. Attach all 21 sitting members ────────────────────────────────────────
UPDATE politicians p SET constituency_id = NULL
 WHERE p.province_territory='YT' AND p.level='provincial' AND p.is_active;

UPDATE politicians p
   SET constituency_id = b.constituency_id, updated_at = now()
  FROM constituency_boundaries b
 WHERE p.province_territory='YT' AND p.level='provincial' AND p.is_active
   AND b.level='provincial' AND b.province_territory='YT'
   AND b.boundaries_version = '2025'
   -- ⚠ Join on the SLUG, not on `name`. Elections Yukon spaces its compound
   -- names ("Mayo - Tatchun", "Marsh Lake - Mount Lorne - Golden Horn") while
   -- our roster does not; slugify collapses both, so a text join on `name`
   -- would miss every hyphenated district.
   AND split_part(b.constituency_id, '/', 2)
     = regexp_replace(
         regexp_replace(lower(p.constituency_name), '[^a-z0-9]+', '-', 'g'),
         '(^-|-$)', '', 'g');

DO $$
DECLARE bnd int; old int; actives int; attached int; dupes int; overlap int;
BEGIN
    SELECT count(*) INTO bnd FROM constituency_boundaries
     WHERE level='provincial' AND province_territory='YT'
       AND effective_from <= CURRENT_DATE
       AND (effective_to IS NULL OR effective_to >= CURRENT_DATE);
    IF bnd <> 21 THEN
        RAISE EXCEPTION 'Expected 21 current YT boundaries, found %', bnd;
    END IF;

    -- ★ The 2015 generation must still EXIST — retired, not deleted.
    SELECT count(*) INTO old FROM constituency_boundaries
     WHERE level='provincial' AND province_territory='YT'
       AND boundaries_version = '2015';
    IF old <> 19 THEN
        RAISE EXCEPTION
          'The 2015 Yukon generation should be retired and retained (19 rows), '
          'found % — it may be the only public copy left', old;
    END IF;

    -- And the two generations must never both be selectable.
    SELECT count(*) INTO overlap FROM constituency_boundaries
     WHERE level='provincial' AND province_territory='YT'
       AND effective_from <= DATE '2025-10-03'
       AND (effective_to IS NULL OR effective_to >= DATE '2025-10-03')
       AND boundaries_version = '2015';
    IF overlap <> 0 THEN
        RAISE EXCEPTION
          '% 2015 rows are still in force on the 2025-10-03 changeover date',
          overlap;
    END IF;

    SELECT count(*) INTO actives FROM politicians
     WHERE province_territory='YT' AND level='provincial' AND is_active;
    SELECT count(*) INTO attached FROM politicians
     WHERE province_territory='YT' AND level='provincial' AND is_active
       AND constituency_id IS NOT NULL;
    IF actives <> 21 OR attached <> 21 THEN
        RAISE EXCEPTION
          'Expected 21 sitting YT MLAs all attached, got % active / % attached',
          actives, attached;
    END IF;

    SELECT count(*) INTO dupes FROM (
        SELECT constituency_id FROM politicians
         WHERE province_territory='YT' AND level='provincial' AND is_active
         GROUP BY 1 HAVING count(*) > 1) d;
    IF dupes <> 0 THEN
        RAISE EXCEPTION '% YT districts resolve to more than one MLA', dupes;
    END IF;

    RAISE NOTICE 'YT: 21 of 21 districts, 21 MLAs of the 36th Assembly attached; 2015 map retired and retained';
END $$;

COMMIT;

SELECT refresh_map_views();
