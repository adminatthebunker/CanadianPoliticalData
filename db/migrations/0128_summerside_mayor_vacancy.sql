-- 0128 — Summerside's mayoralty is vacant. End-date Dan Kutcher.
--
-- ★ THE PUBLISHER SAYS SO IN ITS OWN WORDS, which is why this is a migration and
-- not a refusal. From summerside.ca/city_governance/senior_leadership_mayor_council,
-- read 2026-09-02:
--
--   "Dan Kutcher resigned as Mayor of the City of Summerside, effective
--    September 1, 2026. In accordance with the Prince Edward Island Municipal
--    Government Act, the office of the Mayor will be determined at the next
--    municipal general election on November 2, 2026."
--
-- ⛔ THE SEAT IS DELIBERATELY LEFT EMPTY. There is no successor to install — the
-- city states the office stays open until polling day. `check-boundary-coverage`
-- already models this correctly: a member SHORTFALL is reported as a vacancy,
-- never as a breach (only an EXCESS is a breach, because that means duplicate
-- rows). Ontario legitimately sits two short. So an empty seat is a state the
-- system understands, and inventing a "vacant" placeholder row to fill it would
-- be worse than the gap.
--
-- ★ AND THE PAGE CONFIRMED A DATE WE HAD ONLY INFERRED. PE's 2026-11-02 election
-- was a statutory-cycle inference in every document we hold — the boundary
-- corpus, the timeline, PROGRESS.md. The City of Summerside states it outright.
-- One of the four municipal cliff dates is now sourced rather than derived.
--
-- ⓘ Why the ingester did not do this itself. `apply-pe-municipal-roster` refuses
-- `orphan` and `vacancy` verdicts by design, because "the page did not mention
-- them" is indistinguishable from a template change or a parser regression.
-- That is not hypothetical: the PE parser silently dropped two of
-- Charlottetown's ten councillors on its first run — they publish pronouns
-- between their name and their ward — and reported them as orphans. An
-- auto-retire path would have deactivated two sitting councillors over a
-- missing "(she/her)". Departures are written here, with the evidence, by hand.
--
-- ⚠ NOT IN THIS MIGRATION: Jody Jackson (Stratford, Tea Hill). The town's
-- council page does not mention her at all and Ward 3 shows one member where
-- Wards 1 and 2 show two, which is consistent with a resignation — but the town
-- publishes no statement, so the evidence is ABSENCE, which is exactly what the
-- refusal above exists to distrust. Left for confirmation.
--
-- Three-step retirement, per sk_mlas._detect_sk_retirements.
--
-- Forward-only. Apply with:
--   docker exec -i sw-db psql -U sw -d sovereignwatch -v ON_ERROR_STOP=1 \
--     < db/migrations/0128_summerside_mayor_vacancy.sql

BEGIN;

INSERT INTO politician_changes
    (politician_id, change_type, old_value, new_value, severity)
SELECT p.id, 'retired',
       jsonb_build_object(
         'name', p.name,
         'office', p.elected_office,
         'constituency_id', p.constituency_id,
         'effective', '2026-09-01',
         'reason', 'resigned as Mayor of the City of Summerside',
         'successor', NULL,
         'seat_status', 'vacant until the 2026-11-02 municipal general election',
         'source', 'https://www.summerside.ca/city_governance/senior_leadership_mayor_council'),
       NULL, 'notable'
  FROM politicians p
 WHERE p.is_active AND p.level = 'municipal' AND p.province_territory = 'PE'
   AND p.name = 'Dan Kutcher';

UPDATE politician_terms
   SET ended_at = TIMESTAMPTZ '2026-09-01 00:00:00+00'
 WHERE ended_at IS NULL
   AND politician_id = (SELECT id FROM politicians
                         WHERE name = 'Dan Kutcher' AND is_active
                           AND level = 'municipal' AND province_territory = 'PE');

UPDATE politicians
   SET is_active = false, updated_at = now()
 WHERE is_active AND level = 'municipal' AND province_territory = 'PE'
   AND name = 'Dan Kutcher';

DO $$
DECLARE n int;
BEGIN
    IF EXISTS (SELECT 1 FROM politicians
                WHERE name = 'Dan Kutcher' AND is_active
                  AND level = 'municipal' AND province_territory = 'PE') THEN
        RAISE EXCEPTION 'Dan Kutcher is still active';
    END IF;

    -- The seat must be EMPTY, not backfilled.
    SELECT count(*) INTO n FROM politicians
     WHERE is_active AND constituency_id = 'census-subdivisions/1103025';
    IF n <> 0 THEN
        RAISE EXCEPTION
          'expected the Summerside mayoralty to be vacant, found % active holder(s)', n;
    END IF;

    -- Summerside's eight ward councillors are untouched.
    SELECT count(*) INTO n FROM politicians p
      JOIN constituency_boundaries b ON b.constituency_id = p.constituency_id
     WHERE p.is_active AND b.source_set = 'summerside-wards'
       AND b.boundary_kind = 'district';
    IF n <> 8 THEN
        RAISE EXCEPTION 'expected 8 Summerside ward councillors, found %', n;
    END IF;

    SELECT count(*) INTO n FROM politicians p
     WHERE p.is_active AND p.constituency_id IS NOT NULL
       AND NOT EXISTS (
         SELECT 1 FROM constituency_boundaries b
          WHERE b.constituency_id = p.constituency_id
            AND b.effective_from <= CURRENT_DATE
            AND (b.effective_to IS NULL OR b.effective_to >= CURRENT_DATE));
    IF n <> 0 THEN
        RAISE EXCEPTION '% sitting member(s) orphaned corpus-wide', n;
    END IF;

    RAISE NOTICE '0128 ok: Summerside mayoralty vacant until 2026-11-02; 8 ward councillors intact';
END $$;

COMMIT;
