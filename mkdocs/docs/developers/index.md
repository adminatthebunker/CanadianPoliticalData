---
title: Developer API
description: Read-only HTTP API access to the public Canadian political dataset — politicians, jurisdictions, coverage stats — via bearer-token-authenticated endpoints with per-tier rate limits.
---

# Developer API

Build on top of Canadian Political Data programmatically. The public
**`/api/public/v1/*`** surface gives you read access to the same
dataset that powers the website — politicians, jurisdictions, coverage
stats — over a stable, versioned HTTP API.

This is the **public-facing** surface. It's separate from the internal
`/api/v1/*` API that backs the website itself; the public surface has
its own URL prefix, its own CORS posture (permissive `*` so you can
call from a browser), and its own rate limits keyed on API tokens you
issue from your account.

## Quickstart

1. **[Sign in](https://canadianpoliticaldata.org/login)** with a magic
   link sent to your email.
2. Go to **[`/account/api-keys`](https://canadianpoliticaldata.org/account/api-keys)**
   and click "New API key." The full token is shown once — copy it
   into your secrets manager. Storage is HMAC-hashed; we can't recover
   it after this page closes.
3. Make your first call:

   ```bash
   curl -H 'Authorization: Bearer cpd_live_…' \
        https://canadianpoliticaldata.org/api/public/v1/coverage \
     | jq '.summary'
   ```

   ```json
   {
     "total": 14,
     "live": 9,
     "partial": 3,
     "blocked": 2,
     "none": 0
   }
   ```

4. **Or try semantic search** — every authenticated tier (free / dev /
   pro) can query the full Hansard corpus:

   ```bash
   curl -H 'Authorization: Bearer cpd_live_…' \
        'https://canadianpoliticaldata.org/api/public/v1/search/speeches?q=carbon%20tax&limit=3' \
     | jq '.items[] | {politician_name, party, spoken_at, similarity, text: (.text[:140])}'
   ```

   Free-tier keys get 5 semantic queries per hour (separate from the
   general 60/hr API budget) — enough to prototype, not enough to
   stress the GPU.

That's it. No SDK to install, no credentials to negotiate. **Anonymous
calls also work** for non-search endpoints at a lower rate limit —
useful for prototyping before you commit to creating a key.

## Interactive reference

The full endpoint reference lives in **[Swagger UI](https://canadianpoliticaldata.org/api/public/v1/docs/)**
with "Try it out" buttons that hit the live API. Raw OpenAPI spec is
at **[`/api/public/v1/docs/json`](https://canadianpoliticaldata.org/api/public/v1/docs/json)**
(or `/yaml`) for client-codegen tools.

## Tiers and pricing

Every authenticated key has **two independent rate-limit buckets** —
one for general API calls and one for the GPU-backed semantic-search
endpoints:

| Tier | General bucket | Semantic-search bucket | Cost | How to get it |
|---|---|---|---|---|
| Anonymous | 30 / hr per IP | not available | Free | No setup needed |
| Free | 60 / hr per key | **5 / hr per key** | Free | Create an API key at `/account/api-keys` |
| Developer | 1,000 / hr per key | **100 / hr per key** | $20 / mo | Subscribe at [`/account/billing`](https://canadianpoliticaldata.org/account/billing) |
| Pro | 10,000 / hr per key | **10,000 / hr per key** | $200 / mo | Subscribe at `/account/billing` |

The two buckets are independent — blowing through your hourly
semantic-search budget doesn't stop you from calling `/bills` or
`/coverage`. See [Rate limiting](./rate-limiting.md) for the full
mechanics including the GPU concurrency semaphore.

When you subscribe, **all of your existing API keys auto-promote** to
the new tier in both buckets — no need to mint new keys or update
your integrations. On cancellation, your tier stays at the higher
limit until the period end (you keep what you paid for), then drops
to the free tier.

## What's in v1.0

19 endpoints across eight tags:

**Reference data** (any tier including anonymous):

- **`GET /coverage`** — current state of all 14 Canadian jurisdictions
  (federal + 10 provinces + 3 territories): bills/Hansard/votes/committees
  pipelines status + row counts.
- **`GET /jurisdiction-sources`** — flat per-jurisdiction list, no
  summary rollup.
- **`GET /politicians/:id`** — single politician with currently-active
  websites (hosting provider, country, CDN/CMS, sovereignty tier 1-6)
  and constituency boundary GeoJSON.

**Legislative data** (free tier; authenticated):

- **`GET /bills`**, **`GET /bills/{id}`**, **`GET /bills/{id}/events`**,
  **`GET /bills/{id}/sponsors`** — federal + provincial legislation
  with stage-transition events and FK-joined sponsors. See [Bills](./bills.md).
- **`GET /votes`**, **`GET /votes/{id}`**, **`GET /votes/{id}/positions`** —
  recorded chamber votes (divisions, voice, acclamation, consensus) with
  per-politician position breakdowns. See [Votes](./votes.md).
- **`GET /committees/meetings`** — distinct committee meetings derived
  from the speeches table. See [Committees](./committees.md).

**Search auxiliaries** (any tier including anonymous; no embeddings, fast lookups):

- **`GET /search/sessions`** — parliament + session catalog for the
  cascading filter dropdown.
- **`GET /search/chunks/:id`** — anchor-chunk lookup by UUID.
- **`GET /search/meta`** — backfill-progress meta (`total_chunks`,
  `embedded_chunks`, `coverage`).

**Semantic search** (any authenticated tier; uses the separate
semantic-search rate-limit bucket — free=5/hr, dev=100/hr,
pro=10000/hr — and the shared TEI concurrency semaphore):

- **`GET /search/speeches`** — hybrid HNSW + BM25 search over the full
  Hansard corpus. Two modes: `timeline` (default; flat chunk list with
  per-result `similarity` score) and `politician` (grouped by
  speaker, with their top-N matching chunks). Supports
  `speech_type=committee` to scope to committee transcripts.
- **`GET /search/speeches/count`** — count-only sibling for off-path
  count staging when paginating large result sets.
- **`GET /search/facets`** — aggregations (party, politician, year,
  language) over the top-N candidate pool. Powers analytics tabs.

All three semantic-search routes share a TEI semaphore (max 2
concurrent + 6 queued = 8 slots total) — past that they 503 with
`Retry-After: 5` to prevent any single client from starving the GPU.
See [Rate limiting](./rate-limiting.md#tei-semaphore-on-semantic-search)
for details on both the per-tier bucket and the GPU semaphore.

**Bulk export** (`read:bulk` scope required — orthogonal to tier):

- **`GET /exports/dumps`** — list current full-dataset dump artifacts
  (filename, size, modified-at, kind).
- **`GET /exports/dumps/:filename`** — stream a specific dump file
  (`pg_dump --schema=public` custom-format archive + integrity
  checksum + manifest).

Same files served anonymously at
[`/datasets/`](https://canadianpoliticaldata.org/datasets/) — the
API surface adds auth + per-key metering. See
[Bulk export](./bulk-export.md) for the full guide including
`pg_restore` instructions.

## Topics

- **[Authentication](./authentication.md)** — token format, key
  creation, rotation, revocation, scopes.
- **[Rate limiting](./rate-limiting.md)** — per-tier limits, headers,
  429 handling, TEI semaphore.
- **[Bills](./bills.md)** — legislation, events, sponsors.
- **[Votes](./votes.md)** — chamber votes + per-politician positions.
- **[Committees](./committees.md)** — committee meetings and transcript search.
- **[Bulk export](./bulk-export.md)** — `read:bulk` scope,
  `pg_dump` artifacts, restore guide.
- **[Errors](./errors.md)** — 400 / 401 / 403 / 404 / 429 / 503
  catalog.

## Stability

`/api/public/v1/*` is **frozen as v1.0**. New optional query parameters
and response fields may be added without a version bump; field
removals or renames require a v2 with at least 6 months notice and a
`Sunset` HTTP header. See the
[Stability & Versioning](https://github.com/adminatthebunker/CanadianPoliticalData/blob/main/docs/api.md#stability--versioning)
section of the internal API reference for the full policy.

## Help

- Open an issue on [GitHub](https://github.com/adminatthebunker/CanadianPoliticalData/issues).
- Email **[admin@thebunkerops.ca](mailto:admin@thebunkerops.ca)** for
  partnership / commercial-use questions.
