# Yukon — Electoral Boundary Research

> Standalone boundary/roster dossier for Yukon. Cross-cutting context
> (methodology, licence matrix, reconciliation strategy) lives in [`overview.md`](./overview.md).
> The legislative-data dossier for this jurisdiction is at [`../yukon.md`](../yukon.md).

**Agency:** Elections Yukon | **Website:** https://electionsyukon.ca | **Districts (current):** 21 | **Current order:** Electoral District Boundaries Act, S.Y. 2024, c. 14 (assented 2024-11-21) | **Next redistribution:** Electoral District Boundaries Commission struck after every second general election — next commission expected after the 2029 general election

**Status snapshot (2026-08-18):** ✅ **Cracked, and cheaply.** ★ Yukon publishes its electoral districts as a plain shapefile on an open directory listing — `map-data.service.yukon.ca` — with **no WAF, no licence gate, no account**, alongside a live CKAN API at `open.yukon.ca/api/3` and two ArcGIS REST services. **Difficulty 1.** ⚠ **This is the opposite of the legislative surface:** `electionsyukon.ca`, `yukonassembly.ca`, and even `yukon.ca` are Cloudflare-challenged (403 to every server-side fetch), which is why [`../yukon.md`](../yukon.md) rates YT at difficulty 5 — the *boundary* path routes around that entirely. ★ **Seat-count discrepancy RESOLVED in favour of `jurisdiction_sources`:** Yukon went **19 → 21** seats; our `seats = 21` is correct and the "19 members" figure is stale. ⛔ **Our 19 held boundary rows are a full generation out of date** — they are the superseded 2015 set, and 6 of the 21 current districts have no polygon at all. ⛔ **The prior (2015) generation is unrecoverable from any authoritative source** — GeoYukon overwrote the layer in place and the `open.canada.ca` mirrors were delisted; our Open North rows are now the only copy anywhere. ⛔ **One thing blocks the build: the 2025 dissolution date.** The Act comes into force on dissolution, not assent, and every source that states the date is Cloudflare-403 — so the new generation's `effective_from` is bounded (2024-11-21 < d < 2025-11-03) but not pinned. ★ The *prior* generation's date **is** pinned to the day — **2016-10-07**, Commissioner's Order 2016/01, from the CEO's own report, retrieved through the one unblocked route. ⚠ The YT roster is a stale/current blend — **33 rows flagged `is_active` against 21 seats**.

---

## ★ Seat-count discrepancy: resolved

The task brief flagged a conflict — `jurisdiction_sources.seats = 21` for YT, against an
Assembly said to have 19 members and 19 boundary rows held. **`jurisdiction_sources` is right.**

- The **Electoral District Boundaries Commission** was appointed 2023-12-14, issued an interim
  report in May 2024, and tabled its **final report on 2024-10-09**. It recommended increasing
  from **19 to 21** districts — **13 in Whitehorse, 8 rural** — both new seats in Whitehorse,
  driven by population growth.
- The Legislative Assembly adopted it as **Bill No. 45**. The **Electoral District Boundaries Act,
  S.Y. 2024, c. 14** was **assented to on 2024-11-21**.
- ⚠ **Assent did not change the map.** The Act's coming-into-force is tied to dissolution, and
  Elections Yukon stated the position explicitly: *"Until the next territorial election is called,
  and the Legislative Assembly dissolved, the current 19 electoral districts, and the 19 Members
  of the Legislative Assembly remain unchanged. When the next election is called, nominations
  will open for the 21 electoral districts."* So between 2024-11-21 and dissolution, Yukon still
  had 19 districts.
- The **2025 Yukon general election (2025-11-03)** was the first contested on the 21-district map,
  electing the **36th Legislature** — 21 seats.

**So: the correct current figure is 21.** It became 21 on the dissolution of the 35th Legislative
Assembly in autumn 2025 (see `effective_from` below — the exact day is `needs confirmation`, but
it is unambiguously before the 2025-11-03 polling day and after the 2024-11-21 assent). The "19"
in the brief is the pre-2025 count. **`jurisdiction_sources.seats = 21` is correct as it stands —
no correction needed.** If the row is edited for any other reason, leave `seats` at 21.

**Corroborating evidence from our own DB, found before the web confirmed it:** the `politicians`
table already contains a 2025-cohort of YT members sitting for districts that do not exist in the
2015 set — `Whistle Bend South`, `Southern Lakes`, `Marsh Lake-Mount Lorne-Golden Horn`. The
roster ingested the new map; the boundary table never did.

## Current boundaries

- **Source URL(s):** https://map-data.service.yukon.ca/GeoYukon/Administrative_Boundaries/Yukon_Electoral_Districts/Yukon_Electoral_Districts.shp.zip ; https://map-data.service.yukon.ca/GeoYukon/Administrative_Boundaries/Yukon_Electoral_Districts/Yukon_Electoral_Districts.kmz.zip ; https://map-data.service.yukon.ca/GeoYukon/Administrative_Boundaries/Yukon_Electoral_Districts/Yukon_Electoral_Districts.fgdb.zip ; https://mapservices.gov.yk.ca/arcgis/rest/services/GeoYukon/GY_AdministrativeBoundaries/MapServer/75 ; https://services.arcgis.com/bwohQix8s7zRvYC9/arcgis/rest/services/Approved_Yukon_Electoral_Districts_2024/FeatureServer/0 ; https://open.yukon.ca/api/3/action/package_show?id=yukon-electoral-districts
- **Format:** Shapefile (zipped, 132 KB), KMZ (zipped, 174 KB), and File Geodatabase (zipped, 132 KB) from the GeoYukon directory listing; ArcGIS REST (JSON / geoJSON / PBF) from two independent services. GeoJSON export confirmed working and complete.
- **CRS / projection:** **EPSG:3578** — `.prj` reads verbatim `PROJCS["NAD_1983_Yukon_Albers",GEOGCS["GCS_North_American_1983",DATUM["D_North_American_1983",SPHEROID["GRS_1980",6378137.0,298.257222101]],PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]],PROJECTION["Albers"],PARAMETER["False_Easting",500000.0],PARAMETER["False_Northing",500000.0],PARAMETER["Central_Meridian",-132.5],PARAMETER["Standard_Parallel_1",61.66666666666666],PARAMETER["Standard_Parallel_2",68.0],PARAMETER["Latitude_Of_Origin",59.0],UNIT["Meter",1.0]]`. ⚠ The ESRI WKT carries **no `AUTHORITY` node**, so the EPSG code must be assigned by parameter match, not read. The parameters match `EPSG:3578` (`NAD83 / Yukon Albers`) exactly. **Do not use 3579** (`NAD83(CSRS) / Yukon Albers`) — the datum in the `.prj` is plain `D_North_American_1983`, not CSRS. Both SRIDs are already present in our `spatial_ref_sys`, so `ST_Transform(geom, 4326)` from 3578 works with no `spatial_ref_sys` insert.
- **Attribute schema:** from the `.dbf` header of **the specific file recommended below** (`Yukon_Electoral_Districts.dbf`, dBase III, 21 records, 2 fields) — `ELECT_NAME` (`C`, len 50) English district name; `FR_ELECNAM` (`C`, len 50) French district name. ⚠ **The three publications use three different field-name sets for the same two columns:** GeoYukon's shapefile says `ELECT_NAME` / `FR_ELECNAM`; the GeoYukon REST layer says `ELECTORAL_DISTRICT_NAME` / `FR_ELECTORAL_DISTRICT_NAME` (plus `OBJECTID`, `SHAPE.AREA`, `SHAPE.LEN`); the Elections Yukon AGOL copy says `ELECTORAL_` / `FR_ELECTOR` (plus `FID`, `Shape_Leng`, `Shape_Area`, `Shape__Area`, `Shape__Length`). Code against the file you actually load, not a generic schema.
- ⓘ **`.cpg` check:** Yukon's is **lowercase** `.cpg` and declares `UTF-8`. No accented characters appear in the 21 English names, so the mojibake risk that bit the NWT file does not arise here — but glob case-insensitively anyway, since the two territories differ on this within the same research pass.
- **District ID field:** ⚠ **There is none.** No code, no number, no stable key — across all three publications the only identifying attribute is the district *name*. `OBJECTID` / `FID` are ArcGIS row ordinals and are not stable across republication. The build phase must **derive the key by slugifying `ELECT_NAME`**, which is exactly what our existing `constituency_id` convention already does.
- ✅ **One row per district — no duplicate-`constituency_id` risk.** Checked explicitly rather than assumed: **21 records → 21 distinct `ELECT_NAME` values → 21 distinct slugs**, zero duplicates. The `.shp` header declares shape type 5 (Polygon) with 21 geometry records and ⓘ **max parts = 1** — every Yukon district is a single simple polygon, no islands, no holes. Yukon is the easy case here; contrast NWT, where four districts carry up to 20 parts each.
- **Effective date → `effective_from` = the dissolution of the 35th Legislative Assembly, autumn 2025.** ⚠ **`needs confirmation` on the exact day.** This is the **legal in-force date** per the ruling: S.Y. 2024, c. 14 comes into force on dissolution, not on assent (see the seat-count section for Elections Yukon's verbatim statement). Bounds are firm — after **2024-11-21** (assent) and before **2025-11-03** (polling day). The 2016 precedent is a strong indicator of the shape: Commissioner's Order 2016/01 dissolved the 33rd Assembly **31 days** before that polling day, which would put 2025 dissolution in the first week of October. **I have not converted that into a date, because it is arithmetic on a precedent, not a record.**
  - **Why it could not be pinned:** the primary sources are all Cloudflare-blocked — `yukon.ca/en/dissolution-legislative-assembly-2025` (403), `electionsyukon.ca` (403), `laws.yukon.ca` (403), `yukonassembly.ca` Bill 45 PDF (403). The Chief Electoral Officer's report archive on `open.yukon.ca` **does** come through the unblocked API but its most recent volume is the 2021 general election — no 2025 report is published yet. A human with a browser resolves this in one page load; see handoff items.
  - ⚠ **Competing dates, recorded as required — do not use these:** **assent, 2024-11-21** (the Act's own date, and the date stamped on the CEO's official map issue — *"Official Electoral Districts of the Yukon, dated November 21, 2024"*), and the **AGOL layer modification date**. Using assent would wrongly return the 21-district map for the ~11 months in 2024–25 when Yukon demonstrably still had 19 districts and 19 sitting members. That is the identical failure mode the federal agent found, at almost identical magnitude.
- **District count:** **21**, and it matches the seat count of the 36th Legislature exactly.
- ✅ **GeoJSON vs shapefile: verified identical, and the GeoJSON is the recommended input.** Checked before preferring it, per instruction. Both carry **21 features**, and the district-name sets are **byte-identical** (`set(shp) == set(geojson)` → `True`), as are the slug sets — despite the two files coming from *different publishers* (GeoYukon vs Elections Yukon's own AGOL org), which makes the agreement a genuine cross-check rather than a tautology. Geometry was spot-checked by computing geodesic area on the GeoJSON in PostGIS against what we hold: the districts that the 2024 order did **not** redraw come out near-exact — `Vuntut Gwitchin` **0.00%**, `Klondike` **+0.06%**, `Riverdale North` **−0.38%**, `Riverdale South` **+0.66%**. ★ That is a useful double result: it confirms the GeoJSON is faithful, *and* it confirms that the large disagreements elsewhere (e.g. `Porter Creek South` 4.7 → 209.8 km²) are **real boundary changes from the redistribution, not data errors**. **Prefer the GeoJSON** — it is already EPSG:4326 and skips the reprojection step. Keep the shapefile as the durable archive copy and as the native-CRS reference.
- **Difficulty (1–5):** **1** — open directory listing plus a documented CKAN API plus two ArcGIS REST services, no auth anywhere.
- **Notes:** The AGOL item metadata gives the authoritative provenance string verbatim: *"Official Electoral Districts of the Yukon, dated November 21, 2024, issued under the authority of the Chief Electoral Officer."* `accessInformation` is *"Government of Yukon on behalf of Elections Yukon"*. The GeoYukon dataset description records the lineage: boundaries were built *"by interpreting the 2008 Electoral District boundaries (amended in July 2015), and updating/modifying the boundaries to account for population growth and distribution, as of 2024"*, aligned to NRCan CanVec 1:50 000 and the National Road Network — so the 2024 linework is a **descendant of**, not independent of, the 2015 linework. Unchanged districts should therefore be geometrically near-identical to what we hold, which makes the diff a useful validation signal during the build.
- **Bonus layer:** polling divisions are published on the same pattern at `https://map-data.service.yukon.ca/GeoYukon/Administrative_Boundaries/Yukon_Polling_Divisions/` (CKAN id `yukon-electoral-polling-divisions`, ArcGIS `MapServer/74`). Not staged — out of scope for `constituency_boundaries`, but it is the obvious sub-district layer if we ever want one.

## Prior boundaries (immediately preceding)

- **Source URL(s):** ⛔ **None live.** Dead ends, all confirmed 2026-08-18, recorded so nobody re-probes them: `https://mapservices.gov.yk.ca/arcgis/rest/services/GeoYukon/GY_AdministrativeBoundaries/MapServer/12` (was "Electoral Districts (2015)"; now HTTP 500 `{"error":{"code":500,"message":"json"}}` — the layer is gone and the group layer `MapServer/10` lists only 74 and 75); `https://open.canada.ca/data/en/dataset/503fdbfe-ea12-c40f-e7e2-b597bacef562` ("Yukon Electoral Districts 2015" — HTTP 404, delisted); `https://open.canada.ca/data/en/dataset/0b50b49e-aadc-24c4-ec85-148df785fe5e` ("Yukon Electoral Districts 2008" — HTTP 404, delisted); `https://hub.arcgis.com/api/v3/datasets/yukon::yukon-electoral-districts-2015` (HTTP 403); `open.yukon.ca` CKAN (`package_search?q=electoral` returns 6 datasets, none historical).
- **Format:** ⛔ Unavailable. The only surviving artifacts are the **19 rows we already hold**, mirrored from Open North, and paper/PDF maps behind the Cloudflare wall on `electionsyukon.ca`.
- **CRS / projection:** n/a — nothing to read. Our held rows are already EPSG:4326.
- **Attribute schema:** n/a. Our held rows carry `constituency_id` + `name` only.
- **District ID field:** n/a. Our slugs are `yukon-electoral-districts-2015/<slug>`.
- **Effective date → `effective_from` = `2016-10-07`.** ★ **Pinned to the day, from a primary source.** Statutory instrument: Electoral District Boundaries Act, **S.Y. 2008, c. 14**, as amended by **S.Y. 2015, c. 11**; in force on dissolution, same mechanism as the 2024 Act. The Chief Electoral Officer's own report on the 2016 general election records the dissolution verbatim: *"The election commenced on Friday, October 7, 2016. On that date, Commissioner's Order 2016/01 dissolved the 33rd Legislative Assembly and Order 2016/02 directed the Chief Electoral Officer to issue Writs of Election to Returning Officers in each of the **19** electoral districts of Yukon."* ✅ That single sentence supplies the legal date, the instrument number, and independent confirmation of the 19-district count. Retrieved from the CEO report archive via the unblocked `open.yukon.ca` CKAN API — the one route around the Cloudflare wall.
  - ⚠ **Competing dates, recorded as required — do not use these:** the **July 2015** amendment date (S.Y. 2015, c. 11), which is what GeoYukon's lineage note cites and what our `source_set` is named after, and the **2016-11-07** polling day. The amendment predates the legal in-force date by ~15 months; the polling day postdates it by 31 days.
- **Superseded date → `effective_to` = the 2025 dissolution**, i.e. the same value as the current generation's `effective_from`, so the two abut with no gap and no overlap. ⚠ Inherits the same **`needs confirmation`** on the exact day.
- **District count:** **19**, matching the seat count of the 33rd–35th Legislatures.
- **Difficulty (1–5):** **5** — blocked/unavailable. Not a scraping problem; the data was withdrawn.
- **Notes:** ★ **This is a preservation finding, not just a gap.** GeoYukon republishes the electoral-districts layer **in place** rather than versioning it, and the federal mirrors that would have caught the old vintage were delisted when Yukon migrated off `data.gov.yk.ca` to `open.yukon.ca`. The 19 rows sitting in our `constituency_boundaries` today are, as far as this pass could determine, **the only machine-readable copy of the 2015 Yukon map in public circulation**. ⚠ **Do not delete or overwrite them during the re-key** — retire them by setting `effective_to`, per the temporal design the table already has. The same overwrite-in-place risk applies to the 2024 layer going forward: whatever we ingest now should be treated as our own archive copy.

## District ↔ elected official mapping

- **Roster source:** ⛔ `https://yukonassembly.ca/mlas` is Cloudflare-challenged (the standing YT blocker in [`../yukon.md`](../yukon.md)); `electionsyukon.ca` returns HTTP 403 to server-side fetches as well. There is **no unblocked roster endpoint** — the boundary win does not extend to the roster.
- **Join key:** district name → slug. Same derivation as the boundary key, so once both sides are slugified the join is exact. There is **no `politicians.yt_mla_slug` column** (convention #1 in `CLAUDE.md` is unmet for Yukon — `nt_mla_slug` exists, `yt_*` does not).
- **Current state of our roster:** ⚠ **33 rows are `is_active` for YT against 21 seats.** The table holds two overlapping cohorts and neither has been reconciled against the 2025 election:
  - **19 rows** carry a `constituency_id` — all of them pointing at `yukon-electoral-districts-2015/*`. These are the **2021 cohort**. Several are members who did not return in 2025 (e.g. `Sandy Silver` / Klondike, `Jeanie McLean` / Mountainview, `Richard Mostyn` / Whitehorse West) yet are still flagged active. 4 of them sit in districts that **no longer exist**: `Mount Lorne-Southern Lakes`, `Pelly-Nisutlin`, `Takhini-Kopper King`, `Watson Lake`.
  - **13 rows** carry a `constituency_name` but a **NULL `constituency_id`** — the **2025 cohort** (`Brent McDonald`, `Jen Gehmair`, `Cory Bellmore`, `Linda Moen`, `Ted Laking`, `Doris Anderson`, `Adam Gerle`, `Carmen Gustafson`, `Justin Ziegler`, `Tyler Porter`, `Debra-Leigh Reti`, `Linda Benoit`, `Laura Lang`). They are NULL because **there was no boundary row to point at** — the FK target does not exist yet.
  - **1 row** has no constituency at all (`Pat Duncan`).
- **Attribution rate:** 19/33 active rows = **58%**, which is the 59% the brief cites. ★ **That number is misleading and the boundary load fixes most of it mechanically:** the 13 NULLs are not a name-matching failure, they are a missing-polygon failure. Loading the 21-district set and re-running attribution should take YT to ~100% of the *real* roster in one pass — the residual work is end-dating the 2021 cohort, not fuzzy-matching names.
- **Coverage against the new map:** 18 of 21 districts have at least one active MLA row. **3 have none** — `Takhini`, `Watson Lake - Ross River - Faro`, `Whistle Bend North` — so the 2025 roster ingest was itself incomplete, independent of the boundary problem.
- **Difficulty (1–5):** **5** for a fresh roster scrape (Cloudflare); **1** for the FK repair, which is pure SQL against data we already hold.

## Postal-code correspondence (if published)

- **Published correspondence file:** ⛔ None. Elections Yukon publishes **no** postal-code → district table, and no forward-sortation-area correspondence.
- **What exists instead:** an address-level lookup web app — `https://yukon.maps.arcgis.com/apps/instant/lookup/index.html?appid=cf83d958791142d381396347c04f69cb` ("Yukon Electoral District and Polling Division Search"), backed by the same `MapServer/74`/`75` layers we are already ingesting. It resolves a **civic address**, not a postal code.
- **Assessment:** ✅ **No gap for us.** Yukon has ~35,600 registered voters and a handful of FSAs (`Y0A`, `Y0B`, `Y1A`), so postal-code granularity is coarse to the point of uselessness in Whitehorse — several of the 13 Whitehorse districts share one FSA. Our existing point-in-polygon path through `public.postcode_cache` + Open North centroids is the right mechanism and needs nothing Yukon-specific. ⚠ But note the accuracy ceiling: a `Y1A` centroid cannot distinguish `Porter Creek North` from `Whistle Bend South`. Whitehorse lookups should be treated as low-confidence unless the user supplies a full 6-character postcode.

## Terms / Licensing

- **Licence:** **Open Government Licence – Yukon**, licence id `OGL-Yukon-2.0` as returned by the CKAN API on both electoral datasets.
- **Licence URL:** https://yukon.ca/en/your-government/open-government/open-government-licence-yukon (also cited by the AGOL item as https://open.yukon.ca/data/open-government-licence-yukon)
- **Verbatim clause quote:** ⛔ **Could not be captured.** Both licence URLs sit behind Cloudflare and return **HTTP 403** with the interstitial body `Just a moment... Enable JavaScript and cookies to continue` to every server-side fetch attempted (plain `curl`, `curl` with a realistic browser UA, and `WebFetch`). The licence *identity* is machine-confirmed from the CKAN metadata — `license_title: "Open Government Licence - Yukon"`, `license_id: "OGL-Yukon-2.0"`, `license_url: "https://yukon.ca/..."` — but the redistribution and attribution clauses were **not read** and are therefore **not quoted here**. Raised as a handoff item; see below.
- **Attribution actually asserted by the data:** the AGOL `licenseInfo` field reads verbatim `Open Government Licence - Yukon (https://open.yukon.ca/data/open-government-licence-yukon)`, and `copyrightText` on the GeoYukon REST layer reads verbatim `Government of Yukon on behalf of Elections Yukon`. Those two strings are the safe attribution to carry forward regardless of what the licence body says.
- **No click-through anywhere.** ✅ Every file listed above downloads with a bare GET. No account, no checkbox, no agreement form was encountered at any point in this pass.

## Rate limits / auth

- **Auth:** none, on any boundary endpoint.
- **Rate limits:** none observed or documented. 8 requests across `map-data.service.yukon.ca`, `mapservices.gov.yk.ca`, `services.arcgis.com`, and `open.yukon.ca/api/3` in a few minutes drew no throttling, no `Retry-After`, no 429.
- **maxRecordCount:** `1000` on the GeoYukon REST layer, `2000` on the Elections Yukon AGOL layer. Both far exceed 21 features — a single unpaged `where=1=1` query returns the complete set with `exceededTransferLimit` absent. No pagination needed.
- ⚠ **Cloudflare split — the single most important operational fact in this dossier.** The *data* hosts are wide open; the *web* hosts are not:
  | Host | Server-side fetch |
  |---|---|
  | `map-data.service.yukon.ca` | ✅ 200 |
  | `mapservices.gov.yk.ca` | ✅ 200 |
  | `services.arcgis.com` (Elections Yukon AGOL) | ✅ 200 |
  | `open.yukon.ca/api/3/*` (CKAN API) | ✅ 200 |
  | `open.yukon.ca/data/*` (CKAN **web pages**) | ⛔ 403 Cloudflare |
  | `electionsyukon.ca` | ⛔ 403 Cloudflare |
  | `yukon.ca` | ⛔ 403 Cloudflare |
  Note the split *within* `open.yukon.ca`: the JSON API answers, the HTML pages do not. Any Yukon tooling should be pointed at `/api/3/` exclusively.
- ⚠ **Trap — the CKAN "All resource data" ZIP is a stub.** `https://open.yukon.ca/data/279a74bd-7578-4d03-a09c-90ae9b7000b3/resource/5583638f-6a8e-465d-a577-38764ce9048b/download/yukon-electoral-districts-aatjwnxi.zip` returns **HTTP 200, `Content-Type: application/zip`, `Content-Length: 832`** — 832 bytes, not a shapefile. It looks like a valid download and is not. Use the `map-data.service.yukon.ca` path.

## Staged files

Staging root `data/boundaries/yukon/`, manifest at `data/boundaries/yukon/PROVENANCE.md`. **596 KB total**, all under the 500 MB budget with room to spare. `current` only — `prior` is empty and will stay empty (see above).

| Path | Bytes | What it is |
|---|---:|---|
| `current/Approved_Yukon_Electoral_Districts_2024.geojson` | 290,264 | ★ **Recommended build input.** Elections Yukon AGOL export, already EPSG:4326, 21 features. Verified identical to the shapefile on count, names and geometry. |
| `current/Yukon_Electoral_Districts.shp.zip` | 132,056 | **Durable archive copy + native-CRS reference.** EPSG:3578, 21 features, from GeoYukon — the CEO's 2024-11-21 issue. Bundles a `disclaimer.pdf` dated 2014-06-05. |
| `current/Yukon_Electoral_Districts.kmz.zip` | 173,925 | KMZ of the same layer. Convenience/QA only. |

**Not staged, deliberately:** the FGDB (`Yukon_Electoral_Districts.fgdb.zip`, 132,476 B) — same content, and we have no GDAL to read it; the polling-divisions layer — out of scope.

## Reconciliation with `constituency_boundaries`

**What we hold today:**

| | |
|---|---|
| `source_set` | `yukon-electoral-districts-2015` |
| `constituency_id` prefix | ~~`yukon-electoral-districts-2015/`~~ → **`yukon-electoral-districts/`** (⛔ ruling A6, see below) |
| Rows | **19** |
| `level` | `provincial` |
| `province_territory` | `YT` |
| `boundaries_version` | `current` (on all 19 — ⚠ now factually wrong) |
| `effective_from` | `2023-01-01` (on all 19 — ⚠ an Open North mirroring artifact, not a legal date; the 2015 order predates it by 8 years) |
| `effective_to` | `NULL` (on all 19 — ⚠ these are superseded and should not be open-ended) |

**Match rate against the authoritative 21:** **15 of 21 (71%)** on slugified name.

- **15 exact slug matches** — `copperbelt-north`, `copperbelt-south`, `klondike`, `kluane`, `lake-laberge`, `mayo-tatchun`, `mountainview`, `porter-creek-centre`, `porter-creek-north`, `porter-creek-south`, `riverdale-north`, `riverdale-south`, `vuntut-gwitchin`, `whitehorse-centre`, `whitehorse-west`. ⚠ One of these differs in **display name** only: authoritative `Mayo - Tatchun` vs held `Mayo-Tatchun` (spaced hyphen). Same slug, so the key survives; the `name` column should be refreshed to the authoritative spelling.
- **6 authoritative districts have no held row** — `marsh-lake-mount-lorne-golden-horn`, `southern-lakes`, `takhini`, `watson-lake-ross-river-faro`, `whistle-bend-north`, `whistle-bend-south`. Two are genuinely new (the Whistle Bend pair); four are renames/resplits of retired districts.
- **4 held rows have no authoritative counterpart** — `Mount Lorne-Southern Lakes`, `Pelly-Nisutlin`, `Takhini-Kopper King`, `Watson Lake`. All four were dissolved or renamed by the 2024 order.

### ⛔ Ruling A6 — our `constituency_id` prefix encodes a generation, and must not

`yukon-electoral-districts-**2015**/` bakes the vintage into the identity. The unique key is
`(constituency_id, boundaries_version)`, so `constituency_id` is generation-independent by
design and `boundaries_version` is what carries the vintage. **Target prefix:
`yukon-electoral-districts/<slug>`.** Superseded reading struck through above rather than
deleted.

★ **A6 makes the Yukon build materially cheaper, and it changes my earlier recommendation.**
I originally called for a full re-key under a new `source_set = 'yukon-electoral-districts-2024'`.
Under A6 that is exactly the wrong move — it would encode `2024` in the identity and repeat
the violation one generation later. With a generation-free prefix, the 15 name-stable
districts **keep their `constituency_id`** and simply gain a second row at a new
`boundaries_version`, which the unique constraint explicitly permits. The re-key shrinks from
21 rows to a one-time prefix rename of the 19 we hold.

**Revised build shape:**

1. **Re-prefix the 19 held rows** from `yukon-electoral-districts-2015/<slug>` to `yukon-electoral-districts/<slug>`, and set `boundaries_version = '2015'` (currently the inaccurate `'current'`). One `UPDATE`; the unique constraint is satisfied because the version changes with it.
2. **Retire, do not delete**, the 19: set `effective_to = <2025 dissolution date>`. ⚠ Per the preservation finding above, these rows are the last public copy of the 2015 map — dropping them destroys data that cannot be re-fetched.
3. **Insert 21 rows** from the staged **GeoJSON** (already EPSG:4326) at `constituency_id = 'yukon-electoral-districts/<slug-of-ELECT_NAME>'`, `boundaries_version = '2024'`, `effective_from = <2025 dissolution date>`, `effective_to = NULL`. For the 15 name-stable districts this is a second row against an existing `constituency_id` — intended, and the temporal columns disambiguate. For the 6 new districts it is a genuinely new `constituency_id`.
4. The 4 dissolved districts (`mount-lorne-southern-lakes`, `pelly-nisutlin`, `takhini-kopper-king`, `watson-lake`) simply never get a `'2024'` row. They stay queryable for historical dates and fall out of current-date queries via `effective_to`. No deletion, no tombstone needed.
5. Correct the bogus `effective_from = '2023-01-01'` on the retired rows to **`2016-10-07`** — the legal in-force date, pinned from the CEO's 2016 report.
6. Re-run FK attribution. The 13 NULL-`constituency_id` 2025-cohort MLAs should resolve on the slug join with no fuzzy matching. `Marsh Lake-Mount Lorne-Golden Horn` in `politicians.constituency_name` slugifies to `marsh-lake-mount-lorne-golden-horn`, identical to the authoritative `Marsh Lake - Mount Lorne - Golden Horn` — ✅ the spacing difference is absorbed by slugification, confirmed by running it.
7. ⛔ **Steps 2 and 3 are blocked on one unknown date.** Do not substitute the assent date (2024-11-21) as a placeholder — that silently asserts the 21-district map governed 11 months during which Yukon had 19 members. If the build must proceed before the date is confirmed, use `2025-11-03` (polling day) as the deliberately-conservative stand-in and leave a `TODO` — it errs by at most ~30 days and never claims coverage the map did not have.

**~~Naming note~~ — superseded by A6.** ~~The source is legally the *2024* Act even though the
map first governed in *2025*; `yukon-electoral-districts-2024` matches the Act, `...-2025`
matches the election, pick one.~~ Moot: under A6 no year belongs in `constituency_id` at all.
The 2024-vs-2025 question survives only as the value of `boundaries_version`, where it is
cosmetic — **recommend `'2024'`**, matching the statute and the CEO's map issue date.

**Unique-constraint note:** `constituency_boundaries` is unique on `(constituency_id, boundaries_version)`. ⚠ Under A6 this constraint becomes **load-bearing rather than incidental**: the 15 name-stable districts will hold two rows sharing one `constituency_id` (e.g. `yukon-electoral-districts/klondike` at `'2015'` and at `'2024'`), and only `boundaries_version` keeps them distinct. Step 1 must therefore set `boundaries_version = '2015'` **in the same statement** as the prefix rename — renaming the prefix first while all 19 still read `'current'` would collide with the new rows on insert. ✅ Verified against the live schema: `constituency_boundaries_id_version_key UNIQUE (constituency_id, boundaries_version)`.

## Municipal wards

**Whitehorse:** no ward boundaries exist — the mayor and six councillors are elected **at large**. There is nothing to ingest, and our zero municipal rows for YT are correct rather than a gap. (Out of scope per brief; one line only.)

## Research-handoff items

- **⛔ One date is blocking the Yukon build: when was the 35th Legislative Assembly dissolved in 2025?** Everything else here is settled. The Act comes into force on dissolution, so that date is both the new generation's `effective_from` and the old generation's `effective_to`. Every primary source that would state it is behind Cloudflare — `yukon.ca/en/dissolution-legislative-assembly-2025`, `electionsyukon.ca`, `laws.yukon.ca`, and the Bill 45 PDF on `yukonassembly.ca`, all 403 — and the CEO report archive that *is* reachable stops at 2021. **A human opening `yukon.ca/en/dissolution-legislative-assembly-2025` in a browser resolves this in one page load**; the Commissioner's Order number and date will be on it, in the same form as Order 2016/01. Bounds meanwhile: after 2024-11-21, before 2025-11-03, and the 2016 precedent suggests the first week of October. ⚠ **Do not let anyone substitute the assent date** — see the build-shape note for why that is the one wrong answer.
- **The OGL–Yukon licence text could not be read — is that acceptable to proceed on?** The licence *identity* is machine-confirmed from CKAN metadata (`OGL-Yukon-2.0`), the data is published on an open portal with no gate, and Yukon's OGL is by name a member of the standard Canadian OGL family — but **the actual redistribution and attribution clauses were never retrieved**, because `yukon.ca` and `open.yukon.ca/data/*` return Cloudflare 403 to every server-side fetch. Per the brief's flag-don't-guess rule I have not paraphrased them. A human opening the URL in a browser resolves this in thirty seconds. **No licence was accepted and no form was submitted at any point.**
- **The 2015 Yukon map is on the brink of being lost, and we are holding the last copy.** GeoYukon overwrote the layer in place; `open.canada.ca` delisted both the 2015 and 2008 mirrors (confirmed 404). Our 19 rows appear to be the only machine-readable public copy left. Two asks: (1) confirm the retire-don't-delete instruction is honoured in the build migration; (2) decide whether we want to **export those 19 polygons to a durable artifact** under `data/boundaries/yukon/prior/` before touching them — a `pg_dump`-of-geometry or a GeoJSON export costs nothing and is genuinely irreplaceable. Recommend yes.
- **The YT roster needs an end-dating pass and it is not a boundary job.** 33 rows are `is_active` against 21 seats. The 2021 cohort was never end-dated when the 2025 election happened, so defeated members still read as sitting — the same class of staleness tracked in `project_municipal_ended_at_stale`. Boundary work will fix the 13 NULL FKs mechanically but will **not** fix the 19 stale-active rows, and leaving them makes YT look like a 33-seat legislature. Who owns that cleanup?
- **3 of the 21 districts have no MLA row at all** — `Takhini`, `Watson Lake - Ross River - Faro`, `Whistle Bend North`. The 2025 roster ingest was incomplete before boundaries entered the picture. Given `yukonassembly.ca` is Cloudflare-blocked, filling these three may need the same manual/allowlist route [`../yukon.md`](../yukon.md) already proposes for YT Hansard — or just three hand-entered rows, which for three members is probably the cheaper answer.
- **Should Yukon get a `politicians.yt_mla_slug` column?** `CLAUDE.md` convention #1 says every jurisdiction with a stable member ID gets one, and NT has `nt_mla_slug`. Yukon has none. ⚠ The blocker is that the *upstream* has no stable member ID either — and `electionsyukon.ca` / `yukonassembly.ca` are unreadable, so we cannot check whether one exists behind the WAF. Deferring, but noting the convention gap explicitly rather than silently.

## Status

> ⚠ **Reconciled 2026-09-01.** The checkboxes below are the **research phase's** record
> (closed 2026-08-18) and several were overtaken by the build — migrations `0064`–`0121`,
> merged to `main` 2026-08-28. An unticked box here is **not** evidence that something is
> still outstanding.
>
> **Live counts: [`PROGRESS.md`](./PROGRESS.md)** (generated by `boundary-progress`).
> **What actually landed:** the migration headers, which are the accurate record.
> This file's job is the *reasoning* — sources, licences, traps, vintage evidence.

- [x] Current boundaries located and staged (2026-08-18)
- [x] CRS confirmed from `.prj` — **EPSG:3578**, parameter-matched (no `AUTHORITY` node in the WKT); **not 3579**, the datum is plain NAD83
- [x] Attribute schema read from `.dbf` header of the recommended file — 2 fields, no ID column; three publications use three different field-name sets
- [x] `.cpg` read case-insensitively — lowercase `.cpg`, UTF-8, no accented names at risk
- [x] Distinct-ID check — **21 records → 21 distinct IDs**, no duplicate-`constituency_id` risk; **max parts = 1**, every district a single simple polygon
- [x] GeoJSON vs shapefile verified identical on count, names and geometry — **GeoJSON recommended as build input**
- [x] Seat-count discrepancy resolved — **21 is correct, `jurisdiction_sources.seats` needs no change**
- [x] Prior generation `effective_from` established as the **legal in-force date** — **`2016-10-07`**, Commissioner's Order 2016/01, from the CEO's own 2016 report; July 2015 amendment date and 2016-11-07 polling day recorded as discrepancies
- [x] District ID reconciliation confirmed — 15/21 slug match
- [ ] ⛔ **Ruling A6 violation** — `constituency_id` prefix encodes the generation; re-prefix to `yukon-electoral-districts/` and move the vintage to `boundaries_version`. **Not applied.** ★ Applying it shrinks the build from a 21-row re-key to a 19-row prefix rename + 6 new districts.
- [x] Re-tested for the BC defect — ✅ **negative**: unchanged districts match to within 0.4%, so the large deltas are real redistribution, not corruption. YT is visibly short (19 rows vs 21 seats), not deceptively healthy.
- [x] Roster reconciliation confirmed — 18/21 districts covered, 33 active rows vs 21 seats
- [x] Confirmed no click-through licence gate on any boundary endpoint
- [ ] Current generation `effective_from` — ⛔ **blocked: 2025 dissolution date unobtainable, every primary source Cloudflare-403. Bounded to 2024-11-21 < d < 2025-11-03. This blocks the build.**
- [ ] Prior boundaries located — ⛔ **blocked: withdrawn from all authoritative sources; our 19 held rows are the last copy**
- [ ] Licence text captured verbatim — ⛔ **blocked: Cloudflare 403 on `yukon.ca` and `open.yukon.ca/data/*`; licence identity confirmed via CKAN API only**
- [ ] 2015 polygons exported to a durable artifact before re-key — **recommended, not done**
- [ ] YT roster end-dating pass — out of scope for this dossier, **raised**
