"""Edmonton media-asset probe — map every meeting to its ISI CDN recording.

Edmonton meetings are broadcast by ISI Global and the recordings sit on
``video.isilive.ca/edmonton/<file>.mp4`` — unauthenticated, unthrottled,
range-seekable (probe 2026-08-14; full evidence in the pipeline-hardening
plan). The eScribe player page hands out the filename:

    GET pub-edmonton.escribemeetings.com/Players/ISIStandAlonePlayer.aspx?Id=<uuid>
    → <div id="isi_player" data-client_id="edmonton"
           data-file_name="Encoder 1_CC_2023-06-07-10-54.mp4">

``data-client_id="empty"`` is a clean "no ISI asset" negative (~25% of
meetings) — those fall back to YouTube.

This stage is METADATA-ONLY (2–3 small requests per meeting): it never
downloads media. Results land in ``meetings.raw->'media'``:

    {"version": 1, "generated_at": …,
     "isi": {"file_name": …, "url": …, "etag": …, "bytes": …,
             "last_modified": …} | {"empty": true},
     "error": "…"?}

The ``(etag, bytes)`` pair is the immutable media identity (CDP-style
content addressing without paying for a download — nginx ETags are
mtime+size); derived artifacts should be keyed on it, and freshness checks
are conditional HEADs.

Politeness: video.isilive.ca robots.txt is a blanket Disallow. We fetch
only URLs the public player hands us (no crawling), one connection, spaced
requests, project bot UA. A courtesy note to the City Clerk is drafted at
docs/runbooks/draft-email-edmonton-city-clerk.md.
"""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import quote

import httpx
import orjson

from ..db import Database
from .escribe import CITIES, HEADERS, SSL_VERIFY

log = logging.getLogger(__name__)

PLAYER_URL = "https://pub-edmonton.escribemeetings.com/Players/ISIStandAlonePlayer.aspx?Id={uuid}"
ISI_BASE = "https://video.isilive.ca/{client}/{file}"
REQUEST_DELAY_SECS = 0.6
REQUEST_TIMEOUT = 30

_PLAYER_RE = re.compile(
    r'id="isi_player"[^>]*data-client_id="(?P<client>[^"]*)"[^>]*data-file_name="(?P<file>[^"]*)"',
)
_PLAYER_RE_SWAPPED = re.compile(
    r'id="isi_player"[^>]*data-file_name="(?P<file>[^"]*)"[^>]*data-client_id="(?P<client>[^"]*)"',
)
_GUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE,
)


@dataclass
class MediaProbeStats:
    meetings_seen: int = 0
    isi_found: int = 0
    isi_empty: int = 0
    errors: int = 0


def parse_player_page(html: str) -> Optional[tuple[str, str]]:
    """→ (client_id, file_name) or None when the div is absent."""
    m = _PLAYER_RE.search(html) or _PLAYER_RE_SWAPPED.search(html)
    if not m:
        return None
    return m.group("client"), m.group("file")


async def probe_media_assets(
    db: Database, *, city_slug: str = "edmonton", limit: Optional[int] = None,
    force: bool = False,
) -> MediaProbeStats:
    """Probe the ISI asset for every GUID meeting lacking a media record."""
    stats = MediaProbeStats()
    city = CITIES[city_slug]
    rows = await db.fetch(
        f"""
        SELECT id::text AS id, source_meeting_id
        FROM meetings
        WHERE source_system = $1
          {"" if force else "AND raw->'media' IS NULL"}
        ORDER BY started_at DESC
        {"LIMIT $2" if limit else ""}
        """,
        *([city.source_system, limit] if limit else [city.source_system]),
    )
    rows = [r for r in rows if _GUID_RE.match(r["source_meeting_id"] or "")]

    async with httpx.AsyncClient(
        headers=HEADERS, timeout=REQUEST_TIMEOUT, verify=SSL_VERIFY,
        follow_redirects=True,
    ) as client:
        for r in rows:
            stats.meetings_seen += 1
            media: dict = {
                "version": 1,
                "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
            try:
                resp = await client.get(PLAYER_URL.format(uuid=r["source_meeting_id"]))
                resp.raise_for_status()
                parsed = parse_player_page(resp.text)
                if not parsed or parsed[0] in ("", "empty") or not parsed[1] \
                        or parsed[1] == "empty":
                    media["isi"] = {"empty": True}
                    stats.isi_empty += 1
                else:
                    client_id, file_name = parsed
                    url = ISI_BASE.format(client=client_id, file=quote(file_name))
                    await asyncio.sleep(REQUEST_DELAY_SECS)
                    head = await client.head(url)
                    if head.status_code == 200:
                        media["isi"] = {
                            "file_name": file_name,
                            "url": url,
                            "etag": head.headers.get("etag", "").strip('"'),
                            "bytes": int(head.headers.get("content-length", 0)),
                            "last_modified": head.headers.get("last-modified"),
                            "accept_ranges": head.headers.get("accept-ranges") == "bytes",
                        }
                        stats.isi_found += 1
                    else:
                        media["isi"] = {"empty": True, "head_status": head.status_code}
                        stats.isi_empty += 1
            except httpx.HTTPError as exc:
                media["error"] = str(exc)[:200]
                stats.errors += 1
            await db.execute(
                """
                UPDATE meetings
                SET raw = raw || jsonb_build_object('media', $1::jsonb),
                    updated_at = now()
                WHERE id = $2::uuid
                """,
                orjson.dumps(media).decode(), r["id"],
            )
            await asyncio.sleep(REQUEST_DELAY_SECS)

    log.info("media probe: seen=%d isi=%d empty=%d errors=%d",
             stats.meetings_seen, stats.isi_found, stats.isi_empty, stats.errors)
    return stats
