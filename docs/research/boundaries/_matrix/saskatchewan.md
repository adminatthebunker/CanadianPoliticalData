### licence
| Jurisdiction | Rows held | Source | Licence | Internal use | Redistribution | Notes |
|---|---:|---|---|---|---|---|
| [Saskatchewan](../saskatchewan.md) | 46 | Elections Saskatchewan — `cdn.elections.sk.ca` (current `maps-ge30/`, prior `maps-ge29/`) | ⛔ none published — bare `Copyright © 2025 Elections Saskatchewan`; `/copyright/`, `/privacy-policy/`, `/terms-of-use/` all 404 | ⚠ defensible | ⛔ **not cleared** | No click-through, no registration — nothing accepted. Silence on reuse, not a refusal. Same decision as Manitoba; decide together. SK GeoHub (open `sk-suudl` licence) publishes **no** constituency layer — checked, 0 matches |

### coverage
| Jurisdiction | Rows held | Seats | Authoritative count | Vintage held | Current vintage | Delta |
|---|---:|---:|---:|---|---|---|
| [Saskatchewan](../saskatchewan.md) | 46 | 61 | 61 | ⛔ **The Representation Act, 2012** — ★ **proven by geometry**, not inferred: 46/46 stored polygons match 2012 shapes to a median 0.07%, 0/46 match 2022 (median 11.67%) | The Representation Act, 2022 — 2022 Commission, in force 2024-10-01 (writs, 30th GE) | ⚠ **61 wrong or missing, not 15.** The 46 held are exactly the **name-stable intersection** of the two orders, carrying 2012 geometry under current names — the BC signature. 15 districts absent (76,475 km², 11.7% of the province); 41 of the 46 present are the wrong shape; 7 have a name moved onto >2× or <0.5× different territory (worst: Regina Wascana Plains, 792 km² stored vs 13.8 km² actual). Seat count held 61→61, so counts gave no warning. **Must load all 61 as a new generation — a 15-row backfill would leave 41 stale rows behind a complete-looking 61/61.** ✅ Prior generation now staged (61/61, recovered via Wayback CDX per A5) |

### A6 prefix migration
| Jurisdiction | Current prefix | Target prefix | `politicians` | `politician_terms` | `constituency_boundaries` | Total |
|---|---|---|---:|---:|---:|---:|
| [Saskatchewan](../saskatchewan.md) | `saskatchewan-electoral-districts-representation-act-2012` | `saskatchewan-electoral-districts` | 45 | 182 | 46 | **273** |

Pure `replace()` substitution, reversible with the inverse. ★ Applying it **before** the generational load means the 46 name-stable districts need no `politicians` update when the 2022 geometry lands — only the 15 genuinely new districts do.
