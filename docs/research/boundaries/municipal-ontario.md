# Municipal Ontario — Electoral Boundary Research

> Standalone boundary dossier for Ontario municipal wards — **48 source sets / 410 rows**, the
> largest municipal block we hold. Cross-cutting context (methodology, licence matrix,
> reconciliation strategy) lives in [`overview.md`](./overview.md); my matrix rows are in
> [`_matrix/municipal-ontario.md`](./_matrix/municipal-ontario.md).
> This dossier owns **boundaries only**. Transcript/roster research for the individual cities
> lives in [`../cities/toronto.md`](../cities/toronto.md), [`../cities/ottawa.md`](../cities/ottawa.md),
> [`../cities/hamilton.md`](../cities/hamilton.md) and [`../cities/mississauga.md`](../cities/mississauga.md).

**Agency:** none — each municipality is its own boundary authority under the *Municipal Act, 2001* s. 222 | **Sets held:** 48 | **Rows held:** 410 | **Real ward polygons:** 343 | **Redistribution trigger:** council by-law, discretionary, appealable to the Ontario Land Tribunal within 45 days

**Status snapshot (2026-08-18):** ⛔ **The row counts are not what they appear, and the defect is structural rather than per-city.** Of 410 rows, only **343 are actual ward polygons**. The rest are whole-municipality or whole-region stand-ins: **40 stray `census-subdivisions/` rows sitting *inside* named ward sets**, 1 stray `census-divisions/` row, and a 26-row `census-subdivisions` set that contains no wards at all. ★ **This is not the 17-uses-nationally fallback described in the brief — 40 of the 48 ON sets are individually contaminated**, each with exactly one municipality polygon bundled in beside its wards. ⛔ **Consequence, measured not inferred: every municipal point-in-polygon lookup returns 2–4 overlapping matches.** A point at Toronto City Hall matches both `toronto-wards-2018/spadina-fort-york` and `census-subdivisions/3520005`; a point in Mississauga matches **four** polygons across two sets. ⛔ **Peel is duplicated wholesale** — all 27 Brampton/Caledon/Mississauga wards exist twice, once in `peel-wards` and once in the per-city sets, under two incompatible ID schemes, which is the entire explanation for the 12 ON "boundaries with zero matching official". ⚠ Two sets named `*-wards` contain **zero wards** (`lasalle-wards`, `whitchurch-stouffville-wards`). ✅ Sourcing is easy where it matters — Toronto publishes all four of its ward models on CKAN — but ⚠ **Ontario has no provincial federation**: it is ~40 separate ArcGIS Hub tenancies, which is why this dossier is organised by platform family rather than by city.

---

## Platform families

Ontario is the **fragmented** case. There is no `donnees.quebec`-style federation and no
provincial ward layer — the Ontario GeoHub carries municipal *boundaries* but not *wards*,
because wards are created by local by-law and never centrally registered. Practical
consequence for the build: **~40 separate endpoints, ~40 separate licences**, and no single
sweep. Grouping them:

**Family A — ArcGIS Hub / ArcGIS Open Data (the large majority).** Most Ontario cities of any
size run an Esri tenancy that exposes wards as a FeatureServer with `/query?f=geojson`.
Observed publishers in this class during probing include `BramptonMaps`, `WhitbyGIS`,
`COBGeomatics` (Burlington), and the Ottawa/Hamilton/Mississauga portals. **Difficulty 1–2**
per city: the pattern is uniform (`.../FeatureServer/0/query?where=1=1&outFields=*&outSR=4326&f=geojson`),
so one generic ArcGIS harvester handles the whole family — the work is *discovering* the 40
service URLs, not parsing them. ⚠ A global Hub keyword search for "Ward Boundaries" is
useless: it returns Nigeria, South Africa, and Ohio ahead of Ontario. Discovery has to be
per-municipality, seeded from each city's open-data landing page.

**Family B — CKAN (a small minority, but it includes Toronto).** `open.toronto.ca` runs CKAN
at `ckan0.cf.opendata.inter.prod-toronto.ca/api/3`. ★ Its `city-wards` dataset is the single
best municipal boundary source in this dossier: it carries the **25-ward model (current), the
44-ward model, and the 47-ward model** in one package, in GeoJSON / SHP / GPKG / CSV across
three CRSs (4326, 2945, 2952). That is current *and* two prior generations from one endpoint —
exactly what the temporal `constituency_boundaries` design wants, and rare. Toronto also
publishes `wards-and-elected-councillors`, a combined boundary+roster layer.

**Family C — no machine-readable ward source (the at-large municipalities).** Not a gap; see
the `census-subdivisions` section. These councils have no wards to publish.

⚠ **Licence heterogeneity is the real ON risk, not access.** Each municipality sets its own
terms. Toronto's CKAN reports `license_title: None` / `"License not specified"` on the ward
datasets — the Open Government Licence – Toronto applies in practice but is **not asserted in
the metadata**, so it cannot be machine-harvested. Multiply that ambiguity by ~40 publishers.
`UNTESTED — probe during build`: no per-city licence audit was attempted here; at ~40
municipalities that is a build-phase task, and it is the reason the licence matrix row for ON
is marked mixed rather than clear.

## ⛔ The `census-subdivisions` contamination — 40 of 48 sets

This is the headline structural finding and it is broader than the brief anticipated.

**Shape of the defect:** almost every named ward set contains **exactly one** extra row whose
`constituency_id` begins `census-subdivisions/` (a 7-digit StatCan CSD code) rather than the
set's own prefix. It is the whole-municipality polygon, sitting in the same `source_set` as
that municipality's wards.

```
ON | ajax-wards | ajax-wards/ward-1            | Ward 1 | 10.775
ON | ajax-wards | ajax-wards/ward-2            | Ward 2 | 32.166
ON | ajax-wards | ajax-wards/ward-3            | Ward 3 | 24.804
ON | ajax-wards | census-subdivisions/3518005  | Ajax   | 67.717   ← not a ward
```

**Tally for Ontario:** 410 rows total = **343 real ward polygons** + 40 stray CSD rows + 1
stray CD row (`census-divisions/3521`, Peel) + a 26-row `census-subdivisions` set (23 CSD + 3
CD) that contains no wards whatsoever.

⛔ **Why it matters more than a tidiness complaint.** The CSD polygon **geometrically contains**
every ward in its own set, so a point-in-polygon lookup matches both. Measured directly:

| Test point | Matching municipal polygons | What matched |
|---|---:|---|
| Toronto City Hall | **2** | `toronto-wards-2018/spadina-fort-york` + `census-subdivisions/3520005` |
| Montréal downtown | 2 | (see [`municipal-quebec.md`](./municipal-quebec.md)) |
| Québec City | 3 | district + borough + CSD |
| **Mississauga** | **4** | `mississauga-wards/ward-4` + `peel-wards/mississauga-ward-4` + `census-subdivisions/3521005` + `census-divisions/3521` |

So "who represents me" on the municipal layer currently returns a *set*, not an answer, and
nothing in the schema distinguishes the ward from its container. Any consumer taking the first
row gets an arbitrary result.

★ **But the CSD rows are not junk — they are load-bearing for at-large councils**, and
deleting them indiscriminately would destroy real coverage. They carry officials:
`census-subdivisions/3537034` (LaSalle) has **7** councillors attached;
`census-subdivisions/3519044` (Whitchurch-Stouffville) has 7;
`census-subdivisions/3526047` (Niagara-on-the-Lake) has **12**.

**Recommended fix:** do not delete. Introduce an explicit tier — a `boundary_kind` column
(`ward` / `municipality` / `region`) or, cheaper and schema-free, **split the CSD rows out into
their own `source_set`** so the ward sets contain only wards. Then have the municipal PIP
resolver prefer the smallest matching polygon, or filter to `boundary_kind='ward'` and fall
back to `municipality` only when no ward matches. That single rule fixes the multi-match
problem for at-large and warded councils simultaneously.

### At-large vs genuine gap — the two zero-ward sets

Both are named `*-wards` and contain only a municipality polygon, which reads identically in
the row counts. They are opposite cases:

- ✅ **`lasalle-wards` (LaSalle, ON — CSD 3537034) — legitimate, no data can exist.** LaSalle
  elects a Mayor, a Deputy Mayor and **five councillors at large**; there are no wards. Our 7
  officials correctly hang off the CSD polygon. **Nobody should hunt for a LaSalle ward file.**
  ⚠ The set *name* is the problem — `lasalle-wards` implies LaSalle has one ward. Rename to
  something honest (`lasalle-at-large`) or fold into the `census-subdivisions` set.
- ⛔ **`whitchurch-stouffville-wards` (CSD 3519044) — a genuine gap.** The Town has **six
  wards**, three rural and three in the Community of Stouffville, each returning one
  councillor, and **new ward boundaries took effect for the October 2022 election**. We hold
  none of them; all 7 officials are collapsed onto the municipality polygon. A real ward file
  exists and should be sourced.

⚠ **The general triage rule:** a CSD row with **multiple** officials attached is an at-large
council (correct); a CSD row in a set that *also* has ward rows is contamination (remove);
a CSD-only set for a municipality that has wards is a gap (source it). ★ **A province-wide
answer key exists** — AMO publishes *"2022 Municipal Election — Municipalities At Large, Ward,
or Both"* at https://www.amo.on.ca/sites/default/files/assets/DOCUMENTS/Elections/Municipal/2022MunicipalElectionMUNICIPALITIESAtLargeWardorBoth.pdf — which classifies every Ontario
municipality. That single PDF resolves the at-large-vs-gap question for all 48 sets and should
be the first thing the build phase reads. ⚠ It is keyed to 2022; municipalities that switched
since would need re-checking.

## ⛔ Peel — 27 wards held twice under incompatible IDs

`peel-wards` (31 rows) is a **regional** set that re-states every lower-tier ward:

- 1 × `census-divisions/3521` (Peel Region, 1,256 km²)
- 3 × `census-subdivisions/` (Mississauga, Brampton, Caledon)
- 27 × `peel-wards/` real wards = **10 Brampton + 6 Caledon + 11 Mississauga**

Those same 27 wards also exist in `brampton-wards` (10), `caledon-wards` (6) and
`mississauga-wards` (11) — the counts match exactly. ★ **Complete duplication**, differing only
in ID convention: `brampton-wards/ward-3` vs `peel-wards/brampton-ward-3`.

★ **This is the whole explanation for Ontario's 12 orphan ward polygons**, and the answer to
the brief's stale-geometry-vs-stale-roster question is **neither**:

| Set | Orphan ward rows |
|---|---:|
| `peel-wards` | 9 (Brampton 1, 2, 4, 7, 9; Caledon 1, 2, 5, 6) |
| `brampton-wards` | 3 (Wards 5, 6, 7) |

The councillors exist and are current — they are just attached to the *other* copy. Directly
observed: `Martin Medeiros` sits at both `brampton-wards/ward-3` and `peel-wards/brampton-ward-3`;
`Pat Fortini` at both `.../ward-8` variants. ★ And the decisive detail — **`Paul Vicente` is at
`brampton-wards/ward-1` in one set and `peel-wards/brampton-ward-5` in the other.** That is not
an error: **Brampton pairs its wards**, with regional councillors representing two wards each
(1&5, 3&4, 7&8, 9&10) and city councillors representing pairs as well. Each of the two ingests
picked a *different* ward from the pair to hang the councillor on, so each set orphans the ward
the other one used.

**Recommendation:** retire the `peel-wards` duplicates and keep the per-city sets, which use
the cleaner `ward-N` convention matching how Brampton, Caledon and Mississauga name their own
wards. Keep exactly one row for Peel Region itself, moved to the region tier. ⚠ Then model
Brampton's paired representation explicitly — a councillor covering Wards 1 and 5 needs two
rows or a many-to-many, and collapsing it to one ward will keep producing phantom orphans
whichever set survives.

## ★ Two-tier duplication — prediction tested, and refined

My Atlantic dossier proposed that *duplication risk tracks two-tier governance, not amalgamation
history*, and predicted Ontario's surviving two-tier regions — **Niagara, Waterloo, Lambton** —
should show Peel-shaped duplication. **Tested 2026-08-18. The prediction is refuted for all
three, and the corrected rule is better.**

Counting ward polygons that fall inside each `census-divisions/` region polygon:

| Region | km² | Ward polygons inside | Distinct sets | Exact duplicates |
|---|---:|---:|---:|---:|
| Peel | 1,256 | 54 | 4 | **16** |
| Waterloo | 1,385 | 40 | 7 | **0** |
| Niagara | 1,884 | 24 | 5 | **0** |
| Lambton | 3,036 | 0 | 0 | 0 |

Niagara and Waterloo *are* two-tier — Niagara holds Fort Erie, Grimsby, Lincoln, St. Catharines
and Welland; Waterloo holds Cambridge, Kitchener, North Dumfries, Waterloo, Wellesley, Wilmot
and Woolwich — yet neither has a single duplicated ward. Lambton has a region polygon and no
ward sets beneath it at all.

★ **Why Peel is different, and the corrected rule.** The distinguishing feature is not the
governance structure but whether **the upper tier has its own boundary set in addition to the
lower-tier sets**. Open North published a `peel-wards` set restating all 27 lower-tier wards;
it published no `niagara-wards` or `waterloo-wards`. So:

> **Duplication risk tracks whether an upper-tier region has its own ward set alongside its
> lower-tier municipalities' sets — not two-tier governance, and not amalgamation history.**

⓵ That is a strictly better rule because it is **directly testable in SQL** with no governance
knowledge: look for a `source_set` whose members' geometries are contained by another set's, or
just run the duplicate-geometry query below. Two-tier governance was a useful *heuristic* for
where to look — it correctly flagged Peel and correctly cleared the amalgamated single-tier
cities — but it over-predicts, and the geometry test is decisive.

### ⚠ Build-phase trap: `ST_Equals` catches only 16 of Peel's 27 duplicates

The exact-equality query finds **16 duplicate pairs — 10 Brampton, 6 Caledon**. It finds **zero
for Mississauga**, even though `mississauga-wards` and `peel-wards/mississauga-ward-*` both hold
all 11 wards. They are near-identical but not vertex-identical:

| Pair | `mississauga-wards` km² | `peel-wards` km² | Overlap | `ST_Equals` |
|---|---:|---:|---:|---|
| ward-4 | 12.14 | 12.14 | **99.90%** | ✗ |
| ward-10 | 14.91 | 14.93 | 99.94% | ✗ |
| ward-1 | 23.34 | 23.56 | 99.65% | ✗ |
| *(all 11)* | — | — | **99.65–99.94%** | ✗ |

Two different digitisations of the same wards. ⛔ **A de-duplication pass written around
`ST_Equals` would remove Brampton and Caledon and silently leave Mississauga doubled** — bad,
because the surviving duplication would look deliberate.

### ⛔⛔ …but the obvious fix is worse. Both wrong answers look plausible

My first proposal here was a bare overlap threshold — "≥99% of the smaller polygon". **That is
wrong, and badly so.** Measured against the live ON municipal set:

| Rule | Pairs returned | |
|---|---:|---|
| `ST_Equals` | **16** | ⛔ under-matches — 10 Brampton + 6 Caledon, zero Mississauga |
| overlap ≥ 99% of the smaller | **444** | ⛔⛔ **over-matches catastrophically** |
| overlap ≥ 99% **AND** area ratio 0.95–1.05 | **27** | ✅ exactly right |

**The failure is containment.** A ward is 100% inside its own city's CSD polygon *and* 100%
inside its census division, so "≥99% of the smaller polygon" is **trivially true** for every
ward/container pair in the table. Sample false positives the naive rule returns:

| Pair | % of smaller | Area ratio |
|---|---:|---:|
| `welland-wards/ward-2` vs `census-divisions/3526` (Niagara) | 100.00 | **0.0020** |
| `grimsby-wards/ward-1` vs `census-divisions/3526` | 99.83 | **0.0018** |
| `ottawa-wards/rideau-vanier` vs `census-subdivisions/3506008` | 99.70 | **0.0031** |

⛔ **A migration on that rule would delete wards as duplicates of the municipality containing
them** — the mirror image of the `ST_Equals` failure and strictly worse, because it destroys real
coverage instead of merely leaving redundancy. Given the tier contamination documented above puts
a container polygon in 40 of 48 ON sets, it would fire everywhere.

**The area-ratio guard is what rejects containment.** True duplicates are the same ward twice, so
their areas match to within a few percent; a ward and its container differ by 300–700×. With the
guard the query returns exactly **27 — the 16 vertex-identical pairs plus all 11 Mississauga
pairs, and nothing else**, split `mississauga-wards`↔`peel-wards` 11, `brampton-wards`↔`peel-wards`
10, `caledon-wards`↔`peel-wards` 6.

★ **The transferable lesson is that both wrong answers look reasonable in isolation.** `ST_Equals`
returns a clean-looking 16; the bare threshold returns 444, which a reader might rationalise as
"lots of overlap in a dense province". Only running all three side by side shows which is correct
— so **run all three before writing any de-duplication migration.**

Canonical detector:

```sql
WITH pairs AS (
  SELECT a.constituency_id AS a_id, b.constituency_id AS b_id,
         a.source_set AS set_a, b.source_set AS set_b,
         ST_Area(a.boundary::geography) AS aa,
         ST_Area(b.boundary::geography) AS ab,
         ST_Area(ST_Intersection(a.boundary, b.boundary)::geography) AS ai
  FROM constituency_boundaries a
  JOIN constituency_boundaries b ON a.id < b.id
  WHERE a.level = 'municipal' AND b.level = 'municipal'
    AND a.province_territory = b.province_territory
    AND ST_Intersects(a.boundary, b.boundary)   -- keeps the pairwise scan cheap
)
SELECT set_a, set_b, a_id, b_id
FROM pairs
WHERE ai > 0.99 * LEAST(aa, ab)                       -- near-coincident, catches re-digitisation
  AND LEAST(aa, ab) / NULLIF(GREATEST(aa, ab), 0)
      BETWEEN 0.95 AND 1.05;                          -- ⛔ REQUIRED: rejects containment
```

## ⛔ Ruling A6 — sets with a year in the prefix

**`toronto-wards-2018` is the only Ontario violation**, and it is the exemplar the brief names.
Target: **`toronto-wards/<slug>`**, with `2018` moved to `boundaries_version`.

★ Toronto is also the case where A6 pays off most visibly. The city has run **four** ward models
(44 → 47 → 25, plus the 2010 44-ward revision), and Toronto's CKAN publishes three of them
side by side. Under A6 a ward whose name and territory survived a redraw keeps one
`constituency_id` across generations and gains a row per `boundaries_version`; under the current
scheme every redraw would mint `toronto-wards-2026`, `toronto-wards-2030`, and the temporal
query that A6 exists to enable would never work. ⚠ Toronto's 25-ward model is **still current**
(unchanged since 2018), so this is a rename with no geometry change — the cheapest possible
moment to fix it, before the next review forces a second generation into the table.

All other 47 ON sets are already year-free and A6-compliant as prefixes. ⓘ They are *not*
compliant in spirit, because `boundaries_version` is uniformly the uninformative string
`'current'` across all 410 rows — so no ON set records which generation it holds. That has to
be populated as part of any A6 migration or the constraint carries no information.

## Amalgamation and ward-review cadence

★ **This is the fastest-decaying jurisdiction class in the whole corpus, and structurally so.**
Under **s. 222 of the *Municipal Act, 2001***, a municipality may by by-law "divide or redivide
the municipality into wards or dissolve the existing wards". Two features make this unlike
provincial redistribution:

- **No mandated cycle and no independent commission.** A review is initiated at council's
  discretion, or triggered by a petition of electors. There is no equivalent of a decennial
  boundaries commission, so changes are unpredictable in timing and can land in any year.
- **A 45-day appeal window to the Ontario Land Tribunal** under s. 222(4), open to any person
  or agency. So the in-force date is not the by-law date — it is the by-law date plus a
  possible OLT proceeding. ⚠ Under ruling A2 the legal in-force date is what we store, and for
  Ontario wards that date is **per-municipality and frequently litigated**. There is no
  statutory instrument to cite the way S.Y. 2024 c. 14 was citable for Yukon; the citation is a
  numbered municipal by-law (e.g. Ottawa's *Ward Boundaries and Council Composition By-law No.
  2021-3*).

**Practical cadence observed:** reviews cluster in the year or two before a municipal election.
Ontario municipal elections are fixed — the fourth Monday of October every four years, so
**2022-10-24, 2026-10-26, 2030**. ⚠ **A 2026 general municipal election falls on 2026-10-26 —
roughly two months from now** — and municipalities that completed reviews in 2024–26 will have
new wards in force for it. Our entire ON layer carries `effective_from = 2023-01-01` (an Open
North mirroring artifact, not a legal date) and `boundaries_version = 'current'`, so **we have
no way to tell which sets are about to be superseded.** Documented active or recent reviews
found while probing: Pickering, Haldimand County, Grimsby, New Tecumseth, Loyalist, and
Whitchurch-Stouffville (effective 2022). That is 6 of our 48 sets with known movement, from a
non-exhaustive search.

**Recommendation:** treat ON municipal boundaries as requiring a **re-harvest immediately after
2026-10-26**, not a one-time build. This is the class where a "load it once" approach guarantees
a stale-and-confident lookup within months.

## Postal-code correspondence

⛔ None. No Ontario municipality found in this pass publishes a postal-code → ward
correspondence, and there is no provincial equivalent. Our point-in-polygon path is the right
mechanism and needs nothing ON-specific — **but only once the multi-match defect above is
fixed**, since PIP is precisely the mechanism that is currently returning 2–4 answers.

## Terms / Licensing

- **No single licence — ~40 municipal licensors.** This is the defining licence characteristic
  of the Ontario block and the reason its matrix row is *mixed*.
- **Toronto:** `open.toronto.ca` CKAN reports `license_title: None` and `"License not
  specified"` on both `city-wards` and `wards-and-elected-councillors`. ⚠ The Open Government
  Licence – Toronto governs the portal in practice, but because it is **absent from the dataset
  metadata** it cannot be harvested programmatically and was not read in this pass. Recorded as
  unresolved rather than assumed.
- **ArcGIS Hub publishers:** most Ontario municipal Hub tenancies attach an Open Government
  Licence modelled on OGL–Canada 2.0, but the licence string is per-tenant and several report
  `license: custom`. Not audited here.
- **No click-through gate encountered** on any Ontario endpoint reached during this pass. ⓘ
  Unlike Elections Ontario at the provincial level (confirmed click-through per the brief), the
  *municipal* portals are open. Provincial and municipal Ontario behave very differently.
- **Verbatim clause quotes:** ⛔ none captured. With ~40 licensors and no federation, quoting
  them is a build-phase audit, not a research-pass deliverable. Flagged as a handoff item.

## Rate limits / auth

- **Auth:** none on any endpoint reached.
- **Rate limits:** none observed. Toronto CKAN and ArcGIS Hub both answered without throttling.
- ⚠ **ArcGIS `maxRecordCount` matters here in a way it did not for the territories.** Ward
  layers are small (≤ 25 features), so single unpaged queries suffice — but the *polling
  subdivision* layers some cities publish alongside them run to thousands of features and will
  silently truncate at `exceededTransferLimit`. If the build ever harvests those, paginate.
- ⚠ **Toronto's CKAN datastore dump URL** (`/datastore/dump/<id>`) returns a different
  serialisation from the resource `download/` URLs. Prefer the explicit
  `city-wards-data-4326.geojson` resource; the dump endpoint is not CRS-labelled.

## Staged files

Staging root `data/boundaries/municipal-ontario/`, manifest at
`data/boundaries/municipal-ontario/PROVENANCE.md`. **1.5 MB.** ⚠ **Representative, not
exhaustive** — with 48 sets across ~40 publishers, staging every municipality is a build-phase
harvest, not a research deliverable. Toronto was staged because it is the largest single set,
the A6 exemplar, and the only ON publisher offering multiple generations.

| Path | Bytes | What it is |
|---|---:|---|
| `current/toronto-city-wards-4326.geojson` | 1,148,140 | ★ Toronto 25-ward model, EPSG:4326, from `open.toronto.ca` CKAN. The current set and the A6 exemplar. |
| `prior/toronto-44-ward-model-2010-wgs84.zip` | 307,071 | Toronto 44-ward model (May 2010), WGS84 shapefile. Demonstrates that the prior generation is retrievable — contrast Yukon, where it is not. |

**Not staged, deliberately:** the 47-ward model and the MTM/NAD27 CRS variants (same content);
the ~39 other municipalities (build-phase harvest); polling subdivisions (out of scope).

## Reconciliation with `constituency_boundaries`

**What we hold:** 48 `source_set` values, **410 rows**, `level='municipal'`,
`province_territory='ON'`. Every row carries `boundaries_version = 'current'` and
`effective_from = '2023-01-01'` — ⚠ both are Open North mirroring artifacts, not facts. No ON
set records a real generation or a real in-force date.

**Composition (counted, not estimated):**

| | Rows |
|---|---:|
| Real ward polygons | **343** |
| Stray `census-subdivisions/` inside ward sets | 40 |
| Stray `census-divisions/` inside ward sets | 1 |
| The `census-subdivisions` set (23 CSD + 3 CD, no wards) | 26 |
| **Total** | **410** |

Of the 343 real ward polygons, **27 are duplicates** (the Peel/per-city overlap), so the true
distinct ward count is **316**.

**Per-set detail.** `Real` = rows whose `constituency_id` prefix matches the `source_set`;
`CSD/CD` = whole-municipality or whole-region rows; `Orph` = real ward rows with no matching
official.

| Set | Rows | Real | CSD/CD | Orph | Notes |
|---|---:|---:|---:|---:|---|
| `ajax-wards` | 4 | 3 | 1 | 0 | ✅ **corrected 2026-08-27 — Ajax has 3 wards, not 4.** AMO 2026 lists `Councillor, Ward 1-3` AND `Councillor (Regional And Town), Ward 1-3`: each ward elects both a local and a regional councillor, and the six labels were read as six wards. Held data was already complete. |
| `belleville-wards` | 3 | 2 | 1 | 0 | ⚠ Belleville has 6 wards — 2 held |
| `brampton-wards` | 10 | 10 | 0 | 3 | ✅ clean of CSD; orphans = Peel duplication |
| `brantford-wards` | 6 | 5 | 1 | 0 | |
| `burlington-wards` | 5 | 4 | 1 | 0 | ⚠ Burlington has 6 wards — 4 held |
| `caledon-wards` | 6 | 6 | 0 | 0 | ✅ clean; duplicated in `peel-wards` |
| `cambridge-wards` | 8 | 8 | 0 | 0 | ✅ clean |
| `census-subdivisions` | 26 | 0 | 26 | 0 | ★ no wards at all — 23 CSD + 3 CD (Lambton, Niagara, Waterloo). Largely legitimate at-large councils |
| `chatham-kent-wards` | 7 | 6 | 1 | 0 | |
| `clarington-wards` | 5 | 4 | 1 | 0 | |
| `fort-erie-wards` | 4 | 4 | 0 | 0 | ✅ clean |
| `greater-sudbury-wards` | 13 | 12 | 1 | 0 | |
| `grimsby-wards` | 4 | 4 | 0 | 0 | ✅ clean; ⚠ active ward/composition review |
| `guelph-wards` | 7 | 6 | 1 | 0 | |
| `haldimand-county-wards` | 7 | 6 | 1 | 0 | ⚠ active ward boundary review |
| `hamilton-wards` | 16 | 15 | 1 | 0 | 15 wards — matches council |
| `kawartha-lakes-wards` | 9 | 8 | 1 | 0 | |
| `king-wards` | 7 | 6 | 1 | 0 | |
| `kingston-wards` | 13 | 12 | 1 | 0 | |
| `kitchener-wards` | 10 | 10 | 0 | 0 | ✅ clean |
| `lasalle-wards` | 1 | **0** | 1 | 0 | ✅ **at-large — legitimate, no ward data exists**. Rename the set |
| `lincoln-wards` | 4 | 4 | 0 | 0 | ✅ clean |
| `london-wards` | 15 | 14 | 1 | 0 | |
| `markham-wards` | 8 | 7 | 1 | 0 | |
| `milton-wards` | 5 | 4 | 1 | 0 | |
| `mississauga-wards` | 11 | 11 | 0 | 0 | ✅ clean; duplicated in `peel-wards` |
| `newmarket-wards` | 7 | 6 | 1 | 0 | |
| `north-dumfries-wards` | 4 | 4 | 0 | 0 | ✅ clean |
| `oakville-wards` | 8 | 7 | 1 | 0 | |
| `oshawa-wards` | 6 | 5 | 1 | 0 | |
| `ottawa-wards` | 25 | 24 | 1 | 0 | 24 wards — matches council. By-law 2021-3 |
| `peel-wards` | 31 | 27 | 4 | 9 | ⛔ **regional duplicate** of Brampton+Caledon+Mississauga |
| `pickering-wards` | 4 | 3 | 1 | 0 | ⚠ active ward boundary review |
| `richmond-hill-wards` | 7 | 6 | 1 | 0 | |
| `sault-ste-marie-wards` | 6 | 5 | 1 | 0 | |
| `st-catharines-wards` | 7 | 6 | 1 | 0 | |
| `thunder-bay-wards` | 8 | 7 | 1 | 0 | |
| `toronto-wards-2018` | 26 | 25 | 1 | 0 | ⛔ **A6 violation**; 25 wards, still current |
| `uxbridge-wards` | 6 | 5 | 1 | 0 | |
| `vaughan-wards` | 6 | 5 | 1 | 0 | |
| `waterloo-wards` | 8 | 7 | 1 | 0 | |
| `welland-wards` | 7 | 6 | 1 | 0 | |
| `wellesley-wards` | 5 | 4 | 1 | 0 | |
| `whitby-wards` | 5 | 4 | 1 | 0 | |
| `whitchurch-stouffville-wards` | 1 | **0** | 1 | 0 | ⛔ **genuine gap** — 6 wards exist, new for 2022 |
| `wilmot-wards` | 5 | 4 | 1 | 0 | |
| `windsor-wards` | 10 | 9 | 1 | 0 | |
| `woolwich-wards` | 4 | 3 | 1 | 0 | |

⚠ **The "Real" column is the number to read, and several are short of the actual council.**
⚠ **Two of these three were not gaps.** Ajax holds 3 of 3 (the "4" double-counted its regional councillors) and Belleville holds 2 of 2 (Ward 1 elects six councillors, which was misread as six wards). Only Burlington was real, at 4 of 6, fixed 2026-08-27. Both corrections came from AMO's 2026 roster. Because the CSD row inflates the
total, `belleville-wards` reads as 3 rows for a 6-ward council and looks merely incomplete
rather than two-thirds missing. ★ **This is the BC defect in municipal form** — plausible row
counts concealing partial ingest — and it argues for auditing *every* set's real count against
its council size, not just the ones flagged here.

**Recommended build shape:**

1. **Separate the tiers.** Move all 41 stray CSD/CD rows out of the ward sets. Either add
   `boundary_kind` or give them their own `source_set`. This alone fixes the 2–4 match problem.
2. **De-duplicate Peel.** Retire the 27 `peel-wards/` ward rows, keep the per-city sets, keep
   one Peel region row at the region tier.
3. **Apply A6** to `toronto-wards-2018` → `toronto-wards/` + `boundaries_version='2018'`.
4. **Populate `boundaries_version` for real** across all 48 sets — currently uniformly
   `'current'`, which carries no information and blocks the temporal design.
5. **Replace `effective_from = '2023-01-01'`** with the per-municipality by-law in-force date
   under ruling A2. ⚠ This is 48 separate by-law lookups with no central register; expect it to
   be the most expensive part of the ON build, and consider whether municipal rows need legal
   dates at the same fidelity as legislative ones.
6. **Audit real-count vs council size** for all 48 using the AMO at-large/ward PDF as the key.
7. **Re-harvest after 2026-10-26.**

## Research-handoff items

- **How should the ward/municipality tier be modelled — new column or new `source_set`?** This
  blocks the fix for the 2–4 match defect and it is a schema decision, not a research one. A
  `boundary_kind` column is cleaner and survives future tiers (region, borough — QC needs the
  latter); a separate `source_set` is zero-migration. **Recommend `boundary_kind`**, because
  [`municipal-quebec.md`](./municipal-quebec.md) independently needs a *third* tier for
  boroughs, and two ad-hoc `source_set` splits will not compose.
- **Do municipal rows need legal in-force dates at ruling-A2 fidelity?** For provinces the
  statutory instrument is citable in one lookup. For Ontario it is 48 municipal by-laws, each
  with a 45-day OLT appeal window that can move the date, and no central register. That is a
  large amount of work for a layer whose consumers mostly want "which ward am I in *now*".
  **I recommend a documented exception**: store the municipal-election date the boundaries
  first governed (2022-10-24 for most current sets) rather than chasing by-law dates, and mark
  the field's provenance honestly. Raising it rather than deciding, since A2 was stated
  without a municipal carve-out.
- **Ontario municipal elections are on 2026-10-26 — about two months out. Who owns the
  re-harvest?** At least 6 of our 48 sets have documented recent or active ward reviews
  (Pickering, Haldimand, Grimsby, New Tecumseth, Loyalist, Whitchurch-Stouffville). Loading the
  current data now without scheduling a post-election refresh guarantees confident-wrong ward
  answers from late October. This is the single most time-sensitive item across both of my
  municipal dossiers.
- **~40 municipal licences are unaudited, and Toronto's is unstated.** No click-through was
  encountered anywhere, and municipal open-data portals are permissive by convention — but
  Toronto's CKAN literally reports `"License not specified"` on the ward datasets, so the
  largest ON set has **no machine-readable licence at all**. Is a per-municipality licence
  audit in scope before the data is used, or is the internal-use case sufficient to proceed on
  convention? I have not assumed either way.
- **Brampton's paired wards need a representation model.** Regional councillors cover two wards
  (1&5, 3&4, 7&8, 9&10). Whichever Peel copy survives de-duplication, a one-councillor-per-ward
  assumption will keep generating phantom orphans. Needs a many-to-many or a deliberate rule.
- **`whitchurch-stouffville-wards` is a real, sourceable gap** — 6 wards in force since October
  2022, zero held. Small and worth fixing in the first build pass.

## Status

> ⚠ **Reconciled 2026-09-01.** The checkboxes below are the **research phase's** record
> (closed 2026-08-18) and several were overtaken by the build — migrations `0064`–`0121`,
> merged to `main` 2026-08-28. An unticked box here is **not** evidence that something is
> still outstanding.
>
> **Live counts: [`PROGRESS.md`](./PROGRESS.md)** (generated by `boundary-progress`).
> **What actually landed:** the migration headers, which are the accurate record.
> This file's job is the *reasoning* — sources, licences, traps, vintage evidence.

- [x] All 48 ON sets inventoried and decomposed by row tier (2026-08-18)
- [x] `census-subdivisions` fallback quantified — **40 of 48 sets contaminated**, far beyond the briefed scope
- [x] At-large vs genuine gap resolved for both zero-ward sets — LaSalle legitimate, Whitchurch-Stouffville a real gap
- [x] Multi-match PIP defect demonstrated by measurement (2–4 polygons per point)
- [x] 12 ON orphan ward rows diagnosed — **neither stale geometry nor stale roster; Peel duplication plus Brampton's paired wards**
- [x] A6 violations identified — `toronto-wards-2018` only
- [x] Two-tier duplication prediction tested on Niagara / Waterloo / Lambton — ⛔ **refuted for all three**; corrected rule is *upper tier has its own ward set*, which is directly SQL-testable
- [x] Peel duplication measured exactly — **27 real pairs**: 16 vertex-identical + 11 near-identical (99.65–99.94%)
- [x] De-duplication detector validated three ways — `ST_Equals` **16** (under), bare ≥99% overlap **444** (over, via containment), **≥99% + area ratio 0.95–1.05 → 27 ✅**. ⚠ My first proposal was the 444 rule; corrected after measurement
- [x] Platform families mapped; representative current + prior staged
- [x] Ward-review cadence established — s. 222, discretionary, 45-day OLT appeal, **next election 2026-10-26**
- [ ] Per-municipality licence audit — ⛔ **not done, ~40 licensors; Toronto's is unstated in metadata**
- [x] Real-count-vs-council-size audit for all 48 sets — ✅ **done 2026-08-27** against the AMO register; see § *Coverage audit against AMO*, below in this file, which this line contradicted for five days. Windsor fixed by `0108`
- [ ] Per-municipality by-law in-force dates — **blocked pending the A2 municipal-exception decision**
- [x] Tier modelling decision — ✅ **settled**: three-valued `boundary_kind` (migration `0061`), `source_set` kept generation-free per ruling A6 with the generation in `boundaries_version` + `effective_from`
- [~] Post-2026-10-26 re-harvest — **partly pre-empted.** Seven 2026 ward maps are already loaded and dormant (Burlington, Chatham-Kent, Haldimand, London, Ottawa, Pickering + Whitchurch-Stouffville); `check-boundary-coverage`'s `pending-flip` reports them, and ⛔ **Chatham-Kent detaches 17 sitting councillors on 2026-10-26**. Roster side is `amo-on:` (`apply-on-municipal-roster`). ⚠ Still needs an owner for the sets *not* pre-loaded

---

## AMO 2026 election API — a province-wide ward-count answer key (2026-08-27)

`municipal-ontario.md` previously named AMO's 2022 at-large/ward **PDF** as the
answer key for which Ontario municipalities elect by ward. There is now a live,
unauthenticated, machine-readable replacement keyed to the 2026 election:

```
https://elections2026.amo.on.ca/api/public/Municipalities        -> 449 municipalities (urlId, name)
https://elections2026.amo.on.ca/api/public/municipality/<urlId>  -> isWard, isAtLarge, tier,
                                                                    upperTierName, population,
                                                                    members[] with positionWard
```

Verified 2026-08-27: HTTP 200, 449 rows, no key required. ⚠ Only the `public/`
prefix is open — `/api/municipality/<id>` without it returns 404.

**It cross-checked 33 of the 35 municipalities staged in this wave.** Ottawa 24,
Mississauga 11, London 14, Windsor 10, Kingston 12, Greater Sudbury 12,
Kitchener 10, Cambridge 8, Oakville 7, Kawartha Lakes 8, Brantford 5, Guelph 6,
Milton 4, Wellesley/Wilmot/North Dumfries 4, Woolwich 3, Whitby 4, Oshawa 5,
Markham 8, Newmarket 7, Vaughan 5, Whitchurch-Stouffville 6, Scugog/Brock/
Uxbridge 5 each — all matching the staged feature counts exactly.

### ⛔ Read `positionWard` carefully — it is not a ward list

The `members[]` array is **seats, not wards**, and the field is free text. Four
distinct traps, all seen in real data:

1. **Non-ward seats are mixed in.** `Mayor`, `Regional Councillor`,
   `Councillor At Large`. Strip them or every count is inflated.
2. **One ward can appear under two position titles.** Ajax lists six labels —
   `Councillor, Ward 1-3` *and* `Councillor (Regional And Town), Ward 1-3` —
   because each ward elects both a local and a regional councillor. **Ajax has
   3 wards, not 6 and not the 4 this dossier previously assumed.**
3. **One label can cover several wards.** Brampton's labels are `1, 5`, `2, 6`,
   `3, 4`, `7, 8`, `9, 10` — five labels, ten wards. Caledon and Clarington mix
   single and paired forms in the same list.
4. **Real typos and whitespace variants.** Thunder Bay carries both `Northwood`
   and `Nortwood`; Burlington has `Councillor (Regional And Town), Ward 6`
   alongside `...(Regional And City), Ward 6`. De-duplicate on a normalised key.

⚠ **`isAtLarge` does not mean "at-large council".** It goes true whenever *any*
seat is elected at large — including the mayor — so Cambridge and Guelph both
report `isAtLarge=true` while being ward councils. Use the labels, never the flag.

### ⛔ It does NOT date a map — a claim retracted 2026-08-27

An earlier version of this section said a staged file matching AMO's 2026 count
while an older file does not is evidence the map is a **future** generation.
**That is wrong, and it was tested and disconfirmed the same day it was written.**

Running AMO against the eight large cities returned 2026 counts of Ottawa 24,
Hamilton 15, Mississauga 11, Brampton 10, London 14, Windsor 10, Kingston 12,
Sudbury 12 — every one **identical to that city's current count**, including the
two cities that have genuinely redrawn for 2026. Ottawa's 2026 map amends six
wards and keeps 24. London's moves 13 of 14 boundaries and keeps 14.

★ The reason is structural, not a quirk of those two. Councils redraw to
**equalise population**, and changing council SIZE is a separate and harder
decision requiring a composition by-law. So a count-preserving redraw is the
common case and a count-changing one is the exception. Chatham-Kent (6→8) and
Haldimand (6→7) are datable this way only because they happened to resize
council at the same time — they are the minority, and generalising from them was
the error.

This is ruling A7 reasserting itself in a new costume: a matching count proves
nothing, and neither does a *changed* count prove what changed. **Only geometry
plus the instrument dates a map.**

### ★ What it IS good for — a coverage audit

AMO independently establishes how many wards each council should have, which is
the answer to this dossier's open item on real-count-vs-council-size across all
48 Ontario sets. It confirmed `windsor-wards` held **9 rows for a 10-ward
council** — a partial ingest nothing else had caught, because no check was
comparing our count against the council's.

### Three further parsing traps

3. ⛔ **Ontario reuses municipality names across tiers.** `Hamilton, Township of`
   is urlId 10173, in Northumberland County; `Hamilton, City of` is 19430. A
   name-substring match on the list endpoint silently grabs the wrong one. Expect
   the same for Kingston, Norwich, Lincoln and others.
4. ⛔ **Ottawa and Kingston put the ward NAME after the number** —
   `Councillor, Ward 1 Orleans East Cumberland`,
   `Councillor, Ward District 1 Countryside`. A rule that strips the non-ward
   seats and then reads a *trailing* number returns **zero wards** for both,
   which reads as an at-large council. Extract the digits following the token
   `Ward` (optionally `Ward District`).
5. ⚠ **AMO normalises names lossily** — diacritics and hyphens stripped,
   sometimes truncated. `Orléans East-Cumberland` becomes `Orleans East
   Cumberland`; `West Carleton-March` becomes `West Carleton`. Safe for counting,
   never for name matching.

### On comparison method — the asymmetry matters

⚠ Hash **inequality** proves nothing: vertex order and coordinate precision
differ between exports of identical geometry, so hashing London's vintages
reported "all different" and was uninformative. But hash **equality is
conclusive** proof of sameness and is worth keeping as a cheap first pass —
Greater Sudbury's `Ward_Boundaries` and `Wards_2018` came back byte-identical
from two different service URLs, which settled its vintage in one step.

⚠ And the area/centroid test has a floor. Ottawa's By-law 2025-5 names **six**
wards; a 0.5%-area / 150 m-centroid threshold clears only **three** of them.
Wards 11, 13 and 21 move by 0.03-0.11% and ≤15 m — indistinguishable from
re-digitisation noise, even though ward 21 is 719 km² so its 0.11% is a real
~0.8 km² transfer. **The test answers "is this a distinct map"; it understates
WHICH wards moved, and systematically misses small transfers into large rural
wards. The by-law is the authority on scope.**

### ⛔ A year in a dataset name is not a generation

City of Waterloo publishes `Wards2010`, `Wards2014`, `PoliticalWards_2018` and
`Wards2022` as four separate FeatureServers with four separate dataset pages.
Measured, **2014 / 2018 / 2022 are the same geometry** — all 7 wards agree to
<0.01% area; only the councillor attribute columns differ. `Wards2010` returns
**HTTP 200 with an empty `features` array**, the same empty-200 trap class as the
BC pcms endpoints.

Ingesting each year-labelled layer as its own `boundaries_version` would
fabricate three Waterloo generations and one empty one. Toronto's
multi-generation CKAN package is genuine; Waterloo's is a publication-cycle
artifact. **Compare geometry before trusting a year label.**

⚠ The correct test is **per-ward area agreement**, not `ST_Equals` and not a file
hash. Vertex order and coordinate precision differ between exports of identical
geometry — hashing the London 2014/2022/2026 files reported "all different" and
proved nothing.

### Corrections to earlier entries in this dossier

- **Belleville is 2 wards, not 6.** AMO lists `Councillor, Ward 1` and
  `Councillor, Ward 2` only. The recorded "Belleville 2/6" gap was not a gap —
  the held data was already complete and the expectation was wrong.
- **Ajax is 3 wards, not 4.** See trap 2 above. The recorded "Ajax 3/4" gap was
  likewise not a gap.
- **Whitchurch-Stouffville is confirmed at 6**, against the single row held. That
  gap is real.

### Coverage audit against AMO — results, 2026-08-27

Ran held live district count vs AMO's 2026 ward count across all 51 live Ontario
municipal sets. This is the audit AMO is genuinely for, and it closes this
dossier's open item on real-count-vs-council-size.

**Held short — a ward we do not have:**

| set | held | AMO 2026 | note |
|---|---|---|---|
| `windsor-wards` | 9 | 10 | ★ fixed 2026-08-27 (migration 0108) |
| `burlington-wards` | 4 | 6 | ★ fixed 2026-08-27 (migration 0109) |
| `markham-wards` | 7 | 8 | staged file has 8 — pending an in-force date |
| `newmarket-wards` | 6 | 7 | staged file has 7 — pending an in-force date |
| `richmond-hill-wards` | 6 | 7 | ✅ **RESOLVED — AMO is wrong, our 6 is right.** Its `members[]` contains both "Michael Shu — Councillor, Ward 6" and "Michael Shiu — Councillor, Ward 8": a candidate-registration data-entry duplicate, one letter and one digit apart. The City's own election pages list Wards 1-6 only. Nothing to load, nothing to chase |
| `chatham-kent-wards` | 6 | 8 | expected: the 2026 redraw, already loaded future-dated |
| `haldimand-county-wards` | 6 | 7 | expected: as above |

**Held excess — PARTLY resolved, and I got Port Colborne wrong first time.**
`lincoln-wards` 4 vs 3 is a real 2026 reduction and our 4-ward data is correct
for the current term. ⛔ **Port Colborne is NOT.** Its wards 1 and 3 were redrawn
by **By-law 6948/94/21** (passed 2021-11-08, "to change the boundaries of ward
one and ward three", appeal deadline 2021-12-23), in force **2022-10-24** — so
our data is stale for the CURRENT term, independently of the 2026 reduction.
Both were 2026 reductions; Lincoln: council-composition and ward-boundary review 2024-25, final
report 2025-06-30, **By-law No. 2025-28** enacted 2025-07-30. Port Colborne:
final report 2025-06-24, Council voted March 2026, provincial regulation
approved May 2026 — three wards (two urban, one rural), council from eight
councillors to six. ★ Reclassify both from "unresolved" to **correct now,
superseded 2026-10-26**, and add them to the post-election re-harvest list
alongside Chatham-Kent and Haldimand.

⚠ **`king-wards` runs the other way**: the staged authoritative file holds 7
wards with named councillors while AMO reports 6. Held is 6. Not loaded until
that is explained — it is the only case in the wave where the *source* exceeds
both AMO and what we hold.

### ⛔ Parsing `positionWard` for a count — four cases, or the audit lies

A first pass reported Brampton as 5 wards, Thunder Bay as 0 and Pelham as 0, all
wrong. The field needs all four of these handled before a count means anything:

1. **Paired labels.** Brampton's five labels `1, 5` / `2, 6` / `3, 4` / `7, 8` /
   `9, 10` are ten wards. Extract *every* integer in the tail, not the first.
2. **Name-based wards.** Thunder Bay's are `Current River`, `McIntyre`,
   `Neebing`… with no numbers at all; Kingston's are `Ward District 1
   Countryside`. A digits-only parser returns zero and the council reads as
   at-large.
3. **Word-numbers.** Pelham's labels are `One`, `Two`, `Three`.
4. **Typos are distinct values.** Thunder Bay carries both `Northwood` and
   `Nortwood`, which counts as 8 wards for a 7-ward council unless normalised.

⚠ **AMO has genuine gaps.** Hamilton, Waterloo and Niagara Falls return position
labels with no ward component at all, so AMO cannot audit them. Absence of ward
data in AMO is not evidence of an at-large council — cross-check before
concluding anything from a zero.

### Durham/York triage — 2026-08-27

Eleven sets were staged and count-verified. Loaded: **Markham** (By-law 2013-29,
2013-03-19, OMB appeal dismissed 2013-10-24 → 2014-10-27) and **Newmarket**
(publisher prose, "since 2003" → 2003-11-10). Both were interior *holes* —
Markham missing Ward 7, Newmarket missing Ward 5.

⛔ **Brock and Scugog are deliberately NOT loaded**, and the reason is not only
the missing date. We hold **no councillors at all** for either township, so
loading their wards would add a dated assertion I cannot support in order to
serve a roster that does not exist. Five wards are confirmed in place at the
2010, 2018 and 2022 Durham elections — a bound, not a date, and no by-law was
located.

⚠ **Ajax, Clarington, Oshawa, Uxbridge, Vaughan and Whitby are provenance-only.**
✅ All six now loaded — the first four by `0116`, Clarington and Vaughan by `0118`.
Held and authoritative counts match and geometry agrees, so a load buys a real
in-force date and a licence but fixes no coverage. Pending dates; low urgency.

⚠ **Whitby's layer says "Updated January 2021".** That is a publication date and
is deliberately unused — ruling A10.4 exists precisely for this.

⛔ Three are held pending an explanation, not a date:
- **King** — the city's own file has SEVEN wards with named councillors while
  AMO's 2026 roster shows six and we hold six. The only case in the wave where
  the *source* exceeds both AMO and what we hold.
- **Richmond Hill** — AMO lists wards 1-6 **and 8**, with no ward 7; the city's
  file has six.
- **Pickering** — two staged files, both effectively three wards but
  geometrically different, and one carries two zero-area sliver polygons. This
  dossier already flags an active Pickering ward boundary review.

### ⛔ A roster-side gap the boundary work exposes

Whitchurch-Stouffville's six wards are now loaded, and **all seven of its
councillors still sit on the `census-subdivisions/` municipality polygon** —
their `constituency_name` is "Whitchurch-Stouffville", because the retired Open
North mirror never carried ward assignments for them.

⚠ **No existing check can see this.** `wrong-tier` does not fire: a councillor on
a municipality polygon is exactly what a legitimate at-large council looks like
(LaSalle, Burnaby, Abbotsford). The two cases are indistinguishable from the
data we hold.

★ **AMO now distinguishes them.** Its `isWard` flag plus the ward labels say
whether a council elects by ward, so "ward council whose roster sits on the
municipality polygon" becomes a detectable class rather than an invisible one.
Worth a check once Ontario's roster is harvested after 2026-10-26 — assigning
these members is roster work, not boundary work, and the boundaries are now in
place waiting for it.

### ⛔ Three more traps, 2026-08-27

**1. A published ward map may be ROTATED relative to north.** A north-up render
of Guelph's staged geometry looked nothing like the City's ward-map PDF and
carried a dead-straight 45° boundary running the length of the city — which
reads as a corrupt reprojection. It is not. **Guelph's municipal boundary
genuinely is a rectangle rotated ~45°**, and both the City's PDF and the Watson
report are page-rotated to portrait with a tilted north arrow. Good Guelph data
was nearly discarded on this.

⚠ Confirm before calling geometry corrupt: check the native `spatialReference`
(Guelph's is EPSG:26917 and correct), compare against the publisher's own
municipal-boundary layer (88.97 km² vs a 89.36 km² ward union), and compare
length-weighted edge bearings against an independent control — Open North's
`census-subdivisions/<id>/simple_shape` is cheap and gave the same bbox and the
same bearing clusters at 44.5°/134.5°.

**2. An Ontario by-law may name the TERM-START date, not the election.**
Lincoln's By-law 2025-28 says its new structure "shall come into force and
effect on **November 15, 2026**" — the start of the council term. Under A10.4
the value to store is the election it first governs, **2026-10-26**. ⚠ Ontario
by-laws are inconsistent about which of the two they name, so the date printed
in the instrument is not automatically the date to store. This is the same
two-dates-for-one-boundary hazard that produced a 20-day Ottawa overlap and a
permanent London one, both fixed in migration `0112`.

**3. Name collisions are worse than same-name-different-tier.** Brantford was
held back because a 2024 ward-boundary review appeared to have an unfindable
outcome. That review belongs to the **County of Brant**, a different
municipality whose name differs by three letters and which surrounds the City.
AMO lists them separately (`Brant, County of` 10123 vs `Brantford, City of`
10109). ⛔ Verify the municipality, not the string — a substring match compounds
this rather than catching it.

### Licence: for Niagara, look at the CKAN mirror, not the Hub item

St. Catharines' ArcGIS item reports `licenseInfo = null`, but the same dataset
is mirrored on Niagara Open Data under, verbatim, **"Open Government License 2.0
(Corporation of the City of St. Catharines)"**. Lincoln, Welland and Fort Erie
each have their own OGL 2.0 instance there too. ★ For the twelve Niagara
municipalities the licence lives on the CKAN mirror — an ArcGIS `licenseInfo` of
null is not evidence that no licence exists.

### The six still not established — with the floors that WERE established

None is loaded. A floor is not a date, and a plausible-looking wrong date is
worse than no load.

| | floor established | why the date is still open |
|---|---|---|
| **Thunder Bay** | 1985 composition | The City states "The last change to the composition of City Council was in 1985, when the current system was created", and council had only ward councillors from 1970. ⛔ But **composition and boundaries are separable** and a count-preserving redraw is the common case — nothing says the lines drawn in 1985 are the lines in force. Wards are NOT changing for 2026: a four-ward recommendation was voted down 2025-04-09. ⚠ Its licence is *named but unreachable* — the item links `City-of-Thunder-Bay-Open-Data-Licence.pdf`, which 404s. Treat as unresolved, not open. |
| **Wellesley** | ≤ 2014-10-27 | Published `ward_map.pdf` has PDF CreationDate 2014-07-23 and matches the staged geometry exactly, including the stepped notch on the Ward 1 / Ward 4 edge at Hergott/Kressler Road. Dates the publication, not the boundary. |
| **Wilmot** | ≤ 2018-10-22, drawn 2016 | `allwards.pdf` CreationDate 2018-07-30, in-map credit "Development Services 2016", matches exactly including Ward 3's jagged north edge at Baden. |
| **Woolwich** | ≤ 2014-10-27 | The superseded `Ward_Polls` service (created 2017-10-27, attributed to the 2014-2018 council) dissolves by ward to 12.224 / 163.614 / 153.734 km² against the staged 12.172 / 163.606 / 153.731 — re-digitisation noise. |
| **North Dumfries** | none | Three per-ward PDFs all dated 2022-04-29 — a pre-election publication date, which A10.4 excludes. No ward page, no by-law register entry, no election page (`/elections/` 404s). **No earlier artefact exists to compare against**, so not even a floor. |
| **St. Catharines** | none | Source and licence resolved (above). Wards are 1 Merritton, 2 St. Andrew's, 3 St. George's, 4 St. Patrick's, 5 Grantham, 6 Port Dalhousie — ⚠ the sixth is St. George's, not "Western Hill". The City publishes street-by-street boundary descriptions but no by-law, no adoption date, no effective date. Names descend from the 1961 amalgamation; descriptions reference Highway 406 so the lines postdate its construction. Neither yields an election. |

### King and Pickering — both resolved 2026-08-27

**King** — the discrepancy was the publisher bundling the mayor into the ward
layer. The `MunicipalWardCounsillors` service returns SEVEN features: six wards
(47.85 / 33.88 / 120.39 / 37.64 / 36.58 / 60.52 km², summing to 336.86) plus a
seventh with `WARD_NUMBER = null` carrying **Mayor Steve Pellegrini** on a
336.49 km² township-wide polygon. King has **six** wards, confirmed by the
Township and by AMO, and our held six are correct.

★ That is the `census-subdivisions`-inside-a-ward-set contamination this dossier
records for our own data, appearing on the **publisher's** side. A spec for King
needs a `row_filter` dropping the null-ward row, and `expect_districts=6`. Not
loaded — the count is settled but no in-force date was established.

**Pickering** — ⛔ **By-law 8196/25**, passed 2025-07-15, appealed to the OLT
2025-08-29, **appeal withdrawn 2025-10-06**, so the new boundaries are in full
force for the 2026 election. The `New Wards` layer is the future map and is now
loaded dormant; the current map's mirror rows are end-dated 2026-10-25.

⚠ Three wards before and after — ruling A7 again, and the third Ontario case
where only an instrument could date the map.

⚠ What 8196/25 supersedes matters: a **2021** ward boundary review had already
adopted boundaries to take effect for 2026, and Council reopened it on
2025-01-27 against updated population data and replaced it. A map adopted in
2021 that will now never govern an election is not a generation worth holding —
A10.4 keys on the election a map GOVERNED, and that one governs none.

⚠ Pickering's published current layer carries **two zero-area sliver polygons
labelled "Ward 1"** beside its three real wards, so a naive feature count reads
5 for a 3-ward city. Its current in-force date remains unestablished.

### ⛔ Migration 0097's Niagara aggregator needs a re-audit

All twelve Niagara municipalities were loaded from one Region layer,
`VoterTool_data/FeatureServer/1` (44 polygons), stamped
`boundaries_version='2018'`, `effective_from=2018-10-22`. That was right for
2018 and **the layer has not been touched since**: its `editingInfo.lastEditDate`
is **2018-10-17**, five days before the 2018 election, and its service
description still reads "Upon the close of the nomination period official
candidate lists will be provided by the LAMs". It was built for the 2018
voter-lookup tool and abandoned.

⚠ So the 2018 date is honest but the data is eight years old, and at least one
municipality has moved since:

| | movement since 2018 | our data |
|---|---|---|
| **Port Colborne** | By-law 6948/94/21 (2021-11-08) redrew wards 1 and 3, in force 2022-10-24 | ⛔ **stale for the current term** |
| Welland | redrawn for 2026 | 2018 map, correct now |
| Niagara-on-the-Lake, Thorold | named in O. Reg. 140/26 with Port Colborne | 2018 map, correct now |
| Lincoln | By-law 2025-28, 4 → 3 for 2026 | 2018 map, correct now |

⚠ **Port Colborne's 2026 reduction came by Minister's regulation** (O. Reg.
140/26 under s.218.2.2 of the Municipal Act, in force 2026-05-22), **not** by
by-law, because the municipal deadline had passed. So unlike Lincoln there is no
s.222(4) appeal window to check, and the citation shape is a regulation.

⛔ Neither has a clean open-licensed machine-readable source for its new wards:
the aggregator's `licenseInfo` is a disclaimer, not a grant; it is not on
niagaraopendata.ca so the Region's OGL does not reach it; Lincoln's own portal
dataset is OGL 2.0 but its resources are `ward-and-poll-map-2014.pdf`; and Port
Colborne publishes no ward dataset at all. Lincoln's new wards exist only as
Schedule "A" metes-and-bounds text.

### ⛔ An explicit licence prohibition is not the same as silence

✅ **RESOLVED 2026-08-28 — both loaded.** Two Durham/York municipalities were
dated on 2026-08-27 and held, and this is the only time in the programme that
licence — not evidence — was the blocker:

- **Clarington** (1997-11-10, By-law 96-151 of 1996-08-12). The AGOL item's
  licenceInfo, verbatim: "The data is made available for personal informational
  purposes only and has not been prepared for, is not suitable for, and may not
  be used for, any commercial, legal, engineering, or surveying purpose." No
  linked grant behind it — unlike Oshawa, this really is the licence.
- **Vaughan** (2010-10-25). All three candidate ward layers have empty
  `licenseInfo` and empty `accessInformation`, `copyrightText` is the empty
  string, Vaughan runs no open-data catalogue, and York Region does not
  republish its wards. The only governing text is the site-wide terms: "No part
  of this web site, or the information contained therein, may be reproduced,
  stored in a retrieval system, or transmitted, in any form or by any means ...
  without the prior written permission of the City."

⚖ **Operator decision 2026-08-28: load both.** The standing rule
**"licence recorded, never a gate"** stands, and now covers explicit
prohibitions as well as the *unstated* licences it was originally made against —
the modal Ontario answer. Both texts are recorded verbatim in
`data/boundaries/municipal-ontario/PROVENANCE.md` § "Clarington + Vaughan" and
are paraphrased nowhere. Loaded by migration `0118`: Clarington 4 wards at
1997-11-10, Vaughan 5 at 2010-10-25, mirror generation retired, five Vaughan
councillors re-keyed and re-attached.

★ **Clarington is the counter-example to Oshawa and both readings are right.**
Oshawa's `licenseInfo` renders as a disclaimer wrapped around a hyperlink and
the hyperlink is the grant; Clarington's disclaimer has no linked grant behind
it. The discriminator is whether an `<a href>` survives the tag strip, **not**
the tone of the prose — reading the visible text alone gets Oshawa wrong, and
reading past it gets Clarington wrong.

⛔ **Vaughan publishes FOUR ward layers and one of them is the wrong answer.**
All four give 5 wards with identical `WARD_NO` and `DESCRIP`, so no attribute
separates them. Item `04a102f180dd48b5a1e98d93e8baf289` ("Ward", snippet names
the authority: "as per the latest ward boundary review from City Clerks") was
chosen and is byte-identical in geometry to `b8f3327011d54dc1b9f624d9b57c076f`,
an independently-owned second item. `43ef9df09ccd…` (pmomaps) is the same
generation 0.02% finer. But `982a8b1cbf00…` ("Ward Boundary_CRM") is a
**generalised** copy off by up to **5.12%** on Ward 1 — correct count, correct
names, correct owner domain, wrong map. Four siblings agreeing on a count is
four chances to take the wrong one, not a corroboration.

⚠ **Vaughan's set was re-keyed by the load.** Held ids were slugged from the
neighbourhood name (`vaughan-wards/maplekleinburg`, `…/thornhill`) while the
display names were already "Ward N"; the uniform label wins, so the ids are now
`vaughan-wards/ward-1 … ward-5`. `politician_terms` was re-keyed inside the
migration (no tool covers that table) and `politicians` was detached for
`reattach-municipal-roster`, which re-linked all five. Clarington's ids were
already `ward-N` and were untouched.

★ **Vaughan is also the tranche's cleanest illustration of why the appeal window
matters.** By-law 89-2009 is NOT the operative instrument: it was appealed, and
"the OMB imposed a different ward structure than the one approved by Vaughan
Council, but maintained the number of wards at 5". Five before, five after — the
count survived the appeal and the map did not. Cite the OMB order, note the
by-law.
