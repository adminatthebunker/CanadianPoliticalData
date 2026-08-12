"""SK committee Hansard ingester — Hansard Verbatim Reports → ``speeches``.

Committee layer over the SK chamber pipeline (``sk_hansard.py``), following
the federal/AB/BC reuse-not-fork pattern: discovery + committee-aware
speaker resolution here; parsing via the existing chamber parsers
(``sk_hansard_parse.parse_hansard_html`` for the Word-15 HTML exports,
``sk_hansard_pdf_parse.extract_speeches_from_text`` for PDF-only meetings).

## Discovery

Same paginated archive the chamber walker uses
(https://www.legassembly.sk.ca/legislative-business/archive/?page=N), but
matching the committee document family the chamber regexes deliberately
skip:

    …/legdocs/Committees/{ACR}/Debates/{NN}L/{YYYYMMDD}Debates-{ACR}-HTML.htm
    …/legdocs/Committees/{ACR}/Debates/{NN}L/{YYYYMMDD}Debates-{ACR}.pdf

Only the ``/Debates/`` family is verbatim Hansard — Minutes / Notices /
Reports / Tableddocs live in sibling paths and are excluded by the regex.
HTML wins over PDF for the same (acronym, legislature, date) key, mirroring
the chamber dedup. Probed 2026-08-12: both formats published per meeting on
30L; depth to late 1990s per the archive's own description.

## Session resolution

Committee paths carry the legislature only (``30L``) — no session digit.
``legislative_sessions`` SK rows have no start/end dates, so session
boundaries are derived empirically from the chamber corpus: the first
chamber sitting date of each session (via ``speeches`` ⋈
``legislative_sessions``). A meeting belongs to the latest session whose
first sitting is on/before the meeting date (committees regularly meet
intersessionally after the house rises — those belong to the ongoing
session). Meetings before the parliament's first known sitting land in
session 1.

## Speaker resolution — witness-safe by construction

SK committee transcripts label members with FULL names (``Hugh Gordon: —``,
``Chair Wotherspoon: —``) unlike the chamber's honorific+surname style, and
there is no structured attendance block (the Chair introduces members in
prose). Resolution therefore deliberately narrows the chamber resolver:

  1. full-name slug hit (``candidate_slug`` ∈ sk_assembly_slug) → conf 1.0
  2. Chair / Deputy Chair surname shapes → single-candidate surname
     lookup → conf 0.85 (chairs are always members)
  3. ``Hon. First Last`` (ministers at estimates) → slug, then
     single-candidate surname → 0.85
  4. plain full-name label whose slug misses → **witness, NULL, conf 0.0**
     — no surname fallback. This is the AB lesson (witness "Mr. Lord" →
     MLA Lord over-match) inverted through SK's full-name convention: a
     full-name label that isn't an MLA's full name is a witness, and
     falling back to surname would re-introduce exactly the collision the
     convention protects against.

``politician_committees`` has no SK rows, so there is no membership-
restricted tier; the full-name gate substitutes for it.
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
from .sk_hansard import (
    ARCHIVE_URL,
    HEADERS,
    SOURCE_SYSTEM,
    _ensure_session,
    _fetch,
    _fetch_pdf_bytes,
    _load_lastname_lookup,
    _load_slug_lookup,
)
from .sk_hansard_parse import ParsedSpeech, parse_hansard_html
from .sk_hansard_pdf_parse import (
    ParsedSpeech as PDFParsedSpeech,
    extract_speeches_from_text,
)
from .pdf_utils import pdftotext as _pdftotext

log = logging.getLogger(__name__)

# Acronym → display name. Enumerated from the archive + committee pages
# 2026-08-12 (29L + 30L). An acronym missing here still ingests (the
# acronym doubles as the name) but logs an error so the operator adds it —
# a renamed/new committee must never become a silent hole.
KNOWN_COMMITTEES: dict[str, str] = {
    "BIE": "Board of Internal Economy",
    "CCA": "Standing Committee on Crown and Central Agencies",
    "ECO": "Standing Committee on the Economy",
    "HOS": "Standing Committee on House Services",
    "HUS": "Standing Committee on Human Services",
    "IAJ": "Standing Committee on Intergovernmental Affairs and Justice",
    "PAC": "Standing Committee on Public Accounts",
    "PBC": "Standing Committee on Private Bills",
    "PRV": "Standing Committee on Privileges",
}

_COMMITTEE_HTML_RE = re.compile(
    r"https://docs\.legassembly\.sk\.ca/legdocs/Committees/"
    r"(?P<acr>[A-Za-z]+)/Debates/(?P<legl>\d+)L/"
    r"(?P<ymd>\d{8})Debates-(?P=acr)-HTML\.htm",
    re.IGNORECASE,
)
_COMMITTEE_PDF_RE = re.compile(
    r"https://docs\.legassembly\.sk\.ca/legdocs/Committees/"
    r"(?P<acr>[A-Za-z]+)/Debates/(?P<legl>\d+)L/"
    r"(?P<ymd>\d{8})Debates-(?P=acr)\.pdf",
    re.IGNORECASE,
)

# "[The committee met at 09:00.]" — committee transcripts carry their start
# time in a bracket line instead of the chamber masthead.
_MET_AT_RE = re.compile(r"\[\s*The\s+committee\s+met\s+at\s+(\d{1,2}):(\d{2})",
                        re.IGNORECASE)

# "Chair Wotherspoon" / "Deputy Chair Thorsteinson" — the chamber
# classifier's role-only `^(the )?chair\b` branch fires before its
# named-chair branch, so these arrive with role set but last_name=None.
# Recover the surname from the raw label here.
_CHAIR_NAME_RE = re.compile(
    r"^(?:the\s+)?(?:deputy\s+)?chair(?:\s+of\s+committees?)?\s+"
    r"(?P<last>[A-Z][\w'’\-]+)\s*$",
    re.IGNORECASE,
)


@dataclass
class CommitteeMeetingRef:
    acronym: str
    legislature: int
    meeting_date: Date
    canonical_url: str
    fmt: str = "html"  # 'html' or 'pdf'

    @property
    def committee_name(self) -> str:
        return KNOWN_COMMITTEES.get(self.acronym, self.acronym)


@dataclass
class CommitteeIngestStats:
    meetings_seen: int = 0
    meetings_fetched: int = 0
    meetings_skipped: int = 0
    speeches_inserted: int = 0
    speeches_updated: int = 0
    resolved: int = 0
    witnesses: int = 0
    unknown_acronyms: set[str] = dc_field(default_factory=set)
    sessions_touched: set[str] = dc_field(default_factory=set)
    fetch_failures: list[str] = dc_field(default_factory=list)
    parse_failures: list[str] = dc_field(default_factory=list)


async def discover_committee_meetings(
    client: httpx.AsyncClient, *, max_pages: Optional[int] = None,
) -> list[CommitteeMeetingRef]:
    """Walk the archive pager, return one ref per committee meeting.

    HTML wins over PDF per (acronym, legislature, date) — same dedup rule
    as the chamber walker. Termination mirrors the chamber walker's
    two-consecutive-empty-pages rule, counting only committee matches.
    """
    seen_urls: set[str] = set()
    by_key: dict[tuple[str, int, str], CommitteeMeetingRef] = {}
    page = 0
    consecutive_empty = 0
    while True:
        url = ARCHIVE_URL if page == 0 else f"{ARCHIVE_URL}?page={page}"
        html = await _fetch(client, url)
        if html is None:
            break
        new_for_page = 0
        for regex, fmt in ((_COMMITTEE_HTML_RE, "html"),
                           (_COMMITTEE_PDF_RE, "pdf")):
            for m in regex.finditer(html):
                full_url = m.group(0)
                if full_url in seen_urls:
                    continue
                seen_urls.add(full_url)
                ymd = m.group("ymd")
                try:
                    d = Date(int(ymd[:4]), int(ymd[4:6]), int(ymd[6:8]))
                except ValueError:
                    continue
                acr = m.group("acr").upper()
                key = (acr, int(m.group("legl")), ymd)
                existing = by_key.get(key)
                if existing is not None and existing.fmt == "html":
                    continue
                by_key[key] = CommitteeMeetingRef(
                    acronym=acr,
                    legislature=int(m.group("legl")),
                    meeting_date=d,
                    canonical_url=full_url,
                    fmt=fmt,
                )
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


async def _session_first_sittings(
    db: Database, parliament: int,
) -> list[tuple[int, Date]]:
    """[(session_number, first chamber sitting date), …] ascending.

    Empirical session boundaries — SK ``legislative_sessions`` rows carry
    no start/end dates, but the chamber corpus does.
    """
    rows = await db.fetch(
        """
        SELECT ls.session_number, min(s.spoken_at)::date AS first_sit
          FROM speeches s
          JOIN legislative_sessions ls ON ls.id = s.session_id
         WHERE s.level = 'provincial'
           AND s.province_territory = 'SK'
           AND s.source_system = $1
           AND s.speech_type = 'hansard'
           AND ls.parliament_number = $2
         GROUP BY 1
         ORDER BY 1
        """,
        SOURCE_SYSTEM, parliament,
    )
    return [(int(r["session_number"]), r["first_sit"]) for r in rows]


def _session_for_date(
    boundaries: list[tuple[int, Date]], meeting_date: Date,
) -> int:
    """Latest session whose first sitting is on/before the meeting date."""
    chosen = boundaries[0][0] if boundaries else 1
    for session, first_sit in boundaries:
        if first_sit <= meeting_date:
            chosen = session
    return chosen


def _norm_surname(s: str) -> str:
    import unicodedata
    text = unicodedata.normalize("NFKD", s.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", text)


def _resolve_committee_speaker(
    *,
    candidate_slug: Optional[str],
    last_name: Optional[str],
    first_name: Optional[str],
    role: Optional[str],
    is_chorus: bool,
    speaker_name_raw: str,
    slug_lookup: dict[str, str],
    lastname_lookup: dict[str, list[tuple[str, str]]],
) -> tuple[Optional[str], float]:
    """Witness-safe resolution — see module docstring for the tier design."""
    if is_chorus:
        return None, 0.3
    # Tier 1: full-name slug (members and Hon. ministers both produce one).
    if candidate_slug and candidate_slug in slug_lookup:
        return slug_lookup[candidate_slug], 1.0
    role_bearing = role in ("chair", "deputy_chair", "minister", "speaker",
                            "deputy_speaker")
    # The chamber classifier returns "Chair Wotherspoon" as role-only
    # (no name) — recover the surname from the raw label.
    if role_bearing and not last_name:
        m = _CHAIR_NAME_RE.match(speaker_name_raw.strip())
        if m:
            last_name = m.group("last")
    # Tier 2/3: surname fallback ONLY for shapes that cannot be witnesses —
    # chair roles and Hon.-prefixed ministers ('minister' role).
    if role_bearing and last_name:
        candidates = lastname_lookup.get(_norm_surname(last_name), [])
        if len(candidates) == 1:
            return candidates[0][0], 0.85
        if len(candidates) > 1 and first_name:
            initial = first_name[0].lower()
            narrowed = [c for c in candidates if c[1].startswith(initial)]
            if len(narrowed) == 1:
                return narrowed[0][0], 0.8
        return None, 0.5
    if role_bearing:
        # Bare role label ("The Chair") — attributable in principle,
        # never a witness.
        return None, 0.5
    # Plain full-name label whose slug missed → witness. No surname
    # fallback here, by design.
    return None, 0.0


def _content_hash(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


async def _upsert_committee_speech(
    db: Database, *,
    session_id: str,
    politician_id: Optional[str],
    confidence: float,
    speaker_name_raw: str,
    speaker_role: str,
    spoken_at: datetime,
    sequence: int,
    body_text: str,
    canonical_url: str,
    raw_payload: dict,
    raw_html: Optional[str],
) -> str:
    raw_json = orjson.dumps(raw_payload).decode("utf-8")
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
            $5, 'committee', $6, $7, 'en',
            $8, $9,
            $10, $11, NULL,
            $12::jsonb, $13, $14
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
        speaker_name_raw, speaker_role,
        confidence, spoken_at, sequence,
        body_text, len(body_text.split()),
        SOURCE_SYSTEM, canonical_url,
        raw_json, raw_html, _content_hash(body_text),
    )
    return "inserted" if result and result["inserted"] else "updated"


def _meeting_start(ref: CommitteeMeetingRef, text_head: str) -> datetime:
    """Meeting start timestamp — the '[The committee met at HH:MM.]'
    bracket when present, else 09:00 (SK committees typically sit
    mornings)."""
    m = _MET_AT_RE.search(text_head)
    hh, mm = (int(m.group(1)), int(m.group(2))) if m else (9, 0)
    if not (0 <= hh <= 23 and 0 <= mm <= 59):
        hh, mm = 9, 0
    return datetime(ref.meeting_date.year, ref.meeting_date.month,
                    ref.meeting_date.day, hh, mm, tzinfo=timezone.utc)


async def _ingest_meeting_html(
    db: Database, ref: CommitteeMeetingRef, html: str,
    session_id: str,
    slug_lookup: dict[str, str],
    lastname_lookup: dict[str, list[tuple[str, str]]],
    stats: CommitteeIngestStats,
) -> None:
    _meta, speeches = parse_hansard_html(html)
    if len(speeches) < 3:
        # Closed-session or minutes-shaped documents parse to nearly
        # nothing — skip rather than store fragments (BC guard).
        stats.parse_failures.append(
            f"<3 speeches parsed ({len(speeches)}): {ref.canonical_url}")
        return
    # Word-15 markup splits text runs with spans/entities — strip before
    # matching the "[The committee met at HH:MM.]" bracket.
    head_text = re.sub(r"&nbsp;|\s+", " ",
                       re.sub(r"<[^>]+>", " ", html[:40000]))
    ts = _meeting_start(ref, head_text)
    for s in speeches:
        pol_id, conf = _resolve_committee_speaker(
            candidate_slug=s.candidate_slug,
            last_name=s.last_name,
            first_name=s.first_name,
            role=s.speaker_role,
            is_chorus=s.is_chorus,
            speaker_name_raw=s.speaker_name_raw,
            slug_lookup=slug_lookup,
            lastname_lookup=lastname_lookup,
        )
        if pol_id:
            stats.resolved += 1
        elif conf == 0.0:
            stats.witnesses += 1
        raw_payload = {
            "sk_committee": {
                "extractor": "sk_committees/v1",
                "committee_acronym": ref.acronym,
                "committee_name": ref.committee_name,
                "legislature": ref.legislature,
                "meeting_date": ref.meeting_date.isoformat(),
                "section_label": s.section_label,
                "speaker_role_detected": s.speaker_role,
                "candidate_slug": s.candidate_slug,
            },
        }
        result = await _upsert_committee_speech(
            db,
            session_id=session_id,
            politician_id=pol_id,
            confidence=conf,
            speaker_name_raw=s.speaker_name_raw,
            speaker_role=("chorus" if s.is_chorus
                          else s.speaker_role or "member"),
            spoken_at=ts,
            sequence=s.sequence,
            body_text=s.body_text,
            canonical_url=ref.canonical_url,
            raw_payload=raw_payload,
            raw_html=html if s.sequence == 1 else None,
        )
        if result == "inserted":
            stats.speeches_inserted += 1
        else:
            stats.speeches_updated += 1


async def _ingest_meeting_pdf(
    db: Database, ref: CommitteeMeetingRef, pdf_bytes: bytes,
    session_id: str,
    slug_lookup: dict[str, str],
    lastname_lookup: dict[str, list[tuple[str, str]]],
    stats: CommitteeIngestStats,
) -> None:
    try:
        text = _pdftotext(pdf_bytes, layout=False)
    except Exception as exc:
        stats.parse_failures.append(
            f"pdftotext failed for {ref.canonical_url}: {exc}")
        return
    speeches = extract_speeches_from_text(text)
    if len(speeches) < 3:
        stats.parse_failures.append(
            f"<3 speeches parsed ({len(speeches)}): {ref.canonical_url}")
        return
    ts = _meeting_start(ref, text[:2000])
    for s in speeches:
        # PDF speaker lines carry surname (+ optional initial), no slug.
        # The full-name witness gate can't apply; restrict surname
        # resolution to role-bearing shapes exactly like the HTML path
        # (plain member surnames in committee PDFs risk witness
        # collisions, so they stay NULL).
        pol_id, conf = _resolve_committee_speaker(
            candidate_slug=None,
            last_name=s.surname,
            first_name=s.initial,
            role=s.speaker_role,
            is_chorus=s.is_chorus,
            speaker_name_raw=s.speaker_name_raw,
            slug_lookup=slug_lookup,
            lastname_lookup=lastname_lookup,
        )
        if pol_id:
            stats.resolved += 1
        elif conf == 0.0:
            stats.witnesses += 1
        raw_payload = {
            "sk_committee": {
                "extractor": "sk_committees_pdf/v1",
                "committee_acronym": ref.acronym,
                "committee_name": ref.committee_name,
                "legislature": ref.legislature,
                "meeting_date": ref.meeting_date.isoformat(),
                "section_label": s.section,
                "speaker_role_detected": s.speaker_role,
                "honorific": s.honorific,
                "surname": s.surname,
            },
        }
        result = await _upsert_committee_speech(
            db,
            session_id=session_id,
            politician_id=pol_id,
            confidence=conf,
            speaker_name_raw=s.speaker_name_raw,
            speaker_role=("chorus" if s.is_chorus
                          else s.speaker_role or "member"),
            spoken_at=ts,
            sequence=s.sequence,
            body_text=s.body,
            canonical_url=ref.canonical_url,
            raw_payload=raw_payload,
            raw_html=None,
        )
        if result == "inserted":
            stats.speeches_inserted += 1
        else:
            stats.speeches_updated += 1


async def ingest_sk_committees(
    db: Database,
    *,
    legislature: Optional[int] = None,
    since: Optional[Date] = None,
    until: Optional[Date] = None,
    limit_meetings: Optional[int] = None,
    committees: Optional[list[str]] = None,
    url: Optional[str] = None,
    delay: float = 1.0,
    max_archive_pages: Optional[int] = None,
) -> CommitteeIngestStats:
    """Discover, fetch, parse, and upsert SK committee Hansard.

    Flag-less runs process every meeting the archive lists for the given
    (or current) legislature — full re-list, idempotent upserts, per the
    no-fixed-window forward-ingest rule.
    """
    stats = CommitteeIngestStats()
    committees_filter = (
        {c.strip().upper() for c in committees if c.strip()}
        if committees else None
    )

    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True) as client:
        if url:
            m = _COMMITTEE_HTML_RE.match(url) or _COMMITTEE_PDF_RE.match(url)
            if not m:
                stats.fetch_failures.append(
                    f"unrecognised SK committee URL: {url}")
                return stats
            ymd = m.group("ymd")
            refs = [CommitteeMeetingRef(
                acronym=m.group("acr").upper(),
                legislature=int(m.group("legl")),
                meeting_date=Date(int(ymd[:4]), int(ymd[4:6]), int(ymd[6:8])),
                canonical_url=url,
                fmt="html" if url.lower().endswith(".htm") else "pdf",
            )]
        else:
            refs = await discover_committee_meetings(
                client, max_pages=max_archive_pages)
            log.info("sk_committees: discovery yielded %d meetings", len(refs))

        if legislature is not None:
            refs = [r for r in refs if r.legislature == legislature]
        if committees_filter:
            refs = [r for r in refs if r.acronym in committees_filter]
        if since is not None:
            refs = [r for r in refs if r.meeting_date >= since]
        if until is not None:
            refs = [r for r in refs if r.meeting_date <= until]
        refs.sort(key=lambda r: r.meeting_date, reverse=True)
        if limit_meetings is not None:
            refs = refs[:limit_meetings]
        stats.meetings_seen = len(refs)

        for ref in refs:
            if ref.acronym not in KNOWN_COMMITTEES:
                if ref.acronym not in stats.unknown_acronyms:
                    log.error(
                        "sk_committees: unknown committee acronym %s (%s) — "
                        "add it to KNOWN_COMMITTEES so it carries a display "
                        "name", ref.acronym, ref.canonical_url,
                    )
                stats.unknown_acronyms.add(ref.acronym)

        slug_lookup = await _load_slug_lookup(db)
        lastname_lookup = await _load_lastname_lookup(db)
        session_cache: dict[int, list[tuple[int, Date]]] = {}
        session_id_cache: dict[tuple[int, int], str] = {}

        for ref in refs:
            boundaries = session_cache.get(ref.legislature)
            if boundaries is None:
                boundaries = await _session_first_sittings(db, ref.legislature)
                session_cache[ref.legislature] = boundaries
            session = _session_for_date(boundaries, ref.meeting_date)
            sid = session_id_cache.get((ref.legislature, session))
            if sid is None:
                sid = await _ensure_session(
                    db, parliament=ref.legislature, session=session)
                session_id_cache[(ref.legislature, session)] = sid
            stats.sessions_touched.add(f"{ref.legislature}L{session}S")

            if ref.fmt == "pdf":
                pdf_bytes = await _fetch_pdf_bytes(client, ref.canonical_url)
                if pdf_bytes is None:
                    stats.fetch_failures.append(ref.canonical_url)
                    stats.meetings_skipped += 1
                    continue
                stats.meetings_fetched += 1
                try:
                    await _ingest_meeting_pdf(
                        db, ref, pdf_bytes, sid,
                        slug_lookup, lastname_lookup, stats)
                except Exception as exc:
                    stats.parse_failures.append(f"{ref.canonical_url}: {exc}")
                    log.exception("sk_committees: pdf ingest failed for %s",
                                  ref.canonical_url)
            else:
                html = await _fetch(client, ref.canonical_url)
                if html is None:
                    stats.fetch_failures.append(ref.canonical_url)
                    stats.meetings_skipped += 1
                    continue
                stats.meetings_fetched += 1
                try:
                    await _ingest_meeting_html(
                        db, ref, html, sid,
                        slug_lookup, lastname_lookup, stats)
                except Exception as exc:
                    stats.parse_failures.append(f"{ref.canonical_url}: {exc}")
                    log.exception("sk_committees: ingest failed for %s",
                                  ref.canonical_url)
            await asyncio.sleep(delay)

    log.info(
        "sk_committees: seen=%d fetched=%d skipped=%d inserted=%d updated=%d "
        "resolved=%d witnesses=%d sessions=%s unknown_acronyms=%s "
        "fetch_failures=%d parse_failures=%d",
        stats.meetings_seen, stats.meetings_fetched, stats.meetings_skipped,
        stats.speeches_inserted, stats.speeches_updated,
        stats.resolved, stats.witnesses,
        sorted(stats.sessions_touched), sorted(stats.unknown_acronyms),
        len(stats.fetch_failures), len(stats.parse_failures),
    )
    return stats
