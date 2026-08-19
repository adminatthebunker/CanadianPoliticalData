# Quebec — boundary staging provenance

Retrieved 2026-08-18 over plain HTTPS with a browser `User-Agent`. No licence click-through,
no registration, no form submission was required or performed. Total staged: 122 MB.

⚠ **Licence warning — read before redistributing anything in `current/`, `pending/` or `prior/`.**
The Élections Québec files are **non-commercial use only**; see the verbatim terms below and
`docs/research/boundaries/quebec.md` § Terms / Licensing. The `concordance/` files are the
only openly-licensed material here (CC BY 4.0).

| File | Source URL | Retrieved (UTC) | Bytes | sha256 (first 16) | Licence |
|---|---|---|---:|---|---|
| `current/circonscriptions_electorales_2017_shapefile.zip` | https://donnees.electionsquebec.qc.ca/autres/provincial/circonscriptions_electorales_2017_shapefile.zip | 2026-08-18T01:16Z | 5062935 | `98f8b968f5bdc9bd…` | Élections Québec — non-commercial, attribution |
| `current/liste_circonscriptions2017.csv` | https://donnees.electionsquebec.qc.ca/autres/provincial/liste_circonscriptions2017.csv | 2026-08-18T01:16Z | 2195 | `99603d55787a767a…` | Élections Québec — non-commercial, attribution |
| `pending/circonscriptions_electorales_2026_shapefile.zip` | https://donnees.electionsquebec.qc.ca/autres/provincial/circonscriptions_electorales_2026_shapefile.zip | 2026-08-18T01:16Z | 5070694 | `abfb6f8b4c2c2f2b…` | Élections Québec — non-commercial, attribution |
| `pending/circonscriptions_electorales_sans_eau_2026.json` | https://donnees.electionsquebec.qc.ca/autres/provincial/circonscriptions_electorales_sans_eau_2026.json | 2026-08-18T01:16Z | 2380742 | `5c22379acdffc613…` | Élections Québec — non-commercial, attribution |
| `pending/liste_circonscriptions2026.csv` | https://donnees.electionsquebec.qc.ca/autres/provincial/liste_circonscriptions2026.csv | 2026-08-18T01:16Z | 3870 | `474f8a654a2cae46…` | Élections Québec — non-commercial, attribution |
| `prior/liste_circonscriptions2011.csv` | https://donnees.electionsquebec.qc.ca/autres/provincial/liste_circonscriptions2011.csv | 2026-08-18T01:35Z | 2168 | `32c750bfe22924c9…` | Élections Québec — non-commercial, attribution |
| `concordance/cp_territoires.csv` | https://www.donneesquebec.ca/recherche/dataset/1a6267da-82ed-4ea0-b35d-9e9618a58ce7/resource/bbd5521c-120f-494b-b2a3-a6a682d8d458/download/cp_territoires.csv | 2026-08-18T01:23Z | 110057201 | `47fa0704a583db7c…` | **CC BY 4.0** |
| `concordance/cp_territoires_retraits.csv` | https://www.donneesquebec.ca/recherche/dataset/1a6267da-82ed-4ea0-b35d-9e9618a58ce7/resource/496f25f1-ba32-4854-88ce-84d91473b3be/download/cp_territoires_retraits.csv | 2026-08-18T01:23Z | 2591898 | `2a9296556a099c4b…` | **CC BY 4.0** |
| `concordance/guide-cp-territoires-mai-2026.pdf` | https://statistique.quebec.ca/fr/fichier/fichier-geolocalisation-codes-postaux-base-referentiel-quebecois-adresses.pdf | 2026-08-18T01:23Z | 2081144 | `dee824bb8c111042…` | **CC BY 4.0** |

## Directory meaning — `pending/` is not `current/`

- `current/` — the **2017 map, 125 circonscriptions**, legally in force since **2018-08-23** and
  still in force on the retrieval date.
- `pending/` — the **2026 map, 127 circonscriptions**, enacted but **NOT YET IN FORCE**. It takes
  effect when the 43rd legislature ends, expected within weeks of the retrieval date. **Do not
  load into `constituency_boundaries` with `effective_to IS NULL` until the legislature has
  actually ended.**
- `prior/` — the 2011 map. **Geometry could not be obtained**; only the district-list CSV
  survives on the data host. See the dossier.
- `concordance/` — ISQ `CP Territoires`, the postal-code → circonscription table.

## Licence — verbatim

### Élections Québec (boundary files)

From `Metadonnees__Shapefile_CEP_2026.docx`, bundled inside `circonscriptions_electorales_2026_shapefile.zip`
(the 2017 metadata carries the same clause, differing only in the contact name and URL):

> **Contraintes d'utilisation**
>
> Quiconque peut, sans autorisation ni frais, mais à la condition de mentionner la source,
> reproduire sous quelque support ou télécharger cette donnée, sauf s'il le fait à des fins de
> commercialisation ou dans le but d'en retirer quelque avantage que ce soit. Dans ce cas, une
> autorisation doit être obtenue d'Élections Québec.

From https://www.electionsquebec.qc.ca/notre-institution/conditions-dutilisation/ :

> **Utilisation à des fins non lucratives**
>
> Vous pouvez télécharger et reproduire tout élément de notre site Web à des fins non lucratives.
> Dans ce contexte, aucune autorisation n'est requise et c'est gratuit.
>
> Vous devez cependant mentionner la source et notre droit d'auteur (©). Si le texte indique le
> nom de l'auteur, vous devez aussi le mentionner.
>
> Toute autre utilisation est interdite, à moins d'une autorisation écrite de notre part. Il en
> va de même si vous souhaitez adapter le contenu d'un élément de notre site.

Note the second sentence of the last paragraph: **adaptation** — which arguably covers
reprojection and simplification — is also stated to require written authorisation.

### Institut de la statistique du Québec (`concordance/`)

CC BY 4.0. Required attribution, verbatim from the guide:

> L'utilisation de CP Territoires est assujettie aux modalités de la licence Creative Commons 4.0 –
> Attribution CC BY, en utilisant la mention : **Institut de la statistique du Québec, CP Territoires –
> Fichier de géolocalisation des codes postaux^MO basé sur le Référentiel québécois des adresses (RQA)
> du ministère des Ressources naturelles et des Forêts.**

And:

> CP Territoires est dorénavant assujetti aux modalités de la licence Creative Commons 4.0 –
> Attribution CC BY. Ainsi, ce produit peut être obtenu gratuitement sur le site web de l'Institut
> de la statistique du Québec, être exploité, modifié et redistribué sous la seule contrainte de
> créditer l'auteur des données d'origine : le ministère des Ressources naturelles et des Forêts
> et l'Institut de la statistique du Québec.
