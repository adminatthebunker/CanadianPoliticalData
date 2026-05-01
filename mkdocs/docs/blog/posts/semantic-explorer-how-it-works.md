---
date: 2026-04-30
authors:
  - adminatthebunker
slug: semantic-explorer-how-it-works
description: >-
  We had 3.4 million speech-chunk embeddings sitting in Postgres and no way
  to *see* them. Here's the four-step chain — embed, UMAP, HDBSCAN, TF-IDF —
  that turned those vectors into a browseable topic map of Canadian
  political speech, plus the new explainer page that opens the hood.
tags:
  - semantic-search
  - embeddings
  - explore
draft: false
---

# From 3.4 million vectors to a topic map: how the Semantic Explorer got built

Two weeks ago I wrote about
[rebuilding the embedding pipeline](faster-embeddings-months-to-hours.md) —
trading BGE-M3 for Qwen3-Embedding-0.6B, swapping a hand-rolled FastAPI
wrapper for Hugging Face's TEI, and going from 4.7 chunks per second to 50.
That post ended with the historical backfill in flight. This post is what
happened next.

The backfill finished. 3.4 million speech chunks, every one of them with a
1024-number "fingerprint of meaning" sitting in a Postgres column. Search
worked beautifully — type a query, get back semantically similar chunks in
milliseconds. But there was a question I kept getting that search couldn't
answer: *what is even in this dataset?* You can't search for what you
don't know to look for.

The Semantic Explorer is the answer to that question. It's now live at
[/explore](https://canadianpoliticaldata.org/explore), and there's a new
technical explainer at
[docs.canadianpoliticaldata.org/explore/how-it-works](https://docs.canadianpoliticaldata.org/explore/how-it-works/)
that walks through every choice in detail. This post is the story of how
it got built — what I tried, what I changed my mind about, and what
shipped.

<!-- more -->

## The problem

A 1024-dimensional vector is a list of 1024 numbers. You cannot draw it.
You cannot picture it. You cannot point at one and say "that one is about
housing" — the meaning is distributed across all 1024 directions in a way
the model learned from training and that no human can read off.

Search papers over this by only ever asking the question "which chunks are
nearest to *this* one?" You never have to look at the space directly; you
just probe it. That works great for a known query. It's useless if the
question is "what topics does this Parliament *cover*?"

I wanted a map. Not a search box — a map. Something where you could see
the whole corpus at once, see what clumps together, and click into a
clump to find out what it was. The four-step chain that turns 1024
numbers into a clickable dot looks like this:

```
embed → UMAP → HDBSCAN → TF-IDF
 ↑       ↑       ↑          ↑
 done   3D      groups    labels
        coords  the
                clumps
```

Each arrow is a decision. Some of those decisions I got right the first
time. Some I changed my mind about partway through. Here's what I
learned at each one.

## Step 1: the embeddings were already done

This is the cheap one to talk about because the
[previous post](faster-embeddings-months-to-hours.md) covered it in
detail. By the time I started building the Explorer, every speech chunk
in the corpus already had a Qwen3-Embedding-0.6B vector sitting in
`speech_chunks.embedding`. The git log around mid-April reads like a
shopping list of what it took to get there:

- `feat(embed): TEI service for Qwen3-Embedding-0.6B indexing path`
- `feat(scanner): embed-speech-chunks-next via TEI with batched UNNEST writes`
- `fix(embed): upgrade cuDNN 9.1 → 9.5.1 to clear sm_89 fp16 attention bug`
- `refactor: collapse embedding/embedding_next into single canonical column`

The blue-green column dance (`embedding` → `embedding_next` → back to
`embedding`) was how I migrated from BGE-M3 to Qwen3 without taking
search down. Once the migration was finished, the parallel column got
collapsed back into one. Future me can re-embed if a better model comes
along, but the canonical shape is one column, one HNSW index, one truth.

Total throughput at the end of that phase: 50.9 chunks per second on a
6 GiB laptop GPU. Total corpus: 3.4 million chunks. That's the input to
everything below.

## Step 2: 1024 dimensions down to 3, with UMAP

To draw a map I need x, y, and z — three numbers per chunk, not 1024.
The standard tools for this are PCA, t-SNE, and UMAP, and I'd used all
three in past lives.

I picked UMAP for two reasons. First, it scales to millions of points
without falling over (t-SNE doesn't). Second, it's known to preserve
*local* structure well — if two chunks were close in 1024D, they should
end up close in 3D — and that's the property the map actually depends
on. PCA preserves global *variance* but doesn't care about
neighbourhoods, which makes it lousy for the use case.

The first thing that didn't work: trying to fit UMAP on the full corpus
at once. 3.4 million chunks × 1024 floats × 4 bytes is roughly 14 GB of
embeddings. UMAP's neighbour graph construction needs another several
gigabytes of working set on top of that. The box has 32 GB of RAM and
runs Postgres + the API + everything else on top, so a peak UMAP
working set in the 25-30 GB range was off the table.

The fix is the standard one: fit on a sample, transform the rest. I fit
UMAP on a stratified 500,000-chunk sample (about 2 GB of working set),
which captures enough of the density landscape to produce stable
coordinates. Then I run the fitted model in 50,000-chunk batches over
the remaining 2.9 million. The whole fit-plus-transform takes about 25
minutes.

The other thing I learned the hard way: **distances on a UMAP map are
not metric**. Two clusters being far apart on the screen doesn't mean
they're far apart in the original 1024D space. UMAP optimises local
neighbourhoods at the cost of global geometry, which is exactly what
you want for a *qualitative* layout but a foot-gun if you ever try to
read distances quantitatively. The explainer page makes this explicit
because someone is definitely going to try.

## Step 3: finding the clumps with HDBSCAN — and the three-to-five-levels pivot

The 3D coordinates give me a cloud. The cloud has clumps. I need to
find them and label them.

I picked HDBSCAN over k-means for one big reason: I don't know how
many topics are in Canadian Hansard, and I don't want to pretend I do.
K-means makes you commit to *k* up front and then forces every point
into one of *k* clusters whether it belongs or not. HDBSCAN figures out
the cluster count from the density of the data and is happy to leave
sparse points unclustered. That's the right shape for political speech,
where some chunks are core to a topic and others are scattered between
topics.

The first version shipped with **three levels** of clustering: broad
(~30 clusters), mid (~200), fine (~1500). Internally I called these
"continents, countries, cities." I built it, I demoed it to myself, I
clicked into a fine-grained cluster, and I had a problem: a cluster of
1,500 chunks is still way too big to skim. The drawer would show 15
representative chunks, fine, but the *cluster itself* was still a mess
of conversations from different debates that just happened to be
nearby.

The fix was to keep going. I added two more levels — one at ~2,000
clusters of about 1,000 chunks each, and one at ~6,000 clusters of
about 500. The deepest level gets you down to "this is one specific
exchange between four MPs about one specific bill on one specific day."
That's the resolution where the cluster itself becomes a coherent
thing to read, not just a sample from one.

The five-level pivot also reshaped the UI. The first version made you
click a cluster to drill in, and singleton chains (level-1 cluster
with one level-2 child with one level-3 child) made for awkward
dead-end clicks. The fix was a small piece of frontend logic that
auto-skips singleton chains when you click — you land at the next
*branching* descendant, not the next level. Three lines of code, big
ergonomic improvement.

There's also a memory choice worth being explicit about: HDBSCAN runs
on the **3D coordinates**, not the original 1024D embeddings. On 3.4M
points × 1024 floats it would have OOMed the box; on 3.4M × 3 it runs
in minutes. The cost is that we're clustering on a slightly lossy view
of the data. In practice it doesn't matter, because UMAP was
*specifically* optimised to preserve neighbourhoods — two chunks that
are nearby in 3D are almost always nearby in 1024D too. Validated this
spot-check style by sampling cluster pairs and checking their original-
space cosine similarities. Held up.

## Step 4: TF-IDF labels over LLM labels

A cluster of 50,000 unlabelled dots is useless. The label is what makes
it a topic.

The two real options were:

1. **TF-IDF**: for each cluster, find the words that appear a lot in
   that cluster's chunks but rarely in other clusters' chunks. Take the
   top three. Done.
2. **LLM**: send each cluster's chunks (or a sample) to GPT-4 or
   similar and ask it to write a one-line summary.

The LLM version produces nicer prose. "Carbon pricing as climate
policy: debates over the carbon tax and its effects on Canadian
households" reads better than `carbon · price · pollution`. I built a
prototype that called OpenRouter for label generation, looked at the
output, and then deliberately threw it away.

Two reasons:

**Auditability.** Look at a TF-IDF label and you can see exactly why
it says what it does — those were the rarest, most-distinctive words
in that cluster, period. There's no judgement, no style, no risk of an
LLM smoothing over an actual disagreement in the cluster to write
better prose. For a public-interest tool people might cite, "rougher
but auditable" beats "smoother but opaque." Every time.

**Cost and re-runnability.** A full label pass over 8,000+ clusters
costs cents in TF-IDF and dollars-to-tens-of-dollars in LLM API calls.
Rebuilding the map is a thing I want to do *often* — every time the
corpus grows by a few hundred thousand chunks, every time I tune the
clustering, every time I try a different sample size. Locking that
into a billable external API would have changed the project's
incentive structure in a way I didn't want.

The labels are computed in both English and French (with stop-words
for both languages stripped) so a French-language Quebec cluster gets
French labels and an English Hansard cluster gets English ones. The
top three become the visible label; the next 17 are kept around for
the cluster drawer.

## The decision I'm proudest of: filters don't move the map

This one isn't in the four-step pipeline above. It's a UX decision,
and I think it's the most important call in the whole feature.

When you change a filter on the Explore page — say, from "all parties"
to "NDP only" — the clusters do not physically rearrange. They fade.
Clusters where most chunks survive the filter stay opaque. Clusters
where few survive go translucent. Clusters where none survive fade
out entirely. The geography stays put; the lighting changes.

The first prototype re-projected on every filter change. It looked
amazing the first time you saw it — clusters morphing into a new
arrangement is a great demo. It was useless. Every time you tweaked a
filter the housing cluster moved somewhere different on the screen,
and you could never build a mental map of "where things are." You
were always re-orienting from scratch.

The fade-don't-move version turns the layout into a stable reference
frame that you build intuition against over weeks. Once you know that
"down and to the left is fisheries and oceans" you can ask "where do
BC Greens speak?" and *read the answer off the lit-up regions*. That's
what makes it a map and not just an interactive scatter plot.

I broke the rule once during prototyping by adding a "re-cluster on
the filtered subset" toggle. Took it out before merge. The toggle
re-introduced exactly the disorientation I'd designed the fade-only
mode to avoid. Some features earn their keep by being the *only*
behaviour, not one of two.

## The doc page that opens the hood

All of the above is now written up at
[docs.canadianpoliticaldata.org/explore/how-it-works](https://docs.canadianpoliticaldata.org/explore/how-it-works/).
It's pitched at a grade-12 reading level — no machine-learning
background required — and walks through each of the four pipeline
stages with the tradeoffs explained in plain English. Why 1024
dimensions and not 64 or 4096. Why UMAP and not t-SNE. Why HDBSCAN and
not k-means. Why TF-IDF and not an LLM. Why filtering fades.

There's also a link to it from the Explore page itself, right next to
the 2D/3D toggle. If you've ever been on the Explore page and thought
"this looks cool but I have no idea what I'm looking at," that link is
for you.

Some of this is the kind of detail that usually only lives in a
project's internal architecture docs. I'm putting it on the public
docs site on purpose — civic-data tooling that hides its methodology
is harder to trust than civic-data tooling that doesn't. If a future
reader wants to argue with my choice of TF-IDF over GPT-4 labels,
they're entitled to the receipts.

## What's running now, and what's next

The first promoted projection run is live. Filtering works. Drilling
through the five-level hierarchy works. The cluster drawer pulls
representative chunks with one-click jumps to the full speech in
[Hansard search](https://canadianpoliticaldata.org/hansard).

Things I haven't built yet but want to:

- **Trail-of-breadcrumbs deep links.** Right now the URL preserves
  your filter state and your selected cluster but not the full
  zoom/focus history. Sharing a link should reproduce the exact view
  the sender had.
- **Diffing two filter states.** "What does the cluster pattern look
  like for Liberal MPs in 2015 vs. 2025?" should be a side-by-side
  view, not a thing you flip back and forth between.
- **Committee transcripts.** The corpus is currently floor speech
  only. The committee transcripts pipeline is the next major
  ingestion target; once it's in, the map gets several thousand more
  fine-grained clusters representing the conversations that don't
  happen on the floor.

If you've read this far and want to play with the result, it's at
[/explore](https://canadianpoliticaldata.org/explore). Open it on a
desktop browser if you can — the 3D mode is where the affordances
work best — and click into a few level-1 clusters to start. The map
takes some getting used to, but the click-to-drill mental model
becomes second nature after a couple of minutes.

This is what I built the embeddings for.
