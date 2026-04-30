---
title: Coverage and data sources
description: What jurisdictions Canadian Political Data covers, and where the data comes from.
---

# Coverage and data sources

## Live coverage

For the current, machine-readable status of every jurisdiction we cover,
see the live [coverage dashboard](https://canadianpoliticaldata.org/coverage)
on the main site. It is generated from the same database the rest of the
app reads, so it's never out of date.

The dashboard tells you, for each legislature:

- Whether the **politicians roster** is being maintained.
- Whether **bills** are being ingested.
- Whether **Hansard** speeches are being ingested and embedded for search.
- The **last successful ingest** timestamp.
- Any documented blockers (e.g. PDF-only sources, anti-bot walls).

## Where the data comes from

All ingested data is **upstream-published primary source material**. We do
not paraphrase or rewrite. Specifically:

| Layer | Upstream source |
| --- | --- |
| Federal MPs | OpenParliament + ourcommons.ca rosters |
| Federal Hansard | ourcommons.ca official transcripts |
| Federal bills | LEGISinfo |
| Provincial MLAs / MNAs / MPPs | Each legislature's official member directory |
| Provincial Hansard | Each legislature's official transcripts (HTML, XML, JSON, or PDF depending on the province) |
| Provincial bills | Each legislature's bill index |
| Riding boundaries | Elections Canada and provincial chief electoral officers |
| Hosting / domain data | Public DNS, WHOIS, and certificate transparency logs |

Where multiple official sources exist for the same fact (e.g. a federal MP's
party affiliation), we cross-check rather than picking one.

## What "covered" means

A jurisdiction is **fully covered** when:

1.  Its current sitting members are in the database with party + riding.
2.  Its bills are being ingested with sponsors resolved to politicians.
3.  Its Hansard transcripts are being ingested, chunked, and embedded for
    semantic search.
4.  All three are running on a **daily schedule**, not by hand.

A jurisdiction is **partially covered** when (1) and (2) are running but
Hansard is missing, or vice versa. The coverage dashboard makes this
distinction explicit.

A jurisdiction is **on the roadmap** when the upstream publisher's data is
known to be machine-readable but we haven't built the ingester yet.

A jurisdiction is **blocked** when the upstream publisher only exposes data
in a way we can't reasonably ingest (e.g. scanned PDFs without OCR, behind
a CAPTCHA, or via a hostile WAF).

## Historical coverage

For some legislatures we have historical Hansard going back many years
(federal Hansard reaches back to the 1990s through OpenParliament, and
several provinces back to the early 2000s). For others we only have the
current sitting onward.

The search results page shows the **date** of every speech — sort by date
ascending if you want to find the earliest reference to a topic, or
descending for the most recent.

## Data retention

We do not delete public legislative speech once ingested, even if the
upstream legislature later removes or amends it. The original record
matters for accountability. If you believe a speech is in the system in
error (e.g. attributed to the wrong speaker), use the
[corrections flow](../politicians/corrections.md) — we'll fix the metadata
without erasing the underlying content.

## Reporting a coverage gap

If you spot a missing speech, a mis-attributed speaker, or an entire
jurisdiction we should be covering, [contact us](../about/contact.md). For
single-record fixes, [submit a correction](../politicians/corrections.md) —
accepted corrections also earn credits.
