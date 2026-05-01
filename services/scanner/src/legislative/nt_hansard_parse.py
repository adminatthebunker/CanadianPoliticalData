"""NT Hansard HTML parser.

The transcripts at https://www.ntlegislativeassembly.ca/hansard/hn{YYMMDD}
are emitted by Drupal Views with a clean, stable taxonomy. Each sitting
page is a single ``<article class="node node--type-hansard ...">`` whose
body is a sequence of Drupal-Views rows in document order:

  views-row--type-section   → <h2>{section_name}</h2>
                              e.g. "Members' Statements", "Oral Questions"
  views-row--type-topic     → <h3>{topic}</h3>
                              e.g. "Member's Statement 985-20(1): Daylight Savings Time"
  views-row--type-statement → an <article class="node node--type-member ...">
                              with <a href="/meet-members/mla/{slug}">,
                              speaker title, constituency, then a sibling
                              <div class="views-field views-field-field-body">
                              containing the speech body's <p> paragraphs.

The parser walks rows in order, maintaining ``current_section`` and
``current_topic`` so each statement carries its enclosing context. The
sitting date is parsed from the page header ("Debates of March 6, 2026 (day 90)")
and assembly/session from "20th Assembly, 1st Session".

Translation handling: inline ``[Translation] ... [Translation Ends]``
blocks mark the *English translation* of content originally spoken in a
non-English language (Indigenous or French). The English translation is
the canonical text we want to index, so we leave the markers in the body
and tag ``language='en'`` for the whole speech. A future enhancement
could split mid-speech language portions into separate fields; today's
single-row model keeps speech-as-utterance atomic.

Speaker resolution: every modern (~2018+) speaker turn carries the
``<a href="/meet-members/mla/{slug}">`` wrapper, so we can attribute by
exact slug FK at parse time. Pre-2018 transcripts have partial slug
coverage; bare-name fallback is handled by a separate post-pass
resolver (``resolve-nt-speakers``).
"""
from __future__ import annotations

import html as html_lib
import logging
import re
import unicodedata
from dataclasses import dataclass, field as dc_field
from datetime import date as _date
from typing import Optional

log = logging.getLogger(__name__)


# ── Models ──────────────────────────────────────────────────────────


@dataclass
class ParsedSpeech:
    """One speaker turn from an NT Hansard page.

    Mirrors the field set the upstream ingester writes to the `speeches`
    table. The parser is offline (no DB calls); the caller is responsible
    for FK resolution and raw upsert.
    """
    sequence: int
    speaker_name_raw: str
    speaker_role: Optional[str]      # 'Speaker', 'Deputy Speaker', etc., or None
    nt_mla_slug: Optional[str]       # from /meet-members/mla/{slug}; None if absent
    constituency: Optional[str]
    section: Optional[str]           # H2 ("Members' Statements", ...)
    topic: Optional[str]             # H3 ("Member's Statement 985-20(1): ...")
    body_html: str
    body_text: str
    word_count: int


@dataclass
class ParsedSitting:
    sitting_date: Optional[_date]
    parliament_number: Optional[int]
    session_number: Optional[int]
    day_number: Optional[int]
    speeches: list[ParsedSpeech] = dc_field(default_factory=list)
    parse_warnings: list[str] = dc_field(default_factory=list)


# ── Regex toolkit ───────────────────────────────────────────────────

# Match the page header: "Debates of March 6, 2026 (day 90)"
_DATE_RE = re.compile(
    r"Debates\s+of\s+"
    r"(?P<month>January|February|March|April|May|June|July|"
    r"August|September|October|November|December)\s+"
    r"(?P<day>\d{1,2}),\s+(?P<year>\d{4})"
    r"(?:\s*\(day\s+(?P<day_num>\d+)\))?",
    re.IGNORECASE,
)

# Match "20th Assembly, 1st Session" — assembly = parliament_number,
# session = session_number.
_ASSEMBLY_RE = re.compile(
    r"(?P<asm>\d{1,2})(?:st|nd|rd|th)\s+Assembly,\s+"
    r"(?P<sess>\d{1,2})(?:st|nd|rd|th)\s+Session",
    re.IGNORECASE,
)

# views-row containers — the sole structural anchor we need.
_ROW_BLOCK_RE = re.compile(
    r'<div class="views-row--type-(?P<kind>section|topic|statement)\b[^"]*"[^>]*>'
    r'(?P<body>.*?)'
    r'(?=<div class="views-row--type-|\Z)',
    re.DOTALL,
)

_H2_RE = re.compile(r'<h2[^>]*>(?P<text>.*?)</h2>', re.DOTALL)
_H3_RE = re.compile(r'<h3[^>]*>(?P<text>.*?)</h3>', re.DOTALL)

# Speaker article inside a statement row (members + ministers — has MLA profile).
_SPEAKER_ARTICLE_RE = re.compile(
    r'<article\b[^>]*class="[^"]*node--type-member[^"]*"[^>]*>'
    r'\s*<a\s+href="/(?P<path>meet-members/mla|former-members)/(?P<slug>[a-z0-9-]+)"',
    re.IGNORECASE,
)

# Plain-text speaker field — used for presiding-officer interjections
# (Mr. Speaker, Deputy Speaker, Chair) where there's no MLA profile in
# this view-mode. Also used in pre-2018 transcripts where speaker names
# appear as bare text without the article wrapper.
_SPEAKER_FIELD_RE = re.compile(
    r'<div class="views-field views-field-field-speaker">'
    r'\s*(?:<span class="views-label[^"]*"[^>]*>[^<]*</span>)?'
    r'\s*<span class="field-content">(?P<name>[^<]+)</span>',
    re.DOTALL,
)

# Speaker name + constituency inside a node--type-member article.
_TITLE_RE = re.compile(
    r'<span class="field field--name-title[^"]*"[^>]*>(?P<name>[^<]+)</span>',
)
_CONSTITUENCY_RE = re.compile(
    r'<div class="field field--name-field-constituency[^"]*"[^>]*>(?P<constituency>[^<]+)</div>',
)

# Body div sits as a sibling of the speaker article inside the same
# statement row. Capture all <p> paragraphs.
_BODY_DIV_RE = re.compile(
    r'<div class="views-field views-field-field-body">(?P<inner>.*?)</div>',
    re.DOTALL,
)
_PARA_RE = re.compile(r'<p[^>]*>(?P<inner>.*?)</p>', re.DOTALL)
_TAG_STRIP_RE = re.compile(r'<[^>]+>')
_WS_RE = re.compile(r'\s+')

# Roles to detect on speaker_name_raw when no slug attaches (e.g.,
# "Mr. Speaker", "Madam Chair" cases that the parser passes through).
_ROLE_RE = re.compile(
    r'\b(?:'
    r'Speaker|Deputy Speaker|Chair|Deputy Chair|Acting Chair|'
    r'Sergeant-at-Arms|Clerk|Law Clerk|Lieutenant[ -]?Governor|'
    r'Commissioner|Premier|Prime Minister|Administrator|Page'
    r')\b',
    re.IGNORECASE,
)

_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}


def _strip_html(s: str) -> str:
    """Strip HTML tags + decode entities + collapse whitespace."""
    if not s:
        return ""
    text = _TAG_STRIP_RE.sub(" ", s)
    text = html_lib.unescape(text)
    text = unicodedata.normalize("NFKC", text)
    return _WS_RE.sub(" ", text).strip()


def _detect_role(name_raw: str) -> Optional[str]:
    """If the speaker_name_raw is a presiding role rather than a personal
    name, return the canonical role string (e.g. 'Speaker', 'Deputy Speaker').
    Otherwise None."""
    if not name_raw:
        return None
    cleaned = name_raw.strip()
    # Strip leading honorific so "Mr. Speaker" → "Speaker"
    cleaned = re.sub(
        r"^(?:hon\.?|mr\.?|mrs\.?|ms\.?|miss|madam|madame|dr\.?)\s+",
        "", cleaned, flags=re.IGNORECASE,
    )
    m = _ROLE_RE.match(cleaned)
    if m and len(cleaned) <= len(m.group(0)) + 6:
        return m.group(0).title().replace("Lieutenant-Governor", "Lieutenant-Governor")
    return None


# ── Public parser ───────────────────────────────────────────────────


def parse_sitting(html_text: str) -> ParsedSitting:
    """Parse one NT Hansard sitting HTML page → ParsedSitting.

    Returns a ParsedSitting with whatever it could recover; missing
    metadata or unparseable rows go into ``parse_warnings`` rather
    than raising.
    """
    out = ParsedSitting(
        sitting_date=None, parliament_number=None,
        session_number=None, day_number=None,
    )

    # 1. Sitting date + day number.
    m = _DATE_RE.search(html_text)
    if m:
        try:
            out.sitting_date = _date(
                int(m.group("year")),
                _MONTHS[m.group("month").lower()],
                int(m.group("day")),
            )
        except (KeyError, ValueError) as exc:
            out.parse_warnings.append(f"date parse: {exc}")
        if m.group("day_num"):
            try:
                out.day_number = int(m.group("day_num"))
            except ValueError:
                pass

    # 2. Assembly + session.
    m = _ASSEMBLY_RE.search(html_text)
    if m:
        try:
            out.parliament_number = int(m.group("asm"))
            out.session_number = int(m.group("sess"))
        except ValueError:
            pass

    # 3. Walk views-rows in document order.
    current_section: Optional[str] = None
    current_topic: Optional[str] = None
    sequence = 0

    for row_m in _ROW_BLOCK_RE.finditer(html_text):
        kind = row_m.group("kind")
        body = row_m.group("body")

        if kind == "section":
            h2 = _H2_RE.search(body)
            if h2:
                current_section = _strip_html(h2.group("text"))
                current_topic = None  # new section resets topic
            continue

        if kind == "topic":
            h3 = _H3_RE.search(body)
            if h3:
                current_topic = _strip_html(h3.group("text"))
            continue

        # kind == "statement"
        # Two attribution shapes:
        # (a) MLA profile article  → <article node--type-member> + <a /meet-members/mla/{slug}>
        # (b) Presiding interjection → <div views-field-field-speaker> with plain-text name
        slug: Optional[str] = None
        constituency: Optional[str] = None
        sp_m = _SPEAKER_ARTICLE_RE.search(body)
        if sp_m:
            slug = sp_m.group("slug")
            name_m = _TITLE_RE.search(body)
            if not name_m:
                out.parse_warnings.append(
                    f"statement row #{sequence + 1}: article present but no field--name-title"
                )
                continue
            name_raw = _strip_html(name_m.group("name"))
            const_m = _CONSTITUENCY_RE.search(body)
            constituency = _strip_html(const_m.group("constituency")) if const_m else None
        else:
            field_m = _SPEAKER_FIELD_RE.search(body)
            if not field_m:
                out.parse_warnings.append(
                    f"statement row #{sequence + 1}: no speaker article AND no field--field-speaker"
                )
                continue
            name_raw = _strip_html(field_m.group("name"))

        # body
        body_m = _BODY_DIV_RE.search(body)
        if not body_m:
            out.parse_warnings.append(
                f"statement row by {name_raw!r}: no body div — skipping"
            )
            continue
        inner = body_m.group("inner")
        paragraphs = [_strip_html(p.group("inner")) for p in _PARA_RE.finditer(inner)]
        body_text = "\n\n".join(p for p in paragraphs if p)
        if not body_text:
            # Some rows hold only ceremonial markup ("Members rose to a
            # standing ovation"). Skip silently.
            continue

        sequence += 1
        out.speeches.append(ParsedSpeech(
            sequence=sequence,
            speaker_name_raw=name_raw,
            speaker_role=_detect_role(name_raw),
            nt_mla_slug=slug,
            constituency=constituency,
            section=current_section,
            topic=current_topic,
            body_html=inner.strip(),
            body_text=body_text,
            word_count=len(body_text.split()),
        ))

    return out
