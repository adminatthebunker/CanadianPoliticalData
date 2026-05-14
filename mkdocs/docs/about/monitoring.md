---
title: Paid social-media monitoring
description: How sponsored monitoring of Canadian politicians' public social accounts works on Canadian Political Data — who it's for, what it costs, and how attribution surfaces on the public profile pages.
---

# Paid social-media monitoring

A signed-in user can pay to have a politician's public social-media
accounts (Twitter / X, Bluesky, Instagram, Mastodon) scraped on a
recurring schedule. The captured posts surface publicly on the
politician's profile page, attributed to the subscriber who paid for
the capture if they opted in, or anonymously as *Scraped via paid
monitoring* if they didn't.

This page explains what the feature is, who it's for, and how it works.

## Who it's for

Roughly four audiences, in order of how we've been thinking about it:

- **Journalists** building beat coverage. You want a politician's
  recent posts at a glance without manually trawling four platforms.
- **Researchers and academics** studying political discourse. The
  captured posts go into your data with stable IDs, timestamps, and
  engagement counts.
- **Civic-tech organizations** building accountability tools. Your
  app can show "the last 50 things this MP said on X" without doing
  its own scraping or paying a separate vendor.
- **Engaged citizens** who care about a particular politician and
  want a low-friction way to keep a paper trail of their public
  statements.

The platform is deliberately public-record-leaning. We aren't here
for opposition research as a service, and we aren't here for
private-account anything.

## What gets captured

Only public posts from public accounts on these four platforms today:

- **Twitter / X** via [Apify's tweet scraper](https://apify.com/apidojo/tweet-scraper)
- **Bluesky** via the [public AT Protocol AppView](https://docs.bsky.app/)
- **Instagram** via [Apify's Instagram scraper](https://apify.com/apify/instagram-scraper)
- **Mastodon** via the per-instance public API

We don't access locked / private accounts, DMs, friends-only Facebook
posts, or anything not visible to anyone with a web browser. We don't
have LinkedIn or Facebook-post scraping. See the
[disclaimer](./disclaimer.md) for the full scope statement.

## How it works

1. Sign in. Magic link only — no passwords.
2. Buy credits on the [credits page](./pricing.md). Smallest pack is
   $5 / 50 credits.
3. Visit any politician's profile and click **Monitor**.
4. Pick the platforms you want and the cadence (weekly / monthly /
   quarterly). The panel shows a live cost estimate before you
   commit.
5. Hit *Start monitoring*. The first scheduled scrape runs within
   the cadence window. Each scrape debits credits from your balance;
   failed scrapes refund automatically.

A scrape happens once per cadence window — weekly means one scrape
per week, not a continuous stream. The minimum cadence is weekly
deliberately; daily-everything is a money trap and the upstream
platforms have their own notification systems if you need real-time.

## Pricing

| Platform | Per refresh | Notes |
| --- | ---:| --- |
| Twitter / X | 5 credits ($0.50) | Most expensive; Apify actor has a 50-tweet minimum charge per call |
| Instagram | 8 credits ($0.80) | Higher per-post Apify pricing than Twitter |
| Bluesky | 1 credit ($0.10) | Free upstream; cost covers our compute + storage |
| Mastodon | 1 credit ($0.10) | Free upstream; cost covers our compute + storage |

Worked example: monitoring one politician on **Twitter + Bluesky
weekly** = `(5 + 1) × 4 ≈ 24 credits / month ≈ $2.40`.

There's also a one-shot **archive** action that pulls a deep history
in a single call, priced against the politician's total post count
(visible after a 1-credit profile preview). The same Monitor panel
shows the archive cost beside the recurring cost.

## Attribution

On the politician's *Recent posts* tab, every captured post carries
an attribution line. Three states:

- **Anonymous (default)** — "Scraped via paid monitoring." The
  subscriber's name stays private.
- **Opted-in handle** — "Funded by @yourhandle" as plain text.
- **Opted-in handle + URL** — "Funded by [@yourhandle](#)" as a
  clickable link, rendered with `rel="nofollow noopener external"`
  and opened in a new tab. The URL can point at any
  `https://` destination — your newspaper byline, your org site,
  your social profile, whatever.

To opt in: when you configure monitoring, check the "Show me as the
funder of these scrapes on this politician's public profile" box and
enter the handle (and optionally the URL) you want shown. You can
turn it off again any time via the same panel.

Sample attribution language for orgs:

| Use case | Handle | URL |
| --- | --- | --- |
| Independent journalist | @yourname | https://yournewspaper.com/byline/yourname |
| Research lab | "Carleton Public Policy Lab" | https://carleton.ca/sppa/ |
| Civic-tech org | "OpenNorth" | https://opennorth.ca |
| Curious citizen | (left blank — anonymous) | — |

## Privacy and limits

A few things to know:

- We never attribute to you publicly without your explicit opt-in.
- The link "this user paid for this scrape" lives in our private
  schema and never crosses to the public dataset.
- Subscriber identity is anonymous-by-default on the public profile;
  attribution opt-in is a single per-subscription decision.
- Your monitoring shows up in your own [`/account/monitoring`
  dashboard](https://canadianpoliticaldata.org/account/monitoring)
  regardless of whether you've opted into public attribution.
- We don't sell or share subscriber data. See the
  [privacy notice](./privacy.md).

## Removal requests

If you're a politician (or their staff) and you'd like a captured
post removed from our system, see the [takedown
policy](./takedown.md). We act on accepted requests within 10
business days — faster for court orders or urgent matters.

If you're a subscriber who wants your attribution removed (you opted
in and changed your mind), open the Monitor panel for that politician
and uncheck the attribution box. Posts captured by that subscription
revert to anonymous *Scraped via paid monitoring* on the next page
load.

## Related policies

- [Pricing](./pricing.md) — what credits cost and how they convert.
- [Disclaimer](./disclaimer.md) — what the data is and isn't.
- [Takedown and correction requests](./takedown.md) — removal workflow.
- [Data subject access requests](./dsar.md) — what we hold about you
  and how to retrieve / delete it.
- [Privacy notice](./privacy.md) — what we collect on every visitor.
