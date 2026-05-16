"""SK Journals → `votes` + `vote_positions` extractor.

SK publishes session-aggregated Journals as bilingual EN/FR PDFs at
`https://www.legassembly.sk.ca/legislative-business/journals/`. Each
PDF contains recorded-division pages with a stable shape:

    YEAS / POUR — 32
    [5-column surname grid; collisions disambiguated as
     `Surname (Constituency)` — e.g. `McLeod (Moose Jaw North)` vs
     `McLeod (Lumsden-Morse)`]

    NAYS / CONTRE — 11
    [same shape]

This is dramatically richer than the consensus-shape extractors used
for MB / NL / NT (which leave `vote_positions` empty) — SK is the
first non-federal jurisdiction where per-MLA YEA/NAY positions land.

## Parser shape

We use `pdftotext` without `-layout` to get reading-order one-name-per-
line output, then walk a small state machine to handle paren
wrapping (`Surname (Wrapped\nConstituency)`) and constituency-only
disambiguation suffix lines.

## Resolution

Surnames FK-match against `politicians` WHERE `sk_assembly_slug IS NOT
NULL`. Collisions are disambiguated by `politician_terms` date-window
(the sitting date must fall within `[started_at, ended_at]`) plus the
optional `(Constituency)` parens captured at parse time.

## Idempotency

`source_url` is unique-keyed on the canonical PDF page anchor
(`<pdf_url>#page=N`). Re-runs UPDATE the votes/positions rows in place.
"""

from __future__ import annotations

import asyncio
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

SOURCE_SYSTEM = "votes-sk"
WEB_ROOT = "https://www.legassembly.sk.ca"
JOURNALS_INDEX_URL = f"{WEB_ROOT}/legislative-business/journals/"
REQUEST_TIMEOUT = 60

HEADERS = {
    "User-Agent": "SovereignWatch/1.0 (civic-transparency; +admin@thebunkerops.ca)",
    "Accept": "text/html,application/xhtml+xml,application/pdf",
}

# ── Stats ────────────────────────────────────────────────────────────


@dataclass
class IngestStats:
    journals_seen: int = 0
    journals_fetched: int = 0
    journals_skipped: int = 0
    pages_scanned: int = 0
    divisions_seen: int = 0
    votes_inserted: int = 0
    votes_updated: int = 0
    positions_inserted: int = 0
    positions_updated: int = 0
    bill_links: int = 0
    politician_links: int = 0
    politicians_unresolved: int = 0
    failures: list[str] = dc_field(default_factory=list)


@dataclass
class ParsedCandidate:
    """One MLA's slot in a YEAS or NAYS grid."""
    surname: str
    constituency: Optional[str] = None  # disambiguator from `(...)` parens


@dataclass
class ParsedDivision:
    """One recorded division parsed from the Journal PDF."""
    page: int
    motion_text: str
    yeas_tally: int
    nays_tally: int
    yeas: list[ParsedCandidate]
    nays: list[ParsedCandidate]


@dataclass
class JournalRef:
    """One PDF Journal discovered from the index."""
    legislature: int
    session: int
    title: str
    url: str  # absolute


# ── PDF text parser ─────────────────────────────────────────────────


_YEAS_MARKER_RE = re.compile(
    r"^\s*YEAS\s*/\s*POUR\s*[—–-]\s*(\d+)\s*$"
)
_NAYS_MARKER_RE = re.compile(
    r"^\s*NAYS\s*/\s*CONTRE\s*[—–-]\s*(\d+)\s*$"
)
# Surname [+ optional `(...)` paren] capture. Captures Unicode letters
# / apostrophes / hyphens / dots in surnames (covers d'Autremont,
# McMorris, Carr-Stewart, etc.).
_SURNAME_RE = re.compile(
    r"^([A-ZÉÀÂÄÇÈÊËÎÏÔÖÙÛÜŸ][\w\.\-'’]*)"
    r"(?:\s+\(([^)]*)\))?\s*$",
    re.UNICODE,
)
_OPEN_PAREN_RE = re.compile(r"^([A-ZÉÀÂÄÇÈÊËÎÏÔÖÙÛÜŸ][\w\.\-'’]*)\s+\(([^)]*)$", re.UNICODE)
_CLOSE_PAREN_RE = re.compile(r"^([^)]*)\)\s*$")
_PAREN_ONLY_RE = re.compile(r"^\(([^)]*)\)\s*$")


def _page_chunks(text: str) -> list[tuple[int, str]]:
    """Split full-PDF pdftotext output into (1-indexed page, text) pairs.

    pdftotext separates pages with form-feed (\\x0c). The first chunk
    is page 1.
    """
    parts = text.split("\f")
    return [(i + 1, p) for i, p in enumerate(parts)]


def _parse_candidate_lines(
    lines: list[str], *, expected: Optional[int] = None,
) -> list[ParsedCandidate]:
    """Walk reading-order lines between a YEAS/NAYS marker and its
    successor, emitting one ParsedCandidate per MLA slot.

    Handles three shapes (one per logical entry):
      1. ``Surname``                          — single line
      2. ``Surname (Constituency)``           — single line
      3. ``Surname (Wrapped\\nConstituency)`` — two lines
      4. ``Surname\\n(Constituency)``         — two lines (constituency
                                                only-line disambiguator)

    ``expected`` is the tally announced by the YEAS/NAYS marker. When
    set, parsing stops as soon as that many candidates are emitted —
    this avoids bleeding stray non-candidate tokens from the following
    section (e.g. ROYAL ASSENT prose, ORDERS OF THE DAY headings).
    """
    out: list[ParsedCandidate] = []
    i = 0
    pending_surname: Optional[str] = None
    pending_open_paren: Optional[str] = None
    while i < len(lines):
        if expected is not None and len(out) >= expected and pending_surname is None:
            break
        ln = lines[i].strip()
        i += 1
        if not ln:
            continue

        # Continuation: closing paren on its own line completes a
        # multi-line `Surname (Wrapped\nConstituency)` entry.
        if pending_open_paren is not None:
            mc = _CLOSE_PAREN_RE.match(ln)
            if mc:
                constituency = f"{pending_open_paren} {mc.group(1)}".strip()
                out.append(ParsedCandidate(
                    surname=pending_surname or "", constituency=constituency,
                ))
                pending_surname = None
                pending_open_paren = None
                continue
            # Unexpected line; flush the pending entry without paren.
            out.append(ParsedCandidate(surname=pending_surname or ""))
            pending_surname = None
            pending_open_paren = None
            # fall through to process current line

        # Pure-paren line attaches to the most recent candidate.
        mp = _PAREN_ONLY_RE.match(ln)
        if mp:
            if out and out[-1].constituency is None:
                out[-1] = ParsedCandidate(
                    surname=out[-1].surname, constituency=mp.group(1).strip(),
                )
            continue

        # `Surname (` start of a wrapped multi-line entry.
        mo = _OPEN_PAREN_RE.match(ln)
        if mo:
            pending_surname = mo.group(1)
            pending_open_paren = mo.group(2)
            continue

        # Single-line `Surname` or `Surname (Constituency)`.
        ms = _SURNAME_RE.match(ln)
        if ms:
            surname = ms.group(1)
            constituency = ms.group(2).strip() if ms.group(2) else None
            out.append(ParsedCandidate(surname=surname, constituency=constituency))
            continue

        # Unrecognised — log and skip.
        # (Don't append; helps signal parser regressions.)

    # Flush any unclosed pending entry.
    if pending_surname is not None:
        out.append(ParsedCandidate(surname=pending_surname))
    return out


_MOTION_PREAMBLE_RE = re.compile(
    r"^\s*(?:The question being put|it was moved by|The order of the day being called)",
    re.IGNORECASE,
)


def _extract_motion_text(prior_lines: list[str]) -> str:
    """Pull the English motion preamble preceding a YEAS marker.

    Reading-order output puts EN before FR within each motion block:

        The question being put on clause 4, it was agreed to on
        the following recorded division:

        Le président du comité informe le comité que le
        ...

        YEAS / POUR — 32

    Strategy: walk backward from YEAS marker to find the most recent
    English-side preamble starter (``The question being put`` /
    ``it was moved by`` / ``The order of the day being called``).
    Capture from that line forward until we hit either a blank line
    followed by a French line, or 8 lines total — whichever first.
    """
    # Find the most-recent English preamble start.
    start = None
    for idx in range(len(prior_lines) - 1, -1, -1):
        if _MOTION_PREAMBLE_RE.match(prior_lines[idx]):
            start = idx
            break
    if start is None:
        return ""

    out: list[str] = []
    blank_seen = False
    for idx in range(start, len(prior_lines)):
        s = prior_lines[idx].strip()
        if not s:
            blank_seen = True
            continue
        # Stop when we cross into the French side after a blank.
        if blank_seen and s.startswith(("Le ", "La ", "L’", "L'", "Que ", "Qu’")):
            break
        out.append(s)
        if len(out) >= 8:
            break
    return " ".join(out)[:500].strip()


_NEXT_MOTION_RE = re.compile(
    r"^\s*(?:The question being put|La question|The question being)",
    re.IGNORECASE,
)


def parse_divisions(pdf_text: str) -> list[ParsedDivision]:
    """Walk pdftotext reading-order output, emit one ParsedDivision per
    YEAS/POUR marker. Handles:
      - Multi-page divisions (YEAS spans page boundary)
      - Multi-division pages (clause 1, 2, 3 each get a YEAS/NAYS pair)
      - Unanimous motions (YEAS only, no NAYS) — followed directly by
        the next motion's "The question being put" preamble
    """
    out: list[ParsedDivision] = []
    # Build a flat list of (page_idx, line) so we can attribute each
    # division to the page where its YEAS marker lives.
    flat: list[tuple[int, str]] = []
    for page, ptext in _page_chunks(pdf_text):
        for ln in ptext.split("\n"):
            flat.append((page, ln))

    n = len(flat)
    i = 0
    while i < n:
        m_yeas = _YEAS_MARKER_RE.match(flat[i][1])
        if not m_yeas:
            i += 1
            continue
        marker_page = flat[i][0]
        yeas_tally = int(m_yeas.group(1))
        motion = _extract_motion_text([flat[k][1] for k in range(max(0, i - 30), i)])

        # Scan forward to find division end. Terminate at:
        #   - NAYS marker → start NAYS section
        #   - next YEAS marker → previous division is unanimous
        #   - "The question being put" / "La question" → next motion
        #     (NAYS may have been absent)
        #   - end of text
        j = i + 1
        end_reason = "eof"
        while j < n:
            line = flat[j][1]
            if _NAYS_MARKER_RE.match(line):
                end_reason = "nays"
                break
            if _YEAS_MARKER_RE.match(line):
                end_reason = "next_yeas"
                break
            if _NEXT_MOTION_RE.match(line):
                end_reason = "next_motion"
                break
            j += 1

        yeas_candidates = _parse_candidate_lines(
            [flat[k][1] for k in range(i + 1, j)], expected=yeas_tally,
        )

        nays_candidates: list[ParsedCandidate] = []
        nays_tally = 0
        next_i = j
        if end_reason == "nays":
            m_nays = _NAYS_MARKER_RE.match(flat[j][1])
            nays_tally = int(m_nays.group(1)) if m_nays else 0
            # NAYS continues until next YEAS marker, next motion, or EOF.
            k = j + 1
            end = k
            while end < n:
                ln = flat[end][1]
                if _YEAS_MARKER_RE.match(ln) or _NEXT_MOTION_RE.match(ln):
                    break
                end += 1
            nays_candidates = _parse_candidate_lines(
                [flat[m][1] for m in range(k, end)], expected=nays_tally,
            )
            next_i = end

        out.append(ParsedDivision(
            page=marker_page, motion_text=motion,
            yeas_tally=yeas_tally, nays_tally=nays_tally,
            yeas=yeas_candidates, nays=nays_candidates,
        ))
        i = next_i
    return out


# ── Discovery (Stage 1) ──────────────────────────────────────────────


_PDF_LINK_RE = re.compile(
    r'href="([^"]*journal[^"]*\.pdf)"', re.IGNORECASE,
)
_LEG_HEADER_RE = re.compile(
    r"(\d{1,2})(?:st|nd|rd|th)\s+Legislature", re.IGNORECASE,
)
_SESS_HEADER_RE = re.compile(
    r"(\d{1,2})(?:st|nd|rd|th)\s+Session", re.IGNORECASE,
)


def _walk_index_lines(html: str) -> list[str]:
    """Convert the journals index HTML into a flat ordered list of
    visible lines, suitable for state-machine traversal.

    PDF hrefs are preserved as `__PDFHREF__<url>__ENDPDFHREF__` markers
    so the state machine can pair (leg, sess) headers with the
    following PDF link. The trick: replace `<a ... href="...pdf" ...>`
    with `<a> __PDFHREF__...__ENDPDFHREF__ ` so the tag-stripper
    leaves the marker behind as visible text.
    """
    # Step 1: extract anchor tags pointing at PDFs, replacing the
    # whole opening tag with a stub + visible marker text.
    text = re.sub(
        r'<a\b[^>]*href="([^"]*\.pdf)"[^>]*>',
        r'<a> __PDFHREF__\1__ENDPDFHREF__ ',
        html,
        flags=re.IGNORECASE,
    )
    # Step 2: turn block-level openings into line breaks.
    text = re.sub(r'<(p|h[1-6]|li|tr|td|div|a|br)[^>]*>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</(p|h[1-6]|li|tr|td|div|a|br)>', '\n', text, flags=re.IGNORECASE)
    # Step 3: strip remaining tags + collapse whitespace.
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'[ \t]+', ' ', text)
    return [l.strip() for l in text.split('\n') if l.strip()]


async def discover_journals(client: httpx.AsyncClient) -> list[JournalRef]:
    """Fetch the journals index and emit (leg, sess, url) for each PDF.

    Each PDF anchor's surrounding text carries its own "Nth Session
    Nth Legislature" label, so we parse (leg, sess) per-line from the
    PDF-marker line itself. When the inline label is partial, the most
    recent header from preceding lines fills in.
    """
    r = await client.get(JOURNALS_INDEX_URL, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    lines = _walk_index_lines(r.text)

    pdf_marker_re = re.compile(r'__PDFHREF__([^_]+)__ENDPDFHREF__')

    out: list[JournalRef] = []
    seen_urls: set[str] = set()
    current_leg: Optional[int] = None
    current_sess: Optional[int] = None

    for ln in lines:
        # Track section-divider headers as a fallback for PDF lines
        # that don't carry their own leg/sess label inline.
        if "__PDFHREF__" not in ln:
            m_leg = _LEG_HEADER_RE.search(ln)
            if m_leg:
                current_leg = int(m_leg.group(1))
                current_sess = None
            m_sess = _SESS_HEADER_RE.search(ln)
            if m_sess:
                current_sess = int(m_sess.group(1))
            continue

        m_pdf = pdf_marker_re.search(ln)
        if not m_pdf:
            continue
        href = m_pdf.group(1).strip()
        url = href if href.startswith("http") else f"{WEB_ROOT}{href}"
        if url in seen_urls:
            continue

        # Pull (leg, sess) from the inline label first; fall back to
        # the most-recent standalone header.
        m_leg = _LEG_HEADER_RE.search(ln)
        m_sess = _SESS_HEADER_RE.search(ln)
        leg = int(m_leg.group(1)) if m_leg else current_leg
        sess = int(m_sess.group(1)) if m_sess else current_sess
        if leg is None or sess is None:
            continue
        seen_urls.add(url)
        out.append(JournalRef(
            legislature=leg, session=sess,
            title=f"{leg}L{sess}S", url=url,
        ))
    return out


# ── DB resolution helpers ────────────────────────────────────────────


async def _load_sk_session_index(db: Database) -> dict[tuple[int, int], str]:
    """Return {(parliament, session): session_id} for SK legislative_sessions."""
    rows = await db.fetch(
        """
        SELECT id::text AS id, parliament_number AS p, session_number AS s
          FROM legislative_sessions
         WHERE level='provincial' AND province_territory='SK'
        """
    )
    return {(int(r["p"]), int(r["s"])): r["id"] for r in rows}


async def _ensure_sk_session(
    db: Database, *, legislature: int, session: int,
) -> str:
    row = await db.fetchrow(
        """
        INSERT INTO legislative_sessions (
            level, province_territory, parliament_number, session_number,
            name, source_system, source_url
        )
        VALUES ('provincial', 'SK', $1, $2, $3, $4, $5)
        ON CONFLICT (level, province_territory, parliament_number, session_number)
        DO UPDATE SET updated_at = now()
        RETURNING id::text AS id
        """,
        legislature, session,
        f"{legislature}L, {session}S",
        SOURCE_SYSTEM,
        JOURNALS_INDEX_URL,
    )
    return row["id"]


async def _load_sk_politician_index(db: Database) -> dict[str, list[dict]]:
    """Return {surname_lower: [politician_row, ...]} for SK politicians.

    Each row has: id, sk_assembly_slug, first_name, last_name,
    constituency_name (from politicians, not terms — SK term rows have
    empty constituency_id; this is a known gap for historical Journals).
    """
    rows = await db.fetch(
        """
        SELECT p.id::text AS politician_id, p.sk_assembly_slug AS slug,
               LOWER(p.last_name) AS last_lower, p.last_name AS last,
               p.first_name AS first,
               p.constituency_name AS constituency
          FROM politicians p
         WHERE p.sk_assembly_slug IS NOT NULL
        """
    )
    out: dict[str, list[dict]] = {}
    for r in rows:
        key = (r["last_lower"] or "").strip()
        if not key:
            continue
        out.setdefault(key, []).append(dict(r))
    return out


async def _load_sk_bill_index(db: Database) -> list[dict]:
    """Return SK bills as (id, bill_number, title) for motion-text FK matching."""
    rows = await db.fetch(
        """
        SELECT id::text AS id, bill_number AS number, title
          FROM bills
         WHERE level='provincial' AND province_territory='SK'
        """
    )
    return [dict(r) for r in rows]


def _find_bill_id_for(motion_text: str, bills: list[dict]) -> Optional[str]:
    """Match SK bill numbers from motion text.

    SK motions mention bills by number (e.g. ``clause 4 of Bill 50``).
    Match `Bill\\s+\\d+` against bills.number.
    """
    if not motion_text:
        return None
    m = re.search(r"\bBill\s+No\.?\s+(\d+)\b", motion_text, re.IGNORECASE)
    if not m:
        m = re.search(r"\bBill\s+(\d+)\b", motion_text, re.IGNORECASE)
    if not m:
        return None
    num = m.group(1)
    for b in bills:
        if str(b["number"]).strip() == num:
            return b["id"]
    return None


def _resolve_candidate(
    candidate: ParsedCandidate,
    pol_index: dict[str, list[dict]],
) -> Optional[str]:
    """Return politician_id for a surname (+ optional constituency)
    parsed from a Journal division, using the SK roster.

    Resolution rules (in order):
      1. Single politician with this surname → match.
      2. Multiple politicians + PDF supplied `(Constituency)` parens →
         match by case-insensitive substring on politicians.constituency_name.
      3. Multiple politicians + no parens → unresolved (NULL).
         (Better than guessing — caller leaves politician_id NULL.)

    SK politician_terms.constituency_id is empty across the corpus, so
    historical-sitting disambiguation isn't possible from terms data
    alone. This is fine for the current session (politicians.constituency_name
    is current) and a known gap for historical Journals — fix would be
    a politician_terms.constituency backfill from historical rosters.
    """
    surname_lower = candidate.surname.lower()
    candidates = pol_index.get(surname_lower) or []
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]["politician_id"]
    if candidate.constituency:
        wanted = candidate.constituency.lower()
        for c in candidates:
            cc = (c.get("constituency") or "").lower()
            if cc and wanted in cc:
                return c["politician_id"]
    return None


# ── DB upsert ───────────────────────────────────────────────────────


async def _upsert_vote(
    db: Database, *,
    session_id: str,
    division: ParsedDivision,
    bill_id: Optional[str],
    pdf_url: str,
    sitting_date: Optional[date],
    stats: IngestStats,
) -> tuple[str, str]:
    """Upsert a SK votes row keyed on the PDF page anchor."""
    canonical_url = f"{pdf_url}#page={division.page}"
    occurred_at = (
        datetime.combine(sitting_date, time(12, 0), tzinfo=timezone.utc)
        if sitting_date else None
    )
    result = "passed" if division.yeas_tally > division.nays_tally else "defeated"
    raw_payload = {
        "sk_journal": {
            "page": division.page,
            "pdf_url": pdf_url,
            "yeas_tally": division.yeas_tally,
            "nays_tally": division.nays_tally,
            "yeas_surnames": [c.surname for c in division.yeas],
            "nays_surnames": [c.surname for c in division.nays],
        }
    }
    row = await db.fetchrow(
        """
        INSERT INTO votes (
            session_id, level, province_territory,
            bill_id, speech_id,
            vote_type, occurred_at, result,
            ayes, nays, abstentions, motion_text,
            source_system, source_url, raw
        ) VALUES (
            $1::uuid, 'provincial', 'SK',
            $2, NULL,
            'division', $3, $4,
            $5, $6, NULL, $7,
            $8, $9, $10::jsonb
        )
        ON CONFLICT (source_system, source_url)
        DO UPDATE SET
            bill_id     = EXCLUDED.bill_id,
            occurred_at = EXCLUDED.occurred_at,
            result      = EXCLUDED.result,
            ayes        = EXCLUDED.ayes,
            nays        = EXCLUDED.nays,
            motion_text = EXCLUDED.motion_text,
            raw         = EXCLUDED.raw,
            updated_at  = now()
        RETURNING id::text AS id, (xmax = 0) AS inserted
        """,
        session_id, bill_id, occurred_at, result,
        division.yeas_tally, division.nays_tally,
        division.motion_text or None,
        SOURCE_SYSTEM, canonical_url,
        orjson.dumps(raw_payload).decode("utf-8"),
    )
    if row["inserted"]:
        stats.votes_inserted += 1
    else:
        stats.votes_updated += 1
    if bill_id:
        stats.bill_links += 1
    return row["id"], "inserted" if row["inserted"] else "updated"


async def _upsert_position(
    db: Database, *,
    vote_id: str,
    politician_id: Optional[str],
    name_raw: str,
    position: str,
    stats: IngestStats,
) -> None:
    row = await db.fetchrow(
        """
        INSERT INTO vote_positions (
            vote_id, politician_id, politician_name_raw,
            party_at_time, constituency_at_time, position
        ) VALUES (
            $1::uuid, $2, $3, NULL, NULL, $4
        )
        ON CONFLICT (vote_id, politician_name_raw)
        DO UPDATE SET
            politician_id = EXCLUDED.politician_id,
            position = EXCLUDED.position
        RETURNING (xmax = 0) AS inserted
        """,
        vote_id, politician_id, name_raw, position,
    )
    if row["inserted"]:
        stats.positions_inserted += 1
    else:
        stats.positions_updated += 1
    if politician_id:
        stats.politician_links += 1
    else:
        stats.politicians_unresolved += 1


# ── Public entry points ──────────────────────────────────────────────


async def _process_pdf(
    db: Database, *, journal: JournalRef, pdf_bytes: bytes,
    pol_index: dict[str, list[dict]], bills: list[dict],
    stats: IngestStats,
) -> None:
    """Parse one Journal PDF and persist its divisions."""
    text = _pdftotext(pdf_bytes, layout=False)
    divisions = parse_divisions(text)
    if not divisions:
        log.info("sk_votes: %s — no divisions found", journal.title)
        return
    session_id = await _ensure_sk_session(
        db, legislature=journal.legislature, session=journal.session,
    )
    stats.pages_scanned += text.count("\f") + 1
    stats.divisions_seen += len(divisions)
    for div in divisions:
        # SK Journal pages don't carry per-division dates inline in a
        # reliable way; the bill_id provides downstream date context.
        # Fall back to None (occurred_at NULL) — better than wrong.
        bill_id = _find_bill_id_for(div.motion_text, bills)
        vote_id, _ = await _upsert_vote(
            db, session_id=session_id, division=div, bill_id=bill_id,
            pdf_url=journal.url, sitting_date=None, stats=stats,
        )
        for cand in div.yeas:
            name_raw = (
                f"{cand.surname} ({cand.constituency})"
                if cand.constituency else cand.surname
            )
            pol_id = _resolve_candidate(cand, pol_index)
            await _upsert_position(
                db, vote_id=vote_id, politician_id=pol_id,
                name_raw=name_raw, position="yea", stats=stats,
            )
        for cand in div.nays:
            name_raw = (
                f"{cand.surname} ({cand.constituency})"
                if cand.constituency else cand.surname
            )
            pol_id = _resolve_candidate(cand, pol_index)
            await _upsert_position(
                db, vote_id=vote_id, politician_id=pol_id,
                name_raw=name_raw, position="nay", stats=stats,
            )


async def extract_sk_votes(
    db: Database, *,
    journal_url: Optional[str] = None,
    all_journals: bool = False,
    current_only: bool = True,
    limit_journals: Optional[int] = None,
    delay: float = 1.0,
) -> IngestStats:
    """Extract SK votes from Journals PDFs.

    Mode precedence:
      1. ``journal_url`` set → process that single PDF (smoke test).
      2. ``all_journals=True`` → discover index, fetch every PDF.
      3. ``current_only=True`` (default) → discover index, process the
         highest (leg, sess) only — forward-incremental for daily runs.

    ``limit_journals`` caps how many to process (newest-first).
    """
    stats = IngestStats()
    pol_index = await _load_sk_politician_index(db)
    bills = await _load_sk_bill_index(db)
    log.info(
        "sk_votes: loaded %d SK surnames (%d politicians), %d SK bills",
        len(pol_index),
        sum(len({c['politician_id'] for c in v}) for v in pol_index.values()),
        len(bills),
    )

    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True) as client:
        if journal_url:
            r = await client.get(journal_url, timeout=REQUEST_TIMEOUT)
            r.raise_for_status()
            # We don't know the (leg, sess) from a single URL; default
            # to the index walk's mapping — but for smoke-test purposes
            # require operator to supply via discovery.
            journals = await discover_journals(client)
            journal = next((j for j in journals if j.url == journal_url), None)
            if journal is None:
                stats.failures.append(
                    f"smoke-test URL {journal_url} not present in index"
                )
                return stats
            stats.journals_seen += 1
            stats.journals_fetched += 1
            await _process_pdf(
                db, journal=journal, pdf_bytes=r.content,
                pol_index=pol_index, bills=bills, stats=stats,
            )
            return stats

        journals = await discover_journals(client)
        stats.journals_seen = len(journals)
        if current_only and not all_journals:
            journals.sort(key=lambda j: (j.legislature, j.session), reverse=True)
            journals = journals[:1]
        if limit_journals:
            journals = journals[: int(limit_journals)]

        for j in journals:
            try:
                r = await client.get(j.url, timeout=REQUEST_TIMEOUT)
                r.raise_for_status()
            except httpx.HTTPError as e:
                stats.failures.append(f"fetch {j.url}: {e}")
                continue
            stats.journals_fetched += 1
            await _process_pdf(
                db, journal=j, pdf_bytes=r.content,
                pol_index=pol_index, bills=bills, stats=stats,
            )
            if delay > 0:
                await asyncio.sleep(delay)

    log.info(
        "sk_votes: journals seen=%d fetched=%d divisions=%d "
        "votes inserted=%d updated=%d positions inserted=%d updated=%d "
        "bill_links=%d pol_links=%d unresolved=%d",
        stats.journals_seen, stats.journals_fetched, stats.divisions_seen,
        stats.votes_inserted, stats.votes_updated,
        stats.positions_inserted, stats.positions_updated,
        stats.bill_links, stats.politician_links, stats.politicians_unresolved,
    )
    return stats
