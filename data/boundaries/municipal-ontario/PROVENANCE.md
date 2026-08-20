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

## niagara-region-ward-boundaries.geojson — added 2026-08-20

| field | value |
|---|---|
| source | `https://services1.arcgis.com/WxiLK82TWf8W3O3f/arcgis/rest/services/VoterTool_data/FeatureServer/1/query?where=1=1&outFields=*&outSR=4326&f=geojson` |
| publisher | Niagara Region (AGOL org `WxiLK82TWf8W3O3f`, item `7f3c6df70c59428e9206807b83847e3d`) |
| retrieved | 2026-08-20 UTC |
| bytes | 1486062 |
| sha256 | `dda887c72a07e48a11acc1afe38c281547ea8db53b815783b7cee981fe15ea35` |
| licence | item carries a real `licenseInfo` — a Niagara Region reference-use disclaimer. Clause text not fetched; recorded as unread rather than paraphrased. |
| item modified | 2018-10-17 (the 2018 municipal election) |

**44 features / 12 lower-tier municipalities**, fields `OBJECTID`, `WARD`,
`MUNICIPALITY`, `Shape__Area`, `Shape__Length`. Requested at `outSR=4326`; the
returned file declares EPSG:4326 and the first coordinate is
`[-78.9406864382203, 42.9125636059333]` — degrees, consistent.

★ **How it was found, because the method generalises.** `/sharing/rest/search` on a
city's *own* AGOL host is **not scoped to that city** — it queries the global index.
Searching `regina.maps.arcgis.com` for "ward" returns Baltimore, Montana and
Washington D.C. Scope with `orgid:` taken from `<host>/sharing/rest/portals/self`.
Ontario has no provincial ward layer, but an **upper-tier region** publishing a voter
tool covers its lower-tier municipalities in one service — 12 here. Worth probing Peel,
York, Durham, Halton and Waterloo the same way before treating them as ~47 individual
discoveries.

⛔ **St. Catharines excluded** (`row_filter`): its six wards have NAMES (Grantham,
Merritton, Port Dalhousie, St. Andrew's, St. George's, St. Patrick's — two councillors
each) and the Region's voter tool numbers them 1..6. The aggregator is worse than what
we hold; loading it would orphan twelve councillors to replace a name with an ordinal.
38 districts across 11 municipalities load.

⚠ **Niagara Falls elects at large** — its single feature carries
`WARD = "Councillor at Large"`, which a naive label turns into "Ward Councillor at
Large". Loads as `at-large`.

ⓘ **Vintage measured, not assumed** — 18 held wards match at mean 99.43%, min 98.45%
(Grimsby's ward 3), none below 95%. Per the A8.1 refinement that says nothing about
currency if both sides share a lineage; what it establishes is that the load is
additive rather than a substitution.
