-- v3 — scrape_attribute_url + linkable attribution
--
-- Adds the optional URL companion to scrape_attribute_handle. When set,
-- the public posts API surfaces it as funded_by_url and the politician-
-- profile *Recent posts* tab renders the attribution handle as a link
-- with rel="nofollow noopener external" target="_blank".
--
-- Validation: this column is unconstrained at the DB layer. The API
-- zod schema enforces a basic https://... check; a malformed URL is
-- rejected with 400 rather than persisted. Operator-review is the
-- abuse mechanism, not a domain allowlist.
--
-- Backfill: the two existing rows attributed to "The Bunker Operations"
-- (the operator anchor row + the live Pascal Paradis subscription) get
-- their URL set to https://canadianpoliticaldata.org so the 41
-- already-attributed posts become clickable links on deploy.

ALTER TABLE private.saved_searches
  ADD COLUMN IF NOT EXISTS scrape_attribute_url TEXT;

UPDATE private.saved_searches
   SET scrape_attribute_url = 'https://canadianpoliticaldata.org'
 WHERE scrape_attribute_handle = 'The Bunker Operations'
   AND scrape_attribute_url IS NULL;
