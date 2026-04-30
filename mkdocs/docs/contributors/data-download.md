---
title: Dataset download
description: Direct download of the Canadian Political Data dataset — coming soon.
---

# Dataset download

!!! warning "Coming soon"

    A direct download of the Canadian Political Data dataset is **not
    yet available**. We're working through the privacy and data-scrubbing
    review needed to publish a snapshot that excludes user accounts,
    saved searches, billing data, and other non-public artifacts.

    This page will be updated with the download link, full schema notes,
    and load instructions when the snapshot is published.

## What you'll get when it ships

When the snapshot is published, this page will document:

- A direct-download URL for the latest snapshot.
- The dump format — currently planned as one or more **gzipped
  PostgreSQL dumps** (the same shape as `sovpro db backup`, i.e.
  `pg_dump | gzip` plain-SQL, restorable via `gunzip -c | psql`).
- Step-by-step load instructions for Postgres 16 with PostGIS,
  pgvector, and unaccent.
- The list of tables included (politicians, speeches with embeddings,
  bills, ridings, infrastructure scans) and the list excluded (user
  accounts, auth tokens, saved searches, reports, billing).

## Refresh cadence (planned)

Once shipped, the dataset will be refreshed **approximately weekly**,
after each significant ingest pass. The download URL will always point
at the latest snapshot. If you need a frozen point-in-time copy, mirror
the snapshot you used and cite the date you downloaded.

## Licence (planned)

The published dataset will be released under a **Canadian-friendly,
non-commercial licence** — most likely
[Creative Commons Attribution-NonCommercial 4.0 (CC BY-NC 4.0)](https://creativecommons.org/licenses/by-nc/4.0/),
which is widely understood internationally and works under Canadian
law. The exact terms will be locked in and published alongside the
download.

In short: free for journalism, research, education, and civic-tech
projects, with attribution. Commercial reuse requires a separate
arrangement — [contact us](../about/contact.md).

## In the meantime: bootstrap your own copy

Until the snapshot is published, the working alternative is to **run
the ingestion pipeline locally** and let it build the corpus from the
upstream sources we ourselves ingest from. This is exactly what the
production system does — just on your hardware.

The full how-to is on the [Local installation](local-install.md) page,
specifically the
[Bootstrapping the dataset](local-install.md#bootstrapping-the-dataset)
section.

In one paragraph: you bring up the Docker Compose stack, run the seed
and ingest commands (federal MPs, provincial rosters, then per-
jurisdiction Hansard), and the scanner + embedding service do the rest
on a continuous loop. Building a complete current-session corpus from
cold takes hours; building a complete historical corpus across every
covered jurisdiction takes considerably longer — but you can scope to
just the jurisdictions you care about and skip the rest.

This route also gives you **continuously fresh data** instead of weekly
snapshots, which matters if you're tracking ongoing legislative
activity in real time.

## Want early access?

If you have a research, journalism, or civic-tech use case that would
benefit from an early snapshot — even one with rougher edges than the
public version will have — [contact us](../about/contact.md). We're
happy to share what we have under a short reuse agreement while the
public version comes together.
