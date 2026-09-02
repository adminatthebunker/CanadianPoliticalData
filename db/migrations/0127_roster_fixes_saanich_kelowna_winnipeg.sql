-- 0127 — Three roster defects, each verified against the publisher, not inferred.
--
-- Found by a source-discovery pass over BC/MB/PE municipal rosters (CLAUDE.md
-- rule #5 waived by the operator for that probe). Every fact below was
-- re-verified directly against localelections.ca and data.winnipeg.ca before
-- this migration was written; none of it rests on the probe's summary alone.
--
-- ── 1. SAANICH WAS MISSING EIGHT OF ITS NINE COUNCIL MEMBERS ────────────────
-- We held exactly ONE Saanich row — Mayor Dean Murdock — against 7 to 18 for
-- every other BC council we carry. The eight councillors elected 2022-10-15
-- were simply absent, so a "who represents me" lookup anywhere in Saanich
-- (pop. ~118,000) returned the mayor and nobody else.
--
-- Source: CivicInfo BC's localelections.ca province-wide report builder,
--   /report/index.php?mayors=on&councillors=on&rtype=results&year=2022
-- CivicInfo BC is the not-for-profit that runs BC's local-election database,
-- board-governed by BC local governments, with data entered by the municipal
-- Chief Election Officers themselves. The endpoint pre-filters to winners
-- (1,025 rows, every one Elected=YES). Vote counts recorded below as evidence.
--
-- ⓘ FETCH POSTURE, recorded because it was an operator decision. localelections.ca
-- robots.txt is `User-agent: * / Crawl-delay: 5` with Disallow only on /config/,
-- /wp-admin/, /wordpress/, /blog/ — nothing on /report/. ⚠ Its parent domain
-- civicinfo.bc.ca carries a much more restrictive file (`Content-Signal:
-- ai-train=no`, `User-agent: ClaudeBot / Disallow: /`). Same organisation. The
-- operator's decision was to fetch localelections.ca ONLY, honouring its
-- crawl-delay with a descriptive CPD user-agent, and never civicinfo.bc.ca.
--
-- ⛔ SOURCE PREFIX IS `civicinfo-bc:`, NOT `opennorth:`. Same reasoning as the
-- mamh-qc: and amo-on: decisions — `compare_politicians.detect_retirements`
-- sweeps the opennorth cohort, and rows that never came from the mirror must not
-- be sweepable by it.
--
-- ── 2. KELOWNA: OUR OWN TYPO ────────────────────────────────────────────────
-- We held "Gord Lordgrove". The councillor is "Gord Lovegrove", confirmed twice
-- against the publisher — the 2022 results and the 2026 candidate list. Ours is
-- the error; nothing upstream changed.
--
-- ── 3. WINNIPEG: A COUNCILLOR WITH NO TERM ──────────────────────────────────
-- Emma Durand-Wood (Elmwood — East Kildonan) has a correct `politicians` row and
-- a correct `constituency_id`, and ZERO `politician_terms` rows — so MB returned
-- 15 terms for 16 sitting members and she is invisible to anything that joins
-- through terms.
--
-- ⚠ started_at IS A REAL DATE HERE, AND ITS SIBLINGS' ARE NOT. Every existing
-- municipal term row from the mirror carries `started_at = 2026-04-14 03:11…`,
-- which is the INGEST timestamp, not a term start. Rather than copy a
-- meaningless value for consistency, this uses the actual election that seated
-- each member — Winnipeg 2022-10-26 and Saanich 2022-10-15. Verified from
-- data.winnipeg.ca's own Council Data (r4tk-7dip): Durand-Wood is
-- `year=2022, current_council=true, ward_id=14`. The inconsistency with the
-- mirror rows is deliberate and is an argument for backfilling THEM, not for
-- degrading these.
--
-- Forward-only. Apply with:
--   docker exec -i sw-db psql -U sw -d sovereignwatch -v ON_ERROR_STOP=1 \
--     < db/migrations/0127_roster_fixes_saanich_kelowna_winnipeg.sql

BEGIN;

-- ── 1. Saanich's eight councillors ──────────────────────────────────────────
WITH incoming(first_name, last_name, slug, votes) AS (
    VALUES
      ('Colin', 'Plant',            'colin-plant',            16324),
      ('Susan', 'Brice',            'susan-brice',            15355),
      ('Nathalie', 'Chambers',      'nathalie-chambers',      10633),
      ('Teale', 'Phelps Bondaroff', 'teale-phelps-bondaroff',  9218),
      ('Karen', 'Harper',           'karen-harper',           10436),
      ('Zac', 'de Vries',           'zac-de-vries',           14274),
      ('Judy', 'Brownoff',          'judy-brownoff',          11845),
      ('Mena', 'Westhaver',         'mena-westhaver',         11459)
), ins AS (
INSERT INTO politicians (
    name, first_name, last_name, level, province_territory,
    constituency_id, constituency_name, elected_office, source_id, is_active, extras)
SELECT i.first_name || ' ' || i.last_name, i.first_name, i.last_name,
       'municipal', 'BC',
       'census-subdivisions/5917021', 'Saanich', 'Councillor',
       'civicinfo-bc:saanich-district-council:' || i.slug, true,
       jsonb_build_object('civicinfo_bc', jsonb_build_object(
            'elected_year', 2022, 'votes', i.votes,
            'source', 'localelections.ca /report/index.php rtype=results year=2022'))
  FROM incoming i
 WHERE NOT EXISTS (
        SELECT 1 FROM politicians p
         WHERE p.is_active AND p.level = 'municipal' AND p.province_territory = 'BC'
           AND lower(p.name) = lower(i.first_name || ' ' || i.last_name))
RETURNING id, elected_office, constituency_id
)
INSERT INTO politician_terms (politician_id, office, level, province_territory,
                              constituency_id, started_at, source)
SELECT id, elected_office, 'municipal', 'BC', constituency_id,
       -- BC general local elections: third Saturday of October.
       TIMESTAMPTZ '2022-10-15 00:00:00+00',
       'civicinfo-bc:saanich-district-council'
  FROM ins;

-- ── 2. Kelowna typo ─────────────────────────────────────────────────────────
UPDATE politicians
   SET name = 'Gord Lovegrove', last_name = 'Lovegrove', updated_at = now()
 WHERE name = 'Gord Lordgrove';

-- ── 3. Durand-Wood's missing term ───────────────────────────────────────────
INSERT INTO politician_terms (politician_id, office, level, province_territory,
                              constituency_id, started_at, source)
SELECT p.id, 'Councillor', 'municipal', 'MB', p.constituency_id,
       -- Winnipeg 2022 general municipal election: fourth Wednesday of October.
       TIMESTAMPTZ '2022-10-26 00:00:00+00',
       'city-of-winnipeg:winnipeg-city-council'
  FROM politicians p
 WHERE p.name = 'Emma Durand-Wood' AND p.is_active
   AND NOT EXISTS (SELECT 1 FROM politician_terms t WHERE t.politician_id = p.id);

-- ── Assertions ──────────────────────────────────────────────────────────────
DO $$
DECLARE n int;
BEGIN
    SELECT count(*) INTO n FROM politicians
     WHERE is_active AND constituency_id = 'census-subdivisions/5917021';
    IF n <> 9 THEN
        RAISE EXCEPTION 'Saanich should now hold 9 members (1 mayor + 8 councillors), found %', n;
    END IF;

    SELECT count(*) INTO n FROM politicians
     WHERE is_active AND constituency_id = 'census-subdivisions/5917021'
       AND (SELECT count(*) FROM politician_terms t
             WHERE t.politician_id = politicians.id AND t.ended_at IS NULL) = 0;
    IF n <> 0 THEN
        RAISE EXCEPTION '% Saanich member(s) have no open term row', n;
    END IF;

    IF EXISTS (SELECT 1 FROM politicians WHERE name = 'Gord Lordgrove') THEN
        RAISE EXCEPTION 'the Kelowna typo is still present';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM politicians WHERE name = 'Gord Lovegrove' AND is_active) THEN
        RAISE EXCEPTION 'Gord Lovegrove is missing after the rename';
    END IF;

    SELECT count(*) INTO n FROM politician_terms t
      JOIN politicians p ON p.id = t.politician_id
     WHERE p.province_territory = 'MB' AND p.level = 'municipal'
       AND p.is_active AND t.ended_at IS NULL;
    IF n <> 16 THEN
        RAISE EXCEPTION 'MB should have 16 open municipal terms, found %', n;
    END IF;

    -- Nothing may have been orphaned or detached by this change.
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

    RAISE NOTICE '0127 ok: Saanich 1 -> 9 members, Kelowna typo fixed, MB terms 15 -> 16';
END $$;

COMMIT;
