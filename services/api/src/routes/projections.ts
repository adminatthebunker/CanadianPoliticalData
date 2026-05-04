import type { FastifyInstance } from "fastify";
import { z } from "zod";
import { query, queryOne } from "../db.js";
import { baseFilterSchema, effectivePoliticianIds } from "./search.js";

// Public read-only routes that back /semantic-map.
//
// Three endpoints, all filtered by the same baseFilterSchema as /search:
//
//   GET /projections/clusters/all
//     query: baseFilterSchema (no level/parent — returns all 4 levels)
//     returns one row per cluster across L1..L4 with member_count_filtered
//     for each. Drives the zoom-as-LOD renderer: client loads everything
//     once, gates rendering by camera-distance/apparent-screen-size, no
//     extra round-trips on drilldown.
//
//   GET /projections/clusters       (legacy)
//     query: baseFilterSchema + { cluster_level: 1|2|3|4|5, parent_cluster_id?: int }
//     returns one row per cluster at the given level (optionally restricted
//     to children of parent_cluster_id). Kept for the 2D fallback renderer
//     and any external consumers; the 3D renderer no longer uses it.
//
//   GET /projections/points
//     query: baseFilterSchema + { cluster_id, cluster_level, limit<=2000 }
//     returns individual chunks inside one cluster, with their coordinates
//     and a snippet. Only fired when the user has zoomed into a single
//     L3 cluster (or hovers a smaller-than-N cluster at any level) — the
//     frontend never asks for every point in the corpus.
//
// `cluster_level` is named distinctly from baseFilterSchema's `level`
// (federal/provincial/municipal) to avoid collision when the user
// passes both filters in the same URL.

interface ProjectionRunRow {
  id: string;
  cluster_count_l1: number | null;
  cluster_count_l2: number | null;
  cluster_count_l3: number | null;
  cluster_count_l4: number | null;
  cluster_count_l5: number | null;
  finished_at: string | null;
}

interface ClusterRow {
  id: number;
  parent_id: number | null;
  level: number;
  label: string;
  top_terms: Array<{ term: string; weight: number }> | null;
  member_count: number;
  member_count_filtered: number;
  centroid_x: number | null;
  centroid_y: number | null;
  centroid_z: number | null;
  centroid_x2: number | null;
  centroid_y2: number | null;
  top_chunk_ids: string[];
}

interface PointRow {
  chunk_id: string;
  speech_id: string;
  politician_id: string | null;
  party_at_time: string | null;
  spoken_at: string | null;
  level: string | null;
  province_territory: string | null;
  x: number;
  y: number;
  z: number;
  x2: number;
  y2: number;
  snippet: string;
}

const clustersQuery = baseFilterSchema.extend({
  cluster_level: z.coerce.number().int().min(1).max(5).default(1),
  parent_cluster_id: z.coerce.number().int().positive().optional(),
});

const pointsQuery = baseFilterSchema.extend({
  cluster_level: z.coerce.number().int().min(1).max(5),
  cluster_id: z.coerce.number().int().positive(),
  limit: z.coerce.number().int().min(1).max(2000).default(500),
});

type FilterInput = z.infer<typeof baseFilterSchema>;

// Build a parameterised WHERE clause that constrains the speech_chunks
// alias `ch` against the user's filter. Returns SQL fragment + params
// starting at the supplied $startIdx. Caller appends to its own param
// list and continues numbering from there. Mirrors the shape of
// search.ts's private buildFilterWhere, scoped to filters that actually
// matter for spatial drilldown (no min_similarity, no q, no
// parliament/session — those are search-time concerns).
function buildChunkFilter(
  f: FilterInput, startIdx: number,
): { sql: string; params: (string | number | string[])[] } {
  const where: string[] = [];
  const params: (string | number | string[])[] = [];
  // Allocate the next placeholder *and* push the value in one step so the
  // numbering can never drift. push() returns the new length, so
  // (startIdx + length - 1) is the slot the just-pushed value occupies
  // (1-based positional parameters start at startIdx).
  const add = (v: string | number | string[]): string => {
    const len = params.push(v);
    return `$${startIdx + len - 1}`;
  };

  // Every parameter gets an explicit ::cast — without it, Postgres can't
  // infer types when the filter sits inside a CTE (the projection-route
  // queries do exactly that). pg's prepared-statement protocol bails out
  // with "could not determine data type of parameter $N" on those.
  if (f.lang !== "any") {
    where.push(`ch.language = ${add(f.lang)}::text`);
  }
  if (f.level) {
    where.push(`ch.level = ${add(f.level)}::text`);
  }
  if (f.province_territory) {
    where.push(`ch.province_territory = ${add(f.province_territory)}::text`);
  }
  const pids = effectivePoliticianIds(f);
  if (pids.length > 0) {
    where.push(`ch.politician_id = ANY(${add(pids)}::uuid[])`);
  }
  if (f.party) {
    where.push(`ch.party_at_time = ${add(f.party)}::text`);
  }
  if (f.from) {
    where.push(`ch.spoken_at >= ${add(f.from)}::date`);
  }
  if (f.to) {
    where.push(`ch.spoken_at < (${add(f.to)}::date + interval '1 day')`);
  }
  if (f.exclude_presiding) {
    where.push(
      `NOT EXISTS (SELECT 1 FROM speeches sx WHERE sx.id = ch.speech_id AND sx.speaker_role IS NOT NULL AND sx.speaker_role <> '')`,
    );
  }
  if (f.speech_type) {
    const types = Array.isArray(f.speech_type) ? f.speech_type : [f.speech_type];
    if (types.length > 0) {
      where.push(
        `EXISTS (SELECT 1 FROM speeches sx WHERE sx.id = ch.speech_id AND sx.speech_type = ANY(${add(types)}::text[]))`,
      );
    }
  }
  if (f.politician_active) {
    const wantActive = f.politician_active === "active";
    where.push(
      `EXISTS (SELECT 1 FROM politicians p WHERE p.id = ch.politician_id AND p.is_active = ${wantActive})`,
    );
  }

  return { sql: where.length > 0 ? where.join(" AND ") : "TRUE", params };
}

function clusterCol(level: number): string {
  // Whitelisted lookup so the level can never be a SQL injection vector.
  // baseFilterSchema already z.coerce-checks the int range; this is the
  // belt-and-braces layer.
  switch (level) {
    case 1: return "cluster_id_l1";
    case 2: return "cluster_id_l2";
    case 3: return "cluster_id_l3";
    case 4: return "cluster_id_l4";
    case 5: return "cluster_id_l5";
    default: throw new Error(`invalid cluster level ${level}`);
  }
}

async function getCurrentRun(): Promise<ProjectionRunRow | null> {
  return queryOne<ProjectionRunRow>(
    `SELECT id::text AS id,
            cluster_count_l1, cluster_count_l2, cluster_count_l3,
            cluster_count_l4, cluster_count_l5,
            finished_at
       FROM projection_runs
      WHERE is_current = true
      LIMIT 1`,
  );
}

// /clusters/all uses a single CTE pass over speech_chunk_projections.
// The four UNION ALL legs each group by one cluster_id_lN column, so
// one seq scan + one hash-aggregate pass yields all four level counts.
// Without this bulk path, the prior UI made four serial calls to
// /clusters as users clicked through L1..L4 — each its own full scan.
const allClustersQuery = baseFilterSchema;

export default async function projectionRoutes(app: FastifyInstance) {
  app.get("/clusters/all", async (req, reply) => {
    const parsed = allClustersQuery.safeParse(req.query);
    if (!parsed.success) return reply.badRequest(parsed.error.message);
    const f = parsed.data;

    const run = await getCurrentRun();
    if (!run) {
      return {
        run_id: null,
        clusters: [] as ClusterRow[],
        message: "no current projection run; admin must run `project-embeddings` and `--stage=promote`",
      };
    }

    const filter = buildChunkFilter(f, 2);

    // Skip the per-cluster filter CTE when no filters are set; in that
    // case member_count_filtered ≡ member_count and we can read straight
    // off the speech_clusters table (saves a 4.9M-row seq scan + four
    // hash-aggregates).
    const noFilters = filter.params.length === 0;

    // /clusters/all skips top_terms and top_chunk_ids — the bulk
    // response is for spatial LOD rendering only. The drawer / hover
    // tooltip fetches the full row via /clusters when needed.
    const sql = noFilters
      ? `
        SELECT c.id::int AS id,
               c.parent_id::int AS parent_id,
               c.level::int AS level,
               c.label,
               c.member_count,
               c.member_count AS member_count_filtered,
               c.centroid_x, c.centroid_y, c.centroid_z,
               c.centroid_x2, c.centroid_y2
          FROM speech_clusters c
         WHERE c.run_id = $1::uuid
         ORDER BY c.level ASC, c.member_count DESC
      `
      : `
        WITH filtered AS (
          SELECT p.cluster_id_l1, p.cluster_id_l2,
                 p.cluster_id_l3, p.cluster_id_l4,
                 p.cluster_id_l5
            FROM speech_chunk_projections p
            JOIN speech_chunks ch ON ch.id = p.chunk_id
           WHERE p.run_id = $1::uuid
             AND ${filter.sql}
        ),
        counts AS (
          SELECT cluster_id_l1 AS cluster_id, count(*)::int AS n
            FROM filtered WHERE cluster_id_l1 IS NOT NULL
           GROUP BY 1
          UNION ALL
          SELECT cluster_id_l2, count(*)::int FROM filtered
           WHERE cluster_id_l2 IS NOT NULL GROUP BY 1
          UNION ALL
          SELECT cluster_id_l3, count(*)::int FROM filtered
           WHERE cluster_id_l3 IS NOT NULL GROUP BY 1
          UNION ALL
          SELECT cluster_id_l4, count(*)::int FROM filtered
           WHERE cluster_id_l4 IS NOT NULL GROUP BY 1
          UNION ALL
          SELECT cluster_id_l5, count(*)::int FROM filtered
           WHERE cluster_id_l5 IS NOT NULL GROUP BY 1
        )
        SELECT c.id::int AS id,
               c.parent_id::int AS parent_id,
               c.level::int AS level,
               c.label,
               c.member_count,
               COALESCE(counts.n, 0)::int AS member_count_filtered,
               c.centroid_x, c.centroid_y, c.centroid_z,
               c.centroid_x2, c.centroid_y2
          FROM speech_clusters c
          LEFT JOIN counts ON counts.cluster_id = c.id
         WHERE c.run_id = $1::uuid
         ORDER BY c.level ASC, c.member_count DESC
      `;

    const params: (string | number | string[])[] = [run.id, ...filter.params];

    const clusters = await query<ClusterRow>(sql, params);

    return {
      run_id: run.id,
      cluster_counts: {
        l1: run.cluster_count_l1,
        l2: run.cluster_count_l2,
        l3: run.cluster_count_l3,
        l4: run.cluster_count_l4,
        l5: run.cluster_count_l5,
      },
      clusters,
    };
  });

  app.get("/clusters", async (req, reply) => {
    const parsed = clustersQuery.safeParse(req.query);
    if (!parsed.success) return reply.badRequest(parsed.error.message);
    const f = parsed.data;
    const { cluster_level, parent_cluster_id } = f;

    const run = await getCurrentRun();
    if (!run) {
      return {
        run_id: null,
        cluster_level,
        clusters: [] as ClusterRow[],
        message: "no current projection run; admin must run `project-embeddings` and `--stage=promote`",
      };
    }

    const col = clusterCol(cluster_level);
    const filterStartIdx = parent_cluster_id != null ? 4 : 3;
    const filter = buildChunkFilter(f, filterStartIdx);

    const sql = `
      WITH cluster_filter_counts AS (
        SELECT p.${col} AS cluster_id,
               count(*) AS member_count_filtered
          FROM speech_chunk_projections p
          JOIN speech_chunks ch ON ch.id = p.chunk_id
         WHERE p.run_id = $1::uuid
           AND p.${col} IS NOT NULL
           AND ${filter.sql}
         GROUP BY p.${col}
      )
      SELECT c.id::int AS id,
             c.parent_id::int AS parent_id,
             c.level::int AS level,
             c.label,
             c.top_terms,
             c.member_count,
             COALESCE(cfc.member_count_filtered, 0)::int AS member_count_filtered,
             c.centroid_x, c.centroid_y, c.centroid_z,
             c.centroid_x2, c.centroid_y2,
             ARRAY(SELECT id::text FROM unnest(c.top_chunk_ids) AS id) AS top_chunk_ids
        FROM speech_clusters c
        LEFT JOIN cluster_filter_counts cfc ON cfc.cluster_id = c.id
       WHERE c.run_id = $1::uuid
         AND c.level = $2::smallint
         ${parent_cluster_id != null ? "AND c.parent_id = $3::bigint" : ""}
       ORDER BY c.member_count DESC
    `;

    const params: (string | number | string[])[] = [run.id, cluster_level];
    if (parent_cluster_id != null) params.push(parent_cluster_id);
    params.push(...filter.params);

    const clusters = await query<ClusterRow>(sql, params);

    return {
      run_id: run.id,
      cluster_level,
      parent_cluster_id: parent_cluster_id ?? null,
      clusters,
    };
  });

  app.get("/points", async (req, reply) => {
    const parsed = pointsQuery.safeParse(req.query);
    if (!parsed.success) return reply.badRequest(parsed.error.message);
    const f = parsed.data;
    const { cluster_level, cluster_id, limit } = f;

    const run = await getCurrentRun();
    if (!run) return reply.notFound("no current projection run");

    const col = clusterCol(cluster_level);
    const filterStartIdx = 4;
    const filter = buildChunkFilter(f, filterStartIdx);

    const sql = `
      SELECT p.chunk_id::text AS chunk_id,
             ch.speech_id::text AS speech_id,
             ch.politician_id::text AS politician_id,
             ch.party_at_time,
             ch.spoken_at,
             ch.level,
             ch.province_territory,
             p.x, p.y, p.z, p.x2, p.y2,
             left(ch.text, 240) AS snippet
        FROM speech_chunk_projections p
        JOIN speech_chunks ch ON ch.id = p.chunk_id
       WHERE p.run_id = $1::uuid
         AND p.${col} = $2::bigint
         AND ${filter.sql}
       ORDER BY ch.spoken_at DESC NULLS LAST, p.chunk_id
       LIMIT $3::int
    `;
    const params: (string | number | string[])[] = [run.id, cluster_id, limit];
    params.push(...filter.params);

    const points = await query<PointRow>(sql, params);

    return {
      run_id: run.id,
      cluster_id,
      cluster_level,
      points,
    };
  });

  // Look up projection coords for a small set of chunks. Used by the
  // /search Map tab to position satellites at their actual UMAP positions
  // rather than synthetic radial layout. Capped at 64 IDs per request to
  // keep the URL short and the in-clause cheap.
  app.get("/coords", async (req, reply) => {
    const schema = z.object({
      ids: z
        .string()
        .min(1)
        .transform((s) =>
          s
            .split(",")
            .map((t) => t.trim())
            .filter((t) => /^[0-9a-f-]{36}$/i.test(t)),
        )
        .refine((arr) => arr.length > 0 && arr.length <= 64, {
          message: "ids must be 1–64 valid UUIDs",
        }),
    });
    const parsed = schema.safeParse(req.query);
    if (!parsed.success) return reply.badRequest(parsed.error.message);

    const run = await getCurrentRun();
    if (!run) return { run_id: null, items: [] };

    const ids = parsed.data.ids;
    const items = await query<{
      chunk_id: string;
      x: number;
      y: number;
      z: number;
      x2: number;
      y2: number;
      cluster_id_l3: number | null;
    }>(
      `
      SELECT p.chunk_id::text AS chunk_id, p.x, p.y, p.z, p.x2, p.y2, p.cluster_id_l3
        FROM speech_chunk_projections p
       WHERE p.run_id = $1::uuid
         AND p.chunk_id = ANY ($2::uuid[])
      `,
      [run.id, ids],
    );

    return { run_id: run.id, items };
  });
}
