-- 0055_postcode_cache.sql — Cache for Open North postcode lookups.
--
-- Context: /api/public/v1/postcodes/:postcode and /boundaries/lookup?postcode=
-- proxy Open North in real time. This table caches the per-postcode
-- response so repeat lookups skip the upstream call and outages of
-- Open North don't take our endpoint down.
--
-- Cache semantics (enforced in application code, services/api/src/lib/postcode.ts):
--   - Fresh (fetched_at within 30 days): serve from cache, no upstream call.
--   - Stale (older than 30 days): refetch from upstream; if upstream succeeds,
--     overwrite the row; if upstream returns 5xx, serve the stale row anyway
--     and log the stale-serve. Only invalidate on a confirmed 404 (postcode
--     no longer exists).
--   - Missing: hit upstream, then upsert on success.
--
-- Storage shape rationale:
--   - postcode is the PK (already normalized + uppercase, no spaces).
--   - Stored as discrete lng/lat doubles rather than PostGIS POINT to keep
--     the table lean and reads cheap (no PostGIS roundtrip for the common
--     read path; PIP lookups use ST_MakePoint() at query time).
--   - city/province are denormalized passthroughs from Open North, useful
--     for analytics and surfacing in responses without a second roundtrip.
--   - source is a passthrough of which upstream populated the row, in case
--     we ever add a second source (StatCan PCCF, e.g.) — defaults to
--     'opennorth'.
--
-- Privacy:
--   - This is reference data, not personal data. A postcode is a public
--     geographic identifier; no user_id, ip, or session ever lives here.
--   - Lives in public schema (no risk of bleeding PII into the public
--     dump — the public/private split holds).

CREATE TABLE public.postcode_cache (
  postcode      TEXT PRIMARY KEY,
  centroid_lng  DOUBLE PRECISION NOT NULL,
  centroid_lat  DOUBLE PRECISION NOT NULL,
  city          TEXT,
  province      TEXT,
  source        TEXT NOT NULL DEFAULT 'opennorth',
  fetched_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Cleanup helper: list/prune rows older than N days. Background pruning
-- isn't required for correctness (the SWR layer refreshes lazily) but
-- the index makes age-based queries cheap if we ever add a cleanup job.
CREATE INDEX idx_postcode_cache_fetched_at
  ON public.postcode_cache (fetched_at);
