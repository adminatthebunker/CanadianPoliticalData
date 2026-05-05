---
title: How Hansard search works
description: A plain-language walk-through of how typing a phrase into Hansard search becomes a ranked list of speeches — embedding the query, narrowing by filters, vector retrieval, and how the timeline and by-politician views differ.
---

# How Hansard search works

The [Hansard search page](https://canadianpoliticaldata.org/search) lets you
ask, in plain language, *who has said what in Canadian legislatures*. This
page explains what's actually behind the search box — what your query gets
turned into, how the database picks which paragraphs to show you, and why
ranking deliberately ignores some things you might expect it to use. The
technical detail is real, but the reading level is deliberately kept around
grade 12: no machine-learning background required.

[Open Hansard search :material-magnify:](https://canadianpoliticaldata.org/search){ .md-button .md-button--primary }

## The four-step pipeline at a glance

```
Your query → embed query → narrow by filters → vector search → group + rank
   (text)     (1024 nums)     (SQL WHERE)        (HNSW index)   (timeline / by politician)
```

Every result you see is one **speech chunk** — usually a paragraph or two
from a single politician's turn at the microphone, lifted from the official
Hansard transcript. The system is searching across millions of these chunks
in well under a second.

The four steps below explain how a phrase you type becomes a ranked list of
those chunks.

---

## Step 1 — Turn your query into 1024 numbers (embedding)

The hard part of this whole system is teaching a computer that

> "rising cost of groceries"

and

> "food prices keep going up"

are talking about the same thing — even though they share almost no words.

The trick is called an **embedding**. An embedding model is a piece of
software that reads a chunk of text and turns it into a list of numbers.
Two pieces of text that mean similar things end up with similar lists of
numbers. Two pieces of text about totally different topics end up with very
different lists.

We use a model called **Qwen3-Embedding-0.6B** — the same model that
powers the [Semantic Explorer](../explore/how-it-works.md). For every
query you type, it produces a list of **1024 numbers**. You can think of
those 1024 numbers as coordinates in a space that has 1024 directions
instead of the 3 we're used to in real life. Different directions in that
space roughly track different aspects of meaning — cost-of-living talk,
Indigenous-rights talk, climate talk, and so on. Nobody hand-codes those
directions; the model learned them by reading enormous amounts of text
during training.

Every Hansard speech chunk in the database has already been turned into
its own list of 1024 numbers, ahead of time. Search comes down to: *find
the chunks whose numbers are closest to the numbers we just computed for
your query.*

!!! info "Why we wrap your query with an instruction prefix"

    Before embedding, the API silently prepends a short instruction to
    your query — something like
    *"Instruct: Given a parliamentary search query, retrieve relevant
    Canadian Hansard speech excerpts. Query: …"*. The Hansard chunks
    themselves are indexed *without* this prefix.

    This asymmetric treatment isn't a quirk; it's how Qwen3 was trained.
    On our corpus, adding the instruction prefix to queries roughly
    doubled retrieval quality compared to running the model "naked." The
    stored vectors and the live query vector aren't quite the same shape
    of object — one represents *a passage*, the other represents *what
    you're looking for in passages* — and labelling them differently is
    what lets the model tell them apart.

## Step 2 — Narrow by your filters (SQL WHERE)

Before the system goes hunting through millions of vectors, it first
throws away every chunk that doesn't match your filters. The filters get
combined with **AND**, not OR — every condition has to hold.

Filters available today:

- **Language** — English, French, or any
- **Level** — federal, provincial, or municipal
- **Province / territory** — any of the 13
- **Politician** — pin up to 10 specific people to compare them side by side
- **Party** — at the time of the speech (party switches are tracked)
- **Date range** — from / to, inclusive
- **Parliament + session** — both must be set together
- **Speech type** — floor, committee, question period, statement, point of order
- **Hide presiding-officer turns** — drops procedural Speaker / Chair /
  Président turns, which otherwise pollute results in long debates

Filters apply *before* the vector search runs. That means HNSW (next step)
only has to look at the candidate set that already matches your jurisdiction,
party, date window, and so on — not the whole corpus.

!!! info "Why filtering happens *before* vector search, not after"

    Vector search is fast but not free — scanning the index for nearest
    neighbours across millions of chunks takes real CPU. If we ran the
    vector search first and *then* filtered, we'd often throw away 95% of
    the work we just did. Filtering first means the index only has to
    sift through chunks that already meet your structural criteria, so a
    tightly-filtered query (say, "BC NDP, 2024 onwards, French only") is
    much faster than an unfiltered one — exactly the opposite of how
    keyword search usually behaves.

## Step 3 — Find the nearest chunks (HNSW vector search)

For the candidates that survived your filters, the system finds the ones
whose 1024-number lists are **closest** to your query's 1024-number list.
Closeness is measured with **cosine distance** — the angle between two
vectors, ignoring how long they are. Two chunks pointing in the same
direction are "near" each other regardless of magnitude.

Doing this naively across millions of chunks would be slow. Instead, the
chunks are indexed with a structure called **HNSW** — *Hierarchical
Navigable Small World graph*. The intuition is "build a graph of which
chunks are near which other chunks ahead of time, then walk that graph
greedily to find the nearest neighbours of any new query." Lookups are
sub-second even on millions of vectors, at the cost of building the
graph once when chunks are first indexed.

You can tighten what counts as a real match using the **minimum similarity**
slider. Cosine similarity ranges 0 to 1 (higher = more similar); the server
floor is 0.45, and you can raise it as high as 0.8. A higher threshold gives
you fewer but more obviously on-topic results.

!!! info "Why we search chunks, not whole speeches"

    A 20-minute committee turn often covers half a dozen unrelated topics
    — the speaker introduces themselves, thanks the committee, gives an
    update on one file, then transitions to a totally different file.
    Embedding the whole turn as one vector would average all those topics
    into mush, and the relevant paragraph would never surface for a
    focused query.

    Splitting each speech into paragraph-sized chunks and embedding each
    chunk separately means a single relevant paragraph can rise to the
    top of your results without dragging the unrelated 19 minutes along
    with it. Each result's "View speech →" link takes you back to the
    full turn with that exact chunk highlighted in context.

## Step 4 — Group and rank for display

The matched chunks come back ranked by similarity (or, if you ran an empty
query, by date — useful for browsing what's been said most recently). You
can view that ranked list three different ways:

- **Timeline** — a flat list, one card per chunk, ordered strictly by how
  closely each chunk matches your query.
- **By politician** — chunks regrouped under each speaker, with up to five
  matching quotes per politician. Sortable by total mentions, by best
  single match, by average match across all their hits, or by raw keyword
  hits. This view is built for "who has talked about this, and how much?"
  questions.
- **Analysis** — a chart dashboard showing who, what, and when across the
  result set: top speakers, party split, year-by-year timeline, language
  split. Also the home of the **paid AI analyses** — "Synthesize this
  search" turns the top-N matches into a one-paragraph + five-bullet
  brief with citations; "Map stances" groups speakers by where they sit
  on the topic (for / against / conditional). Both costs preview before
  you commit. See the [reports section](../reports/index.md) for how
  credits work.
- **Map** — a 3D semantic mind-map of the result set, useful for
  exploring how the matched chunks cluster topically.

In each result snippet, you'll see the words from your query shown in
**bold**. That bolding is added by Postgres's `ts_headline` function on
top of the semantic ranking — it's a *visual aid* showing where literal
keyword matches occur, not what determined the order. A chunk can rank
extremely high without containing any of your query's exact words; that's
the whole point of embedding-based search.

!!! info "Why ranking ignores popularity, party, and recency"

    None of these affect ranking:

    - The popularity of the speaker
    - The political party of the speaker
    - How recently the speech was made (unless you sort by date)
    - How long the speech was

    The ranking is purely about semantic similarity to your query. This
    is deliberate. It would be easy to add a "boost ruling-party voices"
    rule, or a "down-rank speeches older than five years" rule. We don't,
    because both choices would silently shape what users see in ways that
    serve incumbency. A small-party MP and a cabinet minister speaking on
    the same topic get the same shot at the top of your results.

---

## Tips for better results

- **Ask the way you'd ask a person.** "What does X think about Y?" works
  better than just "X Y."
- **Be specific where it matters.** *child care fee reductions outside
  Quebec* returns better results than *child care*.
- **If the first results are wrong, rephrase rather than scrolling.** A
  better query usually beats deeper paging.
- **Use filters to slice, not to define.** Filter to "Liberal" if you
  want Liberal MPs' speeches on a topic — but the semantic query still
  defines *what* you're looking for.

## What about exact phrases?

Wrap a phrase in straight double quotes (`"..."`) to push results that
contain those exact words to the top. This re-ranks toward verbatim
matches but still uses semantic similarity for the underlying ordering.

For *pure* boolean or regex search — `(climate AND emergency) NOT motion`
style queries — this isn't the right tool. [OpenParliament](https://openparliament.ca)
and the official Hansard sites expose proper keyword search engines that
handle that case directly.

## Languages

Most provincial legislatures publish in English, with the federal
Parliament and the Quebec National Assembly publishing in both English
and French (and Quebec primarily in French). Qwen3-Embedding is a
multilingual model, so an English query will return relevant
French-language chunks if they're semantically close, and vice versa —
the model places them near each other in vector space regardless of
which language they happen to be in.

Translation between the two is **not** a built-in feature. We surface the
original text. For mixed-language searches, ask the question in the
language you want most of the answers in.

## What this search is good for, and what it's not good for

**Good for:**

- Finding speeches on a topic without knowing the right keyword first.
- Comparing what different speakers say about the same idea — the
  "by politician" view is built for this.
- Surfacing adjacent phrasings of a position (anti-pipeline, anti-LNG,
  anti-fossil-subsidy, pro-just-transition often share semantic space).
- Pulling a representative sample of quotes on a topic for research,
  reporting, or briefing notes.

**Not good for:**

- Boolean / regex queries (`A AND NOT B` style). Use OpenParliament or a
  dedicated keyword search engine.
- Counting raw word frequencies — a chunk can rank high without
  containing your query word at all, so similarity isn't a count.
- Anything beyond Hansard. Bill text, votes, and most committee
  transcripts aren't currently in the searchable corpus. Federal
  committees are partially in; provincial committees are not yet.
- Guaranteed coverage of the most recent days — there's an ingestion lag
  between a speech being delivered and being indexed.
- Queries against speeches whose embeddings haven't been computed yet.
  When historical sessions are still being backfilled, the page shows a
  "Backfill in progress" banner with the current coverage percentage —
  watch for it.

## Privacy of your searches

Search queries are not associated with your account unless you explicitly
[save the search](saved-searches.md). Anonymous searches are logged in
aggregate (counts, latencies) for performance tuning, never with your IP
or the query string itself.

## Where to go next

- [Filters and tips for Hansard search](filters.md) — the per-filter
  reference, with examples.
- [Saved searches and alerts](saved-searches.md) — turn a search into a
  recurring email digest when new matching speeches show up.
- [How the Semantic Explorer is built](../explore/how-it-works.md) — same
  embedding model, used to draw a map instead of return a ranked list.
