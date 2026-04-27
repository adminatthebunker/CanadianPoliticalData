-- Add ola_member_id column to politicians + UNIQUE partial index, so
-- the historical-MPP backfill (ingest-on-former-mpps) can use ON
-- CONFLICT upserts keyed on the stable Ontario field_member_id.
--
-- Mirrors migration 0031 (ab_assembly_mid) and 0032 (mb_assembly_slug).
-- Each Ontario MPP has an immutable integer member_id assigned by
-- ola.org at /en/members/all/<slug>?_format=json -> field_member_id.
-- These run from 1 in the 1st parliament (1867) to ~7500+ for the
-- current 44th parliament. Type INTEGER (not TEXT like AB) because
-- ola.org never zero-pads — values are clean integers.
--
-- The existing `ola_slug` column (migration 0010) stays as a
-- denormalised secondary slug used by the bill sponsor resolver.
-- It is opportunistically populated during the former-MPPs backfill
-- for any politician we touch (currently empty for all 52 ON rows
-- ingested via Open North).
--
-- Pre-migration verification: zero rows with ola_member_id set
-- (column doesn't exist yet), so no uniqueness collisions to clear.

ALTER TABLE politicians
  ADD COLUMN IF NOT EXISTS ola_member_id INTEGER;

DROP INDEX IF EXISTS idx_politicians_ola_member_id;

CREATE UNIQUE INDEX idx_politicians_ola_member_id
    ON politicians (ola_member_id)
    WHERE ola_member_id IS NOT NULL;
