---
title: Politician socials
description: Public-record social media handles and scraped posts per politician, with optional funded-by attribution from the paid monitoring pipeline.
---

# Politician socials

`/api/public/v1/politicians/{id}/socials` and
`/api/public/v1/politicians/{id}/posts` expose the social-media layer:
handles tied to each politician across nine platforms (Twitter, Bluesky,
Mastodon, Instagram, Facebook, YouTube, TikTok, LinkedIn, Threads), plus
the post archive captured by the paid scrape-monitoring pipeline.
**Free-tier** — any authenticated key works; rate-limited by
[tier](./rate-limiting.md).

For the full per-endpoint schema with "Try it out" buttons see the
**[Swagger UI](https://canadianpoliticaldata.org/api/public/v1/docs/)**
under the **Politician socials** tag.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/politicians/{id}/socials` | Live handles for one politician (opt into dead handles with `?include_dead=true`) |
| `GET` | `/politicians/{id}/posts` | Scraped posts from the paid monitoring pipeline, with attribution |

## `GET /politicians/{id}/socials`

Lists the social-media handles tied to a politician. **Filters to
`is_live=true` by default** — dead/abandoned handles drop out of the
response unless you opt back in with `?include_dead=true`.

### Path parameter

| Name | Type | Notes |
|---|---|---|
| `id` | UUID | The politician's `id`. |

### Query parameters

| Name | Type | Notes |
|---|---|---|
| `include_dead` | bool | If `true`, includes handles where `is_live=false`. Default `false`. |

### Response

```json
{
  "items": [
    {
      "platform": "twitter",
      "handle": "PierrePoilievre",
      "url": "https://twitter.com/PierrePoilievre",
      "follower_count": 1290000,
      "lifetime_post_count": 23410,
      "last_post_at": "2026-05-23T14:08:22Z",
      "last_profile_check_at": "2026-05-24T07:30:38Z",
      "last_verified_at": "2026-05-24T07:30:38Z",
      "is_live": true
    },
    {
      "platform": "bluesky",
      "handle": "pierrepoilievre.bsky.social",
      "url": "https://bsky.app/profile/pierrepoilievre.bsky.social",
      "follower_count": 4200,
      "lifetime_post_count": null,
      "last_post_at": null,
      "last_profile_check_at": null,
      "last_verified_at": "2026-05-24T07:30:38Z",
      "is_live": true
    }
  ]
}
```

Returns `404 { code: "not_found" }` for unknown politician UUIDs.

Cache-Control: `public, max-age=300`.

### Example

```bash
PID="..."  # the politician's UUID — fetch from /politicians/{id} or your own catalog
curl -s -H 'Authorization: Bearer cpd_live_…' \
  "https://canadianpoliticaldata.org/api/public/v1/politicians/$PID/socials" \
  | jq '.items[] | {platform, handle, follower_count}'
```

## `GET /politicians/{id}/posts`

Returns public-record social posts captured by the paid monitoring
pipeline. **Visible to everyone** — not gated to subscribers — matching
the public-record framing in
[the disclaimer](https://docs.canadianpoliticaldata.org/about/disclaimer/).

### Query parameters

| Name | Type | Notes |
|---|---|---|
| `platform` | comma-separated string | Filter to specific platforms, e.g. `twitter,bluesky`. Allowed: `twitter`, `bluesky`, `mastodon`, `instagram`, `facebook`, `youtube`, `tiktok`, `linkedin`, `threads`. |
| `limit` | int 1–200 | Default `50`. |

### Response

```json
{
  "items": [
    {
      "id": "uuid",
      "politician_id": "uuid",
      "platform": "twitter",
      "post_id": "1791234567890123456",
      "posted_at": "2026-05-23T14:08:22Z",
      "text": "Today in Ottawa, we…",
      "url": "https://twitter.com/PierrePoilievre/status/1791234567890123456",
      "media_urls": ["https://pbs.twimg.com/…"],
      "engagement": { "likes": 1240, "reposts": 320, "replies": 88 },
      "scraped_at": "2026-05-23T18:15:00Z",
      "funded_by": "@civic_observer",
      "funded_by_url": "https://civicobserver.ca/"
    }
  ]
}
```

`funded_by` and `funded_by_url` are populated when a paid subscriber
who captured this post **opted in** to public attribution on their
subscription. Both fields are `null` for anonymous-funded posts and
for posts captured by admin one-shot runs that weren't linked to an
attribution. Render the attribution as a `rel="nofollow noopener
external"` link when both fields are set.

Ordering: `posted_at DESC`, NULLs last. When multiple subscriptions
captured the same post, the most-recently-finished subscription's
attribution wins.

Cache-Control: `public, max-age=60`.

### Example

```bash
PID="..."
curl -s -H 'Authorization: Bearer cpd_live_…' \
  "https://canadianpoliticaldata.org/api/public/v1/politicians/$PID/posts?platform=twitter&limit=10" \
  | jq '.items[] | "[\(.posted_at)] \(.text[:120])"'
```

## Caveats

- **`follower_count` and `lifetime_post_count` may be NULL** for
  handles that haven't been profile-checked yet. The monitoring
  pipeline backfills these lazily; freshly-imported handles arrive
  with `last_profile_check_at = null` and counts unset.
- **Handle history is opt-in.** Pass `?include_dead=true` to see
  handles a politician moved away from. Useful for archival research;
  dropped from the default response to keep the typical UI use case
  (current-handle linking) clean.
- **Posts coverage depends on monitoring subscriptions.** A politician
  with no active subscription will return an empty `items` array.
  Subscribe at [`/account/monitoring`](https://canadianpoliticaldata.org/account/monitoring)
  to add monitoring; existing captured posts surface immediately for
  anyone (including anonymous web visitors) once monitoring is in
  place.
- **Engagement shape varies by platform.** Twitter posts carry
  `likes`/`reposts`/`replies`; Bluesky `likes`/`reposts`/`replies`;
  Mastodon `favourites`/`reblogs`/`replies`; Instagram `likes`/
  `comments`. Treat `engagement` as an opaque platform-specific
  object — keys and presence vary.
