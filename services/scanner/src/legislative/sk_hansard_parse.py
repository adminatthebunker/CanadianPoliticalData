"""SK Hansard parser — Word-generated HTML, regex-based.

The legassembly.sk.ca Hansard pipeline serves transcripts as Microsoft
Word HTML exports at:

    https://docs.legassembly.sk.ca/legdocs/Assembly/Debates/{N}L{S}S/{YYYYMMDD}DebatesHTML.htm

The markup is messy: windows-1252 encoded, ``<p class=MsoNormal>``
paragraphs throughout, with multi-line tag-spanning text. Speaker turns
look like:

    <p class=MsoNormal ...><span ...><b ...>Speaker Goudy</b></span>
    <span ...>: — I recognize the Minister of Health.</span></p>

Section breaks are ``<h1>...</h1>`` tags carrying anchor names like
``ROUTINE PROCEEDINGS``, ``QUESTION PERIOD``, ``ORDERS OF THE DAY``.

Sitting metadata header lives in centred header paragraphs near the top:
    SECOND SESSION — THIRTIETH LEGISLATURE
    Legislative Assembly of Saskatchewan
    DEBATES AND PROCEEDINGS (HANSARD)
    N.S. Vol. 67 — No. 58A Monday, May 4, 2026, 13:30

Per-paragraph timestamps are bracketed: ``[14:00]``, ``[15:12]``.

Project convention is regex-only HTML parsing (no BeautifulSoup or lxml
dependency in requirements.txt). All NT/MB/NS hansard parsers use this
shape — see e.g. ``mb_hansard_parse.py`` and ``nt_hansard_parse.py``.

Speaker patterns we recognise:
    Speaker {Lastname}                  → presiding officer
    Deputy Speaker {Initial. Lastname}  → presiding officer
    Hon. {First} {Last}                 → cabinet minister
    {First} {Last}                      → backbench MLA
    Some Hon. Members | Hon. Members    → chorus (no FK)
    An Hon. Member                      → unknown member (no FK)
    The Speaker | Deputy Speaker        → role-only narrative (no FK)
"""
from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass
from datetime import date as Date
from html import unescape
from typing import Optional

log = logging.getLogger(__name__)

_TS_BRACKET_RE = re.compile(r"^\s*\[(\d{1,2}:\d{2})\]\s*$")
_HONORIFIC_RE = re.compile(
    r"^(?:hon\.?|honourable|premier|mr\.?|mrs\.?|ms\.?|miss|madam|dr\.?)\s+",
    re.IGNORECASE,
)
_WS_RE = re.compile(r"\s+")
_SPLIT_AFTER_NAME_RE = re.compile(r"^\s*[:—\-–]\s*[—\-–]?\s*", re.UNICODE)

# Strip Word-style XML / VML / Office namespaces and inline drawings.
_XML_BLOCK_RE = re.compile(r"<!--\[if [^\]]*\]>.*?<!\[endif\]-->", re.DOTALL | re.IGNORECASE)
_STYLE_BLOCK_RE = re.compile(r"<style\b.*?</style>", re.DOTALL | re.IGNORECASE)
_SCRIPT_BLOCK_RE = re.compile(r"<script\b.*?</script>", re.DOTALL | re.IGNORECASE)
_HEAD_BLOCK_RE = re.compile(r"<head\b.*?</head>", re.DOTALL | re.IGNORECASE)
_OFFICE_TAG_RE = re.compile(r"<o:[^>]*>|</o:[^>]*>|<v:[^>]*>|</v:[^>]*>", re.IGNORECASE)
# Generic tag stripper (after we've located the bold name + paragraph text).
_ANY_TAG_RE = re.compile(r"<[^>]+>", re.DOTALL)
# Find an entire <p>…</p> block (greedy-tolerant via non-greedy quantifier).
_PARA_RE = re.compile(r"<p\b[^>]*>(?P<body>.*?)</p>", re.DOTALL | re.IGNORECASE)
# Find <h1> / <h2> / <h3> blocks for section headers.
_HEADING_RE = re.compile(
    r"<h(?P<level>[1-3])\b[^>]*>(?P<body>.*?)</h(?P=level)>",
    re.DOTALL | re.IGNORECASE,
)
# First <b>…</b> within a paragraph body.
_BOLD_RE = re.compile(r"<b\b[^>]*>(?P<body>.*?)</b>", re.DOTALL | re.IGNORECASE)


def _norm_ws(s: Optional[str]) -> str:
    return _WS_RE.sub(" ", (s or "").strip())


def _strip_tags(html: str) -> str:
    """Strip all tags + decode entities, collapse whitespace."""
    text = _ANY_TAG_RE.sub(" ", html)
    text = unescape(text)
    return _WS_RE.sub(" ", text).strip()


def _slug_from_name(first: str, last: str) -> str:
    text = f"{first} {last}".strip()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    return re.sub(r"\s+", "-", text).strip("-")


# Speaker patterns ────────────────────────────────────────────────────

@dataclass
class SpeakerMeta:
    raw: str
    role: Optional[str]            # 'speaker' / 'deputy_speaker' / 'chair' / 'deputy_chair' /
                                   # 'minister' / 'member' / 'chorus' / 'unknown'
    candidate_slug: Optional[str]
    last_name: Optional[str]
    first_name: Optional[str]
    is_speaker_role: bool
    is_chorus: bool


def classify_speaker(raw_text: str) -> Optional[SpeakerMeta]:
    text = _norm_ws(raw_text)
    if not text:
        return None

    # Reject all-caps blocks — those are document headers like
    # "DEBATES AND PROCEEDINGS" or section labels, not speaker turns.
    # Real speaker names always have mixed case (Lastname starts upper,
    # internal letters lower).
    letters = [c for c in text if c.isalpha()]
    if letters and all(c.isupper() for c in letters):
        return None

    if re.match(r"^(some\s+)?hon\.?\s+members?\b", text, re.IGNORECASE):
        return SpeakerMeta(raw=text, role="chorus", candidate_slug=None,
                           last_name=None, first_name=None,
                           is_speaker_role=False, is_chorus=True)
    if re.match(r"^an\s+hon\.?\s+member\b", text, re.IGNORECASE):
        return SpeakerMeta(raw=text, role="unknown", candidate_slug=None,
                           last_name=None, first_name=None,
                           is_speaker_role=False, is_chorus=True)

    # Role-only labels — distinct roles for distinct people. The main
    # Speaker is attributable via SPEAKER_ROSTER; the Deputy Speaker /
    # Chair / Deputy Chair are separate (rotating-role) people who
    # need their own roster work — those rows stay unattributed for now.
    # Important: keep these branches separate so the resolver's role-
    # tuple filter (`("speaker",)` for SK) doesn't sweep deputy/chair
    # turns into the main Speaker's bucket.
    if re.match(r"^the\s+deputy\s+chair(\s+of\s+committees?)?\b", text, re.IGNORECASE):
        return SpeakerMeta(raw=text, role="deputy_chair", candidate_slug=None,
                           last_name=None, first_name=None,
                           is_speaker_role=True, is_chorus=False)
    if re.match(r"^the\s+deputy\s+speaker\b", text, re.IGNORECASE):
        return SpeakerMeta(raw=text, role="deputy_speaker", candidate_slug=None,
                           last_name=None, first_name=None,
                           is_speaker_role=True, is_chorus=False)
    if re.match(r"^(the\s+)?chair\b", text, re.IGNORECASE):
        return SpeakerMeta(raw=text, role="chair", candidate_slug=None,
                           last_name=None, first_name=None,
                           is_speaker_role=True, is_chorus=False)
    if re.match(r"^the\s+speaker\b", text, re.IGNORECASE):
        return SpeakerMeta(raw=text, role="speaker", candidate_slug=None,
                           last_name=None, first_name=None,
                           is_speaker_role=True, is_chorus=False)

    m = re.match(r"^speaker\s+([A-Z][\w'\-]+)\.?$", text, re.IGNORECASE)
    if m:
        return SpeakerMeta(raw=text, role="speaker", candidate_slug=None,
                           last_name=m.group(1).strip(), first_name=None,
                           is_speaker_role=True, is_chorus=False)

    # "Deputy Chair (of Committees) {Lastname}" — committee chair with name.
    m = re.match(
        r"^deputy\s+chair(?:\s+of\s+committees?)?\s+"
        r"(?P<init>[A-Z]\.?\s*)?(?P<last>[A-Z][\w'\-]+)\.?$",
        text, re.IGNORECASE,
    )
    if m:
        last = m.group("last").strip()
        init = m.group("init")
        first = (init.strip().rstrip(".") + ".") if init and init.strip() else None
        return SpeakerMeta(
            raw=text, role="deputy_chair", candidate_slug=None,
            last_name=last, first_name=first,
            is_speaker_role=True, is_chorus=False,
        )
    # "Chair {Initial.} {Lastname}" — committee chair with name.
    m = re.match(
        r"^chair\s+(?P<init>[A-Z]\.?\s*)?(?P<last>[A-Z][\w'\-]+)\.?$",
        text, re.IGNORECASE,
    )
    if m:
        last = m.group("last").strip()
        init = m.group("init")
        first = (init.strip().rstrip(".") + ".") if init and init.strip() else None
        return SpeakerMeta(
            raw=text, role="chair", candidate_slug=None,
            last_name=last, first_name=first,
            is_speaker_role=True, is_chorus=False,
        )

    m = re.match(
        r"^deputy\s+speaker\s+(?P<init>[A-Z])\.?\s*(?P<last>[A-Z][\w'\-]+)\.?$",
        text, re.IGNORECASE,
    )
    if m:
        return SpeakerMeta(
            raw=text, role="deputy_speaker", candidate_slug=None,
            last_name=m.group("last").strip(),
            first_name=m.group("init").upper() + ".",
            is_speaker_role=True, is_chorus=False,
        )
    m = re.match(r"^deputy\s+speaker\s+(?P<last>[A-Z][\w'\-]+)\.?$", text, re.IGNORECASE)
    if m:
        return SpeakerMeta(
            raw=text, role="deputy_speaker", candidate_slug=None,
            last_name=m.group("last").strip(), first_name=None,
            is_speaker_role=True, is_chorus=False,
        )

    m = re.match(
        r"^hon\.?\s+([A-Z][\w'\-]+(?:\s+[A-Z][\w'\-]+)?)\s+([A-Z][\w'\-]+)\.?$",
        text, re.IGNORECASE,
    )
    if m:
        first = m.group(1).strip()
        last = m.group(2).strip()
        return SpeakerMeta(raw=text, role="minister",
                           candidate_slug=_slug_from_name(first, last),
                           last_name=last, first_name=first,
                           is_speaker_role=False, is_chorus=False)

    m = re.match(r"^(premier|leader\s+of\s+the\s+opposition)\s+([A-Z][\w'\-]+)\.?$",
                 text, re.IGNORECASE)
    if m:
        return SpeakerMeta(raw=text, role="minister", candidate_slug=None,
                           last_name=m.group(2).strip(), first_name=None,
                           is_speaker_role=False, is_chorus=False)

    m = re.match(
        r"^([A-Z][\w'\-]+(?:\s+[A-Z][\w'\-]+)?)\s+([A-Z][\w'\-]+)\.?$",
        text,
    )
    if m:
        first = m.group(1).strip()
        last = m.group(2).strip()
        return SpeakerMeta(raw=text, role="member",
                           candidate_slug=_slug_from_name(first, last),
                           last_name=last, first_name=first,
                           is_speaker_role=False, is_chorus=False)

    return None


# Sitting metadata header ─────────────────────────────────────────────

_SITTING_HEADER_RE = re.compile(
    r"N\.\s*S\.?\s+Vol\.\s+(?P<vol>\d+)\s*(?:[—–\-]+|\s)\s*"
    r"No\.\s+(?P<no>\d+[A-Za-z]?)\s+"
    r"(?P<weekday>Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s+"
    r"(?P<month>January|February|March|April|May|June|July|August|September|October|November|December)\s+"
    r"(?P<day>\d{1,2}),\s+"
    r"(?P<year>\d{4})"
    r"(?:[,\s]+(?P<hour>\d{1,2}):(?P<minute>\d{2}))?",
    re.IGNORECASE,
)
_MONTH_NUMS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}


@dataclass
class SittingMeta:
    parliament: int
    session: int
    sitting_date: Date
    volume: Optional[int]
    issue: Optional[str]
    start_time: Optional[str]


def parse_sitting_header(plain_text: str, *, fallback_parliament: int,
                         fallback_session: int, fallback_date: Date) -> SittingMeta:
    m = _SITTING_HEADER_RE.search(plain_text)
    if m is None:
        return SittingMeta(
            parliament=fallback_parliament, session=fallback_session,
            sitting_date=fallback_date,
            volume=None, issue=None, start_time=None,
        )
    month = _MONTH_NUMS.get(m.group("month").lower(), fallback_date.month)
    try:
        d = Date(int(m.group("year")), month, int(m.group("day")))
    except ValueError:
        d = fallback_date
    start_time = None
    if m.group("hour") and m.group("minute"):
        start_time = f"{int(m.group('hour')):02d}:{m.group('minute')}"
    return SittingMeta(
        parliament=fallback_parliament,
        session=fallback_session,
        sitting_date=d,
        volume=int(m.group("vol")) if m.group("vol") else None,
        issue=m.group("no"),
        start_time=start_time,
    )


# Speech extraction ───────────────────────────────────────────────────

@dataclass
class ParsedSpeech:
    sequence: int
    speaker_name_raw: str
    speaker_role: Optional[str]
    last_name: Optional[str]
    first_name: Optional[str]
    candidate_slug: Optional[str]
    body_text: str
    word_count: int
    section_label: Optional[str]
    is_speaker_role: bool
    is_chorus: bool


def _scrub_html(html: str) -> str:
    """Drop noise blocks Word emits — head, style, script, conditional
    comments, office namespaces — leaving the body untouched."""
    html = _XML_BLOCK_RE.sub("", html)
    html = _STYLE_BLOCK_RE.sub("", html)
    html = _SCRIPT_BLOCK_RE.sub("", html)
    html = _HEAD_BLOCK_RE.sub("", html)
    html = _OFFICE_TAG_RE.sub("", html)
    return html


def _iter_blocks(html: str):
    """Yield (kind, body) tuples in document order.

    kind: 'h' (heading), 'p' (paragraph). body is the inner HTML.
    """
    matches = []
    for m in _PARA_RE.finditer(html):
        matches.append((m.start(), "p", m.group("body")))
    for m in _HEADING_RE.finditer(html):
        matches.append((m.start(), "h", m.group("body")))
    matches.sort(key=lambda t: t[0])
    for _, kind, body in matches:
        yield kind, body


def parse_hansard_html(html: str) -> tuple[Optional[SittingMeta], list[ParsedSpeech]]:
    """Parse a SK Hansard HTML transcript.

    Returns (sitting_metadata, list_of_speeches). Sitting parliament/session
    are NOT extracted from the body header (caller passes them via
    sitting_date through the URL); we only extract date + volume + issue
    + start_time from the body header for verification / metadata.
    """
    cleaned = _scrub_html(html)
    speeches: list[ParsedSpeech] = []
    section_label: Optional[str] = None
    current: Optional[ParsedSpeech] = None
    sequence = 0

    for kind, body in _iter_blocks(cleaned):
        if kind == "h":
            label = _strip_tags(body)
            if label and len(label) <= 120 and label.upper() == label:
                section_label = label
            continue

        # paragraph
        bold_match = _BOLD_RE.search(body)
        bold_text = _strip_tags(bold_match.group("body")) if bold_match else ""
        full_text = _strip_tags(body)
        if not full_text:
            continue
        if _TS_BRACKET_RE.match(full_text):
            continue

        speaker = classify_speaker(bold_text) if bold_text else None

        if speaker is not None:
            sequence += 1
            body_text = full_text
            if bold_text and full_text.startswith(bold_text):
                body_text = full_text[len(bold_text):]
            body_text = _SPLIT_AFTER_NAME_RE.sub("", body_text, count=1).strip()
            current = ParsedSpeech(
                sequence=sequence,
                speaker_name_raw=speaker.raw,
                speaker_role=speaker.role,
                last_name=speaker.last_name,
                first_name=speaker.first_name,
                candidate_slug=speaker.candidate_slug,
                body_text=body_text,
                word_count=len(body_text.split()),
                section_label=section_label,
                is_speaker_role=speaker.is_speaker_role,
                is_chorus=speaker.is_chorus,
            )
            speeches.append(current)
        else:
            if current is not None:
                current.body_text = (
                    current.body_text + "\n\n" + full_text
                ) if current.body_text else full_text
                current.word_count = len(current.body_text.split())

    plain = _strip_tags(cleaned)
    sitting = parse_sitting_header(
        plain,
        fallback_parliament=0, fallback_session=0,
        fallback_date=Date.today(),
    )
    return sitting, speeches
