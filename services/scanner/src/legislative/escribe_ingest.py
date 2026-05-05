"""eScribe ingest chain — orchestrates discovery → fetch → parse → resolve.

Four stages, each idempotent and restartable:

  1. ``ingest_meetings`` — fetch the calendar HTML once per city; upsert
     ``meetings`` rows. Idempotent on (source_system, source_meeting_id).

  2. ``fetch_meeting_pages`` — for every meeting with NULL ``raw_html``,
     fetch the per-meeting agenda HTML and persist it on the row.
     Skips already-cached pages unless ``force=True``.

  3. ``parse_meeting_pages`` — re-parse cached HTML into:
       * ``bills`` rows (one per agenda item; bill_type ∈ motion|bylaw),
       * ``bill_sponsors`` rows (mover + seconder, name-only initially),
       * ``bill_events`` rows (introduced + outcome stage),
       * ``votes`` rows (one per recorded vote on an item),
       * ``vote_positions`` rows (when per-councillor positions are
         recorded; cities with only-tally votes get an empty position
         list and a ``vote_type='consensus'``).
     No HTTP — runs entirely off cached HTML.

  4. ``resolve_motion_movers`` — fills ``bill_sponsors.politician_id`` for
     rows where it's NULL, using a name-fuzz match against the existing
     municipal politicians roster scoped to the city's Open North council
     slug. The provincial sponsor_resolver pattern doesn't quite fit
     because municipal rows have no per-jurisdiction slug column yet, so
     this resolver is intentionally narrower and lives here rather than
     in the shared sponsor_resolver module.

Configuration is centralised in ``escribe.CITIES`` — passing
``city_slug='all'`` runs every configured city in sequence.

Council-term sessions are resolved by the meeting's ``started_at``
falling within ``[legislative_sessions.start_date, end_date]``. The seed
sessions for Calgary 2021–2025 / 2025–2029 and Edmonton 2021–2025 /
2025–2029 are inserted by migration ``0046``.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
import orjson

from ..db import Database
from .escribe import (
    CITIES,
    EscribeCity,
    HEADERS,
    SSL_VERIFY,
    IngestStats,
    ParsedAgendaItem,
    fetch_calendar,
    fetch_meeting_page,
    parse_calendar_html,
    parse_meeting_html,
)

log = logging.getLogger(__name__)


def _resolve_cities(city_slug: str) -> list[EscribeCity]:
    if city_slug == "all":
        return list(CITIES.values())
    if city_slug not in CITIES:
        raise ValueError(f"unknown city slug {city_slug!r}; known: {list(CITIES)}")
    return [CITIES[city_slug]]


# ── Session resolution ─────────────────────────────────────────────


async def _session_id_for(
    db: Database, city: EscribeCity, started_at: Optional[datetime],
) -> Optional[str]:
    """Pick the seeded council-term session whose date range covers started_at.

    Falls back to the most recent open-ended session if the date is in the
    future or missing. Returns None only if the city has no sessions seeded
    (which would be a bug — migration 0046 seeds them).
    """
    when = started_at.date() if started_at else None
    if when is not None:
        row = await db.fetchrow(
            """
            SELECT id::text AS id FROM legislative_sessions
            WHERE level = 'municipal'
              AND province_territory = $1
              AND source_system = $2
              AND start_date <= $3
              AND (end_date IS NULL OR end_date >= $3)
            ORDER BY start_date DESC
            LIMIT 1
            """,
            city.province_territory, city.source_system, when,
        )
        if row:
            return row["id"]
    # Fallback: latest open-ended term for this city.
    row = await db.fetchrow(
        """
        SELECT id::text AS id FROM legislative_sessions
        WHERE level = 'municipal'
          AND province_territory = $1
          AND source_system = $2
        ORDER BY start_date DESC
        LIMIT 1
        """,
        city.province_territory, city.source_system,
    )
    return row["id"] if row else None


# ── Stage 1: ingest_meetings ───────────────────────────────────────


async def _upsert_meeting(
    db: Database, city: EscribeCity, meeting, session_id: str,
) -> tuple[str, bool]:
    """Insert or update one meetings row. Returns (id, was_inserted)."""
    row = await db.fetchrow(
        """
        INSERT INTO meetings (
            session_id, level, province_territory, municipality_slug,
            body_name, body_type, started_at, agenda_url, video_url,
            source_system, source_meeting_id, raw
        ) VALUES (
            $1, 'municipal', $2, $3, $4, $5, $6, $7, $8, $9, $10, $11
        )
        ON CONFLICT (source_system, source_meeting_id) DO UPDATE SET
            session_id    = EXCLUDED.session_id,
            body_name     = EXCLUDED.body_name,
            body_type     = EXCLUDED.body_type,
            started_at    = EXCLUDED.started_at,
            agenda_url    = COALESCE(EXCLUDED.agenda_url, meetings.agenda_url),
            video_url     = COALESCE(EXCLUDED.video_url, meetings.video_url),
            updated_at    = now()
        RETURNING id::text AS id, (xmax = 0) AS inserted
        """,
        session_id,
        city.province_territory,
        city.slug,
        meeting.body_name,
        meeting.body_type,
        meeting.started_at,
        meeting.agenda_url,
        meeting.video_stream_url,
        city.source_system,
        meeting.source_meeting_id,
        orjson.dumps({"is_cancelled": meeting.is_cancelled}).decode(),
    )
    return row["id"], bool(row["inserted"])


async def ingest_meetings(
    db: Database, *, city_slug: str = "all", limit: Optional[int] = None,
) -> IngestStats:
    stats = IngestStats()
    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, verify=SSL_VERIFY) as client:
        for city in _resolve_cities(city_slug):
            log.info("escribe ingest_meetings: city=%s", city.slug)
            html = await fetch_calendar(client, city)
            if html is None:
                stats.fetch_failures.append(city.calendar_url)
                continue
            meetings = parse_calendar_html(html)
            if limit is not None:
                meetings = meetings[:limit]
            stats.cities_processed += 1
            stats.meetings_seen += len(meetings)
            for m in meetings:
                sid = await _session_id_for(db, city, m.started_at)
                if not sid:
                    log.warning("no session for %s started=%s; skipping", city.slug, m.started_at)
                    stats.parse_warnings += 1
                    continue
                _, inserted = await _upsert_meeting(db, city, m, sid)
                if inserted:
                    stats.meetings_inserted += 1
                else:
                    stats.meetings_updated += 1
    return stats


# ── Stage 2: fetch_meeting_pages ───────────────────────────────────


async def fetch_meeting_pages(
    db: Database, *, city_slug: str = "all",
    limit: Optional[int] = None, force: bool = False,
    delay: float = 1.0,
) -> IngestStats:
    stats = IngestStats()
    cities = _resolve_cities(city_slug)
    where_force = "" if force else " AND raw_html IS NULL "
    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, verify=SSL_VERIFY) as client:
        for city in cities:
            rows = await db.fetch(
                f"""
                SELECT id::text AS id, source_meeting_id
                FROM meetings
                WHERE source_system = $1 {where_force}
                ORDER BY started_at DESC NULLS LAST
                {"LIMIT $2" if limit else ""}
                """,
                *([city.source_system, limit] if limit else [city.source_system]),
            )
            stats.cities_processed += 1
            for r in rows:
                html = await fetch_meeting_page(client, city, r["source_meeting_id"])
                if html is None:
                    await db.execute(
                        "UPDATE meetings SET fetch_error=$1, fetched_at=now(), updated_at=now() WHERE id=$2::uuid",
                        "fetch failed", r["id"],
                    )
                    stats.fetch_failures.append(r["source_meeting_id"])
                    continue
                await db.execute(
                    """
                    UPDATE meetings SET
                        raw_html = $1, fetched_at = now(), fetch_error = NULL,
                        updated_at = now()
                    WHERE id = $2::uuid
                    """,
                    html, r["id"],
                )
                stats.meetings_fetched += 1
                if delay > 0:
                    await asyncio.sleep(delay)
    return stats


# ── Stage 3: parse_meeting_pages ───────────────────────────────────


async def _upsert_bill(
    db: Database, *, city: EscribeCity, session_id: str, meeting_id: str,
    item: ParsedAgendaItem, source_url: str,
) -> tuple[str, bool]:
    """Insert/update one bills row for an agenda item. Returns (bill_id, inserted)."""
    source_id = f"{city.source_system}:{meeting_id}:{item.item_number}"
    title_norm = item.title.strip()[:1000] or item.item_number
    short_title = title_norm[:200] if len(title_norm) > 200 else None
    row = await db.fetchrow(
        """
        INSERT INTO bills (
            session_id, level, province_territory, bill_number,
            title, short_title, bill_type, status,
            source_id, source_system, source_url, meeting_id, raw
        ) VALUES (
            $1, 'municipal', $2, $3, $4, $5, $6, $7, $8, $9, $10, $11::uuid, $12::jsonb
        )
        ON CONFLICT (source_id) DO UPDATE SET
            title         = EXCLUDED.title,
            short_title   = COALESCE(EXCLUDED.short_title, bills.short_title),
            bill_type     = EXCLUDED.bill_type,
            status        = COALESCE(EXCLUDED.status, bills.status),
            meeting_id    = EXCLUDED.meeting_id,
            last_fetched_at = now(),
            updated_at    = now()
        RETURNING id::text AS id, (xmax = 0) AS inserted
        """,
        session_id,
        city.province_territory,
        item.item_number,
        title_norm,
        short_title,
        item.item_type,
        item.vote_result,
        source_id,
        city.source_system,
        source_url,
        meeting_id,
        orjson.dumps({
            "mover": item.mover_name,
            "seconder": item.seconder_name,
            "vote_ayes": item.vote_ayes,
            "vote_nays": item.vote_nays,
            "n_positions": len(item.vote_positions),
        }).decode(),
    )
    return row["id"], bool(row["inserted"])


async def _upsert_sponsors(
    db: Database, bill_id: str, item: ParsedAgendaItem,
) -> int:
    """Insert mover + seconder rows. Idempotent: deletes prior rows for this
    bill first (cheap; municipal motions never have many sponsors)."""
    n = 0
    await db.execute("DELETE FROM bill_sponsors WHERE bill_id = $1::uuid", bill_id)
    if item.mover_name:
        await db.execute(
            """
            INSERT INTO bill_sponsors (bill_id, sponsor_name_raw, role, ordering)
            VALUES ($1::uuid, $2, 'sponsor', 0)
            """,
            bill_id, item.mover_name.strip(),
        )
        n += 1
    if item.seconder_name:
        await db.execute(
            """
            INSERT INTO bill_sponsors (bill_id, sponsor_name_raw, role, ordering)
            VALUES ($1::uuid, $2, 'co_sponsor', 1)
            """,
            bill_id, item.seconder_name.strip(),
        )
        n += 1
    return n


async def _upsert_event(
    db: Database, bill_id: str, stage: str, event_date, source_url: str,
) -> bool:
    # The actual UNIQUE constraint is NULLS NOT DISTINCT on
    # (bill_id, stage, event_date, event_type, committee_name). PostgreSQL
    # requires the ON CONFLICT spec to match the constraint exactly, so we
    # emit explicit NULLs for event_type and committee_name even though
    # municipal motions never set them.
    row = await db.fetchrow(
        """
        INSERT INTO bill_events
            (bill_id, stage, stage_label, event_date, event_type, committee_name, source_url, raw)
        VALUES ($1::uuid, $2, $3, $4, NULL, NULL, $5, '{}'::jsonb)
        ON CONFLICT (bill_id, stage, event_date, event_type, committee_name) DO NOTHING
        RETURNING id
        """,
        bill_id, stage, stage.replace("_", " ").title(), event_date, source_url,
    )
    return bool(row)


def _vote_outcome(item: ParsedAgendaItem) -> str:
    r = (item.vote_result or "").lower()
    if "carr" in r or "approv" in r:
        return "passed"
    if "defeat" in r or "lost" in r:
        return "defeated"
    if "withdraw" in r:
        return "withdrawn"
    return "vote_taken"


async def _upsert_vote(
    db: Database, *, city: EscribeCity, session_id: str, bill_id: str,
    item: ParsedAgendaItem, started_at: Optional[datetime], source_url: str,
) -> tuple[Optional[str], int]:
    """Insert one votes row + per-councillor vote_positions when present.

    Returns (vote_id_or_None, positions_inserted).
    """
    if not item.vote_result and item.vote_ayes is None and not item.vote_positions:
        return None, 0
    has_positions = bool(item.vote_positions)
    vote_type = "division" if has_positions else "consensus"
    outcome = _vote_outcome(item)
    vote_url = f"{source_url}#item={item.item_number}"
    row = await db.fetchrow(
        """
        INSERT INTO votes (
            session_id, bill_id, level, province_territory,
            occurred_at, vote_type, result,
            motion_text, ayes, nays, abstentions,
            source_system, source_url, raw
        ) VALUES (
            $1, $2::uuid, 'municipal', $3,
            $4, $5, $6,
            $7, $8, $9, $10,
            $11, $12, $13::jsonb
        )
        ON CONFLICT (source_system, source_url) DO UPDATE SET
            result      = EXCLUDED.result,
            ayes        = EXCLUDED.ayes,
            nays        = EXCLUDED.nays,
            motion_text = EXCLUDED.motion_text,
            updated_at  = now()
        RETURNING id::text AS id
        """,
        session_id, bill_id, city.province_territory,
        started_at, vote_type, outcome,
        item.title[:500],
        item.vote_ayes, item.vote_nays,
        sum(1 for _, d in item.vote_positions if d == "abstain") or None,
        city.source_system, vote_url,
        orjson.dumps({"raw_result": item.vote_result, "item_number": item.item_number}).decode(),
    )
    vote_id = row["id"]
    # Replace positions rows (idempotent: UNIQUE on (vote_id, politician_name_raw)).
    n_pos = 0
    await db.execute("DELETE FROM vote_positions WHERE vote_id = $1::uuid", vote_id)
    for name, direction in item.vote_positions:
        if not name:
            continue
        position_norm = {"aye": "yea", "nay": "nay",
                         "absent": "absent", "abstain": "abstain"}.get(direction, direction)
        if position_norm not in ("yea", "nay", "abstain", "absent", "paired"):
            continue  # CHECK constraint guard
        try:
            await db.execute(
                """
                INSERT INTO vote_positions (vote_id, politician_name_raw, position)
                VALUES ($1::uuid, $2, $3)
                ON CONFLICT (vote_id, politician_name_raw) DO NOTHING
                """,
                vote_id, name, position_norm,
            )
            n_pos += 1
        except Exception as exc:
            log.warning("vote_positions insert failed for %s/%s: %s", name, position_norm, exc)
    return vote_id, n_pos


async def parse_meeting_pages(
    db: Database, *, city_slug: str = "all", limit: Optional[int] = None,
) -> IngestStats:
    stats = IngestStats()
    cities = _resolve_cities(city_slug)
    for city in cities:
        rows = await db.fetch(
            f"""
            SELECT id::text AS id, session_id::text AS session_id,
                   raw_html, started_at, source_meeting_id
            FROM meetings
            WHERE source_system = $1 AND raw_html IS NOT NULL
            ORDER BY started_at DESC NULLS LAST
            {"LIMIT $2" if limit else ""}
            """,
            *([city.source_system, limit] if limit else [city.source_system]),
        )
        stats.cities_processed += 1
        for mrow in rows:
            try:
                detail = parse_meeting_html(mrow["raw_html"])
            except Exception as exc:
                log.warning("parse failed for meeting %s: %s", mrow["id"], exc)
                stats.parse_warnings += 1
                continue
            stats.pages_parsed += 1
            source_url = (
                f"https://{city.host}/Meeting.aspx?Id={mrow['source_meeting_id']}"
                f"&Agenda=Agenda&lang=English"
            )
            for item in detail.items:
                if not item.title or item.title.strip() == "":
                    continue
                bill_id, inserted = await _upsert_bill(
                    db, city=city, session_id=mrow["session_id"],
                    meeting_id=mrow["id"], item=item, source_url=source_url,
                )
                if inserted:
                    stats.bills_inserted += 1
                else:
                    stats.bills_updated += 1
                stats.bill_sponsors_inserted += await _upsert_sponsors(db, bill_id, item)
                # Always log "introduced" event at meeting date.
                if mrow["started_at"]:
                    if await _upsert_event(
                        db, bill_id, "introduced",
                        mrow["started_at"].date() if hasattr(mrow["started_at"], "date") else None,
                        source_url,
                    ):
                        stats.bill_events_inserted += 1
                if item.vote_result:
                    if await _upsert_event(
                        db, bill_id, _vote_outcome(item),
                        mrow["started_at"].date() if mrow["started_at"] else None,
                        source_url,
                    ):
                        stats.bill_events_inserted += 1
                vote_id, n_pos = await _upsert_vote(
                    db, city=city, session_id=mrow["session_id"], bill_id=bill_id,
                    item=item, started_at=mrow["started_at"], source_url=source_url,
                )
                if vote_id:
                    stats.votes_inserted += 1
                stats.vote_positions_inserted += n_pos
    return stats


# ── Stage 4: resolve_motion_movers ─────────────────────────────────


async def _load_council_roster(db: Database, city: EscribeCity) -> dict[str, str]:
    """Map normalised surname → politician_id for the city's current Open North roster.

    Source IDs look like ``opennorth:calgary-city-council:<person-slug>`` for
    Calgary; Edmonton uses ``opennorth:edmonton-city-council:...``. The
    council slug is the discriminator that scopes the search.
    """
    council_slug = f"opennorth:{city.slug}-city-council:"
    rows = await db.fetch(
        """
        SELECT id::text AS id, name, last_name
        FROM politicians
        WHERE level = 'municipal'
          AND province_territory = $1
          AND source_id LIKE $2
        """,
        city.province_territory, council_slug + "%",
    )
    out: dict[str, str] = {}
    for r in rows:
        # Normalise on last_name when present, falling back to last token of name.
        last = (r["last_name"] or "").strip()
        if not last and r["name"]:
            last = r["name"].split()[-1]
        if last:
            out[last.upper()] = r["id"]
    return out


def _candidate_surname(raw: str) -> Optional[str]:
    """Turn 'Councillor SMITH' / 'SMITH' / 'Mayor Gondek' into 'SMITH' / 'GONDEK'."""
    if not raw:
        return None
    s = raw.strip()
    s = " ".join(s.split())
    # Strip honorifics.
    for pre in ("Councillor", "Mayor", "Deputy Mayor", "Alderman", "Madam"):
        if s.lower().startswith(pre.lower() + " "):
            s = s[len(pre) + 1:]
    # Take the last token, upper-case it.
    tokens = s.split()
    if not tokens:
        return None
    return tokens[-1].strip(".,").upper()


async def resolve_motion_movers(
    db: Database, *, city_slug: str = "all",
) -> IngestStats:
    stats = IngestStats()
    for city in _resolve_cities(city_slug):
        roster = await _load_council_roster(db, city)
        if not roster:
            log.warning("no roster for city=%s; skipping", city.slug)
            continue
        unresolved = await db.fetch(
            """
            SELECT bs.id::text AS bs_id, bs.sponsor_name_raw
            FROM bill_sponsors bs
            JOIN bills b ON b.id = bs.bill_id
            WHERE b.source_system = $1
              AND bs.politician_id IS NULL
              AND bs.sponsor_name_raw IS NOT NULL
            """,
            city.source_system,
        )
        stats.cities_processed += 1
        for row in unresolved:
            surname = _candidate_surname(row["sponsor_name_raw"])
            pid = roster.get(surname) if surname else None
            if pid:
                await db.execute(
                    "UPDATE bill_sponsors SET politician_id = $1::uuid WHERE id = $2::uuid",
                    pid, row["bs_id"],
                )
                stats.movers_resolved += 1
            else:
                stats.movers_unresolved += 1
    return stats
