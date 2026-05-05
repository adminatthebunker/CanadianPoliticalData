# Gotchas

Painful lessons, distilled. Each entry is a rule that came out of a real incident or a deliberate design choice you'd otherwise be tempted to undo.

Read this before any non-trivial change to a listed area. The structure mirrors the per-feature sections in `CLAUDE.md`, so if you're working on auth, jump to the auth section. Each entry says **what** the rule is, **why** it exists, and **how to apply** it.

## Auth & sessions

### Do not bypass CSRF on `/me/*` or `/admin/*` mutations
**Why:** Both surfaces use cookie auth. Without CSRF, any cross-origin POST against an authenticated browser hits the API as the user.
**How to apply:** Every POST/PATCH/DELETE on `/me/*` or `/admin/*` runs `requireCsrf` alongside `requireUser` (or `requireAdmin`). The double-submit token comes from the non-httpOnly `sw_csrf` cookie; clients echo it via `X-CSRF-Token`.

### Do not store plaintext magic-link nonces
**Why:** A DB leak would otherwise leak working login links.
**How to apply:** Only `sha256(nonce)` lives in `login_tokens.token_hash`. The plaintext nonce exists in memory long enough to email it, and never lands in the DB or logs.

### Do not log session cookies or CSRF tokens
**Why:** They're bearer credentials. Logs flow into observability tooling that has a wider trust boundary than the API.
**How to apply:** Fastify's default logger skips `Cookie`. If custom logging is introduced, add explicit redact rules.

### Do not embed `is_admin` in the session JWT
**Why:** Embedding it would mean `UPDATE users SET is_admin = false` only takes effect on next session expiry (up to 30 days). The current per-request DB read makes demotion instant.
**How to apply:** `requireAdmin` re-reads `is_admin` from the DB each request. If admin traffic ever becomes large enough to matter (it won't), cache the lookup with a short TTL — but keep the source of truth in the DB.

### Do not expose a self-promotion route
**Why:** `is_admin` should never be flippable from HTTP. A bug or auth bypass anywhere becomes account takeover.
**How to apply:** Promotion happens via psql only. There is no HTTP endpoint that mutates `is_admin`.

### Do not add social login (Google/Meta/GitHub)
**Why:** Wrong trust model for civic research — leaks user intent (who is researching which politician) to ad platforms.
**How to apply:** Magic-link only. If newsroom SSO becomes a need, reach for Keycloak/Zitadel via the `services/api/src/lib/auth-token.ts` swap seam.

### Do not bump to Keycloak casually
**Why:** Adds operational surface, breakage modes, and an upstream you don't control. The HS256 JWT path is intentionally minimal.
**How to apply:** Revisit only when a concrete need surfaces (partner newsroom SSO, OAuth clients). The `verifyToken` seam in `auth-token.ts` is specifically designed so the swap is mechanical.

## Admin panel & job queue

### Do not link `/admin` from the public nav
**Why:** Reduces drive-by discovery. Admin is gated by `is_admin`, but obscurity is a free additional layer.
**How to apply:** Access is by direct URL only. The frontend admin shell gates render on `useUserAuth().user.is_admin`.

### Do not mount `/var/run/docker.sock` anywhere
**Why:** Mounting the Docker socket is root-equivalent on the host. The job worker doesn't need it.
**How to apply:** The worker spawns scanner subcommands as subprocesses inside its own container (`python -m src <cli>`), not via Docker.

### Do not allow arbitrary commands through the admin job queue
**Why:** The queue runs commands as the scanner image — unrestricted command execution is RCE-equivalent.
**How to apply:** Every admin-submitted command goes through the whitelist in `services/scanner/src/jobs_catalog.py`. `build_cli_args` validates args against a schema before any subprocess spawn. The frontend's `COMMAND_CATALOG` (in `services/api/src/routes/admin.ts`) must stay in sync with the worker's catalog — if they diverge, the worker refuses with `unknown command`.

## Database, migrations, schema

### Do not edit applied migrations
**Why:** No automated runner means you can't trust that "latest applied = latest on disk." Editing in place silently desyncs environments.
**How to apply:** Forward-only — bump the next number and write a new migration. History contains one accidental `0026_*` collision; do not back-renumber to fill gaps.

### Do not adopt OpenCivicData `ocd-person/*` IDs
**Why:** OCD's identifier scheme is built for the US's coverage gaps. The Canadian context has stable per-jurisdiction member IDs upstream; using those keeps joins exact.
**How to apply:** Per-jurisdiction slug/ID columns on `politicians` (see CLAUDE.md convention #1) + `politician_terms` covers the model.

## Embeddings & vector storage

### Do not introduce parallel vector columns on `speech_chunks` for re-embed work
**Why:** A previous blue-green column (`embedding_next`) was renamed back and dropped after the coordination cost (HNSW rebuild, dual-write logic, cutover) outweighed the benefit. Re-introducing it would re-introduce the same coordination cost.
**How to apply:** `embedding` is the canonical Qwen3 column. One column, one HNSW index. For re-embeds, write through the same column.

### Do not call TEI from the alerts worker
**Why:** Re-embedding at alert time scales poorly and can drift from the user's original query (model upgrade between save and alert would change semantics silently).
**How to apply:** The query embedding is cached on `saved_searches.query_embedding` at save time. The worker reads the cached vector directly.

### Do not run `embed-speech-chunks` with TEI on CPU fallback
**Why:** TEI silently degrades to CPU when CUDA init fails (the boot log shows `Using CPU instead`). On Qwen3-0.6B at our `--max-batch-tokens` setting, that is ~30× slower than CUDA; a 251K-chunk job that takes 2 hours on GPU takes 60+ hours on CPU and is indistinguishable from "still working" until you check throughput. On 2026-04-28 a partial CPU run also held the GPU context in a wedged state, blocking eventual recovery.
**How to apply:** The embed client now refuses to start unless single-token inference latency is below `EMBED_PREFLIGHT_DEVICE_LATENCY_MS` (default 1500ms — well above CUDA p99, well below CPU floor). Compose carries a matching healthcheck so the container itself goes `unhealthy` when degraded. Don't disable preflight (`EMBED_PREFLIGHT_DEVICE_LATENCY_MS=0`) except for a small intentional CPU smoke-test, and never on the production embed queue.

### Do not let `embed-speech-chunks` continue past sustained batch failures
**Why:** The pre-2026-04-28 loop caught any per-batch exception and `continue`d. When TEI panicked late in a 251K-chunk run, the loop marched through ~3,000 remaining batches in seconds — every one failing into the void — and exited 0 with no embed but `errors=3000`. We lost 9,526 chunks of progress before noticing. The runbook fingerprint of this failure is dozens of identical "All connection attempts failed" lines in a tight burst.
**How to apply:** The loop now retries each batch with exponential backoff (`EMBED_RETRY_MAX_ATTEMPTS`, `EMBED_RETRY_BASE_DELAY`) and aborts the entire run after `EMBED_MAX_CONSECUTIVE_FAILURES` post-retry batch failures in a row (default 5). The remaining unembedded chunks stay NULL — the next run picks them up — and the operator sees a red `aborted=True` summary line instead of a green-but-empty success.

### Do not bump `TEI_MAX_BATCH_TOKENS` back to 16384 without driver work
**Why:** The 2026-04-28 default lowered the value 16384 → 8192 to reduce per-batch GSP firmware allocation pressure on the `nvidia-driver-580-open` regression that has caused both Xid 62 and `CUDA_ERROR_LAUNCH_FAILED` faults on this hardware. Raising it back without first resolving the driver-side issue (closed-module swap is the runbook's #1 mitigation) re-exposes the same fault path with no resilience buffer beyond the embed-client retry layer.
**How to apply:** Leave `TEI_MAX_BATCH_TOKENS=8192` until after the driver swap (or upstream NVIDIA fix). If raising to test, do it in a single-run env override (`TEI_MAX_BATCH_TOKENS=16384 docker compose up -d tei`) and watch a small-batch job to completion first.

## Stripe, billing, credits ledger

### Do not add a mutable `balance` column on `users`
**Why:** Cached balances diverge under concurrent writes (hold + commit + grant racing) and make refunds incoherent.
**How to apply:** Always derive balance via `SUM(delta) WHERE state IN ('committed','held')`. One row per economic event in `credit_ledger`.

### Do not grant credits from `session.metadata.credits`
**Why:** Stripe Dashboard admins can edit session metadata before payment, and the signature is computed *after* the edit. Signature verification does NOT protect against tampered metadata amounts.
**How to apply:** Always look up via `getPackBySku(metadata.sku)` against the server-side `PACK_CREDITS` catalog. Mismatches between catalog and metadata are logged as a tamper signal; the catalog value wins.

### Do not log Stripe secrets or signature headers
**Why:** `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, and the `stripe-signature` header are bearer credentials.
**How to apply:** The webhook route logs event ids + types only. Failure messages must not include the raw signed body.

### Do not return `credit_purchases.raw_webhook` from any HTTP response
**Why:** It holds the full Stripe event including customer email + payment intent. Audit-only.
**How to apply:** Strip it from any SELECT that flows to the API surface. It stays in the DB.

### Do not accept negative credit amounts in any route
**Why:** A negative grant inverts the ledger semantics; a negative purchase ungrants.
**How to apply:** Zod `z.number().int().positive()` at the route boundary + `<= 0` throw in `services/api/src/lib/credits.ts`.

### Do not build a second Stripe integration
**Why:** One client wrapper = one place to audit, one webhook endpoint, one retry strategy.
**How to apply:** Subscriptions (dev-API plan) reuse `services/api/src/lib/stripe.ts` + `stripe_webhook_events`. One Stripe customer per user.

### Do not flip `STRIPE_TAX_ENABLED=true` without first activating Stripe Tax + adding a Canadian tax registration in the dashboard
**Why:** Stripe rejects every Session that requests `automatic_tax` without an upstream registration. Result: outage on the buy-credits flow.
**How to apply:** Run the full activation checklist in `docs/operations.md` § Stripe Tax — including the test-mode dry-run — before flipping the flag in production.

### Do not flip from test mode to live mode without scrubbing test-mode `users.stripe_customer_id`
**Why:** Stripe customer namespace is per-mode. A `cus_…` created in test mode does not exist in live mode; the live API rejects requests that reference it with `"No such customer: 'cus_…'"`. The frontend sees a generic 502 and the user can't buy credits. Bit me on 2026-05-05 cutover.
**How to apply:** As part of the live-mode swap, run `UPDATE private.users SET stripe_customer_id = NULL WHERE stripe_customer_id IS NOT NULL;` before the first live checkout. `getOrCreateCustomer` mints fresh live-mode customers on next purchase. Stale test-mode customers are abandoned in test mode (harmless, never billable). Documented in `docs/operations.md` § Phase 3 step 6.

### Do not assume the test-mode webhook subscription carries over to live mode
**Why:** Stripe scopes webhook endpoint registrations per-mode (test vs live each have their own list). A webhook registered while the dashboard was toggled to test mode receives test-mode events only — live-mode events have no destination, so the buy succeeds, no credit lands, and the failure is invisible from the user's perspective (success-redirect doesn't carry payment confirmation by design). The Dashboard's "Recent deliveries" view is the only place this surfaces.
**How to apply:** When going live, register `https://canadianpoliticaldata.org/api/v1/webhooks/stripe` a **second time** in the live-mode dashboard. Verify the URL exactly matches your live host (the `.ca` brand-aspiration domain is not currently DNS-routed; using it would silently fail). Subscribe to `checkout.session.completed` only. Stripe retries failed webhooks 5x over 72h, so a delayed fix still works as long as you click Resend on the failed deliveries within that window.

### Do not pass `prod_…` as a Price ID
**Why:** The Stripe Dashboard surfaces the Product ID (`prod_…`) more visibly than the Price ID (`price_…`); first-time integrators routinely paste the wrong one. The `STRIPE_PRICE_ID_CREDIT_PACK_*` env vars must be **price** IDs — `prod_…` values get rejected with `"No such price: 'prod_…'"` on the first checkout. Bit me on 2026-05-05 cutover.
**How to apply:** Sanity-check every `STRIPE_PRICE_ID_*` env var starts with `price_`, not `prod_`. The Stripe two-tier model (one Product, multiple Prices) is intentional — Prices are immutable for audit trail; Products are mutable for catalog.

### Do not bypass the "one pending rate-limit request per user" guard
**Why:** Without it, users can flood the admin queue with duplicate requests.
**How to apply:** App-layer check is the minimum. If the guard becomes load-bearing, add a DB-level partial unique index.

### Do not send the correction-reward email on idempotent re-applies
**Why:** Flipping a correction `applied → triaged → applied` would otherwise email the submitter twice, even though the grant only happened once.
**How to apply:** `grantCorrectionReward` returns `alreadyGranted: true` when the ledger row already exists. The admin PATCH handler only dispatches the email on a fresh insert.

### Do not place the report hold outside the `report_jobs` insert transaction
**Why:** The hold's `reference_id` is the job id; both rows must commit together. If the hold insert fails (insufficient balance, unique-violation on duplicate enqueue), the job row must roll back too.
**How to apply:** Single `BEGIN/COMMIT` wrapping the job insert and the `holdCredits` call.

## Reports worker & LLM map-reduce

### Do not skip server-side HTML sanitisation on stored report HTML
**Why:** The viewer renders via `dangerouslySetInnerHTML`. The sanitisation pass is what makes that safe — the viewer trusts the persist-time pass, not the user.
**How to apply:** `bleach.clean` runs in the worker before persistence — allowlist of `p / h2 / h3 / ul / ol / li / blockquote / em / strong / a[href]`, with `a[href]` constrained to internal `/speeches/...` paths.

### Do not duplicate the OpenRouter error mapping in `lib/reports.ts`
**Why:** Both contradictions and reports route through the same client. Forking the 401/429/timeout switch leads to drift.
**How to apply:** All OpenRouter calls go through `services/api/src/lib/openrouter.ts:callJsonObjectModel`. If you find yourself copying the error switch, you've drifted.

### Do not let the worker call the api over HTTP
**Why:** It's a service-boundary inversion — the worker's job is data plane, the api's job is user surface. Mixing them creates a circular dep at deploy time.
**How to apply:** The worker speaks straight to Postgres for chunk selection, ledger flips, and `report_jobs` updates.

## Blog & MkDocs

### Do not put reference material in the blog
**Why:** The blog is narrative — launches, post-mortems, technical deep-dives, decisions and their reasoning. Reference belongs in `docs/` (internal) or `mkdocs/docs/` (public).
**How to apply:** Before adding a post, ask: "would a returning reader expect to find this in a blog archive, or in a how-to/reference section?" If the latter, edit `mkdocs/docs/` instead.

### Do not put credentials, tokens, or private URLs in the blog
**Why:** The blog is public, indexed, and archived. Once shipped, assume forever.
**How to apply:** Standard secret-scanning hygiene. Internal hostnames + admin paths also count.

### Do not put machine-generated status logs in the blog
**Why:** The blog is for readers. Internal tracking belongs in `docs/runbooks/` or the admin dashboard.
**How to apply:** If you'd never re-read it as a human, it doesn't go in the blog.

## Semantic mind-map / Explore

### Do not re-project on filter change
**Why:** The whole point of the map is a stable spatial reference frame. Re-projecting per filter defeats it — the same speech ends up in a different place each time the user toggles a checkbox.
**How to apply:** Fade clusters proportionally to `member_count_filtered / member_count`. Spatial layout is the landmark; opacity is the filter signal.

### Do not auto-promote after `--stage=all`
**Why:** Promotion is a deliberate manual step so bad projections (failed cluster runs, label anomalies) can be discarded without ever being served.
**How to apply:** `--stage=all` runs fit → cluster → label without flipping `is_current`. Inspect the run, then `--stage=promote` separately.

### Do not confuse `cluster_level` with `level`
**Why:** They coexist in the same query string but mean different things. `cluster_level` ∈ {1,2,3,4} is HDBSCAN hierarchy depth; `level` ∈ {federal, provincial, municipal} is from `baseFilterSchema`.
**How to apply:** When wiring a new query, name the variable for the meaning, not the URL key.

### Do not reach for OpenRouter / hosted LLMs to generate cluster labels
**Why:** TF-IDF is the deliberate choice — self-hosted, deterministic, fast. Hosted-LLM labels would re-introduce a critical-path API dep.
**How to apply:** If label quality becomes a genuine problem, try BERTopic or a local Ollama model first. Hosted only with explicit user sign-off.

### Do not expose `projection_runs` or raw UMAP coords through the public API
**Why:** The full projection tables are large and internal. Exposing them invites scraping and ties the API to internal schema details.
**How to apply:** Only `GET /projections/clusters` and `GET /projections/points` are public. Both are read-only and constrained to the current run.

### Do not allow the frontend to call the scanner directly
**Why:** Projection builds are minutes-long, GPU-bound jobs. They belong on the queue, not on a request thread.
**How to apply:** Builds are triggered via the admin jobs queue (`scanner_jobs`). There is no HTTP endpoint that starts a scanner subprocess.

## Schema isolation (public vs private)

### Do not widen the API role's `search_path` to include `private`
**Why:** The whole point of putting user/payment tables in the `private` schema (migration 0042) is structural enforcement of the privacy boundary. The role `sw` is configured with `search_path = public` precisely so an unqualified `FROM users` raises a hard error instead of silently picking up `private.users`. Widening `search_path` re-creates the "did the engineer remember to qualify" problem we paid the migration cost to eliminate.
**How to apply:** Always write `private.users`, `private.credit_ledger`, etc. in SQL — both in TypeScript route handlers and in Python workers. Never alias to a bare `users`. If you find an unqualified reference, fix it; don't widen `search_path` to make it work.

### Do not put new user-data tables in the `public` schema
**Why:** The public dump (`cli/sovpro db public-dump` → `pg_dump --schema=public`) is the redistribution artifact. Anything in `public` is — by definition, no exceptions — safe to publish. A new table holding emails / sessions / payment metadata / user-submitted content in `public` is a privacy bug waiting to ship.
**How to apply:** New migrations creating user-account, session, payment, or user-submitted-content tables write `CREATE TABLE private.X`, not `CREATE TABLE X`. The dump script's manifest guardrail catches one of the 10 known table-name patterns showing up in `public`, but it does not catch a *novel* PII table; the rule above is what catches that.

### Do not add a `user_id` / `created_by_user_id` column on a public-schema table
**Why:** Same reason. Even if the FK target lives in `private`, the column itself in `public` carries the link to a person and would ship in the public dump.
**How to apply:** If you need to associate a user with a public artifact, put the linking row in `private` (e.g. `private.user_actions(user_id, public_artifact_id)`) and join from there.

## Public distribution

### Do not remove `limit_conn` / `limit_rate` from the `/datasets/` location
**Why:** This is the rate cliff between "anyone can grab the dump" and "the box's home upstream saturates and everything else lags." The 2-concurrent / 50 MB/s cap was set deliberately because there is no CDN in front; pulling the cap means the next viral Hacker News link makes the API and the docs site unresponsive too.
**How to apply:** If the cap is genuinely too tight (a legitimate user complaint, not a hypothetical), measure sustained traffic via `/var/log/nginx/datasets.access.log` first and raise the rate, don't remove it. If you ever need to lift the cap entirely, add a CDN (Cloudflare / Bunny / similar) in front rather than pointing strangers at the home upstream raw.

### Do not put `/datasets/` behind authentication
**Why:** The whole point of this surface is anonymous bulk download — journalists, civic-tech orgs, foreign researchers, the next Wikipedia editor. Adding auth re-creates the same friction we built `/datasets/` to escape, and conflicts with the open-data brand. Auth-gated bulk export is a separate, paid product (public dev API horizon).
**How to apply:** Keep `/datasets/` open + rate-limited. If a future "premium tier" ships, it gets a different URL (`/api/public/v1/bulk/...`) backed by API-key auth, not a flag on `/datasets/`.

### Do not couple a third-party mirror upload into `make-public-dump.sh`
**Why:** An earlier rclone+Proton Drive integration was reverted on 2026-05-04 after Proton's anti-abuse system soft-locked the account on first contact (their reverse-engineered backend trips fraud signals). Even with graceful-degrade gating, an in-script mirror creates an operator-confusion surface: a "succeeded" cron run that quietly ships a stale mirror is worse than no mirror at all. Mirrors are operator-driven now (manual upload).
**How to apply:** If a future mirror needs automation, write it as a separate script invoked *after* `make-public-dump.sh` lands a verified artifact, with its own cron entry, its own logs, and its own failure mode. Do not re-couple the publish path to the mirror upload path.

## Cross-cutting

### Do not make this apolitical
**Why:** The project is civic transparency rooted in democratic values and progressive stances. Non-neutrality is a feature, not a bug to file off.
**How to apply:** Public copy doesn't both-sides access-to-information principles. See `docs/goals.md` for the framing.

### Do not add hosted API dependencies in the critical path
**Why:** Self-hosting is a sovereignty stance and an availability stance. The project survives if OpenAI goes down; it shouldn't have to.
**How to apply:** Self-hosted first; hosted only with explicit user sign-off. The one sanctioned exception is the Anthropic API behind `ANTHROPIC_API_KEY`, used only by `agent-missing-socials` (Tier-3 socials backfill) and gated to abort cleanly when unset.

### Do not build per-jurisdiction UI variants for the same data type
**Why:** It scales linearly with jurisdictions and forks bugs. The whole point of the discriminated tables (one `bills`, one `speeches`, one `votes`) is that one view filters them all.
**How to apply:** One speeches view, one bills view, one votes view — each filterable by `level` + `province_territory`.

### Do not redact non-politician names from source text
**Why:** Hansard is public record. Redacting names corrupts the historical artifact.
**How to apply:** Store source text as-is. Don't surface non-politicians as first-class entities either — the distinction lives in retrieval UX, not at ingest.

### Do not create new `CLAUDE.md` / `AGENTS.md` files in subdirectories
**Why:** Multiple instructions files lead to drift. The root one is the authority.
**How to apply:** If you're tempted to add per-service instructions, ask first. Usually the answer is "extend the root file" or "put it in `docs/`."
