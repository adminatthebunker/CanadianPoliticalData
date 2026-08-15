#!/usr/bin/env python3
"""Voice attribution batch — classify bare Edmonton caption turns by voice.

Production counterpart to voice_audit.py (same venv, see bootstrap.sh).
Numbers behind the gates: 2026-08-14 PoC — 97.1% accuracy on ≥5 s turns,
98.3% ≥8 s, unknown-voice rejection sound at cosine 0.60
(docs/runbooks/edmonton-diarization-poc-2026-08-14.md).

Per meeting: download audio, measure the CART caption lag, embed every
turn ≥3 s with ECAPA (CPU), cache embeddings under cache/. Then globally:
pool per-councillor voiceprints from the HIGH-confidence text tiers
(macro + recognition) across ALL meetings, and classify the bare ≥5 s
turns — accept only when top cosine ≥ COS_MIN and the margin over the
runner-up councillor ≥ MARGIN_MIN.

Results are written to ``meetings.raw->'voice_map'`` as
``[{start_s, name, cos}]`` — NOT to speeches directly. The scanner's
``resolve-meeting-caption-speakers`` stage applies the map (attribution=
'voice', confidence 0.7), which makes voice attribution reparse-safe:
reparse wipes speeches, resolve re-applies.

Usage: python voice_attribute.py [--meetings N] [--cos 0.65] [--margin 0.06]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
SR = 16000
WIN, HOP, MAX_WINDOWS, MIN_WIN_S = 4.0, 2.0, 14, 1.5
EMBED_MIN_DUR = 3.0
CLASSIFY_MIN_DUR = 5.0
ENROL_ATTR = ("macro", "recognition")

PSQL = ["docker", "exec", "sw-db", "psql", "-U", "sw", "-d", "sovereignwatch",
        "-t", "-A", "-F", "\t", "-c"]


def psql(sql: str) -> str:
    return subprocess.run(PSQL + [sql], capture_output=True, text=True, check=True).stdout


def meetings_with_speeches() -> list[tuple[str, str]]:
    """→ [(video_id, video_url)] for meetings with caption speeches."""
    out = psql("""
        SELECT DISTINCT m.video_url
        FROM meetings m
        WHERE m.source_system='edmonton-escribemeetings' AND m.video_url IS NOT NULL
          AND EXISTS (SELECT 1 FROM speeches s
                      WHERE s.source_system='edmonton-youtube-captions'
                        AND s.meeting_id = m.id)
    """)
    rows = []
    for line in out.splitlines():
        url = line.strip()
        if url:
            rows.append((url.split("v=")[-1], url))
    return rows


def fetch_turns(video_id: str) -> list[dict]:
    out = psql(f"""
        SELECT s.sequence, coalesce(p.name, s.speaker_name_raw),
               coalesce(s.raw->>'attribution',''),
               (s.raw->>'start_seconds')::float, (s.raw->>'end_seconds')::float,
               (s.politician_id IS NOT NULL)::int
        FROM speeches s
        LEFT JOIN politicians p ON p.id = s.politician_id
        JOIN meetings m ON m.id = s.meeting_id
        WHERE s.source_system='edmonton-youtube-captions'
          AND m.video_url = 'https://www.youtube.com/watch?v={video_id}'
        ORDER BY s.sequence
    """)
    turns = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) != 6 or not parts[3]:
            continue
        turns.append({
            "seq": int(parts[0]), "speaker": parts[1], "attr": parts[2],
            "start_s": float(parts[3]), "end_s": float(parts[4]),
            "has_fk": parts[5] == "1",
        })
    return turns


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
    import numpy as np
    # 12 turns x 3 candidates: the PoC showed a broad accuracy plateau
    # (4.75-7.25s), so a coarse probe around it is enough.
    sample = [t for t in turns if t["end_s"] - t["start_s"] >= 8][:12]
    best_lag, best_sep = 5.0, -2.0
    for lag in (3.5, 5.0, 6.5):
        embs = embed_turns(audio, sample, lag, clf)
        pairs = [(a, b) for a, b in zip(embs, embs[1:]) if a is not None and b is not None]
        if len(pairs) < 5:
            continue
        sep = -float(np.mean([a @ b for a, b in pairs]))
        if sep > best_sep:
            best_sep, best_lag = sep, lag
    return best_lag


def process_meeting(video_id: str, clf) -> str | None:
    """Embed all turns; cache npz. Returns cache path or None."""
    import numpy as np
    import soundfile as sf
    cache_path = os.path.join(CACHE, f"{video_id}.npz")
    if os.path.exists(cache_path):
        return cache_path
    turns = fetch_turns(video_id)
    if not turns:
        return None
    with tempfile.TemporaryDirectory(prefix="voiceattr-") as workdir:
        # Audio comes from the derivative media cache when present (one
        # YouTube fetch per meeting, ever — see services/scanner/src/
        # legislative/media_cache.py; the compose bind mounts it at
        # ./media-cache so host tooling reads it directly). Fallback:
        # direct audio download for meetings not yet cached.
        cache_opus = os.path.join(
            os.environ.get("MEDIA_CACHE_DIR",
                           os.path.join(HERE, "..", "..", "media-cache")),
            "youtube", video_id, "audio16k.opus")
        wav_path = os.path.join(workdir, "a.wav")
        if os.path.exists(cache_opus):
            subprocess.run(
                ["ffmpeg", "-v", "error", "-i", cache_opus,
                 "-ar", "16000", "-ac", "1", wav_path],
                check=True, capture_output=True, text=True,
            )
        else:
            try:
                subprocess.run(
                    ["yt-dlp", "-f", "bestaudio", "-x", "--audio-format", "wav",
                     "--postprocessor-args", "-ar 16000 -ac 1", "--no-warnings",
                     "--sleep-requests", "2", "--limit-rate", "3M",
                     "--concurrent-fragments", "1",
                     "--retry-sleep", "http:exp=10:600", "--retries", "4",
                     "-o", os.path.join(workdir, "a.%(ext)s"),
                     f"https://www.youtube.com/watch?v={video_id}"],
                    check=True, capture_output=True, text=True,
                )
            except subprocess.CalledProcessError as exc:
                print(f"  {video_id}: audio download failed ({exc.stderr.strip()[-120:]})")
                return None
        audio, sr = sf.read(wav_path, dtype="float32")
        assert sr == SR
        lag = measure_lag(audio, turns, clf)
        # Enrollment: the 8 longest macro/recognition turns per speaker
        # per meeting (a sample is as good as all 1,700 of the mayor's
        # turns for a pooled centroid). Classification targets: bare
        # turns >= CLASSIFY_MIN_DUR. Nothing else needs embedding.
        from collections import defaultdict as _dd
        by_spk = _dd(list)
        for t in turns:
            if t["attr"] in ENROL_ATTR and t["has_fk"] \
                    and t["end_s"] - t["start_s"] >= EMBED_MIN_DUR:
                by_spk[t["speaker"]].append(t)
        enrol_sample = []
        for vs in by_spk.values():
            vs.sort(key=lambda t: t["start_s"] - t["end_s"])  # longest first
            enrol_sample.extend(vs[:8])
        bare = [t for t in turns
                if not t["attr"] and not t["has_fk"]
                and t["speaker"] == "UNATTRIBUTED"
                and t["end_s"] - t["start_s"] >= CLASSIFY_MIN_DUR]
        embeddable = sorted(enrol_sample + bare, key=lambda t: t["seq"])
        print(f"  {video_id}: lag={lag:.1f}s, embedding {len(embeddable)} turns "
              f"({len(enrol_sample)} enrolment + {len(bare)} bare)…", flush=True)
        embs = embed_turns(audio, embeddable, lag, clf)
    keep = [(t, e) for t, e in zip(embeddable, embs) if e is not None]
    np.savez_compressed(
        cache_path,
        embeddings=np.vstack([e for _, e in keep]),
        meta=json.dumps([{k: t[k] for k in ("seq", "speaker", "attr", "start_s", "end_s", "has_fk")}
                         for t, _ in keep]),
        lag=lag,
    )
    return cache_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--meetings", type=int, default=None)
    ap.add_argument("--cos", type=float, default=0.65)
    ap.add_argument("--margin", type=float, default=0.06)
    ap.add_argument("--device", default="auto", choices=("auto", "cuda", "cpu"))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    import numpy as np
    import torch
    from speechbrain.inference.speaker import EncoderClassifier

    os.makedirs(CACHE, exist_ok=True)
    torch.set_num_threads(min(8, os.cpu_count() or 8))
    device = args.device
    if device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"device: {device}")
    clf = EncoderClassifier.from_hparams(
        source="speechbrain/spkrec-ecapa-voxceleb",
        savedir=os.path.expanduser("~/.cache/voice-audit-ecapa"),
        run_opts={"device": device},
    )

    vids = meetings_with_speeches()
    if args.meetings:
        vids = vids[:args.meetings]
    print(f"{len(vids)} meetings")
    caches = {}
    for vid, url in vids:
        p = process_meeting(vid, clf)
        if p:
            caches[vid] = (p, url)

    # Pooled enrollment across all meetings.
    from collections import defaultdict
    pool = defaultdict(list)
    per_meeting = {}
    for vid, (p, url) in caches.items():
        z = np.load(p, allow_pickle=True)
        E, meta = z["embeddings"], json.loads(str(z["meta"]))
        per_meeting[vid] = (E, meta, url)
        for i, m in enumerate(meta):
            if m["attr"] in ENROL_ATTR and m["has_fk"]:
                pool[m["speaker"]].append(E[i])
    cents = {}
    for name, vs in pool.items():
        if len(vs) < 3:
            continue  # too little enrollment to trust
        v = np.mean(vs, axis=0)
        cents[name] = v / (np.linalg.norm(v) + 1e-9)
    names = sorted(cents)
    C = np.vstack([cents[n] for n in names])
    print(f"enrolled {len(names)} councillors: "
          + ", ".join(f"{n}({len(pool[n])})" for n in names))

    total_assigned = 0
    for vid, (E, meta, url) in per_meeting.items():
        entries = []
        for i, m in enumerate(meta):
            if m["attr"] or m["has_fk"] or m["speaker"] != "UNATTRIBUTED":
                continue
            if m["end_s"] - m["start_s"] < CLASSIFY_MIN_DUR:
                continue
            sims = E[i] @ C.T
            order = np.argsort(sims)[::-1]
            top, second = float(sims[order[0]]), float(sims[order[1]]) if len(order) > 1 else 0.0
            if top >= args.cos and (top - second) >= args.margin:
                entries.append({
                    "start_s": round(m["start_s"], 1),
                    "name": names[int(order[0])],
                    "cos": round(top, 3),
                })
        total_assigned += len(entries)
        print(f"  {vid}: {len(entries)} voice assignments")
        if entries and not args.dry_run:
            import datetime as _dt
            envelope = {
                "version": 2,
                "generated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
                "params": {
                    "model": "speechbrain/spkrec-ecapa-voxceleb",
                    "cos_min": args.cos, "margin_min": args.margin,
                    "classify_min_dur": CLASSIFY_MIN_DUR,
                    "lag_s": float(np.load(caches[vid][0], allow_pickle=True)["lag"]),
                },
                "entries": entries,
            }
            payload = json.dumps(envelope).replace("'", "''")
            psql(f"""
                UPDATE meetings
                SET raw = raw || jsonb_build_object('voice_map', '{payload}'::jsonb),
                    updated_at = now()
                WHERE source_system='edmonton-escribemeetings'
                  AND video_url = '{url}'
            """)
    print(f"\ntotal voice assignments: {total_assigned}"
          + (" (dry run — nothing written)" if args.dry_run else
             "\nnow run: docker compose run --rm scanner resolve-meeting-caption-speakers --city edmonton"
             "\nthen:    docker compose run --rm scanner enrich-edmonton-minutes --limit 30  (denorm sync)"))


if __name__ == "__main__":
    main()
