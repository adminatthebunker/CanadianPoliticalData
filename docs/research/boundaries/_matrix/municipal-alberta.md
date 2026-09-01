### licence
| Jurisdiction | Rows held | Source | Licence | Internal use | Redistribution | Notes |
|---|---:|---|---|---|---|---|
| [Municipal Alberta](../municipal-alberta.md) | 53 | Socrata — `data.calgary.ca` (`tz8z-hyaz`, `au4g-xjwh`), `data.edmonton.ca` (`nydb-6rce`) | ⚠ **unread** — both declare the literal string `"See Terms of Use"` with no `termsLink` in metadata | ⚠ defensible | ⚠ **unverified** | No click-through, nothing accepted. Differs from SK/MB provincial: a licence probably *exists*, it just has not been read. Bounded task. 4 of 6 sets (Strathcona, Wood Buffalo, GP County, GP city) have no located publisher at all |

### coverage
| Jurisdiction | Rows held | Seats | Authoritative count | Vintage held | Current vintage | Delta |
|---|---:|---:|---:|---|---|---|
| [Municipal Alberta](../municipal-alberta.md) | 53 (47 wards + 6 CSD) | 47 wards | Calgary 14, Edmonton 12, Strathcona 8, Wood Buffalo 4, GP County 9 | ⛔ **Calgary = superseded 2017–2021** (proven: mean 0.36%, 14/14 within 2% vs old; 4.76%, 6/14 vs current). ✅ Edmonton correct (0.55%). ⚠ Strathcona / Wood Buffalo / GP County **unchecked** | Calgary 2021 wards; Edmonton 2021 wards | ⚠ **Calgary 14/14 present but all stale** — count check passes perfectly, third confirmed A7 case after SK (61→61) and NT (19/19). ⛔ **100% of the City of Grande Prairie is covered by County of GP No. 1 division polygons** (Div 3 53.2% + Div 2 25.5% + Div 4 21.3%) — a genuine cross-municipality overlap, highest-severity defect here. ★ GP city + Lethbridge are legitimately **at-large** (MGA s.148: warding is opt-in), not gaps |

### A6 prefix migration
| Jurisdiction | Current prefixes | Target | Migration |
|---|---|---|---|
| [Municipal Alberta](../municipal-alberta.md) | `calgary-wards`, `edmonton-wards`, `strathcona-county-wards`, `wood-buffalo-wards`, `grande-prairie-wards`, `grande-prairie-county-no-1-divisions` | unchanged | ✅ **all already generation-free — no migration needed** |

### cross-jurisdictional findings from this dossier
- ★ **Alberta municipal sources are Socrata GeoJSON in WGS84** — no `ST_Transform`, no `.prj`, no `.dbf`, no encoding trap. Categorically simpler than the provincial shapefiles. ⚠ Does **not** generalise: Regina's GeoJSON is EPSG:26913.
- ★ **Both Calgary and Edmonton ship the sitting councillor inside the boundary file** (`councillor`, plus Edmonton's `councillor2` for the historic two-member wards). District↔official becomes a property of the row, not a join.
- ⚠ **A5 label check:** Edmonton's dataset is titled *"…Current, Historical and Future"* but has **zero `Future` rows** — only `Current` (12) and `Historical` (30). Labels agree with dates here (unlike Nunavut), but the advertised partition does not exist.
- ⚠ **`rowsUpdatedAt` is not evidence of content currency** — Edmonton's says 2026-08-17 while its rows still start 2021-10-18 (correctly, as it happens).
- ⚠ **Municipal-only name-fallback collision.** `postcode-reps.ts` falls back to `lower(constituency_name)` at the same level; `"Ward 1"` names **48 polygons nationally**. Harmless today (5 NULL-`constituency_id` municipal politicians, all QC) but fires the moment an AB municipal roster loses its boundary link. Provincial/federal names are unique nationally; ward names are not. **Scope the fallback by `source_set`.**
- ⚠ **`coverage_stats.py:188` slug collision** — `source ILIKE '%'||slug||'%'` matches both `opennorth:grande-prairie-city-council` and `opennorth:county-of-grande-prairie-no-1-council` for slug `grande-prairie`, reporting 18 politicians for either. Latent (no GP slug in `meetings` yet); it is a coverage-dashboard defect, not a lookup one.

### A12 — CSD rows carrying officials (migration safety)
| Jurisdiction | CSD rows | Officials on them | Removable? | Council shapes |
|---|---:|---:|---|---|
| Municipal Alberta | 6 | **22** | ⛔ **none** | Grande Prairie city **9** + Lethbridge **9** = at-large (no ward rows at all); Calgary / Edmonton / Strathcona / Wood Buffalo = **hybrid**, 1 official each (the mayor) |

⛔ A migration dropping CSD rows as contamination would orphan **22 sitting Alberta officials**, 18 of them the *entire* councils of Grande Prairie and Lethbridge. ★ The lead's prediction that Strathcona County and Wood Buffalo are hybrids is **confirmed** — both specialised municipalities, mayor at large plus ward councillors. Alberta's hybrid shape is the **minimal** one (1 official on the CSD row) where Atlantic's carries 2–6.

### A12.1 — Grande Prairie tested: NOT Peel-shape
★ **Prediction tested and disconfirmed, and the distinction changes the fix.** Peel duplicates legitimately because its upper tier is a `census-divisions/` row (`census-divisions/3521`, 1,256 km²) over lower-tier CSDs. **Grande Prairie has no `census-divisions/` row at all** — the City is `census-subdivisions/4819012` and the County is a ward-style set with no CSD row, so the two are **peers at the same level**, not tiers. Alberta has no two-tier municipal governance; a point belongs to a city *or* a county, never both. The 100% overlap is therefore a **digitisation error to be clipped**, not legitimate duplication to be accepted.

> ★ **Sharper structural test for A12.1, one query:** legitimate two-tier duplication has a `census-divisions/` row as one of the two parties. If both parties are at CSD level (or one is a ward set with no CSD row), the overlap is an error.

Corroboration: the 9 County divisions sum to 6,153 km²; minus the City's 135 km² that is ~6,018 km², close to the County's true extent — consistent with divisions drawn straight across the City.

### A12.2 — overwrite ratios (Alberta holds the project's 2nd-worst)
| Set | CSD km² | smallest district km² | ratio |
|---|---:|---:|---:|
| `wood-buffalo-wards` | 66,566.0 | 111.5 | **597×** |
| `strathcona-county-wards` | 1,262.8 | 5.0 | **250×** |
| `calgary-wards` | 849.0 | 23.8 | 36× |
| `edmonton-wards` | 700.7 | 20.9 | 33× |

★ **Wood Buffalo 597× is second only to Halifax's 703×**, above Cape Breton (430×) and Mississauga (~104×). A Fort McMurray resident can be told their municipal boundary is **66,566 km² — larger than Nova Scotia**. Good second regression fixture: unlike Halifax it pairs an extreme ratio with a **sparse** ward set (4 wards), exercising a different branch. Calgary and Edmonton are unremarkable — Alberta's extremes are both **specialised municipalities**, huge rural hinterland around a small urban core.
