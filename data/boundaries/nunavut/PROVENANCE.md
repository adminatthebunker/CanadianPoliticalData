# Nunavut — boundary staging provenance

All files retrieved from Elections Nunavut (`www.elections.nu.ca`) over plain HTTPS with a
browser `User-Agent`. No licence click-through, no registration, no form submission was
required or performed. Total staged: 11.5 MB.

| File | Source URL | Retrieved (UTC) | Bytes | sha256 | Licence |
|---|---|---|---:|---|---|
| `current/EN_FUTURE_NU_Constituencies.zip` | https://www.elections.nu.ca/sites/default/files/documents/EN_FUTURE_NU_Constituencies.zip | 2026-08-18T00:47Z | 209842 | `042209c5a2171f71723febcd8d75e1c429f6be87010a1fef34fbd35435d67075` | Open Government Licence – Elections Nunavut v1.0 |
| `current/Future-Constituency-Boundaries-After-Sept-21-2025-v1.pdf` | https://www.elections.nu.ca/sites/default/files/documents/Future-Constituency-Boundaries-After-Sept-21-2025-v1.pdf | 2026-08-18T00:57Z | 6442979 | Crown copyright, Elections Nunavut |
| `current/2023_NEBC_Report_english.pdf` | https://www.elections.nu.ca/sites/default/files/documents/2023%20NEBC%20Report_english.pdf | 2026-08-18T00:50Z | 4395545 | Crown copyright, Elections Nunavut |
| `prior/EN_PRESENT_2013_Present_NU_Constituencies.zip` | https://www.elections.nu.ca/sites/default/files/documents/EN_PRESENT_2013_Present_NU_Constituencies.zip | 2026-08-18T00:57Z | 205983 | Open Government Licence – Elections Nunavut v1.0 |
| `prior/2021_11x17_All_Constituencies.pdf` | https://www.elections.nu.ca/sites/default/files/documents/2021_11x17_All_Constituencies.pdf | 2026-08-18T00:50Z | 507323 | Crown copyright, Elections Nunavut |

## Notes on retrieval

- The current-generation zip is reachable from the Drupal node
  `https://www.elections.nu.ca/en/document/maps-constituencies-gis-2025`, which is itself
  linked from the taxonomy page `https://www.elections.nu.ca/en/taxonomy/term/247`
  ("Maps of Constituencies - GIS shape file"). The node's download button is
  `/en/file-download/download/public/2034`, a 302 to the `/sites/default/files/documents/`
  path recorded above. Either URL works; the direct path is recorded because it is stable
  against Drupal file-id churn.
- **The prior-generation zip is an orphaned file.** It is live at the origin (HTTP 200,
  `Last-Modified: Fri, 22 Nov 2024 14:40:37 GMT`) but is no longer linked from any page on
  `elections.nu.ca` — the documents view lists only the current-generation zip. Its
  existence was recovered from the Internet Archive CDX index
  (`web.archive.org/cdx/search/cdx?url=elections.nu.ca/sites/default/files/*`), then the
  **file itself was fetched from the Elections Nunavut origin, not from the archive**. The
  bytes staged here are the primary-source bytes.
- The licence text for both zips is a `readme <basename>.pdf` bundled *inside* the archive
  (English + Inuktitut syllabics). Quoted verbatim in the dossier.

## Licence — verbatim attribution clause

From `readme EN_FUTURE_NU_Constituencies.pdf`, bundled in the current-generation zip:

> **Open Government Licence – Elections Nunavut**
>
> You must, where you do any of the above:
>
> - Acknowledge the source of the Information by including any attribution statement
>   specified by the Information Provider(s) and, where possible, provide a link to this
>   licence.
> - If the Information Provider does not provide a specific attribution statement, or if
>   you are using Information from several information providers and multiple attributions
>   are not practical for your product or application, you must use the following
>   attribution statement:
>
> **Contains information licensed under the Open Government Licence – Elections Nunavut.**

The same licence text appears in `readme EN_PRESENT_2013_Present_NU_Constituencies.pdf`.
