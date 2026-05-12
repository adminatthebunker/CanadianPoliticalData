---
title: Rate limiting
description: Per-tier rate limits, response headers, retry handling, and how to upgrade if you need more.
---

# Rate limiting

Every public API request is rate-limited per **API key** (when
authenticated) or per **source IP** (when anonymous). Limits are
hourly buckets — the bucket resets one hour after the first request
in it.

## Limits by tier

| Tier | Hourly limit | Bucket key | How to get it |
|---|---|---|---|
| Anonymous | 30 | Source IP | No setup — call without an `Authorization` header |
| Free | 60 | API key id | [Create a key](./authentication.md#creating-a-key) |
| Developer ($20/mo) | 1,000 | API key id | [Subscribe](https://canadianpoliticaldata.org/account/billing) |
| Pro ($200/mo) | 10,000 | API key id | [Subscribe](https://canadianpoliticaldata.org/account/billing) |

When you subscribe to dev or pro, **all of your existing keys
auto-promote** — you don't need to mint new keys.

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

## Quotas vs. rate limits

The current limits are **rate** limits (sliding hourly buckets), not
**quota** limits (monthly caps). There's no "max requests per month"
ceiling — if your bucket has room, you can call. The
`api_usage_daily` counter table exists in the schema but is reserved
for future operator-side analytics; it's not enforced as a quota
today.
