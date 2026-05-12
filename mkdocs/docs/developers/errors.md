---
title: Errors
description: HTTP error response shapes for the public developer API — 400, 401, 404, 429, 503.
---

# Errors

All error responses are JSON with a consistent shape. The five status
codes you might see:

## `400 Bad Request`

Request validation failed (zod error) or a precondition wasn't met
(e.g., `parliament_number` supplied without `session_number` on the
internal search API).

```http
HTTP/1.1 400 Bad Request
Content-Type: application/json

{
  "statusCode": 400,
  "error": "Bad Request",
  "message": "querystring.status: Invalid enum value. Expected 'live' | 'partial' | 'blocked' | 'none'"
}
```

The `message` field carries the zod path + reason and is safe to log /
surface to the developer (you).

## `401 Unauthorized`

The bearer token is missing, malformed, expired, revoked, or for the
wrong environment (a `cpd_test_…` token sent to the live API).
Anonymous calls **don't** 401 — they fall back to the IP-based rate
limit. You'll only see 401 if you sent an `Authorization` header that
didn't validate.

```http
HTTP/1.1 401 Unauthorized
Content-Type: application/json

{
  "error": "invalid or expired api key"
}
```

Possible `error` strings:

- `"missing bearer token (Authorization: Bearer cpd_…)"` — header
  present but doesn't match the `Bearer cpd_…` shape.
- `"invalid or malformed api key"` — token failed the checksum check
  (typo, truncation, or wrong-environment).
- `"invalid or expired api key"` — token's checksum was good but the
  key is unknown / revoked / expired / for a suspended account.

If you get a 401 unexpectedly, check that:

- Your token hasn't been [revoked](./authentication.md#revoking-a-key)
  on `/account/api-keys`.
- You're not sending a test-mode token to the live API or vice versa.
- The token's `expires_at` (if you set one) hasn't passed.

## `403 Forbidden`

You're authenticated but your tier OR scope doesn't authorize this
endpoint. Two flavours, distinguished by the `code` field.

**`code: "insufficient_tier"`** — your billing level (free / dev /
pro) is too low. Surfaces on the pro-tier search endpoints when
called by a free or dev-tier key.

```http
HTTP/1.1 403 Forbidden
Content-Type: application/json

{
  "code": "insufficient_tier",
  "error": "Forbidden",
  "message": "this endpoint requires a pro+ tier API key. Your key is on the free tier. Subscribe or upgrade at /account/billing.",
  "required_tier": "pro",
  "current_tier": "free"
}
```

To resolve: subscribe at
[`/account/billing`](https://canadianpoliticaldata.org/account/billing).
Existing keys auto-promote within seconds of the Stripe webhook
landing — no need to mint new keys.

**`code: "insufficient_scope"`** — your key's capability flags don't
include a required scope. Surfaces on the bulk-export endpoints
when called by a key that didn't tick the `read:bulk` checkbox at
create time.

```http
HTTP/1.1 403 Forbidden
Content-Type: application/json

{
  "code": "insufficient_scope",
  "error": "Forbidden",
  "message": "this endpoint requires the 'read:bulk' scope. Your key has [read:public]. Create a new key with the scope at /account/api-keys, or rotate this one and tick the scope checkbox.",
  "required_scope": "read:bulk",
  "current_scopes": ["read:public"]
}
```

To resolve: create a new key at
[`/account/api-keys`](https://canadianpoliticaldata.org/account/api-keys)
with the required scope ticked. Per-key scope changes-after-creation
aren't supported in v1 — rotate the key with the new scope set OR
create a fresh key for the new workflow.

Anonymous callers see `401` (caught by `requireApiKey`), not 403 —
the tier/scope gates only run after authentication succeeds.

## `404 Not Found`

The resource doesn't exist. For `/politicians/:id`, returned when the
UUID is malformed OR when no politician has that id.

```http
HTTP/1.1 404 Not Found
Content-Type: application/json

{
  "statusCode": 404,
  "error": "Not Found"
}
```

## `429 Too Many Requests`

You've exceeded your tier's hourly rate limit. The `Retry-After`
header tells you how many seconds until the bucket resets.

```http
HTTP/1.1 429 Too Many Requests
Retry-After: 2387
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 0

{
  "statusCode": 429,
  "error": "Too Many Requests",
  "message": "Rate limit exceeded, retry in 2387 seconds"
}
```

See [Rate limiting](./rate-limiting.md) for the per-tier limits and
the recommended retry strategy.

## `503 Service Unavailable`

Two distinct flavours, distinguished by the `code` field:

**`code: "search_overloaded"`** — the public-search TEI semaphore is
at capacity (max 2 concurrent embed requests + max 6 queued). This
fires on `/search/speeches`, `/search/speeches/count`, `/search/facets`
under burst load. Always paired with `Retry-After`:

```http
HTTP/1.1 503 Service Unavailable
Retry-After: 5
Content-Type: application/json

{
  "code": "search_overloaded",
  "error": "Service Unavailable",
  "message": "public search service is at capacity, retry shortly"
}
```

Respect `Retry-After`. The semaphore drains as in-flight requests
complete (typically <1s each); 5 seconds is usually enough for the
queue to clear. See [Rate limiting](./rate-limiting.md#tei-semaphore-on-paid-search)
for the full semaphore design.

**`code: "embedding_service_unavailable"`** — the underlying TEI
service is down or returning errors. Less frequent than overload
(TEI has its own auto-restart layer); when it does fire, treat as
transient and retry with exponential backoff (start 1s, cap 30s).
No `Retry-After` header — the duration is unpredictable.

```http
HTTP/1.1 503 Service Unavailable
Content-Type: application/json

{
  "code": "embedding_service_unavailable",
  "message": "embedding service did not return ok"
}
```

## `500 Internal Server Error`

Unhandled exception in the API. **Bug — please file** at
[GitHub Issues](https://github.com/adminatthebunker/CanadianPoliticalData/issues)
with the `reqId` from the response headers (Fastify includes one on
every request) so we can correlate with server logs.

```http
HTTP/1.1 500 Internal Server Error
Content-Type: application/json

{
  "statusCode": 500,
  "error": "Internal Server Error",
  "message": "Something went wrong"
}
```

The exception message is redacted from the response body for security
(no stack traces, no SQL state). Server-side logs have the full
context.

## Error handling pattern

A robust client should branch on these five codes:

```python
import time
import requests

def call_api(url, headers):
    for attempt in range(3):
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            return r.json()
        if r.status_code == 429:
            time.sleep(int(r.headers.get("Retry-After", "60")))
            continue
        if r.status_code == 503:
            time.sleep(min(2 ** attempt, 30))  # exponential backoff
            continue
        if r.status_code in (400, 401, 403, 404):
            # Permanent — don't retry. 403 means upgrade your tier.
            r.raise_for_status()
        if r.status_code == 500:
            # Transient bug; retry once, then give up
            if attempt == 0:
                time.sleep(2)
                continue
            r.raise_for_status()
    raise RuntimeError(f"Exhausted retries for {url}")
```
