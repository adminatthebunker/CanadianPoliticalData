import type { FastifyReply, FastifyRequest } from "fastify";
import { getApiKey } from "./api-key-auth.js";

/**
 * Per-route scope gate for /api/public/v1/* endpoints. Checked AFTER
 * requireApiKey populates request.apiKey.
 *
 * Distinct from requireTier: tiers are billing levels (free / dev /
 * pro), scopes are capability flags. read:public is currently the
 * only scope (read:bulk was retired with the public-dump distribution
 * surface on 2026-06-02); requireScope is kept as a no-cost seam for
 * reintroducing capability scopes later.
 *
 * Returns 403 with an actionable body when the caller's scopes don't
 * include the required scope. Anonymous callers (no api key) see the
 * same 403 — they should have hit requireApiKey's 401 first.
 */

export type ApiScope = "read:public";
export const ALLOWED_SCOPES: readonly ApiScope[] = ["read:public"];

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
