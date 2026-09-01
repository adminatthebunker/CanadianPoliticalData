# Ottawa — Municipal Data Research

> Standalone research dossier for the City of Ottawa. Cross-cutting context lives in [`overview.md`](./overview.md). The eScribe surface description in [`calgary.md`](./calgary.md) is canonical; this file lists only Ottawa-specific findings.

**Council:** Ottawa City Council | **Website:** https://ottawa.ca/en/city-hall/your-city-government/city-council | **Seats:** 25 (Mayor + 24 councillors, ward-based) | **Next election:** 2026-10-26

**Status snapshot (2026-05-05):** 🚧 **Research only.** Roster live (5 rows out of 25 — full ingest pending). **eScribe confirmed** at `pub-ottawa.escribemeetings.com`. Open-data portal at `open.ottawa.ca` is bilingual (EN + FR primary) — federal-capital nature reflected in the data layer.

---

## Bills / By-laws

- **Source URL(s):** https://ottawa.ca/en/city-hall/legal-services/laws-and-regulations/by-laws (HTML index, EN); https://ottawa.ca/fr/hotel-de-ville/services-juridiques/lois-et-reglements/reglements-municipaux (FR mirror); https://open.ottawa.ca/?q=by-law
- **Format:** Topic-indexed HTML → per-bylaw HTML/PDF. Open-data portal may republish.
- **Difficulty (1-5):** **3**.
- **Notes:** **Bilingual content** — every bylaw exists in both languages. Schema implication shared with Montréal: `title` / `title_fr` columns or a translations sidecar. As the federal capital sitting in a province with a French-language services act, Ottawa's official language obligations are stronger than other ON cities.

## Hansard / Council Meeting Surface (eScribe)

- **Source URL(s):** https://pub-ottawa.escribemeetings.com/
- **Format:** Same eScribe surface as Calgary — see [`calgary.md`](./calgary.md) § eScribe surface in detail.
- **Bilingual?** Confirm: do Ottawa eScribe agendas and minutes carry both English and French versions (linked PDFs)? Not yet probed.
- **Granularity, speakers, video:** family pattern. Ottawa streams on YouTube (@CityofOttawa) + a city-managed `ottawa.ca/live` page.
- **Difficulty (1-5):** **3**, possibly **4** if bilingual handling adds parsing complexity.

## Voting Records

- Per-item recorded votes via eScribe; same shape as Calgary.

## Committee Activity

- Ottawa runs Standing committees: Finance and Corporate Services, Planning and Housing, Transportation, Built Heritage, Agriculture and Rural Affairs, Community Services, Emergency Preparedness and Protective Services, Environment and Climate Change, Audit, etc. — and a separate **Ottawa Police Services Board**, **Library Board**, etc. all running on the same eScribe instance.

## Open-data — open.ottawa.ca

- Portal: https://open.ottawa.ca/
- Backend: ArcGIS Hub (Esri) — **different from CKAN / Socrata / Opendatasoft**. ArcGIS Hub has its own search API at `https://opendata.arcgis.com/api/v3/search` and per-dataset `/query?f=json` REST endpoints.
- **Action item:** confirm whether Ottawa publishes council-meeting metadata via ArcGIS Hub. ArcGIS Hub is more commonly used for GIS data than meeting metadata; Ottawa may rely entirely on the eScribe surface for meeting data.

## Terms / Licensing

- Ottawa Open Data is published under the **Open Data Licence — City of Ottawa** (variant of Canadian municipal OGL family). Confirm at https://open.ottawa.ca/pages/licence.
- eScribe-published agendas/minutes: municipal Crown copyright; transparency use accepted.

## Rate limits / auth

- eScribe: Cloudflare-fronted, polite UA OK.
- ArcGIS Hub: documented rate limits per-org; Esri standard.

## Open questions (for the user before any code)

1. Does Ottawa eScribe carry FR + EN agenda/minute pairs? If yes, the parser needs language-aware handling on first build.
2. Is Ottawa's bilingual ingest a strong reason to pick it as the eScribe-family reference rather than Calgary? Calgary is unilingual EN; Ottawa's bilingual structure is closer to what Montréal will eventually need.

## Status checklist

- [x] eScribe fingerprint confirmed — 2026-05-05
- [x] Bilingual nature noted — 2026-05-05
- [ ] eScribe FR/EN pair behaviour probe
- [ ] ArcGIS Hub catalog enumeration (council-meeting metadata likely sparse here)
- [ ] Open Data Licence — City of Ottawa read
- [ ] User research-handoff
- [ ] First eScribe scraper module (shared with Calgary / Edmonton / Mississauga / Hamilton)
