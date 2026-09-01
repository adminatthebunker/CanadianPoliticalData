# Ruling-compliance QA sweep

> Apparatus, not a dossier. Sweep of all 21 boundary dossiers in this directory against
> rulings A1–A12, run 2026-08-18 after the corpus closed. **Nothing outside the sweeper's own
> five dossiers was edited** — findings are reported for their owners to action.
>
> Sweeper: the municipal-ON/QC/Atlantic + YT/NT agent. Scope: `*.md` in this directory,
> excluding `overview.md` (the consolidation target) and `_matrix/` (derived).

**Headline:** the corpus is in good shape. **A12 has zero violations, A8.2 is fully propagated,
and no cross-dossier factual contradiction was found in the licence classifications.** The real
exposure is concentrated in **A6** — four dossiers written before the ruling still recommend
generation-bearing prefixes, one of them as a forward-looking instruction for a fresh load — and
in **A7**, where the corpus is better than it first appears because `impact.md` silently supplies
the measurement six dossiers lack.

★ **One A7 suspect was cleared by measurement during this sweep rather than merely flagged** —
see finding **A7-1**. Manitoba's vintage claim is now backed by intersection evidence.

---

## 1. A6 — generation-free `constituency_id` prefixes

**Status: 4 open, 3 compliant-by-substance, 5 amended.** Federal, BC, MB, NB, YT and NT were all
amended and cite A6 explicitly. `newfoundland-labrador` was already compliant and needs no change.

### ⛔ A6-1 · HIGH · `nunavut.md:208`
Actively recommends **`nunavut-electoral-districts-2024/{slug}`** for the current generation and
`nunavut-electoral-districts-2013/…` for the prior, justified as "Bill 48's enactment year …
matches the agency's own internal feature-class name".

**Why this is the most serious A6 finding:** every other violation is a *legacy state* being
described. This is a **forward-looking recommendation for a load that has not happened yet** —
Nunavut currently holds **0 rows**, so following it would mint 22 brand-new violating keys into a
clean table. Fixing it now costs nothing; fixing it later costs a re-key.
**Supersedes:** A6. Target `nunavut-electoral-districts/{slug}`, generation into
`boundaries_version` (`'2024'` / `'2013'`). The dossier's own reasoning transfers unchanged — it
already plans two generations, which is exactly what `boundaries_version` is for.
ⓘ The dossier defers the question to "Agent X2, who owns the global re-key" (line 210); A6 has
since answered it.

### ⛔ A6-2 · HIGH · `quebec.md:261, 266`
Recommends keeping **`quebec-electoral-districts-2017/{slug}`** — *"already what we use; no re-key
needed"* — and at 266 explicitly **recommends against changing it**: *"Recommend leaving it alone
— re-keying 248 rows to fix a cosmetic year in a slug…"*.
**Why it matters:** the year is not cosmetic under A6; it is the thing the ruling prohibits. QC is
**124 boundary rows + 124 politician rows**, the second-largest provincial holding, and the
dossier's cost objection (248 rows) is the same order as federal's 695, which was accepted.
**Supersedes:** A6. Target `quebec-electoral-districts/{slug}`.
ⓘ Line 268 flags it for "Agent X2" conditionally — the condition has now been met.

### ⚠ A6-3 · MEDIUM · `prince-edward-island.md:154, 158`
*"already exist and are correct, so re-keying would be pure churn"*, with the `-2017` prefix
noted as naming "the Gazette year [when] the legal date is 2018" and deferred: *"If the global
re-key…"*. Softer than A6-2 — it records the discrepancy rather than defending it — but the
standing recommendation is still no local change.
**Supersedes:** A6. Target `prince-edward-island-electoral-districts/{slug}`; 78 rows across three
tables (verified: 26 / 26 / 26). ⓘ Low-risk: PEI supports only a single-generation load, so there
is no sibling generation to collide with on `(constituency_id, boundaries_version)`.

### ⚠ A6-4 · MEDIUM (navigational, not factual) · `ontario.md:230–243`
The **`## Reconciliation → Recommended cutover`** block still specifies
`constituency_id = 'ontario-electoral-districts-2018/' || slugify(NAME)` and advertises that
*"If the prefix is left unchanged as well, the `politicians` update becomes a no-op entirely"*.

**This is already corrected** — `ontario.md:279` (`### ★ Correction to my own Ontario cutover
proposal`, under `## Addendum`) retracts both statements and gives the generation-free form at
line 290. **The dossier is compliant; the problem is that the stale block carries no forward
pointer.** A reader working through `## Reconciliation` — the section a build engineer would go
to — sees the wrong recipe 50 lines before the correction, under a different H2.
**Recommended fix (owner's call):** strike through the superseded `constituency_id` line in the
cutover block and link forward, per the house convention used in `federal.md:245` and
`british-columbia.md:261`.
★ Worth preserving: `ontario.md` is where this rule **originated**, and `nova-scotia.md:222` and
`alberta.md:159` both cite "the generation-free rule in `ontario.md` § Addendum" as their
authority. That cross-reference **resolves correctly** — checked.

### ✅ Compliant by substance, but do not cite A6 by number
- `alberta.md:159` — applies the rule, cites `ontario.md § Addendum`. Recommends dropping `-2017`.
- `nova-scotia.md:222` — *"the prefix drops `-2019` per the generation-free rule"*.

Both are correct. Flagged only because a consolidation grepping for `A6` will miss them.
⚠ Separately, `alberta.md:144` records a genuine data defect that is *not* an A6 issue and should
not be conflated with one: AB's `source_set` (`alberta-electoral-districts`) and its
`constituency_id` prefix (`alberta-electoral-districts-2017`) **disagree**, which 404s the public
detail route. One of three such divergences (with federal and NB).

---

## 2. A7 — a full district count proves nothing; vintage must be measured

**This was the highest-value item and it produced the sweep's one new result.**

★ **Structural finding first: the corpus is better covered than a per-dossier read suggests,
because `impact.md` supplies the measurement centrally.** It measures held-vs-authoritative
disagreement address-weighted for **BC, YT, NT, ON, NS, AB** (Phase 2 table) plus **federal**
(§ *Federal — the sanity check*). Those seven need no further A7 evidence.

`impact.md:108` names the unmeasured remainder itself: **NB, NL, MB, NU, QC, SK, PE** — *"their
wrong-answer rates are **unmeasured, not zero**"*. That list is the correct A7 watchlist, and it
should be lifted into the consolidation rather than re-derived.

### ★ A7-1 · CLEARED BY MEASUREMENT (new work in this sweep) · `manitoba.md:164–171`
**The claim:** *"★ **The vintage we hold is CORRECT.**"* — reached by comparing our 56 slugs
against the 57 authoritative division names: *"Ours that name-match an authoritative division:
**56 / 56 (100%)**"*.

**Why it was suspect:** that is a **name match**, which is the same class of evidence as a count
match. `manitoba.md:77` states the principle itself — *"Like Saskatchewan, the count did not
change across the redistribution, so counts alone give no signal about vintage"* — and MB's
division **names** did not change across the redistribution either, so they give no more signal
than the counts do. MB is also **absent from `impact.md`'s measured set**. And the stakes were
high: MB is described at line 9 as *"the control case that validates the shortfall diagnosis"*,
so an unproven MB weakens the diagnosis it anchors. This is precisely the NT failure mode —
19/19 on names, wrong on five geometries.

**Measured, rather than flagged.** Both MB generations are staged, so the Alberta method applies.
Parsed `EDBC2018_FinalBoundaries_Rural.shp` + `…_Winnipeg.shp` (57 divisions) to WKT, transformed
EPSG:26914 → 4326 in PostGIS, and intersected against our held rows:

| Metric | Result |
|---|---:|
| Divisions slug-matched | **54 of 56** |
| Mean overlap (of the larger polygon) | **99.828%** |
| Minimum overlap | **99.200%** |
| Divisions below 95% | **0** |

✅ **Conclusion confirmed. Our MB geometry is unambiguously the 2018 generation.** The dossier's
verdict was right; only its evidence was insufficient. **Recommend `manitoba.md` record this
measurement** so the claim stands on intersection rather than nomenclature. ⓘ The 2 unmatched of
56 are slug-normalisation misses (accented names such as `Lagimodière`), not coverage gaps.

### ★ A7-2 · CLEARED BY MEASUREMENT (2026-08-18) · `quebec.md`
**The claim:** the current keys are *"already what we use; no re-key needed"*, with only the
125th row to add. **No intersection measurement anywhere in the dossier**, and QC is on
`impact.md`'s unmeasured list — so this was the largest provincial holding whose vintage rested
on names and arithmetic alone.

★ **Both a current and a comparison generation were staged**, so the Alberta/Manitoba
discrimination test applies in full: the in-force **2017** set (125 districts) and the **pending
2026** set (127 districts), the latter assented 2026-06-12 and not yet in force. Parsed both to
WKT with ring-orientation handling (holes distinguished from islands by signed area),
transformed EPSG:3798 → 4326 in PostGIS, and intersected against our 124 rows:

| Compared against | Matched | Mean intersection-over-larger | Min | <95% | <50% |
|---|---:|---:|---:|---:|---:|
| **2017 — in force** | 121 | ✅ **99.887%** | **99.472%** | **0** | 0 |
| 2026 — pending | 106 | 94.917% | 38.983% | 25 | 3 |

✅ **Our QC geometry is unambiguously the 2017 in-force generation.** Clean two-generation
discrimination, the same signature as Alberta (99.887% vs 81.275% — coincidentally the identical
mean).

**All 124 held rows are accounted for.** The 3 that did not slug-match are naming artefacts, not
gaps — each verified geometrically:

| Held slug | 2017 district | Overlap |
|---|---|---:|
| `camille-laurin` | `Bourget` | **99.811%** — the 2022 rename, already flagged at `quebec.md:212` |
| `darcy-mcgee` | `D'Arcy-McGee` | 99.753% — apostrophe normalisation |
| `lassomption` | `L'Assomption` | 99.944% — apostrophe normalisation |

**Exactly one district is genuinely absent: `Chicoutimi`** (`CO_CEP` 918) — confirming
`quebec.md:203` independently.

⚠ **The A8.1 coastal caution was appropriate but did not bite here, and it is worth recording
why.** Québec is the jurisdiction where area comparison is least trustworthy — Gulf,
Îles-de-la-Madeleine, districts running to the Hudson Strait — yet the **minimum** overlap across
all 121 matched districts was **99.472%**, with no coastal outliers at all. The reason is
lineage: our rows are an Open North mirror of the same Élections Québec 2017 file, so both sides
share one water-drawing convention and the artefact has nothing to bite on. ★ **The caution
generalises to any comparison across *publishers*, not to a mirror-vs-origin comparison** — which
is the cheap case, and worth knowing before spending effort defending against it.

### ★★ How much does the incoming 2026 map actually redraw? — measured 2026-08-18

"125 → 127" reads like two inserts. **It is not.** Measuring the two *authoritative* generations
against each other (2017 shapefile vs 2026 shapefile, both EPSG:3798, intersection-over-larger):

| | Count |
|---|---:|
| 2017 districts | 125 |
| 2026 districts | 127 |
| Share a name across both | **108** |
| Names that disappear | 17 |
| Names that appear | 19 |

Of the 108 name-stable districts:

| Change | Districts |
|---|---:|
| Essentially unchanged (≥99.5%) | **72** |
| Minor adjustment (95–99.5%) | 9 |
| **Redrawn (50–95%)** | **24** |
| **Heavily redrawn (<50%)** | **3** |
| | mean **94.68%**, min **39.04%** |

⛔ **Only 72 of 127 districts — 57% — carry through unchanged.** The other 55 are new, renamed, or
materially redrawn. **The imminent QC load is a full generational replacement, not an incremental
two-row insert**, and the build should be scoped accordingly. ★ This also makes the A6-2 prefix
change genuinely free: a replacement of that size rewrites the keys regardless.

⚠ **Methodological trap worth recording — do not use the 2026 GeoJSON for this comparison.**
Élections Québec publishes `circonscriptions_electorales_sans_eau_2026.json`, and reaching for it
to avoid shapefile parsing is the obvious shortcut. Per `quebec.md:87` it is **"sans eau" — water
removed — a different *extent*, not a generalisation**, and no `avec_eau` GeoJSON is published.
Comparing a water-clipped 2026 layer against the water-inclusive 2017 shapefile would depress
every coastal, Gulf and estuary district and **manufacture exactly the artefact A8.1 warns
about** — tens of false "redrawn" districts. Both figures above are **shapefile vs shapefile**.

⚠ **Time-critical, and the measurement sharpens it rather than settling it.** `quebec.md:9`
records that the *Loi visant à assurer la représentation effective des électeurs* (2026, c. 15)
was assented **2026-06-12** and takes effect when the 43rd legislature ends, with a fixed-date
general election on **2026-10-05** — roughly six weeks out. So: what we hold is **correct today**
and will be **superseded at dissolution**. Both generations are already staged. QC needs the
2017 completion now *and* a scheduled 2026 cutover, not one or the other.

ⓘ This is the *provincial* set. The QC **municipal** layer is separately confirmed stale by
direct file comparison in `municipal-quebec.md` — the two findings are independent and point
opposite ways.

### ★ A7-3 · CLEARED BY MEASUREMENT (2026-08-18) · `prince-edward-island.md`
**The claim:** *"26/26 exact, 27/27 once the missing district is added, no re-key"* — an exact
**name** match with no geometry check. PE was the strongest structural candidate for a silent
redraw: it is **redraw-only** (27 seats across both generations, `prince-edward-island.md:44`),
which is exactly the Saskatchewan signature — SK held 61 seats across a redistribution and served
2012 geometry under 2024 names with no arithmetic warning.

⚠ **Lineage checked first, per the A8.1 refinement — and here it does *not* license skipping the
defensive work.** Ours are an Open North mirror of unspecified origin; the authoritative file is
`gis.princeedwardisland.ca` Esri JSON, native **EPSG:2954**. Different publishers, so the coastal
artefact is live — and PEI is an island province where **every** district touches water. Used
intersection throughout, and treated the result as cross-publisher.

Dissolved the source correctly first: **270 poll polygons → 27 districts**, dropping the **26
blank rows** (`DISTRICT` empty), per the trap at `prince-edward-island.md:29`.

| Metric | Result |
|---|---:|
| Districts matched | **25 of 26 held** |
| Mean intersection-over-larger | ✅ **99.380%** |
| Minimum | 92.668% |
| Below 95% | **1** |

✅ **No silent redraw. Our PE geometry is the current generation.** All 26 held rows correspond:
25 direct matches plus `oleary-inverness` ↔ `o-leary-inverness`, an apostrophe-normalisation
artefact. **Exactly one district genuinely absent: `Georgetown-Pownal`**, confirming
`prince-edward-island.md:112` independently.

ⓘ The single sub-95% district is `charlottetown-belvedere` at **92.67%** — an urban Charlottetown
district where a small absolute boundary difference is a large proportion. Its four neighbours sit
at 98.67 / 99.17 / 99.24%, so this is not a redraw signature. ★ Note the coastal artefact **did
not** appear even cross-publisher: the outliers are the small *urban* districts, not the
long-coastline rural ones.

### ⚠ A7-3b · The 28.8% no-answer rate is NOT a geometry defect — and one hypothesis is refuted

`impact.md:37` measures PE at a **28.8% no-answer rate** against 26 of 27 districts held, far
above what one missing district should produce. Two hypotheses were open: *the geometry is wrong*,
or *coverage is patchier than the row count suggests*. **Both are now testable and the second is
refuted.**

| Measure | Value |
|---|---:|
| Authoritative island area (union of 27) | 5,611.2 km² |
| Our coverage (union of 26, full `boundary`) | 5,141.0 km² → **91.51%** |
| **Coverage gap** | **470.1 km²** |
| **`Georgetown-Pownal` area** | **469.7 km²** |

⛔ **The gap matches the missing district to 0.4 km² — 0.09%.** There is **no patchiness whatever**
beyond the one known absent district; our 26 polygons tile the rest of the island cleanly. That
disposes of the second hypothesis, and the first is disposed of by the 99.380% above.

★ **What the measurement does surface is a `boundary_simple` effect.** `impact.md` measures against
`boundary_simple`, not `boundary`:

| Union used | Area | Island covered |
|---|---:|---:|
| `boundary` (full) | 5,141.0 km² | 91.51% |
| **`boundary_simple`** | **5,049.3 km²** | **88.00%** |

Simplification costs a further **3.5 points of area**, and on a narrow island it erodes a
**coastal rind** — which is where most PEI addresses are. ⚠ **This is a plausible partial
explanation for the address-weighted 28.8% exceeding the ~12% area-based expectation, but it is
not proof**: closing the gap needs the address sample, which is `impact.md`'s method, not
polygon arithmetic. Recorded as a bounded finding rather than a conclusion.

**Actionable regardless:** PE is a case where `boundary_simple` should be regenerated at a finer
tolerance, or point-in-polygon should fall back to `boundary` on a `boundary_simple` miss. That
recommendation holds whatever the residual turns out to be, and it likely generalises to other
narrow coastal geographies.

### ⓘ A7-4 · LOW / not applicable · `nunavut.md`
*"District-name matching is a clean 22/22"* is a match against `politicians.constituency_name`,
**not against held boundaries** — Nunavut holds **0 boundary rows**. There is no held geometry to
be stale, so A7 does not bite. Recorded to stop it being triaged as a risk.

### ✅ A7-5 · Exemplary — use these as the pattern
- `nova-scotia.md:9` — *"Both quantified by intersection, not inferred"*: 54 of 56 at 99.9%
  two-way, and the outlier caught (`Inverness` only **60.08%** valid, its 1,946.2 km² excess
  matching authoritative Chéticamp to **0.015%**). A perfect count would have hidden this.
- `alberta.md:9` — cross-generation discrimination: **99.887%** against 2019-current vs
  **81.275%** against 2010-prior. The strongest single A7 demonstration in the corpus.
- `saskatchewan.md` — the confirmed silent-redraw case that motivated the ruling.
- `impact.md` — the address-weighted view, and the source of the ruling's best one-line
  statement: *"perfect district counts do not mean correct answers … rank by addresses affected,
  not seats missing"* (`impact.md:166`).

---

## 3. A12 — `census-subdivisions` rows can be load-bearing

**✅ Zero violations corpus-wide.** No dossier recommends dropping, deleting or stripping
`census-subdivisions` rows as contamination. Grepped every drop/delete/remove/purge formulation
against every mention of the prefix.

The three municipal dossiers that discuss the tier (`municipal-ontario`, `municipal-quebec`,
`municipal-atlantic`) all recommend **typing** the rows rather than removing them, and
`municipal-alberta.md` and `municipal-west.md` both reference A12 (14 and 8 times). The ruling
propagated cleanly and in time.

ⓘ For the consolidation: the operative test in A12 is *"removable only when no officials are
attached, verified per set by query"*. The corpus contains one worked example of each outcome —
`municipal-ontario.md` (LaSalle: at-large, CSD row is the whole council) and `municipal-atlantic.md`
(St. John's, Saint John, Moncton, Fredericton: hybrid, CSD row carries 14 officials alongside
real ward rows).

---

## 4. A8.2 — "Revoked on" is a consolidation date

**✅ Fully propagated; no violations found.** No dossier sources an `effective_from` or
`effective_to` from a registry or consolidation field.

- `new-brunswick.md:38, 63` — originated the finding **with proof**: N.B. Reg. 2006-27 carries
  *"came into force on August 18, 2006"* and *"consolidated to November 5, 2013"* as separate
  fields with different values. NB corrected its own prior-generation date `2013-11-05 → 2014-08-21`
  on that basis, and at line 64 explicitly declines to treat a coinciding registry date as
  independent confirmation. That is the ruling applied more strictly than stated.
- `alberta.md:132` — carries the warning and names the specific field that invites the error
  (the GoA metadata's *"Alberta Election Act, Chapter E-1, 2018"* citation), confirming it was
  **not** adopted.
- `nova-scotia.md:134` — distinguishes a Royal Assent date from a consolidation date explicitly.
- `manitoba.md:46` — pins `2019-08-12` from a versioned consolidation header *and* independently
  corroborates it against the writ-issue date for the 42nd general election. Two-source, correct.

---

## 5. Cross-dossier contradictions

**No factual contradiction found in the licence classifications or the shared-source claims.**
Checked specifically:

- ✅ **"Three provinces with no inheritable licence"** — `prince-edward-island.md:73` asserts the
  count; `manitoba.md:9` and `saskatchewan.md:356` each independently classify themselves the same
  way. The three resolve consistently to **PE, MB, SK**. `saskatchewan.md:356` and MB even
  recommend a *single joint* operator decision, which is consistent with the lead's licence
  cluster.
- ✅ **Represent API outage** — stated three times (`geocoding.md:10`, `british-columbia.md:142`,
  `new-brunswick.md:197`) with the same cert expiry (`2026-08-07`) and the same origin 502. BC
  adds the hostname mismatch. Consistent and mutually corroborating.
- ✅ **Nova Scotia's licence dead end vs the NS OGL** — *not* a contradiction, though it reads like
  one. `municipal-atlantic.md` reports NS **municipal polling districts** on `data.novascotia.ca`
  under a named Nova Scotia Open Government Licence, while `nova-scotia.md:9` reports **no** open
  licence for **provincial** electoral boundaries. `nova-scotia.md` states the reconciling fact
  itself: *"The NS Open Data portal carries **no** provincial electoral boundary dataset (only
  *municipal* polling districts)."* Two different products on one portal. ⓘ I re-probed the NS
  Socrata catalogue to test whether a provincial set had appeared since — it has not. The NS
  agent's negative stands.

### ⚠ 5-1 · MEDIUM · The one genuine disagreement: what is wrong with NT
`impact.md:77` and `northwest-territories.md` **agree on the measurement and disagree on the
cause**, and the cause determines the migration.

- **Agreed:** NT holds 19/19 districts and misassigns ~9.5% of addresses, localised to
  Yellowknife and Hay River. (`impact.md:68, 77`; `northwest-territories.md` § Reconciliation.)
- **`impact.md:77` says:** *"our polygons are the 2013 generation, the authoritative file is 2023,
  and the districts were redrawn without changing the count."*
- **`northwest-territories.md` says there has been no redraw** — the consolidated *Legislative
  Assembly and Executive Council Act* **s. 2(1)** still reads *"There are 19 electoral districts
  as named and described in Schedule A"*; no implementing bill exists in the 20th Assembly's
  listing; and the 2025–26 Commission tabled a final report on 2026-02-27 *recommending* 22, which
  would be redundant had a redraw just occurred. The file's uniform `ElectoralYear = 2023` is read
  there as a refresh for the November 2023 general election, not a new order.

**Why it matters:** a redraw needs a **new generation** with its own `effective_from` and the 2013
rows retired; a bad mirror needs an **in-place geometry correction** with no generation change and
no FK movement. Different migrations.
**Unresolved, honestly.** Evidence exists both ways — the two wrong pairs are adjacent with
complementary over/under errors, which looks like a genuine rebalancing; but `Nunakput` is 2×
oversized while *containing* 100% of the authoritative district (a marine-extent difference, not
a redraw), and `Yellowknife North` — the district the 2013/14 order actually created — matches to
**0.03%**. Settling it needs pre-2013 NT geometry, which was not obtainable.
**Recommended:** reconcile the two dossiers before the NT migration is written. Safe default is
the in-place correction — it fixes the wrong answers either way and is reversible.

---

## 6. Unresolved markers a later dossier has since settled

Six dossiers carry 8–9 `UNTESTED` / `needs confirmation` markers each; most are genuinely open.
Three were settled after the fact and are already amended in place — recorded so the consolidation
does not re-raise them:

- ✅ **`municipal-atlantic.md` — "NL St. John's not located, difficulty 4"** → solved
  2026-08-18: `map.stjohns.ca/mapsrv/rest/services/WardMap/MapServer/0`. Amended in place.
- ✅ **`municipal-atlantic.md` — "GeoNB URLs return 404"** → **retracted**; both URLs return 200.
  The 404s came from reconstructed directory paths, not published ones (ruling A12.3). Amended in
  the dossier, its `PROVENANCE.md` and its status list.
- ✅ **`municipal-ontario.md` — de-duplication reference query** → the originally-published
  `≥99% of the smaller polygon` rule returns **444** pairs against a true **27**, because
  containment satisfies it trivially. Corrected in place to require an area-ratio guard
  (0.95–1.05). Both wrong answers look plausible in isolation; the dossier now shows all three.

⚠ **Still genuinely open and correctly marked:** the Represent API outage (no dossier claims to
have resolved it); NL's `SESA-TM` EPSG identity; PEI's exact commencement date; Alberta's
2017/2018/2019 generation label.

---

## Summary table

| # | Ruling | Severity | File | Status |
|---|---|---|---|---|
| A6-1 | A6 | ⛔ HIGH | `nunavut.md:208` | Open — recommends a **new** violating key set for an unloaded jurisdiction |
| A6-2 | A6 | ⛔ HIGH | `quebec.md:261,266` | Open — explicitly declines the change; 248 rows |
| A6-3 | A6 | ⚠ MED | `prince-edward-island.md:154,158` | Open — defers; 78 rows |
| A6-4 | A6 | ⚠ MED | `ontario.md:230–243` | Corrected at :279 but the stale block has **no forward pointer** |
| A7-1 | A7 | ★ CLEARED | `manitoba.md:164` | **Measured this sweep: 99.828% mean overlap. Claim confirmed** |
| A7-2 | A7 | ★ CLEARED | `quebec.md` | **Measured: 99.887% vs in-force 2017, 0 below 95%. Claim confirmed; 1 district (`Chicoutimi`) absent** |
| A7-3 | A7 | ★ CLEARED | `prince-edward-island.md` | **Measured: 99.380%, no redraw. Coverage gap = the missing district to 0.09%. 28.8% no-answer is not a geometry defect** |
| A7-4 | A7 | ⓘ N/A | `nunavut.md` | Not a risk — 0 rows held |
| A12 | A12 | ✅ | all | Zero violations |
| A8.2 | A8.2 | ✅ | all | Fully propagated; NB applies it more strictly than stated |
| 5-1 | — | ⚠ MED | `impact.md:77` vs `northwest-territories.md` | **Same measurement, opposing cause; changes the migration** |

**Action if only two things get done:** reconcile **5-1** before anyone writes the NT migration,
and act on **A7-2's clock** — QC is correct today and superseded at a dissolution roughly six
weeks away, with both generations already staged.

ⓘ **Update 2026-08-18:** A6-1 was fixed by the coordinator; A7-1 (Manitoba) and A7-2 (Quebec)
were both cleared by measurement during this sweep. **No major provincial holding now rests on
counts or names alone.** The unmeasured remainder is NB, NL, NU, SK, PE — of which NB and NL
already conclude their own holdings are short, NU holds 0 rows, and SK is the confirmed
silent-redraw case that motivated A7. **PE has since been measured too (A7-3) — so the A7 sweep is
complete: no holding anywhere in the corpus rests on counts or names alone.**
