---
title: Reports and credits
description: Spend credits to generate evidence-cited AI reports on a politician's positions, voting record, or rhetoric over time.
---

# Reports and credits

A **report** is an AI-assisted, evidence-cited summary of what
parliamentarians have said in the chamber, with every claim linking back
to a specific speech chunk so you can verify it in one click.

There are three kinds of report you can ask for today, each priced
proportionally to how much material the system reads:

- **Full report on a politician + topic** (the original) — generated from
  a politician's profile or from a specific search result. Reads every
  matching speech for that politician and produces a multi-section brief.
- **Synthesize this search** — generated from the Analysis tab or
  Timeline view of `/search`. Reads the top N matches across **all**
  speakers in the result set and produces a one-paragraph summary plus
  five bullet findings, each citing source quotes. Useful when you want
  to know what the corpus collectively says about a topic, not what one
  politician said.
- **Stance map for this search** — same trigger surface as Synthesize.
  Groups speakers in the result set by stance (for / against /
  conditional), with one exemplar quote per group. Useful for journalists
  building a "who's on which side" frame.

Reports cost **credits**, which you buy in packs (or earn by submitting
[accepted corrections](../politicians/corrections.md)).

[Buy credits :material-credit-card:](https://canadianpoliticaldata.org/credits){ .md-button .md-button--primary }
[See your credit balance :material-account-cash:](https://canadianpoliticaldata.org/account){ .md-button }

## In this section

- **[Buying credits](credits.md)** — packs, payment, refunds, taxes.
- **[Generating a report](generate.md)** — the flow, the pricing, what to
  expect.

## Why credits, not subscriptions

We charge per report, not per month. This means:

- Casual users pay for what they use, with no recurring bill.
- Heavy users pay in proportion to load — running a report has a real
  compute cost, and we'd rather price it transparently than hide it
  behind tiered plans.
- There's nothing to cancel — credits don't expire.

## What a report contains

The exact shape depends on the kind, but every report includes:

- A **plain-language summary** of what the underlying speeches collectively
  say on the topic.
- **Direct quotes**, with each quote linking back to the originating
  speech.
- **Citations on every claim** — pulled from the actual chamber transcript.

A **full report on a politician** also flags tensions or contradictions
across time. A **synthesize-this-search** opens with a stats table
(party / top speakers / time range) before the bullet findings, and a
**stance map** structures the body as for / against / conditional groups
with an exemplar quote per speaker.

What a report does **not** contain:

- The model's opinions about the politician.
- Speculation about why a politician holds a position.
- Claims that aren't grounded in something the politician actually said
  in Hansard.

## Limits

- One report runs at a time per account (queued; you'll get an email
  when each is ready).
- Free-tier accounts have a soft cap on reports per day to keep abuse
  costs predictable. The cap is generous; if you hit it for legitimate
  research, ask for an increase from your account page.
- Reports are stored on your account and visible only to you. They are
  not indexed by the public site.

## What if a report is wrong

If a report misrepresents what a politician said:

1.  **Tell us** — there's a feedback link on every report.
2.  **You may be eligible for a refund** if the issue is a bug on our
    side (e.g. wrong politician's speeches got included). Refunds add
    credits back to your balance.
3.  We treat report-quality complaints as a learning signal — if a class
    of question consistently produces bad reports, we adjust the prompt
    or the retrieval logic.

We won't refund a report just because the conclusion isn't what you
wanted. Reports describe what the politician has said; that's not the
same as what you wish they'd said.
