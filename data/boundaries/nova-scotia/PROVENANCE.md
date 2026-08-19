# Nova Scotia — boundary staging provenance

Audit trail for files staged under `data/boundaries/nova-scotia/`. File contents are gitignored
(`.gitignore:101`); this record is committed. Dossier:
[`../../../docs/research/boundaries/nova-scotia.md`](../../../docs/research/boundaries/nova-scotia.md).

## current/

| File | Source URL | Retrieved (UTC) | Bytes | sha256 | Licence |
|---|---|---:|---:|---|---|
| `elections-ns-ed-pd-2026-04-09.geojson` | `https://services6.arcgis.com/SLbygoAaBbarfQVN/arcgis/rest/services/ENS_PD_ED/FeatureServer/0/query?where=1%3D1&outFields=*&returnGeometry=true&f=geojson` (paged, `resultRecordCount=400`) | 2026-08-18T01:29Z | 63,873,793 | `ddbae8edaca6a565e732d6ffafd500e164eaba2c262710cc64632fdd9a4d6116` | ⛔ **NONE STATED** — see below |

⛔ **Licence status: unresolved, and this is the headline NS finding.** The AGOL item
(`d9e8704a97f94dd9b517383c1e4e2c07`, owner `Andrew.Cameron_ElectionsNS`) has
`licenseInfo: null` and `accessInformation: null`; the FeatureServer's `copyrightText` is the
empty string. The item description reads *"DO NOT DELETE Electoral Geography for refence in
applications"* — it is an internal service that happens to be publicly readable, **not a
published open-data product**. This file is staged for research only.
**Do not redistribute it, and do not serve it from `/api/public/v1/boundaries/*`, until terms
are obtained from Elections Nova Scotia.** See dossier § Research-handoff items.

**Notes**

- ⚠ **This file is POLLING DIVISIONS, not electoral districts** — **1,817 features** for
  **56 districts**. `ED_NO` + `PD_NO` together are unique (1,817 distinct pairs; verified).
  Loading it naively would create 1,817 `constituency_boundaries` rows for 56 districts. The build
  must dissolve on `ED_NO`. This is the one-row-per-district trap in its most extreme form found
  so far in this project.
- Fields: `OBJECTID`, `ED_NO` (String, zero-padded `'01'`–`'56'`), `ED_NAME`, `PD_NO` (String),
  `IND_POLL`, `RES_CARE`, `SERVICE_AREA`, `RELEASE_DATE` (String, not a date type),
  `electorcount` (Double), `Shape__Area`, `Shape__Length`.
- ⚠ **CRS:** the layer's declared SR is **EPSG:3857 (Web Mercator)** — a *display* projection, not
  a data CRS, which is itself a signal this is a web-map service rather than a data product. As
  with Alberta, `f=geojson` returned **decimal degrees** (first coordinate
  `[-65.586187, 44.757638]`), so ArcGIS reprojected on the way out and the staged file is
  geographic. No `crs` member in the response.
- **`RELEASE_DATE` partitions the file into two generations**: `"September 1, 2020"` on 54
  districts (the 2019 commission set) and `"April 9, 2026"` on exactly two — `ED_NO` 34
  (Inverness, 26 polls, reshaped) and `ED_NO` 56 (Chéticamp-Margarees-Pleasant Bay, 10 polls,
  new). That is the whole footprint of the 2026 change.
- **Assembly note:** the response was paged at 400 records (5 requests, offsets 0/400/800/1200/1600
  returning 400/400/400/400/217) and the `features` arrays concatenated into a single
  FeatureCollection. That is completion of a paginated retrieval, not a transformation — no
  geometry, attribute, or CRS was altered.

## Not staged

- **2025 Electoral Boundaries Commission final report** (released 2026-01-30):
  `https://static1.squarespace.com/static/687953fc91d2d028b8b55a99/t/697ccfa829f00a120ba8cdfe/1769787304458/EBC+2025+Final+Report+EN_2026-01-30.pdf`
  — PDF narrative + maps, not geospatial data. Recorded as the authority for the boundary
  descriptions.
- **Prior generation (2019 commission, 55 districts).** Not separately staged: we already hold it
  as the 55 rows currently in `constituency_boundaries`, and Elections NS's service carries only
  the live geography. The pre-2019 51-district (2012) set was not located on an open surface.
