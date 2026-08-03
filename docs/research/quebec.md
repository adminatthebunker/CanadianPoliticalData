# Quebec — Legislative Data Research

> Standalone research dossier for Quebec. Cross-cutting context (schema, scanner modules, probe hierarchy, research-handoff protocol) lives in [`overview.md`](./overview.md).

**Legislature:** National Assembly of Quebec (Assemblée nationale du Québec) | **Website:** https://www.assnat.qc.ca | **Seats:** 125 | **Next election:** 2026-10-05

**Status snapshot (2026-05-22):** ✅ **Bills live** (102 / 115 / 95 — **94 / 95 sponsors FK-linked, 99%**) via donneesquebec.ca CSV + RSS + bill-detail HTML. ✅ **Hansard live for 8 sessions** (39-1 → 43-2, Jan 2009 → April 2026, **17-year span, 313,345 speeches / 1,278 sittings, 438,830 chunks all embedded with Qwen3**, **86.7% politician-attributed** after the 2026-05-22 full bio re-fetch + dated-resolver re-run picked up trailing `ended_at` coverage that yesterday's partial run hadn't reached). ✅ **Tier 1 Speaker resolution live** — "Le Président" rows tied to the sitting Speaker by date across 5 Speakers (Bissonnet / Vallières / Chagnon / Paradis / Roy). ✅ **Historical MNA roster live (2026-04-27)** — alphabet-walk of /fr/membres/notices/index*.html (16 letter-pages, ~2,500 MNAs since 1764) with bio-prose career-span extraction; one wide-span `politician_terms` row per MNA (`source='assnat.qc.ca:former-mnas'`); date-windowed post-pass resolver `resolve-qc-speakers-dated` now scheduled daily at 16:32 UTC (existed since the 2026-04-27 ship but had never been scheduled — gap closed 2026-05-21). ✅ **Speech-type honest-coverage classification (2026-05-21):** QC parser now emits `speech_type='group'` for `Des voix` / `Une voix` chorus turns (24,608 rows) and `speech_type='staff'` for `Le Secrétaire` Secretary-General turns (3,129 rows). ✅ **Date-windowed surname backfill (2026-05-21):** ran the unscheduled `resolve-qc-speakers-dated` for the first time end-to-end; **+10,917 rows attributed** (Couillard / David / Gaudreault / Ouellet families lifted at 99.4% hit rate when single-date-candidate match); QC attribution **79.1% → 82.6%** (+3.5pp). Schedule seeded so future ingests stay caught up automatically. Remaining 26,868 surname-ambiguous rows characterized 2026-05-21: **~4,500 blocked by a roster-coverage gap** for 2008-2022 retirees (Khadir 1,143 / Deltell 835 / James 490 / Malavoy 477 / Hivon 360 / Weil 341 / Doyer 319 / Vien 311 etc. — all absent from `politicians` because `qc_former_mnas.py` walks `/fr/membres/notices/index*.html` alphabet listings which cover pre-2008-ish history only); a latent SSL bug in that ingester was fixed same day (`httpx.AsyncClient` now uses `verify=False` matching the `qc_bills.py` precedent — alphabet walk now succeeds, 16 pages / 2,556 MNAs found, but all 2,556 are already in roster confirming the source-coverage gap), and a weekly Sun 04:20 UTC schedule was seeded. The remaining recent-retiree URL family (likely under `/fr/deputes/{slug}-{id}/index.html` direct fetches or bilan-de-l'Assemblée per-Legislature lists) is the natural next QC cycle. **~21K rows are genuine surname-ambiguity** (Tremblay / Couillard / Fournier / Bédard / Dupuis families where 5-10 distinct MNAs share a surname and their terms overlap) — needs document-level continuity (find first long-form mention in the same document) or per-mandate `politician_terms.constituency_id` backfill, both deeper refactors. **Document-level continuity resolver shipped 2026-05-21** as `resolve-qc-speakers-doc-continuity` (scheduled daily 16:33 UTC, after `resolve-qc-speakers-dated`): for each unresolved bare-surname row, look for an already-attributed row in the SAME `raw->'qc_hansard'->>'document_id'` where the attributed politician's `last_name` matches the unresolved surname, with a count-distinct=1 gate, confidence 0.75. **Empirical lift was 18 rows out of 26,868 candidates (0.07%)** — the original hypothesis (50-70% of unresolved would have richer-form references earlier in the same doc) was invalidated end-to-end: the remaining unresolved bucket is dominated by documents where the speaker is ALWAYS bare-surname (no `M. Stéphane Bédard` / `M. Bédard (Chicoutimi)` reference earlier in the same sitting day's Hansard to bootstrap from). The resolver still runs daily — lift may grow as other resolvers (role-based, future first-name) attribute more rows that this one can then propagate from. **Real path forward for the 21K surname-ambiguity bucket** is per-mandate `politician_terms.constituency_id` backfill so the `constituency_hint` parser slot (currently populated on only 1,217/26,868 unresolved) becomes useful, plus a riding→politician ground-truth source. **1,272 parens-bearing rows** split into riding hints (`M. Paradis (Lévis)`) and first-name witnesses (`M. Paquin (Mathieu)` — committee witnesses, not MNAs); witness-tagging schema decision and a riding→politician ground-truth source needed for further attribution. Votes / committees not yet built. Private bills and votes registry deferred.

---

## User research (handoff URLs)

These URLs were the user's initial research handoff for QC and seeded the pipeline:

- https://www.assnat.qc.ca/en/travaux-parlementaires/index.html — parliamentary work hub
- https://www.assnat.qc.ca/en/deputes/index.html#listeDeputes — assembly members roster
- https://www.assnat.qc.ca/fr/fils-rss.html — RSS feed catalog (where the bills RSS came from)
- https://www.assnat.qc.ca/en/travaux-parlementaires/projets-loi/projets-loi-43-2.html — bills index for the current session

## Bills & Legislation ✅ LIVE (2026-04-16)

- **Primary source — donneesquebec.ca CSV:** https://www.donneesquebec.ca/recherche/dataset/projets-de-loi — official open-data export, refreshed **daily**, CC-BY-NC-4.0. One HTTP GET returns all 613 bills across current + previous legislature. Columns: `Numero_projet_loi`, `Titre_projet_loi`, `Type_projet_loi`, `Derniere_etape_franchie`, `Date_derniere_etape`, `No_legislature`, `Date_debut_legislature`, `Date_fin_legislature`, `No_session`.
- **Stage timeline — RSS:** https://www.assnat.qc.ca/fr/rss/SyndicationRSS-210.html — XML feed fires on every stage transition in the current session. Same pattern as NS RSS (`ns_rss.py`). Parses ~25 items/day.
- **Sponsor resolution — bill detail HTML:** pattern `https://www.assnat.qc.ca/{en|fr}/travaux-parlementaires/projets-loi/projet-loi-{N}-{parl}-{session}.html`. Sponsor is one `<a href="/en/deputes/{slug}-{id}/index.html">` — numeric MNA id → `politicians.qc_assnat_id` FK lookup (**no name-fuzz**, same leverage as BC's `lims_member_id`).
- **MNA roster:** server-side HTML at `/en/deputes/index.html`. 125 MNAs embedded with numeric ids in URL slugs. Single-page scrape populates `politicians.qc_assnat_id` — run once, enables exact-match sponsor joins forever.
- **Session attribution caveat:** CSV tags carried-over bills with the *current* session (`No_session`) but bill-detail URLs use the *origin* session. The title always prefixes with "{parl}-{sess} PL {N} ..." — parse that prefix to decide the real session, else the detail URL 404s.
- **Private bills ("D'intérêt privé", 58/613, numbered 99x+):** different URL scheme we couldn't pin down. Pipeline skips them in the sponsor-fetch phase; they still get CSV bill rows but no sponsor.
- **Scanner modules:** `qc_mnas.py` (roster), `qc_bills.py` (CSV + RSS + detail HTML).
- **CLI:** `enrich-qc-mna-ids`, `ingest-qc-bills`, `ingest-qc-bills-rss`, `fetch-qc-bill-sponsors`.
- **Terms/Licensing:** CC-BY-NC-4.0 on the open-data CSV. Detail pages are Crown copyright. Civic-transparency use is non-commercial so both fit.
- **Rate limits / auth:** None observed. No WAF signals. 1.5s delay used for politeness in sponsor fetch.
- **Difficulty (1–5):** 2 (CSV makes it trivially easy; one 404 footgun from the session-origin quirk).
- **Results on first run:** 102 bills / 115 events / 95 sponsors (**94 / 95 FK-linked to politicians** = 99%).
- **Outstanding probes:** Private-bill URL scheme; votes registry (see Voting Records below — registry page is ASP.NET postback, deferred).

## Hansard / Debates ✅ LIVE (2026-04-20, sessions 39-1 → 43-2)

> **2026-08-02 — 43-3 hole found + fixed.** Session 43-3 opened 2026-05-05 and its dropdown label carries a `Session en cours - ` prefix that the `_SESSION_OPTION_RE` in `qc_hansard.py` didn't tolerate — discovery raised, the Wayback fallback returned zero sittings, and the daily job reported `succeeded, sittings=0` for ~3 months (the bug was invisible at build time because QC was *between* sessions mid-April: no option carried the prefix then). Regex fixed to allow a prefix; the dropdown-miss error (`SessionNotInDropdownError`) no longer falls back to Wayback. Backfilled 2026-08-02: 17 sittings / 3,961 speeches (43-3, 2026-05-06 → 2026-06-12) + 68 new votes; 43-2's 2026-04-02 end was verified complete (prorogation was 2026-04-08; no sittings after 04-02). The corpus table below predates 43-3 and its totals are stale — trust the DB.

**Final corpus (8 sessions, 2009-01-13 → 2026-04-02):**

| Session | Speeches | Sittings | Politician-resolved | Date range |
|---|---:|---:|---:|---|
| 43-2 | 14,784 | 51 | 84.9 % | 2025-09-30 → 2026-04-02 |
| 43-1 | 65,253 | 223 | 83.4 % | 2022-11-29 → 2025-06-06 |
| 42-2 | 18,944 | 70 | 72.2 % | 2021-10-19 → 2022-06-10 |
| 42-1 | 49,092 | 214 | 69.9 % | 2018-11-27 → 2021-10-07 |
| 41-1 | 45,546 | 352 | 39.8 % | 2014-05-20 → 2018-06-15 |
| 40-1 | 23,872 | 85 | 31.1 % | 2012-10-30 → 2014-02-20 |
| 39-2 | 38,246 | 117 | 40.3 % | 2011-02-23 → 2012-06-15 |
| 39-1 | 57,608 | 166 | 40.5 % | 2009-01-13 → 2011-02-21 |
| **Total** | **313,345** | **1,278** | **57.2 %** | **17-year span** |

Resolution drops on older sessions because retired MNAs aren't in `politicians` — same gap as AB historical backfills. Fixable later by enriching the politicians table with ca. 2009–2018 retired MNAs.

- **Primary source:** Journal des débats daily HTML transcripts at `https://www.assnat.qc.ca/fr/travaux-parlementaires/assemblee-nationale/{parl}-{sess}/journal-debats/{YYYYMMDD}/{doc_id}.html` — one per sitting day. French is primary; English versions often 500 and are not ingested. **100% of content is fetched from the origin (assnat.qc.ca); Wayback is used only for URL discovery on historical sessions (see below).**
- **Discovery — dual path:**
  - **Current session (43-2):** ASP.NET WebForms listing at `/fr/travaux-parlementaires/journaux-debats/`. Session filter `ddlSessionLegislature` (e.g. 1617 = 43-2) + page size `ddlNombreParPage=100` + debate-type `rblOptionTypeDebat=1` + pagination via `__EVENTTARGET=…lkbPageSuivante` POSTs carrying `__VIEWSTATE` / `__EVENTVALIDATION` / `__VIEWSTATEGENERATOR`.
  - **Historical sessions (43-1 and older):** the same form returns HTTP 500 for every non-current session (server-side bug, reproducible from multiple IPs and inside the container). Fallback path: the **Wayback Machine CDX API** at `https://web.archive.org/cdx/search/cdx?url=assnat.qc.ca/fr/travaux-parlementaires/assemblee-nationale/{parl}-{sess}/journal-debats/*&filter=statuscode:200&filter=mimetype:text/html` returns the set of transcript URLs Wayback has indexed for that session. We dedupe the CDX rows and build `SittingRef` objects pointed at the **origin URLs** — every actual transcript fetch still goes straight to assnat.qc.ca. Wayback is a URL-discovery crutch, never a content mirror.
  - **Wayback coverage is a ceiling on discovery.** Per session (indexed transcripts): 43-1 = 223, 42-2 = 70, 42-1 = 215, 41-1 = 354, 40-1 = 107, 39-2 = 117, 39-1 = 166. Real sitting counts may be 5–15 % higher; can be backfilled later if/when the assnat form gets fixed.
- **Parser markup:** Speaker turns are `<p style="text-align: justify"><b>Honorific Surname :</b> speech text…</p>` with continuation paragraphs in plain `<p>`s (no `SpeakerContinues` class). Heading-vs-speaker disambiguated by *trailing colon* inside the `<b>` — centered bold without a colon is a section heading. NBSP (`\xa0`) between tokens is common. The parse module lives at `services/scanner/src/legislative/qc_hansard_parse.py` — pure-offline, importable for fixture testing.
- **Attribution shapes observed:**
  - Person: `M. Ciccone` / `Mme Charest` — honorific + surname only (no given name).
  - Role + person: `La Vice-Présidente (Mme Soucy)` — resolved via the parenthetical name.
  - Role + riding: `M. Lévesque (Chapleau)` — riding used to disambiguate shared surnames (Lévesque, Bélanger, Roy). The scanner stores the riding as `raw.qc_hansard.constituency_hint` and the SpeakerLookup indexes `(surname, constituency) → politician` so these resolve cleanly.
  - Pure role: `Le Président` / `La Vice-Présidente` / `Le Premier ministre` / `Le Ministre de X` / `Le Secrétaire` / `Des voix` / `Une voix`.
- **Speaker resolution:** `politicians.qc_assnat_id` carries 124/124 active MNAs (enriched by `enrich-qc-mna-ids`). The SpeakerLookup builds four indexes from the politicians table: `by_full_name`, `by_surname` (with compound-surname + name-tail keys — e.g. "Boivin Roy" indexes both "Karine Boivin Roy" and "Roy"), and `by_riding_surname`. Presiding-officer rows (`speaker_role='Le Président'`) are left NULL at ingest and resolved in a post-pass by `presiding_officer_resolver.py` using the QC SPEAKER_ROSTER (Paradis / Roy).
- **Source system:** `source_system='hansard-qc'`. Upsert key `UNIQUE NULLS NOT DISTINCT (source_system, source_url, sequence)` — idempotent.
- **Scanner modules:** `qc_hansard.py` (discovery + fetch + upsert + post-pass), `qc_hansard_parse.py` (HTML → ParsedSpeech).
- **CLI:** `ingest-qc-hansard --parliament 43 --session 2 [--since/--until/--limit-sittings/--limit-speeches/--url]`, `resolve-qc-speakers`, `resolve-presiding-speakers --province=QC`, `chunk-speeches`, `embed-speech-chunks`.
- **Difficulty (1–5):** **3**. ASP.NET postback pagination is the only wrinkle; the per-sitting markup is clean semantic HTML.
- **Terms/Licensing:** Crown copyright. Civic-transparency / non-commercial use fits the stated terms.
- **Rate limits / auth:** None observed; 1.5 s delay between sittings for politeness.
- **Known limitations:**
  - *Shared-surname ambiguity without a riding hint* — e.g. "Mme Bélanger" when two Bélanger MNAs are active and the transcript doesn't include the riding. ~15–20 rows per sitting fall here; they land `confidence=0.0 politician_id=NULL` and don't resolve until we add context tracking (next-speech inference).
  - *Le Secrétaire / Des voix / Une voix* — structurally non-resolvable (Le Secrétaire is assembly staff, not an MNA; the voices are anonymous). Expect ~60 rows per sitting to remain `politician_id=NULL`.
  - *Historical sessions* — the 43-1 and earlier backfill will resolve less cleanly because retired MNAs aren't in `politicians` yet (same roster gap as AB). V1 scopes to current session.
  - *Sections* — `raw.qc_hansard.section` is not yet populated (heading markup varies across eras). Speech text still includes the section heading words, so retrieval is unaffected.

## ★ Historical MNA roster — live 2026-04-27

**Problem:** Hansard resolution rates dropped from 84 % on 43-2 to **31-46 %** on 39-1/39-2/40-1/41-1 because retired MNAs (anyone who left before the current 124-MNA roster snapshot) weren't in `politicians`. The QC dossier flagged this on 2026-04-20 as "Fixable later by enriching the politicians table with ca. 2009-2018 retired MNAs."

**Source:** Single alphabetical listing at `https://www.assnat.qc.ca/fr/lien/11861.html` (redirects to `/fr/membres/notices/index.html`) — *Liste des députés depuis 1764* (~2,556 MNAs). Walked across 16 letter-pages:

```
index.html       (A)        index-jk.html  (J+K)
index-b.html     (B)        index-l.html   (L)
index-c.html     (C)        index-m.html   (M)
index-d.html     (D)        index-no.html  (N+O)
index-ef.html    (E+F)      index-p.html   (P)
index-g.html     (G)        index-qr.html  (Q+R)
index-hi.html    (H+I)      index-s.html   (S)
                            index-tu.html  (T+U)
                            index-vz.html  (V-Z)
```

Each entry on a letter-page has the form:

```html
<a href="https://www.assnat.qc.ca/fr/deputes/{slug}-{id}/index.html">Surname,&nbsp;Given Name</a>&nbsp;(en fonction)
```

— or, for some pre-Confederation members, the alternate URL shape `/fr/patrimoine/anciens-parlementaires/{slug}-{id}.html`. **Crucially the two URL families do *not* share a stable integer:** they each maintain a SEPARATE integer ID space and the small-N range collides (deputes/`khadir-amir-25` and patrimoine/`baby-charles-25` are completely different MNAs). `qc_assnat_id` is therefore the integer from the **`deputes/` family only** — the same key `qc_mnas.py` uses for current MNAs and `qc_bills.py` joins on for sponsor FK. Patrimoine rows get `qc_assnat_id = NULL` and a `source_id` of `assnat.qc.ca:former-mnas:patrimoine:{slug}-{id}` (or the transitional `…:patrimoine:legacy-{id}` if demoted from a legacy buggy run). The `(en fonction)` suffix distinguishes current-roster entries.

**No JSON serializer.** `?_format=json` returns the same HTML. The bio page at `/fr/deputes/{slug}-{id}/biographie.html` (or `.../patrimoine/anciens-parlementaires/{slug}-{id}.html`) renders the career as **prose only** — no per-mandate structured listing — e.g.:

> Élue députée du Parti québécois (PQ) dans La Peltrie en 1981. […] Défaite en 1985. Élue députée dans Taillon en 1989. Réélue en 1994, en 1998 et en 2003. Démissionna comme députée le 20 mars 2006. Élue députée dans Charlevoix à l'élection partielle du 24 septembre 2007. […] Défaite en 2014.

We extract a **single coarse career span** per MNA via five regex patterns:

| Regex (Python) | Captures | Use |
|---|---|---|
| `\b(?:[Éé]lue?\|R[ée]{1,2}lue?)\b[^.]{0,160}?\ben\s+(\d{4})\b` | first-of-multi election years | `started_at` = min |
| `\b[Dd][ée]fait[ee]?\b[^.]{0,80}?\ben\s+(\d{4})\b` | defeat year | `ended_at` candidate |
| `\b[Dd][ée]missionna\b[^.]{0,200}?\b(\d{4})\b` | resignation year | `ended_at` candidate |
| `\b[Dd][ée]c[ée]da\b[^.]{0,160}?\b(\d{4})\b` | death year | `ended_at` candidate |
| `\b[Nn]e\s+s['’]?est\s+pas\s+repr[ée]sent[ée]e?\b[^.]{0,160}?\b(\d{4})\b` | did-not-stand-for-reelection year | `ended_at` candidate |

`ended_at = max(end_candidates ≥ start_year)`, NULL if no end marker. Gaps within the span (e.g. Marois's 1985-1989 hiatus) are tolerable — they coincide with periods where the MNA wasn't speaking in Hansard, so over-including them is harmless to the resolver.

On re-runs the term-insert path will **widen** an existing `ended_at` if a later end-year is detected (it never narrows), so iterative regex improvements pick up trailing coverage without manual SQL. Use `--bio-for-existing` to force bio re-fetch for already-stored MNAs after adding a regex (Khadir / Hivon / Weil all gained 2018-2022 trailing coverage this way on 2026-05-21).

**Module:** `services/scanner/src/legislative/qc_former_mnas.py` (`ingest_qc_former_mnas`).

**Migration:** `0038_unique_qc_assnat_id.sql` — promotes the existing partial btree on `qc_assnat_id` to a UNIQUE partial index so the politicians upsert can use `ON CONFLICT (qc_assnat_id) WHERE qc_assnat_id IS NOT NULL`. **Pre-flight collision** (Éric vs Eric Girard, both `qc_assnat_id=17929`, ingested 2026-04-14 by Open North via differently-encoded slugs) was merged manually — surviving row keeps the accent-correct Éric Girard form, plain-spelling row's 1,234 speeches + 2,045 chunks reparented onto it.

**Resolver:** `qc_hansard.resolve_qc_speakers_dated` — single-CTE date-windowed update.

```sql
WITH unresolved AS (
  SELECT s.id, s.spoken_at,
         COALESCE(s.raw->'qc_hansard'->>'paren_surname',
                  s.raw->'qc_hansard'->>'surname') AS surname_raw
    FROM speeches s
   WHERE s.source_system='hansard-qc' AND s.politician_id IS NULL
     AND s.spoken_at IS NOT NULL
     AND COALESCE(s.raw->'qc_hansard'->>'paren_surname',
                  s.raw->'qc_hansard'->>'surname') IS NOT NULL
),
candidates AS (
  SELECT u.id AS speech_id, array_agg(DISTINCT p.id) AS cand_ids,
         count(DISTINCT p.id) AS n_cands
    FROM unresolved u
    JOIN politicians p
      ON p.province_territory='QC' AND p.level='provincial'
     AND lower(unaccent(p.last_name)) = lower(unaccent(u.surname_raw))
    JOIN politician_terms pt
      ON pt.politician_id=p.id AND pt.province_territory='QC' AND pt.level='provincial'
     AND (pt.started_at IS NULL OR pt.started_at::date <= u.spoken_at::date)
     AND (pt.ended_at   IS NULL OR pt.ended_at::date   >= u.spoken_at::date)
   GROUP BY u.id
)
-- ... cand_count=1 → update speeches + speech_chunks in same SQL
```

**CLI:** `ingest-qc-former-mnas`, `resolve-qc-speakers-dated`, `resolve-qc-speakers-doc-continuity`. All three wired into `jobs_catalog.py` + `admin.ts` mirror. The ingester command exposes `--bio-for-existing` for the regex-improvement re-fetch path described above.

**2026-05-21 fix — recent-retirees (2008-2022) roster gap closed.** The original ingester treated the `deputes/`-family and `patrimoine/`-family integers as a single `qc_assnat_id` namespace. Because patrimoine integers are sequential small Ns (1, 3, 5, 7, …) while deputes integers grow into the tens of thousands, the patrimoine entries silently *occluded* the same-N deputes entries via `ON CONFLICT (qc_assnat_id) DO UPDATE` — the patrimoine row landed first (alphabet-walk starts at A), and the deputes-family insert for Khadir=25 / Hivon=27 / Deltell=17 / James=49 / Doyer=91 / Vien=191 / Weil=33 / Malavoy=255 turned into a no-op update on the wrong politician. ~4,500 Hansard rows of these 8 MNAs were stuck as `politician_id IS NULL` for a year. The fix: namespace the listing dedup on `(bio_kind, qc_assnat_id)`; patrimoine inserts now leave `qc_assnat_id` NULL and identify themselves by `source_id` only; a one-time Pass 1.5 demotes any legacy-shape `assnat.qc.ca:former-mnas:qc_assnat_id={N}` row whose stored `last_name` doesn't match the deputes/-listing `last_name` at integer N. After re-ingesting + re-running `resolve-qc-speakers-dated`, all 8 verified retirees were fully attributed (1,143 / 835 / 490 / 477 / 360 / 341 / 319 / 311 rows respectively, plus secondary lift across other recent retirees — **6,090 total speech attributions** vs the 4,500 spec target).

## ★ Tier 1 Speaker resolution — live 2026-04-20

"Le Président" / "La Présidente" attributions carry only the role, not a name. Resolution is date-ranged against `politician_terms.office='Speaker'`, seeded from a small hand-curated roster in `presiding_officer_resolver.py::SPEAKER_ROSTER["QC"]`:

| Speaker | Start | End |
|---|---|---|
| Michel Bissonnet | 2003-05-13 | 2008-04-08 |
| Yvon Vallières | 2008-04-08 | 2011-04-05 |
| Jacques Chagnon | 2011-04-05 | 2018-10-01 |
| François Paradis | 2018-11-28 | 2022-11-29 |
| Nathalie Roy | 2022-11-29 | — |

Run with:

```bash
docker compose run --rm scanner resolve-presiding-speakers --province QC
```

Idempotent. DELETE-then-INSERT of Speaker terms on each run. Updates `speeches.politician_id` **and** `speech_chunks.politician_id` (denormalised copy) in the same transaction. Adding a new Speaker is a 3-line PR: append a `SpeakerTerm(…)`, bump the prior Speaker's `ended_at`, re-run the command.

**Scope note:** Tier 1 covers only "Le Président" (single-person-at-a-time, date-determinable). Tier 2 would extend to "Le Vice-Président" / "La Vice-Présidente" — which is partially auto-resolved already because the Journal des débats uses the `(Mme Soucy)` parenthetical form that names the Vice-Président directly, so most Vice-Président rows resolve at ingest without needing a term-based post-pass.

## Voting Records / Divisions

- **Source URL(s):** https://www.assnat.qc.ca/fr/lien/12779.html (Register of Recorded Divisions); also embedded in Journal des débats and bill pages
- **Format:** HTML scattered across multiple pages.
- **Roll-call availability:** Yes; member names and votes.
- **Difficulty (1–5):** 4.
- **Notes:** No dedicated voting API. Registry page is **ASP.NET postback** — needs form-aware scrape or Playwright. Requires navigating bill/session structure.

## Committee Activity

- **Source URL(s):** https://www.assnat.qc.ca/fr/travaux-parlementaires/commissions/index.html ; https://www.assnat.qc.ca/en/deputes/fonctions-parlementaires-ministerielles/composition-commissions.html ; individual committee pages at `/travaux-parlementaires/commissions/{committee-code}/`
- **Format:** HTML + PDF reports; committee Hansard in HTML.
- **Data available:** Memberships, meetings, reports, transcripts (Journal des débats per committee).
- **Overlap with existing scanner:** None.
- **Difficulty (1–5):** 4.
- **Notes:** Committees (commissions) organized by legislature/session code. Bilingual.

## Existing third-party scrapers

- **opencivicdata/scrapers-ca:** `ca_qc` module exists.
- Other: None identified.

## Status

- [x] Research complete
- [x] Schema drafted (migration `0012_politician_qc_assnat_id.sql`)
- [x] Ingestion prototyped
- [x] Production ingestion live (2026-04-16) — bills + events + sponsors
- [ ] Hansard / Journaux des débats
- [ ] Voting records (registry page is ASP.NET postback — needs form-aware scrape or Playwright)
- [ ] Committee meetings + reports
- [ ] Private-bill URL scheme
