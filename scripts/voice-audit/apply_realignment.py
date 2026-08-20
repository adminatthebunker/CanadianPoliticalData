#!/usr/bin/env python3
"""Apply a realign_offsets.py report: patch offsets, invalidate, flag.

Dry-run by default — pass --apply to write.

For each meeting the report calls `corrected`:
  * patch caption_offset_s in the on-disk meta.json (audio/frames/times
    are untouched siblings, so nothing is re-derived or re-downloaded)
  * patch meetings.raw->'speaker_timeline'->'caption_offset_s', which the
    panel tier reads (youtube_captions.make_panel_owner_lookup and
    edmonton_panel_ocr both use `offset + 13.0` as the probe lead), so a
    bad offset degraded panel attribution too
  * delete the meeting's npz so voice_attribute re-embeds it
    (process_meeting early-returns on file existence; there is no --force)
  * drop raw->'voice_map' — the writer SKIPS its UPDATE when a re-run
    yields zero entries, so a stale map would otherwise silently survive
  * reset that meeting's voice speeches to bare. resolve_meeting_caption_
    speakers is additive-only and never retracts, and reparse explicitly
    preserves 'voice' when caption text is unchanged, so nothing else
    will ever clear them

For `unconfirmed` meetings (operator decision 2026-08-19: flag, don't
delete) the attributions stay but are marked: confidence 0.3 and
raw->'voice_unverified' = true, so consumers can filter them out.

Every row touched is recoverable from public.voice_realign_backup_20260819.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
MEDIA = os.environ.get(
    "MEDIA_CACHE_DIR", os.path.abspath(os.path.join(HERE, "..", "..", "media-cache")))
PSQL = ["docker", "exec", "sw-db", "psql", "-U", "sw", "-d", "sovereignwatch",
        "-v", "ON_ERROR_STOP=1"]


def psql(sql, quiet=False):
    r = subprocess.run(PSQL + ["-tAc", sql], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"psql failed: {r.stderr.strip()[:300]}")
    if not quiet and r.stdout.strip():
        return r.stdout.strip()
    return r.stdout.strip()


def media_index():
    idx = {}
    for root, _, files in os.walk(MEDIA):
        if "meta.json" not in files:
            continue
        p = os.path.join(root, "meta.json")
        try:
            j = json.load(open(p))
        except Exception:
            continue
        m = re.search(r"v=([A-Za-z0-9_-]{11})", j.get("video_url", ""))
        if m:
            idx[m.group(1)] = (p, j)
    return idx


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("report")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    rows = json.load(open(args.report))
    corrected = [r for r in rows if r["verdict"] == "corrected"]
    confirmed = [r for r in rows if r["verdict"] == "confirmed"]
    # Anything we could not decide gets flagged, not just the meetings that
    # scored too weakly: "too_few_labels" / "no_npz" / "no_overlap" are
    # equally unverified, and leaving them silently trusted is the exact
    # failure mode this whole exercise exists to fix.
    unverified = [r for r in rows
                  if r["verdict"] not in ("confirmed", "corrected")]
    print(f"report: {len(rows)} meetings — {len(confirmed)} confirmed, "
          f"{len(corrected)} corrected, {len(unverified)} unverified "
          f"({Counter(r['verdict'] for r in unverified).most_common()})")
    if not args.apply:
        print("\n*** DRY RUN — nothing written (pass --apply) ***")

    idx = media_index()

    # ---- guard: the backup must exist before anything is mutated -------
    n_backup = psql("select count(*) from public.voice_realign_backup_20260819")
    print(f"rollback table holds {n_backup} rows")
    if int(n_backup) == 0:
        sys.exit("refusing to proceed: rollback table is empty")

    # ---- 1. patch meta.json --------------------------------------------
    # `corrected` gets a new offset. `confirmed` keeps its offset but is
    # still stamped identity-verified: without that stamp a later
    # `realign-media-offsets` run would recompute these with VAD and could
    # overwrite a value identity already validated. The stamp is what
    # makes that CLI's skip-guard work.
    patched = stamped = 0
    payload = {}
    for r in corrected + confirmed:
        got = idx.get(r["vid"])
        if not got:
            print(f"  ! {r['vid']}: no meta.json on disk")
            continue
        path, j = got
        patch = {"align_method": "identity", "identity_peak": r["peak"],
                 "identity_verified_at": "2026-08-19"}
        if r["verdict"] == "corrected":
            # Only record the prior value the FIRST time, or a re-run would
            # overwrite the original with our own correction and lose it.
            if j.get("align_method") != "identity":
                patch["align_offset_previous"] = j.get("caption_offset_s")
            patch["caption_offset_s"] = r["recovered"]
            patched += 1
        else:
            stamped += 1
        # The cache tree is owned by the container's uid (1001); the host
        # user cannot write it. Patch through the container that owns it
        # rather than loosening permissions on the whole cache.
        payload[os.path.join("/media-cache",
                             os.path.relpath(path, MEDIA))] = patch
    print(f"meta.json — offsets rewritten: {patched}, "
          f"verified-in-place: {stamped}")

    if args.apply and payload:
        script = (
            "import json,os,sys\n"
            "p=json.load(sys.stdin)\n"
            "n=0\n"
            "for path,patch in p.items():\n"
            "    with open(path) as fh: j=json.load(fh)\n"
            "    j.update(patch)\n"
            "    t=path+'.tmp'\n"
            "    with open(t,'w') as fh: json.dump(j,fh)\n"
            "    os.replace(t,path); n+=1\n"
            "print('patched',n)\n"
        )
        r = subprocess.run(
            ["docker", "exec", "-i", "sw-scanner-jobs", "python3", "-c", script],
            input=json.dumps(payload), capture_output=True, text=True)
        if r.returncode != 0:
            sys.exit(f"meta.json patch failed: {r.stderr.strip()[:300]}")
        print(f"  {r.stdout.strip()}")

    def vid_list(rs):
        return ",".join("'https://www.youtube.com/watch?v=%s'" % r["vid"] for r in rs)

    # ---- 2. corrected: patch the DB-side timeline offset ----------------
    if corrected:
        cases = " ".join(
            f"when video_url='https://www.youtube.com/watch?v={r['vid']}' "
            f"then '{r['recovered']}'::text" for r in corrected)
        sql = f"""
        update meetings set raw = jsonb_set(
                 raw, '{{speaker_timeline,caption_offset_s}}',
                 to_jsonb((case {cases} end)::float), true),
               updated_at = now()
        where municipality_slug='edmonton'
          and raw ? 'speaker_timeline'
          and video_url in ({vid_list(corrected)})
        """
        if args.apply:
            psql(sql)
            print(f"timeline caption_offset_s patched for {len(corrected)} meetings")
        else:
            print(f"timeline offsets to patch: {len(corrected)}")

    # ---- 3. corrected: invalidate npz + voice_map + speeches ------------
    removed = 0
    for r in corrected:
        p = os.path.join(CACHE, f"{r['vid']}.npz")
        if os.path.exists(p):
            if args.apply:
                os.remove(p)
            removed += 1
    print(f"npz caches to delete: {removed}")

    if corrected and args.apply:
        psql(f"""
        update meetings set raw = raw - 'voice_map', updated_at = now()
        where municipality_slug='edmonton' and video_url in ({vid_list(corrected)})
        """)
        n = psql(f"""
        with t as (
          update speeches s set politician_id = null, confidence = 0,
                 speaker_name_raw = 'UNATTRIBUTED',
                 -- qualify: meetings also has a `raw` column, so a bare
                 -- reference is ambiguous inside UPDATE ... FROM
                 raw = s.raw - 'attribution', updated_at = now()
          from meetings m
          where m.id = s.meeting_id and m.municipality_slug='edmonton'
            and s.raw->>'attribution' = 'voice'
            and m.video_url in ({vid_list(corrected)})
          returning 1)
        select count(*) from t""")
        print(f"  voice_map cleared; {n} voice speeches reset to bare")

    # ---- 4. unconfirmed: flag rather than delete ------------------------
    if unverified and args.apply:
        n = psql(f"""
        with t as (
          update speeches s set confidence = 0.3,
                 raw = s.raw || '{{"voice_unverified": true}}'::jsonb,
                 updated_at = now()
          from meetings m
          where m.id = s.meeting_id and m.municipality_slug='edmonton'
            and s.raw->>'attribution' = 'voice'
            and m.video_url in ({vid_list(unverified)})
          returning 1)
        select count(*) from t""")
        print(f"unverified: {n} voice speeches flagged voice_unverified")
    elif unverified:
        print(f"unverified: {len(unverified)} meetings would be flagged")

    if args.apply:
        print("\nnext: ./.venv/bin/python voice_attribute.py --cached-only")
        print("then: docker compose run --rm -T scanner "
              "resolve-meeting-caption-speakers --city edmonton")


if __name__ == "__main__":
    main()
