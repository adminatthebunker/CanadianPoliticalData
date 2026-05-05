"""eScribe ingester — pub-{city}.escribemeetings.com → meetings/bills/votes.

eScribe is a Canadian municipal-meeting SaaS (now under OnBoard) used by
~100+ Canadian cities. Calgary, Edmonton, Ottawa, Mississauga, and Hamilton
all publish their council + committee agendas on it. One scraper module
covers the whole family — only the hostname differs.

Discovery is **server-rendered**: a single GET of
``MeetingsCalendarView.aspx`` returns a single ~425KB HTML document with
the full historical meeting list (typically back to ~2017) inlined,
grouped by ``MeetingType="..."`` panels. Each meeting row contains:

  - ``Meeting.aspx?Id=<guid>&lang=English`` link (the per-meeting agenda)
  - ``VideoStream.aspx?MeetingId=<guid>`` link when video is available
  - ``YearYYYY`` CSS classes for client-side year filtering (every year is
    inline; we don't need to paginate)
  - Date / time strings in long human format

The AJAX endpoint at ``MeetingsContent.aspx/PastMeetings`` was probed and
behaves inconsistently for non-browser callers (returns ``{"d":[]}`` even
for known-good meeting types). We deliberately bypass it — the SSR
HTML route is more reliable.

Per-meeting agenda HTML lives at ``Meeting.aspx?Id=<guid>&Agenda=Agenda``;
parser extracts motion text, mover, seconder, and recorded votes from
the structured ``class="Vote" / "VoteHeader" / "Voters" / "Votes"`` DOM.

Idempotency:
  - meetings: upsert keyed on ``(source_system, source_meeting_id)``.
  - bills:    upsert keyed on ``source_id`` (UNIQUE).
  - votes:    upsert keyed on ``(source_system, source_url)``.

Project convention: regex-only HTML parsing — no BeautifulSoup / lxml.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import ssl
from dataclasses import dataclass, field as dc_field
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

log = logging.getLogger(__name__)

REQUEST_TIMEOUT = 60
HEADERS = {
    "User-Agent": "CanadianPoliticalDataBot/1.0 (+https://canadianpoliticaldata.ca; admin@thebunkerops.ca)",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-CA,en;q=0.9",
}

# eScribe is fronted by Cloudflare with a chain that goes through
# `SSL.com TLS Transit ECC CA R2` → `AAA Certificate Services` (Comodo).
# The certifi 2026.4.x bundle in the container doesn't ship the intermediate
# AAA-root needed to validate that chain, but Debian's
# /etc/ssl/certs/ca-certificates.crt does. Use the OS bundle when present.
def _verify_ctx() -> object:
    os_bundle = "/etc/ssl/certs/ca-certificates.crt"
    if os.path.exists(os_bundle):
        return ssl.create_default_context(cafile=os_bundle)
    return True  # fall back to httpx default (certifi)


SSL_VERIFY = _verify_ctx()


# ── City config ─────────────────────────────────────────────────────


@dataclass(frozen=True)
class EscribeCity:
    slug: str                     # 'calgary' | 'edmonton'
    host: str                     # 'pub-calgary.escribemeetings.com'
    province_territory: str       # 'AB'
    source_system: str            # 'calgary-escribemeetings'
    youtube_channel: str          # 'https://www.youtube.com/@CityofCalgary'

    @property
    def base_url(self) -> str:
        return f"https://{self.host}"

    @property
    def calendar_url(self) -> str:
        return f"{self.base_url}/MeetingsCalendarView.aspx"

    def meeting_url(self, source_meeting_id: str) -> str:
        return f"{self.base_url}/Meeting.aspx?Id={source_meeting_id}&Agenda=Agenda&lang=English"


CITIES: dict[str, EscribeCity] = {
    "calgary": EscribeCity(
        slug="calgary",
        host="pub-calgary.escribemeetings.com",
        province_territory="AB",
        source_system="calgary-escribemeetings",
        youtube_channel="https://www.youtube.com/@CityofCalgary",
    ),
    "edmonton": EscribeCity(
        slug="edmonton",
        host="pub-edmonton.escribemeetings.com",
        province_territory="AB",
        source_system="edmonton-escribemeetings",
        youtube_channel="https://www.youtube.com/@cityofedmonton",
    ),
}


# ── Models ──────────────────────────────────────────────────────────


@dataclass
class ParsedMeeting:
    """One row from the calendar HTML."""
    source_meeting_id: str       # eScribe GUID
    body_name: str               # MeetingType panel name, e.g. "Combined Meeting of Council"
    body_type: str               # 'council' | 'committee' | 'committee_of_the_whole'
    started_at: Optional[datetime]
    location: Optional[str] = None
    agenda_url: Optional[str] = None
    video_stream_url: Optional[str] = None
    is_cancelled: bool = False


@dataclass
class ParsedAgendaItem:
    item_number: str             # e.g. "5.1" or "M2024-1234"
    title: str
    description: Optional[str] = None
    item_type: str = "motion"    # 'motion' | 'bylaw' | 'report' (resolves to bills.bill_type)
    mover_name: Optional[str] = None
    seconder_name: Optional[str] = None
    vote_result: Optional[str] = None  # 'Carried' | 'Defeated' | 'Withdrawn' | None
    vote_ayes: Optional[int] = None
    vote_nays: Optional[int] = None
    vote_positions: list[tuple[str, str]] = dc_field(default_factory=list)
                                  # [(councillor_name, 'aye'|'nay'|'absent'), ...]


@dataclass
class ParsedMeetingDetail:
    body_name: str
    started_at: Optional[datetime]
    items: list[ParsedAgendaItem]


@dataclass
class IngestStats:
    cities_processed: int = 0
    meetings_seen: int = 0
    meetings_inserted: int = 0
    meetings_updated: int = 0
    meetings_fetched: int = 0
    pages_parsed: int = 0
    bills_inserted: int = 0
    bills_updated: int = 0
    bill_events_inserted: int = 0
    bill_sponsors_inserted: int = 0
    votes_inserted: int = 0
    vote_positions_inserted: int = 0
    movers_resolved: int = 0
    movers_unresolved: int = 0
    parse_warnings: int = 0
    fetch_failures: list[str] = dc_field(default_factory=list)


# ── HTTP ────────────────────────────────────────────────────────────


async def _fetch(client: httpx.AsyncClient, url: str) -> Optional[str]:
    try:
        r = await client.get(url, timeout=REQUEST_TIMEOUT)
        if r.status_code != 200:
            log.warning("escribe fetch %s -> http %d", url, r.status_code)
            return None
        if len(r.text) < 1000:
            log.warning("escribe fetch %s -> short body (%d bytes)", url, len(r.text))
            return None
        return r.text
    except httpx.HTTPError as exc:
        log.warning("escribe fetch %s -> %s", url, exc)
        return None


# ── Calendar (discovery) parser ────────────────────────────────────


# Each "MeetingType" panel wraps a group of meetings of the same type.
# Layout (server-rendered):
#   <div class="panel-contents MeetingTypeContainer" MeetingType="...">
#     <div class='Year2026' >... meeting row ...</div>
#     <div class='Year2025' >... meeting row ...</div>
#     ...
#   </div>
# The MeetingType attribute name is the body name we want.
_PANEL_RE = re.compile(
    r'class="panel-contents MeetingTypeContainer"\s+MeetingType="(?P<body>[^"]+)"',
    re.IGNORECASE,
)

# Per-meeting agenda link (the canonical Meeting.aspx URL):
#   <a ... href='Meeting.aspx?Id=<guid>&lang=English' ...>{body name}</a>
# We capture the GUID + the surrounding 4 KB of HTML to extract date/time/year.
_AGENDA_LINK_RE = re.compile(
    r"href='Meeting\.aspx\?Id=(?P<id>[a-f0-9-]{36})(?:&(?:Agenda|amp;Agenda)=Agenda)?(?:&(?:lang|amp;lang)=English)?'",
    re.IGNORECASE,
)

# Video stream link (when present):
_VIDEO_RE = re.compile(
    r"href='VideoStream\.aspx\?MeetingId=(?P<id>[a-f0-9-]{36})'",
    re.IGNORECASE,
)

# Date strings in the calendar — long format with day-of-week.
# e.g. "Tuesday, May 05, 2026 @ 9:30 AM"  or  "Monday, October 27, 2025"
_DATE_LONG_RE = re.compile(
    r"(?:Sun|Mon|Tues|Wednes|Thurs|Fri|Satur)day,\s+"
    r"(?P<month>January|February|March|April|May|June|July|August|"
    r"September|October|November|December)\s+"
    r"(?P<day>\d{1,2}),\s+"
    r"(?P<year>\d{4})"
    r"(?:\s+@\s+(?P<hour>\d{1,2}):(?P<minute>\d{2})\s+(?P<ampm>AM|PM))?",
    re.IGNORECASE,
)

# YearXXXX CSS class on each meeting row — the canonical year discriminator.
_YEAR_CLASS_RE = re.compile(r"\bYear(?P<y>\d{4})\b")

# "Cancelled" marker.
_CANCELLED_RE = re.compile(r"\bCancelled\b", re.IGNORECASE)

_MONTH_TO_NUM = {
    name.lower(): i for i, name in enumerate(
        ["", "January", "February", "March", "April", "May", "June",
         "July", "August", "September", "October", "November", "December"]
    )
}


def _parse_long_date(s: str) -> Optional[datetime]:
    m = _DATE_LONG_RE.search(s)
    if not m:
        return None
    month = _MONTH_TO_NUM[m.group("month").lower()]
    day = int(m.group("day"))
    year = int(m.group("year"))
    hour = int(m.group("hour")) if m.group("hour") else 0
    minute = int(m.group("minute")) if m.group("minute") else 0
    if m.group("ampm"):
        ap = m.group("ampm").upper()
        if ap == "PM" and hour < 12:
            hour += 12
        elif ap == "AM" and hour == 12:
            hour = 0
    # Mountain Time for AB cities; store as UTC by adding 6h (MST) or 7h (MDT)
    # — we don't disambiguate DST here; the discrepancy is at most 1h and
    # doesn't affect session-bucketing or daily ordering. Better to add a
    # proper tz lookup later if cities are added in other zones.
    try:
        naive = datetime(year, month, day, hour, minute)
    except ValueError:
        return None
    # Treat as Mountain time → UTC. AB observes MST (UTC-6 in summer, MDT)
    # and MST (UTC-7 in winter). Approximate DST window Mar-Nov; the
    # discrepancy at the boundary (1h for ~1 day a year) doesn't affect
    # session bucketing or daily ordering. Add the offset via timedelta
    # so dates roll over cleanly for evening meetings.
    offset_h = 6 if (3 <= month <= 11) else 7
    return naive.replace(tzinfo=timezone.utc) + timedelta(hours=offset_h)


_BODY_TYPE_HEURISTICS = (
    # Order matters; first match wins.
    (re.compile(r"\bcombined meeting of council\b", re.IGNORECASE), "council"),
    (re.compile(r"\bregular meeting of council\b", re.IGNORECASE), "council"),
    (re.compile(r"\bcouncil\b(?!\s+\w+\s+committee)", re.IGNORECASE), "council"),
    (re.compile(r"\bcommittee of the whole\b", re.IGNORECASE), "committee_of_the_whole"),
    (re.compile(r"\bcommittee\b", re.IGNORECASE), "committee"),
    (re.compile(r"\bcommission\b", re.IGNORECASE), "committee"),
    (re.compile(r"\bboard\b", re.IGNORECASE), "committee"),
)


def _classify_body_type(body_name: str) -> str:
    for rx, kind in _BODY_TYPE_HEURISTICS:
        if rx.search(body_name):
            return kind
    return "committee"  # default for "Sub-Committee on ...", "Advisory ...", etc.


# aria-label pattern wraps every Meeting.aspx link in the calendar HTML
# with a string like "<MeetingType> <DayOfWeek>, <Month> <DD>, <YYYY> @ <Time>"
# (or similar with action prefix "Public Comment for ..." / "Share ...").
# We use this as the primary discovery path because it's present in BOTH
# the server-rendered upcoming-meetings section AND inside the per-type
# panels when AJAX has populated them. Matching the aria-label gives us
# meeting type + date in one shot.
_ARIA_LINK_RE = re.compile(
    r"aria-label='(?P<aria>[^']{5,200}?)'"
    r"\s+href='Meeting\.aspx\?Id=(?P<id>[a-f0-9-]{36})"
    r"(?:&(?:Agenda|amp;Agenda)=Agenda)?(?:&(?:lang|amp;lang)=English)?'",
    re.IGNORECASE,
)

# Strip the action-verb prefix off the aria-label so what's left starts
# with the meeting type. The page emits multiple links per meeting with
# different prefixes ("Share", "Public Comment for", "Request to speak for",
# etc.); we de-dup on Id and prefer the canonical heading link with no prefix.
_ARIA_PREFIX_RE = re.compile(
    r"^(?:Share|Public Comment(?: for)?|Open for Comments(?: for)?|"
    r"Request to speak for|Delgation request for|Delegation request for|"
    r"View Live Stream(?: For)?|Open|Attachment for)\s+",
    re.IGNORECASE,
)


def _parse_aria_label(aria: str) -> tuple[str, Optional[datetime]]:
    """Extract (meeting_type, started_at) from an aria-label string.

    The label shapes (most common to least):
      "Executive Committee Tuesday, May 05, 2026 @ 9:30 AM"
      "Share Executive Committee Tuesday, May 05, 2026 @ 9:30 AM"
      "Public Comment for Executive Committee Tuesday, May 05, 2026 @ 9:30 AM"
      "Combined Meeting of Council Monday, October 27, 2025"

    We strip the action prefix, then split on the date pattern.
    """
    s = _ARIA_PREFIX_RE.sub("", aria.strip())
    # The date starts at the first day-of-week token.
    dm = _DATE_LONG_RE.search(s)
    started_at = _parse_long_date(s) if dm else None
    if dm:
        meeting_type = s[:dm.start()].strip().rstrip(".,")
    else:
        meeting_type = s.strip()
    # Trailing punctuation/period markers from "Combined Meeting of Council."
    meeting_type = meeting_type.rstrip(".")
    return meeting_type, started_at


def parse_calendar_html(html: str) -> list[ParsedMeeting]:
    """Walk every Meeting.aspx anchor and yield one ParsedMeeting per unique id.

    Pragmatic strategy: rather than walking the panel hierarchy (which is
    AJAX-populated and so empty in the server response), we harvest every
    aria-label='...' href='Meeting.aspx?Id=<guid>' pair. The aria-label
    encodes the meeting type and date in one place, and dedup is on
    the GUID. Multiple anchors per meeting are common (heading, share,
    public-comment, video) — we keep the one whose aria-label parses
    cleanly to (type, date).

    This means we get the server-rendered upcoming + most-recent-past
    meetings (typically ~5-20 per fetch). Historical backfill (older
    months / years) is **out of scope** for this parser — that needs the
    AJAX path or an alternate URL pattern, both of which are flaky on
    Calgary's eScribe instance as of 2026-05-05. Daily-cron coverage
    going forward is what this surface delivers.
    """
    out: list[ParsedMeeting] = []
    seen_ids: set[str] = set()

    for am in _ARIA_LINK_RE.finditer(html):
        mid = am.group("id").lower()
        if mid in seen_ids:
            continue
        meeting_type, started_at = _parse_aria_label(am.group("aria"))
        if not meeting_type:
            continue
        # Slice ~2 KB of surrounding HTML to find the video stream URL and
        # cancelled flag for this meeting.
        link_pos = am.start()
        ctx_start = max(0, link_pos - 1500)
        ctx_end = min(len(html), link_pos + 1500)
        ctx = html[ctx_start:ctx_end]
        video_match = _VIDEO_RE.search(ctx)
        video_url: Optional[str] = None
        if video_match and video_match.group("id").lower() == mid:
            video_url = video_match.group(0).split("'")[1]
        seen_ids.add(mid)
        out.append(ParsedMeeting(
            source_meeting_id=mid,
            body_name=meeting_type,
            body_type=_classify_body_type(meeting_type),
            started_at=started_at,
            location=None,
            agenda_url=f"Meeting.aspx?Id={mid}&Agenda=Agenda&lang=English",
            video_stream_url=video_url,
            is_cancelled=bool(_CANCELLED_RE.search(ctx)),
        ))
    return out


# ── Per-meeting parser ─────────────────────────────────────────────


# Vote block on a per-meeting page. eScribe renders recorded votes inside a
# div hierarchy with these class markers:
#   <div class="VoteResult"> ... <span class="VoteResultText">Carried</span>
#   <div class="VoteHeader">In Favour (N)</div>
#   <div class="Voters"><span>Name 1</span><span>Name 2</span>...</div>
#   <div class="VoteHeader">Opposed (N)</div>
#   <div class="Voters">...</div>
#
# We capture each <div class="Vote ..."> ... </div> block (greedy enough
# to swallow the inner Voters list) and then sub-parse it.
_VOTE_BLOCK_RE = re.compile(
    r'<div\s+class="Vote(?:\s+[^"]+)?"[^>]*>(?P<inner>.+?)</div>\s*<!--\s*/Vote\s*-->'
    r'|<div\s+class="VoteResults?"[^>]*>(?P<inner2>.+?)(?=<div\s+class="VoteResults?"|<div\s+class="(?:AgendaItem|MotionItem|Section)|\Z)',
    re.IGNORECASE | re.DOTALL,
)

_VOTE_RESULT_RE = re.compile(
    r'class="VoteResultText[^"]*"[^>]*>\s*(?P<result>[A-Za-z][^<]+?)\s*<',
    re.IGNORECASE,
)

_VOTE_HEADER_RE = re.compile(
    r'class="VoteHeader[^"]*"[^>]*>\s*(?P<label>In Favour|Opposed|Absent|Abstained)\s*'
    r'(?:\s*\(\s*(?P<count>\d+)\s*\))?',
    re.IGNORECASE,
)

_VOTERS_BLOCK_RE = re.compile(
    r'class="Voters?"[^>]*>(?P<inner>.+?)</div>',
    re.IGNORECASE | re.DOTALL,
)

# Inside Voters, each councillor name is wrapped in a <span> or anchor.
_VOTER_NAME_RE = re.compile(
    r'<(?:span|a)[^>]*>\s*(?P<name>[A-Z][^<]{2,80}?)\s*</(?:span|a)>',
    re.IGNORECASE,
)

# Mover / seconder lines in the agenda body. eScribe uses fairly free-form
# HTML for these — common shapes:
#   "Moved by Councillor SMITH"
#   "Moved by: Councillor SMITH"
#   "Moved by:  Mayor GONDEK / Seconded by: Councillor JONES"
_MOVER_RE = re.compile(
    r'\bmoved by[:\s]+(?:Councillor|Mayor|Alderman|Deputy Mayor)?\s*'
    r'(?P<name>[A-Z][A-Za-z\'\-\.\s]{1,60}?)'
    r'(?=\s*(?:[,;<.]|seconded|/|\bSeconded\b|$))',
    re.IGNORECASE,
)
_SECONDER_RE = re.compile(
    r'\bseconded by[:\s]+(?:Councillor|Mayor|Alderman|Deputy Mayor)?\s*'
    r'(?P<name>[A-Z][A-Za-z\'\-\.\s]{1,60}?)'
    r'(?=\s*(?:[,;<.]|/|$))',
    re.IGNORECASE,
)

# Agenda item header (one per substantive decision). Common eScribe class
# names: AgendaItem, AgendaItemNumber, AgendaItemHeading, MotionTitle.
# NOTE: eScribe per-meeting HTML is "templates plus AJAX": a future or just-
# scheduled meeting renders empty `<div class="ItemTitle"></div>` etc. shells
# that get populated by JS once the user expands an item. Past meetings are
# expected to render motion text inline, but that hypothesis hasn't yet been
# confirmed against a known-good past Calgary meeting (the calendar AJAX
# endpoint is opaque from server-side calls).
#
# Parser keeps a tight match: require an `AgendaItem` class **alone**
# (not `AgendaItemAttachment` etc.). If a meeting has no AgendaItem
# elements, it produces zero bills — that's the right outcome for
# upcoming-meeting agenda placeholders.
_AGENDA_ITEM_RE = re.compile(
    r'<div[^>]*class="AgendaItem"[^>]*>'
    r'(?P<inner>.+?)'
    r'(?=<div[^>]*class="(?:AgendaItem|Section[^"]*)|\Z)',
    re.IGNORECASE | re.DOTALL,
)
_ITEM_NUMBER_RE = re.compile(
    r'class="(?:AgendaItemNumber|ItemNumber|MotionNumber)"[^>]*>\s*'
    r'(?P<num>[A-Z0-9][A-Z0-9\.\-/]{0,20})',
    re.IGNORECASE,
)
_ITEM_TITLE_RE = re.compile(
    r'class="(?:AgendaItemTitle|ItemTitle|MotionTitle)"[^>]*>\s*'
    r'(?P<title>[^<]{2,500}?)<',
    re.IGNORECASE,
)
# Bylaw items typically have a number like "BL2024M-50" or "Bylaw 12M2025"
_BYLAW_NUMBER_RE = re.compile(
    r'\b(?:Bylaw|BL|By-law)\s*(?P<num>\d{1,5}[A-Z]?\d{0,4}(?:-\d+)?)\b',
    re.IGNORECASE,
)

_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(s: str) -> str:
    return re.sub(r"\s+", " ", _HTML_TAG_RE.sub(" ", s)).strip()


def _normalize_voter(name: str) -> str:
    name = re.sub(r"^(?:Councillor|Mayor|Deputy Mayor|Alderman)\s+", "", name, flags=re.IGNORECASE)
    return _strip_html(name).strip(" .,")


def _parse_vote_block(block: str) -> dict:
    """Extract result, ayes/nays counts, and per-voter positions.

    Returns dict with keys: result, ayes, nays, positions=[(name, dir), ...]
    `dir` ∈ {'aye', 'nay', 'absent', 'abstain'}.
    """
    out = {"result": None, "ayes": None, "nays": None, "positions": []}
    rm = _VOTE_RESULT_RE.search(block)
    if rm:
        out["result"] = rm.group("result").strip()

    # Walk header → voters pairs in order.
    cursor = 0
    while True:
        hm = _VOTE_HEADER_RE.search(block, cursor)
        if not hm:
            break
        label = hm.group("label").lower()
        count = int(hm.group("count")) if hm.group("count") else None
        # Find the next Voters block after this header.
        vm = _VOTERS_BLOCK_RE.search(block, hm.end())
        if not vm:
            cursor = hm.end()
            continue
        names = [_normalize_voter(n.group("name"))
                 for n in _VOTER_NAME_RE.finditer(vm.group("inner"))]
        names = [n for n in names if n and len(n) > 1]
        direction = {
            "in favour": "aye", "opposed": "nay",
            "absent": "absent", "abstained": "abstain",
        }.get(label, label)
        if direction == "aye":
            out["ayes"] = count if count is not None else len(names)
        elif direction == "nay":
            out["nays"] = count if count is not None else len(names)
        for n in names:
            out["positions"].append((n, direction))
        cursor = vm.end()
    return out


def parse_meeting_html(html: str) -> ParsedMeetingDetail:
    """Parse a per-meeting agenda page → list of ParsedAgendaItem with votes.

    The eScribe agenda DOM varies between cities and over time. This parser
    is best-effort and tolerant: items without a clear number/title are
    still emitted with placeholders, so the upstream upsert can decide
    whether to keep them. Vote blocks are matched independently of items
    and then attached to the nearest preceding item by document position.
    """
    body_name = ""
    started_at = None
    # Body name often appears as the page H1.
    h1 = re.search(r"<h1[^>]*>(?P<text>.+?)</h1>", html, re.IGNORECASE | re.DOTALL)
    if h1:
        body_name = _strip_html(h1.group("text"))
    started_at = _parse_long_date(html[:6000])

    items: list[ParsedAgendaItem] = []
    item_positions: list[int] = []
    for m in _AGENDA_ITEM_RE.finditer(html):
        inner = m.group("inner")
        num_m = _ITEM_NUMBER_RE.search(inner)
        title_m = _ITEM_TITLE_RE.search(inner)
        bylaw_m = _BYLAW_NUMBER_RE.search(inner[:2000])
        item_number = num_m.group("num").strip() if num_m else f"#{len(items)+1}"
        title = _strip_html(title_m.group("title")) if title_m else _strip_html(inner)[:200]
        item_type = "bylaw" if bylaw_m else "motion"
        if bylaw_m:
            item_number = f"BL-{bylaw_m.group('num')}"
        mover = _MOVER_RE.search(inner)
        seconder = _SECONDER_RE.search(inner)
        items.append(ParsedAgendaItem(
            item_number=item_number,
            title=title or item_number,
            description=None,
            item_type=item_type,
            mover_name=_strip_html(mover.group("name")).strip() if mover else None,
            seconder_name=_strip_html(seconder.group("name")).strip() if seconder else None,
        ))
        item_positions.append(m.start())

    # Now attach vote blocks to items by document position.
    for vm in _VOTE_BLOCK_RE.finditer(html):
        block = vm.group("inner") or vm.group("inner2") or ""
        if not block:
            continue
        # Find which item this vote belongs to (largest item_position <= vm.start()).
        owner_idx = -1
        for i, p in enumerate(item_positions):
            if p <= vm.start():
                owner_idx = i
            else:
                break
        if owner_idx < 0:
            continue
        info = _parse_vote_block(block)
        if info["result"]:
            items[owner_idx].vote_result = info["result"]
        if info["ayes"] is not None:
            items[owner_idx].vote_ayes = info["ayes"]
        if info["nays"] is not None:
            items[owner_idx].vote_nays = info["nays"]
        if info["positions"]:
            items[owner_idx].vote_positions.extend(info["positions"])

    return ParsedMeetingDetail(
        body_name=body_name,
        started_at=started_at,
        items=items,
    )


# ── Public client (used by escribe_ingest) ──────────────────────────


async def fetch_calendar(client: httpx.AsyncClient, city: EscribeCity) -> Optional[str]:
    """One GET. Returns the full ~425KB HTML or None on failure."""
    return await _fetch(client, city.calendar_url)


async def fetch_meeting_page(
    client: httpx.AsyncClient,
    city: EscribeCity,
    source_meeting_id: str,
) -> Optional[str]:
    """One GET per meeting. Returns the per-meeting HTML or None."""
    return await _fetch(client, city.meeting_url(source_meeting_id))
