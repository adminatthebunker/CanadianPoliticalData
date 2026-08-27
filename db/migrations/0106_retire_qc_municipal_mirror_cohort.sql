-- 0106 — retire the last 127 Open North councillors in Québec.
--
-- Completes the Québec municipal side of the Open North retirement. 0103 removed
-- the 221 duplicate rows the 2026-08-23 run CREATED; this removes the cohort
-- that predates it — the pre-2025-election roster the mirror had been serving
-- since April, still sitting alongside the MAMH rebuild.
--
-- ★ THE EVIDENCE IS PER-MUNICIPALITY, NOT AGGREGATE. For all 127 rows, MAMH
-- holds a roster for the same municipality, and in EVERY municipality it holds
-- at least as many members as the mirror does — Montréal 103 to 36, Québec 22
-- to 16, Lévis 16 to 15, Laval 23 to 12. There is no municipality where
-- retiring the mirror cohort could thin a council below what the authoritative
-- source already covers, and the migration asserts that rather than assuming it.
--
-- ⛔ SCOPE BY MUNICIPALITY, NEVER BY DISTRICT NAME. An earlier count of this
-- cohort matched on (level, province, constituency slug) and reported 286
-- instead of 203, because `District 1` exists in dozens of Québec
-- municipalities and the join was pairing councillors in different cities. Same
-- ambiguity 0089 fixed for boundaries, where Gatineau's Plateau councillor
-- landed on Québec City's Plateau 400 km away. The municipality is recovered
-- from `source_id`, which both sides carry:
--     opennorth:conseil-municipal-de-brossard:...   -> brossard
--     mamh-qc:brossard:...                          -> brossard
--
-- ⚠ Also clears the `displaced` finding. Claudio Benedetti (Brossard),
-- Dennis Dicks and Pierre Matuszewski (Senneville) and Claudia Abaunza
-- (Terrebonne) sat on polygons disjoint from every colleague's — all four are
-- mirror rows in municipalities where MAMH holds the real council. The check
-- was reporting a genuine defect; the fix is retiring the stale roster, not
-- re-attaching it.
--
-- ⛔ Deactivate, never delete: a deleted row cannot be audited, cannot be merged
-- by the duplicate-politician pass, and takes its speech attributions with it.
--
-- Forward-only. Apply with:
--   docker exec -i sw-db psql -U sw -d sovereignwatch -v ON_ERROR_STOP=1 \
--     < db/migrations/0106_retire_qc_municipal_mirror_cohort.sql

BEGIN;

CREATE TEMP TABLE _qc_mirror ON COMMIT DROP AS
SELECT p.id,
       regexp_replace(split_part(p.source_id, ':', 2),
                      '^conseil-(municipal|de-ville)-(de-|d-|du-|des-)?', '') AS muni
  FROM politicians p
 WHERE p.is_active
   AND p.level = 'municipal'
   AND p.province_territory = 'QC'
   AND p.source_id LIKE 'opennorth:%';

CREATE TEMP TABLE _mamh ON COMMIT DROP AS
SELECT split_part(source_id, ':', 2) AS muni, count(*) AS n
  FROM politicians
 WHERE is_active AND level = 'municipal' AND province_territory = 'QC'
   AND source_id LIKE 'mamh-qc:%'
 GROUP BY 1;

DO $$
DECLARE total int; uncovered int; thinner int;
BEGIN
    SELECT count(*) INTO total FROM _qc_mirror;
    IF total <> 127 THEN
        RAISE EXCEPTION 'Cohort is % rows, not the measured 127', total;
    END IF;

    -- ⛔ Refuse to retire anyone in a municipality MAMH does not cover — that
    -- would delete the only roster those residents have.
    SELECT count(*) INTO uncovered
      FROM _qc_mirror m LEFT JOIN _mamh a ON a.muni = m.muni
     WHERE a.muni IS NULL;
    IF uncovered <> 0 THEN
        RAISE EXCEPTION '% mirror councillors sit in municipalities with no '
          'MAMH roster — retiring them would leave those councils empty', uncovered;
    END IF;

    -- And refuse where the authoritative roster is SMALLER than the mirror's.
    SELECT count(*) INTO thinner FROM (
        SELECT m.muni FROM _qc_mirror m
         GROUP BY m.muni
        HAVING count(*) > (SELECT a.n FROM _mamh a WHERE a.muni = m.muni)) d;
    IF thinner <> 0 THEN
        RAISE EXCEPTION '% municipalities hold more mirror councillors than '
          'MAMH members — MAMH is not the fuller roster there', thinner;
    END IF;
END $$;

UPDATE politicians SET is_active = false, updated_at = now()
 WHERE id IN (SELECT id FROM _qc_mirror);

UPDATE politician_terms SET ended_at = now()
 WHERE ended_at IS NULL AND politician_id IN (SELECT id FROM _qc_mirror);

INSERT INTO politician_changes (politician_id, change_type, old_value, new_value, severity)
SELECT id, 'retired',
       jsonb_build_object('is_active', true),
       jsonb_build_object('is_active', false,
                          'via', '0106_retire_qc_municipal_mirror_cohort',
                          'cause', 'superseded by the MAMH 2025-11-02 roster'),
       'notable'
  FROM _qc_mirror;

DO $$
DECLARE left_over int; orphans int;
BEGIN
    SELECT count(*) INTO left_over FROM politicians
     WHERE is_active AND level = 'municipal' AND province_territory = 'QC'
       AND source_id LIKE 'opennorth:%';
    IF left_over <> 0 THEN
        RAISE EXCEPTION '% Québec mirror councillors still active', left_over;
    END IF;

    SELECT count(*) INTO orphans FROM politicians p
     WHERE p.is_active AND p.constituency_id IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM constituency_boundaries b
                        WHERE b.constituency_id = p.constituency_id);
    IF orphans <> 0 THEN
        RAISE EXCEPTION '% members point at a non-existent boundary', orphans;
    END IF;

    RAISE NOTICE '0106: 127 Québec mirror councillors retired; MAMH is now the '
                 'sole municipal roster in Québec';
END $$;

COMMIT;

SELECT refresh_map_views();
