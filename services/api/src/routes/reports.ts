import type { FastifyInstance } from "fastify";
import { z } from "zod";
import { config } from "../config.js";
import { pool, query, queryOne } from "../db.js";
import { getUser, requireUser } from "../middleware/user-auth.js";
import { requireCsrf } from "../lib/csrf.js";
import {
  countRecentReportJobs,
  dailyReportCapForTier,
  estimateAnalysisCost,
  priceAnalysis,
  type AnalysisCostEstimate,
} from "../lib/reports.js";
import { getBalance, holdCredits } from "../lib/credits.js";

/**
 * Premium-reports HTTP surface.
 *
 *   GET  /reports/meta             — public; reports `enabled` + `model`
 *                                     so the frontend can grey the button.
 *   POST /reports/estimate         — requireUser + requireCsrf. Pure read;
 *                                     no hold placed.
 *   POST /reports                  — requireUser + requireCsrf + 5/min.
 *                                     Estimates server-side, places hold,
 *                                     enqueues `report_jobs` row in one
 *                                     transaction.
 *   GET  /me/reports               — caller's reports (newest 50).
 *   GET  /reports/:id              — caller's report by id (404 for non-owner).
 *   POST /reports/:id/bug-report   — caller flags a quality issue.
 *
 * Two endpoints for the "view a report" path — one for browsing the
 * list (`/me/reports`) and one for the viewer page (`/reports/:id`)
 * which is mounted as a standalone route in the frontend (no public
 * chrome) and is the URL emailed to the user when their report is
 * ready.
 */

// Per-kind input shapes. The discriminated union forces every code path
// downstream to handle every kind explicitly — adding a new kind without
// the corresponding case in the dispatcher fails type-check.
//
// search_synthesis and stance_map share the same input shape (chunk_ids
// from the frontend's current search). Both have a per-kind cap of 500
// matching maxChunksFor() — the zod max is the boundary that rejects
// oversized request bodies before any DB work.

const fullReportInputs = z.object({
  kind: z.literal("full_report"),
  politician_id: z.string().uuid(),
  query: z.string().trim().min(2).max(500),
});

const searchAnalysisInputsBase = {
  chunk_ids: z.array(z.string().uuid()).min(1).max(500),
  query: z.string().trim().min(1).max(500),
  filter_payload: z.record(z.unknown()).optional(),
};

const searchSynthesisInputs = z.object({
  kind: z.literal("search_synthesis"),
  ...searchAnalysisInputsBase,
});

const stanceMapInputs = z.object({
  kind: z.literal("stance_map"),
  ...searchAnalysisInputsBase,
});

// Back-compat: bodies missing `kind` default to 'full_report' so existing
// frontend callers continue to work unchanged. Once the frontend always
// sends kind explicitly, the preprocess wrapper can be dropped.
const analysisBody = z.preprocess(
  (input) => {
    if (
      input &&
      typeof input === "object" &&
      !Array.isArray(input) &&
      !("kind" in (input as Record<string, unknown>))
    ) {
      return { ...(input as Record<string, unknown>), kind: "full_report" };
    }
    return input;
  },
  z.discriminatedUnion("kind", [fullReportInputs, searchSynthesisInputs, stanceMapInputs])
);

type AnalysisBody = z.infer<typeof analysisBody>;

const bugReportBody = z.object({
  message: z.string().trim().min(10).max(2000),
});

interface PoliticianRow {
  id: string;
  name: string | null;
}

/** Sentinel for "politician_id from the body doesn't resolve". */
class PoliticianNotFoundError extends Error {
  constructor() {
    super("politician not found");
    this.name = "PoliticianNotFoundError";
  }
}

interface EstimateResult {
  est: AnalysisCostEstimate;
  politician: PoliticianRow | null;
  query: string;
  /**
   * For chunk-driven kinds (search_synthesis / stance_map): the subset
   * of submitted chunk_ids that actually exist in speech_chunks. Cost
   * is priced against this count, not the raw submission, so users
   * don't pay for fabricated UUIDs. NULL for full_report (chunks are
   * resolved later by the worker via HNSW).
   */
  validChunkIds: string[] | null;
}

/**
 * Compute everything needed to render a cost preview OR to enqueue a
 * job for an analysis body. Single source of truth for "what does this
 * request cost?" — POST /estimate calls it for the modal; POST / calls
 * it again server-side before placing the hold (never trust client
 * numbers).
 */
async function estimateForBody(body: AnalysisBody): Promise<EstimateResult> {
  if (body.kind === "full_report") {
    const politician = await queryOne<PoliticianRow>(
      `SELECT id, name FROM politicians WHERE id = $1`,
      [body.politician_id]
    );
    if (!politician) throw new PoliticianNotFoundError();
    const est = await estimateAnalysisCost({
      kind: "full_report",
      politician_id: body.politician_id,
      query: body.query,
    });
    return { est, politician, query: body.query, validChunkIds: null };
  }
  // search_synthesis | stance_map. Validate chunk_ids exist before
  // pricing so fabricated UUIDs don't inflate the user's bill.
  const validRows = await query<{ id: string }>(
    `SELECT id FROM speech_chunks WHERE id = ANY($1::uuid[])`,
    [body.chunk_ids]
  );
  const validIds = validRows.map((r) => r.id);
  const est = priceAnalysis(body.kind, validIds.length);
  return { est, politician: null, query: body.query, validChunkIds: validIds };
}

export default async function reportsRoutes(app: FastifyInstance) {
  // ── GET /meta ────────────────────────────────────────────────
  app.get("/meta", async (_req, reply) => {
    return reply.send({
      enabled: config.reports.enabled,
      model: config.reports.enabled ? config.reports.model : null,
      bucket_size: config.reports.bucketSize,
      max_chunks: config.reports.maxChunks,
      base_cost_credits: config.reports.baseCostCredits,
      per_chunk_bucket_cost: config.reports.perChunkBucketCost,
    });
  });

  // ── POST /estimate ───────────────────────────────────────────
  // Dispatches on `kind`:
  //   full_report      → embed query, HNSW count, price.
  //   search_synthesis → validate chunk_ids exist, price by valid count.
  //   stance_map       → same as search_synthesis (different formula).
  // Response shape is kind-aware: `politician` is populated only for
  // full_report (back-compat); a `kind` field is always present.
  app.post(
    "/estimate",
    { preHandler: [requireUser, requireCsrf] },
    async (req, reply) => {
      if (!config.reports.enabled) {
        return reply.code(503).send({ error: "Premium reports not configured" });
      }
      const parsed = analysisBody.safeParse(req.body);
      if (!parsed.success) {
        return reply.code(400).send({ error: "invalid body", details: parsed.error.flatten() });
      }
      const userId = getUser(req)!.sub;

      let result: { est: AnalysisCostEstimate; politician: PoliticianRow | null; query: string };
      try {
        result = await estimateForBody(parsed.data);
      } catch (err) {
        if (err instanceof PoliticianNotFoundError) {
          return reply.code(404).send({ error: "politician not found" });
        }
        req.log.error({ err, kind: parsed.data.kind }, "[reports] estimate failed");
        return reply.code(502).send({ error: "Failed to estimate report cost" });
      }

      const balance = await getBalance(userId);

      return reply.send({
        kind: parsed.data.kind,
        politician: result.politician
          ? { id: result.politician.id, name: result.politician.name }
          : null,
        query: result.query,
        estimated_chunks: result.est.estimated_chunks,
        candidate_chunks: result.est.candidate_chunks,
        estimated_credits: result.est.estimated_credits,
        capped: result.est.capped,
        balance,
        sufficient: balance >= result.est.estimated_credits,
      });
    }
  );

  // ── POST /reports (enqueue) ──────────────────────────────────
  app.post(
    "/",
    {
      preHandler: [requireUser, requireCsrf],
      config: {
        rateLimit: {
          max: 5,
          timeWindow: "1 minute",
          keyGenerator: (req) => `reports-submit:${getUser(req)?.sub ?? req.ip}`,
        },
      },
    },
    async (req, reply) => {
      if (!config.reports.enabled) {
        return reply.code(503).send({ error: "Premium reports not configured" });
      }
      const parsed = analysisBody.safeParse(req.body);
      if (!parsed.success) {
        return reply.code(400).send({ error: "invalid body", details: parsed.error.flatten() });
      }
      const body = parsed.data;
      const userId = getUser(req)!.sub;
      const tierRow = await queryOne<{ rate_limit_tier: string }>(
        `SELECT rate_limit_tier FROM private.users WHERE id = $1`,
        [userId]
      );
      const tier = tierRow?.rate_limit_tier ?? "default";

      // Tier daily cap. Shared across all kinds — one paid-AI cap per
      // user per day, not per-kind caps that users would have to track.
      const cap = dailyReportCapForTier(tier);
      if (cap !== null) {
        const recent = await countRecentReportJobs(userId);
        if (recent >= cap) {
          return reply.code(429).send({
            error: "daily report limit reached",
            tier,
            limit: cap,
            count: recent,
          });
        }
      }

      // Re-estimate server-side. Never trust the client's numbers.
      let estResult: EstimateResult;
      try {
        estResult = await estimateForBody(body);
      } catch (err) {
        if (err instanceof PoliticianNotFoundError) {
          return reply.code(404).send({ error: "politician not found" });
        }
        req.log.error({ err, kind: body.kind }, "[reports] estimate failed");
        return reply.code(502).send({ error: "Failed to estimate report cost" });
      }
      const est = estResult.est;
      if (est.estimated_chunks < 1) {
        return reply.code(400).send({
          error:
            body.kind === "full_report"
              ? "no matching quotes for this politician + query"
              : "no matching speech chunks for the supplied chunk_ids",
        });
      }

      // Balance check before placing the hold. Race-tight: the unique
      // partial index on (kind='report_hold', reference_id=jobId)
      // makes the hold itself idempotent, but we still want to refuse
      // submission when balance is insufficient before even creating
      // the job row.
      const balance = await getBalance(userId);
      if (balance < est.estimated_credits) {
        return reply.code(402).send({
          error: "insufficient credits",
          balance,
          required: est.estimated_credits,
        });
      }

      // Build the kind-specific INSERT shape. full_report keeps the
      // existing (politician_id, query) columns; new kinds park their
      // chunk_ids + filter_payload in the `inputs` JSONB. Both shapes
      // share kind / estimated_chunks / estimated_credits.
      const inputsPayload =
        body.kind === "full_report"
          ? {}
          : {
              chunk_ids: estResult.validChunkIds ?? [],
              query: body.query,
              filter_payload: body.filter_payload ?? null,
            };
      // politician_id is full_report-only (the new kinds aren't anchored
      // to one politician). query lives on the dedicated column for ALL
      // kinds, which keeps the /me/reports SELECT and the viewer's query
      // display single-source — no COALESCE with inputs->>'query'.
      const politicianIdForRow = body.kind === "full_report" ? body.politician_id : null;
      const queryForRow = body.query;

      // Atomic enqueue + hold. If anything throws inside the
      // transaction (incl. the holdCredits insert hitting the unique
      // index, which would only happen on duplicate submit retries
      // and is fine to surface as a 5xx), nothing persists.
      const client = await pool.connect();
      try {
        await client.query("BEGIN");
        const jobRes = await client.query<{ id: string }>(
          `INSERT INTO private.report_jobs
               (user_id, kind, politician_id, query, inputs, estimated_chunks, estimated_credits)
             VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7)
             RETURNING id`,
          [
            userId,
            body.kind,
            politicianIdForRow,
            queryForRow,
            JSON.stringify(inputsPayload),
            est.estimated_chunks,
            est.estimated_credits,
          ]
        );
        const jobId = jobRes.rows[0]?.id;
        if (!jobId) throw new Error("report_jobs insert returned no id");

        // holdCredits inserts a -delta row in 'held' state with
        // reference_id=jobId. Idempotent via uniq_credit_ledger_kind_ref.
        const holdLedgerId = await holdCredits({
          userId,
          amount: est.estimated_credits,
          reportJobId: jobId,
        });

        await client.query(
          `UPDATE private.report_jobs SET hold_ledger_id = $1 WHERE id = $2`,
          [holdLedgerId, jobId]
        );
        await client.query("COMMIT");

        const balanceAfter = await getBalance(userId);
        return reply.code(201).send({
          id: jobId,
          kind: body.kind,
          estimated_credits: est.estimated_credits,
          balance_after: balanceAfter,
        });
      } catch (err) {
        await client.query("ROLLBACK").catch(() => {});
        req.log.error({ err, userId, kind: body.kind }, "[reports] enqueue failed");
        return reply.code(500).send({ error: "Failed to enqueue report" });
      } finally {
        client.release();
      }
    }
  );

  // GET /api/v1/reports/public/:id — anonymous viewer for reports the
  // owner has flipped to is_public = true. The literal "public" segment
  // sits before the uuid so it can never collide with another :id-shaped
  // route. 404 (not 403) for private reports avoids id enumeration.
  // Returns the same payload shape as /me/reports/:id minus user_id.
  app.get("/public/:id", async (req, reply) => {
    const params = z.object({ id: z.string().uuid() }).safeParse(req.params);
    if (!params.success) return reply.code(404).send({ error: "not found" });
    const row = await queryOne<{
      id: string;
      kind: string;
      politician_id: string | null;
      politician_name: string | null;
      politician_party: string | null;
      query: string | null;
      status: string;
      html: string | null;
      summary: string | null;
      chunk_count_actual: number | null;
      estimated_credits: number;
      model_used: string | null;
      is_public: boolean;
      error: string | null;
      created_at: Date;
      finished_at: Date | null;
    }>(
      `SELECT rj.id,
              rj.kind,
              rj.politician_id,
              p.name  AS politician_name,
              p.party AS politician_party,
              rj.query,
              rj.status,
              rj.html,
              rj.summary,
              rj.chunk_count_actual,
              rj.estimated_credits,
              rj.model_used,
              rj.is_public,
              rj.error,
              rj.created_at,
              rj.finished_at
         FROM private.report_jobs rj
         LEFT JOIN public.politicians p ON p.id = rj.politician_id
        WHERE rj.id = $1
          AND rj.is_public = true
          AND rj.status = 'succeeded'`,
      [params.data.id]
    );
    if (!row) return reply.code(404).send({ error: "report not found" });
    return reply.send({ report: row });
  });
}

export async function meReportsRoutes(app: FastifyInstance) {
  app.get(
    "/",
    { preHandler: [requireUser] },
    async (req, reply) => {
      const userId = getUser(req)!.sub;
      const rows = await query<{
        id: string;
        kind: string;
        politician_id: string | null;
        politician_name: string | null;
        politician_party: string | null;
        query: string | null;
        status: string;
        summary: string | null;
        estimated_credits: number;
        chunk_count_actual: number | null;
        model_used: string | null;
        word_count: number | null;
        is_public: boolean;
        created_at: Date;
        finished_at: Date | null;
        error: string | null;
      }>(
        `SELECT rj.id,
                rj.kind,
                rj.politician_id,
                p.name  AS politician_name,
                p.party AS politician_party,
                rj.query,
                rj.status,
                rj.summary,
                rj.estimated_credits,
                rj.chunk_count_actual,
                rj.model_used,
                rj.is_public,
                CASE
                  WHEN rj.html IS NOT NULL
                    THEN array_length(
                      regexp_split_to_array(
                        trim(regexp_replace(rj.html, '<[^>]+>', ' ', 'g')),
                        '\\s+'
                      ),
                      1
                    )
                  ELSE NULL
                END AS word_count,
                rj.created_at,
                rj.finished_at,
                rj.error
           FROM private.report_jobs rj
           LEFT JOIN public.politicians p ON p.id = rj.politician_id
          WHERE rj.user_id = $1
          ORDER BY rj.created_at DESC
          LIMIT 50`,
        [userId]
      );
      return reply.send({ reports: rows });
    }
  );

  // GET /me/reports/:id → viewer payload (the URL emailed to the user
  // is /reports/:id but the API endpoint sits under /me/reports for
  // the ownership-gated read; the frontend page calls this from the
  // standalone viewer route).
  app.get(
    "/:id",
    { preHandler: [requireUser] },
    async (req, reply) => {
      const params = z.object({ id: z.string().uuid() }).safeParse(req.params);
      if (!params.success) return reply.code(404).send({ error: "not found" });
      const userId = getUser(req)!.sub;
      const row = await queryOne<{
        id: string;
        user_id: string;
        kind: string;
        politician_id: string | null;
        politician_name: string | null;
        politician_party: string | null;
        query: string | null;
        status: string;
        html: string | null;
        summary: string | null;
        chunk_count_actual: number | null;
        estimated_credits: number;
        model_used: string | null;
        is_public: boolean;
        error: string | null;
        created_at: Date;
        finished_at: Date | null;
      }>(
        `SELECT rj.id, rj.user_id,
                rj.kind,
                rj.politician_id,
                p.name AS politician_name,
                p.party AS politician_party,
                rj.query,
                rj.status,
                rj.html,
                rj.summary,
                rj.chunk_count_actual,
                rj.estimated_credits,
                rj.model_used,
                rj.is_public,
                rj.error,
                rj.created_at,
                rj.finished_at
           FROM private.report_jobs rj
           LEFT JOIN public.politicians p ON p.id = rj.politician_id
          WHERE rj.id = $1`,
        [params.data.id]
      );
      // 404 (not 403) for non-owner to avoid id enumeration.
      if (!row || row.user_id !== userId) {
        return reply.code(404).send({ error: "report not found" });
      }
      // Strip user_id from the wire payload; it's already on req.user.
      const { user_id: _omit, ...rest } = row;
      void _omit;
      return reply.send({ report: rest });
    }
  );

  app.post(
    "/:id/bug-report",
    { preHandler: [requireUser, requireCsrf] },
    async (req, reply) => {
      const params = z.object({ id: z.string().uuid() }).safeParse(req.params);
      if (!params.success) return reply.code(404).send({ error: "not found" });
      const parsed = bugReportBody.safeParse(req.body);
      if (!parsed.success) {
        return reply.code(400).send({ error: "invalid body", details: parsed.error.flatten() });
      }
      const userId = getUser(req)!.sub;
      const owner = await queryOne<{ user_id: string }>(
        `SELECT user_id FROM private.report_jobs WHERE id = $1`,
        [params.data.id]
      );
      // 404 for non-owner: same id-enumeration discipline.
      if (!owner || owner.user_id !== userId) {
        return reply.code(404).send({ error: "report not found" });
      }
      const inserted = await queryOne<{ id: string }>(
        `INSERT INTO private.report_bug_reports (report_id, user_id, message)
              VALUES ($1, $2, $3)
              RETURNING id`,
        [params.data.id, userId, parsed.data.message]
      );
      return reply.code(201).send({ id: inserted?.id });
    }
  );

  // PATCH /me/reports/:id/visibility — owner flips is_public.
  // 404 (not 403) for non-owner: same id-enumeration discipline as
  // the viewer fetch.
  app.patch(
    "/:id/visibility",
    { preHandler: [requireUser, requireCsrf] },
    async (req, reply) => {
      const params = z.object({ id: z.string().uuid() }).safeParse(req.params);
      if (!params.success) return reply.code(404).send({ error: "not found" });
      const parsed = z.object({ is_public: z.boolean() }).safeParse(req.body);
      if (!parsed.success) {
        return reply.code(400).send({ error: "invalid body", details: parsed.error.flatten() });
      }
      const userId = getUser(req)!.sub;
      const owner = await queryOne<{ user_id: string; status: string }>(
        `SELECT user_id, status FROM private.report_jobs WHERE id = $1`,
        [params.data.id]
      );
      if (!owner || owner.user_id !== userId) {
        return reply.code(404).send({ error: "report not found" });
      }
      // Only succeeded reports can be made public — unfinished or failed
      // reports have nothing useful to share.
      if (parsed.data.is_public && owner.status !== "succeeded") {
        return reply.code(409).send({ error: "report is not in a shareable state" });
      }
      await query(
        `UPDATE private.report_jobs SET is_public = $1 WHERE id = $2`,
        [parsed.data.is_public, params.data.id]
      );
      return reply.send({ id: params.data.id, is_public: parsed.data.is_public });
    }
  );
}

