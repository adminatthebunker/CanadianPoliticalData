# Newfoundland and Labrador — Electoral Boundary Research

> Standalone boundary/roster dossier for Newfoundland and Labrador. Cross-cutting context
> (methodology, licence matrix, reconciliation strategy) lives in [`overview.md`](./overview.md).
> The legislative-data dossier for this jurisdiction is at [`../newfoundland-labrador.md`](../newfoundland-labrador.md).

**Agency:** Elections NL | **Website:** https://www.elections.gov.nl.ca | **Districts (current):** 40 | **Current order:** 2015 Electoral Districts Boundaries Commission (*Electoral Boundaries Act*, RSNL1990 c. E-4, s. 13(1)) | **Next redistribution:** ⚠ **due this calendar year** — s. 13(2) requires a commission "in the calendar year beginning in 2026"

**Status snapshot (2026-08-18):** ✅ **Both generations located and staged**, but NL is a markedly messier jurisdiction than BC and the headline number in the brief needs restating. ★ **We hold 36 of 40 districts and the shortfall is exactly 4** — `Burgeo - La Poile`, `Humber - Gros Morne`, `Labrador West`, `St. John's East - Quidi Vidi`. ★ **The mechanism is *not* BC's.** Open North's NL roster is itself short — **36 members for a 40-seat House** — so those 4 districts never had a representative to hang a boundary off. Same root trap (boundaries are a side effect of roster ingestion) but the opposite proximate cause: BC's roster was complete and the boundary URLs were missing; NL's roster is simply incomplete. ⚠ **The brief's "8 districts with zero matching officials" does not reproduce** — every one of our 36 boundaries has exactly one active official and there are **zero orphans**. The real 8 is on the *politician* side: 8 duplicate `direct:assembly-nl-ca` rows carrying a `NULL constituency_id`. ⛔ **Three genuine traps:** the authoritative geometry file's **only attribute is `DIST_NAME`** — no district ID of any kind; it carries an **upstream typo in that only key field** (`Cartwright - L'Anse aux Clair`, should be *au* Clair); and its `.prj` is a **custom non-EPSG projection** (`SESA-TM`). ★ Prior 48-district generation recovered via the A5 Wayback CDX technique after all origin URLs 404'd. ✅ Licence is clean and open (OGL–NL v1.0). ✅ **A6: NL is the one jurisdiction whose prefix is already correct** — `newfoundland-and-labrador-electoral-districts` encodes no generation, so no prefix change is needed.

---

## Current boundaries

- **Source URL(s):** https://opendata.gov.nl.ca/public/opendata/page/?page-id=datasetdetails&id=361 ; https://opendata.gov.nl.ca/public/opendata/filedownload/?file-id=3323 ; discovery via https://www.elections.gov.nl.ca/resources/gis/
- **Format:** Shapefile, zipped (`NL_EB_Poly_50k.zip`, 15.5 MiB → `NL_EB_Poly_50k_Upload.{shp,shx,dbf,prj,sbn,sbx,cpg,shp.xml}`). No GeoJSON offered anywhere. The `_50k` in the filename is the source mapping scale (1:50,000), not a generalisation for display.
- **CRS / projection:** ⛔ **Custom, non-standard, and this is a build blocker if unhandled.** Verbatim `.prj` WKT:
  ```
  PROJCS["SESA-TM",GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",SPHEROID["WGS_1984",
  6378137.0,298.257223563]],PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]],
  PROJECTION["Transverse_Mercator"],PARAMETER["False_Easting",1000000.0],
  PARAMETER["False_Northing",0.0],PARAMETER["Central_Meridian",-59.5],
  PARAMETER["Scale_Factor",0.998],PARAMETER["Latitude_Of_Origin",0.0],UNIT["Meter",1.0]]
  ```
  No `AUTHORITY` clause, and — unlike BC's BC Albers — **the parameters do not correspond to any standard EPSG code I can identify.** A Transverse Mercator on the **WGS84** datum with central meridian **−59.5°**, scale factor **0.998**, and false easting **1,000,000 m** is not UTM (UTM uses 0.9996 and 500,000) and not NL's MTM zones. `SESA-TM` appears to be a provincial in-house projection. **`needs confirmation` — whether an official EPSG code exists for it.**
  - **Build recommendation:** do not guess an EPSG. Register the projection explicitly in `spatial_ref_sys` under a private SRID (the 900000+ range is conventional for user definitions) with the proj4 string derived from those parameters:
    ```
    +proj=tmerc +lat_0=0 +lon_0=-59.5 +k=0.998 +x_0=1000000 +y_0=0 +datum=WGS84 +units=m +no_defs
    ```
    then `ST_Transform(ST_SetSRID(geom, <that srid>), 4326)`. ⚠ **This is exactly the case where the Fort Erie bug recurs** — an unrecognised `.prj` invites someone to `ST_SetSRID(…, 4326)` and store metres as degrees. The `boundary_in_wgs84_bounds` CHECK would reject the rows, and per the loader trap that rejection is currently *swallowed*, so NL would silently end up with zero boundaries.
  - ⚠ Note the datum is **WGS84**, not NAD83 — different from the prior generation (below) and from every other jurisdiction in this workstream so far.
- **Attribute schema:** ⛔ **A single field.** dBase III (`0x03`), 40 records, 289-byte header, 51-byte records:

  | Field | Type | Length |
  |---|---|---:|
  | `DIST_NAME` | C | 50 |

  That is the entire schema. **There is no district ID, no code, no population, no area, no gazette date — nothing but the name.**
- **District ID field:** ⛔ **None exists.** `DIST_NAME` is the only candidate key, and it is a free-text name. This is the weakest key situation of any jurisdiction examined so far — BC hands us `ELECTORAL_DISTRICT_ID`, Regina hands us a ward number, NL hands us nothing. Consequences:
  - `authority_district_id` under [`overview.md`](./overview.md) recommendation (d) would have to be the **name itself** (or a slug of it), which is not a stable identifier in the sense the column intends.
  - The name is unique (40 records, **40 distinct `DIST_NAME`** — verified), so it *works* as a key; it is simply fragile against renames and typos. And there is already a typo — see below.
  - ★ The prior generation's file is **richer** than the current one (it has `OBJECTID`, `PARTY`, `MEMBER`, `POPULATION`), so this is a regression in the agency's own publishing, not a permanent constraint.
- **⚠★ TRAP — the authoritative file has a typo in its only key field.** The shapefile spells district 7 **`Cartwright - L'Anse aux Clair`**. The correct name is **`Cartwright - L'Anse au Clair`** ("aux Clair" is not grammatical French and does not match the place name). Three independent confirmations:
  1. Elections NL's own poll-map PDF for the district is served at `.../pollmaps/Cartwright%20-%20L'Anse%20au%20Clair.pdf` — **the same agency spells it "au Clair" everywhere except inside this shapefile.**
  2. The **prior-generation file** (2011, also Elections NL) spells it `Cartwright-L'Anse au Clair` — correct. So this is a **regression introduced in the 2015 file**, not a historical convention.
  3. Our own DB, sourced from Open North, holds `Cartwright—L'Anse au Clair` — correct.

  Because `DIST_NAME` is the *only* field, a name typo is a **total key failure for that district** — there is no ID to fall back on. Any name-based join must special-case it. **Do not "fix" it by editing the staged file** (staging is immutable); handle it as a normalisation rule in the loader and record the rule.
- **⚠ Name separator differs from what we store.** The authoritative file uses a **spaced hyphen** (`Baie Verte - Green Bay`); our rows use an **em dash with no spaces** (`Baie Verte—Green Bay`). Every multi-part NL district name is affected. Normalisation must fold `—`/`–`/`-` and collapse surrounding whitespace before comparing — with that fold, 35 of our 36 names match the authoritative file exactly (the 36th being the Cartwright typo above).
- **Effective date:** `needs confirmation`. The 40-district set was first used at the **2015 general election (2015-11-30)**, and the commission reported 2015-06-08. But the *Electoral Boundaries Act* is unusually quiet on commencement: **s. 14(2)** requires the minister to submit the report to the Lieutenant-Governor in Council and lay it before the House within 10 days, and **no section specifies a proclamation, order-in-council, or automatic in-force mechanism** — unlike BC's `Electoral Districts Act` s. 6, which names the triggering event outright. Per the A2 ruling I am recording both candidates and marking the legal one unresolved:
  - **Legal in-force date: `needs confirmation`** — not establishable from the Act alone. The implementing instrument is likely a proclamation or an amendment to the *House of Assembly Act* district schedule; that instrument was not located in this pass.
  - **Dataset metadata date: 2015-09-10** (portal "modified"; published 2015-06-12).
  - **Practical first-use date: 2015-11-30** (the general election).
  - **Recommendation:** use **2015-11-30** as `effective_from` with an explicit `needs confirmation` marker, since it is the first date on which the boundaries actually determined anyone's representation — which is the question the column exists to answer. Do not use the metadata date; it precedes first use by three months.
- **District count:** **40** records, **40 distinct `DIST_NAME`** — ✅ matches the 40-seat House of Assembly and s. 13(1) of the Act ("the commission shall divide the province into 40 proposed one-member districts").
  - ★ **A4 distinct-ID check passed**, and it mattered here: NL is heavily islanded, but the file is **one record per district**, not one per polygon fragment. No duplicate-key risk on load.
  - ⚠ **Beware a tempting false pattern:** Elections NL states the province has "36 electoral districts on the island and 4 in Labrador". We hold 36. **These are unrelated.** We hold 3 of the 4 Labrador districts (Torngat Mountains, Lake Melville, Cartwright—L'Anse au Clair) and are missing one Labrador district (Labrador West) plus three island districts. The 36/36 coincidence is pure numerology — worth stating so nobody "explains" our gap with it.
- **Difficulty (1–5):** **2** — the data is open, free, unauthenticated and directly downloadable, but it is shapefile-only, has a one-field schema with no ID, carries a typo in that field, uses a non-standard projection, and has no documented legal in-force date. Everything is *obtainable*; nothing is *tidy*.
- **Notes:** ⚠ The portal describes the dataset as "the final version of the **proposed** electoral boundaries" — it is the commission's product, and the agency has published **no separate post-enactment file**. The district count and names match the enacted House, so it is almost certainly identical to what was adopted, but "proposed" is the agency's own word and that gap should be closed before it becomes our authoritative geometry. See `## Research-handoff items`.

## Prior boundaries (immediately preceding)

- **Source URL(s):** ⚠ **archive only** — https://web.archive.org/web/20250802080819id_/https://www.elections.gov.nl.ca/elections/resources/shapedata/Distribution_2011.zip . Origin URLs, **all HTTP 404** as of 2026-08-18: https://www.elections.gov.nl.ca/elections/resources/shapedata/Distribution_2011.zip ; https://www.elections.gov.nl.ca/elections/ElectoralBoundaries/Distibution_2011.zip ; https://www.elections.gov.nl.ca/elections/ElectoralBoundaries/Shapefile.zip
- **★ Found with the A5 Wayback CDX technique**, which is the only reason this generation exists in our staging at all. The CDX sweep over `elections.gov.nl.ca/*` for `.zip|.shp|.geojson|.kmz` surfaced seven archived spatial artifacts; `Distribution_2011.zip` was the only prior-generation district file among them. Wayback holds genuine `200` captures from 2017 through **2025-08-02** at a stable ~11,375,70x bytes. Note the older path carries an **upstream spelling error** (`Distibution_2011.zip`) — a CDX sweep catches that where a guessed URL never would. The other archived artifacts, recorded so nobody re-probes: `Basic_Polls_Shapefile 2015.zip`, `Basic_Polls_Shapefile 2019.zip` (polling divisions, finer than districts), `Island_2015.zip` + `Labrador_2015.zip` (the current generation split in two), `2015GEResults.zip` (election results, not geometry).
- **Format:** Shapefile, zipped (11.0 MiB → `Provincial_Districts.{shp,shx,dbf,prj,sbn,sbx,shp.xml}`). ⚠ No `.cpg` in any case — encoding undeclared; all 48 names are pure ASCII, so nothing mojibakes.
- **CRS / projection:** **EPSG:2961** — `NAD83(CSRS) / UTM zone 21N`. Verbatim `.prj`:
  ```
  PROJCS["NAD83_Zone_21N",GEOGCS["GCS_North_American_1983_CSRS",
  DATUM["D_North_American_1983_CSRS",SPHEROID["GRS_1980",6378137.0,298.257222101]],
  PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]],
  PROJECTION["Transverse_Mercator"],PARAMETER["False_Easting",500000.0],
  PARAMETER["False_Northing",0.0],PARAMETER["Central_Meridian",-57.0],
  PARAMETER["Scale_Factor",0.9996],PARAMETER["Latitude_Of_Origin",0.0],UNIT["Meter",1.0]]
  ```
  Derived by hand (no `AUTHORITY` clause): FE 500,000 + SF 0.9996 + CM −57° = **UTM zone 21N**; the datum string is `..._CSRS`, so this is **EPSG:2961 (NAD83(CSRS) / UTM 21N)**, *not* EPSG:26921 (plain NAD83 / UTM 21N). Same class of distinction as BC's 3005-vs-3153 — the projection parameters are identical between the two codes and only the datum separates them.
  - ⚠★ **The two NL generations use entirely different, mutually incompatible CRSs** — a custom WGS84 Transverse Mercator for 2015 versus NAD83(CSRS) UTM 21N for 2011. A loader that hardcodes one SRID for "NL" will silently corrupt the other generation. **SRID must be per-file, never per-jurisdiction.**
- **Attribute schema:** dBase, 48 records — and **richer than the current generation**: `OBJECTID` (N,10), `ELEC_DISTR` (C, district name), `PARTY` (C), `MEMBER` (C), `FCODE` (C), `POPULATION` (N).
- **District ID field:** `OBJECTID` (1–48). ⚠ `OBJECTID` is an ArcGIS row identifier, not a published district code — treat it as file-scoped, not as an authority key. `ELEC_DISTR` is the practical key, 48 records / **48 distinct** names.
  - ★ **Bonus: this file carries the sitting member and party per district** (`MEMBER`, `PARTY` — e.g. `Labrador West / PC / Nick McGrath`). That is a free historical district↔official mapping for the 48-seat era, useful to [`../newfoundland-labrador.md`](../newfoundland-labrador.md), which records that NL Hansard carries no inline riding.
- **Effective date:** `needs confirmation` — the 48-district distribution predates the 2015 commission and was used through the 2011 and 2014 general elections. Not established in this pass.
- **Superseded date:** **2015-11-30** (`needs confirmation`, same reasoning as the current generation's `effective_from`) — the two generations abut at the 2015 general election.
- **District count:** **48** records / 48 distinct names — ✅ matches the pre-2015 48-seat House and the "48 to 40" reduction the commission implemented.
- **Difficulty (1–5):** **4** — the data itself is clean and easy to parse, but it is **gone from the agency's website** and recoverable only from the Internet Archive, which is a materially weaker provenance position and needs an operator decision before it becomes load-bearing.
- **Notes:** The spelling `Cartwright-L'Anse au Clair` here is **correct**, which is what establishes the 2015 file's `aux Clair` as a regression rather than a house style.

## District ↔ elected official mapping

- **Roster source:** the House of Assembly member list at https://www.assembly.nl.ca/members/members.aspx — already ingested by our own scraper under `source_id` prefix `direct:assembly-nl-ca:<lastnamefirstname>`, and the only source that covers all 40 seats.
- **Current state is messy and is the real story behind the brief's "8".** Measured 2026-08-18 on active NL provincial politicians:

  | Measure | Count |
  |---|---:|
  | Active NL provincial politician rows | **48** |
  | …sourced `opennorth:newfoundland-labrador-legislature` | **36** (all carry a `constituency_id`; all 36 resolve to a boundary) |
  | …sourced `direct:assembly-nl-ca` | **12** (all carry `constituency_name`; **none** carries a `constituency_id`) |
  | Boundaries with zero active officials | **0** |
  | Politicians with a `constituency_id` matching no boundary (orphans) | **0** |

  48 active rows against a 40-seat House means **8 rows are duplicates**: of the 12 `direct:` rows, **8 name a district that already has an Open North row with a boundary** (Carbonear—Trinity—Bay de Verde, Corner Brook, Gander, Lake Melville, Lewisporte—Twillingate, St. Barbe—L'Anse aux Meadows, St. George's—Humber, St. John's West) and **4 name the districts we hold no boundary for** (Burgeo - La Poile, Humber - Gros Morne, Labrador West, St. John's East - Quidi Vidi). 36 + 4 = 40. ✅
  - **So the brief's "8 zero-match" is real but inverted:** it is 8 *officials* unreachable from the boundary side, not 8 *boundaries* with no official. Every boundary we hold has exactly one official. The 8 are duplicate rows that the boundary-bearing Open North rows already cover, which means **fixing them is a deduplication job, not a boundary job** — and it will not change coverage. The 4 genuinely-uncovered districts are the real gap.
  - ⚠ This is the duplicate-politician pattern already tracked in `scripts/audit_politician_duplicates.py`; NL should be run through that detector. **Do not merge blindly** — the Cooke rule (never merge both-native-id pairs) applies, though here only one side of each pair has an ID at all, which is the easy case.
- **Difficulty:** the roster side is workable, but ⚠ NL offers **no stable per-MLA identifier** — there is no `nl_assembly_id` equivalent, and per CLAUDE.md convention #1 one should be minted (`nl_assembly_slug`, following the existing `direct:assembly-nl-ca:<slug>` shape) before this is built on.

## Postal-code correspondence (if published)

⛔ **None published.** Per the A3 ruling this got a few minutes only: Elections NL's GIS page offers district and polling-division shapefiles and nothing postal; the NL open data portal's spatial catalogue has no postal product; there is no NL analogue to the Elections Québec concordance or the BC LIMS `allPostalCodeLookups` table. Point-in-polygon is the only route for NL, which makes closing the 4-district gap the whole job.

## Terms / Licensing

**Licence:** **Open Government Licence – Newfoundland and Labrador, version 1.0** — https://opendata.gov.nl.ca/public/opendata/page/?page-id=licence (declared on dataset 361 as "Open Government Licence").

This is the Canadian OGL family text, and it is Class A / transferable in [`overview.md`](./overview.md)'s taxonomy. The clauses that govern us, verbatim:

> The Information Provider grants You a worldwide, royalty-free, perpetual, non-exclusive licence to use the Information, including for commercial purposes.

> You are free to copy, modify, publish, translate, adapt, distribute or otherwise use the Information in any medium, mode or format for any lawful purpose.

**Redistribution: ✅ permitted** — "publish" and "distribute" named explicitly, no viral flow-down, nothing to attach to API responses. This clears `/api/public/v1/boundaries/*`.

**Attribution: ✅ required.** The licence's default statement, verbatim:

> Contains information licensed under the Open Government Licence – Newfoundland and Labrador.

with the licence's own qualifier that you should "acknowledge the source of the Information by including any attribution statement specified by the Information Provider and, where possible, provide a link to this licence." Dataset 361 specifies no custom attribution, so the default applies.

⚠ **The prior generation's licence position is NOT established.** `Distribution_2011.zip` was retrieved from the Internet Archive, not from the portal, and it carries no bundled licence file. The OGL–NL covers *the open data portal*; a file that predates the portal and is no longer served by the agency is **not demonstrably under it**. Do not assume the current dataset's licence flows backwards to it. See `## Research-handoff items`.

## Rate limits / auth

- **`opendata.gov.nl.ca`** — no auth, no key, no rate-limit headers, no click-through. Direct `filedownload/?file-id=N` links serve the file with a `Content-Disposition` filename. Dataset pages are plain server-rendered HTML.
- **`elections.gov.nl.ca`** — no auth, no WAF observed. ⚠ Link rot is the operative hazard rather than blocking: three separate historical download paths all 404 while the files remain in the archive. Anything located here should be staged immediately, not bookmarked.
- **`web.archive.org` CDX** — no auth. Use the `id_` raw-content endpoint (`/web/<timestamp>id_/<url>`) to get the original bytes without Wayback's HTML wrapper.
- No CAPTCHA, no registration, nothing accepted or submitted anywhere.

## Staged files

Staged under `data/boundaries/newfoundland-labrador/`; full table with sha256 in
[`PROVENANCE.md`](../../../data/boundaries/newfoundland-labrador/PROVENANCE.md).
**27.8 MB of the 500 MB budget.**

| Generation | File | Districts | Bytes |
|---|---|---:|---:|
| current | `current/NL_EB_Poly_50k.zip` | 40 | 16,254,401 |
| prior | `prior/Distribution_2011.zip` ⚠ archive-retrieved | 48 | 11,497,732 |

## Reconciliation with `constituency_boundaries`

**What we hold:** `source_set = 'newfoundland-and-labrador-electoral-districts'`,
`constituency_id` prefix identical, **36 rows**, `level = 'provincial'`,
`boundaries_version = 'current'`, `effective_from = '2023-01-01'`, `effective_to = NULL`
(the hardcoded placeholders). NL also holds 6 municipal rows under `st-johns-wards` —
out of scope here.

### ✅ A6 — NL is the one jurisdiction already compliant

**`newfoundland-and-labrador-electoral-districts` encodes no generation.** Of the 13
federal/provincial prefixes in the table, 12 violate the A6 ruling; this is the one that
does not. **No prefix change is required for NL** — it is already the shape every other
jurisdiction is being migrated toward, and it can serve as the reference example in the
build plan. The slug half is a kebab-case name slug (`.../baie-verte-green-bay`),
consistent with every other provincial set.

### The gap is exactly 4 districts

After folding dash variants and whitespace, our 36 names match the authoritative 40 with
**one spelling discrepancy and four absences**:

| Missing district (authoritative spelling) | Sitting member in our DB | Their `constituency_id` |
|---|---|---|
| `Burgeo - La Poile` | Michael King | `NULL` |
| `Humber - Gros Morne` | Mike Goosney | `NULL` |
| `Labrador West` | Joseph Power | `NULL` |
| `St. John's East - Quidi Vidi` | Sheilagh O'Leary | `NULL` |

Plus `Cartwright—L'Anse au Clair`, which we hold and which is spelled **correctly** in our
DB and **incorrectly** in the authoritative file — the only case in this workstream so far
where our data is right and the authority's is wrong.

### ★ The mechanism — roster-coverage, not BC's missing-`boundary_url`

Both are instances of the [`overview.md`](./overview.md) trap "boundaries are a side effect
of roster ingestion", but the proximate causes are different and the distinction matters
for what the build has to fix:

| | BC | NL |
|---|---|---|
| Open North roster size vs seats | **93 / 93 — complete** | **36 / 40 — short** |
| Politicians with `NULL constituency_id` | 41 | 0 *(of the Open North rows)* |
| Orphans | 0 | 0 |
| Proximate cause | roster complete, but 41 reps carried **no `related.boundary_url`**, so `_constituency_id()` returned `None` and the fetch was skipped | **4 districts have no representative in the roster at all**, so they were never iterated |
| Fingerprint | 41 NULL keys, 0 orphans | 36 clean rows, 4 districts simply absent |

NL's is the **Nunavut fingerprint** — the same failure that leaves Nunavut with zero
polygons despite 23 active politicians. The clean tell is that every one of our 36 rows is
healthy: 36 boundaries, 36 officials, 0 NULL keys among them, 0 orphans. Nothing was
dropped mid-flight; four districts were never reached. **No amount of re-running the
current loader fixes this** — it is bounded above by Open North's roster, which is short,
and Open North is down anyway.

### Cutover

- `authority = 'elections-nl'`; `authority_district_id` = ⚠ **the district name**, because no ID exists. Record explicitly that NL's authority key is a name, not a code — it is the exception to the pattern and a future reader will assume otherwise.
- `constituency_id` keeps `newfoundland-and-labrador-electoral-districts/<slugify(DIST_NAME)>` — **unchanged prefix (A6-clean)**, and the 36 existing slugs should be re-derivable, giving 36 stable keys plus 4 pure inserts.
- ⚠ **Normalisation rules the loader must implement, both mandatory:**
  1. Fold `—` / `–` / ` - ` / `-` to a single separator and collapse whitespace, or the authoritative names will not match a single one of our multi-part slugs.
  2. Special-case `Cartwright - L'Anse aux Clair` → `Cartwright - L'Anse au Clair`. **Log it loudly** rather than fixing it silently, so the day Elections NL corrects the typo we notice the rule has gone stale.
- ⚠ **Per-file SRID, not per-jurisdiction** — 2015 is the custom `SESA-TM`, 2011 is EPSG:2961.
- Unlike BC, the 36 rows we hold are **not known to be wrong** — they appear to be the current generation's geometry. But they came through Open North's `simple_shape` endpoint, so they are a doubly-simplified derivative of the authoritative file regardless, and should be replaced on the same principle.
- The 8 duplicate politician rows should be deduplicated **before** cutover, or the post-cutover orphan assertion will be measuring a roster problem and reporting it as a boundary problem.

## Research-handoff items

- **★ A new NL commission is due *this calendar year*, and that changes the priority of this jurisdiction.** *Electoral Boundaries Act* s. 13(2), verbatim: "In the calendar year beginning in 2026, and every 10 calendar years after that, the commission shall … divide the province into 40 proposed one-member districts." Today is 2026-08-18. **Any NL boundary load may be superseded within months.** Two consequences worth an operator decision: (a) it argues for loading the current 40 now and treating the temporal model as live rather than theoretical for NL specifically; (b) NL is the best near-term test of whether our staleness alarm actually fires — we know a redistribution is coming, so we can verify the alarm catches it rather than waiting for a surprise. Note the seat count stays at 40 by statute, so a **`district_count == seat_count` check will NOT catch this redistribution** — only a boundary-vintage check would. That is a real limitation of the alarm design I recommended, and NL is the counter-example.
- **"Proposed" vs enacted geometry.** Dataset 361 is described by the portal as "the final version of the **proposed** electoral boundaries". The count and names match the enacted House, so it is very likely identical, but the agency publishes nothing labelled as the enacted set. **Should we ask Elections NL to confirm the published file is the adopted geometry?** This is a short email and it removes the single largest correctness caveat on NL.
- **Legal in-force date is not establishable from the statute.** Unlike BC (`Electoral Districts Act` s. 6 names the triggering event), the NL *Electoral Boundaries Act* specifies no commencement mechanism — s. 14(2) only requires tabling. The implementing instrument was not located. Recommend `effective_from = 2015-11-30` (first general election on the new boundaries) marked `needs confirmation`, but an operator or a follow-up pass should find the actual proclamation or the *House of Assembly Act* schedule amendment.
- **⚠ Prior-generation provenance and licence.** `Distribution_2011.zip` exists only in the Internet Archive; all three origin URLs 404. Two questions: **(a)** is an archive-retrieved file acceptable as authoritative geometry for a superseded generation we would serve publicly? **(b)** the OGL–NL covers the open data portal — it does **not** self-evidently cover a file the agency has withdrawn. If the prior generation is going to be loaded and served, its licence needs establishing independently, most cheaply by asking Elections NL to re-publish it.
- **`SESA-TM` projection identity.** The current file's CRS is a custom provincial Transverse Mercator with no `AUTHORITY` clause and no EPSG code I could match. The proj4 string above is derived from its parameters and should be correct, but **it is derived, not looked up** — worth one confirmation against Elections NL or the NL GIS division before it becomes the basis for every NL coordinate we serve. A wrong scale factor or central meridian shifts every NL boundary by a consistent, plausible-looking offset.
- **No stable NL member ID.** Per CLAUDE.md convention #1, mint `politicians.nl_assembly_slug` from the existing `direct:assembly-nl-ca:<slug>` shape before building further on the NL roster. This also gives the deduplication job a key to work with.
- **Not a blocker, flagged per standing instruction 8:** no fetched page contained text addressed to an AI agent.

## Status

- [x] Current boundaries located and staged (2026-08-18) — 40/40, shapefile, custom CRS
- [x] Prior boundaries located and staged (2026-08-18) — 48/48, EPSG:2961 — ★ via A5 Wayback CDX after all origin URLs 404'd
- [x] Licence cleared for internal use — OGL–NL v1.0
- [x] Licence cleared for **redistribution** — "copy, modify, publish … distribute"; no flow-down
- [x] Attribution string captured verbatim
- [x] CRS recorded for both generations — ⚠ they differ, and the current one is **non-standard**; proj4 derived, `needs confirmation`
- [x] Attribute schema confirmed from `.dbf` headers (not guessed) — current is a **single field**
- [x] **★ The 36-row gap diagnosed** — exactly 4 districts, named, each with its sitting member identified
- [x] **★ Mechanism distinguished from BC's** — roster-coverage (36/40 roster), not missing `boundary_url`
- [x] **★ Brief's "8 zero-match" resolved** — 0 boundaries lack officials; the 8 are duplicate politician rows with NULL keys
- [x] **⚠ Upstream typo found in the only key field** — `L'Anse aux Clair`, confirmed wrong three ways
- [x] A4 checks — 40/40 and 48/48 distinct, one row per district, no fragmentation; `.cpg` present (UTF-8) on current, absent on prior
- [x] ✅ **A6 — NL needs no prefix change**, the one already-compliant jurisdiction
- [x] Postal-code correspondence — confirmed **none published**; do not re-probe
- [ ] Legal in-force dates — **`needs confirmation` for both generations**; statute specifies no commencement mechanism
- [ ] "Proposed vs enacted" geometry confirmation — **research-handoff item**
- [ ] Prior-generation licence + provenance decision (archive-only) — **research-handoff item**
- [ ] `SESA-TM` EPSG identity confirmation — **research-handoff item**
- [ ] Deduplicate the 8 duplicate politician rows — must precede cutover
- [ ] Build-phase cutover (4 inserts + 36 replacements; per-file SRID; two mandatory name-normalisation rules)
