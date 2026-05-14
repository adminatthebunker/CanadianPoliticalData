-- Scrape monitoring: extend credit_ledger.kind with the three new states
-- for the user-billed Apify-backed politician-monitoring feature.
--
-- The three kinds mirror the report-job triad shape:
--   * scrape_hold    -- -N when a scheduled scrape is queued
--   * scrape_commit  -- marker state flip (no delta change) on success
--   * scrape_refund  -- marker state flip on failure (full refund)
--
-- The existing uniq_credit_ledger_kind_ref partial unique index
-- (defined in 0033) covers (kind, reference_id) WHERE reference_id IS
-- NOT NULL, so duplicate holds for the same scrape_jobs.id raise a
-- unique_violation (SQLSTATE 23505) automatically. reference_id will
-- be the scrape_jobs.id (text-cast UUID).
--
-- Pattern follows 0034 exactly: introspect the existing CHECK
-- constraint by name (so this migration survives prior renames) and
-- drop + readd. Postgres has no ALTER ADD CHECK on an existing
-- constraint; drop + re-add is the canonical move.
--
-- The table now lives in `private` per 0042; the constraint is
-- attached to the table by OID, so the introspection still resolves.

DO $$
DECLARE
  cname text;
BEGIN
  SELECT conname INTO cname
    FROM pg_constraint
   WHERE conrelid = 'private.credit_ledger'::regclass
     AND contype  = 'c'
     AND pg_get_constraintdef(oid) LIKE '%stripe_purchase%'
     AND pg_get_constraintdef(oid) LIKE '%correction_reward%'
   LIMIT 1;
  IF cname IS NULL THEN
    RAISE EXCEPTION 'expected kind CHECK constraint on private.credit_ledger not found';
  END IF;
  EXECUTE format('ALTER TABLE private.credit_ledger DROP CONSTRAINT %I', cname);
END $$;

ALTER TABLE private.credit_ledger
  ADD CONSTRAINT credit_ledger_kind_check
  CHECK (kind IN (
    'stripe_purchase',
    'admin_credit',
    'report_hold',
    'report_commit',
    'report_refund',
    'correction_reward',
    'scrape_hold',
    'scrape_commit',
    'scrape_refund'
  ));
