"""NT Hansard ingester — Drupal HTML → `speeches` table.

The Drupal site at ntlegislativeassembly.ca publishes one HTML page per
sitting at a stable URL pattern:

    https://www.ntlegislativeassembly.ca/hansard/hn{YYMMDD}

Discovery walks the paginated listing at
``/documents-proceedings/hansard?page=N`` (Drupal Views default pager,
~50 sittings/page, ~30 pages back to ~2002). Each listing row exposes
the HTML transcript URL plus PDF and Word alternates which we don't
ingest — HTML is canonical.

Speaker resolution is by direct slug lookup: the parser extracts
``nt_mla_slug`` from each speech's
``<a href="/meet-members/mla/{slug}">`` wrapper, and this ingester joins
that to ``politicians.nt_mla_slug`` at insert time. Presiding-officer
interjections (Mr. Speaker, Deputy Speaker) come through with
``speaker_role`` set; ``resolve-presiding-speakers --province NT`` maps
those by date once a speaker roster is seeded.

NT runs consensus government — no party affiliation, so ``party_at_time``
stays NULL on every row. ``level='provincial'`` matches the existing NT
bills pipeline convention (the ``province_territory='NT'`` discriminator
already says it's a territory).

Idempotency: upsert keyed on
``(source_system='hansard-nt', source_url, sequence)``. Re-runs UPDATE
in place; structural changes to the parser only require re-running the
ingest with no schema changes. Full ``raw_html`` is stored on the
``sequence=1`` row of each sitting to support re-parsing without re-
fetching.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from dataclasses import dataclass, field as dc_field
from datetime import datetime, timezone
from typing import Optional

import httpx
import orjson

from ..db import Database
from .nt_hansard_parse import ParsedSitting, ParsedSpeech, parse_sitting

log = logging.getLogger(__name__)

BASE = "https://www.ntlegislativeassembly.ca"
LISTING_URL = f"{BASE}/documents-proceedings/hansard"
SOURCE_SYSTEM = "hansard-nt"

REQUEST_TIMEOUT = 60
HEADERS = {
    "User-Agent": "CanadianPoliticalDataBot/1.0 (+https://canadianpoliticaldata.ca; admin@thebunkerops.ca)",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-CA,en;q=0.9",
}

# Listing-page hansard link: /hansard/hn{YYMMDD}
_LISTING_LINK_RE = re.compile(
    r'href="/hansard/hn(?P<ymd>\d{6})"', re.IGNORECASE,
)


# ── Models ──────────────────────────────────────────────────────────


@dataclass
class SittingRef:
    hn_id: str               # "hn260306"
    ymd: str                 # "260306" — YY MM DD as printed in the slug
    canonical_url: str       # full HTML URL


@dataclass
class IngestStats:
    listing_pages_fetched: int = 0
    sittings_seen: int = 0
    sittings_fetched: int = 0
    sittings_skipped: int = 0
    speeches_inserted: int = 0
    speeches_updated: int = 0
    sessions_touched: set[str] = dc_field(default_factory=set)
    parse_warnings: int = 0
    fetch_failures: list[str] = dc_field(default_factory=list)


# ── Discovery ───────────────────────────────────────────────────────


async def _fetch(client: httpx.AsyncClient, url: str) -> Optional[str]:
    try:
        r = await client.get(url, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        return r.text
    except Exception as exc:
        log.warning("nt_hansard: fetch %s failed: %s", url, exc)
        return None


async def discover_sittings(
    client: httpx.AsyncClient, *, max_pages: Optional[int] = None,
) -> list[SittingRef]:
    """Walk the listing pager, return one SittingRef per sitting URL.

    De-dupes on hn_id (the listing has a few cross-listed rows). Stops
    when a page returns no new sittings or 404s.
    """
    seen_ids: set[str] = set()
    refs: list[SittingRef] = []
    page = 0
    while True:
        url = LISTING_URL if page == 0 else f"{LISTING_URL}?page={page}"
        html = await _fetch(client, url)
        if not html:
            break
        new_ids = []
        for m in _LISTING_LINK_RE.finditer(html):
            hid = "hn" + m.group("ymd")
            if hid in seen_ids:
                continue
            seen_ids.add(hid)
            new_ids.append(hid)
        if not new_ids:
            break
        for hid in new_ids:
            ymd = hid[2:]  # "260306"
            refs.append(SittingRef(
                hn_id=hid, ymd=ymd,
                canonical_url=f"{BASE}/hansard/{hid}",
            ))
        page += 1
        if max_pages is not None and page >= max_pages:
            break
        await asyncio.sleep(0.5)
    return refs


# ── Session ensure ──────────────────────────────────────────────────


async def _ensure_session(
    db: Database, *, parliament: int, session: int,
) -> str:
    """Return legislative_sessions.id for NT (parliament, session).

    NT bills already populate this table for the current 20th Assembly;
    this is defensive for older sittings whose session row may not
    exist yet.
    """
    row = await db.fetchrow(
        """
        INSERT INTO legislative_sessions
            (level, province_territory, parliament_number, session_number,
             name, source_system, source_url)
        VALUES ('provincial', 'NT', $1, $2, $3, 'hansard-nt', $4)
        ON CONFLICT (level, province_territory, parliament_number, session_number)
        DO UPDATE SET updated_at = now()
        RETURNING id::text AS id
        """,
        parliament, session,
        f"{parliament}th Assembly, {session}{_ord_suffix(session)} Session",
        f"{LISTING_URL}",
    )
    return row["id"]


def _ord_suffix(n: int) -> str:
    if 10 < n % 100 < 20:
        return "th"
    return ["th", "st", "nd", "rd", "th", "th", "th", "th", "th", "th"][n % 10]


# ── Speaker resolution ──────────────────────────────────────────────


async def _load_slug_lookup(db: Database) -> dict[str, str]:
    """{nt_mla_slug → politicians.id (text)} — preloaded once per ingest."""
    rows = await db.fetch(
        """
        SELECT id::text AS id, nt_mla_slug
          FROM politicians
         WHERE province_territory = 'NT'
           AND level = 'provincial'
           AND nt_mla_slug IS NOT NULL
        """
    )
    return {r["nt_mla_slug"]: r["id"] for r in rows}


# ── Per-sitting upsert ──────────────────────────────────────────────


def _content_hash(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


async def _upsert_speech(
    db: Database, *,
    session_id: str,
    politician_id: Optional[str],
    speech: ParsedSpeech,
    spoken_at: datetime,
    canonical_url: str,
    raw_payload: dict,
    raw_html: Optional[str],
) -> str:
    """Insert or update one speech. Returns 'inserted' or 'updated'."""
    raw_json = orjson.dumps(raw_payload).decode("utf-8")
    confidence = 1.0 if politician_id and speech.nt_mla_slug else 0.5
    speech_type = "hansard"

    result = await db.fetchrow(
        """
        INSERT INTO speeches (
            session_id, politician_id, level, province_territory,
            speaker_name_raw, speaker_role, party_at_time, constituency_at_time,
            confidence, speech_type, spoken_at, sequence, language,
            text, word_count,
            source_system, source_url, source_anchor,
            raw, raw_html, content_hash
        ) VALUES (
            $1::uuid, $2, 'provincial', 'NT',
            $3, $4, NULL, $5,
            $6, $7, $8, $9, 'en',
            $10, $11,
            $12, $13, NULL,
            $14::jsonb, $15, $16
        )
        ON CONFLICT (source_system, source_url, sequence)
        DO UPDATE SET
            politician_id = EXCLUDED.politician_id,
            speaker_name_raw = EXCLUDED.speaker_name_raw,
            speaker_role = EXCLUDED.speaker_role,
            constituency_at_time = EXCLUDED.constituency_at_time,
            confidence = EXCLUDED.confidence,
            speech_type = EXCLUDED.speech_type,
            spoken_at = EXCLUDED.spoken_at,
            text = EXCLUDED.text,
            word_count = EXCLUDED.word_count,
            raw = EXCLUDED.raw,
            raw_html = EXCLUDED.raw_html,
            content_hash = EXCLUDED.content_hash,
            updated_at = now()
        RETURNING (xmax = 0) AS inserted
        """,
        session_id,
        politician_id,
        speech.speaker_name_raw,
        speech.speaker_role,
        speech.constituency,
        confidence,
        speech_type,
        spoken_at,
        speech.sequence,
        speech.body_text,
        speech.word_count,
        SOURCE_SYSTEM,
        canonical_url,
        raw_json,
        raw_html,
        _content_hash(speech.body_text),
    )
    return "inserted" if result and result["inserted"] else "updated"


async def _ingest_sitting(
    db: Database, ref: SittingRef, html_text: str,
    slug_lookup: dict[str, str], stats: IngestStats,
) -> None:
    sit = parse_sitting(html_text)
    stats.parse_warnings += len(sit.parse_warnings)
    if not sit.sitting_date:
        stats.fetch_failures.append(f"{ref.hn_id}: parser found no sitting date — skipping")
        return
    if not sit.parliament_number or not sit.session_number:
        stats.fetch_failures.append(
            f"{ref.hn_id}: parser found date but no assembly/session — skipping"
        )
        return
    if not sit.speeches:
        stats.fetch_failures.append(f"{ref.hn_id}: zero speeches parsed — skipping")
        return

    session_id = await _ensure_session(
        db, parliament=sit.parliament_number, session=sit.session_number,
    )
    stats.sessions_touched.add(session_id)

    spoken_at = datetime(
        sit.sitting_date.year, sit.sitting_date.month, sit.sitting_date.day,
        12, 0, 0, tzinfo=timezone.utc,  # noon UTC convention; ordering is by sequence within sitting
    )

    for speech in sit.speeches:
        politician_id = slug_lookup.get(speech.nt_mla_slug) if speech.nt_mla_slug else None
        raw_payload = {
            "nt_hansard": {
                "hn_id": ref.hn_id,
                "sitting_date": sit.sitting_date.isoformat(),
                "parliament": sit.parliament_number,
                "session": sit.session_number,
                "day_number": sit.day_number,
                "section": speech.section,
                "topic": speech.topic,
                "speaker_role": speech.speaker_role,
                "nt_mla_slug": speech.nt_mla_slug,
                "constituency": speech.constituency,
            }
        }
        result = await _upsert_speech(
            db,
            session_id=session_id,
            politician_id=politician_id,
            speech=speech,
            spoken_at=spoken_at,
            canonical_url=ref.canonical_url,
            raw_payload=raw_payload,
            raw_html=html_text if speech.sequence == 1 else None,
        )
        if result == "inserted":
            stats.speeches_inserted += 1
        else:
            stats.speeches_updated += 1


# ── Public entry point ──────────────────────────────────────────────


async def ingest_nt_hansard(
    db: Database,
    *,
    limit_sittings: Optional[int] = None,
    since_hn_id: Optional[str] = None,
    only_url: Optional[str] = None,
    delay: float = 1.0,
) -> IngestStats:
    """Ingest NT Hansard sittings into ``speeches``.

    ``limit_sittings`` caps the number of sittings ingested (newest first).
    ``since_hn_id``: skip sittings whose hn_id sorts at-or-below the given
    value (smoke-test aid).
    ``only_url``: bypass discovery and ingest exactly one transcript URL.
    """
    stats = IngestStats()
    slug_lookup = await _load_slug_lookup(db)
    log.info("nt_hansard: loaded %d slug → politician lookups", len(slug_lookup))

    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True) as client:
        # Discovery
        if only_url:
            m = re.search(r"/hansard/(hn\d{6})", only_url)
            if not m:
                stats.fetch_failures.append(f"--url malformed: {only_url}")
                return stats
            hid = m.group(1)
            refs = [SittingRef(hn_id=hid, ymd=hid[2:], canonical_url=only_url)]
        else:
            refs = await discover_sittings(client)
            stats.listing_pages_fetched = -1  # not tracking individually
        stats.sittings_seen = len(refs)
        log.info("nt_hansard: discovered %d sittings", len(refs))

        if since_hn_id:
            refs = [r for r in refs if r.hn_id > since_hn_id]
        if limit_sittings is not None:
            refs = refs[:int(limit_sittings)]

        for ref in refs:
            html = await _fetch(client, ref.canonical_url)
            if not html:
                stats.sittings_skipped += 1
                stats.fetch_failures.append(f"{ref.hn_id}: fetch returned empty")
                continue
            try:
                await _ingest_sitting(db, ref, html, slug_lookup, stats)
                stats.sittings_fetched += 1
            except Exception as exc:
                stats.sittings_skipped += 1
                stats.fetch_failures.append(f"{ref.hn_id}: ingest exception: {exc}")
                log.exception("nt_hansard: failed to ingest %s", ref.hn_id)
            await asyncio.sleep(delay)

    log.info(
        "nt_hansard: seen=%d fetched=%d skipped=%d "
        "inserted=%d updated=%d sessions=%d warns=%d fails=%d",
        stats.sittings_seen, stats.sittings_fetched, stats.sittings_skipped,
        stats.speeches_inserted, stats.speeches_updated,
        len(stats.sessions_touched), stats.parse_warnings, len(stats.fetch_failures),
    )
    return stats
