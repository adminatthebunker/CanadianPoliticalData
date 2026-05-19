import type { FastifyInstance } from "fastify";
import { z } from "zod";
import { query, queryOne } from "../db.js";

// Filters for GET /bills. Mirrors the search.ts shape: zod coerces query-string
// scalars + the politicians.ts include_count knob is omitted because count is
// always returned (bills are small; 10K cap not relevant here).
const listQuery = z.object({
  level: z.enum(["federal", "provincial", "municipal"]).optional(),
  province_territory: z.string().length(2).optional(),
  session_id: z.string().regex(/^[0-9a-f-]{36}$/i).optional(),
  status: z.string().optional(),
  sponsor_politician_id: z.string().regex(/^[0-9a-f-]{36}$/i).optional(),
  q: z.string().max(200).optional(),
  introduced_from: z.string().regex(/^\d{4}-\d{2}-\d{2}$/).optional(),
  introduced_to: z.string().regex(/^\d{4}-\d{2}-\d{2}$/).optional(),
  page: z.coerce.number().int().min(1).default(1),
  limit: z.coerce.number().int().min(1).max(100).default(50),
});

const idParam = z.object({
  id: z.string().regex(/^[0-9a-f-]{36}$/i),
});

export default async function billRoutes(app: FastifyInstance) {
  // ── GET /api/v1/bills ───────────────────────────────────────────
  app.get("/", async (req, reply) => {
    const q = listQuery.safeParse(req.query);
    if (!q.success) return reply.badRequest(q.error.message);
    const {
      level, province_territory, session_id, status, sponsor_politician_id,
      q: search, introduced_from, introduced_to, page, limit,
    } = q.data;
    const offset = (page - 1) * limit;

    const where: string[] = [];
    const params: (string | number)[] = [];
    if (level)              { params.push(level);              where.push(`b.level = $${params.length}`); }
    if (province_territory) { params.push(province_territory); where.push(`b.province_territory = $${params.length}`); }
    if (session_id)         { params.push(session_id);         where.push(`b.session_id = $${params.length}`); }
    if (status)             { params.push(status);             where.push(`b.status = $${params.length}`); }
    if (introduced_from)    { params.push(introduced_from);    where.push(`b.introduced_date >= $${params.length}`); }
    if (introduced_to)      { params.push(introduced_to);      where.push(`b.introduced_date <= $${params.length}`); }
    if (search)             { params.push(`%${search}%`);      where.push(`(b.title ILIKE $${params.length} OR b.short_title ILIKE $${params.length} OR b.bill_number ILIKE $${params.length})`); }
    if (sponsor_politician_id) {
      params.push(sponsor_politician_id);
      where.push(
        `EXISTS (SELECT 1 FROM bill_sponsors bs
                  WHERE bs.bill_id = b.id AND bs.politician_id = $${params.length})`,
      );
    }
    const whereSql = where.length ? `WHERE ${where.join(" AND ")}` : "";

    const total = (await queryOne<{ n: number }>(
      `SELECT COUNT(*)::int AS n FROM bills b ${whereSql}`,
      params,
    ))?.n ?? 0;

    const items = await query(
      `
      SELECT
        b.id, b.session_id, b.level, b.province_territory,
        b.bill_number, b.title, b.short_title, b.bill_type,
        b.status, b.status_changed_at, b.introduced_date,
        b.source_system, b.source_url, b.first_seen_at, b.updated_at,
        ls.parliament_number, ls.session_number, ls.name AS session_name,
        COALESCE(ev.n, 0)::int AS events_count,
        COALESCE(sp.n, 0)::int AS sponsors_count
      FROM bills b
      JOIN legislative_sessions ls ON ls.id = b.session_id
      LEFT JOIN LATERAL (
        SELECT COUNT(*) AS n FROM bill_events WHERE bill_id = b.id
      ) ev ON true
      LEFT JOIN LATERAL (
        SELECT COUNT(*) AS n FROM bill_sponsors WHERE bill_id = b.id
      ) sp ON true
      ${whereSql}
      ORDER BY b.introduced_date DESC NULLS LAST, b.bill_number
      LIMIT ${limit} OFFSET ${offset}
      `,
      params,
    );

    return { items, page, limit, total, pages: Math.max(1, Math.ceil(total / limit)) };
  });

  // ── GET /api/v1/bills/:id ───────────────────────────────────────
  app.get("/:id", async (req, reply) => {
    const p = idParam.safeParse(req.params);
    if (!p.success) return reply.badRequest(p.error.message);

    const bill = await queryOne(
      `
      SELECT
        b.id, b.session_id, b.level, b.province_territory,
        b.bill_number, b.title, b.short_title, b.bill_type,
        b.status, b.status_changed_at, b.introduced_date,
        b.source_id, b.source_system, b.source_url,
        b.first_seen_at, b.last_fetched_at, b.created_at, b.updated_at,
        ls.parliament_number, ls.session_number, ls.name AS session_name,
        ls.start_date AS session_start_date, ls.end_date AS session_end_date,
        COALESCE(ev.n, 0)::int AS events_count,
        COALESCE(sp.n, 0)::int AS sponsors_count,
        COALESCE(vt.n, 0)::int AS votes_count
      FROM bills b
      JOIN legislative_sessions ls ON ls.id = b.session_id
      LEFT JOIN LATERAL (
        SELECT COUNT(*) AS n FROM bill_events WHERE bill_id = b.id
      ) ev ON true
      LEFT JOIN LATERAL (
        SELECT COUNT(*) AS n FROM bill_sponsors WHERE bill_id = b.id
      ) sp ON true
      LEFT JOIN LATERAL (
        SELECT COUNT(*) AS n FROM votes WHERE bill_id = b.id
      ) vt ON true
      WHERE b.id = $1
      `,
      [p.data.id],
    );
    if (!bill) return reply.notFound();
    return { bill };
  });

  // ── GET /api/v1/bills/:id/events ────────────────────────────────
  app.get("/:id/events", async (req, reply) => {
    const p = idParam.safeParse(req.params);
    if (!p.success) return reply.badRequest(p.error.message);

    const bill = await queryOne<{ id: string }>(
      `SELECT id FROM bills WHERE id = $1`,
      [p.data.id],
    );
    if (!bill) return reply.notFound();

    const events = await query(
      `
      SELECT id, bill_id, stage, stage_label, event_type, outcome,
             committee_name, event_date, source_url, created_at
        FROM bill_events
       WHERE bill_id = $1
       ORDER BY event_date ASC NULLS LAST, created_at ASC
      `,
      [p.data.id],
    );
    return { bill_id: p.data.id, events };
  });

  // ── GET /api/v1/bills/:id/sponsors ──────────────────────────────
  app.get("/:id/sponsors", async (req, reply) => {
    const p = idParam.safeParse(req.params);
    if (!p.success) return reply.badRequest(p.error.message);

    const bill = await queryOne<{ id: string }>(
      `SELECT id FROM bills WHERE id = $1`,
      [p.data.id],
    );
    if (!bill) return reply.notFound();

    const sponsors = await query(
      `
      SELECT bs.id, bs.bill_id, bs.politician_id, bs.sponsor_name_raw,
             bs.role, bs.ordering, bs.created_at,
             p.name AS politician_name,
             p.party AS politician_party,
             p.openparliament_slug
        FROM bill_sponsors bs
        LEFT JOIN politicians p ON p.id = bs.politician_id
       WHERE bs.bill_id = $1
       ORDER BY bs.ordering ASC, bs.created_at ASC
      `,
      [p.data.id],
    );
    return { bill_id: p.data.id, sponsors };
  });
}
