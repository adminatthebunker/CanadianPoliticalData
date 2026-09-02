# Municipal Atlantic — Electoral Boundary Research

> Standalone boundary dossier for Atlantic Canada municipal wards and districts —
> **9 source sets / 83 rows** across NS, NB, PE and NL. Cross-cutting context (methodology,
> licence matrix, reconciliation strategy) lives in [`overview.md`](./overview.md); my matrix
> rows are in [`_matrix/municipal-atlantic.md`](./_matrix/municipal-atlantic.md).
> This dossier owns **boundaries only**.

**Agencies:** four provincial regimes — Nova Scotia Open Data + HRM's own AGOL (NS); Service New Brunswick / GNB Socrata (NB); Elections PEI (PE); municipal only (NL) | **Sets held:** 9 | **Rows held:** 83 | **Real ward polygons:** 74 | **Redistribution trigger:** per-province municipal election cycle, all four staggered

**Status snapshot (2026-08-18):** ✅ **This is the healthiest municipal block in the corpus, and the cleanest reconciliation in any of my four dossiers.** **Zero orphans** — all 83 rows have a matching official, against 12 in Ontario and 5 in Québec. **Zero Peel-shape duplication** — every PIP returns exactly 2 polygons, never 3 or 4. Ward counts match council for 8 of 9 sets. ✅ **NS and NB are fully solved from two province-wide files**: `data.novascotia.ca` publishes *Municipal Polling Districts* (238 districts / 49 municipalities, NS OGL) and `gnb.socrata.com` publishes *Ward boundaries for Local Governments and Rural Districts* (330 wards / 90 local governments, OGL–NB) — **Halifax 16 ✅ and Cape Breton 12 ✅ both match exactly what we hold**. ★ **The `census-subdivisions` rows here are NOT contamination in the Ontario sense — they are load-bearing.** Atlantic councils are *hybrid*: the CSD polygon carries the mayor and the at-large councillors (St. John's 6, Saint John 3, Moncton 3, Fredericton 2) while the ward polygons carry the ward councillors. Deleting them would orphan 14 sitting officials. ⛔ **But Halifax is the single worst case in the corpus for the `lookupBoundariesAtPoint` overwrite bug — a 703× area ratio**, 5,957 km² CSD against an 8.5 km² district. ⛔ **PE is the one genuine blocker**: no machine-readable ward source found for any of the three PEI municipalities; Elections PEI publishes ward and poll **maps** only. ⚠ Three of four provinces have live staleness triggers — NB voted **2026-05-11**, NL voted **2025-10-02**, PE votes **2026-11-02**.

---

## Platform families

Atlantic is the **four-regimes** case: too small for a single federation, too varied to treat as
one. It also adds a platform family neither ON nor QC needed — **Socrata**.

**Family A — Socrata, province-wide (NS and NB). ★ The good news, and it covers 6 of 9 sets.**
Both provinces run Socrata instances publishing a *single province-wide municipal ward layer*,
so there is no per-municipality discovery problem at all — the opposite of Ontario:

| Province | Host | Dataset | Coverage | Licence |
|---|---|---|---|---|
| NS | `data.novascotia.ca` | `gcep-xeci` *Municipal Polling Districts* | **238 districts / 49 municipalities** | Nova Scotia Open Government Licence |
| NB | `gnb.socrata.com` | `7zs3-pcvk` *Ward boundaries for Local Governments and Rural Districts* | **330 wards / 90 local governments** | Open Government Licence – New Brunswick |

Both expose `?method=export&format=GeoJSON` on `/api/geospatial/<id>`, plus CSV and FGDB. **One
GET each; difficulty 1.** Between them they cover Halifax, Cape Breton, Fredericton, Moncton and
Saint John — five of our nine sets — and NS's file was refreshed **2025-11-19**.

✅ **GeoNB is alive — my earlier 404 report was wrong, and the mistake is worth recording.**
I initially reported both GeoNB downloads as dead. They are not. The brief gave me *filenames*
without directory paths, and I **reconstructed** paths from those filenames
(`/downloads2/mred/`, `/downloads2/lg_gl/`) instead of using the NB dossier's actual URLs. My
reconstructions 404; the real paths return HTTP 200:

| URL | Status | Bytes |
|---|---|---:|
| `https://geonb.snb.ca/downloads/mun_electoral_districts/geonb_mred-cerm_shp.zip` | ✅ 200 | 956,278 |
| `https://geonb.snb.ca/downloads/lg/geonb_lg_gl_wards_quartiers_shp.zip` | ✅ 200 | 4,266,202 |

⚠ **The generalisable lesson (ruling A12.3): a 404 on a *reconstructed* path is evidence about
the reconstruction, not about the resource.** Same filenames, different directories. Never
report a URL dead unless it is the URL someone actually published.

ⓘ **Both routes work, so the choice is format, not availability.** GeoNB serves zipped
shapefiles; the Socrata mirror serves GeoJSON directly plus CSV and FGDB, and supports
server-side SoQL filtering — which matters because the NB file is 330 wards fetched for 3
cities. **Socrata was staged on those grounds.** GeoNB remains the publisher of record, and the
licence conclusion the NB agent reached (open, no flow-down) is unaffected either way.

**Family B — municipal ArcGIS Online (NS Halifax, NB Saint John).** Halifax Regional
Municipality runs `hrm.maps.arcgis.com` (org `halifax_agol`) and publishes
`ADM_Polling_District2024` as a FeatureServer. ★ **It carries a `COUNCILLOR` field** — boundary
and roster in one layer, the same shape as Toronto's `wards-and-elected-councillors` and the
only other example in the corpus. Saint John runs `catalogue-saintjohn.opendata.arcgis.com`.
Both are redundant with the province-wide Socrata files but useful as cross-checks, and
Halifax's councillor names are directly reconcilable against `politicians`.

**Family C — PDF/paper only (PE). ⛔ The genuine blocker.** No machine-readable ward source was
found for Charlottetown, Summerside or Stratford. `data.princeedwardisland.ca/api/3` returns
**404** (no CKAN), ArcGIS Hub has no PEI ward layer, and `gov.pe.ca/gis` publishes municipal
*boundaries* but no ward layer. Elections PEI publishes **"Municipal Ward and Poll Maps"** at
https://www.electionspei.ca/municipal-ward-and-poll-maps and Charlottetown publishes ward maps
at https://www.charlottetown.ca/resident_services/maps — both **map products, not data**.
**Difficulty 5.** Raised as a handoff item; not invented around.

**Family D — municipal ArcGIS Server, unadvertised (NL). ✅ SOLVED 2026-08-18 — difficulty 1.**
St. John's runs its **own ArcGIS Server**, not ArcGIS Online, which is why every portal-level
probe missed it. Service root `https://map.stjohns.ca/mapsrv/rest/services`; the ward layer is
**`WardMap/MapServer/0`, named `WARDS_wCouncillorInfo`** — open, unauthenticated, GeoJSON via
`?f=geojson`.

**How it was found**, since the route generalises: the city's MapCentre viewer
(`map.stjohns.ca/mapcentre/`) loads the ArcGIS JS API 4.23, so a service had to exist. The page
HTML contains no service URLs, but its `js/layers.js` bundle does — one `grep` for
`rest/services` over that file yielded `map.stjohns.ca/mapsrv/...`. ★ **When a municipal viewer
is an Esri app, the service URL is in the viewer's JavaScript, not its HTML.** Neither
`/arcgis/rest/services` nor `/server/rest/services` resolves on that host (both 404), so
guessing the conventional path would have failed — `mapsrv` is a custom mount.

⚠ **False-positive trap:** ArcGIS Online keyword searches for "St. John's ward" return dozens of
hits for **St. John the Baptist Parish, Louisiana** (owner `J-Mann`), which look plausible at a
glance. None are Newfoundland.

- **CRS:** service reports `wkid: 32181` = **EPSG:32181, NAD83 / MTM zone 1** (the Newfoundland
  MTM zone). The staged copy was exported `outSR=4326`, so no reprojection is needed at load.
- **Attribute schema:** `WARD` (Integer), `WARDNAME`, `COUNCILLOR`, `ROLE`, `ROLE2`,
  `COUN_PHONE`, `COUN_FAX`, `COUN_EMAIL`, `COUN_HLINK`, `MAP_HLINK`, `WARDMAP_LINK`,
  `COUN_IMAGE`, `POP2001`, `ID`, `OBJECTID`, `GlobalID`. ⓘ `POP2001` dates the attribute table's
  origin to the 2001 census era.
- **Licence:** ⛔ **none stated** — no `copyrightText`, no `licenseInfo`, no terms on the service
  or the viewer. The only Atlantic source with no licence at all, and unlike Toronto there is not
  even a portal-level licence to point at. Raised as a handoff item.

### ★★ The St. John's layer independently confirms ruling A12 — and our roster beats the city's

The layer returns **11 features: 5 ward polygons (`WARD` 1–5) and 6 rows at `WARD = 0`** carrying
the Mayor, Deputy Mayor and four Councillors-at-Large, each with a city-wide geometry. **The City
of St. John's models hybrid representation exactly the way our schema does** — at-large members
get a whole-municipality polygon alongside the ward polygons. That is independent, publisher-side
confirmation that the `census-subdivisions` row in `st-johns-wards` is correct data rather than
contamination, arrived at from the opposite direction.

⚠ **But the city layer's councillor attributes are stale, and ours are not.** Checked against the
2025-10-02 official results:

| Ward | City layer | 2025 official | |
|---|---|---|---|
| 1 | Jill Bruce | Jill Bruce | ✅ |
| 2 | Ophelia Ravencroft | **Brenda Halley** | ⛔ stale |
| 3 | Greg Noseworthy | Greg Noseworthy | ✅ |
| 4 | Tom Davis | Tom Davis | ✅ |
| 5 | Carl Ridgeley | **Donnie Earle** | ⛔ stale |
| Deputy Mayor | Sheilagh O'Leary | **Ron Ellsworth** | ⛔ stale |
| At-large | Burton, Hanlon, Hickman, Ellsworth | **Cadigan, Hammond, Hickman, Ryall** | ⛔ stale |

★ **Our `politicians` rows are the 2025 council, complete and correct** — Breen (mayor),
Ellsworth (deputy), Cadigan / Hammond / Hickman / Ryall (at-large), Bruce / Halley / Noseworthy /
Davis / Earle (wards 1–5). ⚠ **So take the geometry from this layer and ignore its `COUNCILLOR`
field.** A build that trusted the authoritative source's roster attributes would *downgrade* our
data by four years. Contrast Halifax, whose `COUNCILLOR` field is current — the field's existence
does not imply its currency, and it has to be checked per source.

## ★ The `census-subdivisions` rows here are load-bearing — ruling A12 (superseding A10.3)

All 9 Atlantic sets carry exactly one `census-subdivisions/<CSD>` row — a **100% contamination
rate**, higher than Ontario's 83% or Québec's 92%. But the Atlantic case is materially
different, and applying the Ontario fix unchanged would break real coverage.

**These councils are *hybrid*, not at-large-or-ward.** The same municipality elects some
councillors by ward and others at large, and the two tiers of polygon are doing different jobs:

| Municipality | Officials on the CSD polygon | Officials on ward polygons |
|---|---:|---:|
| St. John's, NL | **6** (mayor, deputy mayor, 4 councillors-at-large) | 5 ward councillors |
| Saint John, NB | **3** | 8 across 4 wards (2 each) |
| Moncton, NB | **3** | 8 across 4 wards (2 each) |
| Fredericton, NB | **2** | 12 across 12 wards |

St. John's is the textbook case and the counts confirm it exactly: council is a mayor, a deputy
mayor, **four councillors-at-large** and **five ward councillors** — 6 on the CSD row, 5 on the
wards. ⚠ **The brief lists St. John's as a plausible at-large candidate; it is not.** It is
hybrid, and so are all three New Brunswick cities.

★ **So ruling A10.3 needed a third category — now issued as ruling A12.** The existing distinction is *at-large*
(legitimate, no data can exist — Ontario's LaSalle) vs *gap* (real ward file exists —
Whitchurch-Stouffville). Atlantic adds **hybrid**: the municipality has real wards *and* real
at-large seats, so the CSD polygon must be **retained alongside** the ward polygons rather than
removed as contamination. Under the A10.2 three-valued `boundary_kind`, these rows are
`municipality` and they are correct — the fix is to *type* them, never to delete them.
⚠ A migration written from the Ontario dossier that drops CSD rows from ward sets would orphan
**14 sitting Atlantic officials**.

⛔ **The PIP defect is still real, and Halifax is the worst instance in the corpus.** Every
Atlantic point returns exactly 2 polygons — ward + CSD — but the *size disparity* is extreme,
which is what makes the `lookupBoundariesAtPoint` overwrite bug so damaging here:

| Set | CSD km² | Smallest ward km² | Ratio |
|---|---:|---:|---:|
| `halifax-districts` | 5,956.9 | 8.5 | **703×** |
| `cape-breton-districts` | 2,558.5 | 6.0 | **430×** |
| `fredericton-wards` | 139.4 | 2.4 | 58× |
| `summerside-wards` | 28.5 | 0.7 | 43× |
| `st-johns-wards` | 476.9 | 11.0 | 43× |
| `charlottetown-wards` | 52.8 | 1.8 | 29× |
| `saint-john-wards` | 364.2 | 13.7 | 27× |
| `stratford-wards` | 26.0 | 3.5 | 7× |
| `moncton-wards` | 146.3 | 23.7 | 6× |

For comparison the Mississauga case the lead verified is ~104×. A downtown Halifax resident whose
district is 8.5 km² can be told their municipal boundary is *Halifax Regional Municipality* —
5,957 km², reaching from Peggy's Cove to the Musquodoboit Valley. **The smallest-matching-polygon
resolver rule fixes this everywhere in the block**, and Atlantic is the strongest argument for
it because the failure is so visually absurd.

## ★ No Peel-shape duplication — and the structural reason why

The brief flagged Halifax Regional Municipality as structurally Peel-shaped and worth testing
specifically. **Tested; it is not, and the reason generalises.**

Point-in-polygon at six Atlantic city centres returns **exactly 2 polygons every time** —
never 3 or 4. There is no regional set restating lower-tier wards, and no ward exists under two
ID schemes anywhere in the block.

★ **Peel-shape duplication requires a *surviving* two-tier structure.** Peel Region is an upper
tier whose three lower-tier municipalities — Brampton, Caledon, Mississauga — each kept their
own council, so both tiers have wards and both got ingested. **Atlantic amalgamations dissolved
the lower tier**: HRM (1996) and CBRM (1995) absorbed their constituent towns into a single
municipality with a single council. There is one layer because there is one council. Same for
Ontario's own amalgamated single-tier cities — Toronto, Hamilton, Ottawa, Greater Sudbury all
show 2 matches, not 4.

**Diagnostic worth reusing:** duplication risk tracks *two-tier governance*, not *amalgamation
history*. Ontario's remaining two-tier regions (Peel, and by inspection Niagara, Waterloo and
Lambton, which appear as `census-divisions/` rows in the `census-subdivisions` set) are where to
look; amalgamated single-tier cities are safe.

## Ward counts vs council — 8 of 9 correct

Unlike Montréal (39 of 59) or Belleville (2 of 6), the Atlantic sets are essentially complete.
Verified against the authoritative province-wide files where they exist:

| Set | Held wards | Authoritative | Verdict |
|---|---:|---:|---|
| `halifax-districts` | 16 | **16** (NS Socrata + HRM AGOL) | ✅ exact |
| `cape-breton-districts` | 12 | **12** (NS Socrata) | ✅ exact |
| `moncton-wards` | 4 | **4** (NB Socrata) | ✅ exact |
| `saint-john-wards` | 4 | **4** (NB Socrata) | ✅ exact |
| `fredericton-wards` | 12 | **13** (NB Socrata) | ⚠ **short by one** |
| `st-johns-wards` | 5 | **5** (WardMap layer) | ✅ exact |
| `charlottetown-wards` | 10 | 10 (council composition) | ✅ consistent |
| `summerside-wards` | 8 | 8 (council composition) | ✅ consistent |
| `stratford-wards` | 3 | ⚠ unverified — no source | `needs confirmation` |

⚠ **The one gap is precise and explains itself.** Fredericton's authoritative ward labels are
`1, 2, 3, 4, 4-Lincoln, 5, 6, 7, 8, 9, 10, 11, 12` — thirteen entries, because
**`4-Lincoln`** is a distinct sub-ward created when Lincoln was annexed to Fredericton under
New Brunswick's **2023 local governance reform**. We hold `ward-1` … `ward-12` and are missing
`4-Lincoln` exactly. ★ That single missing row is also evidence our NB sets are **pre-reform**:
the 2023 reform reorganised NB into 90 local governments and rural districts, which is why the
authoritative dataset is titled *"Ward boundaries for Local Governments and Rural Districts"*
rather than *municipalities*.

## Staleness — three of four provinces, staggered

Atlantic has neither Québec's single synchronised trigger nor Ontario's fully discretionary
chaos. Each province runs a fixed quadrennial municipal cycle, but the four are **out of phase**,
so this block needs four dates rather than one:

| Province | Last municipal election | Our sets | Next |
|---|---|---|---|
| **NS** | Oct 2024 | ✅ **current** — HRM layer is literally named *Electoral Districts (2024 Election)* and reconciles 16/16 | 2028 |
| **NB** | ⚠ **2026-05-11** (three months ago) | ⛔ **pre-election, and pre-2023-reform** — the missing Fredericton `4-Lincoln` ward is the tell | 2030 |
| **NL** | **2025-10-02** (moved from Sept 30 to avoid the National Day for Truth and Reconciliation) | ✅ **roster is the 2025 council, verified line-by-line against official results**; boundaries stable — the last documented St. John's ward change was for the **2017** election, and no 2025 change was found | 2029 |
| **PE** | Nov 2022 | ⚠ current-ish, but **2026-11-02 is 2.5 months away** | 2026-11-02 |

⚠ **NS and NL are both current** — NS confirmed 16/16 against the 2024 map, NL confirmed roster-complete against the 2025 results with no ward-boundary change since 2017. ⓘ **This corrects my first pass**, which listed NL as behind its election; the probe showed our roster is current and it is the *city's own layer* that is four years stale. **NB is the one province genuinely behind an election.** PE is in front of one. ★ Combined with the Ontario 2026-10-26 date already on the build schedule, **the autumn
of 2026 contains two municipal elections that will stale our data (ON, PE)** — worth treating as
one scheduling constraint rather than two.

## Ruling A6

✅ **No violations.** No Atlantic `source_set` carries a year in its prefix — checked all 9.

⚠ Same latent problem as everywhere else: `boundaries_version = 'current'` and
`effective_from = '2023-01-01'` on all 83 rows, so no set records its generation. ★ Under
**ruling A10.4** the municipal in-force date is the municipal election date the boundaries first
governed, which for Atlantic is cheap and unambiguous — four dates for nine sets:

| Sets | `effective_from` |
|---|---|
| `halifax-districts`, `cape-breton-districts` | 2024-10-19 (NS municipal election) |
| `fredericton-wards`, `moncton-wards`, `saint-john-wards` | 2026-05-11 **once re-harvested**; currently the 2022-05-09 map |
| `st-johns-wards` | 2025-10-02 **once re-harvested**; currently the 2021-09-28 map |
| `charlottetown-wards`, `summerside-wards`, `stratford-wards` | 2022-11-07 (PE municipal election) |

No by-laws to chase, exactly as A10.4 intends.

## Postal-code correspondence

⛔ None published by any Atlantic province or municipality. Point-in-polygon is the mechanism,
subject to the smallest-polygon fix above. ⓘ Atlantic FSAs are coarse — `B3H` covers much of
peninsular Halifax across several districts — so 3-character lookups here carry the same
low-confidence caveat noted for the territories.

## Terms / Licensing

- **NS — Nova Scotia Open Government Licence.** `license.name` on `gcep-xeci` reads
  *"Nova Scotia Open Government Licence"*, terms at http://novascotia.ca/opendata/licence.asp.
  ✅ Machine-readable and asserted in the metadata, unlike Toronto's.
  ★ **This answers the brief's question directly: the municipal route is cleaner than the
  provincial one.** Elections NS's only surface is an internal AGOL service with
  `licenseInfo: null`, a dead end — but NS's *municipal* polling districts are on the open
  provincial Socrata portal under a named, linked licence. The two are unrelated products.
- **NB — Open Government Licence – New Brunswick**, asserted as `license_title` on the
  federated open.canada.ca record for `7zs3-pcvk`. ✅ Consistent with the NB agent's
  already-cleared conclusion (open, no flow-down); only the URLs differ.
- **PE — unknown.** No dataset, so no licence. Elections PEI's map products carry no stated
  terms that were reachable in this pass.
- **NL — ⛔ no licence stated.** The St. John's ArcGIS service carries empty `copyrightText`
  and `licenseInfo`, and neither the viewer nor the city site states open-data terms. The data is
  openly served and unauthenticated, but **nothing asserts a licence** — weaker than Toronto,
  which at least has a portal-level OGL to point at.
- **No click-through gate encountered** on any Atlantic endpoint. No account, no form.
- **Verbatim clause quotes:** ⛔ not captured for NS or NB. Both licences are named, linked and
  machine-readable, and both are OGL-family, but the clause text was not fetched in this pass —
  recorded as unread rather than paraphrased.

## Rate limits / auth

- **Auth:** none.
- **Rate limits:** none observed on `data.novascotia.ca`, `gnb.socrata.com`,
  `services2.arcgis.com` (HRM) or ArcGIS Hub.
- ⚠ **Socrata GeoJSON exports are large and unsimplified** — NS is **21.4 MB** for 238 features,
  NB **21.8 MB** for 330. Both are province-wide files being fetched for 2–3 municipalities
  each, so the build should filter server-side (Socrata SoQL `$where`) or accept the whole file
  once and slice locally. Slicing locally is simpler and the files are within budget.
- ⓘ HRM's ArcGIS layer has `maxRecordCount: 2000` against 16 features — single unpaged query,
  no pagination needed.
- ⚠ `data.princeedwardisland.ca/api/3/action/package_search` returns **HTTP 404** — there is no
  CKAN there. Recorded so nobody re-probes it.

## Staged files

Staging root `/media/bunker-admin/Internal/sovpro/data/boundaries/municipal-atlantic/`,
manifest at that directory's `PROVENANCE.md`. **43 MB.** ⚠ `prior/` is empty — no Atlantic
publisher was found offering a superseded generation, unlike Toronto (3 models) or Montréal (5).

| Path | Bytes | What it is |
|---|---:|---|
| `current/ns-municipal-polling-districts.geojson` | 21,389,104 | ★ **Province-wide NS.** 238 districts / 49 municipalities. Contains Halifax (16) and Cape Breton (12) — both of our NS sets from one file. |
| `current/nb-lg-wards-quartiers.geojson` | 21,756,026 | ★ **Province-wide NB.** 330 wards / 90 local governments. Contains Fredericton (13), Moncton (4), Saint John (4) — all three of our NB sets. |
| `current/halifax-polling-districts-2024.geojson` | 1,002,744 | HRM's own 2024-election layer, EPSG:4326, **with a `COUNCILLOR` field**. Cross-check + roster reconciliation. |

**Not staged:** PE and NL — no machine-readable source exists to stage (see handoff items).

## Reconciliation with `constituency_boundaries`

**What we hold:** 9 `source_set` values, **83 rows**, `level='municipal'`, across NS/NB/PE/NL.
All rows carry `boundaries_version = 'current'` and `effective_from = '2023-01-01'` — Open North
mirroring artifacts.

**Composition:** 83 = **74 real ward/district polygons** + **9 `census-subdivisions/` rows**
(one per set). No `census-divisions/` rows, no borough tier, **no duplicates**.

| PT | Set | Rows | Real | CSD | Orph | A6 | Authoritative source | Verdict |
|---|---|---:|---:|---:|---:|---|---|---|
| NS | `halifax-districts` | 17 | 16 | 1 | 0 | ok | NS Socrata + HRM AGOL | ✅ 16/16 slug match |
| NS | `cape-breton-districts` | 13 | 12 | 1 | 0 | ok | NS Socrata | ✅ count matches |
| NB | `fredericton-wards` | 13 | 12 | 1 | 0 | ok | NB Socrata | ⚠ missing `4-Lincoln` |
| NB | `moncton-wards` | 5 | 4 | 1 | 0 | ok | NB Socrata | ✅ count matches |
| NB | `saint-john-wards` | 5 | 4 | 1 | 0 | ok | NB Socrata + city AGOL | ✅ count matches |
| PE | `charlottetown-wards` | 11 | 10 | 1 | 0 | ok | ⛔ none found | count consistent w/ council |
| PE | `summerside-wards` | 9 | 8 | 1 | 0 | ok | ⛔ none found | count consistent w/ council |
| PE | `stratford-wards` | 4 | 3 | 1 | 0 | ok | ⛔ none found | ⚠ `needs confirmation` |
| NL | `st-johns-wards` | 6 | 5 | 1 | 0 | ok | ✅ `map.stjohns.ca` WardMap | ✅ **5/5 + 6 at-large, exact** |

**Halifax name reconciliation (the only set checked at name level, since it is the only one with
a directly comparable authoritative name field):** **16 of 16 slugs match.** The single
difference is cosmetic — authoritative
`Hammonds Plains – Upper Hammonds Plains – Lucasville - Middle & Upper Sackville` slugifies with
the `&` dropped, while our stored name spells it `and`. Same district, no re-key.

**Recommended build shape:**

1. **Type the tiers, do not delete.** Set `boundary_kind='municipality'` on the 9 CSD rows and
   `'district'` on the 74 ward rows. ⚠ **Deleting the CSD rows would orphan 14 at-large
   officials** — Atlantic is the block where the Ontario-shaped fix is actively wrong.
2. **Refresh NS from `gcep-xeci`** — filter `mun IN ('Halifax Regional Municipality','Cape Breton Regional Municipality')`.
   Set `effective_from='2024-10-19'`. This is a low-risk refresh: counts and names already match.
3. **Re-harvest NB from `7zs3-pcvk`** post-2026-05-11 election, filtering
   `elect_comm IN ('The City of Fredericton','Moncton','The City of Saint John')`. Picks up the
   missing `4-Lincoln` ward and whatever the 2026 election changed.
4. **Refresh NL geometry from `WardMap/MapServer/0`** (source now known). ⚠ **Take the geometry
   only — discard the `COUNCILLOR` field**, which is four years stale; our roster is the correct
   2025 council. Set `effective_from='2017-09-26'` unless a later ward change is found.
5. **Leave PE alone** pending a source. The 2022 rows are all we have and all we are likely to
   get before the 2026-11-02 election — **do not delete them**.
6. **Populate `boundaries_version`** with the real generation on all 83 rows.
7. **Apply the smallest-matching-polygon resolver rule** — Halifax at 703× is the strongest
   demonstration case in the corpus for regression-testing that fix.

## Research-handoff items

- **⛔ PE has no machine-readable ward boundaries and I could not manufacture one.** Charlottetown
  (10 wards), Summerside (8) and Stratford (3) are all PDF/paper only: no CKAN at
  `data.princeedwardisland.ca` (404), no ArcGIS Hub layer, no ward layer on `gov.pe.ca/gis`.
  Elections PEI publishes *ward and poll maps* as map products. **Difficulty 5.** Two possible
  routes, neither attempted: ask Elections PEI directly (the same civic-transparency approach
  that worked for the NS WAF conversation), or digitise from the PDFs, which I would not
  recommend for 21 polygons. ⓘ Note the PEI *Legislative Assembly* Radware blockade recorded in
  [`../prince-edward-island.md`](../prince-edward-island.md) is **not** the obstacle here — the
  municipal and Elections PEI hosts are separate and reachable. The data simply does not exist
  in vector form.
- ✅ ~~**NL St. John's needs one more probe.**~~ **Done 2026-08-18 — solved, difficulty 1.**
  `https://map.stjohns.ca/mapsrv/rest/services/WardMap/MapServer/0`, found by grepping the
  MapCentre viewer's `layers.js`. ⛔ **One thing does need a human: the layer states no licence
  whatsoever.** No `copyrightText`, no `licenseInfo`, no portal terms. Every other Atlantic source
  has at least a named licence. Is openly-served-but-unlicensed acceptable for internal use, or
  does St. John's need an email to `maps@stjohns.ca`? I have not assumed.
- ~~**The NB agent's GeoNB URLs are dead — please propagate the correction.**~~ ⛔ **Retracted
  2026-08-18 — I was wrong.** Both GeoNB URLs return HTTP 200. I had reconstructed the directory
  paths from bare filenames instead of using the dossier's real URLs, then reported my own bad
  reconstruction as a dead publisher link. Nothing needs propagating. See the corrected note
  under *Platform families*. The Socrata route is still preferable on **format** grounds
  (GeoJSON + server-side SoQL vs zipped shapefile) — a different and much weaker claim than the
  one I made.
- **Ruling A10.3 needed a third category: *hybrid*.** ✅ **Adopted as ruling A12.** At-large-vs-gap does not describe Atlantic,
  where four municipalities elect both ward and at-large councillors and the CSD polygon carries
  the at-large seats. The practical risk is concrete: a migration written from the Ontario
  dossier that treats CSD-in-a-ward-set as contamination would orphan 14 sitting officials here.
  A12 now says the CSD row is removable only when the set has **no** at-large
  officials attached to it.
- **NB and NL are behind elections that have already happened** (2026-05-11 and 2025-10-02), and
  **PE votes 2026-11-02**. Combined with Ontario's 2026-10-26, autumn 2026 stales two more
  blocks. Same scheduling-constraint question as Ontario: who owns the post-election re-harvest?
  ⓘ NS is the one Atlantic province that needs nothing.
- **Is Stratford PE actually 3 wards?** It is the only set whose count I could not verify against
  any authoritative source, and 3 is unusually low. Cheap to confirm if anyone has a PE contact;
  otherwise it stays `needs confirmation`.

## Build outcome — Halifax + Cape Breton, 2026-09-02

Both cut over. `halifax-districts` 16 and `cape-breton-districts` 12 now carry
authoritative geometry; migrations `0123` (cutover) and `0124` (one re-key).

### ⛔ The correction this dossier needs

The 2026-08-18 status snapshot above says *"Halifax 16 ✅ and Cape Breton 12 ✅ both
match exactly what we hold"*, and the reconciliation table says `✅ count matches`.
**That was a COUNT match and it was read as agreement.** `load-boundaries --compare`
against the authoritative file measured the geometry:

| set | matched | mean overlap | min | below 95% |
|---|---:|---:|---:|---:|
| `halifax-districts` | 15/16 | 99.88% | 99.65% | 0 |
| `cape-breton-districts` | 12/12 | — | **34.55%** | **8** |

Cape Breton's district-9 overlapped its authoritative counterpart by **34.55%**,
district-4 by 69.20%, district-11 by 70.68%. Cause: **N.S. Reg. 150/2023** — CBRM was
redistricted and the mirror held the pre-2023 map. Residents in those districts were
being returned the wrong councillor, and every count-based check in this dossier said
the set was fine. ★ This is ruling A7 exactly — *vintage must be measured, not counted*
— and it is the second time the same lesson has been paid for.

### Why the two needed different sources

⛔ Cape Breton's districts are **numbered**; Halifax's are **named**. The province-wide
`ns-municipal-polling-districts.geojson` carries only codes (`HX01`, `CB07`), so
`_ns_label` renders both as "District N". For Cape Breton that matches our held ids.
For Halifax it would have renamed all 16 districts, re-keyed every id, detached all 16
councillors and **discarded the district names** — which the city's own file has and the
province's does not. Halifax therefore has its own spec reading
`halifax-polling-districts-2024.geojson` (`DISTNAME`), verified to reproduce all 16 held
ids through the loader's own `slugify`.

That is why the `row_filter` excluded `HX` and `CB` in the first place. It still
excludes `HX`, now for a documented reason rather than an unexplained one.

### ⚠ Two traps for the next cutover

1. **`census-subdivisions/1209034` and `/1217030` are filed INSIDE these two source_sets**
   but are `boundary_kind='municipality'` — the hybrid-council polygons carrying the
   mayor and at-large members (ruling A12). The new generation does not replace them.
   `0123`'s predicates are scoped to `boundary_kind='district'` for that reason, and it
   asserts both survived.
2. ⛔ **`reattach-municipal-roster` cannot fix a re-key orphan.** It selects councils
   holding a member with `constituency_id IS NULL`. A re-key leaves the member pointing
   at an id that no longer resolves — orphaned, not detached — so the daily job never
   sees them. Only `check-boundary-coverage` caught it, as a `municipal/orphaned` BREACH.
   One councillor (Hammonds Plains) was affected, because the publisher writes
   "Middle & Upper Sackville" and the mirror expanded `&` to `and` while our slugify
   drops it — the same one-character identity divergence as the `œ` case in `0098`.


## PE roster sources — probed 2026-09-02

⚠ Rule #5 waived by the operator for this pass. Findings only; no ingester built.
⛔ **This changes the roster verdict, not the geometry one.** PE geometry remains
Difficulty 5 and unsolved — see below.

### The dossier's "hand-curation is the honest answer" is no longer right

All three PEI cities publish **ward-keyed** rosters at stable URLs, and the three defects
found below show hand-curation has already drifted.

| city | URL | shape | difficulty |
|---|---|---|---|
| **Stratford** | `townofstratford.ca/government-services/contact-town-of-stratford/mayor-council/` | `<Office> <Name>, Ward N, <Ward Name>` — number **and** name on every row | **1–2** |
| **Summerside** | `summerside.ca/city_governance/senior_leadership_mayor_council` | `<Office> <Name>  Ward N: <Ward Name>  <phone> <email>`; all 8 wards match our slugs exactly | **2** |
| **Charlottetown** | `/mayor___council/city_council/meet_my_councillor` + `/ward_maps` | server-rendered, all 10 councillors with ward NUMBERS only; the second page supplies number→name | **3** |

★ **FPEIM (`fpeim.ca/municipal-directory/`) is a cross-check, not a source.** It covers every
PEI municipality with mayor, deputy mayor, CAO, full councillor list, contacts and meeting
schedules, and its WordPress `wp-json` gives a freshness signal. ⛔ But councillors are a flat
comma-separated list with **no ward attribution**, and our rows key on
`charlottetown-wards/*` etc. It cannot maintain that key. ⚠ Its `modified_gmt` said
2026-09-02 while the page body reads "last revised: April 2025" — irreconcilable, so treat
the on-page date as the honest one.

⛔ **Dead ends:** `electionspei.ca` is behind a **Radware** bot-manager CAPTCHA (not
Cloudflare) — hard-blocked, do not retry with a different UA. `data.princeedwardisland.ca`
CKAN returns **404** — there is no PEI CKAN, confirming this dossier. Stratford's open-data
catalogue page exists but is **empty prose**, an aspiration rather than a catalogue.

### ⚠ Three roster defects found, NOT yet actioned

None of these were written — each rests on a single web read, and de-activating or re-keying
a sitting official on that basis is not reversible enough to do unverified.

1. ⛔ **Charlottetown Wards 4 and 5 may be mis-keyed.** Composing the two city pages gives
   Ward 4 *Spring Park* = Mitchell Tweel and Ward 5 *Ellen's Creek* = Kevin Ramsay; we hold
   Tweel on `st-avards` and Ramsay on `spring-park`. `st-avards` is not a current ward name.
   ★ **Do a POLYGON CHECK FIRST.** This is consistent with our `charlottetown-wards` set
   being a prior generation in which 4 and 5 were drawn differently — supporting evidence is
   that the city files the Ward 4 and 5 booklets under *Election Information* while wards
   1,2,3,6–10 sit under *MAPS*. If the boundaries moved, re-keying the roster alone is wrong.
2. **Stratford** lists 5 councillors; we hold 6. Jody Jackson (`stratford-wards/tea-hill`)
   appears nowhere on the town site. Consistent with a resignation, no `ended_at` recorded.
3. **Summerside's mayor departed 2026-09-01** per a city news release; we and FPEIM both
   still carry Dan Kutcher as active. Summerside's 8 ward attachments are otherwise correct.

⛔ **PE geometry is unchanged and still blocked.** Elections PEI is CAPTCHA-walled, there is
no PEI CKAN, Stratford's catalogue is empty, and Charlottetown publishes ward booklets as
PDFs. The roster is solvable by these routes; the geometry is not.


## Status

> ⚠ **Reconciled 2026-09-01.** The checkboxes below are the **research phase's** record
> (closed 2026-08-18) and several were overtaken by the build — migrations `0064`–`0121`,
> merged to `main` 2026-08-28. An unticked box here is **not** evidence that something is
> still outstanding.
>
> **Live counts: [`PROGRESS.md`](./PROGRESS.md)** (generated by `boundary-progress`).
> **What actually landed:** the migration headers, which are the accurate record.
> This file's job is the *reasoning* — sources, licences, traps, vintage evidence.

- [x] All 9 Atlantic sets inventoried and decomposed by row tier (2026-08-18)
- [x] Orphan check — ✅ **zero orphans across all 83 rows**, the cleanest of my four dossiers
- [x] Peel-shape duplication tested specifically for Halifax — ✅ **negative**; 2 polygons everywhere, and the structural reason established (amalgamation dissolved the lower tier)
- [x] `census-subdivisions` rows analysed — ★ **load-bearing here, not contamination**; they carry 14 at-large officials
- [x] Overwrite-bug severity quantified — ⛔ **Halifax 703×, the worst in the corpus**
- [x] NS solved — province-wide Socrata `gcep-xeci`, NS OGL; **Halifax 16/16 name match, Cape Breton 12 ✅**
- [x] NB solved — province-wide Socrata `7zs3-pcvk`, OGL–NB; Moncton 4 ✅, Saint John 4 ✅, **Fredericton missing `4-Lincoln`**
- [x] GeoNB URLs re-verified — ✅ **both alive (200)**; my earlier 404 report was a bad path reconstruction, retracted
- [x] A6 checked — ✅ **no violations** across all 9 sets
- [x] A10.4 in-force dates derived — four municipal election dates, no by-laws needed
- [x] Staleness assessed per province — NS current; NB, NL behind an election; PE in front of one
- [ ] PE ward boundaries located — ⛔ **blocked: no vector source exists; PDF/paper only, difficulty 5**
- [x] NL St. John's source located — ✅ **solved**: `map.stjohns.ca/mapsrv/.../WardMap/MapServer/0`, EPSG:32181, 5 wards + 6 at-large rows; independently confirms A12
- [ ] Stratford PE ward count verified — **needs confirmation**
- [ ] NB re-harvest post-2026-05-11 — **not done; NB is the one province genuinely behind an election**
- [ ] NL geometry refresh from the new source — **not done**; ⚠ take geometry only, the layer's roster attributes are 4 years stale
- [ ] St. John's licence — ⛔ **none stated on the service; needs an operator decision**
- [x] A10.3 amended for the *hybrid* case — ✅ **adopted as ruling A12**: a CSD row is removable only when no officials are attached, verified per set by query
