# Québec municipal roster — 2025 general election results

The replacement for the Open North municipal roster in Québec, which is a full
election cycle stale: queried 2026-08-19, Open North still served **Valérie
Plante** as mayor of Montréal, 9½ months after Soraya Martinez Ferrada won on
2025-11-02. Open North is *up* — it is simply not maintained — so re-running
`ingest-all-councils` cannot fix this. A new source was required.

## Source

| | |
|---|---|
| Publisher | Ministère des Affaires municipales et de l'Habitation |
| Catalogue | https://www.donneesquebec.ca/recherche/dataset/resultats-des-elections-municipales-generales |
| File | https://donneesouvertes.affmunqc.net/election_municipale/Elec2025_Mun.csv |
| Licence | **CC-BY 4.0** (`cc-by`), declared on the CKAN package |
| Retrieved | 2026-08-19 |
| Bytes | 1998339 |
| sha256 | 8148d2ceeb9b0061362afe82bcac34ce7b6a28ff6d3ef83c1f4161ab526f39dc |

Gate-free direct download: plain GET, no agreement, no account, no form.

## Shape

12,658 candidate rows, comma-delimited, **UTF-8 with BOM** (decode as
`utf-8-sig`; a plain utf-8 read leaves a BOM on the first column name).
21 columns. Province-wide: 1,061 municipalities, **7,835 elected**.

Columns that matter: `Nom de la municipalité`, `Nom de l'arrondissement`
(borough), `Nom du district électoral` (ward), `Type de poste`, `Nom` /
`Prénom`, `Nom du parti ou de l'équipe`, `Statut du candidat`.

⚠ **Winners are two statuses, not one**: `Élu` (3,228) and `Élu sans
opposition` (4,607). Filtering on equality with `Élu` silently drops 59% of
the elected officials in the province. Non-winning statuses are `Non élu`,
`Désistement`, `Égalité`, `Déces`, `Colistier remplacé` and empty.

⚠ **`Conseiller d'arrondissement` is a distinct office** (42 province-wide) and
is NOT a member of city council. Montréal returns 103 winners; excluding the 38
borough councillors gives exactly the 65-member city council (1 mayor + 46
`Conseiller` + 18 `Maire d'arrondissement`). ⓘ Sherbrooke and Longueuil are the
counter-example — Open North's held rosters for those two DO include their
borough councillors, so the exclusion is not a universal rule and composition
has to be decided per municipality rather than by office type alone.

## Other files in the same package

Earlier generations (2021, 2017, 2013, 2009, 2005) and MRC-level results are
published alongside. `Elec2021_Mun.csv` is the generation our stale rows came
from and is the reference for diffing what changed.
