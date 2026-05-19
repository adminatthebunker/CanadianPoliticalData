import type { FastifyInstance } from "fastify";
import { z } from "zod";
import { query, queryOne } from "../db.js";

/**
 * Committee meetings — a derived view over speeches WHERE speech_type='committee'.
 *
 * There is no `meetings` table; meetings are inferred from speech rows.
 * The grouping key has to vary by source_system because the upstreams
 * differ in URL granularity:
 *
 *   - openparliament (federal): one URL per speech turn
 *       e.g. https://openparliament.ca/committees/justice/45-1/29/larry-brock-1/
 *     The meeting URL is everything before the last path segment:
 *       https://openparliament.ca/committees/justice/45-1/29/
 *
 *   - assembly.ab.ca (AB): one URL per meeting (the PDF transcript)
 *       e.g. https://docs.assembly.ab.ca/.../20260413_1030_01_hs.pdf
 *
 *   - hansard-bc (BC): one URL per document; in practice these are
 *     mostly Committee-of-the-Whole sittings flagged as 'committee' by
 *     the chamber parser, not standing-committee transcripts. See
 *     timeline.md § BC Committee-of-the-Whole misclassification.
 *
 * SQL groups on:
 *   CASE WHEN source_url LIKE '%openparliament.ca/committees/%'
 *        THEN regexp_replace(source_url, '/[^/]+/?$', '/')
 *        ELSE source_url
 *   END AS meeting_url
 *
 * Returned shape per meeting: { meeting_url, level, province_territory,
 * source_system, date (date of first speech), first_spoken_at,
 * last_spoken_at, speech_count }.
 *
 * For full-text search inside committee transcripts use
 * /api/v1/search/speeches?speech_type=committee (and the public-API pair
 * /api/public/v1/search/speeches).
 */

const listQuery = z.object({
  level: z.enum(["federal", "provincial", "municipal"]).optional(),
  province_territory: z.string().length(2).optional(),
  source_system: z.string().max(64).optional(),
  from: z.string().regex(/^\d{4}-\d{2}-\d{2}$/).optional(),
  to: z.string().regex(/^\d{4}-\d{2}-\d{2}$/).optional(),
  page: z.coerce.number().int().min(1).default(1),
  limit: z.coerce.number().int().min(1).max(100).default(50),
});

const MEETING_URL_EXPR = `CASE
        WHEN s.source_url LIKE '%openparliament.ca/committees/%'
          THEN regexp_replace(s.source_url, '/[^/]+/?$', '/')
        ELSE s.source_url
      END`;

export default async function committeeMeetingRoutes(app: FastifyInstance) {
  // ── GET /api/v1/committees/meetings ─────────────────────────────
  app.get("/meetings", async (req, reply) => {
    const q = listQuery.safeParse(req.query);
    if (!q.success) return reply.badRequest(q.error.message);
    const { level, province_territory, source_system, from, to, page, limit } = q.data;
    const offset = (page - 1) * limit;

    const where: string[] = ["s.speech_type = 'committee'"];
    const params: (string | number)[] = [];
    if (level)              { params.push(level);              where.push(`s.level = $${params.length}`); }
    if (province_territory) { params.push(province_territory); where.push(`s.province_territory = $${params.length}`); }
    if (source_system)      { params.push(source_system);      where.push(`s.source_system = $${params.length}`); }
    if (from)               { params.push(from);               where.push(`s.spoken_at >= $${params.length}`); }
    if (to)                 { params.push(to);                 where.push(`s.spoken_at <= $${params.length}`); }
    const whereSql = `WHERE ${where.join(" AND ")}`;

    // Count distinct meetings (not speeches).
    const total = (await queryOne<{ n: number }>(
      `
      SELECT COUNT(*)::int AS n FROM (
        SELECT 1 FROM speeches s
        ${whereSql}
        GROUP BY ${MEETING_URL_EXPR}, s.level, s.province_territory, s.source_system
      ) sub
      `,
      params,
    ))?.n ?? 0;

    const items = await query(
      `
      SELECT
        ${MEETING_URL_EXPR}     AS meeting_url,
        s.level,
        s.province_territory,
        s.source_system,
        MIN(s.spoken_at)::date  AS date,
        MIN(s.spoken_at)        AS first_spoken_at,
        MAX(s.spoken_at)        AS last_spoken_at,
        COUNT(*)::int           AS speech_count
      FROM speeches s
      ${whereSql}
      GROUP BY ${MEETING_URL_EXPR}, s.level, s.province_territory, s.source_system
      ORDER BY MIN(s.spoken_at) DESC NULLS LAST
      LIMIT ${limit} OFFSET ${offset}
      `,
      params,
    );

    return { items, page, limit, total, pages: Math.max(1, Math.ceil(total / limit)) };
  });
}
