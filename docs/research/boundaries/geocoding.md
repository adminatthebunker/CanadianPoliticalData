# Postal-code geocoding — open-licence source research

> Cross-cutting dossier: the postal-code → lat/lng half of the "who represents me" lookup.
> This is not a jurisdiction dossier — it has no boundary files and no roster. Methodology,
> licence matrix and reconciliation strategy live in [`overview.md`](./overview.md); the
> point-in-polygon half is already ours and is covered by the per-jurisdiction dossiers.

**Constraint:** open-licence sources only, no paid datasets (operator, 2026-08-17) | **Incumbent:** Open North Represent `/postcodes/` | **Active postal codes in Canada:** ~926,425 | **Derivable open-licence:** 856,929 (92.5%) | **Recommended source:** StatCan National Address Register (46-26-0002)

**Status snapshot (2026-08-18):** ⛔ **The incumbent is down right now, not hypothetically.** `represent.opennorth.ca` fails two ways at once: its Let's Encrypt certificate expired `Aug 7 09:51:36 2026 GMT` (11 days ago), so Node's `fetch()` rejects the connection before any HTTP happens, and the origin behind it returns `502 Bad Gateway` even with TLS verification disabled. ⚠ With only **8 rows** in `public.postcode_cache`, the effect is precise: those 8 postcodes still resolve, and **every other postcode in Canada returns `503`**. ★ **An open-licence replacement exists, is staged, and is measured — not estimated.** StatCan's National Address Register (cat. 46-26-0002, released 2026-06-26, Statistics Canada Open Licence) yields **856,929 distinct six-character postal codes with WGS84 coordinates — 92.5% of the ~926,425 active codes** — from 17,362,476 address rows at 99.67% postal-code fill, across all **13** provinces and territories. Against the ~97% structural ceiling for any civic-address method, that is ~95% of what is reachable. ✅ **The rural worry is answered: rural FSA coverage is 100%, and rural 6-character lookup is 98.26% accurate federally** (urban 99.91%). ⛔ **But rural *FSA-level* fallback is unusable — 68.46% federally and 52.82–57.88% provincially**, so the system must never return a single silent district for a rural FSA; see § How the system should behave. ★ Bonus: `FED_CODE` on the **2023 Representation Order** joins directly to our existing `constituency_id`. ⛔ PCCF and PCFRF permanently closed; ⛔ Open North publishes no postal data to mirror.

---

## The dependency today

`services/api/src/lib/postcode.ts:120` issues the single remaining outbound Open North call in the entire API:

```
https://represent.opennorth.ca/postcodes/{CODE}/?format=json
```

and reads exactly three things from the response — `centroid.coordinates` (`[lng, lat]`), `city`, `province`. Everything downstream of that point is already ours: the point-in-polygon runs against our own `public.constituency_boundaries` (1,949 rows).

**Two consumers:** `/api/public/v1/postcodes/:postcode` (rich shape, boundaries included) and `/api/public/v1/boundaries/lookup?postcode=` (centroid only).

**Current failure, verified 2026-08-18 00:52 UTC:**

- **TLS:** `subject=CN=represent-tempeh.opennorth.ca`, `issuer=C=US, O=Let's Encrypt, CN=R13`, `notBefore=May 9 09:51:37 2026 GMT`, `notAfter=Aug 7 09:51:36 2026 GMT`. Expired. `curl` returns `(60) SSL certificate problem: certificate has expired`; Node's `fetch()` throws the same way, which `fetchPostcode()` catches and converts to `PostcodeUpstreamError("unavailable")`.
- **Origin:** with `curl -k`, the response is `502 Bad Gateway` from `nginx/1.10.3 (Ubuntu)`. So the certificate is not the only problem and there is no client-side workaround — including the tempting one of relaxing TLS verification, which would be wrong anyway.
- **Cache depth:** `SELECT count(*) FROM public.postcode_cache` → **8**, oldest `2026-05-26`, newest `2026-08-14`. The SWR design in `postcode.ts` is sound; it has just never been given a corpus to fall back on. A cache that only ever fills on demand cannot be an outage buffer.

⚠ **Trap for the build phase.** The FSA path costs up to three sequential upstream calls per cold FSA: Open North's endpoint 404s on 3-character input, so `postcode.ts:112` probes `{FSA}1A1`, `{FSA}0A0`, `{FSA}1B1` in order. Any local dataset removes that hack outright — an FSA centroid becomes a `GROUP BY left(postcode,3)` over data we hold.

**Known bounded gaps:** this dossier covers the geocode only. It does not address the staleness of `constituency_boundaries` itself, which is the subject of the per-jurisdiction boundary dossiers.

## Restricted sources (closed questions)

Recording these with citations so the question does not get re-opened in six months.

### ⛔ PCCF — Postal Code<sup>OM</sup> Conversion File (StatCan 92-154-X)

- **Source URL(s):** https://www150.statcan.gc.ca/n1/en/catalogue/92-154-X
- **Status:** discontinued as a public release product. Verbatim: *"The last issue of this publication was the Postal Code<sup>OM</sup> Conversion File (PCCF), June 2017 file released on December 13, 2017."*
- **Distribution now:** as of February 2018, shared between StatCan and Canada Post. StatCan continues to supply share partners and the Data Liberation Initiative; *"Canada Post Corporation will assume the distribution of this product to all others."*
- **Why unusable:** DLI access is restricted to affiliates of participating post-secondary institutions, for teaching and research. We are neither. The Canada Post route is a commercial licence, which the operator has ruled out.
- **Open derivative check:** none found. DLI-licensed PCCF copies are mirrored by universities (e.g. Borealis, `doi:10.5683/SP3/HHXSMZ`, March 2026 issue) but each sits behind DLI authentication and carries the same end-use restriction. No historical release predating the restriction has been re-published under an open licence — the Canada Post licence attaches to the postal code data itself, so age does not launder it.
- **Difficulty (1–5):** **5** — blocked by licence, not by technology.

### ⛔ PCFRF — Postal Codes<sup>OM</sup> by Federal Ridings File (StatCan 92-178-X)

- **Source URL(s):** https://www150.statcan.gc.ca/n1/en/catalogue/92-178-X ; guide https://www150.statcan.gc.ca/n1/en/catalogue/92-178-G
- **Status:** *"The last issue of this publication was the 2013 Representation Order file released on December 13, 2017."* Same February 2018 StatCan/Canada Post distribution split as the PCCF.
- **Blocking clause:** *"Users must obtain a Postal Code End-use licence agreement to continue to use and receive the Postal Code Data Products."* That is a licence-acceptance event, which per the standing instructions no agent may perform.
- **Price:** **$892/yr** (established independently by the federal boundary agent). Elections Canada publishes no open equivalent — Maps Corner, all three CKAN datasets and the redistribution site were checked; only the interactive VIS lookup exists.
- ★ **And we do not need it.** Our lookup is already point-in-polygon against our own polygons, and an authoritative polygon strictly beats a weighted postal→district concordance. The federal postal problem reduces entirely to *geocoding* — getting a coordinate — which is what the rest of this dossier is about. A concordance was never the shape of the answer.
- **Doubly stale anyway:** the final issue is keyed to the **2013** Representation Order. We hold **2023** Representation Order boundaries (`constituency_id` prefix `federal-electoral-districts-2023-representation-order/`), so even a licensed PCFRF would be two redistributions behind for federal use.
- **Superseded by:** ★ the NAR carries `FED_CODE` on the 2023 order. See § The derivation path.
- **Difficulty (1–5):** **5** — blocked by licence.

### ⏸️ Geocoder.ca / Geolytica

- **Source URL(s):** https://geocoder.ca/?freedata=1 ; https://geocoder.ca/?terms=1 ; https://geocoder.ca/?sued=1
- **Record count:** **926,425** unique postal codes, geocoded to street level, dataset dated **2026-05-01**. This is the best available count of what "complete" means, and the yardstick used throughout this dossier.
- **Provenance:** crowdsourced, **not** Canada Post licensed. Canada Post sued Geolytica in 2012; the action was abandoned in 2016 with no finding, and no Canadian case law establishes postal codes as copyrightable. This is the same reasoning already recorded in the header comment of `postcode.ts`.
- **Paid tier:** ~$998 CAD for the full 6-character file. ⛔ Out of scope — operator has ruled out paid datasets.
- **Free tier:** free to non-profits under **Creative Commons Attribution 2.5 Canada**, by email request. ⛔ **Not a public download** — it requires identifying ourselves, asserting non-profit status, and accepting terms. That is exactly the registration-and-licence-acceptance action the standing instructions forbid an agent from performing. Raised as a handoff item rather than pursued.
- **Difficulty (1–5):** **5** for an agent; **2** for a human who is willing to send the email and who can honestly claim non-profit status.

## Candidate open sources

### ★ StatCan National Address Register (NAR) — cat. 46-26-0002 — **recommended**

- **Source URL(s):** https://www150.statcan.gc.ca/n1/pub/46-26-0002/462600022022001-eng.htm ; archive https://www150.statcan.gc.ca/n1/pub/46-26-0002/2022001/202606.zip ; user guide https://www150.statcan.gc.ca/n1/pub/46-26-0002/462600022022002-eng.pdf
- **Format:** one zip containing per-province CSVs in two parallel trees, `Addresses/Address_<PRUID>.csv` and `Locations/Location_<PRUID>.csv`, joined on `LOC_GUID`. Large provinces are split into `_part_N` members. 55 members total; full manifest staged at `data/boundaries/_geocoding/nar_202606_manifest.csv`.
- **CRS / projection:** `BG_LATITUDE` / `BG_LONGITUDE` are plain WGS84 decimal degrees — no `.prj`, no reprojection needed, drops straight into our lookup. (`BG_X` / `BG_Y` in the address file are a projected pair and are **not** what you want; ignore them.)
- ⚠ **Positional accuracy — these are blockface centroids, not rooftop points.** Verbatim from the user guide: *"Latitude and longitude are coordinates derived from the blockface centroid (when blockface was available). A blockface represents one side of a street between two consecutive features intersecting that street."* So each address point is the midpoint of its street segment, not the building. That is entirely adequate for riding assignment — segment-scale error is tens of metres against districts kilometres across — but it sets the precision floor, and it is the reason an address sitting on a street that *forms* a riding boundary can land on the wrong side. This is a floor on the source, not on our processing; averaging many points per postal code does not overcome it. It is one component of the residual error measured in § The rural question.
- **Attribute schema (address file, 31 fields):** `LOC_GUID`, `ADDR_GUID`, `APT_NO_LABEL`, `CIVIC_NO`, `CIVIC_NO_SUFFIX`, `OFFICIAL_STREET_NAME`, `OFFICIAL_STREET_TYPE`, `OFFICIAL_STREET_DIR`, `PROV_CODE`, `CSD_ENG_NAME`, `CSD_FRE_NAME`, `CSD_TYPE_ENG_CODE`, `CSD_TYPE_FRE_CODE`, `MAIL_STREET_NAME`, `MAIL_STREET_TYPE`, `MAIL_STREET_DIR`, `MAIL_MUN_NAME`, `MAIL_PROV_ABVN`, **`MAIL_POSTAL_CODE`**, `BG_DLS_LSD`, `BG_DLS_QTR`, `BG_DLS_SCTN`, `BG_DLS_TWNSHP`, `BG_DLS_RNG`, `BG_DLS_MRD`, `BG_X`, `BG_Y`, `BF_REPPOINT_X`, `BF_REPPOINT_Y`, `BU_N_CIVIC_ADD`, `BU_USE`.
- **Attribute schema (location file, 12 fields):** `LOC_GUID`, `CSD_CODE`, **`FED_CODE`**, `FED_ENG_NAME`, `FED_FRE_NAME`, `ER_CODE`, `ER_ENG_NAME`, `ER_FRE_NAME`, **`BG_LATITUDE`**, **`BG_LONGITUDE`**, `BF_REPPOINT_LATITUDE`, `BF_REPPOINT_LONGITUDE`.
- **District ID field:** `FED_CODE` — a 5-digit SGC federal electoral district code, e.g. `13001`. ★ This is exactly the suffix of our existing `constituency_id`; see § Reconciliation.
- **Effective date:** release `202606`, published **2026-06-26**. Federal district names in the file (`Fredericton—Oromocto`, `Moncton—Dieppe`, `Saint John—Kennebecasis`, `Acadie—Annapolis`, `Sackville—Bedford—Preston`, `Sydney—Glace Bay`) are **2023 Representation Order** names, not 2013 ones — confirmed by inspection, not assumed.
- **District count:** 10 FEDs in NB, 11 in NS, both matching the 2023 order.
- **Coverage:** all **13** provinces and territories — PRUIDs 10, 11, 12, 13, 24, 35, 46, 47, 48, 59, 60, 61, 62. Includes NL, YT and NU, which the ODA omits entirely.
- **Size:** `202606.zip` = **1,665,944,959 bytes** (1.67 GB). ✅ Staged at `data/boundaries/_geocoding/nar/202606.zip` (sha256 `c87df8d3…a564364`) after the coordinator raised the budget. Staged only — not unzipped; every measurement here streams members in-memory.
- **Difficulty (1–5):** **1** — documented product, stable URL, plain CSV, no auth, no click-through, `Range` supported.
- **Notes:** the register is built from StatCan's Building Register and validated against two independent sources. Verbatim from the user guide: *"The corresponding mailing version of the address is added and follows Canada Post's addressing guidelines."* Note **guidelines**, not licensed data — the NAR follows Canada Post's *formatting conventions*. Unlike the PCCF and PCFRF catalogue pages, the NAR carries no Canada Post distribution carve-out and no end-use licence requirement. ⚠ This distinction is the whole legal basis of the recommendation and is flagged for operator confirmation in § Research-handoff items.

### ⚠ StatCan Open Database of Addresses (ODA) — cat. 46-26-0001 — **rejected on measurement**

- **Source URL(s):** https://www.statcan.gc.ca/en/lode/databases/oda ; metadata https://www.statcan.gc.ca/en/lode/databases/oda/metadata ; files `https://www150.statcan.gc.ca/n1/en/pub/46-26-0001/2021001/ODA_<PR>_v1.zip`
- **Format:** zipped CSV, one per province.
- **Attribute schema (22 fields):** `latitude`, `longitude`, `source_id`, `id`, `group_id`, `street_no`, `street`, `str_name`, `str_type`, `str_dir`, `unit`, `city`, **`postal_code`**, `full_addr`, `city_pcs`, `str_name_pcs`, `str_type_pcs`, `str_dir_pcs`, `csduid`, `csdname`, `pruid`, `provider`.
- **Effective date:** version **1.0**, released **2021-04-29**. No v2 published as of 2026-08-18 — five years stale.
- **Coverage:** 10 jurisdictions only — AB, BC, MB, NB, NS, NT, ON, PE, QC, SK. ⛔ **No NL, no YT, no NU.**
- **District count:** ~10 million address records from 99 data providers.
- **Difficulty (1–5):** **1** to obtain — and it does not matter, because the field we need is empty.
- **★ The measurement that rejects it.** The metadata describes `postal_code` as *"provided as is from original data"*, which turns out to mean "mostly absent". Eight provincial files downloaded and counted:

| Province | Rows | With 6-char postal code | Fill | Distinct postal codes |
|---|---:|---:|---:|---:|
| BC | 800,396 | 123,473 | 15.4% | 8,167 |
| NS | 1,075,714 | 142,126 | 13.2% | 11,767 |
| NB | 634,206 | 62,371 | 9.8% | 7,520 |
| QC | 1,254,237 | 79,170 | 6.3% | 6,264 |
| MB | 236,847 | 0 | 0.0% | 0 |
| NT | 6,996 | 0 | 0.0% | 0 |
| PE | 74,412 | 0 | 0.0% | 0 |
| SK | 157,715 | 0 | 0.0% | 0 |

  **33,718 distinct postal codes across eight provinces** — under 4% of the national total. Four provinces contribute literally nothing.

- **Why it fails, precisely:** postal codes in the ODA come from a handful of individual *municipal* publishers, not from any provincial or federal source. Grouping the populated rows by `provider` gives the entire national contribution: Coquitlam (55,459), Halifax (142,126), Moncton (40,144), New Westminster (36,569), Nanaimo (31,289), Fredericton (22,227), Longueuil (79,170). Seven cities. That is the whole of it. The ODA is a civic-address database that happens to carry a postal code wherever one municipality chose to publish one.
- **Superseded by:** the NAR, which is the same StatCan programme's successor and carries the field properly. ~~Initially treated as the highest-value lead per the brief.~~

### ⏸️ OpenAddresses Canada

- **Source URL(s):** https://openaddresses.io/ ; https://github.com/openaddresses/openaddresses ; coverage https://results.openaddresses.io/coverage/world/
- **Format:** per-source CSV/GeoJSON generated from municipal open-data portals.
- **Licence:** per-source; the aggregate is commonly described as ODbL, with individual sources under their own municipal open licences.
- **Postal codes:** same structural problem as the ODA, and for the same reason — OpenAddresses and StatCan collaborated on the ODA's address-compilation code and draw from the same municipal portals. Where a city publishes a postal code, it survives; where it does not, there is nothing to harvest.
- **Difficulty (1–5):** **2** — structured and scriptable, but the yield ceiling is set by the same seven-ish municipalities.
- **Notes:** ⏸️ Deferred, not rejected outright — it is a plausible *supplement* for filling specific municipal gaps after the NAR is loaded, since it is refreshed continuously whereas the ODA is frozen at 2021. Not a primary source. **UNTESTED — probe during build** if per-city gap-filling turns out to be needed.

### ⏸️ OpenStreetMap `addr:postcode`

- **Source URL(s):** https://download.geofabrik.de/north-america/canada.html ; tag stats https://taginfo.geofabrik.de/north-america:canada/
- **Format:** `canada-latest.osm.pbf`, ~6.0 GB. Overpass is viable for targeted extraction; a full-country pull is not.
- **Licence:** **ODbL**. ⚠ Share-alike. Mixing ODbL postal centroids into a table we redistribute or expose via the public API raises a copyleft question the other candidates do not. Since the NAR alone is sufficient, taking on ODbL obligations for a marginal gain is a bad trade.
- **Measured coverage (taginfo, data until 2026-08-17T20:19:49Z):** 704,242 objects carry `addr:postcode` — 208,326 nodes, 494,539 ways, 1,377 relations — but only **97,961 distinct values**. Against 926,425 active codes that is a **~11% ceiling**, and the distinct-value count includes malformed and non-Canadian strings, so the true figure is lower. For scale, `addr:housenumber` has 6,325,195 objects, so postal code is tagged on roughly 11% of OSM addresses in Canada.
- **Difficulty (1–5):** **3** — the extraction is routine; the licence and the coverage ceiling are the problems.
- **Notes:** ⏸️ Deferred. Best use is as an independent cross-check on a sample of NAR centroids, not as a source.

### ⚠ Provincial and municipal civic-address open data

- **Source URL(s):** enumerated authoritatively in `Data_Sources.csv`, shipped inside every ODA provincial zip — 99 providers with dataset URL, licence URL, licence title, version, attribution statement, and download date. That file is the best single index of Canadian open address data and is worth keeping regardless of what we ingest.
- **Postal codes:** the measurement in the ODA section above **is** the measurement of this category, because the ODA is precisely the aggregation of these sources. Seven municipalities out of 99 providers publish postal codes.
- **BC — DataBC Address Geocoder:** the *API* is open and returns postal codes on request; whether the underlying *dataset* is downloadable in bulk is a separate question. **UNTESTED — probe during build**, and low priority: swapping one outbound provincial API dependency for the Open North one we are trying to remove reproduces the failure mode this whole exercise exists to eliminate.
- **QC — Adresses Québec, AB, ON, NS civic addresses:** all feed the ODA already; their postal-code contribution is included in the zeros above.
- **Difficulty (1–5):** **4** — 99 separate licences, 99 refresh cadences, and a measured yield under 4%. The integration cost is enormous and the payoff is a rounding error next to the NAR.
- **Notes:** ⛔ Not worth pursuing as a source. ★ Do keep `Data_Sources.csv` as a licence index.

## The derivation path

The brief's hypothesis was that we would have to *derive* 6-character centroids from civic-address data because no ready-made open file exists. **The measurement says otherwise: the derivation is unnecessary, because the NAR already carries the postal code.** The "derivation" reduces to a two-file join and a `GROUP BY`.

**The join:**

```sql
-- conceptual; the build phase decides the actual staging shape
SELECT a.MAIL_POSTAL_CODE                AS postcode,
       avg(l.BG_LATITUDE)                AS centroid_lat,
       avg(l.BG_LONGITUDE)               AS centroid_lng,
       count(*)                          AS address_points,
       mode() WITHIN GROUP (ORDER BY l.FED_CODE) AS dominant_fed
  FROM nar_address  a
  JOIN nar_location l USING (LOC_GUID)
 WHERE a.MAIL_POSTAL_CODE ~ '^[A-Z][0-9][A-Z][0-9][A-Z][0-9]$'
 GROUP BY 1;
```

**Measured nationally — the full register, not a sample.** The archive was staged on 2026-08-18 and every `Addresses/` member streamed: **17,362,476 address rows across all 13 provinces and territories.**

| PR | Address rows | Postal-code fill | Distinct postal codes | of which rural |
|---|---:|---:|---:|---:|
| ON | 6,246,543 | 99.9% | 282,771 | 1,062 |
| QC | 4,568,811 | 100.0% | 217,887 | 1,013 |
| BC | 2,371,842 | 99.7% | 117,688 | 643 |
| AB | 1,900,424 | 98.7% | 88,590 | 583 |
| NB | 400,100 | 99.9% | 56,761 | 0 |
| NS | 537,686 | 99.1% | 28,503 | 256 |
| MB | 572,158 | 99.1% | 25,924 | 412 |
| SK | 427,749 | 99.6% | 22,337 | 587 |
| NL | 215,268 | 99.5% | 10,969 | 378 |
| PE | 87,085 | 98.9% | 4,106 | 50 |
| YT | 18,535 | 93.4% | 909 | 17 |
| NT | 11,989 | 99.9% | 473 | 25 |
| NU | 4,286 | 100.0% | 11 | 11 |
| **National** | **17,362,476** | **99.67%** | **856,929** | **5,037 (0.59%)** |

★ **856,929 distinct six-character postal codes — 92.5% of Geocoder.ca's 926,425.**

~~National estimate ~677,000 (~73%), extrapolated from a 22.2% FSA sample.~~ Superseded by the exact count above. The estimate was a floor, as flagged — it excluded ON, QC, AB and BC, which between them hold 707,000 codes. **The open-licence path lands at the top of the predicted range, not the bottom.**

**How close is that to the theoretical maximum?** StatCan's own analysis of Canada Post's Address Lookup File (92F0138) states that *"About 97% of the postal codes in the file are associated with delivery to a civic address"*, with the remainder being *"post office boxes and postal service routes"*. The NAR is a **civic**-address register, so ~97% is its structural ceiling — the missing 3% have no civic address to hang on. Against that ceiling, 92.5% of all codes means we capture **~95% of everything reachable by this method**. The residual ~4.5% is ordinary currency lag (see § Refresh cadence), not a design flaw.

**Two quality findings:**

- ★ **The register is fresher than the 2021 census FSA file.** NAR spans **1,673** FSAs against the 2021 file's 1,643, and contains FSAs the census file lacks: `E1K`, `E2R` (NB), `Y0C`, `Y1B` (YT). ⚠ **Trap:** do not "validate" NAR against `lfsa000b21a_e` and treat extra FSAs as errors — the FSA boundary file is the stale side of that comparison.
- ★ **Fill is uniformly high.** 99.67% nationally; the weakest jurisdiction is YT at 93.4% and only AB (98.7%) and PE (98.9%) fall below 99%.

**Known bounded gaps:**

- **Nunavut** — 11 distinct postal codes from 4,286 addresses, against roughly 25 communities. Real under-coverage, but consequence-free federally: NU is a single riding, so any point in the territory resolves correctly. It would matter if we added NU's 22 territorial districts, which we hold **zero** boundaries for.
- **PO-box-only and rural-route-only codes** — the ~3% structural blind spot quantified above. The `BU_N_CIVIC_ADD` field (e.g. `PO BOX 30`) shows the register carries non-civic delivery info where a civic address exists, but a code with *no* civic address anywhere cannot appear.

## The rural question

This is the section that decides whether the open-licence path is viable, so it gets the space. The worry, stated plainly: **NAR is a civic-address register. Rural Canada is where civic addressing is thinnest, rural FSAs are geographically enormous, and rural Canada is exactly where civic-data access matters most and alternatives are thinnest.** If rural postcodes silently resolve to the wrong riding, we would have built a confident-wrong-answer machine aimed at the people least able to route around it.

**Answer up front: 6-character rural lookup is safe (98.26% federal). Rural FSA fallback is not (68.46% federal, ~53–58% provincial) and must never be used silently.**

### What "rural" means here, and how many there are

Canada Post's definition, via StatCan 92F0138: *"A postal code with a '0' in the second character is classified as 'rural' and all other postal codes are considered as 'urban' by Canada Post."* Rural codes are *"serviced by rural route drivers and/or postal outlets"*.

⚠ **This is a delivery-mode classification, not a settlement one** — the same source warns it *"does not signify that the postal code applies to 'rural areas' or 'urban areas' based on the current census population."*

- **Rural FSAs:** 181 of 1,643 (11.0%) in the StatCan 2021 file; 182 of 1,673 in NAR. Independently corroborated — StatCan 92F0153 reports 184 of 1,638 FSAs with rural mail delivery as of May 2011, so the proportion has been stable at ~11% for fifteen years.
- **Rural postal codes:** ★ **5,037 of 856,929 — just 0.59%** (measured across the full register). Rural codes are a *tiny* share of codes.
- **Rural addresses:** but a *large* share of addresses. Rural-FSA addresses are 32.8% of NS, 53.2% of PE, 32.8% of NL, 28.0% of NT, 24.6% of SK, 20.9% of YT, 18.2% of MB.

★ **That asymmetry is the whole story.** A rural postal code carries vastly more addresses than an urban one — Nova Scotia averages **682 addresses per rural code against 12.7 per urban code, a 54× ratio**. Rural codes are coarse *by Canada Post design*, covering a whole village or delivery route. This is a property of the postal system, not a defect in our data — and it is why "few rural postal codes" is the expected shape rather than evidence of a gap.

### Is the coverage actually there? Yes — this was a false alarm

The initial signal looked alarming: NAR New Brunswick contains **zero** postal codes with `0` in the second character. ⚠ **It is a false alarm, and it is worth recording why so nobody re-raises it.** New Brunswick genuinely has no rural delivery areas. StatCan 92F0138 says so in as many words:

> *"For example, New Brunswick does not contain any rural delivery areas although Statistics Canada does classify much of New Brunswick as rural."*

Checking the jurisdictions that *do* have rural FSAs: **every one is present in NAR.** NS all 14 (`B0C B0E B0H B0J B0K B0L B0M B0N B0P B0R B0S B0T B0V B0W`), SK all 11, NL all 13, MB all 10, PE both, NT both, NU all three, YT both plus one the 2021 census file lacks. Across the nine jurisdictions checked in detail, rural-FSA coverage is **100%**. ✅ **There is no systematic rural absence.**

### The measurement that matters — full national register, all 13 jurisdictions

For every postal code, take every NAR address point in it, read the `FED_CODE` StatCan assigned to each, and ask: does a single-answer lookup get it right?

| Level | Keys | Span >1 federal riding | Dominant-rule accuracy |
|---|---:|---:|---:|
| 6-char **urban** | 851,892 | 1,973 (0.23%) | ✅ **99.91%** |
| 6-char **rural** | 5,037 | 1,051 (20.87%) | ✅ **98.26%** |
| FSA **urban** | 1,491 | 861 (57.75%) | ⚠ 91.21% |
| FSA **rural** | 182 | 151 (82.97%) | ⛔ **68.46%** |

Per jurisdiction, federal:

| PR | rural 6-char | urban 6-char | rural FSA | urban FSA |
|---|---:|---:|---:|---:|
| AB | 97.25% | 99.92% | ⛔ 53.40% | 90.89% |
| BC | 99.47% | 99.94% | ⛔ 66.65% | 87.89% |
| MB | 99.24% | 99.90% | 85.95% | 92.51% |
| NB | n/a | 99.95% | n/a | 93.56% |
| NL | 99.67% | 99.95% | 83.75% | 97.87% |
| NS | 98.66% | 99.84% | 79.51% | 92.89% |
| NT | 100.00% | 100.00% | 100.00% | 100.00% |
| NU | 100.00% | n/a | 100.00% | n/a |
| ON | 96.07% | 99.87% | ⛔ 67.63% | 89.92% |
| PE | 98.91% | 99.11% | ⛔ 58.52% | 93.09% |
| QC | 99.79% | 99.96% | ⛔ 67.58% | 94.36% |
| SK | 99.69% | 99.97% | ⛔ 69.62% | 89.69% |
| YT | 100.00% | 100.00% | 100.00% | 100.00% |

**Read that honestly.** Yes, 20.87% of rural postal codes touch more than one federal riding — five times the urban rate. But the addresses inside them are lopsidedly concentrated in one riding, so a single answer is still right **98.26%** of the time. Rural 6-character lookup is **1.7 percentage points** worse than urban. That is a real gap and it should be disclosed, but it is not a failure mode — it is comparable to the residual error any centroid-based method carries, and part of it is the blockface-centroid floor described in § Candidate open sources.

**The FSA row is the failure mode.** A rural FSA fallback is wrong for **31.5%** of rural addresses federally. AB (53.40%), PE (58.52%), BC (66.65%), QC (67.58%), ON (67.63%) and SK (69.62%) are all near or below two-in-three.

### Provincial districts — materially worse, and measured

Provincial districts are smaller than federal ones, so ambiguity should be worse. ★ Rather than assert that, I measured it: NAR address points inside rural FSAs, point-in-polygon against our own `constituency_boundaries` provincial polygons.

| Probe | Rural FSAs | Span >1 provincial district | Max districts | Dominant-rule accuracy |
|---|---:|---:|---:|---:|
| **NS** (`nova-scotia-electoral-districts-2019`, 55 rows) | 14 | 12 (85.7%) | **7** | ⛔ **57.88%** |
| **MB** (`manitoba-electoral-districts-2018`, 56 rows) | 10 | 10 (**100%**) | **7** | ⛔ **52.82%** |

Same probe at 6-character resolution: **NS 96.34%, MB 97.65%** (rural codes spanning >1 district: 14.2% and 16.8%).

⛔ **A rural FSA fallback for provincial districts is a coin flip.** Manitoba is the clean statement of it: *every single* rural FSA spans multiple provincial districts, up to seven, and picking the dominant one is right 52.82% of the time.

The worst individual cases, NS rural FSAs against provincial districts:

| FSA | Provincial districts spanned | Dominant-rule accuracy | Top three |
|---|---:|---:|---|
| `B0W` | 5 | 32.0% | Clare / Argyle / Shelburne |
| `B0J` | **7** | 32.8% | Chester-St. Margaret's / Lunenburg / Eastern Shore |
| `B0K` | **7** | 34.8% | Pictou West / Pictou East / Cumberland North |
| `B0N` | 5 | 38.3% | Hants West / Colchester-Musquodoboit Valley / Hants East |
| `B0P` | 5 | 45.5% | Kings West / Kings North / Hants West |

And federally, the worst rural FSAs found: SK `S0G` spans 5 ridings across 16,918 addresses at **34.3%** accuracy — worse than picking at random among the top two; SK `S0H` 47.0%; MB `R0H` 49.1%; SK `S0J` 51.2%; NL `A0G` 56.6%.

⚠ Both provincial probes use boundary sets that are themselves stale (NS 2019, MB 2018 — and MB holds 56 rows against 57 seats). That affects *which* district a point maps to, but not the structural finding that rural FSAs span many districts. The direction of the error, if anything, understates the problem: fresher boundaries with more seats subdivide further.

### Verdict

✅ **The open path does degrade gracefully — but only if we never fall back to a bare FSA answer for a rural postcode.** The data is there (100% of rural FSAs, 98.26% federal accuracy at 6-char). The danger is entirely in the fallback design, which is ours to control. See § How the system should behave.

## FSA fallback

Fully specified so the option is on the table, then bounded by the measurements above.

- **Dataset:** 2021 Census Forward Sortation Area Boundary File
- **Catalogue:** **92-179-X** (data), reference guide **92-179-G**
- **Source URL(s):** https://www12.statcan.gc.ca/census-recensement/2021/geo/sip-pis/boundary-limites/index2021-eng.cfm?year=21 ; digital file https://www12.statcan.gc.ca/census-recensement/2021/geo/sip-pis/boundary-limites/files-fichiers/lfsa000b21a_e.zip ; REST https://geo.statcan.gc.ca/geo_wa/rest/services/2021/Cartographic_boundary_files/MapServer/14
- **Format:** zipped shapefile (`lfsa000b21a_e` digital / `lfsa000b21s_e` cartographic); also live via ArcGIS REST and WMS.
- **Size:** `lfsa000b21a_e.zip` = **162,038,215 bytes**. Fetch confirmed working; not staged, because the recommendation does not depend on it.
- **CRS / projection:** **EPSG:3347**, NAD83 Statistics Canada Lambert (`wkid 3347`, `latestWkid 3347`, confirmed from the REST layer's `spatialReference`). ⚠ Needs reprojection to WGS84. The REST endpoint will do it server-side — `&outSR=4326&f=geojson` returns WGS84 GeoJSON directly, verified against `B0J`, which is the cheapest route given there is no GDAL on this host.
- **Attribute schema:** `CFSAUID` (string), `DGUID` (string), `PRUID` (string), `PRNAME` (string), `LANDAREA` (double), `OBJECTID` (OID), `SHAPE` (geometry), `SHAPE_Length` (double), `SHAPE_Area` (double).
- **District ID field:** `CFSAUID` — the 3-character FSA. Would need a new `source_set`; nothing in `constituency_boundaries` corresponds today.
- **Effective date:** 2021 Census geography. ⚠ Per amendment A2, boundary generations take the **legal in-force date** — but FSAs have no legal in-force date. They are a Canada Post operational geography snapshotted by StatCan, not an instrument made under statute; there is no SI to cite. **Use the metadata date, `2022-09-21` (release date) — `needs confirmation` is not applicable, the legal date does not exist.** Flagging explicitly so the A2 ruling is not read as unapplied.
- **District count:** **1,643** polygons, retrieved and counted. NL 35, PE 7, NS 77, NB 110, QC 414, ON 520, MB 74, SK 52, AB 154, BC 191, YT 3, NT 3, NU 3. **181 (11.0%) rural.**
- ⚠ **One polygon per row?** Not verified for this file. Per amendment A4, count DISTINCT `CFSAUID`, not records, on load — an FSA with detached islands may well be multiple rows. **UNTESTED — probe during build.**
- **Licence:** Statistics Canada Open Licence.
- **Difficulty (1–5):** **1** via the REST service; **2** via the zip, because of the trap below.
- ⚠ **Trap:** `curl -sSL` on the zip URL enters a **redirect loop and dies at 50 hops**. The endpoint sets a cookie and redirects to itself expecting it back. `curl -c jar -b jar` retrieves it correctly (`http=200`, 162,038,215 bytes). Do not conclude the file is gone.

**Quantified degradation** — the numbers are in § The rural question; the summary is:

| | Federal | Provincial (NS / MB probes) |
|---|---:|---:|
| FSA fallback, urban | 91.21% | not measured |
| FSA fallback, **rural** | ⛔ **68.46%** | ⛔ **57.88% / 52.82%** |
| 6-char, urban | 99.91% | not measured |
| 6-char, **rural** | ✅ **98.26%** | ✅ **96.34% / 97.65%** |

Against the boundary brief's own standard — *"a stale boundary is WORSE than a missing one: the lookup returns a confident wrong riding"* — a silent FSA answer is a confident-wrong-answer machine: **~1 in 11 urban** and **~1 in 3 rural** federally, and **~1 in 2 rural** provincially.

**Verdict:** ⏸️ Keep the FSA file, but only to answer *"the user typed three characters"* and to bound the answer when a 6-character code is unknown — and in both cases **surface the ambiguity rather than picking a winner**. ⛔ Never adopt it as the primary geocode, and ⛔ never let it silently return one district for a rural FSA.

## Open North's own concordances

Priority 4 asked whether mirroring Open North's postal concordance is the fastest fix. **It is not an option at all, for a simpler reason than licensing: the data is not published.**

- **Repository:** https://github.com/opennorth/represent-canada-data
- **What the README says:** *"All datasets are from government sources, with one exception: the postal code<sup>OM</sup> dataset in the `postcodes/fed` directory is from Geocoder.ca."*
- **★ What is actually in the repo:** there is **no `postcodes/` directory**. The full recursive tree (809 paths, untruncated, via the GitHub trees API) has top-level entries `boundaries/`, `concordances/`, `docker/`, `manifest`, `constants.py`, `country-ca.csv`, `tasks.py` and packaging files. Nothing matching `postcode` anywhere. The README documents a path that does not exist in the public tree — the maintenance instructions reference `--base=path/to/private/data`, so the postal concordance lives in a **private** companion repository.
- **Therefore:** the transitivity question is moot. There is nothing to mirror. ⛔ Closed.
- **On transitivity anyway, for the record:** the repo carries 86 per-directory `LICENSE.txt` files, and the top-level one is explicit that permission is theirs and not necessarily ours — *"Open North has permission to redistribute all shapefiles in this repository… In some cases, you will not have permission to redistribute the shapefile."* The top-level file is otherwise entirely GeoNB terms, including *"The Licensee shall license all individuals (or companies) who obtain data or derivative products from the Licensee… the same terms and conditions"* — a flow-down clause. So even for the boundary files that *are* published, per-directory licence review is mandatory before we redistribute any of them. That is a live consideration for the other boundary agents, not for this dossier.
- **★ One genuinely useful public concordance does exist** in the repo, and it is not postal-to-federal. It gets its own section below.

## ★ Elections Québec postal → provincial-district concordance

The one open-licence postal→district file found anywhere in this research. Worth its own section because it is a **template**, not a one-off.

- **Source URL(s):** https://www.electionsquebec.qc.ca/francais/provincial/carte-electorale/entites-administratives-liees-a-un-code-postal.php ; mirrored at https://raw.githubusercontent.com/opennorth/represent-canada-data/master/concordances/ocd-division/country:ca/province:qc/out.csv
- **Format:** headerless 2-column CSV, 2,361,271 bytes. Rows are `postalcode,district_number` — e.g. `G0A1A0,714`, `G0A1E0,760`, `G0A1H0,760`.
- **Publisher:** Élections Québec — a government source, satisfying the primary-source rule.
- **Licence:** Élections Québec *"Conditions d'utilisation de notre site Web"*. The `LICENSE.txt` in that directory reads verbatim: *"Attribution: This data is provided by the Gouvernement du Québec (http://www.electionsquebec.qc.ca), reproduced according to the terms of the 'Conditions d'utilisation de notre site Web'… Copyright in the work belongs to the Gouvernement du Québec."* ✅ Redistributable with attribution.
- **Difficulty (1–5):** **1** — a flat CSV behind a stable raw URL.

**Use it as a cross-check, not as a data source.** Per amendment A3 and the coordinator's ruling: our lookup is point-in-polygon against authoritative polygons, and a polygon strictly beats a concordance. But an *independent* postal→district file is exactly what you want to validate a PIP implementation. Concretely: derive NAR centroids for every QC postal code, PIP them against `quebec-electoral-districts-2017` (124 rows held), and diff against this file. Disagreements are either a bug in our PIP, a stale polygon, or a genuinely boundary-straddling postal code — all three are things we want to know, and there is no other way to find them.

⚠ The file's district numbers are Élections Québec's own codes and will need mapping to our `constituency_id`. Vintage is also unstated in the file — the `update.sh` alongside it references `quebec-electoral-districts-2017`, matching what we hold, but **needs confirmation** against the current QC map before the diff is trusted.

★ **This is a per-jurisdiction pattern worth checking everywhere.** Élections Québec publishes it under *"entités administratives liées à un code postal"*. If other provincial election agencies publish an equivalent, each one is a free correctness check on that province's PIP. Raised for the other jurisdiction agents in § Research-handoff items.

## Recommendation

Ranked. The headline, now measured rather than estimated: **the open-licence-only path reaches 92.5% of national postal-code coverage — 856,929 of ~926,425 active codes — at accuracy equal to or better than the incumbent, and it cannot go down.** There is a residual shortfall and it is quantified below. It does not change the recommendation.

### 1. ✅ Adopt the StatCan National Address Register as the primary geocode

Join `Addresses/Address_<PR>.csv` to `Locations/Location_<PR>.csv` on `LOC_GUID`, group by `MAIL_POSTAL_CODE`, average the WGS84 coordinates. The archive is staged at `data/boundaries/_geocoding/nar/202606.zip`.

| | Open North (incumbent) | NAR (proposed) |
|---|---|---|
| Availability | ⛔ **down now** — cert expired 2026-08-07, origin 502. Only the 8 cached codes resolve | ✅ local table, no outbound call, cannot fail at request time |
| Latency | network round trip; up to **3** sequential calls for a cold FSA | single indexed local lookup |
| Coverage | ~926,425 codes, *when reachable* | **856,929 — 92.5%**, always reachable |
| Precision | street-level centroid | mean of all civic address points in the code (median 4–6 points; NS mean 18.6). ⚠ blockface-centroid floor |
| Federal accuracy | our own PIP | our own PIP, **plus** `FED_CODE` on the 2023 order as a cross-check. 99.91% urban / 98.26% rural |
| Licence | Geocoder.ca-derived; our redistribution rights never established | **Statistics Canada Open Licence** — *"use, reproduce, publish, freely distribute, or sell"* + sublicence |
| Refresh | opaque | semi-annual, predictable, ours to schedule |

**The shortfall, stated plainly:** **69,496 active postal codes (7.5%) will not be in the derived table.** Two causes, both understood: ~3% of all codes are PO-box or service-route only and have no civic address for a civic register to carry (StatCan 92F0138), and the remainder is currency lag against Canada Post's 500–2,500 new codes per month. Against the ~97% structural ceiling, we capture **~95% of everything this method can reach**.

★ **And the comparison is not 92.5% versus 100%.** The incumbent's *effective* coverage today is 8 postal codes. Even fully healthy, it was a network dependency with a demonstrated 10+ day outage. Trading 7.5% of coverage — which degrades to a bounded, disclosed answer, not an error — for the removal of a single point of failure is not a close call.

### 2. ✅ Keep the 2021 FSA Boundary File — bounded to two jobs

Load `lfsa000b21a_e` (1,643 polygons, EPSG:3347) as its own `source_set`, for (a) 3-character user input and (b) bounding the answer for 6-character codes we lack. ⛔ **Never as a silent single-district answer** — 68.46% federal / ~53–58% provincial for rural FSAs. See § How the system should behave.

### 3. ✅ Ingest the Elections Québec concordance as a PIP cross-check

Not as a data source. See its section above.

### 4. ⏸️ Hold OpenAddresses and OSM in reserve

At 92.5% coverage with a 97% ceiling, the marginal gain no longer justifies 99 municipal licences or ODbL share-alike. ⛔ Effectively closed unless the residual turns out to concentrate somewhere that matters.

### 5. ⛔ Do not pursue PCCF, PCFRF, or paid Geocoder.ca

Closed with citations. The free Geocoder.ca non-profit tier remains a live operator decision, but at 92.5% it is now an optimisation, not a rescue.

## How the system should behave

Requested by the coordinator, and downstream of the numbers above. The governing principle, in their words: *"I would rather ship a lookup that says 'this rural postcode spans 3 ridings, here are all 3' than one that silently picks the wrong one."* The data supports that instinct exactly — the danger in this design is never the coverage, it is a confident single answer where the input does not justify one.

**Design the response shape around resolution, not around success/failure.** Four cases:

1. **6-char known, all address points in one district** — 99.7% of lookups. Return the single district, `confidence: exact`.
2. **6-char known, points span districts** (0.23% urban / 20.87% rural) — return the **dominant** district *and* the others, with address-point shares: `{district: "Kings—Hants", share: 0.78}, {district: "Acadie—Annapolis", share: 0.22}`. ★ We can compute those shares exactly from the NAR point counts, so this costs nothing at query time. `confidence: dominant`.
3. **6-char unknown, FSA known** — ⛔ **never collapse to one district.** Return **all** districts intersecting the FSA with their shares, plus an explicit note that resolution is FSA-level. For a rural FSA this is the difference between a 68% guess and an honest set of 3–7 candidates. `confidence: fsa_only`.
4. **Neither known** — a genuine 404, and for a *new* postcode say so specifically ("this may be newer than our data, last refreshed <date>") rather than "not found", because per § Refresh cadence that is the likely cause.

**Three supporting rules:**

- ⚠ **Never let case 3 look like case 1 on the wire.** If the shape is identical and only a field differs, every client that ignores the field silently ships the 68% answer. Prefer `districts: []` always-plural over a nullable `district`, so the ambiguity is structural rather than advisory.
- ★ **Invert the cache.** `postcode_cache` at 8 rows means the SWR fallback in `postcode.ts` is decorative. Once a local table exists, the outbound call must come **out of the hot path** — local table first, upstream only for codes we do not hold, never on the critical path. Otherwise the next Open North outage reproduces today's incident exactly.
- **Surface the vintage.** Return the NAR release (`202606`) alongside the answer, the way `/postcodes/:postcode` already returns `source` and `fetched_at`. It makes staleness diagnosable instead of invisible.

⚠ Note this is a *recommendation on shape*, not a build instruction — the operator decides. But the numbers make one thing non-negotiable: **whatever ships must not return a single silent district for a rural FSA.**

## Measured user impact

Full write-up in [`impact.md`](./impact.md). Summarised here because it is the other half of the same user's experience: this dossier fixes *getting a coordinate*, that one measures *what the coordinate resolves to*.

Using the same NAR register as an address-weighted sampling frame (16,157,303 addresses; 32,500 sampled, 2,500 per jurisdiction):

| Measure | Rate |
|---|---:|
| Provincial — **no answer** | ⛔ **9.15%** of Canadian addresses |
| Provincial — wrong answer | ⚠ 2.12% (over the 6 jurisdictions with authoritative geometry, 62.3% of addresses) |
| Provincial — any error, those 6 | ⛔ **12.61%** |
| Federal — any error | ✅ 1.79% |

★ **BC alone contributes 6.05 of the 9.15 national points** — fixing one province cuts the national no-answer rate to 3.10%. ★ **NT holds a perfect 19-of-19 district count and still misinforms 14.3% of its addresses**, concentrated in Yellowknife, because its whole error budget is misassignment rather than absence.

**These two error sources are independent and compound on the same lookup.** The geocode contributes 0.09% (urban) to 1.74% (rural) at 6-character resolution; the polygon contributes the rates above. A rural BC address is poorly served from both directions at once — which is the argument for fixing the geocode and the boundaries as one piece of work, not two.

## Refresh cadence

Canada Post creates and retires codes continuously, so staleness is the standing risk of any local table.

**Observed NAR release history** (from the archive listing at `462600022022001-eng.htm`, sizes retrieved by HEAD):

| Release | Archive | Bytes |
|---|---|---:|
| 2022 | `2022.zip` | 1,669,597,409 |
| 2023 | `2023.zip` | 1,862,619,570 |
| 2024 | `2024.zip` | 1,883,436,717 |
| Dec 2024 | `202412.zip` | 1,933,364,566 |
| Jul 2025 | `202507.zip` | 1,995,579,320 |
| Dec 2025 | `202512.zip` | 2,015,170,163 |
| **Jun 2026** | **`202606.zip`** | **1,665,944,959** |

**Pattern:** annual 2022–2024, then **semi-annual** from December 2024 (Dec / Jun–Jul). Drift between refreshes is therefore ~6 months.

**★ How much drift is that, quantified?** Canada Post's own creation rate is documented by StatCan (92F0138, *How Postal Codes Map to Geographic Areas*): the Address Lookup File carries *"about 500 to 2500 new postal codes introduced or 'birthed' each month."* Over a six-month release cycle that is **3,000–15,000 new codes**, i.e. **0.35%–1.7%** of the 856,929 we would hold. At the end of a cycle, therefore, somewhere between 1 in 290 and 1 in 60 lookups is for a code minted since our last refresh.

Because new codes track new construction, that drift lands disproportionately on new subdivisions and infill — precisely the people who have recently moved and are most likely to be looking up a riding they do not yet know. ⚠ Those users must get an explicit "this postcode may be newer than our data" message and an FSA-level answer with its ambiguity shown, never a bare 404 and never a silent single-riding guess. See § How the system should behave.

⚠ **The June 2026 archive is 349 MB smaller than December 2025**, reversing four consecutive increases. That is a 17% drop, not noise, and it is unexplained — it could be a methodology or compression change, or it could be a content regression. **Compare distinct postal-code counts between `202512.zip` and `202606.zip` before adopting `202606`**, and be prepared to prefer the December file. Flagged rather than resolved: `202606` is now staged and the server honours `Range`, so the comparison is a distinct-postal-code count on each — cheap, but it needs the December archive fetched too. See § Research-handoff items.

**Refresh mechanism:** the URL pattern `.../2022001/<YYYYMM>.zip` is predictable, so a scanner command can HEAD the next expected release and fall back to listing `462600022022001-eng.htm`. Idempotent per CLAUDE.md convention #7; suggested shape `ingest-nar-postcodes` split into `fetch-nar-archive` / `parse-nar-postcodes`.

**FSA boundary file cadence:** decennial, tied to the census. The 2021 file (released 2022-09-21) stands until the 2026 Census geography products publish — ⚠ which is imminent, and the 2026 FSA file should be preferred as soon as it exists.

## Reconciliation with `constituency_boundaries`

This dossier does not add boundary rows, but the NAR's `FED_CODE` reconciles cleanly and that is worth recording for the build phase.

- **What we hold:** 1,949 rows total; `source_set = 'federal-electoral-districts'` has **342** rows (343 seats — one missing, per the boundary brief).
- **Our key shape:** `constituency_id` = `federal-electoral-districts-2023-representation-order/10001` (name `Avalon`), `.../10002` (`Cape Spear`), `.../10003`, `.../10004`.
- **★ The suffix is the SGC federal electoral district code — byte-identical to NAR `FED_CODE`.** NAR gives `13001 Acadie—Bathurst`, `12006 Halifax`; our IDs carry the same 5-digit codes. **No re-key needed.** The join is `split_part(constituency_id, '/', 2) = FED_CODE`.
- **Both sides are on the 2023 Representation Order** — confirmed by district *names*, not assumed from the ID format.
- **★ This makes the NAR a free audit of our federal boundary set.** Loading `FED_CODE` alongside the derived centroids lets us PIP each centroid against our own polygons and diff the result against StatCan's answer. Disagreements localise our staleness precisely — including, very likely, identifying the one missing federal district.
- **Postcode cache:** `public.postcode_cache` (migration `0055`) has `source` defaulting to `'opennorth'`, so a NAR-sourced row can coexist by writing `source = 'nar-202606'`. ⚠ But the table is keyed and TTL'd for a *cache*; a derived national table is reference data with different semantics and probably wants its own table rather than overloading this one. Design call for the build phase.

## Research-handoff items

- **Confirm the NAR licence read before we build on it.** This is the load-bearing legal claim in the dossier. The user guide says the mailing address *"follows Canada Post's addressing guidelines"* — **guidelines**, i.e. formatting conventions — and that the product is *"made available for free under the Statistics Canada Open Licence"*. There is no Canada Post distribution carve-out and no end-use licence requirement, in explicit contrast to the PCCF and PCFRF catalogue pages which carry both. My reading is that NAR postal codes are StatCan-derived and openly licensed. **Does the operator want that confirmed in writing by StatCan before we redistribute derived centroids?** Contact from the user guide: `statcan.statisticalregistersinfo-inforegistresstatistiques.statcan@statcan.gc.ca`. Low risk, cheap to ask, permanently closes the last open question.
- **⚠ Explain the `202512` → `202606` size regression before adopting `202606`.** The June 2026 archive is **349 MB smaller** than December 2025, reversing four consecutive increases — a 17% drop, not noise. It could be a methodology or compression change, or a content regression. Both archives are now cheap to compare (`202512.zip` is 2,015,170,163 bytes and the server honours `Range`); the check is a distinct-postal-code count on each. **This is the one item that could change the recommended release**, though not the recommended source.
- **★ Ask the other jurisdiction agents to look for a local Élections Québec equivalent.** QC publishes an open postal→provincial-district file under *"entités administratives liées à un code postal"*. Every province that publishes one gives us a free independent correctness check on that province's point-in-polygon output. Cheap to check, high value, and it needs the per-jurisdiction agents rather than me.
- **Decide on the Geocoder.ca free non-profit tier — requires a human.** 926,425 codes under CC-BY 2.5 Canada, free to non-profits by email via https://geocoder.ca/?freedata=1. ⛔ I did not and will not request it: it requires identifying the project, asserting non-profit status, and accepting terms, which the standing instructions forbid. **Two questions: does CPD qualify as non-profit for their purposes, and is CC-BY 2.5 attribution acceptable on our output?** ⏸️ Downgraded in urgency — at 92.5% coverage this is an optimisation worth ~7.5%, not a rescue. Note the provenance trade: it is crowdsourced rather than governmental.
- **Provincial-district ambiguity is measured only for NS and MB**, and both probes ran against boundary sets that are themselves stale (NS 2019; MB 2018, 56 rows against 57 seats). The structural finding — rural FSAs span many provincial districts — is robust, but the exact percentages will move once `constituency_boundaries` is refreshed. Re-run then; the query is in this dossier's history and takes minutes.
- **Nunavut under-coverage is accepted, not fixed** — 11 postal codes for the territory. Consequence-free federally (NU is one riding). It becomes a real gap only if we add NU's 22 territorial districts, which we hold **zero** boundaries for.
- **FSA polygon-per-row not verified.** Per amendment A4, count DISTINCT `CFSAUID` on load rather than records; an FSA with detached islands may be multiple rows. Only matters if the FSA file is actually ingested.

## Status

> ⚠ **Reconciled 2026-09-01.** The checkboxes below are the **research phase's** record
> (closed 2026-08-18) and several were overtaken by the build — migrations `0064`–`0121`,
> merged to `main` 2026-08-28. An unticked box here is **not** evidence that something is
> still outstanding.
>
> **Live counts: [`PROGRESS.md`](./PROGRESS.md)** (generated by `boundary-progress`).
> **What actually landed:** the migration headers, which are the accurate record.
> This file's job is the *reasoning* — sources, licences, traps, vintage evidence.

- [x] Incumbent dependency traced and current failure diagnosed (2026-08-18) — **cert expired 2026-08-07 + origin 502; 8 cached codes work, all others 503**
- [x] Restricted sources closed with citations — PCCF (92-154-X), PCFRF (92-178-X, $892/yr, 2013 Order)
- [x] Open candidate sources enumerated and licence-checked
- [x] ODA evaluated and **rejected on measurement** — 0–15.4% postal-code fill, 7 contributing municipalities
- [x] OpenAddresses / OSM / provincial-municipal evaluated — deferred, ceilings quantified
- [x] NAR located, schema documented, licence read, 2023 Representation Order confirmed
- [x] NAR archive **staged** — `data/boundaries/_geocoding/nar/202606.zip`, 1,665,944,959 bytes, sha256 recorded
- [x] **Exact national postal-code count computed** — 856,929 (92.5% of active), full register, 17,362,476 rows, 99.67% fill
- [x] Structural ceiling established from primary source — ~97% (StatCan 92F0138)
- [x] Blockface-centroid positional basis recorded
- [x] **Rural coverage question answered** — 100% of rural FSAs present; NB zero-rural confirmed as a real Canada Post fact, not a gap
- [x] **Rural accuracy quantified nationally** — 6-char rural **98.26%** federal vs urban 99.91%
- [x] **Rural FSA fallback quantified and rejected** — **68.46%** federal, worst FSA 34.3%
- [x] **Provincial-district ambiguity measured** (NS + MB PIP probes) — rural FSA **57.88% / 52.82%**; rural 6-char 96.34% / 97.65%
- [x] Systematic-absence check across ON, SK, NL, NB (+9 more) — no systematic rural absence anywhere
- [x] FSA fallback fully specified — 92-179-X, 1,643 polygons, EPSG:3347
- [x] Refresh cadence established — semi-annual; drift 500–2,500 new codes/month = 0.35–1.7% per cycle
- [x] Open North concordance question closed — **no postal data in the public repo at all**
- [x] Elections Québec concordance documented as a PIP cross-check + per-jurisdiction pattern
- [x] `FED_CODE` ↔ `constituency_id` reconciliation confirmed — no re-key required
- [x] Response-shape recommendation delivered (§ How the system should behave)
- [x] Matrix fragment written to `_matrix/geocoding.md` per amendment A1
- [x] Address-weighted user-impact measurement delivered — [`impact.md`](./impact.md), 9.15% provincial no-answer
- [ ] `202512` vs `202606` size-regression explained — **open; could change the recommended release**
- [ ] NAR licence confirmed in writing by StatCan — **operator decision, not blocking**
- [ ] Geocoder.ca free non-profit tier — **blocked: requires a human to request and accept CC-BY 2.5**
- [ ] Provincial ambiguity re-measured against refreshed boundaries — **deferred to post-refresh**

---

**Agent note (standing instruction 8).** No page fetched during this research contained text addressed to an AI agent. No licence was accepted, no account registered, no form submitted, and no click-through agreement passed. Two gated resources were identified and left untouched: the Geocoder.ca non-profit data request and the Canada Post Postal Code End-use licence. The StatCan cookie-jar redirect on `lfsa000b21a_e.zip` is an ordinary session cookie, not a licence gate — no terms were presented or accepted.
