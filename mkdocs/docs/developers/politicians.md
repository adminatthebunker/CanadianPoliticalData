---
title: Politicians
description: List and detail endpoints for the ~2,000 Canadian politicians (federal MPs + provincial/territorial MLAs/MPPs/MNAs/MHAs + municipal councillors), with contact info, party, status, term dates, and constituency boundary.
---

# Politicians

`/api/public/v1/politicians/*` exposes the politicians roster: a list
endpoint sized for civic-app seeding ("the 87 sitting AB MLAs in one
call") and a detail endpoint that returns the full contact card —
email, phone, office addresses, party, status, term dates, websites,
and constituency boundary. **Free-tier** — any authenticated key works.

For the full per-endpoint schema with "Try it out" buttons see the
**[Swagger UI](https://canadianpoliticaldata.org/api/public/v1/docs/)**
under the **Politicians** and **Politicians (list)** tags.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/politicians` | Paginated list with `jurisdiction` / `role` / `status` / `constituency_id` / `q` filters |
| `GET` | `/politicians/{id}` | Single politician with contact info, websites, and boundary |
| `GET` | `/politicians/{id}/offices` | Structured office list — see [Contact info](./contact.md) |

## `GET /politicians`

Paginated list designed for seeding a per-jurisdiction politicians UI
in one call (the "find me the 87 sitting AB MLAs" use case).

### Query parameters

| Name | Type | Notes |
|---|---|---|
| `jurisdiction` | `federal` \| 2-letter province code | Maps to `level=federal` OR `(level=provincial AND province_territory=…)`. Omit for cross-jurisdiction. |
| `role` | string | Case-insensitive substring match on `elected_office` (e.g. `mla` matches "MLA"; `mp` matches "Member of Parliament"; `councillor` matches "Councillor"). Substring is intentional — different jurisdictions render the same role differently. |
| `status` | `sitting` \| `former` \| `all` | Defaults to `sitting`. |
| `constituency_id` | string | Open North constituency_id (`source_set/slug`), matched exactly. Use with `status=sitting` to get the current rep for a riding from a `/boundaries/{set}/{slug}` response in one call. |
| `q` | string ≤ 200 chars | Name substring (trigram-indexed). |
| `page` | int ≥ 1 | Default `1`. |
| `limit` | int 1–100 | Default `50`. |

### Response

```json
{
  "items": [
    {
      "id": "uuid",
      "full_name": "Hon. Janet Smith",
      "honorific": "Hon.",
      "party": "Alberta New Democratic Party",
      "status": "sitting",
      "level": "provincial",
      "province_territory": "AB",
      "constituency_id": "alberta-electoral-districts-2017/calgary-bow",
      "constituency_name": "Calgary-Bow",
      "elected_office": "MLA",
      "photo_url": "/assets/politicians/uuid.jpg",
      "email": "Calgary.Bow@assembly.ab.ca",
      "phone": "1 403 297-7104",
      "term_start_at": "2023-05-30T00:00:00Z",
      "last_verified_at": "2026-05-24T07:30:38Z"
    }
  ],
  "page": 1,
  "limit": 50,
  "total": 87,
  "pages": 2
}
```

`phone` falls back to the constituency office phone when the
top-level `politicians.phone` is null (covers most rows; the canonical
column is sparse).

`last_verified_at` is sourced from `politicians.updated_at` — the
closest signal of "when did we last touch this row" since the table
doesn't track a separate verification timestamp.

Cache-Control: `public, max-age=300`.

### Examples

```bash
# The headline use case: 87 sitting AB MLAs in one call
curl -s -H 'Authorization: Bearer cpd_live_…' \
  'https://canadianpoliticaldata.org/api/public/v1/politicians?jurisdiction=AB&role=mla&status=sitting&limit=100' \
  | jq '.total, .items[0]'

# Current rep for a specific riding (chain from a boundary call)
curl -s -H 'Authorization: Bearer cpd_live_…' \
  'https://canadianpoliticaldata.org/api/public/v1/politicians?constituency_id=alberta-electoral-districts-2017/calgary-glenmore&status=sitting' \
  | jq '.items[0] | {full_name, party, email}'

# Search by name
curl -s -H 'Authorization: Bearer cpd_live_…' \
  'https://canadianpoliticaldata.org/api/public/v1/politicians?q=poilievre&status=all' \
  | jq '.items[] | {full_name, status, party}'
```

## `GET /politicians/{id}`

Single politician with contact info, active websites + latest
infrastructure scan, and constituency boundary GeoJSON.

### Response

```json
{
  "politician": {
    "id": "uuid",
    "name": "Hon. Janet Smith",
    "first_name": "Janet",
    "last_name": "Smith",
    "honorific": "Hon.",
    "party": "Alberta New Democratic Party",
    "elected_office": "MLA",
    "level": "provincial",
    "province_territory": "AB",
    "constituency_name": "Calgary-Bow",
    "constituency_id": "alberta-electoral-districts-2017/calgary-bow",
    "email": "Calgary.Bow@assembly.ab.ca",
    "phone": "1 403 297-7104",
    "fax": null,
    "constituency_office_address": "#311A, 2525 Woodview Drive SW, Calgary, AB",
    "legislature_office_address": "5th Floor, 9820 - 107 Street, Edmonton\nAB",
    "mailing_address": null,
    "status": "sitting",
    "term_start_at": "2023-05-30T00:00:00Z",
    "term_end_at": null,
    "last_verified_at": "2026-05-24T07:30:38Z",
    "photo_url": "/assets/politicians/uuid.jpg",
    "personal_url": "https://janetsmith.ca/",
    "official_url": "https://www.assembly.ab.ca/members/calgary-bow",
    "social_urls": { "...": "..." },
    "is_active": true,
    "openparliament_slug": null,
    "ab_assembly_mid": "00187"
  },
  "websites": [/* websites with their latest infrastructure_scan */],
  "boundary": {
    "constituency_id": "alberta-electoral-districts-2017/calgary-bow",
    "name": "Calgary-Bow",
    "level": "provincial",
    "boundary_geojson": { "type": "MultiPolygon", "coordinates": [/* … */] },
    "centroid_lng": -114.16,
    "centroid_lat": 51.07
  }
}
```

See **[Contact info](./contact.md)** for the per-field semantics and
the `/offices` subresource (full structured list — useful when the
politician has multiple constituency offices).

Returns `404 { code: "not_found" }` for unknown UUIDs.

Cache-Control: `public, max-age=60`.

## Schema gaps (known limitations)

- **`honorific` is best-effort regex-derived from `name`.** Coverage
  is roughly 30–50% — most politicians don't carry a prefix in the
  `name` field. We match `Hon.`, `Rt. Hon.`, `Sen.`, `Sir`, `Dame`,
  `Dr.`, `Mr.`, `Mrs.`, `Ms.`, `Mx.`, `Prof.` Adding a structured
  column is a future migration.
- **`status` returns `sitting` \| `former` only.** Deceased
  politicians appear as `former` — we don't track that state
  separately today.
- **`mailing_address` is always `null` in v1.** The upstream
  (`politician_offices.kind`) discriminates `legislature` / `constituency` /
  `office` but doesn't tag a mailing-specific kind. Falls through to
  null until we tag the right rows.

## Recipes

### "Which MP represents this postcode?"

```bash
PC="K1A0A6"
CID=$(curl -s -H 'Authorization: Bearer cpd_live_…' \
        "https://canadianpoliticaldata.org/api/public/v1/postcodes/$PC" \
      | jq -r '.boundaries.federal.constituency_id')
curl -s -H 'Authorization: Bearer cpd_live_…' \
  "https://canadianpoliticaldata.org/api/public/v1/politicians?constituency_id=$CID&status=sitting" \
  | jq '.items[0] | {full_name, party, email, phone}'
```

### Roster of every sitting federal MP with full contact

```bash
PAGE=1
while :; do
  curl -s -H 'Authorization: Bearer cpd_live_…' \
    "https://canadianpoliticaldata.org/api/public/v1/politicians?jurisdiction=federal&role=mp&status=sitting&page=$PAGE&limit=100" \
    | jq -r '.items[] | [.full_name, .party, .email, .phone] | @tsv'
  PAGES=$(curl -s -H 'Authorization: Bearer cpd_live_…' \
    "https://canadianpoliticaldata.org/api/public/v1/politicians?jurisdiction=federal&role=mp&status=sitting&page=1&limit=100" \
    | jq .pages)
  [ "$PAGE" -ge "$PAGES" ] && break
  PAGE=$((PAGE + 1))
done
```
