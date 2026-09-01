# Prince Edward Island — Electoral Boundary Research

> Standalone boundary/roster dossier for Prince Edward Island. Cross-cutting context
> (methodology, licence matrix, reconciliation strategy) lives in [`overview.md`](./overview.md).
> The legislative-data dossier for this jurisdiction is at [`../prince-edward-island.md`](../prince-edward-island.md).

**Agency:** Elections PEI | **Website:** https://www.electionspei.ca | **Districts (current):** 27 | **Current order:** *Electoral Boundaries Act* Schedule as replaced by **SPEI 2017, c. 63, s. 1** | **Next redistribution:** no fixed cycle — a Commission is appointed under s. 8 of the Act

**Status snapshot (2026-08-18):** ★ **Elections PEI is blocked, but the boundaries are obtainable anyway — from a different government host the agency does not advertise.** ⛔ `electionspei.ca` is behind **Radware ShieldSquare**, the same WAF the legislative-data dossier recorded for `assembly.pe.ca`: 302 to `validate.perfdrive.com`, `__uzma`/`__uzmb`/`__uzmc` cookies, confirmed against two independent clients. **Elections PEI itself is difficulty 5** and I did not attempt to work around it. ⚠ `www.princeedwardisland.ca` is also blocked but *presents differently* — `HTTP 200` with a "Verifying your browser" stub body, so a status-code check reports it open. That is the A4 trap and it caught me for one step. ★★ **The find: `gis.princeedwardisland.ca/server/rest/services` is a wide-open public ArcGIS Server, and it carries `Provincial_Electoral_Wards_and_Polls`** — all 27 districts, no auth, no WAF, no rate limit. It is **invisible to the province's own open-data portal search**, which is why it looks like PEI publishes nothing. ★ **The missing 27th district is `Georgetown - Pownal` (District 2)**, confirmed primary-side twice over: from the GIS layer's own attribute table and from the statutory Schedule of the *Electoral Boundaries Act*. ⚠⚠ **Severest one-district-per-row trap in the corpus so far: 270 poll polygons for 27 districts, plus 26 blank junk rows.** A naive load produces 10× duplication and a phantom 28th district. ⛔ **No licence is stated anywhere** — `copyrightText` is empty on the service and the layer, and the agency that would say otherwise is behind the WAF. **Difficulty 2** via the GIS server; **5** via Elections PEI.

---

## Current boundaries

- **Source URL(s):** https://gis.princeedwardisland.ca/server/rest/services/Provincial_Electoral_Wards_and_Polls/FeatureServer/0 ; https://gis.princeedwardisland.ca/server/rest/services?f=json ; https://www.princeedwardisland.ca/sites/default/files/legislation/e-02-1-electoral_boundaries_act.pdf
- **Format:** ArcGIS Server **FeatureServer**, `capabilities: Query` (read-only). ⚠ The service advertises `supportedQueryFormats: JSON` only — **`f=geojson` is not supported**, so the staged artifact is raw **Esri JSON** and the build must convert. `maxRecordCount` is 2000; all 270 features return in one call with no `exceededTransferLimit`. No downloadable shapefile, GeoJSON, KML or GDB is published anywhere reachable.
- **CRS / projection:** **EPSG:2954** — NAD83(CSRS) / Prince Edward Isl. Stereographic, coordinates in metres. The service reports `{"wkid": 2291, "latestWkid": 2954}`; **use 2954**, as 2291 is the deprecated NAD83(CSRS98) variant. There is no `.prj` to read — the CRS comes from the service metadata — so this is another case where the EPSG must be asserted explicitly at load. Verified through PostGIS: `(408500, 674773)` in 2954 → `-62.8900, 46.1234`, central PEI. (2291 transforms identically at this precision; the datum difference is centimetres.)
- **Attribute schema:** 18 fields from the layer definition. The ones that matter: **`DIST_NO`** `esriFieldTypeInteger` — district number 1–27; **`DISTRICT`** `esriFieldTypeString(100)` — district name, spaced as `Souris - Elmira`; `POLL_NO` `esriFieldTypeInteger`; `POLL_NAME` `esriFieldTypeString(75)`; `ET_ID` Double; `AREA_SQM` Double; `electorcou` Double (elector count); `civicaddre` Double; `dwellingco` Double; `censuselec`, `censuspopu`, `censusarea` Double; `sort_order` SmallInteger; `OBJECTID_1` OID; `OBJECTID` Integer; `Shape_Leng`, `Shape__Area`, `Shape__Length` Double. Field names are truncated at 10 characters in the classic shapefile style (`electorcou`, `civicaddre`, `dwellingco`), which suggests the layer was published from a shapefile.
- **District ID field:** **`DIST_NO`** — integer 1–27, dense, no gaps, matches the district numbers in the statutory Schedule. This is the stable authority key for PEI and it is a good one. `DISTRICT` carries the name. ⚠ Neither field is unique per row — see the district count note.
- **Effective date:** **`effective_from` = commencement of SPEI 2017, c. 63 — `needs confirmation`.**
  - **Statutory instrument identified:** the Schedule to the *Electoral Boundaries Act*, R.S.P.E.I. 1988, Cap. E-2.1, was replaced by **2017, c. 63, s. 1**. The citation appears at the foot of the Schedule in the office consolidation: `2006,c.44,s.9; 2017,c.63,s.1.` Section 2(1) reads, verbatim: *"The province, for the purpose of the election of members to serve in the Legislative Assembly, is divided into twenty-seven districts, with the names, district numbers and boundaries as set out in the Schedule."*
  - **What is firm:** the consolidation is stated "current to March 26, 2019" and already incorporates 2017, c. 63, so the replacement Schedule was in force by then. The map was first used at the general election of **2019-04-23**. So the legal date lies between the 2017 fall sitting and 2019-03-26.
  - **What is not firm:** the exact assent or proclamation date. Per A2 I am not inventing one. The PEI Table of Public Acts would settle it in one lookup, but it lives on the WAF-blocked HTML estate and could not be reached by filename guessing. **`needs confirmation` — see handoff items.** As an interim value the build could use **2019-04-23** (first election held on these boundaries) and mark it provisional; that is defensible operationally and is never *later* than the truth in a way that would misattribute an address.
  - ⚠ **Dataset-metadata date: none available.** The ArcGIS layer exposes no publication or vintage field at all — no `CreaDate`, no `description`, no metadata document. So unlike Nunavut and Québec there is no metadata-vs-legal discrepancy to record, only an absence.
- **Superseded date:** n/a — current generation.
- **District count:** **27**, matching the 27 seats. ✅ Confirmed independently from the layer (`DIST_NO` 1–27, all present) and from the statutory Schedule (`2. The electoral districts are as follows: 1. Souris-Elmira … 27. Tignish-Palmer Road`).
- **Difficulty (1–5):** **2** — undocumented but structured, exactly the probe-hierarchy case. The service is unlisted, unadvertised, and absent from the province's open-data search, but once found it is a clean REST API. **Elections PEI itself is 5.**
- **Notes:**
  - ⚠⚠ **One polygon per POLL, not per district — 270 rows for 27 districts.** This is the trap flagged in A4, and here it is an order of magnitude worse than the federal 352-for-343 case. Poll counts run 7–12 per district (`Alberton - Bloomfield` has 12, `Mermaid - Stratford` and `Evangeline - Miscouche` have 7). **The build must dissolve on `DIST_NO`**; a straight insert yields 270 rows collapsing onto 27 `constituency_id` values.
  - ⚠ **26 of the 270 rows are blank filler** — `DIST_NO = 0`, `DISTRICT = ' '`, `POLL_NAME = ' '`, `electorcou = 0.0`, one ring each. Grouping without filtering produces a **phantom 28th district** with an empty name. **Filter `WHERE DIST_NO > 0`.** 244 real poll polygons + 26 junk = 270.
  - ★ **PEI's districts are legally defined by civic address, not by geometry.** Schedule s. 1(3), verbatim: *"The civic address assigned to a property pursuant to the Emergency 911 Act determines the electoral district in which the property is located."* The polygons are a rendering of an address-based rule, not the rule itself. That is worth knowing before we present PEI point-in-polygon results as authoritative — near a boundary, the civic address governs and our polygon may not.
  - ⚠ **The statute contains a typo in a district name.** Schedule entry 20 reads **`Kensingston-Malpeque`**. The GIS layer says `Kensington - Malpeque` and so do we. Use the GIS spelling; note the statute if anyone ever diffs against it.
  - Name spacing differs between sources: the GIS layer and our DB use `Souris - Elmira` (spaces around the hyphen), the statute uses `Souris-Elmira` (no spaces). Normalise before joining.

## Prior boundaries (immediately preceding)

- **Source URL(s):** https://www.princeedwardisland.ca/sites/default/files/legislation/e-02-1-electoral_boundaries_act.pdf (statutory text only)
- **Format:** ⛔ **No geometry available.** The ArcGIS layer holds the current generation only — there is no `_2006`, `_historic` or date-filtered variant on the server, and no versioned archive.
- **CRS / projection:** n/a.
- **Attribute schema:** n/a.
- **District ID field:** `DIST_NO` 1–27 under the prior Schedule too, but the districts themselves differ.
- **Effective date:** the prior Schedule was enacted by **2006, c. 44, s. 9**, and governed the 2007, 2011 and 2015 general elections. Precise commencement `needs confirmation`, same blocker as above.
- **Superseded date:** superseded by 2017, c. 63, s. 1 — same `needs confirmation` date as the current generation's `effective_from`.
- **District count:** 27. The seat count has been 27 across both generations; the 2017 commission had **no mandate to change it**, only to redraw. So PEI is a redraw-only boundary, like Nunavut 2024 and unlike Québec 2026.
- **Difficulty (1–5):** **5** for geometry — not published in any reachable form.
- **Notes:** **Known bounded gap.** PEI can support only a single-generation load. The 2017 Electoral Boundaries Commission report (`epeiEBC2017.pdf`, dated 2017-05-05) would document the prior boundaries and the changes, but its old `gov.pe.ca` URL now 301-chains to a generic publications index — the file has been relocated or withdrawn, and the index that would give its new path is WAF-blocked. Recorded so nobody re-probes that URL.

## District ↔ elected official mapping

- **Source URL(s):** https://gis.princeedwardisland.ca/server/rest/services/Provincial_Electoral_Wards_and_Polls/FeatureServer/0 (districts only) ; https://www.assembly.pe.ca (⛔ WAF-blocked) ; https://www.electionspei.ca (⛔ WAF-blocked)
- ⛔ **No reachable source maps districts to sitting MLAs.** Both the Legislative Assembly and Elections PEI are behind Radware. The GIS layer carries geography and elector counts but no member names.
- ⚠ **Our roster has the same 26-of-27 gap as our boundaries** — 26 PEI MLAs, all 26 with a populated `constituency_id`, zero dangling references. Both were mirrored from Open North, so the gap is correlated, not independent: **the internal diff cannot identify the missing district**, because the district is missing from both sides. That is why the identification below had to come from outside our data.
- ✅ **`Georgetown - Pownal` (District 2) is the missing one**, established from two primary sources that agree: the GIS layer's attribute table (`DIST_NO = 2`, `DISTRICT = 'Georgetown - Pownal'`, 9 polls) and the *Electoral Boundaries Act* Schedule (`2. Georgetown-Pownal`, with a full metes-and-bounds description and the line *"All as more particularly shown on the map for Electoral District 2 Georgetown - Pownal"*). The district is live — there was a Georgetown-Pownal by-election in 2025.
- **No per-MLA stable identifier was found**, because no reachable source lists MLAs at all. Per CLAUDE.md convention #1 a `pe_assembly_slug` column is still the right shape when a source unblocks; the existing legislative dossier already carries that as an open item.
- ⚠ Historical note for whoever reconciles the roster: at the 2019 general election the vote in **Charlottetown - Hillsborough Park** was deferred to **2019-07-15** following the death of a candidate, so 26 of 27 districts polled on 2019-04-23. Any term-start backfill keyed to the general-election date alone will get that district wrong.

## Postal-code correspondence (if published)

**One-line answer (per amendment A3):** ⛔ **None published, and PEI is the jurisdiction where one
would matter least anyway.**

- No postal-code table appears on the GIS server, on `data.princeedwardisland.ca`, or anywhere else reachable. Elections PEI might publish one; it is behind the WAF.
- ★ **But PEI has something better in principle and worse in practice.** Schedule s. 1(3) makes the **civic address** the legal determinant of a property's district, and the GIS layer carries a `civicaddre` count per poll — so the province plainly maintains an address→district assignment internally. It is not published. A civic-address concordance would be strictly better than a postal one, since it *is* the legal rule rather than an approximation of it.
- The province does publish a `civic_addresses` feature service on the same open ArcGIS Server. **`UNTESTED — probe during build`:** whether it carries a district field. If it does, PEI gets an exact address-level lookup rather than a polygon approximation, which would make it the most accurate jurisdiction in the corpus rather than one of the shakiest. Not pursued here — it is address-geocoding scope, not boundary scope, and belongs with the geocoding dossier.

## Terms / Licensing

⛔ **Unresolved, and not resolvable from any machine-reachable source. This is the PEI blocker.**

- **The ArcGIS service states nothing.** `copyrightText` is the empty string `''` on both the FeatureServer and layer 0. `serviceDescription` and `description` are empty. There is no metadata document, no licence field, no attribution string, no terms URL.
- **The Hub front end does not cover this layer.** `data.princeedwardisland.ca` is an ArcGIS Hub site (subdomain `data-princeedwardisland`) fronting the same server, and it is reachable — but `Provincial_Electoral_Wards_and_Polls` **is not in its catalogue**, so there is no dataset page carrying terms. Targeted searches of the org's public items for `electoral`, `election`, `polling`, `riding` and `constituency` all return **0**.
- **The agency that would state terms is behind the WAF.** `electionspei.ca` and `assembly.pe.ca` both bounce.
- This matches X2's finding that **PEI is one of the three provinces with no inheritable licence** — the only thing in `represent-canada-data` is a 2006 directory. So there is no fallback provenance to lean on either.
- **The Act PDF** carries the standard Legislative Counsel Office notice, verbatim: *"This document, prepared by the Legislative Counsel Office, is an office consolidation of this Act, current to March 26, 2019. It is intended for information and reference purposes only. This document is not the official version of the Act."* Crown copyright, Province of Prince Edward Island. It is staged as evidence of the statutory basis, not as redistributable content.
- **Assessment:** the data is public, unauthenticated, and published by a government open-data server, which is a reasonable basis for internal use. But "no terms stated" is not the same as "openly licensed", and PEI is the one jurisdiction in this pair where we would be relying on silence. Raised as a handoff item.

## Rate limits / auth

- ✅ **`gis.princeedwardisland.ca` — no auth, no rate limiting, no WAF.** ~10 requests including a 13 MB geometry query, all clean. Read-only (`capabilities: Query`). This host appears to be entirely outside the Radware deployment.
- ⛔ **`www.electionspei.ca` — Radware ShieldSquare, hard block.** Every request 302s to `validate.perfdrive.com?...&ssk=botmanager_support@radware.com`, setting `__uzma`/`__uzmb`/`__uzmc`/`__uzmd`/`__uzme`/`__uzmf`/`uzmx` cookies. Confirmed with **two independent clients**: curl with a realistic Chrome UA, and WebFetch (which identified itself honestly as `Claude-User (claude-code/…)` and was bounced identically). Underlying stack is Drupal (`x-drupal-dynamic-cache: MISS`). **I did not follow the challenge URL** — passing a bot-management gate is working around the block, which is out of scope. Difficulty **5**.
- ⚠ **`www.princeedwardisland.ca` — Radware too, but disguised.** Returns `HTTP 200` with a 125 KB body that is the challenge page: *"Radware Page / Verifying your browser before proceeding... Incident ID: …"*. **A status-code check reports this host as open. It is not.** This is exactly the A4 "200 error page" trap; I recorded the host as reachable for one step before checking the payload.
- ★ **The carve-out that made the Act retrievable: static files under `/sites/default/files/` are NOT challenged.** `…/sites/default/files/legislation/e-02-1-electoral_boundaries_act.pdf` returns `HTTP 200 application/pdf`, 4.68 MB, immediately. **This is a materially useful finding for [`../prince-edward-island.md`](../prince-edward-island.md)**, which currently rates the whole PEI estate difficulty 5 — bills and Hansard PDFs may well be fetchable by direct file path even though every listing page is blocked. The catch is that you must already know the filename, and the pages that reveal filenames are challenged. Guessing failed for the Table of Public Acts (three plausible names, all 404).
- ⛔ **Dead end — `gov.pe.ca` is retired.** `gov.pe.ca/photos/original/epeiEBC2017.pdf` 301-chains through `www.gov.pe.ca` to `https://www.princeedwardisland.ca/en/publications`. Search engines still index the old paths; they no longer resolve to files.
- ⛔ **Dead end — PEI's open-data portal has no electoral layer.** `data.princeedwardisland.ca` is reachable, and the ArcGIS org behind it (owner `pei_enterprise_admin`, Hub group `3f3e0df042854ea59560465cde7987cc`) was searched directly: `electoral` → 0, `election` → 0, `polling` → 0, `riding` → 0, `constituency` → 0. The 100-item public catalogue contains fire, school, police, ambulance, county, municipal and emergency-service zones but no electoral geography. ★ **The layer exists on the underlying ArcGIS Server but was never surfaced to the Hub** — which is the entire reason it looks like PEI publishes nothing. Enumerating `…/server/rest/services?f=json` (82 services across 17 folders) is what found it.
- ⏸️ **`open.canada.ca` — not established.** The first query of the session succeeded; subsequent PEI queries were rejected with a *"Request Rejected … support ID"* HTML page rather than JSON, which reads as IP rate limiting rather than an empty result. **`UNTESTED — probe during build`;** I am not recording a negative I did not actually obtain.
- ⏸️ **`geo.ca` — not established.** `geocore.api.geo.ca/geo` returned a Lambda `INVALID_FUNCTION_ARGUMENT: Invalid WKT: POLYGON((undefined undefined…))` runtime error for a keyword-only query, i.e. the endpoint wants a bounding box. Not retried — the authoritative source was already in hand.

## Staged files

Staged under `data/boundaries/prince-edward-island/` with `PROVENANCE.md`. **18 MB total.**
Nothing converted, reprojected, or loaded — in particular `outSR` was deliberately **not** passed
to the query endpoint, so the staged coordinates are the server's native EPSG:2954 metres rather
than a server-side reprojection.

| Generation | File | Bytes | sha256 (first 16) |
|---|---|---:|---|
| current | `Provincial_Electoral_Wards_and_Polls_esrijson_native2954.json` | 13,368,875 | `76dd232c3baf4892…` |
| current | `e-02-1-electoral_boundaries_act.pdf` | 4,684,724 | `02849e8ce0767f95…` |

No `prior/` directory — there is nothing to put in it.

## Reconciliation with `constituency_boundaries`

**What we hold:** `source_set = 'prince-edward-island-electoral-districts-2017'`, **26 rows**,
`level = 'provincial'`, `province_territory = 'PE'`, `effective_from = 2023-01-01` (Open North
mirror date, not a legal date). Slug pattern
`prince-edward-island-electoral-districts-2017/{kebab-name}`, e.g.
`prince-edward-island-electoral-districts-2017/alberton-bloomfield`.

### The missing 27th district

**`Georgetown - Pownal`, `DIST_NO` 2.** Our 26 rows include every one of its neighbours —
`Souris - Elmira` (1), `Montague - Kilmuir` (3), `Belfast - Murray River` (4),
`Mermaid - Stratford` (5), `Stratford - Keppoch` (6), `Morell - Donagh` (7) — which is consistent
with a single-row mirroring gap rather than a systematic one. Slug to mint:
`prince-edward-island-electoral-districts-2017/georgetown-pownal`.

### Name matching

✅ **26/26 exact on the GIS layer's `DISTRICT` field**, using the same normalisation applied
elsewhere in this corpus (casefold, collapse whitespace around hyphens). Our stored names already
use the layer's ` - ` spacing convention, so the two agree character-for-character apart from case
folding. Adding the 27th makes it 27/27. **No re-key required, no fuzzy matching, no diacritics** —
PEI district names are plain ASCII throughout, including `O'Leary - Inverness` whose apostrophe is
a plain `U+0027`.

⚠ Two spellings to be aware of when joining against non-GIS sources: the statute writes
`Souris-Elmira` without spaces, and misspells district 20 as `Kensingston-Malpeque`.

### `DIST_NO` as the authority key

`DIST_NO` is an integer 1–27 that matches the statutory district numbers, so unlike Québec's
`CO_CEP` it is **semantically anchored in the Act** rather than being an internal code. Whether it
survives a future redistribution unchanged is unknown — PEI has kept 27 districts across both
generations and renumbering would be gratuitous, but Québec renumbered wholesale with zero overlap,
so **do not assume**. Recommend storing `DIST_NO` as a per-generation attribute and keying identity
on the normalised name, consistent with the Québec recommendation.

### ⚠ The load is not a straight insert

PEI is the one jurisdiction in this pair that needs a real transformation step:

1. Filter `WHERE DIST_NO > 0` — drops the 26 blank junk rows.
2. Dissolve the remaining 244 poll polygons by `DIST_NO` → 27 `MultiPolygon`s.
3. `ST_SetSRID(geom, 2954)` then `ST_Transform(…, 4326)`. The CRS comes from the service metadata, not from a `.prj`.
4. Assert exactly 27 rows out. Anything else means the filter or the dissolve is wrong.

The existing `boundary_in_wgs84_bounds` check constraint is a useful backstop here — PEI
coordinates are ~400,000 m eastings, so a forgotten transform fails loudly rather than silently.

### Proposed `constituency_id` scheme

Keep `prince-edward-island-electoral-districts-2017/{kebab-name}` unchanged — 26 of 27 slugs
already exist and are correct, so re-keying would be pure churn. Add the one missing slug.

⚠ Flag for **Agent X2**: the set name says `-2017` (the amending Act's year), while the map's
first electoral use was 2019 and its precise commencement is unconfirmed. Same pattern as Québec,
where `-2017` names the Gazette year and the legal date is 2018. **If the global re-key
standardises set names on in-force years, both provinces move together** — and PEI's would be
unresolvable until the commencement date is confirmed, which is an argument for standardising on
*publication/enactment* year rather than in-force year.

## Research-handoff items

- ⛔ **PEI boundary data has no stated licence at all, and the only body that could state one is behind a WAF.** The ArcGIS service returns an empty `copyrightText`; the layer is absent from the province's Hub catalogue so there is no dataset page; X2 found nothing inheritable in `represent-canada-data` beyond a 2006 directory. The data is public and unauthenticated on a government server, which is a reasonable basis for internal use — but **"no terms stated" is not "openly licensed"**, and PEI would be the one jurisdiction where we rely on silence. **Do we proceed on that basis, or email Elections PEI / the PEI GIS group and ask? And is internal-only use acceptable while redistribution stays blocked?**
- **The legal in-force date for SPEI 2017, c. 63 is unconfirmed.** The instrument is identified and the Schedule text is in hand; only the assent/proclamation date is missing, and it needs the PEI Table of Public Acts, which is on the WAF-blocked HTML estate. **Is `2019-04-23` (first general election on these boundaries) acceptable as a provisional `effective_from` with a `needs confirmation` marker, or should this block the PEI load?** My recommendation is proceed provisionally — the interim value is never late enough to misattribute an address to a superseded district.
- ★ **The Radware carve-out is worth writing back into the legislative dossier.** [`../prince-edward-island.md`](../prince-edward-island.md) rates all of PEI difficulty 5 on the strength of the WAF, but **static files under `princeedwardisland.ca/sites/default/files/` are served unchallenged** — a 4.7 MB statute PDF came back instantly. Bills and Hansard may be reachable the same way. The obstacle is filename discovery, not fetching. **Should someone re-probe PEI bills/Hansard on that basis before the Playwright investment that dossier contemplates?** That could turn a difficulty-5 jurisdiction into a difficulty-3 one for a fraction of the cost.
- **`civic_addresses` on the same open GIS server may carry a district field.** PEI's districts are *legally* defined by civic address (Schedule s. 1(3)), not by geometry, so an address→district table would be the authoritative lookup and our polygons would become a fallback rather than the source of truth. **Worth a probe — and if it pans out, does PEI get an address-level lookup path distinct from the PIP path used everywhere else?** Not pursued here; it straddles this dossier and the geocoding one.
- **PEI can only ever be a single-generation load from primary sources.** No prior geometry is published, and the 2017 Commission report PDF has been withdrawn from `gov.pe.ca`. **Accept 27 districts with no history, or ask Elections PEI for the prior file?**
- **Confirm nobody else needs `open.canada.ca` unblocked.** My PEI queries there started being rejected with a support-ID page after earlier successful queries this session — almost certainly IP rate limiting across the agent fleet rather than anything PEI-specific. Worth knowing if several agents are hitting it concurrently.

## Status

> ⚠ **Reconciled 2026-09-01.** The checkboxes below are the **research phase's** record
> (closed 2026-08-18) and several were overtaken by the build — migrations `0064`–`0121`,
> merged to `main` 2026-08-28. An unticked box here is **not** evidence that something is
> still outstanding.
>
> **Live counts: [`PROGRESS.md`](./PROGRESS.md)** (generated by `boundary-progress`).
> **What actually landed:** the migration headers, which are the accurate record.
> This file's job is the *reasoning* — sources, licences, traps, vintage evidence.

- [x] Current boundaries located and staged (2026-08-18) — via the unlisted `gis.princeedwardisland.ca` ArcGIS Server
- [x] Missing 27th district identified — **`Georgetown - Pownal`, `DIST_NO` 2** — confirmed from the GIS layer and the statutory Schedule
- [x] Statutory instrument identified — **SPEI 2017, c. 63, s. 1**, replacing the Schedule to the *Electoral Boundaries Act*, R.S.P.E.I. 1988, Cap. E-2.1
- [x] CRS identified — **EPSG:2954**; no `.prj` exists, so it must be asserted at load; verified by PostGIS transform
- [x] Attribute schema read from the layer definition — `DIST_NO` / `DISTRICT` / `POLL_NO` / `POLL_NAME` + 14 others
- [x] ⚠ **One-district-per-row checked and FAILED** — 270 poll polygons for 27 districts, plus 26 blank `DIST_NO = 0` rows; dissolve + filter required
- [x] Name reconciliation confirmed — 26/26 exact, 27/27 once the missing district is added, no re-key
- [x] Elections PEI accessibility established — ⛔ **Radware ShieldSquare, difficulty 5**, confirmed with two clients, not worked around
- [x] Matrix fragment written to `_matrix/prince-edward-island.md` per A1 — `overview.md` not touched
- [ ] **Licence cleared — ⛔ blocked: no terms stated anywhere, agency unreachable**
- [ ] Legal in-force date confirmed — **`needs confirmation`**, blocked on the WAF-hosted Table of Public Acts
- [ ] District ↔ MLA mapping — **no reachable source**
- [ ] Prior boundaries — **not published in any reachable form**
- [ ] `civic_addresses` probed for a district field — build phase
