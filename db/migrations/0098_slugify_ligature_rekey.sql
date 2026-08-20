-- 0098 — Re-key the one constituency_id minted by a slugify that mangled `œ`.
--
-- ⛔ THE DEFECT WAS DIVERGENCE, NOT THE MANGLING
-- ----------------------------------------------
-- Two implementations of one function:
--
--   • `boundary_loader.slugify` (Python) mints every constituency_id.
--   • `cpd_slugify` (SQL, migration 0080) is what the roster attach joins on,
--     and `qc_municipal_roster.slugify` documents itself as matching the Python
--     one.
--
-- They disagreed on LIGATURES. Unicode NFKD does not touch `œ` — it is a single
-- character, not an accented `o` — so it survived normalisation, survived the
-- combining-mark strip, and was then eaten by the `[^a-z0-9]+` rule and replaced
-- with a hyphen MID-WORD. Postgres `unaccent()`, which `cpd_slugify` uses,
-- expands it to `oe`.
--
--   name          Champlain–L’Île-des-Sœurs
--   Python (was)  champlain-lile-des-s-urs      <- minted into the table
--   SQL           champlain-lile-des-soeurs     <- what the roster looked for
--
-- ★ The symptom was not an error. Three Verdun councillors — one `Conseiller`
-- and two `Conseiller d'arrondissement` — simply failed to attach, among a
-- residue of 65 that looked like ordinary naming noise.
--
-- The Python side now expands ligatures explicitly (`_LIGATURES`), and
-- `check-boundary-coverage` gained TWO checks so this cannot recur silently:
--
--   `slug-divergence` — the two functions must agree on every boundary name.
--   `stale-slug-id`   — a loader-minted id must still equal slugify(name).
--
-- ⚠ The second is the one that matters here: fixing a function does not
-- retroactively fix the ids it already wrote. Without this migration the
-- corrected slugify would mint the right id on the next load and leave the wrong
-- one beside it.
--
-- ⓘ Blast radius is exactly one row. Verified across all 1,908 boundary names:
-- one carries a ligature. Ids keyed on `slug_field` rather than the name
-- (federal FED_NUM, StatCan CSD codes) are correctly excluded from the check.
--
-- Forward-only. Apply with:
--   docker exec -i sw-db psql -U sw -d sovereignwatch -v ON_ERROR_STOP=1 \
--     < db/migrations/0098_slugify_ligature_rekey.sql

BEGIN;

DO $$
DECLARE n int;
BEGIN
    SELECT count(*) INTO n FROM constituency_boundaries
     WHERE constituency_id = 'montreal-boroughs-and-districts/champlain-lile-des-s-urs';
    IF n <> 1 THEN
        RAISE EXCEPTION
          'Expected the mangled Champlain id to be present exactly once, found %', n;
    END IF;
    -- The corrected id must not already exist, or the update collides.
    SELECT count(*) INTO n FROM constituency_boundaries
     WHERE constituency_id = 'montreal-boroughs-and-districts/champlain-lile-des-soeurs';
    IF n <> 0 THEN
        RAISE EXCEPTION
          'The corrected Champlain id already exists — a load ran with the fixed '
          'slugify before this migration, so both generations are present';
    END IF;
END $$;

UPDATE constituency_boundaries
   SET constituency_id = 'montreal-boroughs-and-districts/champlain-lile-des-soeurs',
       updated_at = now()
 WHERE constituency_id = 'montreal-boroughs-and-districts/champlain-lile-des-s-urs';

-- Nothing is attached to it today (that is the defect), but re-key defensively:
-- the roster attach is idempotent and may have run between edits.
UPDATE politicians
   SET constituency_id = 'montreal-boroughs-and-districts/champlain-lile-des-soeurs',
       updated_at = now()
 WHERE constituency_id = 'montreal-boroughs-and-districts/champlain-lile-des-s-urs';
UPDATE politician_terms
   SET constituency_id = 'montreal-boroughs-and-districts/champlain-lile-des-soeurs'
 WHERE constituency_id = 'montreal-boroughs-and-districts/champlain-lile-des-s-urs';

DO $$
DECLARE leftover int;
BEGIN
    SELECT count(*) INTO leftover FROM constituency_boundaries
     WHERE constituency_id LIKE '%-s-urs';
    IF leftover <> 0 THEN
        RAISE EXCEPTION 'Still % ligature-mangled ids', leftover;
    END IF;
    RAISE NOTICE 'Champlain–L''Île-des-Soeurs re-keyed';
END $$;

COMMIT;
