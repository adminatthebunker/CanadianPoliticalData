-- 0089 — Québec municipal: unpick three councillors attached to another
--        municipality's district, and stop the class of error recurring.
--
-- ⛔ THE DEFECT
-- ------------
-- `qc_municipal_roster.py`'s district attach joined on the district slug alone:
--
--     AND b.boundary_kind = 'district'
--     AND split_part(b.constituency_id, '/', 2) = cpd_slugify(p.constituency_name)
--
-- with no clause tying the polygon to the councillor's own municipality. Québec
-- district slugs are nowhere near unique across municipalities — `district-1`
-- exists in THIRTEEN source sets — so the join is ambiguous, and Postgres
-- resolves ambiguity by whichever plan it picks, not by geography.
--
-- Three councillors were attached to a district 100–400 km from the council
-- they sit on:
--
--   Bettyna Bélizaire   Gatineau, Plateau      -> quebec-districts/plateau
--   David Bisson        Kirkland, Saint-Charles-> longueuil-districts/saint-charles
--   Mohamed Ba          Laval, Le Carrefour    -> sherbrooke-districts/carrefour
--
-- ★ Bélizaire is the proof it is the JOIN and not the data: her
-- `politician_terms` row already carries the correct `gatineau-districts/plateau`.
-- Gatineau has a Plateau district; the query simply did not say which Plateau.
--
-- Mohamed Ba came through the article-normalising fallback pass, where
-- `le-carrefour` and `carrefour` fold together — a second way into the same hole.
--
-- ⚠ Why this had to be fixed BEFORE the numbered-district work rather than after:
-- MAMH names no district for 111 of Québec's councillors, identifying them by
-- post number instead, so attaching them means joining on `district-N` — the
-- most ambiguous key in the table. Landing that on top of an unscoped join would
-- have turned 3 wrong rows into ~85.
--
-- The loader fix is in `qc_municipal_roster.py`: every attach now joins through
-- an explicit municipality -> source_set map (`source_set_for`), asserted to
-- resolve before any row is touched. This migration repairs what the old join
-- already wrote; re-running the ingester re-attaches all three correctly.
--
-- Forward-only. Apply with:
--   docker exec -i sw-db psql -U sw -d sovereignwatch -v ON_ERROR_STOP=1 \
--     < db/migrations/0089_qc_cross_municipality_attachments.sql

BEGIN;

-- Detach, do not guess. The ingester re-derives from the municipality's own set
-- on its next run; leaving a wrong-but-populated value would hide the repair
-- from the NULL-only attach passes and make it permanent.
WITH mis AS (
    SELECT p.id,
           p.source_id,
           p.constituency_id AS wrong_id,
           b.source_set,
           CASE WHEN split_part(p.source_id, ':', 2) = 'montreal'
                THEN 'montreal-boroughs-and-districts'
                ELSE split_part(p.source_id, ':', 2) || '-districts'
           END AS expected_set
      FROM politicians p
      JOIN constituency_boundaries b ON b.constituency_id = p.constituency_id
     WHERE p.is_active AND p.level = 'municipal' AND p.province_territory = 'QC'
       AND p.source_id LIKE 'mamh-qc:%'
)
UPDATE politicians p
   SET constituency_id = NULL, updated_at = now()
  FROM mis
 WHERE p.id = mis.id
   -- `census-subdivisions` is legitimate: it is where the StatCan municipal
   -- outline a mayor sits on lives.
   AND mis.source_set NOT IN (mis.expected_set, 'census-subdivisions');

DO $$
DECLARE remaining int;
BEGIN
    SELECT count(*) INTO remaining
      FROM politicians p
      JOIN constituency_boundaries b ON b.constituency_id = p.constituency_id
     WHERE p.is_active AND p.level = 'municipal' AND p.province_territory = 'QC'
       AND p.source_id LIKE 'mamh-qc:%'
       AND b.source_set NOT IN (
             CASE WHEN split_part(p.source_id, ':', 2) = 'montreal'
                  THEN 'montreal-boroughs-and-districts'
                  ELSE split_part(p.source_id, ':', 2) || '-districts' END,
             'census-subdivisions');
    IF remaining <> 0 THEN
        RAISE EXCEPTION
          'Expected 0 cross-municipality QC attachments after repair, found %',
          remaining;
    END IF;
    RAISE NOTICE 'QC: cross-municipality attachments cleared; re-run '
                 'ingest-qc-municipal-roster to re-derive them in-municipality';
END $$;

COMMIT;
