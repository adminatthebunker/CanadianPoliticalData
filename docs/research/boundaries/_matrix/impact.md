### coverage

> ⛔ **Created 2026-09-01, the last of the 20 fragments.** `overview.md` flagged it as the one
> outstanding fragment on 2026-08-18 and it was never written — which is why the impact study's
> headline figures propagated into `overview.md` and `../README.md` as bare numbers with no
> matrix row carrying their caveats.
>
> ⚠ **These measure the Open North mirror and have NOT been re-run since the cutover.** They are
> a **pre-cutover baseline** — the evidence that justified the build (migrations `0064`–`0121`) —
> never a current error rate. Live counts: [`../PROGRESS.md`](../PROGRESS.md).

| Jurisdiction | Rows held | Seats | Authoritative count | Vintage held | Current vintage | Delta |
|---|---:|---:|---:|---|---|---|
| National — provincial layer, **no answer** | 665 | 714 | 714 | mixed 2012–2024 | varies | ⛔ **9.15%** of Canadian addresses got nothing (address-weighted, 32,500-address NAR sample, 2,500/jurisdiction, seed 2026). BC contributed 6.05pp alone. ✅ Superseded by the cutover — every jurisdiction is now on authoritative geometry |
| National — provincial layer, **wrong answer** | 665 | 714 | 714 | mixed | varies | ⚠ **2.12%** over the 6 jurisdictions whose authoritative geometry was readable (62.3% of addresses); **any-error 12.61%**. BC 48.3%, YT 37.9%, NT 14.3%, ON 2.1%, NS 1.9%, AB 1.2% |
| National — federal layer (control) | 342 | 343 | 343 | 2023 Rep. Order | 2023 Rep. Order | ✅ 0.95% no-answer + 0.83% wrong = **1.79%**, consistent with the single missing district. ★ The control is the load-bearing part: it shows the method does not over-report |
| National — municipal layer | 942 | n/a | n/a | mixed | varies | ⛔ **Not measurable by this method.** A municipal PIP returned a *set*, not an answer (Mississauga Civic Centre → 4 overlapping polygons), so there was no single answer to score. ✅ Closed by the cutover — PIP integrity is now `tested=1316 ok=1316 ambiguous=0 lost=0` |

### cross-jurisdictional findings from this dossier

- ★ **Address-weighted, not area-weighted or district-weighted.** A district-weighted rate
  flatters a jurisdiction whose failures are urban and punishes one whose failures are empty
  tundra. The unit that matters is *people who get a wrong answer*.
- ★ **The federal control is what makes the provincial numbers credible.** Run against the one
  layer known to be nearly correct, the method returned 1.79% — so a 42.3% BC reading is a
  finding, not an artefact of the harness.
- ⚠ **`boundary_simple` is not free.** PE loses 2.10% of its area to simplification against
  <0.5% elsewhere, so part of PE's 28.8% no-answer rate is the tolerance, not the map. Any
  re-run must measure against full `boundary`, as `/boundaries/lookup` does.
- ⚠ **33–71% of FSAs cross a federal riding boundary**, which is why `approximate` on an
  `fsa_derived` postcode answer is load-bearing rather than cosmetic.

### a6

| Jurisdiction | Current prefix | A6-compliant target | Status |
|---|---|---|---|
| n/a — no boundary rows are owned by this dossier | — | — | ✅ Not applicable; impact is a measurement dossier, not a source dossier |
