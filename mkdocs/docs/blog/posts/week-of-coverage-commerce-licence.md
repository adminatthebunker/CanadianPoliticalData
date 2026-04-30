---
date: 2026-04-27
authors:
  - adminatthebunker
slug: week-of-coverage-commerce-licence
description: >-
  Eight days, thirty-eight commits. Roughly 750,000 new Hansard
  speeches across four provinces, a Stripe billing rail with Canadian
  sales tax, an "In Beta" status badge, a redesigned lander, and a
  licence change from MIT to PolyForm Noncommercial 1.0.0. Here's what
  shipped and why.
tags:
  - coverage
  - launch
  - billing
  - licence
---

# A week of coverage, commerce, and one big licence change

Eight days, thirty-eight commits. The kind of week that warrants
stepping back from "what did we ship today" to "what shape is the
project in now." Three big threads ran in parallel — provincial
coverage, monetization, and one quiet-but-load-bearing governance
decision.

<!-- more -->

## Coverage exploded

The headline number is **more than 750,000 new Hansard speeches**
added across the corpus this week. The breakdown:

**Manitoba** went from "no Hansard ingest" to a fully backfilled
historical record in three commits. Current sessions (43-1, 43-2,
43-3) landed first with about 30,000 speeches; a historical backfill
across Legislatures 39 through 43 added another 292,000; and a
**Word97-era parser** unlocked the older legs 37–38 (1999–2007) for a
further 115,000. Plus 764 former MLAs spanning 1870 to present,
sourced from the Manitoba Assembly's own archives.

**Quebec** got the historical treatment too — session 43-2 landed
earlier in the week (14,784 speeches), then a backfill across 8 prior
sessions added another 313,000.

**Ontario** got an MPP roster reaching back through the historical
record, plus a pre-2007 Hansard parser that handles the older
hand-typeset transcript format the Legislative Assembly published
before switching to structured XML.

**New Brunswick** and **Newfoundland** went live during what one
commit message calls "the post-reboot digest" — Hansard pipelines for
both, plus an Alberta historical-MLAs pass and a Nova Scotia
speaker-roster job.

**British Columbia** and **Quebec** got historical-roster backfills
late in the week, finishing the "every politician who's ever served"
ambition for two more provinces.

A **tier-1 presiding-officer speech-attribution resolver** landed
too — when a speech is attributed to "The Speaker" or "Madame la
Présidente" in the source, we now resolve that to the actual
politician occupying the chair at the time. Plus BC-specific resolver
fixes for edge cases that the bilingual chamber turned up.

The Hansard ingest pipeline itself got reliability work: timeout
handling, stale-job recovery for the worker queue. At this volume of
backfill those weren't optional — a transient network blip a few
hours into a 100k-speech run shouldn't require restarting from zero.

## The billing rail went live

Earlier in the week the **Stripe billing rail** shipped — credit
ledger, checkout flow, the whole append-only money-as-data design —
backing the AI report-generation feature. The architectural notes on
the ledger discipline (no mutable balance column, ever; the partial
unique index that catches duplicate Stripe events at the application
layer) live in `CLAUDE.md` for anyone reading the source.

Two days later, **Stripe Tax for Canadian GST/HST/PST** was wired in
behind a `STRIPE_TAX_ENABLED` runtime flag. With the flag flipped
(and the matching activation done in the Stripe dashboard), checkout
calculates Canadian sales tax based on the buyer's billing address
and preserves the breakdown on the receipt. Without it, the existing
checkout path is unchanged — a clean opt-in.

Corrections that get accepted now grant **credits as a reward** to
the submitter (10 credits per accepted correction, by default), with
an email notification on the grant. The grant is idempotent —
flipping a correction `applied → triaged → applied` doesn't double-pay
— and anonymous corrections skip the grant silently, since there's no
account to attribute to. This is the start of the "corrections with
credit" loop the [accounts post](accounts-alerts-corrections.md)
flagged a week earlier.

## Search got serious polish

A round of search-UX work cleaned up the Hansard search page:

- **New filters**: a `min_similarity` floor (so you can demand
  high-confidence semantic matches), `parliament + session` filters
  (so you can scope to a specific sitting), and `speech_type` (to
  exclude procedural interjections from research-quality queries).
- **Sort modes** for the results pane, with a dense-grid presentation
  when sorted "by politician."
- **Inline view tabs and sort chips on a single row** — less vertical
  real-estate spent on chrome, more on results.
- **Inline save-search button** as a green CTA next to the search bar,
  reducing the click cost of converting a useful search into a
  recurring alert.

The lander itself also got a redesign: flatter layout, a two-card
hero (semantic search + map), and corpus statistics surfaced more
prominently.

## "In Beta" — said out loud

The header now carries an **In Beta badge** with a hover panel
explaining the project's maturity status, and the lander shipped a
companion modal.

Why it matters: there's enough data to do real research with — well
over a million speeches across the federal corpus and a growing list
of provincial legislatures, plus a working semantic-search pipeline —
but coverage gaps remain (PEI, Yukon, parts of the federal historical
record), the AI report feature is still settling, and the dataset
download isn't yet published. Saying "beta" out loud is more useful
than pretending otherwise.

## And one quiet but load-bearing change

The project **relicensed from MIT to
[PolyForm Noncommercial 1.0.0](https://polyformproject.org/licenses/noncommercial/1.0.0/)**
mid-week.

The reasoning: the public-facing site is and will stay free for
personal use, journalism, research, education, and civic-tech work.
The underlying corpus and infrastructure represent significant
ongoing engineering work that needs to sustain itself, and that gets
harder if the codebase is a free input to ad-tech, surveillance, or
political-targeting products. PolyForm Noncommercial draws a clean
line: open and free for noncommercial use, separately licensed for
commercial use.

If you're using the source for personal research or building tools
for a civic-tech project, nothing changes. If you're integrating it
into a paid product, [contact us](../../about/contact.md) about a
commercial licence. The full text lives in the repo at
[`/LICENSE`](https://github.com/adminatthebunker/CanadianPoliticalData/blob/main/LICENSE).

## What's next

The next-priority work is **filling the remaining provincial Hansard
gaps** — Saskatchewan, then breaking through the WAFs that block PEI
and Yukon — and pushing the federal historical backfill the rest of
the way. After that, the public dataset download (currently flagged
"coming soon" on the
[contributors page](../../contributors/data-download.md)) gets
finalized once the user-data scrubbing review is done.

This is the rhythm the project will hold for a while: provinces,
then infrastructure, then back to provinces. If a jurisdiction you
care about is missing, the
[coverage dashboard](https://canadianpoliticaldata.org/coverage) is
the honest scoreboard.

If you find a misattribution or a missing politician along the way —
and at this volume, you will — the
[corrections page](https://canadianpoliticaldata.org/corrections) is
where to flag it. Accepted corrections now earn credits. Two-way
just got a little more two-way.
