-- 0104 — re-attach the 117 sitting members left without a district.
--
-- After 0101–0103 the boundary table and the roster are both correct, but 120
-- sitting federal/provincial members carry no resolvable district: BC 41,
-- NL 36, NB 27, SK 15, and one MP. Two causes, one fix.
--
--   • The 2026-08-23 run re-pointed ~940 members onto mirror constituency_ids.
--     0101 carried most of them across by matching the id TAIL, which survives
--     a prefix change (`…/10001` on both sides). Where the mirror generation
--     used different district ids than the authoritative one — Newfoundland's
--     mirror set holds 36 districts against the 2015 commission's 40 — there
--     was no tail to match, and 0101 correctly set NULL rather than guess.
--   • BC and NB were already detached before the incident.
--
-- ★ Attach on the district NAME, which both sides agree on even when their ids
-- do not. `cpd_slugify` on both sides, so the comparison is accent-, case- and
-- punctuation-insensitive — and it is the SQL half of the pair that
-- `check-boundary-coverage` now asserts stays in step with Python's `slugify`,
-- after a ligature divergence silently detached three Verdun councillors
-- (`Sœurs` → `s-urs` on one side, `soeurs` on the other).
--
-- ⛔ AMBIGUITY IS A REFUSAL, NOT A TIE-BREAK. A member whose name matches two
-- live boundaries is not attached and not guessed at. Postgres resolves an
-- ambiguous join by plan choice, not by geography, which is how Gatineau's
-- Plateau councillor ended up on Québec City's Plateau 400 km away (0089).
--
-- ⚠ Scoped to federal and provincial. Municipal district names are nowhere near
-- unique — `District 1` exists in dozens of Québec municipalities — so the same
-- join there would need a municipality qualifier, which is `qc_municipal_roster`'s
-- job, not this migration's.
--
-- ⛔ THREE SASKATCHEWAN MEMBERS ARE LEFT DETACHED, DELIBERATELY. Their district
-- names match nothing live: SK's roster still carries 2012 names against the
-- 2022 Representation Act map. SK sits at exactly 61 members for 61 seats, so
-- they are sitting MLAs whose district was RENAMED, not members who left —
-- retiring them would invent vacancies in a full chamber, and attaching them
-- would require a hand-built rename table. Named here so the residue is a known
-- three, not an unexplained gap: see the postcondition.
--
-- Forward-only. Apply with:
--   docker exec -i sw-db psql -U sw -d sovereignwatch -v ON_ERROR_STOP=1 \
--     < db/migrations/0104_reattach_members_by_slug.sql

BEGIN;

CREATE TEMP TABLE _attach ON COMMIT DROP AS
SELECT p.id AS politician_id,
       min(b.constituency_id) AS constituency_id,
       count(DISTINCT b.constituency_id) AS candidates
  FROM politicians p
  JOIN constituency_boundaries b
    ON b.level = p.level
   AND (p.level = 'federal' OR b.province_territory = p.province_territory)
   AND b.effective_from <= CURRENT_DATE
   AND (b.effective_to IS NULL OR b.effective_to >= CURRENT_DATE)
   AND cpd_slugify(b.name) = cpd_slugify(p.constituency_name)
 WHERE p.is_active
   AND p.level IN ('federal', 'provincial')
   AND (p.level <> 'federal' OR p.elected_office = 'MP')
   AND p.constituency_name IS NOT NULL
   AND (p.constituency_id IS NULL
        OR NOT EXISTS (SELECT 1 FROM constituency_boundaries x
                        WHERE x.constituency_id = p.constituency_id))
 GROUP BY p.id;

DO $$
DECLARE total int; ambiguous int;
BEGIN
    SELECT count(*), count(*) FILTER (WHERE candidates > 1)
      INTO total, ambiguous FROM _attach;
    IF ambiguous <> 0 THEN
        RAISE EXCEPTION '% members match more than one live district — refusing '
          'to let the query planner choose their riding', ambiguous;
    END IF;
    IF total <> 117 THEN
        RAISE EXCEPTION 'Attachable set is %, not the measured 117', total;
    END IF;
END $$;

UPDATE politicians p
   SET constituency_id = a.constituency_id, updated_at = now()
  FROM _attach a WHERE p.id = a.politician_id;

-- ⚠ The open term must move too. A term row left pointing at a dead id is a
-- second, quieter dangling reference that no coverage check looks at.
UPDATE politician_terms t
   SET constituency_id = a.constituency_id
  FROM _attach a
 WHERE t.politician_id = a.politician_id AND t.ended_at IS NULL;

DO $$
DECLARE r record; left_over int;
BEGIN
    FOR r IN
        SELECT p.level, p.province_territory AS ju, count(*) AS n
          FROM politicians p
         WHERE p.is_active AND p.level IN ('federal', 'provincial')
           AND (p.level <> 'federal' OR p.elected_office = 'MP')
           AND (p.constituency_id IS NULL
                OR NOT EXISTS (SELECT 1 FROM constituency_boundaries b
                                WHERE b.constituency_id = p.constituency_id))
         GROUP BY 1, 2
    LOOP
        IF NOT (r.level = 'provincial' AND r.ju = 'SK' AND r.n = 3) THEN
            RAISE EXCEPTION '%/%: % members still unattached — only the three '
              'known Saskatchewan renames were expected', r.level, r.ju, r.n;
        END IF;
    END LOOP;

    SELECT count(*) INTO left_over FROM politicians p
     WHERE p.is_active AND p.constituency_id IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM constituency_boundaries b
                        WHERE b.constituency_id = p.constituency_id);
    IF left_over <> 0 THEN
        RAISE EXCEPTION '% members point at a non-existent boundary', left_over;
    END IF;

    RAISE NOTICE '0104: 117 members re-attached; 3 SK renames remain, named';
END $$;

COMMIT;

SELECT refresh_map_views();
