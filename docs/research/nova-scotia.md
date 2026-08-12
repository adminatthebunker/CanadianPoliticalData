# Nova Scotia — Legislative Data Research

> Standalone research dossier for Nova Scotia. Cross-cutting context (schema, scanner modules, probe hierarchy, research-handoff protocol) lives in [`overview.md`](./overview.md).

**Legislature:** House of Assembly | **Website:** https://nslegislature.ca | **Seats:** 55 | **Next election:** By 2029-12-07

**Status snapshot (2026-04-22):** ✅ **Bill rows live** via Socrata — easiest source in the country (3,522 bills across 24 sessions). Per-bill HTML cache **partially blocked by WAF budget** (~25/3,522 cached). RSS-feed pivot or email allowlist pending. ✅ **Hansard session 65-1 live** — 10,608 speeches across 44 sittings (Dec 2024 → present), 100% speaker resolution via `politicians.nslegislature_slug` + date-ranged Speaker roster. NS is the **reference implementation** that other provincial pipelines follow.

---

## Bills & Legislation

- **Source URL(s):** https://nslegislature.ca/legislative-business/ ; https://data.novascotia.ca/Government-Administration/Bills-introduced-in-the-Nova-Scotia-Legislature/iz5x-dzyf
- **Format:** **Socrata API** (JSON, CSV, SoQL queries) via data.novascotia.ca.
- **Fields captured upstream:** Bill title, status, first/assented-to versions (1995–96 to present), bill types.
- **Terms/Licensing:** **Open Government Licence (Nova Scotia)** — permissive, attribution only.
- **Rate limits / auth:** Public app token recommended but not required. Rate limits generous; documented at dev.socrata.com.
- **Difficulty (1–5):** **2** — easiest bills source in the country.
- **Notes:** **The NS reference implementation.** Socrata's SoQL query language is a JSON/REST API — the closest provincial analog to federal LEGISinfo. The shared `bills` schema was built against this source first.

## ★ RSS feed (discovered 2026-04-15)

Complement to Socrata: `https://nslegislature.ca/legislative-business/bills-statutes/rss` serves an RSS 2.0 feed of every bill in the current session (253 items for 65-1, ~122 KB, single request). Delivers richer status text than Socrata — commencement clauses, exceptions, effective-date caveats in the `<description>` field.

**What RSS gives us:**

- Status text: `"Royal Assent - October 2, 2025; Commencement: October 3, 2025 except:..."` — commencement + exception detail that Socrata's terse `description` field never had.
- pubDate on each status change.
- Single-request polling suitable for a daily cron.

**What RSS doesn't give us:**

- Historical bills (current session only).
- Sponsor slug (still needs HTML bill-page fetch).

**Integration:** `legislative/ns_rss.py` + CLI `ingest-ns-bills-rss`. Matches RSS items to existing Socrata-ingested bills via the canonical source_id; merges RSS payload into `bills.raw.rss`; refreshes `bills.status` and `bills.status_changed_at`; appends `bill_events` rows for the current stage. Fully idempotent, no WAF impact.

## Known blocker: NS WAF daily budget

The per-bill HTML detail-page fetcher hits a per-IP request budget (~11–14 reqs / window). Delay-tuning does **not** help — the counter is per successful request, not per unit time. Two open paths:

- **(a)** Switch phase-2 fetcher to the `/bill-N/rss` endpoint (served from a different CDN path in probe tests).
- **(b)** Email `legcomm@novascotia.ca` for a civic-transparency allowlist.

Neither has been started. Meanwhile the existing 25-bill cache is sufficient to prove the pipeline. The 3,500+ re-fetches we've done so far were waste — the same headers re-trigger the WAF every time.

## Hansard / Debates

- **Source URL(s):** https://nslegislature.ca/legislative-business/hansard-debates ; https://nslegislature.ca/about/supporting-offices/hansard-reporting-services
- **Format:** HTML transcripts from 1994 forward; PDF index; video/audio webcasts.
- **Granularity:** Daily; includes committee Hansards.
- **Speaker identification:** Yes.
- **Difficulty (1–5):** 3 (HTML scrape; near-trivial once the slug roster is stamped).
- **Notes:** Transcripts published next morning after sitting. Contact: Hansard Reporting Services, 902-424-7990.

### Implementation (current-session, 2026-04-22)

Session index URL `https://nslegislature.ca/legislative-business/hansard-debates/{parliament}-{session}` lists every sitting in the given assembly. Sitting transcript URLs follow `/assembly-{N}-session-{M}/house_{YYmonDD}` — deterministic, enumerable. No Hansard-specific RSS feed exists (probed 2026-04-22: `/rss`, `/feed`, `/hansard-debates/rss`, `/hansard/rss`, `/legislative-business/rss` — only the last returns a valid RSS, and it's empty); `?_format=json` also disabled.

Every speaker turn in the body HTML is a `<p>` opening with `<a name="{slug}-NNNN"></a><a href="/members/profiles/{slug}">NAME</a>` (member) or `<a href="/members/speaker/">THE SPEAKER</a>` (presiding). The slug is the exact value stored on `politicians.nslegislature_slug`, so speaker resolution is a direct FK join — the strongest attribution model of any NS-visible legislature, on par with the federal openparliament pipeline. No name-fuzz fallback is used in production.

**Pipeline:** `ingest-ns-mlas` → `ingest-ns-hansard` → `resolve-presiding-speakers --province NS` → `chunk-speeches` → `embed-speech-chunks`. The MLA roster command harvests `(slug, displayed_name)` pairs from the newest sittings and stamps `nslegislature_slug` on existing NS politician rows; at the start of NS Hansard work only 10/55 seated MLAs had slugs (sponsors of the 25 WAF-cached bills), so this pre-pass is load-bearing.

The NS Hansard pages sit on a different CDN path than the per-bill HTML that triggered the WAF budget — no rate-limit issues observed at 1.5s delay between sittings.

**Phase-1 scope (landed 2026-04-22):** Session 65-1 only, 44 sittings, 10,608 speeches, 100 % politician_id resolved (5,665 slug-joined to MLAs + 4,943 Speaker turns resolved to Danielle Barkhouse via `presiding_officer_resolver`). Historical sessions (back to 1994) deferred until an historical-MLA roster pass lands slugs for departed members.

**Premier role-only Pass-3 (shipped 2026-05-22):** Historical NS sessions ingested between Phase-1 and this cycle surfaced a 1,904-row `speaker_name_raw='THE PREMIER'` bucket (`speaker_role IS NULL`) spanning 2013-12-03 → 2021-03-31 — the McNeil + Rankin Liberal era. The NS Hansard parser stamps the ALL-CAPS role token into `speaker_name_raw` rather than `speaker_role` for the bare-role turns, so the cross-jurisdictional `resolve-role-only-presiding-officers` resolver (previously role-keyed only) grew a `ROLE_ONLY_NAME_PATTERNS` companion map that matches on `speaker_name_raw` when `speaker_role IS NULL OR ''`. Roster: Stephen McNeil (2013-10-22 → 2021-02-23), Iain Rankin (2021-02-23 → 2021-08-31). Houston (PC, 2021-08-31+) ships in the parens-form `HON. TIM HOUSTON (The Premier)` and is Pass-1 territory. Resolver attributed all 1,904 rows at confidence 0.85; NS attribution rose from 96.73 % → 99.70 %. Daily schedule: `45 13 * * *` UTC, between `extract-ns-votes` (50 13) and the BC chain (00 14). **Pre-existing Houston mis-attribution cleanup (shipped same cycle 2026-05-22):** the Phase-1 ingest pipeline had attributed `speaker_name_raw='THE PREMIER'` rows to Houston at confidence 1.0 by simple last-name match without a date-window check — including 112 rows from McNeil/Rankin's era (17 in 2016 + 18 in 2017 + 9 in 2018 + 68 pre-Aug-2021). Cleanup: one transaction reset `politician_id=NULL` on those 112 rows + cleared 144 `speech_chunks` denorms; re-ran `resolve-role-only-presiding-officers --province NS` which re-attributed all 112 via the McNeil/Rankin roster (17 + 18 + 9 = 44 → Stephen McNeil; 68 → Iain Rankin). The other 435 Houston-at-confidence-1.0 rows (post-2023-10-19, within his actual Premiership) were left untouched as legitimately correct. NS attribution % unchanged at 99.70 % (politician_id swap only).

## Voting Records / Divisions

- **Source URL(s):** https://nslegislature.ca/ruling-topics/votes ; https://nslegislature.ca/legislative-business/hansard-dates/
- **Format:** House Journals with voice votes and recorded roll calls.
- **Roll-call availability:** Yes when roll call is demanded (two members required per rules).
- **Difficulty (1–5):** 3.
- **Notes:** Divisions entered in minutes. No standalone export.

## Committee Activity — research complete 2026-08-12, build-ready

> **2026-08-12 probe (corrects an earlier belief):** the Hansard-section claim that the daily Hansard feed "includes committee Hansards" is **wrong for the current site** — the chamber feed (`/legislative-business/hansard-debates/assembly-N-session-M`) lists only `house_*` sittings. Committee Hansard lives in **per-committee archive pages**: `/legislative-business/committees/standing/{slug}/archive/{slug}` renders a table (Meeting Date / Subject / Video / Correspondence / Hansard) whose Hansard links are per-meeting **PDFs** at `nslegislature.ca/sites/default/files/pdfs/committees/{code}/{code}_{YYYYMMDD}.pdf` (e.g. `pa/pa_20260617.pdf`; `corr/` sibling dir holds correspondence). Eleven standing committees: assembly-matters, community-services, health, human-resources, internal-affairs, law-amendments, natural-resources-and-economic-development, private-and-local-bills, public-accounts, public-bills, veterans-affairs.
>
> **PDF shape (sampled pa_20260617.pdf):** structured cover page — WITNESSES block (name — title per line, grouped by org), CHAIR / VICE-CHAIR names, date/time — then ALL-CAPS speaker labels (`THE CHAIR:` …). This is the AB-committees cover-page pattern: parse the witness roster from the cover, resolve members by name against the NS roster (`nslegislature_slug` FK exists on `politicians` but PDFs carry no slugs — name-based), everyone in the WITNESSES block is NULL-by-design. Bounded new-PDF-parser build (~AB-sized slice, difficulty 3, not the hoped-for discovery-filter change). WAF note: `/sites/default/files/` PDF fetch succeeded without challenge at probe time; verify budget behaviour before a full walk.

- **Overlap with existing scanner:** none — needs a new `ns_committees.py` (discovery = 11 archive pages, likely paginated; parser = new all-caps PDF shape).
- **Notes:** Contact: legcomm@novascotia.ca, 902-424-4432.

## Existing third-party scrapers

- **opencivicdata/scrapers-ca:** `ca_ns` module exists (provincial + Halifax, Cape Breton).
- Other: None identified.

## Status

- [x] Research complete
- [x] Schema drafted (0006 — same as ON)
- [x] Ingestion prototyped (Socrata → 3,522 bills across 24 sessions)
- [~] Production ingestion partial — bill rows complete; per-bill HTML fetch blocked by WAF budget (25/3,522 cached). RSS-feed pivot or email allowlist pending.
- [x] Sponsor→politician resolver working (14/14 parsed sponsors linked)
- [x] Hansard — session 65-1 live (10,608 speeches, 100% resolved); historical sessions ingested with Premier role-only Pass-3 (2026-05-22) closing the 1,904-row `THE PREMIER` bucket → 99.70% NS attribution overall. Pre-2013 historical backfill still deferred
- [ ] Votes
- [ ] Committees
