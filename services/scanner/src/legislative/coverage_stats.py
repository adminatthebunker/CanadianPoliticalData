"""Refresh the per-jurisdiction stats that drive /coverage.

`jurisdiction_sources` (migration 0019) was seeded with hardcoded status
flags and zero counts. The public coverage page reads those rows as-is,
so flipping Hansard from "partial" to "live" after a real ingest
requires this refresher to run. Keeping it here — offline, SQL-only —
lets the admin re-trigger it after any ingest job.

The refresh is purely derivative:
  - `speeches_count` = rows in `speeches` for this level+prov.
  - `politicians_count` = rows in `politicians` for this level+prov.
  - `bills_count` = rows in `bills` for this level+prov.
  - `hansard_status` flips to 'live' if we have ≥ 50 k speeches in that
    jurisdiction, 'partial' if 1-49k, else left alone.
  - `votes_count` = rows in `votes` for this level+prov.
  - `votes_status` flips to 'live' if ≥ 100 votes, 'partial' if 1-99,
    else 'none' (added 2026-04-30 once 0018 votes shipped + 11,784 rows
    landed across federal + 8 provinces + NT).
  - `bills_status` flips to 'live' if ≥ 500 bills, 'partial' if 1-499,
    else 'none' (added 2026-04-30 alongside the federal historical
    backfill from 35-1 to 43-2). The 'blocked' editorial flag is
    preserved (PE, YT) so a re-derive doesn't downgrade a known-blocker.
  - `last_verified_at` = now().

Status flags for committees are NOT touched — those remain editorial
judgements (e.g. "PE is blocked by a WAF") that don't flow from row
counts. Edit them directly in SQL or via a future migration.
"""
from __future__ import annotations

import logging
from typing import Optional

from ..db import Database

log = logging.getLogger(__name__)

# Mapping from jurisdiction_sources.jurisdiction code → (level, province_territory)
# filter pair used against speeches / politicians / bills.
JURISDICTION_FILTER: dict[str, tuple[str, Optional[str]]] = {
    "federal": ("federal", None),
    "AB": ("provincial", "AB"),
    "BC": ("provincial", "BC"),
    "MB": ("provincial", "MB"),
    "NB": ("provincial", "NB"),
    "NL": ("provincial", "NL"),
    "NS": ("provincial", "NS"),
    "NT": ("provincial", "NT"),
    "NU": ("provincial", "NU"),
    "ON": ("provincial", "ON"),
    "PE": ("provincial", "PE"),
    "QC": ("provincial", "QC"),
    "SK": ("provincial", "SK"),
    "YT": ("provincial", "YT"),
}


def _hansard_status(speech_count: int) -> Optional[str]:
    """Derive hansard_status from speech count. Returns None if we
    shouldn't touch the existing value (e.g. blocked jurisdictions)."""
    if speech_count >= 50_000:
        return "live"
    if speech_count >= 1_000:
        return "partial"
    return None


def _votes_status(votes_count: int) -> str:
    """Derive votes_status from votes count.

    Threshold rationale: federal has ~4500, QC ~3000, NS ~2500, ON ~800,
    AB ~600, BC ~250 — all well above 100 (live). MB at 47, NT at 31,
    NL at 2 land in partial. NB/NU/SK/PE/YT at 0 → none.
    """
    if votes_count >= 100:
        return "live"
    if votes_count >= 1:
        return "partial"
    return "none"


def _bills_status(bills_count: int) -> str:
    """Derive bills_status from bills count.

    Threshold rationale: bills are dense compared to votes (every motion
    progresses through multiple readings, each tracked as a row). Live
    legislatures regularly have 500-15K bills in their archive — federal
    targets ~10-15K post-historical-backfill, AB has 11K, NS has 3.5K,
    BC has 2.3K, NB/NL ~1.2K. The 500-row floor for 'live' separates
    "we have a real archive" from "we have a current-session sliver"
    (federal pre-backfill state at 412 was correctly 'partial'). MB at
    81 / ON at 111 / NT at 20 / NU at 4 land in partial (technically
    live datasets but too sparse to be definitive yet — Hansard chains
    are seeded but historical bills weren't fully ingested). PE/SK/YT
    at 0 → none/blocked respectively.
    """
    if bills_count >= 500:
        return "live"
    if bills_count >= 1:
        return "partial"
    return "none"


async def refresh_coverage_stats(db: Database) -> dict[str, dict[str, int]]:
    """Recompute jurisdiction_sources counts from live tables.

    Returns a per-jurisdiction report keyed by jurisdiction code, each
    value being a dict of before/after deltas.
    """
    report: dict[str, dict[str, int]] = {}

    for code, (level, prov) in JURISDICTION_FILTER.items():
        # Count live rows. prov=NULL means no province filter (federal).
        if prov is None:
            speeches = await db.fetchval(
                "SELECT count(*) FROM speeches WHERE level = $1", level,
            )
            pols = await db.fetchval(
                "SELECT count(*) FROM politicians WHERE level = $1", level,
            )
            bills_ct = await db.fetchval(
                "SELECT count(*) FROM bills WHERE level = $1", level,
            )
            votes_ct = await db.fetchval(
                "SELECT count(*) FROM votes WHERE level = $1", level,
            )
        else:
            speeches = await db.fetchval(
                "SELECT count(*) FROM speeches WHERE level = $1 AND province_territory = $2",
                level, prov,
            )
            pols = await db.fetchval(
                "SELECT count(*) FROM politicians WHERE level = $1 AND province_territory = $2",
                level, prov,
            )
            bills_ct = await db.fetchval(
                "SELECT count(*) FROM bills WHERE level = $1 AND province_territory = $2",
                level, prov,
            )
            votes_ct = await db.fetchval(
                "SELECT count(*) FROM votes WHERE level = $1 AND province_territory = $2",
                level, prov,
            )

        current = await db.fetchrow(
            """
            SELECT speeches_count, politicians_count, bills_count,
                   votes_count, hansard_status, votes_status, bills_status
              FROM jurisdiction_sources
             WHERE jurisdiction = $1
            """,
            code,
        )
        if current is None:
            log.warning("jurisdiction %s not in jurisdiction_sources; skipping", code)
            continue

        new_hansard = _hansard_status(speeches)
        # Don't downgrade from 'blocked' — that's editorial.
        if current["hansard_status"] == "blocked":
            new_hansard = "blocked"
        # Don't touch if no signal.
        if new_hansard is None:
            new_hansard = current["hansard_status"]

        new_votes_status = _votes_status(votes_ct)
        # Preserve 'blocked' editorial flag for votes too.
        if current["votes_status"] == "blocked":
            new_votes_status = "blocked"

        new_bills_status = _bills_status(bills_ct)
        # Preserve 'blocked' editorial flag for bills too (PE, YT).
        if current["bills_status"] == "blocked":
            new_bills_status = "blocked"

        await db.execute(
            """
            UPDATE jurisdiction_sources
               SET speeches_count    = $2,
                   politicians_count = $3,
                   bills_count       = $4,
                   votes_count       = $5,
                   hansard_status    = $6,
                   votes_status      = $7,
                   bills_status      = $8,
                   last_verified_at  = now(),
                   updated_at        = now()
             WHERE jurisdiction = $1
            """,
            code, speeches, pols, bills_ct, votes_ct,
            new_hansard, new_votes_status, new_bills_status,
        )

        report[code] = {
            "speeches": speeches,
            "politicians": pols,
            "bills": bills_ct,
            "votes": votes_ct,
            "hansard_status": new_hansard,
            "votes_status": new_votes_status,
            "bills_status": new_bills_status,
            "prev_speeches": current["speeches_count"] or 0,
            "prev_bills": current["bills_count"] or 0,
            "prev_votes": current["votes_count"] or 0,
            "prev_hansard_status": current["hansard_status"],
            "prev_votes_status": current["votes_status"],
            "prev_bills_status": current["bills_status"],
        }
        log.info(
            "coverage %s: speeches %d→%d politicians→%d bills %d→%d votes %d→%d "
            "hansard %s→%s votes %s→%s bills %s→%s",
            code,
            current["speeches_count"] or 0, speeches,
            pols,
            current["bills_count"] or 0, bills_ct,
            current["votes_count"] or 0, votes_ct,
            current["hansard_status"], new_hansard,
            current["votes_status"], new_votes_status,
            current["bills_status"], new_bills_status,
        )

    return report
