# BC pre-P35 historical-roster + dated-resolver — 2026-04-29

Closes the pre-P35 gap left by the 2026-04-27 BC + QC handoff (LIMS only knows P35+, 1992+). Backfills 1969-1991 MLAs from Wikipedia, ships a date-windowed BC speaker resolver, and lifts pre-1992 Hansard attribution from a 8-50% floor to a 59-90% ceiling.

## Snapshot before / after

```
Parl  Years      Speeches    Before %    After %    Lift
P29   1970-72    11,351      13.9        59.0       +45.1
P30   1972-75    70,938      10.9        66.8       +55.9
P31   1976-79    21,399       8.8        69.1       +60.3
P32   1979-83    51,623      15.3        85.8       +70.5
P33   1983-86    48,264      22.8        89.4       +66.6
P34   1987-91    26,016      49.8        90.4       +40.6
P35-43           513,433     ~93         ~93        ~0    (already at ceiling)
```

**+136,595 pre-P35 speeches newly attributed.** BC chunks 67.6% → 90.4% attributed (+186K). Modern parliaments unchanged (already at the surname-FK ceiling).

## What shipped — files

```
services/scanner/src/legislative/
  bc_former_mlas.py              — Wikipedia per-parliament wikitable parser (NEW)
  bc_hansard.py                  — added resolve_bc_speakers_dated (single-CTE)

services/scanner/src/__main__.py — 2 new Click commands:
  ingest-bc-former-mlas          — parliaments 29-34 (default), --parliaments override
  resolve-bc-speakers-dated      — date-windowed speaker rescue

services/scanner/src/jobs_catalog.py — mirror entries for both
services/api/src/routes/admin.ts     — UI catalog mirror for both
```

No DB migrations.

## The dated resolver — what makes it different

Mirrors `resolve-mb-speakers-dated` / `resolve-qc-speakers-dated` with one structural twist: BC parser stores `speaker_name_raw` ("HON. MR. CURTIS", "Hon. K. Conroy", "M. de Jong") on the speech row directly rather than pre-parsing a `surname` field into `raw->'bc_hansard'`. The CTE derives surname inline:

```sql
lower(unaccent(
  regexp_replace(
    regexp_replace(s.speaker_name_raw, '^.*\s', ''),
    '[^\w''-]+$', ''
  )
))
```

Last whitespace-separated token, trailing punctuation stripped (apostrophe + hyphen preserved for "O'Brien" and "MacDonald-Smith"), lower+unaccent. Compound surnames degrade to last token ("de Jong" → "jong"), matching the existing `SpeakerLookup.by_initial_last` invariant.

Filters:
- `speaker_role IS NULL` — Speaker / Chair / Clerk role rows skipped (those are handled by `resolve-presiding-speakers --province BC`)
- Last-token NOT IN role-vocab `{speaker, chairman, chair, chairperson, clerk, members, house, leader, lieutenant-governor, administrator}` — defensive guard
- `cand_count = 1` — surnames matching multiple politicians whose terms overlap the speech date stay NULL (genuine ambiguity)

Idempotency: `IS DISTINCT FROM` guard on the chunk update + GREATEST confidence floor at 0.85 (never lowers an already-attributed row's confidence). Re-run = 0 updates.

## Wikipedia source — why and how

`leg.bc.ca/members/{N}th-Parliament/{Slug}` URL pattern exists but the pages are JS-rendered with no static data — would need Playwright. Elections BC publishes only PDFs for 1871-1986 (the obvious URL 404s; would need site-search to find the canonical filename). Wikipedia has clean, complete `wikitable sortable` per-parliament articles for every BC parliament since 1871. Used the MediaWiki API:

```
https://en.wikipedia.org/w/api.php?action=parse&page={N}{ord}_Parliament_of_British_Columbia
  &prop=wikitext&section={members_section_idx}
```

Members section was always index 1 across the six target parliaments. Default delay 1.5s between API calls (single 429 hit at 0.5s in tight smoke-test loop).

### Wikitext parsing — load-bearing details

Each member row is delimited by a `{{Canadian party colour|BC|<party>|row}}` template (BC's tables consistently use this rather than `|-` row separators). Splitting on the template gives chunks that alternate `[pre, party_token1, body1, party_token2, body2, ...]`.

**Rowspan handling is required.** BC pre-1991 used multi-member ridings (Vancouver-Burrard, Vancouver Centre, Vancouver South, Vancouver-Point Grey, Victoria) where 2 MLAs share a constituency. The Wikipedia tables encode this as `rowspan=N` on district/party cells:

- Same-party multi-member: 3 cells in row 2 (name + first-elected + terms; district + party rowspan'd)
- Different-party multi-member: 4 cells in row 2 (name + party + first-elected + terms)
- Party-switcher (single MLA, 2 parties mid-term): 1 cell in row 2 (just the new party)

Initial parser used a "skip if cells < 5" rule and **lost 9 valid members in P30 alone**. Refactored to per-position carryover tracking: `carryover[pos] = (value, rows_remaining)`, applied before parsing this row, decremented after. This recovers all rowspan'd cells and correctly attributes party-switchers (first-listed party wins; second insert hits the existence-check skip).

### Politician identifier strategy

Pre-P35 MLAs aren't in LIMS → no `lims_member_id`. Used the existing `politicians.source_id` UNIQUE column with format `wikipedia:bc-mla:{wikipedia_slug}` (e.g., `wikipedia:bc-mla:Bob_Skelly`). Mirrors AB's `assembly.ab.ca:former-mlas:ab_assembly_mid={mid}`, MB's `manitoba-assembly:slug:{slug}`, QC's `assnat.qc.ca:former-mnas:qc_assnat_id={id}` precedents.

Name-merge layer: before insert, normalize-and-match `first last` against existing BC politicians. 48 of 186 unique members merged onto LIMS-keyed P35+ rows (MLAs whose careers spanned the 1991/1992 boundary). The remaining 138 went in fresh (160 inserted total — discrepancy is within-run dedupe).

## The ledger

```sql
-- BC politicians: 381 → 541 (+160), 160 wikipedia-keyed pre-P35 rows
SELECT count(*) AS total_bc_pols,
       count(*) FILTER (WHERE source_id LIKE 'wikipedia:bc-mla:%') AS wikipedia_keyed
  FROM politicians WHERE province_territory='BC' AND level='provincial';
-- → 541, 160

-- BC politician_terms: 853 → 1212 (+359 across 6 wikipedia-keyed sources)
SELECT source, count(*)
  FROM politician_terms WHERE province_territory='BC' AND level='provincial'
 GROUP BY 1 ORDER BY 1;
-- wikipedia:bc-29th-parliament  54
-- wikipedia:bc-30th-parliament  56
-- wikipedia:bc-31st-parliament  57
-- wikipedia:bc-32nd-parliament  58
-- wikipedia:bc-33rd-parliament  59
-- wikipedia:bc-34th-parliament  75 (P34 had unusual by-election churn)

-- Pre-P35 speech attribution
SELECT ls.parliament_number, count(*) AS speeches,
       round(100.0*count(*) FILTER (WHERE s.politician_id IS NOT NULL)/count(*),1) AS pct
  FROM speeches s JOIN legislative_sessions ls ON ls.id=s.session_id
 WHERE s.source_system='hansard-bc' AND ls.parliament_number BETWEEN 29 AND 34
 GROUP BY 1 ORDER BY 1;
```

## Two-step modern-era bonus

Before pre-P35 work, running `resolve-bc-speakers-dated` against the *existing* modern roster lifted P35-P42 by ~6,000 speeches. Surnames where two MLAs across decades collided in the in-Python `by_initial_last` lookup (e.g. Moira Stilwell P39 vs. Michelle Stilwell P41 — both "M. Stilwell") got cleanly disambiguated by the date-window filter. Largest bonus on P41 (89.1% → 95.3%, +6.2). The dated resolver is now the recommended successor to the in-Python `resolve-bc-speakers` for ongoing daily attribution lifts.

## Pre-flight gotchas surfaced during the run

1. **Wikipedia ordinals**: 31st, 32nd, 33rd are irregular suffixes — `f"{n}th"` works for 29-30 and 34+ but breaks for 31/32/33. Wrote `_ordinal(n)` helper that handles the irregular tens (11-19 always `-th`) and the 1/2/3 suffixes for everything else.

2. **MediaWiki `prop=sections` is deprecated** — emits a warning. Continues to work; kept for now since the `prop=tocdata` migration would change response shape. Switch when the deprecation hits an end-of-life date.

3. **Multi-member-riding rowspan** caught the parser. P30 lost 9 members on first parse; P34 would have lost 10. The carryover-tracking refactor is the load-bearing fix and applies to every BC parliament with multi-seat ridings (essentially every pre-1991 article).

4. **Party-switchers are recorded once per parliament**: Frank Calder served P30 first as NDP, then crossed to Social Credit. The wikitable encodes both via rowspan. Our `existence-check on (politician_id, source)` for `politician_terms` skips the second insert; first-listed party wins. Acceptable — the dated resolver doesn't care about party. A future floor-crossing tracker could split if needed.

5. **Surname extraction inline in SQL vs pre-stash in raw**: chose inline because backfilling 577K JSONB rows would have meant a separate migration step. Tradeoff: ~10-12 minute resolver run on first pass (sequential scan over 577K speeches with derived `lower(unaccent(...))` per row blocks index use). On idempotent re-runs the candidate set shrinks to ~4K still-ambiguous and runs in seconds.

## Out of scope — explicitly deferred

- **Pre-P29 BC roster (1871-1969)**: Wikipedia has articles back to the 1st Parliament. No payoff because we have zero BC Hansard ingested for parliaments before P29 (LIMS HDMS doesn't host pre-1970 transcripts). Building the roster now would be unused.
- **First-initial disambiguation** to crack the 4,115 still-ambiguous floor. Would lift maybe 2-3K more rows. Need a "K. Conroy" → first_name LIKE 'K%' fallback when surname-only is ambiguous. Reasonable next session.
- **Riding-hint disambiguation**: speeches don't carry constituency, but bills do. Could cross-reference contemporaneous bills speeches for further surname-collision rescue. Probably <1K rows.
- **Floor-crossing per-row party tracking**: today we record one term per (politician, parliament) with first-listed party. A separate `politician_party_changes` table could record crossings if and when the data product needs it.
- **Pre-P35 BC bill-sponsor resolution**: BC bills layer is LIMS-keyed and only goes back to P35. Pre-P35 bills aren't ingested.

## Addendum — presiding-officer Speaker cleanup (same session)

After the dated-resolver run, ~50K speeches still carried `speaker_role IS NOT NULL`. Of those, ~20,348 were tagged `'Speaker'` or `'The Speaker'` and unresolved — pre-P38 Speaker rows that the existing presiding-officer roster (which only covered P38+) couldn't reach.

Extended `SPEAKER_ROSTER["BC"]` in `services/scanner/src/legislative/presiding_officer_resolver.py` from 5 entries (P38-current) to **18 entries (P29-current)**, covering 1969-2026. Source: Wikipedia "Speaker of the Legislative Assembly of British Columbia" — year-precision dates only, but BC sittings cluster Spring+Fall so the resulting attribution noise on within-parliament transitions (Reynolds → Rogers in P34, Sawicki → Barnes in P35, Lovick → Brewin → Hartley in P36) is bounded.

Names matched against politicians.name strings produced by ingest-bc-former-mlas — every Speaker since 1969 is already in `politicians` from the Wikipedia roster ingest. No `_insert_minimal_politician` stubs needed. One first-name fallback hit (`Gretchen` → `Gretchen Mann Brewin`) — surname-only fallback when no first-name exact match in the province; logged for review, behaved correctly.

### Resolver result

```
resolve-presiding-speakers (BC): roster=18 terms=18
  scanned=20348 resolved=20348 no_term_match=0 chunks_updated=24590
```

**Every Speaker-tagged row resolved.** Re-run idempotent (scanned=0). The +20,348 rows lift on top of the pre-P35 dated-resolver work brought BC's overall attribution from ~67% (start of session) to ~93%.

### Final BC resolution (post-presiding cleanup)

```
Parl  Years      Speeches    %
P29   1970-72    11,351      85.3
P30   1972-75    70,938      75.1
P31   1976-79    21,399      77.6
P32   1979-83    51,623      91.9
P33   1983-86    48,264      93.7
P34   1987-91    26,016      93.1
P35   1992-96    83,187      99.9
P36   1996-2001  34,023      99.8
P37   2001-2005  31,664      99.9   ← +11.6 just from Speaker roster
P38-43           227,821     ~93
```

### Still-null speaker_role rows after cleanup (out of scope)

```
Chairman                              16,421   ← legacy "MR. CHAIRMAN", rotating Committee-of-the-Whole chair
The Chair                              7,817   ← modern Committee chair, rotating
Deputy Speaker                         5,038   ← rotates
Lieutenant-Governor + Administrator       70   ← throne speeches, ceremonial
```

Resolving these requires per-sitting committee-membership tables — a different workstream. They're recorded as role-only attributions ("the person presiding at this moment was the Chair") rather than misattributed to individual MLAs. Acceptable residual.

## Convention #1 status (per CLAUDE.md)

```
- Federal: openparliament_slug
- Nova Scotia: nslegislature_slug
- Ontario: ola_slug + ola_member_id (int)
- BC: lims_member_id (int)                  ← P35+ only; pre-P35 via politicians.source_id
- Quebec: qc_assnat_id (int)
- Alberta: ab_assembly_mid (text)
- Manitoba: mb_assembly_slug
```

No CLAUDE.md change needed. The pre-P35 BC roster uses the generic `source_id` UNIQUE column (already documented as the universal politicians-key fallback for jurisdictions without a per-jurisdiction integer ID).
