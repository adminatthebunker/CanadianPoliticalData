# Ontario — Electoral Boundary Research

> Standalone boundary/roster dossier for Ontario. Cross-cutting context
> (methodology, licence matrix, reconciliation strategy) lives in [`overview.md`](./overview.md).
> The legislative-data dossier for this jurisdiction is at [`../ontario.md`](../ontario.md).

**Agency:** Elections Ontario | **Website:** https://www.elections.on.ca | **Districts (current):** 124 | **Current order:** Representation Act, 2015 + Far North Electoral Boundaries Act, 2017 (first used at the 2018 general election) | **Next redistribution:** no commission struck; trigger is a post-2023-federal-order provincial review — **needs confirmation**

**Status snapshot (2026-08-18):** ★ **Licence problem solved, and better than expected.** Elections Ontario publishes electoral district boundaries under an **Open Use Data Product Licence Agreement** that grants a worldwide, royalty-free, perpetual licence including commercial use and redistribution with **no attribution clause** — more permissive than OGL-Ontario. ⛔ It sits behind an "I Agree" button, so per the standing rule it was **not clicked**; text recorded verbatim below and raised as a handoff item. ✅ A **gate-free authoritative alternative** was found and staged: the MTO Authoritative ArcGIS feature service, 124 features carrying a contiguous integer **`ED_ID` 1–124**, 7.3× the geometric detail we currently hold. ✅ **Exact reconciliation achieved** — all 123 of our existing slugs map 1:1 onto authoritative names with byte-identical text; the single gap is **ED_ID 98, Scarborough Southwest** (MPP Doly Begum). ★ **Ontario is now the strongest early-cutover candidate** for the [`overview.md`](./overview.md) option-(d) strategy: `ED_ID` is a clean authority key and the mapping is deterministic, not fuzzy. ⛔ GeoHub and `data.ontario.ca` do **not** publish provincial electoral geometry — that route is a dead end, recorded so nobody re-probes it.

---

## Current boundaries

Two routes to the same generation. Route B is staged; Route A is the licence of record.

### Route A — Elections Ontario (authoritative agency, licence-preferred, gated)

- **Source URL(s):** https://www.elections.on.ca/en/voting-in-ontario/electoral-district-shapefiles.html ; https://www.elections.on.ca/en/voting-in-ontario/electoral-district-shapefiles/open-use-data-product-licence-agreement.html
- **Format:** SHP (zipped) — `UNTESTED — probe during build`, not downloaded
- **CRS / projection:** `UNTESTED — probe during build`. Ontario agencies commonly publish EPSG:3161 (NAD83 / Ontario MNR Lambert); the MTO service is EPSG:4269. Read the `.prj` before assuming.
- **Attribute schema:** `UNTESTED — probe during build`
- **District ID field:** `UNTESTED — probe during build`. Expect the same `ED_ID` 1–124 as Route B; confirm.
- **Effective date:** ✅ **2018-05-08** — the legal in-force date, established below
- **District count:** 124 — matches the seat count
- **Difficulty (1–5):** **2** — structured download, but gated by a click-through the agent may not accept
- **Notes:** ★ This is the *primary* source and carries the *best* licence. The gate is the only obstacle and it is a one-click operator action, not a registration wall. See § Research-handoff items.

### Route B — MTO Authoritative ArcGIS feature service (gate-free, staged) ✅

- **Source URL(s):** https://services.arcgis.com/6iGx1Dq91oKtcE7x/arcgis/rest/services/Electoral_Districts_Public_View/FeatureServer/0 ; https://www.arcgis.com/sharing/rest/content/items/e5b708b7e7d245d6836a1c5805c3e42b?f=json
- **Format:** ArcGIS Feature Service — serves GeoJSON directly via `?f=geojson`; no zip, no shapefile handling
- **CRS / projection:** **EPSG:4269** — NAD83 geographic (lat/lng degrees). Service metadata reports `spatialReference: {wkid: 4269, latestWkid: 4269}`; no `.prj` exists because this is a service, not a file. ⚠ The GeoJSON response carries **no `crs` member**, so RFC 7946 consumers will silently assume WGS84 — see § Known traps below.
- **Attribute schema:** `OBJECTID` (esriFieldTypeOID), **`ED_ID` (esriFieldTypeInteger)**, `NAME` (String), `NAME_FRENCH` (String), `OVERVIEW_MAP` (String), `DETAILED_OVERVIEW` (String), `MPP_INFO` (String). Read from the service's own field metadata, not guessed.
- **District ID field:** ★ **`ED_ID`** — integer, contiguous **1–124**, no gaps. Alphabetical by English name for 1–122, with the two 2017-created northern districts appended as **123 = Kiiwetinoong** and **124 = Mushkegowuk—James Bay**. That ordering is itself evidence of the statutory history (see § District ↔ elected official mapping). **This does not match what we store** — our slug is the kebab-cased name — but the mapping is exact and deterministic; see § Reconciliation.
- **Effective date:** ✅ **2018-05-08** (legal). ⚠ The service's own metadata dates are `created` **2019-06-25** and `modified` **2020-02-25** — 13½ months *after* the legal date. Per the [`overview.md`](./overview.md) `effective_from` ruling, the legal date is the value to load; the metadata dates are recorded here only as the noted discrepancy.
- **District count:** **124** (verified by `returnCountOnly`) — matches the seat count
- **Difficulty (1–5):** **1** — documented, queryable, paginated, no auth, no gate
- **Notes:** `capabilities: Query,Extract` — bulk extraction is explicitly permitted by the service. `maxRecordCount` 2000 > 124, so one request returns everything. **196,512 total vertices, avg 1,585/district** — against 27,064 total / avg 220 for what we currently hold from Open North. Owner is `Authoritative_mto_on_ca`, an Ontario government authoritative account, but MTO is a *republisher* here, not the boundary authority — Elections Ontario is. Treat Route B as a licensed-weaker mirror of Route A, not as the primary source.

### Dead ends — do not re-probe

- ⛔ **Ontario GeoHub (`geohub.lio.gov.on.ca`)** — the site is a JavaScript-only ArcGIS Hub shell; server-rendered fetch returns only the page title. Probed the underlying LIO service directory at `https://ws.lioservices.lrc.gov.on.ca/arcgis1071a/rest/services` (20 folders: `Access_Environment`, `Aerial_Photo`, `Bait_Harvest`, `CLTIP`, `COSINE`, `DDS`, `Geographic_Names`, `GeologyOntario`, `IAO_KMS_Map`, `License_Issuer`, `LIO`, `LIO_Imagery`, `LIO_OPEN_DATA`, `MLAS`, `MLAS_Intra`, `MOE`, `PEP`, `Pits_And_Quarries`, `TEST`, `Utilities`) and enumerated `LIO_OPEN_DATA` (10 generically-named services `LIO_Open01`–`LIO_Open10`). **No electoral-district layer.** Expected in hindsight — electoral districts are Elections Ontario's mandate, not Land Information Ontario's.
- ⛔ **`data.ontario.ca` (CKAN)** — searched `electoral`, `riding`, `electoral boundaries`, `constituency`. **Zero geospatial electoral-district datasets.** The only electoral hit is `government-official-names` (OGL-ON-1.0), a bilingual CSV names list — useful, staged, but not geometry. Full-text `electoral boundaries` returns 0 results.
- ⛔ **ArcGIS Hub global search** — surfaces only third-party copies (`CentralOHatHome`, `miho_mkg`, `philiphahn`, `DSSSGeography`). Not primary sources; ignored per standing instruction 1.

## Prior boundaries (immediately preceding)

- **Source URL(s):** none located on an open, gate-free surface — see Notes
- **Format:** ⛔ not located
- **CRS / projection:** ⛔ not located
- **Attribute schema:** ⛔ not located
- **District ID field:** ⛔ not located
- **Effective date:** 2007-10-10 (39th general election) — the Representation Act, 2005 set
- **Superseded date:** **2018-05-07** → becomes `effective_to`. The 124-district set took legal effect 2018-05-08 (see § Effective dates), so the 107-district set's last day in force was the day before. ⚠ *Not* 2018-06-07 — polling day is a month too late, and the 2005 set was never in force for the 2018 election.
- **District count:** **107** — matches the pre-2018 seat count
- **Difficulty (1–5):** **4** — the names are freely available under OGL-ON; the *geometry* is not published anywhere open that this pass could find
- **Notes:** The staged OGL-ON CSV carries **154 former electoral district names** (`Ajax—Pickering`, `Algoma`, `Ancaster—Dundas—Flamborough—Aldershot`, `Barrie—Simcoe—Bradford`, `Beaches—Woodbine`, …), which spans several generations, not just the 107-district one — it is a cumulative historical list, so it cannot by itself delimit the 2005 set. Third-party AGOL copies exist (`miho_mkg`'s `Ontario2003` / `Ontario2007` / `Ontario2011` feature services) but are **not primary sources** and must not be cited as such. **Known bounded gaps:** prior-generation geometry is unresolved for Ontario. The temporal model does not need it to load the current generation correctly — it only needs it to answer "who represented this address in 2014?", which is not a shipped feature. Recommend deferring rather than blocking the cutover.

## District ↔ elected official mapping

The statutory chain, because conflating the provincial and federal orders is the single most likely build error:

1. **Representation Act, 2015** (S.O. 2015, c. 31, Sch. 1 — enacted by the *Electoral Boundaries Act, 2015*) — replaced the 107 districts of the Representation Act, 2005. Section 2(1) as originally enacted: **11 northern** districts (carried forward from the Representation Act, 1996) + **111 southern** = **122**.
2. **Far North Electoral Boundaries Act, 2017** (S.O. 2017, c. 18, s. 1) — amended s. 2(1) to read **13 northern** districts, reconstituting *Kenora—Rainy River* and *Timmins—James Bay* as four: Kenora—Rainy River, **Kiiwetinoong**, **Mushkegowuk—James Bay**, Timmins.
3. Net: **13 + 111 = 124**, first used at the 2018 general election, unchanged since.

Section 2(1) as amended, verbatim:

> **Redistribution 2 (1)** For the purpose of representation in the Legislative Assembly, Ontario is divided into the following electoral districts: 1. The 13 northern electoral districts, whose names and boundaries are set out in the Schedule. 2. In the part of Ontario that lies outside the 13 northern electoral districts, 111 southern electoral districts whose names and boundaries are identical to those of the federal electoral districts that come into effect on the first dissolution of Parliament after May 1, 2014. 2017, c. 18, s. 1 (1, 2).

★ Note what clause 2 actually pins the southern districts to: *"the federal electoral districts that come into effect on the first dissolution of Parliament after May 1, 2014"* — that is the **2013 federal Representation Order**, which per [`federal.md`](./federal.md) took legal effect **2015-08-02** (SI/2013-102). Ontario's 111 southern districts are therefore a *static snapshot* of the 2013 federal lines, frozen into provincial statute by reference. They do not track later federal orders.

> ⚠ **The 2023 federal redistribution did NOT change Ontario's provincial boundaries.** Federal Ontario moved to 122 seats on new lines; provincial Ontario remains **124 districts on the 2013-federal-derived lines**. They were aligned once, in 2015, and have diverged since. Never derive one from the other, and never assume a shared district ID.

★ The `ED_ID` numbering independently corroborates this history: 1–122 are strictly alphabetical by English name, and 123/124 — Kiiwetinoong and Mushkegowuk—James Bay, the two districts created in 2017 — are appended out of alphabetical order. The ID space encodes the amendment.

**Roster source.** `www.ola.org` Drupal `?_format=json`, already live for bills and Hansard (see [`../ontario.md`](../ontario.md)). Per-member node `/en/members/all/{slug}?_format=json` exposes:

- `field_member_id` — stable integer, already stored as `politicians.ola_member_id`
- ★ **`field_last_riding`** — a `taxonomy_term` reference carrying **`target_id`** (stable integer, e.g. `32401`) **and `url`** (e.g. `/en/riding/scarborough-southwest`)

Verified against Doly Begum (`field_member_id` 7508 → `field_last_riding.target_id` 32401, `url` `/en/riding/scarborough-southwest`). ⚠ The riding taxonomy term itself is **HTML-only** — both `/en/riding/{slug}?_format=json` and `/taxonomy/term/{tid}?_format=json` return HTTP 406 *"No route found for the specified format. Supported formats: html."* So the riding node's own fields are not machine-readable; only the reference embedded in the member node is.

**Assessment for the option-(d) authority key:** use **`ED_ID`** (`authority = 'elections-ontario'`), not the OLA `tid`. `ED_ID` comes from the boundary authority and is stable, small, and contiguous; the OLA `tid` is a Drupal CMS artifact that could change on a content migration. The OLA `tid`/slug is still valuable as a **secondary crosswalk** for joining MPPs to ridings without name-matching — and note its slug is character-identical to our existing `constituency_id` suffix, which makes an OLA-side join trivial today.

## Effective dates — legal vs metadata

Applying the `effective_from` ruling (use the **legal in-force date**, record the metadata date as a discrepancy).

**Operative provision — Representation Act, 2015, s. 2(2), verbatim:**

> **Effective date (2)** The redistribution described in subsection (1) takes effect immediately after the first dissolution of the Legislature after November 30, 2016.

> **Existing electoral districts maintained until effective date (3)** …

The first dissolution of the Ontario Legislature after 2016-11-30 was the dissolution of the 41st Parliament on **2018-05-08** (writs issued 2018-05-09; general election 2018-06-07). Corroborated by Elections Ontario's own *Dates of General Elections, Dates of Opening and Dissolution of Legislatures* report, https://results.elections.on.ca/api/report-groups/45/report-outputs/1045/pdf/en .

| | Date | Basis |
|---|---|---|
| ✅ **Legal in-force — use this** | **2018-05-08** | Representation Act, 2015 s. 2(2) + dissolution of the 41st Parliament |
| ⚠ Dataset metadata (discrepancy) | 2019-06-25 (created) / 2020-02-25 (modified) | MTO AGOL item `e5b708b7e7d245d6836a1c5805c3e42b` |
| ⚠ Commonly-cited but wrong | 2018-06-07 | The general election. The order was already in force for a month by polling day. |

**Gap: 13½ months** between legal and metadata — larger than the federal 11-month gap, and in the same direction. Ontario is a second independent confirmation that the metadata date is systematically late and must not be used.

`effective_to` for this generation: **NULL** — still in force.

⚠ **Our 123 existing rows carry `effective_from = '2023-01-01'`**, the loader's hardcoded placeholder. It is wrong by more than four and a half years and must not be carried forward.

**Prior generation:** the Representation Act, 2005 set was superseded at the same instant, so its `effective_to` = **2018-05-07** (the day before), or 2018-05-08 exclusive — pick one convention project-wide. Its own `effective_from` would need the equivalent provision in the 2005 Act; **not established** (geometry is unavailable anyway, see § Prior boundaries).

## Postal-code correspondence (if published)

⛔ **Not published as a downloadable artifact.** Elections Ontario operates an interactive postal-code lookup at `https://voterinformationservice.elections.on.ca/en/election/search?mode=postalCode` (and a second at `https://eregistration.elections.on.ca/en/voter-info/find-electoral-district`), but publishes no postal-code ↔ district concordance file. This is **unlike Elections Québec**, which X1 found does publish one.

Consequence: Ontario postal-code resolution stays point-in-polygon against our own geometry — which is the existing architecture, so nothing changes. It also means there is no independent concordance to validate our PIP against; the interactive lookup is the only cross-check and it is manual. Recommend spot-checking a sample of postcodes by hand at cutover rather than treating the absence as a blocker.

## Terms / Licensing

### ★ Elections Ontario — Open Use Data Product Licence Agreement (electoral district boundaries)

Licence URL: https://www.elections.on.ca/en/voting-in-ontario/electoral-district-shapefiles/open-use-data-product-licence-agreement.html — last updated **September 23, 2023**. Recorded verbatim without accepting:

> **Definitions**
>
> 1. In this licence, the terms below have the following meanings:
> "Information" means "Electoral District Boundaries" files that are offered for use under the terms of this licence.
> "Elections Ontario" means His Majesty the King in right of Ontario, as represented by the Chief Electoral Officer.
> "You" means the natural or legal person, or body of persons corporate or incorporate, acquiring rights under this licence.
>
> **Using Information under this licence**
>
> 2. Any use whatsoever of the Information indicates your acceptance of the terms below.
> 3. Elections Ontario grants you a worldwide, royalty-free, perpetual, non-exclusive licence to use the Information, including for commercial purposes, subject to the terms below.
>
> **You are free to**
>
> 4. Copy, modify, publish, translate, adapt, distribute or otherwise use the Information in any medium, mode or format for any lawful purpose.
>
> **Non-endorsement**
>
> 5. This licence does not grant you any right to use the Information in a way that suggests any official status or that Elections Ontario endorses you or your use of the Information.
>
> **No warranty**
>
> 6. The Information is licensed "as is", and Elections Ontario excludes all representations, warranties, obligations, and liabilities, whether expressed or implied, to the maximum extent permitted by law.
> 7. Elections Ontario is not liable for any errors or omissions in the Information, and will not under any circumstances be liable for any direct, indirect, special, incidental, consequential, or other loss, injury or damage caused by its use or otherwise arising in connection with this licence or the Information, even if specifically advised of the possibility of such loss, injury or damage.
>
> **Governing Law**
>
> 8. This licence is governed by the laws of the Province of Ontario and the applicable laws of Canada.
> 9. Legal proceedings related to this licence may only be brought in the courts of Ontario.
>
> **Versioning**
>
> 10. Elections Ontario may make changes to the terms of this licence from time to time and issue a new version of the licence. Your use of the Information will be governed by the terms of the licence in force as of the date you accessed the information.

**Analysis.** Clauses 3 and 4 together grant everything we need: commercial use, modification, and **distribution** in any medium — which covers serving boundary GeoJSON from `/api/public/v1/boundaries/*`. There is **no attribution clause**, making this *more* permissive than OGL-Ontario. Clause 5 (non-endorsement) is satisfied by not implying official status. Clause 10 means the licence version should be pinned by access date.

⚠ **Correction to a prior assumption.** Elections Ontario serves **two different** agreements from the same page, and the brief's premise had them the wrong way round:

| Product | Agreement | Restrictive? |
|---|---|---|
| **Electoral district shapefiles** | **Open Use** Data Product Licence Agreement | No — open, commercial, redistributable |
| Polling division shapefiles | **Limited Use** Data Product Licence Agreement | Yes — separate, not reviewed; out of scope |

The "Limited Use" gate applies to *polling divisions*, not to the electoral district boundaries we need.

⚠ **On clause 2 vs. the click-through.** Clause 2 states acceptance is triggered by "any use whatsoever of the Information", not by clicking — so the "I Agree" button is arguably navigation rather than contract formation. That reading was **not acted on**. The standing no-click-through rule is absolute and the operator makes this call, not the agent.

### MTO Authoritative feature service (Route B, staged)

No licence agreement; the AGOL item's `licenseInfo` is a bare Crown copyright notice plus a disclaimer, recorded verbatim (HTML stripped):

> © Queen's Printer for Ontario, 2020.
>
> The maps shown here are for illustration purposes only and are not suitable for site-specific use or applications. Ministry of Transportation provides this information with the understanding that it is not guaranteed to be accurate, correct or complete and conclusions drawn from such information are the responsibility of the user. While every effort has been made to use data believed to be accurate; a degree of error is inherent in all maps. Map products are intended for reference purposes only, and the Ministry of Transportation will accept no liability for consequential and indirect damages arising from the use of these maps. These maps are distributed "as-is" without warranties of any kind, either expressed or implied, including but not limited to warranties of suitability to a particular purpose or use.

`accessInformation` is null. ⚠ **This is not an open licence** — it grants no explicit redistribution right, and *"not suitable for site-specific use or applications"* arguably describes exactly what point-in-polygon riding assignment does. **Do not redistribute Route B geometry through the public API.** It is fit for internal validation and for proving the pipeline; the licensed artifact must come from Route A.

### data.ontario.ca names CSV (staged)

Open Government Licence – Ontario 1.0 (`OGL-ON-1.0`), https://www.ontario.ca/page/open-government-licence-ontario. Attribution required; redistribution permitted. Clean.

## Rate limits / auth

- **ArcGIS feature service:** no authentication, no API key, no observed rate limiting. `maxRecordCount` 2000; `supportsPagination: true`. Full 124-feature GeoJSON retrieved in **1.7 s / 7.3 MB** in a single request. Polite-UA requests were served without challenge.
- **`data.ontario.ca` CKAN:** standard CKAN Action API, no auth, no observed limit.
- **`www.ola.org`:** Drupal REST, no auth. Already in production use for bills/Hansard; existing politeness settings apply.
- **`www.elections.on.ca`:** static pages served without challenge to a polite UA. The download itself is behind the click-through, not behind auth.
- **No robots.txt violations observed.** No page fetched during this pass contained text addressed to an AI agent.

## Staged files

Under `data/boundaries/ontario/current/`, with hashes and URLs in
[`../../../data/boundaries/ontario/PROVENANCE.md`](../../../data/boundaries/ontario/PROVENANCE.md):

| File | Bytes | What it is |
|---|---:|---|
| `mto-authoritative-electoral-districts-2018-nad83.geojson` | 7,292,979 | 124 features, `ED_ID` 1–124, native EPSG:4269, 196,512 vertices |
| `mgcs-onterm-current-and-former-electoral-districts-en-2022-02-09.csv` | 17,931 | OGL-ON bilingual names: 124 current + 154 former |

Total staged: **7.3 MB** against the 500 MB budget. No file was converted, reprojected, or unzipped.

## Reconciliation with `constituency_boundaries`

**What we hold today.** 123 rows, `level='provincial'`, `province_territory='ON'`:

- `source_set` = `ontario-electoral-districts-representation-act-2015`
- `constituency_id` prefix = `ontario-electoral-districts-representation-act-2015` (⚠ unlike federal/AB/NB, ON's `source_set` and prefix **do** match — Ontario is not one of the divergent jurisdictions)
- Slug half = kebab-cased district name, e.g. `…-act-2015/kitchener-south-hespeler`
- All rows `boundaries_version='current'`, `effective_from='2023-01-01'` (⚠ wrong — the ON order took effect in 2018, not 2023; the date is the loader's hardcoded placeholder), `effective_to=NULL`
- Geometry: 27,064 vertices total, **avg 220/district** — Open North `simple_shape`, already simplified

**Does the authoritative file's ID match ours?** No — `ED_ID` is an integer, our slug is a name. **But the mapping is exact and deterministic, not fuzzy.** Slugifying the authoritative `NAME` (em/en-dash → hyphen, strip apostrophes and periods, ASCII-fold, lowercase, collapse to single hyphens) reproduces our existing slugs with:

- **123 / 123 matched**
- **0 extras** on our side
- **0 name-text differences** on the matched set — including em-dashes and `Toronto—St. Paul's`
- **1 authoritative district absent from our table: `ED_ID` 98, Scarborough Southwest**

★ That is the cleanest reconciliation result available. Ontario needs **no fuzzy matching, no manual crosswalk, and no judgement calls** — the re-key is a deterministic function of a field both sides already carry.

**The two ON anomalies are separate and neither is a re-key problem:**

1. ⚠ **Scarborough Southwest has no boundary row.** Its MPP **Doly Begum** exists in our roster but is unreachable: she has **two active `politicians` rows** — `ola.org:former-mpps:member_id=7508` (carries `ola_slug`/`ola_member_id`, but `constituency_id` **and** `constituency_name` both NULL) and `op:doly-begum` (carries `constituency_name = 'Scarborough Southwest'`, `constituency_id` NULL). Neither row can resolve: the exact join fails on the NULL `constituency_id`, and the `lower(constituency_name)` fallback fails because no boundary named "Scarborough Southwest" exists. She is the 1 unreachable ON provincial rep counted in [`overview.md`](./overview.md). ★ Loading the authoritative 124 fixes the boundary half; the **duplicate-row half is a roster defect** and belongs to the duplicate-politician audit workstream, not to this one.
2. ⚠ **York—Simcoe has a boundary but no active MPP.** Not a data bug — **Caroline Mulroney** (`ola_member_id` 7523) is present with `is_active = false`, updated 2026-08-17. This is a genuine **vacancy** pending a by-election, and the boundary row is correct. No action.

**Recommended cutover.** Ontario should be the **first** option-(d) cutover:

```
authority             = 'elections-ontario'
authority_district_id = ED_ID::text            -- '1'..'124'
constituency_id       = 'ontario-electoral-districts-2018/' || slugify(NAME)
boundaries_version    = 'representation-act-2015-far-north-2017'
effective_from        = DATE '2018-05-08'      -- legal in-force; Rep. Act 2015 s.2(2)
effective_to          = NULL                   -- still in force
```

Keeping the *existing* slug shape for the suffix means the 123 existing `politicians.constituency_id` values need only a prefix rewrite, and Scarborough Southwest is a pure insert. If the prefix is left unchanged as well, **the `politicians` update becomes a no-op entirely** and the cutover is: insert 124 authoritative rows, delete the 123 Open North rows, backfill `authority`/`authority_district_id`. That is the lowest-risk cutover available in the project — recommend it as the pilot that proves the whole strategy.

Sequencing note: the four read paths missing `effective_to IS NULL` (see [`overview.md`](./overview.md) § Known traps) must be fixed first regardless, since two of them are ON-visible (`map.ts:219` no-data overlay, and both politician-detail routes).

## Known traps

- ⚠ **The GeoJSON response has no `crs` member but is NOT WGS84.** The service's native SR is **EPSG:4269 (NAD83)**. RFC 7946 says a GeoJSON document without `crs` is WGS84 — so a naive loader will label NAD83 coordinates as 4326. Passing `outSR=4326` returns **byte-identical coordinates** (ArcGIS applies no datum transformation by default), so the ~1–2 m Ontario NAD83↔WGS84 offset is present on both paths. Immaterial for riding assignment, material for provenance honesty: the build must `ST_Transform(ST_SetSRID(geom, 4269), 4326)`, never `ST_SetSRID(geom, 4326)` alone. This is the Fort Erie failure mode in miniature — the same shape of bug, three orders of magnitude smaller.
- ⚠ **`effective_from` on our existing ON rows is wrong.** All 123 say `2023-01-01`; the order took effect in **2018**. Nothing reads the column yet, so nothing is broken — but do not carry the value forward at cutover.
- ⚠ **MTO is a republisher, not the boundary authority.** The account name `Authoritative_mto_on_ca` is an ArcGIS "authoritative" badge for the Ministry of Transportation, not a statement that MTO draws electoral boundaries. Elections Ontario does. Cite Route A as the source of record even if Route B supplies the bytes during development.
- ✅ **One row per district — checked.** The staged GeoJSON has 124 features and 124 distinct `ED_ID` values (verified contiguous 1–124), so islands are *not* split into separate rows. No duplicate-`constituency_id` hazard on load. Ontario has plenty of island geography (Manitoulin, Toronto Islands, Georgian Bay), so this was worth confirming rather than assuming.
- ⚠ **If the operator takes Route A, the shapefile traps apply and Route B's findings do not transfer.** Route B is a feature service with self-describing field metadata; a downloaded SHP is not. On the Elections Ontario zip, specifically: glob the `.cpg` **case-insensitively** (an uppercase `.CPG` is missed by a lowercase glob and every `—`/accented district name mojibakes); read the `.prj` and expect **no `AUTHORITY` clause**, so identify the EPSG from the projection parameters yourself rather than trusting auto-detection; recount distinct district IDs rather than records; and do not assume Route A's field names match Route B's `ED_ID`/`NAME`/`NAME_FRENCH`.
- ⚠ **Two Elections Ontario licences, easily confused.** "Open Use" (electoral districts) vs "Limited Use" (polling divisions). Quoting the wrong one into the licence matrix would misstate our rights in both directions.

## Addendum — should `authority` / `authority_district_id` also land on the roster side?

Requested by the coordinator after the federal agent found only 11 of 1,873 federal `politician_terms` rows carry a `constituency_id`. Ontario is the right place to answer it because `ola_member_id` is already a real native ID on the roster side. **Recommendation: no — and the premise conflates two different joins.**

**1. The current-state roster join is already healthy; it is the *historical* join that is empty.** Those are different columns serving different purposes:

| Join | Column | Health | Used by |
|---|---|---|---|
| Current-state "who represents this point" | `politicians.constituency_id` | **2,258 / 2,260 active resolve exactly (99.91%)** — federal 342/342, provincial 663/663, municipal 1,253/1,255 | the PIP path (`postcode-reps.ts`, `alerts_worker.py`, `public/postcodes.ts`, `boundaries.ts`) |
| Historical "which riding did this person sit for" | `politician_terms.constituency_id` | federal **0.56%**, provincial 7.11%, municipal 94.81% | Hansard speaker resolution only — **never the PIP path** |

Nothing in the lookup path reads `politician_terms.constituency_id`. Filling it would not move the 135-unreachable-reps number by one.

**2. ★ The three modules that *do* read it want a name, not an ID.** Verified in code:

- `services/scanner/src/legislative/bc_allcaps_resolver.py:197` — selects `pt.constituency_id AS riding` to disambiguate `MR. G.S. WALLACE (Oak Bay)`-shaped labels
- `services/scanner/src/legislative/bc_committees.py:302` — `lower(regexp_replace(pt.constituency_id, '^.*/', ''))`
- `services/scanner/src/legislative/ab_committees.py:263` — same, plus space→hyphen normalisation

All three strip the prefix and match the **suffix against riding names as printed in Hansard and committee documents**. An integer `ED_ID` would be useless to them. This is a positive argument for option (d) as designed — keeping a human-readable slug suffix rather than re-keying to bare integers — and an argument against adding an ID column to the roster, which would serve no existing consumer.

**3. Duplicating district identity on the roster re-creates the bug we are fixing.** `authority_district_id` on both `politicians` and `constituency_boundaries` is two unenforced copies of the same fact with no FK between them — the same shape as today's `constituency_id` problem, one level up. The authoritative ID is one hop away through `constituency_boundaries`; that hop is the normalisation, not a cost.

**4. What the roster side actually needs is a stable *person* ID, not a district ID.** That is CLAUDE.md convention #1 and it is a genuinely separate problem: district identity vs person identity. Ontario already has it (`ola_member_id`, 1,992/1,993 ON politicians, no collisions per [`../ontario.md`](../ontario.md)); the federal proposal of `politicians.ourcommons_person_id` is the correct shape. **Separate migration** — it shares no columns, no tables, and no failure mode with the boundary re-key, and coupling them would make the boundary cutover wait on roster scraping.

### ★ Correction to my own Ontario cutover proposal

Working through this surfaced an error in the § Reconciliation block above, which I have left in place rather than silently rewriting.

I proposed `constituency_id = 'ontario-electoral-districts-2018/' || slugify(NAME)` and advertised that keeping the *existing* prefix would make the `politicians` update a no-op. **Both are wrong, for the same reason: a `constituency_id` prefix must not encode a generation.**

`constituency_id` is generation-independent by design — the unique key is `(constituency_id, boundaries_version)`, so one district string spans every generation and a politician row correctly matches whichever generation is current. Encoding `2018` (or the existing `-representation-act-2015`) into the prefix breaks that: the next Ontario redistribution would force an UPDATE of every `politicians` row *again*, permanently, once per redistribution. The "no-op" I advertised is a false economy that buys one cutover and taxes all future ones.

**Revised recommendation for Ontario:**

```
constituency_id       = 'ontario-electoral-districts/' || slugify(NAME)   -- generation-FREE
boundaries_version    = 'representation-act-2015-far-north-2017'          -- generation lives HERE
authority             = 'elections-ontario'
authority_district_id = ED_ID::text
effective_from        = DATE '2018-05-08'
```

Cost: one 123-row `UPDATE politicians` — trivial. Benefit: Ontario never needs another `politicians` update on redistribution. The three Hansard resolvers above are unaffected, because `regexp_replace(…, '^.*/', '')` is greedy and strips whatever prefix it finds.

**Generalises to a project-wide rule:** *the generation belongs in `boundaries_version` and `effective_from`, never in the `constituency_id` prefix.* Several current prefixes violate it — `federal-electoral-districts-2023-representation-order`, `alberta-electoral-districts-2017`, `new-brunswick-electoral-districts-2018`, `ontario-electoral-districts-representation-act-2015`, `saskatchewan-electoral-districts-representation-act-2012`. Each is a future forced re-key. Recommend the coordinator fold this into `overview.md` § Reconciliation strategy, since it changes the target `constituency_id` shape for every jurisdiction, not just Ontario.

## Research-handoff items

- **Will you accept the Elections Ontario "Open Use Data Product Licence Agreement" and download the electoral district shapefiles?** This is the one blocker on a fully-licensed Ontario boundary set. The licence text is quoted verbatim above and is genuinely open (worldwide, royalty-free, perpetual, commercial use permitted, redistribution permitted, no attribution required) — in my reading it is *more* permissive than OGL-Ontario and clears redistribution through `/api/public/v1/boundaries/*`. The gate is a single "I Agree" button at https://www.elections.on.ca/en/voting-in-ontario/electoral-district-shapefiles/open-use-data-product-licence-agreement.html leading to `.../open-use-data-product-licence-agreement/download-shapefiles.html`. Not clicked, per the standing rule. Note clause 2 ("any use whatsoever of the Information indicates your acceptance") suggests the button is navigation rather than contract formation, but that is your call, not mine.
- **Is Route B acceptable as an interim geometry source for internal use only?** The MTO service is staged and gate-free, but its licence is a bare Crown copyright with a *"not suitable for site-specific use"* disclaimer. My recommendation: use it to build and validate the pipeline, but do **not** serve it through the public API. If Route A is accepted, this question disappears.
- ~~**Confirm the exact statutory in-force date.**~~ ✅ **RESOLVED 2026-08-18** — Representation Act, 2015 s. 2(2) quoted verbatim above; legal in-force date is **2018-05-08**, the dissolution of the 41st Parliament. My earlier placeholder of 2018-06-07 (polling day) was wrong by a month; the MTO metadata date is wrong by 13½ months. See § Effective dates.
- **Prior-generation (107-district) geometry is unresolved.** Not published open. Options are (a) defer — nothing currently reads historical boundaries; (b) ask Elections Ontario directly; (c) accept a third-party AGOL copy, which violates primary-sources-only. **Recommend (a).**
- **Doly Begum has two active `politicians` rows.** Out of scope for boundaries, but it is why Scarborough Southwest will still not resolve cleanly even after the geometry lands. Route to the duplicate-politician audit workstream.

## Status

> ⚠ **Reconciled 2026-09-01.** The checkboxes below are the **research phase's** record
> (closed 2026-08-18) and several were overtaken by the build — migrations `0064`–`0121`,
> merged to `main` 2026-08-28. An unticked box here is **not** evidence that something is
> still outstanding.
>
> **Live counts: [`PROGRESS.md`](./PROGRESS.md)** (generated by `boundary-progress`).
> **What actually landed:** the migration headers, which are the accurate record.
> This file's job is the *reasoning* — sources, licences, traps, vintage evidence.

- [x] Current boundaries located and staged (2026-08-18) — Route B, 124 features, 7.3 MB
- [x] Authoritative district ID identified — `ED_ID`, integer, contiguous 1–124
- [x] District ID reconciliation confirmed — 123/123 exact, 0 name drift, 1 gap (ED_ID 98)
- [x] Missing district identified — **Scarborough Southwest** (MPP Doly Begum)
- [x] Second anomaly resolved — York—Simcoe is a genuine vacancy (Caroline Mulroney, `is_active=false`), not a data defect
- [x] Roster ↔ district mapping route confirmed — OLA `field_last_riding` taxonomy reference
- [x] Licence text recorded verbatim (Open Use + MTO + OGL-ON)
- [x] GeoHub / data.ontario.ca dead ends recorded
- [x] Postal-code concordance question answered — **none published**
- [ ] Licence cleared for redistribution — **blocked: click-through agreement, operator decision required**
- [x] Legal `effective_from` established (2026-08-18) — **2018-05-08**, Rep. Act 2015 s. 2(2); metadata-date discrepancy of 13½ months recorded
- [x] One-row-per-district verified — 124 features / 124 distinct `ED_ID`, no island splitting
- [ ] Prior boundaries located — **not published open; recommend deferring**
