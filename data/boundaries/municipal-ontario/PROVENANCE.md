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
| `current/ottawa-wards-2022.geojson` | https://services.arcgis.com/G6F8XLCl5KtAlZ2G/arcgis/rest/services/Wards_2022_2026/FeatureServer/0/query?where=1=1&outFields=*&outSR=4326&f=geojson | 2026-08-27T17:2xZ | 390479 | `a2882b9b6e85e7530778fd3e3c681bb39b8b7715af1612a59422f2b28f1085e1` | City of Ottawa Open Data Licence 2.0 — licenseInfo is a bare URL, no licence name |
| `current/ottawa-wards-2026.geojson` | https://maps.ottawa.ca/arcgis/rest/services/Planning/MapServer/277/query?where=1=1&outFields=*&outSR=4326&f=geojson | 2026-08-27T17:2xZ | 435256 | `ad6a593b73ad98e95d59677b8dd64e79c949bd86c21178fff10b2626154eabd3` | as above |
| `current/hamilton-wards-2018.geojson` | https://services.arcgis.com/rYz782eMbySr2srL/arcgis/rest/services/Ward_Boundaries/FeatureServer/7/query?where=1=1&outFields=*&outSR=4326&f=geojson | 2026-08-27T17:2xZ | 1393152 | `3fe79f8c9c4e70fed6cd9a69fccb21264473d0b7f0127dcc7afb3e0d613e9f78` | "Open Data Licence Terms and Conditions", hamilton.ca |
| `current/mississauga-wards-2006.geojson` | https://services6.arcgis.com/hM5ymMLbxIyWTjn2/arcgis/rest/services/Ward_Boundaries/FeatureServer/2/query?where=1=1&outFields=*&outSR=4326&f=geojson | 2026-08-27T17:2xZ | 307733 | `44f12c203dcbdbebfda60b0a3b9685a7c41fb7b0f6cf95f467d71f479ceaeeb0` | "Terms of Use" PDF — the linked smartcity.mississauga.ca copy 403s; live copy at www5.mississauga.ca |
| `current/brampton-wards-2014.geojson` | https://services3.arcgis.com/rl7ACuZkiFsmDA2g/arcgis/rest/services/Planning_Local_Government/FeatureServer/3/query?where=1=1&outFields=*&outSR=4326&f=geojson | 2026-08-27T17:2xZ | 90716 | `57c2c17105396c4c1cad236eae520d8624b8cf223578654d3f6dfa56a6f8e0a2` | ⚠ **unresolved** — licenseInfo is the bare string "CC BY", no version, no URL |
| `current/london-wards-2018.geojson` | https://maps.london.ca/server/rest/services/OpenData/OpenData_Elections/MapServer/8/query?where=1=1&outFields=*&outSR=4326&f=geojson | 2026-08-27T17:2xZ | 370418 | `e5f51d74093bcd721ee35052dc22ee693fe44e8ef1b14a2a7eb8aae6c760f258` | ⚠ **none stated** — licenseInfo empty; Hub "Terms of Use" link is `href="#"` |
| `current/london-wards-2026.geojson` | https://maps.london.ca/server/rest/services/OpenData/OpenData_Elections/MapServer/9/query?where=1=1&outFields=*&outSR=4326&f=geojson | 2026-08-27T17:2xZ | 373414 | `03bc1953c14ee9c887b9640ece6278d062974923bf7e930d69e52d64f500e7f8` | ⚠ **none stated** — as above |
| `current/windsor-wards-2010.geojson` | https://mappmycity.ca/arcgis/rest/services/OpenDataServices/Boundaries/MapServer/5/query?where=1=1&outFields=*&outSR=4326&f=geojson | 2026-08-27T17:2xZ | 117498 | `d8751e1f83488ab75fea29960c9de8b28a53ff92bf25ea092a58b88e9fd6e74f` | City of Windsor Open Data Terms of Use (PDF, 200) |
| `current/kingston-districts-2014.geojson` | https://services1.arcgis.com/5GRYvurYYUwAecLQ/arcgis/rest/services/Electoral_District_Boundary/FeatureServer/0/query?where=1=1&outFields=*&outSR=4326&f=geojson | 2026-08-27T17:2xZ | 112252 | `c1d16510e6067da1596d0c01fd72fbce95f58d2c3f95b1c7e1dd371f3a19f12e` | City of Kingston Open Data License (PDF, 200) |
| `current/sudbury-wards-2006.geojson` | https://services.arcgis.com/q3mIlR87lZlZsds3/arcgis/rest/services/Ward_Boundaries/FeatureServer/0/query?where=1=1&outFields=*&outSR=4326&f=geojson | 2026-08-27T17:2xZ | 448712 | `645e6644a2e41bca91d23d0e8c16fb2dc7dd3faf68fce035a3ad674b7974a277` | Greater Sudbury Open Data Licence (OGL-Ontario 1.0) — portal level only, licenseInfo empty |

## Ontario large cities — staged 2026-08-27

Eight municipalities plus two future generations. ⚠ **Ruling A10.4 in-force dates
span twenty years** — 2006-11-13 (Mississauga, Greater Sudbury), 2010-10-25
(Windsor), 2014-10-27 (Brampton, Kingston), 2018-10-22 (Hamilton, London),
2022-10-24 (Ottawa). The mirror stamped every one `2023-01-01`. Note 2006-11-13
is a **Monday in November**: Ontario's fixed fourth-Monday-of-October rule starts
with 2010, so a generated date is wrong for anything earlier.

- ⛔ **`london-wards-2018.geojson` comes from a layer titled "Election 2022
  Wards".** It is geometrically identical to London's own "Election 2018 and
  2022" layer (0 of 14 wards differ by >0.5%) and differs from the 2014 layer in
  8 of 14, so its in-force date is **2018**. The file was renamed on staging so
  its name stops asserting the wrong vintage. All four London vintages have 14
  wards numbered 1-14 — count, name and number are useless discriminators here.
- ⛔ **Kingston's rows carry `ELECTION_YEAR = '2022'` and `CURRENT_ = 'Y'`.**
  That is a roster-currency stamp, not a boundary date; mapping it to
  `effective_from` dates Kingston two full election cycles late. The boundary
  date exists only in the layer's prose description.
- ⚠ **Layer index is almost never 0** — Hamilton 7, Windsor 5, Brampton 3,
  Mississauga 2, London 8/9, Ottawa-2026 277. `/FeatureServer/0` returns HTTP 200
  with empty metadata and then a 400 on `/query`, which reads as a working fetch
  until you count features.
- ⚠ **Three of ten responses omit the GeoJSON `crs` member** even though
  `outSR=4326` was honoured (London ×2, Windsor, Ottawa-2026). Verify the CRS by
  reading a coordinate, never by trusting that member.
- ★ **Windsor gains a ward we never had.** We held 9 of 10; Ward 2 was absent.
- Discovery technique correction: `<host>/sharing/rest/portals/self` does **not**
  work on ArcGIS Hub tenancies — all eight city hosts returned non-JSON. Use
  `https://hub.arcgis.com/utilities/domains/<host>` for the org id, then search
  `orgid:<ID>`. And search **ward, district, boundaries AND election** — Kingston
  uses "district" throughout and returns nothing for "ward", while Hamilton's
  current layer surfaces only under "boundaries" (a "ward" search returns its
  2001-2018 predecessor, a confidently-wrong pick with a plausible count).

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
