import type { FastifyInstance } from "fastify";
import { query, queryOne } from "../db.js";

// ────────────────────────────────────────────────────────────────
// /api/v1/socials/stats
// /api/v1/socials/politicians/:id
// ────────────────────────────────────────────────────────────────
//
// Phase 5 — surfaces the politician_socials table:
//   - stats: aggregate counts by platform + liveness buckets
//   - per-politician: the ordered list of their normalized handles
//
// Route conventions match politicians.ts (no external validator for
// read-only endpoints).
export default async function socialsRoutes(app: FastifyInstance) {
  app.get("/stats", async () => {
    const byPlatform = await query<{ platform: string; n: number }>(
      `SELECT platform, COUNT(*)::int AS n
         FROM politician_socials
         GROUP BY platform
         ORDER BY n DESC`
    );

    const totals = await queryOne<{
      total: number;
      live: number;
      dead: number;
      never_verified: number;
    }>(
      `SELECT
          COUNT(*)::int                                           AS total,
          COUNT(*) FILTER (WHERE is_live = true)::int             AS live,
          COUNT(*) FILTER (WHERE is_live = false)::int            AS dead,
          COUNT(*) FILTER (WHERE last_verified_at IS NULL)::int   AS never_verified
         FROM politician_socials`
    );

    return {
      by_platform: Object.fromEntries(byPlatform.map(r => [r.platform, r.n])),
      total: totals?.total ?? 0,
      live: totals?.live ?? 0,
      dead: totals?.dead ?? 0,
      never_verified: totals?.never_verified ?? 0,
    };
  });

  app.get("/politicians/:id", async (req, reply) => {
    const { id } = req.params as { id: string };
    const exists = await queryOne<{ n: number }>(
      `SELECT 1 AS n FROM politicians WHERE id = $1`, [id]
    );
    if (!exists) return reply.notFound();

    const items = await query(
      `SELECT id, politician_id, platform, handle, url,
              last_verified_at, is_live, follower_count,
              lifetime_post_count, last_post_at, last_profile_check_at,
              created_at, updated_at
         FROM politician_socials
        WHERE politician_id = $1
        ORDER BY platform, handle`,
      [id]
    );

    return { items };
  });

  // ── GET /api/v1/socials/politicians/:id/posts ───────────────────────
  // Public read of scraped social posts. Anonymous-visible.
  //
  // v2 (shipped 2026-05-12): the EXISTS-on-subscriber gate from v1 is
  // gone. Captured posts are visible to anyone who lands on a
  // politician's profile, matching the public-record framing in
  // mkdocs/docs/about/disclaimer.md and the takedown workflow in
  // mkdocs/docs/about/takedown.md.
  //
  // Attribution: each post carries a `funded_by` field, derived from
  // the `saved_searches.scrape_attribute_handle` opt-in of whichever
  // subscriber's scrape captured it (NULL = anonymous). When multiple
  // subscribers captured the same post, the most-recently-set non-null
  // attribute_handle wins. Subscribers who haven't opted in stay
  // anonymous on the public surface forever (the column is private,
  // never returned).
  //
  // Filter by platform with ?platform=twitter,bluesky. Limit is hard
  // capped at 200 — the frontend paginates client-side from there.
  app.get<{
    Params: { id: string };
    Querystring: { platform?: string; limit?: string };
  }>(
    "/politicians/:id/posts",
    async (req, reply) => {
      const limit = Math.min(200, Math.max(1, parseInt(req.query.limit ?? "50", 10) || 50));
      const platformFilter = (req.query.platform ?? "").split(",").map(s => s.trim()).filter(Boolean);

      const params: (string | number | string[])[] = [req.params.id];
      let platformClause = "";
      if (platformFilter.length > 0) {
        params.push(platformFilter);
        platformClause = `AND sp.platform = ANY($${params.length}::text[])`;
      }
      params.push(limit);

      // The LATERAL subquery picks the most-recent non-null
      // scrape_attribute_handle (and its companion URL) across this
      // post's capturing scrapes. The `private.scrape_jobs →
      // private.saved_searches` join lives entirely inside the
      // LATERAL, returning only the projected `funded_by` text and
      // `funded_by_url` — no other private-schema fields cross the
      // boundary into the public response. v3 (2026-05-12) added the
      // URL projection; the discipline is unchanged.
      const items = await query(
        `SELECT sp.id, sp.politician_id, sp.platform, sp.post_id,
                sp.posted_at, sp.text, sp.url, sp.media_urls,
                sp.engagement, sp.scraped_at,
                attribution.funded_by,
                attribution.funded_by_url
           FROM public.social_posts sp
           LEFT JOIN LATERAL (
             SELECT ss.scrape_attribute_handle AS funded_by,
                    ss.scrape_attribute_url    AS funded_by_url
               FROM private.scrape_jobs sj
               JOIN private.saved_searches ss ON ss.id = sj.saved_search_id
              WHERE sj.politician_id = sp.politician_id
                AND sj.platform      = sp.platform
                AND sj.status        = 'succeeded'
                AND ss.scrape_attribute_handle IS NOT NULL
              ORDER BY sj.finished_at DESC NULLS LAST
              LIMIT 1
           ) attribution ON TRUE
          WHERE sp.politician_id = $1
            ${platformClause}
          ORDER BY sp.posted_at DESC NULLS LAST
          LIMIT $${params.length}`,
        params
      );

      return reply.send({ items });
    }
  );
}
