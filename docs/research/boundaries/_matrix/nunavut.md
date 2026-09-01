### licence

| Jurisdiction | Rows held | Source | Licence | Internal use | Redistribution | Notes |
|---|---:|---|---|---|---|---|
| Nunavut (territorial) | 0 | Elections Nunavut — https://www.elections.nu.ca/sites/default/files/documents/EN_FUTURE_NU_Constituencies.zip | Open Government Licence – Elections Nunavut v1.0 | ✅ Yes | ✅ Yes | No click-through, no registration, no WAF — plain HTTPS GET. Licence text is not a web page; it ships as `readme <basename>.pdf` **inside** each zip (EN + Inuktitut syllabics). Worldwide, royalty-free, perpetual, commercial use permitted. **Attribution is a hard condition** — non-compliance terminates the grant automatically: *"Contains information licensed under the Open Government Licence – Elections Nunavut."* Exemptions: personal information, third-party rights, agency crests/logos. Governed by the laws of Nunavut. Licence is versioned and pinned by access date — see `data/boundaries/nunavut/PROVENANCE.md`. Same OGL covers the prior generation. Commission reports + PDF map books are plain Crown copyright — staged as evidence, **do not redistribute those**. |

### coverage

| Jurisdiction | Rows held | Seats | Authoritative count | Vintage held | Current vintage | Delta |
|---|---:|---:|---:|---|---|---|
| Nunavut (territorial) | 0 | 22 | 22 | — none, absent entirely (Open North never published a NU set) | Bill 48, *An Act Respecting the Constituencies of Nunavut* — assented May 2024, **legally in force 2025-09-22** (*Nunavut Elections Act* s.29(2)) | **22 districts missing.** Not stale — absent. All 22 NU rows in `politicians` also carry `constituency_id = NULL`, so postcode lookup returns nothing for the territorial layer. Closable in full: authoritative shapefiles secured for **both** generations (current 2025-09-22→; prior 2013-09-23→2025-09-21), 22/22 case-insensitive name match against our roster, zero re-key hazard. |
