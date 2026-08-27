-- 0103 — retire the roster rows the Open North mirror left shadowing
--        authoritative members.
--
-- The 2026-08-23 run damaged the roster as well as the boundary table. 0101 and
-- 0102 repaired the geometry; this repairs the people. Two distinct causes, kept
-- in separate sections because they are NOT the same defect and must not be
-- asserted together.
--
-- ═══ SECTION A — 221 rows the incident CREATED (Québec municipal) ═════════
--
-- ★ These are not resurrections. `politician_changes` records 224
-- `newly_elected` events on 2026-08-23, every one of them Québec municipal and
-- mirror-sourced, and every corresponding `politicians` row has
-- `created_at::date = 2026-08-23`. The mirror inserted brand-new duplicate
-- person records into municipalities whose roster had already been rebuilt from
-- the MAMH election file (2025-11-02) in f63b6d9. 221 are still active.
--
-- ⚠ The audit row is the evidence, deliberately. `updated_at` cannot be used:
-- 0101's re-point bumped it on ~940 rows, destroying it as an incident marker.
-- `created_at` and `politician_changes.detected_at` are both immutable, and
-- they agree.
--
-- ═══ SECTION B — 29 rows superseded by an authoritative load ══════════════
--
-- ⛔ A DIFFERENT DEFECT, AND OLDER THAN THE INCIDENT. Federal 11, Yukon 10,
-- Newfoundland 8. These carry no 2026-08-23 audit row: the authoritative
-- ingesters that loaded the current rosters on 2026-08-19 added the sitting
-- members but never retired the mirror cohort they replaced. Yukon is the clean
-- illustration — the territory voted, `direct:yukonassembly-ca:` loaded the 21
-- sitting MLAs, and `opennorth:yukon-legislature:` kept the defeated cohort
-- active alongside them, so Klondike showed both Sandy Silver and Brent
-- McDonald. Federal shows Chrystia Freeland still holding University—Rosedale
-- next to Danielle Martin.
--
-- ⚠ Not every Section B pair is a departed member. Nine of the federal eleven
-- are the SAME person under two name forms — `Jasraj Hallan` /
-- `Jasraj Singh Hallan`, `Rob Oliphant` / `Robert Oliphant`. Retiring the
-- mirror row is still correct: openparliament is the federal source of record
-- and the mirror row is a duplicate person record either way. It is deactivated,
-- never deleted, so the duplicate-politician audit can still merge it later.
--
-- ⛔ SCOPE THE SEAT MATCH. An earlier draft matched on
-- (level, province, constituency slug) alone and reported 286 Québec municipal
-- duplicates. `District 1` exists in dozens of Québec municipalities, so it was
-- pairing councillors in different cities — the same ambiguity 0089 fixed for
-- boundaries, where Gatineau's Plateau councillor landed on Québec City's
-- Plateau 400 km away. Section A avoids it entirely by keying on the audit row.
-- Section B is federal/provincial only, where a district name IS unique within
-- its jurisdiction.
--
-- ═══ SECTION C — 4 Yukon members on districts that no longer exist ═══════
--
-- Section B leaves Yukon at 22 sitting members for 21 seats, because it can
-- only retire a mirror row whose seat an authoritative member also holds — and
-- `direct:yukonassembly-ca:` has so far loaded only 13 of the 21. The residue
-- sits on districts the 2025 redistribution ABOLISHED: Takhini-Kopper King,
-- Pelly-Nisutlin, Watson Lake, and Mount Lorne-Southern Lakes. 0101 already
-- detached them, because no live boundary carries those names.
--
-- ★ The test is "their district name matches no live boundary in their
-- jurisdiction", and across the whole country it selects exactly 8 rows: these
-- 4 and 4 in Saskatchewan.
--
-- ⛔ SASKATCHEWAN IS DELIBERATELY EXCLUDED. SK sits at exactly 61 actives for
-- 61 seats, so retiring anyone there would manufacture four vacancies in a full
-- chamber — the evidence says its roster is complete and its district NAMES
-- drifted (2012 → 2022 Representation Act), not that four members left. Yukon
-- is over its seat count, which is positive evidence of surplus. Act where the
-- count says "too many", never where it says "exactly right".
--
-- Forward-only. Apply with:
--   docker exec -i sw-db psql -U sw -d sovereignwatch -v ON_ERROR_STOP=1 \
--     < db/migrations/0103_retire_mirror_shadow_roster.sql

BEGIN;

-- ── Section A ────────────────────────────────────────────────────────────
CREATE TEMP TABLE _incident_rows ON COMMIT DROP AS
SELECT p.id FROM politicians p
 WHERE p.is_active
   AND p.source_id LIKE 'opennorth:%'
   AND p.created_at::date = DATE '2026-08-23'
   AND EXISTS (SELECT 1 FROM politician_changes c
                WHERE c.politician_id = p.id
                  AND c.change_type = 'newly_elected'
                  AND c.detected_at::date = DATE '2026-08-23');

-- ── Section B ────────────────────────────────────────────────────────────
CREATE TEMP TABLE _superseded ON COMMIT DROP AS
SELECT p.id FROM politicians p
 WHERE p.is_active
   AND p.source_id LIKE 'opennorth:%'
   AND p.level IN ('federal', 'provincial')
   AND EXISTS (
       SELECT 1 FROM politicians q
        WHERE q.is_active AND q.id <> p.id
          AND q.source_id NOT LIKE 'opennorth:%'
          AND q.level = p.level
          AND (p.level = 'federal'
               OR q.province_territory = p.province_territory)
          AND cpd_slugify(q.constituency_name) = cpd_slugify(p.constituency_name));

CREATE TEMP TABLE _abolished ON COMMIT DROP AS
SELECT p.id FROM politicians p
 WHERE p.is_active
   AND p.source_id LIKE 'opennorth:%'
   AND p.level = 'provincial'
   AND p.province_territory = 'YT'
   AND p.constituency_name IS NOT NULL
   AND NOT EXISTS (
       SELECT 1 FROM constituency_boundaries b
        WHERE b.level = p.level
          AND b.province_territory = p.province_territory
          AND b.effective_from <= CURRENT_DATE
          AND (b.effective_to IS NULL OR b.effective_to >= CURRENT_DATE)
          AND cpd_slugify(b.name) = cpd_slugify(p.constituency_name))
   AND p.id NOT IN (SELECT id FROM _superseded);

DO $$
DECLARE a int; b int; c int; overlap int;
BEGIN
    SELECT count(*) INTO a FROM _incident_rows;
    SELECT count(*) INTO b FROM _superseded;
    SELECT count(*) INTO c FROM _abolished;
    IF c <> 4 THEN
        RAISE EXCEPTION 'Section C is % rows, not the measured 4 Yukon '
          'abolished-district members', c;
    END IF;
    IF a <> 221 THEN
        RAISE EXCEPTION 'Section A is % rows, not the measured 221 — re-measure '
          'before retiring anyone', a;
    END IF;
    IF b <> 29 THEN
        RAISE EXCEPTION 'Section B is % rows, not the measured 29 (fed 11 / '
          'YT 10 / NL 8)', b;
    END IF;
    -- The two causes must not overlap; if they do, one of the rules is wrong.
    SELECT count(*) INTO overlap
      FROM _incident_rows i JOIN _superseded s ON s.id = i.id;
    IF overlap <> 0 THEN
        RAISE EXCEPTION '% rows classified under both causes', overlap;
    END IF;
END $$;

-- ⛔ Deactivate, never delete. A deleted row cannot be audited, cannot be
-- merged by the duplicate-politician pass, and takes its speech and vote
-- attributions with it.
UPDATE politicians SET is_active = false, updated_at = now()
 WHERE id IN (SELECT id FROM _incident_rows
              UNION ALL SELECT id FROM _superseded
              UNION ALL SELECT id FROM _abolished);

UPDATE politician_terms SET ended_at = now()
 WHERE ended_at IS NULL
   AND politician_id IN (SELECT id FROM _incident_rows
                         UNION ALL SELECT id FROM _superseded
                         UNION ALL SELECT id FROM _abolished);

INSERT INTO politician_changes (politician_id, change_type, old_value, new_value, severity)
SELECT id, 'retired',
       jsonb_build_object('is_active', true),
       jsonb_build_object('is_active', false,
                          'via', '0103_retire_mirror_shadow_roster',
                          'cause', 'open-north mirror row shadowing an '
                                   'authoritative member'),
       'notable'
  FROM (SELECT id FROM _incident_rows
        UNION ALL SELECT id FROM _superseded
        UNION ALL SELECT id FROM _abolished) x;

-- ── Postconditions ───────────────────────────────────────────────────────
DO $$
DECLARE r record; got int;
BEGIN
    -- No chamber over its seat count. Asserted against jurisdiction_sources,
    -- which this migration does not touch — an independent witness.
    FOR r IN
        SELECT p.province_territory AS ju, count(*) AS actives, j.seats
          FROM politicians p
          JOIN jurisdiction_sources j ON j.jurisdiction = p.province_territory
         WHERE p.is_active AND p.level = 'provincial'
         GROUP BY 1, 3 HAVING count(*) > j.seats
    LOOP
        RAISE EXCEPTION 'provincial/%: % actives for % seats',
                        r.ju, r.actives, r.seats;
    END LOOP;

    SELECT count(*) INTO got FROM politicians
     WHERE is_active AND level = 'federal' AND elected_office = 'MP';
    IF got > 343 THEN
        RAISE EXCEPTION 'federal: % sitting MPs for 343 seats', got;
    END IF;

    -- ⚠ Retiring a member must not orphan a boundary or strand a term.
    SELECT count(*) INTO got FROM politicians p
     WHERE p.is_active AND p.constituency_id IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM constituency_boundaries b
                        WHERE b.constituency_id = p.constituency_id);
    IF got <> 0 THEN
        RAISE EXCEPTION '% sitting members point at a non-existent boundary', got;
    END IF;

    RAISE NOTICE '0103: 221 incident + 29 superseded + 4 abolished-district rows retired';
END $$;

COMMIT;

SELECT refresh_map_views();
