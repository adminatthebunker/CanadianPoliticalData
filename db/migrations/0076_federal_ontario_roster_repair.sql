-- 0076 — Federal + Ontario roster repair: 9 same-person merges, 3 departed
--        members still flagged sitting, and a correction to 0072's comment.
--
-- ⛔ FIRST, A CORRECTION TO THE RECORD
-- -----------------------------------
-- Migration `0072` (applied) says in a comment:
--
--     "Scarborough Southwest holds Bill Blair AND `op:doly-begum` — Doly Begum
--      is an Ontario MPP, misclassified as federal."
--
-- **That is wrong, and it is exactly backwards.** Verified since:
--   • Bill Blair resigned as MP on 2026-02-02 on appointment as High
--     Commissioner to the United Kingdom.
--   • Doly Begum resigned as MPP on 2026-02-03 to contest the resulting federal
--     by-election.
--   • She WON it on 2026-04-13 and has been the MP for Scarborough Southwest
--     since.
--
-- So `op:doly-begum` is the correct current federal row and the OPENNORTH row
-- (Bill Blair) is the stale one. 0072 is not edited — it is applied, and
-- migrations are forward-only — so the correction lives here instead.
--
-- ⚠ The lesson is worth more than the fix: I read "an Ontario MPP appears in the
-- federal table" as a classification bug because that is the usual cause, and
-- did not check whether she had changed level. A duplicate pair is not evidence
-- of a mislabel; it is evidence that something changed and one side did not
-- follow.
--
-- ── The federal picture ─────────────────────────────────────────────────────
-- 354 active MPs against 343 seats: 11 pairs sharing a district, each an
-- `op:*` (openparliament) row against an `opennorth:house-of-commons:*` row.
-- The split is perfectly clean and it decides the merge direction:
--
--     every op:*        row carries openparliament_slug AND all the speeches
--     every opennorth:* row carries neither (0 speeches, no native id)
--
-- ⚠ Note this is the OPPOSITE direction from British Columbia in 0069, where
-- the opennorth rows held the native ids and the traditional names. There is no
-- global "prefer source X" rule — the keeper is whichever row carries the native
-- identifier and the content, and that has to be checked per jurisdiction.
--
-- The 11 split into two classes that must NOT be handled the same way:
--
--   A. NINE are one person under two spellings. The opennorth twin holds no
--      speeches but does hold socials and constituency offices, which are real
--      and must move:
--        Jasraj Hallan/Jasraj Singh Hallan · Shuv/Shuvaloy Majumdar ·
--        Michelle Rempel/Rempel Garner · Rob/Robert Oliphant ·
--        Bobby/Robert J. Morrissey · Vincent/Vincent Neil Ho ·
--        Rhéal/Rhéal Éloi Fortin · Jessica Fancy/Fancy-Landry ·
--        Tatiana Auguste (identical name, two ids)
--
--   B. TWO are DIFFERENT PEOPLE, where the opennorth row is a departed member:
--        Scarborough Southwest — Bill Blair    (resigned 2026-02-02)
--        University—Rosedale   — Chrystia Freeland (seat won by Danielle Martin)
--      ⛔ These must be DEACTIVATED, never merged. Moving Bill Blair's
--      constituency offices onto Doly Begum would attach one member's offices to
--      another — a worse error than the duplicate it replaced.
--
-- ⚠ Class A keeps the op:* display name. Several opennorth spellings are
-- arguably better (`Michelle Rempel Garner`, `Rhéal Éloi Fortin`), but choosing
-- per-person across nine MPs without an authority is guesswork, and openparliament
-- takes its names from ourcommons.ca. The discarded variants are recorded in
-- politician_changes. A `name_alt` column is the real fix and is a known gap —
-- the same one flagged for BC's Indigenous traditional names in 0069.
--
-- ── Ontario ─────────────────────────────────────────────────────────────────
-- ON showed 124 boundaries, 123 active MPPs, 122 attached. Investigated, and
-- BOTH gaps are correct:
--   • Scarborough Southwest — vacant since Begum resigned 2026-02-03.
--   • York—Simcoe — vacant since Caroline Mulroney resigned 2026-06-05;
--     by-election called for 2026-09-03.
-- The only defect is Begum's Ontario row, correctly filed under
-- `ola.org:former-mpps` and still flagged `is_active = true`.
--
-- ★ CONSEQUENCE FOR THE FORTHCOMING check-boundary-coverage
-- ---------------------------------------------------------
-- Ontario proves `active_politicians == seat_count` is TOO STRICT. Vacancies are
-- normal and legitimate — Ontario has two right now. The assertion must be
-- `actives <= seats`, with `actives > seats` (duplicates) the error and
-- `actives < seats` reported as a vacancy count, not a failure. An alarm that
-- fires on correct data gets muted, and a muted alarm is worse than none.
--
-- Forward-only. Apply with:
--   docker exec -i sw-db psql -U sw -d sovereignwatch -v ON_ERROR_STOP=1 \
--     < db/migrations/0076_federal_ontario_roster_repair.sql

BEGIN;

-- ── Class A: nine same-person merges ────────────────────────────────────────
CREATE TEMP TABLE _fed_merge ON COMMIT DROP AS
SELECT k.id AS keep_id, d.id AS drop_id, k.name AS keep_name, d.name AS drop_name
  FROM (VALUES
    ('op:jasraj-singh-hallan',  'opennorth:house-of-commons:jasraj-hallan'),
    ('op:shuv-majumdar',        'opennorth:house-of-commons:shuvaloy-majumdar'),
    ('op:michelle-rempel',      'opennorth:house-of-commons:michelle-rempel-garner'),
    ('op:rob-oliphant',         'opennorth:house-of-commons:robert-oliphant'),
    ('op:bobby-morrissey',      'opennorth:house-of-commons:robert-j.-morrissey'),
    ('op:vincent-ho',           'opennorth:house-of-commons:vincent-neil-ho'),
    ('op:rheal-fortin',         'opennorth:house-of-commons:rhéal-éloi-fortin'),
    ('op:jessica-fancy-landry', 'opennorth:house-of-commons:jessica-fancy'),
    ('op:tatiana-auguste',      'opennorth:house-of-commons:tatiana-auguste')
  ) AS v(keep_src, drop_src)
  JOIN politicians k ON k.source_id = v.keep_src
  JOIN politicians d ON d.source_id = v.drop_src;

DO $$
DECLARE n int; sp int;
BEGIN
    SELECT count(*) INTO n FROM _fed_merge;
    IF n <> 9 THEN
        RAISE EXCEPTION 'Expected 9 federal merge pairs, resolved %', n;
    END IF;
    -- ⛔ Refuse if any drop row turns out to hold speeches after all: that would
    -- mean the clean "op has everything" split no longer holds, and a delete
    -- would destroy content.
    SELECT count(*) INTO sp FROM _fed_merge m
     WHERE EXISTS (SELECT 1 FROM speeches s WHERE s.politician_id = m.drop_id);
    IF sp <> 0 THEN
        RAISE EXCEPTION
          '% federal drop-rows hold speeches; this migration assumes they hold '
          'none and would lose them', sp;
    END IF;
END $$;

-- ⛔ TRANSFER THE DISTRICT LINK FIRST. The 11 `op:*` keepers all carry a NULL
-- constituency_id — the boundary link lives on the opennorth twin, which is why
-- they showed as "unattached" all along. Deleting the twin before moving the
-- link would leave nine sitting MPs pointing at nothing, and the post-condition
-- below catches exactly that (it did, on the first attempt).
--
-- ⓘ Safe for the two class-B pairs as well: the PERSON changed but the DISTRICT
-- did not, so Doly Begum inherits Bill Blair's Scarborough Southwest link and
-- Danielle Martin inherits Chrystia Freeland's University—Rosedale link. That is
-- the correct answer, not a coincidence — the pairing key was the district.
UPDATE politicians k
   SET constituency_id = d.constituency_id, updated_at = now()
  FROM politicians d
 WHERE d.source_id IN (
        'opennorth:house-of-commons:jasraj-hallan',
        'opennorth:house-of-commons:shuvaloy-majumdar',
        'opennorth:house-of-commons:michelle-rempel-garner',
        'opennorth:house-of-commons:robert-oliphant',
        'opennorth:house-of-commons:robert-j.-morrissey',
        'opennorth:house-of-commons:vincent-neil-ho',
        'opennorth:house-of-commons:rhéal-éloi-fortin',
        'opennorth:house-of-commons:jessica-fancy',
        'opennorth:house-of-commons:tatiana-auguste',
        'opennorth:house-of-commons:bill-blair',
        'opennorth:house-of-commons:chrystia-freeland')
   AND k.level = 'federal' AND k.is_active AND k.elected_office = 'MP'
   AND k.constituency_id IS NULL
   AND k.id <> d.id
   AND k.constituency_name = d.constituency_name
   AND d.constituency_id IS NOT NULL;

-- Record the discarded name variant before it disappears.
INSERT INTO politician_changes (politician_id, change_type, old_value, new_value, severity)
SELECT m.keep_id, 'name_change',
       jsonb_build_object('discarded_variant', m.drop_name),
       jsonb_build_object('kept', m.keep_name,
                          'migration', '0076_federal_ontario_roster_repair',
                          'note', 'duplicate opennorth row merged; no name_alt '
                                  'column exists to retain the variant'),
       'info'
  FROM _fed_merge m WHERE m.keep_name <> m.drop_name;

-- Socials carry a unique index on (politician_id, platform, lower(handle)).
DELETE FROM politician_socials sd
 USING _fed_merge m, politician_socials sk
 WHERE sd.politician_id = m.drop_id AND sk.politician_id = m.keep_id
   AND sk.platform = sd.platform AND lower(sk.handle) = lower(sd.handle);
UPDATE politician_socials sd SET politician_id = m.keep_id
  FROM _fed_merge m WHERE sd.politician_id = m.drop_id;

-- ★ Offices are the reason this is a merge: the opennorth rows carry the
-- constituency office addresses and the op:* rows largely do not.
UPDATE politician_offices o SET politician_id = m.keep_id
  FROM _fed_merge m WHERE o.politician_id = m.drop_id;
UPDATE politician_committees c SET politician_id = m.keep_id
  FROM _fed_merge m WHERE c.politician_id = m.drop_id;
UPDATE politician_changes ch SET politician_id = m.keep_id
  FROM _fed_merge m WHERE ch.politician_id = m.drop_id;

DELETE FROM politician_terms t USING _fed_merge m WHERE t.politician_id = m.drop_id;
DELETE FROM politicians p USING _fed_merge m WHERE p.id = m.drop_id;

-- ── Class B: three departed members still flagged sitting ───────────────────
-- ⛔ Deactivated, NOT merged, and NOT deleted. They are real people with real
-- service records; `is_active = false` removes them from every roster and
-- lookup while keeping their history and their offices attached to them rather
-- than to their successors.
UPDATE politicians SET is_active = false, updated_at = now()
 WHERE source_id IN (
   -- Resigned as MP 2026-02-02, appointed High Commissioner to the UK.
   'opennorth:house-of-commons:bill-blair',
   -- Seat won by Danielle Martin; Freeland no longer sits for it.
   'opennorth:house-of-commons:chrystia-freeland'
 ) AND is_active;

-- Resigned as MPP 2026-02-03; already correctly filed under former-mpps, but
-- left flagged active, so she counted toward Ontario's sitting members.
UPDATE politicians SET is_active = false, updated_at = now()
 WHERE source_id = 'ola.org:former-mpps:member_id=7508' AND is_active;

DO $$
DECLARE mps int; fdupes int; on_act int; on_dupes int; unattached int; vac int;
BEGIN
    SELECT count(*) INTO mps FROM politicians
     WHERE level='federal' AND is_active AND elected_office='MP';
    IF mps <> 343 THEN
        RAISE EXCEPTION 'Expected 343 active MPs, found %', mps;
    END IF;

    SELECT count(*) INTO fdupes FROM (
        SELECT constituency_id FROM politicians
         WHERE level='federal' AND is_active AND elected_office='MP'
           AND constituency_id IS NOT NULL
         GROUP BY 1 HAVING count(*) > 1) d;
    IF fdupes <> 0 THEN
        RAISE EXCEPTION '% federal districts still resolve to two MPs', fdupes;
    END IF;

    SELECT count(*) INTO unattached FROM politicians
     WHERE level='federal' AND is_active AND elected_office='MP'
       AND constituency_id IS NULL;
    IF unattached <> 0 THEN
        RAISE EXCEPTION '% sitting MPs have no district', unattached;
    END IF;

    SELECT count(*) INTO on_act FROM politicians
     WHERE province_territory='ON' AND level='provincial' AND is_active;
    SELECT count(*) INTO on_dupes FROM (
        SELECT constituency_id FROM politicians
         WHERE province_territory='ON' AND level='provincial' AND is_active
           AND constituency_id IS NOT NULL
         GROUP BY 1 HAVING count(*) > 1) d;
    IF on_act <> 122 OR on_dupes <> 0 THEN
        RAISE EXCEPTION
          'Expected 122 sitting Ontario MPPs (124 seats less 2 vacancies) with '
          'no duplicates; got % active, % duplicated', on_act, on_dupes;
    END IF;

    SELECT count(*) INTO vac FROM constituency_boundaries b
     WHERE b.level='provincial' AND b.province_territory='ON'
       AND NOT EXISTS (SELECT 1 FROM politicians p
                        WHERE p.is_active AND p.constituency_id = b.constituency_id);
    RAISE NOTICE 'federal: 343 MPs / 343 seats, all attached. Ontario: 122 MPPs, % genuine vacancies (Scarborough Southwest, York—Simcoe)', vac;
END $$;

COMMIT;

SELECT refresh_map_views();
