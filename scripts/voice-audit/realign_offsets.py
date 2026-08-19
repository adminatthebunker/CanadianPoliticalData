#!/usr/bin/env python3
"""Recover per-meeting caption->audio offsets by SPEAKER IDENTITY.

Why this exists
---------------
``caption_align.align_captions_to_audio`` cross-correlates speech ENERGY
inside a hard-coded ``SEARCH_WINDOW_S = 600`` window. ISI assets are raw
encoder streams that start well before the meeting, so for 216 of 405
Edmonton ISI meetings the true offset lies OUTSIDE that window entirely —
the aligner cannot reach the right answer, takes an unconditional argmax
over the wrong range, and its peak/median score still clears MIN_SCORE.
The bad offset then slices every voice embedding window from the wrong
moment, so the audio is not the person the caption names.

Identity is a much stronger alignment signal than energy, and it is
immune to the self-similarity (recesses, roll calls) that traps
cross-correlation. For each meeting we embed a sliding window across the
cached audio ONCE, then sweep candidate offsets asking: at which offset
do the macro/recognition-labelled turns actually sound like the
councillor the caption names?

Read-only by default. ``--apply`` is a separate, later step — this script
only ever writes its JSON report.

Usage:
  ./.venv/bin/python realign_offsets.py --report out.json           # all ISI
  ./.venv/bin/python realign_offsets.py --calibrate --limit 40      # known-good only
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from collections import defaultdict

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
MEDIA = os.environ.get(
    "MEDIA_CACHE_DIR", os.path.abspath(os.path.join(HERE, "..", "..", "media-cache")))

SR = 16000
WIN = 4.0            # embedding window length (s)
COARSE_HOP = 15.0    # stride for the full-range sweep
FINE_HOP = 3.0       # stride for the refinement pass
FINE_SPAN = 150.0    # +- around the coarse winner to refine
MIN_OVERLAP = 600.0  # caption span and audio must overlap by at least this
MIN_LABELS = 8       # meetings with fewer labelled turns are not decidable
HALF_MIN_LABELS = 4  # per-half minimum for the drift check
ENROL_ATTR = ("macro", "recognition")
MIN_ENROL = 5        # samples needed before a councillor gets a centroid

# Accept rule — calibrated against known-good meetings (see --calibrate).
ACCEPT_PEAK = 0.45       # top-1 agreement at the winning offset
ACCEPT_RATIO = 3.0       # winning peak vs the sweep's baseline
ACCEPT_DRIFT = 10.0      # |first-half - second-half| best offset (s)
CONFIRM_TOL = 15.0       # |recovered - stored| within this => "confirmed"


# --------------------------------------------------------------------------
# cache discovery
# --------------------------------------------------------------------------
def load_media_meta() -> tuple[dict, dict]:
    meta, dirs = {}, {}
    for root, _, files in os.walk(MEDIA):
        if "meta.json" not in files:
            continue
        try:
            j = json.load(open(os.path.join(root, "meta.json")))
        except Exception:
            continue
        m = re.search(r"v=([A-Za-z0-9_-]{11})", j.get("video_url", ""))
        if m:
            meta[m.group(1)] = j
            dirs[m.group(1)] = root
    return meta, dirs


def load_npz(vid):
    p = os.path.join(CACHE, f"{vid}.npz")
    if not os.path.exists(p):
        return None
    try:
        z = np.load(p, allow_pickle=True)
        E = z["embeddings"]
        return E / (np.linalg.norm(E, axis=1, keepdims=True) + 1e-9), \
            json.loads(str(z["meta"]))
    except Exception:
        return None


class Bank:
    """Per-councillor centroid bank that can exclude one meeting's rows.

    Kept as sums+counts so a meeting can be subtracted in O(1) — probing a
    meeting whose own turns helped build the bank would otherwise score
    itself and inflate calibration.
    """

    def __init__(self):
        self.sums = defaultdict(lambda: None)
        self.counts = defaultdict(int)
        self.by_meeting = defaultdict(lambda: defaultdict(
            lambda: [None, 0]))       # vid -> name -> [sum, n]

    def add(self, vid, name, vec):
        self.sums[name] = vec.copy() if self.sums[name] is None \
            else self.sums[name] + vec
        self.counts[name] += 1
        slot = self.by_meeting[vid][name]
        slot[0] = vec.copy() if slot[0] is None else slot[0] + vec
        slot[1] += 1

    def matrix(self, exclude_vid=None):
        names, rows = [], []
        drop = self.by_meeting.get(exclude_vid, {}) if exclude_vid else {}
        for n in sorted(self.sums):
            s, c = self.sums[n], self.counts[n]
            if n in drop:
                s = s - drop[n][0]
                c -= drop[n][1]
            if c < MIN_ENROL:
                continue
            v = s / c
            names.append(n)
            rows.append(v / (np.linalg.norm(v) + 1e-9))
        return names, (np.vstack(rows) if rows else np.zeros((0, 192)))


# --------------------------------------------------------------------------
# embedding
# --------------------------------------------------------------------------
def decode(opus):
    with tempfile.TemporaryDirectory(prefix="realign-") as td:
        wav = os.path.join(td, "a.wav")
        subprocess.run(["ffmpeg", "-v", "error", "-i", opus, "-ar", str(SR),
                        "-ac", "1", wav], check=True, capture_output=True)
        import soundfile as sf
        audio, sr = sf.read(wav, dtype="float32")
    assert sr == SR
    return audio


def embed_at(audio, clf, dev, starts):
    """Embed WIN-second windows beginning at each start (seconds)."""
    import torch
    w = int(WIN * SR)
    keep, out, B = [], [], 64
    valid = [s for s in starts if 0 <= s and int(s * SR) + w <= len(audio)]
    for i in range(0, len(valid), B):
        chunk = valid[i:i + B]
        batch = np.stack([audio[int(s * SR):int(s * SR) + w] for s in chunk])
        with torch.no_grad():
            e = clf.encode_batch(torch.from_numpy(batch).to(dev)).squeeze(1).cpu().numpy()
        out.append(e)
        keep.extend(chunk)
    if not out:
        return np.array([]), np.zeros((0, 192))
    E = np.vstack(out)
    return np.array(keep), E / (np.linalg.norm(E, axis=1, keepdims=True) + 1e-9)


def sweep(starts, best_idx, labels, name_idx, grid, hop, min_labels=MIN_LABELS):
    """Top-1 agreement for every candidate offset. Vectorised.

    labels: list of (name, caption_start). An offset maps caption time t to
    audio time t+o; we look up the window covering that audio time.
    """
    if len(starts) == 0 or not labels:
        return np.full(len(grid), np.nan)
    t = np.array([l[1] for l in labels], dtype=float)          # (L,)
    want = np.array([name_idx.get(l[0], -1) for l in labels])  # (L,)
    ok = want >= 0
    if ok.sum() < min_labels:
        return np.full(len(grid), np.nan)
    t, want = t[ok], want[ok]
    base = starts[0]
    # window index for each (offset, label)
    idx = np.rint(((t[None, :] + grid[:, None]) - base) / hop).astype(np.int64)
    valid = (idx >= 0) & (idx < len(best_idx))
    idx = np.clip(idx, 0, len(best_idx) - 1)
    hit = (best_idx[idx] == want[None, :]) & valid
    tot = valid.sum(axis=1)
    with np.errstate(invalid="ignore"):
        out = np.where(tot >= min_labels, hit.sum(axis=1) / np.maximum(tot, 1), np.nan)
    return out


def probe(vid, media, mdir, bank, clf, dev, exclude_self):
    npz = load_npz(vid)
    if npz is None:
        return {"vid": vid, "verdict": "no_npz"}
    _, mt = npz
    labels = [(m["speaker"], float(m["start_s"])) for m in mt
              if m["attr"] in ENROL_ATTR and m["has_fk"]
              and m["end_s"] - m["start_s"] >= 5.0]
    if len(labels) < MIN_LABELS:
        return {"vid": vid, "verdict": "too_few_labels", "n_labels": len(labels)}

    names, C = bank.matrix(exclude_vid=vid if exclude_self else None)
    if C.shape[0] == 0:
        return {"vid": vid, "verdict": "no_bank"}
    name_idx = {n: i for i, n in enumerate(names)}

    opus = os.path.join(mdir, "audio16k.opus")
    if not os.path.exists(opus):
        return {"vid": vid, "verdict": "no_audio"}
    dur = float(media.get("duration") or 0.0)
    cap_max = max(float(m["end_s"]) for m in mt)

    # Feasible offsets: caption span and audio must overlap by MIN_OVERLAP.
    lo = -(cap_max - MIN_OVERLAP)
    hi = dur - MIN_OVERLAP
    if hi <= lo:
        return {"vid": vid, "verdict": "no_overlap", "duration": dur,
                "caption_span": cap_max}

    audio = decode(opus)
    dur_actual = len(audio) / SR

    # --- coarse pass over the whole feasible range ---
    starts = np.arange(0, dur_actual - WIN, COARSE_HOP)
    st_c, E_c = embed_at(audio, clf, dev, starts)
    if len(st_c) == 0:
        return {"vid": vid, "verdict": "no_windows"}
    best_c = np.argmax(E_c @ C.T, axis=1)
    grid_c = np.arange(lo, hi + 1, COARSE_HOP)
    sc = sweep(st_c, best_c, labels, name_idx, grid_c, COARSE_HOP)
    if np.all(np.isnan(sc)):
        return {"vid": vid, "verdict": "unscorable"}
    coarse_best = float(grid_c[int(np.nanargmax(sc))])
    baseline = float(np.nanmedian(sc))

    # --- fine pass around the winner ---
    f_lo, f_hi = coarse_best - FINE_SPAN, coarse_best + FINE_SPAN
    w_lo = max(0.0, min(l[1] for l in labels) + f_lo - WIN)
    w_hi = min(dur_actual - WIN, max(l[1] for l in labels) + f_hi + WIN)
    st_f, E_f = embed_at(audio, clf, dev, np.arange(w_lo, w_hi, FINE_HOP))
    if len(st_f) == 0:
        return {"vid": vid, "verdict": "no_fine_windows"}
    best_f = np.argmax(E_f @ C.T, axis=1)
    grid_f = np.arange(f_lo, f_hi + 0.5, 1.0)
    sf_ = sweep(st_f, best_f, labels, name_idx, grid_f, FINE_HOP)
    if np.all(np.isnan(sf_)):
        return {"vid": vid, "verdict": "unscorable_fine"}
    best = float(grid_f[int(np.nanargmax(sf_))])
    peak = float(np.nanmax(sf_))

    # --- drift / consistency: independent halves must agree ---
    mid = float(np.median([l[1] for l in labels]))
    h1 = sweep(st_f, best_f, [l for l in labels if l[1] <= mid],
               name_idx, grid_f, FINE_HOP, min_labels=HALF_MIN_LABELS)
    h2 = sweep(st_f, best_f, [l for l in labels if l[1] > mid],
               name_idx, grid_f, FINE_HOP, min_labels=HALF_MIN_LABELS)
    o1 = float(grid_f[int(np.nanargmax(h1))]) if not np.all(np.isnan(h1)) else None
    o2 = float(grid_f[int(np.nanargmax(h2))]) if not np.all(np.isnan(h2)) else None
    drift = (o2 - o1) if (o1 is not None and o2 is not None) else None

    stored = media.get("caption_offset_s")
    ratio = peak / baseline if baseline > 1e-6 else float("inf")
    # A meeting with too few labels to split cannot be drift-checked. That
    # is a reason to demand a stronger peak, not to reject outright —
    # rejecting on an unevaluable check threw away good alignments in the
    # first calibration pass.
    if drift is None:
        decisive = peak >= max(ACCEPT_PEAK, 0.6) and ratio >= ACCEPT_RATIO
    else:
        decisive = (peak >= ACCEPT_PEAK and ratio >= ACCEPT_RATIO
                    and abs(drift) <= ACCEPT_DRIFT)
    if not decisive:
        verdict = "unconfirmed"
    elif stored is not None and abs(best - float(stored)) <= CONFIRM_TOL:
        verdict = "confirmed"
    else:
        verdict = "corrected"

    return {"vid": vid, "verdict": verdict, "stored": stored,
            "recovered": round(best, 2),
            "peak": round(peak, 3), "baseline": round(baseline, 3),
            "ratio": round(ratio, 2), "half1": o1, "half2": o2,
            "drift": drift, "n_labels": len(labels),
            "duration": round(dur_actual, 1), "caption_span": round(cap_max, 1),
            "search_lo": round(lo, 1), "search_hi": round(hi, 1),
            "align_score": media.get("align_score"),
            "outside_600": bool(abs(best) > 600)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", default="realign_report.json")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--calibrate", action="store_true",
                    help="probe only meetings believed already-good "
                         "(youtube source or align_score>=10) to validate the "
                         "accept rule before trusting it on suspects")
    ap.add_argument("--bank-from", default=None,
                    help="JSON report from a previous pass; rebuild the "
                         "centroid bank from its confirmed/corrected meetings")
    ap.add_argument("--device", default="auto", choices=("auto", "cuda", "cpu"))
    args = ap.parse_args()

    media, dirs = load_media_meta()
    print(f"{len(media)} cached meetings on disk", flush=True)

    def believed_good(vid):
        j = media.get(vid, {})
        return j.get("source") != "isi" or (j.get("align_score") or 0) >= 10

    # ---- centroid bank ----
    bank_ok = None
    if args.bank_from:
        prev = {r["vid"]: r for r in json.load(open(args.bank_from))}
        bank_ok = {v for v, r in prev.items()
                   if r.get("verdict") in ("confirmed", "corrected")}
        print(f"bank seeded from {len(bank_ok)} verified meetings", flush=True)

    bank = Bank()
    for fn in sorted(f for f in os.listdir(CACHE) if f.endswith(".npz")):
        vid = fn[:-4]
        use = (vid in bank_ok) if bank_ok is not None else believed_good(vid)
        if not use:
            continue
        got = load_npz(vid)
        if not got:
            continue
        E, mt = got
        for i, m in enumerate(mt):
            if m["attr"] in ENROL_ATTR and m["has_fk"]:
                bank.add(vid, m["speaker"], E[i])
    names, C = bank.matrix()
    print(f"centroid bank: {len(names)} councillors", flush=True)

    targets = [v for v in media if media[v].get("source") == "isi"]
    if args.calibrate:
        targets = [v for v in targets if believed_good(v)]
    targets.sort()
    if args.limit:
        targets = targets[:args.limit]
    print(f"probing {len(targets)} meetings", flush=True)

    import torch
    from speechbrain.inference import EncoderClassifier
    dev = args.device
    if dev == "auto":
        dev = "cuda" if torch.cuda.is_available() else "cpu"
    clf = EncoderClassifier.from_hparams(
        source="speechbrain/spkrec-ecapa-voxceleb",
        savedir=os.path.expanduser("~/.cache/voice-audit-ecapa"),
        run_opts={"device": dev})
    print(f"device: {dev}", flush=True)

    out, t0 = [], time.time()
    for i, vid in enumerate(targets, 1):
        try:
            r = probe(vid, media[vid], dirs[vid], bank, clf, dev,
                      exclude_self=True)
        except Exception as exc:
            r = {"vid": vid, "verdict": "error", "error": str(exc)[:200]}
        out.append(r)
        el = time.time() - t0
        print(f"[{i}/{len(targets)}] {vid} {r['verdict']:>14} "
              f"stored={r.get('stored')} rec={r.get('recovered')} "
              f"peak={r.get('peak')} ratio={r.get('ratio')} "
              f"({el/i:.0f}s/mtg)", flush=True)
        json.dump(out, open(args.report, "w"), indent=1)

    from collections import Counter
    print("\n" + "=" * 60)
    for k, n in Counter(r["verdict"] for r in out).most_common():
        print(f"  {k:>16}: {n}")
    print(f"report -> {args.report}")


if __name__ == "__main__":
    main()
