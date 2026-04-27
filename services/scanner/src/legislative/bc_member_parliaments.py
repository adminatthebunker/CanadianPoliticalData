"""BC per-parliament terms enricher.

Background: ``scripts/bc-enrich-historical-mlas.py`` already inserts
~376 historical BC MLAs into ``politicians`` keyed on
``lims_member_id``. But the existing pipeline doesn't insert
``politician_terms`` rows for the (member, parliament) edges, so
``politician_terms`` carries only ~98 BC rows (the current-session
ingest from Open North + a few presiding-officer seeds). That's fine
for the current Hansard corpus (P38-S4 → P43-S2) because BC's
SpeakerLookup uses ``lims_member_id`` for exact-int FK matching and
hits 85-96 % across all sessions on name/initial alone — but it
leaves us without a date-windowed disambiguation path for any
pre-P38 Hansard backfill or for surnames that collide across eras.

This module fills that gap by querying LIMS GraphQL's
``allMemberParliaments`` connection (single query, ~750 edges) and
inserting one ``politician_terms`` row per (member, parliament) edge
with ``source = 'lims.leg.bc.ca:parliament-{N}'``. Mirrors AB's
``ingest-ab-former-mlas`` legl-keyed term shape and ON's
``ingest-on-former-mpps`` `parliament-N` pattern.

LIMS GraphQL is a public read-only API (no auth, no rate limit
documented). The single ``allMemberParliaments`` query returns ~75 KB
of JSON in one round trip — no pagination needed at this scale.

Idempotency: politician_terms upserted on (politician_id, office,
started_at, source). Re-running is a no-op.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field as dc_field
from datetime import date, datetime, timezone
from typing import Optional

import httpx

from ..db import Database

log = logging.getLogger(__name__)

LIMS_GRAPHQL_URL = "https://lims.leg.bc.ca/graphql"
REQUEST_TIMEOUT = 60

# Pull every (memberId, parliamentId, parliament number, parliament
# dates) edge in one go. The connection holds 750 rows as of
# 2026-04-27 — easily fits in one response, no pagination.
_QUERY = """
{
  allMemberParliaments {
    totalCount
    nodes {
      memberId
      parliamentId
      parliamentByParliamentId {
        number
        startDate
        endDate
      }
    }
  }
}
"""


@dataclass
class _Edge:
    member_id: int          # lims_member_id
    parliament: int         # parliament number (1..43)
    started_at: Optional[date]
    ended_at: Optional[date]


@dataclass
class Stats:
    edges_fetched: int = 0
    edges_with_dates: int = 0
    politicians_matched: int = 0
    politicians_missing: int = 0
    terms_inserted: int = 0
    terms_skipped_existing: int = 0
    missing_lims_ids: list[int] = dc_field(default_factory=list)


async def enrich_bc_member_parliaments(db: Database) -> Stats:
    """Stamp politician_terms for every (member, parliament) edge from LIMS.

    Lookup chain:
      1. GraphQL ``allMemberParliaments`` → 750 edges with dates.
      2. ``politicians`` table (province_territory='BC',
         lims_member_id IS NOT NULL) → maps lims_member_id → our UUID.
      3. Insert one ``politician_terms`` row per (member, parliament)
         that doesn't already have one for that
         (politician_id, started_at, source) triple.

    Members in the GraphQL response that don't have a corresponding
    politicians row (lims_member_id missing from our table) are
    counted in ``Stats.politicians_missing`` and logged. Use
    ``scripts/bc-enrich-historical-mlas.py`` to backfill those before
    rerunning this command, so the (member, parliament) terms can
    attach.
    """
    stats = Stats()

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        r = await client.post(LIMS_GRAPHQL_URL, json={"query": _QUERY})
        r.raise_for_status()
        payload = r.json()

    nodes = (
        payload.get("data", {})
               .get("allMemberParliaments", {})
               .get("nodes", [])
    )

    edges: list[_Edge] = []
    for n in nodes:
        try:
            mid = int(n["memberId"])
        except (TypeError, ValueError, KeyError):
            continue
        parl = (n.get("parliamentByParliamentId") or {})
        try:
            parl_num = int(parl["number"])
        except (TypeError, ValueError, KeyError):
            continue
        start_raw = parl.get("startDate")
        end_raw = parl.get("endDate")
        try:
            started = date.fromisoformat(start_raw) if start_raw else None
            ended = date.fromisoformat(end_raw) if end_raw else None
        except (TypeError, ValueError):
            continue
        edges.append(_Edge(
            member_id=mid, parliament=parl_num,
            started_at=started, ended_at=ended,
        ))
    stats.edges_fetched = len(edges)
    stats.edges_with_dates = sum(1 for e in edges if e.started_at is not None)
    log.info(
        "bc_member_parliaments: fetched %d edges (%d with dates)",
        stats.edges_fetched, stats.edges_with_dates,
    )

    # Map lims_member_id → politicians.id (UUID).
    existing_rows = await db.fetch(
        """
        SELECT id::text AS id, lims_member_id
          FROM politicians
         WHERE province_territory = 'BC'
           AND level = 'provincial'
           AND lims_member_id IS NOT NULL
        """
    )
    lims_to_pol: dict[int, str] = {
        int(r["lims_member_id"]): r["id"] for r in existing_rows
    }

    missing: set[int] = set()
    for edge in edges:
        pol_id = lims_to_pol.get(edge.member_id)
        if pol_id is None:
            missing.add(edge.member_id)
            continue
        stats.politicians_matched += 1
        if edge.started_at is None:
            # No usable date span — skip; the LIMS record is
            # incomplete and the term wouldn't be useful for
            # date-windowed resolution.
            continue

        start_dt = datetime(
            edge.started_at.year, edge.started_at.month, edge.started_at.day,
            tzinfo=timezone.utc,
        )
        end_dt = (
            datetime(
                edge.ended_at.year, edge.ended_at.month, edge.ended_at.day,
                23, 59, 59, tzinfo=timezone.utc,
            )
            if edge.ended_at else None
        )
        source = f"lims.leg.bc.ca:parliament-{edge.parliament}"

        existing = await db.fetchrow(
            """
            SELECT 1 FROM politician_terms
             WHERE politician_id = $1::uuid
               AND office = 'MLA'
               AND source = $2
               AND started_at = $3
            """,
            pol_id, source, start_dt,
        )
        if existing is not None:
            stats.terms_skipped_existing += 1
            continue
        await db.execute(
            """
            INSERT INTO politician_terms
                (politician_id, office, level, province_territory,
                 started_at, ended_at, source)
            VALUES
                ($1::uuid, 'MLA', 'provincial', 'BC',
                 $2, $3, $4)
            """,
            pol_id, start_dt, end_dt, source,
        )
        stats.terms_inserted += 1

    stats.politicians_missing = len(missing)
    stats.missing_lims_ids = sorted(missing)[:20]  # sample for logging

    log.info(
        "bc_member_parliaments: matched=%d missing_pols=%d "
        "terms_inserted=%d terms_skipped=%d "
        "missing_lims_id_sample=%s",
        stats.politicians_matched, stats.politicians_missing,
        stats.terms_inserted, stats.terms_skipped_existing,
        stats.missing_lims_ids,
    )
    return stats
