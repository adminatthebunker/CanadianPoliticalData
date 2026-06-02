---
date: 2026-05-05
authors:
  - adminatthebunker
slug: seven-ways-to-analyze
description: >-
  Until last week there was one paid AI surface on Canadian Political Data —
  the full report. Now there are seven. Here's why generalising the substrate
  was the right call, what each new analysis does, and why the credit ledger
  didn't have to change.
tags:
  - reports
  - ai
  - launch
draft: false
---

# Seven ways to analyze: turning one paid surface into a substrate

The first paid AI thing on Canadian Political Data was the **Full Report**.
You'd land on a politician's page, type a topic, click *Generate*, watch a
hold drop on your credit balance, and fifteen minutes later get back a
multi-section essay with sourced citations to every quote the model used.
It worked. People used it. But it answered exactly one question — *what
has this person said about this topic, end to end?* — and that left a lot
of other shapes of question on the floor.

This week I shipped six more.

<!-- more -->

The new kinds are **search_synthesis**, **stance_map**, **topic_pulse**,
**narrative_timeline**, **voting_audit**, and **compare_politicians**.
Each is a different *shape* of LLM output — a paragraph, a grouped table,
a temporal arc, a side-by-side — pointed at a different *shape* of input
— a search result page, a cluster from the [Semantic
Explorer](semantic-explorer-how-it-works.md), a politician's voting
record. The credit ledger didn't change. The worker pipeline didn't
change. The hold/commit/release flow didn't change. What changed was
exactly one column: a `kind` discriminator on `report_jobs`, plus a
JSONB `inputs` blob.

This post is the why and the how.

## What the seven kinds do

The full menu, in plain English:

| Kind                  | Question it answers                                                       |
|-----------------------|---------------------------------------------------------------------------|
| `full_report`         | What has this politician said about this topic, end to end?               |
| `search_synthesis`    | What's the gist of these search results?                                  |
| `stance_map`          | Who's for, who's against, who's conditional — and their best quote each? |
| `topic_pulse`         | What's the current state of debate in this cluster?                       |
| `narrative_timeline`  | How has the framing of this topic shifted over time?                      |
| `voting_audit`        | Where does this politician's voice contradict their vote?                 |
| `compare_politicians` | Side-by-side: politician A vs B on this topic.                            |

Every one of them returns Markdown with citations back to the exact
Hansard speech chunks the model used. The citations are how you tell an
analysis apart from a hallucination — every claim is one click away from
the speech it came from, with the speaker, date, and Parliament intact.
That property is non-negotiable; it's why the analyses are worth
charging for.

![Hansard search results with the Analyze drop-down open, showing the six new analysis kinds](images/analyze-launch/01-analyze-menu.png)

*The Analyze drop-down on a Hansard search results page. Same place the
Full Report button used to live, plus six new neighbours.*

## Why one substrate instead of seven workers

The naive way to build six more LLM features is to build six more
features. Six new tables. Six new workers. Six new cost endpoints. Six
sets of confirmation modals. Six places to forget to add idempotency.

I'd just spent a couple of months on the original report pipeline —
tuning the map-reduce, the bucket size, the prompt cache discipline,
the hold/commit/release ledger, the Stripe-webhook two-layer
idempotency — and the thing I noticed when I stepped back was that
**none of that was actually about reports**. It was about *paid
LLM-output artifacts*, generically. Hold credits → claim a job → run a
prompt → write the result → commit the hold (or refund it on failure).
The shape was right; only the prompt was specific.

So the migration is small. From `0045_analysis_jobs.sql`:

```sql
alter table private.report_jobs
    add column if not exists kind text not null default 'full_report',
    add column if not exists inputs jsonb not null default '{}'::jsonb;

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
```

That's the whole schema change. Two columns and a CHECK. Existing rows
default to `'full_report'` so the old code paths keep working bit-for-bit
identical, and the per-kind input shape lives in `inputs.*` JSONB —
chunk IDs, topic, the second-politician slug for compare, whatever the
specific kind needs.

The CHECK exists for a reason: every kind in the database enum *must*
also have a handler in the Python worker's `KIND_HANDLERS` dispatcher
and a cost-formula entry in the API's registry. The constraint is the
failsafe — if a future me adds a kind to the API but forgets the
worker, the database refuses the row at insert time and the user sees
a clean 400 instead of an orphaned job.

## What didn't change

The headline of the rewrite is what I *didn't* have to touch.

**The credit ledger.** The ledger only knows about three event kinds:
`report_hold`, `report_commit`, `report_refund`. I deliberately kept
the "report" prefix even though it now means "any paid analysis,"
because forking those into seven new ledger kinds would force a
migration on every call site of `holdCredits` / `commitHold` /
`releaseHold` for zero correctness benefit. The two-layer idempotency
guard — `uniq_credit_ledger_kind_ref` on `(kind, reference_id)` —
continues to work unchanged because `reference_id` is still
`report_jobs.id`. Stripe webhook retries can't double-charge. Worker
crashes can't double-refund.

**The worker.** `services/scanner/src/reports_worker.py` got a new
`KIND_HANDLERS` dispatch dict at the top, but the queue → claim →
map-reduce → commit/refund choreography is the same one that's been
running reports since phase 1. Each handler is a prompt template plus
an input-shape contract; the rest is shared.

**The confirm modal.** The original `FullReportConfirmModal` was
rewritten as the kind-agnostic `AnalysisConfirmModal` and the old
component became a six-line shim that hard-codes `kind="full_report"`
for legacy call sites. The cost table — *Quotes analysed / Cost /
Balance / After* — is identical across kinds. Only three pieces of
copy vary: the heading, the body intro, and the confirm button label.
That copy lives in a single `COPY_BY_KIND` map, one entry per kind,
and it's the only file you need to touch to add a seventh.

![Cost-confirmation modal showing 247 quotes analysed, 12 credits, balance after](images/analyze-launch/02-confirm-modal.png)

*One modal, seven kinds. The cost table is the same shape every time;
only the heading and intro line change per kind.*

## What did change: the cost shape

The interesting part of generalising was the cost formula. The full
report's formula was:

```
cost = base + ceil(min(chunks, cap) / bucketSize) * perBucket
```

Plain English: a flat fee, plus a per-bucket charge for every bucket
of input chunks the model has to read, capped so a runaway query
doesn't run a runaway bill. The same shape works for every other kind
— but the *knobs* don't.

A `search_synthesis` reads maybe 40 chunks (the top page of search
results) and writes one paragraph; it's cheap. A `narrative_timeline`
might span 1,500 chunks across two decades and writes a multi-era
arc; it's expensive. A `voting_audit` is in the middle but it does an
extra pass against `vote_positions`, so its cap is set lower because
the per-chunk reasoning is heavier.

Rather than fork the formula, I kept the *shape* and parameterised the
knobs:

```ts
function knobsFor(kind: AnalysisKind): {
  base: number;
  bucketSize: number;
  perBucket: number;
  cap: number;
} { ... }
```

`full_report`'s knobs still come from environment variables — they
were operator-tunable from day one and I didn't want to break that
contract. The six new kinds are hard-coded for now; if any of them
ever needs operator-level tuning, the lift to env-vars is mechanical.
Until then, "edit this file and redeploy" is fine.

The other thing I want to be honest about: there's no cache. Every
analysis re-runs and re-charges from scratch. I prototyped a
`cache_key` column that would short-circuit on identical (kind, inputs)
hashes, looked at it for a week, and pulled it back out. The reasoning:
the user's protection against accidents is the cost-confirmation
modal, not a behind-the-scenes cache. Caching introduced a class of
"why is the output different from last time?" questions that I didn't
want to own (the model changed, the corpus grew, the prompt was
tweaked — *something* always differs over weeks), and the cost
savings were modest because the same query at slightly different
times against a slightly larger corpus is *not* the same job.

## How the kinds dispatch in the UI

The CTA shell is a single `AnalysisButton` component that takes a
`kind` prop and a `inputs` blob. Adding a new analysis to a new page
is a one-line addition wherever you'd put a button:

```tsx
<AnalysisButton
  kind="stance_map"
  inputs={{ chunk_ids: results.map(r => r.id) }}
  label="Map stances"
  meta={reportsMeta}
  guard={() => results.length === 0 ? "Run a search first" : null}
/>
```

The button handles its own pre-flight gate (signed in? premium analyses
enabled on this server? caller's `guard` happy?), opens the
`AnalysisConfirmModal` with a server-side cost estimate, and on
confirmation POSTs to `/reports` with the right body shape. The
server's zod discriminated union is the boundary that rejects malformed
inputs — I trust the wire format, not the React caller.

![Hansard politician page with the Voting Audit Analyze button highlighted](images/analyze-launch/03-voting-audit-cta.png)

*Voting audit lives on the politician page; stance map and search
synthesis live on the search results page; topic pulse lives in the
[Semantic Explorer](semantic-explorer-how-it-works.md) cluster drawer.
Each kind is a one-line `<AnalysisButton kind="…" />` at the call
site.*

## The two pieces of plumbing I shipped alongside

Two things landed in the same commit that aren't *Analyze* per se but
are load-bearing for the rest of the project to keep working:

**A real `private` schema.** The political dataset (politicians,
speeches, bills, votes, projections) lives in the `public` schema.
User accounts, payments, sessions, saved searches, corrections, and
*now report jobs* live in `private`. The redistributable public dump
is produced by `pg_dump --schema=public` and by construction it
cannot pull in anything from `private`. I'd been doing this with
table-name conventions and a dump-time guardrail; making it a real
schema split means the boundary is enforced by Postgres, not by
discipline. The `bills.meeting_id` cross-schema FK to municipal
meetings is the only cross-boundary edge in the system, and it
points the safe direction (public → public).

**A pricing page.** The blog has been quietly hand-waving "premium
analyses cost credits" for two months. The new
[/about/pricing](https://docs.canadianpoliticaldata.org/about/pricing/)
page lays out the credit packs, the per-analysis cost formula, and
the free quota that signed-in users get. Honestly, this should have
shipped at the same time as the original full report. Better late.

![Pricing page showing credit packs and per-analysis costs](images/analyze-launch/04-pricing.png)

*The new public pricing page. The cost rows match the live formulas
in `services/api/src/lib/reports.ts:knobsFor` — if a knob changes,
this page updates with it.*

## What's next

A few obvious follow-ups, in rough priority order:

- **Compare more than two politicians.** `compare_politicians` is
  fixed at two by the input schema. The map-reduce can already
  handle N; it's the prompt that has to be rewritten for N-way
  comparison without becoming an unreadable wall.
- **Stance maps over a search result rather than a cluster.**
  Currently `stance_map` takes chunk IDs from the cluster drawer;
  letting it run on arbitrary search results is one zod schema
  change away.
- **Voting audit for committees.** Voting audit currently pulls
  floor votes only because committee transcripts aren't ingested
  yet; the moment that pipeline lands, the audit gets sharper for
  free.
- **Saved analyses.** Right now an analysis is one-shot: you
  generate it, you read it, it sits in your reports list. Pinning
  the best ones to a public profile (with the citations intact) is
  the path to letting researchers cite our outputs in their own
  work.

If you're a paying user, the new kinds are already on your reports
list. If you're not, sign in (it's free, magic-link only, no
passwords) and the free quota gives you enough credits to try
`search_synthesis` on a real query before deciding whether the
premium kinds are worth the price.

The whole thing was about three days of work end-to-end. That's the
payoff for keeping the original pipeline boring: when the second,
third, and seventh thing want to ride the same rails, they can.
