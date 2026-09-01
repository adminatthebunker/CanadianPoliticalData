# Northwest Territories — Electoral Boundary Research

> Standalone boundary/roster dossier for the Northwest Territories. Cross-cutting context
> (methodology, licence matrix, reconciliation strategy) lives in [`overview.md`](./overview.md).
> The legislative-data dossier for this jurisdiction is at [`../northwest-territories.md`](../northwest-territories.md).

**Agency:** Elections NWT | **Website:** https://www.electionsnwt.ca | **Districts (current):** 19 | **Current order:** S.N.W.T. 2014, c. 21 (Bill 18, 5th Session, 17th Legislative Assembly), in force **2015-10-25** | **Next redistribution:** 🚧 **in flight** — 2025–26 Commission tabled its final report 2026-02-27 recommending **22** districts; no implementing bill before the House as of 2026-08-18

**Status snapshot (2026-08-18):** ✅ **Cracked.** The NWT Centre for Geomatics publishes the 19 electoral districts as a shapefile on a bare GET, plus an ArcGIS REST service, under the Open Government Licence – Northwest Territories. **Difficulty 1.** ✅ **The vintage we hold is correct** — the 2013/14 order is still the law, confirmed against the consolidated statute itself, which reads verbatim *"There are 19 electoral districts as named and described in Schedule A"*. The brief's "13 years old" concern is real as a *vintage* but the map has not been superseded. ✅ **19/19 district names reconcile on slug — a 100% match, no re-key needed.** ⛔ **But the geometry we hold is materially wrong for 5 of the 19, and it is producing wrong answers in production right now.** Measured by polygon intersection against the authoritative file: held `Great Slave` is **missing 69% of its area**, held `Frame Lake` is **2.0× oversized** and only 48% of it is really Frame Lake, held `Hay River North` is **missing 30%**, held `Hay River South` is **3.6× oversized**, and held `Nunakput` is **2.0× oversized**. The two Yellowknife districts and the two Hay River districts are adjacent pairs with complementary over/under errors — their shared boundaries are in the wrong place, so addresses there resolve to the neighbouring district. ★ **This reframes NT from "low-priority refresh" to the highest-value correctness fix in this pair of dossiers.** ⚠ A redistribution is also in progress: the 2025–26 Commission recommended **19 → 22** (Yellowknife 7→9, Monfwi split, Inuvik and Hay River rebalanced, and `Great Slave` renamed as "demeaning and objectionable"). MLAs have not acted; whatever we load has a **known expiry** ahead of the 2027-10-05 general election. ⚠ The production geomatics REST host 404s; only the `sandbox.` host answers.

---

## Current vintage: still in force, but on a clock

The brief asked whether a newer commission has redrawn the NWT map. Answer: **a commission has
recommended it, but nothing has been enacted, so the 2013 order still governs.** The sequence:

- **2013/14 order** — the 2012/13 Electoral Boundaries Commission; the 19-member model was adopted by the Assembly in May 2014 and enacted through **Bill 18, 5th Session, 17th Legislative Assembly** = **S.N.W.T. 2014, c. 21, *An Act to Amend the Legislative Assembly and Executive Council Act***. This is the order that merged `Tu Nedhe` and the Dettah/N'Dilo portion of `Weledeh` into **`Tu Nedhé-Wiilideh`**, moving the Yellowknife remainder of `Weledeh` into a new **`Yellowknife North`**; the other 17 districts were retained with minor adjustments. In force **2015-10-25**, first contested at the **2015-11-23** general election. **Still in force today.**
- ✅ **Confirmed against the consolidated statute, not inferred.** The current consolidation of the *Legislative Assembly and Executive Council Act* states at **s. 2(1)**, verbatim: *"There are 19 electoral districts as named and described in Schedule A."* That is the operative provision, and it still says 19.
- **2025–26 Commission** — struck under the standing rule that a commission convenes after every second general election. Interim report November 2025 with four models; public hearings December 2025; **final report tabled in the Legislative Assembly on 2026-02-27** as `TD 483-20(1)`.
- **Recommendation: 22 districts** — three more than today. Yellowknife goes from 7 to 9; `Monfwi` splits in two; boundaries in Inuvik and Hay River are rebalanced for voter parity; the Dettah access road and part of Highway 3 east of Boundary Creek move into `Tu Nedhé-Wiilideh`. The commission also recommended **renaming `Great Slave`**, calling the name "demeaning and objectionable."
- **Status as of 2026-08-18: not enacted.** ✅ Verified directly against the Assembly's bills listing for the 20th Assembly — bills run to No. 53 and **none concerns territorial electoral boundaries or districts**. (Bill 51, *An Act to Amend the Local Authorities Elections Act*, is municipal-election procedure, not territorial boundaries — do not mistake it for the implementing bill.)
- **Deadline pressure:** the next general election is fixed for **2027-10-05**. For a 22-district map to govern it, a bill has to pass with enough lead time for Elections NWT to redraw polling divisions. That puts the decision window roughly in the **2026-2027 sittings** — i.e. our loaded data has a plausible 12-month shelf life.

⚠ **Implication for the build:** load the 19-district set now — it is correct and it fixes real
attribution — but **set up NT to be re-checked before the 2027 election**, and do not name the
`source_set` in a way that assumes permanence.

## Current boundaries

- **Source URL(s):** https://www.geomatics.gov.nt.ca/en/electoral-district-boundaries ; https://www.sandbox.geomatics.gov.nt.ca/arcgis/rest/services/Pro_GNWT/Boundaries_LCC/MapServer/2 ; https://open.canada.ca/data/en/dataset/27aafdc3-1c8a-679f-bc69-91cc09a0320a
- **Format:** Zipped shapefile (1.25 MB) from the geomatics site; ArcGIS REST (JSON / geoJSON) from the sandbox host. ⚠ **The shapefile URL does not look like a file URL** — it is a plain page-shaped path with no extension, but the server returns the ZIP body directly (`Content-Type` unset, inner members `ElectoralDistricts.shp/.dbf/.prj/.shx/.sbn/.sbx/.CPG` plus a 75 KB `.shp.xml`). A scraper that assumes HTML at that URL will parse a ZIP as text and find nothing; `curl -o` works.
- **CRS / projection:** **ESRI:102002 — no EPSG equivalent exists.** The `.prj` reads verbatim `PROJCS["Canada_Lambert_Conformal_Conic",GEOGCS["GCS_North_American_1983",DATUM["D_North_American_1983",SPHEROID["GRS_1980",6378137.0,298.257222101]],PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]],PROJECTION["Lambert_Conformal_Conic"],PARAMETER["False_Easting",0.0],PARAMETER["False_Northing",0.0],PARAMETER["Central_Meridian",-96.0],PARAMETER["Standard_Parallel_1",50.0],PARAMETER["Standard_Parallel_2",70.0],PARAMETER["Latitude_Of_Origin",40.0],UNIT["Meter",1.0]]`. The REST layer independently confirms it, reporting `wkid: 102002, latestWkid: 102002`. ✅ **SRID 102002 is already present in our `spatial_ref_sys`** (`auth_name = 'ESRI'`), verified by query, so `ST_Transform(geom, 4326)` works with no insert. ⚠ Do **not** reach for EPSG:3347 (StatCan Lambert) or EPSG:3978 (Canada Atlas Lambert) — both are Lambert Conformal Conic on NAD83 and both have *different* standard parallels and origin. Silently substituting either shifts the geometry by kilometres. This is a continent-wide projection with a 40°N origin being used for territory at 60–78°N, which is unusual but is what the publisher chose; honour it.
- **Attribute schema:** from the `.dbf` header of **the specific file recommended below** (`ElectoralDistricts.dbf`, dBase III, 19 records, 5 fields) — `ED` (`C`, len 25) English district name; `nonYK` (`C`, len 5) flag, `y`/`n`, marking districts **outside** Yellowknife (12 `y` / 7 `n`); `ElectoralY` (`N`, len 5) electoral year, uniformly `2023`; `Shape_STAr` (`F`, len 19, dec 11) area; `Shape_STLe` (`F`, len 19, dec 11) perimeter. ★ The REST layer carries **different field names for the same data plus one extra field** — `Shape.STArea()` / `Shape.STLength()` rather than the truncated DBF forms, and `EDFrench`, the French district name (`Hay River Nord`, `Delta du Mackenzie`, `Yellowknife Sud`, …), which the shapefile omits entirely. That is the reason to keep the staged GeoJSON: it is the only route to French names.
- ⚠ **`.CPG` trap, confirmed live here.** The encoding file is `ElectoralDistricts.**CPG**` — **uppercase**. A `*.cpg` glob misses it, and the fallback decode mojibakes `Tu Nedhé - Wiilideh` into `Tu NedhÃ© - Wiilideh`. Observed first-hand during this pass: a latin-1 read produced exactly that corruption, and the case-insensitive glob then found the `.CPG` declaring `UTF-8`, which decodes cleanly. **Glob case-insensitively and honour the declared UTF-8.**
- **District ID field:** ⚠ **There is none.** Same shape as Yukon — `ED` (the name) is the only identifying attribute. `OBJECTID` is an ArcGIS row ordinal (observed values start at 420, clearly not a domain key) and must not be persisted as a stable ID. The build phase should **derive the key by slugifying `ED`**, which reproduces our existing `constituency_id` slugs exactly (see Reconciliation).
- ✅ **One row per district — no duplicate-`constituency_id` risk.** Checked explicitly rather than assumed: **19 records → 19 distinct `ED` values → 19 distinct slugs**, zero duplicates. ★ Multi-part districts *are* present and are stored correctly as **multi-part geometry within a single record**, not as one row per island: `Tu Nedhé - Wiilideh` has **20 parts**, `Yellowknife North` 20, `Sahtu` 14, `Dehcho` 2. The `.shp` header declares shape type 5 (Polygon) with 19 geometry records. So the archipelago risk flagged in the brief is real in the *geometry* but **does not** manifest as duplicate rows here. Load as `MultiPolygon` (which our schema already requires) and it is safe.
- **Effective date → `effective_from` = `2015-10-25`.** This is the **legal in-force date**, per the ruling. Statutory instrument: **S.N.W.T. 2014, c. 21**, whose coming-into-force note reads verbatim **"On dissolution of the 17th Legislative Assembly"**. Elections NWT records that dissolution verbatim: *"Following the dissolution of the 17th Legislative Assembly on October 25, the Chief Electoral Officer will issue the Writs of Election for the 2015 Territorial General Election on Monday, October 26."* So dissolution = **2015-10-25**, writs 2015-10-26, polling day 2015-11-23.
  - ⚠ **Competing dates, recorded as required — do not use these:** the agency's dataset metadata says **`ElectoralYear = 2023`** on every feature and the shapefile members are stamped **2023-07-28**, i.e. the file was refreshed for the 2023 general election. That is ~7 years and 9 months after the legal date. Using the metadata date would wrongly return "no district" for any address query between 2015 and 2023. The federal precedent (SI/2023-57 → dissolution, not the Elections Canada metadata date) applies identically.
- **Superseded date:** `NULL` — still in force. ⚠ Expected to be superseded before the **2027-10-05** general election if the 22-district recommendation is enacted.
- **District count:** **19**. ✅ Confirmed three independent ways: the statute (`LAECA` s. 2(1), *"There are 19 electoral districts"*), the file (19 distinct `ED` values), and the seat count of the 20th Legislative Assembly. `jurisdiction_sources.seats = 19` for NT is correct and needs no change.
- ✅ **GeoJSON vs shapefile: verified identical, and the GeoJSON is the recommended input.** Checked before preferring it, per instruction. Both carry **19 features**; the `ED` name sets are **byte-identical** (`set(shp) == set(geojson)` → `True`) and so are the slug sets. Geometry agreement was tested too, by computing geodesic area on the GeoJSON in PostGIS and comparing against the `.dbf`'s stored planar `Shape_STAr`: the GeoJSON runs **+3.0% on 13 of 19 districts**, tapering to +0.9% for the Inuvik pair and **−2.4% for `Nunakput`**. ★ That is not disagreement — it is the **latitude-dependent area distortion of ESRI:102002**, whose standard parallels are 50°N and 70°N. Districts near 60°N inflate by ~3%; `Nunakput`, which reaches ~78°N and sits beyond the northern standard parallel, flips sign. The pattern tracks latitude monotonically, which is an **independent confirmation that the CRS identification is correct** — a wrong SRID would produce scattered, not graduated, error. **Conclusion: the GeoJSON is faithful, already EPSG:4326, and avoids the reprojection step entirely. Prefer it.** Keep the shapefile as the durable archive copy and as the source of the `Shape_STAr` sanity numbers.
- **Difficulty (1–5):** **1** — bare-GET shapefile plus an open ArcGIS REST service, no auth, no gate.
- **Notes:** The REST layer's own description states the purpose verbatim: *"Part of the Elections NWT mandate is to provide maps to all the Deputy Returning Officers and for candidate use during the periodic NWT Elections. To create these maps requires accurate boundaries of each of the 19 Electoral Districts of the NWT... Previous versions of the required maps had been created by Earth Tec of Edmonton in Autocad format."* `copyrightText` reads verbatim `Elections NWT, NWTCG`. So this is the operational election file, not a cartographic derivative — the right thing to ingest. Consensus government: **no parties**, so there is no party dimension to carry on NT district data.

## Prior boundaries (immediately preceding)

- **Source URL(s):** ⛔ **None found.** Dead ends, all confirmed 2026-08-18: the REST layer `MapServer/2` holds a single vintage — `ElectoralYear` is `2023` on all 19 features with no other value present, so there is no historical slice hiding in the current layer; the parent group layer `MapServer/1` ("Election Boundaries") exposes only `Electoral District`, `Electoral Polling Division`, `Polling Locations`, `Returning Offices` — no dated variants; `open.canada.ca` carries exactly one GNWT electoral dataset, and it is the current one.
- **Format:** ⛔ Unavailable in machine-readable form. A file named `NWTElectoralDistricts2011.shp` (and an `-AEA` NWT Albers variant) is referenced in third-party metadata, which suggests the pre-2013 set was distributed at some point, but **no live URL for it was located** and third-party mirrors are not primary sources. `UNTESTED — probe during build`: the NWT Discovery Portal (`http://nwtdiscoveryportal.enr.gov.nt.ca/geoportal/catalog/main/home.page`) is an unprobed Esri Geoportal catalogue and is the most likely remaining home for it.
- **CRS / projection:** unknown — nothing read.
- **Attribute schema:** unknown — nothing read.
- **District ID field:** unknown.
- **Effective date:** the 2006 Electoral Boundaries Commission order, in force on the dissolution preceding the **2007-10-01** general election. That commission folded the Deh Cho and Tu Nedhe communities together and moved Detah and Ndilo out of `Weledeh` into `Tu Nedhe`. ⚠ **`needs confirmation`** — the enacting instrument and its dissolution date were not established in this pass, and since we hold no pre-2013 rows there is nothing to date. Chase only if the prior generation is ever obtained.
- **Superseded date:** **`2015-10-25`** → `effective_to`. Legal date, matching the current generation's `effective_from` exactly, so the two generations abut with no gap and no overlap.
- **District count:** **19** — the count did not change in 2013; the *composition* did. `Tu Nedhe` and `Weledeh` disappeared, `Tu Nedhé-Wiilideh` and `Yellowknife North` appeared.
- **Difficulty (1–5):** **4** — probably obtainable but not from any indexed endpoint; needs a catalogue crawl or a request to NWTCG.
- **Notes:** ⓘ **Lower stakes than the equivalent Yukon gap.** We hold no pre-2013 NT rows, so nothing is at risk of being destroyed, and the pre-2013 map has not governed representation since 2015 — it matters only for historical Hansard attribution (a member who sat for `Weledeh` before 2015 cannot be point-in-polygon'd against today's map). Given NT Hansard coverage is `partial` per `jurisdiction_sources`, this is a low-priority backfill, not a blocker.

## District ↔ elected official mapping

- **Roster source:** https://www.ntassembly.ca/members and the constituency map at https://www.ntlegislativeassembly.ca/visitors/maps/constituency-map. ✅ Unblocked — `ntlegislativeassembly.ca` answers server-side fetches, unlike its Yukon counterpart.
- **Join key:** district name → slug, and we already have a native ID column for the member side: **`politicians.nt_mla_slug`** (kebab-case, stable across the `/meet-members/mla/` and `/former-members/` URL paths), per `CLAUDE.md` convention #1. ✅ NT is one of the jurisdictions where convention #1 is already satisfied.
- **Current state of our roster:** **21 rows `is_active`, 19 with a `constituency_id`** = **90% attributed**. ★ The 19 attributed rows map **one-to-one onto the 19 districts** — every seat is filled, no district is orphaned, no district is double-claimed. This is the cleanest roster↔boundary correspondence encountered in this pass.
- **The 2 unattributed rows are both data-quality artifacts, not boundary problems:**
  - **`Rj Simpson`** — a duplicate of `R.J. Simpson` (Hay River North, correctly attributed). A punctuation/casing variant that escaped deduplication. This is precisely the pattern the reusable detector at `scripts/audit_politician_duplicates.py` exists to catch; worth re-running for NT. ⚠ Check the `Cooke` rule before merging — but these are unlikely to be a both-native-id pair, since the duplicate carries no constituency.
  - **`Dawn Anderson`** — a former MLA (Thebacha, 18th Assembly) still flagged `is_active`. A missing end-date, the same class of staleness tracked in `project_municipal_ended_at_stale`.
- **Assessment:** ⚠ The brief cites NT at 95% attributed; the measured figure is **90%** (19/21). The 5-point gap is these two rows. ★ **Neither is fixed by boundary work** — both are roster hygiene. Loading boundaries changes NT attribution by exactly zero, because NT attribution is already complete against every district that exists. **This is the important negative result in this dossier:** NT is the one jurisdiction here where the boundary refresh is a geometry-accuracy improvement rather than a coverage improvement.
- **Difficulty (1–5):** **2** for a roster scrape (unblocked, structured, native slug column already in place); **1** for the two-row cleanup.

## Postal-code correspondence (if published)

- **Published correspondence file:** ⛔ None. Elections NWT publishes no postal-code → district table and no FSA correspondence.
- **What exists instead:** the polling-division layer (`MapServer/3`, "Electoral Polling Division - 0-1:250k scale") and a polling-locations point layer (`MapServer/20`), both on the same open REST service. Neither is postal-keyed.
- **Assessment:** ✅ **No gap for us.** Our existing point-in-polygon path through `public.postcode_cache` + Open North centroids is the right mechanism and needs nothing NT-specific. ⚠ Note the same accuracy ceiling flagged for Yukon, and worse here: essentially the entire territory is **one FSA, `X0E`/`X1A`**, with `X1A` covering all of Yellowknife. A postcode centroid in `X1A` cannot distinguish `Frame Lake` from `Range Lake` from `Yellowknife Centre` — seven districts share it. **Yellowknife lookups from a 3-character FSA are effectively a coin flip and should be surfaced as low-confidence**; a full 6-character postcode is required for a meaningful answer.

## Terms / Licensing

- **Licence:** **Open Government Licence – Northwest Territories**, as recorded on the GNWT's open.canada.ca entry (`license_title: "Open Government Licence Northwest Territories"`).
- **Licence URL:** https://www.gov.nt.ca/en/open-government-licence-northwest-territories
- **Verbatim clause quote** (grant of rights, obligations, and exemptions). ⚠ **Served in French.** The GNWT's `/en/` URL returns the French text — the English page appears to be mis-routed, and `/en/services/open-government-licence-northwest-territories` returns a generic Programs-and-Services page. Quoting what the server actually returns rather than a paraphrase or a self-made translation:

  > Le fournisseur d'information vous octroie une licence mondiale, libre de redevances, perpétuelle et non exclusive pour l'utilisation de l'information, y compris à des fins commerciales, sous réserve des modalités énoncées ci-dessous.
  >
  > Vous êtes libre : de copier, de modifier, de publier, de traduire, d'adapter, de distribuer ou d'utiliser autrement les renseignements, quel que soit le support, le mode ou le format employé, à toutes fins légitimes.
  >
  > Vous êtes tenu, lorsque vous exercez l'une ou l'autre des activités susmentionnées : de citer la source de l'information en ajoutant tout énoncé d'attribution précisé par le fournisseur d'information et, lorsque possible, de fournir un lien vers cette licence; d'utiliser l'énoncé d'attribution suivant, si le fournisseur d'information ne vous fournit pas un énoncé d'attribution précis, ou si vous utilisez des renseignements provenant de plusieurs fournisseurs d'information et que la présence de multiples énoncés ne se prête pas à votre produit ou à votre application : **Contient des renseignements visés par la licence du gouvernement ouvert des Territoires du Nord-Ouest.**
  >
  > Les modalités de cette licence sont importantes, et si vous ne respectez pas l'une ou l'autre d'entre elles, les droits qui vous sont concédés aux termes de la présente licence ou de toute autre licence semblable octroyée par le fournisseur d'information vous seront retirés automatiquement.
  >
  > Exemptions : La présente licence ne confère pas le droit d'utiliser : des renseignements personnels; l'information ou les dossiers non accessibles en vertu de la Loi sur l'accès à l'information et la protection de la vie privée des Territoires du Nord-Ouest; des droits de tierces parties que le fournisseur [d'information n'a pas le pouvoir de céder].

- **Reading of the redistribution clause:** ✅ **Explicitly permissive.** *Mondiale, libre de redevances, perpétuelle et non exclusive*, expressly *y compris à des fins commerciales*, with the right to *distribuer* named outright. Redistribution of the boundary data is squarely within the grant, conditional only on attribution.
- **Attribution required:** yes. The publisher-specified statement takes precedence where one is given; the REST layer's own `copyrightText` supplies it verbatim as **`Elections NWT, NWTCG`**. Where no publisher statement applies, the licence's own fallback wording (bolded above) must be used.
- **Exemption that matters to us:** the licence does not grant rights over personal information or over records exempt under the NWT ATIPP Act. ✅ Not engaged here — electoral district polygons contain no personal information. Relevant only if we ever ingest the polling-locations or elector-level layers.
- **No click-through anywhere.** ✅ Both files download with a bare GET. No account, no checkbox, no agreement form was encountered at any point in this pass.

## Rate limits / auth

- **Auth:** none, on any boundary endpoint.
- **Rate limits:** none observed or documented. No throttling, `Retry-After`, or 429 across the requests made in this pass.
- **maxRecordCount:** `2000` on `MapServer/2` — far above 19 features, so a single unpaged `where=1=1` query returns the complete set with `exceededTransferLimit` absent. No pagination needed.
- ⚠ **Trap — the REST API only answers on the `sandbox.` host.**
  | Host | Result |
  |---|---|
  | `www.geomatics.gov.nt.ca/en/electoral-district-boundaries` (the ZIP) | ✅ 200 |
  | `www.sandbox.geomatics.gov.nt.ca/arcgis/rest/services/...` | ✅ 200 |
  | `www.geomatics.gov.nt.ca/arcgis/rest/services/...` | ⛔ **404** |
  The production host serves the download page but **not** the ArcGIS REST endpoint; the working REST endpoint is on a host literally named `sandbox`. Convenient today, but not a surface to build a recurring pipeline on — **the durable path is the ZIP**. Use the REST service for the `EDFrench` field and for ad-hoc checks, and expect it to move.
- ⚠ **Secondary trap — the GNWT `/en/` licence URL serves French.** Noted above; not a blocker, but it will confuse a future reader who assumes the English text was never captured.

## Staged files

Staging root `data/boundaries/northwest-territories/`, manifest at `data/boundaries/northwest-territories/PROVENANCE.md`. **5.6 MB total**, well under the 500 MB budget. `current` only — `prior` is empty (see above).

| Path | Bytes | What it is |
|---|---:|---|
| `current/NWT_ElectoralDistricts.zip` | 1,249,927 | ★ **Authoritative build input.** Native ESRI:102002, 19 features, from the NWT Centre for Geomatics. Inner members named `ElectoralDistricts.*`. |
| `current/NWT_ElectoralDistricts.geojson` | 4,599,720 | REST export, EPSG:4326, 19 features. **Cross-check — and the only source of the `EDFrench` names.** |

⚠ The GeoJSON is 3.7× the size of the zipped shapefile because it is uncompressed WGS84 coordinate text at full vertex density — the NT coastline (`Nunakput` alone is 1.15 M km² with a 4,368 km perimeter) dominates. Expect the same ratio at load time; the `boundary_simple` generalization our schema already carries will matter more for NT than for anywhere else in this corpus.

## Reconciliation with `constituency_boundaries`

**What we hold today:**

| | |
|---|---|
| `source_set` | `northwest-territories-electoral-districts-2013` |
| `constituency_id` prefix | ~~`northwest-territories-electoral-districts-2013/`~~ → **`northwest-territories-electoral-districts/`** (⛔ ruling A6, see below) |
| Rows | **19** |
| `level` | `provincial` |
| `province_territory` | `NT` |
| `boundaries_version` | `current` (on all 19 — ✅ accurate, unusually) |
| `effective_from` | `2023-01-01` (on all 19 — ⚠ an Open North mirroring artifact, not a legal date; the order predates it by ~8 years) |
| `effective_to` | `NULL` (on all 19 — ✅ correct, the order is still in force) |

**Match rate against the authoritative 19: ✅ 19 of 19 (100%)** on slugified name. **No re-key is required.** Every authoritative `ED` value slugifies to a `constituency_id` suffix we already hold, and every held row has an authoritative counterpart — zero orphans on either side.

**2 display-name normalizations** (slug identical, `name` column differs):

| Authoritative `ED` | Held `name` | Shared slug |
|---|---|---|
| `Mackenzie-Delta` | `Mackenzie Delta` | `mackenzie-delta` |
| `Tu Nedhé - Wiilideh` | `Tu Nedhé-Wiilideh` | `tu-nedhe-wiilideh` |

⚠ Both are pure hyphen/space spacing differences and both are absorbed by slugification — **verified by running it**, not assumed. ⓘ Note that the *held* spellings read better than the authoritative ones here (`Mackenzie Delta`, `Tu Nedhé-Wiilideh` match the Assembly's own usage). This is a rare case where refreshing `name` from the source would make the display **worse**; recommend keeping our spellings and treating `ED` as key-only.

### ⛔ The identity layer is clean; the geometry layer is not

The 100% name match made this look like a cosmetic refresh. It is not. Measuring each held
polygon against its authoritative counterpart in PostGIS — `ST_Intersection` on
`::geography`, so the numbers are true surface areas, not projected ones — found **5 of 19
districts materially wrong**:

| District | Auth km² | Held km² | % of authoritative covered by held | % of held that is actually this district |
|---|---:|---:|---:|---:|
| `Great Slave` | 7.9 | 2.5 | **30.6** | 96.8 |
| `Hay River North` | 40.5 | 29.3 | **70.2** | 97.2 |
| `Frame Lake` | 5.2 | 10.5 | 98.0 | **48.0** |
| `Hay River South` | 99.9 | 357.2 | 93.0 | **26.0** |
| `Nunakput` | 564,266.2 | 1,148,022.9 | 100.0 | **49.1** |
| `Range Lake` | 21.0 | 21.0 | 99.7 | 99.5 |
| `Kam Lake` | 20.6 | 20.8 | 99.8 | 99.0 |
| `Yellowknife South` | 20.3 | 20.2 | 98.9 | 99.6 |
| `Yellowknife Centre` | 0.9 | 0.9 | 91.2 | 93.3 |

Read the two right-hand columns as a pair. `Great Slave` is *undersized* — 69% of the real
district is missing from our polygon. `Frame Lake`, its **immediate neighbour**, is
*oversized* — less than half of what we store as Frame Lake actually is. The same
complementary pattern repeats exactly for the `Hay River North` / `Hay River South` pair.
★ **Complementary over/under errors between adjacent districts mean the shared boundary is
drawn in the wrong place** — which is the "confident wrong riding" failure the whole project
exists to eliminate, and it is live today for addresses in Yellowknife and Hay River.

`Nunakput` is a different and milder case: held contains **100%** of the authoritative
district and adds an equal amount again, almost certainly marine extent. Land-address
lookups still resolve correctly; only the area statistic and offshore points are affected.

The remaining 14 districts agree within ~1% and need nothing but a routine refresh.

⚠ **Hypothesis, offered as one:** the districts that are wrong are concentrated among those
the 2013/14 order *changed* (`Great Slave` and `Yellowknife North` come out of the
`Weledeh` dissolution). That is consistent with the Open North mirror carrying **pre-2013
geometry under post-2013 labels** for the affected districts. Not verified — we hold no
pre-2013 polygons to test it against — but if true it means the `source_set` name
`...-2013` has been describing the wrong vintage for those rows all along.

**Recommended build shape — an update in place, not a re-key:**

1. ⛔ **Re-prefix the `constituency_id`s per ruling A6** — `northwest-territories-electoral-districts-2013/<slug>` → **`northwest-territories-electoral-districts/<slug>`** — and move the vintage to `boundaries_version = '2013'` (currently the vaguer `'current'`). ~~Keep every existing `constituency_id`; nothing about the identity layer changes.~~ Superseded: the prefix encodes a generation and must not. ★ **A6 also dissolves the `...-2013`-vs-`...-2014` naming question I raised earlier** — the statute is S.N.W.T. **2014** c. 21, which made the `-2013` suffix mildly wrong, but with no year in the prefix at all the discrepancy simply disappears. Set `boundaries_version = '2014'` if matching the statute matters; it is cosmetic either way. ⓘ NT is the cheap case: **19 rows, one `UPDATE`, no second generation to disambiguate against**, so unlike Yukon there is no collision hazard.
2. **Replace the geometry on all 19 rows** from the staged **GeoJSON** (already EPSG:4326, no reprojection step) and recompute `boundary_simple`, `centroid`, and `area_sqkm`. ★ Per the table above this is not a polish step — it is the correctness fix, and it should be treated as the priority item in the NT build.
3. **Leave `name` alone** (see the note above), or normalize deliberately if a house rule requires matching the source.
4. **Set `effective_from = '2015-10-25'`**, replacing the bogus `2023-01-01`. Legal in-force date per S.N.W.T. 2014, c. 21.
5. **Do not set `effective_to`.** The order is still in force.
6. **Consider populating French names** from the GeoJSON's `EDFrench` if the schema ever grows a `name_fr` column. It does not have one today, so this is a note, not a step.

**Post-load assertion, and use it — it would have caught the current bug.** The `.dbf` carries
`Shape_STAr` in planar m² for every district. After loading, geodesic `area_sqkm` should sit
**~3% above** `Shape_STAr/1e6` for southern districts, tapering to ~+0.9% for the Inuvik pair
and **−2.4%** for `Nunakput` (the ESRI:102002 latitude profile described above). Concretely:
`Nunakput` ≈ **564,266 km²**, `Great Slave` ≈ **7.9 km²**, `Frame Lake` ≈ **5.2 km²**,
`Yellowknife Centre` ≈ **0.9 km²**. ⚠ Note these deliberately **do not** match what we hold
today for the five broken districts — that mismatch is the bug, not a tolerance. If the
reprojection is done with the wrong SRID (3347 or 3978 instead of 102002) the whole profile
breaks scattershot rather than by latitude, which is the tell.

**Unique-constraint note:** `constituency_boundaries` is unique on `(constituency_id, boundaries_version)`. The geometry `UPDATE` touches neither column, so the refresh itself has **no constraint interaction**. ⚠ The A6 re-prefix in step 1 does touch `constituency_id`, but since NT has only one generation there is no sibling row to collide with — a single `UPDATE` setting both `constituency_id` and `boundaries_version` is safe. Contrast Yukon, where the same constraint becomes load-bearing because two generations share each key.

## Municipal wards

**Yellowknife:** no ward boundaries exist — the eight councillors are elected **at large** (16 candidates contested 8 seats in 2022). There is nothing to ingest, and our zero municipal rows for NT are correct rather than a gap. (Out of scope per brief; one line only.)

## Research-handoff items

- **⛔ Raise the priority of the NT geometry refresh — 5 districts are returning wrong answers today.** This is the one item here that is not a question. Held `Great Slave` is missing 69% of its area to an oversized `Frame Lake`, and held `Hay River North` is missing 30% to an oversized `Hay River South`; both are adjacent pairs with misplaced shared boundaries, so postcode lookups in Yellowknife and Hay River currently resolve some addresses to the wrong MLA. I originally reported NT as a low-priority cosmetic refresh on the strength of the 100% name match — **that was wrong, and the polygon-intersection measurement is what corrected it.** Names matching told us nothing about whether the shapes were right.
- **Do we load 19 districts now knowing 22 may land before the 2027 election?** ★ **Recommend yes, and now emphatically** — it fixes live wrong-riding answers, the change is an in-place geometry update on rows that already exist, and no FK moves. The 19-district map is the law today (LAECA s. 2(1)) and governs until a bill passes. The ask is not whether to load but **who re-checks NT before 2027-10-05**, and whether that belongs in a standing calendar item rather than a one-off note in this dossier. Without an owner, we will discover the 22-district map the way we discovered the Yukon one — from a roster row pointing at a district that does not exist.
- **NT boundary work will not move the attribution number, and the number is 90%, not 95%.** Worth saying plainly so nobody reads a flat attribution metric after the build as a failure — the value of this build is geometric correctness, which no attribution metric will show. The two unattributed rows are `Rj Simpson` (duplicate of `R.J. Simpson`) and `Dawn Anderson` (former MLA never end-dated). Both are roster hygiene: re-run `scripts/audit_politician_duplicates.py` for NT and end-date the stale term. **Should that be folded into the boundary build, or tracked separately?** It is a two-row fix, so folding it in is tempting — but it is a different kind of change and the duplicate-merge rules have their own guardrails (the Cooke rule), so I have not assumed.
- **Is the `...-2013` `source_set` name worth correcting to `...-2014`?** The statute is S.N.W.T. **2014**, c. 21. Renaming would churn 19 `constituency_id` values and every FK pointing at them for zero functional gain. **Recommend leaving it** and noting the discrepancy here — but flagging it because a future reader comparing `source_set` against the statute will otherwise think one of them is wrong.
- **The pre-2013 NT map was not located — is it worth chasing?** Third-party metadata references `NWTElectoralDistricts2011.shp` but no live URL was found. The one unprobed lead is the NWT Discovery Portal (`http://nwtdiscoveryportal.enr.gov.nt.ca/geoportal/catalog/main/home.page`), an Esri Geoportal catalogue. ⓘ Lower stakes than the Yukon equivalent — we hold no pre-2013 rows, so nothing is at risk, and it matters only for attributing pre-2015 Hansard (where a member sat for `Weledeh` or `Tu Nedhe`, districts that no longer exist). Given NT Hansard is `partial`, **recommend deferring** unless historical attribution becomes a priority. Flagging so the decision is explicit rather than an omission.
- **The working REST endpoint is on a host named `sandbox`.** `www.sandbox.geomatics.gov.nt.ca` answers; the production host 404s on the same path. That is almost certainly a GNWT misconfiguration rather than an intended public API, and it could be corrected — in either direction — without notice. The staged ZIP is the durable path and the build should depend on it. ⚠ **But the `EDFrench` field exists only on the REST service**, so if French names ever matter, capture them now rather than assuming the endpoint persists.

## Status

- [x] Current boundaries located and staged (2026-08-18)
- [x] CRS confirmed from `.prj` and cross-confirmed from the REST layer — **ESRI:102002, no EPSG equivalent**, already in our `spatial_ref_sys`
- [x] Attribute schema read from `.dbf` header of the recommended file — 5 fields, no ID column; REST uses different field names and adds `EDFrench`
- [x] `.CPG` read case-insensitively — **uppercase `.CPG`, UTF-8**; mojibake trap confirmed live
- [x] Distinct-ID check — **19 records → 19 distinct IDs**, no duplicate-`constituency_id` risk; 4 districts are multi-part within a single record (max 20 parts)
- [x] GeoJSON vs shapefile verified identical on count, names and geometry — **GeoJSON recommended as build input**
- [x] District count confirmed — 19, three independent ways (statute, file, seat count); `jurisdiction_sources.seats = 19` needs no change
- [x] Current vintage verified as still in force — **LAECA s. 2(1) reads "There are 19 electoral districts"**, and no implementing bill exists in the 20th Assembly's listing
- [x] `effective_from` established as the **legal in-force date** — `2015-10-25`, per S.N.W.T. 2014 c. 21 ("On dissolution of the 17th Legislative Assembly") and the Elections NWT dissolution record; metadata date (2023) recorded as a discrepancy
- [x] District ID reconciliation confirmed — **19/19 slug match, no re-key needed**
- [ ] ⛔ **Ruling A6 violation** — `constituency_id` prefix encodes the generation; re-prefix to `northwest-territories-electoral-districts/` and move the vintage to `boundaries_version`. **Not applied.**
- [x] Re-tested for the BC defect (old geometry under current names) — ⛔ **positive, and worse than BC's**: area is *misassigned*, not missing
- [x] Roster reconciliation confirmed — 19/19 districts filled one-to-one; 2 stale rows are roster hygiene, not boundary gaps
- [x] Licence cleared for internal use — ✅ **OGL-NWT expressly permits redistribution and commercial use, subject to attribution** (`Elections NWT, NWTCG`)
- [x] Held-vs-authoritative geometry measured — ⛔ **5 of 19 districts materially wrong; 2 adjacent pairs have misplaced shared boundaries**
- [ ] Geometry refresh applied — ⛔ **not done; this is the priority NT build item, not a cosmetic one**
- [ ] Prior boundaries located — ⛔ **not published; one unprobed lead (NWT Discovery Portal), recommend deferring**
- [ ] In-force date of the *prior* (2006) order — **needs confirmation; only matters if the prior generation is obtained**
- [ ] Owner assigned for the pre-2027 re-check against the 22-district recommendation — **needs operator call**
- [ ] NT roster hygiene (`Rj Simpson` duplicate, `Dawn Anderson` end-date) — out of scope for this dossier, **raised**
