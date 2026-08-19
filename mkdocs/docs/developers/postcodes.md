---
title: Postcodes
description: Resolve a Canadian postcode or FSA to lat/lng plus the containing federal/provincial/municipal ridings — the geocoding leg of "find my representatives" widgets.
---

# Postcodes

`/api/public/v1/postcodes/:postcode` resolves a Canadian postcode (or
3-character FSA) to a lat/lng centroid plus the containing electoral
ridings at every level — the missing geocoding leg that turns a user-
typed postcode into something `/boundaries/lookup` can act on.
**Free-tier.** Resolution is **fully local** — no upstream call is made
while serving your request.

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
  "source": "nar",
  "fetched_at": "2026-08-18T04:12:00Z",
  "address_points": 42,
  "approximate": false,
  "spans_districts": null,
  "boundaries": {
    "federal":    { "constituency_id": "federal-electoral-districts-2023-representation-order/35079", "name": "Ottawa Centre", "level": "federal", "...": "..." },
    "provincial": { "constituency_id": "ontario-electoral-districts-representation-act-2015/ottawa-centre", "name": "Ottawa Centre", "level": "provincial", "...": "..." },
    "municipal":  { "constituency_id": "ottawa-wards/somerset-ward", "name": "Somerset", "level": "municipal", "...": "..." }
  }
}
```

`source` is one of:

- `nar` — exact match in our copy of the Statistics Canada **National
  Address Register** (catalogue 46-26-0002, Statistics Canada Open
  Licence). 855,905 postal codes. This is the normal case.
- `cache` — exact match in a small override table holding codes the
  register cannot supply. The register is built from **civic
  addresses**, so PO-box-only, rural-route-only and large-volume-receiver
  codes are absent by construction — `K1A 0A6` (House of Commons) is the
  canonical example.
- `fsa_derived` — no exact match anywhere, so the point was averaged
  from the other known codes in the same forward sortation area.
  **Always accompanied by `approximate: true`. Read the next section
  before using it.**

!!! warning "`approximate: true` means the answer may be wrong"

    An FSA is not a riding, and half of them are not even *inside* one
    riding. Measured against our own boundary data: **50.1% of Canadian
    FSAs span more than one federal riding.** Toronto's `M5V` spans
    **five**.

    So when `approximate` is true, the single district in `boundaries`
    is the most likely answer, not a reliable one. Use
    **`spans_districts`** — present only for approximate resolutions —
    which lists *every* district the FSA touches, computed by
    point-in-polygon from each known member code. Show the user the set,
    or ask them for a full postcode.

    For exact matches (`nar` / `cache`), `approximate` is `false` and
    `spans_districts` is `null`.

- `address_points` — how many civic addresses were averaged to produce
  the centroid. `1` means a single address, which is positionally
  weaker than a high count. `null` for non-register sources.

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
| 200 | Postcode or FSA resolved + boundaries computed |
| 400 | Malformed postcode (doesn't match `A1A 1A1` or `A1A` shape) |
| 404 | No location on file — not in the register, not in the override table, and its FSA has no known member codes |

There is **no 503 path.** Resolution is local, so there is no upstream
that can be unavailable. (Before 2026-08-18 this endpoint proxied Open
North and returned 503 when that host was down — which it was, for
eleven days in August 2026. That is what prompted the change.)

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

Pass a 3-character FSA and we average the coordinates of every
6-character code we hold in that FSA, weighted by how many civic
addresses each represents. The response carries `source: "fsa_derived"`
and `approximate: true`.

**Read `spans_districts`, not `boundaries`.** An FSA is a mail-sorting
area, not an electoral one, and the two agree less often than people
expect. Measured against our own boundary data:

| | |
|---|---:|
| Canadian FSAs we hold codes for | 1,668 |
| …that span **more than one** federal riding | **835 (50.1%)** |
| Toronto `M5V` alone spans | **5 federal ridings** |

So for an FSA query, `boundaries.federal` is the riding containing the
weighted centroid — a reasonable single guess, and wrong about half the
time. `spans_districts` lists every district the FSA actually touches.
Show the set, or ask the user for their full postcode.

Exact 6-character codes do not have this problem and are marked
`approximate: false`.

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

## Where the data comes from

Resolution reads two local tables. There is no upstream in the request
path.

**`postcode_centroids`** — 855,905 codes derived from the Statistics
Canada **National Address Register** (catalogue 46-26-0002), under the
[Statistics Canada Open Licence](https://www.statcan.gc.ca/en/reference/licence),
which grants the explicit right to reproduce, distribute and
sublicence. We join the register's address and location files on
`LOC_GUID`, group by mailing postal code, and average the WGS84
coordinates — so a centroid is the centre of the civic addresses that
actually share that code, not a single sampled point. `address_points`
tells you how many were averaged.

**`postcode_cache`** — a small override table for codes the register
cannot supply, since the register is built from civic addresses.
PO-box-only, rural-route-only and large-volume-receiver codes have
none. `K1A 0A6` resolves from here.

Coverage is roughly 73–92% of active Canadian postal codes by exact
match; the remainder fall through to the FSA path above rather than
failing.

`X-Cache-Source` mirrors `source` for monitoring tools that read
headers rather than bodies, and `X-Postcode-Approximate: true` is set
on approximate resolutions.

### Why this changed

This endpoint used to proxy [Open North's](https://represent.opennorth.ca/)
Represent API with a 30-day cache in front. On 2026-08-07 that host's
TLS certificate expired *and* its origin began returning 502, and it
stayed down for eleven days. Our cache held eight rows, so effectively
every postal code in Canada returned 503 for the duration.

Rebuilding on an openly-licensed dataset we hold ourselves removes the
failure mode rather than mitigating it. We did not keep Open North as a
fallback: a fallback that is only exercised during an outage is a
fallback that fails during an outage.

## Caveats

- **Coverage is not complete, by construction.** The National Address
  Register lists civic addresses. A postal code with no civic address —
  PO-box-only, rural-route-only, some government and large-volume-receiver
  codes — is absent unless it is in our small override table. Those fall
  through to the FSA path and are marked `approximate: true`.
- **Postcode → boundaries is centroid-based.** A postal code that
  straddles a riding boundary resolves to whichever riding contains the
  centroid. `address_points: 1` is the weakest case — a single address
  with no averaging.
- **Coordinates are blockface centroids**, per the register's own
  documentation, not rooftop points. Ample for riding assignment; not a
  substitute for a rooftop geocoder.
- **No FSA polygons.** We derive FSA answers from member postal codes.
  If you need the polygon, Statistics Canada publishes a free FSA
  boundary file at
  [catalogue 92-179-X](https://www150.statcan.gc.ca/n1/en/catalogue/92-179-X).
- **`city` is the modal municipality** across the addresses sharing the
  code — a code spanning two municipalities reports the more common one.
  Cosmetic; use the structured boundary fields for anything programmatic.
