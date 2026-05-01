# Migration 0018 votes + NT votes extractor — 2026-04-30

Closes the longest-parked migration in the project: `0018_votes.sql` finally lands. NT consensus-government data validates the `vote_type` discriminator without forcing schema revisions. Federal openparliament.ca vote_urls extraction (structured JSON) and provincial regex extension (BC/AB/MB/QC/...) are unblocked.

## What shipped

```
db/migrations/
  0018_votes.sql                         APPLIED (was unapplied since project start)

services/scanner/src/legislative/
  nt_votes.py                            NEW — Hansard-text votes extractor

services/scanner/src/__main__.py         1 new Click command:
  extract-nt-votes

services/scanner/src/jobs_catalog.py     Mirror entry
services/api/src/routes/admin.ts         UI catalog mirror

scripts/seed-daily-ingest-schedules.sql  Added 21:50 UTC NT votes entry
                                         (chained after presiding-speaker resolver)

docs/research/northwest-territories.md   Status snapshot — votes "live"
docs/plans/semantic-layer.md             Mark 0018 applied
CLAUDE.md                                Updated votes line ("not yet in DB" → applied)
TODO.md / docs/timeline.md               Re-sync (migration 0018 done; remaining votes work promoted)
```

## Schema validation result

The `0018_votes.sql` schema has carried a TENTATIVE warning since project inception, hedged for the case where consensus-government data forced revisions. **No revisions needed.** NT data fits the existing schema:

| NT vote shape | Schema fit |
|---|---|
| `---Carried` Hansard annotation | `vote_type='consensus'`, `result='passed'`, ayes/nays NULL |
| `---Defeated` (zero in NT corpus) | `vote_type='consensus'`, `result='defeated'` |
| Inline "Motion is carried" | Same as marker, fallback path |
| Per-member positions | NT doesn't publish; `vote_positions` stays empty (schema permits) |
| Bill linkage | Opportunistic via `Bill N` text mention; `bill_id` NULL when none |

The schema's docstring already anticipated this exact shape: *"For 'voice' / 'acclamation' / some 'consensus' votes this table may be empty. The frontend should render 'voted on division' rather than assume an empty set means nobody voted."*

## NT corpus extraction result

```
extract-nt-votes (full corpus): scanned=655 inserted=31 updated=0 skipped=624 bill_links=0
by_type:   {'consensus': 31}
by_result: {'passed': 31}
```

31 votes across 13 years of NT Hansard (2013–2026). Distribution by year: 2016=8, 2017=2, 2018=4, 2019=5, 2020=2, 2021=3, 2022=1, 2024=4, 2025=1, 2026=1.

This is sparse for a reason: NT consensus government produces few formal recorded votes. Most chamber time is deliberation, members' statements, oral questions, and committee reports. Formal motion votes (the kind that get a `---Carried` annotation) are reserved for committee report adoption, bill readings, and procedural questions of order. Compare to a future federal extraction, which will show partisan-division shape with numerical tallies and populated `vote_positions`.

Idempotent on re-run: scanned=655 inserted=0 updated=31. The unique constraint `(source_system='votes-nt', source_url)` keyed on `{canonical_sitting_url}#vote-{sequence}` catches duplicate runs cleanly.

## Detection logic — what's load-bearing

The extractor uses a **broad-SQL pre-filter + precise-Python classifier** split:

- **SQL pre-filter** (`speeches.text ~ '(?m)^---'` OR inline-outcome+question-call): catches any speech with potential vote-outcome signal. Hits 655 rows out of 13,966.
- **Python classifier** (`_classify` in `nt_votes.py`): rejects 95% of pre-filter hits — `---Unanimous consent granted` (489), `---Applause` (74), other Hansard convention markers that aren't votes. Only `Carried | Defeated | Withdrawn | Negatived | Tied` are recognized as outcome words.

Inverting the split (precise SQL + loose Python) would push regex into the database where it's harder to maintain and test. The current split keeps the precision in app code where it belongs.

## Pre-flight gotchas surfaced

1. **`unanimous consent` is 756× more common than `motion carried`** — but it's a procedural waiver (member asking to extend statement, change agenda), NOT a vote outcome. Initial classifier instinct was to model these as "acclamation" votes; correctly rejected after probe revealed the procedural-not-vote use. The `---Unanimous consent granted` annotations are filtered at the Python layer.

2. **The marker is the load-bearing signal, not the prose** — Hansard convention `---Carried` annotations appear on their own line after the Speaker's procedural body. Speakers say "Question has been called. All those in favour? All those opposed? Motion carried." regardless of the actual vote shape; the `---Carried` annotation distinguishes a real vote from a phrase mentioning "carried" in passing.

3. **`motion_text` captures the procedural call, not the substance** — the actual motion being voted on was moved by a Member in a preceding speech, which the extractor doesn't easily reach from the Speaker's announcement row. We use the Speaker text itself as motion_text; the substantive subject lives in `raw->'nt_hansard'->>'topic'` from the parent sitting context. Future enhancement: link to the preceding "I move that..." speech via sequence-1 lookup.

4. **PostgreSQL POSIX regex doesn't support `\b`** — uses `\y` for word boundary. Caught during the corpus probe when `text ~ '\bCarried\b'` returned 0 despite obvious matches. Switched to ILIKE / explicit char-class.

5. **`level` CHECK constraint forced 'provincial' for territories** — the `votes` schema's `level IN ('federal','provincial','municipal')` doesn't include 'territorial', so we use `level='provincial'` matching the existing NT bills/Hansard convention. The `province_territory='NT'` discriminator already conveys territorial status.

## Out of scope (this iteration)

- **Federal openparliament.ca vote_urls extraction** — structured JSON, easier than NT regex. Separate workstream now unblocked.
- **Provincial regex extension** (BC/AB/MB/QC/ON/NS/NB/NL) — defer until federal extraction validates the cross-jurisdiction extractor shape.
- **Search filters by `vote_type` / `result`** — phase-2 UI work.
- **Vote-comparison UI** ("Compare A vs B on issue X") — Next 4 timeline item; depends on this layer existing.
- **Speech-to-motion linkage** — current extractor's `motion_text` is the Speaker's procedural call. Linking back to the preceding "I move that..." speech is a refinement; defer.

## Convention status (per CLAUDE.md)

```
- Bills layer:        federal, NS, ON, BC, QC, AB, NB, NL, MB, NT, NU live
- Hansard layer:      federal, NS, ON, BC, QC, AB, NB, NL, MB, NT live
- Speaker resolution: federal, AB, MB, QC, ON, BC, NT live
- Votes layer:        NT live (2026-04-30) ← NEW
- Committee layer:    not yet
```

## Verification

1. **Migration applied**: `\d votes` and `\d vote_positions` show expected schema.
2. **NT extraction**: 31 votes inserted, all `vote_type='consensus'`, all `result='passed'`. Empty `vote_positions` (NT consensus default).
3. **Idempotency**: re-run produced 0 inserts, 31 updates.
4. **Year distribution**: 31 votes spread across 2016–2026 (sparse but real).
5. **Schedule**: 21:50 UTC NT votes entry chains after presiding-speaker resolver. First fire 2026-04-30 21:50.
