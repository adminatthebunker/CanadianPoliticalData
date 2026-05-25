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
 * Public socials endpoints (/api/public/v1/politicians/:id/socials,
 * /politicians/:id/posts). Free-tier (requireApiKey only). Mirrors the
 * internal /api/v1/socials/politicians/:id and /posts SQL, but
 * deliberately projects only the public-safe columns — operator
 * enrichment fields (source, confidence, evidence_url,
 * flagged_low_confidence, profile_metadata, posting_velocity_per_week,
 * discovered_at) stay internal.
 *
 * Live-only by default: ?include_dead=true opts back into the full
 * handle history for callers that need is_live=false rows.
 */

const politicianIdParam = z.object({
  id: z
    .string()
    .regex(/^[0-9a-f-]{36}$/i)
    .describe("UUID of the politician"),
});

const socialsQuery = z
  .object({
    include_dead: z.coerce.boolean().optional().describe(
      "If true, include handles where is_live=false. Default: only live handles.",
    ),
  })
  .passthrough();

const postsQuery = z
  .object({
    platform: z
      .string()
      .max(200)
      .optional()
      .describe(
        "Comma-separated platform filter, e.g. twitter,bluesky. " +
          "Allowed values: twitter, bluesky, mastodon, instagram, " +
          "facebook, youtube, tiktok, linkedin, threads.",
      ),
    limit: z.coerce.number().int().min(1).max(200).optional(),
  })
  .passthrough();

export default async function publicV1SocialsRoutes(app: FastifyInstance) {
  app.setValidatorCompiler(validatorCompiler);
  app.setSerializerCompiler(serializerCompiler);
  const a = app.withTypeProvider<ZodTypeProvider>();

  // ── GET /api/public/v1/politicians/:id/socials ────────────────
  a.get(
    "/politicians/:id/socials",
    {
      preHandler: [requireApiKey],
      config: { rateLimit: publicRateLimitConfig },
      schema: {
        tags: ["Politician socials"],
        summary: "Social media handles for one politician",
        description:
          "List of social-media handles tied to this politician across " +
          "platforms (Twitter, Bluesky, Mastodon, Instagram, Facebook, " +
          "YouTube, TikTok, LinkedIn, Threads). Filters to handles where " +
          "is_live=true by default; pass ?include_dead=true to include " +
          "dead/abandoned handles for historical research. 404 on missing " +
          "politician id. Response: `{ items: [{ platform, handle, url, " +
          "follower_count, lifetime_post_count, last_post_at, " +
          "last_profile_check_at, last_verified_at, is_live }, ...] }`. " +
          "Cache-Control: public, max-age=300.",
        params: politicianIdParam,
        querystring: socialsQuery,
      },
    },
    async (req, reply) => {
      const { id } = req.params;
      const { include_dead } = req.query;

      const exists = await queryOne<{ n: number }>(
        `SELECT 1 AS n FROM politicians WHERE id = $1`,
        [id],
      );
      if (!exists) return reply.notFound();

      const items = await query(
        `SELECT platform, handle, url,
                follower_count, lifetime_post_count,
                last_post_at, last_profile_check_at, last_verified_at,
                is_live
           FROM politician_socials
          WHERE politician_id = $1
            ${include_dead ? "" : "AND is_live = true"}
          ORDER BY platform, handle`,
        [id],
      );

      reply.header("Cache-Control", "public, max-age=300");
      return { items };
    },
  );

  // ── GET /api/public/v1/politicians/:id/posts ──────────────────
  // Mirrors the internal /api/v1/socials/politicians/:id/posts shape:
  // public-read of scraped social posts (v2 lifted the
  // subscriber-only gate; framed as public-record per
  // mkdocs/docs/about/disclaimer.md). funded_by attribution comes
  // from the LATERAL join to private.scrape_jobs → saved_searches
  // — only the projected handle/url cross the schema boundary.
  a.get(
    "/politicians/:id/posts",
    {
      preHandler: [requireApiKey],
      config: { rateLimit: publicRateLimitConfig },
      schema: {
        tags: ["Politician socials"],
        summary: "Scraped social posts for one politician",
        description:
          "Public-record posts captured by the paid scrape-monitoring " +
          "pipeline. Filter by ?platform=twitter,bluesky (comma-separated). " +
          "Limit capped at 200, default 50. Each post carries an optional " +
          "`funded_by` field (opt-in attribution from the subscriber whose " +
          "scrape captured it) and `funded_by_url` (optional link). " +
          "Response: `{ items: [{ id, politician_id, platform, post_id, " +
          "posted_at, text, url, media_urls, engagement, scraped_at, " +
          "funded_by, funded_by_url }, ...] }`. " +
          "Cache-Control: public, max-age=60.",
        params: politicianIdParam,
        querystring: postsQuery,
      },
    },
    async (req, reply) => {
      const { id } = req.params;
      const limit = Math.min(200, Math.max(1, req.query.limit ?? 50));
      const platformFilter = (req.query.platform ?? "")
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);

      const params: (string | number | string[])[] = [id];
      let platformClause = "";
      if (platformFilter.length > 0) {
        params.push(platformFilter);
        platformClause = `AND sp.platform = ANY($${params.length}::text[])`;
      }
      params.push(limit);

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
        params,
      );

      reply.header("Cache-Control", "public, max-age=60");
      return { items };
    },
  );
}
