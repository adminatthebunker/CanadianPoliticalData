-- 0069 — BC roster merge (repairing a defect 0065 introduced) + NS seat count.
--
-- ★ THE BUG THIS FIXES IS MINE, AND IT IS LIVE
-- --------------------------------------------
-- `0065_british_columbia_boundary_cutover.sql` asserted the BOUNDARY count (93)
-- and never asserted the ROSTER count. The equivalent assertion was added two
-- migrations later, to NB in `0067`:
--
--     IF actives <> 49 THEN RAISE EXCEPTION ... 'Duplicate roster rows would
--     surface as districts with two MLAs.'
--
-- ...and never backported. BC therefore stands at **98 active provincial rows
-- for 93 seats with zero NULL constituency_id**, which means five districts
-- return TWO MLAs each through `/boundaries/lookup`, `/postcodes/:postcode` and
-- every rep-list endpoint. It has been that way since 0065 shipped.
--
-- ⚠ Before 0065 this was invisible: 41 BC politicians carried a NULL
-- constituency_id, so the duplicates had no boundary to attach to. Fixing the
-- boundaries is what surfaced it — the predicted "roster defects surface at
-- cutover, not boundary ones" pattern, exactly as with Ontario's op:doly-begum.
--
-- ⛔ WHY THIS IS A MERGE AND NOT NB's DEACTIVATION
-- -----------------------------------------------
-- NB's six duplicates were empty HTML-entity shells; deactivating them cost
-- nothing. BC's five are NOT empty — they carry **424 speeches**:
--
--     Tamara Davidson     334 speeches   (the opennorth twin has ZERO)
--     Debra Toporowski     65
--     Joan Phillip         25
--
-- Deactivating them would strand all 424 on an inactive row and erase them from
-- the sitting member's profile. Tamara Davidson is the clear case: her entire
-- speech history hangs off the row that is NOT the one linked to a boundary.
--
-- ⛔ DIRECTION OF THE MERGE, AND WHY IT IS NOT ARBITRARY
-- -----------------------------------------------------
-- Keep `opennorth:bc-legislature:*`, drop `direct:leg-bc-ca:*`. Three
-- independent reasons agree:
--
--   1. Only the opennorth rows carry `lims_member_id` — BC's native Legislative
--      Assembly ID (360, 363, 368, 384, 60). The `direct:` rows carry none. This
--      is the one-native-one-orphan precondition that
--      `scripts/merge_exact_name_orphan_dups.py` requires, and it satisfies the
--      "Cooke rule" (never merge two rows that EACH carry a distinct native ID).
--   2. The opennorth rows carry the Assembly's own spelling, which for four of
--      the five is an Indigenous traditional name that the anglicized `direct:`
--      row discards:
--
--        Á'a:líya Warbus                    vs  A'aliya Warbus
--        Qwulti'stunaat - Debra Toporowski  vs  Debra Toporowski
--        Laanas - Tamara Davidson           vs  Tamara Davidson
--        Amshen - Joan Phillip              vs  Joan Phillip
--
--      ⚠ There is no alias column on `politicians`, so the anglicized forms are
--      lost here. Acceptable — the `direct:` rows are April-2026 Wikipedia
--      transcriptions, not an authority — but `name_alt` is a real follow-up.
--   3. The fifth pair is NOT an orthographic variant and was checked separately:
--      `Rohini Arora` vs `Reah Arora`. Verified against the BC NDP caucus and
--      Assembly listings — she is **Rohini "Reah" Arora**; Rohini is the
--      published legal name. Same direction, different reason.
--
-- ⓘ These five are the residue of `scripts/dedupe_gap_vs_opennorth.sql`
-- (commit 1f94125), whose normaliser folds only `[^a-z0-9]+` and so could not
-- pair "laanas tamara davidson" with "tamara davidson", nor "a a l ya warbus"
-- with "a aliya warbus".
--
-- ⚠ AFTERCARE: `fill-bc` would recreate these rows. It is an unconditional
-- INSERT ... ON CONFLICT (source_id) DO UPDATE that ends with `is_active = true`,
-- keyed on a hardcoded April-2026 Python roster, and it is registered in NO
-- schedule, catalogue or whitelist. Do not run it. The `actives == seats`
-- assertion being added to `check-boundary-coverage` is the standing guard.
--
-- Forward-only. Apply with:
--   docker exec -i sw-db psql -U sw -d sovereignwatch -v ON_ERROR_STOP=1 \
--     < db/migrations/0069_bc_roster_merge_and_ns_seats.sql

BEGIN;

CREATE TEMP TABLE _bc_merge ON COMMIT DROP AS
SELECT o.id AS keep_id, d.id AS drop_id,
       o.name AS keep_name, d.name AS drop_name,
       o.constituency_name,
       -- ★ Snapshot BEFORE the move, so the post-condition can prove the 424
       -- speeches actually landed rather than merely not-erroring.
       (SELECT count(*) FROM speeches s WHERE s.politician_id = o.id)
         + (SELECT count(*) FROM speeches s WHERE s.politician_id = d.id)
         AS expect_speeches
  FROM politicians o
  JOIN politicians d
    ON  o.province_territory = 'BC' AND o.level = 'provincial' AND o.is_active
   AND  d.province_territory = 'BC' AND d.level = 'provincial' AND d.is_active
   AND  o.source_id LIKE 'opennorth:bc-legislature:%'
   AND  d.source_id LIKE 'direct:leg-bc-ca:%'
   AND  lower(o.constituency_name) = lower(d.constituency_name);

DO $$
DECLARE n int; bad int;
BEGIN
    SELECT count(*) INTO n FROM _bc_merge;
    IF n <> 5 THEN
        RAISE EXCEPTION
          'Expected exactly 5 BC duplicate pairs, found %. The roster changed '
          'since this migration was written — re-derive before applying.', n;
    END IF;
    -- ⛔ Refuse if any pair would merge two rows that each carry a native ID.
    SELECT count(*) INTO bad FROM _bc_merge m
      JOIN politicians k ON k.id = m.keep_id
      JOIN politicians dd ON dd.id = m.drop_id
     WHERE k.lims_member_id IS NOT NULL AND dd.lims_member_id IS NOT NULL
       AND k.lims_member_id IS DISTINCT FROM dd.lims_member_id;
    IF bad <> 0 THEN
        RAISE EXCEPTION
          'Cooke rule: % pair(s) carry two distinct lims_member_id values. '
          'Those are different people, not duplicates.', bad;
    END IF;
END $$;

-- ── 1. Move the content ─────────────────────────────────────────────────────
UPDATE speeches s SET politician_id = m.keep_id
  FROM _bc_merge m WHERE s.politician_id = m.drop_id;

UPDATE speech_references r SET politician_id = m.keep_id
  FROM _bc_merge m WHERE r.politician_id = m.drop_id;

UPDATE vote_positions v SET politician_id = m.keep_id
  FROM _bc_merge m WHERE v.politician_id = m.drop_id;

UPDATE bill_sponsors b SET politician_id = m.keep_id
  FROM _bc_merge m WHERE b.politician_id = m.drop_id;

UPDATE social_posts sp SET politician_id = m.keep_id
  FROM _bc_merge m WHERE sp.politician_id = m.drop_id;

UPDATE politician_committees c SET politician_id = m.keep_id
  FROM _bc_merge m WHERE c.politician_id = m.drop_id;

UPDATE politician_offices o SET politician_id = m.keep_id
  FROM _bc_merge m WHERE o.politician_id = m.drop_id;

-- ⚠ Preserve the audit trail rather than letting it cascade away with the row.
UPDATE politician_changes ch SET politician_id = m.keep_id
  FROM _bc_merge m WHERE ch.politician_id = m.drop_id;

-- Socials carry a unique index on (politician_id, platform, lower(handle)).
-- 13 of the 17 rows on the drop side duplicate a handle the keeper already has;
-- drop those, move the 4 that are genuinely new (a Bluesky account and three
-- constituency-office handles the opennorth scrape never saw).
DELETE FROM politician_socials sd
 USING _bc_merge m, politician_socials sk
 WHERE sd.politician_id = m.drop_id
   AND sk.politician_id = m.keep_id
   AND sk.platform = sd.platform
   AND lower(sk.handle) = lower(sd.handle);

UPDATE politician_socials sd SET politician_id = m.keep_id
  FROM _bc_merge m WHERE sd.politician_id = m.drop_id;

-- Terms: the keeper already holds 2-3 real terms sourced from Open North; the
-- drop side's single gap-filler term adds nothing but would double-count. Drop.
DELETE FROM politician_terms t
 USING _bc_merge m WHERE t.politician_id = m.drop_id;

-- ── 2. Retire the duplicate rows ────────────────────────────────────────────
DELETE FROM politicians p USING _bc_merge m WHERE p.id = m.drop_id;

-- ── 3. Nova Scotia is a 56-seat House ───────────────────────────────────────
-- Bills 203 and 205, Royal Assent 2026-04-09, split Inverness and created
-- Chéticamp-Margarees-Pleasant Bay; the by-election of 2026-06-23 seated Claude
-- Bourgeois (PC) in it. `jurisdiction_sources.seats` still said 55, which would
-- make the forthcoming `check-boundary-coverage` assertion certify the gap as
-- correct. (YT was checked at the same time and is already 21 — no change.)
UPDATE jurisdiction_sources SET seats = 56, updated_at = now()
 WHERE jurisdiction = 'NS' AND seats = 55;

-- ── Post-conditions ─────────────────────────────────────────────────────────
DO $$
DECLARE actives int; dupes int; orphans int; sp int;
BEGIN
    SELECT count(*) INTO actives FROM politicians
     WHERE province_territory='BC' AND level='provincial' AND is_active;
    IF actives <> 93 THEN
        RAISE EXCEPTION
          'Expected 93 active BC provincial politicians, found % (93 seats).',
          actives;
    END IF;

    SELECT count(*) INTO dupes FROM (
        SELECT constituency_id FROM politicians
         WHERE province_territory='BC' AND level='provincial' AND is_active
           AND constituency_id IS NOT NULL
         GROUP BY 1 HAVING count(*) > 1) d;
    IF dupes <> 0 THEN
        RAISE EXCEPTION '% BC districts still resolve to more than one MLA', dupes;
    END IF;

    SELECT count(*) INTO orphans FROM politicians p
     WHERE p.province_territory='BC' AND p.level='provincial' AND p.is_active
       AND p.constituency_id IS NULL;
    IF orphans <> 0 THEN
        RAISE EXCEPTION '% active BC MLAs left with no boundary', orphans;
    END IF;

    -- ★ The whole point of merging rather than deactivating: every speech that
    -- was on a dropped row must now be on its keeper.
    --
    -- ⚠ NOT "no BC speech sits on an inactive politician" — that is true of
    -- 613,315 rows belonging to legitimately retired former members, and an
    -- assertion that fires on correct data is worse than none.
    SELECT count(*) INTO sp FROM _bc_merge m
     WHERE (SELECT count(*) FROM speeches s WHERE s.politician_id = m.keep_id)
           <> m.expect_speeches;
    IF sp <> 0 THEN
        RAISE EXCEPTION
          '% of 5 merged BC politicians do not hold the combined speech count '
          'their pair had before the merge', sp;
    END IF;

    RAISE NOTICE 'BC: 93 of 93 districts resolve to exactly one sitting MLA';
END $$;

COMMIT;

SELECT refresh_map_views();
