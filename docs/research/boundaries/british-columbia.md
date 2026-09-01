# British Columbia — Electoral Boundary Research

> Standalone boundary/roster dossier for British Columbia. Cross-cutting context
> (methodology, licence matrix, reconciliation strategy) lives in [`overview.md`](./overview.md).
> The legislative-data dossier for this jurisdiction is at [`../british-columbia.md`](../british-columbia.md).

**Agency:** Elections BC | **Website:** https://elections.bc.ca | **Districts (current):** 93 | **Current order:** Electoral Districts Act, SBC 2023 c. 15 (2022-23 BC Electoral Boundaries Commission) | **Next redistribution:** ~October 2029 — *Electoral Boundaries Commission Act*, RSBC 1996 c. 107, **s. 5(2)**: "A new commission must be appointed no later than one year after the final voting day for every second general election following the appointment under subsection (1)." The 2022-23 commission was appointed 2021-10-21; counting the two general elections after it (2024-10-19, then the fixed-date 2028 election), the next commission is due within a year of the 2028 vote. Boundaries from it would not take force until the *following* dissolution — so **the 93-district set is stable through at least the 2028 election**

**Status snapshot (2026-08-18):** ✅ **Fully cracked — best-outcome jurisdiction, and the 52-row mystery is solved.** ★ The 52 rows we hold are **not a 2015 set and not any real BC redistribution** — they are the **exact 52-district name-stable intersection of the 2015 (87) and 2023 (93) orders**, carrying **2015 geometry** (51 of 52 areas match the authoritative 2015 shapes to <0.5%). ★ The mechanism is proven from our own DB, not guessed: Open North's BC roster **was complete at 93**, but **41 rows carry a `NULL` `constituency_id` and there are 0 orphans** — and zero orphans is the fingerprint proving the boundary fetch was *never called* rather than 404-ing. Those 41 representative records have no `related.boundary_url`, so `_constituency_id()` returned `None` and the guard at `opennorth.py:590` skipped the fetch, silently. **One root cause produces both halves of BC's problem** — the same `None` nulls the politician's district linkage (the 45 unreachable reps) *and* suppresses the boundary write (the 52 wrong polygons). ⛔ Pagination, regional-gap and short-roster explanations were each tested and **falsified**. ✅ Both generations staged (41.9 MB) in native **EPSG:3005**. ✅ Licence is **genuinely open and redistributable** — Elections BC Open Data Licence, commercial use and redistribution explicit, attribution-only. ★ **LIMS answers the roster question outright**: `allConstituencies` active-93 names match Elections BC `ED_NAME` **exactly, 93/93, zero divergence**. ★★ **BC publishes a complete postal-code→district concordance** — LIMS `allPostalCodeLookups`, **164,848 postcodes, all 93 current districts covered, no auth** — which can retire all 45 unreachable BC reps *without waiting for the polygon build*. ⚠ Three silent-mis-join traps found, all verified rather than suspected: `ELECTORAL_DISTRICT_ID` is generation-scoped (0/52 stable); **8 `ED_ABBREVIATION` codes are recycled onto different districts** across generations; and **the shapefile and WFS distributions of the same 2015 dataset disagree on the district ID by exactly one, 87/87** — contiguous IDs make that off-by-one map every district to its alphabetical neighbour with no error. ⛔ Open North is down (502 + cert expired 2026-08-07), but **nothing here depends on it** — the diagnosis is settled from our own DB and the authoritative files.

---

## Current boundaries

- **Source URL(s):** https://catalogue.data.gov.bc.ca/dataset/provincial-electoral-districts-electoral-boundaries-redistribution-2023 ; https://openmaps.gov.bc.ca/geo/pub/WHSE_ADMIN_BOUNDARIES.EBC_ELECTORAL_DISTS_BS11_SVW/ows?service=WFS&version=2.0.0&request=GetFeature&typeName=pub:WHSE_ADMIN_BOUNDARIES.EBC_ELECTORAL_DISTS_BS11_SVW&outputFormat=application/json&srsName=EPSG:3005
- **Format:** GeoJSON via WFS 2.0.0 (`outputFormat=application/json`), unzipped, 20.8 MiB. ⚠ **The catalogue record offers no vector download** — its four resources are a BCGW custom-order form, WMS, a KML *ground overlay* (raster tiles, not polygons), and an Oracle SDE pointer. The WFS endpoint is undocumented in the record; it was derived from the WMS resource URL by swapping `service=WMS` for `service=WFS` on the same `ows` path. Shapefile is also obtainable this way — `GetCapabilities` advertises `SHAPE-ZIP` alongside `application/json` (confirmed 2026-08-18, not attempted) — but GeoJSON is preferred per standing instruction 4, and ⚠ pulling `SHAPE-ZIP` would import the off-by-one ID trap documented under `## Prior boundaries`.
- **CRS / projection:** **EPSG:3005** — BC Albers. Requested explicitly via `srsName=EPSG:3005`; the response header confirms `"crs": {"type":"name","properties":{"name":"urn:ogc:def:crs:EPSG::3005"}}`. Verbatim WKT projection name, read from the 2015 shapefile's `.prj` (the same BCGW projection applies to both generations): `NAD_1983_BC_Environment_Albers`, full WKT:
  ```
  PROJCS["NAD_1983_BC_Environment_Albers",GEOGCS["GCS_North_American_1983",
  DATUM["D_North_American_1983",SPHEROID["GRS_1980",6378137.0,298.257222101]],
  PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]],PROJECTION["Albers"],
  PARAMETER["False_Easting",1000000.0],PARAMETER["False_Northing",0.0],
  PARAMETER["Central_Meridian",-126.0],PARAMETER["Standard_Parallel_1",50.0],
  PARAMETER["Standard_Parallel_2",58.5],PARAMETER["Latitude_Of_Origin",45.0],
  UNIT["Meter",1.0]]
  ```
  Coordinates are **metres** (first vertex `[1273122.7116, 469481.0502]`). ⚠ `ST_Transform(ST_SetSRID(geom, 3005), 4326)` is mandatory — `ST_SetSRID` alone reproduces the Fort Erie bug and the `boundary_in_wgs84_bounds` CHECK will reject every row.
  - ⚠ **The `.prj` carries no `AUTHORITY` clause**, so no automated EPSG detection will resolve it — the code must be supplied explicitly by the build. Derived by hand from the parameters rather than assumed, and each one matches **EPSG:3005** (`NAD83 / BC Albers`): projection Albers equal-area; false easting **1,000,000 m**; false northing **0**; central meridian **−126°**; standard parallels **50°** and **58.5°**; latitude of origin **45°**; units metre; spheroid GRS 1980.
  - ⚠ **EPSG:3005 vs EPSG:3153 — do not confuse them.** Both are "BC Albers" with *identical* projection parameters; they differ only in datum (NAD83 vs NAD83(CSRS)). The `.prj` says `D_North_American_1983`, i.e. plain NAD83 → **3005**, not 3153. Deriving the code from the projection parameters alone would not distinguish these; the datum string is what settles it.
  - The WFS request used `srsName=EPSG:3005` and the response independently declares `urn:ogc:def:crs:EPSG::3005`, which corroborates the hand derivation from a second direction.
- **Attribute schema:** from the WFS `DescribeFeatureType` XSD (authoritative, no guessing) — `ELECTORAL_DISTRICT_ID` (decimal, non-null), `BOUNDARY_SET_ID` (decimal, non-null), `ED_ABBREVIATION` (string, non-null), `ED_NAME` (string, non-null), `GAZETTE_DATE` (date), `FEATURE_AREA_SQM` (decimal), `FEATURE_LENGTH_M` (decimal), `SHAPE` (gml geometry), `OBJECTID` (decimal), `SE_ANNO_CAD_DATA` (hexBinary — ArcGIS annotation blob, ignore).
- **District ID field:** **`ELECTORAL_DISTRICT_ID`** (integer, 258–350 in this generation, unique across all 93). This is the authoritative Elections BC key and is what `authority_district_id` should hold with `authority = 'elections-bc'` per [`overview.md`](./overview.md) recommendation (d). It does **not** match anything we currently store — our `constituency_id` slugs are kebab-case names. See `## Reconciliation` for the re-key.
  - ⚠ **`ELECTORAL_DISTRICT_ID` is generation-scoped, not a persistent district identity.** Verified: of the 52 districts whose *name* is unchanged between the 2015 and 2023 orders, **0 of 52** keep the same `ELECTORAL_DISTRICT_ID` (Abbotsford-Mission is `171` in the 2015 WFS set and `258` in the 2023 set). Values are contiguous and assigned in alphabetical order within each generation — 171–257 for 2015, 258–350 for 2023 — i.e. the 2023 block simply continues numbering where 2015 stopped. It is unique *within* a `BOUNDARY_SET_ID`, which is exactly right for a per-generation key and exactly wrong for joining generations. Pair it with `BOUNDARY_SET_ID` and never join across them on it alone.
  - ⚠ See also the **shapefile-vs-WFS off-by-one trap** under `## Prior boundaries` — the same field name carries different values in different distributions of the same dataset.
- **Effective date:** **2024-09-21** → `effective_from`. Legal chain, all primary: *Electoral Districts Act*, SBC 2023 c. 15, **s. 1** — "There are to be 93 electoral districts, with one member of the Legislative Assembly to be elected for each"; **s. 6** — "This Act comes into force on the day the 42nd Parliament is dissolved"; the 42nd Parliament was dissolved **2024-09-21** (general election 2024-10-19). Corroborated from the opposite direction by BC Laws' point-in-time record for the superseded Act, which states it was "repealed by 2023-15-5, effective September 21, 2024."
  - ⚠ **Do not use `GAZETTE_DATE` (`2023-12-07`) as `effective_from`.** It is the date the boundaries were gazetted, ten months before they had legal force. It is useful as a *dataset* version stamp, not as the temporal-model in-force date.
- **District count:** **93** features returned, `totalFeatures: 93`. ✅ Matches the 93-seat Legislative Assembly and s. 1 of the Act exactly.
  - ★ **Counted DISTINCT district IDs, not records** — the federal 45th-GE trap (352 records for 343 districts because islands are separate rows). **BC does not have it:** 93 records / **93 distinct `ELECTORAL_DISTRICT_ID`** / 93 distinct `ED_NAME`, zero duplicates. One row per district in both generations (2015: 87/87/87). No risk of duplicate `constituency_id` on load.
  - ★ **And BC's islands do not fragment the geometry at all, for an interesting reason: these polygons are not land-clipped.** Every one of the 93 features is a **single-ring `Polygon`** — no multipart geometry, no holes, no separate island rows — which looks impossible for a coast like BC's until you notice the areas. Shoelace area computed from the served EPSG:3005 coordinates matches the stated `FEATURE_AREA_SQM` to **0.000% for all 93** (and all 87), and the district areas **sum to 1,039,594 km² against a BC land area of ~944,735 km²**. The excess is marine: electoral boundaries are drawn *across the water*, enclosing islands within one continuous ring rather than clipping to the shoreline. **This is good news for PIP** — there are no offshore gaps, so a coastal or island address always falls inside exactly one district. It also means `area_sqkm` computed from these polygons is *not* a land area and shouldn't be presented as one.
- **Difficulty (1–5):** **1** — documented open-data catalogue, machine-readable CKAN API, standards-compliant WFS with introspectable schema, no auth, no rate limit observed, genuinely open licence. The only friction is that the vector endpoint is not listed in the catalogue record.
- **Notes:** All 93 geometries are `Polygon`, **not** `MultiPolygon` — the build must wrap in `ST_Multi` for the `geometry(MultiPolygon,4326)` column. This is full-resolution geometry (21 MB for 93 features), unlike the Open North `simple_shape` derivative we hold today; the GIST index on `boundary` listed as build prerequisite #2 in [`overview.md`](./overview.md) is genuinely load-bearing here, not an optimisation.
- **★ A second, maintained "current" layer exists — and it makes a free staleness canary.** `WHSE_ADMIN_BOUNDARIES.EBC_PROV_ELECTORAL_DIST_SVW` (catalogue slug `current-provincial-electoral-districts-of-british-columbia`) is a *rolling* current-generation layer. Verified 2026-08-18 to be **byte-equivalent in identity to BS11**: same 93 `ED_NAME` values (exact set equality), same `BOUNDARY_SET_ID = 11`, same `GAZETTE_DATE = 2023-12-07`, same attribute schema.
  - **Build guidance:** pin the load to the **versioned** `BS11` layer, because a rolling layer silently changes vintage underneath a reproducible build.
  - **Monitoring guidance:** poll the **rolling** layer's `BOUNDARY_SET_ID` on a schedule; if it ever returns something other than `11`, a redistribution has landed. That is a single cheap WFS call with `propertyName=BOUNDARY_SET_ID&count=1`. **This is precisely the alarm whose absence produced the current BC situation** — worth generalising to every jurisdiction that publishes a rolling layer.

## Prior boundaries (immediately preceding)

- **Source URL(s):** https://catalogue.data.gov.bc.ca/dataset/provincial-electoral-districts-electoral-boundaries-redistribution-2015 ; https://catalogue.data.gov.bc.ca/dataset/9530a41d-6484-41e5-b694-acb76e212a58/resource/34eedf53-c60b-4237-bf6e-81228a51ab12/download/edsre2015.zip ; https://openmaps.gov.bc.ca/geo/pub/WHSE_ADMIN_BOUNDARIES.EBC_ELECTORAL_DISTS_BS10_SVW/ows?service=WFS&version=2.0.0&request=GetFeature&typeName=pub:WHSE_ADMIN_BOUNDARIES.EBC_ELECTORAL_DISTS_BS10_SVW&outputFormat=application/json&srsName=EPSG:3005
- **Format:** Shapefile (zipped, 6.4 MiB — exactly four members: `.shp` / `.shx` / `.dbf` / `.prj`) **and** GeoJSON via WFS (12.7 MiB). ⚠ **No `.cpg` in any case** — checked case-insensitively (`-iname '*.cpg'`) per the uppercase-`.CPG` trap, and there is genuinely none, so the `.dbf` **encoding is undeclared**. All 87 `ED_NAME` values are pure ASCII (BC has no accented district names in either generation), so nothing mojibakes here — but the build must not *assume* a declared encoding exists, and this file offers no evidence either way. A jurisdiction with accented names and no `.cpg` would be a real hazard. Unlike 2023, this generation *does* offer a direct shapefile and a KMZ in the catalogue record. Both are staged; see `## Staged files` for why.
- **CRS / projection:** **EPSG:3005**, `NAD_1983_BC_Environment_Albers` — verbatim `.prj` WKT identical to the block quoted under `## Current boundaries` (read directly from `edsre2015/edsre2015.prj`).
- **Attribute schema:** parsed from the `.dbf` header (dBase III, `0x03`, 87 records, 289-byte header, 207-byte records) — `ED_ID` (N, 11), `BDYSET_ID` (N, 11), `ED_ABBREV` (C, 3), `ED_NAME` (C, 100), `GAZETTE_DT` (D, 8), `FEAT_AREA` (N, 31.15), `FEAT_PERIM` (N, 31.15), `OBJECTID` (N, 11).
  - ⚠ **The shapefile truncates field names relative to WFS**: `ED_ID`→`ELECTORAL_DISTRICT_ID`, `BDYSET_ID`→`BOUNDARY_SET_ID`, `ED_ABBREV`→`ED_ABBREVIATION`, `GAZETTE_DT`→`GAZETTE_DATE`, `FEAT_AREA`→`FEATURE_AREA_SQM`, `FEAT_PERIM`→`FEATURE_LENGTH_M`. Same data, two names. A loader written against one and pointed at the other silently reads nothing. This is why both formats are staged.
- **District ID field:** `ED_ID` (shapefile) / `ELECTORAL_DISTRICT_ID` (WFS), unique across all 87, scoped to `BDYSET_ID = 10`. ⚠ **The two distributions do not carry the same values — see the off-by-one trap below.** WFS `ELECTORAL_DISTRICT_ID` runs **171–257** (contiguous); shapefile `ED_ID` runs **170–256** (contiguous).
- **⚠★ TRAP — the shapefile and the WFS disagree on the district ID by exactly one, silently.** Verified across all 87 records by decoding the `.dbf` and diffing against the WFS GeoJSON:

  | Relationship | Agreement |
  |---|---|
  | SHP `ED_ID` == WFS `ELECTORAL_DISTRICT_ID` | **0 / 87** |
  | SHP `ED_ID` + 1 == WFS `ELECTORAL_DISTRICT_ID` | **87 / 87** |
  | SHP `OBJECTID` == WFS `ELECTORAL_DISTRICT_ID` | **87 / 87** |
  | `ED_NAME` agrees | 87 / 87 |
  | `ED_ABBREV` / `ED_ABBREVIATION` agrees | 87 / 87 |

  Abbotsford-Mission is `ED_ID = 170, OBJECTID = 171` in the shapefile and `ELECTORAL_DISTRICT_ID = 171` in the WFS. What the shapefile calls `OBJECTID` is what the WFS calls `ELECTORAL_DISTRICT_ID`; the shapefile's own `ED_ID` is one lower throughout.

  **Why this is dangerous rather than merely annoying:** both ID sets are *contiguous and alphabetically ordered*, so an off-by-one does not throw, does not orphan, and does not fail any count check — it maps **every district to its alphabetical neighbour**. Loading the shapefile's `ED_ID` as `authority_district_id` and later joining anything keyed on the WFS value would attach 87 wrong polygons with no error anywhere, which is the same class of silent-wrongness that produced the current 52-row situation.

  **Mitigation:** key on **`ED_NAME`** (87/87 agreement across distributions, and 93/93 against LIMS) and pin `authority_district_id` to a single named distribution — recommend the **WFS** value, since 2023 is only available via WFS and using the same source for both generations keeps the semantics consistent. Record which distribution the ID came from. The 2023 generation is unaffected in practice because no shapefile is published for it in the catalogue, but the same trap would appear the moment someone pulls `outputFormat=SHAPE-ZIP`.
- **Effective date:** **2017-04-11** → `effective_from` for this generation. *Electoral Districts Act*, SBC 2015 c. 39, **s. 6**: "This Act comes into force on the day the 40th Parliament is dissolved" (assented 2015-11-17; 40th Parliament dissolved 2017-04-11 ahead of the 2017-05-09 general election). `needs confirmation` — the dissolution date itself was not read off a primary Elections BC/Legislative Assembly page in this pass; the *supersession* date below was, and is the one the temporal model actually needs.
- **Superseded date:** **2024-09-21** → `effective_to`. Primary and unambiguous: BC Laws' point-in-time record for SBC 2015 c. 39 states the Act was "repealed by 2023-15-5, effective September 21, 2024," which is the same dissolution event that brought the 93-district order into force. The two generations therefore abut exactly with no gap and no overlap — a clean temporal cutover.
- **District count:** **87** features (`totalFeatures: 87`; `.dbf` header independently reports 87 records). ✅ Matches s. 1 of SBC 2015 c. 39 and the seat count used in the 2017 and 2020 general elections.
- **Difficulty (1–5):** **1** — same open catalogue, plus a direct shapefile link in the record.
- **Notes:** `GAZETTE_DATE` is uniformly `2016-12-01` across all 87 features. Geometry type is `Polygon` for all 87 — `ST_Multi` required, same as 2023.

## District ↔ elected official mapping

**★ This is BC's strongest asset and it is already in our schema.** BC needs no name-fuzzing at any layer.

- **Roster source:** LIMS GraphQL, `POST https://api.lims.leg.bc.ca/graphql` (the `dyn.leg.bc.ca` SPA hardcodes this host; `https://lims.leg.bc.ca/graphql` also answers identically — both verified 2026-08-18). No auth, permissive CORS, fully introspectable. Documented in depth in [`../british-columbia.md`](../british-columbia.md) § *Member Data — LIMS GraphQL*.
- **Query:** `{ allConstituencies(first: 200) { totalCount nodes { id name active electoralCode memberId } } }` → `totalCount: 187`, of which **93 `active: true`** and 94 historical.
- **★ Name join is exact, 93/93.** The set of LIMS `active: true` constituency names is **identical** to the set of Elections BC 2023 `ED_NAME` values — verified by set equality, **zero LIMS-only names and zero Elections-BC-only names**. No punctuation drift, no accent drift, no "and"/"&" divergence. This is the cleanest district↔official mapping found in the project so far; the federal set needed apostrophe normalisation and BC needs nothing.
- **Direct MLA edge:** `Constituency.memberId` → `Member.id` → our existing `politicians.lims_member_id` (integer column, migration `0011`, already populated for 376 modern MLAs). So the chain is **`constituency_boundaries` → Elections BC `ED_NAME` → LIMS `Constituency.name` → `Constituency.memberId` → `politicians.lims_member_id`** — one name join and then exact integer FKs the rest of the way. Also available: `memberParliamentsByConstituencyId` and `memberElectionsByConstituencyId` for historical district↔member edges, which would let the *prior* generation be mapped to the MLAs who actually sat in it.
- **LIMS `Constituency.id` is LIMS's own key, not Elections BC's.** Abbotsford-Mission is LIMS `id: 3` and Elections BC `ELECTORAL_DISTRICT_ID: 258`. Do not conflate them. LIMS `id` is stable within LIMS and is a perfectly good join key *to LIMS*; `ELECTORAL_DISTRICT_ID` is the authority key for `authority_district_id`.
- **★ `Constituency.electoralCode` is the Elections BC abbreviation — but only 38/93 populated.** Where present it matches `ED_ABBREVIATION` **exactly: 38 of 38, zero mismatches**. The population pattern is fully explained and is not random: the 38 coded rows are precisely the constituency rows **LIMS created new** for the 2023 redistribution. Of the 41 districts new in 2023, 38 have codes; the 3 that don't (`Bulkley Valley-Stikine`, `Richmond Centre`, `Vancouver-Little Mountain`) are names that existed in earlier BC generations, so LIMS reactivated a pre-existing row instead of creating one. All 52 name-stable districts kept their older, uncoded rows — **0 of 52 carry a code**. Net: `electoralCode` is trustworthy where present but is **not usable as the join key** at 41% coverage. Use `ED_NAME` ↔ `Constituency.name`, which is 100%.

## Postal-code correspondence (if published)

**★★ Yes — and it is the single highest-value find in this dossier.** BC publishes a complete, current, unauthenticated postal-code→electoral-district concordance. X1 found Elections Québec publishes one; **BC's is larger, free, and queryable over an API we already integrate with.**

- **Source:** LIMS GraphQL, same endpoint as the roster. Type `PostalCodeLookup` with fields `postalCode` (String, non-null), `constituencyId` (Int), and the `constituencyByConstituencyId` edge. Query: `{ allPostalCodeLookups(first: N) { totalCount nodes { postalCode constituencyId } } }`.
- **Volume: 164,848 postal codes.** Format is 6-character, no space (`V4X2E6`).
- **★ Coverage is complete and current-generation:** **all 93 active districts have at least one postcode (93/93, none zero)** and **all 94 historical districts have exactly zero**. The table has been maintained through the 2024 redistribution and contains no stale-generation rows. Per-district counts range from 330 (`Nechako Lakes`, sparse rural) to 3,288 (`Kelowna-Lake Country-Coldstream`), which is the expected urban/rural distribution and a good sanity signal that this is real per-postcode data rather than an FSA-level approximation.
- **★ Named resolver also exists.** The SPA bundle carries a `GetMLAName($postalCode)` named GraphQL operation — a first-class postcode→MLA resolver, already noted in [`../british-columbia.md`](../british-columbia.md). So BC offers both the bulk table and a point query.
- **Why this matters beyond BC:** this is an **independent, authoritative cross-check on our point-in-polygon output**. For BC we can compute PIP from the Elections BC polygons and then verify it against 164,848 known-correct answers from the Legislative Assembly's own system. That is a regression-test corpus for the *whole* boundary pipeline, not just BC — if our PIP disagrees with LIMS on BC postcodes, the bug is in the PIP path, not in BC's geometry.
- **⚠ It is a concordance, not geometry, and should not replace the polygons.** Postcodes are delivery routes, not areas; a postcode straddling a boundary gets assigned to one district by whatever rule Elections BC/LIMS applies, and new postcodes appear continuously. Use it to *validate* and as an immediate stopgap, keep polygons as the source of truth.
- **Elections BC does not publish an equivalent** — confirmed dead end, do not re-probe. Its 25-dataset catalogue was enumerated: it has voting-area boundaries, voting-place assignment tables, an `edva-conversion-tables` dataset and an "Electoral District Voting Area to Municipal Boundary Conversion Table", but **no postal-code product of any kind**. The "conversion tables" the Elections BC maps page advertises are voting-area↔voting-place and voting-area↔municipality, not postal.

## Terms / Licensing

**Licence:** **Elections BC Open Data Licence** — https://www.elections.bc.ca/docs/EBC-Open-Data-Licence.pdf (`license_id: 42` in the BC Data Catalogue; attached to every Elections BC boundary dataset checked: 2008, 2015, 2023, and the rolling current layer).

⚠ **Note a correction to the upstream audit.** [`overview.md`](./overview.md) classes BC as Class A "Open Government Licence – British Columbia". The agency-direct licence on all Elections BC spatial data is **not** OGL-BC; it is Elections BC's own instrument. The *conclusion* is unchanged — it is genuinely open and transferable — but the licence name and the required attribution string are different, and the attribution string is the part that has to be exactly right.

Retrieved and read directly from the PDF (no click-through, no gate — it is a plain static PDF at a stable URL). Verbatim, the clauses that govern our use:

> **2.** The Information Provider grants You a worldwide, royalty-free, perpetual, non-exclusive licence to use the Information, including for commercial purposes, subject to the terms below.

> **3.** You are free to copy, modify, publish, translate, adapt, distribute or otherwise use the Information in any medium, mode or format for any lawful purpose.

**Redistribution: ✅ explicitly permitted.** Clause 3 names "publish" and "distribute" outright. This clears `/api/public/v1/boundaries/*` serving BC GeoJSON under permissive CORS — unlike the Class B "distributed with permission" rows (NS, NT) and unlike the GeoNB clause II.5 flow-down, **there is no viral term and no downstream-licensing obligation here.** Nothing needs to be attached to the API response.

**Attribution: ✅ required, and the string is prescribed verbatim.** Clause 4:

> **4.** You must, where You do any of the above, acknowledge the source of the Information by including this attribution statement and, where possible, providing a link to this licence:
>
> **Contains information licenced under the Elections BC Open Data Licence**

(Reproduced with the licence's own British spelling of "licenced" — use it exactly as written.) The "where possible, providing a link to this licence" clause means the attribution should carry the PDF URL.

**Termination is automatic on breach.** Clause 5:

> **5.** The terms of this licence are important, and if You fail to comply with any of them, the rights granted to You under this licence, or any similar licence granted by the Information Provider, end automatically.

Note the reach of "or any similar licence granted by the Information Provider" — a breach on one Elections BC dataset terminates our rights to *all* of them. Getting the attribution string right is therefore not cosmetic.

**Exclusions (clause 6)** carve out Personal Information, records not accessible under FOIPPA, third-party rights, **the names, crests, logos, or other official marks of the Information Provider**, and separately-IP'd information. Practical consequence: we may serve the geometry and attributes freely, but must not put the Elections BC logo or wordmark on anything. **Clause 7** (non-endorsement) forbids using the Information in a way suggesting official status or Elections BC endorsement — relevant to how a "who represents me" result is worded, not to the data itself.

**⚠ Accuracy disclaimer, carried on the dataset records and the Elections BC maps page** (verbatim):

> Elections BC does not warrant or guarantee the accuracy or reliability of spatial data when used in conjunction with other spatial data. The GIS spatial data files should not be used to determine a voter's electoral district or voting area.

This is not a licence restriction and does not block use, but it is directly on point for our product — the agency explicitly disclaims the exact use case our postcode lookup implements. It belongs in user-facing copy on the lookup result, and it strengthens the case for cross-checking PIP against the LIMS postal concordance rather than treating polygon PIP as final.

**LIMS / Legislative Assembly data** (roster + postal concordance) carries **no published licence** — it is an unauthenticated public API of the Legislative Assembly with no terms page found. Crown copyright presumptively applies. We already ingest it heavily for Hansard, bills and votes, so this is not a new exposure, but note it is a *different* and weaker licence position than the Elections BC geometry. See `## Research-handoff items`.

## Rate limits / auth

- **BC Data Catalogue (`catalogue.data.gov.bc.ca`)** — CKAN 3 API, no auth, no key, no rate-limit headers observed. `package_search` and `package_show` both answered immediately.
- **DataBC WFS/WMS (`openmaps.gov.bc.ca`)** — no auth, no key, no rate-limit headers. Served a 21 MB WFS GeoJSON response in one request without throttling or paging. Supports `propertyName=` projection (used here to pull attributes without geometry — cheap enough to poll for the staleness canary) and `count=`/`startIndex=` paging if ever needed. Standards-compliant WFS 2.0.0; `DescribeFeatureType` returns a real XSD, which is why no field name in this dossier is guessed.
- **LIMS GraphQL (`api.lims.leg.bc.ca`)** — no auth, permissive CORS, no documented or observed rate limit. Consistent with the existing dossier's finding of "no WAF observed on `lims.leg.bc.ca` across probe traffic." `api.lims.leg.bc.ca` honours `If-None-Match` with clean 304s. Keep 1–2 s spacing per the existing BC convention.
- **No CAPTCHA, no WAF, no click-through, no registration anywhere in the BC boundary surface.** Nothing was accepted or submitted.
- ⛔ **Open North (`represent.opennorth.ca`) — DOWN**, independently re-confirmed 2026-08-18 during this pass: TLS certificate `CN=represent-tempeh.opennorth.ca` (hostname mismatch), `notAfter=Aug 7 09:51:36 2026 GMT` — **expired**; ignoring TLS, every path returns **HTTP 502**. Matches [`overview.md`](./overview.md) § Known blockers exactly. No BC work depends on it.

## Staged files

Staged under `data/boundaries/british-columbia/`; full table with sha256 in
[`PROVENANCE.md`](../../../data/boundaries/british-columbia/PROVENANCE.md).
**41.9 MB of the 500 MB budget.** Nothing converted, nothing reprojected, nothing loaded;
both GeoJSON files were requested in native EPSG:3005 via `srsName`.

| Generation | File | Bytes |
|---|---|---:|
| current | `current/ebc-electoral-districts-2023-bs11-epsg3005.geojson` | 21,828,718 |
| prior | `prior/edsre2015.zip` (agency-native SHP; carries the `.prj`) | 6,721,791 |
| prior | `prior/ebc-electoral-districts-2015-bs10-epsg3005.geojson` | 13,324,804 |

`prior/edsre2015/` is an unzipped working copy, extracted only to read the `.prj` and
`.dbf` per the no-GDAL procedure — a derivative of the staged zip, freely deletable.

The 2015 set is staged in **both** formats deliberately: the shapefile is the agency-native
artifact and the only thing carrying a `.prj`, but its `.dbf` truncates field names, so the
WFS GeoJSON is staged alongside to make the build symmetric with 2023 and remove any need
for a `.shp` reader (build prerequisite #6 in [`overview.md`](./overview.md) is therefore
**not** blocking for BC).

## Reconciliation with `constituency_boundaries`

**What we hold:** `source_set = 'british-columbia-electoral-districts-2015-redistribution'`,
`constituency_id` prefix identical, **52 rows**, all `level = 'provincial'`,
`boundaries_version = 'current'`, `effective_from = '2023-01-01'`, `effective_to = NULL`
— the hardcoded placeholders noted in [`overview.md`](./overview.md), not real dates.
(BC also holds 12 municipal rows across `census-subdivisions` ×10, `vancouver-wards` ×1,
`langley-wards` ×1 — out of scope for this dossier.)

### ★ What the 52 rows actually are — answered

**They are the exact name-stable intersection of the 2015 and 2023 orders, carrying 2015 geometry.** Not a partial 2015 load, not any real BC redistribution. Four independent lines of evidence:

1. **The count is not a coincidence.** |2015 ∩ 2023| by `ED_NAME` is **exactly 52** (2015-only: 35; 2023-only: 41; 52 + 41 = 93). Computed from the two authoritative files.
2. **Set membership is exact in both directions.** All 52 of our names are in the LIMS active-93 *and* in the 2015 set. **Zero orphans** — nothing we hold is absent from either. The 41 names we're missing are exactly the 41 districts new or renamed in 2023 (`Burnaby Centre`, `Kootenay Central`, `Langford-Highlands`, `Vancouver-Yaletown`, …). We hold **none** of the 35 names that existed only in 2015 (`Chilliwack`, `Nanaimo`, `Vancouver-Mount Pleasant`, …).
3. **The geometry is 2015.** Comparing our stored `area_sqkm` against authoritative `FEATURE_AREA_SQM` for all 52: **51 of 52 match the 2015 shape to within 0.5%**, most to 0.00% (`Abbotsford-Mission` ours 660.2 km² / 2015 660.2 / 2023 88.3; `Fraser-Nicola` ours 34,829.8 / 2015 34,830.4 / 2023 27,818.1). Only 48 vs 4 "closer to 2015" would be weak; **51/52 inside 0.5%** is conclusive. The single outlier is `Peace River North` at 0.56% — a simplification artifact, not a different generation.
4. **35 rows could not have gone missing at random.** If a 2015-vintage load had dropped rows for some ordinary reason, the 35 dropped would be an arbitrary subset. That they are *precisely* the 35 names which do not survive into 2023 has effectively zero probability under any random-loss model. Set membership was determined by the **current** roster; geometry came from the **2015** file.

### Competing explanations, tested and falsified

Three alternative diagnoses were put forward. All three make checkable predictions, and all three fail. Recording them so nobody re-runs the analysis.

| Hypothesis | Prediction if true | Measured | Verdict |
|---|---|---|---|
| **Pagination artefact** (a page-size cutoff truncated the fetch) | our 52 = the alphabetically first 52 of the 87 | our set spans alphabetical positions **0–86, interleaved**; first held `Abbotsford South`, last held `West Vancouver-Sea to Sky`; first missing `Burnaby-Deer Lake`, last missing `Vernon-Monashee`; `held == first52` is **False** | ⛔ **falsified** |
| **Regional roster gap** (Open North's roster missed a region) | held and missing districts occupy disjoint regions | **10 region prefixes appear in *both* sets** — Burnaby, Cariboo, Kamloops, Kelowna, Maple, North, Port, Richmond, Surrey, Vancouver | ⛔ **falsified** |
| **Roster only covered 52 districts at ingest** | we hold ~52 Open-North-sourced BC MLA rows | we hold **93** rows sourced `opennorth:bc-legislature`; the roster was complete | ⛔ **falsified** |
| **Redistribution boundary** (the real one) | all 35 missing absent from the 2023 order; all 52 held present in it | **35/35** and **52/52** | ✅ **confirmed, both directions** |

Worth stating plainly because a pagination artefact *would* have been a significant cross-jurisdiction find: **there is no pagination bug here.** 52 is not a page size, not a round number, and not a prefix of any ordering — it is a fact about the relationship between two redistributions.

### ★ The mechanism — a loader defect, and it is not BC-specific

Read from the code, not inferred:

- `_constituency_id()` (`services/scanner/src/opennorth.py:246`) mints the key by string-splitting **the individual representative's** `related.boundary_url`, and **returns `None` when that field is absent**.
- `_upsert_politician` (`opennorth.py:271`, `299`) writes whatever it gets — `constituency_id = EXCLUDED.constituency_id` — so a `None` lands as a **`NULL` `constituency_id` on the politician row, with no log line**.
- `_ingest_set` fetches a boundary **only inside the per-representative handler**, and the fetch is **guarded on the key existing** — `opennorth.py:590`: `if cid and cid not in seen_ids:`. A `None` key means `_fetch_boundary` is **never called at all**.

**★ The DB settles which failure it was, and it is not the one I first reported.** Measured 2026-08-18 on `politicians` where `is_active AND level='provincial' AND province_territory='BC'`:

| Measure | Count |
|---|---:|
| Rows sourced `opennorth:bc-legislature` | **93** |
| …of which carry a `constituency_id` | **52** |
| …of which carry **no** `constituency_id` | **41** |
| Active BC MLAs whose `constituency_id` resolves to a boundary | 52 |
| **Orphaned — `constituency_id` set but matching no boundary** | **0** |

**Open North's BC roster was complete at 93.** It is not the case that the roster only covered 52 districts, and it is not the case that 41 boundary fetches 404'd. **Zero orphans is the fingerprint that discriminates between them:** a swallowed 404 in `_fetch_boundary` would leave the politician holding a non-NULL `constituency_id` pointing at a boundary that was never written — an orphan. There are none. The 41 have a **`NULL` key**, which can only mean `_constituency_id()` returned `None`, which can only mean the representative record carried **no `related.boundary_url` at all** — Open North does not publish a boundary URL for a district that does not exist in its 2015 set.

So the correct chain is one step earlier than a swallowed 404, and the fetch never happened:

> Open North's BC roster is current (93 MLAs) while its boundary set is still 2015. For the 52 MLAs whose district name survived the redistribution unchanged, `boundary_url` pointed at a 2015 slug that still exists, so a row was written — **with 2015 geometry under a current district name**. For the other 41, the representative record has no `boundary_url`, `_constituency_id()` returned `None`, the politician was written with a **`NULL` `constituency_id`**, and the guard at `opennorth.py:590` skipped the boundary fetch entirely. **Nothing was logged, counted, or raised at any point.**

**★ This means BC's two symptoms have a single root cause.** The 45 unreachable sitting reps and the 52 wrong polygons are not separate problems — the same `None` both nulls the politician's district linkage *and* suppresses the boundary fetch, in the same iteration of the same loop. Corroborated: 46 active BC MLAs have no `constituency_id` (41 Open North + 5 `direct:leg-bc-ca`), all 46 do have a `constituency_name`, and X2 measured 45 unreachable — the one-row difference is the `lower(constituency_name)` fallback rescuing a single rep.

**It generalises, and the generalisation is broader than a 404 would have been.** Any jurisdiction where Open North's roster is fresher than its boundary set loses exactly the renamed districts — silently, on *both* the politician and the boundary side. The damage shape is the important part: not 41 missing polygons at the edges, but **52 confidently-wrong polygons in the middle**, each serving 2015 geometry under a 2023 district name. That is precisely the "confident wrong riding" failure this workstream exists to eliminate, and it is invisible to every count-based check we have.

**★ No longer `UNTESTED`.** My earlier note said the slug-level 404-vs-200 probe was blocked by Open North being down. That probe is now **moot rather than pending** — the orphan count answers the question from our own DB without needing Represent at all, and answers it against the 404 hypothesis. Nothing here depends on Open North returning.

### Re-key

Our `constituency_id` slugs are Open-North-minted kebab-case names. Verified: **all 52 are exactly reproduced by `slugify(ED_NAME)` against the 2015 set, and — because they are the name-stable subset — against the 2023 set too.** So the slug half is deterministically derivable from Elections BC's own `ED_NAME` and no naming convention has to be invented for the 41 new districts. This is the option-(a) trap in [`overview.md`](./overview.md) dissolving for BC specifically: we can mint all 93 keys in the shape we already emit, from the authority's own field, without guessing.

#### ⛔ Prefix ruling A6 — supersedes the recommendation below (added 2026-08-18, after this dossier was first written)

**A `constituency_id` prefix must not encode a generation.** The unique key is
`(constituency_id, boundaries_version)`, so `constituency_id` is generation-independent
*by design* and `boundaries_version` is what carries the generation. Baking a year into
the prefix forces a full `politicians` UPDATE at every redistribution.

**BC is the country's most acute case**, because our prefix
`british-columbia-electoral-districts-2015-redistribution` does not merely encode a
generation — given this dossier's central finding, it encodes the **wrong** one. The
geometry is 2015 but the district names are 2023, so the prefix misdescribes both halves
of what the row actually contains.

- **Target prefix: `british-columbia-electoral-districts/<slug>`** — no year.
- ★ **This makes the cutover strictly cleaner and vindicates the temporal model.** With a
  generation-free prefix the 52 existing rows **keep their `constituency_id` unchanged**,
  take `effective_to = 2024-09-21` and a superseded `boundaries_version`; the 93 new rows
  land under the *same* key space as a second `boundaries_version`. No `politicians`
  UPDATE is needed for the 52 at all. This would be the **first time migration `0021`'s
  temporal machinery is actually exercised**, and BC is the natural place to prove it —
  it is the only jurisdiction where both generations are fully identified and staged.
- ⚠ **The all-93-are-new-inserts conclusion is unchanged and, if anything, reinforced.**
  Keeping the *key* is not keeping the *row*. The 52 old rows keep their identity and are
  closed off with an `effective_to`; the 52 new rows are still fresh inserts carrying
  correct 2023 geometry. Do not let "the key is already right" become "the row is already
  right" — that is exactly the mistake that would preserve every wrong polygon.

Per recommendation (d), the BC cutover is:

- `authority = 'elections-bc'`; `authority_district_id = ELECTORAL_DISTRICT_ID` (as text), scoped by generation.
- ~~`constituency_id` keeps its `{prefix}/{slug}` shape, minted as `slugify(ED_NAME)` — **52 of 93 keys are then byte-identical to what we already hold, and the 41 new ones are pure inserts.** No read path changes for the 52.~~ → **superseded by A6 above:** keep the `{prefix}/{slug}` shape and the `slugify(ED_NAME)` slug, but the prefix drops the `-2015-redistribution` suffix. The 52 keys stay byte-identical *in their slug half*; the prefix change is a one-time rewrite of 52 `constituency_boundaries` rows plus the 52 `politicians` rows pointing at them, done once and never again.
- ⚠ **The 52 existing rows must still be replaced, not left alone.** Their key is (nearly) right and their *geometry is wrong* (2015 shapes under 2023 names). It is tempting to treat matching keys as "already correct" and only insert the 41 — that would leave the confidently-wrong half of the problem in place. **All 93 rows are new-generation inserts.**
- Supersede the existing 52 by renaming their `boundaries_version` off `'current'` **before** inserting, per the mutable-label trap, and set `effective_to = '2024-09-21'`.
- New generation: `boundaries_version` = something durable (e.g. `'bc-2023'` / `BOUNDARY_SET_ID` 11), `effective_from = '2024-09-21'`, `effective_to = NULL`.
- The prior generation can be loaded **complete at 87 rows** from the staged 2015 file, not just the 52 we happen to hold — `effective_from = '2017-04-11'` (`needs confirmation`), `effective_to = '2024-09-21'`.

**Verification available to BC that no other jurisdiction has:** after cutover, run all **164,848** LIMS postcodes through the PIP path and diff against LIMS's own district assignment. Expect near-total agreement; investigate every disagreement as a PIP bug. Post-cutover the 45 unreachable BC reps should go to **0**, and `politicians.constituency_id` can be joined to the new rows through the exact `ED_NAME` ↔ LIMS `Constituency.name` ↔ `lims_member_id` chain.

### ⚠ Three traps for the build

All three are **silent mis-join** hazards: none of them throws, orphans a row, or fails a
count check. They produce a confidently-wrong answer, which is the exact failure class
this workstream exists to remove.

- **Shapefile `ED_ID` is one less than WFS `ELECTORAL_DISTRICT_ID`, 87/87** — full evidence table under `## Prior boundaries`. Because IDs are contiguous and alphabetical, mixing distributions shifts every district onto its neighbour. Pin to one distribution (recommend WFS) and key on `ED_NAME`.

- **`ELECTORAL_DISTRICT_ID` never persists across generations** — 0 of 52 name-stable districts keep their ID. Unique within `BOUNDARY_SET_ID` only. Correct as `authority_district_id` *per generation*; wrong for any temporal join.
- **★ 8 `ED_ABBREVIATION` codes are recycled onto *different* districts.** 54 abbreviations appear in both generations; 46 mean the same district, **8 do not**:

  | Abbrev | 2015 district | 2023 district |
  |---|---|---|
  | `BNE` | Burnaby-Edmonds | Burnaby East |
  | `BNN` | Burnaby North | Burnaby-New Westminster |
  | `CHC` | Chilliwack | Chilliwack-Cultus Lake |
  | `POM` | Port Moody-Coquitlam | Port Moody-Burquitlam |
  | `SHU` | Shuswap | Salmon Arm-Shuswap |
  | `SRC` | Surrey-Cloverdale | Surrey City Centre |
  | `SRG` | Surrey-Green Timbers | Surrey-Guildford |
  | `SUN` | Surrey-Newton | Surrey North |

  `BNN` is the sharpest: **Burnaby North exists in both generations as a district**, but its 2023 abbreviation is `BNO`, and `BNN` was reassigned to Burnaby-New Westminster. Keying on `ED_ABBREVIATION` across generations would silently attach Burnaby North's 2015 polygon to Burnaby-New Westminster's 2023 record — a wrong answer with no error. Separately, 6 of the 52 name-stable districts **changed abbreviation** while keeping their name (`Surrey-Guildford` `SUG`→`SRG`, `Richmond-Queensborough` `RQE`→`RCQ`, `Burnaby North` `BNN`→`BNO`, `Richmond-Steveston` `RST`→`RCS`, `Surrey-Newton` `SUN`→`SRN`, `Surrey-Cloverdale` `SRC`→`SRD`). **Use `ED_ABBREVIATION` only within a generation.**

## Research-handoff items

- **LIMS licence position.** The Elections BC *geometry* is cleanly licensed for redistribution. The **LIMS roster and the 164,848-row postal concordance carry no published licence** — unauthenticated Legislative Assembly APIs with no terms page found. We already redistribute LIMS-derived Hansard, bills and votes, so this is pre-existing rather than new, but if the postal concordance is going to be **served** (as opposed to used internally to validate PIP), that is a new redistribution of a new dataset. Worth a direct ask to the Legislative Assembly's Digital Information Office, which has been responsive per the existing BC dossier. **Recommendation: use it internally as a validation corpus and a stopgap immediately; hold off on serving it until asked.**
- **Attribution string placement.** Clause 4 requires "Contains information licenced under the Elections BC Open Data Licence" (their spelling) with a link to the PDF "where possible" — and clause 5 terminates rights to *all* Elections BC datasets on any breach. Where does this go? The `/api/public/v1/boundaries/*` JSON response, the map footer, and the public docs are three different surfaces with three different answers. This needs an operator decision, and it generalises: every jurisdiction is going to land a differently-worded attribution string, so a per-`source_set` attribution column that read paths can emit is probably the right shape rather than hardcoding per province.
- **Elections BC accuracy disclaimer vs. our product.** The agency states its spatial data "should not be used to determine a voter's electoral district or voting area" — the literal thing our postcode lookup does. Every jurisdiction will have some version of this. Does the operator want a standing disclaimer on lookup results? BC is the right place to settle the wording because it is the jurisdiction where we can actually *measure* our error rate, against the LIMS concordance.
- **2015 `effective_from` needs a primary citation.** `2017-04-11` (dissolution of the 40th Parliament) is inferred from s. 6 of SBC 2015 c. 39 plus the known 2017-05-09 election date; the dissolution date itself was not read off a primary page in this pass. The **supersession** date (`2024-09-21`) *is* primary-sourced from BC Laws and is the one the cutover actually depends on, so this is a low-stakes tidy-up, not a blocker.
- **Generalise the staleness canary — this is the real lesson of BC.** BC's rolling `EBC_PROV_ELECTORAL_DIST_SVW` layer exposes `BOUNDARY_SET_ID`; one cheap WFS call detects the next redistribution the day it lands. **Nothing in our system would currently notice a redistribution at all** — that is why 52 wrong polygons sat unremarked across a general election. Two candidates for the standing check, both cheap: (a) poll each jurisdiction's rolling layer for a version-field change; (b) assert `district_count == seat_count` per jurisdiction on a schedule, which needs no per-jurisdiction integration and would have caught BC (52 ≠ 93), NB, SK, MB, ON and Nunavut simultaneously. **(b) is the higher-leverage one** and pairs naturally with the orphan assertion already listed as build prerequisite #7.
- **Not a blocker, flagged per standing instruction 8:** no fetched page contained text addressed to an AI agent. Nothing anomalous encountered.

## Status

- [x] Current boundaries located and staged (2026-08-18) — 93/93, EPSG:3005, `BS11`
- [x] Prior boundaries located and staged (2026-08-18) — 87/87, EPSG:3005, `BS10`, both SHP and GeoJSON
- [x] Licence cleared for internal use — Elections BC Open Data Licence, clause 2
- [x] Licence cleared for **redistribution** — clause 3 explicit; ✅ no viral flow-down, no downstream-licensing obligation
- [x] Attribution string captured verbatim — placement is a handoff item
- [x] CRS confirmed from `.prj` — EPSG:3005, `NAD_1983_BC_Environment_Albers`; ⚠ **no `AUTHORITY` clause**, EPSG derived by hand from parameters and distinguished from EPSG:3153 by datum
- [x] Attribute schema confirmed from WFS XSD + `.dbf` header (not guessed)
- [x] District ID field identified — `ELECTORAL_DISTRICT_ID`, generation-scoped
- [x] In-force date established from primary legislation — 2024-09-21, both directions; metadata date (2023-12-07) recorded as the noted discrepancy per the A2 ruling
- [x] In-force status established from the **statute**, not from any filename or folder label (A5)
- [x] District ↔ MLA mapping confirmed — LIMS `allConstituencies`, exact 93/93 name join
- [x] **★ Diagnosis of the 52 rows — complete**, four independent evidence lines
- [x] **★ Loader silent-drop mechanism identified in code** — ~~`_fetch_boundary` returns `None` on 404 unlogged~~ → **corrected 2026-08-18**: the roster was complete at 93 and **zero orphans** proves the fetch was never called. `related.boundary_url` absent → `_constituency_id()` returns `None` → politician written with `NULL constituency_id` → guard at `opennorth.py:590` skips the fetch. One root cause for **both** the 45 unreachable reps and the 52 wrong polygons
- [x] **★ Competing diagnoses tested** — pagination artefact, regional roster gap, and "roster only covered 52" all **falsified** with measurements
- [x] **★ Postal-code concordance located** — LIMS `allPostalCodeLookups`, 164,848 codes, 93/93 districts
- [x] **★ Shapefile-vs-WFS off-by-one ID trap identified** — 87/87, silent; key on `ED_NAME`, pin one distribution
- [x] **A4 one-row-per-district check** — 93/93/93 and 87/87/87 distinct IDs, no island fragmentation; polygons are water-extended single rings, area matches stated to 0.000%
- [x] **A4 `.CPG` case-insensitive check** — none present in any case; encoding undeclared, all names pure ASCII
- [x] Elections BC postal-code product — confirmed **does not exist** (25-dataset catalogue enumerated); do not re-probe
- [x] ~~Open North 404-vs-200 slug confirmation~~ — **moot, not blocked.** The orphan count answers it from our own DB and answers *against* the 404 hypothesis; nothing depends on Represent returning
- [ ] LIMS licence position for the postal concordance — **research-handoff item**
- [ ] 2015 `effective_from` primary citation — `needs confirmation`, low stakes
- [x] **⛔ A6 prefix ruling applied** — target `british-columbia-electoral-districts/<slug>` (no year). BC is the acute case: the current prefix encodes the **wrong** generation. Prior recommendation struck through, not deleted
- [ ] Build-phase cutover (all 93 as new-generation inserts; the existing 52 carry wrong geometry and must be replaced, not kept) — ★ candidate for the **first real exercise of the `boundaries_version` temporal model**
