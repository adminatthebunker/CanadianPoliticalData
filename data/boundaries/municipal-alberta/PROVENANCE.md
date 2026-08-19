# Municipal Alberta boundaries — staged file provenance

Audit trail for `data/boundaries/municipal-alberta/`. Data files are gitignored; this record is committed.
Research dossier: [`../../../docs/research/boundaries/municipal-alberta.md`](../../../docs/research/boundaries/municipal-alberta.md).

⚠ **Licence unresolved — not cleared for redistribution.** Both Calgary's and Edmonton's Socrata
catalogues declare their licence as the literal string `"See Terms of Use"`, with **no `termsLink`**
populated in dataset metadata. No click-through gate was encountered and nothing was accepted or
submitted; the files download over a plain public API. But the actual terms pages were **not read** this
pass, so redistribution is unverified. This differs from the Saskatchewan and Manitoba *provincial*
cases, where no licence exists at all — here one probably does and simply has not been resolved.

| File | Source URL | Retrieved (UTC) | Bytes | sha256 | Licence |
|---|---|---|---|---|---|
| `current/edmonton-wards_nydb-6rce.geojson` | https://data.edmonton.ca/api/geospatial/nydb-6rce?method=export&format=GeoJSON | 2026-08-18T05:31:57Z | 2,049,099 | `04fb61b0bb1ac0c307108b89b19339ec312d37a489bc9889a510279dd9259da5` | ⚠ "See Terms of Use" — unread |
| `current/calgary-wards_tz8z-hyaz.geojson` | https://data.calgary.ca/api/geospatial/tz8z-hyaz?method=export&format=GeoJSON | 2026-08-18T05:31:58Z | 638,679 | `fe5fd01e40b9c83853d22d66181897d26c4b9d8c4062e517816e34bdae8cbb41` | ⚠ "See Terms of Use" — unread |
| `prior/calgary-wards-2017-2021_au4g-xjwh.geojson` | https://data.calgary.ca/api/geospatial/au4g-xjwh?method=export&format=GeoJSON | 2026-08-18T05:34:58Z | 964,611 | `8a6cc13181329076dd3f4e2a90852b32a8f70ff0d05703d75121efef696b5807` | ⚠ "See Terms of Use" — unread |

Total staged: 3,652,389 bytes (3.5 MiB) against a 500 MB agent budget.

## What is in each file

- **`edmonton-wards_nydb-6rce.geojson` — 42 features covering ALL generations in one file.**
  `effdt_type` partitions them: **`Current` = 12** (the in-force 2021 wards, `effective_start_date`
  2021-10-18, open-ended) and **`Historical` = 30** (2007-10-15 → 2021-10-17). Staged under `current/`
  because it is one file; the build should partition on `effdt_type` / the date columns rather than
  expecting a separate prior download.
  ⚠ **The dataset title claims "Current, Historical and Future" but there are zero `Future` rows.**
  Per brief amendment A5, in-force status was established from the date ranges, not the title or label.
  Historical ends 2021-10-17 and Current is open-ended with no break at the 2025 election, so the 2021
  geometry remains in force.
- **`calgary-wards_tz8z-hyaz.geojson` — 14 features, 14 wards**, the current generation.
- **`prior/calgary-wards-2017-2021_au4g-xjwh.geojson` — 14 features, 14 wards**, the 2017–2021
  generation. ★ **This is the generation our 14 `calgary-wards` rows actually match** (mean area error
  0.36%, 14/14 within 2%, versus 4.76% and 6/14 against current). Staged specifically to make that
  comparison reproducible.

## CRS — no reprojection needed

✅ **All three files are EPSG:4326 (WGS84).** Verified by inspection rather than assumed: none carries a
`crs` member, so RFC 7946's WGS84 default applies, and the coordinates are degree-scaled
(Calgary's first vertex is `[-114.2111288, 51.1833656]`). There is no `.prj` to parse and no
`ST_Transform` step — a categorical simplification versus the provincial shapefiles (federal EPSG:3347,
SK 26913, MB 26914).

⚠ **Do not generalise this to all municipal GeoJSON.** Regina's, in `../municipal-west/`, is EPSG:26913
projected metres with an explicit legacy `crs` member.

## Not staged (deliberate)

| Source | Why not |
|---|---|
| Calgary `9u83-tgux` — Ward Boundaries 2013–2017 | A third generation; available and cheap, but out of scope for current + immediately-prior |
| Strathcona County (8 wards) | ⚠ **UNTESTED** — `data.strathcona.ca` resolves (HTTP 200) but is not CKAN; publisher not located |
| Regional Municipality of Wood Buffalo (4 wards) | ⚠ **UNTESTED** — publisher not located |
| County of Grande Prairie No. 1 (9 divisions) | ⚠ **UNTESTED** — publisher not located. ⛔ This is the set whose polygons cover 100% of the City of Grande Prairie; see the dossier |
| City of Grande Prairie, Lethbridge | ★ Both elect **at large** — no ward data exists to stage (A10.3) |

Those four untested sets account for **21 of Alberta's 53 rows**, all of unknown vintage. Per A7 their
matching district counts prove nothing.
