---
title: Committees
description: Read access to committee transcripts via the meetings-list endpoint and the speech_type=committee search filter.
---

# Committees

Committee work is exposed two ways:

- **`GET /committees/meetings`** — distinct meetings list, derived from
  Hansard speech rows. Free-tier; **no TEI** cost.
- **`/search/speeches?speech_type=committee`** — full-text search
  inside committee transcripts. **Pro-tier** (TEI-embedded; see
  [Rate limiting](./rate-limiting.md#tei-semaphore-on-semantic-search)).

Coverage as of v1.0:

| Jurisdiction | Source | Speeches | Notes |
|---|---|---|---|
| Federal (HoC committees) | openparliament.ca | ~5.5K (P45-S1) | 100% MP-FK |
| Alberta (standing committees) | assembly.ab.ca PDFs | ~10K (L31-S2) | First provincial slice; 31% MLA-FK (transcripts are ~40% witnesses) |
| BC | hansard-bc | ~34K | Mostly **Committee of the Whole** — sittings in committee form, not standing-committee transcripts. Real BC standing-committee pipeline is still on the roadmap. |

Other provinces don't have committee transcripts ingested yet.

## `GET /committees/meetings`

Distinct committee meetings inferred from speeches with
`speech_type='committee'`.

### Query parameters

| Name | Type | Notes |
|---|---|---|
| `level` | `federal` \| `provincial` \| `municipal` | Filter by chamber level. |
| `province_territory` | 2-letter code | e.g. `AB`, `BC`. Federal: NULL. |
| `source_system` | string | Direct upstream filter — `openparliament` (federal), `assembly.ab.ca` (AB), `hansard-bc` (BC). |
| `from` | `YYYY-MM-DD` | Lower bound on first spoken-at within meeting. |
| `to` | `YYYY-MM-DD` | Upper bound. |
| `page` | int ≥ 1 | Default `1`. |
| `limit` | int 1–100 | Default `50`. |

### Response

```json
{
  "items": [
    {
      "meeting_url": "https://openparliament.ca/committees/justice/45-1/29/",
      "level": "federal",
      "province_territory": null,
      "source_system": "openparliament",
      "date": "2026-05-06",
      "first_spoken_at": "2026-05-06T15:30:00Z",
      "last_spoken_at": "2026-05-06T17:25:00Z",
      "speech_count": 184
    },
    {
      "meeting_url": "https://docs.assembly.ab.ca/LADDAR_files/docs/committees/hs/legislature_31/session_2/20260413_1030_01_hs.pdf",
      "level": "provincial",
      "province_territory": "AB",
      "source_system": "assembly.ab.ca",
      "date": "2026-04-13",
      "first_spoken_at": "2026-04-13T16:30:00Z",
      "last_spoken_at": "2026-04-13T18:15:00Z",
      "speech_count": 142
    }
  ],
  "page": 1,
  "limit": 50,
  "total": 5766,
  "pages": 116
}
```

### How `meeting_url` is computed

There's no `committee_meetings` table — meetings are derived per-row.

- **Federal openparliament.ca**: source URL is per-speech-turn
  (`https://openparliament.ca/committees/justice/45-1/29/larry-brock-1/`).
  The meeting key strips the per-speaker slug:
  `https://openparliament.ca/committees/justice/45-1/29/`. The path
  segment after `/committees/` is the committee acronym; the next is
  `<parliament>-<session>`; then the meeting number.
- **AB assembly.ab.ca**: source URL is the meeting PDF; the meeting
  key is the URL itself. Committee acronym is the path segment after
  `/committees/` (e.g. `hs` for Health).

If your client needs the committee acronym specifically, parse it
out of `meeting_url` — exposing a `committee_acronym` field as a
first-class column is a v1.1 candidate.

### Example

```bash
curl -s -H "Authorization: Bearer cpd_live_…" \
  "https://canadianpoliticaldata.org/api/public/v1/committees/meetings?level=federal&from=2026-01-01" \
  | jq '.items[] | {date, meeting_url, speech_count}'
```

## Full-text search inside transcripts

For "find every committee speech mentioning X" use the existing
search endpoint with the `speech_type=committee` filter:

```bash
curl -s -H "Authorization: Bearer cpd_live_…" \
  "https://canadianpoliticaldata.org/api/public/v1/search/speeches?q=carbon%20capture&speech_type=committee&limit=20"
```

This is the **PRO-tier** search route — it routes the query through
TEI for embedding and shares the 8-slot concurrency semaphore with
all other paid search calls. See [Rate
limiting](./rate-limiting.md#tei-semaphore-on-semantic-search) for the
503 + `Retry-After` semantics.

## Recipes

### Walk every meeting for one federal committee in a parliament

The meeting URL convention means you can filter post-fetch by URL
substring:

```bash
curl -s -H "Authorization: Bearer cpd_live_…" \
  "https://canadianpoliticaldata.org/api/public/v1/committees/meetings?level=federal&limit=100" \
  | jq '.items[] | select(.meeting_url | contains("/justice/45-1/"))'
```

### Fetch every speech in one meeting

The `meeting_url` is a prefix; combine with the speech search:

```bash
MURL="https://openparliament.ca/committees/justice/45-1/29/"
curl -s -H "Authorization: Bearer cpd_live_…" \
  "https://canadianpoliticaldata.org/api/public/v1/search/speeches?q=&speech_type=committee&limit=50" \
  | jq --arg m "$MURL" '[.items[] | select(.source_url | startswith($m))]'
```

(The empty `q=` triggers the route's session-listing fallback mode;
substitute a real query term for actual relevance ranking.)

## Caveats

- **BC misclassification.** A large chunk of BC `speech_type='committee'`
  rows are sittings of the Committee of the Whole inside the BC
  Legislative Assembly chamber — NOT standing-committee transcripts.
  When BC's real provincial-committee pipeline ships, these may be
  reclassified.
- **MLA-FK rates are lower than chamber Hansard.** Committee meetings
  bring in witnesses (not politicians), so the unresolved speeches in
  a committee transcript are usually correctly-unresolved witnesses,
  not a parsing failure.
- **No `committee_acronym` or `committee_name` as first-class fields**
  in v1.0. Parse them out of `meeting_url`. Promotion to columns is a
  v1.1 candidate once the column-derivation logic stabilises across
  more provinces.
