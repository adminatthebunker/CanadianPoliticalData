import type { FastifyInstance } from "fastify";
import { z } from "zod";
import {
  serializerCompiler,
  validatorCompiler,
  type ZodTypeProvider,
} from "fastify-type-provider-zod";
import { requireApiKey } from "../../middleware/api-key-auth.js";
import { publicRateLimitConfig } from "../../middleware/api-rate-limit.js";
import { resolvePostcode, PostcodeUpstreamError } from "../../lib/postcode.js";
import { lookupBoundariesAtPoint } from "./boundaries.js";

/**
 * Public postcode endpoint (/api/public/v1/postcodes/:postcode).
 *
 * Two-stage lookup: proxy Open North for the centroid, then run
 * our own PIP against `constituency_boundaries` so the response
 * `boundaries.*` slot is byte-identical to what /boundaries/lookup
 * returns. Open North's `boundaries_centroid` is intentionally not
 * passed through — its shape diverges, and it includes ward /
 * school / non-mirrored sets we wouldn't recognise.
 *
 * Accepts 6-char (K1A 0A6, K1A-0A6, K1A0A6) or 3-char FSA (K1A).
 * No local cache — Canada Post licensing stays Open North's
 * problem.
 */

const postcodeParam = z.object({
  postcode: z
    .string()
    .min(3)
    .max(8)
    .describe("6-char postcode (K1A0A6) or 3-char FSA (K1A)"),
});

export default async function publicV1PostcodesRoutes(app: FastifyInstance) {
  app.setValidatorCompiler(validatorCompiler);
  app.setSerializerCompiler(serializerCompiler);
  const a = app.withTypeProvider<ZodTypeProvider>();

  a.get(
    "/postcodes/:postcode",
    {
      preHandler: [requireApiKey],
      config: { rateLimit: publicRateLimitConfig },
      schema: {
        tags: ["Postcodes"],
        summary: "Resolve postcode/FSA to lat/lng + containing ridings",
        description:
          "Real-time proxy to Open North's Represent API for postcode " +
          "geocoding, then runs our own point-in-polygon against the " +
          "centroid so the `boundaries.*` slots are byte-identical to " +
          "what /boundaries/lookup returns. Accepts either a 6-char " +
          "postcode (K1A0A6, K1A 0A6, K1A-0A6) or a 3-char FSA (K1A). " +
          "For FSAs the centroid is a representative point inside the " +
          "FSA polygon and the boundary lookup uses that point — good " +
          "enough for 'what's the dominant riding for this FSA' but " +
          "not authoritative for FSAs that straddle riding boundaries. " +
          "Response: `{ postcode, is_fsa, latlng: { lat, lng }, city, " +
          "province, source: 'cache'|'cache_stale'|'live', fetched_at, " +
          "boundaries: { federal: {...}|null, provincial: {...}|null, " +
          "municipal: {...}|null } }`. The `source` field indicates " +
          "whether this came from the local cache (fresh within 30 " +
          "days), a stale cache served because Open North was " +
          "unreachable, or a live Open North fetch. Returns 400 on " +
          "malformed input, 404 when Open North doesn't know the " +
          "postcode (the cache row is evicted on confirmed 404), 503 " +
          "only when Open North is unreachable AND no cache row exists. " +
          "Cache-Control: public, max-age=86400.",
        params: postcodeParam,
      },
    },
    async (req, reply) => {
      const { postcode } = req.params;

      let resolved;
      try {
        resolved = await resolvePostcode(postcode);
      } catch (err) {
        if (err instanceof PostcodeUpstreamError) {
          if (err.kind === "invalid") return reply.badRequest(err.message);
          if (err.kind === "not_found") return reply.notFound(err.message);
          return reply.serviceUnavailable(err.message);
        }
        throw err;
      }

      const boundaries = await lookupBoundariesAtPoint(
        resolved.latlng.lng,
        resolved.latlng.lat,
      );

      reply.header("Cache-Control", "public, max-age=86400");
      reply.header("X-Cache-Source", resolved.source);
      return {
        postcode: resolved.postcode,
        is_fsa: resolved.is_fsa,
        latlng: resolved.latlng,
        city: resolved.city,
        province: resolved.province,
        source: resolved.source,
        fetched_at: resolved.fetched_at,
        boundaries,
      };
    },
  );
}
