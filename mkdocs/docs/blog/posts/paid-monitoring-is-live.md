---
date: 2026-05-12
authors:
  - adminatthebunker
slug: paid-monitoring-is-live
description: >-
  You can now set Canadian Political Data to scrape a politician's
  public social-media posts on a schedule — weekly, monthly, or
  quarterly — and have the cost auto-debited from your credit
  balance. Four platforms at launch. Here's how it works, what it
  costs, and where the boundaries are.
tags:
  - launch
  - monitoring
  - apify
draft: false
---

# Paid social-media monitoring is now live

This week I shipped paid politician monitoring. You can pick a
politician, pick a set of platforms (Twitter, Bluesky, Instagram,
Mastodon), pick a cadence (weekly, monthly, quarterly), and the
service will scrape their public posts on that schedule, debit
credits from your balance per refresh, and show you the result in
your dashboard.

The Hansard speech alerts that have been around since user accounts
launched are still free and still work. Social monitoring is the
second axis on the same Monitor button — same row in our database,
same dashboard, different pricing.

<!-- more -->

## What it does

When you sign in and visit a politician's page, the **Monitor**
button (top of the profile, next to their name) opens a panel with
two sections.

The first is the existing **email alerts** — free, daily or weekly
digest of new speeches by that politician. You may already have this
on for the people you follow.

The second is new: **social-content monitoring**. Tick the platforms
you want, pick a cadence, and the panel computes a live cost
estimate before you commit to anything.

The example I keep using internally is monitoring Pierre Poilievre
on Twitter and Bluesky weekly. That's `(5 + 1) credits × 4 weeks` =
**24 credits per month**, which is about $2.40. If you'd rather
sleep on it, monthly cadence is a quarter of that.

Once you save, a daemon picks up the subscription on its next tick
and starts running scrapes on schedule. Each scrape produces a row
in your `/account/monitoring` dashboard, posts land in your
subscriber view of the politician's profile, and the credit debit
shows up in your ledger history. If a scrape fails (the politician
deleted their account, the platform returned an error, anything),
the credits refund automatically and you see "failed — refunded" in
the dashboard rather than the cost-plus-nothing outcome.

## The four platforms, and why they cost what they cost

Two are paid Apify-backed; two are free upstream and effectively
free for us to run.

| Platform | Source | Cost per refresh |
| --- | --- | --- |
| **Twitter / X** | `apidojo/tweet-scraper` on Apify | **5 credits** ($0.50) |
| **Instagram** | `apify/instagram-scraper` on Apify | **8 credits** ($0.80) |
| **Bluesky** | Direct AT Protocol public AppView | **1 credit** ($0.10) |
| **Mastodon** | Per-instance public API | **1 credit** ($0.10) |

The Bluesky and Mastodon numbers aren't typos. Both have explicit
"public AppView" or "public timeline" APIs that don't require auth
or token-key access — Bluesky's official docs even use the phrase
"generous rate limits." Our compute and storage for those is real
but small, and we charge a token credit per refresh to cover it
rather than offer it as a free monitoring tier (free monitoring is
the email-digest path).

Twitter is the most expensive because the Apify actor we use has a
50-tweet minimum per query — even if we ask for 10 most-recent
tweets, the actor charges us for 50. Instagram has higher per-post
pricing than Twitter (`$1.50/1k` vs `$0.40/1k`) so the per-refresh
charge is correspondingly higher.

All four credits prices are tuned for ~5–10x markup over our actual
Apify cost. That spread covers a few things — our own ops and
storage, the daily-USD circuit breaker that protects us if an actor
runs amok, and the room to absorb cost variance without surprising
users with a re-priced bill. If the underlying actor cost ever
drops materially, we'll pass it through; if it spikes, we'll
absorb it and revisit.

## What you actually see

The dashboard at `/account/monitoring` shows two tables.

The first is your **active subscriptions**: one row per politician
you're monitoring, with the platforms, cadence, last run, next run,
and (if you've fallen below the credit floor) a *Paused — out of
credits* banner with a link to the credits page.

The second is your **recent scrape activity**: the last 50 jobs in
reverse-chronological order, with status pills (`succeeded` green,
`failed` red, `running` yellow), result counts, and the credits
spent. Click a politician's name to jump to their profile, where
the scraped posts appear on the *Recent posts (your monitoring)*
panel — visible only to you and any other subscribers of that
politician (more on that below).

If you want to know how much it would cost to grab a politician's
entire post history in one go — say, every tweet they've ever made
— there's an **archive** path. Run a profile preview first (1 credit
for the Apify platforms, free for Bluesky and Mastodon) and the
panel computes the archive cost. Mark Carney's 1,012 lifetime
Instagram posts come out to 55 credits ($5.50). Pascal Paradis's
~8,000 lifetime tweets come out around 170 credits ($17). These are
one-shot purchases, no recurring debit — and your subscribed posts
that are already in our system count, so the marginal cost is just
for the gap between what you have and the full archive.

## Where the data lives, and who sees it

Today, scraped posts are **subscriber-only**. If you pay to monitor
a politician, you see their posts on that politician's profile page.
Anonymous visitors don't. Other signed-in users who haven't
subscribed don't either. This is a deliberate v1 stance.

The reason: I wanted to ship the paid loop first and the
public-display surface second. Showing third-party public posts on
a politician's profile page (even though those posts are *already
public* on the source platform) implies a publishing posture —
people will treat what we display as our editorial choice — and
that needs a documented takedown workflow, a DSAR process, and a
public disclaimer about scope and accuracy.

Those three things shipped today alongside the monitoring feature:

- [Takedown and correction requests](../../about/takedown.md) — what's
  eligible, response SLAs (3 business days to acknowledge, 10 to act),
  escalation path.
- [Data subject access requests](../../about/dsar.md) — how to ask
  what we hold, get a copy, or have it deleted. PIPEDA-grounded.
- [Disclaimer](../../about/disclaimer.md) — what the scraped content
  is and isn't, fair-use framing, future-changes notice.

The next step is to flip the visibility gate so scraped posts appear
on the public politician profile pages too, with an *optional*
"Funded by @handle" attribution that subscribers can opt into. The
governance docs were the blocker for that and they're now in place.
Public-on-profile is a separate ship; I'd rather get the v1 right
than rush into a publishing posture I can't defend.

For the subscribers who care: your monitoring shows up in your
dashboard regardless of v2. The change, when it lands, is whether
the politician's *public* profile page also shows the data — not
whether you see your own monitoring.

## What it doesn't do

A few things to set expectations:

- **Private accounts**: out of scope. We don't scrape locked
  accounts, DMs, friends-only Facebook posts, private Instagram
  stories. Public posts on public accounts of politicians, period.
- **LinkedIn**: deferred. The LinkedIn scrapers all require a real
  account's cookies, which means scraping in a way that's a clear
  ToS violation. Not until we have a defensible posture.
- **Facebook posts** (as opposed to page metadata): deferred for
  similar reasons. Meta's terms are actively hostile to scraping
  and the legal exposure is asymmetric.
- **Real-time alerts**: out of scope, deliberately. The minimum
  cadence is *weekly*, and the daemon checks for due subscriptions
  every minute — so a weekly subscription might run an hour or two
  after its anniversary mark, not at the same minute every week. If
  you want real-time, the upstream platforms have notification
  features for that. We're for cadence-based archival monitoring.
- **Automated engagement**: never. Read-only, by design. We won't
  add a "like" or "reply" feature, ever. That's not transparency,
  that's astroturfing.

## What's next, in rough order

- **Public-on-profile (v2)**. Now that the governance docs are in
  place, this is the next product-shaped slice. Adds a public read
  surface on the politician profile page, with subscriber-attribution
  as an opt-in.
- **More platforms (Phase 2)**. TikTok, Threads, and Facebook page
  metadata are the obvious next adds. TikTok is the highest-signal of
  the three for federal-level political content; Threads is sparse
  but growing; Facebook page metadata is bio + follower count + last
  active without touching post content.
- **Better archive UX**. The one-shot archive button is functional
  but spartan — a progress estimate and a "this account is X% larger
  than the typical Twitter user" comparison would help users size
  their purchase.
- **Cross-platform deduplication**. Many politicians cross-post the
  same content to Twitter, Bluesky, and Instagram. The platforms
  index them as separate posts; eventually I want the dashboard to
  surface "this is the same post on three platforms" as a single
  visual unit.

If you want to try the monitoring without committing to ongoing
debits, the cheapest experiment is to run a single **preflight**
on a politician you care about (1 credit for Apify platforms, free
on Bluesky/Mastodon). You'll see their lifetime post count, follower
count, and the cost projection for various monitoring cadences and
the full archive — all without committing to a subscription.

The whole monitoring stack was about a week of work, mostly tearing
through the four platform integrations once the credit-ledger
plumbing was extended to handle the new `scrape_hold` /
`scrape_commit` / `scrape_refund` kinds. The ledger discipline is
the part that took thought; the actor integrations were rote. That's
roughly the proportion I'd hope for in any extension of the system:
the boring core stays boring, and most of the work goes to making
the new surface useful.

Sign in, click Monitor on a politician you actually care about, run
a preflight on one platform, and you'll see what I mean by the cost
calculator. The whole flow is designed to make you uncertain about
nothing before you commit to a recurring debit.
