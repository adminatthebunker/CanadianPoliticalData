### licence

| Jurisdiction | Rows held | Source | Licence | Internal use | Redistribution | Notes |
|---|---:|---|---|---|---|---|
| National (postal geocode) | 8 | Open North Represent `/postcodes/` — incumbent | Undeclared to us; Geocoder.ca-derived | ⛔ down since 2026-08-07 | ⛔ rights never established | Cert expired `Aug 7 09:51:36 2026 GMT` + origin 502. Only the 8 cached codes resolve; every other Canadian postcode 503s |
| National (postal geocode) | 0 (staged) | StatCan National Address Register, cat. 46-26-0002, rel. `202606` | Statistics Canada Open Licence | ✅ yes | ✅ yes — *"use, reproduce, publish, freely distribute, or sell"* + sublicence | **Recommended.** Yields **856,929** codes (92.5%). `MAIL_POSTAL_CODE` + WGS84 `BG_LATITUDE`/`BG_LONGITUDE`, all 13 PR/T. Archive staged, sha256 recorded. Attribution required |
| National (FSA polygons) | 0 | StatCan 2021 Census FSA Boundary File, cat. 92-179-X | Statistics Canada Open Licence | ✅ yes | ✅ yes | 1,643 polygons, EPSG:3347. ⚠ Fallback only — see coverage table |
| National (civic addresses) | 0 | StatCan Open Database of Addresses, cat. 46-26-0001 v1.0 | Open Government Licence – Canada | ✅ yes | ✅ yes | ⛔ Rejected: 0–15.4% postal-code fill, only 7 municipalities contribute any |
| National (postal→FED) | 0 | StatCan PCFRF, cat. 92-178-X | Canada Post end-use licence, $892/yr | ⛔ no | ⛔ no | Closed. Last issue keyed to superseded 2013 Order (338 districts vs today's 343) |
| National (postal→geography) | 0 | StatCan PCCF, cat. 92-154-X | Canada Post licensed; DLI-restricted | ⛔ no | ⛔ no | Closed. Last public issue June 2017, released 2017-12-13 |
| National (postal geocode) | 0 | Geocoder.ca / Geolytica | CC-BY 2.5 Canada (non-profit, on request) OR ~$998 paid | 🚧 operator decision | 🚧 attribution required | 926,425 codes @ 2026-05-01. ⛔ Agent may not request — requires identifying the project and accepting terms |
| National (civic addresses) | 0 | OpenStreetMap `addr:postcode` | **ODbL** | ⏸️ deferred | ⚠ share-alike contaminates a redistributed table | 704,242 objects but only 97,961 distinct values (~11% ceiling) |
| Quebec (postal→prov district) | 0 | Elections Québec, via `opennorth/represent-canada-data` `concordances/…/province:qc/out.csv` | Elections Québec site terms; © Gouvernement du Québec, attribution required | ✅ yes | ✅ with attribution | ★ Only open postal→district concordance found. Use as a **PIP cross-check**, not a data source. Per-jurisdiction pattern worth checking elsewhere |
| National (boundary files) | n/a | `opennorth/represent-canada-data` | Per-directory; 86 `LICENSE.txt` files | ⚠ per-directory review | ⚠ **not transitive** | *"Open North has permission… In some cases, you will not have permission to redistribute."* Top-level file is GeoNB terms with a flow-down clause. **No postal data in the public repo at all** |

### coverage

| Jurisdiction | Rows held | Seats | Authoritative count | Vintage held | Current vintage | Delta |
|---|---:|---:|---:|---|---|---|
| National — postal codes (6-char) | 8 | n/a | ~926,425 active (Geocoder.ca, 2026-05-01) | on-demand cache, 2026-05-26 → 2026-08-14 | NAR `202606` (2026-06-26) | **−926,417.** Cache is 0.001% of the space; incumbent is down, so effective coverage is 8 codes |
| National — NAR derived | 0 (staged) | n/a | ~926,425 | none | NAR `202606` (2026-06-26) | **856,929 = 92.5%**, measured on the full register (17,362,476 rows, 99.67% fill). Shortfall 69,496. Structural ceiling ~97% — 3% of codes are PO-box / service-route only (StatCan 92F0138) — so ~95% of what is reachable |
| National — FSAs | 0 | n/a | 1,643 CFSAs (181 rural, 11.0%) | none | 2021 Census (rel. 2022-09-21) | −1,643. ⚠ 2026 Census FSA file imminent |
| Federal — postal→riding accuracy | n/a | 343 | n/a | n/a | NAR `FED_CODE`, 2023 Rep. Order | National, full register: 6-char urban **99.91%** (851,892 codes), 6-char rural **98.26%** (5,037); FSA urban 91.21%, **FSA rural 68.46%** (worst FSA 34.3%) |
| Provincial — postal→district accuracy (NS probe) | 55 | 55 | n/a | 2019 | 2019 | 6-char rural **96.34%**; **FSA rural 57.88%** — ⛔ unusable, up to 7 districts per rural FSA |
| Provincial — postal→district accuracy (MB probe) | 56 | 57 | n/a | 2018 | 2018 | 6-char rural **97.65%**; **FSA rural 52.82%** — ⛔ **100%** of MB rural FSAs span >1 district, up to 7 |
| National — rural share | n/a | n/a | n/a | n/a | NAR `202606` | Rural FSAs 182/1,673 (10.9%); rural postal codes **5,037/856,929 (0.59%)** — but 18–53% of *addresses* per province |
| National — provincial lookup, **no answer** | 665 (prov) | n/a | n/a | mixed 2012–2024 | authoritative varies | ⛔ **9.15% of Canadian addresses get nothing** (address-weighted, 32,500-address sample). BC contributes 6.05pp alone |
| National — provincial lookup, **wrong answer** | 665 (prov) | n/a | n/a | mixed | authoritative varies | ⚠ **2.12%** over the 6 jurisdictions with readable authoritative geometry (62.3% of addresses); any-error **12.61%**. BC 48.3%, YT 37.9%, NT 14.3%, ON 2.1%, NS 1.9%, AB 1.2% |
| National — federal lookup (control) | 342 | 343 | 343 | 2023 Rep. Order | 2023 Rep. Order | ✅ 0.95% no-answer + 0.83% wrong = **1.79%** — consistent with the one missing district; confirms the method does not over-report |
