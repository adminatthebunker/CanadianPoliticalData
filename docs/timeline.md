# Timeline / direction

Where the project is going, in priority order. Last reviewed 2026-05-03.

This is the **what we're building next** doc. For the **why**, read [`goals.md`](./goals.md). For the **how**, read the per-feature plan under [`plans/`](./plans/) linked from each item below. When this file disagrees with the plan docs, the plan docs win — keep this one short and reorder it as priorities shift.

Three horizons:
- **Now** — in flight, expected to land in the next cycle.
- **Next** — the four stated priorities, in order. Each has a one-paragraph framing and a link to the plan doc (or a flag that no plan exists yet).
- **Later** — documented in plan docs but deliberately deferred. Not orphaned; just not the current focus.

A separate **Always-on** section covers governance, monitoring, and ingest hygiene that doesn't fit a horizon.

---

## Now (in flight)

These are partially built and the goal is to finish them, not to start something new on top.

- **`/api/v1/search` finalization.** Hybrid HNSW + BM25 retrieval is wired with zod validation and instruction prompting at query time. Filter expansion (`min_similarity`, `parliament_number + session_number`, `speech_type`, the `/search/sessions` endpoint, frontend advanced-filters disclosure) shipped 2026-04-26; performance + UX lift shipped 2026-05-03 in commit `1df626f` — pg pool 10 → 30, query-embedding LRU (60s/500), result-cache LRU on the frontend, `anchor_chunk_id` re-centring with `AnchorChunkBanner` + `SearchMapView` (radial graph of top-K, click-to-recentre), `include_count` split, `source_system` denorm. Remaining is the public contract freeze (zod schema lock + `docs/api.md` v1.0 sign-off). Plan: [`plans/semantic-layer.md`](./plans/semantic-layer.md), [`plans/search-features-handoff.md`](./plans/search-features-handoff.md).
- **Premium reports — phase 1c follow-ups.** Phase 1b (LLM map-reduce, `/reports/<id>` viewer, refund flow) and phase 1c #1 (public-share + citation, migration 0036) are shipped. Remaining ranked queue: report-this-search button, re-run on new evidence, per-section flagging, compare two politicians. Plan: [`plans/premium-reports-followups.md`](./plans/premium-reports-followups.md).

---

## Next (priorities, in order)

### 1. Database — finish the corpus

The product is only as definitive as the data behind it. Database expansion stays priority one until the remaining Hansard pipelines are live and votes are modelled.

- **Remaining Hansard pipelines: NU → SK → PE/YT.** Four jurisdictions left (NT shipped 2026-04-29). NU needs consensus-government + multilingual handling (EN + Inuktitut + Inuinnaqtun + FR); SK is PDF-only and needs dedicated parser investment; PE/YT sit behind WAFs/CAPTCHAs. Each is gated on the **research-handoff rule** (see CLAUDE.md convention #5) — user research pass first, code second. Status table: [`research/overview.md`](./research/overview.md).
- **Votes table — ✅ done across both shapes.** Migration 0018 applied 2026-04-30; NT consensus-government data validated the schema without revisions (31 NT consensus votes); federal openparliament.ca structured-JSON extraction live the same day with 100% politician-FK resolution via openparliament_slug. Federal historical-session backfill (39-1 → 43-2) shipped 2026-04-30 (4,481 votes / 1.45M positions), provincial regex extensions live across BC/AB/MB/QC/ON/NS/NB/NL (7,303 votes). Federal vote→bill linkage lifted from 10.2% → 54.7% on 2026-05-01 via pure-SQL re-link pass after federal-bills historical backfill.
- **Provincial historical bills — ✅ complete across all active provinces.** `--all-sessions` walker pattern propagated from federal to ON (111 → 3,412), MB (81 → 1,971), and QC (497 → 1,192) over 2026-05-01 / 2026-05-02. QC required a new HTML discoverer (`discover_qc_bills_html`) targeting assnat.qc.ca historical session pages because the donneesquebec CSV is deliberately current+previous only. Every actively-ingestible province now has `bills_status=live`; remaining gaps are NT/NU (consensus-government, naturally smaller) and PE/SK/YT (research- or WAF-gated).
- **Committee transcripts.** Same speech pipeline as Hansard, `speech_type='committee'`. Deferred until votes land so the table stays coherent. Plan: [`plans/semantic-layer.md`](./plans/semantic-layer.md) § phase 4.
- **Historical-roster backfills — ✅ done across AB / MB / ON / QC / BC.** AB (+901, 2026-04-22), MB (+764, 2026-04-23), ON (2026-04-26), QC (~2K via assnat alphabet-walk, 2026-04-27), BC pre-P35 (+160 via Wikipedia + extended Speaker roster P29-P37, 2026-04-29). BC corpus 67.6% → 91.9% attributed. Remaining 8% residual (Committee-Chair / Chairman / Deputy-Speaker rotating roles) needs per-sitting committee-membership data — different workstream, not date-windowed-only.
- **Corrections inbox — SMTP poller + admin review queue.** Web flag-button shipped; `correction_submissions` table exists (migration 0020); SMTP ingest and admin UI not built yet. Small but blocks the public correction policy.
- **Apify social-post deep enrichment.** Phase 0/1 (schema + Twitter pilot) → 2–5 (Instagram, TikTok, Bluesky direct, Mastodon direct, reverse-WHOIS). $100–$250/mo steady-state on quarterly refresh. Plan: [`plans/apify-social-deep-enrichment.md`](./plans/apify-social-deep-enrichment.md).
- **Bill text for SK/PE/YT.** 10/13 sub-national + federal already have bills. Lower priority than Hansard for the same three jurisdictions; bundle the work when their Hansard pipeline lands.

### 2. Chat interface

A conversational front door over the semantic-search + contradictions stack. The retrieval, ranking, and grounded-citation primitives already exist — chat is the UX wrapper that strings them into a turn-based interaction with memory of what the user has already asked.

- **No plan doc yet.** Before writing one, decide: scope (general-purpose Q&A vs. politician-scoped vs. bill-scoped), grounding discipline (every claim cites a chunk, refusal otherwise), model (OpenRouter free-tier like contradictions, or paid like phase-1b reports), and metering (free, credit-metered, or rate-limited).
- **Reuse, don't fork.** The semantic-search hybrid retrieval and the contradictions consent/model picker are the load-bearing pieces. Building a separate retrieval path for chat is the wrong default.
- **Open questions to settle in the plan doc:** session persistence (saved-searches table extension vs. new `chat_sessions`?); transcript export; how chat interacts with the credit ledger; voice-input handoff (see priority #3).

### 3. Accessibility, including voice

Civic-transparency tooling that's only usable by sighted desktop users with steady hands isn't doing its job. Two distinct workstreams:

- **Accessibility audit + remediation.** Keyboard navigation across `/search`, `/coverage`, `/postal`, the politician page, the admin shell. Screen-reader testing on the same surfaces. Color contrast pass on the map (Leaflet defaults are not great). ARIA landmarks and form labels. WCAG 2.2 AA target. No plan doc; needs one before the audit starts.
- **Voice interface.** Two layers: (a) speech-to-text for query input — STT on-device where possible, server-side fallback; (b) text-to-speech for results read-back, prioritized for low-vision and low-literacy users. Tight coupling to the chat interface in priority #2 — voice queries should land in the chat surface, not in `/search`. Unscoped; the plan doc has to come before any code.
- **Sovereignty constraint.** Whatever STT/TTS we pick has to be self-hostable or have a defensible Canadian-data path. Hosted Whisper-via-third-party is not the default. See [`plans/sovereignty-runtime-deps.md`](./plans/sovereignty-runtime-deps.md) for the precedent.

### 4. UI improvements

Smaller, mostly contained UI work. Each can ship independently.

- **`/chunk/<uuid>` detail page.** Internal view showing the full speech around a chunk + neighbouring chunks. Currently chunks deep-link out to source Hansard via `source_url + source_anchor`; the internal page would let a user expand context without leaving the site.
- **Politician biography brief.** Full-coverage report (all speeches, bills, votes per politician) as a phase-2+ premium SKU on top of phase-1b query-scoped reports. Plan: [`plans/premium-reports.md`](./plans/premium-reports.md) § v2+.
- **Topic dashboard / time series.** "Climate mentions across all legislatures over time" style. Faceted aggregations by party, jurisdiction, speaker. Goals doc lists this as the phase-2+ artifact past the v1 search box.
- **Compare politician A vs. B on topic X.** Same phase-2+ bucket. Probably reuses the chat surface from priority #2 once that exists.
- **Map polish.** Symbol legend, faster cluster-zoom transitions, and constituency-boundary year picker now that boundaries are temporal (migration 0021).

---

## Later (deferred, but documented)

Plan docs exist for these. They're not abandoned — they're parked behind the priorities above.

- **Public developer API (`/api/public/v1/*`) with three paid tiers.** Greenfield: free / dev / pro tiers, Stripe subscriptions (distinct from credit-pack one-time), per-tier rate limits, OpenAPI + Swagger UI, key provisioning at `/account/api-keys`. Plan: [`plans/public-developer-api.md`](./plans/public-developer-api.md).
- **Bulk export endpoints (Parquet / CSV) — `read:bulk` scope.** Per-jurisdiction-month presigned exports. Sits behind the dev-API v1.0 launch as v1.1. Plan: same doc as above.
- **Map tiles self-hosting.** CARTO + OSM tiles currently CDN-loaded. Three options scoped: nginx raster cache, PMTiles + MapLibre GL (~25 GB Z0–Z14 Canada), OpenMapTiles container. Plan: [`plans/sovereignty-runtime-deps.md`](./plans/sovereignty-runtime-deps.md) § item 3.
- **Browser-automation (Playwright/Camoufox) for PE/YT WAF jurisdictions.** Investment only worth making if the alternative — direct outreach to the legislatures for a civic-transparency allowlist — fails. Plan: [`plans/national-expansion-scoping.md`](./plans/national-expansion-scoping.md) q5.3.
- **Openparliament.ca live-call → scheduled refresh.** `/api/v1/openparliament` currently hits `api.openparliament.ca` per request; move to a scanner refresh job and cache in DB. Outage-mitigation. Plan: [`plans/sovereignty-runtime-deps.md`](./plans/sovereignty-runtime-deps.md) § item 4.

---

## Always-on

Not horizon-bound. These need attention every cycle regardless of what else is in flight.

- **Governance docs before public launch.** Takedown / correction policy. DSAR workflow (especially before Apify social enrichment goes public). Disclaimer text on AI-generated reports. None written yet; small, but blocking.
- **Backup system completion.** Path B (parallel `pg_dump` directory format → internal NVMe + LUKS USB mirror) is documented in [`docs/operations.md`](./operations.md) § Backups but is operator-run, not automated. Pending: a single `sovpro db backup-fast` wrapper, scheduled run via `scanner_schedules`, retention / rotation of old snapshots, off-host mirror (S3 / B2), and a logged end-to-end restore drill so the wall-time floor is a measured number, not an estimate.
- **Embedding-model drift monitoring.** Re-run the eval set under [`services/embed/eval/queries/queries.jsonl`](../services/embed/eval/queries/queries.jsonl) on any model change. Qwen3-Embedding-0.6B is current; BGE-M3 wrapper kept on disk for rollback only. Plan context: [`plans/embedding-model-comparison.md`](./plans/embedding-model-comparison.md).
- **AI contradictions false-positive watch.** Feature is live and free-tier; watch for quoted-opponent and party-transition-boundary failure modes. Plan: [`plans/ai-contradictions-handoff.md`](./plans/ai-contradictions-handoff.md).
- **Coverage dashboard accuracy.** `/coverage` is the honesty surface. After every Hansard or bills ingest, run `refresh-coverage-stats` so the dashboard doesn't lie.
- **Documentation freshness.** When `/api/v1/search` ships, update [`docs/api.md`](./api.md). When the public dev-API ships, add a `/developers` section to [`README.md`](../README.md). When this timeline gets stale, edit it.

---

## Recently shipped (last two cycles, 2026-04-26 → 2026-05-03)

For context on what just landed, so this doc reads against a known baseline.

### Cycle 2026-05-01 → 2026-05-03

- **Search perf lift + speech-detail rebuild + graph-view exploration** (2026-05-03, bulk commit `1df626f`). Three workstreams that landed together: (a) **API perf** — pg pool 10 → 30 (25/25 burst test, was 13/25), query-embedding LRU (60s/500), result-cache LRU in `useSpeechSearch`, `include_count` split off the hot path, `source_system` denorm; (b) **Search exploration UI** — `anchor_chunk_id` parameter on `/search/speeches` re-centres the ranking on a specific chunk, surfaced in the UI by the new `AnchorChunkBanner` and `SearchMapView` (radial graph of top-K results, click a satellite to make it the new anchor); (c) **Speech-detail rebuild** — new `SpeechDetailPage` with `ExchangeSpeechRow` (back-and-forth turn rendering), `RelatedSpeechesPanel` (list + graph modes), `QuoteShareMenu`, `MapleLeafLoader`, plus helper libs `speechHelpers` / `textHighlight` / `videoEmbedUrl`. Edge: nginx switched to variable-based `proxy_pass` with Docker embedded DNS resolver (kills the ~30s 502 window on `docker compose up -d --build api`); `/docs/` root-anchored in `.gitignore` as the durable fix for the runbook accidental-add issue. Runbook trail: [`runbooks/handoff-2026-04-27-semantic-explore-graph-redesign.md`](./runbooks/handoff-2026-04-27-semantic-explore-graph-redesign.md), [`runbooks/handoff-2026-05-02-search-efficiency-and-laptop-capacity.md`](./runbooks/handoff-2026-05-02-search-efficiency-and-laptop-capacity.md).
- **Provincial historical bills — workstream complete.** `--all-sessions` walker pattern propagated to ON (2026-05-01: 111 → 3,412 across P36-P44), then MB + QC (2026-05-02: 81 → 1,971 across 31 MB sessions; 497 → 1,192 across 8 QC sessions via new `discover_qc_bills_html` against assnat.qc.ca historical session pages). All three provinces flipped `bills_status='live'`. QC joins federal/AB/BC/NS/ON with all three legislative columns at live. Commits `8d39fb7` (ON), `11be12d` (MB+QC).
- **Federal vote→bill linkage 10.2% → 54.7%** (2026-05-01) via new `relink-federal-votes` Click subcommand — pure-SQL UPDATE pass against `votes.raw->'openparliament_vote'->>'bill_url'`. 1,993 newly linked, 0 unmatched. Avoided re-fetching 1.45M ballots. Commit `3a90893`.
- **ON / QC bills `introduced_date`** (2026-05-01) — ON parser-side patch derives from /status sub-page first_reading events, hits 100% on P42-P44 (786/786). QC partial via RSS-window roll-up. Older parliaments need separate work — documented gap. Commit `3a90893`.
- **`bills_status` auto-derivation** (2026-04-30) — `coverage_stats.py` now flips all three legislative status columns (hansard / votes / bills) from row counts. 500-row threshold for 'live'. Five overstated jurisdictions honestly downgraded; federal first to flip all-three-live, NS from stale 'partial' to 'live'. Commit `bdc791f`.
- **Federal historical bills backfill** (2026-04-30) — `ingest-federal-bills --all-sessions` walks every federal session in `legislative_sessions`. 412 → **5,542** bills across P37-S1 → P44-S1 (openparliament.ca coverage floor at 2001). Sponsor FK rate 86.5%. Same commit as auto-derive (`bdc791f`).

### Cycle 2026-04-26 → 2026-04-30

- **Provincial votes extractors — 8 jurisdictions live** — one self-contained module per province (`bc_votes.py`, `ab_votes.py`, `qc_votes.py`, `on_votes.py`, `mb_votes.py`, `ns_votes.py`, `nl_votes.py`, `nb_votes.py`); **7,303 provincial votes added** (QC dominant at 2,961 with 1,840 numerical divisions). Schema validated against every `vote_type` value (division/consensus/acclamation). Runbook: [`runbooks/handoff-2026-04-30-provincial-votes.md`](./runbooks/handoff-2026-04-30-provincial-votes.md) (2026-04-30).
- **Federal votes extractor live + full historical backfill complete** — openparliament.ca structured-JSON pipeline; **4,481 divisions / 1.45M vote_positions / 18.5 years (2006-05 → 2024-12) / 99.98% politician-FK** via `openparliament_slug` exact match (the cleanest votes pipeline in the project). Daily 11:30 UTC schedule slot. Runbook: [`runbooks/handoff-2026-04-30-federal-votes.md`](./runbooks/handoff-2026-04-30-federal-votes.md) (2026-04-30).
- **Migration 0018 votes applied + NT votes extractor live** — closes the project's longest-parked migration. NT consensus-government data validates the schema without revisions; 31 consensus votes across 2013-2026 NT Hansard corpus, all `vote_type='consensus'` with NULL ayes/nays (NT doesn't publish per-member positions). Daily 21:50 UTC NT votes-extraction schedule slot. Runbook: [`runbooks/handoff-2026-04-30-votes-layer.md`](./runbooks/handoff-2026-04-30-votes-layer.md) (2026-04-30).
- **NT Hansard pipeline live** — Drupal HTML scrape of ntlegislativeassembly.ca with per-turn `<a href="/meet-members/mla/{slug}">` direct slug-FK speaker attribution (the cleanest pattern of any sub-national pipeline so far). 19 current MLAs slug-stamped + 117 former MLAs inserted; 13th-20th Assembly Speaker roster seeded into `presiding_officer_resolver`. Migration 0041 added `nt_mla_slug` to politicians (CLAUDE.md convention #1). Daily 21:30 UTC schedule slot. Runbook: [`runbooks/handoff-2026-04-29-nt-hansard.md`](./runbooks/handoff-2026-04-29-nt-hansard.md) (2026-04-29).
- **BC pre-P35 historical roster + dated resolver + extended Speaker roster** — Wikipedia per-parliament wikitable parser ingested 160 pre-1992 MLAs across P29-P34 + 359 per-parliament term rows; new `resolve-bc-speakers-dated` CTE with inline surname extraction; `SPEAKER_ROSTER["BC"]` extended back from P38 to P29 (+13 historical Speakers). BC corpus attribution lift: 67.6% → 91.9% (+136K speeches, +20K Speaker-tagged, +186K chunks). Runbook: [`runbooks/handoff-2026-04-29-bc-pre-p35-roster.md`](./runbooks/handoff-2026-04-29-bc-pre-p35-roster.md) (2026-04-29).
- **TEI + scanner-side embed resilience layer** — device-aware TEI healthcheck (single-token /embed, fails on CPU fallback), restart-on-failure cap, preflight inference-latency check, per-batch exponential backoff, abort-on-5-consecutive-failures guard. Closes the GPU-regression silent-CPU-fallback gap. (2026-04-28)
- **`chunk-and-embed-speeches` daily schedule** — single combined Click command + `scanner_schedules` row at 08:00 UTC (02:00 Mountain), atomic chunk → embed ordering in one process. (2026-04-29)
- **BC + QC historical-roster backfills** — QC alphabet-walk of assnat.qc.ca (2,090 career spans extracted; migration 0038 promoted `qc_assnat_id` to UNIQUE partial after merging an Open North Éric/Eric Girard duplicate); BC `enrich-bc-member-parliaments` (LIMS GraphQL `allMemberParliaments`, 750 edges, BC terms 103 → 853). QC P39-P42 +12-33% on resolution. (2026-04-27)
- **BC pre-P38 Hansard parser** — era-branching `bc_hansard_parse.py` extension for legacy ALL-CAPS (P29-P34) + mixed-case (P36-P37) markup. +378K BC speeches; corpus ~198K → ~577K. (2026-04-27)
- **ON historical MPP roster + pre-2007 Hansard parser** — propagated date-windowed-resolver pattern to ON. (2026-04-26)

### Cycle 2026-04-23 → 2026-04-26

- **Phase 1b — premium reports** — `report_jobs` table (migration 0035), `reports-worker` compose service, OpenRouter map-reduce, sanitised-HTML viewer at `/reports/<id>`, refund flow (released-hold vs compensating admin-credit), admin triage queue. First credit-spending feature.
- **Phase 1c #1 — public-share + citation** — `is_public` flag (migration 0036), `/public/reports/<id>` route, citation block in viewer footer (2026-04-24).
- **ON Hansard pipeline** — name-based resolution + parens-name extraction; six ON commands packed into the 18:00 UTC daily-ingest slot (2026-04-24).
- **`/api/v1/search` filter expansion** — `min_similarity`, `parliament_number + session_number`, and `speech_type` filters on `baseFilterSchema`; new `/search/sessions` endpoint backing the cascading parliament/session dropdown; advanced-filters disclosure on `/search` (2026-04-26).
- **Operational hygiene** — `OPENROUTER_MODEL` → `OPENROUTER_CONTRADICTIONS_MODEL` rename with legacy fallback + boot-time deprecation warning; `scripts/backup-database.sh` hardened (`.env`-sourced knobs, file-pinned `DB_PASSWORD`, zstd default 19 → 3); BetaBadge in the site header; `docs/api.md` Search section finally written (2026-04-26).
- **Stripe Tax wiring** — `STRIPE_TAX_ENABLED` env flag, `automatic_tax` + address collection + `tax_id_collection` on the Checkout Session when on, `tax_enabled` field on `/me/credits/packs`, frontend disclosure on `/account/credits`, plan-doc + operations.md activation checklist. Default off — operator dashboard activation (Stripe Tax + Canadian registration + per-product tax codes) is the remaining deploy step (2026-04-26).

