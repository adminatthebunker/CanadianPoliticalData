### licence
| Jurisdiction | Rows held | Source | Licence | Internal use | Redistribution | Notes |
|---|---:|---|---|---|---|---|
| [Municipal West (BC/SK/MB)](../municipal-west.md) | 49 | Socrata `data.winnipeg.ca` (`t4cg-yaxs`, `mp2r-jeav`); Regina shapefiles (origin not recorded); unattributed ArcGIS item for Saskatoon | ⚠ **all three unread, and one is WRONG** — Winnipeg declares `"Open Government Licence - Prince Edward Island"` on a Manitoba dataset; Saskatoon `license: none`; Regina's terms page behind HTTP 403 | ⚠ defensible | ⚠ **unverified** | No click-through, nothing accepted. ★ **A machine-readable licence field can be flatly wrong — licence-matrix rows must cite a terms page someone read, never a portal tag.** BC needs no licence work (no ward data exists) |

### coverage
| Jurisdiction | Rows held | Seats | Authoritative count | Vintage held | Current vintage | Delta |
|---|---:|---:|---:|---|---|---|
| [Municipal West (BC/SK/MB)](../municipal-west.md) | 49 (34 wards + 15 CSD) | Winnipeg 15, Saskatoon 10, Regina 10; BC 0 | Winnipeg 15, Saskatoon 10, Regina 10 | ✅ Winnipeg correct (mean 0.34%). ⚠ **Regina INCONCLUSIVE** — matches neither 2024 (12.34%) nor 2020 (11.22%). ⚠ Saskatoon untestable | Winnipeg 2018; Regina 2024; Saskatoon unknown | ★ **Winnipeg missing exactly one ward: `Elmwood – East Kildonan` (14)** — one INSERT into a correct-vintage set. ⚠ Regina must not be loaded until polygon intersection settles its generation. ⛔ Saskatoon has no verifiable primary source. ★ **BC's zero wards is CORRECT** — at-large is the statutory default under the Local Government Act (wards need an LGIC-approved bylaw); all 12 BC rows are whole-municipality polygons |

### A6 prefix migration
| Jurisdiction | Current prefixes | Target | Migration |
|---|---|---|---|
| [Municipal West (BC/SK/MB)](../municipal-west.md) | `winnipeg-wards`, `saskatoon-wards`, `regina-wards`, `vancouver-wards`, `langley-wards`, `census-subdivisions` | unchanged | ✅ **all already generation-free — no migration needed** |

### cross-jurisdictional findings from this dossier
- ★ **GeoJSON is not always WGS84.** Regina's carries a legacy `crs` member naming **EPSG:26913** and projected-metre coordinates. RFC 7946 mandates WGS84 and removed `crs`, so "GeoJSON ⇒ 4326" sounds safe and is wrong — and it **fails silently**, placing wards in the Gulf of Guinea. Cost me a bogus 100%-error reading. **Check coordinate magnitude on every GeoJSON.**
- ★ **A machine-readable licence field can be flatly wrong** — Winnipeg's Manitoba dataset is tagged with PEI's provincial OGL. Never populate the licence matrix from portal metadata.
- ⚠ **Socrata's catalogue API is federated by default.** `data.winnipeg.ca/api/catalog/v1?q=ward` returned Calgary's and Edmonton's datasets at the top with no off-domain indication. Scope with `search_context=<host>`. **A federated hit is not evidence the dataset belongs to the host you queried.**
- ⚠ **A declared area column can be empty.** Regina's 2020 `SHAPE_AREA`/`SHAPE_LEN` are empty strings despite `F(31,15)` declarations; areas had to be computed from `.shp` rings.
- ⚠ **Multipart trap confirmed again** — Saskatoon's 13 records are 10 distinct wards (W1/W5/W6 ×2).
- ⚠ **Two municipalities named "Langley"** — City (CSD 5915002, 10.2 km²) and Township (5915001, 314.7 km²), a 31× area difference under one name. CSD codes distinguish them; nothing name-based will.
- ★ **A10.1 contamination is milder in the west than in Ontario** — every western ward-council PIP returns **2** polygons (ward + city CSD), never Mississauga's 4. No `census-divisions` tier and no double-ID duplication. CSD rows confirmed **load-bearing**: they carry BC's at-large councillors, so deleting them would remove BC from the lookup entirely.

### A12 — CSD rows carrying officials (migration safety) — ★ LARGEST EXPOSURE IN THE PROJECT
| Jurisdiction | CSD rows | Officials on them | Removable? | Council shapes |
|---|---:|---:|---|---|
| Municipal West (BC/SK/MB) | 15 | **107** | ⛔ **none** | **BC 12 rows / 104 officials** — at-large, the CSD row *is* the entire council (Vancouver **18**; Surrey/Coquitlam/Kelowna/Langley Twp/Victoria/Abbotsford/Burnaby **9** each; Richmond 8; New Westminster 7; Langley City 7; Saanich 1). SK 2 / 2 and MB 1 / 1 = **hybrid**, mayor only |

⛔ **107 officials — 9× the Atlantic block's 14, and 104 of them in BC.** Because BC has **no ward polygons at all**, its CSD rows are not a redundant second tier: they are the only geometry attaching BC's sitting officials to anything. **A migration dropping CSD rows as contamination would delete British Columbia from the postcode lookup entirely — silently, with no row-count signal.** This is the strongest single argument for A12's revised rule.

### A12.2 — overwrite ratios (west is modest)
| Set | CSD km² | smallest district km² | ratio |
|---|---:|---:|---:|
| `winnipeg-wards` | 474.8 | 8.5 | 56× |
| `saskatoon-wards` | 238.0 | 8.6 | 28× |
| `regina-wards` | 182.5 | 8.0 | 23× |

No extreme case — the three western ward cities are compact. ⚠ **BC cannot be expressed as a ratio at all**: with no ward rows a BC PIP returns exactly one polygon, and it is *correctly* the whole municipality. Nothing to overwrite, nothing to fix.

### ★ Incidental find for the ON dossier — A12.1's "where to look next", located
The three surviving two-tier Ontario regions A12.1 flags are already in the DB, and they are **filed inside the `census-subdivisions` source_set under a `census-divisions/` prefix** — a set/prefix mismatch that hides them:

| `constituency_id` | name | km² |
|---|---|---:|
| `census-divisions/3538` | Lambton | 3,036.3 |
| `census-divisions/3526` | Niagara | 1,883.9 |
| `census-divisions/3530` | Waterloo | 1,385.3 |
| `census-divisions/3521` | Peel | 1,256.2 |

All four are `level='municipal'`, `province_territory='ON'`. Peel is the known case; **Niagara, Waterloo and Lambton are the predicted ones and they are present**, so A12.1's prediction holds. Handing this to whoever owns the Ontario dossier — it is outside both of mine.
