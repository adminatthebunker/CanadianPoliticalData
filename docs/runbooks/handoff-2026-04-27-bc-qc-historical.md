# BC + QC historical-roster backfills — 2026-04-27

Continues the propagation pattern from AB (2026-04-22), MB (2026-04-23), and ON (2026-04-26). User asked: "Lets start working through those historical roster backfills please."

## Snapshot before / after

### Quebec — 31-46 % → expected 80 %+ on older sessions

Before:
| Session | Speeches | % resolved |
|---|---:|---:|
| 39-1 | 57,608 | 46.4 |
| 39-2 | 38,246 | 41.4 |
| 40-1 | 23,872 | 31.5 |
| 41-1 | 45,546 | 39.8 |
| 42-1 | 49,092 | 69.9 |
| 42-2 | 18,944 | 72.2 |
| 43-1 | 65,253 | 83.4 |
| 43-2 | 14,784 | 84.0 |

Driver of the gap: only 124 *current* MNAs in `politicians`; retired MNAs from 2009-2018 weren't in the table.

After roster ingest + `resolve-qc-speakers-dated`: TBD (run pending). Target ≥ 80 % on the four worst sessions; the absolute ceiling is bounded by intrinsic role-only attributions ("Le Président" fully resolved, but "Le Secrétaire", "Une voix", "Des voix" stay NULL by design).

### British Columbia — 85-96 % name-only resolution stays; per-parliament terms now seeded

BC's existing name-based resolver was already at 85-96 % across P38-P43 because `lims_member_id` enables exact-int FK joins on the 376-MLA roster that was enriched in 2026-04-19/20. What was missing was per-parliament `politician_terms`: only ~98 BC term rows existed (current session + presiding officers + a handful of direct ingests). After this session: 853 total BC terms, 750 of them legl-keyed via LIMS GraphQL `allMemberParliaments`, source `lims.leg.bc.ca:parliament-{N}`. No resolution lift expected (the existing pipeline already hits 85-96 %), but the data is now available for future date-windowed work — BC Hansard pre-P38 backfill (HDMS archives back to 1970) gets a clean disambiguation path now without requiring further roster work.

The unresolved 4-15 % across P38-P43 is dominated by presiding-officer / staff roles (Deputy Speaker ≈ 4,952 rows, Committee Chair ≈ 7,749, Clerk / Law-Clerk / Lt.-Governor ≈ 60) plus a handful of single-letter parser misfires. Those need Tier 2/3 presiding-officer roster work, **not** more roster MLAs. Out of scope for this session.

## What shipped — files

```
db/migrations/
  0038_unique_qc_assnat_id.sql        — promote partial btree → UNIQUE partial

services/scanner/src/legislative/
  qc_former_mnas.py                   — alphabet-walk + bio-prose ingester (NEW)
  bc_member_parliaments.py            — LIMS GraphQL → per-parliament terms (NEW)
  qc_hansard.py                       — added resolve_qc_speakers_dated (single-CTE)

services/scanner/src/__main__.py      — 3 new Click commands:
  ingest-qc-former-mnas
  resolve-qc-speakers-dated
  enrich-bc-member-parliaments

services/scanner/src/jobs_catalog.py  — mirror entries for all 3
services/api/src/routes/admin.ts      — UI catalog mirror for all 3

docs/research/quebec.md               — historical-MNA section + status snapshot
```

## Pre-flight gotchas surfaced during the run

1. **Éric vs Eric Girard duplicate** — Open North current-roster ingest (2026-04-14) created two `politicians` rows for the same QC MNA via differently-encoded slugs (`opennorth:quebec-assemblee-nationale:éric-girard` and `:eric-girard`). Both shared `qc_assnat_id=17929`. Migration 0038's UNIQUE partial index would have failed without merging them first. Resolution: kept the accent-correct `Éric Girard` row, reparented the plain row's 1,234 speeches + 2,045 chunks (and 0 bill_sponsors) onto it, deleted the duplicate's identical `politician_terms` entry + the row itself in a single transaction.

   **Trap to avoid in future**: any UNIQUE-partial migration on a politician ID column must pre-flight-check for upstream-encoding-induced duplicates. Open North isn't the only ingester that hits this — anywhere a roster source is name-keyed with accents, slug normalization can branch.

2. **assnat.qc.ca soft-404** — `?_format=json` on assnat detail pages returns the same HTML, not 404 + JSON. Drupal serializer is **off**. Detail pages also live under TWO URL shapes:
   - Most former MNAs: `/fr/deputes/{slug}-{id}/index.html` (and `/biographie.html` for the actual bio)
   - Some pre-Confederation: `/fr/patrimoine/anciens-parlementaires/{slug}-{id}.html` (single page, no `/biographie.html` variant)

   The alphabet-listing parser in `qc_former_mnas.py` captures the URL `kind` and the bio fetcher reconstructs the right URL accordingly.

3. **Bio prose vs structured listings** — unlike ola.org's per-parliament listings, assnat.qc.ca only narrates careers as prose. We extract a single coarse career span per MNA via four regex patterns (Élu / Réélu / Défait / Démissionna / Décéda + year). Discrete mandate gaps (e.g. Marois's 1985-1989 hiatus) are tolerated — they don't have any Hansard speeches in them, so over-including is harmless to the date-windowed CTE.

   First 50 alphabet entries (mostly pre-Confederation Lower Canada / Conseil législatif appointees) hit only 14/48 = 29 % prose-match rate. Match rate is much higher for 20th-21st century MNAs whose bios follow the modern template — the gap-fill we actually need (2009-2018 retired MNAs).

4. **Federal years bleed into prose extraction** — bios narrate full political careers including non-QC events. Jean Charest's bio mentions "Réélu en 1988" (federal MP) and "Démissionna ... 1998" (federal Tory leader resignation) before "Élu député ... dans Sherbrooke en 1998" (his QC start). Our extractor takes `start_year = min(all Élu years)` and lands on 1988 — a decade before his actual QC career started. This is **harmless for the current QC corpus (2009-2026)** because the cand_count=1 gate still filters correctly: Jean Charest's 1988-2012 extracted span over-includes 1988-1998 but no Hansard speeches in our DB fall in that window. If we ever extend QC Hansard pre-2009, this drifts; the fix would be to gate `Élu` matches on QC context tokens like "Assemblée nationale" or "député du Québec" within the same sentence/clause window.

4. **BC LIMS GraphQL is dense** — `allMemberParliaments` returns all 750 (member, parliament) edges in a single query, no pagination needed at this scale, no rate-limiting observed. Each parliament's `startDate` / `endDate` is included via `parliamentByParliamentId` resolver. Single ~75 KB response. If LIMS ever paginates this connection, switch to cursor-based PageInfo iteration.

## The ledger

```sql
-- QC: politicians grew from 128 → ~1,500 (net depending on bio-extract success rate)
SELECT count(*)
  FROM politicians
 WHERE province_territory='QC' AND level='provincial';

-- QC: terms with new source
SELECT source, count(*)
  FROM politician_terms
 WHERE province_territory='QC' AND level='provincial'
 GROUP BY 1 ORDER BY 2 DESC;

-- BC: 853 terms now (was 103), 750 from LIMS legl-keyed
SELECT source, count(*)
  FROM politician_terms
 WHERE province_territory='BC' AND level='provincial'
 GROUP BY 1 ORDER BY 2 DESC;

-- QC resolution lift after dated post-pass
SELECT raw->'qc_hansard'->>'parliament' AS parl,
       raw->'qc_hansard'->>'session' AS sess,
       round(100.0*count(*) FILTER (WHERE politician_id IS NOT NULL)/count(*),1) AS pct
  FROM speeches
 WHERE source_system='hansard-qc'
 GROUP BY 1,2 ORDER BY 1,2;
```

## Pre-P38 BC Hansard backfill — added 2026-04-27 (later in same session)

After completing the BC + QC roster work, the user asked to start on the next lift, so we kept going with BC Hansard pre-P38.

### What shipped

`bc_hansard_parse.py` got an era-branching extension:

- New `detect_era()` — checks for `class="speakerbegins"` markers; absent → legacy.
- New `parse_url_meta()` filename branch for `{NN}p_{NN}s_{YYMMDD}{x}.htm` (legacy filename pattern; `x ∈ {a,m,p,n,z}` for am/morning/pm/night/special, mapped to `'am'`/`'pm'` token).
- New `_extract_legacy()` walker that handles two legacy sub-eras in one pass:
  - **P29-P34 (1970-1991)**: ALL-CAPS attributions (`HON. MR. GARDOM:`, `MR. SPEAKER:`) + `class="noindent"` continuations.
  - **P36-P37 (1996-2005)**: mixed-case attributions (`Hon. R. Coleman:`, `J. MacPhail:`) with NBSP-prefix indenting + bare-`<p>` continuations.

The unified opener regex captures both styles (`(?P<attribution>[^<]{2,200}?):` lifted from 80→200 chars to absorb `&nbsp;` runs in P37 attribution prefixes). The unified continuation regex matches `class="noindent"` / `class="quote"` (P29-P34) **plus** any `<p>` paragraph that doesn't itself look like a speaker opener (P36-P37). Section headings are filtered via `_LEGACY_SKIP_CLASS_RE` (proc_head / subj_head / toc1 / toc2 / time / page / header / footer / appendixSmall).

### Coverage delta

| Parliament | Era | Speeches | Resolved % |
|---|---|---:|---:|
| P29 (1970-1972) | Legacy ALL-CAPS | 11,351 | 13.9 |
| P30 (1972-1975) | Legacy ALL-CAPS | 70,938 | 10.9 |
| P31 (1976-1979) | Legacy ALL-CAPS | 21,399 | 8.8 |
| P32 (1979-1983) | Legacy ALL-CAPS | 51,623 | 15.3 |
| P33 (1983-1986) | Legacy ALL-CAPS | 48,264 | 22.8 |
| P34 (1987-1991) | Legacy ALL-CAPS | 26,016 | 49.8 |
| P35 (1992-1996) | Legacy ALL-CAPS | 83,187 | 97.4 |
| P36 (1996-2001) | Legacy mixed-case | 34,023 | 98.9 |
| P37 (2001-2005) | Legacy mixed-case | 31,664 | 87.6 |
| **P29-P37 total** | | **378,465** | **57.0 %** |

BC corpus grew from ~198,548 → 577,013 speeches (~2.9× growth). Pre-P35 resolution is bottlenecked by the LIMS `allMembers` historical-roster floor at P35 (1992) — pre-P35 MLAs simply aren't in `politicians`. Lifting them would require a separate roster-extension workstream (elections.bc.ca / Wikipedia / BC Archives), which is **out of scope** for this session.

### Embed phase issue (open follow-up)

Mid-embed phase, TEI hit a CUDA driver error (`CUDA_ERROR_UNKNOWN`) and fell back to CPU. ~424K BC chunks remain unembedded. Restart-recreate of the TEI container did not recover GPU access — it consistently logs "Could not find a compatible CUDA device on host" despite host `nvidia-smi` reporting the GPU healthy with 5731 MiB free and only Steam Helper using 5 MiB.

This is a docker-nvidia integration state issue (kernel module needs a reload, or docker daemon restart needed). Both require root. The fix is one of:

```bash
# Option A — reload nvidia-uvm kernel module
sudo rmmod nvidia_uvm && sudo modprobe nvidia_uvm

# Option B — restart docker daemon
sudo systemctl restart docker

# Option C — host reboot (heaviest, last resort)
```

After recovery, re-running `embed-speech-chunks` is idempotent and will pick up the 424K pending chunks.

```bash
docker compose run --rm scanner embed-speech-chunks
```

Throughput estimate: at ~17K chunks/min for modern era and ~3K/min for legacy era (longer chunks per the BC dossier), the pending 424K chunks should embed in 1-3 hours once GPU is back.

## Out of scope

- **Pre-P35 BC roster backfill** (1872-1991). Would lift P29-P34 resolution from ~10 % to ~80 %. Roster source candidates: elections.bc.ca, Wikipedia, BC Archives. Different workstream, separate from LIMS.
- **QC Tier 2 Vice-Président resolution** for the small fraction that doesn't auto-resolve from the parenthetical name form. Would need a hand-curated VP roster (similar to the SPEAKER_ROSTER pattern).
- **QC private-bills URL scheme**, votes registry (ASP.NET postback) — these are the bills/votes outstanding items still listed in `quebec.md`.

## Convention #1 status (per CLAUDE.md)

```
- Federal: openparliament_slug
- Nova Scotia: nslegislature_slug
- Ontario: ola_slug + ola_member_id (int)
- BC: lims_member_id (int)
- Quebec: qc_assnat_id (int)               ← already documented; no CLAUDE.md change needed
- Alberta: ab_assembly_mid (text)
- Manitoba: mb_assembly_slug
```
