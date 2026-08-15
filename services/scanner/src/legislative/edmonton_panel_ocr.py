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

    def read(self, frame_path: str) -> tuple[Optional[str], float, Optional[str], Optional[str]]:
        """→ (roster_name, score, raw_ocr_text, timer_str). roster_name is
        None for no-detection AND for non-roster (staff) names — check
        raw_ocr_text for the latter."""
        from PIL import Image
        import numpy as np

        img = Image.open(frame_path).convert("RGB")
        arr = np.asarray(img).astype(int)
        best_name, best_score, best_raw, best_box = None, 0.0, None, None
        for box in _frame_candidates(arr):
            x0, y0, x1, y1 = box
            crop = img.crop((max(0, x0 - 5), max(0, y0 - 5), x1 + 5, y1 + 5)).convert("L")
            h = hashlib.md5(crop.tobytes()).hexdigest()
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
            return None, 0.0, None, None
        timer = self._read_timer(img, arr.shape, best_box)
        if best_score >= ROSTER_MATCH_THRESHOLD:
            return best_name, best_score, best_raw, timer
        return None, best_score, best_raw, timer

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


async def _roster_names(db: Database, city: EscribeCity) -> list[str]:
    rows = await db.fetch(
        """
        SELECT name FROM politicians
        WHERE level = 'municipal' AND province_territory = $1 AND source_id LIKE $2
        """,
        city.province_territory, f"opennorth:{city.slug}-city-council:%",
    )
    return [r["name"] for r in rows if r["name"]]


async def ocr_speaker_timeline(
    db: Database, *, city_slug: str = "edmonton", limit: Optional[int] = None,
    force: bool = False,
) -> PanelStats:
    """Stage 8 — build the on-screen speaker timeline for meetings that
    have a video and caption speeches but no timeline yet."""
    stats = PanelStats()
    city = CITIES[city_slug]
    caption_source = f"{city.source_system.split('-')[0]}-youtube-captions"
    roster = await _roster_names(db, city)

    rows = await db.fetch(
        f"""
        SELECT m.id::text AS id, m.video_url, m.source_meeting_id,
               m.raw->'fetch' AS fetch_memo
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
    )
    for r in rows:
        stats.meetings_seen += 1
        memo = r["fetch_memo"]
        if isinstance(memo, str):
            memo = orjson.loads(memo)
        if fetch_backoff_active(memo):
            stats.skipped_no_interval += 1  # reused as skip counter here
            continue
        # Media comes from the derivative cache: one fetch per meeting,
        # ever; frames + audio persist for every future iteration.
        paths = await ensure_derivatives(r["video_url"])
        if not paths:
            await record_fetch_outcome(db, r["id"], ok=False, error="media fetch failed")
            stats.download_failures += 1
            continue
        await record_fetch_outcome(db, r["id"], ok=True)
        with open(paths["times"]) as fh:
            times = json.load(fh)["keyframe_pts"]
        frames_dir = paths["frames_dir"]
        frame_files = sorted(os.listdir(frames_dir))
        n_frames = len(frame_files)
        with tempfile.TemporaryDirectory(prefix="panelocr-") as tmpdir:
            reader = _FrameReader(roster, tmpdir)
            samples = []
            for t, fname in zip(times, frame_files):
                name, score, raw, timer = reader.read(os.path.join(frames_dir, fname))
                staff_raw = None
                if name is None and raw:
                    cleaned = _clean_ocr(raw)
                    if _NAME_SHAPE_RE.match(cleaned):
                        staff_raw = cleaned
                samples.append({
                    "t": round(t, 1), "name": name, "raw": staff_raw, "timer": timer,
                })
                stats.frames_processed += 1
            stats.unique_crops_ocrd += len(reader._crop_cache)
        intervals = _samples_to_intervals(samples)

        timeline = {
            "version": 1,
            "frames": n_frames,
            "cadence_secs": 5,
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
        log.info("timeline for meeting=%s: %d intervals (%d speaking) from %d frames",
                 r["source_meeting_id"], len(intervals), speaking, n_frames)
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
            probe_t = (t["start_s"] or 0) + PANEL_LEAD_SECS
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
