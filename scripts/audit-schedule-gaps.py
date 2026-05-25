#!/usr/bin/env python3
"""Audit `scanner_jobs_catalog` vs `scanner_schedules` for latent gaps.

Finds commands registered in `services/scanner/src/jobs_catalog.py::COMMANDS`
that have no corresponding row in `scanner_schedules`. Categorises each
gap by the likely "should this be scheduled?" heuristic so the operator
can act on the HIGH bucket quickly.

Motivation: cycle 2026-05-21 surfaced three latent "code shipped, schedule
forgotten" instances in a single session — `resolve-qc-speakers-dated`
(shipped 2026-04-27, never scheduled), `ingest-qc-former-mnas` (same
shape), and earlier `resolve-role-only-presiding-officers` (SK slot
missed until 2026-05-14). Each cost ~10K-row attribution misses for as
long as the gap persisted. This script makes the pattern findable.

Usage:
    python3 scripts/audit-schedule-gaps.py
    docker exec sw-db psql -U sw -d sovereignwatch -t -c \\
        "SELECT DISTINCT command FROM scanner_schedules ORDER BY 1" \\
        | python3 scripts/audit-schedule-gaps.py --stdin

The default mode queries the live DB via `docker exec sw-db psql ...`.
"""
from __future__ import annotations

import argparse
import ast
import subprocess
import sys
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
CATALOG_PATH = REPO_ROOT / "services" / "scanner" / "src" / "jobs_catalog.py"


def load_catalog_keys() -> dict[str, dict[str, str]]:
    """Parse jobs_catalog.py and return {command: metadata} for COMMANDS."""
    tree = ast.parse(CATALOG_PATH.read_text())
    for node in tree.body:
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "COMMANDS"
        ):
            commands: dict[str, dict[str, str]] = {}
            if isinstance(node.value, ast.Dict):
                for k_node, v_node in zip(node.value.keys, node.value.values):
                    key = ast.literal_eval(k_node)
                    meta: dict[str, str] = {}
                    if isinstance(v_node, ast.Dict):
                        for kk, vv in zip(v_node.keys, v_node.values):
                            if isinstance(kk, ast.Constant) and isinstance(vv, ast.Constant):
                                meta[kk.value] = vv.value
                    commands[key] = meta
            return commands
    raise RuntimeError("Couldn't find COMMANDS in jobs_catalog.py")


def query_scheduled_commands() -> set[str]:
    """Return the set of distinct command values from scanner_schedules."""
    result = subprocess.run(
        [
            "docker", "exec", "sw-db", "psql",
            "-U", "sw", "-d", "sovereignwatch", "-t", "-A",
            "-c", "SELECT DISTINCT command FROM scanner_schedules ORDER BY 1",
        ],
        capture_output=True, text=True, check=True,
    )
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


# Categorisation heuristics. Mirror the structure of the
# manual triage done during the 2026-05-21 audit.
_LOW_EXACT = {
    "backfill-terms", "ingest-legislatures", "seed-orgs",
    "merge-ab-presiding-stubs", "audit-socials",
    "ingest-mlas", "ingest-mps", "ingest-senators",
    "dispatch-scrapes", "run-scrape-jobs", "poll-scrape-costs",
    "scrape-politician", "probe-missing-socials", "harvest-personal-socials",
}
_LOW_SUBSTR = {"escribe", "caption", "meetings-to-youtube", "councils"}

# Commands manually verified during the 2026-05-21 audit as
# one-shot-complete (target a static historical corpus that doesn't
# grow) or superseded by a cross-jurisdictional successor. Listing them
# here so the audit doesn't keep nagging.
_ONE_SHOT_VERIFIED = {
    # Pre-1993 BC ALL-CAPS only; modern BC Hansard doesn't use the
    # `MR. G.S. WALLACE (Oak Bay)` shape, so no new candidates accrue.
    "resolve-bc-allcaps": "pre-1993 corpus — modern BC doesn't produce ALL-CAPS shape",
    # Description: "Run after pre-P35 historical-roster backfill" —
    # backfill is one-shot, 0 backlog observed 2026-05-21.
    "resolve-bc-speakers-dated": "targets pre-P35 backfill — one-shot complete, no growing input",
    # Federal-only, parens-name presiding-officer. Superseded by
    # `resolve-inline-presiding-officers` (Tier-2 Pass 1, 2026-05-05,
    # cross-jurisdictional) which already runs daily at 23:30 UTC.
    "resolve-acting-speakers": "superseded by resolve-inline-presiding-officers (cross-jurisdictional Tier-2 Pass 1)",
    # Socrata historical backfill; sibling `ingest-ns-bills-rss` (12:00 UTC
    # daily) covers current-session new bills + status/events. Socrata
    # endpoint is for the historical sweep, run manually when needed.
    "ingest-ns-bills": "historical Socrata backfill — sibling ingest-ns-bills-rss covers daily current-session",
    # Both stages run in a single process via `chunk-and-embed-speeches`
    # (cron '0 8 * * *' = 02:00 MT, post-ingest). Atomic chunk→embed
    # ordering is the whole reason that wrapper exists; scheduling these
    # two separately would re-introduce the queue-ordering race the
    # wrapper removes.
    "chunk-speeches": "covered by chunk-and-embed-speeches chain (cron 0 8 * * *)",
    "embed-speech-chunks": "covered by chunk-and-embed-speeches chain (cron 0 8 * * *)",
}


def categorise(cmd: str, meta: dict[str, str]) -> tuple[str, str]:
    """Return (bucket, rationale)."""
    if cmd in _ONE_SHOT_VERIFIED:
        return ("LOW", f"VERIFIED one-shot/superseded — {_ONE_SHOT_VERIFIED[cmd]}")
    if "agent-missing" in cmd:
        return ("BUDGET", "paid LLM — intentionally unscheduled (budget gate)")
    if cmd in _LOW_EXACT:
        return ("LOW", "one-shot / daemon / federal generic")
    if any(s in cmd for s in _LOW_SUBSTR):
        return ("LOW", "municipal / parked")
    if "former" in cmd:
        return ("HIGH", "historical-roster ingester (same shape as ingest-qc-former-mnas fix 2026-05-21)")
    if cmd.endswith("-dated"):
        # Descriptions containing "after ... backfill" are likely
        # one-shot — flag for verification before scheduling.
        desc = meta.get("description", "").lower()
        if "after" in desc and "backfill" in desc:
            return ("MEDIUM", "date-windowed resolver, but description says 'after backfill' — verify it's not one-shot")
        return ("HIGH", "date-windowed resolver (same shape as resolve-qc-speakers-dated fix 2026-05-21)")
    if cmd.startswith("resolve-"):
        return ("HIGH", "speaker resolver — idempotent re-runs catch new ingest")
    if "coverage" in cmd or cmd == "refresh-views":
        return ("HIGH", "coverage / materialized view refresh (TODO Always-on)")
    if "enrich" in cmd or "mlas" in cmd or "mpps" in cmd:
        return ("MEDIUM", "roster enrichment — likely should be daily/weekly")
    if "bills" in cmd or "hansard" in cmd:
        return ("HIGH", "ingester (suspicious gap — most siblings are scheduled)")
    if "chunk" in cmd or "embed" in cmd:
        return ("MEDIUM", "covered by chunk-and-embed-speeches if that's scheduled — check chain")
    return ("MEDIUM", "needs operator eyeball")


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stdin", action="store_true",
        help="Read scheduled commands from stdin (one per line) instead of querying DB.",
    )
    parser.add_argument(
        "--format", choices=("human", "tsv"), default="human",
        help="Output format. 'human' (default) groups by bucket; 'tsv' is machine-readable.",
    )
    args = parser.parse_args(argv)

    catalog = load_catalog_keys()
    if args.stdin:
        scheduled = {line.strip() for line in sys.stdin if line.strip()}
    else:
        try:
            scheduled = query_scheduled_commands()
        except (subprocess.CalledProcessError, FileNotFoundError) as exc:
            print(f"error: failed to query scheduled commands: {exc}", file=sys.stderr)
            print("Hint: pass --stdin and pipe in the list of scheduled commands.", file=sys.stderr)
            return 2

    unscheduled = sorted(set(catalog.keys()) - scheduled)

    buckets: dict[str, list[tuple[str, str, str]]] = {
        "HIGH": [], "MEDIUM": [], "BUDGET": [], "LOW": [],
    }
    for cmd in unscheduled:
        meta = catalog[cmd]
        bucket, rationale = categorise(cmd, meta)
        buckets[bucket].append((cmd, meta.get("category", ""), rationale))

    if args.format == "tsv":
        print("bucket\tcommand\tcategory\trationale")
        for label in ("HIGH", "MEDIUM", "BUDGET", "LOW"):
            for cmd, cat, rationale in buckets[label]:
                print(f"{label}\t{cmd}\t{cat}\t{rationale}")
        return 0

    headers = {
        "HIGH":   "HIGH — likely latent schedule gap (act on these first)",
        "MEDIUM": "MEDIUM — plausibly should be scheduled, operator eyeball",
        "BUDGET": "BUDGET-GATED — intentionally unscheduled (LLM cost)",
        "LOW":    "LOW — one-shot / daemon / parked / generic-superset",
    }
    print(f"Catalog: {len(catalog)} commands")
    print(f"Scheduled: {len(scheduled)} distinct command values in scanner_schedules")
    print(f"Unscheduled: {len(unscheduled)}\n")
    for label in ("HIGH", "MEDIUM", "BUDGET", "LOW"):
        items = buckets[label]
        print(f"### {headers[label]} ({len(items)})")
        if not items:
            print("  (none)\n")
            continue
        for cmd, cat, rationale in items:
            print(f"  {cmd:40s} [{cat or '-'}]  {rationale}")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
