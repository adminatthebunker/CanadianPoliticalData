import type { FastifyInstance } from "fastify";
import { z } from "zod";
import {
  serializerCompiler,
  validatorCompiler,
  type ZodTypeProvider,
} from "fastify-type-provider-zod";
import { query, queryOne } from "../../db.js";
import { requireApiKey } from "../../middleware/api-key-auth.js";
import { publicRateLimitConfig } from "../../middleware/api-rate-limit.js";
import { resolvePostcode, PostcodeUpstreamError } from "../../lib/postcode.js";
import { currentBoundary } from "../../lib/boundary-temporal.js";
import { boundaryLicence } from "../../lib/boundary-licence.js";

/**
 * Public constituency-boundaries endpoints
 * (/api/public/v1/boundaries/*). Free-tier (requireApiKey only) —
 * boundary data is mirrored from Open North's free public API, so
 * paywalling it would be poor citizenship.
 *
 * Three routes:
 *   GET /boundaries                    — paginated metadata list
 *   GET /boundaries/lookup             — point-in-polygon lookup
 *   GET /boundaries/:source_set/:slug  — detail with GeoJSON
 *
 * Route-order discipline: /lookup is registered BEFORE the wildcard
 * /:source_set/:slug so Fastify's literal-path-first matching keeps
 * /lookup from being captured by the wildcard.
 *
 * "Current" boundary filter: the date predicate from `lib/boundary-temporal.ts`
 * (`effective_from <= CURRENT_DATE AND (effective_to IS NULL OR effective_to >=
 * CURRENT_DATE)`), which is the contract migration 0021 documents. It replaced a
 * bare `effective_to IS NULL` on 2026-08-18: that older form silently activates a
 * future-dated incoming generation the moment the outgoing one is end-dated,
 * because the incoming rows are then the only ones with a NULL effective_to. boundaries_version
 * is exposed in responses as a string but isn't currently filterable
 * — all live rows share version='current'.
 */

const LEVELS = ["federal", "provincial", "municipal"] as const;

const listQuery = z
  .object({
    level: z.enum(LEVELS).optional(),
    province_territory: z.string().length(2).optional(),
    bbox: z
      .string()
      .regex(/^-?\d+(\.\d+)?,-?\d+(\.\d+)?,-?\d+(\.\d+)?,-?\d+(\.\d+)?$/)
      .optional()
      .describe(
        "Bounding-box filter as minLng,minLat,maxLng,maxLat (WGS84). " +
          "Returns boundaries whose simplified geometry's bbox intersects.",
      ),
    page: z.coerce.number().int().min(1).optional(),
    limit: z.coerce.number().int().min(1).max(100).optional(),
  })
  .passthrough();

const lookupQuery = z
  .object({
    lat: z.coerce.number().min(40).max(85).optional().describe("Latitude in WGS84"),
    lng: z.coerce.number().min(-145).max(-50).optional().describe("Longitude in WGS84"),
    postcode: z
      .string()
      .min(3)
      .max(8)
      .optional()
      .describe(
        "Canadian postcode (6-char like K1A0A6) or FSA (3-char like K1A). Used as an alternative to lat/lng; if both are provided, postcode wins.",
      ),
    level: z.enum(LEVELS).optional(),
  })
  .passthrough();

const detailParams = z.object({
  source_set: z
    .string()
    .min(1)
    .max(200)
    .regex(/^[a-z0-9-]+$/)
    .describe(
      "Open North boundary set, e.g. federal-electoral-districts-2023-representation-order",
    ),
  slug: z
    .string()
    .min(1)
    .max(200)
    .regex(/^[a-z0-9-]+$/i)
    .describe(
      "Per-set boundary slug (kebab-case for provincial, numeric for federal)",
    ),
});

const detailQuery = z
  .object({
    precision: z.coerce.number().int().min(1).max(15).optional().describe(
      "ST_AsGeoJSON precision (decimal places of lat/lng). Default 6.",
    ),
  })
  .passthrough();

interface BoundaryMetaRow {
  constituency_id: string;
  name: string;
  level: string;
  province_territory: string | null;
  source_set: string | null;
  area_sqkm: number | null;
  centroid_lng: number | null;
  centroid_lat: number | null;
  effective_from: string | null;
  effective_to: string | null;
  boundaries_version: string | null;
}

interface BoundaryWithGeoJsonRow extends BoundaryMetaRow {
  boundary_geojson: unknown;
}

/**
 * PIP lookup against the full (non-simplified) boundary at a lng/lat
 * point. Returns the matching rows shaped for the public API. Used
 * by /boundaries/lookup AND /postcodes/:postcode so the shape stays
 * byte-identical across both surfaces.
 */
export async function lookupBoundariesAtPoint(
  lng: number,
  lat: number,
  levels?: readonly string[],
): Promise<{
  federal: ReturnType<typeof shapeBoundaryWithGeoJson> | null;
  provincial: ReturnType<typeof shapeBoundaryWithGeoJson> | null;
  municipal: ReturnType<typeof shapeBoundaryWithGeoJson> | null;
}> {
  const lvls = levels && levels.length > 0 ? levels : (LEVELS as readonly string[]);
  const rows = await query<BoundaryWithGeoJsonRow>(
    `SELECT constituency_id, name, level, province_territory, source_set,
            area_sqkm,
            ST_X(centroid) AS centroid_lng,
            ST_Y(centroid) AS centroid_lat,
            effective_from, effective_to, boundaries_version,
            ST_AsGeoJSON(boundary_simple)::jsonb AS boundary_geojson
       FROM constituency_boundaries
      WHERE ${currentBoundary()}
        AND level = ANY($1::text[])
        AND ST_Contains(boundary, ST_SetSRID(ST_MakePoint($2, $3), 4326))
      -- Smallest-first, so the per-level pick below is the most specific
      -- polygon rather than whichever row the planner returned last.
      ORDER BY level, area_sqkm ASC NULLS LAST`,
    [lvls as string[], lng, lat],
  );
  const out: {
    federal: ReturnType<typeof shapeBoundaryWithGeoJson> | null;
    provincial: ReturnType<typeof shapeBoundaryWithGeoJson> | null;
    municipal: ReturnType<typeof shapeBoundaryWithGeoJson> | null;
  } = { federal: null, provincial: null, municipal: null };
  // Keep the FIRST row per level — i.e. the smallest containing polygon.
  //
  // This previously overwrote, so the survivor was whichever row came last and
  // the result was non-deterministic. It matters most at the municipal level,
  // where a single point legitimately sits inside several nested polygons:
  // 62 of 72 ON/QC ward sets file a whole-municipality `census-subdivisions`
  // row alongside their wards, and four upper-tier `census-divisions` regions
  // sit above those again. Measured worst cases — a downtown Halifax address
  // is inside both its 8.5 km² district and the 5,957 km² Regional
  // Municipality (703×); Wood Buffalo is 597×; a Mississauga address returns
  // four polygons including the 1,256 km² Region of Peel, which elects nobody
  // to a ward. Smallest-first returns the ward.
  //
  // ⚠ The larger polygons are NOT junk and must not be filtered out: all 115
  // whole-municipality rows carry sitting officials (326 nationally), and in
  // BC — where at-large is the statutory default and no ward polygons exist —
  // they are the only geometry attaching 104 officials to anything. They are
  // the right answer when nothing smaller contains the point, which this
  // ordering preserves for free.
  for (const row of rows) {
    if (row.level === "federal" || row.level === "provincial" || row.level === "municipal") {
      if (out[row.level] === null) out[row.level] = shapeBoundaryWithGeoJson(row);
    }
  }
  return out;
}

export default async function publicV1BoundariesRoutes(app: FastifyInstance) {
  app.setValidatorCompiler(validatorCompiler);
  app.setSerializerCompiler(serializerCompiler);
  const a = app.withTypeProvider<ZodTypeProvider>();

  // ── GET /api/public/v1/boundaries ─────────────────────────────
  a.get(
    "/boundaries",
    {
      preHandler: [requireApiKey],
      config: { rateLimit: publicRateLimitConfig },
      schema: {
        tags: ["Constituency boundaries"],
        summary: "Paginated list of constituency boundaries (metadata only)",
        description:
          "List of federal/provincial/municipal electoral boundaries " +
          "mirrored from Open North (represent.opennorth.ca). Metadata only " +
          "— no GeoJSON payload; clients fetch detail by source_set + slug " +
          "when they need geometry. Filters: level, province_territory " +
          "(two-letter code; ignored for federal since federal ridings span " +
          "all of Canada), bbox (minLng,minLat,maxLng,maxLat WGS84). " +
          "Pagination: ?page=&limit= (limit cap 100, default 50). Response: " +
          "`{ items: [{ constituency_id, name, level, province_territory, " +
          "source_set, area_sqkm, centroid: { lng, lat }, effective_from, " +
          "effective_to, boundaries_version }, ...], page, limit, total, " +
          "pages }`. Cache-Control: public, max-age=3600.",
        querystring: listQuery,
      },
    },
    async (req, reply) => {
      const { level, province_territory, bbox } = req.query;
      const page = req.query.page ?? 1;
      const limit = req.query.limit ?? 50;
      const offset = (page - 1) * limit;

      const where: string[] = [currentBoundary()];
      const params: (string | number)[] = [];
      if (level) {
        params.push(level);
        where.push(`level = $${params.length}`);
      }
      if (province_territory) {
        params.push(province_territory.toUpperCase());
        where.push(`province_territory = $${params.length}`);
      }
      if (bbox) {
        const parts = bbox.split(",").map(Number);
        if (parts.length === 4 && parts.every((n) => Number.isFinite(n))) {
          const [minLng, minLat, maxLng, maxLat] = parts as [
            number,
            number,
            number,
            number,
          ];
          params.push(minLng, minLat, maxLng, maxLat);
          where.push(
            `boundary_simple && ST_MakeEnvelope($${params.length - 3}, $${params.length - 2}, $${params.length - 1}, $${params.length}, 4326)`,
          );
        }
      }

      const whereSql = `WHERE ${where.join(" AND ")}`;

      const totalRow = await queryOne<{ n: number }>(
        `SELECT COUNT(*)::int AS n FROM constituency_boundaries ${whereSql}`,
        params,
      );
      const total = totalRow?.n ?? 0;

      params.push(limit, offset);
      const items = await query<BoundaryMetaRow>(
        `SELECT constituency_id, name, level, province_territory, source_set,
                area_sqkm,
                ST_X(centroid) AS centroid_lng,
                ST_Y(centroid) AS centroid_lat,
                effective_from, effective_to, boundaries_version
           FROM constituency_boundaries
           ${whereSql}
          ORDER BY level, province_territory NULLS FIRST, name
          LIMIT $${params.length - 1} OFFSET $${params.length}`,
        params,
      );

      reply.header("Cache-Control", "public, max-age=3600");
      return {
        items: items.map(shapeBoundary),
        page,
        limit,
        total,
        pages: Math.max(1, Math.ceil(total / limit)),
      };
    },
  );

  // ── GET /api/public/v1/boundaries/lookup ──────────────────────
  // Point-in-polygon. Returns the containing riding at each level
  // (or just one level if ?level= is set). Uses the full `boundary`
  // for exactness — boundary_simple was simplified at ~555m which
  // misclassifies points near district edges.
  //
  // Two input modes: lat/lng (direct) or postcode (resolved via Open
  // North in real time). Postcode wins if both are passed.
  a.get(
    "/boundaries/lookup",
    {
      preHandler: [requireApiKey],
      config: { rateLimit: publicRateLimitConfig },
      schema: {
        tags: ["Constituency boundaries"],
        summary: "Find the riding(s) containing a lat/lng point or postcode",
        description:
          "Point-in-polygon lookup against the full (non-simplified) " +
          "boundary geometry. Returns the containing riding at each level " +
          "by default — useful for 'who's my MP, MLA, and city councillor' " +
          "civic-app patterns. Pass ?level=federal|provincial|municipal to " +
          "narrow to one level. Two input modes: pass either ?lat=&lng= " +
          "(WGS84; lat 40–85, lng -145 to -50) OR ?postcode= (6-char " +
          "Canadian postcode like K1A0A6, or 3-char FSA like K1A). When " +
          "postcode is passed it's resolved via Open North in real time " +
          "and the centroid is used; if both are passed, postcode wins. " +
          "Each match includes the simplified GeoJSON so a downstream " +
          "map widget can render the riding without a follow-up call. " +
          "Response: `{ federal: {...}|null, provincial: {...}|null, " +
          "municipal: {...}|null }`. Cache-Control: public, max-age=3600.",
        querystring: lookupQuery,
      },
    },
    async (req, reply) => {
      const { lat, lng, level, postcode } = req.query;

      let resolvedLat: number;
      let resolvedLng: number;
      if (postcode) {
        try {
          const r = await resolvePostcode(postcode);
          resolvedLat = r.latlng.lat;
          resolvedLng = r.latlng.lng;
        } catch (err) {
          if (err instanceof PostcodeUpstreamError) {
            if (err.kind === "invalid") return reply.badRequest(err.message);
            if (err.kind === "not_found") return reply.notFound(err.message);
            return reply.serviceUnavailable(err.message);
          }
          throw err;
        }
      } else if (lat !== undefined && lng !== undefined) {
        resolvedLat = lat;
        resolvedLng = lng;
      } else {
        return reply.badRequest(
          "must pass either ?lat=&lng= or ?postcode=",
        );
      }

      const levels = level ? [level] : undefined;
      const out = await lookupBoundariesAtPoint(
        resolvedLng,
        resolvedLat,
        levels,
      );

      reply.header("Cache-Control", "public, max-age=3600");
      return out;
    },
  );

  // ── GET /api/public/v1/boundaries/:source_set/:slug ───────────
  // Detail with full GeoJSON. constituency_id reconstructed from
  // two path params to avoid URL-encoded slashes.
  a.get(
    "/boundaries/:source_set/:slug",
    {
      preHandler: [requireApiKey],
      config: { rateLimit: publicRateLimitConfig },
      schema: {
        tags: ["Constituency boundaries"],
        summary: "Single boundary with simplified GeoJSON",
        description:
          "Single constituency boundary by Open North source_set + slug. " +
          "The two path params reconstruct constituency_id = source_set + " +
          "'/' + slug — this keeps slashes out of the URL path. Examples: " +
          "`/boundaries/federal-electoral-districts-2023-representation-order/35064` " +
          "(federal ridings use numeric slugs), " +
          "`/boundaries/alberta-electoral-districts/calgary-bow` " +
          "(provincial ridings use kebab-case slugs). " +
          "The returned GeoJSON is the simplified geometry (boundary_simple, " +
          "~555m tolerance) — good for web maps but not authoritative for " +
          "edge cases; for exact membership use /boundaries/lookup. " +
          "Optional ?precision=6 lowers GeoJSON coordinate precision for " +
          "bandwidth-constrained clients (default 6). 404 on missing " +
          "boundary. Response: `{ boundary: { constituency_id, name, level, " +
          "province_territory, source_set, area_sqkm, centroid, " +
          "effective_from, effective_to, boundaries_version, " +
          "boundary_geojson } }`. Cache-Control: public, max-age=3600.",
        params: detailParams,
        querystring: detailQuery,
      },
    },
    async (req, reply) => {
      const { source_set, slug } = req.params;
      const precision = req.query.precision ?? 6;
      const constituencyId = `${source_set}/${slug}`;

      const row = await queryOne<BoundaryWithGeoJsonRow>(
        `SELECT constituency_id, name, level, province_territory, source_set,
                area_sqkm,
                ST_X(centroid) AS centroid_lng,
                ST_Y(centroid) AS centroid_lat,
                effective_from, effective_to, boundaries_version,
                ST_AsGeoJSON(boundary_simple, $2)::jsonb AS boundary_geojson
           FROM constituency_boundaries
          WHERE constituency_id = $1
            AND ${currentBoundary()}`,
        [constituencyId, precision],
      );

      if (!row) return reply.notFound();

      reply.header("Cache-Control", "public, max-age=3600");
      return { boundary: shapeBoundaryWithGeoJson(row) };
    },
  );
}

function shapeBoundary(row: BoundaryMetaRow) {
  return {
    constituency_id: row.constituency_id,
    name: row.name,
    level: row.level,
    province_territory: row.province_territory,
    source_set: row.source_set,
    area_sqkm: row.area_sqkm,
    centroid:
      row.centroid_lng !== null && row.centroid_lat !== null
        ? { lng: row.centroid_lng, lat: row.centroid_lat }
        : null,
    effective_from: row.effective_from,
    effective_to: row.effective_to,
    boundaries_version: row.boundaries_version,
    // One line covers the ENTIRE public boundary surface: this is the only
    // shaping function, and shapeBoundaryWithGeoJson spreads it — so list,
    // lookup and detail all inherit the licence without further plumbing.
    licence: boundaryLicence(row.source_set),
  };
}

function shapeBoundaryWithGeoJson(row: BoundaryWithGeoJsonRow) {
  return {
    ...shapeBoundary(row),
    boundary_geojson: row.boundary_geojson,
  };
}
