---
title: Generating a report
description: How to ask Canadian Political Data to compile an evidence-cited report on a politician.
---

# Generating a report

Reports are generated from a politician profile or from the search page,
once you have credits in your balance.

## The flow

1.  **Navigate to the politician** whose record you want to summarise.
    From a search result, click through to their profile.
2.  **Click "Generate full report"** on their profile, or on a specific
    speech result.
3.  **Confirm the topic.** A modal asks what question or topic you want
    the report focused on. The clearer you are, the better the report —
    `their position on healthcare privatization, 2018–present` works
    better than `healthcare`.
4.  **Confirm the cost.** The modal shows how many credits the report
    will cost — calculated up-front based on how many speech chunks
    match the politician + topic. You see the price before you commit.
5.  **Submit.** Credits are placed on hold (not yet spent). The report
    is queued.
6.  **Wait for the email.** Reports typically take a few minutes. You
    don't need to keep the page open — we'll email you a link when it's
    ready.
7.  **Read.** The report opens in a print-friendly view. Every quote
    and claim links back to the source speech.

## How pricing works

Report cost is proportional to **how much material the system has to
read**:

- A politician with 10 speeches on a topic costs less than one with 500.
- A narrowly-scoped topic ("their stance on Bill C-11") costs less than
  a broad one ("everything they've said on culture and broadcasting").
- The exact pricing formula is shown in the confirmation modal — no
  hidden cost.

If a report turns out to be much smaller than the upfront estimate
(because, say, many candidate speeches were duplicates), the **unused
portion is refunded** to your balance automatically.

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
