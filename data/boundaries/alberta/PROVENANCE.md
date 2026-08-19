# Alberta — boundary staging provenance

Audit trail for files staged under `data/boundaries/alberta/`. File contents are gitignored
(`.gitignore:101`); this record is committed. Dossier:
[`../../../docs/research/boundaries/alberta.md`](../../../docs/research/boundaries/alberta.md).

Both files come from the same Government of Alberta ArcGIS MapServer:
`https://geospatial.alberta.ca/titan/rest/services/boundary/goa_administrative_area_10tm_nad83_aep/MapServer`
(layer 3 = current, layer 4 = prior), catalogued on the Alberta Open Government portal as
*Provincial Electoral Division - Current 2019*, dataset `gda-e201c640-1f76-429c-8c24-89ff496f956e`.

## current/

| File | Source URL | Retrieved (UTC) | Bytes | sha256 | Licence |
|---|---|---:|---:|---|---|
| `goa-provincial-electoral-division-current-2019.geojson` | `…/MapServer/3/query?where=1%3D1&outFields=EDNUMBER,EDNAME&returnGeometry=true&f=geojson` | 2026-08-18T01:26Z | 10,827,816 | `d2e738fe62cb70b8bf95ebd08fb74e62756667e4166cc8d92aa18799136ab361` | **Open Government Licence – Alberta**, https://open.alberta.ca/licence — commercial use and redistribution permitted; **attribution mandatory**. |

## prior/

| File | Source URL | Retrieved (UTC) | Bytes | sha256 | Licence |
|---|---|---:|---:|---|---|
| `goa-provincial-electoral-division-historical-2010.geojson` | `…/MapServer/4/query?where=1%3D1&outFields=EDNUMBER,EDNAME&returnGeometry=true&f=geojson` | 2026-08-18T01:29Z | 11,052,841 | `93bf9ce64378cc2b90ba889d4b79021583a0d14ff73409eb17521d7ed32e8867` | Same — OGL-Alberta. |

**Required attribution string** (licence terminates automatically on non-compliance):

> Contains information licensed under the Open Government Licence – Alberta.

**Notes**

- **87 features each**, `EDNUMBER` distinct 87 in both — one row per division, no island splitting.
  Verified by `returnCountOnly` and by distinct-value count, per the one-row-per-district rule.
- ⚠ **CRS: the service's native SR is EPSG:3400** (`wkid 102184 / latestWkid 3400`, NAD83 / Alberta
  10-TM Forest — **projected, metres**). But `f=geojson` output came back in **decimal degrees**
  (first coordinate `[-112.883445, 49.628507]`), i.e. **ArcGIS reprojected on the way out**. The
  response carries **no GeoJSON `crs` member**. So these staged files are *already* geographic, not
  10TM — the opposite of what the service path (`_10tm_nad83_`) implies. Whether the output datum is
  strictly WGS84 or NAD83-values-labelled-WGS84 is unresolved (~1–2 m in Alberta either way);
  `needs confirmation` if sub-metre accuracy ever matters. **Do not** apply a 3400→4326
  `ST_Transform` to these files — they are already transformed. If the build re-fetches from the
  service without `f=geojson` (e.g. `f=json`), it *will* get 10TM metres and must transform.
- No transformation, reprojection, or unzipping was performed locally. GeoJSON was requested from
  the service in that format.
- Layer 5 (*Provincial Electoral Division - Historical 2003*) also exists and was **not** staged —
  two generations back, out of scope.

## Not staged — deliberately

- **2025-26 Electoral Boundaries Commission final report** (dated 2026-03-23), proposing **89**
  divisions: https://www.elections.ab.ca/uploads/abebc_2026_rpt_final.pdf — a PDF report, not
  geospatial data. **No 89-division geospatial layer exists yet** on the GoA service, consistent
  with the new map not being in force. See dossier § Research-handoff items.
