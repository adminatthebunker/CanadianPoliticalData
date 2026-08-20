-- 0084 — Remove the mirror generations the scheduled ingester put back, and
--        make it impossible for it to do so again.
--
-- ⛔ THE CUTOVERS WERE BEING SILENTLY UNDONE, ONE JURISDICTION PER CRON SLOT
-- ---------------------------------------------------------------------------
-- `opennorth._ingest_set` writes boundaries as a SIDE-EFFECT of roster ingest,
-- keyed on `set_def.boundary_set` — the old generation-suffixed names. Migrations
-- 0064-0080 deleted exactly those rows when each jurisdiction moved onto an
-- authoritative agency source. Nothing stopped the ingester writing them back.
--
-- The daily schedule then did precisely that, hours after the cutovers landed:
--
--     2026-08-19 21:35:27-50   quebec-electoral-districts-2017    124 rows
--     2026-08-19 21:40:36-45   manitoba-electoral-districts-2018   56 rows
--
-- Both provinces were returned to TWO live generations. Québec went to 249
-- current districts against 125 seats and Manitoba to 113 against 57, with both
-- areas exactly doubled — so every point-in-polygon in either province returned
-- two answers.
--
-- ★ `check-boundary-coverage` caught it the same evening, on its first run after
-- the municipal checks were added. That is the sentinel earning its place: the
-- damage was invisible in the API (the extra row is a *duplicate*, not an error)
-- and would otherwise have surfaced as intermittent double results.
--
-- ⚠ The remaining jurisdictions were not hit only because their roster ingests
-- had not yet come round in the schedule. This was a live, spreading regression,
-- not a one-off.
--
-- Two halves to the fix:
--   • CODE (already applied): `_ingest_set` now refuses to write a boundary
--     unless `set_def.level == 'municipal'`. Federal and provincial geometry is
--     owned by `boundary_loader.py`; municipal is still mirrored and is the only
--     level Open North may write.
--   • DATA (this migration): drop what it already put back.
--
-- ⓘ Discriminator: every resurrected row carries `boundaries_version='current'`,
-- the Open North artifact, while every authoritative row carries a real
-- generation label. That is ALMOST a rule — but `northwest-territories-
-- electoral-districts-2013` is legitimately 'current', because NWT was corrected
-- IN PLACE (0075) rather than re-keyed. So this uses an explicit allowlist of
-- authoritative source_sets rather than the version string, and will therefore
-- also catch any future resurrection under a name nobody has thought of.
--
-- Forward-only. Apply with:
--   docker exec -i sw-db psql -U sw -d sovereignwatch -v ON_ERROR_STOP=1 \
--     < db/migrations/0084_purge_resurrected_mirror_generations.sql

BEGIN;

CREATE TEMP TABLE _authoritative(source_set text PRIMARY KEY) ON COMMIT DROP;
INSERT INTO _authoritative VALUES
  ('federal-electoral-districts'),
  ('alberta-electoral-districts'),
  ('british-columbia-electoral-districts'),
  ('manitoba-electoral-districts'),
  ('new-brunswick-electoral-districts'),
  ('newfoundland-and-labrador-electoral-districts'),
  -- ⚠ NWT keeps its generation suffix on purpose: 0075 corrected its geometry in
  -- place rather than minting a new generation, so the original ids stayed.
  ('northwest-territories-electoral-districts-2013'),
  ('nova-scotia-electoral-districts'),
  ('nunavut-electoral-districts'),
  ('ontario-electoral-districts'),
  ('prince-edward-island-electoral-districts'),
  ('quebec-electoral-districts'),
  ('saskatchewan-electoral-districts'),
  ('yukon-electoral-districts');

-- ⛔ THE ROSTER WAS RE-POINTED TOO, and that is the half that would have hurt.
--
-- `_upsert_politician` sets `constituency_id` from `_constituency_id(rep,
-- set_def)`, which yields the OLD mirror id. So the scheduled ingest did not
-- merely add duplicate polygons — it moved **180 politicians** off their
-- authoritative boundary and back onto the resurrected one. Deleting the
-- boundaries without first moving those members forward would have orphaned
-- every one of them (the first attempt at this migration did exactly that and
-- was caught by the post-condition).
--
-- Re-point rather than detach: match each stale row to its authoritative
-- counterpart on (slug, province, level), which is exact because the cutovers
-- only ever stripped a generation suffix from the prefix.
CREATE TEMP TABLE _repoint ON COMMIT DROP AS
SELECT stale.constituency_id AS old_id, auth.constituency_id AS new_id
  FROM constituency_boundaries stale
  JOIN constituency_boundaries auth
    ON auth.level = stale.level
   AND auth.province_territory IS NOT DISTINCT FROM stale.province_territory
   AND split_part(auth.constituency_id, '/', 2)
     = split_part(stale.constituency_id, '/', 2)
   AND auth.source_set IN (SELECT source_set FROM _authoritative)
 WHERE stale.level IN ('federal', 'provincial')
   AND stale.source_set NOT IN (SELECT source_set FROM _authoritative);

DO $$
DECLARE ambiguous int;
BEGIN
    -- One stale id must map to exactly one authoritative id, or the re-point is
    -- a guess. (Québec has two live generations, so its slugs appear twice —
    -- deduplicated below rather than assumed away.)
    SELECT count(*) INTO ambiguous FROM (
        SELECT old_id FROM _repoint GROUP BY 1 HAVING count(DISTINCT new_id) > 1) d;
    IF ambiguous <> 0 THEN
        RAISE EXCEPTION
          '% stale boundary ids map to more than one authoritative id — '
          'the re-point would be a guess', ambiguous;
    END IF;
END $$;

UPDATE politicians p SET constituency_id = r.new_id, updated_at = now()
  FROM (SELECT DISTINCT old_id, new_id FROM _repoint) r
 WHERE p.constituency_id = r.old_id;

UPDATE politician_terms t SET constituency_id = r.new_id
  FROM (SELECT DISTINCT old_id, new_id FROM _repoint) r
 WHERE t.constituency_id = r.old_id;

DELETE FROM constituency_boundaries
 WHERE level IN ('federal', 'provincial')
   AND source_set NOT IN (SELECT source_set FROM _authoritative);

-- ── Undo the retirement the same ingest run performed ───────────────────────
-- ⛔ Jennifer Flett won The Pas-Kameesak on 2026-07-22, was added to the roster
-- at 18:50 by migration 0077 after the boundary work found the seat empty, and
-- was RETIRED at 21:40 the same evening by `detect_retirements` — because Open
-- North has never heard of her and that function treats the feed as ground
-- truth for who exists.
--
-- ★ The id was chosen deliberately to be the one Open North *will* mint, so the
-- next real ingest updates rather than duplicates. That reasoning was right for
-- the insert path and blind to the retirement path: the very same choice put a
-- hand-verified row inside the sweep. Both the code fix (a seat-count floor gate
-- in `compare_politicians.detect_retirements`) and this reactivation are needed
-- — the gate stops it recurring, this repairs what already happened.
--
-- ⚠ Claude Bourgeois (NS) and Brendan Curran (PE) carry the same shape of id and
-- were queued for the same fate behind Manitoba in the schedule. The floor gate
-- reaches them before their ingests come round.
UPDATE politicians SET is_active = true, updated_at = now()
 WHERE source_id = 'opennorth:manitoba-legislature:jennifer-flett'
   AND NOT is_active;

UPDATE politician_terms t SET ended_at = NULL
  FROM politicians p
 WHERE p.id = t.politician_id
   AND p.source_id = 'opennorth:manitoba-legislature:jennifer-flett'
   AND t.ended_at IS NOT NULL;

INSERT INTO politician_changes (politician_id, change_type, new_value, severity)
SELECT p.id, 'newly_elected',
       jsonb_build_object(
         'migration', '0084_purge_resurrected_mirror_generations',
         'reason', 'reversing an incorrect automated retirement: detect_retirements '
                   'retired a sitting member because the Open North feed omits her',
         'elected_at', '2026-07-22'),
       'warning'
  FROM politicians p
 WHERE p.source_id = 'opennorth:manitoba-legislature:jennifer-flett';

DO $$
DECLARE stray int; qc int; mb int; orphans int; attached_qc int; attached_mb int;
BEGIN
    SELECT count(*) INTO stray FROM constituency_boundaries
     WHERE level IN ('federal', 'provincial')
       AND source_set NOT IN (SELECT source_set FROM _authoritative);
    IF stray <> 0 THEN
        RAISE EXCEPTION '% non-authoritative federal/provincial rows remain', stray;
    END IF;

    SELECT count(*) INTO qc FROM constituency_boundaries
     WHERE level='provincial' AND province_territory='QC'
       AND effective_from <= CURRENT_DATE
       AND (effective_to IS NULL OR effective_to >= CURRENT_DATE);
    IF qc <> 125 THEN
        RAISE EXCEPTION 'Expected 125 current QC districts, found %', qc;
    END IF;

    SELECT count(*) INTO mb FROM constituency_boundaries
     WHERE level='provincial' AND province_territory='MB'
       AND effective_from <= CURRENT_DATE
       AND (effective_to IS NULL OR effective_to >= CURRENT_DATE);
    IF mb <> 57 THEN
        RAISE EXCEPTION 'Expected 57 current MB districts, found %', mb;
    END IF;

    -- The rosters must still be fully attached to the authoritative rows.
    SELECT count(*) INTO attached_qc FROM politicians
     WHERE province_territory='QC' AND level='provincial' AND is_active
       AND constituency_id IS NOT NULL;
    SELECT count(*) INTO attached_mb FROM politicians
     WHERE province_territory='MB' AND level='provincial' AND is_active
       AND constituency_id IS NOT NULL;
    IF attached_qc <> 125 OR attached_mb <> 57 THEN
        RAISE EXCEPTION
          'Roster detached by the purge: QC % of 125, MB % of 57',
          attached_qc, attached_mb;
    END IF;

    SELECT count(*) INTO orphans FROM politicians p
     WHERE p.is_active AND p.level IN ('federal','provincial')
       AND p.constituency_id IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM constituency_boundaries b
                        WHERE b.constituency_id = p.constituency_id);
    IF orphans <> 0 THEN
        RAISE EXCEPTION '% federal/provincial members left orphaned', orphans;
    END IF;

    RAISE NOTICE 'purged the resurrected mirror generations; QC 125 / MB 57, all attached';
END $$;

COMMIT;

SELECT refresh_map_views();
