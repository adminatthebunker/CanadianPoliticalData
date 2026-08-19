# Northwest Territories — boundary file provenance

Staged by the boundary-research pass on 2026-08-18. Files themselves are gitignored;
this table is the committed audit trail. See [`../../../docs/research/boundaries/northwest-territories.md`](../../../docs/research/boundaries/northwest-territories.md).

**Generation staged:** `current` only. The `prior` generation (pre-2013 order, with `Tu Nedhe`
and `Weledeh` as separate districts) is **not published** in any machine-readable form we
could find. See the dossier's Research-handoff items.

| File | Source URL | Retrieved (UTC) | Bytes | sha256 | Licence |
|---|---|---|---|---|---|
| `current/NWT_ElectoralDistricts.zip` | https://www.geomatics.gov.nt.ca/en/electoral-district-boundaries | 2026-08-18T00:50:40Z | 1249927 | `08fb0428556f0b88aa960590e846a82639cec1020813274dbbff78c1dffcb77a` | Open Government Licence – Northwest Territories |
| `current/NWT_ElectoralDistricts.geojson` | https://www.sandbox.geomatics.gov.nt.ca/arcgis/rest/services/Pro_GNWT/Boundaries_LCC/MapServer/2/query?where=1%3D1&outFields=*&outSR=4326&f=geojson | 2026-08-18T00:55Z | 4599720 | `e0c7da5eef537f3ac1c8612e1ea50ec0cc5da90bd7632467c19405bec4bc7b75` | Open Government Licence – Northwest Territories |

## Notes

- The `.geojson` is the **recommended build input**: already EPSG:4326, so no reprojection
  step, and it carries one field the shapefile `.dbf` lacks (`EDFrench`, the French district
  names). Verified identical to the shapefile on feature count (19) and district-name set.
- The `.zip` is the **durable archive copy and native-CRS reference**. ⚠ Its source URL looks
  like an HTML page but the server returns the shapefile ZIP directly with `Content-Type`
  unset — `curl -o` works; a naive scraper expecting HTML will parse a ZIP as text. Inner
  members are named `ElectoralDistricts.*` (shp/dbf/prj/shx/sbn/sbx/**CPG** + a 75 KB `.shp.xml`).
- CRS is `Canada_Lambert_Conformal_Conic` = **ESRI:102002**, which has **no EPSG equivalent**.
  SRID 102002 is already present in our `spatial_ref_sys`. ⚠ Do not substitute EPSG:3347 or
  EPSG:3978 — both are NAD83 Lambert but with different parallels and origin.
- ⚠ **The `.CPG` extension is UPPERCASE.** A `*.cpg` glob misses it and the fallback decode
  mojibakes `Tu Nedhé - Wiilideh` into `Tu NedhÃ© - Wiilideh`. Confirmed live during staging.
  It declares `UTF-8`.
- Shapefile structure checks: 19 records → **19 distinct district names**, no duplicate-key
  risk. Four districts are **multi-part within a single record** (`Tu Nedhé - Wiilideh` 20
  parts, `Yellowknife North` 20, `Sahtu` 14, `Dehcho` 2) — load as `MultiPolygon`.
- ⛔ **The held geometry in `constituency_boundaries` disagrees materially with this file for
  5 of 19 districts** (`Great Slave`, `Frame Lake`, `Hay River North`, `Hay River South`,
  `Nunakput`). See the dossier's Reconciliation section — this file is the correct one.
- ⚠ The REST service answers only on the **`www.sandbox.` host**. The production host
  `www.geomatics.gov.nt.ca/arcgis/rest/...` returns 404. Treat the sandbox endpoint as
  convenient but not contractually stable; the `.zip` is the durable path.
