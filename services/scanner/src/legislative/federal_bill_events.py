"""Federal bill_events ingester — parl.ca/LegisInfo XML → `bill_events`.

Fills the gap left by `federal_bills.py:18-22` (openparliament.ca doesn't
expose stage timelines). Every other jurisdiction has stage events; until
this module shipped, federal bills had `bill_events.bill_id IS NULL` for
all 5,542 federal rows.

## Source

`https://www.parl.ca/legisinfo/en/bills/xml?parlsession={p}-{s}` returns
the entire bill list for a session as XML — one `<Bill>` element per
bill carrying `BillId` (LEGISinfo's stable internal int — matches
`bills.raw->>'legisinfo_id'` already captured by `federal_bills.py`),
plus inline milestone timestamps:

  * `PassedHouseFirstReadingDateTime`     → first_reading  / event_type=house
  * `PassedHouseSecondReadingDateTime`    → second_reading / event_type=house
  * `PassedHouseThirdReadingDateTime`     → third_reading  / event_type=house
  * `PassedSenateFirstReadingDateTime`    → first_reading  / event_type=senate
  * `PassedSenateSecondReadingDateTime`   → second_reading / event_type=senate
  * `PassedSenateThirdReadingDateTime`    → third_reading  / event_type=senate
  * `ReceivedRoyalAssentDateTime`         → royal_assent   / event_type=NULL

One HTTP GET per session unlocks ~7 stage timestamps × bill-count.
No per-bill detail fetches needed.

## FK match

`BillId` (XML int) ⇄ `bills.raw->>'legisinfo_id'` (string). Bills that
don't exist in the local table (older sessions before the 2026-04-30
historical backfill floor at P37-S1) are simply skipped — counted in
`stats['no_match']` for visibility.

## Idempotency

`bill_events_uniq` constraint covers `(bill_id, stage, event_date,
event_type, committee_name)` with `NULLS NOT DISTINCT`. Re-runs on the
same session emit the same INSERTs and `ON CONFLICT DO NOTHING`s
through. Safe to schedule daily.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional
from xml.etree import ElementTree as ET

import httpx
import orjson

from ..db import Database
from .current_session import current_session

log = logging.getLogger(__name__)

LEGISINFO_ROOT = "https://www.parl.ca/legisinfo/en"
SOURCE_SYSTEM = "legisinfo-bill-events"
REQUEST_TIMEOUT = 60

HEADERS = {
    "User-Agent": "SovereignWatch/1.0 (civic-transparency; +admin@thebunkerops.ca)",
    "Accept": "application/xml",
}

# (XML element name, canonical stage, event_type)
# event_type is the chamber for House/Senate-disambiguated stages, NULL
# (None) for stages that occur once across the whole bill (royal assent).
_MILESTONE_FIELDS: tuple[tuple[str, str, Optional[str]], ...] = (
    ("PassedHouseFirstReadingDateTime",  "first_reading",  "house"),
    ("PassedHouseSecondReadingDateTime", "second_reading", "house"),
    ("PassedHouseThirdReadingDateTime",  "third_reading",  "house"),
    ("PassedSenateFirstReadingDateTime", "first_reading",  "senate"),
    ("PassedSenateSecondReadingDateTime","second_reading", "senate"),
    ("PassedSenateThirdReadingDateTime", "third_reading",  "senate"),
    ("ReceivedRoyalAssentDateTime",      "royal_assent",   None),
)

_STAGE_LABELS: dict[str, str] = {
    "first_reading":  "First reading",
    "second_reading": "Second reading",
    "third_reading":  "Third reading",
    "royal_assent":   "Royal assent",
}


@dataclass
class IngestStats:
    sessions_touched: int = 0
    sessions_skipped: int = 0   # XML fetch failed
    bills_seen: int = 0         # <Bill> elements parsed
    bills_matched: int = 0      # had a corresponding row in bills
    bills_no_match: int = 0     # XML had legisinfo_id we don't know about
    events_attempted: int = 0   # non-empty milestone timestamps
    events_inserted: int = 0    # rows that newly landed in bill_events
    events_existing: int = 0    # ON CONFLICT DO NOTHING
    by_stage: dict[str, int] = field(default_factory=dict)


def _parse_dt(raw: Optional[str]) -> Optional[date]:
    """LEGISinfo timestamps look like '2021-11-22T19:00:00-05:00'."""
    if not raw:
        return None
    raw = raw.strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw).date()
    except ValueError:
        # Fallback: date-only or unexpected shape; just take YYYY-MM-DD.
        try:
            return datetime.strptime(raw[:10], "%Y-%m-%d").date()
        except ValueError:
            return None


def _bill_to_dict(bill_el: ET.Element) -> dict[str, Optional[str]]:
    """Flatten a <Bill> element to {tag: text}. Inner XML is ignored —
    LEGISinfo's bill records are flat, no nested structures we need."""
    out: dict[str, Optional[str]] = {}
    for child in bill_el:
        text = (child.text or "").strip() if child.text else ""
        out[child.tag] = text or None
    return out


async def _fetch_session_xml(
    client: httpx.AsyncClient, parliament: int, session: int,
) -> Optional[bytes]:
    url = f"{LEGISINFO_ROOT}/bills/xml?parlsession={parliament}-{session}"
    try:
        r = await client.get(url, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        return r.content
    except httpx.HTTPError as e:
        log.warning("legisinfo session xml fetch %s: %s", url, e)
        return None


async def _bill_id_index(
    db: Database, *, parliament: int, session: int,
) -> dict[str, str]:
    """Map LEGISinfo BillId (string) → bills.id (uuid string) for one session."""
    rows = await db.fetch(
        """
        SELECT b.id, b.raw->>'legisinfo_id' AS legisinfo_id
          FROM bills b
          JOIN legislative_sessions s ON s.id = b.session_id
         WHERE b.level='federal'
           AND s.parliament_number=$1
           AND s.session_number=$2
           AND b.raw->>'legisinfo_id' IS NOT NULL
        """,
        parliament, session,
    )
    return {r["legisinfo_id"]: str(r["id"]) for r in rows}


async def _insert_event(
    db: Database, *,
    bill_id: str, stage: str, stage_label: str, event_date: date,
    event_type: Optional[str], source_url: Optional[str], raw: dict,
) -> bool:
    """Returns True iff a new row landed (False on conflict)."""
    row = await db.fetchrow(
        """
        INSERT INTO bill_events (
            bill_id, stage, stage_label, event_date, event_type,
            source_url, raw
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb)
        ON CONFLICT ON CONSTRAINT bill_events_uniq DO NOTHING
        RETURNING id
        """,
        bill_id, stage, stage_label, event_date, event_type,
        source_url, orjson.dumps(raw).decode(),
    )
    return row is not None


async def ingest_federal_bill_events(
    db: Database, *,
    parliament: Optional[int] = None,
    session: Optional[int] = None,
    all_sessions: bool = False,
) -> IngestStats:
    """Fetch LEGISinfo XML and write per-bill milestone events.

    Args:
        parliament/session: explicit override.
        all_sessions: walk every federal session present in
          legislative_sessions. Older sessions where no `bills` rows
          exist (pre-P37) silently no-op — the bill_id_index for that
          session is empty.
    """
    stats = IngestStats()

    if parliament is not None and session is not None:
        targets: list[tuple[int, int]] = [(parliament, session)]
    elif all_sessions:
        rows = await db.fetch(
            """
            SELECT parliament_number, session_number
              FROM legislative_sessions
             WHERE level='federal' AND province_territory IS NULL
             ORDER BY parliament_number, session_number
            """
        )
        targets = [(r["parliament_number"], r["session_number"]) for r in rows]
    else:
        p, s = await current_session(db, level="federal")
        targets = [(p, s)]

    if not targets:
        log.warning("ingest_federal_bill_events: no target sessions")
        return stats

    log.info("ingest_federal_bill_events: %d session(s)", len(targets))

    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True) as client:
        for parl, sess in targets:
            xml_bytes = await _fetch_session_xml(client, parl, sess)
            if xml_bytes is None:
                stats.sessions_skipped += 1
                continue
            stats.sessions_touched += 1

            try:
                root = ET.fromstring(xml_bytes)
            except ET.ParseError as e:
                log.warning("legisinfo XML parse %d-%d: %s", parl, sess, e)
                stats.sessions_skipped += 1
                continue

            index = await _bill_id_index(db, parliament=parl, session=sess)
            log.info(
                "legisinfo %d-%d: %d <Bill> elements, %d local bills indexed",
                parl, sess, len(root), len(index),
            )

            for bill_el in root.iter("Bill"):
                stats.bills_seen += 1
                bill_dict = _bill_to_dict(bill_el)
                legisinfo_id = bill_dict.get("BillId")
                if not legisinfo_id:
                    continue

                local_bill_id = index.get(legisinfo_id)
                if local_bill_id is None:
                    stats.bills_no_match += 1
                    continue
                stats.bills_matched += 1

                bill_number = bill_dict.get("BillNumberFormatted") or "?"
                source_url = (
                    f"{LEGISINFO_ROOT}/bill/{parl}-{sess}/{bill_number}"
                )

                for xml_field, stage, event_type in _MILESTONE_FIELDS:
                    raw_ts = bill_dict.get(xml_field)
                    event_date = _parse_dt(raw_ts)
                    if event_date is None:
                        continue
                    stats.events_attempted += 1

                    inserted = await _insert_event(
                        db,
                        bill_id=local_bill_id,
                        stage=stage,
                        stage_label=_STAGE_LABELS[stage],
                        event_date=event_date,
                        event_type=event_type,
                        source_url=source_url,
                        raw={
                            "source_system": SOURCE_SYSTEM,
                            "legisinfo_id": legisinfo_id,
                            "xml_field": xml_field,
                            "raw_timestamp": raw_ts,
                            "bill_number": bill_number,
                            "parliament": parl,
                            "session": sess,
                        },
                    )
                    if inserted:
                        stats.events_inserted += 1
                        stats.by_stage[stage] = stats.by_stage.get(stage, 0) + 1
                    else:
                        stats.events_existing += 1

    log.info("ingest_federal_bill_events: %s", stats)
    return stats


# ---------------------------------------------------------------------------
# Pure-SQL backfill: bills.introduced_date ← bill_events first_reading
# ---------------------------------------------------------------------------

@dataclass
class RelinkIntroducedStats:
    candidates: int = 0          # bills with first_reading event but null intro
    updated: int = 0             # rows actually flipped this run
    by_jurisdiction: dict[str, int] = field(default_factory=dict)


async def relink_bill_introduced_dates(
    db: Database, *,
    levels: Optional[list[str]] = None,
    provinces: Optional[list[str]] = None,
) -> RelinkIntroducedStats:
    """Backfill `bills.introduced_date` from `bill_events.stage='first_reading'`.

    Pure-SQL UPDATE pass — no upstream calls. Wherever a bill has at
    least one `first_reading` event but `introduced_date IS NULL`, set
    it to the earliest such event's date. Idempotent: bills that already
    have an `introduced_date` are left alone.

    Filters:
      levels: restrict to e.g. ['provincial']. Default: all levels.
      provinces: restrict to e.g. ['MB','NS']. Default: all provinces.
    """
    stats = RelinkIntroducedStats()

    where_clauses = ["b.introduced_date IS NULL"]
    params: list = []
    if levels:
        params.append(levels)
        where_clauses.append(f"b.level = ANY(${len(params)})")
    if provinces:
        params.append(provinces)
        where_clauses.append(f"b.province_territory = ANY(${len(params)})")
    where_sql = " AND ".join(where_clauses)

    # Pre-count candidates for telemetry.
    stats.candidates = await db.fetchval(
        f"""
        SELECT count(DISTINCT b.id)
          FROM bills b
          JOIN bill_events be ON be.bill_id = b.id
         WHERE be.stage = 'first_reading'
           AND be.event_date IS NOT NULL
           AND {where_sql}
        """,
        *params,
    )

    rows = await db.fetch(
        f"""
        WITH first_dates AS (
            SELECT bill_id, MIN(event_date) AS d
              FROM bill_events
             WHERE stage = 'first_reading' AND event_date IS NOT NULL
             GROUP BY bill_id
        ),
        upd AS (
            UPDATE bills b
               SET introduced_date = fd.d,
                   updated_at = now()
              FROM first_dates fd
             WHERE b.id = fd.bill_id
               AND {where_sql}
            RETURNING b.level, b.province_territory
        )
        SELECT level, province_territory, count(*) AS n
          FROM upd
         GROUP BY level, province_territory
         ORDER BY level, province_territory
        """,
        *params,
    )

    for r in rows:
        prov = r["province_territory"] or r["level"]
        stats.by_jurisdiction[prov] = (stats.by_jurisdiction.get(prov, 0) + r["n"])
        stats.updated += r["n"]

    log.info("relink_bill_introduced_dates: %s", stats)
    return stats
