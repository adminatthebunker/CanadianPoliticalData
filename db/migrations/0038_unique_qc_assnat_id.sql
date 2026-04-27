-- Promote idx_politicians_qc_assnat_id from a regular partial btree to
-- a UNIQUE partial index, so the historical-MNA backfill
-- (ingest-qc-former-mnas) can use ON CONFLICT upserts keyed on the
-- stable assnat.qc.ca numeric MNA id.
--
-- Mirrors 0031 (ab_assembly_mid), 0032 (mb_assembly_slug),
-- 0037 (ola_member_id). The qc_assnat_id column itself was added in
-- 0012; we're only tightening its uniqueness constraint here.
--
-- Pre-migration verification:
--   SELECT qc_assnat_id, count(*) FROM politicians
--    WHERE qc_assnat_id IS NOT NULL
--    GROUP BY 1 HAVING count(*) > 1;
-- Must return zero rows. The 124 current-MNA rows ingested via
-- enrich-qc-mna-ids are already keyed 1:1 by qc_assnat_id (it's the
-- assembly's stable per-MNA identifier — see qc_mnas.py docstring).

DROP INDEX IF EXISTS idx_politicians_qc_assnat_id;

CREATE UNIQUE INDEX idx_politicians_qc_assnat_id
    ON politicians (qc_assnat_id)
    WHERE qc_assnat_id IS NOT NULL;
