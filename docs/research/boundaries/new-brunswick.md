# New Brunswick — Electoral Boundary Research

> Standalone boundary/roster dossier for New Brunswick. Cross-cutting context
> (methodology, licence matrix, reconciliation strategy) lives in [`overview.md`](./overview.md).
> The legislative-data dossier for this jurisdiction is at [`../new-brunswick.md`](../new-brunswick.md).

**Agency:** Elections New Brunswick (data published through GeoNB / Service New Brunswick) | **Website:** https://www.electionsnb.ca | **Districts (current):** 49 | **Current order:** N.B. Reg. 2023-42, *Electoral Districts Boundaries Regulation*, in force 2024-09-19 | **Next redistribution:** commission due 24–25 months before the second scheduled general election after 2024 — i.e. established ~2030, applying to the 2032 general election

**Status snapshot (2026-08-18):** ✅ **Cracked end to end — and the licensing alarm was a false alarm.** ★ Both generations of authoritative district geometry are staged (49 + 49 polygons, direct from GeoNB, difficulty **1**), the enacting regulations and their commencement dates are pinned to the day from the statutory instruments, and the roster↔district name join is **49/49 exact with zero residue in either direction**. ⚠ The 22 rows we hold are now diagnosed precisely, not approximately: they are the **2018 snapshot of the superseded 2013-46 generation**, matching that generation's areas to a mean of 1.32% and diverging from the in-force geometry by a mean of **124.87%** — Moncton Northwest is off by 996%, Moncton East by 743%, Miramichi Bay-Neguac by 387%. All 22 are the "confident wrong riding" failure mode at full strength; 27 districts return nothing at all, and 47% of the province's land area has no provincial polygon. ✅ **The GeoNB flow-down clause does not bind data taken from GeoNB today.** The clause Open North reproduces is § 4.5 of the *GeoNB License Agreement* dated **2012-07-04** — superseded in 2015 by the **GeoNB Open Data Licence v1.0**, which is the licence shipped inside every current download bundle and which contains **no flow-down of any kind**. Independently corroborated: `open.canada.ca` tags every NB electoral dataset `license_id: nb-oglnb`. Re-sourcing from GeoNB extinguishes the compliance gap rather than mitigating it, and § Research-handoff items gives the operator a concrete minimal implementation for the residual attribution obligation. ⏸️ Two sign-offs remain, neither blocking.

**Amendment pass (2026-08-18, second sweep).** Re-worked against brief amendments A1–A5. Four things changed materially:

- ⚠ **`effective_from` for the prior generation was wrong and is corrected.** ~~2013-11-05~~ → **2014-08-21**. Applying the A2 ruling exposed that `laws.gnb.ca`'s "Revoked on `<date>`" header field is the **consolidation cutoff, not a legal date** — N.B. Reg. 2006-27 carries *both* fields separately and they differ ("came into force on August 18, 2006" vs "consolidated to November 5, 2013"), which proves it. The legal date comes from the statutory trigger instead. Details in § Prior boundaries.
- ★ **A tier-1 source I had missed: the NB open-data portal at `gnb.socrata.com` serves these datasets as WGS84 GeoJSON** through a documented Socrata API, mirrored on `open.canada.ca`. It would eliminate the reprojection step entirely — except that **it stops at the 2020 generation** and has no 2024 dataset, so it cannot supply the in-force boundaries. See § Alternative distribution points.
- ★ **A5's Wayback CDX technique paid off twice:** it surfaced a **KMZ variant of the current districts** (WGS84-native, now staged) and an entire superseded download directory, `downloads/prov_electoral_districts/`, holding standalone per-generation bundles that are **still live at the origin** and are cleaner than the combined historic archive.
- ✅ **A4 traps checked, and two of them bite here.** No `.prj` in any of the eleven files carries an `AUTHORITY` clause — EPSG:2953 had to be derived from the projection parameters. Records-vs-distinct-IDs is clean in every generation. Case-insensitive `.cpg` sweep found no uppercase variants but did confirm two generations ship none at all.

---

## Current boundaries

- **Source URL(s):** https://geonb.snb.ca/downloads/provincial_elections/geonb_2024_ped-cep_shp.zip ; https://geonb.snb.ca/downloads/provincial_elections/geonb_2024_ped-cep_fgdb.zip ; https://geonb.snb.ca/downloads/provincial_elections/geonb_2024_ped-cep_kmz.zip ; https://geonb.snb.ca/arcgis/rest/services/GeoNB_ENB_Provincial_Elections/MapServer/2
- **Format:** SHP, zipped (1,252,663 bytes) — **recommended**. Also FGDB (818,844 bytes) and **KMZ (2,436,011 bytes)**. No GeoJSON. The KMZ was found via the A5 Wayback CDX sweep, not from any page: it is unlinked from the catalogue *and* absent from the ArcGIS service listing. It is WGS84-native, which is tempting, but see Notes — its attributes are unusable.
- **CRS / projection:** **EPSG:2953** — ⚠ **derived from the projection parameters, because the `.prj` carries no `AUTHORITY` clause.** Verified: *zero of the eleven* `.prj` files across all staged NB generations contains the string `AUTHORITY`, so EPSG auto-detection will fail on every one of them and the build must hardcode the code. Verbatim `geonb_2024_ped_cep.prj`: `PROJCS["NAD_1983_CSRS_New_Brunswick_Stereographic",GEOGCS["GCS_North_American_1983_CSRS",DATUM["D_North_American_1983_CSRS",SPHEROID["GRS_1980",6378137.0,298.257222101]],PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]],PROJECTION["Double_Stereographic"],PARAMETER["False_Easting",2500000.0],PARAMETER["False_Northing",7500000.0],PARAMETER["Central_Meridian",-66.5],PARAMETER["Scale_Factor",0.999912],PARAMETER["Latitude_Of_Origin",46.5],UNIT["Meter",1.0]]`. Parameter-by-parameter against the EPSG:2953 definition (NAD83(CSRS) / New Brunswick Stereographic): projection Double_Stereographic ✓, latitude of origin 46.5 ✓, central meridian −66.5 ✓, scale factor 0.999912 ✓, false easting 2 500 000 ✓, false northing 7 500 000 ✓, ellipsoid GRS 1980 ✓, unit metre ✓ — all eight match, no ambiguity. Two independent corroborations: the ArcGIS service reports `wkid 2036 / latestWkid 2953`, and GeoNB's own `read_me.txt` states "EPSG code: 2953" in prose. `.shp` header confirms projected metres: shapeType 5 (Polygon), bbox `(2306896.8, 7275121.5)–(2713275.2, 7677113.0)`.
- **Attribute schema:** from the `.dbf` header of **this specific file** (`geonb_2024_ped_cep.dbf`, 6 fields, 49 records, last-updated 2024-08-22) — `DIST_ID` N(10), `PED_Names_` C(254), `LabelField` C(254), `Colour` C(2), `Shape_Leng` F(19,11), `Shape_Area` F(19,11). Encoding UTF-8, declared in `geonb_2024_ped_cep.cpg` (lowercase extension; a case-insensitive sweep found no uppercase `.CPG` anywhere in the NB corpus). ⚠ Do not carry this schema across to the other GeoNB files — the polling-division bundle for the same generation uses a **different 12-field schema** (`Name_Both`, `PED`, `ProvPoll`, `PED_Names_`, `PED_Names1`, `Electors_`, `Date`, `PED_P0`, `ProPollPad`, …), and the prior generations differ again. Read every header.
- **District ID field:** **`DIST_ID`, integer 1–49.** ★ It is not an arbitrary sequence — it is the map number used by the enacting regulation itself. N.B. Reg. 2023-42 s. 3(a) reads "Restigouche West, the boundaries of which are shown on the **map 1** – Restigouche West / Restigouche-Ouest in Schedule A", and `LabelField` is literally `"1-Restigouche West / Restigouche-Ouest"`. `DIST_ID` is therefore the authoritative statutory district number and `PED_Names_` the authoritative statutory map name, byte-for-byte. It does **not** match anything we currently store — see Reconciliation. ⚠ `DIST_ID` is stable *within* a generation only; see the trap below.
- **Effective date:** **2024-09-19** → `effective_from`. **Legal in-force date, per the A2 ruling.** Statutory instrument: **N.B. Reg. 2023-42 (O.C. 2023-162)** under the *Electoral Boundaries and Representation Act*, RSNB 2014, c. 106. Section 5 verbatim: "This Regulation comes into force on the first dissolution of the Legislative Assembly after April 24, 2023." The 60th Legislature was dissolved **2024-09-19** for the 2024-10-21 general election. **Competing dates, all rejected, recorded so nobody re-litigates them:**

  | Candidate | Value | What it actually is |
  |---|---|---|
  | ✅ **legal in-force** | **2024-09-19** | first dissolution after 2023-04-24, per Reg. 2023-42 s. 5 — **use this** |
  | ⛔ regulation filed | 2023-06-29 | O.C. date; the regulation existed but was not in force for 15 months |
  | ⛔ GeoNB `read_me.txt` "DATE" | 2023-09-29 | agency dataset-metadata date |
  | ⛔ GeoNB catalogue "Date" column | 2025-03-06 | catalogue-page refresh date, later still |
  | ⛔ file `Last-Modified` | 2024-08-22 | when the zip was written to the origin |
  | ⛔ commission final report filed | 2023-03-12 | filed with the Clerk; report ≠ regulation |

  ⚠ **Do not use `laws.gnb.ca`'s "Revoked on `<date>`" header field as a legal date for anything.** It is the consolidation cutoff. Proof: N.B. Reg. 2006-27 carries the two as *separate* footer notes with *different* values — "This Regulation came into force on August 18, 2006" and "This Regulation is consolidated to November 5, 2013". For 2023-42 the two happen to coincide, which is exactly why it is a trap.
- **Superseded date:** n/a — current.
- **District count:** **49**, matching the 49-seat Legislative Assembly exactly. ★ Counted as **DISTINCT `DIST_ID`, not records** (A4): `.dbf` records = 49 **and** distinct `DIST_ID` = 49, so this file is strictly one row per district with no island-split duplicates. That was worth checking — New Brunswick has Grand Manan, Campobello, Deer Island, Miscou and Lamèque, and exactly one record in the file is multipart (2 parts). Same 1:1 property verified for all four prior generations. Two further independent confirmations of the count: ArcGIS `returnCountOnly` = 49, and N.B. Reg. 2023-42 s. 3 enumerates paragraphs (a)–(ww) = 49.
- **Difficulty (1–5):** **1** — plain HTTPS `GET` on a static file, plus a documented open ArcGIS REST service as a second path.
- **Notes:** ★ **The archive is not linked from the GeoNB catalogue.** The catalogue rows titled "Electoral districts — Provincial, current (2025)" and "Electoral districts — Provincial, historic" both link to the *polling-division* bundles (`geonb_2025_ppd_svp_*.zip`, `geonb_historic-historique_ppd_svp_*.zip`), not to any district file. The `ped-cep` archives were found by probing the `provincial_elections/` download directory directly, and the CDX sweep later confirmed the set. They are public, stable and `Last-Modified: Thu, 22 Aug 2024` — but they cannot be reached by browsing, so the URL is the record. Note also the underscore/hyphen inconsistency that defeats guessing: the *archive* is `geonb_2024_ped-cep_shp.zip` (hyphen) while the *shapefile inside it* is `geonb_2024_ped_cep.shp` (underscore).

  ⚠ **The DBF 10-character field-name limit renames a field between access paths**: the ArcGIS service calls it `PED_Names_B`, the shapefile `.dbf` calls it `PED_Names_`. A loader written against the REST schema will `KeyError` on the shapefile.

  ⚠ **A generation label in the catalogue does not mean what it says** (A5's "never trust a filename"). The catalogue's newest provincial row is titled "current (2025)" — that is the **2025 polling-division revision**, not a 2025 district generation. There is no 2025 district generation; the districts in force are the 2024 file, and in-force status here was established from **N.B. Reg. 2023-42 s. 5 plus the dissolution date**, not from any filename, folder or catalogue label.

  ⓘ **Payload verified, not just status codes** (A4). Every `200` was confirmed to be a real archive — `unzip -l` succeeds and the internal structure is as expected; every `404` returned an HTML body of zero content-length. No wrong-vintage path served a 200 error page.

  ⚠ **The KMZ is a trap despite being WGS84-native.** `geonb_2024_ped-cep_kmz.zip` unpacks to a `doc.kml` with 49 `<Placemark>`s in plain lon/lat degrees (`-66.61890170282737,48.0249941985088,0`) — no reprojection needed. But it has **zero machine-readable attributes**: `<ExtendedData>`, `<SchemaData>` and `<SimpleData>` counts are all 0, and `DIST_ID` / `PED_Names_B` / `Num_PED` / `Colour` exist only as rows of an HTML `<table>` inside a CDATA `<description>` blob. The only structured field is `<name>`, formatted `"1 / Restigouche West / Restigouche-Ouest"` — which uses `" / "` as **both** the ID separator and the English/French separator, so it is genuinely ambiguous without the "first token is the integer ID" rule (and districts with no distinct French name have only two tokens: `"6 / Caraquet"`). **Recommendation: load the shapefile, and use the KMZ as an independent check that `ST_Transform` produced the right answer.** That check is worth having — a silent reprojection error is precisely the Fort Erie failure mode, and here we have a free second opinion in the target CRS.

## Prior boundaries (immediately preceding)

- **Source URL(s):** https://geonb.snb.ca/downloads/provincial_elections/geonb_historic-historique_ped-cep_shp.zip ; https://geonb.snb.ca/arcgis/rest/services/GeoNB_ENB_Provincial_Elections/MapServer/0 — and ★ **standalone per-snapshot bundles under a superseded directory, unlinked from anywhere but still live at the origin**, found by the A5 Wayback CDX sweep and then tested against the live host: https://geonb.snb.ca/downloads/prov_electoral_districts/geonb_2020_ped-cep_shp.zip (813,676 B) ; https://geonb.snb.ca/downloads/prov_electoral_districts/geonb_2018_ped-cep_shp.zip (791,306 B) ; https://geonb.snb.ca/downloads/prov_electoral_districts/geonb_2018_ped-cep_kml.zip (1,389,185 B) ; https://geonb.snb.ca/downloads/prov_electoral_districts/geonb_2014_ped-cep_shp.zip (3,166,069 B) ; https://geonb.snb.ca/downloads/prov_electoral_districts/geonb_2010_ped-cep_shp.zip (1,756,537 B). All `200` with `application/x-zip-compressed`. `geonb_ped-cep_shp.zip` and `geonb_2020_ped-cep_kml.zip` are `404` — the CDX index lists them but the origin has dropped them, so **test candidates against the live origin rather than trusting the index**. The combined `historic-historique` archive already staged contains the same content; these standalone URLs are recorded because pulling one snapshot is cheaper than a 6 MB archive.
- **Format:** SHP, zipped (6,206,225 bytes), containing four snapshots in four directories — `2010/` (`geonb_2010_ped-cep`), `2014/`, `2018/`, `2020/` (`geonb_<year>_ped_cep`). ⓘ These are four snapshots of **two** legal generations, not four generations — see Notes.
- **CRS / projection:** **EPSG:2953**, identical `.prj` WKT to the current file, verified on `2020/geonb_2020_ped_cep.prj`. All generations are the same projection, and **none of them carries an `AUTHORITY` clause either** — the code must be hardcoded for every file.
- **Attribute schema:** the schema drifts generation to generation and must be read per file, not assumed.
  - `2020/geonb_2020_ped_cep.dbf` — 7 fields, 49 records: `DIST_ID` N(10), `PED_Name_E` C(50), `PED_Name_F` C(50), `MLA_Names` C(50), `PED_Names_` C(100), `Shape_Leng` F(19,11), `Shape_Area` F(19,11). UTF-8 (`.cpg` present).
  - `2018/geonb_2018_ped_cep.dbf` — 4 fields, 49 records: `DIST_ID` N(10), `PED_Name_E` C(50), `PED_Name_F` C(50), `Shape_Area` F(19,11). UTF-8 (`.cpg` present).
  - `2014/geonb_2014_ped_cep.dbf` — 8 fields, 49 records: `OBJECTID_1` N(9), `OBJECTID` N(9), `DIST_ID` N(9), `PED_Name_E` C(50), `PED_Name_F` C(50), `Shape_Leng`, `Shape_Le_1`, `Shape_Area`. ⚠ **No `.cpg` — this file is cp1252, not UTF-8.** Decoded as UTF-8 the accents mojibake (`Shediac-Beaubassin-Cap-Pel\xe9`).
  - `2010/geonb_2010_ped-cep.dbf` — 8 fields, **55 records**: `PED_NAME_E` C(50), `PED_NAME_F` C(50), `PED_NUM` N(4), `MODIFIED_D` D(8), `SHAPE_LENG`, `PED_BOTH` C(50), `Shape_Le_1`, `Shape_Area`. Different ID field name (`PED_NUM`, not `DIST_ID`) and no `.cpg`.
- **District ID field:** `DIST_ID` 1–49 for 2014/2018/2020; `PED_NUM` 1–55 for 2010.
- **Effective date:** ⚠ ~~2013-11-05~~ → **2014-08-21**. **Corrected on the amendment pass; the earlier value was a consolidation date masquerading as a legal one.** Statutory instrument: **N.B. Reg. 2013-46 (O.C. 2013-208)**, filed 2013-07-05, s. 5: "comes into force on the first dissolution of the Legislative Assembly after June 6, 2013." The 57th Legislature was dissolved **2014-08-21** for the fixed-date 2014-09-22 general election. The discarded 2013-11-05 came from `laws.gnb.ca` displaying N.B. Reg. 2006-27 as "Revoked on 5 November 2013" — which the A2 ruling forced me to test, and which turns out to be the **consolidation cutoff**: Reg. 2006-27's own footer carries the two as separate notes with different values, "came into force on **August 18, 2006**" and "consolidated to **November 5, 2013**". A dissolution in November 2013 never happened; the registry field simply is not a legal date. Corroboration for 2014-08-21: the GeoNB `2014/` snapshot's `.dbf` was last written **2014-08-22**, the day after.
- **Superseded date:** **2024-09-19** → `effective_to`. N.B. Reg. 2023-42 s. 4: "New Brunswick Regulation 2013-46 under the *Electoral Boundaries and Representation Act* is repealed", commencing on the 2024-09-19 dissolution per s. 5. ⓘ `laws.gnb.ca` also shows 2013-46 "Revoked on 19 September 2024", but per the finding above that is the consolidation cutoff and merely *coincides* with the legal date here — treat it as consistent, not as independent confirmation. The independent confirmation is the dissolution of the 60th Legislature on 2024-09-19.
- **District count:** 49 (2014, 2018, 2020) and 55 (2010), each with records == DISTINCT district ID. New Brunswick went 55 → 49 seats at the 2013 redistribution, so the 2010 file is two generations back, not one.
- **Difficulty (1–5):** **1**.
- **Notes:** ★ **Four files, two legal generations.** `2014/`, `2018/` and `2020/` are three snapshots of **N.B. Reg. 2013-46** (in force 2014-08-21 → 2024-09-19). `2010/` is a snapshot of **N.B. Reg. 2006-27** (O.C. 2006-128, filed 2006-04-13, **in force 2006-08-18** per its own footer note → superseded 2014-08-21), the 55-district generation. So NB's full legal chain is 2006-27 → 2013-46 → 2023-42, each commencing on a dissolution rather than on filing. If a third generation is ever loaded for historical lookups, those are the dates.

  ⚠ **The snapshots are not all drawn the same way, and it changes the coastline.** The southernmost record in the 2018, 2020 and 2024 files is **Fundy-The Isles-Saint John Lorneville** (2018/2020: "…-Saint John West") as a **single-part ring reaching y = 7,275,121.5**, which is south of Grand Manan (y ≈ 7,299,983 in EPSG:2953) — i.e. those files draw an **offshore/marine envelope**, so mainland and islands are enclosed in one connected ring. The 2014 file instead is **land-only with separate island parts** — 22 multipart records, up to 32 parts, 331,130 vertices against 2018's 91,159, and a bbox that stops 2.8 km further north. Consequence for the build: within one legal generation, 2014 and 2018/2020 disagree about the coastline and about whether offshore points fall inside a district. Harmless for postcode PIP (postal centroids are on land), but do not treat the four snapshots as interchangeable, and do not compute areas across them.

  ★ **The 2013-46 generation was amended at least five times mid-life** — the consolidated regulation carries amending references `2014-67`, `2016-64`, `2017-28`, `2018-3`, `2018-38` — so "the prior generation" is a moving target and the four dated files are four point-in-time snapshots of it, not four generations. Two districts were *renamed* mid-generation: `DIST_ID 36` Charlotte-Campobello → Saint Croix and `DIST_ID 37` Oromocto-Lincoln → Oromocto-Lincoln-Fredericton (2014 → 2018). At least one was resized: Saint Croix is 3,084.4 km² in the 2018 file and 2,407.8 km² in the 2020 file. **For `effective_to` bookkeeping the correct file is `2020/`** — the last state of the generation before repeal. The `2018/` file is the one that matters for diagnosing what we currently hold. ⚠ `MLA_Names` on the 2020 file (and on ArcGIS layer 0) is a frozen roster snapshot of the 2018–2020 Legislature — it names Gilles Lepage, Denis Landry, Daniel Guitard. It is **not** a roster source; treat it as decoration.

## District ↔ elected official mapping

- **Roster source:** `politicians` / `politician_terms`, already populated for New Brunswick — 49 sitting MLAs of the 61st Legislature. The legislative dossier at [`../new-brunswick.md`](../new-brunswick.md) covers legnb.ca ingestion; nothing new is needed here.
- **Join mechanism:** ✅ **exact string match on the English district name, 49/49, no fallback required.** The authoritative `PED_Names_` value is bilingual with a `" / "` separator where the names differ (`"Restigouche West / Restigouche-Ouest"`) and a single value where they do not (`"Caraquet"`, `"Tantramar"`). Splitting on `" / "` and taking the first half yields the district's legal short name — which is exactly what N.B. Reg. 2023-42 s. 3 uses as the operative name, and exactly what our roster stores. Verified both directions: **zero roster names fail to match an authoritative district, and zero authoritative districts fail to match a roster name.** All 49 matched on the first (English) half; none required the French half.
- ⚠ **The separator is not stable across generations.** The 2024 layer uses `" / "` with surrounding spaces; the prior generation's combined field uses `"/"` with none (`"Restigouche West/Restigouche-Ouest"`). Split on `/` and strip, do not split on the literal `" / "`.
- ⚠ **Five sitting-MLA rows carry HTML entities in `politicians.name`** — `Alexandre C&#xE9;dric Doucet`, `Beno&#xEE;t Bourque`, `Isabelle Th&#xE9;riault`, `Jean-Claude D&#x27;Amours`, `Ren&#xE9; Legacy` — duplicating five correctly-encoded rows, so NB shows **55 active provincial rows for 49 seats**. One of them, `Jean-Claude D&#x27;Amours`, also carries an entity-mangled `constituency_name` (`Edmundston-Vall&#xE9;e-des-Rivi&#xE8;res`), which is the only NB roster string that fails the name join. This is a pre-existing roster defect, not a boundary problem, but it will produce five duplicate reps on any postcode lookup once the boundaries are correct. Raised as a handoff item.
- **Notable:** ★ Elections NB's own public "find my district" tool at `https://www1.gnb.ca/elections/en/provstreetkey/provskinformation-e.asp` resolves a **civic address** to `PhysicalAddressUnit_ID` + `GeographyXCoordinate` / `GeographyYCoordinate` hidden fields and POSTs those to `provresults-e.asp`. The agency is itself geocoding to a point and running point-in-polygon — the same architecture as our lookup. That is independent confirmation that PIP against the authoritative polygon is the correct approach for NB and that no lookup table is being withheld.

## Postal-code correspondence (if published)

⛔ **None. Elections NB publishes no postal-code → district concordance and has no postal-code input anywhere on its public surface** (checked: both street-key lookups, the GeoNB catalogue, the ENB publications index — the lookup is civic-address autocomplete, placeholder "Ex: 123 Main St Fredericton"). No NB equivalent to X1's Elections Québec file; don't re-probe. ⓘ Worth one extra line only because of what it reveals: ENB's own tool resolves the address to `GeographyXCoordinate` / `GeographyYCoordinate` and POSTs the point — **the agency does point-in-polygon, same as us**, which is independent confirmation that an authoritative polygon is the right target and no lookup table is being withheld.

## Alternative distribution points

Probe-hierarchy tier 1 (open-data portal API) exists for New Brunswick after all — I missed it on the first pass and found it on the amendment sweep. It is genuinely better than GeoNB in format, and useless for our actual need.

**★ `gnb.socrata.com` — the New Brunswick open-data portal, Socrata.** Catalogue query: `https://api.us.socrata.com/api/catalog/v1?domains=gnb.socrata.com&q=electoral`. Each provincial electoral-district dataset exposes a **WGS84 GeoJSON export** at `https://gnb.socrata.com/api/geospatial/<id>?method=export&format=GeoJSON`, plus CSV and the original FGDB:

| Generation | Socrata id | GeoJSON |
|---|---|---|
| Provincial 2020 | `c468-yuuy` | ✅ |
| Provincial 2018 | `6ba8-4pp6` | ✅ |
| Provincial 2014 | `5her-qd5j` | ✅ |
| Provincial 2010 | `fisn-z39s` | ✅ |
| **Provincial 2024 (in force)** | — | ⛔ **does not exist** |

⛔ **The portal stops at 2020 and has no dataset for the in-force generation.** The full catalogue for `q=electoral` is 11 results — 2010/2014/2018/2020 provincial (as both `dataset` and `map` types), municipal, local-government, and a federal `href` stub. Nothing for 2024. **So the portal is exactly one generation behind, which is the same failure we are trying to fix, and it cannot be the source of record.** It would have removed reprojection, `.dbf` decoding, cp1252, and the missing-`AUTHORITY` problem in one stroke — worth re-checking at build time in case GNB backfills 2024, but do not plan around it.

**`open.canada.ca`** federates the same records (`package_search?q="Electoral Districts" "New Brunswick"`), attributed to *Government of New Brunswick*, with resources pointing back at `gnb.socrata.com`. Same 2020 ceiling. Its value here is evidentiary, not as a source — see Terms / Licensing.

**`geo.ca`** — not separately probed beyond confirming its search API path has moved; it federates HNAP records from the same provincial catalogue, so it cannot hold a generation the province has not published. Dead end, do not re-probe.

**Elections NB directly** — publishes maps and the commission reports, and points at GeoNB for data. No independent GIS download. `https://www.electionsnb.ca/content/enb/en/maps/provincial-electoral-districts.html` is a `404`; the maps live under the site's "For Maps" navigation as PDFs.

**Statistics Canada** — federal electoral geography and census geography only. No provincial electoral districts for any province. Not applicable, as the brief anticipated.

## Terms / Licensing

✅ **New Brunswick is a Class A jurisdiction. Redistribution is permitted, attribution is the only condition, and there is no flow-down.** The alarm raised against NB in [`overview.md`](./overview.md) § Licence matrix was correct about the *text* Open North carries and wrong about that text still governing. Three documents, in chronological order:

**1. GeoNB License Agreement — 2012-07-04 — SUPERSEDED.** https://geonb.snb.ca/downloads/documents/geonb_license_e.pdf (93,470 bytes, `Last-Modified: Fri, 13 Jul 2012`). This is the document Open North's repository-root `LICENSE.txt` reproduces as its "Section II", and the source of the flow-down. Its § 4.5 verbatim:

> "The Licensee shall license all individuals (or companies) who obtain Data or Derivative Products from the Licensee the right to use the Data or Derivative Products by way of a license agreement, and that agreement shall impose upon these individuals (or companies) the same terms and conditions as those contained in section 4.0 of this Agreement."

It is a click-through agreement — "BY ACCESSING, DOWNLOADING, PRINTING OR USING THE DATA … YOU ARE AGREEING TO BE BOUND BY THE TERMS OF THIS AGREEMENT" — with a one-year auto-renewing term (§ 5), termination on breach, and an obligation on termination to "delete or destroy all Data acquired under this Agreement" (§ 6.3). **Per standing instruction 3 it was read but not accepted, and no file was taken under it.** It is not the licence on any current GeoNB download.

**2. GeoNB Open Data Licence v1.0 — last updated 2015-06-16 — ✅ THIS IS WHAT GOVERNS THE STAGED FILES.** https://geonb.snb.ca/documents/license/geonb-odl_en.pdf. Every archive staged for this dossier ships a `license_licence.txt` naming this document and nothing else, and each `read_me.txt` repeats it under `**LICENSE**`. It is an OGL-shaped grant. Verbatim, the clauses that matter:

> "2. The Information Provider grants you a worldwide, royalty-free, perpetual, non-exclusive licence to use the Information, including for commercial purposes, subject to the terms below."
>
> "3. Copy, modify, publish, translate, adapt, **distribute** or otherwise use the Information in any medium, mode or format for any lawful purpose."
>
> "5. If the Information Provider does not provide a specific attribution statement … you should use the following attribution statement: **“Contains information licenced under the GeoNB Open Data Licence.”**"

**It contains no flow-down, no sublicensing restriction, no term limit, and no termination-on-notice.** Clauses 6–13 are exemptions (personal information, third-party rights, official symbols), non-endorsement, no-warranty, governing law, and definitions. The attribution obligation is phrased "You **should**", not "must" — weaker than the federal OGL. Note the British spelling "licenced" in the required string; reproduce it exactly.

**3. New Brunswick Open Government Licence – Version 2 — ✅ also non-flow-down.** https://www.gnb.ca/en/campaign/geonb/open-government-license.html. This is what the GeoNB *catalogue page* for the provincial electoral datasets cites (alongside "Restriction on use: **Unrestricted**" and "Responsible Agency: Elections New Brunswick"). Self-described as "based on version 2.0 of the Open Government Licence — Canada", with the same free-to-"copy, modify, publish, translate, adapt, distribute" grant, explicit commercial use, and:

> "acknowledge the source of the Information by including any attribution statement specified by the Information Provider(s) and, where possible, provide a link to this licence"
>
> "Contains information licensed under the Open Government Licence – New Brunswick."

Note the *stronger* obligation ("You **must**") and the *different* required string from document 2.

**★ Independent corroboration from outside GeoNB.** The supersession finding does not rest on GeoNB's own pages. `open.canada.ca` carries every New Brunswick electoral-district dataset attributed to *Government of New Brunswick* with `license_id: nb-oglnb`, `license_title: "Open Government Licence - New Brunswick"`, and `license_url: http://www.snb.ca/e/2000/data-E.html` — which resolves to the OGL-NB text, **not** to the 2012 agreement. Three separate publishers of this data (GeoNB's catalogue, the NB Socrata portal, and the federal open-data portal) all state an open licence; **none of them references the 2012 agreement at all.** The only place the flow-down still appears is Open North's repository.

**Does sourcing from GeoNB rather than Open North change our obligations? Yes — decisively, and in our favour.** Open North's `LICENSE.txt` binds *its* recipients to the 2012 agreement because Open North accepted the 2012 agreement when it took the data. We never accepted anything from Service New Brunswick, and the files staged here were served under the 2015 Open Data Licence, which contains no clause of that kind. Replacing the 22 mirrored rows with GeoNB-direct geometry does not *mitigate* the flow-down exposure — it removes the only data we hold that the flow-down could ever have attached to. The compliance question then collapses from "must we bolt a licence-propagation mechanism onto `/api/public/v1/boundaries/*`?" to "which of two attribution strings do we print?"

**ArcGIS service `copyrightText`:** `Elections New Brunswick/Élections Nouveau-Brunswick`.

**Recommended attribution once the operator confirms** — cite both, since the catalogue page and the in-bundle licence file disagree about which applies and both are cheap to satisfy:

> Provincial electoral district boundaries: Elections New Brunswick, published via GeoNB (Service New Brunswick). Contains information licenced under the GeoNB Open Data Licence (https://geonb.snb.ca/documents/license/geonb-odl_en.pdf) and the Open Government Licence – New Brunswick (https://www.gnb.ca/en/campaign/geonb/open-government-license.html).

## Rate limits / auth

- **None encountered.** No API key, no account, no referer check, no rate limiting observed across roughly 30 requests (catalogue pages, ArcGIS `?f=json` metadata, layer queries, HEAD probes across a directory, and four archive downloads) in a ten-minute window. Every URL is anonymous HTTPS.
- **No click-through gate on any file taken.** All four archives and the licence PDF were plain `GET`s against static paths on `geonb.snb.ca`. No form, no checkbox, no account, no terms interstitial. ⓘ For the record: the GeoNB Open Data Licence's clause 1 reads "Use of any Information indicates your acceptance of the terms below" — passive-acceptance wording of the same shape as the federal OGL the Federal agent worked under, not a click-through gate. Flagged in handoff so the operator can confirm they are comfortable with that characterisation.
- `geonb.snb.ca` is fronted by Cloudflare and sets `access-control-allow-origin: *`. `geonb.snb.ca/downloads2/` returns **401** and is not a public path — dead end, do not re-probe.
- **ArcGIS REST:** `https://geonb.snb.ca/arcgis/rest/services/GeoNB_ENB_Provincial_Elections/MapServer`, ArcGIS Server `currentVersion 10.91`. Layer **2** = current districts (2024), layer **0** = prior districts (2018 vintage, `description: "Provincial Electoral Districts 2018"`), layers 1/3/4 = polling divisions. `f=json` and `returnCountOnly` both work unauthenticated. `maxRecordCount` is `UNTESTED — probe during build`; 49 features will fit under any plausible default, but paginate defensively if pulling the 1,753-polygon polling layers.

## Staged files

`data/boundaries/new-brunswick/` — 45.7 MB of the 500 MB budget. Full table with sha256 in
[`PROVENANCE.md`](../../../data/boundaries/new-brunswick/PROVENANCE.md).

| Generation | File | Bytes | What it is |
|---|---|---:|---|
| `current/` | `geonb_2024_ped-cep_shp.zip` | 1,252,663 | ★ **49 in-force districts (N.B. Reg. 2023-42) — the build target** |
| `current/` | `geonb_2024_ped-cep_kmz.zip` | 2,436,011 | same 49 districts, WGS84-native — **reprojection cross-check only**, attributes unusable |
| `current/` | `geonb_2025_ppd_svp_shp.zip` | 5,818,872 | 1,753 polling divisions, 2025 revision |
| `prior/` | `geonb_historic-historique_ped-cep_shp.zip` | 6,206,225 | districts for 2010 (55) / 2014 / 2018 / 2020 (49 each) |
| `prior/` | `geonb_historic-historique_ppd_svp_shp.zip` | 29,641,702 | polling divisions for 2010 / 2014 / 2018 / 2020 / 2024 |
| — | `geonb-odl_en.pdf` | 406,790 | the governing licence, staged as evidence |

Nothing was converted, reprojected, or loaded. The archives are byte-for-byte as served; schema
inspection was done on a copy extracted into the session scratchpad.

⚠ The polling-division bundles are staged only because the GeoNB catalogue's "Electoral districts"
rows link to them rather than to the district files. They are not needed for the district load.
They do carry `PED` / `PED_Names_` / `PED_Names1` district attributes on every poll polygon, so
they are the natural source if poll-level geography is ever wanted — and `Electors_` gives an
elector count per poll.

## Reconciliation with `constituency_boundaries`

**What we hold:** **22 rows**, `level = 'provincial'`, `province_territory = 'NB'`,
`source_set = 'new-brunswick-electoral-districts-2024'`, `constituency_id` prefix
`new-brunswick-electoral-districts-2018/`, all `boundaries_version = 'current'`,
all `effective_from = '2023-01-01'`, all `effective_to = NULL`.

### ★ What the 22 actually are — diagnosed, not estimated

**They are the 22 district *names* that survived unchanged from the 2013-46 generation into the
2023-42 generation.** Not a subset of the 2018 set, not a subset of the 2024 set — the
**intersection of the two**. Verified by set comparison against both authoritative `.dbf` files:
the 2013-46 and 2023-42 generations share exactly 22 district names; our 22 rows are exactly
those 22 names; the difference in both directions is empty.

**★ This is the same fingerprint the BC agent found**, and NB is a second instance of it rather than an independent bug. Two loader paths can produce it, and they are **observationally identical**:

- **(a) no fetch attempted.** `opennorth.py:589` mints `cid = _constituency_id(rep, set_def)` by string-splitting `related.boundary_url` and fetches only when that URL is present. If Represent left `boundary_url` null on the 27 renamed districts, no fetch happened. The comment at `opennorth.py:109` ("Open North doesn't currently populate `boundary_url` on NB reps") points this way, though it is wrong as written — it is populated for 22 of 49.
- **(b) fetch attempted and 404'd, silently.** `_fetch_boundary` (`opennorth.py:502`) retries only on 429/502/503/504 and falls through to a bare `return None` at line 513 on everything else, 404 included — no log, no counter, no raise. If Represent emitted `boundary_url` for all 49 against its 2018 boundary set, the 27 post-2023 names would 404 and vanish without trace. **This is exactly the path the BC agent verified.**

⚠ **I cannot settle which one applies to NB, and I am not going to guess.** Distinguishing them requires reading Represent's NB rep payload, and Represent has been down since at least 2026-08-07 (expired cert, origin 502) per [`overview.md`](./overview.md). What *is* settled is that the 22 `constituency_id`s all carry the `-2018` prefix, so whatever Represent did emit pointed at its **2018** boundary set — the 22 polygons were fetched from the superseded generation under names that happen to survive into the current one.

★ **And the `-2024` label was never Represent's at all — it is ours.** `_upsert_boundary` writes `source_set = set_def.boundary_set`, which is the hardcoded string `"new-brunswick-electoral-districts-2024"` at `opennorth.py:113`. Nothing upstream asserted a 2024 generation; our own config aspirationally named a boundary set that Represent very likely never had, while the IDs recorded what was actually fetched. **`source_set` is the fabrication and `constituency_id` is the honest witness** — which is the reverse of the intuitive reading, and the reason this went unnoticed.

⓵ **The build consequence is identical under (a) and (b), so this does not block anything.** It matters only for the loader post-mortem — and the fix it implies is the same one [`overview.md`](./overview.md) already lists: make loaders fail the run on a missing or rejected boundary rather than logging the row and continuing.

**The geometry is the 2018 vintage of the superseded generation.** Comparing our stored
`area_sqkm` against `Shape_Area` in both authoritative files:

| Compared against | Mean absolute area difference across the 22 |
|---|---:|
| 2013-46 generation (`2020/geonb_2020_ped_cep`) | **1.32%** |
| 2023-42 generation (`geonb_2024_ped_cep`) | **124.87%** |

21 of 22 match the superseded generation to **≤ 0.3%**. The lone outlier, Saint Croix
(ours 3,084.2 km² vs 2,407.8 km² in the 2020 file), matches the **2018** file at 3,084.4 km² —
0.01% — pinning the vintage to 2018 exactly, as the `constituency_id` prefix claimed all along.
Against the in-force geometry the same 22 rows are catastrophically wrong:

| District | Ours (km²) | In force (km²) | Error |
|---|---:|---:|---:|
| Moncton Northwest | 266.9 | 24.4 | **996%** |
| Moncton East | 208.3 | 24.7 | **743%** |
| Miramichi Bay-Neguac | 6,381.4 | 1,310.9 | **387%** |
| Restigouche West | 7,896.7 | 3,495.1 | **126%** |
| Moncton South | 12.6 | 43.4 | **71%** |
| Saint John East | 76.1 | 244.8 | **69%** |

**So the `source_set` label is the only thing about these rows that mentions 2024, and it is the
one thing that is false.** `constituency_id`'s `-2018` prefix, the geometry, and the areas all
agree with each other; `source_set` and `effective_from = '2023-01-01'` are both fabrications —
the latter a hardcoded literal in `_upsert_boundary`, per [`overview.md`](./overview.md).

### Coverage, measured

- **22 of 49 districts** have any polygon; **27 have none**.
- Sum of our 22 areas is **38,767 km²** against New Brunswick's ~72,900 km² — **47% of the province has no provincial boundary at all.**
- The 22 do not overlap each other (checked pairwise, zero intersections above 1 km²) — they are internally consistent, just consistently wrong and mostly absent.
- Spot-checked point-in-polygon at ten town centroids: 9 of 10 return "no match" (Bathurst, Fredericton downtown, Grand Falls, Oromocto, Sackville, Saint John west, Shippagan, Sussex, Woodstock). The tenth, Miramichi city, returns **Miramichi Bay-Neguac** — a district that still exists by name but whose in-force polygon is 21% of the size of the one we tested against. That single row is the "confident wrong riding" case in miniature.
- 30 sitting NB representatives are unreachable by postcode lookup — matches X2's independent measure.

### The roster side

`politician_terms`: **22 of 56** open NB provincial terms carry a `constituency_id` (**39.3%**) —
the same 22 districts, by construction, since both strings came from the same Represent response.
`politicians.constituency_id` is populated for the same 22 and null for the rest.

### ★ Re-key: required, and unusually clean

> ⛔ **Load all 49 as new-generation inserts. Do not treat the 22 matching keys as "already correct" and insert only the 27.**
>
> This is the single most expensive mistake available in New Brunswick, and the 22 keys are precisely the bait for it: they match on name, they match on `constituency_id`, and 21 of them are within 0.3% of *a* real district — just the wrong generation's. Inserting only the 27 gaps would leave every one of the 22 confidently-wrong polygons in place and close the ticket looking green. **The damage here is not 27 absences. It is 27 absences plus 22 wrong answers**, and the 22 are the worse half because nothing in the response signals them.

The authoritative key is `DIST_ID` (1–49), the statutory map number in N.B. Reg. 2023-42.
Nothing we store resembles it — our slugs are Open North kebab-case names under a
`new-brunswick-electoral-districts-2018/` prefix. **A re-key is required for all 49 districts.**

It is, however, about as easy as a re-key gets, because the name join is exact:

1. Split `PED_Names_` on `/`, strip, take the first element → the district's legal short name.
2. Join to `politicians.constituency_name` / `politician_terms.constituency_name`. **49/49, verified, no fuzz, no fallback, no manual mapping table.**
3. Mint `constituency_id` as **`new-brunswick-electoral-districts/<kebab-slug>`** — recommendation (d) in [`overview.md`](./overview.md), now constrained by **ruling A6: no generation marker in the prefix.** ⚠ This supersedes my earlier suggestion of `new-brunswick-electoral-districts-2023-42`, which was wrong: naming it for the regulation instead of the year is *still* encoding a generation, and it fails A6 for the same reason `-2018` does. The uniqueness key is `(constituency_id, boundaries_version)`, so the generation belongs in `boundaries_version` and nowhere else. ★ The target shape already exists in the table — `newfoundland-and-labrador-electoral-districts` is the **only one of our 13 federal/provincial prefixes that is already A6-compliant**; the other 12, NB included, embed a four-digit year. Copy NL's shape.
4. Set `authority = 'elections-new-brunswick'`, `authority_district_id = DIST_ID`.

**One-time re-key cost for New Brunswick: 66 rows**, measured, not estimated:

| Table | Rows carrying the `-2018` prefix |
|---|---:|
| `politicians` | 22 |
| `politician_terms` | 22 |
| `constituency_boundaries` | 22 |
| **Total strings rewritten** | **66** |

Trivially small, and it is a `WHERE constituency_id LIKE 'new-brunswick-electoral-districts-2018/%'` update against a text column with no FK anywhere — the whole NB cutover is three `UPDATE`s and one `INSERT` of 49 rows. ⓘ The `politicians` and `politician_terms` counts are equal and both equal the boundary count because all three strings came from the same Represent response in the same ingest pass; that is the coupling [`overview.md`](./overview.md) warns is unenforced, visible here as a tidy coincidence.

⚠ **`DIST_ID` is not stable across generations, and this is the single most dangerous fact in this
dossier.** 27 of 49 `DIST_ID`s point at a *different district* between the two generations —
`DIST_ID 2` was Campbellton-Dalhousie and is now Restigouche East; `DIST_ID 4` was Bathurst
West-Beresford and is now Bathurst; `DIST_ID 5` was Bathurst East-Nepisiguit-Saint-Isidore and is
now Hautes-Terres-Nepisiguit. A join on `authority_district_id` alone, unscoped by generation,
would silently attach 27 districts' worth of history to the wrong geography. The
`UNIQUE (authority, authority_district_id, boundaries_version)` constraint proposed in
[`overview.md`](./overview.md) is exactly the right shape and New Brunswick is the jurisdiction
that proves why the `boundaries_version` column has to be in it.

### Build notes specific to NB

- **`ST_Transform`, never `ST_SetSRID`.** The geometry is projected metres (bbox `(2306896.8, 7275121.5)–(2713275.2, 7677113.0)`). Labelling it 4326 reproduces the Fort Erie bug exactly, and the `boundary_in_wgs84_bounds` CHECK would then convert it into 49 silently-missing rows because `_ingest_set` swallows the exception per row. Correct form: `ST_Transform(ST_SetSRID(geom, 2953), 4326)`. PostGIS 3.4 reports `USE_PROJ=1`, so this works in-database with no GDAL.
- **Read `.cpg` before decoding any `.dbf`.** 2024 / 2020 / 2018 declare UTF-8; **2014 and 2010 have no `.cpg` and are cp1252**. NB district names carry `é`, `î`, `Î` (`Shippagan-Les-Îles`, `Champdoré-Irishtown`, `Grand Falls-Vallée-des-Rivières-Saint-Quentin`).
- **Field name differs by access path:** `PED_Names_B` via ArcGIS REST, `PED_Names_` in the `.dbf`.
- **Store both language forms.** `PED_Names_` holds `"English / Français"` where they differ. The English half is the legal name and the join key; the French half is real data we currently discard and NB is officially bilingual. Worth a `name_fr` column on `constituency_boundaries` rather than throwing it away — 20 of 49 districts have a distinct French form.
- **Cutover must rename the superseded generation's `boundaries_version` before inserting**, per the [`overview.md`](./overview.md) trap: all 22 existing rows are `'current'` and `ON CONFLICT (constituency_id, boundaries_version) DO UPDATE` would overwrite in place. In NB's case the 22 old `constituency_id`s will not collide with new ones (different prefix), so the risk here is orphaning rather than clobbering — but the four read paths missing `effective_to IS NULL` will double-count if the old rows are left with `effective_to = NULL`.
- **Set the old rows honestly:** `effective_from = '2014-08-21'`, `effective_to = '2024-09-19'` — both legal dates from the statutory triggers, not agency metadata. Do not leave `effective_from = '2023-01-01'` in place; it is wrong by a decade and postdates the geometry's own snapshot by five years.

### Municipal wards — not this dossier

We hold **23 municipal rows across 3 NB sets** (`fredericton-wards` 13, `moncton-wards` 5,
`saint-john-wards` 5, each including one `census-subdivisions/<CSD>` whole-municipality polygon).
A municipal agent covers those. ⓘ One pointer for whoever picks them up: GeoNB publishes
province-wide municipal coverage at
`https://geonb.snb.ca/downloads/mun_electoral_districts/geonb_mred-cerm_shp.zip` (electoral
districts) and `https://geonb.snb.ca/downloads/lg/geonb_lg_gl_wards_quartiers_shp.zip` (wards for
local governments and rural districts), both under the same GeoNB Open Data Licence, both listed
on the catalogue and dated 2026-01-31.

## Research-handoff items

### The three licence decisions, answered

**Q1 — If we obtain the boundaries directly from GeoNB rather than via Open North, does the flow-down obligation still attach?**

**No. It is an artefact of Open North's redistribution grant, not inherent to GeoNB's licence.** The clause is § 4.5 of the *GeoNB License Agreement* dated **2012-07-04** — a click-through contract with a one-year auto-renewing term that Open North entered into in order to obtain the data, and whose terms Open North then passed down to its recipients because § 4.5 obliged it to. GeoNB replaced that contract in 2015 with the **GeoNB Open Data Licence v1.0**, a unilateral open grant with no flow-down, no sublicensing restriction, no term, and no termination clause. Every file staged for this dossier ships that 2015 licence in its own `license_licence.txt` and names it in `read_me.txt`. The province's catalogue and both mirrors cite the equally flow-down-free **OGL-NB v2**. Three independent publishers state an open licence; none references the 2012 agreement.

The practical consequence is stronger than "we may comply differently" — **there is nothing left to comply with on the flow-down axis.** Loading the staged GeoNB geometry and deleting the 22 Open-North-derived rows removes the only data in our database that § 4.5 could ever have attached to. No licence-propagation machinery, no downstream-agreement obligation, no change to the permissive CORS posture.

⚠ **Two honest caveats.** (a) This is a legal characterisation and I am not the right party to make it final; if you want a second opinion, this is the moment. (b) While the flow-down disappears, **an attribution obligation does not** — both live licences require it, and we currently serve NB boundary GeoJSON with no attribution at all. That residual obligation is Q2, and it is the part that is genuinely actionable today. **The decision you are actually being asked for is not "may we serve this" but "do we ship the attribution now or after the re-source".** My recommendation: ship it now, because it is small, it is required under either reading, and it makes the re-source a pure data swap.

**Q2 — What would compliance actually require, concretely?**

Neither licence demands a per-object licence field or a click-through. Both require an attribution statement and, where possible, a link. The minimal honest implementation is **one new file and four small edits, no migration**:

1. **New `services/api/src/lib/boundary-licence.ts`** — a `BOUNDARY_LICENCES: Record<string, { name, url, attribution, source }>` map keyed on `constituency_boundaries.source_set`, plus `boundaryLicence(sourceSet: string)` returning the entry or a conservative default. Start it with the NB entry and the federal one the Federal agent established; other jurisdictions land as each agent's row is settled.
2. **`services/api/src/routes/public/boundaries.ts:381`, `shapeBoundary()`** — add one line, `licence: boundaryLicence(row.source_set)`. ★ This is the whole surface in one edit: `shapeBoundary` is the sole shaping function, `shapeBoundaryWithGeoJson` spreads it, and all three endpoints (list, `lookup`, detail) go through one or the other. Nothing else in the route needs touching.
3. **The three zod response schemas in the same file** — add a nullable `licence` object so the field is documented rather than stripped by the serializer.
4. **`services/api/src/routes/public/index.ts:162`, the `onSend` hook** — add `reply.header("Link", '<https://docs.canadianpoliticaldata.org/developers/licences/>; rel="license"')` beside the three existing CORS headers. One line, applies to every public response, costs nothing.
5. **Docs** — a `mkdocs/docs/developers/licences.md` page listing source, licence name, licence URL and required attribution string per `source_set`, and a sentence in the Swagger plugin description pointing at it.

⚠ **Do not key attribution on `source_set` without reading [`overview.md`](./overview.md) § Known traps first.** `_upsert_boundary` writes `source_set` last-writer-wins for the shared `census-subdivisions` rows, so it is not a stable attribute at municipal level. It is stable and correct for every provincial and federal set including NB, which is what this needs — but a default entry for unmapped sets is mandatory, not optional.

**Q3 — Is there an alternative NB source with cleaner terms?**

**No cleaner terms exist, because the terms are already clean — but there is a better *format*, and it is one generation stale.** Full findings in § Alternative distribution points; the short answer:

- **`gnb.socrata.com`** (the NB open-data portal) serves WGS84 GeoJSON through a documented API under the same OGL-NB — strictly better format, no reprojection, no `.dbf`. ⛔ **But it has no 2024 dataset; it stops at the 2020 generation.** Cannot supply the in-force boundaries. Re-check at build time.
- **`open.canada.ca`** federates the same records with `license_id: nb-oglnb`. Same 2020 ceiling. Useful as licence evidence, not as a source.
- **Elections NB directly** — maps and commission reports only; points at GeoNB for data.
- **`geo.ca`** — federates the same provincial catalogue; cannot hold what the province has not published.
- **StatCan** — federal and census geography only, no provincial electoral districts, as anticipated.

**GeoNB remains the source of record for the in-force generation, and its terms are already Class A.** There is nothing to trade up to.

### Other items

- **Five duplicate NB MLA rows with HTML-entity-encoded names need cleaning before the boundary cutover, not after.** `Alexandre C&#xE9;dric Doucet`, `Beno&#xEE;t Bourque`, `Isabelle Th&#xE9;riault`, `Jean-Claude D&#x27;Amours`, `Ren&#xE9; Legacy` duplicate five correctly-encoded rows, giving 55 active provincial rows for 49 seats. Today they are invisible because 27 districts return nothing anyway. The moment the boundaries are correct, five NB districts start returning two MLAs each. This is roster hygiene, arguably one for the duplicate-politician audit rather than the boundary build, but the boundary cutover is what makes it user-visible. Also `Robert McKee, K.C.` duplicates `Robert McKee` with an honorific — same district, different shape of the same problem.
- **Are you comfortable with the GeoNB ODL's passive-acceptance wording?** Clause 1 reads "Use of any Information indicates your acceptance of the terms below." No form was submitted, no checkbox ticked, no account created — the five archives were plain HTTPS `GET`s on public static paths, the same posture as the federal OGL downloads. I judged this not to be a click-through gate under standing instruction 3, and staged the files. Flagging it so the judgement is yours to ratify rather than mine to assume. **The separate 2012 click-through agreement was read but explicitly not accepted, and no file was taken under it.**
- ✅ **Resolved on the amendment pass, recorded so it is not re-opened:** the prior generation's `effective_from` (was `needs confirmation`, now **2014-08-21** from the statutory trigger) and the attribution-string question, which is now folded into Q1/Q2 above with a recommendation rather than left open.
- **No blockers.** Nothing about New Brunswick is waiting on a human to unlock a download. Every item above is a judgement call or a data-hygiene task; the geometry, the schema, the licence text, the enacting instruments, the legal dates, and the join are all in hand.

## Status

> ⚠ **Reconciled 2026-09-01.** The checkboxes below are the **research phase's** record
> (closed 2026-08-18) and several were overtaken by the build — migrations `0064`–`0121`,
> merged to `main` 2026-08-28. An unticked box here is **not** evidence that something is
> still outstanding.
>
> **Live counts: [`PROGRESS.md`](./PROGRESS.md)** (generated by `boundary-progress`).
> **What actually landed:** the migration headers, which are the accurate record.
> This file's job is the *reasoning* — sources, licences, traps, vintage evidence.

- [x] Current boundaries located and staged (2026-08-18) — 49/49 districts, `geonb_2024_ped-cep_shp.zip`, plus the WGS84 KMZ cross-check
- [x] Prior boundaries located and staged (2026-08-18) — 49/49 for 2014/2018/2020, plus 55 for 2010; standalone per-snapshot URLs recorded
- [x] CRS confirmed — EPSG:2953, **derived from the projection parameters because no `.prj` in the corpus carries an `AUTHORITY` clause**; all eight parameters matched, corroborated by the ArcGIS `latestWkid` and GeoNB's `read_me.txt`
- [x] Attribute schema read from the `.dbf` header of every generation individually (they differ)
- [x] District count verified as **DISTINCT `DIST_ID`, not records** — 49 = 49 in every 49-seat generation, 55 = 55 in 2010; no island-split duplicate rows
- [x] `.cpg` swept case-insensitively — no uppercase variants; 2014 and 2010 ship none and are cp1252
- [x] Effective / superseded dates traced to the statutory instruments per the A2 ruling — Reg. 2023-42 in force **2024-09-19**, Reg. 2013-46 **2014-08-21 → 2024-09-19**, Reg. 2006-27 **2006-08-18 → 2014-08-21**; agency metadata dates recorded and rejected
- [x] ⚠ Prior-generation `effective_from` **corrected** from ~~2013-11-05~~ to **2014-08-21** — the discarded value was `laws.gnb.ca`'s consolidation cutoff, not a legal date
- [x] Licence text obtained verbatim from source (GeoNB ODL v1.0, NB OGL v2, and the superseded 2012 agreement)
- [x] Flow-down question resolved — **the GeoNB § 4.5 flow-down is from a 2012 agreement superseded in 2015 and does not attach to data taken from GeoNB today**; corroborated independently via `open.canada.ca` (`license_id: nb-oglnb`)
- [x] Q1 / Q2 / Q3 licence decisions answered with a concrete minimal implementation (1 new file, 4 edits, no migration)
- [x] District ↔ sitting-MLA name join verified — 49/49 exact, zero residue in either direction
- [x] Diagnosis of the 22 existing rows completed — they are the cross-generation name intersection, carrying 2018-snapshot geometry
- [x] Postal-code correspondence investigated — **confirmed not published by Elections NB** (A3: closed in minutes, not re-probed)
- [x] Alternative distribution points probed — NB Socrata portal + `open.canada.ca` serve WGS84 GeoJSON but **stop at the 2020 generation**; GeoNB remains the source of record
- [x] Wayback CDX sweep completed (A5) — surfaced the unlinked KMZ and the live-but-unlinked `prov_electoral_districts/` directory; dead CDX entries tested against the origin rather than assumed
- [x] Matrix rows written to [`_matrix/new-brunswick.md`](./_matrix/new-brunswick.md) per A1
- [ ] Attribution shipped to `/api/public/v1/boundaries/*` — **recommended now, ahead of the re-source; awaiting operator go-ahead**
- [ ] Supersession reading ratified by the operator — **recommended, not blocking; fallback is equally actionable**
- [ ] Five entity-encoded duplicate MLA rows cleaned — **must precede the cutover**
- [ ] District ID reconciliation executed — re-key of all 49 to `DIST_ID`, deferred to the build phase
