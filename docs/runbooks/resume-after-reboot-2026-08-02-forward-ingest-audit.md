# Resume after reboot — 2026-08-02 forward-ingest audit + GPU wedge

Session context: full forward-ingest audit across all jurisdictions + external-dep
quick win. All work is **done and verified** except (a) the GPU is wedged and
6,562 speech chunks await embedding, and (b) **14 changed files are uncommitted**.
This runbook is the pickup list after the reboot / GPU reset.

## 1. Why the reboot: GPU wedged (again)

During the backfill embed catch-up (`chunk-and-embed-speeches`, 8,866 chunks),
TEI faulted at 2,304 embeds: **Xid 45 ×7 → Xid 154 "GPU Reset Required"** —
the bursty-duty-cycle signature from the 580-fault memory
(`project_gpu_driver_open_580_fault.md`, updated with this recurrence). TEI fell
back to CPU; the scanner abort-guard stopped cleanly.

Per the established protocol, prefer the **full EC reset** over a warm reboot
(warm reboots have left the fans dead before): shut down, unplug, hold power
30 s, check vents, boot.

### Post-boot checks (in order)

```bash
# 1. GPU is back on CUDA (not CPU fallback)
docker logs sw-tei --tail 20 | grep -Ei "cuda|cpu"     # want "Starting Qwen3 model on Cuda"
docker ps --format '{{.Names}} {{.Status}}' | grep tei  # want (healthy) — healthcheck is device-aware

# 2. No fresh Xids
sudo dmesg | grep -i xid | tail -5

# 3. Drain the embed backlog (or just wait for the daily 08:00 UTC schedule)
docker compose run --rm scanner chunk-and-embed-speeches
docker exec sw-db psql -U sw -d sovereignwatch -c \
  "select count(*) from speech_chunks where embedding is null;"   # want 0
```

Backlog at shutdown: **6,562 chunks** (QC/NB backfill speeches). Small run —
but note this wedge happened on exactly this small nightly load shape, so if it
wedges again mid-drain, that further confirms the transient hypothesis; the
abort-guard makes retrying safe.

## 2. Commit the session's work (14 files, all verified working)

Nothing is committed. `git status` should show:

- `services/scanner/src/legislative/qc_hansard.py` — dropdown regex now tolerates
  the `Session en cours - ` prefix (root cause of the QC hole) + new
  `SessionNotInDropdownError` that no longer falls back to Wayback.
- `services/scanner/src/legislative/on_bills.py` — `discover_ola_bills_current()`
  (DB-latest session + successor probe) + `require_bills` phantom-session guard.
- `services/scanner/src/__main__.py` — `discover-on-bills` auto-resolve flags;
  new `check-ingest-freshness` command.
- `services/scanner/src/legislative/freshness.py` — **new file**, the sentinel.
- `services/scanner/src/legislative/ns_rss.py` — WAF-challenge sniff + retry +
  new-assembly canary.
- `services/scanner/src/jobs_catalog.py` + `services/api/src/routes/admin.ts` —
  two-place whitelist entries for `check-ingest-freshness`.
- `services/api/src/routes/lookup.ts` — local-first PIP rewrite (no more live
  Open North representatives call). **API image was rebuilt + deployed already.**
- `scripts/seed-daily-ingest-schedules.sql` — since_days removed, limit_sittings
  25, sentinel schedule row, NU comment.
- `docs/gotchas.md`, `docs/plans/sovereignty-runtime-deps.md` (row 7),
  `docs/research/{quebec,new-brunswick,nunavut}.md` — rules + incident notes.

Suggested split (or one commit if preferred):

```
fix(scanner): qc session-dropdown regex + loud SessionNotInDropdownError — closes 2.5mo QC hole
feat(scanner): ON bills successor probe + NS RSS WAF retry + new-assembly canary
feat(scanner): check-ingest-freshness sentinel (weekly, fails job on speech-vs-bill-event lag)
infra: drop since_days from daily hansard schedules — self-healing windows (seed + live rows)
feat(api): lookup.ts local-first PIP — drop uncached Open North representatives call
docs: forward-ingest gotchas rules + QC/NB/NU incident notes + sovereignty tracker row 7
```

## 3. Live DB state already changed (survives reboot, no action)

These were applied directly to `scanner_schedules` and are already consistent
with the updated seed script:

- 15 rows: `since_days` removed; NT/SK `limit_sittings` 5 → 25.
- NS Hansard row: hardcoded `{parliament:65, session:1}` cleared, renamed
  "NS Hansard daily ingest".
- New row: "Ingest freshness sentinel (weekly)", `37 13 * * 1`.

Backfills already ingested + resolved + coverage-refreshed: QC 43-3
(17 sittings / 3,961 speeches / +68 votes, current to 2026-06-12), NB
(+585 speeches to 2026-05-14), NU/NT verified current with upstream.

## 4. Verify the first self-healing nightly cycle (day after reboot)

The schedule change means tonight's Hansard jobs run **without** since_days for
the first time (full current-session re-list, etag-cached). Check durations and
outcomes the next morning:

```bash
docker exec sw-db psql -U sw -d sovereignwatch -c "
  select command, status, round(extract(epoch from finished_at-started_at)) as secs
    from scanner_jobs
   where queued_at > now() - interval '1 day'
     and command like 'ingest-%hansard%' or command like 'ingest-%committees'
   order by secs desc nulls last;"
```

Benchmark: flag-less `ingest-federal-hansard` measured **5m49s** (the worst
case; it also recovered 1,142 window-skipped speeches). If any job runs
pathologically long or times out (2 h daemon cap), that command is the candidate
for the `resolve_since()` high-water refinement noted in `docs/gotchas.md` —
do NOT just put `since_days` back.

The sentinel fires Monday 13:37 UTC; expected result all-ok (it passed manually
2026-08-02: 12 jurisdictions, 0 breaches). A FAILED sentinel job in the admin
panel = a jurisdiction's Hansard silently broke — wide `--since` re-run +
check session auto-resolution.

## 5. Small open threads (non-blocking)

- **NB corrupt PDF**: `61\2\hansard\33 2026-05-05b.pdf` fails pdftotext
  ("Couldn't find trailer dictionary") — retry in a week; if still broken, that
  sitting needs the NB Legislative Library. Noted in
  `docs/research/new-brunswick.md`.
- **QC resolver backlog**: 43-3 backfill left ~1.4K ambiguous speaker
  attributions (dated resolver got 1,575; the plain resolver's 44,922
  still-unresolved is the pre-existing historical backlog, not new).
- **NU upstream question** (research-handoff gated): will 2025+ transcripts
  appear on `/hansard`, or does the post-2025-election assembly publish
  elsewhere? See `docs/research/nunavut.md`.
- **ON successor probe** goes live implicitly — first real test is the next ON
  prorogation/election. Probe is nightly, idempotent, phantom-session-guarded.
- **Deferred dep work** (documented, not started): openparliament runtime
  mirror (sovereignty tracker row 4), ourcommons ingest alternative
  (`docs/research/federal.md`), local postcode-centroid table (PCCF, migration
  0055 seam), map tiles (tracker row 3).

## 6. Quick sanity one-liner after everything

```bash
docker compose run --rm scanner check-ingest-freshness   # want: breaches=0, exit 0
```
