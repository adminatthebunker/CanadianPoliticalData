# Boundary + Open North replacement — progress

⛔ **Generated file. Do not hand-edit.** Regenerate with `boundary-progress`; run it in the same change that lands a cutover.

The prose dossiers in this directory carry the *reasoning* — licences, traps, per-jurisdiction findings. This file carries the *counts*, because the hand-maintained coverage matrices were wrong within four days of the programme shipping.

## Geometry — is the map ours?

Keyed on `constituency_boundaries.authority`, which is NULL until a set is cut over to the agency that publishes it. Counts districts and boroughs only — municipality rows are city outlines, not seats — and only generations in force **today**.

| level | live | authoritative | % | successor dated | remaining |
|---|---:|---:|---:|---:|---:|
| federal | 343 | 343 | 100.0% | 0 | 0 |
| provincial | 781 | 657 | 84.1% | 124 | 0 |
| municipal | 1343 | 1119 | 83.3% | 15 | 209 |
| **total** | **2467** | **2119** | **85.9%** | **139** | **209** |

**successor dated** — mirror geometry still in force, with an authoritative replacement already loaded and dated. It resolves on a known day with no work: all of it is Québec's 2017 provincial map, live until 2026-10-04, superseded 2026-10-05 by the 127-district successor (migration `0117`). ⚠ Until that date, Québec provincial lookups return mirror polygons.

**remaining** — mirror geometry with nothing queued behind it. This is the backlog.

### Municipal districts by province

| province | live | authoritative | % | remaining |
|---|---:|---:|---:|---:|
| QC | 338 | 226 | 66.9% | 112 |
| ON | 347 | 292 | 84.1% | 40 |
| AB | 47 | 26 | 55.3% | 21 |
| PE | 21 | 0 | 0.0% | 21 |
| SK | 20 | 10 | 50.0% | 10 |
| NL | 5 | 0 | 0.0% | 5 |
| MB | 15 | 15 | 100.0% | 0 |
| NB | 312 | 312 | 100.0% | 0 |
| NS | 238 | 238 | 100.0% | 0 |

### The named remainder

209 district rows across 31 sets. Each is a map somebody has to go and get.

| province | set | live | remaining |
|---|---|---:|---:|
| QC | `montreal-boroughs-and-districts` | 76 | 18 |
| QC | `saint-jerome-districts` | 12 | 12 |
| PE | `charlottetown-wards` | 10 | 10 |
| SK | `saskatoon-wards` | 10 | 10 |
| AB | `grande-prairie-county-no-1-divisions` | 9 | 9 |
| AB | `strathcona-county-wards` | 8 | 8 |
| PE | `summerside-wards` | 8 | 8 |
| QC | `cote-saint-luc-districts` | 8 | 8 |
| QC | `dollard-des-ormeaux-districts` | 8 | 8 |
| QC | `kirkland-districts` | 8 | 8 |
| QC | `pointe-claire-districts` | 8 | 8 |
| QC | `westmount-districts` | 8 | 8 |
| ON | `thunder-bay-wards` | 7 | 7 |
| ON | `king-wards` | 6 | 6 |
| ON | `richmond-hill-wards` | 6 | 6 |
| ON | `st-catharines-wards` | 6 | 6 |
| QC | `beaconsfield-districts` | 6 | 6 |
| QC | `dorval-districts` | 6 | 6 |
| QC | `mercier-districts` | 6 | 6 |
| QC | `montreal-est-districts` | 6 | 6 |
| NL | `st-johns-wards` | 5 | 5 |
| QC | `quebec-districts` | 26 | 5 |
| QC | `sainte-anne-de-bellevue-districts` | 5 | 5 |
| QC | `senneville-districts` | 5 | 5 |
| AB | `wood-buffalo-wards` | 4 | 4 |
| ON | `north-dumfries-wards` | 4 | 4 |
| ON | `wellesley-wards` | 4 | 4 |
| ON | `wilmot-wards` | 4 | 4 |
| ON | `woolwich-wards` | 3 | 3 |
| PE | `stratford-wards` | 3 | 3 |
| QC | `saguenay-districts` | 18 | 3 |

## Roster — is the person ours?

⛔ `source_id LIKE 'opennorth:%'` counts **provenance, not staleness**, and over-reports the exposure by ~948 rows. A row carrying a native legislature ID (CLAUDE.md convention #1) is matched by exact FK from its own legislature's pipeline every day; the prefix is just the provenance of its first write. All 332 "frozen" federal MPs are in that bucket.

⚠ These are **refresh-path** buckets, not freshness. Nothing on `politicians` records when we last confirmed a person still holds a seat.

| scope | active | replaced | legacy prefix, live pipeline | no replacement path |
|---|---:|---:|---:|---:|
| municipal ON | 603 | 26 | 0 | 577 |
| municipal BC | 104 | 0 | 0 | 104 |
| municipal AB | 74 | 0 | 0 | 74 |
| provincial NB | 49 | 0 | 0 | 49 |
| municipal NB | 34 | 0 | 0 | 34 |
| municipal NS | 30 | 0 | 0 | 30 |
| provincial NL | 40 | 12 | 0 | 28 |
| municipal PE | 27 | 0 | 0 | 27 |
| provincial PE | 26 | 0 | 0 | 26 |
| municipal SK | 22 | 0 | 0 | 22 |
| municipal MB | 16 | 1 | 0 | 15 |
| municipal NL | 11 | 0 | 0 | 11 |
| provincial YT | 18 | 13 | 0 | 5 |
| provincial NS | 55 | 0 | 54 | 1 |
| federal CA | 332 | 0 | 332 | 0 |
| provincial AB | 87 | 0 | 87 | 0 |
| provincial BC | 93 | 0 | 93 | 0 |
| provincial MB | 57 | 0 | 57 | 0 |
| provincial NT | 19 | 0 | 19 | 0 |
| provincial ON | 122 | 0 | 122 | 0 |
| provincial QC | 125 | 1 | 124 | 0 |
| provincial SK | 61 | 1 | 60 | 0 |
| **total (all rows)** | **2534** | **583** | **948** | **1003** |

**1003 rows have no replacement path.** That is the honest exposure number.

## Election cliff

⚠ Dates other than Ontario's are **statutory-cycle inferences, not confirmed against each province's own Act**. Ontario's is corroborated by our own dormant 2026 maps. Confirm before acting.

| province | next municipal election | rows with no path | replacement ingester |
|---|---|---:|---|
| BC | 2026-10-17 | 104 | ⛔ **none** |
| ON | 2026-10-26 | 577 | `amo-on: (AMO per-cycle API)` |
| MB | 2026-10-28 | 15 | ⛔ **none** |
| PE | 2026-11-02 | 27 | ⛔ **none** |
| QC | 2029-11-04 | 0 | `mamh-qc: (MAMH election result)` |

## Boundary generations flipping within 60 days

- 2026-10-05 provincial/QC quebec-electoral-districts -> v2026: 125 live districts become 127 (+2) | ⛔ 6 sitting members would detach | ⚠ jurisdiction_sources.seats is 125 and will not agree — update it in the same change that ingests the election result
- 2026-10-26 municipal/ON burlington-wards -> v2026: 6 live districts become 6 (0)
- 2026-10-26 municipal/ON chatham-kent-wards -> v2026: 6 live districts become 8 (+2) | ⛔ 17 sitting members would detach
- 2026-10-26 municipal/ON haldimand-county-wards -> v2026: 6 live districts become 7 (+1)
- 2026-10-26 municipal/ON london-wards -> v2026: 14 live districts become 14 (0)
- 2026-10-26 municipal/ON ottawa-wards -> v2026: 24 live districts become 24 (0)
- 2026-10-26 municipal/ON pickering-wards -> v2026: 3 live districts become 3 (0)

---

_Generated 2026-09-02 by `boundary-progress`. Do not hand-edit — regenerate._
