import type { FastifyInstance, FastifyRequest } from "fastify";
import { z } from "zod";
import {
  requireApiKey,
} from "../../middleware/api-key-auth.js";
import { requireTier } from "../../middleware/api-tier-gate.js";
import { publicRateLimitConfig } from "../../middleware/api-rate-limit.js";
import {
  withPublicTeiSlot,
  PublicSearchOverloadedError,
} from "../../lib/tei-semaphore.js";

/**
 * Public search endpoints (/api/public/v1/search/*).
 *
 * Six routes, two tiers of access:
 *
 *   PRO-tier (requires subscription, hits TEI for query embedding):
 *   - GET /search/speeches         — full search; mirror of internal /api/v1/search/speeches
 *   - GET /search/speeches/count   — count-only sibling
 *   - GET /search/facets           — aggregations over top-N
 *
 *   FREE-tier (no TEI, just lookup tables; rate-limited but accessible):
 *   - GET /search/sessions         — parliament/session catalog
 *   - GET /search/chunks/:id       — anchor-chunk lookup
 *   - GET /search/meta             — backfill-progress
 *
 * Implementation pattern: each handler proxies to the internal
 * /api/v1/search/* route via `app.inject`, which runs the request
 * through Fastify's in-process pipeline without going over the
 * network. This avoids 500+ lines of route-logic duplication —
 * the internal handlers remain the single source of truth for
 * search semantics, and behavior changes there propagate here for
 * free.
 *
 * For TEI-dependent routes, the entire inject is wrapped in
 * withPublicTeiSlot — the semaphore holds a slot while the
 * internal handler calls encodeQuery + executes the SQL. If the
 * queue exceeds capacity (active + pending > maxConcurrent +
 * maxQueue), we 503 immediately with Retry-After rather than
 * making the caller wait minutes.
 *
 * Auth: requireApiKey + requireTier('pro') on the three TEI routes;
 * inherited optionalApiKey from the parent plugin on the three
 * free-tier routes (so callers without a key get the anonymous
 * IP-bucket rate limit).
 */

// Forward whatever the caller sent as query/params straight through
// to the internal route. The internal route's zod schema does the
// actual validation; we don't re-validate here.

function buildQuery(req: FastifyRequest): string {
  const q = req.query as Record<string, unknown> | undefined;
  if (!q) return "";
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(q)) {
    if (value === undefined || value === null) continue;
    if (Array.isArray(value)) {
      for (const v of value) {
        if (v !== undefined && v !== null) params.append(key, String(v));
      }
    } else {
      params.append(key, String(value));
    }
  }
  const s = params.toString();
  return s ? `?${s}` : "";
}

interface ProxyOptions {
  app: FastifyInstance;
  internalUrl: string;
  /** When true, wrap the inject in the TEI semaphore. */
  needsTei: boolean;
}

async function proxyToInternal(
  req: FastifyRequest,
  reply: import("fastify").FastifyReply,
  opts: ProxyOptions,
) {
  const { app, internalUrl, needsTei } = opts;
  const url = `${internalUrl}${buildQuery(req)}`;

  const doInject = async () => {
    return app.inject({
      method: "GET",
      url,
      // Don't forward Authorization — internal routes are public-already
      // for the read-only endpoints we proxy, and the user's API key
      // would be meaningless to them.
    });
  };

  try {
    const res = needsTei ? await withPublicTeiSlot(doInject) : await doInject();
    // Pass through the body + status. Forward Cache-Control so
    // intermediate caches (CDN, browser) can still hit. Don't
    // forward Set-Cookie or auth-related headers.
    if (res.headers["cache-control"]) {
      reply.header("Cache-Control", res.headers["cache-control"]);
    }
    reply.code(res.statusCode);
    return res.json();
  } catch (err) {
    if (err instanceof PublicSearchOverloadedError) {
      reply.header("Retry-After", String(err.retryAfterSeconds));
      reply.code(err.statusCode);
      return {
        code: err.code,
        error: "Service Unavailable",
        message: err.message,
      };
    }
    throw err;
  }
}

// ── Schemas (input only — response shapes documented in mkdocs) ─────

const speechesQuery = z
  .object({
    q: z.string().max(500).optional(),
    anchor_chunk_id: z.string().regex(/^[0-9a-f-]{36}$/i).optional(),
    lang: z.enum(["en", "fr", "any"]).optional(),
    level: z.enum(["federal", "provincial", "municipal"]).optional(),
    province_territory: z.string().length(2).optional(),
    politician_ids: z.union([z.string().uuid(), z.array(z.string().uuid())]).optional(),
    party: z.string().optional(),
    from: z.string().regex(/^\d{4}-\d{2}-\d{2}$/).optional(),
    to: z.string().regex(/^\d{4}-\d{2}-\d{2}$/).optional(),
    exclude_presiding: z.union([z.boolean(), z.string()]).optional(),
    politician_active: z.enum(["active", "inactive"]).optional(),
    min_similarity: z.coerce.number().min(0).max(1).optional(),
    parliament_number: z.coerce.number().int().positive().optional(),
    session_number: z.coerce.number().int().positive().optional(),
    speech_type: z.union([z.string(), z.array(z.string())]).optional(),
    page: z.coerce.number().int().min(1).optional(),
    limit: z.coerce.number().int().min(1).max(50).optional(),
    group_by: z.enum(["timeline", "politician"]).optional(),
    per_group_limit: z.coerce.number().int().min(1).max(10).optional(),
    sort: z.enum(["mentions", "best_match", "avg_match", "keyword_hits"]).optional(),
    include_count: z.union([z.boolean(), z.enum(["true", "false"])]).optional(),
  })
  .passthrough();

const facetsQuery = z
  .object({
    q: z.string().max(500).optional(),
    anchor_chunk_id: z.string().regex(/^[0-9a-f-]{36}$/i).optional(),
    limit: z.coerce.number().int().min(10).max(500).optional(),
  })
  .passthrough();

const sessionsQuery = z.object({
  level: z.enum(["federal", "provincial", "municipal"]).optional(),
  province: z.string().length(2).optional(),
});

const chunkIdParam = z.object({
  id: z.string().regex(/^[0-9a-f-]{36}$/i),
});

export default async function publicV1SearchRoutes(app: FastifyInstance) {
  // Reach back up to the root app for inject — encapsulated `app` here
  // can also do inject (Fastify routes injection works against the
  // declaring instance and resolves URLs against the full route table).
  const root = app;

  // ── PRO-tier (TEI-dependent) ──────────────────────────────────

  app.get(
    "/search/speeches",
    {
      preHandler: [requireApiKey, requireTier("pro")],
      config: { rateLimit: publicRateLimitConfig },
      schema: {
        tags: ["Search (paid)"],
        summary: "Hybrid HNSW + BM25 semantic search over Hansard (PRO)",
        description:
          "Mirror of the internal /api/v1/search/speeches endpoint. " +
          "Pro-tier only — the embed step routes through a shared TEI " +
          "semaphore (max 2 concurrent + 6 queued; 503 with Retry-After " +
          "if the queue saturates). Same response shape as the internal " +
          "route (timeline mode by default; group_by=politician for " +
          "grouped). See /developers/rate-limiting for the semaphore.",
        querystring: speechesQuery,
      },
    },
    async (req, reply) => {
      return proxyToInternal(req, reply, {
        app: root,
        internalUrl: "/api/v1/search/speeches",
        needsTei: true,
      });
    },
  );

  app.get(
    "/search/speeches/count",
    {
      preHandler: [requireApiKey, requireTier("pro")],
      config: { rateLimit: publicRateLimitConfig },
      schema: {
        tags: ["Search (paid)"],
        summary: "Count-only sibling for /search/speeches (PRO)",
        description:
          "Returns { total, capped }. Capping kicks in at 10,000 + 1 " +
          "(HNSW LIMIT trick). Use alongside ?include_count=false on " +
          "/search/speeches to stage count off the hot path. Same " +
          "TEI semaphore as /search/speeches.",
        querystring: speechesQuery,
      },
    },
    async (req, reply) => {
      return proxyToInternal(req, reply, {
        app: root,
        internalUrl: "/api/v1/search/speeches/count",
        needsTei: true,
      });
    },
  );

  app.get(
    "/search/facets",
    {
      preHandler: [requireApiKey, requireTier("pro")],
      config: { rateLimit: publicRateLimitConfig },
      schema: {
        tags: ["Search (paid)"],
        summary: "Aggregations over the top-N candidate pool (PRO)",
        description:
          "Returns { analyzed_count, analysis_limit, chunk_ids, by_party, " +
          "by_politician, by_year, by_language, keyword_overlap, mode }. " +
          "Optional ?limit query (clamped [10, 500], default 200) sets " +
          "the candidate-pool size. Same TEI semaphore as /search/speeches.",
        querystring: facetsQuery,
      },
    },
    async (req, reply) => {
      return proxyToInternal(req, reply, {
        app: root,
        internalUrl: "/api/v1/search/facets",
        needsTei: true,
      });
    },
  );

  // ── FREE-tier (no TEI, lookup tables) ─────────────────────────

  app.get(
    "/search/sessions",
    {
      config: { rateLimit: publicRateLimitConfig },
      schema: {
        tags: ["Search (free)"],
        summary: "Parliament + session catalog (FREE)",
        description:
          "Returns { sessions: [{ parliament_number, session_number, " +
          "name, start_date, end_date }] }. Backs the cascading dropdown " +
          "on the search filter UI. Cache-Control: public, max-age=3600.",
        querystring: sessionsQuery,
      },
    },
    async (req, reply) => {
      return proxyToInternal(req, reply, {
        app: root,
        internalUrl: "/api/v1/search/sessions",
        needsTei: false,
      });
    },
  );

  app.get(
    "/search/chunks/:id",
    {
      config: { rateLimit: publicRateLimitConfig },
      schema: {
        tags: ["Search (free)"],
        summary: "Anchor-chunk lookup by UUID (FREE)",
        description:
          "Returns the chunk text + speech metadata + politician (if " +
          "resolved). 404 on missing or malformed id. Cache-Control: " +
          "public, max-age=60.",
        params: chunkIdParam,
      },
    },
    async (req, reply) => {
      const { id } = req.params as { id: string };
      return proxyToInternal(req, reply, {
        app: root,
        internalUrl: `/api/v1/search/chunks/${encodeURIComponent(id)}`,
        needsTei: false,
      });
    },
  );

  app.get(
    "/search/meta",
    {
      config: { rateLimit: publicRateLimitConfig },
      schema: {
        tags: ["Search (free)"],
        summary: "Backfill-progress meta (FREE)",
        description:
          "Returns { total_chunks, embedded_chunks, coverage }. Useful " +
          "for callers wanting to know what fraction of the corpus is " +
          "currently embedded + searchable.",
      },
    },
    async (_req, reply) => {
      return proxyToInternal(_req, reply, {
        app: root,
        internalUrl: "/api/v1/search/meta",
        needsTei: false,
      });
    },
  );
}
