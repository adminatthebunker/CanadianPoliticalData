import type { FastifyReply, FastifyRequest } from "fastify";
import { getApiKey } from "./api-key-auth.js";

/**
 * Per-route tier gate for /api/public/v1/* endpoints. Checked AFTER
 * requireApiKey populates request.apiKey.
 *
 * Returns 403 with an actionable body when the caller's tier is
 * below the route's minimum. Anonymous callers (no api key) see the
 * same 403 — they should have hit requireApiKey's 401 first, but if
 * the route only uses optionalApiKey + requireTier, anon falls
 * through to here.
 *
 * Tier ordering (low → high): free < dev < pro. requireTier('pro')
 * accepts only pro; requireTier('dev') accepts dev + pro.
 */

const TIER_RANK: Record<"free" | "dev" | "pro", number> = {
  free: 0,
  dev: 1,
  pro: 2,
};

export function requireTier(minTier: "dev" | "pro") {
  const minRank = TIER_RANK[minTier];
  return async function tierGate(req: FastifyRequest, reply: FastifyReply) {
    const ak = getApiKey(req);
    if (!ak) {
      return reply.code(403).send({
        code: "insufficient_tier",
        error: "Forbidden",
        message:
          `this endpoint requires a ${minTier}+ tier API key. ` +
          `Anonymous and free-tier callers can't reach it. ` +
          `Subscribe at /account/billing.`,
        required_tier: minTier,
        current_tier: "anonymous",
      });
    }
    if (TIER_RANK[ak.tier] < minRank) {
      return reply.code(403).send({
        code: "insufficient_tier",
        error: "Forbidden",
        message:
          `this endpoint requires a ${minTier}+ tier API key. ` +
          `Your key is on the ${ak.tier} tier. ` +
          `Subscribe or upgrade at /account/billing.`,
        required_tier: minTier,
        current_tier: ak.tier,
      });
    }
  };
}
