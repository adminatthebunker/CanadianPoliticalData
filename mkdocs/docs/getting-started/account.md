---
title: Create an account
description: Sign in to Canadian Political Data with a magic link — no password.
---

# Create an account

Canadian Political Data uses **passwordless sign-in**. There is no password
to remember, no password to leak. The flow is the same whether you're
creating an account for the first time or signing back in.

## How it works

1.  Go to the [sign-in page](https://canadianpoliticaldata.org/login).
2.  Enter your email address.
3.  We send you a one-time link. Click it within **15 minutes**.
4.  You're signed in. The session lasts **30 days** of inactivity, after
    which you'll get another link the next time you visit.

That's the whole flow. There is no separate "register" step — the first
time you sign in with a new email, an account is created for you.

!!! tip "Trouble receiving the email?"

    - Check your spam folder. Magic links come from `noreply@thebunkerops.ca`
      (or whichever address the operator has configured).
    - Wait 60 seconds before requesting another. The system rate-limits to
      protect against abuse.
    - If your address belongs to a custom domain with strict DMARC, ask your
      mail admin to allow our sending domain.

## What we store

- Your email address.
- The timestamp of your most recent sign-in.
- Any saved searches and reports you create.
- A running tally of credits you've purchased, earned, or spent.

We do not store passwords (we don't have any), social-login tokens (we don't
support those), IP-derived location, or browsing history outside the
features you explicitly use.

## What we don't do

- **No social login.** Signing in with Google / Facebook / GitHub leaks your
  research interests to ad platforms — wrong trust model for a civic
  transparency tool. Email magic links only.
- **No password export.** There is nothing to export.
- **No third-party trackers.** The site is not instrumented for ad
  retargeting.

## Signing out

Use the account menu in the top-right corner. Signing out clears the session
on the device you're using. Other signed-in devices remain signed in until
their own 30-day window elapses, or until you change your email.

To sign every device out at once, contact us — we can rotate your session
key.

## Deleting your account

Email [admin@thebunkerops.ca](mailto:admin@thebunkerops.ca) from the address
on the account. We'll confirm before deleting and remove your record,
saved searches, and report history. Hansard speech data is public and
remains in the corpus regardless.
