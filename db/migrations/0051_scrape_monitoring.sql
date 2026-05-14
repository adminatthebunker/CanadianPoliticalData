-- Scrape monitoring schema: paid, user-billed Apify scrapes of monitored
-- politicians' social accounts.
--
-- Three pieces in one migration:
--
-- 1. Extend private.saved_searches with six scrape-related columns.
--    saved_searches already encodes "user is monitoring this politician"
--    when filter_payload.politician_ids = [X]. We layer scrape-monitoring
--    onto the same row instead of inventing a parallel subscription
--    table. One subscription row covers both speech-alerts AND
--    social-content scrapes for that politician.
--
-- 2. Create private.scrape_jobs — one row per (scheduled) scrape attempt.
--    Mirrors private.report_jobs in shape:
--       hold_ledger_id  -> credit_ledger row in state='held'
--       status          -> queued/running/succeeded/failed/cancelled/refunded
--    The (kind='scrape_hold', reference_id=scrape_jobs.id::text) pair is
--    covered by the existing uniq_credit_ledger_kind_ref partial unique
--    index from 0033 for ledger-side dedup.
--
-- 3. Create public.social_posts — upstream-public post content. Lives in
--    `public` because the posts themselves are not PII (a tweet is a
--    tweet). For v1 the API filters to subscriber-only via an EXISTS
--    join against private.scrape_jobs at query time — the visibility
--    gate is in the SQL, not the client. v2 (post-governance-docs)
--    flips that to public-read.
--
--    The scrape_job_id column is intentionally NOT a foreign key (it
--    crosses the private<->public schema boundary, and the link "user
--    paid for this scrape" must stay isolated to `private`). It's a
--    logical reference for audit / re-running, nothing more.

-- ── 1. Extend saved_searches ──────────────────────────────────────────

ALTER TABLE private.saved_searches
  ADD COLUMN IF NOT EXISTS scrape_platforms        TEXT[] NOT NULL DEFAULT '{}',
  ADD COLUMN IF NOT EXISTS scrape_cadence          TEXT   NOT NULL DEFAULT 'none'
       CHECK (scrape_cadence IN ('none','weekly','monthly','quarterly')),
  ADD COLUMN IF NOT EXISTS scrape_last_run_at      TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS scrape_next_run_at      TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS scrape_attribute_handle TEXT,
  ADD COLUMN IF NOT EXISTS scrape_paused_reason    TEXT;

-- Dispatcher's hot path: rows that are due and not paused.
CREATE INDEX IF NOT EXISTS idx_saved_searches_scrape_due
  ON private.saved_searches (scrape_next_run_at)
  WHERE scrape_cadence <> 'none' AND scrape_paused_reason IS NULL;

-- ── 2. scrape_jobs ────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS private.scrape_jobs (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id           UUID NOT NULL REFERENCES private.users(id),
  saved_search_id   UUID REFERENCES private.saved_searches(id) ON DELETE SET NULL,
  politician_id     UUID NOT NULL REFERENCES public.politicians(id),
  platform          TEXT NOT NULL CHECK (platform IN (
    'twitter','bluesky','instagram','mastodon',
    'tiktok','threads','facebook'
  )),
  status            TEXT NOT NULL DEFAULT 'queued'
                    CHECK (status IN ('queued','running','succeeded','failed','cancelled','refunded')),
  trigger_source    TEXT NOT NULL DEFAULT 'subscription'
                    CHECK (trigger_source IN ('subscription','admin','user_oneshot')),
  apify_actor       TEXT,
  apify_run_id      TEXT,
  dataset_id        TEXT,
  estimated_credits INTEGER NOT NULL CHECK (estimated_credits >= 0),
  hold_ledger_id    UUID REFERENCES private.credit_ledger(id),
  result_count      INTEGER,
  cost_usd_apify    NUMERIC(10,4),
  error             TEXT,
  claimed_at        TIMESTAMPTZ,
  started_at        TIMESTAMPTZ,
  finished_at       TIMESTAMPTZ,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TRIGGER trg_scrape_jobs_touch BEFORE UPDATE ON private.scrape_jobs
  FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

CREATE INDEX IF NOT EXISTS idx_scrape_jobs_user_time
  ON private.scrape_jobs (user_id, created_at DESC);

-- Worker claim hot path.
CREATE INDEX IF NOT EXISTS idx_scrape_jobs_queue
  ON private.scrape_jobs (created_at)
  WHERE status IN ('queued','running');

CREATE INDEX IF NOT EXISTS idx_scrape_jobs_pol_platform
  ON private.scrape_jobs (politician_id, platform, finished_at DESC);

-- ── 3. social_posts ───────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.social_posts (
  id            BIGSERIAL PRIMARY KEY,
  politician_id UUID NOT NULL REFERENCES public.politicians(id) ON DELETE CASCADE,
  platform      TEXT NOT NULL,
  post_id       TEXT NOT NULL,
  posted_at     TIMESTAMPTZ,
  text          TEXT,
  url           TEXT,
  media_urls    TEXT[],
  engagement    JSONB,
  raw           JSONB,
  scraped_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  scrape_job_id UUID,
  UNIQUE (platform, post_id)
);

CREATE INDEX IF NOT EXISTS idx_social_posts_pol_time
  ON public.social_posts (politician_id, posted_at DESC);

CREATE INDEX IF NOT EXISTS idx_social_posts_engagement
  ON public.social_posts USING GIN (engagement);
