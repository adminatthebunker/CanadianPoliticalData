"""NU Hansard ingester — Nunavut Legislative Assembly PDFs → `speeches`.

Source: ``https://www.assembly.nu.ca/hansard`` — Drupal 9 page listing
~59 sitting PDFs back to 2021-02-24. Each PDF lives at
``/sites/default/files/<YYYY-MM>/<YYYYMMDD>_Hansard.pdf``.

## Bilingual / multilingual handling

Per the 2026-05-14 probe, NU publishes a single English-primary PDF per
sitting with inline ``(interpretation)`` markers wrapping Inuktitut
passages. ``/iu/hansard-iu`` and ``/IU-CA/hansard-ius`` paths are
language-switched chrome with no PDF index — so we only ingest the EN
PDFs. Inuktitut and French translations are reachable per-document but
not via the index.

## Speaker shapes

NU consensus government, so no party affiliation — ``party_at_time``
stays NULL on every row. Speaker turns in the PDF text follow these
shapes:

    Speaker (Hon. Tony Akoak) (interpretation): Good morning...
    Hon. David Akeeagok (interpretation): Good morning, my colleagues.
    Mr. Adam Lightstone: Thank you, Mr. Speaker...
    Ms. Mary Killiktee: ...
    Joelie Kaernerk (Amittuq): ...  [constituency in parens]

Resolution is name-based against the existing NU politicians roster
(``last_name`` + ``constituency_name``). Presiding-officer turns
(``Speaker (...)``, ``Chairman``) carry ``speaker_role`` and defer to
``resolve-presiding-speakers --province NU`` for date-windowed lookup
(roster TBD).

## Idempotency

Upsert keyed on ``(source_system='hansard-nu', source_url, sequence)``.
``raw_html`` carries the full pdftotext output for re-parsing.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from dataclasses import dataclass, field as dc_field
from datetime import date, datetime, time, timezone
from typing import Optional

import httpx
import orjson

from ..db import Database
from .pdf_utils import pdftotext as _pdftotext

log = logging.getLogger(__name__)

WEB_ROOT = "https://www.assembly.nu.ca"
HANSARD_INDEX_URL = f"{WEB_ROOT}/hansard"
SOURCE_SYSTEM = "hansard-nu"
REQUEST_TIMEOUT = 60

HEADERS = {
    "User-Agent": "SovereignWatch/1.0 (civic-transparency; +admin@thebunkerops.ca)",
    "Accept": "text/html,application/pdf",
}

# Filename pattern: /sites/default/files/<YYYY-MM>/<YYYYMMDD>_Hansard*.pdf
_PDF_HREF_RE = re.compile(
    r'href="(/sites/default/files/[^"]*?(\d{8})_Hansard[^"]*?\.pdf)"',
    re.IGNORECASE,
)


# ── Models ──────────────────────────────────────────────────────────


@dataclass
class SittingRef:
    sitting_date: date
    url: str  # absolute


@dataclass
class ParsedSpeech:
    sequence: int
    speaker_name_raw: str
    speaker_role: Optional[str]
    constituency_raw: Optional[str]
    is_interpretation: bool
    text: str


@dataclass
class IngestStats:
    sittings_seen: int = 0
    sittings_fetched: int = 0
    sittings_skipped: int = 0
    speeches_inserted: int = 0
    speeches_updated: int = 0
    speeches_resolved: int = 0
    speeches_unresolved: int = 0
    speeches_presiding: int = 0
    sessions_touched: set = dc_field(default_factory=set)
    failures: list[str] = dc_field(default_factory=list)


# ── Discovery ────────────────────────────────────────────────────────


async def discover_sittings(client: httpx.AsyncClient) -> list[SittingRef]:
    """Fetch /hansard index and emit one SittingRef per PDF."""
    r = await client.get(HANSARD_INDEX_URL, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    seen: set[str] = set()
    out: list[SittingRef] = []
    for m in _PDF_HREF_RE.finditer(r.text):
        href = m.group(1)
        ymd = m.group(2)
        url = href if href.startswith("http") else f"{WEB_ROOT}{href}"
        if url in seen:
            continue
        seen.add(url)
        try:
            d = datetime.strptime(ymd, "%Y%m%d").date()
        except ValueError:
            continue
        out.append(SittingRef(sitting_date=d, url=url))
    return out


# ── PDF text parser ─────────────────────────────────────────────────


# Speaker-turn detection at line start. Captures honorific (Hon./Mr./Ms.),
# optional name, optional `(Constituency)` parens, optional
# `(interpretation)` marker, then `:` and the speech body.
# Pattern is intentionally wide; the post-match cleanup decides whether
# to treat the row as a real speech or stage direction.
_SPEAKER_LINE_RE = re.compile(
    r"^(?P<role>Speaker|Chairman|Co-Chair|Deputy\s+Speaker|Mr\.|Ms\.|Mrs\.|Hon\.)"
    r"\s+"
    r"(?P<name>[^()\n:]+?)"
    r"(?:\s+\((?P<constituency>[^)\n]+?)\))?"
    r"(?:\s+\((?P<interp>interpretation(?:\s+ends)?)\))?"
    r"\s*:\s*(?P<body>.*)$",
    re.IGNORECASE,
)

# Speaker (named) — `Speaker (Hon. Tony Akoak)` — special-case where the
# bracketed name carries the actual person, not the constituency.
_SPEAKER_BRACKET_RE = re.compile(
    r"^Speaker\s+\((?P<title>Hon\.|Mr\.|Ms\.|Mrs\.)?\s*"
    r"(?P<name>[^)\n]+)\)\s*"
    r"(?:\((?P<interp>interpretation(?:\s+ends)?)\))?"
    r"\s*:\s*(?P<body>.*)$",
    re.IGNORECASE,
)

_STAGE_RE = re.compile(r"^>>")  # ">>House commenced at 9:00" etc.
_PAGE_HEADER_RE = re.compile(r"^\s*(\d+)\s*$")  # bare page number
_DATE_LINE_RE = re.compile(
    r"^\s*(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s+"
    r"(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d+",
    re.IGNORECASE,
)


def parse_pdf(pdf_text: str) -> list[ParsedSpeech]:
    """Walk pdftotext reading-order output, emit one ParsedSpeech per
    speaker turn. Continuation lines (body wraps) attach to the
    most-recent turn.
    """
    out: list[ParsedSpeech] = []
    current: Optional[dict] = None

    def flush():
        nonlocal current
        if current is None:
            return
        body = "\n".join(current["body"]).strip()
        if body:
            out.append(ParsedSpeech(
                sequence=len(out) + 1,
                speaker_name_raw=current["name"],
                speaker_role=current["role"],
                constituency_raw=current["constituency"],
                is_interpretation=current["is_interpretation"],
                text=body,
            ))
        current = None

    # Skip the TOC / front matter — start emitting speeches after the
    # first "Item 1:" or ">>House commenced" marker, whichever first.
    started = False
    for raw_line in pdf_text.split("\n"):
        line = raw_line.rstrip()
        stripped = line.strip()
        if not started:
            if (
                stripped.startswith(("Item 1:", "Item 2:", ">>House commenced", ">>Prayer"))
                or _SPEAKER_BRACKET_RE.match(stripped)
            ):
                started = True
            else:
                continue
        if not stripped:
            continue
        # Skip page headers, date lines, "Nunavut Hansard" footer.
        if _PAGE_HEADER_RE.match(stripped):
            continue
        if _DATE_LINE_RE.match(stripped):
            continue
        if stripped in ("Nunavut Hansard", "Iqaluit, Nunavut"):
            continue
        if _STAGE_RE.match(stripped):
            # Stage direction — attach to current turn if any, else skip.
            if current is not None:
                current["body"].append(stripped)
            continue

        # Speaker (bracketed name) — Speaker(Hon. Tony Akoak): ...
        mb = _SPEAKER_BRACKET_RE.match(stripped)
        if mb:
            flush()
            title = (mb.group("title") or "").strip()
            name = (mb.group("name") or "").strip()
            interp = mb.group("interp")
            current = {
                "name": f"Speaker ({title + ' ' if title else ''}{name})".strip(),
                "role": "Speaker",
                "constituency": None,
                "is_interpretation": bool(interp),
                "body": [mb.group("body").strip()],
            }
            continue

        # Plain speaker turn.
        m = _SPEAKER_LINE_RE.match(stripped)
        if m and ":" in stripped:
            role_raw = (m.group("role") or "").strip()
            name = (m.group("name") or "").strip()
            constituency = m.group("constituency")
            interp = m.group("interp")
            # Filter out false positives: lines like "Mr. Speaker, ..."
            # where "Mr. Speaker" is referential, not a speaker label.
            # Heuristic: if the post-colon body is empty or the name
            # looks like a continuation, skip.
            if not name or len(name) > 80:
                if current is not None:
                    current["body"].append(stripped)
                continue
            # False-positive filter: lines like "Mr. Speaker, my
            # questions are:" — the captured "name" is "Speaker,
            # my questions are" which is referential, not vocative.
            # If the captured name contains a comma or more than three
            # whitespace-delimited tokens, it's prose mid-sentence —
            # attach as a continuation line, not a new turn.
            if "," in name or len(name.split()) > 3:
                if current is not None:
                    current["body"].append(stripped)
                continue
            flush()
            speaker_role: Optional[str] = None
            if role_raw.lower().startswith(("speaker", "chairman", "co-chair", "deputy speaker")):
                speaker_role = role_raw.strip()
            current = {
                "name": f"{role_raw} {name}".strip(),
                "role": speaker_role,
                "constituency": constituency.strip() if constituency else None,
                "is_interpretation": bool(interp),
                "body": [m.group("body").strip()],
            }
            continue

        # Continuation line.
        if current is not None:
            current["body"].append(stripped)
    flush()
    return out


# ── DB resolution ────────────────────────────────────────────────────


async def _load_nu_politician_index(db: Database) -> dict[str, list[dict]]:
    """Return {surname_key: [pol_row, ...]} for NU politicians.

    Indexes by the full lowercase last_name AND by each whitespace-
    delimited token within it. This means "Pitsiulaaq Brewster" is
    reachable as both "pitsiulaaq brewster" (full) and "brewster"
    (token) — important because Hansard PDFs address MLAs by short
    surname even when our DB carries the multi-word form.
    """
    rows = await db.fetch(
        """
        SELECT id::text AS politician_id,
               name,
               LOWER(last_name) AS last_lower,
               last_name,
               first_name,
               constituency_name
          FROM politicians
         WHERE level='provincial' AND province_territory='NU'
        """
    )
    out: dict[str, list[dict]] = {}
    for r in rows:
        full = (r["last_lower"] or "").strip()
        if not full:
            continue
        keys = {full}
        # Token-split for multi-word last names (Inuit-language naming
        # often appends a clan/lineage name as a second token).
        keys.update(t for t in full.split() if t)
        rec = dict(r)
        for k in keys:
            out.setdefault(k, []).append(rec)
    return out


def _resolve_speaker(
    parsed: ParsedSpeech,
    pol_index: dict[str, list[dict]],
) -> Optional[str]:
    """Return politician_id for a parsed speech's speaker, or None.

    Disambiguation order when multiple surname candidates:
      1. ``(Constituency)`` parens from PDF, if present.
      2. First-name match (PDF carries "Hon. P.J. Akeeagok" /
         "Hon. David Akeeagok" so the first token after the honorific
         is the disambiguator — match against politicians.first_name
         leading token).
      3. Give up — leave politician_id NULL.
    """
    if parsed.speaker_role:
        # Presiding-officer turn — defer to a separate resolver.
        return None
    # Extract name tokens after the honorific.
    raw = parsed.speaker_name_raw
    tokens = raw.split()
    if not tokens:
        return None
    if tokens[0].lower() in {"hon.", "mr.", "ms.", "mrs."}:
        tokens = tokens[1:]
    if not tokens:
        return None

    # Look up by last token first, then by last-two-tokens (catches
    # multi-word surnames like "Healey Akearok").
    surname_candidates = [tokens[-1].lower()]
    if len(tokens) >= 2:
        surname_candidates.append(" ".join(tokens[-2:]).lower())
    candidates: list[dict] = []
    for sk in surname_candidates:
        if sk in pol_index:
            candidates = pol_index[sk]
            break
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]["politician_id"]

    # Multiple — try constituency disambiguator first.
    if parsed.constituency_raw:
        wanted = parsed.constituency_raw.lower()
        for c in candidates:
            cc = (c.get("constituency_name") or "").lower()
            if cc and wanted in cc:
                return c["politician_id"]

    # First-name disambiguator. PDF speaker labels carry the first
    # name(s) before the surname; everything between the honorific and
    # the surname is the given-name portion. Normalize aggressively:
    # strip all dots + collapse all whitespace, then case-fold. This
    # makes "P.J." == "P. J." == "PJ" == "p j".
    if len(tokens) >= 2:
        first_raw = "".join(tokens[:-1]).replace(".", "").replace(" ", "").lower()
        if first_raw:
            for c in candidates:
                db_first = (c.get("first_name") or "").replace(".", "").replace(" ", "").lower()
                if db_first and db_first == first_raw:
                    return c["politician_id"]
    return None


# ── DB upsert ───────────────────────────────────────────────────────


async def _ensure_nu_session(
    db: Database, *, sitting_date: date,
) -> str:
    """Resolve session_id for the (assembly, session) covering this sitting.

    NU is currently in 6th Assembly, 2nd Session. Without a date-windowed
    sessions table we look up the most recent NU session row; new
    sessions land via the bills ingester.
    """
    row = await db.fetchrow(
        """
        SELECT id::text AS id
          FROM legislative_sessions
         WHERE level='provincial' AND province_territory='NU'
         ORDER BY parliament_number DESC, session_number DESC
         LIMIT 1
        """
    )
    if row:
        return row["id"]
    # Seed a placeholder session if none exists.
    row = await db.fetchrow(
        """
        INSERT INTO legislative_sessions (
            level, province_territory, parliament_number, session_number,
            name, source_system, source_url
        )
        VALUES ('provincial', 'NU', 6, 2,
                '6th Assembly, 2nd Session',
                $1, $2)
        ON CONFLICT (level, province_territory, parliament_number, session_number)
        DO UPDATE SET updated_at = now()
        RETURNING id::text AS id
        """,
        SOURCE_SYSTEM, HANSARD_INDEX_URL,
    )
    return row["id"]


async def _upsert_speech(
    db: Database, *,
    session_id: str,
    sitting_date: date,
    speech: ParsedSpeech,
    politician_id: Optional[str],
    source_url: str,
    stats: IngestStats,
) -> None:
    spoken_at = datetime.combine(sitting_date, time(12, 0), tzinfo=timezone.utc)
    language = "iu" if speech.is_interpretation else "en"
    raw_payload = {
        "nu_hansard": {
            "is_interpretation": speech.is_interpretation,
            "constituency_raw": speech.constituency_raw,
        }
    }
    content_hash = hashlib.sha256(
        f"{source_url}|{speech.sequence}|{speech.text}".encode("utf-8")
    ).hexdigest()
    row = await db.fetchrow(
        """
        INSERT INTO speeches (
            session_id, politician_id, level, province_territory,
            speaker_name_raw, speaker_role, party_at_time,
            constituency_at_time, confidence, speech_type,
            spoken_at, sequence, language, text,
            source_system, source_url, raw,
            content_hash
        ) VALUES (
            $1::uuid, $2, 'provincial', 'NU',
            $3, $4, NULL,
            $5, 1.0, 'turn',
            $6, $7, $8, $9,
            $10, $11, $12::jsonb,
            $13
        )
        ON CONFLICT (source_system, source_url, sequence)
        DO UPDATE SET
            politician_id = COALESCE(EXCLUDED.politician_id, speeches.politician_id),
            speaker_name_raw = EXCLUDED.speaker_name_raw,
            speaker_role = EXCLUDED.speaker_role,
            constituency_at_time = EXCLUDED.constituency_at_time,
            spoken_at = EXCLUDED.spoken_at,
            language = EXCLUDED.language,
            text = EXCLUDED.text,
            raw = EXCLUDED.raw,
            updated_at = now()
        RETURNING (xmax = 0) AS inserted
        """,
        session_id, politician_id,
        speech.speaker_name_raw, speech.speaker_role,
        speech.constituency_raw,
        spoken_at, speech.sequence, language, speech.text,
        SOURCE_SYSTEM, source_url, orjson.dumps(raw_payload).decode("utf-8"),
        content_hash,
    )
    if row["inserted"]:
        stats.speeches_inserted += 1
    else:
        stats.speeches_updated += 1
    if politician_id:
        stats.speeches_resolved += 1
    elif speech.speaker_role:
        stats.speeches_presiding += 1
    else:
        stats.speeches_unresolved += 1
    stats.sessions_touched.add(session_id)


# ── Public entry points ──────────────────────────────────────────────


async def _process_sitting(
    db: Database, *,
    sitting: SittingRef, pdf_bytes: bytes,
    pol_index: dict[str, list[dict]],
    stats: IngestStats,
) -> None:
    text = _pdftotext(pdf_bytes, layout=False)
    speeches = parse_pdf(text)
    if not speeches:
        log.warning("nu_hansard: %s — no speeches parsed", sitting.url)
        return
    session_id = await _ensure_nu_session(db, sitting_date=sitting.sitting_date)
    for sp in speeches:
        pol_id = _resolve_speaker(sp, pol_index)
        await _upsert_speech(
            db, session_id=session_id, sitting_date=sitting.sitting_date,
            speech=sp, politician_id=pol_id, source_url=sitting.url,
            stats=stats,
        )


async def ingest_nu_hansard(
    db: Database, *,
    since: Optional[date] = None,
    until: Optional[date] = None,
    limit_sittings: Optional[int] = None,
    one_off_url: Optional[str] = None,
    delay: float = 1.0,
) -> IngestStats:
    """Ingest NU Hansard PDFs into the `speeches` table.

    Modes:
      - ``one_off_url`` set → ingest one PDF (smoke test)
      - else → discover sittings via the /hansard index, filter by
        ``since`` / ``until`` / ``limit_sittings``, ingest each.

    Idempotent: re-runs UPDATE rows in place.
    """
    stats = IngestStats()
    pol_index = await _load_nu_politician_index(db)
    log.info(
        "nu_hansard: loaded %d NU politicians (%d distinct surnames)",
        sum(len(v) for v in pol_index.values()), len(pol_index),
    )

    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True) as client:
        if one_off_url:
            r = await client.get(one_off_url, timeout=REQUEST_TIMEOUT)
            r.raise_for_status()
            # Try to derive sitting date from the filename.
            m = re.search(r"(\d{8})_Hansard", one_off_url)
            if not m:
                stats.failures.append(f"can't parse date from {one_off_url}")
                return stats
            d = datetime.strptime(m.group(1), "%Y%m%d").date()
            sitting = SittingRef(sitting_date=d, url=one_off_url)
            stats.sittings_seen += 1
            stats.sittings_fetched += 1
            await _process_sitting(
                db, sitting=sitting, pdf_bytes=r.content,
                pol_index=pol_index, stats=stats,
            )
            return stats

        sittings = await discover_sittings(client)
        stats.sittings_seen = len(sittings)
        # Filter
        if since is not None:
            sittings = [s for s in sittings if s.sitting_date >= since]
        if until is not None:
            sittings = [s for s in sittings if s.sitting_date <= until]
        sittings.sort(key=lambda s: s.sitting_date, reverse=True)
        if limit_sittings:
            sittings = sittings[: int(limit_sittings)]

        for sitting in sittings:
            try:
                r = await client.get(sitting.url, timeout=REQUEST_TIMEOUT)
                r.raise_for_status()
            except httpx.HTTPError as e:
                stats.failures.append(f"fetch {sitting.url}: {e}")
                stats.sittings_skipped += 1
                continue
            stats.sittings_fetched += 1
            await _process_sitting(
                db, sitting=sitting, pdf_bytes=r.content,
                pol_index=pol_index, stats=stats,
            )
            if delay > 0:
                await asyncio.sleep(delay)

    log.info(
        "nu_hansard: sittings seen=%d fetched=%d skipped=%d "
        "speeches inserted=%d updated=%d resolved=%d presiding=%d unresolved=%d",
        stats.sittings_seen, stats.sittings_fetched, stats.sittings_skipped,
        stats.speeches_inserted, stats.speeches_updated, stats.speeches_resolved,
        stats.speeches_presiding, stats.speeches_unresolved,
    )
    return stats
