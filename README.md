# Canadian Political Data

> **The most accessible political data website in Canada — open source to the core.**
>
> Who represents you, what they've said, how they've voted, and where their infrastructure lives. Across every level of government, every province and territory, as far back as the digital record goes.

Canadian Political Data tracks elected officials across every level of Canadian government — every currently-sitting federal MP and senator (plus historical MPs back to 1994 via the Hansard pipeline), every provincial and territorial legislature, and municipal councils from coast to coast.

The public site is **free and the dataset is open**. Enter a postal code at **[canadianpoliticaldata.ca](https://canadianpoliticaldata.ca)** and see your own MP, MLA, and councillors — with their parliamentary record, their social handles, and where their websites are hosted.

Live coverage numbers, route map, and what's currently ingested live on the site itself — see **[/coverage](https://canadianpoliticaldata.ca/coverage)** for the honest, up-to-the-minute picture.

---

## Why this exists

**Access to information is a right.** Canadians shouldn't have to know which government website to dig through, or what a "Hansard" is, or which province publishes bills as PDFs and which as JSON, just to find out what their elected representatives have said and done.

This project takes that seriously. Three principles fall out of it:

1. **Free and frictionless for the public.** No accounts for basic search, no dark patterns. Postal-code lookup is the front door. Search is the next one.
2. **Source-available to the core.** Every ingester, every schema decision, every upstream quirk and blocker lives in this repo under [PolyForm Noncommercial 1.0.0](./LICENSE) — free for personal, research, educational, and other noncommercial use. Per-jurisdiction research dossiers under [`docs/research/`](docs/research/) document exactly how each legislature's data was sourced, what's reliable, and what's not.
3. **Honest about gaps.** Coverage holes are surfaced on the public [`/coverage`](https://canadianpoliticaldata.ca/coverage) dashboard rather than hidden.

The project is **not apolitical**. It's rooted in democratic values, civic transparency, and progressive stances on access to information. See [`docs/goals.md`](docs/goals.md) for the full framing and [`docs/timeline.md`](docs/timeline.md) for what's being built next.

---

## Where to go

| If you want to… | Go to |
|---|---|
| Look up your representatives | **[canadianpoliticaldata.ca](https://canadianpoliticaldata.ca)** |
| See current coverage and known gaps | **[/coverage](https://canadianpoliticaldata.ca/coverage)** |
| Read end-user / contributor docs and the blog | **[docs.canadianpoliticaldata.ca](https://docs.canadianpoliticaldata.ca/)** |
| **Build on top of the dataset programmatically** | **[/developers](https://docs.canadianpoliticaldata.ca/developers/)** |
| Download the full dataset (Postgres dump) | [/datasets/](https://canadianpoliticaldata.ca/datasets/) (anonymous) or [`/api/public/v1/exports/dumps`](https://docs.canadianpoliticaldata.ca/developers/bulk-export/) (authenticated) |
| Understand a specific jurisdiction's data sources | [`docs/research/`](docs/research/) |
| Run it locally | [Quick Start](#quick-start) below |

## Developer API

A bearer-token-authenticated public API surface lives at **`/api/public/v1/*`** with eleven endpoints across five tags:

- **Reference data** (any tier, any scope): `/coverage`, `/jurisdiction-sources`, `/politicians/:id`
- **Search auxiliaries** (any tier, any scope, no GPU): `/search/sessions`, `/search/chunks/:id`, `/search/meta`
- **Semantic search** (PRO tier only — TEI-embedded; shared concurrency semaphore): `/search/speeches`, `/search/speeches/count`, `/search/facets`
- **Bulk export** (`read:bulk` scope required, any tier): `/exports/dumps`, `/exports/dumps/:filename`

Three pricing tiers — Free (60 req/hr), Developer ($20/mo, 1,000 req/hr), Pro ($200/mo, 10,000 req/hr) — manageable at [`/account/billing`](https://canadianpoliticaldata.ca/account/billing). Subscriptions auto-promote all of a user's existing API keys to the new tier.

- **Get a key**: [`/account/api-keys`](https://canadianpoliticaldata.ca/account/api-keys)
- **Interactive reference**: [`/api/public/v1/docs/`](https://canadianpoliticaldata.ca/api/public/v1/docs/) (Swagger UI)
- **Developer guide**: [`docs.canadianpoliticaldata.ca/developers/`](https://docs.canadianpoliticaldata.ca/developers/)
- **Stability**: `/api/public/v1/*` is frozen as v1.0; field removals or renames require v2 with a 6-month deprecation notice. See `docs/api.md` § Stability & Versioning.

---

## Architecture

```
┌────────────┐    ┌─────────┐     ┌─────────────┐    ┌──────────────┐
│  Frontend  │◄──►│  nginx  │◄───►│  API        │◄──►│  PostgreSQL  │
│  React/TS  │    │  proxy  │     │  Fastify    │    │  + PostGIS   │
│  Leaflet   │    └─────────┘     │  Node 20    │    │  + pgvector  │
└────────────┘                    └─────┬───────┘    └──────┬───────┘
                                        │                   ▲
                ┌───────────────────────┴────┐              │
                │                            │              │
         ┌──────▼───────┐            ┌───────▼────────┐     │
         │   change     │            │    Scanner     │─────┤
         │  detection   │            │    Python      │     │
         │  (webhook)   │            │    asyncio     │     │
         └──────────────┘            └───────┬────────┘     │
                                             │ HTTP         │
                                     ┌───────▼────────────┐ │
                                     │  TEI               │ │
                                     │  Qwen3-Embedding-  │ │
                                     │  0.6B (GPU fp16)   │ │
                                     └────────────────────┘ │
                                                            │
                                     ┌─────────────────┐    │
                                     │ scanner-jobs    │────┘
                                     │ admin worker    │
                                     └─────────────────┘
```

Node 20 + Fastify API, React 18 + Vite frontend, Python 3.13 + asyncio scanner, Postgres 16 + PostGIS + pgvector, Hugging Face TEI serving Qwen3-Embedding-0.6B on a local GPU. Single-host Docker Compose, Pangolin tunnel to public.

Service-by-service detail in [`docs/architecture.md`](docs/architecture.md).

---

## Quick Start

```bash
# 1. Configure environment
cp .env.example .env
# edit .env — at minimum set DB_PASSWORD, WEBHOOK_SECRET, JWT_SECRET, and SMTP

# 2. Download GeoLite2 databases
# Create a free MaxMind account and place these files in ./data/
#   - GeoLite2-City.mmdb
#   - GeoLite2-ASN.mmdb

# 3. Build and start
make up

# 4. Seed referendum organizations (first time only)
make seed

# 5. Ingest politicians — pick your coverage
docker compose run --rm scanner ingest-mps            # Federal MPs
docker compose run --rm scanner ingest-senators       # Senators
docker compose run --rm scanner ingest-legislatures   # All provincial + territorial
docker compose run --rm scanner ingest-all-councils   # Municipal councils
docker compose run --rm scanner fill-gaps             # Legislatures Open North doesn't cover

# 6. Run a scan
make scan

# 7. Open the site
open http://localhost
```

The full CLI is `sovpro --help` (~95 subcommands across ingest, enrichment, Hansard, scan, and maintenance). Day-to-day ops in [`docs/operations.md`](docs/operations.md); the full ingestion playbook in [`docs/scanner.md`](docs/scanner.md).

---

## Audience and roadmap

The project serves two audiences in sequence:

- **Engaged citizens (free, public, forever).** Postal-code lookup, per-politician pages, the map, the change feed, and — soon — semantic search over Hansard. No account ever required.
- **Lobbyists, journalists, academics, advocacy orgs (paid API tiers, future).** Bulk export (CSV/Parquet), programmatic semantic search, scheduled topic alerts, "compare A vs. B" tooling. Funds the public side.

The public side stays free forever. See [`docs/goals.md`](docs/goals.md) for non-goals and [`docs/timeline.md`](docs/timeline.md) for what's being built next.

---

## Contributing

This is an in-the-open project, and contributions — especially research dossiers for the four remaining bills pipelines (MB, SK, PE, YT), Hansard pipelines for non-federal legislatures, and corrections to existing data — are welcome.

Before opening a PR for a new ingestion pipeline, please read the **research-handoff protocol** in [`docs/research/overview.md`](docs/research/overview.md). Short version: pause and document the upstream endpoints first; the time saved by skipping that step is almost always lost rebuilding the scraper.

Read [`CLAUDE.md`](CLAUDE.md) for project-level conventions (jurisdiction-specific ID columns, the probe hierarchy, persistent rate-limit caching, idempotent Click subcommands).

---

## License + attribution

[PolyForm Noncommercial 1.0.0](./LICENSE) — free for personal, research, educational, and other noncommercial use. Commercial use requires a separate licence; contact **[The Bunker Operations (BNKops)](https://bnkops.com/)** at [admin@thebunkerops.ca](mailto:admin@thebunkerops.ca).

This project uses data from:

- [Open North's Represent API](https://represent.opennorth.ca/) under the [Open Government License — Canada](https://open.canada.ca/en/open-government-licence-canada)
- [openparliament.ca](https://openparliament.ca) (federal MP profiles, speeches, and sponsored bills)
- [MaxMind GeoLite2 databases](https://www.maxmind.com/) (IP geolocation)
- Per-jurisdiction provincial sources documented in [`docs/data-sources.md`](docs/data-sources.md), each under its respective open-government licence (CC-BY-NC-4.0 for Quebec; OGL variants elsewhere; Crown copyright where no open licence is published)

Attribution to Open North, openparliament.ca, and MaxMind is preserved in the public-site footer. Don't remove it if you redistribute.
