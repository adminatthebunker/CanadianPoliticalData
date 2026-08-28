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
