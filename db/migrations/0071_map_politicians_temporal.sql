-- 0071 — map_politicians: add the temporal predicate. A read path the
--        TypeScript fix could not reach, found by Quebec going two-generational.
--
-- ★ HOW THIS SURFACED
-- -------------------
-- `0070` had just committed cleanly when its trailing `SELECT refresh_map_views()`
-- failed:
--
--     ERROR: could not create unique index "idx_mp_unique"
--     DETAIL: Key (politician_id, website_id)=(69468d66-…, 55577172-…) is duplicated.
--
-- The cause is one line in the view:
--
--     LEFT JOIN constituency_boundaries cb ON cb.constituency_id = p.constituency_id
--
-- — with no date filter. `constituency_id` is generation-INDEPENDENT by design;
-- the unique key is (constituency_id, boundaries_version). So the moment Quebec
-- held two generations, every politician in one of the 108 districts that carry
-- through from 2017 to 2026 matched TWO boundary rows, and the view emitted two
-- otherwise-identical rows per website. `idx_mp_unique` caught it.
--
-- ⓘ `services/api/src/lib/boundary-temporal.ts` audited nine drifted read paths
-- on 2026-08-18 and fixed them all. This is a TENTH, and it was invisible to
-- that audit because it is not TypeScript — it lives inside a materialized view
-- in the database. A convention enforced by grepping application code cannot see
-- SQL that ships in a migration.
--
-- ★ The index did its job. This is the counter-example to Fort Erie: there, a
-- CHECK constraint fired correctly and `_ingest_set`'s blanket `except Exception`
-- turned the rejection into a silent absence. Here the constraint fired and
-- nothing swallowed it, so a latent bug became a loud, located failure the first
-- time it could possibly matter.
--
-- ⚠ CURRENT_DATE inside a matview is evaluated AT REFRESH, not at query time. The
-- view is therefore correct only as of its last refresh. `refresh-views` is
-- scheduled daily at 23:55, so Quebec's 2026-08-29 switch reaches the map within
-- 24 hours. That is acceptable for a map layer and NOT acceptable for a lookup —
-- which is why the lookup paths query the table directly rather than this view.
--
-- Recreated rather than altered: CREATE OR REPLACE does not exist for
-- materialized views. All six indexes are restored below, unchanged.
--
-- Forward-only. Apply with:
--   docker exec -i sw-db psql -U sw -d sovereignwatch -v ON_ERROR_STOP=1 \
--     < db/migrations/0071_map_politicians_temporal.sql

BEGIN;

DROP MATERIALIZED VIEW IF EXISTS map_politicians;

CREATE MATERIALIZED VIEW map_politicians AS
SELECT p.id AS politician_id,
    p.name,
    p.party,
    p.elected_office,
    p.level,
    p.province_territory,
    p.constituency_name,
    p.photo_url,
    cb.constituency_id,
    (st_asgeojson(cb.boundary_simple))::jsonb AS boundary_geojson,
    st_x(cb.centroid) AS constituency_lng,
    st_y(cb.centroid) AS constituency_lat,
    w.id AS website_id,
    w.url AS website_url,
    w.label AS website_label,
    w.hostname,
        CASE
            WHEN (COALESCE(w.label, ''::text) = 'shared_official'::text) THEN 'shared_official'::text
            WHEN ((w.hostname ~* '\.(libparl|liberal|conservative|conservativeeda|ndp|albertandp|ucp2023|unitedconservative|blocquebecois|greenparty|partiquebecois|pq)\.(ca|org|com|quebec)$'::text) OR (w.hostname ~* '^(libparl|liberal|conservative|conservativeeda|ndp|albertandp|ucp2023|unitedconservative|blocquebecois|greenparty|partiquebecois|pq)\.(ca|org|com|quebec)$'::text)) THEN 'party_managed'::text
            ELSE 'personal'::text
        END AS site_class,
    s.id AS scan_id,
    s.ip_country,
    s.ip_region,
    s.ip_city,
    s.ip_latitude AS server_lat,
    s.ip_longitude AS server_lng,
    s.ip_asn,
    s.ip_org,
    s.hosting_provider,
    s.hosting_country,
    s.datacenter_region,
    s.sovereignty_tier,
    s.cdn_detected,
    s.cms_detected,
    s.scanned_at
   FROM (((politicians p
     JOIN websites w ON (((w.owner_type = 'politician'::text) AND (w.owner_id = p.id) AND (w.is_active = true))))
     LEFT JOIN constituency_boundaries cb ON ((cb.constituency_id = p.constituency_id)
         -- ⛔ THE FIX. See the migration header.
         AND cb.effective_from <= CURRENT_DATE
         AND (cb.effective_to IS NULL OR cb.effective_to >= CURRENT_DATE)))
     LEFT JOIN LATERAL ( SELECT infrastructure_scans.id,
            infrastructure_scans.website_id,
            infrastructure_scans.scanned_at,
            infrastructure_scans.ip_addresses,
            infrastructure_scans.cname_chain,
            infrastructure_scans.nameservers,
            infrastructure_scans.mx_records,
            infrastructure_scans.ip_country,
            infrastructure_scans.ip_region,
            infrastructure_scans.ip_city,
            infrastructure_scans.ip_latitude,
            infrastructure_scans.ip_longitude,
            infrastructure_scans.ip_asn,
            infrastructure_scans.ip_org,
            infrastructure_scans.hosting_provider,
            infrastructure_scans.hosting_country,
            infrastructure_scans.datacenter_region,
            infrastructure_scans.sovereignty_tier,
            infrastructure_scans.cdn_detected,
            infrastructure_scans.cms_detected,
            infrastructure_scans.tls_issuer,
            infrastructure_scans.tls_subject,
            infrastructure_scans.tls_expiry,
            infrastructure_scans.tls_valid,
            infrastructure_scans.http_status,
            infrastructure_scans.http_server_header,
            infrastructure_scans.http_powered_by,
            infrastructure_scans.http_final_url,
            infrastructure_scans.duration_ms,
            infrastructure_scans.error,
            infrastructure_scans.raw_data
           FROM infrastructure_scans
          WHERE (infrastructure_scans.website_id = w.id)
          ORDER BY infrastructure_scans.scanned_at DESC
         LIMIT 1) s ON (true))
  WHERE ((p.is_active = true) AND (COALESCE(w.label, ''::text) <> 'shared_official'::text));

-- Restored exactly as they were before the drop.
CREATE INDEX idx_mp_class ON public.map_politicians USING btree (site_class);
CREATE INDEX idx_mp_level ON public.map_politicians USING btree (level);
CREATE INDEX idx_mp_party ON public.map_politicians USING btree (party);
CREATE INDEX idx_mp_province ON public.map_politicians USING btree (province_territory);
CREATE INDEX idx_mp_tier ON public.map_politicians USING btree (sovereignty_tier);
-- ★ The one that caught the bug. Also what REFRESH ... CONCURRENTLY requires.
CREATE UNIQUE INDEX idx_mp_unique ON public.map_politicians USING btree (politician_id, website_id);

DO $$
DECLARE dupes int; qc int;
BEGIN
    SELECT count(*) INTO dupes FROM (
        SELECT politician_id, website_id FROM map_politicians
         GROUP BY 1,2 HAVING count(*) > 1) d;
    IF dupes <> 0 THEN
        RAISE EXCEPTION '% duplicated (politician_id, website_id) pairs remain', dupes;
    END IF;

    -- Every QC politician in the view must resolve to at most one boundary.
    SELECT count(*) INTO qc FROM (
        SELECT politician_id FROM map_politicians
         WHERE province_territory = 'QC' AND level = 'provincial'
         GROUP BY 1 HAVING count(DISTINCT constituency_id) > 1) d;
    IF qc <> 0 THEN
        RAISE EXCEPTION '% QC politicians still match two generations', qc;
    END IF;

    RAISE NOTICE 'map_politicians rebuilt with the temporal predicate';
END $$;

COMMIT;

SELECT refresh_map_views();
