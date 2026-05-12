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

A backend dependency is degraded. Currently only surfaces on the
internal search API (`/api/v1/search/*`) when the embedding service
is unreachable; the public API doesn't expose search yet so you won't
see this in v1.0. Documented here for forward-compat:

```http
HTTP/1.1 503 Service Unavailable
Content-Type: application/json

{
  "code": "embedding_service_unavailable",
  "message": "embedding service did not return ok"
}
```

Treat as transient. Retry with exponential backoff (start at 1s, cap
at 30s). The condition usually clears within a minute or two — the
embedding service has its own auto-restart layer.

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
        if r.status_code in (400, 401, 404):
            # Permanent — don't retry
            r.raise_for_status()
        if r.status_code == 500:
            # Transient bug; retry once, then give up
            if attempt == 0:
                time.sleep(2)
                continue
            r.raise_for_status()
    raise RuntimeError(f"Exhausted retries for {url}")
```
