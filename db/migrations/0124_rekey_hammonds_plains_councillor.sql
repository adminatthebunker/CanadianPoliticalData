-- 0124 — Re-key the one Halifax councillor whose district id changed in 0123.
--
-- 0123 replaced Halifax's mirror geometry with the city's own. Fifteen of the
-- sixteen district ids were byte-identical; one was not:
--
--   old  …/hammonds-plains-upper-hammonds-plains-lucasville-middle-and-upper-sackville
--   new  …/hammonds-plains-upper-hammonds-plains-lucasville-middle-upper-sackville
--
-- The publisher's name is "Hammonds Plains – Upper Hammonds Plains – Lucasville
-- - Middle & Upper Sackville". The mirror expanded `&` to `and`; our slugify
-- drops it. Same class as the `œ` divergence re-keyed in 0098 — a rendering
-- difference in one character, load-bearing because the slug IS the identity.
--
-- ⛔ WHY reattach-municipal-roster COULD NOT DO THIS. That job selects councils
-- holding a member with `constituency_id IS NULL`. A re-key does not null
-- anything — it leaves the member pointing at an id that no longer resolves to a
-- live row. So the member is orphaned, not detached, and the daily job does not
-- see them at all. `check-boundary-coverage` DID catch it, as a
-- `municipal/orphaned` BREACH, which is the only reason this is not silent.
-- Worth remembering for every future cutover that changes a slug.
--
-- One row. Matched on the exact old id, not on a name, and asserted both ways.
--
-- Forward-only. Apply with:
--   docker exec -i sw-db psql -U sw -d sovereignwatch -v ON_ERROR_STOP=1 \
--     < db/migrations/0124_rekey_hammonds_plains_councillor.sql

BEGIN;

DO $$
DECLARE n_target int;
BEGIN
    -- Refuse if the destination is not a single live district.
    SELECT count(*) INTO n_target FROM constituency_boundaries
     WHERE constituency_id = 'halifax-districts/hammonds-plains-upper-hammonds-plains-lucasville-middle-upper-sackville'
       AND boundary_kind = 'district'
       AND effective_from <= CURRENT_DATE
       AND (effective_to IS NULL OR effective_to >= CURRENT_DATE);
    IF n_target <> 1 THEN
        RAISE EXCEPTION 'destination district is not uniquely live (found %)', n_target;
    END IF;
END $$;

UPDATE politicians
   SET constituency_id = 'halifax-districts/hammonds-plains-upper-hammonds-plains-lucasville-middle-upper-sackville',
       updated_at = now()
 WHERE is_active
   AND constituency_id = 'halifax-districts/hammonds-plains-upper-hammonds-plains-lucasville-middle-and-upper-sackville';

UPDATE politician_terms
   SET constituency_id = 'halifax-districts/hammonds-plains-upper-hammonds-plains-lucasville-middle-upper-sackville'
 WHERE ended_at IS NULL
   AND constituency_id = 'halifax-districts/hammonds-plains-upper-hammonds-plains-lucasville-middle-and-upper-sackville';

DO $$
DECLARE n_orphan int; n_stale int;
BEGIN
    SELECT count(*) INTO n_stale FROM politicians
     WHERE is_active AND constituency_id LIKE '%middle-and-upper-sackville';
    IF n_stale <> 0 THEN
        RAISE EXCEPTION '% active member(s) still on the old id', n_stale;
    END IF;

    -- Corpus-wide: no sitting member may point at a non-live boundary.
    SELECT count(*) INTO n_orphan FROM politicians p
     WHERE p.is_active AND p.constituency_id IS NOT NULL
       AND NOT EXISTS (
         SELECT 1 FROM constituency_boundaries b
          WHERE b.constituency_id = p.constituency_id
            AND b.effective_from <= CURRENT_DATE
            AND (b.effective_to IS NULL OR b.effective_to >= CURRENT_DATE));
    IF n_orphan <> 0 THEN
        RAISE EXCEPTION '% sitting member(s) still orphaned corpus-wide', n_orphan;
    END IF;

    RAISE NOTICE '0124 ok: Hammonds Plains councillor re-keyed; 0 orphans corpus-wide';
END $$;

COMMIT;
