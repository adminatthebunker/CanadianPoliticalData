# Provincial vote_positions probing — 2026-04-30

After scoping the plan for per-MLA vote ingest (`docs/runbooks/handoff-2026-04-30-provincial-votes.md` flagged this as the natural follow-on), I probed the source documents for several provinces. Findings here so the next session doesn't have to redo the discovery work.

The plan file (`/home/bunker-admin/.claude/plans/woolly-purring-penguin.md`) listed expected URL patterns and complexity estimates; this runbook records what's *actually* available, which is more complex than the plan assumed.

## Empirical probe results

| Province | Source location | Format (actual) | Per-MLA list visible? | Plan was wrong about |
|---|---|---|---|---|
| **NS** | `nslegislature.ca/sites/default/files/pdfs/proceedings/journals/{ASSEMBLY-SESSION}/{NNN}%20{YYYYMmmDD}.pdf` | **PDF** | TBD (pdfplumber probe needed) | Plan said HTML; actually PDF — comparable complexity to AB |
| **ON** | `ola.org/en/legislative-business/votes-search` (P43+) | JS-driven search; backend API not yet found | TBD | Plan assumed Drupal `?_format=json` would expose it; returns "Permission denied" body. Need to inspect SPA bundle for real API |
| **BC** | `leg.bc.ca/.../votes-and-proceedings/...html` is an iframe wrapper | Real content elsewhere — `lims.leg.bc.ca/hdms/votes/...` 404s; LIMS GraphQL has no vote-related fields | Unknown | Plan assumed HTML; the wrapper page has no inline content |
| **AB** | `docs.assembly.ab.ca/LADDAR_files/.../legislature_{N}/session_{S}/{YYYYMMDD}_1200_01_vp.pdf` | **PDF** (confirmed in plan) | Likely yes (per dossier) | Plan was correct |
| **QC** | `assnat.qc.ca/fr/travaux-parlementaires/registre-des-votes/index.html` | HTML | TBD (not probed today) | Plan assumed HTML — needs verification |
| **MB** | `gov.mb.ca/legislature/business/votes_proceedings.html` | HTML/PDF mixed | TBD | Plan said HTML/PDF; needs verification |
| **NL** | embedded in Hansard text | HTML | name-FK only | Plan correct |
| **NB** | `legnb.ca/.../legislation/...` Journals | HTML/PDF, bilingual | name-FK only | Plan correct |

## What the plan got right

- The schema validation conclusion: `vote_positions` table is the right home for this data; no migration needed.
- The reusable upsert pattern in `federal_votes.py:_upsert_vote_positions`.
- The matching strategy (Option A: date+sequence): still the cleanest design choice.
- The per-province politician-FK feasibility (6 with slug-FKs ready, NL+NB needing name-based).

## What the plan got wrong

- **NS isn't a low-complexity POC** — it's PDF parsing, comparable to AB. Phase 1 should NOT be NS.
- **ON's "structured votes-search" is JS-driven** — not directly JSON-exposable. Discovery would need SPA-bundle inspection (similar to how BC LIMS GraphQL was discovered).
- **BC V&P content lives somewhere we haven't located yet** — the `leg.bc.ca` page is a wrapper but the real payload isn't on the obvious LIMS HDMS paths.
- **Per-province discovery cost is non-trivial** — the plan's 1-2 sessions per province estimate was optimistic. More realistic: 2-4 sessions per province for first ingest.

## Recommended re-ordering

Drop the original Phase 1/2 split:

1. **New Phase 1 candidate: AB** — PDFs are confirmed available at predictable URLs (`docs.assembly.ab.ca/LADDAR_files/.../legislature_{N}/session_{S}/{YYYYMMDD}_1200_01_vp.pdf`) and `pdfplumber` is in scanner requirements. The discovery is done; only parser + matching remains. ~3-4 sessions.

2. **New Phase 2: QC** — Registre des votes URL is structured HTML (per dossier). Once probed and confirmed, parsing is straightforward and the yield is the largest single province (~230K positions). ~3 sessions.

3. **New Phase 3: ON via SPA inspection** — fetch the votes-search page as Chrome would, look at network tab for the real API endpoint. If found, ON is high-yield with `ola_slug` FK ready. ~3 sessions to discover + build.

4. **NS, MB, BC, NL, NB**: defer. Each needs its own dedicated discovery + parser session.

## What was NOT changed today

- `services/scanner/src/legislative/` — no new code shipped this session beyond what was committed earlier
- The plan file remains the recommended approach with this runbook as an empirical caveat
- No migrations, schedules, or politicians-table changes

## Suggested next step

Commit today's votes work that *did* ship (NT + federal + 8 provincial extractors), then start V&P ingest as a fresh focused session beginning with **AB PDF parsing** (cleanest known source).

The user previously said they'd do "full historical ingest another time" for federal pre-2006; the same posture probably applies here — V&P ingest is best done as a dedicated multi-session workstream rather than tacked onto an already-substantial day.
