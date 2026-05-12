-- Developer-API key management (phase 1a-i of the public dev-API workstream).
-- See docs/plans/public-developer-api.md for the locked spec.
--
-- All three tables live in `private` because they hold user-scoped credentials
-- (CLAUDE.md convention #8: anything that holds an account, an email, a
-- payment, a session token, a saved query, or user-submitted content).
-- The redistributable public dump (cli/sovpro db public-dump) cannot
-- pull them in by construction.
--
-- Token shape (minted by services/api/src/lib/api-key-token.ts):
--   cpd_<env>_<22-char-base62-random>_<6-char-checksum>
-- where <env> is "live" or "test" so test/live tokens can't accidentally
-- cross-environments (Stripe lesson from the 2026-05-05 live-mode deploy).
-- Storage discipline: only `prefix` (cpd_<env>_<random>) is stored
-- plaintext; the full token is HMAC-SHA256'd with API_KEY_PEPPER and
-- stored as `token_hash`. Lookup is O(1) on (prefix) — the prefix index
-- gates the hash comparison so we don't seq-scan the table.

CREATE TABLE IF NOT EXISTS private.api_keys (
  id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         uuid        NOT NULL REFERENCES private.users(id) ON DELETE CASCADE,
  -- Plaintext prefix, e.g. "cpd_live_abc123XYZ_def4". Indexed (NOT unique
  -- — we partial-unique on (prefix) WHERE revoked_at IS NULL below so a
  -- rotated/revoked key can theoretically share a prefix with a fresh
  -- one without colliding; in practice the random body makes this
  -- vanishingly unlikely).
  prefix          text        NOT NULL,
  -- HMAC-SHA256(API_KEY_PEPPER, full_token). Bytea, not text.
  token_hash      bytea       NOT NULL,
  -- User-supplied label so the keys page can show "production worker",
  -- "personal cli", etc. Required and trimmed at the API layer.
  name            text        NOT NULL,
  -- Tier governs rate limits (see services/api/src/middleware/api-rate-limit.ts).
  -- For phase 1a only `free` is reachable from the self-service flow;
  -- dev/pro require Stripe subscription wiring (phase 1b).
  tier            text        NOT NULL DEFAULT 'free'
                  CHECK (tier IN ('free', 'dev', 'pro')),
  -- Capability scopes. Phase 1a hard-codes ['read:public']. read:bulk
  -- (Parquet/CSV exports) is reserved for v1.1.
  scopes          text[]      NOT NULL DEFAULT ARRAY['read:public']::text[],
  -- Optional CIDR allowlist (phase 1b enforcement). Schema lives here so
  -- a future migration doesn't need to add it.
  allowed_cidrs   cidr[],
  -- Throttled write — at most once per key per minute (in-process LRU
  -- in the auth middleware). Used by the /me/api-keys list page.
  last_used_at    timestamptz,
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),
  -- Optional natural expiry. NULL = never expires.
  expires_at      timestamptz,
  -- Soft-delete on revoke. Auth middleware checks this NULL.
  revoked_at      timestamptz,
  -- Set by /me/api-keys/:id/rotate on the NEW key, pointing at the
  -- rotated-out predecessor. Lets the keys page show "rotated from prefix
  -- cpd_live_xxx" without joining elsewhere.
  rotated_from_id uuid        REFERENCES private.api_keys(id) ON DELETE SET NULL,
  -- 24h grace window on the OLD key after a rotation. While set in the
  -- future, the old key continues to authenticate; once past, the auth
  -- middleware treats it as revoked.
  grace_until     timestamptz
);

CREATE INDEX IF NOT EXISTS idx_api_keys_user_id
  ON private.api_keys (user_id);
CREATE INDEX IF NOT EXISTS idx_api_keys_prefix
  ON private.api_keys (prefix);
CREATE INDEX IF NOT EXISTS idx_api_keys_active
  ON private.api_keys (user_id) WHERE revoked_at IS NULL;

-- Touch trigger reuses the existing public.touch_updated_at function.
DROP TRIGGER IF EXISTS trg_api_keys_touch ON private.api_keys;
CREATE TRIGGER trg_api_keys_touch
  BEFORE UPDATE ON private.api_keys
  FOR EACH ROW EXECUTE FUNCTION public.touch_updated_at();


CREATE TABLE IF NOT EXISTS private.api_key_events (
  id           uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  api_key_id   uuid        NOT NULL REFERENCES private.api_keys(id) ON DELETE CASCADE,
  event_type   text        NOT NULL
               CHECK (event_type IN ('created', 'rotated', 'revoked',
                                     'rate_limited', 'quota_exceeded')),
  -- Event-specific context. e.g. {"endpoint": "/api/public/v1/coverage",
  -- "limit": 60, "window": "1h"} for rate_limited rows.
  metadata     jsonb       NOT NULL DEFAULT '{}'::jsonb,
  created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_api_key_events_key_created
  ON private.api_key_events (api_key_id, created_at DESC);


-- Daily usage rollup. Schema lives here so phase 1c's writer can land
-- without a migration. Phase 1a does NOT write to this table (no
-- analytics surface yet to consume it); the rate-limit middleware tracks
-- hourly buckets in @fastify/rate-limit's in-memory store only.
CREATE TABLE IF NOT EXISTS private.api_usage_daily (
  api_key_id      uuid        NOT NULL REFERENCES private.api_keys(id) ON DELETE CASCADE,
  date            date        NOT NULL,
  request_count   integer     NOT NULL DEFAULT 0,
  -- Reserved for /search/speeches-class endpoints in phase 1b that should
  -- count toward a separate quota.
  expensive_count integer     NOT NULL DEFAULT 0,
  bytes_returned  bigint,
  PRIMARY KEY (api_key_id, date)
);
