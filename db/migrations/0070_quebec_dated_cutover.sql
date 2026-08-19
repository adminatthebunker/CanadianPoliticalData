-- 0070 — Quebec: the first DATED cutover. Two generations coexist, and the
--        switch happens by itself on 2026-08-29 with nobody present.
--
-- ★ WHAT MAKES THIS DIFFERENT FROM EVERY CUTOVER SO FAR
-- -----------------------------------------------------
-- 0064-0069 all did the same thing: load the new generation, DELETE the old one,
-- done in one transaction on the day. That works when the new map is already law.
-- Quebec's is not law yet — it becomes law in days — so deleting the 2017 map
-- today would answer every Quebec address from a map that has not taken effect.
--
-- Instead both generations sit in the table with non-overlapping date ranges and
-- `currentBoundary()` picks between them. Migration 0021 designed for this in
-- 2024 and nothing has ever used it.
--
-- ⛔ THE DATE, AND WHY IT IS A CEILING RATHER THAN A GUESS
-- -------------------------------------------------------
-- `Loi visant à assurer la représentation effective des électeurs`, 2026 c. 15
-- art. 2: the new list takes effect when the 43rd legislature ENDS — that day,
-- not the day after. (⚠ Nunavut's rule is "the 1st day following dissolution";
-- do not carry that pattern across.)
--
-- `Loi sur l'Assemblée nationale` art. 6 fixes when that is: the legislature
-- expires on 29 August of the fourth calendar year after the last general
-- election. Last GE 2022-10-03 → **2026-08-29**. The Lieutenant-Governor may
-- dissolve earlier at the Premier's request; it cannot run later.
--
-- ★ So the error is ONE-SIDED. 2026-08-29 is the latest lawful date, so this can
-- only ever make us late — serving the still-lawful 2017 map for a few extra
-- days if dissolution is called early. It can never activate a map that is not
-- yet law. A date taken from the polling day (2026-10-05) would have failed the
-- other way and served a REPEALED map for the whole five-week writ period.
--
-- ⚠ If dissolution is proclaimed before the 29th, move both dates. One UPDATE on
-- each generation; no reload.
--
-- Run AFTER both loads:
--   load-boundaries --spec-file .../quebec-2026.py             (127 rows, v2026)
--   load-boundaries --spec-file .../quebec-2017-chicoutimi.py  (1 row,   v2017)
--
-- Forward-only. Apply with:
--   docker exec -i sw-db psql -U sw -d sovereignwatch -v ON_ERROR_STOP=1 \
--     < db/migrations/0070_quebec_dated_cutover.sql

BEGIN;

DO $$
DECLARE n2026 int; nchic int; nold int;
BEGIN
    SELECT count(*) INTO n2026 FROM constituency_boundaries
     WHERE constituency_id LIKE 'quebec-electoral-districts/%'
       AND boundaries_version = '2026';
    IF n2026 <> 127 THEN
        RAISE EXCEPTION
          'Expected 127 QC 2026 rows, found %. Run the quebec-2026 load first.',
          n2026;
    END IF;

    SELECT count(*) INTO nchic FROM constituency_boundaries
     WHERE constituency_id = 'quebec-electoral-districts/chicoutimi'
       AND boundaries_version = '2017';
    IF nchic <> 1 THEN
        RAISE EXCEPTION
          'Chicoutimi is missing from the 2017 generation. Run the '
          'quebec-2017-chicoutimi load first.';
    END IF;

    SELECT count(*) INTO nold FROM constituency_boundaries
     WHERE constituency_id LIKE 'quebec-electoral-districts-2017/%';
    IF nold <> 124 THEN
        RAISE EXCEPTION 'Expected 124 legacy QC rows, found %', nold;
    END IF;
END $$;

-- ── 1. Move the 2017 generation onto the generation-free prefix ─────────────
-- ⚠ Also corrects two things the Open North mirror got wrong for every row it
-- ever wrote: `boundaries_version = 'current'` (a label that cannot survive a
-- second generation existing) and `effective_from = 2023-01-01` (hardcoded in
-- opennorth.py, unrelated to any legal event). The real date is the dissolution
-- that preceded the 2018 general election.
--
-- ⓘ No conflict with the Chicoutimi row just loaded: Chicoutimi is precisely the
-- district these 124 do not include.
UPDATE constituency_boundaries
   SET constituency_id = 'quebec-electoral-districts/'
                       || split_part(constituency_id, '/', 2),
       source_set = 'quebec-electoral-districts',
       boundaries_version = '2017',
       effective_from = DATE '2018-08-23',
       effective_to = DATE '2026-08-28',
       updated_at = now()
 WHERE constituency_id LIKE 'quebec-electoral-districts-2017/%';

UPDATE politicians
   SET constituency_id = 'quebec-electoral-districts/'
                       || split_part(constituency_id, '/', 2)
 WHERE constituency_id LIKE 'quebec-electoral-districts-2017/%';

UPDATE politician_terms
   SET constituency_id = 'quebec-electoral-districts/'
                       || split_part(constituency_id, '/', 2)
 WHERE constituency_id LIKE 'quebec-electoral-districts-2017/%';

-- ── 2. Chicoutimi's member ──────────────────────────────────────────────────
-- ★ The missing polygon and the missing MNA turned out to be the SAME district.
-- Marie-Karlynn Laflamme (qc_assnat_id 20193) won the Chicoutimi by-election on
-- 2026-02-23 for the Parti québécois and was sworn in 2026-03-03, taking the
-- seat from the CAQ. Our ingester filed her under
-- `assnat.qc.ca:former-mnas` with a NULL constituency_name and a NULL party,
-- while still flagging her active — so Quebec read as 125 active members with
-- one of them representing nowhere, and Chicoutimi had neither a boundary nor a
-- representative.
--
-- ⚠ The `former-mnas` source_id is left as-is. It is wrong, but it is the row's
-- upstream identity and rewriting it here would just hide the ingester bug that
-- produced it. Fixing that classifier is separate work.
UPDATE politicians
   SET constituency_name = 'Chicoutimi',
       party = COALESCE(NULLIF(party, ''), 'Parti québécois'),
       constituency_id = 'quebec-electoral-districts/chicoutimi',
       updated_at = now()
 WHERE qc_assnat_id = 20193
   AND province_territory = 'QC' AND level = 'provincial' AND is_active
   AND constituency_name IS NULL;

-- ── Post-conditions ─────────────────────────────────────────────────────────
DO $$
DECLARE today_n int; after_n int; dup_today int; dup_after int;
        orphans int; actives int; attached int;
BEGIN
    -- The generation in force TODAY: the complete 2017 map, 125 districts.
    SELECT count(*) INTO today_n FROM constituency_boundaries
     WHERE level='provincial' AND province_territory='QC'
       AND effective_from <= CURRENT_DATE
       AND (effective_to IS NULL OR effective_to >= CURRENT_DATE);
    IF today_n <> 125 THEN
        RAISE EXCEPTION 'Expected 125 QC districts in force today, found %', today_n;
    END IF;

    -- ★ The assertion this whole migration exists for. On 2026-08-29 exactly one
    -- generation must be selectable, and it must be the 2026 one. Before this
    -- migration ran, that same query returned 251.
    SELECT count(*) INTO after_n FROM constituency_boundaries
     WHERE level='provincial' AND province_territory='QC'
       AND effective_from <= DATE '2026-08-29'
       AND (effective_to IS NULL OR effective_to >= DATE '2026-08-29');
    IF after_n <> 127 THEN
        RAISE EXCEPTION
          'Expected 127 QC districts in force on 2026-08-29, found % — the two '
          'generations overlap and every Quebec address would return twice',
          after_n;
    END IF;

    SELECT count(*) INTO dup_today FROM (
        SELECT constituency_id FROM constituency_boundaries
         WHERE level='provincial' AND province_territory='QC'
           AND effective_from <= CURRENT_DATE
           AND (effective_to IS NULL OR effective_to >= CURRENT_DATE)
         GROUP BY 1 HAVING count(*) > 1) d;
    SELECT count(*) INTO dup_after FROM (
        SELECT constituency_id FROM constituency_boundaries
         WHERE level='provincial' AND province_territory='QC'
           AND effective_from <= DATE '2026-08-29'
           AND (effective_to IS NULL OR effective_to >= DATE '2026-08-29')
         GROUP BY 1 HAVING count(*) > 1) d;
    IF dup_today <> 0 OR dup_after <> 0 THEN
        RAISE EXCEPTION 'QC duplicate districts: % today, % on 2026-08-29',
          dup_today, dup_after;
    END IF;

    SELECT count(*) INTO orphans FROM politicians p
     WHERE p.constituency_id LIKE 'quebec-electoral-districts%'
       AND NOT EXISTS (SELECT 1 FROM constituency_boundaries b
                        WHERE b.constituency_id = p.constituency_id);
    IF orphans <> 0 THEN
        RAISE EXCEPTION 'QC cutover left % orphaned politician rows', orphans;
    END IF;

    SELECT count(*) INTO actives FROM politicians
     WHERE province_territory='QC' AND level='provincial' AND is_active;
    SELECT count(*) INTO attached FROM politicians
     WHERE province_territory='QC' AND level='provincial' AND is_active
       AND constituency_id IS NOT NULL;
    IF actives <> 125 OR attached <> 125 THEN
        RAISE EXCEPTION
          'Expected 125 active QC MNAs all attached, got % active / % attached',
          actives, attached;
    END IF;

    RAISE NOTICE 'QC: 125 districts in force today, 127 from 2026-08-29';
    -- ⓘ Not an error: 17 districts disappear in the 2026 map and their members'
    -- constituency_id will resolve to no CURRENT row from the 29th. During a writ
    -- there are no sitting MNAs at all, and the roster is rebuilt after the
    -- 2026-10-05 election, so this self-resolves.
END $$;

COMMIT;

SELECT refresh_map_views();
