# New Brunswick — boundary staging provenance

Staged by the New Brunswick boundary-research agent, 2026-08-18. Research dossier:
[`../../../docs/research/boundaries/new-brunswick.md`](../../../docs/research/boundaries/new-brunswick.md).

All files retrieved by direct unauthenticated HTTPS `GET` from `geonb.snb.ca`. **No licence was
accepted, no account registered, no form submitted, no checkbox ticked.** Nothing has been
converted, reprojected, or loaded. `.zip` archives are staged byte-for-byte as served; the
extraction used for schema inspection happened in a scratch directory, not here.

Total staged: 45,762,263 bytes (45.7 MB) against a 500 MB budget.

| File | Source URL | Retrieved (UTC) | Bytes | sha256 | Licence |
|---|---|---|---:|---|---|
| `current/geonb_2024_ped-cep_shp.zip` | https://geonb.snb.ca/downloads/provincial_elections/geonb_2024_ped-cep_shp.zip | 2026-08-18T01:05:36Z | 1252663 | `864207e81151dc9e354bcf0e6994cd56dc494dcfbdc19b4e3074ba3f6805cc97` | GeoNB Open Data Licence v1.0 |
| `current/geonb_2024_ped-cep_kmz.zip` | https://geonb.snb.ca/downloads/provincial_elections/geonb_2024_ped-cep_kmz.zip | 2026-08-18T01:24:51Z | 2436011 | `01db9feba158c3de492c73d27ccd74b1c1e330abac66fc1b60eb1621a1305592` | GeoNB Open Data Licence v1.0 |
| `current/geonb_2025_ppd_svp_shp.zip` | https://geonb.snb.ca/downloads/provincial_elections/geonb_2025_ppd_svp_shp.zip | 2026-08-18T01:04:05Z | 5818872 | `d7ec87e4403d7d3c430d9702af7b585f6bbedc46f8fc7fa5d436e06bd3180998` | GeoNB Open Data Licence v1.0 |
| `prior/geonb_historic-historique_ped-cep_shp.zip` | https://geonb.snb.ca/downloads/provincial_elections/geonb_historic-historique_ped-cep_shp.zip | 2026-08-18T01:05:36Z | 6206225 | `589ae6e3acfa3cd4ad2b88c8edaafea0287f7c5a7b2045e85d1bc88288e1aa97` | GeoNB Open Data Licence v1.0 |
| `prior/geonb_historic-historique_ppd_svp_shp.zip` | https://geonb.snb.ca/downloads/provincial_elections/geonb_historic-historique_ppd_svp_shp.zip | 2026-08-18T01:04:05Z | 29641702 | `66fc5c553108e32cd34b114b36a12b2ed40f16bac4d2fc967d1bfba5e9f4e2a8` | GeoNB Open Data Licence v1.0 |
| `geonb-odl_en.pdf` | https://geonb.snb.ca/documents/license/geonb-odl_en.pdf | 2026-08-18T01:05:36Z | 406790 | `538a140bbc9196b4dc09eca4ce922cee5dc7717bf5699944958524ec79075e6c` | n/a — this *is* the licence |

## What is inside each archive

`geonb_2024_ped-cep_shp.zip` — the **49 in-force provincial electoral districts** (NB Reg 2023-42).
One shapefile set `geonb_2024_ped_cep.{shp,shx,dbf,prj,cpg,sbn,sbx,shp.xml}` plus
`license_licence.txt`, `read_me.txt`, `lisez_moi.txt`. This is the primary target file.

`geonb_historic-historique_ped-cep_shp.zip` — four generations of electoral districts, one
directory each: `2010/` (55 districts, `geonb_2010_ped-cep`), `2014/`, `2018/`, `2020/`
(49 districts each, `geonb_<year>_ped_cep`). The `2018/` set is the exact vintage currently
in `constituency_boundaries`; the `2020/` set is the last state of the superseded generation.

`geonb_2025_ppd_svp_shp.zip` / `geonb_historic-historique_ppd_svp_shp.zip` — **polling
divisions**, not districts (1,753 polygons for 2025). Staged because they carry the
`PED` / `PED_Names_` district attributes and are the only files the GeoNB catalogue's
"Electoral districts — Provincial" rows actually link to. The historic polling archive
contains `2010/ 2014/ 2018/ 2020/ 2024/`. Not needed for the district load; keep for
poll-level work and as the catalogue's own idea of what "electoral districts" means.

`geonb_2024_ped-cep_kmz.zip` — the same 49 in-force districts as KML, **already in WGS84**
(`-66.61890170282737,48.0249941985088,0`). Staged as an independent check that the build's
`ST_Transform(…, 2953 → 4326)` produced the right answer. ⚠ Not a substitute for the shapefile:
it has no `<ExtendedData>` / `<SchemaData>` / `<SimpleData>` at all — `DIST_ID`, `PED_Names_B`,
`Num_PED` and `Colour` exist only as rows of an HTML table inside a CDATA `<description>`.

## Notable

⚠ **None of the `ped-cep` archives is linked from the GeoNB data catalogue.** The catalogue's
"Electoral districts — Provincial, current (2025)" and "…, historic" rows both point at the
*polling-division* bundles. The `shp` and `fgdb` district URLs were found by probing the
`provincial_elections/` download directory; the **`kmz` variant was found only via the Internet
Archive CDX index** and appears on no page and in no service listing. All are stable, public, and
`Last-Modified: Thu, 22 Aug 2024`, but they are undiscoverable by browsing — record the URLs, do
not expect to re-find them from the catalogue.

⚠ **A superseded download directory is still live at the origin.** `downloads/prov_electoral_districts/`
serves standalone per-snapshot bundles that predate the `provincial_elections/` layout and are
linked from nowhere: `geonb_2020_ped-cep_shp.zip` (813,676 B), `geonb_2018_ped-cep_shp.zip`
(791,306 B), `geonb_2018_ped-cep_kml.zip` (1,389,185 B), `geonb_2014_ped-cep_shp.zip`
(3,166,069 B), `geonb_2010_ped-cep_shp.zip` (1,756,537 B). Not staged — the combined
`historic-historique` archive above already contains the same content — but recorded because
fetching one snapshot beats fetching 6 MB. Two CDX-listed siblings (`geonb_ped-cep_shp.zip`,
`geonb_2020_ped-cep_kml.zip`) are `404` at the origin: **test candidates against the live host,
do not trust the index.**

ⓘ **Payloads were verified, not just status codes.** Every `200` recorded here unzips to the
expected internal structure; every `404` returned an HTML body with no content-length. No
wrong-vintage path served a 200 error page.
