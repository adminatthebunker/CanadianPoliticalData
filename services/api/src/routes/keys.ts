import type { FastifyInstance } from "fastify";
import { z } from "zod";
import { query, queryOne } from "../db.js";
import { requireUser, getUser } from "../middleware/user-auth.js";
import { requireCsrf } from "../lib/csrf.js";
import {
  mintApiKey,
  isConfigured as apiKeysConfigured,
} from "../lib/api-key-token.js";

/**
 * Self-service developer API key management.
 *
 * Mounted under /api/v1/me/api-keys. All routes require requireUser
 * (session cookie auth) — this surface is for humans managing their
 * own keys, NOT for keys themselves to introspect (use the public
 * surface for that). Mutating routes additionally require CSRF.
 *
 * Ownership pattern: every query is scoped `WHERE user_id = $1` against
 * the session's user; cross-user access returns 404 (not 403, prevents
 * id-enumeration — same discipline as /me/reports/:id).
 *
 * Token visibility: full tokens are returned ONCE, on POST /me/api-keys
 * and POST /me/api-keys/:id/rotate. The list endpoint never returns
 * a full token, only the prefix. Token storage is HMAC-hashed; we
 * literally cannot reconstruct the full token after creation.
 */

const createBody = z.object({
  name: z.string().trim().min(1).max(100),
  // Optional natural expiry — bounded at ~10 years to prevent silly
  // never-rotates keys. NULL/omitted = never expires.
  expires_in_days: z.coerce.number().int().min(1).max(3650).optional(),
});

interface KeyRow {
  id: string;
  user_id: string;
  prefix: string;
  name: string;
  tier: "free" | "dev" | "pro";
  scopes: string[];
  last_used_at: string | null;
  created_at: string;
  updated_at: string;
  expires_at: string | null;
  revoked_at: string | null;
  rotated_from_id: string | null;
  grace_until: string | null;
}

const SELECT_KEY_COLUMNS = `
  id::text,
  user_id::text,
  prefix,
  name,
  tier,
  scopes,
  last_used_at,
  created_at,
  updated_at,
  expires_at,
  revoked_at,
  rotated_from_id::text,
  grace_until
`;

function ensureConfigured(reply: import("fastify").FastifyReply): boolean {
  if (apiKeysConfigured()) return true;
  reply.code(503).send({
    error: "developer api disabled: API_KEY_PEPPER not configured on server",
  });
  return false;
}

export default async function keysRoutes(app: FastifyInstance) {
  // ── GET /me/api-keys ─────────────────────────────────────────
  app.get("/", { preHandler: requireUser }, async (req, reply) => {
    if (!ensureConfigured(reply)) return;
    const claims = getUser(req);
    if (!claims) return reply.code(401).send({ error: "not signed in" });

    const rows = await query<KeyRow>(
      `SELECT ${SELECT_KEY_COLUMNS}
         FROM private.api_keys
        WHERE user_id = $1
        ORDER BY created_at DESC`,
      [claims.sub],
    );
    return reply.send({ api_keys: rows });
  });

  // ── POST /me/api-keys ────────────────────────────────────────
  // Returns the FULL token in the response body. This is the only
  // place the full token is ever surfaced — the frontend must show
  // it to the user once and warn that it won't be retrievable later.
  app.post(
    "/",
    { preHandler: [requireUser, requireCsrf] },
    async (req, reply) => {
      if (!ensureConfigured(reply)) return;
      const claims = getUser(req);
      if (!claims) return reply.code(401).send({ error: "not signed in" });

      const parsed = createBody.safeParse(req.body);
      if (!parsed.success) {
        return reply.code(400).send({
          error: "invalid body",
          details: parsed.error.flatten(),
        });
      }
      const { name, expires_in_days } = parsed.data;

      const minted = mintApiKey();
      const expiresAt = expires_in_days
        ? new Date(Date.now() + expires_in_days * 86_400_000).toISOString()
        : null;

      const row = await queryOne<KeyRow>(
        `INSERT INTO private.api_keys
           (user_id, prefix, token_hash, name, expires_at)
         VALUES ($1, $2, $3, $4, $5::timestamptz)
         RETURNING ${SELECT_KEY_COLUMNS}`,
        [claims.sub, minted.prefix, minted.hash, name, expiresAt],
      );
      if (!row) {
        return reply.code(500).send({ error: "failed to create api key" });
      }

      // Audit row.
      await queryOne(
        `INSERT INTO private.api_key_events (api_key_id, event_type, metadata)
         VALUES ($1, 'created', $2::jsonb)`,
        [row.id, JSON.stringify({ name })],
      );

      return reply.code(201).send({ ...row, token: minted.token });
    },
  );

  // ── POST /me/api-keys/:id/rotate ─────────────────────────────
  // Generates a new key inheriting (name, tier, scopes, expires_at)
  // from the old; sets rotated_from_id on the new key + grace_until
  // on the old key (24h continued validity). Returns the new full token.
  app.post<{ Params: { id: string } }>(
    "/:id/rotate",
    { preHandler: [requireUser, requireCsrf] },
    async (req, reply) => {
      if (!ensureConfigured(reply)) return;
      const claims = getUser(req);
      if (!claims) return reply.code(401).send({ error: "not signed in" });
      const { id } = req.params;
      if (!/^[0-9a-f-]{36}$/i.test(id)) return reply.code(404).send({ error: "not found" });

      const existing = await queryOne<KeyRow>(
        `SELECT ${SELECT_KEY_COLUMNS}
           FROM private.api_keys
          WHERE id = $1 AND user_id = $2`,
        [id, claims.sub],
      );
      if (!existing) return reply.code(404).send({ error: "not found" });
      if (existing.revoked_at) {
        return reply.code(400).send({ error: "cannot rotate a revoked key" });
      }

      const minted = mintApiKey();
      const grace = new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString();

      // Set grace_until on the old key (still authenticates for 24h).
      await queryOne(
        `UPDATE private.api_keys
            SET grace_until = $1::timestamptz
          WHERE id = $2`,
        [grace, id],
      );
      await queryOne(
        `INSERT INTO private.api_key_events (api_key_id, event_type, metadata)
         VALUES ($1, 'rotated', $2::jsonb)`,
        [id, JSON.stringify({ grace_until: grace, replaced_by_prefix: minted.prefix })],
      );

      const newRow = await queryOne<KeyRow>(
        `INSERT INTO private.api_keys
           (user_id, prefix, token_hash, name, tier, scopes,
            expires_at, rotated_from_id)
         VALUES ($1, $2, $3, $4, $5, $6, $7::timestamptz, $8::uuid)
         RETURNING ${SELECT_KEY_COLUMNS}`,
        [
          claims.sub, minted.prefix, minted.hash, existing.name,
          existing.tier, existing.scopes, existing.expires_at, id,
        ],
      );
      if (!newRow) {
        return reply.code(500).send({ error: "failed to mint rotated key" });
      }
      await queryOne(
        `INSERT INTO private.api_key_events (api_key_id, event_type, metadata)
         VALUES ($1, 'created', $2::jsonb)`,
        [newRow.id, JSON.stringify({ rotated_from_id: id, name: existing.name })],
      );

      return reply.code(201).send({ ...newRow, token: minted.token });
    },
  );

  // ── DELETE /me/api-keys/:id ──────────────────────────────────
  // Soft-delete: sets revoked_at, leaves the row (and its events) in
  // place for audit. The auth middleware refuses revoked keys.
  app.delete<{ Params: { id: string } }>(
    "/:id",
    { preHandler: [requireUser, requireCsrf] },
    async (req, reply) => {
      if (!ensureConfigured(reply)) return;
      const claims = getUser(req);
      if (!claims) return reply.code(401).send({ error: "not signed in" });
      const { id } = req.params;
      if (!/^[0-9a-f-]{36}$/i.test(id)) return reply.code(404).send({ error: "not found" });

      const row = await queryOne<{ id: string }>(
        `UPDATE private.api_keys
            SET revoked_at = now(),
                grace_until = NULL
          WHERE id = $1 AND user_id = $2 AND revoked_at IS NULL
          RETURNING id::text`,
        [id, claims.sub],
      );
      if (!row) {
        // Either doesn't exist, isn't ours, or was already revoked.
        return reply.code(404).send({ error: "not found" });
      }
      await queryOne(
        `INSERT INTO private.api_key_events (api_key_id, event_type, metadata)
         VALUES ($1, 'revoked', '{}'::jsonb)`,
        [row.id],
      );
      return reply.code(204).send();
    },
  );
}
