-- 0107 — attach Saskatchewan's last three members: spelling variants, not renames.
--
-- ⚠ CORRECTS 0104's HEADER. That migration left these three detached and
-- described them as districts "renamed 2012 -> 2022", inferred from the fact
-- that SK's roster predates the 2022 Representation Act map. That was wrong.
-- With the rest of the province attached, exactly three members are unattached
-- and exactly three districts are unfilled, and they pair one-to-one on
-- spelling alone:
--
--   roster                      authoritative (Elections Saskatchewan)
--   Saskatoon Silver Springs    Saskatoon Silverspring
--   Saskatoon Chief Mistawis    Saskatoon Chief Mistawasis
--   Moosomin-Monmartre          Moosomin-Montmartre
--
-- ★ The boundary side is correct in all three: Mistawasis is the Cree name
-- carried by Mistawasis Nêhiyawak, Montmartre is the town's actual spelling,
-- and Silverspring is Elections Saskatchewan's form. These are roster typos
-- inherited from the Open North mirror, which is why `cpd_slugify` could not
-- bridge them — it normalises accents, case and punctuation, not misspellings.
--
-- ⛔ Hand-written, and deliberately so. A fuzzy matcher (trigram similarity,
-- Levenshtein) would attach these three and would ALSO attach the next
-- near-miss that happens to be a genuinely different riding. Three rows do not
-- justify a heuristic that has to be right forever; an explicit table can be
-- read and disagreed with. The assertion below is what makes it safe: if the
-- unattached set is not exactly these three, nothing is written.
--
-- ⚠ Fixes the ROSTER row, not just the attachment. `constituency_name` is what
-- renders on the politician's page and what every future slug join uses, so
-- leaving the misspelling in place would mean re-solving this the next time
-- anyone joins on the name.
--
-- Forward-only. Apply with:
--   docker exec -i sw-db psql -U sw -d sovereignwatch -v ON_ERROR_STOP=1 \
--     < db/migrations/0107_sk_roster_spelling_attachments.sql

BEGIN;

CREATE TEMP TABLE _sk_fix (roster_name text, correct_name text) ON COMMIT DROP;
INSERT INTO _sk_fix VALUES
  ('Saskatoon Silver Springs', 'Saskatoon Silverspring'),
  ('Saskatoon Chief Mistawis', 'Saskatoon Chief Mistawasis'),
  ('Moosomin-Monmartre',       'Moosomin-Montmartre');

DO $$
DECLARE unattached int; unmatched int;
BEGIN
    SELECT count(*) INTO unattached FROM politicians p
     WHERE p.is_active AND p.level = 'provincial' AND p.province_territory = 'SK'
       AND (p.constituency_id IS NULL
            OR NOT EXISTS (SELECT 1 FROM constituency_boundaries b
                            WHERE b.constituency_id = p.constituency_id));
    IF unattached <> 3 THEN
        RAISE EXCEPTION 'Saskatchewan has % unattached members, not the three '
          'this table describes — do not apply a hand-written map to a set it '
          'was not written for', unattached;
    END IF;

    -- Every correct_name must name exactly one live, currently-unfilled district.
    SELECT count(*) INTO unmatched FROM _sk_fix f
     WHERE NOT EXISTS (
        SELECT 1 FROM constituency_boundaries b
         WHERE b.level = 'provincial' AND b.province_territory = 'SK'
           AND b.name = f.correct_name
           AND b.effective_from <= CURRENT_DATE
           AND (b.effective_to IS NULL OR b.effective_to >= CURRENT_DATE));
    IF unmatched <> 0 THEN
        RAISE EXCEPTION '% of the three target districts do not exist under the '
          'spelling given', unmatched;
    END IF;
END $$;

UPDATE politicians p
   SET constituency_name = f.correct_name,
       constituency_id   = b.constituency_id,
       updated_at = now()
  FROM _sk_fix f
  JOIN constituency_boundaries b
    ON b.level = 'provincial' AND b.province_territory = 'SK'
   AND b.name = f.correct_name
   AND b.effective_from <= CURRENT_DATE
   AND (b.effective_to IS NULL OR b.effective_to >= CURRENT_DATE)
 WHERE p.is_active AND p.level = 'provincial' AND p.province_territory = 'SK'
   AND p.constituency_name = f.roster_name;

UPDATE politician_terms t
   SET constituency_id = p.constituency_id
  FROM politicians p
 WHERE t.politician_id = p.id AND t.ended_at IS NULL
   AND p.constituency_name IN (SELECT correct_name FROM _sk_fix);

INSERT INTO politician_changes (politician_id, change_type, old_value, new_value, severity)
SELECT p.id, 'constituency_change',
       jsonb_build_object('constituency_name', f.roster_name),
       jsonb_build_object('constituency_name', f.correct_name,
                          'via', '0107_sk_roster_spelling_attachments',
                          'cause', 'mirror-inherited misspelling'),
       'info'
  FROM politicians p JOIN _sk_fix f ON p.constituency_name = f.correct_name
 WHERE p.is_active AND p.level = 'provincial' AND p.province_territory = 'SK';

DO $$
DECLARE left_over int;
BEGIN
    SELECT count(*) INTO left_over FROM politicians p
     WHERE p.is_active AND p.level = 'provincial' AND p.province_territory = 'SK'
       AND (p.constituency_id IS NULL
            OR NOT EXISTS (SELECT 1 FROM constituency_boundaries b
                            WHERE b.constituency_id = p.constituency_id));
    IF left_over <> 0 THEN
        RAISE EXCEPTION '% Saskatchewan members still unattached', left_over;
    END IF;
    RAISE NOTICE '0107: three Saskatchewan spellings corrected and attached';
END $$;

COMMIT;

SELECT refresh_map_views();
