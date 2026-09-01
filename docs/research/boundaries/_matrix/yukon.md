### licence
| Jurisdiction | Rows held | Source | Licence | Internal use | Redistribution | Notes |
|---|---:|---|---|---|---|---|
| Yukon | 19 | GeoYukon (`map-data.service.yukon.ca`) + Elections Yukon AGOL + `open.yukon.ca` CKAN API | Open Government Licence – Yukon 2.0 (`OGL-Yukon-2.0`) | ✅ Yes — no gate, no account, bare GET | ⚠ Presumed yes, **not verified** | ⛔ Licence *text* never read — `yukon.ca` and `open.yukon.ca/data/*` return Cloudflare 403 to every server-side fetch. Identity confirmed from CKAN metadata only; clauses not quoted rather than guessed. Attribution asserted by the data itself: `Government of Yukon on behalf of Elections Yukon`. No click-through encountered anywhere. |

### coverage
| Jurisdiction | Rows held | Seats | Authoritative count | Vintage held | Current vintage | Delta |
|---|---:|---:|---:|---|---|---|
| Yukon | 19 | 21 | 21 | 2015 order (S.Y. 2008 c. 14 as am. by S.Y. 2015 c. 11), in force 2016-10-07 | 2024 order (S.Y. 2024 c. 14, assented 2024-11-21), in force on the 2025 dissolution | ⛔ **One full generation stale.** 15/21 slug match; 6 authoritative districts have no polygon (`Marsh Lake - Mount Lorne - Golden Horn`, `Southern Lakes`, `Takhini`, `Watson Lake - Ross River - Faro`, `Whistle Bend North`, `Whistle Bend South`), 4 held rows point at dissolved districts (`Mount Lorne-Southern Lakes`, `Pelly-Nisutlin`, `Takhini-Kopper King`, `Watson Lake`). **Full re-key required.** ★ `jurisdiction_sources.seats = 21` is CORRECT — Yukon went 19→21 at the 2025-11-03 election; do not "fix" it to 19. ⛔ Build blocked on the exact 2025 dissolution date (Cloudflare). ⛔ Prior generation unrecoverable — GeoYukon overwrote in place, `open.canada.ca` mirrors delisted; our 19 rows are the last public copy. |

### a6
| Jurisdiction | Current prefix | A6-compliant target | Status |
|---|---|---|---|
| Yukon | `yukon-electoral-districts-2015/` | `yukon-electoral-districts/` | ⛔ **Violation** — year in prefix. Not applied. ★ Applying A6 *shrinks* the build: the 15 name-stable districts keep their `constituency_id` and gain a second row at `boundaries_version='2024'`, so the 21-row re-key becomes a 19-row prefix rename + 6 new districts. ⚠ The unique key becomes load-bearing — rename prefix and set `boundaries_version='2015'` in the same statement or the new rows collide. |
