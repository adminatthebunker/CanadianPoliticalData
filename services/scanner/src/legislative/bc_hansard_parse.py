"""BC Hansard HTML parser — Blues + Final HDMS, single code path.

Both variants come from `lims.leg.bc.ca/hdms/file/Debates/{parl}{sess}/...`:

  Blues:  .../{YYYYMMDD}{am|pm}-House-Blues.htm
  Final:  .../{YYYYMMDD}{am|pm}-Hansard-n{NNN}.html

They share semantic class names but hyphenate differently (Final: `Speaker-Name`,
Blues: `SpeakerName`). We normalise class names (strip hyphens, lowercase) so
one dispatcher handles both.

## Class taxonomy (normalised form)

  speakerbegins        — first paragraph of a speaker turn; contains name span
  speakercontinues     — subsequent paragraph in same turn
  speakercontinuesmidspeech / chairchangemidspeech — mid-turn procedural notes
  speakername          — span inside speakerbegins wrapping the name
  bold                 — span wrapping the ":" after the name
  timeline             — sitting open/adjourn marker ("The House met at 1:33 p.m.")
  timestamp            — intra-sitting clock marker ("[1:35 p.m.]"); carries id= in Final
  proceedings / proceedingsheading
                       — top-level section ("Routine Business")
  businessheading      — mid-level section ("Oral Questions", "Members' Statements")
  subjectheading       — per-topic heading under a business section
  editorialcomment     — bracketed procedural inserts
  styleline            — motion/leave/adjournment one-liners (not speeches)

## Output

Yields `ParsedSpeech` — one per speaker turn (SpeakerBegins + its Continues).
Non-speech paragraphs (headings, style lines, editorial comments) influence
the enclosing turn's metadata but are not emitted as rows themselves.

This module is pure-offline: no network, no DB. Caller supplies the raw HTML.
"""
from __future__ import annotations

import hashlib
import html
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone
from typing import Iterator, Optional
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)

VANCOUVER_TZ = ZoneInfo("America/Vancouver")


# ── Filename parsing ────────────────────────────────────────────────
# Modern URL patterns (P38-S4 onward):
#   {YYYYMMDD}{am|pm}-House-Blues.htm            — Blues draft (P40-S4+)
#   {YYYYMMDD}{am|pm}-Hansard-n{NNN}.html        — Final, 43rd-Parl-era
#   {YYYYMMDD}{am|pm}-Hansard-v{VOL}n{NNN}.htm   — Final, pre-43rd-Parl
#
# Legacy URL pattern (P29 1970 — P37 2005):
#   {NN}p_{NN}s_{YYMMDD}{x}.htm    where x ∈ {a, m, p, n, z}
#                                  a/m=morning, p=afternoon,
#                                  n=evening, z=night/special
_URL_FILENAME_RE = re.compile(
    r"/(?P<date>\d{8})(?P<half>am|pm)-"
    r"(?P<kind>House-Blues"
    r"|Hansard-n(?P<issue_new>\d+)"
    r"|Hansard-v(?P<volume>\d+)n(?P<issue_old>\d+)"
    r")\.html?$",
    re.IGNORECASE,
)
_URL_LEGACY_FILENAME_RE = re.compile(
    r"/(?P<parl>\d{1,2})p_(?P<sess>\d{1,2})s_"
    r"(?P<yymmdd>\d{6})(?P<half_letter>[a-z])\.htm$",
    re.IGNORECASE,
)
_LEGACY_HALF_LETTER_TO_TOKEN: dict[str, str] = {
    "a": "am",   # morning
    "m": "am",   # morning (alternate)
    "p": "pm",   # afternoon
    "n": "pm",   # evening — bucket as pm for sort purposes
    "z": "pm",   # night/special — bucket as pm
}


@dataclass
class UrlMeta:
    sitting_date: date
    half: str  # 'am' | 'pm'
    variant: str  # 'blues' | 'final' | 'legacy'
    issue: Optional[int] = None
    volume: Optional[int] = None

    @property
    def default_hhmm(self) -> time:
        """Fallback start time when the transcript lacks a Time-Line."""
        return time(10, 0) if self.half == "am" else time(13, 30)


def parse_url_meta(url: str) -> UrlMeta:
    m = _URL_FILENAME_RE.search(url)
    if m:
        d = datetime.strptime(m.group("date"), "%Y%m%d").date()
        kind_lower = m.group("kind").lower()
        variant = "blues" if kind_lower == "house-blues" else "final"
        issue = m.group("issue_new") or m.group("issue_old")
        volume = m.group("volume")
        return UrlMeta(
            sitting_date=d,
            half=m.group("half").lower(),
            variant=variant,
            issue=int(issue) if issue else None,
            volume=int(volume) if volume else None,
        )
    m = _URL_LEGACY_FILENAME_RE.search(url)
    if m:
        # Legacy: 2-digit year, century inferred from parliament era.
        # Per LIMS HDMS coverage: P29 (1970-1972) is the floor, no
        # century ambiguity through P37 (2005). Anything from
        # YY in [70..99] is 19YY, [00..05] is 20YY.
        yymmdd = m.group("yymmdd")
        yy = int(yymmdd[:2])
        century = 1900 if yy >= 70 else 2000
        try:
            d = datetime.strptime(
                f"{century + yy:04d}{yymmdd[2:]}", "%Y%m%d",
            ).date()
        except ValueError as exc:
            raise ValueError(f"bad legacy date in filename: {url}") from exc
        half = _LEGACY_HALF_LETTER_TO_TOKEN.get(
            m.group("half_letter").lower(), "pm",
        )
        return UrlMeta(
            sitting_date=d,
            half=half,
            variant="legacy",
            issue=None,
            volume=None,
        )
    raise ValueError(f"not a recognized BC Hansard filename: {url}")


# ── Class-name normalisation ────────────────────────────────────────
# Turn "Speaker-Name" / "SpeakerName" / "speaker name" (P42 multi-class
# attribute) all into "speakername" for dispatch. Strips hyphens,
# underscores, and whitespace so multi-class CSS attributes collapse
# into a single canonical token.
def _norm_cls(raw: str) -> str:
    return raw.replace("-", "").replace("_", "").replace(" ", "").lower()


# ── Paragraph iterator ──────────────────────────────────────────────
# Every content-bearing <p class="..."> in body order. We keep id= when
# present (Final uses it as anchor for time stamps and headings).
_P_TAG_RE = re.compile(
    r'<p\s+class="(?P<cls>[^"]+)"(?P<attrs>[^>]*)>(?P<body>.*?)</p>',
    re.DOTALL | re.IGNORECASE,
)
_ID_ATTR_RE = re.compile(r'\sid="(?P<id>[^"]+)"')


@dataclass
class _Para:
    raw_cls: str
    norm_cls: str
    body_html: str
    anchor: Optional[str]


def _iter_paragraphs(html_text: str) -> Iterator[_Para]:
    for m in _P_TAG_RE.finditer(html_text):
        cls = m.group("cls").strip()
        attrs = m.group("attrs") or ""
        id_match = _ID_ATTR_RE.search(attrs)
        yield _Para(
            raw_cls=cls,
            norm_cls=_norm_cls(cls),
            body_html=m.group("body"),
            anchor=id_match.group("id") if id_match else None,
        )


# ── HTML → text ──────────────────────────────────────────────────────
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _strip_tags(html_text: str) -> str:
    """Collapse whitespace, unescape entities, drop inline tags."""
    without = _TAG_RE.sub("", html_text)
    unescaped = html.unescape(without)
    return _WS_RE.sub(" ", unescaped).strip()


# ── Time stamp parsing ──────────────────────────────────────────────
# Both variants use "[1:35 p.m.]" / "[10:03 a.m.]" inside the <p>. Final
# also emits an id like "118B:1335" on the <p> tag — easier to parse the
# id when present.
_TS_ID_RE = re.compile(r"(?P<hhmm>\d{4})")
_TS_TEXT_RE = re.compile(
    r"\[(?P<h>\d{1,2}):(?P<m>\d{2})\s*(?P<ampm>[ap])\.?m\.?\]",
    re.IGNORECASE,
)


def _parse_time_stamp(anchor: Optional[str], body_text: str) -> Optional[time]:
    if anchor:
        # Anchor forms in Final: "118B:1335", "NNN:HHMM"
        tail = anchor.split(":")[-1]
        if len(tail) == 4 and tail.isdigit():
            return time(int(tail[:2]), int(tail[2:]))
    m = _TS_TEXT_RE.search(body_text)
    if m:
        h = int(m.group("h"))
        mins = int(m.group("m"))
        if m.group("ampm").lower() == "p" and h < 12:
            h += 12
        elif m.group("ampm").lower() == "a" and h == 12:
            h = 0
        return time(h, mins)
    return None


# "The House met at 1:33 p.m."  /  "The House adjourned at 6:51 p.m."
_TIME_LINE_RE = re.compile(
    r"(?P<h>\d{1,2}):(?P<m>\d{2})\s*(?P<ampm>[ap])\.?m\.?",
    re.IGNORECASE,
)


# ── Speaker-name extraction ─────────────────────────────────────────
# Both variants wrap the name in <span class="SpeakerName">/<span class="Speaker-Name">
# and the trailing colon in <span class="Bold">:</span>. In Blues the honorific
# can be in a separate span from the name.
_SPAN_RE = re.compile(
    r'<span\s+class="(?P<cls>[^"]+)"[^>]*>(?P<body>.*?)</span>',
    re.DOTALL | re.IGNORECASE,
)


def _extract_speaker(body_html: str) -> tuple[str, str]:
    """Return (speaker_name_raw, body_text).

    speaker_name_raw is the concatenation of SpeakerName span(s), including
    any honorific (Hon., Mr., etc.). body_text is what follows the Bold
    colon, or the full paragraph minus name spans if no colon is found.
    """
    name_parts: list[str] = []
    seen_colon = False
    tail_start = 0
    for m in _SPAN_RE.finditer(body_html):
        norm = _norm_cls(m.group("cls"))
        text = _strip_tags(m.group("body"))
        # `speakername` — modern P43 markup
        # `attribution` — pre-P43 markup (attribution span includes the
        #   trailing colon in the same span, e.g. "M. Karagianis:")
        if not seen_colon and norm in ("speakername", "attribution"):
            # Occasional Final markup tags the colon with Speaker-Name too
            # (e.g. Deputy Speaker). Treat a colon-only span as end-of-name.
            if text.strip() == ":":
                seen_colon = True
                tail_start = m.end()
            else:
                name_parts.append(text)
                tail_start = m.end()
                # `attribution` span bundles "Name:" in one span — if it
                # ends with a colon, mark the colon as seen so trailing
                # paragraphs aren't re-classified.
                if norm == "attribution" and text.rstrip().endswith(":"):
                    seen_colon = True
        elif not seen_colon and norm == "bold":
            if text.strip() == ":":
                seen_colon = True
                tail_start = m.end()
    name = " ".join(p for p in name_parts if p).strip()
    # Collapse "Hon. " + "Ravi Parmar" → "Hon. Ravi Parmar"
    name = _WS_RE.sub(" ", name)
    # Edge case: Final/Blues occasionally bundle "The Chair: " (name + colon
    # + trailing space) into a single SpeakerName span with no sibling Bold
    # span. Strip any trailing colon + whitespace.
    name = re.sub(r"\s*:\s*$", "", name).strip()
    body_text = _strip_tags(body_html[tail_start:]) if tail_start else _strip_tags(body_html)
    return name, body_text


# ── Section → speech_type mapping ───────────────────────────────────
# Applied from the most recent BusinessHeading (or ProceedingsHeading
# fallback). Unknown sections default to 'floor' with the raw heading
# preserved in raw.procedural_section for future remapping.
SECTION_TO_TYPE = {
    "oral questions": "question_period",
    "members' statements": "statement",
    "members statements": "statement",
    "statements by members": "statement",
    "ministerial statements": "statement",
    "tributes": "statement",
    "introductions by members": "statement",
    "petitions": "statement",
    "introduction and first reading of bills": "floor",
    "second reading of bills": "floor",
    "third reading of bills": "floor",
    "committee of the whole": "committee",
    "committee of the whole house": "committee",
    "committee of supply": "committee",
    "report and third reading of bills": "floor",
    "royal assent": "floor",
    "orders of the day": "floor",
    "routine business": "floor",
    "point of order": "point_of_order",
    "point of privilege": "point_of_order",
}


def _map_speech_type(section: Optional[str]) -> str:
    if not section:
        return "floor"
    return SECTION_TO_TYPE.get(section.strip().lower(), "floor")


# ── Sitting Speaker extraction ──────────────────────────────────────
# Both variants name the presiding Speaker in the HTML head:
#   Blues:  <h2 class="speaker">The Honourable Raj Chouhan, Speaker</h2>
#   Final:  <p class="Speaker">The Honourable <span class="Speaker">Raj
#                                                 Chouhan</span>, Speaker</p>
# Extract just the name ("Raj Chouhan") so the ingester can resolve
# "The Speaker" attributions to the actual politician.
# P43 Blues uses <h2 class="speaker">; P42 uses <h3 class="heading-right
# speaker"> (multi-class). Match either tag and require "speaker" among
# the class tokens.
_SITTING_SPEAKER_RE_BLUES = re.compile(
    r'<h[23][^>]+class="[^"]*\bspeaker\b[^"]*"[^>]*>(?P<body>.*?)</h[23]>',
    re.DOTALL | re.IGNORECASE,
)
_SITTING_SPEAKER_RE_FINAL = re.compile(
    r'<p[^>]+class="Speaker"[^>]*>(?P<body>[^<]*(?:<span[^>]*>[^<]*</span>[^<]*)*)</p>',
    re.DOTALL | re.IGNORECASE,
)
_HONOURABLE_RE = re.compile(r"^(?:the\s+)?(?:hon(?:ourable|\.?)\s+)+", re.IGNORECASE)
_SPEAKER_SUFFIX_RE = re.compile(r",\s*(?:the\s+)?speaker\s*$", re.IGNORECASE)


def extract_sitting_speaker(html_text: str) -> Optional[str]:
    """Pull the presiding Speaker's name out of the sitting's HTML header.

    Returns the clean name ("Raj Chouhan") with "The Honourable" prefix
    and ", Speaker" suffix stripped. Returns None if no match.
    """
    for regex in (_SITTING_SPEAKER_RE_BLUES, _SITTING_SPEAKER_RE_FINAL):
        m = regex.search(html_text)
        if not m:
            continue
        text = _strip_tags(m.group("body"))
        text = _SPEAKER_SUFFIX_RE.sub("", text)
        text = _HONOURABLE_RE.sub("", text).strip()
        if text:
            return text
    return None


# ── Role / honorific detection ──────────────────────────────────────
# Presiding officers: role-only attribution. These never carry a
# politician_id from name-match alone; they need term-role lookup.
_PRESIDING_ROLES = {
    "the speaker",
    "deputy speaker",
    "assistant deputy speaker",
    "the chair",
    "deputy chair",
    "the deputy chair",
    "the acting chair",
    "assistant deputy chair",
}

# Parenthetical role: "Hon. David Eby (Premier)" → name, role
_PAREN_ROLE_RE = re.compile(r"^(?P<name>[^(]+?)\s*\((?P<role>[^)]+)\)\s*$")


def _split_role(speaker_name_raw: str) -> tuple[str, Optional[str]]:
    stripped = speaker_name_raw.strip()
    low = stripped.lower()
    if low in _PRESIDING_ROLES:
        return stripped, stripped  # role == name in this case
    m = _PAREN_ROLE_RE.match(stripped)
    if m:
        return m.group("name").strip(), m.group("role").strip()
    return stripped, None


# ── Output dataclass ────────────────────────────────────────────────
@dataclass
class ParsedSpeech:
    sequence: int
    speaker_name_raw: str
    speaker_role: Optional[str]
    speech_type: str
    spoken_at: datetime  # UTC
    text: str
    language: str
    source_anchor: Optional[str]
    content_hash: str
    raw: dict = field(default_factory=dict)

    @property
    def word_count(self) -> int:
        return len(self.text.split())


def _content_hash(text: str) -> str:
    normalised = unicodedata.normalize("NFKC", text).strip().lower()
    normalised = _WS_RE.sub(" ", normalised)
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()


def _localise(sitting_date: date, t: time) -> datetime:
    return datetime.combine(sitting_date, t, tzinfo=VANCOUVER_TZ).astimezone(timezone.utc)


# ── Main extractor ──────────────────────────────────────────────────
@dataclass
class ParseResult:
    url: str
    url_meta: UrlMeta
    speeches: list[ParsedSpeech]
    sitting_start: Optional[time]
    sitting_end: Optional[time]
    section_hits: dict[str, int]  # diagnostics: raw section → paragraph count
    sitting_speaker_name: Optional[str]  # Presiding Speaker for "The Speaker" resolution


# ── Era detection ──────────────────────────────────────────────────
# Modern BC Hansard transcripts use class-driven semantics
# (`SpeakerBegins`, `Speaker-Name`, `Time-Stamp`, etc.). Pre-P38
# transcripts (1970-2008) use bare `<p><b>NAME:</b> body</p>`
# openers + `<p class="noindent">` continuations. The two markup
# families don't overlap meaningfully — modern has 0 of the legacy
# `noindent` paragraphs in body sections, and legacy has 0 of the
# `speakerbegins` markers — so a single class-presence count is
# sufficient to dispatch.
_LEGACY_DETECT_RE = re.compile(
    r'<p\s+class="(?:[^"]*\b)?noindent\b', re.IGNORECASE,
)
_MODERN_DETECT_RE = re.compile(
    r'<p\s+class="(?:[^"]*\b)?speaker[-_ ]?begins\b', re.IGNORECASE,
)


def detect_era(html_text: str) -> str:
    """Return 'modern' or 'legacy' based on observed markup.

    Modern (P38-S4 onward, late 2008+) emits `<p class="speakerbegins">`
    or `<p class="speaker-begins">` openers. Legacy (P29 1970 → P37 2005)
    uses bare `<p><b>NAME:</b>` openers — class-driven semantics is
    absent. The two formats don't overlap; presence of `speakerbegins`
    is sufficient to call it modern.
    """
    if _MODERN_DETECT_RE.search(html_text):
        return "modern"
    return "legacy"


# ── Legacy extractor (P29 1970 → P37 2005) ─────────────────────────
# Speaker openers are bare <p> tags whose first child is a <b> wrapping
# the all-caps attribution and a trailing colon. Continuations are
# <p class="noindent"> (and bare <p> tags whose first text isn't a
# speaker opener). Procedural text + headings live in
# class="proc_head" / "subj_head" — we treat them as section markers.
_LEGACY_OPENER_RE = re.compile(
    r"<p(?P<attrs>[^>]*)>"                 # bare <p> or with align="center"
    r"\s*<b[^>]*>"                           # <b> opener
    # Attribution: up to 200 chars to absorb NBSP indenting
    # ("&nbsp;" = 6 chars, P37 prefixes ~11 of them); the regex is
    # non-greedy and stops at the first colon.
    r"(?P<attribution>[^<]{2,200}?):"
    r"\s*</b>"                               # close of bold
    r"(?P<rest>.*?)</p>",
    re.DOTALL | re.IGNORECASE,
)
# Distinguish "real speaker openers" from book-keeping bold lines
# ("(Hansard)", "1970 Legislative Session: 1st Session, 29th
# Parliament", "FRIDAY, APRIL 3, 1970", "Afternoon Sitting"). Real
# attributions are uppercase honorific + name with internal whitespace
# and contain at least one alphabetic character.
_LEGACY_HONORIFIC_PREFIX_RE = re.compile(
    r"^\s*(?:HON\.?|MR\.?|MRS\.?|MS\.?|MISS|MADAM|MADAME|DR\.?)\s+",
    re.IGNORECASE,
)
# P36-P37 era also uses bare initial+surname form for non-Hon. members
# ("J. MacPhail", "R. Coleman"), or initial+initial+surname form
# (rarer). Single capital letter + period + space + capitalised
# surname (which may be compound with hyphens, periods, or apostrophes).
_LEGACY_INITIAL_LAST_PREFIX_RE = re.compile(
    r"^\s*[A-Z]\.\s*(?:[A-Z]\.\s*)?[A-Z][A-Za-z][\w'.\- ]*",
)


def _attribution_looks_like_speaker(att: str) -> bool:
    """Return True if attribution text matches a real speaker opener.

    Filters out section headings, front-matter, and TOC entries by
    requiring either an honorific prefix (Hon./Mr./Mrs./Ms.) OR an
    initial+surname pattern (J. MacPhail / R. Coleman) — the two
    attribution shapes used across legacy markup eras.
    """
    # Normalise: strip NBSPs, collapse whitespace, drop leading garbage.
    s = att.replace("\xa0", " ").replace("&nbsp;", " ")
    s = _WS_RE.sub(" ", s).strip()
    if not s:
        return False
    # Reject mostly-numeric tokens or sitting-date headers.
    if re.search(r"\d{4}", s):
        return False
    if _LEGACY_HONORIFIC_PREFIX_RE.match(s):
        return True
    if _LEGACY_INITIAL_LAST_PREFIX_RE.match(s):
        return True
    return False


def _normalize_attribution(att: str) -> str:
    """Strip NBSPs, leading whitespace, and collapse runs to single spaces."""
    s = att.replace("\xa0", " ").replace("&nbsp;", " ")
    return _WS_RE.sub(" ", s).strip()


def _extract_legacy(html_text: str, meta: UrlMeta) -> tuple[
    list[ParsedSpeech], dict[str, int], Optional[time], Optional[time], Optional[str],
]:
    """Walk the legacy-markup body via offset-based slicing.

    Each speaker opener match defines the start of a turn; the body
    includes everything between this opener and the next opener (which
    captures both the rest of the opener's <p> AND any subsequent
    `<p class="noindent">` continuations).
    """
    speeches: list[ParsedSpeech] = []
    section_hits: dict[str, int] = {}
    sitting_start: Optional[time] = None
    sitting_end: Optional[time] = None
    sitting_speaker_name: Optional[str] = None  # not exposed in legacy markup

    # Find all speaker openers; segments between them are the turns.
    openers: list[tuple[int, int, str, str]] = []
    for m in _LEGACY_OPENER_RE.finditer(html_text):
        att = (m.group("attribution") or "").strip()
        if not _attribution_looks_like_speaker(att):
            continue
        openers.append((m.start(), m.end(), att, m.group("rest") or ""))

    if not openers:
        return speeches, section_hits, sitting_start, sitting_end, sitting_speaker_name

    # First sitting timestamp — look for "The House met at H:MM p.m."
    # in the body before the first speaker opener.
    pre = html_text[: openers[0][0]]
    tm = _TIME_LINE_RE.search(_strip_tags(pre))
    if tm:
        h = int(tm.group("h"))
        m_ = int(tm.group("m"))
        if tm.group("ampm").lower() == "p" and h < 12:
            h += 12
        elif tm.group("ampm").lower() == "a" and h == 12:
            h = 0
        sitting_start = time(h, m_)

    for i, (start, end, attribution, rest_html) in enumerate(openers):
        # Body extends from end-of-opener up to next opener (or end of
        # doc for the last turn).
        body_end = openers[i + 1][0] if i + 1 < len(openers) else len(html_text)
        between = html_text[end:body_end]
        cont_bodies: list[str] = []
        # rest_html closes at </p>, so it's the rest of the opening
        # paragraph's body.
        rest_text = _strip_tags(rest_html)
        if rest_text:
            cont_bodies.append(rest_text)
        for pm in _LEGACY_CONTINUATION_RE.finditer(between):
            attrs = pm.group("attrs") or ""
            seg_body = pm.group("body") or ""
            # Skip class-bearing section markers (proc_head, subj_head,
            # toc1, toc2, time, page, header, footer, appendixSmall).
            if _LEGACY_SKIP_CLASS_RE.search(attrs):
                continue
            # Skip paragraphs that are themselves speaker openers — the
            # opener pass already captured them. (Detected via leading
            # <b>NAME:</b> after optional NBSP/whitespace.)
            if _LEGACY_OPENER_DETECT_RE.match(seg_body):
                continue
            seg_text = _strip_tags(seg_body)
            if seg_text:
                cont_bodies.append(seg_text)
        text = "\n\n".join(b for b in cont_bodies if b).strip()
        if not text:
            continue
        # Speaker role detection: "MR. SPEAKER" / "MR. CHAIRMAN" /
        # "MADAM SPEAKER" → role-only attribution. Otherwise honorific
        # + surname is captured raw.
        cleaned_attribution = _normalize_attribution(attribution)
        role = _legacy_role_from_attribution(cleaned_attribution)
        spoken_at = _localise(
            meta.sitting_date, sitting_start or meta.default_hhmm,
        )
        speech = ParsedSpeech(
            sequence=len(speeches) + 1,
            speaker_name_raw=cleaned_attribution,
            speaker_role=role,
            speech_type="speech",
            spoken_at=spoken_at,
            text=text,
            language="en",
            source_anchor=None,
            content_hash=_content_hash(text),
            raw={
                "variant": meta.variant,
                "section": None,
                "subject": None,
                "issue": meta.issue,
                "half": meta.half,
            },
        )
        speeches.append(speech)

    return speeches, section_hits, sitting_start, sitting_end, sitting_speaker_name


# Continuation paragraphs in legacy markup. Two markup styles seen:
#
#   P29-P34/P35 era: <p class="noindent"> / <p class="quote"> ...
#   P36-P37 era:     bare <p>...</p> with NBSP indenting (no class)
#
# We accept any <p>...</p> in the inter-opener slice, then post-filter
# out paragraphs that look like section markers (proc_head / subj_head /
# toc1 / toc2 / time / page / header / footer / appendixSmall) — those
# classes are explicitly excluded.
_LEGACY_CONTINUATION_RE = re.compile(
    r"<p(?P<attrs>[^>]*)>(?P<body>.*?)</p>",
    re.DOTALL | re.IGNORECASE,
)
_LEGACY_SKIP_CLASS_RE = re.compile(
    r'class="(?:[^"]*\b)?'
    r"(?:proc_head|subj_head|toc1|toc2|time|page|header|footer|"
    r"appendixSmall)\b",
    re.IGNORECASE,
)
# Continuation paragraphs that contain a leading <b>NAME:</b> are
# actually speaker openers — skip them in the continuation pass; the
# opener pass handles them.
_LEGACY_OPENER_DETECT_RE = re.compile(
    r'\s*(?:&nbsp;)*\s*<b[^>]*>'
    r"\s*(?:&nbsp;)*\s*"
    r"[^<]{2,80}?:"
    r"\s*</b>",
    re.IGNORECASE,
)


_LEGACY_ROLE_RE = re.compile(
    r"^\s*(?:HON\.?\s+)?(?:MR\.?|MRS\.?|MS\.?|MADAM|MADAME)\s+"
    r"(?P<role>SPEAKER|CHAIRMAN|CHAIRPERSON|CHAIR)\b",
    re.IGNORECASE,
)


def _legacy_role_from_attribution(att: str) -> Optional[str]:
    """If attribution names a role (Speaker/Chair), return it; else None."""
    m = _LEGACY_ROLE_RE.match(att or "")
    if m:
        return m.group("role").title()
    return None


def extract_speeches(html_text: str, url: str) -> ParseResult:
    """Parse one BC Hansard sitting (Blues / Final / Legacy) into ParsedSpeech list."""
    meta = parse_url_meta(url)
    if meta.variant == "legacy" or detect_era(html_text) == "legacy":
        speeches, section_hits, ss, se, speaker = _extract_legacy(html_text, meta)
        return ParseResult(
            url=url,
            url_meta=meta,
            speeches=speeches,
            sitting_start=ss,
            sitting_end=se,
            section_hits=section_hits,
            sitting_speaker_name=speaker,
        )
    speeches: list[ParsedSpeech] = []
    current_section: Optional[str] = None
    current_subject: Optional[str] = None
    current_time: Optional[time] = None
    current_time_anchor: Optional[str] = None
    sitting_start: Optional[time] = None
    sitting_end: Optional[time] = None
    section_hits: dict[str, int] = {}

    # Open turn accumulator
    turn_speaker: Optional[str] = None
    turn_role_from_name: Optional[str] = None
    turn_role_parenthetical: Optional[str] = None
    turn_body: list[str] = []
    turn_anchor: Optional[str] = None
    turn_time: Optional[time] = None
    turn_section: Optional[str] = None
    turn_subject: Optional[str] = None

    def flush_turn() -> None:
        nonlocal turn_speaker, turn_role_from_name, turn_role_parenthetical
        nonlocal turn_body, turn_anchor, turn_time, turn_section, turn_subject
        if turn_speaker is None:
            return
        text = "\n\n".join(b for b in turn_body if b).strip()
        if not text:
            turn_speaker = None
            turn_body = []
            return
        t = turn_time or current_time or meta.default_hhmm
        speech = ParsedSpeech(
            sequence=len(speeches) + 1,
            speaker_name_raw=turn_speaker,
            speaker_role=turn_role_parenthetical or turn_role_from_name,
            speech_type=_map_speech_type(turn_section),
            spoken_at=_localise(meta.sitting_date, t),
            text=text,
            language="en",
            source_anchor=turn_anchor,
            content_hash=_content_hash(text),
            raw={
                "variant": meta.variant,
                "section": turn_section,
                "subject": turn_subject,
                "issue": meta.issue,
                "half": meta.half,
            },
        )
        speeches.append(speech)
        turn_speaker = None
        turn_role_from_name = None
        turn_role_parenthetical = None
        turn_body = []
        turn_anchor = None
        turn_time = None
        turn_section = None
        turn_subject = None

    for para in _iter_paragraphs(html_text):
        cls = para.norm_cls

        # ── Time markers ──
        if cls in ("timestamp",):
            text = _strip_tags(para.body_html)
            t = _parse_time_stamp(para.anchor, text)
            if t:
                current_time = t
                current_time_anchor = para.anchor
            continue

        if cls in ("timeline",):
            text = _strip_tags(para.body_html)
            tm = _TIME_LINE_RE.search(text)
            if tm:
                h = int(tm.group("h"))
                m_ = int(tm.group("m"))
                if tm.group("ampm").lower() == "p" and h < 12:
                    h += 12
                elif tm.group("ampm").lower() == "a" and h == 12:
                    h = 0
                t_obj = time(h, m_)
                if sitting_start is None:
                    sitting_start = t_obj
                    current_time = t_obj
                else:
                    sitting_end = t_obj
            continue

        # ── Section headings: flush current turn, update context ──
        # `proceduralheading` is used in pre-P43 sittings in place of
        # `proceedingsheading` (same semantic meaning).
        if cls in ("proceedings", "proceedingsheading", "proceduralheading"):
            flush_turn()
            current_section = _strip_tags(para.body_html) or None
            current_subject = None
            section_hits[current_section or ""] = section_hits.get(current_section or "", 0) + 1
            continue
        if cls == "businessheading":
            flush_turn()
            current_section = _strip_tags(para.body_html) or None
            current_subject = None
            section_hits[current_section or ""] = section_hits.get(current_section or "", 0) + 1
            continue
        if cls == "subjectheading":
            flush_turn()
            current_subject = _strip_tags(para.body_html) or None
            continue

        # ── TOC in Final: Speaker-Name <p> outside Proceedings-Group wrapping
        # a link. Body is just the name wrapped in <a>. Skip by heuristic:
        # if the paragraph body is only a <a href="#..."> followed by plain
        # text and nothing else, it's TOC. Real speeches use SpeakerBegins.
        if cls == "speakername":
            continue

        # ── Speaker turn boundaries ──
        if cls == "speakerbegins":
            flush_turn()
            speaker_name, body_text = _extract_speaker(para.body_html)
            if not speaker_name:
                # Malformed SpeakerBegins with no name span (seen occasionally
                # in Blues after mid-speech chair change): treat as continuation
                # of previous speaker if one was just flushed, else drop.
                if speeches:
                    last = speeches[-1]
                    last.text += "\n\n" + body_text
                    last.text = last.text.strip()
                    last.content_hash = _content_hash(last.text)
                continue
            name_clean, role_name = _split_role(speaker_name)
            # Parenthetical role (rare in BC; included for safety)
            paren = _PAREN_ROLE_RE.match(name_clean)
            if paren:
                name_clean = paren.group("name").strip()
                turn_role_parenthetical = paren.group("role").strip()
            turn_speaker = name_clean
            turn_role_from_name = role_name
            turn_body = [body_text] if body_text else []
            turn_anchor = para.anchor or current_time_anchor
            turn_time = current_time
            turn_section = current_section
            turn_subject = current_subject
            continue

        if cls in ("speakercontinues", "speakercontinuesmidspeech"):
            body_text = _strip_tags(para.body_html)
            if body_text and turn_speaker is not None:
                turn_body.append(body_text)
            continue

        # Non-speech context — ignored for output but flushes nothing.
        if cls in (
            "editorialcomment",
            "chairchangemidspeech",
            "styleline",
            "dateoftranscript",
            "timelineroman",
        ):
            continue

        # Any other class inside a speaker turn → treat as body continuation.
        if turn_speaker is not None:
            body_text = _strip_tags(para.body_html)
            if body_text:
                turn_body.append(body_text)

    flush_turn()

    return ParseResult(
        url=url,
        url_meta=meta,
        speeches=speeches,
        sitting_start=sitting_start,
        sitting_end=sitting_end,
        section_hits=section_hits,
        sitting_speaker_name=extract_sitting_speaker(html_text),
    )


# ── CLI harness for offline iteration ───────────────────────────────
# `python -m src.legislative.bc_hansard_parse <path-or-url>` prints
# parsed speeches to stdout — use against saved fixtures to iterate
# regex without DB or network.
if __name__ == "__main__":  # pragma: no cover
    import sys

    if len(sys.argv) < 2:
        print("usage: python -m src.legislative.bc_hansard_parse <fixture.htm[l]>", file=sys.stderr)
        sys.exit(2)
    path = sys.argv[1]
    with open(path, encoding="utf-8") as f:
        raw = f.read()
    # Infer URL from filename for URL meta parsing
    fake_url = f"https://lims.leg.bc.ca/hdms/file/Debates/43rd2nd/{path.rsplit('/', 1)[-1]}"
    result = extract_speeches(raw, fake_url)
    print(
        f"url={result.url}\n"
        f"variant={result.url_meta.variant} date={result.url_meta.sitting_date} "
        f"half={result.url_meta.half} issue={result.url_meta.issue}\n"
        f"sitting_start={result.sitting_start} sitting_end={result.sitting_end}\n"
        f"speeches={len(result.speeches)}\n"
        f"sections seen: {result.section_hits}\n"
        "---"
    )
    for sp in result.speeches[:8]:
        print(
            f"[{sp.sequence:3d}] {sp.spoken_at:%H:%M} "
            f"{sp.speech_type:<18} anchor={sp.source_anchor} "
            f"({sp.word_count:>4} words) {sp.speaker_name_raw!r}"
        )
        preview = sp.text[:140].replace("\n", " ")
        print(f"      {preview}…")
    print("...")
    for sp in result.speeches[-4:]:
        print(
            f"[{sp.sequence:3d}] {sp.spoken_at:%H:%M} "
            f"{sp.speech_type:<18} anchor={sp.source_anchor} "
            f"({sp.word_count:>4} words) {sp.speaker_name_raw!r}"
        )
