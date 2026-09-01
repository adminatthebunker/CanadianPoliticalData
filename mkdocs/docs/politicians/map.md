---
title: The map
description: Browse Canadian electoral ridings on an interactive map.
---

# The map

The [map](https://canadianpoliticaldata.org/map) shows electoral ridings
across Canada. Click a riding to see who currently represents it, plus a
link straight into their profile and recent speeches.

## What you can do

- **Pan and zoom.** Standard map controls — drag to pan, scroll to zoom,
  two-finger pinch on touch.
- **Click a riding.** Pops up the current representative, their party,
  and a "view profile" link.
- **Switch jurisdiction.** Federal ridings and provincial ridings are
  separate layers — pick which you want to see (you can show both
  overlaid, but it gets busy).
- **Search by riding name.** The search box jumps the map to the matching
  riding's centroid.
- **Search by address.** Type an address (or just a city) to see which
  ridings cover it.

## Boundary versions

Riding boundaries change after every redistribution. The map shows the
**currently active** boundaries.

⚠ **There is no date selector yet.** This page described one for some time;
it was never built. The *data* is fully temporal — every boundary carries an
in-force range, superseded generations are retained rather than deleted, and
maps that take force later are loaded in advance and sit dormant until their
date — but the map UI exposes only what is in force today. The picker is on
the roadmap.

Until it ships, historical and future boundaries are reachable through the
[developer API](../developers/boundaries.md), which returns `effective_from`,
`effective_to` and `boundaries_version` on every row.

This is what the picker will be for:

- "Who used to represent this address?" — the boundaries in effect at the time.
- "How has this riding's footprint changed?" — successive redistributions.

## Mobile

The map is usable on mobile but is best on a tablet or larger screen.
On a phone, prefer the [politicians directory](https://canadianpoliticaldata.org/politicians)
search-by-name flow if you already know who you're looking for.

## Data sources

- **Federal boundaries** — Elections Canada electoral district shapefiles.
- **Provincial boundaries** — each province's Chief Electoral Officer
  (formats vary; some provinces publish clean GeoJSON, others only PDFs
  we have to digitize).
- **Municipal wards** — each municipality's own open-data portal, one
  publisher at a time. Coverage is real but **uneven**, and deliberately so:
  where a city publishes only a PDF we would have to trace, we hold no wards
  for it rather than a guess. Brossard is the worked example — we removed
  nine ward polygons that were a partial copy of a superseded map and left
  the city with none, because an honest gap beats a confident wrong answer.
- **Representative-to-riding mapping** — synthesized from each
  legislature's official member directory plus the term-history records
  in the database.

If a riding shows the wrong representative, that's almost always a
roster-staleness bug — please [submit a correction](corrections.md).

## What the map is not

The map is **not** a polling-results visualization. It does not show
election margins, vote shares, or projections. It is a "who currently
holds this seat" reference. We may add results overlays in the future
if there's clear demand; let us know.
