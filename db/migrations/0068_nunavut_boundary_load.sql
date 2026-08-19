-- 0068 — Nunavut: the first jurisdiction loaded from nothing.
--
-- ★ Not a cutover — a creation. Nunavut is the ONLY jurisdiction where we held
-- zero boundary rows. Not stale: absent. Open North never published a Nunavut
-- boundary set, and our loader only ever fetched boundaries as a side effect of
-- roster ingestion, so all 22 NU politicians carried a NULL `constituency_id`
-- and a postcode lookup anywhere in Nunavut returned nothing at the territorial
-- level. 100% no-answer, the only jurisdiction in the country at that figure.
--
-- Because there is nothing to migrate, this is also the only place where the
-- correct `constituency_id` convention was FREE rather than a migration:
-- `nunavut-electoral-districts/<slug>`, generation-free from the start.
-- (The dossier's original `-2024` suffix recommendation is superseded — following
-- it would have minted 22 brand-new violating keys into a clean table.)
--
-- ⚠ The filenames are inverted
-- ----------------------------
-- `EN_FUTURE_NU_Constituencies.zip` is the set **currently in force**;
-- `EN_PRESENT_2013_Present_…` is **superseded**. Both were named relative to
-- their 2024-10-28 release date and never revised, so when the 6th Assembly
-- dissolved the labels silently swapped meaning. The loader keys on the spec, not
-- the filename.
--
-- `effective_from = 2025-09-22`: Bill 48, *An Act Respecting the Constituencies
-- of Nunavut*; per *Nunavut Elections Act* s.29(2) it "comes into force on the
-- 1st day following the day the Legislative Assembly dissolves". The 6th Assembly
-- dissolved 2025-09-21. Elections Nunavut's own annual report states
-- "(Effective September 22, 2025)". ⛔ Every metadata date is wrong by 10+ months.
--
-- Run AFTER `load-boundaries --jurisdiction nunavut`.
--
-- Forward-only. Apply with:
--   docker exec -i sw-db psql -U sw -d sovereignwatch -v ON_ERROR_STOP=1 \
--     < db/migrations/0068_nunavut_boundary_load.sql

BEGIN;

DO $$
DECLARE n int;
BEGIN
    SELECT count(*) INTO n FROM constituency_boundaries
     WHERE source_set = 'nunavut-electoral-districts'
       AND boundaries_version = '2025';
    IF n <> 22 THEN
        RAISE EXCEPTION
          'Expected 22 Nunavut rows, found %. Run '
          '`load-boundaries --jurisdiction nunavut` first.', n;
    END IF;
END $$;

-- ── Display casing ──────────────────────────────────────────────────────────
-- ⚠ Elections Nunavut stores district names in UPPERCASE ("IQALUIT-NIAQUNNGUU"),
-- unlike every other jurisdiction in the table, and the public API surfaces
-- `name` verbatim.
--
-- Rather than invent a title-casing rule in the loader — which would be a
-- transformation applied to an authoritative source, and which naive
-- implementations get wrong on particles like "BAIE d'HUDSON" — the display form
-- is taken from our own roster, which already carries the Assembly's title-case
-- spelling ("Arviat North-Whale Cove", "Gjoa Haven"). Identity is unaffected:
-- slugs derive from a lowercased name, so this changes presentation only.
--
-- ⓘ Nunavut Elections Act s.31(1) makes all four language versions of a district
-- name equally authoritative. `name` and `name_fr` are the only columns we have,
-- so the Inuktitut syllabics (`Name_I`, all 22) and Inuinnaqtun (`Name_Inu`,
-- 11 of 22) are not stored. That is a real fidelity loss and a known follow-up.
UPDATE constituency_boundaries b
   SET name = p.constituency_name
  FROM (
    SELECT DISTINCT ON (lower(constituency_name))
           constituency_name
      FROM politicians
     WHERE province_territory = 'NU' AND level = 'provincial' AND is_active
       AND constituency_name IS NOT NULL
     ORDER BY lower(constituency_name), constituency_name
  ) p
 WHERE b.source_set = 'nunavut-electoral-districts'
   AND lower(b.name) = lower(p.constituency_name)
   AND b.name <> p.constituency_name;

-- ── Attach the roster ───────────────────────────────────────────────────────
-- All 22 NU politicians have a NULL constituency_id today, for the structural
-- reason above. Verified 22/22 join case-insensitively with zero residue.
UPDATE politicians p
   SET constituency_id = b.constituency_id
  FROM constituency_boundaries b
 WHERE p.province_territory = 'NU' AND p.level = 'provincial' AND p.is_active
   AND p.constituency_id IS NULL
   AND b.source_set = 'nunavut-electoral-districts'
   AND lower(b.name) = lower(p.constituency_name);

DO $$
DECLARE bnd int; attached int; orphans int;
BEGIN
    SELECT count(*) INTO bnd FROM constituency_boundaries
     WHERE level='provincial' AND province_territory='NU'
       AND effective_from <= CURRENT_DATE
       AND (effective_to IS NULL OR effective_to >= CURRENT_DATE);
    IF bnd <> 22 THEN
        RAISE EXCEPTION 'Expected 22 current NU boundaries, found %', bnd;
    END IF;

    SELECT count(*) INTO attached FROM politicians
     WHERE province_territory='NU' AND level='provincial' AND is_active
       AND constituency_id IS NOT NULL;
    IF attached <> 22 THEN
        RAISE EXCEPTION
          'Expected all 22 NU politicians attached, got %. The join was verified '
          'at 22/22 before load, so a shortfall means the casing update or the '
          'roster changed underneath.', attached;
    END IF;

    SELECT count(*) INTO orphans FROM politicians p
     WHERE p.constituency_id LIKE 'nunavut-electoral-districts%'
       AND NOT EXISTS (SELECT 1 FROM constituency_boundaries b
                        WHERE b.constituency_id = p.constituency_id);
    IF orphans <> 0 THEN
        RAISE EXCEPTION 'NU load left % orphaned politician rows', orphans;
    END IF;

    RAISE NOTICE 'NU: 22 of 22 districts created and attached — first territorial answers ever';
END $$;

COMMIT;

SELECT refresh_map_views();
