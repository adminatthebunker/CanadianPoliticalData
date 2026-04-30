---
title: Local installation
description: Run the full Canadian Political Data stack on your own hardware via Docker Compose.
---

# Local installation

Running the full stack locally gets you the live API, the React
frontend, the Python ingestion scanner, the embedding service, and the
Postgres database — the same containers we run in production, on your
own hardware.

This is the right path if you're contributing to the codebase, running
a private mirror, or want fresh ingestion rather than the
[periodic dataset snapshot](data-download.md).

The codebase is **public on GitHub** at
[`adminatthebunker/CanadianPoliticalData`](https://github.com/adminatthebunker/CanadianPoliticalData)
— clone it, fork it, run it.

## Prerequisites

| Required | Why |
| --- | --- |
| **Docker Engine 24+** with Compose v2 | Everything runs in containers. No host-level Postgres / Node / Python install needed. |
| **8 GB RAM** minimum, 16 GB recommended | Postgres + the API + the frontend + the scanner all run simultaneously. |
| **20 GB free disk** | Container images, Postgres data volume, GeoIP databases. More if you're ingesting a lot of historical Hansard. |
| **macOS, Linux, or Windows + WSL2** | Tested on Linux; macOS works; Windows works under WSL2. |

| Optional | Why |
| --- | --- |
| **NVIDIA GPU + nvidia-container-toolkit** | The embedding service (TEI / Qwen3-Embedding-0.6B) is GPU-accelerated. CPU fallback works but ingestion is much slower. |
| **A MaxMind GeoLite2 account** (free) | Used by the infrastructure-scan layer to attribute IPs to countries. The scanner runs without it but skips the geo step. |
| **A SendGrid / Mailgun / Proton SMTP account** | For magic-link emails when developing the auth flow. The scanner runs without it; emails fall through to stdout in dev mode. |

## Quick start

```bash
# 1. Clone the repo.
git clone https://github.com/adminatthebunker/CanadianPoliticalData.git sovpro
cd sovpro

# 2. Copy the example env file and fill in the secrets.
cp .env.example .env
$EDITOR .env

# 3. Bring the stack up. First run takes a few minutes (image builds + db init).
docker compose up -d

# 4. Watch it come up.
docker compose ps
docker compose logs -f api
```

When `docker compose ps` shows everything `healthy` (or at least
`running`), open:

| URL | What it is |
| --- | --- |
| `http://localhost:8088/` | The frontend (via the same nginx as production) |
| `http://localhost:8088/api/v1/health` | API health check |
| `http://localhost:8088/admin/` | Admin panel (requires an admin user — see [Admin access](#admin-access)) |
| `http://localhost:8088/status/` | Uptime Kuma dashboard |

## Environment variables

The bare minimum to get a working stack is `DB_PASSWORD` and
`WEBHOOK_SECRET` — both can be any random strings. Everything else has
sensible defaults or feature-flags off cleanly when unset.

The full set of variables, what they enable, and their fail-closed
behaviour when unset is documented in `.env.example` itself. A few of
the more important ones:

`DB_PASSWORD`
:   **Required.** Postgres superuser password. Pick something random.

`JWT_SECRET`
:   Required to enable user sign-in. Generate with `openssl rand -hex 32`.
    Without it, `/api/v1/auth/*` returns 503.

`SMTP_HOST` / `SMTP_USERNAME` / `SMTP_PASSWORD`
:   Required to actually send magic-link emails. Without them, links
    are logged to stdout — fine for local dev.

`STRIPE_SECRET_KEY` / `STRIPE_WEBHOOK_SECRET`
:   Required to enable credit purchase flows. Without them, the
    purchase UI hides cleanly and `/webhooks/stripe` refuses every event.

`OPENROUTER_API_KEY`
:   Required for AI report generation. Without it, the "Generate
    report" UI is hidden.

`HTTP_PORT` / `HTTPS_PORT`
:   Override the host ports nginx binds. Defaults: `8088` / `8443`.

`DOCS_PREVIEW_PORT`
:   Override the host port the docs preview binds. Default: `8000`.

## Bootstrapping the dataset

A direct dataset snapshot is not yet published — see
[Dataset download](data-download.md) for the planned shape and ETA.
Until it's available, the recommended path is to **bootstrap your own
copy by running the same ingestion pipeline we run in production**.

The scanner is idempotent and restartable — every ingest command can be
re-run safely. You can scope to only the jurisdictions you care about,
and you don't have to backfill everything before the system becomes
useful.

### Phase 1 — minimum viable corpus (~30 minutes)

Bring the stack up and seed the structural data:

```bash
# Stack up.
sovpro up

# Seed organizations + the federal politician roster.
docker compose run --rm scanner python -m src seed-orgs
docker compose run --rm scanner python -m src ingest-mps

# Confirm rows landed.
sovpro db psql -c "SELECT COUNT(*) FROM politicians;"
```

At this point you have every current federal MP, party affiliation, and
riding — enough to render the politicians directory and the federal
slice of the map. No Hansard speeches yet.

### Phase 2 — federal Hansard (a few hours)

```bash
# Ingest current-session federal Hansard.
docker compose run --rm scanner python -m src ingest-federal-hansard

# The TEI embedding service runs continuously — new chunks get embedded
# automatically. You can watch progress:
docker compose logs -f tei
```

After this finishes you have a searchable federal Hansard corpus for
the current parliamentary session, with semantic embeddings ready for
similarity queries.

### Phase 3 — provincial rosters and Hansard (variable)

```bash
# Provincial member rosters.
docker compose run --rm scanner python -m src ingest-mlas

# Per-jurisdiction Hansard. Pick the provinces you care about; running
# all of them in parallel will saturate ingest concurrency.
docker compose run --rm scanner python -m src ingest-on-hansard
docker compose run --rm scanner python -m src ingest-bc-hansard
docker compose run --rm scanner python -m src ingest-ab-hansard
docker compose run --rm scanner python -m src ingest-qc-hansard
docker compose run --rm scanner python -m src ingest-ns-hansard
# ... etc.
```

The full per-jurisdiction command list lives in
`services/scanner/src/__main__.py` — grep for `ingest-` to enumerate.

### Phase 4 — let the schedules take over

Once you've backfilled the slice you care about, switch on the
production-style daily schedules so the system stays current without
manual prodding:

```bash
docker exec -i sw-db psql -U sw -d sovereignwatch \
  < scripts/seed-daily-ingest-schedules.sql
```

The `scanner-jobs` daemon picks up scheduled rows whose `next_run_at`
has elapsed, runs them, and advances the next-run timestamp. From here,
your local mirror tracks upstream automatically.

### Going faster

Most ingest commands take optional flags to scope the work — historical
sessions, specific date ranges, etc. Run any command with `--help` to
see the available knobs:

```bash
docker compose run --rm scanner python -m src ingest-federal-hansard --help
```

For continuously growing the corpus over time without re-downloading
everything, the daily-schedule approach in Phase 4 is what production
uses and what you should converge on.

## Admin access

The admin panel is gated by a `users.is_admin = true` flag, set by
direct SQL update. There is no self-promotion route by design.

```bash
# After signing in once via the magic-link flow at /login, promote yourself:
docker exec -it sw-db psql -U sw -d sovereignwatch \
  -c "UPDATE users SET is_admin = true WHERE email = 'you@example.com';"
```

The next request from your browser picks up the new flag — the check
re-reads from the database on every request, so no logout / login is
needed.

## Day-to-day operator commands

The repository includes a wrapper CLI at `cli/sovpro` that bundles the
common operations into short commands. Add it to your `PATH`:

```bash
export PATH="$PWD/cli:$PATH"

sovpro up                  # docker compose up -d --build
sovpro down                # docker compose down
sovpro ps                  # service status
sovpro logs api            # tail one service
sovpro db psql             # interactive psql as sw on sovereignwatch
sovpro db backup           # writes backups/<timestamp>.sql.gz
sovpro doctor              # sanity-check every service
sovpro stats               # quick row counts and sovereignty metrics
```

Ingestion shortcuts:

```bash
sovpro ingest all          # seed orgs + ingest the standard set of rosters
sovpro scan full           # re-scan all infrastructure, ignore staleness
sovpro scan                # re-scan stale records only
```

For one-off scanner subcommands not in the wrapper:

```bash
docker compose run --rm scanner python -m src <subcommand>
```

The full list of subcommands lives in
`services/scanner/src/__main__.py`.

## Updating the stack

```bash
# Pull the latest source.
git pull

# Rebuild and restart anything that changed.
docker compose up -d --build

# If you've pulled new database migrations, apply them in order:
ls db/migrations/*.sql | sort | xargs -I {} \
  docker exec -i sw-db psql -U sw -d sovereignwatch -v ON_ERROR_STOP=1 -f {}
```

Migrations are forward-only — once applied, they're never edited or
rolled back. If you've already applied an earlier migration the re-run
is a no-op (each migration is idempotent at the SQL level).

## Stopping cleanly

```bash
# Stop everything but keep the data volume.
docker compose down

# Stop AND wipe the database. Destructive — only do this when you mean it.
docker compose down -v
```

The data volume (`pgdata`) and asset volume survive across restarts.
The `-v` flag removes them.

## Troubleshooting

??? note "GPU not detected by the embedding service"

    Check the runtime is installed:

    ```bash
    docker info | grep -i nvidia
    docker run --rm --gpus all nvidia/cuda:12-base-ubuntu22.04 nvidia-smi
    ```

    If the second command fails, install
    [`nvidia-container-toolkit`](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)
    and restart Docker.

??? note "Port 8088 / 8443 already in use"

    Set `HTTP_PORT` and `HTTPS_PORT` in your `.env` to free ports
    before bringing the stack up.

??? note "Magic-link emails aren't arriving"

    Without SMTP configured, magic links are logged to the API
    container's stdout instead of being sent. Check:

    ```bash
    docker compose logs api | grep -i "magic link"
    ```

    Copy the URL from the log and paste it into your browser. This is
    the intended local-dev fallback.

??? note "Scanner errors on first run"

    Most "no such table" errors mean migrations haven't run yet. The
    `db` container's init scripts apply the base schema on first boot
    only — for any migration added later, see the
    [Updating the stack](#updating-the-stack) section above.

??? note "I broke my database and want to start over"

    ```bash
    docker compose down -v        # wipes volumes
    docker compose up -d db       # fresh init scripts run
    ```

    Then [bootstrap the dataset again](#bootstrapping-the-dataset).
