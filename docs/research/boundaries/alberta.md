# Alberta — Electoral Boundary Research

> Standalone boundary/roster dossier for Alberta. Cross-cutting context
> (methodology, licence matrix, reconciliation strategy) lives in [`overview.md`](./overview.md).
> The legislative-data dossier for this jurisdiction is at [`../alberta.md`](../alberta.md).

**Agency:** Elections Alberta / Alberta Electoral Boundaries Commission | **Website:** https://www.elections.ab.ca | **Districts (current):** 87 | **Current order:** *Electoral Divisions Act* (2017 commission; divisions first used at the 2019 general election) | **Next redistribution:** ★ **final report already delivered 2026-03-23, proposing 89 divisions — not yet enacted**

**Status snapshot (2026-08-18):** ✅ **Cleanly solved — the easiest jurisdiction in the project so far.** Alberta publishes its 87 provincial electoral divisions through a Government of Alberta ArcGIS MapServer under the **Open Government Licence – Alberta**, which permits commercial use *and* redistribution with a mandatory attribution string. No click-through, no registration, no WAF. ✅ **Current *and* prior generations both staged** from the same service (layer 3 = 2019 current, layer 4 = 2010 historical; layer 5 = 2003 also exists). ✅ **Perfect reconciliation: 87/87, zero gaps, zero extras, zero name drift**, with `EDNUMBER` (1–87) as a clean authority key. ★ **Vintage verified by measurement, not by counting**: our geometry matches the 2019 current generation at **99.887% mean overlap** (0 districts below 95%) versus **81.275%** against the 2010 prior generation — **the Alberta rows are correct and current, and the Saskatchewan silent-redraw failure mode is ruled out.** ★ **The one real defect is metadata, exactly as suspected**: `source_set = 'alberta-electoral-districts'` while every `constituency_id` carries the prefix `alberta-electoral-districts-2017` — one of the three set/prefix divergences in the table. ⚠ **Known expiry**: the 2025-26 Electoral Boundaries Commission reported **2026-03-23** recommending **89** divisions; our 87 are correct today but will go stale the moment that map is enacted.

---

## Current boundaries

- **Source URL(s):** https://geospatial.alberta.ca/titan/rest/services/boundary/goa_administrative_area_10tm_nad83_aep/MapServer/3 ; https://open.alberta.ca/api/3/action/package_show?id=gda-e201c640-1f76-429c-8c24-89ff496f956e ; https://geodiscover.alberta.ca/geoportal/rest/metadata/item/0999f0448e384d81981ff82b25656d16/xml
- **Format:** ArcGIS MapServer layer — serves GeoJSON directly via `?f=geojson`; no zip, no shapefile handling
- **CRS / projection:** ⚠ **Two answers, and this matters.** The service's declared native SR is **EPSG:3400** (`wkid 102184 / latestWkid 3400`, *NAD83 / Alberta 10-TM (Forest)* — projected, metres), which is what the service path `_10tm_nad83_` advertises. But a `f=geojson` request returns **decimal degrees** — ArcGIS reprojects on the way out. The staged file is therefore already geographic. See § Known traps.
- **Attribute schema:** `OBJECTID` (OID), **`EDNUMBER` (String)**, `EDNAME` (String), `EDPROV` (String), `MLA_TITLE` (String), `MLA_FNAME` (String), `MLA_LNAME` (String), `SHAPE` (Geometry), `GlobalID` (GlobalID). Read from the layer's own field metadata.
- **District ID field:** ★ **`EDNUMBER`** — numeric string, values `'1'`–`'87'`, **87 distinct**. Not zero-padded (unlike `politicians.ab_assembly_mid`, which is — see § District ↔ elected official mapping). **Does not match what we store** (our slug is the kebab-cased name), but the mapping is exact and deterministic — see § Reconciliation.
- **Effective date:** **2019-04-16** (the 30th general election, first use) — ⚠ `needs confirmation` against the *Electoral Divisions Act*'s own commencement provision; see § Effective dates.
- **District count:** **87** (verified by `returnCountOnly`) — matches the seat count
- **Difficulty (1–5):** **1** — documented, catalogued on the provincial open-data portal, queryable, openly licensed, no gate
- **Notes:** `capabilities: Map,Query,Data`; `maxRecordCount` 1000 > 87, so one request returns everything. The GoA dataset title is *"Provincial Electoral Division - **Current 2019**"* — note **2019** (first election using the divisions), where our prefix says **2017** (the commission/Act year). Both refer to the same generation; see § Reconciliation for which to prefer. Staged file: **265,272 vertices, avg 3,049/division** against our 36,792 / avg 423 — **7.2× more geometric detail**. The layer's `MLA_*` fields carry the sitting member's name, but they are a convenience snapshot and must not be treated as a roster source — `politicians` is the roster.

## Prior boundaries (immediately preceding)

- **Source URL(s):** https://geospatial.alberta.ca/titan/rest/services/boundary/goa_administrative_area_10tm_nad83_aep/MapServer/4
- **Format:** same MapServer, layer 4, *Provincial Electoral Division - Historical 2010*
- **CRS / projection:** identical to current — declared EPSG:3400, `f=geojson` emits degrees
- **Attribute schema:** **identical** to layer 3 (`EDNUMBER`, `EDNAME`, `EDPROV`, `MLA_*`) — the two generations share one schema, so a single loader handles both
- **District ID field:** `EDNUMBER`, 87 distinct
- **Effective date:** 2012-04-23 (28th general election, first use of the 2010 commission's divisions) — `needs confirmation`
- **Superseded date:** the day before the 2019 divisions took effect → becomes `effective_to`; see § Effective dates
- **District count:** **87** — Alberta held 87 seats in both generations, so the count is unchanged; the *boundaries and names* are what moved
- **Difficulty (1–5):** **1** — same service, same licence
- **Notes:** ★ Alberta is the only jurisdiction researched so far that ships its **prior** generation from the same openly-licensed endpoint as its current one. Name diff between generations: **29 names dropped, 29 added** (e.g. `Airdrie` → `Airdrie-Cochrane` + `Airdrie-East`; `Banff-Cochrane` → `Banff-Kananaskis`; `Athabasca-Sturgeon-Redwater` + `Barrhead-Morinville-Westlock` → `Athabasca-Barrhead-Westlock`). 58 of 87 names are stable across the boundary change — ⚠ **a name-keyed join would silently mismatch those 58**, attaching 2010 geometry to 2019 districts. This is the clearest argument in the project for `EDNUMBER`-keyed loading over name matching. Layer 5 (*Historical 2003*) exists for a third generation; not staged.

## District ↔ elected official mapping

Roster source is unchanged from the legislative pipeline: `assembly.ab.ca`, already live, keyed by **`politicians.ab_assembly_mid`** (zero-padded text, UNIQUE partial index per migration `0031`, populated back to 1906 by `ab_former_mlas.py` — see [`../alberta.md`](../alberta.md)).

⚠ **`ab_assembly_mid` is a *member* ID, not a district ID.** It identifies an MLA, not an electoral division, so it cannot serve as the boundary authority key. The two IDs answer different questions and both are needed.

**Does Elections Alberta or the Assembly expose a district identifier?** ✅ Yes — **`EDNUMBER`** on the GoA geospatial layer, which is the Government of Alberta's own numbering of the divisions. That is the authority key for option (d). ⚠ Note the padding difference: `EDNUMBER` is **unpadded** (`'1'`, `'87'`) while `ab_assembly_mid` is **zero-padded**; do not assume a shared convention just because both are numeric-looking text. `UNTESTED — probe during build`: whether the Assembly's own member pages expose the same division number, which would give a direct `EDNUMBER` ↔ MLA join and remove the last name-matching step from AB.

## Postal-code correspondence (if published)

⛔ **None published.** Elections Alberta offers an interactive "find your division" lookup only. Per the standing ruling this is not worth further budget — our lookup is point-in-polygon and an authoritative polygon beats a weighted postal concordance. One line, recorded, moving on.

## Terms / Licensing

### ✅ Open Government Licence – Alberta

Licence URL: https://open.alberta.ca/licence. The dataset's CKAN record (`gda-e201c640-1f76-429c-8c24-89ff496f956e`) declares `license_title: "Open Government Licence - Alberta"`. Operative clauses, verbatim:

> **Using Information under this licence**
>
> Use of any Information indicates your acceptance of the terms below.
>
> The Information Provider grants you a worldwide, royalty-free, perpetual, non-exclusive licence to use the Information, including for commercial purposes, subject to the terms below.
>
> **You are free to:**
>
> Copy, modify, publish, translate, adapt, distribute or otherwise use the Information in any medium, mode or format for any lawful purpose.
>
> **You must, where you do any of the above:**
>
> Acknowledge the source of the Information by including any attribution statement specified by the Information Provider(s) and, where possible, provide a link to this licence.
>
> If the Information Provider does not provide a specific attribution statement, or if you are using Information from several Information Providers and multiple attributions are not practical for your product or application, you must use the following attribution statement:
>
> > Contains information licensed under the Open Government Licence – Alberta.
>
> The terms of this licence are important, and if you fail to comply with any of them, the rights granted to you under this licence, or any similar licence granted by the Information Provider, will end automatically.
>
> **Exemptions**
>
> This licence does not grant you any right to use:
> Personal Information;
> Information or Records that are not accessible under applicable laws;
> third party rights the Information Provider is not authorized to license;
> the names, crests, logos, or other official symbols of the Information Provider; and
> Information subject to other intellectual property rights, including patents, trade-marks and official marks.
>
> **Non-endorsement**
>
> This licence does not grant you any right to use the Information in a way that suggests any official status or that the Information Provider endorses you or your use of the Information.

**Analysis.** Use ✅ and redistribution ✅ are both granted, including commercially, so serving Alberta boundary GeoJSON from `/api/public/v1/boundaries/*` is permitted. ⚠ **Attribution is a hard condition, not a courtesy** — the licence terminates *automatically* on non-compliance. The required string is exactly:

> Contains information licensed under the Open Government Licence – Alberta.

⚠ The **Exemptions** clause excludes "the names, crests, logos, or other official symbols of the Information Provider" — irrelevant to polygons, but it also excludes **Personal Information**, which is worth a moment's thought given the layer's `MLA_TITLE` / `MLA_FNAME` / `MLA_LNAME` fields. Sitting MLAs' names in their official capacity are not personal information in the PIPA sense, but the cleanest course is simply **not to ingest those three columns** — we have a roster, and the fields add nothing.

★ This licence is materially better than what the Open North mirror gave us. Per [`overview.md`](./overview.md), our current AB rows arrive via Open North's Represent API under a chain we never had rights to redistribute. **Loading from the GoA service replaces an unlicensed mirror with a properly licensed primary source** — a compliance improvement independent of the data-quality improvement.

## Rate limits / auth

- **`geospatial.alberta.ca` MapServer:** no authentication, no API key, no observed rate limiting. Full 87-feature GeoJSON (10.8 MB) retrieved in a single request; prior generation likewise (11.1 MB). `maxRecordCount` 1000.
- **`open.alberta.ca` CKAN:** standard CKAN Action API, no auth. Fronted by Cloudflare; `https://open.alberta.ca/licence` returned HTTP 520 to one client and HTTP 200 to a polite-UA `curl` moments later — **transient, not a block**. No challenge, no WAF.
- **`www.elections.ab.ca`:** static pages, served without challenge. `abebc.ca` 301-redirects to `www.elections.ab.ca/resources/reports/electoral-boundaries-commission/`.
- **No robots.txt violations observed.** No page fetched during this pass contained text addressed to an AI agent.

## Staged files

Under `data/boundaries/alberta/`, with hashes and URLs in
[`../../../data/boundaries/alberta/PROVENANCE.md`](../../../data/boundaries/alberta/PROVENANCE.md):

| File | Bytes | What it is |
|---|---:|---|
| `current/goa-provincial-electoral-division-current-2019.geojson` | 10,827,816 | 87 features, `EDNUMBER` 1–87, 265,272 vertices |
| `prior/goa-provincial-electoral-division-historical-2010.geojson` | 11,052,841 | 87 features, prior generation, identical schema |

Total staged: **21 MB** against the 500 MB budget. No file was converted, reprojected, or unzipped locally.

## Effective dates — legal vs metadata

Applying the `effective_from` ruling (use the **legal in-force date**, record the metadata date as a discrepancy).

| | Date | Basis | Confidence |
|---|---|---|---|
| Legal in-force (current) | **2019-04-16** | 30th general election, first use of the 2017 commission's divisions | ⚠ `needs confirmation` — I did not locate a commencement provision in the *Electoral Divisions Act* fixing a date independent of the election |
| ⚠ Dataset metadata | dataset titled *"Current **2019**"* | GoA open-data catalogue | recorded as discrepancy |
| ⚠ Our current prefix says | **2017** | the commission / Act year, not the in-force year | recorded as discrepancy |
| Legal in-force (prior) | 2012-04-23 | 28th general election, first use of the 2010 commission's divisions | ⚠ `needs confirmation` |
| Superseded (prior) | 2019-04-15 | day before the current set took effect | derived |

⚠ **Alberta is a genuinely harder date case than Ontario or Nova Scotia**, and I am flagging that rather than inventing precision. Ontario's Representation Act, 2015 states its trigger explicitly ("immediately after the first dissolution of the Legislature after November 30, 2016"); Nova Scotia's amending Act has a datable Royal Assent. Alberta's *Electoral Divisions Act* is a schedule of division descriptions, and I did not establish whether it commences on Royal Assent, on proclamation, or on the first writ after a date. **Three candidate dates are in play (2017 Act, 2018 Act chapter cited in the GoA metadata as "Alberta Election Act, Chapter E-1, 2018", 2019 first use) and they differ by up to two years.** Raised as a handoff item.

⚠ **Our 87 existing rows carry `effective_from = '2023-01-01'`**, the loader's hardcoded placeholder — fiction, like every other row in the table. Do not carry it forward.

⚠ **Do not read a consolidation date as a commencement date.** Alberta's King's Printer serves consolidated statutes that carry "current as of" / revision fields; those record when the consolidation was cut, not when the instrument came into force, and the two can differ by years. The date must come from the **commencement trigger inside the instrument** plus the triggering event. That is precisely why the three candidate dates above are unresolved rather than guessed — the GoA metadata's *"Alberta Election Act, Chapter E-1, 2018"* citation is the kind of field that invites this error, and it has **not** been adopted as `effective_from`.

**Attribution obligation.** OGL-Alberta makes attribution a hard condition, so unlike Ontario (whose Open Use licence has no attribution clause) **Alberta requires a per-row attribution string to be surfaced on the public boundary API**. The implementation surface is small: `shapeBoundary()` at `services/api/src/routes/public/boundaries.ts:381` is the sole shaping function and `shapeBoundaryWithGeoJson` spreads it at `:401`, so list, lookup and detail all route through one of the two — a single added field covers the entire public boundary surface. Required string, exactly:

> Contains information licensed under the Open Government Licence – Alberta.

## Reconciliation with `constituency_boundaries`

**What we hold today.** 87 rows, `level='provincial'`, `province_territory='AB'`:

- `source_set` = **`alberta-electoral-districts`**
- `constituency_id` prefix = **`alberta-electoral-districts-2017`**
- ★ **These differ** — Alberta is one of only three set/prefix divergences in the whole table (with federal and NB). Cause, per [`overview.md`](./overview.md): `_upsert_boundary` writes `source_set = set_def.boundary_set` (the *representative set's* configured value) while `constituency_id` is parsed from each rep's `boundary_url`. Neither is wrong; they come from different places in the same API response. **Consequence:** the public detail route `/boundaries/:source_set/:slug` rebuilds `constituency_id` from its path params, so `/boundaries/alberta-electoral-districts/calgary-bow` **404s** and only `/boundaries/alberta-electoral-districts-2017/calgary-bow` resolves. The parameter is misnamed, not the data.
- Slug half = kebab-cased division name, e.g. `alberta-electoral-districts-2017/airdrie-cochrane`
- All rows `boundaries_version='current'`, `effective_from='2023-01-01'`, `effective_to=NULL`
- Geometry: 36,792 vertices, **avg 423/division** — Open North `simple_shape`
- Roster join: **87 active AB MLAs, 87 with a `constituency_id`, 87 resolving.** No orphans, no name-fallback reliance.

**Does the authoritative file's ID match ours?** No — `EDNUMBER` is a number, our slug is a name. **But the mapping is exact.** Slugifying `EDNAME` (dash-fold, strip apostrophes/periods, ASCII-fold, lowercase, collapse) reproduces our slugs with:

- **87 / 87 matched**
- **0 authoritative divisions missing from our table**
- **0 rows in our table absent upstream**
- **0 name-text differences**

Alberta needs no fuzzy matching and no manual crosswalk — the same clean result as Ontario, with the added advantage that there is no missing district to insert.

**What the correct prefix should be.** Neither current value. Per the rule established in [`ontario.md`](./ontario.md) § Addendum — **a `constituency_id` prefix must not encode a generation**, because the column is generation-independent (unique key is `(constituency_id, boundaries_version)`) and baking a year in forces a full `politicians` UPDATE at every redistribution. `alberta-electoral-districts-2017` violates this and would have to be rewritten again in 2027. Recommended:

```
constituency_id       = 'alberta-electoral-districts/' || slugify(EDNAME)   -- generation-FREE
                        -- also fixes the set/prefix divergence: this IS the current source_set
source_set            = 'alberta-electoral-districts'                        -- unchanged
authority             = 'elections-alberta'
authority_district_id = EDNUMBER                                             -- '1'..'87'
boundaries_version    = 'electoral-divisions-act-2017'
effective_from        = DATE '2019-04-16'                                    -- needs confirmation
effective_to          = NULL
```

★ Note the elegance: dropping `-2017` from the prefix simultaneously (a) removes the generation encoding and (b) **closes the set/prefix divergence**, because the de-generationed prefix is exactly the existing `source_set` value. One change fixes both defects. Cost is one 87-row `UPDATE politicians`.

### ★ Vintage verification — measured, not inferred

A full district count proves only that every rep linked to *something*. Alberta passes 87/87, which is exactly the profile that hides a Saskatchewan-style silent redraw (SK holds 61 seats across both its 2012 and 2022 maps). So the count was disregarded and the geometry measured directly.

**Method.** Authoritative per-district areas computed in PostGIS from the staged GeoJSON with `ST_Area(geom::geography)/1e6` — the *identical* formula that produced our stored `area_sqkm`, so the two are directly comparable. Overlap computed as `ST_Area(ST_Intersection(ours, authoritative)::geography) / ST_Area(authoritative::geography)`. Run read-only against both candidate generations. **Alberta is landlocked**, so there is no marine-envelope or island-parts drawing-convention confound and area is a trustworthy comparator here.

| Candidate generation | n | unmatched | mean abs area error | max area error | mean overlap | min overlap | districts < 95% overlap |
|---|---:|---:|---:|---:|---:|---:|---:|
| **2019 current (2017 commission)** | 87 | **0** | **0.046%** | 0.324% | **99.887%** | 99.583% | **0** |
| 2010 prior | 87 | 29 | 22.465% | 107.540% | 81.275% | 16.449% | 33 |

> ✅ **Our geometry matches the 2019 (2017-commission) generation to 99.89%, therefore the Alberta rows are CORRECT and CURRENT — not stale, not misassigned.**

The 0.046% residual is Open North's `simple_shape` simplification, not a boundary difference. The 2010 comparison is the control and behaves exactly as a wrong-vintage result should: 29 districts whose names no longer exist, a third of the province below 95% overlap, and one district at 16% — the same signature that settled New Brunswick.

★ **This rules out the Saskatchewan failure mode for Alberta.** AB has *not* redrawn while holding 87 seats. That is consistent with the independent legislative evidence: the 2025-26 commission only reported on **2026-03-23** and its 89-division map is not enacted, so the 2017-commission divisions remain the current legal generation — which is also why the GoA portal serving a "Current 2019" layer is the current generation and not a portal lagging reality (the A8.3 trap does not bite here, and was checked rather than assumed).

**Cutover ordering.** Alberta is a strong second cutover after Ontario: same clean reconciliation, plus it exercises two things Ontario cannot — **loading a prior generation** (so it is the first real test of the `boundaries_version` / `effective_to` machinery that migration `0021` built and nobody has ever run) and **fixing a set/prefix divergence**. Recommend AB immediately after ON, and before any jurisdiction with an actual data gap.

## Known traps

- ⚠ **The service path says 10TM but `f=geojson` returns degrees.** Native SR is EPSG:3400 (projected, metres); the GeoJSON export is already reprojected to geographic, with **no `crs` member** in the response. So the staged files must **not** be given `ST_SetSRID(geom, 3400)` — that would place Alberta somewhere in the Gulf of Guinea. But a build that re-fetches with `f=json` instead of `f=geojson` **will** get 10TM metres and **must** transform. The correct incantation depends on the request format, which is an unusually easy thing to get wrong six months from now.
- ⚠ **58 of 87 division names are unchanged between the 2010 and 2019 generations, but their boundaries moved.** A name-keyed load of both generations would attach the wrong geometry to those 58 without erroring. Key on `EDNUMBER` + `boundaries_version`.
- ⚠ **`EDNUMBER` is not zero-padded; `ab_assembly_mid` is.** Two numeric-looking text columns in the same jurisdiction with different padding conventions. They also identify different things (division vs member).
- ⚠ **`EDNUMBER` is not stable across generations.** Both layers number 1–87, but the 2010 `EDNUMBER` 12 and the 2019 `EDNUMBER` 12 are not the same place. The authority key is unique *within* a generation only — which is exactly why the proposed unique constraint is `(authority, authority_district_id, boundaries_version)` and not `(authority, authority_district_id)`.
- ⚠ **Do not ingest `MLA_TITLE` / `MLA_FNAME` / `MLA_LNAME`.** A stale roster snapshot embedded in a boundary file, and the OGL-Alberta Exemptions clause carves out Personal Information. We have `politicians`.
- ⚠ **The `2017` / `2018` / `2019` labelling is genuinely ambiguous.** Our prefix says 2017 (commission), the GoA dataset title says 2019 (first election), and the GoA metadata description cites *"the Alberta Election Act, Chapter E-1, 2018"*. All three refer to one generation. Pick `boundaries_version` deliberately and document it, rather than inheriting whichever label a given source happened to use.

## Research-handoff items

- **Confirm Alberta's legal in-force date for the 87-division set.** This is the one thing I could not establish to the standard the `effective_from` ruling asks for. Three candidate dates (2017 commission report / the 2018 Act chapter cited in GoA metadata / 2019 first use) span two years. Resolving it needs the commencement provision of the *Electoral Divisions Act* from the Alberta King's Printer — https://kings-printer.alberta.ca/documents/Acts/E03.pdf and https://open.alberta.ca/dataset/e04p3 are the leads. I have used **2019-04-16** with an explicit `needs confirmation` marker, per the ruling's fallback.
- **★ Alberta will need a second cutover, and there is a window to plan for it.** The 2025-26 Electoral Boundaries Commission delivered its final report **2026-03-23** proposing **89** divisions (the increase from 87 was authorised in advance by the *Justice Statutes Amendment Act, 2024*, formerly Bill 31). I found **no evidence the new map has been enacted** as of 2026-08-18, and the GoA geospatial service still publishes only the 87-division "Current 2019" layer with no 89-division sibling — consistent with it not being in force. Alberta's next fixed-date general election is due **2027**. **Recommend a watch on the GoA service for a new layer**, since its appearance is the cleanest available signal that the map has changed. This is the first jurisdiction where we can see a redistribution coming rather than discovering it after the fact — a good test of whether the temporal model actually works.
- **Should we ingest the 2003 generation too?** Layer 5 (*Historical 2003*) is available under the same licence at no extra cost. Out of scope for this pass; flagging because the marginal effort is near zero if historical lookups ever become a feature.

## Status

- [x] Current boundaries located and staged (2026-08-18) — 87 features, 10.8 MB
- [x] Prior boundaries located and staged (2026-08-18) — 87 features, 11.1 MB, identical schema
- [x] Licence cleared for internal use — **OGL-Alberta**
- [x] Licence cleared for redistribution — **OGL-Alberta, attribution mandatory and automatically terminating**
- [x] Authoritative district ID identified — `EDNUMBER`, 1–87
- [x] District ID reconciliation confirmed — 87/87 exact, 0 gaps, 0 extras, 0 name drift
- [x] Set/prefix divergence diagnosed, and a fix identified that closes it as a side effect
- [x] One-row-per-district verified — 87 features / 87 distinct `EDNUMBER`, both generations
- [x] ★ **Vintage verified by measurement (2026-08-18)** — 99.887% mean overlap vs 2019 current (0 districts <95%) against 81.275% vs 2010 prior (33 districts <95%). **Rows are correct and current; the Saskatchewan silent-redraw failure mode is ruled out.**
- [x] Attribution string identified and implementation surface located (`public/boundaries.ts:381`)
- [x] Next redistribution identified — 2025-26 commission reported 2026-03-23, 89 divisions, not yet enacted
- [ ] Legal `effective_from` confirmed — **needs confirmation; three candidate dates spanning two years**
- [ ] 89-division map enactment — **pending; watch the GoA service for a new layer**
