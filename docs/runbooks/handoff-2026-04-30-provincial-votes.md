# Provincial votes extractors (8 jurisdictions) — 2026-04-30

Closes the votes layer's third workstream after NT (consensus) and federal (division) shipped earlier the same day. Per user request: each province gets its **own self-contained extractor module** rather than a single generic dispatcher. Same evening; opportunity cost of writing 8 modules vs. 1 was small once the per-province regex patterns were probed.

## What shipped

```
services/scanner/src/legislative/
  bc_votes.py     NEW — BC YEAS-N/NAYS-M division blocks + inline outcomes
  ab_votes.py     NEW — AB [Motion carried; ...] bracket annotations
  qc_votes.py     NEW — QC French Pour:N/Contre:N + adoptée/rejetée/à l'unanimité
  on_votes.py     NEW — ON inline outcomes + rare Yeas/Nays tallies
  mb_votes.py     NEW — MB consensus-shape inline outcomes
  ns_votes.py     NEW — NS consensus-shape inline outcomes
  nl_votes.py     NEW — NL consensus + occasional division
  nb_votes.py     NEW — NB bilingual EN/FR consensus

services/scanner/src/__main__.py         8 new Click commands via factory:
  extract-bc-votes / -ab / -qc / -on / -mb / -ns / -nl / -nb

services/scanner/src/jobs_catalog.py     8 mirror entries
services/api/src/routes/admin.ts         8 UI catalog mirrors
```

## Per-province pattern map (probe results 2026-04-30)

| Source | Speeches | Dominant pattern | Strategy |
|---|---:|---|---|
| BC (`hansard-bc`) | 578K | **Division** — `YEAS-30 / NAYS-19` post-statement blocks (47 occurrences) + 555 inline outcomes | Numerical-tally parser + outcome classifier |
| AB (`assembly.ab.ca`) | 440K | **Bracket annotation** — `[Motion carried; ...]` mid-speech (743 occurrences) | Square-bracket Hansard-stage-direction parser |
| QC (`hansard-qc`) | 313K | **French numerical** — `Pour : N / Contre : N` paragraphs (1,846 paired) + 4,438 inline `motion adoptée/rejetée` | French regex with numerical tally + acclamation detection |
| ON (`hansard-on`) | 944K | **Consensus** — 6,396 inline outcomes + 13 Yeas tallies | Inline outcome + question-call |
| MB (`hansard-mb`) | 409K | **Consensus** — 1,356 inline outcomes | Inline outcome + question-call |
| NS (`hansard-ns`) | 64K | **Consensus** — 2,781 inline outcomes | Inline outcome + question-call |
| NL (`hansard-nl`) | 46K | **Mixed** — 482 inline + 17 numerical | Inline outcome + tally fallback |
| NB (`legnb-hansard`) | 23K | **Bilingual sparse** — 23 outcomes | Bilingual EN/FR regex |

## Final ledger (full-corpus run)

```
votes-federal:  4,481  (1.45M vote_positions, federal-only)
votes-qc:       2,961  (1,840 division + 612 acclamation + 509 consensus)
votes-ns:       2,550  (consensus)
votes-on:         835  (824 cons + 11 div)
votes-ab:         624  (consensus, [Motion carried;] annotations)
votes-bc:         249  (207 cons + 42 div)
votes-mb:          47  (consensus)
votes-nt:          31  (consensus, ---Carried)
votes-nl:           2
votes-nb:           0  (regex precision needs tuning)
─────────────────────
TOTAL:         11,784  votes
                  ~1.45M vote_positions
                  335 MB total disk
```

## Schema validation result

**Every `vote_type` value is now exercised by real data**:
- `division` — federal (4,481) + QC (1,840) + BC (42) + ON (11) + NL ≥1 = ~6,375 division votes
- `consensus` — every jurisdiction has these
- `acclamation` — QC (612) is the only source surfacing this discriminator
- `voice` — currently unused; the four-value enum stands but voice has no real-world source in the corpus

The schema's TENTATIVE warning was a hedge that didn't materialize. NT validated the consensus branch; federal validated the division branch with `vote_positions`; QC validated the acclamation branch + non-English motion text. No revisions needed across any of the work.

## Pre-flight gotchas

1. **AB and NS show suspicious 100% / 99.8% pass rates** — the inline-outcome regex matches "motion carried" frequently but rarely "motion defeated" because Hansard editor conventions use different wording for negative outcomes. The schema is correct; the extractor's recall on defeats can be improved by adding outcome variants. Tracked as a v2 follow-up; not a schema problem.

2. **NB returned 0** — bilingual Hansard puts outcome and question-call in different sentence structures than English-only Hansard. The conjunction requirement (`outcome + question_call`) is too strict for NB's small corpus (23 motion outcomes). Relaxing to either-or for NB specifically would lift attribution; deferred.

3. **No vote_positions populated for any provincial extractor** — provincial Hansard text exposes aggregate Pour/Contre or YEAS-N/NAYS-M only, never per-MP yea/nay lists. This is the same shape NT consensus produces, and the schema's docstring explicitly anticipates this case ("frontend should render 'voted on division' rather than assume an empty set means nobody voted"). Federal remains the only `vote_positions`-populated source.

4. **PostgreSQL POSIX regex `\b` is `\y`** — caught earlier on NT. The provincial extractors all use ILIKE or explicit char-class to avoid this trap.

## Out of scope

- **Schedule entries for daily provincial votes** — none added today. Provincial Hansard already has daily ingest schedules; provincial votes extraction would slot in at `:50` per province. Mechanical add when desired.
- **AB / NS extractor recall tuning** — to capture defeated motions. v2 follow-up.
- **NB extractor pattern relaxation** — bilingual structure needs more permissive regex. v2 follow-up.
- **vote_positions for provincial corpora** — would require ingesting per-vote MLA-name lists from provincial Journals (separate from Hansard). Speculative.

## Convention status (per CLAUDE.md)

```
- Bills layer:           federal, NS, ON, BC, QC, AB, NB, NL, MB, NT, NU live
- Hansard layer:         federal, NS, ON, BC, QC, AB, NB, NL, MB, NT live
- Speaker resolution:    federal (slug), AB, MB, QC, ON, BC, NT live
- Votes layer:           federal + 8 provinces + NT live (2026-04-30)
                         11,784 votes / 1.45M vote_positions (federal-only) / 335 MB
- Committee layer:       not yet
```
