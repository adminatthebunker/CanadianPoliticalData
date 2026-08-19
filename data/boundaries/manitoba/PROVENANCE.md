# Manitoba electoral boundaries — staged file provenance

Audit trail for `data/boundaries/manitoba/`. Data files are gitignored; this record is committed.
Research dossier: [`../../../docs/research/boundaries/manitoba.md`](../../../docs/research/boundaries/manitoba.md).

⛔ **Licence is NOT cleared.** Elections Manitoba publishes no open licence. The site footer reads
`© 2026. All rights reserved.` and the maps page carries a disclaimer, quoted verbatim in the dossier,
that the maps *"are provided for informational purposes only"* and are *"not guaranteed to be without
error."* No click-through agreement and no registration wall were encountered (nothing was accepted or
submitted), but there is no affirmative grant to reuse or redistribute. This corroborates X2's upstream
audit finding that Manitoba has **no inheritable licence** in `represent-canada-data`. Treat these files
as **staged pending operator licence clearance**.

| File | Source URL | Retrieved (UTC) | Bytes | sha256 | Licence |
|---|---|---|---|---|---|
| `current/2018_Final_ED_Manitoba_Public_Urban.zip` | https://www.electionsmanitoba.ca/downloads/2018_Final_ED_Manitoba_Public_Urban.zip | 2026-08-18T01:10:09Z | 1,736,709 | `8fa6886b93004946e27cd36e224b6572697592b1f13cff715170c07c1061e6d7` | ⛔ Crown copyright, no open licence |
| `current/2018_Final_ED_Winnipeg_Public_Urban.zip` | https://www.electionsmanitoba.ca/downloads/2018_Final_ED_Winnipeg_Public_Urban.zip | 2026-08-18T01:10:09Z | 76,016 | `ebff2bd20dd2ef13c27281be90d6995db8c354387120b6ff0bd7bf5b00db8fae` | ⛔ Crown copyright, no open licence |
| `prior/2008_Final_ED_Manitoba_Dec_10_2008_Public_Rural.zip` | https://www.electionsmanitoba.ca/downloads/2008_Final_ED_Manitoba_Dec_10_2008_Public_Rural.zip | 2026-08-18T01:30:25Z | 280,469 | `592523df08e91999f07b4f0b073f71b2d18c34ea35f2fedf3d1fdb3db0f3fe92` | ⛔ Crown copyright, no open licence |
| `prior/2008_Final_ED_Manitoba_Dec_10_2008_Public_Urban.zip` | https://www.electionsmanitoba.ca/downloads/2008_Final_ED_Manitoba_Dec_10_2008_Public_Urban.zip | 2026-08-18T01:30:25Z | 64,370 | `54b4e0d3c3aace3d80d5336eaddfe8ea1e78a5d12f6d74f50835900d9463070f` | ⛔ Crown copyright, no open licence |

Total staged: 2,157,564 bytes (2.1 MiB) against a 500 MB agent budget.
Upstream `Last-Modified` on both: `Thu, 25 Mar 2021 04:16:58 GMT`.

## ★ The province is split across TWO shapefiles — both are required

Neither file is a complete province. They partition the 57 electoral divisions with no overlap:

| Archive | Inner shapefile | Records | `Type` |
|---|---|---:|---|
| `2018_Final_ED_Manitoba_Public_Urban.zip` | `EDBC2018_FinalBoundaries_Rural` | 25 | `Rural` |
| `2018_Final_ED_Winnipeg_Public_Urban.zip` | `EDBC2018_FinalBoundaries_Winnipeg` | 32 | `Urban` |
| | **union** | **57** | — |

⚠ **The outer zip names are misleading**: both end `_Public_Urban`, but the first contains the *Rural*
feature class. Go by the inner filename and the `Type` attribute, never the archive name.

Verified on the union: 57 records, 57 distinct `ED` values, no multipart split, and both `OBJECTID` and
`Area` are unique across the union (57 distinct each). Both files are NAD83 / UTM zone 14N =
**EPSG:26914** with no `AUTHORITY` clause, and both declare UTF-8 in a **`.CPG` with an uppercase
extension**.

## ★ Prior generation — staged, recovered via Wayback CDX

The **2008 Electoral Divisions Boundaries Commission** generation, also split Rural/Urban:

| Archive | Inner feature class | Records | `Type` |
|---|---|---:|---|
| `2008_Final_ED_Manitoba_Dec_10_2008_Public_Rural.zip` | same basename | 26 | `Rural` |
| `2008_Final_ED_Manitoba_Dec_10_2008_Public_Urban.zip` | same basename | 31 | `Urban` |
| | **union** | **57** | — |

⚠ **The Rural/Urban split is 26/31 here, against 25/32 in the 2018 generation** — one division moved
between the files. Do not hardcode per-file counts.

EPSG:26914, `PROJCS` byte-identical to the current generation. ⚠ **No `.cpg` in either archive**
(the 2018 files have an uppercase `.CPG`), so encoding is undeclared. ⚠ **No French names** —
`ED_French` is a 2018 addition. ⚠ **`Area` is an area measurement in km² here** (alongside
`Area_no_Wa`), *not* the 1–57 division number it holds in the 2018 files — the same field name carries
opposite meanings across generations.

**How it was found.** Direct probing failed: six guessed 2008/1998-era filenames all 404'd, and the
commission's own site (`boundariescommission.mb.ca`) returns HTTP 500 to this day. The Wayback CDX index
over `electionsmanitoba.ca/*` listed 21 archived archives including both halves, and both proved **still
live at the origin** — unlinked, not deleted. The real filenames embed the commission's report date
(`Dec_10_2008`), which no filename guess would have produced.

## Not staged (deliberate)

| File | Bytes | Why not |
|---|---:|---|
| https://www.electionsmanitoba.ca/downloads/VA_MB2023_public.zip | 4,092,141 | 2023 general-election *voting areas* — sub-division geography, out of scope |
| https://www.electionsmanitoba.ca/downloads/VA_MB2019_public.zip | — | 2019 voting areas, same reason |
| Per-byelection `VA_*_public.zip` files | — | Single-division voting areas for 2022–2026 byelections |
