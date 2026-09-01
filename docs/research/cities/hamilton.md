# Hamilton — Municipal Data Research

> Standalone research dossier for the City of Hamilton. Cross-cutting context lives in [`overview.md`](./overview.md). The eScribe surface description in [`calgary.md`](./calgary.md) is canonical.

**Council:** Hamilton City Council | **Website:** https://www.hamilton.ca/government-information/council-committee/city-council | **Seats:** 16 (Mayor + 15 councillors, ward-based) | **Next election:** 2026-10-26

**Status snapshot (2026-05-05):** 🚧 **Research only.** Roster live (5 of 16). **eScribe confirmed** at `pub-hamilton.escribemeetings.com`. Hamilton is a **single-tier amalgamated city** (no upper-tier regional overlap; 2001 amalgamation), which simplifies the schema relative to Mississauga (Peel) or Ottawa-area councils.

---

## Bills / By-laws

- **Source URL(s):** https://www.hamilton.ca/government-information/by-laws-and-enforcement (HTML index); https://open.hamilton.ca/?q=by-law
- **Format:** Topic-indexed HTML → per-bylaw HTML/PDF.
- **Difficulty (1-5):** **3**.

## Hansard / Council Meeting Surface (eScribe)

- **Source URL(s):** https://pub-hamilton.escribemeetings.com/
- **Format:** Same eScribe surface as Calgary — see [`calgary.md`](./calgary.md).
- **Granularity, speakers, video:** family pattern. Hamilton streams on YouTube (@cityofhamilton).
- **Difficulty (1-5):** **3**.

## Voting Records / Committee Activity

- eScribe per-item votes; standing committees include General Issues Committee (which is Council-as-committee for most decisions, a Hamilton quirk), Planning, Public Works, Audit Finance and Administration, Emergency and Community Services, etc.
- **Hamilton-specific quirk:** the **General Issues Committee (GIC)** is council-of-the-whole acting as a committee — most substantive debate happens there, and the formal Council meeting subsequently rubber-stamps. Schema mapping question: do we treat GIC items as committee items or as council items? Lean towards modeling them as a separate `body_type='committee_of_the_whole'` so they're searchable both ways.

## Open-data — open.hamilton.ca

- Portal: https://open.hamilton.ca/
- Backend: Likely CKAN (Hamilton has historically used CKAN; needs confirmation).
- **Action item:** check the API base and enumerate council-related datasets.

## Terms / Licensing

- Hamilton Open Data Licence — confirm.
- eScribe agendas/minutes: municipal Crown copyright.

## Open questions (for the user before any code)

1. Is the General Issues Committee distinction worth modeling as its own `body_type`, or just `'committee'` like every other?
2. Hamilton has a strong civic-tech community (Code for Hamilton historically); is there a known contact who could share bylaw / decisions feeds?

## Status checklist

- [x] eScribe fingerprint confirmed — 2026-05-05
- [ ] open.hamilton.ca backend identification + dataset enumeration
- [ ] GIC (Committee of the Whole) modeling decision
- [ ] Open Data Licence — Hamilton read
- [ ] User research-handoff
- [ ] First eScribe scraper module (shared with Calgary / Edmonton / Ottawa / Mississauga)
