---
title: Bills
description: Read access to federal + provincial legislation rows, stage-transition events, and politician sponsors via the bearer-token-authenticated public API.
---

# Bills

`/api/public/v1/bills/*` exposes the legislation layer: every bill the
scanner has ingested across the federal parliament and all currently-
live provincial legislatures, with stage-transition events and FK-joined
sponsor lists. **Free-tier** — any authenticated key works; rate-limited
by [tier](./rate-limiting.md).

The shape mirrors the database: one `bills` row per (session, bill_number),
one `bill_events` row per stage transition (first reading, second reading,
committee, royal assent, …), and one `bill_sponsors` row per politician
attached to the bill.

For the full per-endpoint schema with "Try it out" buttons see the
**[Swagger UI](https://canadianpoliticaldata.org/api/public/v1/docs/)**
under the **Bills** tag.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/bills` | Paginated list with jurisdiction + session + status + sponsor filters |
| `GET` | `/bills/{id}` | Single bill with denormalized counts (events, sponsors, votes) |
| `GET` | `/bills/{id}/events` | Stage-transition history, oldest first |
| `GET` | `/bills/{id}/sponsors` | Sponsor list, FK-joined to politicians |

## `GET /bills`

Paginated bills list.

### Query parameters

| Name | Type | Notes |
|---|---|---|
| `level` | `federal` \| `provincial` \| `municipal` | Filter by chamber level. |
| `province_territory` | 2-letter code | e.g. `ON`, `AB`, `BC`. Federal bills have this NULL — combine with `level=federal` to fetch only those. |
| `session_id` | UUID | Restrict to a single parliamentary session. Use `/search/sessions` to enumerate. |
| `status` | string | Free-text upstream status (`Royal Assent`, `Second Reading`, …). Exact match. |
| `sponsor_politician_id` | UUID | Bills sponsored or co-sponsored by this politician. |
| `q` | string ≤ 200 chars | Substring match against `title`, `short_title`, `bill_number` (ILIKE `%q%`). |
| `introduced_from` | `YYYY-MM-DD` | Lower bound on `introduced_date` (inclusive). |
| `introduced_to` | `YYYY-MM-DD` | Upper bound on `introduced_date` (inclusive). |
| `page` | int ≥ 1 | Default `1`. |
| `limit` | int 1–100 | Default `50`. |

### Response

```json
{
  "items": [
    {
      "id": "uuid",
      "session_id": "uuid",
      "level": "federal",
      "province_territory": null,
      "bill_number": "C-21",
      "title": "An Act to amend certain Acts and to make certain consequential amendments (firearms)",
      "short_title": null,
      "bill_type": "government",
      "status": "Royal Assent",
      "status_changed_at": "2023-12-15T18:30:00Z",
      "introduced_date": "2022-05-30",
      "source_system": "openparliament",
      "source_url": "https://openparliament.ca/bills/44-1/C-21/",
      "first_seen_at": "...",
      "updated_at": "...",
      "parliament_number": 44,
      "session_number": 1,
      "session_name": "44th Parliament, 1st Session",
      "events_count": 12,
      "sponsors_count": 1
    }
  ],
  "page": 1,
  "limit": 50,
  "total": 5542,
  "pages": 111
}
```

### Example

```bash
curl -s -H "Authorization: Bearer cpd_live_…" \
  "https://canadianpoliticaldata.org/api/public/v1/bills?level=federal&q=firearms&limit=10" \
  | jq '.items[] | {bill_number, title, status}'
```

## `GET /bills/{id}`

Single bill, joined to its `legislative_session` for parliament/session
labels, with denormalized `events_count`, `sponsors_count`, and
`votes_count`. Use the per-sub-resource endpoints below to drill in.

```json
{
  "bill": {
    "id": "uuid",
    "session_id": "uuid",
    "level": "federal",
    "province_territory": null,
    "bill_number": "C-21",
    "title": "...",
    "short_title": null,
    "bill_type": "government",
    "status": "Royal Assent",
    "status_changed_at": "...",
    "introduced_date": "2022-05-30",
    "source_id": "openparliament:44-1:C-21",
    "source_system": "openparliament",
    "source_url": "https://openparliament.ca/bills/44-1/C-21/",
    "parliament_number": 44,
    "session_number": 1,
    "session_name": "44th Parliament, 1st Session",
    "session_start_date": "2021-11-22",
    "session_end_date": "2025-01-06",
    "events_count": 12,
    "sponsors_count": 1,
    "votes_count": 4
  }
}
```

Returns `404 { code: "not_found" }` for unknown UUIDs.

## `GET /bills/{id}/events`

Append-only stage-transition log. One row per
(`stage`, `event_date`, `event_type`, `committee_name`) tuple. Ordered
by `event_date ASC` so callers can timeline a bill's progress without
re-sorting.

Federal events come from parl.ca/LegisInfo XML
(`Passed{Chamber}{Stage}DateTime` fields). Provincial events come from
per-jurisdiction Hansard scrapes and bills-status pages.

```json
{
  "bill_id": "uuid",
  "events": [
    {
      "id": "uuid",
      "bill_id": "uuid",
      "stage": "first_reading",
      "stage_label": "First Reading",
      "event_type": null,
      "outcome": null,
      "committee_name": null,
      "event_date": "2022-05-30",
      "source_url": "https://openparliament.ca/bills/44-1/C-21/",
      "created_at": "..."
    }
  ]
}
```

## `GET /bills/{id}/sponsors`

Politicians attached to a bill, ordered by `ordering ASC` (preserves
upstream display order).

```json
{
  "bill_id": "uuid",
  "sponsors": [
    {
      "id": "uuid",
      "bill_id": "uuid",
      "politician_id": "uuid",
      "sponsor_name_raw": "Hon. Marco Mendicino",
      "role": "sponsor",
      "ordering": 0,
      "created_at": "...",
      "politician_name": "Marco Mendicino",
      "politician_party": "Liberal",
      "openparliament_slug": "marco-mendicino"
    }
  ]
}
```

When `politician_id` is `null` the sponsor hasn't been resolved against
the `politicians` table yet — typically historical MLAs from sessions
we haven't backfilled. `sponsor_name_raw` is always populated.

## Recipes

### Every federal bill introduced in the current session

```bash
SID=$(curl -s "https://canadianpoliticaldata.org/api/public/v1/search/sessions?level=federal" \
       | jq -r '.sessions[0].session_id')
curl -s -H "Authorization: Bearer cpd_live_…" \
  "https://canadianpoliticaldata.org/api/public/v1/bills?session_id=$SID&limit=100"
```

### Sponsor activity for one politician

```bash
PID="00000000-0000-0000-0000-000000000000"  # Marco Mendicino's UUID
curl -s -H "Authorization: Bearer cpd_live_…" \
  "https://canadianpoliticaldata.org/api/public/v1/bills?sponsor_politician_id=$PID" \
  | jq '.items[] | {bill_number, title, status, introduced_date}'
```

### Timeline a single bill

```bash
ID="..."
curl -s -H "Authorization: Bearer cpd_live_…" \
  "https://canadianpoliticaldata.org/api/public/v1/bills/$ID/events" \
  | jq '.events[] | "\(.event_date)\t\(.stage)\t\(.outcome // "")"'
```

## Caveats

- **`status` is free-text upstream**. Same logical stage may render as
  `Second Reading` (federal openparliament), `2nd Reading` (some
  provincial scrapes), or `Adopté` (Quebec). Use `bill_events.stage`
  for the canonical machine-readable enum (`first_reading`,
  `second_reading`, `committee`, `third_reading`, `royal_assent`,
  `introduced`, `withdrawn`).
- **`introduced_date` is denormalized from `bill_events`** where
  available. For some provinces it's still NULL pending the
  per-jurisdiction backfill (`relink-bill-introduced-dates`).
- **Sponsor resolution rate varies by jurisdiction.** Federal: ~86%.
  Most provinces: 60-100% after the per-jurisdiction roster backfills.
  Pre-2006 sessions: lower — historical rosters are still landing.
