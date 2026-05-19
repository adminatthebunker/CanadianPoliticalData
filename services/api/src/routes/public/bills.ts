import type { FastifyInstance } from "fastify";
import { z } from "zod";
import { requireApiKey } from "../../middleware/api-key-auth.js";
import { publicRateLimitConfig } from "../../middleware/api-rate-limit.js";
import { proxyToInternal } from "./proxy.js";

/**
 * Public bills endpoints (/api/public/v1/bills/*). Free-tier
 * (requireApiKey, no requireTier — bills are small reference data,
 * no TEI cost). Each handler proxies to the internal /api/v1/bills
 * route via app.inject() — same single-source-of-truth pattern used
 * by the search routes.
 */

const listQuery = z
  .object({
    level: z.enum(["federal", "provincial", "municipal"]).optional(),
    province_territory: z.string().length(2).optional(),
    session_id: z.string().regex(/^[0-9a-f-]{36}$/i).optional(),
    status: z.string().optional(),
    sponsor_politician_id: z.string().regex(/^[0-9a-f-]{36}$/i).optional(),
    q: z.string().max(200).optional(),
    introduced_from: z.string().regex(/^\d{4}-\d{2}-\d{2}$/).optional(),
    introduced_to: z.string().regex(/^\d{4}-\d{2}-\d{2}$/).optional(),
    page: z.coerce.number().int().min(1).optional(),
    limit: z.coerce.number().int().min(1).max(100).optional(),
  })
  .passthrough();

const idParam = z.object({
  id: z.string().regex(/^[0-9a-f-]{36}$/i),
});

export default async function publicV1BillsRoutes(app: FastifyInstance) {
  const root = app;

  app.get(
    "/bills",
    {
      preHandler: [requireApiKey],
      config: { rateLimit: publicRateLimitConfig },
      schema: {
        tags: ["Bills"],
        summary: "List bills with jurisdiction + session + status filters",
        description:
          "Paginated list of bills across federal + provincial legislatures. " +
          "Filters: level, province_territory, session_id, status, " +
          "sponsor_politician_id, q (substring of title/short_title/bill_number), " +
          "introduced_from, introduced_to. Each item includes the session " +
          "label, denormalized events_count + sponsors_count, and the " +
          "upstream source_url. Response: " +
          "`{ items: [...], page, limit, total, pages }`.",
        querystring: listQuery,
      },
    },
    async (req, reply) => {
      return proxyToInternal(req, reply, {
        app: root,
        internalUrl: "/api/v1/bills",
      });
    },
  );

  app.get(
    "/bills/:id",
    {
      preHandler: [requireApiKey],
      config: { rateLimit: publicRateLimitConfig },
      schema: {
        tags: ["Bills"],
        summary: "Single bill with session detail and denorm counts",
        description:
          "Full bill row joined to its legislative_session, plus " +
          "events_count, sponsors_count, and votes_count. 404 on missing id. " +
          "Response: `{ bill: { ... } }`.",
        params: idParam,
      },
    },
    async (req, reply) => {
      const { id } = req.params as { id: string };
      return proxyToInternal(req, reply, {
        app: root,
        internalUrl: `/api/v1/bills/${encodeURIComponent(id)}`,
      });
    },
  );

  app.get(
    "/bills/:id/events",
    {
      preHandler: [requireApiKey],
      config: { rateLimit: publicRateLimitConfig },
      schema: {
        tags: ["Bills"],
        summary: "Stage-transition events for one bill",
        description:
          "Append-only event log: first_reading, second_reading, committee, " +
          "third_reading, royal_assent, etc., ordered by event_date ASC. " +
          "Federal events come from parl.ca/LegisInfo XML; provincial events " +
          "come from per-jurisdiction Hansard + bills-status pages. " +
          "Response: `{ bill_id, events: [...] }`.",
        params: idParam,
      },
    },
    async (req, reply) => {
      const { id } = req.params as { id: string };
      return proxyToInternal(req, reply, {
        app: root,
        internalUrl: `/api/v1/bills/${encodeURIComponent(id)}/events`,
      });
    },
  );

  app.get(
    "/bills/:id/sponsors",
    {
      preHandler: [requireApiKey],
      config: { rateLimit: publicRateLimitConfig },
      schema: {
        tags: ["Bills"],
        summary: "Sponsor list for one bill (FK-joined to politicians)",
        description:
          "Bill sponsors with role ('sponsor' | 'co_sponsor') and ordering. " +
          "When politician_id is resolved, the politician's current name, " +
          "party, and openparliament_slug are surfaced. When unresolved, " +
          "sponsor_name_raw still carries the upstream string. " +
          "Response: `{ bill_id, sponsors: [...] }`.",
        params: idParam,
      },
    },
    async (req, reply) => {
      const { id } = req.params as { id: string };
      return proxyToInternal(req, reply, {
        app: root,
        internalUrl: `/api/v1/bills/${encodeURIComponent(id)}/sponsors`,
      });
    },
  );
}
