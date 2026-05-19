import type { FastifyInstance } from "fastify";
import { z } from "zod";
import { query, queryOne } from "../db.js";

const listQuery = z.object({
  level: z.enum(["federal", "provincial", "municipal"]).optional(),
  province_territory: z.string().length(2).optional(),
  session_id: z.string().regex(/^[0-9a-f-]{36}$/i).optional(),
  bill_id: z.string().regex(/^[0-9a-f-]{36}$/i).optional(),
  result: z.enum(["passed", "defeated", "tied", "withdrawn", "deferred"]).optional(),
  vote_type: z.enum(["division", "voice", "acclamation", "consensus"]).optional(),
  occurred_from: z.string().regex(/^\d{4}-\d{2}-\d{2}$/).optional(),
  occurred_to: z.string().regex(/^\d{4}-\d{2}-\d{2}$/).optional(),
  page: z.coerce.number().int().min(1).default(1),
  limit: z.coerce.number().int().min(1).max(100).default(50),
});

const idParam = z.object({
  id: z.string().regex(/^[0-9a-f-]{36}$/i),
});

export default async function voteRoutes(app: FastifyInstance) {
  // ── GET /api/v1/votes ───────────────────────────────────────────
  app.get("/", async (req, reply) => {
    const q = listQuery.safeParse(req.query);
    if (!q.success) return reply.badRequest(q.error.message);
    const {
      level, province_territory, session_id, bill_id, result, vote_type,
      occurred_from, occurred_to, page, limit,
    } = q.data;
    const offset = (page - 1) * limit;

    const where: string[] = [];
    const params: (string | number)[] = [];
    if (level)              { params.push(level);              where.push(`v.level = $${params.length}`); }
    if (province_territory) { params.push(province_territory); where.push(`v.province_territory = $${params.length}`); }
    if (session_id)         { params.push(session_id);         where.push(`v.session_id = $${params.length}`); }
    if (bill_id)            { params.push(bill_id);            where.push(`v.bill_id = $${params.length}`); }
    if (result)             { params.push(result);             where.push(`v.result = $${params.length}`); }
    if (vote_type)          { params.push(vote_type);          where.push(`v.vote_type = $${params.length}`); }
    if (occurred_from)      { params.push(occurred_from);      where.push(`v.occurred_at >= $${params.length}`); }
    if (occurred_to)        { params.push(occurred_to);        where.push(`v.occurred_at <= $${params.length}`); }
    const whereSql = where.length ? `WHERE ${where.join(" AND ")}` : "";

    const total = (await queryOne<{ n: number }>(
      `SELECT COUNT(*)::int AS n FROM votes v ${whereSql}`,
      params,
    ))?.n ?? 0;

    const items = await query(
      `
      SELECT
        v.id, v.session_id, v.level, v.province_territory,
        v.bill_id, v.speech_id,
        v.vote_type, v.occurred_at, v.result,
        v.ayes, v.nays, v.abstentions, v.motion_text,
        v.source_system, v.source_url, v.created_at, v.updated_at,
        ls.parliament_number, ls.session_number, ls.name AS session_name,
        b.bill_number, b.title AS bill_title,
        COALESCE(vp.n, 0)::int AS positions_count
      FROM votes v
      JOIN legislative_sessions ls ON ls.id = v.session_id
      LEFT JOIN bills b ON b.id = v.bill_id
      LEFT JOIN LATERAL (
        SELECT COUNT(*) AS n FROM vote_positions WHERE vote_id = v.id
      ) vp ON true
      ${whereSql}
      ORDER BY v.occurred_at DESC NULLS LAST, v.created_at DESC
      LIMIT ${limit} OFFSET ${offset}
      `,
      params,
    );

    return { items, page, limit, total, pages: Math.max(1, Math.ceil(total / limit)) };
  });

  // ── GET /api/v1/votes/:id ───────────────────────────────────────
  app.get("/:id", async (req, reply) => {
    const p = idParam.safeParse(req.params);
    if (!p.success) return reply.badRequest(p.error.message);

    const vote = await queryOne(
      `
      SELECT
        v.id, v.session_id, v.level, v.province_territory,
        v.bill_id, v.speech_id,
        v.vote_type, v.occurred_at, v.result,
        v.ayes, v.nays, v.abstentions, v.motion_text,
        v.source_system, v.source_url, v.created_at, v.updated_at,
        ls.parliament_number, ls.session_number, ls.name AS session_name,
        b.bill_number, b.title AS bill_title, b.short_title AS bill_short_title,
        COALESCE(vp.n, 0)::int AS positions_count
      FROM votes v
      JOIN legislative_sessions ls ON ls.id = v.session_id
      LEFT JOIN bills b ON b.id = v.bill_id
      LEFT JOIN LATERAL (
        SELECT COUNT(*) AS n FROM vote_positions WHERE vote_id = v.id
      ) vp ON true
      WHERE v.id = $1
      `,
      [p.data.id],
    );
    if (!vote) return reply.notFound();
    return { vote };
  });

  // ── GET /api/v1/votes/:id/positions ─────────────────────────────
  // No pagination — vote_positions is bounded per-vote (≤~350 rows
  // even for the federal chamber).
  app.get("/:id/positions", async (req, reply) => {
    const p = idParam.safeParse(req.params);
    if (!p.success) return reply.badRequest(p.error.message);

    const vote = await queryOne<{ id: string }>(
      `SELECT id FROM votes WHERE id = $1`,
      [p.data.id],
    );
    if (!vote) return reply.notFound();

    const positions = await query(
      `
      SELECT vp.id, vp.vote_id, vp.politician_id, vp.politician_name_raw,
             vp.party_at_time, vp.constituency_at_time, vp.position, vp.created_at,
             p.name AS politician_name,
             p.party AS politician_party_current,
             p.openparliament_slug
        FROM vote_positions vp
        LEFT JOIN politicians p ON p.id = vp.politician_id
       WHERE vp.vote_id = $1
       ORDER BY vp.position, vp.politician_name_raw
      `,
      [p.data.id],
    );
    return { vote_id: p.data.id, positions };
  });
}
