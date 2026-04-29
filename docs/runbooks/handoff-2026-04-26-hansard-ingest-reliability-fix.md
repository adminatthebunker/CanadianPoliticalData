# Handoff — 2026-04-26 (Hansard ingest reliability — timeout fix + mid-loop stuck-job sweep)

**Session arc:** today's automated Hansard batch had 2 failures (NS, QC at the same `TimeoutError` on the post-pass `UPDATE speech_chunks` denormalisation) and 1 stuck `running` row (MB — subprocess died without parent flipping state). Root-caused both classes, shipped a focused fix, verified end-to-end live. Tomorrow morning is the real test: the same 9-job cron should produce 9/9 succeeded for the first time in ~3 days.

**Committed:** `0b00042 fix(scanner): hansard ingest timeouts + stale-job recovery` — already on local `main`, **not pushed** (branch is +4 vs. `origin/main`; user wanted to gate the push on a parallel WIP frontend branch).

**TL;DR — verify tomorrow ~21:00 UTC (after the 20:15 NL run, the last in the daily Hansard chain):**

```bash
docker exec sw-db psql -U sw -d sovereignwatch -c "
SELECT command, status, exit_code,
       EXTRACT(EPOCH FROM (finished_at - started_at))::int AS dur_s,
       LEFT(COALESCE(error,''), 60) AS err
  FROM scanner_jobs
 WHERE schedule_id IS NOT NULL
   AND queued_at::date = '2026-04-27'
   AND command ILIKE '%hansard%'
 ORDER BY queued_at;"
```

**Expected:** 9 rows, every `status='succeeded'`, `exit_code=0`, no `err` value. The sequence by UTC time:

| UTC  | Job                       | Healthy duration |
|------|---------------------------|------------------|
| 11:15 | `ingest-federal-hansard` | ~25 min          |
| 13:00 | `ingest-ns-hansard`      | ~2 min           |
| 14:15 | `ingest-bc-hansard`      | ~5 min           |
| 15:15 | `ingest-ab-hansard`      | ~3 min           |
| 16:15 | `ingest-qc-hansard`      | ~4 min           |
| 17:15 | `ingest-mb-hansard`      | ~2 min           |
| 18:20 | `ingest-on-hansard`      | ~3 min           |
| 19:15 | `ingest-nb-hansard`      | ~1 min           |
| 20:15 | `ingest-nl-hansard`      | ~1 min           |

If all 9 succeed, the timeout fix is validated under real cron load and this incident class is closed.

---

## What shipped

Commit `0b00042` — 8 files, +27 / −29.

### `services/scanner/src/db.py`
- Added `timeout: Optional[float] = None` kwarg to `fetch / fetchrow / fetchval / execute`. When `None`, the pool's `command_timeout=60` default still applies (no behavior change for any existing caller). When set, the asyncpg per-statement ceiling is overridden for that single call.
- Mirrors the idiom already in use at `ab_former_mlas.py:468/513` (timeout=600) and `mb_hansard.py:801` (timeout=1800), which previously had to drop to raw `db.pool.execute(..., timeout=…)` because the wrapper didn't expose it.

### `services/scanner/src/legislative/{ns,qc,mb,bc,nl,on}_hansard.py`
- Added `timeout=300` to the post-pass `UPDATE speech_chunks sc SET politician_id = s.politician_id …` call in each. Federal and AB Hansard pipelines do not run this exact post-pass and were not touched.
- Why: this UPDATE is the only statement in any Hansard pipeline that legitimately can run > 60 s under contention. NS/QC/MB had been failing on it intermittently for ~3 days; today both NS and QC tripped it on the same scheduled run.

### `services/scanner/src/jobs_worker.py`
- **Moved `recover_stuck_jobs(db)` from outside the loop (line 381) to inside the loop body.** The docstring claimed it ran every poll cycle; the code only fired at boot. That's why today's MB row sat stuck for 5 h — the worker was up the whole time but never re-ran the sweep.
- Removed the duplicate `db.fetchval(...)` UPDATE inside `recover_stuck_jobs` (it ran the same query twice; the first one threw away its result).
- Lowered `JOBS_STUCK_MINUTES` default from `10` → `5`. Safe because the single-worker architecture means the sweep only runs when the worker is *idle* between jobs — a healthy long-running ingest (e.g. federal at 25 min, embed at 7+ h) is never seen by the sweep, since the worker stays inside `run_job` for that entire time.
- Wrapped the new sweep call in its own try/except so a DB hiccup in the sweep doesn't skip `enqueue_due_schedules` or `claim_next_job`.

---

## How verified live (today, 22:18 UTC)

1. Restarted `scanner-jobs` after the edits land via the bind-mount.
2. Boot logs:
   ```
   22:18:35 jobs worker started (poll=5s, default_timeout=36000s, tail=4096 bytes)
   22:18:36 recovered 1 stuck job(s) from a stalled worker
   22:18:36 running job f12d08ed-…: python -m src ingest-mb-hansard
   ```
   The new sweep automatically caught the day-old stuck MB row on the very first poll iteration — no manual SQL cleanup was needed.
3. MB rerun completed cleanly: `succeeded exit=0 dur_s=202` — comfortably inside the new 300 s post-pass UPDATE budget.
4. **Mid-loop sweep test:** inserted a synthetic `refresh-coverage-stats` row with `started_at = now() - 20 min, status='running'` while MB was in flight. When MB finished, the next loop iteration swept the synthetic row and ran it inside 2 s. End-to-end log:
   ```
   22:21:57 finalised job f12d08ed-… succeeded
   22:21:57 recovered 1 stuck job(s) from a stalled worker
   22:21:57 running job 3a42b2b8-… python -m src refresh-coverage-stats
   22:21:59 finalised job 3a42b2b8-… succeeded exit=0
   ```

So the post-MB chain proved both the new timeout ceiling AND the new sweep cadence work as intended.

---

## If tomorrow's run fails

### Scenario A: a Hansard job fails with `TimeoutError` again

Means the 300 s budget isn't enough either. Check which statement:

```bash
docker exec sw-db psql -U sw -d sovereignwatch -c "
SELECT command, RIGHT(stderr_tail, 1500) AS tail
  FROM scanner_jobs
 WHERE status='failed'
   AND queued_at::date = '2026-04-27'
   AND command ILIKE '%hansard%';"
```

If the traceback still ends in `bind_execute / TimeoutError` at one of the `legislative/*_hansard.py` post-pass UPDATEs, the next escalation is to rewrite the UPDATE as a chunked statement (e.g. WHERE id between $low and $high, batches of 5k). Plan rejected this for today because `would_update=0` across all provinces in current state — the failure is timing-sensitive, not volume-driven. If it recurs, that conclusion was wrong.

### Scenario B: a job is stuck in `running` for > 5 min

Should now self-recover within ~5 min via the mid-loop sweep. To confirm the sweep is actually running:

```bash
docker logs sw-scanner-jobs --since 30m 2>&1 | grep -E "recovered|running job|finalised"
```

If you see `running job` lines but no `recovered N stuck job(s)` lines, the sweep is silent because nothing's stale (good) — silence is success here. If a row is genuinely stuck > 5 min and the sweep doesn't kick in, the worker is wedged; restart it: `docker compose restart scanner-jobs`.

### Scenario C: subprocess dies but row stays `running` (the original MB symptom)

Not the same as scenario B — scenario B is "the row is stuck and the sweep isn't catching it." Scenario C is "the subprocess is gone but the row keeps showing running" — exactly what bit us today. With the mid-loop sweep, this resolves itself in ~5 min instead of needing a manual restart. **Open question:** the *root cause* of the MB subprocess dying without the parent flipping state is still unidentified — the worker was alive (PID 1, 5 h uptime) yet the row never finalised. Could be an asyncio task hanging in `proc.wait()` after a docker-internal pipe break, but I didn't dig further. If this happens again with the new code in place, the sweep will paper over it within minutes, but the underlying bug is still there.

---

## Open followups

1. **Push to GitHub.** Commit `0b00042` is local-only. `git push origin main` once the WIP frontend branch (SpeechFilters / HansardSearchPage / hansard-search.css) is either landed or unstaged — I deliberately didn't bundle those into this commit.
2. **Find the root cause of the subprocess-died-no-finalise bug.** The mid-loop sweep is a backstop; the real bug is somewhere in `run_job` / `proc.wait()` / `_finalise`. Worth one focused session to instrument the subprocess lifecycle with debug logging and try to reproduce.
3. **Heartbeat column for future multi-worker safety.** Today's `JOBS_STUCK_MINUTES=5` is safe only because there's a single `scanner-jobs` container. If `scanner-jobs` is ever scaled to N replicas, a sibling worker could falsely sweep an in-flight job at minute 5. The proper fix is a `last_heartbeat_at` column updated periodically by `run_job`; the sweep checks heartbeat instead of `started_at`. Out of scope today; document this constraint in CLAUDE.md if anyone proposes scaling out.
4. **Server-side `statement_timeout` on the `sw` role?** Currently unset (verified live). The asyncpg `command_timeout=60` is the only timer. A server-side default would be a defense-in-depth layer but would also affect API queries — needs a separate decision.

---

## Files touched (committed)

- `services/scanner/src/db.py`
- `services/scanner/src/jobs_worker.py`
- `services/scanner/src/legislative/ns_hansard.py`
- `services/scanner/src/legislative/qc_hansard.py`
- `services/scanner/src/legislative/mb_hansard.py`
- `services/scanner/src/legislative/bc_hansard.py`
- `services/scanner/src/legislative/nl_hansard.py`
- `services/scanner/src/legislative/on_hansard.py`

## Plan reference

Full plan with rationale and what was *intentionally* left out of scope: `~/.claude/plans/linked-hugging-fox.md`.
