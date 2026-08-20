-- 0091 — Scope the authority-key uniqueness index to `source_set`.
--
-- ⛔ THE UPSTREAM DEFECT THAT FORCED THIS
-- --------------------------------------
-- Nova Scotia's province-wide municipal polling-district file assigns the code
-- `BWAL` to TWO different municipalities:
--
--   Town of Bridgewater   poll_dist BWAL   mu_code BW   co_code LU
--   Town of Berwick       poll_dist BWAL   mu_code BW   co_code KI
--
-- Both also share `mu_code = BW`. Only `co_code` and the regulation number tell
-- them apart. That is the province's error, not ours — but it is real, it is in
-- the authoritative file, and it is not going to be fixed on our schedule.
--
-- ⓘ WHY THE INDEX WAS RIGHT AND IS NOW TOO NARROW
-- -----------------------------------------------
-- `idx_boundaries_authority_key` (0061) enforces that one agency does not issue
-- the same district id twice within a generation, and it has earned its keep:
-- NB's DIST_ID points at a different district in 27 of 49 cases across
-- generations, which is exactly what `boundaries_version` in the key catches.
--
-- That invariant was written when one spec meant one agency publishing one
-- jurisdiction, where `source_set` is constant and adding it changes nothing.
-- It does not survive an AGGREGATOR: when a province publishes all 49 of its
-- municipalities in one file, the agency's district id is only ever unique
-- *within the municipality that owns it*. Bridgewater's `BWAL` and Berwick's
-- `BWAL` are not a collision — they are two councils, each with one at-large
-- district, and the province happens to have reused a code.
--
-- So the key gains `source_set`. Every existing row keeps its guarantee (their
-- source_set is constant per authority), and aggregators become expressible
-- without mangling the stored id.
--
-- ⚠ The alternative — qualifying `authority_district_id` with the set slug —
-- was rejected: it would store `berwick-town-districts:BWAL` instead of the
-- code the agency actually published, destroying the one thing the column is
-- for. A constraint that is too narrow should be widened, not worked around by
-- corrupting the data it constrains.
--
-- ⚠ The duplicate is NOT thereby hidden. `boundary_loader` reports any authority
-- id appearing in more than one set of an aggregator as a run `problem`, so the
-- upstream defect stays visible without being fatal.
--
-- Forward-only. Apply with:
--   docker exec -i sw-db psql -U sw -d sovereignwatch -v ON_ERROR_STOP=1 \
--     < db/migrations/0091_authority_key_scoped_to_source_set.sql

BEGIN;

DROP INDEX IF EXISTS idx_boundaries_authority_key;

CREATE UNIQUE INDEX idx_boundaries_authority_key
    ON constituency_boundaries
       (authority, source_set, authority_district_id, boundaries_version)
    WHERE authority IS NOT NULL AND authority_district_id IS NOT NULL;

COMMENT ON COLUMN constituency_boundaries.authority_district_id IS
    'The agency''s own district identifier (Elections Canada FED_NUM, Elections '
    'Ontario ED_ID, StatCan CSD code, NS poll_dist, ...). Unique within '
    '(authority, source_set, boundaries_version). Generation-scoped because '
    'NB''s DIST_ID points at a different district in 27 of 49 cases across '
    'generations; set-scoped because an aggregator file publishes many '
    'municipalities at once and NS reuses `BWAL` for both Bridgewater and '
    'Berwick.';

DO $$
DECLARE n int;
BEGIN
    -- The narrower guarantee must still hold everywhere it held before, i.e.
    -- for every authority that publishes exactly one source_set.
    SELECT count(*) INTO n FROM (
        SELECT authority, authority_district_id, boundaries_version
          FROM constituency_boundaries
         WHERE authority IS NOT NULL AND authority_district_id IS NOT NULL
           AND authority IN (SELECT authority FROM constituency_boundaries
                              WHERE authority IS NOT NULL
                              GROUP BY authority HAVING count(DISTINCT source_set) = 1)
         GROUP BY 1, 2, 3 HAVING count(*) > 1) d;
    IF n <> 0 THEN
        RAISE EXCEPTION
          'Widening the key exposed % duplicate authority ids among '
          'single-set authorities — those were real collisions', n;
    END IF;
END $$;

COMMIT;
