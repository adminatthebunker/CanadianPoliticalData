-- 0085 — Repair the roster damage done by the 23:40 Open North refresh, and
--        record why the ingester can no longer do it again.
--
-- ⛔ WHAT HAPPENED
-- ----------------
-- The weekly Open North roster suite ran at 2026-08-19 23:40 — `ingest-mps`,
-- `ingest-mlas`, `ingest-bc-mlas`, `ingest-ontario-mpps`,
-- `ingest-new-brunswick-mlas`, `ingest-nl-mhas`, `ingest-pei-mlas`,
-- `ingest-yukon-mlas`, `ingest-mb-mlas`, `ingest-nt-mlas` — and each one
-- overwrote two columns it had no business overwriting:
--
--   • `constituency_id`, rewritten from the rep's Open North `boundary_url`,
--     i.e. the OLD mirror id. Those boundaries were deleted by the cutovers, so
--     726 sitting members across 8 jurisdictions ended up pointing at geometry
--     that does not exist. Every bad value is the authoritative slug under a
--     retired prefix, which is what makes this repairable by a prefix swap.
--
--   • `is_active`, forced true for everyone in the feed — resurrecting members
--     we had deliberately retired. Newfoundland went back to 48 sitting MHAs for
--     40 seats and Yukon to 32 for 21: the cohorts defeated in the 2025 general
--     elections, which Open North still lists because it is a full cycle stale.
--
-- ★ This is the third distinct way the same mirror undid this programme in one
-- evening. First it resurrected deleted BOUNDARIES (0084). Then it retired a
-- hand-verified sitting member (0084). Now it has detached and un-retired the
-- ROSTER. The common cause is that a mirror we no longer trust was still
-- authoritative over columns we had deliberately set.
--
-- Code fix already applied in `opennorth.py`: the upsert now leaves
-- `constituency_id` and `is_active` alone for federal and provincial rows —
-- municipal is still mirrored and still writes both. The ingest continues to run
-- (it remains the only roster source for most jurisdictions); it simply no
-- longer overrules a cutover.
--
-- ⚠ Accepted consequence: Open North can no longer REACTIVATE a provincial
-- member. A genuinely re-elected former member now needs a deliberate
-- reactivation, and `check-boundary-coverage` reports the shortfall as a vacancy
-- rather than hiding it. Given the feed's staleness that is the safer default.
--
-- Forward-only. Apply with:
--   docker exec -i sw-db psql -U sw -d sovereignwatch -v ON_ERROR_STOP=1 \
--     < db/migrations/0085_repair_roster_after_mirror_overwrite.sql

BEGIN;

-- ── 1. Prefix swap: every bad id is the right slug under a retired prefix ───
CREATE TEMP TABLE _prefix_fix(old_prefix text, new_prefix text) ON COMMIT DROP;
INSERT INTO _prefix_fix VALUES
  ('federal-electoral-districts-2023-representation-order', 'federal-electoral-districts'),
  ('ontario-electoral-districts-representation-act-2015',   'ontario-electoral-districts'),
  ('alberta-electoral-districts-2017',                      'alberta-electoral-districts'),
  ('manitoba-electoral-districts-2018',                     'manitoba-electoral-districts'),
  ('british-columbia-electoral-districts-2015-redistribution', 'british-columbia-electoral-districts'),
  ('prince-edward-island-electoral-districts-2017',         'prince-edward-island-electoral-districts'),
  ('new-brunswick-electoral-districts-2018',                'new-brunswick-electoral-districts'),
  ('yukon-electoral-districts-2015',                        'yukon-electoral-districts'),
  ('quebec-electoral-districts-2017',                       'quebec-electoral-districts'),
  ('northwest-territories-electoral-districts',             'northwest-territories-electoral-districts-2013');

UPDATE politicians p
   SET constituency_id = f.new_prefix || '/' || split_part(p.constituency_id, '/', 2),
       updated_at = now()
  FROM _prefix_fix f
 WHERE p.constituency_id LIKE f.old_prefix || '/%'
   AND EXISTS (
     SELECT 1 FROM constituency_boundaries b
      WHERE b.constituency_id
          = f.new_prefix || '/' || split_part(p.constituency_id, '/', 2));

UPDATE politician_terms t
   SET constituency_id = f.new_prefix || '/' || split_part(t.constituency_id, '/', 2)
  FROM _prefix_fix f
 WHERE t.constituency_id LIKE f.old_prefix || '/%'
   AND EXISTS (
     SELECT 1 FROM constituency_boundaries b
      WHERE b.constituency_id
          = f.new_prefix || '/' || split_part(t.constituency_id, '/', 2));

-- Anything still pointing at a boundary that does not exist is detached rather
-- than left dangling; the slug re-attach below picks it up if it can.
UPDATE politicians p SET constituency_id = NULL
 WHERE p.is_active AND p.level IN ('federal', 'provincial')
   AND p.constituency_id IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM constituency_boundaries b
                    WHERE b.constituency_id = p.constituency_id);

-- ── 2. Re-retire the cohorts the refresh brought back ───────────────────────
-- ⚠ Same explicit source_id lists as 0076, 0079 and 0080 — deliberately
-- repeated rather than re-derived, so this migration asserts the same set those
-- did and cannot quietly retire someone new.
UPDATE politicians SET is_active = false, updated_at = now()
 WHERE is_active AND source_id IN (
   -- Newfoundland: defeated 2025-10-14 (0080)
   'opennorth:newfoundland-labrador-legislature:steve-crocker',
   'opennorth:newfoundland-labrador-legislature:gerry-byrne',
   'opennorth:newfoundland-labrador-legislature:john-haggie',
   'opennorth:newfoundland-labrador-legislature:perry-trimper',
   'opennorth:newfoundland-labrador-legislature:derek-bennett',
   'opennorth:newfoundland-labrador-legislature:krista-lynn-howell',
   'opennorth:newfoundland-labrador-legislature:scott-reid',
   'opennorth:newfoundland-labrador-legislature:siobhan-coady',
   -- Yukon: did not return in the 36th Assembly (0079)
   'opennorth:yukon-legislature:sandy-silver',
   'opennorth:yukon-legislature:jeremy-harper',
   'opennorth:yukon-legislature:jeanie-mclean',
   'opennorth:yukon-legislature:john-streicker',
   'opennorth:yukon-legislature:stacey-hassard',
   'opennorth:yukon-legislature:geraldine-van-bibber',
   'opennorth:yukon-legislature:ranj-pillai',
   'opennorth:yukon-legislature:nils-clarke',
   'opennorth:yukon-legislature:tracy-anne-mcphee',
   'opennorth:yukon-legislature:annie-blake',
   'opennorth:yukon-legislature:richard-mostyn',
   -- Federal: resigned / superseded (0076)
   'opennorth:house-of-commons:bill-blair',
   'opennorth:house-of-commons:chrystia-freeland',
   -- Federal: same-person duplicates of the op:* rows that hold the speeches
   'opennorth:house-of-commons:jasraj-hallan',
   'opennorth:house-of-commons:shuvaloy-majumdar',
   'opennorth:house-of-commons:michelle-rempel-garner',
   'opennorth:house-of-commons:robert-oliphant',
   'opennorth:house-of-commons:robert-j.-morrissey',
   'opennorth:house-of-commons:vincent-neil-ho',
   'opennorth:house-of-commons:rhéal-éloi-fortin',
   'opennorth:house-of-commons:jessica-fancy',
   'opennorth:house-of-commons:tatiana-auguste',
   -- Ontario: resigned as MPP 2026-02-03 to contest a federal by-election
   'ola.org:former-mpps:member_id=7508'
 );

-- Yukon's three re-elected incumbents changed district; the refresh reverted
-- their constituency_name to the abolished one (0079).
UPDATE politicians SET constituency_name = 'Whistle Bend North', updated_at = now()
 WHERE source_id = 'opennorth:yukon-legislature:yvonne-clarke' AND is_active;
UPDATE politicians SET constituency_name = 'Watson Lake-Ross River-Faro', updated_at = now()
 WHERE source_id = 'opennorth:yukon-legislature:patti-mcleod' AND is_active;
UPDATE politicians SET constituency_name = 'Takhini', updated_at = now()
 WHERE source_id = 'opennorth:yukon-legislature:kate-white' AND is_active;

-- ── 3. Re-attach anything still loose, by authoritative slug ────────────────
-- ⚠ `cpd_slugify` (0080), never a hand-written regex: it strips apostrophes and
-- periods before hyphenating, which a naive expression does not.
UPDATE politicians p
   SET constituency_id = b.constituency_id, updated_at = now()
  FROM constituency_boundaries b
 WHERE p.is_active AND p.constituency_id IS NULL
   AND p.level = 'provincial'
   AND b.level = 'provincial'
   AND b.province_territory = p.province_territory
   AND b.effective_from <= CURRENT_DATE
   AND (b.effective_to IS NULL OR b.effective_to >= CURRENT_DATE)
   AND split_part(b.constituency_id, '/', 2) = cpd_slugify(p.constituency_name);

DO $$
DECLARE bad int; rec record;
BEGIN
    SELECT count(*) INTO bad FROM politicians p
     WHERE p.is_active AND p.level IN ('federal', 'provincial')
       AND p.constituency_id IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM constituency_boundaries b
                        WHERE b.constituency_id = p.constituency_id);
    IF bad <> 0 THEN
        RAISE EXCEPTION '% members still point at a non-existent boundary', bad;
    END IF;

    FOR rec IN
        SELECT j.jurisdiction, j.seats,
               (SELECT count(*) FROM politicians p
                 WHERE p.level='provincial' AND p.province_territory=j.jurisdiction
                   AND p.is_active) AS actives
          FROM jurisdiction_sources j
         WHERE j.jurisdiction IN ('AB','BC','MB','NB','NL','NS','NT','NU','ON','PE','QC','SK','YT')
    LOOP
        IF rec.actives > rec.seats THEN
            RAISE EXCEPTION
              '% has % sitting members for % seats — the refresh reactivated '
              'someone this migration did not re-retire',
              rec.jurisdiction, rec.actives, rec.seats;
        END IF;
    END LOOP;

    RAISE NOTICE 'roster repaired: 0 dangling constituency_ids, no chamber over its seat count';
END $$;

COMMIT;

SELECT refresh_map_views();
