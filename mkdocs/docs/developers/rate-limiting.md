---
title: Rate limiting
description: Per-tier rate limits, response headers, retry handling, and how to upgrade if you need more.
---

# Rate limiting

Every public API request is rate-limited per **API key** (when
authenticated) or per **source IP** (when anonymous). Limits are
hourly buckets — the bucket resets one hour after the first request
in it.

## Two buckets per key

Every authenticated key has **two independent rate-limit buckets**:

- **General bucket** — for navigation endpoints (`/coverage`,
  `/politicians/:id`, `/bills`, `/votes`, `/committees/meetings`, the
  free search auxiliaries, exports, …). Higher per-tier limits.
- **Semantic-search bucket** — for the TEI-embedded endpoints
  (`/search/speeches`, `/search/speeches/count`, `/search/facets`).
  Lower per-tier limits because each call hits the GPU.

The two buckets are independent: blowing through your hourly semantic
budget doesn't stop you from calling `/bills` or `/coverage`, and
vice-versa.

## Limits by tier

| Tier | General bucket | Semantic-search bucket | How to get it |
|---|---|---|---|
| Anonymous | 30 / hr (per source IP) | not available (sign in for free key) | No setup — call without an `Authorization` header |
| Free | 60 / hr | **5 / hr** | [Create a key](./authentication.md#creating-a-key) |
| Developer ($20/mo) | 1,000 / hr | **100 / hr** | [Subscribe](https://canadianpoliticaldata.org/account/billing) |
| Pro ($200/mo) | 10,000 / hr | **10,000 / hr** | [Subscribe](https://canadianpoliticaldata.org/account/billing) |

All buckets are per-API-key, sliding-hourly. When you subscribe to dev
or pro, **all of your existing keys auto-promote** in both buckets —
you don't need to mint new keys.

> **Anonymous semantic search is not available** — the three
> `/search/speeches*` and `/search/facets` endpoints require an API
> key. The navigation auxiliaries (`/search/sessions`,
> `/search/chunks/:id`, `/search/meta`) accept anonymous callers
> against the general IP bucket.

## Response headers

Every response (success and 429) includes the standard
`X-RateLimit-*` headers so you can pace your client without
hammering and backing off:

```http
HTTP/1.1 200 OK
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 47
X-RateLimit-Reset: 2387
Cache-Control: public, max-age=300
```

- **`X-RateLimit-Limit`** — your current bucket's max (depends on
  tier).
- **`X-RateLimit-Remaining`** — calls left in this bucket.
- **`X-RateLimit-Reset`** — seconds until the bucket resets.

When the bucket is empty, you get a `429 Too Many Requests`:

```http
HTTP/1.1 429 Too Many Requests
Retry-After: 2387
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 2387
Content-Type: application/json

{
  "statusCode": 429,
  "error": "Too Many Requests",
  "message": "Rate limit exceeded, retry in 2387 seconds"
}
```

The `Retry-After` header is in seconds — your client should respect it
rather than retrying immediately.

## Retry strategy

For 429 responses:

```python
import time
import requests

def get_with_retry(url, headers, max_attempts=3):
    for attempt in range(max_attempts):
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 429:
            retry_after = int(r.headers.get("Retry-After", "60"))
            # Cap the wait to something reasonable for interactive use
            time.sleep(min(retry_after, 300))
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError(f"Exhausted retries for {url}")
```

For 503 responses (rare — occurs only on the search surface when the
embedding service is degraded), retry with exponential backoff. See
the [errors guide](./errors.md#503-service-unavailable).

## Caching

Most public endpoints set `Cache-Control: public, max-age=N` so
intermediate caches (your CDN, your local HTTP cache) can serve
repeats without consuming your rate-limit bucket:

| Endpoint | Cache TTL |
|---|---|
| `/coverage` | 5 minutes |
| `/jurisdiction-sources` | 5 minutes |
| `/politicians/:id` | 1 minute |

If you're hitting the rate limit, **enable caching in your client**
before upgrading tiers. A simple in-process LRU + TTL keyed on URL
will dramatically cut your API call volume for any read-heavy
workload — these endpoints don't change second-to-second.

## Upgrading

If you've optimized your client and still need more headroom:

1. Visit [`/account/billing`](https://canadianpoliticaldata.org/account/billing).
2. Pick **Developer** ($20/mo, 1,000/hr) or **Pro** ($200/mo,
   10,000/hr).
3. Pay with any major card via Stripe-hosted Checkout.
4. **All of your existing API keys auto-promote** to the new tier.
   The next call you make will see `X-RateLimit-Limit: 1000` (or
   `10000` for pro). No code change required.

Rate-limited authenticated calls are also recorded in an audit log
(`private.api_key_events.event_type = 'rate_limited'`) so you can
look back at usage patterns when deciding whether to upgrade.

## TEI semaphore on semantic search

The semantic-search endpoints (`/search/speeches`,
`/search/speeches/count`, `/search/facets`) share a **GPU concurrency
budget** independent of your tier's rate limit. The embedding step
runs on a single GPU and serves both interactive search and
background ingest, so we cap simultaneous embed requests across all
public-API callers regardless of tier.

- **Max concurrent**: 2 embed requests in flight at a time.
- **Max queued**: 6 requests waiting for a slot.
- **Total slots**: 8.

When all 8 slots are full, additional requests get refused immediately
with **`503 Service Unavailable`** + **`Retry-After: 5`** so your
client can back off cleanly rather than waiting minutes:

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

This is **independent of** both the general and semantic per-tier
hourly rate limits — it's a third, orthogonal protection layer:

- Blow through your semantic-search hourly bucket: **429**.
- Hit the GPU concurrency ceiling because eight callers (regardless of
  tier) are all firing at once: **503 + `Retry-After: 5`**.
- Hit your general bucket on `/bills` / `/coverage` etc.: **429** —
  separate from the semantic bucket.

## Quotas vs. rate limits

The current limits are **rate** limits (sliding hourly buckets), not
**quota** limits (monthly caps). There's no "max requests per month"
ceiling — if your bucket has room, you can call. The
`api_usage_daily` counter table exists in the schema but is reserved
for future operator-side analytics; it's not enforced as a quota
today.
