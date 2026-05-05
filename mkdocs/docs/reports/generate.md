---
title: Generating a report
description: How to ask Canadian Political Data to compile an evidence-cited report — full report on a politician, synthesise a search, or map stances across the chamber.
---

# Generating a report

There are three trigger surfaces for paid analyses, all priced
up-front and all credit-refunded if the worker fails. Pick the one that
matches the question you're trying to answer.

## Full report on a politician

Use this when the question is *what does this person say about X?*

1.  **Navigate to the politician** whose record you want to summarise.
    From a search result, click through to their profile.
2.  **Click "Generate full report"** on their profile, or in the
    politician card on the `/search` "By politician" view.
3.  **Confirm the topic.** A modal asks what question or topic you want
    the report focused on. The clearer you are, the better the report —
    `their position on healthcare privatization, 2018–present` works
    better than `healthcare`.
4.  **Confirm the cost.** The modal shows how many credits the report
    will cost — calculated up-front based on how many speech chunks
    match the politician + topic.
5.  **Submit.** Credits are placed on hold (not yet spent). The report
    is queued.
6.  **Wait for the email.** Reports typically take a few minutes.
7.  **Read.** The report opens in a print-friendly view. Every quote
    and claim links back to the source speech.

## Synthesize a search

Use this when the question is *what does the corpus collectively say about
X?* — across multiple speakers, parties, and parliaments at once.

1.  **Search Hansard** at [/search](https://canadianpoliticaldata.org/search)
    with whatever query, filters, and date range you want.
2.  **Pick how many results to analyse.** The "Analyse top N" picker
    appears above the result list (Timeline view) and on the Analysis
    tab. Choose 25 / 50 / 100 / 200 / 500 — or click "Other…" to enter
    a custom count up to the 500 cap.
3.  **Click "Synthesize"** (or "Synthesize this search" on the Analysis
    tab). The cost-preview modal opens, showing exactly how many credits
    you'll be charged for the chosen N.
4.  **Submit, wait, read** — same flow as the per-politician report.
    The synthesis opens with a stats table (party split, top speakers,
    time range), then a paragraph of headline framing, then five bullet
    findings each citing two-to-three source quotes.

## Map stances on a search

Same trigger surface as Synthesize — same picker, same modal flow. Click
"Map stances" instead. The output is structured by stance (for / against
/ conditional) with one exemplar quote per speaker per stance, useful
when you're building a "who's on which side" frame for an article.

## How pricing works

Cost is proportional to **how much material the system has to read**.
Each kind has its own formula:

- **Full report on a politician**: priced from the count of speech chunks
  matching the politician + topic.
- **Synthesize this search**: 5 credits + 1 per 10 chunks analysed
  (e.g. 25 chunks = 8 credits, 200 = 25, 500 = 55).
- **Stance map for this search**: 10 credits + 1 per 10 chunks analysed
  (slightly higher base because the structured output costs more).

The confirm modal always shows the exact final cost, your current
balance, and what your balance will be after — no hidden charges.

If a report turns out to be much smaller than the upfront estimate
(because, say, many candidate chunk IDs no longer exist), the **unused
portion is refunded** to your balance automatically. If the worker fails
entirely (model timeout, transient error), the **full hold is released**
and you're not charged.

## Hold vs commit

When you click submit, credits are placed on **hold** — your spendable
balance drops, but the credits aren't actually spent yet:

- If the report **succeeds**, the hold becomes a charge.
- If the report **fails** (server error, model timeout, etc.), the hold
  is released. Your balance returns to where it was. You're not charged
  for failures.
- If a report is **stuck running for too long**, the system automatically
  re-queues it (with the same hold in place) and tries again. You don't
  need to do anything.

## What makes a good report query

Good queries are **specific** and **time-bounded**:

- :material-check: `their position on the carbon price, 2019–present`
- :material-check: `how they've framed Indigenous reconciliation in
  their first vs second term`
- :material-check: `everything they've said about housing supply policy`

Vague queries get vague reports:

- :material-close: `what they think`
- :material-close: `bad things they've done`
- :material-close: `their best speeches`

The system can only summarise what's actually in the Hansard record. It
cannot tell you what they "really mean" or what they've "secretly
done" — only what they've said in the chamber.

For **synthesize** and **stance map**, the same advice applies, plus:
the search filters you have set when you click the CTA shape what gets
analysed. A search filtered to "Conservative MPs, 44th Parliament"
synthesises a different brief than the same query unfiltered.

## Reading the output

A report has four sections:

1.  **Summary.** A few short paragraphs describing the politician's
    stated positions on the topic.
2.  **Quotes and citations.** Inline quotes with links to each
    originating speech.
3.  **Tensions** *(when applicable).* If the politician has held
    different positions over time, this section flags the shift with the
    dates and speeches involved.
4.  **Sources.** Every speech consulted, with date and link.

You can print, share, or save the report from the viewer page. Reports
are private to your account — sharing means sharing the rendered HTML
or a printout, not granting another account access.

## Caveats

- Reports describe what the politician **said in the chamber.** They do
  not describe what the politician voted on (votes are a separate data
  layer), what the politician has said outside the chamber (interviews,
  social media, press releases — outside our scope), or what the
  politician has actually done in office.
- Reports use the speeches we have in the database **as of the time the
  report was generated.** If new Hansard ingests later, your report
  doesn't auto-update. Re-run the report if you want the most current
  picture.
- Reports are AI-generated and may contain errors of summarization,
  attribution, or framing — even though every quote is verbatim. Always
  click through to the underlying speeches before quoting a report in
  publication.
