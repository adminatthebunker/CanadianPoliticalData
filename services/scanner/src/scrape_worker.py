"""Scrape worker: Apify-backed politician monitoring + pre-flight + archive.

Three job kinds share this worker, distinguished by scrape_jobs.scrape_kind:

  monitoring  recurring, cadence-driven. Fixed per-platform credit cost
              held at dispatch time and committed on success. The
              dispatcher loop finds due saved_searches and enqueues
              one job per (subscription, platform) pair.

  preflight   one-shot, cheap. Calls a profile-scraper actor (or free
              public API for Bluesky / Mastodon) and caches the
              result onto politician_socials. Returns profile metadata
              + a cost calculator the UI can show.

  archive     one-shot, volume-priced. Pulls a deep history (up to
              ~3,000 posts) in a single run. Cost is tiered against
              politician_socials.lifetime_post_count.

Billing discipline:
  Every job has a hold_ledger_id placed at dispatch / submit time, via
  credits_py.hold_scrape_credits. On success → commit. On failure →
  release (full refund, all-or-nothing — matches the report-job
  precedent). Never a mutable balance column anywhere. Idempotent.

The platform-level circuit breaker (SCRAPE_DAILY_USD_CAP) is an
independent guard against runaway Apify spend on our side — if the
worker's running sum of Apify cost_usd_apify for the UTC day hits
the cap, it stops dequeuing until UTC midnight. Independent of any
per-user credit cap (which is the job-level hold).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import signal
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx

try:
    from apify_client import ApifyClientAsync
except ImportError:  # apify-client not installed at test/import time
    ApifyClientAsync = None  # type: ignore[assignment, misc]

from .credits_py import (
    commit_scrape_hold,
    hold_scrape_credits,
    release_scrape_hold,
    try_hold_scrape_credits,
)
from .db import Database, get_dsn

log = logging.getLogger("scrape_worker")


# ── Config (env-driven) ─────────────────────────────────────────────


APIFY_API_TOKEN = os.environ.get("APIFY_API_TOKEN", "").strip()
SCRAPE_TWITTER_TWEETS_PER_RUN = int(os.environ.get("SCRAPE_TWITTER_TWEETS_PER_RUN", "10"))
SCRAPE_INSTAGRAM_POSTS_PER_RUN = int(os.environ.get("SCRAPE_INSTAGRAM_POSTS_PER_RUN", "10"))
SCRAPE_BLUESKY_POSTS_PER_RUN = int(os.environ.get("SCRAPE_BLUESKY_POSTS_PER_RUN", "20"))
SCRAPE_MASTODON_POSTS_PER_RUN = int(os.environ.get("SCRAPE_MASTODON_POSTS_PER_RUN", "20"))
SCRAPE_ARCHIVE_MAX_ITEMS = int(os.environ.get("SCRAPE_ARCHIVE_MAX_ITEMS", "3000"))
SCRAPE_DAILY_USD_CAP = float(os.environ.get("SCRAPE_DAILY_USD_CAP", "5.0"))
SCRAPE_DISPATCH_INTERVAL = int(os.environ.get("SCRAPE_DISPATCH_INTERVAL", "60"))

# Per-platform per-run credit costs (mirror of services/api/src/lib/scrape-pricing.ts).
# Worker-side source of truth for what to debit; if these diverge from the
# TS constants, the API cost-estimate UI and the actual debit disagree.
MONITORING_CREDITS_PER_PLATFORM: dict[str, int] = {
    "twitter": 5,
    "instagram": 8,
    "bluesky": 1,
    "mastodon": 1,
}

PREFLIGHT_CREDITS_PER_PLATFORM: dict[str, int] = {
    "twitter": 1,
    "instagram": 1,
    "bluesky": 0,
    "mastodon": 0,
}

# Archive curve: floor + ceil((postCount - bucketSize) / bucketSize) * perBucket.
ARCHIVE_CURVES: dict[str, dict[str, int]] = {
    "twitter": {"floor": 10, "perBucket": 1, "bucketSize": 50},
    "instagram": {"floor": 15, "perBucket": 2, "bucketSize": 50},
    "bluesky": {"floor": 5, "perBucket": 1, "bucketSize": 100},
    "mastodon": {"floor": 5, "perBucket": 1, "bucketSize": 100},
}

# Apify actor slugs. Pinned here so a switch (e.g. cheaper alternative
# actor) is a one-line change. Verified against the actors listed in
# docs/plans/apify-social-deep-enrichment.md.
APIFY_ACTORS = {
    "twitter_timeline": "apidojo/tweet-scraper",
    "twitter_profile": "apidojo/twitter-user-scraper",
    "instagram": "apify/instagram-scraper",
    "instagram_profile": "apify/instagram-profile-scraper",
}

# Local cost floors per platform, used when Apify's run record reports
# `usageTotalUsd=0`. Some actors (notably apidojo/tweet-scraper) settle
# their billing asynchronously and don't include it in the sync
# response — we'd otherwise undercount platform spend and the
# SCRAPE_DAILY_USD_CAP circuit breaker would be toothless. Floors are
# conservative-leaning so the cap fires on time rather than late.
#
#   twitter: 50-tweet minimum × $0.40/1k = $0.02 per query (apidojo/tweet-scraper)
#   instagram: $1.50/1k posts (apify/instagram-scraper)
#   twitter_profile + instagram_profile: ~$0.50/1k profiles, 1 profile per run
APIFY_PLATFORM_FLOOR_USD: dict[str, float] = {
    "twitter": 0.02,
    "instagram": 0.0015,    # per-post; multiplied by result_count below
    "twitter_profile": 0.0005,
    "instagram_profile": 0.0005,
}


def estimate_apify_cost_floor(
    platform: str, scrape_kind: str, result_count: int, reported_usd: float
) -> float:
    """Return max(reported, locally-estimated floor) so the daily cap
    is accurate even when Apify's run response omits usageTotalUsd.

    Free platforms (Bluesky / Mastodon) always return 0; their floor
    is also 0 so this is a no-op there.
    """
    if reported_usd > 0:
        return reported_usd
    if scrape_kind == "preflight":
        if platform == "twitter":
            return APIFY_PLATFORM_FLOOR_USD["twitter_profile"]
        if platform == "instagram":
            return APIFY_PLATFORM_FLOOR_USD["instagram_profile"]
        return 0.0
    # monitoring / archive
    if platform == "twitter":
        return APIFY_PLATFORM_FLOOR_USD["twitter"]  # fixed 50-tweet floor
    if platform == "instagram":
        per_post = APIFY_PLATFORM_FLOOR_USD["instagram"]
        return max(per_post * max(result_count, 1), per_post)
    return 0.0

# Stale-claim sweep: if a job has been 'running' longer than this, the
# worker re-queues it. The Apify sync call has a 300s hard timeout;
# 30 minutes is generous for the async + dataset-fetch path.
STALE_CLAIM_MINUTES = 30


# ── Apify client (lazy singleton) ───────────────────────────────────


_apify_client: Optional[Any] = None


def get_apify_client() -> Any:
    global _apify_client
    if _apify_client is None:
        if not APIFY_API_TOKEN:
            raise RuntimeError("APIFY_API_TOKEN is not set")
        if ApifyClientAsync is None:
            raise RuntimeError("apify-client package not installed")
        _apify_client = ApifyClientAsync(token=APIFY_API_TOKEN)
    return _apify_client


# ── Pricing helpers (worker-side mirror) ────────────────────────────


def monitoring_credits_for(platform: str) -> int:
    if platform not in MONITORING_CREDITS_PER_PLATFORM:
        raise ValueError(f"platform not supported: {platform}")
    return MONITORING_CREDITS_PER_PLATFORM[platform]


def preflight_credits_for(platform: str) -> int:
    return PREFLIGHT_CREDITS_PER_PLATFORM.get(platform, 0)


def archive_credits_for(platform: str, post_count: int) -> int:
    curve = ARCHIVE_CURVES.get(platform)
    if not curve:
        raise ValueError(f"platform not supported: {platform}")
    if post_count <= curve["bucketSize"]:
        return curve["floor"]
    extra = post_count - curve["bucketSize"]
    buckets = -(-extra // curve["bucketSize"])  # ceil-divide without imports
    return curve["floor"] + buckets * curve["perBucket"]


def credits_for_job(scrape_kind: str, platform: str, post_hint: int | None = None) -> int:
    """Resolve credit cost for a job at dispatch time."""
    if scrape_kind == "monitoring":
        return monitoring_credits_for(platform)
    if scrape_kind == "preflight":
        return preflight_credits_for(platform)
    if scrape_kind == "archive":
        if post_hint is None:
            # Conservative: charge for the configured max if we don't have
            # a cached lifetime count yet (the UI should preflight first).
            post_hint = SCRAPE_ARCHIVE_MAX_ITEMS
        return archive_credits_for(platform, post_hint)
    raise ValueError(f"unknown scrape_kind: {scrape_kind}")


# ── Platform-specific scrapers ──────────────────────────────────────
# Each returns a tuple (posts, profile_metadata, cost_usd_apify).
# posts: list of dicts ready for upsert into public.social_posts.
# profile_metadata: dict cached onto public.politician_socials, or None.
# cost_usd_apify: float, the actual Apify usageTotalUsd (or 0 for free APIs).


HANDLE_CLEAN_RE = re.compile(r"^[@]+|/+$")


def _normalize_handle(handle: str) -> str:
    return HANDLE_CLEAN_RE.sub("", handle or "").strip()


async def _apify_run_and_collect(
    actor_slug: str,
    run_input: dict[str, Any],
    timeout_s: int = 290,
) -> tuple[list[dict[str, Any]], float, str | None]:
    """Call an Apify actor and return (items, cost_usd, run_id).

    v7a-2 (2026-05-13): added run_id to enable async cost
    finalization. Apify settles usageTotalUsd minutes after the sync
    call returns; the worker periodically GETs /v2/actor-runs/{id} to
    replace the locally-estimated cost floor with the real number.

    Uses .call() which blocks until the run finishes; cheaper than
    polling and within the 300s Apify sync limit for our small batches.
    """
    client = get_apify_client()
    run = await client.actor(actor_slug).call(
        run_input=run_input,
        timeout_secs=timeout_s,
    )
    if run is None:
        return [], 0.0, None
    dataset_id = run.get("defaultDatasetId")
    items: list[dict[str, Any]] = []
    if dataset_id:
        async for item in client.dataset(dataset_id).iterate_items():
            items.append(item)
    cost = float(run.get("usageTotalUsd") or 0.0)
    run_id = run.get("id")
    return items, cost, run_id


# ── Twitter ──────────────────────────────────────────────────────────


def _twitter_normalize_post(
    raw: dict[str, Any], politician_id: str
) -> dict[str, Any] | None:
    """Map apidojo/tweet-scraper output to our social_posts shape.

    Defensive about field names: the actor's output schema has shifted
    across versions; we try multiple key variants and skip rows that
    lack a stable identifier.
    """
    post_id = (
        raw.get("id")
        or raw.get("id_str")
        or raw.get("tweet_id")
        or raw.get("conversationId")
    )
    if not post_id:
        return None
    text = raw.get("text") or raw.get("full_text") or raw.get("rawContent") or ""
    url = raw.get("url") or raw.get("twitterUrl")
    if not url and post_id:
        author = (
            raw.get("author", {}).get("userName")
            if isinstance(raw.get("author"), dict)
            else raw.get("user", {}).get("screen_name")
            if isinstance(raw.get("user"), dict)
            else None
        )
        if author:
            url = f"https://x.com/{author}/status/{post_id}"
    posted_at_raw = (
        raw.get("createdAt")
        or raw.get("created_at")
        or raw.get("posted_at")
    )
    posted_at = _coerce_timestamp(posted_at_raw)
    engagement = {
        "likes": raw.get("likeCount") or raw.get("favorite_count") or raw.get("likes"),
        "replies": raw.get("replyCount") or raw.get("reply_count"),
        "reposts": raw.get("retweetCount") or raw.get("retweet_count"),
        "views": raw.get("viewCount") or raw.get("view_count"),
        "quotes": raw.get("quoteCount"),
        "bookmarks": raw.get("bookmarkCount"),
    }
    engagement = {k: v for k, v in engagement.items() if v is not None}
    media = []
    for m in raw.get("media") or []:
        if isinstance(m, dict) and m.get("media_url"):
            media.append(m["media_url"])
        elif isinstance(m, str):
            media.append(m)
    return {
        "politician_id": politician_id,
        "platform": "twitter",
        "post_id": str(post_id),
        "posted_at": posted_at,
        "text": text,
        "url": url,
        "media_urls": media or None,
        "engagement": engagement or None,
        "raw": raw,
    }


def _coerce_timestamp(val: Any) -> Optional[datetime]:
    """Apify actors return timestamps in mixed formats. Accept ISO-8601,
    epoch ints, and Twitter's `Wed Oct 10 20:19:24 +0000 2018` format."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val if val.tzinfo else val.replace(tzinfo=timezone.utc)
    if isinstance(val, (int, float)):
        # Heuristic: 13-digit → ms, 10-digit → s.
        if val > 1e12:
            return datetime.fromtimestamp(val / 1000, tz=timezone.utc)
        return datetime.fromtimestamp(val, tz=timezone.utc)
    if isinstance(val, str):
        try:
            return datetime.fromisoformat(val.replace("Z", "+00:00"))
        except ValueError:
            pass
        # Twitter's legacy format.
        try:
            return datetime.strptime(val, "%a %b %d %H:%M:%S %z %Y")
        except ValueError:
            pass
    return None


async def scrape_twitter_timeline(
    handle: str,
    politician_id: str,
    max_items: int,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None, float, str | None]:
    """Pull recent tweets via apidojo/tweet-scraper."""
    cleaned = _normalize_handle(handle)
    if not cleaned:
        return [], None, 0.0, None
    items, cost, run_id = await _apify_run_and_collect(
        APIFY_ACTORS["twitter_timeline"],
        {
            "twitterHandles": [cleaned],
            "maxItems": max_items,
            "sort": "Latest",
        },
    )
    posts = []
    for raw in items:
        normalized = _twitter_normalize_post(raw, politician_id)
        if normalized:
            posts.append(normalized)
    return posts, None, cost, run_id


async def scrape_twitter_profile(
    handle: str,
    politician_id: str,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None, float, str | None]:
    """Profile probe via apidojo/twitter-user-scraper."""
    cleaned = _normalize_handle(handle)
    if not cleaned:
        return [], None, 0.0, None
    items, cost, run_id = await _apify_run_and_collect(
        APIFY_ACTORS["twitter_profile"],
        {
            "twitterHandles": [cleaned],
            "maxItems": 1,
            "getFollowers": False,
            "getFollowing": False,
        },
    )
    profile = items[0] if items else None
    metadata: dict[str, Any] | None = None
    if profile:
        # Defensive field reads — actor output has evolved.
        statuses = (
            profile.get("statusesCount")
            or profile.get("statuses_count")
            or profile.get("tweetsCount")
            or profile.get("tweets_count")
        )
        followers = (
            profile.get("followers")
            or profile.get("followersCount")
            or profile.get("followers_count")
        )
        created = profile.get("createdAt") or profile.get("created_at")
        verified = (
            profile.get("isVerified")
            or profile.get("isBlueVerified")
            or profile.get("verified")
        )
        metadata = {
            "lifetime_post_count": int(statuses) if statuses is not None else None,
            "follower_count": int(followers) if followers is not None else None,
            "account_created_at": _coerce_iso(created),
            "verified": bool(verified) if verified is not None else None,
            "raw": profile,
        }
    return [], metadata, cost, run_id


def _coerce_iso(val: Any) -> str | None:
    dt = _coerce_timestamp(val)
    return dt.isoformat() if dt else None


# ── Stubs for non-Twitter platforms (Phase 1c/1d will fill in) ──────


# ── Bluesky (free, AT Protocol public AppView) ──────────────────────


BLUESKY_BASE = "https://public.api.bsky.app/xrpc"
# Bluesky's published "generous limits" — keep a short timeout so a
# slow appview doesn't stall the worker.
BLUESKY_TIMEOUT_S = 20.0


def _bsky_post_id_to_rkey(uri: str) -> str | None:
    """AT URI -> rkey. e.g. at://did:plc:.../app.bsky.feed.post/abc123 -> abc123"""
    if not uri or "/" not in uri:
        return None
    return uri.rsplit("/", 1)[-1] or None


def _bluesky_normalize_post(
    item: dict[str, Any], politician_id: str
) -> dict[str, Any] | None:
    """Map a Bluesky feed item to our social_posts shape. `item` is one
    element of getAuthorFeed's `feed` array; we read `item.post`."""
    post = item.get("post") if isinstance(item.get("post"), dict) else None
    if not post:
        return None
    uri = post.get("uri")
    if not uri:
        return None
    record = post.get("record") if isinstance(post.get("record"), dict) else {}
    author = post.get("author") if isinstance(post.get("author"), dict) else {}
    handle = author.get("handle")
    rkey = _bsky_post_id_to_rkey(uri)
    url = f"https://bsky.app/profile/{handle}/post/{rkey}" if handle and rkey else None
    posted_at = _coerce_timestamp(record.get("createdAt") or post.get("indexedAt"))
    engagement = {
        "likes": post.get("likeCount"),
        "replies": post.get("replyCount"),
        "reposts": post.get("repostCount"),
        "quotes": post.get("quoteCount"),
    }
    engagement = {k: v for k, v in engagement.items() if v is not None}
    return {
        "politician_id": politician_id,
        "platform": "bluesky",
        "post_id": uri,
        "posted_at": posted_at,
        "text": record.get("text") or "",
        "url": url,
        "media_urls": None,
        "engagement": engagement or None,
        "raw": post,
    }


async def scrape_bluesky_timeline(
    handle: str, politician_id: str, max_items: int
) -> tuple[list[dict[str, Any]], dict[str, Any] | None, float, str | None]:
    """Pull recent skeets via app.bsky.feed.getAuthorFeed. Free."""
    cleaned = _normalize_handle(handle)
    if not cleaned:
        return [], None, 0.0, None
    async with httpx.AsyncClient(timeout=BLUESKY_TIMEOUT_S) as client:
        resp = await client.get(
            f"{BLUESKY_BASE}/app.bsky.feed.getAuthorFeed",
            params={"actor": cleaned, "limit": min(max(max_items, 1), 100)},
        )
        resp.raise_for_status()
        data = resp.json()
    feed = data.get("feed") or []
    posts: list[dict[str, Any]] = []
    for item in feed:
        normalized = _bluesky_normalize_post(item, politician_id)
        if normalized:
            posts.append(normalized)
    return posts, None, 0.0, None


async def scrape_bluesky_profile(
    handle: str, politician_id: str
) -> tuple[list[dict[str, Any]], dict[str, Any] | None, float, str | None]:
    """Profile probe via app.bsky.actor.getProfile. Free."""
    cleaned = _normalize_handle(handle)
    if not cleaned:
        return [], None, 0.0, None
    async with httpx.AsyncClient(timeout=BLUESKY_TIMEOUT_S) as client:
        resp = await client.get(
            f"{BLUESKY_BASE}/app.bsky.actor.getProfile",
            params={"actor": cleaned},
        )
        resp.raise_for_status()
        profile = resp.json()
    posts_count = profile.get("postsCount")
    metadata = {
        "lifetime_post_count": int(posts_count) if posts_count is not None else None,
        "follower_count": int(profile.get("followersCount") or 0) or None,
        "account_created_at": _coerce_iso(profile.get("createdAt")),
        "verified": None,
        "raw": profile,
    }
    return [], metadata, 0.0, None


# ── Mastodon (free, per-instance public API) ────────────────────────


MASTODON_TIMEOUT_S = 15.0
# Be polite — Mastodon instances run on volunteer infra. Per the docs:
# unauthenticated requests share a coarse bucket per instance.
MASTODON_UA = "CanadianPoliticalDataBot/1.0 (+https://canadianpoliticaldata.org)"


def _parse_mastodon_handle(handle: str, fallback_url: str | None = None) -> tuple[str, str] | None:
    """
    Split `@user@instance.tld` (or `user@instance.tld`) into `(user, instance)`.
    Falls back to the URL host if the handle is unparseable. Returns None
    if we can't determine an instance.
    """
    if handle:
        h = handle.lstrip("@")
        if "@" in h:
            user, instance = h.split("@", 1)
            if user and instance:
                return user, instance
    if fallback_url:
        # https://instance.tld/@user or /users/user
        m = re.match(r"https?://([^/]+)/(?:@|users/)([^/?#]+)", fallback_url)
        if m:
            return m.group(2), m.group(1)
    return None


def _strip_html(text: str | None) -> str:
    """Mastodon's `content` is HTML; strip tags + decode common entities.
    Cheap regex pass — fine for short post text."""
    if not text:
        return ""
    # Replace block-level closes with newlines so paragraphs read sensibly.
    t = re.sub(r"</p\s*>", "\n\n", text, flags=re.IGNORECASE)
    t = re.sub(r"<br\s*/?>", "\n", t, flags=re.IGNORECASE)
    t = re.sub(r"<[^>]+>", "", t)
    # Light entity decode.
    t = t.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    t = t.replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " ")
    return t.strip()


def _mastodon_normalize_post(
    raw: dict[str, Any], politician_id: str
) -> dict[str, Any] | None:
    """Mastodon status -> social_posts row."""
    post_id = raw.get("id")
    if not post_id:
        return None
    media_urls: list[str] = []
    for m in raw.get("media_attachments") or []:
        url = m.get("url") or m.get("remote_url")
        if url:
            media_urls.append(url)
    engagement = {
        "replies": raw.get("replies_count"),
        "reposts": raw.get("reblogs_count"),
        "likes": raw.get("favourites_count"),
    }
    engagement = {k: v for k, v in engagement.items() if v is not None}
    return {
        "politician_id": politician_id,
        "platform": "mastodon",
        "post_id": str(post_id),
        "posted_at": _coerce_timestamp(raw.get("created_at")),
        "text": _strip_html(raw.get("content")),
        "url": raw.get("url") or raw.get("uri"),
        "media_urls": media_urls or None,
        "engagement": engagement or None,
        "raw": raw,
    }


async def scrape_mastodon_timeline(
    handle: str, politician_id: str, max_items: int, fallback_url: str | None = None
) -> tuple[list[dict[str, Any]], dict[str, Any] | None, float, str | None]:
    """Pull recent toots from the politician's home instance. Free."""
    parsed = _parse_mastodon_handle(handle, fallback_url)
    if not parsed:
        return [], None, 0.0, None
    user, instance = parsed
    headers = {"User-Agent": MASTODON_UA, "Accept": "application/json"}
    async with httpx.AsyncClient(timeout=MASTODON_TIMEOUT_S, headers=headers) as client:
        lookup = await client.get(
            f"https://{instance}/api/v1/accounts/lookup",
            params={"acct": user},
        )
        if lookup.status_code == 404:
            return [], None, 0.0, None
        lookup.raise_for_status()
        account = lookup.json()
        account_id = account.get("id")
        if not account_id:
            return [], None, 0.0, None
        statuses = await client.get(
            f"https://{instance}/api/v1/accounts/{account_id}/statuses",
            params={
                "limit": min(max(max_items, 1), 40),
                "exclude_replies": "false",
                "exclude_reblogs": "false",
            },
        )
        statuses.raise_for_status()
        toots = statuses.json()
    posts: list[dict[str, Any]] = []
    for t in toots:
        n = _mastodon_normalize_post(t, politician_id)
        if n:
            posts.append(n)
    return posts, None, 0.0, None


async def scrape_mastodon_profile(
    handle: str, politician_id: str, fallback_url: str | None = None
) -> tuple[list[dict[str, Any]], dict[str, Any] | None, float, str | None]:
    """Profile probe via /accounts/lookup. Free."""
    parsed = _parse_mastodon_handle(handle, fallback_url)
    if not parsed:
        return [], None, 0.0, None
    user, instance = parsed
    headers = {"User-Agent": MASTODON_UA, "Accept": "application/json"}
    async with httpx.AsyncClient(timeout=MASTODON_TIMEOUT_S, headers=headers) as client:
        resp = await client.get(
            f"https://{instance}/api/v1/accounts/lookup",
            params={"acct": user},
        )
        if resp.status_code == 404:
            return [], None, 0.0, None
        resp.raise_for_status()
        account = resp.json()
    statuses = account.get("statuses_count")
    metadata = {
        "lifetime_post_count": int(statuses) if statuses is not None else None,
        "follower_count": int(account.get("followers_count") or 0) or None,
        "account_created_at": _coerce_iso(account.get("created_at")),
        "verified": None,
        "raw": account,
    }
    return [], metadata, 0.0, None


# ── Instagram (Apify) ───────────────────────────────────────────────


def _instagram_normalize_post(
    raw: dict[str, Any], politician_id: str
) -> dict[str, Any] | None:
    """apify/instagram-scraper post -> social_posts row. Field names
    here follow that actor's documented output as of 2026-05."""
    post_id = raw.get("id") or raw.get("shortCode") or raw.get("code")
    if not post_id:
        return None
    caption = raw.get("caption") or raw.get("captionText") or ""
    posted_at = _coerce_timestamp(
        raw.get("timestamp")
        or raw.get("takenAtTimestamp")
        or raw.get("taken_at")
    )
    url = raw.get("url")
    if not url and raw.get("shortCode"):
        url = f"https://www.instagram.com/p/{raw['shortCode']}/"
    media_urls = []
    for m in raw.get("images") or []:
        if isinstance(m, str):
            media_urls.append(m)
    if raw.get("displayUrl"):
        media_urls.insert(0, raw["displayUrl"])
    if raw.get("videoUrl"):
        media_urls.append(raw["videoUrl"])
    engagement = {
        "likes": raw.get("likesCount") or raw.get("likes_count"),
        "comments": raw.get("commentsCount") or raw.get("comments_count"),
        "views": raw.get("videoViewCount") or raw.get("video_view_count"),
    }
    engagement = {k: v for k, v in engagement.items() if v is not None}
    return {
        "politician_id": politician_id,
        "platform": "instagram",
        "post_id": str(post_id),
        "posted_at": posted_at,
        "text": caption,
        "url": url,
        "media_urls": media_urls or None,
        "engagement": engagement or None,
        "raw": raw,
    }


async def scrape_instagram_timeline(
    handle: str, politician_id: str, max_items: int
) -> tuple[list[dict[str, Any]], dict[str, Any] | None, float, str | None]:
    """Recent IG posts via apify/instagram-scraper."""
    cleaned = _normalize_handle(handle)
    if not cleaned:
        return [], None, 0.0, None
    items, cost, run_id = await _apify_run_and_collect(
        APIFY_ACTORS["instagram"],
        {
            "directUrls": [f"https://www.instagram.com/{cleaned}/"],
            "resultsType": "posts",
            "resultsLimit": max_items,
        },
    )
    posts: list[dict[str, Any]] = []
    for raw in items:
        n = _instagram_normalize_post(raw, politician_id)
        if n:
            posts.append(n)
    return posts, None, cost, run_id


async def scrape_instagram_profile(
    handle: str, politician_id: str
) -> tuple[list[dict[str, Any]], dict[str, Any] | None, float, str | None]:
    """Profile probe via apify/instagram-profile-scraper (or main
    instagram-scraper in `details` mode)."""
    cleaned = _normalize_handle(handle)
    if not cleaned:
        return [], None, 0.0, None
    items, cost, run_id = await _apify_run_and_collect(
        APIFY_ACTORS["instagram_profile"],
        {"usernames": [cleaned]},
    )
    profile = items[0] if items else None
    metadata: dict[str, Any] | None = None
    if profile:
        posts_count = (
            profile.get("postsCount")
            or profile.get("posts_count")
            or profile.get("mediaCount")
        )
        followers = (
            profile.get("followersCount")
            or profile.get("followers_count")
        )
        metadata = {
            "lifetime_post_count": int(posts_count) if posts_count is not None else None,
            "follower_count": int(followers) if followers is not None else None,
            "account_created_at": None,
            "verified": profile.get("verified") or profile.get("isVerified"),
            "raw": profile,
        }
    return [], metadata, cost, run_id


# ── Per-platform dispatch by scrape_kind ────────────────────────────


async def execute_scrape(
    *,
    platform: str,
    scrape_kind: str,
    handle: str,
    politician_id: str,
    handle_url: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None, float, str | None, str | None]:
    """Run the right scraper for (platform, scrape_kind) and return
    (posts, profile_metadata, cost_usd, apify_actor_slug, apify_run_id).

    `apify_run_id` is the Apify actor-run identifier; persisted on
    scrape_jobs.apify_run_id so the v7a-2 async cost-finalization pass
    can re-fetch usageTotalUsd after Apify settles billing. None for
    free platforms (Bluesky/Mastodon) — those rows are skipped by the
    polling pass via `WHERE apify_run_id IS NOT NULL`.

    `handle_url` is the canonical profile URL stored on
    politician_socials.url. Mastodon needs it to fall back to URL-host
    parsing when the handle doesn't carry an @instance suffix.
    """
    if platform == "twitter":
        if scrape_kind == "monitoring":
            posts, meta, cost, run_id = await scrape_twitter_timeline(
                handle, politician_id, SCRAPE_TWITTER_TWEETS_PER_RUN
            )
            return posts, meta, cost, APIFY_ACTORS["twitter_timeline"], run_id
        if scrape_kind == "preflight":
            posts, meta, cost, run_id = await scrape_twitter_profile(handle, politician_id)
            return posts, meta, cost, APIFY_ACTORS["twitter_profile"], run_id
        if scrape_kind == "archive":
            posts, meta, cost, run_id = await scrape_twitter_timeline(
                handle, politician_id, SCRAPE_ARCHIVE_MAX_ITEMS
            )
            return posts, meta, cost, APIFY_ACTORS["twitter_timeline"], run_id
    if platform == "bluesky":
        if scrape_kind == "preflight":
            posts, meta, cost, run_id = await scrape_bluesky_profile(handle, politician_id)
            return posts, meta, cost, None, run_id
        depth = (
            SCRAPE_ARCHIVE_MAX_ITEMS if scrape_kind == "archive"
            else SCRAPE_BLUESKY_POSTS_PER_RUN
        )
        posts, meta, cost, run_id = await scrape_bluesky_timeline(handle, politician_id, depth)
        return posts, meta, cost, None, run_id
    if platform == "mastodon":
        if scrape_kind == "preflight":
            posts, meta, cost, run_id = await scrape_mastodon_profile(
                handle, politician_id, fallback_url=handle_url
            )
            return posts, meta, cost, None, run_id
        depth = (
            SCRAPE_ARCHIVE_MAX_ITEMS if scrape_kind == "archive"
            else SCRAPE_MASTODON_POSTS_PER_RUN
        )
        posts, meta, cost, run_id = await scrape_mastodon_timeline(
            handle, politician_id, depth, fallback_url=handle_url
        )
        return posts, meta, cost, None, run_id
    if platform == "instagram":
        if scrape_kind == "preflight":
            posts, meta, cost, run_id = await scrape_instagram_profile(handle, politician_id)
            return posts, meta, cost, APIFY_ACTORS.get("instagram_profile"), run_id
        depth = (
            SCRAPE_ARCHIVE_MAX_ITEMS if scrape_kind == "archive"
            else SCRAPE_INSTAGRAM_POSTS_PER_RUN
        )
        posts, meta, cost, run_id = await scrape_instagram_timeline(handle, politician_id, depth)
        return posts, meta, cost, APIFY_ACTORS.get("instagram"), run_id
    raise ValueError(f"unknown platform: {platform}")


# ── DB helpers ──────────────────────────────────────────────────────


async def upsert_social_posts(
    db: Database, posts: list[dict[str, Any]], scrape_job_id: Any
) -> int:
    """Insert new posts; UNIQUE(platform, post_id) handles dedup.
    Returns the count inserted (not seen)."""
    if not posts:
        return 0
    inserted = 0
    async with db.pool.acquire() as conn:
        async with conn.transaction():
            for p in posts:
                row = await conn.fetchrow(
                    """INSERT INTO public.social_posts (
                           politician_id, platform, post_id, posted_at,
                           text, url, media_urls, engagement, raw,
                           scrape_job_id
                         )
                         VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9::jsonb, $10)
                         ON CONFLICT (platform, post_id) DO NOTHING
                         RETURNING id""",
                    p["politician_id"],
                    p["platform"],
                    p["post_id"],
                    p["posted_at"],
                    p["text"],
                    p["url"],
                    p["media_urls"],
                    json.dumps(p["engagement"]) if p["engagement"] else None,
                    json.dumps(p["raw"]) if p["raw"] else None,
                    scrape_job_id,
                )
                if row:
                    inserted += 1
    return inserted


async def update_profile_cache(
    db: Database,
    politician_id: Any,
    platform: str,
    metadata: dict[str, Any],
) -> None:
    """Persist pre-flight metadata onto politician_socials. We update
    the row matched on (politician_id, platform); if multiple handles
    exist for that platform, the first (lowest-id) wins."""
    if not metadata:
        return
    lifetime = metadata.get("lifetime_post_count")
    followers = metadata.get("follower_count")
    raw_blob = metadata.get("raw")
    await db.execute(
        """UPDATE public.politician_socials
              SET lifetime_post_count       = COALESCE($3, lifetime_post_count),
                  follower_count            = COALESCE($4, follower_count),
                  profile_metadata          = COALESCE($5::jsonb, profile_metadata),
                  last_profile_check_at     = now(),
                  updated_at                = now()
            WHERE politician_id = $1
              AND platform      = $2
              AND id = (
                SELECT id FROM public.politician_socials
                 WHERE politician_id = $1 AND platform = $2
                 ORDER BY id LIMIT 1
              )""",
        politician_id,
        platform,
        lifetime,
        followers,
        json.dumps(raw_blob) if raw_blob is not None else None,
    )


async def lookup_handles(
    db: Database, politician_id: Any, platform: str
) -> list[tuple[str, str]]:
    """All live handles for (politician, platform), ordered by id.

    v7 (2026-05-13): was returning a single tuple; politicians with
    multiple handles per platform (e.g. Anita Anand has `anitaanandmp`
    + `anitaoakville` on Instagram) need a fallback chain — if the
    first handle returns empty/dead, we try the next before giving up
    on the probe. `process_job()` iterates and stops on first hit.
    """
    rows = await db.fetch(
        """SELECT handle, url FROM public.politician_socials
            WHERE politician_id = $1
              AND platform      = $2
              AND COALESCE(is_live, true) IS TRUE
              AND handle IS NOT NULL
            ORDER BY id""",
        politician_id,
        platform,
    )
    return [(r["handle"], r["url"]) for r in rows]


async def daily_apify_spend(db: Database) -> float:
    """Sum of cost_usd_apify for the current UTC day. Powers the
    SCRAPE_DAILY_USD_CAP circuit breaker."""
    row = await db.fetchrow(
        """SELECT COALESCE(SUM(cost_usd_apify), 0)::float8 AS spend
             FROM private.scrape_jobs
            WHERE finished_at >= date_trunc('day', now() at time zone 'utc')
              AND status = 'succeeded'"""
    )
    return float(row["spend"] if row else 0.0)


# ── v7a-2: async cost finalization ──────────────────────────────────


SCRAPE_COST_POLL_DELAY_MIN = int(os.environ.get("SCRAPE_COST_POLL_DELAY_MIN", "5"))
SCRAPE_COST_POLL_BATCH = int(os.environ.get("SCRAPE_COST_POLL_BATCH", "20"))


async def poll_apify_run_costs(db: Database) -> dict[str, int]:
    """Re-fetch usageTotalUsd for succeeded Apify-backed scrape_jobs
    whose cost wasn't yet finalized.

    Many Apify actors (notably apidojo/tweet-scraper) report
    usageTotalUsd=0 in the sync run response and settle billing minutes
    later. process_job() writes a local estimate via
    estimate_apify_cost_floor() so SCRAPE_DAILY_USD_CAP isn't toothless,
    then sets apify_run_id and leaves cost_usd_apify_finalized=false.
    This pass scans rows older than SCRAPE_COST_POLL_DELAY_MIN minutes,
    fetches the run record, and overwrites cost_usd_apify with the real
    number (when > 0). The finalized flag flips regardless — even
    Apify settling at $0 is a settled value.

    Free platforms (Bluesky/Mastodon) have apify_run_id NULL and are
    excluded by the partial index on the migration. Stats returned:
    {scanned, updated, finalized_zero, errors}.
    """
    if not APIFY_API_TOKEN or ApifyClientAsync is None:
        return {"scanned": 0, "updated": 0, "finalized_zero": 0, "errors": 0}

    rows = await db.fetch(
        f"""SELECT id, apify_run_id, cost_usd_apify
              FROM private.scrape_jobs
             WHERE status = 'succeeded'
               AND apify_run_id IS NOT NULL
               AND cost_usd_apify_finalized = false
               AND finished_at < now() - interval '{SCRAPE_COST_POLL_DELAY_MIN} minutes'
             ORDER BY finished_at
             LIMIT {SCRAPE_COST_POLL_BATCH}"""
    )
    if not rows:
        return {"scanned": 0, "updated": 0, "finalized_zero": 0, "errors": 0}

    client = get_apify_client()
    updated = 0
    finalized_zero = 0
    errors = 0
    for r in rows:
        run_id = r["apify_run_id"]
        prev_cost = float(r["cost_usd_apify"] or 0.0)
        try:
            run = await client.run(run_id).get()
            real_cost = float((run or {}).get("usageTotalUsd") or 0.0)
            if real_cost > 0:
                # Overwrite our local estimate with Apify's settled
                # number. The local floor was conservative; the real
                # value is authoritative for daily-cap accounting.
                await db.execute(
                    """UPDATE private.scrape_jobs
                          SET cost_usd_apify = $2,
                              cost_usd_apify_finalized = true
                        WHERE id = $1""",
                    r["id"], real_cost,
                )
                updated += 1
                log.info(
                    "cost-finalized job=%s run=%s prev=%.4f real=%.4f",
                    r["id"], run_id, prev_cost, real_cost,
                )
            else:
                # Apify settled the cost as 0 — flag finalized so we
                # don't poll forever. Keeps the local floor in place
                # since billing wasn't actually $0 from our side (the
                # plan-tier amortization argument); the daily-cap
                # circuit breaker stays on the conservative side.
                await db.execute(
                    """UPDATE private.scrape_jobs
                          SET cost_usd_apify_finalized = true
                        WHERE id = $1""",
                    r["id"],
                )
                finalized_zero += 1
        except Exception as e:  # noqa: BLE001
            # Don't flip the finalized flag on transient errors —
            # we want to retry next tick. The partial index keeps
            # the scan cheap regardless.
            errors += 1
            log.warning(
                "cost-finalize failed job=%s run=%s: %s: %s",
                r["id"], run_id, type(e).__name__, e,
            )

    return {
        "scanned": len(rows),
        "updated": updated,
        "finalized_zero": finalized_zero,
        "errors": errors,
    }


# ── Worker: claim + process ─────────────────────────────────────────


async def claim_next_scrape_job(db: Database) -> dict[str, Any] | None:
    """Atomically claim the oldest queued job. Re-queues stale 'running' rows."""
    await db.execute(
        f"""UPDATE private.scrape_jobs
              SET status = 'queued', claimed_at = NULL
            WHERE status = 'running'
              AND claimed_at IS NOT NULL
              AND claimed_at < now() - interval '{STALE_CLAIM_MINUTES} minutes'""",
    )
    row = await db.fetchrow(
        """UPDATE private.scrape_jobs
              SET status = 'running',
                  claimed_at = now(),
                  started_at = COALESCE(started_at, now())
            WHERE id = (
              SELECT id FROM private.scrape_jobs
               WHERE status = 'queued'
               ORDER BY created_at
               LIMIT 1
               FOR UPDATE SKIP LOCKED
            )
            RETURNING id, user_id, saved_search_id, politician_id, platform,
                      scrape_kind, trigger_source, estimated_credits,
                      hold_ledger_id"""
    )
    return dict(row) if row else None


async def mark_job_succeeded(
    db: Database,
    job_id: Any,
    *,
    result_count: int,
    cost_usd_apify: float,
    apify_actor: str | None,
    apify_run_id: str | None,
) -> None:
    # cost_usd_apify here is the local estimate / floor. The v7a-2
    # polling pass (poll_apify_run_costs) re-fetches the real
    # usageTotalUsd from /v2/actor-runs/<id> 5+ minutes later for any
    # row with apify_run_id set, and overwrites cost_usd_apify in
    # place. Free-platform rows (Bluesky/Mastodon) leave apify_run_id
    # NULL and are skipped by the poll.
    await db.execute(
        """UPDATE private.scrape_jobs
              SET status = 'succeeded',
                  finished_at = now(),
                  result_count = $2,
                  cost_usd_apify = $3,
                  apify_actor = COALESCE($4, apify_actor),
                  apify_run_id = COALESCE($5, apify_run_id)
            WHERE id = $1""",
        job_id,
        result_count,
        cost_usd_apify,
        apify_actor,
        apify_run_id,
    )


async def mark_job_failed(
    db: Database,
    job_id: Any,
    *,
    error: str,
    cost_usd_apify: float,
    apify_actor: str | None,
) -> None:
    await db.execute(
        """UPDATE private.scrape_jobs
              SET status = 'failed',
                  finished_at = now(),
                  cost_usd_apify = $2,
                  error = $3,
                  apify_actor = COALESCE($4, apify_actor)
            WHERE id = $1""",
        job_id,
        cost_usd_apify,
        error,
        apify_actor,
    )


async def process_job(db: Database, job: dict[str, Any]) -> None:
    """Run a single claimed job end-to-end. Commits or releases the
    held credits and updates the scrape_jobs row."""
    job_id = job["id"]
    user_id = job["user_id"]
    politician_id = job["politician_id"]
    platform = job["platform"]
    scrape_kind = job["scrape_kind"]
    hold_ledger_id = job.get("hold_ledger_id")

    log.info(
        "claiming job=%s user=%s politician=%s platform=%s kind=%s",
        job_id, user_id, politician_id, platform, scrape_kind,
    )

    cost_usd = 0.0
    actor: str | None = None
    run_id: str | None = None
    try:
        handles = await lookup_handles(db, politician_id, platform)
        if not handles:
            raise RuntimeError(
                f"no live {platform} handle for politician {politician_id}"
            )

        # Multi-handle fallback: try each handle in turn, stop on first
        # non-empty result. A politician with multiple handles per
        # platform (rare but real — e.g. an old + new account, or a
        # constituency + personal handle) gets at least one shot at
        # data even if the first handle is dead or empty. We charge
        # for at most one attempt (the cost_usd we record is whatever
        # the final platform call reported — Apify counts each call as
        # separate billing). Tried-handles list is purely for the
        # `tried` audit field in failure cases.
        posts: list[dict[str, Any]] = []
        metadata: dict[str, Any] | None = None
        tried: list[str] = []
        for handle, handle_url in handles:
            tried.append(handle)
            posts, metadata, cost_usd, actor, run_id = await execute_scrape(
                platform=platform,
                scrape_kind=scrape_kind,
                handle=handle,
                politician_id=str(politician_id),
                handle_url=handle_url,
            )
            if posts or metadata:
                break  # got data — accept this handle's result
            log.info(
                "job=%s handle=%s returned empty; trying next of %d candidates",
                job_id, handle, len(handles),
            )

        inserted = 0
        if posts:
            inserted = await upsert_social_posts(db, posts, job_id)
        if metadata:
            await update_profile_cache(db, politician_id, platform, metadata)

        # Apply local cost floor when Apify reports 0 (some actors
        # settle billing async, see APIFY_PLATFORM_FLOOR_USD). Keeps
        # the daily-cap circuit breaker accurate even on the apidojo
        # Twitter actor's silent settlement. The v7a-2 polling pass
        # (poll_apify_run_costs) later replaces this estimate with the
        # real usageTotalUsd once Apify settles billing.
        cost_usd_recorded = estimate_apify_cost_floor(
            platform, scrape_kind, inserted, cost_usd
        )

        await mark_job_succeeded(
            db, job_id,
            result_count=inserted,
            cost_usd_apify=cost_usd_recorded,
            apify_actor=actor,
            apify_run_id=run_id,
        )

        # Only the user-billed kinds have a hold to commit. Admin
        # one-shots may have hold_ledger_id=NULL.
        if hold_ledger_id is not None:
            await commit_scrape_hold(db, hold_ledger_id)

        log.info(
            "succeeded job=%s inserted=%d cost_usd_reported=%.4f cost_usd_recorded=%.4f actor=%s",
            job_id, inserted, cost_usd, cost_usd_recorded, actor,
        )
    except Exception as e:  # noqa: BLE001
        reason = f"{type(e).__name__}: {e}"
        log.warning("job=%s failed: %s", job_id, reason)
        await mark_job_failed(
            db, job_id,
            error=reason[:500],
            cost_usd_apify=cost_usd,
            apify_actor=actor,
        )
        if hold_ledger_id is not None:
            await release_scrape_hold(db, hold_ledger_id, reason[:200])


# ── Dispatcher: cadence-driven enqueue ──────────────────────────────


_CADENCE_DAYS = {"weekly": 7, "monthly": 30, "quarterly": 91}


async def enqueue_scrape_job(
    db: Database,
    *,
    user_id: Any,
    politician_id: Any,
    platform: str,
    scrape_kind: str,
    saved_search_id: Any | None = None,
    trigger_source: str = "subscription",
    post_hint: int | None = None,
) -> tuple[str, str] | None:
    """Create a scrape_jobs row, place the credit hold, and link them.
    Returns (job_id, hold_ledger_id) on success, None if the user
    doesn't have enough credits (the dispatcher should pause the sub
    for 'out_of_credits' in that case)."""
    credits = credits_for_job(scrape_kind, platform, post_hint=post_hint)
    job_row = await db.fetchrow(
        """INSERT INTO private.scrape_jobs (
               user_id, saved_search_id, politician_id, platform,
               estimated_credits, scrape_kind, trigger_source
             )
             VALUES ($1, $2, $3, $4, $5, $6, $7)
             RETURNING id""",
        user_id, saved_search_id, politician_id, platform,
        credits, scrape_kind, trigger_source,
    )
    if not job_row:
        raise RuntimeError("scrape_jobs INSERT returned no id")
    job_id = job_row["id"]

    # No-cost jobs (Bluesky/Mastodon preflight at 0 credits) skip the
    # ledger entirely — there's nothing to hold.
    if credits == 0:
        return str(job_id), ""

    hold_id = await try_hold_scrape_credits(
        db, user_id=user_id, amount=credits, scrape_job_id=job_id,
    )
    if hold_id is None:
        # Insufficient balance — roll back the job row (we can't bill).
        await db.execute(
            "DELETE FROM private.scrape_jobs WHERE id = $1",
            job_id,
        )
        return None
    await db.execute(
        "UPDATE private.scrape_jobs SET hold_ledger_id = $2 WHERE id = $1",
        job_id, hold_id,
    )
    return str(job_id), hold_id


async def dispatch_due_subscriptions(db: Database) -> dict[str, int]:
    """One tick of the dispatcher: find saved_searches with scrape_cadence
    != 'none' that are due, and enqueue one job per (subscription,
    platform) pair. Returns a small stats dict."""
    rows = await db.fetch(
        """SELECT id, user_id,
                  filter_payload ->> 'politician_ids' AS politician_ids,
                  scrape_platforms, scrape_cadence, scrape_next_run_at
             FROM private.saved_searches
            WHERE scrape_cadence <> 'none'
              AND scrape_paused_reason IS NULL
              AND (scrape_next_run_at IS NULL OR scrape_next_run_at <= now())"""
    )
    stats = {"due": len(rows), "enqueued": 0, "paused_no_credits": 0, "skipped": 0}

    for sub in rows:
        # filter_payload.politician_ids is a JSON array (str-cast); parse.
        pol_ids_raw = sub["politician_ids"]
        try:
            pol_ids = json.loads(pol_ids_raw) if isinstance(pol_ids_raw, str) else (pol_ids_raw or [])
        except json.JSONDecodeError:
            pol_ids = []
        if not pol_ids:
            stats["skipped"] += 1
            continue

        platforms = sub["scrape_platforms"] or []
        if not platforms:
            stats["skipped"] += 1
            continue

        paused = False
        for pol_id in pol_ids:
            for platform in platforms:
                try:
                    res = await enqueue_scrape_job(
                        db,
                        user_id=sub["user_id"],
                        politician_id=pol_id,
                        platform=platform,
                        scrape_kind="monitoring",
                        saved_search_id=sub["id"],
                        trigger_source="subscription",
                    )
                except Exception as e:  # noqa: BLE001
                    log.warning(
                        "dispatch failed for sub=%s pol=%s platform=%s: %s",
                        sub["id"], pol_id, platform, e,
                    )
                    continue
                if res is None:
                    paused = True
                    break  # don't keep trying other platforms once balance is dry
                else:
                    stats["enqueued"] += 1
            if paused:
                break

        # Advance the watermark even on paused — otherwise we'd retry
        # every dispatch tick. The 'out_of_credits' state means the
        # subscription doesn't run until the user tops up; clearing
        # the reason on the next API touch re-arms it.
        cadence = sub["scrape_cadence"]
        days = _CADENCE_DAYS.get(cadence, 7)
        next_run = datetime.now(timezone.utc) + timedelta(days=days)
        if paused:
            await db.execute(
                """UPDATE private.saved_searches
                      SET scrape_paused_reason = 'out_of_credits',
                          scrape_last_run_at   = now(),
                          scrape_next_run_at   = $2
                    WHERE id = $1""",
                sub["id"], next_run,
            )
            stats["paused_no_credits"] += 1
        else:
            await db.execute(
                """UPDATE private.saved_searches
                      SET scrape_last_run_at = now(),
                          scrape_next_run_at = $2
                    WHERE id = $1""",
                sub["id"], next_run,
            )
    return stats


# ── Run loop ────────────────────────────────────────────────────────


async def run_queued_jobs(db: Database, limit: int = 5) -> dict[str, int]:
    """Drain up to `limit` queued jobs. Respects SCRAPE_DAILY_USD_CAP."""
    stats = {"processed": 0, "succeeded": 0, "failed": 0, "stopped_by_cap": 0}
    for _ in range(limit):
        if SCRAPE_DAILY_USD_CAP > 0:
            spent = await daily_apify_spend(db)
            if spent >= SCRAPE_DAILY_USD_CAP:
                log.warning(
                    "SCRAPE_DAILY_USD_CAP hit: spent=$%.4f cap=$%.2f — stopping",
                    spent, SCRAPE_DAILY_USD_CAP,
                )
                stats["stopped_by_cap"] = 1
                break
        job = await claim_next_scrape_job(db)
        if not job:
            break
        try:
            await process_job(db, job)
            # Re-read status to count succeeded vs failed.
            status_row = await db.fetchrow(
                "SELECT status FROM private.scrape_jobs WHERE id = $1",
                job["id"],
            )
            if status_row and status_row["status"] == "succeeded":
                stats["succeeded"] += 1
            else:
                stats["failed"] += 1
        except Exception as e:  # noqa: BLE001
            log.exception("process_job crashed for job=%s: %s", job["id"], e)
            stats["failed"] += 1
        stats["processed"] += 1
    return stats


# ── One-shot helper (Click subcommand entry point) ──────────────────


OPERATOR_ANCHOR_NAME = "[operator] One-shot attribution anchor"


async def _find_operator_anchor_id(db: Database, user_id: Any) -> Any | None:
    """Look up the operator-attribution anchor saved_search for this
    user. Returns None when the row doesn't exist (graceful degradation
    on deployments that haven't run the v3 backfill yet — the scrape
    just lands with NULL saved_search_id and shows up as anonymous
    attribution on the public profile, matching pre-v3 behaviour)."""
    row = await db.fetchrow(
        """SELECT id FROM private.saved_searches
            WHERE user_id = $1 AND name = $2
            ORDER BY created_at LIMIT 1""",
        user_id, OPERATOR_ANCHOR_NAME,
    )
    return row["id"] if row else None


async def one_shot_scrape(
    db: Database,
    *,
    user_id: Any,
    politician_id: Any,
    platform: str,
    scrape_kind: str,
    post_hint: int | None = None,
) -> dict[str, Any]:
    """Enqueue + immediately drain a single scrape job. Used for
    admin/operator-driven scrapes via the scrape-politician CLI.

    Auto-attribution: links new one-shot scrape_jobs to the operator
    anchor saved_search when one exists for `user_id`, so the public
    posts API surfaces them with the operator's chosen attribution
    handle/URL (default "The Bunker Operations" → canadianpoliticaldata.org
    for the canonical admin user). Without this, every admin one-shot
    would be an orphan and would need a manual SQL backfill to surface
    attribution publicly. Falls back to NULL (and anonymous attribution)
    when the anchor isn't present."""
    trigger_source = "user_oneshot" if scrape_kind == "archive" else "admin"
    anchor_id = await _find_operator_anchor_id(db, user_id)
    res = await enqueue_scrape_job(
        db,
        user_id=user_id,
        politician_id=politician_id,
        platform=platform,
        scrape_kind=scrape_kind,
        trigger_source=trigger_source,
        post_hint=post_hint,
        saved_search_id=anchor_id,
    )
    if res is None:
        return {"ok": False, "reason": "insufficient_balance"}
    job_id, hold_id = res
    # Process it immediately (single-job drain).
    stats = await run_queued_jobs(db, limit=1)
    final = await db.fetchrow(
        """SELECT status, result_count, cost_usd_apify, error
             FROM private.scrape_jobs WHERE id = $1""",
        job_id,
    )
    return {
        "ok": True,
        "job_id": job_id,
        "hold_ledger_id": hold_id or None,
        "drain_stats": stats,
        "final": dict(final) if final else None,
    }


# ── Main daemon (Click: run-scrape-worker) ──────────────────────────


_stop = asyncio.Event()


def _handle_signal(sig: int) -> None:
    log.info("signal %d — shutting down", sig)
    _stop.set()


async def main() -> None:
    logging.basicConfig(
        level=os.environ.get("SCRAPE_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s scrape-worker %(message)s",
    )
    log.info(
        "scrape-worker starting interval=%ds twitter_depth=%d daily_cap=$%.2f apify=%s",
        SCRAPE_DISPATCH_INTERVAL,
        SCRAPE_TWITTER_TWEETS_PER_RUN,
        SCRAPE_DAILY_USD_CAP,
        "set" if APIFY_API_TOKEN else "UNSET",
    )
    if not APIFY_API_TOKEN:
        log.warning("APIFY_API_TOKEN unset — Apify-backed jobs will fail")

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _handle_signal, sig)

    db = Database(get_dsn())
    await db.connect()
    try:
        while not _stop.is_set():
            try:
                d_stats = await dispatch_due_subscriptions(db)
                if d_stats["enqueued"]:
                    log.info("dispatch: %s", d_stats)
                r_stats = await run_queued_jobs(db, limit=10)
                if r_stats["processed"]:
                    log.info("run: %s", r_stats)
                # v7a-2: re-fetch Apify usageTotalUsd for rows whose
                # billing wasn't settled at sync-return time. Cheap
                # partial-index scan; no-op when nothing is due.
                c_stats = await poll_apify_run_costs(db)
                if c_stats["scanned"]:
                    log.info("cost-poll: %s", c_stats)
            except Exception as e:  # noqa: BLE001
                log.exception("tick failed: %s", e)
            for _ in range(SCRAPE_DISPATCH_INTERVAL):
                if _stop.is_set():
                    break
                await asyncio.sleep(1)
    finally:
        await db.close()
