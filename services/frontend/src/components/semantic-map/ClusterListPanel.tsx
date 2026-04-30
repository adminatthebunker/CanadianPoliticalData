import { useEffect, useRef } from "react";
import type { ClusterRow } from "../../hooks/useSemanticMap";

// Indexed counterpart to the spatial map. Same data, different access
// path: every cluster currently visible on the canvas appears as a
// row with a colour swatch (same hue as the sphere) + label + chunk
// count. Hover bidirectionally syncs with the map's hoveredId, click
// drills in identically to onClusterClick.
//
// On desktop this lives as a sidebar; on mobile it stacks below the
// stage. We don't try to be a draggable bottom sheet — that's a
// follow-up if the simple stack doesn't carry its weight.

interface Props {
  clusters: ClusterRow[];
  hoveredId: number | null;
  onHover: (id: number | null) => void;
  onClusterClick: (c: ClusterRow) => void;
  heading: string;
  emptyHint?: string;
  loading?: boolean;
}

// Identical to colorFor in the renderers — keep the swatch and
// sphere colours pinned to the same hash so map ↔ list reads as one
// thing.
function colorFor(id: number): string {
  const phi = 0.6180339887498949;
  const hue = ((id * phi) % 1) * 360;
  const sat = 70 + ((id * 13) % 20);
  const lit = 58 + ((id * 7) % 12);
  return `hsl(${hue.toFixed(1)}, ${sat}%, ${lit}%)`;
}

export default function ClusterListPanel({
  clusters, hoveredId, onHover, onClusterClick, heading, emptyHint, loading,
}: Props) {
  const listRef = useRef<HTMLUListElement | null>(null);

  // When the map's hover state changes due to a sphere hover (not from
  // this panel's own mouse events), scroll the matching row into view
  // so the user can see the sync. Skip when hoveredId is set from
  // within the panel — onHover from row mouse events runs before this
  // effect on the same render, so we use a ref to detect "external"
  // updates.
  const lastSourceRef = useRef<"panel" | "external" | null>(null);
  useEffect(() => {
    if (hoveredId == null) return;
    if (lastSourceRef.current === "panel") {
      lastSourceRef.current = null;
      return;
    }
    const el = listRef.current?.querySelector<HTMLElement>(
      `[data-cluster-id="${hoveredId}"]`,
    );
    el?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [hoveredId]);

  const handleHover = (id: number | null) => {
    lastSourceRef.current = "panel";
    onHover(id);
  };

  return (
    <aside className="semantic-map__panel" aria-label="Topic list">
      <header className="semantic-map__panel-header">
        <h2 className="semantic-map__panel-heading">{heading}</h2>
        <span className="semantic-map__panel-meta">
          {clusters.length}
          {" "}
          {clusters.length === 1 ? "topic" : "topics"}
        </span>
      </header>
      {loading && (
        <div className="semantic-map__panel-empty">Loading clusters…</div>
      )}
      {!loading && clusters.length === 0 && (
        <div className="semantic-map__panel-empty">
          {emptyHint ?? "No topics here."}
        </div>
      )}
      {!loading && clusters.length > 0 && (
        <ul ref={listRef} className="semantic-map__panel-list">
          {clusters.map((c) => {
            const hovered = hoveredId === c.id;
            const truncated = c.label.length > 60
              ? `${c.label.slice(0, 58)}…`
              : c.label;
            return (
              <li key={c.id}>
                <button
                  type="button"
                  data-cluster-id={c.id}
                  className={
                    "semantic-map__panel-row" + (hovered ? " is-hovered" : "")
                  }
                  onMouseEnter={() => handleHover(c.id)}
                  onMouseLeave={() => handleHover(null)}
                  onFocus={() => handleHover(c.id)}
                  onBlur={() => handleHover(null)}
                  onClick={() => onClusterClick(c)}
                  aria-label={`${c.label} — ${c.member_count.toLocaleString()} chunks`}
                >
                  <span
                    className="semantic-map__panel-swatch"
                    style={{ backgroundColor: colorFor(c.id) }}
                    aria-hidden
                  />
                  <span className="semantic-map__panel-label" title={c.label}>
                    {truncated}
                  </span>
                  <span className="semantic-map__panel-row-count">
                    {c.member_count.toLocaleString()}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </aside>
  );
}
