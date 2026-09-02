# Municipal Québec — boundary file provenance

Staged by the boundary-research pass on 2026-08-18. Files themselves are gitignored;
this table is the committed audit trail. See
[`../../../docs/research/boundaries/municipal-quebec.md`](../../../docs/research/boundaries/municipal-quebec.md).

⚠ **Representative, not exhaustive.** Québec is 24 source sets, most of them harvestable in one
sweep from the Données Québec CKAN federation — a build-phase job. Montréal was staged because
it is the largest set, the partial-ingest case, and the only publisher in either municipal
dossier offering five dated generations.

| File | Source URL | Retrieved (UTC) | Bytes | sha256 | Licence |
|---|---|---|---|---|---|
| `current/montreal-districts-electoraux-2025.geojson` | https://donnees.montreal.ca/dataset/70acec75-c2b4-4d26-a399-facc7b0ad9bf/resource/fa1f8cfc-cdbf-42fd-9979-32c16b68b5ca/download/districts-electoraux-2025.json | 2026-08-18T01:32Z | 6883713 | `849bab6a85cada42e89baafcd98ceb2b75ccfd260765c00121584bc759543bcd` | CC-BY 4.0 (`cc-by`) |
| `prior/montreal-districts-electoraux-2021.geojson` | https://donnees.montreal.ca/dataset/70acec75-c2b4-4d26-a399-facc7b0ad9bf/resource/d0c1467b-a551-42df-98b4-057e00a84275/download/districts-electoraux-2021.geojson | 2026-08-18T01:32Z | 2142598 | `2fe6696f19027f1213253aaf94d67140f6db0d08f6a5c1dc236cf8c533233b42` | CC-BY 4.0 (`cc-by`) |

## Notes

- Catalogue entry is `vmtl-districts-electoraux` on **Données Québec**
  (`donneesquebec.ca/recherche/api/3`), publisher *Ville de Montréal*, licence `cc-by`,
  last modified 2025-10-20. Données Québec federates; the resource URLs resolve to
  `donnees.montreal.ca`.
- ★ The same dataset publishes **five generations** — 2025, 2021, 2017, 2013 and 2009 — each in
  GeoJSON / SHP / CSV. Only current and prior were staged; the other three are free to fetch
  during the build if a deeper temporal layer is wanted.
- ⚠ **`donnees.montreal.ca` returns HTTP 403 to a bare `curl`.** A browser `User-Agent` clears
  it. The Données Québec catalogue API is *not* protected, so a harvester will read the
  catalogue fine and then fail on every download — it looks like a data problem and is a UA
  problem. Cost two failed fetches during this staging.
- ⚠ **Property names changed completely between generations** — an A4-class trap:
  - 2021: `nom`, `num`, `arrondissement`, `id`, `municipalite`
  - 2025: `NO_DISTRICT`, `CODE_DISTRICT`, `NOM_DISTRICT`, `NOM_ARR`
  Code against the specific vintage; a harvester keyed to 2021 reads nothing from 2025.
- **Feature counts: 2025 = 58 districts, 2021 = 59 districts.** Montréal lost one district in
  the redraw for the 2025-11-02 general municipal election.
- ⛔ **What we hold in the database matches neither file.** `montreal-boroughs-and-districts`
  holds 62 real rows, of which only **39 match a 2021 district name** — the rest are boroughs.
  So we hold roughly 39 of 59 districts plus 19 arrondissements, not a complete district set.
  See the dossier's reconciliation section.
- Files are uncompressed, unsimplified GeoJSON — 6.9 MB for 58 features. Budget accordingly if
  harvesting all 24 Québec sets in one run.

## Données Québec district files — added 2026-08-20

All CC-BY, fetched with a browser User-Agent (⚠ `donnees.montreal.ca` 403s a bare
curl; the Données Québec catalogue API does not, so a harvester reads the catalogue
fine and then fails on every download).

| file | bytes | sha256 | source |
|---|---:|---|---|
| `laval-districts-2025.geojson` | 367510 | `2de4bd5ec55fa902…` | see below |
| `quebec-city-districts-2025.geojson` | 599682 | `4bc4044bb4bcaa01…` | see below |
| `longueuil-districts-2025.geojson` | 199744 | `bf170bbadf905b72…` | see below |

- **Laval** — `donneesquebec.ca` package
  `limites-des-districts-electoraux-des-dernieres-elections-municipales`,
  resource `limite-district-electoral.geojson`, package modified 2026-05-20.
  **22 districts**; CRS declared `urn:ogc:def:crs:OGC:1.3:CRS84` (WGS84, lon/lat).
  Fields `NOM`, `NUMERO`, `CONSEILLER`, `TEL_CELL`, `COURRIEL`.
  ★ Laval redistricted 20 → 22 for 2025-11-02, and **the seven new district names
  are exactly the seven councillors that could not attach** — roster from MAMH,
  map from the city, two bodies agreeing. Loaded (migration 0099).

- **Ville de Québec** — package `vque_43`, resource `vdq-districtelectoral.geojson`,
  **resource modified 2026-08-18**, the freshest municipal source in the corpus.
  **21 districts**, fields `ID`, `NOM`, `PARTI`, `CONSEILLER`. No `crs` member →
  RFC 7946 WGS84.
  ⛔ Only TWO of its five "new" districts are new; three are the same district with
  its ARTICLE restored (`plateau` → `le-plateau`, `pointe-de-sainte-foy` →
  `la-pointe-de-sainte-foy`, `chute-montmorency-seigneurial` →
  `la-chute-montmorency-seigneurial`). Loaded (0099), which re-keys those three.

- **Longueuil** — package `districts-electoraux-longueuil`, resource
  `districtelectoral.json`. ⛔ **FETCHED AND DELIBERATELY NOT LOADED.** The resource
  is dated **2024-03-01** and holds **15 districts whose slugs are byte-identical to
  the 15 we already have**, while Longueuil's 2025 roster names six districts that
  exist in neither. The city has not published its post-redistribution map. Staged so
  the next person does not re-fetch it to reach the same conclusion; its six
  councillors stay unattached rather than being forced onto a superseded map.

ⓘ **All three files name the sitting councillor** (`CONSEILLER`), as Calgary,
Edmonton, Winnipeg and Halifax do. With Open North retired, municipal boundary files
are a roster source and not only a geometry source.

## Sherbrooke — added 2026-08-28

| File | Source URL | Retrieved (UTC) | Bytes | sha256 | Licence |
|---|---|---|---|---|---|
| `current/sherbrooke-districts-2025.geojson` | https://donneesouvertes-sherbrooke.opendata.arcgis.com/api/download/v1/items/3579a4b8ceb24c7896edc0d86ee4714e/geojson?layers=0 | 2026-08-28T16:20Z | 934687 | `a2695e930dade548166086984f1b2f4a7d4b6b71e7330f443c945be6f64a5ccf` | CC-BY 4.0 — licence_id `cc-by`, licence_title "Attribution (CC-BY 4.0)" verbatim from the Données Québec package |

- Catalogue entry is `3579a4b8ceb24c7896edc0d86ee4714e_0` on **Données Québec**,
  publisher *Ville de Sherbrooke - Données géomatiques*, title `Districts électoraux`,
  package modified 2026-06-01. The GeoJSON resource resolves to the city's own
  ArcGIS Hub. Gate-free; no User-Agent trick needed (unlike `donnees.montreal.ca`).
  Live REST mirror:
  `services3.arcgis.com/qsNXG7LzoUbR4c1C/arcgis/rest/services/DistrictElectoral/FeatureServer/0`.
- **In-force date 2025-11-02** (ruling A10.4 — the general election the map first
  governed). **Instrument: Règlement numéro 1289** *divisant le territoire des
  arrondissements de la Ville de Sherbrooke en districts électoraux (14 conseillers
  municipaux et 2 conseillers d'arrondissement)*, adopted at the ordinary council
  sitting of **2024-05-21**, approved by the **Commission de la représentation
  électorale on 2024-10-31** and in force from that date. By-law PDF (3,189,014 bytes):
  `https://www.sherbrooke.ca/Fichiers/3337a882-4a53-e611-80ea-00155d09650f/Sites/333ba32f-4b53-e611-80ea-00155d09650f/Elections%202025/reglement1289.pdf`
  Its technical descriptions were prepared 2024-04-08 by arpenteure-géomètre
  Maylis Casenave, plan 3856-15, minute 802.
  ⚠ The city's web page says "Le 7 mai 2024 … a été adopté"; the by-law's own first
  page says the sitting was **21 mai 2024**. The instrument wins — 7 May is almost
  certainly the avis de motion. Neither date is the one we store.
  ⚠ That page now 404s (post-election cleanup); read via the Internet Archive
  snapshot `20251104124658`. The by-law PDF is still live.
- ⛔ **EPSG:3857, not 4326** — the only Québec municipal file in the corpus that is.
  The Hub download declares `crs: {name: "EPSG:3857"}` and ships Web Mercator metres;
  the three files above are all WGS84 degrees. A harvester that infers the CRS from
  its Québec siblings relabels metres as degrees.
- ⛔ **32 features for 16 districts.** Every district is published TWICE with
  identical attributes and identical geometry (OBJECTID 1–16 and 17–32). A record
  count reads a 32-district Sherbrooke.
- ★ **It is BOTH a partial-ingest hole AND a real redraw, and the two were easy to
  confuse.** `--compare` against what we held: 16 authoritative / 16 held /
  **15 matched, mean overlap 99.3777%, min 98.7511%, none below 95%**. The one
  district absent from our table was `lennoxville`; the one row we hold that the
  district file does not is the city's CSD outline `2443027`. So the mirror never
  ingested district 3.0 — that part is a hole.
- ⛔ **BUT DO NOT CONCLUDE "HOLE, THEREFORE KEEP THE OLD DATE."** A 99.38% mean
  overlap against *mirror* geometry of unknown vintage is not proof the lines
  stood still, and here they did not. Test used, and worth reusing: Élections
  Québec publishes the CRE's own map per borough for BOTH elections, so the two
  vintages can be diffed directly. Rendered `43027-IA-002,00-F01` and
  `-IA-004,00-F01` for 2021 and 2025 at 70 dpi and compared ink with a 2-pixel
  registration tolerance (a plain pixel diff is useless — the base map is redrawn
  from a newer Adresses Québec and every street shifts a pixel):
  - **Arrondissement 4 (Les Nations): district lines UNCHANGED.** The residue is
    new-subdivision streets, relabelled streets, and the title block.
  - **Arrondissement 2 (Fleurimont): district lines MOVED.** A long dotted
    boundary segment present in only one vintage, plus the `2,3` and `2,1`
    district labels sitting in different places — a label moves when its
    district's shape does.
  Règlement 1289 is therefore a genuine redistribution, not a re-enactment, and
  2025-11-02 is a new generation rather than a continuation.
- ⓘ For the record, "keep the pre-existing in-force date" was never an option
  here: the date we held was the Open North mirror's fabricated `2023-01-01`.
  Had 1289 turned out to be a pure re-enactment, the honest move would have been
  to hunt down the *previous* division by-law for its date — not to keep 2023.
- ⚠ **District 3.0 de Lennoxville is the exact union of 3.1 d'Uplands and 3.2 de
  Fairview** (58,289,370 = 25,351,810 + 32,937,560 in layer units). That is
  Sherbrooke's real structure, not a defect: Lennoxville holds bilingual-municipality
  status under the Charte de la langue française so its limits cannot be redrawn by
  a districting exercise, and it elects one *conseiller municipal* over the whole
  borough plus two *conseillers d'arrondissement* over its halves. A point in
  Lennoxville returns **two** districts, and that is correct.
- ⓘ Names are stripped of their leading French article on load (`de Lennoxville` →
  `Lennoxville`, `d'Ascot` → `Ascot`) and of the `(district d'arrondissement)`
  suffix. See the long note on `_sherbrooke_label` for why this deliberately does
  *not* follow the Québec-City precedent in 0099.

## Élections Québec register of divided municipalities — found 2026-08-28

The authoritative list of which Québec municipalities are divided into electoral
districts, per general election, is a **CSV behind a JS table**, not a page:

| Election | CSV |
|---|---|
| 2025-11-02 | `https://donnees.electionsquebec.qc.ca/autres/cartes-muni-district-2025/cartes_municipales_pour_web_2025.csv` |
| 2021-11-07 | `https://donnees.electionsquebec.qc.ca/autres/cartes-muni-district-2021/cartes_municipales_pour_web.csv` |

Semicolon-separated; columns `MUNICIPALITE;DESIGNATION;CODE_MUNICIPALITE;POPULATION;
REGION_ADMINISTRATIVE;NOM_CARTE_MULTIPLE;CARTE_DISPONIBLE;MODIFICATION`. The
second-to-last column is a map code and the CRE's own map for that municipality is at
`…/cartes-muni-district-<year>/<CARTE_DISPONIBLE>.pdf`. 271 municipalities for 2025,
267 for 2021; the six divided into arrondissements (Lévis, Longueuil, Montréal,
Québec, Saguenay, Sherbrooke) get one map per borough.

⛔ **These maps are raster PDFs and carry no instrument date** — the only date printed
on them is `Production : Avril 2025`, a cartography run, not a coming-into-force. Use
the register to establish *that* a municipality is divided and which generation it
belongs to; use the municipality's own division by-law for the date. Élections Québec
publishes **no municipal district geometry at all** — its open-data surface
(`donnees.electionsquebec.qc.ca/production/municipal/…`) is candidacies and results
only.

## ⛔ Brossard, Kirkland, Senneville, Sainte-Anne-de-Bellevue — NOT STAGED, 2026-08-28

All four were researched to the end of the probe hierarchy and **publish no
machine-readable district geometry in any format**. Dates were established for two
of them and are recorded here so the next pass does not redo the work; there is
simply nothing to load.

| municipality | in-force date | instrument | geometry |
|---|---|---|---|
| Brossard | 2025-11-02 | Règlement **REG-478** adopted 2024-05-28 (10 → 12 districts), **modified by the Commission de la représentation électorale**, announced 2024-12-03 | none — PDF map only |
| Senneville | 2025-11-02 | **By-law numéro 500**, avis de motion + projet 2024-04-23, CRE approval 2024-04-19, **adopted 2024-05-28, in force 2024-05-30** | none — the by-law delimits its six districts in *prose* |
| Kirkland | not established | — | none |
| Sainte-Anne-de-Bellevue | not established | — | none |

- **Brossard.** City page `brossard.ca/sujets/districts-electoraux/` lists 12 districts
  with elector counts and links exactly one artefact:
  `https://brossard.ca/app/uploads/2025/10/Districts2025-2029_carteVF_20241212.pdf`.
  Not on Données Québec (`package_search?q=brossard` → 0 results). Its public ArcGIS
  org is `Amenagement_Brossard` (`services8.arcgis.com/Vy9ekHNIOKBu4xaY`) — ten items,
  none electoral; `Limites_des_secteurs` is an unattributed *polyline* layer of
  neighbourhood sectors, not districts. ★ Brossard is the one genuine REDRAW of the
  five: 10 districts before, 12 now, and the CRE overrode the City's own delimitation.
  The 9 mirror polygons we hold are a partial ingest **of the superseded 10-district
  map** and are wrong twice over.
- **Senneville.** By-law 500 is a clean, dated, bilingual instrument
  (`https://www.senneville.ca/wp-content/uploads/2024/06/0.13.1.Reglement-500-Districts-electoraux-2025-VF.pdf`)
  — and its Article 1 delimits the six districts by *clockwise prose* ("the rear
  boundary line of Pacific Avenue (North-East side), excluding Morningside Avenue…").
  There is no plan annexed in any vector form. ⛔ Do not digitise it.
- **Kirkland.** Eight districts, and its site offers a street-name→district *lookup
  form* plus eight per-district PDFs at `ville.kirkland.qc.ca/client_file/districts.php?id=190..197`
  (403 to a bare curl). No division by-law was located online.
- **Sainte-Anne-de-Bellevue.** Six districts, three south (1–3) and three north (4–6)
  per the city's own wording. No division by-law and no map file located online.

### ⛔ The numbering gap is NOT evidence of a partial ingest — measure the residual

All three of Brossard, Senneville and Sainte-Anne hold polygons with a gap in the
middle of the numbering (Brossard 1–9 of a ten-district map, Senneville 1,2,4,5,6,
Sainte-Anne 1,3,4,5,6), and in Senneville's and Sainte-Anne's case the *mirror's own
roster* had the matching gap too. That pattern reads exactly like Open North's
documented failure mode — a district gets a polygon only if a sitting representative
for it appears in the roster — and on that reasoning all three were first written up
here as partial-ingest holes. **For Sainte-Anne that was wrong.**

The cheap test that settles it is a residual: union the held districts and subtract
them from the municipality outline. A real hole leaves a district-shaped gap; a
complete-but-superseded map leaves nothing.

| set | muni km² | districts km² | residual km² | parts | largest part km² |
|---|---:|---:|---:|---:|---:|
| `sainte-anne-de-bellevue-districts` | 10.949 | 10.949 | **0.000** | **0** | — |
| `senneville-districts` | 7.527 | 18.459 | 0.480 | 9 | 0.436 |
| `brossard-districts` | 45.355 | 48.723 | 3.772 | 35 | 3.464 |

- **Sainte-Anne-de-Bellevue: the five polygons TILE the city exactly.** Zero residual,
  zero parts. There is no missing sixth district to go and find — what we hold is a
  complete FIVE-district partition whose numbering happens to skip 2, and the council
  now elects six. It is a resize, not a hole. `qc_municipal_roster`'s own refusal
  message ("council resized, so post N is no longer district N") was right.
- **Senneville: probably a real hole, but the subtraction cannot prove it.** The
  largest residual part (0.436 km²) is bigger than two of the five held districts
  (0.224 and 0.133 km²), so it is district-shaped. ⚠ But the districts total
  18.459 km² against a 7.527 km² CSD outline — 2.45× — because the district polygons
  run out into the lac des Deux Montagnes to the municipal boundary while the CSD
  outline is land-only. Two geometries that disagree that badly cannot be differenced
  into a trustworthy polygon.
- ⛔ **And even a clean residual would not be loadable.** By-law 500 is a fresh 2024
  division; a polygon derived from 2021-vintage mirror geometry would be a confident
  answer to the wrong question. Deriving a *municipality outline* from a union of
  districts (migration 0100) is safe arithmetic; deriving a *district* from a
  complement is not the same operation and must not borrow its precedent.
- Probes that came up empty for all four: Données Québec CKAN (`package_search`),
  ArcGIS Online public search by name and by owner, Élections Québec open data, and a
  CMM / agglomeration-wide layer (none exists — `limites_administratives_agglomeration`
  is municipal outlines only).

## Longueuil and Terrebonne — added 2026-08-28

Both are **real redraws**, both loaded, both dated **2025-11-02** under ruling A10.4.
Neither publisher is Données Québec: each city publishes its current map only to its
own ArcGIS Online organisation.

| File | Source URL | Retrieved (UTC) | Bytes | sha256 | Licence |
|---|---|---|---|---|---|
| `current/longueuil-districts-2025-11.geojson` | https://services2.arcgis.com/h4XWvDXfYYyD6jNu/arcgis/rest/services/DO_DistrictElectoral/FeatureServer/0/query?where=1%3D1&outFields=*&outSR=4326&f=geojson | 2026-08-28T17:20Z | 324204 | `0ca37a47fd95f42f65a345efcb95501db58cd161e1e1351a5ed17c89679ac86b` | CC-BY 4.0 — item `licenseInfo` verbatim: "Cette donnée est mise à disposition selon les termes de la Licence Creative Commons Attribution 4.0 International" |
| `current/terrebonne-districts-2025-11.geojson` | https://services3.arcgis.com/kKl4g5Ltuw8RvFq1/arcgis/rest/services/districts_electoraux/FeatureServer/0/query?where=1%3D1&outFields=*&outSR=4326&f=geojson | 2026-08-28T17:20Z | 541886 | `abe88830ee698f3fd1189340e209af50b4526ed86492e421d0f202aa423a1bd7` | CC-BY 4.0 **by policy, not by item** — see below |

⚠ Both URLs carry `outSR=4326`, so the staged files are WGS84 degrees. The **native**
SRs are EPSG:32188 (Longueuil, NAD83 MTM 8) and EPSG:2950 (Terrebonne, NAD83(CSRS)
MTM 8), both in metres. Re-fetch without `outSR` and `src_epsg=4326` in the loader
spec silently relabels metres as degrees.

### Longueuil — 15 → 18 districts

- Catalogue entry is ArcGIS Online item `acb5405480754fd4a41734bd81fafbe6`
  ('Districts électoraux', owner `VilleLongueuil`, org `h4XWvDXfYYyD6jNu`),
  attributed to the *Service de la géomatique, Direction de l'aménagement et de
  l'urbanisme*. Gate-free to a bare curl.
- **In-force date stored: 2025-11-02** (ruling A10.4 — the general election the map
  first governed). **Instrument: Règlement CO-2024-1269** *divisant le territoire de
  la municipalité en districts électoraux*: avis de motion 2024-04-16 (CO-240416-8.24),
  adopted 2024-06-11 (CO-240611-8.11), **in force 2024-10-31**. By-law PDF:
  `https://www3.longueuil.quebec/sites/longueuil/files/reglements/co-2024-1269_eev_annexe.pdf`
  The 18 toponyms were attached afterwards by **Règlement CO-2024-1293**, adopted
  2025-01-21, in force 2025-01-23.
- ⛔ **The 2024-10-31 in-force date is statutory, not discretionary, and it is the
  same date for every Québec municipality in this arc.** LERM art. 30: *"le règlement
  divisant le territoire de la municipalité en districts électoraux entre en vigueur le
  31 octobre de l'année civile qui précède celle où doit avoir lieu l'élection générale
  pour laquelle la division doit être effectuée."* Finding "2024-10-31" in a QC
  division by-law is therefore **no evidence at all** about that particular
  municipality — do not read it as a coincidence worth remarking on, and do not store
  it. A10.4 stores polling day.
- ⛔ **Ignore the city's own "19 septembre 2025".** The ArcGIS item snippet reads
  *"Carte interactive des districts électoraux (en vigueur depuis le 19 septembre 2025,
  aux fins de l'élection du 2 novembre 2025)"*. That is polling day **minus 44** — the
  first day of the *période électorale* (LERM art. 364) and of the nomination window
  named in Longueuil's own avis public d'élection. No instrument entered into force
  that day. It is GIS shorthand, and it cost a real probe to disprove.
- ★ **The previously staged file was, and still is, stale — the refusal was correct.**
  `longueuil-districts-2025.geojson` came from Données Québec package
  `districts-electoraux-longueuil`, resource dated 2024-03-01. Re-probed 2026-08-28:
  **the package still serves the superseded 15-district map**, and its `CONSEILLER`
  field still names the 2021–25 council (Éric Bouchard, Jonathan Tabarah, …). Données
  Québec is not a route to Longueuil's current map and should not be re-checked for one.
- ⚠ **A SECOND city layer holds the same map**, `Elections2025_Districts/FeatureServer`
  (item `da4b81410c514e338e5126c8ce2f5add`, owner `bruno.belzile` — a staff account in
  the *same* org `h4XWvDXfYYyD6jNu`, which is what makes it official). It publishes the
  18 districts **twice**, as layers 1 and 2, with byte-identical geometry — the
  Sherbrooke double-publication pattern in a second city. Measured against the
  open-data layer district-for-district: **min IoU 0.999982, mean 0.999996** — the same
  map at different coordinate precision. It carries a `NUMERO` field with the by-law's
  own 1–18 numbering, which the open-data layer lacks; it carries **no licence text**,
  which is why the spec reads the open-data layer instead.
- ⛔ **`OBJECTID` is not the by-law district number** in the open-data layer (OBJECTID 1
  is by-law district 10), so no `authority_district_id` is recorded. The held rows
  carried none either.
- ★ **A real redraw, and `--compare` is what proved it:** authoritative=18 held=16
  matched=13 **mean_overlap=75.8600% min=41.0812% below_95%=10**. Ten of the thirteen
  districts whose *names* survived had moved; `georges-dor` kept 41%. Absent from our
  table (5): `boise-fonrouge`, `boise-pilon`, `croydon-iberville`,
  `longueuil-montreal-sud`, `ruisseau-masse`. We held and the authority does not (3):
  `2458227` (the CSD outline — keep it), `explorateurs`, `iberville`.
  The 15→18 increase required a Charter amendment: private bill **PL 204,
  *Loi concernant la Ville de Longueuil***, sanctioned 2024-02-14.
- ⓘ **THE ARRONDISSEMENT TRAP DID NOT FIRE, though Longueuil was the live candidate.**
  The layer is ONE TIER: 18 districts, **10 Vieux-Longueuil / 7 Saint-Hubert / 1
  Greenfield Park**. District 11 *Greenfield Park* **is** the borough (coterminous,
  hence exempt from the ±15% rule at +21.03% deviation), and the borough's 2
  *conseillers d'arrondissement* are elected **borough-wide over that same polygon**
  rather than over sub-districts — the borough ships no sub-district geometry. So three
  people name `de Greenfield Park` and all three correctly resolve to one polygon:
  20 councillors, 18 districts, no nesting. No `kind_builder` needed, unlike Sherbrooke.
- ⚠ **MAMH prefixes EVERY Longueuil district with a French article** (`de`, `du`, `des`,
  `d'`) — `de Croydon-Iberville`, `du Boisé-Pilon`. Not one of the 18 slug-matches the
  polygon exactly. The QC roster's article/elision/spacing fallback pass handles this
  and attached 5 of the 6 flagged councillors on load. ⛔ It also means a bare
  `cpd_slugify` equality test on Longueuil reports **zero** matches and looks like a
  catastrophe; it is not.
- ⚠ **The sixth councillor was never a geometry problem.** MAMH writes district 3 as
  `de Fatima-du Parcours-du-Cerf`; the city — in CO-2024-1293, in the layer, **and in
  the superseded 15-district map** — writes `Fatima-Parcours-du-Cerf`. The name is
  unchanged across the redistribution and the interior `du` is MAMH's alone, so this is
  a spelling divergence and takes a `constituency_name_alias` row (0121 step 6), not a
  polygon rename. It predates the cutover.
- ⓘ The layer names the sitting councillor (`CONSEILLER`) and party (`PARTI`), refreshed
  to the 2025-elected council — a roster source as well as a geometry source.

### Terrebonne — 16 → 16 districts, and the count saw nothing

- Catalogue entry is ArcGIS Online item `f2edea41fd2c46aab4ba9d7d7c06885f`
  ('TRB_DistrictsElectoraux', owner `Ville_Terrebonne`, org
  `a73949cd742c49f48a4110e454889211`). Fields `de_numero`, `de_nom`, `de_conseiller`.
- ⛔ **NOT on Données Québec.** `package_search?q=terrebonne` returns **2** packages —
  a GTFS feed and a provincial geodesy layer — neither electoral. ArcGIS Online search
  is what found this; ⚠ note that `q=terrebonne district` is dominated by **Terrebonne
  Parish, Louisiana**, which owns ~20 of the first 25 hits. The Québec city was hit 25.
- ⚠ **LICENCE IS BY POLICY, NOT BY ITEM** — the one licence caveat in this batch. The
  ArcGIS item's `licenseInfo` is **empty**, unlike Longueuil's and Sherbrooke's which
  carry it inline. The city's council-adopted **Politique sur les données ouvertes**
  (POL.1201.21, résolution du conseil municipal **#284-05-2021** adopted 2021-05-10)
  settles it at **s. 9 "Licence d'utilisation"** verbatim: *"La « Licence Creative
  Commons Attribution 4.0 International (CC-BY) » fait office de référence et de
  consensus international dans le domaine des données ouvertes. Cette licence est aussi
  retenue par l'ensemble des municipalités et des entités gouvernementales provinciales
  qui utilisent le portail de publication du gouvernement du Québec. Les données
  ouvertes de la Ville de Terrebonne seront donc assujetties à cette licence."*
  Source: `https://terrebonne.ca/wp-content/uploads/2023/08/Terrebonne_Politique_de_donnees_ouvertes_VF.pdf`
- **In-force date stored: 2025-11-02** (A10.4). **Instrument: Règlement numéro 929**
  *concernant la division du territoire de la Ville de Terrebonne en seize (16)
  districts électoraux, désignant et délimitant ces districts*: avis de motion
  2024-05-07 (rés. 234-05-2024), opposition period 8–23 May 2024 against a threshold of
  500, **zero oppositions certified 2024-05-24**, adopted at a séance extraordinaire
  2024-05-31 (rés. 262-05-2024), **in force 2024-10-31** (same LERM art. 30 rule).
  R929 art. 4 **expressly repeals Règlement numéro 764** (adopted 2020-05-11) — the map
  we held.
  Promulgation notice (**the citable copy**):
  `https://terrebonne.ca/wp-content/uploads/2024/10/Avis-public-R929-PROM2_Site-internet.pdf`
- ⚠ **The June 2024 standalone by-law PDF leaves the in-force line BLANK**
  (`Date d'entrée en vigueur : ___________ 2024`). The filled, signed copy is the one
  appended to the October promulgation notice. Cite the promulgation PDF, not
  `R929-districts-electoraux.pdf`.
- ⚠ **The CRE acted, but administratively — do not look for a decision document.**
  Zero electors opposed, so no public hearing was triggered and Élections Québec
  publishes nothing per-municipality. The CRE nonetheless **confirmed conformity on
  2024-08-23**, and council adopted **résolution 449-09-2024 on 2024-09-04** amending
  R929 on the CRE's recommendations, which forms part of the by-law as if adopted with
  it (LERM art. 21). This is attested only by the clerk's promulgation notice — solid,
  but second-hand as to the CRE's own act.
- ⛔ **THE TRAP: 16 BEFORE, 16 AFTER, AND THE LINES MOVED ANYWAY.** The brief's own
  reading was that this might be a rename. `--compare` settled it: authoritative=16
  held=17 matched=14 **mean_overlap=81.7721% min=40.9525% below_95%=12**. **Twelve of
  the fourteen districts whose names never changed had moved**, `du-ruisseau-noir` down
  to 41%. R929 says the same thing in its own words — the city's summary is that the
  by-law *"touche 13 des 16 districts actuels, soit les districts 1, 2, 3, 4, 5, 6, 7,
  8, 9, 11, 13, 14 et 15, alors que les limites existantes sont conservées pour trois
  (3) districts, soit les districts 10, 12 et 16."*
- ⛔ **AND THE TWO RENAMES RUN THE WRONG WAY FOR A NAME PATCH.** The **Urbanova sector
  moved OUT of district 5 and INTO district 7**. District 5 was renamed
  `Grand Ruisseau` → `La Bergeronne` *because it lost* Urbanova; district 7 was renamed
  `Côte de Terrebonne` → `Côte de Terrebonne-Urbanova` *because it gained* it. Aliasing
  `cote-de-terrebonne-urbanova` onto `cote-de-terrebonne` would have put every Urbanova
  address in the district that no longer contains it — right councillor name, wrong
  ground. ★ The sitting councillor for the new district 7, Marie-Ève Couturier, was in
  fact found attached to the old `cote-de-terrebonne` polygon and had to be detached.
- ★ **Independent corroboration of the vintage, without the by-law:** the same ArcGIS
  org holds `districts_electoraux_vector_tile_archive_20251103` — an archive copy cut
  **the day after the 2025-11-02 election** — and the live layer was modified
  2025-11-03. The publisher archived the old map and replaced it at the election. Two
  unrelated bodies of evidence, one conclusion. ⓘ This "look for an `_archive_<date>`
  sibling in the publisher's org" test is cheap and reusable.
- ⚠ **One name is taken from the by-law, not the layer.** The layer writes district 2
  as `Boisé Laurier`; R929 designates it **`Du Boisé-Laurier`**, and so does MAMH. The
  loader's `_terrebonne_label` restores the by-law form — which is also what keeps the
  district's existing id `terrebonne-districts/du-boise-laurier` instead of minting a
  second id (`boise-laurier`) for a district continuing under its own name. Confirmed by
  the load reporting `slug_matches_existing=14` rather than 13. ⓘ District 15 is left
  alone: R929 writes `Saint-Charles-Des Fleurs` and the layer `Saint-Charles-Des-Fleurs`,
  and both slugify identically, so there is nothing to fix.
- ⓘ The layer names the sitting councillor (`de_conseiller`), refreshed to the
  2025-elected council.

### ⓘ Route notes worth keeping

- **Longueuil's by-law register lives on the legacy Drupal host**
  `www3.longueuil.quebec/fr/reglements/<slug>`, which is **not linked from the current
  site** — the live site exposes only a Constellio React app whose GraphQL endpoint
  returns 400 to non-browser clients. The `www3` register is the machine-readable path
  to QC municipal by-law dates and signature blocks (`Avis de motion / Projet /
  Adoption / Entrée en vigueur`).
- **Terrebonne 403s a plain WebFetch and Cloudflare-challenges some paths, but it is
  WordPress** and its REST API (`/wp-json/wp/v2/search`, `/media`) answers a bare curl.
  That is how R929, the opposition certificate and the open-data policy were located,
  and it is reusable for the other Québec municipalities in this arc.

## Gatineau, Saguenay, Lévis, Trois-Rivières, Saint-Jean-sur-Richelieu — added 2026-09-02

| File | Source URL | Retrieved (UTC) | Bytes | sha256 | Licence |
|---|---|---|---|---|---|
| `current/gatineau-districts-2025-11.zip` | https://www.gatineau.ca/upload/donneesouvertes/DISTRICT_ELECTORAUX.zip | 2026-09-02T17:39Z | 92659 | `2a8b6135d085aadf425fc2ad3d9053ef65d7eb0748171b18efaa68741dd4f2a1` | CC-BY 4.0 — licence_id `cc-by` on Données Québec package `vgat_-1582475471`, which lists this exact URL as its SHP resource |
| `current/saguenay-districts-2025.geojson` | https://www.donneesquebec.ca/recherche/dataset/92fd1b10-66dc-4017-968a-b9b6f232a2e9/resource/753bd337-4c4d-48cc-875f-94b301d79020/download/sag_districtselectoraux.geojson | 2026-09-02T17:24Z | 287726 | `35975f108db952e4c24520c60a5c13735a23b3ac36fbfd5ba6d373f9ce533ae4` | CC-BY 4.0 — licence_id `cc-by`, package `sag_district-electoral` |
| `current/levis-districts-2025-11.geojson` | https://cartes.ville.levis.qc.ca/arcgis/rest/services/SiteWeb/SiteVille/MapServer/5/query?where=1%3D1&outFields=*&outSR=4326&f=geojson | 2026-09-02T17:37Z | 496904 | `a87a1934e08aaa61734f36cf37b6cb1d11fe30fdee2cf89034fbf61052f516e1` | ⚠ **ASSERTED, NOT READ** — CC-BY 4.0 carried over from the city's own Données Québec package `districts-electoraux-levis`; the MapServer publishes no licence text of its own |
| `current/trois-rivieres-districts-2025-11.geojson` | https://geo.v3r.net/arcgis/rest/services/DonneesOuvertes/DistrictsElectoraux_LAYER_DO/FeatureServer/60/query?where=1%3D1&outFields=*&outSR=4326&f=geojson | 2026-09-02T17:37Z | 135091 | `60b3477c8ebb7f88455067e5cdad4303cc6fe3f5dc6f38423a456882d49257d1` | CC-BY 4.0 — the `DonneesOuvertes` folder is the upstream of Données Québec package `districts-electoraux-v3r` (`cc-by`) |
| `current/saint-jean-sur-richelieu-districts-2025.geojson` | https://www.donneesquebec.ca/recherche/dataset/6218a375-a8fe-45ce-959b-22c90a291b0b/resource/f937a7e0-6672-4b44-910b-2c83f27c7c92/download/sjsr-disctricts-electoraux.geojson | 2026-09-02T17:24Z | 295488 | `7cdca10e480d20e5515bb91fc678295511c5c79648b6da47a0c3ed63461a9c47` | CC-BY 4.0 — licence_id `cc-by`, package `sjsr-districts-electoraux` |

### ⛔ The count and the name list are blind for all five

MAMH's own election results (`resultats-des-elections-municipales-generales`,
resources `Elec2021_Mun.csv` and `Elec2025_Mun.csv`, CC-BY) record **identical district
counts and identical district names in 2021 and in 2025** for every one of the five:
Gatineau 19, Saguenay 15, Lévis 15, Trois-Rivières 14, Saint-Jean-sur-Richelieu 12.
Not one district was added, dropped or renamed anywhere in this tranche. So neither the
count nor the name list can distinguish a refreshed map from a superseded one — the
Terrebonne case, five times over.

★ **What did distinguish them was the councillor field.** Every one of these files names
its sitting councillor, and MAMH's 2025 results give the elected councillor per district.
Comparing the two, district by district, dates the file directly:

| set | file's councillors | verdict |
|---|---|---|
| Saguenay | 15 of 15 = 2025-elected | refreshed after the poll |
| Saint-Jean-sur-Richelieu | 12 of 12 = 2025-elected | refreshed after the poll |
| Trois-Rivières (live layer) | 14 of 14 = 2025-elected | refreshed after the poll |
| Gatineau (Données Québec GeoJSON) | 2021-25 council | ⛔ superseded |
| Lévis (Données Québec) | 2021-25 council | ⛔ superseded |

ⓘ This is the cheapest currency test we have for a Québec municipal file and it needs
no by-law. Reusable: fetch `Elec2025_Mun.csv`, filter on the 5-digit municipal code,
keep `Statut du candidat` starting `Élu`, join on the district or the poste number.

### ⛔ Gatineau — one Données Québec package, two vintages, and the format decides which

Package `vgat_-1582475471` offers CSV, GeoJSON, KML, SHP and XLSX. **Four of the five
resource URLs are `www.gatineau.ca/upload/donneesouvertes/…`, served live by the city.
The GeoJSON is the one exception — a Données-Québec-side copy — and it is the old map.**

| | last-modified | `DAT_REC` | `CONS` |
|---|---|---|---|
| DQ GeoJSON `district_electoraux.json` | 2025-04-24 | `20210101` | 2021-25 council |
| city `DISTRICT_ELECTORAUX.zip` (staged) | **2025-11-25** | `20240101` | 2025-29 council |

⚠ **And they are not the same map.** District-for-district IoU between the two:
100.0000% for seventeen of nineteen, `de Hull-Wright` **96.4566%** and
`du Parc-de-la-Montagne-Saint-Raymond` **96.9578%** — a real adjustment along their
shared limit, carried out under the division reviewed for 2025. Note what that does to
the usual checks: **19 districts before and after, all 19 names identical, and nothing
below 95%.** A `--compare` summary alone reads as "the map did not move".

ⓘ **Reusable test, after Terrebonne's `_archive_<date>` sibling:** when a package offers
one layer in several formats, HEAD every URL. Divergent `last-modified` headers inside a
single package mean it is not a package — it is a live directory and a stale mirror
sharing one title. Cost here: the wrong file was already downloaded and inspected before
the headers were checked.

### ⛔ Lévis — Données Québec is four years stale and it is a different map

Package `districts-electoraux-levis` still serves the file uploaded **2022-07-21**
(package `metadata_modified` 2023-06-26). Its `CONSEILLER` field is the 2021-25 council.
Measured against the city's live layer, same fifteen names on both sides:

| district | IoU | | district | IoU |
|---|---:|---|---|---:|
| Charny | **44.4154%** | | Notre-Dame | 94.2007% |
| Bienville | 56.7050% | | Saint-Étienne | 96.0763% |
| Saint-Rédempteur | 56.7127% | | Breakeyville | 97.2147% |
| Taniata | 58.9272% | | Saint-Nicolas | 99.1078% |
| Villieu | 77.5753% | | Saint-Jean | 99.2484% |
| Lauzon | 88.9717% | | Pintendre | 99.8914% |
| Christ-Roi | 92.9151% | | Saint-David | 99.9155% |
| Saint-Romuald | 93.9031% | | | |

Nine of fifteen below 95%. Lévis redivided for 2025 and kept every name.

★ **The current layer is not published as open data at all.** It lives on
`cartes.ville.levis.qc.ca`, the city's on-prem ArcGIS Server behind the public
"Districts et secteurs" map at `levis.ca`. That host is named nowhere on the site's
HTML — it appears only inside the Nuxt JS chunks, which had to be enumerated from
`/fr/carte-interactive` and grepped for `MapServer`. ⚠ **Licence therefore rests on an
assertion**, not on anything the artifact carries; the city's ArcGIS Online org
(`villedelevis`, `niuNnVx0H92jOc5F`) holds only an `ElectoralDistricts` service last
modified 2020-11-10 and a `carte_electoral_2017` layer, neither current.

ⓘ Lévis is **one tier**, despite being staged under a two-tier expectation. The same
MapServer publishes `Arrondissements` as layer 4, but the boroughs elect nobody — Lévis
wound up its borough councils in 2009 and MAMH's 2025 results record fifteen
`Conseiller` posts and a mayor, with no borough post of any kind.

### ★ Trois-Rivières — the only file in the tranche that states its own vintage

`geo.v3r.net`'s `DonneesOuvertes/DistrictsElectoraux_LAYER_DO` layer 60 carries, per
district: `V_ANNEE = 2024` (the division's reference year), `V_DATE_RECENSEMENT =
2025-10-18` (the elector census for the 2025-11-02 poll), `V_CONSEILLERS` = the
2025-elected council, `V_ACTIF = 1`. No inference needed.

ⓘ The Données Québec copy is the **same map** — 99.9171% to 99.9799% IoU
district-for-district, coordinate precision and nothing else — so either file loads the
same polygons. The live layer was staged because the DQ extract drops exactly the four
fields that carry the evidence: it publishes `OBJECTID / ID / NOM / V_ACTIF /
MUNICIPALITE` and no `V_ANNEE`, no `V_DATE_RECENSEMENT`, no councillor.

⚠ **And it inverts the one flag it kept.** The live layer stores `V_ACTIF` as a smallint
and every district is `1`; the DQ GeoJSON, CSV *and* shapefile all render it as the
string `"Non"` for all fourteen. Taken at face value that says the published set is
inactive — the exact opposite of the truth. The published field dictionary
(`districtselectorauxv3r.pdf`) describes `V_ACTIF` only as "Statut du district
électoral" and lists four fields the extract does not contain.

### ⓘ Per-file notes

- **Gatineau** — zipped shapefile, `.prj` is bare `GCS_WGS_1984` (degrees), `.cpg` says
  UTF-8. 19 features, 19 distinct districts. Fields `MUNID`, `CODEID`, `DISTRICT`,
  `NUM`, `CONS`, `PART`, `ARR`, `DT01`, `DT02`, `NBR_ELECT`, `DAT_REC`, `EMAIL`, `AIRE`,
  `PERIM`, `ENTITEID`. ⚠ `CODEID` and `NUM` disagree — Mitigomijokan is CODEID 19 /
  NUM 5, because the district was inserted into the ballot order rather than appended;
  `CODEID` is the one that does not move. ⛔ Names carry their leading article
  (`d'Aylmer`, `de l'Orée-du-Parc`) where our 19 ids and MAMH's results do not
  (`aylmer`, `oree-du-parc`); the draft spec strips it in a `name_builder`, without
  which the load would mint nineteen new ids and detach the whole council.
- **Saguenay** — GeoJSON, no `crs` member (RFC 7946 WGS84; first coordinate
  −71.382, 48.421 agrees). 15 features, 15 distinct. ⚠ **Lowercase** field names —
  `id`, `municipalite`, `nom`, `conseiller` — where every other publisher in this
  tranche uppercases them. Districts are numbered, not named. Field dictionary published
  alongside as `sag_districtselectoraux_meta.pdf`.
- **Lévis** — GeoJSON via `outSR=4326`; **native SR is EPSG:32187** (NAD83 / MTM zone
  **7**, metres) — not the zone 8 that Longueuil, Terrebonne and Trois-Rivières sit in.
  15 features, 15 distinct. Fields `OBJECTID`, `NUMERO`, `NOM`, `UTILISATEURCREATION`,
  `NOMCONSEIL`.
- **Trois-Rivières** — GeoJSON via `outSR=4326`; native SR **EPSG:32188**. 14 features,
  14 distinct. ⛔ Names KEEP their article (`de Châteaudun`, `du Carmel`) and so do our
  14 ids — the opposite of Gatineau, in the same tranche. The convention is per-city
  because the mirror that minted the ids was per-city.
- **Saint-Jean-sur-Richelieu** — GeoJSON, no `crs` member (first coordinate −73.231,
  45.313). 12 features, 12 distinct. Fields `ID`, `MUNICIPALITE`, `NOM`, `CONSEILLER`,
  `INFORMATION` (a per-district `sjsr.ca` profile URL). ⛔ `ID` runs 81875–81886 — a
  city-wide feature sequence, not a by-law district number (district *n* is `ID − 81874`)
  — so it is deliberately NOT recorded as `authority_district_id`, the same call made at
  Longueuil for its OBJECTID. ⚠ The resource filename carries the publisher's own typo,
  `sjsr-disctricts-electoraux.geojson`; kept as-is. ⓘ No second publication of this
  layer exists anywhere — no ArcGIS Online org, no reachable map server — so unlike
  Lévis and Gatineau there was no independent copy to cross-check against, and the
  councillor field is the only thing dating the file.

ⓘ **All five files name the sitting councillor**, three of them refreshed to the
2025-elected council. Gatineau additionally carries the party (`PART`) and a
`gatineau.ca` email per district; Saint-Jean-sur-Richelieu carries a profile URL.

### `--compare` against what we hold (2026-09-02, no writes)

| set | authoritative | held | matched | mean | min | below 95% | we hold, authority does not |
|---|---:|---:|---:|---:|---:|---:|---|
| `gatineau-districts` | 19 | 20 | 19 | 98.9087% | 96.0596% | 0 | `2481017` |
| `saguenay-districts` | 15 | 19 | 15 | 96.7180% | 91.2581% | 3 | `2494068`, `chicoutimi`, `jonquiere`, `la-baie` |
| `levis-districts` | 15 | 16 | 15 | 83.9369% | 44.1075% | 8 | `2425213` |
| `trois-rivieres-districts` | 14 | 15 | 14 | 92.7316% | 49.3602% | 4 | `2437067` |
| `saint-jean-sur-richelieu-districts` | 12 | 13 | 12 | 95.5116% | 68.5824% | 2 | `2456083` |

Zero districts in "authority has, we do not" anywhere — every slug in all five files
lands on a row we already hold, including Gatineau's nineteen once the article is
stripped. The single unmatched row in four of the five sets is the stray
`census-subdivisions/<7-digit>` municipality polygon the dossier already documents.

⛔ **Read the Gatineau row against the Gatineau section above.** Mean 98.91%, min 96.06%,
**nothing below 95%** — and the map still moved, at Hull-Wright and
Parc-de-la-Montagne—Saint-Raymond. A clean summary is not a clean bill of health when
the two sides share a publisher.

⚠ **Saguenay's three orphans are structural, not a shortfall.** The authoritative file
publishes districts only; the `saguenay-boroughs/*` rows filed inside
`saguenay-districts` have no counterpart in it and no counterpart in MAMH's 2025 results
either, which record fifteen `Conseiller` posts and a mayor and no borough post — the
présidents d'arrondissement are designated from among the sitting councillors. So this
is a source that OMITS a tier, not one that MIXES tiers as Sherbrooke's does, and no
`kind_builder` applies. Whether to retire or keep those three rows is the cutover
migration's decision.
