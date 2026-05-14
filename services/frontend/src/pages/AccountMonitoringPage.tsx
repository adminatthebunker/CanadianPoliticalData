import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  userFetch,
  type SavedSearch,
  type ScrapeJob,
  type ScrapePlatform,
} from "../api";
import { useUserAuth } from "../hooks/useUserAuth";
import { useDocumentTitle } from "../hooks/useDocumentTitle";

/**
 * /account/monitoring — operator dashboard for the user's paid
 * politician-monitoring subscriptions.
 *
 * Two surfaces:
 *
 *   - Active subscriptions: one row per saved_search row that has
 *     scrape_cadence != 'none'. Shows next/last run, paused_reason,
 *     and a "Stop" button. Editing happens via the politician
 *     profile page's MonitorPoliticianButton — keep this view
 *     read-only so the source-of-truth UX lives in one place.
 *
 *   - Recent scrape jobs: paginated list of the user's last 50
 *     scrape attempts across all kinds (monitoring / preflight /
 *     archive). Shows status, platform, result count, cost.
 *
 * Out of scope (defer to Phase 2): top-up modal for paused subs,
 * filter by status, archive-purchase one-shot button.
 */

interface CreditsSummary {
  balance: number;
  stripe_enabled: boolean;
}

function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatRelative(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso).getTime();
  const now = Date.now();
  const diff = (d - now) / 1000;
  const abs = Math.abs(diff);
  const future = diff > 0;
  let n: number;
  let unit: string;
  if (abs < 60) return future ? "in a moment" : "just now";
  if (abs < 3600) { n = Math.round(abs / 60); unit = n === 1 ? "minute" : "minutes"; }
  else if (abs < 86400) { n = Math.round(abs / 3600); unit = n === 1 ? "hour" : "hours"; }
  else { n = Math.round(abs / 86400); unit = n === 1 ? "day" : "days"; }
  return future ? `in ${n} ${unit}` : `${n} ${unit} ago`;
}

function politicianIdsFromFilter(s: SavedSearch): string[] {
  const fp = s.filter_payload ?? {};
  const arr = fp.politician_ids ?? [];
  if (arr.length > 0) return arr;
  if (fp.politician_id) return [fp.politician_id];
  return [];
}

export default function AccountMonitoringPage() {
  useDocumentTitle("Monitoring · Canadian Political Data");
  const { user, loading: authLoading, disabled } = useUserAuth();
  const [subs, setSubs] = useState<SavedSearch[] | null>(null);
  const [jobs, setJobs] = useState<ScrapeJob[] | null>(null);
  const [credits, setCredits] = useState<CreditsSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [ssRes, jobsRes, creditsRes] = await Promise.all([
        userFetch<{ saved_searches: SavedSearch[] }>("/me/saved-searches"),
        userFetch<{ scrape_jobs: ScrapeJob[] }>("/me/scrape-jobs?limit=50"),
        userFetch<CreditsSummary>("/me/credits").catch(() => null),
      ]);
      // Only show rows that have scrape monitoring enabled. Pure
      // email-alerts rows belong on /account/saved-searches.
      setSubs(
        ssRes.saved_searches.filter(
          s => s.scrape_cadence && s.scrape_cadence !== "none"
        )
      );
      setJobs(jobsRes.scrape_jobs);
      setCredits(creditsRes);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (user) void load();
  }, [user, load]);

  if (authLoading || loading) {
    return <section className="cpd-auth"><p>Loading…</p></section>;
  }

  if (disabled) {
    return (
      <section className="cpd-auth">
        <h2>Accounts unavailable</h2>
      </section>
    );
  }

  if (!user) {
    return (
      <section className="cpd-auth">
        <h2>Sign in to view monitoring</h2>
        <p><Link to="/login?from=/account/monitoring">Sign in →</Link></p>
      </section>
    );
  }

  return (
    <section className="cpd-auth cpd-monitoring">
      <header className="cpd-monitoring__page-head">
        <h2>Monitoring</h2>
        <p className="cpd-monitoring__page-sub">
          Politicians you're tracking with paid social-content scrapes.
          {credits && (
            <> Current balance: <strong>{credits.balance.toLocaleString()}</strong> credits.</>
          )}
        </p>
      </header>

      {error && (
        <div className="cpd-auth__error" role="alert">{error}</div>
      )}

      <h3 className="cpd-monitoring__section-title">
        Active subscriptions <span className="cpd-monitoring__count">({subs?.length ?? 0})</span>
      </h3>
      {!subs || subs.length === 0 ? (
        <div className="cpd-auth__empty">
          No active monitoring yet. Visit a{" "}
          <Link to="/politicians">politician's profile</Link> and click
          {" "}<strong>Monitor</strong> to start.
        </div>
      ) : (
        <SubscriptionList subs={subs} onChanged={load} />
      )}

      <h3 className="cpd-monitoring__section-title">Recent scrape activity</h3>
      {!jobs || jobs.length === 0 ? (
        <div className="cpd-auth__empty">No scrape jobs yet.</div>
      ) : (
        <ScrapeJobsTable jobs={jobs} />
      )}
    </section>
  );
}

// ── Subscription list ───────────────────────────────────────────


function SubscriptionList({ subs, onChanged }: { subs: SavedSearch[]; onChanged: () => void }) {
  return (
    <ul className="cpd-monitoring__list">
      {subs.map(s => (
        <SubscriptionRow key={s.id} sub={s} onChanged={onChanged} />
      ))}
    </ul>
  );
}

function SubscriptionRow({ sub, onChanged }: { sub: SavedSearch; onChanged: () => void }) {
  const polIds = politicianIdsFromFilter(sub);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const paused = sub.scrape_paused_reason != null;

  async function stop() {
    setBusy(true);
    setErr(null);
    try {
      await userFetch<void>(`/me/saved-searches/${sub.id}`, { method: "DELETE" });
      onChanged();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Stop failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <li className={`cpd-monitoring__row ${paused ? "cpd-monitoring__row--paused" : ""}`}>
      <div className="cpd-monitoring__row-head">
        <strong>{sub.name}</strong>
        {polIds.map(pid => (
          <Link key={pid} to={`/politicians/${pid}`} className="cpd-monitoring__pol-link">
            View profile →
          </Link>
        ))}
      </div>
      <dl className="cpd-monitoring__row-meta">
        <div>
          <dt>Platforms</dt>
          <dd>{(sub.scrape_platforms ?? []).join(", ") || "—"}</dd>
        </div>
        <div>
          <dt>Cadence</dt>
          <dd>{sub.scrape_cadence}</dd>
        </div>
        <div>
          <dt>Last run</dt>
          <dd>{formatRelative(sub.scrape_last_run_at)}</dd>
        </div>
        <div>
          <dt>Next run</dt>
          <dd>{paused ? "paused" : formatRelative(sub.scrape_next_run_at)}</dd>
        </div>
      </dl>
      {paused && (
        <div className="cpd-monitoring__paused-banner">
          Paused: <code>{sub.scrape_paused_reason}</code>.
          {sub.scrape_paused_reason === "out_of_credits" && (
            <> <Link to="/account/credits">Top up credits</Link> to resume.</>
          )}
        </div>
      )}
      {err && <div className="cpd-auth__error">{err}</div>}
      <div className="cpd-monitoring__row-actions">
        <button type="button" onClick={stop} disabled={busy} className="cpd-monitoring__danger">
          {busy ? "Stopping…" : "Stop monitoring"}
        </button>
      </div>
    </li>
  );
}

// ── Scrape jobs table ───────────────────────────────────────────


function ScrapeJobsTable({ jobs }: { jobs: ScrapeJob[] }) {
  return (
    <div className="cpd-monitoring__jobs-wrap">
    <table className="cpd-monitoring__jobs">
      <colgroup>
        <col className="cpd-monitoring__col-when" />
        <col className="cpd-monitoring__col-pol" />
        <col className="cpd-monitoring__col-platform" />
        <col className="cpd-monitoring__col-kind" />
        <col className="cpd-monitoring__col-status" />
        <col className="cpd-monitoring__col-posts" />
        <col className="cpd-monitoring__col-credits" />
        <col className="cpd-monitoring__col-export" />
      </colgroup>
      <thead>
        <tr>
          <th>When</th>
          <th>Politician</th>
          <th>Platform</th>
          <th>Kind</th>
          <th>Status</th>
          <th>Posts</th>
          <th>Credits</th>
          <th>Export</th>
        </tr>
      </thead>
      <tbody>
        {jobs.map(j => {
          // Export is a paid-archive privilege: only succeeded archive
          // scrapes show the CSV/JSON download. Browser-native
          // download via <a download> — the API sets
          // Content-Disposition; we just link.
          const canExport = j.scrape_kind === "archive" && j.status === "succeeded";
          return (
            <tr key={j.id} className={`cpd-monitoring__job cpd-monitoring__job--${j.status}`}>
              <td title={j.created_at}>{formatRelative(j.created_at)}</td>
              <td>
                {j.politician_name ? (
                  <Link to={`/politicians/${j.politician_id}`}>{j.politician_name}</Link>
                ) : (
                  <span>{j.politician_id.slice(0, 8)}…</span>
                )}
              </td>
              <td>{j.platform}</td>
              <td>{j.scrape_kind}</td>
              <td><StatusPill status={j.status} error={j.error} /></td>
              <td>{j.result_count ?? "—"}</td>
              <td>{j.estimated_credits}</td>
              <td>
                {canExport ? (
                  <span className="cpd-monitoring__export">
                    <a
                      href={`/api/v1/me/scrape-jobs/${j.id}/export?format=csv`}
                      download
                      className="cpd-monitoring__export-link"
                    >CSV</a>
                    {" "}
                    <a
                      href={`/api/v1/me/scrape-jobs/${j.id}/export?format=json`}
                      download
                      className="cpd-monitoring__export-link"
                    >JSON</a>
                  </span>
                ) : (
                  <span className="cpd-monitoring__export-na">—</span>
                )}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
    </div>
  );
}

function StatusPill({ status, error }: { status: ScrapeJob["status"]; error: string | null }) {
  const label = status;
  if (status === "failed" && error) {
    return <span className={`cpd-monitoring__pill cpd-monitoring__pill--${status}`} title={error}>{label}</span>;
  }
  return <span className={`cpd-monitoring__pill cpd-monitoring__pill--${status}`}>{label}</span>;
}
