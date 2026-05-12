import type { FastifyReply, FastifyRequest } from "fastify";
import { getApiKey } from "./api-key-auth.js";

/**
 * Per-route scope gate for /api/public/v1/* endpoints. Checked AFTER
 * requireApiKey populates request.apiKey.
 *
 * Distinct from requireTier: tiers are billing levels (free / dev /
 * pro), scopes are capability flags (read:public / read:bulk).
 * A free-tier key CAN have read:bulk scope (cheap-but-allowed bulk
 * download access without paying for higher request rate). A pro-tier
 * key WITHOUT read:bulk can hammer search but can't download dumps.
 *
 * Returns 403 with an actionable body when the caller's scopes don't
 * include the required scope. Anonymous callers (no api key) see the
 * same 403 — they should have hit requireApiKey's 401 first.
 */

export type ApiScope = "read:public" | "read:bulk";
export const ALLOWED_SCOPES: readonly ApiScope[] = ["read:public", "read:bulk"];

export function requireScope(scope: ApiScope) {
  return async function scopeGate(req: FastifyRequest, reply: FastifyReply) {
    const ak = getApiKey(req);
    if (!ak) {
      return reply.code(403).send({
        code: "insufficient_scope",
        error: "Forbidden",
        message:
          `this endpoint requires the '${scope}' scope. ` +
          `Anonymous callers can't reach it. ` +
          `Sign in and create a key with the scope at /account/api-keys.`,
        required_scope: scope,
        current_scopes: [],
      });
    }
    if (!ak.scopes.includes(scope)) {
      return reply.code(403).send({
        code: "insufficient_scope",
        error: "Forbidden",
        message:
          `this endpoint requires the '${scope}' scope. ` +
          `Your key has [${ak.scopes.join(", ")}]. ` +
          `Create a new key with the scope at /account/api-keys, or ` +
          `rotate this one and tick the scope checkbox.`,
        required_scope: scope,
        current_scopes: ak.scopes,
      });
    }
  };
}
