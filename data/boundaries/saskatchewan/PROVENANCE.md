# Saskatchewan electoral boundaries — staged file provenance

Audit trail for `data/boundaries/saskatchewan/`. Data files are gitignored; this record is committed.
Research dossier: [`../../../docs/research/boundaries/saskatchewan.md`](../../../docs/research/boundaries/saskatchewan.md).

⛔ **Licence is NOT cleared.** Elections Saskatchewan publishes no open licence — the only statement
anywhere on `elections.sk.ca` is the footer string `Copyright © 2025 Elections Saskatchewan`. There is
no click-through agreement and no registration wall (nothing was accepted or submitted), but there is
also no affirmative grant to reuse or redistribute. Treat these files as **staged pending operator
licence clearance**; do not serve derived geometry from `/api/public/v1/boundaries/*` until resolved.

| File | Source URL | Retrieved (UTC) | Bytes | sha256 | Licence |
|---|---|---|---|---|---|
| `current/ESK_KML_Shape_Files_Mar2024.zip` | https://cdn.elections.sk.ca/maps-ge30/ESK_KML_Shape_Files_Mar2024.zip | 2026-08-18T01:10:06Z | 12,223,644 | `d865ff66e1201eb633fe6667ac60bd4412c6a88285216daabc6a8276dc073d63` | ⛔ Crown copyright, no open licence |
| `prior/Elections_SK_constituency_shape_files_GE29.zip` | https://cdn.elections.sk.ca/maps-ge29/Elections_SK_constituency_shape_files_GE29.zip | 2026-08-18T01:30:25Z | 1,763,172 | `1fc1e1d811936ca138b1c389da09ae235b91fa0ed5e7643388c8105429751398` | ⛔ Crown copyright, no open licence |

Total staged: 13,986,816 bytes (13.3 MiB) against a 500 MB agent budget.
Upstream `Last-Modified` (current): `Fri, 08 Mar 2024 22:52:46 GMT`.

## What is inside the archive

⚠ **Nested zips.** The outer archive is a macOS-created bundle (it carries `__MACOSX/` and `.DS_Store`
entries). The constituency shapefile is a **zip inside the zip**:

```
ESK_KML_Shape_Files_Mar2024.zip
├── KML/ConstituencyGE30th.kmz                        1,471,529
├── KML/VotingAreas_30thGE.kmz                        5,760,989
├── ShapeFile/Constituency/Constituency30th.zip         971,204  ← the one we want
│   └── ConstituencyGE30th.{shp,shx,dbf,prj,cpg,sbn,sbx}
└── ShapeFile/Voting Areas/VotingAreas_30thGE.zip     4,046,488
```

`ConstituencyGE30th.dbf` holds **61 records / 61 distinct districts**, one row per district (no
multipart split). `ConstituencyGE30th.prj` is NAD83 / UTM zone 13N = **EPSG:26913**, with no
`AUTHORITY` clause. Encoding is UTF-8, declared in a lowercase `.cpg`.

## ★ Prior generation — staged, recovered via Wayback CDX

`Elections_SK_constituency_shape_files_GE29.zip` is the **2012 Representation Act** generation, used at
the 29th General Election (2020). It unpacks directly (no nesting) to
`Constituency.{shp,shx,dbf,prj,sbn,sbx}` — **61 records / 61 distinct `Con_Name`**, EPSG:26913 with a
`PROJCS` string byte-identical to the current generation. ⚠ **No `.cpg`** — encoding is undeclared.

**How it was found.** Direct probing failed: four guessed filenames under `maps-ge29/` all returned 404,
and the dossier initially recorded the prior generation as unobtainable. The Wayback CDX index over
`cdn.elections.sk.ca/*` listed 16 archived archives, including this one, and the file proved **still
live at the origin** — Elections Saskatchewan retains `maps-ge29/` but no longer links to it from any
page. Per brief amendment A5, in-force status was established from **content** (its 61 names, and the
fact that our 46 stored polygons reproduce its geometry to a median of 0.07%), not from the `GE29`
filename.

⚠ **Unit trap in this file:** `AreaKM` is already km² while `Shape_Area` is m². Use `Shape_Area/1e6` for
any comparison against the current generation, which publishes only `Shape_Area`.

## Not staged (deliberate)

| File | Bytes | Why not |
|---|---:|---|
| `ShapeFile/Voting Areas/VotingAreas_30thGE.zip` (inside the archive) | 4,046,488 | Voting areas — sub-constituency geography, out of scope for `constituency_boundaries` |
| `KML/*.kmz` (inside the archive) | 7,232,518 | KML duplicates of the same geometry; the shapefile is the better input |
| https://cdn.elections.sk.ca/maps-ge30/ESK_GE30_Maps_May2024.zip | — | Raster/PDF map sheets, not vector data |
