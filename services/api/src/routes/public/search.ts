import type { FastifyInstance } from "fastify";
import { z } from "zod";
import {
  requireApiKey,
} from "../../middleware/api-key-auth.js";
import {
  publicRateLimitConfig,
  publicSearchRateLimitConfig,
} from "../../middleware/api-rate-limit.js";
import { proxyToInternal } from "./proxy.js";

/**
 * Public search endpoints (/api/public/v1/search/*).
 *
 * Six routes, two rate-limit buckets:
 *
 *   SEMANTIC (TEI-dependent — separate :search-suffixed bucket so
 *   semantic queries don't drain the general API bucket; per-tier
 *   limits free=5/hr, dev=100/hr, pro=10000/hr):
 *   - GET /search/speeches         — full search; mirror of internal /api/v1/search/speeches
 *   - GET /search/speeches/count   — count-only sibling
 *   - GET /search/facets           — aggregations over top-N
 *
 *   AUXILIARIES (no TEI, lookup tables; general per-tier bucket):
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
 * making the caller wait minutes. This GPU-protection layer is
 * orthogonal to the per-tier rate-limit bucket.
 *
 * Auth: requireApiKey on the three semantic routes (anonymous is
 * blocked at the preHandler stage — anon = IP bucket, trivially
 * rotated → GPU abuse vector). Auxiliary routes inherit
 * optionalApiKey from the parent plugin so anon callers get the
 * IP-bucket rate limit.
 */

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

  // ── Semantic (TEI-dependent; :search-namespaced bucket) ───────

  app.get(
    "/search/speeches",
    {
      preHandler: [requireApiKey],
      config: { rateLimit: publicSearchRateLimitConfig },
      schema: {
        tags: ["Search (semantic)"],
        summary: "Hybrid HNSW + BM25 semantic search over Hansard",
        description:
          "Mirror of the internal /api/v1/search/speeches endpoint. " +
          "Available to every authenticated tier — free=5/hr, dev=100/hr, " +
          "pro=10000/hr — counted against a SEPARATE bucket from the " +
          "general API rate limit (so semantic queries don't drain the " +
          "60/hr free or 1000/hr dev budget for /coverage etc., and " +
          "vice versa). The embed step also routes through a shared TEI " +
          "semaphore (max 2 concurrent + 6 queued; 503 with Retry-After " +
          "if the queue saturates) — that GPU-protection layer is " +
          "orthogonal to the per-tier rate limit. Same response shape " +
          "as the internal route (timeline mode by default; " +
          "group_by=politician for grouped). See /developers/rate-limiting " +
          "for both layers.",
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
      preHandler: [requireApiKey],
      config: { rateLimit: publicSearchRateLimitConfig },
      schema: {
        tags: ["Search (semantic)"],
        summary: "Count-only sibling for /search/speeches",
        description:
          "Returns { total, capped }. Capping kicks in at 10,000 + 1 " +
          "(HNSW LIMIT trick). Use alongside ?include_count=false on " +
          "/search/speeches to stage count off the hot path. Shares the " +
          "semantic-search rate-limit bucket (free=5/hr, dev=100/hr, " +
          "pro=10000/hr) and the TEI semaphore with /search/speeches.",
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
      preHandler: [requireApiKey],
      config: { rateLimit: publicSearchRateLimitConfig },
      schema: {
        tags: ["Search (semantic)"],
        summary: "Aggregations over the top-N candidate pool",
        description:
          "Returns { analyzed_count, analysis_limit, chunk_ids, by_party, " +
          "by_politician, by_year, by_language, keyword_overlap, mode }. " +
          "Optional ?limit query (clamped [10, 500], default 200) sets " +
          "the candidate-pool size. Shares the semantic-search rate-limit " +
          "bucket and the TEI semaphore with /search/speeches.",
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
