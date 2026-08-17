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

import asyncio
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
# DASH video itags (135/244/136) carry NO audio — pin video+audio pairs so
# the single cached fetch serves both derivative streams (itag 140 = m4a
# audio; 18 = muxed 360p last-resort).
VIDEO_FORMAT = os.environ.get("PANEL_OCR_YT_FORMAT", "135+140/244+140/136+140/18")
JS_RUNTIME = os.environ.get("PANEL_OCR_JS_RUNTIME", "node")
DOWNLOAD_TIMEOUT_SECS = 1800


def _paths_for(d: str) -> dict:
    return {
        "dir": d,
        "audio": os.path.join(d, "audio16k.opus"),
        "frames_dir": os.path.join(d, "frames"),
        "times": os.path.join(d, "times.json"),
        "meta": os.path.join(d, "meta.json"),
    }


def cache_dir_for(video_id: str) -> str:
    return os.path.join(CACHE_ROOT, "youtube", video_id)


def isi_cache_dir_for(etag: str) -> str:
    import re as _re
    return os.path.join(CACHE_ROOT, "isi", _re.sub(r"[^A-Za-z0-9._-]", "_", etag))


def find_cache(video_id: str, isi_etag: Optional[str] = None) -> Optional[dict]:
    """Existing derivatives for a meeting, either source (ISI preferred)."""
    if isi_etag:
        d = isi_cache_dir_for(isi_etag)
        if os.path.exists(os.path.join(d, "meta.json")):
            return _paths_for(d)
    d = cache_dir_for(video_id)
    if os.path.exists(os.path.join(d, "meta.json")):
        return _paths_for(d)
    return None


def derivatives_ready(video_id: str) -> bool:
    d = cache_dir_for(video_id)
    return os.path.exists(os.path.join(d, "meta.json"))


def load_meta_from(paths: dict) -> Optional[dict]:
    try:
        with open(paths["meta"]) as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


def load_meta(video_id: str) -> Optional[dict]:
    return load_meta_from(_paths_for(cache_dir_for(video_id)))


async def _derive_from_file(video: str, paths: dict, *, source: str,
                            video_url: str, identity: dict,
                            vtt_text: Optional[str]) -> bool:
    """Shared derivation: local video file → keyframes + opus + times +
    (when vtt_text given) caption alignment → meta. True on success.

    ffprobe/ffmpeg run via asyncio.to_thread — they take minutes on an
    8h meeting, and blocking the loop would stall concurrent workers'
    downloads (cache-edmonton-media --workers N)."""
    probe = await asyncio.to_thread(
        subprocess.run,
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
    dur_out = (await asyncio.to_thread(
        subprocess.run,
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", video],
        capture_output=True, text=True,
    )).stdout.strip()
    duration = float(dur_out) if dur_out else None

    frames_dir = paths["frames_dir"]
    os.makedirs(frames_dir, exist_ok=True)
    # Frames are stored at 480 height: the panel-OCR reader normalizes to
    # 480 before analysis anyway, and native 720p JPEGs made frames ~92%
    # of each cache dir (~312MB/meeting → ~140MB).
    res = await asyncio.to_thread(
        subprocess.run,
        ["ffmpeg", "-v", "error", "-skip_frame", "nokey", "-i", video,
         "-map", "0:v", "-vf", "scale=-2:480", "-vsync", "0", "-q:v", "4",
         os.path.join(frames_dir, "f%06d.jpg"),
         "-map", "0:a", "-ac", "1", "-ar", "16000",
         "-c:a", "libopus", "-b:a", "24k", paths["audio"]],
        capture_output=True, text=True,
    )
    if res.returncode != 0:
        log.warning("derivative pass failed for %s: %s", video_url, res.stderr[:300])
        return False

    n_frames = len(os.listdir(frames_dir))
    # Keyframe-alignment sanity (review fragility B7): fail loudly.
    if abs(len(times) - n_frames) > 2 or (
        duration and times and times[-1] < duration * 0.9
    ):
        log.error("keyframe alignment unsafe (%s): %d pts / %d frames / "
                  "last %.0fs of %.0fs — cache aborted",
                  source, len(times), n_frames,
                  times[-1] if times else -1, duration or -1)
        return False

    caption_offset = None
    align_score = None
    if vtt_text:
        try:
            from .caption_align import align_captions_to_audio
            r = await asyncio.to_thread(
                align_captions_to_audio, vtt_text, paths["audio"])
            align_score = round(r.score, 1)
            if r.trusted:
                caption_offset = round(r.offset_s, 2)
            else:
                log.warning("caption alignment untrusted (%s, score=%.1f)",
                            source, r.score)
        except Exception as exc:
            log.warning("caption alignment failed (%s): %s", source, exc)
    # ISI derivatives are USELESS without a trusted offset — every caption
    # timestamp is YouTube-based, so an unaligned ISI cache would corrupt
    # every consumer. YouTube caches keep legacy fallbacks (+8 lead, lag
    # sweep), so an untrusted offset there is survivable.
    if source == "isi" and caption_offset is None:
        return False

    with open(paths["times"], "w") as fh:
        json.dump({"keyframe_pts": times, "duration": duration}, fh)
    with open(paths["meta"], "w") as fh:
        json.dump({
            "version": 2,
            "source": source,
            "video_url": video_url,
            **identity,
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "duration": duration,
            "n_frames": n_frames,
            "caption_offset_s": caption_offset,
            "align_score": align_score,
        }, fh)
    return True


async def _download_isi(isi: dict, dest: str) -> bool:
    """Stream the ISI CDN MP4 to a temp file: single connection, project
    bot UA (robots is a blanket Disallow — we fetch only URLs the public
    eScribe player handed us; courtesy note drafted for the City Clerk)."""
    import httpx
    from .escribe import HEADERS
    try:
        async with httpx.AsyncClient(headers=HEADERS, timeout=120,
                                     follow_redirects=True) as client:
            async with client.stream("GET", isi["url"]) as resp:
                resp.raise_for_status()
                with open(dest, "wb") as fh:
                    async for chunk in resp.aiter_bytes(1 << 20):
                        fh.write(chunk)
        return True
    except httpx.HTTPError as exc:
        log.warning("ISI download failed %s: %s", isi.get("url"), str(exc)[:200])
        return False


async def ensure_derivatives(
    video_url: str, isi: Optional[dict] = None, vtt_text: Optional[str] = None,
) -> Optional[dict]:
    """Fetch-once source ladder: existing cache (either namespace) → ISI
    (unthrottled 720p; requires vtt for the mandatory caption alignment) →
    YouTube 480p fallback. Returns the standard paths dict or None (caller
    memoizes the failure)."""
    video_id = video_url.split("v=")[-1].split("&")[0]
    isi = isi if isi and isi.get("url") and isi.get("etag") else None
    existing = find_cache(video_id, isi["etag"] if isi else None)
    if existing:
        return existing

    if isi and vtt_text:
        d = isi_cache_dir_for(isi["etag"])
        paths = _paths_for(d)
        os.makedirs(d, exist_ok=True)
        try:
            with tempfile.TemporaryDirectory(prefix="mediacache-") as tmpdir:
                video = os.path.join(tmpdir, "video.mp4")
                if await _download_isi(isi, video):
                    ok = await _derive_from_file(
                        video, paths, source="isi", video_url=video_url,
                        identity={"isi_etag": isi["etag"], "isi_url": isi["url"]},
                        vtt_text=vtt_text,
                    )
                    if ok:
                        return paths
        except Exception as exc:
            log.warning("ISI derivation crashed for %s: %s", video_id, exc)
        # ISI failed (download, derive, crash, or untrusted alignment):
        # clean the namespace dir and fall through to the YouTube lane.
        import shutil as _shutil
        _shutil.rmtree(d, ignore_errors=True)
        log.info("ISI lane failed for %s — falling back to YouTube", video_id)

    d = cache_dir_for(video_id)
    paths = _paths_for(d)
    os.makedirs(d, exist_ok=True)
    # The YouTube lane stays single-file regardless of caller concurrency
    # (attestation scoring is per-IP; parallel fetches burn goodwill).
    # ISI (above) has no such lock — the CDN is explicitly unthrottled.
    async with _YOUTUBE_LANE_LOCK:
        return await _ensure_youtube(video_url, video_id, paths, vtt_text)


_YOUTUBE_LANE_LOCK = asyncio.Lock()


async def _ensure_youtube(
    video_url: str, video_id: str, paths: dict, vtt_text: Optional[str],
) -> Optional[dict]:
    with tempfile.TemporaryDirectory(prefix="mediacache-") as tmpdir:
        out = os.path.join(tmpdir, "video.%(ext)s")
        args = [
            "-f", VIDEO_FORMAT,
            "--merge-output-format", "mp4",
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
        ok = await _derive_from_file(
            video, paths, source="youtube", video_url=video_url,
            identity={"video_id": video_id, "format": VIDEO_FORMAT},
            vtt_text=vtt_text,
        )
        if not ok:
            return None
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
