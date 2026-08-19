# Municipal Atlantic — boundary file provenance

Staged by the boundary-research pass on 2026-08-18. Files themselves are gitignored;
this table is the committed audit trail. See
[`../../../docs/research/boundaries/municipal-atlantic.md`](../../../docs/research/boundaries/municipal-atlantic.md).

⚠ **`prior/` is empty.** No Atlantic publisher was found offering a superseded generation —
unlike Toronto (3 ward models) or Montréal (5). Both province-wide files are current-only.

⛔ **PE is not staged because no machine-readable source exists** — Charlottetown, Summerside
and Stratford are PDF/paper only. See the dossier's Research-handoff items.
✅ **NL was solved on a follow-up probe (2026-08-18)** and is staged below.

| File | Source URL | Retrieved (UTC) | Bytes | sha256 | Licence |
|---|---|---|---|---|---|
| `current/ns-municipal-polling-districts.geojson` | https://data.novascotia.ca/api/geospatial/gcep-xeci?method=export&format=GeoJSON | 2026-08-18T05:29Z | 21389104 | `55bfd6e03a01c3167da9e8232974908f952b4762471c9372795e9ad5f896fd96` | Nova Scotia Open Government Licence |
| `current/nb-lg-wards-quartiers.geojson` | https://gnb.socrata.com/api/geospatial/7zs3-pcvk?method=export&format=GeoJSON | 2026-08-18T05:26Z | 21756026 | `f80be3ab551db10a1f457c5846162b01c33d704c7d88429889a69c3e32def42a` | Open Government Licence – New Brunswick |
| `current/st-johns-wards-wcouncillor.geojson` | https://map.stjohns.ca/mapsrv/rest/services/WardMap/MapServer/0/query?where=1%3D1&outFields=*&outSR=4326&f=geojson | 2026-08-18T06:05Z | 4698474 | `aa0c94ed6deec2efb90d5fa81c77a29102bd96f5e9b40438e0fa9dd95928a17f` | ⛔ **none stated** |
| `current/halifax-polling-districts-2024.geojson` | https://services2.arcgis.com/11XBiaBYA9Ep0yNJ/arcgis/rest/services/ADM_Polling_District2024/FeatureServer/0/query?where=1%3D1&outFields=*&outSR=4326&f=geojson | 2026-08-18T05:26Z | 1002744 | `3c7933bf3a07a237c26b5df1b22e60cad7e59500d18fccd8547aab2e5b65f9ee` | ⚠ unstated on the layer; HRM open-data terms |

## Notes

- ★ **Two province-wide files cover 5 of our 9 Atlantic sets.** No per-municipality discovery
  needed for NS or NB — the opposite of Ontario.
  - NS `gcep-xeci` *Municipal Polling Districts*: **238 districts / 49 municipalities**, includes
    **Halifax Regional Municipality (16)** and **Cape Breton Regional Municipality (12)**.
    Licence named and linked in the metadata (`http://novascotia.ca/opendata/licence.asp`).
    Rows last updated **2025-11-19**. Fields: `mun`, `poll_dist`, `co_code`, `mu_code`,
    `reg_num`, `shape_leng`, `shape_area`. Filter on `mun`.
  - NB `7zs3-pcvk` *Ward boundaries for Local Governments and Rural Districts*: **330 wards /
    90 local governments**, includes **The City of Fredericton (13)**, **Moncton (4)** and
    **The City of Saint John (4)**. Fields: `elect_comm` (local government name — filter on
    this, **not** `name_e`, which is the literal string "Ward"), `ward`, `eng_label`,
    `frn_label`, `name_e`, `name_f`, `type`.
- ✅ **GeoNB is alive; an earlier note here claiming otherwise was wrong and is retracted.**
  `https://geonb.snb.ca/downloads/mun_electoral_districts/geonb_mred-cerm_shp.zip` (956,278 B)
  and `https://geonb.snb.ca/downloads/lg/geonb_lg_gl_wards_quartiers_shp.zip` (4,266,202 B) both
  return HTTP 200. The 404s originally reported came from **reconstructing** directory paths out
  of bare filenames (`/downloads2/mred/`, `/downloads2/lg_gl/`) rather than using the published
  URLs. ⚠ A 404 on a reconstructed path says nothing about the resource — only about the guess.
- ⓘ **Socrata vs GeoNB is a format choice, not an availability one.** GeoNB serves zipped
  shapefiles; Socrata serves GeoJSON directly, plus CSV/FGDB, and supports server-side SoQL
  filtering — which matters because the NB file is 330 wards fetched for 3 cities. Socrata was
  staged for that reason; GeoNB remains the publisher of record.
- ★ The Halifax layer carries a **`COUNCILLOR`** field alongside `DIST_ID` / `DISTNAME` —
  boundary and roster in one, the same shape as Toronto's `wards-and-elected-councillors`.
  Useful for reconciling `politicians` directly. Its `licenseInfo` and `copyrightText` are both
  empty, so the licence is unstated on the layer itself; the NS Socrata file is the
  licence-clean route for the same 16 districts.
- ⚠ **Both Socrata GeoJSON exports are large and unsimplified** — ~21 MB each for a few hundred
  features — and each is being fetched for only 2–3 municipalities. Filter server-side with
  Socrata SoQL, or accept the file once and slice locally.
- ⛔ **What we hold in the database differs in one specific place:** `fredericton-wards` holds
  `ward-1` … `ward-12` but the authoritative NB file has **thirteen** entries, the extra being
  **`4-Lincoln`** — a sub-ward created by New Brunswick's 2023 local governance reform. Evidence
  our NB sets are pre-reform. Halifax by contrast reconciles **16/16**.
- ★ **St. John's (`WardMap/MapServer/0`, `WARDS_wCouncillorInfo`)** was found by grepping the
  MapCentre viewer's `js/layers.js` for `rest/services` — the city runs its **own ArcGIS Server**
  on a custom `mapsrv` mount, so `/arcgis/rest/services` and `/server/rest/services` both 404 and
  no portal-level search finds it. Native CRS is **EPSG:32181 (NAD83 / MTM zone 1)**; the staged
  copy is `outSR=4326`.
- ★ **11 features: 5 ward polygons + 6 rows at `WARD = 0`** (Mayor, Deputy Mayor, 4
  Councillors-at-Large, each with city-wide geometry). Independent publisher-side confirmation of
  ruling A12 — the city models hybrid representation the same way our schema does.
- ⚠ **Take the geometry, discard the `COUNCILLOR` field.** Checked against the 2025-10-02 official
  results, the layer's roster is ~4 years stale (Ward 2, Ward 5, Deputy Mayor and 3 of 4 at-large
  seats are all wrong). **Our `politicians` rows are the correct 2025 council.** Contrast Halifax,
  whose `COUNCILLOR` field *is* current — currency has to be checked per source.
- ⛔ **No licence is stated anywhere on the St. John's service** — empty `copyrightText` and
  `licenseInfo`, no portal terms. The only Atlantic source with no licence at all.
