# Municipal West (BC / SK / MB) — Electoral Boundary Research

> Standalone boundary/roster dossier for British Columbia, Saskatchewan and Manitoba municipal wards.
> Cross-cutting context (methodology, licence matrix, reconciliation strategy) lives in [`overview.md`](./overview.md).
> Per-city legislative dossiers: [`../cities/vancouver.md`](../cities/vancouver.md), [`../cities/winnipeg.md`](../cities/winnipeg.md).
> Sibling municipal dossiers: [`municipal-alberta.md`](./municipal-alberta.md), [`municipal-ontario.md`](./municipal-ontario.md), [`municipal-quebec.md`](./municipal-quebec.md), [`municipal-atlantic.md`](./municipal-atlantic.md).

**Agencies:** each municipality (no provincial ward register in any of the three) | **Enabling statutes:** BC — Local Government Act, R.S.B.C. 2015, c. 1, Part 3 (at-large is the statutory default; wards require a "neighbourhood constituency" bylaw approved by the Lieutenant Governor in Council); SK — The Cities Act, S.S. 2002, c. C-11.1; MB — The Municipal Act / The City of Winnipeg Charter | **Sets held:** 6 | **Rows held:** 49 | **Real ward councils:** 3 (Winnipeg, Saskatoon, Regina)

**Status snapshot (2026-08-18):** ✅ **BC is a clean at-large finding, not a gap — and it has a statutory answer key.** Under the Local Government Act, **at-large election is BC's statutory default**; wards ("neighbourhood constituencies") require a bylaw approved by the Lieutenant Governor in Council. So BC's 12 rows containing **zero wards** is correct and complete, and **nobody should hunt for BC ward boundaries.** ⚠ But two BC sets are named `*-wards` while containing only a city polygon, which reads as a gap on sight. ✅ **Winnipeg is the healthiest set in this dossier** — geometry matches the in-force 2018 wards at **mean 0.34%**, and the one absent ward is identified: ★ **`Elmwood – East Kildonan` (ward 14)**. ⚠ **Regina is the honest failure of this pass: the vintage check is INCONCLUSIVE.** Our 10 rows match neither the 2024 generation (mean 12.34%) nor the 2020 one (mean 11.22%), with individual wards matching one or the other — consistent with a *third*, older generation. Marked `needs confirmation`; per A8.1 it needs polygon intersection, not area. ⛔ **Saskatoon's only located source is an unattributed ArcGIS Online item** with no copyright, no description and no owning organisation — staged but **not accepted as primary**. ★ **Trap: Regina's GeoJSON is EPSG:26913 projected metres with a legacy `crs` member** — not WGS84, unlike every Socrata municipal file. ⛔ **A12: this dossier holds the project's largest CSD-removal exposure — all 15 western CSD rows carry officials, 107 in total, and 104 of those are in BC**, where the CSD row *is* the whole council (Vancouver alone carries 18). Dropping CSD rows as contamination would delete British Columbia from the lookup entirely.

---

## Current boundaries

- **Source URL(s):** https://data.winnipeg.ca/api/geospatial/t4cg-yaxs?method=export&format=GeoJSON ; https://data.winnipeg.ca/api/views/t4cg-yaxs.json ; https://services6.arcgis.com/doi7PAc643EKEEOk/arcgis/rest/services/Saskatoon_Ward_Boundaries/FeatureServer/0 ; Regina's `Wards_2024` shapefile + GeoJSON (staged earlier in this run by another agent — see Staged files; the `regina.ca` origin returns HTTP 403 to automated clients and the retrieval URL was not recorded)
- **Format:** Winnipeg — GeoJSON via Socrata. Saskatoon — ArcGIS FeatureServer, queryable as GeoJSON. Regina — ESRI shapefile (zipped) plus a GeoJSON conversion.
- **CRS / projection:**
  - **Winnipeg: EPSG:4326 (WGS84)** ✅ — no `crs` member (RFC 7946 default), first coordinate `[-97.14512717699358, 49.93576174353671]`. No reprojection needed.
  - **Saskatoon: EPSG:4326** ✅ — requested explicitly via `outSR=4326` on the FeatureServer query, which is the reprojection-free path.
  - ⚠ **Regina: EPSG:26913 (NAD83 / UTM zone 13N) — projected metres, NOT WGS84.** The GeoJSON carries an explicit legacy `crs` member, `{"type":"name","properties":{"name":"EPSG:26913"}}`, and its first coordinate is `[535248.19, 5591196.13]`. The bundled `.prj` confirms `NAD_1983_UTM_Zone_13N` (⚠ with no `AUTHORITY` clause, per A4).
    ★ **This is a trap worth promoting.** RFC 7946 mandates WGS84 and removed the `crs` member entirely, so "it's GeoJSON, therefore it's 4326" is a reasonable-sounding assumption that is **wrong here** — and it fails silently, placing Regina's wards in the Gulf of Guinea rather than erroring. It cost me a bogus 100%-error reading before I caught it. **Check coordinate magnitude on every GeoJSON, regardless of extension.**
- **Attribute schema:**

  | Set | Fields | Notes |
  |---|---|---|
  | Winnipeg `t4cg-yaxs` | `number`, `name`, `councillor`, `phone`, `asst`, `asst_phone`, `clerk`, `clerk_phone`, `community`, `website` | ★ carries the councillor **and** their office contacts |
  | Saskatoon (ArcGIS) | `FID`, `FeatId1`, `OBJECTID`, `DIST_ID`, `DIST_NAME`, `Shape_Leng`, `Shape_Area`, `Shape__Area`, `Shape__Length` | ⚠ no councillor; ⚠ three near-duplicate area/length fields |
  | Regina `Wards_2024` | `OBJECTID`, `ID`, `ELECT_YEAR`, `POPULATION`, `VOTE_POP`, `SHAPE_AREA`, `SHAPE_LEN` | ★ `ELECT_YEAR` self-documents the generation; ★ carries population and voting population |

  ★ **Regina's `ELECT_YEAR` is the single most useful field found in this dossier** — the file states its own generation (`2024`), which is exactly what A5 says never to infer from a filename. The 2020 file's schema differs (`WARD`, `URL`, `POPULATION`, no `ELECT_YEAR`), so the self-documentation is new in 2024.
- **District ID field:** Winnipeg `number` (1–15). Saskatoon `DIST_ID` (1–10). Regina `ID` (1–10). All are dense small integers, all generation-scoped. Our slugs are kebab-case names (`winnipeg-wards/st-vital`) or `ward-N`, so no re-key is required; see Reconciliation.
- **Effective date:** per A10.4, the election the boundaries first governed. **Winnipeg: 2018-10-24** (dataset description: *"updated in November of 2018 to reflect the new council wards"*). **Regina: 2024-11-13** (`ELECT_YEAR = 2024`; Regina's general election was 2024-11-13). **Saskatoon: UNTESTED** — the unattributed source carries no date field.
- **Superseded date:** n/a (current).
- **District count:** Winnipeg **15** ✅ (matches 15 councillors). Saskatoon **10 distinct** ⚠ from **13 records** — a multipart split (W1×2, W5×2, W6×2), exactly A4's "count DISTINCT district IDs, not records". Regina **10** ✅.
- **Difficulty (1–5):** **2** for Winnipeg (documented Socrata, but not discoverable without scoping the catalogue search — see Notes). **3** for Regina (origin WAF-blocked to automated clients). **4** for Saskatoon (no verifiable primary source located).
- **Notes:**
  - ⚠ **Socrata's catalogue API is federated by default and will silently return other cities' datasets.** Querying `https://data.winnipeg.ca/api/catalog/v1?q=ward` returned Calgary's and Edmonton's ward datasets at the top of the results with no indication they were off-domain. `search_context=data.winnipeg.ca` scopes it correctly. **A federated search result is not evidence that the dataset belongs to the host you queried** — worth adding to the probe hierarchy for any Socrata city.
  - ⛔ **`www.regina.ca` returns HTTP 403** to automated clients, and neither `open.regina.ca` nor `opendata.regina.ca` resolves in DNS. Regina's files exist in staging only because another agent retrieved them earlier in this run; **I could not independently reach the origin**, and the source URL was not recorded with them. See handoff items.
  - ⛔ **Saskatoon's source is not verifiably primary.** The ArcGIS Online item `b9fff26dba5a4f5c9e1425e4f9d21654_0` has an empty `copyrightText`, an empty `description`, and `orgName: None` — it is not attributable to the City of Saskatoon. `opendata-saskatoon.hub.arcgis.com` resolves (HTTP 200) but its dataset search API returned no usable result shape. Standing instruction 1 says primary sources only, so this file is staged as a **candidate**, clearly labelled, and must not be loaded until its provenance is established.

## Prior boundaries (immediately preceding)

- **Source URL(s):** https://data.winnipeg.ca/api/geospatial/mp2r-jeav?method=export&format=GeoJSON ; Regina `Wards_2020` shapefile (staged earlier in this run; origin URL not recorded)
- **Format:** Winnipeg — GeoJSON, Socrata (`mp2r-jeav`, "Electoral Wards (2014-2018)"). Regina — zipped ESRI shapefile.
- **CRS / projection:** Winnipeg EPSG:4326. Regina EPSG:26913, `.prj` byte-identical to the 2024 file — ✅ no cross-generation reprojection difference.
- **Attribute schema:** Winnipeg `mp2r-jeav` — `number`, `name`, `councillor`, `phone`, `community` (a subset of the current file; no `asst`/`clerk`/`website`). Regina `WARDS_2020` — `OBJECTID`, `WARD` (character, not numeric), `URL`, `POPULATION`, `SHAPE_AREA`, `SHAPE_LEN`.
  ⚠ **Regina's `SHAPE_AREA` and `SHAPE_LEN` are empty strings in the 2020 file** despite being declared as `F(31,15)`. Areas for the vintage check below had to be computed by parsing the `.shp` polygon rings directly. A loader that trusts the declared area column will get nulls.
  ⚠ **`WARD` is `C(5)` in 2020 but `ID` is `N(6)` in 2024** — the key changed both name and type across the generation.
- **District ID field:** Winnipeg `number`; Regina `WARD` (2020) / `ID` (2024). Generation-scoped in both cities.
- **Effective date:** Winnipeg **2014-10-22** (the 2014 general election). Regina **2020-11-09** (the 2020 general election).
- **Superseded date:** Winnipeg **2018-10-24**. Regina **2024-11-13**.
- **District count:** Winnipeg 15 (unchanged across the redraw — no count signal). Regina 10 (likewise unchanged).
- **Difficulty (1–5):** **1** for Winnipeg; **3** for Regina (same WAF problem).
- **Notes:** ★ Both cities held their ward count constant across the redistribution — Winnipeg 15→15, Regina 10→10 — so, exactly as in Saskatchewan (61→61) and Calgary (14→14), **the count check is blind here and only a geometry comparison can establish vintage.**

## District ↔ elected official mapping

- **Source URL(s):** https://data.winnipeg.ca/api/views/t4cg-yaxs.json (field `councillor`) ; https://www.gov.mb.ca/legislature/members/mla_list_constituency.html (provincial, for contrast) ; Saskatoon and Regina — no councillor field in either boundary source
- **Format:** Winnipeg carries the councillor, their assistant, the ward clerk, phone numbers and a `winnipeg.ca` node URL per ward — the richest district↔official payload in this dossier. Saskatoon's and Regina's boundary files carry none, so both require a separate roster fetch (**UNTESTED** — not located this pass).
- **★ Join quality — measured for Winnipeg:** our 14 `winnipeg-wards/*` politicians match 14 of the 15 councillors in the Socrata file **exactly by name** (Duncan, Gilroy, Rollins, Eadie, Browaty, Sharma, Santos, Orlikow, Allard, Dobson, Chambers, Mayes, Wyatt, Lukes). The 15th, **Emma Durand-Wood (Elmwood – East Kildonan)**, is the ward we do not hold. **14/14 of what we have agrees; the gap is a whole missing ward, not a mismatch.**
- ⚠ **Name normalisation required:** the file writes ward names with spaced hyphens (`Elmwood - East Kildonan`, `Charleswood - Tuxedo - Westwood`) where our rows use em-dashes (`Charleswood—Tuxedo—Westwood`). Same drift as the federal ASCII-vs-typographic apostrophe case.
- ⚠ **No stable per-councillor identifier** in any of the three cities' files — names only.
- **Difficulty (1–5):** **1** for Winnipeg; **UNTESTED** for Saskatoon and Regina.

## Postal-code correspondence (if published)

⛔ **None published by any BC, SK or MB municipality**; time-boxed per A3. Not needed — the lookup is point-in-polygon.

## Terms / Licensing

⚠ **Winnipeg's machine-readable licence field is wrong, and that is the notable finding here.** `data.winnipeg.ca`'s dataset `t4cg-yaxs` declares its licence as, verbatim:

> "Open Government Licence - Prince Edward Island"

★ **A Manitoba city's dataset is tagged with Prince Edward Island's provincial licence.** This is a misconfigured Socrata licence picker, not a legal position — the City of Winnipeg has no relationship to PEI's OGL and cannot grant rights under it. **The consequence is concrete: the machine-readable licence field cannot be trusted as an input to the licence matrix**, here or anywhere else. Winnipeg's actual open-data terms were not read this pass, so Winnipeg's licence is **unresolved**, not "OGL-PEI".

⚠ **Saskatoon:** the ArcGIS Online item reports `license: none` and an empty `copyrightText`. Combined with the missing organisation attribution, there is nothing to rely on. **Unresolved, and compounded by the provenance problem.**

⚠ **Regina:** no licence information accompanies the staged shapefiles, and `www.regina.ca` returns HTTP 403 to automated clients, so the terms page could not be read. **Unresolved.**

**Assessment.** No click-through gate was encountered anywhere in this dossier — nothing was accepted, no account created, no form submitted (standing instruction 3 was not engaged). But unlike Saskatchewan and Manitoba provincial, where I established that **no licence exists**, here all three licences are simply **unread**. That is a materially different state and should not be recorded as ⛔-blocked: internal research use is defensible, redistribution is unverified, and resolving it is three short tasks rather than a policy decision.

⚠ **BC needs no licence work** — there are no BC ward boundaries to license, only CSD polygons sourced from Statistics Canada.

## Rate limits / auth

- **Authentication:** none on any surface reached.
- **Rate limiting:** none encountered; roughly 20 requests across `data.winnipeg.ca`, `hub.arcgis.com`, `services6.arcgis.com`, `opendata-saskatoon.hub.arcgis.com` and `www.regina.ca`. Zero 429s.
- ⛔ **`www.regina.ca` returns HTTP 403** to a plain `curl`. Not tested with a browser `User-Agent` this pass — it may be simple UA-filtering like `elections.sk.ca` rather than a real block. **UNTESTED — retry with a realistic UA during build before concluding Regina is unreachable.**
- ⛔ **DNS:** `open.regina.ca`, `opendata.regina.ca`, `data.saskatoon.ca` and `opendata.winnipeg.ca` do **not** resolve. Recorded so nobody re-probes these plausible-but-wrong hostnames; the working hosts are `data.winnipeg.ca` and `opendata-saskatoon.hub.arcgis.com`.
- ⚠ **Socrata catalogue federation** (see Notes above) — scope with `search_context` or you will get other cities' data.
- **Instruction-source boundary:** no page fetched contained text addressed to an AI agent. Nothing to report under standing instruction 8.

## Staged files

Staging root `/media/bunker-admin/Internal/sovpro/data/boundaries/municipal-west/`; sha256 audit table in [`PROVENANCE.md`](../../../data/boundaries/municipal-west/PROVENANCE.md). **932 KiB of a 500 MB budget.**

| Path | Bytes | Features | Districts | Role |
|---|---:|---:|---:|---|
| `current/winnipeg-electoral-wards.geojson` | 329,525 | 15 | 15 | ★ current Winnipeg wards (2018) |
| `current/regina-wards-2024.geojson` | 179,628 | 10 | 10 | ★ current Regina wards — ⚠ EPSG:26913 |
| `current/regina-wards-2024_shp.zip` | 45,074 | 10 | 10 | same, original shapefile |
| `current/saskatoon-wards_arcgis.geojson` | 156,887 | 13 | **10** | ⚠ **candidate only — provenance unverified** |
| `prior/winnipeg-electoral-wards-2014-2018.geojson` | 207,541 | 15 | 15 | ★ prior Winnipeg wards (2014) |
| `prior/regina-wards-2020_shp.zip` | 35,626 | 10 | 10 | ★ prior Regina wards (2020) |

⚠ **Layout note.** The Regina and Winnipeg files were staged earlier in this run by another agent under a per-city subtree (`municipal-west/regina/current/`, `municipal-west/winnipeg/current/`), which also left a duplicate copy of the Winnipeg GeoJSON. I consolidated everything into the flat `current/` + `prior/` layout used by the brief and by the three finished municipal dossiers, verified the duplicate was byte-identical by sha256 before removing it, and left the file contents untouched. No BC files are staged — see below.

**Nothing staged for BC, deliberately.** There are no BC ward boundaries to stage. The 12 BC rows are whole-municipality CSD polygons whose authoritative source is Statistics Canada's Census Subdivision file, which is the federal agent's territory, not a municipal source.

## Reconciliation with `constituency_boundaries`

**What we hold** (read-only query, 2026-08-18) — **49 rows across 6 `source_set` values**:

| Province | `source_set` | Rows | Of which wards | Embedded CSD row |
|---|---|---:|---:|---|
| MB | `winnipeg-wards` | 15 | **14** | ✅ `census-subdivisions/4611040` Winnipeg, 475 km² |
| SK | `saskatoon-wards` | 11 | 10 | ✅ `census-subdivisions/4711066`, 238 km² |
| SK | `regina-wards` | 11 | 10 | ✅ `census-subdivisions/4706027`, 183 km² |
| BC | `census-subdivisions` (standalone) | 10 | **0** | — 10 at-large cities |
| BC | `vancouver-wards` | 1 | **0** | ✅ `census-subdivisions/5915022`, 116 km² |
| BC | `langley-wards` | 1 | **0** | ✅ `census-subdivisions/5915002`, 10 km² |

All 49 carry `effective_from = '2023-01-01'`, `effective_to = NULL` — the hardcoded literals, meaningless as dates.

### ★ BC: zero wards is CORRECT and complete (A10.3)

**BC's answer key is statutory, and stronger than Ontario's survey-based one.** Under the Local Government Act, unless a bylaw provides otherwise **every council member must be elected from the municipality at large**; wards ("neighbourhood constituencies") require a bylaw that must be approved by the Lieutenant Governor in Council before adoption. At-large is therefore the default and warding the rare exception — the same statutory shape as Alberta's MGA s. 148, and the inverse of Ontario's.

Vancouver's 10 councillors are elected at large. **All 12 BC rows are whole-municipality polygons and that is the complete, correct picture** — there is no BC ward data, and none can exist without a bylaw that has not been made. ✅ **No BC agent-hours should be spent hunting for it.**

⚠ **But the naming actively invites the opposite conclusion.** `vancouver-wards` and `langley-wards` each hold exactly one row, and it is a city polygon, not a ward. On sight these read as 1-row gaps in a ward set. Under A10.2 both should carry `boundary_kind = 'municipality'`; renaming the sets would be better still. This is the same misleading-name problem as Alberta's `grande-prairie-wards`.

⚠ **Two different municipalities are both named "Langley"** — `census-subdivisions/5915002` (City of Langley, 10.2 km², filed under `langley-wards`) and `census-subdivisions/5915001` (Township of Langley, 314.7 km², in the standalone set). Not a duplicate, but a 31× area difference under one name, and a name join would merge them. The CSD codes distinguish them correctly; nothing name-based will.

### ★★ A7 vintage check — Winnipeg correct, Regina INCONCLUSIVE

| City | Rows | vs **current** generation | vs **prior** generation | Verdict |
|---|---:|---|---|---|
| **Winnipeg** | 14 | **mean 0.34%**, median 0.35%, max 0.55% | not needed | ✅ **correct vintage (2018)** |
| **Regina** | 10 | mean 12.34%, 2/10 within 2% | mean 11.22%, 1/10 within 2% | ⚠ **INCONCLUSIVE — neither** |
| **Saskatoon** | 10 | UNTESTED | UNTESTED | ⚠ **unknown** — no trustworthy source to compare against |

**Winnipeg is clean.** A 0.34% mean across 14 wards, with a maximum of 0.55%, is measurement noise — our geometry is the in-force 2018 generation. Winnipeg is the only set in this dossier confirmed correct.

⚠ **Regina is the honest failure of this pass, and I am reporting it as unresolved rather than forcing a verdict.** Our 10 wards match *neither* candidate generation, and the pattern is genuinely mixed rather than uniformly bad:

| Ward | ours (km²) | 2024 | 2020 | vs 2024 | vs 2020 |
|---|---:|---:|---:|---:|---:|
| Ward 9 | 23.90 | 25.19 | 23.93 | 5.11% | **0.13%** |
| Ward 5 | 12.85 | 12.93 | 14.24 | **0.63%** | 9.74% |
| Ward 1 | 16.19 | 15.89 | 17.90 | **1.89%** | 9.57% |
| Ward 6 | 30.40 | 36.55 | 29.63 | 16.81% | **2.59%** |
| Ward 2 | 19.93 | 15.68 | 17.23 | 27.13% | 15.69% |
| Ward 3 | 9.29 | 8.44 | 7.33 | 9.98% | 26.76% |
| | | | **mean** | **12.34%** | **11.22%** |

Some wards match 2024 closely (1, 5), others match 2020 closely (6, 9), and several (2, 3, 7, 10) match neither. **That is the signature of a third generation**, not of a botched comparison — Regina's wards were also redrawn before 2020, and Open North's set may predate both files I hold. Two caveats I cannot rule out: my 2020 areas were computed by parsing `.shp` rings in pure Python because the file's `SHAPE_AREA` column is empty, and Regina's ward geometry follows a river, so drawing-convention differences (A8.1) could contribute.

**Per A8.1 this needs polygon intersection, not area** — `ST_Area(ST_Intersection(ours, candidate)) / ST_Area(ours)` per ward against each generation, which PostGIS can do trivially once the files are loaded to a staging table. **Marked `needs confirmation`; do not load Regina on the assumption it is either generation.**

**Saskatoon was not vintage-checked at all** because the only located source is unattributed. Per A7 its matching 10-ward count proves nothing.

### ★ Winnipeg's missing ward

**`Elmwood – East Kildonan` (ward number 14, Councillor Emma Durand-Wood).** Identified two ways that agree: it is the one authoritative ward name absent from our 14, and it is the one councillor in the Socrata file with no counterpart in our roster. Winnipeg's own dataset is the authority for both facts.

⚠ Per A7's mechanism, the likely cause is the familiar one — an Open North representative record carrying no `related.boundary_url`, which yields both a missing polygon and a NULL `constituency_id` from a single `None`. Worth confirming during build rather than assuming.

### ⛔ A12 — every western CSD row carries officials, and BC's carry entire councils

Verified per set with a query rather than inferred, per A12. This is the **largest exposure in the
project** — 9× the Atlantic block's 14:

| Province | CSD rows | Officials on them | Council shape |
|---|---:|---:|---|
| **BC** | 12 | **104** | at-large — the CSD row is the *entire* council |
| **AB** (for contrast, see [`municipal-alberta.md`](./municipal-alberta.md)) | 6 | 22 | 2 at-large, 4 hybrid |
| **SK** | 2 | 2 | hybrid — mayor only |
| **MB** | 1 | 1 | hybrid — mayor only |
| | **21 (west + AB)** | **129** | |

Per-row, BC is stark: **Vancouver 18**, Surrey / Coquitlam / Kelowna / Langley Township / Victoria /
Abbotsford / Burnaby **9 each**, Richmond 8, New Westminster 7, Langley City 7, Saanich 1.

⛔ **Not one of the 15 western CSD rows is removable.** Because BC has no ward polygons at all, its CSD
rows are not a redundant second tier — they are the *only* geometry attaching 104 sitting BC officials
to anything. A migration written from the "CSD rows are contamination" framing would remove British
Columbia from the postcode lookup completely, silently, and with no row-count signal that anything
had gone wrong.

★ **Winnipeg, Saskatoon and Regina are hybrids in the minimal form** — one official (the mayor) on the
CSD row, councillors on wards. Structurally the same category as St. John's, but carrying 1 official
instead of 6.

⚠ **This supersedes the "contamination" framing** used elsewhere in this dossier and in A10.1. The
defect is not the CSD rows' presence; it is `lookupBoundariesAtPoint` overwriting in a loop instead of
preferring the smallest matching polygon. **Fix the resolver, keep the rows.**

### ⚠ A12.2 — overwrite-bug severity in the west is modest

| Set | CSD km² | smallest district km² | ratio |
|---|---:|---:|---:|
| `winnipeg-wards` | 474.8 | 8.5 | 56× |
| `saskatoon-wards` | 238.0 | 8.6 | 28× |
| `regina-wards` | 182.5 | 8.0 | 23× |

None approaches Halifax's 703× or Wood Buffalo's 597×; the three western ward cities are compact, so
the CSD polygon is only tens of times larger than a ward rather than hundreds. ⚠ **But BC is a special
case the ratio cannot express**: with no ward rows, a BC PIP returns exactly one polygon and it is
*correctly* the whole municipality — there is nothing to overwrite and nothing to fix.

### A10.1 stacking — present, but milder than Ontario

Four of the six sets carry an embedded `census-subdivisions/<CSD>` row. A live PIP at each city hall:

| Point | Polygons returned | What |
|---|---:|---|
| Winnipeg City Hall | **2** | `Point Douglas` (23 km²) + `Winnipeg` CSD (475 km²) |
| Saskatoon City Hall | **2** | `Ward 6` (9 km²) + `Saskatoon` CSD (238 km²) |
| Regina City Hall | **2** | `Ward 3` (9 km²) + `Regina` CSD (183 km²) |
| Vancouver City Hall | **1** | `Vancouver` CSD only — ✅ correct for an at-large city |
| Surrey City Hall | **1** | `Surrey` CSD only — ✅ correct |

**Two polygons, never Mississauga's four.** There is no `census-divisions` tier for these provinces and no double-ID duplication of a ward, so the western case is mild tier-stacking only. ★ And per A10.1 the CSD rows are **load-bearing**: they are the only polygons carrying BC's at-large councillors and mayors, so deleting them would remove BC from the lookup entirely.

⚠ `lookupBoundariesAtPoint` collapses to one row per level by overwriting in a loop, so which of the two municipal polygons wins is non-deterministic — the same defect the Ontario pass found, reproduced here at half the magnitude.

### A6 prefix migration

✅ **All six western municipal prefixes are already generation-free** (`winnipeg-wards`, `saskatoon-wards`, `regina-wards`, `vancouver-wards`, `langley-wards`, `census-subdivisions`) and comply with A6 as they stand. **No prefix migration is required for BC, SK or MB municipal.**

Under recommendation (d): `authority = 'city-of-winnipeg'` / `'city-of-saskatoon'` / `'city-of-regina'` / `'statcan-csd'`; `authority_district_id` = Winnipeg `number`, Saskatoon `DIST_ID`, Regina `ID`, CSD rows the SGC code. `boundary_kind` per A10.2: `district` for wards, `municipality` for all 14 CSD rows. Neither BC, SK nor MB has a borough tier.

**Proposed temporal values:**

| Generation | `boundaries_version` | `effective_from` | `effective_to` | Rows |
|---|---|---|---|---|
| Winnipeg 2018 wards | `2018-election` | `2018-10-24` | `NULL` | 15 |
| Winnipeg 2014 wards | `2014-election` | `2014-10-22` | `2018-10-24` | 15 (available, not held) |
| Regina 2024 wards | `2024-election` | `2024-11-13` | `NULL` | 10 |
| Regina 2020 wards | `2020-election` | `2020-11-09` | `2024-11-13` | 10 (available, not held) |
| Saskatoon | UNTESTED | `needs confirmation` | — | 10 |

## Research-handoff items

- **⚠ Regina's vintage is unresolved and must not be guessed.** Our 10 rows match neither the 2024 nor the 2020 generation on area (12.34% / 11.22% mean), with individual wards matching one or the other — most consistent with a third, older generation. **Per A8.1 the next step is polygon intersection, not a better area comparison**: load both staged generations to a scratch table and compute `ST_Area(ST_Intersection(ours, candidate))/ST_Area(ours)` per ward. That is a build-phase task of a few minutes and it will settle it definitively. **Do not load Regina until it is settled** — a wrong-generation load here would be the Calgary mistake repeated knowingly.
- **⛔ Saskatoon has no verifiable primary source.** The only located file is an unattributed ArcGIS Online item (empty `copyrightText`, empty description, `orgName: None`) which nonetheless yields a plausible 10 distinct wards from 13 multipart records. Staged as a **candidate only**. `opendata-saskatoon.hub.arcgis.com` resolves but its search API returned no usable result; the City's real open-data catalogue was not found. **Needs either a proper source or an explicit decision to accept an unattributed one** — I would not load it as-is.
- **⚠ Regina's origin is WAF-blocked to me and its files arrived without a recorded source URL.** `www.regina.ca` returns HTTP 403 to plain `curl` and the two `regina.ca` open-data hostnames do not resolve. The staged shapefiles came from another agent earlier in this run. **Two cheap actions:** retry `www.regina.ca` with a realistic browser `User-Agent` (Elections Saskatchewan turned out to be UA-filtering, not a real block), and recover the source URL so `PROVENANCE.md` has a real citation instead of an attribution note.
- **★ Add Winnipeg's missing `Elmwood – East Kildonan` ward.** One INSERT into an already-correct-vintage set; the authoritative geometry is staged. Same shape as Manitoba provincial's `The Pas-Kameesak` — and, as there, the cheapest correctness win available in this dossier.
- **⚠ Three licences are unread, not absent.** Winnipeg's Socrata declares **"Open Government Licence – Prince Edward Island"** on a Manitoba dataset, which is a misconfiguration and cannot be relied on; Saskatoon reports `none`; Regina's terms page is behind the 403. This is materially different from SK/MB provincial, where no licence exists at all — here the work is reading three pages. ★ **The transferable lesson is worth promoting: a machine-readable licence field can be flatly wrong, so licence-matrix rows should cite a terms page someone actually read, never a portal's metadata tag.**
- **⚠ Rename or reclassify `vancouver-wards` and `langley-wards`.** Each holds one city polygon and zero wards. Under A10.2, `boundary_kind = 'municipality'` records this structurally so no future agent reads BC's correct at-large picture as a 12-row gap. Same fix as Alberta's `grande-prairie-wards`.

## Roster sources — BC and MB, probed 2026-09-02

⚠ Rule #5 was waived by the operator for this pass. Findings only; no ingester built.

### ✅ BUILT 2026-09-02 — `compare-bc-municipal-roster` / `apply-bc-municipal-roster`

`services/scanner/src/legislative/bc_municipal_roster.py`. Verified against the completed
2022 cycle: **12 councils, 113 authority rows, 111 matched.**

⛔ **The two remainders are the important result, and they are not defects.** The authority
lists *Chak Au* for Richmond (he has since moved to federal politics — there is a federal MP
row for him) and *Misty Van Popta* for Langley Township (we hold her replacement, Blair
Whitmarsh). In both cases **our data is more current than the 2022 result**. A wholesale
apply would have re-installed one and reverted the other, on a green verdict, because a
`gap` looks identical whether the hole is ours or the publisher's. Hence the **90-day
freshness window**: past that, a blanket write is refused and `--council` is required.

⚠ Four other things the build found that this research did not:
- **Vancouver's polygon is served by two elected bodies.** The Park Board's 7 commissioners
  file under `Jurisdiction Type = "Park Board"`, not `"City"`, so they need their own key —
  without it they read as 7 retirements. The parkboards report is province-wide (Cultus Lake
  has one too).
- **`verify_mapping` must check AREA, not name.** Our own boundary table calls both Langleys
  "Langley", so transposing their CSD codes passes every name check and 7-vs-9 members is
  plausible either way round. They differ 30x in area.
- **Four of five apparent 2022 mismatches were name-form artefacts** (Richard T. Lee, Robert/
  Rob Rindt, Christopher Mark Coleman, Angela Kate Haer). A loose matcher handles them for
  reporting only; it requires the surname token to match exactly.
- **Use the apex host.** `www.localelections.ca` with a generic tool user-agent returns 403;
  `localelections.ca` with a descriptive one returns 200.

### ★ BC is ONE province-wide endpoint, not twelve scrapes

**`https://localelections.ca/report/index.php`** — CivicInfo BC's report builder.
CivicInfo BC is the not-for-profit that runs BC's local-election database, board-governed
by BC local governments, with data entered by the municipal Chief Election Officers
themselves. It is the closest thing BC has to a local-election authority; there is no
provincial administrator.

```
/report/index.php?mayors=on&councillors=on
  &incumbent=on&servedDiff=on&servedPrior=on&prevExp=on&new=on&unknown=on
  &rtype=results[&year=2022]
```

Other office toggles: `directors` (RD electoral areas), `parkboards`, `trustees`,
`islandstrustcouncillors`, `commissioners`. Two GETs cover the entire province.
Server-rendered HTML table. `rtype=results` adds `Elected` and `Number of Votes`;
the endpoint **pre-filters to winners**, so `Elected` is not a column you filter on.

Carries: name, office (`Elected Type`), slate (`Elector Organization`), incumbency
(`Experience`), votes, acclamation. ⛔ **No ward column — correctly**, which independently
confirms the statutory at-large finding: all 104 BC members attach to
`boundary_kind='municipality'`.

★ It also natively disambiguates **Langley (City)** from **Langley (Township)** via
`Jurisdiction Type` — the name-collision this dossier previously called unsolvable.

**Validated against the completed 2022 cycle** (1,025 rows): 97 authoritative against our
104 held rows, **93 exact matches**. The four non-matches decomposed into two name-form
artefacts (Rob/Robert), two cases where **our data is MORE current** than 2022 (post-election
turnover in Langley Twp and Richmond), one typo of ours (Lovegrove, fixed in `0127`) and one
real gap — **Saanich held 1 of 9 members**, filled by `0127`.

⚠ **Parsing hazards.** Per-municipality name casing is inconsistent (Kelowna submits ALL
CAPS, New Westminster all-caps surnames only). Row width is ragged — reject rows whose cell
count ≠ header count rather than positional-indexing. Emails are Cloudflare-obfuscated.
Archived cycles drop the contact columns.

⚠ **The AMO trap applies in full.** The 2026 list is a CANDIDATE list until the count;
nominations close 2026-09-11 16:00. Compare per-municipality, never ingest wholesale.

⛔ **Fetch posture — operator decision, 2026-09-02.** `localelections.ca/robots.txt` is
`User-agent: *` / `Crawl-delay: 5`, Disallow only `/config/ /wp-admin/ /wordpress/ /blog/`
— nothing on `/report/`. Its **parent domain `civicinfo.bc.ca` is far more restrictive**:
`Content-Signal: ai-train=no, use=reference` and `User-agent: ClaudeBot → Disallow: /`.
Same organisation. The decision was: **fetch `localelections.ca` only**, honour its
crawl-delay, use a descriptive CPD user-agent with a contact URL, cache by etag
(convention #6), and **never fetch civicinfo.bc.ca**. ⚠ Use the apex host — `www.` plus a
generic tool user-agent returns 403.

⛔ **Dead ends, so nobody repeats them:** `civicinfo.bc.ca/directories`, `/data`,
`/election-results` — all Cloudflare 403. `catalogue.data.gov.bc.ca` CKAN has **no**
elected-official dataset, only boundary layers; DataBC is not a roster source. Wayback-found
`/ajax/electionreports/*.php` paths are either retired (IIS 404) or 403. **UBCM was reached
(200) but NOT exhaustively probed** — it is the unexplored fallback if the licence position
ever changes.

Difficulty **2**. Source prefix must be `civicinfo-bc:`, never `opennorth:`, so
`detect_retirements` cannot sweep it — same reasoning as `mamh-qc:` and `amo-on:`.

### ✅ MB BUILT 2026-09-02 — `compare-mb-municipal-roster` / `apply-mb-municipal-roster`

`services/scanner/src/legislative/mb_municipal_roster.py`. **16 of 16 seats agree** today,
so MB is verified correct rather than merely assumed correct.

★ **Joined on the ward NUMBER, not the name.** Our `winnipeg-wards` polygons carry
`authority_district_id` as a dense 1..15 and Socrata carries the same value as `ward_id`.
That sidesteps the `web_name` trap below entirely, and the compare confirms ward 7
resolving correctly.

⚠ Two things the build found that this research did not:
- **The trap here is the INVERSE of Ontario's.** Winnipeg publishes a settled council
  updated *by hand* after each election, so `current_council` names the OUTGOING council
  until the city refreshes it. The danger is reading too LATE, not too early.
- **A superseded `--year` is lethal.** Before the guard, `--year 2018` dry-ran to
  installed=4 / retired=5 — five sitting councillors retired and their predecessors
  reinstated, on a clean run. The retained-prior-cycles property that makes this source
  good is the same one that makes an unguarded `--year` dangerous.

### MB — a better source than this dossier's

⛔ **Prefer `data.winnipeg.ca/resource/r4tk-7dip.json` ("Council Data") over the ward
GeoJSON.** Socrata, difficulty **1**, licence **declared** "Canada Open Government Licence".
⚠ Note that is a *different* dataset from `t4cg-yaxs` (the ward geometry), which still
carries the misconfigured `Open Government Licence - Prince Edward Island` value this
dossier flagged — re-confirmed 2026-09-02, still wrong.

Three reasons it beats the geometry file:
1. It carries the **mayor** (`ward_id=0`) — the gap a ward file structurally cannot fill.
2. `current_council` is an explicit boolean; no inference from a filename or election date.
3. It **retains prior cycles** (2014/2018/2022, 16 rows each), so retirement detection is a
   diff *inside one file* rather than a sweep-and-deactivate against a mirror.

⚠ Correction to this dossier: the geometry file's `councillor` field IS populated on all 15
features, but `asst` / `asst_phone` / `clerk` / `clerk_phone` are **NULL on every feature** —
the "carries office contacts" claim overstates it.

⛔ **`web_name` is not a safe join key.** It looks perfect — kebab-case, matches our
`winnipeg-wards/<slug>` form, agrees on 15 of 16 rows — and diverges on exactly one: ward 7
is `Charleswood - Tuxedo - Westwood` but `web_name` is the truncated `charleswood-tuxedo`,
which matches **no polygon**. Join on `ward_id` (dense 1–15) or `slugify(name_english)`.
⚠ Ward names are cycle-scoped, so scope every join to `current_council=true`.

✅ **No 2026 MB redraw** — `t4cg-yaxs` is still the only current ward set, so the 2018
geometry and slugs survive the election and the join key holds. ⚠ Scope catalogue searches
with `search_context=data.winnipeg.ca`; unscoped queries return Calgary's and Edmonton's wards.

**MB is currently CORRECT** — all 16 members match the authority by name with correct ward
attachment. Its exposure is purely forward-looking: **2026-10-28**.


## Status

> ⚠ **Reconciled 2026-09-01.** The checkboxes below are the **research phase's** record
> (closed 2026-08-18) and several were overtaken by the build — migrations `0064`–`0121`,
> merged to `main` 2026-08-28. An unticked box here is **not** evidence that something is
> still outstanding.
>
> **Live counts: [`PROGRESS.md`](./PROGRESS.md)** (generated by `boundary-progress`).
> **What actually landed:** the migration headers, which are the accurate record.
> This file's job is the *reasoning* — sources, licences, traps, vintage evidence.

- [x] BC at-large established from statute, not inference — Local Government Act, LGIC-approved bylaw required for wards
- [x] Current boundaries located and staged — Winnipeg 15/15, Regina 10/10
- [x] Prior boundaries located and staged — Winnipeg 2014, Regina 2020
- [x] CRS confirmed per file — Winnipeg/Saskatoon WGS84; ★ **Regina EPSG:26913, not WGS84**
- [x] Attribute schemas parsed for all three ward cities, both generations where held
- [x] ★★ A7 vintage check run — **Winnipeg correct (0.34%)**; Regina **inconclusive**; Saskatoon untestable
- [x] ★ Winnipeg's missing ward identified — **`Elmwood – East Kildonan` (14)**
- [x] ★ A10.1 stacking measured — 2 polygons per PIP, not 4
- [x] ⛔ **A12 hybrid check — all 15 western CSD rows carry officials (107; BC alone 104); NONE removable**
- [x] ⚠ A12.2 ratios measured — Winnipeg 56×, Saskatoon 28×, Regina 23×; no extreme case in the west
- [x] A10.3 at-large distinguished from gap — all 12 BC rows correct and complete
- [x] A6 compliance confirmed — all six prefixes already generation-free
- [x] Staging layout reconciled with the earlier agent's per-city tree, duplicate verified by sha256 and removed
- [ ] Regina vintage resolved — **blocked: needs polygon intersection during build**
- [ ] Saskatoon primary source established — **blocked: only an unattributed candidate exists**
- [ ] Regina source URL recovered and origin reachable — **blocked: HTTP 403, UA retry untested**
- [ ] Three licences read and recorded — **unresolved (Winnipeg's declared licence is wrong)**
