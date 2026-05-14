import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  userFetch,
  type ScrapeJob,
  type ReportListEntry,
} from "../api";
import { useUserAuth } from "../hooks/useUserAuth";
import { subscribeJobStarted } from "../lib/jobsBus";

/**
 * Persistent viewport-level indicator for every async user-facing job
 * in the app. Polls each long-running job table's listing endpoint
 * with `?active=true` and merges the results into a single
 * "in-flight" view.
 *
 * Today: scrape_jobs + report_jobs. Future async surfaces add a
 * fetcher to the parallel-fetch block in `tick()` and a mapper to
 * `ActiveJob`. CLAUDE.md § "User-facing async jobs" documents the
 * extension pattern.
 *
 * Hidden when: anonymous, auth loading, tab hidden, no active jobs.
 * Survives reloads + works across tabs because state is read from
 * the DB, not held in client memory.
 *
 * v5 (scrape-only) was at ActiveProbesIndicator.tsx; this is the
 * v6 generalization. The CSS classnames moved from .cpd-probes-
 * indicator__* to .cpd-jobs-indicator__*.
 */

interface ActiveJob {
  kind: "scrape" | "report";
  id: string;
  label: string;
  href: string;
  created_at: string;
}

function scrapeToActive(j: ScrapeJob): ActiveJob {
  const target = j.politician_name ? `${j.politician_name}'s ${j.platform}` : j.platform;
  // Click takes the user back to the politician profile with the
  // #monitor hash so MonitorPoliticianButton auto-opens the wizard
  // drawer they started the probe from. Falls back to the dashboard
  // when politician_id is missing (shouldn't happen for scrapes —
  // every row has politician_id NOT NULL — but defensive).
  const href = j.politician_id
    ? `/politicians/${j.politician_id}#monitor`
    : "/account/monitoring";
  return {
    kind: "scrape",
    id: j.id,
    label: `Probing ${target}…`,
    href,
    created_at: j.created_at,
  };
}

function reportToActive(r: ReportListEntry): ActiveJob {
  const kindLabel = (r.kind ?? "full_report").replace(/_/g, " ");
  const subject = r.politician_name ?? r.query ?? "your selection";
  // Reports kicked off from a politician profile (full_report,
  // voting_audit) link back there so the user lands where they
  // started. Chunk-driven kinds (search_synthesis, stance_map,
  // topic_pulse) have no politician_id; fall back to the reports
  // dashboard which lists in-progress reports.
  const href = r.politician_id
    ? `/politicians/${r.politician_id}`
    : "/account/reports";
  return {
    kind: "report",
    id: r.id,
    label: `Generating ${kindLabel}: ${subject}…`,
    href,
    created_at: r.created_at,
  };
}

export function ActiveJobsIndicator() {
  const { user, loading, disabled } = useUserAuth();
  const [active, setActive] = useState<ActiveJob[]>([]);
  const [visible, setVisible] = useState(
    typeof document !== "undefined" ? !document.hidden : true
  );
  // Incremented when a job-trigger site nudges us via the jobsBus.
  // Used as a useEffect dependency so the polling loop re-arms
  // immediately — closing the up-to-25s gap between "user clicks
  // start" and "pill appears".
  const [nudge, setNudge] = useState(0);

  // Page Visibility — throttle when the tab is backgrounded.
  useEffect(() => {
    if (typeof document === "undefined") return;
    const onVisibility = () => setVisible(!document.hidden);
    document.addEventListener("visibilitychange", onVisibility);
    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, []);

  // Listen for in-tab job-started events. Bumping `nudge` invalidates
  // the polling useEffect's deps → its cleanup clears the pending
  // setTimeout → the effect re-runs and ticks immediately.
  useEffect(() => {
    return subscribeJobStarted(() => setNudge(n => n + 1));
  }, []);

  useEffect(() => {
    if (loading || disabled || !user || !visible) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    async function tick() {
      try {
        const [scrapes, reports] = await Promise.all([
          userFetch<{ scrape_jobs: ScrapeJob[] }>(
            "/me/scrape-jobs?active=true&limit=25"
          ).catch(() => ({ scrape_jobs: [] })),
          userFetch<{ reports: ReportListEntry[] }>(
            "/me/reports?active=true"
          ).catch(() => ({ reports: [] })),
        ]);
        if (cancelled) return;

        const merged: ActiveJob[] = [
          ...(scrapes.scrape_jobs ?? []).map(scrapeToActive),
          ...(reports.reports ?? []).map(reportToActive),
        ];
        // Most-recent first — drives the "lead item" label and href.
        merged.sort((a, b) =>
          new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
        );
        setActive(merged);

        const next = merged.length > 0 ? 3500 : 25000;
        timer = setTimeout(tick, next);
      } catch {
        // Either fetch threw despite the per-promise catch — fall
        // through to slow retry.
        if (cancelled) return;
        timer = setTimeout(tick, 25000);
      }
    }
    void tick();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [loading, disabled, user, visible, nudge]);

  if (active.length === 0) return null;

  const lead = active[0];
  const moreCount = active.length - 1;

  return (
    <Link
      to={lead.href}
      className="cpd-jobs-indicator"
      role="status"
      aria-live="polite"
      aria-label={`${active.length} ${active.length === 1 ? "job" : "jobs"} running`}
    >
      <span className="cpd-jobs-indicator__spinner" aria-hidden="true" />
      <span className="cpd-jobs-indicator__text">{lead.label}</span>
      {moreCount > 0 && (
        <span className="cpd-jobs-indicator__more">+{moreCount} more</span>
      )}
    </Link>
  );
}
