# API Reference

Base URL: `http://<host>/api/v1`

All endpoints return JSON. Pagination: `?page=N&limit=M` where applicable.

> **`/api/v1/search/*` is frozen as v1.0 on 2026-05-12.**
> New optional query params and response fields may be added without a version bump.
> Field removals or renames require v2. See **[Stability & Versioning](#stability--versioning)** below.

## Stability & Versioning

The `/api/v1/search/*` surface — `/speeches`, `/speeches/count`, `/politician-quotes`, `/facets`, `/sessions`, `/chunks/:id`, `/meta` — is the canonical search contract. The frontend `/search` page consumes it; saved searches persist filters in this shape; the planned **Public developer API** workstream (`docs/plans/public-developer-api.md`) will derive `/api/public/v1/*` from it. Sign-off date: **2026-05-12**.

**Backward-compatible (allowed within v1.x — no version bump):**
- New optional query parameters.
- New response fields (clients should ignore unknown keys).
- New endpoints under `/api/v1/search/*`.
- New server-side defaults that don't change observable output for existing requests.
- Tightening internal performance tuning (HNSW `ef_search`, query-embedding LRU, etc.) when output is unchanged.

**Breaking (require v2):**
- Removing or renaming any documented field.
- Changing a documented default in a way that alters observable output (e.g., `min_similarity` server-side default of 0.5, the `/politician-quotes` 0.45 clamp, the `/facets` `?limit` default of 200, the 10,000 `capped` ceiling).
- Removing an endpoint or removing a value from a previously-permissive enum (e.g., dropping `floor` from `speech_type`).
- Changing the structural shape of an existing field (e.g., array → scalar).

**Deprecation policy:** any v2 cutover ships with at least **6 months notice** in this doc, in the application changelog, and in a `Sunset` HTTP header on the deprecated endpoint(s). Deprecated fields and endpoints continue to function in full during the notice window.

**Schema source of truth:** `services/api/src/routes/search.ts` — `baseFilterSchema` (filter contract), `searchQuery` (extends with pagination), and `SPEECH_TYPE_VALUES` (the speech-type enum). When the docs and the schema disagree, **the schema wins** and this doc is the bug.

**Auth tiers** are not part of the v1.0 freeze: `/politician-quotes` is auth-gated + rate-limited (60/min) today; everything else is public. Public-developer-API tier annotations (free / dev / pro) live in that workstream's own surface and don't backflow into v1.

## Politicians

### `GET /politicians`
Query params:
- `level` — `federal | provincial | municipal`
- `province` — 2-letter (`AB`, `ON`, ...)
- `party` — exact match
- `sovereignty_tier` — 1-6
- `search` — name substring (ILIKE)
- `page`, `limit` (max 500, default 50)

### `GET /politicians/:id`
Returns the politician, all websites with their latest scan, and the constituency boundary GeoJSON.

## Search (Hansard)

Semantic + structural search over Canadian Hansard. Backs `/search` in the frontend. The shared filter schema (`baseFilterSchema` in `services/api/src/routes/search.ts`) is the single source of truth for what's a valid search; saved searches reuse the same shape.

### Shared filter parameters

Accepted by `/search/speeches`, `/search/politician-quotes`, and `/search/facets`.

- `q` — semantic query string (max 500 chars). Empty `q` switches `/speeches` to recency mode; `/politician-quotes` requires `q` (400 otherwise); `/facets` allows it but at least one structural filter must be present.
- `lang` — `en | fr | any` (default `any`).
- `level` — `federal | provincial | municipal`.
- `province_territory` — 2-letter (`AB`, `ON`, ...).
- `politician_ids` — repeated UUID, max 10. Legacy alias `politician_id` (single or repeated) is also accepted; both forms are deduped server-side via `effectivePoliticianIds()`.
- `party` — exact match against `speech_chunks.party_at_time`.
- `from`, `to` — ISO `YYYY-MM-DD` bounds on `spoken_at`.
- `exclude_presiding` — `true` strips Speaker / Chair turns (rows where `speeches.speaker_role` is non-empty).
- `min_similarity` — cosine-similarity floor 0..1. Only meaningful with `q` set; ignored in recency mode. `/politician-quotes` and grouped `/speeches` clamp to `>= 0.45` server-side so quote counts stay aligned with the grouped-view `mention_count`.
- `parliament_number` + `session_number` — must arrive together; resolved against `legislative_sessions` within the request's (level, province). One without the other is dropped as ambiguous.
- `speech_type` — repeated param over `floor | committee | question_period | statement | point_of_order | group` (sourced from `SPEECH_TYPE_VALUES` in `services/api/src/routes/search.ts`). Example: `?speech_type=question_period&speech_type=statement`.
- `politician_active` — `active | inactive`. Restrict to speeches by politicians who are currently in office (`active`) or no longer in office (`inactive`). Implemented as an EXISTS join to `politicians.is_active`, so unresolved speeches (`politician_id IS NULL`) drop out of both sides — an unresolved speaker is neither active nor inactive.
- `anchor_chunk_id` — UUID. Anchor-chunk search: rank the corpus by cosine similarity to this chunk's embedding instead of a text query. Mutually exclusive with `q` — when both are present, `q` wins and the anchor is ignored. The anchor itself is excluded from results so it doesn't dominate its own ranking. 404 (`anchor_not_found`) if the chunk doesn't exist.

### `GET /search/speeches`

Two modes selected by `group_by`.

**Timeline mode** (`group_by=timeline`, default). Flat chunk list, paginated.
- Adds: `page` (default 1), `limit` (1–50, default 20).
- `include_count` (default `true`): set to `false` to skip the COUNT(*) query and have `total` and `pages` returned as `null`. The frontend opts out and stages count off the hot path via `/search/speeches/count` because the threshold-COUNT can't use HNSW (it's a cardinality-of-neighbourhood question, not a top-K one) and on a q-only query against the full corpus it costs ~15s. URL form accepts `false` / `"false"` literally — `z.coerce.boolean("false")` would silently coerce to true, so the schema does explicit literal-aware parsing.
- 400 if neither `q`, `anchor_chunk_id`, nor any structural filter is present.

```jsonc
{
  "items": [
    {
      "chunk_id": "uuid", "speech_id": "uuid", "chunk_index": 0,
      "text": "…", "snippet_html": "<b>…</b>",
      "similarity": 0.72,            // null in recency mode
      "spoken_at": "2024-03-21T00:00:00Z",
      "language": "en", "level": "federal", "province_territory": null,
      "party_at_time": "Conservative",
      "politician": {
        "id": "uuid", "name": "...", "slug": "...",
        "photo_url": "...", "party": "...", "socials": [...]
      },
      "speech": {
        "speaker_name_raw": "...", "speaker_role": "...",
        "source_url": "...", "source_anchor": "...",
        "source_system": "openparliament", // origin pipeline; backs video deep-links
        "session": { "parliament_number": 44, "session_number": 1 }
      }
    }
  ],
  "page": 1, "limit": 20,
  "total": 1234,                      // null when include_count=false
  "capped": false,                    // true when total === 10000 (HNSW LIMIT trick)
  "pages": 62,                        // null when include_count=false
  "mode": "semantic"                  // or "recent"
}
```

**Grouped mode** (`group_by=politician`). One politician per group with their top-N matching chunks.
- Adds: `per_group_limit` (1–10, default 5), `sort` ∈ `mentions | best_match | avg_match | keyword_hits` (default `mentions`).
- Requires `q` — grouping only makes sense when ranked semantically; q-less grouped calls 400.
- Only resolved politicians appear in groups (chunks with `politician_id IS NULL` drop out).
- `SET LOCAL hnsw.ef_search = 600` is applied inside a transaction so the candidate pool isn't silently capped at the default 40.

```jsonc
{
  "mode": "grouped",
  "group_by": "politician",
  "page": 1, "limit": 20,
  "per_group_limit": 5,
  "total_politicians": 20,
  "groups": [
    {
      "politician": { "id": "...", "name": "...", "slug": "...", "photo_url": "...", "party": "...", "socials": [...] },
      "best_similarity": 0.72,
      "chunks": [ /* same chunk shape as timeline, minus politician — it's on the group */ ]
    }
  ]
}
```

### `GET /search/speeches/count`

Count-only sibling of `/speeches`. Same filter shape, runs only the `COUNT(*)` query so the frontend can stage it in parallel with a `/speeches?include_count=false` call — results render fast while the (potentially slow) total resolves separately. Threshold semantics mirror `/speeches` exactly so the count and the rendered page agree on what's included.

- 400 if neither `q`, `anchor_chunk_id`, nor any structural filter is present.

```json
{ "total": 1234, "capped": false }
```

`capped: true` means the count hit the cap (10,000 + 1 cancel-after sentinel) and the real total is `>= 10,000`. The cap exists because threshold-COUNT on a q-only query against the full corpus is ~15s without HNSW, and the UI doesn't need an exact figure past five digits.

### `GET /search/politician-quotes`

Single-politician deep-dive backing the "Show all matching quotes" expand affordance on `/search`'s grouped view. **Auth-gated** (`requireUser`) and per-user rate-limited at 60/min keyed on `expand-quotes:<userId>`.
- Required: `politician_id` (single UUID), `q`.
- Accepts the rest of the shared filter set; `min_similarity` is clamped `>= 0.45` server-side regardless of input.
- Returns the same shape as `/search/speeches` timeline mode, scoped to the single politician.

### `GET /search/facets`

Analytics breakdown over the top-N candidate pool (semantic when `q` is set, else recent). Backs the Analysis tab on `/search`. `SET LOCAL hnsw.ef_search = 300` per statement.

- Optional `limit` query param controls N: clamped `[10, 500]`, default `200`. Upper bound is shared with the analysis CTA's input cap (max input to a paid search analysis is 500 chunks; same number).
- 400 if neither `q`, `anchor_chunk_id`, nor any structural filter is present.

```jsonc
{
  "analyzed_count": 200, "analysis_limit": 200,
  "chunk_ids":     ["uuid", "uuid", ...],                    // top-N chunk ids the tiles aggregate over; same set feeds the "Analyse these results" CTA
  "by_party":      [{ "party": "Conservative", "count": 47, "avg_similarity": 0.68 }, ...],
  "by_politician": [{ "politician": { "id": "...", "name": "...", "slug": "..." }, "count": 12, "avg_similarity": 0.71 }, ...],
  "by_year":       [{ "year": 2023, "count": 18 }, ...],
  "by_language":   [{ "language": "en", "count": 162 }, { "language": "fr", "count": 38 }],
  "keyword_overlap": { "both": 84, "semantic_only": 116 },   // null in recency mode
  "mode": "semantic"
}
```

### `GET /search/sessions`

Lookup table for the cascading parliament/session dropdown in the advanced-filters disclosure.
- Query params: `level`, `province` (2-letter, optional). For `level=federal` with no `province`, restricts to `province_territory IS NULL`.
- Response: `{ "sessions": [{ "parliament_number", "session_number", "name", "start_date", "end_date" }] }`, newest first.
- `Cache-Control: public, max-age=3600` — sessions change ~once per prorogation.

### `GET /search/chunks/:id`

Anchor-chunk lookup. The `/search` frontend's anchor banner uses this to render "currently anchored on `<speaker>`: `<chunk text>`" with a single round trip rather than two (chunk → `speech_id` → speech).

- Path param `:id` is a UUID; 400 (`invalid id`) if it doesn't match `[0-9a-f-]{36}`.
- 404 if the chunk doesn't exist.

```jsonc
{
  "chunk_id": "uuid", "speech_id": "uuid",
  "text": "…",
  "char_start": 0, "char_end": 412,
  "language": "en",
  "speaker_name_raw": "...", "party_at_time": "Conservative",
  "spoken_at": "2024-03-21T00:00:00Z",
  "level": "federal", "province_territory": null,
  "source_url": "...", "source_anchor": "#turn-32",
  "source_system": "openparliament",
  "politician": {
    "id": "uuid", "name": "...", "slug": "...",
    "photo_url": "...", "party": "..."
  } // null if speech.politician_id is unresolved
}
```

### `GET /search/meta`

Backfill-progress surface for the UI banner above results.

```json
{ "total_chunks": 1480000, "embedded_chunks": 1480000, "coverage": 1.0 }
```

## Organizations

### `GET /organizations`
- `type` — `referendum_leave | referendum_stay | political_party | indigenous_rights | advocacy | government_body | media`
- `side` — `leave | stay | neutral`
- `search` — name substring

### `GET /organizations/:idOrSlug`
Looks up by UUID or slug (e.g. `alberta-prosperity-project`).

## Map

### `GET /map/geojson`
- `level`, `province`, `group=politicians|organizations|all`

Returns a `FeatureCollection` containing three feature kinds:
- `kind: "constituency"` — MultiPolygon
- `kind: "server"` — Point
- `kind: "connection"` — LineString from constituency centroid → server

### `GET /map/referendum`
Returns a `FeatureCollection` focused on referendum orgs, with the AB provincial boundary as context.

## Stats

### `GET /stats`
Top-level rollup: politicians by level/party, sovereignty distribution, top providers + locations, organizations summary.

### `GET /stats/referendum`
```json
{
  "leave_side":  { "orgs": [...], "total_websites": N, "hosted_in_us": N, ... },
  "stay_side":   { ... },
  "irony_score": "Organizations advocating to leave Canada..."
}
```

## Coverage

### `GET /coverage`
Query params:
- `status` — filter by `bills_status`: `live | partial | blocked | none`

Returns the `jurisdiction_sources` table plus a rollup summary:

```json
{
  "jurisdictions": [
    {
      "jurisdiction": "AB",
      "legislature_name": "Legislative Assembly of Alberta",
      "seats": 87,
      "bills_status": "live",
      "hansard_status": "none",
      "votes_status": "none",
      "committees_status": "live",
      "bills_difficulty": 2,
      "blockers": null,
      "notes": "Legislature 31 S1+S2 live (114 bills); Hansard is PDF-only",
      "bills_count": 0,
      "speeches_count": 0,
      "votes_count": 0,
      "politicians_count": 0,
      "last_verified_at": null
    }
  ],
  "summary": { "total": 14, "live": 8, "partial": 2, "blocked": 2, "none": 2 }
}
```

Seeded on migration 0019 and kept current by `jurisdiction_sources` updates from ingest pipelines.

## Changes

### `GET /changes`
- `since` (ISO timestamp), `owner_type`, `change_type`, `severity`
- Returns scan deltas with owner name + URL.

## Webhooks

### `POST /webhooks/change`
Receives notifications from the `change` detection container. Authenticated via:
```
X-Signature: sha256=<hex(hmac_sha256(WEBHOOK_SECRET, raw_body))>
```
If `WEBHOOK_SECRET` is unset, the endpoint accepts unsigned posts (dev mode only).

## Open Graph

### `GET /og/share`
Returns a dynamic **1200×630 PNG** share card with the current headline stat
(% of Canadian politicians hosting outside Canada) and a sovereignty-tier bar
chart. Intended for use in `<meta property="og:image">` tags.

- `Content-Type: image/png`
- `Cache-Control: public, max-age=300`
- In-process cache refreshes every 5 minutes from live `/stats` data.

## Admin

All `/api/v1/admin/*` routes require a valid user session cookie (`sw_session`) on a user whose `users.is_admin = true`. Mutating verbs (POST / PATCH / DELETE) additionally require the double-submit CSRF token in `X-CSRF-Token`.

- Not signed in → **401** `{"error":"not signed in"}`.
- Signed in but not admin → **403** `{"error":"admin access required"}`.
- CSRF missing/invalid on a mutating route → **403** `{"error":"csrf check failed"}`.
- `JWT_SECRET` unset on the server → **503** (admin surface is disabled along with all user auth).

No `POST /admin/login` endpoint — admins sign in via the shared magic-link flow (`POST /api/v1/auth/request-link` → email → `POST /api/v1/auth/verify`). The `is_admin` flag is included on `GET /me`.

### `GET /admin/commands`
Returns the whitelist catalog:
```json
{ "commands": [ { "key": "chunk-speeches", "category": "hansard",
                  "description": "...", "args": [ ... ] }, ... ] }
```
Used by the frontend form generator.

### `GET /admin/jobs`
Query: `?status=queued|running|succeeded|failed|cancelled`, `?schedule_id=…`, `?limit=1..500` (default 100).
Returns `{ jobs: [...] }` with a `stdout_snippet`/`stderr_snippet` (first 500 chars each) for list-view rendering.

### `POST /admin/jobs`
Body: `{ command: string, args: object, priority?: 0..100 }`. Command must be in the whitelist. Returns `{ id }` on 201.

### `GET /admin/jobs/:id`
Full row with `stdout_tail` / `stderr_tail` (last 4 KB each) and `error`.

### `POST /admin/jobs/:id/cancel`
Flips status to `cancelled` **only** if currently `queued`. Running jobs are not interrupted (returns 409).

### `GET /admin/schedules`
List all rows in `scanner_schedules`.

### `POST /admin/schedules`
Body: `{ name, command, args, cron, enabled? }`. `cron` is 5-field UTC.

### `PATCH /admin/schedules/:id`
Partial update. Changing `cron` clears `next_run_at` so the worker recomputes it.

### `DELETE /admin/schedules/:id`
Returns 204. `scanner_jobs.schedule_id` is set NULL via FK (jobs history is preserved).

### `GET /admin/stats`
Dashboard counters:
```json
{
  "speeches": 20,
  "chunks": { "total": 20, "embedded": 20, "pending": 0 },
  "jobs":    { "queued": 0, "running": 0, "succeeded_24h": 3, "failed_24h": 0 },
  "jurisdictions": { "live": 8, "total": 14 },
  "recent_failures": [ { "id", "command", "finished_at", "error" }, ... ]
}
```

## Credits (billing rail — phase 1a)

All `/me/credits/*` routes require a signed-in session (`sw_session` cookie). Mutating routes additionally require the `sw_csrf` cookie echoed in the `X-CSRF-Token` header. When Stripe is unconfigured (`STRIPE_SECRET_KEY` unset), the feature returns `stripe_enabled: false` and the purchase endpoint 503s — no payment surface is exposed.

### `GET /me/credits`
Current spendable balance + recent ledger history (up to 50 entries, newest first). `reference_id` is deliberately omitted from the user-facing shape — see `/admin/users/:id` for the full-fidelity admin view.
```json
{
  "balance": 120,
  "history": [
    { "id": "uuid", "delta": 100, "state": "committed", "kind": "stripe_purchase", "reason": null, "created_at": "2026-04-23T..." },
    { "id": "uuid", "delta": 20,  "state": "committed", "kind": "admin_credit",    "reason": "Launch promo", "created_at": "..." }
  ],
  "stripe_enabled": true
}
```

### `GET /me/credits/packs`
Lists the credit packs currently offered. Filtered to packs whose `STRIPE_PRICE_ID_*` env var is set — if a pack isn't configured, it's simply omitted.
- `tax_enabled` mirrors the `STRIPE_TAX_ENABLED` server flag. The frontend uses it to render an "applicable Canadian sales tax (GST/HST/PST) will be calculated at checkout" disclosure when on. Whether a given checkout *actually* charges tax depends on the buyer's billing address and the dashboard's tax registrations — see `docs/operations.md` § Stripe Tax.
```json
{
  "enabled": true,
  "tax_enabled": false,
  "packs": [
    { "sku": "small",  "credits": 50,  "display_price": "$5",  "bonus_label": null },
    { "sku": "medium", "credits": 250, "display_price": "$20", "bonus_label": "12% bonus" }
  ]
}
```

### `POST /me/credits/checkout`
Per-route rate limit: 5/min. Creates a Stripe Checkout Session for the given SKU and returns the hosted-page URL. The frontend `window.location.assign`s to that URL. The actual credit grant happens via the `POST /webhooks/stripe` handler after payment completion.
```json
// request
{ "sku": "small" }
// response
{ "url": "https://checkout.stripe.com/c/pay/cs_test_…", "session_id": "cs_test_…" }
```

## Me — corrections

### `GET /me/corrections`
The caller's own correction submissions (up to 200, newest first). Extends the public `CorrectionSubmission` shape with `credits_earned` (integer, 0 when no reward has landed):
```json
{
  "corrections": [
    { "id": "uuid", "subject_type": "politician", "subject_id": "uuid",
      "issue": "…", "proposed_fix": "…", "evidence_url": null,
      "status": "applied", "reviewer_notes": "Fixed.",
      "received_at": "2026-04-24T…", "resolved_at": "2026-04-24T…",
      "credits_earned": 10 }
  ]
}
```

## Rate-limit requests

### `GET /me/rate-limit-requests`
The caller's own rate-limit increase requests (up to 20, newest first).

### `POST /me/rate-limit-requests`
Per-route rate limit: 3/hour. One-pending-per-user: returns 409 if the caller already has an unresolved request.
```json
// request
{ "reason": "Covering the upcoming federal election, need higher report volume", "requested_tier": "extended" }
// response 201
{ "id": "uuid", "reason": "...", "requested_tier": "extended", "status": "pending", "admin_response": null, "created_at": "...", "resolved_at": null }
```

## Stripe webhook

### `POST /webhooks/stripe`
Not called by clients — registered in the Stripe dashboard as the endpoint for `checkout.session.completed` events. Verifies the `Stripe-Signature` header before any DB write. Two-layer idempotency via `stripe_webhook_events.id` PK + `credit_ledger (kind, reference_id)` partial unique index. Returns 200 with `{ received: true }` on success, `{ received: true, duplicate: true }` on re-delivery, `{ received: false, reason: "stripe not configured" }` 200 when disabled, 400 on signature failure.

## Admin — user management (phase 1a additions)

All routes under `/admin/*` require `is_admin=true` on the session user plus CSRF on mutations.

### `GET /admin/users`
Query: `?q=<email-substring>&limit=<n>` (limit 1–100, default 20). Returns users matching the email ILIKE pattern.

### `GET /admin/users/:id`
Single user detail + current balance + ledger history (up to 100 entries, retains `reference_id`).

### `POST /admin/users/:id/grant-credits`
Admin comp flow. Body: `{ "amount": <1..100_000>, "reason": "<3..500 chars>" }`. Produces a `credit_ledger` row with `kind='admin_credit'`, `created_by_admin_id` = acting admin, `reason` = supplied note.

### `PATCH /admin/users/:id`
Body: `{ "rate_limit_tier": "default" | "extended" | "unlimited" | "suspended" }`. Suspending a user takes effect on their next request via `requireUser`'s re-read.

### `PATCH /admin/corrections/:id`
Body: `{ "status": Status, "reviewer_notes"?: string | null }`. On transition to `status='applied'` for a non-anonymous correction, the submitter receives a `credit_ledger` grant (kind `correction_reward`, amount = `CORRECTION_REWARD_CREDITS`) and a notification email. Idempotent via the `(kind, reference_id)` partial unique index — re-applying the same correction does not double-grant and does not re-notify. Response extends the updated correction with a `credit_reward` block:
```json
{
  "credit_reward": {
    "credits": 10,
    "granted": true,          // a fresh ledger row was inserted
    "already_granted": false, // true on idempotent re-applies
    "eligible": true          // true when status=applied and user_id is set
  }
}
```

### `GET /admin/rate-limit-requests`
Query: `?status=pending|approved|denied&limit=<n>`. Queue of user-submitted increase requests.

### `PATCH /admin/rate-limit-requests/:id`
Body: `{ "status": "approved"|"denied", "admin_response": "<message to user>", "apply_tier": "extended"|"unlimited"? }`. When approved with `apply_tier`, the user's `rate_limit_tier` is bumped atomically.

## Premium reports (phase 1b)

All `/reports/*` and `/me/reports/*` routes (other than the public `meta`) require a signed-in session; mutating routes additionally require the `sw_csrf` header.

### `GET /reports/meta`
Public. Reports whether the feature is enabled (both `OPENROUTER_API_KEY` and `OPENROUTER_REPORT_MODEL` set), the configured model id, and the cost-formula knobs the frontend uses to render the confirm modal:
```json
{
  "enabled": true,
  "model": "anthropic/claude-sonnet-4.6",
  "bucket_size": 10,
  "max_chunks": 300,
  "base_cost_credits": 5,
  "per_chunk_bucket_cost": 1
}
```

### `POST /reports/estimate`
Body: `{ "politician_id": "uuid", "query": "carbon tax" }`. Returns the per-server-side cost calculation:
```json
{
  "politician": { "id": "uuid", "name": "Ziad Aboultaif" },
  "query": "carbon tax",
  "estimated_chunks": 80,
  "candidate_chunks": 80,
  "estimated_credits": 13,
  "capped": false,
  "balance": 50,
  "sufficient": true
}
```
Pure read; no hold placed. `capped: true` indicates `candidate_chunks > REPORT_MAX_CHUNKS`.

### `POST /reports`
Per-route rate limit: 5/min. Re-runs the estimate server-side, checks the tier daily cap, then atomically inserts a `report_jobs` row + a `holdCredits` ledger row inside a single transaction. Returns:
```json
{ "id": "uuid", "estimated_credits": 13, "balance_after": 37 }
```
Error responses: `402` for insufficient credits (`{ balance, required }`); `429` if the tier daily cap is exceeded (`{ tier, limit, count }`); `400` if no candidate quotes match.

### `GET /me/reports`
Newest-50 list of caller's reports.
```json
{
  "reports": [
    {
      "id": "uuid",
      "politician_id": "uuid",
      "politician_name": "Ziad Aboultaif",
      "politician_slug": "ziad-aboultaif",
      "query": "carbon tax",
      "status": "succeeded",
      "summary": "…",
      "estimated_credits": 13,
      "chunk_count_actual": 78,
      "created_at": "...",
      "finished_at": "...",
      "error": null
    }
  ]
}
```

### `GET /me/reports/:id`
Ownership-gated viewer payload. **Returns 404 (not 403) for non-owners** to avoid id-enumeration.
```json
{
  "report": {
    "id": "uuid",
    "politician_id": "uuid",
    "politician_name": "...",
    "politician_party": "Conservative",
    "query": "carbon tax",
    "status": "succeeded",
    "html": "<p>…</p>",
    "summary": "…",
    "chunk_count_actual": 78,
    "estimated_credits": 13,
    "model_used": "anthropic/claude-sonnet-4.6",
    "error": null,
    "created_at": "...",
    "finished_at": "..."
  }
}
```

### `POST /me/reports/:id/bug-report`
Caller flags a quality issue with their own report. Body: `{ "message": "<10..2000 chars>" }`. Returns `{ id }` on 201. Does not auto-refund — admins triage at `/admin/bug-reports`.

## Admin — reports (phase 1b additions)

### `GET /admin/reports`
Query: `?status=queued|running|succeeded|failed|refunded&q=<email-or-query-substring>&limit=1..200` (default 50). Operator triage view with token counts and ledger linkage.

### `GET /admin/reports/:id`
Full row including raw `html`, `error`, `tokens_in/out`, `hold_ledger_id`.

### `POST /admin/reports/:id/refund`
Body: `{ "reason": "<3..500 chars>" }`. Idempotent. Two modes:
- If the hold is still `held` (job is queued / running / failed but worker hasn't committed): flips it to `refunded` (`releaseHold` path). Response `{ refunded: true, mode: "released_hold", credits: N }`.
- If the hold has already `committed` (job succeeded): inserts a fresh compensating `admin_credit` row matching the original cost. Response `{ refunded: true, mode: "compensating_admin_credit", credits: N }`.

### `GET /admin/bug-reports`
Query: `?status=open|reviewing|resolved|dismissed&limit=1..200`.

### `PATCH /admin/bug-reports/:id`
Body: `{ "status": "<status>", "admin_notes"?: "<= 2000 chars or null>" }`. `resolved_at` is auto-set to `now()` on transition to `resolved` / `dismissed`.

## Health

### `GET /health`
```json
{ "ok": true, "db": true }
```

## Error responses

Cross-cutting error shapes for the v1.0 search surface (and most other endpoints — Fastify defaults).

**`400 Bad Request`** — zod validation failure or business-logic precondition (e.g., grouped `/speeches` without `q`, `parliament_number` without `session_number`, `/speeches` with neither query nor structural filter). Body is the Fastify default:

```json
{ "statusCode": 400, "error": "Bad Request", "message": "<zod error or precondition text>" }
```

**`404 Not Found`** — missing `anchor_chunk_id` (body `{ "statusCode": 404, "error": "Not Found", "message": "anchor_not_found" }`), missing `/chunks/:id`, or owner-gated 404 on `/me/reports/:id` for non-owners (deliberate, not 403, to prevent id-enumeration).

**`429 Too Many Requests`** — only on `/search/politician-quotes` today (limit 60/min keyed on `expand-quotes:<userId>`). Standard `Retry-After` header in seconds.

**`503 Service Unavailable`** — query embedding failed because the TEI service is unreachable or returned non-OK. Fastify `setErrorHandler` (in `services/api/src/index.ts`) maps the internal `EmbeddingServiceUnavailableError` thrown by `encodeQuery()` (in `services/api/src/routes/search.ts`) to a stable code so the frontend can show a "search temporarily unavailable, retry shortly" surface instead of a generic 500:

```json
{ "code": "embedding_service_unavailable", "message": "<detail>" }
```

`503` is distinct from a generic 500: the API is up; only the embedding inference path is degraded. Callers should treat it as transient and retry with backoff. The scanner-side ingest pipeline has its own multi-attempt retry layer for the same upstream — `503` here only ever surfaces on interactive search calls.

**`500 Internal Server Error`** — unhandled exception. Bug — please file. Body is the Fastify default with the exception message redacted.
