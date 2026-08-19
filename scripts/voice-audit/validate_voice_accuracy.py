#!/usr/bin/env python3
"""Leave-one-out validation of voice attribution. Read-only, no GPU.

This is the harness that found the 2026-08-19 alignment bug, kept as a
standing regression check rather than a throwaway.

It scores every meeting's macro/recognition-labelled turns — whose
speaker is known from the text tiers — against centroids pooled from the
whole corpus. Where alignment holds, the embedding for a labelled turn
really is that councillor and top-1 identification lands ~92%. Where the
caption offset is wrong, the window is cut from the wrong moment and
accuracy collapses to near chance.

Read the DISTRIBUTION, not the mean. A unimodal ~90% corpus is healthy; a
bimodal one (a good cluster plus a cluster near zero) means a subset is
misaligned, and the mean will hide it — the corpus averaged 54% while
half of it was broken.

Usage:
  ./.venv/bin/python validate_voice_accuracy.py
  ./.venv/bin/python validate_voice_accuracy.py --min-dur 5
"""
from __future__ import annotations

import argparse
import json
import os
import re
from collections import defaultdict

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
MEDIA = os.environ.get(
    "MEDIA_CACHE_DIR", os.path.abspath(os.path.join(HERE, "..", "..", "media-cache")))
ENROL_ATTR = ("macro", "recognition")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-dur", type=float, default=8.0,
                    help="score only turns at least this long (embedding "
                         "quality is strongly duration-dependent)")
    ap.add_argument("--min-test", type=int, default=8,
                    help="meetings need this many scorable turns")
    ap.add_argument("--json", default=None, help="write per-meeting rows here")
    args = ap.parse_args()

    meta = {}
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

    per_meeting, pool = {}, defaultdict(list)
    for fn in sorted(f for f in os.listdir(CACHE) if f.endswith(".npz")):
        try:
            z = np.load(os.path.join(CACHE, fn), allow_pickle=True)
            E, mt = z["embeddings"], json.loads(str(z["meta"]))
        except Exception:
            continue
        En = E / (np.linalg.norm(E, axis=1, keepdims=True) + 1e-9)
        per_meeting[fn[:-4]] = (En, mt)
        for i, m in enumerate(mt):
            if m["attr"] in ENROL_ATTR and m["has_fk"]:
                pool[m["speaker"]].append(En[i])

    names = sorted(n for n, v in pool.items() if len(v) >= 3)
    C = np.vstack([(lambda v: v / (np.linalg.norm(v) + 1e-9))(
        np.vstack(pool[n]).mean(axis=0)) for n in names])
    print(f"{len(per_meeting)} meetings, {len(names)} councillors enrolled")

    rows = []
    for vid, (En, mt) in per_meeting.items():
        idx = [i for i, m in enumerate(mt)
               if m["attr"] in ENROL_ATTR and m["has_fk"]
               and m["speaker"] in names
               and (m["end_s"] - m["start_s"]) >= args.min_dur]
        if len(idx) < args.min_test:
            continue
        pred = np.argmax(En[idx] @ C.T, axis=1)
        truth = np.array([names.index(mt[i]["speaker"]) for i in idx])
        j = meta.get(vid, {})
        rows.append({"vid": vid, "acc": float((pred == truth).mean()),
                     "n": len(idx), "source": j.get("source", "?"),
                     "align_method": j.get("align_method", "vad"),
                     "offset": j.get("caption_offset_s")})

    acc = np.array([r["acc"] for r in rows])
    print(f"\nscored {len(rows)} meetings (turns >= {args.min_dur:.0f}s)")
    print(f"mean {acc.mean():.1%}  median {np.median(acc):.1%}")

    print("\ndistribution (bimodality is the tell):")
    for lo, hi in ((0, .2), (.2, .4), (.4, .6), (.6, .8), (.8, .95), (.95, 1.01)):
        n = int(((acc >= lo) & (acc < hi)).sum())
        print(f"  {lo:>4.0%}-{hi:<4.0%} {n:>4}  {'#' * int(60 * n / max(1, len(acc)))}")

    print("\nby media source:")
    by = defaultdict(list)
    for r in rows:
        by[r["source"]].append(r["acc"])
    for k, v in sorted(by.items()):
        a = np.array(v)
        print(f"  {k:>8}: {len(a):>4} meetings  mean {a.mean():.1%}  "
              f"broken(<50%) {(a < 0.5).mean():.1%}")

    print("\nby alignment method:")
    by = defaultdict(list)
    for r in rows:
        by[r["align_method"]].append(r["acc"])
    for k, v in sorted(by.items()):
        a = np.array(v)
        print(f"  {k:>8}: {len(a):>4} meetings  mean {a.mean():.1%}  "
              f"broken(<50%) {(a < 0.5).mean():.1%}")

    broken = (acc < 0.5).mean()
    print(f"\nHEALTH: mean {acc.mean():.1%}, broken {broken:.1%} "
          f"— target >=85% mean and <10% broken")
    if args.json:
        json.dump(rows, open(args.json, "w"), indent=1)
        print(f"per-meeting rows -> {args.json}")


if __name__ == "__main__":
    main()
