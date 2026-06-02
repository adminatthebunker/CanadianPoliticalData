---
title: For contributors
description: Run Canadian Political Data locally, download the dataset, and explore the architecture.
---

# For contributors

This section is for developers, researchers, and operators who want to
run the system themselves, work with the underlying dataset, or
understand how the pieces fit together.

There are two paths, depending on what you need:

<div class="grid cards" markdown>

-   :material-docker:{ .lg .middle } **Run the whole stack**

    ---

    Spin up the full system on your own hardware via Docker Compose:
    Postgres, the API, the React frontend, the Python scanner, and the
    embedding service. Bootstraps its own dataset by ingesting from
    the same upstream sources we do.

    Best for: developers contributing to the codebase, operators running
    a private mirror, or anyone who wants the live ingestion pipeline.

    [:octicons-arrow-right-24: Local installation](local-install.md)

-   :material-database-arrow-down:{ .lg .middle } **Just the data**

    ---

    Want the dataset for your own SQL without standing up the full
    stack? Run the scanner's ingestion pipeline locally to bootstrap a
    fresh corpus from the same upstream sources — the local-install
    path above covers it end to end.

    [:octicons-arrow-right-24: Bootstrapping the dataset](local-install.md#bootstrapping-the-dataset)

</div>

## What's coming

Detailed reference for the scanner CLI, the HTTP API surface, the
ingestion playbook for new jurisdictions, and the architectural deep-dive
will land in this section in subsequent passes. For now, see the inline
README and source comments in the codebase, or [contact us](../about/contact.md)
if you're trying to do something specific and the public docs don't
cover it yet.

## Source

The codebase is **public on GitHub**:
[`adminatthebunker/CanadianPoliticalData`](https://github.com/adminatthebunker/CanadianPoliticalData).
The internal name is `sovpro` (a contraction of *SovereignWatch* +
*project*); the public brand is *Canadian Political Data*. Both names
refer to the same project — you'll see `sovpro` in path names, the CLI,
and container labels.

Issues, pull requests, and discussion are welcome on the GitHub repo.
For larger contributions or institutional partnerships,
[get in touch](../about/contact.md) so we can talk before you sink time
into a substantial branch.

## Reuse and citation

- For citing data you found through the site, link to the speech /
  bill / politician page directly. Each page URL is stable.
- For bulk reuse, the underlying records come from public legislative
  sources under their respective open-government licences — see the
  per-jurisdiction notes in the repo's `docs/data-sources.md`.
- For UI screenshots in publications, no permission needed — credit
  *canadianpoliticaldata.org*.
