---
title: Privacy
description: What Canadian Political Data collects, what it doesn't, and how to reach us about your data.
---

# Privacy

Short version: we collect the minimum we need to run the service, we
don't share it with anyone, and you can ask us to delete it whenever you
want.

## What we collect

**Anonymous visitors:**

- Anonymous request logs — IP address, user agent, requested URL, status
  code, response time. Retained for 30 days for operational debugging,
  then aggregated and the per-request rows discarded.
- No cookies beyond a session token if you sign in.

**Signed-in users:**

- Your email address.
- Your sign-in timestamps.
- Your saved searches (query text + filters).
- Your purchased credits, earned credits, and report history.
- Reports you've generated (private to your account).

That's the whole list. We don't infer demographics, build a profile,
score you, or share any of it with third parties.

## What we don't collect

- Your password (there isn't one).
- Your social-login identity (we don't support social login).
- Your precise location (we use country-level GeoIP only, for billing
  region detection).
- Your search history if you're not signed in. Anonymous searches are
  not associated with any persistent identifier.

## Cookies

| Cookie | Purpose | Lifetime | Type |
| --- | --- | --- | --- |
| `sw_session` | Keeps you signed in | 30 days | HTTP-only, secure |
| `sw_csrf` | Cross-site-request protection | 30 days | Readable by JS (intentional, paired with the session cookie) |

We do not set marketing, analytics, or tracking cookies.

## Email

If you sign in, you're agreeing to receive:

- The **magic-link emails** you ask for.
- **Alert digests** for any saved searches you've turned on.
- **Operational emails** when relevant — receipts, "your report is
  ready," correction-applied notifications.

We do **not** send marketing emails, newsletters, or feature
announcements via email. If we ever change that, it would be opt-in,
clearly separated from operational mail.

## Payment data

Card details are handled by Stripe and never touch our servers. We see
only the Stripe customer ID, the pack purchased, and the gross amount
paid. See [Buying credits](../reports/credits.md) for more.

## Deleting your data

Email [admin@thebunkerops.ca](mailto:admin@thebunkerops.ca) from the
account email and ask for deletion. We'll confirm and then remove:

- Your user record
- Your saved searches
- Your report history
- Your purchase history (we keep a minimal anonymized accounting record
  for tax compliance)

Hansard speech data, politician roster data, and other public-record
data is unaffected — those are public records, not your personal data.

## Where data lives

Servers are operated in Canada. The database, search index, and
generated reports all live on infrastructure under the same operator,
with no third-party data processors except:

- **Stripe** — payment processing.
- **Email delivery service** — for outbound mail (magic links, alerts,
  receipts).
- **OpenRouter / model providers** — when you generate a report, the
  selected speeches plus your topic prompt are sent to a large language
  model for summarization. We do not associate this with your identity
  in the model provider's records.

## Children

The site isn't designed for or marketed to children under 13. We don't
knowingly collect data from anyone under 13.

## Changes to this notice

We'll edit this page when our practices change, with the change
reflected in the documentation site's git history (visible from the
repo, when public). Material changes will be noted on the
[home page](../index.md) for at least 30 days.

## Related policies

- [Disclaimer](./disclaimer.md) — what the AI-generated reports and
  the scraped social-media content from paid monitoring are and aren't.
- [Takedown and correction requests](./takedown.md) — how to ask us to
  remove or correct content about you.
- [Data subject access requests](./dsar.md) — how to ask what we hold
  about you, get a copy, or have it deleted.

## Questions or complaints

[admin@thebunkerops.ca](mailto:admin@thebunkerops.ca).
