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

### Do not add a catalog entry without restarting `sw-scanner-jobs`
**Why:** The two-place rule is really a **three-step** rule, and the missing step fails in
a way that accuses the two files that are correct. `jobs_worker.py:38` binds the catalog
with a module-level `from .jobs_catalog import build_cli_args, get_command`, so the dict
is fixed at process start. The `./services/scanner/src:/app/src` bind mount keeps the
*file* current but cannot rebind a *running* process's import. The job then fails as
`unknown command in catalog: <name>` — which reads exactly like a `jobs_catalog.py` /
`admin.ts` divergence, so the natural response is to re-check two files that already
agree.

`reattach-municipal-roster` was lost this way: the entry was committed 2026-08-28 10:02,
the daemon had started 2026-08-27 00:05, and the job failed **5 runs out of 5** — it had
never once succeeded — silently removing the only automated defence against a boundary
cutover severing its council. ★ Same shape as the 2026-08-23 mirror regression: a
scanner-family container executing code older than the guard meant to stop it. There the
stale layer was the image; here the mount was already right and the stale layer was the
process lifetime.

**How to apply:** After editing `jobs_catalog.py`, run `docker compose restart
scanner-jobs`, then queue the new command once with `--dry-run` and confirm it reaches
`succeeded`. A `failed` row with a **NULL `exit_code`** and empty `stdout_tail`/
`stderr_tail` is the signature — the worker refused before spawning anything, so there is
no subprocess output to find. Check `scanner_jobs.error`, which carries the real reason.

## Database, migrations, schema

### Do not edit applied migrations
**Why:** No automated runner means you can't trust that "latest applied = latest on disk." Editing in place silently desyncs environments.
**How to apply:** Forward-only — bump the next number and write a new migration. History contains one accidental `0026_*` collision; do not back-renumber to fill gaps.

### Do not adopt OpenCivicData `ocd-person/*` IDs
**Why:** OCD's identifier scheme is built for the US's coverage gaps. The Canadian context has stable per-jurisdiction member IDs upstream; using those keeps joins exact.
**How to apply:** Per-jurisdiction slug/ID columns on `politicians` (see CLAUDE.md convention #1) + `politician_terms` covers the model.

### Do not "correct" `random_page_cost` to 1.1
**Why:** every SSD tuning guide recommends 1.1, and it is wrong for this host. 1.1 effectively asserts random reads are nearly free because the data is cached — true when the working set fits in RAM, false here: `speeches` is 182 GB and `speech_chunks` 58 GB against 61 GB of host memory, so a large share of random reads reach the device. Measured 2026-10-26: below 2.0 the speeches×chunks join flips to an index scan that is a wash warm (19 ms vs 19 ms) and worse cold — 7,233 page reads against 445, scattering random I/O across a 182 GB heap. At 3.0+ the `vote_positions` join reverts to a sequential scan of 1.6M rows, 0.28 ms → 4.53 ms. 2.0 is the only value that wins both.
**How to apply:** the value and the full plan-flip table live in `docker-compose.yml` beside the `command:` args. Re-walk that table (`set random_page_cost=<x>; explain <query>`) before moving it. Do not reason from "it's an SSD" alone — that is how you land on 1.1.

### Do not trust a timing comparison that did not alternate and repeat
**Why:** the first measurement of the `random_page_cost` change showed the index plan 6× *slower* (164 ms vs 27.8 ms). It was cold-cache ordering: alternating the two settings across three passes showed them identical. The opposite error is as easy — two of four test queries appeared to improve 3–5× at the new setting while their plans were byte-identical at both, so the difference was pure cache noise and nothing to do with the change.
**How to apply:** alternate settings within each pass, run at least three passes, and before claiming an improvement confirm the **plan actually changed** — compare `explain` output, not just `Execution Time`.

## Embeddings & vector storage

### Do not find chunker/embedder work via anti-joins against the corpus
**Why:** "Speeches with no chunks" as `LEFT JOIN speech_chunks … WHERE c.id IS NULL` is O(corpus), not O(backlog) — Postgres must prove *absence*, so it hash-joins both full tables (~24 GB of buffer reads by 2026-08). The daily `chunk-and-embed-speeches` job crossed the pool's 60 s `command_timeout` on 2026-08-03/04 and failed two mornings running, purely from data growth. Same failure class as a fixed `since_days` window: cost/coverage drifts silently until a green job goes red (or worse, stays green with missing work).
**How to apply:** Pending work is a flag + partial index: `speeches.needs_chunking` (migration `0057`, default `true` on insert, cleared transactionally per processed speech — skips included) mirrors `idx_chunks_needs_embedding` (`WHERE embedding IS NULL`) on the embed side. New derived-work pipelines get the same shape: a work-queue marker the processor clears, never a corpus-wide "what's missing" scan on a schedule. Re-queue for re-processing by setting the flag, not by deleting the marker column.

### Do not run monolithic bulk UPDATEs against `speech_chunks`
**Why:** Any non-HOT update on `speech_chunks` (and every `politician_id` change is non-HOT — the column is indexed) inserts a fresh tuple into *all* of the table's indexes, including the HNSW vector index, whose graph inserts touch dozens of pages each. With full-page writes that is ~0.5 MB of WAL **per updated row** — 6,920 drifted BC rows generated ~1 GB/min of WAL, drove checkpoints to every 26 s, and blew a 300 s statement timeout that then **rolled back all the work**, leaving the same backlog for the next nightly run (the 2026-08-04 BC Hansard poison loop). A monolithic sweep under any timeout either finishes or achieves nothing.
**How to apply:** Batch bulk `speech_chunks` updates by primary key with a commit per batch — `sync_chunk_politician_scoped()` in `speech_chunker.py` is the canonical shape (1,000-row batches, autocommit, converges across runs and survives crashes; four of its seven batches survived the 2026-08-04 mid-run Docker daemon bounce). Per-province Hansard ingesters call it scoped to the run's sitting-date floor instead of inlining their own sweep. The same discipline applies to any future backfill that touches a `speech_chunks` column: batch + commit, never one statement.

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
**Why:** The `public` / `private` schema split is the structural privacy boundary — anything in `public` is, by definition and with no exceptions, safe to redistribute. A table holding emails / sessions / payment metadata / user-submitted content in `public` is a privacy bug waiting to ship.
**How to apply:** New migrations creating user-account, session, payment, or user-submitted-content tables write `CREATE TABLE private.X`, not `CREATE TABLE X`. The qualification convention (`private.X` everywhere, never aliased) is the first line of defence; placing the table in `private` is what actually keeps it off the public side.

### Do not add a `user_id` / `created_by_user_id` column on a public-schema table
**Why:** Same reason. Even if the FK target lives in `private`, the column itself in `public` carries the link to a person and would ship in the public dump.
**How to apply:** If you need to associate a user with a public artifact, put the linking row in `private` (e.g. `private.user_actions(user_id, public_artifact_id)`) and join from there.

## Electoral boundaries & municipal rosters

### Do not hand-maintain a boundary or roster count in prose
**Why:** It was tried and it failed inside four days. The coverage matrices in
`docs/research/boundaries/overview.md` were the programme's record; the build ran for ten
days without touching them, and because `/docs/` excluded the *directory* — so git never
descended into it — there was no diff in which anyone could notice. The header was still
asserting "every one of the 1,949 boundary rows is still an Open North mirror" after
migration `0105` had installed a trigger refusing exactly those rows.
**How to apply:** Run `boundary-progress` and commit `docs/research/boundaries/PROGRESS.md`
**in the same change that lands a cutover**. Prose keeps the reasoning — licences, traps,
vintage evidence — and links to the generated file for any number. If you catch yourself
typing a district count into a `.md`, that is the smell.

### Do not use `source_id LIKE 'opennorth:%'` as a staleness measure
**Why:** It measures **provenance**, not freshness, and over-reports by ~948 rows. A
politician carrying a native legislature ID (convention #1) is matched by exact FK from its
own legislature's pipeline every day; the `opennorth:` prefix records only where the row was
*first* written. All 332 federal MPs it counted as "frozen" are refreshed daily. The
headline said 1,057 federal/provincial frozen; the honest figure is **109**.
**How to apply:** Test `HAS_NATIVE_ID` (`boundary_coverage.py`) alongside the prefix. ⚠ The
result is a **refresh-path** classification, not a freshness one — nothing on `politicians`
records when we last *confirmed* a person still holds a seat, and `updated_at` only moves
when a field changes, so a stable roster looks stale and a mass sweep looks fresh. Municipal
is the exception: no council official has a native ID, so there the prefix does mean frozen.

### Do not treat `authority IS NULL` on a live boundary row as work to do
**Why:** A superseded generation stays live until the day its successor takes force.
Québec's 2017 provincial map is 124 mirror rows answering lookups **right now, correctly**,
with an authoritative 127-district successor already loaded and dated 2026-10-05 (migration
`0117`). Counting it as backlog invents 124 rows of work; counting it as done hides that
today's Québec provincial answers are mirror geometry.
**How to apply:** Classify three ways, as `boundary_progress.py` does — authoritative,
mirror-with-a-dated-successor, and mirror-with-nothing-queued. Only the third is a backlog.

### Do not count boundary rows with `effective_to IS NULL`
**Why:** That is not the live set. It counts **dormant future** generations as though they
were in force — seven Ontario 2026 ward maps and Québec's 2026 provincial map are loaded and
waiting right now — and it drops generations that are end-dated but have not expired. It is
the same defect that had six sentinel checks failing open, and it produced a wrong figure
twice while the tracker was being written.
**How to apply:** `effective_from <= CURRENT_DATE AND (effective_to IS NULL OR effective_to
>= CURRENT_DATE)`. Use `LIVE_WINDOW` from `boundary_progress.py`. ⚠ Also exclude
`boundary_kind = 'municipality'` when counting seats — those rows are city outlines, and
counting them alongside districts made 34 sets look "partially replaced" when each had
exactly one authoritative row, the outline, and none of its districts.

**Do not assume `reattach-municipal-roster` cleans up after a re-key.**
It does not, and the two failures look identical from a distance. That job
selects councils holding a member whose `constituency_id IS NULL` — a
**detached** member. A re-key nulls nothing: it leaves the member pointing at an
id that no longer resolves to a live row. That member is **orphaned**, not
detached, so the job never selects their council and reports `matched=0` while
looking perfectly healthy. *Why:* found 2026-09-02 on the Halifax cutover. One
district id changed because the publisher writes "Middle & Upper Sackville" —
the mirror expanded `&` to `and`, our `slugify` drops it — and the councillor
sat on a dead id. `reattach-municipal-roster` ran green; only
`check-boundary-coverage` saw it, as a `municipal/orphaned` **BREACH**. Same
one-character identity class as the `œ` divergence re-keyed in `0098`.
*How to apply:* handle it **inside the cutover migration**, before the
end-dating, and pick the right one of two established patterns:

- **The district genuinely changed** (renamed because its ground moved,
  dissolved, split) → set `constituency_id = NULL` for members on ids the new
  generation does not reproduce, then let `reattach-municipal-roster` place them
  **geographically**. This is `0121`, which documents the trap in full and warns
  against skipping it on the assumption reattach will cope. Use this whenever
  the correct destination is a question about ground rather than spelling.
- **Only the id's rendering changed** and the mapping is certain → re-key
  directly, matched on the exact old id and asserted both directions. This is
  `0098` (the `œ` ligature) and `0124` (`&` vs `and`). Use it only when the
  polygon is the same polygon and you can say so.

Then run `check-boundary-coverage` to prove zero orphans corpus-wide.
⛔ Do not extend the reattach job to auto-fix orphans — choosing between those
two patterns is a judgement about identity, and the breach stopping to ask is
the feature, not the defect.

**Do not read a matching district COUNT as matching geometry.**
Ruling A7 — vintage must be measured, not counted — and this is the second time
the same lesson has been paid for. *Why:* `municipal-atlantic.md` recorded Cape
Breton as `✅ count matches` (12 held, 12 authoritative) and that was cited as
evidence the set was healthy. When the authoritative file was finally loaded,
`--compare` measured district-9 at **34.55%** overlap with the polygon we were
serving, district-4 at 69.20%, district-11 at 70.68%, 8 of 12 below 95%. CBRM
had been redistricted by N.S. Reg. 150/2023 and the mirror held the pre-2023
map; residents were being returned the wrong councillor while every count-based
check said fine. *How to apply:* run `load-boundaries --compare` before any
cutover and **read** `mean_overlap` / `min` / `below_95%`, not just the matched
count. ⚠ The inverse trap too — a near-perfect overlap proves nothing when both
files descend from the same publisher, which is what made Terrebonne look fine
while 12 of its 14 name-preserved districts had moved.

**Do not ship a municipal boundary cutover without re-attaching the roster.**
A cutover renames the `source_set` and re-keys `constituency_id`. The roster is
a different table joined on that id and nothing in the cutover touches it, so
the council is silently detached. *Why:* found 2026-08-28 — 142 sitting
officials across 18 councils held a NULL `constituency_id` while their ward
polygon sat there unlinked (Calgary 14, Winnipeg 14, Welland 12, Fredericton 12,
Edmonton 12, Regina 10). *How to apply:* run
`reattach-municipal-roster` after any cutover (now also scheduled daily at
13:45 UTC, twelve minutes before the sentinel); for Québec run
`ingest-qc-municipal-roster`, which does its own attach.

**Do not match a member to a district by name — not even a whole council's
worth of names.** *Why:* `Ward 1` exists in hundreds of sets, and the
whole-council "fingerprint" idea is also wrong because cities number wards
identically: Calgary's fourteen names are covered exactly by `hamilton-wards`
and `london-wards`. *How to apply:* names narrow, **geography decides** —
`ST_Contains` the candidate districts against the council's own municipality
polygon, using `ST_PointOnSurface` (a crescent-shaped ward's centroid can fall
outside it). Refuse on a tie; see migration 0089, where a Gatineau councillor
was attached to a Québec City district 400 km away.

**Every `EXISTS` against `constituency_boundaries` must filter the live
window.** *Why:* a superseded generation is end-dated, never deleted, so a bare
`EXISTS` asks "was this ever a district?" and stays true forever. Six checks
have now shipped with this bug (`duplicate-generation`, `duplicate-geometry`,
`wrong-tier`, `displaced`, and both orphan checks). *How to apply:* always add
`effective_from <= CURRENT_DATE AND (effective_to IS NULL OR effective_to >=
CURRENT_DATE)`, and prove a new check fires by re-introducing the defect in a
rolled-back transaction.

**A boundary generation's in-force date is the election it first governed, not
its legal date (ruling A10.4).** *Why:* between the two, sitting members point
at districts that have never held an election. *How to apply:* date it to
polling day, and change **both** the migration and the loader spec — the spec
stamps `effective_from` and will restore the old date on the next load.
⚠ `jurisdiction_sources.seats` changes with the election, not with the map.

**Do not name a plpgsql variable `overlaps`.** *Why:* `OVERLAPS` is a reserved
SQL keyword (the period operator); `IF overlaps <> 0` is a syntax error that
reads as nonsense. *How to apply:* use `n_overlap`.

**`constituency_name_alias` is not a fuzzy matcher.** *Why:* algorithmic
abbreviation-normalising would pair `Saint-Charles` in Kirkland with
`Saint-Charles` in Longueuil. *How to apply:* one explicit row per reasoned
decision, scoped per council, with the evidence in `reason`. Use it only when
two sources spell the SAME district differently — never for a district that was
genuinely renamed, which makes the polygon's own name stale.

## Public edge & crawler policy

**Do not block search or citation crawlers from `/api/`.** The frontend is a
client-rendered SPA: `/` returns ~1.8 KB containing `<div id="root"></div>` and
nothing else, and every page's content arrives over `/api/v1/*`. A 403 (or a
robots.txt `Disallow: /api/`) that applies to Googlebot makes every page render
empty, and Google concludes the site has no content.

*Why:* the usual advice — "crawlers have no business in your JSON API" — assumes
server-rendered HTML where the API is redundant with the page. Under client-side
rendering the API **is** the page. Verified 2026-08-29: the first version of the
`/api/` rule 403'd Googlebot, caught only because the verification pass tested the
allowed crawlers rather than just the blocked ones.

*How to apply:* `$ua_search_ok` in `nginx/nginx.conf` exempts search and citation
crawlers from `$block_api_crawler`, and `nginx/robots.txt` gives them their own
group with `Allow: /api/`. Both must be changed together. Revisit only if the
frontend gains SSR or prerendering.

**Do not rate-limit `/api/` by client address alone.** A per-IP `limit_req` is
the obvious design and it would not have stopped the 2026-10-26 incident at any
threshold that leaves the site usable.

*Why:* the crawler farm spread ~1,050 req/min across 251 addresses in a single
`/24`, so each address sat at 17 req/min — *below* measured legitimate human
traffic (~15/min sustained, and one search page load fans out into seven
`/api/v1` calls at once). There was no per-IP signal to threshold against. The
same volume aggregated by `/24` was 1,050/min against a legitimate peak of
45/min: a 23× difference.

*How to apply:* keep the `api_net` `/24` zone in `nginx/nginx.conf`. The per-IP
zone catches single-source abuse and the `/24` zone catches farms; they are not
redundant. Re-measure with the commands in `docs/operations.md` § *Rate limiting
`/api/`* before moving a threshold — the subnet rate is pinned between the pro
API tier below it (10,000 req/h ≈ 2.8 r/s) and the farm above it (17.5 r/s), so
moving it needs both bounds rechecked.

**Do not exempt anything from the `/24` rate-limit zone.** Exemptions belong on
the per-IP zone only.

*Why:* both exemption signals are client-supplied and unverifiable at the edge —
nginx cannot authenticate an API token, and any scraper can send
`User-Agent: Googlebot`. Verified 2026-10-26: a forged
`Authorization: Bearer cpd_live_forged_deadbeef` passed 60/60 requests while the
exemption covered both zones. With exemptions confined to the per-IP zone,
forging one buys relief from 2 r/s and nothing more.

*How to apply:* `$api_ip_exempt` feeds `$api_limit_ip` only. `$api_limit_net` has
no exemption branch and must not gain one. Googlebot does not need one: its full
observed per-minute peak passes on `burst=120` alone with 2.6× margin.

**Do not add an uncached, unfiltered aggregate to a public endpoint.** A
`COUNT(*)` over `speech_chunks` has no answer cheaper than reading all 58 GB.

*Why:* `/api/v1/search/meta` fed a UI progress banner with an unauthenticated,
uncached `COUNT(*)`. On 2026-10-26 a crawler called it ~80×/min; 31 scans ran
concurrently, `sw-db` held ~830% CPU and the host reached 96 °C against a 100 °C
critical threshold. 1,727 requests returned 499 (client aborted) — Fastify does
not cancel the underlying query when the socket dies, so abandoned requests cost
a full scan anyway. The endpoint was computing a constant: coverage was 1.0.

*How to apply:* cache it, and **single-flight it**. A plain TTL cache is not
enough — every request arriving during the ~20 s scan after expiry misses and
starts its own, which is the same stampede once per TTL. See
`readEmbedCoverage()` in `services/api/src/routes/search.ts` for the
stale-while-revalidate + `inFlight` shape; the `inFlight` promise is load-bearing
and must not be simplified away.

**Do not count the asking backend when measuring `pg_stat_activity`.** Filter
`pid <> pg_backend_pid()`.

*Why:* a diagnostic keyed on `query LIKE '%<some text>%'` matches its own query
text, so it reports a floor of 1 forever. Cost ~10 minutes of chasing a
phantom scan on 2026-10-26 after the real ones were already gone.

**Do not set Fastify `trustProxy: true`.** It walks the whole `X-Forwarded-For`
chain and returns the **leftmost** entry, which is attacker-supplied.

*Why:* verified 2026-08-29 — a different `X-Forwarded-For` per request produced a
fresh rate-limit bucket every time, making the 300/min global limit opt-out by
header for anyone who knew to send one.

*How to apply:* `services/api/src/index.ts` uses a CIDR allowlist
(`["127.0.0.1", "::1", "172.16.0.0/12"]`), which skips private hops from the right
and is correct whether nginx overwrites or appends the header. `nginx.conf` sets
`real_ip_recursive off` — with it `on`, nginx lands on the leftmost entry and
reintroduces the same forgery.

**Do not let the SPA catch-all answer `/robots.txt`.** Until 2026-08-29 it
returned `200` + `index.html`, which every crawler parses as "no rules".

*Why:* a 200 of HTML is worse than a 404. Both mean "no restrictions", but the
200 looks intentional and hides the omission from every check that only asserts
the status code.

*How to apply:* both vhosts have `location = /robots.txt` serving
`nginx/robots.txt` from disk, ahead of the proxy catch-all. Assert the
`Content-Type` is `text/plain`, not just that the status is 200.

**A blocked crawler must still be able to read `/robots.txt`.** `$block_ai` is
deliberately a two-variable map (trainer UA **and** not-robots.txt) rather than a
server-level `if`, which runs in the rewrite phase and would swallow the
robots.txt request too. A crawler that only ever sees 403 has no machine-readable
reason to back off, and some retry harder on 403 than on an honoured `Disallow`.

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

### Do not schedule forward ingest with a fixed event-date window (`since_days`)
**Why:** A fixed window filtered on the *upstream event date* (sitting date, vote date) turns any outage or publication lag longer than the window into a **permanent silent hole that reports success**. The 2026-08-02 audit found three: QC lost ~2.5 months of Hansard+votes (a dropdown-label change broke session discovery; the daily `since_days=14` job then reported `succeeded, sittings=0` while the window slid past the gap), NB lost 77 days (NB publishes transcripts 2–3 months after the sitting — by publication day the sitting date was outside the window forever), and NU sat 741 days stale (NU publishes ~15 months late; a 14-day window can *never* ingest anything from NU). Even federal was missing 1,142 speeches.
**How to apply:** Daily schedules pass empty args and let each command's self-healing fallback drive: `resolve_since()` DB-high-water−overlap where wired, current-session bounds otherwise (`services/scanner/src/legislative/_forward.py`). Ingest is idempotent + etag-cached, so re-listing the current session nightly is cheap (measured: federal full current-session pass = 5m49s). `--since-days` stays available for manual runs, but never bake it into a schedule row. Backstop: the weekly `check-ingest-freshness` sentinel (`legislative/freshness.py`) compares `MAX(bill_events.event_date)` vs `MAX(speeches.spoken_at)` per jurisdiction and fails the job on breach.

### Do not let a discovery fallback swallow "the current session isn't where I expected"
**Why:** Fallback paths built for historical data (Wayback CDX, archive listings) return empty for current sessions, converting a real discovery failure into `succeeded, sittings=0`. That's how the QC hole survived ~3 months of green daily runs: the current-session dropdown label grew a "Session en cours - " prefix, the option regex stopped matching, discovery raised, and the Wayback fallback silently returned nothing.
**How to apply:** Distinguish failure classes. "Requested session missing from upstream's own index" is a raise-loudly error (`SessionNotInDropdownError` in `qc_hansard.py`), never a fallback trigger. When adding a session-scoped scraper, ask: if upstream renames/moves the current session, does this pipeline fail red, or does it succeed with zero rows?
