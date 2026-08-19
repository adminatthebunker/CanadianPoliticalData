# Jurisdiction Research

This directory holds **one self-contained research dossier per jurisdiction** — federal plus all 13 Canadian provinces and territories. Each file is reviewable on its own; you do not need to read the others (or this index) to understand what one jurisdiction looks like.

For the cross-cutting context — schema migrations, scanner-module conventions, the probe hierarchy, the research-handoff protocol, the comparison matrix, licensing notes, and shared blockers — see [`overview.md`](./overview.md). That file is the authority on *how* we approach research; the per-jurisdiction files are *what we found*, per place.

## Index

### Overview
- [Cross-cutting overview](./overview.md) — schema log, scanner-module conventions, probe hierarchy, research-handoff protocol, comparison matrix, licensing, known blockers, next steps.

### Federal
- [Federal](./federal.md) — House of Commons via openparliament.ca mirror; only Canadian legislature with a comprehensive third-party portal we can lean on.

### Provinces (by region, west to east)
- [British Columbia](./british-columbia.md) — ✅ **Bills live** via LIMS PDMS JSON. GraphQL member API also available.
- [Alberta](./alberta.md) — ✅ **Bills live** via Assembly Dashboard server-rendered HTML. Committees pre-existing. Hansard PDF-only.
- [Saskatchewan](./saskatchewan.md) — ⏸️ **Deferred** (PDF-only progress-of-bills). Hansard well-indexed.
- [Manitoba](./manitoba.md) — ⏸️ **Deferred** (PDF-only billstatus). Stage timeline locked behind `billstatus.pdf`.
- [Ontario](./ontario.md) — ✅ **Bills + Hansard live** via HTML scrape (bills) and `?_format=json` JSON node (Hansard). Name-based speaker resolution; parens-name extraction handles presiding-officer attributions exactly.
- [Quebec](./quebec.md) — ✅ **Bills live** via donneesquebec.ca CSV + RSS + detail HTML. Bilingual.
- [New Brunswick](./new-brunswick.md) — ✅ **Bills live** via two-step legnb.ca HTML scrape.
- [Nova Scotia](./nova-scotia.md) — ✅ **Bills live** via Socrata API (easiest source in country); per-bill HTML cache blocked by WAF budget.
- [Prince Edward Island](./prince-edward-island.md) — ⏸️ **Deferred** (Radware ShieldSquare CAPTCHA).
- [Newfoundland & Labrador](./newfoundland-labrador.md) — ✅ **Bills live** via single-page session table; sponsor data not exposed.

### Territories
- [Yukon](./yukon.md) — ⏸️ **Deferred** (Cloudflare Bot Management blockade).
- [Northwest Territories](./northwest-territories.md) — ✅ **Bills live** via ntassembly.ca Drupal 9. Consensus government — no sponsors by design.
- [Nunavut](./nunavut.md) — ✅ **Bills live** via Drupal 9 single-page view. Consensus government — no sponsors by design.

### Cities (tier-1, research only as of 2026-05-05)

Municipal-level dossiers live under [`cities/`](./cities/). Cross-cutting context (system fingerprints, family clusters, schema implications, probe hierarchy adapted for municipalities) lives in [`cities/overview.md`](./cities/overview.md). Tier-1 = ten cities by population × civic salience; ingest is a *Later*-horizon workstream per [`../timeline.md`](../timeline.md).

- [Cities overview](./cities/overview.md) — coverage matrix, system-fingerprint families (open-data API / eScribe / bespoke), priority ordering.
- [Toronto](./cities/toronto.md) — 🚧 research. CKAN at open.toronto.ca (15 council datasets); TMMIS Akamai-walled.
- [Montréal](./cities/montreal.md) — 🚧 research. ★ CKAN `sous-titrage-conseil-municipal` is the strongest municipal-Hansard-equivalent in Canada (real-time captions, 2018+).
- [Vancouver](./cities/vancouver.md) — 🚧 research. Opendatasoft v2.1 alternative to Cloudflare-walled council.vancouver.ca.
- [Calgary](./cities/calgary.md) — ⏸️ parked. Pipeline scaffold landed; eScribe past-meetings AJAX opaque to server-side callers; **no YouTube channel** for council (video lives only inside eScribe). Promotion needs Socrata republish probe or Playwright.
- [Edmonton](./cities/edmonton.md) — ⏸️ parked. Same eScribe block as Calgary, **but** does maintain a YouTube channel — captions path becomes tractable once the correct handle is found.
- [Ottawa](./cities/ottawa.md) — 🚧 research. eScribe (bilingual EN/FR) + ArcGIS Hub.
- [Mississauga](./cities/mississauga.md) — 🚧 research. eScribe + Peel Regional intersection.
- [Hamilton](./cities/hamilton.md) — 🚧 research. eScribe + General Issues Committee quirk.
- [Winnipeg](./cities/winnipeg.md) — 🚧 research. DMIS bespoke + Socrata; needs reachability re-probe.
- [Québec](./cities/quebec.md) — 🚧 research. Bespoke IIS/ASP.NET; six arrondissements add scope; FR primary.

### Electoral boundaries (started 2026-08-18)

Boundary/roster dossiers live under [`boundaries/`](./boundaries/). Cross-cutting context — the `constituency_id` re-key strategy, licence and coverage matrices, the consolidated handoff register, and the geospatial probe hierarchy — lives in [`boundaries/overview.md`](./boundaries/overview.md). This directory answers *"where do authoritative electoral boundaries come from, and are ours correct"*; the sibling dossiers one level up answer *"where does legislative text come from"*. Motivation: our 1,949 boundary rows were all mirrored from Open North's Represent API, which has been ⛔ **down since 2026-08-07**, and measurement found **9.15% of Canadian addresses get no provincial answer** from the lookup today.

- [Boundaries overview](./boundaries/overview.md) — ★ the authority on the `constituency_id` question; coverage + licence matrices; 99 handoff items triaged.
- [Geocoding](./boundaries/geocoding.md) — ✅ open-licence postal→coordinate research. **StatCan National Address Register** (cat. 46-26-0002, StatCan Open Licence) recommended; PCCF/PCFRF/Geocoder.ca closed with citations.
- [Measured impact](./boundaries/impact.md) — ★ address-weighted error rates. **9.15% no answer, 12.61% any error** over the six measurable jurisdictions.
- [Federal](./boundaries/federal.md) — ✅ OGL-Canada, 343 FEDs. One district absent (24077 Ville-Marie—Le Sud-Ouest—Île-des-Sœurs).
- [Alberta](./boundaries/alberta.md) — ✅ **cleanest jurisdiction.** OGL-Alberta, 87/87, both generations from one licensed endpoint.
- [British Columbia](./boundaries/british-columbia.md) — ⛔ 52 rows carrying **2015 geometry under 2023 names**. ★ LIMS publishes a 164,848-postcode concordance — our PIP regression corpus.
- [Saskatchewan](./boundaries/saskatchewan.md) — ⛔ 41 wrong + 15 absent, **proven** (46/46 match 2012 to 0.07%). ⛔ no open licence.
- [Manitoba](./boundaries/manitoba.md) — ⚠ one absent (The Pas-Kameesak); cheapest cutover. ⛔ no open licence.
- [Ontario](./boundaries/ontario.md) — ★ **pilot cutover** — 123/123 exact slug reproduction. Elections Ontario's licence is *Open Use*, not Limited Use.
- [Quebec](./boundaries/quebec.md) — ⚠ one absent. ★ Élections Québec publishes the only open postal→district concordance in Canada.
- [New Brunswick](./boundaries/new-brunswick.md) — ⛔ 22 rows = 2018 geometry under 2024 names; **47% of the province uncovered.** ✅ GeoNB ODL is clean; the flow-down alarm was false.
- [Nova Scotia](./boundaries/nova-scotia.md) — ⛔ **56 seats, not 55** (Charter ruling → Bill 205). Inverness *reshaped*, not renamed. ⛔ no licence route exists.
- [Prince Edward Island](./boundaries/prince-edward-island.md) — ⚠ one absent, but 28.8% no-answer is unexplained by that alone.
- [Newfoundland & Labrador](./boundaries/newfoundland-labrador.md) — ⚠ four absent; a new commission is due this year.
- [Northwest Territories](./boundaries/northwest-territories.md) — ⛔ **count perfect, 5 of 19 misassigned.** Returns wrong MLAs today.
- [Yukon](./boundaries/yukon.md) — ⛔ stale generation (19 held, 21 seats). ★ We may hold the last copy of the 2015 map.
- [Nunavut](./boundaries/nunavut.md) — ⛔ **zero rows.** ✅ Closable — Elections Nunavut ships a real shapefile. ⚠ the `FUTURE`/`PRESENT` filenames are inverted.
- [Municipal — Ontario](./boundaries/municipal-ontario.md) — ⛔ only 343 of 410 rows are wards; Peel duplicated wholesale. ⚠ elections 2026-10-26.
- [Municipal — Quebec](./boundaries/municipal-quebec.md) — ⛔ entire layer one generation stale (2025-11-02 election). ★ single CKAN sweep fixes all 24 sets.
- Municipal — [Alberta](./boundaries/municipal-alberta.md) / [Atlantic](./boundaries/municipal-atlantic.md) / [West](./boundaries/municipal-west.md) — 🚧 pending.

## Status legend

- ✅ **Live** — production ingestion running; data in `bills` / `bill_events` / `bill_sponsors`.
- 🚧 **In progress** — schema or ingester partially built.
- ⏸️ **Deferred** — research complete; ingestion blocked on tooling, infra, or upstream changes.
- ⛔ **Blocked** — upstream is hostile or absent; needs alternative path.

## Scope

These dossiers cover four legislative-data layers per jurisdiction:

1. **Bills & Legislation** — proposed laws and their stage timelines.
2. **Hansard / Debates** — verbatim transcripts of chamber proceedings.
3. **Voting Records / Divisions** — recorded roll-call votes.
4. **Committee Activity** — memberships, meetings, reports.

Plus standard front-matter (legislature name, seats, next election) and a Status checklist.

## Editing convention

When you complete or change something for a jurisdiction, update its file's "Status" section and (if material) its difficulty rating or blocker note. Keep one fact in one file — if a finding affects every jurisdiction, write it in the cross-cutting plan doc, not per-jurisdiction.
