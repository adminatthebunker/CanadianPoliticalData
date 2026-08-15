#!/usr/bin/env bash
# One-time venv for the voice auditor. torch/speechbrain deliberately live
# here, NOT in the scanner image (~1.2GB of CPU-torch the daily pipeline
# doesn't need). Run from this directory:
#   ./bootstrap.sh && source .venv/bin/activate && python voice_audit.py <VIDEO_ID>
set -euo pipefail
cd "$(dirname "$0")"
python3 -m venv .venv
./.venv/bin/pip install --upgrade pip
# CPU-only torch keeps the install small-ish and sidesteps the GPU driver
# fault entirely (the auditor runs ~12x realtime on CPU).
# torchaudio must come from the same CPU index — plain PyPI serves a
# CUDA build that dies on import (libcudart.so not found).
./.venv/bin/pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
./.venv/bin/pip install speechbrain soundfile numpy "yt-dlp>=2026.7.4"
echo "done. activate with: source $(pwd)/.venv/bin/activate"
