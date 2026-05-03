# Handoff — provincial historical bills + federal re-link cycle

Cycle: **2026-04-30 → 2026-05-03**. Closes the provincial-historical-bills workstream by propagating the `--all-sessions` walker pattern across federal, ON, MB, and QC. Same cycle ships `bills_status` auto-derivation, a federal vote→bill re-link that lifts linkage from 10.2% to its natural 54.7% ceiling, and `introduced_date` extraction for ON (P42-P44, 100%) and QC (RSS window, 35%).

## What landed

| Commit | Date | Subject |
|---|---|---|
| `bdc791f` | 2026-04-30 | coverage auto-derive bills_status + votes/NT cli commands |
| `3a90893` | 2026-05-01 | federal vote→bill re-link + ON/QC bills introduced_date |
| `8d39fb7` | 2026-05-01 | ontario bills --all-sessions historical backfill |
| `11be12d` | 2026-05-02 | mb + qc bills --all-sessions historical backfill |

## Coverage state at end of cycle

| Jurisdiction | Bills | Sessions | Hansard | Votes | Bills | All three live? |
|---|---:|---:|---|---|---|---|
| federal | 5,542 | 19 | live | live | live | ✅ |
| AB | 11,136 | 136 | live | live | live | ✅ |
| BC | 2,277 | 44 | live | live | live | ✅ |
| NS | 3,522 | 24 | live | live | live | ✅ |
| ON | 3,412 | 20 | live | live | live | ✅ |
| QC | 1,192 | 8 | live | live | live | ✅ (new this cycle) |
| MB | 1,971 | 31 | live | partial | live | (votes partial) |
| NB | 1,248 | 20 | partial | none | live | |
| NL | 1,195 | 24 | partial | partial | live | |
| NT | 20 | 1 | partial | partial | partial | |
| NU | 4 | 1 | none | none | partial | |
| PE | 0 | — | none | none | blocked | |
| SK | 0 | — | none | none | none | |
| YT | 0 | — | blocked | blocked | blocked | |

**6 of 14 jurisdictions now have all three legislative-data columns at `live`** (federal + AB + BC + NS + ON + QC).

## Per-province detail

### Federal — 412 → 5,542 bills

`ingest-federal-bills --all-sessions` walks every federal session in `legislative_sessions` (P37-S1 through P44-S1). openparliament.ca's coverage floor is 37-1 (2001) — pre-P37 sessions exist in `legislative_sessions` (from Hansard ingest history) but openparliament returns empty bill lists for them. ~5 hours of polite scraping at 0.5s delay per detail fetch.

Sponsor FK: 4,794/5,542 (86.5%) via `openparliament_slug` exact match. The 13.5% gap is mostly Senate bills with collective sponsors plus a small number of bills where openparliament didn't carry a `politician_url`.

### Ontario — 111 → 3,412 bills

`discover-on-bills --all-sessions` enumerates ola.org's session-index pages for every ON session. ola.org's coverage floor is P36-S1 (1995); P32-P35 sessions exist in `legislative_sessions` but ola.org's modern CMS doesn't host those archives.

Phases: discover (32 sessions, ~10 sec) → fetch (3,301 stubs × 2 HTML pages × 1.5s polite delay = ~6 hours) → parse (uses cached HTML, ~30 sec).

`introduced_date`: 786/786 = 100% for P42-P44; 0/2,626 for P41 and earlier (older /status sub-page markup uses different HTML structure than P42+). Documented as a separate follow-up.

### Manitoba — 81 → 1,971 bills

`ingest-mb-bills --all-sessions` walks every MB session in `legislative_sessions` calling the existing per-session ingest function. gov.mb.ca's `INDEX_URL = web2.gov.mb.ca/bills/{P}-{S}/index.php` template resolves at every session unchanged. ~2 minutes total runtime (one HTTP GET per session, no per-bill fetches).

Sponsor FK: 594/1,971 (30%) via `mb_assembly_slug` exact match. Lower than expected because the historical MB MLA roster doesn't reach back through all 31 sessions. Tightening attribution is a separate roster workstream — bills with NULL `politician_id` still land usefully, the resolver can re-run later when the roster expands.

### Quebec — 497 → 1,192 bills

The donneesquebec CSV pipeline is **deliberately current+previous only** (~613 rows by upstream design). To reach pre-P42 sessions, a new function `discover_qc_bills_html` targets assnat.qc.ca's per-session index page directly:

```
https://www.assnat.qc.ca/en/travaux-parlementaires/projets-loi/projets-loi-{P}-{S}.html
```

Each session HTML page lists every bill as a link to its detail page. The new pass extracts bill numbers via the existing `_BILL_URL_FROM_RSS_RE` regex, upserts minimal stubs (placeholder titles, no sponsor). The existing `fetch-qc-bill-sponsors` command picks up the new stubs on subsequent runs to enrich titles + sponsors.

Critically: `ON CONFLICT (source_id) DO UPDATE` only touches `source_url + last_fetched_at`. The existing 497 CSV-derived rows' rich data (titles, types, status, stage events) is preserved — the HTML pass complements rather than overwriting.

Per-session breakdown (every QC session has bills, no zero rows):
```
P43-S2=48,  P43-S1=195, P42-S2=72,  P42-S1=182,
P41-S1=296, P40-S1=115, P39-S2=108, P39-S1=176
```

## Federal vote→bill re-link (no API calls)

The federal_votes extractor's runtime `bill_index = {bills.raw->>'url' → bills.id}` only matched against the 412 bills that existed when extraction first ran. After the federal historical bills backfill, the `votes.raw->'openparliament_vote'->>'bill_url'` field on each vote row pointed to bills now present in the table.

`relink-federal-votes` is a pure-SQL UPDATE pass — no openparliament.ca API calls — that joins `votes` against `bills` via the `raw` payload. **1,993 votes newly linked, 0 unmatched.** Federal vote→bill linkage went from 10.2% (458/4,481) to **54.7%** (2,451/4,481) — the natural ceiling, since the remaining 2,030 votes have NULL `bill_url` (non-bill divisions: supply / procedural / time allocation).

Avoided re-fetching 1.45M ballot rows that the alternative `extract-federal-votes --all-sessions` re-run would have required.

## `bills_status` auto-derivation

`coverage_stats.py` now derives all three legislative status columns from row counts. Threshold rationale (empirical, based on observed jurisdiction densities):
- `≥ 500` bills → 'live'
- `1-499` → 'partial'
- `0` → 'none'
- `'blocked'` (editorial) is preserved across re-derives.

Same shape as the previously-shipped `_votes_status` (≥100 / 1-99 / 0) and `_hansard_status` (≥50K / 1K-49K / 0).

The auto-derivation honestly downgraded five jurisdictions (MB / NT / NU / ON / QC at the time) from over-stated `'live'` to `'partial'` — those flipped back to `'live'` once the historical backfills landed.

## `introduced_date` extraction

| Province | State | Source |
|---|---|---|
| ON (P42-P44) | 786/786 = 100% | `/status` sub-page `first_reading` events, derived during parse |
| ON (P41 and earlier) | 0/2,626 | older /status markup uses different HTML structure — separate work |
| QC | 173/1,192 = 14.5% | RSS-window roll-up via new `derive_qc_introduced_dates` SQL helper |
| federal | not extracted | openparliament doesn't expose introduction date on the list endpoint |
| NS | not addressable | Socrata only ships `date_status_changed` (current stage) |
| MB | not addressable | dates live in separate `billstatus.pdf` (different module) |

The QC RSS window only carries recent events. Bills sanctioned before that window have no 'introduced' event in `bill_events`. Lifting QC to ~100% requires extracting "Sitting held on {date}" from `<h3>Introduction</h3>` on each bill detail page during `fetch-qc-bill-sponsors`. ~10-20 LOC + per-bill HTTP cost (already paid for sponsor extraction).

## What's now possible

1. **Six provinces with full bills × votes × hansard depth** support compare-A-vs-B queries on legislative behavior over multi-decade timespans.
2. **Federal vote→bill linkage at 54.7%** unblocks "show me how each MP voted on Bill C-N" queries for the 2,451 federal divisions that are bill-tied. The remaining 2,030 are correctly flagged NULL — they aren't bill votes.
3. **`/coverage` page tells the truth across three columns** automatically. No more stale editorial flags drifting from row counts.

## What's next (recommended sequencing)

Three obvious follow-ups, in approximate effort order:

1. **QC sponsor backfill on the new 695 HTML-discovered bills** — run `fetch-qc-bill-sponsors`, ~25 min at 2s polite pace.
2. **QC `introduced_date` 14.5% → ~100%** — patch `fetch-qc-bill-sponsors` with `<h3>Introduction</h3>` date extraction. ~10-20 LOC; pairs naturally with the sponsor backfill above.
3. **ON pre-P42 `introduced_date`** — research older /status markup, patch parser. ~half-day.

Larger-scope follow-ups already documented:
- **Federal `bill_events` from LEGISinfo XML** (5,542 federal bills × 0 events; structurally important; different feed shape from openparliament).
- **Committee transcripts (federal first)** — phase 4 of `semantic-layer.md` is now unblocked. Per-province research-handoff gated.
- **MB sponsor-FK lift via expanded MLA roster** — current 30% rate reflects roster floor, not parser bug.

## Files touched this cycle

- `services/scanner/src/legislative/coverage_stats.py` — `_bills_status()` + extension to UPDATE/SELECT
- `services/scanner/src/legislative/federal_votes.py` — `relink_federal_votes()` SQL UPDATE pass + `RelinkStats` dataclass
- `services/scanner/src/legislative/on_bills.py` — `discover_ola_bills_all_sessions()` walker + `_persist_introduced_date()` parser-side helper
- `services/scanner/src/legislative/qc_bills.py` — `derive_qc_introduced_dates()` + `discover_qc_bills_html()` + `discover_qc_bills_html_all_sessions()`
- `services/scanner/src/legislative/mb_bills.py` — `ingest_all_sessions()` walker
- `services/scanner/src/__main__.py` — `--all-sessions` flags on ingest-mb-bills + discover-on-bills, new `discover-qc-bills-html` and `relink-federal-votes` commands, extended print formatters

No migrations, no schema changes, no daily-schedule updates this cycle. All changes are forward-only and idempotent on existing source_id keys.
