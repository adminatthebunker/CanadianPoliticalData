import type { FastifyInstance } from "fastify";
import { z } from "zod";
import { requireApiKey } from "../../middleware/api-key-auth.js";
import { publicRateLimitConfig } from "../../middleware/api-rate-limit.js";
import { proxyToInternal } from "./proxy.js";

/**
 * Public committees endpoints (/api/public/v1/committees/*). Free-tier.
 *
 * Only one endpoint at v1.0: GET /committees/meetings — a derived list
 * of distinct committee meetings inferred from speeches rows where
 * speech_type='committee'. For full-text search inside the transcripts
 * use /api/public/v1/search/speeches?speech_type=committee (which is
 * pro-tier because it routes through TEI).
 */

const meetingsQuery = z
  .object({
    level: z.enum(["federal", "provincial", "municipal"]).optional(),
    province_territory: z.string().length(2).optional(),
    source_system: z.string().max(64).optional(),
    from: z.string().regex(/^\d{4}-\d{2}-\d{2}$/).optional(),
    to: z.string().regex(/^\d{4}-\d{2}-\d{2}$/).optional(),
    page: z.coerce.number().int().min(1).optional(),
    limit: z.coerce.number().int().min(1).max(100).optional(),
  })
  .passthrough();

export default async function publicV1CommitteesRoutes(app: FastifyInstance) {
  const root = app;

  app.get(
    "/committees/meetings",
    {
      preHandler: [requireApiKey],
      config: { rateLimit: publicRateLimitConfig },
      schema: {
        tags: ["Committees"],
        summary: "Distinct committee meetings derived from Hansard speeches",
        description:
          "Paginated list of distinct committee meetings inferred from " +
          "speeches WHERE speech_type='committee'. Federal meetings come " +
          "from openparliament.ca; AB meetings from assembly.ab.ca PDF " +
          "transcripts. Each item: " +
          "`{ meeting_url, level, province_territory, source_system, date, " +
          "first_spoken_at, last_spoken_at, speech_count }`. " +
          "Filters: level, province_territory, source_system, from, to. " +
          "For full-text search inside committee transcripts use " +
          "`/api/public/v1/search/speeches?speech_type=committee` " +
          "(pro-tier — TEI-dependent).",
        querystring: meetingsQuery,
      },
    },
    async (req, reply) => {
      return proxyToInternal(req, reply, {
        app: root,
        internalUrl: "/api/v1/committees/meetings",
      });
    },
  );
}
