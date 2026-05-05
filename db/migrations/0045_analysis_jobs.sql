-- Generalize report_jobs into a multi-kind analysis-jobs substrate.
--
-- Phase 0 of the new paid-analysis surfaces. The reports-worker pipeline
-- (queue → claim → map-reduce → commit/refund) is the right shape for
-- every paid AI analysis we want to ship; today it's hard-coded to one
-- kind ("Full report — analyze everything" per politician + query). This
-- migration introduces a `kind` discriminator and a generic `inputs`
-- JSONB so each new analysis is a prompt template + an input shape, not
-- a new table or a new worker.
--
-- The existing per-politician usage continues to work unchanged: rows
-- inserted without an explicit kind default to 'full_report', and the
-- (politician_id, query) columns are preserved (just relaxed to
-- nullable). The full_report cost formula and worker handler stay
-- bit-for-bit identical.
--
-- Cost-cap discipline lives in the cost-formula registry on the API side
-- (services/api/src/lib/reports.ts:KIND_COST_FORMULA) — the database
-- enforces the kind enum, the API enforces the input cap per kind. No
-- cache_key column: every analysis re-runs and re-charges, with the
-- AnalysisConfirmModal as the user's protection against accidents.

-- New columns ─────────────────────────────────────────────────────

alter table private.report_jobs
    add column if not exists kind text not null default 'full_report',
    add column if not exists inputs jsonb not null default '{}'::jsonb;

-- Constrain the kind enum at the database boundary. Any new analysis
-- kind requires both an entry here AND a handler in the Python worker's
-- KIND_HANDLERS dispatcher; the CHECK is the failsafe that catches a
-- mismatch (e.g. API row inserted with a kind the worker doesn't know).
alter table private.report_jobs
    drop constraint if exists report_jobs_kind_check;

alter table private.report_jobs
    add constraint report_jobs_kind_check
        check (kind in (
            'full_report',
            'search_synthesis',
            'stance_map',
            'topic_pulse',
            'narrative_timeline',
            'voting_audit',
            'compare_politicians'
        ));

-- Relax full_report-shaped columns to nullable. search_synthesis et al
-- are not anchored to a single politician, and chunk_ids may live in
-- inputs.chunk_ids instead of being derived from a topic query. The
-- per-kind zod validator on POST /reports enforces which fields a given
-- kind requires.
alter table private.report_jobs
    alter column politician_id drop not null;

alter table private.report_jobs
    alter column query drop not null;

-- Index for admin / per-user filtering by kind. Most queries are
-- (user_id, kind) for "my synthesis reports" or (kind, status) for the
-- admin dashboard. The existing idx_report_jobs_user_time covers the
-- "my recent reports" case without kind; this is purely additive.
create index if not exists idx_report_jobs_user_kind_time
    on private.report_jobs(user_id, kind, created_at desc);

-- credit_ledger.kind enum stays as 'report_hold' / 'report_commit' /
-- 'report_refund'. The "report" prefix is now a generic term in this
-- codebase for any paid analysis artifact — fork would force a
-- migration on every call site of holdCredits/commitHold/releaseHold
-- for zero correctness benefit. The two-layer idempotency guard
-- (uniq_credit_ledger_kind_ref on (kind, reference_id)) continues to
-- work unchanged because reference_id remains the report_jobs.id.
