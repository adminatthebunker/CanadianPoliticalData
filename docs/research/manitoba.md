# Manitoba — Legislative Data Research

> Standalone research dossier for Manitoba. Cross-cutting context (schema, scanner modules, probe hierarchy, research-handoff protocol) lives in [`overview.md`](./overview.md).

**Legislature:** Legislative Assembly of Manitoba | **Website:** https://www.gov.mb.ca/legislature | **Seats:** 57 | **Next election:** By 2027-10-05

**Status snapshot (2026-05-14):** 🟢 **Live.** Bills roster + bill stage events from `billstatus.pdf` + Hansard for **legislatures 37-43** — 28 sessions, **1999-11-26 → 2026-04-16** (full 27-year span). **410,315 speeches, 89.37% resolved to politicians.** Parser dispatches on Word-export format: legs 39-43 go through `mb_hansard_parse` (MsoNormal, modern markup), legs 37-38 go through `mb_hansard_parse_w97` (uppercase-tag Word 97 export with `<B><P>Name:</B>text</P>` speaker pattern and split-sitting `hNN_1.html` + `hNN_2.html` transcript shape). Resolution mix: name-matched at ingest + date-windowed presiding speakers (Hickes/Reid/Driedger/Lindsey) + Tier-2 Pass-1 inline-name presiding resolver + Tier-2 Pass-3 role-only Deputy Speaker resolver (Santos/Brick/Nevakshonoff/Piwniuk/Micklefield/Blashko, 37L-43L) + Tier-2 Pass-4 cross-jurisdictional named-speaker resolver + `resolve-mb-speakers-dated` using `politician_terms` spans. Politicians table holds the full **880-MLA historical roster** back to 1870 (56 current + 824 historical from `ingest-mb-former-mlas`). All via `ingest-mb-mlas` / `ingest-mb-former-mlas` / `ingest-mb-bills` / `parse-mb-bill-events` / `ingest-mb-hansard` / `resolve-mb-speakers-dated` / `resolve-presiding-speakers` / `resolve-role-only-presiding-officers` / `relink-mb-speaker-roles` (parser-regex catch-up). PDF extraction uses the shared `pdf_utils.pdftotext` helper (Poppler, `-raw` mode) that also backs AB Hansard — no new dependency.

---

## User research (handoff URLs)

The user's initial Manitoba research handoff:

- **Bills search:** https://web2.gov.mb.ca/bills/search/search.php
- **Current session bills:** https://web2.gov.mb.ca/bills/43-3/index.php (PDFs)
- **Members:** https://www.gov.mb.ca/legislature/members/mla_list_constituency.html
- **Hansard:** https://www.gov.mb.ca/legislature/hansard/43rd_3rd/43rd_3rd.html#top (HTML / PDF versions)

## Bills & Legislation 🟢 LIVE (2026-04-20)

- **Roster from `/bills/{P}-{S}/index.php`** via `ingest-mb-bills` — parses the Government Bills + Private Members' Bills tables on a single page. Current session 43-3: **81 bills** (47 government + 34 PMB), all sponsors FK-linked to politicians via the slug join.
- **Per-bill pages** (`b{NNN}e.php`) are bill-text-only as predicted — no sponsor, no dates. We never fetch them; the index has all the metadata we need.
- **Stage timeline from `billstatus.pdf`** via `fetch-mb-billstatus-pdf` + `parse-mb-bill-events` — 106 events across 80 bills (bill 235 is pre-first-reading and not yet in the PDF). Dates span first reading / second reading / committee (with committee name like "Justice", "Social and Economic Development"). PDF parsed via Poppler's `pdftotext -raw` mode (the `-layout` mode wrapped dates awkwardly across lines).
- **Canonical ID:** `politicians.mb_assembly_slug` (surname slug from `info/<surname>.html`) added in migration `0030`. 56/56 seated MLAs have it stamped via `ingest-mb-mlas`. Compound surnames ("Dela Cruz" → slug `delacruz`) handled by slug-candidate ordering in the parser.
- **No open-data portal, no RSS, no JSON endpoints** (as probed). Scraping is the only path.

## Hansard / Debates 🟢 LIVE (43rd Legislature complete, 2026-04-21)

- **Source URL pattern:** `/hansard/{leg}_{sess}/vol_NN[letter]/hNN[letter].html` — Word-exported HTML served as windows-1252 (force encoding on fetch, otherwise accented characters mojibake).
- **Full 43rd Legislature ingested:** 3 sessions, 184 sitting-days, **30,649 speeches**, 81.3% resolved to politicians (24,912 / 30,649), span 2023-11-09 → 2026-04-16. Per-session breakdown:
    - **43-1:** 12,379 speeches, 75 days (2023-11-09 → 2024-11-08), 77.5% resolved
    - **43-2:** 12,882 speeches, 75 days (2024-11-19 → 2025-11-07), 81.7% resolved
    - **43-3:** 5,388 speeches, 34 days (2025-11-18 → 2026-04-16), 89.0% resolved
- **Resolution pipeline:** inline name match via `mb_assembly_slug` → `resolve-mb-speakers` post-pass → `resolve-mb-speakers-dated` (date-windowed historical surnames) → `resolve-presiding-speakers --province MB` (links "The Speaker" rows to Hickes/Reid/Driedger/Lindsey across 37L-43L windows) → Tier-2 Pass-1 `resolve-inline-presiding-officers` (parens-name presiding shapes) → Tier-2 Pass-3 `resolve-role-only-presiding-officers --province MB` (links role-only `The Deputy Speaker` rows to Santos/Brick/Nevakshonoff/Piwniuk/Micklefield/Blashko across 37L-43L) → Tier-2 Pass-4 `resolve-named-speakers` (cross-jurisdictional surname FK with date-windowed disambiguation) → `relink-mb-speaker-roles` (parser-regex catch-up for honorific-prefixed presiding labels missed at ingest).
- **Parser quirks:** timestamp markers are `<b>*</b> (HH:MM)` between speech blocks — we use them to set per-speech `spoken_at` accurately rather than defaulting to sitting-start time. Speaker attribution uses `<b>Hon./Mr./Mrs./Ms./MLA Surname:</b>` with the full person's first+last name spelled out only on throne-speech / formal introductions. `_clean_speaker` strips U+00AD SOFT HYPHEN characters that Word HTML occasionally embeds inside speaker labels (would otherwise block `_GROUP_RAW_RE` from tagging the row `speech_type='group'`).
- **MB chamber-parser empty-role bucket (2026-05-14, commit `bfeb5a3`):** before this cycle, `_ROLE_PATTERNS` required a `the` prefix or the specific `madam\s+speaker` / `mister\s+speaker` exact shape. MB pre-43L Hansard uses `Mr. Deputy Speaker` / `Madam Chairperson` (honorific-prefixed) — four new pattern entries route these to the same canonical roles. The new `relink-mb-speaker-roles` Click command applies the regex set to existing rows; `mb_speaker_role_relink.py` imports `_match_role` from the parser so the relink and future ingests share the regex byte-for-byte.
- **MB heading-misclassification cleanup (same cycle):** committee-transcript section headings (`Meetings`, `Committee Membership`, `Officials Speaking on Record at the … meeting`, etc.) were being inserted as `speech_type='floor'` rows because `_is_heading()`'s structural detection missed shapes with trailing colons. New `_HEADING_TEXT_RE` catches 20+ named-section-heading shapes; 628 existing rows reclassified `speech_type='floor' → 'metadata'`.
- **MB 1970-01-01 fallback-date fix (same cycle):** `extract_sitting_date()` now decodes HTML entities before regex match (root cause: `&nbsp;` between day-of-week and month was blocking `_HEADER_DATE_RE` on legacy MB sittings); `_HEADER_DATE_RE` accepts optional comma after month name. 1,803 rows date-corrected across 10 historical sittings (2007-04 → 2008-09, 38L-5S / 39L-1S / 39L-2S).
- **Remaining gap (~10.6% unresolved):** rotating Committee-of-the-Whole Chair labels (`The Chairperson` / `The Deputy Chair` / `The Acting Chairperson`) — chamber Hansard lacks in-corpus chair-handover signals, so date-windowed resolution doesn't apply. Same family as deferred AB Acting Speaker / BC Chairman. ~50 paren-only constituency-fragment rows whose section heading is a generic non-name string ("Introduction of Guests" / "Motion presented.") are also out of reach without a multi-paragraph speaker-name parser fix (deep refactor; deferred).

## Voting Records / Divisions

- **Source URL(s):** https://www.gov.mb.ca/legislature/business/votes_proceedings.html
- **Format:** Votes and Proceedings documents; typically embedded in daily records.
- **Roll-call availability:** Variable format.
- **Difficulty (1–5):** 4.
- **Notes:** No standalone export.

## Committee Activity

- **Source URL(s):** https://www.gov.mb.ca/legislature/committees/ ; https://www.gov.mb.ca/legislature/committees/membership.html
- **Format:** HTML pages with meeting notices, broadcasts, reports, clerk contacts.
- **Data available:** Non-permanent rotating membership; broadcasts; reports.
- **Overlap with existing scanner:** None.
- **Difficulty (1–5):** 2.
- **Notes:** Meetings via Zoom Webinar. Standing committees can't meet Jan–Aug except Public Accounts.

## Existing third-party scrapers

- **opencivicdata/scrapers-ca:** `ca_mb` module exists (provincial + Winnipeg municipal).
- Other: None identified.

## Status

- [x] Research complete
- [ ] Schema drafted
- [ ] Ingestion prototyped
- [ ] Production ingestion live
