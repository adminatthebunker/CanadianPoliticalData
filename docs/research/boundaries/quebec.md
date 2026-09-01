# Quebec — Electoral Boundary Research

> Standalone boundary/roster dossier for Quebec. Cross-cutting context
> (methodology, licence matrix, reconciliation strategy) lives in [`overview.md`](./overview.md).
> The legislative-data dossier for this jurisdiction is at [`../quebec.md`](../quebec.md).

**Agency:** Élections Québec (Directeur général des élections); delimitation by the **Commission de la représentation électorale (CRE)** | **Website:** https://www.electionsquebec.qc.ca | **Districts (current):** 125 | **Current order:** carte électorale de 2017, in force **2018-08-23** | **Next redistribution:** ⚠ **already enacted — 127 circonscriptions, in force when the 43rd legislature ends, expected within weeks of 2026-08-18**

**Status snapshot (2026-08-18):** 🚧 **Data is excellent; the licence is the problem; and the clock is running.** ✅ Élections Québec publishes real shapefiles for both the in-force and the incoming map, by plain HTTPS GET, no WAF, no registration. ⚠⚠ **Quebec is days-to-weeks away from a 125 → 127 redistribution.** The *Loi visant à assurer la représentation effective des électeurs* (2026, c. 15) was assented **2026-06-12** and takes effect when the 43rd legislature ends — the fixed-date general election is **2026-10-05**, so dissolution is imminent. Loading the wrong generation in either direction is a live risk for the next few weeks. ★ **The missing 125th district is `Chicoutimi`** (`CO_CEP` 918) — absent from `constituency_boundaries` entirely; the only "Chicoutimi" row we hold is a *municipal Saguenay borough*, which is exactly the kind of near-miss that makes a naive count look fine. ★★ **The postal concordance the brief asked about exists and is genuinely first-class** — but it is published by the **Institut de la statistique du Québec**, not Élections Québec: `CP Territoires`, **CC BY 4.0**, **220,513 Québec postal codes of which 99.87% resolve to exactly one circonscription**, with 100% lat/lng fill. That is a ready-made ground-truth set for measuring our point-in-polygon accuracy. ⛔ **The boundary files themselves are NOT open** — Élections Québec permits reproduction "à des fins non lucratives" only, and states that adaptation requires written authorisation. That needs a human decision before we ship. ★ `CO_CEP` is a clean 3-digit district key **within** a generation — and is **completely renumbered between generations, zero overlap**, which settles how to key the cutover. **Difficulty 1** to fetch; **licence is the blocker.**

---

## ⚠ Three generations are in play — get this right before loading anything

| Map | Districts | Status on 2026-08-18 | `effective_from` | `effective_to` | Staged at |
|---|---:|---|---|---|---|
| carte électorale **2011** | 125 | superseded | 2012 (see below) | `2018-08-22` | `prior/` — **list only, no geometry** |
| carte électorale **2017** | 125 | ✅ **IN FORCE** — load this one | `2018-08-23` | `NULL` for now | `current/` |
| carte électorale **2026** (Assemblée nationale) | **127** | 🚧 **enacted, not yet in force** | end of 43rd legislature — **imminent** | — | `pending/` |
| carte électorale 2026 (CRE version) | 127 | ⛔ **never in force — superseded before commencement** | — | — | not staged (PDF only) |

**The fourth row is a real trap.** Élections Québec's delimitation page offers two complete file
sets for "2026": one established by the **Commission de la représentation électorale** (published
in the *Gazette officielle du Québec* on **2026-01-14**) and one established by the **Assemblée
nationale**, which amended the Commission's decision before enacting it. Only the Assembly's
version will ever govern an election. The CRE version modified 51 circonscriptions; the Assembly
kept only 39 of those changes and preserved the 2017 delimitations in Île-de-Montréal and
Gaspésie–Bas-Saint-Laurent. ✅ Conveniently, **only the Assembly version is published as data** —
the CRE version is PDF maps only (`/autres/cartes-prov-rf-2026/`), so the data files under
`/autres/provincial/` are unambiguous. But anyone reading the page will see two parallel file
lists and must not assume they are the same map.

**When exactly does the 2026 map commence?** From `Metadonnees__Shapefile_CEP_2026.docx`, verbatim:

> Selon l'article 2 de la *Loi visant à assurer la représentation effective des électeurs*, la liste
> des circonscriptions électorales entrera en vigueur lorsque la 43e législature aura pris fin, sauf
> si cette fin survient le ou avant le 14 juillet 2026.

The 43rd legislature was still sitting on 2026-08-18, so the escape clause did not fire and the new
map **will** take effect. The general rule is stated by Élections Québec verbatim: *"La nouvelle
carte électorale entre en vigueur lorsque la législature prend fin. Si celle-ci prend fin moins de
six mois après la publication de la nouvelle carte électorale à la Gazette officielle du Québec, les
élections générales doivent se tenir sur la base de la carte électorale précédente."*

⏳ **Operational consequence.** Québec's fixed election date is the first Monday of October —
**2026-10-05** — so dissolution lands somewhere in late August / early September 2026. Between now
and then, the correct `effective_to IS NULL` row is the **2017** one. The day the legislature ends,
it becomes the **2026** one. **This dossier will go stale within weeks.** Recommend the build treat
the cutover as a scheduled event with a watch on the dissolution proclamation, not as a
one-time load. `UNTESTED — probe during build:` the exact dissolution date, which was not yet
announced on 2026-08-18.

## Current boundaries

- **Source URL(s):** https://donnees.electionsquebec.qc.ca/autres/provincial/circonscriptions_electorales_2017_shapefile.zip ; https://donnees.electionsquebec.qc.ca/autres/provincial/liste_circonscriptions2017.csv ; https://www.electionsquebec.qc.ca/cartes-electorales/revision-de-la-carte-electorale-du-quebec/la-carte-electorale-delimitation-finale/
- **Format:** Esri shapefile, zipped (4.8 MB). Six files: `.shp` / `.shx` / `.dbf` / `.prj` / `.CPG` + `Metadonnees_CEP_2017.docx`. ⚠ **No GeoJSON is published for the 2017 generation** — the `circonscriptions_electorales_sans_eau_*.json` GeoJSON exists only for 2026. A MapInfo `.tab` zip is also offered (2.8 MB); redundant, not staged.
- **CRS / projection:** **EPSG:3798** (NAD83 / MTQ Lambert) — ⚠ **asserted manually; the `.prj` carries no `AUTHORITY` clause and its `PROJCS` name is the non-standard string `LambertAQ`, so neither EPSG lookup nor name matching will resolve it.** `.prj` verbatim: `PROJCS["LambertAQ",GEOGCS["GCS_North_American_1983",DATUM["D_North_American_1983",SPHEROID["GRS_1980",6378137.0,298.257222101]],PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]],PROJECTION["Lambert_Conformal_Conic"],PARAMETER["False_Easting",800000.0],PARAMETER["False_Northing",0.0],PARAMETER["Central_Meridian",-70.0],PARAMETER["Standard_Parallel_1",50.0],PARAMETER["Standard_Parallel_2",46.0],PARAMETER["Scale_Factor",1.0],PARAMETER["Latitude_Of_Origin",44.0],UNIT["Meter",1.0]]`. Identification path, recorded so it can be checked: the parameter set (LCC, `lat_0=44`, `lon_0=-70`, `lat_1=50`, `lat_2=46`, `x_0=800000`, `y_0=0`, GRS80, metres) matches exactly three rows in PostGIS `spatial_ref_sys` — 3797 (NAD27), **3798 (NAD83)**, 3799 (NAD83 CSRS). The `.prj` datum is `D_North_American_1983`, which selects **3798**. Verified by transforming the `.shp` header bbox through PostGIS: `(79569, 113908)` → `-79.0919, 44.6414` and `(1697055, 2105873)` → `-53.3478, 61.9077`, i.e. Québec. ✅ **Corroborated by the agency**: the *2026* metadata document states "•EPSG : 3798" outright for the identical projection; the 2017 metadata gives the parameters but no EPSG number.
- **Attribute schema:** dBASE, 125 records, last updated 2017-05-26. ⚠ **`.CPG` extension is UPPERCASE** (`Circonscriptions_électorales_2017_shapefile.CPG`); a `*.cpg` glob returns empty. Content is `UTF-8` and it is honest — `Bourassa-Sauvé`, `Châteauguay`, `Îles-de-la-Madeleine` all decode cleanly as UTF-8. Fields: `CO_CEP` N(3) — district code; `NM_CEP` C(30) — district name; `NM_TRI_CEP` C(30) — accent-stripped uppercase sort key (e.g. `BOURASSASAUVE`).
- **District ID field:** **`CO_CEP`** — a 3-digit integer, 125 distinct values, no duplicates, range 104–938, **all even**. This is the stable authority key the brief asked about, and it is a good one *within* a generation. See § Reconciliation for the cross-generation caveat, which is severe.
- **Effective date:** **`effective_from = 2018-08-23`** — the **legal in-force date**, per amendment A2.
  - **Statutory mechanism:** the delimitation was published by the CRE in the *Gazette officielle du Québec*, **partie 2, n° 9B, 2 mars 2017**. Commencement is governed by the *Loi sur l'Assemblée nationale* (chapitre A-23.1) as applied by the Élections Québec rule quoted above: the map enters into force when the legislature ends. From `Metadonnees_CEP_2017.docx`, verbatim: *"Les circonscriptions sont celles décrites par la Commission de la représentation électorale à la Gazette officielle du Québec du 2 mars 2017 (G.O., partie 2, no 9B, 2 mars 2017). **Elles entreront en vigueur lorsque la législature aura pris fin en application de la Loi sur l'Assemblée nationale (chapitre A-23.1).**"*
  - **The legislature ended 2018-08-23.** Primary source, Assemblée nationale du Québec, verbatim: *"Le 23 août 2018, le lieutenant-gouverneur a proclamé la dissolution de l'Assemblée nationale."* First used at the general election of 2018-10-01.
  - ⚠ **Dataset-metadata date — DO NOT USE: 2017-03-02** (Gazette publication), with file timestamps of 2017-05-26. **The metadata date leads the legal date by ~18 months.** This is the A2 discrepancy in its textbook form, and it has already contaminated our data twice over: our `source_set` is named `quebec-electoral-districts-2017` after the publication year, and Open North stamped `effective_from = 2023-01-01`, a mirror date that is neither.
- **Superseded date:** `NULL` **today**, but see the generations table — this becomes `2026-XX-XX` (day the 43rd legislature ends) within weeks.
- **District count:** **125**, matching the 125 seats. ✅ Verified one-district-per-row: `.dbf` 125 records, **125 distinct `CO_CEP`, 125 distinct `NM_CEP`, zero duplicates**; `.shx` implies 125; `.shp` 125 polygon records. 130 rings across 125 records — **4 records are multipart** (islands and detached fragments), but multipart *within* a record, which PostGIS ingests as a `MultiPolygon` without any dissolve step. No island-row duplication.
- **Difficulty (1–5):** **1** to fetch — direct, unauthenticated, structured. The difficulty in Québec is entirely licence and timing, not access.
- **Notes:**
  - The 2017 file predates a rename. **`Bourget` (`CO_CEP` 370) was renamed `Camille-Laurin` in 2021**, and the shapefile — frozen at 2017-05-26 — still says `Bourget`. Our DB already holds the post-rename name. ⚠ A name-keyed load of this file would insert a duplicate `Bourget` row alongside the existing `Camille-Laurin`. Key on `CO_CEP`, or special-case 370.
  - Only 4 records are multipart, which is low for a province with the Îles-de-la-Madeleine and a long island-strewn coast — consistent with a land-and-water partition rather than a coastline-clipped file.

## Prior boundaries (immediately preceding)

- **Source URL(s):** https://donnees.electionsquebec.qc.ca/autres/provincial/liste_circonscriptions2011.csv ; https://www.electionsquebec.qc.ca/cartes-electorales/anciennes-cartes-electorales-du-quebec/
- **Format:** ⛔ **List only — the geometry is gone.** `liste_circonscriptions2011.csv` (2.2 KB, 125 districts) is still served, but `circonscriptions_electorales_2011_shapefile.zip`, `…_2011_mapinfo.zip` and `…_2001_shapefile.zip` all return **HTTP 403** from the same directory that serves the 2017 and 2026 archives. Élections Québec appears to retire geometry for superseded generations while keeping the district lists.
- **CRS / projection:** n/a — no geometry obtained.
- **Attribute schema:** CSV, `;`-delimited, **CP1252**, two columns: `BSQ` (the district code — note the agency calls the same value `BSQ` in the CSV and `CO_CEP` in the shapefile) and `CIRCONSCRIPTION`.
- **District ID field:** `BSQ`. ⚠ Codes were renumbered again at this boundary: `Abitibi-Est` is `579` in 2011, `648` in 2017, `689` in 2026.
- **Effective date:** the 2011 map governed from the end of the 39th legislature (2012) to 2018-08-22. **`needs confirmation`** — the precise dissolution date was not established in this pass, and no metadata document accompanies the surviving CSV.
- **Superseded date:** **`2018-08-22`** — the day before the 2017 map took force.
- **District count:** 125 — the seat count has been 125 since 1989, so 2011 → 2017 → 2026 is 125 → 125 → 127. The 2026 change is the first seat-count change in this table's history.
- **Difficulty (1–5):** **5** for geometry (withdrawn by the publisher), **1** for the district list.
- **Notes:** **Known bounded gap:** we cannot build a two-generation temporal model for Québec from Élections Québec alone. If the prior generation is wanted, the "Anciennes cartes électorales" and "Atlas historique des circonscriptions électorales du Québec" pages are the next place to look, and the Fondation Lionel-Groulx publishes an *Atlas des élections au Québec* on Données Québec under CC-BY-SA 4.0 — a third-party source, share-alike, and not staged here. Low priority: the immediate need is the 2017 → 2026 cutover, not 2011 history.

## Pending boundaries (enacted, not yet in force) — the 2026 map

- **Source URL(s):** https://donnees.electionsquebec.qc.ca/autres/provincial/circonscriptions_electorales_2026_shapefile.zip ; https://donnees.electionsquebec.qc.ca/autres/provincial/circonscriptions_electorales_sans_eau_2026.json ; https://donnees.electionsquebec.qc.ca/autres/provincial/liste_circonscriptions2026.csv
- **Format:** Esri shapefile zipped (5.1 MB, ten files inside a directory prefix — note the 2017 archive has **no** directory prefix, so an unzip routine must not assume either), **plus GeoJSON** (2.4 MB) and CSV. ⚠ The GeoJSON is named `circonscriptions_electorales_sans_eau_2026.json` — **"sans eau", i.e. water removed.** Per the A4 note that cartographic-vs-digital is a difference of *extent*: this is a land-clipped variant with a **different extent** from the shapefile, not a generalised version of it. For point-in-polygon a water-clipped layer can leave a point in the St. Lawrence or the Gulf matching **no** district. `UNTESTED — probe during build:` whether the two agree on land. **Recommend loading the shapefile, not the GeoJSON**, despite the brief's general GeoJSON preference — the preference assumes equivalent content, and here it does not hold. No `avec_eau` GeoJSON is published (probed: 403).
- **CRS / projection:** **EPSG:3798**, stated outright by the agency this time. `.prj` verbatim: `PROJCS["NAD_1983_MTQ_Lambert",GEOGCS["GCS_North_American_1983",DATUM["D_North_American_1983",SPHEROID["GRS_1980",6378137.0,298.257222101]],PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]],PROJECTION["Lambert_Conformal_Conic"],PARAMETER["False_Easting",800000.0],PARAMETER["False_Northing",0.0],PARAMETER["Central_Meridian",-70.0],PARAMETER["Standard_Parallel_1",46.0],PARAMETER["Standard_Parallel_2",50.0],PARAMETER["Latitude_Of_Origin",44.0],UNIT["Meter",1.0]]` — ⚠ still **no `AUTHORITY` clause**, but `Metadonnees__Shapefile_CEP_2026.docx` lists "•EPSG : 3798" explicitly. The standard parallels are listed in the opposite order from 2017 (46/50 vs 50/46) and the `Scale_Factor` parameter is dropped; both are cosmetic and do not change the CRS.
- **Attribute schema:** dBASE, 127 records, last updated 2026-06-18. `.CPG` **UPPERCASE** again, `UTF-8`. Fields: `CO_CEP` N(3), `NM_CEP` C(**50**), `NMTRI_CEP` C(50). ⚠⚠ **Two schema drifts from 2017 in the same file** — the sort-key field is renamed `NM_TRI_CEP` → **`NMTRI_CEP`** (underscore dropped), and `NM_CEP` widens from 30 to 50 characters. This is exactly the A4 "same agency, different field names across generations" trap. A loader written against 2017 will `KeyError` on 2026.
- **District ID field:** `CO_CEP`, 127 distinct, range 117–837, **all odd**.
- **Effective date:** **end of the 43rd legislature — date not yet known on 2026-08-18.** Statutory instrument: ***Loi visant à assurer la représentation effective des électeurs*, 2026, chapitre 15**, sanctionnée **2026-06-12**, published *Gazette officielle du Québec*, Partie 2, **2026-06-17, n° 24A**. Commencement per its article 2, quoted verbatim above.
- **Superseded date:** n/a.
- **District count:** **127** (125 + 2). ✅ One-district-per-row verified: 127 records, **127 distinct `CO_CEP`, 127 distinct `NM_CEP`**, 129 rings across 127 records, **only 1 multipart record**.
- **Difficulty (1–5):** **1**.
- **Notes:**
  - **The two new circonscriptions are `Bellefeuille`** (Laurentides–Lanaudière) **and `Marie-Lacoste-Gérin-Lajoie`** (Estrie–Centre-du-Québec).
  - Full name delta, 2017 → 2026. **New:** `Arthabaska-L'Érable`, `Bellefeuille`, `Camille-Laurin`, `Daniel-Johnson`, `Marie-Lacoste-Gérin-Lajoie`, `Matane-Matapédia-Mitis`, `Pierre-Laporte`, `Rivière-du-Loup–Témiscouata–Les Basques`, `Vimont-Auteuil`. **Retired:** `Arthabaska`, `Bourget`, `Johnson`, `Laporte`, `Matane-Matapédia`, `Rivière-du-Loup-Témiscouata`, `Vimont`. Note `Camille-Laurin` appears as "new" only because the 2017 *file* still says `Bourget`; the rename happened in 2021.
  - ⚠⚠ **The 2026 file introduces U+2013 EN DASH into district names** — `Anjou–Louis-Riel`, `Saint-Henri–Sainte-Anne`, `Charlevoix–Côte-de-Beaupré`, `Drummond–Bois-Francs`, `Rivière-du-Loup–Témiscouata–Les Basques`, `Rouyn-Noranda–Témiscamingue`. The **2017 file uses plain ASCII hyphens throughout** and so does our DB. At cutover, a naive name join will silently miss those six. See § Reconciliation.
  - ⚠ **The 2026 CSV is CP1252, not ISO-8859-1, and not UTF-8** — it contains `0x96` (en dash) and `0x92` (right single quote), which live in the CP1252 C1 range. Decoding as Latin-1 raises **no exception** and silently yields `Anjou\x96Louis-Riel` and `Arthabaska-L\x92Érable`. The 2017 CSV is plain Latin-1 (no C1 bytes), so a decoder that worked on 2017 corrupts 2026. ⚠ And note the **shapefile `.dbf` is UTF-8 while the CSV beside it is CP1252** — same agency, same download page, same generation, two encodings.

## District ↔ elected official mapping

- **Source URL(s):** https://www.assnat.qc.ca/fr/deputes/index.html ; https://www.electionsquebec.qc.ca/cartes-electorales/circonscriptions-provinciales/
- ✅ **Our roster is complete and already joined.** 125 sitting MNAs, **124 with a populated `constituency_id`**, and **zero dangling references** — every populated `constituency_id` resolves to a row in `constituency_boundaries`. Québec is in far better shape than Nunavut on this axis.
- ⚠ **The one MNA without a riding is `Marie-Karlynn Laflamme`**, whose `constituency_name` is *also* blank. Given that `Chicoutimi` is the one district with no polygon, the pairing is near-certain — but it is an inference from two independent gaps lining up, not something confirmed against the Assemblée nationale roster in this pass. **Flagged, not asserted.** See handoff items.
- ✅ `politicians.qc_assnat_id` already exists (integer, promoted to a UNIQUE partial index by migration `0038`). **It is a member ID, not a district ID** — it identifies the deputy, not the circonscription, so it does not substitute for `CO_CEP`. The two are complementary: `qc_assnat_id` keys the person, `CO_CEP` keys the seat.
- Sanity check performed: `Paul St-Pierre Plamondon` resolves to `quebec-electoral-districts-2017/camille-laurin`, which is correct and confirms the post-2021 name is what our roster carries.
- ⏳ **The entire roster turns over at the 2026-10-05 general election**, onto 127 seats. Any cutover plan has to sequence boundaries and roster together.

## Postal-code correspondence (if published)

★★ **This is the find the brief was after, and it is better than a concordance — it is a
ready-made accuracy test set.** One correction to the framing: it is published by the
**Institut de la statistique du Québec**, not Élections Québec.

- **Source URL(s):** https://www.donneesquebec.ca/recherche/dataset/cp-territoires ; https://www.donneesquebec.ca/recherche/dataset/1a6267da-82ed-4ea0-b35d-9e9618a58ce7/resource/bbd5521c-120f-494b-b2a3-a6a682d8d458/download/cp_territoires.csv
- **Product:** `CP Territoires` (formerly `AQgéopostal`), version **mai 2026**, refreshed **quarterly**. Built from the **Référentiel québécois des adresses (RQA)** of the ministère des Ressources naturelles et des Forêts — a real provincial address register, not a crowdsourced or municipal patchwork.
- **Licence:** ✅ **CC BY 4.0.** Genuinely open, commercial use permitted, redistribution permitted. ★ Note the irony: **the concordance is more freely licensed than the boundaries it describes.**
- **Format / encoding:** CSV, **UTF-8**, quoted, comma-separated, 105 MB, 50 columns. (Contrast the Élections Québec CSVs, which are CP1252.) A SAS variant and a 2.1 MB usage guide are also published; a companion `cp_territoires_retraits.csv` (2.5 MB) lists retired codes.
- **Measured contents** (counted from the staged file, not quoted from the guide):
  - **240,358 rows**, **220,513 distinct postal codes**.
  - **125 distinct `CO_CEP`** — all of them, **all even**, i.e. the **2017 generation**. Confirmed by the guide, which labels the field *"Code de CEP (circonscription électorale provinciale) **(2017)**"*. So it describes the map that is in force today, which is exactly what a cross-check needs. ⏳ It will need re-pulling after the 2026 cutover.
  - **Zero rows with an empty `CO_CEP`.**
  - **100% `LAT`/`LONG` fill** — coordinates in decimal degrees, **NAD 1983** per the guide (EPSG:4269, not 4326; sub-metre difference, but state it explicitly rather than assume).
- **Key columns:** `CP` (postal code), `CO_CEP`/`NOM_CEP` (provincial district), `CO_CEF`/`NOM_CEF` (**federal** district), `LAT`/`LONG`, `PRC_REP` (share of dwellings), `CPCGADIDU` (composite key), plus municipality / MRC / région administrative / CLSC / school-board / census columns.
- ⚠ **It is one row per (postal code × territory) intersection, not one row per postal code.** 15,700 codes (7.1%) appear on more than one row, up to 22 rows for a single code. A naive join fans out. Use `PRC_REP` to pick the dominant row or to weight.
- ★ **The number that matters for us: 99.87% of Québec postal codes resolve to exactly one circonscription.** Only **292 codes (0.13%)** straddle a district boundary, and none straddles more than three. So there is a **220,221-postal-code unambiguous ground-truth set**.
- ⚠ **`CO_CEF`/`NOM_CEF` are labelled "(2013)"** in the guide — the **superseded** federal Representation Order, not the 2023 one. So this is **not** a drop-in open substitute for PCFRF, and it should not be offered to the federal workstream as one without that caveat attached. The provincial side is current; the federal side is a generation behind.

### Proposed accuracy measurement — the first empirical one available to this project

The file supplies both a coordinate and the expected district, so no external geocoder is needed:

1. Load the 2017 shapefile into `constituency_boundaries` (`ST_SetSRID(…, 3798)` → `ST_Transform(…, 4326)`).
2. For each of the 220,221 unambiguous codes, run our PIP on `ST_SetSRID(ST_MakePoint(LONG, LAT), 4269)` transformed to 4326.
3. Compare the resulting `constituency_id` against `CO_CEP`. Report the disagreement rate overall and per district.
4. Run it twice — once against `boundary` and once against `boundary_simple` — to **measure what the ~555 m simplification tolerance actually costs**. That number is currently unknown and is assumed harmless across the whole table.

⚠ **State the limitation honestly when reporting the result.** ISQ derives `CO_CEP` by its own
spatial assignment at the address level, so this is **not** an independent check of point-in-polygon
*as a method*. It is an independent check of **our implementation** — our CRS handling, our
transform, our generation, our simplification tolerance, and our slug mapping — against a
provincial statistical agency's. Those are precisely the failure modes this corpus exists to
prevent, so the test is worth running; it just should not be reported as "our lookup is 99.x%
accurate against ground truth."

## Terms / Licensing

⛔ **Élections Québec boundary data is non-commercial-use-only. This is the blocker for Quebec.**

- **Instrument:** no named licence. Terms are stated in two places: the `Contraintes d'utilisation` clause inside each shapefile's bundled metadata `.docx`, and the site-wide conditions page.
- **Licence URL:** https://www.electionsquebec.qc.ca/notre-institution/conditions-dutilisation/ (the 2017 metadata still points at the dead `http://www.electionsquebec.qc.ca/fr/copyright.asp`).
- **Metadata clause, verbatim** (from `Metadonnees__Shapefile_CEP_2026.docx`):
  > Quiconque peut, sans autorisation ni frais, mais à la condition de mentionner la source, reproduire sous quelque support ou télécharger cette donnée, **sauf s'il le fait à des fins de commercialisation ou dans le but d'en retirer quelque avantage que ce soit**. Dans ce cas, une autorisation doit être obtenue d'Élections Québec.
- **Conditions page, verbatim:**
  > **Utilisation à des fins non lucratives**
  >
  > Vous pouvez télécharger et reproduire tout élément de notre site Web à des fins non lucratives. Dans ce contexte, aucune autorisation n'est requise et c'est gratuit.
  >
  > Vous devez cependant mentionner la source et notre droit d'auteur (©). Si le texte indique le nom de l'auteur, vous devez aussi le mentionner.
  >
  > **Toute autre utilisation est interdite, à moins d'une autorisation écrite de notre part. Il en va de même si vous souhaitez adapter le contenu d'un élément de notre site.**
- **Reading of it, plainly:** three separate problems. (1) Commercial use, or use "dans le but d'en retirer quelque avantage que ce soit", needs prior written authorisation. (2) **Adaptation** needs written authorisation too — and reprojecting to EPSG:4326 and simplifying to `boundary_simple` is arguably adaptation. (3) Attribution including the © symbol is mandatory in all cases.
- **Also verbatim, and worth recording:** *"Toute personne qui utilise ce site Web est liée à ses conditions d'utilisation par la simple consultation du site."* Binding on mere consultation. Note this is **not** a click-through — there was nothing to accept and nothing was accepted, so the standing rule was not engaged by downloading.
- **ISQ `CP Territoires`:** ✅ **CC BY 4.0**, no restrictions beyond attribution. Required credit line, verbatim: *"Institut de la statistique du Québec, CP Territoires – Fichier de géolocalisation des codes postaux^MO basé sur le Référentiel québécois des adresses (RQA) du ministère des Ressources naturelles et des Forêts."* The guide adds: *"ce produit peut être obtenu gratuitement … être exploité, modifié et redistribué sous la seule contrainte de créditer l'auteur des données d'origine."*

## Rate limits / auth

- ✅ **No WAF, no auth, no rate limiting observed** across ~40 requests to `www.electionsquebec.qc.ca`, `donnees.electionsquebec.qc.ca`, `www.donneesquebec.ca` and `statistique.quebec.ca`.
- `www.elections.quebec` 301s to `www.electionsquebec.qc.ca`. Data host is a separate origin, `donnees.electionsquebec.qc.ca`.
- ⚠ **The data host returns `HTTP 403` with a 7,745-byte HTML body for any path that does not exist** — it is not a 404. This is the A4 "check the payload, not the status code" trap inverted: here the *status* is the reliable signal (200 + `application/x-zip-compressed` vs 403 + `text/html`), but a script that treats 403 as "forbidden, retry with credentials" will loop forever on what is really a not-found. Directory listing is not available (`/autres/provincial/` → 403).
- ⛔ **Dead end — Données Québec has no provincial boundary set.** The CKAN portal at `donneesquebec.ca` carries a great deal of *municipal* electoral geography (Montréal, Laval, Gatineau, Québec, Repentigny, Saint-Hyacinthe districts and sections de vote) but **nothing from the DGEQ or the CRE**. Élections Québec publishes on its own host only. Recorded so nobody re-probes; the municipal agent may find the portal useful.
- ⛔ **Dead end — `nunavutlegislation.ca`-style statute lookup was not needed here**; the statutory citation came from the shapefile's own metadata document, which is a better source anyway.

## Staged files

Staged under `data/boundaries/quebec/` with `PROVENANCE.md`. **122 MB total** (105 MB of it the
concordance CSV), well inside the 500 MB budget. Nothing converted, reprojected, or loaded; archives
were unzipped **into the scratchpad only** to read headers per the no-GDAL procedure.

| Generation | File | Bytes | sha256 (first 16) |
|---|---|---:|---|
| current (2017, in force) | `circonscriptions_electorales_2017_shapefile.zip` | 5,062,935 | `98f8b968f5bdc9bd…` |
| current | `liste_circonscriptions2017.csv` | 2,195 | `99603d55787a767a…` |
| **pending (2026, NOT in force)** | `circonscriptions_electorales_2026_shapefile.zip` | 5,070,694 | `abfb6f8b4c2c2f2b…` |
| pending | `circonscriptions_electorales_sans_eau_2026.json` | 2,380,742 | `5c22379acdffc613…` |
| pending | `liste_circonscriptions2026.csv` | 3,870 | `474f8a654a2cae46…` |
| prior (2011) | `liste_circonscriptions2011.csv` | 2,168 | `32c750bfe22924c9…` |
| concordance | `cp_territoires.csv` | 110,057,201 | `47fa0704a583db7c…` |
| concordance | `cp_territoires_retraits.csv` | 2,591,898 | `2a9296556a099c4b…` |
| concordance | `guide-cp-territoires-mai-2026.pdf` | 2,081,144 | `dee824bb8c111042…` |

⚠ The `pending/` directory name is load-bearing — see the generations table. Do not let it be
flattened into `current/` by a tidy-up.

## Reconciliation with `constituency_boundaries`

**What we hold:** `source_set = 'quebec-electoral-districts-2017'`, **124 rows**, `level = 'provincial'`,
`province_territory = 'QC'`, `boundaries_version = 'current'`, `effective_from = 2023-01-01`
(the Open North mirror date — **not** a legal date; the correct value is `2018-08-23`),
`effective_to = NULL`. Slug pattern `quebec-electoral-districts-2017/{kebab-name}`.

### ★ The missing 125th district is `Chicoutimi`

`CO_CEP` **918** in the 2017 map. Confirmed by normalised set difference between the shapefile's
125 `NM_CEP` values and our 124 rows. ⚠ The only `Chicoutimi` row anywhere in the table is
`saguenay-boroughs/chicoutimi`, a **municipal** Saguenay borough — a near-miss that will satisfy a
careless `WHERE name ILIKE '%chicout%'` check and hide the gap.

The same diff surfaces one apparent mismatch in the other direction: our DB has `Camille-Laurin`,
which the 2017 file does not, because the file predates the 2021 rename of `Bourget` (`CO_CEP` 370).
That is a naming artifact, not a missing district. Net: **exactly one district genuinely absent.**

### ⚠ `CO_CEP` is renumbered wholesale between generations — zero overlap

This is the single most important fact for the cutover plan, and it is counter-intuitive for a
field that looks like a stable code:

| | 2011 | 2017 | 2026 |
|---|---|---|---|
| code count | 125 | 125 | 127 |
| range | — | 104–938 | 117–837 |
| parity | — | **all even** | **all odd** |
| overlap with 2017 | — | — | **0 codes** |

**108 district names survive from 2017 into 2026, and not one of them keeps its `CO_CEP`.**
`Abitibi-Est` goes 579 → 648 → 689. `Acadie` goes 338 → 299. The parity flip (even → odd) looks
deliberate, presumably to make a stale join fail loudly rather than silently — but only if you
notice.

**Consequences:**
- `CO_CEP` is an excellent **within-generation** key: unique, compact, no accents, no dash
  ambiguity. Use it to key the load and to dedupe.
- `CO_CEP` is **useless as a cross-generation identity key**. It must be stored as a
  per-generation *attribute*, never as the primary identity.
- Cross-generation identity therefore has to come from the **name**, which brings the dash problem
  below.

### ⚠ Dash normalisation is mandatory, and our table is already inconsistent

| Source | Dash used | Example |
|---|---|---|
| QC 2017 shapefile | ASCII hyphen `-` | `Charlevoix-Côte-de-Beaupré` |
| **QC 2026 shapefile** | **U+2013 EN DASH** | `Charlevoix–Côte-de-Beaupré` |
| ISQ `CP Territoires` | **U+2013 EN DASH** | `Charlevoix–Côte-de-Beaupré` |
| our QC rows | ASCII hyphen | `Charlevoix-Côte-de-Beaupré` |
| our **federal** rows | **U+2014 EM DASH** | `Rivière-des-Prairies—Pointe-aux-Trembles` |

Three different dash characters across one table. At least six 2026 districts carry an en dash.
A build that joins on raw names will silently drop them. **Recommend a shared normalisation
helper** — NFKD, strip combining marks, fold `—`/`–`/`-` to `-`, collapse whitespace, casefold —
applied on both sides of every name join, and used to generate slugs. The 22/22 and 125/125
matches reported in this corpus were all obtained that way.

### Proposed `constituency_id` scheme

Keep the existing shape, `{source_set}/{kebab-slug}`, and keep the **year in the set name** —
Québec is the strongest argument in the corpus for doing so, because it is about to hold two
generations simultaneously with 108 shared names:

- current: `quebec-electoral-districts-2017/{slug}` — **already what we use; no re-key needed**, just the 125th row added and `effective_from` corrected to `2018-08-23`.
- pending: `quebec-electoral-districts-2026/{slug}`.

⚠ Note the set name `…-2017` refers to the **Gazette publication year**, not the in-force year
(2018). That is now baked into 124 existing `constituency_id` values and into `politicians.constituency_id`
for 124 MNAs. **Recommend leaving it alone** — re-keying 248 rows to fix a cosmetic year in a slug
is not worth the coordination cost, provided `effective_from` carries the correct legal date and
this dossier records the discrepancy. Flag for **Agent X2**: if the global re-key standardises on
in-force years, Québec's would become `…-2018` and `…-2026`, and that decision should be taken
once, not per-jurisdiction.

### Cutover checklist for the imminent 2026 change

1. Add the missing `Chicoutimi` row to the 2017 set (125/125).
2. Correct 2017 `effective_from` to `2018-08-23`.
3. Load the 2026 shapefile as `quebec-electoral-districts-2026/*` with `effective_from` **NULL/held** until the dissolution date is known.
4. On dissolution: set 2017 `effective_to` = dissolution date, 2026 `effective_from` = dissolution date + 0 (the Act says the list enters into force *when the legislature ends*, not the day after — ⚠ **this differs from Nunavut's "the day after" rule; do not copy the NU pattern**).
5. Re-point the 125 → 127 MNA roster after the 2026-10-05 election.
6. Re-pull `CP Territoires` once ISQ publishes a version whose `CO_CEP` is the 2026 generation.

## Research-handoff items

- ⛔ **The Élections Québec licence is non-commercial and forbids adaptation without written permission. This needs a human decision before Québec boundaries ship.** Verbatim: *"Toute autre utilisation est interdite, à moins d'une autorisation écrite de notre part. Il en va de même si vous souhaitez adapter le contenu."* Three questions: **(a)** Does CPD count as non-commercial today? The project went single-user in 2026-06 and the bulk-export surface was decommissioned, but the public dev API still advertises paid dev/pro tiers. **(b)** Does reprojecting to 4326 and generating `boundary_simple` count as "adapter"? **(c)** Should we simply email `Info@electionsquebec.qc.ca` and ask for written authorisation, naming the project? A one-paragraph request would probably resolve all three, and Québec is a jurisdiction we cannot serve without it. **I have not contacted them** — outbound contact is the operator's call.
- ⏳ **Quebec redistributes within weeks and this dossier expires with it.** 125 → 127 when the 43rd legislature ends, ahead of the 2026-10-05 fixed-date election; the exact dissolution date was not announced as of 2026-08-18. **Who watches for the dissolution proclamation, and does the build schedule a cutover job or wait for a manual trigger?** Getting this wrong in either direction produces confidently wrong answers for every Québec address.
- **Confirm that `Marie-Karlynn Laflamme` is the member for `Chicoutimi`.** She is the one MNA of 125 with no `constituency_name` and no `constituency_id`; `Chicoutimi` is the one district of 125 with no polygon. The inference is strong but it is an inference. A single check against `assnat.qc.ca/fr/deputes/` settles it, and it is roster-side work rather than boundary-side.
- **Should the 220,221-code accuracy measurement be run as part of the build, and who owns the result?** It is cheap once the polygons are loaded, it is the first empirical accuracy number this project would have, and it doubles as a regression test for future generations. It would also produce the first measurement of what `boundary_simple`'s ~555 m tolerance actually costs. I have staged everything needed but have not run it — it requires loading polygons, which is out of scope for research.
- **The 2011 geometry is withdrawn by the publisher (HTTP 403), so Québec cannot have a two-generation temporal model from the primary source.** Only the district-list CSV survives. **Is a prior generation wanted badly enough to pursue third-party sources** (the Fondation Lionel-Groulx *Atlas des élections au Québec* on Données Québec is CC-BY-**SA**, i.e. share-alike, which is its own problem), **or do we accept 2018-08-23 as the earliest Québec date we can answer for?**
- **Dash normalisation is a cross-cutting decision, not a Québec one.** Our table currently holds ASCII hyphens in QC rows and em dashes in federal rows, and the incoming QC 2026 file uses en dashes. **Should there be one shared normalisation helper for the whole build, and should stored `name` values be normalised or left verbatim as published?** My recommendation: store `name` exactly as published (it is the legal name) and normalise only for joining and slug generation — but that only works if every jurisdiction's loader uses the same helper.
- ⚠ **`CO_CEF` in the concordance is the 2013 federal order, not 2023.** Worth passing to the federal workstream so it is not mistaken for an open PCFRF substitute — the provincial half is current, the federal half is a generation stale.

## Status

- [x] Current boundaries (2017, 125 districts) located and staged (2026-08-18)
- [x] **In-force generation established** — 2017 is current; 2026 is enacted but not yet in force
- [x] Pending boundaries (2026, 127 districts) located and staged, **quarantined in `pending/`**
- [x] CRE-vs-Assembly version distinguished — only the Assembly version is published as data
- [x] Missing 125th district identified — **`Chicoutimi`, `CO_CEP` 918**
- [x] CRS identified — **EPSG:3798** both generations; ⚠ asserted manually, neither `.prj` has an `AUTHORITY` clause; corroborated by the 2026 metadata document
- [x] Attribute schemas read per generation — ⚠ **field names drift** (`NM_TRI_CEP` → `NMTRI_CEP`)
- [x] Encoding sidecars checked — ⚠ `.CPG` **UPPERCASE** on both; ⚠ CSVs are **CP1252**, shapefiles UTF-8
- [x] One-district-per-row verified — 125/125 and 127/127 distinct IDs, no island-row duplication
- [x] Legal in-force date established per A2 — **2018-08-23**, metadata date 2017-03-02 recorded as the discrepancy
- [x] **Postal concordance located, staged, and quantified** — ISQ `CP Territoires`, CC BY 4.0, 220,513 codes, 99.87% unambiguous
- [x] Matrix fragment written to `_matrix/quebec.md` per A1 — `overview.md` not touched
- [ ] **Licence cleared for our use — ⛔ blocked: non-commercial restriction + adaptation clause**
- [ ] Prior generation (2011) geometry — **unavailable, publisher returns 403**
- [ ] `Marie-Karlynn Laflamme` → `Chicoutimi` confirmed — roster-side
- [ ] Accuracy measurement run against the 220,221-code set — build phase
- [ ] 2026 cutover executed on dissolution — **scheduled event, weeks away**
