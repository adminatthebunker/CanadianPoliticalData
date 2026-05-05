---
title: Pricing
description: Why most of Canadian Political Data is free, and what we charge for — the rule is "we charge for compute we can't run on our own hardware."
---

# Pricing

The short version: **we charge for compute we can't run on our own
hardware.** Everything we *can* run on the home server in Edmonton is
free — that's most of the site.

## The rule

Canadian Political Data is operated on a single, modest server hosted in
amiskwaciy-waskahikan (Edmonton), Treaty 6 territory, behind a Canadian
network connection. Most of the product runs there at no marginal cost
to us:

- The full Hansard text corpus and the embeddings index.
- Politician rosters, ridings, bills, votes, hosting-sovereignty data.
- Semantic search — including the AI model that converts your query
  into a vector. That model runs on a local GPU. It costs us
  electricity, not API fees.
- The map, the explore view, alerts, saved searches, magic-link login.

When you use the public site, **none of that compute leaves the
building.** It is also why we can keep the public side free
indefinitely.

The pieces we *can't* run locally are the ones that need a much larger
language model than our hardware can host. Today that's exactly one
feature: **[generating a report](../reports/generate.md).** Reports are
produced by a large hosted language model (via a third-party inference
API) summarising the relevant speeches with citations. That call costs
us real money, per report, in proportion to how much text the model has
to read and write.

So reports cost credits. Search doesn't.

## What's free, forever

- **Searching Hansard** — full semantic search across every speech we've
  ingested.
- **Browsing politicians, ridings, bills, votes** — the entire
  structured dataset.
- **The map and the explore view.**
- **Saved searches and alerts** — we run the comparison job ourselves
  on a schedule; no external compute.
- **Submitting corrections** — and you *earn* credits for accepted ones.
- **The public dataset dump** — a weekly Postgres dump of the public
  schema, served at
  [`/datasets/`](https://canadianpoliticaldata.org/datasets/) for
  anyone who wants to reuse the data.

We will not put any of these behind a paywall. If something currently
free becomes paid in the future, it will be because the cost shape
genuinely changed (e.g. we couldn't keep running it on local hardware),
and we will say so explicitly.

## What costs credits

Today: **report generation.** A report is an AI-assisted, evidence-cited
summary of what a politician has said about a topic across Hansard,
with every quote linking back to its source. The model that writes the
summary is hosted by a third-party inference provider — there is a
direct, per-token cost to us each time you run one.

Pricing details — pack sizes, per-report cost, the hold/commit/release
flow, refunds — are in the
[Reports and credits](../reports/index.md) section. The short version
relevant to this page:

- The cost is shown to you **before** you commit to running a report.
- Credits are placed on **hold**, not spent, until the report
  succeeds. If it fails, the hold is released and your balance is
  unchanged.
- If a report consumes less than the up-front estimate, the unused
  portion is **automatically refunded** to your balance.
- Spent credits are not refundable in general; bug-driven failures on
  our side are. See [Buying credits](../reports/credits.md#refunds).

## What might cost credits later

There are a few features on the roadmap that, like reports, are
fundamentally bottlenecked on compute we can't host locally:

- **Programmatic API access for institutional users** — bulk export,
  scheduled topic alerts, and "compare A vs B" tooling for journalists,
  academics, and advocacy organizations. The public web UI stays free;
  the paid tier covers the operating cost of serving high-volume
  programmatic workloads.
- **Voice / accessibility features** that depend on hosted speech
  models.

When something new becomes paid, the same rule applies: the price
exists because the underlying compute has a real per-call cost we
can't absorb into the home server. We will say so on the page where the
charge appears.

## What will *not* cost credits

We are not going to:

- Charge for the things the home server can serve at scale (search,
  browsing, the map, alerts).
- Charge for "premium" politician profiles, "early access" data, or
  anything that's just a reshuffling of the public record behind a
  gate.
- Run ads, sell user data, or take political-party donations or
  sponsorships. The public side is funded by credit purchases for the
  things we genuinely can't run for free, plus, where applicable,
  grants.

## How the money flows

Credit purchases are processed by **Stripe**. We see a Stripe customer
ID, the pack purchased, and the amount paid — not your card number. We
pay the third-party LLM provider directly out of credit revenue. There
is no external investor extracting margin from this product.

If you are a journalist, academic, educator, or community organization
and the credit cost is a barrier to legitimate work, please
[get in touch](contact.md) — we grant credits for public-interest use.

## Why it's structured this way

The alternative pricing models all looked worse:

- **Subscriptions** — would require us to charge users a recurring fee
  to subsidise a feature most of them never use, and would push us
  toward locking up the free side to make subs feel valuable.
- **Ads or tracking** — would compromise the "access without
  surveillance" stance and would not pay the bills at our scale anyway.
- **Charging for search** — would defeat the point. The product exists
  to make the parliamentary record actually accessible.

Tying price to compute we can't run locally is the cleanest way to keep
the public side free, the paid side honest, and the incentives aligned:
we make money only when you ask the system to do something genuinely
expensive on your behalf, and only after you've seen the price.

## See also

- [Reports and credits](../reports/index.md) — the operational details:
  buying, refunds, taxes, the report flow.
- [About](index.md) — who runs the project and what we believe.
- [Privacy](privacy.md) — what data we keep about your purchases (the
  short answer: as little as possible).
