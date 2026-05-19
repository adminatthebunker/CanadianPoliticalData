import type { FastifyRequest } from "fastify";
import { queryOne } from "../db.js";
import { getApiKey } from "./api-key-auth.js";

/**
 * Per-tier rate-limit shape for /api/public/v1/* routes. Fed into the
 * per-route `config.rateLimit` slot honoured by @fastify/rate-limit
 * (which is registered globally in index.ts at the app default of
 * 300/min — this struct is the more-restrictive override).
 *
 * Phase 1a tiers (only `free` reachable from self-service):
 *   free  → 60 requests / hour    (per api key id)
 *   anon  → 30 requests / hour    (per source ip)
 *   dev   → 1000  / hour          [reserved; phase 1b]
 *   pro   → 10000 / hour          [reserved; phase 1b]
 *
 * Hourly bucket tracking lives in @fastify/rate-limit's in-memory store
 * (no DB writes here). The api_usage_daily table schema exists for the
 * phase 1c analytics writer; we don't double-write today.
 */

const TIER_HOURLY: Record<"free" | "dev" | "pro", number> = {
  free: 60,
  dev: 1000,
  pro: 10000,
};

const ANONYMOUS_HOURLY = 30;

// Separate bucket for the TEI-dependent semantic-search endpoints
// (/search/speeches, /search/speeches/count, /search/facets). Pulled
// out of the general bucket so a free-tier caller can do a few semantic
// queries an hour without burning their general 60/hr budget, and so
// a heavy semantic-search caller can't drain the general budget.
//
// Anonymous is blocked at the preHandler stage via requireApiKey — but
// we still set a max of 0 here as defense-in-depth in case requireApiKey
// is ever loosened.
const TIER_SEARCH_HOURLY: Record<"free" | "dev" | "pro", number> = {
  free: 5,
  dev: 100,
  pro: 10000,
};

// Anonymous semantic search is blocked at the preHandler stage by
// requireApiKey (which returns 401). We give the anon bucket a
// nonzero ceiling matching the general anon limit so the rate-limit
// middleware doesn't bounce the request with a misleading 429 before
// requireApiKey gets a chance to surface the correct 401. In practice
// no anon caller ever consumes this budget because they 401 first.
const ANONYMOUS_SEARCH_HOURLY = 30;

/** keyGenerator: api key id when authed, else source IP. */
export function publicRateLimitKey(req: FastifyRequest): string {
  const ak = getApiKey(req);
  if (ak) return `apikey:${ak.id}`;
  return `ip:${req.ip}`;
}

/** max resolver: per-tier when authed, anonymous fallback otherwise. */
export function publicRateLimitMax(req: FastifyRequest, _key: string): number {
  const ak = getApiKey(req);
  if (!ak) return ANONYMOUS_HOURLY;
  return TIER_HOURLY[ak.tier] ?? ANONYMOUS_HOURLY;
}

/**
 * Audit hook — writes a `rate_limited` row into private.api_key_events
 * when an authed caller exceeds their bucket. Fire-and-forget; errors
 * are swallowed so the 429 still goes out cleanly.
 *
 * Hooked via @fastify/rate-limit's `onExceeded` config slot. Picks the
 * correct per-tier limit + bucket label based on which URL path matched
 * — semantic-search endpoints debit a different bucket and read against
 * a stricter per-tier ceiling.
 */
function isSemanticSearchUrl(url: string): boolean {
  // path-only check; ignores query string
  const path = url.split("?", 1)[0] ?? url;
  return (
    path === "/api/public/v1/search/speeches" ||
    path === "/api/public/v1/search/speeches/count" ||
    path === "/api/public/v1/search/facets"
  );
}

export function onRateLimitExceeded(req: FastifyRequest): void {
  const ak = getApiKey(req);
  if (!ak) return; // anon callers — no key to log against
  const isSemantic = isSemanticSearchUrl(req.url);
  const limit = isSemantic
    ? (TIER_SEARCH_HOURLY[ak.tier] ?? ANONYMOUS_SEARCH_HOURLY)
    : (TIER_HOURLY[ak.tier] ?? ANONYMOUS_HOURLY);
  const meta = JSON.stringify({
    endpoint: req.url,
    tier: ak.tier,
    bucket: isSemantic ? "semantic" : "general",
    limit,
    window: "1h",
  });
  void queryOne(
    `INSERT INTO private.api_key_events (api_key_id, event_type, metadata)
     VALUES ($1, 'rate_limited', $2::jsonb)`,
    [ak.id, meta],
  ).catch(() => { /* fire-and-forget */ });
}

/** Spread into a route's `config.rateLimit` slot. */
export const publicRateLimitConfig = {
  max: publicRateLimitMax,
  timeWindow: "1 hour",
  keyGenerator: publicRateLimitKey,
  onExceeded: onRateLimitExceeded,
};

// ── Semantic-search bucket (TEI-dependent routes) ────────────────

/**
 * Namespaced keyGenerator: same identity as publicRateLimitKey but
 * suffixed with `:search` so @fastify/rate-limit treats it as a
 * separate bucket. A free-tier user blowing through their 5/hr
 * semantic-search budget does not affect their 60/hr general budget,
 * and vice versa.
 */
export function publicSearchRateLimitKey(req: FastifyRequest): string {
  return `${publicRateLimitKey(req)}:search`;
}

export function publicSearchRateLimitMax(req: FastifyRequest, _key: string): number {
  const ak = getApiKey(req);
  if (!ak) return ANONYMOUS_SEARCH_HOURLY;
  return TIER_SEARCH_HOURLY[ak.tier] ?? ANONYMOUS_SEARCH_HOURLY;
}

/** Spread into the semantic-search routes' `config.rateLimit` slot. */
export const publicSearchRateLimitConfig = {
  max: publicSearchRateLimitMax,
  timeWindow: "1 hour",
  keyGenerator: publicSearchRateLimitKey,
  onExceeded: onRateLimitExceeded,
};
