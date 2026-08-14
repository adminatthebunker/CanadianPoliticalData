import { query } from "../db.js";
import { resolvePostcode } from "./postcode.js";

/**
 * Postcode → current-representative politician IDs.
 *
 * Shared by /api/v1/lookup/postcode/:code (map drawer) and the search
 * routes' `postcode` filter so both surfaces resolve the same rep set:
 * geocode via lib/postcode.ts (30-day SWR cache over Open North), then
 * point-in-polygon against constituency_boundaries joined to politicians
 * on constituency_id, with a level+name fallback for rows lacking one.
 *
 * A point commonly sits in several current boundaries at once (federal
 * riding + provincial riding + municipal ward + city-wide polygon) —
 * intentional: the ward gives the ward councillor, the city polygon the
 * mayor / at-large members.
 *
 * Propagates PostcodeUpstreamError from resolvePostcode(); callers map
 * it to their own error shape.
 */

// Same LRU shape as anchorCache in routes/search.ts. Reps for a postcode
// only change on elections / boundary updates, so a short TTL is purely
// a memory bound, not a correctness need.
const REPS_CACHE_MAX = 200;
const REPS_CACHE_TTL_MS = 5 * 60_000;
const repsCache = new Map<string, { ids: string[]; expiresAt: number }>();

export async function politicianIdsForPostcode(input: string): Promise<string[]> {
  const key = input.replace(/[\s-]/g, "").toUpperCase();
  const now = Date.now();
  const hit = repsCache.get(key);
  if (hit && hit.expiresAt > now) {
    repsCache.delete(key);
    repsCache.set(key, hit);
    return hit.ids;
  }
  if (hit) repsCache.delete(key);

  const resolved = await resolvePostcode(input);
  const { lat, lng } = resolved.latlng;

  const rows = await query<{ id: string }>(
    `WITH hits AS (
       SELECT constituency_id, name, level
         FROM constituency_boundaries
        WHERE effective_to IS NULL
          AND ST_Contains(boundary, ST_SetSRID(ST_MakePoint($1, $2), 4326))
     )
     SELECT DISTINCT p.id
       FROM politicians p
       JOIN hits h
         ON p.constituency_id = h.constituency_id
         OR (p.constituency_id IS NULL
             AND p.level = h.level
             AND lower(p.constituency_name) = lower(h.name))
      WHERE p.is_active = true`,
    [lng, lat],
  );
  const ids = rows.map((r) => r.id);

  if (repsCache.size >= REPS_CACHE_MAX) {
    const oldest = repsCache.keys().next().value;
    if (oldest !== undefined) repsCache.delete(oldest);
  }
  repsCache.set(key, { ids, expiresAt: now + REPS_CACHE_TTL_MS });
  return ids;
}
