import type { FastifyInstance } from "fastify";
import { z } from "zod";
import { query } from "../db.js";

// GET /api/v1/coverage
//
// Public coverage dashboard feed — reads jurisdiction_sources and
// returns one row per Canadian jurisdiction we do (or don't) cover.
// Seeded by db/migrations/0019_jurisdiction_sources.sql; row counts
// (bills_count, speeches_count, etc.) are refreshed by a separate job
// against the live bills / speeches tables.
//
// The frontend renders a table grouped by `bills_status`. No filtering
// by default — coverage is small (16 rows), so we serve the whole set.
// Optional `?status=live` for future use (e.g. a "what's live" widget
// on the lander).
//
// Municipalities (migration 0060) are rows in the same table, marked
// `level = 'municipal'` and pointing at their province via
// `parent_jurisdiction`. They come back in the same flat array,
// ordered so each city immediately follows its parent province; the
// frontend indents on `parent_jurisdiction` rather than nesting, which
// keeps one <table> and one card list.
//
// Caveat on `?status=`: filtering can strip a parent while keeping its
// children, leaving cities visually orphaned. Nothing calls it with a
// status today; a caller that does should re-add parents client-side.

const listQuery = z.object({
  status: z.enum(["live", "partial", "blocked", "none"]).optional(),
});

interface CoverageRow {
  jurisdiction: string;
  legislature_name: string;
  seats: number | null;
  level: "federal" | "provincial" | "municipal";
  parent_jurisdiction: string | null;
  municipality_slug: string | null;
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

export default async function coverageRoutes(app: FastifyInstance) {
  app.get("/", async (req, reply) => {
    const parsed = listQuery.safeParse(req.query);
    if (!parsed.success) return reply.badRequest(parsed.error.message);
    const { status } = parsed.data;

    const rows = await query<CoverageRow>(
      `SELECT jurisdiction, legislature_name, seats,
              level, parent_jurisdiction, municipality_slug,
              bills_status, hansard_status, votes_status, committees_status,
              bills_difficulty, hansard_difficulty, votes_difficulty, committees_difficulty,
              blockers, notes, source_urls,
              bills_count, speeches_count, votes_count, politicians_count,
              last_verified_at, updated_at
         FROM jurisdiction_sources
        ${status ? "WHERE bills_status = $1" : ""}
        ORDER BY
          -- Sort on the parent's key so a city travels with its province,
          -- then put the province itself ahead of its cities.
          CASE WHEN COALESCE(parent_jurisdiction, jurisdiction) = 'federal' THEN 0 ELSE 1 END,
          COALESCE(parent_jurisdiction, jurisdiction),
          CASE WHEN parent_jurisdiction IS NULL THEN 0 ELSE 1 END,
          jurisdiction`,
      status ? [status] : []
    );

    // Rollup counts — convenient for the page header without a second
    // round-trip. Legislatures are classified by their bills pipeline,
    // as they always have been.
    //
    // Municipalities are classified by Hansard instead. A city council
    // passes bylaws, not bills, and we ingest none of them — so a
    // bills-centric rule would file Edmonton under "pending" despite its
    // 256K transcribed speeches. Hansard is the equivalent primary
    // pipeline for a council, so it's the honest axis. Legislature
    // numbers are untouched by this branch.
    const headline = (r: CoverageRow) =>
      r.level === "municipal" ? r.hansard_status : r.bills_status;

    const summary = {
      total: rows.length,
      live: rows.filter(r => headline(r) === "live").length,
      partial: rows.filter(r => headline(r) === "partial").length,
      blocked: rows.filter(r => headline(r) === "blocked").length,
      none: rows.filter(r => headline(r) === "none").length,
    };

    return { jurisdictions: rows, summary };
  });
}
