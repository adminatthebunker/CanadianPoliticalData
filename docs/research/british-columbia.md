# British Columbia — Legislative Data Research

> Standalone research dossier for British Columbia. Cross-cutting context (schema, scanner modules, probe hierarchy, research-handoff protocol) lives in [`overview.md`](./overview.md).

**Legislature:** Legislative Assembly of British Columbia | **Website:** https://www.leg.bc.ca | **Seats:** 93 | **Next election:** 2028-10-21

**Status snapshot (2026-05-19):** ✅ **Bills live** via LIMS PDMS JSON. ✅ **Hansard live** via LIMS HDMS debates JSON + HTML, **581,391 speeches** (P29-P43 / 1970-2026 / full digital record); **94.4% attribution**. ✅ **Standing-committee transcripts live** (2026-05-19, see § Committee Activity) — `ingest-bc-committees` reads `scripts/seeds/bc-committee-meetings.json` (no listing API on lims.leg.bc.ca for committees) and lands `speech_type='committee'` rows; 976 speeches across 5 seeded meetings in `cay`/`fgs`/`dem`; daily 14:25 UTC. **Modern roster** (376 LIMS-keyed MLAs) enriched 2026-04-19/20; **per-parliament terms** (750 LIMS edges, P35-P43) added 2026-04-27; **pre-P35 historical roster** (160 Wikipedia-keyed MLAs covering 1969-1991) and **dated speaker resolver** added 2026-04-29 — see `docs/runbooks/handoff-2026-04-29-bc-pre-p35-roster.md`. **Presiding-officer Speaker roster extended** to P29-P37 same day, lifting Speaker-tagged attribution from 0% to 100% across pre-P38 (+20,348 rows). **2026-05-05 BC ALL-CAPS resolver** (commit `b0b2562`) parsed `MR. G.S. WALLACE (Oak Bay)` / `HON. D. BARRETT (Premier)` shapes the dated resolver mishandled (extracted constituency-in-parens as surname): three-tier disambiguation (lastname+date single → riding hint → first-initial), **+11,017 attributions**; BC corpus 92.5% → 94.4%. Votes / committees not yet built. Difficulty re-rated — Bills 5→2, Hansard 3→2.

---

## Bills & Legislation

- **Source URL(s):** https://www.leg.bc.ca/parliamentary-business/bills-and-legislation ; https://www.bclaws.gov.bc.ca/civix/content/bills/
- **Format:** HTML on leg.bc.ca; enacted legislation on bclaws.gov.bc.ca under Queen's Printer License. **Real bills data lives at LIMS PDMS** (see below).
- **Fields captured upstream:** Bill number, title, reading stages, sponsor.
- **Terms/Licensing:** Crown copyright. BC Laws permits commercial + non-commercial use under Queen's Printer License. leg.bc.ca page content restricted to personal use without written consent.
- **Rate limits / auth:** None documented.
- **Difficulty (1–5):** **2** (re-rated 2026-04-15 — upgraded from initial 5). After discovering the React SPA, deeper probing turned up a structured JSON endpoint at `https://lims.leg.bc.ca/pdms/bills/progress-of-bills/{sessionId}` that returns the full bill table as JSON. No auth, no SPA rendering needed. The earlier-found LIMS GraphQL gives us session IDs. This makes BC the second-easiest bills source in Canada after NS Socrata.
- **Notes:** See "★ Bills API — LIMS PDMS" below for endpoint shape and integration plan. bclaws.gov.bc.ca is still authoritative for enacted bill text; PDMS `files[].path` links into `/ldp/{session}/{reading}/{name}.htm` which can be resolved via `lims.leg.bc.ca/hdms/file/...` (same file-serving pattern as Hansard).

## ★ Bills API — LIMS PDMS (discovered 2026-04-15)

Root endpoint: `GET https://lims.leg.bc.ca/pdms/bills/progress-of-bills/{sessionId}` → JSON array of bills for that session. Session IDs come from LIMS GraphQL `allSessions`.

**Sample record shape:**

```json
{
  "billId": 1028,
  "billNumber": 1,
  "title": "An Act to Ensure the Supremacy of Parliament",
  "firstReading": "2026-02-14",
  "secondReading": null,
  "committeeReading": null,
  "thirdReading": null,
  "reportReading": null,
  "royalAssent": null,
  "chapterNumber": null,
  "billTypeId": 1,
  "memberId": 236,
  "memberAlias": null,
  "titleChanged": false,
  "reinstated": false,
  "ruledOutOfOrder": false,
  "files": { "nodes": [
    { "readingTypeName": "1st Reading", "readingTypeId": 1,
      "readingDate": "2026-02-14",
      "fileName": "gov01-1.htm",
      "path": "/ldp/38th2nd/1st_read/gov01-1.htm" }
  ] }
}
```

**What it gives us directly into our schema:**

- `bills.bill_number` ← `billNumber`
- `bills.title` ← `title`
- `bills.status` / `bills.status_changed_at` ← derived from latest non-null reading date
- `bill_events` rows ← one per non-null reading date (first/second/committee/third/report/royal_assent)
- `bill_sponsors.politician_id` ← **already resolved** via `memberId`, which is the integer LIMS member ID. We can ingest BC members via LIMS GraphQL `allMembers` and store `lims_member_id INT` on politicians → exact-int join replaces slug/name fuzz entirely.

**Session enumeration:**

- Current session: ID 206 = 43rd Parliament, 2nd Session, 36 bills as of 2026-04-15.
- Previous session: ID 173 = 43rd-1st (2025), ~185 bills.
- Entire BC historical: `allSessions` returns every session back to 1872 (id 171). PDMS appears to serve all of them.

**Retrieval characteristics:**

- Single request per session (no paging; 36 bills ≈ 5 KB, 500-bill sessions ≈ 50 KB).
- Polite pacing still recommended (~1 req/sec) but total traffic to cover all BC history is tiny — 140 sessions × ~50 KB ≈ 7 MB.
- No WAF observed on `lims.leg.bc.ca` across probe traffic.

**This downgrades BC from "blocked until we build Playwright" to "API-driven pipeline" — similar effort to NS Socrata, but with more structured data per bill.**

## Hansard / Debates

- **Source URL(s):** Discovery via `https://lims.leg.bc.ca/hdms/debates/{parl}{sess}` (JSON listing of every sitting). Transcripts: `https://lims.leg.bc.ca/hdms/file/Debates/{parl}{sess}/{YYYYMMDD}{am|pm}-{House-Blues.htm|Hansard-n{NNN}.html}`. The Drupal page at leg.bc.ca is a PDF-viewer wrapper — the real HTML lives on LIMS HDMS.
- **Format:** HTML with rich semantic markup (`SpeakerBegins`, `Speaker-Name`, `Time-Stamp`, `Proceedings-Group`, etc.). Both Blues (draft, ~1 hr post-adjournment) and Final HDMS variants share the same class taxonomy — Final hyphenates class names, Blues does not; single parser handles both.
- **Speaker identification:** By MLA name (no stable per-turn IDs). Sitting Speaker's name lives in the HTML header and is extracted per-sitting to resolve "The Speaker" attributions.
- **Difficulty (1–5):** **2** (re-rated 2026-04-19 — downgraded from initial 3). The JSON debate-index endpoint eliminates URL discovery entirely; markup is stable and class-driven.
- **Notes:** Archives from 1970 onward. Discovery endpoint covers every session LIMS has indexed. Deputy Speaker / Committee Chair attributions (~10% of rows) remain role-only in v1 — LIMS GraphQL's role data isn't reliably scoped to the current session.

## ★ Hansard pipeline — LIMS HDMS (live 2026-04-19)

Current scope: 43rd Parliament, 2nd Session. **40 House sittings, ~4,800 speeches, 89.5% politician-linked** (97.5% of named MLAs — the remainder are legitimate non-MLA guests).

**Upsert key strategy:** `speeches.source_url = hansard-bc.canonical/Debates/{parl}{sess}/{YYYYMMDD}{am|pm}-Hansard.html` — a synthesized canonical URL stable across Blues and Final. Real URLs live in `speeches.raw.bc_hansard.{blues_url, final_url, variant}`. Final overwrites Blues in place via `ON CONFLICT DO UPDATE` using this canonical key.

**Ingest commands:**

```bash
# Full session backfill
python -m src ingest-bc-hansard --parliament 43 --session 2

# Smoke-test one URL
python -m src ingest-bc-hansard --parliament 43 --session 2 \
    --url https://lims.leg.bc.ca/hdms/file/Debates/43rd2nd/20260415pm-House-Blues.htm

# Post-pass resolver (after expanding BC MLA roster or fixing name-normalisation)
python -m src resolve-bc-speakers

# Tier 1 presiding-officer seeder + resolver (idempotent)
python -m src resolve-presiding-speakers --province BC
```

**Module layout:**

- `services/scanner/src/legislative/bc_hansard.py` — discovery, fetch, upsert orchestrator, speaker lookup, post-pass resolver
- `services/scanner/src/legislative/bc_hansard_parse.py` — pure-offline HTML parser (stdlib `re` + `html`), handles Blues + Final variants
- `services/scanner/src/legislative/presiding_officer_resolver.py` — shared Tier 1 Speaker seeder + date-ranged resolver (used by both BC and AB)

## ★ Speaker resolver — two bugs fixed 2026-04-20

Post-ingest audit surfaced two resolver bugs that caused ~6,300 named-MLA speeches to resolve as ambiguous/unmatched. Both now fixed; document here so we recognise the shape if a future province imports the same code.

**Bug 1 — compound-surname initial-last parse.** `bc_hansard.py` `SpeakerLookup.resolve()` required exactly 2 tokens after normalisation for the initial-last branch (`"p milobar"`). Compound surnames like "M. de Jong" normalise to 3 tokens (`"m de jong"`), fell through to the surname-only branch, and were then flagged ambiguous because the `by_surname` index held both Michael and Harry de Jong under `"jong"`. The index was already built correctly — keyed on `"{initial} {last_token_of_surname}"`, so `"m jong"` would have matched Michael uniquely. Fix: accept 3+ tokens when `tokens[0]` is a single letter and look up `f"{tokens[0]} {tokens[-1]}"`. Recovered ~4,724 Michael de Jong rows plus similar patterns. Applies to any future "van Dongen", "de la Cruz", etc.

**Bug 2 — duplicate politicians row from enrichment script.** `scripts/bc-enrich-historical-mlas.py` deduped on `lims_member_id` alone. The bills-ingest roster pipeline creates `politicians` rows with `lims_member_id IS NULL` for current MLAs; the enrichment script then saw no existing LIMS-61 row for Lana Popham and inserted a second row, poisoning the `by_initial_last["l popham"]` lookup (two candidates → ambiguous → unresolved). Fix: enrichment script now name-lookups any existing unlinked BC row and UPDATEs it to attach `lims_member_id`, rather than INSERTing a duplicate. One-time DB merge collapsed the existing Popham duplicate (transferred `lims_member_id=61` to the active row, deleted the historical row — zero FK references so the merge was trivial). Recovered ~1,589 Popham rows.

**Where the same pattern could bite future provinces:**
- Any province that adopts the "LIMS GraphQL historical-roster enrichment" pattern (BC-specific for now) inherits the duplicate-row risk if the enrichment script doesn't UPSERT on name for rows missing the canonical ID.
- The compound-surname fix now lives in `bc_hansard.py`; if we clone that resolver for another legislature, copy the 3+-token branch too.

## ★ Presiding-officer resolution — Tier 1 live 2026-04-20

BC "The Speaker" attributions were already resolved at ingest time by `bc_hansard.py`'s `BC_PARLIAMENT_SPEAKER` dict + `sitting_speaker_name` fallback. As of 2026-04-20 this is **backstopped** (not replaced) by shared `presiding_officer_resolver.py` which seeds BC's Speaker roster into `politician_terms` for schema consistency with AB and any future province.

**Why seed terms even though BC Hansard already resolves Speaker at ingest:**
1. Single source of truth — `politician_terms` is the canonical place for "who held office X between dates Y–Z". Keeping BC out of it creates a weird asymmetry with AB.
2. The in-code dict is keyed on `parliament` only — it silently gets the 41st Parliament wrong because that parliament had three Speakers (Reid → Thomson → Plecas). Term-based lookup handles the mid-parliament switch; dict lookup doesn't. Post-pass `resolve-presiding-speakers --province BC` can catch any drift the ingest-time path misses.
3. Future `bc_hansard.py` cleanup can retire `BC_PARLIAMENT_SPEAKER` entirely once we confirm the term-based path covers every existing case.

**BC Speaker roster (seeded into `politician_terms`, `source='presiding_officer_seed'`).** Extended back from P38 to P29 on 2026-04-29 to cover the full Hansard corpus span:

| Speaker | Start | End | Parliament |
|---|---|---|---:|
| William Harvey Murray | 1969-08-27 | 1972-08-30 | 29 |
| Gordon Dowding | 1972-08-30 | 1975-12-11 | 30 |
| Dean Edward Smith | 1975-12-11 | 1979-05-10 | 31 |
| Harvey Schroeder | 1979-05-10 | 1983-05-05 | 32 |
| Kenneth Walter Davidson | 1983-05-05 | 1986-10-22 | 33 |
| John Douglas Reynolds | 1986-10-22 | 1990-01-01 | 34 |
| Charles Stephen Rogers | 1990-01-01 | 1991-10-17 | 34 |
| Joan Sawicki | 1991-10-17 | 1994-01-01 | 35 |
| Emery Barnes | 1994-01-01 | 1996-05-28 | 35 |
| Dale Lovick | 1996-05-28 | 1998-01-01 | 36 |
| Gretchen Mann Brewin | 1998-01-01 | 2000-01-01 | 36 |
| Bill Hartley | 2000-01-01 | 2001-05-16 | 36 |
| Claude Richmond | 2001-05-16 | 2005-05-17 | 37 |
| Bill Barisoff | 2005-05-17 | 2013-05-14 | 38, 39 |
| Linda Reid | 2013-05-14 | 2017-06-22 | 40 |
| Steve Thomson | 2017-06-22 | 2017-06-29 | 41 (7 days) |
| Darryl Plecas | 2017-09-08 | 2020-12-07 | 41 |
| Raj Chouhan | 2020-12-07 | — | 42, 43 |

Gap between Thomson (ends June 29, 2017) and Plecas (starts Sept 8, 2017) = summer recess; no Hansard falls in that window so no attribution is lost. Pre-2005 dates are year-precision on Wikipedia — within-parliament transitions (P34, P35, P36) use Jan 1 of the transition year as a conservative boundary. BC sittings cluster Spring + Fall, so the resulting attribution noise around January transitions is bounded. Sources: Wikipedia "Speaker of the Legislative Assembly of British Columbia" + per-parliament articles.

**Resolver run after extension:** `resolve-presiding-speakers --province BC` resolved all 20,348 unattributed Speaker-tagged rows (no_term_match=0). P37 jumped 88.3% → 99.9% from a single Richmond entry.

**Out of scope (Tier 2/3):** Chairman (16,421 legacy "MR. CHAIRMAN" rows = Committee-of-the-Whole chair, rotating), The Chair (7,817 modern rotating), Deputy Speaker (5,038 rotating), various Clerk / Law-Clerk / Lt.-Governor ceremonial roles (~70). Resolving these requires per-sitting committee-membership data (for Chairman/The Chair/Deputy Speaker) — they're attributed today as role-only ("the person presiding at this moment was the Chair") rather than misattributed to a specific MLA. Acceptable residual at the date-windowed-only attribution ceiling (BC corpus 91.9% attributed).

## Voting Records / Divisions

- **Source URL(s):** https://www.leg.bc.ca/parliamentary-business/overview/43rd-parliament/2nd-session/votes-and-proceedings
- **Format:** HTML Votes and Proceedings.
- **Roll-call availability:** Yes, recorded divisions with member names.
- **Difficulty (1–5):** 3.
- **Notes:** No dedicated voting API. Consistent URL structure per Parliament/session.

## Committee Activity

- **Status (2026-05-19):** ✅ Standing-committee transcripts SHIPPED via `ingest-bc-committees` — `bc_committees.py` + `scripts/seeds/bc-committee-meetings.json`. First-cycle outcome: 5 meetings / 976 speeches / 62% MLA-FK (witness rate consistent with committee transcripts being ~40% non-MLA). Three active 43rd-Parliament committee codes seeded: `fgs` (Finance and Government Services), `cay` (Children and Youth), `dem` (Democratic and Electoral Reform). Daily schedule 14:25 UTC.
- **Source URL(s):** https://lims.leg.bc.ca/hdms/file/Committees/{parl}{sess}/{code}/{date}{am|pm}-{ShortName}-{Location}-Blues.htm (modern Blues); /...-{ShortName}-{Location}-n{NNN}.html (Final). Filename token + location vary per committee + meeting (e.g. "Finance"/"Nelson", "ChildrenYouth"/"Victoria", "DemElecReform"/"Victoria"). Filenames probed and confirmed via site:lims.leg.bc.ca search.
- **Format:** HTML only (no PDF Final variant for current-session committee transcripts confirmed). Same `SpeakerBegins` / `Time-Stamp` / `Proceedings-Group` class taxonomy as floor Hansard — `bc_hansard_parse.extract_speeches` reused unchanged. Title-page block adds `<p class="CommitteeNamePreamble">` / `<p class="Location">` markers extracted by `extract_committee_meta()`.
- **Difficulty (1–5):** **3** (re-rated 2026-05-19 from initial 2). The parser is essentially free reuse of `bc_hansard_parse` (markup identical), but **discovery has no API**: HDMS `/hdms/committees/{parl}{sess}` returns 404; HDMS directory listings under `/hdms/file/Committees/` return 404; LIMS GraphQL has zero committee fields (only `Executive Council` + `Other` role types); leg.bc.ca per-committee pages are SPA-rendered with no meeting dates in static HTML; Drupal `/jsonapi/` + `?_format=json` both disabled. v1 ships with an operator-curated seed file (`scripts/seeds/bc-committee-meetings.json`) — the ingester reads it and is idempotent over whatever set it sees. Auto-discovery is a follow-up workstream (Playwright over the SPA pages, or BC Hansard team API outreach).
- **NOT same as Section A / Section C of Committee of the Whole.** The existing `/hdms/debates/{parl}{sess}` JSON listing emits `CommitteeA`/`CommitteeC` entries (74 of 171 in 43rd-2nd) — those are Committee-of-the-Whole sub-chamber sittings (chamber business, "Estimates"/"Section A/C" content). They are filtered out at `bc_hansard.py:_parse_debate_index_entry` and stay out. Genuine standing-committee transcripts (CAY, FGS, DEM, etc.) live in a completely separate `/hdms/file/Committees/{parl}{sess}/{code}/` URL tree.
- **Speaker resolution:** chamber-wide BC lookup (`load_bc_speaker_lookup`) — BC has 0 `politician_committees` rows so the AB-style committee-restricted lookup pattern can't be used. Witness over-attribution is a known v1 limitation. Will tighten when BC `politician_committees` membership ingest lands (separate workstream).
- **Out of scope for v1:** historical backfill (pre-43rd; IndexCmt paths exist for some historical sessions but filenames vary per session — defer until v1 ships); membership ingest (no API for it); LAMC special-prefix shape (`42nd-LAMC`); substitute-MLA detection from `Membership` section (BC HTML has it but not parsed in v1).
- **Catalog probed 2026-05-19** (via site:lims.leg.bc.ca search): `cay`, `fgs`, `dem` (active 43rd-1st); `pac`, `health`, `rpa`, `rpea` (historical). Catalog lives in `bc_committees.STANDING_COMMITTEES` and is keyed on LIMS committee code (lowercase).

## Existing third-party scrapers

- **opencivicdata/scrapers-ca:** `ca_bc` module exists.
- Other: None identified.

## ★ Member Data — LIMS GraphQL (discovered 2026-04-15)

Independent of the bills question, BC exposes a **public, fully-introspectable GraphQL API** at `https://lims.leg.bc.ca/graphql` (POST). No auth, no documented rate limit, CORS permissive. Discovered by mining the `dyn.leg.bc.ca` React SPA bundle for an Apollo client `uri`.

**Schema scope:** 110 root query fields covering members, parliaments, sessions, constituencies, parties, ministers, executive councils, clerks, legislative assistants. Notable `all*` entry points:

- `allMembers`, `allMemberParliaments`, `allMemberElections`, `allMemberRoles`, `allMemberResignations`, `allMemberTypes`, `allMemberConstituencies`
- `allParliaments`, `allSessions`, `allParties`
- `allConstituencies`, `allConstituencyOffices`
- `allExecutiveCouncils`, `allExecutiveStaffs`, `allMinisters`
- `allClerks`, `allLegislativeAssistants`, `allRoles`, `allRoleTypes`
- `allSocialMediaLinks`

**What it does NOT expose:** bills, Hansard, divisions, committees — this is a member/role/org data API, not a legislative-activity one.

**Why it's valuable anyway:**

1. Richer than Open North for BC — includes role history (minister → critic → private member transitions), executive council membership over time, committee postings.
2. Single query fetches what Open North's Represent API returns plus ~10× more structured metadata.
3. Can replace / augment our BC gap filler (`gap_fillers/bc.py`) once we decide how to fold this into our politicians table.
4. Introspection means no schema guessing — `__schema { queryType { fields { name } } }` returns everything.

**Minimum probe query:**

```bash
curl -s -X POST -H "Content-Type: application/json" \
  --data '{"query":"{ allMembers(first: 5) { nodes { id firstName lastName } } }"}' \
  https://lims.leg.bc.ca/graphql
```

**Later-work to capture:** a BC-members enrichment that hits this API to populate politician role history + constituency-office detail in our DB. Independent of the bills pipeline; could be done at any time.

## Status

- [x] Research complete — partially superseded 2026-04-15/19 (see re-ratings)
- [x] Schema drafted — shared schema applies; no new migration needed beyond `0011_politician_lims_member_id.sql`
- [x] Ingestion prototyped (LIMS PDMS pipeline)
- [x] Production ingestion live (bills: 43-2 current, 36 bills / 92 events / 36 sponsors / 36 FK-linked)
- [x] Production ingestion live (Hansard: full P29-P43 corpus, **577,013 speeches / 91.9% politician-linked** as of 2026-04-29)
- [x] Modern-roster enrichment (376 MLAs via LIMS GraphQL `allMembers` — `scripts/bc-enrich-historical-mlas.py`, 2026-04-19/20)
- [x] Resolver bug fixes (compound-surname initial-last + duplicate-Popham merge, 2026-04-20)
- [x] Tier 1 presiding-officer (Speaker) terms seeded into `politician_terms` — initial P38-P43 (2026-04-20), **extended back to P29 (2026-04-29)** with +13 historical Speakers
- [x] Historical backfill — Hansard pre-P38 (P29 1970 → P37 2005, 9 parliaments). Era-branching parser added to `bc_hansard_parse.py` for the bare-`<p><b>NAME:</b>` legacy markup with two sub-eras (P29-P34 ALL-CAPS attributions + `class="noindent"` continuations; P36-P37 mixed-case `Hon. R. Coleman` / `J. MacPhail` attributions + bare-`<p>` continuations). 378,465 new speeches added (2026-04-27).
- [x] Per-parliament terms for modern roster (P35-P43) — `enrich-bc-member-parliaments` via LIMS GraphQL `allMemberParliaments`, 750 (member, parliament) edges, BC terms 103 → 853 (2026-04-27).
- [x] **Pre-P35 BC roster source — Wikipedia per-parliament wikitable parser** (`bc_former_mlas.py`). 160 pre-1992 MLAs across P29-P34, source-tagged `wikipedia:bc-mla:{slug}`, terms tagged `wikipedia:bc-{N}{ord}-parliament`. Multi-member-riding rowspan handled via per-position carryover tracking. (2026-04-29)
- [x] **Date-windowed speaker resolver — `resolve-bc-speakers-dated`** (`bc_hansard.py`). Single CTE with inline surname extraction (BC parser doesn't pre-stash surname in `raw`). Lifted pre-P35 attribution from 8-50% to 75-90%; rescued ~6K modern surname-collision rows as a bonus. Idempotent. (2026-04-29)
- [ ] Historical backfill — bills (PDMS serves every session back to 1872, not yet ingested)
- [ ] Hansard scheduler cron (Blues poller + Final sweep)
- [ ] Tier 2 presiding officers — Deputy Speaker (5,038 rows) — needs per-parliament roster source
- [ ] Tier 3 presiding officers — Committee of the Whole Chair / Chairman (7,817 + 16,421 rows) — needs parser-level extraction of "X in the chair" proceedings headers + per-sitting Committee Chair roster
- [x] **Committee transcripts (standing/special) — shipped 2026-05-19** via `ingest-bc-committees`. 5 seeded meetings → 976 speeches / 62% MLA-FK; daily 14:25 UTC. Discovery via operator-curated seed file (`scripts/seeds/bc-committee-meetings.json`); BC has no listing API. Section A/C of Committee of the Whole remains a separate (and explicitly chamber-business) workstream — see § Committee Activity above.
- [ ] BC `politician_committees` membership ingest — separate workstream; needs Playwright or BC Hansard team API outreach. Required to gain witness-rejection from AB-style committee-restricted lookup.
- [ ] Auto-discovery of new BC committee transcripts (replace `bc-committee-meetings.json` seed)
- [ ] Votes
- [ ] LIMS GraphQL member-enrichment workstream (optional, independent of bills)
