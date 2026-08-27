-- 0111 — Markham: retire the mirror generation, and gain Ward 7.
--
-- ★ WE WERE MISSING WARD 7 — held rows were Wards 1-6 and 8. An interior hole,
-- the same shape as Newmarket's Ward 5 in 0110, and the sixth partial-ingest
-- defect in this programme (Winnipeg Elmwood, Fort Erie ×2, Windsor Ward 2,
-- Burlington ×2, Newmarket Ward 5). Every address in Ward 7 resolved to no
-- councillor. The other seven overlap the authoritative map at 99.6% or better.
--
-- ⚠ Found by auditing held district count against AMO's 2026 roster. Nothing
-- else would have caught it: the set had a plausible count, plausible names,
-- and no orphaned members, because a missing polygon orphans nobody — it
-- simply answers nothing.
--
-- ★ DATE FROM AN INSTRUMENT, not prose and not a layer title: Ward Boundary
-- By-law 2013-29, passed by Markham City Council 2013-03-19, with the Ontario
-- Municipal Board dismissing the appeal on 2013-10-24. So the boundaries first
-- governed the 2014-10-27 election. Same shape as Haldimand's By-law 2588/25 —
-- a numbered by-law with a resolved tribunal proceeding, which is the strongest
-- evidence class ruling A2 recognises.
--
-- ⚠ Markham has had EIGHT wards since 1997, with the numbering unchanged
-- through adjustments in 1978, 1982, 1997 and 2006. The count is therefore
-- useless as a vintage signal across five generations — ruling A7 in its purest
-- form. What makes 2014 the answer rather than 1997 is that the 2013 review
-- changed all eight boundaries.
--
-- Forward-only. Apply with:
--   docker exec -i sw-db psql -U sw -d sovereignwatch -v ON_ERROR_STOP=1 \
--     < db/migrations/0111_markham_ward7.sql

BEGIN;

DO $$
DECLARE auth int;
BEGIN
    SELECT count(*) INTO auth FROM constituency_boundaries
     WHERE source_set = 'markham-wards' AND boundaries_version = '2014'
       AND boundary_kind = 'district';
    IF auth <> 8 THEN
        RAISE EXCEPTION 'Expected 8 authoritative Markham wards, found % — run '
          'the load first', auth;
    END IF;
END $$;

DELETE FROM constituency_boundaries
 WHERE source_set = 'markham-wards'
   AND boundaries_version = 'current'
   AND boundary_kind = 'district';

DO $$
DECLARE live int; w7 int; csd int; orphans int;
BEGIN
    SELECT count(*) INTO live FROM constituency_boundaries
     WHERE source_set = 'markham-wards' AND boundary_kind = 'district'
       AND effective_from <= CURRENT_DATE
       AND (effective_to IS NULL OR effective_to >= CURRENT_DATE);
    IF live <> 8 THEN
        RAISE EXCEPTION 'Markham has % live wards, expected 8', live;
    END IF;

    SELECT count(*) INTO w7 FROM constituency_boundaries
     WHERE constituency_id = 'markham-wards/ward-7';
    IF w7 <> 1 THEN RAISE EXCEPTION 'Ward 7 still absent'; END IF;

    SELECT count(*) INTO csd FROM constituency_boundaries
     WHERE source_set = 'markham-wards' AND boundary_kind = 'municipality';
    IF csd <> 1 THEN RAISE EXCEPTION 'Markham municipality polygon lost'; END IF;

    SELECT count(*) INTO orphans FROM politicians p
     WHERE p.is_active AND p.constituency_id IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM constituency_boundaries b
                        WHERE b.constituency_id = p.constituency_id);
    IF orphans <> 0 THEN
        RAISE EXCEPTION 'cutover orphaned % sitting members', orphans;
    END IF;

    RAISE NOTICE 'Markham: 8 wards live, Ward 7 recovered';
END $$;

COMMIT;

SELECT refresh_map_views();
