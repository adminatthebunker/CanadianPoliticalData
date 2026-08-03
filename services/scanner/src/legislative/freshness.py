"""Ingest-freshness sentinel — turns silent data holes into failed jobs.

Motivated by the 2026-08-02 audit: QC had a ~2.5-month Hansard+votes hole
(a dropdown-regex break silently rerouted discovery to the Wayback
fallback), NB had 77 days of late-published transcripts skipped by a
fixed since-window, and NU sat 741 days stale — all while every daily
job reported success, because "succeeded" only means "the command ran",
not "the data is current".

The sentinel cross-checks two independent signals per jurisdiction:

    lag = MAX(bill_events.event_date) - MAX(speeches.spoken_at)

Bill events and speeches come from different upstream surfaces (bill
status trackers vs Hansard transcripts), so a legislature in recess goes
quiet on BOTH, while a broken Hansard pipeline shows bills advancing
with no speeches behind them. That asymmetry is the detector.

Thresholds are per-jurisdiction because publication lag is real and
legitimate in places (NU publishes transcripts ~15 months after the
sitting; NB runs months behind). Those get wide thresholds — the
sentinel is for *pipeline* breakage, not upstream slowness we can't fix.

Exit contract: the Click wrapper exits non-zero when any jurisdiction
breaches, so a breach surfaces as a `failed` scanner job in the admin
panel dashboard (same visibility contract as check-bc-committees-
freshness, the dead-canary precedent).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from ..db import Database

log = logging.getLogger(__name__)

DEFAULT_THRESHOLD_DAYS = 30

# Known upstream publication lag (days) — jurisdictions whose Hansard
# legitimately trails the bill trackers. Values are deliberately roomy;
# the point is catching breakage, not nagging about upstream cadence.
#   NB: transcripts publish ~2-3 months after sitting.
#   NU: transcripts publish ~15+ months after sitting (observed:
#       May 2024 sittings uploaded Aug/Sep 2025). As of 2026-08-02 the
#       full upstream listing ends at 2024-05-31 (lag 741d vs bill
#       events) — verified NOT a pipeline bug (full re-scan found
#       nothing newer). Threshold sits just above that so the sentinel
#       stays quiet at known-good but fires if the lag keeps growing.
THRESHOLD_OVERRIDES: dict[str, int] = {
    "NB": 150,
    "NU": 800,
}

# Jurisdictions with no Hansard pipeline at all (blocked upstream) —
# skip rather than alarm on every run. Keep in sync with
# jurisdiction_sources.hansard_status = 'blocked'/'none'.
SKIP_JURISDICTIONS: set[str] = {"PE", "YT"}


@dataclass
class FreshnessRow:
    jurisdiction: str
    latest_speech: Optional[str]
    latest_bill_event: Optional[str]
    lag_days: Optional[int]
    threshold_days: int
    breached: bool


async def check_ingest_freshness(
    db: Database,
    *,
    threshold_days: int = DEFAULT_THRESHOLD_DAYS,
) -> list[FreshnessRow]:
    """Compute per-jurisdiction speech-vs-bill-event lag and flag breaches."""
    rows = await db.fetch(
        """
        WITH sp AS (
            SELECT COALESCE(province_territory, 'federal') AS jur,
                   MAX(spoken_at)::date AS latest_speech
              FROM speeches
             GROUP BY 1
        ),
        ev AS (
            SELECT COALESCE(b.province_territory, 'federal') AS jur,
                   MAX(e.event_date)::date AS latest_bill_event
              FROM bill_events e
              JOIN bills b ON b.id = e.bill_id
             GROUP BY 1
        )
        SELECT ev.jur,
               sp.latest_speech,
               ev.latest_bill_event,
               (ev.latest_bill_event - sp.latest_speech) AS lag_days
          FROM ev
          LEFT JOIN sp USING (jur)
         ORDER BY ev.jur
        """
    )
    out: list[FreshnessRow] = []
    for r in rows:
        jur = r["jur"]
        if jur in SKIP_JURISDICTIONS:
            continue
        limit = THRESHOLD_OVERRIDES.get(jur, threshold_days)
        lag = r["lag_days"]
        # No speeches at all for a jurisdiction with bill events is a
        # breach in its own right (unless skipped above).
        breached = (lag is None) or (lag > limit)
        out.append(
            FreshnessRow(
                jurisdiction=jur,
                latest_speech=str(r["latest_speech"]) if r["latest_speech"] else None,
                latest_bill_event=(
                    str(r["latest_bill_event"]) if r["latest_bill_event"] else None
                ),
                lag_days=lag,
                threshold_days=limit,
                breached=breached,
            )
        )
    return out
