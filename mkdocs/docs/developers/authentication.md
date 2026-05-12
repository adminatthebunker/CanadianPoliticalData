---
title: Authentication
description: How to mint, use, rotate, and revoke API keys for the Canadian Political Data public developer API.
---

# Authentication

The public developer API uses **bearer tokens** sent in the standard
`Authorization` header. You mint and manage your own keys at
[`/account/api-keys`](https://canadianpoliticaldata.org/account/api-keys)
after signing in.

Anonymous calls also work, at the lower 30-req/hr-per-IP rate limit.
You only need a key when you want the higher free-tier limit (60/hr)
or one of the paid tiers (1,000/hr or 10,000/hr).

## Token format

Every key looks like this:

```
cpd_live_AbC123XyZ987def012ghi3_4Bz9Q1
└┬┘ └┬─┘ └─────────┬─────────┘ └──┬──┘
 │   │             │              │
 │   │             │              └── 6-char checksum (HMAC-derived;
 │   │             │                  rejects typos client-side)
 │   │             └── 22 chars of base62 randomness (132 bits entropy)
 │   └── env: "live" in production, "test" in dev/staging
 └── scheme prefix; brand-namespaced so a leaked token in logs
     is greppable
```

Tokens **only work in their own environment** — a `cpd_test_…` token
won't authenticate against the production live API and vice versa.
Same posture as Stripe's per-mode customer / price IDs.

Tokens are **shown once at creation** (and once more if you rotate
them) — copy into your secrets manager immediately. Storage is
HMAC-SHA256 hashed with a server-side pepper, so we cannot recover
the full token after the dialog closes. If you lose it, rotate the
key (or revoke and create a new one).

## Sending a token

Standard `Authorization: Bearer <token>` header:

```bash
curl -H 'Authorization: Bearer cpd_live_…' \
     https://canadianpoliticaldata.org/api/public/v1/coverage
```

```python
import requests

headers = {"Authorization": "Bearer cpd_live_..."}
r = requests.get(
    "https://canadianpoliticaldata.org/api/public/v1/coverage",
    headers=headers,
    timeout=10,
)
r.raise_for_status()
data = r.json()
```

```javascript
const r = await fetch(
  "https://canadianpoliticaldata.org/api/public/v1/coverage",
  { headers: { Authorization: `Bearer ${process.env.CPD_API_KEY}` } },
);
const data = await r.json();
```

## Creating a key

1. Sign in at [`/login`](https://canadianpoliticaldata.org/login)
   (magic link).
2. Navigate to [`/account/api-keys`](https://canadianpoliticaldata.org/account/api-keys).
3. Click **"+ New API key"**.
4. Give it a name — use this to remember which integration it's for
   (`production worker`, `staging-cron`, `personal-cli`).
5. Optional: set an expiry in days (1 – 3,650). Leave blank for no
   expiry. Even non-expiring keys can be rotated or revoked at any
   time.
6. Click **"Create key"**. The full token appears in a banner at the
   top of the page. **Copy it now** — this is the only time it's
   shown.

## Rotating a key

Use rotation when:

- You suspect the token leaked (committed to a public repo, shared
  in a screenshot).
- You want to swap to a fresh token on a regular cadence.
- A team member who knew the token has left.

Rotation creates a **new** token while keeping the **old** one valid
for **24 hours** (the grace window). This lets you swap your
integrations to the new token without downtime:

1. On `/account/api-keys`, click **"Rotate"** on the key.
2. Confirm. The new token is shown once — copy it.
3. Update your integrations to use the new token within 24 hours.
4. After 24 hours, the old token automatically stops working.

The new key inherits the old key's name, tier, scopes, and expiry
date. The old key's `rotated_from_id` is recorded for audit.

## Revoking a key

Revocation is **immediate** and **irreversible** — no grace window.
Use it when the key is actively compromised (you didn't have time to
rotate first) or no longer needed.

1. On `/account/api-keys`, click **"Revoke"** on the key.
2. Confirm. The key 401s on the next request.

The row stays in the database with `revoked_at` set so you can audit
when the key was active. To clear it from the list visually, just
ignore revoked rows — they're displayed with a "revoked" chip.

## Plan + key tier interaction

When you subscribe to **Developer** ($20/mo) or **Pro** ($200/mo) at
[`/account/billing`](https://canadianpoliticaldata.org/account/billing),
**all of your existing keys auto-promote** to the new tier. You don't
need to mint new keys or update integrations — same token, higher
rate limit.

When you cancel, your keys stay at the higher tier until the period
ends (you keep what you paid for), then auto-demote to free.

If a payment goes past-due, your tier stays active during Stripe's
dunning window. If Stripe ultimately gives up, the subscription is
deleted and your keys demote to free.

### Pro-tier-only endpoints

The semantic-search endpoints (`/search/speeches`,
`/search/speeches/count`, `/search/facets`) are **gated to PRO tier
only** because they hit a GPU-backed embedding service. Calling them
with a free or dev-tier key returns:

```json
{
  "code": "insufficient_tier",
  "required_tier": "pro",
  "current_tier": "free"
}
```

Subscribe at
[`/account/billing`](https://canadianpoliticaldata.org/account/billing)
to unlock — your existing keys auto-promote within seconds of the
Stripe webhook landing. The free-tier auxiliaries
(`/search/sessions`, `/search/chunks/:id`, `/search/meta`) work for
any tier including anonymous.

## Scopes

Tiers and scopes are **orthogonal axes**:

- **Tier** = your billing level. Free / Developer / Pro. Governs
  rate limits and access to expensive-by-default endpoints.
- **Scope** = the capability flags your specific key carries.
  Governs access to opt-in surfaces.

Today there's one scope beyond the implicit baseline:

| Scope | What it unlocks | Default? |
|---|---|---|
| `read:public` | Every public-API endpoint that doesn't require an opt-in scope. | **Yes** — every key implicitly carries this. |
| `read:bulk` | The `/api/public/v1/exports/*` endpoints. Multi-GB `pg_dump` archives of the public dataset. | **No** — opt in at create time. |

A free-tier key CAN have `read:bulk` (no subscription required for
bulk download). A pro-tier key WITHOUT `read:bulk` can hammer search
but can't download dumps. Two orthogonal axes.

To add `read:bulk` to a new key:

1. At [`/account/api-keys`](https://canadianpoliticaldata.org/account/api-keys),
   click "+ New API key."
2. In the **Scopes** fieldset, tick the `read:bulk` checkbox.
3. Click "Create key" — the resulting token carries both
   `read:public` (implicit) and `read:bulk` (opted in).

Per-key scope changes-after-creation aren't supported in v1 — rotate
the key with the new scope set, OR create a new key for the bulk
workflow alongside your existing one. See
[Bulk export](./bulk-export.md) for the full download guide.

## Security notes

- **Never commit tokens to source control.** Use environment variables
  or a secrets manager. Tokens leaked to public repos get scraped by
  bots within hours.
- **The `cpd_` prefix is greppable.** If you suspect a leak, search
  your logs / repo / chat history for `cpd_live_` to find any
  exposure.
- **Use one key per integration.** Easier to revoke a single
  compromised integration without breaking the rest.
- **Rotate keys when team members leave** if they had access to
  your secrets.
- **The server can't read your tokens.** Storage is HMAC-hashed; even
  database-level access wouldn't recover the full token. Lost tokens
  must be rotated, not retrieved.
