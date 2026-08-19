-- 0078 — Nova Scotia cutover: 1,817 polling divisions to 56 districts, and the
--        56th seat.
--
-- ★ THE FIRST REAL DISSOLVE
-- -------------------------
-- Elections NS publishes POLLING DIVISIONS, not districts: 1,817 features for
-- 56, the most extreme instance in the corpus. `dissolve_by = 'ED_NO'` unions
-- them; 1,761 parts were merged away. Inserted naively that would have been
-- 1,817 rows — a 32x duplication.
--
-- ⚠ Worth recording precisely: `dissolve_by` was a NO-OP until 2026-08-19.
-- `group_features` read the dissolve key, checked it for non-emptiness, and then
-- discarded it — both branches computed `slugify(name)`. It was fixed before
-- this load. But honestly: the fix did not change Nova Scotia's ANSWER, because
-- ED_NAME is byte-consistent across all 1,817 divisions, so grouping by name
-- already produced 56. The dissolve was correct by luck and is now correct by
-- construction, with a cross-feature consistency check that reports disagreeing
-- spellings instead of silently splitting a district in two.
--
-- ── A surgical two-district defect, not a stale province ────────────────────
--   authoritative 56 | held 55 | matched 55
--   mean overlap 99.1462%, and only ONE district below 95%
--
--   `Inverness`  59.80% — reshaped when it was split
--   `Chéticamp-Margarees-Pleasant Bay` — absent entirely
--
-- Everything else in Nova Scotia was correct to ~99%. The 1,946.2 km² of excess
-- in our Inverness polygon matches authoritative Chéticamp's 1,946.5 km² to
-- 0.015%: our Inverness IS the old undivided Inverness, so **99.99% of the new
-- district has been answering with the Inverness MLA**.
--
-- ── The 56th seat, and why the roster hid it ────────────────────────────────
-- Bills 203 and 205 (Elections Act and House of Assembly Act amendments), Royal
-- Assent **2026-04-09**, 65th General Assembly, took the House from 55 to 56 on
-- the 2025 commission's recommendation. `RELEASE_DATE` in the data agrees, and
-- is carried on exactly the two changed districts.
--
-- ⛔ INVERNESS WAS NOT RENAMED. The commission proposed `Inverness-We'koqma'q`
-- and secondary reporting still repeats it, but the enacted Bill 203 creates
-- only the new district and speaks of "the electoral district of Inverness …
-- the remaining part". ED_NAME 34 is `Inverness` and the Assembly lists Kyle
-- MacQuarrie for `Inverness`. Following the commission's name would have looked
-- like a second delta and broken a name-keyed load.
--
-- ★ The roster read 55 members for 55 districts with nothing unattached —
-- internally consistent and wrong, the same correlated-mirror blindness as PEI.
-- **Claude Bourgeois (PC)** won Chéticamp-Margarees-Pleasant Bay in the
-- by-election of **2026-06-23** and has sat since. The newest NS row was updated
-- 2026-08-16, so the ingester is running and still missing him.
--
-- ⓘ Licence, recorded as provenance and not as a gate (operator decision): the
-- ArcGIS service states no licence at all — `licenseInfo` null, `copyrightText`
-- empty — and its own description reads "DO NOT DELETE Electoral Geography for
-- refence in applications", i.e. an internal service rather than a data product.
-- The Open North mirror we were already serving carries Open North's
-- non-transferable permission, not ours. This generation inherits that gap
-- rather than creating it; closing it needs a direct request to Elections NS.
--
-- Run AFTER `load-boundaries --jurisdiction nova-scotia`.
--
-- Forward-only. Apply with:
--   docker exec -i sw-db psql -U sw -d sovereignwatch -v ON_ERROR_STOP=1 \
--     < db/migrations/0078_nova_scotia_boundary_cutover.sql

BEGIN;

DO $$
DECLARE n int;
BEGIN
    SELECT count(*) INTO n FROM constituency_boundaries
     WHERE constituency_id LIKE 'nova-scotia-electoral-districts/%'
       AND boundaries_version = '2026';
    IF n <> 56 THEN
        RAISE EXCEPTION
          'Expected 56 authoritative NS rows, found %. Run '
          '`load-boundaries --jurisdiction nova-scotia` first.', n;
    END IF;
END $$;

UPDATE politicians
   SET constituency_id = 'nova-scotia-electoral-districts/'
                       || split_part(constituency_id, '/', 2)
 WHERE constituency_id LIKE 'nova-scotia-electoral-districts-2019/%';

UPDATE politician_terms
   SET constituency_id = 'nova-scotia-electoral-districts/'
                       || split_part(constituency_id, '/', 2)
 WHERE constituency_id LIKE 'nova-scotia-electoral-districts-2019/%';

DELETE FROM constituency_boundaries
 WHERE constituency_id LIKE 'nova-scotia-electoral-districts-2019/%';

-- ── The 56th member ─────────────────────────────────────────────────────────
-- ⚠ source_id matches the id Open North's ingester will mint, so the next
-- `ingest-ns-mlas` UPDATEs this row instead of inserting a duplicate — the same
-- reasoning as PEI (0074) and Manitoba (0077), avoiding BC's failure (0069).
INSERT INTO politicians (
    source_id, name, first_name, last_name, level, province_territory,
    constituency_name, constituency_id, party, elected_office, is_active
)
SELECT 'opennorth:nova-scotia-legislature:claude-bourgeois', 'Claude Bourgeois',
       'Claude', 'Bourgeois', 'provincial', 'NS',
       'Chéticamp-Margarees-Pleasant Bay',
       'nova-scotia-electoral-districts/cheticamp-margarees-pleasant-bay',
       'Progressive Conservative Association of Nova Scotia', 'MLA', true
 WHERE NOT EXISTS (
    SELECT 1 FROM politicians
     WHERE source_id = 'opennorth:nova-scotia-legislature:claude-bourgeois');

INSERT INTO politician_changes (politician_id, change_type, new_value, severity)
SELECT p.id, 'newly_elected',
       jsonb_build_object(
         'migration', '0078_nova_scotia_boundary_cutover',
         'elected_at', '2026-06-23',
         'inserted_by', 'migration (not an ingester)',
         'reason', 'first member for the district created by Bills 203/205 '
                   '(Royal Assent 2026-04-09); never ingested',
         'verified_against', 'CBC byelection result + Government of Nova Scotia '
                             'news release + nslegislature.ca'),
       'warning'
  FROM politicians p
 WHERE p.source_id = 'opennorth:nova-scotia-legislature:claude-bourgeois'
   AND NOT EXISTS (SELECT 1 FROM politician_changes c
                    WHERE c.politician_id = p.id AND c.change_type = 'newly_elected');

DO $$
DECLARE bnd int; dupes int; orphans int; actives int; attached int; inv numeric;
BEGIN
    SELECT count(*) INTO bnd FROM constituency_boundaries
     WHERE level='provincial' AND province_territory='NS'
       AND effective_from <= CURRENT_DATE
       AND (effective_to IS NULL OR effective_to >= CURRENT_DATE);
    IF bnd <> 56 THEN
        RAISE EXCEPTION 'Expected 56 current NS boundaries, found %', bnd;
    END IF;

    SELECT count(*) INTO dupes FROM (
        SELECT constituency_id FROM constituency_boundaries
         WHERE level='provincial' AND province_territory='NS'
           AND effective_from <= CURRENT_DATE
           AND (effective_to IS NULL OR effective_to >= CURRENT_DATE)
         GROUP BY 1 HAVING count(*) > 1) d;
    IF dupes <> 0 THEN
        RAISE EXCEPTION 'NS cutover left % duplicated districts', dupes;
    END IF;

    SELECT count(*) INTO orphans FROM politicians p
     WHERE p.constituency_id LIKE 'nova-scotia-electoral-districts%'
       AND NOT EXISTS (SELECT 1 FROM constituency_boundaries b
                        WHERE b.constituency_id = p.constituency_id);
    IF orphans <> 0 THEN
        RAISE EXCEPTION 'NS cutover left % orphaned politician rows', orphans;
    END IF;

    SELECT count(*) INTO actives FROM politicians
     WHERE province_territory='NS' AND level='provincial' AND is_active;
    SELECT count(*) INTO attached FROM politicians
     WHERE province_territory='NS' AND level='provincial' AND is_active
       AND constituency_id IS NOT NULL;
    IF actives <> 56 OR attached <> 56 THEN
        RAISE EXCEPTION
          'Expected 56 active NS MLAs all attached, got % active / % attached',
          actives, attached;
    END IF;

    -- ★ The split actually happened. Our old Inverness carried the whole
    -- undivided district at ~4,850 km²; the post-split one is ~2,900. If this
    -- still reads high, the dissolve produced the pre-split shape.
    SELECT area_sqkm::numeric INTO inv FROM constituency_boundaries
     WHERE constituency_id = 'nova-scotia-electoral-districts/inverness'
       AND effective_from <= CURRENT_DATE
       AND (effective_to IS NULL OR effective_to >= CURRENT_DATE);
    IF inv > 4000 THEN
        RAISE EXCEPTION
          'Inverness is still % km² — that is the pre-split district; the '
          'Chéticamp division did not separate', round(inv);
    END IF;

    RAISE NOTICE 'NS: 56 of 56 districts, Inverness now % km² post-split, 56 MLAs attached',
      round(inv);
END $$;

COMMIT;

SELECT refresh_map_views();
