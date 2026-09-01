# Winnipeg — Municipal Data Research

> Standalone research dossier for the City of Winnipeg. Cross-cutting context lives in [`overview.md`](./overview.md).

**Council:** Winnipeg City Council | **Website:** https://www.winnipeg.ca/council | **Seats:** 16 (Mayor + 15 councillors, ward-based) | **Next election:** 2026-10-28

**Status snapshot (2026-05-05):** 🚧 **Research only — needs deeper probe.** Roster live (5 of 16). The city's bespoke meeting management system is **DMIS — Decision Making Information System** at `dmis.winnipeg.ca`, but the first probe pass returned an empty response (connection issue, not a 4xx/5xx). The system exists and is reachable from a browser; bot-mitigation, IP-block, or temporary downtime are the candidate explanations. **A second probe pass is required before this dossier can be confidently rated.** The city's open-data portal at `data.winnipeg.ca` is **Socrata** — same backend as NS / NB / Edmonton / Calgary.

---

## Bills / By-laws

- **Source URL(s):** https://www.winnipeg.ca/clerks/cks_council/bylaws (legacy clerks site, now redirected); https://legacy.winnipeg.ca/clerks/dmis/ (per probe redirect chain — legacy DMIS surface still active alongside the new one); https://data.winnipeg.ca/?q=bylaw
- **Format:** DMIS hosts decisions and bylaws; structured PDF bodies. Socrata likely republishes a bylaw index.
- **Difficulty (1-5):** **3-4**, gated on DMIS access pattern.

## Hansard / Council Meeting Surface (DMIS)

- **Source URL(s):** https://dmis.winnipeg.ca/ (subdomain confirmed via 307 redirect from `winnipeg.ca/dmis`); https://legacy.winnipeg.ca/clerks/dmis/ (older surface, 302-reachable).
- **System:** DMIS (Decision Making Information System) — **bespoke City of Winnipeg system**, not a SaaS. Likely an older ASP.NET application; the redirect chain runs through `volt-adc` (Volterra ADC) + AWS ALB, which is consistent with City of Winnipeg's other web infrastructure.
- **Format (TBD on probe):** Per-meeting agenda + minutes + decisions. Whether speaker-level data exists or whether it's decisions-only is unverified.
- **Granularity:** Per-meeting agenda item.
- **Speaker identification:** Unknown until DMIS is readable.
- **Difficulty (1-5):** **3-4** (estimated; needs probe).
- **Notes:** **Action item before any code:** re-probe `dmis.winnipeg.ca` from a browser to capture the actual landing page HTML, then re-probe with curl using a real browser UA + cookies if needed. The empty-response on first pass is **suspect for bot mitigation** (Volterra ADC has bot management features); confirm before rating final difficulty.

## Voting Records / Committee Activity

- DMIS likely covers Standing Policy Committees on Property and Development, Heritage and Downtown Development, Infrastructure Renewal and Public Works, Water and Waste, etc., plus Executive Policy Committee (mayor's cabinet). Confirm post-probe.

## Open-data — data.winnipeg.ca (Socrata)

- Portal: https://data.winnipeg.ca/
- Backend: **Socrata.** Same code paths as NS / NB / Edmonton / Calgary scanners.
- API base: `https://data.winnipeg.ca/resource/<id>.json`, catalog `https://data.winnipeg.ca/api/catalog/v1`.
- **Action item:** enumerate council-meeting datasets via `package_search` equivalent.

## Terms / Licensing

- Winnipeg Open Data is published under the **Open Data Licence — City of Winnipeg** (Canadian municipal OGL family). Confirm at https://data.winnipeg.ca/stories/s/Open-Data-Licence/qy3p-2vxx.
- DMIS-published material: municipal Crown copyright.

## Rate limits / auth

- DMIS: unknown until probed.
- Socrata: app token recommended; ~10000 req/hour with token.

## Open questions (for the user before any code)

1. Is `dmis.winnipeg.ca` reachable from your browser? Confirming this lets us decide whether to invest in browser automation or whether a polite UA + Cookie pass-through fixes the issue.
2. Does Winnipeg DMIS publish decisions in a structured format, or is it minutes-only? The first determines whether the per-decision schema (sponsor, vote, outcome) maps cleanly; the second pushes us towards a minutes-PDF parse pipeline.
3. Winnipeg has historically had a strong civic-tech presence (OpenWinnipeg, etc.); is there a known DMIS data-feed contact?

## Status checklist

- [x] DMIS subdomain identified (dmis.winnipeg.ca) — 2026-05-05
- [x] Socrata open-data backend confirmed — 2026-05-05
- [ ] **DMIS reachability re-probe (blocker before any further work)**
- [ ] DMIS HTML structure characterisation
- [ ] Socrata catalog enumeration for bylaw / decisions / agenda datasets
- [ ] Open Data Licence terms read
- [ ] User research-handoff
- [ ] First scraper module (post-handoff, gated on DMIS reachability)
