---
title: How search works
description: A plain-language explanation of semantic and keyword search on Canadian Political Data.
---

# How search works

Hansard search uses two layers, in order:

1.  **Semantic search** — your query is converted to a vector (a numeric
    fingerprint of its meaning) and compared against the same kind of
    fingerprint computed for every speech chunk in the database.
2.  **Optional keyword filters** — you can narrow results by speaker,
    party, jurisdiction, date range, etc. without changing the semantic
    ranking.

Results are sorted by **semantic similarity** by default. You can re-sort
by date or speaker.

## Why semantic, not just keywords

A keyword search only finds speeches that contain the exact words you
typed. Semantic search finds speeches that **mean** something similar to
what you typed, even if they use entirely different words.

!!! example "Concrete example"

    Search: `government should not subsidize fossil fuel companies`

    A keyword search would only find speeches with that exact phrase.

    Semantic search returns speeches arguing against oil and gas tax
    breaks, against pipeline funding, for ending subsidies, against
    LNG support, and so on — including ones that never use the word
    "subsidize" or "fossil fuel."

## What gets searched

Every speech in our Hansard corpus is split into smaller **chunks**
(typically a few sentences each). Each chunk is embedded into a 1024-
dimensional vector and indexed. When you search:

- Your query is embedded with the same model.
- The system retrieves the most-similar chunks across the whole corpus.
- Chunks are grouped back into the speeches they came from for display.
- Each result shows the most relevant chunk, with a link to the full
  speech in context.

## What does **not** affect ranking

- The popularity of the speaker.
- The political party of the speaker.
- How recently the speech was made (unless you sort by date).
- How long the speech is.

The ranking is purely about semantic similarity to your query. This is
deliberate — it would be easy to bury small-party voices behind a "boost
ruling-party speeches" rule, and we don't.

## Tips for better results

- **Ask the way you'd ask a person.** "What does X think about Y?" works
  better than just "X Y."
- **Be specific where it matters.** `child care fee reductions outside
  Quebec` returns better results than `child care`.
- **If the first results are wrong, rephrase rather than scrolling.** A
  better query usually beats deeper paging.
- **Use filters to slice, not to define.** Filter to "Liberal" if you want
  Liberal MPs' speeches on a topic — but the semantic query still defines
  *what* you're looking for.

## What if I want exact phrases?

Wrap a phrase in straight double quotes (`"..."`) to require it appear
verbatim. This re-ranks results to favour matches with that phrase, but
still uses semantic similarity for ordering. For pure boolean / regex
search, this isn't the right tool — Hansard.ca and OpenParliament both
expose keyword search if that's what you need.

## Languages

Most provincial legislatures publish in English, with the federal Parliament
and the Quebec National Assembly publishing in both English and French (and
Quebec primarily in French). The embedding model is multilingual, so a
French query can return French-language speeches; an English query about a
Quebec topic will return relevant French speeches alongside English ones.

Translation between the two is not yet a built-in feature — we surface the
original. For mixed-language searches, ask the question in the language you
want most of the answers in.

## Privacy of your searches

Search queries are not associated with your account unless you explicitly
[save the search](saved-searches.md). Anonymous searches are logged in
aggregate (counts, latencies) for performance tuning, never with your IP or
the query string itself.
