# British Columbia — boundary staging provenance

Audit trail for files staged under `data/boundaries/british-columbia/`. The files
themselves are gitignored; this record is committed. Research dossier:
[`../../../docs/research/boundaries/british-columbia.md`](../../../docs/research/boundaries/british-columbia.md).

All files retrieved from **DataBC** (`catalogue.data.gov.bc.ca` / `openmaps.gov.bc.ca`),
the BC Data Catalogue, which republishes Elections BC's authoritative spatial data.
Data owner on every record is **Elections BC**. Nothing was converted, reprojected, or
loaded; both GeoJSON files were requested in their **native EPSG:3005** via `srsName`.

| File | Source URL | Retrieved (UTC) | Bytes | sha256 | Licence |
|---|---|---|---|---|---|
| `current/ebc-electoral-districts-2023-bs11-epsg3005.geojson` | https://openmaps.gov.bc.ca/geo/pub/WHSE_ADMIN_BOUNDARIES.EBC_ELECTORAL_DISTS_BS11_SVW/ows?service=WFS&version=2.0.0&request=GetFeature&typeName=pub:WHSE_ADMIN_BOUNDARIES.EBC_ELECTORAL_DISTS_BS11_SVW&outputFormat=application/json&srsName=EPSG:3005 | 2026-08-18 01:04 | 21,828,718 | `2b784a5d12b5baf28c4050eb57798fed956eb561b63fdb5d46fbff6ed4edfe96` | Elections BC Open Data Licence |
| `prior/edsre2015.zip` | https://catalogue.data.gov.bc.ca/dataset/9530a41d-6484-41e5-b694-acb76e212a58/resource/34eedf53-c60b-4237-bf6e-81228a51ab12/download/edsre2015.zip | 2026-08-18 01:04 | 6,721,791 | `28de16c169c9167c16d9788bcec58a48fd3f0a76139110cb286ee13831a15562` | Elections BC Open Data Licence |
| `prior/ebc-electoral-districts-2015-bs10-epsg3005.geojson` | https://openmaps.gov.bc.ca/geo/pub/WHSE_ADMIN_BOUNDARIES.EBC_ELECTORAL_DISTS_BS10_SVW/ows?service=WFS&version=2.0.0&request=GetFeature&typeName=pub:WHSE_ADMIN_BOUNDARIES.EBC_ELECTORAL_DISTS_BS10_SVW&outputFormat=application/json&srsName=EPSG:3005 | 2026-08-18 01:06 | 13,324,804 | `66d779df5753020ca1e16da2ada6e1184cf5d0f17b8ec66ab92d8aa4ef01ba69` | Elections BC Open Data Licence |

**Total staged: 41.9 MB** of the 500 MB agent budget (53 MB on disk including the
unzipped shapefile working copy below).

## Notes

- `prior/edsre2015/` is an **unzipped working copy** of `edsre2015.zip`, extracted only to
  `cat` the `.prj` and parse the `.dbf` header per the no-GDAL procedure. It is a
  derivative of the staged zip, carries no independent provenance, and can be deleted and
  re-extracted at will. The zip is the artifact of record.
- Both generations are staged **twice-over in effect**: the 2015 set as both the
  agency-native shapefile (which carries the `.prj`) and as WFS GeoJSON. This is
  deliberate — the shapefile `.dbf` **truncates field names** (`ED_ABBREV`, `GAZETTE_DT`,
  `FEAT_AREA`) while WFS emits them in full (`ED_ABBREVIATION`, `GAZETTE_DATE`,
  `FEATURE_AREA_SQM`). Staging the 2015 set as GeoJSON too makes the build symmetric with
  2023 and avoids needing a `.shp` reader at all.
- The 2023 generation has **no shapefile or GeoJSON resource in the catalogue record** —
  only WMS, a KML *ground overlay* (raster, useless for PIP), and an Oracle SDE pointer.
  The WFS endpoint above is the vector escape hatch and is not advertised in the catalogue.
  See the dossier's `## Current boundaries` for the full probe trail.
- No licence was accepted, no account registered, no form submitted. The Elections BC Open
  Data Licence is a plain PDF at a stable URL with no click-through gate.
