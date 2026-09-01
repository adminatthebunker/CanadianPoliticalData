> ⓘ **Written by proxy** (the municipal-ON/QC/Atlantic agent, 2026-08-18) from the content of
> [`../newfoundland-labrador.md`](../newfoundland-labrador.md), because its author was throttled.
> Every claim below is derived from that dossier; row counts re-verified against the DB. The
> dossier's author should sanity-check before consolidation.

### licence
| Jurisdiction | Rows held | Source | Licence | Internal use | Redistribution | Notes |
|---|---:|---|---|---|---|---|
| [Newfoundland and Labrador](../newfoundland-labrador.md) | 36 | Open Data NL portal — `opendata.gov.nl.ca` dataset 361 (`NL_EB_Poly_50k.zip`, 15.5 MiB SHP); prior generation from Wayback only | ✅ **Open Government Licence – Newfoundland and Labrador v1.0**, https://opendata.gov.nl.ca/public/opendata/page/?page-id=licence | ✅ **yes** | ✅ **yes** | Canadian OGL family, Class A / transferable. Verbatim grant: *"The Information Provider grants You a worldwide, royalty-free, perpetual, non-exclusive licence to use the Information, including for commercial purposes."* "Publish" and "distribute" named explicitly; no viral flow-down, nothing to attach to API responses — clears `/api/public/v1/boundaries/*`. Attribution required, verbatim: *"Contains information licensed under the Open Government Licence – Newfoundland and Labrador."* No click-through, no account |

### coverage
| Jurisdiction | Rows held | Seats | Authoritative count | Vintage held | Current vintage | Delta |
|---|---:|---:|---:|---|---|---|
| [Newfoundland and Labrador](../newfoundland-labrador.md) | 36 | 40 | 40 | 2015 commission set (undated in DB — `boundaries_version='current'`, `effective_from='2023-01-01'` placeholders) | 2015 Electoral Districts Boundaries Commission (*Electoral Boundaries Act*, RSNL1990 c. E-4, s. 13(1)) | ⛔ **Exactly 4 missing**: `Burgeo - La Poile`, `Humber - Gros Morne`, `Labrador West`, `St. John's East - Quidi Vidi`. ★ **Not the BC defect** — Open North's NL *roster* is short (36 members for a 40-seat House), so those 4 districts never had a representative to hang a boundary off. Same root trap (boundaries ingested as a side effect of roster ingestion), opposite proximate cause. ⚠ The brief's "8 districts with zero matching officials" **does not reproduce** — zero orphans; the real 8 is 8 duplicate `direct:assembly-nl-ca` politician rows with `NULL constituency_id`. ⚠ **Next redistribution is due now** — s. 13(2) requires a commission "in the calendar year beginning in 2026". ✅ Prior 48-district generation recovered and staged |

### A6 prefix migration
| Jurisdiction | Current prefix | Target prefix | `politicians` | `politician_terms` | `constituency_boundaries` | Total |
|---|---|---|---:|---:|---:|---:|
| [Newfoundland and Labrador](../newfoundland-labrador.md) | `newfoundland-and-labrador-electoral-districts` | *(no change)* | 36 | 36 | 36 | **0** |

✅ **NL is the one jurisdiction already A6-compliant** — the prefix encodes no generation. No
migration needed; it is the shape every other jurisdiction is being moved toward. ⚠ Still carries
the corpus-wide `boundaries_version='current'` placeholder, so the generation is unrecorded.

### cross-jurisdictional findings from this dossier
- ⛔ **A non-EPSG custom projection — the strongest `.prj` trap in the corpus.** The `.prj` names `SESA-TM`: Transverse Mercator on the **WGS84** datum (not NAD83), central meridian −59.5°, scale factor **0.998**, false easting **1,000,000 m**. Not UTM (0.9996 / 500,000), not NL's MTM zones, no `AUTHORITY` clause, and **no standard EPSG code identified**. Do not guess one — register it in `spatial_ref_sys` under a private SRID (900000+) with `+proj=tmerc +lat_0=0 +lon_0=-59.5 +k=0.998 +x_0=1000000 +y_0=0 +datum=WGS84 +units=m +no_defs`, then `ST_Transform`. ⚠ This is exactly where the Fort Erie bug recurs: an unrecognised `.prj` invites `ST_SetSRID(…, 4326)`, storing metres as degrees; the `boundary_in_wgs84_bounds` CHECK would reject the rows and — per the loader trap — that rejection is currently **swallowed**, so NL would silently end up with zero boundaries.
- ⛔ **Weakest key situation in the corpus: the `.dbf` has exactly one field.** dBase III, 40 records, `DIST_NAME` (C, 50) and nothing else — no ID, no code, no population, no area, no date. Contrast BC's `ELECTORAL_DISTRICT_ID`. Any `authority_district_id` would have to be the name itself.
- ⚠ **The single key field carries an upstream typo** — `Cartwright - L'Anse aux Clair`, which should be *au* Clair. Confirmed a regression, not house style, because the prior-generation file spells it correctly. A typo in the *only* join key is unusually costly.
- ✅ **A4 distinct-ID check passed** — 40 records / 40 distinct names, one row per district despite NL being heavily islanded. No duplicate-key risk.
- ⚠ **A tempting false pattern to refuse:** Elections NL says the province has "36 districts on the island and 4 in Labrador", and we hold 36. **Unrelated.** We hold 3 of 4 Labrador districts and are missing 1 Labrador + 3 island. Pure numerology — worth stating so nobody "explains" the gap with it.
- ★ **A5 Wayback CDX recovered the prior generation after every origin URL 404'd.** The sweep over `elections.gov.nl.ca/*` surfaced seven archived spatial artifacts; `Distribution_2011.zip` (48 districts) was the only prior-generation district file, with genuine 200 captures through 2025-08-02. ★ One archived path carries an **upstream spelling error** (`Distibution_2011.zip`) — a CDX sweep catches that where URL guessing never would. Other artifacts found, recorded so nobody re-probes: `Basic_Polls_Shapefile 2015/2019.zip`, `Island_2015.zip` + `Labrador_2015.zip`, `2015GEResults.zip`.
- ⚠ **Legal in-force date unresolved under A2.** The *Electoral Boundaries Act* is unusually quiet on commencement — s. 14(2) covers tabling but **no section specifies a proclamation or automatic in-force mechanism**, unlike BC's `Electoral Districts Act` s. 6. Candidates recorded: dataset metadata **2015-09-10**, first use **2015-11-30**. Legal date `needs confirmation`.
