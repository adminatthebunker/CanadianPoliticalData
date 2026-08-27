-- 0114 — Brantford: a holdback released, because the premise was a name collision.
--
-- ⛔ BRANTFORD WAS NEVER ACTUALLY UNCERTAIN. It was held back from 0109 because
-- a ward-boundary review appeared to run through 2024 — survey July, Policy
-- Development Committee 2024-09-03, Council 2024-09-23 — with an outcome that
-- could not be found, and the FeatureServer's 2024-02-14 modification date
-- predating that meeting looked like a live risk. Its ward count is 5 either
-- way, so no count check could have settled it.
--
-- ★ That review belongs to the COUNTY OF BRANT, not the CITY OF BRANTFORD.
-- engagebrant.ca names the municipality outright, "Policy Development
-- Committee" is a County of Brant committee (Brantford has none), and AMO
-- lists them as separate municipalities — "Brant, County of" urlId 10123
-- against "Brantford, City of" urlId 10109, verified directly. There was no
-- Brantford decision to find.
--
-- ⚠ This dossier already warns that Ontario reuses municipality names across
-- tiers ("Hamilton, Township of" is not "Hamilton, City of"). This is the
-- sharper form: two municipalities whose names differ by three letters, one
-- inside the other's county. Verify the municipality, not the string — a
-- substring match would have compounded the error rather than caught it.
--
-- In-force 2018-10-22, from an instrument. The boundaries changed once, at the
-- 2017 annexation. Brantford-Brant Boundary Adjustment Agreement, Part II,
-- Article 5.01: "existing Wards 1, 2, 3 and 4 of the City shall be enlarged as
-- required to include the entirety of that Phase annexed ... Except for the
-- enlargement of the said Wards 1, 2, 3, and 4, there shall be no other changes
-- to the boundaries of the said Wards 1, 2, 3, and 4, or to any other Ward
-- boundaries within the City of Brantford." Signed 2016-06-28, effective
-- 2017-01-01; the first municipal election after that was 2018-10-22.
--
-- ★ Corroborated by geometry rather than taken on trust: the five wards total
-- 102.58 km² against a pre-2017 city of ~72.5 km², and Ward 1 alone carries a
-- 34,499 m perimeter against ~15,019 m for the others — it absorbed most of the
-- annexed land, exactly as Article 5.01 describes. Overlap against the held
-- mirror is 99.6% or better, so this is a provenance upgrade, not a repair.
--
-- ⚠ A LIVE CAVEAT, recorded because it will not announce itself. The agreement
-- runs in three phases with a Trigger Mechanism, and s.5.03 provides that when
-- it is exercised "the City shall specify the resulting City Ward Boundary
-- changes". The 2021 census area matches the full annexation and the City's own
-- 2026 ward map matches this geometry, so no later phase has moved the wards —
-- but a future trigger will, and it will NOT surface as a ward review.
--
-- Forward-only. Apply with:
--   docker exec -i sw-db psql -U sw -d sovereignwatch -v ON_ERROR_STOP=1 \
--     < db/migrations/0114_brantford_cutover.sql

BEGIN;

DO $$
DECLARE auth int;
BEGIN
    SELECT count(*) INTO auth FROM constituency_boundaries
     WHERE source_set = 'brantford-wards' AND boundaries_version = '2018'
       AND boundary_kind = 'district';
    IF auth <> 5 THEN
        RAISE EXCEPTION 'Expected 5 authoritative Brantford wards, found %', auth;
    END IF;
END $$;

DELETE FROM constituency_boundaries
 WHERE source_set = 'brantford-wards'
   AND boundaries_version = 'current'
   AND boundary_kind = 'district';

DO $$
DECLARE live int; csd int; orphans int; n_overlap int;
BEGIN
    SELECT count(*) INTO live FROM constituency_boundaries
     WHERE source_set = 'brantford-wards' AND boundary_kind = 'district'
       AND effective_from <= CURRENT_DATE
       AND (effective_to IS NULL OR effective_to >= CURRENT_DATE);
    IF live <> 5 THEN
        RAISE EXCEPTION 'Brantford has % live wards, expected 5', live;
    END IF;

    SELECT count(*) INTO csd FROM constituency_boundaries
     WHERE source_set = 'brantford-wards' AND boundary_kind = 'municipality';
    IF csd <> 1 THEN RAISE EXCEPTION 'Brantford municipality polygon lost'; END IF;

    SELECT count(*) INTO n_overlap FROM constituency_boundaries a
      JOIN constituency_boundaries b
        ON b.source_set = a.source_set
       AND b.boundaries_version <> a.boundaries_version
       AND a.boundary_kind = 'district' AND b.boundary_kind = 'district'
       AND a.effective_from <= coalesce(b.effective_to, DATE '9999-12-31')
       AND b.effective_from <= coalesce(a.effective_to, DATE '9999-12-31')
     WHERE a.source_set = 'brantford-wards';
    IF n_overlap <> 0 THEN
        RAISE EXCEPTION 'Brantford left % overlapping generation pairs', n_overlap;
    END IF;

    SELECT count(*) INTO orphans FROM politicians p
     WHERE p.is_active AND p.constituency_id IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM constituency_boundaries b
                        WHERE b.constituency_id = p.constituency_id);
    IF orphans <> 0 THEN
        RAISE EXCEPTION 'cutover orphaned % sitting members', orphans;
    END IF;

    RAISE NOTICE 'Brantford: 5 wards on the post-annexation 2018 map';
END $$;

COMMIT;

SELECT refresh_map_views();
