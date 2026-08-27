-- 0108 — retire the mirror generation for eight Ontario large cities.
--
-- Run AFTER `load-boundaries --jurisdiction {ottawa,hamilton,mississauga,
-- brampton,london,windsor,kingston,greater-sudbury}-wards` and the two
-- future-dated 2026 specs.
--
-- ★ THIS IS A PROVENANCE UPGRADE, NOT A GEOMETRY REPLACEMENT — with one
-- exception. `--compare` put all eight at 97.7% overlap or better against the
-- mirror, so the shapes were substantially right. What was wrong was
-- everything ELSE about the rows: no authority, no licence, and an
-- `effective_from` of 2023-01-01 that is wrong by between 1 and 20 years in
-- every case.
--
--   2006-11-13  Mississauga, Greater Sudbury   (twenty years old)
--   2010-10-25  Windsor
--   2014-10-27  Brampton, Kingston
--   2018-10-22  Hamilton, London
--   2022-10-24  Ottawa
--
-- ⚠ 2006-11-13 is a MONDAY IN NOVEMBER. Ontario's fixed fourth-Monday-of-
-- October election rule begins with 2010, so a date derived from that rule is
-- wrong for anything earlier — and two of these eight are earlier.
--
-- ★ THE EXCEPTION: WINDSOR GAINS A WARD IT NEVER HAD. We held 9 of 10; Ward 2
-- was simply absent, so addresses in it resolved to nothing. Same defect class
-- as Winnipeg's Elmwood in 0093 and Fort Erie's two wards in 0097 — a partial
-- ingest that no count check caught because nothing was comparing our count to
-- the council's.
--
-- ⛔ TWO FUTURE GENERATIONS ARE ALREADY LOADED AND MUST STAY DORMANT.
-- `ottawa-wards` version 2026 and `london-wards` version 2026 carry
-- effective_from = 2026-10-26 and are NOT live today. They are real, published,
-- by-law-backed maps for the next election, not comparators:
--   Ottawa   By-law 2025-5 (2025-01-22) amends wards 6, 9, 11, 13, 21, 24.
--            A per-ward area comparison found exactly those six moving and the
--            other 18 identical to 0.00% — the by-law's scope, recovered from
--            the geometry alone.
--   London   a genuine redraw: 13 of 14 wards move by more than 0.5%, ward 12
--            by -50.7%.
-- Ottawa additionally states its own end date, which no other city here does,
-- so its 2022 generation carries effective_to = 2026-11-14. The assertion below
-- checks both stay dormant — loading a future map as current would put the
-- wrong councillor against every address in those two cities for two months.
--
-- ⛔ SCOPED TO IDS THE AUTHORITATIVE GENERATION ACTUALLY REPLACED, so the
-- `census-subdivisions/*` municipality polygons that live INSIDE these ward
-- sets — and carry each city's mayor — survive. Same carve-out as 0093, and
-- the same reason: a ward file does not supersede a municipality polygon.
--
-- ⚠ Roster-neutral by construction, and this time that premise is CHECKED
-- rather than asserted in a comment: both generations carry the same
-- constituency_id, and the post-condition counts orphans directly.
--
-- Forward-only. Apply with:
--   docker exec -i sw-db psql -U sw -d sovereignwatch -v ON_ERROR_STOP=1 \
--     < db/migrations/0108_ontario_large_city_cutover.sql

BEGIN;

CREATE TEMP TABLE _sets(source_set text PRIMARY KEY, n int) ON COMMIT DROP;
INSERT INTO _sets VALUES
  ('ottawa-wards', 24), ('hamilton-wards', 15), ('mississauga-wards', 11),
  ('brampton-wards', 10), ('london-wards', 14), ('windsor-wards', 10),
  ('kingston-wards', 12), ('greater-sudbury-wards', 12);

DO $$
DECLARE r record; got int;
BEGIN
    FOR r IN SELECT * FROM _sets LOOP
        SELECT count(*) INTO got FROM constituency_boundaries
         WHERE source_set = r.source_set
           AND boundaries_version <> 'current'
           AND boundary_kind = 'district'
           AND effective_from <= CURRENT_DATE;
        IF got <> r.n THEN
            RAISE EXCEPTION '%: % authoritative live districts, expected % — '
              'run the load first', r.source_set, got, r.n;
        END IF;
    END LOOP;
END $$;

DELETE FROM constituency_boundaries old
 USING constituency_boundaries new
 WHERE old.source_set IN (SELECT source_set FROM _sets)
   AND old.boundaries_version = 'current'
   AND new.constituency_id = old.constituency_id
   AND new.source_set = old.source_set
   AND new.boundaries_version <> 'current';

DO $$
DECLARE dupes int; csds int; orphans int; dormant int; win int;
BEGIN
    -- No id live in two generations within these sets.
    SELECT count(*) INTO dupes FROM (
        SELECT constituency_id FROM constituency_boundaries
         WHERE source_set IN (SELECT source_set FROM _sets)
           AND effective_from <= CURRENT_DATE
           AND (effective_to IS NULL OR effective_to >= CURRENT_DATE)
         GROUP BY 1 HAVING count(*) > 1) d;
    IF dupes <> 0 THEN
        RAISE EXCEPTION 'cutover left % ids live in two generations', dupes;
    END IF;

    -- The mayoral polygons must survive.
    SELECT count(*) INTO csds FROM constituency_boundaries
     WHERE source_set IN (SELECT source_set FROM _sets)
       AND constituency_id LIKE 'census-subdivisions/%';
    IF csds < 6 THEN
        RAISE EXCEPTION 'only % mayoral census-subdivision polygons survived', csds;
    END IF;

    -- ⛔ The 2026 maps must still be dormant.
    SELECT count(*) INTO dormant FROM constituency_boundaries
     WHERE source_set IN ('ottawa-wards', 'london-wards')
       AND boundaries_version = '2026'
       AND effective_from > CURRENT_DATE;
    IF dormant <> 38 THEN
        RAISE EXCEPTION 'expected 38 dormant 2026 districts (Ottawa 24 + '
          'London 14), found %', dormant;
    END IF;

    -- ★ Windsor's tenth ward.
    SELECT count(*) INTO win FROM constituency_boundaries
     WHERE source_set = 'windsor-wards' AND boundary_kind = 'district'
       AND effective_from <= CURRENT_DATE;
    IF win <> 10 THEN
        RAISE EXCEPTION 'Windsor has % live wards, expected 10', win;
    END IF;

    -- Nobody orphaned, anywhere.
    SELECT count(*) INTO orphans FROM politicians p
     WHERE p.is_active AND p.constituency_id IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM constituency_boundaries b
                        WHERE b.constituency_id = p.constituency_id);
    IF orphans <> 0 THEN
        RAISE EXCEPTION 'cutover orphaned % sitting members', orphans;
    END IF;

    RAISE NOTICE 'Ontario large-city cutover: 8 sets on authoritative sources, '
                 'Windsor +1 ward, 2 future generations dormant';
END $$;

COMMIT;

SELECT refresh_map_views();
