"""YouTube auto-captions ingester for municipal council meetings.

Pipeline:
  Stage 5 — match_meetings_to_youtube — list a city's official YouTube
            channel via yt-dlp's flat-playlist mode and match each
            council/committee video to a row in `meetings` by date proximity
            + body-name heuristic. Writes the matched URL to
            `meetings.video_url`.

  Stage 6 — fetch_meeting_captions — for each meeting with a video_url
            but no speeches yet, invoke yt-dlp to download the auto-caption
            VTT, parse it into timestamped lines, collapse contiguous
            same-speaker lines into speeches.* rows. Stores the original
            VTT in `speeches.raw_html` so re-parsing doesn't need re-fetch.

  Stage 7 — resolve_meeting_caption_speakers — best-effort name-fuzz
            attribution against the city's Open North roster. Captions
            that look like 'Councillor SMITH:' or 'HER WORSHIP THE MAYOR:'
            get FK'd; otherwise politician_id stays NULL with confidence
            set so the speech remains thematically searchable but not
            speaker-filterable.

The downstream `chunk-and-embed-speeches` pipeline auto-picks up
`level='municipal'` rows (it does not filter by level), so as soon as
speeches land here the embedding corpus extends without further work.

yt-dlp is invoked as an async subprocess. We deliberately do NOT use the
yt-dlp Python API — staying at the subprocess boundary keeps the upgrade
path painless and lets us cap network egress per-call via the --max-downloads
and --socket-timeout flags.
"""
from __future__ import annotations

import asyncio
import hashlib
import html
import json
import logging
import os
import re
import shutil
import tempfile
from dataclasses import dataclass, field as dc_field
from datetime import datetime, timedelta, timezone
from typing import Optional

import orjson

from ..db import Database
from .escribe import CITIES, EscribeCity

log = logging.getLogger(__name__)

YT_DLP_BIN = os.environ.get("YT_DLP_BIN", "yt-dlp")
YT_TIMEOUT_SECS = 180         # per yt-dlp invocation
DEFAULT_RATE_DELAY = 30.0      # seconds between caption fetches (avoid YT throttling)

# Politeness flags for every yt-dlp invocation (2026-08-14 research:
# request pacing + single-connection discipline + exponential retry-sleep
# are what actually prevent 403 attestation blocks; parallelism and big
# flat retries are what trigger them).
YTDLP_POLITE_ARGS = [
    "--sleep-requests", "2",
    "--limit-rate", "3M",
    "--concurrent-fragments", "1",
    "--retries", "4",
    "--fragment-retries", "4",
    "--retry-sleep", "http:exp=10:600",
    "--socket-timeout", "30",
]

# GVS PO-token provider (bgutil sidecar; compose service `pot-provider`).
# YouTube 403s video-format downloads without attestation since 2026-08.
# Unset POT_PROVIDER_URL → flags omitted (captions rarely need a token).
POT_PROVIDER_URL = os.environ.get("POT_PROVIDER_URL", "")
YTDLP_POT_ARGS = (
    [
        "--extractor-args", f"youtubepot-bgutilhttp:base_url={POT_PROVIDER_URL}",
        "--extractor-args", "youtube:fetch_pot=always",
    ]
    if POT_PROVIDER_URL else []
)


# ── Models ──────────────────────────────────────────────────────────


@dataclass
class YoutubeVideo:
    video_id: str
    title: str
    upload_date: Optional[str] = None      # 'YYYYMMDD'
    duration: Optional[int] = None          # seconds


@dataclass
class CaptionLine:
    start_seconds: float
    end_seconds: float
    text: str


@dataclass
class CaptionStats:
    cities_processed: int = 0
    meetings_seen: int = 0
    matched_videos: int = 0
    # attribution kind -> turn count across the run ('macro' / 'recognition'
    # / 'alternation' / 'bare') — the per-layer lift metric.
    attribution_counts: dict = dc_field(default_factory=dict)
    skipped_no_match: int = 0
    captions_fetched: int = 0
    speeches_inserted: int = 0
    speeches_updated: int = 0
    speakers_resolved: int = 0
    speakers_unresolved: int = 0
    parse_warnings: int = 0
    fetch_failures: list[str] = dc_field(default_factory=list)


def _resolve_cities(city_slug: str) -> list[EscribeCity]:
    if city_slug == "all":
        return list(CITIES.values())
    if city_slug not in CITIES:
        raise ValueError(f"unknown city slug {city_slug!r}; known: {list(CITIES)}")
    return [CITIES[city_slug]]


# ── yt-dlp subprocess wrappers ──────────────────────────────────────


async def _run_ytdlp(args: list[str], timeout: int = YT_TIMEOUT_SECS) -> tuple[int, str, str]:
    """Run yt-dlp with given args. Returns (returncode, stdout, stderr)."""
    proc = await asyncio.create_subprocess_exec(
        YT_DLP_BIN, *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return -1, "", f"yt-dlp timeout after {timeout}s"
    return proc.returncode, stdout.decode("utf-8", "replace"), stderr.decode("utf-8", "replace")


async def list_channel_videos(
    channel_url: str, max_videos: int = 200,
) -> list[YoutubeVideo]:
    """List a channel's recent videos via yt-dlp flat-playlist mode.

    Output is one JSON object per line via --print and --print-to-file
    is avoided; we use --print '%(id)s\\t%(title)s\\t%(upload_date)s\\t%(duration)s'
    for compactness.
    """
    args = [
        "--flat-playlist",
        "--ignore-errors",
        "--no-warnings",
        "--socket-timeout", "30",
        "--playlist-end", str(max_videos),
        "--print", "%(id)s\t%(title)s\t%(upload_date)s\t%(duration)s",
        channel_url,
    ]
    rc, out, err = await _run_ytdlp(args, timeout=YT_TIMEOUT_SECS)
    if rc != 0 and not out:
        log.warning("yt-dlp channel-list failed (rc=%s): %s", rc, err.strip()[:300])
        return []
    videos: list[YoutubeVideo] = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) < 2 or not parts[0]:
            continue
        vid_id = parts[0].strip()
        title = parts[1].strip() if len(parts) > 1 else ""
        upload_date = parts[2].strip() if len(parts) > 2 and parts[2] != "NA" else None
        duration = None
        if len(parts) > 3 and parts[3] not in ("NA", ""):
            try:
                duration = int(float(parts[3]))
            except ValueError:
                pass
        videos.append(YoutubeVideo(
            video_id=vid_id, title=title,
            upload_date=upload_date, duration=duration,
        ))
    return videos


def _find_vtt(target_dir: str, video_url: str) -> Optional[str]:
    vid_id = video_url.split("=")[-1].split("&")[0]
    for entry in os.listdir(target_dir):
        if entry.startswith(f"cap-{vid_id}") and entry.endswith(".vtt"):
            return os.path.join(target_dir, entry)
    return None


async def download_auto_captions(
    video_url: str, target_dir: str, languages: tuple[str, ...] = ("en.*",),
) -> Optional[tuple[str, str]]:
    """Download English captions for one video, preferring human-authored
    tracks over YouTube ASR. Returns (path-to-vtt, track_kind) where
    track_kind is 'manual' or 'auto', or None on failure.

    Edmonton (and other cities that pipe their broadcast encoder into
    YouTube) carry the live stenography track as a *manual* subtitle with a
    generated language tag like ``en-uYU-mmqFLq8`` — hence the ``en.*``
    wildcard rather than a fixed language list.
    """
    output_template = os.path.join(target_dir, "cap-%(id)s.%(ext)s")
    base = [
        "--skip-download",
        "--sub-langs", ",".join(languages),
        "--convert-subs", "vtt",
        "--no-warnings",
        *YTDLP_POLITE_ARGS,
        "-o", output_template,
        video_url,
    ]
    # Pass 1: human/CC tracks. rc can be nonzero on partial successes, so
    # always look for the file regardless.
    rc, out, err = await _run_ytdlp(["--write-subs", *base], timeout=YT_TIMEOUT_SECS)
    path = _find_vtt(target_dir, video_url)
    if path:
        return path, "manual"
    # Pass 2: auto-captions fallback.
    rc, out, err = await _run_ytdlp(["--write-auto-subs", *base], timeout=YT_TIMEOUT_SECS)
    if rc != 0:
        log.info("yt-dlp captions failed for %s (rc=%s): %s", video_url, rc, err.strip()[:300])
    path = _find_vtt(target_dir, video_url)
    if path:
        return path, "auto"
    return None


# ── VTT parser ──────────────────────────────────────────────────────


# WEBVTT cue format:
#   00:01:23.456 --> 00:01:25.789
#   Caption text line 1
#   Caption text line 2
#
# Auto-captions also include positioning info on the timestamp line; we
# strip that. Auto-caption rolling-display duplicates lines across cues,
# so we de-dup on text after parsing.
_VTT_TS_RE = re.compile(
    r"^(?P<sh>\d+):(?P<sm>\d{2}):(?P<ss>\d{2})\.(?P<sms>\d{3})"
    r"\s+-->\s+"
    r"(?P<eh>\d+):(?P<em>\d{2}):(?P<es>\d{2})\.(?P<ems>\d{3})"
)
_VTT_TAG_RE = re.compile(r"<[^>]+>")


def _ts_to_seconds(h: str, m: str, s: str, ms: str) -> float:
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def parse_vtt(vtt_text: str) -> list[CaptionLine]:
    """Parse a WebVTT string into a deduped CaptionLine list, in time order.

    Roll-up captions (both YouTube ASR and broadcast CC re-encodes) repeat
    each display line across successive cues: a cue typically shows the
    previous line as plain text plus the new line with ``<c>`` word timing,
    and the next cue repeats the new line plain. We therefore emit one
    CaptionLine per *display line*, timestamped at the first cue where it
    appears, deduping only against a small rolling window of recent lines —
    NOT a global set, which would silently drop legitimately repeated
    short lines ("THANK YOU." ×100 across a 7-hour meeting).

    Text is HTML-unescaped: broadcast CC tracks encode the ``>>``
    speaker-turn marker as ``&gt;&gt;``.
    """
    out: list[CaptionLine] = []
    recent: list[str] = []  # last few emitted texts (rolling-window dedup)
    cur_start: Optional[float] = None
    cur_end: Optional[float] = None

    def emit(raw_line: str) -> None:
        text = _VTT_TAG_RE.sub("", raw_line)
        text = html.unescape(text)
        text = re.sub(r"\s+", " ", text).strip()
        if not text or cur_start is None:
            return
        if text in recent:
            return
        recent.append(text)
        del recent[:-4]
        out.append(CaptionLine(
            start_seconds=cur_start, end_seconds=cur_end or cur_start, text=text,
        ))

    for raw in vtt_text.splitlines():
        line = raw.strip("﻿").rstrip()
        if not line:
            cur_start = cur_end = None
            continue
        m = _VTT_TS_RE.match(line)
        if m:
            cur_start = _ts_to_seconds(m.group("sh"), m.group("sm"), m.group("ss"), m.group("sms"))
            cur_end = _ts_to_seconds(m.group("eh"), m.group("em"), m.group("es"), m.group("ems"))
            continue
        if line.upper() in ("WEBVTT", "NOTE") or line.startswith(("NOTE ", "WEBVTT")):
            continue
        # Skip cue identifiers (bare tokens between cues).
        if cur_start is None and re.fullmatch(r"[A-Za-z0-9_\-]+", line):
            continue
        emit(line)
    return out


# ── Speech construction (collapse + attribute) ─────────────────────


# Caption-text speaker-prefix patterns. eScribe + YouTube auto-captions
# from Canadian council channels typically render speaker IDs as one of:
#   "MAYOR GONDEK:"
#   "Councillor Smith:"
#   ">> Councillor Smith:"
#   "MS. JONES:"
#   ">> CHAIRMAN:"
# Auto-captions sometimes drop the speaker label entirely on continuation;
# we treat unlabelled blocks as continuations of the previous speaker.
_SPEAKER_TURN_RE = re.compile(
    r"^(?:>>+\s*)?"
    r"(?P<role>Mayor|Councillor|Madam Chair|Chair|Chairman|Chairperson|"
    r"Deputy Mayor|Alderman|Acting Mayor|Her Worship|His Worship|"
    r"Mr\.|Ms\.|Mrs\.|Dr\.|Sir|Madam)?\s*"
    r"(?P<name>[A-Z][A-Z'\-\s]{1,40})"
    r"\s*[:\-–]\s+"
    r"(?P<rest>.+)$",
    re.IGNORECASE,
)


@dataclass
class CaptionSpeech:
    speaker_role: Optional[str]
    speaker_name_raw: str
    text: str
    start_seconds: float
    end_seconds: float
    # How the speaker was identified: 'macro' (steno name macro after '>>'),
    # 'recognition' (chair recognized the speaker just before the turn),
    # or None (unattributed). Drives stage-7 confidence tiers.
    attribution: Optional[str] = None


def collapse_captions_into_speeches(lines: list[CaptionLine]) -> list[CaptionSpeech]:
    """Walk caption lines, detect speaker-turn boundaries, collapse contiguous
    text into speech rows.
    """
    speeches: list[CaptionSpeech] = []
    cur_role: Optional[str] = None
    cur_name: Optional[str] = "UNATTRIBUTED"
    cur_text: list[str] = []
    cur_start: Optional[float] = None
    cur_end: Optional[float] = None

    def flush():
        nonlocal cur_text, cur_start, cur_end
        if cur_start is None or not cur_text:
            return
        text = " ".join(cur_text).strip()
        text = re.sub(r"\s+", " ", text)
        if len(text) < 3:
            cur_text = []
            return
        speeches.append(CaptionSpeech(
            speaker_role=cur_role,
            speaker_name_raw=cur_name or "UNATTRIBUTED",
            text=text,
            start_seconds=cur_start,
            end_seconds=cur_end or cur_start,
        ))
        cur_text = []
        cur_start = cur_end = None

    for line in lines:
        m = _SPEAKER_TURN_RE.match(line.text.strip())
        if m:
            # Speaker turn boundary.
            flush()
            role = m.group("role")
            name_token = m.group("name").strip().rstrip(":-– ")
            cur_role = role.strip() if role else None
            cur_name = name_token
            cur_text = [m.group("rest").strip()]
            cur_start = line.start_seconds
            cur_end = line.end_seconds
        else:
            if cur_start is None:
                cur_start = line.start_seconds
            cur_end = line.end_seconds
            cur_text.append(line.text)
    flush()
    return speeches


# ── CC-turn collapse (broadcast stenography convention) ─────────────


# Broadcast CC (live stenography re-encoded by YouTube) marks every speaker
# turn with '>>'. The steno operator has *name macros* only for recurring
# speakers — Edmonton renders them mixed-case in an otherwise ALL-CAPS
# transcript: '>> Mayor Andrew Knack:', '>> The Chair:', '>> The Clerk:'.
# Everyone else gets a bare '>>'; who they are is carried by the chair's
# recognition immediately beforehand ('COUNCILLOR PRINCIPE.' → '>> GOOD
# MORNING.').
_CC_TURN_RE = re.compile(r"^>>+\s*(?:(?P<label>[^:]{1,60}):\s*)?(?P<rest>.*)$")

# A recognition names the next speaker in the chair's turn. Two shapes:
#   trailing:  '... COUNCILLOR PRINCIPE.'  (name ends the turn; queue
#              readouts like 'COUNCILLOR WRIGHT, COUNCILLOR PARMAR.' name
#              several — the LAST-named speaks first)
#   invited:   '... COUNCILLOR SALVADOR, DO YOU HAVE QUESTIONS?' /
#              'THANK YOU, COUNCILLOR SALVADOR, IF YOU WANT TO PUT THE
#              MOTION ON THE FLOOR' (name mid-tail, followed by an
#              invitation clause)
# COUNSELLOR is a recurring live-steno spelling of Councillor.
_CC_NAME_MENTION_RE = re.compile(
    r"(?P<role>COUNCILLOR|COUNSELLOR|MAYOR)\s+(?P<name>[A-Z][A-Z'\-]+)",
    re.IGNORECASE,
)

# Clause after the name that turns a mention into a hand-off.
_CC_INVITATION_RE = re.compile(
    r"\b(?:go ahead|you have the floor|the floor is yours|proceed"
    r"|do you have|has (?:a )?questions?|any (?:other |further )?questions"
    r"|your (?:thoughts|questions|turn)"
    r"|you'?re (?:up|next)|to close|if you (?:want|would like)|would you like"
    r"|please|first|next|to speak|to move|wrap us up)\b",
    re.IGNORECASE,
)

# Mention prefixes that *reference* a member rather than hand them the
# floor: motion attributions ('SECONDED BY COUNCILLOR PARMAR.') and — when
# nothing invitational follows — turn-closers ('THANK YOU, COUNCILLOR
# PAQUETTE.').
_CC_REFERENCE_PREFIX_RE = re.compile(
    r"(?:MOVED|SECONDED|CARRIED|SUPPORTED|OPPOSED|REQUESTED|INTRODUCED)\s+BY\s*$",
    re.IGNORECASE,
)
_CC_THANK_YOU_PREFIX_RE = re.compile(r"THANK\s+YOU,?\s*$|SORRY,?\s*$", re.IGNORECASE)

# "MY NAME IS LISA DRURY AND …" — capture 2-3 name tokens, stopping at
# connectives so trailing prose doesn't ride along.
_SELF_INTRO_RE = re.compile(
    r"\bMY NAME IS\s+(?P<name>[A-Z][A-Z'\-]+"
    r"(?:\s+(?!AND\b|I\b|I'M\b|FROM\b|WITH\b|OF\b|THE\b|HERE\b|SPEAKING\b"
    r"|IN\b|ON\b|AT\b|FOR\b"
    r"|EXECUTIVE\b|DIRECTOR\b|PRESIDENT\b|CHAIR\b|CEO\b|MANAGER\b|COORDINATOR\b)"
    r"[A-Z][A-Z'\-]+){1,2})",
    re.IGNORECASE,
)

_CC_ROLE_LABELS = {
    "the chair": "Chair",
    "chair": "Chair",
    "the clerk": "Clerk",
    "the city clerk": "Clerk",
    "interpreter": "Interpreter",
}


def _cc_recognized_speaker(prev_text_tail: str) -> Optional[tuple[str, str]]:
    """If the previous turn hands the floor to a member, return
    (role, NAME); else None. See the shape notes above _CC_NAME_MENTION_RE."""
    tail = prev_text_tail[-160:]
    mentions = list(_CC_NAME_MENTION_RE.finditer(tail))
    if not mentions:
        return None
    m = mentions[-1]  # queue readouts: last-named speaks first
    prefix = tail[max(0, m.start() - 30):m.start()]
    suffix = tail[m.end():].strip()
    if _CC_REFERENCE_PREFIX_RE.search(prefix):
        return None
    trailing_only_punct = re.fullmatch(r"[.,!?;:'\")\]]*", suffix) is not None
    if trailing_only_punct:
        # Bare trailing mention: a recognition — unless it closes the
        # speaker's own turn ('THANK YOU, COUNCILLOR PAQUETTE.').
        if _CC_THANK_YOU_PREFIX_RE.search(prefix):
            return None
    else:
        # Mid-tail mention: only a hand-off when an invitation follows.
        if not _CC_INVITATION_RE.search(suffix):
            return None
    role = m.group("role").title()
    if role == "Counsellor":
        role = "Councillor"
    return role, m.group("name").upper()


def collapse_cc_turns(
    lines: list[CaptionLine], panel_owner_at=None,
) -> list[CaptionSpeech]:
    """Collapse '>>'-marked broadcast-CC captions into speeches.

    Attribution per turn, best-first:
      - named steno macro after '>>'  → attribution='macro'
      - chair recognition at the tail of the previous turn → 'recognition'
      - otherwise UNATTRIBUTED (None)
    """
    speeches: list[CaptionSpeech] = []
    cur_role: Optional[str] = None
    cur_name: str = "UNATTRIBUTED"
    cur_attr: Optional[str] = None
    cur_text: list[str] = []
    cur_start: Optional[float] = None
    cur_end: Optional[float] = None

    def flush():
        nonlocal cur_text
        if cur_start is None or not cur_text:
            cur_text = []
            return
        text = re.sub(r"\s+", " ", " ".join(cur_text)).strip()
        if len(text) < 3:
            cur_text = []
            return
        role, name, attr = cur_role, cur_name, cur_attr
        # Roll-call relay guard: a short recognized turn that itself says
        # "…from Councillor <other member>" is someone relaying a remote
        # member's greeting, not the recognized member speaking
        # ("And good morning from Councillor Wright.").
        if attr == "recognition" and len(text.split()) <= 12:
            fm = re.search(
                r"\bFROM\s+(?:COUNCILLOR|COUNSELLOR|MAYOR)\s+([A-Z][A-Z'\-]+)",
                text, re.IGNORECASE,
            )
            if fm and fm.group(1).upper() != name.upper():
                role, name, attr = None, "UNATTRIBUTED", None
        # Self-introduction naming: public-hearing speakers open with
        # "my name is X" — name the turn (display-level; these are members
        # of the public, so stage 7 must NOT roster-match them).
        if attr is None and name == "UNATTRIBUTED":
            si = _SELF_INTRO_RE.search(text[:160])
            if si:
                name = si.group("name").title()
                attr = "self_intro"
        speeches.append(CaptionSpeech(
            speaker_role=role, speaker_name_raw=name, text=text,
            start_seconds=cur_start, end_seconds=cur_end or cur_start,
            attribution=attr,
        ))
        cur_text = []

    for line in lines:
        text = line.text.strip()
        m = _CC_TURN_RE.match(text)
        if m:
            prev_tail = " ".join(cur_text[-3:]) if cur_text else ""
            flush()
            cur_start = line.start_seconds
            cur_end = line.end_seconds
            label = (m.group("label") or "").strip()
            rest = (m.group("rest") or "").strip()
            if label:
                low = label.lower()
                if low in _CC_ROLE_LABELS:
                    cur_role = _CC_ROLE_LABELS[low]
                    cur_name = label
                else:
                    # 'Mayor Andrew Knack' — split role prefix if present.
                    parts = label.split(None, 1)
                    if parts and parts[0].lower() in (
                        "mayor", "councillor", "deputy", "acting",
                    ) and len(parts) > 1:
                        cur_role = parts[0].title()
                        cur_name = parts[1]
                    else:
                        cur_role = None
                        cur_name = label
                cur_attr = "macro"
            else:
                rec = _cc_recognized_speaker(prev_tail)
                if rec:
                    cur_role, cur_name = rec
                    cur_attr = "recognition"
                else:
                    cur_role = None
                    cur_name = "UNATTRIBUTED"
                    cur_attr = None
            if rest:
                cur_text.append(rest)
        else:
            if cur_start is None:
                cur_start = line.start_seconds
            cur_end = line.end_seconds
            cur_text.append(text)
    flush()
    _apply_block_alternation(speeches, panel_owner_at=panel_owner_at)
    return speeches


# ── Block-alternation resolver (question-period structure) ─────────
#
# Committee/council question periods have rigid structure: the chair
# recognizes a member, then the exchange alternates member ↔ staff until
# the chair's next turn ("Thank you, Councillor X. Councillor Y?"). The
# steno marks every turn with '>>' but names neither side, so these turns
# land bare. We recover the member side deterministically:
#
#   - block = run of bare turns following a recognition-attributed turn
#   - anchors inside the block re-sync parity:
#       · a turn opening by addressing the OWNER by name → staff
#         ("Thank you, Councillor Parmar. From our understanding…")
#       · a turn opening by thanking the chair/mayor, or noting the
#         countdown ("I'm out of time") → owner
#       · a turn opening by thanking a DIFFERENT member → block ends
#   - between consecutive anchors, fill by strict alternation ONLY when
#     the anchors' parity is consistent; otherwise leave that gap NULL
#     (steno double-'>>' glitches produce same-speaker adjacent turns —
#     conservative beats wrong)
#
# Owner turns get attribution='alternation' (stage-7 confidence 0.65);
# staff turns stay politician_id=NULL by design.

_CC_BLOCK_MAX = 60

_CC_ADDRESSES_MEMBER_RE = re.compile(
    r"^\s*(?:THANK YOU|THANKS|GOOD MORNING|GOOD AFTERNOON|GOOD EVENING)[,.!]?\s*"
    r"(?:COUNCILLOR|COUNSELLOR|MAYOR)\s+(?P<name>[A-Z][A-Z'\-]+)",
    re.IGNORECASE,
)
_CC_ADDRESSES_CHAIR_RE = re.compile(
    r"^\s*(?:THANK YOU|THANKS)[,.!]?\s*"
    r"(?:(?:MAYOR|MADAM CHAIR|MR\.? CHAIR|CHAIR|YOUR WORSHIP)\b|(?:THROUGH THE CHAIR))",
    re.IGNORECASE,
)
_CC_OUT_OF_TIME_RE = re.compile(r"\b(?:I'?M|I AM)\s+OUT OF TIME\b", re.IGNORECASE)


def _apply_block_alternation(
    speeches: list[CaptionSpeech],
    panel_owner_at=None,
) -> int:
    """Attribute owner-side turns inside question-period blocks. Mutates
    the list in place; returns the number of turns attributed.

    Blocks open in two ways:
      - a 'recognition'-attributed turn (text grammar) — owner-side fills
        get attribution='alternation';
      - when text recognition failed, ``panel_owner_at(start_seconds)``
        (the clerk-panel OCR timeline, when available) can supply the
        floor owner for a bare turn that follows an attributed turn —
        that turn and the block's owner-side fills get attribution='panel'.
        NOTE the panel names the floor OWNER, not the turn-level speaker:
        the member's countdown ticks through staff answers, so the panel
        must feed this alternation engine, never attribute turns directly.
    """
    changed = 0
    n = len(speeches)
    i = 0
    while i < n:
        fill_attr = "alternation"
        if speeches[i].attribution == "recognition":
            pass
        elif (
            panel_owner_at is not None
            and speeches[i].attribution is None
            and speeches[i].speaker_name_raw == "UNATTRIBUTED"
            and (i == 0 or speeches[i - 1].attribution is not None)
        ):
            owner = panel_owner_at(speeches[i].start_seconds)
            if owner is None:
                i += 1
                continue
            speeches[i].speaker_role = "Councillor"
            speeches[i].speaker_name_raw = owner
            speeches[i].attribution = "panel"
            changed += 1
            fill_attr = "panel"
        else:
            i += 1
            continue
        owner_name = speeches[i].speaker_name_raw
        owner_role = speeches[i].speaker_role

        block: list[int] = []
        j = i + 1
        while j < n and speeches[j].attribution is None and len(block) < _CC_BLOCK_MAX:
            block.append(j)
            j += 1

        # Anchor detection (with hard block-break on a hand-off to another
        # member). A fourth anchor class, 'chair', covers the chair's short
        # un-macro'd procedural prompts ("Thank you. Do you have a motion
        # please go ahead.") — without it the alternation phase inverts and
        # credits the chair's prompts to the member (bug found by the
        # diarization cross-check, seq 248-262 of the 2026-08-12 Exec mtg).
        anchors: list[tuple[int, str]] = [(i, "owner")]
        kept: list[int] = []
        for k in block:
            head = speeches[k].text[:80]
            m = _CC_ADDRESSES_MEMBER_RE.match(head)
            if m:
                if m.group("name").upper() == owner_name.upper():
                    anchors.append((k, "staff"))
                    kept.append(k)
                    continue
                break  # addresses a different member — block over
            if _CC_ADDRESSES_CHAIR_RE.match(head) or _CC_OUT_OF_TIME_RE.search(head):
                anchors.append((k, "owner"))
            elif (
                len(speeches[k].text.split()) <= 35
                and _CC_INVITATION_RE.search(speeches[k].text)
            ):
                anchors.append((k, "chair"))
            kept.append(k)

        # Panel-opened blocks carry extra risk: the panel names the FLOOR
        # OWNER, but after a chair hand-off to a non-roster party (staff
        # team, delegation) the actual speakers aren't the owner at all —
        # the owner's clock keeps running either way. Require at least one
        # independent in-block anchor (a turn addressing the owner or the
        # chair) before trusting a panel-supplied owner; otherwise revert
        # the opener and skip the block.
        if fill_attr == "panel" and len(anchors) <= 1:
            speeches[i].speaker_role = None
            speeches[i].speaker_name_raw = "UNATTRIBUTED"
            speeches[i].attribution = None
            changed -= 1
            i = j if block else i + 1
            continue

        # Interpolate between parity-consistent anchors; extrapolate past
        # the last anchor to the block end. 'chair' anchors stay
        # unattributed themselves and reset the phase: the turn after a
        # chair prompt is the member speaking.
        labels: dict[int, str] = {
            k: lab for k, lab in anchors if k != i and lab != "chair"
        }

        def _step(label: str) -> str:
            # Who speaks after `label` under strict alternation.
            return "staff" if label == "owner" else "owner"

        def _predict(base_label: str, distance: int) -> str:
            lab = base_label
            for _ in range(distance):
                lab = _step(lab)
            return lab

        for (a, la), (b, lb) in zip(anchors, anchors[1:]):
            if lb != "chair" and _predict(la, b - a) != lb:
                continue  # glitched parity — leave the gap unattributed
            for k in kept:
                if a < k < b:
                    labels[k] = _predict(la, k - a)
        # Trailing extrapolation past the last anchor — text-anchored
        # blocks only; panel-opened blocks fill just the anchor-bracketed
        # segments.
        if fill_attr != "panel":
            last_a, last_la = anchors[-1]
            for k in kept:
                if k > last_a:
                    labels[k] = _predict(last_la, k - last_a)

        for k, lab in labels.items():
            if lab == "owner" and speeches[k].attribution is None:
                speeches[k].speaker_role = owner_role
                speeches[k].speaker_name_raw = owner_name
                speeches[k].attribution = fill_attr
                changed += 1
        i = j if block else i + 1
    return changed


def looks_like_cc_turn_captions(lines: list[CaptionLine], min_markers: int = 40) -> bool:
    """True when the caption stream uses the '>>' turn convention densely
    enough for turn-based collapsing to beat the label-regex collapse."""
    return sum(1 for ln in lines if ln.text.lstrip().startswith(">>")) >= min_markers


# The clerk panel leads captions by ~7-10s (arms at recognition ~2-3s
# before speech; CART captions lag audio ~5s), so a caption turn is probed
# against the timeline at start+8s, clear of the interval's leading edge.
_PANEL_PROBE_LEAD_SECS = 8.0
_PANEL_START_MARGIN_SECS = 5.0


def make_panel_owner_lookup(timeline: Optional[dict]):
    """Build a ``f(caption_start_seconds) -> SURNAME | None`` lookup from a
    meetings.raw->'speaker_timeline' JSON (see edmonton_panel_ocr). Returns
    None when no usable timeline exists. Surnames are upper-cased to match
    the recognition-machinery convention."""
    if not timeline:
        return None
    speaking = [
        iv for iv in timeline.get("intervals", [])
        if iv.get("state") == "speaking" and iv.get("name")
    ]
    if not speaking:
        return None

    def lookup(start_seconds: float) -> Optional[str]:
        probe = start_seconds + _PANEL_PROBE_LEAD_SECS
        for iv in speaking:
            if iv["start"] + _PANEL_START_MARGIN_SECS <= probe <= iv["end"]:
                return iv["name"].split()[-1].upper()
        return None

    return lookup


# ── Truecasing (broadcast CC is transmitted ALL CAPS) ───────────────


# Words that should keep a capital regardless of position. Lowercase key →
# cased form. Deliberately small: sentence-casing does most of the work and
# roster names are merged in per-city at runtime. Unknown proper nouns
# (companies, street names) come out lowercase — grow this list as they
# annoy, or leave them; the raw VTT is preserved so re-truecasing is a
# reparse away, never a refetch.
_STATIC_PROPER: dict[str, str] = {
    **{m.lower(): m for m in (
        "January", "February", "March", "April", "May", "June", "July",
        "August", "September", "October", "November", "December",
        "Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
        "Saturday", "Sunday",
        "Edmonton", "Alberta", "Calgary", "Ottawa", "Canada", "Canadian",
        "Canadians", "Albertans", "Edmontonians",
        "Treaty", "Métis", "Metis", "Cree", "Inuit", "Papaschase",
        "God",
    )},
}

# Abbreviations whose trailing period does not end a sentence.
_NON_TERMINAL_ABBREV = {"a.m", "p.m", "mr", "ms", "mrs", "dr", "vs", "no", "st", "e.g", "i.e"}

_SENTENCE_END_TAIL_RE = re.compile(r"[.!?]['\")\]]*$")
_ROLE_BEFORE_NAME_RE = re.compile(r"\b(councillor|mayor|chair)(\s+[A-Z])")


async def _load_truecase_dictionary(db: Database, city: EscribeCity) -> dict[str, str]:
    """Static proper nouns + the city's roster name tokens (so 'knack' →
    'Knack', 'jo-anne' → 'Jo-Anne')."""
    out = dict(_STATIC_PROPER)
    council_slug = f"opennorth:{city.slug}-city-council:"
    rows = await db.fetch(
        """
        SELECT name FROM politicians
        WHERE level = 'municipal' AND province_territory = $1 AND source_id LIKE $2
        """,
        city.province_territory, council_slug + "%",
    )
    for r in rows:
        for token in (r["name"] or "").split():
            token = token.strip(".,")
            if len(token) >= 2:
                out[token.lower()] = token
    return out


def truecase_caption_text(text: str, proper: dict[str, str]) -> str:
    """Sentence-case an ALL-CAPS broadcast-CC string.

    Leaves already-mixed-case text untouched (auto-captions, macro labels),
    so it is safe to apply unconditionally.
    """
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return text
    if sum(c.isupper() for c in letters) / len(letters) < 0.7:
        return text

    out: list[str] = []
    cap_next = True
    for w in text.lower().split():
        core = w.strip(".,!?;:()\"'“”‘’[]")
        if core in proper:
            replaced = w.replace(core, proper[core], 1)
        elif core == "i" or core.startswith("i'"):
            replaced = w.replace("i", "I", 1)
        elif cap_next:
            replaced = w
            for idx, ch in enumerate(w):
                if ch.isalpha():
                    replaced = w[:idx] + ch.upper() + w[idx + 1:]
                    break
        else:
            replaced = w
        out.append(replaced)
        cap_next = bool(
            _SENTENCE_END_TAIL_RE.search(w)
            and not any(ch.isdigit() for ch in w)
            and core not in _NON_TERMINAL_ABBREV
        )
    result = " ".join(out)
    # 'councillor rutherford' → 'Councillor Rutherford' (title before a
    # roster-cased name reads as a proper title).
    result = _ROLE_BEFORE_NAME_RE.sub(lambda m: m.group(1).title() + m.group(2), result)
    return result


# ── DB writers ──────────────────────────────────────────────────────


# The Open North roster in `politicians` is CURRENT-membership only. Using
# it against meetings from an earlier council term would produce confident
# wrong FKs — e.g. every ">> Mayor …" macro in a 2021-2025 Edmonton meeting
# would resolve to Andrew Knack at 0.9 when the mayor was Amarjeet Sohi
# (2026-08-14 review, fragility B5; ~500 meetings of the planned backfill).
# Until a dated-roster ingest exists (Socrata yqff-55ja + minutes
# attendance — backfill-prep work), every roster-based resolution step must
# REFUSE to match for meetings before the current term.
def _roster_valid_for(city_slug: str, when) -> bool:
    from .edmonton_socrata import _TERM_SESSIONS
    if when is None:
        return False
    current_start = _TERM_SESSIONS["2025-2029"][2]
    d = when.date() if hasattr(when, "date") else when
    return d >= current_start


async def roster_for_date(
    db: Database, city: EscribeCity, when,
) -> Optional[tuple[dict[str, str], Optional[str]]]:
    """(SURNAME → politician_id, mayor_id) valid at `when`.

    Current term → the live Open North roster; earlier dates → the dated
    politician_terms rows from ingest-edmonton-roster-history (2004→2021
    elections). None when no roster covers the date — callers must then
    refuse to attribute rather than guess.
    """
    if when is None:
        return None
    d = when.date() if hasattr(when, "date") else when
    if _roster_valid_for(city.slug, when):
        roster = await _load_council_roster(db, city)
        mayor = await _find_mayor(db, city)
        return (roster, mayor) if roster else None
    rows = await db.fetch(
        """
        SELECT p.id::text AS id, p.name, p.last_name, t.office
        FROM politician_terms t
        JOIN politicians p ON p.id = t.politician_id
        WHERE t.level = 'municipal' AND t.province_territory = $1
          AND (p.source_id LIKE 'opennorth:' || $2 || '-city-council:%'
               OR p.source_id LIKE 'edmonton-socrata:%')
          AND t.started_at <= $3::date
          AND (t.ended_at IS NULL OR t.ended_at > $3::date)
        """,
        city.province_territory, city.slug, d,
    )
    if not rows:
        return None
    roster: dict[str, str] = {}
    mayor: Optional[str] = None
    for r in rows:
        last = (r["last_name"] or "").strip() or (r["name"].split()[-1] if r["name"] else "")
        if last:
            roster[last.upper()] = r["id"]
        if (r["office"] or "").lower() == "mayor":
            mayor = r["id"]
    return (roster, mayor) if roster else None


async def _load_council_roster(db: Database, city: EscribeCity) -> dict[str, str]:
    """Map UPPERCASE-surname → politician_id for the city's Open North roster."""
    council_slug = f"opennorth:{city.slug}-city-council:"
    rows = await db.fetch(
        """
        SELECT id::text AS id, name, last_name, elected_office
        FROM politicians
        WHERE level = 'municipal'
          AND province_territory = $1
          AND source_id LIKE $2
        """,
        city.province_territory, council_slug + "%",
    )
    out: dict[str, str] = {}
    for r in rows:
        last = (r["last_name"] or "").strip() or (r["name"].split()[-1] if r["name"] else "")
        if last:
            out[last.upper()] = r["id"]
    return out


async def _find_mayor(db: Database, city: EscribeCity) -> Optional[str]:
    """Return politician_id of the city's current mayor (Open North roster)."""
    council_slug = f"opennorth:{city.slug}-city-council:"
    row = await db.fetchrow(
        """
        SELECT id::text AS id FROM politicians
        WHERE level = 'municipal'
          AND province_territory = $1
          AND source_id LIKE $2
          AND elected_office ILIKE 'mayor%'
        LIMIT 1
        """,
        city.province_territory, council_slug + "%",
    )
    return row["id"] if row else None


def _content_hash(s: str) -> str:
    return hashlib.sha256(re.sub(r"\s+", " ", s).strip().lower().encode("utf-8")).hexdigest()


async def _upsert_speech(
    db: Database, *,
    session_id: str, city: EscribeCity, meeting_id: str,
    politician_id: Optional[str], confidence: float,
    speaker_name_raw: str, speaker_role: Optional[str],
    speech_type: str,
    spoken_at: datetime, sequence: int, text: str,
    source_url: str, source_anchor: str,
    raw_payload: dict, raw_vtt: Optional[str],
) -> bool:
    """Insert or update one speech row. Returns True if newly inserted."""
    word_count = len(text.split())
    chash = _content_hash(text)
    row = await db.fetchrow(
        """
        INSERT INTO speeches (
            session_id, politician_id, level, province_territory,
            speaker_name_raw, speaker_role, party_at_time, constituency_at_time,
            confidence, speech_type, spoken_at, sequence, language,
            text, word_count,
            source_system, source_url, source_anchor,
            raw, raw_html, content_hash, meeting_id
        ) VALUES (
            $1::uuid, $2, 'municipal', $3,
            $4, $5, NULL, NULL,
            $6, $7, $8, $9, 'en',
            $10, $11,
            $12, $13, $14,
            $15::jsonb, $16, $17, $18::uuid
        )
        ON CONFLICT (source_system, source_url, sequence) DO UPDATE SET
            politician_id    = EXCLUDED.politician_id,
            speaker_name_raw = EXCLUDED.speaker_name_raw,
            speaker_role     = EXCLUDED.speaker_role,
            confidence       = EXCLUDED.confidence,
            spoken_at        = EXCLUDED.spoken_at,
            text             = EXCLUDED.text,
            word_count       = EXCLUDED.word_count,
            raw              = EXCLUDED.raw,
            content_hash     = EXCLUDED.content_hash,
            updated_at       = now()
        RETURNING (xmax = 0) AS inserted
        """,
        session_id,
        politician_id,
        city.province_territory,
        speaker_name_raw[:200],
        speaker_role,
        confidence,
        speech_type,
        spoken_at,
        sequence,
        text,
        word_count,
        f"{city.source_system.split('-')[0]}-youtube-captions",
        source_url,
        source_anchor,
        orjson.dumps(raw_payload).decode(),
        raw_vtt,  # only set on the sequence=1 row; subsequent rows pass None
        chash,
        meeting_id,
    )
    return bool(row["inserted"])


# ── Stage 5: match_meetings_to_youtube ─────────────────────────────


# Stream-VOD titles on Canadian council channels carry the meeting date and
# body verbatim: 'July 7, 2026 - City Council - Public Hearing'. This is the
# join key against the structured meetings spine — flat-playlist mode returns
# upload_date as NA, so the title date is authoritative.
# Tolerant of the title sloppiness observed on the real channels:
# 'Apr 25, 2023' (abbreviated month), 'June11, 2025' (missing space),
# '2025 -City Council' (no space after the dash).
_TITLE_DATE_RE = re.compile(
    r"^(?P<month>[A-Z][a-z]+)\.?\s*(?P<day>\d{1,2}),?\s+(?P<year>\d{4})\s*[-–]\s*(?P<body>.+)$",
)

# Qualifier noise appended to the body in video titles (and occasionally in
# Socrata meeting_type): parenthesized annotations plus scheduling words.
_TITLE_QUALIFIER_RE = re.compile(
    r"\([^)]*\)"
    r"|\b(?:continuation|continued|part\s*\d+|day\s*\d+"
    r"|non\s*-?\s*regular|orientation|virtual|from\s+\w+\s+room)\b",
    re.IGNORECASE,
)


def _parse_stream_title(title: str) -> Optional[tuple]:
    """'July 7, 2026 - City Council - Public Hearing' → (date, body-string)."""
    m = _TITLE_DATE_RE.match(title.strip())
    if not m:
        return None
    stamp = f"{m.group('month')} {m.group('day')} {m.group('year')}"
    d = None
    for fmt in ("%B %d %Y", "%b %d %Y"):
        try:
            d = datetime.strptime(stamp, fmt).date()
            break
        except ValueError:
            continue
    if d is None:
        return None
    return d, m.group("body").strip()


def _squash_body(s: str) -> str:
    """Normalize a body name for comparison: lowercase alnum only, with the
    'special ' prefix dropped ('Special City Council' ≡ video 'Special City
    Council' but Socrata sometimes files it under the plain body)."""
    s = re.sub(r"^\s*special\s+", "", s, flags=re.IGNORECASE)
    return re.sub(r"[^a-z0-9]", "", s.lower())


async def match_meetings_to_youtube(
    db: Database, *, city_slug: str = "all", limit: Optional[int] = None,
    max_channel_videos: int = 800,
) -> CaptionStats:
    """Stage 5 — attach channel stream VODs to meetings rows by
    (title-date, normalized body name). Meetings come from the structured
    spine (Socrata for Edmonton); videos from every configured room channel.
    """
    stats = CaptionStats()
    for city in _resolve_cities(city_slug):
        if not city.youtube_channels:
            continue
        videos: list[YoutubeVideo] = []
        for channel in city.youtube_channels:
            got = await list_channel_videos(channel, max_videos=max_channel_videos)
            log.info("youtube match: city=%s channel=%s videos=%d",
                     city.slug, channel, len(got))
            if not got:
                stats.fetch_failures.append(f"channel:{channel}")
            videos.extend(got)
        if not videos:
            continue
        stats.cities_processed += 1

        rows = await db.fetch(
            """
            SELECT id::text AS id, body_name, video_url,
                   (started_at AT TIME ZONE 'America/Edmonton')::date AS local_date
            FROM meetings
            WHERE source_system = $1
              AND started_at IS NOT NULL
            """,
            city.source_system,
        )
        by_date: dict = {}
        for r in rows:
            # dict() — asyncpg Records are immutable and we update video_url
            # in the in-memory index as matches land.
            by_date.setdefault(r["local_date"], []).append(dict(r))

        matched = 0
        unmatched_titles: list[str] = []
        conflicts = 0
        for v in videos:
            parsed = _parse_stream_title(v.title)
            if not parsed:
                unmatched_titles.append(v.title)
                continue
            vdate, vbody = parsed
            candidates = by_date.get(vdate, [])
            if not candidates:
                unmatched_titles.append(v.title)
                continue
            vsquash = _squash_body(vbody)
            vsquash_base = _squash_body(_TITLE_QUALIFIER_RE.sub("", vbody))
            best = None
            for r in candidates:
                msquash = _squash_body(r["body_name"])
                if msquash == vsquash:
                    best = r
                    break
                if best is None and msquash == vsquash_base:
                    best = r
            if best is None:
                # Qualifier-stripped comparison both sides (Socrata
                # meeting_type carries '- Non-Regular' style suffixes too).
                for r in candidates:
                    msquash_base = _squash_body(_TITLE_QUALIFIER_RE.sub("", r["body_name"]))
                    if msquash_base and msquash_base == vsquash_base:
                        best = r
                        break
            if best is None:
                # Last resort: containment either way (committee names get
                # abbreviated in titles occasionally).
                for r in candidates:
                    msquash = _squash_body(r["body_name"])
                    if msquash and (msquash in vsquash or vsquash in msquash):
                        best = r
                        break
            if best is None:
                unmatched_titles.append(v.title)
                continue
            stats.meetings_seen += 1
            if best["video_url"]:
                conflicts += 1
                continue
            video_url = f"https://www.youtube.com/watch?v={v.video_id}"
            await db.execute(
                """
                UPDATE meetings SET video_url = $1, updated_at = now()
                WHERE id = $2::uuid AND video_url IS NULL
                """,
                video_url, best["id"],
            )
            best["video_url"] = video_url  # keep the in-memory index current
            stats.matched_videos += 1
            matched += 1
            if limit and matched >= limit:
                break
        stats.skipped_no_match += len(unmatched_titles)
        log.info(
            "youtube match: city=%s videos=%d matched=%d already-matched=%d unmatched=%d",
            city.slug, len(videos), matched, conflicts, len(unmatched_titles),
        )
        for t in unmatched_titles[:25]:
            log.info("  unmatched video title: %r", t)
        if len(unmatched_titles) > 25:
            log.info("  ... and %d more unmatched titles", len(unmatched_titles) - 25)
    return stats


# ── Stage 6: fetch_meeting_captions ────────────────────────────────


async def _write_caption_speeches(
    db: Database, *, city: EscribeCity, meeting_row, cap_speeches: list[CaptionSpeech],
    vtt_text: str, track_kind: str, truecase_dict: dict[str, str],
    stats: CaptionStats,
) -> int:
    """Upsert one meeting's collapsed caption speeches. Returns inserted count."""
    r = meeting_row
    speech_type = "floor" if r["body_type"] == "council" else "committee"
    base_url = r["video_url"]
    spoken_base = r["started_at"] or datetime.now(timezone.utc)
    # Self-introduced speakers' name tokens join this meeting's truecase
    # dictionary so their names capitalize inside the speech text too.
    meeting_dict = dict(truecase_dict)
    for sp in cap_speeches:
        if sp.attribution == "self_intro":
            for token in sp.speaker_name_raw.split():
                if len(token) >= 2:
                    meeting_dict.setdefault(token.lower(), token)
    truecase_dict = meeting_dict
    n_inserted = 0
    for seq, sp in enumerate(cap_speeches, start=1):
        kind = sp.attribution or "bare"
        stats.attribution_counts[kind] = stats.attribution_counts.get(kind, 0) + 1
        # Live CART captions lag the audio by ~5s (measured 4.75-7.25s via
        # voice-embedding grid sweep, 2026-08-14 diarization PoC), so the
        # jump link starts 5s early to land just before the words. The
        # exact caption offset stays in source_anchor / raw for data use.
        source_url = f"{base_url}&t={max(0, int(sp.start_seconds) - 5)}"
        source_anchor = f"{r['source_meeting_id']}:{int(sp.start_seconds)}"
        spoken_at = spoken_base + timedelta(seconds=sp.start_seconds)
        inserted = await _upsert_speech(
            db,
            session_id=r["session_id"], city=city, meeting_id=r["id"],
            politician_id=None, confidence=0.0,
            speaker_name_raw=sp.speaker_name_raw,
            speaker_role=sp.speaker_role,
            speech_type=speech_type,
            spoken_at=spoken_at, sequence=seq,
            text=truecase_caption_text(sp.text, truecase_dict),
            source_url=source_url, source_anchor=source_anchor,
            raw_payload={
                "start_seconds": sp.start_seconds,
                "end_seconds": sp.end_seconds,
                "video_url": base_url,
                # 'manual' = human/CC track, 'auto' = YouTube ASR.
                "caption_track": track_kind,
                # 'macro' | 'recognition' | None — see CaptionSpeech.
                "attribution": sp.attribution,
            },
            # VTT is persisted on meetings.raw_captions_vtt (migration
            # 0058), not on speech rows — speech deletes must never be
            # able to destroy the caption cache.
            raw_vtt=None,
        )
        if inserted:
            stats.speeches_inserted += 1
            n_inserted += 1
        else:
            stats.speeches_updated += 1
    return n_inserted


def _collapse_for_track(
    vtt_text: str, panel_owner_at=None,
) -> Optional[list[CaptionSpeech]]:
    """Parse + collapse one VTT into speeches; None when the VTT is empty."""
    cap_lines = parse_vtt(vtt_text)
    if not cap_lines:
        return None
    if looks_like_cc_turn_captions(cap_lines):
        return collapse_cc_turns(cap_lines, panel_owner_at=panel_owner_at)
    return collapse_captions_into_speeches(cap_lines)


async def fetch_meeting_captions(
    db: Database, *, city_slug: str = "all",
    limit: Optional[int] = None, delay: float = DEFAULT_RATE_DELAY,
) -> CaptionStats:
    stats = CaptionStats()
    cities = _resolve_cities(city_slug)
    for city in cities:
        rows = await db.fetch(
            f"""
            SELECT m.id::text AS id, m.session_id::text AS session_id,
                   m.video_url, m.started_at, m.body_name, m.body_type,
                   m.source_meeting_id,
                   m.raw->'speaker_timeline' AS timeline
            FROM meetings m
            WHERE m.source_system = $1
              AND m.video_url IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1 FROM speeches s
                  WHERE s.source_system = $2
                    AND s.meeting_id = m.id
              )
            ORDER BY m.started_at DESC
            {"LIMIT $3" if limit else ""}
            """,
            *([city.source_system,
               f"{city.source_system.split('-')[0]}-youtube-captions",
               limit]
              if limit else
              [city.source_system,
               f"{city.source_system.split('-')[0]}-youtube-captions"]),
        )
        stats.cities_processed += 1
        truecase_dict = await _load_truecase_dictionary(db, city)
        for r in rows:
            stats.meetings_seen += 1
            with tempfile.TemporaryDirectory() as tmpdir:
                got = await download_auto_captions(r["video_url"], tmpdir)
                if not got:
                    stats.fetch_failures.append(r["video_url"])
                    if delay > 0:
                        await asyncio.sleep(delay)
                    continue
                vtt_path, track_kind = got
                try:
                    vtt_text = open(vtt_path, "r", encoding="utf-8", errors="replace").read()
                except OSError as exc:
                    log.warning("read vtt %s failed: %s", vtt_path, exc)
                    stats.fetch_failures.append(r["video_url"])
                    continue
            timeline = r["timeline"]
            if isinstance(timeline, str):
                timeline = orjson.loads(timeline)
            cap_speeches = _collapse_for_track(
                vtt_text, panel_owner_at=make_panel_owner_lookup(timeline),
            )
            if cap_speeches is None:
                stats.parse_warnings += 1
                continue
            stats.captions_fetched += 1
            # Canonical VTT lives on the meeting row (migration 0058) so it
            # survives speech deletes; the seq-1 raw_html copy is legacy.
            await db.execute(
                "UPDATE meetings SET raw_captions_vtt = $1, updated_at = now() WHERE id = $2::uuid",
                vtt_text, r["id"],
            )
            n_inserted = await _write_caption_speeches(
                db, city=city, meeting_row=r, cap_speeches=cap_speeches,
                vtt_text=vtt_text, track_kind=track_kind,
                truecase_dict=truecase_dict, stats=stats,
            )
            log.info("captions for meeting=%s -> %d speeches (%d new)",
                     r["source_meeting_id"], len(cap_speeches), n_inserted)
            if delay > 0:
                await asyncio.sleep(delay)
    return stats


async def _diff_write_caption_speeches(
    conn, *, city: EscribeCity, meeting_row, cap_speeches: list[CaptionSpeech],
    track_kind: str, truecase_dict: dict[str, str],
) -> dict:
    """Content-hash-aware reparse writer (2026-08-15, replacing
    delete-and-reinsert). Per sequence:

      - text hash unchanged + attribution tier unchanged → NO write at all
        (chunks and embeddings stay; DB-side attributions like voice/chair
        FKs survive untouched);
      - hash unchanged, collapse now assigns a DIFFERENT tier → update the
        speaker metadata, reset the FK for re-resolution, keep the chunks
        (text identical ⇒ embeddings still valid; only the denorm sync is
        needed afterwards);
      - hash changed → full update, delete the row's chunks, re-enter the
        needs_chunking queue;
      - new/removed trailing sequences → insert/delete.

    A no-op reparse therefore embeds nothing — the 2026-08-14 review found
    seven full 8.7K-chunk re-embeds for regex-sized changes.
    """
    r = meeting_row
    speech_type = "floor" if r["body_type"] == "council" else "committee"
    base_url = r["video_url"]
    spoken_base = r["started_at"] or datetime.now(timezone.utc)
    meeting_dict = dict(truecase_dict)
    for sp in cap_speeches:
        if sp.attribution == "self_intro":
            for token in sp.speaker_name_raw.split():
                if len(token) >= 2:
                    meeting_dict.setdefault(token.lower(), token)

    existing = {
        e["sequence"]: e for e in await conn.fetch(
            """
            SELECT id, sequence, content_hash,
                   raw->>'attribution' AS attr
            FROM speeches
            WHERE source_system = $1 AND meeting_id = $2::uuid
            """,
            f"{city.source_system.split('-')[0]}-youtube-captions", r["id"],
        )
    }
    counts = {"kept": 0, "retiered": 0, "changed": 0, "inserted": 0, "deleted": 0}
    source_system = f"{city.source_system.split('-')[0]}-youtube-captions"

    for seq, sp in enumerate(cap_speeches, start=1):
        text = truecase_caption_text(sp.text, meeting_dict)
        chash = _content_hash(text)
        raw_payload = {
            "start_seconds": sp.start_seconds,
            "end_seconds": sp.end_seconds,
            "video_url": base_url,
            "caption_track": track_kind,
            "attribution": sp.attribution,
        }
        ex = existing.get(seq)
        if ex and ex["content_hash"] == chash:
            same_tier = (ex["attr"] == sp.attribution) or (
                # DB-side tiers (voice map / minutes chair) attach to rows
                # the collapse leaves bare — don't clobber them.
                sp.attribution is None and ex["attr"] in ("voice",)
            )
            if same_tier:
                counts["kept"] += 1
                continue
            await conn.execute(
                """
                UPDATE speeches
                SET speaker_name_raw = $1, speaker_role = $2,
                    politician_id = NULL, confidence = 0,
                    raw = $3::jsonb, updated_at = now()
                WHERE id = $4
                """,
                sp.speaker_name_raw[:200], sp.speaker_role,
                orjson.dumps(raw_payload).decode(), ex["id"],
            )
            counts["retiered"] += 1
            continue
        if ex:
            await conn.execute("DELETE FROM speech_chunks WHERE speech_id = $1", ex["id"])
            await conn.execute(
                """
                UPDATE speeches
                SET text = $1, word_count = $2, content_hash = $3,
                    speaker_name_raw = $4, speaker_role = $5,
                    politician_id = NULL, confidence = 0,
                    spoken_at = $6, source_url = $7, source_anchor = $8,
                    raw = $9::jsonb, needs_chunking = true, updated_at = now()
                WHERE id = $10
                """,
                text, len(text.split()), chash,
                sp.speaker_name_raw[:200], sp.speaker_role,
                spoken_base + timedelta(seconds=sp.start_seconds),
                f"{base_url}&t={max(0, int(sp.start_seconds) - 5)}",
                f"{r['source_meeting_id']}:{int(sp.start_seconds)}",
                orjson.dumps(raw_payload).decode(), ex["id"],
            )
            counts["changed"] += 1
            continue
        await _upsert_speech(
            conn,
            session_id=r["session_id"], city=city, meeting_id=r["id"],
            politician_id=None, confidence=0.0,
            speaker_name_raw=sp.speaker_name_raw, speaker_role=sp.speaker_role,
            speech_type=speech_type,
            spoken_at=spoken_base + timedelta(seconds=sp.start_seconds),
            sequence=seq, text=text,
            source_url=f"{base_url}&t={max(0, int(sp.start_seconds) - 5)}",
            source_anchor=f"{r['source_meeting_id']}:{int(sp.start_seconds)}",
            raw_payload=raw_payload, raw_vtt=None,
        )
        counts["inserted"] += 1

    stale = [e["id"] for s, e in existing.items() if s > len(cap_speeches)]
    if stale:
        await conn.execute(
            "DELETE FROM speeches WHERE id = ANY($1::uuid[])", stale,
        )
        counts["deleted"] = len(stale)
    return counts


async def reparse_meeting_captions(
    db: Database, *, city_slug: str = "all",
) -> CaptionStats:
    """Rebuild caption speeches from the cached VTTs — no network, and
    (since 2026-08-15) no unnecessary re-embedding: unchanged turns are
    left untouched, so only rows whose text actually changed re-enter the
    chunk/embed queue. Run resolve-meeting-caption-speakers afterwards to
    re-fill attributions on retiered/changed rows.
    """
    stats = CaptionStats()
    for city in _resolve_cities(city_slug):
        source_system = f"{city.source_system.split('-')[0]}-youtube-captions"
        truecase_dict = await _load_truecase_dictionary(db, city)
        rows = await db.fetch(
            """
            SELECT m.id::text AS id, m.session_id::text AS session_id,
                   m.video_url, m.started_at, m.body_name, m.body_type,
                   m.source_meeting_id,
                   m.raw->'speaker_timeline' AS timeline,
                   COALESCE(m.raw_captions_vtt, s.raw_html) AS vtt,
                   COALESCE(s.raw->>'caption_track', 'manual') AS track
            FROM meetings m
            LEFT JOIN speeches s
              ON s.source_system = $2
             AND s.sequence = 1
             AND s.meeting_id = m.id
            WHERE m.source_system = $1
              AND m.video_url IS NOT NULL
              AND (m.raw_captions_vtt IS NOT NULL OR s.raw_html IS NOT NULL)
            """,
            city.source_system, source_system,
        )
        stats.cities_processed += 1
        for r in rows:
            stats.meetings_seen += 1
            timeline = r["timeline"]
            if isinstance(timeline, str):
                timeline = orjson.loads(timeline)
            cap_speeches = _collapse_for_track(
                r["vtt"], panel_owner_at=make_panel_owner_lookup(timeline),
            )
            if cap_speeches is None:
                stats.parse_warnings += 1
                continue
            for sp in cap_speeches:
                kind = sp.attribution or "bare"
                stats.attribution_counts[kind] = stats.attribution_counts.get(kind, 0) + 1
            # One transaction per meeting: a mid-reparse kill must never
            # leave the meeting half-updated.
            async with db.pool.acquire() as conn:
                async with conn.transaction():
                    counts = await _diff_write_caption_speeches(
                        conn, city=city, meeting_row=r, cap_speeches=cap_speeches,
                        track_kind=r["track"], truecase_dict=truecase_dict,
                    )
            stats.captions_fetched += 1
            stats.speeches_inserted += counts["inserted"]
            stats.speeches_updated += counts["retiered"] + counts["changed"]
            if any(counts[k] for k in ("retiered", "changed", "inserted", "deleted")):
                log.info("reparsed meeting=%s: %s", r["source_meeting_id"], counts)
    return stats


# ── Stage 7: resolve_meeting_caption_speakers ──────────────────────


def _normalise_caption_name(raw: str) -> Optional[str]:
    """'COUNCILLOR JONES' / 'Mayor Gondek' / 'MS. SMITH' → 'JONES' / 'GONDEK' / 'SMITH'."""
    if not raw:
        return None
    s = " ".join(raw.split()).strip(":-– ")
    # Drop common prefixes (case-insensitive).
    for pre in ("Councillor", "Counsellor", "Mayor", "Deputy Mayor", "Alderman", "Acting Mayor",
                "Mr.", "Ms.", "Mrs.", "Dr.", "Madam Chair", "Chair", "Chairman",
                "Chairperson", "Sir", "Madam", "Her Worship", "His Worship"):
        if s.lower().startswith(pre.lower() + " "):
            s = s[len(pre) + 1:].strip()
    if not s:
        return None
    # Take the last token, upper-case.
    parts = s.split()
    if not parts:
        return None
    surname = parts[-1].strip(".,;:").upper()
    return surname if len(surname) >= 2 else None


def _levenshtein_leq(a: str, b: str, max_dist: int = 2) -> Optional[int]:
    """Edit distance between a and b if ≤ max_dist, else None. Small inputs
    only (surnames) — O(len(a)·len(b)) is fine."""
    if abs(len(a) - len(b)) > max_dist:
        return None
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        cur = [i]
        best = i
        for j, cb in enumerate(b, start=1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
            best = min(best, cur[j])
        if best > max_dist:
            return None
        prev = cur
    return prev[-1] if prev[-1] <= max_dist else None


def _fuzzy_roster_match(surname: str, roster: dict[str, str]) -> Optional[str]:
    """Unique-best fuzzy surname match (edit distance ≤ 2) to absorb live-steno
    misspellings ('PACKET' → PAQUETTE-ish). Returns politician_id only when
    exactly one roster surname is at the minimum distance."""
    best_dist = 3
    best_ids: list[str] = []
    for known, pid in roster.items():
        d = _levenshtein_leq(surname, known, max_dist=2)
        if d is None:
            continue
        if d < best_dist:
            best_dist = d
            best_ids = [pid]
        elif d == best_dist:
            best_ids.append(pid)
    return best_ids[0] if len(best_ids) == 1 else None


# Confidence tiers by (attribution, match tier). Deterministic-only per the
# 2026-08-14 decision — no LLM; unresolved names are logged so an LLM batch
# pass can be justified later IF fuzzy leaves a real residue.
_CONF_BY_ATTRIBUTION = {"macro": 0.9, "recognition": 0.7, "panel": 0.75, "alternation": 0.65}
_CONF_DEFAULT_EXACT = 0.7
_CONF_FUZZY = 0.6


async def resolve_meeting_caption_speakers(
    db: Database, *, city_slug: str = "all",
) -> CaptionStats:
    stats = CaptionStats()
    for city in _resolve_cities(city_slug):
        source_system = f"{city.source_system.split('-')[0]}-youtube-captions"
        # Per-meeting-date roster cache: pre-2025 meetings resolve against
        # the dated politician_terms roster; current-term against Open
        # North; dates with no roster refuse to attribute.
        roster_cache: dict = {}

        async def _roster_at(when):
            key = when.date() if when is not None and hasattr(when, "date") else when
            if key not in roster_cache:
                roster_cache[key] = await roster_for_date(db, city, when)
            return roster_cache[key]
        unresolved = await db.fetch(
            """
            SELECT s.id::text AS id, s.speaker_name_raw, s.speaker_role,
                   s.raw->>'attribution' AS attribution,
                   m.started_at AS meeting_started_at
            FROM speeches s
            LEFT JOIN meetings m ON m.id = s.meeting_id
            WHERE s.source_system = $1
              AND s.politician_id IS NULL
            """,
            source_system,
        )
        stats.cities_processed += 1
        unmatched_names: dict[str, int] = {}
        roster_skipped = 0
        for r in unresolved:
            dated = await _roster_at(r["meeting_started_at"])
            if dated is None:
                roster_skipped += 1
                stats.speakers_unresolved += 1
                continue
            roster, mayor_id = dated
            raw_name = (r["speaker_name_raw"] or "").strip()
            role = (r["speaker_role"] or "").lower()
            attribution = r["attribution"]
            # Structurally unattributable rows: bare turns and rotating
            # role-labels (Chair/Clerk/Interpreter) stay NULL by design.
            # self_intro rows are named members of the public — roster-
            # matching them would FK a citizen who shares a councillor's
            # surname.
            if raw_name.upper() == "UNATTRIBUTED" or attribution == "self_intro" \
                    or role in ("chair", "clerk", "interpreter"):
                stats.speakers_unresolved += 1
                continue
            exact_conf = _CONF_BY_ATTRIBUTION.get(attribution, _CONF_DEFAULT_EXACT)
            pid: Optional[str] = None
            confidence = 0.0
            # 1. Mayor / her-his worship → mayor.
            if mayor_id and ("mayor" in role or "worship" in role
                             or raw_name.lower().startswith(("mayor", "her worship", "his worship"))):
                pid = mayor_id
                confidence = exact_conf
            else:
                surname = _normalise_caption_name(raw_name)
                if surname and surname in roster:
                    pid = roster[surname]
                    confidence = exact_conf
                elif surname:
                    pid = _fuzzy_roster_match(surname, roster)
                    confidence = _CONF_FUZZY
            if pid:
                await db.execute(
                    """
                    UPDATE speeches SET politician_id = $1::uuid,
                                        confidence = $2,
                                        updated_at = now()
                    WHERE id = $3::uuid
                    """,
                    pid, confidence, r["id"],
                )
                stats.speakers_resolved += 1
            else:
                stats.speakers_unresolved += 1
                unmatched_names[raw_name] = unmatched_names.get(raw_name, 0) + 1
        if roster_skipped:
            log.warning(
                "%s: %d turns skipped — meeting predates the current-term "
                "roster; dated-roster ingest needed before those can resolve",
                city.slug, roster_skipped,
            )
        if unmatched_names:
            top = sorted(unmatched_names.items(), key=lambda kv: -kv[1])[:20]
            log.info("caption speaker names unresolved for %s (top %d): %s",
                     city.slug, len(top), top)

        # Voice-map application: the offline voice attributor
        # (scripts/voice-audit/voice_attribute.py) stores per-meeting
        # {start_s, name, cos} entries in meetings.raw->'voice_map'.
        # Applying them here (rather than the script writing speeches
        # directly) makes voice attribution reparse-safe — a reparse
        # deletes and reinserts speeches, then this stage re-applies.
        voice_meetings = await db.fetch(
            """
            SELECT id::text AS id, started_at, raw->'voice_map' AS vmap
            FROM meetings
            WHERE source_system = $1 AND raw->'voice_map' IS NOT NULL
            """,
            city.source_system,
        )
        # Voice enrollment comes from current-term labelled turns; the map's
        # names are only meaningful for current-term meetings.
        voice_meetings = [
            vm for vm in voice_meetings
            if _roster_valid_for(city.slug, vm["started_at"])
        ]
        import orjson as _orjson
        name_to_pid: dict[str, str] = {}
        for r in await db.fetch(
            """
            SELECT id::text AS id, name FROM politicians
            WHERE level = 'municipal' AND province_territory = $1 AND source_id LIKE $2
            """,
            city.province_territory, f"opennorth:{city.slug}-city-council:%",
        ):
            if r["name"]:
                name_to_pid[r["name"]] = r["id"]
        voice_applied = 0
        for vm in voice_meetings:
            entries = vm["vmap"]
            if isinstance(entries, str):
                entries = _orjson.loads(entries)
            # v2 maps carry a {version, generated_at, params, entries}
            # envelope; v1 maps were a bare list.
            if isinstance(entries, dict):
                entries = entries.get("entries", [])
            for e in entries:
                pid = name_to_pid.get(e.get("name") or "")
                if not pid:
                    continue
                result = await db.execute(
                    """
                    UPDATE speeches
                    SET politician_id = $1::uuid, confidence = 0.7,
                        speaker_name_raw = $2,
                        raw = raw || '{"attribution": "voice"}'::jsonb,
                        updated_at = now()
                    WHERE source_system = $3
                      AND meeting_id = $4::uuid
                      AND politician_id IS NULL
                      AND raw->>'attribution' IS NULL
                      AND speaker_name_raw = 'UNATTRIBUTED'
                      AND abs((raw->>'start_seconds')::float - $5) < 0.6
                    """,
                    pid, e["name"], source_system, vm["id"], float(e["start_s"]),
                )
                try:
                    voice_applied += int(result.rsplit(" ", 1)[-1])
                except (ValueError, AttributeError):
                    pass
        if voice_applied:
            stats.speakers_resolved += voice_applied
            log.info("voice-map applied: %d turns for %s", voice_applied, city.slug)
        elif voice_meetings:
            # Silent under-application is the failure mode here (a
            # segmentation change shifts start_seconds and the map stops
            # matching) — make zero loud, but only when no voice
            # attributions exist at all (a re-run after a successful apply
            # legitimately applies 0).
            existing_voice = await db.fetchval(
                "SELECT count(*) FROM speeches WHERE source_system = $1 "
                "AND raw->>'attribution' = 'voice'",
                source_system,
            )
            if not existing_voice:
                log.warning(
                    "voice maps present for %d meetings but 0 voice turns in DB "
                    "— stale maps after a segmentation change?", len(voice_meetings),
                )

        # This stage writes politician_id after chunking may have run —
        # reconcile the chunk denorm at the end (cheap, idempotent).
        from datetime import date as _date
        from .speech_chunker import sync_chunk_politician_scoped
        synced = await sync_chunk_politician_scoped(
            db, province=city.province_territory, source_system=source_system,
            min_date=_date(2011, 1, 1), level="municipal",
        )
        if synced:
            log.info("chunk politician denorm synced: %d rows", synced)
    return stats
