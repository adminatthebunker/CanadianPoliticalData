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
