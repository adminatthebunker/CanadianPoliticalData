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
