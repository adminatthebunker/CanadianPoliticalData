# Yukon 2015 electoral districts — exported from our own database

⚠ **This is a preservation copy, not an upstream download.** The 2015 Yukon electoral
district geometry appears to be **no longer available anywhere upstream**: GeoYukon
overwrote the layer in place (`MapServer/12` now returns 500) and both `open.canada.ca`
mirrors are delisted (404). Our `constituency_boundaries` table may hold the last
public copy.

Exported 2026-08-18 by the boundary-research coordinator, before any build work touches
the table, so the 2015 generation cannot be lost to an in-place update.

| Field | Value |
|---|---|
| Source | `constituency_boundaries WHERE province_territory='YT' AND level='provincial'` |
| Exported | 2026-08-18T01:24:36Z |
| Features | 19 (MultiPolygon, EPSG:4326) |
| Bytes | 564181 |
| sha256 | 5cf6f0ffdb9effc02e94344671906664db38cc02ac3b99d148f056cdf8ae9136 |
| Licence | Originally Open North mirror of Yukon data; see `../PROVENANCE.md` |

**Caveat on trustworthiness.** These rows came from Open North and carry a fabricated
`effective_from = 2023-01-01` (hardcoded for every row in the table by
`opennorth.py`). The true prior-generation in-force date is **2016-10-07**. The geometry
itself spot-checks well — districts the 2024 order left unchanged match authoritative
shapes to within 0.4% — but this copy has not been validated against an upstream original,
because no upstream original remains to validate against.
