# Ontario — boundary staging provenance

Audit trail for files staged under `data/boundaries/ontario/`. File contents are
gitignored (`.gitignore:101`); this record is committed. Dossier:
[`../../../docs/research/boundaries/ontario.md`](../../../docs/research/boundaries/ontario.md).

## current/

| File | Source URL | Retrieved (UTC) | Bytes | sha256 | Licence |
|---|---|---:|---:|---|---|
| `mto-authoritative-electoral-districts-2018-nad83.geojson` | https://services.arcgis.com/6iGx1Dq91oKtcE7x/arcgis/rest/services/Electoral_Districts_Public_View/FeatureServer/0/query?where=1%3D1&outFields=*&returnGeometry=true&f=geojson | 2026-08-18T01:06:48Z | 7,292,979 | `769d07203c1bf24f9e95897d07462c5233ecb06139cafacaf5eba4b6086fa1c1` | © Queen's Printer for Ontario, 2020 — bare Crown copyright + "illustration purposes only" disclaimer. **Not** OGL-Ontario. See dossier § Terms / Licensing. |
| `mgcs-onterm-current-and-former-electoral-districts-en-2022-02-09.csv` | https://data.ontario.ca/dataset/bcfd82bc-bbe0-4029-a09a-0c1312fb66f3/resource/874d1833-2b8d-4c46-b97f-06c7bf6fe01a/download/mgcs-onterm-reference-lists-current-and-former-electoral-districts-en-utf8-2022-02-09.csv | 2026-08-18T01:02:00Z | 17,931 | `56794b61da9ffba7859b5ec419cfdb09d2ed578f5fe6978017a142f07ab8d737` | Open Government Licence – Ontario 1.0 (`OGL-ON-1.0`), https://www.ontario.ca/page/open-government-licence-ontario |

**Notes**

- The GeoJSON is the **MTO Authoritative** AGOL feature service (`Electoral_Districts_v3`), 124 features,
  `ED_ID` 1–124 contiguous. Retrieved in the service's **native SR, EPSG:4269 (NAD83 geographic)** —
  no `outSR` was passed. ⚠ The response carries **no GeoJSON `crs` member**, so a consumer following
  RFC 7946 will assume WGS84. Coordinates are NAD83 values. Requesting `outSR=4326` returns
  byte-identical coordinates (ArcGIS applies no datum transformation by default), so the ~1–2 m
  NAD83↔WGS84 difference in Ontario is present either way and is immaterial for riding assignment —
  but the build must `ST_Transform(…, 4269, 4326)` explicitly rather than `ST_SetSRID(…, 4326)`.
- No transformation, reprojection, or unzipping was performed. GeoJSON was requested from the
  service in that format; that is format negotiation by the API, not a local conversion.
- The CSV is a bilingual **names** reference (124 current + 154 former districts). No geometry, no IDs.
  Its 124 current names match the MTO service's 124 exactly (symmetric difference empty) — an
  independent OGL-licensed cross-check on the name authority.

## Not staged — deliberately

- **Elections Ontario electoral district shapefiles.** The preferred licence route
  (*Open Use Data Product Licence Agreement* — permits commercial use and redistribution,
  no attribution clause), but the download sits behind an "I Agree" button at
  https://www.elections.on.ca/en/voting-in-ontario/electoral-district-shapefiles/open-use-data-product-licence-agreement.html
  with the file behind
  `.../open-use-data-product-licence-agreement/download-shapefiles.html`.
  **Not clicked** per the standing no-click-through rule. Raised as a research-handoff item.
- **Elections Ontario polling division shapefiles** — behind the separate and more restrictive
  *Limited Use Data Product Licence Agreement*. Out of scope for electoral districts; not clicked.
- **Prior generation (107 districts, Representation Act, 2005).** Not located on any open,
  gate-free surface. See dossier § Prior boundaries.

## Operator-downloaded (2026-08-18) — Route A, licensed

The research pass deliberately did not fetch these. The download sits behind an
"I Agree" click-through and no agent may accept a licence on the operator's
behalf. **The operator accepted the *Open Use Data Product Licence Agreement*
and downloaded them by hand.**

| File | Bytes | sha256 | Licence | Used |
|---|---:|---|---|---|
| `Electoral District Shapefile - 2022 General Election.zip` | 1,847,182 | `70fd809a4998147b228fd9275e34e569…` | Elections Ontario **Open Use** — commercial use + redistribution explicit, no attribution clause | ✅ **loaded** via `load-boundaries --jurisdiction ontario` |
| `Polling Division Shapefile - 2025 General Election.zip` | 9,100,400 | `5a9be7c8d1722466d3e5d14d3667e428…` | Elections Ontario **Limited Use** — separate, more restrictive agreement | ⛔ **not used** — polling divisions, not electoral districts, and a different licence. Staged only. |

**Source CRS.** ⚠ The `.prj` declares a custom `EO_Lambert_Conformal_Conic` with
**no `AUTHORITY` clause and no EPSG code at all** — Lambert Conformal Conic,
central meridian −84, standard parallels 44.5/54.5, false easting 1,000,000,
NAD83, metres. It is specifically **not** EPSG:3161 (Ontario MNR Lambert, which
uses CM −85, SP 44.5/53.5, FE 930,000). The loader therefore carries the proj4
string transcribed by hand from the `.prj`, and PostGIS transforms from that
string directly rather than via an SRID.

That transcription is verified by measurement, not assumed: the resulting
geometry matches our previously-held Ontario rows at **99.8902% mean overlap,
99.3706% minimum, zero districts below 95%** — and independently agrees with the
MTO GeoJSON comparison (99.8877%), which is a different publisher in a different
projection. Any wrong parameter would have produced garbage rather than
four-decimal agreement.

**Encoding** is UTF-8, declared in the `.cpg` sidecar. **Attribute names are
DBF-truncated to 10 characters** — `ENGLISH_NA` / `FRENCH_NAM`, not the full
names the ArcGIS REST surface exposes. A loader written against the REST schema
would raise a KeyError here.
