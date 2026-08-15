"""Edmonton eScribe minutes enrichment — chair, attendance, delegation.

The eScribe per-meeting minutes pages are server-rendered (the 2026-08-14
probe disproved the "eScribe is JS-walled" belief for detail pages) and the
Socrata spine already carries their URLs on every 2021+ meeting row. The
minutes give three things the captions can't:

  - **the chair** — "Councillor A. Stevenson conducted roll call and
    confirmed the attendance of Members of Urban Planning Committee."
    The roll-call conductor is the presiding chair; committee caption turns
    macro'd as 'The Chair' can then be FK'd to a real member.
  - **attendance** — "Councillors J. Morgan, T. Parmar, …" (useful later
    for term-correct rosters during the historical backfill).
  - **Administration delegation names** — "The following members of
    Administration's delegation answered questions:" followed by
    "K. Snyder, Urban Planning and Economy" lines. Stored for future
    staff-naming; not auto-applied (mapping staff to specific caption turns
    needs per-item timing we don't have).

Parsed results are merged into ``meetings.raw`` under the ``"minutes"`` key
(the raw Socrata row keeps its other keys); the HTML itself lands in
``meetings.raw_minutes_html`` so re-parsing never re-fetches.
"""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field as dc_field
from typing import Optional

import html as html_mod
import httpx
import orjson

from ..db import Database
from .escribe import CITIES, HEADERS, SSL_VERIFY

log = logging.getLogger(__name__)

REQUEST_TIMEOUT = 60
FETCH_DELAY_SECS = 1.0

_TAG_RE = re.compile(r"<[^>]+>")

# "Mayor A. Knack conducted roll call…" / "Councillor A. Stevenson conducted roll call…"
_ROLL_CALL_RE = re.compile(
    r"\b(?:Mayor|Councillor)\s+(?P<name>[A-Z]\.\s*[A-Z][\w'\-]+)\s+conducted\s+roll\s*call",
    re.IGNORECASE,
)

# Attendance list lines: "Councillors J. Morgan, T. Parmar, K. Principe and J. Wright"
_INITIAL_SURNAME_RE = re.compile(r"\b([A-Z])\.\s*([A-Z][\w'\-]+)")

_DELEGATION_HEADER_RE = re.compile(
    r"following\s+(?:members?|public speakers?)\b.*\b(?:presentation|answered questions)",
    re.IGNORECASE,
)
# "K. Snyder, Urban Planning and Economy" — an initial-surname line, with an
# optional org/title tail.
_DELEGATION_NAME_LINE_RE = re.compile(r"^([A-Z]\.\s*[A-Z][\w'\-]+)(?:,\s*(.+))?$")


@dataclass
class MinutesStats:
    meetings_seen: int = 0
    fetched: int = 0
    fetch_failures: int = 0
    parsed: int = 0
    chairs_found: int = 0
    chair_turns_resolved: int = 0
    per_chair: dict = dc_field(default_factory=dict)


def _minutes_lines(raw_html: str) -> list[str]:
    text = html_mod.unescape(_TAG_RE.sub("\n", raw_html))
    return [l.strip() for l in text.splitlines() if l.strip()]


def parse_minutes(raw_html: str) -> dict:
    """Extract chair / attendance / delegation from a minutes page.
    Every field is best-effort; missing pieces come back None/empty."""
    lines = _minutes_lines(raw_html)
    chair: Optional[str] = None
    attendance: list[str] = []
    staff: list[dict] = []

    for i, line in enumerate(lines):
        if chair is None:
            m = _ROLL_CALL_RE.search(line)
            if m:
                chair = re.sub(r"\s+", " ", m.group("name"))
                # Attendance follows within the next few lines.
                for j in range(i + 1, min(i + 6, len(lines))):
                    if lines[j].lower().startswith(("councillors", "councillor", "mayor")):
                        for im in _INITIAL_SURNAME_RE.finditer(lines[j]):
                            attendance.append(f"{im.group(1)}. {im.group(2)}")
                        break
        if _DELEGATION_HEADER_RE.search(line):
            is_admin = "administration" in line.lower()
            for j in range(i + 1, min(i + 12, len(lines))):
                nm = _DELEGATION_NAME_LINE_RE.match(lines[j])
                if not nm:
                    break
                staff.append({
                    "name": nm.group(1).replace(".", ". ").replace("  ", " ").strip(),
                    "org": (nm.group(2) or "").strip() or None,
                    "kind": "administration" if is_admin else "public",
                })

    # Dedup staff on (name, kind).
    seen = set()
    deduped = []
    for s in staff:
        key = (s["name"], s["kind"])
        if key not in seen:
            seen.add(key)
            deduped.append(s)
    return {"chair": chair, "attendance": sorted(set(attendance)), "delegation": deduped}


async def _resolve_initial_surname(
    db: Database, city, name: str, when=None,
) -> Optional[str]:
    """'A. Stevenson' → politician id, matching surname exactly and first
    initial when it disambiguates. Date-aware: resolves against the roster
    valid at `when` (current term = Open North; earlier = dated
    politician_terms; uncovered dates refuse)."""
    m = re.match(r"([A-Z])\.\s*(.+)$", name)
    if not m:
        return None
    initial, surname = m.group(1), m.group(2).strip()
    from .youtube_captions import _roster_valid_for
    if when is None or _roster_valid_for(city.slug, when):
        rows = await db.fetch(
            """
            SELECT id::text AS id, name, last_name FROM politicians
            WHERE level = 'municipal' AND province_territory = $1
              AND source_id LIKE $2
              AND lower(coalesce(last_name, '')) = lower($3)
            """,
            city.province_territory, f"opennorth:{city.slug}-city-council:%", surname,
        )
    else:
        d = when.date() if hasattr(when, "date") else when
        rows = await db.fetch(
            """
            SELECT DISTINCT p.id::text AS id, p.name, p.last_name
            FROM politician_terms t
            JOIN politicians p ON p.id = t.politician_id
            WHERE t.level = 'municipal' AND t.province_territory = $1
              AND (p.source_id LIKE 'opennorth:' || $2 || '-city-council:%'
                   OR p.source_id LIKE 'edmonton-socrata:%')
              AND t.started_at <= $3::date
              AND (t.ended_at IS NULL OR t.ended_at > $3::date)
              AND lower(coalesce(p.last_name, '')) = lower($4)
            """,
            city.province_territory, city.slug, d, surname,
        )
    if not rows:
        return None
    if len(rows) == 1:
        return rows[0]["id"]
    for r in rows:
        if (r["name"] or "").strip()[:1].upper() == initial:
            return r["id"]
    return None


async def enrich_minutes(
    db: Database, *, city_slug: str = "edmonton", limit: Optional[int] = None,
    delay: float = FETCH_DELAY_SECS,
) -> MinutesStats:
    """Hydrate minutes HTML for video-matched meetings, parse chair /
    attendance / delegation into meetings.raw->'minutes', and FK-resolve
    'The Chair' caption turns to the parsed chair (confidence 0.8).

    Idempotent: cached HTML is never refetched; parsing and chair
    application re-run cheaply each time.
    """
    stats = MinutesStats()
    city = CITIES[city_slug]
    caption_source = f"{city.source_system.split('-')[0]}-youtube-captions"

    rows = await db.fetch(
        f"""
        SELECT id::text AS id, minutes_url, video_url, raw_minutes_html,
               source_meeting_id, started_at
        FROM meetings
        WHERE source_system = $1
          AND minutes_url IS NOT NULL
          AND video_url IS NOT NULL
        ORDER BY started_at DESC
        {"LIMIT $2" if limit else ""}
        """,
        *([city.source_system, limit] if limit else [city.source_system]),
    )

    async with httpx.AsyncClient(
        headers=HEADERS, timeout=REQUEST_TIMEOUT, verify=SSL_VERIFY, follow_redirects=True,
    ) as client:
        for r in rows:
            stats.meetings_seen += 1
            raw_html = r["raw_minutes_html"]
            if not raw_html:
                try:
                    resp = await client.get(r["minutes_url"])
                    resp.raise_for_status()
                    raw_html = resp.text
                except httpx.HTTPError as exc:
                    log.warning("minutes fetch failed %s: %s", r["minutes_url"], exc)
                    stats.fetch_failures += 1
                    continue
                await db.execute(
                    "UPDATE meetings SET raw_minutes_html = $1, updated_at = now() WHERE id = $2::uuid",
                    raw_html, r["id"],
                )
                stats.fetched += 1
                if delay > 0:
                    await asyncio.sleep(delay)

            parsed = parse_minutes(raw_html)
            stats.parsed += 1
            from datetime import datetime, timezone
            envelope = {
                "version": 2,
                "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "params": {"parser": "edmonton_minutes/2"},
                **parsed,
            }
            await db.execute(
                """
                UPDATE meetings
                SET raw = raw || jsonb_build_object('minutes', $1::jsonb),
                    updated_at = now()
                WHERE id = $2::uuid
                """,
                orjson.dumps(envelope).decode(), r["id"],
            )
            if not parsed["chair"]:
                continue
            stats.chairs_found += 1
            chair_pid = await _resolve_initial_surname(
                db, city, parsed["chair"], when=r["started_at"],
            )
            if not chair_pid:
                log.info("chair %r not resolved to a council member (staff or ex-member?)",
                         parsed["chair"])
                continue
            result = await db.execute(
                """
                UPDATE speeches
                SET politician_id = $1::uuid, confidence = 0.8, updated_at = now()
                WHERE source_system = $2
                  AND source_anchor LIKE $3 || ':%'
                  AND politician_id IS NULL
                  AND speaker_role = 'Chair'
                """,
                chair_pid, caption_source, r["source_meeting_id"],
            )
            n = int(result.split()[-1]) if result else 0
            stats.chair_turns_resolved += n
            if n:
                stats.per_chair[parsed["chair"]] = stats.per_chair.get(parsed["chair"], 0) + n

    # Chair resolution may run after chunking — reconcile the chunks'
    # politician_id denorm unconditionally (cheap, idempotent, and a prior
    # run may have left stale chunks even when this run resolved nothing).
    from datetime import date as _date
    from .speech_chunker import sync_chunk_politician_scoped
    synced = await sync_chunk_politician_scoped(
        db, province=city.province_territory,
        source_system=caption_source, min_date=_date(2011, 1, 1),
        level="municipal",
    )
    log.info("chunk politician denorm synced: %d rows", synced)

    log.info(
        "edmonton minutes: seen=%d fetched=%d parsed=%d chairs=%d chair_turns_resolved=%d per_chair=%s",
        stats.meetings_seen, stats.fetched, stats.parsed, stats.chairs_found,
        stats.chair_turns_resolved, stats.per_chair,
    )
    return stats
