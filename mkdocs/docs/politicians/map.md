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
**currently active** boundaries by default. Where we have data for
historical boundaries, you can switch to a previous version using the
date selector.

This matters for journalism and research:

- "Who used to represent this address?" — switch to the boundaries that
  were in effect at the time.
- "How has this riding's footprint changed?" — flip between successive
  redistribution years.

## Mobile

The map is usable on mobile but is best on a tablet or larger screen.
On a phone, prefer the [politicians directory](https://canadianpoliticaldata.org/politicians)
search-by-name flow if you already know who you're looking for.

## Data sources

- **Federal boundaries** — Elections Canada electoral district shapefiles.
- **Provincial boundaries** — each province's Chief Electoral Officer
  (formats vary; some provinces publish clean GeoJSON, others only PDFs
  we have to digitize).
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
