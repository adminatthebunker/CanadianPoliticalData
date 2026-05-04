import type { FastifyInstance } from "fastify";
import { z } from "zod";
import { config } from "../config.js";
import { pool, query, queryOne } from "../db.js";
import { resolvePhotoUrl } from "../lib/photos.js";
import { requireUser, getUser } from "../middleware/user-auth.js";

// Instruction prefix for Qwen3-Embedding-0.6B query encoding.
// Indexing pipeline (scanner/src/legislative/speech_embedder.py) writes
// documents UNWRAPPED — this prefix is retrieval-time only. Omitting it
// drops NDCG@10 from 0.43 to 0.22 per services/embed/eval/REPORT.md.
const INSTRUCT_PREFIX =
  "Instruct: Given a parliamentary search query, retrieve relevant Canadian Hansard speech excerpts\nQuery: ";

// Shared filter fields for /speeches and /facets. Both handlers accept
// the same shape; /speeches adds page+limit on top.
// Exported so /me/saved-searches can reuse the exact validation shape —
// single source of truth for "what's a valid search".
// `politician_id` is the legacy singular field; `politician_ids` is the
// canonical multi-select form. Both are accepted for backward compat
// (existing URLs, already-stored saved_searches rows) and collapsed via
// `effectivePoliticianIds()` at SQL-build time. New writes should use
// `politician_ids` exclusively.
// Fastify parses repeated URL params (`?politician_id=a&politician_id=b`)
// as a string[]. Accept either form and let effectivePoliticianIds()
// collapse it downstream — keeps the URL convention ergonomic without
// forcing every caller to know about politician_ids.
const politicianIdInput = z.union([
  z.string().uuid(),
  z.array(z.string().uuid()).max(10),
]).optional();

// Speech-type taxonomy populated by ingest. `floor` is the catch-all for
// jurisdictions whose Hansard parsers don't structurally distinguish turn
// types (most provincial PDF feeds); the others are well-populated on
// federal Hansard.
const SPEECH_TYPE_VALUES = [
  "floor",
  "committee",
  "question_period",
  "statement",
  "point_of_order",
  "group",
] as const;

export const baseFilterSchema = z.object({
  q: z.string().trim().max(500).default(""),
  lang: z.enum(["en", "fr", "any"]).default("any"),
  level: z.enum(["federal", "provincial", "municipal"]).optional(),
  province_territory: z.string().length(2).optional(),
  politician_id: politicianIdInput,
  politician_ids: z.array(z.string().uuid()).max(10).optional(),
  party: z.string().max(64).optional(),
  from: z.string().regex(/^\d{4}-\d{2}-\d{2}$/).optional(),
  to: z.string().regex(/^\d{4}-\d{2}-\d{2}$/).optional(),
  exclude_presiding: z.coerce.boolean().optional(),
  // Restrict to speeches by politicians who are currently in office
  // ("active") or no longer in office ("inactive"). Implemented as an
  // EXISTS join to politicians.is_active so unresolved speeches
  // (politician_id IS NULL) are excluded from both sides — an
  // unresolved speaker is neither active nor inactive.
  politician_active: z.enum(["active", "inactive"]).optional(),
  // Cosine-similarity floor (0..1). Applies only when `q` is present —
  // recency-mode browsing has no similarity to threshold against. Mirrors
  // the channel /politician-quotes already uses; the difference is the
  // public /speeches route doesn't impose a server-side 0.45 minimum.
  min_similarity: z.coerce.number().min(0).max(1).optional(),
  // Restrict to speeches inside one (parliament, session) pair. Both must
  // be present together; the resolver looks up `legislative_sessions.id`
  // by (parliament_number, session_number) within the level/province
  // already on the request, so a global "31st Parliament" without
  // jurisdiction context would be ambiguous.
  parliament_number: z.coerce.number().int().positive().max(100).optional(),
  session_number: z.coerce.number().int().positive().max(20).optional(),
  // Multi-select: e.g. `?speech_type=question_period&speech_type=statement`
  // matches the repeated-param convention used by `politician_id`.
  // Coerced to an array regardless of single/multi form so handlers don't
  // have to special-case URLSearchParams' single-value shape.
  speech_type: z.union([
    z.enum(SPEECH_TYPE_VALUES),
    z.array(z.enum(SPEECH_TYPE_VALUES)).max(SPEECH_TYPE_VALUES.length),
  ]).optional(),
  // Anchor-chunk search: rank the corpus by cosine similarity to this
  // chunk's embedding instead of a text query. Mutually exclusive with
  // `q` — when both are present, `q` wins and the anchor is ignored.
  // The anchor itself is excluded from results so it doesn't dominate
  // its own ranking (it would always cosine-distance to 0).
  anchor_chunk_id: z.string().regex(/^[0-9a-f-]{36}$/i).optional(),
});

export function effectivePoliticianIds(
  f: Pick<z.infer<typeof baseFilterSchema>, "politician_id" | "politician_ids">
): string[] {
  const ids: string[] = [];
  if (f.politician_ids) ids.push(...f.politician_ids);
  if (f.politician_id) {
    if (Array.isArray(f.politician_id)) ids.push(...f.politician_id);
    else ids.push(f.politician_id);
  }
  // Dedupe, cap at 10.
  const seen = new Set<string>();
  const out: string[] = [];
  for (const id of ids) {
    if (!seen.has(id) && out.length < 10) {
      seen.add(id);
      out.push(id);
    }
  }
  return out;
}

const searchQuery = baseFilterSchema.extend({
  page: z.coerce.number().int().min(1).default(1),
  limit: z.coerce.number().int().min(1).max(50).default(20),
  // Rendering mode: flat chunk list (default) or one politician per card
  // with their top-N matching chunks underneath. Grouped mode requires
  // `q` because grouping only makes sense when ranked by semantic
  // relevance — a q-less grouped call is a 400.
  group_by: z.enum(["timeline", "politician"]).default("timeline"),
  per_group_limit: z.coerce.number().int().min(1).max(10).default(5),
  // Grouped-mode-only: which per-politician metric decides the top-20.
  // Ignored for group_by=timeline. Default `mentions` answers "who talks
  // about this topic the most" — matches user intuition and the Analysis
  // tab's TOP SPEAKERS list.
  sort: z.enum(["mentions", "best_match", "avg_match", "keyword_hits"]).default("mentions"),
  // Allow callers to skip the (potentially slow) COUNT(*) query and
  // fetch the total via the dedicated /speeches/count endpoint instead.
  // When `include_count=false` the response shape is unchanged but
  // `total` and `pages` are reported as null. Default true so existing
  // bookmarks and integrations keep their previous behaviour. The
  // /search frontend now opts out and stages the count off in parallel
  // because the threshold path on COUNT can't use HNSW (it's a
  // cardinality-of-neighbourhood question, not a top-K one) and on a
  // q-only query against the full 4.9M-chunk corpus it costs ~15s.
  //
  // Manual coercion: z.coerce.boolean() treats the *string* "false" as
  // truthy (Boolean("false") === true), which would silently ignore the
  // opt-out. Coerce to literal-aware boolean here so URL params behave.
  include_count: z
    .union([z.boolean(), z.enum(["true", "false"])])
    .default(true)
    .transform((v) => (typeof v === "boolean" ? v : v === "true")),
});

// Single-politician deep-dive ("show all of X's quotes for query Q").
// Authenticated, rate-limited surface backing the expand-card affordance
// on /search. Extends baseFilterSchema rather than forking it so saved
// filters and pin shares stay compatible. politician_id is overridden to
// required + single-UUID — the multi-pin form doesn't fit the deep-dive
// UX, and a missing id would silently fall through to a global search.
const expandQuery = baseFilterSchema.extend({
  politician_id: z.string().uuid(),
  page: z.coerce.number().int().min(1).default(1),
  limit: z.coerce.number().int().min(1).max(50).default(50),
  // min_similarity inherited from baseFilterSchema; /politician-quotes
  // additionally clamps it to ≥0.45 server-side (see handler) so the
  // baseline "actually matches the query" definition never weakens.
});

type BaseFilter = z.infer<typeof baseFilterSchema>;

interface SpeechSearchRow {
  chunk_id: string;
  speech_id: string;
  chunk_index: number;
  text: string;
  snippet_html: string | null;
  distance: number | null;
  spoken_at: string | null;
  language: "en" | "fr";
  level: string | null;
  province_territory: string | null;
  party_at_time: string | null;
  politician_id: string | null;
  politician_name: string | null;
  politician_slug: string | null;
  politician_photo_url: string | null;
  politician_photo_path: string | null;
  politician_party: string | null;
  politician_socials: Array<{ platform: string; url: string; handle: string | null }> | null;
  speech_speaker_name_raw: string;
  speech_speaker_role: string | null;
  speech_source_url: string | null;
  speech_source_anchor: string | null;
  speech_source_system: string | null;
  parliament_number: number | null;
  session_number: number | null;
  // Per-politician aggregates repeated on every chunk row of a group —
  // the grouping walker just reads them off the first row it sees for
  // each politician_id.
  mention_count?: number;
  best_dist?: number | null;
  avg_dist?: number | null;
  keyword_hits?: number;
}

// Collapses duplicate TEI calls when the same query lands in a short window —
// e.g. burst traffic, paginated repeats. Qwen3 is deterministic per input, so
// a cached vector is semantically identical to re-embedding.
const QUERY_CACHE_MAX = 500;
const QUERY_CACHE_TTL_MS = 60_000;
const queryCache = new Map<string, { vec: number[]; expiresAt: number }>();

export async function encodeQuery(text: string): Promise<number[]> {
  const cacheKey = text.trim().toLowerCase();
  const now = Date.now();
  const hit = queryCache.get(cacheKey);
  if (hit && hit.expiresAt > now) {
    queryCache.delete(cacheKey);
    queryCache.set(cacheKey, hit);
    return hit.vec;
  }
  if (hit) queryCache.delete(cacheKey);

  const wrapped = `${INSTRUCT_PREFIX}${text}`;
  const res = await fetch(`${config.teiUrl}/embed`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ inputs: [wrapped], normalize: true }),
  });
  if (!res.ok) {
    throw new Error(`TEI returned ${res.status}: ${await res.text().catch(() => "")}`);
  }
  const data: unknown = await res.json();
  // TEI default: bare [[...floats...]]. OpenAI-compat: {data: [{embedding: [...]}]}.
  let vec: number[] | null = null;
  if (Array.isArray(data) && Array.isArray((data as unknown[])[0])) {
    vec = (data as number[][])[0] ?? null;
  } else if (data && typeof data === "object" && "data" in data) {
    const d = (data as { data: Array<{ embedding: number[] }> }).data;
    vec = d?.[0]?.embedding ?? null;
  }
  if (!vec) throw new Error("Unexpected TEI /embed response shape");

  if (queryCache.size >= QUERY_CACHE_MAX) {
    const oldest = queryCache.keys().next().value;
    if (oldest !== undefined) queryCache.delete(oldest);
  }
  queryCache.set(cacheKey, { vec, expiresAt: now + QUERY_CACHE_TTL_MS });
  return vec;
}

export function toPgVector(vec: number[]): string {
  // pgvector literal: '[0.1,0.2,...]'. join with "," no spaces for tightness.
  return `[${vec.join(",")}]`;
}

// Anchor-chunk embedding cache. Same LRU shape as queryCache above, but
// keyed by chunk_id directly (chunks don't change after ingest, so a longer
// TTL would be safe — kept at 5min to bound memory under churn).
const ANCHOR_CACHE_MAX = 200;
const ANCHOR_CACHE_TTL_MS = 5 * 60_000;
const anchorCache = new Map<string, { vec: number[]; expiresAt: number }>();

async function resolveAnchorVector(chunkId: string): Promise<number[] | null> {
  const now = Date.now();
  const hit = anchorCache.get(chunkId);
  if (hit && hit.expiresAt > now) {
    anchorCache.delete(chunkId);
    anchorCache.set(chunkId, hit);
    return hit.vec;
  }
  if (hit) anchorCache.delete(chunkId);

  // pgvector returns embeddings as text in the wire protocol when cast.
  // Round-trip through ::text → JSON-parse the bracketed literal.
  const row = await queryOne<{ embedding: string }>(
    `SELECT embedding::text AS embedding FROM speech_chunks WHERE id = $1 AND embedding IS NOT NULL`,
    [chunkId],
  );
  if (!row) return null;
  let vec: number[];
  try {
    vec = JSON.parse(row.embedding) as number[];
  } catch {
    return null;
  }
  if (!Array.isArray(vec) || vec.length === 0) return null;

  if (anchorCache.size >= ANCHOR_CACHE_MAX) {
    const oldest = anchorCache.keys().next().value;
    if (oldest !== undefined) anchorCache.delete(oldest);
  }
  anchorCache.set(chunkId, { vec, expiresAt: now + ANCHOR_CACHE_TTL_MS });
  return vec;
}

export interface SearchVector {
  vec: number[];
  /** When set, callers should append `AND sc.id != $excludeChunkId` so the
   *  anchor doesn't return itself as its own closest match. */
  excludeChunkId: string | null;
  source: "text" | "anchor";
}

/** Resolves the search vector for a request. Text query takes precedence
 *  over anchor when both are present. Returns null when neither is set
 *  (recent-mode browsing). Returns "missing_anchor" when the anchor id was
 *  set but the chunk doesn't exist — callers should 404. */
export async function resolveSearchVector(
  filter: Pick<BaseFilter, "q" | "anchor_chunk_id">,
): Promise<SearchVector | null | "missing_anchor"> {
  const q = filter.q?.trim();
  if (q) {
    const vec = await encodeQuery(q);
    return { vec, excludeChunkId: null, source: "text" };
  }
  if (filter.anchor_chunk_id) {
    const vec = await resolveAnchorVector(filter.anchor_chunk_id);
    if (!vec) return "missing_anchor";
    return { vec, excludeChunkId: filter.anchor_chunk_id, source: "anchor" };
  }
  return null;
}

/** Build the WHERE clause + filter params shared by /speeches and /facets.
 *  Returns filter-only params (no vector, no q-text). Callers append those
 *  at whatever $N index they need and pass the combined array to `query`. */
function buildFilterWhere(f: BaseFilter): {
  whereSql: string;
  filterParams: (string | number | string[])[];
} {
  const where: string[] = ["sc.embedding IS NOT NULL"];
  const filterParams: (string | number | string[])[] = [];
  if (f.lang !== "any") { filterParams.push(f.lang); where.push(`sc.language = $${filterParams.length}`); }
  if (f.level)          { filterParams.push(f.level); where.push(`sc.level = $${filterParams.length}`); }
  if (f.province_territory) { filterParams.push(f.province_territory); where.push(`sc.province_territory = $${filterParams.length}`); }
  const pids = effectivePoliticianIds(f);
  if (pids.length > 0) { filterParams.push(pids); where.push(`sc.politician_id = ANY($${filterParams.length}::uuid[])`); }
  if (f.party)          { filterParams.push(f.party); where.push(`sc.party_at_time = $${filterParams.length}`); }
  if (f.from)           { filterParams.push(f.from); where.push(`sc.spoken_at >= $${filterParams.length}`); }
  if (f.to)             { filterParams.push(f.to);   where.push(`sc.spoken_at < ($${filterParams.length}::date + interval '1 day')`); }
  // Hide presiding-officer turns ("I declare the motion lost", procedural
  // chair speech). Correlated EXISTS scoped to the HNSW candidate pool —
  // negligible cost since the WHERE caps at ~1k chunks.
  if (f.exclude_presiding) {
    where.push(
      `NOT EXISTS (SELECT 1 FROM speeches sx WHERE sx.id = sc.speech_id AND sx.speaker_role IS NOT NULL AND sx.speaker_role <> '')`,
    );
  }
  if (f.politician_active) {
    const wantActive = f.politician_active === "active";
    where.push(
      `EXISTS (SELECT 1 FROM politicians p WHERE p.id = sc.politician_id AND p.is_active = ${wantActive})`,
    );
  }
  // Restrict to a specific (parliament, session) — sc.session_id is
  // already denormalised, so this is a pre-filter against legislative_sessions.
  // Both numbers must be present together; one without the other is ambiguous.
  if (f.parliament_number != null && f.session_number != null) {
    filterParams.push(f.parliament_number);
    const pIdx = filterParams.length;
    filterParams.push(f.session_number);
    const sIdx = filterParams.length;
    where.push(
      `EXISTS (SELECT 1 FROM legislative_sessions ls WHERE ls.id = sc.session_id AND ls.parliament_number = $${pIdx} AND ls.session_number = $${sIdx})`,
    );
  }
  // Speech-type multi-select. Same EXISTS pattern as exclude_presiding;
  // the column lives on speeches, not speech_chunks. Coerce single value
  // → array so the SQL is uniform.
  if (f.speech_type) {
    const types = Array.isArray(f.speech_type) ? f.speech_type : [f.speech_type];
    if (types.length > 0) {
      filterParams.push(types);
      where.push(
        `EXISTS (SELECT 1 FROM speeches sx WHERE sx.id = sc.speech_id AND sx.speech_type = ANY($${filterParams.length}::text[]))`,
      );
    }
  }
  return { whereSql: where.join(" AND "), filterParams };
}

function hasAnyStructuralFilter(f: BaseFilter): boolean {
  const speechTypes = Array.isArray(f.speech_type)
    ? f.speech_type.length > 0
    : Boolean(f.speech_type);
  return Boolean(
    effectivePoliticianIds(f).length > 0 ||
    f.party || f.level || f.province_territory || f.from || f.to ||
    (f.parliament_number != null && f.session_number != null) ||
    speechTypes ||
    f.politician_active
  );
}

type SearchInput = z.infer<typeof searchQuery>;

/** Grouped-by-politician search: return top-K politicians, each with their
 *  top-M chunks on the query, so readers can see one politician's statements
 *  on a topic side-by-side. The core bet: seeing a politician's quotes across
 *  parliaments makes contradictions or evolution visible without any AI
 *  claim. Requires `q` — grouping a recency-ordered result would just be
 *  "whichever politicians spoke most recently", which isn't interesting. */
async function handleGroupedByPolitician(
  app: FastifyInstance,
  reply: import("fastify").FastifyReply,
  input: SearchInput,
) {
  const { q, page, limit, per_group_limit, sort } = input;
  if (!q && !input.anchor_chunk_id) {
    return reply.badRequest("group_by=politician requires a semantic query (`q`) or `anchor_chunk_id`");
  }

  const { whereSql: baseWhereSql, filterParams } = buildFilterWhere(input);
  const resolved = await resolveSearchVector(input);
  if (resolved === "missing_anchor") return reply.notFound("anchor_not_found");
  if (!resolved) {
    // Defensive — guarded above, but keeps the type narrow for downstream.
    return reply.badRequest("could not resolve search vector");
  }
  const vecLiteral = toPgVector(resolved.vec);

  // Anchor mode: exclude the anchor itself + skip the kw_hit ts_query
  // (no text to match). The keyword_hits sort silently degrades to "0
  // for everyone, ranked by mentions / similarity" in that case — a
  // reasonable behaviour given the tab still works on the other sorts.
  let whereSql = baseWhereSql;
  let extraExcludeParam: string | null = null;
  if (resolved.excludeChunkId) {
    extraExcludeParam = resolved.excludeChunkId;
    // append below to unified `params` so $-numbering stays correct
  }

  // Cap politicians per page at 20 regardless of user-supplied limit — the
  // UI renders one card per politician and larger pages get unusable.
  const politicianLimit = Math.min(limit, 20);
  const politicianOffset = (page - 1) * politicianLimit;
  // Pulling 1000 chunk candidates so `mentions`/`keyword_hits` counts are
  // meaningful, not just a function of a too-tight top-500 window.
  // pgvector 0.8.2 caps hnsw.ef_search at 1000; CANDIDATE_POOL tracks
  // that ceiling — exceeding it would silently truncate recall anyway.
  const CANDIDATE_POOL = 1000;
  // Distance threshold for counting a chunk as a "mention" — below this
  // similarity (0.45) Qwen3 results start drifting off-topic for the
  // civic-Hansard corpus. Tuned by eye; revisit if recall complaints.
  // Client may tighten via min_similarity; never loosen below 0.45 so
  // mention_count stays semantically "actually about this topic".
  const MIN_SIMILARITY_FLOOR = 0.45;
  const effectiveMinSimilarity = Math.max(
    MIN_SIMILARITY_FLOOR,
    input.min_similarity ?? 0,
  );
  const MAX_DISTANCE = 1 - effectiveMinSimilarity;

  // Build params/index map dynamically — anchor mode skips the q text
  // param entirely (kw_hit becomes a literal 0). The exclude-id (when in
  // anchor mode) is appended to the *base* filter set so the WHERE clause
  // built above is consistent with the count branch's numbering scheme.
  const params: unknown[] = [...filterParams];
  if (extraExcludeParam) {
    params.push(extraExcludeParam);
    whereSql = `${baseWhereSql} AND sc.id != $${params.length}::uuid`;
  }
  params.push(vecLiteral);
  const vIdx = params.length;
  let qIdx: number | null = null;
  if (q && resolved.source === "text") {
    params.push(q);
    qIdx = params.length;
  }
  params.push(CANDIDATE_POOL);
  const poolIdx = params.length;
  params.push(politicianLimit);
  const plIdx = params.length;
  params.push(politicianOffset);
  const poIdx = params.length;
  params.push(per_group_limit);
  const pglIdx = params.length;
  params.push(MAX_DISTANCE);
  const mdIdx = params.length;
  params.push(sort);
  const sortIdx = params.length;

  const kwHitExpr = qIdx
    ? `(sc.tsv @@ websearch_to_tsquery(COALESCE(sc.tsv_config, 'simple')::regconfig, $${qIdx}))::int`
    : `0`;
  const headlineSnippetExpr = qIdx
    ? `ts_headline(
             COALESCE(r.tsv_config, 'simple')::regconfig,
             r.text,
             websearch_to_tsquery(COALESCE(r.tsv_config, 'simple')::regconfig, $${qIdx}),
             'MaxWords=35, MinWords=15, ShortWord=3, MaxFragments=2, FragmentDelimiter=" … ", HighlightAll=FALSE'
           )`
    : `NULL::text`;

  const sql = `
    WITH candidates AS (
      SELECT sc.id AS chunk_id, sc.speech_id, sc.chunk_index, sc.text, sc.tsv,
             sc.spoken_at, sc.language, sc.level, sc.province_territory,
             sc.party_at_time, sc.politician_id, sc.session_id, sc.tsv_config,
             (sc.embedding <=> $${vIdx}::vector)::float AS distance,
             ${kwHitExpr} AS kw_hit
        FROM speech_chunks sc
       WHERE ${whereSql}
       ORDER BY sc.embedding <=> $${vIdx}::vector
       LIMIT $${poolIdx}
    ),
    qualified AS (
      SELECT * FROM candidates
       WHERE politician_id IS NOT NULL
         AND distance <= $${mdIdx}
    ),
    pol_stats AS (
      SELECT politician_id,
             COUNT(*)::int         AS mention_count,
             MIN(distance)::float  AS best_dist,
             AVG(distance)::float  AS avg_dist,
             SUM(kw_hit)::int      AS keyword_hits
        FROM qualified
       GROUP BY politician_id
    ),
    top_pols AS (
      SELECT * FROM pol_stats
       ORDER BY
         CASE WHEN $${sortIdx} = 'mentions'     THEN -mention_count END ASC,
         CASE WHEN $${sortIdx} = 'keyword_hits' THEN -keyword_hits  END ASC,
         CASE WHEN $${sortIdx} = 'avg_match'    THEN  avg_dist      END ASC,
         CASE WHEN $${sortIdx} = 'best_match'   THEN  best_dist     END ASC,
         best_dist
       LIMIT $${plIdx} OFFSET $${poIdx}
    ),
    ranked AS (
      SELECT q.*, tp.best_dist, tp.avg_dist, tp.mention_count, tp.keyword_hits,
             ROW_NUMBER() OVER (PARTITION BY q.politician_id ORDER BY q.distance) AS rn_in_pol
        FROM qualified q
        JOIN top_pols tp ON tp.politician_id = q.politician_id
    )
    SELECT r.chunk_id, r.speech_id, r.chunk_index, r.text,
           ${headlineSnippetExpr} AS snippet_html,
           r.distance, r.spoken_at, r.language, r.level, r.province_territory,
           r.party_at_time, r.politician_id,
           r.best_dist, r.avg_dist, r.mention_count, r.keyword_hits,
           r.rn_in_pol,
           p.name                        AS politician_name,
           p.openparliament_slug         AS politician_slug,
           p.photo_url                   AS politician_photo_url,
           p.photo_path                  AS politician_photo_path,
           p.party                       AS politician_party,
           socials.items                 AS politician_socials,
           s.speaker_name_raw            AS speech_speaker_name_raw,
           s.speaker_role                AS speech_speaker_role,
           s.source_url                  AS speech_source_url,
           s.source_anchor               AS speech_source_anchor,
           s.source_system               AS speech_source_system,
           ls.parliament_number,
           ls.session_number
      FROM ranked r
      LEFT JOIN politicians p           ON p.id  = r.politician_id
      LEFT JOIN speeches s              ON s.id  = r.speech_id
      LEFT JOIN legislative_sessions ls ON ls.id = s.session_id
      LEFT JOIN LATERAL (
        SELECT jsonb_agg(
                 jsonb_build_object('platform', ps.platform, 'url', ps.url, 'handle', ps.handle)
                 ORDER BY ps.platform
               ) AS items
          FROM politician_socials ps
         WHERE ps.politician_id = p.id
           AND COALESCE(ps.is_live, true)
      ) socials ON true
     WHERE r.rn_in_pol <= $${pglIdx}
     ORDER BY
       CASE WHEN $${sortIdx} = 'mentions'     THEN -r.mention_count END ASC,
       CASE WHEN $${sortIdx} = 'keyword_hits' THEN -r.keyword_hits  END ASC,
       CASE WHEN $${sortIdx} = 'avg_match'    THEN  r.avg_dist      END ASC,
       CASE WHEN $${sortIdx} = 'best_match'   THEN  r.best_dist     END ASC,
       r.best_dist, r.politician_id, r.spoken_at ASC NULLS FIRST
  `;

  // HNSW: ef_search must be ≥ the LIMIT for the index to actually return
  // that many rows; 1000 is the pgvector 0.8.2 maximum. SET LOCAL inside
  // a transaction scopes it so pooled connections don't carry the bump
  // elsewhere.
  const client = await pool.connect();
  let rows: SpeechSearchRow[] = [];
  try {
    await client.query("BEGIN");
    await client.query("SET LOCAL hnsw.ef_search = 1000");
    const res = await client.query(sql, params as unknown as unknown[]);
    rows = res.rows as SpeechSearchRow[];
    await client.query("COMMIT");
  } catch (err) {
    await client.query("ROLLBACK").catch(() => {});
    app.log.error({ err, q, sort }, "grouped search failed");
    throw err;
  } finally {
    client.release();
  }

  // Walk the pre-sorted rows (best_dist, politician_id, spoken_at) and
  // bucket consecutive same-politician rows into one group.
  interface ChunkItem {
    chunk_id: string;
    speech_id: string;
    chunk_index: number;
    text: string;
    snippet_html: string | null;
    similarity: number | null;
    spoken_at: string | null;
    language: "en" | "fr";
    level: string | null;
    province_territory: string | null;
    party_at_time: string | null;
    speech: {
      speaker_name_raw: string;
      speaker_role: string | null;
      source_url: string | null;
      source_anchor: string | null;
      source_system: string | null;
      session: { parliament_number: number; session_number: number } | null;
    };
  }
  interface PoliticianGroup {
    politician: {
      id: string;
      name: string | null;
      slug: string | null;
      photo_url: string | null;
      party: string | null;
      socials: Array<{ platform: string; url: string; handle: string | null }>;
    };
    best_similarity: number | null;
    avg_similarity: number | null;
    mention_count: number;
    keyword_hits: number;
    chunks: ChunkItem[];
  }

  const groups: PoliticianGroup[] = [];
  let current: PoliticianGroup | null = null;
  for (const r of rows) {
    if (!r.politician_id) continue;
    if (!current || current.politician.id !== r.politician_id) {
      current = {
        politician: {
          id: r.politician_id,
          name: r.politician_name,
          slug: r.politician_slug,
          photo_url: resolvePhotoUrl({
            photo_path: r.politician_photo_path,
            photo_url: r.politician_photo_url,
          }),
          party: r.politician_party,
          socials: r.politician_socials ?? [],
        },
        best_similarity: r.best_dist != null ? 1 - r.best_dist : null,
        avg_similarity: r.avg_dist != null ? 1 - r.avg_dist : null,
        mention_count: r.mention_count ?? 0,
        keyword_hits: r.keyword_hits ?? 0,
        chunks: [],
      };
      groups.push(current);
    }
    current.chunks.push({
      chunk_id: r.chunk_id,
      speech_id: r.speech_id,
      chunk_index: r.chunk_index,
      text: r.text,
      snippet_html: r.snippet_html,
      similarity: r.distance !== null ? 1 - r.distance : null,
      spoken_at: r.spoken_at,
      language: r.language,
      level: r.level,
      province_territory: r.province_territory,
      party_at_time: r.party_at_time,
      speech: {
        speaker_name_raw: r.speech_speaker_name_raw,
        speaker_role: r.speech_speaker_role,
        source_url: r.speech_source_url,
        source_anchor: r.speech_source_anchor,
        source_system: r.speech_source_system,
        session:
          r.parliament_number !== null && r.session_number !== null
            ? { parliament_number: r.parliament_number, session_number: r.session_number }
            : null,
      },
    });
  }

  return {
    mode: "grouped",
    group_by: "politician" as const,
    page,
    limit: politicianLimit,
    per_group_limit,
    groups,
    total_politicians: groups.length,
  };
}

/** Timeline-mode search: flat list of chunks, ranked by semantic distance
 *  when `q` is present, else by recency. Used by both the public
 *  /speeches route and the gated /politician-quotes deep-dive route, so
 *  the SQL lives once and both callers share the same response shape.
 *
 *  options.minSimilarity (0..1, requires q) — drop chunks whose cosine
 *  similarity to the query falls below this floor from BOTH the count
 *  and the result set. /politician-quotes passes 0.45, mirroring
 *  handleGroupedByPolitician's MIN_SIMILARITY, so the deep-dive's count
 *  matches the headline `mention_count` on the same card and doesn't
 *  inflate to "every chunk this politician has ever uttered under the
 *  parent search's structural filters". /speeches doesn't pass it, so
 *  the public timeline keeps its existing wide-net behaviour. */
async function runTimelineSearch(
  input: SearchInput,
  options: {
    minSimilarity?: number;
    includeCount?: boolean;
    /** Optional Fastify reply — used to short-circuit with 404 when the
     *  caller passed an `anchor_chunk_id` that doesn't resolve. Callers
     *  that don't pass one get an empty result set instead. */
    reply?: import("fastify").FastifyReply;
  } = {},
) {
  const { q, page, limit } = input;
  const { minSimilarity } = options;
  const includeCount = options.includeCount !== false;
  const offset = (page - 1) * limit;

  const { whereSql: baseWhereSql, filterParams } = buildFilterWhere(input);

  // Resolve the search vector — text query, anchor chunk, or recent-mode.
  // Anchor mode appends `AND sc.id != $exclude` to filter out the anchor
  // itself (it would always cosine-distance to 0 and dominate the ranking).
  const resolved = await resolveSearchVector(input);
  if (resolved === "missing_anchor") {
    const reply = options.reply;
    if (reply) return reply.notFound("anchor_not_found");
    return { items: [], page: 1, limit, total: 0, pages: 0, mode: "recent" as const };
  }
  let queryVecLiteral: string | null = null;
  let excludeChunkId: string | null = null;
  let vectorSource: "text" | "anchor" | null = null;
  if (resolved) {
    queryVecLiteral = toPgVector(resolved.vec);
    excludeChunkId = resolved.excludeChunkId;
    vectorSource = resolved.source;
  }
  const hasVector = queryVecLiteral !== null;

  // Append the anchor-exclusion filter to the shared WHERE so both the
  // count and the main SELECT pick it up.
  let whereSql = baseWhereSql;
  if (excludeChunkId) {
    filterParams.push(excludeChunkId);
    whereSql = `${baseWhereSql} AND sc.id != $${filterParams.length}::uuid`;
  }

  const applyThreshold =
    hasVector && minSimilarity != null && minSimilarity > 0;
  const maxDistance = applyThreshold ? 1 - (minSimilarity as number) : null;

  // Exact count — no cap. The cheap path (no threshold) is just
  // COUNT(*) over the structural filter set, which Postgres answers
  // from indexes in <100ms even at corpus scale. The expensive path
  // (threshold set) requires evaluating cosine distance for each row
  // that passes the structural filters; cost scales with the filter
  // set size and on a q-only query degrades to ~15s. Callers that need
  // results-fast can set include_count=false and fetch the total from
  // /search/speeches/count in parallel — the results query is HNSW-
  // bounded (~50-200ms) regardless of threshold.
  let total: number | null = null;
  if (includeCount) {
    // filterParams already carries the anchor-exclusion param (if any)
    // appended above. The threshold branch adds the vector+distance
    // pair on top so anchor mode can also threshold-count.
    const countParams: (string | number | string[])[] = [...filterParams];
    let countWhere = whereSql;
    if (applyThreshold) {
      countParams.push(queryVecLiteral as string);
      const cvIdx = countParams.length;
      countParams.push(maxDistance as number);
      const cdIdx = countParams.length;
      countWhere = `${whereSql} AND (sc.embedding <=> $${cvIdx}::vector) <= $${cdIdx}`;
    }
    const countRow = await queryOne<{ n: number }>(
      `SELECT COUNT(*)::int AS n
         FROM speech_chunks sc
        WHERE ${countWhere}`,
      countParams,
    );
    total = countRow?.n ?? 0;
  }

  // Build the main SELECT.
  const params: (string | number | string[])[] = [...filterParams];
  let orderBy: string;
  let vectorParamIndex: number | null = null;
  if (hasVector) {
    params.push(queryVecLiteral as string);
    vectorParamIndex = params.length;
    // Single-key ORDER BY: adding a tiebreaker (sc.id) forces Postgres to
    // materialise the full filtered set to satisfy deterministic sort,
    // defeating the HNSW index (8ms → 4400ms on 1.4M rows).
    orderBy = `sc.embedding <=> $${vectorParamIndex}::vector`;
  } else {
    orderBy = "sc.spoken_at DESC NULLS LAST, sc.id";
  }

  // ts_headline uses the per-row tsv_config so highlight tokenisation
  // matches the index used at build time. Only meaningful for text-mode
  // searches — anchor-mode has no string to highlight, so we skip the
  // expression entirely and leave snippet_html null.
  let headlineExpr = "NULL::text";
  if (q && vectorSource === "text") {
    params.push(q);
    const qIdx = params.length;
    headlineExpr = `
      ts_headline(
        COALESCE(sc.tsv_config, 'simple')::regconfig,
        sc.text,
        websearch_to_tsquery(COALESCE(sc.tsv_config, 'simple')::regconfig, $${qIdx}),
        'MaxWords=35, MinWords=15, ShortWord=3, MaxFragments=2, FragmentDelimiter=" … ", HighlightAll=FALSE'
      )`;
  }

  let mainWhere = whereSql;
  if (applyThreshold) {
    // Reuse vectorParamIndex (already pushed above) and add a fresh
    // distance param so this WHERE doesn't share params with the count
    // query's separate paramslist.
    params.push(maxDistance as number);
    const mdIdx = params.length;
    mainWhere = `${whereSql} AND (sc.embedding <=> $${vectorParamIndex}::vector) <= $${mdIdx}`;
  }

  const sql = `
    SELECT
      sc.id                         AS chunk_id,
      sc.speech_id,
      sc.chunk_index,
      sc.text,
      ${headlineExpr}               AS snippet_html,
      ${vectorParamIndex ? `(sc.embedding <=> $${vectorParamIndex}::vector)::float` : "NULL::float"} AS distance,
      sc.spoken_at,
      sc.language,
      sc.level,
      sc.province_territory,
      sc.party_at_time,
      sc.politician_id,
      p.name                        AS politician_name,
      p.openparliament_slug         AS politician_slug,
      p.photo_url                   AS politician_photo_url,
      p.photo_path                  AS politician_photo_path,
      p.party                       AS politician_party,
      socials.items                 AS politician_socials,
      s.speaker_name_raw            AS speech_speaker_name_raw,
      s.speaker_role                AS speech_speaker_role,
      s.source_url                  AS speech_source_url,
      s.source_anchor               AS speech_source_anchor,
      s.source_system               AS speech_source_system,
      ls.parliament_number,
      ls.session_number
    FROM speech_chunks sc
    LEFT JOIN politicians p           ON p.id  = sc.politician_id
    LEFT JOIN speeches   s            ON s.id  = sc.speech_id
    LEFT JOIN legislative_sessions ls ON ls.id = s.session_id
    LEFT JOIN LATERAL (
      SELECT jsonb_agg(
               jsonb_build_object('platform', ps.platform, 'url', ps.url, 'handle', ps.handle)
               ORDER BY ps.platform
             ) AS items
        FROM politician_socials ps
       WHERE ps.politician_id = p.id
         AND COALESCE(ps.is_live, true)
    ) socials ON true
    WHERE ${mainWhere}
    ORDER BY ${orderBy}
    LIMIT ${limit} OFFSET ${offset}
  `;

  const rows = await query<SpeechSearchRow>(sql, params);

  const items = rows.map((r) => ({
    chunk_id: r.chunk_id,
    speech_id: r.speech_id,
    chunk_index: r.chunk_index,
    text: r.text,
    snippet_html: r.snippet_html,
    similarity: r.distance !== null ? 1 - r.distance : null,
    spoken_at: r.spoken_at,
    language: r.language,
    level: r.level,
    province_territory: r.province_territory,
    party_at_time: r.party_at_time,
    politician: r.politician_id
      ? {
          id: r.politician_id,
          name: r.politician_name,
          slug: r.politician_slug,
          photo_url: resolvePhotoUrl({
            photo_path: r.politician_photo_path,
            photo_url: r.politician_photo_url,
          }),
          party: r.politician_party,
          socials: r.politician_socials ?? [],
        }
      : null,
    speech: {
      speaker_name_raw: r.speech_speaker_name_raw,
      speaker_role: r.speech_speaker_role,
      source_url: r.speech_source_url,
      source_anchor: r.speech_source_anchor,
      source_system: r.speech_source_system,
      session:
        r.parliament_number !== null && r.session_number !== null
          ? { parliament_number: r.parliament_number, session_number: r.session_number }
          : null,
    },
  }));

  return {
    items,
    page,
    limit,
    total,
    pages: total != null ? Math.max(1, Math.ceil(total / limit)) : null,
    mode: (hasVector ? "semantic" : "recent") as "semantic" | "recent",
  };
}

export default async function searchRoutes(app: FastifyInstance) {
  app.get("/speeches", async (req, reply) => {
    const parsed = searchQuery.safeParse(req.query);
    if (!parsed.success) return reply.badRequest(parsed.error.message);
    const { group_by } = parsed.data;

    if (group_by === "politician") {
      return handleGroupedByPolitician(app, reply, parsed.data);
    }

    if (
      !parsed.data.q &&
      !parsed.data.anchor_chunk_id &&
      !hasAnyStructuralFilter(parsed.data)
    ) {
      return reply.badRequest("provide `q`, `anchor_chunk_id`, or at least one filter (politician_ids, party, level, province, from, to, parliament+session, speech_type, politician_active)");
    }

    // Default the cosine-similarity floor to 0.5 when not set. Below
    // ~0.5 the corpus produces a long tail of weak associative matches
    // ("environment" → every speech that mentions trees) that drown the
    // ranking signal. The slider on /search lets the user explicitly
    // disable the floor by sending min_similarity=0 — that path stays
    // open for users who want the raw recall behaviour. min_similarity
    // is only meaningful alongside a semantic query; runTimelineSearch
    // already gates on `hasVector && minSimilarity > 0` so recency-mode
    // browsing ignores it harmlessly. Anchor mode opts into the same
    // 0.5 floor — the anchor chunk's neighbourhood beyond ~0.5 cosine
    // becomes weak signal under Qwen3.
    const effectiveMin = parsed.data.min_similarity ?? 0.5;
    return runTimelineSearch(parsed.data, {
      minSimilarity: effectiveMin,
      includeCount: parsed.data.include_count,
      reply,
    });
  });

  // Count-only sibling of /speeches. Same filter shape, but runs only
  // the COUNT query so the frontend can fire it in parallel with a
  // /speeches?include_count=false call and let results render fast
  // while the (potentially slow) total resolves separately. Threshold
  // semantics mirror /speeches exactly so the count and the rendered
  // page agree on what's included.
  app.get("/speeches/count", async (req, reply) => {
    const parsed = baseFilterSchema.safeParse(req.query);
    if (!parsed.success) return reply.badRequest(parsed.error.message);

    if (
      !parsed.data.q &&
      !parsed.data.anchor_chunk_id &&
      !hasAnyStructuralFilter(parsed.data)
    ) {
      return reply.badRequest("provide `q`, `anchor_chunk_id`, or at least one filter (politician_ids, party, level, province, from, to, parliament+session, speech_type, politician_active)");
    }

    const { whereSql: baseWhereSql, filterParams } = buildFilterWhere(parsed.data);
    const effectiveMin = parsed.data.min_similarity ?? 0.5;

    const resolved = await resolveSearchVector(parsed.data);
    if (resolved === "missing_anchor") return reply.notFound("anchor_not_found");
    const hasVector = resolved !== null;
    const applyThreshold = hasVector && effectiveMin > 0;

    let whereSql = baseWhereSql;
    const countParams: (string | number | string[])[] = [...filterParams];
    if (resolved && resolved.excludeChunkId) {
      countParams.push(resolved.excludeChunkId);
      whereSql = `${baseWhereSql} AND sc.id != $${countParams.length}::uuid`;
    }
    let countWhere = whereSql;
    if (applyThreshold && resolved) {
      countParams.push(toPgVector(resolved.vec));
      const cvIdx = countParams.length;
      countParams.push(1 - effectiveMin);
      const cdIdx = countParams.length;
      countWhere = `${whereSql} AND (sc.embedding <=> $${cvIdx}::vector) <= $${cdIdx}`;
    }
    const row = await queryOne<{ n: number }>(
      `SELECT COUNT(*)::int AS n
         FROM speech_chunks sc
        WHERE ${countWhere}`,
      countParams,
    );
    return { total: row?.n ?? 0 };
  });

  // Authenticated deep-dive: every quote one politician has on the query.
  // Backs the "Show all N matching quotes" expand affordance on /search's
  // politician view. Hard-gated behind requireUser + a per-user rate limit
  // so anon callers can't bypass the "sign in to expand" UI by URL — same
  // posture as POST /reports (the established gated-search-feature
  // precedent in this codebase).
  app.get(
    "/politician-quotes",
    {
      preHandler: [requireUser],
      config: {
        rateLimit: {
          max: 60,
          timeWindow: "1 minute",
          keyGenerator: (req) => `expand-quotes:${getUser(req)?.sub ?? req.ip}`,
        },
      },
    },
    async (req, reply) => {
      const parsed = expandQuery.safeParse(req.query);
      if (!parsed.success) return reply.badRequest(parsed.error.message);
      if (!parsed.data.q && !parsed.data.anchor_chunk_id) {
        return reply.badRequest("`q` or `anchor_chunk_id` is required for /politician-quotes");
      }
      // Force timeline mode + collapse to the single requested politician.
      // per_group_limit/sort/group_by don't apply here but SearchInput
      // demands them; supply the schema defaults so runTimelineSearch's
      // shared filter builder works unchanged.
      const input: SearchInput = {
        ...parsed.data,
        politician_id: undefined,
        politician_ids: [parsed.data.politician_id],
        group_by: "timeline",
        per_group_limit: 5,
        sort: "mentions",
        // /politician-quotes is the deep-dive expand surface — its
        // count drives the "Show all N matching quotes" badge so we
        // always want it.
        include_count: true,
      };
      // 0.45 mirrors handleGroupedByPolitician's MIN_SIMILARITY so the
      // deep-dive count matches mention_count on the same card —
      // "actually matching quotes for this query", not "every chunk
      // this MP has ever uttered under the structural filters". Client
      // can tighten further (e.g. 0.7 for "strong matches only") but
      // never loosen below the 0.45 floor.
      const clientMin = parsed.data.min_similarity ?? 0;
      const effectiveMin = Math.max(0.45, clientMin);
      return runTimelineSearch(input, { minSimilarity: effectiveMin, reply });
    }
  );

  app.get("/facets", async (req, reply) => {
    const parsed = baseFilterSchema.safeParse(req.query);
    if (!parsed.success) return reply.badRequest(parsed.error.message);
    const { q } = parsed.data;

    if (
      !q &&
      !parsed.data.anchor_chunk_id &&
      !hasAnyStructuralFilter(parsed.data)
    ) {
      return reply.badRequest("provide `q`, `anchor_chunk_id`, or at least one filter to aggregate");
    }

    const { whereSql: baseWhereSql, filterParams } = buildFilterWhere(parsed.data);
    const params: (string | number | string[])[] = [...filterParams];

    const resolved = await resolveSearchVector(parsed.data);
    if (resolved === "missing_anchor") return reply.notFound("anchor_not_found");
    const hasVector = resolved !== null;

    // Append anchor exclusion to the shared WHERE so the top-N CTE picks
    // it up too.
    let whereSql = baseWhereSql;
    if (resolved && resolved.excludeChunkId) {
      params.push(resolved.excludeChunkId);
      whereSql = `${baseWhereSql} AND sc.id != $${params.length}::uuid`;
    }

    // Mirror the /speeches default — a 0.5 floor unless the caller
    // explicitly opts out with min_similarity=0. Without this the
    // analysis tiles would summarise the top-200 by raw distance,
    // which can include chunks below the user's effective threshold
    // and drift the dashboard "Analyzed top 200 of N" away from the
    // timeline's filtered total.
    const effectiveMin = parsed.data.min_similarity ?? 0.5;
    const applyThreshold = hasVector && effectiveMin > 0;

    // Top-N CTE: 200 semantic-ranked rows when a vector is available
    // (text query OR anchor chunk), else most-recent fallback.
    const ANALYSIS_LIMIT = 200;
    let topCte: string;
    let vectorParamIndex: number | null = null;
    if (resolved) {
      params.push(toPgVector(resolved.vec));
      vectorParamIndex = params.length;
      let topWhere = whereSql;
      if (applyThreshold) {
        params.push(1 - effectiveMin);
        const mdIdx = params.length;
        topWhere = `${whereSql} AND (sc.embedding <=> $${vectorParamIndex}::vector) <= $${mdIdx}`;
      }
      topCte = `
        SELECT sc.id, sc.politician_id, sc.party_at_time, sc.language,
               sc.spoken_at, sc.tsv, sc.tsv_config,
               sc.embedding <=> $${vectorParamIndex}::vector AS dist
          FROM speech_chunks sc
         WHERE ${topWhere}
         ORDER BY sc.embedding <=> $${vectorParamIndex}::vector
         LIMIT ${ANALYSIS_LIMIT}`;
    } else {
      topCte = `
        SELECT sc.id, sc.politician_id, sc.party_at_time, sc.language,
               sc.spoken_at, sc.tsv, sc.tsv_config,
               NULL::float AS dist
          FROM speech_chunks sc
         WHERE ${whereSql}
         ORDER BY sc.spoken_at DESC NULLS LAST, sc.id
         LIMIT ${ANALYSIS_LIMIT}`;
    }

    // Keyword-overlap needs the user's raw query text. Only appended when
    // q is present so numbering stays stable in the else branch.
    let keywordOverlapExpr = "NULL::jsonb";
    if (q) {
      params.push(q);
      const qIdx = params.length;
      keywordOverlapExpr = `
        (SELECT jsonb_build_object(
           'both', COUNT(*) FILTER (
              WHERE t.tsv @@ websearch_to_tsquery(COALESCE(t.tsv_config,'simple')::regconfig, $${qIdx})
           )::int,
           'semantic_only', COUNT(*) FILTER (
              WHERE NOT (t.tsv @@ websearch_to_tsquery(COALESCE(t.tsv_config,'simple')::regconfig, $${qIdx}))
           )::int
         ) FROM top t)`;
    }

    const sql = `
      WITH top AS (${topCte})
      SELECT
        (SELECT COUNT(*)::int FROM top)                                 AS analyzed_count,
        COALESCE((
          SELECT jsonb_agg(row_to_json(x))
            FROM (
              SELECT party_at_time AS party, COUNT(*)::int AS count,
                     ROUND(AVG(1 - dist)::numeric, 3)::float AS avg_similarity
                FROM top
               GROUP BY party_at_time
               ORDER BY count DESC
            ) x
        ), '[]'::jsonb)                                                  AS by_party,
        COALESCE((
          SELECT jsonb_agg(row_to_json(x))
            FROM (
              SELECT t.politician_id,
                     p.name                AS politician_name,
                     p.openparliament_slug AS politician_slug,
                     COUNT(*)::int         AS count,
                     ROUND(AVG(1 - COALESCE(t.dist, 0))::numeric, 3)::float AS avg_similarity
                FROM top t
                LEFT JOIN politicians p ON p.id = t.politician_id
               GROUP BY t.politician_id, p.name, p.openparliament_slug
               ORDER BY count DESC
               LIMIT 10
            ) x
        ), '[]'::jsonb)                                                  AS by_politician,
        COALESCE((
          SELECT jsonb_agg(row_to_json(x))
            FROM (
              SELECT EXTRACT(YEAR FROM spoken_at)::int AS year, COUNT(*)::int AS count
                FROM top
               WHERE spoken_at IS NOT NULL
               GROUP BY 1
               ORDER BY 1
            ) x
        ), '[]'::jsonb)                                                  AS by_year,
        COALESCE((
          SELECT jsonb_agg(row_to_json(x))
            FROM (
              SELECT language, COUNT(*)::int AS count
                FROM top
               GROUP BY language
            ) x
        ), '[]'::jsonb)                                                  AS by_language,
        ${keywordOverlapExpr}                                            AS keyword_overlap
    `;

    interface FacetsRow {
      analyzed_count: number;
      by_party: Array<{ party: string | null; count: number; avg_similarity: number }>;
      by_politician: Array<{
        politician_id: string | null;
        politician_name: string | null;
        politician_slug: string | null;
        count: number;
        avg_similarity: number;
      }>;
      by_year: Array<{ year: number; count: number }>;
      by_language: Array<{ language: "en" | "fr"; count: number }>;
      keyword_overlap: { both: number; semantic_only: number } | null;
    }

    // pgvector HNSW's default `ef_search=40` silently caps the candidate
    // set — a LIMIT 200 against the HNSW index returns only 40 rows
    // unless ef_search is raised. Wrap the facets query in a transaction
    // with SET LOCAL so the change scoped to this statement and doesn't
    // pollute pooled connections.
    const client = await pool.connect();
    let row: FacetsRow | null = null;
    try {
      await client.query("BEGIN");
      await client.query("SET LOCAL hnsw.ef_search = 300");
      try {
        const res = await client.query(sql, params as unknown as unknown[]);
        row = (res.rows[0] as FacetsRow) ?? null;
      } catch (err: unknown) {
        if (q) {
          app.log.warn({ err, q }, "facets query failed with q present; retrying without keyword_overlap");
          const retrySql = sql.replace(keywordOverlapExpr, "NULL::jsonb");
          const retryParams = params.slice(0, -1);
          const res = await client.query(retrySql, retryParams as unknown as unknown[]);
          row = (res.rows[0] as FacetsRow) ?? null;
        } else {
          throw err;
        }
      }
      await client.query("COMMIT");
    } catch (err) {
      await client.query("ROLLBACK").catch(() => {});
      throw err;
    } finally {
      client.release();
    }

    return {
      analyzed_count: row?.analyzed_count ?? 0,
      analysis_limit: ANALYSIS_LIMIT,
      by_party: row?.by_party ?? [],
      by_politician: (row?.by_politician ?? []).map((r) => ({
        politician: r.politician_id
          ? { id: r.politician_id, name: r.politician_name, slug: r.politician_slug }
          : null,
        count: r.count,
        avg_similarity: r.avg_similarity,
      })),
      by_year: row?.by_year ?? [],
      by_language: row?.by_language ?? [],
      keyword_overlap: row?.keyword_overlap ?? null,
      mode: q ? "semantic" : "recent",
    };
  });

  // Session list for the cascading parliament/session dropdown on the
  // search filter UI. Fast, cacheable — the table changes ~once per
  // prorogation. `province` is omitted for federal (matches the existing
  // URL convention from /search/speeches and the page filter).
  const sessionsQuery = z.object({
    level: z.enum(["federal", "provincial", "municipal"]).optional(),
    province: z.string().length(2).optional(),
  });

  app.get("/sessions", async (req, reply) => {
    const parsed = sessionsQuery.safeParse(req.query);
    if (!parsed.success) return reply.badRequest(parsed.error.message);
    const { level, province } = parsed.data;

    const where: string[] = [];
    const params: (string | number)[] = [];
    if (level) { params.push(level); where.push(`level = $${params.length}`); }
    if (province) {
      params.push(province);
      where.push(`province_territory = $${params.length}`);
    } else if (level === "federal") {
      where.push(`province_territory IS NULL`);
    }
    const whereSql = where.length > 0 ? `WHERE ${where.join(" AND ")}` : "";

    interface SessionRow {
      parliament_number: number;
      session_number: number;
      name: string | null;
      start_date: string | null;
      end_date: string | null;
    }
    const rows = await query<SessionRow>(
      `SELECT parliament_number, session_number, name, start_date, end_date
         FROM legislative_sessions
         ${whereSql}
        ORDER BY parliament_number DESC, session_number DESC`,
      params,
    );
    // Browser-side cache for an hour; sessions change ~once per
    // prorogation, never within a request burst.
    reply.header("Cache-Control", "public, max-age=3600");
    return { sessions: rows };
  });

  // Anchor-chunk lookup — the /search frontend's anchor banner uses this
  // to render "currently anchored on <speaker>: <chunk text>" with a
  // single round trip rather than two (chunk → speech_id → speech).
  app.get("/chunks/:id", async (req, reply) => {
    const { id } = req.params as { id: string };
    if (!/^[0-9a-f-]{36}$/i.test(id)) return reply.badRequest("invalid id");
    const row = await queryOne<{
      chunk_id: string;
      speech_id: string;
      text: string;
      char_start: number;
      char_end: number;
      language: string;
      speaker_name_raw: string;
      party_at_time: string | null;
      spoken_at: string | null;
      level: string;
      province_territory: string | null;
      source_url: string;
      source_anchor: string | null;
      source_system: string;
      politician_id: string | null;
      politician_name: string | null;
      politician_slug: string | null;
      politician_photo_url: string | null;
      politician_photo_path: string | null;
      politician_party: string | null;
    }>(
      `
      SELECT sc.id           AS chunk_id,
             sc.speech_id    AS speech_id,
             sc.text,
             sc.char_start, sc.char_end, sc.language,
             s.speaker_name_raw, s.party_at_time, s.spoken_at,
             s.level, s.province_territory, s.source_url, s.source_anchor, s.source_system,
             s.politician_id,
             p.name                AS politician_name,
             p.openparliament_slug AS politician_slug,
             p.photo_url           AS politician_photo_url,
             p.photo_path          AS politician_photo_path,
             p.party               AS politician_party
        FROM speech_chunks sc
        JOIN speeches s          ON s.id = sc.speech_id
        LEFT JOIN politicians p  ON p.id = s.politician_id
       WHERE sc.id = $1
      `,
      [id],
    );
    if (!row) return reply.notFound();
    return {
      chunk_id: row.chunk_id,
      speech_id: row.speech_id,
      text: row.text,
      char_start: row.char_start,
      char_end: row.char_end,
      language: row.language,
      speaker_name_raw: row.speaker_name_raw,
      party_at_time: row.party_at_time,
      spoken_at: row.spoken_at,
      level: row.level,
      province_territory: row.province_territory,
      source_url: row.source_url,
      source_anchor: row.source_anchor,
      source_system: row.source_system,
      politician: row.politician_id
        ? {
            id: row.politician_id,
            name: row.politician_name,
            slug: row.politician_slug,
            photo_url: resolvePhotoUrl({
              photo_path: row.politician_photo_path,
              photo_url: row.politician_photo_url,
            }),
            party: row.politician_party,
          }
        : null,
    };
  });

  app.get("/meta", async () => {
    // Backfill progress surface for the UI banner.
    const row = await queryOne<{ total: number; embedded: number }>(
      `SELECT COUNT(*)::int AS total,
              COUNT(*) FILTER (WHERE embedding IS NOT NULL)::int AS embedded
         FROM speech_chunks`,
    );
    const total = row?.total ?? 0;
    const embedded = row?.embedded ?? 0;
    return {
      total_chunks: total,
      embedded_chunks: embedded,
      coverage: total > 0 ? embedded / total : 0,
    };
  });
}
