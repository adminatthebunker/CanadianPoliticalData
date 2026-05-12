-- 0047_websites_provenance.sql
-- Mirror politician_socials' provenance shape onto the websites table so
-- agent-discovered politician websites are auditable and routable through
-- a low-confidence review queue (the same pattern migration 0026 set up
-- for politician_socials).
--
-- Forward-only. Existing rows get NULL source/confidence and
-- flagged_low_confidence=false; only rows written by future ingest
-- (agent_sonnet, etc.) populate these.

ALTER TABLE websites
    ADD COLUMN IF NOT EXISTS source                  TEXT,
    ADD COLUMN IF NOT EXISTS confidence              NUMERIC(4,3),
    ADD COLUMN IF NOT EXISTS evidence_url            TEXT,
    ADD COLUMN IF NOT EXISTS flagged_low_confidence  BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS discovered_at           TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS last_verified_at        TIMESTAMPTZ;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'websites_confidence_range'
    ) THEN
        ALTER TABLE websites
            ADD CONSTRAINT websites_confidence_range
            CHECK (confidence IS NULL OR (confidence BETWEEN 0 AND 1));
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_websites_flagged
    ON websites(flagged_low_confidence) WHERE flagged_low_confidence = true;

-- Coverage view used by the websites Tier-3 agent (agent-missing-websites).
-- Politicians with no active website row AND no denormalised personal_url /
-- official_url on the politicians table itself.
CREATE OR REPLACE VIEW v_websites_missing AS
SELECT  p.id                  AS politician_id,
        p.name,
        p.level,
        p.province_territory,
        p.party,
        p.constituency_name,
        p.openparliament_slug,
        p.ola_slug,
        p.nslegislature_slug,
        p.lims_member_id,
        p.qc_assnat_id,
        p.ab_assembly_mid,
        p.mb_assembly_slug,
        p.nt_mla_slug,
        p.sk_assembly_slug
  FROM  politicians p
  LEFT JOIN websites w
    ON  w.owner_type = 'politician'
   AND  w.owner_id   = p.id
   AND  w.is_active  = true
 WHERE  p.is_active = true
   AND  w.id IS NULL
   AND  COALESCE(NULLIF(TRIM(p.personal_url), ''), NULLIF(TRIM(p.official_url), '')) IS NULL;

COMMENT ON COLUMN websites.source IS
  'Origin of row: legacy|wikidata|openparliament|legislature_scrape|agent_sonnet|admin_manual. '
  'Mirrors politician_socials.source semantics.';
COMMENT ON COLUMN websites.confidence IS
  '[0,1] discovery confidence. Tier-1 scrapers pass 1.0; agent_sonnet rows '
  'flag below 0.85 via flagged_low_confidence.';
COMMENT ON COLUMN websites.flagged_low_confidence IS
  'TRUE when confidence is below the source-specific promotion threshold; '
  'feeds the operator review queue (parallel of /admin/socials/review).';
