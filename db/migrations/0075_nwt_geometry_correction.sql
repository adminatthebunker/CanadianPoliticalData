-- 0075 — Northwest Territories: correct the geometry IN PLACE, and reunite the
--        Premier with his own speeches.
--
-- ⛔ THE DEFECT: right names, wrong shapes, for 6 of 19
-- ----------------------------------------------------
-- All 19 NWT rows name-matched the authoritative set exactly, so every
-- count-based check passed while the polygons were badly wrong. Measured against
-- Elections NWT immediately before this migration:
--
--     hay-river-south  26.03%      great-slave      30.64%
--     nunakput         45.12%      frame-lake       48.02%
--     hay-river-north  70.19%      (6 below 95%, mean 84.51%)
--
-- Two ADJACENT pairs with complementary over- and under-coverage — the signature
-- of misplaced shared boundaries — in Yellowknife and Hay River, the two places
-- with enough population for it to matter. NWT is the counter-example to
-- district-count checking: a perfect 19/19 count over demonstrably wrong shapes.
--
-- ★ REDRAW OR BAD MIRROR — the question that chose this migration's shape
-- -----------------------------------------------------------------------
-- Two dossiers disagreed. `impact.md` read it as a 2013→2023 redraw (⇒ load a
-- NEW generation and end-date the old). The NT dossier read it as a corrupt Open
-- North mirror (⇒ correct in place, keep the 2015 date). Operator ruling: the
-- mirror is unmaintained, correct in place — which is also the reversible
-- option, since fabricating a 2023 generation that never existed in law would
-- have to be unpicked later.
--
-- ⚠ The statute agrees with the ruling. LAECA s. 2(1) still reads "There are 19
-- electoral districts", and S.N.W.T. 2014 c. 21 came into force "on dissolution
-- of the 17th Legislative Assembly" (2015-10-25). No instrument since has
-- redrawn them, so there IS no 2023 generation to load — `ElectoralYear = 2023`
-- on every feature is a file-refresh stamp, not a legal vintage.
--
-- What the in-place load already did (0 inserted, 19 updated):
--     total area   2,192,291 km²  ->  1,609,305 km²
--     avg vertices         621    ->        5,930
--     French names             0  ->           19
--
-- ⓘ 1.61M km² still exceeds NWT's 1,346,106 km² land-plus-freshwater, and that
-- is CORRECT rather than a projection error: Nunakput alone is 564,266 km²
-- because Elections NWT's polygon extends over the Beaufort Sea and the Arctic
-- islands. The other 18 sum to ~1,045,000 km², right for the mainland. Do not
-- "fix" this.
--
-- Run AFTER `load-boundaries --jurisdiction northwest-territories`.
--
-- Forward-only. Apply with:
--   docker exec -i sw-db psql -U sw -d sovereignwatch -v ON_ERROR_STOP=1 \
--     < db/migrations/0075_nwt_geometry_correction.sql

BEGIN;

DO $$
DECLARE n int; pts numeric;
BEGIN
    SELECT count(*), avg(ST_NPoints(boundary)) INTO n, pts
      FROM constituency_boundaries
     WHERE level='provincial' AND province_territory='NT';
    IF n <> 19 THEN
        RAISE EXCEPTION 'Expected 19 NT rows, found %', n;
    END IF;
    -- The corrected geometry averages ~5,930 vertices; the mirror averaged 621.
    -- Refuse to proceed if the load has not happened.
    IF pts < 3000 THEN
        RAISE EXCEPTION
          'NT geometry still averages % vertices — run '
          '`load-boundaries --jurisdiction northwest-territories` first',
          round(pts);
    END IF;
END $$;

-- ── 1. The legal in-force date ──────────────────────────────────────────────
-- ⚠ effective_from is deliberately NOT in the loader's DO UPDATE SET (a
-- generation's dates are owned by migrations, so a re-run cannot un-retire
-- something), which is exactly why the in-place load left 2023-01-01 in place
-- and this statement is needed.
UPDATE constituency_boundaries
   SET effective_from = DATE '2015-10-25', updated_at = now()
 WHERE level='provincial' AND province_territory='NT'
   AND effective_from = DATE '2023-01-01';

-- ── 2. District names follow the authority ──────────────────────────────────
-- The load overwrote two display names with Elections NWT's spellings:
--     Mackenzie Delta   -> Mackenzie-Delta
--     Tu Nedhé-Wiilideh -> Tu Nedhé - Wiilideh
--
-- ★ The NT dossier recommended reverting to ours because they "read better".
-- Declining that, and aligning the ROSTER to the authority instead — the same
-- direction 0066 took for Saskatchewan, where three of our spellings were
-- corrected toward Elections Saskatchewan. The naming authority for a district
-- is the body that creates it; "reads better" is not a reason to overrule it,
-- and having the boundary and the roster disagree on screen is worse than either
-- spelling.
--
-- Slugs are unaffected either way, so nothing re-keys.
UPDATE politicians p
   SET constituency_name = b.name, updated_at = now()
  FROM constituency_boundaries b
 WHERE b.constituency_id = p.constituency_id
   AND p.province_territory='NT' AND p.level='provincial' AND p.is_active
   AND p.constituency_name IS DISTINCT FROM b.name;

-- ── 3. Reunite R.J. Simpson with his 349 speeches ───────────────────────────
-- ★ NWT carried 20 active rows for 19 seats. The extra is `Rj Simpson`
-- (`ntlegislativeassembly.ca:mla:rj-simpson`) with no district and no party,
-- duplicating `R.J. Simpson` (`opennorth:…:r.j.-simpson`), the sitting Premier
-- and MLA for Hay River North.
--
-- ⛔ Deactivating would have been wrong for the same reason as BC in 0069: the
-- duplicate holds **349 speeches** and the boundary-linked row holds **zero**.
-- Every word the Premier has said in the House hangs off the row that is not
-- attached to a district. This is a merge.
--
-- ⚠ `Rocky Simpson` (227 speeches, former member) is a DIFFERENT PERSON and is
-- untouched — which is why this targets an exact source_id rather than a name.
--
-- ★ The durable half is moving `nt_mla_slug`. `nt_mlas.py` resolves identity by
-- that column (`ON CONFLICT (nt_mla_slug)`) and only inserts a fresh row when it
-- finds no match. Moving the slug onto the keeper means the next
-- `ingest-nt-mlas` stamps the existing row instead of recreating the duplicate.
-- Deleting without moving it would just resurrect this on the next run.
CREATE TEMP TABLE _nt_merge ON COMMIT DROP AS
SELECT k.id AS keep_id, d.id AS drop_id, d.nt_mla_slug,
       (SELECT count(*) FROM speeches s WHERE s.politician_id = k.id)
         + (SELECT count(*) FROM speeches s WHERE s.politician_id = d.id)
         AS expect_speeches
  FROM politicians k, politicians d
 WHERE k.source_id = 'opennorth:northwest-territories-legislature:r.j.-simpson'
   AND d.source_id = 'ntlegislativeassembly.ca:mla:rj-simpson';

DO $$
DECLARE n int;
BEGIN
    SELECT count(*) INTO n FROM _nt_merge;
    IF n <> 1 THEN
        RAISE EXCEPTION
          'Expected exactly 1 NT merge pair, found % — the roster changed since '
          'this migration was written', n;
    END IF;
END $$;

UPDATE speeches s SET politician_id = m.keep_id
  FROM _nt_merge m WHERE s.politician_id = m.drop_id;
UPDATE speech_references r SET politician_id = m.keep_id
  FROM _nt_merge m WHERE r.politician_id = m.drop_id;
UPDATE vote_positions v SET politician_id = m.keep_id
  FROM _nt_merge m WHERE v.politician_id = m.drop_id;
UPDATE bill_sponsors b SET politician_id = m.keep_id
  FROM _nt_merge m WHERE b.politician_id = m.drop_id;
UPDATE politician_changes c SET politician_id = m.keep_id
  FROM _nt_merge m WHERE c.politician_id = m.drop_id;

-- Move the identity column BEFORE deleting, or the unique index blocks it.
UPDATE politicians d SET nt_mla_slug = NULL FROM _nt_merge m WHERE d.id = m.drop_id;
UPDATE politicians k SET nt_mla_slug = m.nt_mla_slug, updated_at = now()
  FROM _nt_merge m WHERE k.id = m.keep_id;

DELETE FROM politicians p USING _nt_merge m WHERE p.id = m.drop_id;

DO $$
DECLARE bnd int; actives int; attached int; dupes int; sp int; area numeric;
BEGIN
    SELECT count(*) INTO bnd FROM constituency_boundaries
     WHERE level='provincial' AND province_territory='NT'
       AND effective_from <= CURRENT_DATE
       AND (effective_to IS NULL OR effective_to >= CURRENT_DATE);
    IF bnd <> 19 THEN
        RAISE EXCEPTION 'Expected 19 current NT boundaries, found %', bnd;
    END IF;

    SELECT count(*) INTO actives FROM politicians
     WHERE province_territory='NT' AND level='provincial' AND is_active;
    SELECT count(*) INTO attached FROM politicians
     WHERE province_territory='NT' AND level='provincial' AND is_active
       AND constituency_id IS NOT NULL;
    IF actives <> 19 OR attached <> 19 THEN
        RAISE EXCEPTION
          'Expected 19 active NT MLAs all attached, got % active / % attached',
          actives, attached;
    END IF;

    SELECT count(*) INTO dupes FROM (
        SELECT constituency_id FROM politicians
         WHERE province_territory='NT' AND level='provincial' AND is_active
           AND constituency_id IS NOT NULL
         GROUP BY 1 HAVING count(*) > 1) d;
    IF dupes <> 0 THEN
        RAISE EXCEPTION '% NT districts resolve to more than one MLA', dupes;
    END IF;

    SELECT count(*) INTO sp FROM _nt_merge m
     WHERE (SELECT count(*) FROM speeches s WHERE s.politician_id = m.keep_id)
           <> m.expect_speeches;
    IF sp <> 0 THEN
        RAISE EXCEPTION 'the merged NT row does not hold the combined speech count';
    END IF;

    SELECT sum(area_sqkm)::numeric INTO area FROM constituency_boundaries
     WHERE level='provincial' AND province_territory='NT';
    RAISE NOTICE 'NT: 19 of 19 districts corrected in place, % km² (Nunakput carries the marine extent), 19 MLAs attached',
      round(area);
END $$;

COMMIT;

SELECT refresh_map_views();
