# Municipal Alberta — Electoral Boundary Research

> Standalone boundary/roster dossier for Alberta municipal wards. Cross-cutting context
> (methodology, licence matrix, reconciliation strategy) lives in [`overview.md`](./overview.md).
> Per-city legislative dossiers: [`../cities/edmonton.md`](../cities/edmonton.md), [`../cities/calgary.md`](../cities/calgary.md).
> Sibling municipal dossiers: [`municipal-ontario.md`](./municipal-ontario.md), [`municipal-quebec.md`](./municipal-quebec.md), [`municipal-atlantic.md`](./municipal-atlantic.md), [`municipal-west.md`](./municipal-west.md).

**Agency:** each municipality (no provincial ward register) | **Enabling statute:** Municipal Government Act, R.S.A. 2000, c. M-26, s. 148 (council may divide the municipality into wards by bylaw) | **Sets held:** 6 ward/division sets + 1 standalone CSD row | **Rows held:** 53 | **Next redistribution:** per-municipality, by council bylaw; Alberta general municipal elections are quadrennial (most recent 2025-10-20)

**Status snapshot (2026-08-18):** ⚠ **Two of six sets are the wrong vintage or structurally wrong, and one is a live cross-municipality defect.** ★★ **Calgary is a textbook A7 case: 14 wards held against 14 authoritative — a perfect count — but the geometry is the superseded 2017–2021 generation.** Measured against both: **14/14 within 2% of the 2017–2021 shapes (mean 0.36%)** versus only 6/14 against current (mean 4.76%, max 17.53%). ✅ **Edmonton is correct** — mean 0.55% against the in-force 2021 wards, 12/12. ⛔ **★ Grande Prairie is a genuine cross-municipality overlap, not a tier-stacking artifact: 100% of the City of Grande Prairie is covered by County of Grande Prairie No. 1 division polygons** (Division 3 53.2% + Division 2 25.5% + Division 4 21.3%), because the County divisions were never clipped to exclude the City. ⛔ **A12 correction — the CSD rows here are NOT contamination and none is removable: all 6 carry sitting officials (22 in total).** Calgary, Edmonton, Strathcona and Wood Buffalo are **hybrid councils** (mayor on the CSD row, councillors on wards); Grande Prairie city and Lethbridge are at-large with **9 officials each** on the CSD row and no wards at all. ⚠ A10.1 stacking is still real but milder than Ontario's — every ward-council PIP returns **2** polygons, never Mississauga's 4. ⚠ **A12.2: Wood Buffalo's overwrite ratio is 597×** (66,566 km² CSD against a 111 km² ward) — second-worst in the project after Halifax's 703×, and Strathcona is 250×. ✅ **All Alberta municipal sources are Socrata GeoJSON in WGS84 — no reprojection, no `.dbf` parsing, no encoding traps.** ⛔ Licences are "See Terms of Use" on both Calgary and Edmonton — no named open licence.

---

## Current boundaries

- **Source URL(s):** https://data.edmonton.ca/api/geospatial/nydb-6rce?method=export&format=GeoJSON ; https://data.calgary.ca/api/geospatial/tz8z-hyaz?method=export&format=GeoJSON ; https://data.edmonton.ca/api/views/nydb-6rce.json ; https://data.calgary.ca/api/views/tz8z-hyaz.json
- **Format:** GeoJSON via Socrata's geospatial export endpoint. Both cities also expose the same layer as SODA JSON with an embedded geometry column.
- **CRS / projection:** ✅ **EPSG:4326 (WGS84)** for both. Verified by inspection, not assumption: neither file carries a `crs` member (so RFC 7946's WGS84 default applies) and the first coordinates are `[-114.2111288, 51.1833656]` (Calgary) and degree-scaled for Edmonton. ★ **No `ST_Transform` needed and no `.prj` to parse** — a categorical simplification versus the provincial shapefiles (federal 3347, SK 26913, MB 26914). ⚠ Do **not** generalise this to all municipal GeoJSON: Regina's, in [`municipal-west.md`](./municipal-west.md), is EPSG:26913 with an explicit legacy `crs` member.
- **Attribute schema:**

  | Set | Fields | Notes |
  |---|---|---|
  | Edmonton `nydb-6rce` | `name_1`, `name_2`, `effective_start_date`, `effective_end_date`, `effdt_type`, `councillor`, `councillor2`, `geometry_multipolygon` | ★ carries the sitting councillor **and** a temporal model |
  | Calgary `tz8z-hyaz` | `ward_num`, `label`, `councillor`, `multipolygon` | ★ carries the sitting councillor |

  ★ **Both Alberta files ship the elected official inside the boundary file.** That is rare — federal, SK and MB all require a separate roster fetch — and it makes the district↔official mapping a property of the geometry rather than a join.
- **District ID field:** Calgary `ward_num` (integer 1–14). Edmonton `name_2` (the Indigenous-language ward name, e.g. `Anirniq Ward`); Edmonton publishes **no** numeric ward ID in this dataset — `name_1` is just the uppercased name. Our slugs already derive from these names, so no re-key is needed for either city; see Reconciliation.
- **Effective date:** per A10.4 (relaxed for municipal), the election the boundaries first governed. **Edmonton: 2021-10-18** — established from the data, not the label: `Historical` rows end 2021-10-17 and `Current` rows start 2021-10-18 with an open end date, and there is **no break at the 2025 election**, so the 2021 ward geometry remains in force. **Calgary: 2021-10-18** for the current generation (the 2021 general election), the boundaries defined by council bylaw under MGA s. 148.
- **Superseded date:** n/a (current).
- **District count:** Edmonton **12** (matches 12 councillors); Calgary **14** (matches 14 councillors). ⚠ **Both match our row counts exactly, and for Calgary that is precisely the trap** — see the vintage check in Reconciliation.
- **Difficulty (1–5):** **1** — documented Socrata APIs on both, open catalogue search, GeoJSON export, WGS84, no auth, no WAF.
- **Notes:**
  - ★ **A5 label check on Edmonton, as instructed — the labels are honest but the title is not.** The dataset is titled *"City of Edmonton Ward Boundary and Council Composition_Current, Historical and Future"*, yet `effdt_type` has only **two** values: `Current` (12 rows) and `Historical` (30 rows). **There are zero `Future` rows.** Unlike Nunavut's inverted `FUTURE`/`PRESENT` files the labels here agree with the dates, but the advertised third partition does not exist — so a loader filtering `effdt_type='Future'` to pre-stage the next generation silently gets nothing. **In-force status was established from the date ranges, not from the title or the label.**
  - ⚠ **`rowsUpdatedAt` is not evidence of content currency.** Edmonton's dataset reports `rowsUpdatedAt = 2026-08-17` (the day before this research) while its `Current` rows still carry `effective_start_date = 2021-10-18`. That is correct here — the boundaries genuinely have not changed since 2021 — but the timestamp tells you nothing either way, and the same field on Winnipeg's dataset ([`municipal-west.md`](./municipal-west.md)) is actively misleading.
  - ✅ **Edmonton's councillor list cross-checks clean against our roster** — all 12 names in the Socrata `Current` rows match our 12 `edmonton-wards/*` politicians exactly (Rutherford, Paquette, Morgan, Tang, Salvador, Clarke, Stevenson, Janz, Elliott, Parmar, Wright, Principe).
  - **Not researched this pass — the four smaller sets.** Strathcona County (8 wards), Regional Municipality of Wood Buffalo (4 wards), County of Grande Prairie No. 1 (9 divisions) and the City of Grande Prairie (at-large) each publish through their own portals. `data.strathcona.ca` resolves (HTTP 200) but is not CKAN and was not probed further. **UNTESTED — probe during build.** They are 24 of the 53 rows and none of them is Calgary-or-Edmonton-scale, but the Grande Prairie overlap below is the highest-severity defect in this dossier and sits in that untested group.

## Prior boundaries (immediately preceding)

- **Source URL(s):** https://data.calgary.ca/api/geospatial/au4g-xjwh?method=export&format=GeoJSON ; https://data.edmonton.ca/api/geospatial/nydb-6rce?method=export&format=GeoJSON (same file — see below)
- **Format:** GeoJSON, Socrata. Calgary also publishes `9u83-tgux` (Ward Boundaries 2013–2017) as a third generation.
- **CRS / projection:** EPSG:4326 (WGS84), as current.
- **Attribute schema:** Calgary `au4g-xjwh` — `ward_num`, `label`, `councillor`, identical to the current file. ★ Same schema across generations, which is *not* the norm (contrast Manitoba's `Area` field changing meaning between 2008 and 2018).
- **District ID field:** `ward_num`. ⚠ Generation-scoped — ward 11's 2017–2021 shape and its current shape are different territory under the same number.
- **Effective date:** Calgary **2017-10-16** (2017 general election). Edmonton's historical rows span **2007-10-15 → 2021-10-17** across three generations.
- **Superseded date:** **2021-10-18** for both cities.
- **District count:** Calgary 14 (unchanged across the redraw — the count check gives no signal). Edmonton 30 historical rows covering the 2007, 2010/2013 and 2017 generations.
- **Difficulty (1–5):** **1**.
- **Notes:**
  - ★ **Edmonton needs no separate prior-generation download.** `nydb-6rce` is a single temporal file holding all 42 rows — 12 `Current` plus 30 `Historical` — so one fetch gives every generation Edmonton has published. Staged once under `current/`; the build should partition on `effdt_type` / the date columns rather than expecting two files.
  - Calgary, by contrast, publishes one dataset per generation, which is why `au4g-xjwh` is staged separately under `prior/`.

## District ↔ elected official mapping

- **Source URL(s):** the boundary files themselves — https://data.calgary.ca/api/views/tz8z-hyaz.json (field `councillor`) ; https://data.edmonton.ca/api/views/nydb-6rce.json (fields `councillor`, `councillor2`)
- **Format:** an attribute on each ward polygon; no separate roster fetch required.
- **★ Join quality:** trivially perfect — the official is a property of the district row, so there is no name join to get wrong and no possibility of the SK-style spelling drift. Edmonton's 12 names match our roster exactly (verified). Calgary's `councillor` field was not cross-checked against our roster this pass — **UNTESTED**, but the mechanism is the same.
- `councillor2` on Edmonton's historical rows carries the second councillor from the era when Edmonton wards returned two members each (the 2007–2010 rows show pairs, e.g. Ward 1 Karen Leibovici + Linda Sloan). ⚠ A loader assuming one councillor per ward will silently drop half the historical council.
- ⚠ **No stable per-councillor identifier** in either file — names only. Same limitation as SK and MB.
- **Difficulty (1–5):** **1**.

## Postal-code correspondence (if published)

⛔ **None published by any Alberta municipality**, and per A3 this was time-boxed to a quick check. Not needed — the lookup is point-in-polygon and the staged WGS84 ward polygons are a strictly better input.

## Terms / Licensing

⛔ **No named open licence on either major source.** Both Socrata catalogues report their licence as the literal string:

> "See Terms of Use"

with **no `termsLink`** populated on Calgary's dataset metadata. Neither the Open Government Licence – Canada nor a municipal OGL variant is declared in machine-readable metadata for `tz8z-hyaz` or `nydb-6rce`.

**What this is and is not.** It is **not** a click-through gate — no agreement was presented, no account required, nothing was accepted or submitted (standing instruction 3 was not engaged); both files download over plain HTTPS from a public API. But the machine-readable licence field points at a terms page that the metadata does not name, so **the licence has not actually been read** in this pass.

⚠ **This differs from Saskatchewan and Manitoba, where I established that no licence exists.** Here a licence very likely *does* exist — Alberta's major cities generally publish under an open municipal licence — and the gap is that I did not resolve and read it. Marking this `needs confirmation` rather than ⛔-blocked would be over-claiming in the other direction, so: **internal research use is defensible; redistribution is unverified pending someone reading the two cities' actual open-data terms pages.** That is a cheap, bounded task and it is in the handoff items.

## Rate limits / auth

- **Authentication:** none. Socrata's public read APIs need no app token at the volumes used here (an unauthenticated client is throttled only under sustained load).
- **Rate limiting:** none encountered. Roughly 15 requests across `data.calgary.ca` and `data.edmonton.ca` — zero 429s, zero throttling.
- **No WAF** on either host. Both answered plain `curl` without a `User-Agent` header. ✅ Notably cleaner than `elections.sk.ca` (Cloudflare UA-filtering) and `www.regina.ca` (HTTP 403).
- **Caching:** Socrata exposes `rowsUpdatedAt` in `/api/views/<id>.json`, which is the cheap refresh check — ⚠ but see the note above: it reflects metadata touches, not necessarily content changes.
- **Instruction-source boundary:** no page fetched contained text addressed to an AI agent. Nothing to report under standing instruction 8.

## Staged files

Staging root `/media/bunker-admin/Internal/sovpro/data/boundaries/municipal-alberta/`; sha256 audit table in [`PROVENANCE.md`](../../../data/boundaries/municipal-alberta/PROVENANCE.md). **3.5 MiB of a 500 MB budget.**

| Path | Bytes | Features | Districts | Role |
|---|---:|---:|---:|---|
| `current/edmonton-wards_nydb-6rce.geojson` | 2,049,099 | 42 | 12 current + 30 historical | ★ all Edmonton generations in one temporal file |
| `current/calgary-wards_tz8z-hyaz.geojson` | 638,679 | 14 | 14 | ★ current Calgary wards |
| `prior/calgary-wards-2017-2021_au4g-xjwh.geojson` | 964,611 | 14 | 14 | ★ the generation our rows actually match |

**Not staged:** Calgary `9u83-tgux` (Ward Boundaries 2013–2017, a third generation — available, out of scope); the Strathcona County, Wood Buffalo and Grande Prairie sources (UNTESTED, see above).

## Reconciliation with `constituency_boundaries`

**What we hold** (read-only query, 2026-08-18) — **53 rows across 7 `source_set` values**:

| `source_set` | Rows | Of which wards | Embedded CSD row | Notes |
|---|---:|---:|---|---|
| `calgary-wards` | 15 | 14 | ✅ `census-subdivisions/4806016` Calgary, 849 km² | ⚠ **stale vintage** |
| `edmonton-wards` | 13 | 12 | ✅ `census-subdivisions/4811061` Edmonton, 701 km² | ✅ correct |
| `strathcona-county-wards` | 9 | 8 | ✅ `census-subdivisions/4811052`, 1,263 km² | UNTESTED |
| `grande-prairie-county-no-1-divisions` | 9 | 9 | ⛔ **none** — the only clean AB set | UNTESTED |
| `wood-buffalo-wards` | 5 | 4 | ✅ `census-subdivisions/4816037`, 66,566 km² | UNTESTED |
| `grande-prairie-wards` | 1 | **0** | ✅ `census-subdivisions/4819012`, 135 km² — ★ **9 officials** | ★ at-large — see A10.3 below |
| `census-subdivisions` (standalone) | 1 | — | Lethbridge `4802012`, 125 km² — ★ **9 officials** | at-large city |

All 53 carry `effective_from = '2023-01-01'`, `effective_to = NULL` — the hardcoded literals from `services/scanner/src/opennorth.py`, meaningless as dates.

### ★★ A7 vintage check — Calgary is stale, Edmonton is correct

Comparing our stored `area_sqkm` (geodesic) against areas computed from each authoritative generation:

| City | Rows | vs **current** generation | vs **prior** generation | Verdict |
|---|---:|---|---|---|
| **Edmonton** | 12 | **mean 0.55%**, median 0.41%, max 1.44% | n/a (2021 is current) | ✅ **correct vintage** |
| **Calgary** | 14 | mean 4.76%, max 17.53%, only **6/14** within 2% | **mean 0.36%, 14/14 within 2%** | ⛔ **stale — 2017–2021 generation** |

**Calgary is conclusive.** All 14 wards match the 2017–2021 shapes in a tight band of 0.28–0.42% — that spread is my spherical-area approximation against PostGIS geodesic area, i.e. measurement noise, not disagreement — while against the current generation the errors scatter from 0.21% to 17.53%. The six wards that look "fine" against current (1, 2, 4, 5, 10, 13) are simply wards the 2021 redraw barely touched, the same pattern as Saskatchewan's Athabasca and Cumberland. **No ward matches the current generation better than it matches the old one.**

⚠ **And Calgary held 14 wards before the redraw and holds 14 now**, so the count check passes perfectly. This is the third confirmed instance of A7's central point, after SK (61→61) and NT (19/19).

⚠ Per A8.1 I should note the counter-argument and dismiss it: Calgary is landlocked, so the offshore-envelope drawing-convention problem that makes coastal comparisons unreliable does not apply. The area comparison is trustworthy here.

**Strathcona County, Wood Buffalo and Grande Prairie County were NOT vintage-checked** — I did not locate their authoritative sources this pass. Per A7 a matching count proves nothing, so those 21 ward/division rows must be treated as **unknown vintage**, not as correct. That is the single largest gap in this dossier.

### ⛔ ★ The Grande Prairie overlap — a live cross-municipality defect

Distinct from A10.1's tier-stacking, and worse. A PIP at Grande Prairie City Hall returns two polygons that belong to **two different municipalities**:

```
grande-prairie-wards                 :: Grande Prairie (135 km²)   ← the City
grande-prairie-county-no-1-divisions :: Division 3     (214 km²)   ← the County
```

Measured overlap of the County's divisions against the City polygon:

| County division | Overlap with the City | % of the City covered |
|---|---:|---:|
| Division 3 | 71.9 km² | 53.2% |
| Division 2 | 34.5 km² | 25.5% |
| Division 4 | 28.8 km² | 21.3% |
| **Total** | **135.2 km²** | **100.0%** |

**Every square kilometre of the City of Grande Prairie is also covered by a County division polygon**, because the County's divisions were digitised over the City rather than clipped around it. Every Grande Prairie address currently resolves to a County councillor in addition to its own.

### ★ A12.1 tested — this is NOT Peel-shape duplication, and the structural test says so

A12.1 predicted Grande Prairie as Alberta's likeliest two-tier duplication candidate. **Tested, and it is not one** — the distinction matters because it changes the fix from "accept, both tiers are real" to "clip, one of them is wrong."

The discriminator is which *level* each party sits at:

| | upper tier | lower tier | legitimate? |
|---|---|---|---|
| **Peel (ON)** | `census-divisions/3521` Peel, 1,256 km² | `census-subdivisions/…` Mississauga + its ward set | ✅ genuine two-tier — both councils really do govern the same ground |
| **Grande Prairie (AB)** | ⛔ **none — there is no `census-divisions/` row for Grande Prairie** | City = `census-subdivisions/4819012`; County = a ward-style set with **no CSD row of its own** | ⛔ **peer vs peer** |

Alberta has no two-tier municipal governance: a city and a county are **peer municipalities at the same level**, and a point belongs to one or the other, never both. Grande Prairie city residents do not elect County councillors. So the 100% overlap **cannot** be legitimate duplication — it is a digitisation error, and the County divisions must be clipped.

★ **This sharpens A12.1 into a one-query structural test** that is better than "do the polygons overlap":

> **Legitimate two-tier duplication has a `census-divisions/` row as one of the two parties. If both parties are at CSD level (or one is a ward set with no CSD row), the overlap is an error.**

Corroborating arithmetic: the nine County divisions sum to **6,153 km²**, and subtracting the City's 135 km² leaves ~6,018 km² — close to the County's true extent, consistent with the divisions having been drawn straight across the City rather than around it.

⚠ A repo-wide scan for cross-`source_set` municipal overlaps >0.5 km² in AB/BC/SK/MB returns **only these three pairs plus one 0.5 km² sliver** where `strathcona-county-wards/Ward 1` meets `edmonton-wards`. That sliver is a digitisation difference along a shared boundary and is not worth acting on.

### ⚠ A12.2 — overwrite-bug severity, and Alberta holds the project's second-worst case

Ratio of the CSD polygon to the smallest district in the same set, i.e. how wrong
`lookupBoundariesAtPoint` can be when its overwrite loop picks the CSD row:

| Set | CSD km² | smallest district km² | ratio |
|---|---:|---:|---:|
| `wood-buffalo-wards` | 66,566.0 | 111.5 | **597×** |
| `strathcona-county-wards` | 1,262.8 | 5.0 | **250×** |
| `calgary-wards` | 849.0 | 23.8 | 36× |
| `edmonton-wards` | 700.7 | 20.9 | 33× |

★ **Wood Buffalo at 597× is second only to Halifax's 703×** and worse than Cape Breton (430×) or Mississauga (~104×). A Fort McMurray resident can be told their municipal boundary is the entire Regional Municipality — **66,566 km², larger than Nova Scotia**, stretching to the Saskatchewan border. **Wood Buffalo is a strong second regression fixture for the smallest-matching-polygon fix**, and unlike Halifax it pairs an extreme ratio with a *sparse* ward set (4 wards), which exercises a different branch.

Calgary and Edmonton are unremarkable at 36× and 33× — the extreme cases in Alberta are the two **specialised municipalities**, whose CSD polygons include vast rural hinterland around a small urban core.

### ⚠ The Grande Prairie name collision — latent, in the coverage dashboard

The lead flagged that our attribution matches on a slug. The specific path is `services/scanner/src/legislative/coverage_stats.py:188`:

```sql
SELECT count(DISTINCT politician_id) FROM politician_terms
WHERE level = 'municipal' AND source ILIKE '%' || $1 || '%'
```

`$1` is a `municipality_slug`. The two Grande Prairie sources in `politician_terms` are `opennorth:grande-prairie-city-council` (9 terms) and `opennorth:county-of-grande-prairie-no-1-council` (9 terms), so a slug of `grande-prairie` matches **both** and reports 18 politicians for whichever municipality is being counted.

✅ **Currently latent, not live** — `meetings.municipality_slug` holds only `edmonton` today, so no Grande Prairie slug exists to trigger it. It fires the moment either Grande Prairie municipality is added to the coverage dashboard. Note this is a **coverage-statistics** defect, not a lookup defect: `getRepsForPostcode` joins on `constituency_id`, not on `source`.

### ⚠ A latent name-fallback collision that is municipal-specific

`services/api/src/lib/postcode-reps.ts` joins politicians to boundaries on `constituency_id`, with this fallback:

```sql
OR (p.constituency_id IS NULL AND p.level = h.level
    AND lower(p.constituency_name) = lower(h.name))
```

⚠ **At municipal level the district names are not unique.** `"Ward 1"` names **48 polygons** nationally, including five Alberta sets (`calgary-wards`, `strathcona-county-wards`, `wood-buffalo-wards`, plus `regina-wards` and `saskatoon-wards` in the west). A municipal politician with a NULL `constituency_id` and `constituency_name = 'Ward 1'` matches **all 48**. Provincial and federal district names are unique nationally; `"Ward 1"` is not, so this failure mode exists only at municipal level.

✅ **Currently harmless: exactly 5 active municipal politicians have a NULL `constituency_id`, all in Quebec — zero in Alberta.** But A7 established that a missing `related.boundary_url` leaves `constituency_id` NULL, so this is a loaded gun: **the next Alberta municipality whose Open North roster loses its boundary link will silently attribute its councillors to up to 47 other cities' wards.** Worth fixing before it fires — scoping the fallback by `source_set` would do it.

### ⛔ A12 — every Alberta CSD row carries officials; none is removable

Verified per set with a query rather than inferred from set names, per A12:

| Set | CSD row | Officials on it | Ward rows | Council shape |
|---|---|---:|---:|---|
| `grande-prairie-wards` | Grande Prairie | **9** | 0 | at-large |
| `census-subdivisions` | Lethbridge | **9** | 0 | at-large |
| `calgary-wards` | Calgary | 1 | 14 | **hybrid** — mayor |
| `edmonton-wards` | Edmonton | 1 | 12 | **hybrid** — mayor |
| `strathcona-county-wards` | Strathcona County | 1 | 8 | **hybrid** — mayor |
| `wood-buffalo-wards` | Wood Buffalo | 1 | 4 | **hybrid** — mayor |
| | **total** | **22** | | |

⛔ **All six have officials attached, so under A12 not one of them is removable.** A migration
written from the "CSD rows are contamination" framing would orphan **22 sitting Alberta officials** —
18 of them the entire councils of Grande Prairie and Lethbridge, which have no ward rows at all.

★ **The lead's prediction that Strathcona County and Wood Buffalo are hybrids is confirmed**, and both
are specialised municipalities electing a mayor at large plus ward councillors. But Alberta's hybrid
shape is the **minimal** one — exactly one official (the mayor) on the CSD row — where Atlantic
Canada's carries 2–6 (mayor, deputy, and at-large seats). Same structural category, an order of
magnitude less exposure per set.

⚠ **This supersedes the "contamination" framing** used earlier in this dossier and in A10.1. The
correct statement for Alberta is: the CSD rows are **load-bearing everywhere**, and the defect is not
their presence but `lookupBoundariesAtPoint` overwriting rather than preferring the smallest matching
polygon. Fix the resolver, keep the rows.

### ★ Grande Prairie city is at-large — a legitimate finding, not a gap (A10.3)

`grande-prairie-wards` holds **one row, and it is the city CSD polygon, not a ward**. The City of Grande Prairie elects its eight councillors at large; there are no wards and no ward data can exist. Same for Lethbridge (the standalone `census-subdivisions` row). **Nobody should hunt for Grande Prairie or Lethbridge ward boundaries.** Alberta's answer key is structural: under MGA s. 148 a council *may* divide into wards by bylaw, so at-large is the default and warding is the exception — the inverse of Ontario's picture, and the same statutory shape as BC.

⚠ The set is nonetheless **misleadingly named**: `grande-prairie-wards` contains no wards. Renaming it, or marking it with A10.2's `boundary_kind = 'municipality'`, would prevent a future agent from reading it as a gap.

### A6 prefix migration

All six AB ward sets are already generation-free (`calgary-wards`, `edmonton-wards`, …) and **comply with A6 as they stand**. ✅ **No prefix change is required for Alberta** — the only municipal violator flagged repo-wide is `toronto-wards-2018`, which is Ontario's.

Under recommendation (d): `authority = 'city-of-calgary'` / `'city-of-edmonton'` / etc.; `authority_district_id` = Calgary `ward_num`, Edmonton `name_2`. `boundary_kind` per A10.2: `district` for the ward rows, `municipality` for the seven embedded CSD rows. Alberta has no borough tier, so the third value is unused here.

**Proposed temporal values:**

| Generation | `boundaries_version` | `effective_from` | `effective_to` | Rows |
|---|---|---|---|---|
| Calgary 2021 wards | `2021-election` | `2021-10-18` | `NULL` | 14 |
| Calgary 2017 wards | `2017-election` | `2017-10-16` | `2021-10-18` | 14 (currently mislabelled as current) |
| Edmonton 2021 wards | `2021-election` | `2021-10-18` | `NULL` | 12 |

## Research-handoff items

- **⛔ Calgary must be reloaded as a generational replacement, not left alone because the count matches.** All 14 rows are 2017–2021 geometry. The 2021 redraw moved Ward 11 by 17.5% of its area, so a Calgary address near a redrawn boundary currently resolves to the wrong councillor. Both generations are staged; this is a load, not more research.
- **⛔ The Grande Prairie City/County overlap needs a decision, and it is not a data-refresh problem.** The County's division polygons cover 100% of the City. Options: (a) clip the County divisions against the City CSD at load time — correct and cheap, since both polygons are already in the table; (b) source a properly clipped County file, which requires finding the County's publisher first; (c) accept and let the API return both. **Recommendation: (a)**, with the clip done in the loader and asserted (`ST_Area(ST_Intersection(county, city)) = 0`) before commit. **This is the highest-severity defect in this dossier.**
- **⚠ Four of six Alberta sets were never vintage-checked** — Strathcona County (8 wards), Wood Buffalo (4), Grande Prairie County (9 divisions), plus the at-large rows. That is 21 ward/division rows of unknown vintage. Per A7 their matching counts prove nothing. `data.strathcona.ca` resolves but is not CKAN; the other three publishers were not located. **This is the largest bounded gap here and it needs either budget or an explicit decision to accept unknown vintage on the smaller municipalities.**
- **⚠ Read the two Socrata terms pages and settle the licence.** Both Calgary and Edmonton declare `"See Terms of Use"` with no link in metadata. Unlike SK and MB — where I established that no licence exists — here one probably does, and the gap is simply that nobody has read it. Bounded task; would move Alberta from "unverified" to a clean licence-matrix row.
- **⚠ Scope the `postcode-reps.ts` name fallback by `source_set`.** `"Ward 1"` matches 48 municipal polygons nationally. Harmless today (5 NULL-`constituency_id` municipal politicians, all in QC) but it fires silently the first time an Alberta municipal roster loses its boundary link. This is a cross-jurisdictional fix, not an Alberta one.
- **Rename or reclassify `grande-prairie-wards`.** It contains zero wards and one city polygon. Under A10.2, `boundary_kind = 'municipality'` records the fact structurally so no future agent reads it as a gap.

## Status

- [x] Current boundaries located and staged (2026-08-18) — Calgary 14/14, Edmonton 12/12
- [x] Prior boundaries located and staged — Calgary 2017–2021; Edmonton's are in the same temporal file
- [x] CRS confirmed — **EPSG:4326 WGS84, no reprojection needed**, verified by coordinate inspection
- [x] Attribute schema parsed for both major sets
- [x] ★ A5 label check on Edmonton — labels honest, but the title's "Future" partition does not exist
- [x] ★★ A7 vintage check — **Calgary stale (2017–2021), Edmonton correct**, both measured against two generations
- [x] ★ A10.1 stacking measured — 5 of 6 sets carry an embedded CSD row; PIP returns 2 polygons, not 4
- [x] ⛔ **A12 hybrid check — all 6 CSD rows carry officials (22 total); NONE removable**
- [x] ★ A12.1 tested — Grande Prairie is **peer-vs-peer, not Peel-shape**; no `census-divisions` row exists
- [x] ⚠ A12.2 ratios measured — **Wood Buffalo 597×** (2nd worst in project), Strathcona 250×, Calgary 36×, Edmonton 33×
- [x] ⛔ Grande Prairie City/County overlap quantified — **100% of the City covered by County divisions**
- [x] A10.3 at-large distinguished from gap — Grande Prairie city and Lethbridge are legitimately at-large
- [x] District ↔ official mapping — carried inside both boundary files; Edmonton cross-checked 12/12
- [x] A6 compliance confirmed — all AB prefixes already generation-free, no migration needed
- [ ] Vintage check for Strathcona / Wood Buffalo / Grande Prairie County — **not done, 21 rows of unknown vintage**
- [ ] Licence read and recorded — **"See Terms of Use" unresolved on both cities**
- [ ] Grande Prairie overlap remediated — **blocked on an operator decision**
