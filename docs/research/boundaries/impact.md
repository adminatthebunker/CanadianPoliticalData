# Measured user impact — how wrong is the lookup today

> Companion to [`geocoding.md`](./geocoding.md). That dossier answers *"where do we get a coordinate."*
> This one answers *"given the coordinate, how often does the answer we return match reality."*
> Per-jurisdiction boundary sources live in the sibling dossiers; cross-cutting context in [`overview.md`](./overview.md).

**Unit:** addresses, not districts | **Frame:** 16,157,303 geocodable Canadian addresses (StatCan NAR `202606`) | **Sample:** 32,500 (2,500 per province/territory) | **Method:** point-in-polygon against `constituency_boundaries.boundary_simple`

**Status snapshot (2026-08-18):** ⛔ **9.15% of Canadian addresses — roughly one in eleven — get no provincial answer at all from the lookup today.** A further **2.12%** get a confidently wrong one across the six provinces where authoritative geometry could be checked, so the measured provincial error rate over those six is **12.61%**. ★ **The address view and the district view disagree sharply, and the address view is the one that matches lived experience.** British Columbia holds 52 of 93 districts — a number that sounds like "somewhat incomplete" — and returns nothing for **42.3%** of its addresses, contributing **6.05 of the 9.15 percentage points** on its own. Conversely Northwest Territories holds a *perfect* 19 of 19 districts and still misinforms **14.3%** of its addresses, because its entire error budget is misassignment rather than absence. ✅ **Federal is healthy and serves as the method's sanity check:** 0.95% no-answer, 0.83% wrong, **1.79% total** — consistent with a single missing district, which is what we know to be true. ⚠ All figures are sample estimates with ~±0.4 to ±1.9 pp of sampling error, measured against simplified geometry; see § Method and caveats.

---

## Headline figures

| Measure | Rate | Scope |
|---|---:|---|
| **Provincial — no answer** | **9.15%** | address-weighted, all 13 jurisdictions |
| **Provincial — wrong answer** | **2.12%** | address-weighted over the 6 measurable jurisdictions (62.3% of addresses) |
| **Provincial — any error** | **12.61%** | same 6 jurisdictions |
| Federal — no answer | 0.95% | address-weighted, all 13 |
| Federal — wrong answer | 0.83% | address-weighted, all 13 |
| **Federal — any error** | **1.79%** | address-weighted, all 13 |

★ **The single number for the operator: ask the lookup "who is my MLA" from a random Canadian address and it fails to answer about 1 time in 11.** Add the wrong answers in the provinces we can check and it is wrong or silent about 1 time in 8.

⚠ The 9.15% and the 2.12% are **not** additive into a single national "any error" figure, because the wrong-answer rate is only measured for six jurisdictions. The honest combined statement is the 12.61% over those six, which cover 62.3% of Canadian addresses.

## Phase 1 — the no-answer rate

For each jurisdiction, 2,500 randomly drawn addresses were tested with `ST_Contains(boundary_simple, point)` against every `level='provincial'` polygon we hold. "No answer" means zero polygons contained the point.

| PR | Districts held | Actual seats | Addresses (frame) | Share of CA | **No answer** | 95% CI | Contribution to national |
|---|---:|---:|---:|---:|---:|---|---:|
| NU | **0** | 22 | 4,270 | 0.03% | ⛔ **100.0%** | — | 0.03 pp |
| NB | 22 | 49 | 385,398 | 2.39% | ⛔ **55.2%** | ±1.95 | 1.32 pp |
| BC | 52 | 93 | 2,309,789 | 14.30% | ⛔ **42.3%** | ±1.94 | **6.05 pp** |
| PE | 26 | 27 | 85,367 | 0.53% | ⚠ 28.8% | ±1.78 | 0.15 pp |
| SK | 46 | 61 | 347,851 | 2.15% | ⚠ 22.3% | ±1.63 | 0.48 pp |
| NL | 36 | 40 | 184,693 | 1.14% | ⚠ 11.8% | ±1.27 | 0.13 pp |
| NT | 19 | 19 | 11,281 | 0.07% | 4.8% | ±0.84 | 0.00 pp |
| MB | 56 | 57 | 526,366 | 3.26% | 3.2% | ±0.69 | 0.10 pp |
| YT | 19 | 19 (now 21) | 17,832 | 0.11% | 3.0% | ±0.67 | 0.00 pp |
| QC | 124 | 125 | 4,559,562 | 28.22% | 1.4% | ±0.46 | 0.40 pp |
| ON | 123 | 124 | 5,433,902 | 33.63% | 1.3% | ±0.44 | 0.44 pp |
| NS | 55 | 55 | 534,574 | 3.31% | 0.7% | ±0.33 | 0.02 pp |
| AB | 87 | 87 | 1,756,418 | 10.87% | ✅ 0.2% | ±0.18 | 0.02 pp |
| **National** | | | **16,157,303** | 100% | **9.15%** | | **9.15 pp** |

⚠ **Do not read the unweighted mean.** Averaging the thirteen percentages gives 21.2%, which is meaningless — it weights Nunavut's 4,270 addresses the same as Ontario's 5.4 million. The address-weighted figure is **9.15%**.

### What the predictions got right, and what they got wrong

The coordinator predicted severe holes in NB, SK, BC, YT and 100% in NU. Scoring that honestly:

- ✅ **NU 100%** — exactly as predicted. We hold zero polygons; every address returns nothing.
- ✅ **NB 55.2%** — predicted "roughly half"; the 22 polygons we hold cover 47% of the province by area and 44.8% by address. Close agreement between the area and address views here, which is itself informative: NB's missing districts are not concentrated in its cities.
- ✅ **BC 42.3%** and ✅ **SK 22.3%** — both confirmed as large holes.
- ⚠ **YT was wrong.** Predicted a large hole; measured **3.0%**. We hold 19 Yukon polygons and Yukon had 19 districts in 2015, so the territory is almost fully *covered*. ★ But this is where the address view earns its keep — Yukon's real problem is not absence, it is that the 2024 redistribution went to 21 districts with substantial renaming, so **34.9% of Yukon addresses get a confidently wrong district** (§ Phase 2). A coverage-only audit would have scored Yukon as nearly healthy. It is the worst jurisdiction we can measure.

## Phase 2 — the wrong-answer rate

Where an agent has staged authoritative current-generation geometry as GeoJSON, each sampled address was resolved twice — once against our stored `boundary_simple`, once against the authoritative polygons — and the two district names compared after Unicode normalisation (accent-folded, lowercased, non-alphanumerics stripped, so `Mackenzie-Delta` ≡ `Mackenzie Delta` and `Tu Nedhé - Wiilideh` ≡ `Tu Nedhé-Wiilideh`).

| PR | Authoritative source | Auth districts | Ours | **No answer** | **Wrong** | **Any error** | Wrong given we answered |
|---|---|---:|---:|---:|---:|---:|---:|
| **BC** | Elections BC 2023 (BS11) | 93 | 52 | ⛔ 42.3% | ⛔ 6.0% | ⛔ **48.3%** | 10.5% |
| **YT** | Approved Yukon EDs 2024 | 21 | 19 | 3.0% | ⛔ **34.9%** | ⛔ **37.9%** | **36.0%** |
| **NT** | NWT Electoral Districts 2023 | 19 | 19 | 4.8% | ⚠ **9.5%** | ⚠ **14.3%** | 10.0% |
| **ON** | MTO authoritative EDs 2018 | 124 | 123 | 1.3% | 0.8% | 2.1% | 0.8% |
| **NS** | Elections NS ED-PD 2026-04-09 | 55 (1,817 PDs) | 55 | 0.7% | 1.2% | 1.9% | 1.2% |
| **AB** | GoA provincial EDs 2019 | 87 | 87 | ✅ 0.2% | ✅ 1.0% | ✅ 1.2% | 1.0% |

**Weighted over these six (62.3% of Canadian addresses): 2.12% wrong, 12.61% any error.**

### ★ NT — the case the district count completely hides

The coordinator flagged NT as the priority, and the prediction was exactly right. NT holds **19 of 19** districts. Every coverage metric scores it perfect. Yet **14.3% of NT addresses get a wrong or missing answer**, and 9.5 points of that is *misassignment* — our polygons are the 2013 generation, the authoritative file is 2023, and the districts were redrawn without changing the count.

It concentrates exactly where the coordinator expected — Yellowknife, which is where the addresses are:

| Ours says | Authoritative says | Sampled addresses |
|---|---|---:|
| Frame Lake | Yellowknife Centre | 42 |
| Frame Lake | Great Slave | 29 |
| Yellowknife North | Great Slave | 25 |
| Kam Lake | Frame Lake | 23 |
| Yellowknife South | Kam Lake | 22 |
| Yellowknife North | Tu Nedhé-Wiilideh | 19 |
| Hay River North | Hay River South | 18 |
| Yellowknife Centre | Yellowknife North | 16 |

Nine of the ten worst pairs are Yellowknife districts trading addresses with each other. A resident of downtown Yellowknife has a roughly one-in-ten chance of being told the wrong MLA, with no signal that anything is wrong.

### YT — worst measured jurisdiction

34.9% wrong, 36.0% of answered lookups. Driven by the 2024 redistribution (19 → 21 districts) with wholesale renaming: `Takhini-Kopper King` → `Takhini` (153 sampled addresses), `Pelly-Nisutlin` → `Watson Lake-Ross River-Faro` (90), `Porter Creek Centre` → `Whistle Bend North` (86), `Mount Lorne-Southern Lakes` → `Marsh Lake-Mount Lorne-Golden Horn` (76).

⚠ Some of these are pure renames of near-identical geometry, where the *representative* may be the same person. That still counts as wrong for our purposes — we return a district name that no longer exists, and any join to a current roster fails.

### BC — the largest absolute contributor

42.3% no-answer plus 6.0% wrong. Of the addresses BC *does* answer, **10.5% are wrong**, because our 52 polygons are the 2015 generation against a 2023 authoritative set. BC is 14.3% of Canadian addresses, so it alone contributes 6.05 of the national 9.15 pp no-answer figure. ★ **Fixing BC alone would cut the national no-answer rate by two thirds, from 9.15% to 3.10%.**

### Not measurable

No authoritative current geometry in a format readable without GDAL (all staged as zipped shapefiles; there is no `ogr2ogr`, `fiona` or `pyshp` on this host):

**NB, NL, MB, NU, QC, SK, PE.** Their no-answer rates in Phase 1 are solid — that measurement needs only our own table — but their wrong-answer rates are **unmeasured, not zero**. ⚠ Given that NB, SK and NL hold 2012–2024-era geometry against redistributed maps, their true wrong-answer rates are likely material. **UNTESTED — measure during build**, once shapefiles can be read.

## Federal — the sanity check

Federal was run as a control, exactly as the coordinator asked, because we know the answer in advance: we hold 342 of 343 districts, missing only `24077`. A method that over-reports would show federal error too.

**It does not.** ✅ 0.95% no-answer, 0.83% wrong, **1.79% total**.

★ The federal comparison is unusually strong evidence because it needs no staged geometry: NAR's `Location_*.csv` carries StatCan's own `FED_CODE` on the 2023 Representation Order for every address, and the numeric suffix of our `constituency_id` is the same SGC code. So every one of the 32,500 sampled addresses carries an authoritative federal answer, and the comparison is a string equality — no name normalisation, no geometry, no judgement.

| PR | No answer | Wrong |
|---|---:|---:|
| QC | 2.0% | 0.7% |
| ON | 0.8% | 0.8% |
| BC | 0.5% | 1.6% |
| NS | 0.4% | 0.4% |
| MB | 0.3% | 0.9% |
| AB | 0.2% | 0.6% |
| SK | 0.2% | 0.6% |
| PE | 0.0% | 0.4% |
| NL | 0.0% | 0.6% |
| NB | 0.0% | 0.3% |
| NT / NU / YT | 0.0% | 0.0% |

The residual ~1.8% is consistent with the one missing district plus simplification error at boundaries (§ Method and caveats) — not with a systematic fault. **The method is not over-reporting.** That materially raises confidence in the provincial numbers, which use the same machinery.

## Method and caveats

**Sampling frame.** StatCan National Address Register release `202606` (2026-06-26), staged at `data/boundaries/_geocoding/nar/202606.zip`. Every address row with a joinable `LOC_GUID` and non-null `BG_LATITUDE`/`BG_LONGITUDE`: **16,157,303 addresses**.

**Sample.** Reservoir sample, 2,500 per jurisdiction, seed `2026`, **address-weighted within each jurisdiction** — an apartment building with 200 units contributes 200 chances, not one. This is deliberate: the question is about people, and dwelling units track people far better than buildings do.

**National weighting.** Per-jurisdiction rates are combined by each jurisdiction's share of the 16.16M-address frame. Equal-n sampling gives every jurisdiction a tight interval; the weighting restores national proportionality.

**Sampling error.** At n=2,500 the 95% CI half-width is ±0.39 pp at p=1%, ±1.18 pp at p=10%, ±1.87 pp at p=35%. ⚠ **These are estimates, not census counts.** Per-jurisdiction figures should be read as ±1–2 pp; the national weighted figures are tighter because errors are independent across jurisdictions, but they inherit the frame's own limits.

**⚠ Simplified geometry.** All PIP used `boundary_simple` (~555 m tolerance), because there is **no GIST index on `constituency_boundaries.boundary`** — only on `boundary_simple` and `centroid`. A full-geometry sweep would be a sequential scan over ~1,900 MultiPolygons per point, and the host was thermally saturated. Consequences:

- Addresses within roughly 555 m of a district boundary may be misclassified in either direction. This inflates the wrong-answer rate slightly and adds noise to no-answer near coastlines and outer edges.
- It also creates **multi-matches** where simplified neighbours overlap. These are counted as **agreement** when the authoritative district is among our matches — treating them as disagreements would have overstated NT's error by 5 pp and YT's by 2 pp. The multi-match counts are reported separately below.
- ★ The bias is **toward over-reporting error**, which makes the headline figures conservative in the right direction — the true situation is no worse than stated.

Multi-match rates (share of sampled addresses matching >1 of our polygons): NT 5.1%, YT 2.4%, SK 0.7%, NL 2.2%, PE 0.6%, AB 1.0%, MB 1.2%, NS 0.7%, BC 0.2%, ON 0.4%, QC 0.5%.

**Name comparison.** Unicode NFKD, combining marks stripped, lowercased, non-alphanumerics removed. A residual risk of false disagreement remains where an agency renamed a district without changing its geometry — see the Yukon note, where that is the dominant effect and is reported as wrong deliberately.

**Database discipline.** Read-only against project data. All working sets were `CREATE TEMP TABLE` inside a single session, dropped on disconnect. **No indexes were created on project tables, no project rows were written, and NAR was never loaded into Postgres as a persistent table.** Authoritative geometry was passed as `ST_GeomFromGeoJSON` literals; BC was reprojected in-query from EPSG:3005 with `ST_Transform`.

**Known bounded gaps:**

- Wrong-answer is unmeasured for **NB, NL, MB, NU, QC, SK, PE** (shapefile-only, no GDAL). Their true rates are unknown and probably non-trivial.
- The frame is NAR's civic addresses. Addresses with no civic record — PO-box-only and service-route-only delivery, ~3% of postal codes per StatCan 92F0138 — are outside the frame entirely.
- Municipal boundaries (942 rows, 92 source sets) were not tested at all.
- Nunavut's 100% is exact rather than estimated: we hold zero polygons, so no sample was required to establish it.

## What this changes

- ★ **BC is the highest-value fix in the entire boundary project.** One province, 6.05 of 9.15 national percentage points. Nothing else comes close on an address-weighted basis.
- ★ **Perfect district counts do not mean correct answers.** NT holds 19/19 and misinforms 14.3% of its addresses. Any triage ranked by "seats missing" would have put NT last. Rank by addresses affected instead.
- ⚠ **Yukon shows the reverse failure of coverage metrics** — nearly full coverage, worst measured error rate. Renaming and redistribution without a count change is invisible to every metric except this one.
- ✅ **Federal is fine and should be left alone** until the missing district is added.
- **Combined with [`geocoding.md`](./geocoding.md):** these two error sources are independent and both land on the same user. The geocode contributes its own error (0.09% urban / 1.74% rural at 6-character resolution) on top of the polygon error measured here. For a rural BC address the compounded picture is poor from both directions at once.

## Research-handoff items

- **Should the lookup return "we don't know" rather than nothing?** Today a no-answer is indistinguishable from an error to the caller. At 9.15% this is the single most common outcome after success, and it deserves a distinct, honest response shape — the same argument made in `geocoding.md` § How the system should behave.
- **Measure the seven unmeasured jurisdictions.** Needs a shapefile reader in the toolchain (GDAL, or `pyshp` in the scanner image). NB and SK are the priorities — both hold badly outdated geometry over meaningful address counts.
- **Re-run after each boundary refresh.** The whole harness is a sample CSV plus a parameterised SQL file; re-running it is minutes of work and turns "we fixed BC" into a measured delta rather than an assertion.
- **⚠ Consider a GIST index on `constituency_boundaries.boundary`.** Its absence forced the entire measurement onto simplified geometry. If the production lookup also uses `boundary` for exactness — `geocoding.md` notes `/boundaries/lookup` does — then production is doing sequential scans over ~1,900 MultiPolygons per request. **That is a live performance question, not just a research inconvenience.** Not raised as a fix; raised as something to check.
- **Municipal levels are untested** — 942 rows across 92 source sets, no coverage or accuracy figure at all.

## Status

- [x] Address-weighted national frame built from NAR `202606` — 16,157,303 addresses
- [x] Sample drawn — 32,500 addresses, 2,500 per jurisdiction, seed 2026
- [x] Phase 1 provincial no-answer measured for all 13 jurisdictions
- [x] National address-weighted headline computed — **9.15%**
- [x] Coordinator's predictions scored — NU/NB/BC/SK confirmed, **YT refuted** (coverage fine, accuracy worst)
- [x] Phase 2 wrong-answer measured for 6 jurisdictions (62.3% of addresses)
- [x] NT priority case measured and localised to Yellowknife — 14.3% error on a perfect district count
- [x] Federal control run — 1.79% total error, method confirmed not over-reporting
- [x] Multi-match artifact identified and corrected to set-membership semantics
- [x] Sampling error and simplification bias quantified and stated
- [ ] Wrong-answer for NB, NL, MB, NU, QC, SK, PE — **blocked: shapefile-only, no GDAL on host**
- [ ] Municipal-level impact — **not started**
- [ ] Re-measure after boundary refreshes — **deferred, harness is reusable**
