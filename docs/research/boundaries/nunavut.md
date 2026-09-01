# Nunavut — Electoral Boundary Research

> Standalone boundary/roster dossier for Nunavut. Cross-cutting context
> (methodology, licence matrix, reconciliation strategy) lives in [`overview.md`](./overview.md).
> The legislative-data dossier for this jurisdiction is at [`../nunavut.md`](../nunavut.md).

**Agency:** Elections Nunavut | **Website:** https://www.elections.nu.ca | **Districts (current):** 22 | **Current order:** Bill 48, *An Act Respecting the Constituencies of Nunavut* (6th Assembly, assented May 2024; in force 2025-09-22) | **Next redistribution:** no statutory trigger — the periodic-review section was repealed (s.15, repealed S.Nu. 2011, c.17, s.6); a commission is struck ad hoc by Assembly resolution under s.16(1)

**Status snapshot (2026-08-18):** ★ **Cracked outright — this gap closes.** ✅ Elections Nunavut publishes a **real Esri shapefile** of all 22 constituencies, not a PDF map: `EN_FUTURE_NU_Constituencies.zip` (205 KB, 22 polygons, EPSG:4617 NAD83(CSRS) geographic), reachable by plain HTTPS GET with **no licence click-through, no registration, no WAF**. ★ The **immediately-prior generation is also available as a shapefile** — `EN_PRESENT_2013_Present_NU_Constituencies.zip`, an *orphaned* file still live at the origin but no longer linked from any page; found via the Internet Archive CDX index, then fetched from the Elections Nunavut origin itself. ★ Both zips bundle a `readme` PDF carrying the **Open Government Licence – Elections Nunavut v1.0** verbatim — commercial use permitted, attribution required, nothing to accept. ✅ **District-name matching is a clean 22/22** against our existing `politicians.constituency_name` values on a case-insensitive compare; zero manual mapping. ✅ Effective dates are pinned to the day by Elections Nunavut's own annual report ("Effective September 22, 2025") and by the prior generation's readme ("became the official constituencies … on September 23, 2013"). ⚠⚠ **The two filenames are now inverted and will mislead you — read the next section before touching either file.** `EN_FUTURE_…` is the set **currently in force**; `EN_PRESENT_2013_Present_…` is the **superseded** one. ⚠ Second trap: the current file's ESRI metadata abstract is **stale boilerplate carried over from the 2011 commission** and claims the 2011 boundaries are "the current constituency boundaries" — ignore the abstract, trust the readme and the `idPurp` block. **Difficulty 1.**

---

## ⚠ Which file is in force — resolved, and the answer is counter-intuitive

The lead flagged the word "FUTURE" in `EN_FUTURE_NU_Constituencies.zip`. It is a live hazard, and the resolution inverts what the filenames say:

| File | Filename says | **Actually is** | `effective_from` | `effective_to` |
|---|---|---|---|---|
| `EN_FUTURE_NU_Constituencies.zip` | future | ✅ **CURRENTLY IN FORCE** — load this one | `2025-09-22` | `NULL` |
| `EN_PRESENT_2013_Present_NU_Constituencies.zip` | present | ⛔ **SUPERSEDED** — historical only | `2013-09-23` | `2025-09-21` |

**Why the names lie.** Both files were released together on **2024-10-28** and named relative to *that* moment: at the time, the 2013 set was the present one and the Bill 48 set was still forthcoming. The names were frozen at release and never revised. When the 6th Assembly dissolved on 2025-09-21, the labels silently swapped meaning. It is now **2026-08-18** — the "future" set has been in force for eleven months and has already been used to run a general election.

**Evidence that `EN_FUTURE_…` is in force today, not forthcoming:**

1. Elections Nunavut, *2024-2025 Annual Report of the Chief Electoral Officer* (`TD-422-6(2)`), verbatim: "Bill 48 an act respecting the constituencies of Nunavut (new boundaries) was approved by the Legislative Assembly of Nunavut. The new boundaries will be effective the 1st day following the dissolution of the sixth Legislative Assembly. **(Effective September 22, 2025)**"
2. Elections Nunavut, *Report on the Conduct of the Seventh Nunavut General Election* (`TD-008-7(2)`), verbatim: "The election was conducted in accordance with the electoral boundaries established by the Boundaries Commission during 2022–2023 review and tabled in the Legislative Assembly. **These boundaries came into force the day following the dissolution of the Sixth Legislative Assembly.**" The 2025-10-27 general election was **already run** on these boundaries; writs issued 2025-09-22.
3. The prior file's own bundled readme, verbatim: "These boundaries **will be replaced** by redistributed constituencies and boundaries the day after the day that the sixth Legislative Assembly of Nunavut dissolves." That replacement has happened.
4. Elections Nunavut's Drupal node for the download is titled **"Maps of Constituencies GIS - 2025"** at `/en/document/maps-constituencies-gis-2025`, and it is the only entry under the site's "Maps of Constituencies - GIS shape file" taxonomy term.

**And there is no third, genuinely-forthcoming set.** Re-checked the full `/en/documents` inventory on 2026-08-18: exactly **one** `.zip` is linked anywhere on `elections.nu.ca` — `EN_FUTURE_NU_Constituencies.zip`. The commission reports on file are 2006, 2011, and 2023 only; **no fifth commission has been struck**, and none can be until the Assembly passes a resolution under s.16(1) (the periodic-review trigger, s.15, was repealed by S.Nu. 2011, c.17, s.6). So there is nothing to record-but-not-load.

**On the 2023 NEBC report** (staged under `current/`): those are the boundaries that are **now in force**, not a future set — it is the *fourth* commission, whose recommendations became Bill 48. It is staged as the reasoning behind the current geometry, not as a forthcoming generation. ⚠ But note it is a *recommendation*, and the Assembly enacted a narrower version of it — see the last bullet under Current boundaries.

**Recommended defensive measure for the build:** do not key the loader on the filename. Key on the readme text or on an explicit generation argument, and assert that the row loaded with `effective_to IS NULL` has `effective_from = '2025-09-22'`. If Elections Nunavut ever re-issues under the same filename for the *next* redistribution — which their naming habit suggests they might — a filename-driven loader would silently install boundaries that do not legally exist yet.

---

## Current boundaries

- **Source URL(s):** https://www.elections.nu.ca/sites/default/files/documents/EN_FUTURE_NU_Constituencies.zip ; https://www.elections.nu.ca/en/document/maps-constituencies-gis-2025 ; https://www.elections.nu.ca/en/taxonomy/term/247
- **Format:** Esri shapefile, zipped. Archive contains `.shp` / `.shx` / `.dbf` / `.prj` / `.CPG` / `.sbn` / `.sbx` / `.shp.xml` plus `readme EN_FUTURE_NU_Constituencies.pdf` (the licence). 205 KB zipped, 289 KB unzipped. No GeoJSON is offered.
- **CRS / projection:** **EPSG:4617** — ⚠ **asserted manually; the `.prj` carries no `AUTHORITY` clause, so EPSG auto-detection will fail.** `.prj` verbatim, complete: `GEOGCS["GCS_North_American_1983_CSRS",DATUM["D_North_American_1983_CSRS",SPHEROID["GRS_1980",6378137.0,298.257222101]],PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]]` — note it ends at the `UNIT` clause with no `AUTHORITY["EPSG",…]`. The code was recovered from `EN_FUTURE_NU_Constituencies.shp.xml`, which carries `<WKID>4140</WKID><LatestWKID>4617</LatestWKID>`; 4140 is the deprecated NAD83(CSRS98) code and **4617 is the one to use**. Cross-checks: the ESRI name `GCS_North_American_1983_CSRS` and the GRS 1980 spheroid parameters (`6378137.0, 298.257222101`) both identify NAD83(CSRS) unambiguously, and the coordinates are decimal degrees in range. So: geographic, **not** a polar or UTM projection despite the high-Arctic extent. The build **must** do an explicit `ST_SetSRID(geom, 4617)` before `ST_Transform(…, 4326)` — anything relying on the `.prj` to self-identify will either fail or silently assume the wrong datum. Datum shift to WGS84 is sub-metre.
- **Attribute schema:** dBASE III (`0x03`), 22 records. ⚠ **The encoding sidecar is `EN_FUTURE_NU_Constituencies.CPG` — UPPERCASE extension.** A `*.cpg` glob returns **empty** on this archive (verified). Its content is `UTF-8`, and this is load-bearing: `Name_I` holds Inuktitut syllabics and `Name_Fr` holds accented French (`BAIE d'HUDSON`). Miss the sidecar, fall back to CP1252, and every non-ASCII name mojibakes. Glob case-insensitively, or hard-code UTF-8 for this jurisdiction. Fields from the `.dbf` header: `Loc` C(2) — always `NU`; `Name_I` C(50) — Inuktitut **syllabics** (e.g. `ᐊᒡᒍ`, `ᖁᑦᑎᒃᑐᕐᒃ`); `Name_Fr` C(50) — French, **populated for only 6 of 22** (`BAFFIN SUD`, `BAIE d'HUDSON`, `RANKIN INLET NORD-CHESTERFIELD INLET`, `RANKIN INLET SUD`, `ARVIAT SUD`, `ARVIAT NORD-WHALE COVE`), blank elsewhere; `Name_Inu` C(50) — **Inuinnaqtun** roman orthography, populated for 11 of 22 (e.g. `IQALUKTUUTTIAQ`, `QAMANITTUAQ`, `KANGIRLINIQ HIVURAA`), blank elsewhere; `Shape_Leng` F(19,11); `Shape_Area` F(19,11); `Name_E` C(56) — English, **UPPERCASE**, populated for all 22.
- **District ID field:** ⚠ **There is no numeric or slug ID field.** `Loc` is the constant `'NU'`. `Name_E` is the de-facto key — unique across all 22, stable across both generations, and matches our roster (see Reconciliation). Note s.31(1) of the *Nunavut Elections Act*: "Nunavut is divided into 22 constituencies with the names set out in Part 1 of the Schedule. **Each language version of those names is equally authoritative.**" English is a convenience key, not a privileged one; the Inuktitut/Inuinnaqtun/French names should be preserved as display metadata rather than discarded.
- **Effective date:** **`effective_from = 2025-09-22`** — the **legal in-force date**, per amendment A2.
  - **Statutory instrument:** Bill 48, *An Act Respecting the Constituencies of Nunavut*, 6th Legislative Assembly, assented **May 2024**. Commencement is governed by *Nunavut Elections Act* s.29(2), verbatim: "Any Act respecting the boundaries of constituencies comes into force on the **1st day following the day the Legislative Assembly dissolves**, but no earlier than six months after the day the bill was enacted." The 6th Assembly was dissolved effective Sunday **2025-09-21** (instrument `R-029-2025 — Dissolution of the Sixth Legislative Assembly of Nunavut`); writs for the 7th general election issued **2025-09-22**.
  - **Confirmed by the agency, not inferred:** Elections Nunavut's *2024-2025 Annual Report of the Chief Electoral Officer* states of Bill 48 — "The new boundaries will be effective the 1st day following the dissolution of the sixth Legislative Assembly. **(Effective September 22, 2025)**". Corroborated by the agency's own map-book filename `Future-Constituency-Boundaries-After-Sept-21-2025.pdf` and by the readme bundled in the zip.
  - ⚠ **Dataset-metadata date — DO NOT USE: 2024-10-28** (readme: "This file was released on October 28, 2024"). Supporting metadata timestamps: ESRI `.shp.xml` CreaDate/ModDate `20241110`, `.dbf` last-update `2024-09-21`, HTTP `Last-Modified: Wed, 20 Nov 2024 14:40:23 GMT`. **The metadata date leads the legal date by ~11 months** — exactly the discrepancy A2 warns about. A loader that took the publication date would place every Nunavut address in the new riding for the whole of the 7th Assembly's pre-election period, including the 2025 campaign.
  - `R-029-2025` itself was **not read**: `nunavutlegislation.ca` is Cloudflare-gated (see Rate limits / auth). The dissolution date is nonetheless firm — it is stated in the shapefile readme as the scheduled date, implied by the 2025-09-22 writ issuance, and the resulting in-force date is stated outright by the CEO's annual report. No `needs confirmation` marker warranted on the date; the *bill number* is likewise firm (named in the annual report).
- **Superseded date:** n/a — current generation, `effective_to` stays `NULL`.
- **District count:** **22**, exactly matching the 22 seats in the Legislative Assembly (one MLA per constituency, s.31(1)).
  - ✅ **One district per row — the island trap does not bite here, despite the archipelago.** Verified: `.dbf` records = 22, **DISTINCT `Name_E` = 22, zero duplicates**; `.shx` implied records = 22; `.shp` header = 22 records, all shape type 5 (Polygon), and **every record has exactly 1 ring** (`min=max=1`, histogram `{1: 22}`). No multipart geometry, no separate island rows, no holes.
  - The reason is the envelope design: because the polygons include marine area and tile the territory wall-to-wall (s.30(a)), Baffin, Victoria, Ellesmere and the rest are *enclosed* by their district polygon rather than stored as separate parts. This is why a jurisdiction that is almost entirely islands produces a file with no multipart geometry at all — counter-intuitive, and worth stating so nobody "fixes" it.
  - Consequence for the load: a straight one-row-to-one-`constituency_id` insert is safe. **No dissolve/`ST_Collect` step is needed**, and none should be added. If a future re-issue ever exceeds 22 records, that is the signal the format changed — worth an assertion.
- **Difficulty (1–5):** **1** — documented, direct, unauthenticated download of a structured file under an open licence.
- **Notes:**
  - **Geometry is a wall-to-wall administrative partition, not a coastline-clipped dataset.** 22 single-part polygons, 5,387 vertices total, bbox `lon -120.680833 .. -57.531918`, `lat 51.157146 .. 89.999999`. The northern extent reaching 90°N and the inclusion of marine areas is deliberate — s.30(a) of the Act requires that "no part of Nunavut lies outside a constituency". ★ For our purposes this is **better** than a coastline file: every point in and around the territory falls in exactly one district, so point-in-polygon has no gaps to fall through.
  - Vertex budget is spent where it matters. The intra-community splits carry the detail — `SOUTH BAFFIN` 2,097 vertices, `ARVIAT SOUTH` 419, `IQALUIT-TASILUK` 324, `IQALUIT-SINAA` 322, `IQALUIT-NIAQUNNGUU` 223, `IQALUIT-MANIRAJAK` 170 — while single-community rural districts are 22–99-vertex envelopes (`TUNUNIQ` 22, `GJOA HAVEN` 23, `CAMBRIDGE BAY` 33). No holes, no multipart rings.
  - ⚠ **Stale metadata trap.** `EN_FUTURE_NU_Constituencies.shp.xml` contains an FGDC `abstract`/`purpose` block reading "These boundaries were updated in 2011 by the Nunavut Boundary Commission … **They are the current constituency boundaries**." That text is inherited boilerplate from the previous dataset. The authoritative description is the ArcGIS `idPurp` block in the same file and the bundled readme, both of which say May-2024 approval / in force the day after the 6th Assembly dissolves. Anyone reading the abstract alone will date this file wrong by twelve years.
  - The ESRI lineage block also preserves dead pre-2013 district names (`OKPIK`, `IGLOOLIK SOUTH`, `IGLOOLIK NORTH`, `IPELLIE`, `NAKASUK`, `JOAMIE`, `NATTILIK`) from `CalculateField` calls. Historical residue only — none of them appear in the `.dbf`.
  - **What Bill 48 actually adopted is narrower than what the commission recommended.** The 2023 NEBC report proposed restructuring the Kivalliq — a new "Rankin Inlet North and Coral Harbour" constituency and a "Naujaat and Chesterfield Inlet" constituency. Comparing `Shape_Area` between the two generations shows `AIVILIK` and `RANKIN INLET NORTH-CHESTERFIELD INLET` **unchanged to four decimal places**, so that restructuring was *not* enacted. 15 of 22 districts show any area change at all, and only the Iqaluit ridings move materially: `IQALUIT-MANIRAJAK` −2.40%, `IQALUIT-SINAA` +0.44%, `IQALUIT-TASILUK` −0.09%, `IQALUIT-NIAQUNNGUU` +0.005%. Everything else is sub-0.01% sliver adjustment. ⚠ **Do not read the NEBC report as the order** — it is a recommendation the Assembly modified.

## Prior boundaries (immediately preceding)

- **Source URL(s):** https://www.elections.nu.ca/sites/default/files/documents/EN_PRESENT_2013_Present_NU_Constituencies.zip ; https://www.elections.nu.ca/sites/default/files/documents/2021_11x17_All_Constituencies.pdf ; https://www.elections.nu.ca/sites/default/files/documents/report-2011-nunavut-electoral-boundaries-commission-8-en.pdf
- **Format:** Esri shapefile, zipped — same nine-file layout as the current generation, 201 KB zipped. Also staged: the 2021 `11x17` all-constituencies PDF map book, as a human-readable cross-check.
- **CRS / projection:** **EPSG:4617**, byte-identical `.prj` to the current generation — and ⚠ **likewise carrying no `AUTHORITY` clause**: `GEOGCS["GCS_North_American_1983_CSRS",DATUM["D_North_American_1983_CSRS",SPHEROID["GRS_1980",6378137.0,298.257222101]],PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]]`. Same manual `ST_SetSRID(geom, 4617)` requirement.
- **Attribute schema:** ✅ **byte-identical field signature to the current generation** — verified field-by-field, not assumed (this is the A4 "two files from the same agency may differ" trap, checked and cleared): `Loc` C(2,0), `Name_I` C(50,0), `Name_Fr` C(50,0), `Name_Inu` C(50,0), `Shape_Leng` F(19,11), `Shape_Area` F(19,11), `Name_E` C(56,0). Same order, same widths, same decimal counts, dBASE III, 22 records. ⚠ `.CPG` is **also UPPERCASE** here (`EN_PRESENT_2013_Present_NU_Constituencies.CPG`, content `UTF-8`) — the lowercase glob misses it on this archive too. A single loader handles both generations with no branching.
- **District ID field:** `Name_E`, and the **same 22 English names as the current generation** — the 2024 order changed geometry only, no district was created, retired, or renamed. This makes the temporal model trivial: 22 `constituency_id` values, each with two rows differing only in `boundaries_version` / `effective_from` / `effective_to` / geometry.
- **Effective date:** **`effective_from = 2013-09-23`** — the **legal in-force date**, per A2. From the bundled readme, verbatim: "These constituencies were proposed in 2011 by the Nunavut Electoral Boundaries Commission and were subsequently approved by the third Legislative Assembly of Nunavut. **They became the official constituencies and electoral boundaries for the territory of Nunavut on September 23, 2013.**" Same s.29(2) mechanism — the 3rd Assembly dissolved 2013-09-22 ahead of the 2013-10-28 general election.
  - **Statutory instrument: bill number `needs confirmation`.** The commencement mechanism and the date are both primary-sourced, but the *citation* for the 2013-generation constituencies Act was not recovered — it would live on `nunavutlegislation.ca`, which is Cloudflare-gated. The date itself does **not** need confirmation; only the bill number does. Low priority: nothing in the build depends on it.
  - ⚠ **Dataset-metadata dates — DO NOT USE, and here they are wildly misleading:** readme "released on October 28, 2024"; `.shp` built `2024-02-29`; `.dbf` last-update `2024-09-21`; HTTP `Last-Modified: Fri, 22 Nov 2024 14:40:37 GMT`. Every metadata timestamp on this file postdates its legal in-force date by **more than eleven years** — it is a 2024 re-issue of a 2013 boundary set, packaged alongside its successor. A metadata-derived `effective_from` here would be off by over a decade and would make the two generations overlap.
- **Superseded date:** **`effective_to = 2025-09-21`** — the last day the 6th Assembly existed; the successor order took force the following day, per s.29(2). Readme verbatim: "These boundaries will be replaced by redistributed constituencies and boundaries the day after the day that the sixth Legislative Assembly of Nunavut dissolves." The two generations therefore abut exactly with no gap and no overlap: `2013-09-23 → 2025-09-21`, then `2025-09-22 → NULL`.
- **District count:** 22 — Nunavut went 19 → 22 seats at the 2013 general election under the 2011 commission, so this generation is the first 22-seat map. ✅ Same one-district-per-row verification as the current file: 22 `.dbf` records, **22 distinct `Name_E`, zero duplicates**, 22 `.shx` records, 22 polygons, **1 ring each** (histogram `{1: 22}`).
- **Difficulty (1–5):** **2** — the file is structurally identical to the current one and downloads cleanly, but it is **unlinked from every page on the site**; you cannot reach it by navigation. Discovery required the Internet Archive CDX index. Rated 2 rather than 1 purely on discoverability; once you have the URL it is a 1.
- **Notes:**
  - The bytes staged in `prior/` were fetched **from the Elections Nunavut origin** (HTTP 200, `Last-Modified: Fri, 22 Nov 2024 14:40:37 GMT`), not from the Internet Archive. The archive was used only to learn that the filename exists. Primary-source provenance is intact.
  - Total vertices 4,485 vs 5,387 in the current generation — the added ~900 vertices are almost entirely the redrawn Iqaluit dividing lines.
  - ⚠ Because it is orphaned, this file could disappear on any Drupal file-system cleanup. It is staged now; treat the local copy as the archival one.
  - Generations older than 2013 (the 19-seat map from 1999, and the 2006 commission's work) are **not** published in any machine-readable form. Only PDF commission reports exist: `nunavut-electoral-boundaries-commission-2006-final-report-8-en.pdf`, `report-2011-nunavut-electoral-boundaries-commission-8-en.pdf`, `electoral-boundaries-commission-8-en.pdf`. Out of scope for the two-generation model; recorded so nobody re-probes.

## District ↔ elected official mapping

- **Source URL(s):** https://assembly.nu.ca/members/mla ; https://www.elections.nu.ca/en/constituency-map ; https://www.elections.nu.ca/en/2025-territorial-general-elections
- The Legislative Assembly's `/members/mla` page is the authoritative roster and renders **server-side HTML** — no JS, no API needed. Each row is a Drupal view with `views-field-field-member-name` (name) and `views-field-field-member-mla` (constituency), grouped under `Speaker` / `Premier of Nunavut` / `Cabinet` / `Members` headings. Difficulty 2.
- **Consensus government — no parties.** All 22 members sit as independents; there is no party column to parse and none should be synthesised.
- **Current state as of 2026-08-18: 21 sitting members + 1 vacancy.** `/members/mla` renders `VACANT` for **Hudson Bay**. ⚠ Our DB still carries **Daniel Qavvik** as the active member for Hudson Bay — our roster is stale by one seat. That is a roster-pipeline item, not a boundary item, but the boundary build will surface it the moment a Sanikiluaq postcode resolves to a member who has left.
- Elections Nunavut's `/en/constituency-map` is the better source for the **constituency → community** crosswalk, which the roster page does not carry: `Aggu`→Igloolik; `Aivilik`→Naujaat, Coral Harbour; `Amittuq`→Igloolik, Sanirajak; `Arviat North-Whale Cove`→Arviat, Whale Cove; `Arviat South`→Arviat; `Baker Lake`→Baker Lake; `Cambridge Bay`→Cambridge Bay; `Gjoa Haven`→Gjoa Haven; `Hudson Bay`→Sanikiluaq; `Iqaluit-Manirajak`/`Iqaluit-Niaqunnguu`/`Iqaluit-Sinaa`/`Iqaluit-Tasiluk`→Iqaluit; `Kugluktuk`→Kugluktuk; `Netsilik`→Taloyoak, Kugaaruk; `Pangnirtung`→Pangnirtung; `Quttiktuq`→Arctic Bay, Grise Fiord, Resolute Bay; `Rankin Inlet North-Chesterfield Inlet`→Rankin Inlet, Chesterfield Inlet; `Rankin Inlet South`→Rankin Inlet; `South Baffin`→Kinngait, Kimmirut; `Tununiq`→Pond Inlet; `Uqqummiut`→Clyde River, Qikiqtarjuaq.
- **Per-MLA stable ID:** the roster page links each member photo to a bare Drupal node — `<a href="/node/2669">` for the Speaker, for instance. There is no human-readable per-member slug anywhere on `assembly.nu.ca`. This is the open question already logged in [`../nunavut.md`](../nunavut.md) ("is there a stable per-MLA slug or numeric ID … we can stamp on `politicians.nu_assembly_slug`"). The answer is: **only the node id**. Whether a Drupal `nid` is stable enough to persist per CLAUDE.md convention #1 is a roster-side call, not a boundary-side one — handed off, not decided here.
- ⚠ **The 2025 general election is not the whole story for Aggu.** Elections Nunavut's results page carries an "Aggu New Election Results December 15, 2025" heading alongside the 2025-10-27 general election. Any roster refresh keyed to the general-election date alone will get Aggu wrong.

## Postal-code correspondence (if published)

**One-line answer (per amendment A3):** ⛔ **None published, open-licence or otherwise — nothing to chase here.** The rest of this section is not about concordances; it is a point-in-polygon accuracy warning specific to Nunavut that the build needs before launch.

- Elections Nunavut publishes no postal-code ↔ constituency correspondence file in any format. No PC/FSA table appears anywhere in the documents index; the only geographic products are the shapefile and the PDF map books. No open-licence equivalent of the Elections Québec file exists here, so the A3 exception does not apply.
- ⚠ **This layer would be near-useless in Nunavut even if it existed, and the reason matters for how we present lookups.** Nunavut has 25 communities and three FSAs (`X0A`, `X0B`, `X0C`); a community typically maps to a single postal code. But **ten of the 22 districts are intra-community splits**: Iqaluit is divided four ways (`Iqaluit-Manirajak` / `-Niaqunnguu` / `-Sinaa` / `-Tasiluk`), Arviat two ways (`Arviat South` / `Arviat North-Whale Cove`), Rankin Inlet two ways (`Rankin Inlet South` / `Rankin Inlet North-Chesterfield Inlet`), and Igloolik is split between `Aggu` and `Amittuq`. A postal-code centroid cannot discriminate between them — it resolves to one point somewhere in the settlement and the answer is a coin-flip.
- **Recommendation for the build:** for NU, point-in-polygon against the real polygon is correct and will work for the 12 single-district communities. For the 10 split-community districts, a postcode-derived point should be treated as **ambiguous, not authoritative** — the honest UI is "your community is split between X and Y; enter a street address" rather than a confident wrong riding. Since our current behaviour returns *nothing* for NU, anything is an improvement, but shipping a false-confidence answer for Iqaluit (~40% of the territory's population) would be the worst outcome.
- Our `public.postcode_cache` currently holds **0** rows matching `X0%` — no NU postcode has ever been resolved through the Open North proxy, so there is no cached evidence either way about what that upstream returns for NU. `UNTESTED — probe during build.`

## Terms / Licensing

- **Licence name:** Open Government Licence – Elections Nunavut, **version 1.0**.
- **Licence URL:** not published as a standalone web page. The full text ships **inside each zip** as `readme <basename>.pdf`, in English and Inuktitut syllabics. Identical text in both the current and prior archives.
- ✅ **Nothing to accept.** No click-through agreement, no checkbox, no account, no form. Contrast Elections Ontario. The download is a plain `GET`.
- **Grant, verbatim:**
  > The Information Provider grants you a worldwide, royalty-free, perpetual, non-exclusive licence to use the Information, including for commercial purposes, subject to the terms below.
  >
  > You are free to:
  >
  > - Copy, modify, publish, translate, adapt, distribute or otherwise use the Information in any medium, mode or format for any lawful purpose.
- **Attribution clause, verbatim:**
  > You must, where you do any of the above:
  >
  > - Acknowledge the source of the Information by including any attribution statement specified by the Information Provider(s) and, where possible, provide a link to this licence.
  > - If the Information Provider does not provide a specific attribution statement, or if you are using Information from several information providers and multiple attributions are not practical for your product or application, you must use the following attribution statement:
  >
  > **Contains information licensed under the Open Government Licence – Elections Nunavut.**
- **Redistribution:** expressly permitted — "publish … distribute or otherwise use the Information in any medium, mode or format for any lawful purpose", commercial use included. No share-alike, no non-commercial restriction, no field-of-use limit.
- **Exemptions, verbatim:**
  > This licence does not grant you any right to use:
  >
  > - Personal Information;
  > - third party rights the Information Provider is not authorized to license;
  > - the names, crests, logos, or other official symbols of the Information Provider; and
  > - Information subject to other intellectual property rights, including patents, trade-marks and official marks.
- **Non-endorsement, verbatim:**
  > This licence does not grant you any right to use the Information in a way that suggests any official status or that the Information Provider endorses you or your use of the Information.
- **Termination, verbatim:** "The terms of this licence are important, and if you fail to comply with any of them, the rights granted to you under this licence, or any similar licence granted by the Information Provider, will end automatically." Attribution is therefore a hard condition, not a courtesy.
- **Governing law:** "This licence is governed by the laws of the Territory of Nunavut and the applicable laws of Canada. Legal proceedings related to this licence may only be brought in the courts of Nunavut."
- **Versioning caveat, verbatim:** "This is version 1.0 of the Open Government Licence – Nunavut. The Information Provider may make changes to the terms of this licence from time to time and issue a new version of the licence. Your use of the Information will be governed by the terms of the licence in force as of the date you accessed the information." → the licence-as-accessed is pinned by our retrieval timestamp in `PROVENANCE.md`. Keep that timestamp.
- The commission reports and PDF map books carry no explicit licence — plain Crown copyright. They are staged as evidence and reference only; **do not redistribute those PDFs**, only the shapefile-derived geometry.
- Site footer reads `Copyright © 2023 Elections Nunavut`, which does not displace the OGL grant attached to the data products.

## Rate limits / auth

- ✅ **None encountered.** No API key, no session, no referer check, no rate limiting observed across ~30 requests to `www.elections.nu.ca` during this pass.
- `Server: Apache`, Drupal 9/10. `elections.nu.ca` 301s to `www.elections.nu.ca`; always use the `www.` host.
- No `sitemap.xml` (404). `robots.txt` exists and returns 200. The `/en/documents` view renders the **entire** document inventory server-side in one ~200 KB page — no pagination, no AJAX view, no infinite scroll. That single page is the cheapest inventory probe for this site; re-fetch it rather than crawling.
- A realistic browser `User-Agent` was sent throughout as a courtesy; nothing suggests it is required.
- ⛔ **Dead end — `nunavutlegislation.ca` is Cloudflare-gated.** The consolidated statutes and regulations site (which hosts `R-029-2025 — Dissolution of the Sixth Legislative Assembly of Nunavut`, and would be the primary source for Bill 48's assent date) returns `HTTP 403` with `cf-mitigated: challenge` to server-side requests, including on its `/en/file-download/download/public/<id>` endpoints. Same blocker tier as PE/YT. Not needed for the boundary build — the effective date is pinned from Elections Nunavut's own documents — but recorded so nobody re-probes it.
- ⛔ **Dead end — no Government of Nunavut open-data portal.** `data.gov.nu.ca` and `opendata.gov.nu.ca` do not resolve (NXDOMAIN); `https://www.gov.nu.ca/en/open-data` returns `HTTP 403`. GN publishes no CKAN/Socrata/ArcGIS Hub instance.
- ⛔ **Dead end — `open.canada.ca` has nothing.** CKAN `package_search?q=nunavut+electoral+constituency` returns 29 hits, none of which are Nunavut *territorial* electoral boundaries (the matches are federal-riding datasets, PFAS sampling in Nunavut, and Charter statements). Statistics Canada does not publish provincial/territorial electoral districts.
- ⏸️ **Not probed:** `geo.ca` (resolves, 200) and the Nunavut Planning Commission at `nunavut.ca` (resolves, 200). Both were left alone because the authoritative source was already secured for both generations under an open licence — a second copy of the same polygons from a re-publisher adds provenance risk, not value. If a higher-fidelity coastline-following variant is ever wanted, NPC is where to look first.

## Staged files

Staged under `data/boundaries/nunavut/` with `PROVENANCE.md` (committed; the payloads are gitignored). 11.5 MB total, well inside the 500 MB budget. Nothing was converted, reprojected, or loaded — the zips are staged as-downloaded. The archives were unzipped **into the scratchpad only**, to read `.prj` / `.dbf` / `.shp` headers per the no-GDAL procedure.

| Generation | File | Bytes | sha256 (first 16) |
|---|---|---:|---|
| current | `EN_FUTURE_NU_Constituencies.zip` | 209,842 | `042209c5a2171f71…` |
| current | `Future-Constituency-Boundaries-After-Sept-21-2025-v1.pdf` | 6,442,979 | `38310f55a2e2a44a…` |
| current | `2023_NEBC_Report_english.pdf` | 4,395,545 | `6b3a35da12c0c110…` |
| prior | `EN_PRESENT_2013_Present_NU_Constituencies.zip` | 205,983 | `f96e3662be8e72ed…` |
| prior | `2021_11x17_All_Constituencies.pdf` | 507,323 | `fe4b9272dccd932f…` |

~~⚠ **`data/boundaries/**/PROVENANCE.md` is not actually being tracked.** `.gitignore:97-98` reads `data/boundaries/` followed by `!data/boundaries/**/PROVENANCE.md`, but git never descends into an excluded *directory*, so the negation is inert.~~ ✅ **Resolved 2026-08-18** — the fix landed in `.gitignore:99-105` (`data/boundaries/**` + `!data/boundaries/**/` + `!data/boundaries/**/PROVENANCE.md`) while this pass was running. Re-verified: `git check-ignore -v data/boundaries/nunavut/PROVENANCE.md` now reports the **negation** line, and `git status` lists seven agents' `PROVENANCE.md` files as untracked-and-addable. Nothing further needed here.

⚠ **But the dossiers themselves are in an ignored tree.** `.gitignore:90` is `/docs/`, which ignores the entire internal docs tree. The 16 legacy `docs/research/*.md` files survive only because they were tracked *before* that rule was added — gitignore does not affect already-tracked files. **`git ls-files docs/research/boundaries/` returns zero**: this dossier, `_matrix/nunavut.md`, and every other agent's output are ignored and will not be committed by a plain `git add`. Same class of problem as the PROVENANCE one, one directory up, and it covers the whole workstream's deliverable rather than just its audit trail. Two options, both fine, and the choice is a policy call for the coordinator rather than mine:

- `git add -f docs/research/boundaries/` at consolidation time, leaving the ignore rule alone; or
- narrow the rule so only the boundaries subtree is exposed. Tested in a scratch repo — adds the boundaries dossiers, keeps `docs/plans/` and the rest of `docs/` ignored, no side effects on the already-tracked legacy files:

```gitignore
/docs/**
!/docs/research/
!/docs/research/boundaries/
!/docs/research/boundaries/**
```

Not applied — `.gitignore` is shared across the fleet. Raised as a handoff item below.

## Reconciliation with `constituency_boundaries`

**What we hold today: nothing.**

```
SELECT count(*) FROM constituency_boundaries
 WHERE province_territory = 'NU' OR source_set ILIKE '%nunavut%';
-- 0
```

Not stale — **absent**. Open North never published a `nunavut-electoral-districts` boundary set, and because `services/scanner/src/opennorth.py` ingests boundaries as a side effect of roster ingestion, no upstream set meant no rows. The placeholder at `services/scanner/src/opennorth.py:147-159` still declares `boundary_set="nunavut-electoral-districts"` against a representative path that returns zero objects. All 22 NU rows in `politicians` carry `constituency_id = NULL`. A postcode lookup anywhere in Nunavut returns nothing for the territorial layer today.

**Our roster side is clean.** All 22 active NU rows have `constituency_name` populated, all 22 distinct.

**Name matching: 22/22, zero manual mapping.** Normalising both sides (NFKD, strip combining marks, casefold, collapse whitespace around hyphens) gives a complete bijection between `politicians.constituency_name` and the shapefile's `Name_E`. Nothing is left over on either side. The only systematic difference is case — the shapefile is UPPERCASE throughout, our roster is title case:

| shapefile `Name_E` | our `constituency_name` |
|---|---|
| `ARVIAT NORTH-WHALE COVE` | `Arviat North-Whale Cove` |
| `IQALUIT-NIAQUNNGUU` | `Iqaluit-Niaqunnguu` |
| `RANKIN INLET NORTH-CHESTERFIELD INLET` | `Rankin Inlet North-Chesterfield Inlet` |
| `UQQUMMIUT` | `Uqqummiut` |

…and so on for all 22. **No diacritics anywhere** — every English name is plain ASCII, so the syllabics-vs-roman-orthography hazard the brief anticipated does not bite on the join key. It only matters for display: the syllabics live in `Name_I` and the Inuinnaqtun in `Name_Inu`, and those are legally co-equal per s.31(1). `lower(constituency_name) = lower(Name_E)` is sufficient and needs no fuzzy fallback. Recommend an assertion in the loader that all 22 join, and a hard failure if fewer do.

**Proposed `constituency_id` scheme.** Open North never minted one, so we choose. Existing territorial precedent in the table is `{source_set}/{kebab-slug}` with a generation year baked into the set name:

```
northwest-territories-electoral-districts-2013/dehcho
yukon-electoral-districts-2015/…
british-columbia-electoral-districts-2015-redistribution/…
```

~~**Recommendation:** `source_set = 'nunavut-electoral-districts-2024'`, `constituency_id = 'nunavut-electoral-districts-2024/{kebab(lower(Name_E))}'`… The `-2024` suffix is Bill 48's enactment year and matches the agency's own internal feature-class name (`EN_2024_Present_Official_Constituency_Bdy`); the prior generation then becomes `nunavut-electoral-districts-2013/…`.~~

> ⛔ **SUPERSEDED by ruling A6 (2026-08-18) — coordinator resolution.** A generation must
> **never** appear in a `constituency_id` prefix. The unique key is
> `(constituency_id, boundaries_version)`, so `constituency_id` is generation-independent by
> design and `boundaries_version` carries the generation; baking a year into the prefix
> forces a full `politicians` UPDATE on every future redistribution. **12 of our 13
> federal/provincial prefixes already violate this** and are each a future forced re-key.
>
> **✅ Adopt for both generations:**
> ```
> source_set      = 'nunavut-electoral-districts'
> constituency_id = 'nunavut-electoral-districts/{kebab(lower(Name_E))}'
>                   e.g. nunavut-electoral-districts/rankin-inlet-north-chesterfield-inlet
> ```
> Generations are distinguished by `boundaries_version` plus
> `effective_from` / `effective_to` — current `2025-09-22 → NULL`, prior
> `2013-09-23 → 2025-09-21`.
>
> ⛔ **This is the highest-severity A6 item in the corpus and the only one that is free to
> fix.** Every other violation describes a legacy state that already exists in the table;
> Nunavut holds **0 rows**, so following the struck-through recommendation would mint 22
> brand-new violating keys into a clean slate. The dossier's own observation that "either
> scheme works for NU because the 22 names are identical across both generations" is what
> makes the correct scheme cost nothing here.
>
> The two questions below were deferred to Agent X2 and are now **both answered**: bare set
> name (question 1), and therefore no year at all (question 2, moot).

~~Two things to settle with **Agent X2**, who owns the global re-key:~~ *(resolved — retained for the reasoning trail)*

1. **Year-in-set-name vs bare set name.** NT/YT/BC carry the year; AB (`alberta-electoral-districts`) does not. If X2 standardises on bare set names, NU should be `nunavut-electoral-districts/…` for both generations, distinguished by `boundaries_version` + `effective_from`/`effective_to` alone — which the table's `(constituency_id, boundaries_version)` unique constraint already supports. **Either scheme works for NU because the 22 names are identical across both generations**; NU is unusually insensitive to this decision and should follow whatever X2 picks rather than driving it.
2. **Which year, if a year is used.** `-2024` (enactment) vs `-2025` (in force). I prefer `-2024` to match the agency's naming, but `-2025` is defensible and NT's `-2013` appears to be an in-force year. X2's call.

**Retire the dead placeholder.** Whatever is chosen, `services/scanner/src/opennorth.py:147-159` should stop claiming `boundary_set="nunavut-electoral-districts"` — that string will never resolve upstream and, if a future re-key happens to mint the same slug from the Elections Nunavut file, the stale comment becomes actively misleading about where the rows came from.

**Temporal load is straightforward.** Two generations, same 22 keys, same schema, same CRS:

| | `boundaries_version` | `effective_from` | `effective_to` |
|---|---|---|---|
| `EN_PRESENT_2013_Present_NU_Constituencies` | prior | `2013-09-23` | `2025-09-21` |
| `EN_FUTURE_NU_Constituencies` | current | `2025-09-22` | `NULL` |

Note that existing rows across the table carry a placeholder `effective_from = 2023-01-01` inherited from the Open North mirror date. NU would be the first jurisdiction whose dates are **real legal in-force dates**. Worth flagging to whoever owns the temporal-model cleanup: don't let a normalisation pass overwrite these with the placeholder.

**Backfill `politicians.constituency_id`** from `lower(constituency_name) = lower(Name_E)` once the rows land — 22/22 will match, which finally makes the NU roster joinable to geography.

## Research-handoff items

- ~~**`.gitignore` negation is inert — every boundary agent's `PROVENANCE.md` is silently untracked.**~~ ✅ **Resolved 2026-08-18** — fix landed centrally at `.gitignore:99-105` mid-run and is verified working. No action needed.
- **The boundary dossiers are themselves in an ignored tree — nothing in `docs/research/boundaries/` can be committed by a plain `git add`.** `.gitignore:90` is `/docs/`; the 16 legacy `docs/research/*.md` files are tracked only by grandfathering. `git ls-files docs/research/boundaries/` returns **0**. This is the whole workstream's deliverable, ~24 dossiers plus the `_matrix/` fragments. **Do you want `git add -f docs/research/boundaries/` at consolidation, or should the ignore rule be narrowed?** A tested narrowing pattern is in § Staged files. Either works; the intent behind `/docs/` being ignored is yours to interpret, so I have not touched it.
- **Confirm the `constituency_id` scheme with Agent X2 before the build.** NU is genuinely indifferent between `nunavut-electoral-districts/…` and `nunavut-electoral-districts-2024/…` because the 22 names are stable across both generations. **Does X2 want NU to adopt the year-suffixed form (matching NT/YT/BC) or the bare form (matching AB)?** This dossier recommends year-suffixed, `-2024`, but will not fight for it.
- **Multilingual district names need a storage decision.** `constituency_boundaries.name` is a single `text` column, but s.31(1) of the *Nunavut Elections Act* makes all four language versions **equally authoritative** — English is not the legal primary. The shapefile carries Inuktitut syllabics for all 22, Inuinnaqtun for 11, and French for 6. **Do we (a) store English in `name` and drop the rest, (b) add a `names JSONB` column, or (c) stage the alternates in a side table?** Dropping them is a defensible v1 but is a real fidelity loss in the only jurisdiction where Inuktitut is an official working language, and it will look careless if anyone from Nunavut reads our data. This is a schema question above my scope.
- **Intra-community splits break postcode lookup for ~10 of 22 districts.** Iqaluit (4 districts), Arviat (2), Rankin Inlet (2), and Igloolik (split between Aggu and Amittuq) all share single postal codes. **Is the product answer "return the ambiguous set and ask for a street address", or "return nothing", or "return the largest-population district"?** Returning one confident district for an Iqaluit postcode would be a stale-boundary-class error in a jurisdiction we are otherwise about to serve perfectly. Needs a UI/product call before launch, not after.
- **Our NU roster is one seat stale.** `assembly.nu.ca/members/mla` shows **Hudson Bay = VACANT** as of 2026-08-18; our DB still lists Daniel Qavvik as active. Separately, Aggu was decided by a "New Election" on **2025-12-15**, not at the 2025-10-27 general election. **Should the boundary build trigger a NU roster refresh, or is that a separate ticket?**
- **The prior-generation shapefile is an orphaned file with no inbound links.** It is live at the origin today but unreachable by navigation, so it is one Drupal cleanup away from vanishing. It is staged locally. **Should orphaned-but-live primary files like this be mirrored somewhere more durable than a gitignored staging dir?** This will not be the last one.
- **No per-MLA stable identifier exists for Nunavut.** `assembly.nu.ca` links member bios only as `/node/<nid>` (e.g. `/node/2669`). Per CLAUDE.md convention #1 a new jurisdiction should get a persisted canonical member ID, but a bare Drupal node id is weak. **Do we persist `nu_assembly_nid` anyway, or continue name-matching for NU?** Roster-side call; recorded here because this pass answered the open question logged in [`../nunavut.md`](../nunavut.md).
- **Nunavut hamlet/municipal wards — probably nothing to find, deliberately not chased.** Elections Nunavut administers municipal council elections and states a council "normally has eight councillors plus a mayor, all of whom are elected locally every four years", with no ward structure described and **no ward geometry published anywhere on the site**. `UNTESTED — probe during build`, but the expectation is at-large councils with no boundaries to ingest. Flagged for the municipal agent, not researched further per brief scope.

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
- [x] Prior boundaries located and staged (2026-08-18) — orphaned file recovered from origin
- [x] **In-force generation established (2026-08-18)** — `EN_FUTURE_…` is the set currently in force; the filenames are inverted. No forthcoming set exists to record-but-not-load.
- [x] Licence cleared for internal use — **Open Government Licence – Elections Nunavut v1.0, no acceptance required, commercial + redistribution permitted, attribution mandatory**
- [x] CRS identified — EPSG:4617, both generations. ⚠ **Asserted manually; neither `.prj` has an `AUTHORITY` clause.**
- [x] Attribute schema read from `.dbf` header — both generations, field signature verified byte-identical
- [x] Encoding sidecar checked — ⚠ **`.CPG` is UPPERCASE on both archives**; content `UTF-8`
- [x] One-district-per-row verified — 22 records / 22 distinct IDs / 1 ring each, both generations; **no island-row duplication despite the archipelago**
- [x] Effective / superseded dates pinned to the day from primary sources — **legal in-force dates used per A2**, metadata dates recorded as discrepancies
- [x] District ID reconciliation confirmed — 22/22 case-insensitive match, no re-key hazard
- [x] Matrix fragment written to `_matrix/nunavut.md` per A1 — **`overview.md` not touched**
- [ ] `constituency_id` scheme ratified — **pending Agent X2's global decision**
- [ ] Multilingual name storage decided — **pending schema call**
- [ ] Loaded into `constituency_boundaries` — build phase
- [ ] `politicians.constituency_id` backfilled for the 22 NU members — build phase
- [ ] `services/scanner/src/opennorth.py:147-159` placeholder retired — build phase
