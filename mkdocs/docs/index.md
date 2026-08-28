---
title: Canadian Political Data — Help & Docs
description: >-
  A sovereign record of Canadian political activity — electoral boundaries,
  rosters and Hansard taken directly from the agencies that produce them and
  held on Canadian infrastructure, with no third-party mirror in between. How
  to search Hansard, find your representatives, set up alerts, and generate
  AI-assisted reports.
---

# Canadian Political Data

**Canadian Political Data** is a public-interest project that makes Canadian
political activity searchable, comparable, and accountable. Hansard speeches,
elected officials, ridings, and the public infrastructure that supports them —
all in one place, with semantic search across federal and provincial
legislatures.

The site is free to use. An optional account unlocks saved searches, email
alerts, and credit-funded AI reports.

## Sovereign by construction

Canadian political data has a habit of being held one step removed from the
people it describes — aggregated by an intermediary, mirrored abroad, or
dependent on a service that can quietly stop being maintained.

This project is built the other way round:

- **Primary sources, not a mirror.** Electoral boundaries come from Elections
  Canada, the thirteen provincial and territorial chief electoral officers,
  and individual municipalities. Rosters come from each legislature's own
  member directory, or from the province's own published election result.
  Nothing sits between those agencies and this database.
- **Held here, not rented.** The corpus, the geometry and the search index all
  live on Canadian infrastructure we run. Answering "who represents this
  address?" needs no live call to anyone else — which matters, because in
  August 2026 the aggregator this project used to depend on was unreachable
  for eleven days and every postal-code lookup in the country failed with it.
  That dependency is gone.
- **Dated, not just current.** Boundaries carry the generation they belong to
  and the date it took effect, and superseded maps are kept rather than
  deleted — so the site can answer for a date, not only for today.

⚠ **And where it is not current, it says so.** Federal and provincial rosters
are ingested daily. Municipal rosters are rebuilt from official election
results in Québec and Ontario; for the remaining provinces they are *frozen*
at the last state of a source we no longer ingest from — accurate as of a
known date, but unable to notice a change since. The
[coverage page](getting-started/coverage.md) breaks this down rather than
averaging it into a single reassuring number. A record that tells you where it
is weak is worth more than one that claims to be uniformly strong.

[Open the main site :material-arrow-right:](https://canadianpoliticaldata.org){ .md-button .md-button--primary }
[Coverage status :material-map-marker-check:](getting-started/coverage.md){ .md-button }
[Local installation :material-docker:](contributors/local-install.md){ .md-button }

---

## Where to start

<div class="grid cards" markdown>

-   :material-magnify:{ .lg .middle } **Search Hansard**

    ---

    Find what your representatives have said — by topic, person, party, date,
    or jurisdiction. Semantic search means you can ask in plain language.

    [:octicons-arrow-right-24: How search works](searching/how-it-works.md)

-   :material-account-search:{ .lg .middle } **Find a politician**

    ---

    Browse every federal MP and provincial MLA / MNA / MPP, with party,
    riding, term history, and links to their speeches and votes.

    [:octicons-arrow-right-24: Politicians directory](politicians/index.md)

-   :material-bell-ring:{ .lg .middle } **Save a search and get alerts**

    ---

    Sign in with your email, save a search, and we'll email you when new
    speeches match. No password — just a magic link.

    [:octicons-arrow-right-24: Saved searches](searching/saved-searches.md)

-   :material-file-document-multiple:{ .lg .middle } **Generate a report**

    ---

    Spend credits to ask the system to compile an evidence-cited report on a
    politician's position, voting record, or rhetoric over time.

    [:octicons-arrow-right-24: Reports & credits](reports/index.md)

</div>

---

## What this site is — and isn't

!!! info "Public interest, not neutral"

    Canadian Political Data is rooted in democratic and access-to-information
    values. It is **not** a politically neutral product. The data is presented
    as faithfully as possible, but the editorial choices about what to cover
    and what to surface are deliberately civic-minded.

!!! warning "Coverage is growing"

    Federal coverage (House of Commons + Senate) is the most complete.
    Provincial and territorial coverage varies — see
    [Coverage and data sources](getting-started/coverage.md) for the live
    picture. If a jurisdiction you care about is missing, that is almost
    always because the upstream legislature publishes its data in a way that
    we are still working to ingest cleanly, not because we are uninterested.

---

## Built for

- **Journalists and researchers** — fast access to primary-source legislative
  speech with citation-ready links.
- **Civic organizers** — track positions over time, set alerts on issues that
  matter to your community.
- **Students and educators** — a corpus to query, not a curated reading list.
- **Engaged citizens** — see what the people who represent you are actually
  saying in the chamber.

If you are a developer or contributor looking for the runtime architecture,
scanner CLI, or API reference, see [Contributors](contributors/index.md).
