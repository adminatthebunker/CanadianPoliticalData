-- 0067 — New Brunswick cutover: retire the Open North mirror, adopt Elections NB
--        via GeoNB. Includes a roster deduplication that MUST happen first.
--
-- NB is second by impact: **47% of the province has no provincial boundary
-- coverage at all** and 30 sitting MLAs are unreachable by postcode.
--
-- What we held
-- ------------
-- 22 rows, and they are the exact name intersection of the 2013-46 and 2023-42
-- generations carrying **2018 geometry under 2024 names**. Area error measured
-- against each candidate generation:
--
--   vs 2013-46 (superseded) :   1.32%   <- this is what we hold
--   vs 2023-42 (in force)   : 124.87%
--
-- Re-measured against the authoritative file immediately before this migration:
-- Moncton Northwest overlaps its real counterpart by **3.97%**, Moncton East by
-- 7.24%, Miramichi Bay-Neguac by 19.24%.
--
-- ⛔ All 49 load as a new generation; all 22 are retired. Deleted rather than
-- end-dated for the same reason as BC and SK — 2018 shapes under 2024 names was
-- never a real generation. The authoritative prior file is staged under
-- `data/boundaries/new-brunswick/prior/` if genuine history is wanted.
--
-- ★ The bilingual name split
-- --------------------------
-- NB publishes ONE field, `PED_Names_`, as "English / Français" (20 of 49 have a
-- distinct French form). The loader's new `name_split` handles it. Measured cost
-- of not splitting: slugs like `restigouche-west-restigouche-ouest`, giving
-- **9 of 22 matched and 13 orphaned**. Split: 22 matched, 27 new, 0 orphaned —
-- and 20 French names recovered into `name_fr`, which we previously discarded in
-- an officially bilingual province.
--
-- ⚠ ROSTER DEDUPLICATION — must precede the boundary cutover
-- -----------------------------------------------------------
-- NB carries **55 active provincial rows for 49 seats**: 49 clean `opennorth`
-- rows plus **6 duplicate `direct:legnb-ca:` rows**, five of which have
-- HTML-entity-encoded names (`Beno&#xEE;t Bourque`, `Ren&#xE9; Legacy`, …) and one
-- of which also has an entity-encoded *constituency name*
-- (`Edmundston-Vall&#xE9;e-des-Rivi&#xE8;res`). The sixth is `Robert McKee, K.C.`
-- against `Robert McKee`.
--
-- Every one was verified to have an `opennorth` twin in the same district.
--
-- ★ This is invisible TODAY only because the 27 districts they sit in return
-- nothing. The moment the boundaries are correct, six districts start returning
-- two MLAs each — and it would read as a regression caused by the boundary load.
-- Cleaning it here, in the same transaction, is what stops a correct change from
-- looking like a broken one.
--
-- Run AFTER `load-boundaries --jurisdiction new-brunswick`.
--
-- Forward-only. Apply with:
--   docker exec -i sw-db psql -U sw -d sovereignwatch -v ON_ERROR_STOP=1 \
--     < db/migrations/0067_new_brunswick_boundary_cutover.sql

BEGIN;

DO $$
DECLARE n int;
BEGIN
    SELECT count(*) INTO n FROM constituency_boundaries
     WHERE constituency_id LIKE 'new-brunswick-electoral-districts/%'
       AND boundaries_version = '2024';
    IF n <> 49 THEN
        RAISE EXCEPTION
          'Expected 49 authoritative NB rows, found %. Run '
          '`load-boundaries --jurisdiction new-brunswick` first.', n;
    END IF;
END $$;

-- ── 1. Deduplicate the roster, BEFORE any boundary reattachment ─────────────
-- Deactivated rather than deleted: they are real people with real source rows,
-- and `politician_changes` is the audit trail for mutations. Deactivating keeps
-- the history and removes them from every `is_active` lookup.
UPDATE politicians d
   SET is_active = false, updated_at = now()
 WHERE d.province_territory = 'NB'
   AND d.level = 'provincial'
   AND d.is_active
   AND d.source_id LIKE 'direct:legnb-ca%'
   AND EXISTS (
       SELECT 1 FROM politicians o
        WHERE o.province_territory = 'NB' AND o.level = 'provincial'
          AND o.is_active AND o.source_id LIKE 'opennorth%'
          AND o.id <> d.id
          -- Compare on the entity-stripped, punctuation-stripped district name,
          -- since one duplicate's constituency_name is itself entity-encoded.
          AND lower(regexp_replace(o.constituency_name, '[^a-zA-Z]', '', 'g'))
            = lower(regexp_replace(
                regexp_replace(d.constituency_name, '&#x[0-9A-Fa-f]+;', '', 'g'),
                '[^a-zA-Z]', '', 'g'))
   );

-- ── 2. Re-key and reattach ──────────────────────────────────────────────────
UPDATE politicians
   SET constituency_id = 'new-brunswick-electoral-districts/'
                       || split_part(constituency_id, '/', 2)
 WHERE constituency_id LIKE 'new-brunswick-electoral-districts-2018/%';

UPDATE politician_terms
   SET constituency_id = 'new-brunswick-electoral-districts/'
                       || split_part(constituency_id, '/', 2)
 WHERE constituency_id LIKE 'new-brunswick-electoral-districts-2018/%';

UPDATE politicians p
   SET constituency_id = b.constituency_id
  FROM constituency_boundaries b
 WHERE p.constituency_id IS NULL
   AND p.is_active AND p.level = 'provincial' AND p.province_territory = 'NB'
   AND b.level = 'provincial' AND b.province_territory = 'NB'
   AND b.boundaries_version = '2024'
   AND lower(p.constituency_name) = lower(b.name);

-- Any slug that no longer names a district (the 2018 generation retired some).
UPDATE politicians p SET constituency_id = NULL
 WHERE p.constituency_id LIKE 'new-brunswick-electoral-districts/%'
   AND NOT EXISTS (SELECT 1 FROM constituency_boundaries b
                    WHERE b.constituency_id = p.constituency_id);
UPDATE politician_terms t SET constituency_id = NULL
 WHERE t.constituency_id LIKE 'new-brunswick-electoral-districts/%'
   AND NOT EXISTS (SELECT 1 FROM constituency_boundaries b
                    WHERE b.constituency_id = t.constituency_id);

DELETE FROM constituency_boundaries
 WHERE constituency_id LIKE 'new-brunswick-electoral-districts-2018/%';

DO $$
DECLARE bnd int; orphans int; dupes int; attached int; actives int;
BEGIN
    SELECT count(*) INTO bnd FROM constituency_boundaries
     WHERE level='provincial' AND province_territory='NB'
       AND effective_from <= CURRENT_DATE
       AND (effective_to IS NULL OR effective_to >= CURRENT_DATE);
    IF bnd <> 49 THEN
        RAISE EXCEPTION 'Expected 49 current NB provincial boundaries, found %', bnd;
    END IF;

    -- ★ The dedup must have brought the roster to the seat count.
    SELECT count(*) INTO actives FROM politicians
     WHERE province_territory='NB' AND level='provincial' AND is_active;
    IF actives <> 49 THEN
        RAISE EXCEPTION
          'Expected 49 active NB provincial politicians after dedup, found % '
          '(49 seats). Duplicate roster rows would surface as districts with '
          'two MLAs.', actives;
    END IF;

    SELECT count(*) INTO orphans FROM politicians p
     WHERE p.constituency_id LIKE 'new-brunswick-electoral-districts%'
       AND NOT EXISTS (SELECT 1 FROM constituency_boundaries b
                        WHERE b.constituency_id = p.constituency_id);
    IF orphans <> 0 THEN
        RAISE EXCEPTION 'NB cutover left % orphaned politician rows', orphans;
    END IF;

    SELECT count(*) INTO dupes FROM (
        SELECT constituency_id FROM constituency_boundaries
         WHERE level='provincial' AND province_territory='NB'
           AND effective_from <= CURRENT_DATE
           AND (effective_to IS NULL OR effective_to >= CURRENT_DATE)
         GROUP BY 1 HAVING count(*) > 1) d;
    IF dupes <> 0 THEN
        RAISE EXCEPTION 'NB cutover left % duplicated districts', dupes;
    END IF;

    SELECT count(*) INTO attached FROM constituency_boundaries b
     WHERE b.level='provincial' AND b.province_territory='NB'
       AND EXISTS (SELECT 1 FROM politicians p
                    WHERE p.is_active AND p.constituency_id = b.constituency_id);
    RAISE NOTICE 'NB: % of 49 districts resolve to a sitting MLA', attached;
END $$;

COMMIT;

SELECT refresh_map_views();
