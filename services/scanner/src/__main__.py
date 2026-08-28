"""CLI entry point for the scanner service.

Usage:
    python -m src --help
    python -m src ingest-mps
    python -m src ingest-mlas
    python -m src ingest-councils
    python -m src backfill-terms
    python -m src seed-orgs
    python -m src scan [--limit N] [--stale-hours N]
    python -m src refresh-views
    python -m src stats
    python -m src normalize-socials
    python -m src verify-socials [--limit N] [--stale-hours N]
"""
from __future__ import annotations

import asyncio
import os
import sys
from typing import Optional

import click
from rich.console import Console
from rich.table import Table

from .committees import (
    ingest_ab_committees,
    ingest_all_committees,
    ingest_federal_committees,
)
from .compare_politicians import backfill_initial_terms
from .db import Database, get_dsn
from .legislative._forward import forward_options as _forward_options
from .enrich import (
    enrich_alberta_mlas,
    enrich_all_legislatures,
    enrich_bc_mlas,
    enrich_federal_mps,
    enrich_manitoba_mlas,
    enrich_new_brunswick_mlas,
    enrich_nl_mhas,
    enrich_nova_scotia_mlas,
    enrich_nunavut_mlas,
    enrich_nwt_mlas,
    enrich_ontario_mpps,
    enrich_pei_mlas,
    enrich_quebec_mnas,
    enrich_saskatchewan_mlas,
    enrich_yukon_mlas,
)
from .opennorth import (
    ingest_alberta_extras,
    ingest_all_councils,
    ingest_all_legislatures,
    ingest_bc_mlas,
    ingest_councils,
    ingest_manitoba_mlas,
    ingest_mlas,
    ingest_mps,
    ingest_new_brunswick_mlas,
    ingest_nl_mhas,
    ingest_nova_scotia_mlas,
    ingest_nunavut_mlas,
    ingest_nwt_mlas,
    ingest_ontario_mpps,
    ingest_pei_mlas,
    ingest_quebec_mnas,
    ingest_saskatchewan_mlas,
    ingest_yukon_mlas,
)
from .scanner import scan_all
from .seed_orgs import seed_organizations
from .socials import bulk_import_socials, normalize_socials, verify_liveness
from .socials_audit import audit_socials
from .socials_probe import PLATFORMS_SUPPORTED, probe_missing_socials
from .socials_agent import (
    DEFAULT_BATCH_SIZE as AGENT_DEFAULT_BATCH_SIZE,
    DEFAULT_MODEL as AGENT_DEFAULT_MODEL,
    agent_find_socials,
)
from .websites_agent import (
    DEFAULT_BATCH_SIZE as WEBSITES_AGENT_DEFAULT_BATCH_SIZE,
    DEFAULT_MODEL as WEBSITES_AGENT_DEFAULT_MODEL,
    agent_find_websites,
)
from .resolve_openparliament import resolve_slugs
from .socials_enrichment import (
    enrich_all_socials,
    enrich_from_openparl,
    enrich_from_wikidata,
    enrich_mastodon_candidates,
)
from .stats import print_stats

console = Console()


@click.group()
@click.option("--database-url", envvar="DATABASE_URL", default=None, help="Postgres DSN")
@click.pass_context
def cli(ctx: click.Context, database_url: Optional[str]) -> None:
    """Canadian Political Data scanner — ingest, scan, and classify political websites."""
    ctx.ensure_object(dict)
    ctx.obj["dsn"] = database_url or get_dsn()


@cli.command("ingest-mps")
@click.option("--limit", type=int, default=500)
@click.pass_context
def cmd_ingest_mps(ctx: click.Context, limit: int) -> None:
    """Fetch federal MPs from Open North."""
    asyncio.run(_run(ingest_mps, ctx.obj["dsn"], limit=limit))


@cli.command("ingest-mlas")
@click.option("--limit", type=int, default=100)
@click.pass_context
def cmd_ingest_mlas(ctx: click.Context, limit: int) -> None:
    """Fetch Alberta MLAs from Open North."""
    asyncio.run(_run(ingest_mlas, ctx.obj["dsn"], limit=limit))


@cli.command("ingest-councils")
@click.pass_context
def cmd_ingest_councils(ctx: click.Context) -> None:
    """Fetch Edmonton + Calgary councils from Open North."""
    asyncio.run(_run(ingest_councils, ctx.obj["dsn"]))


@cli.command("ingest-ab-extras")
@click.pass_context
def cmd_ingest_ab_extras(ctx: click.Context) -> None:
    """Fetch additional Alberta municipal councils (Strathcona, Wood Buffalo, Lethbridge, Grande Prairie)."""
    asyncio.run(_run(ingest_alberta_extras, ctx.obj["dsn"]))


# ─────────────────────────────────────────────────────────────────────
# Provincial / territorial legislature ingestion (Phase 2)
# ─────────────────────────────────────────────────────────────────────


@cli.command("ingest-legislatures")
@click.option("--limit", type=int, default=200,
              help="Max reps to fetch per legislature (default 200 — larger than any province).")
@click.pass_context
def cmd_ingest_legislatures(ctx: click.Context, limit: int) -> None:
    """Fetch MLAs/MPPs/MNAs/MHAs for every province + territory."""
    asyncio.run(_run(ingest_all_legislatures, ctx.obj["dsn"], limit=limit))


@cli.command("ingest-bc-mlas")
@click.option("--limit", type=int, default=200)
@click.pass_context
def cmd_ingest_bc_mlas(ctx: click.Context, limit: int) -> None:
    """Fetch British Columbia MLAs from Open North."""
    asyncio.run(_run(ingest_bc_mlas, ctx.obj["dsn"], limit=limit))


@cli.command("ingest-ontario-mpps")
@click.option("--limit", type=int, default=200)
@click.pass_context
def cmd_ingest_ontario_mpps(ctx: click.Context, limit: int) -> None:
    """Fetch Ontario MPPs from Open North."""
    asyncio.run(_run(ingest_ontario_mpps, ctx.obj["dsn"], limit=limit))


@cli.command("ingest-quebec-mnas")
@click.option("--limit", type=int, default=200)
@click.pass_context
def cmd_ingest_quebec_mnas(ctx: click.Context, limit: int) -> None:
    """Fetch Québec MNAs (Assemblée nationale) from Open North."""
    asyncio.run(_run(ingest_quebec_mnas, ctx.obj["dsn"], limit=limit))


@cli.command("ingest-manitoba-mlas")
@click.option("--limit", type=int, default=200)
@click.pass_context
def cmd_ingest_manitoba_mlas(ctx: click.Context, limit: int) -> None:
    """Fetch Manitoba MLAs from Open North."""
    asyncio.run(_run(ingest_manitoba_mlas, ctx.obj["dsn"], limit=limit))


@cli.command("ingest-saskatchewan-mlas")
@click.option("--limit", type=int, default=200)
@click.pass_context
def cmd_ingest_saskatchewan_mlas(ctx: click.Context, limit: int) -> None:
    """Fetch Saskatchewan MLAs from Open North."""
    asyncio.run(_run(ingest_saskatchewan_mlas, ctx.obj["dsn"], limit=limit))


@cli.command("ingest-nova-scotia-mlas")
@click.option("--limit", type=int, default=200)
@click.pass_context
def cmd_ingest_nova_scotia_mlas(ctx: click.Context, limit: int) -> None:
    """Fetch Nova Scotia MLAs from Open North."""
    asyncio.run(_run(ingest_nova_scotia_mlas, ctx.obj["dsn"], limit=limit))


@cli.command("ingest-new-brunswick-mlas")
@click.option("--limit", type=int, default=200)
@click.pass_context
def cmd_ingest_new_brunswick_mlas(ctx: click.Context, limit: int) -> None:
    """Fetch New Brunswick MLAs from Open North."""
    asyncio.run(_run(ingest_new_brunswick_mlas, ctx.obj["dsn"], limit=limit))


@cli.command("ingest-pei-mlas")
@click.option("--limit", type=int, default=200)
@click.pass_context
def cmd_ingest_pei_mlas(ctx: click.Context, limit: int) -> None:
    """Fetch Prince Edward Island MLAs from Open North."""
    asyncio.run(_run(ingest_pei_mlas, ctx.obj["dsn"], limit=limit))


@cli.command("ingest-nl-mhas")
@click.option("--limit", type=int, default=200)
@click.pass_context
def cmd_ingest_nl_mhas(ctx: click.Context, limit: int) -> None:
    """Fetch Newfoundland & Labrador MHAs from Open North."""
    asyncio.run(_run(ingest_nl_mhas, ctx.obj["dsn"], limit=limit))


@cli.command("ingest-yukon-mlas")
@click.option("--limit", type=int, default=200)
@click.pass_context
def cmd_ingest_yukon_mlas(ctx: click.Context, limit: int) -> None:
    """Fetch Yukon MLAs from Open North."""
    asyncio.run(_run(ingest_yukon_mlas, ctx.obj["dsn"], limit=limit))


@cli.command("ingest-nwt-mlas")
@click.option("--limit", type=int, default=200)
@click.pass_context
def cmd_ingest_nwt_mlas(ctx: click.Context, limit: int) -> None:
    """Fetch Northwest Territories MLAs from Open North."""
    asyncio.run(_run(ingest_nwt_mlas, ctx.obj["dsn"], limit=limit))


@cli.command("ingest-nunavut-mlas")
@click.option("--limit", type=int, default=200)
@click.pass_context
def cmd_ingest_nunavut_mlas(ctx: click.Context, limit: int) -> None:
    """Fetch Nunavut MLAs (currently 0 rows — see opennorth.py TODO)."""
    asyncio.run(_run(ingest_nunavut_mlas, ctx.obj["dsn"], limit=limit))


# ─────────────────────────────────────────────────────────────────────
# Municipal ingestion (Phase 4)
# ─────────────────────────────────────────────────────────────────────


@cli.command("ingest-all-councils")
@click.option("--limit", "limit_per_set", type=int, default=200,
              help="Max councillors to ingest per municipal set")
@click.pass_context
def cmd_ingest_all_councils(ctx: click.Context, limit_per_set: int) -> None:
    """Fetch every municipal council Open North indexes (Phase 4)."""
    asyncio.run(_run(ingest_all_councils, ctx.obj["dsn"],
                     limit_per_set=limit_per_set))


@cli.command("seed-orgs")
@click.pass_context
def cmd_seed_orgs(ctx: click.Context) -> None:
    """Seed referendum organizations (idempotent)."""
    asyncio.run(_run(seed_organizations, ctx.obj["dsn"]))


@cli.command("backfill-terms")
@click.pass_context
def cmd_backfill_terms(ctx: click.Context) -> None:
    """One-time: open an initial politician_terms row for every active
    politician without an existing open term."""
    async def _wrap(db: Database) -> None:
        stats = await backfill_initial_terms(db)
        console.print(
            f"[green]backfill-terms[/green]: inserted={stats['inserted']} "
            f"skipped={stats['skipped']} candidates={stats['candidates']}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("enrich-mps")
@click.option("--limit", type=int, default=None)
@click.option("--force", is_flag=True, help="Re-discover even if personal_url is set")
@click.pass_context
def cmd_enrich_mps(ctx: click.Context, limit, force) -> None:
    """Discover personal/campaign websites for federal MPs (via ourcommons.ca)."""
    asyncio.run(_run(enrich_federal_mps, ctx.obj["dsn"], limit=limit, force=force))


@cli.command("enrich-mlas")
@click.option("--limit", type=int, default=None)
@click.pass_context
def cmd_enrich_mlas(ctx: click.Context, limit) -> None:
    """Discover personal websites for Alberta MLAs (via assembly.ab.ca)."""
    asyncio.run(_run(enrich_alberta_mlas, ctx.obj["dsn"], limit=limit))


# ─────────────────────────────────────────────────────────────────────
# Per-legislature enrichment (Phase 3)
# ─────────────────────────────────────────────────────────────────────


@cli.command("enrich-legislatures")
@click.option("--limit", type=int, default=None,
              help="Max rows per province (default: all without personal_url).")
@click.pass_context
def cmd_enrich_legislatures(ctx: click.Context, limit) -> None:
    """Run every provincial/territorial enricher in sequence."""
    asyncio.run(_run(enrich_all_legislatures, ctx.obj["dsn"], limit=limit))


@cli.command("enrich-bc-mlas")
@click.option("--limit", type=int, default=None)
@click.pass_context
def cmd_enrich_bc_mlas(ctx: click.Context, limit) -> None:
    """Discover personal sites for BC MLAs (via leg.bc.ca)."""
    asyncio.run(_run(enrich_bc_mlas, ctx.obj["dsn"], limit=limit))


@cli.command("enrich-ontario-mpps")
@click.option("--limit", type=int, default=None)
@click.pass_context
def cmd_enrich_ontario_mpps(ctx: click.Context, limit) -> None:
    """Discover personal sites for Ontario MPPs (via ola.org)."""
    asyncio.run(_run(enrich_ontario_mpps, ctx.obj["dsn"], limit=limit))


@cli.command("enrich-quebec-mnas")
@click.option("--limit", type=int, default=None)
@click.pass_context
def cmd_enrich_quebec_mnas(ctx: click.Context, limit) -> None:
    """Discover personal sites for Québec MNAs (via assnat.qc.ca)."""
    asyncio.run(_run(enrich_quebec_mnas, ctx.obj["dsn"], limit=limit))


@cli.command("enrich-manitoba-mlas")
@click.option("--limit", type=int, default=None)
@click.pass_context
def cmd_enrich_manitoba_mlas(ctx: click.Context, limit) -> None:
    """Discover personal sites for Manitoba MLAs (via gov.mb.ca/legislature)."""
    asyncio.run(_run(enrich_manitoba_mlas, ctx.obj["dsn"], limit=limit))


@cli.command("enrich-saskatchewan-mlas")
@click.option("--limit", type=int, default=None)
@click.pass_context
def cmd_enrich_saskatchewan_mlas(ctx: click.Context, limit) -> None:
    """Discover personal sites for Saskatchewan MLAs (via legassembly.sk.ca)."""
    asyncio.run(_run(enrich_saskatchewan_mlas, ctx.obj["dsn"], limit=limit))


@cli.command("enrich-nova-scotia-mlas")
@click.option("--limit", type=int, default=None)
@click.pass_context
def cmd_enrich_nova_scotia_mlas(ctx: click.Context, limit) -> None:
    """Discover personal sites for Nova Scotia MLAs (via nslegislature.ca)."""
    asyncio.run(_run(enrich_nova_scotia_mlas, ctx.obj["dsn"], limit=limit))


@cli.command("enrich-new-brunswick-mlas")
@click.option("--limit", type=int, default=None)
@click.pass_context
def cmd_enrich_new_brunswick_mlas(ctx: click.Context, limit) -> None:
    """Discover personal sites for NB MLAs (via legnb.ca)."""
    asyncio.run(_run(enrich_new_brunswick_mlas, ctx.obj["dsn"], limit=limit))


@cli.command("enrich-pei-mlas")
@click.option("--limit", type=int, default=None)
@click.pass_context
def cmd_enrich_pei_mlas(ctx: click.Context, limit) -> None:
    """Discover personal sites for PEI MLAs (via assembly.pe.ca)."""
    asyncio.run(_run(enrich_pei_mlas, ctx.obj["dsn"], limit=limit))


@cli.command("enrich-nl-mhas")
@click.option("--limit", type=int, default=None)
@click.pass_context
def cmd_enrich_nl_mhas(ctx: click.Context, limit) -> None:
    """Discover personal sites for NL MHAs (via assembly.nl.ca)."""
    asyncio.run(_run(enrich_nl_mhas, ctx.obj["dsn"], limit=limit))


@cli.command("enrich-yukon-mlas")
@click.option("--limit", type=int, default=None)
@click.pass_context
def cmd_enrich_yukon_mlas(ctx: click.Context, limit) -> None:
    """Discover personal sites for Yukon MLAs (via yukonassembly.ca)."""
    asyncio.run(_run(enrich_yukon_mlas, ctx.obj["dsn"], limit=limit))


@cli.command("enrich-nwt-mlas")
@click.option("--limit", type=int, default=None)
@click.pass_context
def cmd_enrich_nwt_mlas(ctx: click.Context, limit) -> None:
    """Discover personal sites for NWT MLAs (via ntlegislativeassembly.ca)."""
    asyncio.run(_run(enrich_nwt_mlas, ctx.obj["dsn"], limit=limit))


@cli.command("enrich-nunavut-mlas")
@click.pass_context
def cmd_enrich_nunavut_mlas(ctx: click.Context) -> None:
    """Stub — Nunavut has no ingested politicians yet (see opennorth.py TODO)."""
    asyncio.run(_run(enrich_nunavut_mlas, ctx.obj["dsn"]))


# ─────────────────────────────────────────────────────────────────────
# Socials (Phase 5)
# ─────────────────────────────────────────────────────────────────────


@cli.command("normalize-socials")
@click.pass_context
def cmd_normalize_socials(ctx: click.Context) -> None:
    """Explode politicians.social_urls JSONB into politician_socials rows."""
    asyncio.run(_run(normalize_socials, ctx.obj["dsn"]))


@cli.command("audit-socials")
@click.option("--csv", "csv_path", default=None,
              help="Where to write the missing-rows CSV (default $POLITICIAN_SOCIALS_AUDIT_CSV or /tmp/politician_socials_audit.csv)")
@click.option("--no-csv", is_flag=True, help="Skip CSV export; just print tables")
@click.pass_context
def cmd_audit_socials(ctx: click.Context, csv_path, no_csv) -> None:
    """Snapshot social coverage and refresh v_socials_missing view."""
    asyncio.run(_run(audit_socials, ctx.obj["dsn"],
                     csv_path=csv_path, no_csv=no_csv))


@cli.command("probe-missing-socials")
@click.option("--platform", type=click.Choice(list(PLATFORMS_SUPPORTED)),
              default="bluesky",
              help="Which missing platform to probe (default: bluesky)")
@click.option("--limit", type=int, default=500,
              help="Max v_socials_missing rows to process this run")
@click.option("--dry-run", is_flag=True,
              help="Print would-be inserts without writing")
@click.pass_context
def cmd_probe_missing_socials(ctx: click.Context, platform: str,
                              limit: int, dry_run: bool) -> None:
    """Tier-2: pattern-probe URL candidates and upsert scored hits."""
    asyncio.run(_run(probe_missing_socials, ctx.obj["dsn"],
                     platform=platform, limit=limit, dry_run=dry_run))


@cli.command("agent-missing-socials")
@click.option("--platform", type=str, default=None,
              help="Focus on a single platform (e.g. twitter). Default: all missing platforms per politician.")
@click.option("--batch-size", type=int, default=AGENT_DEFAULT_BATCH_SIZE,
              help="Politicians per agent call (capped at 25)")
@click.option("--max-batches", type=int, default=20,
              help="Hard cap on agent calls per invocation")
@click.option("--model", type=str, default=AGENT_DEFAULT_MODEL)
@click.option("--dry-run", is_flag=True,
              help="Print candidate hits without inserting")
@click.pass_context
def cmd_agent_missing_socials(ctx: click.Context, platform, batch_size,
                              max_batches, model, dry_run) -> None:
    """Tier-3: Sonnet agent + web_search for residual missing socials."""
    asyncio.run(_run(agent_find_socials, ctx.obj["dsn"],
                     platform=platform, batch_size=batch_size,
                     max_batches=max_batches, model=model,
                     dry_run=dry_run))


@cli.command("agent-missing-websites")
@click.option("--batch-size", type=int, default=WEBSITES_AGENT_DEFAULT_BATCH_SIZE,
              help="Politicians per agent call (capped at 25)")
@click.option("--max-batches", type=int, default=20,
              help="Hard cap on agent calls per invocation")
@click.option("--model", type=str, default=WEBSITES_AGENT_DEFAULT_MODEL)
@click.option("--dry-run", is_flag=True,
              help="Print candidate hits without inserting")
@click.pass_context
def cmd_agent_missing_websites(ctx: click.Context, batch_size, max_batches,
                               model, dry_run) -> None:
    """Tier-3: Sonnet agent + web_search for politician personal/party websites.

    Search budget is hard-capped at 3 per politician via the web_search
    tool's `max_uses` parameter. Per-batch cap = 3 × batch_size.
    """
    asyncio.run(_run(agent_find_websites, ctx.obj["dsn"],
                     batch_size=batch_size, max_batches=max_batches,
                     model=model, dry_run=dry_run))


@cli.command("verify-socials")
@click.option("--limit", type=int, default=500, help="Max rows to verify per run")
@click.option("--stale-hours", type=int, default=168,
              help="Re-verify rows whose last_verified_at is older than this")
@click.pass_context
def cmd_verify_socials(ctx: click.Context, limit: int, stale_hours: int) -> None:
    """Issue liveness checks against each politician_socials URL."""
    asyncio.run(_run(verify_liveness, ctx.obj["dsn"],
                     limit=limit, stale_hours=stale_hours))


@cli.command("bulk-import-socials")
@click.option("--input", "input_path", required=True,
              help="Path to JSONL (one {politician_id, urls:[...]} per line)")
@click.pass_context
def cmd_bulk_import_socials(ctx: click.Context, input_path: str) -> None:
    """Import agent-discovered social URLs via the canonical upserter."""
    asyncio.run(_run(bulk_import_socials, ctx.obj["dsn"], input_path=input_path))


@cli.command("scan")
@click.option("--limit", type=int, default=None, help="Max websites to scan")
@click.option("--stale-hours", type=int, default=24,
              help="Skip sites scanned within this many hours (0 = scan all)")
@click.option("--concurrency", type=int, default=None, help="Override SCANNER_CONCURRENCY")
@click.option("--only", type=click.Choice(["politician", "organization"]), default=None)
@click.pass_context
def cmd_scan(ctx: click.Context, limit, stale_hours, concurrency, only) -> None:
    """Scan websites (DNS, GeoIP, TLS, HTTP)."""
    asyncio.run(_run(scan_all, ctx.obj["dsn"],
                     limit=limit, stale_hours=stale_hours,
                     concurrency=concurrency, owner_type=only))


@cli.command("backfill-politician-photos")
@click.option("--limit", type=int, default=None,
              help="Cap the number of politicians processed this run.")
@click.option("--stale-days", type=int, default=30,
              help="Re-fetch photos whose last fetch is older than N days.")
@click.option("--politician-id", type=str, default=None,
              help="Process a single politician by UUID (overrides limit/stale filters).")
@click.option("--concurrency", type=int, default=4,
              help="Parallel fetches. Per-host rate limiting still applies.")
@click.pass_context
def cmd_backfill_photos(
    ctx: click.Context,
    limit: Optional[int],
    stale_days: int,
    politician_id: Optional[str],
    concurrency: int,
) -> None:
    """Mirror upstream politician portraits onto the local `assets` volume.

    Writes to /assets/politicians/<uuid>.<ext> and updates politicians.photo_path
    + photo_bytes_hash + photo_fetched_at + photo_source_url. The original
    photo_url is left untouched for attribution and re-fetch.
    """
    from .photos import backfill_politician_photos

    async def _wrap(db: Database) -> None:
        stats = await backfill_politician_photos(
            db,
            limit=limit,
            stale_days=stale_days,
            politician_id=politician_id,
            concurrency=concurrency,
        )
        console.print(f"[green]backfill-politician-photos[/green]: {stats.summary()}")
        for sample in stats.fail_samples:
            console.print(f"  [yellow]fail[/yellow] {sample}")

    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("refresh-views")
@click.pass_context
def cmd_refresh(ctx: click.Context) -> None:
    """Refresh map materialized views."""
    async def _run_refresh(dsn: str) -> None:
        db = Database(dsn)
        await db.connect()
        try:
            await db.pool.execute("SELECT refresh_map_views();")
            console.print("[green]Materialized views refreshed[/green]")
        finally:
            await db.close()

    asyncio.run(_run_refresh(ctx.obj["dsn"]))


@cli.command("stats")
@click.pass_context
def cmd_stats(ctx: click.Context) -> None:
    """Print sovereignty summary."""
    asyncio.run(_stats(ctx.obj["dsn"]))


async def _run(func, dsn: str, **kwargs) -> None:
    db = Database(dsn)
    await db.connect()
    try:
        await func(db, **kwargs)
    finally:
        await db.close()


async def _stats(dsn: str) -> None:
    db = Database(dsn)
    await db.connect()
    try:
        await print_stats(db, console)
    finally:
        await db.close()


# ─────────────────────────────────────────────────────────────────────
# Committee ingestion (Team C)
# ─────────────────────────────────────────────────────────────────────


@cli.command("ingest-committees-federal")
@click.pass_context
def cmd_ingest_committees_federal(ctx: click.Context) -> None:
    """Scrape parl.ca / ourcommons.ca committee members into politician_committees."""
    asyncio.run(_run(ingest_federal_committees, ctx.obj["dsn"]))


@cli.command("ingest-committees-ab")
@click.pass_context
def cmd_ingest_committees_ab(ctx: click.Context) -> None:
    """Scrape assembly.ab.ca committee membership into politician_committees."""
    asyncio.run(_run(ingest_ab_committees, ctx.obj["dsn"]))


@cli.command("ingest-committees-all")
@click.pass_context
def cmd_ingest_committees_all(ctx: click.Context) -> None:
    """Run every available committee ingester (federal + implemented provinces)."""
    asyncio.run(_run(ingest_all_committees, ctx.obj["dsn"]))


# ─────────────────────────────────────────────────────────────────────
# Socials enrichment from external sources (Team B)
# ─────────────────────────────────────────────────────────────────────


@cli.command("enrich-socials-wikidata")
@click.option("--level", type=click.Choice(["federal", "provincial"]),
              default=None, help="Restrict to one level; default covers all.")
@click.option("--include-inactive", is_flag=True,
              help="Also enrich is_active=false politicians (historical roster).")
@click.pass_context
def cmd_enrich_socials_wikidata(ctx: click.Context, level, include_inactive) -> None:
    """Pull handles for Canadian legislators via Wikidata SPARQL."""
    async def _wrap(db: Database) -> None:
        n = await enrich_from_wikidata(
            db, level=level, include_inactive=include_inactive
        )
        console.print(f"[green]wikidata enrichment inserted {n} rows[/green]")
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("enrich-socials-openparl")
@click.option("--include-inactive", is_flag=True,
              help="Also enrich former federal MPs (historical roster).")
@click.pass_context
def cmd_enrich_socials_openparl(ctx: click.Context, include_inactive) -> None:
    """Backfill federal-MP handles from openparliament.ca detail pages."""
    async def _wrap(db: Database) -> None:
        n = await enrich_from_openparl(db, include_inactive=include_inactive)
        console.print(f"[green]openparl enrichment inserted {n} rows[/green]")
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("resolve-openparliament-slugs")
@click.pass_context
def cmd_resolve_openparliament_slugs(ctx: click.Context) -> None:
    """Match our federal MPs to their openparliament.ca URL slugs.

    Populates politicians.openparliament_slug via name-matching against
    openparliament.ca's public list. Re-entrant: skips MPs that already
    have a slug. Run after each federal ingest to pick up by-election
    winners.
    """
    async def _wrap(db: Database) -> None:
        await resolve_slugs(db)
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("enrich-socials-mastodon")
@click.option("--include-inactive", is_flag=True,
              help="Also match against is_active=false politicians.")
@click.pass_context
def cmd_enrich_socials_mastodon(ctx: click.Context, include_inactive) -> None:
    """Walk canada.masto.host directory and match politicians by display name."""
    async def _wrap(db: Database) -> None:
        n = await enrich_mastodon_candidates(db, include_inactive=include_inactive)
        console.print(f"[green]mastodon enrichment inserted {n} rows[/green]")
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("enrich-socials-all")
@click.option("--include-inactive", is_flag=True,
              help="Run all three enrichers against the full politicians table "
                   "(active + inactive); useful for historical-roster backfill.")
@click.pass_context
def cmd_enrich_socials_all(ctx: click.Context, include_inactive) -> None:
    """Run wikidata → openparl → mastodon enrichers in order."""
    async def _wrap(db: Database) -> None:
        await enrich_all_socials(db, include_inactive=include_inactive)
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


# ─────────────────────────────────────────────────────────────────────
# Municipal enrichment (Team D)
# ─────────────────────────────────────────────────────────────────────


@cli.command("enrich-municipal")
@click.option("--limit", type=int, default=None,
              help="Max councillors to enrich (default: all without personal_url).")
@click.option("--concurrency", type=int, default=6,
              help="Max parallel HTTP connections across hosts.")
@click.pass_context
def cmd_enrich_municipal(ctx: click.Context, limit, concurrency: int) -> None:
    """Discover per-councillor personal/campaign sites across 108 councils.

    Covers every municipal politician ingested via Open North (Phase 4).
    Uses a handful of CMS-specific scrapers for the large platforms
    (Drupal-Ottawa, WordPress-Mississauga) plus a name-aware generic scorer
    that works against any municipal site. Respects robots.txt per host.
    """
    from .muni_enrich import enrich_municipal
    asyncio.run(_run(enrich_municipal, ctx.obj["dsn"],
                     limit=limit, concurrency=concurrency))


# ─────────────────────────────────────────────────────────────────────
# Gap fillers (Team A — web-research-driven)
# ─────────────────────────────────────────────────────────────────────
# Direct scrapers for legislatures Open North either doesn't cover
# (Nunavut) or leaves with unusable data (NB/NL empty url field,
# BC mostly-missing roster, Yukon Cloudflare-blocked). Each command is
# a thin wrapper around the corresponding gap_fillers submodule.
from .legislative.ns_bills import ingest_ns_bills  # noqa: E402
from .legislative.ns_bill_pages import fetch_ns_bill_pages  # noqa: E402
from .legislative.ns_bill_parse import parse_ns_bill_pages  # noqa: E402
from .legislative.on_bills import (  # noqa: E402
    discover_ola_bills, fetch_ola_bill_pages, parse_ola_bill_pages,
)
from .legislative.sponsor_resolver import resolve_sponsors  # noqa: E402
from .legislative.bc_bills import (  # noqa: E402
    enrich_bc_member_ids, ingest_bc_bills,
)
from .legislative.ns_rss import ingest_ns_rss  # noqa: E402
from .legislative.ns_mlas import ingest as ingest_ns_mlas  # noqa: E402
from .legislative.ns_hansard import (  # noqa: E402
    ingest as ingest_ns_hansard,
    resolve_ns_speakers as resolve_ns_hansard_speakers,
)
from .legislative.qc_mnas import enrich_qc_mna_ids  # noqa: E402
from .legislative.qc_bills import (  # noqa: E402
    fetch_qc_bill_sponsors, ingest_qc_bills_csv, ingest_qc_bills_rss,
)
from .legislative.ab_mlas import enrich_ab_mla_ids  # noqa: E402
from .legislative.ab_former_mlas import (  # noqa: E402
    ingest_ab_former_mlas, resolve_ab_speakers, enrich_ab_mlas,
)
from .legislative.ab_presiding_merge import merge_ab_presiding_stubs  # noqa: E402
from .legislative.ab_bills import ingest_ab_bills  # noqa: E402
from .legislative.mb_mlas import ingest as ingest_mb_mlas  # noqa: E402
from .legislative.mb_former_mlas import ingest_mb_former_mlas  # noqa: E402
from .legislative.on_former_mpps import ingest_on_former_mpps  # noqa: E402
from .legislative.qc_former_mnas import ingest_qc_former_mnas  # noqa: E402
from .legislative.bc_member_parliaments import enrich_bc_member_parliaments  # noqa: E402
from .legislative.mb_bills import ingest as ingest_mb_bills  # noqa: E402
from .legislative.mb_billstatus import (  # noqa: E402
    fetch as fetch_mb_billstatus,
    parse_events as parse_mb_bill_events,
)
from .legislative.mb_bill_sponsors import resolve as resolve_mb_bill_sponsors  # noqa: E402
from .legislative.mb_hansard import (  # noqa: E402
    ingest as ingest_mb_hansard,
    resolve_mb_speakers as resolve_mb_hansard_speakers,
    resolve_mb_speakers_dated as resolve_mb_hansard_speakers_dated,
)
from .legislative.nb_bills import ingest_nb_bills  # noqa: E402
from .legislative.nb_hansard import (  # noqa: E402
    ingest as ingest_nb_hansard,
    ingest_all_sessions_in_legislature as ingest_nb_hansard_all_sessions,
    resolve_nb_speakers as resolve_nb_hansard_speakers,
)
from .legislative.nl_bills import ingest_nl_bills  # noqa: E402
from .legislative.nl_hansard import (  # noqa: E402
    ingest as ingest_nl_hansard,
    resolve_nl_speakers as resolve_nl_hansard_speakers,
)
from .legislative.nt_bills import ingest_nt_bills  # noqa: E402
from .legislative.nu_bills import ingest_nu_bills  # noqa: E402
from .gap_fillers import bc as _gf_bc  # noqa: E402
from .gap_fillers import nb as _gf_nb  # noqa: E402
from .gap_fillers import nl as _gf_nl  # noqa: E402
from .gap_fillers import nunavut as _gf_nunavut  # noqa: E402
from .gap_fillers import ontario as _gf_ontario  # noqa: E402
from .gap_fillers import yukon as _gf_yukon  # noqa: E402
from .gap_fillers.runner import run_all as _gf_run_all  # noqa: E402


@cli.command("fill-gaps")
@click.pass_context
def cmd_fill_gaps(ctx: click.Context) -> None:
    """Run every gap-filler (NU/YT/NB/NL/BC/ON) in sequence."""
    asyncio.run(_run(_gf_run_all, ctx.obj["dsn"]))


@cli.command("fill-nunavut")
@click.pass_context
def cmd_fill_nunavut(ctx: click.Context) -> None:
    """Scrape assembly.nu.ca for the 22 Nunavut MLAs (consensus government)."""
    asyncio.run(_run(_gf_nunavut.run, ctx.obj["dsn"]))


@cli.command("fill-yukon")
@click.pass_context
def cmd_fill_yukon(ctx: click.Context) -> None:
    """Bootstrap Yukon (21 MLAs) from Wikipedia — yukonassembly.ca is Cloudflare-blocked."""
    asyncio.run(_run(_gf_yukon.run, ctx.obj["dsn"]))


@cli.command("fill-nb")
@click.pass_context
def cmd_fill_nb(ctx: click.Context) -> None:
    """Scrape legnb.ca for the 49 NB MLA roster (Open North returns empty URLs)."""
    asyncio.run(_run(_gf_nb.run, ctx.obj["dsn"]))


@cli.command("fill-nl")
@click.pass_context
def cmd_fill_nl(ctx: click.Context) -> None:
    """Scrape assembly.nl.ca for the 40 NL MHA roster (Open North returns empty URLs)."""
    asyncio.run(_run(_gf_nl.run, ctx.obj["dsn"]))


@cli.command("fill-bc")
@click.pass_context
def cmd_fill_bc(ctx: click.Context) -> None:
    """Seed BC (93 MLAs) from Wikipedia + leg.bc.ca email table (Open North has only 5)."""
    asyncio.run(_run(_gf_bc.run, ctx.obj["dsn"]))


@cli.command("fill-ontario")
@click.pass_context
def cmd_fill_ontario(ctx: click.Context) -> None:
    """Fill Ontario MPP personal URLs + socials via OLP caucus / Wikipedia / Wikidata / DNS-probe."""
    async def _wrap(db: Database) -> None:
        stats = await _gf_ontario.fill_ontario(db)
        console.print(
            f"[green]fill-ontario summary[/green]: "
            f"personal_urls={stats['personal_urls']} "
            f"socials={stats['socials']} "
            f"unmatched={stats['unmatched']}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


# ─────────────────────────────────────────────────────────────────────
# Provincial legislative activity — bills (Nova Scotia first)
# ─────────────────────────────────────────────────────────────────────


@cli.command("ingest-ns-bills")
@click.option("--limit", type=int, default=None,
              help="Cap total records (for smoke tests). Default: all ~3.5k bills.")
@click.pass_context
def cmd_ingest_ns_bills(ctx: click.Context, limit) -> None:
    """Ingest Nova Scotia bills from the Socrata dataset iz5x-dzyf.

    Populates legislative_sessions, bills, and bill_events. Sponsor
    resolution is a separate pass — Socrata does not expose sponsor names.
    """
    async def _wrap(db: Database) -> None:
        stats = await ingest_ns_bills(db, limit=limit)
        console.print(
            f"[green]ingest-ns-bills[/green]: "
            f"bills={stats['bills']} events={stats['events']} "
            f"sessions={stats['sessions']} skipped={stats['skipped']}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("fetch-ns-bill-pages")
@click.option("--limit", type=int, default=None,
              help="Max bills to fetch this run (default: all pending).")
@click.option("--force", is_flag=True,
              help="Re-fetch even bills whose HTML is already cached.")
@click.option("--delay", "delay_secs", type=float, default=4.0,
              help="Minimum delay between requests (seconds). Default 4.0.")
@click.option("--jitter", "jitter_secs", type=float, default=2.0,
              help="Additional 0..jitter seconds random delay. Default 2.0.")
@click.pass_context
def cmd_fetch_ns_bill_pages(ctx: click.Context, limit, force, delay_secs, jitter_secs) -> None:
    """Fetch + cache nslegislature.ca HTML for every bill (phase 2).

    Idempotent: skips bills with raw_html already populated unless --force.
    At 4–6 sec per request, a full 3,500-bill backlog takes ~4–6 hours.
    Halts on WAF fingerprint detection so progress isn't wasted fighting
    a live block.
    """
    async def _wrap(db: Database) -> None:
        stats = await fetch_ns_bill_pages(
            db, limit=limit, force=force,
            delay_secs=delay_secs, jitter_secs=jitter_secs,
        )
        flag = " [yellow](WAF-aborted)[/yellow]" if stats["waf_aborted"] else ""
        console.print(
            f"[green]fetch-ns-bill-pages[/green]{flag}: "
            f"ok={stats['ok']} err={stats['err']} total={stats['total']}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("discover-on-bills")
@click.option("--parliament", type=int, default=None,
              help="Explicit parliament. Omit (with --session omitted) to "
                   "auto-resolve the current session and probe for "
                   "successors after a prorogation/election.")
@click.option("--session", type=int, default=None)
@click.option("--all-sessions", is_flag=True,
              help="Walk every ON session in legislative_sessions. "
                   "Overrides --parliament/--session.")
@click.pass_context
def cmd_discover_on_bills(
    ctx: click.Context, parliament, session, all_sessions: bool,
) -> None:
    """Enumerate Ontario bills from ola.org session index (phase 1).

    With no flags: DB-latest session + successor probe (self-healing
    across prorogations). With --all-sessions, walks every (parliament,
    session) pair already in legislative_sessions for ON. Idempotent on
    source_id; subsequent runs only pick up newly-listed bills.
    """
    from .legislative.on_bills import (
        discover_ola_bills_all_sessions,
        discover_ola_bills_current,
    )

    if (parliament is None) != (session is None):
        raise click.UsageError("--parliament and --session must be given together")

    async def _wrap(db: Database) -> None:
        if all_sessions:
            stats = await discover_ola_bills_all_sessions(db)
            console.print(
                f"[green]discover-on-bills[/green] (all sessions): "
                f"sessions={stats['sessions_touched']} "
                f"bills={stats['bills']}"
            )
        elif parliament is None:
            stats = await discover_ola_bills_current(db)
            console.print(
                f"auto-resolved current ON session: "
                f"P{stats['parliament']}-S{stats['session']}"
            )
            console.print(
                f"[green]discover-on-bills[/green] "
                f"P{stats['parliament']}-S{stats['session']}: "
                f"bills={stats['bills']} "
                f"successor_bills={stats['successor_bills']}"
            )
        else:
            stats = await discover_ola_bills(
                db, parliament=parliament, session=session,
            )
            console.print(
                f"[green]discover-on-bills[/green] P{parliament}-S{session}: "
                f"bills={stats['bills']}"
            )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("fetch-on-bill-pages")
@click.option("--limit", type=int, default=None)
@click.option("--force", is_flag=True)
@click.option("--delay", "delay_secs", type=float, default=1.5)
@click.option("--jitter", "jitter_secs", type=float, default=1.0)
@click.pass_context
def cmd_fetch_on_bill_pages(ctx: click.Context, limit, force, delay_secs, jitter_secs) -> None:
    """Fetch + cache ola.org bill page + /status sub-page (phase 2)."""
    async def _wrap(db: Database) -> None:
        stats = await fetch_ola_bill_pages(
            db, limit=limit, force=force,
            delay_secs=delay_secs, jitter_secs=jitter_secs,
        )
        flag = " [yellow](WAF-aborted)[/yellow]" if stats["waf_aborted"] else ""
        console.print(
            f"[green]fetch-on-bill-pages[/green]{flag}: "
            f"main={stats['main_ok']} status={stats['status_ok']} "
            f"err={stats['err']} total={stats['total']}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("parse-on-bill-pages")
@click.option("--limit", type=int, default=None)
@click.pass_context
def cmd_parse_on_bill_pages(ctx: click.Context, limit) -> None:
    """Parse cached ola.org HTML into sponsors + events (phase 3).

    Also derives bills.introduced_date from the earliest first_reading
    event scraped from the /status sub-page table.
    """
    async def _wrap(db: Database) -> None:
        stats = await parse_ola_bill_pages(db, limit=limit)
        console.print(
            f"[green]parse-on-bill-pages[/green]: "
            f"bills={stats['bills']} sponsors={stats['sponsors']} "
            f"events={stats['events']} titled={stats['titled']} "
            f"dated={stats['dated']} no_sponsor={stats['no_sponsor']}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("ingest-ns-bills-rss")
@click.pass_context
def cmd_ingest_ns_bills_rss(ctx: click.Context) -> None:
    """Refresh current-session NS bills from the public RSS feed.

    One request — no WAF budget impact. Adds richer status text +
    commencement metadata for current-session bills that already
    exist in the DB (via Socrata). Idempotent and safe to schedule.
    """
    async def _wrap(db: Database) -> None:
        stats = await ingest_ns_rss(db)
        console.print(
            f"[green]ingest-ns-bills-rss[/green]: "
            f"items={stats['items']} matched={stats['matched']} "
            f"updated={stats['updated']} events_added={stats['events_added']} "
            f"unmatched={stats['unmatched']}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("ingest-ns-mlas")
@click.option("--parliament", type=int, default=65,
              help="Assembly number whose Hansard we scrape for slugs (default 65 = current).")
@click.option("--session", type=int, default=1,
              help="Session within the assembly (default 1).")
@click.option("--sample-sittings", type=int, default=5,
              help="How many sittings from the top of the session index to scan (newer=more coverage).")
@click.pass_context
def cmd_ingest_ns_mlas(
    ctx: click.Context, parliament: int, session: int, sample_sittings: int,
) -> None:
    """Stamp politicians.nslegislature_slug for seated NS MLAs.

    NS Hansard anchors every speaker to /members/profiles/<slug> but
    only the ~10 bill-sponsors we've managed to fetch past the WAF
    have slugs today. This command harvests (slug, displayed_name)
    pairs from the newest sittings of the given session, name-matches
    them to existing NS politicians, and stamps the slug — prereq
    for ingest-ns-hansard speaker resolution. Idempotent.
    """
    async def _wrap(db: Database) -> None:
        stats = await ingest_ns_mlas(
            db,
            parliament=parliament,
            session=session,
            sample_sittings=sample_sittings,
        )
        console.print(
            f"[green]ingest-ns-mlas[/green]: "
            f"sittings={stats.sittings_scanned} harvested={stats.slugs_harvested} "
            f"stamped={stats.stamped} already={stats.already_correct} "
            f"conflict={stats.conflict} no_match={stats.no_match} "
            f"ambiguous={stats.ambiguous}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("ingest-ns-hansard")
@click.option("--parliament", type=int, default=None,
              help="NS assembly number. Default: latest in legislative_sessions.")
@click.option("--session", type=int, default=None,
              help="Session within the assembly. Default: latest.")
@click.option("--since", type=str, default=None,
              help="Only ingest sittings on/after this ISO date (YYYY-MM-DD).")
@click.option("--since-days", type=int, default=None,
              help="Forward-incremental: clamp --since to today - N days "
                   "(use in daily schedules).")
@click.option("--until", type=str, default=None,
              help="Only ingest sittings on/before this ISO date (YYYY-MM-DD).")
@click.option("--limit-sittings", type=int, default=None,
              help="Cap on sittings processed (newest-first when capped).")
@click.option("--limit-speeches", type=int, default=None,
              help="Cap on TOTAL speeches ingested. Smoke-test friendly.")
@click.option("--url", "one_off_url", type=str, default=None,
              help="Bypass discovery and ingest a single sitting URL directly.")
@click.pass_context
def cmd_ingest_ns_hansard(
    ctx: click.Context, parliament, session,
    since: Optional[str], since_days: Optional[int], until: Optional[str],
    limit_sittings: Optional[int], limit_speeches: Optional[int],
    one_off_url: Optional[str],
) -> None:
    """Ingest Nova Scotia Hansard (HTML transcripts) → `speeches` table.

    When --parliament/--session are omitted, resolves the current session
    from legislative_sessions (populated by ingest-ns-bills).
    """
    from .legislative.current_session import current_session
    from .legislative._forward import parse_iso_date, clamp_since_with_days

    effective_since = clamp_since_with_days(parse_iso_date(since), since_days)

    async def _wrap(db: Database) -> None:
        nonlocal parliament, session
        if (parliament is None or session is None) and one_off_url is None:
            parliament, session = await current_session(
                db, level="provincial", province_territory="NS",
            )
            console.print(
                f"[dim]auto-resolved current NS session: "
                f"P{parliament}-S{session}[/dim]"
            )
        if since_days is not None and effective_since is not None:
            console.print(
                f"[dim]forward-incremental: --since clamped to "
                f"{effective_since.isoformat()} (since_days={since_days})[/dim]"
            )
        stats = await ingest_ns_hansard(
            db,
            parliament=parliament,
            session=session,
            since=effective_since,
            until=parse_iso_date(until),
            limit_sittings=limit_sittings,
            limit_speeches=limit_speeches,
            one_off_url=one_off_url,
        )
        console.print(
            f"[green]ingest-ns-hansard[/green]: "
            f"sittings={stats.sittings_scanned} seen={stats.speeches_seen} "
            f"inserted={stats.speeches_inserted} updated={stats.speeches_updated} "
            f"skipped_empty={stats.skipped_empty} parse_errors={stats.parse_errors} "
            f"resolved={stats.speeches_resolved} role={stats.speeches_role_only} "
            f"slug_unknown={stats.speeches_slug_unknown} "
            f"ambiguous={stats.speeches_ambiguous} unresolved={stats.speeches_unresolved}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("resolve-ns-speakers")
@click.option("--limit", type=int, default=None,
              help="Cap speeches scanned (smoke-test aid).")
@click.pass_context
def cmd_resolve_ns_speakers(ctx: click.Context, limit: Optional[int]) -> None:
    """Re-resolve politician_id on NS Hansard speeches with NULL politician_id.

    Run after ingest-ns-mlas stamps new slugs, or after fixing a
    parser edge case. Idempotent.
    """
    async def _wrap(db: Database) -> None:
        stats = await resolve_ns_hansard_speakers(db, limit=limit)
        console.print(
            f"[green]resolve-ns-speakers[/green]: "
            f"scanned={stats.speeches_scanned} updated={stats.speeches_updated} "
            f"still_unresolved={stats.still_unresolved}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("ingest-on-hansard")
@click.option("--parliament", type=int, default=None,
              help="Ontario Parliament number (e.g. 44). Default: latest in legislative_sessions.")
@click.option("--session", type=int, default=None,
              help="Session within the parliament (e.g. 1). Default: latest.")
@click.option("--since", type=str, default=None,
              help="Only ingest sittings on/after this ISO date (YYYY-MM-DD).")
@click.option("--since-days", type=int, default=None,
              help="Forward-incremental: clamp --since to today - N days "
                   "(use in daily schedules).")
@click.option("--until", type=str, default=None,
              help="Only ingest sittings on/before this ISO date (YYYY-MM-DD).")
@click.option("--limit-sittings", type=int, default=None,
              help="Cap on sittings processed (newest-first when capped).")
@click.option("--limit-speeches", type=int, default=None,
              help="Cap on TOTAL speeches ingested. Smoke-test friendly.")
@click.option("--url", "one_off_url", type=str, default=None,
              help="Bypass discovery and ingest a single sitting URL directly.")
@click.pass_context
def cmd_ingest_on_hansard(
    ctx: click.Context, parliament, session, since, since_days, until,
    limit_sittings, limit_speeches, one_off_url,
) -> None:
    """Ingest Ontario Hansard (HTML transcripts via ola.org JSON node) → speeches.

    Discovery: walk the session HTML at /house-documents/parliament-{P}/session-{S}/.
    Per-sitting fetch uses ?_format=json which carries the body HTML in
    `body.value` plus structured field_date / field_associated_bill_multi.

    Speaker resolution is name-based against the ON politicians roster
    (no per-speaker slug anchors in ON markup). Bare-role turns ("The
    Speaker" without inline parens) defer to
    `resolve-presiding-speakers --province ON`.

    When --parliament/--session are omitted, resolves the current
    session from legislative_sessions (populated by ingest-on-bills).
    """
    from .legislative.on_hansard import ingest as _ingest
    from .legislative.current_session import current_session
    from .legislative._forward import parse_iso_date, clamp_since_with_days

    effective_since = clamp_since_with_days(parse_iso_date(since), since_days)

    async def _wrap(db: Database) -> None:
        nonlocal parliament, session
        if (parliament is None or session is None) and one_off_url is None:
            parliament, session = await current_session(
                db, level="provincial", province_territory="ON",
            )
            console.print(
                f"[dim]auto-resolved current ON session: "
                f"P{parliament}-S{session}[/dim]"
            )
        # When one_off_url is set, parliament/session are still needed for
        # legislative_sessions upsert. Default to the current session DB
        # value if not supplied.
        if (parliament is None or session is None) and one_off_url is not None:
            parliament, session = await current_session(
                db, level="provincial", province_territory="ON",
            )
        if since_days is not None and effective_since is not None:
            console.print(
                f"[dim]forward-incremental: --since clamped to "
                f"{effective_since.isoformat()} (since_days={since_days})[/dim]"
            )
        stats = await _ingest(
            db,
            parliament=parliament,
            session=session,
            since=effective_since,
            until=parse_iso_date(until),
            limit_sittings=limit_sittings,
            limit_speeches=limit_speeches,
            one_off_url=one_off_url,
        )
        console.print(
            f"[green]ingest-on-hansard[/green]: "
            f"sittings={stats.sittings_scanned} seen={stats.speeches_seen} "
            f"inserted={stats.speeches_inserted} updated={stats.speeches_updated} "
            f"skipped_empty={stats.skipped_empty} parse_errors={stats.parse_errors} "
            f"resolved={stats.speeches_resolved} role={stats.speeches_role_only} "
            f"ambiguous={stats.speeches_ambiguous} unresolved={stats.speeches_unresolved}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("resolve-on-speakers")
@click.option("--limit", type=int, default=None,
              help="Cap speeches scanned (smoke-test aid).")
@click.pass_context
def cmd_resolve_on_speakers(ctx: click.Context, limit: Optional[int]) -> None:
    """Re-resolve politician_id on ON Hansard speeches with NULL politician_id.

    Run after expanding the ON MPP roster (e.g. after ingest-ontario-mpps)
    to pick up speeches whose name now resolves. Idempotent.
    """
    from .legislative.on_hansard import resolve_on_speakers as _resolve

    async def _wrap(db: Database) -> None:
        stats = await _resolve(db, limit=limit)
        console.print(
            f"[green]resolve-on-speakers[/green]: "
            f"scanned={stats.speeches_scanned} updated={stats.speeches_updated} "
            f"still_unresolved={stats.still_unresolved}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("enrich-bc-member-ids")
@click.pass_context
def cmd_enrich_bc_member_ids(ctx: click.Context) -> None:
    """Populate politicians.lims_member_id via LIMS GraphQL allMembers.

    Name-matches active BC provincial politicians against the LIMS
    member roster. Run before ingest-bc-bills so sponsor resolution
    becomes an exact integer FK lookup.
    """
    async def _wrap(db: Database) -> None:
        stats = await enrich_bc_member_ids(db)
        console.print(
            f"[green]enrich-bc-member-ids[/green]: "
            f"scanned={stats['politicians_scanned']} "
            f"linked={stats['linked']} ambiguous={stats['ambiguous']}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("ingest-bc-bills")
@click.option("--all-sessions", is_flag=True,
              help="Backfill every historical BC session (default: current only).")
@click.option("--parliament", type=int, default=None)
@click.option("--session", type=int, default=None)
@click.pass_context
def cmd_ingest_bc_bills(ctx: click.Context, all_sessions, parliament, session) -> None:
    """Ingest BC bills from LIMS PDMS.

    Default: current session only. Use --all-sessions for full history,
    or --parliament/--session for a single specific session.
    """
    async def _wrap(db: Database) -> None:
        stats = await ingest_bc_bills(
            db,
            current_only=not all_sessions and parliament is None,
            parliament=parliament, session=session,
        )
        console.print(
            f"[green]ingest-bc-bills[/green]: "
            f"sessions={stats['sessions_touched']} bills={stats['bills']} "
            f"events={stats['events']} sponsors={stats['sponsors']} "
            f"sponsors_linked={stats['sponsors_linked']}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("resolve-bill-sponsors")
@click.option("--limit", type=int, default=None)
@click.pass_context
def cmd_resolve_bill_sponsors(ctx: click.Context, limit) -> None:
    """Link bill_sponsors → politicians via slug join + name match.

    Pure offline. Re-entrant: only touches rows with politician_id NULL.
    As it links by name, it backfills politicians.<source>_slug so
    subsequent runs short-circuit to the slug index.
    """
    async def _wrap(db: Database) -> None:
        stats = await resolve_sponsors(db, limit=limit)
        console.print(
            f"[green]resolve-bill-sponsors[/green]: "
            f"scanned={stats['scanned']} by_slug={stats['linked_by_slug']} "
            f"by_name={stats['linked_by_name']} "
            f"slugs_backfilled={stats['slugs_backfilled']} "
            f"unmatched={stats['unmatched']}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("enrich-qc-mna-ids")
@click.pass_context
def cmd_enrich_qc_mna_ids(ctx: click.Context) -> None:
    """Populate politicians.qc_assnat_id by scraping the MNA index page.

    Numeric MNA ids are embedded in the profile-URL slug. Run before
    fetch-qc-bill-sponsors so bill sponsor resolution becomes an exact
    integer FK lookup — no name-fuzz, no ambiguity.
    """
    async def _wrap(db: Database) -> None:
        stats = await enrich_qc_mna_ids(db)
        console.print(
            f"[green]enrich-qc-mna-ids[/green]: "
            f"scanned={stats['politicians_scanned']} "
            f"linked={stats['linked']} ambiguous={stats['ambiguous']}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("ingest-qc-bills")
@click.option("--all-sessions", is_flag=True,
              help="Ingest every session in the CSV (default: current only).")
@click.pass_context
def cmd_ingest_qc_bills(ctx: click.Context, all_sessions) -> None:
    """Ingest Quebec bills from the donneesquebec.ca CSV export.

    Authoritative daily snapshot — one HTTP GET for the whole roster.
    Emits one bill_events row per bill (the last stage reached). Run
    ingest-qc-bills-rss after this to fill in the full stage timeline.
    """
    async def _wrap(db: Database) -> None:
        stats = await ingest_qc_bills_csv(db, current_only=not all_sessions)
        console.print(
            f"[green]ingest-qc-bills[/green]: "
            f"rows={stats['rows']} sessions={stats['sessions_touched']} "
            f"bills={stats['bills']} events={stats['events']}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("discover-qc-bills-html")
@click.option("--parliament", type=int, default=None,
              help="Legislature number. Required unless --all-sessions.")
@click.option("--session", type=int, default=None,
              help="Session number within the legislature.")
@click.option("--all-sessions", is_flag=True,
              help="Walk every QC session in legislative_sessions.")
@click.pass_context
def cmd_discover_qc_bills_html(
    ctx: click.Context, parliament, session, all_sessions: bool,
) -> None:
    """Discover historical QC bills via assnat.qc.ca session index pages.

    Complements ingest-qc-bills (donneesquebec CSV, current+previous
    only) by reaching pre-current sessions. One HTTP GET per session
    index page; minimal stub rows (title placeholder, no sponsor).
    Run fetch-qc-bill-sponsors afterward to enrich the new stubs.

    Idempotent on source_id.
    """
    from .legislative.qc_bills import (
        discover_qc_bills_html, discover_qc_bills_html_all_sessions,
    )

    async def _wrap(db: Database) -> None:
        if all_sessions:
            stats = await discover_qc_bills_html_all_sessions(db)
            console.print(
                f"[green]discover-qc-bills-html[/green] (all sessions): "
                f"sessions={stats['sessions_touched']} bills={stats['bills']}"
            )
            return
        if parliament is None or session is None:
            console.print(
                "[red]error[/red]: --parliament and --session are required "
                "unless --all-sessions is set"
            )
            return
        stats = await discover_qc_bills_html(
            db, parliament=parliament, session=session,
        )
        console.print(
            f"[green]discover-qc-bills-html[/green] P{parliament}-S{session}: "
            f"bills={stats['bills']}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("ingest-qc-bills-rss")
@click.pass_context
def cmd_ingest_qc_bills_rss(ctx: click.Context) -> None:
    """Refresh current-session QC stage events from the public RSS feed.

    One request — every stage transition on every current-session bill.
    Idempotent (bill_events_uniq). Safe to schedule daily. Final step
    rolls up bill_events 'introduced' rows into bills.introduced_date.
    """
    async def _wrap(db: Database) -> None:
        stats = await ingest_qc_bills_rss(db)
        console.print(
            f"[green]ingest-qc-bills-rss[/green]: "
            f"items={stats['items']} matched={stats['matched']} "
            f"events_added={stats['events_added']} "
            f"unmatched={stats['unmatched']} dated={stats['dated']}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("fetch-qc-bill-introduced-dates")
@click.option("--limit", type=int, default=None,
              help="Cap bills scanned this run (default: every undated bill).")
@click.option("--delay", type=float, default=1.5,
              help="Delay between HTTP requests (seconds).")
@click.pass_context
def cmd_fetch_qc_bill_introduced_dates(
    ctx: click.Context, limit, delay,
) -> None:
    """Fetch QC bill detail pages and write introduced_date events.

    Sibling of fetch-qc-bill-sponsors. Iterates every QC bill where
    `introduced_date IS NULL`, GETs the detail page, extracts the
    `<h3>Introduction</h3> Sitting held on <date>` token, and inserts
    a `bill_events` first_reading row. Calls derive-qc-introduced-dates
    at the end to roll the events up onto bills.introduced_date in a
    single SQL pass.

    ~1,019 candidates × 1.5s = ~25 min on first backfill. Steady-state
    runs touch only newly-discovered undated bills (seconds).
    """
    from .legislative.qc_bills import fetch_qc_bill_introduced_dates

    async def _wrap(db: Database) -> None:
        stats = await fetch_qc_bill_introduced_dates(
            db, limit=limit, delay_seconds=delay,
        )
        console.print(
            f"[green]fetch-qc-bill-introduced-dates[/green]: "
            f"scanned={stats['scanned']} fetched={stats['pages_fetched']} "
            f"events_inserted={stats['events_inserted']} "
            f"rolled_up={stats['rolled_up']} "
            f"no_date={stats['no_date_found']} "
            f"not_found={stats['not_found']} errors={stats['errors']}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("fetch-qc-bill-sponsors")
@click.option("--limit", type=int, default=None,
              help="Cap bills scanned this run (default: every un-sponsored bill).")
@click.option("--delay", type=float, default=2.0,
              help="Delay between HTTP requests (seconds).")
@click.pass_context
def cmd_fetch_qc_bill_sponsors(ctx: click.Context, limit, delay) -> None:
    """Fetch QC bill detail pages and link sponsors by MNA numeric id.

    ~150 bills/session; 2s default delay = ~5 min to complete. Direct
    FK lookup via politicians.qc_assnat_id, so any bill whose sponsor
    is a current sitting MNA resolves cleanly. Skips bills that already
    have a sponsor row — safe to re-run.
    """
    async def _wrap(db: Database) -> None:
        stats = await fetch_qc_bill_sponsors(db, limit=limit, delay_seconds=delay)
        console.print(
            f"[green]fetch-qc-bill-sponsors[/green]: "
            f"scanned={stats['scanned']} fetched={stats['pages_fetched']} "
            f"sponsors={stats['sponsors']} linked={stats['sponsors_linked']} "
            f"no_sponsor={stats['no_sponsor_found']} "
            f"not_found={stats['not_found']} errors={stats['errors']}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("enrich-ab-mla-ids")
@click.pass_context
def cmd_enrich_ab_mla_ids(ctx: click.Context) -> None:
    """Populate politicians.ab_assembly_mid by scraping the MLAs index page.

    Zero-padded 4-char mids are embedded in profile-URL query strings.
    Run before ingest-ab-bills so sponsor resolution is an exact FK
    lookup — no name-fuzz.
    """
    async def _wrap(db: Database) -> None:
        stats = await enrich_ab_mla_ids(db)
        console.print(
            f"[green]enrich-ab-mla-ids[/green]: "
            f"scanned={stats['politicians_scanned']} "
            f"linked={stats['linked']} ambiguous={stats['ambiguous']}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("ingest-ab-former-mlas")
@click.option("--from-legl", type=int, default=1,
              help="Earliest legislature to enumerate (default: 1 = 1906).")
@click.option("--until-legl", type=int, default=31,
              help="Latest legislature to enumerate (default: 31 = current).")
@click.option("--delay", type=float, default=1.0,
              help="Seconds between page fetches (be polite).")
@click.pass_context
def cmd_ingest_ab_former_mlas(
    ctx: click.Context, from_legl: int, until_legl: int, delay: float,
) -> None:
    """Enumerate every MLA who's ever served in the AB Legislature.

    Scrapes assembly.ab.ca/members/...?legl=N for N in [--from-legl,
    --until-legl], upserts politicians keyed on ab_assembly_mid, and
    creates politician_terms rows per (politician, legislature) using
    the year ranges advertised on each index page.

    Full-history default (1..31) takes ~35 seconds at --delay=1.0 and
    yields ~800-900 unique politicians covering 1906-present. Safe to
    re-run: politicians are upserted on ab_assembly_mid, terms on
    (politician_id, office, started_at).

    Prereq for resolver date-awareness — without term date ranges,
    historical speeches can't be date-filtered against the right
    contemporaneous roster.
    """
    async def _wrap(db: Database) -> None:
        stats = await ingest_ab_former_mlas(
            db, from_legl=from_legl, until_legl=until_legl, delay=delay,
        )
        console.print(
            f"[green]ingest-ab-former-mlas[/green]: "
            f"legls={stats.legls_scanned} "
            f"mid_legl_pairs={stats.mid_legl_pairs_seen} "
            f"politicians_inserted={stats.politicians_inserted} "
            f"politicians_updated={stats.politicians_updated} "
            f"terms_inserted={stats.terms_inserted} "
            f"terms_skipped={stats.terms_skipped} "
            f"missing_legl_dates={stats.missing_legl_dates}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))



@cli.command("ingest-nl-former-mlas")
@click.pass_context
def cmd_ingest_nl_former_mlas(ctx: click.Context) -> None:
    """Seed NL historical-MLA roster (50th General Assembly, 2021-2025).

    Mirror of ingest-nb-former-mlas / ingest-ns-former-mlas. Hand-
    curated Python literal sourced from Wikipedia. Required for Pass 4
    surname resolution on NL Hansard 2022-2025 — the existing NL
    current-roster ingester only knows the sitting 51st GA.
    """
    from .legislative.nl_former_mlas import ingest_nl_former_mlas

    async def _wrap(db: Database) -> None:
        stats = await ingest_nl_former_mlas(db)
        console.print(
            f"[green]ingest-nl-former-mlas[/green]: "
            f"legislatures={stats.legislatures_processed} "
            f"unique_mlas={stats.unique_mlas} "
            f"inserted={stats.politicians_inserted} "
            f"matched={stats.politicians_matched_existing} "
            f"terms_inserted={stats.terms_inserted} "
            f"terms_skipped={stats.terms_skipped_existing}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("ingest-nu-former-mlas")
@click.pass_context
def cmd_ingest_nu_former_mlas(ctx: click.Context) -> None:
    """Seed NU 6th Assembly historical roster (2021-2025) from Wikipedia.

    22 MLAs sourced from the `6th_Nunavut_Legislature` Wikipedia article.
    Required for surname resolution on NU Hansard PDFs (2021-02-24 to
    2024-05-31) — the existing direct-scraper only knows the 7th
    Assembly that was sworn in Nov 2025. Fuzzier name match tolerates
    multi-word surnames (`Pitsiulaaq Brewster` ⊇ `Brewster`).
    """
    from .legislative.nu_former_mlas import ingest_nu_former_mlas

    async def _wrap(db: Database) -> None:
        stats = await ingest_nu_former_mlas(db)
        console.print(
            f"[green]ingest-nu-former-mlas[/green]: "
            f"legislatures={stats.legislatures_processed} "
            f"unique_mlas={stats.unique_mlas} "
            f"inserted={stats.politicians_inserted} "
            f"matched={stats.politicians_matched_existing} "
            f"terms_inserted={stats.terms_inserted} "
            f"terms_skipped={stats.terms_skipped_existing}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("ingest-ns-former-mlas")
@click.pass_context
def cmd_ingest_ns_former_mlas(ctx: click.Context) -> None:
    """Seed NS historical-MLA roster (62nd-64th General Assemblies, 2013-2024).

    Mirror of ingest-nb-former-mlas. Hand-curated Python literal sourced
    from per-Assembly Wikipedia articles. Required for Pass 4 surname
    resolution on pre-2024 NS Hansard — the existing ingest-ns-mlas
    only covers the sitting 65th General Assembly.
    """
    from .legislative.ns_former_mlas import ingest_ns_former_mlas

    async def _wrap(db: Database) -> None:
        stats = await ingest_ns_former_mlas(db)
        console.print(
            f"[green]ingest-ns-former-mlas[/green]: "
            f"legislatures={stats.legislatures_processed} "
            f"unique_mlas={stats.unique_mlas} "
            f"inserted={stats.politicians_inserted} "
            f"matched={stats.politicians_matched_existing} "
            f"terms_inserted={stats.terms_inserted} "
            f"terms_skipped={stats.terms_skipped_existing}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("ingest-nb-former-mlas")
@click.pass_context
def cmd_ingest_nb_former_mlas(ctx: click.Context) -> None:
    """Seed NB historical-MLA roster (58th-60th Legislatures, 2014-2024).

    NB doesn't publish a machine-readable former-members directory and
    legnb.ca's `/en/members/former-members` URL 404s. This command
    inserts a hand-curated roster sourced from Wikipedia per-Legislature
    articles. Idempotent: re-runs UPSERT politicians and skip-existing
    terms by (politician_id, started_at, source).

    Required for Pass 4 surname-only resolution to fire on NB Hansard
    pre-2024 — without per-Legislature term windows on the historical
    politicians, date-window narrowing returns no candidates.
    """
    from .legislative.nb_former_mlas import ingest_nb_former_mlas

    async def _wrap(db: Database) -> None:
        stats = await ingest_nb_former_mlas(db)
        console.print(
            f"[green]ingest-nb-former-mlas[/green]: "
            f"legislatures={stats.legislatures_processed} "
            f"unique_mlas={stats.unique_mlas} "
            f"inserted={stats.politicians_inserted} "
            f"matched={stats.politicians_matched_existing} "
            f"terms_inserted={stats.terms_inserted} "
            f"terms_skipped={stats.terms_skipped_existing}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("ingest-mb-former-mlas")
@click.option("--living/--no-living", default=True,
              help="Include the living-MLAs bio page.")
@click.option("--deceased/--no-deceased", default=True,
              help="Include the deceased-MLAs bio page.")
@click.option("--delay", type=float, default=1.0,
              help="Seconds between page fetches.")
@click.pass_context
def cmd_ingest_mb_former_mlas(
    ctx: click.Context, living: bool, deceased: bool, delay: float,
) -> None:
    """Enumerate every MLA who's ever served in the MB Legislature.

    Scrapes gov.mb.ca/legislature/members/mla_bio_{living,deceased}.html,
    which together list ~800+ MLAs back to 1870 with their term
    ranges. Name-matches against existing politicians first so
    current-roster rows (slug='byram', etc.) receive their
    historical terms rather than spawning duplicates; net-new
    historical rows land keyed on 'lastname-firstname' slugs.

    Idempotent: politicians upserted on mb_assembly_slug (migration
    0032 UNIQUE partial); politician_terms upserted on
    (politician_id, office, started_at).
    """
    async def _wrap(db: Database) -> None:
        stats = await ingest_mb_former_mlas(
            db, include_living=living, include_deceased=deceased, delay=delay,
        )
        console.print(
            f"[green]ingest-mb-former-mlas[/green]: "
            f"pages={stats.pages_fetched} "
            f"names_seen={stats.names_seen} "
            f"terms_parsed={stats.terms_parsed} "
            f"inserted={stats.politicians_inserted} "
            f"updated={stats.politicians_updated} "
            f"slug_collisions={stats.slug_collisions} "
            f"terms_inserted={stats.terms_inserted} "
            f"terms_skipped_existing={stats.terms_skipped_existing} "
            f"terms_skipped_active={stats.terms_skipped_active}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("ingest-on-former-mpps")
@click.option("--from-parliament", type=int, default=1,
              help="Earliest parliament to enumerate (default: 1 = 1867).")
@click.option("--until-parliament", type=int, default=44,
              help="Latest parliament to enumerate (default: 44 = current).")
@click.option("--delay", type=float, default=1.0,
              help="Seconds between page fetches (be polite to ola.org).")
@click.pass_context
def cmd_ingest_on_former_mpps(
    ctx: click.Context, from_parliament: int, until_parliament: int, delay: float,
) -> None:
    """Enumerate every MPP who's ever served in the Ontario Legislative Assembly.

    Scrapes ola.org/en/members/parliament-{N} for N in [--from-parliament,
    --until-parliament], then GETs /en/members/all/<slug>?_format=json
    per unique slug to capture the stable field_member_id. Upserts
    politicians keyed on ola_member_id (name-matching existing ON rows
    first so Open North current-roster entries get stamped rather
    than duplicated), and creates politician_terms rows per
    (politician, parliament) using the parliament's official date
    range.

    Full-history default (1..44) covers ~5500 MPPs from 1867-present;
    each parliament is one HTTP request and ~120 members each → ~50
    listing fetches + ~5500 per-member JSON fetches at --delay=1.0
    is ~95 minutes. Smoke-test with --from-parliament 32 to align
    with the Hansard-backwards-extension scope (parliaments 32-44).

    Idempotent: politicians upserted on ola_member_id (migration 0037
    UNIQUE partial); politician_terms upserted on (politician_id,
    office, started_at). Re-running is a no-op.

    Prereq for resolve-on-speakers-dated and for backfilling Ontario
    Hansard parliaments 32-43.
    """
    async def _wrap(db: Database) -> None:
        stats = await ingest_on_former_mpps(
            db,
            from_parliament=from_parliament,
            until_parliament=until_parliament,
            delay=delay,
        )
        console.print(
            f"[green]ingest-on-former-mpps[/green]: "
            f"parliaments={stats.parliaments_scanned} "
            f"unique_slugs={stats.unique_slugs} "
            f"json_fetches={stats.member_json_fetches} "
            f"json_failures={stats.member_json_failures} "
            f"inserted={stats.politicians_inserted} "
            f"updated={stats.politicians_updated} "
            f"name_matched={stats.politicians_name_matched} "
            f"terms_inserted={stats.terms_inserted} "
            f"terms_skipped={stats.terms_skipped_existing} "
            f"missing_listings={stats.parliaments_missing_listing}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("resolve-ab-speakers")
@click.option("--limit", type=int, default=None,
              help="Cap speeches scanned (smoke-test aid).")
@click.pass_context
def cmd_resolve_ab_speakers(ctx: click.Context, limit: Optional[int]) -> None:
    """Re-resolve politician_id on AB Hansard speeches with NULL
    politician_id.

    Keyed on (surname, legislature) from the parser-extracted
    speeches.raw->'ab_hansard' fields, joined against the historical
    politician_terms rows stamped by ingest-ab-former-mlas. Single
    SQL batch; cheap enough to run after every roster top-up.

    No-op on speeches where the surname + legislature yields multiple
    candidates (same surname in the same legislature — rare but real).
    Those stay NULL pending a riding-aware or portfolio-aware
    follow-up.
    """
    async def _wrap(db: Database) -> None:
        stats = await resolve_ab_speakers(db, limit=limit)
        console.print(
            f"[green]resolve-ab-speakers[/green]: "
            f"scanned={stats.scanned} updated={stats.updated} "
            f"still_unresolved={stats.still_unresolved}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("enrich-ab-mlas")
@click.option("--mid", type=str, default=None,
              help="Process a single ab_assembly_mid (smoke test).")
@click.option("--limit", type=int, default=None,
              help="Cap number of MLAs processed this run.")
@click.option("--delay", type=float, default=1.0,
              help="Seconds between page fetches (politeness).")
@click.option("--refresh/--no-refresh", default=False,
              help="Re-fetch even MLAs already enriched (etag-cached).")
@click.pass_context
def cmd_enrich_ab_mlas(
    ctx: click.Context, mid: Optional[str], limit: Optional[int],
    delay: float, refresh: bool,
) -> None:
    """Fetch /member-information?mid=NNNN per AB MLA and persist detail.

    Captures photo, party history, constituency history, and the full
    "Offices and Roles" table (Speaker / Premier / Minister / Critic /
    committee chair periods) into politicians + politician_terms. The
    Speaker terms enable merge-ab-presiding-stubs to disambiguate
    `presiding-officer-seed:AB:%` stubs and fold their speeches into
    the proper MID-keyed politicians.

    Sets photo_url; does NOT download/hash the photo. Run
    backfill-politician-photos afterwards to mirror the images onto
    the local /assets volume.

    Idempotent: skips MLAs whose extras.ab_member_info_fetched_at is
    set unless --refresh is passed.
    """
    async def _wrap(db: Database) -> None:
        stats = await enrich_ab_mlas(
            db, mid=mid, limit=limit, delay=delay, refresh=refresh,
        )
        console.print(
            f"[green]enrich-ab-mlas[/green]: "
            f"considered={stats.considered} fetched={stats.fetched} "
            f"updated={stats.politicians_updated} "
            f"terms_inserted={stats.terms_inserted} "
            f"failed={stats.failed}"
        )
        for s in stats.fail_samples:
            console.print(f"  [yellow]fail[/yellow] {s}")
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("merge-ab-presiding-stubs")
@click.option("--dry-run/--no-dry-run", default=False,
              help="Report stub→twin pairs without modifying any rows.")
@click.pass_context
def cmd_merge_ab_presiding_stubs(ctx: click.Context, dry_run: bool) -> None:
    """One-time reconciliation of AB presiding-officer-seed stubs.

    Each stub is merged into its MID-keyed twin (matched on last_name,
    disambiguated by overlapping Speaker terms when multiple twins share
    a surname). Speeches and speech_chunks reassign to the twin and the
    stub is deleted.

    speeches.speaker_role is preserved — the [Speaker] / [Chair] badge
    in search results survives the merge.

    Idempotent: a re-run finds zero stubs and is a no-op.
    """
    async def _wrap(db: Database) -> None:
        stats = await merge_ab_presiding_stubs(db, dry_run=dry_run)
        verb = "would_merge" if dry_run else "merged"
        console.print(
            f"[green]merge-ab-presiding-stubs[/green]: "
            f"considered={stats.stubs_considered} "
            f"{verb}={stats.stubs_merged} "
            f"no_twin={stats.stubs_no_twin} "
            f"ambiguous={stats.stubs_ambiguous} "
            f"empty_orphans={stats.skipped_no_speeches} "
            f"speeches_moved={stats.speeches_moved} "
            f"chunks_moved={stats.chunks_moved}"
        )
        for s in stats.fail_samples:
            console.print(f"  [yellow]skip[/yellow] {s}")
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("resolve-mb-bill-sponsors")
@click.option("--limit", type=int, default=None,
              help="Cap on rows scanned this run (default: all unresolved).")
@click.pass_context
def cmd_resolve_mb_bill_sponsors(ctx: click.Context, limit: Optional[int]) -> None:
    """Link any unresolved MB bill_sponsors rows to politicians.

    ingest-mb-bills resolves sponsors inline via slug join, so this
    command is mostly a no-op against a fresh roster. It matters for
    historical backfills where a bill was ingested before its sponsor
    had ``mb_assembly_slug`` stamped, or where the sponsor text used
    an edge-case format.
    """
    async def _wrap(db: Database) -> None:
        stats = await resolve_mb_bill_sponsors(db, limit=limit)
        console.print(
            f"[green]resolve-mb-bill-sponsors[/green]: "
            f"scanned={stats['scanned']} by_slug={stats['linked_by_slug']} "
            f"by_name={stats['linked_by_name']} "
            f"slugs_backfilled={stats['slugs_backfilled']} "
            f"unmatched={stats['unmatched']}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("fetch-mb-billstatus-pdf")
@click.pass_context
def cmd_fetch_mb_billstatus(ctx: click.Context) -> None:
    """Download billstatus.pdf into the scanner's PDF cache (MB_PDF_CACHE_DIR).

    Idempotent: re-runs on the same UTC day reuse the cached copy.
    Keyed by date so prior caches remain for diffing.
    """
    async def _wrap(db: Database) -> None:
        stats = await fetch_mb_billstatus(db)
        console.print(
            f"[green]fetch-mb-billstatus-pdf[/green]: "
            f"bytes={stats['path_bytes']} cached={stats['cached']}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("parse-mb-bill-events")
@click.option("--parliament", type=int, default=None,
              help="Legislature number. Default: latest in legislative_sessions.")
@click.option("--session", type=int, default=None,
              help="Session number within the legislature. Default: latest.")
@click.pass_context
def cmd_parse_mb_bill_events(ctx: click.Context, parliament, session) -> None:
    """Parse MB billstatus.pdf → bill_events (real stage dates).

    Deletes prior manitoba-billstatus events for this session, then
    re-inserts from the current parse. Requires that ingest-mb-bills
    has already created the matching bills rows.

    When --parliament/--session are omitted, resolves the current session
    from legislative_sessions.
    """
    from .legislative.current_session import current_session

    async def _wrap(db: Database) -> None:
        nonlocal parliament, session
        if parliament is None or session is None:
            parliament, session = await current_session(
                db, level="provincial", province_territory="MB",
            )
            console.print(
                f"[dim]auto-resolved current MB session: "
                f"P{parliament}-S{session}[/dim]"
            )
        stats = await parse_mb_bill_events(
            db, parliament=parliament, session=session,
        )
        console.print(
            f"[green]parse-mb-bill-events[/green]: "
            f"bills_seen={stats['bills_seen']} "
            f"events_deleted={stats['events_deleted']} "
            f"events_inserted={stats['events_inserted']} "
            f"status_updated={stats['latest_status_updated']} "
            f"no_match={stats['bills_no_match']}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("ingest-mb-bills")
@click.option("--parliament", type=int, default=None,
              help="Legislature number. Default: latest in legislative_sessions.")
@click.option("--session", type=int, default=None,
              help="Session number within the legislature. Default: latest.")
@click.option("--all-sessions", is_flag=True,
              help="Walk every MB session in legislative_sessions. "
                   "Overrides --parliament/--session.")
@click.pass_context
def cmd_ingest_mb_bills(
    ctx: click.Context, parliament, session, all_sessions: bool,
) -> None:
    """Ingest Manitoba bills roster from web2.gov.mb.ca.

    One HTTP GET per session returns Government Bills + Private Members'
    Bills tables on a single page. Sponsor names on the index are the
    only sponsor metadata — per-bill pages are text-only. Stage dates
    come from `billstatus.pdf` in a separate command
    (`parse-mb-bill-events`); this command only writes bills + sponsors.

    When --parliament/--session are omitted, resolves the current session
    from legislative_sessions. On a fresh DB, pass them explicitly once
    (e.g. --parliament 43 --session 3). With --all-sessions, walks every
    (parliament, session) pair already in legislative_sessions for MB
    (idempotent on source_id).
    """
    from .legislative.current_session import current_session
    from .legislative.mb_bills import ingest_all_sessions as _ingest_all

    async def _wrap(db: Database) -> None:
        nonlocal parliament, session
        if all_sessions:
            stats = await _ingest_all(db)
            console.print(
                f"[green]ingest-mb-bills[/green] (all sessions): "
                f"sessions={stats['sessions_touched']} "
                f"bills={stats['bills']} sponsors={stats['sponsors']} "
                f"sponsors_linked={stats['sponsors_linked']}"
            )
            return
        if parliament is None or session is None:
            parliament, session = await current_session(
                db, level="provincial", province_territory="MB",
            )
            console.print(
                f"[dim]auto-resolved current MB session: "
                f"P{parliament}-S{session}[/dim]"
            )
        stats = await ingest_mb_bills(db, parliament=parliament, session=session)
        console.print(
            f"[green]ingest-mb-bills[/green]: "
            f"bills={stats['bills']} inserted={stats['bills_inserted']} "
            f"updated={stats['bills_updated']} sponsors={stats['sponsors']} "
            f"sponsors_linked={stats['sponsors_linked']} "
            f"skipped={stats['rows_skipped']}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("ingest-mb-mlas")
@click.pass_context
def cmd_ingest_mb_mlas(ctx: click.Context) -> None:
    """Stamp politicians.mb_assembly_slug on existing MB rows; insert any missing MLAs.

    Open North already populates most MB MLAs but does not surface the
    Legislative Assembly's canonical identifier (the surname slug in
    /legislature/members/info/{surname}.html). This command fetches the
    authoritative roster and stamps the slug onto matching rows,
    inserting fresh rows for any MLA not yet covered upstream. Run
    before ingest-mb-bills and ingest-mb-hansard so sponsor / speaker
    resolution is an exact FK lookup.
    """
    async def _wrap(db: Database) -> None:
        stats = await ingest_mb_mlas(db)
        console.print(
            f"[green]ingest-mb-mlas[/green]: "
            f"fetched={stats['fetched']} matched={stats['matched_existing']} "
            f"inserted={stats['inserted']} slugs_set={stats['slugs_set']} "
            f"already={stats['slugs_already_correct']} conflicts={stats['slug_conflict']}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("ingest-ab-bills")
@click.option("--legislature", type=int, default=None,
              help="One specific legislature (pair with --session for one session).")
@click.option("--session", type=int, default=None,
              help="One specific session (requires --legislature).")
@click.option("--all-sessions-in-legislature", type=int, default=None,
              metavar="L", help="Every session in legislature L.")
@click.option("--all-sessions", is_flag=True,
              help="Backfill every session ever (Legislature 1 onward, ~137 sessions).")
@click.option("--delay", type=float, default=1.5,
              help="Delay between session fetches (seconds).")
@click.pass_context
def cmd_ingest_ab_bills(
    ctx: click.Context, legislature, session,
    all_sessions_in_legislature, all_sessions, delay,
) -> None:
    """Ingest Alberta bills from the Assembly Dashboard.

    One HTTP GET per session returns the full bill roster + stage
    history + sponsor. Default: current session only.
    """
    async def _wrap(db: Database) -> None:
        stats = await ingest_ab_bills(
            db,
            legislature=legislature, session=session,
            all_sessions_in_legislature=all_sessions_in_legislature,
            all_sessions=all_sessions,
            delay_seconds=delay,
        )
        console.print(
            f"[green]ingest-ab-bills[/green]: "
            f"sessions={stats['sessions_touched']} bills={stats['bills']} "
            f"events={stats['events']} sponsors={stats['sponsors']} "
            f"sponsors_linked={stats['sponsors_linked']}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("ingest-nb-bills")
@click.option("--legislature", type=int, default=None,
              help="One specific legislature (pair with --session).")
@click.option("--session", type=int, default=None,
              help="One specific session (requires --legislature).")
@click.option("--all-sessions-in-legislature", type=int, default=None,
              metavar="L", help="Every session in legislature L.")
@click.option("--delay", type=float, default=1.5,
              help="Delay between bill detail-page fetches (seconds).")
@click.pass_context
def cmd_ingest_nb_bills(
    ctx: click.Context, legislature, session,
    all_sessions_in_legislature, delay,
) -> None:
    """Ingest New Brunswick bills from legnb.ca.

    Default: current session. Per-bill detail fetch is the cost —
    ~35 bills/session × 1.5s delay ≈ 1 minute. Sponsor resolution is
    name-based (legnb.ca exposes no numeric MLA id).
    """
    async def _wrap(db: Database) -> None:
        stats = await ingest_nb_bills(
            db,
            legislature=legislature, session=session,
            all_sessions_in_legislature=all_sessions_in_legislature,
            delay_seconds=delay,
        )
        console.print(
            f"[green]ingest-nb-bills[/green]: "
            f"sessions={stats['sessions_touched']} bills={stats['bills']} "
            f"events={stats['events']} sponsors={stats['sponsors']} "
            f"sponsors_linked={stats['sponsors_linked']}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("ingest-nl-bills")
@click.option("--ga", type=int, default=None, metavar="G",
              help="General Assembly number (pair with --session).")
@click.option("--session", type=int, default=None,
              help="Session number (requires --ga).")
@click.option("--all-sessions-in-ga", type=int, default=None,
              metavar="G", help="Every session in GA G.")
@click.option("--all-sessions", is_flag=True,
              help="Every session in the index (GA 44 onwards, ~40 sessions).")
@click.option("--delay", type=float, default=1.0,
              help="Delay between session fetches (seconds).")
@click.pass_context
def cmd_ingest_nl_bills(
    ctx: click.Context, ga, session,
    all_sessions_in_ga, all_sessions, delay,
) -> None:
    """Ingest Newfoundland & Labrador bills from assembly.nl.ca.

    One HTTP GET per session = full stage timeline. **No sponsor data**
    (NL doesn't publish it on the list or per-bill pages). Default:
    current session.
    """
    async def _wrap(db: Database) -> None:
        stats = await ingest_nl_bills(
            db,
            ga=ga, session=session,
            all_sessions_in_ga=all_sessions_in_ga,
            all_sessions=all_sessions,
            delay_seconds=delay,
        )
        console.print(
            f"[green]ingest-nl-bills[/green]: "
            f"sessions={stats['sessions_touched']} "
            f"bills={stats['bills']} events={stats['events']}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("ingest-nt-bills")
@click.option("--delay", type=float, default=1.5,
              help="Delay between per-bill detail-page fetches (seconds).")
@click.pass_context
def cmd_ingest_nt_bills(ctx: click.Context, delay) -> None:
    """Ingest Northwest Territories bills from ntassembly.ca.

    List page + per-bill detail pages. Assembly + session parsed from
    each detail page, so multi-session pages are handled implicitly.
    No sponsor data (consensus government).
    """
    async def _wrap(db: Database) -> None:
        stats = await ingest_nt_bills(db, delay_seconds=delay)
        console.print(
            f"[green]ingest-nt-bills[/green]: "
            f"sessions={stats['sessions_touched']} "
            f"bills={stats['bills']} events={stats['events']}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("extract-federal-votes")
@click.option("--session", type=str, default=None,
              help="Parliament-session slug like '44-1'. Default: current.")
@click.option("--limit-votes", type=int, default=None,
              help="Cap on votes processed (newest-first; smoke-test aid).")
@click.option("--delay", type=float, default=0.5,
              help="Seconds between openparliament.ca API calls (politeness).")
@_forward_options
@click.pass_context
def cmd_extract_federal_votes(
    ctx: click.Context, session, limit_votes, delay, since, since_days,
) -> None:
    """Extract federal votes + per-MP positions from openparliament.ca.

    Two structured-JSON endpoints: vote list at /votes/?session={S} for
    summary records, and /votes/ballots/?vote={URL} for per-MP ballots.
    Politician attribution by exact-string FK match against
    politicians.openparliament_slug. Bill linkage via bill_url against
    bills.raw->>'url'. speech_id stays NULL (future post-pass).

    Idempotent: votes upsert on (source_system='votes-federal', source_url);
    vote_positions upsert on (vote_id, politician_name_raw=slug). Re-runs
    UPDATE in place; politician_id can lift on subsequent passes if the
    roster fills.

    Forward-incremental: --since / --since-days skip the per-vote
    ballots fetch (the cost driver) for votes whose `occurred_at` is
    older than the cutoff. With neither flag, the DB high-water on
    `votes.occurred_at WHERE level='federal'` minus 14d overlap is used.
    """
    from .legislative.federal_votes import extract_federal_votes as _extract
    from .legislative._forward import parse_iso_date, resolve_since

    async def _wrap(db: Database) -> None:
        effective_since = await resolve_since(
            db,
            explicit_since=parse_iso_date(since),
            since_days=since_days,
            table="votes",
            timestamp_column="occurred_at",
            where="level=$1",
            where_params=["federal"],
        )
        if effective_since is not None:
            console.print(
                f"[dim]forward-incremental: skipping votes before "
                f"{effective_since.isoformat()}[/dim]"
            )
        stats = await _extract(
            db, session=session, limit_votes=limit_votes, delay=delay,
            since=effective_since,
        )
        console.print(
            f"[green]extract-federal-votes[/green]: "
            f"votes seen={stats.votes_seen} inserted={stats.votes_inserted} "
            f"updated={stats.votes_updated} "
            f"positions inserted={stats.positions_inserted} "
            f"updated={stats.positions_updated} "
            f"bill_links={stats.bill_links} pol_links={stats.politician_links} "
            f"pol_unresolved={stats.politicians_unresolved} "
            f"api_calls={stats.api_calls}"
        )
        if stats.failures:
            console.print(
                f"[yellow]federal_votes failures (first 5):[/yellow] "
                f"{stats.failures[:5]}"
            )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("relink-federal-votes")
@click.pass_context
def cmd_relink_federal_votes(ctx: click.Context) -> None:
    """Re-derive federal votes.bill_id from votes.raw against current bills.

    Pure-SQL UPDATE pass — no openparliament.ca API calls. Each vote's
    raw payload retains the openparliament `bill_url` from the original
    extraction; this command joins that against the current `bills`
    table to lift the linkage rate after a federal-bills backfill (e.g.
    `ingest-federal-bills --all-sessions`). Idempotent: votes already
    linked to the right bill are skipped via `IS DISTINCT FROM`.

    Run after any federal-bills ingest. Cheap enough to schedule daily.
    """
    from .legislative.federal_votes import relink_federal_votes as _relink

    async def _wrap(db: Database) -> None:
        stats = await _relink(db)
        console.print(
            f"[green]relink-federal-votes[/green]: "
            f"bills_available={stats.bill_index_size} "
            f"candidates={stats.candidates} "
            f"already_linked={stats.already_linked} "
            f"newly_linked={stats.newly_linked} "
            f"no_match={stats.unchanged}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


def _make_provincial_votes_cmd(prov_lower: str, prov_upper: str, source_label: str):
    """Helper: build a Click command for a provincial votes extractor."""
    @cli.command(f"extract-{prov_lower}-votes")
    @click.option("--limit-sittings", type=int, default=None,
                  help="Cap to most-recent N sittings (smoke-test aid).")
    @click.pass_context
    def _cmd(ctx: click.Context, limit_sittings) -> None:
        from importlib import import_module
        mod = import_module(f".legislative.{prov_lower}_votes", package="src")
        extract_fn = getattr(mod, f"extract_{prov_lower}_votes")
        async def _wrap(db: Database) -> None:
            stats = await extract_fn(db, limit_sittings=limit_sittings)
            console.print(
                f"[green]extract-{prov_lower}-votes[/green]: "
                f"scanned={stats.speeches_scanned} "
                f"inserted={stats.votes_inserted} updated={stats.votes_updated} "
                f"skipped={stats.votes_skipped_no_outcome} "
                f"bill_links={stats.bill_linkage_hits}"
            )
            if stats.by_type:
                console.print(f"[dim]by_type:[/dim] {stats.by_type}")
            if stats.by_result:
                console.print(f"[dim]by_result:[/dim] {stats.by_result}")
        asyncio.run(_run(_wrap, ctx.obj["dsn"]))
    _cmd.__doc__ = (
        f"Derive `votes` rows from already-ingested {prov_upper} Hansard speeches.\n\n"
        f"    Source corpus: source_system='{source_label}'.\n"
        f"    Idempotent: upsert keyed on (source_system='votes-{prov_lower}', source_url).\n"
        f"    Run after the corresponding ingest-{prov_lower}-hansard command."
    )
    return _cmd


_extract_bc_votes_cmd = _make_provincial_votes_cmd("bc", "BC", "hansard-bc")
_extract_ab_votes_cmd = _make_provincial_votes_cmd("ab", "AB", "assembly.ab.ca")
_extract_qc_votes_cmd = _make_provincial_votes_cmd("qc", "QC", "hansard-qc")
_extract_on_votes_cmd = _make_provincial_votes_cmd("on", "ON", "hansard-on")
_extract_mb_votes_cmd = _make_provincial_votes_cmd("mb", "MB", "hansard-mb")
_extract_ns_votes_cmd = _make_provincial_votes_cmd("ns", "NS", "hansard-ns")
_extract_nl_votes_cmd = _make_provincial_votes_cmd("nl", "NL", "hansard-nl")
_extract_nb_votes_cmd = _make_provincial_votes_cmd("nb", "NB", "legnb-hansard")


@cli.command("extract-sk-votes")
@click.option("--journal-url", type=str, default=None,
              help="Process a single Journal PDF by URL (smoke test).")
@click.option("--all-journals", is_flag=True, default=False,
              help="Process every Journal (historical backfill).")
@click.option("--current-only", is_flag=True, default=True,
              help="Process only the highest (legislature, session) Journal "
                   "(default; use --all-journals to backfill).")
@click.option("--limit-journals", type=int, default=None,
              help="Cap journals processed (newest-first when capped).")
@click.option("--delay", type=float, default=1.0,
              help="Seconds between per-PDF fetches.")
@click.pass_context
def cmd_extract_sk_votes(
    ctx: click.Context, journal_url, all_journals, current_only,
    limit_journals, delay,
) -> None:
    """Extract SK votes from Journals PDFs with per-MLA roll-call.

    SK Journals are session-aggregated PDFs at
    /legislative-business/journals/ with structured YEAS / POUR — N
    and NAYS / CONTRE — M grids. Surname-only with `(Constituency)`
    parens for disambiguation when two MLAs share a surname.

    Per-MLA YEA/NAY positions land in `vote_positions` (unlike the
    consensus-shape extractors for MB / NL / NT). Tallies are
    populated from the marker. Bill linkage via `Bill N` mention in
    the motion text.

    Default: current-session-only (forward-incremental, daily-friendly).
    Use --all-journals for historical backfill (~117 PDFs back to 1L1S).
    Idempotent: source_url is keyed on `<pdf_url>#page=N`.
    """
    from .legislative.sk_votes import extract_sk_votes as _extract

    async def _wrap(db: Database) -> None:
        stats = await _extract(
            db, journal_url=journal_url, all_journals=all_journals,
            current_only=current_only, limit_journals=limit_journals,
            delay=delay,
        )
        console.print(
            f"[green]extract-sk-votes[/green]: "
            f"journals seen={stats.journals_seen} fetched={stats.journals_fetched} "
            f"divisions={stats.divisions_seen} "
            f"votes inserted={stats.votes_inserted} updated={stats.votes_updated} "
            f"positions inserted={stats.positions_inserted} updated={stats.positions_updated} "
            f"bill_links={stats.bill_links} "
            f"pol_links={stats.politician_links} unresolved={stats.politicians_unresolved}"
        )
        if stats.failures:
            console.print(
                f"[yellow]sk_votes failures (first 5):[/yellow] {stats.failures[:5]}"
            )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("extract-nt-votes")
@click.option("--limit-sittings", type=int, default=None,
              help="Cap to most-recent N sittings (smoke-test aid).")
@click.pass_context
def cmd_extract_nt_votes(ctx: click.Context, limit_sittings) -> None:
    """Derive `votes` rows from already-ingested NT Hansard speeches.

    NT consensus government → most votes are `vote_type='consensus'` with
    NULL ayes/nays (no per-member tracking in Hansard text). The Hansard
    convention `---Carried` / `---Defeated` annotation is the canonical
    signal. Bill linkage is opportunistic via `Bill N` mention.

    Idempotent: upsert keyed on (source_system='votes-nt', source_url).
    Re-runs UPDATE in place. Run after ingest-nt-hansard.
    """
    from .legislative.nt_votes import extract_nt_votes as _extract

    async def _wrap(db: Database) -> None:
        stats = await _extract(db, limit_sittings=limit_sittings)
        console.print(
            f"[green]extract-nt-votes[/green]: "
            f"scanned={stats.speeches_scanned} "
            f"inserted={stats.votes_inserted} updated={stats.votes_updated} "
            f"skipped={stats.votes_skipped_no_outcome} "
            f"bill_links={stats.bill_linkage_hits}"
        )
        if stats.by_type:
            console.print(f"[dim]by_type:[/dim] {stats.by_type}")
        if stats.by_result:
            console.print(f"[dim]by_result:[/dim] {stats.by_result}")
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("ingest-nu-hansard")
@click.option("--since", type=str, default=None,
              help="Only ingest sittings on/after this ISO date (YYYY-MM-DD).")
@click.option("--since-days", type=int, default=None,
              help="Forward-incremental: clamp --since to today - N days "
                   "(use in daily schedules).")
@click.option("--until", type=str, default=None,
              help="Only ingest sittings on/before this ISO date.")
@click.option("--limit-sittings", type=int, default=None,
              help="Cap sittings processed (newest-first when capped).")
@click.option("--url", "one_off_url", type=str, default=None,
              help="Bypass discovery and ingest a single PDF URL directly.")
@click.option("--delay", type=float, default=1.0,
              help="Seconds between per-PDF fetches.")
@click.pass_context
def cmd_ingest_nu_hansard(
    ctx: click.Context, since, since_days, until, limit_sittings,
    one_off_url, delay,
) -> None:
    """Ingest Nunavut Hansard PDFs into the `speeches` table.

    Source: assembly.nu.ca/hansard, ~59 PDFs back to 2021-02-24. English-
    primary with `(interpretation)` markers for Inuktitut passages.
    Consensus government → no party affiliation. Speaker resolution
    via politicians.last_name + constituency_name disambiguation.

    Idempotent: upsert keyed on (source_system='hansard-nu', source_url, sequence).
    """
    from .legislative.nu_hansard import ingest_nu_hansard as _ingest
    from .legislative._forward import parse_iso_date, clamp_since_with_days

    effective_since = clamp_since_with_days(parse_iso_date(since), since_days)

    async def _wrap(db: Database) -> None:
        if since_days is not None and effective_since is not None:
            console.print(
                f"[dim]forward-incremental: --since clamped to "
                f"{effective_since.isoformat()} (since_days={since_days})[/dim]"
            )
        stats = await _ingest(
            db,
            since=effective_since,
            until=parse_iso_date(until),
            limit_sittings=limit_sittings,
            one_off_url=one_off_url,
            delay=delay,
        )
        console.print(
            f"[green]ingest-nu-hansard[/green]: "
            f"sittings seen={stats.sittings_seen} fetched={stats.sittings_fetched} "
            f"skipped={stats.sittings_skipped} "
            f"speeches inserted={stats.speeches_inserted} updated={stats.speeches_updated} "
            f"resolved={stats.speeches_resolved} presiding={stats.speeches_presiding} "
            f"unresolved={stats.speeches_unresolved}"
        )
        if stats.failures:
            console.print(f"[yellow]nu_hansard failures (first 3):[/yellow] {stats.failures[:3]}")
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("ingest-nt-hansard")
@click.option("--limit-sittings", type=int, default=None,
              help="Cap on sittings ingested (newest-first). Smoke-test friendly.")
@click.option("--since", "since_hn_id", type=str, default=None,
              help="Only ingest sittings with hn_id sorting strictly above this (e.g. 'hn250101').")
@click.option("--since-days", type=int, default=None,
              help="Forward-incremental: derive --since hn_id from today - N days "
                   "(use in daily schedules). Loses to explicit --since.")
@click.option("--url", "only_url", type=str, default=None,
              help="Bypass discovery and ingest a single transcript URL directly.")
@click.option("--delay", type=float, default=1.0,
              help="Seconds between per-sitting fetches.")
@click.pass_context
def cmd_ingest_nt_hansard(
    ctx: click.Context, limit_sittings, since_hn_id, since_days, only_url, delay,
) -> None:
    """Ingest Northwest Territories Hansard from ntlegislativeassembly.ca.

    Discovery walks /documents-proceedings/hansard?page=N until empty
    (~30 pages back to ~2002). Per-sitting HTML at /hansard/hn{YYMMDD}
    parsed into one speech row per views-row--type-statement. Speaker
    attribution by direct nt_mla_slug FK (run ingest-nt-mlas first).
    Idempotent: upsert keyed on (source_system, source_url, sequence).
    """
    from .legislative.nt_hansard import ingest_nt_hansard as _ingest

    # NT's discovery filter is an opaque hn_id (hn{YYMMDD}); convert
    # --since-days to that shape if no explicit --since provided.
    if since_hn_id is None and since_days is not None:
        from datetime import date as _date, timedelta as _td
        cutoff = _date.today() - _td(days=int(since_days))
        since_hn_id = f"hn{cutoff.strftime('%y%m%d')}"
        console.print(
            f"[dim]forward-incremental: --since clamped to {since_hn_id} "
            f"(since_days={since_days})[/dim]"
        )

    async def _wrap(db: Database) -> None:
        stats = await _ingest(
            db,
            limit_sittings=limit_sittings,
            since_hn_id=since_hn_id,
            only_url=only_url,
            delay=delay,
        )
        console.print(
            f"[green]ingest-nt-hansard[/green]: "
            f"seen={stats.sittings_seen} fetched={stats.sittings_fetched} "
            f"skipped={stats.sittings_skipped} "
            f"inserted={stats.speeches_inserted} updated={stats.speeches_updated} "
            f"sessions={len(stats.sessions_touched)} "
            f"warns={stats.parse_warnings} fails={len(stats.fetch_failures)}"
        )
        if stats.fetch_failures:
            console.print(
                f"[yellow]nt_hansard fail samples:[/yellow] {stats.fetch_failures[:3]}"
            )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("ingest-sk-bills")
@click.option("--all-sessions", is_flag=True, default=False,
              help="Walk every progress-of-bills PDF on the bills page (historical backfill).")
@click.option("--url", type=str, default=None,
              help="Bypass discovery; ingest a single PDF URL.")
@click.option("--delay", type=float, default=1.0,
              help="Seconds between per-PDF requests when walking multiple.")
@click.option("--dry-run", is_flag=True, default=False,
              help="Parse + report counts without writing to the DB.")
@click.option("--selftest", is_flag=True, default=False,
              help="Fetch the current PDF and assert hand-curated golden cases. No DB writes.")
@click.pass_context
def cmd_ingest_sk_bills(
    ctx: click.Context, all_sessions, url, delay, dry_run, selftest,
) -> None:
    """Ingest SK bills from progress-of-bills.pdf.

    Single-command flow: scrapes /legislative-business/bills/, identifies
    each PDF's (parliament, session) by reading the first-page header,
    parses the tabular text via pdftotext -layout, and upserts bills +
    bill_events + bill_sponsors. Idempotent.

    Default: ingest the currently-active session only. --all-sessions
    walks every recent progress-of-bills PDF (skips yearly-span legacy
    PDFs from 1998–2017 which use a different table shape).
    """
    if selftest:
        from .legislative.sk_bills import run_selftest
        rc = asyncio.run(run_selftest())
        raise click.exceptions.Exit(rc)

    from .legislative.sk_bills import ingest_sk_bills as _ingest

    async def _wrap(db: Database) -> None:
        stats = await _ingest(
            db,
            all_sessions=all_sessions,
            url=url,
            delay=delay,
            dry_run=dry_run,
        )
        prefix = "[yellow]DRY-RUN[/yellow] " if dry_run else ""
        console.print(
            f"{prefix}[green]ingest-sk-bills[/green]: "
            f"pdfs={stats.pdfs_seen} "
            f"bills_parsed={stats.bills_parsed} "
            f"bills_inserted={stats.bills_inserted} "
            f"bills_updated={stats.bills_updated} "
            f"sponsors={stats.sponsors_inserted} "
            f"fk_hits={stats.sponsor_fk_hits} "
            f"fk_misses={stats.sponsor_fk_misses} "
            f"events={stats.events_inserted} "
            f"failures={len(stats.failures)}"
        )
        if dry_run and stats.sample:
            console.print("[yellow]DRY-RUN sample (first 5 bills):[/yellow]")
            for pb in stats.sample:
                stages = ", ".join(f"{k}={v}" for k, v in pb.stages.items())
                console.print(
                    f"  [{pb.bill_number}] {pb.bill_type:14} "
                    f"{(pb.title[:60] + '…') if len(pb.title) > 60 else pb.title}"
                )
                console.print(
                    f"      sponsor={pb.sponsor_raw!r} force={pb.force_code!r} "
                    f"comm1={pb.committee_first!r} comm2={pb.committee_second!r}"
                )
                console.print(f"      stages: {stages}")
        if stats.failures:
            for f in stats.failures[:5]:
                console.print(f"  [yellow]warn:[/yellow] {f}")

    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("ingest-sk-hansard")
@click.option("--limit-sittings", type=int, default=None,
              help="Cap to first N sittings (newest-first ordering).")
@click.option("--since", type=str, default=None,
              help="Only ingest sittings on or after YYYY-MM-DD.")
@click.option("--since-days", type=int, default=None,
              help="Forward-incremental: clamp --since to today - N days "
                   "(use in daily schedules).")
@click.option("--url", type=str, default=None,
              help="Bypass discovery; ingest one transcript URL.")
@click.option("--delay", type=float, default=1.0,
              help="Seconds between per-sitting fetches.")
@click.option("--max-archive-pages", type=int, default=None,
              help="Cap discovery walker (defensive). Default: walk to empty.")
@click.pass_context
def cmd_ingest_sk_hansard(
    ctx: click.Context, limit_sittings, since, since_days, url, delay, max_archive_pages,
) -> None:
    """Ingest SK Hansard from docs.legassembly.sk.ca.

    Discovery walks the paginated archive at /legislative-business/archive/
    and harvests every Assembly-debates HTML URL. Per-sitting URLs embed
    parliament/session/date (e.g. 30L2S/20260504DebatesHTML.htm) so we
    don't need to read body headers for those fields. Speakers are
    attached to politicians via sk_assembly_slug — run ingest-sk-mlas
    first.

    Idempotent. UPSERT keys: (source_system='hansard-sk', source_url, sequence).
    """
    from .legislative.sk_hansard import ingest_sk_hansard as _ingest
    from datetime import date as _Date
    from .legislative._forward import clamp_since_with_days

    explicit_since = None
    if since:
        try:
            explicit_since = _Date.fromisoformat(since)
        except ValueError:
            console.print(f"[red]invalid --since {since!r}; expected YYYY-MM-DD[/red]")
            raise click.exceptions.Exit(2)
    effective_since = clamp_since_with_days(explicit_since, since_days)
    if since_days is not None and effective_since is not None:
        console.print(
            f"[dim]forward-incremental: --since clamped to "
            f"{effective_since.isoformat()} (since_days={since_days})[/dim]"
        )

    async def _wrap(db: Database) -> None:
        stats = await _ingest(
            db,
            limit_sittings=limit_sittings,
            since=effective_since,
            url=url,
            delay=delay,
            max_archive_pages=max_archive_pages,
        )
        console.print(
            f"[green]ingest-sk-hansard[/green]: "
            f"seen={stats.sittings_seen} fetched={stats.sittings_fetched} "
            f"skipped={stats.sittings_skipped} "
            f"speeches_inserted={stats.speeches_inserted} "
            f"speeches_updated={stats.speeches_updated} "
            f"sessions={len(stats.sessions_touched)} "
            f"fetch_fail={len(stats.fetch_failures)} "
            f"parse_fail={len(stats.parse_failures)}"
        )
        if stats.fetch_failures or stats.parse_failures:
            for f in (stats.fetch_failures + stats.parse_failures)[:5]:
                console.print(f"  [yellow]warn:[/yellow] {f}")

    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("ingest-sk-committees")
@click.option("--legislature", type=int, default=None,
              help="Restrict to one legislature (e.g. 30). Default: current.")
@click.option("--all-legislatures", is_flag=True, default=False,
              help="Ingest every legislature the archive lists (historical "
                   "backfill). Overrides --legislature.")
@click.option("--since", type=str, default=None,
              help="Only ingest meetings on or after YYYY-MM-DD.")
@click.option("--until", type=str, default=None,
              help="Only ingest meetings on or before YYYY-MM-DD.")
@click.option("--limit-meetings", type=int, default=None,
              help="Cap to first N meetings (newest-first ordering).")
@click.option("--committees", type=str, default=None,
              help="Comma-separated committee acronyms (e.g. PAC,CCA).")
@click.option("--url", type=str, default=None,
              help="Bypass discovery; ingest one transcript URL.")
@click.option("--delay", type=float, default=1.0,
              help="Seconds between per-meeting fetches.")
@click.option("--max-archive-pages", type=int, default=None,
              help="Cap discovery walker (defensive). Default: walk to empty.")
@click.pass_context
def cmd_ingest_sk_committees(
    ctx: click.Context, legislature, all_legislatures, since, until,
    limit_meetings, committees, url, delay, max_archive_pages,
) -> None:
    """Ingest SK committee Hansard Verbatim Reports.

    Discovery walks the same paginated archive as ingest-sk-hansard but
    harvests the Committees/{ACR}/Debates family the chamber walker
    skips. HTML wins over PDF per meeting. Sessions are resolved from
    the meeting date against chamber-corpus session boundaries (committee
    URLs carry legislature only). Speaker resolution is witness-safe:
    full-name slug match or role-bearing surname only — plain names that
    aren't an MLA's full name are witnesses and stay NULL.

    Idempotent. UPSERT keys: (source_system='hansard-sk', source_url, sequence).
    """
    from .legislative.sk_committees import ingest_sk_committees as _ingest
    from .legislative.current_session import current_session
    from datetime import date as _Date

    def _parse_date(val, flag):
        if not val:
            return None
        try:
            return _Date.fromisoformat(val)
        except ValueError:
            console.print(f"[red]invalid {flag} {val!r}; expected YYYY-MM-DD[/red]")
            raise click.exceptions.Exit(2)

    since_d = _parse_date(since, "--since")
    until_d = _parse_date(until, "--until")
    committees_list = (
        [c for c in committees.split(",") if c.strip()] if committees else None
    )

    async def _wrap(db: Database) -> None:
        legl = legislature
        if all_legislatures:
            legl = None
        elif legl is None:
            legl, _sess = await current_session(
                db, level="provincial", province_territory="SK")
            console.print(f"[dim]auto-resolved current SK legislature: {legl}L[/dim]")
        stats = await _ingest(
            db,
            legislature=legl,
            since=since_d,
            until=until_d,
            limit_meetings=limit_meetings,
            committees=committees_list,
            url=url,
            delay=delay,
            max_archive_pages=max_archive_pages,
        )
        console.print(
            f"[green]ingest-sk-committees[/green]: "
            f"seen={stats.meetings_seen} fetched={stats.meetings_fetched} "
            f"skipped={stats.meetings_skipped} "
            f"inserted={stats.speeches_inserted} "
            f"updated={stats.speeches_updated} "
            f"resolved={stats.resolved} witnesses={stats.witnesses} "
            f"sessions={sorted(stats.sessions_touched)} "
            f"fetch_fail={len(stats.fetch_failures)} "
            f"parse_fail={len(stats.parse_failures)}"
        )
        if stats.unknown_acronyms:
            console.print(
                f"  [red]unknown acronyms:[/red] {sorted(stats.unknown_acronyms)}"
            )
        if stats.fetch_failures or stats.parse_failures:
            for f in (stats.fetch_failures + stats.parse_failures)[:5]:
                console.print(f"  [yellow]warn:[/yellow] {f}")

    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("ingest-on-committees")
@click.option("--parliament", type=int, default=None,
              help="ON Parliament number (e.g. 44). Default: current.")
@click.option("--since", type=str, default=None,
              help="Only ingest transcripts on or after YYYY-MM-DD.")
@click.option("--until", type=str, default=None,
              help="Only ingest transcripts on or before YYYY-MM-DD.")
@click.option("--limit-transcripts", type=int, default=None,
              help="Cap to first N transcripts (newest-first ordering).")
@click.option("--committees", type=str, default=None,
              help="Comma-separated committee slugs "
                   "(e.g. public-accounts,justice-policy).")
@click.option("--url", type=str, default=None,
              help="Bypass discovery; ingest one transcript URL.")
@click.pass_context
def cmd_ingest_on_committees(
    ctx: click.Context, parliament, since, until, limit_transcripts,
    committees, url,
) -> None:
    """Ingest ON standing-committee transcripts via ola.org Drupal JSON.

    Discovery walks each committee's per-parliament transcripts listing;
    transcript nodes are fetched with ?_format=json and parsed with the
    ON chamber Hansard parser (same attribution shapes). Speaker
    resolution is witness-safe: exact full-name matching only — plain
    names that aren't an MPP's full name are witnesses and stay NULL.

    Idempotent. UPSERT keys: (source_system='hansard-on', source_url, sequence).
    """
    from .legislative.on_committees import ingest_on_committees as _ingest
    from .legislative.current_session import current_session
    from datetime import date as _Date

    def _parse_date(val, flag):
        if not val:
            return None
        try:
            return _Date.fromisoformat(val)
        except ValueError:
            console.print(f"[red]invalid {flag} {val!r}; expected YYYY-MM-DD[/red]")
            raise click.exceptions.Exit(2)

    since_d = _parse_date(since, "--since")
    until_d = _parse_date(until, "--until")
    committees_list = (
        [c for c in committees.split(",") if c.strip()] if committees else None
    )

    async def _wrap(db: Database) -> None:
        parl = parliament
        if parl is None:
            parl, _sess = await current_session(
                db, level="provincial", province_territory="ON")
            console.print(f"[dim]auto-resolved current ON parliament: P{parl}[/dim]")
        stats = await _ingest(
            db,
            parliament=parl,
            since=since_d,
            until=until_d,
            limit_transcripts=limit_transcripts,
            committees=committees_list,
            one_off_url=url,
        )
        console.print(
            f"[green]ingest-on-committees[/green]: "
            f"committees={stats.committees_walked} "
            f"seen={stats.transcripts_seen} fetched={stats.transcripts_fetched} "
            f"skipped={stats.transcripts_skipped} "
            f"inserted={stats.speeches_inserted} "
            f"updated={stats.speeches_updated} "
            f"resolved={stats.resolved} witnesses={stats.witnesses} "
            f"sessions={sorted(stats.sessions_touched)} "
            f"fetch_fail={len(stats.fetch_failures)} "
            f"parse_fail={len(stats.parse_failures)}"
        )
        if stats.fetch_failures or stats.parse_failures:
            for f in (stats.fetch_failures + stats.parse_failures)[:5]:
                console.print(f"  [yellow]warn:[/yellow] {f}")

    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("ingest-sk-mlas")
@click.option("--parliaments", default="30",
              help="Comma-separated SK parliament numbers to fetch (e.g. '29,30'). Default: 30.")
@click.pass_context
def cmd_ingest_sk_mlas(ctx: click.Context, parliaments: str) -> None:
    """Upsert SK MLA roster from the Hansard speaker index.

    SK publishes no per-MLA stable identifier; we synthesise the slug
    `firstname-lastname` and persist it as `politicians.sk_assembly_slug`.
    The speaker index at docs.legassembly.sk.ca/legdocs/Assembly/Debates/
    Indexes/{N}/{N}L-SP-full.html lists every MLA who has spoken during
    the parliament along with party, constituency, session participation,
    and cabinet portfolio.

    Idempotent. Re-runs upsert via ON CONFLICT on sk_assembly_slug.
    """
    from .legislative.sk_mlas import ingest_sk_mlas as _ingest

    parls = [int(p.strip()) for p in parliaments.split(",") if p.strip()]

    async def _wrap(db: Database) -> None:
        stats = await _ingest(db, parliaments=parls)
        console.print(
            f"[green]ingest-sk-mlas[/green]: "
            f"parliaments={stats.parliaments_fetched} "
            f"entries={stats.entries_parsed} "
            f"inserted={stats.politicians_inserted} "
            f"updated={stats.politicians_updated} "
            f"retired={stats.politicians_retired} "
            f"failures={len(stats.failures)}"
        )
        if stats.failures:
            console.print(
                f"[yellow]sk_mlas warnings:[/yellow] "
                f"{stats.failures[:5]}"
            )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("ingest-nt-mlas")
@click.option("--include-former/--no-include-former", default=True,
              help="Walk /members/former-members and insert any MLA missing from politicians.")
@click.pass_context
def cmd_ingest_nt_mlas(ctx: click.Context, include_former: bool) -> None:
    """Stamp `nt_mla_slug` on existing NT politicians + insert former MLAs.

    Current 19 MLAs typically already exist via Open North roster
    (`opennorth:northwest-territories-legislature:{slug}`); this stamps
    `nt_mla_slug` on those rows so the Hansard parser can attribute
    speaker turns by FK. Former MLAs (~100+, paginated at
    /members/former-members) get inserted fresh with `is_active=false`,
    `party=NULL` (NT is consensus government — no party affiliation).

    Idempotent. Re-runs only stamp newly-discovered slugs.
    """
    from .legislative.nt_mlas import ingest_nt_mlas as _ingest

    async def _wrap(db: Database) -> None:
        stats = await _ingest(db, include_former=include_former)
        console.print(
            f"[green]ingest-nt-mlas[/green]: "
            f"current={stats.current_slugs_seen} former={stats.former_slugs_seen} "
            f"stamped={stats.politicians_stamped} "
            f"inserted={stats.politicians_inserted} "
            f"skipped={stats.politicians_skipped}"
        )
        if stats.failures:
            console.print(
                f"[yellow]nt_mlas warnings:[/yellow] "
                f"{stats.failures[:5]}"
            )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("ingest-nu-bills")
@click.option("--assembly", type=int, default=None,
              help="Assembly number (default: current sitting).")
@click.option("--session", type=int, default=None,
              help="Session number (default: current sitting).")
@click.pass_context
def cmd_ingest_nu_bills(ctx: click.Context, assembly, session) -> None:
    """Ingest Nunavut bills from assembly.nu.ca/bills-and-legislation.

    Drupal 9 table view — one HTTP GET returns every current-session
    bill with typed <time> elements for each stage. Caller provides
    assembly/session (Drupal doesn't print them). No sponsor data
    (consensus government).
    """
    from .legislative.nu_bills import DEFAULT_ASSEMBLY, DEFAULT_SESSION
    async def _wrap(db: Database) -> None:
        stats = await ingest_nu_bills(
            db,
            assembly=assembly if assembly is not None else DEFAULT_ASSEMBLY,
            session=session if session is not None else DEFAULT_SESSION,
        )
        console.print(
            f"[green]ingest-nu-bills[/green]: "
            f"sessions={stats['sessions_touched']} "
            f"bills={stats['bills']} events={stats['events']}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("parse-ns-bill-pages")
@click.option("--limit", type=int, default=None,
              help="Cap bills parsed this run (for iteration on the regex).")
@click.pass_context
def cmd_parse_ns_bill_pages(ctx: click.Context, limit) -> None:
    """Parse cached bill HTML into bill_sponsors + bill_events (phase 3).

    Pure offline. Safe to re-run. Skips bills that already have a
    sponsor row; delete from bill_sponsors to reparse.
    """
    async def _wrap(db: Database) -> None:
        stats = await parse_ns_bill_pages(db, limit=limit)
        console.print(
            f"[green]parse-ns-bill-pages[/green]: "
            f"bills={stats['bills']} sponsors={stats['sponsors']} "
            f"events={stats['events']} no_sponsor={stats['no_sponsor']}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


# ─────────────────────────────────────────────────────────────────────
# Offices backfill (final gap fill)
# ─────────────────────────────────────────────────────────────────────
from .offices import backfill_offices  # noqa: E402


@cli.command("backfill-offices")
@click.pass_context
def cmd_backfill_offices(ctx: click.Context) -> None:
    """Materialise politicians.extras->'offices' into politician_offices.

    Idempotent one-time backfill. Ongoing ingestion also populates the
    table automatically via opennorth._upsert_politician.
    """
    async def _wrap(db: Database) -> None:
        stats = await backfill_offices(db)
        console.print(
            f"[green]backfill-offices[/green]: "
            f"inserted={stats['inserted']} skipped={stats['skipped']} "
            f"politicians_touched={stats['politicians_touched']} "
            f"parse_failures={stats['parse_failures']}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


# ─────────────────────────────────────────────────────────────────────
# Senate ingestion (final gap fill)
# ─────────────────────────────────────────────────────────────────────
from .gap_fillers import senate as _gf_senate  # noqa: E402


@cli.command("ingest-senators")
@click.pass_context
def cmd_ingest_senators(ctx: click.Context) -> None:
    """Scrape sencanada.ca for the 105 Canadian senators (provincial seats).

    Open North has no representative-set for the Canadian Senate, so we go
    directly to the Senate's own Umbraco AJAX endpoints. Rows are upserted
    with level='federal', elected_office='Senator', and province_territory
    set to the constitutionally-apportioned province for each seat. Safe
    to re-run; source_id 'direct:sencanada-ca:<slug>' is idempotent.
    """
    asyncio.run(_run(_gf_senate.run, ctx.obj["dsn"]))


# ─────────────────────────────────────────────────────────────────────
# Personal-site social harvest (nationwide)
# ─────────────────────────────────────────────────────────────────────


@cli.command("harvest-personal-socials")
@click.option("--limit", type=int, default=None,
              help="Max politicians to process per run (default: all).")
@click.pass_context
def cmd_harvest_personal_socials(ctx: click.Context, limit) -> None:
    """Fetch every politician's personal site and harvest social handles
    from header/footer. Covers politicians whose personal_url came from
    gap fillers, Wikipedia-based scraping, etc. (not just Phase 5)."""
    from .harvest_personal_socials import harvest_all_personal_socials
    async def _wrap(db: Database) -> None:
        stats = await harvest_all_personal_socials(db, limit=limit)
        console.print(f"[green]{stats}[/green]")
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


# ─────────────────────────────────────────────────────────────────────
# Federal Hansard — speeches ingest (openparliament.ca)
# ─────────────────────────────────────────────────────────────────────

@cli.command("ingest-federal-bills")
@click.option("--parliament", type=int, default=None,
              help="Parliament number. Default: latest in legislative_sessions.")
@click.option("--session", type=int, default=None,
              help="Session number. Default: latest.")
@click.option("--all-sessions", is_flag=True,
              help="Walk every federal session in legislative_sessions.")
@click.option("--limit", type=int, default=None,
              help="Cap on bills processed (smoke-test friendly).")
@click.option("--delay", "delay_secs", type=float, default=0.5,
              help="Seconds between per-bill detail fetches (be polite to openparliament.ca).")
@click.option("--since", type=str, default=None,
              help="Forward-incremental: skip detail fetch for bills introduced before this ISO date.")
@click.option("--since-days", type=int, default=None,
              help="Forward-incremental: --since = today - N days "
                   "(use in daily schedules; defaults from DB high-water if neither given).")
@click.pass_context
def cmd_ingest_federal_bills(
    ctx: click.Context, parliament, session, all_sessions, limit, delay_secs,
    since, since_days,
) -> None:
    """Ingest federal bills from openparliament.ca JSON API.

    Closes the federal bills_status='partial' gap. Sponsor FK via
    politicians.openparliament_slug. Idempotent on
    source_id='openparliament-bills:{p}-{s}:{number}'.

    No stage events (openparliament doesn't expose them on bills); status
    field carries the latest stage as a string.

    Forward-incremental: --since / --since-days skip the per-bill detail
    fetch (the cost driver) for bills whose `introduced` date is older
    than the cutoff. With neither flag set, the DB high-water on
    `bills.introduced_date WHERE level='federal'` minus 14d overlap is used.
    """
    from .legislative.federal_bills import ingest_federal_bills
    from .legislative._forward import parse_iso_date, resolve_since

    async def _wrap(db: Database) -> None:
        effective_since = await resolve_since(
            db,
            explicit_since=parse_iso_date(since),
            since_days=since_days,
            table="bills",
            timestamp_column="introduced_date",
            where="level=$1",
            where_params=["federal"],
        )
        if effective_since is not None:
            console.print(
                f"[dim]forward-incremental: skipping bills introduced before "
                f"{effective_since.isoformat()}[/dim]"
            )
        stats = await ingest_federal_bills(
            db,
            parliament=parliament, session=session,
            all_sessions=all_sessions,
            limit=limit, delay_seconds=delay_secs,
            since=effective_since,
        )
        console.print(
            f"[green]ingest-federal-bills[/green]: "
            f"sessions={stats['sessions_touched']} bills={stats['bills']} "
            f"sponsors={stats['sponsors']} sponsors_linked={stats['sponsors_linked']} "
            f"skipped_older={stats.get('skipped_older', 0)}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("ingest-federal-bill-events")
@click.option("--parliament", type=int, default=None,
              help="Parliament number. Default: latest in legislative_sessions.")
@click.option("--session", type=int, default=None,
              help="Session number. Default: latest.")
@click.option("--all-sessions", is_flag=True,
              help="Walk every federal session in legislative_sessions.")
@click.pass_context
def cmd_ingest_federal_bill_events(
    ctx: click.Context, parliament, session, all_sessions,
) -> None:
    """Ingest federal bill stage events from parl.ca/LegisInfo XML.

    Closes the federal stage-timeline gap: openparliament.ca (the
    federal bills source) doesn't expose milestones, so prior to this
    command all 5,542 federal bills had 0 bill_events rows. One HTTP
    GET per session yields ~7 milestones per bill (1st/2nd/3rd reading
    in each chamber + royal assent). FK to bills.id via
    bills.raw->>'legisinfo_id'.

    Idempotent on bill_events_uniq (bill_id, stage, event_date,
    event_type, committee_name). Run after ingest-federal-bills so the
    legisinfo_id index is populated.
    """
    from .legislative.federal_bill_events import ingest_federal_bill_events

    async def _wrap(db: Database) -> None:
        stats = await ingest_federal_bill_events(
            db,
            parliament=parliament, session=session,
            all_sessions=all_sessions,
        )
        console.print(
            f"[green]ingest-federal-bill-events[/green]: "
            f"sessions={stats.sessions_touched}/{stats.sessions_touched + stats.sessions_skipped} "
            f"bills_seen={stats.bills_seen} matched={stats.bills_matched} "
            f"no_match={stats.bills_no_match} "
            f"events_attempted={stats.events_attempted} "
            f"inserted={stats.events_inserted} existing={stats.events_existing}"
        )
        if stats.by_stage:
            console.print(f"[dim]inserted by stage:[/dim] {stats.by_stage}")
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("relink-bill-introduced-dates")
@click.option("--levels", "levels_csv", type=str, default=None,
              help="Comma-separated list of levels (e.g. 'provincial,federal'). "
                   "Default: all.")
@click.option("--provinces", "provinces_csv", type=str, default=None,
              help="Comma-separated list of province/territory codes "
                   "(e.g. 'MB,NS'). Default: all.")
@click.pass_context
def cmd_relink_bill_introduced_dates(
    ctx: click.Context, levels_csv, provinces_csv,
) -> None:
    """Backfill bills.introduced_date from bill_events first_reading rows.

    Pure-SQL UPDATE pass — no upstream calls. Wherever a bill has at
    least one first_reading event but introduced_date IS NULL, set
    introduced_date to the earliest such event's date. Idempotent.

    Was conceived to close MB (81 bills) + NS (2,114 bills) gap where
    the events existed but the denormalised intro-date column was
    never populated. Generic across jurisdictions; safe to schedule
    daily after the ingest chain.
    """
    from .legislative.federal_bill_events import relink_bill_introduced_dates

    levels = [s.strip() for s in levels_csv.split(",")] if levels_csv else None
    provinces = (
        [s.strip().upper() for s in provinces_csv.split(",")] if provinces_csv else None
    )

    async def _wrap(db: Database) -> None:
        stats = await relink_bill_introduced_dates(
            db, levels=levels, provinces=provinces,
        )
        console.print(
            f"[green]relink-bill-introduced-dates[/green]: "
            f"candidates={stats.candidates} updated={stats.updated}"
        )
        if stats.by_jurisdiction:
            console.print(f"[dim]updated by jurisdiction:[/dim] {stats.by_jurisdiction}")
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("ingest-federal-hansard")
@click.option("--parliament", type=int, default=None,
              help="Parliament number (e.g. 44). Default: latest in legislative_sessions.")
@click.option("--session", type=int, default=None,
              help="Session number within the parliament (e.g. 1). Default: latest.")
@click.option("--since", type=str, default=None,
              help="Only fetch debates on/after this ISO date (YYYY-MM-DD).")
@click.option("--since-days", type=int, default=None,
              help="Forward-incremental: narrow --since to today - N days "
                   "(use in daily schedules to skip already-ingested sittings).")
@click.option("--until", type=str, default=None,
              help="Only fetch debates on/before this ISO date (YYYY-MM-DD).")
@click.option("--limit-debates", type=int, default=None,
              help="Cap on sitting days fetched.")
@click.option("--limit-speeches", type=int, default=None,
              help="Cap on TOTAL speeches ingested. Smoke-test friendly.")
@click.pass_context
def cmd_ingest_federal_hansard(
    ctx: click.Context, parliament, session, since, since_days, until,
    limit_debates, limit_speeches,
) -> None:
    """Ingest federal House of Commons speeches from openparliament.ca.

    Lands rows in `speeches` with attribution captured at-time-of-speech
    (party / constituency parsed from openparliament's attribution line).
    Idempotent via UNIQUE (source_system, source_url, sequence); re-runs
    over the same date range are safe and update mutable columns.

    When --parliament/--session are omitted, resolves the current session
    from legislative_sessions (populated by the bills ingester). Schedule
    bills before Hansard in the daily-ingest chain.
    """
    from datetime import date as _date, timedelta as _td
    from .legislative.federal_hansard import ingest as _ingest, federal_session_bounds
    from .legislative.current_session import current_session

    def _parse_d(s):
        return _date.fromisoformat(s) if s else None

    effective_since = _parse_d(since)
    effective_until = _parse_d(until)

    async def _wrap(db: Database) -> None:
        nonlocal parliament, session, effective_since, effective_until
        if parliament is None or session is None:
            parliament, session = await current_session(db, level="federal")
            console.print(
                f"[dim]auto-resolved current federal session: "
                f"P{parliament}-S{session}[/dim]"
            )

        # Auto-derive date bounds from the parliament/session if the caller
        # didn't provide explicit --since / --until. Without this, the
        # underlying /debates/ walk enumerates every Hansard sitting day
        # openparliament has indexed (back to 1994) and tags them all with
        # whichever session we named — which is how 896k speeches ended up
        # mis-labeled as P43-S2 on 2026-04-18. Explicit flags still win.
        if effective_since is None and effective_until is None:
            try:
                auto_since, auto_until = federal_session_bounds(parliament, session)
                effective_since = auto_since
                effective_until = auto_until
                console.print(
                    f"[dim]auto-deriving date range for P{parliament}-S{session}: "
                    f"{effective_since} → {effective_until}[/dim]"
                )
            except ValueError as exc:
                console.print(f"[red]{exc}[/red]")
                raise click.Abort()

        # Forward-incremental narrowing: clamp effective_since up to
        # today - since_days. Daily schedules pass since_days=14 to skip
        # already-ingested sittings; ad-hoc operators get the full
        # session-range default.
        if since_days is not None:
            cutoff = _date.today() - _td(days=int(since_days))
            if effective_since is None or cutoff > effective_since:
                effective_since = cutoff
                console.print(
                    f"[dim]forward-incremental: narrowed --since to "
                    f"{effective_since.isoformat()} (since_days={since_days})[/dim]"
                )

        stats = await _ingest(
            db,
            parliament=parliament,
            session=session,
            since=effective_since,
            until=effective_until,
            limit_debates=limit_debates,
            limit_speeches=limit_speeches,
        )
        console.print(
            f"[green]ingest-federal-hansard[/green]: "
            f"debates={stats.debates_scanned} seen={stats.speeches_seen} "
            f"inserted={stats.speeches_inserted} updated={stats.speeches_updated} "
            f"skipped_empty={stats.skipped_empty} "
            f"unresolved_slug={stats.speeches_unresolved}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("ingest-federal-committees")
@click.option("--parliament", type=int, default=None,
              help="Parliament number (e.g. 45). Default: latest in legislative_sessions.")
@click.option("--session", type=int, default=None,
              help="Session number within the parliament. Default: latest.")
@click.option("--since", type=str, default=None,
              help="Only fetch meetings on/after this ISO date (YYYY-MM-DD).")
@click.option("--since-days", type=int, default=None,
              help="Forward-incremental: narrow --since to today - N days "
                   "(use in daily schedules to skip already-ingested meetings).")
@click.option("--until", type=str, default=None,
              help="Only fetch meetings on/before this ISO date (YYYY-MM-DD).")
@click.option("--limit-meetings", type=int, default=None,
              help="Cap on meeting documents fetched.")
@click.option("--limit-speeches", type=int, default=None,
              help="Cap on TOTAL speeches ingested. Smoke-test friendly.")
@click.option("--include-in-camera", is_flag=True, default=False,
              help="Also enumerate in_camera=true meetings (rare — they almost "
                   "never have evidence published, so usually no rows land).")
@click.option("--all-sessions", is_flag=True, default=False,
              help="Historical backfill: walk every federal session in "
                   "legislative_sessions (P39+, the openparliament committee-"
                   "evidence floor), deriving date bounds per session. Ignored "
                   "when --parliament/--session are given; --since/--until/"
                   "--since-days are ignored in this mode.")
@click.pass_context
def cmd_ingest_federal_committees(
    ctx: click.Context, parliament, session, since, since_days, until,
    limit_meetings, limit_speeches, include_in_camera, all_sessions,
) -> None:
    """Ingest federal House of Commons committee evidence (transcripts).

    Lands rows in `speeches` with `speech_type='committee'` using the
    same openparliament fabric as `ingest-federal-hansard`. Witnesses
    (non-MP departmental officials, civil-society reps) land as rows
    with `politician_id=NULL` — same shape as unresolved floor speeches.

    Skips meetings with `has_evidence=false` (in-camera sessions or
    meetings pending transcription); daily `--since-days=14` runs
    re-visit recent meetings until their evidence lands upstream.

    Idempotent via UNIQUE (source_system, source_url, sequence); re-runs
    over the same date range are safe.
    """
    from datetime import date as _date, timedelta as _td
    from .legislative.federal_hansard import (
        ingest_committees as _ingest_committees,
        federal_session_bounds,
    )
    from .legislative.current_session import current_session

    def _parse_d(s):
        return _date.fromisoformat(s) if s else None

    effective_since = _parse_d(since)
    effective_until = _parse_d(until)

    async def _wrap(db: Database) -> None:
        nonlocal parliament, session, effective_since, effective_until

        # Historical-backfill walker: one ingest_committees() pass per federal
        # session row, each with its own federal_session_bounds()-derived date
        # window (same 896k-mis-tagging guardrail as the single-session path).
        # Mirrors ingest-federal-bills --all-sessions.
        if all_sessions and parliament is None and session is None:
            rows = await db.fetch(
                """
                SELECT parliament_number, session_number
                  FROM legislative_sessions
                 WHERE level='federal' AND province_territory IS NULL
                 ORDER BY parliament_number, session_number
                """
            )
            targets = [(r["parliament_number"], r["session_number"]) for r in rows]
            total_inserted = total_meetings = 0
            for p, s in targets:
                try:
                    w_since, w_until = federal_session_bounds(p, s)
                except ValueError as exc:
                    console.print(f"[yellow]skipping P{p}-S{s}: {exc}[/yellow]")
                    continue
                console.print(f"[dim]P{p}-S{s}: {w_since} → {w_until}[/dim]")
                stats = await _ingest_committees(
                    db,
                    parliament=p,
                    session=s,
                    since=w_since,
                    until=w_until,
                    limit_meetings=limit_meetings,
                    limit_speeches=limit_speeches,
                    include_in_camera=include_in_camera,
                )
                total_inserted += stats.speeches_inserted
                total_meetings += stats.meetings_scanned
                console.print(
                    f"[green]P{p}-S{s}[/green]: "
                    f"meetings={stats.meetings_scanned} "
                    f"inserted={stats.speeches_inserted} "
                    f"updated={stats.speeches_updated} "
                    f"unresolved_slug={stats.speeches_unresolved}"
                )
            console.print(
                f"[green]ingest-federal-committees --all-sessions[/green]: "
                f"sessions={len(targets)} meetings={total_meetings} "
                f"inserted={total_inserted}"
            )
            return

        if parliament is None or session is None:
            parliament, session = await current_session(db, level="federal")
            console.print(
                f"[dim]auto-resolved current federal session: "
                f"P{parliament}-S{session}[/dim]"
            )

        # Auto-derive date bounds from the parliament/session unless the
        # caller provided explicit --since / --until. Mirrors federal-hansard's
        # 896k-mis-tagging guardrail — without this the /committees/meetings/
        # walk would enumerate every meeting since openparliament's coverage
        # floor regardless of which session we named.
        if effective_since is None and effective_until is None:
            try:
                auto_since, auto_until = federal_session_bounds(parliament, session)
                effective_since = auto_since
                effective_until = auto_until
                console.print(
                    f"[dim]auto-deriving date range for P{parliament}-S{session}: "
                    f"{effective_since} → {effective_until}[/dim]"
                )
            except ValueError as exc:
                console.print(f"[red]{exc}[/red]")
                raise click.Abort()

        # Forward-incremental narrowing.
        if since_days is not None:
            cutoff = _date.today() - _td(days=int(since_days))
            if effective_since is None or cutoff > effective_since:
                effective_since = cutoff
                console.print(
                    f"[dim]forward-incremental: narrowed --since to "
                    f"{effective_since.isoformat()} (since_days={since_days})[/dim]"
                )

        stats = await _ingest_committees(
            db,
            parliament=parliament,
            session=session,
            since=effective_since,
            until=effective_until,
            limit_meetings=limit_meetings,
            limit_speeches=limit_speeches,
            include_in_camera=include_in_camera,
        )
        console.print(
            f"[green]ingest-federal-committees[/green]: "
            f"meetings={stats.meetings_scanned} seen={stats.speeches_seen} "
            f"inserted={stats.speeches_inserted} updated={stats.speeches_updated} "
            f"skipped_empty={stats.skipped_empty} "
            f"unresolved_slug={stats.speeches_unresolved}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("ingest-ab-hansard")
@click.option("--legislature", type=int, default=None,
              help="Alberta Legislature number (e.g. 31). Default: latest in legislative_sessions.")
@click.option("--session", type=int, default=None,
              help="Session within the legislature (e.g. 2). Default: latest.")
@click.option("--since", type=str, default=None,
              help="Only fetch sittings on/after this ISO date (YYYY-MM-DD).")
@click.option("--since-days", type=int, default=None,
              help="Forward-incremental: clamp --since to today - N days "
                   "(use in daily schedules).")
@click.option("--until", type=str, default=None,
              help="Only fetch sittings on/before this ISO date (YYYY-MM-DD).")
@click.option("--limit-sittings", type=int, default=None,
              help="Cap on sitting PDFs fetched (newest-first).")
@click.option("--limit-speeches", type=int, default=None,
              help="Cap on TOTAL speeches ingested. Smoke-test friendly.")
@click.pass_context
def cmd_ingest_ab_hansard(
    ctx: click.Context, legislature, session, since, since_days, until,
    limit_sittings, limit_speeches,
) -> None:
    """Ingest Alberta Hansard by parsing sitting PDFs from docs.assembly.ab.ca.

    When --legislature/--session are omitted, resolves the current session
    from legislative_sessions (populated by ingest-ab-bills).
    """
    from .legislative.ab_hansard import ingest as _ingest
    from .legislative.current_session import current_session
    from .legislative._forward import parse_iso_date, clamp_since_with_days

    effective_since = clamp_since_with_days(parse_iso_date(since), since_days)

    async def _wrap(db: Database) -> None:
        nonlocal legislature, session
        if legislature is None or session is None:
            legislature, session = await current_session(
                db, level="provincial", province_territory="AB",
            )
            console.print(
                f"[dim]auto-resolved current AB session: "
                f"L{legislature}-S{session}[/dim]"
            )
        if since_days is not None and effective_since is not None:
            console.print(
                f"[dim]forward-incremental: --since clamped to "
                f"{effective_since.isoformat()} (since_days={since_days})[/dim]"
            )
        stats = await _ingest(
            db,
            legislature=legislature,
            session=session,
            since=effective_since,
            until=parse_iso_date(until),
            limit_sittings=limit_sittings,
            limit_speeches=limit_speeches,
        )
        console.print(
            f"[green]ingest-ab-hansard[/green]: "
            f"sittings={stats.sittings_scanned} seen={stats.speeches_seen} "
            f"inserted={stats.speeches_inserted} updated={stats.speeches_updated} "
            f"skipped_empty={stats.skipped_empty} "
            f"resolved={stats.speeches_resolved} role_only={stats.speeches_role_only} "
            f"ambiguous={stats.speeches_ambiguous} unresolved={stats.speeches_unresolved}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("ingest-ab-committees")
@click.option("--legislature", type=int, default=None,
              help="Alberta Legislature number (e.g. 31). Default: latest in legislative_sessions.")
@click.option("--session", type=int, default=None,
              help="Session within the legislature (e.g. 2). Default: latest.")
@click.option("--since", type=str, default=None,
              help="Only fetch meetings on/after this ISO date (YYYY-MM-DD).")
@click.option("--since-days", type=int, default=None,
              help="Forward-incremental: clamp --since to today - N days "
                   "(use in daily schedules).")
@click.option("--until", type=str, default=None,
              help="Only fetch meetings on/before this ISO date (YYYY-MM-DD).")
@click.option("--limit-meetings", type=int, default=None,
              help="Cap on meeting PDFs fetched (newest-first across all committees).")
@click.option("--limit-speeches", type=int, default=None,
              help="Cap on TOTAL speeches ingested. Smoke-test friendly.")
@click.option("--committees", "committees", type=str, default=None,
              help="Optional comma-separated committee acronyms (e.g. 'HS,EF'). "
                   "Default: all 11 standing committees.")
@click.pass_context
def cmd_ingest_ab_committees(
    ctx: click.Context, legislature, session, since, since_days, until,
    limit_meetings, limit_speeches, committees,
) -> None:
    """Ingest Alberta standing-committee transcripts (PDFs from docs.assembly.ab.ca).

    Lands rows in `speeches` with `speech_type='committee'`. Speaker
    resolution prefers a committee-restricted lookup (MLAs who were
    members of the meeting's committee on the meeting date, sourced from
    `politician_committees`) and falls back to the chamber-wide lookup
    when the committee has no membership rows.

    Witnesses (non-MLA committee speakers — deputy ministers, industry
    reps, ATCO execs, etc.) land as `politician_id=NULL` rows with their
    raw honorific+surname preserved.

    When --legislature/--session are omitted, resolves the current AB
    session from legislative_sessions.
    """
    from .legislative.ab_committees import ingest_committees as _ingest_committees
    from .legislative.current_session import current_session
    from .legislative._forward import parse_iso_date, clamp_since_with_days

    effective_since = clamp_since_with_days(parse_iso_date(since), since_days)
    committees_list = (
        [c.strip() for c in committees.split(",") if c.strip()]
        if committees
        else None
    )

    async def _wrap(db: Database) -> None:
        nonlocal legislature, session
        if legislature is None or session is None:
            legislature, session = await current_session(
                db, level="provincial", province_territory="AB",
            )
            console.print(
                f"[dim]auto-resolved current AB session: "
                f"L{legislature}-S{session}[/dim]"
            )
        if since_days is not None and effective_since is not None:
            console.print(
                f"[dim]forward-incremental: --since clamped to "
                f"{effective_since.isoformat()} (since_days={since_days})[/dim]"
            )
        stats = await _ingest_committees(
            db,
            legislature=legislature,
            session=session,
            since=effective_since,
            until=parse_iso_date(until),
            limit_meetings=limit_meetings,
            limit_speeches=limit_speeches,
            committees=committees_list,
        )
        console.print(
            f"[green]ingest-ab-committees[/green]: "
            f"meetings={stats.meetings_scanned} seen={stats.speeches_seen} "
            f"inserted={stats.speeches_inserted} updated={stats.speeches_updated} "
            f"skipped_empty={stats.skipped_empty} fetch_failures={stats.fetch_failures} "
            f"resolved={stats.speeches_resolved} role_only={stats.speeches_role_only} "
            f"ambiguous={stats.speeches_ambiguous} unresolved={stats.speeches_unresolved} "
            f"roster_parsed={stats.attendees_parsed} "
            f"roster_resolved={stats.attendees_resolved} "
            f"roster_augmented={stats.attendees_augmented}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("ingest-bc-committees")
@click.option("--parliament", type=int, default=None,
              help="BC Parliament number (e.g. 43). Default: latest in legislative_sessions.")
@click.option("--session", type=int, default=None,
              help="Session within the parliament (e.g. 1). Default: latest.")
@click.option("--since", type=str, default=None,
              help="Only fetch meetings on/after this ISO date (YYYY-MM-DD).")
@click.option("--since-days", type=int, default=None,
              help="Forward-incremental: clamp --since to today - N days.")
@click.option("--until", type=str, default=None,
              help="Only fetch meetings on/before this ISO date (YYYY-MM-DD).")
@click.option("--limit-meetings", type=int, default=None,
              help="Cap on meetings fetched (newest-first).")
@click.option("--limit-speeches", type=int, default=None,
              help="Cap on TOTAL speeches ingested. Smoke-test friendly.")
@click.option("--committees", "committees", type=str, default=None,
              help="Optional comma-separated committee codes (e.g. 'fgs,cay'). "
                   "Default: all in seed file.")
@click.option("--seed-file", "seed_file", type=str, default=None,
              help="Seed JSON path (used with --use-seed). Default: "
                   "scripts/seeds/bc-committee-meetings.json")
@click.option("--use-seed", "use_seed", is_flag=True, default=False,
              help="Read the legacy operator-curated seed file instead of "
                   "discovering meetings from the pcms API.")
@click.option("--max-pages", "max_pages", type=int, default=None,
              help="Cap pcms discovery pages (50 meetings/page, date-desc; "
                   "~66 pages reach the 1996 floor). Default: walk until "
                   "--since or the floor.")
@click.pass_context
def cmd_ingest_bc_committees(
    ctx: click.Context, parliament, session, since, since_days, until,
    limit_meetings, limit_speeches, committees, seed_file, use_seed,
    max_pages,
) -> None:
    """Ingest BC standing-committee transcripts (HTML from lims.leg.bc.ca/hdms/file/Committees).

    Lands rows in `speeches` with `speech_type='committee'`. Meeting
    discovery walks the pcms REST API on api.lims.leg.bc.ca (every
    meeting back to 1996; see docs/research/british-columbia.md
    § Committee Activity). --use-seed switches back to the legacy
    operator-curated seed file at scripts/seeds/bc-committee-meetings.json.

    Speaker resolution is committee-restricted where politician_committees
    rows exist, chamber-wide fallback otherwise.

    When --parliament/--session are omitted, resolves the current BC
    session from legislative_sessions; each transcript URL's own
    {parl}{sess} path segment wins per-meeting.
    """
    from pathlib import Path as _Path
    from .legislative.bc_committees import (
        ingest_committees as _ingest_committees,
        DEFAULT_SEED_PATH,
    )
    from .legislative.current_session import current_session
    from .legislative._forward import parse_iso_date, clamp_since_with_days

    effective_since = clamp_since_with_days(parse_iso_date(since), since_days)
    committees_list = (
        [c.strip() for c in committees.split(",") if c.strip()]
        if committees
        else None
    )
    seed_path = _Path(seed_file) if seed_file else DEFAULT_SEED_PATH

    async def _wrap(db: Database) -> None:
        nonlocal parliament, session
        if parliament is None or session is None:
            parliament, session = await current_session(
                db, level="provincial", province_territory="BC",
            )
            console.print(
                f"[dim]auto-resolved current BC session: "
                f"P{parliament}-S{session}[/dim]"
            )
        if since_days is not None and effective_since is not None:
            console.print(
                f"[dim]forward-incremental: --since clamped to "
                f"{effective_since.isoformat()} (since_days={since_days})[/dim]"
            )
        stats = await _ingest_committees(
            db,
            parliament=parliament,
            session=session,
            since=effective_since,
            until=parse_iso_date(until),
            limit_meetings=limit_meetings,
            limit_speeches=limit_speeches,
            committees=committees_list,
            seed_path=seed_path,
            use_seed=use_seed,
            max_pages=max_pages,
        )
        console.print(
            f"[green]ingest-bc-committees[/green]: "
            f"meetings={stats.meetings_scanned} seen={stats.speeches_seen} "
            f"inserted={stats.speeches_inserted} updated={stats.speeches_updated} "
            f"skipped_empty={stats.skipped_empty} "
            f"fetch_failures={stats.fetch_failures} "
            f"parse_errors={stats.parse_errors} "
            f"resolved={stats.speeches_resolved} "
            f"presiding={stats.speeches_presiding} "
            f"role_only={stats.speeches_role_only} "
            f"ambiguous={stats.speeches_ambiguous} "
            f"unresolved={stats.speeches_unresolved} "
            f"visiting_mla={stats.speeches_visiting_mla} "
            f"members_parsed={stats.members_parsed} "
            f"members_resolved={stats.members_resolved} "
            f"members_inserted={stats.members_inserted} "
            f"members_updated={stats.members_updated}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("ingest-bc-vp-votes")
@click.option("--parliament", "parliaments", type=int, multiple=True,
              help="Restrict to specific BC parliament number(s) (e.g. 42). "
                   "Repeatable. Default: all P35+ (the digital floor).")
@click.option("--since", type=str, default=None,
              help="Only process sittings on/after this ISO date.")
@click.option("--since-days", type=int, default=None,
              help="Forward-incremental: clamp --since to today - N days.")
@click.option("--limit-docs", type=int, default=None,
              help="Cap on V&P documents fetched (smoke-test friendly).")
@click.pass_context
def cmd_ingest_bc_vp_votes(
    ctx: click.Context, parliaments, since, since_days, limit_docs,
) -> None:
    """Ingest BC recorded divisions from Votes & Proceedings (pdms).

    Walks lims.leg.bc.ca/pdms/votes-and-proceedings/{parl}{sess} listings
    (P35/1992 → present, the digital floor), fetches each sitting's V&P
    document, parses recorded-division tables (Yeas/Nays with member
    surnames), and lands `votes` (source_system='votes-bc-vp') +
    `vote_positions` with date-windowed surname resolution. Idempotent.

    Coexists with extract-bc-votes (Hansard-regex, consensus-shape);
    distinct source_system keeps the two auditable.
    """
    from .legislative.bc_vp_votes import ingest_bc_vp_votes
    from .legislative._forward import parse_iso_date, clamp_since_with_days

    effective_since = clamp_since_with_days(parse_iso_date(since), since_days)

    async def _wrap(db: Database) -> None:
        stats = await ingest_bc_vp_votes(
            db,
            parliaments=list(parliaments) or None,
            since=effective_since,
            limit_docs=limit_docs,
        )
        d = stats.as_dict()
        console.print(
            f"[green]ingest-bc-vp-votes[/green]: "
            f"sessions={d['sessions']} docs={d['docs_fetched']} "
            f"with_divisions={d['docs_with_divisions']} "
            f"votes_inserted={d['votes_inserted']} "
            f"votes_updated={d['votes_updated']} "
            f"positions={d['positions']} "
            f"resolved={d['positions_resolved']} "
            f"bills_linked={d['bills_linked']} "
            f"fetch_failures={d['fetch_failures']}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("ingest-bc-committee-membership")
@click.option("--parliament", type=int, default=None,
              help="Historical mode: BC parliament number (e.g. 42) — lands "
                   "DATED politician_committees rows bounded by that "
                   "parliament's session range, for the date-aware restricted "
                   "lookup used by the transcript backfill. Default: current "
                   "parliament (open rows + soft-close).")
@click.pass_context
def cmd_ingest_bc_committee_membership(ctx: click.Context, parliament) -> None:
    """Sync BC committee membership (pcms API → politician_committees).

    Fetches api.lims.leg.bc.ca/pcms/committees/membership (or the
    /{parliament}/membership variant with --parliament) and upserts one
    politician_committees row per (member, committee) with role Chair /
    Deputy Chair / Convener / Member. Resolution is an exact FK join on
    politicians.lims_member_id (the API's memberByMemberId.id is the same
    identifier space); name-based fallback only when the local row lacks
    a LIMS id. pcms-sourced open rows whose member dropped off the
    upstream roster are soft-closed. Enables the committee-restricted
    speaker lookup in ingest-bc-committees (witness-rejection).
    """
    from .legislative.bc_committees import ingest_bc_committee_membership

    async def _wrap(db: Database) -> None:
        stats = await ingest_bc_committee_membership(db, parliament=parliament)
        colour = "yellow" if stats.unresolved else "green"
        console.print(
            f"[{colour}]ingest-bc-committee-membership[/{colour}]: "
            f"committees={stats.committees_seen} members={stats.members_seen} "
            f"resolved_by_lims_id={stats.resolved_by_lims_id} "
            f"resolved_by_name={stats.resolved_by_name} "
            f"unresolved={stats.unresolved} "
            f"inserted={stats.rows_inserted} updated={stats.rows_updated} "
            f"closed={stats.rows_closed}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("check-bc-committees-freshness")
@click.option("--threshold-days", type=int, default=21,
              help="Days stale at which to flag a committee. Default: 21.")
@click.option("--alert-to", type=str, default=None,
              help="Override email recipient. Default: $CPD_OPS_EMAIL or admin@thebunkerops.ca.")
@click.option("--always-email", is_flag=True, default=False,
              help="Send email even when no committees are stale (audit cadence).")
@click.pass_context
def cmd_check_bc_committees_freshness(
    ctx: click.Context, threshold_days, alert_to, always_email,
) -> None:
    """Dead-canary: report BC standing-committee freshness (days since last meeting per code).

    BC has no auto-discovery API; the seed file at scripts/seeds/
    bc-committee-meetings.json is hand-curated. If the operator forgets to
    add new meetings, daily-cron silently no-ops over the same N URLs
    forever. This command makes the staleness loud — prints a per-
    committee table to stdout (captured by the admin Jobs page) and
    emails the operator when any active committee crosses the threshold.

    The report is a CANARY not an SLA: BC committees have varied
    cadences (FGS budget-tour bursts, CAY monthly, DEM weekly during
    inquiry, dormant during recess). The operator decides whether a
    flagged staleness is a real gap or just recess.
    """
    from .legislative.bc_committees import check_freshness_and_alert

    async def _wrap(db: Database) -> None:
        rows, emailed = await check_freshness_and_alert(
            db,
            threshold_days=threshold_days,
            alert_to=alert_to,
            always_email=always_email,
        )
        from .legislative.bc_committees import stale_committees as _stale
        stale = _stale(rows, threshold_days)
        console.print(
            f"[green]check-bc-committees-freshness[/green]: "
            f"committees={len(rows)} stale={len(stale)} "
            f"threshold_days={threshold_days} emailed={emailed}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


def _print_problems(problems: list, show: int = 10) -> None:
    """Print boundary-loader problems, always disclosing the total.

    ⚠ The previous form was `for p in problems[:10]` with no count, so a run
    with 400 rejections looked identical to one with 10. A truncation that hides
    how much it truncated is worse than no output.
    """
    if not problems:
        return
    console.print(f"[yellow]problems[/yellow]: {len(problems)}")
    for p in problems[:show]:
        console.print(f"[dim]  - {p}[/dim]")
    if len(problems) > show:
        console.print(f"[dim]  … and {len(problems) - show} more[/dim]")


@cli.command("load-boundaries")
@click.option("--jurisdiction", type=str, default=None,
              help="Registry key from boundary_loader.SPECS (e.g. 'ontario'). "
                   "Omit only when --spec-file is given.")
@click.option("--spec-file", "spec_file", type=str, default=None,
              help="Path to a standalone Python file defining SPEC = "
                   "BoundarySpec(...). Used instead of the SPECS registry so a "
                   "spec can be drafted and --compare'd without editing the "
                   "shared registry — which is what lets several jurisdictions "
                   "be worked on at once without stepping on each other.")
@click.option("--data-root", type=str, default="/data/boundaries",
              help="Root of the staged boundary tree inside the container.")
@click.option("--dry-run", is_flag=True,
              help="Parse, reconcile and report without writing.")
@click.option("--compare", is_flag=True,
              help="Ruling A7 vintage check: measure the staged authoritative "
                   "geometry against what we already hold, without writing. A "
                   "matching district count proves nothing — only overlap does.")
@click.pass_context
def cmd_load_boundaries(
    ctx: click.Context, jurisdiction: Optional[str], spec_file: Optional[str],
    data_root: str, dry_run: bool, compare: bool,
) -> None:
    """Load authoritative electoral boundaries for one jurisdiction.

    Boundary-first: unlike the Open North path this does not require a sitting
    representative to exist before a district gets a polygon. Reprojects via
    PostGIS from the spec's DECLARED source EPSG — never ST_SetSRID.

    A rejected geometry aborts the run rather than logging and continuing.
    """
    from .legislative.boundary_loader import (
        SPECS, compare_boundaries, load_boundaries,
    )

    if spec_file:
        # A draft spec living outside the registry. The file is executed with
        # boundary_loader's namespace pre-populated, so it can name BoundarySpec
        # and date() without importing them.
        import runpy
        from datetime import date as _date
        from .legislative import boundary_loader as _bl

        ns = dict(vars(_bl))
        ns["date"] = _date
        try:
            result = runpy.run_path(spec_file, init_globals=ns)
        except FileNotFoundError:
            raise SystemExit(f"--spec-file: no such file {spec_file!r}")
        spec = result.get("SPEC")
        if spec is None or not isinstance(spec, _bl.BoundarySpec):
            raise SystemExit(
                f"--spec-file {spec_file!r} must define SPEC = BoundarySpec(...)"
            )
        if jurisdiction and jurisdiction != spec.jurisdiction:
            raise SystemExit(
                f"--jurisdiction {jurisdiction!r} contradicts the spec file's "
                f"{spec.jurisdiction!r}"
            )
        console.print(
            f"[dim]using draft spec from {spec_file} "
            f"(jurisdiction={spec.jurisdiction})[/dim]"
        )
    else:
        if not jurisdiction:
            raise SystemExit("give either --jurisdiction or --spec-file")
        spec = SPECS.get(jurisdiction)
        if spec is None:
            raise SystemExit(
                f"unknown jurisdiction {jurisdiction!r}. "
                f"Known: {', '.join(sorted(SPECS))}"
            )

    async def _wrap(db: Database) -> None:
        if compare:
            c = await compare_boundaries(db, spec, data_root=data_root)
            console.print(
                f"[green]load-boundaries --compare[/green]: "
                f"jurisdiction={c.jurisdiction} authoritative={c.authoritative} "
                f"held={c.held} matched={c.matched} "
                f"mean_overlap={c.mean_overlap:.4%} min={c.min_overlap:.4%} "
                f"below_95%={c.below_95}"
            )
            if c.only_authoritative:
                console.print(
                    f"[yellow]absent from our table[/yellow] "
                    f"({len(c.only_authoritative)}): "
                    f"{', '.join(c.only_authoritative[:8])}"
                )
            if c.only_held:
                console.print(
                    f"[yellow]we hold, authority does not[/yellow] "
                    f"({len(c.only_held)}): {', '.join(c.only_held[:8])}"
                )
            if c.worst:
                console.print("[dim]lowest-overlap districts:[/dim] " + ", ".join(
                    f"{n} {v:.2%}" for n, v in c.worst))
            # The grouping that produced `authoritative` can reject or filter
            # features. Reporting it here is what makes --compare a real
            # rehearsal of the load rather than a geometry-only check.
            if c.rejected or c.filtered_out:
                console.print(
                    f"[yellow]grouping[/yellow]: rejected={c.rejected} "
                    f"filtered_out={c.filtered_out}"
                )
            _print_problems(c.problems)
            return
        st = await load_boundaries(db, spec, data_root=data_root, dry_run=dry_run)
        console.print(
            f"[green]load-boundaries[/green]: jurisdiction={st.jurisdiction} "
            f"features={st.features_read} districts={st.distinct_ids} "
            f"inserted={st.inserted} updated={st.updated} rejected={st.rejected} "
            f"filtered_out={st.filtered_out} parts_merged={st.parts_merged} "
            + (f"name_fixups={st.name_fixups_applied} "
               if spec.name_fixups else "") +
            f"slug_matches_existing={st.slug_matches_existing} slug_new={st.slug_new} "
            # ⚠ Ontario declares src_proj4 and no EPSG, so printing src_epsg
            # alone rendered `epsg=None` with no mention of the CRS actually used.
            f"crs={spec.src_epsg if spec.src_epsg else 'proj4'} "
            f"version={spec.boundaries_version}"
            + (" [yellow](dry run)[/yellow]" if dry_run else "")
        )
        if st.features_read != st.distinct_ids:
            console.print(
                f"[yellow]note[/yellow]: {st.features_read} features collapsed to "
                f"{st.distinct_ids} districts (multi-part districts merged)."
            )
        _print_problems(st.problems)
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("ingest-nar-postcodes")
@click.option("--zip-path", "zip_path", type=str,
              default="/data/boundaries/_geocoding/nar/202606.zip",
              help="Path to the staged StatCan NAR archive. The compose file "
                   "mounts ./data at /data (read-only), so the repo path "
                   "data/boundaries/... is /data/boundaries/... in-container.")
@click.option("--provinces", "provinces_csv", type=str, default=None,
              help="Comma-separated StatCan PR codes (e.g. '35,24'). Default: all 13.")
@click.option("--vintage", type=str, default=None,
              help="NAR release tag recorded on each row. Default: the zip's stem.")
@click.option("--dry-run", is_flag=True,
              help="Parse and report counts without writing.")
@click.pass_context
def cmd_ingest_nar_postcodes(
    ctx: click.Context, zip_path: str, provinces_csv: Optional[str],
    vintage: Optional[str], dry_run: bool,
) -> None:
    """Build postcode_centroids from the StatCan National Address Register.

    Replaces the Open North geocode, which has been down since 2026-08-07.
    Idempotent per province (upsert on postcode), so a single province can be
    refreshed without disturbing the rest.

    ~5 min and ~1 GB RSS for all 13 provinces; Ontario alone is ~40 s.
    """
    from .legislative.nar_postcodes import ingest_nar_postcodes

    provinces = (
        [s.strip() for s in provinces_csv.split(",")] if provinces_csv else None
    )

    async def _wrap(db: Database) -> None:
        st = await ingest_nar_postcodes(
            db, zip_path=zip_path, provinces=provinces,
            vintage=vintage, dry_run=dry_run,
        )
        miss_pct = (100.0 * st.no_geometry / st.address_rows) if st.address_rows else 0.0
        console.print(
            f"[green]ingest-nar-postcodes[/green]: "
            f"provinces={st.provinces} postcodes={st.postcodes:,} "
            f"written={st.written:,} rural={st.rural_postcodes:,} "
            f"address_rows={st.address_rows:,} no_geometry={st.no_geometry:,} "
            f"({miss_pct:.2f}%) reppoint_fallbacks={st.reppoint_fallbacks:,}"
            + (" [yellow](dry run)[/yellow]" if dry_run else "")
        )
        if st.by_province:
            console.print(f"[dim]postcodes by province:[/dim] {st.by_province}")
        # The reppoint fallback is load-bearing: without it Ontario loses 12.9%
        # of address rows. A sudden drop to zero means the column moved.
        if st.address_rows and miss_pct > 5.0:
            console.print(
                f"[yellow]warning[/yellow]: {miss_pct:.1f}% of address rows had no "
                f"resolvable geometry (expected <1%). Check BG_/BF_REPPOINT_ columns."
            )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("ingest-qc-municipal-roster")
@click.option("--csv-path", type=str,
              default="/data/rosters/quebec-municipal/current/Elec2025_Mun.csv",
              help="Staged MAMH general-election results CSV.")
@click.option("--dry-run", is_flag=True, help="Report without writing.")
@click.pass_context
def cmd_ingest_qc_municipal_roster(ctx, csv_path: str, dry_run: bool) -> None:
    """Rebuild the Québec municipal roster from the 2025 election results.

    ⛔ Replaces the Open North municipal roster for Québec, which is a full
    election cycle stale — it still served Valérie Plante as mayor of Montréal
    9½ months after she left office. Open North is up but unmaintained, so
    re-running `ingest-all-councils` cannot fix it.

    Source: Ministère des Affaires municipales, CC-BY, one province-wide CSV.
    """
    from .legislative.qc_municipal_roster import ingest_qc_municipal_roster

    async def _wrap(db: Database) -> None:
        st = await ingest_qc_municipal_roster(db, csv_path=csv_path, dry_run=dry_run)
        console.print(
            f"[green]ingest-qc-municipal-roster[/green]: "
            f"councils={st.municipalities} winners={st.winners} "
            f"inserted={st.inserted} rekeyed={st.rekeyed} updated={st.updated} "
            f"deactivated={st.deactivated} attached={st.attached} "
            f"unattached={st.unattached}"
            + (" [yellow](dry run)[/yellow]" if dry_run else "")
        )
        _print_problems(st.problems)
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("reattach-municipal-roster")
@click.option("--council", type=str, default=None,
              help="Limit to one council slug (the middle field of source_id).")
@click.option("--dry-run", is_flag=True, help="Report without writing.")
@click.pass_context
def cmd_reattach_municipal_roster(ctx: click.Context, council, dry_run: bool) -> None:
    """Re-link municipal rosters to geometry a cutover re-keyed underneath them.

    ⛔ A boundary cutover renames the source_set and re-keys constituency_id.
    The roster joins on that id and nothing in the cutover touches it, so every
    cutover silently severs its council. Run this after any municipal cutover.

    Matches a WHOLE COUNCIL at a time, never one member: `Ward 1` exists in
    hundreds of sets, but {Ward 1 … Ward 14} identifies exactly one. Refuses on
    a tie or a partial cover rather than guessing — see 0089, where a Gatineau
    councillor was attached to a Québec City district 400 km away.
    """
    from .legislative.municipal_reattach import reattach_municipal_roster

    async def _wrap(db: Database) -> None:
        st = await reattach_municipal_roster(db, council=council, dry_run=dry_run)
        console.print(
            f"[green]reattach-municipal-roster[/green]: "
            f"councils_examined={st.councils_examined} "
            f"matched={st.councils_matched} attached={st.attached}"
            + (" [yellow](dry run)[/yellow]" if dry_run else "")
        )
        _print_problems(st.problems)
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("check-boundary-coverage")
@click.option("--no-area", is_flag=True,
              help="Skip the area-drift half. Use immediately after a "
                   "deliberate re-load, before BASELINES is updated.")
@click.pass_context
def cmd_check_boundary_coverage(ctx: click.Context, no_area: bool) -> None:
    """Sentinel: does every jurisdiction's electoral geography still add up?

    Checks district count against the agency seat count, roster size against
    seats, unattached members, orphaned constituency_ids, and area drift.

    ⚠ A shortfall of members is a VACANCY and is reported, not failed — Ontario
    legitimately sits 2 short today. Only an EXCESS is a breach, because that
    means duplicate rows. Exits non-zero on any breach so the scheduled run
    surfaces as a FAILED job in the admin panel.
    """
    from .legislative.boundary_coverage import (
        check_boundary_coverage, check_municipal_integrity, check_pending_flips,
    )

    async def _wrap(db: Database) -> None:
        rows = await check_boundary_coverage(db, check_area=not no_area)
        breaches = [r for r in rows if r.breached]
        for r in rows:
            marker = "[red]BREACH[/red]" if r.breached else "[green]ok[/green]"
            vac = f" vacancies={r.vacancies}" if r.vacancies else ""
            frz = (f" [yellow]frozen={r.roster_frozen}"
                   f"@{r.roster_stale_days}d[/yellow]") if r.roster_frozen else ""
            console.print(
                f"{marker} {r.level}/{r.jurisdiction}: districts={r.districts} "
                f"seats={r.seats} members={r.actives} attached={r.attached}{vac}{frz}"
            )
            for b in r.breaches:
                console.print(f"[red]    - {b}[/red]")
        # ⚠ Municipal is checked PER SEAT, not per polygon — a council is
        # mayors + ward councillors + at-large councillors + boroughs, so
        # `districts == seats` has no municipal analogue. See the module.
        muni_all = await check_municipal_integrity(db)
        # Advisories are coverage gaps — reported, never failed. See the
        # MunicipalProblem docstring for why the two do not share a severity.
        muni = [m for m in muni_all if not m.advisory]
        for m in muni_all:
            tag = ("[yellow]gap[/yellow]" if m.advisory else "[red]BREACH[/red]")
            console.print(f"{tag} municipal/{m.kind} ×{m.count}: {m.detail}")
        if not muni_all:
            console.print("[green]ok[/green] municipal: per-seat integrity clean")

        # Flips are dated rows already in the table, not events that happen
        # to us. Reported, never a breach — it is what the report SAYS (a
        # member about to detach, a seat count about to disagree) that needs
        # acting on, and always before the date, never after.
        flips = await check_pending_flips(db)
        for f in flips:
            colour = "red" if f.orphans else "yellow"
            console.print(f"[{colour}]flip[/{colour}] {f.describe()}")
        if not flips:
            console.print("[green]ok[/green] no boundary generation flips in the next 60 days")

        total_vac = sum(r.vacancies for r in rows)
        console.print(
            f"check-boundary-coverage: jurisdictions={len(rows)} "
            f"breaches={len(breaches)} vacancies={total_vac} "
            f"municipal_problems={len(muni)} "
            f"pending_flips={len(flips)} "
            f"roster_frozen={sum(r.roster_frozen for r in rows)}"
        )
        if breaches or muni:
            raise SystemExit(
                f"check-boundary-coverage: {len(breaches)} jurisdiction(s) "
                f"breached {[r.level + '/' + r.jurisdiction for r in breaches]} "
                f"and {len(muni)} municipal problem class(es) "
                f"{[m.kind for m in muni]}. A district count that matches its "
                f"seat count proves nothing on its own — read the lines above."
            )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("check-ingest-freshness")
@click.option("--threshold-days", type=int, default=None,
              help="Default breach threshold in days for jurisdictions "
                   "without a publication-lag override. Default: 30.")
@click.pass_context
def cmd_check_ingest_freshness(ctx: click.Context, threshold_days) -> None:
    """Sentinel: flag jurisdictions whose speeches lag their bill events.

    Bill events and Hansard come from different upstream surfaces, so a
    recess quiets both while a broken Hansard pipeline shows bills
    advancing with no speeches behind them. Exits non-zero on any breach
    so the weekly run surfaces as a FAILED job in the admin panel — the
    counter to "succeeded with sittings=0" holes (QC/NB/NU, 2026-08-02).
    """
    from .legislative.freshness import (
        DEFAULT_THRESHOLD_DAYS,
        check_ingest_freshness,
    )

    effective_threshold = (
        threshold_days if threshold_days is not None else DEFAULT_THRESHOLD_DAYS
    )

    async def _wrap(db: Database) -> None:
        rows = await check_ingest_freshness(
            db, threshold_days=effective_threshold,
        )
        breaches = [r for r in rows if r.breached]
        for r in rows:
            marker = "[red]BREACH[/red]" if r.breached else "[green]ok[/green]"
            console.print(
                f"{marker} {r.jurisdiction}: latest_speech={r.latest_speech} "
                f"latest_bill_event={r.latest_bill_event} "
                f"lag={r.lag_days}d threshold={r.threshold_days}d"
            )
        console.print(
            f"check-ingest-freshness: jurisdictions={len(rows)} "
            f"breaches={len(breaches)}"
        )
        if breaches:
            raise SystemExit(
                f"check-ingest-freshness: {len(breaches)} jurisdiction(s) "
                f"breached: {[r.jurisdiction for r in breaches]} — a Hansard "
                f"pipeline is likely silently broken; run its ingest with a "
                f"wide --since and check session auto-resolution."
            )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("ingest-bc-hansard")
@click.option("--parliament", type=int, default=None,
              help="BC Parliament number (e.g. 43). Default: latest in legislative_sessions.")
@click.option("--session", type=int, default=None,
              help="Session within the parliament (e.g. 2). Default: latest.")
@click.option("--since", type=str, default=None,
              help="Only fetch sittings on/after this ISO date (YYYY-MM-DD).")
@click.option("--since-days", type=int, default=None,
              help="Forward-incremental: clamp --since to today - N days "
                   "(use in daily schedules).")
@click.option("--until", type=str, default=None,
              help="Only fetch sittings on/before this ISO date (YYYY-MM-DD).")
@click.option("--limit-sittings", type=int, default=None,
              help="Cap on sittings processed (newest-first when capped).")
@click.option("--limit-speeches", type=int, default=None,
              help="Cap on TOTAL speeches ingested. Smoke-test friendly.")
@click.option("--url", "one_off_url", type=str, default=None,
              help="Bypass discovery and ingest a single sitting URL directly. "
                   "Useful for smoke-testing the parser on a known file.")
@click.pass_context
def cmd_ingest_bc_hansard(
    ctx: click.Context, parliament, session, since, since_days, until,
    limit_sittings, limit_speeches, one_off_url,
) -> None:
    """Ingest BC Hansard from LIMS HDMS (Blues + Final HTML → speeches).

    When --parliament/--session are omitted, resolves the current session
    from legislative_sessions (populated by ingest-bc-bills).
    """
    from .legislative.bc_hansard import ingest as _ingest
    from .legislative.current_session import current_session
    from .legislative._forward import parse_iso_date, clamp_since_with_days

    effective_since = clamp_since_with_days(parse_iso_date(since), since_days)

    async def _wrap(db: Database) -> None:
        nonlocal parliament, session
        if (parliament is None or session is None) and one_off_url is None:
            parliament, session = await current_session(
                db, level="provincial", province_territory="BC",
            )
            console.print(
                f"[dim]auto-resolved current BC session: "
                f"P{parliament}-S{session}[/dim]"
            )
        if since_days is not None and effective_since is not None:
            console.print(
                f"[dim]forward-incremental: --since clamped to "
                f"{effective_since.isoformat()} (since_days={since_days})[/dim]"
            )
        stats = await _ingest(
            db,
            parliament=parliament,
            session=session,
            since=effective_since,
            until=parse_iso_date(until),
            limit_sittings=limit_sittings,
            limit_speeches=limit_speeches,
            one_off_url=one_off_url,
        )
        console.print(
            f"[green]ingest-bc-hansard[/green]: "
            f"sittings={stats.sittings_scanned} seen={stats.speeches_seen} "
            f"inserted={stats.speeches_inserted} updated={stats.speeches_updated} "
            f"skipped_empty={stats.skipped_empty} parse_errors={stats.parse_errors} "
            f"resolved={stats.speeches_resolved} presiding={stats.speeches_presiding} "
            f"role_only={stats.speeches_role_only} ambiguous={stats.speeches_ambiguous} "
            f"unresolved={stats.speeches_unresolved}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("resolve-bc-speakers")
@click.option("--limit", type=int, default=None,
              help="Cap speeches scanned (smoke-test aid).")
@click.pass_context
def cmd_resolve_bc_speakers(ctx: click.Context, limit: Optional[int]) -> None:
    """Re-resolve politician_id on BC speeches with NULL politician_id.

    Run after expanding the BC MLA roster, fixing name-normalization, or
    enriching lims_member_id on previously-unlinked politicians. Idempotent.
    """
    from .legislative.bc_hansard import resolve_bc_speakers as _resolve

    async def _wrap(db: Database) -> None:
        stats = await _resolve(db, limit=limit)
        console.print(
            f"[green]resolve-bc-speakers[/green]: "
            f"scanned={stats.speeches_scanned} updated={stats.speeches_updated} "
            f"still_unresolved={stats.still_unresolved}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("resolve-bc-speakers-dated")
@click.option("--limit", type=int, default=None,
              help="Cap candidate speeches scanned (smoke-test aid).")
@click.pass_context
def cmd_resolve_bc_speakers_dated(
    ctx: click.Context, limit: Optional[int],
) -> None:
    """Date-windowed BC speaker resolver: joins NULL-politician_id
    speeches against politician_terms whose date span covers s.spoken_at,
    with cand_count=1 gate.

    Mirrors resolve-mb-speakers-dated / resolve-qc-speakers-dated but
    extracts the surname inline from speaker_name_raw (last
    whitespace-separated token, lower+unaccent) — BC parser doesn't
    pre-stash a surname field in raw. Rows where speaker_role IS NOT NULL
    are skipped (those are presiding/role rows handled by
    resolve-presiding-speakers --province BC).

    Run after ingest-bc-former-mlas + enrich-bc-member-parliaments land
    pre-P35 historical MLAs and per-parliament terms. Idempotent.
    """
    from .legislative.bc_hansard import resolve_bc_speakers_dated as _resolve

    async def _wrap(db: Database) -> None:
        stats = await _resolve(db, limit=limit)
        console.print(
            f"[green]resolve-bc-speakers-dated[/green]: "
            f"scanned={stats.speeches_scanned} updated={stats.speeches_updated} "
            f"still_ambiguous={stats.still_unresolved}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("ingest-qc-hansard")
@click.option("--parliament", type=int, default=None,
              help="QC parliament (législature) number. Default: latest in legislative_sessions.")
@click.option("--session", type=int, default=None,
              help="Session within the parliament. Default: latest.")
@click.option("--since", type=str, default=None,
              help="Only fetch sittings on/after this ISO date (YYYY-MM-DD).")
@click.option("--since-days", type=int, default=None,
              help="Forward-incremental: clamp --since to today - N days "
                   "(use in daily schedules).")
@click.option("--until", type=str, default=None,
              help="Only fetch sittings on/before this ISO date (YYYY-MM-DD).")
@click.option("--limit-sittings", type=int, default=None,
              help="Cap on sittings processed (newest-first when capped).")
@click.option("--limit-speeches", type=int, default=None,
              help="Cap on TOTAL speeches ingested. Smoke-test friendly.")
@click.option("--url", "one_off_url", type=str, default=None,
              help="Bypass discovery and ingest a single transcript URL directly.")
@click.pass_context
def cmd_ingest_qc_hansard(
    ctx: click.Context, parliament, session, since, since_days, until,
    limit_sittings, limit_speeches, one_off_url,
) -> None:
    """Ingest Quebec Journal des débats (HTML) → speeches table.

    When --parliament/--session are omitted, resolves the current session
    from legislative_sessions (populated by ingest-qc-bills).
    """
    from .legislative.qc_hansard import ingest as _ingest
    from .legislative.current_session import current_session
    from .legislative._forward import parse_iso_date, clamp_since_with_days

    effective_since = clamp_since_with_days(parse_iso_date(since), since_days)

    async def _wrap(db: Database) -> None:
        nonlocal parliament, session
        if (parliament is None or session is None) and one_off_url is None:
            parliament, session = await current_session(
                db, level="provincial", province_territory="QC",
            )
            console.print(
                f"[dim]auto-resolved current QC session: "
                f"P{parliament}-S{session}[/dim]"
            )
        if since_days is not None and effective_since is not None:
            console.print(
                f"[dim]forward-incremental: --since clamped to "
                f"{effective_since.isoformat()} (since_days={since_days})[/dim]"
            )
        stats = await _ingest(
            db,
            parliament=parliament,
            session=session,
            since=effective_since,
            until=parse_iso_date(until),
            limit_sittings=limit_sittings,
            limit_speeches=limit_speeches,
            one_off_url=one_off_url,
        )
        console.print(
            f"[green]ingest-qc-hansard[/green]: "
            f"sittings={stats.sittings_scanned} seen={stats.speeches_seen} "
            f"inserted={stats.speeches_inserted} updated={stats.speeches_updated} "
            f"skipped_empty={stats.skipped_empty} parse_errors={stats.parse_errors} "
            f"resolved={stats.speeches_resolved} role_only={stats.speeches_role_only} "
            f"ambiguous={stats.speeches_ambiguous} unresolved={stats.speeches_unresolved}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("ingest-mb-hansard")
@click.option("--parliament", type=int, default=None,
              help="MB parliament (legislature) number. Default: latest in legislative_sessions.")
@click.option("--session", type=int, default=None,
              help="Session within the legislature. Default: latest.")
@click.option("--since", type=str, default=None,
              help="Only ingest sittings on/after this ISO date (YYYY-MM-DD).")
@click.option("--since-days", type=int, default=None,
              help="Forward-incremental: clamp --since to today - N days "
                   "(use in daily schedules).")
@click.option("--until", type=str, default=None,
              help="Only ingest sittings on/before this ISO date (YYYY-MM-DD).")
@click.option("--limit-sittings", type=int, default=None,
              help="Cap on sittings processed (newest-first when capped).")
@click.option("--limit-speeches", type=int, default=None,
              help="Cap on TOTAL speeches ingested. Smoke-test friendly.")
@click.option("--url", "one_off_url", type=str, default=None,
              help="Bypass discovery and ingest a single transcript URL directly.")
@click.pass_context
def cmd_ingest_mb_hansard(
    ctx: click.Context, parliament, session, since, since_days, until,
    limit_sittings, limit_speeches, one_off_url,
) -> None:
    """Ingest Manitoba Hansard (Word-exported HTML) → speeches table.

    When --parliament/--session are omitted, resolves the current session
    from legislative_sessions (populated by ingest-mb-bills).
    """
    from .legislative.current_session import current_session
    from .legislative._forward import parse_iso_date, clamp_since_with_days

    effective_since = clamp_since_with_days(parse_iso_date(since), since_days)

    async def _wrap(db: Database) -> None:
        nonlocal parliament, session
        if (parliament is None or session is None) and one_off_url is None:
            parliament, session = await current_session(
                db, level="provincial", province_territory="MB",
            )
            console.print(
                f"[dim]auto-resolved current MB session: "
                f"P{parliament}-S{session}[/dim]"
            )
        if since_days is not None and effective_since is not None:
            console.print(
                f"[dim]forward-incremental: --since clamped to "
                f"{effective_since.isoformat()} (since_days={since_days})[/dim]"
            )
        stats = await ingest_mb_hansard(
            db,
            parliament=parliament,
            session=session,
            since=effective_since,
            until=parse_iso_date(until),
            limit_sittings=limit_sittings,
            limit_speeches=limit_speeches,
            one_off_url=one_off_url,
        )
        console.print(
            f"[green]ingest-mb-hansard[/green]: "
            f"sittings={stats.sittings_scanned} seen={stats.speeches_seen} "
            f"inserted={stats.speeches_inserted} updated={stats.speeches_updated} "
            f"skipped_empty={stats.skipped_empty} parse_errors={stats.parse_errors} "
            f"resolved={stats.speeches_resolved} role_only={stats.speeches_role_only} "
            f"ambiguous={stats.speeches_ambiguous} unresolved={stats.speeches_unresolved}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("resolve-mb-speakers")
@click.option("--limit", type=int, default=None,
              help="Cap speeches scanned (smoke-test aid).")
@click.pass_context
def cmd_resolve_mb_speakers(ctx: click.Context, limit: Optional[int]) -> None:
    """Re-resolve politician_id on MB Hansard speeches with NULL politician_id.

    Run after expanding the MB MLA roster or fixing a parser edge case.
    Idempotent.
    """
    async def _wrap(db: Database) -> None:
        stats = await resolve_mb_hansard_speakers(db, limit=limit)
        console.print(
            f"[green]resolve-mb-speakers[/green]: "
            f"scanned={stats.speeches_scanned} updated={stats.speeches_updated} "
            f"still_unresolved={stats.still_unresolved}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("resolve-mb-speakers-dated")
@click.option("--limit", type=int, default=None,
              help="Cap candidate speeches scanned (smoke-test aid).")
@click.pass_context
def cmd_resolve_mb_speakers_dated(ctx: click.Context, limit: Optional[int]) -> None:
    """Date-windowed MB speaker resolver: uses politician_terms spans to
    disambiguate historical surnames.

    After ingest-mb-former-mlas lands ~800 historical MLAs, the
    name-only resolver flips many rows from "unresolved" to
    "ambiguous" because surnames collide across eras. This v2 joins
    politicians by surname AND politician_terms by spoken_at window —
    if the (surname, date) pair yields exactly one politician, it
    attributes. Mirrors AB's legl-keyed approach with a date
    parametrization instead of a legl parametrization (MB speeches
    don't carry legislature in raw).

    Idempotent.
    """
    async def _wrap(db: Database) -> None:
        stats = await resolve_mb_hansard_speakers_dated(db, limit=limit)
        console.print(
            f"[green]resolve-mb-speakers-dated[/green]: "
            f"scanned={stats.speeches_scanned} updated={stats.speeches_updated} "
            f"still_ambiguous={stats.still_unresolved}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("relink-mb-speaker-roles")
@click.option("--limit", type=int, default=None,
              help="Cap candidate rows scanned (smoke-test aid).")
@click.option("--dry-run", is_flag=True, default=False,
              help="Run SELECT + regex pass without writing UPDATEs.")
@click.pass_context
def cmd_relink_mb_speaker_roles(
    ctx: click.Context, limit: Optional[int], dry_run: bool,
) -> None:
    """Backfill speaker_role on MB rows where the parser left both
    speaker_role and politician_id NULL.

    Applies the current `_ROLE_PATTERNS` from `mb_hansard_parse` to each
    row's `speaker_name_raw`. Originally closed the pre-43L empty-role
    bucket (~21K rows of `Mr./Madam Deputy Speaker` / `Mr./Madam
    Chairperson` shapes the old regex set didn't catch). Idempotent and
    additive — re-running picks up any new patterns added to the parser
    without code-side coordination. Safe to schedule daily.
    """
    from .legislative.mb_speaker_role_relink import relink_mb_speaker_roles

    async def _wrap(db: Database) -> None:
        stats = await relink_mb_speaker_roles(db, limit=limit, dry_run=dry_run)
        console.print(
            f"[green]relink-mb-speaker-roles[/green]: "
            f"scanned={stats.scanned} role_assigned={stats.role_assigned} "
            f"dry_run={dry_run}"
        )
        if stats.by_role:
            console.print(f"[dim]by_role:[/dim] {stats.by_role}")
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("ingest-bc-former-mlas")
@click.option("--parliaments", type=str, default=None,
              help="Comma-separated parliament numbers (e.g. '29,30,31'). Default: 29-34.")
@click.option("--delay", type=float, default=1.5,
              help="Seconds between MediaWiki API calls (be polite to en.wikipedia.org).")
@click.pass_context
def cmd_ingest_bc_former_mlas(
    ctx: click.Context, parliaments: Optional[str], delay: float,
) -> None:
    """Backfill BC pre-1992 MLA roster from Wikipedia per-parliament list articles.

    Closes the pre-P35 gap left by enrich-bc-member-parliaments (LIMS only
    knows P35+, 1992+). Inserts one politicians row per unique MLA across
    parliaments 29-34 (1969-1991), with source_id='wikipedia:bc-mla:{slug}'.
    Inserts one politician_terms row per (politician, parliament) with
    source='wikipedia:bc-{N}th-parliament'.

    Idempotent: re-runs hit partial UNIQUE on politicians.source_id and an
    existence check on (politician_id, source) for terms.

    Run before resolve-bc-speakers-dated to lift pre-P35 attribution.
    """
    from .legislative.bc_former_mlas import (
        ingest_bc_former_mlas, DEFAULT_PARLIAMENTS,
    )
    parls: tuple[int, ...] = DEFAULT_PARLIAMENTS
    if parliaments:
        parls = tuple(int(p.strip()) for p in parliaments.split(",") if p.strip())

    async def _wrap(db: Database) -> None:
        stats = await ingest_bc_former_mlas(db, parliaments=parls, delay=delay)
        console.print(
            f"[green]ingest-bc-former-mlas[/green]: "
            f"parliaments={stats.parliaments_seen} rows={stats.rows_parsed} "
            f"unique={stats.unique_members} "
            f"pols_inserted={stats.politicians_inserted} "
            f"pols_name_matched={stats.politicians_name_matched} "
            f"terms_inserted={stats.terms_inserted} "
            f"terms_skipped={stats.terms_skipped_existing} "
            f"failures={len(stats.parse_failures)}"
        )
        if stats.parse_failures:
            console.print(f"[yellow]parse warnings:[/yellow] {stats.parse_failures[:5]}")
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("enrich-bc-member-parliaments")
@click.pass_context
def cmd_enrich_bc_member_parliaments(ctx: click.Context) -> None:
    """Stamp politician_terms for every BC (member, parliament) edge.

    Single LIMS GraphQL query → ~750 (memberId, parliamentId) edges
    enriched with each parliament's startDate / endDate. Inserts one
    politician_terms row per edge with source='lims.leg.bc.ca:parliament-N'.
    Idempotent.

    Prereq: scripts/bc-enrich-historical-mlas.py must already have
    inserted the 376-MLA historical roster (politicians keyed on
    lims_member_id). Members in the GraphQL response that don't have a
    matching politicians row are reported in the missing-id sample —
    re-run the historical-MLAs script to land them, then re-run this
    command.

    Mirrors AB's per-legislature term shape; gives the future
    resolve-bc-speakers-dated post-pass (and the eventual pre-P38
    Hansard backfill) the per-parliament terms it needs to disambiguate
    historical surname collisions.
    """
    async def _wrap(db: Database) -> None:
        stats = await enrich_bc_member_parliaments(db)
        console.print(
            f"[green]enrich-bc-member-parliaments[/green]: "
            f"edges={stats.edges_fetched} "
            f"edges_with_dates={stats.edges_with_dates} "
            f"matched={stats.politicians_matched} "
            f"missing_pols={stats.politicians_missing} "
            f"terms_inserted={stats.terms_inserted} "
            f"terms_skipped={stats.terms_skipped_existing} "
            f"missing_id_sample={stats.missing_lims_ids}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("ingest-qc-former-mnas")
@click.option("--delay", type=float, default=1.5,
              help="Seconds between page fetches (be polite to assnat.qc.ca).")
@click.option("--limit", type=int, default=None,
              help="Cap MNAs processed this run (smoke-test aid).")
@click.option("--bio-for-existing/--skip-bio-for-existing",
              "bio_for_existing", default=False,
              help="Re-fetch bios for MNAs that already have qc_assnat_id "
                   "stamped. Default skips them to save ~125 requests on "
                   "every re-run.")
@click.pass_context
def cmd_ingest_qc_former_mnas(
    ctx: click.Context, delay: float, limit: Optional[int],
    bio_for_existing: bool,
) -> None:
    """Enumerate every MNA who's served in Quebec's National Assembly since 1764.

    Walks the 16 alphabet-letter pages at
    /fr/membres/notices/index*.html, then fetches each non-current
    MNA's biography page once to extract a coarse career-span via
    prose regex (first "Élu(e) ... en YYYY", last
    "Défait(e) en YYYY" / "Démissionna ... YYYY" /
    "Décéda ... YYYY").

    Upserts politicians keyed on qc_assnat_id (migration 0038 UNIQUE
    partial); inserts one politician_terms row per MNA with
    source='assnat.qc.ca:former-mnas'. Idempotent.

    Prereq for resolve-qc-speakers-dated. Aimed at lifting QC Hansard
    resolution rates on 39-1 → 41-1 sessions where retired MNAs
    aren't currently in the politicians table (31-46% baseline).

    Roughly: 16 listing fetches + ~2,400 bio fetches at --delay=1.5
    is ~60 minutes for a full first run.
    """
    async def _wrap(db: Database) -> None:
        stats = await ingest_qc_former_mnas(
            db,
            delay=delay,
            limit=limit,
            skip_bio_for_existing=not bio_for_existing,
        )
        console.print(
            f"[green]ingest-qc-former-mnas[/green]: "
            f"pages={stats.letter_pages_scanned} "
            f"unique={stats.unique_mnas} "
            f"bios={stats.bios_fetched} bio_failed={stats.bios_failed} "
            f"bio_skipped_current={stats.bios_skipped_current} "
            f"bio_skipped_existing={stats.bios_skipped_existing} "
            f"spans_extracted={stats.spans_extracted} "
            f"span_miss={stats.spans_no_match} "
            f"inserted={stats.politicians_inserted} "
            f"updated={stats.politicians_updated} "
            f"name_matched={stats.politicians_name_matched} "
            f"patrimoine_demoted={stats.patrimoine_demoted} "
            f"terms_inserted={stats.terms_inserted} "
            f"terms_skipped={stats.terms_skipped_existing}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("resolve-qc-speakers-dated")
@click.option("--limit", type=int, default=None,
              help="Cap candidate speeches scanned (smoke-test aid).")
@click.pass_context
def cmd_resolve_qc_speakers_dated(
    ctx: click.Context, limit: Optional[int],
) -> None:
    """Date-windowed QC speaker resolver: joins NULL-politician_id
    speeches against politician_terms whose date span covers
    s.spoken_at, with cand_count=1 gate.

    Run after ingest-qc-former-mnas. Same shape as
    resolve-mb-speakers-dated (date-windowed, not legl-keyed) because
    QC bios narrate careers as prose without per-mandate structure —
    we use one wide span per MNA (source='assnat.qc.ca:former-mnas').

    Speeches whose surname matches multiple politicians whose terms
    overlap with the speech date stay NULL. Idempotent.
    """
    async def _wrap(db: Database) -> None:
        from .legislative.qc_hansard import resolve_qc_speakers_dated as _resolve
        stats = await _resolve(db, limit=limit)
        console.print(
            f"[green]resolve-qc-speakers-dated[/green]: "
            f"scanned={stats.speeches_scanned} updated={stats.speeches_updated} "
            f"still_unresolved={stats.still_unresolved}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("resolve-qc-speakers-doc-continuity")
@click.option("--limit", type=int, default=None,
              help="Cap candidate speeches scanned (smoke-test aid).")
@click.pass_context
def cmd_resolve_qc_speakers_doc_continuity(
    ctx: click.Context, limit: Optional[int],
) -> None:
    """Document-level continuity QC speaker resolver: propagates an
    already-attributed politician_id from another speech in the SAME QC
    Hansard document (raw->'qc_hansard'->>'document_id') to unresolved
    bare-surname rows whose parsed surname matches that politician's
    last_name (accent-stripped, lowercased).

    Run AFTER resolve-qc-speakers-dated. That resolver attributes by
    date-windowed last_name match (single-candidate gate); this one
    bootstraps off the resulting per-doc ground truth — for genuine
    same-surname date-overlap collisions, the surname is usually
    unambiguous within any single sitting day's Hansard.

    Confidence 0.75 (lower than dated's 0.85: corpus-bootstrap rather
    than date-windowed direct match). Same-surname-multiple-politician
    rows in a single doc stay NULL. Idempotent.
    """
    async def _wrap(db: Database) -> None:
        from .legislative.qc_hansard import (
            resolve_qc_speakers_doc_continuity as _resolve,
        )
        stats = await _resolve(db, limit=limit)
        console.print(
            f"[green]resolve-qc-speakers-doc-continuity[/green]: "
            f"scanned={stats.speeches_scanned} updated={stats.speeches_updated} "
            f"still_unresolved={stats.still_unresolved}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("resolve-on-speakers-dated")
@click.option("--limit", type=int, default=None,
              help="Cap candidate speeches scanned (smoke-test aid).")
@click.pass_context
def cmd_resolve_on_speakers_dated(ctx: click.Context, limit: Optional[int]) -> None:
    """Date-windowed ON speaker resolver: surname-equality join against
    politicians whose politician_terms window contains spoken_at.

    Rewritten 2026-05-21 (was parliament-keyed; that approach attributed
    only 0.3% of candidates because most politician_terms lack the
    'ola.org:parliament-N' source tag). Mirrors qc/mb dated resolvers.

    Run after ingest-on-former-mpps lands the historical roster, and
    after backfilling pre-current-Parliament Hansard.

    Same-surname-overlapping-terms rows stay NULL (count DISTINCT > 1).
    Idempotent.
    """
    async def _wrap(db: Database) -> None:
        from .legislative.on_hansard import (
            resolve_on_speakers_dated as _resolve,
            resolve_on_speakers_middle_initial as _resolve_mi,
        )
        stats = await _resolve(db, limit=limit)
        console.print(
            f"[green]resolve-on-speakers-dated[/green]: "
            f"scanned={stats.speeches_scanned} updated={stats.speeches_updated} "
            f"still_unresolved={stats.still_unresolved}"
        )
        # Second pass: rescue same-surname-same-first-initial-different-
        # middle-initial cases (e.g. Dave Cooke ['D. S. Cooke'] vs
        # David R. Cooke ['D. R. Cooke']) that the dated resolver can't
        # break with first-token disambiguation alone.
        mi_stats = await _resolve_mi(db, limit=limit)
        console.print(
            f"[green]resolve-on-speakers-middle-initial[/green]: "
            f"scanned={mi_stats.speeches_scanned} updated={mi_stats.speeches_updated} "
            f"still_unresolved={mi_stats.still_unresolved}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("ingest-nl-hansard")
@click.option("--ga", type=int, default=None,
              help="NL General Assembly number. Default: latest in legislative_sessions.")
@click.option("--session", type=int, default=None,
              help="Session within the GA. Default: latest.")
@click.option("--since", type=str, default=None,
              help="Only ingest sittings on/after this ISO date (YYYY-MM-DD).")
@click.option("--since-days", type=int, default=None,
              help="Forward-incremental: clamp --since to today - N days "
                   "(use in daily schedules).")
@click.option("--until", type=str, default=None,
              help="Only ingest sittings on/before this ISO date (YYYY-MM-DD).")
@click.option("--limit-sittings", type=int, default=None,
              help="Cap on sittings processed (most-recent first when capped).")
@click.option("--limit-speeches", type=int, default=None,
              help="Cap on TOTAL speeches ingested. Smoke-test friendly.")
@click.option("--url", "one_off_url", type=str, default=None,
              help="Bypass discovery and ingest a single transcript URL directly.")
@click.pass_context
def cmd_ingest_nl_hansard(
    ctx: click.Context, ga, session, since, since_days, until,
    limit_sittings, limit_speeches, one_off_url,
) -> None:
    """Ingest Newfoundland & Labrador Hansard (HTML) → speeches table.

    When --ga/--session are omitted, resolves the current session from
    legislative_sessions (populated by ingest-nl-bills).
    """
    from .legislative.current_session import current_session
    from .legislative._forward import parse_iso_date, clamp_since_with_days

    effective_since = clamp_since_with_days(parse_iso_date(since), since_days)

    async def _wrap(db: Database) -> None:
        nonlocal ga, session
        if (ga is None or session is None) and one_off_url is None:
            ga, session = await current_session(
                db, level="provincial", province_territory="NL",
            )
            console.print(
                f"[dim]auto-resolved current NL session: "
                f"GA{ga}-S{session}[/dim]"
            )
        if since_days is not None and effective_since is not None:
            console.print(
                f"[dim]forward-incremental: --since clamped to "
                f"{effective_since.isoformat()} (since_days={since_days})[/dim]"
            )
        stats = await ingest_nl_hansard(
            db,
            ga=ga,
            session=session,
            since=effective_since,
            until=parse_iso_date(until),
            limit_sittings=limit_sittings,
            limit_speeches=limit_speeches,
            one_off_url=one_off_url,
        )
        console.print(
            f"[green]ingest-nl-hansard[/green]: "
            f"sittings={stats.sittings_scanned} (skipped_404={stats.sittings_skipped_404}) "
            f"seen={stats.speeches_seen} "
            f"inserted={stats.speeches_inserted} updated={stats.speeches_updated} "
            f"skipped_empty={stats.skipped_empty} parse_errors={stats.parse_errors} "
            f"resolved={stats.speeches_resolved} group={stats.speeches_group} "
            f"role_only={stats.speeches_role_only} ambiguous={stats.speeches_ambiguous} "
            f"unresolved={stats.speeches_unresolved}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("resolve-nl-speakers")
@click.option("--limit", type=int, default=None,
              help="Cap speeches scanned (smoke-test aid).")
@click.pass_context
def cmd_resolve_nl_speakers(ctx: click.Context, limit: Optional[int]) -> None:
    """Re-resolve politician_id on NL Hansard speeches with NULL politician_id.

    Run after expanding the NL MHA roster or fixing a parser edge case.
    Skips group markers ("SOME HON. MEMBERS") and presiding-role rows
    (those are the province of resolve-presiding-speakers --province NL).
    Idempotent.
    """
    async def _wrap(db: Database) -> None:
        stats = await resolve_nl_hansard_speakers(db, limit=limit)
        console.print(
            f"[green]resolve-nl-speakers[/green]: "
            f"scanned={stats.speeches_scanned} updated={stats.speeches_updated} "
            f"still_unresolved={stats.still_unresolved}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("ingest-nb-hansard")
@click.option("--legislature", type=int, default=None,
              help="NB Legislature number (pair with --session). Required unless --all-sessions-in-legislature is given.")
@click.option("--session", type=int, default=None,
              help="Session within the legislature (requires --legislature).")
@click.option("--all-sessions-in-legislature", type=int, default=None,
              metavar="L",
              help="Every session in legislature L with a non-empty Hansard listing.")
@click.option("--since", type=str, default=None,
              help="Only ingest sittings on/after this ISO date (YYYY-MM-DD).")
@click.option("--since-days", type=int, default=None,
              help="Forward-incremental: clamp --since to today - N days "
                   "(use in daily schedules).")
@click.option("--until", type=str, default=None,
              help="Only ingest sittings on/before this ISO date (YYYY-MM-DD).")
@click.option("--limit-sittings", type=int, default=None,
              help="Cap on sittings processed (newest-first when capped).")
@click.option("--limit-speeches", type=int, default=None,
              help="Cap on TOTAL speeches ingested. Smoke-test friendly.")
@click.pass_context
def cmd_ingest_nb_hansard(
    ctx: click.Context, legislature, session, all_sessions_in_legislature,
    since, since_days, until, limit_sittings, limit_speeches,
) -> None:
    """Ingest New Brunswick Hansard (bilingual PDF) → speeches table.

    Discovery: HTML listing at /en/house-business/hansard/{L}/{S} with
    literal-backslash PDF hrefs (URL-encoded to %5C on fetch). Digital
    coverage starts at Leg 58/3 (2016); earlier sessions return an
    empty listing.

    Parser: reading-order pdftotext over bilingual two-column PDFs.
    English speaker lines trigger new speech rows; French "L'hon. X :"
    labels are treated as body text (the translation of the preceding
    English turn). Speaker resolution is name-based against NB
    politicians; "Mr. Speaker" / "Madam Speaker" rows are left
    politician_id=NULL and resolved by
    `resolve-presiding-speakers --province NB`.

    Idempotent via UNIQUE (source_system, source_url, sequence).
    """
    from .legislative.current_session import current_session
    from .legislative._forward import parse_iso_date, clamp_since_with_days

    effective_since = clamp_since_with_days(parse_iso_date(since), since_days)
    effective_until = parse_iso_date(until)

    async def _wrap(db: Database) -> None:
        nonlocal legislature, session
        if since_days is not None and effective_since is not None:
            console.print(
                f"[dim]forward-incremental: --since clamped to "
                f"{effective_since.isoformat()} (since_days={since_days})[/dim]"
            )
        if all_sessions_in_legislature is not None:
            stats = await ingest_nb_hansard_all_sessions(
                db,
                legislature=all_sessions_in_legislature,
                since=effective_since,
                until=effective_until,
                limit_sittings=limit_sittings,
                limit_speeches=limit_speeches,
            )
        else:
            if legislature is None or session is None:
                legislature, session = await current_session(
                    db, level="provincial", province_territory="NB",
                )
                console.print(
                    f"[dim]auto-resolved current NB session: "
                    f"L{legislature}-S{session}[/dim]"
                )
            stats = await ingest_nb_hansard(
                db,
                legislature=legislature,
                session=session,
                since=effective_since,
                until=effective_until,
                limit_sittings=limit_sittings,
                limit_speeches=limit_speeches,
            )
        console.print(
            f"[green]ingest-nb-hansard[/green]: "
            f"sittings={stats.sittings_scanned} empty={stats.sittings_skipped_empty} "
            f"seen={stats.speeches_seen} inserted={stats.speeches_inserted} "
            f"updated={stats.speeches_updated} skipped_empty={stats.skipped_empty} "
            f"resolved={stats.speeches_resolved} role_only={stats.speeches_role_only} "
            f"ambiguous={stats.speeches_ambiguous} unresolved={stats.speeches_unresolved}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("resolve-nb-speakers")
@click.option("--limit", type=int, default=None,
              help="Cap speeches scanned (smoke-test aid).")
@click.pass_context
def cmd_resolve_nb_speakers(ctx: click.Context, limit: Optional[int]) -> None:
    """Re-resolve politician_id on NB Hansard speeches with NULL politician_id.

    Run after expanding the NB MLA roster or fixing parser edge cases.
    Idempotent.
    """
    async def _wrap(db: Database) -> None:
        stats = await resolve_nb_hansard_speakers(db, limit=limit)
        console.print(
            f"[green]resolve-nb-speakers[/green]: "
            f"scanned={stats.speeches_scanned} updated={stats.speeches_updated} "
            f"still_unresolved={stats.still_unresolved}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("resolve-qc-speakers")
@click.option("--limit", type=int, default=None,
              help="Cap speeches scanned (smoke-test aid).")
@click.pass_context
def cmd_resolve_qc_speakers(ctx: click.Context, limit: Optional[int]) -> None:
    """Re-resolve politician_id on QC speeches with NULL politician_id.

    Run after expanding the QC MNA roster or fixing name normalization.
    Idempotent.
    """
    from .legislative.qc_hansard import resolve_qc_speakers as _resolve

    async def _wrap(db: Database) -> None:
        stats = await _resolve(db, limit=limit)
        console.print(
            f"[green]resolve-qc-speakers[/green]: "
            f"scanned={stats.speeches_scanned} updated={stats.speeches_updated} "
            f"still_unresolved={stats.still_unresolved}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("backfill-politicians-openparliament")
@click.option("--limit", type=int, default=None,
              help="Cap slugs fetched (smoke-test aid). Omit for full backfill.")
@click.option("--resolve/--no-resolve", default=True,
              help="After upserting politicians, re-run speech/chunk resolution. Default on.")
@click.pass_context
def cmd_backfill_politicians_openparliament(
    ctx: click.Context, limit: Optional[int], resolve: bool,
) -> None:
    """Create missing politicians rows by fetching openparliament.ca.

    Discovers slugs referenced by speeches with NULL politician_id,
    fetches each from api.openparliament.ca, and upserts into the
    politicians table with source_id='op:<slug>'. Then re-resolves
    speeches.politician_id and speech_chunks.politician_id.

    Safe to re-run — skips slugs already present. 5 concurrent HTTP
    fetches; ~3 minutes for 700 slugs.
    """
    from .legislative.politicians_op_backfill import run as _run_backfill, resolve_missing

    async def _wrap(db: Database) -> None:
        stats = await _run_backfill(db, limit=limit)
        console.print(
            f"[green]backfill-politicians-openparliament[/green]: "
            f"considered={stats.slugs_considered} fetched={stats.fetched} "
            f"inserted={stats.inserted} updated={stats.updated} "
            f"errors={stats.fetch_errors}"
        )
        if resolve:
            res = await resolve_missing(db)
            console.print(
                f"[green]resolve[/green]: "
                f"speeches_resolved={res['speeches_resolved']} "
                f"chunks_resolved={res['chunks_resolved']} "
                f"vote_positions_resolved={res.get('vote_positions_resolved', 0)}"
            )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("backfill-politician-terms-openparliament")
@click.option("--limit", type=int, default=None,
              help="Cap politicians processed (smoke-test aid). Omit for full run.")
@click.option("--slug", type=str, default=None,
              help="Target exactly one openparliament slug (e.g. pierre-poilievre).")
@click.pass_context
def cmd_backfill_politician_terms_openparliament(
    ctx: click.Context, limit: Optional[int], slug: Optional[str],
) -> None:
    """Hydrate politician_terms from openparliament.ca `memberships`.

    For every federal politician with a known `openparliament_slug`,
    fetches `/politicians/<slug>/` and rewrites their politician_terms
    from the `memberships` array (one row per parliament served in,
    with real election start_date and end_date).

    Supersedes the Open North single-row federal current term when
    present — openparliament has the real dates, not the scrape date.
    Safe to re-run: each politician's `openparliament:memberships`
    rows are deleted and re-written atomically per fetch.

    ~1 req/sec against api.openparliament.ca; ~25 min for 1,300 MPs.
    """
    from .legislative.politicians_op_backfill import run_terms_backfill as _run_terms

    async def _wrap(db: Database) -> None:
        stats = await _run_terms(db, limit=limit, slug=slug)
        console.print(
            f"[green]backfill-politician-terms-openparliament[/green]: "
            f"considered={stats.politicians_considered} fetched={stats.fetched} "
            f"updated={stats.politicians_updated} inserted={stats.terms_inserted} "
            f"deleted={stats.terms_deleted} "
            f"no_memberships={stats.politicians_skipped_no_memberships} "
            f"errors={stats.fetch_errors}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("jobs-worker")
@click.pass_context
def cmd_jobs_worker(ctx: click.Context) -> None:
    """Run the admin-panel jobs daemon (consumes scanner_jobs, expands schedules).

    Intended as the entrypoint of the `scanner-jobs` compose service.
    Stays up indefinitely; polls every JOBS_POLL_INTERVAL seconds.
    """
    from . import jobs_worker as _jw
    asyncio.run(_jw.main())


@cli.command("alerts-worker")
@click.pass_context
def cmd_alerts_worker(ctx: click.Context) -> None:
    """Run the saved-searches alerts daemon.

    Intended as the entrypoint of the `alerts-worker` compose service.
    Polls saved_searches for due alerts, runs HNSW matching against the
    cached query_embedding, and emails digests via Proton SMTP.
    """
    from . import alerts_worker as _aw
    asyncio.run(_aw.main())


@cli.command("reports-worker")
@click.pass_context
def cmd_reports_worker(ctx: click.Context) -> None:
    """Run the premium-reports map-reduce daemon.

    Intended as the entrypoint of the `reports-worker` compose service.
    Polls report_jobs for queued rows, runs LLM map-reduce over every
    matching speech_chunk, persists sanitised HTML, commits the credit
    hold (or releases on failure), and emails the user a "ready" /
    "failed" notification via Proton SMTP. See premium-reports.md plan.
    """
    from . import reports_worker as _rw
    asyncio.run(_rw.main())


@cli.command("chunk-speeches")
@click.option("--limit", type=int, default=None,
              help="Max speeches to chunk this run (default: all pending).")
@click.option("--source-system", type=str, default=None,
              help="Restrict to one source_system (e.g. 'assembly.ab.ca'). "
                   "Bypasses the global spoken_at-DESC queue — useful for "
                   "getting a freshly-ingested pipeline searchable without "
                   "waiting for the daily cron to drain the global backlog.")
@click.option("--speech-type", type=str, default=None,
              help="Restrict to one speech_type (e.g. 'committee' or 'floor').")
@click.pass_context
def cmd_chunk_speeches(ctx: click.Context, limit, source_system, speech_type) -> None:
    """Split speeches.text into retrievable speech_chunks rows.

    Speaker-turn = one chunk by default. Long turns (> ~480 tokens)
    split at paragraph boundary with 50-token overlap. Tiny procedural
    turns (< 8 tokens) are skipped. Idempotent: re-runs only process
    speeches that don't yet have chunks.
    """
    from .legislative.speech_chunker import chunk_pending as _chunk

    async def _wrap(db: Database) -> None:
        if source_system or speech_type:
            console.print(
                f"[dim]chunk-speeches: filtering "
                f"source_system={source_system!r} speech_type={speech_type!r}[/dim]"
            )
        stats = await _chunk(
            db,
            limit_speeches=limit,
            source_system=source_system,
            speech_type=speech_type,
        )
        console.print(
            f"[green]chunk-speeches[/green]: seen={stats.speeches_seen} "
            f"chunked={stats.speeches_chunked} skipped={stats.speeches_skipped} "
            f"chunks={stats.chunks_inserted}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("embed-speech-chunks")
@click.option("--limit", type=int, default=None,
              help="Max chunks to embed this run (default: all pending).")
@click.option("--batch-size", type=int, default=32,
              help="Texts per TEI /embed call. TEI's --max-client-batch-size (default 64) is the hard cap.")
@click.pass_context
def cmd_embed_speech_chunks(ctx: click.Context, limit, batch_size) -> None:
    """Fill speech_chunks.embedding via TEI (Qwen3-Embedding-0.6B).

    Calls TEI at EMBED_URL (default http://tei:80). Uses batched
    UPDATE ... FROM UNNEST for ~1 DB round-trip per batch instead of per
    chunk — measured at 50.9 chunks/sec end-to-end. Safe to interrupt
    and resume; unembedded chunks stay NULL and get picked up on next run.
    """
    from .legislative.speech_embedder import embed_pending as _embed

    async def _wrap(db: Database) -> None:
        stats = await _embed(db, limit_chunks=limit, batch_size=batch_size)
        colour = "red" if stats.aborted_consecutive_failures else "green"
        console.print(
            f"[{colour}]embed-speech-chunks[/{colour}]: seen={stats.chunks_seen} "
            f"embedded={stats.chunks_embedded} batches={stats.batches} "
            f"errors={stats.errors} retries={stats.retries} "
            f"aborted={stats.aborted_consecutive_failures} "
            f"server_ms={stats.total_elapsed_ms}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("chunk-and-embed-speeches")
@click.option("--chunk-limit", type=int, default=None,
              help="Max speeches to chunk this run (default: all pending).")
@click.option("--embed-limit", type=int, default=None,
              help="Max chunks to embed this run (default: all pending).")
@click.option("--batch-size", type=int, default=32,
              help="Texts per TEI /embed call.")
@click.pass_context
def cmd_chunk_and_embed_speeches(
    ctx: click.Context, chunk_limit, embed_limit, batch_size
) -> None:
    """Run chunk-speeches then embed-speech-chunks in a single process.

    Atomic ordering: chunk_pending always completes before embed_pending
    starts, so the embed pass picks up the chunks the same job just
    produced. Use this as the daily post-ingest schedule rather than two
    separate scanner_jobs rows — one process means no queue-ordering
    assumption and no parallel-worker race.

    Step 0 is a denorm sync: speech_chunks copies filter columns from
    its parent speech at insert time, but downstream speaker resolvers
    / session retags / attribution corrections touch only speeches,
    leaving chunks with stale values. Running the sync before
    chunk_pending catches yesterday's drift before today's /search
    queries land on it.
    """
    from .legislative.speech_chunker import (
        chunk_pending as _chunk, sync_chunk_denorm as _sync_denorm,
    )
    from .legislative.speech_embedder import embed_pending as _embed

    async def _wrap(db: Database) -> None:
        sstats = await _sync_denorm(db)
        console.print(
            f"[green]sync-chunk-denorm[/green]: chunks_synced={sstats.chunks_synced}"
        )
        cstats = await _chunk(db, limit_speeches=chunk_limit)
        console.print(
            f"[green]chunk-speeches[/green]: seen={cstats.speeches_seen} "
            f"chunked={cstats.speeches_chunked} skipped={cstats.speeches_skipped} "
            f"chunks={cstats.chunks_inserted}"
        )
        estats = await _embed(db, limit_chunks=embed_limit, batch_size=batch_size)
        colour = "red" if estats.aborted_consecutive_failures else "green"
        console.print(
            f"[{colour}]embed-speech-chunks[/{colour}]: seen={estats.chunks_seen} "
            f"embedded={estats.chunks_embedded} batches={estats.batches} "
            f"errors={estats.errors} retries={estats.retries} "
            f"aborted={estats.aborted_consecutive_failures} "
            f"server_ms={estats.total_elapsed_ms}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("project-embeddings")
@click.option("--stage", type=click.Choice(["fit", "cluster", "label", "promote", "gc", "all"]),
              default="all",
              help="Which stage to run. 'all' chains fit -> cluster -> label and "
                   "leaves promotion to the operator (no auto-go-live).")
@click.option("--run-id", type=str, default=None,
              help="Override run id. Defaults to latest 'running' for cluster/label/promote, "
                   "creates a new run for fit, required for promote.")
@click.option("--sample-size", type=int, default=500_000,
              help="UMAP fit sample size (rows). Stratification is uniform-random.")
@click.option("--transform-batch", type=int, default=50_000,
              help="Rows per UMAP transform + DB write batch.")
@click.option("--max-age-days", type=int, default=7,
              help="gc only: drop superseded/failed runs older than this.")
@click.option("--limit", type=int, default=None,
              help="fit only: cap total chunks projected (smoke-test aid). Production runs leave unset.")
@click.pass_context
def cmd_project_embeddings(
    ctx: click.Context, stage: str, run_id, sample_size, transform_batch, max_age_days, limit,
) -> None:
    """UMAP-project speech_chunks.embedding into 3D + 2D coords; HDBSCAN-cluster
    at four levels; TF-IDF label.

    Stages are idempotent and split so each can be retried independently:

      fit     -> writes speech_chunk_projections rows (cluster_id NULL)
      cluster -> writes speech_clusters rows; stamps cluster_id_lN
      label   -> fills cluster.label / top_terms / top_chunk_ids
      promote -> flips is_current; the API reads this on every request
      gc      -> drops old superseded runs (cascades clusters + projections)
      all     -> fit + cluster + label (does NOT promote — explicit step)

    Powers /semantic-map. See db/migrations/0039 for the schema.
    """
    import logging as _logging
    _logging.basicConfig(
        level=_logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    from .legislative.projection_builder import (
        cluster as _cluster,
        create_run, fit as _fit, find_latest_running_run,
        gc as _gc, label as _label, mark_run_status, promote as _promote,
    )

    async def _wrap(db: Database) -> None:
        nonlocal run_id
        if stage == "gc":
            n = await _gc(db, max_age_days=max_age_days)
            console.print(f"[green]project-embeddings gc[/green]: dropped {n} runs")
            return

        if stage == "promote":
            if not run_id:
                raise click.UsageError("--run-id required for --stage=promote")
            await _promote(db, run_id=run_id)
            console.print(f"[green]project-embeddings promote[/green]: run {run_id} is_current=true")
            return

        if stage in ("fit", "all"):
            run_id, fit_stats = await _fit(
                db, run_id=run_id,
                sample_size=sample_size,
                transform_batch=transform_batch,
                limit=limit,
            )
            await mark_run_status(
                db, run_id, status="running",
                chunk_count=fit_stats.rows_written,
            )
            console.print(
                f"[green]project-embeddings fit[/green]: run={run_id} "
                f"sample={fit_stats.sample_size} fit3d={fit_stats.fit_seconds_3d:.1f}s "
                f"fit2d={fit_stats.fit_seconds_2d:.1f}s "
                f"transform={fit_stats.transform_seconds:.1f}s "
                f"rows={fit_stats.rows_written}"
            )

        if stage in ("cluster", "all"):
            if not run_id:
                run_id = await find_latest_running_run(db)
                if not run_id:
                    raise click.UsageError("no --run-id and no 'running' run found")
            cluster_stats = await _cluster(db, run_id=run_id)
            await mark_run_status(
                db, run_id, status="running",
                cluster_counts=(
                    cluster_stats.level_counts.get(1, 0),
                    cluster_stats.level_counts.get(2, 0),
                    cluster_stats.level_counts.get(3, 0),
                    cluster_stats.level_counts.get(4, 0),
                    cluster_stats.level_counts.get(5, 0),
                ),
            )
            console.print(
                f"[green]project-embeddings cluster[/green]: run={run_id} "
                f"L1={cluster_stats.level_counts.get(1, 0)} "
                f"L2={cluster_stats.level_counts.get(2, 0)} "
                f"L3={cluster_stats.level_counts.get(3, 0)} "
                f"L4={cluster_stats.level_counts.get(4, 0)} "
                f"L5={cluster_stats.level_counts.get(5, 0)} "
                f"({cluster_stats.cluster_seconds:.1f}s)"
            )

        if stage in ("label", "all"):
            if not run_id:
                run_id = await find_latest_running_run(db)
                if not run_id:
                    raise click.UsageError("no --run-id and no 'running' run found")
            label_stats = await _label(db, run_id=run_id)
            console.print(
                f"[green]project-embeddings label[/green]: run={run_id} "
                f"clusters={label_stats.clusters_labelled} "
                f"chunks_read={label_stats.chunks_read} "
                f"({label_stats.seconds:.1f}s)"
            )

        if stage == "all":
            console.print(
                f"[yellow]project-embeddings[/yellow]: run {run_id} ready. "
                f"Run with --stage=promote --run-id={run_id} to make it live."
            )

    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("refresh-coverage-stats")
@click.pass_context
def cmd_refresh_coverage_stats(ctx: click.Context) -> None:
    """Recompute jurisdiction_sources counts from live tables.

    Drives the public /coverage page. Auto-flips:
      * hansard_status: 'live' if speeches ≥ 50k, 'partial' if 1k-49k.
      * votes_status: 'live' if votes ≥ 100, 'partial' if 1-99, 'none' otherwise.
      * bills_status: 'live' if bills ≥ 500, 'partial' if 1-499, 'none' otherwise.
    Updates speeches_count / politicians_count / bills_count / votes_count
    and stamps last_verified_at = now(). 'blocked' status flags are
    preserved across all three columns. Committees status remains editorial.
    """
    from .legislative.coverage_stats import refresh_coverage_stats as _refresh

    async def _wrap(db: Database) -> None:
        report = await _refresh(db)
        for code, stats in sorted(report.items()):
            h_arrow = (
                f"hansard {stats['prev_hansard_status']}→{stats['hansard_status']}"
                if stats["prev_hansard_status"] != stats["hansard_status"]
                else f"hansard={stats['hansard_status']}"
            )
            v_arrow = (
                f"votes {stats['prev_votes_status']}→{stats['votes_status']}"
                if stats["prev_votes_status"] != stats["votes_status"]
                else f"votes={stats['votes_status']}"
            )
            b_arrow = (
                f"bills {stats['prev_bills_status']}→{stats['bills_status']}"
                if stats["prev_bills_status"] != stats["bills_status"]
                else f"bills={stats['bills_status']}"
            )
            console.print(
                f"[green]{code}[/green]: speeches={stats['speeches']} "
                f"(was {stats['prev_speeches']}) politicians={stats['politicians']} "
                f"bills={stats['bills']} (was {stats['prev_bills']}) "
                f"votes={stats['votes']} (was {stats['prev_votes']})  "
                f"{h_arrow}  {v_arrow}  {b_arrow}"
            )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("resolve-bc-allcaps")
@click.option("--limit", type=int, default=None,
              help="Cap candidate speeches scanned (smoke-test aid).")
@click.pass_context
def cmd_resolve_bc_allcaps(ctx: click.Context, limit: Optional[int]) -> None:
    """Resolve BC pre-1990 ALL-CAPS speaker labels.

    Targets `MR. G.S. WALLACE (Oak Bay)` / `HON. D. BARRETT (Premier)`
    shape that the existing `resolve-bc-speakers-dated` extracts the
    constituency-in-parens as the surname (wrong). Parses honorific +
    initials + lastname + parens-hint, then FK-matches against
    politician_terms by date-windowed lastname with constituency or
    first-initial disambiguation when surname-only is ambiguous.

    Idempotent. Re-runs no-op since the WHERE clause excludes already-
    resolved rows.
    """
    from .legislative.bc_allcaps_resolver import resolve_bc_allcaps

    async def _wrap(db: Database) -> None:
        stats = await resolve_bc_allcaps(db, limit=limit)
        console.print(
            f"[green]resolve-bc-allcaps[/green]: "
            f"scanned={stats.scanned} parsed={stats.parsed} "
            f"by_riding={stats.resolved_by_riding} "
            f"by_initial={stats.resolved_by_initial} "
            f"by_lastname={stats.resolved_by_lastname} "
            f"still_ambiguous={stats.still_ambiguous} "
            f"no_term_match={stats.no_term_match} "
            f"no_parse={stats.no_parse}"
        )
        if stats.miss_samples:
            console.print("[yellow]parse-fail samples:[/yellow]")
            for s in stats.miss_samples[:5]:
                console.print(f"  {s}")
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("resolve-inline-presiding-officers")
@click.option("--province", type=str, default=None,
              help="2-letter code (AB/BC/QC/...) to scope the run. Default: all provinces.")
@click.option("--limit", type=int, default=None,
              help="Cap candidate speeches scanned (smoke-test aid).")
@click.pass_context
def cmd_resolve_inline_presiding_officers(
    ctx: click.Context, province: Optional[str], limit: Optional[int],
) -> None:
    """Tier-2 attribution Pass 1 — extract names from parenthesised
    presiding-officer labels and FK-match against politicians.

    Targets speeches like `The Deputy Speaker (Mr. Bas Balkissoon)` or
    `The Chair (Ms. Donna Skelly)` whose chamber's primary parser left
    them unattributed. Sister of resolve-presiding-speakers (which
    handles role-only "The Speaker" turns via SPEAKER_ROSTER).

    Cross-jurisdictional, idempotent. Re-runs are no-ops.
    """
    from .legislative.inline_presiding_resolver import resolve_inline_presiding
    from .legislative.presiding_officer_resolver import (
        DEPUTY_PRESIDING_ROSTER,
        ensure_deputy_presiding_politicians,
        ensure_deputy_presiding_terms,
    )

    async def _wrap(db: Database) -> None:
        # Seed Deputy-Speaker rosters first — Pass-2 narrowing depends on
        # politician_terms rows tagged with DEPUTY_SOURCE_TAG. Idempotent;
        # cheap (a few SQL statements per province in the roster).
        seed_provinces = (
            [province] if province and province in DEPUTY_PRESIDING_ROSTER
            else list(DEPUTY_PRESIDING_ROSTER.keys())
        )
        for prov in seed_provinces:
            name_to_id = await ensure_deputy_presiding_politicians(db, prov)
            await ensure_deputy_presiding_terms(db, prov, name_to_id=name_to_id)

        stats = await resolve_inline_presiding(
            db, province=province, limit=limit,
        )
        console.print(
            f"[green]resolve-inline-presiding-officers[/green]: "
            f"candidates={stats.candidates} "
            f"extracted={stats.extracted} "
            f"fk_hits={stats.fk_hits} "
            f"fk_hits_pass2={stats.fk_hits_pass2} "
            f"fk_misses={stats.fk_misses} "
            f"speeches_updated={stats.speeches_updated} "
            f"chunks_updated={stats.chunks_updated}"
        )
        if stats.misses_sample:
            console.print("[yellow]FK miss samples:[/yellow]")
            for prov, name in stats.misses_sample:
                console.print(f"  [{prov}] {name!r}")
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("resolve-named-speakers")
@click.option("--province", type=str, default=None,
              help="2-letter code (MB/AB/...) to scope the run. Default: all provinces.")
@click.option("--limit", type=int, default=None,
              help="Cap candidate speeches scanned (smoke-test aid).")
@click.pass_context
def cmd_resolve_named_speakers(
    ctx: click.Context, province: Optional[str], limit: Optional[int],
) -> None:
    """Tier-2 attribution Pass 4 — resolve regular MLA speeches the
    chamber parser left politician_id NULL on, where the speaker label
    carries a name (e.g., 'Mrs. Driedger', 'Hon. Erin Selby (Minister
    of Health)'). Cross-jurisdictional, idempotent.

    Distinct from Pass 1/3 which target presiding-officer turns. Pass 4
    is for non-presiding labels with NULL/empty speaker_role. Pre-
    filters out vocatives ('Mr. Speaker'), parliamentary staff (Clerks,
    Sergeants), and generic ('An Honourable Member') placeholders.
    """
    from .legislative.named_speaker_resolver import resolve_named_speakers

    async def _wrap(db: Database) -> None:
        stats = await resolve_named_speakers(db, province=province, limit=limit)
        console.print(
            f"[green]resolve-named-speakers[/green]: "
            f"candidates={stats.candidates} "
            f"extracted={stats.extracted} "
            f"fk_hits_full={stats.fk_hits_full} "
            f"fk_hits_initial={stats.fk_hits_initial} "
            f"fk_hits_surname={stats.fk_hits_surname} "
            f"fk_hits_dated={stats.fk_hits_dated} "
            f"fk_misses={stats.fk_misses} "
            f"speeches_updated={stats.speeches_updated} "
            f"chunks_updated={stats.chunks_updated}"
        )
        if stats.misses_sample:
            console.print("[yellow]FK miss samples:[/yellow]")
            for prov, raw in stats.misses_sample:
                console.print(f"  [{prov}] {raw!r}")
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("resolve-role-only-presiding-officers")
@click.option("--province", type=str, default=None,
              help="2-letter code (AB/...) to scope the run. Default: all provinces in ROLE_ONLY_PRESIDING_ROSTER.")
@click.option("--limit", type=int, default=None,
              help="Cap candidate speeches scanned per role (smoke-test aid).")
@click.pass_context
def cmd_resolve_role_only_presiding_officers(
    ctx: click.Context, province: Optional[str], limit: Optional[int],
) -> None:
    """Tier-2 attribution Pass 3 — resolve role-only presiding labels
    (e.g., AB's `The Deputy Speaker` with no inline name) by date-
    windowed lookup of the corresponding office holder.

    Single-person date-determined roles only (Deputy Speaker, Deputy
    Chair of Committees). Rotating roles (Acting Speaker, generic
    Chair) need a different mechanism and are not handled here.

    Idempotent. Re-runs are no-ops once roster is exhausted.
    """
    from .legislative.presiding_officer_resolver import (
        ROLE_ONLY_PRESIDING_ROSTER,
        ensure_role_only_presiding_politicians,
        ensure_role_only_presiding_terms,
        resolve_role_only_presiding,
    )

    async def _wrap(db: Database) -> None:
        provinces = (
            [province] if province and province in ROLE_ONLY_PRESIDING_ROSTER
            else list(ROLE_ONLY_PRESIDING_ROSTER.keys())
        )
        for prov in provinces:
            name_to_id = await ensure_role_only_presiding_politicians(db, prov)
            await ensure_role_only_presiding_terms(db, prov, name_to_id=name_to_id)

        for prov in provinces:
            stats = await resolve_role_only_presiding(db, prov, limit=limit)
            console.print(
                f"[green]resolve-role-only-presiding-officers[/green] [{prov}]: "
                f"scanned={stats.scanned} "
                f"resolved={stats.resolved} "
                f"no_term_match={stats.no_term_match} "
                f"chunks_updated={stats.chunks_updated}"
            )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("resolve-presiding-speakers")
@click.option("--province", type=click.Choice(["AB", "BC", "QC", "MB", "NB", "NL", "NS", "ON", "NT", "SK"]), default="AB",
              help="Jurisdiction whose Speaker roster to seed + resolve.")
@click.option("--limit", type=int, default=None,
              help="Cap candidate speeches scanned (smoke-test aid).")
@click.pass_context
def cmd_resolve_presiding_speakers(
    ctx: click.Context, province: str, limit: Optional[int],
) -> None:
    """Link 'The Speaker' speeches to the sitting Speaker by date.

    Three-step idempotent pipeline:
      1. Ensure every roster Speaker exists in `politicians` (inserts
         retired Speakers as minimal rows when missing).
      2. Upsert `politician_terms` rows with office='Speaker' and the
         exact start/end dates for each Speaker's tenure.
      3. Resolve NULL-politician_id speeches whose speaker_role / raw
         name indicates 'The Speaker' by looking up the term that
         contains the speech's spoken_at date. Updates speech_chunks
         in the same pass.

    Safe to re-run. If you add a new Speaker to SPEAKER_ROSTER in
    `presiding_officer_resolver.py`, re-running this command picks up
    any new speeches falling in that Speaker's window.
    """
    from .legislative.presiding_officer_resolver import seed_and_resolve

    async def _wrap(db: Database) -> None:
        stats = await seed_and_resolve(db, province, limit=limit)
        console.print(
            f"[green]resolve-presiding-speakers[/green] ({stats['province']}): "
            f"roster={stats['roster']} terms={stats['terms']} "
            f"scanned={stats['scanned']} resolved={stats['resolved']} "
            f"no_term_match={stats['no_term_match']} "
            f"chunks_updated={stats['chunks_updated']}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("resolve-acting-speakers")
@click.option("--limit", type=int, default=None,
              help="Cap candidate speeches scanned (smoke-test aid).")
@click.pass_context
def cmd_resolve_acting_speakers(ctx: click.Context, limit) -> None:
    """Resolve politician_id on federal speeches tagged with a presiding-
    officer attribution like 'The Acting Speaker (Mr. McClelland)'.

    Openparliament doesn't populate politician_url for these turns, so
    they land with politician_id NULL at ingest. This walks them after
    the fact, extracts the parenthesised name, and unique-matches
    against the politicians table.
    """
    from .legislative.acting_speaker_resolver import resolve_acting_speakers as _resolve

    async def _wrap(db: Database) -> None:
        stats = await _resolve(db, limit=limit)
        console.print(
            f"[green]resolve-acting-speakers[/green]: "
            f"scanned={stats['scanned']} resolved={stats['resolved']} "
            f"ambiguous={stats['ambiguous']} "
            f"no_politician_found={stats['no_politician_found']} "
            f"no_parens={stats['no_parens']}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("gc-usage-metrics")
@click.pass_context
def cmd_gc_usage_metrics(ctx: click.Context) -> None:
    """Drop old rows from the operator-observability tables.

    Deletes:
      * private.gpu_samples         older than 90 days
      * private.tei_samples         older than 90 days
      * private.search_request_log  older than 30 days

    Implemented as a thin wrapper over the SQL function
    `private.gc_usage_metrics()` so the retention windows live in one
    place (the migration). Safe to run on an empty DB.
    """
    async def _wrap(db: Database) -> None:
        rows = await db.fetch("SELECT * FROM private.gc_usage_metrics()")
        for r in rows:
            console.print(
                f"[green]gc-usage-metrics[/green]: "
                f"{r['table_name']} deleted={r['deleted_rows']}"
            )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


# ─────────────────────────────────────────────────────────────────────
# Municipal — eScribe + YouTube captions (Calgary, Edmonton)
#
# Seven-stage chain. Stages 1-4 ingest the structured-decisions surface
# (motions, bylaws, recorded votes) from the eScribe SaaS. Stages 5-7
# add the speech corpus by matching meetings to YouTube videos and
# parsing auto-generated captions. The downstream chunk-and-embed-speeches
# job picks up new municipal speeches automatically.
# ─────────────────────────────────────────────────────────────────────

_ESCRIBE_CITY_CHOICES = ("calgary", "edmonton", "all")


@cli.command("ingest-escribe-meetings")
@click.option("--city", type=click.Choice(_ESCRIBE_CITY_CHOICES), default="all")
@click.option("--limit", type=int, default=None,
              help="Max meetings to ingest per city. Smoke-test friendly.")
@click.pass_context
def cmd_ingest_escribe_meetings(ctx: click.Context, city, limit) -> None:
    """Stage 1 — discover meetings from pub-{city}.escribemeetings.com.

    One GET of MeetingsCalendarView.aspx returns the full meeting list
    (typically 2017-present) inline. Idempotent on
    (source_system, source_meeting_id).
    """
    from .legislative.escribe_ingest import ingest_meetings as _ingest

    async def _wrap(db: Database) -> None:
        stats = await _ingest(db, city_slug=city, limit=limit)
        console.print(
            f"[green]ingest-escribe-meetings[/green]: cities={stats.cities_processed} "
            f"seen={stats.meetings_seen} inserted={stats.meetings_inserted} "
            f"updated={stats.meetings_updated} warns={stats.parse_warnings} "
            f"fails={len(stats.fetch_failures)}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("fetch-escribe-meeting-pages")
@click.option("--city", type=click.Choice(_ESCRIBE_CITY_CHOICES), default="all")
@click.option("--limit", type=int, default=None)
@click.option("--force", is_flag=True, default=False,
              help="Re-fetch already-cached pages.")
@click.option("--delay", type=float, default=1.0,
              help="Seconds between per-meeting GETs.")
@click.pass_context
def cmd_fetch_escribe_meeting_pages(ctx: click.Context, city, limit, force, delay) -> None:
    """Stage 2 — populate meetings.raw_html for unfetched rows."""
    from .legislative.escribe_ingest import fetch_meeting_pages as _fetch

    async def _wrap(db: Database) -> None:
        stats = await _fetch(db, city_slug=city, limit=limit, force=force, delay=delay)
        console.print(
            f"[green]fetch-escribe-meeting-pages[/green]: cities={stats.cities_processed} "
            f"fetched={stats.meetings_fetched} fails={len(stats.fetch_failures)}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("parse-escribe-meeting-pages")
@click.option("--city", type=click.Choice(_ESCRIBE_CITY_CHOICES), default="all")
@click.option("--limit", type=int, default=None)
@click.pass_context
def cmd_parse_escribe_meeting_pages(ctx: click.Context, city, limit) -> None:
    """Stage 3 — re-parse cached HTML into bills/votes rows. No HTTP.

    Idempotent: every insert is upsert-on-conflict. Re-runnable after
    parser fixes without re-fetching.
    """
    from .legislative.escribe_ingest import parse_meeting_pages as _parse

    async def _wrap(db: Database) -> None:
        stats = await _parse(db, city_slug=city, limit=limit)
        console.print(
            f"[green]parse-escribe-meeting-pages[/green]: cities={stats.cities_processed} "
            f"parsed={stats.pages_parsed} bills_inserted={stats.bills_inserted} "
            f"bills_updated={stats.bills_updated} events={stats.bill_events_inserted} "
            f"sponsors={stats.bill_sponsors_inserted} votes={stats.votes_inserted} "
            f"positions={stats.vote_positions_inserted} warns={stats.parse_warnings}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("resolve-escribe-motion-movers")
@click.option("--city", type=click.Choice(_ESCRIBE_CITY_CHOICES), default="all")
@click.pass_context
def cmd_resolve_escribe_motion_movers(ctx: click.Context, city) -> None:
    """Stage 4 — name-fuzz match bill_sponsors.politician_id for municipal motions.

    Matches surname tokens against the city's Open North roster
    (politicians with source_id LIKE 'opennorth:{city}-city-council:%').
    """
    from .legislative.escribe_ingest import resolve_motion_movers as _resolve

    async def _wrap(db: Database) -> None:
        stats = await _resolve(db, city_slug=city)
        console.print(
            f"[green]resolve-escribe-motion-movers[/green]: cities={stats.cities_processed} "
            f"resolved={stats.movers_resolved} unresolved={stats.movers_unresolved}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("ingest-edmonton-meetings")
@click.pass_context
def cmd_ingest_edmonton_meetings(ctx: click.Context) -> None:
    """Stage 1 (Edmonton) — meetings spine from the city's Socrata portal.

    data.edmonton.ca publishes the full eScribe meeting record 2011-present
    as open datasets; this bypasses the JS-walled eScribe calendar entirely.
    Idempotent on (source_system, source_meeting_id); safe to run daily.
    """
    from .legislative.edmonton_socrata import ingest_edmonton_meetings as _ingest

    async def _wrap(db: Database) -> None:
        stats = await _ingest(db)
        console.print(
            f"[green]ingest-edmonton-meetings[/green]: fetched={stats.rows_fetched} "
            f"meetings={stats.meetings_seen} inserted={stats.meetings_inserted} "
            f"updated={stats.meetings_updated} sessions_seeded={stats.sessions_seeded} "
            f"skipped(no-id={stats.skipped_no_id} no-dt={stats.skipped_no_datetime}) "
            f"per-term={stats.per_term}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("match-meetings-to-youtube")
@click.option("--city", type=click.Choice(_ESCRIBE_CITY_CHOICES), default="all")
@click.option("--limit", type=int, default=None)
@click.option("--max-channel-videos", type=int, default=800)
@click.pass_context
def cmd_match_meetings_to_youtube(
    ctx: click.Context, city, limit, max_channel_videos,
) -> None:
    """Stage 5 — attach stream VODs from the city's room channels to meetings.

    Stream titles carry the meeting date + body verbatim
    ('July 7, 2026 - City Council'); the join is (title-date, normalized
    body) against the structured meetings spine. Sets meetings.video_url.
    """
    from .legislative.youtube_captions import match_meetings_to_youtube as _match

    async def _wrap(db: Database) -> None:
        stats = await _match(
            db, city_slug=city, limit=limit,
            max_channel_videos=max_channel_videos,
        )
        console.print(
            f"[green]match-meetings-to-youtube[/green]: cities={stats.cities_processed} "
            f"matched={stats.matched_videos} "
            f"unmatched={stats.skipped_no_match} fails={len(stats.fetch_failures)}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("ingest-edmonton-roster-history")
@click.pass_context
def cmd_ingest_edmonton_roster_history(ctx: click.Context) -> None:
    """Dated council membership (2004→2021 elections) from Socrata yqff-55ja.

    Writes politician_terms rows (source=edmonton-socrata:yqff-55ja,
    delete-and-reinsert = idempotent) and creates missing historical
    members. Unlocks FK attribution for pre-2025-term backfill meetings —
    without this the roster gate correctly refuses to resolve them.
    """
    from .legislative.edmonton_socrata import ingest_edmonton_roster_history as _ingest

    async def _wrap(db: Database) -> None:
        stats = await _ingest(db)
        console.print(
            f"[green]ingest-edmonton-roster-history[/green]: rows={stats.rows_fetched} "
            f"matched={stats.people_matched} created={stats.people_created} "
            f"terms={stats.terms_written} skipped={stats.skipped}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("probe-edmonton-media")
@click.option("--limit", type=int, default=None)
@click.option("--force", is_flag=True, default=False,
              help="Re-probe meetings that already have a media record.")
@click.pass_context
def cmd_probe_edmonton_media(ctx: click.Context, limit, force) -> None:
    """Map meetings to their ISI CDN recordings (metadata only, no media).

    2-3 small requests per meeting: eScribe player page for the filename,
    HEAD on video.isilive.ca for etag/size (the media identity key).
    Results in meetings.raw->'media'; ~25% of meetings are ISI-empty and
    keep YouTube as their media source.
    """
    from .legislative.edmonton_media import probe_media_assets as _probe

    async def _wrap(db: Database) -> None:
        stats = await _probe(db, limit=limit, force=force)
        console.print(
            f"[green]probe-edmonton-media[/green]: seen={stats.meetings_seen} "
            f"isi={stats.isi_found} empty={stats.isi_empty} errors={stats.errors}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("ocr-speaker-timeline")
@click.option("--city", type=click.Choice(("edmonton",)), default="edmonton")
@click.option("--limit", type=int, default=None,
              help="Max meetings this run. Each is ~280MB download + ~10-15 CPU-min.")
@click.option("--force", is_flag=True, default=False,
              help="Rebuild timelines that already exist.")
@click.option("--workers", type=int, default=3,
              help="Concurrent OCR worker threads (downloads stay serial).")
@click.option("--cached-only", is_flag=True, default=False,
              help="Only OCR meetings whose derivative cache is complete; "
                   "never fetch media. Safe to run alongside "
                   "cache-edmonton-media (trail-behind mode).")
@click.pass_context
def cmd_ocr_speaker_timeline(ctx: click.Context, city, limit, force, workers, cached_only) -> None:
    """Stage 8 — OCR the clerk's on-screen speaker panel into a timeline.

    Downloads the meeting video at 480p, reads the ~5s YouTube keyframes,
    colour-searches the clerk panel, OCRs the current-speaker entry gated
    on the ticking countdown, and stores interval JSON in
    meetings.raw->'speaker_timeline'. Video and frames are transient.
    """
    from .legislative.edmonton_panel_ocr import ocr_speaker_timeline as _ocr

    async def _wrap(db: Database) -> None:
        stats = await _ocr(db, city_slug=city, limit=limit, force=force,
                           workers=workers, cached_only=cached_only)
        console.print(
            f"[green]ocr-speaker-timeline[/green]: meetings={stats.meetings_seen} "
            f"built={stats.timelines_built} dl_fails={stats.download_failures} "
            f"frames={stats.frames_processed} crops={stats.unique_crops_ocrd} "
            f"intervals={stats.intervals_stored}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("cache-edmonton-media")
@click.option("--city", type=click.Choice(("edmonton",)), default="edmonton")
@click.option("--limit", type=int, default=None,
              help="Max meetings this run (default: all with speeches).")
@click.option("--workers", type=int, default=1,
              help="Concurrent ISI fetch+derive pipelines (YouTube fallback "
                   "stays single-file regardless).")
@click.pass_context
def cmd_cache_edmonton_media(ctx: click.Context, city, limit, workers) -> None:
    """Acquisition-only — build media derivative caches, no OCR.

    Walks speeches-bearing meetings newest-first and runs the media
    source ladder (ISI CDN first, YouTube fallback) to land audio +
    frames + caption alignment in the media cache. Voice attribution
    needs only this; OCR trails later as a separate low-priority pass.
    Serial single-connection politeness; failures memoized in
    meetings.raw->'fetch' with backoff.
    """
    from .legislative.edmonton_panel_ocr import cache_edmonton_media as _cache

    async def _wrap(db: Database) -> None:
        stats = await _cache(db, city_slug=city, limit=limit, workers=workers)
        console.print(
            f"[green]cache-edmonton-media[/green]: meetings={stats.meetings_seen} "
            f"cached={stats.timelines_built} dl_fails={stats.download_failures} "
            f"backoff_skips={stats.skipped_no_interval}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("realign-media-offsets")
@click.option("--city", type=click.Choice(("edmonton",)), default="edmonton")
@click.option("--limit", type=int, default=None)
@click.option("--force", is_flag=True, default=False,
              help="also recompute offsets already verified by identity "
                   "(normally left alone — identity outranks VAD)")
@click.pass_context
def cmd_realign_media_offsets(ctx: click.Context, city, limit, force) -> None:
    """Recompute caption offsets from cached audio — no re-download.

    Offsets written before 2026-08-19 came from an aligner that searched a
    fixed ±600s window; ISI encoder streams start long before the meeting,
    so for 216 of 405 Edmonton meetings the true offset was outside the
    searched range and a confidently-wrong value was stored. This re-runs
    the fixed aligner against audio already on disk and patches meta.json
    in place, leaving anything still untrusted untouched.
    """
    from .legislative.media_cache import find_cache, realign_from_cache

    async def _wrap(db: Database) -> None:
        rows = await db.fetch(
            """
            SELECT regexp_replace(video_url, '^.*v=', '') AS vid,
                   raw_captions_vtt AS vtt,
                   raw->'media'->'isi'->>'etag' AS etag
            FROM meetings
            WHERE municipality_slug = $1 AND video_url IS NOT NULL
              AND raw_captions_vtt IS NOT NULL
            ORDER BY started_at DESC
            """,
            city,
        )
        if limit:
            rows = rows[:limit]
        seen = patched = skipped = 0
        for r in rows:
            paths = find_cache(r["vid"], r["etag"])
            if not paths:
                continue
            seen += 1
            try:
                meta = await asyncio.to_thread(
                    realign_from_cache, paths, r["vtt"], force)
            except Exception as exc:
                console.print(f"[yellow]realign {r['vid']}: {exc}[/yellow]")
                skipped += 1
                continue
            if meta is None:
                skipped += 1
                continue
            patched += 1
            console.print(
                f"  {r['vid']}: {meta.get('align_offset_previous')} -> "
                f"{meta['caption_offset_s']}s "
                f"(score={meta['align_score']} prom={meta['align_prominence']})"
            )
        console.print(
            f"[green]realign-media-offsets[/green]: cached={seen} "
            f"patched={patched} left_alone={skipped}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("apply-panel-attribution")
@click.option("--city", type=click.Choice(("edmonton",)), default="edmonton")
@click.pass_context
def cmd_apply_panel_attribution(ctx: click.Context, city) -> None:
    """Stage 9 — AUDIT caption attributions against the panel timeline.

    Attribution from the panel happens inside the collapse pipeline (the
    timeline feeds block-alternation as a floor-owner source during
    reparse/fetch); this stage only compares direct text attributions
    against the covering interval and logs disagreements for review. It
    never writes.
    """
    from .legislative.edmonton_panel_ocr import apply_panel_attribution as _apply

    async def _wrap(db: Database) -> None:
        stats = await _apply(db, city_slug=city)
        console.print(
            f"[green]apply-panel-attribution[/green]: meetings={stats.meetings_seen} "
            f"disagreements={stats.disagreements} no_interval={stats.skipped_no_interval}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("enrich-edmonton-minutes")
@click.option("--limit", type=int, default=None,
              help="Max meetings to process (default: all video-matched).")
@click.option("--delay", type=float, default=1.0)
@click.pass_context
def cmd_enrich_edmonton_minutes(ctx: click.Context, limit, delay) -> None:
    """Hydrate + parse eScribe minutes; FK-resolve 'The Chair' caption turns.

    Fetches each video-matched meeting's server-rendered minutes page once
    (cached in raw_minutes_html), parses chair/attendance/delegation into
    meetings.raw->'minutes', and attributes Chair-macro caption speeches to
    the roll-call-conducting member at confidence 0.8.
    """
    from .legislative.edmonton_minutes import enrich_minutes as _enrich

    async def _wrap(db: Database) -> None:
        stats = await _enrich(db, limit=limit, delay=delay)
        console.print(
            f"[green]enrich-edmonton-minutes[/green]: seen={stats.meetings_seen} "
            f"fetched={stats.fetched} fails={stats.fetch_failures} "
            f"chairs={stats.chairs_found} chair_turns_resolved={stats.chair_turns_resolved} "
            f"per_chair={stats.per_chair}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("reparse-meeting-captions")
@click.option("--city", type=click.Choice(_ESCRIBE_CITY_CHOICES), default="all")
@click.pass_context
def cmd_reparse_meeting_captions(ctx: click.Context, city) -> None:
    """Rebuild caption speeches from stored VTTs (no network).

    Use after parser / segmentation / truecasing changes. Deletes and
    re-inserts each meeting's speeches (chunks cascade; new rows re-enter
    the chunk queue). Re-run resolve-meeting-caption-speakers after.
    """
    from .legislative.youtube_captions import reparse_meeting_captions as _reparse

    async def _wrap(db: Database) -> None:
        stats = await _reparse(db, city_slug=city)
        console.print(
            f"[green]reparse-meeting-captions[/green]: cities={stats.cities_processed} "
            f"meetings={stats.meetings_seen} reparsed={stats.captions_fetched} "
            f"speeches={stats.speeches_inserted} warns={stats.parse_warnings} "
            f"attribution={stats.attribution_counts}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("fetch-meeting-captions")
@click.option("--city", type=click.Choice(_ESCRIBE_CITY_CHOICES), default="all")
@click.option("--limit", type=int, default=3,
              help="Cap meetings per city. Default 3 — caption fetches are slow + rate-limited.")
@click.option("--delay", type=float, default=30.0,
              help="Seconds between yt-dlp invocations.")
@click.pass_context
def cmd_fetch_meeting_captions(ctx: click.Context, city, limit, delay) -> None:
    """Stage 6 — yt-dlp auto-captions VTT → speeches rows.

    Speech rows land with politician_id=NULL + confidence=0.0; Stage 7
    fills in attribution. Downstream chunk-and-embed-speeches picks up
    level='municipal' rows automatically.
    """
    from .legislative.youtube_captions import fetch_meeting_captions as _fetch

    async def _wrap(db: Database) -> None:
        stats = await _fetch(db, city_slug=city, limit=limit, delay=delay)
        console.print(
            f"[green]fetch-meeting-captions[/green]: cities={stats.cities_processed} "
            f"seen={stats.meetings_seen} captions={stats.captions_fetched} "
            f"speeches_inserted={stats.speeches_inserted} updated={stats.speeches_updated} "
            f"warns={stats.parse_warnings} fails={len(stats.fetch_failures)}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("resolve-meeting-caption-speakers")
@click.option("--city", type=click.Choice(_ESCRIBE_CITY_CHOICES), default="all")
@click.pass_context
def cmd_resolve_meeting_caption_speakers(ctx: click.Context, city) -> None:
    """Stage 7 — best-effort speaker FK for caption-derived speeches.

    Mayor / 'her worship' role tokens → mayor politician.id (confidence 0.7).
    'Councillor SMITH' → surname-match against Open North roster (0.7
    when unique, 0.5 when ambiguous). Otherwise politician_id=NULL.
    """
    from .legislative.youtube_captions import resolve_meeting_caption_speakers as _resolve

    async def _wrap(db: Database) -> None:
        stats = await _resolve(db, city_slug=city)
        console.print(
            f"[green]resolve-meeting-caption-speakers[/green]: cities={stats.cities_processed} "
            f"resolved={stats.speakers_resolved} unresolved={stats.speakers_unresolved}"
        )
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("run-scrape-worker")
@click.pass_context
def cmd_scrape_worker(ctx: click.Context) -> None:
    """Run the Apify scrape worker daemon.

    Long-running. Each tick: (1) dispatch_due_subscriptions finds saved
    searches whose scrape cadence is due and creates scrape_jobs +
    places credit holds; (2) run_queued_jobs drains the queue,
    calling per-platform actors and committing or releasing holds.
    Respects SCRAPE_DAILY_USD_CAP as a circuit breaker against
    runaway Apify spend.
    """
    from . import scrape_worker as _sw
    asyncio.run(_sw.main())


@cli.command("dispatch-scrapes")
@click.pass_context
def cmd_dispatch_scrapes(ctx: click.Context) -> None:
    """One tick of the scrape dispatcher (no daemon).

    Useful for testing the cadence + credit-hold path without running
    the long daemon. Equivalent to one inner iteration of
    run-scrape-worker.
    """
    from .scrape_worker import dispatch_due_subscriptions

    async def _wrap(db: Database) -> None:
        stats = await dispatch_due_subscriptions(db)
        console.print(f"[green]dispatch-scrapes[/green]: {stats}")
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("run-scrape-jobs")
@click.option("--limit", type=int, default=5, show_default=True,
              help="Maximum number of queued jobs to drain in this call.")
@click.pass_context
def cmd_run_scrape_jobs(ctx: click.Context, limit: int) -> None:
    """Drain up to N queued scrape jobs (no daemon).

    Honors SCRAPE_DAILY_USD_CAP; will stop early if hit. Useful for
    one-off draining + verification runs.
    """
    from .scrape_worker import run_queued_jobs

    async def _wrap(db: Database) -> None:
        stats = await run_queued_jobs(db, limit=limit)
        console.print(f"[green]run-scrape-jobs[/green]: {stats}")
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("poll-scrape-costs")
@click.pass_context
def cmd_poll_scrape_costs(ctx: click.Context) -> None:
    """One tick of the Apify cost-finalization poller.

    Re-fetches usageTotalUsd for succeeded scrape_jobs whose billing
    settled after the sync run returned (apidojo/tweet-scraper is the
    canonical culprit; Apify reports 0 sync, settles minutes later).
    Honors SCRAPE_COST_POLL_DELAY_MIN (default 5min) and processes up
    to SCRAPE_COST_POLL_BATCH (default 20) rows. Wraps a single call
    of the same logic that runs every tick inside run-scrape-worker.
    """
    from .scrape_worker import poll_apify_run_costs

    async def _wrap(db: Database) -> None:
        stats = await poll_apify_run_costs(db)
        console.print(f"[green]poll-scrape-costs[/green]: {stats}")
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


@cli.command("scrape-politician")
@click.option("--politician-id", required=True, help="UUID of politicians.id")
@click.option("--platform", required=True,
              type=click.Choice(["twitter", "bluesky", "instagram", "mastodon"]),
              help="Platform to scrape; must be in v1-supported list.")
@click.option("--user-id", required=True,
              help="UUID of private.users.id to bill (admin testing: use the admin user).")
@click.option("--kind", "scrape_kind", default="monitoring", show_default=True,
              type=click.Choice(["monitoring", "preflight", "archive"]),
              help="Job kind. preflight = profile probe only; archive = deep history.")
@click.option("--post-hint", type=int, default=None,
              help="Optional lifetime post count hint for archive pricing.")
@click.pass_context
def cmd_scrape_politician(
    ctx: click.Context,
    politician_id: str,
    platform: str,
    user_id: str,
    scrape_kind: str,
    post_hint: Optional[int],
) -> None:
    """Enqueue + immediately run one scrape job.

    For operator verification and one-shot user-initiated scrapes
    (archive, manual refresh). The job is created with
    trigger_source='admin' for monitoring/preflight kinds and
    'user_oneshot' for archive — the credit hold + commit/release
    discipline is identical regardless.
    """
    from .scrape_worker import one_shot_scrape

    async def _wrap(db: Database) -> None:
        out = await one_shot_scrape(
            db,
            user_id=user_id,
            politician_id=politician_id,
            platform=platform,
            scrape_kind=scrape_kind,
            post_hint=post_hint,
        )
        if not out.get("ok"):
            console.print(f"[red]scrape-politician failed[/red]: {out}")
            return
        console.print(f"[green]scrape-politician[/green]: {out}")
    asyncio.run(_run(_wrap, ctx.obj["dsn"]))


if __name__ == "__main__":
    try:
        cli(obj={})
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted[/yellow]")
        sys.exit(130)
