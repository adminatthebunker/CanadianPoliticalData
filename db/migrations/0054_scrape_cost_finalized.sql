-- v7a-2: async Apify cost finalization
--
-- Some Apify actors (notably apidojo/tweet-scraper) report
-- usageTotalUsd=0 in the sync run response and settle billing minutes
-- later. The worker writes a local estimate via
-- estimate_apify_cost_floor() so SCRAPE_DAILY_USD_CAP isn't toothless;
-- this column tracks whether we've gone back to fetch the real
-- usageTotalUsd from /v2/actor-runs/{id} once it settled.
--
-- Workflow: scrape_worker.main()'s outer loop runs a polling pass
-- every tick — for each succeeded row that has apify_run_id and isn't
-- finalized and finished_at < now() - 5 minutes, GETs the run record
-- and overwrites cost_usd_apify with the real number when it's > 0.
-- Sets the flag regardless (even Apify settling to 0 is a settled
-- value — Bluesky/Mastodon have apify_run_id NULL so they're not in
-- this query's scope).
--
-- The partial index is the hot path: the polling pass scans only
-- unfinalized rows.

ALTER TABLE private.scrape_jobs
  ADD COLUMN IF NOT EXISTS cost_usd_apify_finalized BOOLEAN NOT NULL DEFAULT false;

CREATE INDEX IF NOT EXISTS idx_scrape_jobs_cost_unfinalized
  ON private.scrape_jobs (finished_at)
  WHERE status = 'succeeded'
    AND apify_run_id IS NOT NULL
    AND cost_usd_apify_finalized = false;
