# Ontario — Legislative Data Research

> Standalone research dossier for Ontario. Cross-cutting context (schema, scanner modules, probe hierarchy, research-handoff protocol) lives in [`overview.md`](./overview.md).

**Legislature:** Legislative Assembly of Ontario | **Website:** https://www.ola.org | **Seats:** 124 | **Next election:** 2030-04-11

**Status snapshot (2026-05-22):** ✅ **Bills + Hansard live** across Parliament 36 → 44 (1981 → present). Bills via ola.org HTML scrape (3,412 bills across P36-P44 from the `--all-sessions` walker, all events + sponsors). Hansard via `?_format=json` JSON node — name-based speaker resolution against politicians (no per-speaker slug anchors in ON markup), parens-name extraction handles presiding-officer attributions exactly. **947,256 speeches, 93.11% resolved to politicians** after the 2026-05-22 middle-initial-aware second pass on top of the 2026-05-21 date-windowed resolver. ✅ **Middle-initial disambiguator (2026-05-22):** investigation of the "1,982 still-ambiguous" residue left by the 2026-05-21 first-token rewrite established that **the ON politicians roster has no true duplicates** — the OLA roster is keyed by `ola_member_id` (1,992/1,993 ON politicians carry one, no collisions), and same-surname-same-era pairs like "Dave Cooke" (id 325, Windsor-Riverside, NDP) and "David R. Cooke" (id 477, Kitchener, Liberal) are confirmed via Wikipedia + the OLA member list to be two different MPPs who served simultaneously in P33-P34. Hansard explicitly disambiguates them by middle initial: "D. S. Cooke" / "David S. Cooke" (1,560 + 532 rows) for Dave, "D. R. Cooke" / "David R. Cooke" (422 + 4 rows) for David R. The fix was therefore a resolver pass, not a roster merge: new `resolve_on_speakers_middle_initial` in `services/scanner/src/legislative/on_hansard.py` extracts the middle initial from the speech's `full_name` (second whitespace-delimited token, first letter) and from the politician's `name` column (strip first_name prefix + last_name suffix, take first letter of the remainder), joins on exact middle-initial match + surname + politician-term date window, and attributes when exactly one contemporaneous MPP survives. First initial / first name is intentionally NOT constrained in this pass (the surname-only join already surfaces both Cooke MPPs; the middle initial does the rejection), which gives free nickname tolerance (Hansard "David S. Cooke" labels resolve to `Dave Cooke` without a Dave↔David name map). One politician-table edit was required to make the join symmetric: `Dave Cooke`'s `name` field was enriched from `Dave Cooke` to `Dave S. Cooke` (`ola_member_id` 325 unchanged) so the middle-initial extraction yields `S`. New pass attributed **+2,016 speeches** (450 D.R. Cooke + 1,566 D.S. Cooke), lifting from 92.89% to 93.11%; the Cooke split is now 4,139 rows to Dave / 422 to David R., matching their Hansard prominence (Dave was a long-serving House Leader / Minister; David R. was a single-term Kitchener Liberal). The new pass is wired as a chained second step inside the `resolve-on-speakers-dated` Click command, so the operator surface is unchanged. The previous parliament-keyed resolver attributed only 90/32,297 candidates (0.3%) because most `politician_terms` rows lacked the `ola.org:parliament-N` source tag *and* matched the speech's parliament number; the 2026-05-21 date-window CTE joins on `(pt.started_at <= spoken_at <= pt.ended_at)` against the 5,061 ON `politician_terms` rows (100% started_at, 95% ended_at coverage). A first-token disambiguator (extracted from `raw->'on_hansard'->>'full_name'`, accepting full first-name match, `'F.'`-style initials, or bare single-letter initials) is essential because ON historical Hansard uses initial-style speaker labels (`F. S. Miller`, `R. F. Nixon`) and surname+date alone is 100% ambiguous on the Frank/Gordon Miller, John/Robert Nixon, George/James Taylor (etc.) overlaps. The current residue (~65k rows) is dominated by role labels (`Interjection`, `Mr. Chairman`, `Clerk at the Table`, `An hon. member`, timestamps) which are not person-attributable by design. Pre-2008 bare-`The Speaker` rows (46,415 total) attribute via date-windowed lookup against the historical Speaker roster (Turner / Edighoffer / Warner / McLean / Stockwell / Carr / Curling / Brown / Peters / Levac / Arnott / Skelly, 32L-44L). ✅ **Speech-type honest-coverage classification (2026-05-21):** ON parser now emits `speech_type='group'` for `An hon. member` / `Some hon. members` / `Interjection` chorus turns (6,482 rows — previously untagged with `speaker_role IS NULL`) and `speech_type='staff'` for the Clerk family + `Sergeant-at-Arms` parliamentary-staff turns (3,033 rows across `The Clerk`, `The Clerk-at-the-Table`, `The Deputy Clerk`, `The Acting Clerk-at-the-Table`, `The Clerk of the Committee`, `The Acting Clerk of the Assembly`, `The Acting Table Clerk`, `The Sergeant-at-Arms`, plus the nested-parens `Wai Lam (William) Wong` variant) — mirrors the QC parser's `_GROUP_ROLES` / `_STAFF_ROLES` frozenset pattern; new `_ROLE_PATTERNS` entries normalise the staff and chorus variants at parse-time, existing rows backfilled in one transaction (9,515 total). Attribution % unchanged (these were never MPPs); honest-coverage signal corrected so search filters / coverage queries can exclude non-politician turns. Presiding-officer-of-the-Whole / Acting Chair / Deputy Chair family (rotating chairs) remains a separate, deferred cycle (no in-corpus chair-handover signal). Votes / committees not yet built.

---

## Bills & Legislation

- **Source URL(s):** https://www.ola.org/en/legislative-business/bills/current ; https://www.ola.org/en/legislative-business/bills/all
- **Format:** HTML web pages; no structured API. Per-bill PDFs available.
- **Fields captured upstream:** Bill number, title, status (reading stages), sponsoring MPP.
- **Terms/Licensing:** Crown copyright (Queen's Printer for Ontario). Non-commercial reproduction permitted with attribution. Legislative text freely reproducible.
- **Rate limits / auth:** None documented.
- **Difficulty (1–5):** 3.
- **Notes:** Bills indexed by Parliament and session. URL structure is predictable. No JSON/XML export at the URLs we ingest from.

## Hansard / Debates

- **Source URL(s):** https://www.ola.org/en/legislative-business/hansard-search ; https://www.ola.org/en/legislative-business/house-hansard-index
- **Format:** HTML searchable archive; no API.
- **Granularity:** Per-session daily transcripts (Hansard volumes).
- **Speaker identification:** By MPP name; searchable.
- **Difficulty (1–5):** 3.
- **Notes:** Full-text searchable from 1974-03-05 onward.

## Voting Records / Divisions

- **Source URL(s):** https://www.ola.org/en/legislative-business/house-documents/parliament-44/session-1 (Votes and Proceedings)
- **Format:** HTML Votes and Proceedings; also PDF downloads.
- **Roll-call availability:** Yes, from 43rd Parliament forward, with member names and votes.
- **Difficulty (1–5):** 3.
- **Notes:** Divisions embedded in daily Votes and Proceedings. Consistent URL structure by Parliament/session/date.

## Committee Activity

- **Source URL(s):** https://www.ola.org/en/legislative-business/committees ; https://www.ola.org/en/legislative-business/committees/documents
- **Format:** HTML transcripts; some committees publish CSV exports (e.g. Standing Committee on Finance and Economic Affairs).
- **Data available:** Memberships, meetings (transcripts by date), reports (PDF/HTML), transcripts (HTML).
- **Overlap with existing scanner:** None.
- **Difficulty (1–5):** 3.
- **Notes:** 9 Standing Committees. Transcripts include member remarks, votes, and staff lists.

## Existing third-party scrapers

- **opencivicdata/scrapers-ca:** `ca_on` module exists ([github.com/opencivicdata/scrapers-ca](https://github.com/opencivicdata/scrapers-ca)).
- **Open North Represent API** — reps only, not legislative activity.

## ★ Drupal JSON serializer (discovered 2026-04-15, after initial HTML pipeline shipped)

Every node on `www.ola.org` supports `?_format=json` — the Drupal core REST serializer. This turns the entire bills / sponsors / members graph into a queryable JSON API without any auth:

```
https://www.ola.org/en/legislative-business/bills/parliament-44/session-1/bill-104?_format=json
https://www.ola.org/en/node/9608366?_format=json          # sponsor node
https://www.ola.org/en/members/all/john-fraser?_format=json # member node
```

**Fields available on a bill node** (superset of what we scrape):

- `field_bill_number`, `field_long_title`, `field_short_title`, `field_current_status`
- `field_sponsor` → reference to a bill_sponsor node (which has `field_member` → member node, with `field_member_id` — a stable **integer ID** we can store on politicians for exact-match linking, same trick as BC's `lims_member_id`)
- `field_status_table` — same malformed HTML table we parse, but now arriving inside JSON (still needs the tr-split fix)
- `field_has_divisions` — boolean, signals whether vote roll-calls exist
- `field_debates` — array of Hansard debate node refs
- `field_acts`, `field_acts_affected` — ties into legislation graph
- `field_versions` — bill-text version history
- `field_type` → taxonomy term (government vs. private member's bill)
- `field_parliament`, `field_parliament_sessions`
- `field_latest_activity_date`

**Member node also exposes `field_member_id`** (integer, stable) plus riding, party, dates of service, gender, contact group, expense disclosure links.

**Why it matters going forward:**
- Richer data for free — divisions boolean, type taxonomy, acts-affected graph — that HTML scraping made awkward to get.
- Integer `field_member_id` enables exact sponsor→politician joins (same pattern as BC's LIMS `memberId`). Replace slug-fuzz resolution with a single-column FK.
- Likely applies to **Saskatchewan, Manitoba, PEI, NL** too if they're Drupal-backed — worth probing `?_format=json` on the first bill page of each as a fast triage before writing HTML scrapers. (Result of that probe pass on 2026-04-15: none of the four are Drupal. The serializer trick is Ontario-specific.)

**Not migrating the current ON pipeline** (102 bills, 595 events, sponsors all linked) because the HTML pipeline works and the data is already good. Switch to the JSON serializer when we:
  (a) backfill earlier ON Parliaments, or
  (b) want the divisions / acts-affected / versions data we skipped.

## Open issues

- **Historical ON sponsors** — only current-Parliament MPPs are in our politicians table, so any pre-2024 ON bill would name-match poorly. Not a problem at P44-S1 scope, but will be when we backfill.

## Status

- [x] Research complete
- [x] Schema drafted (0006 — shared across jurisdictions)
- [x] Ingestion prototyped (`ingest-on-bills` P44-S1: 102 bills, 595 events, 102 sponsors)
- [x] Production ingestion live (current session; backfill earlier Parliaments deferred)
- [x] Sponsor→politician resolver working (102/102 linked)
- [ ] JSON-serializer pipeline (optional rewrite; HTML pipeline works fine for current scope)
- [ ] Hansard
- [ ] Votes
- [ ] Committees

## Hansard pipeline ✅ LIVE (2026-04-24)

Probe pass on 2026-04-24 resolved every research question and the pipeline shipped same-day.

- **Endpoint:** `?_format=json` is enabled on Hansard pages (same Drupal serializer pattern as bills). Per-sitting JSON returns `node_type=hansard_document` with `body.value` carrying the full transcript HTML (~9–500 KB depending on sitting), plus structured `field_date`, `field_parliament`, `field_parliament_sessions`, `field_associated_bill_multi`, `field_pdf`, `field_html_upload`.
- **URL pattern:**
  - **Discovery (per session):** `/en/legislative-business/house-documents/parliament-{P}/session-{S}/` (HTML) — lists every sitting as `/{discovery}/{YYYY-MM-DD}/hansard`.
  - **Per-sitting transcript:** the same URL with `?_format=json` returns the JSON node above; the bare URL returns the rendered HTML.
  - Discovery extends back to parliament 29 (1971); per-sitting JSON works for the modern era unconditionally.
- **Speaker markup:** every speech is `<p class="speakerStart"><strong>{Honorific Name (optional role)}:</strong> {body}</p>`. Procedural notes use `<p class="procedure">` and are skipped. Confirmed shapes:
  - `Hon. Stephen Crawford:` / `Mr. Steve Clark:` / `Ms. Laurie Scott:` / `MPP Lisa Gretzky:`
  - `The Speaker (Hon. Donna Skelly):` — presiding officer with the actual speaker's name in parens
  - `The Acting Speaker (Mr. X):` / `The Deputy Speaker (Mr. X):` / `The Clerk of the Assembly (Mr. Trevor Day):`
  - Bare `The Speaker:` / `Madam Speaker:` / `Mr. Speaker:` (legacy / rare in modern era)
- **Speaker resolution:** name-based against `politicians WHERE province_territory='ON'` (no per-speaker `/members/<slug>` anchors in ON markup, so `politicians.ola_slug` is not in the FK chain for Hansard the way it is for bills). **Parens-name extraction** is the key trick: `The Speaker (Hon. Donna Skelly)` resolves to Donna Skelly directly via the parens content, sidestepping the date-windowed Speaker roster lookup that other jurisdictions need. Bare `The Speaker:` rows defer to `resolve-presiding-speakers --province ON` (SPEAKER_ROSTER seeded with current Speaker only — Tier-1 modern coverage).
- **Scanner module:** `services/scanner/src/legislative/on_hansard.py` (orchestrator) + `on_hansard_parse.py` (parser).
- **CLI:** `ingest-on-hansard` + `resolve-on-speakers` (both auto-detect current session via `current_session.py`).
- **Schedule:** packed into the 18:00 UTC ON slot — bills:00, fetch:05, parse:10, hansard:20, resolve:35, presiding:50.
- **First-run smoke (2025-04-14 sitting, opening day with Speaker election):** 18 speeches, 9 MPP speakers (100% resolved), 8 role-only Clerk turns (Trevor Day, not an MPP — leaves politician_id NULL), 1 Lieutenant Governor turn (also NULL by design). 0 parse errors.

**Bilingual content note (probed 2026-04-24):** The `/fr/...` URL pattern exists (`/fr/affaires-legislatives/documents-chambre/legislature-{P}/session-{S}/{YYYY-MM-DD}/journal-debats`) and returns HTTP 200 — but the body is **byte-identical** to the English URL. ON Hansard is published as a single bilingual transcript: francophone MPPs' (e.g. France Gélinas, Anthony Leardi, Guy Bourgouin) speeches appear in French interleaved with the English majority (~3% French in a typical sitting). So the EN ingest already captures everything; **per-speech language detection** (a small French-stopword heuristic in `on_hansard_parse.py`) tags each row as `language='en'` or `'fr'` for search filtering and embedding correctness. There is no separate French Hansard to ingest.

**Out of scope (followups):**
- Bill ↔ Hansard cross-references via `field_associated_bill_multi` — already captured in the JSON we fetch, persisted to `raw->'on_hansard'->'field_associated_bills'`, but not yet promoted to a normalised join table.

## Historical MPP roster ✅ LIVE (2026-04-26)

Probe pass on 2026-04-26 turned up a clean per-parliament roster URL pattern that exposes every MPP back to Confederation; backfill landed same-day.

- **Listing endpoint:** `https://www.ola.org/en/members/parliament-{N}` for N = 1..44. Single-page HTML table per parliament, ~120-130 members each, no pagination, no JS. The `/en/members/all` index page hosts the dropdown that drives this URL pattern (visible in the HTML as a `<select>` of every parliament + its date range). `?_format=json` on the listing returns 406 — JSON is per-member only.
- **Listing row shape:** `<a href="/en/members/all/{slug}">Last, First [Hon.]</a>` followed by a riding cell. Slug is `firstname-lastname` lowercased, even back to 1867 (William Anderson → `william-anderson`).
- **Per-member detail:** `/en/members/all/{slug}?_format=json` returns:
  - `field_member_id[0].value` — **stable integer** assigned once per MPP, never reused (Ted Arnott=2, former Premier Mike Harris=44, William Anderson=768, current MPP Mike Harris=7482). This is the upsert key.
  - `field_first_name`, `field_last_name`, `title`, `field_url_segment` — clean name fields.
  - `field_last_riding[0].url`, `field_last_party[0].target_id` — current/most-recent values only (no per-term party history).
  - `field_dates_of_service[0].target_id` — node ref to a separate "service stint" node (one per continuous span); dereference via `/node/{id}?_format=json` for `field_start_date` / `field_end_date` / `field_start_reason` / `field_end_reason`. Useful for date-window disambiguation; not required for the parliament-keyed resolver.
  - `field_parliament` — array of taxonomy term refs. The taxonomy term URL itself returns 404; ignore it. The (member, parliament) edges come from iterating the listings.
- **Same-name disambiguation:** ola.org assigns different slugs (e.g. `mike-harris` for the current Kitchener-Conestoga MPP, `michael-harris-44` for the former Premier of Nipissing). Slugs are bijective with `field_member_id`. No collision logic needed — the listings already return distinct slugs.
- **Coverage:** all 44 parliaments (1867-12-27 → present). Hansard HTML transcripts confirmed back to **Parliament 32 (1981-04-21)**.
- **Schema additions:** migration `0037_politicians_ola_member_id.sql` adds `politicians.ola_member_id INTEGER` with a UNIQUE partial index. Mirrors AB's `ab_assembly_mid` (TEXT, zero-padded) and MB's `mb_assembly_slug` (TEXT, derived).
- **Scanner module:** `services/scanner/src/legislative/on_former_mpps.py` (ingester) + `resolve_on_speakers_dated` in `on_hansard.py` (date-windowed + first-token disambiguated resolver as of 2026-05-21; was parliament-keyed pre-rewrite).
- **CLI:** `ingest-on-former-mpps` + `resolve-on-speakers-dated`.
- **Term source convention:** `politician_terms.source = 'ola.org:parliament-{N}'` (mirrors `assembly.ab.ca:legl-{N}`). The 2026-05-21 resolver rewrite no longer depends on this tag — it joins purely on `politician_terms.started_at`/`ended_at` against `speeches.spoken_at`, so the source tag is now an audit trail rather than a load-bearing FK. Same-surname-same-era overlaps (Frank/Gordon Miller, John/Robert Nixon, etc.) are disambiguated by matching the first initial / first token from `raw->'on_hansard'->>'full_name'` against `politicians.first_name`.
- **Parliament date map:** hard-coded in `on_former_mpps.PARLIAMENT_DATES` for N=1..44, sourced from the `/en/members/all` dropdown table (verified against per-page headers).
