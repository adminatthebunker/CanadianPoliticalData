# Mississauga — Municipal Data Research

> Standalone research dossier for the City of Mississauga. Cross-cutting context lives in [`overview.md`](./overview.md). The eScribe surface description in [`calgary.md`](./calgary.md) is canonical.

**Council:** Mississauga City Council | **Website:** https://www.mississauga.ca/council/ | **Seats:** 12 (Mayor + 11 councillors, ward-based) | **Next election:** 2026-10-26

**Status snapshot (2026-05-05):** 🚧 **Research only.** Roster live (5 of 12). **eScribe confirmed** at `pub-mississauga.escribemeetings.com`. Mississauga is a **Region of Peel** member-municipality, so a meaningful share of councillors' time is spent at Peel Regional Council too — that's separate ingest scope (see Note below).

---

## Bills / By-laws

- **Source URL(s):** https://www.mississauga.ca/council/bylaws-and-records/ ; https://data.mississauga.ca/?q=bylaw
- **Format:** Topic-indexed HTML → per-bylaw PDF. Open data portal may republish.
- **Difficulty (1-5):** **3**.

## Hansard / Council Meeting Surface (eScribe)

- **Source URL(s):** https://pub-mississauga.escribemeetings.com/
- **Format:** Same eScribe surface as Calgary — see [`calgary.md`](./calgary.md).
- **Granularity, speakers, video:** family pattern. Mississauga streams on YouTube (@cityofmississauga).
- **Difficulty (1-5):** **3**.

## Voting Records / Committee Activity

- eScribe: per-item votes + standing committees (General Committee, Planning and Development, Audit, Budget, Heritage Advisory, etc.).

## Region of Peel intersection (note)

Mississauga councillors also sit on Peel Regional Council (alongside Brampton + Caledon councillors). Peel Regional Council is at https://www.peelregion.ca/council/ and runs a **separate eScribe instance** (likely `pub-peelregion.escribemeetings.com` — needs probing). For Mississauga councillor activity to be modelled accurately, a future build needs to ingest both eScribe instances and join positions across them.

This is a **structural recurring pattern** across the Greater Toronto Area: every GTA-municipality councillor has activity in two systems (their city's eScribe + Peel Regional / York Regional / Halton Regional / Durham Regional eScribe). Schema needs to support a councillor having multiple `politician_terms` rows that point to different bodies. The provincial pattern (a single legislature) didn't have this concern.

## Open-data — data.mississauga.ca

- Portal: https://data.mississauga.ca/
- Backend: ArcGIS Hub (likely — Mississauga + many ON municipalities use Esri).
- **Action item:** enumerate council-meeting datasets via the ArcGIS Hub API.

## Terms / Licensing

- Mississauga Open Data Licence — confirm at https://data.mississauga.ca/pages/licence.
- eScribe agendas/minutes: municipal Crown copyright.

## Open questions (for the user before any code)

1. Should Peel Regional Council ingest be in scope for the Mississauga build, or treated as a separate Tier-2 city target?
2. How do we model a councillor who has positions in two bodies (Mississauga + Peel)? `politician_terms` plural rows is the obvious answer; surfacing this in the UI is the harder problem.

## Status checklist

- [x] eScribe fingerprint confirmed — 2026-05-05
- [ ] Peel Regional Council eScribe instance probe
- [ ] ArcGIS Hub catalog enumeration
- [ ] Open Data Licence — Mississauga read
- [ ] Schema decision: multi-body councillor representation
- [ ] User research-handoff
- [ ] First eScribe scraper module (shared with Calgary / Edmonton / Ottawa / Hamilton)
