-- Profile-cache columns on politician_socials and scrape_kind discriminator
-- on private.scrape_jobs.
--
-- Why:
--   * Pre-flight estimates need cached account metadata (lifetime post
--     count, posting velocity, last post date) so the cost calculator
--     can suggest a sensible cadence without re-calling the platform on
--     every UI render. politician_socials already has follower_count;
--     we extend it rather than introduce a new table.
--   * scrape_jobs now serves three job kinds — monitoring (cadence-driven,
--     recurring), preflight (cheap, returns profile data), archive
--     (volume-priced, one-shot deep history). trigger_source describes
--     *who* triggered (subscription / admin / user_oneshot); scrape_kind
--     describes *what work* — orthogonal axes.
--
-- The profile_metadata JSONB is the catch-all for actor-specific fields
-- (Twitter blue verification, Mastodon instance, etc.); the columned
-- fields above it are the ones we query against.

ALTER TABLE public.politician_socials
  ADD COLUMN IF NOT EXISTS lifetime_post_count       INTEGER,
  ADD COLUMN IF NOT EXISTS posting_velocity_per_week NUMERIC(10,2),
  ADD COLUMN IF NOT EXISTS last_post_at              TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS profile_metadata          JSONB,
  ADD COLUMN IF NOT EXISTS last_profile_check_at     TIMESTAMPTZ;

-- Partial index: pre-flight worker watermark. Pulls rows we haven't
-- probed in a while (or have never probed) for opportunistic refresh.
CREATE INDEX IF NOT EXISTS idx_politician_socials_profile_stale
  ON public.politician_socials (last_profile_check_at NULLS FIRST)
  WHERE is_live IS NOT FALSE;

ALTER TABLE private.scrape_jobs
  ADD COLUMN IF NOT EXISTS scrape_kind TEXT NOT NULL DEFAULT 'monitoring'
       CHECK (scrape_kind IN ('monitoring','preflight','archive'));

CREATE INDEX IF NOT EXISTS idx_scrape_jobs_user_kind
  ON private.scrape_jobs (user_id, scrape_kind, created_at DESC);
