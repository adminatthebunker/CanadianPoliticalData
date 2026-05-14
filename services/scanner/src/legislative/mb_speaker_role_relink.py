"""Backfill `speeches.speaker_role` on already-ingested MB Hansard rows
where the chamber parser left both `politician_id` and `speaker_role`
NULL.

Pure-Python pass — no upstream calls. Walks rows whose `speaker_name_raw`
matches one of the canonical role patterns in `mb_hansard_parse._ROLE_PATTERNS`
and UPDATEs `speaker_role` to the canonical role string. Imports the regex
table from the parser so the relink and future ingests stay byte-for-byte
in sync; adding a new role pattern to the parser automatically widens the
relink's coverage on the next run.

Originally shipped to close the MB chamber-parser empty-role bucket
(~21K rows where MB pre-43L Hansard used `Mr./Madam Deputy Speaker` /
`Mr./Madam Chairperson` shapes the existing `_ROLE_PATTERNS` regexes
didn't catch). Once `speaker_role` is populated, the daily Tier-1
Speaker resolver + Pass-3 role-only resolver attribute the rows by
date-windowed lookup. Idempotent — safe to schedule daily.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from ..db import Database
from .mb_hansard_parse import _clean_speaker, _match_role

log = logging.getLogger(__name__)


@dataclass
class RelinkStats:
    scanned: int = 0
    role_assigned: int = 0
    by_role: dict[str, int] = field(default_factory=dict)


async def relink_mb_speaker_roles(
    db: Database,
    *,
    limit: Optional[int] = None,
    dry_run: bool = False,
) -> RelinkStats:
    """Apply the MB parser's role patterns to existing rows with NULL role.

    Selects MB speeches where `politician_id IS NULL`, `speaker_role` is
    NULL/empty, and `speaker_name_raw` is non-NULL. For each row, runs
    `_match_role(_clean_speaker(raw))` and UPDATEs `speaker_role` when a
    canonical role matches. Returns counts overall + per emitted role.
    """
    stats = RelinkStats()

    rows = await db.fetch(
        """
        SELECT id::text AS id, speaker_name_raw
          FROM speeches
         WHERE province_territory = 'MB'
           AND politician_id IS NULL
           AND (speaker_role IS NULL OR speaker_role = '')
           AND speaker_name_raw IS NOT NULL
         ORDER BY spoken_at
         LIMIT $1
        """,
        limit,
    ) if limit else await db.fetch(
        """
        SELECT id::text AS id, speaker_name_raw
          FROM speeches
         WHERE province_territory = 'MB'
           AND politician_id IS NULL
           AND (speaker_role IS NULL OR speaker_role = '')
           AND speaker_name_raw IS NOT NULL
         ORDER BY spoken_at
        """,
    )

    for row in rows:
        stats.scanned += 1
        role = _match_role(_clean_speaker(row["speaker_name_raw"]))
        if role is None:
            continue
        stats.role_assigned += 1
        stats.by_role[role] = stats.by_role.get(role, 0) + 1
        if not dry_run:
            await db.execute(
                "UPDATE speeches SET speaker_role = $1 WHERE id = $2::uuid",
                role, row["id"],
            )

    log.info(
        "relink_mb_speaker_roles: scanned=%d role_assigned=%d by_role=%s dry_run=%s",
        stats.scanned, stats.role_assigned, stats.by_role, dry_run,
    )
    return stats
