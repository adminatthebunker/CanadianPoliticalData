import { AsyncLocalStorage } from "node:async_hooks";
import type { FastifyInstance } from "fastify";
import { pool } from "../db.js";
import type { AuthedRequest } from "../middleware/user-auth.js";

/**
 * Per-request search telemetry.
 *
 * One row in private.search_request_log per search call, recording
 * timing + filter shape + status. NO raw query text, NO user_id, NO IP,
 * NO email — operational only. The `was_authenticated` flag is the only
 * user-shape field; tier is stored if upstream middleware has stashed
 * it on req.user, but the search route doesn't trigger that lookup
 * itself (a /speeches request has no reason to hit private.users).
 *
 * AsyncLocalStorage carries a per-request mutable bucket so deep
 * helpers (encodeQuery, runTimelineSearch) can stash timings/flags
 * without changing their return signatures.
 */

interface TelemetryBucket {
  startNs: bigint;
  teiMs: number | null;
  resultCount: number | null;
  cachedEmbedding: boolean;
  isAnchorQuery: boolean;
  hasFilters: boolean;
}

const storage = new AsyncLocalStorage<TelemetryBucket>();

export function recordTeiCall(durationMs: number, cached: boolean): void {
  const bucket = storage.getStore();
  if (!bucket) return;
  // First call wins — anchor mode reads embedding from DB after a
  // potential text-encode. If both happen on one request, the text
  // encode is the meaningful TEI-side timing.
  if (bucket.teiMs == null) bucket.teiMs = durationMs;
  if (cached) bucket.cachedEmbedding = true;
}

export function markAnchorQuery(): void {
  const bucket = storage.getStore();
  if (bucket) bucket.isAnchorQuery = true;
}

export function markHasFilters(value: boolean): void {
  const bucket = storage.getStore();
  if (bucket) bucket.hasFilters = value;
}

export function recordResultCount(n: number): void {
  const bucket = storage.getStore();
  if (bucket) bucket.resultCount = n;
}

/**
 * Register the telemetry hooks on a Fastify plugin. Called once inside
 * searchRoutes() — every search request gets wrapped in an
 * AsyncLocalStorage scope, and onResponse writes the row.
 */
export function registerSearchTelemetry(app: FastifyInstance): void {
  app.addHook("preHandler", async (req, _reply) => {
    storage.enterWith({
      startNs: process.hrtime.bigint(),
      teiMs: null,
      resultCount: null,
      cachedEmbedding: false,
      isAnchorQuery: false,
      hasFilters: false,
    });
  });

  app.addHook("onResponse", async (req, reply) => {
    const bucket = storage.getStore();
    if (!bucket) return;
    const totalMs = Math.round(
      Number(process.hrtime.bigint() - bucket.startNs) / 1_000_000,
    );
    const user = (req as AuthedRequest).user;
    const tier =
      (user as { tier?: string } | undefined)?.tier ?? null;
    // Fastify 5: req.routeOptions.url is the full registered URL
    // including the plugin prefix (e.g. '/api/v1/search/speeches').
    const endpoint =
      (req.routeOptions as { url?: string } | undefined)?.url ??
      (req.url.split("?")[0] ?? "/unknown");
    try {
      await pool.query(
        `INSERT INTO private.search_request_log (
           endpoint, total_ms, tei_ms, sql_ms, result_count,
           was_anchor_query, was_authenticated, tier, status_code,
           cached_embedding, has_filters
         ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)`,
        [
          endpoint,
          totalMs,
          bucket.teiMs,
          bucket.teiMs != null ? Math.max(0, totalMs - bucket.teiMs) : null,
          bucket.resultCount,
          bucket.isAnchorQuery,
          !!user,
          tier,
          reply.statusCode,
          bucket.cachedEmbedding,
          bucket.hasFilters,
        ],
      );
    } catch (err) {
      // Telemetry must never break the response.
      req.log.warn({ err }, "search telemetry write failed");
    }
  });
}
