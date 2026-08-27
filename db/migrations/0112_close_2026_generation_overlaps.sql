-- 0112 — close two n_overlap I introduced in 0108, before they can fire.
--
-- ⛔ THIS IS THE 0084 DEFECT, RE-CREATED IN 0108 — and caught only because the
-- generations are future-dated, so it has not happened yet. Both would have
-- gone live silently on 2026-10-26.
--
--   london-wards   2018 generation carries NO effective_to, and its 2026
--                  successor starts 2026-10-26. From that morning BOTH are
--                  live, permanently — 28 polygons for 14 wards, every London
--                  address returning two councillors, forever.
--
--   ottawa-wards   2022 generation ends 2026-11-14 while its successor starts
--                  2026-10-26 — a 20-day window with both live.
--
-- ★ Ottawa's is the more interesting mistake, because the evidence that caused
-- it is quoted in 0108's own header. The city states two different dates:
-- the new boundaries "will serve as the basis for administering the municipal
-- elections on October 26, 2026", but "will take effect on November 15, 2026",
-- and the old ones are "in effect until November 14, 2026". I took the legal
-- effective date for the end of the old generation and the election date for
-- the start of the new one — each defensible on its own, and incoherent
-- together. Two sources of truth for one boundary is how a gap or an overlap
-- gets built.
--
-- ⚠ RULING A10.4 SETTLES IT AND THE WHOLE TABLE ALREADY FOLLOWS IT: municipal
-- generations are keyed on ELECTION dates, not on the day a council is
-- organised. Every date in this programme is an election date — 2006-11-13,
-- 2010-10-25, 2014-10-27, 2018-10-22, 2022-10-24. Ontario's Municipal Act
-- brings a ward by-law into force when the new council is organised, typically
-- mid-November, so a legally-precise model would move EVERY generation
-- boundary by a few weeks. That is a defensible alternative convention and it
-- is not the one this table uses; mixing the two for one city is strictly worse
-- than either.
--
-- So both predecessors end on election eve, 2026-10-25, matching Burlington,
-- Chatham-Kent and Haldimand which were already correct.
--
-- Forward-only. Apply with:
--   docker exec -i sw-db psql -U sw -d sovereignwatch -v ON_ERROR_STOP=1 \
--     < db/migrations/0112_close_2026_generation_overlaps.sql

BEGIN;

UPDATE constituency_boundaries
   SET effective_to = DATE '2026-10-25', updated_at = now()
 WHERE source_set IN ('london-wards', 'ottawa-wards')
   AND boundaries_version IN ('2018', '2022')
   AND boundary_kind = 'district';

DO $$
DECLARE n_overlap int; r record;
BEGIN
    -- ⛔ THE GENERAL CHECK, not just the two I know about: no municipal set may
    -- have two generations whose live windows intersect, at ANY future date.
    -- Keyed on the windows themselves rather than on the sets I happened to
    -- touch — an assertion that can only confirm what the UPDATE did is worth
    -- nothing, which is the lesson of 0093.
    SELECT count(*) INTO n_overlap FROM (
        SELECT a.source_set
          FROM constituency_boundaries a
          JOIN constituency_boundaries b
            ON b.source_set = a.source_set
           AND b.boundaries_version <> a.boundaries_version
           AND b.boundary_kind = 'district'
           AND a.boundary_kind = 'district'
           AND a.effective_from <= coalesce(b.effective_to, DATE '9999-12-31')
           AND b.effective_from <= coalesce(a.effective_to, DATE '9999-12-31')
         WHERE a.level = 'municipal'
         GROUP BY a.source_set) d;
    IF n_overlap <> 0 THEN
        FOR r IN
            SELECT DISTINCT a.source_set, a.boundaries_version AS va,
                   a.effective_from::date AS fa, a.effective_to::date AS ta,
                   b.boundaries_version AS vb, b.effective_from::date AS fb
              FROM constituency_boundaries a
              JOIN constituency_boundaries b
                ON b.source_set = a.source_set
               AND b.boundaries_version <> a.boundaries_version
               AND b.boundary_kind = 'district' AND a.boundary_kind = 'district'
               AND a.effective_from <= coalesce(b.effective_to, DATE '9999-12-31')
               AND b.effective_from <= coalesce(a.effective_to, DATE '9999-12-31')
             WHERE a.level = 'municipal'
        LOOP
            RAISE WARNING 'overlap: % % [%..%] vs % from %',
                r.source_set, r.va, r.fa, r.ta, r.vb, r.fb;
        END LOOP;
        RAISE EXCEPTION '% municipal sets still have overlapping generations',
                        n_overlap;
    END IF;

    RAISE NOTICE 'no municipal set has overlapping generations at any date';
END $$;

COMMIT;
