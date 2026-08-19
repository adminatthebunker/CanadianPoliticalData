# Staged files — postal-code geocoding research (agent X1)

Reference artefacts for [`docs/research/boundaries/geocoding.md`](../../../docs/research/boundaries/geocoding.md).
Nothing here is a boundary file for a jurisdiction — this directory supports the
postal-code → lat/lng question only. Retrieved 2026-08-18 UTC.

**Nothing in this directory was converted, reprojected, or loaded into the database.**
The two NAR CSV samples were decompressed from the source zip (deflate) as the only
way to read them; contents are otherwise byte-identical to upstream.

| File | Source URL | Retrieved (UTC) | Bytes | sha256 | Licence |
|---|---|---|---:|---|---|
| `nar/202606.zip` | https://www150.statcan.gc.ca/n1/pub/46-26-0002/2022001/202606.zip | 2026-08-18 | 1,665,944,959 | `c87df8d39537b75146ab4b38b9b1ca1f820d72e0f74ee2b3722059851a564364` | Statistics Canada Open Licence |
| `nar_202606_manifest.csv` | https://www150.statcan.gc.ca/n1/pub/46-26-0002/2022001/202606.zip | 2026-08-18 | 3,350 | `e5d7b10441d17c5e541b16e2fe9f87cfb5de6b46acdda10d49220f88e570fdd6` | Statistics Canada Open Licence |
| `nar_202606_README.txt` | https://www150.statcan.gc.ca/n1/pub/46-26-0002/2022001/202606.zip | 2026-08-18 | 86 | `f4fa0a9aea6eeae3bca1fe83b661691dcaa269cf0048bedac7304b4845016324` | Statistics Canada Open Licence |
| `nar_address_header.csv` | ditto, `Addresses/Address_62.csv` header row | 2026-08-18 | 420 | `8666a97a6c18997382be731142a83e42c7b1a64d8cc2a3c0db10a5ba52504a29` | Statistics Canada Open Licence |
| `nar_location_header.csv` | ditto, `Locations/Location_62.csv` header row | 2026-08-18 | 156 | `9d3674bc68e814cae3e6a332f7cb05f33c2ec8a3b721ce80faba15a4c7f1a6a8` | Statistics Canada Open Licence |
| `nar_202606_Address_62_NU_sample.csv` | ditto, `Addresses/Address_62.csv` (Nunavut, whole member) | 2026-08-18 | 924,789 | `2022f6517cf1fa0518f251105ca35630d4719cd4746016faf9b9907a7aefe69f` | Statistics Canada Open Licence |
| `nar_202606_Location_62_NU_sample.csv` | ditto, `Locations/Location_62.csv` (Nunavut, whole member) | 2026-08-18 | 285,080 | `ffd58da60a7c5cd2ddb1255bf2bd754a1cf1a9151a7bb2965b55d44c6c649e74` | Statistics Canada Open Licence |
| `statcan_fsa_2021_attributes.json` | https://geo.statcan.gc.ca/geo_wa/rest/services/2021/Cartographic_boundary_files/MapServer/14/query (attributes only, `returnGeometry=false`) | 2026-08-18 | 172,258 | `b954e3c109297dcad2550aa920ea7d31996befa7e16d1615768f1c049003d116` | Statistics Canada Open Licence |
| `statcan_fsa_2021_by_province.json` | derived from the row above (grouping only, no geometry) | 2026-08-18 | 11,605 | `b093fc25dc65515eac7d24e54125c0a615763347750087b0f599c287afed0d4e` | Statistics Canada Open Licence |
| `zip_range_extract.py` | written by agent X1 — not upstream content | 2026-08-18 | 1,241 | `09033e7b58970795ebd43229ad1674de36ea1fa7247f685ff0dba9de8ccaa40b` | n/a (our code) |

## Attribution required on any published derivative

Statistics Canada Open Licence, adaptation form:

> Adapted from Statistics Canada, National Address Register, June 2026. This does not
> constitute an endorsement by Statistics Canada of this product.

## Why the samples are Nunavut

`Address_62` / `Location_62` are the smallest complete province/territory members in the
archive (925 KB / 285 KB uncompressed). They carry the full column set, so they document
the schema without staging a large file. Nunavut is *not* representative for coverage —
it is the weakest jurisdiction in the register (11 distinct postal codes). Coverage
figures in the dossier come from the nine-jurisdiction sample described there.

## `zip_range_extract.py`

The June 2026 NAR archive is 1.67 GB, over the 500 MB per-agent download budget.
`www150.statcan.gc.ca` honours HTTP `Range` (verified: `206 Partial Content`), and the zip
is a plain non-ZIP64 archive whose members are independently deflate-compressed. The
script reads the central directory out of the last 200 KB, then fetches and inflates
individual members by byte offset. This is how every measurement in the dossier was taken
without downloading the whole archive; it is also the recommended ingest path for the
build phase, which only needs `MAIL_POSTAL_CODE` + `LOC_GUID` + coordinates.

Offsets in `nar_202606_manifest.csv` are valid for the `202606.zip` build only. Re-read the
central directory after any new NAR release.

## The staged archive

`nar/202606.zip` is the full national National Address Register, staged 2026-08-18 after the
coordinator raised the download budget. Byte count matches upstream `Content-Length` exactly.
It is **staged, not processed** — nothing was unzipped to disk. All measurements in the dossier
were taken by streaming members out of the archive in-memory (`zipfile` + `csv`), because the
host was thermally saturated at the time; the build phase does the extraction.

Verify before use:

```
sha256sum data/boundaries/_geocoding/nar/202606.zip
# c87df8d39537b75146ab4b38b9b1ca1f820d72e0f74ee2b3722059851a564364
```

## Not staged (deliberate)

- **StatCan 2021 FSA digital boundary file** `lfsa000b21a_e.zip` — 162,038,215 bytes.
  Fetch confirmed working (needs a cookie jar; see the dossier's `⚠ trap` note) but
  discarded rather than staged, because the recommendation does not depend on it.
- **Open Database of Addresses** provincial zips — eight downloaded to scratch for the
  postal-code fill-rate measurement, none staged. ODA is not recommended; see the dossier.

## Relocated by coordinator 2026-08-18

- `fsa_lfsa000b21s_e_layer_metadata.json` — StatCan 2021 Census FSA Boundary File layer metadata (`geo.statcan.gc.ca` MapServer layer 14, 1,643 CFSAs). Was written to the **repo root** as `fsa_meta.json` by the relative-path bug in ruling A9; moved here, contents unchanged.
