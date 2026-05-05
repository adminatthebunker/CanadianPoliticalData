import { useAdminFetch } from "../../hooks/useAdminFetch";
import { useDocumentTitle } from "../../hooks/useDocumentTitle";
import { Sparkline } from "../../components/Sparkline";
import type {
  UsageSnapshot,
  UsageTimeseries,
  SlowSearchesResponse,
} from "../../types/admin";
import "../../styles/admin.css";

function fmtMs(value: number | string | null | undefined): string {
  if (value == null) return "—";
  const n = typeof value === "string" ? Number(value) : value;
  if (!Number.isFinite(n)) return "—";
  if (n < 1) return `${n.toFixed(2)} ms`;
  if (n < 1000) return `${Math.round(n)} ms`;
  return `${(n / 1000).toFixed(1)} s`;
}

function fmtBytes(mb: number | null | undefined): string {
  if (mb == null) return "—";
  if (mb < 1024) return `${mb} MB`;
  return `${(mb / 1024).toFixed(2)} GB`;
}

function fmtAge(ts: string | null | undefined): string {
  if (!ts) return "—";
  const sec = Math.max(0, (Date.now() - new Date(ts).getTime()) / 1000);
  if (sec < 60) return `${Math.floor(sec)}s ago`;
  if (sec < 3600) return `${Math.floor(sec / 60)}m ago`;
  return `${Math.floor(sec / 3600)}h ago`;
}

function VramGauge({ used, total }: { used: number; total: number }) {
  const pct = total > 0 ? Math.min(100, (used / total) * 100) : 0;
  const tone = pct >= 95 ? "danger" : pct >= 80 ? "warn" : "ok";
  return (
    <div
      className={`admin__usage-gauge admin__usage-gauge--${tone}`}
      role="meter"
      aria-valuenow={Math.round(pct)}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={`VRAM ${pct.toFixed(1)}%`}
      title={`${used} / ${total} MB`}
    >
      <div className="admin__usage-gauge-fill" style={{ width: `${pct}%` }} />
      <span className="admin__usage-gauge-label">{pct.toFixed(1)}%</span>
    </div>
  );
}

export default function AdminUsage() {
  useDocumentTitle("Admin · Usage");
  const snap = useAdminFetch<UsageSnapshot>("/usage/snapshot", { pollMs: 5000 });

  const vramSeries = useAdminFetch<UsageTimeseries>(
    "/usage/timeseries?metric=vram_pct&minutes=60",
    { pollMs: 30000 },
  );
  const gpuUtilSeries = useAdminFetch<UsageTimeseries>(
    "/usage/timeseries?metric=gpu_util_pct&minutes=60",
    { pollMs: 30000 },
  );
  const teiP95Series = useAdminFetch<UsageTimeseries>(
    "/usage/timeseries?metric=tei_p95_ms&minutes=60",
    { pollMs: 30000 },
  );
  const searchP95Series = useAdminFetch<UsageTimeseries>(
    "/usage/timeseries?metric=search_p95_ms&minutes=60",
    { pollMs: 30000 },
  );
  const searchCountSeries = useAdminFetch<UsageTimeseries>(
    "/usage/timeseries?metric=search_count&minutes=60",
    { pollMs: 30000 },
  );

  const slow = useAdminFetch<SlowSearchesResponse>(
    "/usage/slow-searches?minutes=1440&limit=20",
    { pollMs: 30000 },
  );

  if (snap.error) {
    return (
      <div className="admin__error" role="alert">
        Failed to load usage: {snap.error.message}
      </div>
    );
  }
  if (snap.loading && !snap.data) {
    return <p className="admin__empty">Loading usage…</p>;
  }
  if (!snap.data) return null;

  const { gpu, tei, search } = snap.data;

  return (
    <div className="admin__content">
      <section className="admin__section">
        <h3>Live</h3>
        <div className="admin__stats-grid">
          <div className="admin__stat">
            <div className="admin__stat-label">VRAM</div>
            {gpu ? (
              <>
                <div className="admin__stat-value">
                  {fmtBytes(gpu.mem_used_mb)}
                  <span className="admin__stat-sub-inline">
                    {" / "}
                    {fmtBytes(gpu.mem_total_mb)}
                  </span>
                </div>
                <VramGauge used={gpu.mem_used_mb} total={gpu.mem_total_mb} />
                <div className="admin__stat-sub">
                  sample {fmtAge(gpu.sampled_at)}
                  {gpu.temperature_c != null && ` · ${gpu.temperature_c}°C`}
                  {gpu.power_w != null && ` · ${Number(gpu.power_w).toFixed(1)} W`}
                </div>
              </>
            ) : (
              <div className="admin__muted">no samples yet</div>
            )}
          </div>

          <div className="admin__stat">
            <div className="admin__stat-label">GPU util</div>
            <div className="admin__stat-value">
              {gpu ? `${gpu.util_gpu_pct}%` : "—"}
            </div>
            <Sparkline
              values={gpuUtilSeries.data?.points.map(p => p.v) ?? []}
              max={100}
              emptyLabel="warming up…"
            />
          </div>

          <div className="admin__stat">
            <div className="admin__stat-label">TEI queue</div>
            <div className="admin__stat-value">
              {tei?.queue_size ?? "—"}
            </div>
            <div className="admin__stat-sub">
              p50 {fmtMs(tei?.request_duration_p50_ms)} · p95{" "}
              {fmtMs(tei?.request_duration_p95_ms)}
            </div>
          </div>

          <div className="admin__stat">
            <div className="admin__stat-label">Searches (60m)</div>
            <div className="admin__stat-value">{search.searches_60m}</div>
            <div className="admin__stat-sub">
              {search.searches_5m} in last 5m · {search.searches_24h} in 24h
              {search.errors_60m > 0 && (
                <>
                  {" · "}
                  <span className="admin__error-inline">
                    {search.errors_60m} 5xx
                  </span>
                </>
              )}
            </div>
          </div>

          <div className="admin__stat">
            <div className="admin__stat-label">Search latency (60m)</div>
            <div className="admin__stat-value">
              {fmtMs(search.p95_60m)}
              <span className="admin__stat-sub-inline"> p95</span>
            </div>
            <div className="admin__stat-sub">
              p50 {fmtMs(search.p50_60m)}
            </div>
          </div>
        </div>
      </section>

      <section className="admin__section">
        <h3>Last hour</h3>
        <div className="admin__stats-grid">
          <div className="admin__stat">
            <div className="admin__stat-label">VRAM %</div>
            <Sparkline
              values={vramSeries.data?.points.map(p => p.v) ?? []}
              max={100}
              emptyLabel="warming up…"
            />
            <div className="admin__stat-sub">0–100%</div>
          </div>
          <div className="admin__stat">
            <div className="admin__stat-label">TEI p95 latency</div>
            <Sparkline
              values={teiP95Series.data?.points.map(p => p.v) ?? []}
              emptyLabel="no TEI traffic"
            />
            <div className="admin__stat-sub">scaled to peak</div>
          </div>
          <div className="admin__stat">
            <div className="admin__stat-label">Search p95</div>
            <Sparkline
              values={searchP95Series.data?.points.map(p => p.v) ?? []}
              emptyLabel="no searches yet"
            />
            <div className="admin__stat-sub">scaled to peak</div>
          </div>
          <div className="admin__stat">
            <div className="admin__stat-label">Search count</div>
            <Sparkline
              values={searchCountSeries.data?.points.map(p => p.v) ?? []}
              emptyLabel="no searches yet"
            />
            <div className="admin__stat-sub">per-minute bucket</div>
          </div>
        </div>
      </section>

      <section className="admin__section">
        <h3>Slowest searches (24h)</h3>
        {slow.loading && !slow.data ? (
          <p className="admin__empty">Loading…</p>
        ) : !slow.data?.rows.length ? (
          <p className="admin__empty">No searches in the last 24h yet.</p>
        ) : (
          <div className="admin__table-wrap">
            <table className="admin__table">
              <thead>
                <tr>
                  <th>When</th>
                  <th>Endpoint</th>
                  <th style={{ textAlign: "right" }}>Total</th>
                  <th style={{ textAlign: "right" }}>TEI</th>
                  <th style={{ textAlign: "right" }}>SQL</th>
                  <th style={{ textAlign: "right" }}>Results</th>
                  <th>Shape</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {slow.data.rows.map((r, i) => (
                  <tr key={`${r.created_at}-${i}`}>
                    <td className="admin__muted">{fmtAge(r.created_at)}</td>
                    <td>
                      <code>{r.endpoint}</code>
                    </td>
                    <td style={{ textAlign: "right" }}>{fmtMs(r.total_ms)}</td>
                    <td style={{ textAlign: "right" }}>{fmtMs(r.tei_ms)}</td>
                    <td style={{ textAlign: "right" }}>{fmtMs(r.sql_ms)}</td>
                    <td style={{ textAlign: "right" }}>
                      {r.result_count ?? "—"}
                    </td>
                    <td className="admin__muted" style={{ fontSize: ".78rem" }}>
                      {[
                        r.was_anchor_query ? "anchor" : null,
                        r.has_filters ? "filtered" : null,
                        r.cached_embedding ? "cached-embed" : null,
                        r.was_authenticated ? "authed" : null,
                      ]
                        .filter(Boolean)
                        .join(" · ") || "—"}
                    </td>
                    <td>
                      <span
                        className={`admin__pill admin__pill--${
                          r.status_code >= 500
                            ? "running"
                            : r.status_code >= 400
                              ? "queued"
                              : "ok"
                        }`}
                      >
                        {r.status_code}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="admin__section">
        <p className="admin__muted" style={{ fontSize: ".8rem" }}>
          Samples written by <code>gpu-sampler</code> (30s) and inline search
          telemetry. No raw query text is stored.
        </p>
      </section>
    </div>
  );
}
