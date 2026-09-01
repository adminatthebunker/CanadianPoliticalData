# Municipal Québec — Electoral Boundary Research

> Standalone boundary dossier for Québec municipal districts — **24 source sets / 347 rows**,
> the second-largest municipal block we hold. Cross-cutting context (methodology, licence
> matrix, reconciliation strategy) lives in [`overview.md`](./overview.md); my matrix rows are
> in [`_matrix/municipal-quebec.md`](./_matrix/municipal-quebec.md).
> This dossier owns **boundaries only**. Transcript/roster research for the individual cities
> lives in [`../cities/montreal.md`](../cities/montreal.md) and [`../cities/quebec.md`](../cities/quebec.md).

**Agency:** Élections Québec (provincial oversight) + each municipality as boundary authority under the *Loi sur les élections et les référendums dans les municipalités* | **Sets held:** 24 | **Rows held:** 347 | **Real district polygons:** 317 | **Redistribution cadence:** ★ **province-wide and synchronised** — every municipality redivides ahead of the fixed general election, held the first Sunday of November every four years

**Status snapshot (2026-08-18):** ⛔ **The entire Québec municipal layer is one full generation out of date, and uniformly so.** Québec held a **province-wide general municipal election on 2025-11-02** across ~1,100 municipalities; every set we hold predates it. Montréal is the proof: the city publishes **58 districts for 2025** against **59 for 2021**, and our rows are the 2021 vintage. ★ Unlike Ontario, this is not 24 independent staleness problems — it is **one synchronised event**, which makes it far cheaper to fix and far easier to schedule. ✅ **Sourcing is excellent: Données Québec is a single CKAN federation** carrying every major municipality's `districts électoraux`, uniformly **CC-BY**, with GeoJSON on every dataset — **difficulty 1**, one API, one licence. ★ Montréal publishes **five generations** (2009 / 2013 / 2017 / 2021 / 2025) from one dataset, which is the richest temporal source in the entire corpus. ⛔ **Same structural defects as Ontario, plus one more:** 22 of 24 sets carry a stray `census-subdivisions/` municipality polygon, and `quebec-districts` / `saguenay-districts` additionally mix **borough** polygons in with districts under a `*-boroughs/` prefix — a genuine third tier. Point-in-polygon at Québec City returns **3** overlapping polygons. ⛔ **Montréal is also partially ingested** — only 39 of 59 2021 districts are present. ✅ **No A6 violations**: no QC set carries a year in its prefix.

---

## Platform families

Québec is the **federated** case, and it is the happiest sourcing story in either municipal
dossier.

**Family A — Données Québec (the dominant family).** `donneesquebec.ca/recherche/api/3` is a
CKAN instance federating provincial and municipal open data. A search for
`"districts électoraux"` returns **31 datasets from 15 municipal publishers**, and *every one*
is licensed `cc-by` and offers **GeoJSON**:

| Publisher | Formats offered |
|---|---|
| Ville de Montréal | CSV, GeoJSON, SHP |
| Ville de Québec | CSV, GeoJSON, KML, SHP |
| Ville de Laval | CSV, GeoJSON, KML, SHP |
| Ville de Gatineau | CSV, GeoJSON, KML, SHP, XLSX |
| Ville de Longueuil | CSV, GeoJSON, KMZ, SHP, XLSX |
| Ville de Lévis | FGDB, GeoJSON, SHP |
| Ville de Sherbrooke | CSV, EsriREST, GeoJSON, HTML, KML |
| Ville de Saguenay | CSV, GeoJSON, PDF, SHP |
| Ville de Trois-Rivières | CSV, GeoJSON, PDF, SHP |
| Ville de Saint-Jean-sur-Richelieu | CSV, GeoJSON, SHP |
| Ville de Rimouski | CSV, GeoJSON, KML, SHP |
| Ville de Repentigny | CSV, GeoJSON, JSON, KML, SHP |
| Ville de Rouyn-Noranda | CSV, EsriREST, GeoJSON, HTML, KML |
| Ville de Saint-Hyacinthe | EsriREST, GeoJSON |
| Ville de Shawinigan | GeoJSON |

★ **One harvester against one CKAN API covers most of the block, under one licence.** That is
the opposite of Ontario's ~40 tenancies and ~40 licences, and the two dossiers should be built
with different tooling for that reason.

**Family B — municipal CKAN behind the federation.** Données Québec federates rather than
hosts: Montréal's resources resolve to `donnees.montreal.ca`. ⚠ **Trap, hit during staging:**
`donnees.montreal.ca` returns **HTTP 403 to a bare `curl`** and serves normally with a browser
`User-Agent`. The Données Québec API itself is unprotected, so a harvester that reads the
catalogue successfully and then fails on every Montréal download will look like a data problem
rather than a UA problem. Set a UA.

**Family C — not on Données Québec (the West Island / off-island suburbs).** Nine of our 24
sets have no publisher in the federation: Beaconsfield, Kirkland, Dorval, Pointe-Claire,
Westmount, Côte-Saint-Luc, Dollard-des-Ormeaux, Senneville, Sainte-Anne-de-Bellevue, plus
Montréal-Est, Mercier, Brossard, Terrebonne and Saint-Jérôme. These are small municipalities
that publish district maps as **PDF on their own websites** or not at all. `UNTESTED — probe
during build`. ★ **A provincial answer key exists:** Élections Québec maintains
*Municipalities divided into electoral districts* at
https://www.electionsquebec.qc.ca/en/electoral-maps/municipalities-divided-into-electoral-districts/
— the register of which municipalities are divided into districts at all, and into how many.
That is the QC equivalent of Ontario's AMO at-large/ward PDF and should be the first thing the
build phase reads: it resolves both the district-count audit and the at-large question for all
24 sets at once.

## ⛔ The 2025 election — the whole layer is one generation stale

This is the finding that dominates the Québec block, and it is different in kind from Ontario's.

- Québec municipal elections are **fixed and province-wide**: the first Sunday of November
  every four years. **2021-11-07**, then **2025-11-02** across roughly **1,100 municipalities**.
  The next is **2029-11-04**.
- Redivision happens ahead of each general election under the *Loi sur les élections et les
  référendums dans les municipalités*, with Élections Québec oversight.
- **Every set we hold carries `effective_from = '2023-01-01'`** — an Open North mirroring
  artifact — and every one of them therefore reflects the **2021** map.

**Montréal is the measurable proof.** Its Données Québec dataset publishes both generations,
so the comparison is direct rather than inferential:

| | Districts |
|---|---:|
| Montréal 2021 (`districts-electoraux-2021.geojson`) | **59** |
| Montréal 2025 (`districts-electoraux-2025.json`) | **58** |
| What we hold (real rows in `montreal-boroughs-and-districts`) | 62 (mixed districts + boroughs) |

⚠ **And a second, independent defect surfaced in the same comparison: Montréal is only
partially ingested.** Of our 62 real rows, only **39 match a 2021 district name** and ~19 match
a **borough** name. So we do not hold 59 districts plus a few boroughs — we hold roughly 39
districts and 19 boroughs. **20 of Montréal's 59 districts from its own generation are simply
absent**, and 19 of the 58 current districts have no row at all. ★ **This is the BC defect
exactly**: 62 rows for a 59-district city reads as complete-and-then-some, while a third of the
districts are missing and boroughs are padding the count.

⚠ **Schema churn between generations is an A4-class trap here.** The property names changed
completely:

| 2021 | 2025 |
|---|---|
| `nom`, `num`, `arrondissement`, `id`, `municipalite` | `NO_DISTRICT`, `CODE_DISTRICT`, `NOM_DISTRICT`, `NOM_ARR` |

A harvester keyed to 2021's lowercase fields silently reads nothing from the 2025 file. Code
against the specific generation, and treat the field map as per-vintage.

## ⛔ Tier contamination — the same defect as Ontario, plus boroughs

**22 of 24 QC sets** carry exactly one stray `census-subdivisions/<7-digit>` row — the
whole-municipality polygon, filed inside the district set. Only `laval-districts` (20) and
`sainte-anne-de-bellevue-districts` (5) are clean.

**Tally:** 347 rows = **317 real district polygons** + 22 stray CSD + 8 borough rows.

**And Québec adds a third tier that Ontario does not have.** This is the "mixed-prefix
anomaly" from the brief, now diagnosed:

| Set | Rows | Districts | Boroughs | CSD | Diagnosis |
|---|---:|---:|---:|---:|---|
| `quebec-districts` | 25 | 19 | **5** (`quebec-boroughs/`) | 1 | ⛔ mis-named; contains arrondissements |
| `saguenay-districts` | 19 | 15 | **3** (`saguenay-boroughs/`) | 1 | ⛔ mis-named; contains arrondissements |
| `montreal-boroughs-and-districts` | 63 | ~43 | ~19 | 1 | ✅ **honestly named**, same structure |

★ **The anomaly is not a data error — it is an unlabelled hierarchy, and Montréal proves the
intent.** Montréal's set is called `montreal-boroughs-and-districts` and openly holds both
tiers. Québec City and Saguenay hold exactly the same two-tier structure but under a
`*-districts` name, with the borough rows given a distinct `*-boroughs/` `constituency_id`
prefix. Whoever built the ingest knew there were two tiers — the prefix records it — but the
`source_set` name does not.

**Boroughs are real elected units in Québec, not administrative decoration.** Montréal's 19
arrondissements each have a *maire d'arrondissement*; Québec City's 6 and Saguenay's 3 likewise.
So the borough rows **should be kept** — they map to real officials. Confirmed in our own data:
`saguenay-boroughs/jonquiere` → `Carl Dufour`; `quebec-boroughs/charlesbourg`,
`.../la-haute-saint-charles`, `.../les-rivieres` all carry officials.

⛔ **PIP consequence, measured:** a point in Québec City matches **three** polygons —
`quebec-districts/cap-aux-diamants` (district), `quebec-boroughs/la-cite-limoilou` (borough),
and `census-subdivisions/2423027` (city). All three are legitimately "the boundary you are in";
nothing in the schema says which is which.

**Recommended split.** Not two-way but **three-way**, and this is why a `boundary_kind` column
beats an ad-hoc `source_set` split (see [`municipal-ontario.md`](./municipal-ontario.md), which
independently needs the same column for two tiers):

| Tier | Example | `boundary_kind` |
|---|---|---|
| District / ward | `quebec-districts/cap-aux-diamants` | `district` |
| Borough / arrondissement | `quebec-boroughs/la-cite-limoilou` | `borough` |
| Municipality | `census-subdivisions/2423027` | `municipality` |

Then rename `quebec-districts` → `quebec-boroughs-and-districts` and `saguenay-districts` →
`saguenay-boroughs-and-districts`, matching the Montréal convention that already exists and is
already correct. The municipal PIP resolver should return the smallest matching polygon by
default, with the tier available for callers that want the borough or city answer.

## ⛔ The 5 QC orphan district polygons — stale geometry, current roster

Québec's orphans have a different cause from Ontario's, and it is the cleaner diagnosis:

| Set | Orphan rows |
|---|---|
| `quebec-districts` | `Lac-Saint-Charles—Saint-Émile`, `Saint-Louis—Sillery`, `Saint-Rodrigue`, `Vanier-Duberger` |
| `saguenay-districts` | `District 5` |

★ **Québec City: stale geometry, current roster — confirmed by name-drift in both directions.**
Our roster holds district names with **no matching polygon** — `Les Saules`,
`Sainte-Foy—Sillery—Cap-Rouge`, `Monts` (all `constituency_id IS NULL`) — while our polygons
hold names with no matching official. Those are two halves of the same redraw: the roster was
refreshed after 2025, the boundaries were not. ✅ Corroborated by the authoritative count —
Québec City is divided into **21 districts grouped in 6 arrondissements** under
*Règlement R.V.Q. 3252*, and we hold **19 districts and 5 boroughs**. So the set is short by 2
districts and 1 borough *and* carries 4 superseded district names.

⚠ **Saguenay `District 5` is a different, smaller case** — the other 14 Saguenay districts all
have officials, so this is a single roster gap (vacancy or missed ingest), not a redraw. Also
note `saguenay-boroughs/chicoutimi` and `saguenay-boroughs/la-baie` have no official while
`jonquiere` does: the borough-president rows are only two-thirds ingested. Neither is a
boundary problem.

**So, answering the brief's per-case question:** Québec City = **stale geometry**;
Saguenay = **stale roster**; and (from the ON dossier) Brampton/Peel = **neither — duplicate
ingestion of paired wards**.

## Ruling A6

✅ **No Québec violations.** No QC `source_set` carries a year in its prefix — checked all 24.

⚠ But the same latent problem as Ontario: `boundaries_version` is uniformly `'current'` across
all 347 rows, so **no QC set records which generation it holds** — which is precisely the
information that would have made the 2021-vs-2025 staleness visible without a manual
comparison. ★ Québec is the best place in the corpus to fix this properly, because Montréal
publishes five dated generations: loading them as `boundaries_version` `'2009'` / `'2013'` /
`'2017'` / `'2021'` / `'2025'` against stable `montreal-districts/<slug>` IDs is exactly the
shape A6 is designed for, and it would give us a working temporal municipal layer for at least
one city.

## Postal-code correspondence

⛔ None published, by any Québec municipality or by Élections Québec. Our point-in-polygon path
is the right mechanism — once the tier defect above is fixed, since PIP is currently what
returns three answers in Québec City.

## Terms / Licensing

- **Licence: `cc-by` — Creative Commons Attribution 4.0 — uniformly, on every one of the 31
  district datasets from all 15 publishers on Données Québec.** ✅ This is the cleanest licence
  position of any block in either of my municipal dossiers, and a marked contrast with
  Ontario's ~40 unaudited licensors.
- **Internal use:** ✅ unambiguous.
- **Redistribution:** ✅ permitted — CC-BY's grant covers reproduction and distribution,
  including commercially, conditional only on attribution.
- **Attribution:** required. Attribute the publishing municipality (e.g. *Ville de Montréal*),
  per CC-BY 4.0.
- **No click-through gate** on any Québec endpoint reached. No account, no form, no checkbox.
- ⚠ **The Family-C municipalities are unlicensed-unknown**, because they are not on Données
  Québec at all. The clean CC-BY finding covers the federated 15, not all 24 sets.

## Rate limits / auth

- **Auth:** none.
- **Rate limits:** none observed on `donneesquebec.ca/recherche/api/3` or `donnees.montreal.ca`.
- ⚠ **`donnees.montreal.ca` returns HTTP 403 to a bare `curl`.** A browser `User-Agent` clears
  it immediately. The catalogue API does not have this protection, so the failure appears only
  at download time. Cost me two failed fetches during staging; recorded so it costs nobody else.
- ⓘ Montréal's GeoJSON is large and unsimplified — the 2025 districts file is **6.9 MB** for 58
  features. Budget accordingly if harvesting all 24 sets in one run.

## Staged files

Staging root `data/boundaries/municipal-quebec/`, manifest at
`data/boundaries/municipal-quebec/PROVENANCE.md`. **8.7 MB.** ⚠ **Representative, not
exhaustive** — Montréal was staged because it is the largest set, the partial-ingest case, and
the only publisher in either municipal dossier offering five generations.

| Path | Bytes | What it is |
|---|---:|---|
| `current/montreal-districts-electoraux-2025.geojson` | 6,883,713 | ★ **Current.** 58 districts, fields `NO_DISTRICT` / `CODE_DISTRICT` / `NOM_DISTRICT` / `NOM_ARR`. The generation we do **not** hold. |
| `prior/montreal-districts-electoraux-2021.geojson` | 2,142,598 | **Prior.** 59 districts, fields `nom` / `num` / `arrondissement` / `id` / `municipalite`. The generation we *think* we hold — useful for measuring exactly what the partial ingest dropped. |

**Not staged, deliberately:** Montréal 2017 / 2013 / 2009 (available from the same dataset, and
worth harvesting during the build for a full temporal layer); the other 23 municipalities
(build-phase harvest via the Données Québec API).

## Reconciliation with `constituency_boundaries`

**What we hold:** 24 `source_set` values, **347 rows**, `level='municipal'`,
`province_territory='QC'`. Every row carries `boundaries_version = 'current'` and
`effective_from = '2023-01-01'` — ⚠ both Open North mirroring artifacts.

**Composition (counted):** 347 = **317 real district polygons** + 22 stray CSD + 8 borough rows.

`Real` = rows whose `constituency_id` prefix matches the `source_set`; `Boro` = `*-boroughs/`
rows; `CSD` = whole-municipality rows; `Orph` = real rows with no matching official.

| Set | Rows | Real | Boro | CSD | Orph | Notes |
|---|---:|---:|---:|---:|---:|---|
| `beaconsfield-districts` | 7 | 6 | 0 | 1 | 0 | Family C — not on Données Québec |
| `brossard-districts` | 10 | 9 | 0 | 1 | 0 | Family C |
| `cote-saint-luc-districts` | 9 | 8 | 0 | 1 | 0 | Family C |
| `dollard-des-ormeaux-districts` | 9 | 8 | 0 | 1 | 0 | Family C |
| `dorval-districts` | 7 | 6 | 0 | 1 | 0 | Family C |
| `gatineau-districts` | 20 | 19 | 0 | 1 | 0 | ✅ on Données Québec |
| `kirkland-districts` | 9 | 8 | 0 | 1 | 0 | Family C |
| `laval-districts` | 20 | 20 | 0 | 0 | 0 | ✅ **clean of CSD**; on Données Québec |
| `levis-districts` | 16 | 15 | 0 | 1 | 0 | ✅ on Données Québec |
| `longueuil-districts` | 16 | 15 | 0 | 1 | 0 | ✅ on Données Québec; ⚠ documented 2025 redécoupage |
| `mercier-districts` | 7 | 6 | 0 | 1 | 0 | Family C |
| `montreal-boroughs-and-districts` | 63 | 62 | — | 1 | 0 | ⛔ **partial** — ~39 of 59 districts + ~19 boroughs. ✅ honestly named |
| `montreal-est-districts` | 7 | 6 | 0 | 1 | 0 | Family C |
| `pointe-claire-districts` | 9 | 8 | 0 | 1 | 0 | Family C |
| `quebec-districts` | 25 | 19 | **5** | 1 | **4** | ⛔ mis-named + stale geometry (21 districts / 6 boroughs authoritative) |
| `saguenay-districts` | 19 | 15 | **3** | 1 | **1** | ⛔ mis-named; orphan is a roster gap |
| `saint-jean-sur-richelieu-districts` | 13 | 12 | 0 | 1 | 0 | ✅ on Données Québec |
| `saint-jerome-districts` | 13 | 12 | 0 | 1 | 0 | Family C |
| `sainte-anne-de-bellevue-districts` | 5 | 5 | 0 | 0 | 0 | ✅ **clean of CSD**; Family C |
| `senneville-districts` | 6 | 5 | 0 | 1 | 0 | Family C |
| `sherbrooke-districts` | 16 | 15 | 0 | 1 | 0 | ✅ on Données Québec |
| `terrebonne-districts` | 17 | 16 | 0 | 1 | 0 | Family C |
| `trois-rivieres-districts` | 15 | 14 | 0 | 1 | 0 | ✅ on Données Québec |
| `westmount-districts` | 9 | 8 | 0 | 1 | 0 | Family C |

⚠ **Every "Real" figure above should be treated as unverified against the actual council size.**
Montréal and Québec City were both checked and both came up short (39 of 59; 19 of 21). Two for
two is not a sample that justifies trusting the other 22. The Élections Québec register named
above gives the authoritative district count per municipality and turns this into a
mechanical audit.

**Recommended build shape:**

1. **Re-harvest the whole block from Données Québec** — one CKAN sweep, CC-BY throughout, GeoJSON
   throughout. Because the staleness is a single synchronised event, this is one job rather
   than 24 investigations.
2. **Introduce the three-tier `boundary_kind`** (`district` / `borough` / `municipality`) and
   classify all 347 existing rows. Shared with the Ontario fix.
3. **Rename `quebec-districts` → `quebec-boroughs-and-districts`** and `saguenay-districts` →
   `saguenay-boroughs-and-districts`, matching the correct Montréal convention.
4. **Load Montréal's five generations** against stable `montreal-districts/<slug>` IDs with real
   `boundaries_version` values. This is the A6 showcase and gives us one genuinely temporal
   municipal city.
5. **Set `effective_from = '2025-11-02'`** for the new generation and `effective_to = '2025-11-02'`
   for the retired 2021 rows. ★ **Québec is much cleaner than Ontario under ruling A2**: the
   in-force date is the fixed province-wide election date, identical for all 24 sets, rather
   than 48 separate municipal by-laws. One date, cited to the *Loi sur les élections et les
   référendums dans les municipalités*.
6. **Retire, do not delete, the 2021 rows** — they become the prior generation, and for the 9
   Family-C municipalities with no open-data publisher they may be the only copy we will get.
7. **Audit real-count vs authoritative count** for all 24 against the Élections Québec register.

## Research-handoff items

- **The whole QC layer is one generation stale and the fix is a single sweep — schedule it.**
  The 2025-11-02 election has already happened (nine months ago), so this is not a forecast:
  every Québec municipal boundary we serve is superseded *today*. Unlike Ontario's fragmented
  timing this is one CKAN harvest under one licence, so it is the **highest value-per-effort
  item across both municipal dossiers**. Recommend doing QC first for that reason.
- **`boundary_kind` needs three values here, not two.** Ontario needs `ward` / `municipality`;
  Québec needs `district` / `borough` / `municipality`, because arrondissement mayors are real
  elected officials with real polygons. If the schema decision is taken from the Ontario dossier
  alone it will be re-opened immediately. Flagging so the two are decided together.
- **Nine Family-C municipalities have no known open-data publisher.** Beaconsfield, Kirkland,
  Dorval, Pointe-Claire, Westmount, Côte-Saint-Luc, Dollard-des-Ormeaux, Senneville,
  Sainte-Anne-de-Bellevue (plus Montréal-Est, Mercier, Brossard, Terrebonne, Saint-Jérôme) are
  absent from Données Québec. `UNTESTED — probe during build`. ⚠ If they publish PDF maps only,
  these are difficulty-5 and the 2021 rows we hold become irreplaceable — **do not delete them
  during the re-harvest** even though they are stale.
- **Should Montréal's full five-generation history be loaded, or just current + prior?** All
  five are free to fetch and it is the only city in the corpus offering that depth, but it
  multiplies Montréal's row count by five for a benefit (historical address lookup) nobody has
  asked for. **Recommend current + prior only**, with the other three recorded as available.
  Raising it because loading them later costs no more than loading them now.
- **Québec City is short 2 districts and 1 borough on top of being stale.** Authoritative is 21
  districts / 6 arrondissements (R.V.Q. 3252); we hold 19 / 5. The re-harvest fixes it, but it
  is worth knowing the gap predates the 2025 redraw — this set was never complete.

## Status

- [x] All 24 QC sets inventoried and decomposed by row tier (2026-08-18)
- [x] Platform family mapped — **Données Québec CKAN federation, 15 publishers, uniformly CC-BY, GeoJSON throughout**
- [x] Licence cleared — ✅ **CC-BY 4.0, redistribution and commercial use permitted with attribution** (federated 15; Family C unknown)
- [x] Staleness established — ⛔ **entire layer is the 2021 vintage; the 2025-11-02 province-wide election superseded it**
- [x] Mixed-prefix anomaly diagnosed — **an unlabelled borough tier, not corruption; Montréal's naming is the correct model**
- [x] 5 QC orphan rows diagnosed — **Québec City = stale geometry; Saguenay = stale roster**
- [x] `census-subdivisions` fallback quantified — 22 of 24 sets contaminated
- [x] Multi-match PIP defect demonstrated — 3 polygons at Québec City
- [x] A6 checked — ✅ **no violations**; but `boundaries_version` is uninformative on all 347 rows
- [x] Montréal current + prior staged; partial-ingest defect measured (39 of 59 districts held)
- [ ] Re-harvest from Données Québec — ⛔ **not done; single sweep, highest value-per-effort item**
- [ ] Family C (9+ municipalities) probed for a boundary source — **not attempted**
- [ ] Real-count audit against the Élections Québec register — **2 of 24 checked, both short**
- [ ] Three-tier `boundary_kind` decision — **needs operator call, jointly with Ontario**
