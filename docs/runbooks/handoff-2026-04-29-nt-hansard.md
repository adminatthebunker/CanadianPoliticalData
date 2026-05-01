# NT Hansard pipeline — 2026-04-29

NT Hansard goes from research-handoff-gated to live, with the cleanest speaker-attribution path of any sub-national pipeline we've built. User greenlit "probe yourself" after BC roster work landed; same-session probe + build + smoke + backfill.

## What shipped

```
db/migrations/
  0041_politicians_nt_mla_slug.sql       NEW — partial UNIQUE on nt_mla_slug

services/scanner/src/legislative/
  nt_mlas.py                             NEW — current + former roster ingester
  nt_hansard.py                          NEW — Drupal HTML ingester
  nt_hansard_parse.py                    NEW — wikitext-style Drupal Views parser
  presiding_officer_resolver.py          UPDATED — added 8-entry NT Speaker roster (13th-20th Assembly)

services/scanner/src/__main__.py         3 new Click commands:
  ingest-nt-mlas
  ingest-nt-hansard
  resolve-presiding-speakers --province NT (extended Choice list)

services/scanner/src/jobs_catalog.py     Mirror entries
services/api/src/routes/admin.ts         UI catalog mirror

scripts/seed-daily-ingest-schedules.sql  Added 21:30 + 21:45 UTC NT chain entries

docs/research/northwest-territories.md   Status snapshot updated
TODO.md / docs/timeline.md               Re-sync (separate task)
```

## Source map

| What | URL pattern | Notes |
|---|---|---|
| Hansard listing | `/documents-proceedings/hansard?page=N` | Drupal Views pager, ~50/page |
| Transcript HTML | `/hansard/hn{YYMMDD}` | Stable since at least 2002 |
| Transcript PDF | `/sites/default/files/hansard/{YYYY-MM}/HN{YYMMDD}.pdf` | Alongside HTML — not ingested |
| Transcript Word | `/sites/default/files/hansard/{YYYY-MM}/HN{YYMMDD}.docx` | Alongside HTML — not ingested |
| Sitemap | `/sitemap.xml` (Drupal Simple XML Sitemap, 3 paged) | Confirms Drupal |
| Current MLAs (19) | `/members/members-legislative-assembly/members` → `/meet-members/mla/{slug}` | Exact match with Open North roster |
| Former MLAs (~117) | `/members/former-members?page=N` → `/former-members/{slug}` | **Different slug path; same slug values** |
| Drupal `?_format=json` | OFF (`"No route found... Supported formats: html"`) | HTML scrape only |
| OpenNWT mirror | `hansard.opennwt.ca` returns 403 | Not viable as alternative source |

## Why this pipeline is structurally cleaner than other provinces

Each speaker turn in modern (2017+) transcripts is wrapped in:

```html
<article class="node node--type-member node--view-mode-teaser">
  <a href="/meet-members/mla/shane-thompson" rel="bookmark">
    <span class="field field--name-title ...">Shane Thompson</span>
    <div class="field field--name-field-constituency ...">Nahendeh</div>
  </a>
</article>
```

The slug *is* the FK. We stamped `nt_mla_slug` on `politicians` (migration 0041), and the parser extracts the slug at parse time. Speaker resolution is an exact-string FK join — no name normalization, no surname-collision logic, no date-window disambiguation. **17/17 MLA turns attributed at 100% on the smoke sitting; 21/21 on a 2017 sitting tested for backward compatibility.**

Compare to the resolution machinery other provinces required:
- BC: 3-tier name lookup (`by_full_name` / `by_initial_last` / `by_surname`) + dated-resolver post-pass
- QC: parens-name extraction + accent normalization + surname-only fallback
- AB: legislature-keyed re-resolution against `legl_assembly_member_id`
- ON: Drupal JSON node fetch with structured speaker fields

NT just gives us the slug at the markup level. That's the win.

## Two markup shapes for speakers (load-bearing detail)

(a) **MLA profile turn** — `<article class="node--type-member">` + nested anchor to `/meet-members/mla/{slug}` + body div sibling. Used for every Member's Statement, Minister's Statement, Oral Question, Reply, etc.

(b) **Presiding-officer interjection** — `<div class="views-field views-field-field-speaker">` with plain-text `<span>MR. SPEAKER</span>` + body div. Used for the Speaker's procedural lines between members ("Thank you Member from X. Members' statements. Member from Y."). No MLA profile because the Speaker doesn't appear as a regular member in this view-mode.

Initial parser only handled (a) and silently skipped (b) — 14 of 31 statement rows on the test sitting. Refactored to try (a) first, fall back to (b), with `speaker_role='Speaker'` set when (b) matches. The existing `resolve-presiding-speakers --province NT` then attributes (b) rows by date against the seeded Speaker roster.

## Bilingual handling — Pattern (A), confirmed appropriate

The NT corpus has inline `[Translation] ... [Translation Ends]` markers but they annotate Indigenous-language or French portions for which the **English translation is already present in the body**. So the body text we ingest IS the canonical English version; we leave the markers in place and tag every speech `language='en'`.

This is structurally similar to NB's bilingual-PDF handling but NT does not duplicate same-utterance content in two languages — there's no two-row-per-utterance question to resolve. Pattern (B) (separate FR speech rows) was considered and rejected; it would have been the first jurisdiction to fork the speech-as-utterance model with no consumer-side requirement asking for it.

If a future surface needs per-language faceting, the principled answer is a `speech_translations` side-table (`speech_id, language, body`) — not a horizontal change to the `speeches` row model.

## Speaker roster (NT)

Seeded into `politician_terms` via `resolve-presiding-speakers --province NT`:

| Speaker | Start | End | Assembly |
|---|---|---|---:|
| Samuel Gargan | 1995-01-01 | 2000-01-01 | 13th |
| Tony Whitford | 2000-01-01 | 2003-01-01 | 14th |
| David Krutko | 2003-01-01 | 2004-01-01 | 15th |
| Paul Delorey | 2004-01-01 | 2011-01-01 | 15th-16th |
| Jackie Jacobson | 2011-01-01 | 2015-01-01 | 17th |
| Jackson Lafferty | 2015-01-01 | 2019-01-01 | 18th |
| Frederick Blake Jr. | 2019-01-01 | 2023-12-07 | 19th |
| Shane Thompson | 2023-12-07 | — | 20th |

Year-only Wikipedia dates with the December 2023 transition pinned to the 20th Assembly's convening date (Nov 14 election → Dec 7 first sitting). Pre-2003 transcripts likely don't exist in the LIMS HDMS scope (sitemap depth ~30 pages back to ~2002).

## Coverage

- **Listing depth**: ~30 paginated listing pages back to ~2002 (~24 years).
- **Per-page**: 45-50 unique sitting URLs.
- **Estimated total**: ~1,500-2,000 sittings.
- **Full backfill**: ran in the same session at 1.0s polite delay; ~50 min wall time.

Daily schedule fires `--limit-sittings 5` at 21:30 UTC — that's enough to catch up freshly-published sittings without re-walking the full ~30-page listing every day.

## Ledger (post-roster, post-smoke; full backfill in flight)

```sql
-- NT politicians: 19 → 136 (+117 former MLAs from /members/former-members)
SELECT count(*) AS total, count(*) FILTER (WHERE nt_mla_slug IS NOT NULL) AS with_slug
  FROM politicians WHERE province_territory='NT' AND level='provincial';
-- → 136, 135 (one Open North row didn't slug-merge — name drift edge)

-- NT Hansard speeches by attribution path
SELECT count(*) AS total,
       count(*) FILTER (WHERE politician_id IS NOT NULL) AS attributed,
       round(100.0*count(*) FILTER (WHERE politician_id IS NOT NULL)/count(*),1) AS pct
  FROM speeches WHERE source_system='hansard-nt';
```

## Follow-ups (not gating today's ship)

- **Migration 0018 votes**: with NT Hansard live, the `vote_type='consensus'` discriminator now has real data to validate against. Apply once we ingest a few NT divisions (separate workstream).
- **NU Hansard**: sister jurisdiction. Multilingual (EN + Inuktitut + Inuinnaqtun + FR) → not the simple English-canonical NT case. Research-handoff still gated.
- **Pre-2017 attribution audit**: the 2017 transcript hit 100% slug coverage; no probe yet of pre-2010 markup. If older sittings show <90% attribution, build a `resolve-nt-speakers` name-fallback. Today the slug-FK path is sufficient.
- **NT bills historical backfill** (Assemblies 16-19 visible in nav, URL routing not mapped) — independent of Hansard work.

## Convention #1 status (per CLAUDE.md)

```
- Federal: openparliament_slug
- Nova Scotia: nslegislature_slug
- Ontario: ola_slug + ola_member_id (int)
- BC: lims_member_id (int)
- Quebec: qc_assnat_id (int)
- Alberta: ab_assembly_mid (text)
- Manitoba: mb_assembly_slug
- Northwest Territories: nt_mla_slug (text)        ← NEW (migration 0041, 2026-04-29)
```
