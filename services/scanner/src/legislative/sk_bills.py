"""SK bills ingester from `progress-of-bills.pdf`.

The Saskatchewan Legislative Assembly publishes its session-scoped bill
roster + stage timeline as a single tabular PDF surfaced from
``/legislative-business/bills/``. URLs use opaque CMS slugs:

    https://www.legassembly.sk.ca/media/{slug}/progress-of-bills.pdf
    https://www.legassembly.sk.ca/media/{slug}/progress-of-bills-29-4.pdf

Discovery walks the bills page, extracts every progress-of-bills PDF URL,
and identifies each one's `(parliament, session)` by reading the first
page header (``Xth Legislature / Yth Session``) — filename is unreliable
since recent CMS slugs are hash-style (`obro0uvn`) without session info.

Parsing uses ``pdftotext -layout`` (column-aligned). The header line:

    No.  EN  *  Title  Member  1st Reading  Royal Rec.  Comm.  2nd Reading  Comm.  Amend Date  3rd Reading  Royal Assent  Comes Into Force On

is detected at parse-time and column character-positions are read off
it dynamically (between sessions the column widths drift slightly).
Each bill block spans one anchor row (leading bill number) plus 0-3
continuation rows (multi-line title, multi-line sponsor name, dates that
span 2 lines for narrow columns like 'Comm.' and 'Royal Assent'). We
slice each row by column, accumulate per-column text across the block,
and extract dates / committee codes / force codes per cell.

Output:
- `bills` row per bill (UPSERT on `source_id`).
- `bill_events` rows per stage with non-empty date (sweep+reinsert per
  session, source-tagged `legassembly-sk-bills`).
- `bill_sponsors` row per bill (FK-matched to `politicians` by
  lastname+firstname against SK roster; on miss, `politician_id=NULL`
  with `sponsor_name_raw` preserved).

Idempotency: re-runs UPSERT bills + sweep-reinsert events. Schedule is
21:45 UTC daily (precedes SK MLA roster + Hansard chain at 22:00–22:30).

This module mirrors `mb_billstatus.py` but with three differences:
1. Single combined ingest command (MB splits fetch / parse).
2. `pdftotext -layout` instead of `-raw` (SK columns don't wrap).
3. Bills + sponsors loaded by this command (MB has separate ingester).
"""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field as dc_field
from datetime import date as Date, datetime, timezone
from typing import Optional

import httpx
import orjson

from ..db import Database
from .pdf_utils import pdftotext

log = logging.getLogger(__name__)

SOURCE_SYSTEM = "legassembly-sk-bills"
BILLS_PAGE_URL = "https://www.legassembly.sk.ca/legislative-business/bills/"

REQUEST_TIMEOUT = 60
HEADERS = {
    "User-Agent": "CanadianPoliticalDataBot/1.0 (+https://canadianpoliticaldata.ca; admin@thebunkerops.ca)",
    "Accept": "text/html,application/pdf,*/*;q=0.8",
    "Accept-Language": "en-CA,en;q=0.9",
}


# ── Discovery ──────────────────────────────────────────────────────

# Match progress-of-bills PDF anchors on the bills page. Two name shapes:
# modern CMS slugs (`/media/obro0uvn/progress-of-bills.pdf`) and labelled
# session-tagged variants (`/media/jquc1jcw/progress-of-bills-29-4.pdf`,
# `/media/2056/29-1-progress-of-bills.pdf`).
_PROGRESS_PDF_HREF_RE = re.compile(
    r'href="(/media/[a-zA-Z0-9_-]+/(?:[a-zA-Z0-9_-]*progress[_-]?of[_-]?bills[a-zA-Z0-9_-]*)\.pdf)"',
    re.IGNORECASE,
)
# Yearly-span legacy PDFs (1998–2017) — explicitly skipped for MVP.
_YEARLY_SPAN_RE = re.compile(r"\d{4}[-_]\d{4}", re.IGNORECASE)
# Per-session header in the PDF: "30th Legislature  2nd Session" or
# "29th Legislature 1st Session". Tolerant of whitespace.
_SESSION_HEADER_RE = re.compile(
    r"(?P<parl>\d{1,3})(?:st|nd|rd|th)\s+Legislature\s+"
    r"(?P<sess>\d{1,2})(?:st|nd|rd|th)\s+Session",
    re.IGNORECASE,
)


@dataclass
class PDFRef:
    url: str
    parliament: int
    session: int
    fetched_bytes: bytes  # cached for the parse pass


async def _fetch_html(client: httpx.AsyncClient, url: str) -> Optional[str]:
    try:
        r = await client.get(url, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        return r.text
    except Exception as exc:
        log.warning("sk_bills: fetch %s failed: %s", url, exc)
        return None


async def _fetch_bytes(client: httpx.AsyncClient, url: str) -> Optional[bytes]:
    try:
        r = await client.get(url, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        if not r.content or len(r.content) < 1000:
            return None
        return r.content
    except Exception as exc:
        log.warning("sk_bills: pdf fetch %s failed: %s", url, exc)
        return None


def _identify_session(pdf_bytes: bytes) -> Optional[tuple[int, int]]:
    """Read first page text and pull `Xth Legislature Yth Session`."""
    try:
        text = pdftotext(pdf_bytes, layout=True)
    except Exception as exc:
        log.warning("sk_bills: pdftotext failed during identify: %s", exc)
        return None
    # Search only the first ~2000 chars (header is at the top).
    head = text[:4000]
    m = _SESSION_HEADER_RE.search(head)
    if m is None:
        return None
    return int(m.group("parl")), int(m.group("sess"))


async def discover_bill_pdfs(
    client: httpx.AsyncClient, *, all_sessions: bool,
) -> list[PDFRef]:
    """Walk the bills page, return one PDFRef per current+recent PDF.

    `all_sessions=False` returns only the currently-active session PDF
    (largest `(parl, sess)` discovered). `all_sessions=True` returns
    every PDF whose filename doesn't match the yearly-span legacy
    pattern.
    """
    html = await _fetch_html(client, BILLS_PAGE_URL)
    if not html:
        return []

    seen_paths: set[str] = set()
    pending: list[tuple[str, str]] = []  # (full_url, href_path)
    for m in _PROGRESS_PDF_HREF_RE.finditer(html):
        path = m.group(1)
        if path in seen_paths:
            continue
        if _YEARLY_SPAN_RE.search(path):
            continue  # 1998–2017 legacy era out of scope for MVP
        seen_paths.add(path)
        pending.append((f"https://www.legassembly.sk.ca{path}", path))
    log.info("sk_bills: discovery surfaced %d candidate PDFs", len(pending))

    refs: list[PDFRef] = []
    for full_url, _ in pending:
        pdf_bytes = await _fetch_bytes(client, full_url)
        if pdf_bytes is None:
            continue
        ident = _identify_session(pdf_bytes)
        if ident is None:
            log.info("sk_bills: skipping %s (couldn't identify parl/sess)",
                     full_url)
            continue
        parl, sess = ident
        refs.append(PDFRef(url=full_url, parliament=parl,
                            session=sess, fetched_bytes=pdf_bytes))
        await asyncio.sleep(0.3)

    if not refs:
        return refs
    if not all_sessions:
        # Keep only the largest (parl, sess) — that's the current session.
        refs.sort(key=lambda r: (r.parliament, r.session), reverse=True)
        refs = [refs[0]]
    return refs


# ── Parsing ────────────────────────────────────────────────────────

# Section banners that determine bill_type.
_SECTION_BANNERS: dict[str, str] = {
    "Government Bills": "government",
    "Private Members' Bills": "private_member",
    "Private Members Bills": "private_member",       # tolerate variant
    "Private Members’ Bills": "private_member",      # curly apostrophe
    "Private Bills": "private",
}

# Date format in cells — "Oct 28, 2025", "Mar. 4, 2026" (period or comma).
_DATE_RE = re.compile(
    r"\b(?P<mon>Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.?\s+"
    r"(?P<day>\d{1,2})[.,]\s+(?P<year>\d{4})\b",
    re.IGNORECASE,
)
_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

# Standing-committee acronyms in the Comm. cell (1st & 2nd reading
# committee referrals). E.g. "CCA", "ECO", "HUS", "IAJ", "PBC", "PAC",
# "HOS", "CF", "CW".
_COMMITTEE_ACRONYM_RE = re.compile(r"\b(?P<code>[A-Z]{2,4})\b")
# Force-code in the rightmost column. Categorical.
_FORCE_CODE_RE = re.compile(r"\b(?P<code>(?:A|OC|SD|SE)(?:[-/](?:A|OC|SD|SE))?)\b")
# Bill row anchor — line begins with whitespace + 1-3 digits + space.
_BILL_ROW_RE = re.compile(r"^\s*(?P<num>\d{1,3})\s")
# Page banner / footer noise.
_NOISE_RE = re.compile(
    r"^\s*(?:"
    r"Progress of Bills\s*$|"
    r"\d+(?:st|nd|rd|th)\s+Legislature\s+\d+(?:st|nd|rd|th)\s+Session\s*$|"
    r"Bill comes into force on:.*$|"
    r"Standing Committees \(SC\):.*$|"
    r"Page \d+ of \d+\s*$|"
    r"\* Specified Bills\s*$|"
    r"EN - Explanatory notes\s*$|"
    r"[A-Z]{1,3} - .*$|"  # legend lines (A - Assent, OC - Order ...)
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.?\s+\d{1,2},\s+\d{4}\s*$|"  # run-date footer
    r"Please visit Publications.*$"
    r")",
    re.IGNORECASE,
)


@dataclass
class ParsedBill:
    bill_number: str
    title: str
    bill_type: str  # 'government' / 'private_member' / 'private'
    sponsor_last: Optional[str]
    sponsor_first: Optional[str]
    sponsor_raw: Optional[str]
    stages: dict[str, Date] = dc_field(default_factory=dict)  # stage_canon → date
    committee_first: Optional[str] = None  # acronym (e.g. CCA) at 1st-reading committee referral
    committee_second: Optional[str] = None  # acronym at 2nd-reading committee referral
    force_code: Optional[str] = None  # categorical: "A", "OC", "A-SD", etc.


@dataclass
class ColumnLayout:
    """Character-position boundaries of each named column (start, end).

    `end` of the last column is None (line end). All bounds are
    half-open `[start, end)`.
    """
    bill_no: tuple[int, int]
    en: tuple[int, int]
    star: tuple[int, int]
    title: tuple[int, int]
    member: tuple[int, int]
    first_reading: tuple[int, int]
    royal_rec: tuple[int, int]
    committee_first: tuple[int, int]
    second_reading: tuple[int, int]
    committee_second: tuple[int, int]
    amend_date: tuple[int, int]
    third_reading: tuple[int, int]
    royal_assent: tuple[int, int]
    force_on: tuple[int, Optional[int]]


def _detect_columns(header_line: str) -> Optional[ColumnLayout]:
    """Detect column character positions from the header line.

    Header looks like (column widths drift between sessions):
        No.   EN  *   Title   Member   Reading   Rec.   Comm.   Reading   Comm.   Date   Reading   Assent   Force On

    Each column's data LEFT boundary is the header marker's start
    position minus a small per-column offset, calibrated empirically
    against 30L2S + 29L1S samples. The TITLE column is the only odd
    one — pdftotext centers "Title" at the middle of its wide column
    (data left-aligns at col 18 right after "*"; header at col ~36).

    Each column's RIGHT = the next column's LEFT, half-open.

    Returns None if required markers are missing.
    """
    h = header_line
    pos_no = h.find("No.")
    pos_en = h.find("EN")
    pos_star = h.find("*", pos_en + 2 if pos_en >= 0 else 0)
    pos_title = h.find("Title")
    pos_member = h.find("Member")
    if min(pos_no, pos_en, pos_star, pos_title, pos_member) < 0:
        return None
    pos_reading_1 = h.find("Reading", pos_member)
    pos_reading_2 = h.find("Reading", pos_reading_1 + 7) if pos_reading_1 >= 0 else -1
    pos_reading_3 = h.find("Reading", pos_reading_2 + 7) if pos_reading_2 >= 0 else -1
    if min(pos_reading_1, pos_reading_2, pos_reading_3) < 0:
        return None
    pos_rec = h.find("Rec.", pos_reading_1, pos_reading_2)
    pos_comm_1 = h.find("Comm.", pos_rec + 4 if pos_rec >= 0 else pos_reading_1,
                        pos_reading_2)
    pos_comm_2 = h.find("Comm.", pos_reading_2, pos_reading_3)
    pos_date = h.find("Date", pos_reading_2, pos_reading_3)
    pos_assent = h.find("Assent", pos_reading_3)
    pos_force = h.find("Force On", pos_assent if pos_assent >= 0 else pos_reading_3)
    if min(pos_rec, pos_comm_1, pos_comm_2, pos_date, pos_assent, pos_force) < 0:
        return None

    # Per-column offsets from header marker START to data LEFT.
    # Calibrated against 30L2S + 29L1S samples; covers the modern (28L+)
    # SK table layout. Negative offset = data starts LEFT of header word.
    L_bill_no = 0
    L_en = max(0, pos_en - 1)
    L_star = max(L_en + 1, pos_star - 1)
    L_title = pos_star + 2                         # data left-aligns at col 18; header centered far right
    L_member = pos_member - 2                      # member data sometimes 2 cols left of header (29L1S)
    L_first_reading = pos_reading_1 - 1
    L_royal_rec = pos_rec - 3                      # data starts 3 cols before "Rec." header
    L_committee_first = pos_comm_1 - 1
    L_second_reading = pos_reading_2 - 2
    L_committee_second = pos_comm_2 - 1
    L_amend_date = pos_date - 1
    L_third_reading = pos_reading_3 - 2
    L_royal_assent = pos_assent - 1
    L_force_on = pos_force - 1

    return ColumnLayout(
        bill_no=(L_bill_no, L_en),
        en=(L_en, L_star),
        star=(L_star, L_title),
        title=(L_title, L_member),
        member=(L_member, L_first_reading),
        first_reading=(L_first_reading, L_royal_rec),
        royal_rec=(L_royal_rec, L_committee_first),
        committee_first=(L_committee_first, L_second_reading),
        second_reading=(L_second_reading, L_committee_second),
        committee_second=(L_committee_second, L_amend_date),
        amend_date=(L_amend_date, L_third_reading),
        third_reading=(L_third_reading, L_royal_assent),
        royal_assent=(L_royal_assent, L_force_on),
        force_on=(L_force_on, None),
    )


def _slice(line: str, span: tuple[int, Optional[int]]) -> str:
    a, b = span
    if b is None:
        return line[a:].strip()
    return line[a:b].strip()


def _parse_date(mon: str, day: str, year: str) -> Optional[Date]:
    m = _MONTHS.get(mon[:3].lower())
    if not m:
        return None
    try:
        return Date(int(year), m, int(day))
    except ValueError:
        return None


def _extract_first_date(cell_text: str) -> Optional[Date]:
    if not cell_text:
        return None
    m = _DATE_RE.search(cell_text)
    if not m:
        return None
    return _parse_date(m.group("mon"), m.group("day"), m.group("year"))


def _split_sponsor(member_cell: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Return (last, first, raw). Member cell is `Lastname, Firstname`.

    SK PDFs occasionally bleed 1-2 chars from the adjacent date column
    into the Member cell (e.g. `Merriman, Paul D` where "D" is the
    leading char of "Dec"). SK politicians have single-word first names
    in our roster, so we trim after the first space in the firstname
    portion. The trimmed `raw` form preserves the original (with bleed)
    for inspection.
    """
    raw = re.sub(r"\s+", " ", member_cell).strip()
    if not raw or raw == ",":
        return None, None, None
    if "," not in raw:
        return None, None, raw
    last, _, first = raw.partition(",")
    last = last.strip()
    first = first.strip()
    # Trim post-firstname bleed (split on whitespace; keep first token).
    if first:
        first = first.split()[0]
    # Same defensive trim for last (rarely needed, but robust).
    if last:
        # Keep multi-token last names like "Nippi-Albright" if no spaces;
        # split-and-drop only if the leading token already looks like a
        # full surname and trailing tokens look like noise.
        last_tokens = last.split()
        last = last_tokens[0] if last_tokens else last
    # Reconstruct a normalised raw for storage / display.
    norm_raw = f"{last}, {first}" if (last and first) else (last or first or raw)
    return (last or None), (first or None), norm_raw


def _is_section_banner(line: str) -> Optional[str]:
    stripped = line.strip()
    return _SECTION_BANNERS.get(stripped)


def parse_pdf_text(text: str) -> list[ParsedBill]:
    """Walk pdftotext -layout output, emit one ParsedBill per row.

    The parser handles multi-line bill blocks: the anchor row carries
    the bill number and primary cell content; continuation rows
    (indented, no leading number) hold title wrap, sponsor wrap, and
    date wraps for narrow columns.
    """
    lines = text.splitlines()
    out: list[ParsedBill] = []
    # SK PDFs print a fresh header at the top of EVERY page, and column
    # widths drift slightly page-to-page (Member shifts col 59↔62 in
    # the same PDF). Track the most-recent page's column layout and
    # update on each header line we encounter.
    cols: Optional[ColumnLayout] = None
    bill_type = "government"  # default until first banner; persists across pages

    # Per-bill accumulator slots. Reset on each new bill anchor row.
    cur_num: Optional[str] = None
    cur_cells: dict[str, list[str]] = {}
    cur_anchor_row: Optional[str] = None  # used by sponsor-fallback regex

    def _flush():
        nonlocal cur_num, cur_cells, cur_anchor_row
        if cur_num is None or cols is None:
            cur_num = None
            cur_cells = {}
            cur_anchor_row = None
            return
        # Concatenate cell lines.
        joined = {k: " ".join(s for s in v if s).strip()
                  for k, v in cur_cells.items()}
        title = joined.get("title", "").strip()
        if not title:
            cur_num = None
            cur_cells = {}
            return

        last, first, raw = _split_sponsor(joined.get("member", ""))
        # Fallback: when the sliced Member cell looks broken (starts with
        # a lowercase letter — title overflowed into the Member column),
        # re-extract sponsor from the full anchor-row text. Skip matches
        # where `last` is a known title-suffix word (e.g. "Act,
        # Harrison" is "...Amendment Act, Harrison" — title ending,
        # sponsor follows). After dropping false-positive prefixes, the
        # rightmost remaining match is the sponsor.
        _TITLE_SUFFIX_BLOCKLIST = {
            "Act", "Acts", "Loi", "Code", "Bill",
            "Code", "Amendment", "Statutes",
        }
        if last and last[0].islower():
            row_text = cur_anchor_row or ""
            # Find every Lastname, Firstname pattern, skipping ones whose
            # `last` looks like a title-suffix word.
            candidates = []
            for m in re.finditer(
                r"\b(?P<last>[A-Z][a-zA-Z'\-]+),\s+(?P<first>[A-Z][a-zA-Z'\-]+)\b",
                row_text,
            ):
                if m.group("last") in _TITLE_SUFFIX_BLOCKLIST:
                    continue
                candidates.append(m)
            # If nothing left after blocklist, retry with overlap-aware
            # scan (sometimes "Act, Harrison" steals "Harrison" from the
            # real "Harrison, Daryl" match — re-scan starting from the
            # offending match's `first` group).
            if not candidates:
                for m in re.finditer(
                    r"\b(?P<last>[A-Z][a-zA-Z'\-]+),\s+(?P<first>[A-Z][a-zA-Z'\-]+)\b",
                    row_text,
                ):
                    if m.group("last") in _TITLE_SUFFIX_BLOCKLIST:
                        # Re-scan from the position of `first` — that's the
                        # actual sponsor lastname stolen by the consumed
                        # match.
                        sub = row_text[m.start("first"):]
                        sub_m = re.search(
                            r"\b(?P<last>[A-Z][a-zA-Z'\-]+),\s+(?P<first>[A-Z][a-zA-Z'\-]+)\b",
                            sub,
                        )
                        if sub_m and sub_m.group("last") not in _TITLE_SUFFIX_BLOCKLIST:
                            candidates.append(sub_m)
                            break
            if candidates:
                m = candidates[-1]
                last = m.group("last")
                first = m.group("first")
                raw = f"{last}, {first}"
        stages: dict[str, Date] = {}
        for canon, key in [
            ("first_reading",        "first_reading"),
            ("royal_recommendation", "royal_rec"),
            ("committee_first",      "committee_first"),
            ("second_reading",       "second_reading"),
            ("committee_second",     "committee_second"),
            ("amend_date",           "amend_date"),
            ("third_reading",        "third_reading"),
            ("royal_assent",         "royal_assent"),
        ]:
            d = _extract_first_date(joined.get(key, ""))
            if d:
                stages[canon] = d

        # Committee acronyms (e.g. CCA, ECO) live in the same Comm. cell
        # as the date. Strip out the date text and pull any 2-4-letter
        # uppercase token left over.
        def _committee_code(s: str) -> Optional[str]:
            s2 = _DATE_RE.sub("", s).strip()
            m = _COMMITTEE_ACRONYM_RE.search(s2)
            return m.group("code") if m else None

        committee_first = _committee_code(joined.get("committee_first", ""))
        committee_second = _committee_code(joined.get("committee_second", ""))

        force_text = joined.get("force_on", "")
        force_match = _FORCE_CODE_RE.search(force_text) if force_text else None
        force_code = force_match.group("code") if force_match else None

        out.append(ParsedBill(
            bill_number=cur_num,
            title=re.sub(r"\s+", " ", title).strip(),
            bill_type=bill_type,
            sponsor_last=last,
            sponsor_first=first,
            sponsor_raw=raw,
            stages=stages,
            committee_first=committee_first,
            committee_second=committee_second,
            force_code=force_code,
        ))
        cur_num = None
        cur_cells = {}
        cur_anchor_row = None

    for line in lines:
        # Banner detection (case-insensitive on stripped text).
        bt = _is_section_banner(line)
        if bt:
            _flush()
            bill_type = bt
            continue

        # Header row (one per page) — re-detect column layout. Each
        # page's pdftotext output uses slightly different column widths
        # so we update on every header encountered, not just the first.
        if "No." in line and "Title" in line and "Member" in line and "Reading" in line:
            detected = _detect_columns(line)
            if detected is not None:
                # Flush any in-progress bill before switching layouts —
                # the new page's columns won't slice the old block correctly.
                _flush()
                cols = detected
            continue

        if cols is None:
            continue

        if _NOISE_RE.match(line):
            continue
        if not line.strip():
            # Blank line — bills can span across blank lines (between
            # title wrap and committee wrap), but a fully-blank stretch
            # of >1 line typically indicates a bill boundary. We don't
            # rely on this — the next bill anchor flushes anyway.
            continue

        # Anchor row vs continuation row. Anchor: digit at start of
        # number-cell. Continuation: number-cell empty (whitespace
        # only). We slice the bill_no column to test.
        bill_no_cell = _slice(line, cols.bill_no)
        if bill_no_cell.isdigit():
            _flush()
            cur_num = bill_no_cell
            cur_cells = {}
            cur_anchor_row = line
        elif cur_num is None:
            # Stray content before first bill — skip.
            continue

        # Accumulate every column from this line.
        for col_name, span in [
            ("title",            cols.title),
            ("member",           cols.member),
            ("first_reading",    cols.first_reading),
            ("royal_rec",        cols.royal_rec),
            ("committee_first",  cols.committee_first),
            ("second_reading",   cols.second_reading),
            ("committee_second", cols.committee_second),
            ("amend_date",       cols.amend_date),
            ("third_reading",    cols.third_reading),
            ("royal_assent",     cols.royal_assent),
            ("force_on",         cols.force_on),
        ]:
            piece = _slice(line, span)
            if piece:
                cur_cells.setdefault(col_name, []).append(piece)

    _flush()
    return out


# ── DB writes ──────────────────────────────────────────────────────


@dataclass
class IngestStats:
    pdfs_seen: int = 0
    bills_parsed: int = 0       # always incremented (covers dry-run + commit modes)
    bills_inserted: int = 0
    bills_updated: int = 0
    sponsors_inserted: int = 0
    sponsor_fk_hits: int = 0
    sponsor_fk_misses: int = 0
    events_deleted: int = 0
    events_inserted: int = 0
    failures: list[str] = dc_field(default_factory=list)
    sample: list[ParsedBill] = dc_field(default_factory=list)  # first ~5 bills (dry-run aid)


async def _ensure_session(
    db: Database, *, parliament: int, session: int,
) -> str:
    name = f"{parliament}{_ord_suffix(parliament)} Legislature, {session}{_ord_suffix(session)} Session"
    row = await db.fetchrow(
        """
        INSERT INTO legislative_sessions
            (level, province_territory, parliament_number, session_number,
             name, source_system, source_url)
        VALUES ('provincial', 'SK', $1, $2, $3, $4, $5)
        ON CONFLICT (level, province_territory, parliament_number, session_number)
        DO UPDATE SET
            name          = COALESCE(legislative_sessions.name, EXCLUDED.name),
            source_system = COALESCE(legislative_sessions.source_system, EXCLUDED.source_system),
            updated_at    = now()
        RETURNING id::text AS id
        """,
        parliament, session, name, SOURCE_SYSTEM, BILLS_PAGE_URL,
    )
    return row["id"]


def _ord_suffix(n: int) -> str:
    if 10 < n % 100 < 20:
        return "th"
    return ["th", "st", "nd", "rd", "th", "th", "th", "th", "th", "th"][n % 10]


async def _resolve_sponsor(
    db: Database, *, last: Optional[str], first: Optional[str],
) -> Optional[str]:
    if not last:
        return None
    if first:
        row = await db.fetchrow(
            """
            SELECT id::text AS id FROM politicians
             WHERE province_territory='SK' AND level='provincial'
               AND lower(unaccent(last_name)) = lower(unaccent($1))
               AND lower(unaccent(first_name)) = lower(unaccent($2))
             LIMIT 1
            """,
            last, first,
        )
        if row:
            return row["id"]
    # Last-name fallback (unique only).
    rows = await db.fetch(
        """
        SELECT id::text AS id FROM politicians
         WHERE province_territory='SK' AND level='provincial'
           AND lower(unaccent(last_name)) = lower(unaccent($1))
        """,
        last,
    )
    if len(rows) == 1:
        return rows[0]["id"]
    return None


async def _upsert_bill(
    db: Database, *, session_id: str, parliament: int, session: int,
    pb: ParsedBill, pdf_url: str,
) -> tuple[str, bool]:
    """Insert or update a bills row. Returns (bill_id, inserted)."""
    source_id = f"legassembly-sk-bills:{parliament}-{session}:bill-{pb.bill_number}"
    raw = {
        "force_code": pb.force_code,
        "committee_first_acronym": pb.committee_first,
        "committee_second_acronym": pb.committee_second,
        "sponsor_raw": pb.sponsor_raw,
    }
    raw = {k: v for k, v in raw.items() if v}
    raw_json = orjson.dumps(raw).decode("utf-8")

    introduced = pb.stages.get("first_reading")
    latest_stage_label = None
    latest_stage_date = None
    for canon in (
        "royal_assent", "third_reading", "amend_date", "committee_second",
        "second_reading", "committee_first", "royal_recommendation", "first_reading",
    ):
        d = pb.stages.get(canon)
        if d:
            latest_stage_label = canon.replace("_", " ").title()
            latest_stage_date = d
            break

    row = await db.fetchrow(
        """
        INSERT INTO bills
            (session_id, level, province_territory,
             bill_number, title, bill_type,
             status, status_changed_at, introduced_date,
             source_id, source_system, source_url, raw)
        VALUES
            ($1::uuid, 'provincial', 'SK',
             $2, $3, $4,
             $5, $6, $7,
             $8, $9, $10, $11::jsonb)
        ON CONFLICT (source_id) DO UPDATE SET
            title             = EXCLUDED.title,
            bill_type         = EXCLUDED.bill_type,
            status            = COALESCE(EXCLUDED.status, bills.status),
            status_changed_at = COALESCE(EXCLUDED.status_changed_at, bills.status_changed_at),
            introduced_date   = COALESCE(EXCLUDED.introduced_date, bills.introduced_date),
            source_url        = EXCLUDED.source_url,
            raw               = bills.raw || EXCLUDED.raw,
            last_fetched_at   = now(),
            updated_at        = now()
        RETURNING id::text AS id, (xmax = 0) AS inserted
        """,
        session_id, pb.bill_number, pb.title, pb.bill_type,
        latest_stage_label,
        datetime.combine(latest_stage_date, datetime.min.time(), tzinfo=timezone.utc) if latest_stage_date else None,
        introduced,
        source_id, SOURCE_SYSTEM, pdf_url, raw_json,
    )
    return row["id"], bool(row["inserted"])


async def _replace_events(
    db: Database, *, bill_id: str, pb: ParsedBill, source_url: str,
) -> int:
    """Delete + reinsert this source's events for one bill. Returns insert count."""
    await db.execute(
        """
        DELETE FROM bill_events
         WHERE bill_id = $1::uuid
           AND raw->>'source' = $2
        """,
        bill_id, SOURCE_SYSTEM,
    )
    inserted = 0
    stage_committee_map = {
        "committee_first":  pb.committee_first,
        "committee_second": pb.committee_second,
    }
    for canon, d in pb.stages.items():
        committee = stage_committee_map.get(canon)
        await db.execute(
            """
            INSERT INTO bill_events
                (bill_id, stage, stage_label, event_date,
                 event_type, committee_name, source_url, raw)
            VALUES ($1::uuid, $2, $3, $4, NULL, $5, $6, $7::jsonb)
            ON CONFLICT ON CONSTRAINT bill_events_uniq DO NOTHING
            """,
            bill_id, canon, canon.replace("_", " ").title(), d,
            committee, source_url,
            orjson.dumps({"source": SOURCE_SYSTEM}).decode(),
        )
        inserted += 1
    return inserted


async def _replace_sponsor(
    db: Database, *, bill_id: str, pb: ParsedBill,
    politician_id: Optional[str],
) -> None:
    """Sweep+reinsert the single sponsor row for this source."""
    await db.execute(
        """
        DELETE FROM bill_sponsors
         WHERE bill_id = $1::uuid AND source_system = $2
        """,
        bill_id, SOURCE_SYSTEM,
    )
    if not pb.sponsor_raw:
        return
    await db.execute(
        """
        INSERT INTO bill_sponsors
            (bill_id, politician_id, sponsor_name_raw,
             role, ordering, source_system)
        VALUES ($1::uuid, $2, $3, 'sponsor', 0, $4)
        """,
        bill_id, politician_id, pb.sponsor_raw, SOURCE_SYSTEM,
    )


async def _ingest_one_pdf(
    db: Database, ref: PDFRef, stats: IngestStats,
    *, dry_run: bool,
) -> list[ParsedBill]:
    """Parse one PDF and (unless dry_run) write to DB. Return parsed list."""
    try:
        text = pdftotext(ref.fetched_bytes, layout=True)
    except Exception as exc:
        stats.failures.append(f"pdftotext failed for {ref.url}: {exc}")
        return []

    bills = parse_pdf_text(text)
    if not bills:
        stats.failures.append(f"no bills parsed from {ref.url}")
        return bills

    log.info("sk_bills: parsed %d bills from %dL%dS (%s)",
             len(bills), ref.parliament, ref.session, ref.url)
    stats.bills_parsed += len(bills)
    # Capture the first 5 parsed bills for dry-run inspection.
    if len(stats.sample) < 5:
        stats.sample.extend(bills[: 5 - len(stats.sample)])

    if dry_run:
        return bills

    session_id = await _ensure_session(
        db, parliament=ref.parliament, session=ref.session,
    )
    for pb in bills:
        bill_id, inserted = await _upsert_bill(
            db, session_id=session_id,
            parliament=ref.parliament, session=ref.session,
            pb=pb, pdf_url=ref.url,
        )
        if inserted:
            stats.bills_inserted += 1
        else:
            stats.bills_updated += 1

        events_added = await _replace_events(
            db, bill_id=bill_id, pb=pb, source_url=ref.url,
        )
        stats.events_inserted += events_added

        pol_id = await _resolve_sponsor(
            db, last=pb.sponsor_last, first=pb.sponsor_first,
        )
        if pb.sponsor_raw:
            stats.sponsors_inserted += 1
            if pol_id:
                stats.sponsor_fk_hits += 1
            else:
                stats.sponsor_fk_misses += 1
        await _replace_sponsor(
            db, bill_id=bill_id, pb=pb, politician_id=pol_id,
        )
    return bills


# ── Public entry point ─────────────────────────────────────────────


async def ingest_sk_bills(
    db: Database, *,
    all_sessions: bool = False,
    url: Optional[str] = None,
    delay: float = 1.0,
    dry_run: bool = False,
) -> IngestStats:
    stats = IngestStats()

    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True) as client:
        if url:
            pdf_bytes = await _fetch_bytes(client, url)
            if pdf_bytes is None:
                stats.failures.append(f"failed to fetch single URL: {url}")
                return stats
            ident = _identify_session(pdf_bytes)
            if ident is None:
                stats.failures.append(f"couldn't identify parl/sess for {url}")
                return stats
            parl, sess = ident
            refs = [PDFRef(url=url, parliament=parl, session=sess,
                           fetched_bytes=pdf_bytes)]
        else:
            refs = await discover_bill_pdfs(client, all_sessions=all_sessions)
        stats.pdfs_seen = len(refs)

        for ref in refs:
            await _ingest_one_pdf(db, ref, stats, dry_run=dry_run)
            await asyncio.sleep(delay)

    log.info(
        "sk_bills: pdfs=%d bills_inserted=%d bills_updated=%d "
        "sponsors=%d fk_hits=%d fk_misses=%d events_inserted=%d failures=%d",
        stats.pdfs_seen, stats.bills_inserted, stats.bills_updated,
        stats.sponsors_inserted, stats.sponsor_fk_hits, stats.sponsor_fk_misses,
        stats.events_inserted, len(stats.failures),
    )
    return stats


# ── Selftest ──────────────────────────────────────────────────────

# Hand-curated golden cases from the 30L2S progress-of-bills.pdf
# captured 2026-05-05. Each tuple is:
#   (bill_number, expected_title_substring, expected_sponsor_last,
#    expected_first_reading, expected_third_reading, expected_force_code)
_GOLDEN_CASES: list[tuple[str, str, str, Date, Optional[Date], Optional[str]]] = [
    ("24", "Saskatchewan Internal Trade", "Kaeding",
     Date(2025, 10, 28), Date(2026, 4, 23), "A"),
    ("25", "Income Tax (Miscellaneous)", "Reiter",
     Date(2025, 10, 28), Date(2025, 11, 25), "A-SD"),
    ("27", "Statute Law Amendment Act", "McLeod",
     Date(2025, 10, 29), Date(2025, 11, 27), "A"),
    ("28", "Public Libraries Amendment Act", "Hindley",
     Date(2025, 10, 30), Date(2025, 11, 27), "OC"),
    ("31", "Defamation Act", "McLeod",
     Date(2025, 11, 4), Date(2026, 4, 14), "OC"),
]


async def run_selftest() -> int:
    """Fetch the current PDF + parse + assert golden cases. Returns
    exit code (0 = pass)."""
    failures: list[str] = []
    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True) as client:
        refs = await discover_bill_pdfs(client, all_sessions=False)
    if not refs:
        print("selftest: discovery yielded zero PDFs", flush=True)
        return 1
    ref = refs[0]
    text = pdftotext(ref.fetched_bytes, layout=True)
    bills = parse_pdf_text(text)
    by_num = {b.bill_number: b for b in bills}
    print(f"selftest: parsed {len(bills)} bills from {ref.parliament}L{ref.session}S",
          flush=True)
    for (num, title_sub, last, first_r, third_r, force) in _GOLDEN_CASES:
        b = by_num.get(num)
        if b is None:
            failures.append(f"bill {num}: not found in parsed output")
            continue
        if title_sub.lower() not in b.title.lower():
            failures.append(f"bill {num}: title mismatch — got {b.title!r}, expected substring {title_sub!r}")
        if (b.sponsor_last or "").lower() != last.lower():
            failures.append(f"bill {num}: sponsor mismatch — got {b.sponsor_last!r}, expected {last!r}")
        if b.stages.get("first_reading") != first_r:
            failures.append(f"bill {num}: first_reading mismatch — got {b.stages.get('first_reading')!r}, expected {first_r}")
        if third_r and b.stages.get("third_reading") != third_r:
            failures.append(f"bill {num}: third_reading mismatch — got {b.stages.get('third_reading')!r}, expected {third_r}")
        if force and b.force_code != force:
            failures.append(f"bill {num}: force_code mismatch — got {b.force_code!r}, expected {force!r}")
    if failures:
        print(f"selftest: {len(failures)} failure(s):", flush=True)
        for f in failures:
            print(f"  - {f}", flush=True)
        return 1
    print("selftest: all golden cases pass", flush=True)
    return 0
