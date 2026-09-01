# Electoral Boundary Research — Cross-Cutting Overview

> Shared methodology, reconciliation strategy, licence matrix, and progress tracking for the Canadian Political Data **electoral-boundary** effort. Per-jurisdiction boundary dossiers are siblings of this file in `docs/research/boundaries/`. The legislative-data counterpart is two directories up at [`../overview.md`](../overview.md); the municipal counterpart at [`../cities/overview.md`](../cities/overview.md). This doc is the boundary-specific layer and is the authority on the `constituency_id` re-key question.

**Status:** 🚧 Research phase 2026-08-18 — **all 21 dossiers complete**. ★ Measured: **9.15% of Canadian addresses get no provincial answer** from the lookup today; **12.61% any error** over the six jurisdictions where authoritative geometry could be checked. Every one of the 1,949 boundary rows is still an Open North mirror, and that upstream is ⛔ **down since 2026-08-07** (expired + mis-issued TLS cert, origin 502). **135 sitting representatives are unreachable by any postcode lookup.** No authoritative geometry loaded yet — the build is deliberately out of scope for this phase.
**Last updated:** 2026-08-18

---

## Why this project exists

The app's "who represents me" lookup resolves a postal code to a point, then runs point-in-polygon against our own `constituency_boundaries` table. Every row in that table was mirrored from Open North's Represent API, so we inherited Open North's staleness wholesale.

**A stale boundary is worse than a missing one.** A missing boundary produces "no representatives found" — visibly wrong, and the user knows not to trust it. A stale boundary produces a confident, plausible, *incorrect* riding, and the user has no signal that anything is wrong. Every jurisdiction below the "shortfall" line in the next section is currently serving that second failure mode to somebody.

The goal of this research round is, per jurisdiction: locate the **authoritative primary source** for current + immediately-prior boundaries, locate the roster source that maps districts to sitting officials, clear the licence, and stage the files. Transformation and loading are the build phase's job, not research's.

---

## What we hold today

Snapshot from the live DB, 2026-08-18. **1,949 rows / 105 distinct `source_set` / 3 levels.**

| Level | Rows | `source_set` values | `constituency_id` prefixes | Avg vertices | Max vertices |
|---|---:|---:|---:|---:|---:|
| Federal | 342 | 1 | 1 | 629 | 23,118 |
| Provincial | 665 | 12 | 12 | 999 | 129,321 |
| Municipal | 942 | 92 | 90 | 105 | 11,048 |

### ★ Municipal set count — reconciled

**The true figure is 92 distinct municipal `source_set` values.** The 94 that per-province counts sum to is a double-count artefact, fully explained:

- Exactly one `source_set` spans more than one province — **`census-subdivisions`, which appears in AB, BC and ON** (37 rows). Counting distinct sets per province therefore counts it three times. 92 + 2 = 94. No other set spans a province boundary.
- Independent confirmation from the loader side: `services/scanner/src/_muni_sets_generated.py` defines **108 municipal representative sets referencing exactly 92 distinct `boundary_set` values** — matching the DB exactly, because `_upsert_boundary` writes `source_set = set_def.boundary_set`. The 108→92 collapse is the many small municipalities that share `census-subdivisions`.
- The `quebec-districts` / `saguenay-districts` rows carrying a `*-boroughs/` prefix are a **separate phenomenon and do not affect this count at all** — that is a `constituency_id` *prefix* divergence, not a `source_set` value. Both sets contribute exactly one `source_set` each. See Known traps.

Distinct `constituency_id` prefixes at municipal level is **90**, two fewer than `source_set`, for the same prefix-divergence reason.

Uniformity of the temporal columns is total and is itself a finding: **every** row is `boundaries_version = 'current'`, `effective_from = '2023-01-01'`, `effective_to = NULL`. Both values are hardcoded string literals in `services/scanner/src/opennorth.py` (`_upsert_boundary`, ~line 545). The date is not the legal in-force date of anything — migration `0021`'s comment calls it "close enough for phase 0".

### Coverage shortfall — measured, not estimated

The honest measure is not "seats minus rows"; it is **how many currently-sitting representatives no postcode lookup can reach**, computed against the exact join the app uses (`postcode-reps.ts`, including its name fallback), excluding senators:

| Level | Jurisdiction | Unreachable sitting reps |
|---|---|---:|
| Provincial | BC | 45 |
| Provincial | NB | 30 |
| Provincial | NU | 22 |
| Provincial | SK | 15 |
| Provincial | NL | 8 |
| Municipal | QC | 5 |
| Provincial | YT | 3 |
| Municipal | ON | 2 |
| Provincial | NT / MB / ON / QC | 1 each |
| Federal | — | 1 |
| | **Total** | **135** |

Provincial boundary rows vs. seats, for the jurisdictions where the gap is structural:

| Jurisdiction | Rows held | Vintage we hold | Note |
|---|---:|---|---|
| Federal | 342 | 2023 Representation Order | one riding absent — **identify, do not guess** |
| BC | 52 | ~~2015 redistribution~~ → ★ **2015 geometry, 2023 district names** | **Not any real BC generation.** Exactly the 52-name intersection of the 87-district 2015 and 93-district 2023 orders; 51/52 areas match 2015 shapes to <0.5%. All 52 serve a *wrong polygon under a current name*. Diagnosed [`british-columbia.md`](./british-columbia.md) |
| NB | 22 | **2018 vintage of N.B. Reg. 2013-46**, mislabelled `-2024` | ✅ diagnosed: the 22 are the *name intersection* of the 2013-46 and 2023-42 generations; geometry matches the superseded set to 1.32% and the in-force set to **124.87%**. [`new-brunswick.md`](./new-brunswick.md) |
| SK | 46 | Representation Act **2012** | |
| NU | 0 | — | absent entirely; 23 active NU politicians, zero polygons |
| ON | 123 | Representation Act 2015 | |
| MB | 56 | 2018 | |
| NL | 36 | undated set slug | |
| YT | 19 | 2015 | roster/seat reconciliation `needs confirmation` |
| AB / NS / NT / PE / QC | 87 / 55 / 19 / 26 / 124 | — | row count matches sitting roster today |

**Known bounded gaps — both now closed (2026-08-18).** The federal shortfall was exactly one riding and the ON provincial shortfall exactly one district; both were identified from the authoritative orders rather than guessed. Ontario's is **Scarborough Southwest** (`ED_ID` 98, MPP Doly Begum) — see [`ontario.md`](./ontario.md); the federal agent has since staged all 343 ridings — see [`federal.md`](./federal.md).

---

## ★ The `constituency_id` problem

`constituency_id` is a free-text `TEXT` column on **three** tables with **no referential integrity anywhere**:

- `politicians.constituency_id` — `db/init.sql:33`
- `politician_terms.constituency_id` — `db/migrations/0002_expansion.sql:15`
- `constituency_boundaries.constituency_id` — `db/init.sql:187`; uniqueness relaxed to `(constituency_id, boundaries_version)` by migration `0021`

Format is `{open-north-boundary-set-slug}/{slug-or-numeric-id}`, minted at `services/scanner/src/opennorth.py:246` (`_constituency_id()`) by string-splitting Open North's `related.boundary_url`. The politicians↔boundaries join works **only** because both rows receive the identical string from the same API response in the same ingest pass. Nothing enforces it. The failure mode is a lookup silently returning "0 representatives found."

### Current health — the risk is prospective, not present

| Measure | Count |
|---|---:|
| `politicians` rows total | 10,453 |
| Active politicians | 2,523 |
| Active with a `constituency_id` | 2,260 |
| …of those, resolving to a current boundary | **2,258 (99.91%)** |
| …orphaned | **2** (Fort Erie wards 2 and 4 — see Known traps) |
| Active with `constituency_id IS NULL` | 263 |
| …rescued by the `lower(constituency_name)` fallback | **30** (11 federal, 19 provincial) |
| …with no `constituency_name` either | 104 (predominantly senators) |

So the exact-match join is healthy today and the name fallback carries only 30 reps (1.3% of resolvable). **The re-key risk is entirely prospective.** Nothing is broken by the current keying; everything would break the moment authoritative keys land without a coordinated cutover.

### Where the load actually sits

`politicians.constituency_id` is populated where `politician_terms.constituency_id` is not — confirmed and sharper than previously believed:

| Level | `politician_terms` rows | with `constituency_id` | % |
|---|---:|---:|---:|
| Federal | 1,970 | 11 | **0.56%** |
| Provincial | 16,591 | 1,179 | 7.11% |
| Municipal | 1,735 | 1,645 | 94.81% |

Total strings a full re-key would rewrite: 2,269 (`politicians`) + 2,835 (`politician_terms`) + 1,949 (`constituency_boundaries`) ≈ **7,053**. `politician_terms` is nearly free at federal and provincial level; `politicians` carries the load.

### ★ Two of the three key classes are already authoritative

This is the finding that reshapes the whole strategy. The slug half of `constituency_id` is **not** uniformly an Open North invention:

- **Federal — all 342 rows carry the Elections Canada FED code** (`federal-electoral-districts-2023-representation-order/35079`; verified: 342/342 slugs are numeric). The identity is already the authoritative government ID. Only the *prefix* is Open North's naming.
- **Municipal whole-municipality rows — 115 rows across 80 `source_set`s carry the StatCan Census Subdivision code** (`census-subdivisions/4811061` = Edmonton). Also already authoritative.
- **Provincial — all 12 sets use kebab-case name slugs** (`alberta-electoral-districts-2017/calgary-bow`), zero numeric. No authoritative ID present.
- **Municipal ward rows** — kebab or small integers (`edmonton-wards/1`), Open North's own naming.

457 of 1,949 rows (23%) therefore need **no re-key at all** — only a backfill recording *which* authority the existing ID belongs to.

---

## Reconciliation strategy

### The options, weighed against the code

**(a) Keep emitting Open-North-shaped slugs indefinitely.** Zero migration risk; every read path untouched. Fatal flaw: for districts Open North never covered we would have to *invent* their slug — all 22 Nunavut constituencies, the missing federal riding, BC's 41 new districts, NB's 27, SK's 15. Inventing a third party's naming convention is guessing, and two agents will guess differently. It also permanently welds our primary key to an upstream that is, as of today, serving an expired certificate behind a 502.

**(b) Coordinated re-key across all three tables and the ~92 municipal sets in one migration.** This mischaracterises the work. We are not rewriting existing rows in place — we are *inserting a new generation* of boundary rows as each jurisdiction's authoritative source clears licensing. A single big-bang migration would require all 14+ jurisdictions' loaders to be finished simultaneously. That is a coordination trap, and a half-applied version leaves `politicians` pointing at keys that exist for some provinces and not others, with no constraint to detect it.

**(c) A `constituency_aliases` mapping table.** Right instinct, wrong mechanism. An alias table only helps if reads go through it — and there are **eleven** read paths joining on `constituency_id` directly, two of them hand-duplicated across TypeScript and Python. Routing all eleven through an alias table is *more* invasive than a re-key, and it inserts a third join into the hot point-in-polygon path that is already a sequential scan.

### ★ Recommendation — (d) Authority columns + per-jurisdiction cutover behind the temporal model

**Keep `constituency_id` exactly as it is, redefined as *our* opaque surrogate key rather than Open North's. Record the authoritative identity in two new columns beside it. Cut over one jurisdiction at a time using the `boundaries_version` machinery that migration `0021` already built and nobody has ever exercised.**

1. `constituency_boundaries` gains `authority` (`elections-canada`, `elections-bc`, `statcan-csd`, …) and `authority_district_id` (text), plus `UNIQUE (authority, authority_district_id, boundaries_version)`. This is the constraint the table has always lacked.
2. `constituency_id` keeps its `{set-slug}/{id}` shape. New loaders mint it from the authoritative source in the **same shape** we already emit — so **no read path changes and no existing row moves**.
3. Backfill `authority` / `authority_district_id` for the 457 rows that are already authoritative (federal FED codes, municipal CSD codes). Pure metadata write, zero key churn, immediately useful.
4. Per jurisdiction, in one transaction: insert the new generation's rows with a real `boundaries_version` and real `effective_from`; `UPDATE politicians SET constituency_id = <new>` joined on `authority_district_id`; set `effective_to` on the superseded rows; **assert zero orphans before COMMIT**.
5. Add the guard whose absence is the actual root cause. Not a foreign key — boundaries are temporal and politicians outlive generations, so an FK would be wrong. A **scheduled assertion** that `COUNT(*) = 0` for active politicians whose `constituency_id` matches no current boundary, wired to the existing scanner-job telemetry.

**Verification per cutover** (all pre-COMMIT):
- orphan count is 0 for the jurisdiction's active politicians;
- exactly one `effective_to IS NULL` row per `constituency_id` table-wide;
- district count equals the seat count from the authoritative order;
- `ST_IsValid` on every new geometry, and every new row inside WGS84 bounds;
- the reference postcodes for that jurisdiction return the same rep set as a hand-check against the elections agency's own lookup.

**Half-applied degradation:** if a cutover aborts between insert and update you get two generations both carrying `effective_to IS NULL` — duplicated map polygons and doubled rep lists. That failure is *invisible* on the four read paths listed under Known traps that omit the `effective_to IS NULL` filter.

> ⚠ **Hard ordering constraint for the build: fix those four read paths BEFORE the first cutover.** They are harmless today only because a second generation has never existed. They stop being harmless on the first authoritative load.

Why (d) beats the alternatives: it never needs a flag day; each jurisdiction is independently revertible; 23% of the table needs no change; the hot PIP path gains no joins; and the authoritative ID becomes a column read rather than a string-parse for every future consumer.

---

## Licence matrix

**Consolidated by the coordinator 2026-08-18 from all 19 `_matrix/` fragments.** Per-source
detail, verbatim clause quotes and attribution strings stay in each dossier's
`## Terms / Licensing`. This table exists to answer one question: **what may we serve
publicly.** Our public boundary GeoJSON at `/api/public/v1/boundaries/*` is served under
permissive CORS with no terms attached, so redistribution is a live question, not academic.

### ✅ Cleared — open licence, redistribution explicit

| Jurisdiction | Licence | Note |
|---|---|---|
| Federal | Open Government Licence – Canada 2.0 | attribution required |
| Alberta | OGL – Alberta | ⚠ attribution is a **hard condition** — breach auto-terminates the grant |
| British Columbia | **Elections BC Open Data Licence** (⚠ *not* OGL-BC) | attribution string is prescribed verbatim, incl. their spelling "licenced" |
| Ontario | Elections Ontario **Open Use** Data Product Licence | commercial + distribution explicit, **no attribution clause at all** |
| New Brunswick | GeoNB Open Data Licence v1.0 | ★ the 2012 flow-down does **not** attach to data taken direct from GeoNB |
| Newfoundland & Labrador | OGL – Newfoundland and Labrador v1.0 | ★ also the only jurisdiction already A6-compliant |
| Nunavut | open, no gate | |
| Northwest Territories | OGL – NWT (via NWT Centre for Geomatics) | ★ sourcing direct from NTCG replaces the non-transferable Open North grant |
| Yukon | OGL – Yukon 2.0 | ⚠ licence **text unreadable** — every Yukon URL is Cloudflare-403; identity confirmed via CKAN metadata only |
| Municipal — Québec (24 sets) | **CC-BY 4.0**, uniform across all publishers | cleanest municipal block in the country |
| Municipal — Atlantic (NS/NB) | NS Open Government Licence; OGL – New Brunswick | two province-wide Socrata files cover 5 of 9 sets |
| Postal geocode — **StatCan NAR** | Statistics Canada Open Licence | explicit right to *"use, reproduce, publish, freely distribute, or sell"* **and sublicence** |
| Postal — StatCan FSA file, ODA | Statistics Canada Open Licence | |
| Postal — **`CP Territoires`** concordance | **CC BY 4.0** | ⚠ published by the **Institut de la statistique du Québec**, *not* Élections Québec — 220,513 QC postal codes, **99.87% resolving**. The only open postal→district concordance in Canada |

### ⛔ NOT cleared — no licence exists, operator decision required

| Jurisdiction | Rows | Position |
|---|---:|---|
| **Nova Scotia** (provincial) | 55 | ⛔ **None stated anywhere.** Elections NS's only machine-readable surface is an internal AGOL service with `licenseInfo: null` and `copyrightText: ""`, described *"DO NOT DELETE … for refence in applications"*. ⚠ `access: public` is an ArcGIS sharing setting, **not a licence**. The NS open-data portal has no provincial electoral product. **We are serving these 55 rows publicly right now.** |
| **Saskatchewan** | 46 | ⛔ Bare `Copyright © 2025 Elections Saskatchewan`, no terms page (404) |
| **Manitoba** | 56 | ⛔ `© 2026. All rights reserved.` + informational-purposes disclaimer. **An affirmative reservation** — stronger than SK's silence, so if only one agency is contacted make it this one |
| **Prince Edward Island** | 26 | ⛔ None stated on service or layer; no inheritable fallback; the agency that could clarify is behind the WAF |
| BC — LIMS postal concordance | (164,848 codes) | ⚠ No licence published. **Internal validation use is fine; serving it is not.** |
| Municipal — Ontario | 410 | ⚠ ~40 municipal licences unaudited; **Toronto's largest set literally reports "License not specified"** |
| Municipal — Alberta, West | 102 | ⚠ Unread. ⛔ **Winnipeg's Socrata declares "OGL – Prince Edward Island" on a Manitoba dataset** — a machine-readable licence field can be flatly wrong; never cite a portal tag |

### ⛔ Closed permanently

| Source | Why |
|---|---|
| StatCan **PCCF** (92-154-X) | Discontinued as a public product; DLI/academic-only; Canada Post licensed data |
| StatCan **PCFRF** (92-178-X) | $892/yr, Canada Post co-distributed, and keyed to the **superseded 2013** Order — even paying buys 338-district coverage against today's 343 |
| Geocoder.ca commercial dataset | Paid; excluded by the open-licence-only constraint |
| OpenStreetMap `addr:postcode` | ⚠ ODbL share-alike would contaminate a redistributed table — decide before mixing |
| Open North `represent-canada-data` | ⚠ Their redistribution permission is **theirs, non-transferable.** Class B ("Distributed with permission from…") grants us nothing and covers NS + NT. **205 rows (ON 123, MB 56, PE 26) have no licence file upstream at all** |

★ **The headline for the operator: four provinces — NS, SK, MB, PE — have no licence route
that research can unlock**, plus several municipal blocks. That is 183 provincial rows.
It is now one policy question, not six separate ones.

## Probe hierarchy for geospatial sources

Geospatial adaptation of the project-wide hierarchy in [`../overview.md`](../overview.md). Record dead ends explicitly so nobody re-probes them.

1. **Open-data portal API** — CKAN / Socrata / ArcGIS Hub / Opendatasoft. Prefer GeoJSON where both it and shapefile are offered.
2. **Elections-agency direct download** — the agency that drew the boundaries. This is the authoritative tier; 1 is often just a republish of it.
3. **Provincial GeoHub / `geo.ca`** — federated catalogues; useful when the agency publishes maps but not data.
4. **Statistics Canada** — federal FEDs and the CSD/CD layers. Authoritative for census geography, *derivative* for provincial electoral districts.
5. **HTML scrape** — only after 1–4.

⛔ **Stop conditions.** A click-through "Limited Use Data Product Licence Agreement" (Elections Ontario confirmed) is a hard stop: record the text verbatim, record the URL behind it if visible, raise a research-handoff item, do not click. A file over the 500 MB per-agent budget is a hard stop: record URL + `Content-Length`, raise a handoff item.

---

## Known traps

Each verified in code or by query on 2026-08-18.

**⚠ `ST_SetSRID` labels, it does not reproject — and the CHECK turns corruption into silent absence.** `_upsert_boundary` builds geometry as `ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON($4), 4326))`. If upstream serves a projected CRS, we store metres labelled as degrees. Migration `0003_boundary_wgs84_guard.sql` was written to repair exactly this — Fort Erie ward boundaries arrived in NAD83 / UTM 17N (EPSG:26917), centroids landed at (~660000, ~4750000), and the frontend drew connection lines past the edge of the world. The migration added `boundary_in_wgs84_bounds`. **The guard works, but the loader swallows the resulting exception**: `_ingest_set`'s per-rep handler is wrapped in `except Exception: log.exception(...)` and continues. ★ Live residue: Fort Erie has 6 wards and 6 sitting councillors but **only 4 boundary rows** — wards 2 and 4 are the *only two orphaned `constituency_id`s in the entire active roster*. The CHECK converted a loud data-corruption bug into a silent data-absence bug. Any new loader must fail the run, not the row.

**⚠ Every point-in-polygon is a sequential scan.** `db/init.sql:200` creates GIST indexes on `boundary_simple` and `centroid` — **not on `boundary`** — yet all four PIP call sites use full `boundary`. Verified plan: `Seq Scan on constituency_boundaries … Rows Removed by Filter: 1945, Buffers: shared hit=3510, Execution Time: 9.398 ms`. Tolerable at 1,949 low-vertex rows *only because the geometry is already simplified* (see next trap). Authoritative full-resolution geometry will make this the dominant cost. **A GIST index on `boundary` is a build prerequisite, not an optimisation.**

**⚠ We never held full-resolution geometry.** `_fetch_boundary` requests `{BASE}/boundaries/{cid}/simple_shape` — Open North's *simplified* rendering geometry, not `/shape`. `boundary_simple` is then a **second** simplification (`ST_Simplify(…, 0.005)`, ~555 m) on top of it. So `constituency_boundaries.boundary`, the column every PIP treats as authoritative, is a derivative. Average vertex counts (federal 629, municipal 105) corroborate. Boundary-edge postcodes can resolve to the wrong riding today, independently of staleness.

**⚠ 12 rows have `NULL boundary_simple`.** The 555 m simplify tolerance exceeds the polygon, `ST_CollectionExtract(…, 3)` returns nothing. All 12 are Montréal-area micro-districts under 0.44 km² (Westmount 4/6/7/8, Montréal-Est 2/3/4/6, Senneville 4/5, Côte-Saint-Luc 1, Sainte-Anne-de-Bellevue 5). Because the only polygon GIST index and every list/detail response use `boundary_simple`, these wards are **invisible on the map and return null GeoJSON from the public API** while still resolving correctly in PIP. Tolerance must scale with feature size.

**⚠ The temporal model has never been exercised, and `'current'` is a mutable label.** All 1,949 rows are `boundaries_version = 'current'`, hardcoded. The unique key is `(constituency_id, boundaries_version)`. If a second generation is also written as `'current'`, `ON CONFLICT DO UPDATE` **overwrites the old row in place** — silently destroying the history migration `0021` exists to preserve. Cutover must rename the superseded generation's version string *before* inserting the new one.

**⚠ Four read paths omit `effective_to IS NULL` and will return duplicates on the first second-generation load.** Audited all eleven:

| Path | Filter present? |
|---|---|
| `services/api/src/lib/postcode-reps.ts:46` | ✅ |
| `services/scanner/src/alerts_worker.py:186` | ✅ |
| `services/api/src/routes/public/boundaries.ts:139` (`lookupBoundariesAtPoint`) | ✅ |
| `services/api/src/routes/public/boundaries.ts:221/233` (list + count) | ✅ |
| `services/api/src/routes/public/boundaries.ts:368` (detail) | ✅ |
| `services/api/src/routes/public/postcodes.ts:218` | ✅ |
| `services/api/src/routes/politicians.ts:478` | ⛔ **missing** |
| `services/api/src/routes/public/politicians.ts:474` | ⛔ **missing** |
| `services/api/src/routes/map.ts:219` (no-data overlay JOIN) | ⛔ **missing** |
| `services/api/src/routes/map.ts:320` (AB context union) | ⛔ **missing** |

The two politician-detail paths do `WHERE constituency_id = $1` with no version filter and `queryOne` — they will return an arbitrary generation. `map.ts:219` will emit duplicate overlay polygons; `map.ts:320` will union both generations of Alberta.

**⚠★ Two distributions of the same dataset can disagree on the district ID — check, don't assume.** Found in BC 2026-08-18 and worth every agent testing for. Elections BC's 2015 set is published both as a shapefile and over WFS. Decoding the `.dbf` and diffing against the WFS GeoJSON: `ED_NAME` agrees 87/87 and the abbreviation agrees 87/87, but **the shapefile's `ED_ID` is exactly one lower than the WFS's `ELECTORAL_DISTRICT_ID` in all 87 records** (what the shapefile calls `OBJECTID` is what WFS calls `ELECTORAL_DISTRICT_ID`). Because these IDs are contiguous and alphabetically ordered, an off-by-one **throws nothing, orphans nothing, and passes every count check** — it silently maps each district onto its alphabetical neighbour. Shapefile `.dbf` field names are also truncated to 10 characters (`ED_ABBREV`, `GAZETTE_DT`, `FEAT_AREA`) where WFS spells them in full, so a loader written against one distribution reads nothing from the other. **Guidance: key on the district *name* where it agrees across distributions, pin `authority_district_id` to one named distribution, and record which.** See [`british-columbia.md`](./british-columbia.md) § Prior boundaries for the evidence table.

**⚠ The Python PIP is a hand-copy of the TypeScript one, synchronised by a comment.** `alerts_worker.py:172` says "PIP + join mirrors services/api/src/lib/postcode-reps.ts — keep the two in sync." Nothing enforces it.

**⚠ The two "byte-identical" postcode surfaces already disagree.** `public/postcodes.ts:214` and `postcode-reps.ts:46` are documented as returning the same rep set. They do not: `postcodes.ts` additionally requires `p.level = b.level` and an open `politician_terms` row, and it **omits the `lower(constituency_name)` fallback entirely**. The 30 active reps that only resolve via the name fallback are therefore visible to the internal lookup and invisible to the public API.

**⚠ `source_set` ≠ the `constituency_id` prefix for 86 of 105 sets — and the pattern is not the one previously assumed.** `_upsert_boundary` writes `source_set = set_def.boundary_set` (the *representative set's* configured boundary set), while `constituency_id` is parsed from the individual rep's `boundary_url`. The divergences:

- **Federal (342 rows):** `source_set = 'federal-electoral-districts'`, prefix = `federal-electoral-districts-2023-representation-order`.
- **AB (87):** `source_set = 'alberta-electoral-districts'`, prefix = `alberta-electoral-districts-2017`.
- **NB (22):** `source_set = 'new-brunswick-electoral-districts-2024'`, prefix = `new-brunswick-electoral-districts-2018`. ★ The set is *named* for a generation whose IDs it does not contain — and the prefix is the honest half: the geometry is the 2018 vintage, confirmed against GeoNB's own files to 0.01% on the discriminating district. ★ **Why exactly 22 of 49:** Represent resolved its NB MLA roster to boundaries *by name* against its own 2018 set, matched only the districts whose names survived the 2023 redistribution, and left `related.boundary_url` null on the other 27 — so `_constituency_id()` returned `None` and no boundary was fetched. A worked instance of the roster-driven-ingestion trap below. [`new-brunswick.md`](./new-brunswick.md) § Reconciliation.
- **★ 80 municipal sets (115 rows):** each `<city>-wards` set contains one row whose prefix is `census-subdivisions/<CSD code>` — the **whole-municipality polygon**, i.e. the mayor's / at-large members' "district". This is by design, not corruption, and `postcode-reps.ts` documents relying on it. A further 4 rows carry `census-divisions/<CD code>` — Ontario regional chairs: Peel (inside `peel-wards`), Niagara, Waterloo, Lambton (inside `census-subdivisions`).
- **QC (5) and Saguenay (3):** prefixes `quebec-boroughs/` and `saguenay-boroughs/` inside `*-districts` sets.

Because `ON CONFLICT` overwrites `source_set`, a `census-subdivisions/*` row's `source_set` is **last-writer-wins** across whichever representative set ingested last. It is not a stable attribute.

**⚠ The detail route's `:source_set` path param is not the `source_set` column.** `/boundaries/:source_set/:slug` rebuilds `` `${source_set}/${slug}` `` and matches `constituency_id`. Given the divergence above, callers must pass the *prefix*, not the column — `/boundaries/federal-electoral-districts-2023-representation-order/35079` works; `/boundaries/federal-electoral-districts/35079` 404s. The parameter is misnamed.

**⚠ Env-var asymmetry.** The API reads `OPEN_NORTH_BASE` (`services/api/src/lib/postcode.ts:32`); the scanner and generator read `OPENNORTH_BASE` (`opennorth.py:36`, `scripts/generate_muni_sets.py:24`). Only `OPENNORTH_BASE` is set in `.env.example:72` and `docker-compose.yml:264`. **The API's variable is never set**, so it always falls back to the hardcoded default — pointing the scanner at a mirror or a local fixture will not redirect the API.

**⚠ Boundaries are a side effect of roster ingestion.** `_ingest_set` fetches a boundary only inside the per-representative handler, keyed off that rep's `boundary_url`. A district with no sitting representative in Open North's roster gets **no boundary row at all**. This is why Nunavut has zero polygons despite 23 active NU politicians, and it means boundary coverage can never exceed roster coverage under the current loader. Authoritative loaders must be driven by the *boundary file*, not the roster.

> **★ BC is the proof case, and it shows the trap is worse than "missing rows."** Confirmed 2026-08-18 — see [`british-columbia.md`](./british-columbia.md) § Reconciliation. **The failure is upstream of the fetch, not a swallowed 404.** `_constituency_id()` (`opennorth.py:246`) returns `None` when the representative record has no `related.boundary_url`; that `None` is written straight to the politician as a **`NULL constituency_id`** (`opennorth.py:299`), and the boundary fetch is **guarded on the key existing** (`opennorth.py:590`, `if cid and …`) so it is **never called**. Nothing is logged, counted, or raised at any step. BC's numbers: Open North's roster was **complete at 93** rows, **41 carry a `NULL` key**, and there are **0 orphans** — zero orphans is the fingerprint, because a swallowed 404 would instead leave a non-NULL key pointing at a boundary that was never written. When Open North's *roster* is fresher than its *boundary set* — BC's roster is the current 93 MLAs, its boundary set is still 2015 — renamed districts have no boundary URL to offer and vanish on **both** sides at once; the districts that were *not* renamed resolve fine and are written **with the old generation's geometry under a current name**. BC's 52 rows are entirely that second category: 51 of 52 match 2015 shapes to <0.5%. So the failure mode is not 41 missing polygons at the edges, it is **52 confidently-wrong polygons in the middle** — exactly the "stale is worse than missing" case this workstream exists to eliminate, produced silently by the loader itself. **One root cause yields both symptoms:** the unreachable-rep count and the wrong-polygon count are the two halves of the same `None`. Any jurisdiction whose roster outpaces its boundary set has the same split. ⛔ Note for other agents: pagination artefact, regional roster gap, and "the roster was short" were each tested against BC and **falsified** — don't re-run those.

---

### ★ A12 — the `census-subdivisions` row is not always contamination

⛔ **Migration-safety, corrects an earlier ruling.** Councils fall into **three** shapes, not
two, and the third is the common one in Atlantic Canada. **Hybrid councils** attach officials
to *both* tiers — the CSD row carries the mayor and at-large seats, ward polygons carry ward
councillors. St. John's has **6 officials on its CSD row** and 5 on wards; Saint John 3 and 8;
Moncton 3 and 8; Fredericton 2 and 12. **Dropping CSD rows as contamination would orphan 14
sitting Atlantic officials.**

**Rule:** a `census-subdivisions/` row is removable **only when no officials are attached to
it** — verified per set by query, never inferred from the set name.

★ **Duplication risk tracks two-tier governance, not amalgamation history.** Peel duplicates
because its lower-tier municipalities each kept a council, so both tiers have wards and both
were ingested. Halifax (1996) and Cape Breton (1995) *dissolved* their lower tiers — verified
clean, 2 polygons not 4. Same for Toronto, Hamilton, Ottawa, Greater Sudbury. **Next to test:
Ontario's surviving two-tier regions — Niagara, Waterloo, Lambton.**

⚠ **The overwrite bug is worse than first measured.** Halifax is a **5,957 km² CSD against an
8.5 km² district — 703×**; Cape Breton 430×; Mississauga, the first case found, only ~104×.
Halifax is the best regression fixture for the smallest-matching-polygon fix.

### ★ Four traps from the western municipal pass

1. ⛔ **GeoJSON is not always WGS84.** Regina's carries a *legacy* `crs` member naming
   EPSG:26913 with projected-metre coordinates. RFC 7946 mandates WGS84 and removed `crs`,
   so "GeoJSON ⇒ 4326" sounds safe, is wrong, and **fails silently** — it put Regina's wards
   in the Gulf of Guinea. **Check coordinate magnitude on every GeoJSON.** Note this
   *inverts* the earlier ArcGIS finding: there, `f=geojson` reprojected to degrees and
   `f=json` did not. There is no constant rule; always check the numbers.
2. ⛔ **A machine-readable licence field can be flatly wrong.** Winnipeg's Socrata dataset
   declares **"Open Government Licence – Prince Edward Island"** on a Manitoba product.
   Licence-matrix rows must cite a terms page a human read, never a portal tag.
3. ⚠ **Socrata's catalogue API is federated by default** — `data.winnipeg.ca/api/catalog/v1`
   returns Calgary's and Edmonton's datasets with no off-domain marker. Scope with
   `search_context`.
4. ⚠ **A latent municipal name-fallback collision.** `postcode-reps.ts` falls back to
   `lower(constituency_name)` at the same level, and **`"Ward 1"` names 48 polygons across
   48 sets** (verified; `Ward 3` 47, `Ward 2` 46). Harmless *today* — exactly 5 municipal
   politicians have a NULL `constituency_id`, all QC (verified) — but A7 established that a
   missing `boundary_url` leaves that column NULL, so the next western municipality to lose
   its link would attribute its councillors to up to 47 other cities. Provincial and federal
   district names are unique nationally; **ward names are not.** Scope the fallback by
   `source_set`.

★ **BC at-large has a statutory answer key, stronger than a published list.** Under the
*Local Government Act*, at-large is BC's **default** — wards require a bylaw approved by the
Lieutenant Governor in Council. Alberta is the same shape (MGA s.148, warding is opt-in).
So BC's 12 zero-ward rows are correct and complete, and **no further agent time should go
into hunting BC ward data.**

⛔ **Grande Prairie is a distinct defect class: two *municipalities* overlap, not two tiers.**
County of Grande Prairie No. 1 divisions were digitised over the City rather than clipped
around it, covering **100% of it** (verified: Division 3 53.2% + Division 2 25.5% +
Division 4 21.3%). Every Grande Prairie city address also returns a County councillor. A
repo-wide cross-set overlap scan found only these three pairs plus a 0.5 km²
Strathcona/Edmonton sliver. Fix is a load-time clip against the City CSD with an
`ST_Area(ST_Intersection(...)) = 0` assertion.

### ★★ The canonical duplicate-detection query — verified, use this one

Three rules were tested against the live ON municipal set. **Two of the three are wrong in
opposite directions**, and both wrong answers look plausible:

| Rule | Pairs | Verdict |
|---|---:|---|
| `ST_Equals(a, b)` | **16** | ⛔ **Under-matches.** Finds all 10 Brampton + 6 Caledon duplicates and **zero Mississauga** — yet all 11 Mississauga wards *are* doubled, at 99.65–99.94% overlap from a second digitisation. A de-dup built on this removes Brampton and Caledon and **silently leaves Mississauga doubled**, which is the worst outcome because the survivor then looks deliberate. |
| overlap ≥ 99% of the smaller polygon | **444** | ⛔ **Over-matches catastrophically.** Containment satisfies it: a ward is 100% inside its own city CSD and its census division, so this rule deletes wards as "duplicates" of the municipality that contains them. |
| ✅ overlap ≥ 99% **AND** area ratio between 0.95 and 1.05 | **27** | ✅ **Correct** — exactly the 16 Brampton/Caledon pairs plus the 11 Mississauga pairs, nothing else. The area-ratio guard is what rejects containment. |

```sql
-- Canonical cross-set duplicate detector. The area-ratio guard is load-bearing:
-- without it, containment (ward inside its CSD / census division) matches too.
SELECT a.constituency_id, b.constituency_id,
       ST_Area(ST_Intersection(a.boundary, b.boundary))
         / least(ST_Area(a.boundary), ST_Area(b.boundary)) AS overlap,
       ST_Area(a.boundary) / ST_Area(b.boundary)           AS area_ratio
  FROM constituency_boundaries a
  JOIN constituency_boundaries b
    ON a.id < b.id
   AND a.level = b.level
   AND ST_Intersects(a.boundary, b.boundary)
 WHERE ST_Area(ST_Intersection(a.boundary, b.boundary))
         / least(ST_Area(a.boundary), ST_Area(b.boundary)) >= 0.99
   AND ST_Area(a.boundary) / ST_Area(b.boundary) BETWEEN 0.95 AND 1.05;
```

⛔ **The corrected duplication rule.** The earlier "duplication tracks two-tier governance"
heuristic was **tested and refuted**: Niagara (24 wards, 5 sets) and Waterloo (40 wards,
7 sets) are genuinely two-tier and have **zero** duplicates; Lambton has no ward sets at all.
Only Peel duplicates. The real discriminator:

> **Duplication risk tracks whether an upper-tier region has its own ward set alongside its
> lower-tier municipalities' sets** — Open North published `peel-wards` but no
> `niagara-wards` or `waterloo-wards`.

That is strictly better because it needs no governance knowledge and is directly SQL-testable.
The governance heuristic remains useful for *where to look*, but it over-predicts.


### ⛔ A12 settled definitively — every CSD row is load-bearing

Coordinator query, 2026-08-18, all municipal `census-subdivisions/*` rows nationally:

| | |
|---|---:|
| CSD rows in the table | **115** |
| …carrying ≥1 sitting official | **115** |
| …removable (zero officials) | **0** |
| Sitting officials attached | **326** |

**There is no contamination to remove.** The coordinator's original guidance — treat CSD rows
inside ward sets as junk — would have deleted **326 sitting officials** from the lookup.
Per-province: ON 157, **BC 104**, QC 22, AB 22, NB 7, NL 6, PE 3, SK 2, NS 2, MB 1.

★ **British Columbia is the sharpest case even though Ontario has more.** BC has **no ward
polygons at all** (at-large is the statutory default under the *Local Government Act*), so
its 12 CSD rows are not a redundant second tier — they are the **only** geometry attaching
104 sitting officials to anything. A wholesale drop would delete British Columbia from the
postcode lookup entirely, silently, with **no row-count signal**.

**The defect was never the rows' presence.** It is `lookupBoundariesAtPoint` overwriting
instead of preferring the smallest matching polygon. **Fix the resolver, keep the rows.**

### ★ The structural test for legitimate vs erroneous overlap

Grande Prairie was predicted to be Peel-shaped and **tested negative**, which changes its fix:

> **Legitimate two-tier duplication has a `census-divisions/` row as one of the two parties.**
> If both parties are at CSD level — or one is a ward set with no CSD row — the overlap is a
> **digitisation error to be clipped**, not duplication to be de-duplicated.

Peel qualifies (`census-divisions/3521`, 1,256 km², over lower-tier CSDs). Grande Prairie does
not: the City is `census-subdivisions/4819012` and the County is a ward-style set with no CSD
row — **peers at the same level**. Alberta has no two-tier municipal governance; a point
belongs to a city *or* a county, and GP city residents do not elect County councillors.

⚠ **All four `census-divisions/` rows exist and are easy to miss.** Verified:

| `constituency_id` | Name | `source_set` | km² |
|---|---|---|---:|
| `census-divisions/3521` | Peel | `peel-wards` | 1,256 |
| `census-divisions/3526` | Niagara | **`census-subdivisions`** | 1,884 |
| `census-divisions/3530` | Waterloo | **`census-subdivisions`** | 1,385 |
| `census-divisions/3538` | Lambton | **`census-subdivisions`** | 3,036 |

Three of the four sit in a `source_set` that does not match their prefix, so a
`source_set`-based scan misses them entirely.

### ⚠ UNRESOLVED — NWT: two dossiers disagree on the *cause*, and it changes the migration

Both agree on the **symptom**, from independent methods: [`impact.md`](./impact.md) measures NT
at 14.3% of addresses wrong with 9.5 points of misassignment localised to Yellowknife;
[`northwest-territories.md`](./northwest-territories.md) finds 5 of 19 districts misassigned by
polygon intersection. Same defect, two directions.

They disagree on **why**:

| | Claim | Build consequence |
|---|---|---|
| [`impact.md`](./impact.md) | Our polygons are the 2013 generation; the authoritative file is 2023; districts were redrawn without changing the count | **New generation** — new `effective_from`, retire the 2013 rows |
| [`northwest-territories.md`](./northwest-territories.md) | **No redraw has occurred.** LAECA s. 2(1) still reads *"There are 19 electoral districts as named and described in Schedule A"*; no implementing bill in the 20th Assembly; the 2025–26 Commission recommended 22 in Feb 2026, which makes little sense had a redraw just happened; `ElectoralYear=2023` is a refresh for the Nov 2023 general election | **In-place geometry correction** — no generation change, no FK movement |

Evidence genuinely cuts both ways: the two wrong pairs are *adjacent with complementary
over/under errors*, which is what rebalancing looks like — but `Nunakput` is 2× oversized while
*containing* 100% of the authoritative district (a marine-extent difference, not a redraw), and
`Yellowknife North`, the district the 2013/14 order actually created, matches to **0.03%**.

⛔ **Do not write the NT migration until this is reconciled.** Resolving it needs the pre-2013
NT geometry, not yet obtained; the one unprobed lead is the NWT Discovery Portal (an Esri
Geoportal catalogue). **Safe default: the in-place correction** — it fixes the wrong answers
under either explanation and is reversible.


### ✅ A7 vintage verification — corpus status

Every major provincial holding has now been verified by **measurement**, not arithmetic.

| Jurisdiction | Verdict | Evidence |
|---|---|---|
| Alberta | ✅ current | 99.887% vs current, 81.275% cross-generation |
| **Quebec** | ✅ **current (2017 in force)** | **99.887% vs 2017, min 99.472%, zero below 95%**; 94.917% vs the pending 2026 map with 25 below 95%. Clean separation |
| **Manitoba** | ✅ current (2018) | **99.828% mean, min 99.200%**, 54/56 — cleared after being suspected on name-matching |
| Nova Scotia | ⛔ 1 absent + 1 reshaped | intersection; caught `Inverness` at 60.08% |
| Saskatchewan | ⛔ 41 wrong + 15 absent | 0.07% vs 2012 / 11.67% vs 2022; 41 match 2012 alone, **0** match 2022 alone |
| British Columbia | ⛔ 52 wrong + 41 absent | name-stable 2015∩2023 intersection carrying 2015 shapes |
| New Brunswick | ⛔ 22 wrong + 27 absent | 1.32% vs superseded / 124.87% vs in force |
| NWT | ⛔ 5 of 19 misassigned | polygon intersection; cause ⚠ disputed (see below) |
| Federal, Ontario, Yukon | measured | via [`impact.md`](./impact.md) Phase 2 |

⚠ **Only PEI (26 rows) still has an unmeasured completeness claim.** NB and NL already
conclude their own holdings are short; NU holds 0 rows; SK is the confirmed silent-redraw
case. PE is a footnote, not a gap — but it is the last one.

★ **Refinement to A8.1, earned in the Quebec run.** The area/drawing-convention artefact
**never appeared** in Quebec — minimum overlap across 121 matched districts was 99.472% with
no coastal or Gulf outliers, in the jurisdiction where the caution should have bitten hardest.
The reason is **lineage**: our rows are an Open North mirror *of the same Élections Québec
file*, so both sides share one water-drawing convention and there is nothing for the artefact
to bite on.

> **A8.1 applies to comparisons across *publishers*, not to mirror-vs-origin comparisons.**

That tells a future measurer when the defensive work can be skipped — which is the cheap and
common case.

★ Three Quebec rows failed to slug-match and were each verified **geometrically** rather than
assumed: `camille-laurin` → `Bourget` (99.811%, the 2022 rename), `darcy-mcgee` →
`D'Arcy-McGee` (99.753%), `lassomption` → `L'Assomption` (99.944%). All apostrophe or rename
artefacts, not gaps.


### ⛔ The incoming Quebec map is a full replacement, not "+2 districts"

Authoritative 2017 vs authoritative 2026, **shapefile vs shapefile**:

| | Count |
|---|---:|
| Names shared across both generations | 108 |
| Names that disappear | 17 |
| Names that appear | 19 |

Of the 108 name-stable districts: **72 unchanged** (≥99.5%), 9 minor (95–99.5%),
**24 redrawn** (50–95%), **3 heavily redrawn** (<50%). Mean 94.68%, min 39.04%.

> ⛔ **Only 72 of 127 districts — 57% — carry through unchanged. 55 are new, renamed, or
> materially redrawn.**

The imminent Quebec load is therefore a **full generational replacement**, to be scoped and
scheduled as one — not two inserts against the existing 124. ★ It also settles **A6-2**
without argument: a replacement that size rewrites the keys regardless, so the
generation-free prefix fix rides along free.

⚠ **Trap — do not use the `sans eau` GeoJSON for geometry comparison.** Élections Québec
publishes `circonscriptions_electorales_sans_eau_2026.json`, and the coordinator initially
suggested it to avoid shapefile parsing. **That would have corrupted the measurement.**
"Sans eau" is water *removed* — a different **extent**, not a generalisation — and no
`avec_eau` GeoJSON is published. Comparing a water-clipped 2026 layer against the
water-inclusive 2017 shapefile depresses every coastal, Gulf and estuary district and
**manufactures precisely the artefact A8.1 warns about**: it would have produced tens of
false "redrawn" districts across the Gaspé, the Îles-de-la-Madeleine and the North Shore.
Both figures above are shapefile-vs-shapefile.

ⓘ **Where the Quebec numbers live.** The A7-2 measurement was produced during the QA sweep by
an agent that did not own `quebec.md`, under a "report, don't edit what you don't own"
instruction — so the full result is in [`_qa-sweep.md`](./_qa-sweep.md), not in the Quebec
dossier. A reasonable convention that cost one round-trip to discover; noted here so the next
reader doesn't repeat it.


### ✅ A7 sweep COMPLETE — and a bounded caveat on the impact figures

**Nothing anywhere in the corpus rests on counts or names alone.** Manitoba, Quebec and PEI
cleared by direct measurement; BC, YT, NT, ON, NS, AB and federal covered by
[`impact.md`](./impact.md) Phase 2. Of the remainder, NB and NL already conclude their own
holdings are short, NU holds 0 rows, and SK is the confirmed silent redraw that motivated the
ruling.

★ **Three of three suspects came back clean.** The corpus's authors were reaching correct
conclusions; what was missing was the *evidence class*, not the judgement.

**PEI result:** 25 of 26 held rows matched at **99.380% mean**, min 92.668%, one below 95%.
The 26th is `oleary-inverness` ↔ `o-leary-inverness`, apostrophe normalisation. Exactly one
district absent — `Georgetown-Pownal`.

★ **PEI's 28.8% no-answer rate is NOT wrong geometry and NOT patchy coverage.** Both
hypotheses were refuted precisely: the island coverage gap is **470.1 km²** and
`Georgetown-Pownal` is **469.7 km²** — a match to **0.09%**. The remaining 26 polygons tile
the island cleanly.

⚠ **But the check surfaced a real measurement caveat.** `impact.md` runs its point-in-polygon
against `boundary_simple`, not `boundary`. Coordinator query, area lost to simplification on
the provincial layer:

| | PE | YT | NL | NT | NB | NS | MB | BC |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| % area lost | **2.10** | 0.41 | 0.18 | 0.16 | 0.09 | 0.06 | 0.03 | 0.01 |

**PEI loses an order of magnitude more than anywhere else**, and on a narrow island that
erosion is a **coastal rind** — which is where most PEI addresses are. That plausibly explains
part of why PE's address-weighted 28.8% exceeds its ~12% area-based expectation.

✅ **The national 9.15% figure is unaffected.** PE is 0.53% of Canadian addresses and every
other jurisdiction loses under 0.5% to simplification, so this is a PEI-local artefact, not a
systemic overstatement. Closing PE's residual needs the address sample, not polygon
arithmetic.

**Actionable regardless:** PE's `boundary_simple` should be regenerated at a finer tolerance,
**or** the PIP path should fall back to full `boundary` on a `boundary_simple` miss. Note this
interacts with build prerequisite **C3** — there is no GIST index on `boundary`, so a fallback
needs that index first.

★ **A second refinement to A8.1, from PEI.** The coastal artefact **did not appear even
cross-publisher**, on an island where every district touches water. The sub-95% outlier was a
compact *urban* district (`charlottetown-belvedere`, 92.67%) where a small absolute difference
is a large proportion — its four neighbours run 98.67–99.24%. So the caution mispredicts in
two directions now: it doesn't fire on mirror-vs-origin comparisons, and where it does fire,
**the risk sits with small-area districts rather than long-coastline ones.**


## Coverage matrix

**Consolidated by the coordinator 2026-08-18 from all per-jurisdiction dossiers.** Rows held
are live counts from `constituency_boundaries`. "No answer" is the address-weighted
measured rate from [`impact.md`](./impact.md) (2,500-address sample per jurisdiction against
the StatCan National Address Register). Verdicts are the dossier findings, not inference.

| Jurisdiction | Rows held | Seats | Authoritative | Vintage held | Current vintage | No answer | Verdict |
|---|---:|---:|---:|---|---|---:|---|
| [Federal](./federal.md) | 342 | 343 | 343 | 2023 Rep. Order | 2023 Rep. Order | 0.95% | ⚠ one district absent — FED **24077** Ville-Marie—Le Sud-Ouest—Île-des-Sœurs |
| [Alberta](./alberta.md) | 87 | 87 | 87 | 2017 | 2017 | ✅ 0.2% | ✅ **complete and current** — cleanest jurisdiction; ⚠ 2026 commission proposes 89 |
| [British Columbia](./british-columbia.md) | 52 | 93 | 93 | **2015 geometry** | 2022-23 (in force 2024-09-21) | ⛔ 42.3% | ⛔ **52 wrong + 41 absent** — the 52 are the name-stable 2015∩2023 intersection carrying 2015 shapes |
| [Saskatchewan](./saskatchewan.md) | 46 | 61 | 61 | **2012 geometry** | 2022 (in force 2024-10-01) | ⚠ 22.3% | ⛔ **41 wrong + 15 absent** — proven: 46/46 match 2012 to 0.07%, 0 match 2022 alone |
| [Manitoba](./manitoba.md) | 56 | 57 | 57 | 2018 | 2018 | 3.2% | ⚠ one absent (**The Pas-Kameesak**); vintage `UNTESTED` |
| [Ontario](./ontario.md) | 123 | 124 | 124 | 2018 (Rep. Act 2015 + Far North Act 2017) | same | 1.3% | ⚠ one absent (**Scarborough Southwest**, `ED_ID` 98); vintage check in flight |
| [Quebec](./quebec.md) | 124 | 125 | 125 | 2017 | 2017 (⛔ **127 enacted, in force within weeks**) | 1.4% | ⚠ one absent — **`Chicoutimi`** (`CO_CEP` 918). ★ The only "Chicoutimi" row we hold is a *municipal Saguenay borough* — the near-miss that makes a naive count look fine. ✅ vintage **measured** — 99.887% vs 2017 in-force |
| [New Brunswick](./new-brunswick.md) | 22 | 49 | 49 | **2018 geometry** | 2023-42 (in force 2024-09-19) | ⛔ 55.2% | ⛔ **22 wrong + 27 absent** — 1.32% area error vs superseded set, 124.87% vs in-force. **47% of the province uncovered** |
| [Nova Scotia](./nova-scotia.md) | 55 | **56** | 56 | 2019 | Bill 205, Royal Assent 2026-04-09 | 0.7% | ⛔ **1 absent + 1 reshaped** — Chéticamp missing; **Inverness reshaped, not renamed** → wrong MLA. `jurisdiction_sources.seats` says 55, **is 56** |
| [Prince Edward Island](./prince-edward-island.md) | 26 | 27 | 27 | 2017 | 2017 | ⚠ 28.8% | ✅ vintage **measured** (99.380%). One absent — `Georgetown-Pownal`; its 469.7 km² matches the 470.1 km² coverage gap to 0.09%. ⚠ 28.8% is partly a `boundary_simple` artefact (PE loses 2.10% to simplification vs <0.5% elsewhere) |
| [Newfoundland & Labrador](./newfoundland-labrador.md) | 36 | 40 | 40 | — | — | ⚠ 11.8% | ⚠ four absent; 8 rows resolve to zero officials |
| [Northwest Territories](./northwest-territories.md) | 19 | 19 | 19 | 2013 (in force 2015-10-25) | 2013 — not superseded | 4.8% | ⛔ **count perfect, 5 of 19 MISASSIGNED** — held `Great Slave` covers 30.6% of the real district. ⚠ 2026 commission proposes 22 |
| [Yukon](./yukon.md) | 19 | **21** | 21 | 2015 (in force 2016-10-07) | S.Y. 2024 c.14, in force at 2025 dissolution | 3.0% | ⛔ **stale generation** — Yukon went 19→21; `jurisdiction_sources.seats` of 21 is **correct**. ★ We may hold the last copy of the 2015 map |
| [Nunavut](./nunavut.md) | **0** | 22 | 22 | — | Bill 48, in force 2025-09-22 | ⛔ **100%** | ⛔ **absent entirely** — Open North never published an NU set. ✅ Closable: Elections Nunavut ships a real shapefile |
| **National (provincial layer)** | **665** | **714** | **714** | | | **9.15%** | |

### Municipal

| Province | Sets | Rows | Verdict |
|---|---:|---:|---|
| [Ontario](./municipal-ontario.md) | 48 | 410 | ⛔ only **343 are wards**; 40 stray CSD + 1 CD + a 26-row set with no wards. **Peel duplicated wholesale.** ⚠ ON municipal elections **2026-10-26** |
| [Quebec](./municipal-quebec.md) | 24 | 347 | ⛔ **entire layer one generation stale** — province-wide election 2025-11-02; we hold the 2021 map. ★ Single CKAN sweep fixes all 24 |
| [Alberta](./municipal-alberta.md) | 7 | 53 | ⛔ **Calgary is a third A7 case** — 14/14 count, 2017–21 geometry (14/14 within 2% of old, 6/14 vs current). ⛔ **Grande Prairie County divisions cover 100% of the City** — verified 53.2+25.5+21.3%. ✅ Edmonton correct |
| Atlantic — [NS/NB/PE/NL](./municipal-atlantic.md) | 9 | 83 | ✅ **healthiest block** — zero orphans, zero duplication, 8/9 ward counts correct. ⛔ but **all 9 CSD rows are load-bearing** (hybrid councils). ⛔ PE difficulty 5 — no ward data exists |
| West — [BC/SK/MB](./municipal-west.md) | 6 | 49 | ✅ Winnipeg correct (1 absent: Elmwood–East Kildonan). ⚠ **Regina vintage INCONCLUSIVE — do not load.** ⛔ Saskatoon has no verifiable primary source. ✅ BC at-large is **statutory** (Local Government Act) — 12 zero-ward rows are correct |
| **Total** | **92** | **942** | ⛔ Verified live: a PIP at Mississauga Civic Centre returns **4 overlapping polygons** |

★ **The `census-subdivisions` contamination is ~4× larger than first briefed** — not 17 uses
nationally but **62 of 72 ON/QC sets**, each carrying one whole-municipality polygon filed
inside the ward set. Every municipal lookup returns a set, not an answer, and
`lookupBoundariesAtPoint` picks non-deterministically among them.

## Known blockers

- ⛔ **★ Open North's Represent API is DOWN and has been since at least 2026-08-07.** `represent.opennorth.ca` serves a Let's Encrypt certificate issued to `CN=represent-tempeh.opennorth.ca` (hostname mismatch) that **expired 2026-08-07**; ignoring TLS entirely, the origin returns **HTTP 502** from `nginx/1.10.3 (Ubuntu)`. Impact: `resolvePostcode()` catches the `fetch` throw and raises `PostcodeUpstreamError('unavailable')`, so the API degrades gracefully rather than 500ing — **but the stale-while-revalidate net is nearly empty**: `public.postcode_cache` holds **8 postcodes** (6 fresh, 2 served stale). Every other postcode in Canada currently fails the lookup. All roster ingestion (`ingest-mps`, `ingest-mlas`, `ingest-councils`) and `scripts/generate_muni_sets.py` are also blocked. This raises the priority of the whole workstream from "improve accuracy" to "replace a failed dependency", and it means **no agent should plan a re-probe of Represent as a fallback source**.
- ⛔ **Click-through licence agreements.** Elections Ontario confirmed. Hard stop per standing instruction 3.
- ⚠ **Class B "distributed with permission" rows** (NS provincial 55, NT territorial 19, 8 municipalities) have no licence flowing to us. Redistribution via `/api/public/v1/boundaries/*` is unlicensed today.
- ~~⚠ **GeoNB clause II.5 flow-down** is unimplemented on the public API.~~ ✅ **Resolved 2026-08-18 — not a blocker.** The clause comes from a 2012 GeoNB agreement superseded in 2015; current GeoNB downloads carry the flow-down-free GeoNB Open Data Licence v1.0. See [`new-brunswick.md`](./new-brunswick.md) § Terms / Licensing. Two operator sign-off items remain (which attribution string; ratifying the supersession reading), neither of which blocks the NB load.
- ⚠ **205 rows (ON / PE / MB provincial) have no licence provenance** in `represent-canada-data`.
- ⚠ **Nunavut is absent entirely** and cannot be fixed by re-running the current loader — it is a structural consequence of roster-driven boundary ingestion.

---

## Build prerequisites

**★ No GDAL anywhere.** Verified 2026-08-18 on the host, in the `sw-db` container, and in the `scanner` container (Python 3.13.15):

| Tool / library | Host | `sw-db` | `scanner` |
|---|---|---|---|
| `ogr2ogr` / `ogrinfo` / `gdalinfo` | ABSENT | ABSENT | — |
| `shp2pgsql` | ABSENT | ABSENT | — |
| `fiona` / `osgeo` / `pyshp` / `geopandas` | ABSENT | — | ABSENT |
| `pyproj` / `shapely` | ABSENT | — | ABSENT |

**But PostGIS 3.4 reports `USE_GEOS=1 USE_PROJ=1`** — so `ST_Transform` works *inside the database*. The build path is therefore: read the shapefile in pure Python → emit WKT/GeoJSON in its native CRS → let PostGIS reproject with `ST_Transform(ST_SetSRID(geom, <native EPSG>), 4326)`. Never `ST_SetSRID` alone; that is the Fort Erie bug.

Research-phase consequences (standing instruction: no conversion, no loading):

- **CRS** — unzip and `cat` the `.prj`; it is plain-text WKT. Record the EPSG code *and* the verbatim projection name.
- **Attribute schema** — parse the `.dbf` header directly: 32-byte file header, then 32 bytes per field descriptor (name = bytes 0–10 ASCII null-padded, type = byte 11). ~20 lines of pure Python. Do not guess field names.
- **GeoJSON** — read the first feature's `properties` object.

Build-phase prerequisites, in order:

1. Fix the four read paths missing `effective_to IS NULL` — **before** any cutover.
2. Add a GIST index on `constituency_boundaries.boundary`.
3. Add `authority` / `authority_district_id` + the unique constraint; backfill the 457 already-authoritative rows.
4. Make the simplify tolerance feature-size-aware so micro-districts keep a `boundary_simple`.
5. Make loaders fail the run on a rejected geometry rather than logging the row and continuing.
6. Add `pyshp` to the scanner image (pure Python, no binary dependency) or write the `.shp` polygon reader; `shapely`/`pyproj` are not needed because PostGIS does the geometry work.
7. Add the orphan assertion to scheduled telemetry.

---

## Handoff register — consolidated

**99 handoff items were raised across 18 dossiers.** Triaged here by what they need, so the
operator has one place to act from. Detail stays in each dossier's
`## Research-handoff items`.

### A. Blocks work until a human acts

| # | Item | Jurisdiction | Why it blocks |
|---|---|---|---|
| A1 | ⛔ **Email Elections Nova Scotia for licence terms.** Their only machine-readable surface is an internal AGOL service with `licenseInfo: null`; the NS open-data portal has no provincial electoral product. Research cannot unlock this. | NS | No open route exists at all |
| A2 | ⛔ **No open licence — decide internal-only vs. pursue permission.** SK publishes bare copyright with no terms page (404); MB publishes "All rights reserved" + disclaimer. If only one agency is contacted, make it MB — an affirmative reservation beats silence. | SK, MB | Redistribution not cleared |
| A3 | ⛔ **Pin the 2025 Yukon dissolution date.** Every Yukon government URL returns Cloudflare 403. Bounded to 2024-11-21 < d < 2025-11-03, likely early October. **One browser page load fixes it.** ⚠ Do not substitute the assent date — that asserts the 21-district map governed for 11 months when Yukon had 19 members. | YT | Blocks the YT build |
| A4 | **Accept (or decline) the Elections Ontario "Open Use Data Product Licence Agreement."** Genuinely open — commercial use and redistribution explicit, no attribution clause. No agent may click "I Agree". ⚠ Clause 2 says acceptance is by "any use whatsoever", so the button may be navigation rather than contract formation — operator's call. | ON | Route A geometry for the pilot cutover |
| A5 | **Accept or reject the NB supersession reading** (that the 2012 flow-down does not bind data taken from GeoNB today). A legal characterisation no agent should finalise. Fallback is cheap and identical in action. | NB | Low stakes, but unresolved |

### B. Live defects in production, independent of the build

| # | Item | Evidence |
|---|---|---|
| B1 | ⛔ **NWT returns wrong MLAs today.** 5 of 19 districts misassigned; held `Great Slave` covers 30.6% of the real district, 69.3% of it sits inside held `frame-lake`. Fix is an in-place geometry update — no re-key, no FK moves. | Measured, [`northwest-territories.md`](./northwest-territories.md) |
| B2 | ⛔ **We are serving 55 NS boundaries publicly with no licence.** Survived the 2026-06-02 public-dump teardown because the boundaries endpoints stayed live. Options: leave pending, or suppress NS from the public endpoints (a service change). | [`nova-scotia.md`](./nova-scotia.md) |
| B3 | ⛔ **Municipal lookup returns a set, not an answer.** Verified: Mississauga Civic Centre → 4 overlapping polygons (ward twice under incompatible IDs, city CSD, Peel census *division* at 1,256 km²). `lookupBoundariesAtPoint` picks non-deterministically. | Verified live by the coordinator |
| B4 | ⚠ **Five NB MLA rows carry HTML-entity-encoded names** duplicating five clean rows — 55 active for 49 seats. Invisible today only because 27 NB districts return nothing. **Must be cleaned before the boundary cutover**, or fixing boundaries surfaces five double-MLA districts and reads as a regression. | Verified by the coordinator |
| B5 | ⚠ **`jurisdiction_sources.seats` is wrong for NS** (55, should be 56 since 2026-04-09) and `last_verified_at` is false comfort — `refresh-coverage-stats` bumps the timestamp without validating seat counts. | Verified by the coordinator |
| B6 | ⚠ **Doly Begum has two active `politicians` rows**; belongs to the duplicate-politician audit, not here. | Verified by the coordinator |

### C. Cross-cutting decisions — settle once, before the first loader

| # | Decision | Raised by |
|---|---|---|
| C1 | **A French-name column on `constituency_boundaries`.** MB publishes `ED_French`, federal ships `ED_NAMEF`, NB has 20 distinct French names, QC needs it. Nowhere to put it today; we currently discard it. | MB, federal, NB, QC |
| C2 | **`boundary_kind` must be three-valued** — `district` / `borough` / `municipality`. Quebec's arrondissement mayors are real elected officials in our data. Speccing from Ontario alone yields two values and an immediate re-open. | municipal-QC |
| C3 | **A GIST index on `constituency_boundaries.boundary`.** Only `boundary_simple` and `centroid` are indexed, yet every PIP uses full `boundary` — a seq scan over ~1,900 MultiPolygons per lookup. Worth doing regardless of this project. | impact |
| C4 | **Should the lookup return "we don't know" rather than nothing?** Falls out of the measurement: 33–71% of FSAs cross a federal riding, and rural FSA fallback is only 68.46% accurate. Silently picking one is the failure mode we are trying to remove. | geocoding, impact |
| C5 | **Dash normalisation** (em-dash vs hyphen in district names) is cross-cutting, not per-jurisdiction. | QC |
| C6 | **Person-ID columns are a separate migration** from boundary work — `ourcommons_person_id` (federal), `yt_mla_slug`, SK `Constitu_1`. Different problem, no shared failure modes; coupling them makes the boundary cutover wait on roster scraping. | federal, YT, SK, X2 |

### D. Redistributions already in flight — the build must absorb these

| Jurisdiction | Status | Deadline pressure |
|---|---|---|
| **Ontario municipal** | Ward changes by council by-law; 6 of 48 sets have documented active reviews | ⚠ **Elections 2026-10-26 — about two months out.** Loading ON wards now without a scheduled post-election re-harvest guarantees confident-wrong answers from late October |
| **NWT** | 2026 commission reported 2026-02-27, proposes **22** districts | Before the 2027-10-05 election |
| **Alberta** | 2026 commission reported 2026-03-23, proposes **89** divisions | Next fixed-date election 2027; watch for an 89-division layer on the GoA service |
| **Newfoundland & Labrador** | A new commission is due **this calendar year** | Raises NL's priority |
| **Quebec municipal** | Province-wide election already happened **2025-11-02** | Already stale — single CKAN sweep fixes all 24 sets |
| ⛔ **Quebec provincial — the most time-critical item in the project** | *Loi visant à assurer la représentation effective des électeurs* (2026, c. 15), assented **2026-06-12**, takes effect at the end of the 43rd legislature. **125 → 127 districts — but measured, only 72 of 127 carry through unchanged, so it is a full replacement.** Both maps staged | ⛔ **Fixed-date general election 2026-10-05 — dissolution is imminent.** Loading the wrong generation in *either* direction is a live risk right now, and the window is weeks |
| **PEI municipal** | Votes **2026-11-02** | 2.5 months out |

## Source-URL verification sweep (2026-08-18)

All **182** unique external URLs across the 18 dossiers were re-checked by the coordinator
after the agents finished, with a ranged-GET fallback for hosts that reject `HEAD`.

| Result | Count | Reading |
|---|---:|---|
| ✅ Reachable | **159** | 152 clean on `HEAD`; **7 respond only to `GET`** — the `HEAD`-lies trap, confirmed in the wild |
| 📄 Template placeholders | 5 | `{CODE}`, `<id`, `<PR` etc. — documented URL templates, correctly not resolvable |
| 🔒 WAF / Cloudflare 403 | 8 | All Yukon government hosts plus `gov.nu.ca/en/open-data` — matches the dossiers' blocker notes |
| ⛔ Genuine 404 | 7 | Recorded below |
| ↩ POST-only (405) | 2 | The two BC LIMS GraphQL endpoints — correct behaviour, not a failure |
| ⛔ HTTP 500 | 1 | `mapservices.gov.yk.ca/.../MapServer/12` — ★ **independently confirms the Yukon 2015 layer was overwritten in place**, and that our exported copy may be the last one |

**The 7 genuine 404s**, all recorded in their dossiers as dead ends:
`elections.gov.nl.ca` × 3 (two 2011-distribution archives — note the upstream's own
`Distibution_2011.zip` typo — plus `Shapefile.zip`); `elections.sk.ca/electoralevents/`;
`electionsnb.ca/.../provincial-electoral-districts.html`;
`electionsquebec.qc.ca/cartes-electorales/anciennes-cartes-electorales-du-quebec/`;
and two `open.canada.ca` dataset IDs (delisted Yukon mirrors).

⚠ Per ruling **A11.1**, a 404 is evidence about the *URL*, not about the file — several of
these should get a Wayback CDX sweep before anyone concludes the data is gone. That
technique already recovered two generations written off as unobtainable.

## Status

- [x] Directory + conventions established (2026-08-18)
- [x] Cross-cutting geocoding research — open-licence path found (StatCan NAR)
- [x] ★ Measured user impact — 9.15% no answer, 12.61% any error over 6 measurable jurisdictions
- [x] `constituency_id` reconciliation strategy decided — option (d), authority columns + per-jurisdiction cutover
- [x] Federal + all 10 provinces + all 3 territories dossiers complete (14/14)
- [x] Municipal Ontario + Quebec + Atlantic dossiers complete
- [x] Staging integrity verified — 19 `PROVENANCE.md`, 94 staged files, 2.1 GB of the 8 GB budget, **49/49 quoted sha256 values match files on disk** (2026-08-18)
- [x] Municipal Alberta + West dossiers complete — **21/21, corpus complete** (2026-08-18)
- [x] Coverage matrix consolidated
- [x] Licence matrix consolidated from all 19 fragments (2026-08-18) — ✅ 14 sources cleared, ⛔ 4 provinces with no licence route
- [x] Handoff register consolidated — 99 items triaged into A/B/C/D
- [x] Parent index updated ([`../README.md`](../README.md))
- [x] `_matrix/` fragments — 19 of 20; only `impact` outstanding (2026-08-18)
- [x] Source-URL re-verification sweep — 159/182 reachable, 7 genuine 404s (2026-08-18)
- [x] `CLAUDE.md` repo-map bullet updated to mention `cities/` and `boundaries/` (2026-08-18)
- [x] `docs/plans/sovereignty-runtime-deps.md` row 7 appended (2026-08-18) — original PCCF nomination kept struck-through with why it was wrong, per that file's audit-trail rule
- [ ] Build plan written — **deliberately out of scope for this research phase**

## Editing convention

Same as the provincial and municipal dossiers ([`../README.md`](../README.md) "Editing convention"): **one fact in one file.** Cross-cutting findings — methodology, licence classes, the reconciliation strategy, traps that span jurisdictions — live here. Per-jurisdiction findings live in the dossier. When you complete or change something, update your dossier's `## Status` checkbox list *and* your row in the Licence and Coverage matrices above.

Superseded findings are **struck through, not deleted**. `UNTESTED — probe during build` beats a plausible invention. If you could not crack a jurisdiction, say so in your status snapshot — no silent omissions.
