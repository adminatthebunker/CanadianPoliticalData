# Calgary — Municipal Data Research

> Standalone research dossier for the City of Calgary. Cross-cutting context lives in [`overview.md`](./overview.md). Calgary is the **eScribe family reference** — what's said here about the eScribe surface generalises to Edmonton, Ottawa, Mississauga, and Hamilton.

**Council:** Calgary City Council | **Website:** https://www.calgary.ca/council.html | **Seats:** 15 (Mayor + 14 councillors, ward-based) | **Next election:** 2025-10-20 (most recent)

**Status snapshot (2026-05-05):** ⏸️ **Parked — Calgary has no Hansard-equivalent corpus we can reach.** Roster live (15 rows). Migration `0046_municipal_meetings.sql` applied; eScribe scanner module + 7-stage Click chain wired and runnable (`services/scanner/src/legislative/{escribe,escribe_ingest,youtube_captions}.py`). **What works:** server-rendered upcoming-meetings ingest landed 3 meetings — proves the schema + scanner shape. **What's blocked / absent:**

- **No YouTube channel.** User confirmed (2026-05-05): Calgary does not maintain a YouTube channel for council proceedings — video lives only inside eScribe (`VideoStream.aspx?MeetingId=<guid>`). So the captions-as-Hansard fallback that works for cities with YouTube does not apply here.
- **eScribe past-meetings AJAX is opaque** to server-side callers. `MeetingsContent.aspx/PastMeetings` POST returns empty / hangs regardless of cookies / browser-like headers / exact MeetingType strings (probed 2026-05-05). Per-meeting agenda pages render empty placeholders populated by a second AJAX call.
- **Net:** without a verbatim transcript or a reliable past-meetings feed, Calgary's substantive municipal record is **eScribe video + minutes PDFs**, both of which need browser automation to extract. A speech-level corpus is not achievable on the current path.

**Promotion conditions:** (a) probe `data.calgary.ca` (Socrata) for a council-decisions or motions dataset republish — best low-friction option; (b) probe eScribe iCal / RSS surfaces; (c) accept Playwright / Camoufox investment to drive the AJAX endpoints + extract video-stream captions where present. Until at least one of those lands, Calgary stays parked. Pipeline scaffolding remains in place so promotion-day work is wiring a fetcher into the existing four-stage chain, not redesigning the schema.

---

## Bills / By-laws

- **Source URL(s):** https://publicaccess.calgary.ca/lldm01/livelink.exe?func=LLM.LegislativeServices&channel=PUBLIC (Open Text LiveLink LLDM — Calgary's bylaw repository); https://data.calgary.ca/?q=bylaw (Socrata search)
- **Format:** LLDM is an older Open Text content-management surface; bylaws are PDFs. Socrata may republish a bylaw index as a structured table.
- **Difficulty (1-5):** **3** via Socrata if a bylaw dataset exists; **4** for LLDM scrape.
- **Notes:** Calgary maintains thousands of bylaws across the city's history. Schema mapping per [`overview.md`](./overview.md).

## Hansard / Council Meeting Surface (eScribe)

- **Source URL(s):** https://pub-calgary.escribemeetings.com/ ; https://pub-calgary.escribemeetings.com/MeetingsCalendarView.aspx ; https://pub-calgary.escribemeetings.com/Meetings.aspx?Tab=All&IsPublic=true
- **Format:** eScribe SaaS (provider: OnBoard, formerly eScribe Software Ltd.). Server-rendered HTML with Syncfusion DateRangePicker + jQuery + a `Meeting` JS bundle. Cloudflare-fronted; polite UA returns 200 OK without challenge.
- **Granularity:** Per-meeting; per-meeting page exposes agenda + minutes + per-agenda-item motion text + per-item recorded vote tally + video link (typically YouTube).
- **Speaker identification:** Per-motion mover and seconder named (linked to councillor); debate speakers NOT identified in minutes (eScribe minutes are decision records, not transcripts). Video has councillors visible; auto-captions on YouTube are the only programmatic speech-level surface.
- **Difficulty (1-5):** **3** for the structured agenda + decisions + votes scrape; **3** for YouTube-captions if speech-level corpus is wanted.
- **Notes:** Calgary council meetings are streamed on **Council Live** (https://www.calgary.ca/council/live-stream.html) and archived on YouTube (@CityofCalgary). Auto-captions are accurate-ish but unreviewed.

## eScribe surface in detail (applies family-wide)

The eScribe HTML scaffolding (verified 2026-05-05 against Calgary; pattern observed identically on Edmonton / Ottawa / Mississauga / Hamilton):

- **Meeting list:** `Meetings.aspx?Tab=All&IsPublic=true` — filterable by date and meeting type (Council, Standing Policy Committee on X, etc.).
- **Calendar view:** `MeetingsCalendarView.aspx` — same data, calendar UI.
- **Per-meeting page:** typically `Meeting.aspx?Id=<guid>` — agenda HTML + downloadable PDFs (agenda, minutes), embedded video player, per-item motion + vote table.
- **CDN dependencies:** Syncfusion @ cdn.syncfusion.com; jQuery 3.4.1, moment.js 2.22.2, Bootstrap 4.4.1, FullCalendar 3.0.1 — all from public CDNs.
- **Robots:** only `Disallow: /` for `User-agent: PetalBot`; everything else allowed.
- **Action item before first ingest:** check whether eScribe exposes an OData / JSON endpoint backing the calendar view. Several US eScribe customers have been observed exposing `/api/odata/...`; Canadian deployments may or may not. If yes, that would lift the family from difficulty 3 to 2.

## Voting Records

- **Source URL(s):** Per-agenda-item recorded vote table in the eScribe meeting page.
- **Format:** Tally + sometimes per-councillor positions. Calgary's eScribe configuration appears to publish per-councillor positions (verified anecdotally; needs confirmation against a recent meeting).
- **Roll-call availability:** Per item where a recorded vote is requested.
- **Difficulty (1-5):** **3**.

## Committee Activity

- **Source URL(s):** Same eScribe instance covers Council + Standing Policy Committees (e.g. SPC on Community and Protective Services, Utilities and Corporate Services, etc.).
- **Format:** Identical to Council meetings.
- **Difficulty (1-5):** **3**.

## Open-data Socrata — secondary path

- Portal: https://data.calgary.ca/
- Backend: Socrata (same backend as Nova Scotia, New Brunswick, Edmonton).
- API base: `https://data.calgary.ca/resource/<dataset-id>.json` (per dataset) and `https://data.calgary.ca/api/catalog/v1` (catalog search).
- Useful as a *complement* to eScribe — not a replacement. Council-meeting decisions land in eScribe first; Socrata republishes derived data (attendance stats, etc.).

## Terms / Licensing

- Calgary Open Data is published under the **Open Government Licence — City of Calgary** — permissive, attribution required, derived from the Canadian provincial OGL family. Confirm at https://data.calgary.ca/stories/s/Open-Calgary-Terms-of-Use/u45n-7awa/.
- eScribe-published material (agendas, minutes, decisions): **municipal Crown copyright**. Civic transparency / non-commercial use widely accepted; commercial redistribution should be checked per-city.

## Rate limits / auth

- eScribe: Cloudflare-fronted, no observed rate limit on polite UAs. Honor `Cache-Control: private` (don't cache shared) and pace at 1-2 req/sec to avoid tripping CF heuristics.
- Socrata: Anonymous calls capped at ~1000/hour/IP without an app token; with a free token, ~10000/hour. Get a token before any meaningful scrape.

## Open questions (for the user before any code)

1. eScribe is five cities for the price of one. Is Calgary the right reference, or would Ottawa (larger council, ON jurisdiction overlap with existing scanner work) be a better pick?
2. Do we have an existing relationship with the Calgary Open Data team that could surface a structured by-law dataset on Socrata vs. discovering by enumeration?

## Status checklist

- [x] eScribe fingerprint confirmed — 2026-05-05
- [x] Robots.txt + Cloudflare front behaviour verified — 2026-05-05
- [ ] eScribe OData/JSON endpoint discovery (would lift difficulty 3 → 2)
- [ ] Sample meeting page parse to confirm motion + vote structure
- [ ] Socrata catalog enumeration for bylaw / decisions datasets
- [ ] Open Government Licence terms read
- [ ] User research-handoff: any contacts / hints
- [ ] First eScribe scraper module (post-handoff) — designed once, configured per-city
