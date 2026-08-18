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
  - `committees_status` flips to 'live' if ≥ 5000 committee speeches,
    'partial' if 1-4999. Below 1, the existing value is preserved —
    AB's existing 'live' is roster-membership-based (not transcript)
    and stays untouched until/unless committee transcripts land there.
    'blocked' is preserved as editorial. Added 2026-05-18 alongside
    federal committee transcripts ingest.
  - `last_verified_at` = now().

Municipal rows (migration 0060) go through the same derivation with a
different filter. They are read from the table rather than hardcoded
here, so adding a city is a seed row rather than a code change.

The filter differs because `speeches` has no city column — the only path
from a speech to a municipality is `speeches.meeting_id` ->
`meetings.municipality_slug`. `bills` and `votes` can't use even that
(`bills.meeting_id` is unpopulated and `votes` has no meeting_id at
all), so they filter on the set of `session_id`s that city's meetings
belong to.
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


def _committees_status(committee_speech_count: int) -> Optional[str]:
    """Derive committees_status from speech_type='committee' row count.

    Returns None when there's no transcript signal (count=0), so callers
    preserve the existing editorial value — AB's pre-existing 'live' is
    membership-roster-based (not transcripts) and shouldn't be downgraded
    by this function until/unless AB committee transcripts ship.

    Thresholds reflect committee data density (denser than votes, much
    less dense than chamber Hansard): ~50 speeches per meeting × ~100
    meetings per session = ~5K speeches as the 'real archive' floor.
    """
    if committee_speech_count >= 5_000:
        return "live"
    if committee_speech_count >= 1:
        return "partial"
    return None


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


async def _count_legislature(
    db: Database, level: str, prov: Optional[str]
) -> dict[str, int]:
    """Row counts for a federal/provincial jurisdiction. prov=None means
    no province filter (federal)."""
    if prov is None:
        where, args = "level = $1", (level,)
    else:
        where, args = "level = $1 AND province_territory = $2", (level, prov)

    return {
        "speeches": await db.fetchval(f"SELECT count(*) FROM speeches WHERE {where}", *args),
        "committee_speeches": await db.fetchval(
            f"SELECT count(*) FROM speeches WHERE {where} AND speech_type = 'committee'",
            *args,
        ),
        "politicians": await db.fetchval(f"SELECT count(*) FROM politicians WHERE {where}", *args),
        "bills": await db.fetchval(f"SELECT count(*) FROM bills WHERE {where}", *args),
        "votes": await db.fetchval(f"SELECT count(*) FROM votes WHERE {where}", *args),
    }


async def _count_municipality(db: Database, slug: str) -> dict[str, int]:
    """Row counts for one municipality (migration 0060).

    Speeches reach a city only through meetings; bills and votes only
    through the sessions those meetings belong to. See module docstring.

    `politicians` is attributed by `politician_terms.source` containing
    the slug — Open North sources look like
    `opennorth:edmonton-city-council` and the Socrata roster like
    `edmonton-socrata:yqff-55ja`. Substring matching is adequate for the
    seeded cities but is NOT a general rule: a future 'grande-prairie'
    row would also match 'county-of-grande-prairie'. Give municipal
    terms a real city column before seeding cities with colliding names.
    """
    session_filter = (
        "session_id IN (SELECT DISTINCT session_id FROM meetings WHERE municipality_slug = $1)"
    )
    return {
        "speeches": await db.fetchval(
            "SELECT count(*) FROM speeches s JOIN meetings m ON m.id = s.meeting_id "
            "WHERE m.municipality_slug = $1",
            slug,
        ),
        "committee_speeches": await db.fetchval(
            "SELECT count(*) FROM speeches s JOIN meetings m ON m.id = s.meeting_id "
            "WHERE m.municipality_slug = $1 AND s.speech_type = 'committee'",
            slug,
        ),
        "politicians": await db.fetchval(
            "SELECT count(DISTINCT politician_id) FROM politician_terms "
            "WHERE level = 'municipal' AND source ILIKE '%' || $1 || '%'",
            slug,
        ),
        "bills": await db.fetchval(
            f"SELECT count(*) FROM bills WHERE level = 'municipal' AND {session_filter}", slug,
        ),
        "votes": await db.fetchval(
            f"SELECT count(*) FROM votes WHERE level = 'municipal' AND {session_filter}", slug,
        ),
    }


async def _apply_counts(
    db: Database, code: str, counts: dict[str, int], report: dict[str, dict[str, int]]
) -> None:
    """Derive statuses from `counts`, write the row, record the delta.

    Shared by legislatures and municipalities — the thresholds and the
    'blocked'-is-editorial preservation rules are identical; only the
    counting filter differs.
    """
    speeches = counts["speeches"]
    committee_speeches = counts["committee_speeches"]
    pols = counts["politicians"]
    bills_ct = counts["bills"]
    votes_ct = counts["votes"]

    current = await db.fetchrow(
        """
        SELECT speeches_count, politicians_count, bills_count,
               votes_count, hansard_status, votes_status, bills_status,
               committees_status
          FROM jurisdiction_sources
         WHERE jurisdiction = $1
        """,
        code,
    )
    if current is None:
        log.warning("jurisdiction %s not in jurisdiction_sources; skipping", code)
        return

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

    new_committees_status = _committees_status(committee_speeches)
    # Preserve editorial values when there's no transcript signal (AB
    # roster-based 'live' stays untouched until AB transcripts ship);
    # 'blocked' is editorial regardless of count.
    if current["committees_status"] == "blocked":
        new_committees_status = "blocked"
    elif new_committees_status is None:
        new_committees_status = current["committees_status"]

    await db.execute(
        """
        UPDATE jurisdiction_sources
           SET speeches_count     = $2,
               politicians_count  = $3,
               bills_count        = $4,
               votes_count        = $5,
               hansard_status     = $6,
               votes_status       = $7,
               bills_status       = $8,
               committees_status  = $9,
               last_verified_at   = now(),
               updated_at         = now()
         WHERE jurisdiction = $1
        """,
        code, speeches, pols, bills_ct, votes_ct,
        new_hansard, new_votes_status, new_bills_status,
        new_committees_status,
    )

    report[code] = {
        "speeches": speeches,
        "committee_speeches": committee_speeches,
        "politicians": pols,
        "bills": bills_ct,
        "votes": votes_ct,
        "hansard_status": new_hansard,
        "votes_status": new_votes_status,
        "bills_status": new_bills_status,
        "committees_status": new_committees_status,
        "prev_speeches": current["speeches_count"] or 0,
        "prev_bills": current["bills_count"] or 0,
        "prev_votes": current["votes_count"] or 0,
        "prev_hansard_status": current["hansard_status"],
        "prev_votes_status": current["votes_status"],
        "prev_bills_status": current["bills_status"],
        "prev_committees_status": current["committees_status"],
    }
    log.info(
        "coverage %s: speeches %d→%d (committee %d) politicians→%d "
        "bills %d→%d votes %d→%d "
        "hansard %s→%s votes %s→%s bills %s→%s committees %s→%s",
        code,
        current["speeches_count"] or 0, speeches, committee_speeches,
        pols,
        current["bills_count"] or 0, bills_ct,
        current["votes_count"] or 0, votes_ct,
        current["hansard_status"], new_hansard,
        current["votes_status"], new_votes_status,
        current["bills_status"], new_bills_status,
        current["committees_status"], new_committees_status,
    )


async def refresh_coverage_stats(db: Database) -> dict[str, dict[str, int]]:
    """Recompute jurisdiction_sources counts from live tables.

    Returns a per-jurisdiction report keyed by jurisdiction code, each
    value being a dict of before/after deltas.
    """
    report: dict[str, dict[str, int]] = {}

    for code, (level, prov) in JURISDICTION_FILTER.items():
        await _apply_counts(db, code, await _count_legislature(db, level, prov), report)

    # Municipalities are table-driven, not hardcoded above: seeding a new
    # city row is enough to bring it into the refresh.
    municipal = await db.fetch(
        "SELECT jurisdiction, municipality_slug FROM jurisdiction_sources "
        " WHERE level = 'municipal' ORDER BY jurisdiction"
    )
    for row in municipal:
        await _apply_counts(
            db, row["jurisdiction"], await _count_municipality(db, row["municipality_slug"]), report
        )

    return report
