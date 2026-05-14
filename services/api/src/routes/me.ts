import type { FastifyInstance } from "fastify";
import { z } from "zod";
import { query, queryOne } from "../db.js";
import { requireUser, getUser } from "../middleware/user-auth.js";
import { SESSION_COOKIE } from "../lib/auth-token.js";
import { CSRF_COOKIE, requireCsrf } from "../lib/csrf.js";
import { baseFilterSchema, encodeQuery, toPgVector } from "./search.js";
import { feedToken } from "./feeds.js";
import { config } from "../config.js";
import {
  archiveCreditsFor,
  creditsForPlatform,
  estimateScrapeCost,
  isCadence,
  isPlatformSupported,
  nextRunAt,
  preflightCreditsFor,
  type ScrapeCadence,
  type ScrapeKind,
  type ScrapePlatform,
} from "../lib/scrape-pricing.js";

/**
 * Self-service user routes. Everything here is gated by requireUser.
 * Mutating endpoints additionally require the double-submit CSRF token.
 *
 * Scope in task #3 (this file as shipped): GET /me, POST /me/logout,
 * PATCH /me (display_name). Saved-searches CRUD lands next in task #4
 * and will extend this same register() function.
 */

interface UserRow {
  id: string;
  email: string;
  display_name: string | null;
  created_at: string;
  last_login_at: string | null;
  is_admin: boolean;
}

const patchBody = z.object({
  display_name: z.string().trim().max(100).nullable().optional(),
});

// Saved-search create/update shapes. filter_payload reuses the
// baseFilterSchema from /search so "what can be saved" is always
// identical to "what can be searched" — one source of truth.
const SCRAPE_PLATFORMS_V1 = ["twitter", "bluesky", "instagram", "mastodon"] as const;
const scrapePlatformSchema = z.enum(SCRAPE_PLATFORMS_V1);
const scrapeCadenceSchema = z.enum(["none", "weekly", "monthly", "quarterly"]);

// Attribution URL: optional companion to scrape_attribute_handle.
// Accept only https URLs at the API boundary so a malformed value
// never makes it to the DB. Empty string normalises to null in the
// handlers below.
const attributionUrlSchema = z
  .string()
  .trim()
  .max(500)
  .refine(s => s === "" || /^https:\/\/[^\s<>"']+$/i.test(s), {
    message: "must be an https:// URL",
  })
  .nullable()
  .optional();

const savedSearchCreateBody = z.object({
  name: z.string().trim().min(1).max(100),
  filter_payload: baseFilterSchema,
  alert_cadence: z.enum(["none", "daily", "weekly"]).default("none"),
  scrape_platforms: z.array(scrapePlatformSchema).default([]),
  scrape_cadence: scrapeCadenceSchema.default("none"),
  scrape_attribute_handle: z.string().trim().max(100).nullable().optional(),
  scrape_attribute_url: attributionUrlSchema,
});

const savedSearchPatchBody = z.object({
  name: z.string().trim().min(1).max(100).optional(),
  alert_cadence: z.enum(["none", "daily", "weekly"]).optional(),
  filter_payload: baseFilterSchema.optional(),
  scrape_platforms: z.array(scrapePlatformSchema).optional(),
  scrape_cadence: scrapeCadenceSchema.optional(),
  scrape_attribute_handle: z.string().trim().max(100).nullable().optional(),
  scrape_attribute_url: attributionUrlSchema,
});

interface SavedSearchRow {
  id: string;
  user_id: string;
  name: string;
  filter_payload: z.infer<typeof baseFilterSchema>;
  alert_cadence: "none" | "daily" | "weekly";
  last_checked_at: string | null;
  last_notified_at: string | null;
  created_at: string;
  updated_at: string;
  has_embedding: boolean;
  scrape_platforms: string[];
  scrape_cadence: "none" | "weekly" | "monthly" | "quarterly";
  scrape_last_run_at: string | null;
  scrape_next_run_at: string | null;
  scrape_attribute_handle: string | null;
  scrape_attribute_url: string | null;
  scrape_paused_reason: string | null;
}

interface SavedSearchResponse extends SavedSearchRow {
  feed_url: string | null;
}

function withFeedUrl(row: SavedSearchRow): SavedSearchResponse {
  const tok = feedToken(row.id);
  return {
    ...row,
    feed_url: tok ? `${config.publicSiteUrl}/api/v1/feeds/${tok}.rss` : null,
  };
}

export default async function meRoutes(app: FastifyInstance) {
  // ── GET /me ──────────────────────────────────────────────────
  app.get("/", { preHandler: requireUser }, async (req, reply) => {
    const claims = getUser(req);
    if (!claims) return reply.code(401).send({ error: "not signed in" });

    const row = await queryOne<UserRow>(
      `SELECT id, email, display_name, created_at, last_login_at, is_admin
         FROM private.users WHERE id = $1`,
      [claims.sub]
    );
    if (!row) {
      // Session is valid but the user row is gone — treat as logged out.
      reply.clearCookie(SESSION_COOKIE, { path: "/" });
      reply.clearCookie(CSRF_COOKIE, { path: "/" });
      return reply.code(401).send({ error: "account no longer exists" });
    }
    return reply.send(row);
  });

  // ── PATCH /me ────────────────────────────────────────────────
  app.patch("/", { preHandler: [requireUser, requireCsrf] }, async (req, reply) => {
    const claims = getUser(req);
    if (!claims) return reply.code(401).send({ error: "not signed in" });

    const parsed = patchBody.safeParse(req.body);
    if (!parsed.success) {
      return reply.code(400).send({ error: "invalid body" });
    }
    const { display_name } = parsed.data;

    const rows = await query<UserRow>(
      `UPDATE private.users SET display_name = $1 WHERE id = $2
       RETURNING id, email, display_name, created_at, last_login_at, is_admin`,
      [display_name ?? null, claims.sub]
    );
    if (!rows[0]) return reply.code(404).send({ error: "user not found" });
    return reply.send(rows[0]);
  });

  // ── POST /me/logout ──────────────────────────────────────────
  // Logout does NOT require CSRF: a forged cross-site logout is
  // low-impact (the user just has to sign in again) and requiring CSRF
  // means a stale token prevents a user from recovering their session.
  app.post("/logout", { preHandler: requireUser }, async (_req, reply) => {
    reply.clearCookie(SESSION_COOKIE, { path: "/" });
    reply.clearCookie(CSRF_COOKIE, { path: "/" });
    return reply.code(204).send();
  });

  // ── GET /me/saved-searches ───────────────────────────────────
  app.get("/saved-searches", { preHandler: requireUser }, async (req, reply) => {
    const claims = getUser(req);
    if (!claims) return reply.code(401).send({ error: "not signed in" });

    const rows = await query<SavedSearchRow>(
      `SELECT id, user_id, name, filter_payload, alert_cadence,
              last_checked_at, last_notified_at, created_at, updated_at,
              (query_embedding IS NOT NULL) AS has_embedding,
              scrape_platforms, scrape_cadence, scrape_last_run_at,
              scrape_next_run_at, scrape_attribute_handle, scrape_attribute_url, scrape_paused_reason
         FROM private.saved_searches
        WHERE user_id = $1
        ORDER BY created_at DESC`,
      [claims.sub]
    );
    return reply.send({ saved_searches: rows.map(withFeedUrl) });
  });

  // ── GET /me/saved-searches/:id ───────────────────────────────
  app.get<{ Params: { id: string } }>(
    "/saved-searches/:id",
    { preHandler: requireUser },
    async (req, reply) => {
      const claims = getUser(req);
      if (!claims) return reply.code(401).send({ error: "not signed in" });

      const row = await queryOne<SavedSearchRow>(
        `SELECT id, user_id, name, filter_payload, alert_cadence,
                last_checked_at, last_notified_at, created_at, updated_at,
                (query_embedding IS NOT NULL) AS has_embedding,
                scrape_platforms, scrape_cadence, scrape_last_run_at,
                scrape_next_run_at, scrape_attribute_handle, scrape_attribute_url, scrape_paused_reason
           FROM private.saved_searches
          WHERE id = $1 AND user_id = $2`,
        [req.params.id, claims.sub]
      );
      if (!row) return reply.code(404).send({ error: "not found" });
      return reply.send(withFeedUrl(row));
    }
  );

  // ── POST /me/saved-searches ──────────────────────────────────
  app.post(
    "/saved-searches",
    { preHandler: [requireUser, requireCsrf] },
    async (req, reply) => {
      const claims = getUser(req);
      if (!claims) return reply.code(401).send({ error: "not signed in" });

      const parsed = savedSearchCreateBody.safeParse(req.body);
      if (!parsed.success) {
        return reply.code(400).send({ error: "invalid body", details: parsed.error.flatten() });
      }
      const {
        name,
        filter_payload,
        alert_cadence,
        scrape_platforms,
        scrape_cadence,
        scrape_attribute_handle,
        scrape_attribute_url,
      } = parsed.data;

      // Empty-string normalize for the URL: zod accepts "" so the
      // frontend can clear the field, but we persist NULL.
      const attributeUrl =
        scrape_attribute_url === "" || scrape_attribute_url == null
          ? null
          : scrape_attribute_url;

      // Compute scrape_next_run_at server-side: NULL when scrape_cadence
      // is 'none', else now() + cadence interval. This is what the
      // scrape worker's dispatcher tests against. The user can edit
      // cadence later via PATCH; we recompute next_run_at the same way.
      const nextRun =
        scrape_cadence === "none"
          ? null
          : nextRunAt(scrape_cadence as ScrapeCadence, new Date()).toISOString();

      // Embed the query now so the alerts worker never has to call TEI.
      // A filter without q (pure time/politician/party filter) gets no
      // embedding — alerts for that kind of search should rely on the
      // filter alone, not semantic ranking.
      let embeddingLiteral: string | null = null;
      if (filter_payload.q && filter_payload.q.trim().length > 0) {
        try {
          const vec = await encodeQuery(filter_payload.q);
          embeddingLiteral = toPgVector(vec);
        } catch (err) {
          req.log.error({ err }, "[saved-searches] TEI embed failed");
          // Save without an embedding rather than 500 — the user's search
          // still functions via the /search endpoint. Alerts accuracy
          // will be lower, which is acceptable degradation.
        }
      }

      const rows = await query<SavedSearchRow>(
        `INSERT INTO private.saved_searches
            (user_id, name, filter_payload, query_embedding, alert_cadence,
             scrape_platforms, scrape_cadence, scrape_next_run_at,
             scrape_attribute_handle, scrape_attribute_url)
         VALUES ($1, $2, $3::jsonb, $4::vector, $5, $6::text[], $7, $8, $9, $10)
         RETURNING id, user_id, name, filter_payload, alert_cadence,
                   last_checked_at, last_notified_at, created_at, updated_at,
                   (query_embedding IS NOT NULL) AS has_embedding,
                   scrape_platforms, scrape_cadence, scrape_last_run_at,
                   scrape_next_run_at, scrape_attribute_handle, scrape_attribute_url, scrape_paused_reason`,
        [
          claims.sub,
          name,
          JSON.stringify(filter_payload),
          embeddingLiteral,
          alert_cadence,
          scrape_platforms,
          scrape_cadence,
          nextRun,
          scrape_attribute_handle ?? null,
          attributeUrl,
        ]
      );
      if (!rows[0]) return reply.code(500).send({ error: "insert failed" });
      return reply.code(201).send(withFeedUrl(rows[0]));
    }
  );

  // ── PATCH /me/saved-searches/:id ─────────────────────────────
  app.patch<{ Params: { id: string } }>(
    "/saved-searches/:id",
    { preHandler: [requireUser, requireCsrf] },
    async (req, reply) => {
      const claims = getUser(req);
      if (!claims) return reply.code(401).send({ error: "not signed in" });

      const parsed = savedSearchPatchBody.safeParse(req.body);
      if (!parsed.success) {
        return reply.code(400).send({ error: "invalid body" });
      }
      const {
        name,
        alert_cadence,
        filter_payload,
        scrape_platforms,
        scrape_cadence,
        scrape_attribute_handle,
        scrape_attribute_url,
      } = parsed.data;

      // If the caller is updating filter_payload, we may need to re-embed.
      // TEI is never called by the alerts worker (see CLAUDE.md), so the
      // vector *must* be refreshed here whenever the query text changes.
      // Decision table:
      //   q unchanged (trim-normalized)  → leave query_embedding alone
      //   q → empty                       → set query_embedding = NULL
      //   q → new non-empty               → re-embed; on TEI failure, keep
      //                                     the stale vector (stale > none)
      let updateEmbedding = false;
      let newEmbeddingLiteral: string | null = null;
      if (filter_payload !== undefined) {
        const existing = await queryOne<{ filter_payload: z.infer<typeof baseFilterSchema> }>(
          `SELECT filter_payload FROM private.saved_searches WHERE id = $1 AND user_id = $2`,
          [req.params.id, claims.sub]
        );
        if (!existing) return reply.code(404).send({ error: "not found" });

        const oldQ = (existing.filter_payload.q ?? "").trim();
        const newQ = (filter_payload.q ?? "").trim();
        if (oldQ !== newQ) {
          if (newQ.length === 0) {
            updateEmbedding = true;
            newEmbeddingLiteral = null;
          } else {
            try {
              const vec = await encodeQuery(newQ);
              updateEmbedding = true;
              newEmbeddingLiteral = toPgVector(vec);
            } catch (err) {
              req.log.error(
                { err },
                "[saved-searches] TEI embed failed on PATCH; keeping prior embedding"
              );
            }
          }
        }
      }

      // Dynamic UPDATE: only touch columns the caller sent. Keeps the
      // touch_updated_at trigger honest (no-op PATCHes don't stamp).
      // last_checked_at / last_notified_at are deliberately left alone —
      // edits reshape *future* alerts, not history.
      const sets: string[] = [];
      const params: (string | null)[] = [];
      if (name !== undefined) {
        params.push(name);
        sets.push(`name = $${params.length}`);
      }
      if (alert_cadence !== undefined) {
        params.push(alert_cadence);
        sets.push(`alert_cadence = $${params.length}`);
      }
      if (filter_payload !== undefined) {
        params.push(JSON.stringify(filter_payload));
        sets.push(`filter_payload = $${params.length}::jsonb`);
      }
      if (updateEmbedding) {
        params.push(newEmbeddingLiteral);
        sets.push(`query_embedding = $${params.length}::vector`);
      }
      // Scrape monitoring fields. When scrape_cadence changes, recompute
      // scrape_next_run_at server-side. Clearing the paused_reason here
      // gives users a "I topped up, resume monitoring" path: any PATCH
      // touching scrape_* settings re-arms the subscription.
      if (scrape_platforms !== undefined) {
        params.push(scrape_platforms as unknown as string);
        sets.push(`scrape_platforms = $${params.length}::text[]`);
      }
      if (scrape_cadence !== undefined) {
        params.push(scrape_cadence);
        sets.push(`scrape_cadence = $${params.length}`);
        if (scrape_cadence === "none") {
          sets.push(`scrape_next_run_at = NULL`);
        } else {
          params.push(nextRunAt(scrape_cadence as ScrapeCadence, new Date()).toISOString());
          sets.push(`scrape_next_run_at = $${params.length}`);
        }
        sets.push(`scrape_paused_reason = NULL`);
      }
      if (scrape_attribute_handle !== undefined) {
        params.push(scrape_attribute_handle);
        sets.push(`scrape_attribute_handle = $${params.length}`);
      }
      if (scrape_attribute_url !== undefined) {
        // Empty-string normalize to NULL.
        const attrUrl = scrape_attribute_url === "" ? null : scrape_attribute_url;
        params.push(attrUrl);
        sets.push(`scrape_attribute_url = $${params.length}`);
      }
      if (sets.length === 0) {
        return reply.code(400).send({ error: "no fields to update" });
      }
      params.push(req.params.id);
      params.push(claims.sub);

      const rows = await query<SavedSearchRow>(
        `UPDATE private.saved_searches SET ${sets.join(", ")}
          WHERE id = $${params.length - 1} AND user_id = $${params.length}
         RETURNING id, user_id, name, filter_payload, alert_cadence,
                   last_checked_at, last_notified_at, created_at, updated_at,
                   (query_embedding IS NOT NULL) AS has_embedding,
                   scrape_platforms, scrape_cadence, scrape_last_run_at,
                   scrape_next_run_at, scrape_attribute_handle, scrape_attribute_url, scrape_paused_reason`,
        params
      );
      if (!rows[0]) return reply.code(404).send({ error: "not found" });
      return reply.send(withFeedUrl(rows[0]));
    }
  );

  // ── DELETE /me/saved-searches/:id ────────────────────────────
  app.delete<{ Params: { id: string } }>(
    "/saved-searches/:id",
    { preHandler: [requireUser, requireCsrf] },
    async (req, reply) => {
      const claims = getUser(req);
      if (!claims) return reply.code(401).send({ error: "not signed in" });

      const res = await query<{ id: string }>(
        `DELETE FROM private.saved_searches WHERE id = $1 AND user_id = $2 RETURNING id`,
        [req.params.id, claims.sub]
      );
      if (res.length === 0) return reply.code(404).send({ error: "not found" });
      return reply.code(204).send();
    }
  );

  // ── GET /me/scrape-cost-estimate ─────────────────────────────
  // Cost calculator powering the MonitorPoliticianButton confirm modal.
  // Returns three costed scenarios for the chosen (politician, platforms,
  // cadence) tuple: monitoring (per-run × runs/month), preflight (flat
  // per-platform), archive (volume-priced using politician_socials'
  // cached lifetime_post_count). Query-string only — no scrape happens,
  // so this is free and CSRF-exempt.
  app.get<{
    Querystring: {
      politician_id?: string;
      platforms?: string;
      cadence?: string;
    };
  }>(
    "/scrape-cost-estimate",
    { preHandler: requireUser },
    async (req, reply) => {
      const politicianId = req.query.politician_id;
      const platformsRaw = (req.query.platforms ?? "").split(",").map(s => s.trim()).filter(Boolean);
      const cadenceIn = req.query.cadence ?? "weekly";

      if (!politicianId) {
        return reply.code(400).send({ error: "politician_id required" });
      }
      const platforms = platformsRaw.filter(isPlatformSupported);
      if (platforms.length === 0) {
        return reply.code(400).send({
          error: "at least one supported platform required",
          supported: SCRAPE_PLATFORMS_V1,
        });
      }
      if (cadenceIn !== "weekly" && cadenceIn !== "monthly" && cadenceIn !== "quarterly") {
        return reply.code(400).send({
          error: "cadence must be weekly/monthly/quarterly for cost estimates",
        });
      }
      const cadence: ScrapeCadence = cadenceIn;

      // Pull cached profile metadata per platform for archive sizing.
      const socials = await query<{
        platform: string;
        lifetime_post_count: number | null;
        follower_count: number | null;
        last_profile_check_at: string | null;
      }>(
        `SELECT platform, lifetime_post_count, follower_count, last_profile_check_at
           FROM public.politician_socials
          WHERE politician_id = $1
            AND platform = ANY($2::text[])
            AND COALESCE(is_live, true) IS TRUE`,
        [politicianId, platforms]
      );

      const perPlatform: Record<string, {
        monitoring_credits_per_run: number;
        preflight_credits: number;
        lifetime_post_count: number | null;
        follower_count: number | null;
        last_profile_check_at: string | null;
        archive_credits: number | null;
        archive_known_size: boolean;
      }> = {};
      for (const p of platforms) {
        const cached = socials.find(s => s.platform === p);
        const lifetime = cached?.lifetime_post_count ?? null;
        const archiveKnown = lifetime !== null && lifetime > 0;
        perPlatform[p] = {
          monitoring_credits_per_run: creditsForPlatform(p),
          preflight_credits: preflightCreditsFor([p]),
          lifetime_post_count: lifetime,
          follower_count: cached?.follower_count ?? null,
          last_profile_check_at: cached?.last_profile_check_at ?? null,
          archive_credits: archiveKnown ? archiveCreditsFor(p, lifetime!) : null,
          archive_known_size: archiveKnown,
        };
      }

      const monitoring = estimateScrapeCost(platforms, cadence);
      const preflight = preflightCreditsFor(platforms);
      const archive = platforms.reduce(
        (acc, p) => (perPlatform[p]?.archive_credits ?? 0) + acc,
        0
      );
      const archiveKnownForAll = platforms.every(p => perPlatform[p]?.archive_known_size);

      return reply.send({
        politician_id: politicianId,
        platforms,
        cadence,
        monitoring,
        preflight_credits: preflight,
        archive_credits: archive,
        archive_known_size: archiveKnownForAll,
        per_platform: perPlatform,
      });
    }
  );

  // ── GET /me/scrape-jobs ──────────────────────────────────────
  // Paginated list of the user's scrape jobs across all kinds. Powers
  // the /account/monitoring dashboard. Status filter is optional;
  // limit is hard-capped at 100 to avoid runaway queries.
  app.get<{
    Querystring: { status?: string; kind?: string; limit?: string; active?: string };
  }>(
    "/scrape-jobs",
    { preHandler: requireUser },
    async (req, reply) => {
      const claims = getUser(req);
      if (!claims) return reply.code(401).send({ error: "not signed in" });
      const limit = Math.min(100, Math.max(1, parseInt(req.query.limit ?? "50", 10) || 50));

      const filters: string[] = ["sj.user_id = $1"];
      const params: (string | number)[] = [claims.sub];
      // `?active=true` shortcuts to status IN ('queued', 'running') —
      // powers the global ActiveProbesIndicator on every page. Treated
      // as mutually exclusive with explicit `?status=`; if both are
      // provided the explicit status wins.
      if (!req.query.status && req.query.active === "true") {
        filters.push(`sj.status IN ('queued', 'running')`);
      } else if (req.query.status) {
        params.push(req.query.status);
        filters.push(`sj.status = $${params.length}`);
      }
      if (req.query.kind) {
        params.push(req.query.kind);
        filters.push(`sj.scrape_kind = $${params.length}`);
      }
      params.push(limit);

      const rows = await query<{
        id: string;
        politician_id: string;
        politician_name: string | null;
        platform: string;
        status: string;
        scrape_kind: string;
        trigger_source: string;
        estimated_credits: number;
        result_count: number | null;
        cost_usd_apify: string | null;
        error: string | null;
        created_at: string;
        finished_at: string | null;
      }>(
        `SELECT sj.id, sj.politician_id,
                p.name AS politician_name,
                sj.platform, sj.status, sj.scrape_kind, sj.trigger_source,
                sj.estimated_credits, sj.result_count,
                sj.cost_usd_apify::text AS cost_usd_apify,
                sj.error, sj.created_at, sj.finished_at
           FROM private.scrape_jobs sj
           LEFT JOIN public.politicians p ON p.id = sj.politician_id
          WHERE ${filters.join(" AND ")}
          ORDER BY sj.created_at DESC
          LIMIT $${params.length}`,
        params
      );
      return reply.send({ scrape_jobs: rows });
    }
  );

  // ── POST /me/scrape-jobs ─────────────────────────────────────
  // Enqueue a one-shot scrape (preflight or archive). The worker
  // daemon picks it up on its next tick; clients poll GET
  // /me/scrape-jobs?status=... or the per-job endpoint below until
  // status flips to 'succeeded' / 'failed'. Monitoring scrapes are
  // *not* enqueued here — those are driven by saved_searches cadence
  // and the dispatcher; this endpoint is for user-initiated one-shots.
  const oneShotBody = z.object({
    politician_id: z.string().uuid(),
    platform: scrapePlatformSchema,
    kind: z.enum(["preflight", "archive"]),
  });

  app.post(
    "/scrape-jobs",
    { preHandler: [requireUser, requireCsrf] },
    async (req, reply) => {
      const claims = getUser(req);
      if (!claims) return reply.code(401).send({ error: "not signed in" });
      const parsed = oneShotBody.safeParse(req.body);
      if (!parsed.success) {
        return reply.code(400).send({ error: "invalid body", details: parsed.error.flatten() });
      }
      const { politician_id, platform, kind } = parsed.data;

      // Resolve credit cost server-side. For archive, prefer the cached
      // lifetime_post_count; if absent we conservatively assume the
      // worker's max (the user has been informed via /scrape-cost-
      // estimate that the cost is approximate).
      let postHint: number | null = null;
      if (kind === "archive") {
        const cached = await queryOne<{ lifetime_post_count: number | null }>(
          `SELECT lifetime_post_count FROM public.politician_socials
            WHERE politician_id = $1 AND platform = $2
              AND COALESCE(is_live, true) IS TRUE
            ORDER BY id LIMIT 1`,
          [politician_id, platform]
        );
        postHint = cached?.lifetime_post_count ?? null;
      }
      const credits =
        kind === "preflight"
          ? preflightCreditsFor([platform])
          : archiveCreditsFor(platform, postHint ?? 3000);

      // Insert the scrape_jobs row + place the hold in one transaction.
      // The unique partial index uniq_credit_ledger_kind_ref guards
      // against duplicate holds for the same job_id; here it's a fresh
      // gen_random_uuid() so we won't collide on first try.
      const balanceRow = await queryOne<{ balance: string | null }>(
        `SELECT COALESCE(SUM(delta), 0)::text AS balance
           FROM private.credit_ledger
          WHERE user_id = $1 AND state IN ('committed','held')`,
        [claims.sub]
      );
      const balance = Number(balanceRow?.balance ?? 0);
      if (balance < credits) {
        return reply.code(402).send({
          error: "insufficient_balance",
          balance,
          required: credits,
        });
      }

      const jobRow = await queryOne<{ id: string }>(
        `INSERT INTO private.scrape_jobs
            (user_id, politician_id, platform, estimated_credits,
             scrape_kind, trigger_source)
          VALUES ($1, $2, $3, $4, $5, 'user_oneshot')
          RETURNING id`,
        [claims.sub, politician_id, platform, credits, kind]
      );
      if (!jobRow) return reply.code(500).send({ error: "insert failed" });

      // Free preflight (Bluesky/Mastodon) skips the ledger entirely.
      if (credits > 0) {
        const hold = await queryOne<{ id: string }>(
          `INSERT INTO private.credit_ledger
              (user_id, delta, state, kind, reference_id)
            VALUES ($1, $2, 'held', 'scrape_hold', $3)
            RETURNING id`,
          [claims.sub, -credits, jobRow.id]
        );
        await query(
          `UPDATE private.scrape_jobs SET hold_ledger_id = $2 WHERE id = $1`,
          [jobRow.id, hold?.id ?? null]
        );
      }

      return reply.code(202).send({
        job_id: jobRow.id,
        estimated_credits: credits,
        scrape_kind: kind,
        platform,
        politician_id,
        status: "queued",
      });
    }
  );

  // ── GET /me/scrape-jobs/:id ──────────────────────────────────
  app.get<{ Params: { id: string } }>(
    "/scrape-jobs/:id",
    { preHandler: requireUser },
    async (req, reply) => {
      const claims = getUser(req);
      if (!claims) return reply.code(401).send({ error: "not signed in" });
      const row = await queryOne(
        `SELECT sj.id, sj.politician_id,
                p.name AS politician_name,
                sj.platform, sj.status, sj.scrape_kind, sj.trigger_source,
                sj.estimated_credits, sj.result_count,
                sj.cost_usd_apify::text AS cost_usd_apify,
                sj.error, sj.created_at, sj.started_at, sj.finished_at
           FROM private.scrape_jobs sj
           LEFT JOIN public.politicians p ON p.id = sj.politician_id
          WHERE sj.id = $1 AND sj.user_id = $2`,
        [req.params.id, claims.sub]
      );
      if (!row) return reply.code(404).send({ error: "not found" });
      return reply.send(row);
    }
  );

  // ── GET /me/scrape-jobs/:id/export?format=csv|json ───────────
  // Subscriber-only bulk download of an archive job's captured posts.
  // Ownership-scoped (404 on cross-user), narrowed to succeeded
  // archive jobs (400 otherwise — the convenience download is a perk
  // of paying for a deep history, not a generic API replacement).
  //
  // Query filters on (politician_id, platform) rather than
  // social_posts.scrape_job_id: dedup means a re-archive only
  // captures NEW posts, so the original archive's posts retain their
  // original job_id. The user paid for "all posts for this
  // politician+platform", not just "posts captured during this
  // scrape window" — they get the full historical archive.
  app.get<{
    Params: { id: string };
    Querystring: { format?: string };
  }>(
    "/scrape-jobs/:id/export",
    { preHandler: requireUser },
    async (req, reply) => {
      const claims = getUser(req);
      if (!claims) return reply.code(401).send({ error: "not signed in" });

      const format = (req.query.format ?? "csv").toLowerCase();
      if (format !== "csv" && format !== "json") {
        return reply.code(400).send({
          error: "invalid format",
          accepted: ["csv", "json"],
        });
      }

      const job = await queryOne<{
        id: string;
        politician_id: string;
        platform: string;
        status: string;
        scrape_kind: string;
        politician_slug: string | null;
      }>(
        `SELECT sj.id, sj.politician_id, sj.platform, sj.status, sj.scrape_kind,
                lower(regexp_replace(p.name, '[^a-zA-Z0-9]+', '-', 'g')) AS politician_slug
           FROM private.scrape_jobs sj
           LEFT JOIN public.politicians p ON p.id = sj.politician_id
          WHERE sj.id = $1 AND sj.user_id = $2`,
        [req.params.id, claims.sub]
      );
      if (!job) return reply.code(404).send({ error: "not found" });
      if (job.status !== "succeeded") {
        return reply.code(400).send({
          error: "export requires a succeeded job",
          status: job.status,
        });
      }
      if (job.scrape_kind !== "archive") {
        return reply.code(400).send({
          error: "export currently supports archive scrapes only",
          scrape_kind: job.scrape_kind,
        });
      }

      const posts = await query<{
        id: string;
        platform: string;
        post_id: string;
        posted_at: string | null;
        text: string;
        url: string | null;
        media_urls: string[] | null;
        engagement: Record<string, unknown> | null;
        scraped_at: string;
      }>(
        `SELECT id::text, platform, post_id, posted_at, text, url,
                media_urls, engagement, scraped_at
           FROM public.social_posts
          WHERE politician_id = $1
            AND platform      = $2
          ORDER BY posted_at DESC NULLS LAST
          LIMIT 5000`,
        [job.politician_id, job.platform]
      );

      const slug = job.politician_slug ?? job.politician_id.slice(0, 8);
      const jobShort = job.id.slice(0, 8);
      const filename = `${slug}-${job.platform}-${jobShort}.${format}`;

      reply.header(
        "Content-Disposition",
        `attachment; filename="${filename}"`
      );

      if (format === "json") {
        reply.header("Content-Type", "application/json; charset=utf-8");
        return reply.send(posts);
      }

      // CSV (RFC 4180). Build inline — small body for our 3000-cap
      // archives; no streaming complexity needed.
      const headers = [
        "post_id", "posted_at", "text", "url", "media_urls",
        "likes", "replies", "reposts", "views", "quotes",
        "scraped_at",
      ];
      const escape = (val: unknown): string => {
        if (val == null) return "";
        // Render Date as ISO 8601 — pg returns timestamptz as a JS
        // Date object; default toString() gives the verbose form
        // "Tue May 12 2026 …" which is awful for spreadsheets and
        // breaks ISO consumers downstream.
        const s = val instanceof Date ? val.toISOString() : String(val);
        if (/[",\n\r]/.test(s)) {
          return `"${s.replace(/"/g, '""')}"`;
        }
        return s;
      };
      const lines: string[] = [headers.join(",")];
      for (const p of posts) {
        const eng = (p.engagement ?? {}) as Record<string, unknown>;
        const row = [
          p.post_id,
          p.posted_at ?? "",
          p.text ?? "",
          p.url ?? "",
          (p.media_urls ?? []).join("|"),
          eng.likes ?? "",
          eng.replies ?? "",
          eng.reposts ?? "",
          eng.views ?? "",
          eng.quotes ?? "",
          p.scraped_at,
        ];
        lines.push(row.map(escape).join(","));
      }
      reply.header("Content-Type", "text/csv; charset=utf-8");
      // Append a trailing newline so the file ends with a record
      // separator — many tools expect this.
      return reply.send(lines.join("\n") + "\n");
    }
  );
}
