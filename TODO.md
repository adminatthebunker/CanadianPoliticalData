# TODO

Actionable checkbox view of [`docs/timeline.md`](./docs/timeline.md). When this file disagrees with the timeline or with a plan doc under [`docs/plans/`](./docs/plans/), **the plan docs win** — update this file rather than the other way round.

- **Last synced with `docs/timeline.md`:** 2026-04-30
- **Why this exists:** the timeline is prose-shaped; this is the version you tick off. One source of priority ordering (timeline), one place to mark progress (here).
- **How to update:** check items as they ship, move them to *Recently shipped*, and re-sync the date above. If a horizon shifts, edit `docs/timeline.md` first, then mirror here.

---

## Now (in flight)

Partially built — finish, do not start new things on top.

- [x] **`/api/v1/search` finalization.** Hybrid HNSW + BM25 is wired. Today's filter expansion (`min_similarity`, `parliament_number + session_number`, `speech_type`, the new `/search/sessions` endpoint, the frontend advanced-filters disclosure) widened the surface; pending: performance tuning + public contract freeze. → [`docs/plans/semantic-layer.md`](./docs/plans/semantic-layer.md), [`docs/plans/search-features-handoff.md`](./docs/plans/search-features-handoff.md)
- [x] **Premium reports — phase 1c follow-ups.** Phase 1b (LLM map-reduce, `/reports/<id>` viewer, refund flow) and phase 1c #1 (public-share + citation, migration 0036) are shipped. Remaining ranked queue: report-this-search button, re-run on new evidence, per-section flagging, compare two politicians. → [`docs/plans/premium-reports-followups.md`](./docs/plans/premium-reports-followups.md)
- [x] **Stripe Tax — operator activation.** Code is shipped (`STRIPE_TAX_ENABLED` flag, default off). Remaining is dashboard-only: activate Stripe Tax, add Canadian tax registration (GST/HST + any provincial PST), classify each credit-pack Price with a tax code, run a test-mode dry-run, then flip `STRIPE_TAX_ENABLED=true` in production. → [`docs/operations.md`](./docs/operations.md) § Stripe Tax

---

## Next 1 — Database: finish the corpus

Priority one until remaining Hansard pipelines are live and votes are modelled. Every provincial Hansard build is gated on the **research-handoff rule** (CLAUDE.md convention #5) — pause and ask the user for their endpoint research before probing.

### Remaining Hansard pipelines (4 left; NT shipped 2026-04-29)

- [x] **NT Hansard** — consensus-government schema. Drupal HTML scrape with direct `nt_mla_slug` FK attribution (cleanest of any sub-national pipeline). 19 current + 117 former MLAs, 13th-20th Assembly Speaker roster. → [`docs/runbooks/handoff-2026-04-29-nt-hansard.md`](./docs/runbooks/handoff-2026-04-29-nt-hansard.md)
- [ ] **NU Hansard** — consensus-government, multilingual (EN + Inuktitut + Inuinnaqtun + FR). Research-handoff gated. → [`docs/research/nunavut.md`](./docs/research/nunavut.md)
- [ ] **SK Hansard** — PDF-only; needs dedicated `pdfplumber` parser investment (same tooling unlocks AB Hansard historical). Research-handoff gated. → [`docs/research/saskatchewan.md`](./docs/research/saskatchewan.md)
- [ ] **PE Hansard** — sits behind WAF/CAPTCHA. Research-handoff gated; may require Playwright/Camoufox track (see *Later*). → [`docs/research/prince-edward-island.md`](./docs/research/prince-edward-island.md)
- [ ] **YT Hansard** — same WAF/CAPTCHA bucket as PE. Research-handoff gated. → [`docs/research/yukon.md`](./docs/research/yukon.md)

### Votes & committees

- [x] **Apply migration `0018_votes.sql`.** Applied 2026-04-30. NT consensus-government data validates the schema without revisions. NT votes extractor live (`extract-nt-votes`), 31 consensus votes across 2013-2026 NT corpus. → [`docs/runbooks/handoff-2026-04-30-votes-layer.md`](./docs/runbooks/handoff-2026-04-30-votes-layer.md)
- [x] **Federal votes extraction (openparliament.ca structured JSON).** Live 2026-04-30. `services/scanner/src/legislative/federal_votes.py` extracts ~928 44-1 divisions × ~340 MPs = ~300K vote_positions with 100% politician_id FK match (via openparliament_slug). Daily 11:30 UTC schedule slot. → [`docs/runbooks/handoff-2026-04-30-federal-votes.md`](./docs/runbooks/handoff-2026-04-30-federal-votes.md)
- [x] **Federal votes — historical sessions** (39-1 through 43-2) shipped 2026-04-30. 4,481 total votes / 1.45M positions / 18.5 years (2006-05 → 2024-12) / 99.98% pol-FK / 335 MB storage. → [`docs/runbooks/handoff-2026-04-30-federal-votes.md`](./docs/runbooks/handoff-2026-04-30-federal-votes.md)
- [ ] **Federal historical bills ingestion** — would lift bill-linkage on votes from 10.2% (44-1 only) to ~50% corpus-wide via trivial UPDATE pass. Separate workstream.
- [x] **Provincial votes extraction (BC/AB/MB/QC/ON/NS/NB/NL)** shipped 2026-04-30. 8 self-contained per-province extractor modules; 7,303 provincial votes added (QC 2,961 div+acclamation rich; NS 2,550 consensus; ON 835; AB 624; BC 249; MB 47; NL 2; NB 0 — needs regex relaxation). → [`docs/runbooks/handoff-2026-04-30-provincial-votes.md`](./docs/runbooks/handoff-2026-04-30-provincial-votes.md)
- [ ] **Provincial votes — extractor v2 tuning** — AB/NS show ~100% pass rate (regex misses defeats); NB returned 0 (bilingual structure needs relaxed pattern). Small follow-up.
- [ ] **Provincial votes daily-ingest schedules** — 8 schedule entries (one per province at `:50` after each Hansard chain). Mechanical; defer until needed.
- [ ] **Committee transcripts.** Same speech pipeline, `speech_type='committee'`. Deferred until votes land. → [`docs/plans/semantic-layer.md`](./docs/plans/semantic-layer.md) § phase 4

### Historical-roster backfills (AB/MB pattern → ON/BC/QC)

- [x] **ON historical roster.** Propagate the date-windowed-resolver pattern. Required before pre-current-session ON Hansard speaker attribution is meaningful pre-2010s.
- [x] **BC historical roster.** Pre-P35 Wikipedia ingester (P29-P34, +160 MLAs / +359 terms) + `resolve-bc-speakers-dated` + extended Speaker roster (P29-P37). BC corpus 67.6% → 91.9% attributed. → [`docs/runbooks/handoff-2026-04-29-bc-pre-p35-roster.md`](./docs/runbooks/handoff-2026-04-29-bc-pre-p35-roster.md)
- [x] **QC historical roster.** Shipped 2026-04-27 — `ingest-qc-former-mnas` + `resolve-qc-speakers-dated`. → [`docs/runbooks/handoff-2026-04-27-bc-qc-historical.md`](./docs/runbooks/handoff-2026-04-27-bc-qc-historical.md)

### Corrections inbox

- [ ] **SMTP poller + admin review queue.** Web flag-button shipped; `correction_submissions` table exists (migration 0020); SMTP ingest and admin UI not built. Small but blocks the public correction policy.

### Social enrichment

- [ ] **Apify social-post deep enrichment, phase 0/1 → 2–5.** Schema + Twitter pilot done (phase 0/1); Instagram, TikTok, Bluesky direct, Mastodon direct, reverse-WHOIS pending. Steady-state cost $100–$250/mo on quarterly refresh. → [`docs/plans/apify-social-deep-enrichment.md`](./docs/plans/apify-social-deep-enrichment.md)

### Bill text for the laggards

- [ ] **SK / PE / YT bill ingest.** 10/13 sub-national + federal already live. Bundle this with each jurisdiction's Hansard build when it lands.

---

## Next 2 — Chat interface

A conversational front door over the existing semantic-search + contradictions stack. Retrieval, ranking, and grounded-citation primitives already exist — chat is the UX wrapper.

- [ ] **Write the plan doc.** No `docs/plans/chat-*.md` exists yet. Settle the open questions before any code:
  - Scope: general-purpose Q&A vs. politician-scoped vs. bill-scoped?
  - Grounding discipline: every claim cites a chunk, refusal otherwise?
  - Model: OpenRouter free-tier (like contradictions) or paid (like phase-1b reports)?
  - Metering: free / credit-metered / rate-limited?
  - Session persistence: extend `saved_searches` or new `chat_sessions`?
  - Transcript export, credit-ledger interaction, voice-input handoff (see Next 3).
- [ ] **Build, reusing existing primitives.** Semantic-search hybrid retrieval + contradictions consent/model picker are load-bearing. **Don't fork retrieval.**

---

## Next 3 — Accessibility (incl. voice)

Two distinct workstreams under one priority. WCAG 2.2 AA is the audit target.

### Accessibility audit + remediation

- [ ] **Plan doc for the audit.** None exists.
- [ ] **Keyboard navigation pass** across `/search`, `/coverage`, `/postal`, the politician page, the admin shell.
- [ ] **Screen-reader testing** on the same surfaces.
- [ ] **Color-contrast pass on the map.** Leaflet defaults are not great.
- [ ] **ARIA landmarks + form labels** site-wide.

### Voice interface

- [ ] **Plan doc for voice.** None exists. Must come before any code.
- [ ] **Speech-to-text for query input** (STT on-device where possible, server-side fallback). Lands in the chat surface from Next 2, not in `/search`.
- [ ] **Text-to-speech for results read-back.** Prioritised for low-vision and low-literacy users.
- [ ] **Sovereignty constraint:** STT/TTS must be self-hostable or have a defensible Canadian-data path. Hosted-Whisper-via-third-party is not the default. → [`docs/plans/sovereignty-runtime-deps.md`](./docs/plans/sovereignty-runtime-deps.md)

---

## Next 4 — UI improvements

Independent, ship-each-on-its-own work.

- [ ] **`/chunk/<uuid>` detail page.** Internal view: full speech around a chunk + neighbours. Today chunks deep-link out to source Hansard via `source_url + source_anchor`.
- [ ] **Politician biography brief.** Full-coverage report (all speeches/bills/votes per politician) as a phase-2+ premium SKU on top of phase-1b query-scoped reports. → [`docs/plans/premium-reports.md`](./docs/plans/premium-reports.md) § v2+
- [ ] **Topic dashboard / time series.** "Climate mentions across all legislatures over time"; faceted aggregations by party / jurisdiction / speaker.
- [ ] **Compare politician A vs. B on topic X.** Phase-2+. Probably reuses the chat surface from Next 2.
- [ ] **Map polish.** Symbol legend, faster cluster-zoom transitions, constituency-boundary year picker (boundaries are temporal as of migration 0021).

---

## Always-on (every cycle, regardless of horizon)

- [ ] **Governance docs before public launch.** Takedown / correction policy, DSAR workflow (especially before Apify social enrichment goes public), AI-report disclaimer text. None written yet; small but blocking.
- **Backup system completion.** Path B (parallel `pg_dump` directory format) is documented in [`docs/operations.md`](./docs/operations.md) § Backups but operator-run. Path A (`sovpro db backup` → single gzipped file) is fine for small / portable snapshots and stays as-is.
  - [ ] **Wrap Path B in a single CLI subcommand** — e.g. `sovpro db backup-fast`. One call performs the manifest write (git SHA + row counts + applied migrations), `pg_dumpall --globals-only`, sidecar `pg_dump -Fd -j 8`, ownership fix-up, and `pg_restore --list` verify. Today it's a five-step copy-paste block.
  - [ ] **Schedule it via `scanner_schedules`.** Daily cadence at a quiet UTC hour, well clear of the daily-ingest band. Failures should surface in the admin Jobs page like every other scanner job.
  - [ ] **Retention / rotation** on the primary backup directory. Keep N daily, M weekly, K monthly; prune the rest. Today snapshots accumulate forever at ~216 GB each.
  - [ ] **LUKS USB mirror automation** — at minimum a ready-to-paste script that drives `cryptsetup luksOpen` → `rsync` → `umount` → `cryptsetup luksClose` from one entry point. Stays operator-triggered (USB needs a passphrase), not scheduled.
  - [ ] **Off-host mirror.** S3 / B2 / equivalent on cron — same `rsync` shape as the USB mirror, different destination. `operations.md` already names this as the production posture; not yet implemented.
  - [ ] **Logged restore drill.** Run `pg_restore -j 4` end-to-end against a fresh staging DB and time it. The HNSW rebuild floor (30–60 min on the 3.4 M-chunk corpus) is currently an estimate; replace with a measured number and re-drill quarterly.
  - [ ] **Encryption-at-rest check.** Confirm the internal NVMe target (`/media/bunker-admin/Internal/canadian-political-data-backups/`) is on an encrypted partition or migrate it to one. Backups carry user emails, magic-link redemption history, Stripe customer IDs, and full speech text — same threat model as the LUKS USB.
- [ ] **Embedding-model drift monitoring.** Re-run the eval set under [`services/embed/eval/queries/queries.jsonl`](./services/embed/eval/queries/queries.jsonl) on any model change. Qwen3-Embedding-0.6B is current; BGE-M3 wrapper kept on disk for rollback only. → [`docs/plans/embedding-model-comparison.md`](./docs/plans/embedding-model-comparison.md)
- [ ] **AI-contradictions false-positive watch.** Live and free-tier; watch for quoted-opponent and party-transition-boundary failure modes. → [`docs/plans/ai-contradictions-handoff.md`](./docs/plans/ai-contradictions-handoff.md)
- [ ] **Coverage-dashboard accuracy.** Run `refresh-coverage-stats` after every Hansard or bills ingest so `/coverage` doesn't lie.
- [ ] **Documentation freshness.** Update [`docs/api.md`](./docs/api.md) when `/api/v1/search` ships; add a `/developers` section to [`README.md`](./README.md) when the public dev-API ships; edit `docs/timeline.md` (and re-sync this file) when priorities shift.

---

## Later (deferred, plan docs exist)

Parked behind the priorities above — not abandoned.

- [ ] **Public developer API** (`/api/public/v1/*`) with three paid tiers. Free / dev / pro, Stripe subscriptions distinct from credit-pack one-time, per-tier rate limits, OpenAPI + Swagger UI, key provisioning at `/account/api-keys`. → [`docs/plans/public-developer-api.md`](./docs/plans/public-developer-api.md)
- [ ] **Bulk export endpoints** (Parquet / CSV) — `read:bulk` scope, per-jurisdiction-month presigned exports. Sits behind dev-API v1.0 as v1.1. → same plan doc.
- [ ] **Map tiles self-hosting.** CARTO + OSM currently CDN-loaded. Three options scoped: nginx raster cache, PMTiles + MapLibre GL (~25 GB Z0–Z14 Canada), OpenMapTiles container. → [`docs/plans/sovereignty-runtime-deps.md`](./docs/plans/sovereignty-runtime-deps.md) § item 3
- [ ] **Browser automation (Playwright / Camoufox)** for PE/YT WAF jurisdictions. Only worth it if direct outreach to legislatures for a civic-transparency allowlist fails. → [`docs/plans/national-expansion-scoping.md`](./docs/plans/national-expansion-scoping.md) q5.3
- [ ] **Openparliament.ca live-call → scheduled refresh.** `/api/v1/openparliament` hits `api.openparliament.ca` per request; move to a scanner refresh job + DB cache (outage-mitigation). → [`docs/plans/sovereignty-runtime-deps.md`](./docs/plans/sovereignty-runtime-deps.md) § item 4

---

## Recently shipped (last two cycles, 2026-04-23 → 2026-04-29)

For context. Move items here from above as they land; trim aggressively after a couple of cycles.

### Cycle 2026-04-26 → 2026-04-30

- [x] **Federal votes extractor live** — openparliament.ca structured-JSON pipeline, ~928 44-1 divisions × ~340 MPs ≈ 300K `vote_positions` with 100% politician-FK resolution via openparliament_slug exact match (cleanest votes pipeline in the project). Federal chain extended: 11:00 bills → 11:15 Hansard → 11:30 votes. → [`docs/runbooks/handoff-2026-04-30-federal-votes.md`](./docs/runbooks/handoff-2026-04-30-federal-votes.md) (2026-04-30).
- [x] **Migration 0018 votes applied + NT votes extractor live** — schema validated against NT consensus-government data without revisions; 31 consensus votes across 2013-2026 corpus; daily 21:50 UTC schedule slot. Federal openparliament.ca + provincial regex extractions now unblocked. → [`docs/runbooks/handoff-2026-04-30-votes-layer.md`](./docs/runbooks/handoff-2026-04-30-votes-layer.md) (2026-04-30).
- [x] **NT Hansard pipeline live** — Drupal HTML scrape of ntlegislativeassembly.ca; per-turn `<a href="/meet-members/mla/{slug}">` direct slug-FK attribution (cleanest pattern of any sub-national pipeline); 19 current + 117 former MLAs ingested; 13th-20th Assembly Speaker roster seeded. Migration 0041 + `nt_mlas.py` + `nt_hansard.py` + `nt_hansard_parse.py`. Daily 21:30 UTC schedule slot. → [`docs/runbooks/handoff-2026-04-29-nt-hansard.md`](./docs/runbooks/handoff-2026-04-29-nt-hansard.md) (2026-04-29).
- [x] **BC pre-P35 historical roster + dated resolver + extended Speaker roster** — `bc_former_mlas.py` Wikipedia per-parliament wikitable parser (+160 MLAs / +359 `politician_terms` rows for P29-P34); `resolve-bc-speakers-dated` (single CTE with inline surname extraction); `SPEAKER_ROSTER["BC"]` extended P38 → P29 (+13 historical Speakers). BC corpus attribution 67.6% → 91.9% (+136K speeches; +20K Speaker-tagged rows; +186K chunks). → [`docs/runbooks/handoff-2026-04-29-bc-pre-p35-roster.md`](./docs/runbooks/handoff-2026-04-29-bc-pre-p35-roster.md) (2026-04-29).
- [x] **TEI + embed resilience layer** — device-aware TEI healthcheck (single-token /embed with `--max-time 1`, fails on CPU fallback), `restart: on-failure:5`, scanner-side preflight CPU-fallback check, exponential-backoff per batch (5 attempts 1s→16s), abort-on-5-consecutive-batch-failures guard. Closes the GPU-regression gap. (2026-04-28)
- [x] **`chunk-and-embed-speeches` daily schedule** — single combined Click command + `scanner_schedules` row at 08:00 UTC (= 02:00 Mountain), atomic chunk → embed ordering in one process. First scheduled run 2026-04-29 cleared 1,157 chunks in 13s. (2026-04-29)
- [x] **BC + QC historical-roster backfills** — QC `ingest-qc-former-mnas` (alphabet-walk of assnat.qc.ca, 2,090/2,383 bios with usable career spans, migration 0038); BC `enrich-bc-member-parliaments` (LIMS GraphQL `allMemberParliaments`, 750 (member, parliament) edges, BC terms 103→853). QC P39-P42 resolution +12-33%. (2026-04-27)
- [x] **BC pre-P38 Hansard parser** — era-branching `bc_hansard_parse.py` extension covering P29-P37 (1970-2005). +378K speeches; BC corpus ~198K → ~577K. (2026-04-27)
- [x] **ON historical MPP roster + pre-2007 Hansard parser** — propagation of date-windowed-resolver pattern to ON. (2026-04-26)

### Cycle 2026-04-23 → 2026-04-26

- [x] **Phase 1b — premium reports** — `report_jobs` table (migration 0035), `reports-worker` compose service, OpenRouter map-reduce, sanitised-HTML viewer at `/reports/<id>`, refund flow (released-hold vs compensating admin-credit), admin triage queue. First credit-spending feature.
- [x] **Phase 1c #1 — public-share + citation** — `is_public` flag (migration 0036), `/public/reports/<id>` route, citation block in viewer footer (2026-04-24).
- [x] **ON Hansard pipeline** — name-based resolution + parens-name extraction; 6 ON commands packed into the 18:00 UTC daily-ingest slot (2026-04-24).
- [x] **`/api/v1/search` filter expansion** — `min_similarity`, `parliament_number + session_number`, and `speech_type` filters on `baseFilterSchema`; new `/search/sessions` endpoint backing the cascading parliament/session dropdown; advanced-filters disclosure on `/search` (2026-04-26).
- [x] **Operational hygiene cluster** — `OPENROUTER_MODEL` → `OPENROUTER_CONTRADICTIONS_MODEL` rename with legacy fallback + boot-time deprecation warning; `scripts/backup-database.sh` hardened (`.env`-sourced knobs, file-pinned `DB_PASSWORD`, zstd default 19 → 3); BetaBadge in the site header; `docs/api.md` Search section finally written (2026-04-26).
- [x] **Stripe Tax wiring** — `STRIPE_TAX_ENABLED` env flag, `automatic_tax` + address collection + `tax_id_collection` on the Checkout Session when on, `tax_enabled` field on `/me/credits/packs`, frontend disclosure on `/account/credits`, plan-doc + `docs/operations.md` activation checklist. Default off — operator dashboard activation listed under Now (2026-04-26).
