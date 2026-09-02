-- 0125 — Trois-Rivières, Saint-Jean-sur-Richelieu, Saguenay and Lévis onto the
--        cities' own geometry. 56 districts.
--
-- Run AFTER:
--   load-boundaries --jurisdiction trois-rivieres-districts
--   load-boundaries --jurisdiction saint-jean-sur-richelieu-districts
--   load-boundaries --jurisdiction saguenay-districts
--   load-boundaries --jurisdiction levis-districts
--
-- ★ NO RE-KEY. Every district id matched name-for-name against the
-- authoritative files, so members keep their `constituency_id` and it simply
-- resolves to the new live row. Contrast 0121 (Terrebonne/Longueuil), where
-- renamed districts stranded four councillors, and 0124, where one Halifax id
-- changed on a `&`. Checked here with --compare before loading, not after.
--
-- ⛔ WHAT --compare MEASURED, AND WHY THE COUNTS WERE NEVER THE POINT
-- ─────────────────────────────────────────────────────────────────
--   set                        matched  mean      min       below 95%
--   trois-rivieres             14/14    92.73%    49.36%    4
--   saint-jean-sur-richelieu   12/12    95.51%    68.58%    2
--   saguenay                   15/15    96.72%    91.26%    3
--   levis                      15/15    83.94%    44.11%    8
--
-- Every one of these sets had a district count that agreed exactly with what we
-- held, which is why they read as healthy for as long as they did. The ground
-- underneath had moved: Lévis's `charny` retains 44% of its former area and 8 of
-- its 15 districts are below 95%; Trois-Rivières's `de-richelieu` retains 49%.
-- The 2025-11-02 general election ran on maps we did not have. Ruling A7 —
-- vintage is measured, never counted.
--
-- ⛔ THREE ROW CLASSES THIS MUST NOT TOUCH
-- ────────────────────────────────────────
-- 1. The four `census-subdivisions` municipality outlines (one per city). They
--    carry the mayor. The new generation does not replace them.
-- 2. ★ Saguenay's THREE BOROUGHS — `chicoutimi`, `jonquiere`, `la-baie`. Saguenay
--    is genuinely two-tier and the city's district file covers only the 15
--    districts. --compare reported these as "we hold, authority does not", which
--    is the same shape a stale row produces and is NOT one: an arrondissement is
--    a real tier with real elected officials (ruling C2, migration 0082 for the
--    Montréal precedent). End-dating them would orphan their members and leave
--    Saguenay with no borough tier at all.
-- 3. Anything not `boundaries_version = 'current'`.
--
-- The predicate below is scoped to `boundary_kind = 'district'` AND
-- `boundaries_version = 'current'` for exactly those reasons, and the DO block
-- asserts all three classes survived.
--
-- ⓘ Date: 2025-11-02, the Québec municipal general election (ruling A10.4 — a
-- map is dated to the election it first governed). ⚠ Not the by-law date: LERM
-- art. 30 forced every division by-law in force on 2024-10-31, so a by-law date
-- is no evidence at all. Old generation end-dated the day before.
--
-- Forward-only. Apply with:
--   docker exec -i sw-db psql -U sw -d sovereignwatch -v ON_ERROR_STOP=1 \
--     < db/migrations/0125_qc_four_cities_cutover.sql

BEGIN;

-- ── 0. The loads must have happened, at the right sizes ─────────────────────
DO $$
DECLARE r record; expected int;
BEGIN
    FOR r IN
        SELECT * FROM (VALUES
            ('trois-rivieres-districts', 14),
            ('saint-jean-sur-richelieu-districts', 12),
            ('saguenay-districts', 15),
            ('levis-districts', 15)
        ) AS t(set_name, n)
    LOOP
        SELECT count(*) INTO expected FROM constituency_boundaries
         WHERE source_set = r.set_name AND boundaries_version = '2025'
           AND boundary_kind = 'district';
        IF expected <> r.n THEN
            RAISE EXCEPTION
              'Expected % authoritative % districts, found %. Run load-boundaries --jurisdiction % first.',
              r.n, r.set_name, expected, r.set_name;
        END IF;
    END LOOP;
END $$;

-- ── 1. Retire the mirror district generation ────────────────────────────────
UPDATE constituency_boundaries
   SET effective_to = DATE '2025-11-01', updated_at = now()
 WHERE source_set IN ('trois-rivieres-districts','saint-jean-sur-richelieu-districts',
                      'saguenay-districts','levis-districts')
   AND boundaries_version = 'current'
   AND boundary_kind = 'district'
   AND effective_to IS NULL;

-- ── 2. Assertions ───────────────────────────────────────────────────────────
DO $$
DECLARE n int;
BEGIN
    -- Exactly 56 live districts across the four, all authoritative.
    SELECT count(*) INTO n FROM constituency_boundaries
     WHERE source_set IN ('trois-rivieres-districts','saint-jean-sur-richelieu-districts',
                          'saguenay-districts','levis-districts')
       AND boundary_kind = 'district'
       AND effective_from <= CURRENT_DATE
       AND (effective_to IS NULL OR effective_to >= CURRENT_DATE);
    IF n <> 56 THEN
        RAISE EXCEPTION 'expected 56 live districts across the four cities, found %', n;
    END IF;

    SELECT count(*) INTO n FROM constituency_boundaries
     WHERE source_set IN ('trois-rivieres-districts','saint-jean-sur-richelieu-districts',
                          'saguenay-districts','levis-districts')
       AND boundary_kind = 'district' AND authority IS NULL
       AND effective_from <= CURRENT_DATE
       AND (effective_to IS NULL OR effective_to >= CURRENT_DATE);
    IF n <> 0 THEN
        RAISE EXCEPTION '% live district rows still carry no authority', n;
    END IF;

    -- ⛔ Saguenay's three boroughs must be untouched.
    SELECT count(*) INTO n FROM constituency_boundaries
     WHERE source_set = 'saguenay-districts' AND boundary_kind = 'borough'
       AND effective_from <= CURRENT_DATE
       AND (effective_to IS NULL OR effective_to >= CURRENT_DATE);
    IF n <> 3 THEN
        RAISE EXCEPTION
          'Saguenay should still have 3 live boroughs (chicoutimi/jonquiere/la-baie), found % — an arrondissement is a real tier, not a stale row', n;
    END IF;

    -- ⛔ The four municipality outlines must be untouched.
    SELECT count(*) INTO n FROM constituency_boundaries
     WHERE source_set IN ('trois-rivieres-districts','saint-jean-sur-richelieu-districts',
                          'saguenay-districts','levis-districts')
       AND boundary_kind = 'municipality'
       AND effective_from <= CURRENT_DATE
       AND (effective_to IS NULL OR effective_to >= CURRENT_DATE);
    IF n <> 4 THEN
        RAISE EXCEPTION 'expected 4 live municipality outlines (they carry the mayors), found %', n;
    END IF;

    -- No id live in two generations.
    SELECT count(*) INTO n FROM (
        SELECT constituency_id FROM constituency_boundaries
         WHERE source_set IN ('trois-rivieres-districts','saint-jean-sur-richelieu-districts',
                              'saguenay-districts','levis-districts')
           AND effective_from <= CURRENT_DATE
           AND (effective_to IS NULL OR effective_to >= CURRENT_DATE)
         GROUP BY constituency_id HAVING count(*) > 1) d;
    IF n <> 0 THEN
        RAISE EXCEPTION '% constituency_id(s) live in two generations', n;
    END IF;

    -- No sitting member orphaned corpus-wide.
    SELECT count(*) INTO n FROM politicians p
     WHERE p.is_active AND p.constituency_id IS NOT NULL
       AND NOT EXISTS (
         SELECT 1 FROM constituency_boundaries b
          WHERE b.constituency_id = p.constituency_id
            AND b.effective_from <= CURRENT_DATE
            AND (b.effective_to IS NULL OR b.effective_to >= CURRENT_DATE));
    IF n <> 0 THEN
        RAISE EXCEPTION '% sitting member(s) orphaned corpus-wide', n;
    END IF;

    RAISE NOTICE '0125 ok: 56 QC districts authoritative; 3 Saguenay boroughs + 4 outlines preserved; 0 orphans';
END $$;

COMMIT;
