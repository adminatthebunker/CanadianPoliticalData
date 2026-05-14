import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import {
  userFetch,
  type SavedSearch,
  type ScrapeCadence,
  type ScrapeCostEstimate,
  type ScrapeJob,
  type ScrapePlatform,
} from "../api";
import { useUserAuth } from "../hooks/useUserAuth";
import { notifyJobStarted } from "../lib/jobsBus";

/**
 * "Monitor politician" surface on the politician profile page. Two
 * axes layered on the same saved_searches row:
 *
 *   - alert_cadence (none/daily/weekly) drives the alerts worker:
 *     emailed digest of new Hansard speeches. Free.
 *   - scrape_cadence (none/weekly/monthly/quarterly) + scrape_platforms[]
 *     drive the scrape_worker: per-refresh Apify pulls of the
 *     politician's socials, debited from the user's credit balance.
 *
 * Today: open the panel, configure either or both axes, hit Save.
 * The DB row is one saved_search keyed (user_id, politician_id-as-
 * filter_payload). Server-side computes scrape_next_run_at on cadence
 * change. Cost preview is fetched server-side from the cached
 * politician_socials.lifetime_post_count.
 *
 * Visibility: scraped posts are subscriber-only until v2; until then
 * they surface in /account/monitoring not on the public profile.
 */

interface Props {
  politicianId: string;
  politicianName: string;
}

const ALL_PLATFORMS: ScrapePlatform[] = ["twitter", "bluesky", "instagram", "mastodon"];
const SCRAPE_CADENCES: Exclude<ScrapeCadence, "none">[] = ["weekly", "monthly", "quarterly"];

type LoadState =
  | { kind: "loading" }
  | { kind: "anonymous" }
  | { kind: "ready"; existing: SavedSearch | null };

function findExisting(rows: SavedSearch[], politicianId: string): SavedSearch | null {
  // Match a "monitor this politician" row: politician_ids=[id] or
  // legacy politician_id=id, with no q.
  for (const s of rows) {
    const fp = s.filter_payload ?? {};
    if (fp.q && fp.q.trim()) continue;
    const ids = fp.politician_ids ?? [];
    if (ids.length === 1 && ids[0] === politicianId) return s;
    if (ids.length === 0 && fp.politician_id === politicianId) return s;
  }
  return null;
}

export function MonitorPoliticianButton({ politicianId, politicianName }: Props) {
  const { user, loading: authLoading, disabled } = useUserAuth();
  const location = useLocation();
  const [load, setLoad] = useState<LoadState>({ kind: "loading" });
  const [open, setOpen] = useState(false);

  // Auto-open the config panel when the URL hash is #monitor. Lets the
  // Posts-tab CTA link directly to the Monitor flow without inter-
  // component plumbing. We strip the hash once opened so a refresh
  // doesn't keep re-triggering. Only fires once auth has resolved AND
  // the user is signed in (anon clicks go to /login via a different CTA).
  useEffect(() => {
    if (authLoading) return;
    if (!user) return;
    if (location.hash !== "#monitor") return;
    setOpen(true);
    // Replace history entry to clear the hash without scrolling.
    if (typeof window !== "undefined") {
      window.history.replaceState(null, "", location.pathname + location.search);
    }
  }, [authLoading, user, location.hash, location.pathname, location.search]);

  const refresh = useCallback(async () => {
    if (!user) {
      setLoad({ kind: "anonymous" });
      return;
    }
    try {
      const res = await userFetch<{ saved_searches: SavedSearch[] }>(
        "/me/saved-searches"
      );
      setLoad({ kind: "ready", existing: findExisting(res.saved_searches, politicianId) });
    } catch (e) {
      setLoad({ kind: "ready", existing: null });
      console.error("MonitorPoliticianButton: load failed", e);
    }
  }, [user, politicianId]);

  useEffect(() => {
    if (authLoading) {
      setLoad({ kind: "loading" });
      return;
    }
    void refresh();
  }, [authLoading, refresh]);

  if (disabled) return null;
  if (load.kind === "loading") return null;

  if (load.kind === "anonymous") {
    const from = encodeURIComponent(location.pathname + location.search);
    return (
      <Link to={`/login?from=${from}`} className="cpd-monitor cpd-monitor--anon">
        Sign in to monitor
      </Link>
    );
  }

  const existing = load.existing;
  const isMonitoring = existing !== null && (
    existing.alert_cadence !== "none" ||
    (existing.scrape_cadence && existing.scrape_cadence !== "none")
  );

  return (
    <div className="cpd-monitor-wrap">
      <button
        type="button"
        className={isMonitoring ? "cpd-monitor cpd-monitor--on" : "cpd-monitor"}
        onClick={() => setOpen(o => !o)}
        aria-expanded={open}
      >
        {isMonitoring ? "✓ Monitoring · Configure" : "Monitor"}
      </button>
      {open && (
        <MonitorConfigPanel
          existing={existing}
          politicianId={politicianId}
          politicianName={politicianName}
          onClose={() => {
            setOpen(false);
            void refresh();
          }}
        />
      )}
    </div>
  );
}

// ── Config panel ──────────────────────────────────────────────────


interface PanelProps {
  existing: SavedSearch | null;
  politicianId: string;
  politicianName: string;
  onClose: () => void;
}

function MonitorConfigPanel({
  existing,
  politicianId,
  politicianName,
  onClose,
}: PanelProps) {
  // Local form state, seeded from the existing row when editing.
  const [alertCadence, setAlertCadence] = useState<"none" | "daily" | "weekly">(
    existing?.alert_cadence ?? "daily"
  );
  const [platforms, setPlatforms] = useState<ScrapePlatform[]>(
    (existing?.scrape_platforms as ScrapePlatform[] | undefined) ?? []
  );
  const [scrapeCadence, setScrapeCadence] = useState<"none" | "weekly" | "monthly" | "quarterly">(
    existing?.scrape_cadence ?? "none"
  );
  // Attribution opt-in: when set, the politician's public profile shows
  // "Funded by <handle>" for posts captured by this subscription. NULL
  // = anonymous "Scraped via paid monitoring". An optional URL turns
  // the handle into a clickable link.
  const initialAttributionEnabled =
    existing?.scrape_attribute_handle != null && existing.scrape_attribute_handle !== "";
  const [attributionEnabled, setAttributionEnabled] = useState(initialAttributionEnabled);
  const [attributionHandle, setAttributionHandle] = useState(
    existing?.scrape_attribute_handle ?? ""
  );
  const [attributionUrl, setAttributionUrl] = useState(
    existing?.scrape_attribute_url ?? ""
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Wizard step. New users land on Scan first (so we have lifetime
  // counts to price Backfill against). Existing subscribers jump
  // straight to Monitor — they're editing an already-configured row.
  type Step = "scan" | "backfill" | "monitor";
  const [step, setStep] = useState<Step>(
    existing && existing.scrape_cadence && existing.scrape_cadence !== "none"
      ? "monitor"
      : "scan"
  );

  // Cost-estimate fetch (debounced — refire when platforms or cadence change).
  const [estimate, setEstimate] = useState<ScrapeCostEstimate | null>(null);
  const [estLoading, setEstLoading] = useState(false);
  // Bumping `refreshTick` re-runs the fetch effect — used after a
  // preflight completes so the cost panel picks up the newly-cached
  // lifetime_post_count without the user having to toggle anything.
  const [refreshTick, setRefreshTick] = useState(0);
  const cadenceForEstimate: "weekly" | "monthly" | "quarterly" =
    scrapeCadence === "none" ? "weekly" : scrapeCadence;

  // Always fetch the estimate for all four supported platforms. Each
  // wizard step reads its own subset of the response:
  //   - Scan step: per_platform[p].lifetime_post_count + .preflight_credits
  //   - Backfill step: per_platform[p].archive_credits
  //   - Monitor step: per_platform[selected].monitoring_credits_per_run
  // The user's monitor-platform selection (`platforms`) drives saving,
  // not the estimate request shape.
  useEffect(() => {
    const ctrl = new AbortController();
    setEstLoading(true);
    const qs = new URLSearchParams({
      politician_id: politicianId,
      platforms: ALL_PLATFORMS.join(","),
      cadence: cadenceForEstimate,
    });
    userFetch<ScrapeCostEstimate>(`/me/scrape-cost-estimate?${qs}`, {
      signal: ctrl.signal,
    })
      .then(res => setEstimate(res))
      .catch(e => {
        if ((e as Error).name !== "AbortError") {
          console.error("cost-estimate failed", e);
        }
      })
      .finally(() => setEstLoading(false));
    return () => ctrl.abort();
  }, [politicianId, cadenceForEstimate, refreshTick]);

  // Panel-level probe watcher — survives step transitions.
  //
  // Why this exists separately from ScanRowPoll: the in-row poll lives
  // inside ScanStep. If the user clicks Continue (advancing to Backfill)
  // while a probe is still running, ScanStep unmounts, its poll
  // cleanup fires, and the original onPreflightDone callback never
  // gets called when the probe lands. The estimate stays stale and
  // the next step's data is wrong.
  //
  // This effect runs at the panel level for the panel's full lifetime
  // (or until the politician changes), polling for any of the user's
  // active scrape jobs against THIS politician. When the count of
  // active jobs drops, it means at least one finished — bump
  // refreshTick to pick up its profile-cache write.
  useEffect(() => {
    let cancelled = false;
    let lastActiveForPolitician = -1;
    let timer: ReturnType<typeof setTimeout> | null = null;

    async function tick() {
      if (cancelled) return;
      try {
        const res = await userFetch<{ scrape_jobs: ScrapeJob[] }>(
          "/me/scrape-jobs?active=true&limit=25"
        );
        if (cancelled) return;
        const mine = (res.scrape_jobs ?? []).filter(
          j => j.politician_id === politicianId
        );
        if (lastActiveForPolitician > 0 && mine.length < lastActiveForPolitician) {
          // A job for this politician just completed — refetch estimate.
          setRefreshTick(t => t + 1);
        }
        lastActiveForPolitician = mine.length;
      } catch {
        // Silent retry — this is a courtesy watcher, not a hard dep.
      }
      if (!cancelled) {
        // Faster cadence than the global indicator (2.5s) since the
        // user is actively waiting on this panel; the load is small.
        timer = setTimeout(tick, 2500);
      }
    }
    timer = setTimeout(tick, 200);
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [politicianId]);

  const totalMonthly = estimate?.monitoring.total_per_month ?? 0;
  const scrapingActive = platforms.length > 0 && scrapeCadence !== "none";

  function togglePlatform(p: ScrapePlatform) {
    setPlatforms(prev => prev.includes(p) ? prev.filter(x => x !== p) : [...prev, p]);
  }

  async function save() {
    setSaving(true);
    setError(null);
    try {
      const wantsAnything =
        alertCadence !== "none" || scrapingActive;
      if (!existing && !wantsAnything) {
        // Nothing to save — no-op.
        onClose();
        return;
      }
      // Normalize the attribution opt-in: only send a non-null handle
      // when the user has both enabled attribution AND typed something.
      // The empty string is preserved as NULL on the server side.
      const attributeHandle = attributionEnabled && attributionHandle.trim().length > 0
        ? attributionHandle.trim()
        : null;
      // URL is only meaningful when handle is also set. Trim + drop
      // non-https; server zod will reject malformed values anyway.
      const attributeUrl =
        attributeHandle && attributionUrl.trim().length > 0
          ? attributionUrl.trim()
          : null;

      if (!existing) {
        // Create.
        await userFetch<SavedSearch>("/me/saved-searches", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name: `Monitor ${politicianName}`,
            filter_payload: { q: "", lang: "any", politician_ids: [politicianId] },
            alert_cadence: alertCadence,
            scrape_platforms: scrapingActive ? platforms : [],
            scrape_cadence: scrapingActive ? scrapeCadence : "none",
            scrape_attribute_handle: attributeHandle,
            scrape_attribute_url: attributeUrl,
          }),
        });
      } else {
        await userFetch<SavedSearch>(`/me/saved-searches/${existing.id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            alert_cadence: alertCadence,
            scrape_platforms: scrapingActive ? platforms : [],
            scrape_cadence: scrapingActive ? scrapeCadence : "none",
            scrape_attribute_handle: attributeHandle,
            scrape_attribute_url: attributeUrl,
          }),
        });
      }
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  async function stopMonitoring() {
    if (!existing) {
      onClose();
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await userFetch<void>(`/me/saved-searches/${existing.id}`, {
        method: "DELETE",
      });
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not stop monitoring");
    } finally {
      setSaving(false);
    }
  }

  return (
    <MonitorDrawer
      politicianName={politicianName}
      onClose={onClose}
    >
      <h3 className="cpd-monitor-panel__title">Configure monitoring</h3>

      <WizardStepIndicator current={step} onJump={setStep} />

      {step === "scan" && (
        <ScanStep
          politicianId={politicianId}
          politicianName={politicianName}
          estimate={estimate}
          onPreflightDone={() => setRefreshTick(t => t + 1)}
        />
      )}

      {step === "backfill" && (
        <BackfillStep
          politicianId={politicianId}
          estimate={estimate}
          onPreflightDone={() => setRefreshTick(t => t + 1)}
        />
      )}

      {step === "monitor" && (
        <MonitorStep
          politicianName={politicianName}
          alertCadence={alertCadence}
          setAlertCadence={setAlertCadence}
          platforms={platforms}
          togglePlatform={togglePlatform}
          scrapeCadence={scrapeCadence}
          setScrapeCadence={setScrapeCadence}
          estimate={estimate}
          attributionEnabled={attributionEnabled}
          setAttributionEnabled={setAttributionEnabled}
          attributionHandle={attributionHandle}
          setAttributionHandle={setAttributionHandle}
          attributionUrl={attributionUrl}
          setAttributionUrl={setAttributionUrl}
        />
      )}

      {error && (
        <div className="cpd-monitor-panel__error" role="alert">{error}</div>
      )}

      <div className="cpd-monitor-panel__actions">
        {step === "scan" && (
          <>
            <button type="button" onClick={onClose} disabled={saving}>Cancel</button>
            <button
              type="button"
              onClick={() => setStep("backfill")}
              className="cpd-monitor-panel__primary"
            >
              Continue →
            </button>
          </>
        )}
        {step === "backfill" && (
          <>
            <button type="button" onClick={() => setStep("scan")} disabled={saving}>← Back</button>
            <button
              type="button"
              onClick={() => setStep("monitor")}
              className="cpd-monitor-panel__primary"
            >
              Continue to monitor →
            </button>
          </>
        )}
        {step === "monitor" && (
          <>
            <button
              type="button"
              onClick={() => setStep(existing && existing.scrape_cadence !== "none" ? "monitor" : "backfill")}
              disabled={saving || (existing != null && existing.scrape_cadence !== "none")}
            >
              ← Back
            </button>
            {existing && (
              <button
                type="button"
                onClick={stopMonitoring}
                disabled={saving}
                className="cpd-monitor-panel__danger"
              >
                Stop monitoring
              </button>
            )}
            <button
              type="button"
              onClick={save}
              disabled={saving}
              className="cpd-monitor-panel__primary"
            >
              {saving ? "Saving…" : existing ? "Save changes" : "Start monitoring"}
            </button>
          </>
        )}
      </div>
    </MonitorDrawer>
  );
}

// ── Wizard step indicator ────────────────────────────────────────


type Step = "scan" | "backfill" | "monitor";

function WizardStepIndicator({
  current,
  onJump,
}: {
  current: Step;
  onJump: (s: Step) => void;
}) {
  const steps: Array<{ key: Step; label: string }> = [
    { key: "scan", label: "Scan" },
    { key: "backfill", label: "Backfill" },
    { key: "monitor", label: "Monitor" },
  ];
  return (
    <ol className="cpd-wizard-steps" aria-label="Configuration steps">
      {steps.map((s, i) => {
        const isCurrent = s.key === current;
        return (
          <li key={s.key} className={`cpd-wizard-step ${isCurrent ? "cpd-wizard-step--current" : ""}`}>
            <button
              type="button"
              onClick={() => onJump(s.key)}
              aria-current={isCurrent ? "step" : undefined}
              className="cpd-wizard-step__btn"
            >
              <span className="cpd-wizard-step__num">{i + 1}</span>
              <span className="cpd-wizard-step__label">{s.label}</span>
            </button>
          </li>
        );
      })}
    </ol>
  );
}

// ── Step 1: Scan (multi-platform preflight) ──────────────────────


function ScanStep({
  politicianId,
  politicianName,
  estimate,
  onPreflightDone,
}: {
  politicianId: string;
  politicianName: string;
  estimate: ScrapeCostEstimate | null;
  onPreflightDone: () => void;
}) {
  const [selected, setSelected] = useState<Set<ScrapePlatform>>(new Set());
  const [perPlatform, setPerPlatform] = useState<Record<string, OneShotState>>({});
  const [submitting, setSubmitting] = useState(false);

  function toggle(p: ScrapePlatform) {
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(p)) next.delete(p);
      else next.add(p);
      return next;
    });
  }

  const selectedCost = Array.from(selected).reduce((acc, p) => {
    return acc + (estimate?.per_platform[p]?.preflight_credits ?? 0);
  }, 0);

  async function runScan() {
    if (submitting || selected.size === 0) return;
    setSubmitting(true);
    for (const platform of ALL_PLATFORMS) {
      if (!selected.has(platform)) continue;
      setPerPlatform(prev => ({ ...prev, [platform]: { kind: "confirming" } }));
      try {
        const res = await userFetch<{ job_id: string }>("/me/scrape-jobs", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            politician_id: politicianId,
            platform,
            kind: "preflight",
          }),
        });
        notifyJobStarted();
        setPerPlatform(prev => ({
          ...prev,
          [platform]: { kind: "running", jobId: res.job_id, sinceMs: Date.now() },
        }));
      } catch (e: unknown) {
        const err = e as { message?: string };
        const msg = typeof err?.message === "string" ? err.message : "scan failed";
        setPerPlatform(prev => ({ ...prev, [platform]: { kind: "error", message: msg } }));
      }
    }
    setSubmitting(false);
  }

  return (
    <div className="cpd-wizard-body">
      <h4 className="cpd-wizard-body__title">Scan {politicianName}'s social accounts</h4>
      <p className="cpd-monitor-panel__hint">
        First, probe each platform to learn the total post count. This drives the cost
        for the backfill (next step) and right-sizes the monitoring cadence. Bluesky
        and Mastodon scans are free; Twitter and Instagram are 1 credit each.
      </p>
      <ul className="cpd-wizard-scan">
        {ALL_PLATFORMS.map(p => {
          const meta = estimate?.per_platform[p];
          const cached = meta?.lifetime_post_count;
          const cost = meta?.preflight_credits ?? 0;
          const state = perPlatform[p];
          return (
            <li key={p} className="cpd-wizard-scan__row">
              <label className="cpd-wizard-scan__platform">
                <input
                  type="checkbox"
                  checked={selected.has(p)}
                  disabled={state?.kind === "running"}
                  onChange={() => toggle(p)}
                />
                <span className="cpd-wizard-scan__name">{p}</span>
              </label>
              <span className="cpd-wizard-scan__meta">
                {state?.kind === "running" && (
                  <ScanRowPoll
                    platform={p}
                    jobId={state.jobId}
                    onDone={() => {
                      setPerPlatform(prev => ({ ...prev, [p]: { kind: "idle" } }));
                      onPreflightDone();
                    }}
                  />
                )}
                {state?.kind === "error" && (
                  <span className="cpd-monitor-panel__backfill-err">{state.message.slice(0, 40)}</span>
                )}
                {(!state || state.kind === "idle") && (
                  cached != null
                    ? <span className="cpd-wizard-scan__cached">✓ {cached.toLocaleString()} posts</span>
                    : <span className="cpd-wizard-scan__cost">{cost === 0 ? "free" : `${cost} cr`}</span>
                )}
              </span>
            </li>
          );
        })}
      </ul>
      <div className="cpd-wizard-scan__action">
        <button
          type="button"
          onClick={runScan}
          disabled={submitting || selected.size === 0}
          className="cpd-monitor-panel__secondary"
        >
          {submitting
            ? "Scanning…"
            : selected.size === 0
              ? "Select platforms to scan"
              : selectedCost === 0
                ? `Run scan (free)`
                : `Run scan (${selectedCost} cr)`}
        </button>
      </div>
    </div>
  );
}

function ScanRowPoll({
  platform,
  jobId,
  onDone,
}: {
  platform: string;
  jobId: string;
  onDone: () => void;
}) {
  const job = useScrapeJobPoll(jobId);
  useEffect(() => {
    if (job && (job.status === "succeeded" || job.status === "failed")) {
      onDone();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job?.status, job?.id]);
  void platform;
  return <span className="cpd-monitor-panel__backfill-running">{job?.status ?? "queued"}…</span>;
}

// ── Step 2: Backfill (multi-platform archive) ────────────────────


function BackfillStep({
  politicianId,
  estimate,
  onPreflightDone,
}: {
  politicianId: string;
  estimate: ScrapeCostEstimate | null;
  onPreflightDone: () => void;
}) {
  return (
    <div className="cpd-wizard-body">
      <h4 className="cpd-wizard-body__title">Sponsor backfill</h4>
      <p className="cpd-monitor-panel__hint">
        Pull the full post history for any platform you've scanned. One-shot purchase;
        the captured posts download as CSV/JSON from your /account/monitoring once complete.
        Skip this step if you only want forward-looking monitoring.
      </p>
      {estimate ? (
        <MultiPlatformBackfillTable
          politicianId={politicianId}
          estimate={estimate}
          dollar={(c: number) => `$${(c * 0.10).toFixed(2)}`}
          onPreflightDone={onPreflightDone}
        />
      ) : (
        <div className="cpd-monitor-panel__cost-status">Loading cost estimates…</div>
      )}
    </div>
  );
}

// ── Step 3: Monitor (recurring scrapes + email digests) ──────────


function MonitorStep({
  politicianName,
  alertCadence,
  setAlertCadence,
  platforms,
  togglePlatform,
  scrapeCadence,
  setScrapeCadence,
  estimate,
  attributionEnabled,
  setAttributionEnabled,
  attributionHandle,
  setAttributionHandle,
  attributionUrl,
  setAttributionUrl,
}: {
  politicianName: string;
  alertCadence: "none" | "daily" | "weekly";
  setAlertCadence: (v: "none" | "daily" | "weekly") => void;
  platforms: ScrapePlatform[];
  togglePlatform: (p: ScrapePlatform) => void;
  scrapeCadence: "none" | "weekly" | "monthly" | "quarterly";
  setScrapeCadence: (v: "none" | "weekly" | "monthly" | "quarterly") => void;
  estimate: ScrapeCostEstimate | null;
  attributionEnabled: boolean;
  setAttributionEnabled: (v: boolean) => void;
  attributionHandle: string;
  setAttributionHandle: (v: string) => void;
  attributionUrl: string;
  setAttributionUrl: (v: string) => void;
}) {
  const scrapingActive = platforms.length > 0 && scrapeCadence !== "none";
  const selectedPerRun = platforms.reduce(
    (acc, p) => acc + (estimate?.per_platform[p]?.monitoring_credits_per_run ?? 0),
    0
  );
  const runsPerMonth = scrapeCadence === "weekly" ? 4 : scrapeCadence === "monthly" ? 1 : scrapeCadence === "quarterly" ? 1 / 3 : 0;
  const monthlyEst = Math.round(selectedPerRun * runsPerMonth * 10) / 10;

  return (
    <div className="cpd-wizard-body">
      <h4 className="cpd-wizard-body__title">Set up monitoring</h4>

      <fieldset className="cpd-monitor-panel__section">
        <legend>Email digests (free)</legend>
        <p className="cpd-monitor-panel__hint">
          New speeches by {politicianName} sent to your inbox.
        </p>
        <label className="cpd-monitor-panel__radio">
          <input type="radio" name="alert_cadence" value="none"
            checked={alertCadence === "none"} onChange={() => setAlertCadence("none")} />
          Off
        </label>
        <label className="cpd-monitor-panel__radio">
          <input type="radio" name="alert_cadence" value="daily"
            checked={alertCadence === "daily"} onChange={() => setAlertCadence("daily")} />
          Daily
        </label>
        <label className="cpd-monitor-panel__radio">
          <input type="radio" name="alert_cadence" value="weekly"
            checked={alertCadence === "weekly"} onChange={() => setAlertCadence("weekly")} />
          Weekly
        </label>
      </fieldset>

      <fieldset className="cpd-monitor-panel__section">
        <legend>Social-content monitoring (paid)</legend>
        <p className="cpd-monitor-panel__hint">
          Pull recent posts on a schedule. Public on the politician's profile;
          attribution defaults to anonymous.
        </p>
        <div className="cpd-monitor-panel__platforms">
          {ALL_PLATFORMS.map(p => (
            <label key={p} className="cpd-monitor-panel__platform">
              <input type="checkbox"
                checked={platforms.includes(p)}
                onChange={() => togglePlatform(p)} />
              {p}
              {estimate?.per_platform[p] && (
                <span className="cpd-monitor-panel__platform-meta">
                  {" · "}
                  {estimate.per_platform[p].monitoring_credits_per_run} cr / refresh
                </span>
              )}
            </label>
          ))}
        </div>
        {platforms.length > 0 && (
          <>
            <div className="cpd-monitor-panel__cadence">
              <span>Cadence:</span>
              {SCRAPE_CADENCES.map(c => (
                <label key={c} className="cpd-monitor-panel__radio">
                  <input type="radio" name="scrape_cadence" value={c}
                    checked={scrapeCadence === c} onChange={() => setScrapeCadence(c)} />
                  {c}
                </label>
              ))}
            </div>
            {scrapingActive && (
              <div className="cpd-monitor-panel__cost">
                <div>
                  <strong>Monitoring:</strong>{" "}
                  {selectedPerRun} credits per refresh (${(selectedPerRun * 0.10).toFixed(2)}) ·{" "}
                  {monthlyEst} credits / month (~${(monthlyEst * 0.10).toFixed(2)})
                </div>
              </div>
            )}
            <div className="cpd-monitor-panel__attribution">
              <label className="cpd-monitor-panel__radio">
                <input type="checkbox"
                  checked={attributionEnabled}
                  onChange={e => setAttributionEnabled(e.target.checked)} />
                Show me as the funder of these scrapes on{" "}
                <strong>{politicianName}</strong>'s public profile
              </label>
              {attributionEnabled && (
                <>
                  <input type="text"
                    value={attributionHandle}
                    onChange={e => setAttributionHandle(e.target.value)}
                    placeholder="@yourhandle or display name"
                    maxLength={100}
                    className="cpd-monitor-panel__attribution-input" />
                  <input type="url"
                    value={attributionUrl}
                    onChange={e => setAttributionUrl(e.target.value)}
                    placeholder="Optional: https://your-site.example.com"
                    maxLength={500}
                    className="cpd-monitor-panel__attribution-input" />
                </>
              )}
              <p className="cpd-monitor-panel__hint">
                {attributionEnabled
                  ? "Public posts show \"Funded by …\" with the handle you entered. URL turns the handle into a link."
                  : "Off (default). Your name stays private."}
              </p>
            </div>
          </>
        )}
      </fieldset>
    </div>
  );
}

// ── Drawer chrome ─────────────────────────────────────────────────


/**
 * Right-side drawer that hosts the monitoring config form. Replaces
 * the pre-v5 absolutely-positioned popover, which collapsed badly past
 * ~150px of vertical content. The drawer lives at viewport level
 * (position: fixed), so it doesn't push or overlap page content; it
 * closes via Escape, backdrop click, or the explicit Close button.
 *
 * Mobile (<640px) the drawer goes full-screen; same component, the
 * CSS handles the breakpoint via @media. No portal — `position:
 * fixed` is enough to escape the parent's stacking context.
 */
function MonitorDrawer({
  politicianName,
  onClose,
  children,
}: {
  politicianName: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  // Esc-to-close + lock body scroll while open. Mirrors the standard
  // dialog interaction model (HTML <dialog> element conventions
  // without taking the polyfill dependency).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = previousOverflow;
    };
  }, [onClose]);

  return (
    <>
      <div className="cpd-monitor-drawer-backdrop" onClick={onClose} />
      <aside
        className="cpd-monitor-drawer"
        role="dialog"
        aria-modal="true"
        aria-label={`Configure monitoring for ${politicianName}`}
      >
        <button
          type="button"
          className="cpd-monitor-drawer__close"
          aria-label="Close monitoring configuration"
          onClick={onClose}
        >
          ✕
        </button>
        <div className="cpd-monitor-drawer__body">
          {children}
        </div>
      </aside>
    </>
  );
}

// ── Cost preview ──────────────────────────────────────────────────


function CostPreview({
  estimate,
  loading,
  active,
  politicianId,
  onPreflightDone,
}: {
  estimate: ScrapeCostEstimate | null;
  loading: boolean;
  active: boolean;
  politicianId: string;
  onPreflightDone: () => void;
}) {
  const perRun = estimate?.monitoring.credits_per_run ?? 0;
  const perMonth = estimate?.monitoring.total_per_month ?? 0;
  const dollar = useMemo(() => (credits: number) => `$${(credits * 0.10).toFixed(2)}`, []);

  if (loading) return <div className="cpd-monitor-panel__cost">Calculating cost…</div>;
  if (!estimate) return null;

  return (
    <div className="cpd-monitor-panel__cost">
      <div>
        <strong>{active ? "Monitoring" : "Estimate"}:</strong>{" "}
        {perRun} credits per refresh ({dollar(perRun)}) ·{" "}
        {Math.round(perMonth * 10) / 10} credits / month (~{dollar(Math.round(perMonth * 100) / 100)})
      </div>
      {/* v4: always render the multi-platform backfill table when any
          platform is selected. The table handles its own known-vs-unknown
          per-row state and exposes the preflight button inline for the
          unknown rows. */}
      <MultiPlatformBackfillTable
        politicianId={politicianId}
        estimate={estimate}
        dollar={dollar}
        onPreflightDone={onPreflightDone}
      />
    </div>
  );
}

// ── Archive + preflight one-shot actions ─────────────────────────


type OneShotState =
  | { kind: "idle" }
  | { kind: "confirming" }
  | { kind: "running"; jobId: string; sinceMs: number }
  | { kind: "done"; job: ScrapeJob }
  | { kind: "error"; message: string };

/**
 * Poll a single scrape job until its status leaves "queued" / "running".
 * Caps at ~60 seconds — the worker daemon polls every 60s so a typical
 * one-shot completes inside the first half of that window.
 */
function useScrapeJobPoll(jobId: string | null) {
  const [job, setJob] = useState<ScrapeJob | null>(null);

  useEffect(() => {
    if (!jobId) return;
    let cancelled = false;
    let tries = 0;
    let timer: ReturnType<typeof setTimeout> | null = null;

    async function tick() {
      try {
        const next = await userFetch<ScrapeJob>(`/me/scrape-jobs/${jobId}`);
        if (cancelled) return;
        setJob(next);
        if (next.status === "succeeded" || next.status === "failed") return;
      } catch {
        // Transient — keep trying until the timeout.
      }
      tries += 1;
      if (cancelled || tries > 60) return;
      timer = setTimeout(tick, 2000);
    }

    void tick();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [jobId]);

  return job;
}

/**
 * Multi-platform backfill sponsor panel. Shows one row per platform
 * (Twitter / Bluesky / Instagram / Mastodon) with lifetime count +
 * archive credits + dollars + a checkbox. Unknown sizes get a
 * per-row "Run profile preview" button (1-credit preflight) that
 * populates the row once finished. "Sponsor backfill" loops over
 * selected rows and POSTs one archive scrape_job per platform; each
 * polls independently for status.
 *
 * Replaces v3's single-platform ArchivePurchaseRow (v4, 2026-05-12).
 */
function MultiPlatformBackfillTable({
  politicianId,
  estimate,
  dollar,
  onPreflightDone,
}: {
  politicianId: string;
  estimate: ScrapeCostEstimate;
  dollar: (n: number) => string;
  onPreflightDone: () => void;
}) {
  // Default: every known-size platform pre-selected.
  const knownPlatforms = estimate.platforms.filter(
    p => estimate.per_platform[p]?.archive_known_size
  );
  const [selected, setSelected] = useState<Set<ScrapePlatform>>(
    new Set(knownPlatforms)
  );
  // Per-platform sponsorship status — null = idle, otherwise the
  // job-id we kicked off (running) or a final state.
  const [perPlatform, setPerPlatform] = useState<
    Record<string, OneShotState>
  >({});
  const [submitting, setSubmitting] = useState(false);
  const [globalError, setGlobalError] = useState<string | null>(null);

  function toggle(p: ScrapePlatform) {
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(p)) next.delete(p);
      else next.add(p);
      return next;
    });
  }

  const selectedCost = estimate.platforms.reduce((acc, p) => {
    if (!selected.has(p)) return acc;
    return acc + (estimate.per_platform[p]?.archive_credits ?? 0);
  }, 0);

  async function sponsorBackfill() {
    if (submitting || selected.size === 0) return;
    setSubmitting(true);
    setGlobalError(null);
    for (const platform of estimate.platforms) {
      if (!selected.has(platform)) continue;
      if (!estimate.per_platform[platform]?.archive_known_size) continue;
      setPerPlatform(prev => ({ ...prev, [platform]: { kind: "confirming" } }));
      try {
        const res = await userFetch<{ job_id: string }>("/me/scrape-jobs", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            politician_id: politicianId,
            platform,
            kind: "archive",
          }),
        });
        notifyJobStarted();
        setPerPlatform(prev => ({
          ...prev,
          [platform]: { kind: "running", jobId: res.job_id, sinceMs: Date.now() },
        }));
      } catch (e: unknown) {
        const err = e as { message?: string };
        const msg = typeof err?.message === "string" ? err.message : "submit failed";
        setPerPlatform(prev => ({
          ...prev,
          [platform]: { kind: "error", message: msg },
        }));
      }
    }
    setSubmitting(false);
  }

  return (
    <div className="cpd-monitor-panel__archive">
      <div className="cpd-monitor-panel__backfill-head">
        <strong>Sponsor backfill</strong>{" "}
        <span className="cpd-monitor-panel__hint cpd-monitor-panel__hint--inline">
          one-shot, full history; download as CSV/JSON once complete
        </span>
      </div>
      <table className="cpd-monitor-panel__backfill">
        <tbody>
          {estimate.platforms.map(p => {
            const meta = estimate.per_platform[p];
            const known = meta?.archive_known_size ?? false;
            const lifetime = meta?.lifetime_post_count;
            const credits = meta?.archive_credits ?? 0;
            const state = perPlatform[p];
            return (
              <tr key={p}>
                <td>
                  <label className="cpd-monitor-panel__backfill-row">
                    <input
                      type="checkbox"
                      checked={selected.has(p) && known}
                      disabled={!known || state?.kind === "running"}
                      onChange={() => toggle(p)}
                    />
                    <span className="cpd-monitor-panel__backfill-platform">{p}</span>
                  </label>
                </td>
                <td className="cpd-monitor-panel__backfill-count">
                  {known
                    ? `${lifetime!.toLocaleString()} posts`
                    : <em>profile not probed</em>}
                </td>
                <td className="cpd-monitor-panel__backfill-cost">
                  {known
                    ? `${credits} cr (${dollar(credits)})`
                    : "—"}
                </td>
                <td className="cpd-monitor-panel__backfill-status">
                  {state?.kind === "running" && (
                    <BackfillRowPoll
                      platform={p}
                      jobId={state.jobId}
                      onDone={(job) => setPerPlatform(prev => ({
                        ...prev,
                        [p]: { kind: "done", job },
                      }))}
                    />
                  )}
                  {state?.kind === "done" && state.job.status === "succeeded" && (
                    <span className="cpd-monitor-panel__backfill-ok">
                      ✓ {state.job.result_count ?? 0} posts
                    </span>
                  )}
                  {state?.kind === "done" && state.job.status === "failed" && (
                    <span className="cpd-monitor-panel__backfill-err"
                          title={state.job.error ?? ""}>failed</span>
                  )}
                  {state?.kind === "error" && (
                    <span className="cpd-monitor-panel__backfill-err">
                      {state.message.slice(0, 40)}
                    </span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
        <tfoot>
          <tr>
            <td colSpan={2}><strong>Selected total</strong></td>
            <td className="cpd-monitor-panel__backfill-cost">
              <strong>{selectedCost} cr ({dollar(selectedCost)})</strong>
            </td>
            <td />
          </tr>
        </tfoot>
      </table>
      <button
        type="button"
        onClick={sponsorBackfill}
        disabled={submitting || selected.size === 0}
        className="cpd-monitor-panel__secondary"
      >
        {submitting ? "Submitting…" : `Sponsor backfill (${selectedCost} cr)`}
      </button>
      {globalError && (
        <div className="cpd-monitor-panel__error">{globalError}</div>
      )}
      {/* Per-platform preflight buttons for unknown sizes — clicking
          fires a 1-credit preflight scrape; on completion we bump
          the parent's refresh tick to re-fetch the cost estimate
          so this row's size lights up. */}
      {estimate.platforms.some(p => !estimate.per_platform[p]?.archive_known_size) && (
        <PreflightRunRow
          politicianId={politicianId}
          estimate={estimate}
          dollar={dollar}
          onDone={onPreflightDone}
        />
      )}
    </div>
  );
}

/**
 * Per-row job poll helper. Used inside MultiPlatformBackfillTable
 * because each row needs its own poll lifecycle (multiple jobs
 * running in parallel). Renders a status line + drives a parent
 * callback on completion.
 */
function BackfillRowPoll({
  platform,
  jobId,
  onDone,
}: {
  platform: string;
  jobId: string;
  onDone: (job: ScrapeJob) => void;
}) {
  const job = useScrapeJobPoll(jobId);
  useEffect(() => {
    if (job && (job.status === "succeeded" || job.status === "failed")) {
      onDone(job);
    }
    // onDone is fresh each render; we only want to react to job-state
    // changes so we intentionally omit it from deps.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job?.status, job?.id]);

  return (
    <span className="cpd-monitor-panel__backfill-running">
      {job?.status ?? "queued"}…
    </span>
  );
}

function PreflightRunRow({
  politicianId,
  estimate,
  dollar,
  onDone,
}: {
  politicianId: string;
  estimate: ScrapeCostEstimate;
  dollar: (n: number) => string;
  onDone: () => void;
}) {
  const [state, setState] = useState<OneShotState>({ kind: "idle" });
  const activeJobId = state.kind === "running" ? state.jobId : null;
  const polled = useScrapeJobPoll(activeJobId);

  useEffect(() => {
    if (polled && (polled.status === "succeeded" || polled.status === "failed")) {
      setState({ kind: "done", job: polled });
      if (polled.status === "succeeded") {
        // Refresh the cost estimate so the archive line lights up
        // now that lifetime_post_count is cached.
        setTimeout(onDone, 500);
      }
    }
  }, [polled, onDone]);

  // Cost = sum of preflight_credits across platforms that aren't already
  // probed. For v1 we just send one preflight per platform sequentially.
  const target = estimate.platforms.find(
    p => !estimate.per_platform[p]?.archive_known_size
  ) ?? estimate.platforms[0];
  const cost = estimate.per_platform[target]?.preflight_credits ?? 1;

  async function runPreflight() {
    if (state.kind === "confirming") return;
    setState({ kind: "confirming" });
    try {
      const res = await userFetch<{ job_id: string }>("/me/scrape-jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          politician_id: politicianId,
          platform: target,
          kind: "preflight",
        }),
      });
      notifyJobStarted();
      setState({ kind: "running", jobId: res.job_id, sinceMs: Date.now() });
    } catch (e: unknown) {
      const err = e as { message?: string } & Record<string, unknown>;
      const msg = typeof err?.message === "string" ? err.message : "Preflight failed";
      setState({ kind: "error", message: msg });
    }
  }

  return (
    <div className="cpd-monitor-panel__archive cpd-monitor-panel__archive--unknown">
      <div>
        Archive cost unknown for <strong>{target}</strong>. Run a profile preview to learn
        total post count ({cost} credit{cost === 1 ? "" : "s"} — {dollar(cost)}).
      </div>
      {state.kind === "idle" && (
        <button type="button" className="cpd-monitor-panel__secondary" onClick={runPreflight}>
          Run profile preview
        </button>
      )}
      {state.kind === "confirming" && (
        <div className="cpd-monitor-panel__cost-status">Submitting…</div>
      )}
      {state.kind === "running" && (
        <div className="cpd-monitor-panel__cost-status">
          Probing… (status: {polled?.status ?? "queued"})
        </div>
      )}
      {state.kind === "done" && state.job.status === "failed" && (
        <div className="cpd-monitor-panel__error">
          Preview failed: {state.job.error?.slice(0, 160) ?? "unknown error"}
        </div>
      )}
      {state.kind === "error" && (
        <div className="cpd-monitor-panel__error">{state.message}</div>
      )}
    </div>
  );
}
