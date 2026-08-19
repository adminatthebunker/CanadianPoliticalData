# Municipal West (BC / SK / MB) boundaries — staged file provenance

Audit trail for `data/boundaries/municipal-west/`. Data files are gitignored; this record is committed.
Research dossier: [`../../../docs/research/boundaries/municipal-west.md`](../../../docs/research/boundaries/municipal-west.md).

⚠ **All three licences are UNREAD, not absent — and one is actively wrong.** Winnipeg's Socrata declares
its licence as `"Open Government Licence - Prince Edward Island"` on a Manitoba dataset, which is a
misconfigured licence picker and cannot be relied on. Saskatoon's ArcGIS item reports `license: none`.
Regina's terms page could not be read because `www.regina.ca` returns HTTP 403 to automated clients.
No click-through gate was encountered anywhere and nothing was accepted or submitted. **Internal
research use is defensible; redistribution is unverified for all three.**

| File | Source URL | Retrieved (UTC) | Bytes | sha256 | Licence |
|---|---|---|---|---|---|
| `current/winnipeg-electoral-wards.geojson` | https://data.winnipeg.ca/api/geospatial/t4cg-yaxs?method=export&format=GeoJSON | 2026-08-18T01:30:22Z | 329,525 | `687e9e9195ea3330d161ca8e9994913e0c6fb898a88fecca62953d3c384d2236` | ⚠ declared "OGL – Prince Edward Island" — **wrong, unread** |
| `prior/winnipeg-electoral-wards-2014-2018.geojson` | https://data.winnipeg.ca/api/geospatial/mp2r-jeav?method=export&format=GeoJSON | 2026-08-18T01:30:25Z | 207,541 | `51bb1c9cbf1dd6a7d34189564419b46fe59d0d135234946a6123adc2e69abbc2` | ⚠ same |
| `current/regina-wards-2024.geojson` | ⚠ **not recorded** — staged earlier in this run; `www.regina.ca` returns HTTP 403 to automated clients | 2026-08-18T01:35:51Z | 179,628 | `28a9373108181fbcdf6e6f3dad3c9116b975f7f16521ae399553aedde5284ea8` | ⚠ unread |
| `current/regina-wards-2024_shp.zip` | ⚠ **not recorded** — as above | 2026-08-18T01:38:22Z | 45,074 | `bc14493e1c0a44f87cae2ac3eec809120bd3f3015b48a4cd6ab58e5f7d593be6` | ⚠ unread |
| `prior/regina-wards-2020_shp.zip` | ⚠ **not recorded** — as above | 2026-08-18T01:38:23Z | 35,626 | `bd8c8ba8ca8b22759bbd604282e17c67bdf5f0d8ef3edc0993dd921f89c948c8` | ⚠ unread |
| `current/saskatoon-wards_arcgis.geojson` | https://services6.arcgis.com/doi7PAc643EKEEOk/arcgis/rest/services/Saskatoon_Ward_Boundaries/FeatureServer/0/query?where=1=1&outFields=*&outSR=4326&f=geojson | 2026-08-18T05:32:34Z | 156,887 | `c7d0c3d47665df82d54bbe2b990ec094c0c34d6212e88dad5916290160c24f61` | ⛔ `license: none`, **provenance unverified** |

Total staged: 954,281 bytes (932 KiB) against a 500 MB agent budget.

## ⚠ Provenance caveats — read before loading anything here

- **Regina's three files were staged earlier in this run by another agent**, under a per-city subtree,
  and arrived **without a recorded source URL**. Their inner shapefile mtimes (2024-10-02 and
  2020-10-16) are consistent with authentic City of Regina publications, and the schemas
  (`ELECT_YEAR`, `POPULATION`, `VOTE_POP`, and a 2020 `URL` field pointing at `regina.ca` ward pages)
  corroborate that. But **I could not independently reach the origin to verify**, so the citation above
  is an honest blank rather than a guess. Recovering it is a handoff item.
- ⛔ **Saskatoon's file is a CANDIDATE, not an accepted source.** The ArcGIS Online item
  (`b9fff26dba5a4f5c9e1425e4f9d21654_0`) has an **empty `copyrightText`, an empty description, and
  `orgName: None`** — it is not attributable to the City of Saskatoon. Standing instruction 1 requires
  primary sources, so **do not load this file** until its provenance is established. It is staged only
  so the next agent does not have to rediscover it.

## Layout reconciliation

The Regina and Winnipeg files were originally staged under a per-city subtree
(`municipal-west/regina/current/`, `municipal-west/winnipeg/current/`, plus an empty `saskatoon/`),
which also left a **duplicate copy of the Winnipeg GeoJSON**. I consolidated everything into the flat
`current/` + `prior/` layout used by the brief and by the three finished municipal dossiers
(`municipal-ontario`, `municipal-quebec`, `municipal-atlantic`). The duplicate was confirmed
**byte-identical by sha256** before removal; no file contents were altered.

## What is in each file

| File | Features | Distinct districts | Notes |
|---|---:|---:|---|
| `winnipeg-electoral-wards.geojson` | 15 | 15 | ★ carries `councillor`, assistant, ward clerk, phones, `winnipeg.ca` URL |
| `winnipeg-electoral-wards-2014-2018.geojson` | 15 | 15 | subset schema — no `asst` / `clerk` / `website` |
| `regina-wards-2024.geojson` / `.zip` | 10 | 10 | ★ `ELECT_YEAR=2024` self-documents the generation |
| `regina-wards-2020_shp.zip` | 10 | 10 | ⚠ `SHAPE_AREA`/`SHAPE_LEN` are **empty strings** despite being declared `F(31,15)` |
| `saskatoon-wards_arcgis.geojson` | **13** | **10** | ⚠ multipart split (W1×2, W5×2, W6×2) — count DISTINCT, not records |

## CRS — mixed, and one file is a trap

| File | CRS | Notes |
|---|---|---|
| Winnipeg (both) | ✅ **EPSG:4326 (WGS84)** | no `crs` member → RFC 7946 default; first vertex `[-97.145127, 49.935762]` |
| Saskatoon | ✅ **EPSG:4326** | requested explicitly via `outSR=4326` on the FeatureServer query |
| **Regina (both generations)** | ⚠ **EPSG:26913 — projected metres, NOT WGS84** | carries an explicit legacy `crs` member; first vertex `[535248.19, 5591196.13]` |

★ **The Regina case is worth promoting as a general trap.** RFC 7946 mandates WGS84 and removed the
`crs` member entirely, so "it is GeoJSON, therefore it is 4326" sounds safe and is **wrong here** — and
it fails *silently*, placing Regina's wards in the Gulf of Guinea rather than raising an error. It
produced a bogus 100%-error reading in my first vintage check before I caught it. **Check coordinate
magnitude on every GeoJSON regardless of extension.** Regina's bundled `.prj` says
`NAD_1983_UTM_Zone_13N` with ⚠ no `AUTHORITY` clause (brief amendment A4), so the build must
`ST_SetSRID(geom, 26913)` explicitly before `ST_Transform`.

## Nothing staged for British Columbia — deliberate

★ **There are no BC ward boundaries to stage, and that is correct rather than a gap.** Under the Local
Government Act at-large election is BC's **statutory default**; wards ("neighbourhood constituencies")
require a bylaw approved by the Lieutenant Governor in Council. All 12 BC rows in
`constituency_boundaries` are whole-municipality Census Subdivision polygons, whose authoritative source
is Statistics Canada — federal territory, not a municipal one. **No BC agent-hours should be spent
hunting for ward data that cannot exist.**
