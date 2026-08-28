---
title: Constituency boundaries
description: Federal, provincial, and municipal electoral district boundaries sourced from Elections Canada, the provincial and territorial chief electoral officers, and individual municipalities, with paginated lookup, point-in-polygon, and full GeoJSON detail endpoints.
---

# Constituency boundaries

`/api/public/v1/boundaries/*` exposes electoral-district geometry for
343 federal ridings, every provincial and territorial legislature
including Nunavut, and municipal wards across Canada. **Free-tier.**

Boundaries come from the agencies that draw them — Elections Canada,
the provincial and territorial chief electoral officers, and individual
municipalities — not from a third-party mirror. That matters for reuse:
there is no single licence covering the set. The fourteen jurisdictions
publish under at least nine different sets of terms and several publish
none at all, so **read [Boundary licences](./licences.md) before you
redistribute anything**. Each response carries a `licence` object and a
`Link: rel="license"` header for the specific source behind that row.

For the full per-endpoint schema with "Try it out" buttons see the
**[Swagger UI](https://canadianpoliticaldata.org/api/public/v1/docs/)**
under the **Constituency boundaries** tag.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/boundaries` | Paginated list with `level`, `province_territory`, and `bbox` filters (metadata only — no GeoJSON) |
| `GET` | `/boundaries/lookup` | Point-in-polygon: find the riding containing a lat/lng at each level |
| `GET` | `/boundaries/{source_set}/{slug}` | Single boundary with simplified GeoJSON |

## `GET /boundaries`

Paginated list of constituency boundaries. **Metadata only** — the
response does not include GeoJSON, so a page of 100 stays
kilobyte-sized. Fetch geometry separately via `/boundaries/{set}/{slug}`
when you need it.

### Query parameters

| Name | Type | Notes |
|---|---|---|
| `level` | `federal` \| `provincial` \| `municipal` | Filter by level. |
| `province_territory` | 2-letter code | e.g. `ON`, `AB`. Federal ridings have this `null` — filter on `level=federal` instead. |
| `bbox` | `minLng,minLat,maxLng,maxLat` | WGS84 bounding-box filter. Uses the GIST index on the simplified geometry for fast lookup. |
| `page` | int ≥ 1 | Default `1`. |
| `limit` | int 1–100 | Default `50`. |

### Response

```json
{
  "items": [
    {
      "constituency_id": "federal-electoral-districts-2023-representation-order/35079",
      "name": "Ottawa Centre",
      "level": "federal",
      "province_territory": null,
      "source_set": "federal-electoral-districts",
      "area_sqkm": 40.73,
      "centroid": { "lng": -75.7076, "lat": 45.3915 },
      "effective_from": "2023-01-01",
      "effective_to": null,
      "boundaries_version": "current"
    }
  ],
  "page": 1,
  "limit": 50,
  "total": 342,
  "pages": 7
}
```

Cache-Control: `public, max-age=3600`.

### Example

```bash
curl -s -H 'Authorization: Bearer cpd_live_…' \
  'https://canadianpoliticaldata.org/api/public/v1/boundaries?level=provincial&province_territory=ON&limit=10' \
  | jq '.items[] | {name, area_sqkm, centroid}'
```

## `GET /boundaries/lookup`

Point-in-polygon lookup. Given a lat/lng **or** a postcode, returns
the containing electoral district at each level — the **"who's my MP,
MLA, and city councillor"** civic-app pattern in a single call.

### Query parameters

| Name | Type | Notes |
|---|---|---|
| `lat` | number, 40 – 85 | WGS84 latitude. Bounded to roughly Canada-plus-buffer; out-of-range inputs return 400. Pass alongside `lng`. |
| `lng` | number, -145 – -50 | WGS84 longitude. Pass alongside `lat`. |
| `postcode` | string | 6-char Canadian postcode (`K1A0A6`) or 3-char FSA (`K1A`). Alternative to `lat`/`lng`; if both are passed, `postcode` wins. Resolved from the StatCan National Address Register — see [Postcodes](./postcodes.md) for the licensing posture and FSA caveats. |
| `level` | `federal` \| `provincial` \| `municipal` | Optional — narrows to one level. Omit to look up all three. |

At least one of `(lat, lng)` or `postcode` must be present, else 400.

### Response

```json
{
  "federal": {
    "constituency_id": "federal-electoral-districts-2023-representation-order/35079",
    "name": "Ottawa Centre",
    "level": "federal",
    "province_territory": null,
    "source_set": "federal-electoral-districts",
    "area_sqkm": 40.73,
    "centroid": { "lng": -75.7076, "lat": 45.3915 },
    "effective_from": "2023-01-01",
    "effective_to": null,
    "boundaries_version": "current",
    "boundary_geojson": { "type": "MultiPolygon", "coordinates": [/* … */] }
  },
  "provincial": { "name": "Ottawa Centre", "...": "..." },
  "municipal":  { "name": "Somerset Ward", "...": "..." }
}
```

Levels with no containing riding come back as `null` (e.g. lat/lng in
an unincorporated area returns `municipal: null`). When you pass
`?level=federal`, the other two keys stay `null` in the response shape.

The simplified `boundary_geojson` (boundary_simple, ~555 m tolerance)
is included so a downstream map widget can render the matched riding
without a follow-up call. **Membership itself is computed against the
full unsimplified geometry** — points near district edges classify
exactly, even though the rendered polygon is smoothed.

Cache-Control: `public, max-age=3600`.

### Example — Parliament Hill (lat/lng)

```bash
curl -s -H 'Authorization: Bearer cpd_live_…' \
  'https://canadianpoliticaldata.org/api/public/v1/boundaries/lookup?lat=45.4242&lng=-75.6989' \
  | jq '{federal: .federal.name, provincial: .provincial.name, municipal: .municipal.name}'
```

### Example — same point via postcode

```bash
curl -s -H 'Authorization: Bearer cpd_live_…' \
  'https://canadianpoliticaldata.org/api/public/v1/boundaries/lookup?postcode=K1A0A6' \
  | jq '{federal: .federal.name, provincial: .provincial.name, municipal: .municipal.name}'
```

Returns the same three matches. The boundary entries are
byte-identical between `/boundaries/lookup` and `/postcodes/{postcode}`
so you can reuse one parser across both endpoints.

```json
{
  "federal":    "Ottawa Centre",
  "provincial": "Ottawa Centre",
  "municipal":  "Somerset Ward"
}
```

## `GET /boundaries/{source_set}/{slug}`

Single boundary with simplified GeoJSON. The two path params
reconstruct `constituency_id = source_set + '/' + slug` — this keeps
slashes out of the URL path so you don't have to URL-encode.

### Path parameters

| Name | Type | Notes |
|---|---|---|
| `source_set` | string | Boundary-set name, e.g. `federal-electoral-districts`, `alberta-electoral-districts` or `nunavut-electoral-districts`. ⚠ **Renamed 2026-08**: sets no longer carry the generation in the name — `federal-electoral-districts-2023-representation-order` is now `federal-electoral-districts` with `boundaries_version = "2023-representation-order"`. Pin the pair, not the name. |
| `slug` | string | Per-set slug. Federal ridings use numeric codes (`35079`); most provincial sets use kebab-case names (`calgary-bow`). |

### Query parameters

| Name | Type | Notes |
|---|---|---|
| `precision` | int 1–15 | Coordinate precision (decimal places) for the GeoJSON output. Default `6` (≈10 cm at the equator). Lower it to `4` for ~10 m precision and ~half the response size. |

### Response

```json
{
  "boundary": {
    "constituency_id": "federal-electoral-districts-2023-representation-order/35079",
    "name": "Ottawa Centre",
    "level": "federal",
    "province_territory": null,
    "source_set": "federal-electoral-districts",
    "area_sqkm": 40.73,
    "centroid": { "lng": -75.7076, "lat": 45.3915 },
    "effective_from": "2023-01-01",
    "effective_to": null,
    "boundaries_version": "current",
    "boundary_geojson": { "type": "MultiPolygon", "coordinates": [/* … */] }
  }
}
```

Returns `404 { code: "not_found" }` for unknown `source_set`/`slug`
combinations.

Cache-Control: `public, max-age=3600`.

### Example

```bash
curl -s -H 'Authorization: Bearer cpd_live_…' \
  'https://canadianpoliticaldata.org/api/public/v1/boundaries/federal-electoral-districts-2023-representation-order/35079?precision=4' \
  | jq '.boundary | {name, area_sqkm}'
```

## Recipes

### Render every Ontario provincial riding on a Leaflet map

```javascript
const ridings = await fetch(
  'https://canadianpoliticaldata.org/api/public/v1/boundaries?level=provincial&province_territory=ON&limit=100',
  { headers: { Authorization: 'Bearer cpd_live_…' } }
).then(r => r.json());

for (const r of ridings.items) {
  const detail = await fetch(
    `https://canadianpoliticaldata.org/api/public/v1/boundaries/${r.constituency_id}?precision=4`,
    { headers: { Authorization: 'Bearer cpd_live_…' } }
  ).then(r => r.json());
  L.geoJSON(detail.boundary.boundary_geojson).addTo(map);
}
```

A bulk-export-style single-file dataset is on the roadmap; the
per-riding fetch loop above is the right pattern for now.

### "Find my representatives" widget

```javascript
navigator.geolocation.getCurrentPosition(async (pos) => {
  const { latitude: lat, longitude: lng } = pos.coords;
  const res = await fetch(
    `https://canadianpoliticaldata.org/api/public/v1/boundaries/lookup?lat=${lat}&lng=${lng}`,
    { headers: { Authorization: 'Bearer cpd_live_…' } }
  ).then(r => r.json());

  console.log({
    federal:    res.federal?.name    ?? 'unknown',
    provincial: res.provincial?.name ?? 'unknown',
    municipal:  res.municipal?.name  ?? 'unknown',
  });
});
```

## Caveats

- **Federal ridings have `province_territory = null`.** Federal ridings
  can span provincial borders, so the column is left null by design.
  Filter on `level=federal` instead.
- **Simplified geometry is for rendering, not law.** The `boundary_simple`
  geometry returned in detail responses is simplified at ~555 m
  tolerance — visually identical to the full boundary at typical web
  zoom levels, but **not authoritative for edge cases**. For exact
  district membership at a point, use `/boundaries/lookup` (which
  queries the full unsimplified geometry server-side).
- **Versioning is temporal and NO LONGER single-state.** ⚠ This page
  previously said every live row carried `boundaries_version =
  "current"` with `effective_to = null`. That has not been true since
  2026-08: rows now carry the generation the agency actually named
  (`2023-representation-order`, `2025`, `2026`, …) and superseded
  generations are **end-dated, not deleted**, so `effective_to` is
  frequently populated. **If you pinned a client to `"current"` or
  assumed a null `effective_to`, it is already wrong.**

  Generations also flip on dates that are already in the table. The
  next one is **Québec on 2026-10-05**, when the province's map goes
  from 125 to 127 districts — six existing districts are renamed or
  expanded, and two are new. The list and detail endpoints continue to
  default to whatever is live on the day of the request, so a caller
  that does not pin a version will simply start receiving the new map.
- **Centroid is unweighted.** Centroids are computed from the polygon
  geometry, not population. For population-weighted centroids
  (campaign targeting, demographic mapping), join your own data.
