# Toronto — Municipal Data Research

> Standalone research dossier for the City of Toronto. Cross-cutting context (probe hierarchy, schema implications, family fingerprints) lives in [`overview.md`](./overview.md).

**Council:** City of Toronto Council | **Website:** https://www.toronto.ca/city-government/council/ | **Seats:** 26 (mayor + 25 councillors, ward-based) | **Next election:** 2026-10-26

**Status snapshot (2026-05-05):** 🚧 **Research only.** Roster live (5 rows in `politicians` via Open North; full 26-seat ingest pending). No speeches, no bylaws, no votes ingested. **Open-data CKAN portal is the recommended ingest path** — it bypasses the Akamai-walled TMMIS agenda system entirely and exposes 15 council-meeting datasets including per-councillor attendance.

---

## Bills / By-laws

- **Source URL(s):** https://www.toronto.ca/legdocs/bylaws/ (HTML index by year, PDF body); https://open.toronto.ca/dataset/?q=bylaw (CKAN open-data search)
- **Format:** Year-indexed HTML page → per-bylaw PDF for the body. CKAN may republish as structured CSV/JSON; needs targeted enumeration.
- **Granularity:** Per-bylaw with passing date and council-meeting reference.
- **Difficulty (1-5):** **3** (HTML scrape) or **2** if a CKAN bylaw dataset is confirmed.
- **Notes:** Toronto council enacts ~700–900 bylaws / year. The decision data lives upstream in TMMIS; bylaw HTML is essentially the published-output surface. Schema mapping: `bills.level='municipal'`, `bills.bill_type='bylaw'`, `bills.province_territory='ON'`, plus a `municipality_slug` discriminator (see [`overview.md`](./overview.md) § Schema implications).

## Hansard / Council "minutes"

- **Source URL(s):** https://secure.toronto.ca/council/agendas-meeting-schedule.do (TMMIS, **Akamai-walled, 403 to non-browser UAs**); https://app.toronto.ca/tmmis/ (TMMIS root); CKAN republishes some derived data.
- **Format:** TMMIS publishes **per-meeting agenda + decisions**, NOT verbatim transcripts. Council meetings are video-streamed at https://www.youtube.com/@cityoftoronto and YouTube auto-captions are the closest thing to a transcript Toronto produces.
- **Granularity:** Per-meeting agenda item; per-item motion text and recorded vote.
- **Speaker identification:** Decisions name the moving / seconding councillor; motion mover/seconder named; debate speakers NOT identified anywhere in TMMIS — only video shows who said what.
- **Difficulty (1-5):** **5** for TMMIS direct (Akamai); **3** for YouTube-captions fallback if redistribution rights work; **2** for the structured decision text via CKAN.
- **Notes:** **Toronto does not publish a Hansard-equivalent verbatim transcript.** What it publishes are (a) decision documents, (b) recorded votes, (c) live + archived video. The semantic-search corpus would have to be built from YouTube captions if we want speech-level granularity. Otherwise, the ingestion focus shifts to *decisions and votes*, not transcripts.

## Voting Records / Divisions

- **Source URL(s):** TMMIS per-item vote breakdown (Akamai-walled); attendance stats on CKAN (https://open.toronto.ca/dataset/members-of-toronto-city-council-meeting-attendance/)
- **Format:** TMMIS exposes recorded-vote tallies inline on each agenda item; CKAN attendance dataset gives per-councillor present/absent across meetings (NOT vote positions).
- **Roll-call availability:** Yes when recorded vote is requested; otherwise voice-only.
- **Difficulty (1-5):** **3** via TMMIS scrape if Akamai-bypassable; **2** if CKAN exposes a vote dataset (search `package_search?q=vote` to confirm).
- **Notes:** Toronto records named votes for every item (current procedure as of the 2022 council reform); per-item position-by-councillor is in TMMIS. Schema: `votes` + `vote_positions`, discriminated `level='municipal'`. NB: many items are decided unanimously by voice; `vote_type='consensus'` (NT-pattern) covers those.

## Committee Activity

- **Source URL(s):** TMMIS committee schedule (Akamai-walled); CKAN `city-council-and-committees-meeting-schedule-reports`.
- **Format:** Standing committees: Executive, Audit, Budget, Civic Appointments, Economic and Community Development, Infrastructure and Environment, Planning and Housing, etc. Each runs on its own TMMIS surface mirroring Council.
- **Difficulty (1-5):** Same as Council — **5 / 3 / 2** by route.

## Open-data CKAN — recommended path

Confirmed reachable (2026-05-05 probe):

- Portal: https://open.toronto.ca/
- CKAN API base: `https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action/`
- Probe of `package_search?q=council+meetings` → **15 datasets**, including:
  - `city-council-and-committees-meeting-schedule-reports`
  - `members-of-toronto-city-council-meeting-attendance`
  - `council-and-standing-committee-meeting-statistics`
  - 12 more — full enumeration is a build-time task, not a research-time one.
- Plus likely (need to confirm): bylaw text dataset, decisions dataset, recorded-votes dataset.

CloudFront in front of the CKAN host (`X-Cache: Miss from cloudfront`); responds to non-browser UAs with no challenge. **This is the path to invest in.** The TMMIS scrape is only worth the Playwright / Camoufox investment if a critical dataset turns out to be missing from CKAN.

## Terms / Licensing

- Toronto's open data is published under the **City of Toronto Open Data Licence** — permissive, attribution required, redistribution allowed for commercial and non-commercial use. Confirm at https://open.toronto.ca/open-data-license/ before first ingest.
- TMMIS-published material (bylaws, decision documents, minutes) is municipal Crown copyright; transparency / non-commercial use widely accepted.

## Rate limits / auth

- CKAN endpoint has no documented per-IP rate limit (CloudFront cache absorbs most calls); honor `Cache-Control` and back off on 429.
- TMMIS Akamai threshold is unknown — every probe so far returns 403. Don't budget against it; treat as "blocked" and use CKAN.

## Open questions (for the user before any code)

1. Is per-councillor *speech* attribution important enough to invest in YouTube-caption ingestion? If yes, that's the only path for a Hansard-equivalent corpus.
2. Is there an existing relationship with Toronto's Open Data team that could surface a Council Decisions structured dataset feed (vs. discovering it via `package_search`)?
3. Bylaws as `bills` (overload existing table) or as a new `bylaws` table? (See [`overview.md`](./overview.md) § Schema implications.)

## Status checklist

- [x] System fingerprint (CKAN + Akamai-walled TMMIS) — 2026-05-05
- [x] CKAN council-meeting dataset count confirmed (15) — 2026-05-05
- [ ] Full CKAN dataset enumeration (bylaws, decisions, votes, committees)
- [ ] Open Data Licence terms read end-to-end
- [ ] User research-handoff: any known datasets / contacts / endpoint hints
- [ ] Schema-design session for `municipality_slug` + `level='municipal'` overload
- [ ] First scraper module (post-handoff)
