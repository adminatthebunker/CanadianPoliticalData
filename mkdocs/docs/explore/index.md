---
title: Explore — semantic mind-map
description: Browse the full Hansard embedding space as an interactive 3D or 2D mind-map, grouped by topic.
---

# Explore — semantic mind-map

The [Explore page](https://canadianpoliticaldata.org/explore) shows every
speech chunk in the Hansard database as a point in a topic map. Related
speeches cluster together — speeches about housing cluster near each other,
speeches about pipelines near each other, speeches about language rights near
each other — because they were mapped using the same semantic embedding model
that powers Hansard search.

[Open the Explore page :material-map:](https://canadianpoliticaldata.org/explore){ .md-button .md-button--primary }

## What you're looking at

The map is built in three steps:

1. Every speech chunk is reduced from its 1024-dimensional embedding to 3D (and 2D) coordinates using UMAP. Semantically similar chunks land near each other.
2. The resulting point cloud is clustered automatically at three levels of granularity — broad topic areas, mid-level sub-topics, and fine-grained clusters.
3. Each cluster is labelled with its three most distinctive terms, computed from the text of its member speeches.

The result is a birds-eye view of what Canadian politicians talk about —
without having to know what to search for first.

!!! note "First projection"
    The map populates after the first projection build completes and is
    promoted to live. If you see an empty map, the initial build is still
    running or has not yet been promoted.

## Navigating the map

### 3D mode (desktop)

- **Rotate** — click and drag.
- **Zoom** — scroll wheel or trackpad pinch.
- **Pan** — right-click and drag, or hold ++shift++ and drag.
- **Click a cluster** — opens the cluster drawer with its label, top terms, and a sample of representative speeches.

### 2D mode (mobile and touch screens)

The map switches to a flat scatter automatically on touch devices.

- **Pan** — drag.
- **Zoom** — pinch or use the +/- controls.
- **Tap a cluster** — opens the cluster drawer.

You can switch between 2D and 3D manually using the toggle in the top-right corner of the map.

## Drilling down

Clusters are organised at three levels:

| Level | Approximate count | What it represents |
|-------|------------------|--------------------|
| 1 — broad | ~30 | Major topic areas (e.g. "health care", "energy", "Indigenous rights") |
| 2 — mid | ~200 | Sub-topics within each area |
| 3 — fine | ~1 500 | Specific debates and recurring themes |

Click a broad cluster to zoom in and reveal its mid-level sub-clusters. Click
again to see fine-grained clusters. The cluster drawer shows up to 15
representative speech excerpts with links to the full speech.

## Filtering the map

The filter bar lets you narrow which speeches count toward each cluster:

- **Jurisdiction** — federal, provincial, or a specific province/territory.
- **Party** — show only speeches from members of a particular party.
- **Date range** — restrict to a time window.
- **Language** — English, French, or both.
- **Speech type** — chamber debate, committee, members' statements, etc.

!!! info "How filtering works"
    Filtering does **not** move the clusters or re-draw the map. The spatial
    layout is a fixed reference frame — clusters always appear in the same
    position so you can build a mental map of the topic space over time.

    Instead, clusters that have no surviving speeches under your current
    filters fade out. Clusters where only some speeches survive become
    partially transparent. The darker a cluster, the more of its speeches
    match your filters.

    This lets you answer questions like "where in the topic space do BC NDP
    members speak?" without the map shifting under your feet every time you
    change a filter.

## From the map to search

Once you've spotted a cluster of interest, click through to its speech
excerpts and use the links to open the full speech in the
[Hansard search](https://canadianpoliticaldata.org/hansard) view. From there
you can search for similar speeches, apply further filters, or save the search
as an alert.

## What the map does not show

- **Individual politicians as labelled points.** The map is speech-chunk
  topology, not a speaker-by-speaker breakdown. Use the
  [politician profiles](https://canadianpoliticaldata.org/politicians) for
  speaker-centric views.
- **Real-time data.** The map is rebuilt periodically from the full embedded
  corpus. Speeches ingested since the last build will not appear until the
  next rebuild.
- **Voting records or bill outcomes.** The map covers spoken Hansard only.
  Bill tracking is on the [coverage page](../getting-started/coverage.md).
- **Non-covered jurisdictions.** If a legislature isn't in the
  [coverage list](../getting-started/coverage.md), its speeches are absent
  from the map.
