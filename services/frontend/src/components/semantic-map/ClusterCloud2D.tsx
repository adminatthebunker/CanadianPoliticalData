import { useEffect, useMemo, useRef, useState } from "react";
import type { ClusterRow, PointRow } from "../../hooks/useSemanticMap";

// SVG-based 2D scatter. Same cluster topology as the 3D renderer — we
// switch only the renderer, never the data. Stable visual landmarks
// (carbon-tax cluster lives at the same screen-space coords regardless
// of zoom level / filter) make the map navigable.
//
// Filter behaviour: hide-and-fade. When the user filters, clusters with
// no surviving members fade to ~15% opacity but stay positioned, so the
// topology never jumps. Per-cluster member_count_filtered drives the
// fill opacity scale.

function colorFor(id: number): string {
  // Golden-ratio hue stride — see ClusterCloud3D for rationale.
  const phi = 0.6180339887498949;
  const hue = ((id * phi) % 1) * 360;
  const sat = 70 + ((id * 13) % 20);
  const lit = 58 + ((id * 7) % 12);
  return `hsl(${hue.toFixed(1)}, ${sat}%, ${lit}%)`;
}

// Uniform multiplier on cluster centroid positions (NOT radii). Same
// constant as the 3D renderer — keep them in sync.
const CLUSTER_SPREAD = 6.5;
function spread(v: number): number {
  return v * CLUSTER_SPREAD;
}

// Per-scene cube-root range for range-normalized radii — see
// ClusterCloud3D for rationale. Keep both renderers in sync.
interface RootRange {
  min: number;
  max: number;
}
function computeRootRange(clusters: ClusterRow[]): RootRange {
  let min = Infinity;
  let max = -Infinity;
  for (const c of clusters) {
    const r = Math.cbrt(Math.max(1, c.member_count));
    if (r < min) min = r;
    if (r > max) max = r;
  }
  if (!isFinite(min) || !isFinite(max)) return { min: 0, max: 1 };
  return { min, max };
}

const RADIUS_MIN_MULT = 1.4;
const RADIUS_MAX_MULT = 7.5;

function clusterRadius2D(
  cluster: ClusterRow, baseRadius: number, range: RootRange,
): number {
  const myRoot = Math.cbrt(Math.max(1, cluster.member_count));
  const denom = range.max - range.min;
  const tLinear = denom > 1e-9 ? (myRoot - range.min) / denom : 0.5;
  // sqrt curve — see ClusterCloud3D for rationale.
  const t = Math.sqrt(tLinear);
  return baseRadius * (RADIUS_MIN_MULT + t * (RADIUS_MAX_MULT - RADIUS_MIN_MULT));
}

// Visibility cap mirrors the 3D renderer.
const VISIBLE_CLUSTER_CAP = 30;

function topByMembers(clusters: ClusterRow[], cap: number): ClusterRow[] {
  if (clusters.length <= cap) return clusters;
  return [...clusters]
    .sort((a, b) => b.member_count - a.member_count)
    .slice(0, cap);
}

// 2D variant of the K-NN edge computation. Same shape as the 3D version
// but uses the (x2, y2) UMAP centroids.
function computeClusterEdges2D(
  clusters: ClusterRow[],
  k: number,
): Array<{ src: ClusterRow; dst: ClusterRow; similarity: number }> {
  const valid = clusters.filter(
    (c) => c.centroid_x2 != null && c.centroid_y2 != null,
  );
  if (valid.length < 2) return [];
  const seen = new Set<string>();
  const edges: Array<{ src: ClusterRow; dst: ClusterRow; similarity: number }> = [];
  for (const a of valid) {
    const distances: Array<{ b: ClusterRow; d: number }> = [];
    for (const b of valid) {
      if (a.id === b.id) continue;
      const dx = (a.centroid_x2! - b.centroid_x2!);
      const dy = (a.centroid_y2! - b.centroid_y2!);
      distances.push({ b, d: Math.sqrt(dx * dx + dy * dy) });
    }
    distances.sort((p, q) => p.d - q.d);
    const top = distances.slice(0, Math.min(k, distances.length));
    if (top.length === 0) continue;
    const maxD = top[top.length - 1].d || 1;
    for (const { b, d } of top) {
      const key = a.id < b.id ? `${a.id}-${b.id}` : `${b.id}-${a.id}`;
      if (seen.has(key)) continue;
      seen.add(key);
      const similarity = Math.max(0.3, 1 - d / (maxD * 1.4));
      edges.push({ src: a, dst: b, similarity });
    }
  }
  return edges;
}

interface Props {
  clusters: ClusterRow[];
  points?: PointRow[]; // when zoomed into an L3 cluster
  onClusterClick: (c: ClusterRow) => void;
  onPointClick?: (p: PointRow) => void;
  hoveredId: number | null;
  onHover: (id: number | null) => void;
}

export default function ClusterCloud2D({
  clusters: rawClusters, points, onClusterClick, onPointClick, hoveredId, onHover,
}: Props) {
  // Apply visibility cap before any other computation so size, viewBox,
  // and rendering all agree on the same set.
  const clusters = useMemo(
    () => topByMembers(rawClusters, VISIBLE_CLUSTER_CAP),
    [rawClusters],
  );
  const rootRange = useMemo(() => computeRootRange(clusters), [clusters]);

  const svgRef = useRef<SVGSVGElement | null>(null);
  const [size, setSize] = useState({ w: 600, h: 600 });

  // Track the parent's pixel size so the SVG fills it.
  useEffect(() => {
    const el = svgRef.current?.parentElement;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect;
        setSize({ w: Math.max(300, width), h: Math.max(300, height) });
      }
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Compute viewBox from the current data so the cloud auto-fits.
  // We include each cluster's *render radius* in the bbox (not just the
  // centroid points) so circles can't be clipped at the edges; then we
  // also expand to match the parent's aspect ratio so the cloud fills
  // the container along whichever axis the bbox is short on.
  const baseRadiusForFit = useMemo(() => {
    const xs: number[] = [];
    const ys: number[] = [];
    for (const c of clusters) {
      if (c.centroid_x2 != null && c.centroid_y2 != null) {
        xs.push(c.centroid_x2);
        ys.push(c.centroid_y2);
      }
    }
    if (xs.length === 0) return 0.4;
    const dx = (Math.max(...xs) - Math.min(...xs)) || 1;
    const dy = (Math.max(...ys) - Math.min(...ys)) || 1;
    return Math.max(0.25, Math.min(dx, dy) * 0.04);
  }, [clusters]);

  const viewBox = useMemo(() => {
    let xMin = Infinity, xMax = -Infinity;
    let yMin = Infinity, yMax = -Infinity;
    let any = false;
    for (const c of clusters) {
      if (c.centroid_x2 == null || c.centroid_y2 == null) continue;
      const r = clusterRadius2D(c, baseRadiusForFit, rootRange);
      const cx = spread(c.centroid_x2);
      const cy = spread(c.centroid_y2);
      xMin = Math.min(xMin, cx - r);
      xMax = Math.max(xMax, cx + r);
      yMin = Math.min(yMin, cy - r);
      yMax = Math.max(yMax, cy + r);
      any = true;
    }
    if (points) {
      for (const p of points) {
        xMin = Math.min(xMin, spread(p.x2)); xMax = Math.max(xMax, spread(p.x2));
        yMin = Math.min(yMin, spread(p.y2)); yMax = Math.max(yMax, spread(p.y2));
        any = true;
      }
    }
    if (!any) return { minX: -10, minY: -10, w: 20, h: 20 };
    const dx = (xMax - xMin) || 1;
    const dy = (yMax - yMin) || 1;
    const padX = dx * 0.12;
    const padY = dy * 0.12;
    let bx = xMin - padX, by = yMin - padY;
    let bw = dx + 2 * padX, bh = dy + 2 * padY;
    // Expand bbox to match container aspect ratio. Without this, a tall
    // SVG container with a wide cluster spread ends up displaying the
    // clusters in a narrow horizontal band with empty space above and
    // below.
    const containerAspect = size.w / size.h;
    const bboxAspect = bw / bh;
    if (containerAspect > bboxAspect) {
      const newW = bh * containerAspect;
      bx -= (newW - bw) / 2;
      bw = newW;
    } else {
      const newH = bw / containerAspect;
      by -= (newH - bh) / 2;
      bh = newH;
    }
    return { minX: bx, minY: by, w: bw, h: bh };
  }, [clusters, points, baseRadiusForFit, rootRange, size.w, size.h]);

  // Sphere radius scales by cube-root of member_count so a 1000x larger
  // cluster doesn't take 1000x the area. Anchored to the smallest of
  // (viewBox dim) so radii are sensible at any auto-fit.
  const baseRadius = Math.min(viewBox.w, viewBox.h) * 0.018;

  // Per-scene label budget — match the 3D renderer's caps so both
  // modes thin labels the same way as scenes get denser.
  const labelledIds = useMemo(() => {
    const sorted = [...clusters].sort((a, b) => b.member_count - a.member_count);
    const n = clusters.length;
    let cap: number;
    if (n <= 8) cap = n;
    else if (n <= 16) cap = 8;
    else cap = 6;
    return new Set(sorted.slice(0, cap).map((c) => c.id));
  }, [clusters]);
  const someoneHovered = hoveredId != null;
  const edges = useMemo(() => {
    // Same K tiering as the 3D renderer — floor at k=4 so the
    // sibling-graph stays connected even for dense focused-mode
    // scenes (53+ L2 children of a UMAP-knot L1).
    const n = clusters.length;
    const k = n <= 8 ? 7 : n <= 20 ? 6 : n <= 50 ? 5 : 4;
    return computeClusterEdges2D(clusters, k);
  }, [clusters]);

  // One radial gradient per cluster — colours are now HSL per cluster
  // ID (golden-ratio hue stride), not palette-indexed, so we generate
  // gradient defs dynamically.
  const gradientDefs = clusters.map((c) => {
    const color = colorFor(c.id);
    return (
      <radialGradient key={`g-${c.id}`} id={`sphere-grad-${c.id}`} cx="35%" cy="32%" r="75%">
        <stop offset="0%" stopColor="#ffffff" stopOpacity="0.55" />
        <stop offset="35%" stopColor={color} stopOpacity="0.95" />
        <stop offset="100%" stopColor={color} stopOpacity="0.7" />
      </radialGradient>
    );
  });
  const drawHalo = clusters.length <= 12;

  return (
    <svg
      ref={svgRef}
      className="semantic-map__svg"
      width={size.w}
      height={size.h}
      viewBox={`${viewBox.minX} ${viewBox.minY} ${viewBox.w} ${viewBox.h}`}
      preserveAspectRatio="xMidYMid meet"
    >
      <defs>
        {gradientDefs}
        <filter id="sphere-glow" x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation={baseRadius * 0.9} result="b" />
          <feMerge>
            <feMergeNode in="b" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>

      {/* Edges layer — drawn before points/spheres so they go behind. */}
      {edges.map(({ src, dst, similarity }) => {
        const incidentToHover =
          hoveredId != null && (src.id === hoveredId || dst.id === hoveredId);
        const baseAlpha = 0.18 + 0.45 * similarity;
        const opacity = incidentToHover
          ? 0.85
          : someoneHovered
          ? baseAlpha * 0.25
          : baseAlpha;
        return (
          <line
            key={`edge-${src.id}-${dst.id}`}
            x1={spread(src.centroid_x2!)}
            y1={spread(src.centroid_y2!)}
            x2={spread(dst.centroid_x2!)}
            y2={spread(dst.centroid_y2!)}
            stroke={incidentToHover ? "#ffffff" : "#94a3b8"}
            strokeOpacity={opacity}
            strokeWidth={
              incidentToHover ? baseRadius * 0.08 : baseRadius * 0.045
            }
            strokeLinecap="round"
            pointerEvents="none"
          />
        );
      })}

      {/* Points layer (only present when zoomed into an L3 cluster). */}
      {points?.map((p) => (
        <circle
          key={p.chunk_id}
          cx={spread(p.x2)} cy={spread(p.y2)}
          r={baseRadius * 0.22}
          fill="#7dd3fc"
          opacity={0.7}
          className="semantic-map__point"
          onClick={() => onPointClick?.(p)}
        />
      ))}

      {/* Cluster sphere layer — body. Sort so hovered cluster renders
          last (on top of the others). */}
      {clusters
        .slice()
        .sort((a, b) => (a.id === hoveredId ? 1 : b.id === hoveredId ? -1 : 0))
        .map((c) => {
          if (c.centroid_x2 == null || c.centroid_y2 == null) return null;
          const r = clusterRadius2D(c, baseRadius, rootRange);
          const filteredRatio = c.member_count > 0
            ? c.member_count_filtered / c.member_count
            : 0;
          const baseFill = 0.22 + 0.72 * Math.min(1, filteredRatio);
          const isHovered = hoveredId === c.id;
          const dimmed = someoneHovered && !isHovered;
          const fillOpacity = dimmed ? baseFill * 0.28 : baseFill;
          const scale = isHovered ? 1.12 : 1.0;
          const rDraw = r * scale;
          const cx = spread(c.centroid_x2);
          const cy = spread(c.centroid_y2);
          const showLabel = labelledIds.has(c.id) || isHovered;
          return (
            <g
              key={c.id}
              className="semantic-map__cluster"
              onClick={() => onClusterClick(c)}
              onMouseEnter={() => onHover(c.id)}
              onMouseLeave={() => onHover(null)}
              style={{ cursor: "pointer" }}
            >
              {drawHalo && !dimmed && (
                <circle
                  cx={cx}
                  cy={cy}
                  r={rDraw * 1.32}
                  fill={colorFor(c.id)}
                  opacity={isHovered ? 0.22 : 0.08}
                  filter="url(#sphere-glow)"
                  pointerEvents="none"
                />
              )}
              <circle
                cx={cx}
                cy={cy}
                r={rDraw}
                fill={`url(#sphere-grad-${c.id})`}
                fillOpacity={fillOpacity}
                stroke={isHovered ? "#ffffff" : "rgba(15,23,42,0.55)"}
                strokeOpacity={isHovered ? 0.95 : dimmed ? 0.25 : 0.7}
                strokeWidth={rDraw * (isHovered ? 0.06 : 0.04)}
              />
              {showLabel && (
                <g style={{ opacity: dimmed ? 0.45 : 1 }}>
                  <text
                    x={cx}
                    y={cy + rDraw + baseRadius * 0.55}
                    textAnchor="middle"
                    fill="#f8fafc"
                    fontSize={baseRadius * 0.6}
                    fontWeight={600}
                    pointerEvents="none"
                    style={{
                      paintOrder: "stroke",
                      stroke: "rgba(2,6,23,0.85)",
                      strokeWidth: baseRadius * 0.06,
                    }}
                  >
                    {c.label.length > 32 ? `${c.label.slice(0, 30)}…` : c.label}
                  </text>
                  <text
                    x={cx}
                    y={cy + rDraw + baseRadius * 1.2}
                    textAnchor="middle"
                    fill="#cbd5e1"
                    fontSize={baseRadius * 0.42}
                    pointerEvents="none"
                    style={{
                      paintOrder: "stroke",
                      stroke: "rgba(2,6,23,0.85)",
                      strokeWidth: baseRadius * 0.05,
                    }}
                  >
                    {c.member_count.toLocaleString()} chunks
                  </text>
                </g>
              )}
            </g>
          );
        })}
    </svg>
  );
}
