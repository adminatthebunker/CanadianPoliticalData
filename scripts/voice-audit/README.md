# voice-audit — ECAPA voice-fingerprint audit of caption attributions

Offline batch auditor for Edmonton caption-speech attributions, ported from
the 2026-08-14 diarization PoC (numbers + method:
`docs/runbooks/edmonton-diarization-poc-2026-08-14.md`).

Role: **auditor, not attributor.** It embeds every caption turn with
ECAPA-TDNN (CPU), enrolls per-councillor voiceprints from the high-confidence
text attributions (macro/recognition), and checks the inferred tiers
(alternation / panel / chair) against the voice. Disagreements go into a TSV
for human review — the PoC's auditor run is what caught the block-alternation
phase-inversion bug.

PoC accuracy context: 90.4% leave-one-out on ≥3 s turns, 97.1% ≥5 s,
98.3% ≥8 s, after per-video caption-lag correction (~5 s, measured — the
script measures it per run unless `--lag` is given). Unknown-voice rejection
at cosine 0.60 correctly bounces staff/public speakers.

```bash
./bootstrap.sh                       # one-time venv (~1.2GB, CPU torch)
source .venv/bin/activate
python voice_audit.py YAobWoLOnO0    # ~15-25 min per 8h meeting, all CPU
```

Requires: docker (DB access goes through `docker exec sw-db psql`), ffmpeg
on PATH (yt-dlp's wav extraction).

Not in scope (deliberately): caption-less videos — no captions means no turn
boundaries, and the PoC showed blind window clustering fails. That needs a
separate segmentation + Whisper spike (GPU).
