# Resume after reboot — 2026-04-29 (BC pre-P38 Hansard, final 9,526 chunks + new resilience layer)

**Status when paused:** Continuation of `resume-after-reboot-2026-04-28-bc-pre-p38-embed-continued.md`. Today's run embedded **241,696 of 251,222 pending BC chunks** in ~95 minutes — clearing the historical 70-min Xid 62 wall — before TEI panicked with a *new* fault signature (`CUDA_ERROR_LAUNCH_FAILED`, no Xid in `dmesg`) and dropped to a CPU-fallback restart loop. **9,526 chunks still NULL**, all in P29-P33 (legacy ALL-CAPS era). Branch is **+8 vs origin/main, still not pushed** — same eight commits from 2026-04-27.

**Three resilience changes shipped before the reboot.** They are live for the next embed run; you do not need to do anything to enable them. See § "What's new since the last runbook".

**TL;DR to resume:**

```bash
# 1) After reboot, confirm GPU + TEI are clean.
docker compose up -d tei
docker compose ps tei                                        # wait for "healthy"
docker compose logs tei --tail 25 | grep -iE "cuda|cpu|qwen|warming|ready"
# Required: "Starting Qwen3 model on Cuda" + "Ready". The new healthcheck
# only flips to "healthy" after a successful single-token /embed roundtrip
# in <1s — i.e. it has already verified CUDA, not just port liveness.

# 2) Embed the 9,526 pending BC chunks (idempotent — only touches NULL).
docker compose run --rm scanner embed-speech-chunks
# At ~3K chunks/min on the legacy era, ETA ~3 min.
# The new preflight check refuses to start if TEI is on CPU; retries
# absorb a single TEI panic+restart; aborts after 5 consecutive batch
# failures rather than silently grinding through the corpus.

# 3) Verification ladder (see § "Verification ladder").

# 4) Push the branch.
git push origin main
```

---

## What's new since the last runbook

Three changes shipped at the end of 2026-04-28 to stop today's failure mode from silently wasting another full embed run:

### 1. Embed-client retry + abort + preflight (`services/scanner/src/legislative/speech_embedder.py`)

| Layer | Behaviour | Tunable |
|---|---|---|
| Preflight | Sends one tiny `/embed` request before fetching pending rows; refuses to start if elapsed > threshold (CUDA <200ms, CPU 2-10s) | `EMBED_PREFLIGHT_DEVICE_LATENCY_MS` (default 1500ms; ≤0 disables) |
| Per-batch retry | Each batch retries up to N times with exponential backoff (1s → 2s → 4s → 8s → 16s = 31s of slack — sized to absorb one TEI panic + CUDA restart cycle) | `EMBED_RETRY_MAX_ATTEMPTS` (5), `EMBED_RETRY_BASE_DELAY` (1.0) |
| Abort guard | After K consecutive post-retry batch failures, abort the whole run instead of `continue`-ing through the rest of the corpus marking everything `errors` | `EMBED_MAX_CONSECUTIVE_FAILURES` (5) |

The abort surfaces in the summary line as `aborted=True` (red instead of green). The previous behaviour silently lost 9,526 chunks on 2026-04-28 with `errors=~3000` and `embedded=241696`.

### 2. Compose-level TEI healthcheck + capped restart (`docker-compose.yml`)

```yaml
healthcheck:
  test: ["CMD-SHELL", "curl -fsS --max-time 1 -X POST -H 'Content-Type: application/json' -d '{\"inputs\":[\"x\"],\"normalize\":true}' http://localhost/embed >/dev/null"]
  interval: 60s
  timeout: 3s
  retries: 3
  start_period: 120s
restart: on-failure:5
```

`--max-time 1` makes curl fail on CPU fallback (which takes 2-10s to return). The container reports `unhealthy` within ~3 minutes of degradation. `restart: on-failure:5` (was `unless-stopped`) caps the doomed-CUDA-init loop at 5 attempts so a wedged driver no longer triggers an infinite CPU-bounce that masks the underlying problem.

### 3. `TEI_MAX_BATCH_TOKENS` default 16384 → 8192 (`docker-compose.yml`)

Halves per-batch GSP firmware allocation pressure on the open-kernel driver regression. Modest throughput cost; substantial reliability gain. Documented in `docs/gotchas.md` § "Do not bump `TEI_MAX_BATCH_TOKENS` back to 16384 without driver work" — don't revert until the closed-module driver swap (mitigation #1) is in.

---

## What this session accomplished (2026-04-28)

| Step | Result |
|---|---|
| Reboot recovered GPU → CUDA | ✓ TEI loaded `FlashQwen3 on Cuda(DeviceId(1))`, `Ready` |
| Embed 251,222 BC chunks | ✗ Partial — 241,696 done, then `CUDA_ERROR_LAUNCH_FAILED` at T+95min |
| Resilience layer (preflight + retry + abort + healthcheck + restart cap + lower batch tokens) | ✓ Shipped before reboot — active for the next embed run |
| Branch | unchanged: +8 vs origin/main, no new commits this session |

The +95min survival window beat the 2026-04-27 / 2026-04-28 runs (+70min and +106K-chunk respectively). Whether the new fault class (CUDA_ERROR_LAUNCH_FAILED with no Xid) will recur after recovery is unknown — the resilience layer protects against it either way.

---

## The new fault signature (different from 2026-04-27 / 2026-04-28)

Earlier sessions failed with **Xid 62 / NV_ERR_RESET_REQUIRED** in `dmesg` — a kernel-side GSP firmware fault requiring module reload to clear.

Today's failure was different:

```
thread '<unnamed>' (41) panicked at /root/.cargo/git/checkouts/cudarc-.../src/driver/safe/core.rs:257:76:
called `Result::unwrap()` on an `Err` value:
DriverError(CUDA_ERROR_LAUNCH_FAILED, "unspecified launch failure")
```

Followed by every TEI restart hitting `DriverError(CUDA_ERROR_UNKNOWN, "unknown error")` on CUDA init and falling to CPU. **No NVRM/Xid lines in `dmesg`.** `nvidia-smi` reported 71% util / 15 MiB used — telemetry sticky from the wedged context.

This is consistent with the same hypothesised root cause (open-kernel driver GSP regression) expressing through a different code path. The cudarc panic is "softer" in that the kernel didn't see it as a hardware reset; the `CUDA_ERROR_UNKNOWN` on subsequent inits is the userspace-context-corruption symptom rather than the GSP-firmware one.

**Practical implication for recovery:** the runbook's earlier-noted "step 1 (`rmmod nvidia_uvm`) is insufficient" may not apply to this fault class. Try the lighter step first.

---

## GPU recovery escalations (after reboot, if needed)

In ascending blast-radius. Pattern matches the 2026-04-28 runbook but the lighter steps may now suffice for this newer fault class:

```bash
# 1) Reload nvidia-uvm kernel module — try first for this softer fault class.
sudo rmmod nvidia_uvm && sudo modprobe nvidia_uvm

# 2) Restart docker daemon — refreshes nvidia-container-runtime state.
sudo systemctl restart docker
docker compose up -d

# 3) Reload ALL nvidia kernel modules — required for NV_ERR_RESET_REQUIRED.
sudo rmmod nvidia_uvm nvidia_drm nvidia_modeset nvidia
sudo modprobe nvidia
docker compose up -d

# 4) Full reboot — guaranteed to clear all GPU state.
sudo reboot
```

After any of the above:

```bash
docker compose up -d tei
docker compose ps tei              # wait for "healthy" — proves CUDA via the new healthcheck
```

---

## Verification ladder after embed completes

Run all four. Expected values reflect the **2026-04-29 baseline** (BC speeches at the latest count after overnight daily-ingest drift):

```sql
-- 1) All BC chunks embedded
SELECT count(*) FILTER (WHERE sc.embedding IS NULL) AS unembedded
  FROM speech_chunks sc JOIN speeches s ON s.id=sc.speech_id
 WHERE s.source_system='hansard-bc';
-- expected: 0

-- 2) BC speech + chunk totals match
SELECT count(*) FROM speeches WHERE source_system='hansard-bc';
-- expected: 577,252+ (± daily-ingest drift since 2026-04-28)

SELECT count(*) FROM speech_chunks sc JOIN speeches s ON s.id=sc.speech_id
 WHERE s.source_system='hansard-bc';
-- expected: 811,520+ (± daily-ingest drift)

-- 3) Per-parliament resolution rates didn't regress
SELECT raw->'bc_hansard'->>'parliament' AS parl,
       count(*) AS speeches,
       round(100.0*count(*) FILTER (WHERE politician_id IS NOT NULL)/count(*),1) AS pct
  FROM speeches WHERE source_system='hansard-bc'
 GROUP BY 1 ORDER BY 1::int;
-- P29-P33: 9-23 %; P34: 49.8 %; P35-P37: 87-99 %; P38-P43: 88-94 %.

-- 4) Coverage stats refreshed
SELECT jurisdiction, hansard_status, speeches_count, politicians_count, bills_count
  FROM jurisdiction_sources WHERE jurisdiction='BC';
-- expected: live | 577,252+ | 381 | 2,277
```

If all four are clean, push:

```bash
git push origin main
```

---

## Mitigation candidates still parked

These are unchanged from the 2026-04-28 runbook — not done in this session because the resilience layer made them less urgent. Still worth doing in expected-leverage order:

1. **Switch to `nvidia-driver-580` (proprietary kernel module).** Highest leverage. The `-open` variant is the most likely root cause; the closed module is more battle-tested on consumer Ada Mobile. Requires reboot.
2. **Upgrade to 580.142** (lower risk, lower leverage).
3. **Enable persistence mode correctly** (`nvidia-persistenced` is active but `persistence_mode = Disabled`).
4. **Periodic preventive TEI restart** (cron-driven `docker compose restart tei` every 50 min during long jobs) — partially obsoleted by the new resilience layer; the embed client now survives a single TEI restart automatically.
5. **File an upstream NVIDIA driver bug** if (1) confirms the open-kernel variant is the trigger. Repro is well-defined now: sustained Qwen3 inference on TEI, ~70-95 min on RTX 4050 Laptop, two distinct failure signatures (Xid 62 with `dmesg` log, or `CUDA_ERROR_LAUNCH_FAILED` without).

---

## State at pause

- TEI: stopped (was restart-looping on CPU fallback after fault; `docker compose stop tei` issued before the recovery).
- Branch: **+8 vs origin/main, not pushed.** Top of stack: `7362711 feat(scanner): bc hansard pre-p38 era-branching parser`. Resilience changes are uncommitted in the working tree alongside the prior pause's untouched WIP.
- Working tree: prior 2026-04-27 WIP (frontend / blog / socials, untouched) plus today's resilience edits (`docker-compose.yml`, `services/scanner/src/legislative/speech_embedder.py`, `services/scanner/src/__main__.py`, `CLAUDE.md`, `docs/operations.md`, `docs/architecture.md`, `docs/gotchas.md`, this runbook).
- 9,526 BC chunks unembedded, all P29-P33.
- Resolvers + coverage refresh: clean and current as of 2026-04-28.

When the embed finishes, decide what to do with the resilience changes:
- Commit them as a separate `feat(scanner): tei + embed resilience layer` commit before pushing, *or*
- Roll them into a follow-up commit after the verification ladder passes.

The earlier runbook's "safe push is just `git push origin main`" still holds for the +8 commits already in place; the resilience changes are working-tree-only and don't ride along until you choose to commit them.

---

## Out of scope (still parked — same list as 2026-04-28)

- Pre-P35 BC roster backfill (1872-1991). Would lift P29-P34 resolution from ~10% to ~80%.
- BC pre-P38 bills backfill (PDMS, ~140 sessions back to 1872).
- BC committee transcripts (Section A / Section C HDMS files).
- QC pre-2009 Hansard backfill (assnat WebForms 500s; Wayback CDX-only past 39-1).
- TEI throughput tuning for legacy-era chunks (longer mean length, ~3K/min vs ~17K/min modern).
- File an upstream NVIDIA driver bug after closed-module swap confirms the trigger.
