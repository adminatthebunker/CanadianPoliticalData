---
title: Filters and tips
description: Narrow Hansard search results by speaker, party, jurisdiction, date, and more.
---

# Filters and tips

The filter panel on the [search page](https://canadianpoliticaldata.org/hansard)
narrows the corpus your semantic query runs against. Filters do **not**
re-rank the results — they decide which speeches are eligible, and the
semantic ranking does the rest within that set.

## Available filters

`Speaker`
:   One or more named politicians. Useful when you want to compare what
    different people have said on the same topic.

`Party`
:   Filter to one or more parties. Combine with a date range to see how a
    party's framing of an issue has shifted.

`Jurisdiction`
:   `Federal` (House of Commons), or any province / territory. Pick more
    than one to compare across legislatures.

`Date range`
:   Speeches between two dates. Inclusive on both ends.

`Speech length`
:   Hide one-line procedural interjections, or only show short
    interventions — depending on what you're researching.

`Has video`
:   (Where available) only return speeches with a video link to ParlVU or
    a provincial equivalent.

## Combining filters

Filters AND together. So:

> *Speakers: any Liberal MP* + *Jurisdiction: Federal* +
> *Date: 2023-01-01 to 2024-12-31*

returns only federal Liberal MP speeches from 2023–2024 that are
semantically similar to your query.

## When *not* to use filters

If you don't know who said the thing you're looking for, **don't filter
by speaker**. Let semantic search find it, then look at who said it.

If you're researching how a topic has been framed *across the political
spectrum*, leave party unfiltered and let the results show you who's
speaking on it.

## Sort options

| Sort | What it does |
| --- | --- |
| **Relevance** (default) | Most semantically similar to your query first. |
| **Newest first** | Most recent speeches first, ranked by similarity within ties. |
| **Oldest first** | Earliest speeches first — useful for tracing when an idea entered the discourse. |
| **By speaker** | Groups speeches by speaker, with the most-similar first within each group. |

## Tips

- **Start broad, then filter.** Run the search first with no filters, see
  what kinds of speeches come back, then filter to narrow.
- **Use date range to track shifts.** Same query, two different date
  ranges, side by side — easy way to see how rhetoric has changed.
- **Save the filter set, not just the query.** When you
  [save a search](saved-searches.md), the filters are saved with it. The
  alert email only fires for new speeches that match the **whole**
  filtered query.
- **Cross-jurisdiction comparison is a feature.** Filter by topic, leave
  jurisdiction open, then look at which legislatures are talking about it
  most.

## Sharing a search

Every search is fully reflected in the URL — query, filters, sort, page.
Copy the address bar to share it. Anyone who opens the link sees the same
results (for as long as the underlying corpus hasn't changed).

This is the easiest way to cite "what I found" in a story or a thread —
share the URL and the reader can verify.
