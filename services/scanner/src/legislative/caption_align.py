"""Caption↔audio offset via VAD cross-correlation (the ffsubsync method).

Two independent time errors exist between a meeting's captions and any
audio we derive:

  - the **source offset**: ISI CDN recordings and YouTube VODs of the same
    meeting start at different wall-clock moments (measured ±minutes, both
    signs), while every caption timestamp we hold is YouTube-based;
  - the **CART lag**: live stenography trails the audio by a variable
    ~3-8 s (mean ≈5 s).

One measurement absorbs both: turn the VTT cue times into a binary
speech/silence track, run an energy VAD over the derived audio, and find
the shift that maximises their cross-correlation. The resulting
``caption_offset_s`` satisfies

    audio_time ≈ caption_time + caption_offset_s

Captions run LATE (an utterance at audio time u gets its cue at ≈u+5), so
a YouTube-sourced cache measures offset ≈ **−5 s**, and an ISI-sourced
cache folds the source shift into the same number. Derived consumer
parameters: voice slicing uses ``audio_start = caption_start + offset``;
the clerk-panel probe lead becomes ``offset + 13.0`` (which reproduces the
empirically-calibrated +8 s at the YouTube offset of −5).
Precision ±1-2 s — inside both the clerk-panel margins and the voice
plateau (4.75-7.25 s tolerance, diarization PoC). Full word-level forced
alignment (plan P5) remains the eventual upgrade; this stage exists to
de-gate ISI acquisition without it.

A low correlation-peak score means the alignment cannot be trusted
(silent recording, mismatched asset): callers must treat the offset as
unknown and keep that meeting on the YouTube lane.
"""
from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass
from typing import Optional

log = logging.getLogger(__name__)

TRACK_HZ = 4                 # 250 ms resolution — plenty for ±1-2 s targets
SEARCH_WINDOW_S = 600.0      # offsets beyond ±10 min are asset mismatches
MIN_SCORE = 3.0              # peak must stand this far above track noise

_CUE_RE = re.compile(
    r"^(\d+):(\d{2}):(\d{2})\.(\d{3})\s+-->\s+(\d+):(\d{2}):(\d{2})\.(\d{3})",
    re.MULTILINE,
)


@dataclass
class AlignResult:
    offset_s: float
    score: float

    @property
    def trusted(self) -> bool:
        return self.score >= MIN_SCORE


def _highpass(track, window_s: float = 60.0):
    """Remove the slow envelope (moving-average subtraction). Roll-up CC is
    near-continuous, so a raw presence track is basically one long
    rectangle — correlation then locks on envelope overlap at lag≈0
    regardless of the true shift (caught by the synthetic-shift property
    test). Only minute-scale STRUCTURE (pauses, density changes, recesses)
    carries alignment information."""
    import numpy as np
    w = max(3, int(window_s * TRACK_HZ))
    kernel = np.ones(w, dtype=np.float32) / w
    baseline = np.convolve(track, kernel, mode="same")
    return track - baseline


def vtt_speech_track(vtt_text: str, n_samples: int):
    """Continuous caption text-density (chars/sec) at TRACK_HZ, high-passed.
    Density beats binary presence for roll-up CC: cue text length tracks
    speech rate, giving real structure to correlate."""
    import numpy as np
    track = np.zeros(n_samples, dtype=np.float32)
    for m in _CUE_RE.finditer(vtt_text):
        start = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3)) + int(m.group(4)) / 1000
        end = int(m.group(5)) * 3600 + int(m.group(6)) * 60 + int(m.group(7)) + int(m.group(8)) / 1000
        # cue text = lines until the next blank line after the timestamp
        tail = vtt_text[m.end():m.end() + 400]
        text = tail.split("\n\n", 1)[0]
        chars = len(re.sub(r"<[^>]+>|\s+", "", text))
        a = max(0, int(start * TRACK_HZ))
        b = min(n_samples, max(a + 1, int(end * TRACK_HZ)))
        if b > a:
            track[a:b] += chars / (b - a)
    return _highpass(track)


def audio_vad_track(audio_path: str):
    """Continuous log-energy track at TRACK_HZ, high-passed, from any
    ffmpeg-readable audio (the cache's 16 kHz opus)."""
    import numpy as np
    res = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", audio_path,
         "-f", "s16le", "-ac", "1", "-ar", "16000", "-"],
        capture_output=True,
    )
    if res.returncode != 0 or not res.stdout:
        raise RuntimeError(f"audio decode failed: {res.stderr[:200]!r}")
    pcm = np.frombuffer(res.stdout, dtype=np.int16).astype(np.float32) / 32768.0
    frame = 16000 // TRACK_HZ
    n = len(pcm) // frame
    if n == 0:
        raise RuntimeError("audio too short")
    energy = (pcm[: n * frame].reshape(n, frame) ** 2).mean(axis=1)
    loge = np.log10(energy + 1e-10)
    return _highpass(loge)


def align_captions_to_audio(vtt_text: str, audio_path: str) -> AlignResult:
    """→ AlignResult(offset_s, score). offset such that
    audio_time ≈ caption_time + offset_s. Check ``.trusted``."""
    import numpy as np
    if len(_CUE_RE.findall(vtt_text)) < 50:
        return AlignResult(0.0, 0.0)  # too few cues — nothing to lock onto
    audio = audio_vad_track(audio_path)
    n = len(audio)
    caps = vtt_speech_track(vtt_text, n)

    a = audio - audio.mean()
    c = caps - caps.mean()
    # FFT cross-correlation, full — then restrict to the search window.
    size = 1
    while size < 2 * n:
        size *= 2
    fa = np.fft.rfft(a, size)
    fc = np.fft.rfft(c, size)
    corr = np.fft.irfft(fa * np.conj(fc), size)
    # corr[k] = Σ a[i]·c[i-k] (circular over the padded length `size`):
    # positive lags k live at indices [0, k]; NEGATIVE lags live at
    # indices size-k — NOT at n+k (the padded length exceeds 2n, and
    # misreading that region cost a debugging round via the synthetic-
    # shift property test). offset = +k/HZ means captions must be shifted
    # right to match audio, i.e. audio_time = caption_time + offset.
    window = int(SEARCH_WINDOW_S * TRACK_HZ)
    lags_w = np.arange(-window, window + 1)
    idx = np.where(lags_w >= 0, lags_w, size + lags_w)
    corr_w = corr[idx]
    peak_i = int(np.argmax(corr_w))
    peak = float(corr_w[peak_i])
    noise = float(np.median(np.abs(corr_w))) + 1e-9
    score = peak / noise
    offset = float(lags_w[peak_i]) / TRACK_HZ
    return AlignResult(offset_s=offset, score=score)
