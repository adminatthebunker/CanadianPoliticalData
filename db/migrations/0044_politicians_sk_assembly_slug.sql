-- Add sk_assembly_slug to politicians + UNIQUE partial index, so the SK
-- roster ingester (ingest-sk-mlas) can use ON CONFLICT upserts and the SK
-- Hansard speaker resolver can attribute speaker turns directly via the
-- synthesised slug.
--
-- Mirrors 0041 (nt_mla_slug), 0032 (mb_assembly_slug), 0037 (ola_member_id)
-- as the established per-jurisdiction-stable-ID pattern (CLAUDE.md
-- convention #1).
--
-- Saskatchewan does NOT publish a stable per-MLA identifier — the
-- legassembly.sk.ca MLA detail-page URL is `?first=Scott&last=Moe`
-- (name-based query string). The /media/{alphanumeric}/ photo path uses
-- opaque CMS asset IDs that aren't reusable as MLA keys. So we synthesise
-- the slug ourselves from name: `firstname-lastname` lowercased + dashes
-- + diacritic-stripped (e.g. "scott-moe", "carla-beck"). This is less
-- robust than upstream-provided IDs but is sufficient because:
--   1. The 30th-leg roster is closed (61 seats; one election → one cohort).
--   2. SK doesn't have multiple MLAs with identical first+last in the
--      same parliament (verified against the speaker index).
--   3. The slug is stable across the parliament — re-runs upsert by it.
--
-- Type TEXT (not int) because the slug is name-derived. Partial index
-- skips rows where the slug stays NULL (most non-SK politicians).

ALTER TABLE politicians
  ADD COLUMN IF NOT EXISTS sk_assembly_slug TEXT;

DROP INDEX IF EXISTS idx_politicians_sk_assembly_slug;

CREATE UNIQUE INDEX idx_politicians_sk_assembly_slug
    ON politicians (sk_assembly_slug)
    WHERE sk_assembly_slug IS NOT NULL;
