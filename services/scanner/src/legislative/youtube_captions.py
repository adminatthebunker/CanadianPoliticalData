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


async def download_auto_captions(
    video_url: str, target_dir: str, languages: tuple[str, ...] = ("en", "en-CA"),
) -> Optional[str]:
    """Download auto-generated English captions for one video. Returns path
    to the .vtt file, or None on failure."""
    # --convert-subs vtt forces VTT regardless of upstream format.
    output_template = os.path.join(target_dir, "cap-%(id)s.%(ext)s")
    args = [
        "--skip-download",
        "--write-auto-subs",
        "--sub-langs", ",".join(languages),
        "--convert-subs", "vtt",
        "--no-warnings",
        "--socket-timeout", "30",
        "-o", output_template,
        video_url,
    ]
    rc, out, err = await _run_ytdlp(args, timeout=YT_TIMEOUT_SECS)
    if rc != 0:
        log.info("yt-dlp captions failed for %s (rc=%s): %s", video_url, rc, err.strip()[:300])
    # Look for the resulting VTT file regardless of rc, since rc can be
    # nonzero on partial successes (e.g. one of two languages missing).
    vid_id = video_url.split("=")[-1].split("&")[0]
    for entry in os.listdir(target_dir):
        if entry.startswith(f"cap-{vid_id}") and entry.endswith(".vtt"):
            return os.path.join(target_dir, entry)
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
    """Parse a WebVTT string into deduped CaptionLine list, in time order."""
    lines: list[CaptionLine] = []
    seen_text: set[str] = set()
    cur_start: Optional[float] = None
    cur_end: Optional[float] = None
    cur_text: list[str] = []

    def flush():
        if cur_start is None or not cur_text:
            return
        text = " ".join(t for t in cur_text if t).strip()
        text = _VTT_TAG_RE.sub("", text)
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            return
        # Auto-captions repeat a rolling window; de-dup exact text.
        if text in seen_text:
            return
        seen_text.add(text)
        lines.append(CaptionLine(start_seconds=cur_start, end_seconds=cur_end or cur_start, text=text))

    for raw in vtt_text.splitlines():
        line = raw.strip("﻿").rstrip()
        if not line:
            flush()
            cur_start = cur_end = None
            cur_text = []
            continue
        m = _VTT_TS_RE.match(line)
        if m:
            flush()
            cur_start = _ts_to_seconds(m.group("sh"), m.group("sm"), m.group("ss"), m.group("sms"))
            cur_end = _ts_to_seconds(m.group("eh"), m.group("em"), m.group("es"), m.group("ems"))
            cur_text = []
            continue
        if line.upper() in ("WEBVTT", "NOTE") or line.startswith("NOTE "):
            continue
        # Skip cue identifiers (numeric or alphanumeric on their own line
        # followed by a timestamp on the next).
        if cur_start is None and re.fullmatch(r"[A-Za-z0-9_\-]+", line):
            continue
        # Caption text line.
        if cur_start is not None:
            cur_text.append(line)
    flush()
    return lines


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


# ── DB writers ──────────────────────────────────────────────────────


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
            raw, raw_html, content_hash
        ) VALUES (
            $1::uuid, $2, 'municipal', $3,
            $4, $5, NULL, NULL,
            $6, $7, $8, $9, 'en',
            $10, $11,
            $12, $13, $14,
            $15::jsonb, $16, $17
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
    )
    return bool(row["inserted"])


# ── Stage 5: match_meetings_to_youtube ─────────────────────────────


def _date_proximity_score(meeting_date, video_date_str: Optional[str]) -> int:
    """Days between meeting and video upload. Smaller is better; None=99999."""
    if not video_date_str or len(video_date_str) != 8 or not meeting_date:
        return 99999
    try:
        v = datetime.strptime(video_date_str, "%Y%m%d").date()
    except ValueError:
        return 99999
    md = meeting_date.date() if hasattr(meeting_date, "date") else meeting_date
    return abs((v - md).days)


_BODY_KEYWORDS = (
    ("council", ("Combined Meeting of Council", "Regular Meeting of Council",
                 "Council", "Special Council", "City Council")),
    ("committee_of_the_whole", ("Committee of the Whole",)),
)


def _title_matches_body(title: str, body_name: str) -> bool:
    t = title.lower()
    b = body_name.lower()
    # Direct substring match (most reliable).
    if b in t:
        return True
    # Loosen "Combined Meeting of Council" → "council meeting" / "city council"
    short = re.sub(r"\bcombined meeting of\b", "", b).strip()
    if short and short in t:
        return True
    # Committee-name matching: drop trailing "Committee" and try.
    if "committee" in b:
        stripped = b.replace("committee", "").strip()
        if stripped and stripped in t:
            return True
    return False


async def match_meetings_to_youtube(
    db: Database, *, city_slug: str = "all", limit: Optional[int] = None,
    max_channel_videos: int = 200, max_date_drift_days: int = 3,
) -> CaptionStats:
    stats = CaptionStats()
    for city in _resolve_cities(city_slug):
        log.info("youtube match: city=%s channel=%s", city.slug, city.youtube_channel)
        videos = await list_channel_videos(
            city.youtube_channel, max_videos=max_channel_videos,
        )
        if not videos:
            log.warning("no videos returned for %s", city.youtube_channel)
            stats.fetch_failures.append(f"channel:{city.slug}")
            continue
        stats.cities_processed += 1
        rows = await db.fetch(
            f"""
            SELECT id::text AS id, body_name, started_at, source_meeting_id
            FROM meetings
            WHERE source_system = $1
              AND video_url IS NULL
              AND started_at IS NOT NULL
            ORDER BY started_at DESC
            {"LIMIT $2" if limit else ""}
            """,
            *([city.source_system, limit] if limit else [city.source_system]),
        )
        for r in rows:
            stats.meetings_seen += 1
            best: Optional[YoutubeVideo] = None
            best_score = 99999
            for v in videos:
                if not _title_matches_body(v.title, r["body_name"]):
                    continue
                score = _date_proximity_score(r["started_at"], v.upload_date)
                if score < best_score:
                    best_score = score
                    best = v
            if best is None or best_score > max_date_drift_days:
                stats.skipped_no_match += 1
                continue
            video_url = f"https://www.youtube.com/watch?v={best.video_id}"
            await db.execute(
                """
                UPDATE meetings SET video_url = $1, updated_at = now()
                WHERE id = $2::uuid AND video_url IS NULL
                """,
                video_url, r["id"],
            )
            stats.matched_videos += 1
    return stats


# ── Stage 6: fetch_meeting_captions ────────────────────────────────


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
                   m.source_meeting_id
            FROM meetings m
            WHERE m.source_system = $1
              AND m.video_url IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1 FROM speeches s
                  WHERE s.source_system = $2
                    AND s.source_url LIKE m.video_url || '%'
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
        for r in rows:
            stats.meetings_seen += 1
            with tempfile.TemporaryDirectory() as tmpdir:
                vtt_path = await download_auto_captions(r["video_url"], tmpdir)
                if not vtt_path:
                    stats.fetch_failures.append(r["video_url"])
                    if delay > 0:
                        await asyncio.sleep(delay)
                    continue
                try:
                    vtt_text = open(vtt_path, "r", encoding="utf-8", errors="replace").read()
                except OSError as exc:
                    log.warning("read vtt %s failed: %s", vtt_path, exc)
                    stats.fetch_failures.append(r["video_url"])
                    continue
            cap_lines = parse_vtt(vtt_text)
            if not cap_lines:
                stats.parse_warnings += 1
                continue
            stats.captions_fetched += 1
            cap_speeches = collapse_captions_into_speeches(cap_lines)

            speech_type = "floor" if r["body_type"] == "council" else "committee"
            base_url = r["video_url"]
            spoken_base = r["started_at"] or datetime.now(timezone.utc)
            n_inserted = 0
            for seq, sp in enumerate(cap_speeches, start=1):
                source_url = f"{base_url}&t={int(sp.start_seconds)}"
                source_anchor = f"{r['source_meeting_id']}:{int(sp.start_seconds)}"
                spoken_at = spoken_base + timedelta(seconds=sp.start_seconds)
                inserted = await _upsert_speech(
                    db,
                    session_id=r["session_id"], city=city, meeting_id=r["id"],
                    politician_id=None, confidence=0.0,
                    speaker_name_raw=sp.speaker_name_raw,
                    speaker_role=sp.speaker_role,
                    speech_type=speech_type,
                    spoken_at=spoken_at, sequence=seq, text=sp.text,
                    source_url=source_url, source_anchor=source_anchor,
                    raw_payload={
                        "start_seconds": sp.start_seconds,
                        "end_seconds": sp.end_seconds,
                        "video_url": base_url,
                    },
                    # Persist the entire VTT on sequence=1 only — re-parsing
                    # any speech in the meeting then has full context.
                    raw_vtt=vtt_text if seq == 1 else None,
                )
                if inserted:
                    stats.speeches_inserted += 1
                    n_inserted += 1
                else:
                    stats.speeches_updated += 1
            log.info("captions for meeting=%s -> %d speeches (%d new)",
                     r["source_meeting_id"], len(cap_speeches), n_inserted)
            if delay > 0:
                await asyncio.sleep(delay)
    return stats


# ── Stage 7: resolve_meeting_caption_speakers ──────────────────────


def _normalise_caption_name(raw: str) -> Optional[str]:
    """'COUNCILLOR JONES' / 'Mayor Gondek' / 'MS. SMITH' → 'JONES' / 'GONDEK' / 'SMITH'."""
    if not raw:
        return None
    s = " ".join(raw.split()).strip(":-– ")
    # Drop common prefixes (case-insensitive).
    for pre in ("Councillor", "Mayor", "Deputy Mayor", "Alderman", "Acting Mayor",
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


async def resolve_meeting_caption_speakers(
    db: Database, *, city_slug: str = "all",
) -> CaptionStats:
    stats = CaptionStats()
    for city in _resolve_cities(city_slug):
        roster = await _load_council_roster(db, city)
        mayor_id = await _find_mayor(db, city)
        source_system = f"{city.source_system.split('-')[0]}-youtube-captions"
        unresolved = await db.fetch(
            """
            SELECT id::text AS id, speaker_name_raw, speaker_role
            FROM speeches
            WHERE source_system = $1
              AND politician_id IS NULL
            """,
            source_system,
        )
        stats.cities_processed += 1
        for r in unresolved:
            role = (r["speaker_role"] or "").lower()
            pid: Optional[str] = None
            confidence = 0.0
            # 1. Mayor / her worship → mayor.
            if mayor_id and ("mayor" in role or "worship" in role
                             or "mayor" in (r["speaker_name_raw"] or "").lower()):
                pid = mayor_id
                confidence = 0.7
            else:
                surname = _normalise_caption_name(r["speaker_name_raw"])
                if surname and surname in roster:
                    pid = roster[surname]
                    confidence = 0.7
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
    return stats
