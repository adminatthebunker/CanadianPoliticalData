-- 0120 — Recorded aliases for district names two sources spell differently.
--
-- WHY
-- ───
-- A roster and a boundary file are published by different bodies, and they do
-- not always agree on a district's name. Where they disagree, one of them is
-- wrong or merely abbreviating — but the member is still that district's
-- member, and an exact slug join drops them on the floor.
--
-- Montréal, found 2026-08-28, is the whole case in three rows:
--
--   MAMH roster                                          City of Montréal
--   Étienne-Desmarteaux                                  Étienne-Desmarteau
--   St-Henri-Petite-Bourgogne-Pte-St-Charles-Griffintown Saint-Henri-Est-…
--
-- The first is a plain error in the provincial CSV: the district is named for
-- the athlete Étienne Desmarteau, who had no x. The other two are MAMH
-- abbreviating (St- for Saint-, Pte- for Pointe-) and dropping "Est".
--
-- ⛔ THIS TABLE IS NOT A FUZZY MATCHER, and must never become one. Every row is
-- an explicit, reasoned, auditable decision with the evidence in the `reason`
-- column. The alternative — normalising abbreviations algorithmically — would
-- silently pair `Saint-Charles` in Kirkland with `Saint-Charles` in Longueuil,
-- which is exactly the 400 km error migration 0089 exists to undo. Scoped per
-- COUNCIL for the same reason.
--
-- ⚠ An alias is for two sources naming the SAME district differently. It is
-- NOT the fix for a district that was genuinely RENAMED — a rename means the
-- polygon's own name is now stale and should be corrected in place, not
-- papered over from the roster side.

BEGIN;

CREATE TABLE IF NOT EXISTS constituency_name_alias (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    council     text NOT NULL,   -- middle field of politicians.source_id
    alias_slug  text NOT NULL,   -- cpd_slugify() of the roster's spelling
    target_slug text NOT NULL,   -- the polygon's own slug
    reason      text NOT NULL,   -- why these are the same district
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (council, alias_slug)
);

COMMENT ON TABLE constituency_name_alias IS
  'Explicit per-council district-name equivalences between a roster source and '
  'a boundary source. One row per reasoned decision; never algorithmic.';

INSERT INTO constituency_name_alias (council, alias_slug, target_slug, reason)
VALUES
  ('montreal', 'etienne-desmarteaux', 'etienne-desmarteau',
   'MAMH Elec2025_Mun.csv spells the district Étienne-Desmarteaux. The City of '
   'Montréal spells it Étienne-Desmarteau, after the athlete Étienne '
   'Desmarteau (1873-1905), whose surname has no x. The city is the naming '
   'authority for its own districts; the provincial CSV carries a typo.'),
  ('montreal',
   'st-henri-petite-bourgogne-pte-st-charles-griffintown',
   'saint-henri-est-petite-bourgogne-pointe-saint-charles-griffintown',
   'MAMH abbreviates St- for Saint- and Pte- for Pointe-, and omits the Est '
   'qualifier. Same district: the city''s Sud-Ouest borough has exactly one '
   'district containing both Petite-Bourgogne and Griffintown.')
ON CONFLICT (council, alias_slug) DO NOTHING;

DO $$
DECLARE n_bad int;
BEGIN
    -- Every alias must point at a district that actually exists and is live.
    -- An alias to nothing is worse than no alias: it looks handled.
    SELECT count(*) INTO n_bad
      FROM constituency_name_alias a
     WHERE NOT EXISTS (
             SELECT 1 FROM constituency_boundaries b
              WHERE split_part(b.constituency_id, '/', 2) = a.target_slug
                AND b.level = 'municipal'
                AND b.effective_from <= CURRENT_DATE
                AND (b.effective_to IS NULL OR b.effective_to >= CURRENT_DATE));
    IF n_bad <> 0 THEN
        RAISE EXCEPTION '% alias row(s) target a district that is not live', n_bad;
    END IF;
    RAISE NOTICE '0120 ok: % alias rows, all targets live',
                 (SELECT count(*) FROM constituency_name_alias);
END $$;

COMMIT;
