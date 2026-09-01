# Federal — Electoral Boundary Research

> Standalone boundary/roster dossier for the federal jurisdiction. Cross-cutting context
> (methodology, licence matrix, reconciliation strategy) lives in [`overview.md`](./overview.md).
> The legislative-data dossier for this jurisdiction is at [`../federal.md`](../federal.md).

**Agency:** Elections Canada (Electoral Geography Division) | **Website:** https://www.elections.ca | **Districts (current):** 343 | **Current order:** 2023 Representation Orders (SI/2023-57, proclaimed 2023-09-22) | **Next redistribution:** triggered by the 2031 decennial census; commissions strike ~2032, order ~2033

**Status snapshot (2026-08-18):** ✅ **Fully cracked — difficulty 1, and this is the reference implementation.** ★ Elections Canada publishes the authoritative 343-district file under **Open Government Licence – Canada 2.0** with **no click-through, no registration, no account, and no rate limiting** — four independent distribution points all resolve. Both generations staged (33.7 MiB of a 500 MB budget). ★ **The missing 343rd district is `24077` — Ville-Marie—Le Sud-Ouest—Île-des-Soeurs (Montréal, QC)**, confirmed against two independent Elections Canada sources; our other 342 rows are complete and correctly keyed. ★ **The slug half needs no re-key at all** — our `constituency_id` *suffix* is already the Elections Canada `FED_NUM`, 342/342 exact, no extras. ⚠ **Amended 2026-08-18 under ruling A6:** the *prefix* does encode a generation and must change, so the cost is no longer zero — but it is still one mechanical `replace()` over 342 rows. See [Reconciliation](#reconciliation-with-constituency_boundaries). ⚠ Three name strings drift from the authoritative spelling (typographic apostrophes + one stray space). ⚠ The published `.prj` carries **no EPSG authority code** — the build must `ST_SetSRID(geom, 3347)` explicitly before `ST_Transform`. ⛔ **No open postal-code↔FED concordance exists**: StatCan's PCFRF is fee-gated at $892/yr and co-distributed with Canada Post — the single genuine dead end here. ⚠ The district↔MP join is the real federal weakness, not the geometry: only **11 of 1,873** federal `politician_terms` rows carry a `constituency_id` at all.

---

## Current boundaries

- **Source URL(s):** https://ftp.maps.canada.ca/pub/elections_elections/Electoral-districts_Circonscription-electorale/federal_electoral_districts_boundaries_2023/FED_CA_2023_EN-SHP.zip ; https://www.elections.ca/res/cir/mapsCorner/vector/FederalElectoralDistricts_2025_SHP.zip ; https://maps-cartes.services.geo.ca/server_serveur/rest/services/ELECTIONS/FED_Elect2025_en/MapServer/3 ; https://open.canada.ca/data/api/3/action/package_show?id=18bf3ea7-1940-46ec-af52-9ba3f77ed708
- **Format:** ESRI shapefile, zipped (9,388,965 bytes). Also published as FGDB/GDB and KMZ, in English and French, plus an ESRI REST feature service and WMS.
- **CRS / projection:** **EPSG:3347** (NAD83 / Statistics Canada Lambert). Verbatim from `FED_CA_2023_EN.prj`:
  `PROJCS["PCS_Lambert_Conformal_Conic",GEOGCS["GCS_North_American_1983",DATUM["D_North_American_1983",SPHEROID["GRS_1980",6378137.0,298.257222101]],PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]],PROJECTION["Lambert_Conformal_Conic"],PARAMETER["False_Easting",6200000.0],PARAMETER["False_Northing",3000000.0],PARAMETER["Central_Meridian",-91.86666666666666],PARAMETER["Standard_Parallel_1",49.0],PARAMETER["Standard_Parallel_2",77.0],PARAMETER["Latitude_Of_Origin",63.390675],UNIT["Meter",1.0]]`
  ⚠ **The WKT contains no `AUTHORITY["EPSG","3347"]` clause** and the projection is named only `PCS_Lambert_Conformal_Conic`. The EPSG identity is established by the parameter set (false easting 6200000, false northing 3000000, central meridian −91.86666666666666, standard parallels 49/77, latitude of origin 63.390675), not by anything in the file. The `.shp` header bbox is `X 3,658,201..9,019,157 / Y 658,873..6,083,005` — metres, so unambiguously projected. Corroborated by the bundled `Data Dictionary.pdf`: *"Datum: NAD83 CNT / Projection: LAMBERT CONFORMAL / Spheroid: GRS 1980 / Units: METERS"*.
- **Attribute schema:** parsed from the `.dbf` header (encoding `UTF-8`, declared in a **`.CPG` with an uppercase extension** — ⚠ a case-sensitive `*.cpg` glob misses it and silently falls back to latin-1, mojibaking every accented Quebec name):

  | Field | dBase type | Length | Dec | Meaning |
  |---|---|---:|---:|---|
  | `FED_NUM` | `N` (numeric) | 5 | 0 | Elections Canada FED code, e.g. `24077` |
  | `ED_NAMEE` | `C` (character) | 100 | 0 | English district name |
  | `ED_NAMEF` | `C` (character) | 100 | 0 | French district name |
  | `REP_ORDER` | `C` (character) | 4 | 0 | Representation order year — constant `2023` |
  | `SHAPE_AREA` | `F` (float) | 19 | 11 | Area in projected units |
  | `SHAPE_LEN` | `F` (float) | 19 | 11 | Perimeter in projected units |

  ⚠ **Field names differ between the two current-generation files.** `FED_CA_2023_EN` uses `REP_ORDER` / `SHAPE_AREA` / `SHAPE_LEN`; `FED_CA_2025_EN` uses `REPORDER` / `SHAPE_Leng` / `SHAPE_Area` (mixed case). A loader hardcoded to one will fail silently on the other. There is **no province field in any Elections Canada file** — province must be derived from the first two digits of `FED_NUM` (SGC province code), or joined from the StatCan file's `PRUID`.
- **District ID field:** `FED_NUM`. ★ **This is already the slug half of our `constituency_id`** — see Reconciliation. Stable across representation orders in format but **not in meaning**: codes are reassigned between orders, so `FED_NUM` alone is not a cross-generation key; `(FED_NUM, REP_ORDER)` is.
- **Effective date:** **2025-03-23** legally; **2024-04-23** administratively. SI/2023-57 was issued 2023-09-22 and registered 2023-09-27 under the title *"Proclamation Declaring the Representation Orders to be in Force Effective on the First Dissolution of Parliament that Occurs after April 22, 2024"*, its operative clause reading *"declare the representation orders set out in Schedules A and B to be in force, effective on the first dissolution of Parliament that occurs at least seven months after the day on which this Our Proclamation is issued."* Seven months after 2023-09-22 is 2024-04-22; the first dissolution after that date was **2025-03-23** (writs for the 45th General Election, polling day 2025-04-28). Elections Canada's own dataset metadata records `time_period_coverage_start = 2024-04-23`, i.e. the administrative "usable from" date rather than the dissolution. See Research-handoff items — **pick one deliberately.**
- **Superseded date:** n/a (current).
- **District count:** **343**, exactly matching the seat count in the House of Commons. ✅ Verified three ways: 343 distinct `FED_NUM` in `FED_CA_2023_EN.dbf` (343 records, one per district); 343 distinct `FED_NUM` in `FED_CA_2025_EN.dbf` (352 records — see below); and `returnCountOnly` on the geo.ca REST service. The two Elections Canada files agree on **all 343 codes and all 343 English names with zero differences**.
- **Difficulty (1–5):** **1** — documented CKAN API, documented ESRI REST service, direct HTTPS download, open licence, published data dictionary.
- **Notes:**
  - ⚠ **`FederalElectoralDistricts_2025_SHP.zip` has 352 records for 343 districts.** Six districts are stored as multiple separate records rather than one multipart geometry: `12006` Halifax (×2), `24021` Côte-Nord—Kawawachikamach—Nitassinan (×3), `24024` Gaspésie—Les Îles-de-la-Madeleine—Listuguj (×2), `46001` Brandon—Souris (×2), `46009` Selkirk—Interlake—Eastman (×4), `59009` Courtenay—Alberni (×2). A loader that does one INSERT per record produces 352 rows and six duplicate `constituency_id`s. **`FED_CA_2023_EN-SHP.zip` does not have this problem** — one record per district — which is why it is the recommended file. If the 45th-GE file is used anyway, `GROUP BY FED_NUM` and `ST_Union` first.
  - ★ **A reprojection-free path exists.** The geo.ca ESRI REST layer accepts `outSR=4326&f=geojson`, supports pagination, and reports `maxRecordCount=50000` against 352 features — so one request returns the whole layer already in WGS84. Fields exposed: `OBJECTID`, `FED_NUM`, `ED_NAMEE`, `ED_NAMEF`, `REPORDER`. Useful as a build-phase fallback if pure-Python `.shp` parsing proves annoying, and useful right now as an independent verification oracle. Confirmed working:
    `https://maps-cartes.services.geo.ca/server_serveur/rest/services/ELECTIONS/FED_Elect2025_en/MapServer/3/query?where=FED_NUM%3D24077&outFields=*&outSR=4326&f=geojson`
  - The shapefile geometry type is `5` (Polygon), not PolygonZ/M — no coordinate-dimension surprises.
  - Elections Canada's internal feature class is `NGD_FED_A_343`, and the shipped `.shp.xml` lineage shows the fields `FED_TYPE`, `ED_ID`, `ELCT_CNT`, `ED_CHNG_TYP` were **deleted before publication**. `ED_ID` is a stable internal long integer and `ED_CHNG_TYP` records how each district changed between orders — both would be genuinely useful and neither is published. Noted for the handoff, not blocking.

## Prior boundaries (immediately preceding)

- **Source URL(s):** https://ftp.maps.canada.ca/pub/elections_elections/Electoral-districts_Circonscription-electorale/Elections_Canada_2021/FED_CA_2021_EN.zip ; https://www12.statcan.gc.ca/census-recensement/2011/geo/bound-limit/files-fichiers/2016/lfed000a16a_e.zip ; https://open.canada.ca/data/api/3/action/package_show?id=47a0f098-7445-41bb-a147-41686b692887
- **Format:** ESRI shapefile, zipped. Elections Canada `FED_CA_2021_EN.zip` = 9,790,556 bytes; Statistics Canada `lfed000a16a_e.zip` = 5,845,230 bytes. StatCan also offers GML and MapInfo.
- **CRS / projection:** **EPSG:3347**, identical WKT to the current generation — byte-for-byte the same `PROJCS` string in all four staged files, and all four `.shp` headers report the identical national bbox `X 3,658,201..9,019,157 / Y 658,873..6,083,005`. ✅ No cross-generation reprojection difference to handle.
- **Attribute schema:**
  - Elections Canada `FED_CA_2021_EN.dbf` (encoding `UTF-8`, 347 records): `OBJECTID` `N`(10,0); `FED_NUM` `N`(10,0); `ED_NAMEE` `C`(100); `ED_NAMEF` `C`(100); `SHAPE_Leng` `F`(19,11); `SHAPE_Area` `F`(19,11); `REPORDER` `C`(8) — constant `2013`.
  - Statistics Canada `lfed000a16a_e.dbf` (338 records): `FEDUID` `C`(5); `FEDNAME` `C`(200); `FEDENAME` `C`(100); `FEDFNAME` `C`(100); **`PRUID` `C`(2)**; **`PRNAME` `C`(100)**.
- **District ID field:** `FED_NUM` (Elections Canada) / `FEDUID` (Statistics Canada) — the same Elections Canada FED code in both, zero-padded 5-character. ⚠ **Codes are reused across orders with different meanings**, so prior-generation rows must be distinguished from current ones by `boundaries_version` / `effective_*`, never by code alone.
- **Effective date:** **2015-08-02** — the dissolution of the 41st Parliament, which issued the writs for the 42nd General Election. SI/2013-102, *"Proclamation Declaring the Representation Order to be in Force Effective on the First Dissolution of Parliament that Occurs after May 1, 2014"*, was proclaimed 2013-10-01; the first dissolution after 2014-05-01 was 2015-08-02.
- **Superseded date:** **2025-03-23** (or **2024-04-22** on the administrative reading) — the mirror of the current generation's effective date. The 2013 Order governed the 42nd, 43rd and 44th General Elections.
- **District count:** **338**, matching the pre-2025 seat count. ✅ Verified: StatCan file has exactly 338 records and 338 distinct `FEDUID`, no multipart. The Elections Canada file has 347 records for 338 districts (multipart, same trap as the 45th-GE file).
- **Difficulty (1–5):** **1**.
- **Notes:**
  - **Recommended file: `FED_CA_2021_EN.zip`** (Elections Canada) for legal authority — it is the boundary-drawing agency's own artifact and carries `REPORDER='2013'` explicitly. **Keep the StatCan file as the reconciliation aid**: it is 1:1 (no multipart `GROUP BY` needed) and it is the *only* staged file carrying province attributes (`PRUID` / `PRNAME`).
  - ⚠ **Em-dash convention differs between the two prior-generation sources.** StatCan writes district names with a double ASCII hyphen — `Pierrefonds--Dollard` — where Elections Canada uses a true em-dash `—`. Any name-based join across these two files needs normalisation. (The current-generation files both use the em-dash.)
  - ⚠ **Trap: StatCan serves a 200-status error page for wrong-vintage paths.** `…/bound-limit/files-fichiers/2021/lfed000a21a_e.zip` returns **HTTP 200 with a 4,099-byte error body**, not a 404. The real 2021-census path is under `…/census-recensement/2021/geo/sip-pis/boundary-limites/files-fichiers/`. Compare `Content-Length`, not status codes, when probing StatCan.

## District ↔ elected official mapping

- **Source URL(s):** https://www.ourcommons.ca/members/en/search/xml ; https://www.elections.ca/content.aspx?section=res&dir=cir/list&document=index338&lang=e
- **Format:** XML, 158,429 bytes, served as `application/xml; charset=utf-8`. No auth, no rate limiting observed, no WAF.
- **Fields per member:** `PersonId` (stable House of Commons integer, e.g. `89156`), `PersonShortHonorific`, `PersonOfficialFirstName`, `PersonOfficialLastName`, `ConstituencyName`, `ConstituencyProvinceTerritoryName`, `CaucusShortName` (party), `FromDateTime`, `ToDateTime` (nil while sitting).
- **★ Join quality — measured, not assumed.** The export holds **338 sitting MPs** (343 seats less 5 vacancies). Joining `ConstituencyName` against the authoritative `ED_NAMEE`:

  | Match stage | Count | % of 338 |
  |---|---:|---:|
  | Exact string match | 336 | 99.4% |
  | + apostrophe/whitespace normalisation | 2 | 0.6% |
  | **Still unmatched** | **0** | **0%** |

  The two needing normalisation are `Mégantic—L'Érable—Lotbinière` and `Mont-Saint-Bruno—L'Acadie`: the House of Commons writes ASCII `'` (U+0027) where Elections Canada writes typographic `’` (U+2019). ✅ **A name join resolves 338/338 to a `FED_NUM`** — so the House of Commons roster is a viable bridge to the authoritative district code.
- **⚠ The export publishes no FED code.** `ConstituencyName` + `ConstituencyProvinceTerritoryName` are the only geographic keys; there is no numeric district identifier anywhere in the payload. The name join above is therefore the *only* available bridge, and it is one renamed district away from breaking. `PersonId` is stable and useful as a `politicians` ID column in its own right (no such column exists today — cf. CLAUDE.md convention #1).
- **Vacant seats (2026-08-18), 5 of 343:** `24018` Chicoutimi—Le Fjord; `24066` Saint-Hyacinthe—Bagot—Acton; `35007` Beaches—East York; `35095` Scarborough North; `59022` North Vancouver—Capilano. Expect these to have a boundary and no representative — that is correct, not a gap.
- **Difficulty (1–5):** **1**.
- **Notes:** Elections Canada's district list pages (`document=index338` for the 2013 Order, and the 2023 equivalent) pair FED codes with names and are a useful independent cross-check on the name spellings, but they are candidate/geography references rather than a sitting-member roster — `ourcommons.ca` is the roster authority.

## Postal-code correspondence (if published)

⛔ **No open-licence postal-code ↔ FED concordance exists.** This is the one genuine dead end in the federal jurisdiction, and it is a hard one.

- **Statistics Canada — Postal Codes<sup>OM</sup> by Federal Ridings File (PCFRF), catalogue 92-178-X.** https://www150.statcan.gc.ca/n1/en/catalogue/92-178-X — this is exactly the product we would want: it links six-character postal codes to FEDs with a `weight` variable estimating the share of a postal code's population in each district (the last edition linked 848,354 active postal codes to the 338 districts of the 2013 Order). ⛔ **It is not open.** The last issue was released 2017-12-13, and since February 2018 distribution is shared between Statistics Canada and Canada Post Corporation, gated behind an **initial annual licensing administration fee of $892** plus the Data Liberation Initiative. **No agent action taken** — no form submitted, no licence accepted, per standing instruction 3.
- **⛔ No 2023-Order edition appears to exist at all.** The PCFRF's last issue is keyed to the 2013 Representation Order. Even paying the fee would not currently buy a concordance for the 343 districts we need.
- **Elections Canada — Voter Information Service.** https://www.elections.ca/scripts/vis/FindED?L=e&PAGEID=20 — an interactive per-postal-code lookup. Authoritative, free, and **not a bulk file**; scraping 850k postal codes out of it would be an abusive use of a public service and is not proposed.
- **Elections Canada publishes no FED-specific concordance of its own.** Checked the Maps Corner vector listing, the CKAN dataset resources for all three Elections Canada boundary datasets, and the redistribution site. Nothing. Recording this explicitly so nobody re-probes it.
- **✅ The good news: we do not need one.** Our lookup is already point-in-polygon, not table-lookup — `resolvePostcode()` geocodes to a point and `lookupBoundariesAtPoint()` does the PIP. Authoritative *polygons* are a complete substitute for a postal concordance, and they are strictly better: a concordance apportions by weight where a postal code straddles a boundary, whereas PIP against the real polygon is exact for a given point. **The federal postal question reduces entirely to the geocoding question**, which is Agent X1's brief, not this one.

## Terms / Licensing

**Licence: Open Government Licence – Canada, version 2.0** (`ca-ogl-lgo`). https://open.canada.ca/en/open-government-licence-canada

Confirmed as the licence on all four staged files, via the CKAN `license_id` field of all three Elections Canada datasets and both Statistics Canada datasets. ✅ **No click-through, no licence acceptance, no registration, no account, no form.** Files are plain HTTPS `GET` from `ftp.maps.canada.ca`, `www.elections.ca` and `www12.statcan.gc.ca`.

Rights granted, verbatim:

> "The Information Provider grants you a worldwide, royalty-free, perpetual, non-exclusive licence to use the Information, including for commercial purposes, subject to the terms below."

Redistribution, verbatim:

> "Copy, modify, publish, translate, adapt, distribute or otherwise use the Information in any medium, mode or format for any lawful purpose."

Attribution requirement, verbatim:

> "Acknowledge the source of the Information by including any attribution statement specified by the Information Provider(s) and, where possible, provide a link to this licence."

and the required acknowledgement string, verbatim:

> "Contains information licensed under the Open Government Licence – Canada."

**Information-provider attribution.** The geo.ca REST service declares its own `copyrightText`, verbatim: *"Government of Canada; Elections Canada; Electoral Geography Division"*. That is the attribution statement specified by the provider, so the OGL clause above requires carrying it.

★ **Assessment: fully cleared for both internal use and redistribution**, including through `/api/public/v1/boundaries/*`. Federal is **Class A** in the overview's licence taxonomy — a named open licence that transfers on its own terms. Unlike the Class B "distributed with permission" provincial sets, nothing here depends on a permission granted to Open North. The only obligation is attribution, and it is satisfied by one static string on the boundary endpoints and the dataset pages.

**Licence-matrix row** (for [`overview.md`](./overview.md) § Licence matrix):

| Jurisdiction | Authority | Licence name | Licence URL | Our use? | Our redistribution? | Attribution string | Verified |
|---|---|---|---|---|---|---|---|
| Federal | Elections Canada | Open Government Licence – Canada 2.0 | https://open.canada.ca/en/open-government-licence-canada | ✅ yes | ✅ yes | "Contains information licensed under the Open Government Licence – Canada." + "Government of Canada; Elections Canada; Electoral Geography Division" | 2026-08-18 |

## Rate limits / auth

- **Authentication:** none, on any surface. No API key, no account, no session, no referer check.
- **Rate limiting:** none observed. Roughly 25 requests were issued across `open.canada.ca`, `www.elections.ca`, `ftp.maps.canada.ca`, `www12.statcan.gc.ca` and `maps-cartes.services.geo.ca` during this research pass — HEAD probes, four full file downloads, and CKAN/REST queries — with **zero 429s, zero throttling, and zero challenge pages**. No WAF signature on any host.
- **`open.canada.ca` CKAN API:** fully open, documented, CKAN 3 action API. `package_show?id=<uuid>` and `package_search?q=…` both work unauthenticated. This is the recommended discovery surface — it is where all four staged files were found, and it carries the licence identifier as structured metadata.
- **geo.ca ESRI REST:** open, `maxRecordCount=50000`, `supportsPagination=true`, `supportedQueryFormats: JSON, geoJSON`, service SR `EPSG:3978` with arbitrary `outSR` supported.
- ⚠ **`www.elections.ca` `content.aspx` pages are flaky for automated fetches** — one representation-order page returned HTTP 500 on a first fetch and others rendered as navigation stubs. The *file* endpoints under `/res/cir/mapsCorner/vector/` were rock-solid throughout. Prefer CKAN and the FTP host over scraping `content.aspx`.
- ⚠ **Trap: `ourcommons.ca/members/en/search/xml` answers `HEAD` with a 302 that resolves to a 404, while `GET` returns 200 and 158 KB of valid XML.** Verified both ways. A HEAD-first liveness probe — the pattern used everywhere else in this pass to check sizes before downloading — reports this endpoint as dead when it is perfectly healthy. Probe it with `GET`.
- **Caching:** all file endpoints return `Last-Modified` (current-generation files: `Tue, 25 Nov 2025 18:00:44 GMT`) and honour `HEAD` with accurate `Content-Length`. ✅ Per CLAUDE.md convention #6 the refresh check is a cheap conditional `HEAD`; there is no reason to ever re-download blind.
- **Instruction-source boundary:** no page fetched during this pass contained text addressed to an AI agent. Nothing to report under standing instruction 8.

## Staged files

Staging root `data/boundaries/federal/`; full audit table with sha256 in [`PROVENANCE.md`](../../../data/boundaries/federal/PROVENANCE.md) (gitignored directory, committed provenance file). **33.7 MiB total against a 500 MB budget.**

| Path | Bytes | Records | Districts | Role |
|---|---:|---:|---:|---|
| `current/FED_CA_2023_EN-SHP.zip` | 9,388,965 | 343 | 343 | ★ **recommended** — current generation |
| `current/FederalElectoralDistricts_2025_SHP.zip` | 10,301,648 | 352 | 343 | cross-check (45th GE snapshot; multipart) |
| `prior/FED_CA_2021_EN.zip` | 9,790,556 | 347 | 338 | ★ **recommended** — prior generation |
| `prior/lfed000a16a_e.zip` | 5,845,230 | 338 | 338 | cross-check (StatCan; 1:1, has `PRUID`) |

**Deliberately not staged:** `PollingDivisionBoundaries_2025_SHP.zip` (95,154,203 bytes) and `AdvancePollingDistrictBoundaries_2025_SHP.zip` (42,382,982 bytes) — polling geography, a possible future layer, out of scope for `constituency_boundaries`. Both are within budget and one `curl` away whenever that layer is wanted; URLs are in `PROVENANCE.md`. Also skipped: the StatCan **cartographic** variants, for the reason in the next note.

★ **Cartographic vs digital — and why it does *not* answer the `boundary_simple` question.** Statistics Canada publishes both, described verbatim in its own metadata: *"Cartographic boundary files portray the geographic areas using only the major land mass of Canada and its coastal islands. Digital boundary files portray the full extent of the geographic areas, including the coastal water area."* The distinction is **extent, not resolution** — and the file sizes prove it, because the cartographic file is the *larger* of the two (2016: digital 5.8 MB vs cartographic 32.8 MB; 2021: digital 10.9 MB vs cartographic **139.4 MB**), since following the real coastline costs far more vertices than cutting straight across water. ⚠ **So the cartographic file is not a pre-generalised variant and must not be loaded into `boundary_simple`.** Neither agency publishes a generalised FED product at all; `boundary_simple` still has to come from `ST_SimplifyPreserveTopology` at build time. Elections Canada publishes only the digital-equivalent full extent, which is the correct choice for `boundary` regardless.

## Reconciliation with `constituency_boundaries`

**What we hold** (read-only query against `sw-db`, 2026-08-18):

- `source_set = 'federal-electoral-districts'` — **342 rows**, `level = 'federal'`, one `source_set`, one `constituency_id` prefix.
- `constituency_id` prefix: `federal-electoral-districts-2023-representation-order/`, slug = the bare numeric Elections Canada FED code (`…/35079`, `…/11003`).
- `province_territory` is **NULL on all 342 rows**; `effective_from = '2023-01-01'` and `effective_to = NULL` on all 342 (the hardcoded literals from `services/scanner/src/opennorth.py`, not a legal date).

**★ The slug half already matches the authority exactly.** Comparing our 342 slugs against the 343 authoritative `FED_NUM` values:

| Check | Result |
|---|---|
| Authoritative districts | 343 |
| Our rows | 342 |
| Slugs matching a `FED_NUM` exactly | **342 / 342 (100%)** |
| Rows in our table with **no** authoritative counterpart | **0** |
| Authoritative districts absent from our table | **1** |

✅ This confirms the overview's ★ claim that the federal slugs are already the authoritative government ID.

> ~~Federal needs **one INSERT**, not a migration.~~
>
> ⚠ **Superseded 2026-08-18 by ruling A6** (`constituency_id` prefixes must not encode a generation).
> The finding above is unaffected — the **suffix** is the authoritative `FED_NUM` and still needs no
> re-key. But our **prefix**, `federal-electoral-districts-2023-representation-order`, bakes a
> representation order into a column whose unique key is `(constituency_id, boundaries_version)`, so
> the generation is recorded twice and every future redistribution would force a full `politicians`
> rewrite. Federal's cost is therefore **not zero**, but it is still small and entirely mechanical.

**★ A6 target prefix: `federal-electoral-districts`** (drop `-2023-representation-order`; the generation
moves to `boundaries_version`). The suffix is untouched, so this is a pure prefix substitution:

| Table | Rows carrying the old prefix | Change |
|---|---:|---|
| `politicians` | **342** (all active) | `UPDATE … SET constituency_id = replace(constituency_id, 'federal-electoral-districts-2023-representation-order/', 'federal-electoral-districts/')` |
| `politician_terms` | **11** | same `replace()` |
| `constituency_boundaries` | **342** | same `replace()`, plus `boundaries_version = '2023-representation-order'` |

**Total federal cost: 695 mechanical row-updates + 1 INSERT (`24077`) + the `authority` backfill.** No
value is computed, looked up, or inferred — every new string is a substring substitution on an existing
one, so the migration is trivially reversible with the inverse `replace()`. The
`authority_district_id = split_part(constituency_id, '/', 2)` backfill is **unaffected**: `split_part`
on `/` returns the same `FED_NUM` before or after the prefix change.

**★ The missing district is `24077` — Ville-Marie—Le Sud-Ouest—Île-des-Soeurs** (Montréal, Quebec). Confirmed independently from `FED_CA_2023_EN.dbf`, from `FED_CA_2025_EN.dbf`, and from a live geo.ca REST query. Its neighbours `24076` Vaudreuil and `24078` Vimy are both present, so this is a single dropped row in the original Open North mirror, not a range gap. Quebec is the only province short: we hold 77 of its 78 seats and the full authoritative count for all twelve other jurisdictions (NL 7, PE 4, NS 11, NB 10, ON 122, MB 14, SK 14, AB 37, BC 43, YT 1, NT 1, NU 1).

⚠ **Three name strings need correcting on rows we already hold** (ours → authoritative):

| `FED_NUM` | Ours | Authoritative | Difference |
|---|---|---|---|
| `24020` | `Côte-du-Sud—Rivière-du-Loup— Kataskomiq—Témiscouata` | `Côte-du-Sud—Rivière-du-Loup—Kataskomiq—Témiscouata` | stray space after the second em-dash |
| `24046` | `Mégantic—L'Érable—Lotbinière` | `Mégantic—L’Érable—Lotbinière` | ASCII `'` vs typographic `’` |
| `24049` | `Mont-Saint-Bruno—L'Acadie` | `Mont-Saint-Bruno—L’Acadie` | ASCII `'` vs typographic `’` |

The apostrophe variants are the same two districts where `ourcommons.ca` also writes ASCII — so the ASCII form is what roster sources emit and the typographic form is what Elections Canada emits. **Normalise on join; do not assume either side is canonical.** Cosmetic for PIP (which never touches the name), load-bearing for the `lower(constituency_name)` fallback path.

**For the overview's recommendation (d) — authority columns:**

- `authority` = `elections-canada`
- `authority_district_id` = the `FED_NUM` string, which is byte-identical to our existing slug
- The backfill for all 342 federal rows is therefore `authority_district_id = split_part(constituency_id, '/', 2)` with no lookup and no risk. ✅ **Unaffected by the A6 prefix change** — `split_part` on `/` returns the same `FED_NUM` whichever prefix precedes it, so the two migrations are order-independent and can be applied in either sequence.
- ★ **After the A6 change, the prior generation shares the same `constituency_id` values as the current one** wherever a FED code is reused — which is exactly the intent: one generation-independent string per district, with `boundaries_version` separating the 338 from the 343. This is also why the `UNIQUE` constraint below is load-bearing rather than defensive.
- ⚠ `authority_district_id` must be qualified by generation before the prior-generation rows load: FED codes are reused across representation orders, so `UNIQUE (authority, authority_district_id, boundaries_version)` — the constraint the overview already proposes — is exactly right and is **load-bearing, not defensive**, the moment the 338 prior rows land.

**Proposed temporal values:**

Both generations share the prefix `federal-electoral-districts/` per ruling A6; the generation lives
entirely in `boundaries_version` and the `effective_*` pair.

| Generation | `constituency_id` | `boundaries_version` | `effective_from` | `effective_to` | Rows |
|---|---|---|---|---|---|
| 2023 Representation Orders | `federal-electoral-districts/<FED_NUM>` | `2023-representation-order` | `2025-03-23` | `NULL` | 343 |
| 2013 Representation Order | `federal-electoral-districts/<FED_NUM>` | `2013-representation-order` | `2015-08-02` | `2025-03-23` | 338 |

(Using the legal dissolution reading; substitute `2024-04-23` / `2024-04-22` throughout if the administrative reading is chosen — see the handoff item.)

⚠ **`province_territory` should be backfilled at the same time.** It is NULL on all 342 rows today, there is a `idx_boundaries_province` index sitting unused because of it, and the value is a pure function of the key: `FED_NUM[0:2]` → `10`=NL, `11`=PE, `12`=NS, `13`=NB, `24`=QC, `35`=ON, `46`=MB, `47`=SK, `48`=AB, `59`=BC, `60`=YT, `61`=NT, `62`=NU. Verified: those thirteen prefixes account for all 343 authoritative codes and all 342 of ours. No inference, no fuzzy matching.

⚠ **The district↔official gap is much larger than the boundary gap, and fixing the boundary does not fix it.** Of 1,873 federal `politician_terms` rows, **11 carry a `constituency_id`** (0.59%); of 352 rows with `ended_at IS NULL`, **11**. Adding `24077` closes the geometry gap completely and still leaves essentially every MP unjoined to a riding on the terms table. The join works today only via `politicians.constituency_id`, which is where the overview notes the federal load actually sits. **Loading the 343rd polygon is necessary but not sufficient** — the roster side needs the `ourcommons.ca` name join documented above.

⚠ Separately: 352 federal `politician_terms` rows are open (`ended_at IS NULL`) against 343 seats and 338 sitting MPs. That surplus is a roster data-quality issue outside this dossier's scope; flagged so it is not mistaken for a boundary problem.

**Senate — ✅ confirmed correct, not a gap.** All **97** rows with `office = 'Senator'` have `constituency_id IS NULL`, and that is right: senators are appointed to represent a province or territory (and, in Quebec, a senatorial division), never a federal electoral district. There is no boundary to attach and none should ever be attached. The overview's count of "104 active politicians with no `constituency_name` either, predominantly senators" is consistent with this. **Do not treat the 97 NULLs as missing data and do not attempt to fill them from the FED layer.** If per-province senator representation is ever wanted in the postcode lookup, the correct join is province, not district — a different code path.

## Research-handoff items

- **Which effective date do we adopt — the legal one or the administrative one?** The 2023 Orders legally came into force at the first dissolution of Parliament after 2024-04-22, which was **2025-03-23**; Elections Canada's own dataset metadata instead records **2024-04-23** as the coverage start, meaning "usable for any election called from this date." Both are defensible and the difference is 11 months. It matters concretely: an `effective_from` of 2025-03-23 means a historical query dated, say, 2024-09-01 returns the *2013* boundaries — which is legally correct, because a by-election held that day would have used them. **Recommendation: use the legal dissolution dates (2015-08-02 and 2025-03-23), because they make the temporal model answer "which riding was this address in on date X" correctly.** Needs a one-line decision before the first cutover, and the same question will recur for every province, so it belongs in `overview.md` once settled.
- **Should we add `politicians.ourcommons_person_id`?** The House of Commons XML publishes a stable integer `PersonId` per member. CLAUDE.md convention #1 says find and persist the canonical member ID first, and federal currently has only `openparliament_slug` — a third-party slug, where `PersonId` is the legislature's own. This is the federal analogue of `ola_member_id` / `lims_member_id`. Cheap to add, and it is the durable half of the district↔MP bridge whose other half is a fragile name match.
- **Do we want the polling-division layer?** Elections Canada publishes polling divisions (95 MB) and advance polling districts (42 MB) under the same OGL, from the same directory, with the same CRS and schema conventions. Both are within budget and were left unstaged as out of scope. They would enable sub-riding analysis and poll-level results joins against the existing `Poll-by-Poll Results` datasets. **Not staged — say the word.**
- **⚠ `.gitignore` silently swallows every `PROVENANCE.md` in this workstream — affects all ~24 agents, not just federal.** Lines 97–98 read `data/boundaries/` then `!data/boundaries/**/PROVENANCE.md`. The negation cannot fire: git does not descend into an excluded directory, so a re-include below it is unreachable. Verified with `git check-ignore -v data/boundaries/federal/PROVENANCE.md` → matches line 97, ignored. **The entire committed audit trail for this project is currently uncommittable.** Verified fix, tested in a throwaway repo (keeps every data file ignored, makes only `PROVENANCE.md` trackable):
  ```gitignore
  data/boundaries/**
  !data/boundaries/**/
  !data/boundaries/**/PROVENANCE.md
  ```
  Not applied — `.gitignore` is shared across every agent in this run and this is the team lead's call, not a per-jurisdiction edit.
- **⚠ Amendment note (2026-08-18): this dossier's original "re-key cost is zero" claim was half right, and the correction is recorded rather than overwritten.** Ruling A6 established that a `constituency_id` prefix must not encode a generation. The suffix finding survives intact and is still the strongest result here — our slug *is* the `FED_NUM`, 342/342. The prefix does not: `federal-electoral-districts-2023-representation-order` records the generation a second time, redundantly with `boundaries_version`, and would force a full `politicians` rewrite at every future redistribution. Corrected in [Reconciliation](#reconciliation-with-constituency_boundaries) with the row counts; the superseded sentence is struck through in place. **Federal is the reference implementation, so anyone modelling on this dossier should take the amended form.**
- **⛔ PCFRF is fee-gated and no agent should probe further.** $892/yr initial licensing administration fee, co-distributed with Canada Post, last issue keyed to the superseded 2013 Order. Recorded here so the postal-geocoding agent does not spend budget rediscovering it. **No form was submitted and no licence accepted.** The federal postal problem is fully absorbed by point-in-polygon against the staged polygons plus whatever geocoder Agent X1 lands on; there is nothing to buy that would help.
- **Elections Canada suppresses two useful fields at publication** — `ED_ID` (stable internal long integer, generation-independent) and `ED_CHNG_TYP` (how each district changed between orders). Both are visible in the shipped `.shp.xml` lineage as fields deleted before release. `geo.services@elections.ca` is the published Electoral Geography Division contact. **No contact was made** (standing instruction). If the operator ever wants a genuinely generation-stable federal district key, or a machine-readable 338→343 crosswalk for historical speech/vote attribution, that is the one email worth sending. Low priority — everything currently planned works without it.

## Status

> ⚠ **Reconciled 2026-09-01.** The checkboxes below are the **research phase's** record
> (closed 2026-08-18) and several were overtaken by the build — migrations `0064`–`0121`,
> merged to `main` 2026-08-28. An unticked box here is **not** evidence that something is
> still outstanding.
>
> **Live counts: [`PROGRESS.md`](./PROGRESS.md)** (generated by `boundary-progress`).
> **What actually landed:** the migration headers, which are the accurate record.
> This file's job is the *reasoning* — sources, licences, traps, vintage evidence.

- [x] Current boundaries located and staged (2026-08-18) — `FED_CA_2023_EN-SHP.zip`, 343/343 districts
- [x] Prior boundaries located and staged (2026-08-18) — `FED_CA_2021_EN.zip`, 338/338 districts
- [x] Second independent source staged for each generation as a cross-check
- [x] Licence cleared for internal use **and** redistribution — OGL–Canada 2.0, no click-through
- [x] CRS confirmed — EPSG:3347, verbatim WKT recorded, ⚠ no EPSG authority code in the `.prj`
- [x] Attribute schema parsed from the `.dbf` header for all four files
- [x] District ID reconciliation confirmed — 342/342 exact on the **suffix**, no suffix re-key required
- [ ] ⚠ **A6 prefix change pending** — `federal-electoral-districts-2023-representation-order` → `federal-electoral-districts`; 695 mechanical row-updates across three tables (amended 2026-08-18)
- [x] Missing district identified — **`24077` Ville-Marie—Le Sud-Ouest—Île-des-Soeurs**
- [x] District ↔ elected official source located and join quality measured — 338/338 after normalisation
- [x] Senate `constituency_id IS NULL` confirmed correct for all 97 rows — not a gap
- [x] Postal-code correspondence investigated — ⛔ **none open; PCFRF fee-gated, dead end recorded**
- [ ] `effective_from` semantics decided (legal 2025-03-23 vs administrative 2024-04-23) — **handoff item, blocks the temporal load**
- [ ] `.gitignore` fixed so `PROVENANCE.md` is committable — **handoff item, blocks the audit trail for all agents**
- [ ] `province_territory` backfill applied to the 342 existing rows — build phase
- [ ] Polling-division layer — deferred pending operator decision
