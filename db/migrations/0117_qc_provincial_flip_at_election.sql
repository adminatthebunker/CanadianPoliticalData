-- 0117 — Québec's 2026 provincial map flips at the election, not at the
--        legal in-force date.
--
-- WHY
-- ───
-- Élections Québec's 2026 map is legally in force 2026-08-29. Migration 0070
-- end-dated the 2017 map at 2026-08-28 accordingly. But the map does not
-- *govern* anything until the fixed-date general election on 2026-10-05 (first
-- Monday of October, Election Act s.129; the previous general election was
-- 2022-10-03).
--
-- Flipping on the legal date produces six weeks in which the database asserts
-- two things that are not true:
--
--   1. Six sitting MNAs represent districts that have never held an election.
--      arthabaska → arthabaska-lerable, johnson → daniel-johnson,
--      laporte → pierre-laporte, matane-matapedia → matane-matapedia-mitis,
--      riviere-du-loup-temiscouata → …-les-basques, vimont → vimont-auteuil.
--      Their constituency_id stops resolving to a live boundary on the 29th.
--   2. Québec has 127 seats. It has 125 filled seats until October; the two
--      new divisions (bellefeuille, marie-lacoste-gerin-lajoie) have no member.
--
-- This applies ruling A10.4 — "the in-force date is the election the boundaries
-- first governed" — to a provincial map. Until now A10.4 has only been used
-- municipally, most recently for the six Ontario 2026 maps loaded dormant at
-- 2026-10-26. Federal already behaves this way: the 2023 representation order
-- took effect at a dissolution, not at proclamation. Québec provincial was the
-- last place the programme had not applied its own rule.
--
-- ⚠ FOLLOW-UP DUE 2026-10-05. jurisdiction_sources.seats for QC must go
--    125 → 127 in the same change that ingests the general election result.
--    Until then 125 is correct — it is how many seats are filled. Doing it
--    early makes check-boundary-coverage red for six weeks; doing it late
--    makes it red from election day. The new `pending-flip` sentinel check
--    surfaces this from 2026-08-06 onward.
--
-- ⓘ The loader spec at boundary_loader.py stamps effective_from for this
--    generation. It is changed in the same commit; a migration alone would be
--    reverted by the next `load-boundaries --set quebec`.

BEGIN;

UPDATE constituency_boundaries
   SET effective_to = DATE '2026-10-04'
 WHERE level = 'provincial'
   AND province_territory = 'QC'
   AND boundaries_version = '2017';

UPDATE constituency_boundaries
   SET effective_from = DATE '2026-10-05'
 WHERE level = 'provincial'
   AND province_territory = 'QC'
   AND boundaries_version = '2026';

DO $$
DECLARE
    n_today    int;
    n_eve      int;
    n_election int;
    n_overlap  int;   -- ⛔ never name this `overlaps`: OVERLAPS is a reserved
                      --    SQL keyword (the period operator) and `IF overlaps
                      --    <> 0` is a syntax error. Cost an hour in 0112.
    n_gap      int;
    n_orphan   int;
BEGIN
    -- The live count on three dates that matter.
    SELECT count(*) INTO n_today FROM constituency_boundaries
     WHERE level='provincial' AND province_territory='QC'
       AND effective_from <= CURRENT_DATE
       AND (effective_to IS NULL OR effective_to >= CURRENT_DATE);

    SELECT count(*) INTO n_eve FROM constituency_boundaries
     WHERE level='provincial' AND province_territory='QC'
       AND effective_from <= DATE '2026-10-04'
       AND (effective_to IS NULL OR effective_to >= DATE '2026-10-04');

    SELECT count(*) INTO n_election FROM constituency_boundaries
     WHERE level='provincial' AND province_territory='QC'
       AND effective_from <= DATE '2026-10-05'
       AND (effective_to IS NULL OR effective_to >= DATE '2026-10-05');

    IF n_today <> 125 THEN
        RAISE EXCEPTION 'expected 125 live QC districts today, found %', n_today;
    END IF;
    IF n_eve <> 125 THEN
        RAISE EXCEPTION 'expected 125 live QC districts on 2026-10-04, found %', n_eve;
    END IF;
    IF n_election <> 127 THEN
        RAISE EXCEPTION 'expected 127 live QC districts on 2026-10-05, found %', n_election;
    END IF;

    -- No date on which both generations are live. Asserted as a window
    -- intersection rather than by sampling dates, so it holds everywhere.
    SELECT count(*) INTO n_overlap
      FROM constituency_boundaries a
      JOIN constituency_boundaries b
        ON a.level = b.level
       AND a.province_territory = b.province_territory
       AND a.boundaries_version < b.boundaries_version
     WHERE a.level='provincial' AND a.province_territory='QC'
       AND a.effective_from <= COALESCE(b.effective_to, DATE '9999-12-31')
       AND b.effective_from <= COALESCE(a.effective_to, DATE '9999-12-31');
    IF n_overlap <> 0 THEN
        RAISE EXCEPTION 'QC generations overlap in % row-pairs', n_overlap;
    END IF;

    -- ...and no gap either: the day after 2017 ends must be the day 2026 starts.
    SELECT count(*) INTO n_gap FROM constituency_boundaries
     WHERE level='provincial' AND province_territory='QC'
       AND boundaries_version='2017'
       AND effective_to + 1 <> DATE '2026-10-05';
    IF n_gap <> 0 THEN
        RAISE EXCEPTION 'QC 2017 does not abut 2026: % rows misdated', n_gap;
    END IF;

    -- The whole point: every sitting MNA still resolves to a LIVE district on
    -- the day the old flip would have detached them.
    SELECT count(*) INTO n_orphan
      FROM politicians p
     WHERE p.is_active AND p.level='provincial' AND p.province_territory='QC'
       AND p.constituency_id IS NOT NULL
       AND NOT EXISTS (
             SELECT 1 FROM constituency_boundaries b
              WHERE b.constituency_id = p.constituency_id
                AND b.effective_from <= DATE '2026-08-29'
                AND (b.effective_to IS NULL OR b.effective_to >= DATE '2026-08-29'));
    IF n_orphan <> 0 THEN
        RAISE EXCEPTION '% MNAs would still detach on 2026-08-29', n_orphan;
    END IF;

    RAISE NOTICE '0117 ok: QC 125 live today and 2026-10-04, 127 from 2026-10-05, 0 orphans';
END $$;

COMMIT;
