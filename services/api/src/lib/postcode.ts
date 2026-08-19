/**
 * Postal-code resolution. **Fully local — no outbound network call.**
 *
 * Two consumers: /api/public/v1/postcodes/:postcode (returns the rich shape with
 * boundaries) and /api/public/v1/boundaries/lookup when called with ?postcode=
 * (uses just the centroid). Plus lib/postcode-reps.ts, which every search
 * `postcode` filter goes through.
 *
 * ── Why this was rewritten (2026-08-18) ─────────────────────────────────────
 *
 * This module used to fetch every centroid from represent.opennorth.ca, with
 * `public.postcode_cache` as a stale-while-revalidate buffer in front. That host
 * went down on 2026-08-07 (TLS certificate expired AND origin returning 502) and
 * the cache held **8 rows** — so the SWR buffer was decorative and every
 * uncached postal code in Canada returned a 503 for eleven days.
 *
 * The replacement is `public.postcode_centroids`, built from the Statistics
 * Canada **National Address Register** (cat. 46-26-0002, Statistics Canada Open
 * Licence — explicit right to reproduce, distribute and sublicence). 855,905
 * postal codes with 100% city coverage, rebuilt by the scanner command
 * `ingest-nar-postcodes`.
 *
 * ★ The outbound call is **removed, not demoted**. Keeping Open North as primary
 * with a local fallback would reproduce exactly this incident the next time it
 * goes down; keeping it as a fallback behind the local table would mean the
 * failure mode returns the moment the local table has a gap. Neither is worth
 * the coupling. If a code is not resolvable locally we say so.
 *
 * ── Resolution order ────────────────────────────────────────────────────────
 *
 *   1. `postcode_centroids` exact match          → source "nar"
 *   2. `postcode_cache` exact match              → source "cache"
 *   3. derived from other codes in the same FSA  → source "fsa_derived"
 *   4. otherwise                                 → PostcodeUpstreamError("not_found")
 *
 * Layer 2 is what `postcode_cache` is *for* now. NAR registers civic addresses,
 * so codes with none are absent by construction — PO-box-only, rural-route-only,
 * and large-volume-receiver / government codes. `K1A 0A6` (House of Commons) is
 * the canonical example: zero NAR rows. The cache retains those.
 *
 * ── ⚠ `approximate` is load-bearing, not decorative ─────────────────────────
 *
 * Layer 3 answers a 6-character code from the *average of its FSA's* known
 * codes, and answers a 3-character FSA the same way. Research measured that
 * **33–71% of FSAs cross a federal riding boundary**, and that rural FSA
 * fallback resolves to the correct federal district only **68.46%** of the time
 * (against 98.26% for an exact rural 6-character match).
 *
 * So an FSA-derived point is a plausible-looking wrong answer roughly a third of
 * the time. Callers MUST NOT present it as exact. `approximate: true` is the
 * signal, and `/lookup/postcode/:code` uses it to return every district the FSA
 * touches rather than the single one containing the derived centroid.
 */

import { query, queryOne } from "../db.js";

const FULL_POSTCODE_RE = /^[A-Za-z]\d[A-Za-z][ -]?\d[A-Za-z]\d$/;
const FSA_RE = /^[A-Za-z]\d[A-Za-z]$/;

export class PostcodeUpstreamError extends Error {
  constructor(
    message: string,
    public readonly kind: "not_found" | "unavailable" | "invalid",
  ) {
    super(message);
    this.name = "PostcodeUpstreamError";
  }
}

export interface ResolvedPostcode {
  /** Display-formatted postcode (e.g. "K1A 0A6" or "K1A") */
  postcode: string;
  /** True when the input was a 3-char FSA, false for 6-char */
  is_fsa: boolean;
  /** Centroid coordinates, WGS84. */
  latlng: { lat: number; lng: number };
  /** Municipality. Modal MAIL_MUN_NAME for NAR rows. */
  city: string | null;
  /** Province/territory two-letter code. */
  province: string | null;
  /**
   * Which layer answered.
   *
   * ⚠ Changed 2026-08-18. Was `"cache" | "cache_stale" | "live"`, which
   * described a cache in front of Open North. Those values cannot occur any
   * more — there is no upstream to be live against or stale relative to.
   */
  source: "nar" | "cache" | "fsa_derived";
  /** When the underlying data was built or last written. */
  fetched_at: string;
  /**
   * Civic address points averaged to produce this centroid. Null for non-NAR
   * layers. 1 means a single address — positionally weaker than a high count.
   */
  address_points: number | null;
  /**
   * True when this is an FSA-level approximation rather than an exact code.
   * Callers must not present an approximate point as a definitive location —
   * see the module docstring.
   */
  approximate: boolean;
}

interface CentroidRow {
  postcode: string;
  lat: number;
  lng: number;
  city: string | null;
  province: string | null;
  address_points: number;
  built_at: string;
}

interface CacheRow {
  postcode: string;
  centroid_lng: number;
  centroid_lat: number;
  city: string | null;
  province: string | null;
  fetched_at: string;
}

interface FsaRow {
  lat: number;
  lng: number;
  city: string | null;
  province: string | null;
  members: number;
}

function normalize(input: string): string {
  return input.replace(/[^A-Za-z0-9]/g, "").toUpperCase();
}

export function classifyPostcode(input: string):
  | { kind: "full"; normalized: string }
  | { kind: "fsa"; normalized: string }
  | { kind: "invalid" } {
  if (typeof input !== "string") return { kind: "invalid" };
  if (FULL_POSTCODE_RE.test(input)) {
    return { kind: "full", normalized: normalize(input) };
  }
  if (FSA_RE.test(input)) {
    return { kind: "fsa", normalized: normalize(input) };
  }
  return { kind: "invalid" };
}

function displayFor(cls: { kind: "full" | "fsa"; normalized: string }): string {
  return cls.kind === "fsa"
    ? cls.normalized
    : `${cls.normalized.slice(0, 3)} ${cls.normalized.slice(3)}`;
}

/** Layer 1 — exact match in the NAR-derived table. */
async function fromCentroids(normalized: string): Promise<CentroidRow | null> {
  return queryOne<CentroidRow>(
    `SELECT postcode, lat, lng, city, province, address_points,
            built_at::text AS built_at
       FROM public.postcode_centroids
      WHERE postcode = $1`,
    [normalized],
  );
}

/** Layer 2 — the retained override table (codes NAR cannot supply). */
async function fromCache(normalized: string): Promise<CacheRow | null> {
  return queryOne<CacheRow>(
    `SELECT postcode, centroid_lng, centroid_lat, city, province,
            fetched_at::text AS fetched_at
       FROM public.postcode_cache
      WHERE postcode = $1`,
    [normalized],
  );
}

/**
 * Layer 3 — derive a point from the other codes in the same FSA.
 *
 * Weighted by `address_points` so a code representing 400 addresses pulls the
 * centroid more than a single-address one. Uses the indexed `left(postcode,3)`
 * expression from migration 0062.
 */
async function fromFsa(fsa: string): Promise<FsaRow | null> {
  const row = await queryOne<FsaRow>(
    `SELECT sum(lat * address_points) / sum(address_points) AS lat,
            sum(lng * address_points) / sum(address_points) AS lng,
            mode() WITHIN GROUP (ORDER BY city)     AS city,
            mode() WITHIN GROUP (ORDER BY province) AS province,
            count(*)                                AS members
       FROM public.postcode_centroids
      WHERE left(postcode, 3) = $1`,
    [fsa],
  );
  return row && row.members > 0 ? row : null;
}

export async function resolvePostcode(input: string): Promise<ResolvedPostcode> {
  const cls = classifyPostcode(input);
  if (cls.kind === "invalid") {
    throw new PostcodeUpstreamError(
      `Not a Canadian postal code: ${String(input).slice(0, 16)}`,
      "invalid",
    );
  }

  const display = displayFor(cls);
  const fsa = cls.normalized.slice(0, 3);

  if (cls.kind === "full") {
    const nar = await fromCentroids(cls.normalized);
    if (nar) {
      return {
        postcode: display,
        is_fsa: false,
        latlng: { lat: nar.lat, lng: nar.lng },
        city: nar.city,
        province: nar.province,
        source: "nar",
        fetched_at: nar.built_at,
        address_points: nar.address_points,
        approximate: false,
      };
    }

    const cached = await fromCache(cls.normalized);
    if (cached) {
      return {
        postcode: display,
        is_fsa: false,
        latlng: { lat: cached.centroid_lat, lng: cached.centroid_lng },
        city: cached.city,
        province: cached.province,
        source: "cache",
        fetched_at: cached.fetched_at,
        address_points: null,
        approximate: false,
      };
    }
  }

  // FSA input, or a 6-char code with no exact match anywhere. Both fall back to
  // the FSA-derived point, and both are flagged approximate.
  const derived = await fromFsa(fsa);
  if (derived) {
    return {
      postcode: display,
      is_fsa: cls.kind === "fsa",
      latlng: { lat: derived.lat, lng: derived.lng },
      city: derived.city,
      province: derived.province,
      source: "fsa_derived",
      fetched_at: new Date().toISOString(),
      address_points: null,
      approximate: true,
    };
  }

  // An FSA row may exist in the retained cache even when no NAR member does
  // (e.g. the government-only FSA K1A).
  const cachedFsa = await fromCache(fsa);
  if (cachedFsa) {
    return {
      postcode: display,
      is_fsa: cls.kind === "fsa",
      latlng: { lat: cachedFsa.centroid_lat, lng: cachedFsa.centroid_lng },
      city: cachedFsa.city,
      province: cachedFsa.province,
      source: "cache",
      fetched_at: cachedFsa.fetched_at,
      address_points: null,
      approximate: cls.kind === "full",
    };
  }

  throw new PostcodeUpstreamError(
    `No location on file for ${display}. Canadian postal codes without a civic ` +
      `address (PO-box-only, rural-route-only, and some government codes) are ` +
      `not in the national address register.`,
    "not_found",
  );
}

/**
 * Every district the FSA touches, for the approximate case.
 *
 * ⚠ Only meaningful when `ResolvedPostcode.approximate` is true. Research
 * measured that 33–71% of FSAs cross a federal riding boundary, so collapsing an
 * FSA to one district is wrong for a large minority of them. This returns the
 * honest set: run point-in-polygon from every known member code of the FSA and
 * union the districts.
 *
 * Capped at 400 member codes — dense urban FSAs run to ~460 and the marginal
 * point adds nothing once the district set has converged.
 */
export async function districtsForFsa(
  fsa: string,
  levels: readonly string[] = ["federal", "provincial", "municipal"],
): Promise<{ constituency_id: string; name: string; level: string }[]> {
  return query<{ constituency_id: string; name: string; level: string }>(
    `WITH pts AS (
       SELECT lat, lng FROM public.postcode_centroids
        WHERE left(postcode, 3) = $1
        ORDER BY address_points DESC
        LIMIT 400
     )
     SELECT DISTINCT b.constituency_id, b.name, b.level
       FROM pts
       JOIN constituency_boundaries b
         ON b.effective_from <= CURRENT_DATE
        AND (b.effective_to IS NULL OR b.effective_to >= CURRENT_DATE)
        AND b.level = ANY($2::text[])
        AND ST_Contains(b.boundary, ST_SetSRID(ST_MakePoint(pts.lng, pts.lat), 4326))
      ORDER BY b.level, b.name`,
    [fsa.toUpperCase(), levels as string[]],
  );
}
