"""Edmonton clerk-panel OCR — on-screen speaker timeline + attribution.

Every Edmonton council/committee stream is a Google Meet broadcast in which
the City Clerk screen-shares a speaker-management app. That shared panel is
a machine-readable identity source (probe 2026-08-14, 100% precision on 61
detections across 2022–2026; full spec in
``docs/runbooks/edmonton-frame-ocr-probe-2026-08-14.md``):

  - the CURRENT speaker renders as accent-blue text (B-R ≈ +60) on a light
    panel; queued entries are near-neutral, spoken entries grey;
  - a countdown timer sits above the name: **frozen 05:00 = armed/queued,
    ticking = actually speaking** — the ticking gate is what makes the
    signal reliable (the clerk arms the queue 7–10 s before speech starts,
    and occasionally arms the wrong person);
  - panel geometry is NOT fixed (Meet reflows) — the panel is found by
    colour search over the full frame, never a hardcoded crop;
  - the timeline has real gaps (votes, procedural stretches) which stay
    unknown — identity is never smeared across a gap.

Two stages:

  Stage 8 — ``ocr_speaker_timeline`` — download the meeting video at 480p,
    pull the ~5 s YouTube keyframes (``-skip_frame nokey`` — no wasted
    decode), OCR the panel per frame with crop-dedup, gate on the ticking
    timer, and store an interval timeline in ``meetings.raw->'speaker_timeline'``.

  Stage 9 — ``apply_panel_attribution`` — align intervals against caption
    turns. The panel LEADS captions by 7–10 s (clerk arms at recognition
    ~2–3 s before speech; live CART captions lag audio ~5 s), so a caption
    turn is compared at ``start_seconds + PANEL_LEAD_SECS``. Roster-matched
    intervals attribute bare turns (attribution='panel', confidence 0.75)
    and audit already-attributed turns (disagreements are logged, never
    overwritten — text macros at 0.9 outrank the panel). Name-shaped
    non-roster intervals name staff turns (speaker_name_raw only,
    politician_id stays NULL).

Media comes from the derivative cache (``media_cache.ensure_derivatives``):
the source video is fetched once ever; persistent keyframes + audio serve
every future iteration offline. Fetch failures are memoized in
``meetings.raw->'fetch'`` with exponential backoff.
"""
from __future__ import annotations

import asyncio
import difflib
import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field as dc_field
from datetime import date
from typing import Optional

import orjson

from ..db import Database
from .escribe import CITIES, EscribeCity

log = logging.getLogger(__name__)

# The clerk panel leads the captions: ~2-3s recognition lead + ~5s CART
# caption lag (both measured 2026-08-14).
PANEL_LEAD_SECS = 8.0
ROSTER_MATCH_THRESHOLD = 0.85
PANEL_CONFIDENCE = 0.75

_TIMER_RE = re.compile(r"(\d{1,2})\s*:\s*(\d{2})")
# A non-roster OCR result that still looks like a person's name (staff /
# public speakers): 2-4 capitalised words, optionally "X. Surname".
_NAME_SHAPE_RE = re.compile(
    r"^(?:[A-Z]\.\s*)?[A-Z][a-zA-Z'\-]+(?:\s+[A-Z][a-zA-Z'\-]+){0,3}$",
)


@dataclass
class PanelStats:
    meetings_seen: int = 0
    timelines_built: int = 0
    download_failures: int = 0
    frames_processed: int = 0
    unique_crops_ocrd: int = 0
    intervals_stored: int = 0
    # apply stage
    turns_attributed: int = 0
    staff_named: int = 0
    disagreements: int = 0
    skipped_no_interval: int = 0


# ── Frame analysis (ported from the 2026-08-14 probe scripts) ──────


def _frame_candidates(arr) -> list[tuple[int, int, int, int]]:
    """Locate accent-blue text runs on a light panel. arr is an int HxWx3
    numpy array. Returns (x0, y0, x1, y1) boxes."""
    import numpy as np

    H, W, _ = arr.shape
    R, B = arr[:, :, 0], arr[:, :, 2]
    lum = arr.sum(axis=2) / 3
    text = (B - R > 30) & (lum < 160) & (B < 200)
    counts = text.sum(axis=1)
    bands: list[tuple[int, int]] = []
    inrun, start = False, 0
    for y in range(H):
        hot = counts[y] > 8
        if hot and not inrun:
            start, inrun = y, True
        elif not hot and inrun:
            inrun = False
            if 7 <= y - start <= 40:
                bands.append((start, y))
    if inrun and 7 <= H - start <= 40:
        bands.append((start, H))

    out: list[tuple[int, int, int, int]] = []
    for (y0, y1) in bands:
        xs = np.nonzero(text[y0:y1].sum(axis=0) > 0)[0]
        if len(xs) == 0:
            continue
        # Contiguous x-run clustering (gap > 30px = separate UI element) —
        # without this, unrelated blue text on the same row merges into the
        # crop and destroys OCR (probe finding: 0% → 100% on Council).
        clusters: list[tuple[int, int]] = []
        cs, prev = xs[0], xs[0]
        for x in xs[1:]:
            if x - prev > 30:
                clusters.append((cs, prev))
                cs = x
            prev = x
        clusters.append((cs, prev))
        for (x0, x1) in clusters:
            if x1 - x0 < 45:
                continue
            band = arr[max(0, y0 - 5):min(H, y1 + 5), x0:x1 + 1]
            if float(np.median(band.reshape(-1, 3).sum(axis=1) / 3)) < 175:
                continue  # must sit on a light panel
            px = arr[y0:y1, x0:x1 + 1].reshape(-1, 3)
            dark = px[px.sum(axis=1) / 3 < 170]
            if len(dark) < 25:
                continue
            m = dark.mean(axis=0)
            if m[2] - m[0] < 25:
                continue  # confirm accent-blue text
            out.append((int(x0), int(y0), int(x1), int(y1)))
    return out


def _tesseract(png_path: str, *extra: str) -> str:
    res = subprocess.run(
        ["tesseract", png_path, "-", "--psm", "7", "-l", "eng", *extra],
        capture_output=True, text=True,
    )
    return res.stdout.strip()


def _clean_ocr(t: str) -> str:
    t = re.sub(r"\(\d+\)", "", t)
    return re.sub(r"[^A-Za-z .\-']", "", t).strip()


def _roster_match(text: str, roster_names: list[str]) -> tuple[Optional[str], float]:
    c = _clean_ocr(text)
    if len(c) < 4:
        return None, 0.0
    best, score = None, 0.0
    for n in roster_names:
        r = difflib.SequenceMatcher(None, c.lower(), n.lower()).ratio()
        if r > score:
            best, score = n, r
    return best, score


class _FrameReader:
    """Per-meeting OCR context with crop dedup (the panel is static for
    most of a multi-minute turn — dedup cuts tesseract calls hugely)."""

    def __init__(self, roster_names: list[str], workdir: str):
        self.roster_names = roster_names
        self.workdir = workdir
        self._crop_cache: dict[str, str] = {}

    @staticmethod
    def load_norm(frame_path: str):
        """Decode + normalise to 480-height. Every geometry constant here
        (band heights 7-40px, x-run minimums, crop pads, timer-region
        offsets) was calibrated at 480p; ISI frames arrive at 720p where
        panel text bands run ~52px and fell straight through the height
        gate (dual-source validation caught it: 27 vs 60 intervals)."""
        from PIL import Image
        img = Image.open(frame_path).convert("RGB")
        if img.height > 520:
            w = round(img.width * 480 / img.height)
            img = img.resize((w, 480), Image.LANCZOS)
        return img

    def region_sig(self, frame_path: str, box):
        """Cheap change-detector signature for the known panel region —
        the user's scene-detection idea, scoped to the panel so the
        constantly-moving camera tiles can't defeat it."""
        import numpy as np
        from PIL import Image
        img = self.load_norm(frame_path)
        x0, y0, x1, y1 = box
        crop = img.crop((max(0, x0 - 8), max(0, y0 - 8), x1 + 8, y1 + 8)).convert("L")
        thumb = crop.resize((32, 8), Image.BILINEAR)
        return (np.asarray(thumb).astype(np.int16) // 8)

    def read_timer_only(self, frame_path: str, box) -> Optional[str]:
        img = self.load_norm(frame_path)
        return self._read_timer(img, (img.height, img.width), box)

    def read(self, frame_path: str) -> tuple[Optional[str], float, Optional[str], Optional[str], Optional[tuple]]:
        """→ (roster_name, score, raw_ocr_text, timer_str, best_box).
        roster_name is None for no-detection AND for non-roster (staff)
        names — check raw_ocr_text for the latter."""
        from PIL import Image
        import numpy as np

        img = self.load_norm(frame_path)
        arr = np.asarray(img).astype(int)
        best_name, best_score, best_raw, best_box = None, 0.0, None, None
        for box in _frame_candidates(arr):
            x0, y0, x1, y1 = box
            crop = img.crop((max(0, x0 - 5), max(0, y0 - 5), x1 + 5, y1 + 5)).convert("L")
            # Jitter-proof dedup key: JPEG noise defeats raw-byte hashing
            # (1,196 "unique" crops in 1,991 frames were mostly identical
            # text re-encoded). Downsample + quantise before hashing.
            thumb = crop.resize((64, 16), Image.BILINEAR)
            h = hashlib.md5((np.asarray(thumb) // 16).tobytes()).hexdigest()
            if h in self._crop_cache:
                txt = self._crop_cache[h]
            else:
                big = crop.resize((crop.width * 4, crop.height * 4), Image.LANCZOS)
                tmp = os.path.join(self.workdir, "_crop.png")
                big.save(tmp)
                txt = _tesseract(tmp)
                self._crop_cache[h] = txt
            name, score = _roster_match(txt, self.roster_names)
            if score > best_score:
                best_name, best_score, best_raw, best_box = name, score, txt, box
        if best_box is None:
            return None, 0.0, None, None, None
        timer = self._read_timer(img, arr.shape, best_box)
        if best_score >= ROSTER_MATCH_THRESHOLD:
            return best_name, best_score, best_raw, timer, best_box
        return None, best_score, best_raw, timer, best_box

    def _read_timer(self, img, shape, box) -> Optional[str]:
        """Countdown digits sit above the name box."""
        x0, y0, x1, y1 = box
        H, W = shape[0], shape[1]
        region = (max(0, x0 - 60), max(0, y0 - 170), min(W, x1 + 260), max(0, y0 - 15))
        if region[3] <= region[1]:
            return None
        crop = img.crop(region).convert("L")
        crop = crop.resize((crop.width * 2, crop.height * 2))
        tmp = os.path.join(self.workdir, "_timer.png")
        crop.save(tmp)
        # The region holds several UI lines — psm 6 (block), not psm 7.
        res = subprocess.run(
            ["tesseract", tmp, "-", "--psm", "6", "-l", "eng",
             "-c", "tessedit_char_whitelist=0123456789:O"],
            capture_output=True, text=True,
        )
        t = res.stdout.replace("O", "0")
        m = _TIMER_RE.search(t)
        return f"{int(m.group(1)):02d}:{m.group(2)}" if m else None


# ── Video → keyframes ───────────────────────────────────────────────






# ── Stage 8: build timelines ───────────────────────────────────────


def _samples_to_intervals(samples: list[dict]) -> list[dict]:
    """Collapse per-frame samples into speaking/armed intervals.

    A run of consecutive samples with the same identity becomes one
    interval; state='speaking' requires the timer to have CHANGED at least
    once within the run (the ticking gate), else state='armed'. Frames with
    no detection break runs — gaps stay unknown by construction.
    """
    intervals: list[dict] = []
    run: list[dict] = []

    def flush():
        if not run:
            return
        timers = [s["timer"] for s in run if s["timer"]]
        ticking = len(set(timers)) > 1
        intervals.append({
            "start": run[0]["t"],
            "end": run[-1]["t"],
            "name": run[0]["name"],
            "raw": run[0]["raw"],
            "state": "speaking" if ticking else "armed",
            "frames": len(run),
        })
        run.clear()

    for s in samples:
        ident = s["name"] or s["raw"]
        if not ident:
            flush()
            continue
        if run and (run[0]["name"] or run[0]["raw"]) != ident:
            flush()
        run.append(s)
    flush()
    return intervals


async def _roster_names(
    db: Database, city: EscribeCity, when=None,
) -> list[str]:
    """Full names for OCR fuzzy-matching, valid at `when` (date-aware so a
    2022 meeting's panel matches Sohi/Cartmell-era names, not today's)."""
    from .youtube_captions import roster_for_date, _roster_valid_for
    if when is None or _roster_valid_for(city.slug, when):
        rows = await db.fetch(
            """
            SELECT name FROM politicians
            WHERE level = 'municipal' AND province_territory = $1 AND source_id LIKE $2
            """,
            city.province_territory, f"opennorth:{city.slug}-city-council:%",
        )
        return [r["name"] for r in rows if r["name"]]
    d = when.date() if hasattr(when, "date") else when
    rows = await db.fetch(
        """
        SELECT DISTINCT p.name
        FROM politician_terms t JOIN politicians p ON p.id = t.politician_id
        WHERE t.level = 'municipal' AND t.province_territory = $1
          AND (p.source_id LIKE 'opennorth:' || $2 || '-city-council:%'
               OR p.source_id LIKE 'edmonton-socrata:%')
          AND t.started_at <= $3::date
          AND (t.ended_at IS NULL OR t.ended_at > $3::date)
        """,
        city.province_territory, city.slug, d,
    )
    return [r["name"] for r in rows if r["name"]]


# Panel-region change gating: force a full analysis at least every N
# gated frames (drift/reflow safety net — a moved panel also changes the
# old region, but belt and braces), and read the timer every Mth gated
# frame so the ticking gate still gets >=2 distinct values per run.
_GATE_FORCE_FULL_EVERY = 24
_GATE_TIMER_EVERY = 6
_GATE_DIFF_THRESHOLD = 1.0


def _ocr_frames_sync(frames_dir: str, times: list, roster: list) -> tuple:
    """CPU-bound frame loop, safe to run in a worker thread (tesseract is a
    subprocess; PIL/numpy release the GIL for the heavy parts). Returns
    (samples, n_unique_crops).

    Scene-detection gating (2026-08-15): the panel is static for ~85-90%
    of frames, so per frame we first diff just the last-known panel region
    (cheap decode + 32x8 thumbnail compare). Unchanged → carry the
    previous identity forward and skip colour-search/OCR entirely; the
    timer is still sampled every few gated frames for the ticking gate.
    """
    import numpy as np
    import tempfile as _tempfile
    samples = []
    with _tempfile.TemporaryDirectory(prefix="panelocr-") as tmpdir:
        reader = _FrameReader(roster, tmpdir)
        frame_files = sorted(os.listdir(frames_dir))
        last_box = None
        last_sig = None
        last_name = None
        last_staff = None
        gated_run = 0
        for t, fname in zip(times, frame_files):
            path = os.path.join(frames_dir, fname)
            if last_box is not None and gated_run < _GATE_FORCE_FULL_EVERY:
                sig = reader.region_sig(path, last_box)
                if (last_sig is not None and sig.shape == last_sig.shape
                        and float(np.abs(sig - last_sig).mean()) < _GATE_DIFF_THRESHOLD):
                    gated_run += 1
                    timer = None
                    if last_name and gated_run % _GATE_TIMER_EVERY == 0:
                        timer = reader.read_timer_only(path, last_box)
                    samples.append({
                        "t": round(t, 1), "name": last_name,
                        "raw": last_staff, "timer": timer,
                    })
                    continue
            name, score, raw, timer, box = reader.read(path)
            staff_raw = None
            if name is None and raw:
                cleaned = _clean_ocr(raw)
                if _NAME_SHAPE_RE.match(cleaned):
                    staff_raw = cleaned
            samples.append({
                "t": round(t, 1), "name": name, "raw": staff_raw, "timer": timer,
            })
            last_box = box
            last_sig = reader.region_sig(path, box) if box else None
            last_name = name
            last_staff = staff_raw
            gated_run = 0
        n_crops = len(reader._crop_cache)
    return samples, n_crops


async def cache_edmonton_media(
    db: Database, *, city_slug: str = "edmonton", limit: Optional[int] = None,
    workers: int = 1,
) -> PanelStats:
    """Acquisition-only pass: build derivative caches (audio + frames +
    alignment) for every speeches-bearing meeting, WITHOUT running OCR.

    Exists because voice attribution — the proven 16-point lever — needs
    only the audio derivative; OCR trails later as cheap gated CPU.
    `workers` parallelises the ISI lane (download of one meeting overlaps
    ffmpeg derivation of another; the CDN is unthrottled). The YouTube
    fallback stays single-file regardless — a module lock in media_cache
    serialises that lane. Failures memoized."""
    stats = PanelStats()
    city = CITIES[city_slug]
    caption_source = f"{city.source_system.split('-')[0]}-youtube-captions"
    rows = await db.fetch(
        f"""
        SELECT m.id::text AS id, m.video_url, m.source_meeting_id,
               m.raw->'fetch' AS fetch_memo,
               m.raw_captions_vtt AS vtt,
               m.raw->'media'->'isi' AS isi
        FROM meetings m
        WHERE m.source_system = $1
          AND m.video_url IS NOT NULL
          AND EXISTS (SELECT 1 FROM speeches s WHERE s.source_system = $2
                      AND s.meeting_id = m.id)
        ORDER BY m.started_at DESC
        {"LIMIT $3" if limit else ""}
        """,
        *([city.source_system, caption_source, limit] if limit
          else [city.source_system, caption_source]),
    )
    from .media_cache import (
        ensure_derivatives, fetch_backoff_active, record_fetch_outcome,
        find_cache,
    )
    # Lane-aware admission: ISI meetings share the parallel pool; ISI-less
    # meetings (YouTube lane, throttled + serialised by the media_cache
    # module lock) get exactly one slot so a run of them can't occupy the
    # pool and collapse ISI concurrency back to serial.
    sem_isi = asyncio.Semaphore(max(1, workers))
    sem_yt = asyncio.Semaphore(1)

    async def _one(r) -> None:
        stats.meetings_seen += 1
        isi = r["isi"]
        if isinstance(isi, str):
            isi = orjson.loads(isi)
        video_id = r["video_url"].split("v=")[-1].split("&")[0]
        if find_cache(video_id, (isi or {}).get("etag")):
            stats.timelines_built += 1  # reused as cached counter here
            return
        memo = r["fetch_memo"]
        if isinstance(memo, str):
            memo = orjson.loads(memo)
        if fetch_backoff_active(memo):
            stats.skipped_no_interval += 1
            return
        lane = sem_isi if (isi and isi.get("url") and isi.get("etag")) else sem_yt
        async with lane:
            # One bad meeting (corrupt download, odd codec) must not kill a
            # multi-day acquisition run — degrade to a memoized failure.
            try:
                paths = await ensure_derivatives(r["video_url"], isi=isi, vtt_text=r["vtt"])
            except Exception as exc:
                log.warning("derivation crashed for meeting=%s: %s", r["source_meeting_id"], exc)
                paths = None
        if not paths:
            await record_fetch_outcome(db, r["id"], ok=False, error="media fetch failed")
            stats.download_failures += 1
            return
        await record_fetch_outcome(db, r["id"], ok=True)
        stats.timelines_built += 1
        log.info("cached media for meeting=%s (%s)", r["source_meeting_id"],
                 "isi" if "/isi/" in paths["dir"] else "youtube")

    await asyncio.gather(*(_one(r) for r in rows))
    return stats


async def ocr_speaker_timeline(
    db: Database, *, city_slug: str = "edmonton", limit: Optional[int] = None,
    force: bool = False, workers: int = 3, cached_only: bool = False,
) -> PanelStats:
    """Stage 8 — build the on-screen speaker timeline for meetings that
    have a video and caption speeches but no timeline yet.

    Pipelined: ONE producer acquires media serially (single-connection
    politeness toward both ISI and YouTube) while `workers` consumer
    threads OCR already-cached meetings concurrently — downloads and CPU
    overlap instead of serialising (~12 CPU-min/meeting OCR was the wall).
    """
    stats = PanelStats()
    city = CITIES[city_slug]
    caption_source = f"{city.source_system.split('-')[0]}-youtube-captions"
    roster_by_date: dict = {}

    rows = await db.fetch(
        f"""
        SELECT m.id::text AS id, m.video_url, m.source_meeting_id,
               m.started_at, m.raw->'fetch' AS fetch_memo,
               m.raw_captions_vtt AS vtt,
               m.raw->'media'->'isi' AS isi
        FROM meetings m
        WHERE m.source_system = $1
          AND m.video_url IS NOT NULL
          {"" if force else "AND m.raw->'speaker_timeline' IS NULL"}
          AND EXISTS (SELECT 1 FROM speeches s WHERE s.source_system = $2
                      AND s.meeting_id = m.id)
        ORDER BY m.started_at DESC
        {"LIMIT $3" if limit else ""}
        """,
        *([city.source_system, caption_source, limit] if limit
          else [city.source_system, caption_source]),
    )

    from .media_cache import (
        ensure_derivatives, fetch_backoff_active, record_fetch_outcome,
        load_meta_from, find_cache,
    )
    import concurrent.futures

    queue: asyncio.Queue = asyncio.Queue(maxsize=workers * 2)
    loop = asyncio.get_running_loop()
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=workers)

    async def producer():
        for r in rows:
            stats.meetings_seen += 1
            memo = r["fetch_memo"]
            if isinstance(memo, str):
                memo = orjson.loads(memo)
            if fetch_backoff_active(memo):
                stats.skipped_no_interval += 1
                continue
            isi = r["isi"]
            if isinstance(isi, str):
                isi = orjson.loads(isi)
            if cached_only:
                # Trail-behind mode: only OCR meetings whose derivative
                # cache is already complete (meta.json is written last,
                # so its presence == fully derived). Never derives, so
                # it can run concurrently with cache-edmonton-media
                # without dir races; skipped meetings are picked up on
                # a later pass.
                video_id = r["video_url"].split("v=")[-1].split("&")[0]
                paths = find_cache(video_id, (isi or {}).get("etag"))
                if not paths:
                    stats.skipped_no_interval += 1
                    continue
            else:
                try:
                    paths = await ensure_derivatives(
                        r["video_url"], isi=isi, vtt_text=r["vtt"],
                    )
                except Exception as exc:
                    log.warning("derivation crashed for meeting=%s: %s",
                                r["source_meeting_id"], exc)
                    paths = None
                if not paths:
                    await record_fetch_outcome(db, r["id"], ok=False, error="media fetch failed")
                    stats.download_failures += 1
                    continue
                await record_fetch_outcome(db, r["id"], ok=True)
            if not os.path.isdir(paths["frames_dir"]) or not os.listdir(paths["frames_dir"]):
                # Frames were pruned after a previous successful OCR pass.
                # A force re-OCR needs a fresh derive: delete the cache
                # dir (meta included) so the ladder re-fetches from ISI.
                log.info("frames pruned for meeting=%s — skipping (delete "
                         "%s to force a re-derive)", r["source_meeting_id"],
                         paths["dir"])
                stats.skipped_no_interval += 1
                continue
            await queue.put((r, paths))
        for _ in range(workers):
            await queue.put(None)

    async def consumer():
        while True:
            item = await queue.get()
            if item is None:
                return
            r, paths = item
            with open(paths["times"]) as fh:
                times = json.load(fh)["keyframe_pts"]
            rkey = r["started_at"].date() if r["started_at"] else None
            if rkey not in roster_by_date:
                roster_by_date[rkey] = await _roster_names(db, city, when=r["started_at"])
            roster = roster_by_date[rkey]
            samples, n_crops = await loop.run_in_executor(
                pool, _ocr_frames_sync, paths["frames_dir"], times, roster,
            )
            stats.frames_processed += len(samples)
            stats.unique_crops_ocrd += n_crops
            intervals = _samples_to_intervals(samples)
            cache_meta = load_meta_from(paths) or {}
            timeline = {
                "version": 2,
                "frames": len(samples),
                "cadence_secs": 5,
                # Interval times are in the SOURCE video's timebase;
                # consumers convert caption timestamps with this offset
                # (audio/video_time = caption_time + offset). None →
                # legacy +8s lead assumption.
                "media_source": cache_meta.get("source", "youtube"),
                "caption_offset_s": cache_meta.get("caption_offset_s"),
                # Carry the alignment's provenance, not just its answer.
                # Until 2026-08-19 the score that justified trusting an
                # offset lived only in on-disk meta.json and never reached
                # Postgres, so a corpus-wide misalignment (216 ISI meetings
                # whose true offset sat outside the old ±600s search window)
                # was invisible to SQL and took a GPU study to find.
                "align_score": cache_meta.get("align_score"),
                "align_method": cache_meta.get("align_method", "vad"),
                "identity_peak": cache_meta.get("identity_peak"),
                "intervals": intervals,
            }
            await db.execute(
                """
                UPDATE meetings
                SET raw = raw || jsonb_build_object('speaker_timeline', $1::jsonb),
                    updated_at = now()
                WHERE id = $2::uuid
                """,
                orjson.dumps(timeline).decode(), r["id"],
            )
            stats.timelines_built += 1
            stats.intervals_stored += len(intervals)
            speaking = sum(1 for iv in intervals if iv["state"] == "speaking")
            log.info("timeline for meeting=%s (%s): %d intervals (%d speaking)",
                     r["source_meeting_id"], timeline["media_source"],
                     len(intervals), speaking)
            # Frames were only ever OCR input — with the timeline stored
            # they're dead weight (~140-300MB/meeting; ~92% of the cache
            # dir). Audio + times + meta stay for voice and audits;
            # frames re-derive from the ISI CDN if ever needed again.
            import shutil as _shutil
            _shutil.rmtree(paths["frames_dir"], ignore_errors=True)

    try:
        await asyncio.gather(producer(), *[consumer() for _ in range(workers)])
    finally:
        pool.shutdown(wait=True)
    return stats


# ── Stage 9: apply to caption turns ────────────────────────────────


async def apply_panel_attribution(
    db: Database, *, city_slug: str = "edmonton",
) -> PanelStats:
    """Stage 9 — AUDIT caption attributions against the panel timeline.

    Attribution itself happens in the collapse pipeline
    (``youtube_captions._apply_block_alternation`` consumes the timeline
    via ``make_panel_owner_lookup`` during reparse/fetch) because the panel
    names the floor OWNER, not the turn-level speaker — the member's
    countdown ticks straight through staff answers, so covered turns must
    go through the alternation engine, never be attributed directly (the
    first cut of this stage did exactly that and credited staff answers to
    the questioner).

    This stage compares attributed turns against the covering interval and
    logs disagreements (never overwrites), then reconciles the chunk
    denorm. Short turns and interval leading edges are skipped — the panel
    leads captions by ~8s, so those zones disagree structurally.
    """
    stats = PanelStats()
    city = CITIES[city_slug]
    caption_source = f"{city.source_system.split('-')[0]}-youtube-captions"

    roster_rows = await db.fetch(
        """
        SELECT id::text AS id, name FROM politicians
        WHERE level = 'municipal' AND province_territory = $1 AND source_id LIKE $2
        """,
        city.province_territory, f"opennorth:{city.slug}-city-council:%",
    )
    by_name = {r["name"]: r["id"] for r in roster_rows}

    meetings = await db.fetch(
        """
        SELECT id::text AS id, video_url, source_meeting_id,
               raw->'speaker_timeline' AS timeline
        FROM meetings
        WHERE source_system = $1 AND raw->'speaker_timeline' IS NOT NULL
        """,
        city.source_system,
    )
    for m in meetings:
        stats.meetings_seen += 1
        timeline = orjson.loads(m["timeline"]) if isinstance(m["timeline"], str) else m["timeline"]
        speaking = [iv for iv in timeline["intervals"] if iv["state"] == "speaking"]
        if not speaking:
            continue
        # Same dynamic lead as make_panel_owner_lookup: offset + 13, with
        # the legacy +8 fallback for timelines without a measured offset.
        _off = timeline.get("caption_offset_s")
        panel_lead = (_off + 13.0) if _off is not None else PANEL_LEAD_SECS

        turns = await db.fetch(
            """
            SELECT id::text AS id, politician_id::text AS politician_id,
                   speaker_name_raw, raw->>'attribution' AS attribution,
                   (raw->>'start_seconds')::float AS start_s,
                   (raw->>'end_seconds')::float AS end_s
            FROM speeches
            WHERE source_system = $1 AND meeting_id = $2::uuid
            ORDER BY sequence
            """,
            caption_source, m["id"],
        )
        for t in turns:
            probe_t = (t["start_s"] or 0) + panel_lead
            iv = next((iv for iv in speaking if iv["start"] <= probe_t <= iv["end"]), None)
            if iv is None:
                stats.skipped_no_interval += 1
                continue
            # Boundary guard: the panel flips 7-10s before the new speaker's
            # captions, so a short chair/previous-speaker turn near a
            # handover lands inside the NEXT speaker's interval. Require the
            # probe point to sit clear of the interval start, and skip
            # sub-3s turns entirely (pilot: all 8 false disagreements were
            # this shape).
            turn_dur = (t["end_s"] or 0) - (t["start_s"] or 0)
            if probe_t < iv["start"] + 5.0 or turn_dur < 3.0:
                stats.skipped_no_interval += 1
                continue
            if not iv["name"]:
                continue
            pid = by_name.get(iv["name"])
            if pid and t["politician_id"] and t["politician_id"] != pid \
                    and t["attribution"] in ("macro", "recognition"):
                # Owner-tier attributions (alternation/panel) SHOULD show
                # the owner and staff turns show nothing — only direct
                # text-identified turns are meaningfully auditable here.
                stats.disagreements += 1
                log.info(
                    "panel disagreement: meeting=%s turn=%s text-says=%s panel-says=%s attr=%s",
                    m["source_meeting_id"], t["id"], t["speaker_name_raw"],
                    iv["name"], t["attribution"],
                )

    # No denorm sync here: this stage is audit-only and never writes
    # politician_id — the sync lives at the end of
    # resolve_meeting_caption_speakers, the stage that does.
    log.info("panel audit: disagreements=%d no-interval=%d",
             stats.disagreements, stats.skipped_no_interval)
    return stats
