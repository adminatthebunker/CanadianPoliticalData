-- 0062 — local postal-code geocode, replacing the last Open North runtime call.
--
-- Context: docs/research/boundaries/geocoding.md.
--
-- Until now `resolvePostcode()` (services/api/src/lib/postcode.ts) fetched every
-- postal-code centroid from represent.opennorth.ca. That host has been down since
-- 2026-08-07 (TLS cert expired + origin 502), and `postcode_cache` held **8 rows**,
-- so the stale-while-revalidate fallback was decorative: every uncached postcode
-- returned 503. This table removes the dependency.
--
-- Source: Statistics Canada **National Address Register**, catalogue 46-26-0002,
-- under the Statistics Canada Open Licence — which grants the explicit right to
-- "use, reproduce, publish, freely distribute, or sell" and to sublicence. This
-- matters because the alternatives are not open: PCCF is discontinued and
-- DLI-restricted, PCFRF costs $892/yr and is Canada Post co-distributed (and its
-- last issue is keyed to the *superseded* 2013 representation order), and
-- Geocoder.ca's dataset is commercial.
--
-- Derivation: join Addresses/Address_<PR>.csv to Locations/Location_<PR>.csv on
-- LOC_GUID, group by MAIL_POSTAL_CODE, average the WGS84 coordinates. Coordinates
-- are blockface centroids (BG_LATITUDE/BG_LONGITUDE) where available, falling back
-- to the building representative point (BF_REPPOINT_*) — 17.2% of Ontario location
-- rows carry only the latter, and discarding them costs 12.9% of address rows.
--
-- ⚠ Known and accepted coverage gap. NAR is a register of **civic addresses**, so
-- postal codes with no civic address are absent: PO-box-only codes, rural-route-only
-- codes, and large-volume-receiver / government codes. `K1A 0A6` (House of Commons)
-- has zero NAR rows, for example. Estimated national coverage is 73–92% of active
-- postal codes. The resolver therefore keeps a layered lookup rather than treating
-- this table as complete — see `postcode_cache`, retained as an override layer.
--
-- ⚠ This is NOT a redistribution of Canada Post's PCAD. Postal codes here are an
-- attribute of StatCan's own openly-licensed address register.
--
-- Forward-only. Apply with:
--   docker exec -i sw-db psql -U sw -d sovereignwatch -v ON_ERROR_STOP=1 \
--     < db/migrations/0062_postcode_centroids.sql

BEGIN;

CREATE TABLE IF NOT EXISTS public.postcode_centroids (
    -- Normalized: uppercase, no spaces or hyphens, exactly 6 characters.
    -- Matches the key convention already used by public.postcode_cache.
    postcode        TEXT PRIMARY KEY CHECK (postcode ~ '^[A-Z][0-9][A-Z][0-9][A-Z][0-9]$'),
    lat             DOUBLE PRECISION NOT NULL CHECK (lat BETWEEN 41 AND 84),
    lng             DOUBLE PRECISION NOT NULL CHECK (lng BETWEEN -142 AND -52),
    -- How many civic address points were averaged. A high count is a genuine
    -- centroid; count = 1 is a single-address code and positionally weaker.
    address_points  INTEGER NOT NULL CHECK (address_points > 0),
    province        TEXT,
    source          TEXT NOT NULL DEFAULT 'statcan-nar',
    -- NAR release identifier, e.g. '202606'. Lets a re-ingest of a newer vintage
    -- be distinguished, and makes staleness measurable.
    source_vintage  TEXT,
    built_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE public.postcode_centroids IS
    'Postal code -> WGS84 centroid, derived from the StatCan National Address '
    'Register (cat. 46-26-0002, Statistics Canada Open Licence). Primary geocode '
    'for the who-represents-me lookup. Coverage is ~73-92% of active postal codes; '
    'PO-box-only, rural-route-only and government codes are absent by construction. '
    'Rebuilt wholesale by the scanner command `ingest-nar-postcodes`.';

-- FSA prefix lookup for the 3-character fallback path. The API derives an FSA
-- answer from the member postcodes it does hold rather than from an FSA polygon,
-- so this index is on the hot path, not a convenience.
CREATE INDEX IF NOT EXISTS idx_postcode_centroids_fsa
    ON public.postcode_centroids (left(postcode, 3));

CREATE INDEX IF NOT EXISTS idx_postcode_centroids_built_at
    ON public.postcode_centroids (built_at);

-- `postcode_cache` (migration 0055) is RETAINED, with its role changed. It was the
-- Open North SWR cache; it is now the override / last-resort layer beneath the NAR
-- table, holding codes NAR cannot supply. Its `source` column already anticipated a
-- second populator ("in case we ever add a second source (StatCan PCCF, e.g.)").
COMMENT ON TABLE public.postcode_cache IS
    'Secondary postal-code geocode layer. Formerly the Open North SWR cache; since '
    'migration 0062 it sits BENEATH public.postcode_centroids and holds codes the '
    'NAR cannot supply (PO-box-only, rural-route-only, government codes such as '
    'K1A 0A6). Rows sourced ''opennorth'' are historical and are no longer refreshed '
    'from upstream.';

COMMIT;

-- ── Verification (run after the ingest, not after this migration) ───────────
-- SELECT count(*) FROM postcode_centroids;                       -- expect ~650k-850k
-- SELECT province, count(*) FROM postcode_centroids GROUP BY 1 ORDER BY 2 DESC;
-- SELECT count(*) FROM postcode_centroids WHERE substr(postcode,2,1) = '0';  -- rural
-- SELECT round(avg(address_points),1), max(address_points) FROM postcode_centroids;
