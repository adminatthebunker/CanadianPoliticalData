### licence
| Jurisdiction | Rows held | Source | Licence | Internal use | Redistribution | Notes |
|---|---:|---|---|---|---|---|
| Municipal Ontario (48 sets) | 410 | ⚠ **No federation** — ~40 independent municipal publishers: ArcGIS Hub tenancies (majority) + CKAN (Toronto) | ⚠ **Mixed / unaudited** — one licensor per municipality | ⚠ Presumed yes | ⚠ Unverified | ⛔ Largest set (Toronto) reports `license_title: None` / `"License not specified"` on CKAN — the OGL–Toronto applies in practice but is **not machine-readable**. ~40 licences unaudited; a per-city audit is a build-phase task. ✅ No click-through gate encountered on any *municipal* endpoint (unlike Elections Ontario provincially). |

### coverage
| Jurisdiction | Rows held | Seats | Authoritative count | Vintage held | Current vintage | Delta |
|---|---:|---:|---:|---|---|---|
| Municipal Ontario (48 sets) | 410 | n/a (48 councils) | ⚠ unaudited per council | undated — all rows `boundaries_version='current'`, `effective_from='2023-01-01'` (Open North artifacts); mostly the 2022-10-24 election map | per-municipality; **next general election 2026-10-26** | ⛔ **Only 343 of 410 rows are wards**; 316 distinct after de-duplication. **40 of 48 sets contaminated** with a stray `census-subdivisions/` municipality polygon → **PIP returns 2–4 overlapping matches** (Mississauga: 4). ⛔ `peel-wards` duplicates all 27 Brampton/Caledon/Mississauga wards under a second ID scheme — this plus Brampton's **paired wards** fully explains the 12 ON orphan rows (neither stale geometry nor stale roster). ⚠ Several sets short of council: Ajax 3/4, Belleville 2/6, Burlington 4/6 — BC-defect shape, unaudited across the rest. ✅ `lasalle-wards` = at-large, legitimate, no data can exist. ⛔ `whitchurch-stouffville-wards` = real gap (6 wards since 2022). ⚠ Fastest-decaying class: s. 222 reviews are discretionary with a 45-day OLT appeal, and **an election lands 2026-10-26**. |

### a6
| Jurisdiction | Current prefix | A6-compliant target | Status |
|---|---|---|---|
| Municipal Ontario | `toronto-wards-2018/` (**only violation** of 48) | `toronto-wards/` | ⛔ **Violation** — year in prefix. Not applied. ★ Cheapest possible moment to fix: the 25-ward model is still current, so it is a rename with no geometry change, and Toronto has run four ward models (44/47/25) whose history CKAN publishes — exactly the case A6 enables. ⚠ Separately, **all 410 ON rows carry `boundaries_version='current'`**, so no set records its generation; A6 migration must populate it or the unique key stays uninformative. |
