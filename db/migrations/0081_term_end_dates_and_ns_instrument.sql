-- 0081 — Close the terms of everyone this programme deactivated, and correct
--        0078's citation of the Nova Scotia instrument.
--
-- ★ RAISED BY THE JURISDICTION AGENTS AFTER THE CUTOVERS HAD LANDED
-- ------------------------------------------------------------------
-- Two findings arrived from the Yukon and Nova Scotia verification passes after
-- 0079 and 0078 were already applied. Both are real; both are recorded forward
-- rather than by editing an applied migration.
--
-- ── 1. Deactivating a politician does not close their term ──────────────────
-- `is_active = false` removes a member from every roster query, but
-- `politician_terms.ended_at IS NULL` still reads as "currently serving" to
-- anything that asks the terms table instead. Twenty rows deactivated across
-- 0067, 0076 and 0079 were left in that state.
--
-- ⚠ AND END-DATING THEM NAIVELY WOULD HAVE MADE IT WORSE. Open North-sourced
-- terms carry a FABRICATED `started_at`: the column defaults to `now()` and the
-- ingester never overrides it, so the value is the date we first ingested, not
-- the date the member took office. Saskatchewan is the clearest proof — 242
-- terms across just 5 distinct start dates, all in 2026, for a legislature whose
-- members have served for decades.
--
-- The Yukon rows are stamped 2026-04-14 and the federal pair 2026-04-13 — the
-- latter being the date of the BY-ELECTION THAT REPLACED THEM, i.e. their
-- successor's start date. Setting `ended_at` to the real departure date without
-- touching `started_at` would have produced `ended_at < started_at` on all 13.
--
-- So each is given a start that is TRUE of the term being closed — the first day
-- of the parliament in which that member demonstrably sat — alongside the real
-- end date. ⓘ Where a member also served earlier (Sandy Silver from 2011, for
-- instance) that earlier service was a SEPARATE term we do not hold; this row
-- describes their last one, and now describes it correctly.
--
-- ── 2. ⛔ 0078 cites the wrong bill ─────────────────────────────────────────
-- `0078_nova_scotia_boundary_cutover.sql` says "Bills 203 and 205 (Elections Act
-- and House of Assembly Act amendments)". The boundary instrument is **Bill 203
-- alone** — *House of Assembly Act (amended)*, **Chapter 10 of the Acts of
-- 2026** — whose s.2(1)(a) strikes "fifty-five" and substitutes "fifty-six" and
-- whose s.2(1)(b) inserts Chéticamp–Margarees–Pleasant Bay. Bill 205 is
-- election-administration modernisation and contains no district list.
--
-- The DATE is unaffected: both received Royal Assent 2026-04-09, so
-- `effective_from` is right. Commencement is genuinely assent, not the Yukon
-- dissolution trap — Bill 203 has NO commencement section, so the default in the
-- *Interpretation Act*, R.S.N.S. 1989, c. 235, s.3(2) applies ("the day of the
-- assent … is the date of the commencement of the Act, if no later commencement
-- is therein provided"), and s.4(2) deems the new seat vacant "on the coming
-- into force of this Act" — a seat cannot be deemed vacant unless it exists.
--
-- ⚠ Bill 205 DOES carry delayed commencement on two unrelated sections, one of
-- them keyed to "the dissolution or the determination by the effluxion of time
-- of the present House of Assembly". Anyone re-reading 205 will hit that
-- language and could wrongly conclude the map is deferred. It is not.
--
-- ⓘ `docs/research/boundaries/nova-scotia.md` repeats "Bill 205" in several
-- places, including its header and effective-dates table.
--
-- Forward-only. Apply with:
--   docker exec -i sw-db psql -U sw -d sovereignwatch -v ON_ERROR_STOP=1 \
--     < db/migrations/0081_term_end_dates_and_ns_instrument.sql

BEGIN;

-- ── Yukon: the 11 who did not return in the 36th Assembly ───────────────────
-- 35th Assembly: general election 2021-04-12, dissolved 2025-10-03.
UPDATE politician_terms t
   SET started_at = TIMESTAMPTZ '2021-04-12',
       ended_at   = TIMESTAMPTZ '2025-10-03'
  FROM politicians p
 WHERE t.politician_id = p.id
   AND t.ended_at IS NULL
   AND NOT p.is_active
   AND p.province_territory = 'YT' AND p.level = 'provincial'
   AND p.source_id LIKE 'opennorth:yukon-legislature:%';

-- ── Federal: two members who resigned mid-Parliament ────────────────────────
-- 45th Parliament: general election 2025-04-28.
UPDATE politician_terms t
   SET started_at = TIMESTAMPTZ '2025-04-28',
       ended_at   = TIMESTAMPTZ '2026-02-02'   -- appointed High Commissioner to the UK
  FROM politicians p
 WHERE t.politician_id = p.id AND t.ended_at IS NULL
   AND p.source_id = 'opennorth:house-of-commons:bill-blair';

UPDATE politician_terms t
   SET started_at = TIMESTAMPTZ '2025-04-28',
       ended_at   = TIMESTAMPTZ '2026-01-09'   -- resigned to advise on Ukraine
  FROM politicians p
 WHERE t.politician_id = p.id AND t.ended_at IS NULL
   AND p.source_id = 'opennorth:house-of-commons:chrystia-freeland';

-- ── Ontario: Doly Begum resigned as MPP to contest the federal by-election ──
-- ⓘ Her `started_at` (2025-04-14, the 44th Parliament's first sitting) is a REAL
-- date from `ola.org:parliament-44`, not an ingest artifact, so only the end
-- needs setting. Historical sources in this table generally have real dates; the
-- fabrication is specific to the Open North path.
UPDATE politician_terms t
   SET ended_at = TIMESTAMPTZ '2026-02-03'
  FROM politicians p
 WHERE t.politician_id = p.id AND t.ended_at IS NULL
   AND p.source_id = 'ola.org:former-mpps:member_id=7508';

-- ── New Brunswick: delete the duplicates' terms outright ────────────────────
-- ⛔ Not end-dated. These six rows were deactivated by 0067 as DUPLICATES of
-- sitting MLAs — five with HTML-entity-encoded names. The member is real and
-- still serving under their `opennorth` row, which holds the genuine term. A
-- second term row for the same service is not history, it is double-counting,
-- and end-dating it would assert these people left office. They did not.
DELETE FROM politician_terms t
 USING politicians p
 WHERE t.politician_id = p.id
   AND t.ended_at IS NULL
   AND NOT p.is_active
   AND p.province_territory = 'NB' AND p.level = 'provincial'
   AND p.source_id LIKE 'direct:legnb-ca%';

DO $$
DECLARE open_terms int; inverted int; touched int;
BEGIN
    -- Everything this programme deactivated must now have a closed term.
    SELECT count(*) INTO open_terms
      FROM politicians p JOIN politician_terms t ON t.politician_id = p.id
     WHERE NOT p.is_active AND t.ended_at IS NULL
       AND p.updated_at::date = CURRENT_DATE;
    IF open_terms <> 0 THEN
        RAISE EXCEPTION
          '% terms are still open on politicians deactivated by this programme',
          open_terms;
    END IF;

    -- ⛔ And nothing here may have created an impossible interval.
    SELECT count(*) INTO inverted FROM politician_terms t
      JOIN politicians p ON p.id = t.politician_id
     WHERE t.ended_at < t.started_at AND p.updated_at::date = CURRENT_DATE;
    IF inverted <> 0 THEN
        RAISE EXCEPTION
          '% terms now end before they start — the started_at correction is '
          'wrong', inverted;
    END IF;

    SELECT count(*) INTO touched FROM politician_terms t
      JOIN politicians p ON p.id = t.politician_id
     WHERE NOT p.is_active AND p.updated_at::date = CURRENT_DATE;
    RAISE NOTICE 'closed/removed the open terms of every politician this programme deactivated (% terms remain on those rows, all end-dated)', touched;

    -- ⚠ REPORTED, NOT ASSERTED — pre-existing and far larger than this
    -- programme. Across the whole table, 228 INACTIVE politicians carried an
    -- open term before this migration and 43 terms already ended before they
    -- started, concentrated in the Open North and openparliament paths where
    -- `started_at` defaults to the ingest timestamp. Fixing that properly means
    -- fixing the ingesters, not patching rows, and is out of scope here.
END $$;

COMMIT;
