# Vancouver — Municipal Data Research

> Standalone research dossier for the City of Vancouver. Cross-cutting context lives in [`overview.md`](./overview.md).

**Council:** Vancouver City Council | **Website:** https://vancouver.ca/ | **Seats:** 11 (Mayor + 10 councillors, at-large) | **Next election:** 2026-10-17

**Status snapshot (2026-05-05):** 🚧 **Research only.** Roster live (5 rows; full ingest pending). The official council site (`council.vancouver.ca`) is **Cloudflare bot-challenged**; the recommended path is the city's **Opendatasoft v2.1 portal** at `opendata.vancouver.ca`, which is the only Opendatasoft deployment among tier-1 cities (different backend from Toronto / Montréal CKAN).

---

## Bills / By-laws

- **Source URL(s):** https://vancouver.ca/your-government/bylaws.aspx (HTML, behind Cloudflare); https://opendata.vancouver.ca/explore/?q=bylaw
- **Format:** Per-bylaw HTML on the council site (challenge-walled); Opendatasoft may republish.
- **Difficulty (1-5):** **3** via Opendatasoft if a bylaw dataset exists; **5** for direct council.vancouver.ca scrape (Cloudflare challenge).
- **Notes:** Vancouver bylaws number into the tens of thousands across the city's history; the active set is smaller. Schema mapping per [`overview.md`](./overview.md) — `bills.bill_type='bylaw'`, `level='municipal'`, `province_territory='BC'`.

## Hansard / Council Minutes

- **Source URL(s):** https://council.vancouver.ca/ (calendar of meetings, **403 with cf-mitigated: challenge** to bot UAs); https://vancouver.ca/your-government/council-meeting-archive.aspx (302 → 404 page); https://www.youtube.com/@CityofVancouver (live + archived video).
- **Format:** Council site publishes per-meeting agenda + minutes (PDF) + video. **No verbatim transcript.** YouTube auto-captions are the only speech-level surface.
- **Granularity:** Per-meeting agenda + minutes. Minutes are decisions-only, NOT verbatim.
- **Speaker identification:** Mover / seconder named on motions; debate speakers not identified except on video.
- **Difficulty (1-5):** **5** for `council.vancouver.ca` direct; **3** for YouTube-captions fallback; **2-3** for an Opendatasoft minutes-metadata dataset if one exists.
- **Notes:** Vancouver's bot-challenge layer is **the same Cloudflare protection seen in YT/PE** (cf-mitigated: challenge in headers, content-security-policy with Cloudflare nonces, accept-ch headers requesting bitness/arch/etc.). Browser automation (Playwright / Camoufox) would defeat it; the project's existing position on those (per `docs/timeline.md` § Later, q5.3) is "deferred until alternative routes fail." Vancouver has an alternative — Opendatasoft — so don't invest in browser automation here.

## Voting Records

- **Source URL(s):** Council minutes name vote totals where requested; per-councillor positions sometimes named in minutes, sometimes not.
- **Format:** Inline in PDF minutes.
- **Difficulty (1-5):** **3-4** depending on minutes structure consistency.

## Committee Activity

- **Source URL(s):** Standing committee schedule on council.vancouver.ca (Cloudflare-walled).
- **Notes:** Vancouver runs Standing Committees on City Finance and Services, Policy and Strategic Priorities, Persons with Disabilities, etc. Same Cloudflare problem; same Opendatasoft fallback.

## Open-data Opendatasoft — recommended path

- Portal: https://opendata.vancouver.ca/
- API base (v2.1 OpenData REST): `https://opendata.vancouver.ca/api/explore/v2.1/catalog/datasets`
- **Different backend from CKAN.** Opendatasoft uses an OData-flavoured REST API: `?where=`, `?select=`, `?refine=field:value`, `?q=keyword`, etc.
- Headers seen on probe: `x-ratelimit-limit: 15000` per day, `x-ratelimit-remaining: 14999`. Generous.
- Total catalog: 196 datasets (probe 2026-05-05). A targeted council-meeting search needs `where=search(metas.default.title, "council")` + likely a `theme=Government` filter — the bare `q=council` returned non-meeting datasets first.
- **Action item:** the per-city dossier should enumerate the council-relevant datasets here. The first probe pass didn't return them on a naive query; it's a needle-in-haystack search rather than a CKAN-style "list all that match."

## Terms / Licensing

- Vancouver Open Data is published under the **Vancouver Open Data Licence** — permissive, attribution required, includes a clause prohibiting use that disparages the city. Confirm at https://opendata.vancouver.ca/pages/licence/ before first ingest.
- Council-site (Cloudflare-walled) content is municipal Crown copyright; less-permissive defaults but the data is functionally public.

## Rate limits / auth

- Opendatasoft: 15,000 requests / IP / day, hard cap. Each export endpoint returns either JSON page (limit ~100) or a pre-signed CSV/Parquet for bulk.
- council.vancouver.ca: bot-challenged, effective limit zero from a server.

## Open questions (for the user before any code)

1. Is the Opendatasoft API surface rich enough to ingest bylaws + decisions + votes, or do we need YouTube-captions for any speech-level Hansard equivalent?
2. Do we accept the Vancouver Open Data Licence's "must not disparage" clause, given that the project's editorial stance is non-apolitical (CLAUDE.md "It is **not apolitical**")? Worth a one-paragraph compatibility read.

## Status checklist

- [x] System fingerprint (Cloudflare challenge on council.vancouver.ca; Opendatasoft v2.1 alternative) — 2026-05-05
- [x] Opendatasoft API confirmed reachable, 196 datasets total — 2026-05-05
- [ ] Targeted council-meeting dataset enumeration via Opendatasoft `where=` clause
- [ ] Vancouver Open Data Licence read; "must not disparage" clause assessed for project compatibility
- [ ] User research-handoff: any contacts / known endpoints
- [ ] First scraper module (post-handoff)
