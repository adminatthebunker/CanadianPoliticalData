---
title: Saved searches and alerts
description: Sign in to save Hansard searches and receive an email when new speeches match.
---

# Saved searches and alerts

Once you're [signed in](../getting-started/account.md), the search page
shows a **Save search** button. Click it, give the search a name, and pick
how often you'd like alerts.

## Cadence options

| Cadence | When you get an email |
| --- | --- |
| `None` | Never — the search is saved for your reference only. |
| `Immediate` | A short delay after a new matching speech is ingested (typically within an hour of the upstream legislature publishing). |
| `Daily` | A single digest each morning if there are new matches. |
| `Weekly` | A single digest each week if there are new matches. |

You can change the cadence at any time from your
[saved searches page](https://canadianpoliticaldata.org/account/saved-searches).

## What's in the digest

Each alert email lists the matching speeches with:

- Speaker name + party + jurisdiction
- Date and a one-paragraph excerpt
- A link straight to the speech in context

It does **not** include the full text of the speeches, partly to keep the
emails readable, partly so the citations always live on the canonical site
where they can be re-verified.

## How "matching" is decided

When you save a search, we cache its semantic fingerprint at save time.
The alerts worker then checks new speeches against that fingerprint —
**without re-asking the model** every time. This means:

- Alerts are fast and predictable.
- The meaning of your saved search is **frozen** at the moment you saved
  it. If the way the model interprets language changes (rare but possible
  on model upgrades), your saved search keeps using the original
  interpretation.
- If you want to "refresh" how a saved search is interpreted, just
  re-save it.

Filters (speaker, party, jurisdiction, date) are applied dynamically on
each digest run, not frozen.

## Pausing or deleting a saved search

From the [saved searches page](https://canadianpoliticaldata.org/account/saved-searches):

- Set cadence to `None` to keep the search but stop the emails.
- Click the trash icon to delete it permanently.

## Limits

- A signed-in account can save up to **50 searches**.
- Immediate-cadence saved searches are capped at **20** to keep mailbox
  noise under control.
- If you hit a limit, the UI explains which one and how to free up space.

## Why no SMS or push?

We deliberately ship email-only alerts for now. Email gives you a permanent,
searchable trail of what was reported and when — useful if you're using
this for journalism or research. SMS and push are louder but less
referenceable. We may add a webhook option for power users in the future;
let us know if that would help your workflow.
