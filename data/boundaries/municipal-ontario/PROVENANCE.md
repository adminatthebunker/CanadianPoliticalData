# Municipal Ontario — boundary file provenance

Staged by the boundary-research pass on 2026-08-18. Files themselves are gitignored;
this table is the committed audit trail. See
[`../../../docs/research/boundaries/municipal-ontario.md`](../../../docs/research/boundaries/municipal-ontario.md).

⚠ **Representative, not exhaustive.** Ontario is 48 source sets across ~40 independent municipal
publishers with no provincial federation, so a complete harvest is a build-phase job. Toronto
was staged because it is the largest single set, the ruling-A6 exemplar, and the only Ontario
publisher offering multiple generations from one endpoint.

| File | Source URL | Retrieved (UTC) | Bytes | sha256 | Licence |
|---|---|---|---|---|---|
| `current/toronto-city-wards-4326.geojson` | https://ckan0.cf.opendata.inter.prod-toronto.ca/dataset/5e7a8234-f805-43ac-820f-03d7c360b588/resource/737b29e0-8329-4260-b6af-21555ab24f28/download/city-wards-data-4326.geojson | 2026-08-18T01:31Z | 1148140 | `a35851f39c83e492c7dde7a8949847844ef1697a3155bb670155a3d1812daf64` | ⚠ **unstated** — CKAN reports "License not specified" |
| `prior/toronto-44-ward-model-2010-wgs84.zip` | https://ckan0.cf.opendata.inter.prod-toronto.ca/dataset/5e7a8234-f805-43ac-820f-03d7c360b588/resource/d96d198c-fb5b-4229-a586-7673c45e80e7/download/44-ward-model-may-2010-wgs84-latitude-longitude.zip | 2026-08-18T01:31Z | 307071 | `aa9f2d12ebc0e7a7b829879d6253a29ec7608a6218cade992be23e08eeeb8fb5` | ⚠ **unstated** — as above |

## Notes

- Both files come from the **`city-wards` dataset** on `open.toronto.ca` (CKAN at
  `ckan0.cf.opendata.inter.prod-toronto.ca/api/3`), which carries the **25-ward model
  (current), the 44-ward model, and the 47-ward model** side by side, in GeoJSON / SHP / GPKG /
  CSV across EPSG:4326, 2945 and 2952. Current *and* two priors from one endpoint — the richest
  Ontario source in the block.
- ⚠ **Licence is not machine-readable.** CKAN reports `license_title: None` and
  `"License not specified"` on `city-wards`. The Open Government Licence – Toronto governs the
  portal in practice but is **not asserted in the dataset metadata**, so it was not read and is
  not quoted. Recorded as unresolved rather than assumed.
- ⚠ **Prefer the explicit resource URLs above over the CKAN datastore dump endpoint**
  (`/datastore/dump/7672dac5-...`), which returns a different serialisation and is not
  CRS-labelled.
- Toronto also publishes `wards-and-elected-councillors` — a combined boundary + roster layer
  in GeoJSON / CSV / SHP / GPKG. Not staged; likely useful for roster reconciliation.
- **Not staged, deliberately:** the 47-ward model and the MTM/NAD27 CRS variants (same content);
  the other ~39 Ontario municipalities (build-phase harvest, mostly ArcGIS Hub FeatureServers);
  polling subdivisions (out of scope, and large enough to hit `maxRecordCount` truncation).
- ⛔ **What we hold in the database is not what these files contain.** `toronto-wards-2018`
  holds 25 ward polygons **plus one `census-subdivisions/3520005` row** (the City of Toronto
  polygon), which causes point-in-polygon at Toronto City Hall to return two matches. See the
  dossier's tier-contamination section — 40 of Ontario's 48 sets have the same defect.
