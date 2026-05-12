import type { FastifyReply, FastifyRequest } from "fastify";
import { queryOne } from "../db.js";
import {
  isConfigured as apiKeyIsConfigured,
  verifyApiKey,
} from "../lib/api-key-token.js";

/**
 * Public-developer-API key middleware. Sibling of user-auth.ts:
 *  - 503 when the feature is disabled (API_KEY_PEPPER unset).
 *  - 401 for missing / invalid / expired / revoked keys (requireApiKey).
 *  - Attaches `request.apiKey` for downstream handlers.
 *
 * Two preHandlers:
 *  - `requireApiKey`: 401s if no valid key. Use when the route MUST
 *    identify the caller (e.g. paid-tier endpoints when phase 1b lands).
 *  - `optionalApiKey`: attaches req.apiKey when a valid key is present;
 *    otherwise leaves it unset and allows the request through. Use on
 *    free-tier public endpoints so the rate-limit middleware can
 *    still distinguish authed-free-tier from anonymous-IP-fallback.
 *
 * Tokens arrive in `Authorization: Bearer cpd_<env>_<body>_<checksum>`.
 * The bearer prefix is required for grep-ability in HTTP captures.
 */

export interface ApiKeyContext {
  /** UUID of the private.api_keys row. */
  id: string;
  /** UUID of the owning user. */
  user_id: string;
  /** "free" | "dev" | "pro". For phase 1a only "free" is reachable. */
  tier: "free" | "dev" | "pro";
  /** Capability scopes. Phase 1a hard-codes ['read:public']. */
  scopes: string[];
  /** Plaintext prefix, useful for logging. Never log the full token. */
  prefix: string;
}

export interface ApiKeyedRequest extends FastifyRequest {
  apiKey?: ApiKeyContext;
}

function readBearerToken(req: FastifyRequest): string | null {
  const header = req.headers["authorization"];
  if (typeof header !== "string") return null;
  const m = /^Bearer\s+(\S+)$/i.exec(header.trim());
  return m && m[1] ? m[1] : null;
}

/**
 * Throttle last_used_at writes — at most once per minute per key. Avoids
 * hammering the DB with an UPDATE on every authed request. Bounded LRU
 * (10K keys) so memory usage stays trivial.
 */
const LAST_USED_BUCKET_MS = 60_000;
const LAST_USED_LRU_MAX = 10_000;
const lastUsedAt = new Map<string, number>();

async function touchLastUsed(apiKeyId: string): Promise<void> {
  const now = Date.now();
  const prev = lastUsedAt.get(apiKeyId) ?? 0;
  if (now - prev < LAST_USED_BUCKET_MS) return;
  lastUsedAt.set(apiKeyId, now);
  if (lastUsedAt.size > LAST_USED_LRU_MAX) {
    // Drop the oldest 1K entries on overflow. Crude but bounded.
    const drop = 1000;
    let i = 0;
    for (const k of lastUsedAt.keys()) {
      lastUsedAt.delete(k);
      if (++i >= drop) break;
    }
  }
  try {
    await queryOne(
      `UPDATE private.api_keys SET last_used_at = now() WHERE id = $1`,
      [apiKeyId],
    );
  } catch {
    // Fire-and-forget; if the touch fails, the key still authenticates.
    // We'll get the timestamp eventually on the next bucket window.
  }
}

interface KeyRow {
  id: string;
  user_id: string;
  tier: "free" | "dev" | "pro";
  scopes: string[];
  prefix: string;
}

async function lookupKey(
  prefix: string,
  hash: Buffer,
): Promise<KeyRow | null> {
  // The prefix index narrows to ~1 row in practice; the hash compare
  // gates the auth decision. Both checks happen in the WHERE so a
  // matching prefix without the right hash drops out.
  //
  // Liveness conditions baked into the SQL: not revoked, not expired
  // (or grace_until window still open after a rotation). The user must
  // exist; rate_limit_tier='suspended' on the user takes effect on the
  // next request (matches the requireUser pattern).
  return queryOne<KeyRow>(
    `
    SELECT k.id::text       AS id,
           k.user_id::text  AS user_id,
           k.tier,
           k.scopes,
           k.prefix
      FROM private.api_keys k
      JOIN private.users    u ON u.id = k.user_id
     WHERE k.prefix     = $1
       AND k.token_hash = $2
       AND (
             k.revoked_at IS NULL
          OR (k.grace_until IS NOT NULL AND k.grace_until > now())
           )
       AND (k.expires_at IS NULL OR k.expires_at > now())
       AND COALESCE(u.rate_limit_tier, 'default') != 'suspended'
     LIMIT 1
    `,
    [prefix, hash],
  );
}

export async function requireApiKey(req: FastifyRequest, reply: FastifyReply) {
  if (!apiKeyIsConfigured()) {
    return reply.code(503).send({
      error: "developer api disabled: API_KEY_PEPPER not configured on server",
    });
  }
  const token = readBearerToken(req);
  if (!token) {
    return reply.code(401).send({
      error: "missing bearer token (Authorization: Bearer cpd_…)",
    });
  }
  const verified = verifyApiKey(token);
  if (!verified) {
    return reply.code(401).send({ error: "invalid or malformed api key" });
  }
  const row = await lookupKey(verified.prefix, verified.hash);
  if (!row) {
    return reply.code(401).send({ error: "invalid or expired api key" });
  }
  (req as ApiKeyedRequest).apiKey = {
    id: row.id,
    user_id: row.user_id,
    tier: row.tier,
    scopes: row.scopes ?? ["read:public"],
    prefix: row.prefix,
  };
  // Throttled fire-and-forget — don't await.
  void touchLastUsed(row.id);
}

export async function optionalApiKey(req: FastifyRequest, _reply: FastifyReply) {
  if (!apiKeyIsConfigured()) return;
  const token = readBearerToken(req);
  if (!token) return;
  const verified = verifyApiKey(token);
  if (!verified) return;
  const row = await lookupKey(verified.prefix, verified.hash);
  if (!row) return;
  (req as ApiKeyedRequest).apiKey = {
    id: row.id,
    user_id: row.user_id,
    tier: row.tier,
    scopes: row.scopes ?? ["read:public"],
    prefix: row.prefix,
  };
  void touchLastUsed(row.id);
}

export function getApiKey(req: FastifyRequest): ApiKeyContext | null {
  return (req as ApiKeyedRequest).apiKey ?? null;
}
