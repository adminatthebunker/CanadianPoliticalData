# CLAUDE.md — SovereignWatch / Canadian Political Data

Project-level instructions for any AI agent working in this repo. Read before writing code.

This file describes how the codebase is *shaped*, not its day-to-day state. For current row counts, ingestion coverage, or what's shipped, query the DB or read the docs it points at — don't trust numbers in this file.

## One-line purpose

**SovereignWatch** is the internal / codebase name. **Canadian Political Data** (domain: `canadianpoliticaldata.ca`) is the public-facing brand — use CPD in blog posts, LinkedIn, external copy, commit messages, migrations, and internal docs.

Project goal: **the definitive source of Canadian political data** — who represents whom, what they've said, how they've voted, where their infrastructure lives. See `docs/goals.md` for the full product framing. It is **not apolitical**; it takes progressive and democratic stances rooted in access-to-information principles.

## Architectural docs — read in this order

1. `docs/goals.md` — north star, audience, non-goals
2. `docs/timeline.md` — current direction in horizons (Now / Next / Later) + the four standing priorities, in order
3. `docs/gotchas.md` — codebase-wide guardrails distilled from past incidents. Every "do not X" rule lives here with rule + why + how to apply. Read before any non-trivial change.
4. `docs/plans/semantic-layer.md` — schema, vector store, embedding plan, phased rollout
5. `docs/research/` — one self-contained research dossier per jurisdiction (federal + 13 provinces/territories), plus `overview.md` for cross-cutting schema log, probe hierarchy, research-handoff protocol, and known blockers
6. `docs/architecture.md` — service-by-service runtime architecture
7. `docs/scanner.md`, `docs/api.md`, `docs/operations.md` — per-component references

`docs/` is **internal-facing** — agent / operator notes, freely candid about gaps, blockers, and in-progress decisions. The **public documentation site** lives separately at `mkdocs/docs/` (rendered by MkDocs Material, served by nginx at `docs.canadianpoliticaldata.ca`). When you need to communicate with end users — explain a feature, document the public dataset, write up the local-install flow — edit `mkdocs/docs/`, not `docs/`.

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
  - **GPU resilience.** TEI carries a device-aware healthcheck (single-token /embed with `--max-time 1` — fails on CPU fallback) and `restart: on-failure:5` so a wedged-driver loop terminates instead of bouncing forever on CPU. The scanner-side embed client adds three layers: a preflight inference-latency check that refuses to start if TEI is on CPU, exponential-backoff retry per batch (5 attempts, 1s→16s — sized to absorb one TEI panic+restart), and an abort-on-5-consecutive-batch-failures guard so a dead TEI doesn't silently grind through the rest of the corpus marking everything `errors`. See `services/scanner/src/legislative/speech_embedder.py` and the 2026-04-28 runbook for the incident that motivated all three.
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

## Admin panel

Private `/admin` surface that lets the operator queue scanner jobs, set cron schedules, and watch a stats dashboard. Read-only public site is unaffected.

### Auth

Admin access is the user-session flow with a DB role flag: **signed-in user with `users.is_admin = true`**. No shared bearer token, no localStorage-held credential. An admin signs in via the same magic-link flow end-users use; the per-request `requireAdmin` preHandler (in `services/api/src/middleware/user-auth.ts`) does `requireUser` + re-reads `is_admin` from the DB each time, so a `UPDATE users SET is_admin = false` takes effect on the next request (not on next session expiry). Mutating admin routes additionally require the double-submit CSRF token.

Promote / demote an account via psql:

```sql
UPDATE users SET is_admin = true  WHERE email = 'you@example.com';
UPDATE users SET is_admin = false WHERE email = 'you@example.com';
```

If no user has `is_admin = true` the admin surface is simply unreachable (403 for any signed-in non-admin, login redirect for anonymous).

### Execution pipeline

1. UI `POST /api/v1/admin/jobs` → row in `scanner_jobs` (`status='queued'`).
2. `sw-scanner-jobs` daemon polls every `JOBS_POLL_INTERVAL` seconds, claims the next row via `UPDATE … FOR UPDATE SKIP LOCKED`.
3. Spawns `python -m src <cli> [flags]` as subprocess (same scanner image), captures last 4 KB of stdout/stderr into `stdout_tail` / `stderr_tail`.
4. Flips status to `succeeded` / `failed` with `exit_code` and `finished_at`.

Schedules table (`scanner_schedules`) is expanded by the same worker — enabled rows whose `next_run_at <= now()` enqueue a new job, then `next_run_at` is advanced via `croniter`.

**Daily-ingest schedule** is defined idempotently by `scripts/seed-daily-ingest-schedules.sql` — re-run the script to update; `created_by='daily-ingest-rollout'` scopes the seed's row ownership. Auto-current-session resolution in `services/scanner/src/legislative/current_session.py` reads the latest `(parliament_number, session_number)` from `legislative_sessions` for each jurisdiction, so schedule rows pass empty `args={}` and don't break at prorogation. Scheduled bills ingest always precedes Hansard in each jurisdiction's chain so the legislative_sessions row is fresh before Hansard tries to attribute speeches.

### Curated command whitelist

The admin UI exposes a subset of scanner commands. The catalog lives in **two places that must stay in sync**:

- `services/scanner/src/jobs_catalog.py` (authoritative for the worker, maps `key` → `{cli, args}`)
- The `COMMAND_CATALOG` constant near the top of `services/api/src/routes/admin.ts` (served to the frontend form generator verbatim)

If they diverge the worker refuses the command with `unknown command` — the UI will show the stale option, but nothing unsafe runs. When adding a command, update both.

### Files involved

| Concern | Path |
|---|---|
| Queue + schedule schema | `db/migrations/0022_scanner_jobs_and_schedules.sql` |
| `is_admin` column + seed | `db/migrations/0029_users_is_admin.sql` |
| Worker daemon | `services/scanner/src/jobs_worker.py` + `jobs_catalog.py` |
| `requireAdmin` preHandler | `services/api/src/middleware/user-auth.ts` |
| API routes | `services/api/src/routes/admin.ts` |
| Frontend admin shell (gates on `useUserAuth().user.is_admin`) | `services/frontend/src/components/AdminLayout.tsx` |
| Frontend pages | `services/frontend/src/pages/admin/*.tsx` |
| Command form generator | `services/frontend/src/components/CommandForm.tsx` |
| Compose service | `scanner-jobs` in `docker-compose.yml` |

### What not to do

See `docs/gotchas.md` § Admin panel & job queue (admin nav, docker.sock, command whitelist) and § Auth & sessions (`is_admin` JWT, self-promotion route).

## User accounts

Public passwordless auth surface. The admin panel piggybacks on this flow via the `users.is_admin` flag — there is only one session system.

### Auth model

Magic-link only (no passwords). Email → one-time nonce → httpOnly `sw_session` JWT cookie + non-httpOnly `sw_csrf` cookie (double-submit CSRF on mutating routes). 30-day session TTL. Rotating `JWT_SECRET` is the phase-1 "force logout everyone" button.

The `services/api/src/lib/auth-token.ts` module is the designated IdP-swap seam: `signSessionToken()` / `verifySessionToken()` today emit/verify HS256 JWTs; a future Keycloak/Zitadel/Logto swap replaces those two functions with a JWKS verifier and every route that calls `requireUser` keeps working. Keep the swap surface *there* — do not spread JWT parsing across route handlers.

### Env vars (feature-disabled ergonomics)

| Var | Purpose | Unset behaviour |
|---|---|---|
| `JWT_SECRET` | HS256 session-cookie signing key. `openssl rand -hex 32`. | `/api/v1/auth/*` + `/api/v1/me/*` return **503**. |
| `SMTP_HOST` / `SMTP_PORT` | Proton submission (`smtp.protonmail.ch:587`). | Defaults applied. |
| `SMTP_USERNAME` / `SMTP_PASSWORD` | Proton per-address submission token. | Emails logged to server stdout instead of sent (dev-stub mode). Auth flow still returns 202 so local smoke-tests work. |
| `SMTP_FROM` | Friendly `From:` header. | As above. |
| `PUBLIC_SITE_URL` | Used to build magic-link + digest URLs. | Defaults to `http://localhost:5173`. |

### Execution pipeline

1. User submits email on `/login` → `POST /api/v1/auth/request-link`. Rate-limited 5/hr/IP + 3/hr/email.
2. API generates a 256-bit nonce, stores SHA-256 hash in `login_tokens` (15-min TTL), emails the plaintext nonce in a link. **Plaintext nonce is never stored.** DB leak cannot leak working links.
3. User clicks link → `/auth/verify?token=…` → `POST /api/v1/auth/verify`. API redeems token (marks `consumed_at`, no re-use), upserts `users` row, mints JWT, sets session + CSRF cookies.
4. `/api/v1/me/*` routes use `requireUser` preHandler. Mutating routes additionally require `X-CSRF-Token: <value>` matching the `sw_csrf` cookie.

### Saved searches

`saved_searches` stores `filter_payload` (the same struct `/search/speeches` validates) plus a cached `query_embedding VECTOR(1024)` computed once at save time from TEI. The alerts worker reads the cached vector directly — **TEI is never called by the worker.**

The create-endpoint reuses `baseFilterSchema` exported from `services/api/src/routes/search.ts` — single source of truth for "what's a valid search." Do not fork the shape.

### Alerts worker

Separate compose service `alerts-worker` (Python, same scanner image). Poll interval `ALERTS_POLL_INTERVAL` (default 300s). Every tick: fetch `saved_searches` due by cadence (`alert_cadence != 'none'` and `last_checked_at` older than the cadence), re-run the HNSW query constrained to `spoken_at > last_checked_at`, send digest if matches, advance watermarks. Digest renders both text/plain and text/html.

### Files involved

| Concern | Path |
|---|---|
| Migration | `db/migrations/0027_users_and_saved_searches.sql` |
| Token sign/verify (IdP-swap seam) | `services/api/src/lib/auth-token.ts` |
| Email adapter (nodemailer SMTP) | `services/api/src/lib/email.ts` |
| CSRF double-submit helper | `services/api/src/lib/csrf.ts` |
| User-auth preHandlers | `services/api/src/middleware/user-auth.ts` |
| Auth routes | `services/api/src/routes/auth.ts` |
| `/me` routes + saved-searches CRUD | `services/api/src/routes/me.ts` |
| Frontend auth hook | `services/frontend/src/hooks/useUserAuth.ts` |
| Frontend pages | `LoginPage`, `VerifyPage`, `AccountPage`, `SavedSearchesPage` under `services/frontend/src/pages/` |
| `SaveSearchButton` (in `/search`) | `services/frontend/src/components/SaveSearchButton.tsx` |
| Header sign-in indicator | `AuthIndicator` in `services/frontend/src/components/Layout.tsx` |
| User-auth CSS | `services/frontend/src/styles/user-auth.css` |
| Alerts worker + digest renderer | `services/scanner/src/alerts_worker.py` |
| Alerts compose service | `alerts-worker` in `docker-compose.yml` |

### What not to do

See `docs/gotchas.md` § Auth & sessions (CSRF, plaintext nonces, cookie logging, social login, Keycloak) and § Embeddings & vector storage (TEI from alerts worker).

### The ledger discipline (do not break)

Credit balance is **always derived** from `SUM(delta) WHERE state IN ('committed','held')`. There is no mutable `balance` column anywhere in the system and there never should be. A hold debits visible spendable balance (negative delta, state `held`); on report success the same row flips to `committed`; on failure to `refunded` (drops out of the sum). One row per economic event.

Idempotency is **two-layer** by design:
- `stripe_webhook_events.id PK` catches duplicate webhook *deliveries* at the door.
- `uniq_credit_ledger_kind_ref` (partial unique index on `(kind, reference_id)`) catches duplicate *application* of the same Stripe event to a user's ledger. If the upstream layer ever fails open, the downstream layer still holds.

### Graceful-degrade ergonomics

Same pattern as `JWT_SECRET` / `OPENROUTER_API_KEY`: with `STRIPE_SECRET_KEY` unset the buy-credits UI hides its purchase buttons, the webhook returns 200-discard, and zero payment surface is exposed. Stripe enablement is a separate, smaller deploy.

### Stripe Tax (Canadian GST/HST/PST)

`STRIPE_TAX_ENABLED=true` is a **runtime opt-in** that mirrors the dashboard Tax-activation switch — Stripe Tax requires both. The code path in `services/api/src/lib/stripe.ts:createCheckoutSession` adds `automatic_tax: { enabled: true }` + `billing_address_collection: 'required'` + `customer_update: { address: 'auto', name: 'auto' }` + `tax_id_collection: { enabled: true }` only when this flag is set. Default off → the existing checkout path is unchanged.

`GET /me/credits/packs` returns `tax_enabled: boolean` so the credits page can render an "applicable Canadian sales tax will be calculated at checkout" disclosure when on. `credit_purchases.amount_cents` records `session.amount_total` (gross of tax); the breakdown is preserved in `raw_webhook.session.total_details.amount_tax`. **Do not flip the flag without first activating Stripe Tax + adding a Canadian tax registration in the dashboard** — checkout will 400 otherwise. Full activation checklist in `docs/operations.md` § Stripe Tax.

### Webhook security — non-negotiable invariants

- Verify the Stripe signature **before any DB write**.
- The credit amount granted **must** come from the server-side `PACK_CREDITS` catalog keyed on `metadata.sku`. **Never** trust `metadata.credits` — Stripe Dashboard admins can edit session metadata before payment, and the signature is computed after that edit. A mismatch between the two is logged as a potential-tamper signal; the catalog value wins.
- Fail-closed when the webhook secret is unset. Plugin-scoped raw-body parser ensures signature verification isn't broken by Fastify's default JSON re-serialisation.

### Admin comp flow

Admins can grant credits directly via `POST /admin/users/:id/grant-credits` (hard-capped at 100,000 per call, zod-checked positive integers only). The grant produces a normal `credit_ledger` row with `kind='admin_credit'` and `created_by_admin_id` set — no parallel "free credits" system exists. Same audit discipline as `is_admin`: psql-only promotion, flipping the flag takes effect on the next request via `requireAdmin`'s per-request re-read.

### Correction-reward flow

Corrections that reach `status='applied'` grant `CORRECTION_REWARD_CREDITS` (default 10, tune via env) to the submitter via `grantCorrectionReward` in `services/api/src/lib/credits.ts`. The grant is a normal ledger row with `kind='correction_reward'` and `reference_id=correction_submissions.id`. The `uniq_credit_ledger_kind_ref` partial unique index makes re-applies idempotent — flipping a correction applied→triaged→applied grants once, not twice. Anonymous corrections (`user_id IS NULL`) skip the grant silently. **No clawback**: once earned, credits stay even if an admin later reverses the status. The PATCH handler wraps UPDATE + ledger-insert in a single transaction so partial grants are impossible; the follow-up email is fire-and-forget after the commit (email failure does NOT roll back the grant).

### Rate-limit tier

`users.rate_limit_tier ∈ ('default','extended','unlimited','suspended')`. `requireUser` re-reads this every request (same DB-read discipline as `requireAdmin`) and 403s `suspended` users immediately. Users can submit an increase request via `POST /me/rate-limit-requests` (one-pending-per-user guard at the app layer); admins resolve in the `/admin/users` queue. Per-day report caps (`REPORTS_RATE_LIMIT_DEFAULT_PER_DAY` / `REPORTS_RATE_LIMIT_EXTENDED_PER_DAY`) are enforced inside `POST /reports`; `unlimited` tier bypasses the cap entirely.

### Report generation

A queued `report_jobs` row debits the user's spendable balance via `holdCredits` (a -delta `held` ledger row); the `reports-worker` Python service polls the table, runs an LLM map-reduce over **every** matching `speech_chunk` for the (politician, query) pair via OpenRouter, persists sanitised HTML on the row, and either `commitHold`s on success (the row flips `held → committed`) or `releaseHold`s on failure (`held → refunded`, balance restored). The user is emailed a "your report is ready" link; the viewer page at `/reports/:id` renders the persisted HTML inside a print-clean standalone layout.

Stale-claim re-queue: a job stuck in `running` past 15 minutes is considered abandoned by a crashed worker and re-queued with the **same** hold still in place. Idempotent state-flip semantics on `commitHold`/`releaseHold` mean re-runs cannot double-debit.

HTML sanitisation discipline: the reduce-step model emits HTML with `CHUNK:<chunk_id>` href tokens. The worker rewrites these to real `/speeches/<speech_id>#chunk-<chunk_id>` paths against the chunk metadata it captured at fetch time, then runs the result through `bleach` (Python) — allowlist of `p / h2 / h3 / ul / ol / li / blockquote / em / strong / a[href]` only, with `a[href]` constrained to internal `/speeches/...` paths. The viewer can `dangerouslySetInnerHTML` because the input is controlled at persist time, not because user content is implicitly safe.

Refund discipline: a refund **before** the worker commits is a state-flip on the `held` row (`releaseHold` path). A refund **after** commit cannot un-commit the row; the admin UI inserts a fresh compensating `admin_credit` row matching the original cost. `POST /admin/reports/:id/refund` picks the right path based on the current ledger state.

### Files involved

| Concern | Path |
|---|---|
| Migration (billing rail) | `db/migrations/0033_billing_rail.sql` |
| Migration (report jobs) | `db/migrations/0035_report_jobs.sql` |
| Stripe SDK wrapper | `services/api/src/lib/stripe.ts` |
| Credit ledger helpers | `services/api/src/lib/credits.ts` |
| Shared OpenRouter client | `services/api/src/lib/openrouter.ts` |
| Report cost / map-reduce / sanitise | `services/api/src/lib/reports.ts` |
| User routes | `services/api/src/routes/credits.ts`, `services/api/src/routes/rate-limit-requests.ts`, `services/api/src/routes/reports.ts` |
| Webhook | `services/api/src/routes/stripe-webhook.ts` |
| Admin additions | `services/api/src/routes/admin.ts` (appended) |
| Suspended enforcement | `services/api/src/middleware/user-auth.ts` (`requireUser`) |
| Reports worker (Python) | `services/scanner/src/reports_worker.py` |
| Frontend user pages | `services/frontend/src/pages/CreditsPage.tsx`, `ReportsListPage.tsx`, `ReportViewerPage.tsx`; balance chip in `AccountPage.tsx` |
| Frontend report button + modal | `services/frontend/src/components/AIFullReportButton.tsx`, `FullReportConfirmModal.tsx` |
| Frontend admin pages | `services/frontend/src/pages/admin/AdminUsers.tsx`, `AdminReports.tsx` |

### What not to do

See `docs/gotchas.md` § Stripe, billing, credits ledger (mutable balance, metadata trust, secrets logging, raw webhook, negative amounts, second integration, Stripe Tax flag, rate-limit guard, correction-reward email, report-hold transaction) and § Reports worker & LLM map-reduce (HTML sanitisation, OpenRouter error mapping, worker→api HTTP).

## Blog (MkDocs Material)

Posts live under `mkdocs/docs/blog/posts/<slug>.md`, rendered by the MkDocs Material blog plugin and served at `docs.canadianpoliticaldata.ca/blog/`. The post-shape, draft workflow, publish checklist, and file map live in the **`blog-post` skill** at `.claude/skills/blog-post/SKILL.md` — that skill auto-loads when you ask to write or publish a post. Guardrails for what doesn't belong in the blog are in `docs/gotchas.md` § Blog & MkDocs.

The migration from React MDX (`services/frontend/src/content/blog/`) happened on 2026-04-27; `/blog` and `/blog/:slug` are now nginx 301 redirects to the docs site, and the redirect regex in `nginx/conf.d/default.conf` depends on the plugin's `post_url_format: "{slug}"` setting in `mkdocs/mkdocs.yml` — don't change one without the other.

## Semantic mind-map / Explore

3D + 2D interactive mind-map of the full Hansard embedding space. Routes: `/semantic-map` (canonical) and `/explore` (alias). The surface is wired end-to-end; the first promoted projection will populate it with data.

### What it does

Runs UMAP dimensionality reduction over all `speech_chunks` embeddings, clusters the result with HDBSCAN at four hierarchical levels (broad → mid → fine → very fine), labels clusters with TF-IDF top-3 terms, and serves the result as a browseable 3D (desktop) or 2D (mobile/touch) map. Users can click into any cluster to see representative speech chunks and drill down to finer levels. Standard Hansard filters (jurisdiction, party, date, language, speech type) dim clusters rather than re-projecting — cluster positions are stable spatial landmarks.

### Run-id + is_current discipline

A full fit/cluster/label cycle is expensive (30–90 min). Results land in a new `projection_runs` row with `is_current = false`. After manual validation, `promote` atomically flips the new run's `is_current = true` and the old run's to `false`. A partial unique index (`idx_projection_runs_current`) enforces at most one current run. The API reads `is_current = true` per-request, so promotion takes effect immediately on the next request — no deploy, no restart.

**Do not add mutable cluster-count, label, or centroid columns to `projection_runs`.** All mutable state lives in the per-run child tables. Immutable run metadata + a single `is_current` boolean is the discipline.

### Pipeline stages

```
project-embeddings --stage=fit       # UMAP-3D + UMAP-2D, transform all chunks
project-embeddings --stage=cluster   # HDBSCAN at 4 levels on 3D coords
project-embeddings --stage=label     # TF-IDF top-3 terms per cluster
project-embeddings --stage=promote   # atomic is_current flip
project-embeddings --stage=gc        # drop runs older than --max-age-days (default 7)
project-embeddings --stage=all       # fit → cluster → label in one pass (does not promote)
```

`--run-id` pins subsequent stages to a specific run. `--sample-size` (default 500k) controls the UMAP fit sample; all chunks are transformed regardless.

### Filtering model

When the user applies filters, the API returns `member_count_filtered` alongside `member_count` per cluster. The frontend fades clusters to ~15% opacity proportional to survival rate; it does **not** re-project. Re-projecting per filter defeats the point — the spatial topology is the stable reference frame.

### API parameter naming

The API uses `cluster_level=1|2|3|4` to mean HDBSCAN hierarchy depth. `level` is already taken by `baseFilterSchema` to mean federal/provincial/municipal. These are **different params**; do not conflate them.

Both read-only routes reuse `baseFilterSchema` and `effectivePoliticianIds` from `services/api/src/routes/search.ts` — single source of truth for valid filter shape.

### Labelling approach

TF-IDF only. No hosted LLM, no OpenRouter call, no per-label generation step. The label for a cluster is the top-3 TF-IDF terms joined by " · " computed over all chunk text in that cluster, with en+fr stopwords stripped. **Do not swap this for a hosted LLM without explicit user sign-off.**

### 3D vs 2D rendering

`useIsTouch()` returns true on phones/tablets → 2D SVG scatter (`ClusterCloud2D`). Desktop → 3D R3F Canvas with `InstancedMesh` + `OrbitControls` (`ClusterCloud3D`). Both consume identical cluster data from `useClusters()`. Do not fork the data model for the two renderers.

### Files involved

| Concern | Path |
|---|---|
| Migration | `db/migrations/0039_speech_chunk_projections.sql` |
| Pipeline (fit/cluster/label/promote/gc) | `services/scanner/src/legislative/projection_builder.py` |
| Click subcommand | `project-embeddings` in `services/scanner/src/__main__.py` |
| API routes | `services/api/src/routes/projections.ts` |
| Route registration | `services/api/src/index.ts` (`/api/v1/projections`) |
| Page | `services/frontend/src/pages/SemanticMapPage.tsx` |
| Route aliases | `/semantic-map` + `/explore` in `services/frontend/src/main.tsx` |
| 2D renderer | `services/frontend/src/components/semantic-map/ClusterCloud2D.tsx` |
| 3D renderer | `services/frontend/src/components/semantic-map/ClusterCloud3D.tsx` |
| Cluster drawer | `services/frontend/src/components/semantic-map/ClusterDrawer.tsx` |
| 2D/3D toggle | `services/frontend/src/components/semantic-map/ModeToggle.tsx` |
| Filter bar | `services/frontend/src/components/semantic-map/SemanticMapFilters.tsx` |
| Data hook | `services/frontend/src/hooks/useSemanticMap.ts` |
| Styles | `services/frontend/src/styles/semantic-map.css` |
| Explore nav link | `services/frontend/src/components/Layout.tsx` + `MobileBottomNav.tsx` |
| Scanner deps | `umap-learn`, `hdbscan`, `scikit-learn`, `numpy` in `services/scanner/requirements.txt` |

### What not to do

See `docs/gotchas.md` § Semantic mind-map / Explore (re-projection, auto-promotion, `cluster_level` vs `level`, hosted-LLM labels, public API surface, frontend→scanner) and § Embeddings & vector storage (parallel vector columns).

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
- `votes` / `vote_positions` — **not yet in the DB.** `0018_votes.sql` is on disk and intentionally unapplied pending real NT/NU consensus-gov't data.
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
