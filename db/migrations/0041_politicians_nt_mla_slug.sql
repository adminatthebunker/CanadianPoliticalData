-- Add nt_mla_slug column to politicians + UNIQUE partial index, so the
-- NT roster ingester (ingest-nt-mlas) can use ON CONFLICT upserts keyed
-- on the stable ntlegislativeassembly.ca slug, and the NT Hansard
-- parser can attribute speaker turns directly via the
-- <a href="/meet-members/mla/{slug}"> wrappers in the transcript HTML.
--
-- Mirrors migration 0031 (ab_assembly_mid), 0032 (mb_assembly_slug),
-- and 0037 (ola_member_id). NT publishes individual MLA bios at:
--   /meet-members/mla/{slug}     -- current 19 MLAs of 20th Assembly
--   /former-members/{slug}       -- ~100+ former MLAs (different path)
--
-- The slug itself is consistent across the two URL paths — same MLA
-- rolling from current to former keeps the same kebab-case "first-last"
-- form. We use the slug (not the path) as the canonical key.
--
-- Type TEXT because the slug is kebab-case ("caitlin-cleveland",
-- "robert-hawkins"), not numeric. NT runs consensus government — no
-- party affiliation is recorded on these MLAs (party stays NULL).
--
-- Pre-migration verification: no existing politicians rows have an
-- nt_mla_slug column (it doesn't exist yet), so no uniqueness
-- collisions to clear.

ALTER TABLE politicians
  ADD COLUMN IF NOT EXISTS nt_mla_slug TEXT;

DROP INDEX IF EXISTS idx_politicians_nt_mla_slug;

CREATE UNIQUE INDEX idx_politicians_nt_mla_slug
    ON politicians (nt_mla_slug)
    WHERE nt_mla_slug IS NOT NULL;
