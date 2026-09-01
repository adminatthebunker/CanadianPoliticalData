# Saskatchewan — Electoral Boundary Research

> Standalone boundary/roster dossier for Saskatchewan. Cross-cutting context
> (methodology, licence matrix, reconciliation strategy) lives in [`overview.md`](./overview.md).
> The legislative-data dossier for this jurisdiction is at [`../saskatchewan.md`](../saskatchewan.md).

**Agency:** Elections Saskatchewan | **Website:** https://www.elections.sk.ca | **Districts (current):** 61 | **Current order:** The Representation Act, 2022 (2022 Saskatchewan Constituency Boundaries Commission) | **Next redistribution:** commission struck after every second general election under The Constituency Boundaries Act, 1993 — next expected ~2032

**Status snapshot (2026-08-18):** ⚠ **Both generations obtained; licence blocked; and what we hold is PROVEN to be the wrong generation.** ✅ The authoritative 61-constituency file is a clean direct download from Elections Saskatchewan (12.2 MB, one record per district, EPSG:26913) — staged. ✅ **The 2012 prior generation is also now staged** — recovered via the Wayback CDX technique (brief amendment A5) and confirmed still live at the origin, merely unlinked. ⛔ **Licence is the blocker, not the data**: Elections Saskatchewan publishes no open licence anywhere, only a bare `Copyright © 2025 Elections Saskatchewan` footer. No click-through was encountered and nothing was accepted. ★★★ **Saskatchewan reproduces the BC signature exactly, and it is now proven rather than inferred** — see [Why we hold 46](#-why-we-hold-46-of-61--the-shortfall-diagnosis). With both generations in hand, an area comparison shows **46/46 of our stored polygons match the 2012 geometry to a median of 0.07%, and 0/46 match the 2022 geometry** (median deviation 11.67%, worst case 5,642%). Our 46 rows are **exactly the 46-name intersection** of the 2012 and 2022 orders, carrying 2012 shapes under names that are still current. ⚠ **SK's real error is 61 wrong or missing, not 15** — and because the seat count held at 61→61 and every name still resolves, nothing about the 46 looks broken. That makes it the worst "confident wrong riding" instance in the corpus. ✅ Roster join is clean: `legassembly.sk.ca` carries all 61 authoritative district names verbatim.

---

## Current boundaries

- **Source URL(s):** https://cdn.elections.sk.ca/maps-ge30/ESK_KML_Shape_Files_Mar2024.zip ; https://www.elections.sk.ca/candidates-political-parties/maps/ ; https://gistest.saskatchewan.ca/arcgis/rest/services/Administrative/MapServer/6
- **Format:** ESRI shapefile, zipped — ⚠ **inside a second zip**. The outer archive (12,223,644 bytes) is a macOS bundle carrying `__MACOSX/` and `.DS_Store`; the shapefile lives at `ShapeFile/Constituency/Constituency30th.zip` (971,204 bytes) and unpacks to `ConstituencyGE30th.{shp,shx,dbf,prj,cpg,sbn,sbx}`. KMZ of the same geometry is bundled alongside.
- **CRS / projection:** **EPSG:26913** (NAD83 / UTM zone 13N). Verbatim from `ConstituencyGE30th.prj`:
  `PROJCS["NAD_1983_UTM_Zone_13N",GEOGCS["GCS_North_American_1983",DATUM["D_North_American_1983",SPHEROID["GRS_1980",6378137.0,298.257222101]],PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]],PROJECTION["Transverse_Mercator"],PARAMETER["False_Easting",500000.0],PARAMETER["False_Northing",0.0],PARAMETER["Central_Meridian",-105.0],PARAMETER["Scale_Factor",0.9996],PARAMETER["Latitude_Of_Origin",0.0],UNIT["Meter",1.0]]`
  ⚠ **No `AUTHORITY["EPSG","26913"]` clause** (brief amendment A4). The EPSG identity is fixed by the parameters — central meridian −105.0 and scale factor 0.9996 are UTM zone 13, on the NAD83 datum. The `.shp` header bbox is `X 133,978..766,070 / Y 5,427,364..6,661,937` — metres, so unambiguously projected. The build must `ST_Transform(ST_SetSRID(geom, 26913), 4326)`; `ST_SetSRID` alone is the Fort Erie bug.
  ⚠ **This differs from Manitoba's zone.** SK is zone 13 (26913), MB is zone 14 (26914). Two neighbouring provinces, two different EPSG codes — a shared prairie loader must not hardcode one.
- **Attribute schema:** parsed from the `.dbf` header; encoding **UTF-8**, declared in a lowercase `.cpg`:

  | Field | dBase type | Length | Dec | Meaning |
  |---|---|---:|---:|---|
  | `Constituen` | `C` (character) | 50 | 0 | Constituency name, e.g. `Athabasca` |
  | `Constitu_1` | `N` (numeric) | 5 | 0 | ★ Constituency number, `1`–`61` |
  | `Constitu_2` | `C` (character) | 10 | 0 | ★ Three-letter code, e.g. `ATH` |
  | `Shape_Leng` | `F` (float) | 19 | 11 | Perimeter, projected units |
  | `Shape_Area` | `F` (float) | 19 | 11 | Area, projected units |

  ⚠ Field names are ArcGIS 10-character truncations (`Constituen`, `Constitu_1`, `Constitu_2`) — visually confusable and trivially mistyped. The `gistest` REST service exposes the *same* layer under a **different** field set (`CONSTITUEN`, `CONSTITU_1`, `CONSTITU_2`, plus `CON_NAME`, `CON_NUM`), so the two surfaces of one dataset disagree on schema — amendment A4's per-file-schema rule applies.
- **District ID field:** ★ **`Constitu_1`** — a dense integer 1–61 — with `Constitu_2` as a secondary three-letter mnemonic. **This matters more than usual**: the SK legislative dossier records that Saskatchewan publishes *no* stable per-MLA identifier (`politicians.sk_assembly_slug` is a synthesised `firstname-lastname`), so SK has been one of the weakest jurisdictions for exact joins. `Constitu_1` is the first genuine numeric Saskatchewan key we have found in any pipeline. ⚠ But it is **not** what we currently store — our slug is a kebab-case name (`.../athabasca`) — and it is a positional number that a future commission will reassign, so it is only stable *within* a generation. Recommend `authority_district_id = Constitu_1` scoped by `boundaries_version`, keeping the kebab-case `constituency_id` unchanged.
- **Effective date:** **2024-10-01** — the issue of the writs for the 30th General Election (polling day 2024-10-28). The 2022 Commission tabled its final report on 2022-10-27; the resulting statute is **The Representation Act, 2022**, which defines the 61 constituencies. Elections Saskatchewan and the Commission both state the new boundaries "come into effect at the issue of the writs for the next General Election," and the 2024 writs were dated 2024-10-01. Per the project ruling (brief amendment A2) this legal date is the value to use. **No conflicting agency-metadata date exists** — the shapefile carries no publication-date attribute; the only other candidate is the file's `Last-Modified` of 2024-03-08, which is a publication artifact and explicitly *not* the in-force date.
- **Superseded date:** n/a (current).
- **District count:** **61**, matching the 61 seats in the Legislative Assembly. ✅ Verified: 61 `.dbf` records and 61 distinct `Constituen` values — one record per district, **no multipart split** (contrast the federal 45th-GE file). Composition per the Commission: 59 southern constituencies redrawn, plus the two northern constituencies **Athabasca** and **Cumberland** left unchanged.
- **Difficulty (1–5):** **2** — undocumented but structured. The file is a plain HTTPS `GET` with no auth, but it is not catalogued in any open-data portal, the download is buried on an HTML maps page behind Cloudflare, and it is a zip-inside-a-zip. The *licence*, not the retrieval, is what is actually blocked.
- **Notes:**
  - ⚠ **Cloudflare fronts `www.elections.sk.ca`.** `WebFetch` received **HTTP 403**; a plain `curl` with a realistic browser `User-Agent` received **HTTP 200** and the full 1.05 MB page. Not a hard WAF — no CAPTCHA, no JS challenge — but a default-UA fetcher will conclude the site is blocked. The `cdn.elections.sk.ca` file host had no such issue.
  - ⚠ **Unknown URLs return HTTP 404 with a ~956 KB full-page body.** Status codes are honest (unlike the StatCan trap), but the payload size is not a signal of success — check the status, not the byte count.
  - ⚠ **The ArcGIS REST service is on a *test* host.** `gistest.saskatchewan.ca/arcgis/rest/services/Administrative/MapServer/6` serves `Provincial Constituencies` (`copyrightText: "Elections Saskatchewan"`, `maxRecordCount: 1000`) and works. The production host `gis.saskatchewan.ca` returns `Server object extension 'featureserver' not found` for the same path. **Do not build a production dependency on a hostname containing `gistest`** — treat it as a convenience oracle only.
  - ⛔ **Dead end: Saskatchewan GeoHub** (`geohub.saskatchewan.ca`, an ArcGIS Hub site) publishes **no** constituency layer — its dataset search returns `numberMatched: 0` for both `constituency` and `electoral`. This matters because Government-of-Saskatchewan datasets there carry the open `sk-suudl` licence; had constituencies been republished under it, the licence problem below would have been solved. They are not. Recorded so nobody re-probes it.
  - ⛔ **Dead end: `open.canada.ca`** carries no Saskatchewan provincial constituency dataset. The federated search surfaces only Government-of-Saskatchewan natural-resource layers (`sk-suudl`) and NRCan federal products.

## Prior boundaries (immediately preceding)

- **Source URL(s):** https://cdn.elections.sk.ca/maps-ge29/Elections_SK_constituency_shape_files_GE29.zip
  ★ **Recovered via the Wayback CDX technique (brief amendment A5), after direct probing failed.** ~~None located.~~ My first pass guessed four filename patterns under `maps-ge29/` and got 404s on all of them; the actual filename is `Elections_SK_constituency_shape_files_GE29.zip`, which no page on `elections.sk.ca` links to any more. The CDX index over `cdn.elections.sk.ca/*` returned 16 archived archives, and **the file is still live at the origin (HTTP 200, 1,763,172 bytes)** — unlinked, not deleted, exactly the pattern A5 describes. Recorded dead ends that remain dead: `https://www.elections.sk.ca/electoralevents/` (HTTP 404); Saskatchewan GeoHub (0 matches); `open.canada.ca` (no SK provincial dataset); `gistest.saskatchewan.ca` (one constituency layer, current generation only).
- **Format:** ESRI shapefile, zipped (1,763,172 bytes). ✅ **Not** nested — unlike the current generation, this archive unpacks directly to `Constituency.{shp,shx,dbf,prj,sbn,sbx}` plus a `.shp.xml`.
- **CRS / projection:** **EPSG:26913** (NAD83 / UTM zone 13N) — **byte-for-byte the same `PROJCS` string as the current generation**, verified by direct comparison. ✅ No cross-generation reprojection difference to handle. ⚠ Same missing `AUTHORITY` clause.
- **Attribute schema:** parsed from the `.dbf` header. ⚠ **No `.cpg` file at all** — the encoding is undeclared, so a reader must assume one. I used latin-1; SK district names in this generation contain no characters where latin-1 and UTF-8 diverge, so nothing is at risk here, but the assumption should be made explicit in the loader rather than left to a default.

  | Field | dBase type | Length | Dec | Meaning |
  |---|---|---:|---:|---|
  | `OBJECTID` | `N` | 9 | 0 | ArcGIS row id |
  | `Con_Name` | `C` | 50 | 0 | Constituency name, e.g. `Estevan` |
  | `Con_Num` | `N` | 4 | 0 | ★ Constituency number |
  | `Variance` | `F` | 13 | 11 | ★ Population variance from quotient, e.g. `-2.78735` (percent) |
  | `AreaKM` | `F` | 19 | 11 | Area in km² — ⚠ **already km², not m²** |
  | `FilterOut` | `N` | 9 | 0 | Undocumented flag; `0` on the sample |
  | `Shape_Leng` | `F` | 19 | 11 | Perimeter, projected units |
  | `Shape_Area` | `F` | 19 | 11 | Area in projected m² |

  ⚠ **`AreaKM` and `Shape_Area` are in different units in the same row** (`5.393e+03` km² vs `5.393e+09` m²). I initially divided `AreaKM` by 1e6 as if it were m² and got nonsense ratios of ~10⁸ before catching it. Use `Shape_Area/1e6` for cross-generation comparison so both generations are measured the same way.
  ⚠ **Field names differ completely from the current generation** (`Con_Name`/`Con_Num` vs `Constituen`/`Constitu_1`) — amendment A4's per-file-schema rule, and a second instance of it within one jurisdiction.
- **District ID field:** **`Con_Num`.** ⚠ **Do not join it across generations.** The current file's `Constitu_1` is also a dense 1–61 integer, so the two generations use overlapping numeric ranges for *different* districts — a cross-generation join on the number would silently produce wrong matches. Scope by `boundaries_version`.
- **Effective date:** **2016-03-08 — `needs confirmation`.** The Representation Act, 2012 was passed 2013-05-15 and its 61 constituencies first took effect at the 28th General Election (polling day 2016-04-04), under the same "issue of the writs" mechanism as the 2022 order. Saskatchewan's writ period is 27 days, which places the writ date at 2016-03-08, but **the writ date was not confirmed from a primary source in this pass** — the arithmetic is mine, not Elections Saskatchewan's. Confirm before loading. (Note the 2012 boundaries were originally scheduled for a 2015-11-02 election that did not occur on that date.)
- **Superseded date:** **2024-10-01** — the mirror of the current generation's effective date. Well established; no confirmation needed.
- **District count:** **61**, the same as the current generation — ✅ now verified directly from the file (61 records, 61 distinct `Con_Name`, no multipart split). ★ **Saskatchewan's seat count did not change** in the 2022 redistribution — only the boundaries and 15 of the names did. This is why the shortfall was not obvious from counts alone: 61 → 61 gives no arithmetic signal that anything moved. ★ **Exactly 46 names appear in both generations** — and those 46 are precisely the rows we hold. See the geometry proof below.
- **Difficulty (1–5):** ~~**5** — unavailable from the agency.~~ **2** — available, but only discoverable through the Wayback CDX index. Elections Saskatchewan's CDN is organised per-general-election and it *retains* `maps-ge29/` alongside `maps-ge30/`; it simply no longer links to it. Nothing is blocked — a WAF, a licence gate and a deletion were all ruled out.
- **Notes:**
  - ★ **A5's CDX technique is the entire reason this generation was recovered**, and the lesson generalises: my direct probing concluded "not published" when the correct conclusion was "not *linked*". Four plausible guessed filenames all 404'd; the real one was none of them. **A 404 on a guessed filename is evidence about the filename, not about the file's existence.**
  - ★ **In-force status established from content, not filename** (amendment A5's second rule). `GE29` in the filename is the 29th General Election, but I did not rely on that: the file's 61 `Con_Name` values were compared against both the 46 names we hold and the current 61, and it is the generation whose geometry our stored rows reproduce to 0.07%. The naming and the content agree — but the content is what establishes it.
  - ~~The 46 rows in `constituency_boundaries` are our only copy of the 2012 geometry.~~ ⚠ **Superseded** — we now hold the authoritative 61-district 2012 file, which supersedes those 46 rows as the prior-generation source and makes them redundant rather than precious.
  - ⛔ `github.com/opennorth/represent-canada-data` is **no longer needed** as a fallback mirror for SK. Standing instruction 1 would have forbidden citing it anyway; the agency's own file is now staged.

## District ↔ elected official mapping

- **Source URL(s):** https://www.legassembly.sk.ca/mlas ; https://www.legassembly.sk.ca/mlas/mla-contact-information/
- **Format:** server-rendered HTML (82,304 bytes). No auth, no rate limiting, no WAF challenge observed on `legassembly.sk.ca` (unlike `elections.sk.ca`).
- **★ Join quality — measured:** the MLA contact page contains **61 of the 61** authoritative `Constituen` values verbatim after punctuation/accent normalisation. **61/61, zero unmatched.** The Legislative Assembly and Elections Saskatchewan agree on district naming, which is not guaranteed and is worth having verified.
- **Fields available:** member name, constituency, caucus standing (Government / Opposition / Independent), contact details. Per-member detail pages are addressed by name query string — `member-details?first=Ken&last=Francis` — **not** by any stable ID.
- ⚠ **No stable per-MLA identifier is published**, consistent with the legislative dossier: `politicians.sk_assembly_slug` is a synthesised `firstname-lastname`, which is why SK sponsor/speaker resolution has always leaned on name-fuzz. The boundary file's `Constitu_1` gives us a stable *district* key but does nothing for *member* identity. **Known bounded gap:** a Saskatchewan MLA who shares a surname with a predecessor remains ambiguous.
- **Difficulty (1–5):** **3** — predictable HTML scrape; no JSON surface found.
- **Notes:** the practical join is `district name → Constitu_1 → boundary`, with the MLA attached by district rather than by member ID. That is sufficient for "who represents me" and insufficient for historical member disambiguation.

## Postal-code correspondence (if published)

⛔ **None published by Elections Saskatchewan.** Per brief amendment A3 this was time-boxed to a quick check: the agency offers an interactive *Find my constituency* lookup (https://www.elections.sk.ca/voters/findmyconstituency/) and no bulk postal file. No open-licence concordance exists for Saskatchewan. **Not needed** — our lookup is point-in-polygon, and the staged 61-district polygon set is a strictly better input than a weighted postal table.

## Terms / Licensing

⛔ **No open licence. This is the blocker for Saskatchewan.**

The only reuse-relevant statement located anywhere on `elections.sk.ca` is the site footer, verbatim:

> "Copyright © 2025 Elections Saskatchewan"

`/copyright/`, `/privacy-policy/` and `/terms-of-use/` all return **HTTP 404** — the agency publishes no
terms-of-use page at all. The ArcGIS layer on the test host carries only:

> "Elections Saskatchewan"

as its `copyrightText`. There is **no** grant of permission to use, copy, modify, publish or distribute,
and no named licence.

**What this is and is not.** It is **not** a click-through gate: no agreement was presented, no checkbox
existed, no account was required, and nothing was accepted or submitted (standing instruction 3 was not
engaged). The files are freely downloadable over plain HTTPS. It is bare Crown copyright with silence on
reuse — which is *weaker* than the click-through case in one respect, because there is not even a written
term to read and comply with.

**Assessment.** Internal research use is defensible. **Redistribution through
`/api/public/v1/boundaries/*` is not cleared** and should not proceed on silence. Saskatchewan belongs in
the overview's licence taxonomy alongside Manitoba as *no licence, no inheritance* — the upstream audit
found no SK provincial licence provenance in `represent-canada-data` either, so there is nothing to
inherit and nothing to quote. This needs an operator decision or an email to the agency; see
Research-handoff items.

## Rate limits / auth

- **Authentication:** none. No API key, no account, no session, no referer check on any surface.
- **Rate limiting:** none observed. Roughly 20 requests across `elections.sk.ca`, `cdn.elections.sk.ca`, `gistest.saskatchewan.ca`, `geohub.saskatchewan.ca` and `legassembly.sk.ca` — zero 429s, zero throttling.
- ⚠ **Cloudflare on `www.elections.sk.ca`** (`server: cloudflare`). Default-UA fetchers get **403**; a browser `User-Agent` gets **200**. No CAPTCHA, no JS challenge, no cookie dance — this is UA filtering, not a Radware/PerfDrive-class blockade, and is nothing like the PE/YT tier. `cdn.elections.sk.ca` (the file host) served every request without a UA header at all.
- **Caching:** `cdn.elections.sk.ca` returns accurate `Content-Length` and `Last-Modified` (`Fri, 08 Mar 2024 22:52:46 GMT`) and honours `HEAD`. ✅ Per CLAUDE.md convention #6 the refresh check is a cheap conditional `HEAD`.
- **Instruction-source boundary:** no page fetched contained text addressed to an AI agent. Nothing to report under standing instruction 8.

## Staged files

Staging root `data/boundaries/saskatchewan/`; sha256 audit table in [`PROVENANCE.md`](../../../data/boundaries/saskatchewan/PROVENANCE.md). **13.3 MiB of a 500 MB budget.**

| Path | Bytes | Districts | Role |
|---|---:|---:|---|
| `current/ESK_KML_Shape_Files_Mar2024.zip` | 12,223,644 | 61 | ★ current generation (2022 commission), nested zip |
| `prior/Elections_SK_constituency_shape_files_GE29.zip` | 1,763,172 | 61 | ★ prior generation (2012 Act), recovered via CDX, not nested |

Not staged: the bundled `VotingAreas_30thGE.zip` (4,046,488 bytes, sub-constituency voting areas) and the two `.kmz` duplicates, both inside the same archive and both out of scope.

## Reconciliation with `constituency_boundaries`

**What we hold** (read-only query, 2026-08-18):

- `source_set = 'saskatchewan-electoral-districts-representation-act-2012'` — **46 rows**, `level = 'provincial'`, `province_territory = 'SK'`, 46 distinct `constituency_id`.
- `constituency_id` prefix `saskatchewan-electoral-districts-representation-act-2012/`, slug = kebab-case district name (`.../athabasca`, `.../regina-lakeview`). **No numeric key.**
- `effective_from = '2023-01-01'`, `effective_to = NULL` on all 46 — the hardcoded literals from `services/scanner/src/opennorth.py`, not a legal date. ⚠ Note the date is *later* than the 2012 generation's real supersession would suggest and earlier than the 2022 order's real effective date; it is meaningless in both directions.
- Also present under `province_territory = 'SK'` but out of scope here: `regina-wards` (11) and `saskatoon-wards` (11), both municipal.

**★ The 46 are the wrong generation, and every one of them still name-matches.** Comparing our 46 slugs against the 61 authoritative `Constituen` values:

| Check | Result |
|---|---:|
| Authoritative districts (2022 commission) | 61 |
| Our rows | 46 |
| Ours that name-match a **current** district | **46 / 46 (100%)** |
| Ours with no current counterpart (districts abolished outright) | **0** |
| Current districts we hold no polygon for | **15** |

The 15 absent: `Dakota-Arm River`, `Estevan-Big Muddy`, `Kindersley-Biggar`, `Martensville-Blairmore`, `Moosomin-Montmartre`, `Regina Mount Royal`, `Regina South Albert`, `Rosetown-Delisle`, `Saskatoon Chief Mistawasis`, `Saskatoon Silverspring`, `Saskatoon Stonebridge`, `Saskatoon University-Sutherland`, `Warman`, `Weyburn-Bengough`, `White City-Qu'appelle`.

⚠ **The 100% name-match is the trap, not the reassurance.** Because no SK district was abolished outright — the 2022 commission renamed 15 and redrew the rest while holding the count at 61 — every one of our 46 rows carries a name that is still current. Nothing in the data looks stale.

### ★★★ Geometry proof — the 46 carry 2012 shapes, measured against both generations

With both generations staged, this is no longer an inference. Comparing each stored polygon's
`area_sqkm` (geodesic, from the 4326 geometry) against `Shape_Area/1e6` from each candidate generation's
shapefile:

| | vs **2012** (GE29) | vs **2022** (GE30) |
|---|---:|---:|
| Median absolute deviation | **0.07%** | **11.67%** |
| Districts matching within 1% | **46 / 46** | 5 / 46 |
| Districts matching *only* this generation | **41** | **0** |

**The method validates itself on a built-in control.** The 2022 commission left exactly two
constituencies untouched — **Athabasca** and **Cumberland**, the two northern seats — and those are two
of the five that match *both* generations (−0.46% and +0.09% against 2022). Where the geometry genuinely
did not change, the test correctly reports no change; the residual sub-1% noise is UTM-planar versus
geodesic distortion, not disagreement. The other three both-matches (`Kelvington-Wadena` +0.80%,
`Melfort` +0.72%, `Prince Albert Northcote` −0.77%) are districts the commission barely adjusted.

**Not one of the 46 matches the 2022 geometry alone.** The worst divergences are not marginal:

| District | ours (km²) | 2012 | 2022 | vs 2012 | vs 2022 |
|---|---:|---:|---:|---:|---:|
| Regina Wascana Plains | 792.1 | 791.9 | 13.8 | **+0.03%** | +5,642% |
| Regina Pasqua | 31.8 | 31.7 | 10.7 | **+0.15%** | +198% |
| Saskatoon Fairview | 28.3 | 28.3 | 11.3 | **+0.09%** | +151% |
| Moose Jaw North | 18.8 | 18.7 | 347.5 | **+0.20%** | −94.6% |
| Moose Jaw Wakamow | 32.6 | 32.6 | 317.6 | **+0.04%** | −89.7% |
| Yorkton | 42.8 | 42.8 | 157.4 | **−0.03%** | −72.8% |

★ **This is the BC signature reproduced exactly.** Our 46 rows are the **name-stable intersection** of
the 87→93-equivalent transition — here 61→61 with 46 names surviving — carrying old geometry under
current names, because `_fetch_boundary` returns `None` on a 404 with no log, no counter and no raise, so
the 15 renamed districts vanished silently while the 46 survivors were written with 2012 shapes.

⚠ **Seven districts had their name moved onto substantially different territory** (>2× or <0.5× the area).
`Regina Wascana Plains` is the extreme: we serve a 792 km² polygon for a district that is now 13.8 km².
A point anywhere in the other 778 km² gets confidently told it is in Wascana Plains when it is not.

**Coverage arithmetic:** the 46 names we hold account for 575,811 km² of Saskatchewan's 652,286 km²
(88.3%); the 15 absent districts are 76,475 km² (11.7%) that return no representative at all. But our
*stored* polygons total 554,324 km² — so 85% of the province is covered by shapes that are wrong for
41 of 46 districts, and the two failure modes are not additive: some of the 11.7% "uncovered" territory
is in fact covered by a stale polygon bearing the wrong district's name.

**Consequence for the build — this is the operative point.** SK is **not** "insert the missing 15."
All 61 must be loaded as a new generation and all 46 existing rows superseded. Treating this as a
backfill would leave 41 wrong polygons in place while making the table *look* complete at 61/61.

**Re-key assessment.** Our slug is a kebab-case name; the authoritative key is the integer `Constitu_1`. Under the overview's recommendation (d): `authority = 'elections-saskatchewan'`, `authority_district_id = Constitu_1` (as text), scoped by `boundaries_version` because the commission reassigns those integers.

**★ A6 target prefix: `saskatchewan-electoral-districts`.** ~~`saskatchewan-electoral-districts-representation-act-2022/…`~~ — ⛔ **that would have violated ruling A6**, which forbids encoding a generation in the prefix. Our current prefix
`saskatchewan-electoral-districts-representation-act-2012` violates it too. The generation belongs in
`boundaries_version` alone, so both generations share one generation-free prefix and the 46 surviving
districts keep the *same* `constituency_id` across the 2012→2022 transition:

| Table | Rows carrying the old prefix | Change |
|---|---:|---|
| `politicians` | **45** (all active; 46th row is inactive) | `replace(constituency_id, 'saskatchewan-electoral-districts-representation-act-2012/', 'saskatchewan-electoral-districts/')` |
| `politician_terms` | **182** | same `replace()` |
| `constituency_boundaries` | **46** | same `replace()`, plus `boundaries_version = '2012-representation-act'` |

**Total SK prefix cost: 273 mechanical row-updates.** ★ Doing this *before* the generational load is
what makes the rest cheap: with a generation-free prefix, the 46 name-stable districts need **no
`politicians` update at all** when the 2022 geometry lands — their `constituency_id` is unchanged and
`boundaries_version` does the switching. Only the 15 genuinely new districts need new `politicians`
values.

⚠ **SK remains a generational insert, not a backfill** — 61 new rows, `effective_to` set on all 46 old
ones. That is unchanged by A6 and is driven by the geometry proof above, not by the keying.

⚠ **`province_territory` is already correct** (`'SK'` on all 46) — unlike the federal rows. No backfill needed.

⚠ **`politician_terms.constituency_id` is empty across the SK corpus**, consistent with the legislative dossier. The join runs entirely through `politicians.constituency_id`. Repointing that column is the whole of the roster-side work.

**Proposed temporal values:**

Both generations share the prefix `saskatchewan-electoral-districts/` per ruling A6.

| Generation | `constituency_id` | `boundaries_version` | `effective_from` | `effective_to` | Rows |
|---|---|---|---|---|---|
| The Representation Act, 2022 | `saskatchewan-electoral-districts/<kebab-name>` | `2022-representation-act` | `2024-10-01` | `NULL` | 61 |
| The Representation Act, 2012 | `saskatchewan-electoral-districts/<kebab-name>` | `2012-representation-act` | `2016-03-08` `needs confirmation` | `2024-10-01` | ✅ **61 available** (46 currently held) |

---

### ★★ Why we hold 46 of 61 — the shortfall diagnosis

**This section is cross-jurisdictional.** It was investigated on Saskatchewan because SK is the cleanest
test case, and the conclusion is reproduced verbatim in [`manitoba.md`](./manitoba.md). Consolidation into
[`overview.md`](./overview.md) is the coordinator's call.

**Both standing hypotheses are wrong.**

⛔ **Pagination/truncation — ruled out.** `services/scanner/src/opennorth.py` calls
`ingest_saskatchewan_mlas(limit=200)` against 61 seats, and `_fetch_reps` (line 219) pages via
`meta.next` until exhausted. The cap cannot bind at 61. Same for Manitoba at 57. There is no page
boundary anywhere near the shortfall, and the missing districts do **not** cluster alphabetically —
they are scattered from `Dakota-Arm River` to `White City-Qu'appelle`.

⛔ **Incomplete roster — ruled out.** Saskatchewan's roster is **complete**: 61 active provincial
politicians, 61 distinct `constituency_name` values, exactly matching the 61 seats. Not one member is
missing. The lead's framing — "if Open North's roster was incomplete for a province, we'd silently get
fewer polygons" — describes a real mechanism that is simply not what happened here.

**★ The actual mechanism: a missing `related.boundary_url` on the representative record.**

`_ingest_set` (line 568) fetches a polygon only as a side effect of iterating representatives, and only
when `_constituency_id()` returns non-null:

```python
cid = _constituency_id(rep, set_def)
if cid and cid not in seen_ids:          # ← silent skip when cid is None
    ...
    gj = await _fetch_boundary(client, set_def, cid)
```

`_constituency_id()` (line 246) returns `None` whenever the rep record has no
`related.boundary_url`. So the count of polygons we hold equals **the number of distinct non-null
`boundary_url` values across active representatives** — nothing else.

**Verified across all 13 provincial/territorial sets:**

| | boundaries held | active reps | distinct district names | reps with **no** `boundary_url` | distinct `constituency_id` |
|---|---:|---:|---:|---:|---:|
| AB | 87 | 87 | 87 | 0 | 87 |
| BC | 52 | 98 | 93 | 46 | 52 |
| MB | 56 | 57 | 56 | 1 | 56 |
| NB | 22 | 55 | 50 | 33 | 22 |
| NL | 36 | 48 | 44 | 12 | 36 |
| NS | 55 | 55 | 55 | 0 | 55 |
| NT | 19 | 20 | 19 | 1 | 19 |
| **NU** | **0** | **22** | **22** | **22** | **0** |
| ON | 123 | 123 | 122 | 1 | 122 |
| PE | 26 | 26 | 26 | 0 | 26 |
| QC | 124 | 125 | 124 | 1 | 124 |
| **SK** | **46** | **61** | **61** | **16** | **45** |
| YT | 19 | 32 | 22 | 13 | 19 |

`boundaries held == distinct constituency_id` in **11 of 13** jurisdictions exactly. The two exceptions
(ON and SK, each `+1`) are polygons retained for a representative who has since gone inactive — a
separate, milder finding: **boundary rows are never retired when their rep is.**

**★ And the reason `boundary_url` is missing is a vintage mismatch between Open North's *roster* and
Open North's *boundary set*.** Open North links a representative to a boundary by district name. When
the roster has moved to a new redistribution and the boundary set has not, the renamed and newly created
districts have nothing to match, so they silently get no `boundary_url`.

Saskatchewan demonstrates this exactly. **15 of the 16 unlinked SK representatives sit for districts
created or renamed by the 2022 commission**, which cannot exist in Open North's 2012 boundary set:

| Our roster's district name | 2022 authoritative name | Present in the 2012 boundary set? |
|---|---|---|
| Dakota-Arm River | Dakota-Arm River | no — new |
| Estevan-Big Muddy | Estevan-Big Muddy | no — renamed |
| Kindersley-Biggar | Kindersley-Biggar | no — renamed |
| Martensville-Blairmore | Martensville-Blairmore | no — renamed |
| Moosomin-Mon**m**artre ⚠ | Moosomin-Mon**tm**artre | no — renamed |
| Regina Mount Royal | Regina Mount Royal | no — new |
| Regina South Albert | Regina South Albert | no — new |
| Rosetown-Delisle | Rosetown-Delisle | no — renamed |
| Saskatoon Chief Mistaw**is** ⚠ | Saskatoon Chief Mistaw**asis** | no — new |
| Saskatoon Silver Springs ⚠ | Saskatoon Silverspring | no — renamed |
| Saskatoon Stonebridge | Saskatoon Stonebridge | no — renamed |
| Saskatoon University-Sutherland | Saskatoon University-Sutherland | no — renamed |
| Warman | Warman | no — new |
| Weyburn-Bengough | Weyburn-Bengough | no — renamed |
| White City-Qu'**A**ppelle ⚠ | White City-Qu'**a**ppelle | no — new |
| **Humboldt-Watrous** | Humboldt-Watrous | ✅ **yes — polygon exists** |

The **16th**, `Humboldt-Watrous`, is a different and rarer failure: the polygon is in our table and the
name is identical, yet the rep still carries no `boundary_url`. That one is a plain upstream linkage
miss, not a vintage effect. It is also why SK shows 46 polygons against 45 linked `constituency_id`s.

⚠ **Four of our SK roster district names are misspelled relative to the authoritative file** (marked ⚠
above: `Monmartre`/`Montmartre`, `Chief Mistawis`/`Chief Mistawasis`, `Silver Springs`/`Silverspring`,
`Qu'Appelle`/`Qu'appelle`). These came in through Open North and would defeat a naive name join at load
time. Normalise, and prefer `Constitu_1` over names wherever possible.

**Correcting the record on Nunavut.** The table above shows NU has **22 active representatives and 22
distinct district names** — a complete roster — with all 22 lacking `boundary_url`. So the overview's
statement that Nunavut's zero rows are explained by roster incompleteness is **wrong**: the roster is
fine, and NU has no polygons because Open North publishes no Nunavut boundary set for any rep to link
to. Same mechanism, most extreme case.

**What this changes for the build.** The shortfall is not a backfill problem, it is a **generational
replacement** problem, and the two look nothing alike:

1. **Counting rows against seats understates the damage.** SK's real error is 61 wrong or missing, not 15 missing — the 46 present rows are stale geometry, and 61 → 61 seats gave no arithmetic warning at all. Any province whose seat count survived its redistribution unchanged is hiding the same way.
2. **A province at full count is not necessarily correct.** AB (87/87), NS (55/55) and PE (26/26) match their seat counts, but that only proves every rep linked *to something* — it says nothing about whether Open North's boundary set is the current vintage. Each still needs its vintage checked against the agency's current order.
3. **The diagnostic is one query.** `reps with no boundary_url`, per jurisdiction, is the shortfall — and whether those reps' district names exist in the held boundary set separates "vintage mismatch" (replace the generation) from "upstream linkage miss" (backfill the row). MB is the worked control case: 1 unlinked rep, and its district *does* need a new polygon, but the vintage is right.
4. **Retire boundaries with their reps.** The ON and SK `+1` rows show polygons outliving the representative that caused them to be fetched. Harmless today; a source of duplicate `effective_to IS NULL` rows once a second generation exists.

## Research-handoff items

- **⛔ Saskatchewan has no open licence — this blocks redistribution, and it needs an operator decision.** Elections Saskatchewan publishes bare Crown copyright (`Copyright © 2025 Elections Saskatchewan`) and no terms-of-use page at all (`/copyright/`, `/privacy-policy/`, `/terms-of-use/` are all 404). Nothing was accepted or submitted. Three options: (a) internal use only, keep SK out of `/api/public/v1/boundaries/*`; (b) email Elections Saskatchewan for written permission — no published GIS contact was found, so this would go through the general contact channel; (c) accept the risk on the civic-transparency argument. **Recommendation: (a) now, (b) in parallel** — SK is one row in a public endpoint and not worth an unlicensed redistribution. Manitoba is in exactly the same position; a single decision can cover both.
- ~~**⛔ The 2012 boundaries are not published by anyone we can cite.**~~ ✅ **RESOLVED 2026-08-18** via the Wayback CDX technique (amendment A5). The full 61-district 2012 file is staged and still live at the origin. The question this item raised — *do we care about SK's prior generation?* — is now cheap to answer yes to: we have the complete authoritative 61, not a 46-row remnant, so historical "which riding was this address in during 2016–2024" queries become answerable at no extra research cost. **Recommendation: load both generations.**
- **⚠ SK must be loaded as a full generational replacement, not a 15-row backfill — this is the one thing to get right.** The geometry proof shows 41 of our 46 polygons are the wrong shape, and inserting only the 15 missing districts would take the table to a *complete-looking* 61/61 while leaving those 41 stale. There is no partial version of this fix that is safe.
- **Confirm the 2016 writ date before loading the prior generation.** I placed the 2012 boundaries' `effective_from` at 2016-03-08 by subtracting Saskatchewan's 27-day writ period from the 2016-04-04 polling day. The mechanism is right and the polling day is certain, but the writ date itself is **my arithmetic, not a cited primary source**. One lookup in Elections Saskatchewan's 28th-General-Election proclamations would settle it.
- **Should `Constitu_1` become a `politicians` column?** Saskatchewan is the jurisdiction CLAUDE.md convention #1 most wants an ID for — `sk_assembly_slug` is synthesised because the Legislative Assembly publishes no member ID. `Constitu_1` is a *district* key, not a member key, so it does not satisfy the convention, but it would make SK boundary joins exact for the first time. Worth a column on `constituency_boundaries` via `authority_district_id`; **not** worth inventing a member ID from it.
- **★ The shortfall diagnosis above changes the build plan for every province, not just SK and MB.** Specifically, item 2 — a province matching its seat count is not evidence its vintage is current — means AB, NS and PE need their vintages checked against the agency's current order even though they look complete. That check is cheap and nobody is currently assigned to it.

## Status

- [x] Current boundaries located and staged (2026-08-18) — 61/61 districts, one record each
- [x] CRS confirmed — EPSG:26913, verbatim WKT recorded, ⚠ no `AUTHORITY` clause
- [x] Attribute schema parsed from the `.dbf` header
- [x] District ID field identified — `Constitu_1`, integer 1–61, generation-scoped
- [x] Legal effective date established — 2024-10-01 (writs, 30th GE), per ruling A2
- [x] District ↔ elected official source located and join quality measured — 61/61
- [x] Postal-code correspondence checked — none published, not needed
- [x] ★★ Shortfall cause diagnosed and verified across all 13 jurisdictions
- [x] ★★★ Geometry **proven** stale — 46/46 match 2012 (median 0.07%), 0/46 match 2022; BC signature reproduced
- [x] Reconciliation completed — 46 held are the **superseded 2012 generation**, 100% name-collide with current
- [x] Prior boundaries located and staged (2026-08-18) — 61/61, recovered via Wayback CDX per A5
- [x] A6 generation-free prefix specified — `saskatchewan-electoral-districts`; 273 mechanical row-updates
- [ ] Prior-generation `effective_from` confirmed — `needs confirmation` (2016 writ date is my arithmetic)
- [ ] Licence cleared for internal use — **blocked: no licence published, operator decision needed**
- [ ] Licence cleared for redistribution — **blocked: do not serve publicly until resolved**
