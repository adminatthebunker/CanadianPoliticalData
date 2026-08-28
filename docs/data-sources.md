# Data Sources

## Politicians + infrastructure

| Source | Used for | License |
|--------|----------|---------|
| ⛔ ~~[Open North Represent](https://represent.opennorth.ca/)~~ | **RETIRED 2026-08-27.** Was MPs, MLAs, councils + all constituency boundaries. Ingestion removed; `trg_block_mirror_boundary` refuses its signature at the DB. Existing `opennorth:`-sourced roster rows remain and are FROZEN — see below | was OGL-Canada |
| Elections Canada + the 13 provincial/territorial chief electoral officers | Federal and provincial/territorial electoral district geometry | ⚠ **No single licence.** Nine-plus different sets of terms across 14 jurisdictions, several with none stated. Per-source terms in `research/boundaries/` and, publicly, `mkdocs/docs/developers/licences.md` |
| Individual municipalities (open-data portals, ArcGIS orgs, by-law PDFs) | Municipal ward geometry | Per-municipality; recorded verbatim in each `data/boundaries/*/PROVENANCE.md`. Two carry explicit prohibitions (Clarington non-commercial, Vaughan prior-written-permission) and are loaded under the standing "licence recorded, never a gate" rule |
| [MAMH Québec](https://donneesouvertes.affmunqc.net/) | Québec municipal roster (`mamh-qc:`) — the 2025-11-02 general election result | CC-BY 4.0 |
| [AMO Ontario](https://elections2026.amo.on.ca/) | Ontario municipal roster (`amo-on:`) — per-cycle election results | Unstated; unauthenticated public API |
| [MaxMind GeoLite2](https://www.maxmind.com/en/geolite2/signup) | IP → country/city/lat/lng/ASN | GeoLite2 EULA (free with attribution) |
| [Thedurancode/change](https://github.com/Thedurancode/change) | Website content change detection | Per upstream |
| [Uptime Kuma](https://uptimekuma.org/) | Uptime monitoring | MIT |
| Hand-curated | Referendum organizations + their websites | n/a (public web) |

## Provincial bills + stage events (10 of 13 jurisdictions live)

| Jurisdiction | Primary source | Format | License |
|---|---|---|---|
| Nova Scotia | `data.novascotia.ca/resource/iz5x-dzyf.json` (Socrata) + `nslegislature.ca/legislative-business/bills-statutes/rss` | Socrata API + RSS + HTML | Open Government Licence — Nova Scotia |
| Ontario | `ola.org/en/legislative-business/bills/...?_format=json` (Drupal REST serializer) | JSON | Queen's Printer for Ontario |
| British Columbia | `lims.leg.bc.ca/graphql` + `lims.leg.bc.ca/pdms/bills/progress-of-bills/{session}` | GraphQL + JSON | BC Legislative Assembly |
| Quebec | `donneesquebec.ca/.../projets-de-loi.csv` + `assnat.qc.ca/fr/rss/SyndicationRSS-210.html` + detail HTML | CSV + RSS + HTML | CC-BY-NC-4.0 |
| Alberta | `assembly.ab.ca/assembly-business/assembly-dashboard?legl={L}&session={S}` | Server-rendered HTML (one-page dashboard) | Crown copyright (Alberta) |
| New Brunswick | `legnb.ca/en/legislation/bills/{legl}/{session}` + detail pages | HTML (list + detail) | Open Government Licence — New Brunswick |
| Newfoundland & Labrador | `assembly.nl.ca/HouseBusiness/Bills/ga{GA}session{S}/` | HTML table | Crown copyright (NL) |
| Northwest Territories | `ntassembly.ca/documents-proceedings/bills/{slug}` | Drupal 9 HTML | Crown copyright (NWT) |
| Nunavut | `assembly.nu.ca/bills-and-legislation` | Drupal 9 HTML view | Crown copyright (Nunavut) |
| Manitoba | `web2.gov.mb.ca/bills/{P}-{S}/index.php` + `billstatus.pdf` | HTML (roster) + PDF (stage events via Poppler) | Crown copyright (Manitoba) |

**Deferred:** Saskatchewan is PDF-only (bill status documents), awaiting the same PDF-extraction investment that powered MB. PEI is behind Radware ShieldSquare; Yukon behind Cloudflare Bot Management — both awaiting a Playwright-based browser automation track.

Per-jurisdiction probe history, endpoint findings, and module pointers live in [`research/`](research/) — one self-contained dossier per jurisdiction (see [`research/overview.md`](research/overview.md) for the shared schema log + probe hierarchy).

## Attribution required

The frontend footer credits MaxMind. For Quebec bills data, CC-BY-NC-4.0
requires attribution to Assemblée nationale du Québec and restricts commercial
use.

⚠ **The footer's Open North credit is now historical, not current.** Boundaries
no longer come from there. Whether to keep the credit for the frozen
`opennorth:`-sourced roster rows that remain is an open call — it is honest
while those rows are served and misleading once they are all replaced.

⛔ **There is no blanket boundary licence to attribute.** Fourteen agencies,
at least nine sets of terms, several unstated. If you redistribute geometry,
check the specific source: the per-row `licence` object and `Link: rel="license"`
header on the public API, `mkdocs/docs/developers/licences.md`, or the
`PROVENANCE.md` beside each staged file.

## Roster freeze

⚠ **894 sitting municipal officials still carry `opennorth:` provenance**, plus
1,057 federal/provincial. Frozen is **not** the same as wrong: the mirror's rows
were written 2026-04-13 → 06-07 and captured every election up to its
retirement, so the data is broadly accurate today. It goes wrong at each
province's next municipal election. Québec (`mamh-qc:`) and Ontario (`amo-on:`)
are the only provinces with a replacement ingester so far.
`check-boundary-coverage` reports the freeze per province.

## Refreshing GeoLite2

MaxMind ships database updates ~weekly. Use their `geoipupdate` tool or download manually:

```bash
# After downloading via your MaxMind account
mv ~/Downloads/GeoLite2-City.mmdb data/
mv ~/Downloads/GeoLite2-ASN.mmdb  data/
sovpro restart   # scanner reads the file at start
```

If the DBs are missing, the scanner still runs — `ip_country`/`ip_city`/`ip_asn` will simply be NULL, and most rows will end up in tier 6 (Unknown). That's safe but not useful.
