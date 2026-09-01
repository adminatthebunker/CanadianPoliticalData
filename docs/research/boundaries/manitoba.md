# Manitoba — Electoral Boundary Research

> Standalone boundary/roster dossier for Manitoba. Cross-cutting context
> (methodology, licence matrix, reconciliation strategy) lives in [`overview.md`](./overview.md).
> The legislative-data dossier for this jurisdiction is at [`../manitoba.md`](../manitoba.md).

**Agency:** Elections Manitoba | **Website:** https://www.electionsmanitoba.ca | **Districts (current):** 57 | **Current order:** 2018 Electoral Divisions Boundaries Commission, enacted into The Electoral Divisions Act, C.C.S.M. c. E40 | **Next redistribution:** commission required at least every 10 years under The Electoral Divisions Act — next report due ~2028

**Status snapshot (2026-08-18):** ✅ **Cleanest provincial jurisdiction researched so far, with one licence caveat.** ✅ The authoritative 57-division boundary set is a direct download from Elections Manitoba (1.7 MiB total, EPSG:26914) — staged. ★ **Manitoba is the control case that validates the shortfall diagnosis**: unlike Saskatchewan, the vintage we hold is *correct* — Open North's `manitoba-electoral-districts-2018` set genuinely is the current 2018 commission — and our 56/57 shortfall is a single incidental gap, not a stale generation. ★ **The one missing division is `The Pas-Kameesak`**, identified by exhaustion. ⚠ The province ships as **two shapefiles** (Rural 25 + Winnipeg 32) that must be unioned; neither is complete alone, and the archive filenames are actively misleading. ⚠ Uppercase `.CPG` and no `AUTHORITY` clause — both known traps, both present. ⛔ **Licence is the blocker**: Elections Manitoba publishes `© 2026. All rights reserved.` and an informational-purposes-only disclaimer, with no reuse grant — corroborating the upstream audit's finding that MB has **no inheritable licence**. ✅ **The 2008 prior generation is now also staged** — recovered via the Wayback CDX technique (brief amendment A5) and confirmed still live at the origin, despite the boundaries commission's own website returning HTTP 500. ✅ Legal in-force date pinned to **2019-08-12** from Manitoba's own consolidated-statute versioning. ★ **The `Area` field question is resolved**: it is a dense 1–57 division number in the 2018 files — Manitoba's stable district key after all — but a genuine area measurement in the 2008 files. Same field name, opposite meaning across generations.

---

## Current boundaries

- **Source URL(s):** https://www.electionsmanitoba.ca/downloads/2018_Final_ED_Manitoba_Public_Urban.zip ; https://www.electionsmanitoba.ca/downloads/2018_Final_ED_Winnipeg_Public_Urban.zip ; https://www.electionsmanitoba.ca/en/resources/maps
- **Format:** ESRI shapefile, zipped. **Two archives, both required** — 1,736,709 and 76,016 bytes.
- **★ The province is split across two files and neither is complete:**

  | Archive | Inner feature class | Records | `Type` |
  |---|---|---:|---|
  | `2018_Final_ED_Manitoba_Public_Urban.zip` | `EDBC2018_FinalBoundaries_Rural` | 25 | `Rural` |
  | `2018_Final_ED_Winnipeg_Public_Urban.zip` | `EDBC2018_FinalBoundaries_Winnipeg` | 32 | `Urban` |
  | | **union** | **57** | — |

  ⚠ **Both outer archives end in `_Public_Urban`, but the first contains the *Rural* feature class.** Go by the inner filename and the `Type` attribute; the archive name is wrong and will mislead anyone who trusts it. A loader that ingests only the file whose name it recognises gets a silently partial province.
- **CRS / projection:** **EPSG:26914** (NAD83 / UTM zone 14N), identical in both files. Verbatim from `EDBC2018_FinalBoundaries_Rural.prj`:
  `PROJCS["NAD_1983_UTM_Zone_14N",GEOGCS["GCS_North_American_1983",DATUM["D_North_American_1983",SPHEROID["GRS_1980",6378137.0,298.257222101]],PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]],PROJECTION["Transverse_Mercator"],PARAMETER["False_Easting",500000.0],PARAMETER["False_Northing",0.0],PARAMETER["Central_Meridian",-99.0],PARAMETER["Scale_Factor",0.9996],PARAMETER["Latitude_Of_Origin",0.0],UNIT["Meter",1.0]]`
  ⚠ **No `AUTHORITY["EPSG","26914"]` clause** (brief amendment A4). Identity is fixed by the parameters — central meridian −99.0 and scale factor 0.9996 are UTM zone 14, NAD83 datum. `.shp` bboxes are `X 311,759..1,109,222 / Y 5,427,444..6,658,760` (Rural) and `X 611,218..646,791 / Y 5,508,304..5,547,427` (Winnipeg) — metres, projected. Build must `ST_Transform(ST_SetSRID(geom, 26914), 4326)`.
  ⚠ **Not the same zone as Saskatchewan.** MB is zone 14 (26914); SK is zone 13 (26913). A shared prairie loader must resolve the EPSG per file, not per region.
- **Attribute schema:** identical in both files. Encoding **UTF-8**, declared in a **`.CPG` with an UPPERCASE extension** — ⚠ exactly the trap in amendment A4; a case-sensitive `*.cpg` glob misses it and mojibakes `Lagimodière`, `La Vérendrye` and every `ED_French` value:

  | Field | dBase type | Length | Dec | Meaning |
  |---|---|---:|---:|---|
  | `OBJECTID` | `N` (numeric) | 10 | 0 | ★ Row ID — unique across the **union** of both files (57 distinct) |
  | `ED` | `C` (character) | 50 | 0 | Electoral division name, English, e.g. `Brandon East` |
  | `ED_French` | `C` (character) | 50 | 0 | ★ French name, e.g. `Brandon-Est` |
  | `Type` | `C` (character) | 50 | 0 | `Rural` or `Urban` — the file's own partition marker |
  | `Area` | `N` (numeric) | 10 | 0 | ★ **Division number, 1–57** — dense, no gaps, uncorrelated with actual area. ⚠ Means something else entirely in the 2008 file |
  | `SHAPE_Leng` | `F` (float) | 19 | 11 | Perimeter, projected units |
  | `SHAPE_Area` | `F` (float) | 19 | 11 | Area, projected units |

  ★ **Bilingual names are published.** Manitoba is the only prairie jurisdiction in this pass shipping an official French district name in the boundary file itself. Worth persisting — it is authoritative and not derivable.
- **District ID field:** ★ **`Area` — resolved 2026-08-18, and it *is* a division number.** ~~There is no published stable district ID.~~ The open question is settled by measurement: `Area` takes the values **1–57 with no gaps and no duplicates**, and its ratio to actual area (`SHAPE_Area/1e6`) ranges from 0.000 to 13.577 — i.e. completely uncorrelated with geography. A dense consecutive integer sequence that ignores area is a district number, not a measurement. `OBJECTID` is also unique across the union but is an ArcGIS row identifier regenerated on export, so it stays untrusted.
  ⚠ **But `Area` means something different in the 2008 file.** There, `Area` sits beside `Area_no_Wa` ("area, no water") and takes values like `460` for St. Paul and `11` for Riel — outside the 1–57 range and plainly a measurement in km². **Elections Manitoba reused one field name for two incompatible meanings across generations.** A loader that reads `Area` as a district number will silently produce garbage on the 2008 file. This is amendment A4's per-file-schema rule in its most dangerous form: not a renamed field, but a *retained* name with changed semantics.
  **Recommendation:** `authority_district_id = Area` (as text) for the 2018 generation, scoped by `boundaries_version`; fall back to the `ED` name for 2008. Our existing kebab-case slug derives from `ED` and remains valid either way, so Manitoba still requires **no suffix re-key**.
- **Effective date:** **2019-08-12.** ★ Pinned from Manitoba's own consolidated-statute versioning rather than inferred: the Manitoba Laws archive serves the version of **The Electoral Divisions Act, C.C.S.M. c. E40** at `https://web2.gov.mb.ca/laws/statutes/archive/e040(2022-02-25)e.php?df=2019-08-12`, whose header states verbatim *"This version was current from August 12, 2019 to February 25, 2022"* — and I verified that this version's Schedule carries the **2018-commission** division names (53 of the 57 matched on a conservative ALL-CAPS heading extraction; the four misses are hyphenation artifacts of my parser, not absences). The immediately preceding archived version runs to 2019-08-11. 2019-08-12 is also the writ-issue date for the 42nd General Election (polling day 2019-09-10), so the statutory and electoral facts agree. Per ruling A2 this legal date is the value to use.
  **Discrepancy to note:** Elections Manitoba's own framing is that the boundaries "went into effect for the 42nd provincial general election, held September 10, 2019" — the *polling day*, 29 days later. The statute version boundary is the better authority and is what I recommend.
- **Superseded date:** n/a (current).
- **District count:** **57**, matching both the 57 seats and s.7(1) of the Act — quoted verbatim: *"The province is hereby divided into 57 electoral divisions."* ✅ Verified on the union: 57 records, 57 distinct `ED`, **no multipart split**.
- **Difficulty (1–5):** **2** — undocumented but structured. Plain HTTPS `GET`, no auth, no WAF, no Cloudflare. Not catalogued in any open-data portal, and the two-file split plus misleading archive names are the only real friction. The *licence*, not the retrieval, is what is blocked.
- **Notes:**
  - ⛔ **Dead end: Data MB** (`geoportal.gov.mb.ca`, an ArcGIS Hub Open Data site) publishes **no** electoral layer. Its dataset search returns `numberMatched: 0` for `electoral` and `electoral division`; the single `constituency` hit and two `riding` hits are false positives (a custom-feed-services layer, provincial forests, crop-reporting regions). This is the probe the brief's order puts first for Manitoba, and it comes up empty — Elections Manitoba's own download is the only source. Recorded so nobody re-probes it.
  - ⛔ **Dead end: `open.canada.ca`** carries no Manitoba provincial electoral dataset; the federated search returns only NRCan federal products.
  - ⚠ The files' `Last-Modified` is `Thu, 25 Mar 2021 04:16:58 GMT` — a 2021 re-upload of 2018-commission data, not a 2021 redistribution. Do not read the timestamp as a vintage.

## Prior boundaries (immediately preceding)

- **Source URL(s):** https://www.electionsmanitoba.ca/downloads/2008_Final_ED_Manitoba_Dec_10_2008_Public_Rural.zip ; https://www.electionsmanitoba.ca/downloads/2008_Final_ED_Manitoba_Dec_10_2008_Public_Urban.zip
  ★ **Recovered via the Wayback CDX technique (brief amendment A5).** ~~None located.~~ Six guessed filenames 404'd on my first pass; the real names embed the commission's report date (`_Dec_10_2008_`), which no guess would have produced. The CDX index over `electionsmanitoba.ca/*` returned 21 archived archives including both halves, and **both are still live at the origin** (HTTP 200; 280,469 and 64,370 bytes) — unlinked, not deleted. Remaining dead ends: the Elections Manitoba maps page (2018 only); the Electoral Division Profiles page (statistical PDFs/Excel only); and **`boundariescommission.mb.ca`, which still returns HTTP 500** over both schemes.
- **Format:** ESRI shapefile, zipped. **Two archives, both required** — same Rural/Urban split as the current generation.
- **CRS / projection:** **EPSG:26914** (NAD83 / UTM zone 14N) — **byte-for-byte the same `PROJCS` string as the current generation**, verified by direct comparison. ✅ No cross-generation reprojection difference. ⚠ Same missing `AUTHORITY` clause.
- **Attribute schema:** ⚠ **No `.cpg` in either archive** — encoding undeclared, unlike the 2018 files' uppercase `.CPG`. I read them as latin-1. Fields (Rural / Urban):

  | Field | dBase type | Length | Meaning |
  |---|---|---:|---|
  | `Id` | `N` | 6 | Row id; `0` on samples — **not** a district key |
  | `ED` | `C` | 30 | Electoral division name — ⚠ 30 chars, vs 50 in the 2018 files |
  | `Type` | `C` | 5 | `Rural` / `Urban` — ⚠ 5 chars, vs 50 in 2018 |
  | `Area` | `N` | 10 | ⚠ **area measurement in km² here**, not a division number — see below |
  | `Area_no_Wa` | `N` | 10 | Area excluding water |
  | `ED_Text` | `C` | 50 | Rural file only; name with punctuation stripped (`StPaul`) |

  ★ **No French names.** `ED_French` is a 2018-generation addition — worth knowing before assuming bilingual coverage is historical.
- **District ID field:** **the `ED` name.** ⚠ **`Area` is NOT a district number in this generation** — it is km² (St. Paul `460`, Riel `11`), the exact opposite of its meaning in the 2018 files. Key the 2008 generation on name only.
- **Effective date:** unknown — `needs confirmation`. The 2008 commission's divisions would have taken effect for the 39th General Election (2011-10-04) under the same mechanism. Manitoba Laws' archive exposes an intermediate version of c. E40 current from **2014-05-01 to 2019-08-11**, which brackets the prior generation's tail but does not by itself establish when the 2008 divisions began. The archive is the right place to settle this — it is browsable by version date — but it was not run to ground in this pass.
- **Superseded date:** **2019-08-12** — the mirror of the current generation's effective date. Well established.
- **District count:** **57** — ✅ verified on the union (26 Rural + 31 Urban = 57 records, 57 distinct `ED`, no multipart). ⚠ Note the split is **26/31**, not the 2018 generation's 25/32 — one division moved between the rural and urban files, so the per-file counts are not stable across generations and must not be hardcoded. Manitoba's seat count has been 57 since well before 2008 (s.7(1) already read 57 in the R.S.M. 1987 consolidation). ★ Like Saskatchewan, **the count did not change across the redistribution**, so counts alone give no signal about vintage.
- ★ **Name churn across the transition:** **41 of 57** division names appear in both generations; **16 were renamed or created** in 2018 and 16 retired. So MB's 2018 commission was comparable in disruption to SK's 2022 one — the difference is entirely that Open North's MB boundary set was refreshed to match and its SK set was not.
- **Difficulty (1–5):** ~~**5** — unavailable.~~ **2** — available, discoverable only through the Wayback CDX index. Retained at the origin, merely unlinked.
- **Notes:**
  - ★ **A5's CDX technique recovered this generation too.** As with SK, my direct probing concluded "not published" when the truth was "not linked" — and here the real filenames embed the commission's report date (`Dec_10_2008`), which no filename guess would ever have produced. **Two for two: CDX-before-concluding-absent should be the default, not the fallback.**
  - ⚠ Manitoba's prior generation is **less urgent than Saskatchewan's** for exactly the reason that makes MB the control case: the vintage we hold is already current, so no stale rows need superseding. It is historical completeness, not a correctness fix — but it is now free.
  - ★ **The 2008 file is also the natural regression fixture** for the geometry test applied to SK: if a future audit wants to confirm MB's 56 rows really are 2018 shapes (rather than assuming it from the `source_set` label), this is the comparison generation. **UNTESTED — worth 10 minutes during build**; MB's vintage is asserted from the `source_set` name and the name-match, not yet from geometry.

## District ↔ elected official mapping

- **Source URL(s):** https://www.gov.mb.ca/legislature/members/mla_list_constituency.html ; https://www.gov.mb.ca/legislature/members/mla_list_alphabetical.html ; https://www.electionsmanitoba.ca/en/Voting/MLA
- **Format:** server-rendered HTML (27,850 bytes for the constituency listing). No auth, no rate limiting, no WAF.
- **★ Join quality — measured:** the Legislative Assembly's constituency listing contains **57 of the 57** authoritative `ED` values verbatim after punctuation/accent normalisation. **57/57, zero unmatched.** Elections Manitoba and the Legislative Assembly agree on division naming exactly — including the accented `Lagimodière` and `La Vérendrye`.
- ★ **The constituency listing is ordered by division, not by member** — which is the ideal shape for this join and rarer than it sounds. A companion PDF at `https://www.gov.mb.ca/legislature/members/pf/electoral_pf.pdf` carries the same division→member mapping with party affiliation.
- ⚠ **No stable per-MLA identifier is published** on the listing pages. Same limitation as Saskatchewan; the join is division-name-based.
- **Difficulty (1–5):** **3** — predictable HTML scrape; no JSON surface found.

## Postal-code correspondence (if published)

⛔ **None published by Elections Manitoba.** Per brief amendment A3 this was time-boxed: the agency offers an interactive *Who is my MLA?* / *What Is My Electoral Division?* lookup and no bulk postal file. No open-licence concordance exists for Manitoba. **Not needed** — our lookup is point-in-polygon and the staged 57-division set is a strictly better input.

## Terms / Licensing

⛔ **No open licence. This is the blocker for Manitoba.**

Elections Manitoba's site footer reads, verbatim:

> "© 2026. All rights reserved."

and the maps page from which the shapefiles are downloaded carries, verbatim:

> "Maps are provided for informational purposes only"

> "not guaranteed to be without error"

with the further note that voting-area maps relate to their specific election dates and *"cannot be used
for comparative purposes with other elections."* There is **no** grant of permission to use, copy,
modify, publish or distribute, and no named licence anywhere on the site.

**What this is and is not.** It is **not** a click-through gate: no agreement was presented, no checkbox
existed, no account was required, and nothing was accepted or submitted (standing instruction 3 was not
engaged). The files are freely downloadable over plain HTTPS. `"All rights reserved"` is, however, a
notably more assertive posture than Saskatchewan's bare copyright line — it is an affirmative reservation
rather than silence.

**Assessment.** ✅ This **confirms X2's upstream audit** from the operator's brief: `represent-canada-data`
holds only a 2008 Manitoba directory and nothing current, so there is no licence to inherit — and now we
know there is none to inherit *because the agency never granted one*, not because the mirror was
incomplete. Manitoba sits in the overview's "no licence provenance" group (with ON and PE) and, on this
evidence, should be reclassified from *provenance unknown* to **provenance established: no licence
granted**.

Internal research use is defensible. **Redistribution through `/api/public/v1/boundaries/*` is not
cleared.** Saskatchewan is in the same position; one operator decision can cover both. See
Research-handoff items.

## Rate limits / auth

- **Authentication:** none on any surface. No API key, no account, no session, no referer check.
- **Rate limiting:** none observed. Roughly 20 requests across `electionsmanitoba.ca`, `gov.mb.ca`, `geoportal.gov.mb.ca` and `web2.gov.mb.ca` — zero 429s, zero throttling, zero challenge pages.
- **No WAF.** ✅ Unlike Saskatchewan, `electionsmanitoba.ca` served every request without a `User-Agent` header and answered `WebFetch` directly. No Cloudflare, no UA filtering.
- **Caching:** the `/downloads/` host returns accurate `Content-Length` and `Last-Modified` and honours `HEAD`. ✅ Refresh check is a cheap conditional `HEAD` per CLAUDE.md convention #6.
- ⚠ **`boundariescommission.mb.ca` returns HTTP 500** over both schemes — not a rate limit, an outage or a decommission. It is the site Elections Manitoba directs boundary-data enquiries to.
- **Instruction-source boundary:** no page fetched contained text addressed to an AI agent. Nothing to report under standing instruction 8.

## Staged files

Staging root `data/boundaries/manitoba/`; sha256 audit table in [`PROVENANCE.md`](../../../data/boundaries/manitoba/PROVENANCE.md). **2.1 MiB of a 500 MB budget.**

| Path | Bytes | Records | Role |
|---|---:|---:|---|
| `current/2018_Final_ED_Manitoba_Public_Urban.zip` | 1,736,709 | 25 (`Rural`) | ★ current generation, part 1 of 2 |
| `current/2018_Final_ED_Winnipeg_Public_Urban.zip` | 76,016 | 32 (`Urban`) | ★ current generation, part 2 of 2 |
| `prior/2008_Final_ED_Manitoba_Dec_10_2008_Public_Rural.zip` | 280,469 | 26 (`Rural`) | ★ prior generation, part 1 of 2 — recovered via CDX |
| `prior/2008_Final_ED_Manitoba_Dec_10_2008_Public_Urban.zip` | 64,370 | 31 (`Urban`) | ★ prior generation, part 2 of 2 — recovered via CDX |

Not staged: `VA_MB2023_public.zip` (4,092,141 bytes) and `VA_MB2019_public.zip` — general-election *voting areas*, sub-division geography, out of scope for `constituency_boundaries`. Also skipped: the per-byelection `VA_*_public.zip` files for 2022–2026.

## Reconciliation with `constituency_boundaries`

**What we hold** (read-only query, 2026-08-18):

- `source_set = 'manitoba-electoral-districts-2018'` — **56 rows**, `level = 'provincial'`, `province_territory = 'MB'`, 56 distinct `constituency_id`.
- `constituency_id` prefix `manitoba-electoral-districts-2018/`, slug = kebab-case division name (`.../agassiz`, `.../fort-rouge`). No numeric key.
- `effective_from = '2023-01-01'`, `effective_to = NULL` on all 56 — the hardcoded literals from `services/scanner/src/opennorth.py`, not a legal date.
- Also present under `province_territory = 'MB'` but out of scope: `winnipeg-wards` (15), municipal.

**★ The vintage we hold is CORRECT.** Comparing our 56 slugs against the 57 authoritative `ED` values:

| Check | Result |
|---|---:|
| Authoritative divisions (2018 commission) | 57 |
| Our rows | 56 |
| Ours that name-match an authoritative division | **56 / 56 (100%)** |
| Ours with no authoritative counterpart | **0** |
| Authoritative divisions we hold no polygon for | **1** |

★ **The one missing division is `The Pas-Kameesak`**, established by exhaustion rather than assertion:
all 57 authoritative names were matched against every named active MB provincial politician; exactly one
division (`The Pas-Kameesak`) has no named representative, exactly one representative
(**Jelynn Dela Cruz**) carries a blank `constituency_name`, and there are **zero** unmatched
representative names on either side. The correspondence is forced.

⚠ **This is a fundamentally milder problem than Saskatchewan's.** Manitoba's `source_set` says 2018 and
Manitoba's current order *is* the 2018 commission — so unlike SK, the 56 polygons we hold are the right
generation with the right geometry. MB needs **one INSERT**, not a generational replacement. It is the
control case that proves the shortfall diagnosis is about vintage rather than about ingest mechanics.

**Why the one row is missing.** Per the diagnosis reproduced below, boundary rows are fetched only for
representatives carrying a `related.boundary_url`, and MB has exactly **one** active representative
without one — the same member whose `constituency_name` is blank upstream. With no district name there
is nothing for Open North to match a boundary against. Note that `The Pas-Kameesak` held a **byelection
in 2026** (Elections Manitoba publishes its voting-area file), so this is most likely an incompletely
populated upstream record for a recently elected member rather than a systemic omission.

**Re-key assessment. No suffix re-key required.** Our kebab-case slug derives from the `ED` name, which
remains valid as a key in both generations. Under the overview's recommendation (d):
`authority = 'elections-manitoba'`, and `authority_district_id = Area` for the 2018 generation now that
`Area` is confirmed to be the division number (falling back to `ED` for 2008, where `Area` means
something else entirely).

**★ A6 prefix change required.** ~~The `source_set` stays `manitoba-electoral-districts-2018`.~~
⛔ **Superseded by ruling A6** — that prefix encodes a generation and must become
`manitoba-electoral-districts`:

| Table | Rows carrying the old prefix | Change |
|---|---:|---|
| `politicians` | **56** (all active) | `replace(constituency_id, 'manitoba-electoral-districts-2018/', 'manitoba-electoral-districts/')` |
| `politician_terms` | **56** | same `replace()` |
| `constituency_boundaries` | **56** | same `replace()`, plus `boundaries_version = '2018-commission'` |

**Total MB prefix cost: 168 mechanical row-updates**, plus the one `The Pas-Kameesak` INSERT and the
`authority` backfill. ★ Still the cheapest cutover of any province examined — and unlike Saskatchewan,
**no geometry needs replacing**, because the vintage we hold is already current.

⚠ **`province_territory` is already correct** (`'MB'` on all 56). No backfill needed.

★ **`ED_French` should be captured on load.** It is authoritative, published, and not derivable — and
`constituency_boundaries` has no French-name column today. Worth raising before the build hardcodes
English-only.

**Proposed temporal values:**

Both generations share the prefix `manitoba-electoral-districts/` per ruling A6.

| Generation | `constituency_id` | `boundaries_version` | `effective_from` | `effective_to` | Rows |
|---|---|---|---|---|---|
| 2018 Electoral Divisions Boundaries Commission | `manitoba-electoral-districts/<kebab-name>` | `2018-commission` | `2019-08-12` | `NULL` | 57 |
| 2008 Electoral Divisions Boundaries Commission | `manitoba-electoral-districts/<kebab-name>` | `2008-commission` | unknown `needs confirmation` | `2019-08-12` | ✅ **57 available** (0 currently held) |

---

### ★★ Why we hold 56 of 57 — the shortfall diagnosis

**This section is cross-jurisdictional and is reproduced from
[`saskatchewan.md`](./saskatchewan.md), where it was investigated in full.** It is repeated here because
Manitoba is the *control case* and the contrast is the point. Consolidation into
[`overview.md`](./overview.md) is the coordinator's call.

**Both standing hypotheses are wrong.**

⛔ **Pagination/truncation — ruled out.** `ingest_manitoba_mlas(limit=200)` runs against 57 seats, and
`_fetch_reps` (`services/scanner/src/opennorth.py:219`) pages via `meta.next` until exhausted. The cap
cannot bind. No alphabetical or page-boundary clustering exists in either province.

⛔ **Incomplete roster — ruled out.** Manitoba has **57 active provincial politicians against 57 seats**;
Saskatchewan has **61 against 61**. Neither roster is missing anybody.

**★ The actual mechanism: a missing `related.boundary_url` on the representative record.** `_ingest_set`
(line 568) fetches a polygon only as a side effect of iterating representatives, and only when
`_constituency_id()` (line 246) returns non-null — which requires `related.boundary_url` to be present.
When it is absent the boundary fetch is skipped silently. **Polygons held == distinct non-null
`boundary_url` across active representatives**, verified to hold exactly in 11 of 13 provincial and
territorial sets (the two `+1` exceptions, ON and SK, are polygons retained after their representative
went inactive — boundary rows are never retired with their rep).

**★ And the usual reason `boundary_url` is missing is a vintage mismatch between Open North's roster and
Open North's boundary set** — the roster moves to a new redistribution, the boundary set does not, and
renamed or newly created districts have nothing to name-match against. Saskatchewan is the worked
example: 15 of its 16 unlinked representatives sit for districts created or renamed by the 2022
commission, which cannot exist in Open North's 2012 boundary set.

**Manitoba is the control that isolates the variable.** MB's boundary set *is* the current vintage, and
MB's shortfall is correspondingly a single row caused by a blank `constituency_name` upstream — an
incidental data gap, not a generational failure. The same one-line diagnostic separates the two cases
everywhere:

> Count active representatives with no `boundary_url`. Then check whether their district names exist in
> the boundary set you hold. **Present → upstream linkage miss, backfill the row** (MB, and SK's
> `Humboldt-Watrous`). **Absent → vintage mismatch, replace the generation** (SK's other 15).

**Correcting the record on Nunavut.** Nunavut has **22 active representatives and 22 distinct district
names** — a complete roster — with all 22 lacking `boundary_url`. The overview's attribution of NU's zero
rows to roster incompleteness is therefore **wrong**: Open North simply publishes no Nunavut boundary set
for any representative to link to. Same mechanism, most extreme case.

**What this changes for the build.** Counting rows against seats understates the damage, because a
province whose seat count survived redistribution unchanged — **both** SK (61→61) and MB (57→57) — gives
no arithmetic warning. And a province at full count is not necessarily correct: AB (87/87), NS (55/55)
and PE (26/26) prove only that every representative linked to *something*, not that the boundary set is
the current vintage. Each still needs a vintage check against its agency's current order.

## Research-handoff items

- **⛔ Manitoba has no open licence — this blocks redistribution and needs an operator decision.** Elections Manitoba publishes `© 2026. All rights reserved.` plus an informational-purposes-only disclaimer, with no reuse grant. Nothing was accepted or submitted. **This is the same decision Saskatchewan needs, and the two should be decided together**; my recommendation for both is internal use only, keep them out of `/api/public/v1/boundaries/*`, and pursue written permission in parallel. Manitoba's `"All rights reserved"` is a more assertive posture than Saskatchewan's silence, so if only one is pursued by email, pursue Manitoba.
- **⚠ Should the missing `The Pas-Kameesak` row be fixed now, independently of the boundary rebuild?** It is one INSERT into an already-correct-vintage set, and it closes a real gap — a Manitoban in that division currently gets "no representatives found." The rebuild will supersede it anyway, but the rebuild is gated on the licence decision above and this is not. **Recommendation: yes, do it as a standalone fix** — it is the cheapest correctness win available in this workstream, and it is licence-independent only if we take the view that a single polygon loaded for internal lookup is internal use. Flagging that caveat rather than deciding it.
- ~~**What is the `Area` field?**~~ ✅ **RESOLVED 2026-08-18 by measurement, no email needed.** In the 2018 files `Area` is a dense 1–57 integer with no gaps or duplicates and zero correlation to actual area (ratio to km² spans 0.000–13.577), so it is Manitoba's division number and should be `authority_district_id`. ⚠ **But in the 2008 files the same field name holds an area measurement in km²** (St. Paul `460`, Riel `11`), sitting beside `Area_no_Wa`. **Flagging this to the coordinator as a cross-jurisdictional trap**: a retained field name with changed semantics is more dangerous than a renamed field, because schema-diff tooling and human review both miss it.
- **★ Should `constituency_boundaries` gain a French-name column?** Manitoba publishes an official `ED_French` for every division and we currently have nowhere to put it. This is not MB-specific — Quebec and New Brunswick will have the same need, and the federal Elections Canada files ship `ED_NAMEF` which the federal agent also flagged as unused. **This is a schema question that spans four jurisdictions and should be settled once, before the first loader is written.**
- ~~**⛔ The 2008 boundaries are not published.**~~ ✅ **RESOLVED 2026-08-18** via the Wayback CDX technique (A5) — both halves staged, both still live at the origin. `boundariescommission.mb.ca` is still returning HTTP 500, but it turned out not to be needed. **Worth telling the other agents: the commission site being down did not mean the data was gone.**
- **Confirm the 2019-08-12 in-force date is the reading we want.** I pinned it to Manitoba's consolidated-statute versioning (*"current from August 12, 2019"*), which is also the 42nd GE writ-issue date. Elections Manitoba instead describes the boundaries as taking effect for the election "held September 10, 2019" — the polling day, 29 days later. Ruling A2 favours the legal date and the statute version boundary is the strongest legal evidence available, so I used it, but a one-line confirmation would close it.

## Status

> ⚠ **Reconciled 2026-09-01.** The checkboxes below are the **research phase's** record
> (closed 2026-08-18) and several were overtaken by the build — migrations `0064`–`0121`,
> merged to `main` 2026-08-28. An unticked box here is **not** evidence that something is
> still outstanding.
>
> **Live counts: [`PROGRESS.md`](./PROGRESS.md)** (generated by `boundary-progress`).
> **What actually landed:** the migration headers, which are the accurate record.
> This file's job is the *reasoning* — sources, licences, traps, vintage evidence.

- [x] Current boundaries located and staged (2026-08-18) — 57/57 divisions across two files
- [x] Two-file split identified and union verified — 25 Rural + 32 Urban = 57, no overlap, no multipart
- [x] CRS confirmed — EPSG:26914, verbatim WKT recorded, ⚠ no `AUTHORITY` clause
- [x] Attribute schema parsed from the `.dbf` header — ⚠ uppercase `.CPG` trap present and handled
- [x] Legal effective date established — 2019-08-12, cited to Manitoba Laws statute versioning, per ruling A2
- [x] District ↔ elected official source located and join quality measured — 57/57
- [x] Postal-code correspondence checked — none published, not needed
- [x] ★★ Shortfall cause diagnosed — vintage is **correct**; single incidental gap
- [x] Missing division identified — **`The Pas-Kameesak`**, by exhaustion
- [x] Reconciliation confirmed — **no suffix re-key**, 56 backfill + 1 insert
- [x] Prior boundaries located and staged (2026-08-18) — 57/57 across two files, recovered via Wayback CDX per A5
- [x] A6 generation-free prefix specified — `manitoba-electoral-districts`; 168 mechanical row-updates
- [x] ★ `Area` field semantics resolved — division number 1–57 in 2018, **area measurement in 2008**; same name, opposite meaning
- [ ] Prior-generation `effective_from` established — `needs confirmation`
- [ ] MB geometry vintage confirmed by measurement — **UNTESTED**; asserted from `source_set` + name-match, and the 2008 file is now staged as the comparison fixture
- [ ] Licence cleared for internal use — **blocked: no licence published, operator decision needed**
- [ ] Licence cleared for redistribution — **blocked: "All rights reserved", do not serve publicly**
