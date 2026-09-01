### licence
| Jurisdiction | Rows held | Source | Licence | Internal use | Redistribution | Notes |
|---|---:|---|---|---|---|---|
| [Federal](../federal.md) | 342 | Elections Canada — `ftp.maps.canada.ca` (`FED_CA_2023_EN-SHP`, `FED_CA_2021_EN`); StatCan `lfed000a16a_e` as prior cross-check | ✅ **Open Government Licence – Canada 2.0** (`ca-ogl-lgo`), https://open.canada.ca/en/open-government-licence-canada | ✅ **yes** | ✅ **yes** | ★ The only jurisdiction cleared for both. No click-through, no registration, no account. Attribution required: "Contains information licensed under the Open Government Licence – Canada." + provider string "Government of Canada; Elections Canada; Electoral Geography Division". Class A — transfers on its own terms, nothing inherited from Open North |

### coverage
| Jurisdiction | Rows held | Seats | Authoritative count | Vintage held | Current vintage | Delta |
|---|---:|---:|---:|---|---|---|
| [Federal](../federal.md) | 342 | 343 | 343 | ✅ **2023 Representation Orders — correct, current** | 2023 Representation Orders (SI/2023-57, proclaimed 2023-09-22), in force 2025-03-23 | ★ **Exactly 1 missing: `24077` Ville-Marie—Le Sud-Ouest—Île-des-Soeurs** (QC). 342/342 held slugs match a `FED_NUM` exactly, zero non-authoritative extras. QC is the only short province (77/78); all 12 other jurisdictions complete. ⚠ 3 name strings drift (typographic apostrophes ×2, one stray space). ✅ Prior generation (2013 Order, 338) also staged |

### A6 prefix migration
| Jurisdiction | Current prefix | Target prefix | `politicians` | `politician_terms` | `constituency_boundaries` | Total |
|---|---|---|---:|---:|---:|---:|
| [Federal](../federal.md) | `federal-electoral-districts-2023-representation-order` | `federal-electoral-districts` | 342 | 11 | 342 | **695** |

Pure `replace()` substitution, reversible with the inverse. ⚠ **Amends this dossier's original "re-key cost is zero" claim** — the *suffix* finding stands exactly (our slug **is** the `FED_NUM`, 342/342), but the prefix encodes a generation and must change. ✅ The `authority_district_id = split_part(constituency_id, '/', 2)` backfill is **unaffected** by the prefix change, so the two migrations are order-independent. After the change both generations share one `constituency_id` per district, with `boundaries_version` separating the 338 from the 343 — which is exactly A6's intent.

### cross-jurisdictional findings from this dossier
- ⚠ **`.prj` files may carry no `AUTHORITY` clause.** Elections Canada's is named only `PCS_Lambert_Conformal_Conic`; EPSG:3347 is established from the parameters (false easting 6200000, false northing 3000000, central meridian −91.86666666666666, standard parallels 49/77, latitude of origin 63.390675). The build must `ST_SetSRID(geom, 3347)` explicitly.
- ⚠ **One district per row is not guaranteed.** `FederalElectoralDistricts_2025_SHP` has **352 records for 343 districts** (6 districts stored as separate island rows: Halifax ×2, Côte-Nord ×3, Gaspésie ×2, Brandon—Souris ×2, Selkirk—Interlake—Eastman ×4, Courtenay—Alberni ×2). Count DISTINCT district IDs, not records. The recommended `FED_CA_2023_EN-SHP` does not have this problem.
- ⚠ **Two files from one agency for one generation can use different field names** — `REP_ORDER`/`SHAPE_AREA`/`SHAPE_LEN` vs `REPORDER`/`SHAPE_Leng`/`SHAPE_Area`.
- ⚠ **`.CPG` may have an UPPERCASE extension** — a case-sensitive `*.cpg` glob misses it and mojibakes every accented Quebec name.
- ⚠ **Cartographic vs digital is a difference of EXTENT, not resolution.** StatCan's cartographic file is the **larger** one (2021: 139 MB vs 11 MB digital) because following the real coastline costs more vertices than cutting across water. **Not** a generalised product; `boundary_simple` still needs `ST_SimplifyPreserveTopology`.
- ⚠ **StatCan serves HTTP 200 error pages** for wrong-vintage paths (a 4,099-byte body under the wrong year directory). Compare `Content-Length`, not status codes.
- ⚠ **`ourcommons.ca/members/en/search/xml` answers `HEAD` with a 302→404 but `GET` with 200** and 158 KB of valid XML. A HEAD-first liveness probe reports it dead when it is healthy.
- ★ **A reprojection-free path exists** — the geo.ca ESRI REST layer accepts `outSR=4326&f=geojson`, supports pagination, and returns all 352 features in one request.
- ✅ **Senate: all 97 `constituency_id IS NULL` rows are CORRECT, not a gap.** Senators represent provinces (and in Quebec, senatorial divisions), never electoral districts. Never fill these from the FED layer.
- ⚠ **The district↔MP join is the real federal weakness, not the geometry** — only **11 of 1,873** federal `politician_terms` rows carry a `constituency_id`. `ourcommons.ca` XML resolves 338/338 sitting MPs to a FED code after apostrophe normalisation, but publishes **no FED code**, so the name match is the only bridge. Its stable `PersonId` is a candidate `politicians.ourcommons_person_id` per CLAUDE.md convention #1.
- ⛔ **No open postal-code↔FED concordance exists.** StatCan's PCFRF (92-178-X) is $892/yr, co-distributed with Canada Post, and keyed to the **superseded** 2013 Order. Not needed — PIP against authoritative polygons strictly beats a weighted concordance.
