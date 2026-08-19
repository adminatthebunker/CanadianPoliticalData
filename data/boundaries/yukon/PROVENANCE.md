# Yukon — boundary file provenance

Staged by the boundary-research pass on 2026-08-18. Files themselves are gitignored;
this table is the committed audit trail. See [`../../../docs/research/boundaries/yukon.md`](../../../docs/research/boundaries/yukon.md).

**Generation staged:** `current` only. The `prior` generation (2015 order, 19 districts) is
**not retrievable** — GeoYukon overwrote the layer in place and the `open.canada.ca` mirrors
were delisted. See the dossier's Research-handoff items.

| File | Source URL | Retrieved (UTC) | Bytes | sha256 | Licence |
|---|---|---|---|---|---|
| `current/Yukon_Electoral_Districts.shp.zip` | https://map-data.service.yukon.ca/GeoYukon/Administrative_Boundaries/Yukon_Electoral_Districts/Yukon_Electoral_Districts.shp.zip | 2026-08-18T00:48:37Z | 132056 | `61defe5f5fb42686485e9f2997eafd287c84bea0575222f33fd09e260a3ad095` | Open Government Licence – Yukon 2.0 |
| `current/Yukon_Electoral_Districts.kmz.zip` | https://map-data.service.yukon.ca/GeoYukon/Administrative_Boundaries/Yukon_Electoral_Districts/Yukon_Electoral_Districts.kmz.zip | 2026-08-18T00:48:37Z | 173925 | `e36c6088ad52ba84984d2e721ce0c9339c7018f7f70e1197a14ee24dccf77ece` | Open Government Licence – Yukon 2.0 |
| `current/Approved_Yukon_Electoral_Districts_2024.geojson` | https://services.arcgis.com/bwohQix8s7zRvYC9/arcgis/rest/services/Approved_Yukon_Electoral_Districts_2024/FeatureServer/0/query?where=1%3D1&outFields=*&outSR=4326&f=geojson | 2026-08-18T00:54Z | 290264 | `ee40d6fe95b57647472b563e313944f583b89759703b1a14e45993af033d2be3` | Open Government Licence – Yukon 2.0 |

## Notes

- The `.geojson` is the **recommended build input**: already EPSG:4326, so no reprojection
  step. Verified identical to the shapefile on feature count (21), district-name set, and
  spot-checked geometry — and the two come from *different publishers* (Elections Yukon's
  AGOL org vs GeoYukon), so the agreement is a real cross-check.
- The `.shp.zip` is the **durable archive copy and native-CRS reference**: published by
  Government of Yukon on behalf of Elections Yukon in `NAD_1983_Yukon_Albers` (**EPSG:3578**
  — parameter-matched, the WKT carries no `AUTHORITY` node; **not** 3579, the datum is plain
  NAD83). Same content the CEO issued dated 2024-11-21. Bundles a `disclaimer.pdf` (2014-06-05).
- Shapefile structure checks: 21 records → **21 distinct district names**, no duplicate-key
  risk; **max parts = 1**, every district a single simple polygon; `.cpg` is lowercase and
  declares UTF-8.
- ⚠ The `open.yukon.ca` CKAN resource advertised as "All resource data"
  (`.../download/yukon-electoral-districts-aatjwnxi.zip`) is an **832-byte stub**, not the
  data. Do not use it. Go to `map-data.service.yukon.ca` directly.
