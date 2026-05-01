# Federal votes extractor — 2026-04-30

Closes the partisan-division branch of the votes layer. NT (`nt_votes.py`,
shipped earlier today) validated `vote_type='consensus'` with empty
`vote_positions`. Federal validates `vote_type='division'` with populated
tallies and per-MP positions — the dominant shape across the rest of the
corpus.

This is the **cleanest votes-data path in the project**: openparliament.ca
exposes structured JSON for every recorded division, and the per-MP
ballot records carry `politician_url` slugs that match
`politicians.openparliament_slug` exactly. **Politician resolution is
100% on the smoke test** — every MP slug found a politicians row,
zero unresolved.

## What shipped

```
services/scanner/src/legislative/
  federal_votes.py                       NEW — openparliament.ca structured-JSON extractor

services/scanner/src/__main__.py         1 new Click command:
  extract-federal-votes

services/scanner/src/jobs_catalog.py     Mirror entry
services/api/src/routes/admin.ts         UI catalog mirror

scripts/seed-daily-ingest-schedules.sql  Federal chain extended:
  11:00 bills → 11:15 Hansard → 11:30 votes (NEW)

docs/research/federal.md                 Status snapshot — votes "live"
TODO.md / docs/timeline.md               Re-sync — federal votes done
```

## Source map

| Endpoint | URL | Role |
|---|---|---|
| Vote list | `/votes/?session={S}&format=json&limit=500` | Discovery; per-vote summary records |
| Per-vote ballots | `/votes/ballots/?vote={vote_url}&format=json&limit=500` | Per-MP positions |
| (not used) Vote detail | `/votes/{S}/{N}/?format=json` | All needed fields are in the list endpoint |

The list endpoint already carries `bill_url`, `session`, `number`,
`date`, `description`, `result`, `yea_total`, `nay_total`, `paired_total`,
and the canonical `url`. Skipping the detail fetch saves ~50% of API calls
without losing any field that maps to the schema.

## Schema mapping

| `votes` column | Source |
|---|---|
| `level` | `'federal'` |
| `province_territory` | `NULL` |
| `bill_id` | Looked up via `vote.bill_url` against `bills.raw->>'url'` |
| `speech_id` | `NULL` (future post-pass via `context_statement`) |
| `vote_type` | `'division'` (every openparliament.ca vote is a recorded division) |
| `occurred_at` | Vote `date` at noon UTC |
| `result` | `Passed`→`passed`, `Failed`→`defeated`, `Tied`→`tied`, `Withdrawn`→`withdrawn` |
| `ayes` / `nays` / `abstentions` | `yea_total` / `nay_total` / `paired_total` |
| `motion_text` | `description.en` (English motion text from the bilingual object) |
| `source_url` | `https://api.openparliament.ca{vote.url}` (canonical absolute URL) |

| `vote_positions` column | Source |
|---|---|
| `politician_id` | `politicians.openparliament_slug` exact match on slug from `politician_url` |
| `politician_name_raw` | The slug itself (openparliament.ca ballots don't carry display names) |
| `position` | `Yes`→`yea`, `No`→`nay`, `Paired`→`paired`, others→`absent` |
| `party_at_time` / `constituency_at_time` | `NULL` (not on ballot record; available via politicians join) |

## Why this is the cleanest pipeline in the project

1. **Exact-string FK match for politicians**: `/politicians/ziad-aboultaif/` → slug `ziad-aboultaif` → `politicians.openparliament_slug = 'ziad-aboultaif'`. No name normalization, no surname disambiguation, no date-windowed lookup. Compare to BC's 3-tier lookup, QC's parens-name extraction, NT's slug-FK (cleanest sub-national but still required parsing).

2. **Structured tallies + result**: `yea_total`, `nay_total`, `paired_total`, and `result` come directly off the JSON. No regex, no text classification.

3. **Bill linkage is exact**: `bill_url='/bills/44-1/C-9/'` matches `bills.raw->>'url'='/bills/44-1/C-9/'` — same path-relative string. Either it matches a bill or there's no bill (procedural motion); no ambiguity.

4. **One pagination loop covers everything**: list endpoint paginates linearly through all session votes; ballot endpoint paginates linearly through all MPs per vote. No multi-stage discovery, no per-page edge cases.

## Coverage

**Full historical corpus shipped same day** (2026-04-30). Final ledger:

| Session | Votes | Positions | Date span |
|---|---:|---:|---|
| 39-1 | 216 | 66,528 | 2006-05 → 2007-09 |
| 39-2 | 157 | 48,356 | 2007-10 → 2008-09 |
| 40-1 | 1 | 308 | 2008-11 (very short) |
| 40-2 | 158 | 48,822 | 2009-01 → 2009-12 |
| 40-3 | 204 | 62,420 | 2010-03 → 2011-03 |
| 41-1 | 760 | 233,206 | 2011-06 → 2013-09 |
| 41-2 | 467 | 142,478 | 2013-10 → 2015-08 |
| 42-1 | 1,379 | 463,572 | 2015-12 → 2019-09 |
| 43-1 | 26 | 8,788 | 2019-12 → 2020-08 (COVID-shortened) |
| 43-2 | 185 | 62,486 | 2020-09 → 2021-08 |
| **44-1** | **928** | **311,735** | **2021-11 → 2024-12** |
| **Total** | **4,481** | **1,448,699** | **2006-05 → 2024-12 (18.5 years)** |

Wall time: ~95 minutes for the historical 10-session sequential backfill (much faster than the projected 3-4 hours; per-session pacing was 2-30 minutes depending on vote count).

## Politician-FK resolution: 99.98%

Across the 1,448,699 vote_positions, **1,448,407 are politician_id-resolved** via `openparliament_slug` exact match. The 292 unresolved are entirely **Stephen Owen** (Liberal MP for Vancouver Quadra, 2000–2008), identified on openparliament.ca by **numeric ID 218** rather than a kebab-case slug. He doesn't exist in our `politicians` table at all (the openparliament-keyed roster ingests current MPs primarily). His ballot records are preserved with `politician_name_raw='218'` and `politician_id=NULL` for future enrichment.

| Session | Unresolved | Note |
|---|---:|---|
| 39-1 | 216 | All Stephen Owen (1 per vote) |
| 39-2 | 76 | All Stephen Owen (Owen left between 39-1 and 39-2) |
| 40-1 → 44-1 | 0 | Modern roster intact |

Fix path (if needed): either insert Stephen Owen as a single politicians row keyed on `openparliament_slug='218'` (polluting the slug column with a numeric identifier), or extend the schema with a separate `openparliament_id INTEGER` column and resolve via that. Deferred.

## Bill linkage rate

Final state: **458 of 4,481 votes (10.2%) are bill_id-linked** — but with a caveat. Only **44-1's 928 votes** had bills available in our DB to link against (49.4% bill-linked rate within 44-1). All 10 historical sessions ran with **0% bill linkage** because our `bills` table only contains ~412 federal bills, all from 44-1.

This is the known asymmetry called out in the plan: federal bills historical backfill is a separate workstream. Once historical bills land, `bill_id` re-resolution is a simple UPDATE pass on `votes` where `bill_url` is set:

```sql
UPDATE votes v
   SET bill_id = b.id, updated_at = now()
  FROM bills b
 WHERE v.source_system = 'votes-federal'
   AND v.bill_id IS NULL
   AND v.raw->'openparliament_vote'->>'bill_url' IS NOT NULL
   AND b.raw->>'url' = v.raw->'openparliament_vote'->>'bill_url';
```

Procedural motions (motion to adjourn, motion to proceed, supply days, opposition motions) have `bill_url=null` regardless and stay unlinked by design.

## Daily schedule

```
11:00 UTC  Federal bills daily ingest
11:15 UTC  Federal Hansard daily ingest
11:30 UTC  Federal votes extraction       ← NEW
```

The chain order matters: bills ingested first → bill_url linkage available; Hansard second → debate-context speech rows in place; votes third → can match against both. First fire 2026-05-01 11:30 UTC.

## Pre-flight gotchas

1. **`API-Version: v1` header is required** for stable JSON shape. openparliament.ca's default version may change; pinning v1 in the User-Agent path keeps schema consistent.

2. **Skipping the per-vote detail fetch** saves ~50% of API calls. The list endpoint carries every field that maps to our schema; the detail endpoint adds `context_statement` (debate URL) and `party_votes` (party-level breakdown), neither of which we currently store.

3. **`politician_name_raw=slug` instead of display name**: openparliament.ca ballots don't include a display name on the per-MP record — only the slug URL. The UNIQUE constraint on `(vote_id, politician_name_raw)` requires a stable per-MP string; the slug fits perfectly and joins back to `politicians.name` when needed.

4. **`Didn't vote` and `Absent` ballot enums** both map to `position='absent'`. The schema's CHECK constraint enforces our 5-value enum; openparliament's source data has slight variations across sessions which we collapse defensively.

## Verification

1. **Smoke**: `extract-federal-votes --session 44-1 --limit-votes 5` inserts 5 votes with populated tallies + ~1680 vote_positions, all 100% politician-resolved.
2. **Politician FK rate**: should be 100% (or near it) on 44-1 because openparliament_slug coverage is full for current MPs.
3. **Bill linkage rate**: 30-60% on a representative sample (procedural motions skew higher than reading votes).
4. **Idempotency**: re-run produces 0 inserts, all updates.
5. **Aggregate consistency**: `SUM(yeas) FROM vote_positions WHERE position='yea'` should equal `SUM(ayes) FROM votes` modulo edge cases (paired, MPs with NULL politician_id).

## Follow-ups

- **Historical sessions (39-1 through 43-2)** — ✅ done same day. 3,553 historical votes / 1,137,003 positions across 10 sessions, 95 min wall time.
- **Stephen Owen edge case** — 292 unresolved positions identified by openparliament.ca numeric ID `218` instead of kebab-case slug. Either insert him manually or add `openparliament_id INTEGER` column to politicians.
- **Federal historical bills ingestion** — would lift bill-linkage from 10.2% (44-1 only) to ~50% corpus-wide via the trivial UPDATE shown above. Separate workstream.
- **`speech_id` linkage** — match `context_statement` debate URL against federal speeches. Per-vote it'd need one extra detail fetch + a date+url scan against `speeches`. Defer.
- **Provincial votes extraction** (BC/AB/MB/QC/ON/NS/NB/NL) — Hansard-text regex like NT, but with populated `vote_positions` more often (BC division calls produce numerical tallies). Same shape as `nt_votes.py`. Mechanical.
- **Search filters by `vote_type='division'` and `result='passed'`** — phase-2 UI work; the data is now there.

## Convention status (per CLAUDE.md)

```
- Bills layer:        federal, NS, ON, BC, QC, AB, NB, NL, MB, NT, NU live
- Hansard layer:      federal, NS, ON, BC, QC, AB, NB, NL, MB, NT live
- Speaker resolution: federal (slug), AB, MB, QC, ON, BC, NT live
- Votes layer:        NT (consensus), federal (division) live ← FEDERAL NEW (2026-04-30)
- Committee layer:    not yet
```
