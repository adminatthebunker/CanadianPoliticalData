import type { FastifyInstance } from "fastify";
import { z } from "zod";
import {
  serializerCompiler,
  validatorCompiler,
  type ZodTypeProvider,
} from "fastify-type-provider-zod";
import { query } from "../../db.js";
import { requireApiKey } from "../../middleware/api-key-auth.js";
import { publicRateLimitConfig } from "../../middleware/api-rate-limit.js";
import {
  resolvePostcode,
  districtsForFsa,
  PostcodeUpstreamError,
} from "../../lib/postcode.js";
import { lookupBoundariesAtPoint } from "./boundaries.js";
import { resolvePhotoUrl } from "../../lib/photos.js";
import { currentBoundary } from "../../lib/boundary-temporal.js";

/**
 * Public postcode endpoint (/api/public/v1/postcodes/:postcode).
 *
 * Two-stage lookup: proxy Open North for the centroid, then run
 * our own PIP against `constituency_boundaries` so the response
 * `boundaries.*` slot is byte-identical to what /boundaries/lookup
 * returns. Open North's `boundaries_centroid` is intentionally not
 * passed through — its shape diverges, and it includes ward /
 * school / non-mirrored sets we wouldn't recognise.
 *
 * Accepts 6-char (K1A 0A6, K1A-0A6, K1A0A6) or 3-char FSA (K1A).
 * No local cache — Canada Post licensing stays Open North's
 * problem.
 */

const postcodeParam = z.object({
  postcode: z
    .string()
    .min(3)
    .max(8)
    .describe("6-char postcode (K1A0A6) or 3-char FSA (K1A)"),
});

export default async function publicV1PostcodesRoutes(app: FastifyInstance) {
  app.setValidatorCompiler(validatorCompiler);
  app.setSerializerCompiler(serializerCompiler);
  const a = app.withTypeProvider<ZodTypeProvider>();

  a.get(
    "/postcodes/:postcode",
    {
      preHandler: [requireApiKey],
      config: { rateLimit: publicRateLimitConfig },
      schema: {
        tags: ["Postcodes"],
        summary: "Resolve postcode/FSA to lat/lng + containing ridings",
        description:
          "Real-time proxy to Open North's Represent API for postcode " +
          "geocoding, then runs our own point-in-polygon against the " +
          "centroid so the `boundaries.*` slots are byte-identical to " +
          "what /boundaries/lookup returns. Accepts either a 6-char " +
          "postcode (K1A0A6, K1A 0A6, K1A-0A6) or a 3-char FSA (K1A). " +
          "Response: `{ postcode, is_fsa, latlng: { lat, lng }, city, " +
          "province, source: 'nar'|'cache'|'fsa_derived', fetched_at, " +
          "address_points, approximate, " +
          "boundaries: { federal: {...}|null, provincial: {...}|null, " +
          "municipal: {...}|null } }`. Resolution is fully local as of " +
          "2026-08-18 — no upstream call. `source` is `nar` for an exact " +
          "match in the Statistics Canada National Address Register " +
          "(855,905 codes), `cache` for a code the register cannot supply " +
          "(PO-box-only, rural-route-only and government codes such as " +
          "K1A 0A6), and `fsa_derived` when the answer was averaged from " +
          "other codes in the same forward sortation area. " +
          "⚠ `approximate: true` accompanies every `fsa_derived` answer " +
          "and must not be presented as an exact location: 33-71% of FSAs " +
          "cross a federal riding boundary, and FSA-level resolution " +
          "picks the correct federal district only ~68% of the time for " +
          "rural codes (against 98% for an exact match). `address_points` " +
          "is how many civic addresses were averaged; 1 is positionally " +
          "weaker than a high count. Returns 400 on malformed input and " +
          "404 when neither the register, the override table, nor the " +
          "FSA has any location on file. No 503 path remains. " +
          "Cache-Control: public, max-age=86400.",
        params: postcodeParam,
      },
    },
    async (req, reply) => {
      const { postcode } = req.params;

      let resolved;
      try {
        resolved = await resolvePostcode(postcode);
      } catch (err) {
        if (err instanceof PostcodeUpstreamError) {
          if (err.kind === "invalid") return reply.badRequest(err.message);
          if (err.kind === "not_found") return reply.notFound(err.message);
          return reply.serviceUnavailable(err.message);
        }
        throw err;
      }

      const boundaries = await lookupBoundariesAtPoint(
        resolved.latlng.lng,
        resolved.latlng.lat,
      );

      // ⚠ When the point is FSA-derived rather than an exact code, `boundaries`
      // is only the district containing a *representative* point, and research
      // measured that 33-71% of FSAs cross a federal riding boundary. Returning
      // that single district would present a coin flip as an answer. So for
      // approximate resolutions we also return every district the FSA touches,
      // computed by point-in-polygon from each known member code.
      const spans = resolved.approximate
        ? await districtsForFsa(resolved.postcode.slice(0, 3))
        : null;

      reply.header("Cache-Control", "public, max-age=86400");
      reply.header("X-Cache-Source", resolved.source);
      if (resolved.approximate) reply.header("X-Postcode-Approximate", "true");
      return {
        postcode: resolved.postcode,
        is_fsa: resolved.is_fsa,
        latlng: resolved.latlng,
        city: resolved.city,
        province: resolved.province,
        source: resolved.source,
        fetched_at: resolved.fetched_at,
        address_points: resolved.address_points,
        approximate: resolved.approximate,
        boundaries,
        // Null for exact matches. For approximate ones, EVERY district the FSA
        // overlaps — `boundaries` above is only the most likely of these.
        spans_districts: spans,
      };
    },
  );

  // ── GET /api/public/v1/postcodes/:postcode/representatives ──────────
  //
  // Composite endpoint: same postcode → centroid → boundary chain as
  // /postcodes/:postcode, but ALSO returns every sitting politician
  // whose constituency contains the centroid, plus that politician's
  // offices and social handles. Lets a civic-app consumer (e.g. Just
  // Say No) replace 4+ round-trips (postcode + politicians-by-
  // constituency + offices + socials per level) with one call.
  //
  // Returns ALL matching boundaries (vs lookupBoundariesAtPoint which
  // collapses to one-per-level): a centroid sitting inside both a
  // city-wide municipal boundary and a ward-sized one yields the
  // mayor AND the ward councillor. `sittingness` mirrors the
  // predicate from /politicians (is_active=true AND a current term
  // exists with ended_at IS NULL).
  a.get(
    "/postcodes/:postcode/representatives",
    {
      preHandler: [requireApiKey],
      config: { rateLimit: publicRateLimitConfig },
      schema: {
        tags: ["Postcodes"],
        summary:
          "Resolve postcode/FSA to all sitting representatives at every level",
        description:
          "Composite endpoint that returns the same `{ postcode, " +
          "latlng, source, fetched_at, boundaries }` shape as " +
          "/postcodes/:postcode plus a `representatives` array — one " +
          "entry per sitting politician whose constituency contains the " +
          "centroid, including their offices and live social handles. " +
          "Returns mayor + the specific ward councillor whose boundary " +
          "contains the postcode at the municipal level (no city-wide " +
          "councillor fanout). Sitting derivation: politicians.is_active " +
          "= true AND a politician_terms row with ended_at IS NULL " +
          "exists. Social handles filtered to is_live=true. Accepts " +
          "the same 6-char or 3-char-FSA input as /postcodes/:postcode. " +
          "Cache-Control: public, max-age=300.",
        params: postcodeParam,
      },
    },
    async (req, reply) => {
      const { postcode } = req.params;

      let resolved;
      try {
        resolved = await resolvePostcode(postcode);
      } catch (err) {
        if (err instanceof PostcodeUpstreamError) {
          if (err.kind === "invalid") return reply.badRequest(err.message);
          if (err.kind === "not_found") return reply.notFound(err.message);
          return reply.serviceUnavailable(err.message);
        }
        throw err;
      }

      // Boundaries for the headline `boundaries` field, same shape as
      // /postcodes/:postcode (one-per-level, may collapse a ward
      // councillor + mayor pair). The `representatives` field below
      // is the authoritative list for the all-reps use case.
      const boundaries = await lookupBoundariesAtPoint(
        resolved.latlng.lng,
        resolved.latlng.lat,
      );

      // Pull every sitting politician whose constituency boundary
      // contains the centroid. One query: PIP against
      // constituency_boundaries, join politicians on constituency_id,
      // apply sitting predicate. Returns 0..N rows (typically 4 for
      // an urban Canadian postcode: MP + MLA + mayor + ward
      // councillor).
      interface RepRow {
        politician_id: string;
        name: string;
        first_name: string | null;
        last_name: string | null;
        party: string | null;
        elected_office: string | null;
        level: string;
        province_territory: string | null;
        email: string | null;
        phone: string | null;
        photo_url: string | null;
        photo_path: string | null;
        personal_url: string | null;
        official_url: string | null;
        social_urls: Record<string, unknown> | null;
        updated_at: string;
        constituency_id: string;
        constituency_name: string;
        boundary_source_set: string | null;
        current_term_started_at: string | null;
      }
      const repRows = await query<RepRow>(
        `SELECT p.id AS politician_id,
                p.name, p.first_name, p.last_name, p.party, p.elected_office,
                p.level, p.province_territory,
                p.email, p.phone, p.photo_url, p.photo_path,
                p.personal_url, p.official_url, p.social_urls,
                p.updated_at,
                b.constituency_id, b.name AS constituency_name,
                b.source_set AS boundary_source_set,
                (SELECT pt.started_at FROM politician_terms pt
                  WHERE pt.politician_id = p.id AND pt.ended_at IS NULL
                  ORDER BY pt.started_at DESC LIMIT 1) AS current_term_started_at
           FROM constituency_boundaries b
           JOIN politicians p
             ON p.constituency_id = b.constituency_id
            AND p.level = b.level
          WHERE ${currentBoundary("b")}
            AND ST_Contains(b.boundary,
                            ST_SetSRID(ST_MakePoint($1, $2), 4326))
            AND p.is_active = true
            AND EXISTS (
              SELECT 1 FROM politician_terms pt2
               WHERE pt2.politician_id = p.id AND pt2.ended_at IS NULL
            )
          ORDER BY
            CASE p.level
              WHEN 'federal' THEN 0
              WHEN 'provincial' THEN 1
              WHEN 'municipal' THEN 2
              ELSE 3
            END,
            p.last_name NULLS LAST, p.name`,
        [resolved.latlng.lng, resolved.latlng.lat],
      );

      // Fan out offices + socials per politician. Two parallel
      // queries scoped to all returned politician_ids — much cheaper
      // than N+1.
      const politicianIds = repRows.map((r) => r.politician_id);
      interface OfficeRow {
        politician_id: string;
        kind: string;
        address: string | null;
        city: string | null;
        province_territory: string | null;
        postal_code: string | null;
        phone: string | null;
        fax: string | null;
        email: string | null;
        hours: string | null;
        lat: number | null;
        lng: number | null;
        source: string | null;
      }
      interface SocialRow {
        politician_id: string;
        platform: string;
        handle: string | null;
        url: string | null;
        follower_count: number | null;
        lifetime_post_count: number | null;
        last_post_at: string | null;
        last_profile_check_at: string | null;
        last_verified_at: string | null;
        is_live: boolean;
      }
      const [officeRows, socialRows] = politicianIds.length === 0
        ? [[] as OfficeRow[], [] as SocialRow[]]
        : await Promise.all([
            query<OfficeRow>(
              `SELECT politician_id, kind, address, city, province_territory,
                      postal_code, phone, fax, email, hours,
                      lat, lon AS lng, source
                 FROM politician_offices
                WHERE politician_id = ANY($1::uuid[])
                ORDER BY politician_id,
                  CASE kind
                    WHEN 'constituency' THEN 0
                    WHEN 'legislature'  THEN 1
                    WHEN 'office'       THEN 2
                    ELSE 3
                  END,
                  updated_at DESC`,
              [politicianIds],
            ),
            query<SocialRow>(
              `SELECT politician_id, platform, handle, url,
                      follower_count, lifetime_post_count,
                      last_post_at, last_profile_check_at, last_verified_at,
                      is_live
                 FROM politician_socials
                WHERE politician_id = ANY($1::uuid[])
                  AND is_live = true
                ORDER BY politician_id, platform, handle`,
              [politicianIds],
            ),
          ]);

      const officesByPolitician = new Map<string, OfficeRow[]>();
      for (const o of officeRows) {
        const list = officesByPolitician.get(o.politician_id) ?? [];
        list.push(o);
        officesByPolitician.set(o.politician_id, list);
      }
      const socialsByPolitician = new Map<string, SocialRow[]>();
      for (const s of socialRows) {
        const list = socialsByPolitician.get(s.politician_id) ?? [];
        list.push(s);
        socialsByPolitician.set(s.politician_id, list);
      }

      const representatives = repRows.map((r) => ({
        level: r.level,
        constituency_id: r.constituency_id,
        constituency_name: r.constituency_name,
        boundary_source_set: r.boundary_source_set,
        politician: {
          id: r.politician_id,
          full_name: r.name,
          first_name: r.first_name,
          last_name: r.last_name,
          honorific: extractHonorificPrefix(r.name),
          party: r.party,
          elected_office: r.elected_office,
          level: r.level,
          province_territory: r.province_territory,
          email: r.email,
          phone: r.phone,
          photo_url: resolvePhotoUrl({
            photo_path: r.photo_path,
            photo_url: r.photo_url,
          }),
          personal_url: r.personal_url,
          official_url: r.official_url,
          social_urls: r.social_urls,
          term_start_at: r.current_term_started_at,
          last_verified_at: r.updated_at,
        },
        offices: (officesByPolitician.get(r.politician_id) ?? []).map((o) => ({
          kind: o.kind,
          address: o.address,
          city: o.city,
          province_territory: o.province_territory,
          postal_code: o.postal_code,
          phone: o.phone,
          fax: o.fax,
          email: o.email,
          hours: o.hours,
          lat: o.lat,
          lng: o.lng,
          source: o.source,
        })),
        socials: (socialsByPolitician.get(r.politician_id) ?? []).map((s) => ({
          platform: s.platform,
          handle: s.handle,
          url: s.url,
          follower_count: s.follower_count,
          lifetime_post_count: s.lifetime_post_count,
          last_post_at: s.last_post_at,
          last_profile_check_at: s.last_profile_check_at,
          last_verified_at: s.last_verified_at,
          is_live: s.is_live,
        })),
      }));

      reply.header("Cache-Control", "public, max-age=300");
      reply.header("X-Cache-Source", resolved.source);
      return {
        postcode: resolved.postcode,
        is_fsa: resolved.is_fsa,
        latlng: resolved.latlng,
        city: resolved.city,
        province: resolved.province,
        source: resolved.source,
        fetched_at: resolved.fetched_at,
        boundaries,
        representatives,
      };
    },
  );
}

// Honorific extraction mirrors politicians.ts — kept inline so this
// module doesn't import a private helper from a sibling route file.
const HONORIFIC_RE =
  /^(Rt\.?\s*Hon\.|Hon\.|Sen\.|Sir|Dame|Dr\.|Mr\.|Mrs\.|Ms\.|Mx\.|Prof\.)\s+/i;
function extractHonorificPrefix(name: string | null | undefined): string | null {
  if (!name) return null;
  const m = HONORIFIC_RE.exec(name);
  return m && m[1] ? m[1].replace(/\s+/g, " ").trim() : null;
}
