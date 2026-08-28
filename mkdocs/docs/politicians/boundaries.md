---
title: Electoral boundaries
description: Where Canadian Political Data's riding and ward boundaries come from — sourced directly from Elections Canada, the provincial and territorial chief electoral officers, and individual municipalities, with no intermediary.
---

# Electoral boundaries

An electoral boundary is the line that decides who represents you. Cross it
and your MP, your MLA and your councillor can all change. Everything on this
site that answers "who represents this address?" — the map, the postcode
lookup, a politician's riding — rests on those lines being right.

## Where ours come from

**Directly from the bodies that draw them.** Elections Canada for federal
ridings, each of the thirteen provincial and territorial chief electoral
officers for their own legislature, and individual municipalities for their
wards.

There is no intermediary. That is a deliberate architectural choice rather
than an incidental one: for most of this project's life the boundaries came
from a third-party aggregator, and in August 2026 that service was
unreachable for eleven days. Every postal-code lookup in the country failed
for the duration. We rebuilt on primary sources and on a Statistics Canada
address dataset we hold ourselves, because a dependency you cannot fix is a
dependency you cannot promise anything about.

The practical difference: if a source we use goes down today, the data is
already here. Nothing about answering "who represents this address?" requires
a live call to anyone else.

## Boundaries have dates

A riding map is not a fact, it is a fact *with a period attached*. Maps are
redrawn — federally after each census-driven redistribution, provincially on
each province's own cycle, municipally whenever a council restructures.

So every boundary we hold carries the generation it belongs to and the date
it took effect, and a superseded map is **kept, not deleted**. Ask about an
address today and you get today's answer; ask about 2019 and you get the map
that was in force then.

Two changes are already loaded and waiting for their dates:

| | |
|---|---|
| **Québec** provincial map | takes effect **2026-10-05**, going from 125 to 127 districts |
| **Ontario** municipal maps | take effect **2026-10-26**, at that province's municipal general election |

Neither is live yet. Both will switch over on the day, without an ingest run.

⚠ A small honesty note on dates: we date a map to the election it first
governed, not to the day the by-law passed. A map that has been enacted but
has never elected anyone is not yet the map that answers "who represents me".

## Reuse and licensing

⛔ **There is no single licence covering this data, and please do not assume
one.** Fourteen agencies publish these boundaries under at least nine
different sets of terms, and several publish none at all. Two municipalities
attach explicit restrictions.

If you want to reuse the geometry, check the specific source rather than the
collection: the [Boundary licences](../developers/licences.md) page lists the
terms per jurisdiction, and the API attaches the applicable licence to every
response it returns.

## When we get it wrong

Boundaries are the layer we can most easily be wrong about quietly, because a
wrong answer looks exactly like a right one. The checks that run daily are
therefore mostly about *disagreement*: does every district resolve one point
to exactly one answer, does every sitting member's riding actually exist, has
a map changed shape since we last looked.

If a riding on the map looks wrong to you, [tell us](corrections.md) — that
is usually faster than our finding it.
