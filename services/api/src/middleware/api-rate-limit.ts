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
 * Hooked via @fastify/rate-limit's `onExceeded` config slot.
 */
export function onRateLimitExceeded(req: FastifyRequest): void {
  const ak = getApiKey(req);
  if (!ak) return; // anon callers — no key to log against
  const meta = JSON.stringify({
    endpoint: req.url,
    tier: ak.tier,
    limit: TIER_HOURLY[ak.tier] ?? ANONYMOUS_HOURLY,
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
