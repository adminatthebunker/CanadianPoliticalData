---
title: Data subject access requests (DSAR)
description: How to ask what personal data Canadian Political Data holds about you, request a copy, or request deletion — under PIPEDA and provincial privacy law.
---

# Data subject access requests

If you want to know what we hold about you, get a copy of it, correct
it, or delete it, this page is for you. The mechanism is sometimes
called a **DSAR** (data subject access request) — the term comes from
European law but the rights exist in Canada too under PIPEDA and the
provincial equivalents (Quebec's Law 25, BC's PIPA, Alberta's PIPA).

This page is the workflow. The [privacy notice](./privacy.md) is the
underlying policy.

## Who can ask

Anyone whose **personal data** we hold. In practice:

- **Signed-in users** — we hold your email, sign-in timestamps, saved
  searches, credit ledger, report history, and (if you've subscribed to
  paid monitoring) scrape job records linking you to specific
  politicians and platforms.
- **Politicians and other public figures** — the public-record data we
  publish about you (Hansard speeches, votes, roster, public social
  posts) is **not your personal data** in the legal sense relevant
  here — it's the official record. The [takedown
  page](./takedown.md) is the right route for that content. But: if
  we hold any *non-public* data about you (a private correction
  submission you filed under your real name, or a paid account you
  created), that part is yours to ask about.
- **Members of the public** mentioned incidentally in a Hansard
  transcript or a politician's social post. Talk to us — see
  [takedown](./takedown.md) for how to deal with the underlying
  content.

## What you can request

Four rights, derived from PIPEDA + provincial regimes:

1. **Access** — what data do you hold about me?
2. **Copy** — give me a portable export of it.
3. **Correction** — fix what's wrong.
4. **Deletion** — erase it. (With limits — see below.)

For platform users, all four routes work. For incidentally-mentioned
public-record content, the realistic right is **correction**, not
deletion — see [takedown](./takedown.md).

## How to ask

Email
[admin@thebunkerops.ca](mailto:admin@thebunkerops.ca?subject=DSAR%20request)
from the email address tied to your account. Subject line: **DSAR
request — [access | copy | correction | deletion]**.

If you don't have an account and you're asking on behalf of yourself
about content we may hold, send the request from any email you control
— we may ask for additional verification.

We don't require a legal form, a lawyer, or a fee. Just say what you
want.

## What we'll send

For a full **access + copy** request from an account holder, you'll
receive a single email back containing:

- Your `users` record (id, email, display name, sign-in timestamps,
  admin flag, rate-limit tier).
- Your `saved_searches` rows (saved queries + alert + monitoring
  settings).
- Your `credit_ledger` rows (every credit grant and debit, with state
  + reason + reference id).
- Your `report_jobs` rows (history, status, results).
- Your `scrape_jobs` rows (paid monitoring history, with the politician
  and platform of each scrape).
- Your `correction_submissions` rows (any corrections you've filed).
- A list of any `social_posts` rows currently visible only because of
  your paid scrape activity (we don't include the post text in the
  export by default — that's the upstream politician's content, not
  yours — but we'll tell you which posts your subscriptions
  surfaced).

Format: JSON file attached, plus a plain-language summary inline in
the email so you don't have to read JSON.

## Correction

If something we hold is wrong, tell us what it should be and why. For
data tied to legislative records, see [takedown and
corrections](./takedown.md). For things like a wrong display name on
your account, a misclassified report, or a credit-ledger entry you
think is incorrect, just send us the detail and we'll fix it.

## Deletion

You can ask us to delete your account and everything tied to it. We
will:

- Erase your `users` row.
- Erase your `saved_searches`, `report_jobs`, `scrape_jobs`,
  `correction_submissions`, and `credit_ledger` rows.
- Anonymise our internal accounting record (we keep a non-identifying
  summary of transactions for tax compliance — see [privacy
  notice](./privacy.md) for the same explanation).
- Erase the captured `social_posts` rows that were scraped by your
  subscriptions if you so request (note that the same posts may
  remain in our system if a *different* subscriber also scraped them
  — those copies aren't yours to delete).
- Cancel any active monitoring subscriptions before the next scheduled
  scrape.

We can't:

- Delete the upstream Hansard or vote records that mention you (we
  don't own them — they're the public record).
- Delete a politician's public posts captured before you deleted your
  account if other people also subscribed to monitor them.

Deletion is confirmed back to you by email within 10 business days.

## Response time

- **Acknowledgement:** within 3 business days.
- **Substantive response:** within 30 days. PIPEDA's statutory deadline
  is 30 days; we aim to be faster. If we need an extension we'll tell
  you why and when to expect a response.
- **Refusals:** if we decline part of a request (typically: keeping
  the anonymised tax-compliance summary), we'll tell you which part
  and on what basis.

## Verification

For access, copy, and deletion requests we'll verify it's really you
asking. If the email matches an active account, that's usually enough.
If not, we may ask for one piece of confirming info (a recent invoice
number, a saved-search name you remember, etc.). We won't ask for
government ID.

## Escalation

If you're not satisfied with our response you can:

- **Reply and tell us** what's missing — most disputes resolve here.
- **Complain to the [Office of the Privacy Commissioner of
  Canada](https://www.priv.gc.ca/)** for federal/private-sector
  privacy complaints, or to your provincial privacy commissioner
  (Quebec, BC, Alberta have their own).

We log every DSAR request and its disposition for our own audit.

## Outside scope of this page

- **Bug reports / general support** — see [contact](./contact.md).
- **Politicians wanting public-record content removed** — see
  [takedown](./takedown.md).
- **What we collect from anonymous visitors** — see [privacy
  notice](./privacy.md).
- **How paid monitoring works** — see [paid monitoring](./monitoring.md).
