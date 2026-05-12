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

That's it. No SDK to install, no credentials to negotiate. **Anonymous
calls also work** at a lower rate limit — useful for prototyping
before you commit to creating a key.

## Interactive reference

The full endpoint reference lives in **[Swagger UI](https://canadianpoliticaldata.org/api/public/v1/docs/)**
with "Try it out" buttons that hit the live API. Raw OpenAPI spec is
at **[`/api/public/v1/docs/json`](https://canadianpoliticaldata.org/api/public/v1/docs/json)**
(or `/yaml`) for client-codegen tools.

## Tiers and pricing

| Tier | Rate limit | Cost | How to get it |
|---|---|---|---|
| Anonymous | 30 / hr per IP | Free | No setup needed |
| Free | 60 / hr per key | Free | Create an API key at `/account/api-keys` |
| Developer | 1,000 / hr per key | $20 / mo | Subscribe at [`/account/billing`](https://canadianpoliticaldata.org/account/billing) |
| Pro | 10,000 / hr per key | $200 / mo | Subscribe at `/account/billing` |

When you subscribe, **all of your existing API keys auto-promote** to
the new tier — no need to mint new keys or update your integrations.
On cancellation, your tier stays at the higher limit until the period
end (you keep what you paid for), then drops to the free tier.

## What's in v1.0

Three read endpoints in v1.0 (frozen 2026-05-12):

- **`GET /coverage`** — current state of all 14 Canadian jurisdictions
  (federal + 10 provinces + 3 territories): bills/Hansard/votes/committees
  pipelines status + row counts. The honesty surface for what we cover.
- **`GET /jurisdiction-sources`** — the same data as `/coverage` but
  as a flat per-jurisdiction list, no summary rollup. For callers
  building their own dashboards.
- **`GET /politicians/:id`** — single politician with their currently-
  active websites (with infrastructure scan: hosting provider, country,
  CDN/CMS detection, sovereignty tier 1-6) and constituency boundary
  GeoJSON.

More endpoints land in future releases. The internal `/api/v1/search/*`
surface is **also** stable as v1.0 (see [`docs/api.md`](https://github.com/adminatthebunker/CanadianPoliticalData/blob/main/docs/api.md)
in the repo) but isn't yet exposed publicly — semantic search over the
full Hansard corpus is the next planned addition once the pro-tier
TEI concurrency wiring lands.

## Topics

- **[Authentication](./authentication.md)** — token format, key
  creation, rotation, revocation.
- **[Rate limiting](./rate-limiting.md)** — per-tier limits, headers,
  429 handling.
- **[Errors](./errors.md)** — 400 / 401 / 404 / 429 / 503 catalog.

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
