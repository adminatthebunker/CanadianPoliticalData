# Operations Guide

## First boot

```bash
sovpro init                  # creates .env + git repo + data/, backups/ dirs
$EDITOR .env                 # set DB_PASSWORD + WEBHOOK_SECRET
make geoip-download          # instructions for GeoLite2 .mmdb files
sovpro up                    # build + start
sovpro doctor                # sanity check
```

After ~30 seconds the database is ready and `scanner-cron` will:
1. seed organizations
2. ingest federal MPs, Alberta MLAs, Edmonton + Calgary councils
3. scan everything
4. refresh map views

You can watch progress with:

```bash
sovpro logs scanner-cron
```

## Common operations

| Goal | Command |
|------|---------|
| Re-scan everything | `sovpro scan full` |
| Re-scan stale only | `sovpro scan` |
| Re-ingest politicians | `sovpro ingest all` |
| Inspect DB | `sovpro db psql` |
| Backup | `sovpro db backup` |
| See current sovereignty stats | `sovpro stats` |
| Tail logs | `sovpro logs api` |
| Restart one service | `sovpro rebuild api` |

## Embedding service

The `tei` service runs HuggingFace **Text Embeddings Inference** serving **Qwen3-Embedding-0.6B** (1024-dim, fp16) on the RTX 4050 GPU. Image `ghcr.io/huggingface/text-embeddings-inference:89-1.9`. Reachable inside the compose network as `http://tei:80`.

The prior custom FastAPI + FlagEmbedding wrapper (BGE-M3 + BGE-reranker-v2-m3) was retired on 2026-04-19 after a 3-way eval (see `docs/plans/embedding-model-comparison.md`). Its code still lives at `services/embed/` for rollback; no compose service references it.

- **Model cache.** First request pulls ~1.3 GB into the `embedmodels` named volume (mounted at `/data`; TEI expects HF_HOME-style layout there). The volume was shared with the legacy BGE-M3 layout so a rollback wouldn't re-download either model.
- **GPU attachment.** Compose uses `deploy.resources.reservations.devices` with `driver: nvidia, capabilities: [gpu]`. Confirm via:
  ```bash
  docker exec sw-tei curl -s http://localhost:80/health
  docker logs sw-tei 2>&1 | head  # expect "Starting Qwen3 model on Cuda" near the top
  ```
- **Overrides** via `.env`:
  ```env
  TEI_MODEL=Qwen/Qwen3-Embedding-0.6B       # HF repo ID
  TEI_MAX_CLIENT_BATCH=64                   # max array length per HTTP call
  TEI_MAX_BATCH_TOKENS=16384                # token-budget across the batch
  TEI_MEMORY=6g                             # soft host-RAM cap (not VRAM)
  EMBED_CUDA_DEVICES=all                    # CUDA_VISIBLE_DEVICES-style
  EMBED_GPU_COUNT=all
  ```
  Any change requires `docker compose up -d tei` to recreate the container.
- **Hot-path endpoints.**
  - `POST /embed` (TEI-native) — body `{"inputs": ["..."], "normalize": true}` → bare JSON array of float arrays.
  - `POST /v1/embeddings` (OpenAI-compatible) — body `{"input": [...], "model": "..."}` → `{data: [{embedding: [...]}, ...]}`.
  - `GET /health` — minimal liveness; weights load on first request (lazy).
- **Throughput (RTX 4050 Mobile, 2026-04-18 re-embed, Qwen3-Embedding-0.6B fp16).**
  - Pure GPU: ~75 chunks/sec.
  - End-to-end through the scanner's batched-UNNEST write path: **50.9 chunks/sec**. 242 k chunks re-embedded in 1 h 19 m.
  - End-to-end is the capacity-planning number; pure-GPU ignores DB write contention.
- **Query-time instruction wrapper (critical).** Qwen3-Embedding needs queries prefixed with an instruction; documents are NOT prefixed. Without the wrapper NDCG drops from ~0.43 to ~0.22. Format:
  ```
  Instruct: Given a parliamentary search query, retrieve relevant Canadian Hansard speech excerpts
  Query: {user query}
  ```
  Indexing code writes documents unwrapped. See `docs/plans/search-features-handoff.md` for the full retrieval contract.
- **Reranking.** The BGE-reranker cross-encoder is **no longer in the critical path** — Qwen3 retrieval quality cleared the bar without it. If you re-introduce reranking, run it as a separate service; don't resurrect the FlagEmbedding wrapper just for it.
- **Scanner env.** The scanner reads `EMBED_URL` (default `http://tei:80`), `EMBED_MODEL_TAG` (default `qwen3-embedding-0.6b`, written to `speech_chunks.embedding_model`), and `EMBED_BATCH` (default 32).
- **Monitoring.** `docker stats sw-tei --no-stream` for host-side CPU/RAM; `nvidia-smi` on the host for GPU utilisation + VRAM; `docker logs sw-tei -f` for model-load progress. `docker compose stop tei` releases the card cleanly when you need it for other work.

## Admin panel

`/admin` on the public frontend surfaces a private operator console: queue any whitelisted scanner command, set cron schedules, and watch dashboard counts (speeches, chunks, pending embeds, job throughput).

- **Enable:** set `JWT_SECRET` + SMTP in `.env`, then `docker compose up -d api scanner-jobs`. Admin access is "signed-in user with `is_admin = true`" — no separate ADMIN_TOKEN anymore.
- **Promote an account:** sign in once via the magic-link flow (`/login` → email → verify), then in psql run `UPDATE users SET is_admin = true WHERE email = 'you@example.com';`. The very next admin request sees the new role (re-read per request).
- **Login:** browse to `/admin`; if not signed in, you'll be bounced to `/login?from=/admin`. Signed-in non-admins see a small "not authorized" surface rather than a redirect loop.
- **Demote / force logout:** `UPDATE users SET is_admin = false WHERE email = '…';` (instant for admin routes). To fully sign someone out, rotate `JWT_SECRET` — invalidates every session in one move.
- **Disabled state:** with `JWT_SECRET` unset, `/api/v1/auth/*` + `/api/v1/me/*` + `/api/v1/admin/*` all return **503**.

### Scheduling commands

- Use `/admin/schedules` → "New schedule". Cron is 5-field UTC (`m h dom mon dow`).
- Schedules that fire too fast + job duration > interval: the worker is single-threaded, so overlapping fires just stack in the queue. Drop the cron frequency or split the work.
- `next_run_at` updates after each fire; stale rows (worker was down) re-sync on next worker boot.
- To disable temporarily, toggle the `enabled` checkbox — no deletion needed.

### Operator-friendly commands

All catalog entries live in `services/scanner/src/jobs_catalog.py`. Out of the box, the admin panel exposes:

- Federal Hansard: `ingest-federal-hansard`, `chunk-speeches`, `embed-speech-chunks`
- NS Hansard: `ingest-ns-mlas`, `ingest-ns-hansard`, `resolve-ns-speakers`
- Provincial bills: one entry per live pipeline (AB/BC/NB/NL/NS/ON/QC + their RSS variants)
- Rosters: `ingest-mps`, `ingest-senators`, `ingest-mlas`, `ingest-councils`, `ingest-legislatures`
- Enrichment: `harvest-personal-socials`
- Maintenance: `refresh-views`, `seed-orgs`, `scan`

Adding a new command requires updates in **two** spots (see CLAUDE.md § Admin panel).

### Worker restart + stuck jobs

`sw-scanner-jobs` is a long-running container. On boot it requeues any `status='running'` row older than `JOBS_STUCK_MINUTES` (default 10 min) with an `error='recovered after worker restart'` note. That makes `docker compose restart scanner-jobs` safe even mid-job — the current run is abandoned, the DB row flips to queued, the next worker picks it up.

## Billing rail (premium reports phase 1a)

Full design + deploy sequence in `docs/plans/premium-reports.md`. Operational quick-ref below.

### Env vars

`STRIPE_SECRET_KEY` unset → feature disabled. UI hides purchase buttons; `POST /me/credits/checkout` returns 503; `POST /webhooks/stripe` returns 200-discard (NOT 5xx — Stripe would retry for 72h and burn its budget). Full list in `.env.example`:

| Var | Unset behaviour |
|---|---|
| `STRIPE_SECRET_KEY` | Checkout endpoint 503s, buy buttons hidden. |
| `STRIPE_WEBHOOK_SECRET` | Webhook signature verification fails closed. |
| `STRIPE_PRICE_ID_CREDIT_PACK_SMALL` / `_MEDIUM` / `_LARGE` | Each pack hides individually if its price id is unset. |
| `STRIPE_SUCCESS_URL` / `STRIPE_CANCEL_URL` | Default to `${PUBLIC_SITE_URL}/account/credits?purchase=success|cancel`. |
| `STRIPE_TAX_ENABLED` | Off → checkout sessions are created without `automatic_tax`. See § Stripe Tax below; do not flip without completing the dashboard activation first. |

### Initial Stripe activation walkthrough

End-to-end sequence from "no Stripe at all" to "live in production." Each phase is independently rollback-safe.

**Phase 1 — Test mode.** Burn the dust off without exposing real money.

1. Sign up at https://dashboard.stripe.com (or use an existing account in test mode).
2. Settings → Developers → API keys → copy the **test** Secret key (`sk_test_…`).
3. Products → create three one-time-payment products: Small / Medium / Large credit packs. Set CAD prices ($5 / $20 / $50). Mark them as `Tax behavior: Exclusive` (we add tax on top, not bake it in). Copy each `price_…` id.
4. Developers → Webhooks → Add endpoint → URL `https://<your-host>/api/v1/webhooks/stripe`, events `checkout.session.completed` only. Copy the test signing secret (`whsec_…`).
5. Populate `.env`:
   ```
   STRIPE_SECRET_KEY=sk_test_...
   STRIPE_WEBHOOK_SECRET=whsec_...
   STRIPE_PRICE_ID_CREDIT_PACK_SMALL=price_...
   STRIPE_PRICE_ID_CREDIT_PACK_MEDIUM=price_...
   STRIPE_PRICE_ID_CREDIT_PACK_LARGE=price_...
   ```
6. `docker compose up -d api` (frontend doesn't need a rebuild — it discovers Stripe state via `/me/credits` and `/me/credits/packs`).
7. End-to-end test: sign in at `/login` → `/account/credits` → buy a small pack with `4242 4242 4242 4242`, any future CVC + expiry. Within seconds you should see:
   - `stripe_webhook_events` row created, `processed_at` populated.
   - `credit_purchases` row with `status='completed'`.
   - `credit_ledger` row with `kind='stripe_purchase'`, `delta=50`, `state='committed'`.
   - Balance chip on the page reflects the new total after the one-shot 2-second poll.
8. Idempotency check: from the Stripe dashboard → Webhook attempts → "Resend" the `checkout.session.completed` event. The API should respond 200 with `{duplicate: true}` and the DB should not gain a second row.

**Phase 2 — Stripe Tax (optional but recommended for Canadian sellers).** See § Stripe Tax below for the full activation, then circle back here.

**Phase 3 — Live mode.** Mechanical swap once the test-mode round-trip is solid.

1. Stripe dashboard → toggle to live mode (top-right).
2. Recreate the three Products in live mode (or use the "Move to live" affordance per product). Note the new `price_…` ids — they are different from test mode.
3. Settings → Developers → API keys → copy the **live** Secret key (`sk_live_…`).
4. Developers → Webhooks → register the same `https://<your-host>/api/v1/webhooks/stripe` endpoint **a second time** in live mode. Live mode has its own webhook list, separate from test mode. Copy the live signing secret.
5. Replace every `STRIPE_*` value in `.env` with its live counterpart. (If you used Stripe Tax in phase 2, also re-enable Stripe Tax in live mode and re-classify the new live-mode Prices — registrations live in `Tax → Registrations` and apply globally.)
6. `docker compose up -d api`. Watch the logs for the "API listening" line and the absence of the Stripe-not-configured warning.
7. Place a real test purchase ($5 — easy to comp back to yourself via `/admin/users/<your-id>/grant-credits` afterwards, or just refund via the Stripe dashboard).

### Stripe Tax (Canadian GST/HST/PST)

Stripe Tax is a runtime opt-in (`STRIPE_TAX_ENABLED=true` mirrors a dashboard switch — both must be on). Code path lives in `services/api/src/lib/stripe.ts:createCheckoutSession`. Default is off so deploying the code before configuring the dashboard is safe.

**Activation checklist** (do all of these *before* flipping `STRIPE_TAX_ENABLED=true`):

1. Stripe dashboard → Settings → Tax → Activate Stripe Tax.
2. Tax → Registrations → Add. Provide your CRA business number (GST/HST), the originating address you serve from, and registration date. Add provincial PST/QST registrations separately if you hold any (Quebec, BC, Saskatchewan, Manitoba — the rest of Canada uses HST or GST + provincial admin).
3. Products → each credit-pack product → Tax behavior → assign a tax code. `txcd_10000000` "General — Services" is the safe default; if accounting decides credits map to a digital-services category, use the corresponding code instead. The tax code drives whether each province treats the sale as taxable, exempt, or zero-rated.
4. Settings → Tax → Reports → decide cadence. Monthly is conventional for GST/HST filing.
5. Test-mode dry-run: from a freshly-loaded `/account/credits`, complete a checkout with `4242 4242 4242 4242` and a Canadian billing address. Confirm in the dashboard's webhook payload that `automatic_tax.status === "complete"` and `total_details.amount_tax > 0`.

**Flipping the switch in production:**

```bash
# in /home/bunker-admin/sovpro/.env
STRIPE_TAX_ENABLED=true
```

```bash
docker compose up -d api
docker compose logs -f api    # watch for "API listening" + no warnings
```

The frontend doesn't need a rebuild — the "Prices are exclusive of tax — applicable Canadian sales tax (GST/HST/PST) will be calculated at checkout" disclosure on `/account/credits` is gated on the live `/me/credits/packs` response (`tax_enabled: true`).

**Rollback:** flip `STRIPE_TAX_ENABLED=false` (or unset) and `docker compose up -d api`. Already-completed Tax-aware sessions are preserved verbatim in `credit_purchases.raw_webhook` (`session.total_details.amount_tax` carries the breakdown). New sessions revert to the no-tax path immediately. **No DB rollback required.**

**Common failure modes:**

| Symptom | Cause | Fix |
|---|---|---|
| Every checkout returns 400 with `Stripe.errors.StripeInvalidRequestError: This account is not registered to collect tax …` | `STRIPE_TAX_ENABLED=true` but no Canadian Tax registration in the dashboard | Add the registration (step 2 above) or unset the flag. |
| Checkout succeeds but `automatic_tax.status === 'failed'` in the webhook payload | Customer's billing address resolves to a jurisdiction the registration doesn't cover (e.g. US visitor) | Stripe still completes the sale at zero tax in this case. Decide whether to refuse non-Canadian buyers (frontend gate) or accept untaxed sales (current behaviour). |
| `credit_purchases.amount_cents` looks higher than the pack price | Working as intended — `amount_cents` = `session.amount_total` (gross of tax). Pre-tax is in `raw_webhook.session.amount_subtotal`. | Add a `tax_cents` column in a future migration if accounting needs it broken out. |
| Existing customers in `credit_purchases` from before activation have no address on the Stripe Customer | Customer object created before `customer_update.address: 'auto'` was on. | Harmless — Stripe just won't have an address for those customers until their next checkout. |

### Compiling a user a credit grant (admin "comp" workflow)

Intended for journalist / partner access or support remediation. Leaves a normal ledger row with admin attribution:

1. Sign in as an admin (`users.is_admin = true`).
2. Navigate to `/admin/users` → search by email → Open the user.
3. In the "Grant credits (comp)" form enter amount (1–100,000) and a reason — the reason is user-visible in their `/account/credits` history so write it for them, not for yourself.
4. Click "Grant credits." The ledger row posts with `kind='admin_credit'`, `created_by_admin_id` = you, and the user's spendable balance updates immediately.

Audit trail: `SELECT * FROM credit_ledger WHERE kind='admin_credit' ORDER BY created_at DESC;` shows every comp with the granting admin id.

### Suspending a user

1. `/admin/users` → search → Open.
2. Dropdown "Rate-limit tier" → `suspended` → blur.
3. Takes effect on the user's next request (no logout required). They see a 403 on every signed-in endpoint until the tier is reverted.

Direct-SQL alternative if the admin UI is unavailable:
```sql
UPDATE users SET rate_limit_tier = 'suspended' WHERE email = 'abuser@example.com';
```

### Rotating the Stripe webhook signing secret

1. In Stripe dashboard → Developers → Webhooks → your endpoint → "Roll signing secret."
2. Copy the new `whsec_…` value.
3. Update `.env` → `STRIPE_WEBHOOK_SECRET=whsec_<new>`.
4. `docker compose up -d api` (api restart only; the Stripe SDK picks up the new secret at boot).
5. Stripe gives you a 24h overlap window where both old and new secrets validate — plenty of time for the restart.

### Verifying the ledger balance of a specific user

```sql
SELECT COALESCE(SUM(delta), 0) AS balance
  FROM credit_ledger
 WHERE user_id = (SELECT id FROM users WHERE email = 'you@example.com')
   AND state IN ('committed','held');
```
Held rows contribute their negative delta → balance is the *spendable* amount, not the gross grant total.

### Disaster: "the ledger is wrong"

Never `UPDATE credit_ledger SET delta = ...`. Every correction must be a **new** ledger row:

```sql
-- Refund 50 credits to a user after a failed report, outside the automatic hold-release path
INSERT INTO credit_ledger (user_id, delta, state, kind, reason, created_by_admin_id)
     VALUES ($user_id, 50, 'committed', 'admin_credit', 'Manual refund — report #xxx hung', $admin_id);
```

The ledger is append-only by discipline, not just by schema. Debug from `SELECT … ORDER BY created_at`; never mutate past rows.

### Correction-reward flow

When an admin transitions a `correction_submissions` row into `status='applied'`, a `credit_ledger` row is inserted inline with `kind='correction_reward'`, `reference_id=correction_submissions.id`, and a fire-and-forget notification email follows after the transaction commits. Key operator knobs:

- `CORRECTION_REWARD_CREDITS` (env, default 10) — payout per accepted correction. Set to 0 to disable the feature without removing the code path.
- Idempotent by the `(kind, reference_id)` partial unique index — applying the same correction twice grants and notifies exactly once.
- Anonymous corrections (`user_id IS NULL`) skip the grant silently.
- Email skipped when `users.email_bounced_at IS NOT NULL` (mirrors the alerts-worker suppression discipline from migration 0028).

**No manual re-grant path is needed.** If you re-apply an already-applied correction, the DB constraint guarantees no duplicate row. If you need to reward outside the normal flow (e.g. an exceptional find that merits more than the flat amount), use the admin-comp flow at `/admin/users/:id/grant-credits` — that's the escape hatch by design.

### Reports operations (phase 1b)

The `reports-worker` compose service is the production runner for premium reports. Default poll interval 5s. Single worker per host is fine — concurrency is handled at the job-claim level (`FOR UPDATE SKIP LOCKED`). Adding a second instance for throughput is safe.

**Tunable knobs** (all env, all picked up on `docker compose up -d --force-recreate api reports-worker`):

| Env var | Default | Effect |
|---|---|---|
| `OPENROUTER_REPORT_MODEL` | `anthropic/claude-sonnet-4.6` | Provider model id. The api and worker MUST agree. |
| `OPENROUTER_REPORT_TIMEOUT_MS` | `120000` | Per map / reduce call. Bump if the model is slow on large inputs. |
| `REPORT_BASE_COST_CREDITS` | `5` | Reduce-step flat cost. |
| `REPORT_PER_CHUNK_BUCKET_COST` | `1` | Per map-bucket cost. |
| `REPORT_BUCKET_SIZE` | `10` | Chunks per map call. Larger buckets = fewer calls but more model output to merge. |
| `REPORT_MAX_CHUNKS` | `300` | Hard cap. Users see "(capped)" in the cost dialog. |
| `REPORTS_RATE_LIMIT_DEFAULT_PER_DAY` | `5` | Daily report cap for `default` tier. |
| `REPORTS_RATE_LIMIT_EXTENDED_PER_DAY` | `20` | Daily report cap for `extended` tier. |
| `REPORTS_POLL_INTERVAL` | `5` | Worker poll cadence. |
| `REPORTS_STALE_CLAIM_MINUTES` | `15` | A `running` job past this age is re-queued (worker crash recovery). |

**Inspecting a stuck job:**
```sql
-- All non-terminal jobs, with claim age:
SELECT id, status, user_id, politician_id, query, claimed_at,
       now() - claimed_at AS age,
       error
  FROM report_jobs
 WHERE status IN ('queued','running')
 ORDER BY created_at;
```

A job stuck in `running` past `REPORTS_STALE_CLAIM_MINUTES` will be auto-re-queued on the next worker tick (the worker runs a sweep before claiming). If you want to force a re-queue immediately:

```sql
UPDATE report_jobs SET status = 'queued', claimed_at = NULL, started_at = NULL
 WHERE id = '<job_id>' AND status = 'running';
```

**Refunding a report** is admin-UI driven at `/admin/reports`. Two modes happen automatically based on the current ledger state:

1. *Hold still `held`* (worker hasn't committed yet — job is queued, running, or failed pre-commit): the hold flips `held → refunded`. Balance immediately reflects the refund.
2. *Hold already `committed`* (job succeeded then bug report came in): a fresh `admin_credit` row is inserted with the same delta, since you can't un-flip a state-flipped row.

If you need to refund manually (admin UI down, etc.) the SQL is in the file `services/api/src/routes/admin.ts` `POST /admin/reports/:id/refund` handler — read it before running anything.

**Rolling the model id** (e.g. `anthropic/claude-sonnet-4.6` → newer snapshot):
```bash
# .env: OPENROUTER_REPORT_MODEL=anthropic/claude-...-newer
docker compose up -d --force-recreate api reports-worker
```
No migration needed. Cost-formula knobs persist across model swaps; revisit them if the new model's pricing is materially different.

**Bug-report queue:** `/admin/bug-reports` lists user-flagged issues. Mark them `reviewing` while you investigate, `resolved` when fixed (no auto-action), `dismissed` if not actionable. There is no automatic credit refund on bug submission — admins decide via the refund button on the parent report.

## Scheduled jobs

`scanner-cron` runs an hourly loop:
- Quick scan every hour for sites stale > 6h
- Full sweep daily at 06:00 UTC
- Re-ingest from Open North weekly Sunday 02:00 UTC

## Backups

Two paths exist. Pick by what the backup is for.

### Path A — quick gzipped archive (legacy, portable)

For ad-hoc snapshots, sharing a DB state with someone else, or before a risky migration where you want a single file you can email yourself:

```bash
sovpro db backup                    # writes backups/<timestamp>.sql.gz
sovpro db restore backups/foo.sql.gz
```

Trade-off: plain SQL gzipped is **single-threaded on restore**. On the live 124 GB corpus the restore path takes hours of single-CPU work. Fine for small DBs and code snapshots; not the right tool for "the database is gone, get it back fast."

### Path B — fast parallel snapshot (use for the live DB)

`pg_dump` directory format with parallel workers and no compression. Output: one file per table, restorable via `pg_restore -j N` for parallel data load + index build. This is what you want for a full DB backup you might actually need to restore in a hurry.

**Storage layout:**

| Path | Filesystem | Role |
|---|---|---|
| `/media/bunker-admin/Internal/canadian-political-data-backups/` | ext4 on internal NVMe | Primary backup. Always dump here first. |
| `/media/bunker-admin/<usb-label>/` | LUKS2 + ext4 on USB | Secondary mirror. Requires unlock + mount each time. |

#### Automation (cron)

The runbook below is wrapped by `scripts/backup-database.sh` and runs daily from the `bunker-admin` user crontab:

```
30 4 * * * /home/bunker-admin/sovpro/scripts/backup-database.sh >/dev/null 2>&1
```

The script flock-guards itself, writes a per-run log next to the dump (`sovereignwatch-<TS>.log`), validates the new dump with `pg_restore --list` before touching any older one, then **demotes prior uncompressed dumps to `.tar.zst` (zstd -19)** and prunes anything beyond `BACKUP_RETENTION` (default 7) total units. Latest dump always stays uncompressed and restore-ready; older history is compressed to fit the internal drive.

Override knobs via env vars: `BACKUP_DEST`, `BACKUP_RETENTION`, `BACKUP_COMPRESS_LEVEL`, `BACKUP_PARALLEL_JOBS`, `SOVPRO_REPO`. To restore a compacted backup, `tar -I zstd -xf sovereignwatch-<TS>.tar.zst` first, then follow the directory-format restore steps below.

#### One-shot procedure

```bash
TS=$(date -u +%Y%m%dT%H%M%SZ)
DEST="/media/bunker-admin/Internal/canadian-political-data-backups"

# 1. Manifest — audit trail (git SHA, row counts, applied migrations)
{
  echo "# sovereignwatch backup manifest"
  echo "timestamp_utc: $TS"
  echo "git_sha: $(git -C /home/bunker-admin/sovpro rev-parse HEAD)"
  echo
  echo "row_counts:"
  docker exec sw-db psql -U sw -d sovereignwatch -tAc \
    "SELECT 'speeches', count(*) FROM speeches UNION ALL
     SELECT 'speech_chunks', count(*) FROM speech_chunks UNION ALL
     SELECT 'politicians', count(*) FROM politicians UNION ALL
     SELECT 'bills', count(*) FROM bills"
  echo
  echo "applied_migrations:"
  ls /home/bunker-admin/sovpro/db/migrations/ | sort
} > "$DEST/sovereignwatch-$TS.manifest.txt"

# 2. Globals — sw role + cluster-level config; needed to restore to a fresh server
docker exec sw-db pg_dumpall -U sw --globals-only \
  > "$DEST/sovereignwatch-$TS.globals.sql"

# 3. Main dump — parallel directory format, no compression, via a throwaway sidecar
docker run --rm \
  --name "sw-backup-$TS" \
  --network sovpro_sw \
  -v "$DEST:/backup" \
  -e PGPASSWORD="$(grep '^DB_PASSWORD=' /home/bunker-admin/sovpro/.env | cut -d= -f2-)" \
  postgres:16 \
  pg_dump -h db -U sw -d sovereignwatch \
          -Fd -j 8 -Z 0 \
          -f "/backup/sovereignwatch-$TS.d" \
          --verbose

# 4. Fix ownership — the sidecar runs as root inside the container
docker run --rm -v "$DEST:/backup" busybox \
  chown -R 1000:1000 "/backup/sovereignwatch-$TS.d"

# 5. Verify — TOC parses, segment count is reasonable, exit 0
docker run --rm -v "$DEST:/backup" postgres:16 \
  pg_restore --list "/backup/sovereignwatch-$TS.d" | head
ls "$DEST/sovereignwatch-$TS.d/" | wc -l
du -sh "$DEST/sovereignwatch-$TS.d"
```

Expected wall-time on the live DB: **15–20 min** on internal NVMe. Output size ≈ 216 GB even though the live DB is 124 GB — `pg_dump` serializes vectors and JSON as text, which expands. The HNSW index on `speech_chunks.embedding` is *not* in the dump (it's rebuilt at restore time).

The sidecar pattern (`docker run --rm postgres:16 …`) is deliberate: it keeps the running `db` container untouched, mounts the backup path the way it needs to be mounted, and leaves no state behind. Don't add a bind-mount to the `db` service in `docker-compose.yml` for this — that requires a restart and persists across reboots.

#### Mirror to LUKS USB

After the internal dump succeeds, mirror to the USB. The drive is LUKS2-encrypted; unlock it first (GNOME Files → click drive → enter passphrase, or CLI `cryptsetup luksOpen`). Then:

```bash
USB="/media/bunker-admin/<usb-label>"   # set this after the LUKS volume mounts

rsync -a --info=progress2 \
  "$DEST/sovereignwatch-$TS.d" \
  "$DEST/sovereignwatch-$TS.globals.sql" \
  "$DEST/sovereignwatch-$TS.manifest.txt" \
  "$USB/"

# Lock when done (GUI eject button or CLI):
sudo umount "$USB"
sudo cryptsetup luksClose <usb-mapper-name>
```

Use `rsync` rather than `cp -r` — it shows live progress (the USB transfer is often longer than the dump itself) and resumes mid-stream if you cancel. The two locations now hold byte-identical copies of the same snapshot.

#### Restore from a directory-format snapshot

```bash
# 1. Recreate the sw role (needed only on a fresh server)
psql -U postgres < sovereignwatch-<TS>.globals.sql

# 2. Empty target DB
createdb -U postgres -O sw sovereignwatch

# 3. Parallel restore (data + indexes in parallel)
pg_restore -U postgres -d sovereignwatch -j 4 --verbose \
  sovereignwatch-<TS>.d
```

The HNSW vector index on `speech_chunks.embedding` rebuilds at restore time. On the 3.4 M-row corpus expect **30–60 min for the index step alone**, regardless of how fast the data load was. That's the floor on full-restore wall-time.

#### What not to do

- **Don't dump to FAT32.** The 4 GB per-file ceiling kills mid-dump on `speeches` / `speech_chunks`. Run `lsblk -f /dev/<x>` to confirm the filesystem type of any new target drive *before* pointing a backup at it; `df -h` does not show FS type by default and is not a substitute.
- **Don't store unencrypted backups on removable media.** Backup files contain everything: user emails, magic-link redemption history, Stripe customer IDs, full speech text. The LUKS layer on the USB is non-optional.
- **Don't re-run pg_dump for the second (USB) copy.** A second dump produces a slightly different snapshot (txn boundary moved). Mirroring with `rsync` gives you two copies of the *same* dump, which is what "redundant backup" actually means.
- **Don't commit `backups/` or the new internal backup directory.** They're not in the public-facing git tree. The legacy `backups/` is host-local; the internal target lives outside the repo entirely.

For production, copy the internal backup directory to off-host storage (S3, B2, etc.) on a cron — same `rsync` invocation as the USB mirror, different destination.

## Deploying

### Local/single host
```bash
sovpro up
```

### Remote single host
```bash
sovpro deploy remote user@host
```
This rsyncs the repo (excluding .env, .git, data/*.mmdb) and runs `docker compose up -d --build` on the remote. You must scp `.env` and the GeoLite2 files to the remote yourself once.

### Behind Pangolin / Cloudflare Tunnel
Point your tunnel at `nginx:80`. nginx is the only public surface — the API, DB, and Kuma stay on the internal network.

## Disaster recovery

If a release breaks the schema:

```bash
sovpro down
sovpro db restore backups/<last-good>.sql.gz
git checkout <last-good-tag>
sovpro up
```

If the DB volume itself is corrupted:

```bash
sovpro db reset             # wipes pgdata (irreversible)
sovpro up
sovpro db restore backups/<last-good>.sql.gz
```
