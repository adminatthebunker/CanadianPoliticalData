-- 0101 — purge the 2026-08-23 Open North mirror resurrection.
--
-- ⛔ WHAT HAPPENED. On 2026-08-23 at 02:00 UTC a single Open North ingestion run
-- re-created 1,155 boundary rows and reverted roughly twelve applied cutover
-- migrations in one pass. Every jurisdiction was left with BOTH generations
-- live: a downtown Toronto point returned 7 boundaries instead of 4, federal
-- reported 685 districts against 343 seats, and total area came to ~200% of the
-- recorded baseline in every province. The run also re-pointed ~940 sitting
-- members onto mirror constituency_ids and resurrected cohorts that
-- authoritative ingesters had already retired.
--
-- ★ HOW IT GOT IN, since the guard was not the failure. `_ingest_set` has
-- refused to run without OPENNORTH_ALLOW_INGEST=1 since 2026-08-20 (f63b6d9).
-- But `scripts/scanner-cron.sh` ran the ingest on a Sunday-02:00-UTC timer from
-- inside `sw-scanner-cron` — the ONLY scanner-family service without a
-- `./services/scanner/src:/app/src` bind mount. It therefore executed source
-- baked into an image built 2026-06-02, three months before the guard existed,
-- and `restart: unless-stopped` carried that image across every rebuild of
-- everything else. It also never wrote a `scanner_jobs` row and never read
-- `scanner_schedules`, so migration 0087's disabling of the twelve Open North
-- schedules did not touch it and the run left no audit trail. Both defects were
-- fixed on 2026-08-27: the block is gone from the script and the mount is added.
--
-- ═══ THE DELETE SET, AND WHY IT IS SAFE ═══════════════════════════════════
--
-- ⚠ Do NOT key this on a constituency_id join. Mirror and authoritative rows use
-- different id PREFIXES — the mirror bakes the generation into the set name,
-- which is exactly the anti-pattern the re-key fixed:
--     current                    federal-electoral-districts-2023-representation-order/10001
--     2023-representation-order  federal-electoral-districts/10001
-- An id-matching DELETE removes 0 of 342 federal rows while appearing to
-- succeed. That is the same false premise that made 0093's assertions pass
-- vacuously: its DELETE and its checks were keyed on the same wrong assumption,
-- so nothing could detect that it had done nothing.
--
-- ⚠ Nor on the signature alone. `boundaries_version='current' AND
-- effective_from='2023-01-01'` also matches ~782 legitimately un-replaced
-- municipal rows — the ~44 Ontario sets, BC, PE, NL, SK — which are the ONLY
-- data that exists for those places. Deleting them is data loss, not cleanup.
--
-- ★ THREE CONDITIONS, AND AN INDEPENDENT WITNESS. The rule is: the mirror
-- signature, AND `boundary_kind IS NULL`, AND (non-municipal, or an
-- authoritative sibling already exists in the same source_set).
--
--   `boundary_kind IS NULL` is the load-bearing clause. The mirror never writes
--   a tier — that is why 257 sitting officials sit untiered and why `wrong-tier`
--   could not see them. Every deliberately-kept row HAS one: the ten
--   `census-subdivisions/*` mayoral polygons 0093 preserved inside ward sets,
--   Montréal's 18 boroughs, Québec's 5 boroughs, and Sainte-Anne-de-Bellevue's
--   5 held districts. Without this clause the rule takes all 38 of them.
--
--   The witness: the rule selects 1,155 rows and ALL 1,155 fall inside the
--   2026-08-23 02:00 UTC burst, with zero rows predating it. The structural
--   rule is the semantics; the created_at window is independent proof it did not
--   over-reach. Neither alone would be enough, which is the whole safety
--   argument — assert both.
--
-- ═══ ORDER MATTERS ════════════════════════════════════════════════════════
-- Re-point the roster BEFORE deleting. 0084 records deleting first and
-- orphaning everyone. ~940 members currently point at mirror ids; the tail of
-- the id survives the prefix change (`…/10001` on both sides), so a tail match
-- carries them across. Yukon's four abolished 2015 districts have no successor
-- and are detached to NULL, correctly — their holders are the pre-election
-- cohort the same run resurrected, retired separately in 0102.
--
-- Forward-only. Apply with:
--   docker exec -i sw-db psql -U sw -d sovereignwatch -v ON_ERROR_STOP=1 \
--     < db/migrations/0101_purge_mirror_resurrection_20260823.sql

BEGIN;

-- ── 1. The delete set ────────────────────────────────────────────────────
CREATE TEMP TABLE _victim ON COMMIT DROP AS
SELECT b.id, b.constituency_id, b.level, b.province_territory, b.source_set,
       b.created_at, split_part(b.constituency_id, '/', 2) AS tail
  FROM constituency_boundaries b
 WHERE b.boundaries_version = 'current'
   AND b.effective_from = DATE '2023-01-01'
   AND b.boundary_kind IS NULL
   AND (b.level <> 'municipal'
        OR EXISTS (SELECT 1 FROM constituency_boundaries n
                    WHERE n.source_set = b.source_set
                      AND n.boundaries_version <> 'current'));

CREATE INDEX ON _victim (constituency_id);

DO $$
DECLARE n int; f int; p int; m int; outside int;
BEGIN
    SELECT count(*), count(*) FILTER (WHERE level='federal'),
           count(*) FILTER (WHERE level='provincial'),
           count(*) FILTER (WHERE level='municipal')
      INTO n, f, p, m FROM _victim;
    IF (n, f, p, m) <> (1155, 342, 646, 167) THEN
        RAISE EXCEPTION 'Delete set is % (fed % / prov % / muni %), not the '
          'measured 1155 (342/646/167). The incident is not what was measured '
          '— stop and re-measure before deleting anything.', n, f, p, m;
    END IF;

    -- ⛔ The independent witness. If the structural rule reaches a row the
    -- incident did not create, it is reaching into live data.
    SELECT count(*) INTO outside FROM _victim
     WHERE created_at <  TIMESTAMPTZ '2026-08-23 00:00Z'
        OR created_at >= TIMESTAMPTZ '2026-08-24 00:00Z';
    IF outside <> 0 THEN
        RAISE EXCEPTION '% rows in the delete set fall outside the 2026-08-23 '
          'burst — the rule is over-reaching into still-live mirror data', outside;
    END IF;
END $$;

-- ── 2. Re-point the roster onto authoritative ids ────────────────────────
-- ⚠ Federal joins on the tail ALONE: authoritative federal rows carry a
-- province_territory, the mirror's carry NULL, so including province in the
-- key maps 0 of 342. Provincial must keep it — district tails repeat across
-- provinces.
CREATE TEMP TABLE _remap ON COMMIT DROP AS
SELECT DISTINCT v.constituency_id AS old_id, a.constituency_id AS new_id
  FROM _victim v
  JOIN constituency_boundaries a
    ON split_part(a.constituency_id, '/', 2) = v.tail
   AND a.level = v.level
   AND (v.level = 'federal'
        OR a.province_territory IS NOT DISTINCT FROM v.province_territory)
   AND NOT (a.boundaries_version = 'current'
            AND a.effective_from = DATE '2023-01-01'
            AND a.boundary_kind IS NULL)
   AND a.effective_from <= CURRENT_DATE
   AND (a.effective_to IS NULL OR a.effective_to >= CURRENT_DATE)
 WHERE v.level <> 'municipal';

DO $$
DECLARE ambiguous int; mapped int;
BEGIN
    -- ⛔ 0084's ambiguity gate: one stale id must map to exactly one
    -- authoritative id, or the re-point is a guess.
    SELECT count(*) INTO ambiguous FROM (
        SELECT old_id FROM _remap GROUP BY 1 HAVING count(*) > 1) d;
    IF ambiguous <> 0 THEN
        RAISE EXCEPTION '% stale ids map to more than one authoritative id — '
          'refusing to guess', ambiguous;
    END IF;
    SELECT count(*) INTO mapped FROM _remap;
    RAISE NOTICE 'remap: % federal/provincial ids carried across', mapped;
END $$;

UPDATE politicians p SET constituency_id = r.new_id, updated_at = now()
  FROM _remap r WHERE p.constituency_id = r.old_id;

UPDATE politician_terms t SET constituency_id = r.new_id
  FROM _remap r WHERE t.constituency_id = r.old_id;

-- ⚠ Anything still pointing into the delete set has no successor (Yukon's four
-- districts abolished in the 2025 redistribution). NULL, never a wrong-but-
-- populated value: 0089 records that a populated wrong id hides the row from
-- every NULL-only re-attach pass afterwards.
UPDATE politicians SET constituency_id = NULL, updated_at = now()
 WHERE constituency_id IN (SELECT constituency_id FROM _victim);
UPDATE politician_terms SET constituency_id = NULL
 WHERE constituency_id IN (SELECT constituency_id FROM _victim);

-- ── 3. Delete ────────────────────────────────────────────────────────────
DELETE FROM constituency_boundaries b USING _victim v WHERE b.id = v.id;

-- ── 4. Re-apply 0090 — the ST_MakeValid repair the run overwrote ─────────
-- Condition-driven, so it covers both re-inserted invalid rows and rows the
-- mirror clobbered in place. Keyed on the primary key, not constituency_id,
-- which is only unique together with boundaries_version.
UPDATE constituency_boundaries b
   SET boundary = v.g,
       boundary_simple = ST_Multi(ST_CollectionExtract(ST_MakeValid(
                           ST_Simplify(v.g, 0.005)), 3)),
       centroid  = ST_Centroid(v.g),
       area_sqkm = ST_Area(v.g::geography) / 1000000,
       updated_at = now()
  FROM (SELECT id, ST_Multi(ST_CollectionExtract(ST_MakeValid(boundary), 3)) AS g
          FROM constituency_boundaries WHERE NOT ST_IsValid(boundary)) v
 WHERE b.id = v.id;

-- ── 5. Postconditions ────────────────────────────────────────────────────
-- ★ Asserted against BASELINES in boundary_coverage.py:63-79, snapshotted
-- 2026-08-19 — deliberately NOT against the signature the DELETE just used.
-- 0093's checks were keyed on the same premise as its DELETE, so they could not
-- witness its failure. An assertion must be able to disagree with the thing it
-- is checking.
DO $$
DECLARE r record; expected int; got int; bad int;
BEGIN
    FOR r IN SELECT * FROM (VALUES
        ('federal','CA',343),('provincial','AB',87),('provincial','BC',93),
        ('provincial','MB',57),('provincial','NB',49),('provincial','NL',40),
        ('provincial','NS',56),('provincial','NT',19),('provincial','NU',22),
        ('provincial','ON',124),('provincial','PE',27),('provincial','QC',125),
        ('provincial','SK',61),('provincial','YT',21)
      ) AS t(lvl, ju, n)
    LOOP
        SELECT count(*) INTO got FROM constituency_boundaries
         WHERE level = r.lvl
           AND (r.lvl = 'federal' OR province_territory = r.ju)
           AND effective_from <= CURRENT_DATE
           AND (effective_to IS NULL OR effective_to >= CURRENT_DATE);
        IF got <> r.n THEN
            RAISE EXCEPTION '%/%: % live districts, baseline says %',
                            r.lvl, r.ju, got, r.n;
        END IF;
    END LOOP;

    SELECT count(*) INTO bad FROM constituency_boundaries WHERE NOT ST_IsValid(boundary);
    IF bad <> 0 THEN RAISE EXCEPTION 'ST_MakeValid left % invalid geometries', bad; END IF;

    SELECT count(*) INTO bad FROM constituency_boundaries
     WHERE ST_IsEmpty(boundary) OR area_sqkm IS NULL OR area_sqkm <= 0;
    IF bad <> 0 THEN RAISE EXCEPTION '% districts emptied by the repair', bad; END IF;

    -- Orphans at EVERY level. 0084 checked only federal/provincial; the 167
    -- municipal rows make the municipal clause load-bearing this time.
    SELECT count(*) INTO bad FROM politicians p
     WHERE p.is_active AND p.constituency_id IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM constituency_boundaries b
                        WHERE b.constituency_id = p.constituency_id);
    IF bad <> 0 THEN
        RAISE EXCEPTION '% sitting members point at a non-existent boundary', bad;
    END IF;

    -- ⛔ 0094 and 0091 survived the incident — verify, do not re-apply.
    IF NOT EXISTS (SELECT 1 FROM constituency_boundaries
                    WHERE constituency_id = 'winnipeg-wards/elmwood-east-kildonan') THEN
        RAISE EXCEPTION '0094 lost: Elmwood – East Kildonan is gone';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_indexes
                    WHERE indexname = 'idx_boundaries_authority_key') THEN
        RAISE EXCEPTION '0091 lost: idx_boundaries_authority_key is gone';
    END IF;

    -- 0098's own postcondition: the mangled ligature id must not be back.
    SELECT count(*) INTO bad FROM constituency_boundaries
     WHERE constituency_id LIKE '%-s-urs';
    IF bad <> 0 THEN RAISE EXCEPTION '0098 reverted: % mangled ligature ids', bad; END IF;

    RAISE NOTICE 'mirror resurrection purged: 1155 rows, baselines restored';
END $$;

COMMIT;

SELECT refresh_map_views();
