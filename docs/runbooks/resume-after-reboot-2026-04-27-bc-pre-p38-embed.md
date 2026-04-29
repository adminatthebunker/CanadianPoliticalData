# Resume after reboot — 2026-04-27 (BC pre-P38 Hansard, embed phase pending)

**Status when paused:** BC + QC historical-roster backfills **shipped** (commits `83ab13f` + `7362711`); BC pre-P38 Hansard **ingest + resolve shipped** (P29 1970 → P37 2005, +378,465 speeches, BC corpus 198K → 577K). The **embed phase did NOT complete** — TEI hit `CUDA_ERROR_UNKNOWN` after embedding 106,432 chunks and fell back to CPU; container restart + recreate did not recover GPU access. **~423,798 BC chunks still have NULL embedding.** Reboot is the clean fix. Branch is +8 vs origin/main, **not pushed**.

**TL;DR to resume:**

```bash
# 1) After reboot, confirm GPU + TEI are clean.
docker compose up -d tei
docker compose logs tei --tail 25 | grep -iE "cuda|cpu|qwen|warming|ready"
# Required: "Starting Qwen3 model on Cuda" + "Ready". If "on Cpu", see §"GPU recovery fallback".

# 2) Embed the 423,798 pending BC chunks (idempotent — only touches NULL).
docker compose run --rm scanner embed-speech-chunks
# Throughput: ~17K chunks/min modern era / ~3K/min legacy era.
# Pending mix is mostly legacy → estimate 90-150 min total.

# 3) Run resolvers + presiding-officer pass + coverage refresh.
docker compose run --rm scanner resolve-bc-speakers
docker compose run --rm scanner resolve-presiding-speakers --province BC
docker compose run --rm scanner refresh-coverage-stats

# 4) (Optional) push the branch to origin/main once GPU work clears.
git push origin main
```

---

## What shipped this session (committed, in `main`)

| SHA | Title | Files |
|---|---|---:|
| `83ab13f` | `feat(scanner): bc + qc historical-roster backfills` | 9 |
| `7362711` | `feat(scanner): bc hansard pre-p38 era-branching parser` | 3 |

### Commit 83ab13f — BC + QC roster

- `db/migrations/0038_unique_qc_assnat_id.sql` — promote `qc_assnat_id` partial btree → UNIQUE partial. Pre-flight required merging the Open North Éric/Eric Girard duplicate (1,234 speeches + 2,045 chunks reparented).
- `services/scanner/src/legislative/qc_former_mnas.py` (new) — alphabet-walk of `assnat.qc.ca/fr/membres/notices/index*.html` (16 letter-pages, 2,556 unique MNAs) + per-MNA bio prose-regex for first/last career years. 2,090/2,383 bios yielded a usable span (88 %).
- `services/scanner/src/legislative/qc_hansard.py` — added `resolve_qc_speakers_dated` single-CTE date-windowed update.
- `services/scanner/src/legislative/bc_member_parliaments.py` (new) — single LIMS GraphQL `allMemberParliaments` query → 750 (member, parliament) edges → `politician_terms` rows with `source='lims.leg.bc.ca:parliament-{N}'`.
- `services/scanner/src/__main__.py` + `jobs_catalog.py` + `services/api/src/routes/admin.ts` — wired three new commands: `ingest-qc-former-mnas`, `resolve-qc-speakers-dated`, `enrich-bc-member-parliaments`.
- `docs/research/quebec.md` + `docs/runbooks/handoff-2026-04-27-bc-qc-historical.md` — narrative + ledger.

QC resolution lift after dated post-pass:
- 39-1: 46.4 % → **62.0 %**  (+15.6)
- 39-2: 41.4 % → **60.9 %**  (+19.5)
- 40-1: 31.5 % → **65.1 %**  (+33.6)
- 41-1: 39.8 % → **60.9 %**  (+21.1)
- 42-1: 69.9 % → **82.6 %**  (+12.7)
- 42-2: 72.2 % → **80.6 %**  (+8.4)

### Commit 7362711 — BC pre-P38 era-branching parser

- `services/scanner/src/legislative/bc_hansard_parse.py` — extended with legacy markup branch:
  - `detect_era()` — modern if `class="speakerbegins"` present, else legacy.
  - `parse_url_meta()` filename branch for `{NN}p_{NN}s_{YYMMDD}{x}.htm`.
  - `_extract_legacy()` walker handling P29-P34 (ALL-CAPS bold + `class="noindent"` continuations) and P36-P37 (mixed-case bold + bare-`<p>` continuations) in one pass.
  - Opener regex: `[^<]{2,200}?:` (200-char budget absorbs P37's NBSP-prefix indenting).
  - Continuation regex skips section markers via `_LEGACY_SKIP_CLASS_RE` (proc_head / subj_head / toc1 / toc2 / time / page / header / footer / appendixSmall).
  - Attribution validator accepts honorifics (Hon./Mr./Mrs./Ms./Dr.) **OR** initial-last form (`J. MacPhail` / `R. Coleman`).
- `docs/research/british-columbia.md` + `docs/runbooks/handoff-2026-04-27-bc-qc-historical.md` — narrative + per-parliament ledger.

BC backfill ledger:

| P  | Era                | Speeches | Resolved % |
|----|--------------------|---------:|-----------:|
| 29 | Legacy ALL-CAPS    |   11,351 | 13.9 |
| 30 | Legacy ALL-CAPS    |   70,938 | 10.9 |
| 31 | Legacy ALL-CAPS    |   21,399 |  8.8 |
| 32 | Legacy ALL-CAPS    |   51,623 | 15.3 |
| 33 | Legacy ALL-CAPS    |   48,264 | 22.8 |
| 34 | Legacy ALL-CAPS    |   26,016 | 49.8 |
| 35 | Legacy ALL-CAPS    |   83,187 | 97.4 |
| 36 | Legacy mixed-case  |   34,023 | 98.9 |
| 37 | Legacy mixed-case  |   31,664 | 87.6 |

P29-P34 resolution is **bottlenecked by missing roster** — LIMS GraphQL `allMembers` only goes back to P35 (1992). Lifting them needs a separate roster-extension workstream (elections.bc.ca / Wikipedia / BC Archives — out of scope for this session).

---

## The actual problem — TEI fell to CPU mid-embed

Symptom: after embedding ~106K BC chunks, TEI started returning "All connection attempts failed" for ~13K consecutive batches. `docker logs sw-tei` shows:

```
WARN  text_embeddings_backend_candle: Could not find a compatible CUDA device on host: CUDA is not available
Caused by: DriverError(CUDA_ERROR_UNKNOWN, "unknown error")
WARN  text_embeddings_backend_candle: Using CPU instead
INFO  text_embeddings_backend_candle: Starting Qwen3 model on Cpu
```

Despite host `nvidia-smi` reporting the GPU healthy:

```
NVIDIA GeForce RTX 4050 Laptop GPU, 580.126.09, 5731 MiB free
```

…and only Steam Helper (PID 15663, 5 MiB) holding the GPU. The CUDA driver is in a stuck state from the host side of the docker-nvidia integration. `docker compose stop tei && docker compose rm -f tei && docker compose up -d tei` did NOT recover. This is a kernel-module-level bad state — reboot is the simplest fix.

### GPU recovery fallback (if reboot doesn't fix it)

In order of escalation:

```bash
# 1) Reload nvidia-uvm kernel module — least invasive.
sudo rmmod nvidia_uvm && sudo modprobe nvidia_uvm

# 2) Restart docker daemon — picks up fresh nvidia-container-runtime state.
sudo systemctl restart docker
docker compose up -d

# 3) Reload all nvidia kernel modules (heaviest non-reboot option).
sudo rmmod nvidia_uvm nvidia_drm nvidia_modeset nvidia
sudo modprobe nvidia
docker compose up -d
```

After any of the above, verify with:

```bash
docker compose logs tei --tail 30 | grep -iE "cuda|cpu|qwen"
# Want: "Starting Qwen3 model on Cuda", NOT "on Cpu".
```

---

## Verification ladder after embed completes

```sql
-- 1) All BC chunks embedded
SELECT count(*) FILTER (WHERE embedding IS NULL) AS unembedded
  FROM speech_chunks sc
  JOIN speeches s ON s.id=sc.speech_id
 WHERE s.source_system='hansard-bc';
-- expected: 0

-- 2) BC speech + chunk totals match
SELECT count(*) AS speeches FROM speeches WHERE source_system='hansard-bc';
-- expected: 577,013

SELECT count(*) AS chunks
  FROM speech_chunks sc JOIN speeches s ON s.id=sc.speech_id
 WHERE s.source_system='hansard-bc';
-- expected: 811,520

-- 3) Per-parliament resolution rates didn't regress
SELECT raw->'bc_hansard'->>'parliament' AS parl,
       count(*) AS speeches,
       round(100.0*count(*) FILTER (WHERE politician_id IS NOT NULL)/count(*),1) AS pct
  FROM speeches WHERE source_system='hansard-bc'
 GROUP BY 1 ORDER BY 1::int;
-- P29-P34 should sit at 9-50 %; P35-P37 at 87-99 %; P38-P43 at 85-96 %.

-- 4) Coverage stats refreshed
SELECT jurisdiction, hansard_status, speeches_count, politicians_count
  FROM jurisdiction_sources WHERE jurisdiction='BC';
```

---

## Out of scope (parked for future sessions)

- **Pre-P35 BC roster backfill** (1872-1991). Would lift P29-P34 resolution from ~10 % to ~80 %. Roster source candidates: elections.bc.ca historical MLA list, Wikipedia "List of MLAs of British Columbia by parliament", BC Archives. Different workstream from LIMS, no clean GraphQL/API.
- **BC pre-P38 bills backfill** (PDMS serves every session back to 1872, ~140 sessions). Would 4-10× current BC bills row count.
- **BC committee transcripts** (Section A / Section C HDMS files — `CommitteeA-Blues.htm`, `CommitteeC-Blues.htm`). Skipped in v1.
- **QC pre-2009 Hansard backfill**. assnat.qc.ca's ASP.NET WebForms page returns HTTP 500 for non-current sessions; Wayback CDX is the discovery fallback (already used for 39-1 → 43-1). Pre-2009 (older than session 39-1) coverage on Wayback is increasingly thin.
- **TEI throughput tuning**. Legacy-era chunks are longer than modern (~2.6-3.2K chunks/min vs ~17K), so embed times scale poorly. Could re-tune `--max-batch-tokens` or split very long speeches more aggressively in `chunk-speeches`.

---

## Working tree state at pause

Clean for this session's work — both feature commits landed. The unrelated frontend / blog / socials WIP that was in the tree at session start is still untouched and unstaged (CLAUDE.md, README, blog deletions, `MapMobileFilters.tsx`, `MobileBottomNav.tsx`, `SearchScrollFab.tsx`, `useMediaQuery.ts`, `ab_former_mlas.py` party-badge edits, `socials_*` enrichment edits). None of these are from this session.

```
$ git status --short | wc -l
~30 lines, all pre-existing WIP from prior conversations
```

When the user is ready to push the embed-completion work, the safe push is just `git push origin main` — the WIP working tree stays local.
