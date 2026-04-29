# Resume after reboot — 2026-04-28 (BC pre-P38 Hansard, embed phase still partial)

**Status when paused:** Continuation of `resume-after-reboot-2026-04-27-bc-pre-p38-embed.md`. After reboot + clean boot on CUDA, `embed-speech-chunks` ran for ~70 min and embedded **172,576 of the 423,798 pending BC chunks** before the GPU re-entered the same `NV_ERR_RESET_REQUIRED` (Xid 62) state from the prior session. **251,222 chunks still NULL**, all in P29-P33 (the legacy ALL-CAPS era). Resolvers + coverage refresh shipped (they don't need GPU). Branch is **+8 vs origin/main, still not pushed** (no new commits this session — same eight as 2026-04-27).

**TL;DR to resume:**

```bash
# 1) After reboot, confirm GPU + TEI are clean.
docker compose up -d tei
docker compose logs tei --tail 25 | grep -iE "cuda|cpu|qwen|warming|ready"
# Required: "Starting Qwen3 model on Cuda" + "Ready". If "on Cpu", see §"GPU recovery escalations".

# 2) Embed the 251,222 pending BC chunks (idempotent — only touches NULL).
docker compose run --rm scanner embed-speech-chunks
# At ~2.1K chunks/min observed mix, ETA ~2 hours.
# If the run dies again at ~70 min with the same Xid 62, see §"Why the GPU keeps faulting".

# 3) (Already done 2026-04-28; safe to re-run, all idempotent.)
docker compose run --rm scanner resolve-bc-speakers
docker compose run --rm scanner resolve-presiding-speakers --province BC
docker compose run --rm scanner refresh-coverage-stats

# 4) Once embed finishes cleanly, push the branch.
git push origin main
```

---

## What this session accomplished

| Step | Result |
|---|---|
| Reboot recovered GPU → CUDA | ✓ TEI loaded `FlashQwen3 on Cuda(DeviceId(1))`, `Ready` |
| Embed 423,798 BC chunks | ✗ Partial — 172,576 done, then Xid 62 at T+70min |
| `resolve-bc-speakers` | ✓ no-op (`updated=0`; already steady-state) |
| `resolve-presiding-speakers --province BC` | ✓ no-op (roster gap, only 5 known officers) |
| `refresh-coverage-stats` | ✓ BC: 577,013 → **577,252 speeches** (+239 from overnight daily-ingest schedule) |

Per-parliament resolution rates are **unchanged from the 2026-04-27 ledger** — running resolvers without new roster data didn't lift any percentages. P34-P43 are 100% embedded; P29-P33 (which already sit at 9-23% resolution because LIMS roster doesn't go back) are 100% unembedded.

---

## Why the GPU keeps faulting — root-cause analysis

### Symptom

Kernel `NVRM` ring buffer starts logging this at 10:30:59 local, ~70 min into the embed run:

```
NVRM: rpcRmApiAlloc_GSP: GspRmAlloc failed:
      hClass=0x0000c56f; status=0x00000062
NVRM: nvAssertOkFailedNoLog: Assertion failed:
      Reset required [NV_ERR_RESET_REQUIRED] (0x00000062)
```

Same fingerprint as the 2026-04-17 cudnn-fix runbook: **Xid 62 → Xid 154 → "GPU Reset Required"**. From this point every CUDA RPC fails; TEI restart-loops and falls to CPU; only a driver reset (or reboot) clears it.

### Why "I had overnight runs work before" — and why they don't now

Pieced together from `project_embed_regression.md` memory + 2026-04-17 cudnn-fix runbook + dpkg history:

| Date | Event |
|---|---|
| pre-2026-04-15 | Overnight embed runs (~71K chunks each) **succeeded reliably** on the legacy `services/embed/` (BGE-M3 + FlagEmbedding + PyTorch) |
| 2026-04-15 | `linux-modules-nvidia-580-open-6.17.0-22` kernel module installed (apt) |
| 2026-04-16 | `nvidia-firmware-580-580.95.05` firmware updated (apt) |
| 2026-04-17 | **First Xid 62 crashes observed.** Run survival drops from ~71K chunks → **~448 chunks**. cudnn-fix runbook traces it to a cuDNN 9.1 fp16-attention bug on sm_89 (true contributing factor — fp16 attention is the heaviest GSP user) |
| ≈ 2026-04-18 | Migration to TEI / Qwen3 / Candle (no more PyTorch/cuDNN attention path); survival window jumps to ~70 min / **~170K chunks** |
| 2026-04-27 | First crash this corpus: ~106K chunks before Xid 62 |
| 2026-04-28 | Second crash this corpus: ~172K chunks before Xid 62 |

The TEI migration sidestepped *most* of the cuDNN-attention failure mode (150× improvement in survival) but **didn't fix the underlying open-kernel-driver GSP regression introduced in mid-April**. TEI just trips it more slowly. That's why "overnight runs used to work" but reboots now buy you ~70 min apiece.

### Most likely root cause

**`nvidia-driver-580-open` (open-kernel variant) running on the AD107M (RTX 4050 Laptop) is hitting a GSP firmware regression** introduced in the 2026-04-15/16 module + firmware push. Evidence:

1. **`-open` is the variant most prone to this.** NVIDIA's open-kernel modules originated for datacenter Hopper/Blackwell and were back-ported to consumer Ada. Mobile RTX 40-series is the population with the most reported GSP regressions in the field.
2. **The regression date matches precisely.** dpkg log shows the kernel module + firmware update window exactly bracketing the first observation of Xid 62 in the project.
3. **Workload pattern doesn't fit.** TEI's per-batch CUDA stream allocation rate is way *lower* than PyTorch eager mode would be — yet PyTorch ran for tens of thousands of chunks pre-regression and TEI dies at hundreds of thousands now. The driver state is the differentiating variable.
4. **No thermal / OOM / hardware signal.** GPU memory headroom was 4.4 GiB free at fault time; nothing in `nvidia-smi -q` indicated thermal events; `dmesg` shows only NVRM RPC failures, no MMU faults or ECC events.

Confidence: **medium-high.** Strong against alternative hypotheses but un-cited against a specific NVIDIA bug ID. A definitive proof would require either (a) reverting to the pre-2026-04-15 kernel module and showing recovery, or (b) swapping to closed driver and showing recovery. Both are mitigation experiments worth doing.

### What it is *not*

- **Not thermal** — 13°C headroom, no events in `nvidia-smi -q -d TEMPERATURE` historically.
- **Not VRAM OOM** — `4467 MiB free` at fault time per `nvidia-smi`.
- **Not the same cuDNN 9.1 bug from 2026-04-17** — TEI/Candle doesn't go through cuDNN attention. That bug was a separate, faster-tripping fault.
- **Not a TEI-specific issue** — same Xid signature appeared with the legacy embed wrapper after the 2026-04-15/16 update.
- **Not concurrent-GPU contention.** Steam Helper held 5 MiB; nothing else was running. Headroom was generous.

---

## GPU recovery escalations (after reboot, if needed)

In order of escalation. The runbook from 2026-04-27 noted that step 1 (`rmmod nvidia_uvm`) was insufficient for the prior fault — that's because `NV_ERR_RESET_REQUIRED` is GSP-firmware-side, not UVM-side. For *this* class of fault, escalate straight to step 3 if the GPU comes back wedged:

```bash
# 1) Reload nvidia-uvm kernel module — may help on userspace-context faults but
#    NOT for NV_ERR_RESET_REQUIRED. Try first only because it's cheap.
sudo rmmod nvidia_uvm && sudo modprobe nvidia_uvm

# 2) Restart docker daemon — picks up fresh nvidia-container-runtime state.
sudo systemctl restart docker
docker compose up -d

# 3) Reload ALL nvidia kernel modules — required for NV_ERR_RESET_REQUIRED.
sudo rmmod nvidia_uvm nvidia_drm nvidia_modeset nvidia
sudo modprobe nvidia
docker compose up -d

# 4) Full reboot — last resort, but the only thing guaranteed to clear GSP state.
sudo reboot
```

After any of the above:

```bash
docker compose logs tei --tail 30 | grep -iE "cuda|cpu|qwen"
# Want: "Starting Qwen3 model on Cuda", NOT "on Cpu".
```

---

## Mitigation candidates (in expected-leverage order)

These are experiments to try in a future session, not actions to run during this resume. Pick one and try it after the embed finishes (or in parallel with continuing on partial completion). All require user authorization because they modify host packages or services.

### 1. Switch to the proprietary kernel module (highest leverage)

Same 580.x version, different module variant. Replaces `nvidia-driver-580-open` with `nvidia-driver-580`. The proprietary module is more battle-tested on consumer Ada Mobile.

```bash
# Investigate first — confirm what's installed and what's available.
apt-cache policy nvidia-driver-580 nvidia-driver-580-open
# 580.126.09 installed (-open); 580.142 available in -updates.

# Swap (will pull replacement modules, no reboot but TEI must stop first).
docker compose stop tei
sudo apt install nvidia-driver-580   # closed variant, same version family
sudo reboot                           # required — module replacement
```

**Expected effect:** if this is the right fix, the embed run will sustain past 70 min on the next attempt. If it doesn't help, we've narrowed to "GSP firmware regression independent of module variant" and the next experiment is driver downgrade.

### 2. Upgrade to 580.142 (lower risk, lower leverage)

Newer point release of the open driver. The `-updates` channel may include a GSP fix that didn't make it into 580.126.

```bash
sudo apt install nvidia-driver-580-open=580.142-0ubuntu0.25.10.1
sudo reboot
```

### 3. Enable persistence mode correctly

`nvidia-persistenced` is `active` but `persistence_mode = Disabled` — the daemon is running with the wrong flags. Persistence mode keeps the GPU initialized continuously, avoiding the context-teardown path that's the most common GSP-state-corruption trigger.

```bash
# Inspect the unit.
systemctl cat nvidia-persistenced
# Likely needs --persistence-mode in ExecStart, plus a kernel cmdline tweak
# (NVreg_PreserveVideoMemoryAllocations=1 conflicts with persistence; resolve before flipping).
```

This is **complementary** to (1) or (2) — not a replacement.

### 4. Periodic TEI restart workaround (no driver change)

If we don't want to touch the driver yet, this is the cheapest workaround: bounce TEI every 50 min during long embed runs, before the GSP wall.

```bash
# Manual: in a separate shell, every ~50 min while the embed runs.
docker compose restart tei
# Or via cron — see scripts/seed-daily-ingest-schedules.sql for the pattern.
```

Not a fix; just gives the embed a fighting chance to finish in one calendar day. Each restart costs ~30 sec of throughput.

### 5. Lower `TEI_MAX_BATCH_TOKENS`

Default is 16384 (compose env). Halving to 8192 reduces per-batch GSP allocation pressure at the cost of throughput. Worth testing if (1) and (2) don't help.

```yaml
# In docker-compose.yml or .env
TEI_MAX_BATCH_TOKENS: 8192
```

---

## Verification ladder after embed eventually completes

Run all four. Expected values reflect the **2026-04-28 baseline** (BC speeches now 577,252, not the 2026-04-27 runbook's 577,013):

```sql
-- 1) All BC chunks embedded
SELECT count(*) FILTER (WHERE sc.embedding IS NULL) AS unembedded
  FROM speech_chunks sc JOIN speeches s ON s.id=sc.speech_id
 WHERE s.source_system='hansard-bc';
-- expected: 0

-- 2) BC speech + chunk totals match
SELECT count(*) FROM speeches WHERE source_system='hansard-bc';
-- expected: 577,252 ± daily-ingest drift

SELECT count(*) FROM speech_chunks sc JOIN speeches s ON s.id=sc.speech_id
 WHERE s.source_system='hansard-bc';
-- expected: 811,520 ± daily-ingest drift

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

---

## State at pause

- TEI: **on CPU fallback** (degrades public `/search/speeches` semantic queries; fix by resolving GPU after reboot).
- Branch: **+8 vs origin/main, not pushed.** No new commits this session — the same eight commits from 2026-04-27 are still local. Top of stack: `7362711 feat(scanner): bc hansard pre-p38 era-branching parser`.
- Working tree: identical to 2026-04-27 pause (frontend / blog / socials WIP from prior conversations, untouched).
- 251,222 BC chunks unembedded, all P29-P33.
- Resolvers + coverage refresh: clean and current.

When the embed finishes, the safe push is just `git push origin main` — the WIP working tree stays local.

---

## Out of scope (still parked)

Carried over from 2026-04-27 plus one new item:

- **Pre-P35 BC roster backfill** (1872-1991). Would lift P29-P34 resolution from ~10 % to ~80 %. Roster source candidates: elections.bc.ca historical MLA list, Wikipedia, BC Archives.
- **BC pre-P38 bills backfill** (PDMS, ~140 sessions back to 1872).
- **BC committee transcripts** (Section A / Section C HDMS files).
- **QC pre-2009 Hansard backfill** (assnat WebForms 500s; Wayback CDX-only past 39-1).
- **TEI throughput tuning** for legacy-era chunks (longer mean length, ~3K/min vs ~17K/min modern).
- **NEW: file an upstream NVIDIA driver bug** if the closed-module swap (mitigation #1) confirms the open-kernel variant is the trigger. Repro recipe is well-defined: sustained Qwen3 inference on TEI, ~70 min on RTX 4050 Laptop, reproducible Xid 62.
