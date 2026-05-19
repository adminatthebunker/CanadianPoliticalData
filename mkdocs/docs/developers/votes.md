---
title: Votes
description: Read access to recorded chamber votes across federal + provincial legislatures, including per-politician position breakdowns, via the bearer-token-authenticated public API.
---

# Votes

`/api/public/v1/votes/*` exposes the voting layer: every recorded
division, voice vote, acclamation, and consensus event the scanner
has extracted across the federal parliament and the live provincial
legislatures. **Free-tier** — any authenticated key works.

The shape mirrors the database: one `votes` row per event, with optional
`vote_positions` children (one per politician who participated, when
the upstream source reports individual positions — divisions yes,
voice votes no).

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/votes` | Paginated list with jurisdiction + session + bill + result filters |
| `GET` | `/votes/{id}` | Single vote with motion text + tallies + bill linkage |
| `GET` | `/votes/{id}/positions` | Per-politician position breakdown |

## `GET /votes`

Paginated votes list.

### Query parameters

| Name | Type | Notes |
|---|---|---|
| `level` | `federal` \| `provincial` \| `municipal` | Filter by chamber level. |
| `province_territory` | 2-letter code | e.g. `ON`, `AB`, `BC`. Federal: NULL. |
| `session_id` | UUID | Restrict to a single parliamentary session. |
| `bill_id` | UUID | Votes attached to a specific bill. |
| `result` | `passed` \| `defeated` \| `tied` \| `withdrawn` \| `deferred` | Vote outcome. |
| `vote_type` | `division` \| `voice` \| `acclamation` \| `consensus` | Shape of the vote. Only `division` carries individual `vote_positions`. |
| `occurred_from` | `YYYY-MM-DD` | Lower bound on `occurred_at` (inclusive). |
| `occurred_to` | `YYYY-MM-DD` | Upper bound on `occurred_at` (inclusive). |
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
      "bill_id": "uuid",
      "speech_id": "uuid",
      "vote_type": "division",
      "occurred_at": "2023-05-18T18:23:00Z",
      "result": "passed",
      "ayes": 209,
      "nays": 117,
      "abstentions": 0,
      "motion_text": "That Bill C-21 be now read a third time and do pass.",
      "source_system": "openparliament",
      "source_url": "https://openparliament.ca/votes/44-1/337/",
      "parliament_number": 44,
      "session_number": 1,
      "session_name": "44th Parliament, 1st Session",
      "bill_number": "C-21",
      "bill_title": "An Act to amend ...",
      "positions_count": 326
    }
  ],
  "page": 1,
  "limit": 50,
  "total": 11784,
  "pages": 236
}
```

### Example

```bash
curl -s -H "Authorization: Bearer cpd_live_…" \
  "https://canadianpoliticaldata.org/api/public/v1/votes?level=federal&result=defeated&occurred_from=2023-01-01&limit=10" \
  | jq '.items[] | {bill_number, motion_text, ayes, nays, occurred_at}'
```

## `GET /votes/{id}`

Single vote with full motion text + bill linkage.

```json
{
  "vote": {
    "id": "uuid",
    "session_id": "uuid",
    "level": "federal",
    "province_territory": null,
    "bill_id": "uuid",
    "speech_id": "uuid",
    "vote_type": "division",
    "occurred_at": "...",
    "result": "passed",
    "ayes": 209,
    "nays": 117,
    "abstentions": 0,
    "motion_text": "...",
    "source_system": "openparliament",
    "source_url": "...",
    "parliament_number": 44,
    "session_number": 1,
    "session_name": "44th Parliament, 1st Session",
    "bill_number": "C-21",
    "bill_title": "...",
    "bill_short_title": null,
    "positions_count": 326
  }
}
```

## `GET /votes/{id}/positions`

Per-politician breakdown. **Not paginated** — bounded per-vote (~338
rows for federal divisions; smaller for provincial chambers).

```json
{
  "vote_id": "uuid",
  "positions": [
    {
      "id": "uuid",
      "vote_id": "uuid",
      "politician_id": "uuid",
      "politician_name_raw": "Hon. Marco Mendicino",
      "party_at_time": "Liberal",
      "constituency_at_time": "Eglinton—Lawrence",
      "position": "yea",
      "created_at": "...",
      "politician_name": "Marco Mendicino",
      "politician_party_current": "Liberal",
      "openparliament_slug": "marco-mendicino"
    }
  ]
}
```

For voice / acclamation / consensus votes this list may be **empty**.
That's not the same as "nobody voted" — the upstream simply didn't
report individual positions. Check `vote.vote_type` first.

`party_at_time` is the politician's party affiliation at the moment
the vote occurred (preserved across floor-crossings); `politician_party_current`
is their party today (or last-known if they're no longer sitting).

## Recipes

### Every federal climate vote since 2023, with vote breakdown

```bash
# 1. Find votes on bills mentioning "climate"
curl -s -H "Authorization: Bearer cpd_live_…" \
  "https://canadianpoliticaldata.org/api/public/v1/bills?q=climate&level=federal&introduced_from=2023-01-01" \
  | jq -r '.items[].id' > /tmp/bill_ids.txt

# 2. For each bill, list its votes
while read BID; do
  curl -s -H "Authorization: Bearer cpd_live_…" \
    "https://canadianpoliticaldata.org/api/public/v1/votes?bill_id=$BID"
done < /tmp/bill_ids.txt | jq -s '[.[].items[]] | sort_by(.occurred_at)'
```

### How did one politician vote on every bill in a session?

```bash
PID="..."
SID="..."
# 1. List all votes in the session
curl -s -H "Authorization: Bearer cpd_live_…" \
  "https://canadianpoliticaldata.org/api/public/v1/votes?session_id=$SID&limit=100" \
  | jq -r '.items[].id' > /tmp/vote_ids.txt

# 2. For each vote, extract just this politician's position
for VID in $(cat /tmp/vote_ids.txt); do
  curl -s -H "Authorization: Bearer cpd_live_…" \
    "https://canadianpoliticaldata.org/api/public/v1/votes/$VID/positions" \
    | jq --arg pid "$PID" '.positions[] | select(.politician_id == $pid) | {vote_id, position}'
done
```

### Find party-line breakers on a specific vote

```bash
VID="..."
curl -s -H "Authorization: Bearer cpd_live_…" \
  "https://canadianpoliticaldata.org/api/public/v1/votes/$VID/positions" \
  | jq '[.positions[]] | group_by(.party_at_time) |
        map({party: .[0].party_at_time,
             counts: (group_by(.position) | map({(.[0].position): length}) | add)})'
```

## Caveats

- **Provincial coverage varies.** Federal: 100% politician-FK via
  `openparliament_slug`. NB/QC/AB: hybrid division + consensus
  detection from Hansard regex. NT/NU: consensus-only (no party
  line). Some `vote_type='consensus'` rows have **zero positions**
  by design.
- **`abstentions` may be NULL** on provinces whose Hansard doesn't
  report it separately from `absent`.
- **Vote → bill linkage isn't 100%**. Federal: 54.7% (the rest are
  non-bill divisions — supply, procedural motions). Other levels:
  varies.
