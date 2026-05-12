import type { FastifyInstance } from "fastify";
import swagger from "@fastify/swagger";
import swaggerUI from "@fastify/swagger-ui";
import { z } from "zod";
import {
  serializerCompiler,
  validatorCompiler,
  jsonSchemaTransform,
  type ZodTypeProvider,
} from "fastify-type-provider-zod";
import { query, queryOne } from "../../db.js";
import { optionalApiKey } from "../../middleware/api-key-auth.js";
import { publicRateLimitConfig } from "../../middleware/api-rate-limit.js";
import { resolvePhotoUrl } from "../../lib/photos.js";
import { config } from "../../config.js";

/**
 * Public developer API surface (/api/public/v1/*).
 *
 * Phase 1c: extends the phase 1a-iii three-endpoint debut with
 * fastify-type-provider-zod integration so the existing zod schemas
 * drive both runtime validation AND OpenAPI emission. Swagger UI
 * mounts at /api/public/v1/docs; raw OpenAPI JSON at
 * /api/public/v1/openapi.json.
 *
 * Auth posture: optionalApiKey at onRequest hook so req.apiKey is
 * populated before @fastify/rate-limit's max resolver fires —
 * preHandler-stage would be too late and authed callers would get
 * the anonymous limit.
 *
 * CORS: permissive (origin: '*') via onSend hook (can't re-register
 * @fastify/cors which refuses double-registration). Public routes are
 * bearer-token-authenticated, not cookie-authenticated; wildcard
 * origin is browser-accepted because credentials: false.
 *
 * Schema source of truth: each endpoint's response shape mirrors its
 * internal /api/v1 sibling (services/api/src/routes/coverage.ts and
 * services/api/src/routes/politicians.ts:442-484). Response zod
 * schemas use .passthrough() on inner objects so adding a SQL column
 * doesn't silently strip the field from the wire — the docs go
 * stale, not the data.
 *
 * The type provider + swagger registrations are scoped to this
 * plugin via Fastify encapsulation; the internal /api/v1/* routes
 * keep their existing validator/serializer (manual safeParse).
 */

// ── Shared schemas ──────────────────────────────────────────────────
// Response schemas are deliberately omitted from route declarations.
// pg returns Date objects for timestamptz columns + JSONB columns
// surface as already-parsed objects, so a strict response zod would
// either need to allow z.union([z.string(), z.date()]) on every
// timestamp field (high-maintenance) or wrap with .transform()
// (changes wire format). The OpenAPI doc still shows the endpoint +
// query/path params; response shape is documented in the developer
// guide at /developers with curl + jq examples (single source of
// truth for response shape lives in the docs, not the schema).

const coverageQuery = z.object({
  status: z
    .enum(["live", "partial", "blocked", "none"])
    .optional()
    .describe("Filter to jurisdictions whose bills_status matches"),
});

const politicianIdParam = z.object({
  id: z
    .string()
    .regex(/^[0-9a-f-]{36}$/i)
    .describe("UUID of the politician"),
});

interface JurisdictionRow {
  jurisdiction: string;
  legislature_name: string;
  seats: number | null;
  bills_status: string;
  hansard_status: string;
  votes_status: string;
  committees_status: string;
  bills_difficulty: number | null;
  hansard_difficulty: number | null;
  votes_difficulty: number | null;
  committees_difficulty: number | null;
  blockers: string | null;
  notes: string | null;
  source_urls: Record<string, unknown>;
  bills_count: number;
  speeches_count: number;
  votes_count: number;
  politicians_count: number;
  last_verified_at: string | null;
  updated_at: string;
}

export default async function publicV1Routes(app: FastifyInstance) {
  // Type provider — installed at plugin scope (Fastify encapsulation
  // means siblings keep the default validator/serializer).
  app.setValidatorCompiler(validatorCompiler);
  app.setSerializerCompiler(serializerCompiler);
  const a = app.withTypeProvider<ZodTypeProvider>();

  // OpenAPI metadata + Swagger UI mount.
  await app.register(swagger, {
    openapi: {
      info: {
        title: "Canadian Political Data — Public API",
        description:
          "Read-only access to the public Canadian political dataset: " +
          "politicians, jurisdictions, coverage stats. Bearer-token " +
          "authenticated via API keys minted at /account/api-keys. " +
          "See /developers for the full guide.",
        version: "1.0.0",
        contact: {
          name: "Canadian Political Data",
          url: "https://canadianpoliticaldata.org/",
          email: "admin@thebunkerops.ca",
        },
        license: {
          name: "See repository LICENSE",
          url: "https://canadianpoliticaldata.org/about/",
        },
      },
      servers: [
        {
          url: `${config.publicSiteUrl}/api/public/v1`,
          description: "Production",
        },
      ],
      components: {
        securitySchemes: {
          bearerAuth: {
            type: "http",
            scheme: "bearer",
            bearerFormat: "cpd_<env>_<random>_<checksum>",
            description:
              "API keys minted at /account/api-keys. Format: " +
              "cpd_live_<22-char-base62>_<6-char-checksum>. " +
              "Anonymous calls work too, at a lower rate limit (30/hr per IP).",
          },
        },
      },
      // Bearer auth is OPTIONAL on every endpoint — anonymous callers
      // hit the IP-bucket rate limit; authed callers get their tier's
      // limit. We don't list it as required globally; per-route
      // security blocks would just say `[{}, { bearerAuth: [] }]` to
      // mean "either anonymous or bearer".
    },
    transform: jsonSchemaTransform,
  });

  await app.register(swaggerUI, {
    routePrefix: "/docs",
    uiConfig: {
      docExpansion: "list",
      deepLinking: true,
    },
    staticCSP: true,
  });

  // Permissive CORS via hook.
  app.addHook("onSend", async (_req, reply, _payload) => {
    reply.header("Access-Control-Allow-Origin", "*");
    reply.header("Access-Control-Allow-Methods", "GET, OPTIONS");
    reply.header(
      "Access-Control-Allow-Headers",
      "Authorization, Content-Type",
    );
  });
  // Cheap OPTIONS preflight responder so browsers don't get a 404.
  // Hidden from the OpenAPI spec — it's mechanical CORS plumbing,
  // not a publicly-relevant endpoint.
  app.options("/*", { schema: { hide: true } }, async (_req, reply) => {
    reply.code(204).send();
  });

  // optionalApiKey runs at onRequest so req.apiKey is populated
  // BEFORE @fastify/rate-limit's per-route keyGenerator/max resolver
  // fires.
  app.addHook("onRequest", optionalApiKey);

  // ── GET /api/public/v1/coverage ───────────────────────────────
  a.get(
    "/coverage",
    {
      config: { rateLimit: publicRateLimitConfig },
      schema: {
        tags: ["Coverage"],
        summary: "Coverage rollup across all 14 Canadian jurisdictions",
        description:
          "Returns one row per jurisdiction (federal + 10 provinces + " +
          "3 territories) with current ingestion status and counts. " +
          "Includes a small summary rollup for headline numbers. " +
          "Response shape: `{ jurisdictions: [{ jurisdiction, " +
          "legislature_name, seats, bills_status, hansard_status, " +
          "votes_status, committees_status, bills_count, speeches_count, " +
          "votes_count, politicians_count, last_verified_at, ... }], " +
          "summary: { total, live, partial, blocked, none } }`. " +
          "Cache-Control: public, max-age=300.",
        querystring: coverageQuery,
      },
    },
    async (req, reply) => {
      const { status } = req.query;
      const rows = await query<JurisdictionRow>(
        `SELECT jurisdiction, legislature_name, seats,
                bills_status, hansard_status, votes_status, committees_status,
                bills_difficulty, hansard_difficulty, votes_difficulty, committees_difficulty,
                blockers, notes, source_urls,
                bills_count, speeches_count, votes_count, politicians_count,
                last_verified_at, updated_at
           FROM jurisdiction_sources
          ${status ? "WHERE bills_status = $1" : ""}
          ORDER BY
            CASE jurisdiction WHEN 'federal' THEN 0 ELSE 1 END,
            jurisdiction`,
        status ? [status] : [],
      );
      const summary = {
        total: rows.length,
        live: rows.filter((r) => r.bills_status === "live").length,
        partial: rows.filter((r) => r.bills_status === "partial").length,
        blocked: rows.filter((r) => r.bills_status === "blocked").length,
        none: rows.filter((r) => r.bills_status === "none").length,
      };
      reply.header("Cache-Control", "public, max-age=300");
      return { jurisdictions: rows, summary };
    },
  );

  // ── GET /api/public/v1/jurisdiction-sources ───────────────────
  a.get(
    "/jurisdiction-sources",
    {
      config: { rateLimit: publicRateLimitConfig },
      schema: {
        tags: ["Coverage"],
        summary: "Flat per-jurisdiction list (no summary rollup)",
        description:
          "Same underlying data as /coverage, but as a raw list of rows " +
          "without the summary block. For callers building their own " +
          "dashboard view. Response shape: `{ items: [...] }` where " +
          "each item is the same row shape as /coverage. " +
          "Cache-Control: public, max-age=300.",
      },
    },
    async (_req, reply) => {
      const rows = await query<JurisdictionRow>(
        `SELECT jurisdiction, legislature_name, seats,
                bills_status, hansard_status, votes_status, committees_status,
                bills_difficulty, hansard_difficulty, votes_difficulty, committees_difficulty,
                blockers, notes, source_urls,
                bills_count, speeches_count, votes_count, politicians_count,
                last_verified_at, updated_at
           FROM jurisdiction_sources
          ORDER BY
            CASE jurisdiction WHEN 'federal' THEN 0 ELSE 1 END,
            jurisdiction`,
        [],
      );
      reply.header("Cache-Control", "public, max-age=300");
      return { items: rows };
    },
  );

  // ── GET /api/public/v1/politicians/:id ────────────────────────
  a.get(
    "/politicians/:id",
    {
      config: { rateLimit: publicRateLimitConfig },
      schema: {
        tags: ["Politicians"],
        summary: "Single politician with active websites + boundary",
        description:
          "Returns the politician row, all currently-active websites " +
          "with their latest infrastructure scan (DNS + hosting + " +
          "sovereignty tier), and the constituency GeoJSON boundary " +
          "when constituency_id is set. 404 on missing or malformed id. " +
          "Response shape: `{ politician: {...}, websites: [...], " +
          "boundary: { constituency_id, name, level, boundary_geojson, " +
          "centroid_lng, centroid_lat } | null }`. " +
          "Cache-Control: public, max-age=60.",
        params: politicianIdParam,
      },
    },
    async (req, reply) => {
      const { id } = req.params;
      const pol = await queryOne<Record<string, unknown>>(
        `SELECT p.*,
                (SELECT MAX(ended_at)
                   FROM politician_terms
                  WHERE politician_id = p.id
                    AND ended_at IS NOT NULL) AS latest_term_ended_at
           FROM politicians p
          WHERE p.id = $1`,
        [id],
      );
      if (!pol) return reply.notFound();
      (pol as Record<string, unknown>).photo_url = resolvePhotoUrl(
        pol as { photo_path?: string | null; photo_url?: string | null },
      );

      const websites = await query(
        `
        SELECT w.*, s.ip_country, s.ip_city, s.ip_latitude, s.ip_longitude,
               s.hosting_provider, s.hosting_country, s.sovereignty_tier,
               s.cdn_detected, s.cms_detected, s.scanned_at
        FROM websites w
        LEFT JOIN LATERAL (
          SELECT * FROM infrastructure_scans WHERE website_id = w.id
          ORDER BY scanned_at DESC LIMIT 1
        ) s ON true
        WHERE w.owner_type='politician' AND w.owner_id=$1 AND w.is_active=true
        ORDER BY w.label
        `,
        [id],
      );

      const boundary = (pol as { constituency_id?: string }).constituency_id
        ? await queryOne(
            `SELECT constituency_id, name, level, ST_AsGeoJSON(boundary_simple)::jsonb AS boundary_geojson,
                    ST_X(centroid) AS centroid_lng, ST_Y(centroid) AS centroid_lat
               FROM constituency_boundaries WHERE constituency_id = $1`,
            [(pol as { constituency_id: string }).constituency_id],
          )
        : null;

      reply.header("Cache-Control", "public, max-age=60");
      return { politician: pol, websites, boundary };
    },
  );
}
