---
title: How the Semantic Explorer is built
description: A plain-language walk-through of the embeddings, dimensionality reduction, clustering, and labelling that turn millions of speech chunks into the Explore map.
---

# How the Semantic Explorer is built

The [Explore page](https://canadianpoliticaldata.org/explore) looks like a
star map of Canadian political speech. This page explains what's actually
behind it — what each point is, how it got placed there, and how the topic
labels are chosen. The technical detail is real, but the reading level is
deliberately kept around grade 12: no machine-learning background required.

[Open the Explore page :material-map:](https://canadianpoliticaldata.org/explore){ .md-button .md-button--primary }

## The four-step pipeline at a glance

```
Hansard speech → split into chunks → embed each chunk → flatten to 3D → cluster → label
        text         (paragraph-ish)   (1024 numbers)     (x, y, z)    (groups)  (top words)
```

Every dot you see on the Explore page is one **speech chunk** — usually a
paragraph or two from a single politician's turn at the microphone. The map
shows roughly 3.4 million of them.

The four steps below explain how a paragraph of text becomes a coloured dot
in a labelled cluster.

---

## Step 1 — Turn each speech chunk into 1024 numbers (embedding)

The hard part of this whole system is teaching a computer that the
sentences

> "We need to act on climate change."

and

> "Carbon emissions must come down."

are talking about the same thing — even though they share almost no words.

The trick is called an **embedding**. An embedding model is a piece of
software that reads a chunk of text and turns it into a list of numbers.
Two chunks that mean similar things end up with similar lists of numbers.
Two chunks about totally different topics end up with very different
lists.

We use a model called **Qwen3-Embedding-0.6B**. For every speech chunk, it
produces a list of **1024 numbers**. You can think of those 1024 numbers as
coordinates in a space that has 1024 directions instead of the 3 we're used
to in real life. Different directions in that space roughly correspond to
different aspects of meaning — one direction might track "how much this
chunk is about money", another "how much this is about Indigenous
sovereignty", another "how angry the speaker sounds". Nobody hand-codes
these directions; the model learned them from reading huge amounts of text
during training.

This is the same model that powers
[Hansard search](../searching/how-it-works.md) — when you type a query, it
gets turned into 1024 numbers the same way, and the search engine looks for
chunks whose numbers are nearest.

!!! info "Why 1024 dimensions?"

    Smaller embeddings (say, 64 numbers) lose too much nuance — chunks
    about *birth tourism* and *air travel* might collapse onto the same
    coordinates because both involve airports. Bigger embeddings (4096
    numbers) cost more storage and more compute without buying much extra
    accuracy on Hansard-style text. 1024 is the size the Qwen3 model was
    trained to produce, and it's a good middle ground for our use case.

The output of step 1 is a **1024-dimensional vector** for every speech
chunk. There are about 3.4 million of these.

## Step 2 — Squash 1024 dimensions down to 3 (UMAP)

A human can't picture 1024 dimensions. To draw the map, we have to project
those 1024-number lists down to **3 numbers** — an x, y, and z coordinate
that we can render on a screen. (For mobile and 2D mode, we also produce a
2-number version with the same technique.)

The tool that does this is called **UMAP** — *Uniform Manifold
Approximation and Projection*. The intuition is:

1. UMAP looks at every chunk's 30 closest neighbours in 1024-d space.
2. It builds a graph where chunks are connected to their neighbours.
3. It tries to redraw that graph in 3D space, keeping neighbours close to
   each other and pushing unrelated points apart.

It's a bit like flattening a wrinkled bedsheet onto a table without tearing
it: nearby points on the sheet stay nearby on the table, even though the
sheet is now flat. UMAP is doing the same thing, just from 1024 dimensions
down to 3.

!!! info "Why this is a careful approximation, not a perfect picture"

    Going from 1024 dimensions to 3 inevitably loses information — there
    just aren't enough directions in 3D to faithfully represent every
    relationship that existed in 1024D. UMAP optimises to preserve **local**
    structure (which chunks are near which) at the expense of **global**
    structure (the absolute distance between two clusters on opposite sides
    of the map is not directly meaningful). Treat the map as a *qualitative*
    layout, not a metric one.

We don't run UMAP on all 3.4 million chunks at once — that would run out of
memory. Instead, we fit it on a stratified sample of 500,000 chunks and use
that fitted model to place the rest in batches of 50,000. The resulting
coordinates are written to a per-run table so that re-running the next step
is cheap.

## Step 3 — Group nearby points into clusters (HDBSCAN)

Once every chunk has 3D coordinates, we need to **find the clumps**. That's
what clustering does: it walks over the cloud of points and decides which
ones belong together as a topic.

We use **HDBSCAN** — *Hierarchical Density-Based Spatial Clustering of
Applications with Noise*. The intuition is "wherever the dots are densely
packed, that's a cluster; wherever they're sparse, that's the empty space
between clusters." HDBSCAN doesn't need you to tell it how many clusters to
look for — it figures that out from the data.

We run HDBSCAN **five times** at five different sensitivities, producing a
hierarchy:

| Level | Roughly this many clusters | What it represents                                                  |
|------:|---------------------------:|---------------------------------------------------------------------|
| 1     | ~30                        | Broad topic areas — "health care", "energy", "Indigenous rights"    |
| 2     | ~150                       | Sub-topics within each area                                         |
| 3     | ~600                       | Specific debates and recurring themes                               |
| 4     | ~2 000                     | Narrow conversations — a particular bill, a particular controversy  |
| 5     | ~6 000                     | Down to single conversations between a handful of speakers          |

When you click a level-1 cluster on the map, you see its level-2 children;
click again and you see level-3, and so on. The five-level hierarchy is
what makes the map feel like you're zooming in instead of just panning.

!!! info "Why we cluster on the 3D coordinates, not the 1024-d originals"

    HDBSCAN on 3.4 million × 1024 numbers would need many gigabytes of RAM
    and run for hours. On 3.4 million × 3 numbers it runs in minutes and
    fits comfortably in memory. The tradeoff is that we're clustering on a
    slightly lossy version of the data — but in practice, two chunks that
    UMAP places near each other in 3D are almost always near each other in
    1024D too, because that's exactly what UMAP was optimising for.

## Step 4 — Pick a label for each cluster (TF-IDF)

A cluster of 50,000 unlabelled dots isn't useful unless we can tell you
what's in it. The labelling step picks the **three most distinctive words**
for each cluster and joins them with dots — that's what you see under each
sphere on the map.

The technique is called **TF-IDF** — *Term Frequency–Inverse Document
Frequency*. Despite the long name, the idea is simple:

- A word is **high TF** for a cluster if it appears a lot in that
  cluster's chunks. ("Doctor" appears a lot in the health-care cluster.)
- A word is **high IDF** if it appears in *few other* clusters. ("Doctor"
  rarely appears in the energy or fisheries clusters.)
- TF-IDF multiplies those together. Words that are common in this cluster
  *and* rare elsewhere score highest. Generic words like "the", "and", or
  "Mr. Speaker" score low because they appear everywhere.

We compute this in both English and French (with stop-words for both
languages stripped out), so a French-language Quebec cluster gets French
labels and an English Hansard cluster gets English ones. The top three
words become the label; the next 17 are kept around for the cluster
drawer.

!!! info "Why we don't use a hosted LLM for labels"

    We considered asking a large language model like GPT-4 to read each
    cluster and write a one-line summary. We deliberately don't. TF-IDF is
    transparent: you can see exactly *why* a label says what it does (these
    were the rarest, most-distinctive words in this cluster). An LLM-
    generated label would be smoother to read but harder to audit and
    expensive to recompute. For a public-interest project, "auditable but a
    bit clunky" beats "polished but opaque."

The labelling step also picks the **15 chunks closest to the cluster's
centre** as representatives. That's what shows up in the cluster drawer
when you click into a topic — chunks that are the most "typical" of the
cluster, not random samples from its edges.

---

## Why filtering doesn't move the clusters

When you change a filter — say, from "all parties" to "NDP only" — the
clusters fade in and out instead of physically rearranging. This is on
purpose.

The clusters' positions on the map are computed from **the full corpus**.
That layout is the *reference frame* you build a mental map against. If we
re-projected the map every time you changed a filter, the housing cluster
might end up on the right one query and on the left the next, and you'd
have no way of remembering where anything is.

So instead, when you filter, we count how many chunks in each cluster
survive the filter. Clusters where most chunks survive stay opaque. Clusters
where few chunks survive fade to ~15% opacity. Clusters where no chunks
survive fade out entirely. The geography stays put; the lighting changes.

This is also why the filter is good at answering questions like "where in
the topic space do BC NDP members speak?" — the surviving lit-up clusters
*are* the answer.

## How often the map is rebuilt

The full pipeline (steps 1–4) takes 30 to 90 minutes to run end-to-end on
the full Hansard corpus. We don't run it on every speech ingestion — that
would be wasteful and would also keep moving the map under everyone's feet.
Instead we run it on a schedule, validate the result, and only then
**promote** it to the live version. The Explore page reads whichever run is
currently promoted.

If you're seeing speeches in [Hansard search](../searching/how-it-works.md)
that don't show up on the map yet, that's why — they're embedded but
haven't been included in a promoted projection run. The next rebuild will
absorb them.

## What this map is good for, and what it's not good for

**Good for:**

- Spotting *what gets talked about* in Canadian legislatures without
  having to know the right keyword first.
- Comparing topical coverage between parties, levels of government, or
  time periods (using filters).
- Finding adjacent topics — "the cluster next to climate is …" often
  reveals genuine policy adjacencies.
- Discovering recurring debates by drilling into level 4 or 5 clusters.

**Not good for:**

- Counting how often a politician spoke about a topic. Use a
  [politician profile](https://canadianpoliticaldata.org/politicians) or
  [Hansard search](https://canadianpoliticaldata.org/hansard) for that.
- Comparing exact distances between two clusters (UMAP doesn't preserve
  global distance reliably).
- Real-time analysis. The map lags reality by however long ago the last
  rebuild was promoted.
- Anything beyond spoken Hansard. Bill text, votes, and committee
  transcripts aren't on the map (yet — committee transcripts are on the
  roadmap).

## Where to go next

- [Filters and tips for Hansard search](../searching/filters.md) — the
  filter shapes work the same way on the Explore page.
- [How search works](../searching/how-it-works.md) — same embedding model,
  used differently.
- [Coverage and data sources](../getting-started/coverage.md) — what's in
  the corpus the map is built from.
