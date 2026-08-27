-- 0109 — Ontario mid-size: ten cutovers, two end-dates, nine deliberate holds.
--
-- ★ KAWARTHA LAKES IS NOT A PROVENANCE UPGRADE — IT IS A REPAIR.
-- `--compare` returned mean overlap 15.04%, minimum 0.00%, with 8 of 8 wards
-- below 95%. That looked like a bad file until the areas were checked against
-- the municipality polygon we already hold:
--
--     census-subdivisions/3516010  Kawartha Lakes   3,335.2 km²
--     authoritative 8 wards, summed                ~3,332   km²   (matches)
--     held mirror wards, summed                     2,364.6 km²   (~1,000 short)
--
-- The mirror's wards do not cover the municipality. Roughly 29% of Kawartha
-- Lakes — about a thousand square kilometres — had no ward polygon at all, so
-- every address in it resolved to no councillor. The city moved from sixteen
-- councillors to eight wards for the 2018 election (By-Law 2017-053, OMB appeal
-- dismissed 2017-10-11) and the mirror never carried the new map.
--
-- ⚠ A count check would have passed this: 8 held, 8 authoritative. Only area
-- against an independent polygon caught it. Ruling A7, third Ontario instance.
--
-- ★ BURLINGTON GAINS TWO WARDS — held 4 of 6. Fourth partial-ingest fix in this
-- programme after Winnipeg's Elmwood (0093), Fort Erie's two (0097) and
-- Windsor's Ward 2 (0108).
--
-- ═══ TWO SETS ARE END-DATED, NOT CUT OVER ════════════════════════════════
-- Chatham-Kent and Haldimand County have published 2026 maps but their CURRENT
-- maps have no established in-force date — Chatham-Kent's is either 1997-11-10
-- or 2000-11-13, Haldimand's probably dates from the county's 2001 creation,
-- and neither was resolved. So their mirror rows stay, still carrying a false
-- 2023-01-01 start.
--
-- ★ But a start date is not needed to know an END date. By-law 2588/25 (OLT
-- appeal dismissed 2025-08-25) and Chatham-Kent's March 2025 by-law both put
-- their successors in force on 2026-10-26, so the current maps demonstrably end
-- on 2026-10-25 whatever day they began. End-dating them now is a fact we have;
-- it also stops both generations going live together the morning after the
-- election, which is the failure 0084 was written for.
--
-- ═══ NINE MUNICIPALITIES DELIBERATELY NOT LOADED ═════════════════════════
-- All discovered, verified and staged in the same pass; none has an established
-- in-force date, so none is loaded. Replacing a date known to be false with one
-- that is merely plausible trades a visible error for a hidden one.
--   Brantford        a 2024 ward review whose outcome was not found, and the
--                    count is 5 either way so no count check would catch a change
--   Guelph           geometry may be the 2006 map rather than the 2022 one —
--                    the Calgary A7 failure mode, councillor attributes update
--                    independently of geometry
--   Thunder Bay      no documentation of when its seven wards were established
--   North Dumfries, Wellesley, Wilmot, Woolwich   small townships, nothing found
--   Chatham-Kent, Haldimand   current generations, as above
--
-- Forward-only. Apply with:
--   docker exec -i sw-db psql -U sw -d sovereignwatch -v ON_ERROR_STOP=1 \
--     < db/migrations/0109_ontario_midsize_cutover.sql

BEGIN;

CREATE TEMP TABLE _sets(source_set text PRIMARY KEY, n int) ON COMMIT DROP;
INSERT INTO _sets VALUES
  ('kitchener-wards', 10), ('cambridge-wards', 8), ('oakville-wards', 7),
  ('milton-wards', 4), ('caledon-wards', 6), ('kawartha-lakes-wards', 8),
  ('sault-ste-marie-wards', 5), ('burlington-wards', 6),
  ('waterloo-wards', 7), ('belleville-wards', 2);

DO $$
DECLARE r record; got int;
BEGIN
    FOR r IN SELECT * FROM _sets LOOP
        SELECT count(*) INTO got FROM constituency_boundaries
         WHERE source_set = r.source_set AND boundaries_version <> 'current'
           AND boundary_kind = 'district' AND effective_from <= CURRENT_DATE;
        IF got <> r.n THEN
            RAISE EXCEPTION '%: % authoritative live districts, expected % — '
              'run the load first', r.source_set, got, r.n;
        END IF;
    END LOOP;
END $$;

DELETE FROM constituency_boundaries old
 USING constituency_boundaries new
 WHERE old.source_set IN (SELECT source_set FROM _sets)
   AND old.boundaries_version = 'current'
   AND new.constituency_id = old.constituency_id
   AND new.source_set = old.source_set
   AND new.boundaries_version <> 'current';

-- ⚠ Kawartha Lakes and Belleville re-key cleanly, but Burlington's mirror held
-- only wards 1-4 so wards 5-6 were inserts, and any mirror row whose id the
-- authoritative generation does NOT reproduce would survive the join above.
-- Sweep those explicitly rather than leaving a stale row live.
DELETE FROM constituency_boundaries
 WHERE source_set IN (SELECT source_set FROM _sets)
   AND boundaries_version = 'current'
   AND boundary_kind = 'district';

-- ── The two end-dates ────────────────────────────────────────────────────
UPDATE constituency_boundaries
   SET effective_to = DATE '2026-10-25', updated_at = now()
 WHERE source_set IN ('chatham-kent-wards', 'haldimand-county-wards')
   AND boundaries_version = 'current'
   AND boundary_kind = 'district'
   AND effective_to IS NULL;

DO $$
DECLARE dupes int; orphans int; kl numeric; muni numeric; burl int; dormant int;
BEGIN
    SELECT count(*) INTO dupes FROM (
        SELECT constituency_id FROM constituency_boundaries
         WHERE source_set IN (SELECT source_set FROM _sets)
           AND effective_from <= CURRENT_DATE
           AND (effective_to IS NULL OR effective_to >= CURRENT_DATE)
         GROUP BY 1 HAVING count(*) > 1) d;
    IF dupes <> 0 THEN
        RAISE EXCEPTION 'cutover left % ids live in two generations', dupes;
    END IF;

    -- ★ Kawartha's wards must now cover the municipality. This is the
    -- assertion the whole migration exists for, and it is keyed on a polygon
    -- the cutover did not touch.
    SELECT sum(area_sqkm) INTO kl FROM constituency_boundaries
     WHERE source_set = 'kawartha-lakes-wards' AND boundary_kind = 'district'
       AND effective_from <= CURRENT_DATE;
    SELECT area_sqkm INTO muni FROM constituency_boundaries
     WHERE constituency_id = 'census-subdivisions/3516010';
    IF abs(kl - muni) / muni > 0.02 THEN
        RAISE EXCEPTION 'Kawartha wards sum to % km² against a municipality of '
          '% km² — still not covering the city', round(kl), round(muni);
    END IF;

    SELECT count(*) INTO burl FROM constituency_boundaries
     WHERE source_set = 'burlington-wards' AND boundary_kind = 'district'
       AND effective_from <= CURRENT_DATE
       AND (effective_to IS NULL OR effective_to >= CURRENT_DATE);
    IF burl <> 6 THEN
        RAISE EXCEPTION 'Burlington has % live wards, expected 6', burl;
    END IF;

    -- Three future generations must be dormant: Burlington 6, Chatham-Kent 8,
    -- Haldimand 7.
    SELECT count(*) INTO dormant FROM constituency_boundaries
     WHERE boundaries_version = '2026' AND effective_from > CURRENT_DATE
       AND source_set IN ('burlington-wards', 'chatham-kent-wards',
                          'haldimand-county-wards');
    IF dormant <> 21 THEN
        RAISE EXCEPTION 'expected 21 dormant 2026 districts, found %', dormant;
    END IF;

    SELECT count(*) INTO orphans FROM politicians p
     WHERE p.is_active AND p.constituency_id IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM constituency_boundaries b
                        WHERE b.constituency_id = p.constituency_id);
    IF orphans <> 0 THEN
        RAISE EXCEPTION 'cutover orphaned % sitting members', orphans;
    END IF;

    RAISE NOTICE 'Ontario mid-size: 10 sets cut over, Kawartha now covers its '
                 'municipality, Burlington +2 wards, 2 sets end-dated';
END $$;

COMMIT;

SELECT refresh_map_views();
