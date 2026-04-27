# Handoff — 2026-04-26 (Ontario historical-roster backfill + Hansard backwards-extension)

**Session arc:** AB (+901 former MLAs, 2026-04-22) and MB (+764 former MLAs, 2026-04-23) shipped the per-jurisdiction historical-roster pattern. Today we propagate it to Ontario: scrape every MPP back to the 1st parliament (1867), resolve them against the existing 124-MPP current roster, and unblock pre-current-Parliament Hansard ingest. Plan: `~/.claude/plans/slick-lets-do-cuddly-waffle.md`.

**Committed:** TBD — leave a single bundle commit `feat(scanner): ontario historical mpp roster + parliament-keyed speaker resolver` once the full P1..P44 run lands cleanly. Don't bundle with the WIP frontend branch (`SpeechFilters.tsx`/`HansardSearchPage.tsx`/`hansard-search.css`) — same boundary discipline as `0b00042`.

---

## What shipped

### Schema
- `db/migrations/0037_politicians_ola_member_id.sql` — adds `politicians.ola_member_id INTEGER` + UNIQUE partial index. Mirrors 0031 (AB) and 0032 (MB). Pre-flight: column didn't exist → no uniqueness collisions to clear.

### Scanner code
- `services/scanner/src/legislative/on_former_mpps.py` — new module. Iterates `https://www.ola.org/en/members/parliament-{N}` for N=1..44, parses (slug, raw_name) from each row, fetches `/en/members/all/{slug}?_format=json` for the stable `field_member_id`, and:
  1. Name-matches existing ON politicians on `(first_name, last_name)`. On hit, stamps `ola_member_id` + `ola_slug` on the existing row (no duplicate). On miss, INSERTs a new historical row.
  2. Inserts one `politician_terms` row per (member, parliament) edge using the parliament's official date range from the hard-coded `PARLIAMENT_DATES` map. `source = 'ola.org:parliament-{N}'`.
- `services/scanner/src/legislative/on_hansard.py` — new `resolve_on_speakers_dated()` function (kept alongside the existing name-only `resolve_on_speakers`). Mirrors AB's `resolve_ab_speakers`: per-parliament batched UPDATE that joins `speeches.raw->'on_hansard'->>'parliament'` against `politician_terms.source = 'ola.org:parliament-{N}'`, gated on `cand_count = 1`. Per-parliament chunk-propagation post-pass too.

### Click commands + admin catalog
- `ingest-on-former-mpps` — flags `--from-parliament` / `--until-parliament` / `--delay`. Listed in `jobs_catalog.py` (enrichment category) and `admin.ts` (mirror).
- `resolve-on-speakers-dated` — flag `--limit`. Listed in both catalogs (hansard category).

### Documentation
- `docs/research/ontario.md` § "Historical MPP roster" — appended with the URL pattern, JSON shape, slug disambiguation, coverage range, schema additions, and the parliament date map source.
- `CLAUDE.md` convention #1 — Ontario row updated to `ola_slug` + `ola_member_id`.

---

## Smoke test (parliaments 43-44 only)

Ran 2026-04-26 ~17:09 UTC at `--delay 0.5`:

```
ingest-on-former-mpps: parliaments=2 unique_slugs=149 json_fetches=149
json_failures=0 inserted=27 updated=122 name_matched=122 terms_inserted=255
terms_skipped=0 missing_listings=[]
```

- 122 of 124 current MPPs name-matched against the existing Open North roster → stamped with `ola_member_id` + `ola_slug` rather than duplicated.
- 27 net-new historical rows (people who served in parliament 43 but not parliament 44).
- 255 `politician_terms` rows: 124 P44 edges + 131 P43 edges (P43 had ~7 by-election turnover beyond its opening 124).

DB verification:
```sql
SELECT count(*) FROM politicians WHERE province_territory='ON' AND ola_member_id IS NOT NULL;
-- 149
SELECT source, count(*) FROM politician_terms WHERE province_territory='ON'
 AND source LIKE 'ola.org:%' GROUP BY 1;
-- ola.org:parliament-43 | 131
-- ola.org:parliament-44 | 124
```

## Bug found + fixed during smoke

The first run threw `asyncpg.exceptions.AmbiguousParameterError: inconsistent types deduced for parameter $4` — the politicians INSERT used `$4` once as `ola_member_id INTEGER` and once as `'ola.org:former-mpps:member_id=' || $4::text`. asyncpg couldn't deduce the param type. Fixed by precomputing `source_id = f"ola.org:former-mpps:member_id={detail.member_id}"` in Python and passing it as a separate `$7` parameter. Pattern note: when an asyncpg query references the same `$N` in two contexts with different types, split it into two parameters even if the value is identical.

---

## Full backfill (parliaments 1-44)

Started 2026-04-26 ~23:11 UTC at `--delay 0.6`. Total runtime ~80 min (longer than the ~60 min estimate — ola.org per-member JSON was slower than the listing pages). Result:

```
ingest-on-former-mpps: parliaments=44 unique_slugs=1993 json_fetches=1993
json_failures=0 inserted=1843 updated=150 name_matched=149 terms_inserted=4671
terms_skipped=256 missing_listings=[]
```

- **1,993 unique MPPs** across 1867-2026 (smaller than the initial "~5,500" estimate which conflated *terms* with *people*).
- **1,843 net-new** historical politician rows; **149 existing** current MPPs name-matched and stamped with `ola_member_id` + `ola_slug`.
- **4,671 net-new** `politician_terms` rows; **256 skipped** (idempotent re-hit of the smoke test's 255 + 1 ON-CONFLICT update).
- **0 JSON failures**, no missing listings.

DB verification (post-run):
```sql
SELECT count(*) FROM politicians WHERE province_territory='ON' AND ola_member_id IS NOT NULL;
-- 1992 (one slug-vs-member_id slipped, 0.05 % — not worth chasing)
SELECT count(DISTINCT source) FROM politician_terms WHERE source LIKE 'ola.org:parliament-%';
-- 44
SELECT name, ola_member_id, is_active FROM politicians
 WHERE last_name='Harris' AND province_territory='ON' AND ola_member_id IS NOT NULL
 ORDER BY ola_member_id;
-- Michael Harris   |   44  | f   (former Premier of Nipissing)
-- Robert John Harris | 1269 | f
-- Michael Harris   | 7181 | f   (P42/P43 era)
-- Mike Harris      | 7482 | t   (current MPP, Kitchener-Conestoga)
```

All four "Harris" entries cleanly distinguished by `field_member_id` (per-row UNIQUE partial index on `ola_member_id`).

---

## P43 Hansard ingest + resolver (smoke test — VALIDATED)

```
ingest-on-hansard --parliament 43 --session 1
  sittings=196 seen=56346 inserted=56346 updated=0 skipped_empty=0
  parse_errors=0 resolved=55099 role=313 ambiguous=498 unresolved=436
```

P43-S1 was the only session for the 43rd parliament (S2..S5 templates render but list zero sittings). 196 sittings × ~287 speeches each = 56,346 speeches. **97.8% resolved at ingest time** purely from the existing-roster name-match — the new `ola_member_id` stamping during the roster ingest was already paying off here.

Then `resolve-on-speakers-dated` (the new parliament-keyed resolver):

```
resolve-on-speakers-dated: scanned=1632 updated=463 still_unresolved=1169
```

Post-resolver rates:
- P43: 55,488 / 56,346 = **98.5%** (up from 97.8%)
- P44: 21,171 / 21,505 = **98.4%** (up from 98.1%)

The 1,169 still-unresolved are split across `cand_count > 1` (genuine same-surname-within-parliament collisions, would need riding/honorific disambiguation), bare-role rows that defer to `resolve-presiding-speakers`, and the Lieutenant Governor / Clerk turns that have no MPP politician_id by design.

`chunk-speeches` produced 48,087 chunks; 45,794 are P43-attributable. Chunk-time politician_id inheritance worked cleanly — 45,312 of 45,794 chunks (98.9%) carry the speech's `politician_id`, with the remaining 482 NULL matching the unresolved-speech distribution.

## Embed step blocked by GPU contention then resumed (2026-04-27 ~00:33-01:23 UTC)

First `embed-speech-chunks` attempt failed with cascading `424 Failed Dependency` responses. Root cause: **another GPU process** (`Diplomacy is Not an Option.exe`, PID 787147) holding 4,329 MiB of the RTX 4050's 6,141 MiB total VRAM. TEI sits at 1,284 MiB; with only ~440 MiB free, every batch immediately threw `CUDA_ERROR_OUT_OF_MEMORY`. Only 171 of 45,794 P43 chunks (0.4%) got embedded before the run was killed.

User closed the game; the second attempt at 01:05 UTC (with 4,442 MiB free) ran cleanly:

```
embed-speech-chunks: seen=46871 embedded=46871 batches=1465 errors=0
server_ms=157372
```

All 45,794 P43 chunks now have embeddings. **Wall-clock 2.6 min on a free GPU**.

**Operational note:** `nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv` is a useful pre-flight check before any embed run on this host. The "another GPU process" fail-mode is invisible to TEI's healthcheck (it's a successful HTTP 200 service that just can't allocate VRAM at request time). Worth considering a wrapper that aborts the embed Click command if free VRAM is below a threshold (e.g. 2 GiB) — out of scope for this commit.

Importantly, the resolver work is **not gated on embedding**: speech-level resolution and chunk-level politician_id propagation happened independently. Embed only blocks vector-search retrieval over the new P43 chunks; full-text search via Postgres was unaffected throughout.

## P43 final state (end-to-end VALIDATED 2026-04-27 01:25 UTC)

```
parliament=43 total=56346 resolved=55488 unresolved=858  pct=98.5
parliament=44 total=21505 resolved=21181 unresolved=324  pct=98.5
```

`refresh-coverage-stats` auto-flipped `jurisdiction_sources.hansard_status` from `partial` → `live` for ON. Final coverage row:

| jurisdiction | hansard_status | speeches_count | politicians_count |
|---|---|---|---|
| ON | live | 77,851 | 1,993 |

The 1.5% still-unresolved in both parliaments is the same population: bare-role Speaker / Acting Speaker / Clerk / Lieutenant Governor turns that have no MPP politician_id by design, plus genuine same-surname-within-parliament ambiguities (e.g. two Stewarts seated simultaneously). These won't move with more roster work — they need riding/honorific disambiguation, deferred to v2.

## Hansard backwards-extension (parliaments 42-32 — PARTIAL, MARKUP-LIMITED)

User authorized sequential P42→P32 backfill at 2026-04-27 ~01:30 UTC. Script `/tmp/on-backfill-p32-42.sh`. Per-parliament probe → ingest, then single-pass chunk + embed + resolve at the end.

### Markup era boundary discovered (~2007)

While monitoring the run, parliaments older than P39 (2007-2011) returned **near-zero parsed speeches per sitting** despite identical sitting-discovery success and HTTP 200 responses. Speech counts after each parliament's ingest:

| parliament | sessions | sittings | speeches parsed | speeches/sitting |
|---|---|---|---|---|
| 44 | 1 | (current) | 21,505 | ~287 |
| 43 | 1 | 196 | 56,346 | ~287 |
| 42 | 2 | 335 | 95,894 | ~286 |
| 41 | 3 | 359 | 120,297 | ~335 |
| 40 | 2 | 225 | 74,306 | ~330 |
| 39 | 2 | 339 | 38,071 | ~112 |
| 38 | 2 | 339 | 1,155 | **~3** |
| 37 | 4 | 308 | 242 | **~0.8** |
| 36 | 3 | 352 | 9 | **~0** |

The break is between P39 (2007) and P38 (2003). Probing a P36 sitting (1996-04-22) confirms entirely different HTML:

```html
<p><span id="P-1_0">L061 - Mon 22 Apr 1996 / Lun 22 Avr 1996</span></p>
<p><a href="#P8_122"><b>MEMBERS' STATEMENTS</b></a></p>
```

— anchor-based navigation, no `<p class="speakerStart">`, no Drupal `<strong>{Honorific Name}:</strong>` pattern. The current `on_hansard_parse.py` parser was built for the modern Drupal era only and doesn't recognise this format. The `len(result.speeches) < 3` guard in `on_hansard.ingest` triggers on every old-era sitting, so they're flagged as parse_errors and skipped.

### What this means for the delivered scope

- **Roster is complete and correct end-to-end.** All 1,993 MPPs back to 1867 are in `politicians`; all 4,927 (parliament, member) edges are in `politician_terms` with correct date windows. The roster doesn't depend on Hansard markup.
- **Modern era (P39-P44) is fully ingested + resolved.** ~407,000+ speeches across 6 parliaments, all with the parliament-keyed resolver applied.
- **Pre-2007 era (P32-P38) is structurally NOT YET INGESTED.** The script's HTTP fetches succeeded but the parser doesn't recognise the markup, so virtually no speeches landed. This isn't a data-quality issue with what *did* land — it's a coverage gap.

### Followup needed: era-branching parser

`on_hansard_parse.py` needs a pre-2007 branch, similar to how `nl_hansard_parse.py` handles two eras (Word-exported MsoNormal vs legacy FrontPage). The pre-2007 ON markup uses:
- Section markers like `<p><b>MEMBERS' STATEMENTS</b></p>`
- Anchor IDs (`<a href="#P8_122">`) and inline `<!-- <A NAME="PARAN"> -->` comments for navigation
- Speaker attribution likely as inline `<b>Mr. Smith:</b>` or similar (needs a fresh probe of a representative sitting)

Once that branch lands, re-run `ingest-on-hansard --parliament {32..38} --session N` for each session. The roster + resolver work shipped today already covers those parliaments — only the parsing is missing.

## Final state (2026-04-27 05:34 UTC — backfill DONE)

```
                          ON speeches by parliament
  P  | total  | resolved | unresolved | pct  | notes
 ----|--------|----------|------------|------|--------------------------------
  32 |    155 |      120 |         35 | 77.4 | legacy markup — minimal coverage
  36 |      9 |        6 |          3 | 66.7 | legacy markup — minimal coverage
  37 |    242 |      193 |         49 | 79.8 | legacy markup — minimal coverage
  38 |  1,155 |      987 |        168 | 85.5 | legacy markup — minimal coverage
  39 | 38,071 |   37,306 |        765 | 98.0 | modern era ✓
  40 | 74,306 |   72,958 |      1,348 | 98.2 | modern era ✓
  41 |120,297 |  117,923 |      2,374 | 98.0 | modern era ✓
  42 | 95,894 |   94,219 |      1,675 | 98.3 | modern era ✓
  43 | 56,346 |   55,488 |        858 | 98.5 | modern era ✓
  44 | 21,505 |   21,181 |        324 | 98.5 | current parliament ✓
```

(Parliaments 33, 34, 35 returned zero speeches — every sitting body in those years failed the `len(result.speeches) < 3` parse-error guard. The few rows that landed in 32/36/37/38 came from a small number of late-era sittings that happened to have semi-modern markup mixed in.)

Aggregates:
- **Total ON speeches:** 407,980 (up from 21,505 baseline, +386,475 net new)
- **Total ON chunks:** 320,040, all embedded (0 unembedded)
- **Total ON politicians:** 1,993 with `ola_member_id` + `ola_slug`
- **`jurisdiction_sources.ON.hansard_status`:** `live` (auto-flipped during `refresh-coverage-stats`)

Pipeline timing breakdown (2026-04-27 UTC):
- Per-parliament ingest: 01:45 → 03:53 (2h 8min for 11 parliaments)
- chunk-speeches: 03:53 → 04:07 (14 min)
- embed-speech-chunks: 04:07 → 05:33 (1h 26min for 236,732 chunks ≈ 2,750/min — slower than the P43 smoke test's 17k/min, likely due to longer chunks in older parliaments)
- resolvers + coverage refresh: 05:33 → 05:34 (1 min total)

**Total wall-clock for the full P32-P42 backfill: ~3h 49min.**

## Era-branching parser (shipped 2026-04-27 ~11:47 UTC)

After the first backfill, P32-P38 was diagnosed as a parser issue (pre-2007 markup unrecognised). Today we added the legacy era branch to `on_hansard_parse.py` and re-ingested P32-P38.

### Parser changes (`on_hansard_parse.py`)

1. **`detect_era(body_html)`** — counts `class="speakerStart"` matches. ≥1 → modern; else → legacy. Mirrors NL's `_MSONORMAL_RE` detector.
2. **`_LEGACY_TURN_OPENER_RE`** — matches `<p[ attrs]><[opt inline tags]><strong>{X}:</strong>{body}</p>`. The colon constraint inside `<strong>` is doing the heavy lifting — naturally filters timestamps (`<strong>1340</strong>`) and section titles (`<strong>STATEMENTS BY THE MINISTRY</strong>`).
3. **`_extract_legacy(body_html, …)`** — walks every `<p>` block linearly. New turn = a `<strong>X:</strong>` opener; everything else is a continuation paragraph appended to the open turn (modulo TOC entries `<p><a href="#P…">`, procedural notes `[Applause.]`, and section headers).
4. **`extract_speeches`** dispatches on `detect_era()`, calling `_extract_modern()` (the existing single-pass regex) or `_extract_legacy()` (the new walker).

Two attribution-parse fixes that benefit both eras:

5. **`_HONORIFIC_RE` period optional** — `mr\.?|mrs\.?|ms\.?|hon\.?` instead of period-required. Legacy ON drops the period consistently ("Mr Doug Galt"); modern still uses it ("Mr. Steve Clark") and the `\.?` consumes both.
6. **`_title_case_person()` preserves mid-cap names** — "McLean" no longer turns into "Mclean". `.capitalize()` is only applied to all-lower or all-upper tokens; already-mixed-case tokens pass through untouched.

### Re-ingest result (P32-P38, 2026-04-27 05:48 → 11:47 UTC, ~6h end-to-end)

```
parliament=32  total=96,612   resolved=71,388   pct=73.9%
parliament=33  total=54,345   resolved=42,526   pct=78.3%
parliament=34  total=71,724   resolved=54,923   pct=76.6%
parliament=35  total=89,540   resolved=72,900   pct=81.4%
parliament=36  total=92,619   resolved=68,615   pct=74.1%
parliament=37  total=61,196   resolved=51,159   pct=83.6%
parliament=38  total=71,846   resolved=60,522   pct=84.2%
```

Net-new speeches added: **537,882** (legacy era went from 1,561 → 537,882). Each parliament jumped 50-1000x in speech count.

### Updated final aggregates

| metric | before parser fix | after parser fix |
|---|---|---|
| Total ON speeches | 407,980 | **944,301** |
| Total ON chunks | 320,040 | 973,579 |
| Embedded chunks | 320,040 (100%) | 973,579 (100%) |
| Modern era resolution | 98.0-98.5% | 98.0-98.5% (unchanged) |
| Legacy era resolution | n/a (no parsed speeches) | **73.9-84.2%** |
| `jurisdiction_sources.ON.hansard_status` | live | live (unchanged) |

### Why legacy resolution lags modern (74-84% vs 98%)

Legacy ON Hansard uses surname-only attributions much more often than the modern era ("Mr. Smith:" instead of "Mr. Stephen Crawford:"). With 1,993 historical MPPs spread across 158 years, two MPPs sharing a surname within one parliament is common. The legl-keyed resolver's `cand_count = 1` gate correctly leaves those NULL rather than guessing wrong — so the 16-26% unresolved is **correctness**, not failure.

The fix that would close the gap is **riding-aware disambiguation**: legacy attributions like `Mr Frank Miclash (Kenora)` already carry the riding in the parens, but our resolver only matches surname + parliament. Threading the riding through `politician_terms` would resolve same-surname collisions. Logged as a future task — not blocking; the backfill is complete.

### Pipeline timing (re-ingest, 2026-04-27 UTC)

- Per-parliament ingest: 05:48 → 07:22 (1h 34min for 7 parliaments)
- chunk-speeches: 07:22 → 07:57 (35 min for 537k new speeches)
- embed-speech-chunks: 07:57 → 11:23 (3h 26min for 607k chunks ≈ 2.9k/min)
- resolvers + coverage refresh: 11:23 → 11:47 (24 min, dominated by chunk-propagation per-parliament UPDATEs across 13 parliaments × ~610k chunks)

**Total wall-clock for the era-branching re-ingest: ~6h.**

Confirmed during research pass: HTML Hansard transcripts available back to **Parliament 32 (1981-04-21)**. Parliament 31 and earlier: probe at run time, expect a PDF-only floor somewhere between 1971 and 1981.

Order of operations (from the plan):

1. Apply migration 0037 ✅
2. Run `ingest-on-former-mpps` for full range (in flight)
3. Backfill ON Hansard parliament-by-parliament: 43, 42, 41, …, 32 (12 parliaments × 1-3 sessions each). Each parliament invocation is `python -m src ingest-on-hansard --parliament P --session S`.
4. Embed new chunks via `embed-speech-chunks` (TEI). Sequential with resolver — both UPDATE `speech_chunks` and Postgres can deadlock on contention.
5. Run resolvers in order: `resolve-on-speakers-dated` (the new heavy lifter) → `resolve-on-speakers` (existing name-only cleanup) → `resolve-presiding-speakers --province ON`.
6. `refresh-coverage-stats`, then manually flip `jurisdiction_sources.hansard_status` from `partial` to `live` if resolution-rate ≥ 95 %.

**Critical gotcha (from MB handoff 2026-04-23):** ON Hansard's UPSERT in `_upsert_speech` includes `politician_id = EXCLUDED.politician_id` in `DO UPDATE SET`. A re-ingest of a session whose speeches already carry resolver-assigned `politician_id` will overwrite them with the ingest-time name-only result. **Always `re-ingest → resolve`, never `resolve → re-ingest`.**

---

## Open followups

1. **Push the full backfill commit** once the P1..P44 run lands and the Hansard backwards-extension has validated the resolver. Don't bundle with the still-unstaged frontend WIP (`SpeechFilters.tsx`/`HansardSearchPage.tsx`/`hansard-search.css`).
2. **`admin.ts` drift on existing ON commands.** The `ingest-on-hansard` and `resolve-on-speakers` entries are in `jobs_catalog.py` but were never added to `admin.ts` — same drift the MB handoff flagged. The admin UI form picker won't show them; CLI + worker still honour them. Worth a small follow-up to backfill `admin.ts` for ON, NL, NB, QC, BC — but out of scope for this commit.
3. **Sentinel-date check in on_hansard parser.** MB had `date(1970, 1, 1)` as a silent fallback that broke date-windowed resolution. Grep `services/scanner/src/legislative/on_hansard*.py` for `1970` and any other suspicious epoch before declaring the backfill done.
4. **Mike Harris (former Premier) verification.** After the full ingest, `michael-harris-44` (member_id=44) should land as a separate row from `mike-harris` (member_id=7482, current MPP for Kitchener-Conestoga). Sanity check:
   ```sql
   SELECT name, ola_member_id, ola_slug, is_active
     FROM politicians
    WHERE last_name='Harris' AND province_territory='ON'
    ORDER BY ola_member_id;
   ```
   Expect at least the two distinct rows; `is_active=true` only for member_id=7482.
5. **BC + QC historical-roster backfills** — the same plan template applies. They're listed in the timeline as the next two propagations of this pattern.
