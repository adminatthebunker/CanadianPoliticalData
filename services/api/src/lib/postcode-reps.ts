import { query } from "../db.js";
import { resolvePostcode } from "./postcode.js";
import { currentBoundary } from "./boundary-temporal.js";

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
       SELECT constituency_id, name, level, province_territory
         FROM constituency_boundaries
        WHERE ${currentBoundary()}
          AND ST_Contains(boundary, ST_SetSRID(ST_MakePoint($1, $2), 4326))
     )
     SELECT DISTINCT p.id
       FROM politicians p
       JOIN hits h
         ON p.constituency_id = h.constituency_id
         -- Name fallback for politicians ingested without a constituency_id
         -- (senators, hand-curated rosters, gap-fillers). Scoped deliberately:
         --
         --   * NOT at municipal level. Ward names are not unique — "Ward 1"
         --     names 48 polygons across 48 sets nationally, "Ward 3" 47,
         --     "Ward 2" 46, and 34 municipal names collide in total. An
         --     unscoped match would attribute one city's councillors to up to
         --     47 others. Verified lossless: the only 5 active municipal
         --     politicians with a NULL constituency_id are QC rows whose names
         --     match ZERO boundaries, so this fallback rescues nothing here.
         --   * province_territory must agree. Federal district names are unique
         --     nationally (0 collisions) but provincial ones are not — the sole
         --     case is "Richmond", which exists in both BC and NS.
         --
         -- Today this is latent rather than live (only those 5 rows have a NULL
         -- constituency_id), but a missing upstream boundary_url sets that
         -- column NULL, which is exactly how 41 BC districts lost their link.
         OR (p.constituency_id IS NULL
             AND h.level <> 'municipal'
             AND p.level = h.level
             AND p.province_territory IS NOT DISTINCT FROM h.province_territory
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
