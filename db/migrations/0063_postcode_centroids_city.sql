-- 0063 — postcode_centroids.city
--
-- Migration 0062 shipped the NAR-derived centroid table without a city name.
-- `ResolvedPostcode.city` is part of the public API response
-- (`GET /api/public/v1/postcodes/:postcode`, and the `/representatives`
-- variant), so dropping it when the Open North resolver is retired would be a
-- visible contract regression rather than an internal change.
--
-- NAR carries `MAIL_MUN_NAME` on the Address record. A postal code can span more
-- than one municipality, so the loader stores the **modal** value — the
-- municipality naming the most civic addresses in that code — rather than an
-- arbitrary first-seen one.
--
-- Forward-only (0062 is already applied; per CLAUDE.md an applied migration is
-- never edited). Apply with:
--   docker exec -i sw-db psql -U sw -d sovereignwatch -v ON_ERROR_STOP=1 \
--     < db/migrations/0063_postcode_centroids_city.sql

BEGIN;

ALTER TABLE public.postcode_centroids
    ADD COLUMN IF NOT EXISTS city TEXT;

COMMENT ON COLUMN public.postcode_centroids.city IS
    'Modal MAIL_MUN_NAME across the civic addresses sharing this postal code. '
    'Modal rather than first-seen because a code can span municipalities.';

COMMIT;
