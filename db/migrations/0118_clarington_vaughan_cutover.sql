-- 0118 — Clarington and Vaughan: the two explicit-prohibition sets, released.
--
-- These are the last two Ontario municipalities held back in the Wave 3
-- boundary programme, and the reason they were held is not evidentiary. Both
-- were researched and dated on 2026-08-27 (see 0116's header). Both were then
-- deliberately NOT loaded, because each carries the programme's first EXPLICIT
-- licence prohibition rather than the usual silence:
--
--   Clarington  AGOL licenseInfo, verbatim: "The data is made available for
--               personal informational purposes only and has not been prepared
--               for, is not suitable for, and may not be used for, any
--               commercial, legal, engineering, or surveying purpose."
--   Vaughan     all four candidate layers have EMPTY licenseInfo, so the
--               governing text is the site-wide terms, verbatim: "No part of
--               this web site, or the information contained therein, may be
--               reproduced, stored in a retrieval system, or transmitted, in
--               any form or by any means, electronic, mechanical recording or
--               otherwise, without the prior written permission of the City."
--
-- ⚖ OPERATOR DECISION 2026-08-28: load both. The standing rule "licence
-- recorded, never a gate" stands, and now covers explicit prohibitions as well
-- as the unstated licences it was originally made against. Full verbatim text,
-- source URLs, checksums and the Wayback citation for Vaughan's terms page are
-- in data/boundaries/municipal-ontario/PROVENANCE.md § "Clarington + Vaughan".
-- ⛔ Nothing in this file paraphrases either licence.
--
-- In-force dates and the instruments that establish them:
--
--   Clarington  1997-11-10, By-law 96-151 (passed 1996-08-12). Report
--               CLD-036-16: "Clarington's existing ward boundaries were
--               established by Council on August 12, 1996 through By-law
--               96-151", and "In 1996, effective for the 1997 elections …
--               the Municipality was divided into the current four wards".
--               ⛔ The by-law's own date is fifteen months early and is not
--               used — the A10.4 recital rule, same shape as Oshawa's 55-2017.
--   Vaughan     2010-10-25, and THE BY-LAW IS NOT THE OPERATIVE INSTRUMENT.
--               Vaughan Ward Boundary Review Final Report (Dec 2016) §2: the
--               2009 review was "adopted by By-law 89-2009, which was appealed
--               to the Ontario Municipal Board (OMB). The OMB imposed a
--               different ward structure than the one approved by Vaughan
--               Council, but maintained the number of wards at 5. This ward
--               structure was implemented for the 2010 municipal elections and
--               is still in place today." Cite the OMB order; note the by-law.
--
-- ★ VAUGHAN IS THE CLEANEST PROOF THAT A COUNT CHECK CANNOT SEE AN APPEAL.
-- Five wards before the OMB, five after — the count survived and the map did
-- not. The `expect_districts = 5` in the spec would have accepted By-law
-- 89-2009's superseded structure with equal confidence. Geometry, not counts:
-- measured against held, the authoritative wards overlap 99.68–99.94% in both
-- directions, so this is a provenance upgrade and not a substitution.
-- Clarington likewise, at 99.80% minimum over its four wards.
--
-- ⚠ VAUGHAN IS RE-KEYED BY THIS CUTOVER AND CLARINGTON IS NOT. Held Vaughan
-- ids were slugged from the neighbourhood name in DESCRIP — maplekleinburg,
-- woodbridge-west, woodbridgevellore, concordthornhill-north, thornhill —
-- while the held DISPLAY names were already "Ward N". The programme's uniform
-- label wins, so the ids become vaughan-wards/ward-1..5. Clarington's were
-- already ward-N and survive untouched.
--
-- ⛔ SO THE OLD ROWS CANNOT SIMPLY BE DELETED. Five sitting Vaughan
-- councillors and five politician_terms rows point at ids that are about to
-- stop existing, and there is no FK to null them. This migration therefore:
--   • re-keys politician_terms directly — deterministic, matched on the
--     display name the two generations share, and no tool covers that table;
--   • sets politicians.constituency_id to NULL for the same five, which is
--     what `reattach-municipal-roster` requires as input. The roster is
--     re-linked by that command, run immediately after this migration, so the
--     whole-council and municipality-anchor safety checks apply to the
--     re-attachment rather than being bypassed by a hand-written UPDATE.
--
-- Forward-only. Apply with:
--   docker exec -i sw-db psql -U sw -d sovereignwatch -v ON_ERROR_STOP=1 \
--     < db/migrations/0118_clarington_vaughan_cutover.sql
-- Then:
--   docker compose run --rm --no-deps scanner reattach-municipal-roster \
--     --council vaughan-city-council

BEGIN;

CREATE TEMP TABLE _sets(source_set text PRIMARY KEY, v text, n int) ON COMMIT DROP;
INSERT INTO _sets VALUES
  ('clarington-wards','1997',4), ('vaughan-wards','2010',5);

-- 1. The authoritative generation is present and complete, before anything is
--    destroyed. A load that half-succeeded must not reach the DELETE.
DO $$
DECLARE r record; got int;
BEGIN
    FOR r IN SELECT * FROM _sets LOOP
        SELECT count(*) INTO got FROM constituency_boundaries
         WHERE source_set = r.source_set AND boundaries_version = r.v
           AND boundary_kind = 'district';
        IF got <> r.n THEN
            RAISE EXCEPTION '%: % authoritative districts at version %, expected %',
                            r.source_set, got, r.v, r.n;
        END IF;
    END LOOP;
END $$;

-- 2. Old id -> new id, for the rows whose slug actually changes. Built from the
--    DISPLAY NAME, which both generations share and which the roster also
--    carries in politicians.constituency_name. ⚠ Must be built BEFORE the
--    delete: after it there is nothing left to map from.
CREATE TEMP TABLE _rekey(old_id text PRIMARY KEY, new_id text NOT NULL) ON COMMIT DROP;
INSERT INTO _rekey(old_id, new_id)
SELECT o.constituency_id, n.constituency_id
  FROM constituency_boundaries o
  JOIN _sets s ON s.source_set = o.source_set
  JOIN constituency_boundaries n
    ON n.source_set = o.source_set
   AND n.boundaries_version = s.v
   AND n.boundary_kind = 'district'
   AND n.name = o.name
 WHERE o.boundaries_version = 'current'
   AND o.boundary_kind = 'district'
   AND n.constituency_id <> o.constituency_id;

-- The map must be a function in both directions, or a re-key silently merges
-- two wards into one. Duplicate display names inside a generation are the way
-- that happens.
DO $$
DECLARE n_map int; n_new int; n_expect int := 5;   -- Vaughan's five; Clarington re-keys nothing
BEGIN
    SELECT count(*), count(DISTINCT new_id) INTO n_map, n_new FROM _rekey;
    IF n_map <> n_new THEN
        RAISE EXCEPTION 're-key map is not injective: % old ids onto % new ids',
                        n_map, n_new;
    END IF;
    IF n_map <> n_expect THEN
        RAISE EXCEPTION 're-key map has % entries, expected % (Vaughan ward-1..5)',
                        n_map, n_expect;
    END IF;
END $$;

-- 3. Carry the historical terms across. No tool covers politician_terms, and
--    a term row is a historical assertion — nulling it would lose the link
--    rather than move it.
UPDATE politician_terms t
   SET constituency_id = k.new_id
  FROM _rekey k
 WHERE t.constituency_id = k.old_id;

-- 4. Detach the sitting members, so `reattach-municipal-roster` can see them.
--    ⛔ Leaving them pointed at a deleted id is the alternative and it is worse:
--    it fails the orphan assertion below, and if that assertion were ever
--    relaxed it would serve a ward id that resolves to no polygon.
UPDATE politicians p
   SET constituency_id = NULL, updated_at = now()
  FROM _rekey k
 WHERE p.constituency_id = k.old_id;

-- 5. Retire the mirror generation. ⛔ THIS IS THE POINT OF THE MIGRATION — a
--    load does not replace a generation, it inserts beside it, and without this
--    every Clarington and Vaughan address resolves to two wards.
--    ⚠ Districts only. The `municipality` row (census-subdivisions/3518017,
--    /3519028) is the city outline, is not superseded by a ward map, and is the
--    anchor `reattach-municipal-roster` needs to identify the council.
DELETE FROM constituency_boundaries
 WHERE source_set IN (SELECT source_set FROM _sets)
   AND boundaries_version = 'current'
   AND boundary_kind = 'district';

-- 6. Assertions. A wrong load rolls the whole thing back.
DO $$
DECLARE r record; got int; n_overlap int; orphans int; detached int;
BEGIN
    -- Exactly the expected number of LIVE districts per set: Clarington 4,
    -- Vaughan 5. Catches both a failed delete (8 / 10) and a failed load (0).
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

    -- No municipal set may have two generations whose live windows intersect at
    -- any date — the invariant 0112 established, asserted table-wide so this
    -- cutover cannot close its own overlap while opening someone else's.
    -- ⛔ `overlaps` is a RESERVED SQL keyword; the variable is n_overlap.
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

    -- No sitting member may point at a constituency_id that has no polygon.
    SELECT count(*) INTO orphans FROM politicians p
     WHERE p.is_active AND p.constituency_id IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM constituency_boundaries b
                        WHERE b.constituency_id = p.constituency_id);
    IF orphans <> 0 THEN
        RAISE EXCEPTION 'cutover orphaned % sitting members', orphans;
    END IF;

    -- And the five we deliberately detached are exactly five, all Vaughan.
    -- More than that means the re-key map caught something it should not have.
    SELECT count(*) INTO detached FROM politicians p
     WHERE p.is_active AND p.level = 'municipal'
       AND p.constituency_id IS NULL
       AND split_part(p.source_id, ':', 2) = 'vaughan-city-council';
    IF detached <> 5 THEN
        RAISE EXCEPTION 'expected 5 detached Vaughan councillors, found %',
                        detached;
    END IF;

    RAISE NOTICE 'Clarington 1997-11-10 (By-law 96-151) and Vaughan 2010-10-25 '
                 '(OMB order, 2009) live; mirror generation retired; 5 Vaughan '
                 'councillors detached for reattach-municipal-roster';
END $$;

COMMIT;

SELECT refresh_map_views();
