# Premium reports — phase 1c follow-ups

Companion to `docs/plans/premium-reports.md`. That doc covers the billing rail (phase 1a) and the report generator (phase 1b) which are both shipped. This doc tracks the **post-launch UX/feature work** that surfaced once the report viewer was being used in earnest, around 2026-04-24.

The premium report viewer (`/reports/:id`) has the basics — generation, viewing, download-as-PDF, ledger/refund flow — but to actually be useful for journalism / research workflows, several gaps remain. The features below are the ranked next-up list. Each is small enough to ship as one PR; together they make the report a first-class artifact (shareable, citable, comparable, refreshable) rather than a one-shot personal blob.

Status legend: `planned` · `in-progress` · `shipped` · `deferred`

---

## 1. Public-share toggle + citation block (paired)

**Status:** shipped (2026-04-24, migration 0036)

**Why it earns its keep.** Reports are currently owner-only — even with a copy of the URL, an unauthenticated visitor sees the "Sign in to view this report" gate. That kills the primary external use case: a journalist writing an article wants to *link* to a report as a primary source. The pair (public-share unlock + citation block to make the citation copy-paste trivial) is what turns the report from "personal export" into "publishable artifact."

**Scope sketch.**
- DB: `report_jobs.is_public boolean DEFAULT false`. Optional `share_slug` if we want short URLs later, but the existing UUID id is fine for v1.
- API:
  - `PATCH /me/reports/:id/visibility` — owner-only, flips `is_public`. CSRF-protected.
  - New `GET /public/reports/:id` — no auth required; returns the report **only if `is_public = true`**, otherwise 404 (id-enumeration discipline).
  - The existing `GET /me/reports/:id` continues to serve the owner's view (always allowed regardless of public state).
- Frontend:
  - In the viewer header, owner sees a `Public` toggle switch beside the Download button. Visitor sees only the report.
  - When public: viewer fetches via the `/public/...` route if the user isn't signed in or doesn't own the report; falls back to `/me/...` for owners. (Simpler: try `/public` first, fall back if 404, since both return the same shape.)
  - Citation block in the report footer: auto-generated APA-style string + "Copy citation" + "Copy link" buttons.

**Open product questions.**
- New reports default to **private** (recommended — least-surprise, matches current behaviour).
- Public reports **do not** show the requesting user's identity (recommended — protects the operator's privacy when they share).
- Public reports **are** indexable by search engines (recommended — the point is reach; if the user toggles public they're consenting to discoverability).
- Once-public-can-flip-private: yes (recommended, but cached crawls obviously persist).

**Critical files (planned).**
- `db/migrations/0036_report_jobs_is_public.sql`
- `services/api/src/routes/reports.ts` (add visibility PATCH + public GET)
- `services/frontend/src/pages/ReportViewerPage.tsx` (toggle + citation block + auth-flexible fetch)
- `services/frontend/src/styles/reports.css` (toggle + citation styling)
- `services/api/src/lib/reports.ts` (no change; sanitisation already runs at persist time, public viewer renders the same html)

---

## 2. Compare two politicians on the same query

**Status:** planned

**Why.** "Trudeau vs. Poilievre on housing" is a use case people manually do today by opening two reports side-by-side. The compare-frame is the natural escalation from the single-politician report.

**Scope sketch (real-comparative version).**
- New report-job kind: `compare` with two `politician_id` fields. Reuse most of the `report_jobs` schema; add `politician_id_b uuid` nullable and a `kind text DEFAULT 'single'` discriminator.
- Cost: roughly 2× a single report (two map-passes, one combined reduce).
- New prompt template `SYSTEM_PROMPT_REDUCE_COMPARE` that takes two analyst-output arrays and produces a side-by-side or interleaved synthesis. Must be added to **both** the Python worker and the TS mirror (existing `KEEP IN SYNC` convention).
- Frontend: new comparison-aware viewer that lays out two columns on wide screens, stacked on mobile.

**Open product questions.**
- True comparative LLM pass vs. cheap "render two existing reports side-by-side"? The cheap version is a frontend-only change but doesn't actually *compare* anything — it just shows two reports in one viewport. Real comparative is much more useful but ~2× cost and a third prompt template.
- Should this allow comparing the **same** politician across two **time periods**? Probably yes as a v2 — same comparative reduce prompt, different chunk-selection filter.

**Notes.** This is the biggest feature on the list. Don't underestimate prompt engineering effort — comparative synthesis is harder than per-politician.

---

## 3. Re-run a report on new evidence

**Status:** planned

**Why.** Hansard ingests daily (federal + 8 provinces live as of 2026-04-24). A 6-month-old report gets staler every week. Letting users re-run an existing `(politician, query)` pair against today's corpus and see what's new is genuinely unique to this product.

**Scope sketch.**
- DB: add `parent_report_id uuid REFERENCES report_jobs(id)` to track lineage. Same row ledger discipline (full new hold + commit/refund cycle — re-runs are not free).
- API: `POST /me/reports/:id/rerun` — clones the row's politician+query, queues a fresh job, returns the new job id.
- Frontend:
  - "Re-run" button in the viewer (only on owner view, only for `succeeded` reports older than ~24h).
  - In the list view, group reports by `(politician_id, query)` and show the **latest** as primary with a "3 versions" badge that expands to show the lineage.
  - Optional v2: a small diff badge ("3 new themes since last run") computed by comparing theme labels — cheap, useful.

**Open product questions.**
- Does re-running consume the same number of credits as the original? Probably yes (cost scales with chunk count, which has likely grown).
- Show users a "your report may be stale" nudge if `created_at` is more than N days old? Could be a quick win on its own.

---

## 4. One-click "report this search" from /search

**Status:** shipped 2026-05-05 — broader scope than originally planned.

**What actually shipped (vs the original plan).** The original plan was a frontend-only button that pre-filled the existing `FullReportConfirmModal` for a single-politician + query case. What landed instead is a generic **analysis-jobs substrate** — `report_jobs` is now `kind`-discriminated (migration 0045), with two new search-result-set kinds (`search_synthesis` + `stance_map`) that don't require a single-politician anchor. The "report this search" affordance is a CTA row on `/search` that works regardless of how many politicians are in the result set, with a user-controllable "analyse top N" picker (25/50/100/200/500/Other…) that drives both the dashboard tile aggregations and the analysis input.

**Why broader.** The original frame was an ergonomics fix (3 clicks → 1) for the existing single-politician flow. As we got into design, the more-interesting affordance was *analysing the result set itself* — what does the corpus collectively say about this query? — rather than "what does politician X say." That demanded a new kind, which demanded the kind discriminator, which then meant adding `stance_map` (a different kind on the same substrate) was nearly free. The substrate-first approach also unblocks the deferred items: `compare_politicians` (#2) is now a prompt + handler away.

**Scope sketch (what shipped).**
- DB: migration 0045 adds `kind` (CHECK enumerating `full_report | search_synthesis | stance_map | topic_pulse | narrative_timeline | voting_audit | compare_politicians`) + `inputs` JSONB + relaxes `politician_id`/`query` to nullable. Index `idx_report_jobs_user_kind_time` for per-user-per-kind list views.
- API: `POST /reports/{,/estimate}` accepts `{kind, ...inputs}` via zod discriminated union. `KIND_COST_FORMULA` registry in `services/api/src/lib/reports.ts:knobsFor`. `/facets` extended with `chunk_ids` field + `?limit=` param so the dashboard tiles + the analysis CTA share one fetch.
- Worker: `KIND_HANDLERS` dispatcher in `reports_worker.py` with shared `run_map_reduce_pipeline` skeleton; `handle_full_report` lifted unchanged; `handle_search_synthesis` and `handle_stance_map` share `_handle_chunk_driven_kind`. Concurrency 2 → 4 to keep K=500 round-trip under ~3min. Aggregations computed server-side from the chunks list and passed to the reduce prompt; reduce prompts emit a `<table class="report-stats">` of dashboard-shape stats at the top of the HTML.
- Frontend: generic `AnalysisButton` + `AnalysisConfirmModal` + `useAnalysisSubmit`. `AIFullReportButton`, `FullReportConfirmModal`, `useFullReportSubmit` slimmed to thin shims. `<SearchSetAnalysisRow>` on `HansardSearchPage` renders both CTAs on the Analysis tab + Timeline view. "Analyse top N" picker with "Other…" custom-N modal (slider + number input + live cost preview, persisted to localStorage). Kind chips on `/me/reports` list; viewer tolerates null politician with kind-aware fallback titles.
- Cap: 500 (was 200). Cost formula: `search_synthesis` 5+⌈K/10⌉, `stance_map` 10+⌈K/10⌉. Validated end-to-end at K=500 (217s wall time, 169K input + 39K output tokens, ~$1.10 model cost vs 55-credit charge).

**Plan + design history:** `/home/bunker-admin/.claude/plans/slick-help-me-now-merry-stonebraker.md` is the as-built record (decisions locked in, pricing math, model-context ceiling analysis).

---

## 5. Citation block — *folded into Feature 1.*

The citation block is small enough that splitting it from public-share would be ceremony. They ship together as one PR.

---

## 6. Per-section "flag this section" inline feedback

**Status:** planned

**Why.** The current "Report a bug" button at the footer is global — the user has to describe *which* section is bad in free text. Per-section flagging would catch hallucination patterns faster (and lays the groundwork for per-section regenerate later, if the corrections-rewards flow makes that worth doing).

**Scope sketch.**
- DB: extend `report_bug_reports` (already exists per CLAUDE.md migration 0035) with an optional `section_anchor text` column (e.g., `"theme-quebec-sovereignty"`).
- Backend HTML rewrite: when the worker rewrites `CHUNK:<id>` href tokens, it could also stamp every `<h2>` with a stable `id` attribute derived from a slug of the heading text. (Note: needs an addition to the `bleach` allowlist for the `id` attribute on `h2`/`h3` — small surface, controlled at persist time so safe.)
- Frontend: a small flag icon next to each `<h2>` that opens an inline mini-form (reusing the existing bug-report endpoint with the `section_anchor` payload).
- Admin UI gains a new column in the bug-reports table showing the offending section.

**Notes.** The HTML-id stamping is the trickiest bit — needs to happen at persist time (in the worker), not at render time, otherwise the flag links don't survive across page loads.

---

## Cross-cutting open questions

1. **Public-share quota / abuse.** If reports become publicly indexable, do we cap how many a single user can flip public per day? Probably not in v1 — the `users.rate_limit_tier` column already exists and a `suspended` user can be cut off entirely.
2. **Versioning the prompt templates.** Once we add `SYSTEM_PROMPT_REDUCE_COMPARE` (Feature 2), we'll have **three** prompt templates duplicated across `services/scanner/src/reports_worker.py` and `services/api/src/lib/reports.ts`. Drift risk is real. Single-sourcing via a JSON template file is the right move at that point — punt until Feature 2 actually starts.
3. **Storage growth.** Re-runs (Feature 3) create new `report_jobs` rows with full HTML. At ~10 KB per report this is fine, but if a power user re-runs the same query 100 times we should consider truncating non-latest html. Probably not a v1 concern.

---

## Sequencing recommendation

| Order | Feature | Why this slot |
|---|---|---|
| 1 | Public-share + citation | Highest external-value unlock; small surface; sets up "report as artifact" framing |
| 2 | "Report this search" button | Quick win; removes friction at the conversion moment |
| 3 | Re-run on new evidence | Unique to this product; pairs naturally with corpus growth story |
| 4 | Per-section feedback | Quality lever; sets up per-section regenerate down the line |
| 5 | Compare two politicians | Sexier but biggest build; do it once the others are stable |
