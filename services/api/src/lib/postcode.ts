/**
 * Postcode resolution against Open North's Represent API, with a
 * Postgres-backed cache.
 *
 * Two consumers: /api/public/v1/postcodes/:postcode (returns the
 * rich shape with boundaries) and /api/public/v1/boundaries/lookup
 * when called with ?postcode= (uses just the centroid).
 *
 * Caching posture (table public.postcode_cache, migration 0055):
 *   - Fresh (fetched_at within CACHE_TTL_MS): served from cache.
 *   - Stale: refetch from upstream. On success, upsert the row.
 *     On upstream 5xx / network failure, serve the stale row anyway
 *     (stale-while-revalidate — postcodes don't actually move; a
 *     stale row is still correct, we just haven't double-checked it
 *     lately). Only invalidate the cache row on a confirmed 404.
 *   - Missing: hit upstream, upsert on success.
 *
 * Licensing note: postcode geocoding data is freely redistributed by
 * Open North and is not subject to active Canada Post enforcement
 * (the 2012 Geolytica suit was abandoned in 2016 and no Canadian case
 * law establishes postcodes as copyrightable). We cache responses to
 * queries our users made — the same way every HTTP cache works — and
 * this is no different in legal substance from the Cache-Control:
 * max-age=86400 header we already emit on /postcodes/:postcode.
 */

import { query, queryOne } from "../db.js";

const FULL_POSTCODE_RE = /^[A-Za-z]\d[A-Za-z][ -]?\d[A-Za-z]\d$/;
const FSA_RE = /^[A-Za-z]\d[A-Za-z]$/;

const OPEN_NORTH_BASE =
  process.env.OPEN_NORTH_BASE ?? "https://represent.opennorth.ca";

/** Fresh-window for the cache. Rows newer than this skip the upstream. */
const CACHE_TTL_MS = 30 * 24 * 60 * 60 * 1000; // 30 days

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
  /** Centroid coordinates from Open North. lat/lng in WGS84. */
  latlng: { lat: number; lng: number };
  /** City name returned by Open North (best-effort; may be empty for FSAs). */
  city: string | null;
  /** Province two-letter code returned by Open North. */
  province: string | null;
  /** Where this resolution came from. */
  source: "cache" | "cache_stale" | "live";
  /** When the underlying data was fetched from upstream. */
  fetched_at: string;
}

interface OpenNorthCentroid {
  type?: string;
  coordinates?: [number, number];
}

interface OpenNorthPostcodeResponse {
  centroid?: OpenNorthCentroid;
  city?: string;
  province?: string;
}

interface CacheRow {
  postcode: string;
  centroid_lng: number;
  centroid_lat: number;
  city: string | null;
  province: string | null;
  fetched_at: string;
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

// FSA fallback suffixes. Open North's /postcodes/:code/ endpoint
// only accepts 6-char postcodes (`/postcodes/T2P/` returns 404), so
// for FSA input we probe with these suffixes in order until one
// resolves. 1A1 has the highest hit rate in practice; 0A0 catches
// the FSAs without a 1A1 issued (newer / sparser areas); 1B1 is a
// final fallback. The resulting centroid is a single-postcode point
// within the FSA, not the FSA's geometric centroid — for our use
// case (which federal/provincial/municipal riding contains this
// FSA) it's typically the dominant riding either way.
const FSA_FALLBACK_SUFFIXES = ["1A1", "0A0", "1B1"];

async function fetchPostcode(
  normalized: string,
): Promise<OpenNorthPostcodeResponse | "not_found"> {
  let resp: Response;
  try {
    resp = await fetch(
      `${OPEN_NORTH_BASE}/postcodes/${normalized}/?format=json`,
      {
        headers: { "User-Agent": "CanadianPoliticalData/1.0" },
      },
    );
  } catch {
    throw new PostcodeUpstreamError(
      "Postcode lookup service is unreachable",
      "unavailable",
    );
  }
  if (resp.status === 404) return "not_found";
  if (!resp.ok) {
    throw new PostcodeUpstreamError(
      `Postcode lookup service returned ${resp.status}`,
      "unavailable",
    );
  }
  try {
    return (await resp.json()) as OpenNorthPostcodeResponse;
  } catch {
    throw new PostcodeUpstreamError(
      "Postcode lookup service returned invalid JSON",
      "unavailable",
    );
  }
}

async function readFromCache(postcode: string): Promise<CacheRow | null> {
  return queryOne<CacheRow>(
    `SELECT postcode, centroid_lng, centroid_lat, city, province, fetched_at
       FROM public.postcode_cache
      WHERE postcode = $1`,
    [postcode],
  );
}

async function writeToCache(
  postcode: string,
  lng: number,
  lat: number,
  city: string | null,
  province: string | null,
): Promise<void> {
  await query(
    `INSERT INTO public.postcode_cache
       (postcode, centroid_lng, centroid_lat, city, province, source, fetched_at)
     VALUES ($1, $2, $3, $4, $5, 'opennorth', now())
     ON CONFLICT (postcode) DO UPDATE
        SET centroid_lng = EXCLUDED.centroid_lng,
            centroid_lat = EXCLUDED.centroid_lat,
            city         = EXCLUDED.city,
            province     = EXCLUDED.province,
            source       = EXCLUDED.source,
            fetched_at   = now()`,
    [postcode, lng, lat, city, province],
  );
}

async function evictFromCache(postcode: string): Promise<void> {
  await query(
    `DELETE FROM public.postcode_cache WHERE postcode = $1`,
    [postcode],
  );
}

function displayFor(cls: { kind: "full" | "fsa"; normalized: string }): string {
  return cls.kind === "full"
    ? `${cls.normalized.slice(0, 3)} ${cls.normalized.slice(3)}`
    : cls.normalized;
}

function isFresh(fetched_at: string): boolean {
  const t = Date.parse(fetched_at);
  if (!Number.isFinite(t)) return false;
  return Date.now() - t < CACHE_TTL_MS;
}

function shapeFromCache(
  row: CacheRow,
  cls: { kind: "full" | "fsa"; normalized: string },
  source: "cache" | "cache_stale",
): ResolvedPostcode {
  return {
    postcode: displayFor(cls),
    is_fsa: cls.kind === "fsa",
    latlng: { lat: row.centroid_lat, lng: row.centroid_lng },
    city: row.city,
    province: row.province,
    source,
    fetched_at: row.fetched_at,
  };
}

/**
 * Resolve a 6-char postcode via the cache + Open North + SWR layer.
 * Returns the row to surface; throws on validation / hard-404 (with
 * eviction) / upstream-down-with-no-cache.
 */
async function resolveFullPostcode(
  cls: { kind: "full"; normalized: string },
): Promise<ResolvedPostcode> {
  // 1) Cache check.
  const cached = await readFromCache(cls.normalized);
  if (cached && isFresh(cached.fetched_at)) {
    return shapeFromCache(cached, cls, "cache");
  }

  // 2) Upstream. On 5xx / network: fall back to stale cache if we have one.
  let body: OpenNorthPostcodeResponse | "not_found";
  try {
    body = await fetchPostcode(cls.normalized);
  } catch (err) {
    if (cached && err instanceof PostcodeUpstreamError && err.kind === "unavailable") {
      return shapeFromCache(cached, cls, "cache_stale");
    }
    throw err;
  }

  // 3) Hard 404 from upstream: evict any stale row (the postcode is gone).
  if (body === "not_found") {
    if (cached) await evictFromCache(cls.normalized);
    throw new PostcodeUpstreamError("Postcode not found", "not_found");
  }

  // 4) Validate + upsert + return as "live".
  const coords = body.centroid?.coordinates;
  if (!coords || coords.length !== 2) {
    throw new PostcodeUpstreamError(
      "Postcode lookup returned no centroid",
      "unavailable",
    );
  }
  const [lng, lat] = coords;
  if (!Number.isFinite(lng) || !Number.isFinite(lat)) {
    throw new PostcodeUpstreamError(
      "Postcode lookup returned non-finite centroid",
      "unavailable",
    );
  }

  const city = body.city ?? null;
  const province = body.province ?? null;
  await writeToCache(cls.normalized, lng, lat, city, province);

  return {
    postcode: displayFor(cls),
    is_fsa: false,
    latlng: { lat, lng },
    city,
    province,
    source: "live",
    fetched_at: new Date().toISOString(),
  };
}

/**
 * Resolve a 3-char FSA via cache + Open North suffix-probe + SWR.
 * Cache key is the 3-char FSA itself (not the probe postcode), so a
 * cached FSA skips the probing dance on the second hit.
 */
async function resolveFsa(
  cls: { kind: "fsa"; normalized: string },
): Promise<ResolvedPostcode> {
  // 1) Cache check (keyed on the 3-char FSA).
  const cached = await readFromCache(cls.normalized);
  if (cached && isFresh(cached.fetched_at)) {
    return shapeFromCache(cached, cls, "cache");
  }

  // 2) Probe Open North with fallback suffixes. Track whether the
  // probes failed with "unavailable" (network/5xx) vs "not_found" so
  // we can SWR-fall-back to stale on the former.
  let resolved: OpenNorthPostcodeResponse | null = null;
  let anyUnavailable = false;
  for (const suffix of FSA_FALLBACK_SUFFIXES) {
    try {
      const probe = await fetchPostcode(`${cls.normalized}${suffix}`);
      if (probe !== "not_found") {
        resolved = probe;
        break;
      }
    } catch (err) {
      if (err instanceof PostcodeUpstreamError && err.kind === "unavailable") {
        anyUnavailable = true;
        continue;
      }
      throw err;
    }
  }

  if (!resolved) {
    // Either every probe 404'd or every probe failed unavailable.
    if (anyUnavailable && cached) {
      return shapeFromCache(cached, cls, "cache_stale");
    }
    if (anyUnavailable) {
      throw new PostcodeUpstreamError(
        "Postcode lookup service is unreachable",
        "unavailable",
      );
    }
    // All probes returned 404 — FSA is genuinely unresolvable.
    if (cached) await evictFromCache(cls.normalized);
    throw new PostcodeUpstreamError(
      "FSA not resolvable via Open North fallback probes",
      "not_found",
    );
  }

  const coords = resolved.centroid?.coordinates;
  if (!coords || coords.length !== 2) {
    throw new PostcodeUpstreamError(
      "Postcode lookup returned no centroid",
      "unavailable",
    );
  }
  const [lng, lat] = coords;
  if (!Number.isFinite(lng) || !Number.isFinite(lat)) {
    throw new PostcodeUpstreamError(
      "Postcode lookup returned non-finite centroid",
      "unavailable",
    );
  }

  const city = resolved.city ?? null;
  const province = resolved.province ?? null;
  await writeToCache(cls.normalized, lng, lat, city, province);

  return {
    postcode: cls.normalized,
    is_fsa: true,
    latlng: { lat, lng },
    city,
    province,
    source: "live",
    fetched_at: new Date().toISOString(),
  };
}

/**
 * Public entrypoint. Look up a postcode (6-char) or FSA (3-char)
 * against the cache + Open North + SWR layer.
 */
export async function resolvePostcode(input: string): Promise<ResolvedPostcode> {
  const cls = classifyPostcode(input);
  if (cls.kind === "invalid") {
    throw new PostcodeUpstreamError(
      "Invalid Canadian postcode (e.g. K1A 0A6) or FSA (e.g. K1A)",
      "invalid",
    );
  }
  if (cls.kind === "full") return resolveFullPostcode(cls);
  return resolveFsa(cls);
}
