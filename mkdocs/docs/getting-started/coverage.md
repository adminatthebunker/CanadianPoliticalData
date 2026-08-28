---
title: Coverage and data sources
description: What jurisdictions Canadian Political Data covers, and where the data comes from.
---

# Coverage and data sources

## Live coverage

For the current, machine-readable status of every jurisdiction we cover,
see the live [coverage dashboard](https://canadianpoliticaldata.org/coverage)
on the main site. It is generated from the same database the rest of the
app reads, so the dashboard never disagrees with what the API will return.

⚠ That is a narrower claim than it sounds, and worth stating plainly: it
means the dashboard matches **our database**, not that our database matches
**reality**. Where an upstream has no live ingester, the dashboard will
faithfully report data that has stopped moving. See *How current is this?*
below.

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
| Municipal councillors | Each province's own election result where one is published — Québec's MAMH, Ontario's AMO — otherwise the municipality's roster |
| Riding boundaries | Elections Canada and the thirteen provincial and territorial chief electoral officers |
| Municipal ward boundaries | Each municipality's own open-data portal, GIS service, or by-law |
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

## How current is this?

Different layers are current in different ways, and we would rather say so
than average them into one number.

**Electoral boundaries — current, and independently so.** Every federal,
provincial and territorial map, and the municipal wards we hold, comes from
the agency that drew it. There is no intermediary between that agency and
us, which means there is nothing in the middle that can go dark and take the
data with it.

⚠ Boundaries are also *dated*, not merely present. A map has a generation and
an in-force date, superseded maps are retained rather than deleted, and a
lookup answers for the date you ask about. Québec's provincial map changes on
2026-10-05 and Ontario's municipal maps on 2026-10-26; both are already
loaded and dormant, waiting for those dates.

**Federal and provincial rosters — ingested on a daily schedule** from each
legislature's own member directory.

**Municipal rosters — mixed, and this is the honest gap.** Québec and Ontario
are rebuilt from the province's own election results. The remaining
provinces' municipal rosters came from a third-party mirror we stopped
ingesting from in August 2026. Those records are **frozen**: they were
accurate when that source last ran, and they will not pick up a change until
we ship a replacement ingester for that province.

⛔ Frozen is not the same as wrong, and we try not to blur the two. A frozen
record was correct at a known moment; what it lacks is a way to notice that
it has stopped being correct. The point at which it goes wrong is that
province's next municipal election, which is why replacements are built
*ahead* of those dates rather than after them.

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
