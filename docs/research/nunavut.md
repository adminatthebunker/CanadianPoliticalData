# Nunavut — Legislative Data Research

> Standalone research dossier for Nunavut. Cross-cutting context (schema, scanner modules, probe hierarchy, research-handoff protocol) lives in [`overview.md`](./overview.md).

**Legislature:** Legislative Assembly of Nunavut | **Website:** https://www.assembly.nu.ca | **Seats:** 22 | **Next election:** 2029-10

**Status snapshot (2026-04-19):** ✅ **Bills live** for 7th Assembly, 1st Session (4 bills / 24 events / **0 sponsors — by design, NU is consensus government**). All 4 are appropriation acts at Royal Assent. Drupal `?_format=json` is **disabled** here unlike Ontario, so HTML scrape is the only route.

**Hansard probe (2026-05-14):** ✅ **Hansard is reachable, no WAF.** Apache + Drupal 9 (same CMS as bills), `X-Drupal-Dynamic-Cache: HIT`. Index at `/hansard` (English, primary) lists 59 PDF references on the page alone using the `/sites/default/files/YYYYMMDD_Hansard.pdf` pattern, with some files in dated subdirs like `/sites/default/files/2022-11/`. Direct PDF download returns `HTTP 200 OK`, no auth, no challenge. The page exposes **four language entry-points** as Drupal language paths — `/hansard` (English), `/fr/hansard`, `/iu/hansard-iu` (Inuktitut romanized), `/IU-CA/hansard-ius` (Inuktitut syllabics) — but only the **English** path lists per-sitting PDF attachments in the page body. The other three paths are language-switched chrome with no PDF index, which suggests Hansard is published as a single English PDF per sitting (the Inuktitut/French translations may exist but aren't indexed under the language paths). `?_format=json` returns 406 (as expected — Drupal serializer is off, matching the bills observation). **Hansard ingestion is ready to design** — open questions reduced to: (a) is there an older-Hansard archive beyond what `/hansard` page lists, and (b) does the `_Hansard_4.pdf`-style suffix represent multi-part sittings or revisions (`20210301_Hansard_4.pdf` is on the index).

---

## Why NU (and NT) are different

NU has **consensus government** — 22 non-partisan MLAs. No political parties, no party whips. Decisions often by consensus or acclamation. Same caveats as NT:

- The "sponsor" concept doesn't apply in the partisan sense — the pipeline writes 0 `bill_sponsors` rows, faithfully.
- "Voting records" in the partisan sense largely don't exist — schema decision deferred (see migration `0018_votes.sql`, intentionally unapplied pending consensus-government modeling).

## Bills & Legislation ✅ LIVE (2026-04-16)

- **Primary source:** Drupal 9 view at `/bills-and-legislation` — single HTML table, one row per bill with typed `<time datetime="…">` elements in each stage column. Only 4 bills in current (7th Assembly, 1st Session) as of 2026-04.
- **Column vocabulary (Drupal `views-field-field-*`):** title, date-of-notice, first-reading, second-reading, reported (Standing Committee), reported-whole (Committee of the Whole), third-reading, date-of-assent.
- **No sponsor data** (consensus government, 22 non-partisan MLAs). Pipeline writes bills + events only.
- **Assembly/session absent from the HTML** — the Drupal view doesn't print it. CLI takes `--assembly N --session S` overrides; default = `7-1` (current as of 2026-04).
- **Drupal `?_format=json` is disabled** — returns 406 Not Acceptable with only `html` as supported format. Unlike Ontario, NU hasn't enabled the JSON serializer. HTML scrape is the only route.
- **Cost:** one HTTP GET for the whole current session.
- **Scanner module:** `services/scanner/src/legislative/nu_bills.py`.
- **CLI:** `ingest-nu-bills [--assembly N] [--session S]`.
- **Results on first run (7th Assembly, 1st Session):** 4 bills / 24 events / 0 sponsors (by design). All 4 are appropriation acts, all at Royal Assent.

## Hansard / Debates

- **Source URL(s):** https://www.assembly.nu.ca/hansard ; Legislative Library: library@assembly.nu.ca, 867-975-5132
- **Format:** Searchable HTML; "Blues" (unedited) available next morning.
- **Granularity:** Speaker, statement, date.
- **Speaker identification:** Name (all non-partisan).
- **Difficulty (1–5):** 2.
- **Notes:** Bilingual publication (Inuktitut + English). Records from 1999-04-01.

## Voting Records / Divisions

- **Source URL(s):** Hansard + Legislative Library proceedings
- **Format:** Summary/textual within Hansard.
- **Roll-call availability:** Unclear — **consensus government (no political parties, 22 non-partisan MLAs)** means partisan voting records don't exist in the traditional sense. Decisions often by consensus or acclamation.
- **Difficulty (1–5):** 4 (conceptual rather than technical difficulty).
- **Notes:** Schema design question: do we skip the votes table for NU, or model consensus/acclamation as a vote type? Recommend the latter for completeness. Contact Legislative Library to clarify formal division procedures.

## Committee Activity

- **Source URL(s):** https://www.assembly.nu.ca (Standing and Special Committees)
- **Format:** HTML committee pages; reports.
- **Data available:** Memberships, schedules, reports.
- **Overlap with existing scanner:** None.
- **Difficulty (1–5):** 3.
- **Notes:** Committees fulfill legislation review, policy exam, spending review. More procedural flexibility than Assembly floor.

## Existing third-party scrapers

- **opencivicdata/scrapers-ca:** NU scraper status — verify in repo; may lack vote coverage due to consensus model.
- Other: https://www.gov.nu.ca/ — general government, not legislative-specific open data.

## Status

- [x] Research complete
- [x] Schema (no new migration — no sponsor FK)
- [x] Ingestion prototyped
- [x] Production ingestion live (2026-04-16) — 7th Assembly, 1st Session, 4 bills
- [ ] Assembly/session auto-detection (currently hard-coded default via CLI flag)
- [x] **Hansard ingestion shipped (2026-05-16)** — `services/scanner/src/legislative/nu_hansard.py`, `ingest-nu-hansard` Click command, daily 21:15 UTC schedule. ~59 PDFs back to 2021-02-24. Parser handles bilingual `(interpretation)` markers + Inuktitut/English interleaving.
- [x] **6th Assembly roster shipped (2026-05-16)** — `services/scanner/src/legislative/nu_former_mlas.py`, `ingest-nu-former-mlas` Click command. 22 MLAs sourced from Wikipedia's `6th_Nunavut_Legislature` article; 8 matched existing 7th Assembly returners, 14 newly inserted with `wikipedia:nu-assembly:` source tag. Politician_terms rows seeded with assembly date span 2021-11-19 → 2025-09-22. Fuzzier name match (`Pitsiulaaq Brewster ⊇ Brewster`) avoids duplicating multi-word-surnamed people who returned.
- [x] **Hansard resolution lift (2026-05-16)**: 40% → 79% → **98.9% (93/94)** on the 20240531 smoke-test sitting. Path: (a) 6th Assembly roster ingester closed the 12-MLA gap; (b) token-based surname index made `Brewster` resolve against `Pitsiulaaq Brewster`; (c) first-name disambiguator (normalized `P.J.` ↔ `P. J.`) split P.J. Akeeagok from David Akeeagok. The 1/94 remainder is a presiding-officer turn deferred to `resolve-presiding-speakers --province NU` (roster TBD).
- [ ] Votes (consensus-government modeling question remains open)

## Research-handoff items (Hansard)

Per [overview.md](./overview.md) rule #5, NU Hansard scraper design is gated on user research. Specific questions to answer before any code is written:

- **Bilingual handling:** Hansard is published in Inuktitut + English. Are they served as separate pages (`/hansard/{date}-iu.html` and `/hansard/{date}-en.html`), one combined page with both languages interleaved, or one canonical English page with Inuktitut as a downloadable attachment? This decides whether `speeches` rows should carry a `language` column or store both as raw payload.
- **Inuktitut character encoding:** UTF-8 syllabics (ᐃᓄᒃᑎᑐᑦ) or transliterated roman? If syllabics, the embedding model (Qwen3) needs to handle them — worth a quick test before scheduling daily runs that fail silently on encoding errors.
- **URL pattern:** The dossier lists `assembly.nu.ca/hansard` as the index; the per-sitting URL pattern is unprobed. Likely Drupal 9 (same CMS as bills), so `/hansard/{slug}` per sitting, but needs confirmation. The bills page disabled `?_format=json` — Hansard probably did too, but test that probe.
- **Blues vs. final:** "Blues (unedited)" published next morning per the dossier. Are Blues at a different URL than the final (BC pattern)? If yes, the parser needs the same Blues→Final swap-in-place logic that `bc_hansard.py` already has.
- **Speaker attribution:** No partisan affiliation; 22 non-partisan MLAs. Is there a stable per-MLA slug or numeric ID anywhere in the Drupal markup we can stamp on `politicians.nu_assembly_slug` (new column, follow CLAUDE.md convention #1)? If only names, the Speaker resolver needs a date-windowed roster to disambiguate across assemblies.
