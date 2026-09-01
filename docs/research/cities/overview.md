# Municipal Data Research — Cross-Cutting Overview

> Shared methodology and progress tracking for the **major-cities** legislative-data effort. Per-city dossiers live as siblings of this file in `docs/research/cities/`. The provincial / federal counterpart is one directory up at [`../overview.md`](../overview.md); read that first for the broader project context — this doc is the municipal-specific layer.

**Status:** First-pass research 2026-05-05; **Edmonton promoted and PILOT LIVE 2026-08-14** — the first municipal speech corpus (`speeches.level='municipal'`: ~10K rows from 19 meetings' CC1 stenography captions, 13/13 sitting members FK-resolved; meetings spine 2,936 rows 2011→present from Socrata). See [`edmonton.md`](./edmonton.md). Other nine cities remain research-only; municipal politicians are roster-only via Open North (571 rows / 108 councils).

**Last updated:** 2026-08-14

---

## ★ Cross-cutting lesson from the 2026-05-05 first-build attempt

**Major Canadian cities are seriously under-published on Hansard-equivalent surfaces compared to provincial / federal legislatures.** What looks at first glance like "five eScribe-fronted cities, one ingest pattern, easy win" turned out (under a real first-build pass against Calgary + Edmonton) to be substantially harder than provincial pipelines, for two structural reasons:

1. **There is no verbatim transcript at most cities.** Council proceedings are video-streamed and minutes (decision-only) are published, but a Hansard-style verbatim record either doesn't exist (Calgary, most ON cities) or exists only as a closed-caption derivative of the live webcast (Montréal — see [`montreal.md`](./montreal.md), the standout exception). The captions-as-Hansard fallback only works for cities with **(a) a public YouTube channel** for council and **(b) auto-caption availability on those videos**. Calgary fails (a) — its video lives only inside eScribe and so isn't reachable via yt-dlp. Edmonton apparently passes (a) but the correct channel handle still needs research. Most other cities are unverified.
2. **eScribe's "structured data" surface is more JS-rendered than provincial scrapers needed to deal with.** The past-meetings list, per-meeting agenda items, motion text, and recorded vote tables all flow through ASP.NET PageMethod AJAX endpoints (`MeetingsContent.aspx/PastMeetings`, `MeetingsCalendarView.aspx/GetCalendarMeetings`, `GetAgendaItemHistoryView`, `GetLegislationItemView`) that return empty / hang to non-browser callers regardless of cookies, headers, or referrer. A polite-UA HTTP scrape gets only the small server-rendered upcoming-meetings shell. **eScribe difficulty re-rated 3 → 4** as a result.

**What this means for the broader cities workstream:** the original tier-1 priority ordering held that the eScribe-family cities (Calgary, Edmonton, Ottawa, Mississauga, Hamilton) would be the easy second tranche after the Montréal captions reference. **That assumption is wrong.** The realistic ordering is:

1. **Montréal** stays #1 (captions on CKAN — proven path).
2. **Toronto** stays #2 (CKAN structured-decisions — proven path).
3. **Vancouver** moves up (Opendatasoft v2.1 — also a structured-data path, untested but in the same low-friction family).
4. **eScribe family slips to a later tranche** — gated on either Playwright/Camoufox investment, or per-city open-data portal probes (`data.calgary.ca`, `data.edmonton.ca`, `open.ottawa.ca`) finding republished decisions feeds. Edmonton specifically has a tractable YouTube path that Calgary lacks; expect the family to fragment rather than ship as a single unit.
5. **Winnipeg / Québec** unchanged (last; bespoke).

The schema scaffolding (migration `0046_municipal_meetings.sql`, scanner modules `escribe.py` / `escribe_ingest.py` / `youtube_captions.py`, 7 Click commands) shipped in the first-build attempt **stands** — those are correct designs and the work is forward-portable to whatever path lands first. Promotion-day work for any one city is wiring a fetcher into the existing four-stage chain.

---

## Why a separate municipal layer

Municipal proceedings don't map cleanly onto the four-layer (bills / Hansard / votes / committees) provincial model. The substantive equivalents:

| Provincial layer | Municipal equivalent |
|---|---|
| Bills | **By-laws** (legislation enacted by council) + **motions** / decision items on agendas |
| Hansard | **Council and committee meeting minutes** (rarely verbatim) + **meeting video** with captions or transcripts where available |
| Votes | **Recorded council votes** on agenda items — where published, the "x in favour, y opposed" tally with per-councillor positions sometimes named, sometimes not |
| Committees | **Standing and ad-hoc committees** (almost universal); **boards and commissions** (varies wildly) |

The schema decision (whether to overload the provincial tables with `level='municipal'` + a new `municipality` discriminator, or to introduce parallel `municipal_*` tables) is **deferred** until at least one city pipeline is built end-to-end. Lean towards overloading — the project's strong precedent (CLAUDE.md convention #2) is one discriminated table per concept, not per-jurisdiction tables. The first hard test of that bias is likely Montréal (see below).

## Tier-1 cities (this round)

Ten cities, ranked by population × civic salience. The ordering also tries to give the eventual scanner one or two early wins:

| # | City | Pop. (≈) | Province | Council | System fingerprint | Hansard-equiv difficulty (1-5) |
|---|---|---:|---|---:|---|---:|
| 1 | Toronto | 2.79M | ON | 26 | TMMIS (custom, Akamai-walled) **+ open.toronto.ca CKAN** | **2** via CKAN |
| 2 | Montréal | 1.76M | QC | 65 | GDD (custom, FR primary) **+ donnees.montreal.ca CKAN — closed-caption ZIPs** | **2** via captions CKAN |
| 3 | Vancouver | 0.66M | BC | 11 | bespoke ASP.NET on `council.vancouver.ca` (Cloudflare-walled) **+ opendata.vancouver.ca Opendatasoft v2.1** | **3** via Opendatasoft |
| 4 | Calgary | 1.31M | AB | 15 | **eScribe** (`pub-calgary.escribemeetings.com`) | **3** |
| 5 | Edmonton | 1.06M | AB | 13 | **eScribe** (`pub-edmonton.escribemeetings.com`) | **3** |
| 6 | Ottawa | 0.96M | ON | 25 | **eScribe** (`pub-ottawa.escribemeetings.com`) | **3** |
| 7 | Mississauga | 0.72M | ON | 12 | **eScribe** (`pub-mississauga.escribemeetings.com`) | **3** |
| 8 | Winnipeg | 0.75M | MB | 16 | **DMIS** (`dmis.winnipeg.ca`, custom) | **3-4** (needs probe) |
| 9 | Québec | 0.55M | QC | 22 | bespoke IIS/ASP.NET on `ville.quebec.qc.ca` | **3-4** |
| 10 | Hamilton | 0.57M | ON | 16 | **eScribe** (`pub-hamilton.escribemeetings.com`) | **3** |

Tier 2 (post-tier-1 fast follow): Brampton, Surrey, Halifax, London (ON), Laval, Markham, Vaughan, Gatineau, Saskatoon, Longueuil. These are **not researched yet** — listed here so we don't lose them when promoting the workstream.

## System-fingerprint takeaways

The first-pass probe (2026-05-05) clusters tier-1 into three families. Pipeline investment scales by family, not by city:

### Family A — Open-data API (CKAN / Opendatasoft)

The cleanest path. Toronto, Montréal, and Vancouver all maintain open-data portals on the **same standard backends used by federal / provincial open-data** (CKAN at federal data.canada.ca and Halifax; Opendatasoft at... very few peers). For these three cities the official agenda system can stay walled — we don't need it. The dataset surface is what matters:

- **Toronto** — `ckan0.cf.opendata.inter.prod-toronto.ca` (CKAN with CloudFront in front of it). Confirmed: **15 council-meeting datasets** including `members-of-toronto-city-council-meeting-attendance`, `city-council-and-committees-meeting-schedule-reports`, `council-and-standing-committee-meeting-statistics`. Likely also a motions/decisions dataset to confirm in the per-city dossier.
- **Montréal** — `donnees.montreal.ca` (CKAN). **16 conseil-municipal datasets** including the `sous-titrage-conseil-municipal` archive (per-meeting closed-caption ZIP files from the live webcast, 2018+). Caption files are explicitly NOT a certified verbatim record but are the closest municipal Hansard analog any Canadian city publishes. Also `calendrier-seances-...`, `profils-participants-questions-conseil-municipal`, contracts/subsidies-by-decision datasets.
- **Vancouver** — `opendata.vancouver.ca` (Opendatasoft v2.1, OAuth-free, `x-ratelimit-limit: 15000/day`). 196 datasets in total; a council-specific subset needs targeted enumeration in the per-city dossier — the keyword "council" matches non-meeting datasets too.

This family is the **municipal NS / NB analog** — a Socrata-equivalent API tier. Difficulty 2 for all three.

### Family B — eScribe (single SaaS, five cities)

Five tier-1 cities — **Calgary, Edmonton, Ottawa, Mississauga, Hamilton** — host their meeting agendas on `pub-<city>.escribemeetings.com`, an eScribe SaaS instance. Common HTML scaffolding (Syncfusion DateRangePicker, `Meeting` JS bundle, `MeetingsCalendarView.aspx`, `Meetings.aspx?Tab=All&IsPublic=true`); single-PetalBot robots.txt; Cloudflare in front but no challenge for normal user agents. **One scraper module covers all five.**

> **★ 2026-08-14 correction (Edmonton probes; likely generalizes):** the eScribe opacity is **listing-only**. Per-meeting detail pages are fully **server-rendered** — `Meeting.aspx?Id=<uuid>&Agenda=PostMinutes` returns complete minutes HTML (MovedBy/SecondedBy/MotionText markup) to plain curl, and `filestream.ashx?DocumentId=<n>` serves attachment PDFs unauthenticated. The blocker reduces to "where do I get the meeting UUIDs" — and any city that republishes its eScribe export on an open-data portal (Edmonton: full Socrata relational export incl. per-councillor roll-call votes) hands them over for free. Before writing off any eScribe city, check its open-data portal for a meetings/motions dataset first; Calgary (`data.calgary.ca`), Ottawa (`open.ottawa.ca`), Hamilton, Mississauga re-probe pending.

**Difficulty re-rated to 4 (2026-05-05 first-build attempt).** A pipeline scaffold (Calgary + Edmonton, migration `0046_municipal_meetings.sql` + `services/scanner/src/legislative/{escribe,escribe_ingest,youtube_captions}.py` + 7 Click commands) confirmed the eScribe surface is **more JS-rendered than initial probing suggested**: the `MeetingsContent.aspx/PastMeetings` AJAX endpoint that backs the past-meetings list returns empty / timeouts to non-browser callers regardless of cookie state, exact MeetingType string, or browser-like headers; per-meeting agenda pages render template placeholders that get populated via a *second* AJAX call to `MeetingsCalendarView.aspx/GetAgendaItemHistoryView`. Edmonton's calendar is even sparser inline than Calgary's (FullCalendar-only, zero rendered meeting rows in the static HTML). **First-build deliverable is therefore the scaffold, not live data.** Live data needs one of: (a) Playwright / Camoufox browser automation against the AJAX endpoints, or (b) an alternate ingest path via the cities' Socrata / CKAN open-data portals (`data.calgary.ca`, `data.edmonton.ca`, `open.ottawa.ca`) — both untested as of 2026-05-05.

eScribe's data shape (per a quick read of the Calgary HTML):

- Meeting list paged by date range, server-rendered.
- Per-meeting page exposes: agenda PDF, minutes PDF (post-meeting), attached items, video link (often YouTube embed or eScribe's own player).
- Per-agenda-item the system stores motion text and recorded vote tallies — the tally is sometimes per-councillor, depending on the city's eScribe configuration.

**Action item before the first eScribe ingest:** confirm whether eScribe exposes a JSON / OData endpoint for the meeting list and per-meeting items. Several eScribe customers in the US have been observed exposing `/api/odata/...` paths; Canadian deployments may or may not. If yes, that lifts the family from difficulty 3 to 2. If no, server-rendered HTML scrape is the floor.

### Family C — bespoke / older custom systems

The largest cities and the older deployments:

- **Toronto TMMIS** — Akamai-walled (403 to all non-browser UAs). Bypassable via the open.toronto.ca CKAN path above; the TMMIS scrape track is only worth investing in if we hit a CKAN dataset gap.
- **Vancouver `council.vancouver.ca`** — Cloudflare bot challenge. Same pattern: skip in favour of the Opendatasoft v2.1 API.
- **Montréal GDD (`ville.montreal.qc.ca/sel/sypre-consultation/`)** — returned a Cloudflare 520 on probe; this is the system that actually produces the decisions / contracts / motions data, but again the CKAN republish path is preferred.
- **Winnipeg DMIS (`dmis.winnipeg.ca`)** — connection failure on first probe; needs a re-probe pass with a real browser to confirm whether it's down, IP-blocked, or fronted by something we missed. Likely an older ASP.NET stack (Volterra ADC + AWS ALB combo seen on `winnipeg.ca`).
- **Québec city (`ville.quebec.qc.ca`)** — IIS/ASP.NET; many guessed paths 403/404, but `/apropos/gouvernance/conseil-municipal/seances/direct.aspx` (live-stream page) returns 200. The séance archive page is somewhere in the same tree but the path needs to be discovered via the homepage navigation, not guessed.

## Probe-hierarchy adaptation for cities

Building on the project-wide hierarchy in [`../overview.md`](../overview.md), the **municipal**-specific ordering:

1. **Open data portal first** — CKAN / Opendatasoft / Socrata republish of meeting metadata. Bypasses agenda-system WAFs entirely. Cities running the largest open-data portals tend to publish the most council data here.
2. **Meeting management SaaS fingerprint** — eScribe (`pub-*.escribemeetings.com`), iCompass / Civica (`*.icompasstech.com`, `*.civicaeris.com`), Granicus (`*.granicus.com`), CivicWeb (`*.civicweb.net`). All of these are predictable to scrape because every customer gets the same HTML scaffolding.
3. **City clerk / decisions subdomain** — `secretariat.toronto.ca`, `clerk.winnipeg.ca`, `app.toronto.ca/tmmis`, etc. Custom systems but with stable URL shapes. Often Akamai- or Cloudflare-fronted; expect 403s on bot UAs.
4. **YouTube / Vimeo channel + caption file** — even when no transcript is published as a structured artifact, captions are commonly available on the city's official video channel. Caption text is the cheapest-quality municipal "Hansard" available where nothing else exists. Note Crown copyright / municipal-licence implications before redistribution.
5. **HTML scrape of agenda PDFs** — only after 1–4. PDF parsing investment is the same as for SK / AB Hansard.

## Schema implications (deferred decisions)

These haven't been settled — they're for the *first eScribe pipeline* design session, not now:

- **Where does the city ID live on `politicians`?** Today only `source_id = opennorth:<council-slug>:<person-slug>` ties a councillor to a city. A first-class `municipality_slug` column on `politicians` (or `politician_terms`) is likely needed once we have a second source per councillor — same logic that drove `openparliament_slug`, `ola_slug`, etc. (CLAUDE.md convention #1).
- **`municipalities` lookup table?** A `municipalities (slug, name, name_fr, province_territory, escribe_subdomain, opendata_endpoint, ...)` table would let scanner modules dispatch by slug and would surface the city as a first-class object on the frontend. Not strictly necessary if we store the city in `politicians.constituency_name` only, but the latter is what Open North already does and it's awkward (constituency = ward, not city).
- **Speeches discriminator.** `speeches.level='municipal'` plus `speeches.province_territory` is enough to qualify a row, but cities within a province need their own discriminator. Probably `speeches.municipality_slug` (nullable, set only when `level='municipal'`).
- **By-laws as bills?** Reuse `bills` with `level='municipal'`, or new `bylaws` table? Crucial for whether municipal data joins the existing federal/provincial search surface or stays siloed. **Bias: reuse, with `bills.level='municipal'` and `bills.bill_type='bylaw'`.**

## Research-handoff status

Per the project rule (CLAUDE.md convention #5; `feedback_research_handoff.md`), the research-handoff applies to **provincial** pipelines explicitly. For cities the user has authorised "feel free to do the first round of probes too" (2026-05-05) — so the dossiers below capture findings from agent-led probing, **not** user-led research. If a city is promoted to a build, the user should be given the dossier and a chance to add findings before any scraper code is written.

## Known blockers (cross-city)

- **Akamai / Cloudflare bot challenges on the largest cities' agenda systems.** Toronto TMMIS and Vancouver council.vancouver.ca both 403 on non-browser UAs. Mitigated by the open-data portals on those same cities; only becomes a hard blocker if a needed dataset isn't republished.
- **Crown copyright + municipal licensing.** Each city's open-data licence needs reading before redistribution in the public dump (`scripts/make-public-dump.sh`). Toronto, Montréal, Vancouver, Calgary, and Edmonton all use Open Government Licence variants (Canada-Toronto, etc.); smaller cities are inconsistent. Per-city dossier captures this.
- **Captions ≠ verbatim minutes.** Montréal's `sous-titrage` is real-time stenography with explicit avertissement that no post-broadcast correction is performed. For semantic-search use this is fine; for direct quotation in a report it's a footnote-required source. The reports-worker will need to know the difference (potentially a new `speeches.transcript_quality` field).

## Coverage matrix

| City | By-laws | Council "Hansard" | Council votes | Committees | Open-data API |
|---|---|---|---|---|---|
| Toronto | CKAN bylaw dataset (likely; confirm) | TMMIS minutes (Akamai-walled) — CKAN attendance ✓ | TMMIS recorded votes (Akamai-walled) | TMMIS committee mtg list (Akamai); CKAN attendance ✓ | CKAN — 15 council datasets ✓ |
| Montréal | CKAN bylaws — confirm slug | **CKAN sous-titrage ZIPs (real-time captions, 2018+)** | CKAN motion-vote dataset — confirm | CKAN — confirm | CKAN — 16 council datasets ✓ |
| Vancouver | likely on Opendatasoft | minutes via council.vancouver.ca (Cloudflare-walled) | likely Opendatasoft | likely Opendatasoft | Opendatasoft v2.1 ✓ |
| Calgary | eScribe agenda items | eScribe minutes PDF + YouTube w/ captions | eScribe per-item tally | eScribe meeting list | partial (open.calgary.ca to confirm) |
| Edmonton | Socrata motions (2011→) ✓ | **✓ LIVE: YouTube CC1 captions (2022→, pilot)** + eScribe minutes HTML | **Socrata per-councillor roll-call ✓ (373K rows, ingest pending)** | Socrata + same caption pipeline ✓ | Socrata full eScribe export ✓ |
| Ottawa | eScribe | eScribe + YouTube | eScribe | eScribe | partial (open.ottawa.ca) |
| Mississauga | eScribe | eScribe + YouTube | eScribe | eScribe | partial (data.mississauga.ca) |
| Winnipeg | DMIS (probe) | DMIS minutes (probe) | DMIS (probe) | DMIS (probe) | data.winnipeg.ca (Socrata, confirm) |
| Québec | bespoke IIS | bespoke + live-stream archive | bespoke | bespoke | donneesouvertes.ville.quebec.qc.ca (confirm) |
| Hamilton | eScribe | eScribe + YouTube | eScribe | eScribe | open.hamilton.ca (CKAN, confirm) |

Difficulty assignment: **2** = open-data API only (Toronto, Montréal); **2-3** = open-data API supplemented by eScribe scrape (Calgary, Edmonton, Ottawa, Mississauga, Hamilton); **3-4** = bespoke + open-data combo (Vancouver, Québec); **3-4 → confirm** = unprobed (Winnipeg).

## Priority ordering (within the cities tier) — updated 2026-05-05

When the *Later — Major municipal councils* horizon is eventually promoted to a build, the order — revised after the Calgary + Edmonton scaffold attempt — is:

1. **Montréal** — closed-caption corpus on CKAN is the largest verbatim-quality municipal-Hansard source in Canada. Exercises the speeches/bilingual seams of the existing pipeline. **Reference implementation.**
2. **Toronto** — CKAN attendance + decisions data lights up council-member activity surfaces immediately. Highest civic impact per row, all via a structured-data path.
3. **Vancouver** — Opendatasoft v2.1 is a structured-data path; a new adapter is the only new code. Same difficulty class as Toronto.
4. **Edmonton — ✅ PROMOTED + PILOT LIVE 2026-08-14** (user call; leapfrogged Montréal/Toronto/Vancouver). Two-layer build: Socrata structured spine + YouTube CC1 stenography captions. See [`edmonton.md`](./edmonton.md) for the full architecture and remaining work (backfill, votes ingest, pre-2022 ASR).
5. **Calgary / Ottawa / Mississauga / Hamilton (eScribe family)** — parked. No clean path until either (a) the cities' open-data portals are confirmed to republish council decisions / motions metadata, or (b) we accept Playwright / Camoufox investment to drive the eScribe AJAX endpoints. Calgary specifically has no YouTube channel for council, so it's worse off than its eScribe siblings.
6. **Winnipeg / Québec** — last; bespoke systems.

## Editing convention

Same as provincial dossiers ([`../README.md`](../README.md) "Editing convention"): when you complete or change something for a city, update its file's "Status" snapshot and the row in the Coverage matrix above. One fact in one file — cross-cutting findings live here, per-city findings live in the dossier.
