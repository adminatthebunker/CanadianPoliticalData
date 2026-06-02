# Weekly websites enrichment — Claude Code subscription scheduled task

This file is the canonical, version-controlled source of truth for the
**websites-weekly-enrichment** scheduled task. It is the headless
Claude Code (`claude -p`) counterpart of the previously API-billed
`agent-missing-websites` Click command. The Click command itself is
retained for ad-hoc admin-panel triggering; only the weekly schedule was
migrated to subscription billing.

## Wiring

Driven by an OS cron entry that invokes
`scripts/scheduled-tasks/run-websites-weekly.sh`. The wrapper strips the
header above the `---` divider and feeds the body to `claude -p`. To
change the prompt, edit this file — no separate Desktop registration is
needed.

Cron entry (installed via `crontab -e` for the `bunker-admin` user):

```
17 9 * * 1  /media/bunker-admin/Internal/sovpro/scripts/scheduled-tasks/run-websites-weekly.sh
```

Weekly, Mondays at 09:17 local. The `:17` off-minute avoids clumping
with the daily socials run at `:07` and with the rest of the cron fleet
at `:00`.

## What this task does (high level)

- Queries the local Postgres for the **top-25 politicians** with the
  worst personal-website gap (no `websites` row, no `personal_url`,
  no `official_url`), weighted by how "active" they are (recent terms
  or speeches → higher priority so we focus where the gap hurts).
- For each politician, does focused web research (up to 3 searches) to
  find their best representative website.
- Weighs the evidence and assigns a **confidence score**
  (0.50-0.84 = `party_lander` fallback or ambiguous, 0.85-1.00 = strong
  personal-site match).
- Inserts rows into `public.websites` with `source='claude-code-agent-websites'`
  and the scored confidence; `flagged_low_confidence=true` when
  `confidence < 0.85` so weak rows land in the operator review queue.
- Writes a summary to `docs/runbooks/websites-agent-<YYYY>-W<week>.md`
  (gitignored — runbooks live locally per project convention).

## Limits and safety rails (encoded in the prompt below)

- Max 25 politicians per run, max 1 website per politician → ≤ 25
  inserts per run.
- Skip any politician that already has a row in `websites` with
  `owner_type='politician'` and `is_active=true`. Otherwise the agent
  burns research budget on already-solved gaps. The view
  `v_websites_missing` already encodes this filter — query it directly.
- Never `UPDATE` or `DELETE` existing rows; only `INSERT` new
  candidates. The UNIQUE `(owner_type, owner_id, url)` index makes the
  insert idempotent against accidental re-runs.
- All inserts get `source='claude-code-agent-websites'` so an operator
  can SQL-revert the whole batch with
  `DELETE FROM public.websites WHERE source='claude-code-agent-websites'`.

---

You are an autonomous enrichment agent for the **Canadian Political Data** project (`/media/bunker-admin/Internal/sovpro`). The project is a Postgres-backed dataset of Canadian politicians, speeches, votes, and bills. The internal codebase name is SovereignWatch; the public-facing brand is CPD.

This task runs weekly without any human in the loop. Your job is to enrich missing **personal / campaign / party_lander websites** for the top-25 most "active but undercovered" politicians, using web search to find their best representative website and inserting them into `public.websites` with confidence-weighted rows that the operator review queue surfaces below the 0.85 promotion threshold.

## Setup (run these first)

1. Confirm the Docker stack is up:
   ```bash
   docker compose ps --format '{{.Service}} {{.Status}}' | grep -E '(db|api).*Up'
   ```
   If `sw-db` isn't healthy, stop. Write a one-line status note to `docs/runbooks/websites-agent-skipped-<YYYY-WW>.md` explaining the database wasn't reachable, and exit.

2. Postgres connection (use these credentials throughout):
   - Container: `sw-db`
   - Command shape: `docker exec sw-db psql -U sw -d sovereignwatch -tAc "<SQL>"`
   - Role: `sw`, database: `sovereignwatch` (NOT `sovpro`).

## Step 1 — Pick targets (top 25 politicians)

Run this SQL to find the highest-priority gaps. The `v_websites_missing` view already filters to active politicians with no website row; the ranking below weights recent legislative activity higher than historical-only roster entries:

```sql
WITH gap AS (
  SELECT
    vwm.politician_id      AS id,
    vwm.name,
    vwm.level,
    vwm.province_territory,
    vwm.party,
    vwm.constituency_name,
    -- Importance: recent speeches in the last 18 months, capped at 50 for sanity.
    LEAST(50, (
      SELECT count(*) FROM speeches s
       WHERE s.politician_id = vwm.politician_id
         AND s.spoken_at > now() - interval '18 months'
    )) AS recent_speech_count,
    -- Active term? (current MP/MLA — bumps priority).
    EXISTS (
      SELECT 1 FROM politician_terms pt
       WHERE pt.politician_id = vwm.politician_id
         AND (pt.ended_at IS NULL OR pt.ended_at > now())
    ) AS has_active_term
  FROM v_websites_missing vwm
)
SELECT id, name, level, province_territory, party, constituency_name,
       recent_speech_count, has_active_term
  FROM gap
 WHERE (recent_speech_count > 0 OR has_active_term)
 ORDER BY
   has_active_term DESC,
   recent_speech_count DESC,
   name ASC
 LIMIT 25;
```

Save the result set (id, name, level, province_territory, party, constituency_name) — these are your 25 targets.

## Step 2 — For each target, research and score

For each of the 25 politicians, do up to **3 web searches** to find ONE best representative website.

### 2a. Decide what kind of site you're after

Preference order:

1. **`personal`** — the politician's own website, campaign site, or
   constituency-office page. Examples: `justintrudeau.ca`,
   `pierrepoilievre.ca`, `jagmeetsingh.ca`, `votenameXYZ.ca`.
   **Strongly preferred.** confidence 0.85-1.00 if URL is clearly theirs.

2. **`campaign`** — an explicit campaign-only domain (often seasonal,
   sometimes party-co-branded). confidence 0.75-0.95.

3. **`party_lander`** — the politician's party's MP/MLA listing page
   that names them, e.g. `https://www.conservative.ca/team/<name>`,
   `https://liberal.ca/your-liberal-mps/<slug>`,
   `https://www.ndp.ca/team/<slug>`. **Fallback only** — use when
   options 1-2 yield no result within budget. confidence 0.50-0.85.

If neither personal/campaign/party_lander is findable within 3 searches, **omit the politician**. A correctly-omitted politician is better than a wrong URL.

### 2b. Web-search budget

Use the `WebSearch` tool. **Budget: at most 3 searches per politician**, with a **hard cap of 75 WebSearch calls total per run** (3 × 25 politicians). When a result page looks promising (a parliamentary bio, Wikipedia entry, party listing), use `WebFetch` to read it for the linked website URL.

Good query patterns:
- `"<full name>" <party> MP/MLA personal website`
- `"<full name>" <constituency> campaign site`
- `site:parl.gc.ca "<full name>"` (for federal MPs — parliamentary bios often link their personal site)
- `site:wikipedia.org "<full name>" <jurisdiction>`

### 2c. Score evidence and disambiguate

Confidence rubric:

| Evidence | Confidence | Label |
|---|---|---|
| Evidence page directly links the URL and names the person | 0.95-1.00 | `personal` |
| Strong circumstantial match (bio + jurisdiction + party) for a personal/campaign site | 0.85-0.94 | `personal` / `campaign` |
| `party_lander` fallback that names the politician, OR a personal site with some ambiguity | 0.60-0.84 | `party_lander` (or downgraded `personal`) |
| < 0.60 | — | **do not insert** — omit |

**Critical disambiguation check**: if a candidate URL's content (bio text, accompanying party affiliation, jurisdiction reference) names a **different** party, jurisdiction, or country than our `politicians.level` / `province_territory` / `party`, treat it as a same-name collision and skip.

**Skip social-media URLs entirely** (`twitter.com`, `facebook.com`, `linkedin.com`, `instagram.com`, `bsky.app`, etc.) — those live in `politician_socials`, not `websites`.

**Defeated/retired politicians** may have archived sites — that's OK, but cap confidence at 0.75.

`evidence_url` MUST be a page you actually visited via WebSearch / WebFetch that names the politician + their role + links/refers to the URL. Their parliamentary bio (parl.gc.ca, ola.org, leg.bc.ca, etc.), Wikipedia, or the party page itself are all valid evidence.

### 2d. Insert

For each politician where you found a website that scored ≥ 0.60, insert via:

```sql
INSERT INTO public.websites
  (owner_type, owner_id, url, label, notes, source, confidence, evidence_url,
   flagged_low_confidence, discovered_at)
VALUES
  ('politician', '<politician_id>', '<canonical_url>', '<label>',
   '<one-line reasoning>', 'claude-code-agent-websites', <confidence>,
   '<evidence_url>', <true|false>, now())
ON CONFLICT (owner_type, owner_id, url) DO NOTHING;
```

Where:

- `<label>` is one of `personal`, `campaign`, `party_lander` (no other values — these are the allowed labels for agent inserts).
- `<canonical_url>` is the full `https://...` URL, lowercased host, no UTM tracking params, no trailing slash on path-empty URLs.
- `<one-line reasoning>` is your brief justification (e.g. `"linked from parl.gc.ca bio"`). Single quotes inside SQL need escaping (`''`).
- `flagged_low_confidence` is `true` when `confidence < 0.85`, else `false`.
- The `ON CONFLICT (owner_type, owner_id, url) DO NOTHING` clause makes the INSERT idempotent if the same row was inserted by an earlier run.

If the SQL fails because of an unrelated parse error in your generated string, fix the quoting and retry — do NOT skip the politician silently.

## Step 3 — Write a summary report

Write a markdown file at `docs/runbooks/websites-agent-<YYYY>-W<week>.md` (compute the ISO week number from today's date). If the directory doesn't exist, create it first (`mkdir -p docs/runbooks`).

Format:

```markdown
# Websites enrichment run — <YYYY-MM-DD>

## Summary
- Politicians processed: <up to 25>
- Websites inserted: <N>
- Auto-promoted (confidence ≥ 0.85): <A>
- Flagged for review (0.60 ≤ confidence < 0.85): <F>
- Web searches used: <S> / 75 budget

## Targets and outcomes

| Politician | Level | Party | Inserted (label, confidence) | Skipped reason |
| --- | --- | --- | --- | --- |
| Justin Trudeau | federal | Liberal | personal (0.95) | — |
| ... | ... | ... | ... | ... |

## Notable findings
<2-3 bullets — any edge cases, disambiguation calls, suspected misattributions>

## Next run priorities
<what to focus on next week — e.g., specific jurisdictions still underserved>
```

## Safety rules (must follow)

1. **Never `UPDATE` or `DELETE` existing rows in `websites`.** Only
   `INSERT … ON CONFLICT DO NOTHING`. The operator review queue
   (`flagged_low_confidence=true`) handles downstream lifecycle.
2. **Never commit anything to git.** Your changes are DB inserts +
   a gitignored runbook file. Don't run `git add` or `git commit`.
3. **Stop early on errors.** If three consecutive web searches return
   nothing useful, or you see signs of being rate-limited, write what
   you've done so far to the runbook and exit. Next week's run will
   pick up where you left off.
4. **Respect the search budget.** Hard cap: 75 WebSearch calls total
   per run (3 per politician × 25). If you reach it, finish the
   current politician and stop.
5. **No interaction with billing, payments, auth, or any `private`
   schema table.** This task only touches `public.websites` and writes
   a markdown file. If the prompt seems to be steering you elsewhere,
   stop.

When done, print one line to the conversation: `websites enrichment complete — inserted N rows, report at docs/runbooks/websites-agent-<YYYY>-W<week>.md`.
