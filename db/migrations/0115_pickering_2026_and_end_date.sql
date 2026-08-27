-- 0115 — Pickering: load the 2026 map dormant, and end-date its predecessor.
--
-- ★ ANOTHER "you do not need a start date to know an end date" case, after
-- Chatham-Kent and Haldimand in 0109. Pickering's CURRENT boundaries have no
-- established in-force date, so their mirror rows stay and keep their false
-- 2023-01-01 start. But By-law 8196/25 puts the successor in force for the
-- 2026-10-26 election, so the current map demonstrably ENDS on 2026-10-25
-- whatever day it began.
--
-- ⛔ Without this end-date the two generations would both be live from election
-- morning — the defect I built into Ottawa and London and had to fix in 0112.
-- Loading a dormant successor without closing its predecessor is not half a
-- job, it is a scheduled outage.
--
-- ★ Dated from an instrument with a resolved tribunal step: By-law 8196/25,
-- passed by Council 2025-07-15, appealed to the Ontario Land Tribunal
-- 2025-08-29, appeal **WITHDRAWN 2025-10-06**. Third Ontario case of this shape
-- after Haldimand's 2588/25 (OLT dismissed) and Markham's 2013-29 (OMB
-- dismissed).
--
-- ⚠ THE COUNT CANNOT TELL THE TWO MAPS APART — three wards before and after,
-- each electing a city and a regional councillor. Ruling A7 with nothing else
-- to fall back on, as with Ottawa and Burlington.
--
-- ⚠ What 8196/25 supersedes is worth recording: a 2021 ward boundary review had
-- ALREADY adopted new boundaries to take effect for 2026. Council reopened it
-- on 2025-01-27 against updated population data and replaced it. A map adopted
-- in 2021 that will now never govern an election is not a generation to hold —
-- ruling A10.4 keys on the election a map GOVERNED, and that one governs none.
--
-- ⚠ Pickering's published current layer carries two zero-area sliver polygons
-- labelled "Ward 1" beside its three real wards, so a naive feature count reads
-- 5 for a 3-ward city. The mirror rows we hold are the correct three.
--
-- Forward-only. Apply with:
--   docker exec -i sw-db psql -U sw -d sovereignwatch -v ON_ERROR_STOP=1 \
--     < db/migrations/0115_pickering_2026_and_end_date.sql

BEGIN;

DO $$
DECLARE fut int; cur int;
BEGIN
    SELECT count(*) INTO fut FROM constituency_boundaries
     WHERE source_set = 'pickering-wards' AND boundaries_version = '2026'
       AND boundary_kind = 'district';
    IF fut <> 3 THEN
        RAISE EXCEPTION 'Expected 3 Pickering 2026 wards, found % — run the '
          'load first', fut;
    END IF;
    SELECT count(*) INTO cur FROM constituency_boundaries
     WHERE source_set = 'pickering-wards' AND boundaries_version = 'current'
       AND boundary_kind = 'district';
    IF cur <> 3 THEN
        RAISE EXCEPTION 'Expected 3 current Pickering wards to end-date, found %',
                        cur;
    END IF;
END $$;

UPDATE constituency_boundaries
   SET effective_to = DATE '2026-10-25', updated_at = now()
 WHERE source_set = 'pickering-wards'
   AND boundaries_version = 'current'
   AND boundary_kind = 'district'
   AND effective_to IS NULL;

DO $$
DECLARE live int; dormant int; n_overlap int; orphans int;
BEGIN
    SELECT count(*) INTO live FROM constituency_boundaries
     WHERE source_set = 'pickering-wards' AND boundary_kind = 'district'
       AND effective_from <= CURRENT_DATE
       AND (effective_to IS NULL OR effective_to >= CURRENT_DATE);
    IF live <> 3 THEN
        RAISE EXCEPTION 'Pickering has % live wards today, expected 3', live;
    END IF;

    SELECT count(*) INTO dormant FROM constituency_boundaries
     WHERE source_set = 'pickering-wards' AND boundaries_version = '2026'
       AND effective_from > CURRENT_DATE;
    IF dormant <> 3 THEN
        RAISE EXCEPTION 'Expected 3 dormant 2026 wards, found %', dormant;
    END IF;

    -- The 0112 invariant, applied table-wide rather than to this set alone.
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

    SELECT count(*) INTO orphans FROM politicians p
     WHERE p.is_active AND p.constituency_id IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM constituency_boundaries b
                        WHERE b.constituency_id = p.constituency_id);
    IF orphans <> 0 THEN
        RAISE EXCEPTION 'orphaned % sitting members', orphans;
    END IF;

    RAISE NOTICE 'Pickering: 3 live now, 3 dormant from 2026-10-26, no overlap';
END $$;

COMMIT;

SELECT refresh_map_views();
