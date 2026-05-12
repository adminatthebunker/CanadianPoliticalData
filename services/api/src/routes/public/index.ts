import type { FastifyInstance, FastifyReply, FastifyRequest } from "fastify";
import { z } from "zod";
import { query, queryOne } from "../../db.js";
import { optionalApiKey } from "../../middleware/api-key-auth.js";
import { publicRateLimitConfig } from "../../middleware/api-rate-limit.js";
import { resolvePhotoUrl } from "../../lib/photos.js";

/**
 * Public developer API surface (/api/public/v1/*).
 *
 * Phase 1a-iii: three read-only endpoints mirroring the internal v1
 * surface for the safest data — public-already coverage stats,
 * politician detail, and the jurisdiction-sources rollup.
 *
 * Auth posture: optionalApiKey at plugin level so the rate-limit
 * middleware can distinguish authenticated free-tier (60/hr per key)
 * from anonymous IP fallback (30/hr). Phase 1b will introduce
 * routes that require an API key (paid tiers + /search/* surface).
 *
 * CORS: permissive (`origin: '*'`) — public dataset, no credentials
 * involved. The internal /api/v1/* surface keeps its restricted CORS
 * + cookie-credentials posture; this is a parallel tree on purpose.
 *
 * Schema source of truth: each endpoint's response shape mirrors its
 * internal /api/v1 sibling (see services/api/src/routes/coverage.ts
 * and services/api/src/routes/politicians.ts:442-484). Phase 1c will
 * fold these into the OpenAPI emission via fastify-type-provider-zod.
 */

const coverageQuery = z.object({
  status: z.enum(["live", "partial", "blocked", "none"]).optional(),
});

interface CoverageRow {
  jurisdiction: string;
  legislature_name: string;
  seats: number | null;
  bills_status: string;
  hansard_status: string;
  votes_status: string;
  committees_status: string;
  bills_difficulty: number | null;
  hansard_difficulty: number | null;
  votes_difficulty: number | null;
  committees_difficulty: number | null;
  blockers: string | null;
  notes: string | null;
  source_urls: Record<string, unknown>;
  bills_count: number;
  speeches_count: number;
  votes_count: number;
  politicians_count: number;
  last_verified_at: string | null;
  updated_at: string;
}

export default async function publicV1Routes(app: FastifyInstance) {
  // Permissive CORS via hook (can't re-register @fastify/cors — it
  // refuses double-registration). Public routes are bearer-token-
  // authenticated, not cookie-authenticated; a cross-origin caller
  // with a Bearer token is the entire point. credentials: false on
  // purpose, so wildcard origin is browser-accepted.
  app.addHook("onSend", async (req, reply, _payload) => {
    reply.header("Access-Control-Allow-Origin", "*");
    reply.header("Access-Control-Allow-Methods", "GET, OPTIONS");
    reply.header(
      "Access-Control-Allow-Headers",
      "Authorization, Content-Type",
    );
    // Don't override Vary — the global cors plugin already sets it on
    // /api/v1/* which doesn't reach here, and our wildcard doesn't
    // depend on the request Origin.
  });
  // Cheap OPTIONS preflight responder so browsers don't get a 404.
  app.options("/*", async (_req, reply) => {
    reply.code(204).send();
  });

  // optionalApiKey runs at onRequest (not preHandler) so req.apiKey is
  // populated BEFORE @fastify/rate-limit's per-route keyGenerator/max
  // resolver fires — otherwise authed callers would get the anonymous
  // rate limit. The performance cost is negligible: optionalApiKey is
  // a no-op when no Bearer header is present.
  app.addHook("onRequest", optionalApiKey);

  // ── GET /api/public/v1/coverage ───────────────────────────────
  // Mirror of internal /api/v1/coverage. Response shape includes a
  // small summary rollup so callers don't need a second query for
  // headline counts.
  app.get(
    "/coverage",
    { config: { rateLimit: publicRateLimitConfig } },
    async (req: FastifyRequest, reply: FastifyReply) => {
      const parsed = coverageQuery.safeParse(req.query);
      if (!parsed.success) return reply.badRequest(parsed.error.message);
      const { status } = parsed.data;

      const rows = await query<CoverageRow>(
        `SELECT jurisdiction, legislature_name, seats,
                bills_status, hansard_status, votes_status, committees_status,
                bills_difficulty, hansard_difficulty, votes_difficulty, committees_difficulty,
                blockers, notes, source_urls,
                bills_count, speeches_count, votes_count, politicians_count,
                last_verified_at, updated_at
           FROM jurisdiction_sources
          ${status ? "WHERE bills_status = $1" : ""}
          ORDER BY
            CASE jurisdiction WHEN 'federal' THEN 0 ELSE 1 END,
            jurisdiction`,
        status ? [status] : [],
      );
      const summary = {
        total: rows.length,
        live:    rows.filter(r => r.bills_status === "live").length,
        partial: rows.filter(r => r.bills_status === "partial").length,
        blocked: rows.filter(r => r.bills_status === "blocked").length,
        none:    rows.filter(r => r.bills_status === "none").length,
      };
      reply.header("Cache-Control", "public, max-age=300");
      return { jurisdictions: rows, summary };
    },
  );

  // ── GET /api/public/v1/jurisdiction-sources ───────────────────
  // Flat per-jurisdiction list. Same underlying table as /coverage
  // but without the summary rollup — for callers that want raw rows
  // to render their own dashboard.
  app.get(
    "/jurisdiction-sources",
    { config: { rateLimit: publicRateLimitConfig } },
    async (_req: FastifyRequest, reply: FastifyReply) => {
      const rows = await query<CoverageRow>(
        `SELECT jurisdiction, legislature_name, seats,
                bills_status, hansard_status, votes_status, committees_status,
                bills_difficulty, hansard_difficulty, votes_difficulty, committees_difficulty,
                blockers, notes, source_urls,
                bills_count, speeches_count, votes_count, politicians_count,
                last_verified_at, updated_at
           FROM jurisdiction_sources
          ORDER BY
            CASE jurisdiction WHEN 'federal' THEN 0 ELSE 1 END,
            jurisdiction`,
        [],
      );
      reply.header("Cache-Control", "public, max-age=300");
      return { items: rows };
    },
  );

  // ── GET /api/public/v1/politicians/:id ────────────────────────
  // Mirror of internal /api/v1/politicians/:id. Same payload shape:
  // politician row + active websites (with latest infrastructure scan)
  // + constituency boundary GeoJSON (when constituency_id is set).
  app.get<{ Params: { id: string } }>(
    "/politicians/:id",
    { config: { rateLimit: publicRateLimitConfig } },
    async (req, reply) => {
      const { id } = req.params;
      if (!/^[0-9a-f-]{36}$/i.test(id)) return reply.notFound();

      const pol = await queryOne<Record<string, unknown>>(
        `SELECT p.*,
                (SELECT MAX(ended_at)
                   FROM politician_terms
                  WHERE politician_id = p.id
                    AND ended_at IS NOT NULL) AS latest_term_ended_at
           FROM politicians p
          WHERE p.id = $1`,
        [id],
      );
      if (!pol) return reply.notFound();
      (pol as Record<string, unknown>).photo_url = resolvePhotoUrl(
        pol as { photo_path?: string | null; photo_url?: string | null },
      );

      const websites = await query(
        `
        SELECT w.*, s.ip_country, s.ip_city, s.ip_latitude, s.ip_longitude,
               s.hosting_provider, s.hosting_country, s.sovereignty_tier,
               s.cdn_detected, s.cms_detected, s.scanned_at
        FROM websites w
        LEFT JOIN LATERAL (
          SELECT * FROM infrastructure_scans WHERE website_id = w.id
          ORDER BY scanned_at DESC LIMIT 1
        ) s ON true
        WHERE w.owner_type='politician' AND w.owner_id=$1 AND w.is_active=true
        ORDER BY w.label
        `, [id],
      );

      const boundary = (pol as { constituency_id?: string }).constituency_id
        ? await queryOne(
            `SELECT constituency_id, name, level, ST_AsGeoJSON(boundary_simple)::jsonb AS boundary_geojson,
                    ST_X(centroid) AS centroid_lng, ST_Y(centroid) AS centroid_lat
               FROM constituency_boundaries WHERE constituency_id = $1`,
            [(pol as { constituency_id: string }).constituency_id])
        : null;

      reply.header("Cache-Control", "public, max-age=60");
      return { politician: pol, websites, boundary };
    },
  );
}
