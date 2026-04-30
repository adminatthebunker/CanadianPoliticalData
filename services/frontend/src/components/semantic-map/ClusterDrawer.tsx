import { Link } from "react-router-dom";
import type { ClusterRow, PointRow } from "../../hooks/useSemanticMap";

// Drawer that opens when the user has selected a single cluster (any
// level) — shows the label, ranked top terms, the 15 representative
// chunks (from cluster.top_chunk_ids → not yet hydrated) plus the
// /projections/points payload for L3.
//
// We don't hydrate top_chunk_ids in v1 — that would require an extra
// /speeches/by-id endpoint. The points fetch covers the common case
// (zoomed into an L3 cluster) with full chunk metadata.

interface Props {
  cluster: ClusterRow | null;
  points: PointRow[] | null;
  pointsLoading?: boolean;
  onClose: () => void;
}

export default function ClusterDrawer({
  cluster, points, pointsLoading, onClose,
}: Props) {
  if (!cluster) return null;
  return (
    <div className="semantic-map__drawer" role="dialog" aria-label={`Cluster ${cluster.label}`}>
      <div className="semantic-map__drawer-header">
        <div>
          <div className="semantic-map__drawer-eyebrow">
            Level {cluster.level} · {cluster.member_count.toLocaleString()} chunks
            {cluster.member_count_filtered !== cluster.member_count && (
              <> · {cluster.member_count_filtered.toLocaleString()} match filter</>
            )}
          </div>
          <h2 className="semantic-map__drawer-title">{cluster.label}</h2>
        </div>
        <button
          type="button"
          className="semantic-map__drawer-close"
          onClick={onClose}
          aria-label="Close cluster details"
        >
          ×
        </button>
      </div>

      {cluster.top_terms && cluster.top_terms.length > 0 && (
        <section className="semantic-map__drawer-section">
          <h3>Top terms</h3>
          <ul className="semantic-map__drawer-terms">
            {cluster.top_terms.slice(0, 12).map((t) => (
              <li key={t.term}>
                <span className="term">{t.term}</span>
                <span className="weight">{t.weight.toFixed(3)}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="semantic-map__drawer-section">
        <h3>Representative chunks</h3>
        {pointsLoading && <p className="semantic-map__drawer-empty">Loading…</p>}
        {!pointsLoading && points && points.length === 0 && (
          <p className="semantic-map__drawer-empty">
            No matching chunks under the current filter.
          </p>
        )}
        {!pointsLoading && points && points.length > 0 && (
          <ul className="semantic-map__drawer-chunks">
            {points.slice(0, 25).map((p) => (
              <li key={p.chunk_id}>
                <Link
                  to={`/speeches/${p.speech_id}#chunk-${p.chunk_id}`}
                  className="semantic-map__chunk-link"
                >
                  <div className="semantic-map__chunk-meta">
                    {p.spoken_at?.slice(0, 10) ?? "(undated)"}
                    {p.party_at_time && (
                      <> · <span className="semantic-map__chunk-party">{p.party_at_time}</span></>
                    )}
                    {p.province_territory && p.level !== "federal" && (
                      <> · {p.province_territory}</>
                    )}
                  </div>
                  <div className="semantic-map__chunk-snippet">{p.snippet}</div>
                </Link>
              </li>
            ))}
          </ul>
        )}
        {!pointsLoading && !points && (
          <p className="semantic-map__drawer-empty">
            Click into this cluster to load matching chunks.
          </p>
        )}
      </section>
    </div>
  );
}
