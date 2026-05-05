"""SK Hansard ingester — discovery + fetch + parse + upsert.

Two-stage flow under one Click subcommand:

  1. Discovery — walk the paginated archive at
     https://www.legassembly.sk.ca/legislative-business/archive/?page=N
     and harvest every Assembly-debates HTML URL. Skip Committee debates
     (they're a separate ``speech_type='committee'`` workstream).

  2. Per-sitting fetch + parse + insert. Each sitting URL embeds the
     parliament/session and date (e.g. ``30L2S/20260504DebatesHTML.htm``)
     so we don't need to read the body for those fields. Speech text is
     extracted by ``sk_hansard_parse.parse_hansard_html``. Speakers are
     attached to politicians via the synthesised ``sk_assembly_slug``
     populated by ``ingest-sk-mlas``.

Idempotency:
- ``legislative_sessions`` upserted on (level, province_territory,
  parliament, session) — re-runs no-op.
- ``speeches`` upserted on (source_system, source_url, sequence) — sequence
  is the per-sitting speaker-turn index.

The SK ingester does NOT currently handle:
- Committee transcripts (filtered out at discovery time).
- Pre-30th-leg eras (2024-) — sample probes for older sessions returned
  404 for the daily HTML pattern, suggesting older transcripts are PDF-
  only or use a different filename convention. Treating that as a
  follow-up workstream.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from dataclasses import dataclass, field as dc_field
from datetime import date as Date, datetime, timezone
from typing import Optional

import httpx
import orjson

from ..db import Database
from .sk_hansard_parse import parse_hansard_html, ParsedSpeech, SittingMeta
from .sk_hansard_pdf_parse import extract_speeches_from_text, ParsedSpeech as PDFParsedSpeech
from .pdf_utils import pdftotext as _pdftotext

log = logging.getLogger(__name__)

ARCHIVE_URL = "https://www.legassembly.sk.ca/legislative-business/archive/"
SOURCE_SYSTEM = "hansard-sk"

REQUEST_TIMEOUT = 45
HEADERS = {
    "User-Agent": "CanadianPoliticalDataBot/1.0 (+https://canadianpoliticaldata.ca; admin@thebunkerops.ca)",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-CA,en;q=0.9",
}

# URL extracted from the archive listing. Filename pattern carries the
# parliament/session/date — e.g.
#   …/Assembly/Debates/30L2S/20260504DebatesHTML.htm        (HTML, current era)
#   …/Assembly/Debates/29L1S/20201207Debates.pdf            (PDF, main sitting)
#   …/Assembly/Debates/29L1S/20201201Debates-EVE.pdf        (PDF, evening sitting)
#   …/Assembly/Debates/29L1S/20221026Debates-AM.pdf         (PDF, morning sitting)
# AM/EVE are SEPARATE sittings (not duplicates) on the same date — each
# gets its own SittingRef so they're stored as distinct rows.
_ASSEMBLY_HANSARD_HTML_RE = re.compile(
    r"https://docs\.legassembly\.sk\.ca/legdocs/Assembly/Debates/"
    r"(?P<parl>\d+)L(?P<sess>\d+)S/"
    r"(?P<ymd>\d{8})DebatesHTML\.htm",
    re.IGNORECASE,
)
_ASSEMBLY_HANSARD_PDF_RE = re.compile(
    r"https://docs\.legassembly\.sk\.ca/legdocs/Assembly/Debates/"
    r"(?P<parl>\d+)L(?P<sess>\d+)S/"
    r"(?P<ymd>\d{8})Debates(?P<suffix>-AM|-EVE)?\.pdf",
    re.IGNORECASE,
)
# Back-compat alias — older imports / tests reference this name.
_ASSEMBLY_HANSARD_RE = _ASSEMBLY_HANSARD_HTML_RE


# ── Discovery ──────────────────────────────────────────────────────


@dataclass
class SittingRef:
    parliament: int
    session: int
    sitting_date: Date
    canonical_url: str
    fmt: str = "html"            # 'html' or 'pdf'
    time_of_day: str = "main"    # 'main' / 'morning' / 'evening'


@dataclass
class IngestStats:
    pages_walked: int = 0
    sittings_seen: int = 0
    sittings_fetched: int = 0
    sittings_skipped: int = 0
    speeches_inserted: int = 0
    speeches_updated: int = 0
    sessions_touched: set[str] = dc_field(default_factory=set)
    fetch_failures: list[str] = dc_field(default_factory=list)
    parse_failures: list[str] = dc_field(default_factory=list)


async def _fetch(client: httpx.AsyncClient, url: str) -> Optional[str]:
    """Fetch HTML / archive listing as text (decoded). Skips PDFs — those
    use _fetch_pdf_bytes to avoid mis-decoding binary as windows-1252.
    """
    try:
        r = await client.get(url, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        if "docs.legassembly.sk.ca" in url:
            return r.content.decode("windows-1252", errors="replace")
        return r.text
    except Exception as exc:
        log.warning("sk_hansard: fetch %s failed: %s", url, exc)
        return None


async def _fetch_pdf_bytes(client: httpx.AsyncClient, url: str) -> Optional[bytes]:
    try:
        r = await client.get(url, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        if not r.content or len(r.content) < 500:
            log.warning("sk_hansard: pdf %s too small (%d bytes)",
                        url, len(r.content) if r.content else 0)
            return None
        return r.content
    except Exception as exc:
        log.warning("sk_hansard: pdf fetch %s failed: %s", url, exc)
        return None


def _suffix_to_time_of_day(suffix: Optional[str]) -> str:
    if not suffix:
        return "main"
    s = suffix.upper()
    if s == "-AM":
        return "morning"
    if s == "-EVE":
        return "evening"
    return "main"


async def discover_sittings(
    client: httpx.AsyncClient, *, max_pages: Optional[int] = None,
) -> list[SittingRef]:
    """Walk the archive pager, return one SittingRef per Assembly sitting.

    Both HTML and PDF transcripts are surfaced. When both formats exist
    for the same (parliament, session, date, time_of_day) tuple, HTML
    wins — we re-ingest from the richer format and skip the PDF
    duplicate. AM/EVE supplementary PDFs are distinct sittings (same
    date, different sittings) and each gets its own SittingRef.
    """
    seen_urls: set[str] = set()
    by_key: dict[tuple[int, int, str, str], SittingRef] = {}
    page = 0
    consecutive_empty = 0
    while True:
        url = ARCHIVE_URL if page == 0 else f"{ARCHIVE_URL}?page={page}"
        html = await _fetch(client, url)
        if html is None:
            break
        new_for_page = 0

        # 1. HTML matches first — these win over any PDF for the same key.
        for m in _ASSEMBLY_HANSARD_HTML_RE.finditer(html):
            full_url = m.group(0)
            if full_url in seen_urls:
                continue
            seen_urls.add(full_url)
            try:
                d = Date(int(m.group("ymd")[:4]),
                         int(m.group("ymd")[4:6]),
                         int(m.group("ymd")[6:8]))
            except ValueError:
                continue
            key = (int(m.group("parl")), int(m.group("sess")),
                   m.group("ymd"), "main")  # HTML pattern has no -AM/-EVE
            ref = SittingRef(
                parliament=int(m.group("parl")),
                session=int(m.group("sess")),
                sitting_date=d, canonical_url=full_url,
                fmt="html", time_of_day="main",
            )
            by_key[key] = ref
            new_for_page += 1

        # 2. PDF matches second — only added when no HTML for the same key.
        for m in _ASSEMBLY_HANSARD_PDF_RE.finditer(html):
            full_url = m.group(0)
            if full_url in seen_urls:
                continue
            seen_urls.add(full_url)
            try:
                d = Date(int(m.group("ymd")[:4]),
                         int(m.group("ymd")[4:6]),
                         int(m.group("ymd")[6:8]))
            except ValueError:
                continue
            tod = _suffix_to_time_of_day(m.group("suffix"))
            key = (int(m.group("parl")), int(m.group("sess")),
                   m.group("ymd"), tod)
            existing = by_key.get(key)
            if existing is not None and existing.fmt == "html":
                continue  # HTML already captured this sitting.
            ref = SittingRef(
                parliament=int(m.group("parl")),
                session=int(m.group("sess")),
                sitting_date=d, canonical_url=full_url,
                fmt="pdf", time_of_day=tod,
            )
            by_key[key] = ref
            new_for_page += 1

        if new_for_page == 0:
            consecutive_empty += 1
            if consecutive_empty >= 2:
                break
        else:
            consecutive_empty = 0
        page += 1
        if max_pages is not None and page >= max_pages:
            break
        await asyncio.sleep(0.5)
    return list(by_key.values())


# ── Sessions / FK lookup ───────────────────────────────────────────


def _ord_suffix(n: int) -> str:
    if 10 < n % 100 < 20:
        return "th"
    return ["th", "st", "nd", "rd", "th", "th", "th", "th", "th", "th"][n % 10]


async def _ensure_session(
    db: Database, *, parliament: int, session: int,
) -> str:
    """Upsert legislative_sessions for SK (parliament, session)."""
    name = (
        f"{parliament}{_ord_suffix(parliament)} Legislature, "
        f"{session}{_ord_suffix(session)} Session"
    )
    row = await db.fetchrow(
        """
        INSERT INTO legislative_sessions
            (level, province_territory, parliament_number, session_number,
             name, source_system, source_url)
        VALUES ('provincial', 'SK', $1, $2, $3, 'hansard-sk', $4)
        ON CONFLICT (level, province_territory, parliament_number, session_number)
        DO UPDATE SET
            name          = COALESCE(legislative_sessions.name, EXCLUDED.name),
            source_system = COALESCE(legislative_sessions.source_system, EXCLUDED.source_system),
            updated_at    = now()
        RETURNING id::text AS id
        """,
        parliament, session, name, ARCHIVE_URL,
    )
    return row["id"]


async def _load_slug_lookup(db: Database) -> dict[str, str]:
    """{sk_assembly_slug → politicians.id (text)}"""
    rows = await db.fetch(
        """
        SELECT id::text AS id, sk_assembly_slug
          FROM politicians
         WHERE province_territory = 'SK'
           AND level = 'provincial'
           AND sk_assembly_slug IS NOT NULL
        """
    )
    return {r["sk_assembly_slug"]: r["id"] for r in rows}


async def _load_lastname_lookup(db: Database) -> dict[str, list[tuple[str, str]]]:
    """{normalised_last_name → [(politicians.id, first_name_lower), ...]}.

    Carries first_name so the Deputy-Speaker fallback can disambiguate by
    first initial when multiple MLAs share a last name (e.g. SK 30L has
    both Blaine and Tim McLeod).
    """
    import unicodedata

    def _norm(s: str) -> str:
        text = unicodedata.normalize("NFKD", s.lower())
        text = "".join(c for c in text if not unicodedata.combining(c))
        return re.sub(r"[^a-z0-9]", "", text)

    rows = await db.fetch(
        """
        SELECT id::text AS id, first_name, last_name
          FROM politicians
         WHERE province_territory = 'SK'
           AND level = 'provincial'
           AND sk_assembly_slug IS NOT NULL
           AND last_name IS NOT NULL
        """
    )
    out: dict[str, list[tuple[str, str]]] = {}
    for r in rows:
        key = _norm(r["last_name"])
        if not key:
            continue
        first_lower = (r["first_name"] or "").lower()
        out.setdefault(key, []).append((r["id"], first_lower))
    return out


def _resolve_politician(
    speech: ParsedSpeech,
    slug_lookup: dict[str, str],
    lastname_lookup: dict[str, list[tuple[str, str]]],
) -> tuple[Optional[str], float]:
    """Return (politician_id_or_None, confidence)."""
    if speech.candidate_slug and speech.candidate_slug in slug_lookup:
        return slug_lookup[speech.candidate_slug], 1.0
    if speech.last_name:
        import unicodedata
        key = unicodedata.normalize("NFKD", speech.last_name.lower())
        key = "".join(c for c in key if not unicodedata.combining(c))
        key = re.sub(r"[^a-z0-9]", "", key)
        candidates = lastname_lookup.get(key, [])
        if len(candidates) == 1:
            return candidates[0][0], 0.85 if speech.is_speaker_role else 0.7
        # Multiple candidates — try first-initial filter when available.
        if len(candidates) > 1 and speech.first_name:
            initial = speech.first_name[0].lower()
            narrowed = [c for c in candidates if c[1].startswith(initial)]
            if len(narrowed) == 1:
                return narrowed[0][0], 0.8 if speech.is_speaker_role else 0.65
    return None, 0.5 if not speech.is_chorus else 0.3


# ── Per-sitting upsert ─────────────────────────────────────────────


def _content_hash(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


async def _upsert_speech(
    db: Database, *,
    session_id: str,
    politician_id: Optional[str],
    confidence: float,
    speech: ParsedSpeech,
    spoken_at: datetime,
    canonical_url: str,
    raw_payload: dict,
    raw_html: Optional[str],
) -> str:
    raw_json = orjson.dumps(raw_payload).decode("utf-8")
    speech_type = "hansard"
    # Preserve the parser's distinct roles — the presiding-officer resolver
    # only attributes role='speaker' (main Speaker chair) via SPEAKER_ROSTER,
    # not deputy_speaker / chair / deputy_chair (separate rotating-role
    # people). Collapsing them all to 'speaker' here would mis-attribute.
    speaker_role = (
        "chorus" if speech.is_chorus else
        speech.speaker_role or "member"
    )
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
            $1::uuid, $2, 'provincial', 'SK',
            $3, $4, NULL, NULL,
            $5, $6, $7, $8, 'en',
            $9, $10,
            $11, $12, NULL,
            $13::jsonb, $14, $15
        )
        ON CONFLICT (source_system, source_url, sequence)
        DO UPDATE SET
            politician_id = EXCLUDED.politician_id,
            speaker_name_raw = EXCLUDED.speaker_name_raw,
            speaker_role = EXCLUDED.speaker_role,
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
        session_id, politician_id,
        speech.speaker_name_raw, speaker_role,
        confidence, speech_type, spoken_at, speech.sequence,
        speech.body_text, speech.word_count,
        SOURCE_SYSTEM, canonical_url,
        raw_json, raw_html, _content_hash(speech.body_text),
    )
    return "inserted" if result and result["inserted"] else "updated"


def _resolve_pdf_speech(
    speech: PDFParsedSpeech,
    slug_lookup: dict[str, str],
    lastname_lookup: dict[str, list[tuple[str, str]]],
) -> tuple[Optional[str], float]:
    """PDF-shape resolver — uses surname (+ optional initial) instead of
    a synthesised slug, since PDF speaker lines lack the Word-HTML
    bold-name convention that produces clean firstname-lastname slugs.
    """
    if speech.surname:
        import unicodedata
        key = unicodedata.normalize("NFKD", speech.surname.lower())
        key = "".join(c for c in key if not unicodedata.combining(c))
        key = re.sub(r"[^a-z0-9]", "", key)
        candidates = lastname_lookup.get(key, [])
        if len(candidates) == 1:
            return candidates[0][0], (
                0.85 if speech.is_speaker_role else 0.9
            )
        if len(candidates) > 1 and speech.initial:
            initial = speech.initial[0].lower()
            narrowed = [c for c in candidates if c[1].startswith(initial)]
            if len(narrowed) == 1:
                return narrowed[0][0], (
                    0.8 if speech.is_speaker_role else 0.85
                )
    return None, (0.5 if not speech.is_chorus else 0.3)


async def _ingest_pdf_sitting(
    db: Database, ref: SittingRef, pdf_bytes: bytes,
    slug_lookup: dict[str, str],
    lastname_lookup: dict[str, list[tuple[str, str]]],
    stats: IngestStats,
) -> None:
    """Fetch + parse one PDF transcript, upsert speeches."""
    try:
        text = _pdftotext(pdf_bytes, layout=False)
    except Exception as exc:
        stats.parse_failures.append(f"pdftotext failed for {ref.canonical_url}: {exc}")
        return
    speeches = extract_speeches_from_text(text)
    if not speeches:
        stats.parse_failures.append(f"no speeches parsed from {ref.canonical_url}")
        return

    session_id = await _ensure_session(
        db, parliament=ref.parliament, session=ref.session,
    )
    stats.sessions_touched.add(f"{ref.parliament}L{ref.session}S")

    # spoken_at: AM=09:00, main=13:30 (afternoon), evening=19:00.
    # These are typical SK sitting times; sequence preserves intra-sitting order.
    hh, mm = {
        "morning": (9, 0),
        "evening": (19, 0),
    }.get(ref.time_of_day, (13, 30))
    ts = datetime(ref.sitting_date.year, ref.sitting_date.month,
                  ref.sitting_date.day, hh, mm, tzinfo=timezone.utc)

    for s in speeches:
        pol_id, conf = _resolve_pdf_speech(s, slug_lookup, lastname_lookup)
        speaker_role = (
            "chorus" if s.is_chorus else
            s.speaker_role or "member"
        )
        raw_payload = {
            "extractor": "sk_hansard_pdf/v1",
            "section_label": s.section,
            "speaker_role_detected": s.speaker_role,
            "honorific": s.honorific,
            "initial": s.initial,
            "surname": s.surname,
            "time_of_day": ref.time_of_day,
        }
        raw_json = orjson.dumps(raw_payload).decode("utf-8")
        # Store raw_html=NULL for PDF rows; the speech text itself is the
        # content. (The chunker / embedder don't need raw_html.)
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
                $1::uuid, $2, 'provincial', 'SK',
                $3, $4, NULL, NULL,
                $5, $6, $7, $8, 'en',
                $9, $10,
                $11, $12, NULL,
                $13::jsonb, NULL, $14
            )
            ON CONFLICT (source_system, source_url, sequence)
            DO UPDATE SET
                politician_id = EXCLUDED.politician_id,
                speaker_name_raw = EXCLUDED.speaker_name_raw,
                speaker_role = EXCLUDED.speaker_role,
                confidence = EXCLUDED.confidence,
                spoken_at = EXCLUDED.spoken_at,
                text = EXCLUDED.text,
                word_count = EXCLUDED.word_count,
                raw = EXCLUDED.raw,
                content_hash = EXCLUDED.content_hash,
                updated_at = now()
            RETURNING (xmax = 0) AS inserted
            """,
            session_id, pol_id,
            s.speaker_name_raw, speaker_role,
            conf, "hansard", ts, s.sequence,
            s.body, len(s.body.split()),
            SOURCE_SYSTEM, ref.canonical_url,
            raw_json, _content_hash(s.body),
        )
        if result and result["inserted"]:
            stats.speeches_inserted += 1
        else:
            stats.speeches_updated += 1


async def _ingest_sitting(
    db: Database, ref: SittingRef, html: str,
    slug_lookup: dict[str, str], lastname_lookup: dict[str, list[str]],
    stats: IngestStats,
) -> None:
    sitting_meta, speeches = parse_hansard_html(html)
    if not speeches:
        stats.parse_failures.append(f"no speeches parsed: {ref.canonical_url}")
        return

    session_id = await _ensure_session(
        db, parliament=ref.parliament, session=ref.session,
    )
    stats.sessions_touched.add(f"{ref.parliament}L{ref.session}S")

    # spoken_at = sitting_date with start_time if known, else 13:30 (default
    # SK afternoon sitting). The body header parses start_time when
    # present; sequence ordering preserves intra-sitting order.
    base_time = sitting_meta.start_time if sitting_meta else None
    if base_time:
        try:
            hh, mm = base_time.split(":")
            ts = datetime(ref.sitting_date.year, ref.sitting_date.month,
                          ref.sitting_date.day, int(hh), int(mm),
                          tzinfo=timezone.utc)
        except ValueError:
            ts = datetime(ref.sitting_date.year, ref.sitting_date.month,
                          ref.sitting_date.day, 13, 30, tzinfo=timezone.utc)
    else:
        ts = datetime(ref.sitting_date.year, ref.sitting_date.month,
                      ref.sitting_date.day, 13, 30, tzinfo=timezone.utc)

    for s in speeches:
        pol_id, conf = _resolve_politician(s, slug_lookup, lastname_lookup)
        raw_payload = {
            "extractor": "sk_hansard/v1",
            "section_label": s.section_label,
            "speaker_role_detected": s.speaker_role,
            "candidate_slug": s.candidate_slug,
            "first_name_detected": s.first_name,
            "last_name_detected": s.last_name,
        }
        result = await _upsert_speech(
            db,
            session_id=session_id,
            politician_id=pol_id,
            confidence=conf,
            speech=s,
            spoken_at=ts,
            canonical_url=ref.canonical_url,
            raw_payload=raw_payload,
            raw_html=html if s.sequence == 1 else None,  # store raw_html once per sitting
        )
        if result == "inserted":
            stats.speeches_inserted += 1
        else:
            stats.speeches_updated += 1


# ── Public entry point ─────────────────────────────────────────────


async def ingest_sk_hansard(
    db: Database,
    *,
    limit_sittings: Optional[int] = None,
    since: Optional[Date] = None,
    url: Optional[str] = None,
    delay: float = 1.0,
    max_archive_pages: Optional[int] = None,
) -> IngestStats:
    """Discover, fetch, parse, and upsert SK Hansard transcripts.

    Args:
      limit_sittings: cap to first N sittings (newest-first ordering).
      since: only process sittings on or after this date.
      url: bypass discovery; ingest a single transcript URL.
      delay: seconds between per-sitting fetches.
      max_archive_pages: cap discovery walker (defensive).
    """
    stats = IngestStats()

    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True) as client:
        if url:
            m_html = _ASSEMBLY_HANSARD_HTML_RE.match(url)
            m_pdf = _ASSEMBLY_HANSARD_PDF_RE.match(url) if not m_html else None
            if m_html:
                ref = SittingRef(
                    parliament=int(m_html.group("parl")),
                    session=int(m_html.group("sess")),
                    sitting_date=Date(int(m_html.group("ymd")[:4]),
                                      int(m_html.group("ymd")[4:6]),
                                      int(m_html.group("ymd")[6:8])),
                    canonical_url=url, fmt="html", time_of_day="main",
                )
            elif m_pdf:
                ref = SittingRef(
                    parliament=int(m_pdf.group("parl")),
                    session=int(m_pdf.group("sess")),
                    sitting_date=Date(int(m_pdf.group("ymd")[:4]),
                                      int(m_pdf.group("ymd")[4:6]),
                                      int(m_pdf.group("ymd")[6:8])),
                    canonical_url=url, fmt="pdf",
                    time_of_day=_suffix_to_time_of_day(m_pdf.group("suffix")),
                )
            else:
                stats.fetch_failures.append(f"unrecognised SK Hansard URL: {url}")
                return stats
            refs = [ref]
        else:
            refs = await discover_sittings(client, max_pages=max_archive_pages)
            stats.pages_walked = (max_archive_pages or 0)
            log.info("sk_hansard: discovery yielded %d sittings", len(refs))

        stats.sittings_seen = len(refs)
        # Newest-first ordering aligns with operator expectations.
        refs.sort(key=lambda r: r.sitting_date, reverse=True)
        if since is not None:
            refs = [r for r in refs if r.sitting_date >= since]
        if limit_sittings is not None:
            refs = refs[:limit_sittings]

        slug_lookup = await _load_slug_lookup(db)
        lastname_lookup = await _load_lastname_lookup(db)
        html_count = sum(1 for r in refs if r.fmt == "html")
        pdf_count = sum(1 for r in refs if r.fmt == "pdf")
        log.info(
            "sk_hansard: %d sittings to ingest (html=%d pdf=%d); %d slug-keyed politicians",
            len(refs), html_count, pdf_count, len(slug_lookup),
        )

        for ref in refs:
            if ref.fmt == "pdf":
                pdf_bytes = await _fetch_pdf_bytes(client, ref.canonical_url)
                if pdf_bytes is None:
                    stats.fetch_failures.append(ref.canonical_url)
                    stats.sittings_skipped += 1
                    continue
                stats.sittings_fetched += 1
                try:
                    await _ingest_pdf_sitting(
                        db, ref, pdf_bytes, slug_lookup, lastname_lookup, stats,
                    )
                except Exception as exc:
                    stats.parse_failures.append(f"{ref.canonical_url}: {exc}")
                    log.exception("sk_hansard: pdf ingest failed for %s", ref.canonical_url)
            else:
                html = await _fetch(client, ref.canonical_url)
                if html is None:
                    stats.fetch_failures.append(ref.canonical_url)
                    stats.sittings_skipped += 1
                    continue
                stats.sittings_fetched += 1
                try:
                    await _ingest_sitting(db, ref, html, slug_lookup, lastname_lookup, stats)
                except Exception as exc:
                    stats.parse_failures.append(f"{ref.canonical_url}: {exc}")
                    log.exception("sk_hansard: ingest failed for %s", ref.canonical_url)
            await asyncio.sleep(delay)

    log.info(
        "sk_hansard: walked=%d seen=%d fetched=%d skipped=%d "
        "speeches_inserted=%d speeches_updated=%d sessions=%d "
        "fetch_failures=%d parse_failures=%d",
        stats.pages_walked, stats.sittings_seen, stats.sittings_fetched,
        stats.sittings_skipped,
        stats.speeches_inserted, stats.speeches_updated,
        len(stats.sessions_touched),
        len(stats.fetch_failures), len(stats.parse_failures),
    )
    return stats
