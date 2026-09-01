> ⓘ **Written by proxy** (the municipal-ON/QC/Atlantic agent, 2026-08-18) from the content of
> [`../prince-edward-island.md`](../prince-edward-island.md), because its author was throttled.
> Every claim below is derived from that dossier; row counts re-verified against the DB. The
> dossier's author should sanity-check before consolidation.

### licence
| Jurisdiction | Rows held | Source | Licence | Internal use | Redistribution | Notes |
|---|---:|---|---|---|---|---|
| [Prince Edward Island](../prince-edward-island.md) | 26 | `gis.princeedwardisland.ca/server/rest/services` — layer `Provincial_Electoral_Wards_and_Polls`. ⛔ Elections PEI itself (`electionspei.ca`) is Radware-blocked | ⛔ **None stated anywhere** | ⚠ **defensible, not cleared** | ⛔ **no** | ⛔ `copyrightText` is the empty string on both FeatureServer and layer 0; `serviceDescription` and `description` empty; no metadata doc, no terms URL, no attribution string. **PEI is one of three provinces with no inheritable licence** — `represent-canada-data` holds only a 2006 directory, so there is no fallback provenance either. Data is public, unauthenticated and on a government open-data server, which is a reasonable basis for internal use — but *"no terms stated" is not "openly licensed"*, and PEI is the one jurisdiction where we would be relying on silence. **Raised as a handoff item.** ⚠ The agency that could clarify is behind the WAF |

### coverage
| Jurisdiction | Rows held | Seats | Authoritative count | Vintage held | Current vintage | Delta |
|---|---:|---:|---:|---|---|---|
| [Prince Edward Island](../prince-edward-island.md) | 26 | 27 | 27 | 2017 Schedule (undated in DB — `effective_from='2023-01-01'`, an Open North mirror date) | *Electoral Boundaries Act* Schedule as replaced by **SPEI 2017, c. 63, s. 1**; first used 2019-04-23 | ★ **Exactly 1 missing: `Georgetown - Pownal` (`DIST_NO` 2)** — confirmed primary-side twice, from the GIS layer's attribute table and from the statutory Schedule. All 26 of its neighbours are held. ✅ Seat count has been 27 across both generations — the 2017 commission had **no mandate to change it**, only to redraw, so PEI is a redraw-only boundary like Nunavut 2024 and unlike Québec 2026. ⛔ **Single-generation load only** — no prior geometry exists in any reachable form. ⚠ Next redistribution has no fixed cycle; a Commission is appointed under s. 8 of the Act |

### A6 prefix migration
| Jurisdiction | Current prefix | Target prefix | `politicians` | `politician_terms` | `constituency_boundaries` | Total |
|---|---|---|---:|---:|---:|---:|
| [Prince Edward Island](../prince-edward-island.md) | `prince-edward-island-electoral-districts-2017` | `prince-edward-island-electoral-districts` | 26 | 26 | 26 | **78** |

⛔ **A6 violation** — year in the prefix. Pure `replace()` substitution, reversible with the
inverse. ⓘ Low-risk here: PEI supports only a single-generation load, so there is no sibling
generation to collide with on the `(constituency_id, boundaries_version)` unique key.

### cross-jurisdictional findings from this dossier
- ★★ **The find: a wide-open public ArcGIS Server the province does not advertise.** `gis.princeedwardisland.ca/server/rest/services` carries `Provincial_Electoral_Wards_and_Polls` — all 27 districts, no auth, no WAF, no rate limit — and is **invisible to the province's own open-data portal search**, which is why PEI looks like it publishes nothing. **Difficulty 2 via the GIS server; 5 via Elections PEI.** Generalises: an agency being WAF-blocked says nothing about whether a *sibling government host* serves the same data.
- ⚠⚠ **Severest one-polygon-per-row trap in the corpus: 270 poll polygons for 27 districts, plus 26 blank junk rows.** Poll counts run 7–12 per district (`Alberton - Bloomfield` 12; `Mermaid - Stratford` and `Evangeline - Miscouche` 7). A naive insert yields 10× duplication collapsing onto 27 `constituency_id` values, **plus a phantom 28th district** from the blank rows. **The build must dissolve on `DIST_NO`** and drop the blanks. Far worse than the federal 352-for-343 case.
- ⚠ **A Radware WAF that returns HTTP 200 — the A4 status-code trap, live.** `electionspei.ca` behaves conventionally (302 → `validate.perfdrive.com`, `__uzma`/`__uzmb`/`__uzmc` cookies). But `www.princeedwardisland.ca` returns **HTTP 200 with a "Verifying your browser" stub body**, so a status-code liveness check reports it open. Compare payloads, not status codes.
- ⚠ **Legal in-force date unresolved under A2, and bounded rather than unknown.** The Schedule was replaced by 2017, c. 63, s. 1 (citation at the foot of the office consolidation: `2006,c.44,s.9; 2017,c.63,s.1.`). The consolidation is "current to March 26, 2019" and already incorporates it, and the map was first used **2019-04-23** — so the legal date lies between the 2017 fall sitting and 2019-03-26. The exact assent/proclamation date is **`needs confirmation`**: the PEI Table of Public Acts would settle it in one lookup but lives on the WAF-blocked HTML estate. Interim value **2019-04-23**, marked provisional — never *later* than the truth in a way that would misattribute an address.
- ⛔ **No prior geometry exists in any reachable form.** The ArcGIS layer holds the current generation only — no `_2006`, `_historic` or date-filtered variant, no versioned archive. The 2017 Commission report (`epeiEBC2017.pdf`, 2017-05-05) would document the prior boundaries, but its old `gov.pe.ca` URL now 301-chains to a generic publications index, and that index is WAF-blocked. **Known bounded gap**; recorded so nobody re-probes the URL.
- ⓘ **Municipal PEI is a separate and harder problem** — see [`municipal-atlantic.md`](../municipal-atlantic.md). Charlottetown, Summerside and Stratford have **no machine-readable ward source at all** (no CKAN at `data.princeedwardisland.ca`, no ArcGIS ward layer, no ward layer on `gov.pe.ca/gis`); Elections PEI publishes ward and poll *maps* only. ★ Note the provincial GIS server that solves provincial PEI does **not** carry municipal wards — the two findings are independent.
