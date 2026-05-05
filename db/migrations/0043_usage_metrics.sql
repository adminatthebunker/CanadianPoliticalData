-- Operator-observability tables for the admin /usage page. All three
-- live in `private` because they are operational telemetry, not part
-- of the redistributable political dataset (CLAUDE.md convention #8).
-- The weekly public dump (`pg_dump --schema=public`) cannot pull them
-- in by construction; nothing else is needed for that boundary.
--
-- Three signal classes, three storage shapes:
--   1. private.gpu_samples       — host GPU pressure (NVML poll, 30s)
--   2. private.tei_samples       — TEI runtime metrics (Prometheus, 30s)
--   3. private.search_request_log — per-search timing (inline Fastify hook)
--
-- The search log records timings + filter shape only. No raw query
-- text, no user_id, no IP, no email — what's not in the INSERT can't
-- leak. `was_authenticated` and `tier` are coarse user-shape fields
-- so we can answer "is the slow path concentrated on free vs paid?"
-- without becoming a PII surface.

CREATE TABLE IF NOT EXISTS private.gpu_samples (
  sampled_at      timestamptz NOT NULL DEFAULT now(),
  gpu_index       integer     NOT NULL DEFAULT 0,
  mem_used_mb     integer     NOT NULL,
  mem_total_mb    integer     NOT NULL,
  util_gpu_pct    integer     NOT NULL,
  util_mem_pct    integer     NOT NULL,
  temperature_c   integer,
  power_w         numeric(6,2)
);

CREATE INDEX IF NOT EXISTS idx_gpu_samples_sampled_at
  ON private.gpu_samples (sampled_at DESC);

CREATE TABLE IF NOT EXISTS private.tei_samples (
  sampled_at                  timestamptz NOT NULL DEFAULT now(),
  -- Live counters / gauges parsed out of the Prometheus text. Nullable
  -- so a partial parse (TEI version that renames a metric, etc.) still
  -- writes a row instead of silently dropping the sample.
  queue_size                  integer,
  request_count_total         bigint,
  request_failure_total       bigint,
  request_duration_p50_ms     numeric(10,2),
  request_duration_p95_ms     numeric(10,2),
  request_duration_p99_ms     numeric(10,2),
  batch_next_size_avg         numeric(10,2),
  -- Forward-compat: store the raw scrape so future derived columns
  -- can be backfilled by re-parsing historical rows.
  raw_metrics                 text
);

CREATE INDEX IF NOT EXISTS idx_tei_samples_sampled_at
  ON private.tei_samples (sampled_at DESC);

CREATE TABLE IF NOT EXISTS private.search_request_log (
  created_at         timestamptz NOT NULL DEFAULT now(),
  -- Route name only (e.g. '/api/v1/search/speeches'). Never the URL
  -- with query params — that would carry the user's search text.
  endpoint           text        NOT NULL,
  total_ms           integer     NOT NULL,
  tei_ms             integer,
  sql_ms             integer,
  result_count       integer,
  was_anchor_query   boolean     NOT NULL DEFAULT false,
  was_authenticated  boolean     NOT NULL DEFAULT false,
  tier               text,
  status_code        integer     NOT NULL,
  cached_embedding   boolean     NOT NULL DEFAULT false,
  -- Coarse shape signal: "did this query carry any structural filter?"
  -- Useful for "is the slow path concentrated on filter-less q-only
  -- queries?" without recording which filters specifically.
  has_filters        boolean     NOT NULL DEFAULT false
);

CREATE INDEX IF NOT EXISTS idx_search_request_log_created_at
  ON private.search_request_log (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_search_request_log_slow
  ON private.search_request_log (total_ms DESC, created_at DESC);

-- Retention. Called on a weekly schedule; deletes drop rows past their
-- per-table cutoff. Returns counts so the runner can log what it did.
-- Different cutoffs per table because their volumes differ:
--   gpu_samples / tei_samples: ~2 rows/min × 2 = ~5,800/day, kept 90d.
--   search_request_log:        bounded by traffic, kept 30d.
CREATE OR REPLACE FUNCTION private.gc_usage_metrics()
RETURNS TABLE(table_name text, deleted_rows bigint)
LANGUAGE plpgsql
AS $$
DECLARE
  d_gpu    bigint;
  d_tei    bigint;
  d_search bigint;
BEGIN
  DELETE FROM private.gpu_samples
   WHERE sampled_at < now() - interval '90 days';
  GET DIAGNOSTICS d_gpu = ROW_COUNT;

  DELETE FROM private.tei_samples
   WHERE sampled_at < now() - interval '90 days';
  GET DIAGNOSTICS d_tei = ROW_COUNT;

  DELETE FROM private.search_request_log
   WHERE created_at < now() - interval '30 days';
  GET DIAGNOSTICS d_search = ROW_COUNT;

  RETURN QUERY VALUES
    ('gpu_samples'::text,         d_gpu),
    ('tei_samples'::text,         d_tei),
    ('search_request_log'::text,  d_search);
END
$$;
