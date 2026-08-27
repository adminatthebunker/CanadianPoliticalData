-- 0105 — refuse Open North mirror boundary writes at the database.
--
-- ⛔ WHY THIS IS NOT A PYTHON GUARD. `_ingest_set` has refused to run without
-- OPENNORTH_ALLOW_INGEST=1 since 2026-08-20. It was present, correct, and
-- irrelevant on 2026-08-23, because the process that mattered — `sw-scanner-cron`
-- — was the only scanner-family container without a source bind mount and was
-- executing an image built 2026-06-02, three months before the guard existed.
-- `restart: unless-stopped` had carried that image through every rebuild of
-- everything else.
--
-- ★ Three defences had already failed by three different routes: the schedules
-- disabled in 0087 (the container never read `scanner_schedules`), the Python
-- guard (wrong copy of the file), and the loader's own conventions (the mirror
-- writes through a different code path entirely). Every one of them lived
-- somewhere a process could be configured not to look. The database is the one
-- place every writer converges, so that is where the last defence belongs.
--
-- ═══ WHAT IS BLOCKED ═════════════════════════════════════════════════════
--
-- The conjunction `boundaries_version = 'current' AND effective_from =
-- '2023-01-01'`. That pair has exactly one producer in the codebase —
-- `opennorth.py`'s `_upsert_boundary`, which hardcodes both literals — and no
-- authoritative loader emits it.
--
-- ⚠ The version alone would be wrong. Northwest Territories legitimately carries
-- `boundaries_version='current'` (0075 corrected it in place rather than
-- re-keying), but its `effective_from` is 2015-10-25. The conjunction has one
-- producer; either half alone has two.
--
-- ═══ WHAT STILL PASSES, DELIBERATELY ═════════════════════════════════════
--
-- • Every `boundary_loader.py` write — real generation labels, real in-force
--   dates. Stage E's remaining ~44 Ontario cutovers are unaffected.
-- • ⛔ THE ~780 MUNICIPAL MIRROR ROWS THAT ARE STILL THE ONLY DATA WE HAVE.
--   The ~44 Ontario sets, BC, PE, NL, SK all carry this signature legitimately.
--   An UPDATE of a row that ALREADY matches is allowed, so 0090-style
--   ST_MakeValid repairs and `effective_to` retirements keep working. Only
--   CREATING the signature is refused. Without this carve-out the migration
--   would block Stage E rather than protect it.
-- • Every DELETE — there is no delete trigger. Cutover migrations need no
--   override.
--
-- ═══ WHAT THIS DOES NOT CATCH, STATED PLAINLY ════════════════════════════
--
-- ⚠ The 2026-08-23 run ALSO silently overwrote Northwest Territories' geometry
-- in place. Because NT shares `boundaries_version='current'` with the mirror,
-- the mirror's `ON CONFLICT DO UPDATE` replaced 19 polygons while leaving
-- `authority='elections-nwt'`, `effective_from=2015-10-25` and `boundary_kind`
-- untouched — a corrupt row wearing an authoritative row's identity, carrying
-- NO signature to test. NT's total area went from 1,609,305 km² to 2,192,291,
-- and Hay River South overlapped its true polygon by 26%.
--
-- ★ No column-level rule can catch that, because on an UPDATE the mirror and
-- the loader leave the identifying columns identical. What caught it was
-- `check-boundary-coverage`'s AREA BASELINE, which is why that check must stay
-- and why the sentinel moved from weekly to daily. Distinguishing writers would
-- need the loader to declare itself in a session GUC; that is a real option if
-- another in-place overwrite ever appears, and is deliberately not built now —
-- the writer is being removed outright, and an unused mechanism rots.
--
-- ═══ OVERRIDE ════════════════════════════════════════════════════════════
--   BEGIN; SET LOCAL cpd.allow_mirror_writes = 'on'; ... COMMIT;
-- Needed by a pre-cutover `pg_restore`. Document it in the restore runbook.
--
-- Forward-only. Apply with:
--   docker exec -i sw-db psql -U sw -d sovereignwatch -v ON_ERROR_STOP=1 \
--     < db/migrations/0105_block_mirror_boundary_writes.sql

BEGIN;

CREATE OR REPLACE FUNCTION cpd_block_mirror_boundary() RETURNS trigger AS $fn$
BEGIN
    IF coalesce(current_setting('cpd.allow_mirror_writes', true), 'off') = 'on' THEN
        RETURN NEW;
    END IF;

    IF NEW.boundaries_version = 'current'
       AND NEW.effective_from = DATE '2023-01-01' THEN

        -- In-place repair of a row that already carries the signature is fine:
        -- ~780 un-replaced municipal rows still legitimately have it.
        IF TG_OP = 'UPDATE'
           AND OLD.boundaries_version = 'current'
           AND OLD.effective_from = DATE '2023-01-01' THEN
            RETURN NEW;
        END IF;

        RAISE EXCEPTION
          'Open North mirror boundary write refused: %',
          coalesce(NEW.constituency_id, '(no id)')
          USING
            DETAIL = 'boundaries_version=''current'' + effective_from=2023-01-01 '
                     'is the Open North mirror signature; no authoritative '
                     'loader emits it. Ingestion was retired 2026-08-19, and on '
                     '2026-08-23 a container running a pre-guard image re-created '
                     '1,155 rows and reverted twelve cutover migrations.',
            HINT   = 'Deliberate? BEGIN; SET LOCAL cpd.allow_mirror_writes = ''on''; ...';
    END IF;

    RETURN NEW;
END $fn$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_block_mirror_boundary ON constituency_boundaries;
CREATE TRIGGER trg_block_mirror_boundary
  BEFORE INSERT OR UPDATE ON constituency_boundaries
  FOR EACH ROW EXECUTE FUNCTION cpd_block_mirror_boundary();

-- ── Prove it works, both ways, before committing ─────────────────────────
DO $$
DECLARE blocked boolean := false; kept int;
BEGIN
    BEGIN
        INSERT INTO constituency_boundaries
          (constituency_id, name, level, source_set, boundaries_version,
           effective_from, boundary)
        VALUES ('cpd-trigger-selftest/x', 'Trigger self-test', 'municipal',
                'cpd-trigger-selftest', 'current', DATE '2023-01-01',
                ST_Multi(ST_GeomFromText(
                  'POLYGON((-75 45,-75 45.1,-74.9 45.1,-74.9 45,-75 45))', 4326)));
    EXCEPTION WHEN raise_exception THEN
        blocked := true;
    END;
    IF NOT blocked THEN
        RAISE EXCEPTION 'Self-test FAILED: the trigger let a mirror insert through';
    END IF;

    -- ⚠ And the carve-out must hold, or this migration breaks Stage E.
    SELECT count(*) INTO kept FROM constituency_boundaries
     WHERE boundaries_version = 'current' AND effective_from = DATE '2023-01-01';
    IF kept < 700 THEN
        RAISE EXCEPTION 'Only % legitimate mirror rows remain — expected ~780; '
          'the purge migrations over-reached', kept;
    END IF;

    RAISE NOTICE 'trigger armed; self-test refused a mirror insert; % '
                 'legitimate mirror rows untouched', kept;
END $$;

COMMIT;
