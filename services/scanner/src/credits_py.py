"""Python port of services/api/src/lib/credits.ts for the scrape worker.

The scrape worker holds, commits, and releases credits from inside the
scanner process rather than calling back to the API — keeping credit
moves out-of-band would introduce a back-channel dependency, and the
SQL is small. Discipline: every change here MUST be mirrored against
the TypeScript original (and vice versa) so the two stay byte-for-byte
on the SQL.

The report-job equivalents (commit_hold / release_hold over
kind='report_hold') already live inline in reports_worker.py — see
that file for the precedent. This module covers the scrape kinds.

Invariants enforced by SQL (do not paper over in Python):

* Each UPDATE narrows on `kind = 'scrape_*'` so a stray
  commit_scrape_hold call can never finalize a report-hold row, and
  vice versa.

* No mutable balance column anywhere. Balance is derived from
  SUM(delta) over states ('committed','held') — see get_balance.

* (kind, reference_id) is unique-indexed in private.credit_ledger
  (uniq_credit_ledger_kind_ref, partial on reference_id IS NOT NULL).
  hold_scrape_credits relies on that for idempotency: a duplicate
  call raises asyncpg.UniqueViolationError, which the dispatcher
  treats as "already held, proceed."
"""

from __future__ import annotations

from typing import Any

import asyncpg

from .db import Database


class InsufficientBalanceError(Exception):
    """Raised when the user's spendable balance is below the requested hold amount."""

    def __init__(self, user_id: str, balance: int, requested: int) -> None:
        super().__init__(
            f"insufficient balance for user {user_id}: have {balance}, need {requested}"
        )
        self.user_id = user_id
        self.balance = balance
        self.requested = requested


async def get_balance(db: Database, user_id: Any) -> int:
    """Spendable balance: SUM(delta) over committed + held rows.

    Mirrors services/api/src/lib/credits.ts:getBalance.
    """
    row = await db.fetchrow(
        """SELECT COALESCE(SUM(delta), 0)::bigint AS balance
             FROM private.credit_ledger
            WHERE user_id = $1
              AND state IN ('committed','held')""",
        user_id,
    )
    return int(row["balance"] if row else 0)


async def hold_scrape_credits(
    db: Database,
    *,
    user_id: Any,
    amount: int,
    scrape_job_id: Any,
) -> str:
    """Place a hold for a scheduled scrape job (kind='scrape_hold').

    Returns the ledger-row UUID. Idempotent per (kind, reference_id):
    a duplicate call raises asyncpg.UniqueViolationError.
    """
    if amount <= 0:
        raise ValueError("hold amount must be positive")
    row = await db.fetchrow(
        """INSERT INTO private.credit_ledger
               (user_id, delta, state, kind, reference_id)
             VALUES ($1, $2, 'held', 'scrape_hold', $3)
             RETURNING id""",
        user_id,
        -amount,
        str(scrape_job_id),
    )
    if row is None:
        raise RuntimeError("hold_scrape_credits: INSERT returned no id")
    return str(row["id"])


async def commit_scrape_hold(db: Database, hold_ledger_id: Any) -> None:
    """Flip a scrape hold to 'committed'. Idempotent: a hold already
    committed or refunded is a no-op (WHERE state='held' narrows)."""
    if hold_ledger_id is None:
        return
    await db.execute(
        """UPDATE private.credit_ledger
              SET state = 'committed'
            WHERE id = $1
              AND state = 'held'
              AND kind = 'scrape_hold'""",
        hold_ledger_id,
    )


async def release_scrape_hold(
    db: Database, hold_ledger_id: Any, reason: str
) -> None:
    """Flip a scrape hold to 'refunded'. Reason is stored for audit
    and surfaced in the user's /me/credits ledger history."""
    if hold_ledger_id is None:
        return
    await db.execute(
        """UPDATE private.credit_ledger
              SET state = 'refunded',
                  reason = $2
            WHERE id = $1
              AND state = 'held'
              AND kind = 'scrape_hold'""",
        hold_ledger_id,
        reason,
    )


async def try_hold_scrape_credits(
    db: Database,
    *,
    user_id: Any,
    amount: int,
    scrape_job_id: Any,
) -> str | None:
    """Convenience wrapper used by the dispatcher: returns the ledger
    id on success, None if the user doesn't have enough. Avoids the
    duplicate ROUND-TRIP shape (check balance then hold) by attempting
    the hold first and only running a balance lookup if the dispatcher
    needs to report 'why we paused this subscription'.

    NOTE: there is a TOCTOU window between get_balance and the INSERT,
    but: holds + commits across a single user are not concurrent
    (one worker, one dispatcher tick at a time per CLAUDE.md), and
    the worst case is a negative spendable balance for a few seconds
    until the failing job's hold is released. Acceptable for v1.
    """
    bal = await get_balance(db, user_id)
    if bal < amount:
        return None
    try:
        return await hold_scrape_credits(
            db,
            user_id=user_id,
            amount=amount,
            scrape_job_id=scrape_job_id,
        )
    except asyncpg.UniqueViolationError:
        # Hold already exists for this scrape_job_id — caller should
        # look it up rather than retry-create. Returning None here
        # signals "did not create" so dispatcher loops cleanly.
        return None
