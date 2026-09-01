# Nova Scotia — Electoral Boundary Research

> Standalone boundary/roster dossier for Nova Scotia. Cross-cutting context
> (methodology, licence matrix, reconciliation strategy) lives in [`overview.md`](./overview.md).
> The legislative-data dossier for this jurisdiction is at [`../nova-scotia.md`](../nova-scotia.md).

**Agency:** Elections Nova Scotia | **Website:** https://electionsnovascotia.ca | **Districts (current):** ★ **56** (not 55) | **Current order:** *House of Assembly Act* as amended by Bill 205, Royal Assent 2026-04-09, implementing the 2025 Electoral Boundaries Commission | **Next redistribution:** no commission struck; the statutory cycle runs off the 2025 commission

**Status snapshot (2026-08-18):** ⛔ **Two problems, and the second one was not on the brief.** **(1) Licence: unresolved and there is no open route.** Elections NS publishes no licensed open-data product for provincial electoral boundaries; its only machine-readable surface is an AGOL feature service with `licenseInfo: null` and the description *"DO NOT DELETE Electoral Geography for refence in applications"* — an internal service that happens to be public. The NS Open Data portal carries **no** provincial electoral boundary dataset (only *municipal* polling districts). The Open North grant we currently rely on is the non-transferable *"Distributed with permission from the Government of Nova Scotia"* class. **We have no right to redistribute NS boundaries today, and I found no way to acquire one without contacting the agency.** **(2) ★ Nova Scotia is NOT numerically complete — it is 56 districts, not 55.** A NS Supreme Court Charter ruling forced a 2025 commission; Bill 205 (RA **2026-04-09**) split Inverness, creating **Chéticamp-Margarees-Pleasant Bay** (`ED_NO` 56, ~3,889 electors, byelection pending). So we are **missing one district and serving a misassigned polygon for a second**. ★ **Both quantified by intersection, not inferred**: 54 of 56 districts match the current generation at **99.9% overlap in both directions** (0 below 95%), but our `Inverness` polygon is only **60.08% valid** — the 1,946.2 km² excess matches authoritative Chéticamp's 1,946.5 km² to **0.015%**, and **99.99% of Chéticamp-Margarees-Pleasant Bay currently resolves to the Inverness MLA**. This is *not* a Saskatchewan-style whole-province silent redraw; it is a surgical two-district defect with a known cause, date, and fix. ⚠ The authoritative geometry is published as **1,817 polling divisions**, not 56 districts. ✅ No WAF encountered on any Elections NS or NS government host.

---

## Current boundaries

- **Source URL(s):** https://services6.arcgis.com/SLbygoAaBbarfQVN/arcgis/rest/services/ENS_PD_ED/FeatureServer/0 ; https://www.arcgis.com/sharing/rest/content/items/d9e8704a97f94dd9b517383c1e4e2c07?f=json
- **Format:** ArcGIS Feature Service — GeoJSON via `?f=geojson`
- **CRS / projection:** ⚠ Declared SR is **EPSG:3857 (Web Mercator)** — a *display* projection, not a data CRS, and itself a signal that this is a web-map service rather than a published data product. As with Alberta, `f=geojson` returns **decimal degrees** (ArcGIS reprojects on export) with **no `crs` member**.
- **Attribute schema:** `OBJECTID` (OID), **`ED_NO` (String, zero-padded `'01'`–`'56'`)**, `ED_NAME` (String), **`PD_NO` (String)**, `IND_POLL` (String), `RES_CARE` (String), `SERVICE_AREA` (String), `RELEASE_DATE` (String — *not* a date type), `electorcount` (Double), `Shape__Area`, `Shape__Length`.
- **District ID field:** ★ **`ED_NO`** — zero-padded numeric string, 56 distinct values. `ED_NO` alone is **not** unique in this file; `(ED_NO, PD_NO)` is (1,817 distinct pairs, verified).
- **Effective date:** ✅ **2026-04-09** — Royal Assent of Bill 205; see § Effective dates
- **District count:** ★ **56** — and this is the finding. The seat count is 56, up from 55. We hold 55.
- **Difficulty (1–5):** **2** — undocumented but structured and queryable; downgraded from 1 only because it is not a published data product and carries no licence
- **Notes:** ⚠ **The file is polling divisions, not districts** — 1,817 features for 56 districts (~32 polls per district). Loading it naively creates 1,817 `constituency_boundaries` rows. The build must dissolve on `ED_NO`. This is the one-row-per-district trap in its most extreme form found anywhere in this project so far. `capabilities: Query` only — **no `Extract`**, unlike Ontario's and Alberta's services; retrieval requires paging (`maxRecordCount` 2000, but 400/request keeps responses manageable). The item is owned by `Andrew.Cameron_ElectionsNS`, an Elections Nova Scotia staff account, and was last modified **2026-04-14**.

### Dead ends — do not re-probe

- ⛔ **NS Open Data portal (`data.novascotia.ca`, Socrata).** Searched `electoral`, `electoral district boundaries`, `constituency`, `provincial boundaries` scoped to the NS domain. **No provincial electoral boundary dataset.** The only boundary-shaped hits are *Municipal Polling Districts* (municipal, NS-OGL) and CBRM municipal districts — wrong level. The unscoped Socrata catalogue is federated and returns PEI/NB/US datasets for these queries; **always scope with `domains=` + `search_context=`** or the results are noise.
- ⛔ **`nsgi.novascotia.ca/arcgis/rest/services`** — HTTP 404, no service directory at that path.
- ⛔ **`electionsnovascotia.ca`** — a JavaScript SPA with a catch-all 404 shell (every unknown path returns the same 1,138-byte document, including `/sitemap.xml`). Path guessing is unproductive; the AGOL account is the machine-readable surface.
- ⛔ **AGOL global search** — apart from the Elections NS account, hits are municipal (HRM polling districts, Antigonish, Wolfville, Kings) or other provinces. `owner:Andrew.Cameron_ElectionsNS` returns 15 items, of which `ENS_ED_PD` is the only electoral geography; the rest are basemaps, logos, historic poll locations, and PDFs.

## Prior boundaries (immediately preceding)

- **Source URL(s):** none needed — see Notes
- **Format:** n/a
- **CRS / projection:** n/a
- **Attribute schema:** n/a
- **District ID field:** n/a
- **Effective date:** 2019 (the 2019 Electoral Boundaries Commission's 55-district set, restoring the Acadian protected constituencies of Argyle, Clare and Richmond and the African Nova Scotian district of Preston)
- **Superseded date:** **2026-04-08** — the day before Bill 205's Royal Assent
- **District count:** **55**
- **Difficulty (1–5):** **1** — we already hold it
- **Notes:** ★ **Nova Scotia's prior generation is the 55 rows already in `constituency_boundaries`.** This is a genuinely useful accident: NS is the only jurisdiction so far where the stale data we hold *is* the correct immediately-preceding generation, so the cutover can retain those rows with an `effective_to` rather than deleting them. It is also the project's first natural opportunity to exercise the two-generation temporal model with data already on disk. ⚠ One caveat: they are Open North `simple_shape` derivatives under an unclear licence, so they are fit for *historical* answers but should be re-sourced if licence-clean history ever matters. The pre-2019 51-district (2012) set was **not** located on any open surface; the Open North upstream carries an `ns/2012` directory under the same non-transferable "distributed with permission" grant.

## District ↔ elected official mapping

Roster source is unchanged from the legislative pipeline: `nslegislature.ca`, keyed by **`politicians.nslegislature_slug`** (see [`../nova-scotia.md`](../nova-scotia.md)).

⚠ **`nslegislature_slug` is a member slug, not a district ID** — same distinction as Alberta's `ab_assembly_mid`. The district authority key is `ED_NO` from the Elections NS service.

**Roster state today:** 55 active NS MLAs, 55 with a `constituency_id`, 55 resolving — no orphans, no name-fallback reliance. ★ But note what that *conceals*: the roster is complete against the **old** 56-seat-minus-one map. There is no MLA row for Chéticamp-Margarees-Pleasant Bay because **the seat is vacant pending a byelection** — the news release states the new riding's MLA will be chosen at a byelection while Inverness's sitting member continues until the next general election. So a "100% resolving" roster metric reads as healthy here while the underlying map is a district short. **A complete roster join is not evidence of complete boundary coverage** — worth remembering for other jurisdictions.

`UNTESTED — probe during build`: whether `nslegislature.ca` exposes an `ED_NO`-equivalent district number that would give a direct district↔member join.

## Postal-code correspondence (if published)

⛔ **None published.** Elections NS offers an interactive lookup only. Per the standing ruling, one line and move on — our lookup is point-in-polygon and an authoritative polygon beats a weighted postal concordance.

## Terms / Licensing

### ⛔ Elections Nova Scotia AGOL service — no licence stated

The authoritative geometry source carries **no licence whatsoever**:

- AGOL item `d9e8704a97f94dd9b517383c1e4e2c07`: `licenseInfo: null`, `accessInformation: null`, `access: public`
- FeatureServer `copyrightText`: `""` (empty string)
- Item description, verbatim: *"DO NOT DELETE Electoral Geography for refence in applications."*
- Item snippet: *"Elections Nova Scotia 2026 Electoral Geography Electoral Districts and Polling Divisions"*; service description still reads *"Elections Nova Scotia 2019 Electoral Geography…"*

`access: public` is an ArcGIS **sharing** setting, not a copyright licence. It means anyone may read the service; it says nothing about reuse or redistribution rights. The description makes plain this is an internal service backing Elections NS's own applications, exposed publicly so those applications work — not a data publication. **Nothing here grants us redistribution rights.**

### ⛔ No NS Open Government Licence product exists for this data

Nova Scotia does operate an open-data portal with a real licence (*Nova Scotia Open Government Licence*), and plenty of NS geospatial data is published under it — but **not provincial electoral boundaries**. Confirmed across four scoped searches (§ Dead ends). *Municipal Polling Districts* is NS-OGL but is the wrong level of government.

### ⛔ The upstream grant we currently rely on is non-transferable

Per [`overview.md`](./overview.md) § licence audit, NS provincial is one of the *"Distributed with permission from…"* class in `represent-canada-data`. Verbatim, in full:

> Distributed with permission from the Government of Nova Scotia.  Please direct licensing inquiries and requests to:
>
> Pierre L. Gareau
> GIS Manager
> Elections Nova Scotia
> Tel: 1-902-424-0408
> Fax: 1-902-424-6622
> gareaupl@gov.ns.ca

The permission is **Open North's**, and the file's own text directs any other party to seek their own. This grants us nothing. Our **55 NS rows are, today, redistributed through `/api/public/v1/boundaries/*` without a licence** — a live compliance gap, not a theoretical one.

### Assessment

| Route | Use | Redistribute |
|---|---|---|
| Elections NS AGOL service | ⚠ arguable (publicly readable, no stated terms) | ⛔ **no** |
| Open North mirror (current) | ⚠ arguable | ⛔ **no** — permission is Open North's |
| NS Open Government Licence | — | ⛔ **n/a — no such product exists** |

⛔ **There is no open route.** Unlike Ontario (where a click-through hid a genuinely open licence) and Alberta (openly licensed outright), Nova Scotia has no licensed path that research alone can unlock. **This requires contacting Elections Nova Scotia.** See § Research-handoff items.

## Rate limits / auth

- **Elections NS AGOL FeatureServer:** no authentication, no rate limiting observed. `capabilities: Query` only (no `Extract`). `maxRecordCount` 2000; retrieved 1,817 features as 5 paged requests of 400 without throttling.
- ✅ **No WAF encountered anywhere on this pass.** Worth stating plainly because the brief flagged it: `nslegislature.ca` returned **HTTP 200** (299 KB, fully parseable) for the Assembly-65 bills listing with a polite bot UA. The `waf-budget` blocker recorded in `jurisdiction_sources` and [`../nova-scotia.md`](../nova-scotia.md) concerns the **per-bill-page fetch budget** during bulk Hansard/bills scraping, not the listing pages, and it did not bite here. `news.novascotia.ca` is Cloudflare-fronted and returned HTTP 403 to one client then HTTP 200 to a polite-UA `curl` — transient, not a block. No UA spoofing or evasion was used on any host.
- **No robots.txt violations observed.** No page fetched during this pass contained text addressed to an AI agent.

## Staged files

Under `data/boundaries/nova-scotia/current/`, with hashes and URLs in
[`../../../data/boundaries/nova-scotia/PROVENANCE.md`](../../../data/boundaries/nova-scotia/PROVENANCE.md):

| File | Bytes | What it is |
|---|---:|---|
| `elections-ns-ed-pd-2026-04-09.geojson` | 63,873,793 | 1,817 polling divisions across 56 districts; `(ED_NO, PD_NO)` unique |

Total staged: **61 MB** against the 500 MB budget. Assembled from 5 paged requests; no geometry, attribute, or CRS altered. ⛔ **Staged for research only — not redistributable** pending the licence question.

## Effective dates — legal vs metadata

Applying the `effective_from` ruling (use the **legal in-force date**, record the metadata date as a discrepancy).

Nova Scotia is the **cleanest date case researched so far**, because the legal event and the agency's data release land on the same day.

| | Date | Basis |
|---|---|---|
| ✅ **Legal in-force — use this** | **2026-04-09** | **Royal Assent** of *Elections Act (amended) and House of Assembly Act (amended)*, Government Bill 205, Assembly 65 Session 1 — status `RA`, dated April 9, 2026 on `nslegislature.ca`'s bills listing |
| ✅ Dataset metadata — **agrees** | 2026-04-09 | Elections NS `RELEASE_DATE = "April 9, 2026"` on exactly the two changed districts |
| Commission final report | 2026-01-30 | 2025 Electoral Boundaries Commission — the recommendation, not the law |
| Legislation introduced | 2026-02-26 | first reading, not in force |
| AGOL item last modified | 2026-04-14 | service publication, 5 days after RA |

★ **The metadata date and the legal date coincide** — Elections NS released the new geography the same day the Act received Royal Assent. That is a strong mutual corroboration and the first jurisdiction where the two agree. It does *not* undercut the ruling: it confirms that when an agency is disciplined the two align, and Ontario (13½ months) and federal (11 months) show what happens when they are not.

⚠ **The 2026-04-09 date above is a Royal Assent date from the Assembly's bill-status listing, not a consolidation date.** Nova Scotia's consolidated-statute site carries "amended to" / revision fields on the *House of Assembly Act*; those record when the consolidation was cut and must **not** be read as commencement — the two can differ by years. `effective_from` here is derived from the legislative event plus the agency's same-day data release, with the commencement provision itself still unread (below).

⚠ `needs confirmation`: whether Bill 205 commences on Royal Assent or on proclamation. The circumstantial evidence for Royal Assent is strong — Elections NS published the new geography that day, and the news release states a byelection *will be held* for the new riding (i.e. the district legally exists now, rather than at the next general election). But I did not read the Act's commencement section.

**`effective_to` for the prior (55-district) generation: 2026-04-08.**

⚠ **Our 55 existing rows carry `effective_from = '2023-01-01'`**, the loader's hardcoded placeholder — fiction, as everywhere. Do not carry it forward; it should become `effective_from` = the 2019 set's real date (`needs confirmation`) and `effective_to = '2026-04-08'`.

## Reconciliation with `constituency_boundaries`

**What we hold today.** 55 rows, `level='provincial'`, `province_territory='NS'`:

- `source_set` = `nova-scotia-electoral-districts-2019`
- `constituency_id` prefix = `nova-scotia-electoral-districts-2019` — ✅ **these match**; NS is *not* one of the set/prefix divergences
- Slug half = kebab-cased district name, e.g. `nova-scotia-electoral-districts-2019/bedford-basin`
- All rows `boundaries_version='current'`, `effective_from='2023-01-01'`, `effective_to=NULL`
- Geometry: 11,103 vertices, **avg 202/district** — Open North `simple_shape`
- Roster join: 55 active MLAs, 55 with `constituency_id`, 55 resolving

**Reconciliation against the authoritative 56.** Slugifying `ED_NAME` and comparing:

- **55 / 55 of our rows matched** — 0 extras, 0 name-text differences (including the accented `Chéticamp` and hyphenated compounds)
- ★ **1 authoritative district missing from our table: `ED_NO` 56, Chéticamp-Margarees-Pleasant Bay**

So the *identity* reconciliation is as clean as Ontario's and Alberta's. **The problem is not keying — it is that our map predates a statute.**

### ★ The two-part defect

1. **Missing district.** Chéticamp-Margarees-Pleasant Bay (~3,889 electors, 10 polling divisions) has no polygon. Any postcode in that area currently resolves to **Inverness** — a district that legally no longer contains it.
2. **⚠ Stale district — the worse half.** `ED_NO` 34 Inverness was *reshaped*, not merely renamed: it carries `RELEASE_DATE = "April 9, 2026"` and 26 polling divisions, down from its pre-split extent. **Our Inverness polygon still covers the Chéticamp territory.** Per [`overview.md`](./overview.md), a stale boundary is worse than a missing one — it returns a confident wrong answer with no signal. This is a live instance.

⚠ **Nova Scotia therefore was not "numerically complete".** The 55-rows-against-55-seats reading was correct as of the 2019 commission and is now wrong in both directions: the seat count moved to 56, and one of the 55 polygons we hold is obsolete. **Row-count-equals-seat-count is not a completeness test** — it cannot see a reshape, and it silently lags any statute enacted after the last mirror.

**Name check — Inverness was *not* renamed.** Secondary reporting suggested Inverness became "Inverness-We'koqma'q". The Elections NS service still says `Inverness` at `ED_NO` 34, and the government news release is explicit: the district divides into *"Chéticamp-Margarees-Pleasant Bay, having 3,889 electors"* and *"Inverness, having 10,609 electors; to be represented by the current MLA for Inverness until the next general election."* **`ED_NAME` 34 stays `Inverness`.** Flagged because the rename would have looked like a second delta and would have broken a name-keyed load.

### ★ Vintage verification — measured, not inferred

Nova Scotia passes a 55/55 count check, which proves only that every rep linked to something. The geometry was therefore measured directly against the authoritative current generation.

**Method.** The 1,817 authoritative polling divisions were dissolved per `ED_NO` in PostGIS (`ST_UnaryUnion(ST_Collect(...))`) from the staged GeoJSON, read-only, then compared district-by-district against our stored polygons. Two overlap ratios were computed in **both** directions, because a one-directional test cannot distinguish "ours is correct" from "ours is a superset":

- **`pct_of_auth_covered`** = how much of the authoritative district our polygon covers
- **`pct_of_ours_valid`** = how much of *our* polygon is actually inside the authoritative district

⚠ **On the coastal caveat.** NS is heavily coastal (Cape Breton, hundreds of islands), so area comparison was expected to be unreliable per the drawing-convention warning. **Empirically it was not** — 54 of 55 districts agree to within 0.04% on area *and* 99.9% on overlap in both directions, which demonstrates that Open North's NS set and Elections NS's own geography use compatible drawing conventions. The caveat was valid a priori and is discharged by measurement; intersection was used regardless, so the conclusion does not rest on area.

**Result — 54 of 55 districts:**

| metric | value |
|---|---|
| mean abs area error | **0.0377%** (max 0.8065%) |
| mean overlap, authoritative covered | **99.907%** (min 99.46%) |
| mean overlap, ours valid | **99.898%** (min 99.08%) |
| districts below 95% either direction | **0** |

The sub-1% deficits cluster on the *smallest* urban districts (Halifax Chebucto, 3.7 km², at 99.08%), which is the expected signature of a fixed-tolerance simplifier, not of a boundary difference.

**Result — the two districts that fail:**

| `ED_NO` | District | authoritative km² | ours km² | auth covered | **ours valid** |
|---:|---|---:|---:|---:|---:|
| 34 | Inverness | 2,929.0 | **4,875.2** | 100.00% | ⛔ **60.08%** |
| 56 | Chéticamp-Margarees-Pleasant Bay | 1,946.5 | — | — | ⛔ **no row** |

★ **The arithmetic closes exactly.** Our Inverness polygon exceeds the authoritative one by **1,946.2 km²**; authoritative Chéticamp is **1,946.5 km²** — agreement to **0.30 km², or 0.015%**. Our Inverness is precisely *new Inverness + Chéticamp*, which is what a pre-split polygon must be.

★ And the direct misassignment measure: **99.99% of Chéticamp-Margarees-Pleasant Bay currently falls inside our `Inverness` polygon** (the remaining 0.01% clips Victoria-The Lakes). Every address in that district resolves to the Inverness MLA today.

> ⛔ **Our geometry matches the current (2026) generation to 99.9% for 54 of 56 districts, therefore those rows are CORRECT. Two are not: `Inverness` is MISASSIGNED — 39.9% of its polygon is territory that legally belongs to another district — and `Chéticamp-Margarees-Pleasant Bay` is MISSING entirely.**

★ **This is materially better news than "NS is stale."** It is not a Saskatchewan-style whole-province silent redraw; it is a surgical two-district defect with a known cause, a known date, and a known fix. 54 districts need nothing.

**Recommended cutover** (blocked on the licence, but the shape is settled):

```
-- dissolve the 1,817 polling divisions on ED_NO first — 56 districts out
constituency_id       = 'nova-scotia-electoral-districts/' || slugify(ED_NAME)  -- generation-FREE
authority             = 'elections-nova-scotia'
authority_district_id = ED_NO                       -- '01'..'56', zero-padded as published
boundaries_version    = 'house-of-assembly-act-2026'
effective_from        = DATE '2026-04-09'
effective_to          = NULL
-- and close out the generation we already hold:
UPDATE constituency_boundaries SET effective_to = DATE '2026-04-08',
       boundaries_version = 'electoral-boundaries-commission-2019'
 WHERE province_territory = 'NS' AND level = 'provincial';
```

Note the prefix drops `-2019` per the generation-free rule in [`ontario.md`](./ontario.md) § Addendum. Preserve `ED_NO`'s zero-padding exactly as published rather than normalising to integers — it is the agency's own representation, and Alberta's unpadded `EDNUMBER` in the same project is a standing reminder that padding conventions are per-jurisdiction.

★ **NS is the best candidate to *prove* the temporal model**, once licensed: it is the only jurisdiction where both generations are in hand (the new one from Elections NS, the old one already in our table), the changed footprint is exactly two districts, and there is a hard legal date separating them. Ontario proves the re-key; Alberta proves the prior-generation load; **Nova Scotia proves a real supersession.**

## Known traps

- ⚠ **1,817 rows for 56 districts.** The extreme case of the one-row-per-district trap. Dissolve on `ED_NO` before loading. `(ED_NO, PD_NO)` is the file's real key.
- ⚠ **`RELEASE_DATE` is a String field holding `"September 1, 2020"` / `"April 9, 2026"`** — not a date type, US-style long format, and it partitions the file into two generations. Useful (it precisely identifies the two changed districts) but must be parsed, not cast.
- ⚠ **Declared SR is EPSG:3857 but `f=geojson` returns degrees.** Web Mercator is a display projection; its presence as the declared SR is a hint that this is a rendering service. Do not `ST_SetSRID(geom, 3857)` on the staged file.
- ⚠ **`access: public` is not a licence.** An ArcGIS sharing setting is not a grant of rights. This distinction is the whole NS licence problem and is easy to gloss over.
- ⚠ **The service description and the item snippet disagree** — service says *"2019 Electoral Geography"*, item snippet says *"2026"*. The data is 2026 (56 districts, April 2026 release dates). Trust the data, not the prose.
- ⚠ **A 100%-resolving roster join hid a missing district**, because the new seat is vacant pending a byelection. Roster completeness metrics cannot detect boundary gaps.
- ⚠ **Socrata's catalogue API is federated.** An unscoped `q=electoral` against `data.novascotia.ca` returns PEI, New Brunswick and US datasets. Always pass `domains=` **and** `search_context=`.

## Research-handoff items

- **★ Will you contact Elections Nova Scotia to request licence terms for the electoral district boundaries?** This is the blocker, and unlike Ontario it cannot be resolved by reading anything — there is no published licence to read. NS publishes no OGL product for this data, and the only grant in existence (in `represent-canada-data`) is Open North's own non-transferable permission, whose text directs other parties to apply separately. The contact named in that file is **Pierre L. Gareau, GIS Manager, Elections Nova Scotia, gareaupl@gov.ns.ca, 1-902-424-0408** — though that record is years old and the current AGOL service is maintained by **Andrew Cameron**, so the contact may have changed. The ask is narrow: permission to use and redistribute district boundaries in a public civic-transparency dataset, and confirmation of a required attribution string.
- **⛔ We are redistributing NS boundaries without a licence right now.** 55 rows are served through `/api/public/v1/boundaries/*` under a grant that belongs to Open North. This is independent of the staleness problem and does not wait on the new map. **Recommend deciding explicitly** whether to (a) leave it pending the licence request, or (b) suppress NS from the public boundary endpoints until terms are obtained. I am flagging rather than choosing, since it is a live-service change.
- **Nova Scotia is one district short and one district stale, effective 2026-04-09.** Independent of licensing, decide whether to correct the map now — every postcode in the Chéticamp area currently returns the wrong MLA. If the licence question will take time, an interim option is to load the two changed districts only, which is a 36-polling-division dissolve rather than a full re-source. Same licence caveat applies.
- **Confirm Bill 205's commencement provision** (Royal Assent vs proclamation) to firm up `effective_from = 2026-04-09`. Evidence strongly favours Royal Assent; I did not read the section.
- **Pre-2019 (51-district, 2012) geometry is unresolved.** Not on any open surface; the Open North copy is under the same non-transferable grant. Recommend deferring — nothing reads historical boundaries today.

## Status

> ⚠ **Reconciled 2026-09-01.** The checkboxes below are the **research phase's** record
> (closed 2026-08-18) and several were overtaken by the build — migrations `0064`–`0121`,
> merged to `main` 2026-08-28. An unticked box here is **not** evidence that something is
> still outstanding.
>
> **Live counts: [`PROGRESS.md`](./PROGRESS.md)** (generated by `boundary-progress`).
> **What actually landed:** the migration headers, which are the accurate record.
> This file's job is the *reasoning* — sources, licences, traps, vintage evidence.

- [x] Current boundaries located and staged (2026-08-18) — 1,817 polling divisions / 56 districts, 61 MB
- [x] ★ Authoritative district count established — **56, not 55**
- [x] Missing district identified — **Chéticamp-Margarees-Pleasant Bay (`ED_NO` 56)**
- [x] Stale district identified — **Inverness (`ED_NO` 34), reshaped 2026-04-09**
- [x] Inverness rename ruled out — `ED_NAME` unchanged; secondary reporting was wrong
- [x] Authoritative district ID identified — `ED_NO`, zero-padded `'01'`–`'56'`
- [x] District ID reconciliation confirmed — 55/55 of ours exact, 0 extras, 0 name drift, 1 missing
- [x] Legal `effective_from` established — **2026-04-09**, Royal Assent of Bill 205; agency metadata agrees
- [x] Prior generation located — it is the 55 rows already in our table; `effective_to = 2026-04-08`
- [x] WAF check — **none encountered**; `nslegislature.ca` served HTTP 200 to a polite UA
- [x] ★ **Vintage verified by measurement (2026-08-18)** — 54/56 districts at 99.9% overlap both directions (0 below 95%); `Inverness` **misassigned** (only 60.08% of our polygon is valid; 39.9% belongs to another district) and `Chéticamp-Margarees-Pleasant Bay` **missing**. 99.99% of Chéticamp currently resolves to Inverness. Not a whole-province staleness — a surgical two-district defect.
- [x] Coastal drawing-convention caveat discharged — 54/55 agree to 0.04% on area *and* 99.9% on intersection, so NS conventions are compatible; conclusion rests on intersection regardless
- [x] Attribution obligation — **n/a, because no licence exists to attribute under** (see § Terms / Licensing)
- [ ] Licence cleared for internal use — **blocked: no licence stated anywhere**
- [ ] Licence cleared for redistribution — **blocked: requires contacting Elections Nova Scotia**
- [ ] Bill 205 commencement provision confirmed — **needs confirmation**
- [ ] Pre-2019 (51-district) geometry — **not published open; recommend deferring**
