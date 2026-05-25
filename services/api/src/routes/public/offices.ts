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

/**
 * Public offices subresource (/api/public/v1/politicians/:id/offices).
 *
 * Mirrors the internal /api/v1/politicians/:id/offices SQL but returns
 * the full structured list — multiple offices per politician (a
 * politician with two constituency offices keeps both rows), with
 * lat/lng/hours/fax. The convenience freeform-string addresses on
 * /politicians/:id are derived from this same data.
 *
 * Column note: the table has `lon` (PostGIS convention); the public
 * response aliases to `lng` for consistency with /boundaries/lookup
 * and /postcodes/:postcode.
 */

const politicianIdParam = z.object({
  id: z
    .string()
    .regex(/^[0-9a-f-]{36}$/i)
    .describe("UUID of the politician"),
});

export default async function publicV1OfficesRoutes(app: FastifyInstance) {
  app.setValidatorCompiler(validatorCompiler);
  app.setSerializerCompiler(serializerCompiler);
  const a = app.withTypeProvider<ZodTypeProvider>();

  a.get(
    "/politicians/:id/offices",
    {
      preHandler: [requireApiKey],
      config: { rateLimit: publicRateLimitConfig },
      schema: {
        tags: ["Politician contact"],
        summary: "Structured office list for one politician",
        description:
          "Constituency, legislature, and other offices for a single " +
          "politician. Multiple rows per politician are preserved — a " +
          "politician with two constituency offices returns both rows " +
          "(deduplication is by (politician_id, kind, phone)). Includes " +
          "lat/lng coordinates, hours-of-operation, fax, and source " +
          "attribution. 404 on unknown politician. Response: `{ items: " +
          "[{ kind, address, city, province_territory, postal_code, " +
          "phone, fax, email, hours, lat, lng, source }, ...] }`. " +
          "Cache-Control: public, max-age=600.",
        params: politicianIdParam,
      },
    },
    async (req, reply) => {
      const { id } = req.params;
      const exists = await queryOne<{ n: number }>(
        `SELECT 1 AS n FROM politicians WHERE id = $1`,
        [id],
      );
      if (!exists) return reply.notFound();

      const items = await query(
        `SELECT kind, address, city, province_territory, postal_code,
                phone, fax, email, hours,
                lat, lon AS lng, source
           FROM politician_offices
          WHERE politician_id = $1
          ORDER BY
            CASE kind
              WHEN 'constituency' THEN 0
              WHEN 'legislature'  THEN 1
              WHEN 'office'       THEN 2
              ELSE 3
            END,
            updated_at DESC`,
        [id],
      );

      reply.header("Cache-Control", "public, max-age=600");
      return { items };
    },
  );
}
