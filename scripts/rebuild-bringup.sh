#!/usr/bin/env bash
# scripts/rebuild-bringup.sh
#
# Bring sovpro back up on a freshly-installed OS, using nothing but what
# survives on the Internal NVMe. Written 2026-11-09 for the Ubuntu 26.04
# reinstall; companion to docs/runbooks/2026-11-09-fresh-ubuntu-rebuild.md,
# which carries the host-side (phase 1) steps this script only VERIFIES.
#
# Why this exists: the runbook is 195 lines and gets read at 2am with a
# half-rebuilt machine. The three things that actually cause damage are
# ordering constraints, not instructions — so they are refusals here.
#
#   ⛔ THE INVARIANT: /media/bunker-admin/Internal/cpd-pgdata is a BIND
#      MOUNT holding a live 323 GB cluster on a separate physical disk.
#      Nothing in this script writes to it, and every mode refuses to run
#      unless that path is a real mounted cluster. If the Internal NVMe
#      were unmounted and Docker started anyway, Postgres would initdb a
#      BLANK cluster over the live data directory. That is the failure
#      this file, the systemd drop-in, and the PG_VERSION sentinel all
#      guard independently.
#
# Modes (default: check):
#   check    verify host prerequisites and captured inputs. No changes.
#   volumes  restore sovpro_assets + sovpro_embedmodels from the capture.
#            Refuses any volume that already has content.
#   image    load the saved sovpro-db image (pinned pgvector 0.8.2).
#   up       docker compose up -d, then verify.
#   verify   the post-rebuild checks only.
#   all      check -> volumes -> image -> up -> verify
#
# Safe to re-run. Every mutating step is skip-if-already-done.

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INTERNAL=/media/bunker-admin/Internal
PGDATA="$INTERNAL/cpd-pgdata"
CAPTURE="${CAPTURE:-$INTERNAL/pre-reinstall-2026-11}"
MODE="${1:-check}"

FAIL=0
ok()   { printf '  \033[32m✓\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$*"; }
bad()  { printf '  \033[31m✗\033[0m %s\n' "$*"; FAIL=$((FAIL+1)); }
hdr()  { printf '\n\033[1m%s\033[0m\n' "$*"; }
die()  { printf '\n\033[31mFATAL:\033[0m %s\n' "$*" >&2; exit 1; }

# ── the guard every mode runs first ──────────────────────────────────
# PG_VERSION is the sentinel: it exists only inside a real initialised
# cluster. Its presence proves the Internal disk is mounted AT THE EXACT
# EXPECTED PATH, which a `mountpoint` check alone does not (a different
# disk mounted there would pass that and fail this).
guard_internal() {
  mountpoint -q "$INTERNAL" \
    || die "$INTERNAL is not a mountpoint. Mount the Internal NVMe before anything else."
  sudo test -f "$PGDATA/PG_VERSION" \
    || die "$PGDATA/PG_VERSION missing — this is NOT the live cluster. Refusing to continue."
}

# ── check ────────────────────────────────────────────────────────────
do_check() {
  hdr "Internal disk"
  ok "$INTERNAL mounted, cluster present (PG_VERSION=$(sudo cat "$PGDATA/PG_VERSION"))"
  if grep -qE '^UUID=[0-9a-f-]+[[:space:]]+/media/bunker-admin/Internal[[:space:]]' /etc/fstab; then
    grep -qE '^UUID=.*Internal.*nofail' /etc/fstab \
      && ok "fstab mounts it by UUID with nofail" \
      || warn "fstab mounts it by UUID but WITHOUT nofail — boot will hang if the disk is absent"
  else
    bad "fstab has no UUID= line for $INTERNAL (mounting by device name breaks on reorder)"
  fi

  hdr "The Docker interlock (must exist BEFORE Docker ever starts)"
  local drop=/etc/systemd/system/docker.service.d/require-internal-mount.conf
  if [[ -f $drop ]] && grep -q "RequiresMountsFor=$INTERNAL" "$drop"; then
    ok "require-internal-mount.conf present and correct"
  else
    bad "MISSING $drop — fstab 'nofail' is only safe because of this drop-in."
    bad "  install it from $CAPTURE/host/require-internal-mount.conf, then:"
    bad "  sudo systemctl daemon-reload && sudo systemctl restart docker"
  fi

  hdr "Host tooling"
  command -v docker >/dev/null && ok "docker $(docker --version | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)" || bad "docker not installed"
  docker compose version >/dev/null 2>&1 && ok "compose plugin present" || bad "docker compose plugin missing"
  command -v nvidia-smi >/dev/null \
    && ok "nvidia-smi: $(nvidia-smi --query-gpu=driver_version --format=csv,noheader 2>/dev/null | head -1)" \
    || bad "nvidia-smi missing — tei will fall back to CPU and its healthcheck will fail by design"
  # ⚠ Do NOT check for an 'nvidia' entry in `docker info` Runtimes. This
  # host attaches the GPU through CDI, not the legacy runtime shim:
  # /etc/docker/daemon.json has no "runtimes" block at all, and compose's
  # deploy.resources.reservations.devices (driver: nvidia) is resolved by
  # Docker 29 from a CDI spec. Checking for the runtime reports a failure on
  # a fully working machine — verified 2026-11-09 with sw-tei healthy.
  if [[ -f /var/run/cdi/nvidia.yaml || -f /etc/cdi/nvidia.yaml ]]; then
    ok "nvidia CDI spec present"
  elif docker info --format '{{json .Runtimes}}' 2>/dev/null | grep -q nvidia; then
    ok "legacy nvidia container runtime registered (no CDI spec)"
  else
    bad "no CDI spec and no nvidia runtime — the GPU reservation will fail"
    bad "  fix: sudo systemctl start nvidia-cdi-refresh.service"
  fi
  # The CDI spec lives under /var/run, which is TMPFS — it does not survive a
  # reboot on its own. nvidia-cdi-refresh.service (shipped with the toolkit,
  # WantedBy=multi-user.target, plus a .path unit watching modules.dep and
  # nvidia-ctk) regenerates it at every boot and on driver upgrade. If that
  # unit is not enabled, the GPU works until the next reboot and then
  # silently does not — so the unit, not a config file, is the dependency.
  systemctl is-enabled nvidia-cdi-refresh.service >/dev/null 2>&1 \
    && ok "nvidia-cdi-refresh.service enabled (regenerates the tmpfs spec at boot)" \
    || bad "nvidia-cdi-refresh.service NOT enabled — CDI spec will vanish on reboot"

  hdr "Secrets"
  # Existence AND non-emptiness, by name. Never print a value: this file
  # holds live Stripe keys, NEWT_ID/NEWT_SECRET and SMTP credentials.
  if [[ -f $REPO/.env ]]; then
    ok ".env present ($(grep -cE '^[A-Z_]+=' "$REPO/.env") variables)"
    # JWT_SECRET and API_KEY_PEPPER are UNREGENERABLE — regenerating
    # either invalidates every user session and every issued API key.
    # DB_PASSWORD must match the SURVIVING cluster, not a new value.
    local k
    for k in JWT_SECRET API_KEY_PEPPER DB_PASSWORD NEWT_ID NEWT_SECRET; do
      if grep -qE "^${k}=.+" "$REPO/.env"; then ok "  $k set"; else bad "  $k MISSING or empty"; fi
    done
  else
    bad ".env MISSING — restore it from the gpg secrets bundle before going further."
    bad "  ⛔ Do NOT regenerate JWT_SECRET or API_KEY_PEPPER. Both are unregenerable."
  fi

  hdr "Captured inputs at $CAPTURE"
  local f
  for f in volumes/sovpro_assets.tar volumes/sovpro_embedmodels-qwen.tar \
           sovpro_kumadata.tgz repo/sovpro-db-image.tar.zst \
           host/require-internal-mount.conf host/crontab-bunker-admin.txt \
           host/docker-daemon.json host/ufw-status.txt \
           host/scanner_schedules-2026-11-09.csv; do
    [[ -f $CAPTURE/$f ]] && ok "$f ($(du -h "$CAPTURE/$f" | cut -f1))" || warn "$f absent"
  done

  hdr "Repo-relative bind mounts compose expects"
  local d
  for d in data db scripts services/scanner/src docs nginx/conf.d; do
    [[ -e $REPO/$d ]] && ok "$d" || bad "$d MISSING from the repo"
  done
  # mkdocs/site is a BUILD ARTIFACT and is gitignored (.gitignore:84,
  # mkdocs/site/*) — 97 of its 98 files are absent from the git bundle. It
  # survives on Internal, but if it is ever lost, nginx serves a 404 at
  # docs.canadianpoliticaldata.org until it is rebuilt. The sources ARE
  # tracked (mkdocs/mkdocs.yml + 51 files under mkdocs/docs/), so the fix is
  # a rebuild, not a restore.
  if [[ -d $REPO/mkdocs/site && -f $REPO/mkdocs/site/404.html ]]; then
    ok "mkdocs/site present ($(find "$REPO/mkdocs/site" -type f | wc -l) files)"
  else
    bad "mkdocs/site missing or incomplete — the public docs site will 404."
    bad "  rebuild it: docker compose run --rm --entrypoint mkdocs docs build -f /docs/mkdocs.yml"
  fi
  # scripts/replicate-to-offsite.sh is UNTRACKED (gitignored) — the git
  # bundle does not carry it, and it is what makes the offsite copy happen.
  [[ -f $REPO/scripts/replicate-to-offsite.sh ]] \
    && ok "replicate-to-offsite.sh present (untracked — git does not carry it)" \
    || bad "scripts/replicate-to-offsite.sh MISSING — restore from the capture tarball"
  # media-cache is a 37 GB regenerable scrape cache; absence costs
  # re-fetches, not data. Create it so the mount does not make one.
  [[ -d $REPO/media-cache ]] || { mkdir -p "$REPO/media-cache"; warn "created empty media-cache/ (regenerable cache)"; }

  hdr "Result"
  if (( FAIL )); then
    printf '  \033[31m%d blocking problem(s).\033[0m Fix these before `up`.\n' "$FAIL"
    return 1
  fi
  ok "all prerequisites satisfied"
}

# ── volumes ──────────────────────────────────────────────────────────
# Restores ONLY the two regenerable-but-expensive volumes. kumadata is
# restored too for completeness, but note: the live volume was verified
# on 2026-11-09 to contain monitors=0, notifications=0, users=0 — Uptime
# Kuma was never configured, so there is nothing of value in it.
restore_volume() {
  local vol="$1" tar="$2" flag="$3"
  if [[ ! -f $tar ]]; then warn "$vol: no capture at $tar, skipping"; return 0; fi
  docker volume create "$vol" >/dev/null
  local n
  n=$(docker run --rm -v "$vol":/d busybox sh -c 'ls -A /d | wc -l')
  if [[ $n -gt 0 ]]; then
    warn "$vol already has $n entries — NOT overwriting (re-run after 'docker volume rm $vol' if you meant to)"
    return 0
  fi
  docker run --rm -v "$vol":/d -v "$(dirname "$tar")":/in:ro busybox \
    tar "x${flag}f" "/in/$(basename "$tar")" -C /d
  ok "$vol restored ($(docker run --rm -v "$vol":/d busybox sh -c 'du -sh /d | cut -f1'))"
}

do_volumes() {
  hdr "Restoring Docker named volumes (never pgdata — that is a bind mount)"
  restore_volume sovpro_assets      "$CAPTURE/volumes/sovpro_assets.tar"          ""
  restore_volume sovpro_embedmodels "$CAPTURE/volumes/sovpro_embedmodels-qwen.tar" ""
  restore_volume sovpro_kumadata    "$CAPTURE/sovpro_kumadata.tgz"                 "z"
}

# ── image ────────────────────────────────────────────────────────────
do_image() {
  hdr "Loading the saved sovpro-db image"
  # db/Dockerfile installs postgresql-16-pgvector UNPINNED. The live
  # cluster registers vector 0.8.2 against a 68 GB HNSW index, so a
  # fresh build means "whatever apt serves in 26.04" — which may not
  # read that index. Prefer the captured image.
  local t="$CAPTURE/repo/sovpro-db-image.tar.zst"
  if docker image inspect sovpro-db:latest >/dev/null 2>&1; then
    ok "sovpro-db:latest already present, skipping load"
  elif [[ -f $t ]]; then
    zstd -dc "$t" | docker load
    ok "loaded sovpro-db:latest from the 2026-11-09 capture"
  else
    warn "no saved image at $t — compose will build db/Dockerfile instead."
    warn "  After it starts, CHECK: select extversion from pg_extension where extname='vector';"
    warn "  It must report 0.8.2. A newer pgvector may not read the existing HNSW index."
  fi
}

# ── up ───────────────────────────────────────────────────────────────
do_up() {
  hdr "Starting the stack"
  local drop=/etc/systemd/system/docker.service.d/require-internal-mount.conf
  [[ -f $drop ]] || die "refusing to start: $drop is missing. Install the interlock FIRST."
  cd "$REPO"
  docker compose up -d
  ok "compose up issued; waiting 90s for healthchecks"
  sleep 90
}

# ── verify ───────────────────────────────────────────────────────────
do_verify() {
  hdr "Verification"
  local n
  n=$(cd "$REPO" && docker compose ps --services --status running | wc -l)
  # 14 is the production set. The 15th service, `docs`, is an
  # operator-only local mkdocs preview and is intentionally down — the
  # public docs site is served by nginx from the tracked mkdocs/site/.
  [[ $n -eq 14 ]] && ok "14/14 production services running" || bad "$n services running, expected 14"
  [[ -z $(cd "$REPO" && docker compose ps -q --status restarting) ]] \
    && ok "no restart loops" || bad "a service is restart-looping"

  docker exec sw-db pg_isready -U sw -d sovereignwatch >/dev/null 2>&1 \
    && ok "sovpro-db-ready" || bad "sovpro-db-ready FAILED"

  # Proves the SURVIVING cluster is attached, not a fresh initdb.
  local rows
  rows=$(docker exec sw-db psql -U sw -d sovereignwatch -tAc \
    'select count(*) from speech_chunks' 2>/dev/null || echo 0)
  if [[ ${rows:-0} -gt 1000 ]]; then
    ok "sovpro-db-rows: $rows speech_chunks (expected ~8.9M — compare host/row-counts-2026-11-09.txt)"
  else
    bad "sovpro-db-rows: only ${rows:-0}. ⛔ STOP. This may be a BLANK cluster."
    bad "  Do not run migrations or ingest. Check the bind mount before anything else."
  fi

  local pgv
  pgv=$(docker exec sw-db psql -U sw -d sovereignwatch -tAc \
    "select extversion from pg_extension where extname='vector'" 2>/dev/null || true)
  [[ $pgv == 0.8.2 ]] && ok "pgvector $pgv (matches the HNSW index)" \
    || bad "pgvector is '${pgv:-absent}', expected 0.8.2 — the 68 GB HNSW index may be unreadable"

  curl -fsS --max-time 10 http://localhost:8088 >/dev/null 2>&1 \
    && ok "sovpro-frontend responds" || bad "sovpro-frontend not responding on :8088"

  # The meaningful GPU check. The healthcheck is a single-token /embed
  # with --max-time 1 and FAILS ON CPU FALLBACK by design, so "healthy"
  # proves CUDA is working, not merely that a container started.
  local h
  h=$(docker inspect --format '{{.State.Health.Status}}' sw-tei 2>/dev/null || echo missing)
  [[ $h == healthy ]] && ok "tei-healthy (proves CUDA, not just a running container)" \
    || bad "tei is '$h' — on CPU fallback or down. Embedding runs will refuse to start (preflight)."

  hdr "Not checked here — do these by hand"
  cat <<'NOTE'
  · scanner_schedules: expect 118 enabled / 122 total.
      docker exec sw-db psql -U sw -d sovereignwatch -tAc \
        'select count(*) filter (where enabled), count(*) from scanner_schedules'
    ⛔ Do NOT re-seed from the August runbook's Appendix A: those rows predate
       the 2026-09-10 overnight-window rewrite and name Open North commands
       (ingest-mps / ingest-mlas / ingest-councils) REMOVED on 2026-08-27.
       They now `die`. Use host/scanner_schedules-2026-11-09.csv.
  · OS crontab: install from host/crontab-bunker-admin.txt (8 jobs).
    ⛔ Read it first and confirm the 00:00 backup line is NOT commented out.
       In August, the capture was taken after #PREWIPE# had commented it out,
       rebuild.sh installed it verbatim, and the nightly dump silently never
       ran again — while verify passed, because it diffed the same file.
  · Public reachability through the Pangolin tunnel, from OFF-network:
    canadianpoliticaldata.org and docs.canadianpoliticaldata.org.
  · One embed batch while watching `sudo dmesg -w` for Xid errors — the
    regression check for whichever NVIDIA driver got installed.
NOTE

  hdr "Result"
  if (( FAIL )); then printf '  \033[31m%d check(s) failed.\033[0m\n' "$FAIL"; return 1; fi
  ok "stack verified"
}

guard_internal
case "$MODE" in
  check)   do_check ;;
  volumes) do_volumes ;;
  image)   do_image ;;
  up)      do_up && do_verify ;;
  verify)  do_verify ;;
  all)     do_check && do_volumes && do_image && do_up && do_verify ;;
  *)       die "unknown mode '$MODE' (check|volumes|image|up|verify|all)" ;;
esac
