# Québec — Municipal Data Research

> Standalone research dossier for the Ville de Québec (provincial capital, distinct from the province). Cross-cutting context lives in [`overview.md`](./overview.md).

**Conseil:** Conseil municipal de Québec | **Website:** https://www.ville.quebec.qc.ca/ | **Seats:** 22 (Mayor + 21 conseillers across 6 arrondissements) | **Next election:** 2025-11-02 (most recent)

**Status snapshot (2026-05-05):** 🚧 **Research only.** Roster live (5 of 22). The city runs a **bespoke IIS / ASP.NET site** at `ville.quebec.qc.ca` — many guessed paths return 403/404, but the live-stream page at `/apropos/gouvernance/conseil-municipal/seances/direct.aspx` returns 200 OK, confirming the council pages exist under `/apropos/gouvernance/`. The séance archive index needs to be discovered via homepage navigation rather than guessed. **FR primary throughout.**

---

## Bills / Règlements

- **Source URL(s):** https://www.ville.quebec.qc.ca/apropos/gouvernance/conseil-municipal/reglements/ (path candidate — needs probe); https://www.donneesquebec.ca/recherche/?q=ville+de+quebec+reglement (provincial open-data aggregator may republish)
- **Format:** PDF règlements via the city site; possible structured republish on donneesquebec.ca.
- **Difficulty (1-5):** **3** if a structured dataset is found; **4** for IIS/ASP.NET HTML scrape (the path discovery is the pain point).
- **Notes:** Québec city règlements are written in French only (no English mirror, unlike Ottawa). Schema can stay single-language for this jurisdiction.

## Hansard / Séances du conseil

- **Source URL(s):** https://www.ville.quebec.qc.ca/apropos/gouvernance/conseil-municipal/seances/direct.aspx (live-stream landing — confirmed 200 OK 2026-05-05); the archive index lives somewhere under `/apropos/gouvernance/conseil-municipal/seances/` (returned 403, suggesting directory listing disabled but specific child pages exist).
- **Format:** Likely per-séance page with PDF procès-verbal + video archive link. **No verbatim transcript appears to be published** — pattern is consistent with most QC municipalities (only Montréal publishes captions).
- **Granularity:** Per-séance.
- **Speaker identification:** Mover / seconder named in the procès-verbal; debate speakers not identified.
- **Difficulty (1-5):** **3-4** for the IIS scrape once the archive index URL is found.
- **Notes:** Possible captions surface — Québec city's accessibility programme may publish caption files similar to Montréal's `sous-titrage` archive. **Worth checking** as part of the next probe pass; if it exists, Québec joins Montréal as a verbatim-quality city.

## Voting Records

- Procès-verbal records vote totals; per-conseiller positions only when a roll-call vote is requested.
- Format: PDF inline.
- Difficulty (1-5): **4** (PDF parse).

## Committee Activity

- Québec runs commissions consultatives on environnement, urbanisme, finances, etc., plus arrondissement councils for each of the six boroughs. Each arrondissement publishes its own séances. **Six borough councils + one city council = seven separate meeting series** to ingest, an order of magnitude more than a typical tier-1 city.

## Open-data — donneesouvertes.ville.quebec.qc.ca

- Portal candidate: https://www.donneesouvertes.ville.quebec.qc.ca/ (needs probe — URL guessed from the city site's likely conventions).
- Provincial aggregator: https://www.donneesquebec.ca/ (CKAN — same backend as the QC provincial bills source). May aggregate Ville de Québec datasets.
- **Action item:** probe both portals; donneesquebec.ca is the more likely one to have structured council data because that's where municipal data tends to land in QC's open-data ecosystem.

## Terms / Licensing

- Québec city open data: licence québécoise (CC-BY 4.0 typical). Confirm.
- City-published règlements / procès-verbaux: municipal Crown copyright; transparency use accepted.
- **Provincial copyright caveat:** Quebec province treats Crown copyright more restrictively than other provinces (commercial use of provincial Hansard requires permission, per `../overview.md` § Legal). The municipal layer typically inherits the same posture. **Read before any redistribution.**

## Rate limits / auth

- IIS site: not characterised; pace at 1-2 req/sec until rate-limit behaviour is known.
- donneesquebec.ca CKAN: 24h cache typical, no observed per-IP cap.

## Open questions (for the user before any code)

1. Is there a known caption archive for Québec city council seances similar to Montréal's `sous-titrage`? Worth a direct contact at the Ville de Québec accessibility team if not visible online.
2. Are the six arrondissement councils in scope for the first build, or just the central conseil municipal? Six boroughs adds significant ingest volume.
3. Provincial-level QC copyright posture — does the municipal data inherit the more restrictive QC stance, or follow the federal/municipal-Crown norm?

## Status checklist

- [x] Site is bespoke IIS/ASP.NET — 2026-05-05
- [x] Council page tree confirmed under `/apropos/gouvernance/` — 2026-05-05
- [ ] Séance archive index URL discovery (path is one level under `/seances/`)
- [ ] Caption archive existence probe (Montréal-equivalent)
- [ ] donneesouvertes.ville.quebec.qc.ca + donneesquebec.ca catalog enumeration
- [ ] Six-arrondissement scope decision
- [ ] QC municipal copyright posture read
- [ ] User research-handoff
- [ ] First scraper module (post-handoff)
