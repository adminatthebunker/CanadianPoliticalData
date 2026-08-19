# Prince Edward Island — boundary staging provenance

Retrieved 2026-08-18. Total staged: 18 MB.

⚠ **Elections PEI is WAF-blocked** (Radware ShieldSquare). Neither file below came from
`electionspei.ca`. Both came from Government of PEI hosts that are reachable — see the note on
the WAF carve-out.

| File | Source URL | Retrieved (UTC) | Bytes | sha256 (first 16) | Licence |
|---|---|---|---:|---|---|
| `current/Provincial_Electoral_Wards_and_Polls_esrijson_native2954.json` | https://gis.princeedwardisland.ca/server/rest/services/Provincial_Electoral_Wards_and_Polls/FeatureServer/0/query?where=1%3D1&outFields=*&returnGeometry=true&f=json&resultRecordCount=2000 | 2026-08-18T01:32Z | 13368875 | `76dd232c3baf4892…` | ⚠ **None stated** — `copyrightText` is empty on both the service and the layer |
| `current/e-02-1-electoral_boundaries_act.pdf` | https://www.princeedwardisland.ca/sites/default/files/legislation/e-02-1-electoral_boundaries_act.pdf | 2026-08-18T01:33Z | 4684724 | `02849e8ce0767f95…` | Crown copyright, Province of PEI; office consolidation, not the official version |

## What the geometry file is, precisely

It is the **raw Esri JSON response** from an ArcGIS Server `query` endpoint, saved verbatim —
not converted, not reprojected, not turned into GeoJSON.

- **270 features**, `esriGeometryPolygon`, 388 rings total. `exceededTransferLimit` is absent, so
  the response is complete in one call (the layer's `maxRecordCount` is 2000).
- **Native CRS preserved: `{"wkid": 2291, "latestWkid": 2954}`** — NAD83(CSRS) / Prince Edward Isl.
  Stereographic, coordinates in metres. `outSR` was deliberately **not** passed, because supplying
  it would have made the server reproject and the staged file would no longer be the source data.
  The service *can* serve 4326 on request if the build prefers.
- ⚠⚠ **These are POLL polygons, not district polygons.** 270 rows cover 27 districts. The build
  **must** dissolve on `DIST_NO`. See the dossier.
- ⚠ **26 of the 270 rows are junk** — `DIST_NO = 0`, blank `DISTRICT`, blank `POLL_NAME`,
  `electorcou = 0`. Filter `WHERE DIST_NO > 0` or they become a phantom 28th district.
- The service advertises `supportedQueryFormats: JSON` only — **`f=geojson` is not available**.

## Licence — nothing is stated, and that is the finding

- The ArcGIS service and layer both return `copyrightText: ""`. No terms, no attribution string,
  no licence reference anywhere in the service metadata.
- `data.princeedwardisland.ca` (the ArcGIS Hub front end for the same server) is reachable, but it
  **does not list this layer at all**, so there is no Hub dataset page carrying terms either.
- Elections PEI, which would be the authoritative place to state terms, is behind the WAF.
- **Conclusion: PEI boundary terms are unresolved and cannot be resolved from a machine-reachable
  source.** This matches X2's finding that PEI is one of the three provinces with no inheritable
  licence. Raised as a handoff item in the dossier.

## Note on the WAF carve-out (how the Act PDF was obtained)

`www.princeedwardisland.ca` serves a Radware challenge for HTML pages — `HTTP 200` with a
"Verifying your browser before proceeding" stub body, which is why a status-code-only check reports
it as open. **Static files under `/sites/default/files/` are NOT challenged** and are served
directly with the correct content type. That is how the consolidated Act was retrieved. The path
must be known in advance; the listing pages that would reveal filenames are still challenged.
