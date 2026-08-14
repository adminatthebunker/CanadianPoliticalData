import type { FastifyInstance } from "fastify";
import { query } from "../db.js";
import { resolvePhotoUrl } from "../lib/photos.js";
import { resolvePostcode, PostcodeUpstreamError } from "../lib/postcode.js";
import { politicianIdsForPostcode } from "../lib/postcode-reps.js";

/**
 * /api/v1/lookup/postcode/:code
 *
 * Local-first "who represents me": resolve the postcode to a centroid
 * via lib/postcode.ts (30-day SWR cache over Open North, table
 * public.postcode_cache), then point-in-polygon against our own
 * constituency_boundaries mirror and join politicians on
 * constituency_id (same `{set}/{slug}` scheme on both tables — an
 * exact join; name+level matching is only the fallback for rows
 * without a constituency_id).
 *
 * This replaced a per-request live call to Open North's
 * /postcodes/:code representatives endpoint (2026-08-02): the only
 * remaining upstream dependency is the cached centroid geocode, so an
 * Open North outage now degrades to cache_stale instead of a 503.
 * Tracked in docs/plans/sovereignty-runtime-deps.md.
 *
 * Tradeoff vs the old passthrough: rep coverage is now bounded by our
 * own politicians/boundaries mirror (which is the product anyway), and
 * border postcodes resolve by centroid rather than Open North's
 * postcode→district concordance — a handful of straddling postcodes
 * may map to the neighbouring riding.
 */

const POSTAL_RE = /^[A-Za-z]\d[A-Za-z][ -]?\d[A-Za-z]\d$/;

const LEVEL_ORDER: Record<string, number> = {
  federal: 0,
  provincial: 1,
  municipal: 2,
};

interface MatchedPolitician {
  id: string;
  name: string;
  party: string | null;
  elected_office: string | null;
  level: string;
  constituency_name: string | null;
  email: string | null;
  photo_path: string | null;
  photo_url: string | null;
  worst_tier: number | null;
  best_tier: number | null;
  websites: number;
  canadian: number;
  cdn: number;
  us: number;
  foreign: number;
}

export default async function lookupRoutes(app: FastifyInstance) {
  app.get("/postcode/:code", async (req, reply) => {
    const { code } = req.params as { code: string };
    if (!POSTAL_RE.test(code)) {
      return reply.badRequest("Invalid Canadian postal code (e.g. K1A 0A6)");
    }

    let resolved;
    try {
      resolved = await resolvePostcode(code);
    } catch (err) {
      if (err instanceof PostcodeUpstreamError) {
        if (err.kind === "not_found") {
          return reply.notFound("Postal code not found");
        }
        if (err.kind === "invalid") {
          return reply.badRequest("Invalid Canadian postal code (e.g. K1A 0A6)");
        }
        app.log.warn({ code, err: err.message }, "postcode resolution unavailable");
        return reply.serviceUnavailable("Postal code lookup service is unreachable");
      }
      throw err;
    }
    // PIP + politician join now lives in lib/postcode-reps.ts, shared with
    // the search routes' `postcode` filter — so "reps the drawer shows" is
    // provably the same set "search filters by". The enrichment
    // (websites / scan summary) stays local to this route.
    const repIds = await politicianIdsForPostcode(code);
    const matched = repIds.length === 0 ? [] : await query<MatchedPolitician>(
      `SELECT p.id, p.name, p.party, p.elected_office, p.level,
              p.constituency_name, p.email,
              p.photo_path, p.photo_url,
              MAX(s.sovereignty_tier) AS worst_tier,
              MIN(s.sovereignty_tier) AS best_tier,
              COUNT(DISTINCT w.id) FILTER (WHERE w.label <> 'shared_official')::int AS websites,
              COUNT(*) FILTER (WHERE s.sovereignty_tier IN (1,2))::int AS canadian,
              COUNT(*) FILTER (WHERE s.sovereignty_tier = 3)::int AS cdn,
              COUNT(*) FILTER (WHERE s.sovereignty_tier = 4)::int AS us,
              COUNT(*) FILTER (WHERE s.sovereignty_tier = 5)::int AS foreign
         FROM politicians p
         LEFT JOIN websites w ON w.owner_type='politician' AND w.owner_id=p.id AND w.is_active
                              AND COALESCE(w.label,'') <> 'shared_official'
         LEFT JOIN LATERAL (
           SELECT * FROM infrastructure_scans WHERE website_id = w.id
           ORDER BY scanned_at DESC LIMIT 1
         ) s ON true
        WHERE p.id = ANY($1::uuid[])
        GROUP BY p.id`,
      [repIds],
    );

    matched.sort(
      (a, b) =>
        (LEVEL_ORDER[a.level] ?? 9) - (LEVEL_ORDER[b.level] ?? 9) ||
        a.name.localeCompare(b.name),
    );

    const enriched = await Promise.all(matched.map(async (p) => {
      const sites = await query<{
        url: string; hostname: string; label: string | null;
        tier: number | null; provider: string | null; country: string | null; city: string | null;
      }>(
        `SELECT w.url, w.hostname, w.label,
                s.sovereignty_tier AS tier, s.hosting_provider AS provider,
                s.ip_country AS country, s.ip_city AS city
         FROM websites w
         LEFT JOIN LATERAL (SELECT * FROM infrastructure_scans WHERE website_id=w.id
                             ORDER BY scanned_at DESC LIMIT 1) s ON true
         WHERE w.owner_type='politician' AND w.owner_id=$1 AND w.is_active
           AND COALESCE(w.label,'') <> 'shared_official'
         ORDER BY w.label`, [p.id],
      );

      return {
        politician_id: p.id,
        name: p.name,
        district: p.constituency_name ?? undefined,
        elected_office: p.elected_office ?? undefined,
        party: p.party ?? undefined,
        email: p.email ?? undefined,
        photo_url: resolvePhotoUrl({ photo_path: p.photo_path, photo_url: p.photo_url }),
        in_database: true,
        scan_summary: {
          websites: p.websites,
          canadian: p.canadian,
          cdn: p.cdn,
          us: p.us,
          foreign: p.foreign,
          worst_tier: p.worst_tier,
          best_tier: p.best_tier,
        },
        sites,
      };
    }));

    reply.header("cache-control", "public, max-age=600");
    reply.header("x-postcode-source", resolved.source);
    return {
      postal_code: resolved.postcode,
      representatives: enriched,
    };
  });
}
