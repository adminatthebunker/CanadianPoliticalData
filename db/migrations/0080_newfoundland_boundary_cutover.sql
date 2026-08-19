-- 0080 — Newfoundland and Labrador: the last province onto an authoritative
--        source, and a roster still showing the 49th General Assembly.
--
-- ★ ALREADY GENERATION-FREE. NL is the one jurisdiction whose `constituency_id`
-- prefix never carried a year, so there is nothing to re-key: the outgoing rows
-- and the incoming ones share an id and differ only by `boundaries_version`
-- ('current' -> '2015-commission'). Both therefore satisfied the current-date
-- predicate the moment the load finished, which is why this runs immediately
-- after it.
--
-- ── The geometry we held was a fifth of the resolution and a fifth short ────
--   authoritative 40 | held 36 | matched 36
--   mean overlap 94.4847%, min 5.37%, 3 below 95%
--   total area: 322,413 km² held  vs  405,904 km² authoritative
--
-- NL's real area is 405,212 km² (373,872 land + 31,340 fresh water), so the
-- authoritative set matches reality to **+0.17%** while the Open North mirror
-- was missing **83,491 km² — a fifth of the province**. Four districts absent
-- outright (Burgeo-La Poile, Humber-Gros Morne, Labrador West, St. John's
-- East-Quidi Vidi), and two more — `windsor-lake` at 5.37% and `corner-brook` at
-- 5.52% — barely overlapping their real counterparts, the same
-- absorbed-by-a-neighbour pattern Nova Scotia's Inverness showed.
--
-- Deleted rather than retired: these are a degraded copy of the SAME 2015
-- generation, not a superseded one. (Contrast Yukon in 0079, whose 19 rows are a
-- genuine prior generation and are retained.)
--
-- ⛔ THE CUSTOM PROJECTION, AND HOW IT WAS VERIFIED
-- ------------------------------------------------
-- NL publishes in `SESA-TM`, which has NO EPSG code: Transverse Mercator, CM
-- -59.5, scale factor **0.998** (not UTM's 0.9996), false easting **1,000,000**
-- (not 500,000), datum **WGS84** (not NAD83). It is declared as a proj4 string
-- rather than guessed at a code, and — because a wrong CRS still "works", it
-- just puts the polygons somewhere else — it was checked against reality rather
-- than assumed:
--     summed area  405,904 km²  vs  405,212 actual   (+0.17%)
--     bbox lon     -67.8177 .. -52.6194  vs  -67.8 .. -52.6
--     bbox lat      46.6107 ..  60.3789  vs   46.6 ..  60.4
-- ⚠ NL's PRIOR generation is EPSG:2961, a different CRS on a different datum.
-- SRID is per FILE, never per jurisdiction.
--
-- ⛔ AND THE AUTHORITY'S OWN DATA CONTAINS A TYPO IN ITS ONLY KEY FIELD
-- ---------------------------------------------------------------------
-- `DIST_NAME` is the ENTIRE attribute schema — no district number, no usable
-- OBJECTID — and district 7 is spelled `Cartwright - L'Anse aux Clair`. The
-- correct name is `L'Anse au Clair`; "aux Clair" is ungrammatical and names no
-- place. Three independent confirmations, one of them the publisher's own site:
-- Elections NL serves that district's poll map at
-- `…/pollmaps/Cartwright%20-%20L'Anse%20au%20Clair.pdf`, its own 2011 file
-- spells it "au", and our rows do too. **This is the one case in the corpus
-- where the authority is wrong and we are right.**
--
-- Handled by the loader's `name_fixups`, added for this case: an exact-match
-- correction applied before anything reads the name, reported as `name_fixups=1`
-- so the day the agency fixes its own data is visible. ⛔ The staged file is NOT
-- edited — it is the byte-for-byte artifact the agency published.
--
-- ── The roster was showing the previous House ───────────────────────────────
-- 48 active members for 40 seats. Same structural cause as Yukon: Open North
-- never dropped the members defeated on 2025-10-14, so `detect_retirements` —
-- which deactivates only what has vanished from the feed — correctly found
-- nothing to do. The feed was wrong.
--
-- The 8 to deactivate were derived TWICE, independently, and the two agree
-- exactly:
--   • from Elections NL's official 2025 result (gov.nl.ca/releases/2025/
--     elections/1015n01), district by district; and
--   • structurally — an `opennorth:` row whose district is also held by a
--     `direct:assembly-nl-ca:` row.
-- 12 direct winners + 28 re-elected opennorth members = 40. ✓
--
-- ⚠ DEACTIVATED, NOT MERGED, and the distinction matters. These 8 hold real
-- speeches, but unlike BC (0069) and NWT (0075) they are DIFFERENT PEOPLE from
-- their successors — Gerry Byrne is not Jim Parsons. Their speeches belong to
-- them and stay with them, exactly as the 613,315 speeches of retired BC members
-- do.
--
-- Run AFTER `load-boundaries --jurisdiction newfoundland-labrador`.
--
-- Forward-only. Apply with:
--   docker exec -i sw-db psql -U sw -d sovereignwatch -v ON_ERROR_STOP=1 \
--     < db/migrations/0080_newfoundland_boundary_cutover.sql

BEGIN;

DO $$
DECLARE n int;
BEGIN
    SELECT count(*) INTO n FROM constituency_boundaries
     WHERE level='provincial' AND province_territory='NL'
       AND boundaries_version = '2015-commission';
    IF n <> 40 THEN
        RAISE EXCEPTION
          'Expected 40 authoritative NL rows, found %. Run '
          '`load-boundaries --jurisdiction newfoundland-labrador` first.', n;
    END IF;
END $$;

-- ── 0. A SQL slugify that matches the loader's, exactly ─────────────────────
-- ⛔ Added here because hand-writing this regex per migration is a bug factory,
-- and it just bit: the naive
--   regexp_replace(lower(name), '[^a-z0-9]+', '-', 'g')
-- turns "St. John's Centre" into `st-john-s-centre`, while the loader's
-- `slugify()` produces `st-johns-centre` — it strips apostrophes and periods
-- BEFORE collapsing everything else to hyphens. Seven of Newfoundland's forty
-- districts failed to attach on the first attempt for exactly that reason.
--
-- ⚠ Yukon's 0079 used the naive form and produced 21/21 only because no Yukon
-- district name contains an apostrophe or a period. It was right by luck.
--
-- Mirrors `boundary_loader.slugify()` step for step:
--   NFKD + strip combining  ->  unaccent()
--   lower                   ->  lower()
--   drop apostrophes/periods
--   [^a-z0-9]+ -> '-'
--   strip leading/trailing '-'
-- ⚠ Keep the two in sync; if slugify() changes, change this.
CREATE OR REPLACE FUNCTION cpd_slugify(name text) RETURNS text AS $fn$
  SELECT trim(both '-' from
           regexp_replace(
             regexp_replace(lower(unaccent($1)), '[''’.]', '', 'g'),
             '[^a-z0-9]+', '-', 'g'))
$fn$ LANGUAGE sql IMMUTABLE STRICT;

-- ── 1. Retire the members defeated on 2025-10-14 ────────────────────────────
UPDATE politicians SET is_active = false, updated_at = now()
 WHERE province_territory='NL' AND level='provincial' AND is_active
   AND source_id IN (
     'opennorth:newfoundland-labrador-legislature:steve-crocker',      -- Carbonear-Trinity-Bay de Verde
     'opennorth:newfoundland-labrador-legislature:gerry-byrne',        -- Corner Brook
     'opennorth:newfoundland-labrador-legislature:john-haggie',        -- Gander
     'opennorth:newfoundland-labrador-legislature:perry-trimper',      -- Lake Melville
     'opennorth:newfoundland-labrador-legislature:derek-bennett',      -- Lewisporte-Twillingate
     'opennorth:newfoundland-labrador-legislature:krista-lynn-howell', -- St. Barbe-L'Anse aux Meadows
     'opennorth:newfoundland-labrador-legislature:scott-reid',         -- St. George's-Humber
     'opennorth:newfoundland-labrador-legislature:siobhan-coady'       -- St. John's West
   );

-- ── 2. Drop the degraded mirror ─────────────────────────────────────────────
DELETE FROM constituency_boundaries
 WHERE level='provincial' AND province_territory='NL'
   AND boundaries_version = 'current';

-- ── 3. Attach all 40 sitting members ────────────────────────────────────────
-- ⚠ Joined on the SLUG, not on `name`. Three spellings of the same districts are
-- in play — the authority uses a SPACED hyphen ("Baie Verte - Green Bay"), our
-- opennorth rows an unspaced EM DASH ("Baie Verte—Green Bay"), and our direct
-- rows a plain hyphen. slugify collapses all three; a text join on `name` would
-- miss most of the province.
UPDATE politicians SET constituency_id = NULL
 WHERE province_territory='NL' AND level='provincial' AND is_active;

UPDATE politicians p
   SET constituency_id = b.constituency_id, updated_at = now()
  FROM constituency_boundaries b
 WHERE p.province_territory='NL' AND p.level='provincial' AND p.is_active
   AND b.level='provincial' AND b.province_territory='NL'
   AND b.boundaries_version = '2015-commission'
   AND split_part(b.constituency_id, '/', 2) = cpd_slugify(p.constituency_name);

DO $$
DECLARE bnd int; dupes int; orphans int; actives int; attached int;
        area numeric; vacant int;
BEGIN
    SELECT count(*) INTO bnd FROM constituency_boundaries
     WHERE level='provincial' AND province_territory='NL'
       AND effective_from <= CURRENT_DATE
       AND (effective_to IS NULL OR effective_to >= CURRENT_DATE);
    IF bnd <> 40 THEN
        RAISE EXCEPTION 'Expected 40 current NL boundaries, found %', bnd;
    END IF;

    SELECT count(*) INTO dupes FROM (
        SELECT constituency_id FROM constituency_boundaries
         WHERE level='provincial' AND province_territory='NL'
           AND effective_from <= CURRENT_DATE
           AND (effective_to IS NULL OR effective_to >= CURRENT_DATE)
         GROUP BY 1 HAVING count(*) > 1) d;
    IF dupes <> 0 THEN
        RAISE EXCEPTION 'NL cutover left % duplicated districts', dupes;
    END IF;

    SELECT count(*) INTO orphans FROM politicians p
     WHERE p.constituency_id LIKE 'newfoundland-and-labrador-electoral-districts%'
       AND NOT EXISTS (SELECT 1 FROM constituency_boundaries b
                        WHERE b.constituency_id = p.constituency_id);
    IF orphans <> 0 THEN
        RAISE EXCEPTION 'NL cutover left % orphaned politician rows', orphans;
    END IF;

    SELECT count(*) INTO actives FROM politicians
     WHERE province_territory='NL' AND level='provincial' AND is_active;
    SELECT count(*) INTO attached FROM politicians
     WHERE province_territory='NL' AND level='provincial' AND is_active
       AND constituency_id IS NOT NULL;
    IF actives <> 40 OR attached <> 40 THEN
        RAISE EXCEPTION
          'Expected 40 sitting NL MHAs all attached, got % active / % attached',
          actives, attached;
    END IF;

    SELECT count(*) INTO vacant FROM constituency_boundaries b
     WHERE b.level='provincial' AND b.province_territory='NL'
       AND NOT EXISTS (SELECT 1 FROM politicians p
                        WHERE p.is_active AND p.constituency_id = b.constituency_id);
    IF vacant <> 0 THEN
        RAISE EXCEPTION '% NL districts have no sitting member', vacant;
    END IF;

    -- ★ The projection check, as an assertion rather than a note. A wrong proj4
    -- for SESA-TM would still load; it would just put Newfoundland somewhere
    -- else. 405,212 km² is the province's real area.
    SELECT sum(area_sqkm)::numeric INTO area FROM constituency_boundaries
     WHERE level='provincial' AND province_territory='NL'
       AND effective_from <= CURRENT_DATE
       AND (effective_to IS NULL OR effective_to >= CURRENT_DATE);
    IF area < 395000 OR area > 415000 THEN
        RAISE EXCEPTION
          'NL total area % km² is outside the plausible band for a 405,212 km² '
          'province — the SESA-TM proj4 string is wrong', round(area);
    END IF;

    RAISE NOTICE 'NL: 40 of 40 districts, % km², 40 MHAs of the 50th General Assembly attached',
      round(area);
END $$;

COMMIT;

SELECT refresh_map_views();
