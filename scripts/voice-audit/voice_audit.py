#!/usr/bin/env python3
"""Voice-fingerprint audit of Edmonton caption-speech attributions.

Offline batch auditor (NOT part of the scanner image — torch/speechbrain
live in a local venv, see bootstrap.sh). Ported from the 2026-08-14
diarization PoC; numbers and method in
docs/runbooks/edmonton-diarization-poc-2026-08-14.md.

For one meeting video:
  1. pull the meeting's caption turns + attributions from the DB
     (via `docker exec sw-db psql` — no python DB deps),
  2. download audio (yt-dlp, 16 kHz mono wav),
  3. measure the CART caption lag (coarse separation sweep) unless --lag
     is given — captions lag audio ~5 s but MEASURE PER VIDEO,
  4. embed every turn ≥3 s with ECAPA-TDNN (CPU),
  5. enroll per-speaker centroids from macro+recognition turns,
  6. audit alternation/panel/chair attributions: voice agreement,
     confident disagreements, unknown-voice rejections,
  7. write a TSV report + console summary.

Disagreements are review input, not auto-applied: the PoC showed voice at
90.4% LOO on ≥3 s turns (98.3% ≥8 s) — great auditor, not an oracle.

Usage (inside the bootstrap venv):
  python voice_audit.py VIDEO_ID [--lag SECS] [--min-dur 3.0] [--out report.tsv]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile

SR = 16000
WIN, HOP, MAX_WINDOWS, MIN_WIN_S = 4.0, 2.0, 14, 1.5
ENROL_ATTR = ("macro", "recognition")
AUDIT_ATTR = ("alternation", "panel", "chair")
REJECT_THRESHOLD = 0.60

PSQL = ["docker", "exec", "sw-db", "psql", "-U", "sw", "-d", "sovereignwatch",
        "-t", "-A", "-F", "\t", "-c"]


def fetch_turns(video_id: str) -> list[dict]:
    sql = f"""
    SELECT s.sequence,
           coalesce(p.name, s.speaker_name_raw),
           coalesce(s.raw->>'attribution', ''),
           (s.raw->>'start_seconds')::float,
           (s.raw->>'end_seconds')::float
    FROM speeches s
    LEFT JOIN politicians p ON p.id = s.politician_id
    JOIN meetings m ON m.id = s.meeting_id
    WHERE s.source_system = 'edmonton-youtube-captions'
      AND m.video_url = 'https://www.youtube.com/watch?v={video_id}'
    ORDER BY s.sequence
    """
    out = subprocess.run(PSQL + [sql], capture_output=True, text=True, check=True).stdout
    turns = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) != 5 or not parts[3]:
            continue
        turns.append({
            "seq": int(parts[0]), "speaker": parts[1], "attr": parts[2],
            "start_s": float(parts[3]), "end_s": float(parts[4]),
        })
    return turns


def download_audio(video_id: str, workdir: str) -> str:
    wav = os.path.join(workdir, "meeting.wav")
    subprocess.run(
        ["yt-dlp", "-f", "bestaudio", "-x", "--audio-format", "wav",
         "--postprocessor-args", "-ar 16000 -ac 1",
         "-o", os.path.join(workdir, "meeting.%(ext)s"),
         f"https://www.youtube.com/watch?v={video_id}"],
        check=True,
    )
    return wav


def windows_for(start_s, end_s, n_samples):
    import numpy as np
    a, b = max(0, int(start_s * SR)), min(n_samples, int(end_s * SR))
    if (b - a) / SR < MIN_WIN_S:
        return []
    wl, hop = int(WIN * SR), int(HOP * SR)
    if b - a < wl:
        return [(a, b)]
    wins = [(s, s + wl) for s in range(a, b - wl + 1, hop)]
    if len(wins) > MAX_WINDOWS:
        idx = np.linspace(0, len(wins) - 1, MAX_WINDOWS).astype(int)
        wins = [wins[i] for i in idx]
    return wins


def embed_turns(audio, turns, lag, clf):
    """Turn embedding = L2-normalised mean of energy-gated window embeddings."""
    import numpy as np
    import torch
    embs = []
    for t in turns:
        wins = windows_for(t["start_s"] - lag, t["end_s"] - lag, len(audio))
        if not wins:
            embs.append(None)
            continue
        chunks = [audio[a:b] for a, b in wins]
        rms = np.array([float(np.sqrt(np.mean(c ** 2)) + 1e-9) for c in chunks])
        keep = rms >= max(rms.max() * 0.15, float(np.median(rms)) * 0.4)
        if not keep.any():
            keep[:] = True
        chunks = [c for c, k in zip(chunks, keep) if k]
        vecs = []
        for j in range(0, len(chunks), 16):
            batch = chunks[j:j + 16]
            L = max(len(c) for c in batch)
            arr = np.zeros((len(batch), L), dtype=np.float32)
            lens = np.zeros(len(batch), dtype=np.float32)
            for k, c in enumerate(batch):
                arr[k, :len(c)] = c
                lens[k] = len(c) / L
            with torch.no_grad():
                e = clf.encode_batch(torch.from_numpy(arr), torch.from_numpy(lens))
            vecs.append(e.squeeze(1).cpu().numpy())
        V = np.vstack(vecs)
        V = V / (np.linalg.norm(V, axis=1, keepdims=True) + 1e-9)
        m = V.mean(axis=0)
        embs.append((m / (np.linalg.norm(m) + 1e-9)).astype(np.float32))
    return embs


def measure_lag(audio, turns, clf) -> float:
    """Coarse lag sweep: pick the shift maximising within-turn coherence
    minus adjacent-turn similarity over a sample of turn pairs."""
    import numpy as np
    sample = [t for t in turns if t["end_s"] - t["start_s"] >= 8][:40]
    best_lag, best_sep = 5.0, -1.0
    for lag in (0.0, 2.0, 3.5, 5.0, 6.5, 8.0):
        embs = embed_turns(audio, sample, lag, clf)
        pairs = [(a, b) for a, b in zip(embs, embs[1:]) if a is not None and b is not None]
        if len(pairs) < 5:
            continue
        across = float(np.mean([a @ b for a, b in pairs]))
        sep = -across  # lower adjacent-turn similarity = cleaner slicing
        if sep > best_sep:
            best_sep, best_lag = sep, lag
    print(f"measured caption lag ≈ {best_lag:.1f}s")
    return best_lag


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video_id")
    ap.add_argument("--lag", type=float, default=None,
                    help="Caption lag in seconds (default: measure)")
    ap.add_argument("--min-dur", type=float, default=3.0)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    import numpy as np
    import soundfile as sf
    import torch
    from speechbrain.inference.speaker import EncoderClassifier

    torch.set_num_threads(min(8, os.cpu_count() or 8))
    turns = fetch_turns(args.video_id)
    if not turns:
        sys.exit(f"no caption turns in DB for video {args.video_id}")
    print(f"{len(turns)} turns loaded from DB")

    with tempfile.TemporaryDirectory(prefix="voiceaudit-") as workdir:
        wav = download_audio(args.video_id, workdir)
        audio, sr = sf.read(wav, dtype="float32")
        assert sr == SR, sr
        clf = EncoderClassifier.from_hparams(
            source="speechbrain/spkrec-ecapa-voxceleb",
            savedir=os.path.expanduser("~/.cache/voice-audit-ecapa"),
            run_opts={"device": "cpu"},
        )
        lag = args.lag if args.lag is not None else measure_lag(audio, turns, clf)
        embs = embed_turns(audio, turns, lag, clf)

    usable = [(t, e) for t, e in zip(turns, embs)
              if e is not None and t["end_s"] - t["start_s"] >= args.min_dur]
    enrol: dict[str, list] = {}
    for t, e in usable:
        if t["attr"] in ENROL_ATTR:
            enrol.setdefault(t["speaker"], []).append(e)
    cents = {s: (lambda v: v / (np.linalg.norm(v) + 1e-9))(np.mean(vs, axis=0))
             for s, vs in enrol.items() if vs}
    if not cents:
        sys.exit("no enrolment turns (macro/recognition) — cannot audit")
    names = sorted(cents)
    C = np.vstack([cents[n] for n in names])

    rows, agree, disagree, unknown = [], 0, 0, 0
    for t, e in usable:
        if t["attr"] not in AUDIT_ATTR:
            continue
        sims = e @ C.T
        k = int(np.argmax(sims))
        pred, cos = names[k], float(sims[k])
        if cos < REJECT_THRESHOLD:
            verdict = "unknown-voice"
            unknown += 1
        elif pred == t["speaker"]:
            verdict = "agree"
            agree += 1
        else:
            verdict = "DISAGREE"
            disagree += 1
        rows.append((t["seq"], t["attr"], t["speaker"], pred, f"{cos:.3f}", verdict))

    total = agree + disagree + unknown
    print(f"\naudited {total} attributed turns (attr in {AUDIT_ATTR}, ≥{args.min_dur}s):")
    print(f"  agree        {agree}")
    print(f"  DISAGREE     {disagree}   <- review these")
    print(f"  unknown-voice {unknown}   (below {REJECT_THRESHOLD} to every centroid)")
    out = args.out or f"voice-audit-{args.video_id}.tsv"
    with open(out, "w") as fh:
        fh.write("seq\tattr\tdb_speaker\tvoice_pred\tcos\tverdict\n")
        for r in rows:
            fh.write("\t".join(str(x) for x in r) + "\n")
    print(f"report: {out}")


if __name__ == "__main__":
    main()
