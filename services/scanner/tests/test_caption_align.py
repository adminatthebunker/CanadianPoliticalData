"""Property tests for the caption↔audio aligner.

These exist because of the 2026-08-19 incident: the aligner searched a
hard-coded ±600 s window, but ISI encoder streams start long before the
meeting, so for 216 of 405 Edmonton ISI meetings the true offset was
outside the searched range entirely. argmax then returned the tallest
WRONG peak, and the peak-over-noise score still cleared MIN_SCORE — a
confidently-wrong offset that silently mis-sliced every voice embedding.

The two regressions worth locking down:
  1. a shift far beyond ±600 s must still be recovered;
  2. a result must not be `trusted` when a rival peak is comparably tall.
"""
from __future__ import annotations

import os
import subprocess
import tempfile

import numpy as np
import pytest

from src.legislative.caption_align import (
    MIN_OVERLAP_S,
    TRACK_HZ,
    align_captions_to_audio,
)

SR = 16000


def _vtt(segments) -> str:
    """Build a VTT whose cues carry varying text length, since the tracks
    correlate text density rather than binary presence."""
    def ts(t):
        h, r = divmod(t, 3600)
        m, s = divmod(r, 60)
        return f"{int(h):02d}:{int(m):02d}:{s:06.3f}"

    out = ["WEBVTT", ""]
    for i, (a, b) in enumerate(segments):
        out += [f"{ts(a)} --> {ts(b)}", "word " * (3 + (i * 7) % 23), ""]
    return "\n".join(out)


def _write_audio(path, duration_s, speech_segments, shift_s):
    """Noise floor with louder 'speech' bursts placed at caption time +
    shift, i.e. audio_time = caption_time + shift."""
    rng = np.random.default_rng(0)
    n = int(duration_s * SR)
    pcm = rng.normal(0, 0.002, n).astype(np.float32)
    for a, b in speech_segments:
        s = int((a + shift_s) * SR)
        e = int((b + shift_s) * SR)
        s, e = max(0, s), min(n, e)
        if e > s:
            pcm[s:e] += rng.normal(0, 0.25, e - s).astype(np.float32)
    data = np.clip(pcm, -1, 1)
    raw = (data * 32767).astype("<i2").tobytes()
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "s16le", "-ar", str(SR),
         "-ac", "1", "-i", "-", path],
        input=raw, check=True, capture_output=True,
    )


def _segments(start, count, on=6.0, gap=9.0):
    """Irregular on/off structure — a perfectly periodic pattern would be
    genuinely ambiguous under shift, which is not what we're testing."""
    segs, t = [], start
    for i in range(count):
        d = on + (i % 5) * 1.5
        segs.append((t, t + d))
        t += d + gap + (i % 7) * 2.0
    return segs


@pytest.mark.parametrize("shift", [-30.0, 120.0, 900.0, 1800.0])
def test_recovers_shift_beyond_the_old_600s_window(tmp_path, shift):
    """The regression that caused the incident: shifts of 900 s and 1800 s
    were unreachable under the old fixed ±600 s search window."""
    segs = _segments(60.0, 90)
    cap_end = segs[-1][1]
    duration = cap_end + max(shift, 0) + MIN_OVERLAP_S + 120
    wav = str(tmp_path / "a.wav")
    _write_audio(wav, duration, segs, shift)

    r = align_captions_to_audio(_vtt(segs), wav)
    assert r.offset_s == pytest.approx(shift, abs=2.0), (
        f"wanted {shift}s, got {r.offset_s}s (score={r.score:.1f}, "
        f"prominence={r.prominence:.2f})")
    assert r.trusted


def test_refuses_when_overlap_is_impossible(tmp_path):
    """Captions far longer than the audio cannot overlap by MIN_OVERLAP_S;
    the aligner must decline rather than invent an offset."""
    segs = _segments(60.0, 200)
    wav = str(tmp_path / "a.wav")
    _write_audio(wav, 120.0, segs[:3], 0.0)
    r = align_captions_to_audio(_vtt(segs), wav)
    assert not r.trusted
    assert r.offset_s == 0.0


def test_untrusted_when_a_rival_peak_is_comparable(tmp_path):
    """A self-similar recording — the same speech pattern repeated twice —
    is genuinely ambiguous. peak/noise happily clears MIN_SCORE here; only
    the prominence gate catches it."""
    segs = _segments(60.0, 40)
    cap_end = segs[-1][1]
    period = cap_end + 200.0
    duration = period * 2 + MIN_OVERLAP_S + 200
    wav = str(tmp_path / "a.wav")
    doubled = list(segs) + [(a + period, b + period) for a, b in segs]
    _write_audio(wav, duration, doubled, 30.0)

    r = align_captions_to_audio(_vtt(segs), wav)
    assert r.prominence < 1.25 or not r.trusted, (
        f"ambiguous alignment reported as trustworthy "
        f"(score={r.score:.1f}, prominence={r.prominence:.2f})")


def test_offset_sign_convention(tmp_path):
    """audio_time = caption_time + offset_s. Consumers depend on this
    sign (voice slicing uses caption_start + offset); flipping it silently
    mis-slices every window."""
    segs = _segments(90.0, 60)
    wav = str(tmp_path / "a.wav")
    shift = 45.0
    _write_audio(wav, segs[-1][1] + shift + MIN_OVERLAP_S + 120, segs, shift)
    r = align_captions_to_audio(_vtt(segs), wav)
    assert r.offset_s > 0
