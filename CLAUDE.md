# CLAUDE.md — SovereignWatch / Canadian Political Data

Project-level instructions for any AI agent working in this repo. Read before writing code.

This file describes how the codebase is *shaped*, not its day-to-day state. For current row counts, ingestion coverage, or what's shipped, query the DB or read the docs it points at — don't trust numbers in this file.

## One-line purpose

**SovereignWatch** is the internal / codebase name. **Canadian Political Data** is the public-facing brand — use CPD in blog posts, LinkedIn, external copy, commit messages, migrations, and internal docs.

**Public domain:** the live deploy serves `canadianpoliticaldata.org`. `canadianpoliticaldata.ca` is reserved as a brand-aspiration alias but is **not currently DNS-routed to the host** — anywhere a URL needs to point at the live API, webhooks, or app, use `.org`. The Stripe webhook URL, magic-link emails, dataset autoindex, and `PUBLIC_SITE_URL` env var all live on `.org`. The MkDocs Material public docs site is served at `docs.canadianpoliticaldata.org`. If/when `.ca` gets pointed at the same nginx as a redirect target, this can be revisited.

Project goal: **the definitive source of Canadian political data** — who represents whom, what they've said, how they've voted, where their infrastructure lives. See `docs/goals.md` for the full product framing. It is **not apolitical**; it takes progressive and democratic stances rooted in access-to-information principles.

## Architectural docs — read in this order

1. `docs/goals.md` — north star, audience, non-goals
2. `docs/timeline.md` — current direction in horizons (Now / Next / Later) + the four standing priorities, in order
3. `docs/gotchas.md` — codebase-wide guardrails distilled from past incidents. Every "do not X" rule lives here with rule + why + how to apply. Read before any non-trivial change.
4. `docs/plans/semantic-layer.md` — schema, vector store, embedding plan, phased rollout
5. `docs/research/` — one self-contained research dossier per jurisdiction (federal + 13 provinces/territories), plus `overview.md` for cross-cutting schema log, probe hierarchy, research-handoff protocol, and known blockers
6. `docs/architecture.md` — service-by-service runtime architecture
7. `docs/scanner.md`, `docs/api.md`, `docs/operations.md` — per-component references

`docs/` is **internal-facing** — agent / operator notes, freely candid about gaps, blockers, and in-progress decisions. The **public documentation site** lives separately at `mkdocs/docs/` (rendered by MkDocs Material, served by nginx at `docs.canadianpoliticaldata.org`). When you need to communicate with end users — explain a feature, document the public dataset, write up the local-install flow — edit `mkdocs/docs/`, not `docs/`.

If you find yourself guessing at product direction, the goals doc is the authority. If you find yourself guessing at schema, the semantic-layer doc is the authority. If you find yourself guessing at *what to work on next*, the timeline doc is the authority.

### Priority check on task assignment (do this every time)

When the user assigns a task, before you start work:

1. **Locate the task in `docs/timeline.md`.** Which horizon (Now / Next / Later / Always-on)? Which of the four standing priorities (database / chat / accessibility-incl-voice / UI) does it fall under, if any?
2. **Tell the user where it lands** in one sentence — "this is in the *Next #1 — database* bucket" or "this isn't on the timeline; closest neighbour is *Later — public dev API*."
3. **If the task is below something more urgent on the timeline, say so** and confirm before proceeding. Don't refuse — the user can always reorder priorities — but make the tradeoff visible.
4. **If the task is in scope and on-priority, just go.** One sentence of orientation is the whole ritual.

If the user says "ignore the timeline for this one," that's a valid answer — but they should be the one saying it.

## Stack

- **DB:** Postgres 16 + PostGIS 3.4 + pgvector 0.8.2 + unaccent, built from `db/Dockerfile` (extends `postgis/postgis:16-3.4` with `postgresql-16-pgvector`).
  - Credentials: user `sw`, database `sovereignwatch` (not `sovpro`).
  - Access inside compose: `docker exec sw-db psql -U sw -d sovereignwatch`.
  - Rebuild after Dockerfile edits: `docker compose build db && docker compose up -d db`. `pgdata` volume persists; `init.sql` / `seed.sql` run once on fresh volumes only.
- **API:** Node 20 + Fastify, zod validation, `services/api/`.
- **Frontend:** React 18 + Vite + Leaflet + React Router 6, `services/frontend/`.
- **Scanner:** Python 3.13 + asyncio + Click, `services/scanner/`.
- **Embed service:** HuggingFace **Text Embeddings Inference (TEI)** serving **Qwen3-Embedding-0.6B** (1024-dim, fp16 on GPU). Image `ghcr.io/huggingface/text-embeddings-inference:89-1.9`, compose service `tei`, reachable inside compose at `http://tei:80` (OpenAI-compatible `POST /v1/embeddings` + TEI-native `POST /embed`).
  - The legacy custom FastAPI + FlagEmbedding wrapper (BGE-M3 + reranker) lives on disk at `services/embed/` for rollback only; no compose service references it.
  - **GPU attach:** `deploy.resources.reservations.devices` (driver `nvidia`, capabilities `[gpu]`). `TEI_MEMORY` caps host memory at 6 GiB; VRAM sits well under the RTX 4050's 6 GiB at `--max-batch-tokens=8192` (lowered from 16384 on 2026-04-28 — see § GPU resilience).
  - **Model cache:** `embedmodels` named volume mounted at `/data` (TEI expects HF_HOME-style layout there). First boot pulls ~1.3 GB from HuggingFace; subsequent boots are seconds.
  - **Reranker:** not in the critical path. Qwen3 retrieval quality on multilingual Hansard is strong enough that the cross-encoder rerank stage was removed. If reranking is reintroduced, do it as a separate service — don't resurrect the FlagEmbedding wrapper just for it.
  - **Env the scanner reads:** `EMBED_URL` (default `http://tei:80`), `EMBED_MODEL_TAG` (default `qwen3-embedding-0.6b`, stored in `speech_chunks.embedding_model`), `EMBED_BATCH` (default 32). Resilience knobs: `EMBED_RETRY_MAX_ATTEMPTS` (5), `EMBED_RETRY_BASE_DELAY` (1.0s), `EMBED_MAX_CONSECUTIVE_FAILURES` (5), `EMBED_PREFLIGHT_DEVICE_LATENCY_MS` (1500 — set ≤0 to disable preflight for intentional CPU debug runs).
  - **GPU resilience.** TEI carries a device-aware healthcheck (single-token /embed with `--max-time 1` — fails on CPU fallback) and `restart: unless-stopped` so it comes back after host reboot. (The earlier `on-failure:5` cap was reverted on 2026-05-04 after a reboot left TEI stopped indefinitely — Docker's on-failure policy ignores clean SIGTERM exits, so a graceful shutdown during host shutdown was treated as "not a failure".) The wedged-driver bounce-loop concern that the cap originally guarded against is covered by the device-aware healthcheck above and by the scanner-side embed client, which adds three layers: a preflight inference-latency check that refuses to start if TEI is on CPU, exponential-backoff retry per batch (5 attempts, 1s→16s — sized to absorb one TEI panic+restart), and an abort-on-5-consecutive-batch-failures guard so a dead TEI doesn't silently grind through the rest of the corpus marking everything `errors`. See `services/scanner/src/legislative/speech_embedder.py` and the 2026-04-28 runbook for the incident that motivated those three.
  - **API-side embedding outage handling.** `services/api/src/routes/search.ts` `encodeQuery()` wraps the TEI fetch in a `try/catch` and throws `EmbeddingServiceUnavailableError`; the app-level `setErrorHandler` in `services/api/src/index.ts` maps that class to a stable `503 { code: "embedding_service_unavailable" }` body so search outages are distinguishable from generic 500s on the frontend. No retry on the API side — search is interactive; a 503 + frontend retry-prompt is the right shape (the scanner-side retry layer is for ingest, which is async and idempotent).
- **Orchestration:** Docker Compose, single host, Pangolin tunnel to public.
- **Public edge:** nginx → api / frontend / uptime-kuma.

## Load-bearing conventions (do not break without discussion)

### 1. Jurisdiction-specific ID columns on `politicians`

Every upstream legislature that ships a stable integer or slug ID for its members gets a column on `politicians`:

- Federal: `openparliament_slug`
- Nova Scotia: `nslegislature_slug`
- Ontario: `ola_slug` + `ola_member_id` (int — stable `field_member_id` from ola.org)
- BC: `lims_member_id` (int)
- Quebec: `qc_assnat_id` (int)
- Alberta: `ab_assembly_mid` (zero-padded text)
- Manitoba: `mb_assembly_slug`
- Northwest Territories: `nt_mla_slug` (kebab-case; same slug across `/meet-members/mla/` and `/former-members/` URL paths)

When adding a new jurisdiction, **find and persist its canonical member ID first**. It replaces name-fuzz with exact FK joins and makes sponsor / speaker resolution trivial. Sub-national legislatures with sparse structured rosters drag the global FK ratio on `bill_sponsors` down — closing the gap means adding ID columns for the remaining legislatures, not rewriting the resolver.

### 2. Discriminated tables, not per-jurisdiction tables

One `bills` table, one `speeches` table, one `votes` table — all discriminated by `level` + `province_territory`. Do not create `bills_ab`, `bills_on`, etc.

### 3. Store `raw_html` / `raw_text` alongside parsed fields

Pattern from `bills.raw_html` — persist the upstream artifact, not just the parsed derivative. Re-parsing is cheaper than re-fetching and often the only option under WAFs.

### 4. Probe hierarchy before writing a scraper

Before building any new ingestion pipeline, check in order:

1. **RSS feeds** — `/rss`, `/feed`, `/feed.xml`, `/rss.xml` at the legislative-business root.
2. **Drupal `?_format=json`** — every node on Drupal sites serializes if REST is on (the ola.org / Ontario pattern).
3. **Iframe-backed content servers** — `lims.leg.bc.ca` proxied from `www.leg.bc.ca`-style subdomain splits.
4. **Open GraphQL endpoints** — search the main SPA bundle for `graphql`, `uri:`, `baseURL`.
5. **HTML scrape** — only after 1–4 come up empty.

### 5. Research-handoff rule (user-enforced)

**Before starting any new provincial pipeline, pause and ask the user for their research pass.** No probing, no migration, no code until the user has either shared their findings or explicitly said "probe yourself."

Applies to every provincial pipeline (bills + Hansard) that is not already live. Check `jurisdiction_sources` and `docs/research/<slug>.md` to confirm what's shipped before assuming. Federal Hansard is shipped, so research-handoff is no longer gating federal work.

Rationale: multiple documented cases where user-led research beat agent-driven probing (ON Drupal JSON, BC LIMS JSON). See `docs/research/overview.md`, the per-jurisdiction dossier under `docs/research/<slug>.md`, and `feedback_research_handoff.md` for the full protocol.

### 6. Rate-limit and cache persistently

Log every upstream request by URL + etag. Re-runs should be free. Past WAF incidents have cost thousands of unnecessary re-fetches; don't repeat that.

### 7. Idempotent Click subcommands for ingest

Every ingest command in `services/scanner/src/__main__.py` is idempotent and restartable. New pipelines follow the same shape — `ingest-<source>`, `fetch-<source>-pages`, `parse-<source>-pages`, `resolve-<source>-sponsors` — split by stage so each can be retried independently.

### 8. Privacy boundary: `public` vs `private` schema

User accounts, sessions, payments, corrections, and reports live in the **`private` schema** (migration `0042`); the political dataset (politicians, speeches, bills, votes, projections) lives in `public`. The split is structural so the public dataset can be redistributed without procedural "did we remember to scrub PII" checks.

Tables that move to `private` when added: anything that holds an account, an email, a payment, a session token, a saved query, or user-submitted content. Public-side tables must not gain `user_id` / `created_by_user_id` columns — that bleeds PII back across the boundary.

Application code **always qualifies** `private.X` in SQL. Never alias, never lean on `search_path`. Grep-ability is the safety net: a future migration that puts a user-data table in `public` is caught by the dump-time guardrail in `scripts/make-public-dump.sh`, but the qualification convention is the first line of defence.

The redistributable artifact is produced by `cli/sovpro db public-dump` → `pg_dump --schema=public`. By construction, nothing in `private` can leak into it.

### 9. Public dataset distribution surface

The redistributable dump is published at `https://canadianpoliticaldata.org/datasets/` — nginx autoindex over a read-only bind mount of `/media/bunker-admin/Internal/.../public-dumps/`. Per-IP `limit_conn 2` + `limit_rate 50m` in `nginx/conf.d/default.conf` keep one client (or a viral inbound link) from saturating the home upstream.

The weekly cron (`0 2 * * 0` local) runs `scripts/make-public-dump.sh`, which produces a fresh timestamped dump on disk. The nginx `/datasets/` location is anonymous by design: it's the cheapest path for journalists, researchers, and civic-tech consumers. Auth-gated bulk export is a different, paid concern (the *Later — public dev API* horizon), not this one. Do not collapse the two.

If a third-party mirror (Proton Drive, B2, R2, etc.) is added later, do it as a *manual operator step* or a separate uploader script — not as a coupled stage inside `make-public-dump.sh`. A failing mirror should never delay or fail the canonical self-host artifact.

## Admin panel

Private `/admin` surface that lets the operator queue scanner jobs, set cron schedules, and watch a stats dashboard. Read-only public site is unaffected. Admin access is the user-session flow with a DB role flag (`users.is_admin = true`); see User accounts below for the auth fabric.

Auth detail (per-request `is_admin` re-read), the queue→daemon→subprocess execution pipeline, daily-ingest schedule seeding, the two-place `COMMAND_CATALOG` / `jobs_catalog.py` whitelist, and the file map live in the **`admin-panel` skill** at `.claude/skills/admin-panel/SKILL.md` — that skill auto-loads when you ask about scanner jobs, schedules, or the admin panel. Guardrails: `docs/gotchas.md` § Admin panel & job queue and § Auth & sessions.

## User accounts

Public passwordless auth surface. The admin panel piggybacks on this flow via the `users.is_admin` flag — there is only one session system. Magic-link only (no passwords); httpOnly `sw_session` JWT + double-submit `sw_csrf` cookie. Credit balance is derived from `SUM(delta) WHERE state IN ('committed','held')` — no mutable balance column anywhere, ever.

The auth pipeline (login token → JWT → CSRF), the IdP-swap seam in `auth-token.ts`, saved searches + alerts worker, the ledger discipline + two-layer Stripe-webhook idempotency, Stripe Tax opt-in, admin credit grants, correction rewards, the rate-limit tier, and the report-generation hold/commit/release flow all live in the **`user-accounts` skill** at `.claude/skills/user-accounts/SKILL.md` — auto-loads when you ask about login, sessions, credits, billing, or reports. Guardrails: `docs/gotchas.md` § Auth & sessions, § Stripe/billing/credits ledger, and § Reports worker & LLM map-reduce.

## Public developer API (`/api/public/v1/*`)

Parallel third-party-facing API surface alongside the internal `/api/v1/*`. **11 endpoints across 5 tags** as of 2026-05-12 (phases 1a + 1b + 1c + 1d + 1e all shipped). Bearer-token authenticated via API keys minted at `/account/api-keys` (HMAC-hashed at rest with `API_KEY_PEPPER`). Two orthogonal authorization axes: **tier** (free / dev $20/mo / pro $200/mo, gates rate limits + paid search) and **scope** (`read:public` implicit / `read:bulk` opt-in, gates bulk export). Permissive CORS (`origin: *`) — public surface, bearer-not-cookie auth.

Key files:
- `services/api/src/routes/public/index.ts` — plugin root; CORS + onRequest hook + Swagger.
- `services/api/src/routes/public/search.ts` — 6 search endpoints, pro-tier-gated TEI semaphore via `app.inject` proxy to internal handlers.
- `services/api/src/routes/public/exports.ts` — 2 bulk-export endpoints, `read:bulk`-scoped, file streams from `/srv/datasets` mount.
- `services/api/src/middleware/api-key-auth.ts` — `requireApiKey` / `optionalApiKey`.
- `services/api/src/middleware/api-tier-gate.ts` — `requireTier('dev'|'pro')`.
- `services/api/src/middleware/api-scope-gate.ts` — `requireScope('read:bulk')`.
- `services/api/src/middleware/api-rate-limit.ts` — per-tier rate-limit resolver.
- `services/api/src/lib/api-key-token.ts` — `cpd_<env>_<random>_<checksum>` mint/verify.
- `services/api/src/lib/tei-semaphore.ts` — `withPublicTeiSlot` admission control.

The interactive reference at `/api/public/v1/docs/` (Swagger UI) and the prose guide at `mkdocs/docs/developers/` are the canonical end-user references — derive from those, not from `docs/api.md` § Public API which is the operator-side overview only. Plan + design history: `docs/plans/public-developer-api.md`. Operations: `docs/operations.md` § Public developer API.

## Blog (MkDocs Material)

Posts live under `mkdocs/docs/blog/posts/<slug>.md`, rendered by the MkDocs Material blog plugin and served at `docs.canadianpoliticaldata.org/blog/`. The post-shape, draft workflow, publish checklist, and file map live in the **`blog-post` skill** at `.claude/skills/blog-post/SKILL.md` — that skill auto-loads when you ask to write or publish a post. Guardrails for what doesn't belong in the blog are in `docs/gotchas.md` § Blog & MkDocs.

The migration from React MDX (`services/frontend/src/content/blog/`) happened on 2026-04-27; `/blog` and `/blog/:slug` are now nginx 301 redirects to the docs site, and the redirect regex in `nginx/conf.d/default.conf` depends on the plugin's `post_url_format: "{slug}"` setting in `mkdocs/mkdocs.yml` — don't change one without the other.

## Semantic mind-map / Explore

3D + 2D interactive mind-map of the full Hansard embedding space, served at `/semantic-map` (canonical) and `/explore` (alias). UMAP→HDBSCAN(4 levels)→TF-IDF labels. Filters dim clusters rather than re-projecting — spatial topology is the stable reference frame.

The fit→cluster→label→promote→gc pipeline (Click stages on `project-embeddings`), the run-id + `is_current` promotion discipline, the `cluster_level` vs `level` API param distinction, the 3D-vs-2D renderer split, and the file map live in the **`semantic-map` skill** at `.claude/skills/semantic-map/SKILL.md` — auto-loads when you ask about projection runs, clusters, or the explore page. Guardrails: `docs/gotchas.md` § Semantic mind-map / Explore and § Embeddings & vector storage.

## Scrape monitoring (paid Apify-backed politician monitoring)

User-facing paid feature shipped 2026-05-12: signed-in users subscribe to scheduled scrapes of monitored politicians' social-content (Twitter / Bluesky / Instagram / Mastodon), debited per-refresh from the credit ledger. Three job kinds — **monitoring** (recurring, cadence-driven), **preflight** (one-shot profile probe), **archive** (one-shot volume-priced deep history). **v2** (same day) flipped the visibility gate to public-read once the governance docs (DSAR / takedown / disclaimer at `mkdocs/docs/about/*`) shipped; scraped posts now appear on every politician's profile in a *Recent posts* tab visible to anyone. **v3** (also same day) added sponsorship discoverability + linkable attribution: a CTA banner on the Posts tab routes anon → `/login` with a return URL and signed-in users → the Monitor panel via a `#monitor` hash, the attribution opt-in gained an optional `https://` URL so "Funded by @handle" can render as a clickable link with `rel="nofollow noopener external"`, and admin one-shot scrapes auto-link to the operator anchor saved_search so future runs surface attribution publicly without manual backfill. Subscribers can opt in to public attribution ("Funded by @handle" with optional URL) on their subscription; default is anonymous ("Scraped via paid monitoring").

Billing is the same fabric as the report-worker hold/commit/release pattern, extended with three new `credit_ledger.kind` values (`scrape_hold` / `scrape_commit` / `scrape_refund`). Pricing constants live in `services/api/src/lib/scrape-pricing.ts` (UI-facing estimates) and `services/scanner/src/scrape_worker.py` (worker-side debits) — **the two must stay in sync**; if they drift, displayed estimates and actual debits disagree. Twitter monitoring = 5 cr/refresh, IG = 8, Bluesky = Mastodon = 1; preflight = 1 cr on Apify platforms / free on Bluesky+Mastodon; archive uses a tiered curve against the cached `politician_socials.lifetime_post_count`.

Subscription model: extends `private.saved_searches` with `scrape_platforms[]` / `scrape_cadence` / `scrape_next_run_at` / `scrape_paused_reason` — same row holds both speech-alert cadence and social-scrape cadence. Worker daemon (`sw-scrape-worker` compose service) ticks every `SCRAPE_DISPATCH_INTERVAL=60s`; daily-USD circuit breaker (`SCRAPE_DAILY_USD_CAP=$5`) is platform-level, independent of per-user balance. Local cost floors per platform (Twitter $0.02/run, IG `result_count × $0.0015`) keep the cap accurate when actors report `usageTotalUsd=0` synchronously.

The full subsystem — three job kinds + ledger discipline + pricing constants + dispatcher loop + daily-cap circuit breaker + file map + the v1-subscriber-only visibility gate that's enforced in SQL via `EXISTS (SELECT 1 FROM private.scrape_jobs sj WHERE sj.user_id = $auth)` — lives in the **`scrape-monitoring` skill** at `.claude/skills/scrape-monitoring/SKILL.md`. That skill auto-loads when you ask about scrape jobs, the monitor button, or cadence-driven monitoring. Plan + design history: `~/.claude/plans/okay-lets-do-purring-hearth.md`. Per-jurisdiction handle data lives on `politician_socials` (with cached `lifetime_post_count` / `follower_count` / `last_profile_check_at` for the cost calculator).

## User-facing async jobs

Several user-facing features kick off async work that takes seconds-to-minutes to complete: premium **reports** (`private.report_jobs`, LLM map-reduce, 2–10 min) and **scrape jobs** (`private.scrape_jobs`, Apify probes / archives, seconds–minutes). A persistent viewport-level **`ActiveJobsIndicator`** at `services/frontend/src/components/ActiveJobsIndicator.tsx` (mounted in `Layout.tsx`) renders a fixed-position pill whenever the signed-in user has any of these in flight. It polls each job table's listing endpoint with `?active=true` in parallel, merges the results, and shows the lead item ("Probing X's twitter…" / "Generating stance map: Pierre Poilievre…") with a `+N more` badge if multiple jobs are running.

**Convention for new async job surfaces**:

1. **Backend**: the per-user listing endpoint (`GET /me/<job-kind>`) must support `?active=true` as a shortcut for `status IN ('queued', 'running')`. The shape lives next to existing per-job filters; precedence rule is explicit `?status=` wins. Examples in `services/api/src/routes/me.ts` (`/me/scrape-jobs`) and `services/api/src/routes/reports.ts` (`/me/reports`).
2. **Frontend**: extend `ActiveJobsIndicator`'s `tick()` parallel fetch with the new endpoint, add a `*-to-active` mapper that emits `{ kind, id, label, href, created_at }`. The merge sorts by `created_at DESC` so the most-recently-started job leads. New job kinds get a new `ActiveJob.kind` string literal.
3. **Polling discipline**: 3.5s cadence when ≥1 active, 25s when idle, suspended while tab hidden (Page Visibility API). Don't add new polling loops outside the indicator's `tick()` — the merge in one place is the convention.
4. **DB-driven, not React state**: the indicator reads from listing endpoints, not from local state set by job-triggering components. This is what lets the indicator survive page reloads, cross-tab activity, and out-of-band probe triggers (e.g. CLI / cron / another tab).

Skipping the convention is what causes "did my job actually start?" support tickets. Anytime you add a new long-running per-user job table, also extend the indicator.

## Headless Claude Code scheduled tasks

Some maintenance work is best done by a Claude Code session itself — web research, evidence-weighing, narrative reporting — rather than a deterministic Python script. The first instance is **daily socials enrichment** (`scripts/scheduled-tasks/run-socials-weekly.sh`, fires at 09:07 local via OS cron): a `claude -p` invocation that targets the top-25 actively-sitting politicians with missing handles, web-searches each, inserts evidence-scored rows into `politician_socials` with `source='claude-code-agent'`, runs `verify-socials`, writes a runbook, and emails a one-paragraph summary to admin via the project's Proton SMTP creds.

This is the **subscription-billed** counterpart to the API-billed `agent-missing-socials` Click command in `services/scanner/src/__main__.py`. Same kind of work; different billing. See `docs/operations.md` § *Daily socials enrichment* for the full runbook (cron line, prompt edit workflow, revert SQL, failure modes).

Pattern for adding more headless-Code scheduled tasks:

1. **Prompt body** lives at `scripts/scheduled-tasks/<task>.md` (version-controlled). It must be self-contained — the scheduled session starts cold with no chat history. Include DB credentials, target SQL, decision rubrics, and explicit safety rails ("never UPDATE/DELETE existing rows", "never git commit", "stop on error", "search budget cap").
2. **Wrapper bash script** at `scripts/scheduled-tasks/run-<task>.sh` strips frontmatter from the prompt file, sets cron-safe `PATH`, invokes `claude -p --model sonnet --permission-mode acceptEdits --add-dir /home/bunker-admin/sovpro`, captures the exit code, calls `send-run-summary.py` to email a summary, prunes old logs.
3. **Source tag on inserts** is the audit primitive — `source='claude-code-agent'` for the socials task; pick a distinct value per task. Lets the operator SQL-revert a whole batch with `DELETE FROM <table> WHERE source = '<tag>'`.
4. **OS cron line** runs as the `bunker-admin` user, at an off-:00 minute (the existing fleet picks `:07`).
5. **Email summary helper** at `scripts/scheduled-tasks/send-run-summary.py` is reusable — it reads any log file, extracts everything after the agent's `<task> complete` signal line, sends via the existing SMTP creds. Have new tasks emit a matching signal line so the helper picks it up.

Guardrails specific to this pattern: never give `--dangerously-skip-permissions` to a headless session that touches more than the public schema or `docs/runbooks/`. `acceptEdits` is the right ceiling — it auto-approves file edits and `docker exec`-style commands but still gates network-altering / destructive operations. If a headless task needs `private` schema write access for any reason, that's a discussion before shipping.

## Database reference

For current row counts, ingestion coverage, or what's shipped: query the DB or read `jurisdiction_sources`. Don't trust counts in this file.

### Core tables

- `politicians` — per-jurisdiction slug columns (see convention #1).
- `politician_terms` — role / party / level / constituency over time.
- `politician_socials` — platform handles, no content.
- `politician_committees`, `politician_offices` — supporting detail.
- `politician_changes` — audit trail of mutations to the politicians table.
- `organizations` — referendum orgs, advocacy, media.
- `websites`, `infrastructure_scans`, `scan_changes` — the hosting-sovereignty layer.
- `constituency_boundaries` — temporal (`effective_from` / `effective_to`).

### Legislative tables

- `legislative_sessions` — jurisdiction + parliament + session.
- `bills` / `bill_events` / `bill_sponsors` — discriminated by `level` + `province_territory`. FK to `politicians` via the per-jurisdiction ID column when available.
- `speeches` / `speech_chunks` / `speech_references` — Hansard text, chunked and embedded with Qwen3-Embedding-0.6B vectors in `speech_chunks.embedding` (`vector(1024)`, HNSW index `idx_chunks_embedding`).
- `votes` / `vote_positions` — **live across federal + 8 provinces + NT** (migration 0018 applied 2026-04-30). One extractor module per jurisdiction in `services/scanner/src/legislative/{prov}_votes.py`: federal via openparliament.ca structured JSON (100% pol-FK, populated tallies + 1.45M vote_positions); NT/AB/MB/ON/NS/NL/NB via Hansard-text regex (consensus-shape, no vote_positions); BC/QC via Hansard-text regex (mixed division + consensus, with QC's `Pour:N/Contre:N` numerical tallies). 11,784 total votes / 335 MB. Committee transcripts still pending.
- `jurisdiction_sources` — coverage + blockers (one row per jurisdiction). Feeds the public coverage dashboard. Refreshed by `refresh-coverage-stats` scanner command. **Check this before assuming a data source is live.**
- `correction_submissions` — corrections inbox (web + email sources).
- `scanner_jobs` / `scanner_schedules` — admin queue + cron (see Admin panel section).
- `projection_runs` / `speech_clusters` / `speech_chunk_projections` — semantic mind-map derived layer (migration `0039`). `projection_runs.is_current` partial unique index ensures at most one live run. Coords are derived from `speech_chunks.embedding`; do not treat them as canonical embeddings.

### Embedding column naming

`speech_chunks` has a single vector column named `embedding` (plus `embedding_model` / `embedded_at`). One canonical column, one HNSW index. Do **not** introduce `_next` suffixes or parallel vector columns for re-embed work — a previous blue-green column was renamed back and dropped, and recreating it would re-introduce the same coordination cost.

### Materialized views

- `map_politicians` / `map_organizations` — refreshed via `SELECT refresh_map_views()` after scan batches.

## Migrations

Numbered sequentially under `db/migrations/`. No automated runner — apply manually with:

```bash
docker exec -i sw-db psql -U sw -d sovereignwatch -v ON_ERROR_STOP=1 < db/migrations/<file>.sql
```

Rules:
- **Forward-only.** Bump the next number; don't edit an applied migration.
- **One file per number, normally.** History contains one accidental `0026_*` collision (two files share the number, both applied). When you write the next migration, bump past the highest number on disk; do not back-renumber to fill gaps.
- **Read the file before relying on it.** `docs/plans/semantic-layer.md` carries the rationale for any migration that intentionally hasn't shipped (notably `0018_votes.sql`).

## Command reference

Operator CLI lives at `cli/sovpro` (bash wrapper over `docker compose`).

```bash
sovpro up                 # docker compose up -d --build
sovpro logs <service>     # tail a service
sovpro db psql            # interactive psql as sw on sovereignwatch
sovpro db backup          # writes backups/<timestamp>.sql.gz
sovpro ingest all         # seed-orgs + ingest-mps + ingest-mlas + ingest-councils + ingest-ab-extras
sovpro scan full          # scan --stale-hours 0 (re-scan everything, ignore staleness)
sovpro doctor             # sanity-check all services
docker compose run --rm scanner python -m src <subcommand>
```

The Click entrypoint is `python -m src` (module is `src`, not `scanner` — the compose mount is `./services/scanner/src:/app/src`). Every Click subcommand is in `services/scanner/src/__main__.py`. Grep there for the full list.

## Development workflow

1. **Read the relevant plan doc first.** Skip and you'll end up rebuilding what's already there.
2. **Check `jurisdiction_sources` / the research doc** before assuming a data source is live.
3. **Run locally first** — `sovpro up` + `sovpro db psql` to validate queries before writing API/scanner code.
4. **Migrations are forward-only.** Bump the number, don't edit an applied migration.
5. **Each Click command should log what it did** — bill counts, sponsor resolution rate, HTML cache hits. Ingest without telemetry is unverifiable.
6. **UI changes need a browser check** — run the dev server, hit the actual page. Type-check passes ≠ feature works.
7. **Git identity:** commits are authored by `adminatthebunker <admin@thebunkerops.ca>`.

## Style

- Python: type hints on public functions; asyncio throughout the scanner.
- TypeScript: strict mode, zod for API request/response schemas.
- SQL: lowercase keywords in migrations, UUIDs for primary keys, `NOT NULL` by default, `created_at` / `updated_at` timestamps, `raw JSONB` for source payloads.
- Commit messages: lowercase imperative, component prefix (`feat(frontend):`, `fix(map):`, `infra:`, etc.). See `git log` for examples.

## What not to do

The full guardrail list lives in `docs/gotchas.md` — every "do not X" rule is there with rule + why + how to apply, organised by topic (Auth & sessions, Admin panel & job queue, Database/migrations/schema, Embeddings & vector storage, Stripe/billing/credits ledger, Reports worker & LLM map-reduce, Blog & MkDocs, Semantic mind-map / Explore, Cross-cutting). Read it before any non-trivial change.

## When in doubt

Ask the user. Research-handoff rule is a specific instance of a broader principle: short pauses for alignment beat long rollbacks.
