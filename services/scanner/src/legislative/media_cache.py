"""Derived-media cache — one fetch per meeting, offline forever after.

The 2026-08-14 retrospective found the pipeline re-downloading source media
on every parser iteration (10+ GB in one day) and fetching audio and video
as SEPARATE YouTube downloads of the same asset. This module is the fix:

  - one 480p video fetch per meeting (yt-dlp, hardened politeness flags);
  - ONE local ffmpeg pass derives everything downstream stages need:
      audio16k.opus   16 kHz mono Opus (~11 MB/hour) — voice fingerprinting
      frames/*.jpg    keyframes (~5 s cadence)       — clerk-panel OCR
      times.json      keyframe pts + duration        — timeline alignment
      meta.json       source, identity, fetched_at   — provenance
  - the source video is deleted; only derivatives persist
    (~30-40 MB/meeting ⇒ ~25 GB for the full 630-meeting backfill).

Cache root: $MEDIA_CACHE_DIR (compose bind-mounts ./media-cache — a host
path, deliberately, so host-side tooling like scripts/voice-audit can read
it too). Layout: <root>/youtube/<video_id>/…

ISI note: meetings.raw->'media' records the ISI CDN asset for ~75% of
meetings (probe-edmonton-media). ISI is the better source (720p, no
throttling) BUT its timeline differs from YouTube's by ±minutes, and every
caption timestamp we hold is YouTube-based — so consumers stay on the
YouTube key until the forced-alignment stage (plan P5) lands. The cache
layout already namespaces by source for that cutover.

Failure memoization: callers should record fetch outcomes in
meetings.raw->'fetch' via record_fetch_outcome() and consult
fetch_backoff_active() so a 403-throttled or caption-less video stops
being retried at the head of every run.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone
from typing import Optional

from .youtube_captions import _run_ytdlp, YTDLP_POLITE_ARGS, YTDLP_POT_ARGS

log = logging.getLogger(__name__)

CACHE_ROOT = os.environ.get("MEDIA_CACHE_DIR", "/media-cache")
VIDEO_FORMAT = os.environ.get("PANEL_OCR_YT_FORMAT", "135/244/136")
JS_RUNTIME = os.environ.get("PANEL_OCR_JS_RUNTIME", "node")
DOWNLOAD_TIMEOUT_SECS = 1800


def cache_dir_for(video_id: str) -> str:
    return os.path.join(CACHE_ROOT, "youtube", video_id)


def derivatives_ready(video_id: str) -> bool:
    d = cache_dir_for(video_id)
    return os.path.exists(os.path.join(d, "meta.json"))


def load_meta(video_id: str) -> Optional[dict]:
    try:
        with open(os.path.join(cache_dir_for(video_id), "meta.json")) as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


async def ensure_derivatives(video_url: str) -> Optional[dict]:
    """Fetch-once: return {'dir', 'audio', 'frames_dir', 'times', 'meta'}
    for the meeting's derivatives, downloading + deriving only on a cache
    miss. Returns None when acquisition fails (caller memoizes)."""
    video_id = video_url.split("v=")[-1].split("&")[0]
    d = cache_dir_for(video_id)
    paths = {
        "dir": d,
        "audio": os.path.join(d, "audio16k.opus"),
        "frames_dir": os.path.join(d, "frames"),
        "times": os.path.join(d, "times.json"),
        "meta": os.path.join(d, "meta.json"),
    }
    if derivatives_ready(video_id):
        return paths

    os.makedirs(d, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mediacache-") as tmpdir:
        out = os.path.join(tmpdir, "video.%(ext)s")
        args = [
            "-f", VIDEO_FORMAT,
            "--js-runtimes", JS_RUNTIME,
            "--no-warnings",
            *YTDLP_POLITE_ARGS,
            *YTDLP_POT_ARGS,
            "-o", out,
            video_url,
        ]
        rc, _, err = await _run_ytdlp(args, timeout=DOWNLOAD_TIMEOUT_SECS)
        video = next(
            (os.path.join(tmpdir, e) for e in os.listdir(tmpdir) if e.startswith("video.")),
            None,
        )
        if not video:
            log.warning("media fetch failed for %s (rc=%s): %s",
                        video_url, rc, err.strip()[:300])
            return None

        # Keyframe pts + duration via packet flags (no decode).
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_packets", "-show_entries", "packet=pts_time,flags",
             "-of", "csv=p=0", video],
            capture_output=True, text=True,
        )
        times = []
        for line in probe.stdout.splitlines():
            parts = line.strip().split(",")
            if len(parts) >= 2 and "K" in parts[1]:
                try:
                    times.append(float(parts[0]))
                except ValueError:
                    pass
        dur_out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", video],
            capture_output=True, text=True,
        ).stdout.strip()
        duration = float(dur_out) if dur_out else None

        # ONE ffmpeg pass: keyframes (video, decode keyframes only) +
        # 16 kHz mono opus (audio) — this is what removes the second
        # YouTube fetch the voice pipeline used to make.
        frames_dir = paths["frames_dir"]
        os.makedirs(frames_dir, exist_ok=True)
        res = subprocess.run(
            ["ffmpeg", "-v", "error", "-skip_frame", "nokey", "-i", video,
             "-map", "0:v", "-vsync", "0", "-q:v", "4",
             os.path.join(frames_dir, "f%06d.jpg"),
             "-map", "0:a", "-ac", "1", "-ar", "16000",
             "-c:a", "libopus", "-b:a", "24k", paths["audio"]],
            capture_output=True, text=True,
        )
        if res.returncode != 0:
            log.warning("derivative pass failed for %s: %s", video_url, res.stderr[:300])
            return None

        n_frames = len(os.listdir(frames_dir))
        # Keyframe-alignment sanity (review fragility B7): fail loudly.
        if abs(len(times) - n_frames) > 2 or (
            duration and times and times[-1] < duration * 0.9
        ):
            log.error("keyframe alignment unsafe for %s: %d pts / %d frames / "
                      "last %.0fs of %.0fs — cache aborted",
                      video_id, len(times), n_frames,
                      times[-1] if times else -1, duration or -1)
            return None

        with open(paths["times"], "w") as fh:
            json.dump({"keyframe_pts": times, "duration": duration}, fh)
        with open(paths["meta"], "w") as fh:
            json.dump({
                "version": 1,
                "source": "youtube",
                "video_id": video_id,
                "video_url": video_url,
                "format": VIDEO_FORMAT,
                "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "duration": duration,
                "n_frames": n_frames,
            }, fh)
    return paths


# ── Fetch-outcome memoization ───────────────────────────────────────

FETCH_BACKOFF = timedelta(hours=6)
FETCH_MAX_ATTEMPTS = 8  # then treat as permanently unavailable


def fetch_backoff_active(meeting_raw_fetch: Optional[dict]) -> bool:
    """True when a previous failure says 'do not retry yet' (or ever)."""
    if not meeting_raw_fetch:
        return False
    attempts = meeting_raw_fetch.get("attempts", 0)
    if attempts >= FETCH_MAX_ATTEMPTS:
        return True
    last = meeting_raw_fetch.get("last_attempt_at")
    if not last:
        return False
    try:
        last_dt = datetime.fromisoformat(last)
    except ValueError:
        return False
    return datetime.now(timezone.utc) - last_dt < FETCH_BACKOFF * max(1, attempts)


async def record_fetch_outcome(db, meeting_id: str, *, ok: bool, error: str = "") -> None:
    """Upsert meetings.raw->'fetch' with attempt bookkeeping."""
    await db.execute(
        """
        UPDATE meetings
        SET raw = raw || jsonb_build_object('fetch', jsonb_build_object(
                'attempts', CASE WHEN $2 THEN 0
                                 ELSE COALESCE((raw->'fetch'->>'attempts')::int, 0) + 1 END,
                'last_attempt_at', $3::text,
                'last_error', NULLIF($4::text, ''))),
            updated_at = now()
        WHERE id = $1::uuid
        """,
        meeting_id, ok,
        datetime.now(timezone.utc).isoformat(timespec="seconds"), error[:200],
    )
