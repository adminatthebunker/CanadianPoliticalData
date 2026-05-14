---
title: Disclaimer
description: What Canadian Political Data publishes, how it's collected, what its limits are, and what the AI-generated reports and scraped social-media content are — and aren't.
---

# Disclaimer

This page tells you, in plain terms, what the data and tools on this
site are and aren't. Two main things to know about: **AI-generated
reports** and **scraped social-media content** from paid monitoring.

## The data we publish

Most of what you see on this site is drawn from official sources:
Hansard transcripts published by federal and provincial legislatures,
the legislatures' own roster pages, official bill texts, official vote
records. We re-index this content to make it searchable — we don't
claim authorship of it, and we link back to the upstream record where
possible.

**Accuracy guarantee:** as faithful as we can be to the upstream
source. When the legislature corrects Hansard, we correct ours. When
the official roster changes, we update ours. **We don't independently
fact-check legislators' statements** — if an MP says something in the
House that isn't true, our copy of Hansard says that thing. That's
how Hansard works.

If you spot a transcription error, a roster mistake, or a vote
mis-attribution, [submit a
correction](../politicians/corrections.md) — we'll fix it. Accepted
corrections from signed-in users earn credits.

### How politician social-media handles are sourced

Each politician's profile shows the social-media accounts we've linked
to them. Those handles come from four kinds of sources, and we tag
each with a confidence score so you can tell them apart:

1. **Open North's roster feed** — the original handles we ingest with
   the politician record itself. Most baseline coverage comes from here.
2. **Wikidata SPARQL + OpenParliament.ca + Mastodon directory walks** —
   deterministic enrichers that match politicians to public structured
   sources by name and jurisdiction.
3. **Operator manual entry** — for high-profile politicians where
   sources 1 and 2 are silent, we add handles by hand with the source
   tag `manual_operator`. These are still verified live with the same
   liveness checker as everything else.
4. **Daily LLM web-research pass** — a small autonomous Claude Code
   session runs each morning, web-searches for handles of the
   25 most-active politicians with the worst gaps, and inserts what
   it finds with an evidence-weighted confidence score (0.3 weak →
   0.9 strong). Every row carries the source URL it was found at, so
   if you're curious where we got a specific handle, that's the audit
   trail. Source tag: `claude-code-agent`.

We don't independently verify that a given handle is operated by the
politician personally rather than by a staffer — the same caveat that
applies to Hansard's recording of who's speaking. If a handle on a
politician's profile is wrong, [submit a
correction](../politicians/corrections.md) and we'll review.

## AI-generated reports

The premium report feature uses a large language model to summarise
matching speeches into a multi-section synthesis. Specifically:

- A report is **a summary of speeches that match a query**, not an
  independent investigation. The model is shown the relevant speech
  text from our corpus and asked to organize and summarise it.
- **The model can make mistakes.** It can mis-attribute a quote
  between two MPs who spoke on the same topic, drop important
  context, or over-confidently summarise something a politician
  qualified heavily in the original. The cited source speeches are
  always linked — read them for the authoritative version.
- **Citations point to our copy of Hansard, not the original**
  legislature URL (when we have an upstream URL on file, we surface
  it too). The speech text underlying any quoted material in a report
  is in the indexed dataset — you can verify any claim by clicking
  through.
- **Reports are private to the account that generated them.** Other
  users can't see them, and they don't appear in public search.
- **We don't fine-tune on user content.** Your queries and the speech
  context shown to the model are not retained by the model provider
  past the response cycle; they're not used for training. See the
  [privacy notice](./privacy.md) for our model-provider arrangement.

If you publish a report (paste it into a thing, quote it in an
article, share it with a colleague), the citation discipline is on
you: cross-reference against the linked source speeches. We provide
the tool; we don't endorse a specific report as a finished work.

## Paid social-media monitoring

If you've subscribed to monitor a politician's social-media accounts,
your dashboard shows posts captured on the cadence you chose
(weekly / monthly / quarterly). Some things to know:

- **All captured content comes from public accounts.** We don't access
  private accounts, DMs, locked tweets, friends-only Facebook posts,
  or anything not accessible to anyone with a web browser. If a
  politician has a public X account, that's the data we capture.
- **It's a snapshot, not a stream.** A scrape captures what was
  visible at the time it ran. If a post was deleted between scrapes,
  we may have the deleted copy — see [takedown](./takedown.md) for
  the policy on this.
- **Engagement counts are point-in-time.** The "238 likes" we recorded
  is what the post had when we scraped it; it may have grown since.
- **Coverage is partial.** Politicians who don't have public accounts
  on a platform won't show data. Some accounts use display-name
  changes, deletions, or restrictions that affect what we can see.
- **Translation and tone are preserved.** We don't summarise or
  rewrite. The text in our database is the text the politician
  posted, with HTML stripped and engagement metadata attached.
- **Visibility is public on the politician's profile page.** Posts
  captured by paying subscribers appear in the *Recent posts* tab of
  the politician's profile, visible to anyone (including anonymous
  visitors). Subscriber identity is **anonymous by default**:
  attribution reads "Scraped via paid monitoring." Subscribers can
  *opt in* to public attribution when they configure their monitor,
  in which case the post line reads "Funded by @theirhandle." The
  opt-in is per-subscription and defaults off.

## Fair use and editorial framing

We publish this data to support journalism, academic research, civic
literacy, and the public's right to scrutinise the people who govern
them. The framing across the site is broadly pro-transparency and
pro-democratic-accountability — we don't pretend to be neutral on the
proposition that voters should be able to easily see what their
representatives have said and done.

We aren't an investigative outfit. We don't editorialise on specific
politicians. We do publish blog posts and analysis from time to time;
those are signed and clearly marked.

Use of any data exported from the site:

- **Permitted** — research, journalism, civic-tech apps, academic
  work, classroom use, personal curiosity, building something useful.
- **Permitted with attribution** — incorporation into derivative works,
  visualisations, publications. Cite as "Canadian Political Data
  (canadianpoliticaldata.org)" or link.
- **Not permitted** — using the scraped content in ways that violate
  the upstream platforms' terms (e.g. for spam, harassment, or
  bulk-republication as if you'd scraped it yourself).
- **Not permitted** — using the data to identify, target, or harass
  private individuals incidentally mentioned in legislative business.

## Future changes (read this if you care)

A few things are in active development that may affect the framing
above:

- **Aggregate views on profile pages.** We may, in a future release,
  surface aggregate statistics (post counts over time, posting
  cadence, topic clustering) on the public politician profile page
  alongside the individual captured posts. The same subscriber-anonymity
  default would apply.
- **More platforms** (TikTok, Threads, Facebook page metadata) may
  come online. The same scope and discipline as above will apply.

## Related policies

- [Paid monitoring](./monitoring.md) — what subscribed monitoring is,
  who it's for, what it costs.
- [Takedown and correction requests](./takedown.md) — removal workflow.
- [Data subject access requests](./dsar.md) — what we hold and how to
  retrieve / delete it.
- [Privacy notice](./privacy.md) — what we collect on every visitor.

## Who to contact

[admin@thebunkerops.ca](mailto:admin@thebunkerops.ca) for anything
about this page. For specific content concerns, the
[takedown](./takedown.md) and [DSAR](./dsar.md) pages have the
detailed workflow.

This page itself is versioned in this site's documentation; you can
see the history of when it changed by looking at the file in the
documentation repository.
