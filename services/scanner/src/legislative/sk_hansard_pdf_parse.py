"""SK Hansard PDF parser — Poppler text → speeches.

Mirror of `ab_hansard.extract_speeches_from_text` for SK Hansard PDFs
(29L1S–29L3S are 100% PDF; early 29L4S has gaps; AM/EVE supplementary
sittings are PDF-only). The HTML era (29L4S onwards) ships through
`sk_hansard_parse.parse_hansard_html`; this module is the parallel
text-based path.

Differences from AB:
- Speaker turn separator is `: — ` (colon space em-dash) instead of `: `.
- Section markers are bare ALL-CAPS lines (`ROUTINE PROCEEDINGS`,
  `QUESTION PERIOD`, etc.) — no `head:` token.
- Names with disambiguating initials: `Mr. D. Harrison`, `Ms. A. Ross`.
- End-of-content marker: `GOVERNMENT OF SASKATCHEWAN` followed by
  `CABINET MINISTERS` (cabinet roster is printed as back-matter on
  every Hansard PDF).
- Honorifics: `Hon.`, `Mr.`, `Mrs.`, `Ms.` (with period, unlike AB's
  `Ms` no-period), `Dr.`.

PDF text comes from `pdf_utils.pdftotext()` in default reading-order
mode (NOT `-layout`) — SK PDFs are two-column prose.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional

log = logging.getLogger(__name__)

# ── Line-level skips (running headers / footers / blanks) ──────────

_PAGE_NUMBER_RE = re.compile(r"^\d{1,5}$")
_RUNNING_TITLE_RE = re.compile(
    r"^(?:LEGISLATIVE ASSEMBLY OF SASKATCHEWAN|SASKATCHEWAN HANSARD)$",
    re.IGNORECASE,
)
_RUNNING_DATE_RE = re.compile(
    r"^(?:January|February|March|April|May|June|July|August|"
    r"September|October|November|December)\s+\d{1,2},\s+\d{4}$",
    re.IGNORECASE,
)
# Bracketed procedural inserts on a single line:
#   [The Assembly met at 13:30.]   [Prayers]
#   [The Assembly recessed from 17:00 until 19:00.]
_PROCEDURAL_RE = re.compile(r"^\[[^\]]+\]$")

# Sitting-open marker — flips us out of preamble.
_OPEN_SITTING_RE = re.compile(
    r"^\[The Assembly (?:met|resumed)\b", re.IGNORECASE,
)

# Cabinet-roster back-matter boundary. Once this header appears we stop
# parsing speeches — anything after is the printed minister list.
_BACK_MATTER_RE = re.compile(r"^GOVERNMENT OF SASKATCHEWAN$")
_BACK_MATTER_FOLLOWUP_RE = re.compile(r"^CABINET MINISTERS$")

# ── Section markers ────────────────────────────────────────────────
# All-caps lines that match a known SK Hansard section name. We list
# them explicitly so random ALL-CAPS bill titles (`AN ACT TO ...`)
# don't get treated as section breaks.

_SECTIONS: frozenset[str] = frozenset({
    "ROUTINE PROCEEDINGS",
    "PRESENTING PETITIONS",
    "READING AND RECEIVING PETITIONS",
    "PRESENTING REPORTS OF STANDING AND SPECIAL COMMITTEES",
    "NOTICES OF MOTIONS AND QUESTIONS",
    "INTRODUCTION OF GUESTS",
    "STATEMENTS BY MEMBERS",
    "QUESTION PERIOD",
    "MINISTERIAL STATEMENTS",
    "INTRODUCTION OF BILLS",
    "ORDERS OF THE DAY",
    "WRITTEN QUESTIONS",
    "GOVERNMENT ORDERS",
    "PRIVATE MEMBERS' BUSINESS",
    "PRIVATE MEMBERS BUSINESS",
    "ADJOURNED DEBATES",
    "ADDRESS IN REPLY",
    "SPECIAL ORDER",
    "FIRST READINGS",
    "SECOND READINGS",
    "THIRD READINGS",
    "COMMITTEE OF FINANCE",
    "COMMITTEE OF THE WHOLE",
    "COMMITTEE OF THE WHOLE ON BILLS",
    "MOTIONS",
    "TABLING OF DOCUMENTS",
    "TABLED DOCUMENTS",
    "TABLING OF REPORTS",
    "POINT OF ORDER",
    "POINTS OF ORDER",
    "RESOLUTIONS",
    "ROYAL ASSENT",
    "PRIVATE BILLS",
})

# ── Speaker line patterns ──────────────────────────────────────────

# Person turn: honorific (+ optional initial) + surname + ": — body".
# Honorifics: Hon. / Mr. / Mrs. / Ms. / Dr. (period included).
# Optional initial like "D." in "Mr. D. Harrison" — disambiguates same-
# surname holders (Mr. D. Harrison vs Mr. J. Harrison etc.).
# Surnames may be hyphenated, apostrophised, or accented (Nippi-Albright,
# D'Autremont, Bélanger).
_PERSON_SPEAKER_RE = re.compile(
    r"^(?P<honorific>Hon\.|Mr\.|Mrs\.|Ms\.|Dr\.)\s+"
    r"(?:(?P<initial>[A-Z])\.\s+)?"
    r"(?P<surname>[\wÀ-ſ'\-]+(?:\s+[\wÀ-ſ'\-]+){0,2})"
    r"\s*:\s*[—\-–]\s*(?P<body>.*)$",
    re.IGNORECASE,
)

# Role-only speaker lines. "The Speaker: — body".
# Listed in descending specificity ("The Acting Speaker" before
# "The Speaker"; "The Deputy Chair of Committees" before "The Chair").
_ROLE_SPEAKER_RE = re.compile(
    r"^(?P<role>The\s+(?:"
    r"Acting\s+Speaker"
    r"|Deputy\s+Chair\s+of\s+Committees"
    r"|Deputy\s+Chair"
    r"|Deputy\s+Speaker"
    r"|Chair"
    r"|Speaker"
    r"|Sergeant[-\s]at[-\s]Arms"
    r"|Clerk(?:\s+Assistant)?"
    r"|Deputy\s+Clerk"
    r"|Principal\s+Clerk"
    r"|Lieutenant\s+Governor"
    r"))\s*:\s*[—\-–]\s*(?P<body>.*)$",
    re.IGNORECASE,
)

# Group attribution — "Some Hon. Members:", "Hon. Members:", etc.
# These are voice-vote responses, kept as roles not persons.
_GROUP_SPEAKER_RE = re.compile(
    r"^(?P<role>Some\s+Hon\.\s+Members"
    r"|Hon\.\s+Members"
    r"|Some\s+Members"
    r"|An\s+Hon\.\s+Member)"
    r"\s*:\s*[—\-–]?\s*(?P<body>.*)$",
    re.IGNORECASE,
)

# Named chair speaker — "Chair B. McLeod", "Deputy Chair Keisig". Same
# shape as the HTML parser; carries the lastname (and optional initial)
# for fallback FK match.
_NAMED_CHAIR_RE = re.compile(
    r"^(?P<role>Chair|Deputy\s+Chair(?:\s+of\s+Committees)?|Deputy\s+Speaker|Speaker)\s+"
    r"(?:(?P<initial>[A-Z])\.?\s+)?"
    r"(?P<surname>[\wÀ-ſ'\-]+)"
    r"\s*:\s*[—\-–]\s*(?P<body>.*)$",
    re.IGNORECASE,
)


# ── Output shape ───────────────────────────────────────────────────

@dataclass
class ParsedSpeech:
    sequence: int
    speaker_name_raw: str        # "The Speaker", "Mr. D. Harrison", "Some Hon. Members"
    speaker_role: Optional[str]  # 'speaker' / 'deputy_speaker' / 'chair' / 'deputy_chair' /
                                 # 'minister' / 'member' / 'chorus' / 'unknown'
    honorific: Optional[str]     # "Hon." / "Mr." / "Ms." / None
    initial: Optional[str]       # "D" / "A" / None
    surname: Optional[str]       # None for role-only / chorus
    body: str
    section: Optional[str]       # "QUESTION PERIOD" etc.
    is_speaker_role: bool
    is_chorus: bool


# ── Normalisers ────────────────────────────────────────────────────

_WS_RE = re.compile(r"\s+")
_SOFT_HYPHEN_RE = re.compile(r"-\n(?=[a-z])")


def _normalise_role(raw: str) -> str:
    """Map matched role text to canonical lowercase short tokens
    consistent with sk_hansard_parse classify_speaker output."""
    t = _WS_RE.sub(" ", raw.strip()).lower()
    if "deputy chair" in t:
        return "deputy_chair"
    if "deputy speaker" in t:
        return "deputy_speaker"
    if "chair" == t.replace("the ", "").strip():
        return "chair"
    if "the chair" in t:
        return "chair"
    if "speaker" in t:
        return "speaker"
    # Sergeant-at-arms / Clerks fall through here — surface as canonical
    # role text so the resolver can ignore them (no MLA FK).
    return t.replace("the ", "")


def _join_body(lines: list[str]) -> str:
    """Join collected body lines, soft-hyphen merging on word breaks."""
    text = "\n".join(lines).strip()
    if not text:
        return ""
    # Merge soft-hyphenated word breaks: "trans-\nport" → "transport".
    text = _SOFT_HYPHEN_RE.sub("", text)
    # Collapse single newlines inside paragraphs to spaces, preserve
    # double-newlines as paragraph breaks.
    paragraphs = [p.replace("\n", " ") for p in re.split(r"\n\s*\n", text)]
    return "\n\n".join(_WS_RE.sub(" ", p).strip() for p in paragraphs if p.strip())


def _looks_like_section(stripped: str) -> bool:
    """True if line is an ALL-CAPS section header we recognise."""
    if stripped != stripped.upper():
        return False
    if stripped in _SECTIONS:
        return True
    return False


# ── Public entry point ────────────────────────────────────────────

def extract_speeches_from_text(raw: str) -> list[ParsedSpeech]:
    """Walk pdftotext output, emit one ParsedSpeech per speaker turn."""
    lines = raw.splitlines()
    out: list[ParsedSpeech] = []
    current_section: Optional[str] = None
    cur: Optional[ParsedSpeech] = None
    cur_body_lines: list[str] = []

    def _finalize() -> None:
        nonlocal cur, cur_body_lines
        if cur is not None:
            body = _join_body(cur_body_lines)
            if body:
                cur.body = body
                out.append(cur)
        cur = None
        cur_body_lines = []

    in_preamble = True
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        stripped = line.strip()

        # Cabinet-roster back-matter — terminate parsing.
        if _BACK_MATTER_RE.match(stripped):
            # Verify the next non-blank line is the followup banner.
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines) and _BACK_MATTER_FOLLOWUP_RE.match(lines[j].strip()):
                _finalize()
                break

        # Blank lines are paragraph separators inside speech bodies.
        if not stripped:
            if cur is not None:
                cur_body_lines.append("")
            i += 1
            continue

        # Running headers / footers / page numbers — skip.
        if (_PAGE_NUMBER_RE.match(stripped)
                or _RUNNING_TITLE_RE.match(stripped)
                or _RUNNING_DATE_RE.match(stripped)):
            i += 1
            continue

        # Procedural bracketed inserts. Flip out of preamble on the
        # first sitting-open marker.
        if _PROCEDURAL_RE.match(stripped):
            if in_preamble and _OPEN_SITTING_RE.match(stripped):
                in_preamble = False
            i += 1
            continue

        # Section header — only flip current_section while we're in
        # content mode. ALL-CAPS lines in the preamble are part of the
        # cover page (TOC, member roster) — ignore them there.
        if _looks_like_section(stripped):
            if not in_preamble:
                _finalize()
                current_section = stripped
            i += 1
            continue

        if in_preamble:
            i += 1
            continue

        # Speaker line detection — try most specific first.
        m_role = _ROLE_SPEAKER_RE.match(stripped)
        m_named_chair = _NAMED_CHAIR_RE.match(stripped) if not m_role else None
        m_group = _GROUP_SPEAKER_RE.match(stripped) if not m_role and not m_named_chair else None
        m_person = (_PERSON_SPEAKER_RE.match(stripped)
                    if not (m_role or m_named_chair or m_group) else None)

        if m_role:
            _finalize()
            role_token = _normalise_role(m_role.group("role"))
            cur = ParsedSpeech(
                sequence=len(out) + 1,
                speaker_name_raw=_WS_RE.sub(" ", m_role.group("role").strip()),
                speaker_role=role_token,
                honorific=None, initial=None, surname=None,
                body="", section=current_section,
                is_speaker_role=True, is_chorus=False,
            )
            body_start = (m_role.group("body") or "").strip()
            if body_start:
                cur_body_lines.append(body_start)
            i += 1
            continue

        if m_named_chair:
            _finalize()
            role_token = _normalise_role(m_named_chair.group("role"))
            initial = m_named_chair.group("initial")
            surname = m_named_chair.group("surname").strip()
            display = m_named_chair.group("role").strip()
            if initial:
                display = f"{display} {initial}. {surname}"
            else:
                display = f"{display} {surname}"
            cur = ParsedSpeech(
                sequence=len(out) + 1,
                speaker_name_raw=display,
                speaker_role=role_token,
                honorific=None,
                initial=(initial.upper() + ".") if initial else None,
                surname=surname,
                body="", section=current_section,
                is_speaker_role=True, is_chorus=False,
            )
            body_start = (m_named_chair.group("body") or "").strip()
            if body_start:
                cur_body_lines.append(body_start)
            i += 1
            continue

        if m_group:
            _finalize()
            role = _WS_RE.sub(" ", m_group.group("role").strip())
            cur = ParsedSpeech(
                sequence=len(out) + 1,
                speaker_name_raw=role,
                speaker_role="chorus",
                honorific=None, initial=None, surname=None,
                body="", section=current_section,
                is_speaker_role=False, is_chorus=True,
            )
            body_start = (m_group.group("body") or "").strip()
            if body_start:
                cur_body_lines.append(body_start)
            i += 1
            continue

        if m_person:
            _finalize()
            honorific = m_person.group("honorific")
            # Normalise capitalisation (older PDFs may use "MR." / "MS.").
            honorific = honorific[0].upper() + honorific[1:].lower()
            initial = m_person.group("initial")
            surname = _WS_RE.sub(" ", m_person.group("surname").strip())
            display_init = f"{initial}. " if initial else ""
            display = f"{honorific} {display_init}{surname}"
            role = "minister" if honorific.lower().startswith("hon") else "member"
            cur = ParsedSpeech(
                sequence=len(out) + 1,
                speaker_name_raw=display,
                speaker_role=role,
                honorific=honorific,
                initial=(initial.upper()) if initial else None,
                surname=surname,
                body="", section=current_section,
                is_speaker_role=False, is_chorus=False,
            )
            body_start = (m_person.group("body") or "").strip()
            if body_start:
                cur_body_lines.append(body_start)
            i += 1
            continue

        # Default: continuation of current speech body.
        if cur is not None:
            cur_body_lines.append(stripped)
        i += 1

    _finalize()
    return out
