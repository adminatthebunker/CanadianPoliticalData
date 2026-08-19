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
import { resolvePhotoUrl } from "../../lib/photos.js";
import { currentBoundary } from "../../lib/boundary-temporal.js";

/**
 * Public politicians endpoints (/api/public/v1/politicians/*).
 *
 *   GET /politicians                — paginated list with civic-app
 *                                     filters (jurisdiction/role/status/
 *                                     constituency_id/q). Lets a
 *                                     downstream app seed "the 87 sitting
 *                                     AB MLAs" in one round-trip.
 *   GET /politicians/:id            — detail. Extended from the previous
 *                                     index.ts inline version with
 *                                     email/phone/fax/honorific/status/
 *                                     term/address fields. Backwards
 *                                     compatible — new fields land inside
 *                                     the existing `politician` object.
 *
 * Free-tier (requireApiKey only).
 *
 * Schema-gap notes (also surfaced in mkdocs/docs/developers/contact.md):
 *   - honorific is best-effort regex-derived from `name` prefix.
 *   - status returns "sitting" | "former" only; deceased politicians
 *     appear as "former" (no deceased tracking).
 *   - mailing_address always null in v1 (no upstream discriminator
 *     for the mailing-vs-constituency-vs-legislature split).
 */

const POL_ID = /^[0-9a-f-]{36}$/i;

const politicianIdParam = z.object({
  id: z.string().regex(POL_ID).describe("UUID of the politician"),
});

const listQuery = z
  .object({
    jurisdiction: z
      .string()
      .min(2)
      .max(8)
      .optional()
      .describe(
        "'federal' maps to level=federal; 2-letter province code (AB, BC, ...) maps to level=provincial AND province_territory=code",
      ),
    role: z
      .string()
      .min(1)
      .max(60)
      .optional()
      .describe(
        "Case-insensitive substring match on elected_office (e.g. 'mla', 'mp', 'councillor')",
      ),
    status: z
      .enum(["sitting", "former", "all"])
      .optional()
      .describe("Defaults to 'sitting'"),
    constituency_id: z
      .string()
      .min(1)
      .max(200)
      .optional()
      .describe(
        "Open North constituency_id (source_set/slug), matched exactly",
      ),
    q: z.string().min(1).max(200).optional().describe("Name substring (trigram-indexed)"),
    page: z.coerce.number().int().min(1).optional(),
    limit: z.coerce.number().int().min(1).max(100).optional(),
  })
  .passthrough();

const HONORIFIC_RE = /^(Rt\.?\s*Hon\.|Hon\.|Sen\.|Sir|Dame|Dr\.|Mr\.|Mrs\.|Ms\.|Mx\.|Prof\.)\s+/i;

function extractHonorific(name: string | null | undefined): string | null {
  if (!name) return null;
  const m = HONORIFIC_RE.exec(name);
  return m && m[1] ? m[1].replace(/\s+/g, " ").trim() : null;
}

function formatAddress(
  o: {
    address?: string | null;
    city?: string | null;
    province_territory?: string | null;
    postal_code?: string | null;
  } | null,
): string | null {
  if (!o) return null;
  const line2 = [o.city, o.province_territory].filter(Boolean).join(", ");
  const line2Plus = [line2, o.postal_code].filter(Boolean).join("  ");
  const lines = [o.address, line2Plus].filter((s) => s && s.trim().length > 0);
  return lines.length > 0 ? lines.join("\n") : null;
}

interface PoliticianRow {
  id: string;
  name: string;
  first_name: string | null;
  last_name: string | null;
  party: string | null;
  elected_office: string | null;
  level: string;
  province_territory: string | null;
  constituency_name: string | null;
  constituency_id: string | null;
  email: string | null;
  phone: string | null;
  photo_url: string | null;
  photo_path: string | null;
  personal_url: string | null;
  official_url: string | null;
  social_urls: Record<string, unknown>;
  is_active: boolean;
  updated_at: string;
  openparliament_slug: string | null;
  nslegislature_slug: string | null;
  ola_slug: string | null;
  ola_member_id: number | null;
  lims_member_id: number | null;
  qc_assnat_id: number | null;
  ab_assembly_mid: string | null;
  mb_assembly_slug: string | null;
  nt_mla_slug: string | null;
  sk_assembly_slug: string | null;
}

interface OfficeRow {
  kind: string;
  address: string | null;
  city: string | null;
  province_territory: string | null;
  postal_code: string | null;
  phone: string | null;
  fax: string | null;
  email: string | null;
}

interface TermRow {
  started_at: string;
  ended_at: string | null;
}

async function fetchPoliticianDetail(id: string) {
  const pol = await queryOne<PoliticianRow>(
    `SELECT id, name, first_name, last_name, party, elected_office,
            level, province_territory, constituency_name, constituency_id,
            email, phone, photo_url, photo_path, personal_url, official_url,
            social_urls, is_active, updated_at,
            openparliament_slug, nslegislature_slug, ola_slug, ola_member_id,
            lims_member_id, qc_assnat_id, ab_assembly_mid, mb_assembly_slug,
            nt_mla_slug, sk_assembly_slug
       FROM politicians WHERE id = $1`,
    [id],
  );
  if (!pol) return null;

  // Most-recent term (any state). Used for both term_start_at and
  // term_end_at, plus the sitting/former derivation (current term =
  // ended_at IS NULL on the most recent term).
  const term = await queryOne<TermRow>(
    `SELECT started_at, ended_at
       FROM politician_terms
      WHERE politician_id = $1
      ORDER BY started_at DESC, created_at DESC
      LIMIT 1`,
    [id],
  );

  // One row per office kind — most recently updated row wins when
  // a politician has multiple constituency offices. DISTINCT ON
  // requires the same prefix in ORDER BY.
  const offices = await query<OfficeRow>(
    `SELECT DISTINCT ON (kind)
            kind, address, city, province_territory, postal_code,
            phone, fax, email
       FROM politician_offices
      WHERE politician_id = $1
      ORDER BY kind, updated_at DESC`,
    [id],
  );
  const officeByKind = new Map(offices.map((o) => [o.kind, o]));
  const constituencyOffice = officeByKind.get("constituency") ?? null;
  const legislatureOffice = officeByKind.get("legislature") ?? null;

  const status: "sitting" | "former" =
    pol.is_active && term && term.ended_at === null ? "sitting" : "former";

  return { pol, term, constituencyOffice, legislatureOffice, status };
}

function shapeDetail(d: NonNullable<Awaited<ReturnType<typeof fetchPoliticianDetail>>>) {
  const { pol, term, constituencyOffice, legislatureOffice, status } = d;
  const honorific = extractHonorific(pol.name);
  return {
    id: pol.id,
    name: pol.name,
    first_name: pol.first_name,
    last_name: pol.last_name,
    honorific,
    party: pol.party,
    elected_office: pol.elected_office,
    level: pol.level,
    province_territory: pol.province_territory,
    constituency_name: pol.constituency_name,
    constituency_id: pol.constituency_id,
    email: pol.email,
    phone: pol.phone ?? constituencyOffice?.phone ?? null,
    fax: constituencyOffice?.fax ?? null,
    constituency_office_address: formatAddress(constituencyOffice),
    legislature_office_address: formatAddress(legislatureOffice),
    mailing_address: null as string | null,
    status,
    term_start_at: term?.started_at ?? null,
    term_end_at: term?.ended_at ?? null,
    last_verified_at: pol.updated_at,
    photo_url: resolvePhotoUrl({
      photo_path: pol.photo_path,
      photo_url: pol.photo_url,
    }),
    personal_url: pol.personal_url,
    official_url: pol.official_url,
    social_urls: pol.social_urls,
    is_active: pol.is_active,
    openparliament_slug: pol.openparliament_slug,
    nslegislature_slug: pol.nslegislature_slug,
    ola_slug: pol.ola_slug,
    ola_member_id: pol.ola_member_id,
    lims_member_id: pol.lims_member_id,
    qc_assnat_id: pol.qc_assnat_id,
    ab_assembly_mid: pol.ab_assembly_mid,
    mb_assembly_slug: pol.mb_assembly_slug,
    nt_mla_slug: pol.nt_mla_slug,
    sk_assembly_slug: pol.sk_assembly_slug,
  };
}

export default async function publicV1PoliticiansRoutes(app: FastifyInstance) {
  app.setValidatorCompiler(validatorCompiler);
  app.setSerializerCompiler(serializerCompiler);
  const a = app.withTypeProvider<ZodTypeProvider>();

  // ── GET /api/public/v1/politicians ────────────────────────────
  a.get(
    "/politicians",
    {
      preHandler: [requireApiKey],
      config: { rateLimit: publicRateLimitConfig },
      schema: {
        tags: ["Politicians (list)"],
        summary: "Paginated politicians list with civic-app filters",
        description:
          "Paginated list of politicians for seeding contact-card UIs. " +
          "Defaults to status='sitting' so the typical 'find me the 87 " +
          "current AB MLAs' use case is one call: " +
          "?jurisdiction=AB&role=mla. Filters: jurisdiction " +
          "(federal | 2-letter province code), role (substring match " +
          "against elected_office), status (sitting | former | all; " +
          "default sitting), constituency_id (exact match), q (name " +
          "substring; trigram-indexed). Response shape: " +
          "`{ items: [{ id, full_name, honorific, party, status, " +
          "level, province_territory, constituency_id, " +
          "constituency_name, elected_office, photo_url, email, phone, " +
          "term_start_at, last_verified_at }, ...], page, limit, total, " +
          "pages }`. Cache-Control: public, max-age=300.",
        querystring: listQuery,
      },
    },
    async (req, reply) => {
      const {
        jurisdiction,
        role,
        constituency_id,
        q,
      } = req.query;
      const status = req.query.status ?? "sitting";
      const page = req.query.page ?? 1;
      const limit = req.query.limit ?? 50;
      const offset = (page - 1) * limit;

      const where: string[] = [];
      const params: (string | number)[] = [];

      if (jurisdiction) {
        const j = jurisdiction.toLowerCase();
        if (j === "federal") {
          where.push("p.level = 'federal'");
        } else if (/^[a-z]{2}$/.test(j)) {
          params.push(j.toUpperCase());
          where.push(
            `p.level = 'provincial' AND p.province_territory = $${params.length}`,
          );
        } else {
          return reply.badRequest(
            "jurisdiction must be 'federal' or a 2-letter province code",
          );
        }
      }
      if (role) {
        params.push(`%${role}%`);
        where.push(`p.elected_office ILIKE $${params.length}`);
      }
      if (constituency_id) {
        params.push(constituency_id);
        where.push(`p.constituency_id = $${params.length}`);
      }
      if (q) {
        params.push(`%${q}%`);
        where.push(`p.name ILIKE $${params.length}`);
      }

      // Status derivation:
      //   sitting → is_active=true AND a current term exists
      //   former  → NOT sitting
      //   all     → no extra predicate
      if (status === "sitting") {
        where.push(
          `p.is_active = true AND EXISTS (
             SELECT 1 FROM politician_terms pt
              WHERE pt.politician_id = p.id AND pt.ended_at IS NULL
           )`,
        );
      } else if (status === "former") {
        where.push(
          `(p.is_active = false OR NOT EXISTS (
             SELECT 1 FROM politician_terms pt
              WHERE pt.politician_id = p.id AND pt.ended_at IS NULL
           ))`,
        );
      }

      const whereSql = where.length > 0 ? `WHERE ${where.join(" AND ")}` : "";

      const totalRow = await queryOne<{ n: number }>(
        `SELECT COUNT(*)::int AS n FROM politicians p ${whereSql}`,
        params,
      );
      const total = totalRow?.n ?? 0;

      params.push(limit, offset);
      const rows = await query<
        PoliticianRow & {
          current_term_started_at: string | null;
          current_term_ended_at: string | null;
          office_phone: string | null;
        }
      >(
        `SELECT p.id, p.name, p.first_name, p.last_name, p.party, p.elected_office,
                p.level, p.province_territory, p.constituency_name, p.constituency_id,
                p.email, p.phone, p.photo_url, p.photo_path,
                p.personal_url, p.official_url, p.social_urls,
                p.is_active, p.updated_at,
                p.openparliament_slug, p.nslegislature_slug, p.ola_slug,
                p.ola_member_id, p.lims_member_id, p.qc_assnat_id,
                p.ab_assembly_mid, p.mb_assembly_slug, p.nt_mla_slug,
                p.sk_assembly_slug,
                (SELECT pt.started_at FROM politician_terms pt
                  WHERE pt.politician_id = p.id
                  ORDER BY pt.started_at DESC, pt.created_at DESC LIMIT 1)
                  AS current_term_started_at,
                (SELECT pt.ended_at FROM politician_terms pt
                  WHERE pt.politician_id = p.id
                  ORDER BY pt.started_at DESC, pt.created_at DESC LIMIT 1)
                  AS current_term_ended_at,
                (SELECT po.phone FROM politician_offices po
                  WHERE po.politician_id = p.id AND po.kind = 'constituency'
                  ORDER BY po.updated_at DESC LIMIT 1)
                  AS office_phone
           FROM politicians p
           ${whereSql}
          ORDER BY p.level, p.province_territory NULLS LAST,
                   p.last_name NULLS LAST, p.name
          LIMIT $${params.length - 1} OFFSET $${params.length}`,
        params,
      );

      const items = rows.map((r) => {
        const isSitting =
          r.is_active && r.current_term_ended_at === null && r.current_term_started_at !== null;
        return {
          id: r.id,
          full_name: r.name,
          honorific: extractHonorific(r.name),
          party: r.party,
          status: (isSitting ? "sitting" : "former") as "sitting" | "former",
          level: r.level,
          province_territory: r.province_territory,
          constituency_id: r.constituency_id,
          constituency_name: r.constituency_name,
          elected_office: r.elected_office,
          photo_url: resolvePhotoUrl({
            photo_path: r.photo_path,
            photo_url: r.photo_url,
          }),
          email: r.email,
          phone: r.phone ?? r.office_phone,
          term_start_at: r.current_term_started_at,
          last_verified_at: r.updated_at,
        };
      });

      reply.header("Cache-Control", "public, max-age=300");
      return {
        items,
        page,
        limit,
        total,
        pages: Math.max(1, Math.ceil(total / limit)),
      };
    },
  );

  // ── GET /api/public/v1/politicians/:id ────────────────────────
  // Detail endpoint — moved from public/index.ts and extended with
  // contact + status + term fields. Backwards-compatible: new fields
  // land inside the existing `politician` object.
  a.get(
    "/politicians/:id",
    {
      preHandler: [requireApiKey],
      config: { rateLimit: publicRateLimitConfig },
      schema: {
        tags: ["Politicians"],
        summary: "Single politician with contact info, websites + boundary",
        description:
          "Returns the politician row enriched with contact info " +
          "(email, phone, fax), formatted office addresses " +
          "(constituency + legislature), derived honorific, current " +
          "status ('sitting' | 'former'), most-recent term dates, all " +
          "currently-active websites with their latest infrastructure " +
          "scan, and the constituency boundary GeoJSON. 404 on missing " +
          "or malformed id. Response: `{ politician: {...}, websites: " +
          "[...], boundary: {...} | null }` — the politician object " +
          "carries the contact fields. Cache-Control: public, max-age=60. " +
          "Schema gaps documented in /developers/contact: honorific is " +
          "best-effort regex-derived from name; status returns " +
          "'sitting' | 'former' only (deceased politicians appear as " +
          "'former'); mailing_address is always null in v1.",
        params: politicianIdParam,
      },
    },
    async (req, reply) => {
      const { id } = req.params;
      const detail = await fetchPoliticianDetail(id);
      if (!detail) return reply.notFound();

      const websites = await query(
        `SELECT w.*, s.ip_country, s.ip_city, s.ip_latitude, s.ip_longitude,
                s.hosting_provider, s.hosting_country, s.sovereignty_tier,
                s.cdn_detected, s.cms_detected, s.scanned_at
           FROM websites w
           LEFT JOIN LATERAL (
             SELECT * FROM infrastructure_scans WHERE website_id = w.id
             ORDER BY scanned_at DESC LIMIT 1
           ) s ON true
          WHERE w.owner_type='politician' AND w.owner_id=$1 AND w.is_active=true
          ORDER BY w.label`,
        [id],
      );

      const boundary = detail.pol.constituency_id
        ? await queryOne(
            `SELECT constituency_id, name, level,
                    ST_AsGeoJSON(boundary_simple)::jsonb AS boundary_geojson,
                    ST_X(centroid) AS centroid_lng,
                    ST_Y(centroid) AS centroid_lat
               FROM constituency_boundaries
              WHERE constituency_id = $1 AND ${currentBoundary()}`,
            [detail.pol.constituency_id],
          )
        : null;

      reply.header("Cache-Control", "public, max-age=60");
      return {
        politician: shapeDetail(detail),
        websites,
        boundary,
      };
    },
  );
}
