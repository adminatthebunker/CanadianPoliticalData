"""Shared forward-incremental helpers for daily-ingest pipelines.

Daily-scheduled pipelines that walk every item in a session are correct
(idempotent upserts) but waste cycles re-processing items that haven't
changed. The pattern this module supports:

  1. Read the highest upstream-event timestamp we've already persisted
     (the high-water mark).
  2. Use that, minus a small overlap buffer for late-arriving upstream
     edits, as the implicit `--since` for the next run.
  3. Each pipeline filters its work to items at-or-after that timestamp.

Important: the high-water is on the **upstream event date**
(`occurred_at` for votes, `introduced_date` for bills, `spoken_at` for
speeches), NOT on our own `updated_at`. Our `updated_at` bumps on every
re-upsert and would collapse the window to zero.

The overlap buffer exists because upstream platforms sometimes back-edit
older items (vote tallies are revised, bill stages get re-stamped). Run
with `since = high_water - overlap` so the next run will catch those
late edits without re-processing the entire corpus.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Optional

import click

from ..db import Database


DEFAULT_OVERLAP_DAYS = 14


async def high_water_timestamp(
    db: Database,
    *,
    table: str,
    timestamp_column: str,
    where: str = "TRUE",
    where_params: Optional[list] = None,
) -> Optional[datetime]:
    """Return MAX(timestamp_column) FROM table WHERE <where>, or None if empty.

    `table` is interpolated literally — pass a trusted constant, not user input.
    `where` is parameterised — pass placeholders ($1, $2, ...) and `where_params`.
    """
    sql = f"SELECT MAX({timestamp_column}) AS hw FROM {table} WHERE {where}"
    row = await db.fetchrow(sql, *(where_params or []))
    if row is None:
        return None
    hw = row["hw"]
    if hw is None:
        return None
    if isinstance(hw, date) and not isinstance(hw, datetime):
        hw = datetime.combine(hw, datetime.min.time(), tzinfo=timezone.utc)
    return hw


async def resolve_since(
    db: Database,
    *,
    explicit_since: Optional[date],
    since_days: Optional[int],
    table: str,
    timestamp_column: str,
    where: str = "TRUE",
    where_params: Optional[list] = None,
    overlap_days: int = DEFAULT_OVERLAP_DAYS,
) -> Optional[date]:
    """Resolve the effective --since for a forward-incremental run.

    Precedence (highest first):
      1. explicit --since flag (caller passed an ISO date)
      2. --since-days flag (caller passed an integer N; resolves to today - N)
      3. DB high-water (max timestamp in the target table) minus overlap_days
      4. None — caller should treat as "full scan"

    Returning a `date` (not datetime) keeps the comparison cheap and
    matches upstream APIs whose filters are date-granular.
    """
    if explicit_since is not None:
        return explicit_since
    if since_days is not None:
        return (datetime.now(timezone.utc) - timedelta(days=int(since_days))).date()
    hw = await high_water_timestamp(
        db,
        table=table,
        timestamp_column=timestamp_column,
        where=where,
        where_params=where_params,
    )
    if hw is None:
        return None
    return (hw - timedelta(days=int(overlap_days))).date()


def forward_options(func):
    """Click decorator pair: --since / --since-days.

    Apply to every Click command that supports forward-incremental mode.
    Both default to None; `resolve_since` does the precedence work.
    """
    func = click.option(
        "--since-days", type=int, default=None,
        help="Forward-incremental: only process items from the last N days "
             "(takes precedence over DB high-water, overridden by --since).",
    )(func)
    func = click.option(
        "--since", "since", type=str, default=None,
        help="Forward-incremental: only process items on/after this ISO date "
             "(YYYY-MM-DD). Wins over --since-days and DB high-water.",
    )(func)
    return func


def parse_iso_date(s: Optional[str]) -> Optional[date]:
    """Lift a Click string argument to a `date`, or None."""
    return date.fromisoformat(s) if s else None


def clamp_since_with_days(
    explicit_since: Optional[date],
    since_days: Optional[int],
) -> Optional[date]:
    """Resolve --since vs --since-days for pipelines that already auto-derive
    a default --since (e.g., Hansard ingesters that fall back to session
    bounds). Use the MAX of (explicit_since, today - since_days), or
    whichever is set. Returns None if neither is set — caller keeps its
    existing default.
    """
    from_days: Optional[date] = None
    if since_days is not None:
        from_days = (datetime.now(timezone.utc) - timedelta(days=int(since_days))).date()
    if explicit_since is not None and from_days is not None:
        return max(explicit_since, from_days)
    return explicit_since if explicit_since is not None else from_days
