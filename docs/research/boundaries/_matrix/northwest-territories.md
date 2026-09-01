### licence
| Jurisdiction | Rows held | Source | Licence | Internal use | Redistribution | Notes |
|---|---:|---|---|---|---|---|
| Northwest Territories | 19 | NWT Centre for Geomatics (`geomatics.gov.nt.ca`) + ArcGIS REST (`sandbox.` host only) | Open Government Licence – Northwest Territories | ✅ Yes — no gate, no account, bare GET | ✅ **Yes, expressly** | Licence text captured verbatim: *"licence mondiale, libre de redevances, perpétuelle et non exclusive… y compris à des fins commerciales"*, with *distribuer* named outright. Attribution required — publisher statement is `Elections NWT, NWTCG`. ⚠ GNWT's own `/en/` licence URL serves the **French** text. Exemptions cover personal information / ATIPP-exempt records — not engaged by boundary polygons. |

### coverage
| Jurisdiction | Rows held | Seats | Authoritative count | Vintage held | Current vintage | Delta |
|---|---:|---:|---:|---|---|---|
| Northwest Territories | 19 | 19 | 19 | 2013/14 order | 2013/14 order — **same** (S.N.W.T. 2014 c. 21, in force 2015-10-25 on dissolution of the 17th Assembly) | ✅ **Vintage correct, IDs 19/19 (100%), no re-key.** Confirmed against the statute: LAECA s. 2(1) reads *"There are 19 electoral districts as named and described in Schedule A."* ⛔ **But geometry is materially wrong for 5 of 19** — held `Great Slave` missing 69% of its area, `Frame Lake` 2.0× oversized (only 48% of it is really Frame Lake), `Hay River North` missing 30%, `Hay River South` 3.6× oversized, `Nunakput` 2.0× oversized. Two adjacent pairs with complementary over/under errors = misplaced shared boundaries = **live wrong-riding answers in Yellowknife and Hay River**. Fix is an in-place geometry update; no FK moves. ⚠ 2025–26 Commission recommended **19→22** (final report tabled 2026-02-27); not enacted, no bill before the House — but expect supersession before the 2027-10-05 election. |

### a6
| Jurisdiction | Current prefix | A6-compliant target | Status |
|---|---|---|---|
| Northwest Territories | `northwest-territories-electoral-districts-2013/` | `northwest-territories-electoral-districts/` | ⛔ **Violation** — year in prefix. Not applied. Cheap case: 19 rows, one `UPDATE`, only one generation so no collision hazard. ⓘ A6 also dissolves the `-2013`-vs-`-2014` naming question (statute is S.N.W.T. **2014** c. 21) — with no year in the prefix the discrepancy disappears. |
