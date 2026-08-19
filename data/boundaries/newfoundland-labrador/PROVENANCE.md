# Newfoundland and Labrador — boundary staging provenance

Audit trail for files staged under `data/boundaries/newfoundland-labrador/`. The files
themselves are gitignored; this record is committed. Research dossier:
[`../../../docs/research/boundaries/newfoundland-labrador.md`](../../../docs/research/boundaries/newfoundland-labrador.md).

Nothing was converted, reprojected, or loaded. Both archives were unzipped **only** to read
the `.prj` and parse the `.dbf` header per the no-GDAL procedure.

| File | Source URL | Retrieved (UTC) | Bytes | sha256 | Licence |
|---|---|---|---|---|---|
| `current/NL_EB_Poly_50k.zip` | https://opendata.gov.nl.ca/public/opendata/filedownload/?file-id=3323 | 2026-08-18 01:30 | 16,254,401 | `e36db6bdf01b6cd44fdb036099280b52af82090206f8249a8d56509d9ac51012` | Open Government Licence – Newfoundland and Labrador v1.0 |
| `prior/Distribution_2011.zip` | ⚠ **Wayback only** — https://web.archive.org/web/20250802080819id_/https://www.elections.gov.nl.ca/elections/resources/shapedata/Distribution_2011.zip (origin 404s) | 2026-08-18 01:38 | 11,497,732 | `24213e0e63eaa05e60270e2268a5ace3ce7d82771e7d272df7bafd24653c935e` | ⚠ unestablished — see dossier |

**Total staged: 27.8 MB** of the 500 MB agent budget (67 MB on disk including unzipped
working copies).

## Notes

- ⚠ **The prior generation came from the Internet Archive, not the live origin.** Found with
  the A5 CDX technique. **All three candidate origin URLs return HTTP 404** as of
  2026-08-18 — `/elections/resources/shapedata/Distribution_2011.zip`,
  `/elections/ElectoralBoundaries/Distibution_2011.zip` (note the upstream typo in that
  older path), and `/elections/ElectoralBoundaries/Shapefile.zip`. Wayback holds genuine
  `200` captures at 11,375,704–11,375,707 bytes across 2017→2025-08-02; the byte-size
  difference against the staged file is Wayback header framing on the `id_` raw endpoint.
  The file is Elections NL's own artifact, but it is **archive-retrieved, not
  agency-served** — flagged as a research-handoff item because it affects both licence
  provenance and whether we can re-fetch it.
- `current/NL_EB_Poly_50k/` and `prior/Distribution_2011/` are unzipped working copies,
  derivatives of the staged zips, freely deletable and re-extractable. The zips are the
  artifacts of record.
- ⚠ **The current file is the commission's "proposed" boundaries.** The portal describes
  dataset 361 as "Polygons and line shapefiles for the final version of the **proposed**
  electoral boundaries." It contains all 40 districts and matches the enacted count, but
  the agency has published no separate post-enactment file — see the dossier's
  `## Current boundaries` and `## Research-handoff items`.
- Only the **polygon** file is staged. Dataset 361 also offers a *lines* shapefile
  (`file-id=2243`), which is the same boundaries as unclosed linework and is not useful
  for point-in-polygon.
- No licence was accepted, no account registered, no form submitted.
