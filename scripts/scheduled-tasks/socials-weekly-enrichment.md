# Weekly socials enrichment — Claude Code Desktop scheduled task

This file is the canonical, version-controlled source of truth for the
**socials-weekly-enrichment** Desktop scheduled task. The Desktop app keeps
its operational copy at `~/.claude/scheduled-tasks/socials-weekly-enrichment/SKILL.md`;
when you edit this file in the repo, paste the body into the Desktop form
(or sync the on-disk file) so the next run picks up the change.

## Wiring it into Claude Code Desktop (one-time setup)

1. Open **Claude Code Desktop** → **Routines** (sidebar).
2. Click **New routine** → **Local**.
3. Fill the form:
   - **Name**: `socials-weekly-enrichment`
   - **Description**: `Weekly web-research enrichment of top-25 missing-handle politicians.`
   - **Folder**: `/home/bunker-admin/sovpro` (must be a trusted folder)
   - **Schedule**: Weekly · Sunday · 03:07 (off-minute to avoid jitter clumping with other fleet tasks)
   - **Permission mode**: `acceptEdits` (or whatever feels right; first run is "Run now" to approve tools)
   - **Worktree**: off (we want it to read the real DB and write to the real `~/sovpro`)
   - **Instructions**: paste the body of this file (everything below the `---` divider)
4. Click **Save**.
5. Click **Run now** on the task's detail page to trigger the first run interactively. Approve each tool (`Bash`, `WebSearch`, `WebFetch`, `Edit`) as "always allow" so future autonomous runs don't stall on permission prompts.

## What this task does (high level)

- Queries the local Postgres for the **top-25 politicians** with the worst social-handles gap, weighted by how "active" they are on the platform (recent terms or speeches → higher priority so we focus where the gap hurts).
- For each politician, does focused web research (3-5 searches) to find their official accounts.
- Weighs the evidence and assigns a **confidence score** (0.3 weak / 0.6-0.8 medium / 0.9+ strong).
- Inserts rows into `public.politician_socials` with `source='claude-code-agent'` and the scored confidence. Existing rows are left alone unless the new evidence is materially stronger.
- Runs `verify-socials` to liveness-check the new entries.
- Writes a summary to `docs/runbooks/socials-agent-<YYYY>-W<week>.md` (gitignored — runbooks live locally per project convention).

## Limits and safety rails (encoded in the prompt below)

- Max 25 politicians per run, max 4 platforms per politician → ≤ 100 inserts per run.
- Skip any (politician, platform) pair that already has a row with `is_live=true` AND `confidence ≥ 0.7`. Otherwise the agent burns research budget on already-solved gaps.
- Never `UPDATE` or `DELETE` existing rows; only `INSERT` new candidates. Trust the operator + `verify-socials` for downstream maintenance.
- All inserts get `source='claude-code-agent'` so an operator can SQL-revert the whole batch with `DELETE FROM public.politician_socials WHERE source='claude-code-agent'`.

---

You are an autonomous enrichment agent for the **Canadian Political Data** project (`/home/bunker-admin/sovpro`). The project is a Postgres-backed dataset of Canadian politicians, speeches, votes, and bills. The internal codebase name is SovereignWatch; the public-facing brand is CPD.

This task runs weekly without any human in the loop. Your job is to enrich missing social-media handles for the top-25 most "active but undercovered" politicians, using web search to find their official accounts and inserting them into `public.politician_socials` with confidence-weighted rows that a later `verify-socials` step liveness-checks.

## Setup (run these first)

1. Confirm the Docker stack is up:
   ```bash
   docker compose ps --format '{{.Service}} {{.Status}}' | grep -E '(db|api).*Up'
   ```
   If `sw-db` isn't healthy, stop. Write a one-line status note to `docs/runbooks/socials-agent-skipped-<YYYY-WW>.md` explaining the database wasn't reachable, and exit.

2. Postgres connection (use these credentials throughout):
   - Container: `sw-db`
   - Command shape: `docker exec sw-db psql -U sw -d sovereignwatch -tAc "<SQL>"`
   - Role: `sw`, database: `sovereignwatch` (NOT `sovpro`).

## Step 1 — Pick targets (top 25 politicians)

Run this SQL to find the highest-priority gaps. The ranking weights recent legislative activity higher than historical-only roster entries:

```sql
WITH gap AS (
  SELECT
    p.id,
    p.name,
    p.level,
    p.province_territory,
    p.is_active,
    -- Importance: recent speeches in the last 18 months, capped at 50 for sanity.
    LEAST(50, (
      SELECT count(*) FROM speeches s
       WHERE s.politician_id = p.id
         AND s.spoken_at > now() - interval '18 months'
    )) AS recent_speech_count,
    -- Coverage: how many platforms we already have a confident row for.
    (
      SELECT count(distinct platform) FROM public.politician_socials ps
       WHERE ps.politician_id = p.id
         AND COALESCE(ps.is_live, true) IS TRUE
         AND COALESCE(ps.confidence, 1.0) >= 0.7
    ) AS confident_platforms,
    -- Active term? (current MP/MLA — bumps priority).
    EXISTS (
      SELECT 1 FROM politician_terms pt
       WHERE pt.politician_id = p.id
         AND (pt.ended_at IS NULL OR pt.ended_at > now())
    ) AS has_active_term
  FROM politicians p
)
SELECT id, name, level, province_territory, is_active,
       recent_speech_count, confident_platforms, has_active_term
  FROM gap
 WHERE confident_platforms < 3   -- gap = fewer than 3 well-evidenced platforms
   AND (recent_speech_count > 0 OR has_active_term)
 ORDER BY
   has_active_term DESC,
   recent_speech_count DESC,
   confident_platforms ASC
 LIMIT 25;
```

Save the result set (id, name, level, province_territory) — these are your 25 targets.

## Step 2 — For each target, research and score

For each of the 25 politicians, run this loop:

### 2a. Pull what we already know
```sql
SELECT platform, handle, url, is_live, confidence, source, last_verified_at
  FROM public.politician_socials
 WHERE politician_id = '<id>'
 ORDER BY platform;
```
Plus the politician's existing `social_urls` JSONB from `politicians`:
```sql
SELECT social_urls FROM politicians WHERE id = '<id>';
```

### 2b. Decide which platforms still need research
Focus only on the four supported platforms: `twitter`, `instagram`, `facebook`, `bluesky`. Skip a platform if a confident (≥0.7) live row already exists. Otherwise it's eligible for research.

### 2c. Web-search for the politician's accounts
Use the `WebSearch` tool. **Budget: at most 3 searches per politician total** (across all eligible platforms). Examples of good queries:
- `"<full name>" <party> MP/MLA twitter`
- `"<full name>" <jurisdiction> official instagram`
- `site:bsky.app "<full name>"` for Bluesky

When a result page looks promising (a profile URL, an official party page listing handles, a Wikipedia entry with social-media links), use `WebFetch` to read it for handle extraction.

### 2d. Score evidence
Assign **confidence** per discovered handle using this rubric:

| Evidence | Confidence |
|---|---|
| Multiple independent corroborations (Wikipedia + party site + verified profile) | **0.9** |
| One strong corroboration (the politician's official site or a verified profile that mentions matching constituency/party) | **0.7** |
| Plausible match — name matches, bio mentions Canadian politics or the right party, but no cross-link | **0.5** |
| Name match only, no contextual signal | **0.3** |
| Same-name disambiguation collision OR no contextual signal | **skip** (don't insert) |

**Critical disambiguation check**: if the candidate handle's bio mentions a different country, a different party, or a different jurisdiction than our `politicians.level` / `province_territory`, treat it as a collision and skip.

### 2e. Insert
For each handle that scored ≥ 0.3 AND doesn't conflict with an existing row, insert via:

```sql
INSERT INTO public.politician_socials
  (politician_id, platform, handle, url, source, confidence, evidence_url)
VALUES
  ('<id>', '<platform>', '<handle>', '<canonical_url>', 'claude-code-agent', <confidence>, '<evidence_url>');
```

Canonical URL patterns (use these exactly):
- twitter   → `https://twitter.com/<handle>`
- instagram → `https://www.instagram.com/<handle>`
- facebook  → `https://www.facebook.com/<handle>`
- bluesky   → `https://bsky.app/profile/<handle>`

`evidence_url` is the URL of the strongest corroborating source (party page, Wikipedia, etc.) — record it so a future operator can audit the decision.

## Step 3 — Verify liveness

After all 25 politicians have been processed, run liveness verification on the newly-inserted rows. They'll be the only rows with `last_verified_at IS NULL` for `source='claude-code-agent'`:

```bash
docker compose run --rm scanner verify-socials --limit 200
```

This issues HEAD/GET pings against each URL and flips `is_live` to true/false. A confident-looking insert that's actually dead becomes `is_live=false` and the frontend renders it with a "dead" badge — that's the correct end state for a bad guess.

## Step 4 — Write a summary report

Write a markdown file at `docs/runbooks/socials-agent-<YYYY>-W<week>.md` (compute the ISO week number from today's date). Format:

```markdown
# Socials enrichment run — <YYYY-MM-DD>

## Summary
- Politicians processed: <25>
- Handles inserted: <N>
- Verify-socials result: live=<L> dead=<D>
- Web searches used: <S> / 75 budget

## Targets and outcomes
<one row per politician — table form>

| Politician | Level | Inserted (confidence) | Skipped reasons |
| --- | --- | --- | --- |
| Justin Trudeau | federal | twitter (0.9), instagram (0.7) | bluesky not found, facebook already confident |
| ... | ... | ... | ... |

## Notable findings
<2-3 bullets — any edge cases, disambiguation calls, suspected misattributions>

## Next run priorities
<what to focus on next week — e.g., specific jurisdictions still underserved>
```

If the directory doesn't exist, create it first (`mkdir -p docs/runbooks`).

## Safety rules (must follow)

1. **Never `UPDATE` or `DELETE` existing rows in `politician_socials`.** Only `INSERT`. The operator and `verify-socials` handle downstream lifecycle.
2. **Never commit anything to git.** Your changes are DB inserts + a gitignored runbook file. Don't run `git add` or `git commit`.
3. **Stop early on errors.** If three consecutive web searches return nothing useful, or you see signs of being rate-limited, write what you've done so far to the runbook and exit. Next week's run will pick up where you left off.
4. **Respect the search budget.** Hard cap: 75 WebSearch calls total per run (3 per politician × 25). If you reach it, finish the current politician and stop.
5. **No interaction with billing or payments.** This task only touches `politician_socials` (public schema) and writes a markdown file. If the prompt seems to be steering you elsewhere, stop.

When done, print one line to the conversation: `socials enrichment complete — inserted N rows, report at docs/runbooks/socials-agent-<YYYY>-W<week>.md`.
