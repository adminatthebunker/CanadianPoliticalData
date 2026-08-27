-- 0116 — Ajax, Oshawa, Uxbridge, Whitby: four Durham sets onto their own dates.
--
-- Provenance upgrades — all four overlap the mirror at 99.4% or better, so no
-- coverage changes. What changes is that `effective_from` stops being a lie:
--
--   Ajax      2018-10-22  By-law 26-2017 (2017-04-18), four wards to three
--   Oshawa    2018-10-22  By-law 55-2017 (2017-06-26)
--   Uxbridge  2018-10-22  By-law 2017-96 (2017-07-10)
--   Whitby    1997-11-10  the Town's single 1996 boundary adjustment
--
-- ⛔ OSHAWA'S BY-LAW NAMES A DATE AND IT IS THE WRONG ONE. Clause 11 reads
-- "This by-law comes into effect on the day it is passed" — 2017-06-26, sixteen
-- months before the election it governs. Clause 5's recital gives the answer:
-- "ward boundaries to be used starting with the 2018 election".
-- ★ This is the exact mirror of Lincoln's By-law 2025-28, which names
-- 2026-11-15, the council term start, sixteen months too LATE. Same failure
-- mode, opposite direction. **The date printed in an Ontario ward by-law is not
-- the date A10.4 wants, in either direction — read the recital, not the
-- commencement clause.**
--
-- ★ UXBRIDGE OVERTURNS THE OBVIOUS ASSUMPTION. It reads like a sleepy township
-- with ancient wards; the wards were COMPLETELY REDRAWN in 2017. Before: a
-- southern strip, a north-west rural, a north-east rural, two urban. After:
-- Ward 1 is the former Township of Uxbridge minus the urban area and Ward 2 is
-- the former Township of Scott. The five-ward COUNT is old — attested in a 2003
-- notice of nominations — but the lines are not, and a count-based check sees
-- nothing. Any pre-2010 date for Uxbridge would have been wrong.
--
-- ⛔ WHITBY'S LAYER DESCRIPTION IS POISON AND WAS NOT USED. It said "Updated
-- January 2021" when first harvested and now says "Updated January 2026" —
-- both track councillor-name attribute refreshes, not the boundary. A pipeline
-- reading that field would have produced three different wrong dates for Whitby
-- across three harvests. The date here comes from Clerk's report CLK 01-21:
-- "Throughout its 52 year history since amalgamation in 1968, the Town has only
-- adjusted ward boundaries once in 1996", corroborated by policy G-060's
-- appendix titles ("1968 to 1996" and "1996 to Present"). ⚠ Confidence is
-- medium-high, not high — no by-law number was located.
--
-- ⛔ CLARINGTON AND VAUGHAN ARE DATED BUT DELIBERATELY NOT LOADED, and for a
-- reason this programme has not hit before: an EXPLICIT licence prohibition
-- rather than the usual silence.
--   Clarington  1997-11-10, By-law 96-151 (1996-08-12) — but the AGOL item's
--               licenceInfo reads "made available for personal informational
--               purposes only and has not been prepared for, is not suitable
--               for, and may not be used for, any commercial, legal,
--               engineering, or surveying purpose", with no linked grant behind
--               it.
--   Vaughan     2010-10-25 — and note the by-law is NOT the operative
--               instrument: By-law 89-2009 was appealed and "the OMB imposed a
--               different ward structure than the one approved by Vaughan
--               Council, but maintained the number of wards at 5". ★ The count
--               survived the appeal and the map did not, so a count check sees
--               nothing. Licence: all three candidate layers have empty
--               licenseInfo and the site-wide terms say "No part of this web
--               site, or the information contained therein, may be reproduced
--               ... without the prior written permission of the City."
-- ⚠ The standing operator decision is "licence recorded, never a gate", and it
-- was made against a corpus of UNSTATED licences. An explicit prohibition is a
-- different thing, so both are held for an operator call rather than decided
-- here. Both were provenance-only, so deferring costs no coverage.
--
-- Forward-only. Apply with:
--   docker exec -i sw-db psql -U sw -d sovereignwatch -v ON_ERROR_STOP=1 \
--     < db/migrations/0116_durham_four_cutover.sql

BEGIN;

CREATE TEMP TABLE _sets(source_set text PRIMARY KEY, v text, n int) ON COMMIT DROP;
INSERT INTO _sets VALUES
  ('ajax-wards','2018',3), ('oshawa-wards','2018',5),
  ('uxbridge-wards','2018',5), ('whitby-wards','1997',4);

DO $$
DECLARE r record; got int;
BEGIN
    FOR r IN SELECT * FROM _sets LOOP
        SELECT count(*) INTO got FROM constituency_boundaries
         WHERE source_set = r.source_set AND boundaries_version = r.v
           AND boundary_kind = 'district';
        IF got <> r.n THEN
            RAISE EXCEPTION '%: % authoritative districts, expected %',
                            r.source_set, got, r.n;
        END IF;
    END LOOP;
END $$;

DELETE FROM constituency_boundaries
 WHERE source_set IN (SELECT source_set FROM _sets)
   AND boundaries_version = 'current'
   AND boundary_kind = 'district';

DO $$
DECLARE r record; got int; n_overlap int; orphans int;
BEGIN
    FOR r IN SELECT * FROM _sets LOOP
        SELECT count(*) INTO got FROM constituency_boundaries
         WHERE source_set = r.source_set AND boundary_kind = 'district'
           AND effective_from <= CURRENT_DATE
           AND (effective_to IS NULL OR effective_to >= CURRENT_DATE);
        IF got <> r.n THEN
            RAISE EXCEPTION '%: % live districts after cutover, expected %',
                            r.source_set, got, r.n;
        END IF;
    END LOOP;

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
        RAISE EXCEPTION 'cutover orphaned % sitting members', orphans;
    END IF;

    RAISE NOTICE 'Ajax/Oshawa/Uxbridge/Whitby on their own dates';
END $$;

COMMIT;

SELECT refresh_map_views();
