---
title: Politician contact info
description: Email, phone, fax, and office addresses for Canadian politicians — embedded in the politician detail response and available as a structured offices subresource.
---

# Politician contact info

Contact info for the ~2,000 politicians in the dataset is available in
two shapes:

1. **Embedded in `/politicians/{id}`** — convenience fields on the
   detail response for rendering a contact card.
2. **Structured at `/politicians/{id}/offices`** — full list with
   lat/lng, hours, fax, and one row per office. Useful for politicians
   with multiple constituency offices.

Both are **free-tier**. The data originates from
[Open North's Represent API](https://represent.opennorth.ca/) which
mirrors the per-member pages every legislature publishes. PIPEDA's
business-contact-information exemption covers this category (public
officials acting in a professional capacity); we are not the
upstream of last resort.

## Convenience fields on `/politicians/{id}`

The detail response's `politician` object carries:

| Field | Type | Notes |
|---|---|---|
| `email` | string \| null | Constituency office email from `politicians.email`. |
| `phone` | string \| null | Prefers `politicians.phone`; falls back to constituency office phone when null. Not E.164-normalized — formatting matches what the upstream legislature publishes (commonly `1 403 297-7104`). |
| `fax` | string \| null | Constituency office fax. |
| `constituency_office_address` | string \| null | Freeform multi-line address formatted from the most recent constituency-office row. Shape: `address\ncity, province_territory  postal_code`. |
| `legislature_office_address` | string \| null | Same shape, from the legislature-office row. |
| `mailing_address` | string \| null | Always `null` in v1 — no upstream discriminator separates mailing from constituency / legislature offices. |
| `honorific` | string \| null | Best-effort regex match against `name` prefix (`Hon.`, `Rt. Hon.`, `Sen.`, `Dr.`, etc.). |
| `status` | `sitting` \| `former` | Derived from `is_active` AND current term presence. Deceased politicians appear as `former`. |
| `term_start_at` / `term_end_at` | timestamptz \| null | Most recent term boundaries. |

When a politician has **multiple constituency offices**, the
embedded `constituency_office_address` shows the most-recently-updated
row. To see all offices, use the subresource below.

See **[Politicians](./politicians.md)** for the full detail response
shape including websites and boundary.

## `GET /politicians/{id}/offices`

Full structured office list. Multiple rows per politician are
preserved — a politician with two constituency offices keeps both.

### Path parameter

| Name | Type | Notes |
|---|---|---|
| `id` | UUID | The politician's `id`. |

### Response

```json
{
  "items": [
    {
      "kind": "constituency",
      "address": "#311A, 2525 Woodview Drive SW",
      "city": "Calgary",
      "province_territory": "AB",
      "postal_code": "T2W 4N4",
      "phone": "1 403 297-7104",
      "fax": null,
      "email": null,
      "hours": "Tue-Thu 9:00-16:00",
      "lat": 50.92,
      "lng": -114.10,
      "source": "opennorth"
    },
    {
      "kind": "legislature",
      "address": "5th Floor, 9820 - 107 Street",
      "city": "Edmonton",
      "province_territory": "AB",
      "postal_code": "T5K 1E7",
      "phone": "1 780 427-2655",
      "fax": null,
      "email": null,
      "hours": null,
      "lat": null,
      "lng": null,
      "source": "opennorth"
    }
  ]
}
```

- `kind` values are `constituency`, `legislature`, or `office` (a
  fallback bucket Open North uses when the upstream legislature
  doesn't specify).
- Ordering: constituency → legislature → office, then most-recently-
  updated first within each kind.
- `lng` is aliased from PostGIS column `lon` so it matches the
  `lng` naming everywhere else in the public API.

Returns `404 { code: "not_found" }` for unknown politician UUIDs.
Empty `items` array for politicians with no offices on file (rare —
mostly historical unrostered politicians).

Cache-Control: `public, max-age=600`.

### Example

```bash
PID="..."
curl -s -H 'Authorization: Bearer cpd_live_…' \
  "https://canadianpoliticaldata.org/api/public/v1/politicians/$PID/offices" \
  | jq '.items[] | {kind, address, phone, lat, lng}'
```

## Recipes

### Render an MLA contact card from one detail call

```bash
PID="..."
curl -s -H 'Authorization: Bearer cpd_live_…' \
  "https://canadianpoliticaldata.org/api/public/v1/politicians/$PID" \
  | jq '.politician | {
        name, honorific, party, status,
        email, phone,
        constituency: .constituency_office_address,
        legislature:  .legislature_office_address
      }'
```

### "Email every sitting AB MLA" (legitimate use; respect rate limits)

```bash
curl -s -H 'Authorization: Bearer cpd_live_…' \
  'https://canadianpoliticaldata.org/api/public/v1/politicians?jurisdiction=AB&role=mla&status=sitting&limit=100' \
  | jq -r '.items[] | .email // empty' \
  > ab-mla-emails.txt
```

Mass-contact via the API is **not prohibited** for legitimate civic
purposes (open letters, journalism, constituent organizing) but is
**rate-limited**: 60 req/hr per key on the free tier means enumerating
the full 1,500-politician roster takes ~25 hours. See
[Rate limiting](./rate-limiting.md). Harassment, defamation, and
spam-marketing fall under [our takedown policy](https://docs.canadianpoliticaldata.org/about/takedown/).

## Caveats

- **`phone` format varies by jurisdiction.** Some upstreams render
  `1 403 297-7104`, some `(403) 297-7104`, some `403.297.7104`. We
  pass through what Open North gives us. Normalize client-side if
  you need a canonical format (E.164 or otherwise).
- **`fax` is sparsely populated.** Mostly federal MPs and Quebec
  MNAs; most provincial MLAs returned a fax number to the upstream
  legislature historically but ingest coverage varies.
- **`hours`, `lat`, `lng` are nullable.** Open North's coverage of
  the structured fields is best in federal + ON + AB; smaller
  legislatures often supply just `address` + `phone`.
- **`mailing_address` is always null in v1.** Use
  `legislature_office_address` as a fallback for mail — most
  legislatures consider that the canonical mailing endpoint.
- **`source` is no longer always `opennorth`.** That mirror was retired
  in August 2026 and replacement ingesters have started landing:
  Québec municipal rows carry `mamh-qc` (the province's own election
  result) and Ontario municipal rows `amo-on`. Most rows are still
  `opennorth` — those are frozen at the mirror's final state, which
  captured every election up to its retirement, so they are broadly
  accurate but will not pick up future changes. Treat `source` as a
  provenance field with an open set of values, not a constant.
