import type { FastifyInstance } from "fastify";
import { z } from "zod";
import { requireApiKey } from "../../middleware/api-key-auth.js";
import { publicRateLimitConfig } from "../../middleware/api-rate-limit.js";
import { proxyToInternal } from "./proxy.js";

/**
 * Public votes endpoints (/api/public/v1/votes/*). Free-tier — same
 * posture as bills (no TEI cost, requireApiKey only). Proxies to
 * /api/v1/votes/*.
 */

const listQuery = z
  .object({
    level: z.enum(["federal", "provincial", "municipal"]).optional(),
    province_territory: z.string().length(2).optional(),
    session_id: z.string().regex(/^[0-9a-f-]{36}$/i).optional(),
    bill_id: z.string().regex(/^[0-9a-f-]{36}$/i).optional(),
    result: z.enum(["passed", "defeated", "tied", "withdrawn", "deferred"]).optional(),
    vote_type: z.enum(["division", "voice", "acclamation", "consensus"]).optional(),
    occurred_from: z.string().regex(/^\d{4}-\d{2}-\d{2}$/).optional(),
    occurred_to: z.string().regex(/^\d{4}-\d{2}-\d{2}$/).optional(),
    page: z.coerce.number().int().min(1).optional(),
    limit: z.coerce.number().int().min(1).max(100).optional(),
  })
  .passthrough();

const idParam = z.object({
  id: z.string().regex(/^[0-9a-f-]{36}$/i),
});

export default async function publicV1VotesRoutes(app: FastifyInstance) {
  const root = app;

  app.get(
    "/votes",
    {
      preHandler: [requireApiKey],
      config: { rateLimit: publicRateLimitConfig },
      schema: {
        tags: ["Votes"],
        summary: "List recorded chamber votes across federal + provinces",
        description:
          "Paginated list of votes (divisions, voice votes, acclamations, " +
          "and NT/NU consensus events). Federal data: 100% politician-FK " +
          "via openparliament_slug. Provincial: division-or-consensus shape " +
          "varies by jurisdiction. Filters: level, province_territory, " +
          "session_id, bill_id, result, vote_type, occurred_from, occurred_to. " +
          "Each item carries denormalized session + bill labels and a " +
          "positions_count (use /votes/:id/positions for the breakdown). " +
          "Response: `{ items: [...], page, limit, total, pages }`.",
        querystring: listQuery,
      },
    },
    async (req, reply) => {
      return proxyToInternal(req, reply, {
        app: root,
        internalUrl: "/api/v1/votes",
      });
    },
  );

  app.get(
    "/votes/:id",
    {
      preHandler: [requireApiKey],
      config: { rateLimit: publicRateLimitConfig },
      schema: {
        tags: ["Votes"],
        summary: "Single vote with motion text and tallies",
        description:
          "Full vote row with motion_text, ayes/nays/abstentions, result, " +
          "occurred_at, and bill linkage. 404 on missing id. " +
          "Response: `{ vote: { ... } }`.",
        params: idParam,
      },
    },
    async (req, reply) => {
      const { id } = req.params as { id: string };
      return proxyToInternal(req, reply, {
        app: root,
        internalUrl: `/api/v1/votes/${encodeURIComponent(id)}`,
      });
    },
  );

  app.get(
    "/votes/:id/positions",
    {
      preHandler: [requireApiKey],
      config: { rateLimit: publicRateLimitConfig },
      schema: {
        tags: ["Votes"],
        summary: "Per-politician position breakdown for one vote",
        description:
          "Returns one row per politician who voted, with position " +
          "('yea' | 'nay' | 'abstain' | 'paired' | 'absent'), the party " +
          "they belonged to at the time of the vote, and FK-joined " +
          "politician name + current party + openparliament_slug. May be " +
          "empty for voice / acclamation / consensus vote types. " +
          "Not paginated — vote_positions is bounded per-vote (~350 rows " +
          "even for federal). Response: `{ vote_id, positions: [...] }`.",
        params: idParam,
      },
    },
    async (req, reply) => {
      const { id } = req.params as { id: string };
      return proxyToInternal(req, reply, {
        app: root,
        internalUrl: `/api/v1/votes/${encodeURIComponent(id)}/positions`,
      });
    },
  );
}
