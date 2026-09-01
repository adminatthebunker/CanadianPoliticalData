### licence
| Jurisdiction | Rows held | Source | Licence | Internal use | Redistribution | Notes |
|---|---:|---|---|---|---|---|
| [Manitoba](../manitoba.md) | 56 | Elections Manitoba — `electionsmanitoba.ca/downloads/` (current `2018_Final_ED_*`, prior `2008_Final_ED_*`) | ⛔ none published — `© 2026. All rights reserved.` + "Maps are provided for informational purposes only" | ⚠ defensible | ⛔ **not cleared** | No click-through, no registration — nothing accepted. ✅ Confirms X2's audit: nothing to inherit **because none was granted**. Reclassify MB from *provenance unknown* to *provenance established: no licence*. More assertive posture than SK's silence — if only one agency is emailed, email this one. Data MB portal publishes **no** electoral layer — checked, 0 matches |

### coverage
| Jurisdiction | Rows held | Seats | Authoritative count | Vintage held | Current vintage | Delta |
|---|---:|---:|---:|---|---|---|
| [Manitoba](../manitoba.md) | 56 | 57 | 57 | ✅ **2018 Commission — correct, current** (asserted from `source_set` + 56/56 name-match; ⚠ not yet confirmed by geometry — the 2008 file is now staged as the comparison fixture) | 2018 Electoral Divisions Boundaries Commission, C.C.S.M. c. E40, in force 2019-08-12 | ✅ **1 missing: `The Pas-Kameesak`** (identified by exhaustion). ★ Control case — vintage is right, so this is one INSERT and **no geometry replacement**, unlike SK. ⚠ Ships as **two shapefiles** (25 Rural + 32 Urban) that must be unioned; archive names misleading (both say `_Urban`). ✅ Prior generation now staged (57/57 across 26+31, recovered via Wayback CDX per A5) — note the split is 26/31 there, not 25/32 |

### A6 prefix migration
| Jurisdiction | Current prefix | Target prefix | `politicians` | `politician_terms` | `constituency_boundaries` | Total |
|---|---|---|---:|---:|---:|---:|
| [Manitoba](../manitoba.md) | `manitoba-electoral-districts-2018` | `manitoba-electoral-districts` | 56 | 56 | 56 | **168** |

Pure `replace()` substitution, reversible with the inverse. Cheapest cutover of any province examined: 168 prefix updates + 1 INSERT + the `authority` backfill, with no geometry replacement.

### cross-jurisdictional traps found here
- ⚠ **Retained field name, changed semantics.** MB's `Area` is a dense 1–57 **division number** in the 2018 files but an **area measurement in km²** in the 2008 files. More dangerous than a renamed field — schema-diff tooling and human review both miss it. Worth adding to the brief's A4 trap list.
- ⚠ **Per-file record split is not stable across generations** — 25/32 Rural/Urban in 2018, 26/31 in 2008. Never hardcode per-file counts for a multi-file jurisdiction.
- ★ **A French-name column is needed and this is not MB-specific.** MB publishes `ED_French` (2018 only; absent in 2008), federal ships `ED_NAMEF`, and QC and NB will want the same. `constituency_boundaries` has nowhere to put it. Settle once, before the first loader is written.
