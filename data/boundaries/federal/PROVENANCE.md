# Federal electoral boundaries — staged file provenance

Audit trail for `data/boundaries/federal/`. The data files themselves are gitignored;
this record is committed. Research dossier: [`../../../docs/research/boundaries/federal.md`](../../../docs/research/boundaries/federal.md).

All four files are **Open Government Licence – Canada v2.0** (`ca-ogl-lgo`),
https://open.canada.ca/en/open-government-licence-canada — no click-through, no
registration, no account. Required acknowledgement, verbatim:

> "Contains information licensed under the Open Government Licence – Canada."

| File | Source URL | Retrieved (UTC) | Bytes | sha256 | Licence |
|---|---|---|---|---|---|
| `current/FED_CA_2023_EN-SHP.zip` | https://ftp.maps.canada.ca/pub/elections_elections/Electoral-districts_Circonscription-electorale/federal_electoral_districts_boundaries_2023/FED_CA_2023_EN-SHP.zip | 2026-08-18T00:52:07Z | 9,388,965 | `eab55b952164ba7e8bf569f00c1fe4b6480b532411e1436de427772d9cebae59` | OGL–Canada 2.0 |
| `current/FederalElectoralDistricts_2025_SHP.zip` | https://www.elections.ca/res/cir/mapsCorner/vector/FederalElectoralDistricts_2025_SHP.zip | 2026-08-18T00:47:08Z | 10,301,648 | `4004a6bff0303c46bc5d9318a3c0b4a0322599bc707712a3c41acffafbef0b93` | OGL–Canada 2.0 |
| `prior/FED_CA_2021_EN.zip` | https://ftp.maps.canada.ca/pub/elections_elections/Electoral-districts_Circonscription-electorale/Elections_Canada_2021/FED_CA_2021_EN.zip | 2026-08-18T00:52:07Z | 9,790,556 | `ae6e6bb268ce1964910bbe7869f0f6482ad4de0d94caee043cb1571236dacda0` | OGL–Canada 2.0 |
| `prior/lfed000a16a_e.zip` | https://www12.statcan.gc.ca/census-recensement/2011/geo/bound-limit/files-fichiers/2016/lfed000a16a_e.zip | 2026-08-18T00:49:43Z | 5,845,230 | `60f7b312ce3090fa2abbaec8dfd812ad8e105904ee4646445daddd76cb9064a1` | OGL–Canada 2.0 |

Total staged: 35,326,399 bytes (33.7 MiB) against a 500 MB agent budget.

## Which file the build should use

- **Current generation → `current/FED_CA_2023_EN-SHP.zip`.** 343 records, exactly one
  per district, no multipart split. Publisher: Elections Canada, via the Open Government
  Portal dataset `18bf3ea7-1940-46ec-af52-9ba3f77ed708`.
- **Prior generation → `prior/FED_CA_2021_EN.zip`.** Elections Canada's own 2013-Order
  file (338 districts across 347 records). Dataset `47a0f098-7445-41bb-a147-41686b692887`.

The other two are cross-checks, deliberately retained:

- `FederalElectoralDistricts_2025_SHP.zip` is the 45th-General-Election snapshot
  (dataset `97a2a33c-54cc-4f2e-82c1-047ad8212f05`). Same 343 FED codes and same 343 names
  as `FED_CA_2023_EN-SHP.zip` — **verified byte-for-byte equal on every key and name** —
  but split into 352 records because six districts are stored as separate island rows.
  Kept as the independent confirmation that the recommended file is complete.
- `lfed000a16a_e.zip` is Statistics Canada's 2013-Order digital boundary file. Kept
  because it is 1:1 (338 records) and, unlike every Elections Canada file, carries
  `PRUID` / `PRNAME` province attributes.

## Not staged (deliberate)

| File | Size | Why not |
|---|---:|---|
| `PollingDivisionBoundaries_2025_SHP.zip` | 95,154,203 | Polling divisions — a future layer, out of scope for `constituency_boundaries` |
| `AdvancePollingDistrictBoundaries_2025_SHP.zip` | 42,382,982 | Same |
| `lfed000b21a_e.zip` (StatCan 2021 cartographic) | 139,449,505 | Cartographic variant; not needed — see the dossier's note that cartographic is a *clip*, not a generalisation |
| `lfed000b16a_e.zip` (StatCan 2016 cartographic) | 32,834,519 | Same |
