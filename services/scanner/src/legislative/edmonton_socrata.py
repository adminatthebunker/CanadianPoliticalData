"""Edmonton council-meeting spine from the city's Socrata open-data portal.

The City Clerk publishes the entire eScribe meeting record as open Socrata
datasets on data.edmonton.ca (probe 2026-08-14) — meetings, agenda items,
motions, per-councillor roll-call votes, and attendance, 2011-06-01 to
present, no auth, SoQL query support. This module ingests the *meetings*
layer only; it is the canonical spine that the YouTube-captions speech
pipeline (``youtube_captions.py``) matches videos against.

Datasets used:
  - ``7zht-i9ve`` — "Meeting Details, Agenda Items, and Motions (Multiple
    Terms)". Denormalized 2011-06-01 → end of the 2021-2025 term. The
    2025-2029 term is ABSENT despite the dataset's daily-update flag;
    re-check that assumption occasionally (if the city folds the current
    term in, the union below simply produces harmless duplicate upserts).
  - ``ct7z-2r6h`` — "2025-2029 Meeting Details". Current term, updated
    daily, includes future scheduled meetings and prebuilt eScribe
    agenda/minutes URLs.

Key shapes to know:
  - 2011-2021 rows carry an integer ``meeting_id`` from the pre-eScribe
    system; 2021+ rows carry the eScribe GUID. Both go into
    ``meetings.source_meeting_id`` under source_system
    ``edmonton-escribemeetings`` (the data is an eScribe export either way,
    and the captions stages key off that source_system).
  - ``meeting_datetime`` is naive local time (America/Edmonton).
  - eScribe ``Meeting.aspx`` detail pages are server-rendered and fetch
    cleanly; only the calendar-listing AJAX is opaque. GUID-shaped ids get
    agenda/minutes URLs constructed here even when the dataset row lacks
    them.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field as dc_field
from datetime import date, datetime
from typing import Optional
from zoneinfo import ZoneInfo

import httpx
import orjson

from ..db import Database
from .escribe import CITIES, HEADERS, SSL_VERIFY

log = logging.getLogger(__name__)

SOCRATA_BASE = "https://data.edmonton.ca/resource"
MULTI_TERM_DATASET = "7zht-i9ve"
CURRENT_TERM_DATASET = "ct7z-2r6h"
REQUEST_TIMEOUT = 120

EDMONTON_TZ = ZoneInfo("America/Edmonton")
ESCRIBE_BASE = "https://pub-edmonton.escribemeetings.com"

_GUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE,
)

# Council terms seeded as legislative_sessions. 2021+ terms come from
# migration 0046; the three older terms are seeded idempotently below with
# the same parliament_number scheme (2=Edmonton, 5xx=council-term series).
# Boundaries are contiguous around Edmonton's October general elections so
# _session_for_term's date fallback can never fall in a gap.
_TERM_SESSIONS: dict[str, tuple[int, str, date, Optional[date]]] = {
    "2011-2013": (2511, "Edmonton 2010–2013 Council Term", date(2010, 10, 18), date(2013, 10, 20)),
    "2013-2017": (2513, "Edmonton 2013–2017 Council Term", date(2013, 10, 21), date(2017, 10, 15)),
    "2017-2021": (2517, "Edmonton 2017–2021 Council Term", date(2017, 10, 16), date(2021, 10, 17)),
    # 2021-2025 / 2025-2029 exist from migration 0046 (2521 / 2525).
    "2021-2025": (2521, "Edmonton 2021–2025 Council Term", date(2021, 10, 18), date(2025, 10, 19)),
    "2025-2029": (2525, "Edmonton 2025–2029 Council Term", date(2025, 10, 20), None),
}


# ── Dated roster history (yqff-55ja) ────────────────────────────────

ROSTER_DATASET = "yqff-55ja"
ROSTER_SOURCE_TAG = "edmonton-socrata:yqff-55ja"
# Backfill meetings start 2011; one election of margin.
ROSTER_MIN_ELECTION = date(2004, 1, 1)


@dataclass
class RosterStats:
    rows_fetched: int = 0
    people_matched: int = 0
    people_created: int = 0
    terms_written: int = 0
    skipped: int = 0


def _normalize_office(office: str) -> str:
    o = (office or "").strip().title()
    return "Councillor" if o == "Alderman" else o


async def ingest_edmonton_roster_history(db: Database) -> RosterStats:
    """Dated council membership from the Socrata membership-history dataset.

    Why: the Open North roster is current-term only, and the attribution
    resolvers must never match a pre-2025 meeting against it (the mayor for
    2021-2025 was Amarjeet Sohi, not Andrew Knack). This ingests each
    election's slate (2004→2021; the dataset is stale past the 2021
    election, which is fine — the current term comes from Open North) as
    ``politician_terms`` rows: service = [election_date, next general
    election), with the 2021 cohort closed at the 2025-10-20 term boundary.
    By-elections (single-row election dates) open a term for the winner at
    their date; the predecessor's row keeps the election-boundary end (a
    documented approximation — resignations mid-term are not modelled, and
    an absent member can't be recognized by the chair anyway).

    People: matched to existing municipal-AB politicians by exact
    case-insensitive full name (continuing members like Knack/Paquette
    attach terms to their Open North row); otherwise created with
    ``source_id = edmonton-socrata:yqff-55ja:<slug>`` and is_active=false.
    NEVER merged with existing rows beyond the exact-name match — see the
    duplicate-politician Cooke rule.

    Terms are delete-and-reinserted scoped by ``source = ROSTER_SOURCE_TAG``
    (the standard revert primitive), so re-runs are idempotent.
    """
    stats = RosterStats()
    city = CITIES["edmonton"]
    async with httpx.AsyncClient(
        headers=HEADERS, timeout=REQUEST_TIMEOUT, verify=SSL_VERIFY,
    ) as client:
        rows = await _fetch_json(client, ROSTER_DATASET, {
            "$where": f"election_date >= '{ROSTER_MIN_ELECTION.isoformat()}'",
            "$limit": "2000",
        })
    stats.rows_fetched = len(rows)

    parsed = []
    by_election: dict[date, int] = {}
    for r in rows:
        try:
            ed = datetime.fromisoformat(r["election_date"]).date()
        except (KeyError, ValueError):
            stats.skipped += 1
            continue
        first = (r.get("first_name") or "").strip()
        last = (r.get("last_name") or "").strip()
        if not last:
            stats.skipped += 1
            continue
        parsed.append({
            "election": ed, "first": first, "last": last,
            "office": _normalize_office(r.get("office", "")),
            "raw": r,
        })
        by_election[ed] = by_election.get(ed, 0) + 1

    general = sorted(d for d, n in by_election.items() if n >= 10)
    term_2025_start = _TERM_SESSIONS["2025-2029"][2]

    def service_end(start: date) -> date:
        nxt = [g for g in general if g > start]
        return nxt[0] if nxt else term_2025_start

    # Delete-and-reinsert the tagged term rows (idempotent revert scope).
    await db.execute(
        "DELETE FROM politician_terms WHERE source = $1", ROSTER_SOURCE_TAG,
    )

    for p in parsed:
        full = f"{p['first']} {p['last']}".strip()
        pid = await db.fetchval(
            """
            SELECT id::text FROM politicians
            WHERE level = 'municipal' AND province_territory = $1
              AND lower(name) = lower($2)
            ORDER BY is_active DESC, created_at ASC
            LIMIT 1
            """,
            city.province_territory, full,
        )
        if pid:
            stats.people_matched += 1
        else:
            slug = re.sub(r"[^a-z0-9]+", "-", full.lower()).strip("-")
            pid = await db.fetchval(
                """
                INSERT INTO politicians (
                    source_id, name, first_name, last_name,
                    elected_office, level, province_territory,
                    is_active, extras
                ) VALUES ($1, $2, $3, $4, $5, 'municipal', $6, false, $7::jsonb)
                ON CONFLICT (source_id) DO UPDATE SET updated_at = now()
                RETURNING id::text
                """,
                f"{ROSTER_SOURCE_TAG}:{slug}", full, p["first"], p["last"],
                p["office"], city.province_territory,
                orjson.dumps({"yqff_row": p["raw"]}).decode(),
            )
            stats.people_created += 1
        start = p["election"]
        end = service_end(start)
        await db.execute(
            """
            INSERT INTO politician_terms (
                politician_id, office, level, province_territory,
                started_at, ended_at, source
            ) VALUES ($1::uuid, $2, 'municipal', $3, $4::date, $5::date, $6)
            """,
            pid, p["office"], city.province_territory,
            start, end, ROSTER_SOURCE_TAG,
        )
        stats.terms_written += 1

    log.info("edmonton roster history: rows=%d matched=%d created=%d terms=%d skipped=%d",
             stats.rows_fetched, stats.people_matched, stats.people_created,
             stats.terms_written, stats.skipped)
    return stats


@dataclass
class SpineStats:
    rows_fetched: int = 0
    meetings_seen: int = 0
    meetings_inserted: int = 0
    meetings_updated: int = 0
    skipped_no_id: int = 0
    skipped_no_datetime: int = 0
    sessions_seeded: int = 0
    per_term: dict = dc_field(default_factory=dict)


def _parse_meeting_datetime(value: Optional[str]) -> Optional[datetime]:
    """'2025-09-19T09:30:00.000' (naive Edmonton local) → tz-aware datetime."""
    if not value:
        return None
    try:
        naive = datetime.fromisoformat(value)
    except ValueError:
        return None
    if naive.tzinfo is not None:
        return naive
    return naive.replace(tzinfo=EDMONTON_TZ)


def _body_type_for(meeting_type: str) -> str:
    t = meeting_type.lower()
    if "council" in t and "committee" not in t:
        return "council"
    return "committee"


def _escribe_urls(source_meeting_id: str, row: dict) -> tuple[Optional[str], Optional[str]]:
    """(agenda_url, minutes_url). Prefer the dataset's prebuilt URLs (fixing
    the known //Meeting.aspx double slash); construct from the GUID otherwise.
    Integer legacy ids have no eScribe page — both None."""

    def from_col(col: str) -> Optional[str]:
        v = row.get(col)
        if isinstance(v, dict):
            v = v.get("url")
        if isinstance(v, str) and v.startswith("http"):
            return v.replace(".com//", ".com/")
        return None

    agenda = from_col("agenda_html")
    minutes = from_col("minutes_html")
    if (agenda and minutes) or not _GUID_RE.match(source_meeting_id):
        return agenda, minutes
    agenda = agenda or f"{ESCRIBE_BASE}/Meeting.aspx?Id={source_meeting_id}&Agenda=Agenda&lang=English"
    minutes = minutes or f"{ESCRIBE_BASE}/Meeting.aspx?Id={source_meeting_id}&Agenda=PostMinutes&lang=English"
    return agenda, minutes


async def _fetch_json(client: httpx.AsyncClient, dataset: str, params: dict) -> list[dict]:
    resp = await client.get(f"{SOCRATA_BASE}/{dataset}.json", params=params)
    resp.raise_for_status()
    return resp.json()


async def _seed_sessions(db: Database, city, stats: SpineStats) -> dict[str, str]:
    """Ensure one legislative_sessions row per council term; return
    council_term → session_id."""
    out: dict[str, str] = {}
    for term, (parl, name, start, end) in _TERM_SESSIONS.items():
        row = await db.fetchrow(
            """
            INSERT INTO legislative_sessions
                (level, province_territory, parliament_number, session_number,
                 name, start_date, end_date, source_system)
            VALUES ('municipal', $1, $2, 1, $3, $4, $5, $6)
            ON CONFLICT (level, province_territory, parliament_number, session_number)
                DO UPDATE SET updated_at = now()
            RETURNING id::text AS id, (xmax = 0) AS inserted
            """,
            city.province_territory, parl, name, start, end, city.source_system,
        )
        out[term] = row["id"]
        if row["inserted"]:
            stats.sessions_seeded += 1
            log.info("seeded session %s (%s)", name, term)
    return out


async def _upsert_meeting(
    db: Database, city, session_id: str, *,
    source_meeting_id: str, body_name: str, started_at: datetime,
    agenda_url: Optional[str], minutes_url: Optional[str],
    raw_row: dict,
) -> bool:
    row = await db.fetchrow(
        """
        INSERT INTO meetings (
            session_id, level, province_territory, municipality_slug,
            body_name, body_type, started_at,
            agenda_url, minutes_url,
            source_system, source_meeting_id, raw
        ) VALUES (
            $1::uuid, 'municipal', $2, $3,
            $4, $5, $6,
            $7, $8,
            $9, $10, $11::jsonb
        )
        ON CONFLICT (source_system, source_meeting_id) DO UPDATE SET
            session_id  = EXCLUDED.session_id,
            body_name   = EXCLUDED.body_name,
            body_type   = EXCLUDED.body_type,
            started_at  = EXCLUDED.started_at,
            agenda_url  = COALESCE(EXCLUDED.agenda_url, meetings.agenda_url),
            minutes_url = COALESCE(EXCLUDED.minutes_url, meetings.minutes_url),
            -- MERGE, never replace: meetings.raw also carries expensive
            -- derived state written by other stages ('speaker_timeline',
            -- 'voice_map', 'minutes'). A plain EXCLUDED.raw here wiped it
            -- all on every daily refresh (caught in the 2026-08-14 review
            -- before the first scheduled run fired).
            raw         = meetings.raw || EXCLUDED.raw,
            updated_at  = now()
        RETURNING (xmax = 0) AS inserted
        """,
        session_id, city.province_territory, city.slug,
        body_name, _body_type_for(body_name), started_at,
        agenda_url, minutes_url,
        city.source_system, source_meeting_id, orjson.dumps(raw_row).decode(),
    )
    return bool(row["inserted"])


async def ingest_edmonton_meetings(db: Database) -> SpineStats:
    """Union the multi-term backbone with the current-term details table
    into ``meetings`` rows. Idempotent; safe to re-run daily."""
    stats = SpineStats()
    city = CITIES["edmonton"]
    sessions = await _seed_sessions(db, city, stats)

    async with httpx.AsyncClient(
        headers=HEADERS, timeout=REQUEST_TIMEOUT, verify=SSL_VERIFY,
    ) as client:
        # Distinct meetings out of the denormalized 76K-row backbone: group
        # by every selected column server-side so one request returns ~2.8K.
        cols = "council_term,meeting_id,meeting_type,meeting_title,meeting_datetime,meeting_location"
        multi = await _fetch_json(client, MULTI_TERM_DATASET, {
            "$select": cols, "$group": cols, "$limit": "50000",
        })
        current = await _fetch_json(client, CURRENT_TERM_DATASET, {"$limit": "50000"})

    for row in multi:
        stats.rows_fetched += 1
        mid = (row.get("meeting_id") or "").strip()
        started = _parse_meeting_datetime(row.get("meeting_datetime"))
        if not mid:
            stats.skipped_no_id += 1
            continue
        if started is None:
            stats.skipped_no_datetime += 1
            continue
        term = row.get("council_term") or ""
        session_id = sessions.get(term)
        if session_id is None:
            log.warning("unknown council_term %r on meeting %s; skipping", term, mid)
            stats.skipped_no_id += 1
            continue
        agenda_url, minutes_url = _escribe_urls(mid, row)
        stats.meetings_seen += 1
        inserted = await _upsert_meeting(
            db, city, session_id,
            source_meeting_id=mid,
            body_name=(row.get("meeting_type") or "Unknown").strip(),
            started_at=started,
            agenda_url=agenda_url, minutes_url=minutes_url,
            raw_row=row,
        )
        stats.meetings_inserted += inserted
        stats.meetings_updated += (not inserted)
        stats.per_term[term] = stats.per_term.get(term, 0) + 1

    for row in current:
        stats.rows_fetched += 1
        mid = (row.get("uuid") or "").strip()
        started = _parse_meeting_datetime(row.get("meeting_datetime"))
        if not mid:
            stats.skipped_no_id += 1
            continue
        if started is None:
            stats.skipped_no_datetime += 1
            continue
        term = row.get("council_term") or "2025-2029"
        session_id = sessions.get(term) or sessions["2025-2029"]
        agenda_url, minutes_url = _escribe_urls(mid, row)
        stats.meetings_seen += 1
        inserted = await _upsert_meeting(
            db, city, session_id,
            source_meeting_id=mid,
            body_name=(row.get("meeting_type") or "Unknown").strip(),
            started_at=started,
            agenda_url=agenda_url, minutes_url=minutes_url,
            raw_row=row,
        )
        stats.meetings_inserted += inserted
        stats.meetings_updated += (not inserted)
        stats.per_term[term] = stats.per_term.get(term, 0) + 1

    log.info(
        "edmonton socrata spine: fetched=%d meetings=%d inserted=%d updated=%d "
        "skipped(no-id=%d no-dt=%d) per-term=%s",
        stats.rows_fetched, stats.meetings_seen, stats.meetings_inserted,
        stats.meetings_updated, stats.skipped_no_id, stats.skipped_no_datetime,
        stats.per_term,
    )
    return stats
