---
title: Postcodes
description: Resolve a Canadian postcode or FSA to lat/lng plus the containing federal/provincial/municipal ridings — the geocoding leg of "find my representatives" widgets.
---

# Postcodes

`/api/public/v1/postcodes/:postcode` resolves a Canadian postcode (or
3-character FSA) to a lat/lng centroid plus the containing electoral
ridings at every level — the missing geocoding leg that turns a user-
typed postcode into something `/boundaries/lookup` can act on.
**Free-tier** — postcode geocoding is freely redistributable through
Open North; we proxy them in real time.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/postcodes/{postcode}` | Full postcode (`K1A0A6`) or 3-char FSA (`K1A`) → lat/lng + boundaries |
| `GET` | `/boundaries/lookup?postcode=…` | Shortcut: skip the postcode envelope, get the boundaries directly. See [Boundaries](./boundaries.md). |

## `GET /postcodes/{postcode}`

### Path parameter

| Name | Type | Notes |
|---|---|---|
| `postcode` | string | 6-character Canadian postcode (`K1A0A6`, `K1A 0A6`, or `K1A-0A6`) **or** 3-character FSA (`K1A`). Case-insensitive. |

### Response

```json
{
  "postcode": "K1A 0A6",
  "is_fsa": false,
  "latlng": { "lat": 45.423781, "lng": -75.6974 },
  "city": "OTTAWA",
  "province": "ON",
  "source": "cache",
  "fetched_at": "2026-05-24T18:30:00Z",
  "boundaries": {
    "federal":    { "constituency_id": "federal-electoral-districts-2023-representation-order/35079", "name": "Ottawa Centre", "level": "federal", "...": "..." },
    "provincial": { "constituency_id": "ontario-electoral-districts-representation-act-2015/ottawa-centre", "name": "Ottawa Centre", "level": "provincial", "...": "..." },
    "municipal":  { "constituency_id": "ottawa-wards/somerset-ward", "name": "Somerset", "level": "municipal", "...": "..." }
  }
}
```

`source` is one of:

- `cache` — fresh row served from our local cache (within 30 days of the last upstream fetch).
- `cache_stale` — cache row was older than 30 days, we tried to refresh it from Open North, but Open North was unreachable so we returned the stale row anyway. Postcodes don't move; stale data is still correct.
- `live` — fresh upstream fetch (either no cache row existed, or the cache row was stale and the upstream succeeded). The cache row is updated on the way out.

- `boundaries.{level}` has the **byte-identical shape** to what
  `/boundaries/lookup` returns for that level — including the
  simplified `boundary_geojson`. Reuse one parser across both
  endpoints.
- `boundaries.{level}` is `null` when no riding at that level
  contains the centroid. Common for FSAs that fall in unincorporated
  areas (municipal `null`) or postcodes outside our boundary
  coverage.
- `latlng` is `{ lat, lng }` (lat first), not the GeoJSON
  `[lng, lat]` convention — matches what most JS map APIs expect.

Returns:

| Status | When |
|---|---|
| 200 | Postcode or FSA resolved + boundaries computed (from cache or live upstream) |
| 400 | Malformed postcode (doesn't match `A1A 1A1` or `A1A` shape) |
| 404 | Open North confirmed the postcode doesn't exist (cache row evicted if any) |
| 503 | Open North is unreachable AND no cache row exists to fall back on |

Cache-Control: `public, max-age=86400` (one day — postcodes don't move).

### Examples

```bash
# Parliament Hill
curl -s -H 'Authorization: Bearer cpd_live_…' \
  'https://canadianpoliticaldata.org/api/public/v1/postcodes/K1A0A6' \
  | jq '{
      postcode, city, latlng,
      federal:    .boundaries.federal.name,
      provincial: .boundaries.provincial.name,
      municipal:  .boundaries.municipal.name
    }'
```

```json
{
  "postcode": "K1A 0A6",
  "city": "OTTAWA",
  "latlng": { "lat": 45.423781, "lng": -75.6974 },
  "federal":    "Ottawa Centre",
  "provincial": "Ottawa Centre",
  "municipal":  "Somerset"
}
```

```bash
# Downtown Calgary as an FSA
curl -s -H 'Authorization: Bearer cpd_live_…' \
  'https://canadianpoliticaldata.org/api/public/v1/postcodes/T2P' \
  | jq '.boundaries.federal.name'
```
```text
"Calgary Centre"
```

## FSA support — how it works

Open North's `/postcodes/:code/` endpoint only accepts **6-character
postcodes**; passing a 3-character FSA returns 404 directly. To give
you FSA support we probe Open North with three fallback suffixes in
order — `1A1`, `0A0`, `1B1` — and use the centroid from the first one
that resolves.

This means an FSA's `latlng` is technically the centroid of a single
postcode within that FSA, not the FSA's geometric centroid. For the
"which dominant federal/provincial/municipal ridings cover this FSA"
use case this is almost always fine — within an FSA the spread is
kilometers, not riding-borders. But if you need FSA-polygon centroids
exactly, plug in Statistics Canada's free FSA centroid file
client-side instead.

## "Find my representatives" recipe

```bash
PC="K1A0A6"  # the postcode the user typed

# One call: resolve postcode → containing federal riding
CID=$(curl -s -H 'Authorization: Bearer cpd_live_…' \
        "https://canadianpoliticaldata.org/api/public/v1/postcodes/$PC" \
      | jq -r '.boundaries.federal.constituency_id')

# Second call: who currently represents that riding?
curl -s -H 'Authorization: Bearer cpd_live_…' \
  "https://canadianpoliticaldata.org/api/public/v1/politicians?constituency_id=$CID&status=sitting" \
  | jq '.items[0] | {full_name, party, email, phone}'
```

Two calls total — postcode → riding → representative. Repeat for the
provincial and municipal levels to populate all three "who's my X"
slots.

## Caching and the upstream relationship

Postcode resolutions are cached server-side in `public.postcode_cache`
(migration `0055`) — a small table keyed on the normalized postcode
with the centroid + city + province + a `fetched_at` timestamp.

Cache semantics:

- **Fresh** (cache row younger than 30 days): served from cache,
  no upstream call. Sub-millisecond response.
- **Stale** (row older than 30 days): we refetch from Open North in
  the request path. On success we overwrite the row; on Open North
  5xx / network failure we serve the stale row anyway (postcodes
  don't actually move — a stale row is still correct, we just
  haven't double-checked it lately). The response `source` field is
  `cache_stale` in this case so callers can see what happened.
- **Confirmed 404**: cache row evicted; subsequent calls re-resolve
  to a 404.
- **Cold + upstream down**: no cache fallback available, return 503.

The `source` field in every response is one of `cache` / `cache_stale`
/ `live`, plus a `fetched_at` timestamp showing when the underlying
data was last pulled from upstream. The `X-Cache-Source` response
header mirrors the same value for monitoring tools that look at
headers rather than bodies.

### About the upstream

[Open North](https://represent.opennorth.ca/) is the Canadian civic-
tech organization that maintains the Represent API. They aggregate
postcode-to-geography mappings from community-submitted CC0 data, not
from Canada Post's licensed PCAD file. They've redistributed this
data publicly without authentication for over a decade.

The 2012 Canada Post lawsuit against Geocoder.ca over postcode
geocoding was abandoned by Canada Post in 2016 with no judicial
finding, and Canadian copyright law doesn't recognize a sui-generis
database right. The practical landscape: civic-tech projects across
Canada cache postcode data routinely; we do the same. Caching
responses to queries our users made is no different in legal
substance from the `Cache-Control: max-age=86400` HTTP header we
already emit, except that it survives client-side cache eviction.

## Caveats

- **No FSA polygons.** We return a representative postcode centroid
  for FSAs, not the FSA polygon. If you need the polygon itself,
  Statistics Canada publishes a free FSA boundary file at
  [`statcan.gc.ca/.../lfsa000a21a_e.zip`](https://www150.statcan.gc.ca/n1/en/catalogue/92-179-X).
- **Postcode → boundaries is centroid-based.** A postcode that
  straddles a riding boundary will resolve to whichever riding
  contains the *centroid*. For postcodes-on-the-line edge cases,
  multiple-point sampling client-side is the right approach.
- **`city` and `province` come from Open North.** They're cosmetic;
  use the structured boundary fields for anything programmatic.
- **Open North's data quality is best-effort.** Some unknown
  postcode shapes still return 200 with an FSA-level centroid
  (Open North falls back to FSA centroid for unrecognized 6-char
  inputs). If you need strict postcode-existence checking, validate
  against PCAD client-side.
