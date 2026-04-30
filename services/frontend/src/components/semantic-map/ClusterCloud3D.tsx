import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { Html, Line, OrbitControls, Stars } from "@react-three/drei";
import * as THREE from "three";
import type { ClusterRow, PointRow } from "../../hooks/useSemanticMap";

// 3D R3F renderer. Same input shape as ClusterCloud2D — only the
// renderer differs. OrbitControls give the user finger-orbit on touch
// and click-drag on desktop. Camera animates to fit the visible
// clusters whenever the cluster set changes (drilldown / breadcrumb
// up).

const COLOR_PALETTE = [
  "#ff6b6b", "#ffa94d", "#ffd43b", "#a9e34b", "#69db7c",
  "#38d9a9", "#3bc9db", "#4dabf7", "#748ffc", "#9775fa",
  "#da77f2", "#f783ac", "#fa5252", "#fd7e14", "#fcc419",
  "#94d82d", "#40c057", "#20c997", "#15aabf", "#339af0",
];
// Golden-ratio hue stride spreads sequential cluster IDs across the
// colour wheel so neighbouring clusters (which are often spatially
// close in UMAP space at L3) get maximally distinct colours instead of
// adjacent palette entries.
function colorFor(id: number): string {
  const phi = 0.6180339887498949;
  const hue = ((id * phi) % 1) * 360;
  const sat = 70 + ((id * 13) % 20); // 70–90%
  const lit = 58 + ((id * 7) % 12);  // 58–70%
  return `hsl(${hue.toFixed(1)}, ${sat}%, ${lit}%)`;
}

// Per-LEVEL cube-root extents. Computing range globally (across all 4
// levels) collapses the natural size hierarchy because L1's max and L4's
// max are both ~600k members for our current run (the giant procedural
// cluster). Computing range per-level keeps each level normalized within
// its own population, then we apply a per-level multiplier band so L1
// spheres are inherently bigger than L4 spheres — which is what makes
// LOD-zoom work (finer-grained levels are below the visibility floor at
// default zoom and only reveal as the camera closes in).
interface RootRange {
  min: number;
  max: number;
}
type RootRangeByLevel = Record<number, RootRange>;
function computeRootRangesByLevel(clusters: ClusterRow[]): RootRangeByLevel {
  const out: RootRangeByLevel = {};
  for (const c of clusters) {
    const r = Math.cbrt(Math.max(1, c.member_count));
    const cur = out[c.level];
    if (!cur) {
      out[c.level] = { min: r, max: r };
    } else {
      if (r < cur.min) cur.min = r;
      if (r > cur.max) cur.max = r;
    }
  }
  return out;
}

// Per-level visible radius bands, in baseRadius units. The bands don't
// overlap by design: L1's smallest (3.0) is bigger than L2's largest
// (2.8), so at default L1-fit zoom L2 spheres are below the apparent-
// pixel floor and get hidden. As the camera closes in on a region, L1
// grows past LOD_SPHERE_MAX_PX and L2 enters the visible band. Same
// pattern cascades to L3 and L4.
const LEVEL_RADIUS_BANDS: Record<number, [number, number]> = {
  1: [4.5, 11.0],
  2: [1.8, 4.0],
  3: [0.9, 1.6],
  4: [0.35, 0.75],
};

// Per-level cap on simultaneously-rendered clusters. Even with LOD
// hiding under-sized spheres, a level whose clusters are spatially
// packed (UMAP knots — most of L1 lives in one English-language blob)
// can put 100+ same-size spheres in the visible band at once, which
// reads as visual noise. Top-N by member_count keeps the default scene
// legible; the long tail surfaces only as you zoom into its region.
const LEVEL_RENDER_CAP: Record<number, number> = {
  1: 15,
  2: 60,
  3: 140,
  4: 320,
};

function clusterRadius(
  cluster: ClusterRow, baseRadius: number, ranges: RootRangeByLevel,
): number {
  const range = ranges[cluster.level];
  const band = LEVEL_RADIUS_BANDS[cluster.level];
  if (!range || !band) return baseRadius;
  const myRoot = Math.cbrt(Math.max(1, cluster.member_count));
  const denom = range.max - range.min;
  const tLinear = denom > 1e-9 ? (myRoot - range.min) / denom : 0.5;
  // sqrt curve gives smaller-half clusters more visual presence in
  // skewed scenes where one giant pulls range.max far above the median.
  const t = Math.sqrt(Math.max(0, Math.min(1, tLinear)));
  const [minMult, maxMult] = band;
  return baseRadius * (minMult + t * (maxMult - minMult));
}

// K-nearest-neighbours by 3D UMAP centroid distance — a fast client-side
// proxy for cosine similarity in original embedding space. UMAP is
// designed to preserve local neighbourhood structure, so close-in-3D ≈
// semantically related. Returns an array of [srcId, dstId, similarity]
// edges, where similarity is in (0, 1] inverse to distance (1 = same
// point). Each edge is undirected and emitted once (src.id < dst.id).
function computeClusterEdges(
  clusters: ClusterRow[],
  k: number,
): Array<{ src: ClusterRow; dst: ClusterRow; similarity: number }> {
  const valid = clusters.filter(
    (c) => c.centroid_x != null && c.centroid_y != null && c.centroid_z != null,
  );
  if (valid.length < 2) return [];
  const seen = new Set<string>();
  const edges: Array<{ src: ClusterRow; dst: ClusterRow; similarity: number }> = [];
  // Compute pairwise distances; for each cluster, keep top-K closest.
  for (const a of valid) {
    const distances: Array<{ b: ClusterRow; d: number }> = [];
    for (const b of valid) {
      if (a.id === b.id) continue;
      const dx = (a.centroid_x! - b.centroid_x!);
      const dy = (a.centroid_y! - b.centroid_y!);
      const dz = (a.centroid_z! - b.centroid_z!);
      distances.push({ b, d: Math.sqrt(dx * dx + dy * dy + dz * dz) });
    }
    distances.sort((p, q) => p.d - q.d);
    const top = distances.slice(0, Math.min(k, distances.length));
    if (top.length === 0) continue;
    const maxD = top[top.length - 1].d || 1;
    for (const { b, d } of top) {
      const key = a.id < b.id ? `${a.id}-${b.id}` : `${b.id}-${a.id}`;
      if (seen.has(key)) continue;
      seen.add(key);
      // Map distance → (0, 1] similarity. Closest neighbour ≈ 1, K-th
      // neighbour ≈ 0.3, so the closest connections render strongest.
      const similarity = Math.max(0.3, 1 - d / (maxD * 1.4));
      edges.push({ src: a, dst: b, similarity });
    }
  }
  return edges;
}

// Uniform multiplier on cluster centroid positions (NOT radii). UMAP
// tends to pack semantically similar topics tightly; spreading the
// centroids without resizing the spheres exaggerates the gaps for
// legibility while preserving relative distances. Single source of
// truth — every read of centroid_{x,y,z} in this file goes through
// `spread(...)`.
//
// Why 6.5: balances breathing room between adjacent L1 spheres in the
// English-language UMAP knot against the camera fit-distance — every
// extra unit of spread pushes the camera further out, shrinking the
// apparent sphere size in default-zoom view. The starfield dot layer
// fills the "empty" space at higher spreads so the zoomed-out view
// reads as a galaxy of topics rather than a sparse cloud.
const CLUSTER_SPREAD = 6.5;
function spread(v: number): number {
  return v * CLUSTER_SPREAD;
}

// Per-level relaxation: how much empty space (in baseRadius units)
// to insist on between adjacent sphere surfaces. UMAP packs
// semantically similar clusters tightly, so without an explicit
// push-apart pass L1 spheres in dense topical knots end up kissing
// at every zoom level no matter how big CLUSTER_SPREAD is. The
// relaxation runs only between same-level pairs so finer levels
// stay nested inside their parents' regions.
const LEVEL_PADDING_MULT: Record<number, number> = {
  1: 1.6,
  2: 0.8,
  3: 0.4,
  4: 0.2,
};
const RELAX_ITERATIONS = 40;

// Force-directed relaxation: returns adjusted-centroid clusters where
// same-level spheres no longer overlap. The math runs in spread-space
// (post-CLUSTER_SPREAD), then divides the result back through so
// downstream callers can keep using spread() unchanged. O(N²) per
// level per iteration, fine for our N ≤ 4400 clusters.
function relaxOverlaps(
  clusters: ClusterRow[],
  baseRadius: number,
  rootRanges: RootRangeByLevel,
): ClusterRow[] {
  const valid = clusters.filter(
    (c) => c.centroid_x != null && c.centroid_y != null && c.centroid_z != null,
  );
  if (valid.length < 2) return clusters;

  // Initialise positions in spread space.
  const pos = new Map<number, [number, number, number]>();
  const rad = new Map<number, number>();
  const byLevel = new Map<number, ClusterRow[]>();
  for (const c of valid) {
    pos.set(c.id, [
      spread(c.centroid_x!), spread(c.centroid_y!), spread(c.centroid_z!),
    ]);
    rad.set(c.id, clusterRadius(c, baseRadius, rootRanges));
    const arr = byLevel.get(c.level) ?? [];
    arr.push(c);
    byLevel.set(c.level, arr);
  }

  for (let iter = 0; iter < RELAX_ITERATIONS; iter++) {
    for (const [level, levelClusters] of byLevel) {
      const padding = (LEVEL_PADDING_MULT[level] ?? 0.5) * baseRadius;
      const n = levelClusters.length;
      for (let i = 0; i < n; i++) {
        const ci = levelClusters[i];
        const pi = pos.get(ci.id)!;
        const ri = rad.get(ci.id)!;
        for (let j = i + 1; j < n; j++) {
          const cj = levelClusters[j];
          const pj = pos.get(cj.id)!;
          const rj = rad.get(cj.id)!;
          const dx = pj[0] - pi[0];
          const dy = pj[1] - pi[1];
          const dz = pj[2] - pi[2];
          const d2 = dx * dx + dy * dy + dz * dz;
          const minDist = ri + rj + padding;
          if (d2 >= minDist * minDist) continue;
          const d = Math.sqrt(d2) || 1e-6;
          const overlap = (minDist - d) * 0.5;
          const nx = dx / d, ny = dy / d, nz = dz / d;
          pi[0] -= nx * overlap; pi[1] -= ny * overlap; pi[2] -= nz * overlap;
          pj[0] += nx * overlap; pj[1] += ny * overlap; pj[2] += nz * overlap;
        }
      }
    }
  }

  // Write displacements back as raw centroids (divided by CLUSTER_SPREAD)
  // so spread() in downstream code reproduces the relaxed positions.
  return clusters.map((c) => {
    const p = pos.get(c.id);
    if (!p) return c;
    return {
      ...c,
      centroid_x: p[0] / CLUSTER_SPREAD,
      centroid_y: p[1] / CLUSTER_SPREAD,
      centroid_z: p[2] / CLUSTER_SPREAD,
    };
  });
}

interface Props {
  clusters: ClusterRow[];
  points?: PointRow[];
  onClusterClick: (c: ClusterRow) => void;
  hoveredId: number | null;
  onHover: (id: number | null) => void;
  // Fires when the user clicks empty canvas space (no sphere
  // intersected). The page uses this to step out of focus mode when
  // a focused cluster is active — gives a tap-anywhere-to-exit gesture
  // alongside the breadcrumb back button.
  onBackgroundClick?: () => void;
  // Incrementing counter — when it changes, the camera re-snaps to fit
  // the current cluster set. Lets a "Reset view" button rescue users
  // who've orbited into deep space.
  resetSignal?: number;
}

interface ClusterMeshProps {
  cluster: ClusterRow;
  baseRadius: number;
  rootRanges: RootRangeByLevel;
  hovered: boolean;
  dimmed: boolean;
  drawHalo: boolean;
  showLabel: boolean;
  onClick: (c: ClusterRow) => void;
  onHover: (id: number | null) => void;
}

function ClusterMesh({
  cluster, baseRadius, rootRanges, hovered, dimmed, drawHalo, showLabel, onClick, onHover,
}: ClusterMeshProps) {
  if (cluster.centroid_x == null || cluster.centroid_y == null || cluster.centroid_z == null) {
    return null;
  }
  const r = clusterRadius(cluster, baseRadius, rootRanges);
  const filteredRatio = cluster.member_count > 0
    ? cluster.member_count_filtered / cluster.member_count
    : 0;
  // Hover-focus mode: when *some* cluster is hovered, dim all the
  // others so the active one pops out of the cloud. This is the main
  // tool for distinguishing clusters in dense L3 views where 30+ blobs
  // pack the same volume.
  const baseOpacity = 0.4 + 0.55 * Math.min(1, filteredRatio);
  const opacity = dimmed ? baseOpacity * 0.22 : baseOpacity;
  const scale = hovered ? 1.12 : 1.0;
  const color = colorFor(cluster.id);

  return (
    <group
      position={[spread(cluster.centroid_x), spread(cluster.centroid_y), spread(cluster.centroid_z)]}
      scale={scale}
    >
      <mesh
        onClick={(e) => {
          e.stopPropagation();
          onClick(cluster);
        }}
        onPointerOver={(e) => {
          e.stopPropagation();
          onHover(cluster.id);
        }}
        onPointerOut={() => onHover(null)}
      >
        <sphereGeometry args={[r, 48, 32]} />
        <meshPhysicalMaterial
          color={color}
          transparent
          opacity={opacity}
          roughness={0.35}
          metalness={0.1}
          clearcoat={0.6}
          clearcoatRoughness={0.25}
          emissive={color}
          emissiveIntensity={hovered ? 0.6 : dimmed ? 0.04 : 0.18}
        />
      </mesh>
      {/* Halo: in sparse scenes (≤12 clusters) every cluster gets one;
          in dense scenes the halo blends neighbours into a glow blob,
          so we draw it only for the hovered cluster as a "this is the
          one" cue. */}
      {(drawHalo || hovered) && !dimmed && (
        <mesh>
          <sphereGeometry args={[r * (hovered ? 1.16 : 1.09), 32, 24]} />
          <meshBasicMaterial
            color={hovered ? "#ffffff" : color}
            transparent
            opacity={hovered ? 0.28 : 0.08}
            side={THREE.BackSide}
            depthWrite={false}
          />
        </mesh>
      )}
      {/* Subtle dark outline ring — gives non-hovered clusters a
          defined edge against their neighbours. Skipped on hover so
          the cluster reads as a clean glossy sphere. */}
      {!hovered && (
        <mesh>
          <sphereGeometry args={[r * 1.001, 36, 24]} />
          <meshBasicMaterial
            color="#0f172a"
            transparent
            opacity={dimmed ? 0.08 : 0.18}
            wireframe
            depthWrite={false}
          />
        </mesh>
      )}
      {showLabel && (
        <Html
          position={[0, r * 1.18, 0]}
          center
          zIndexRange={[100, 0]}
          style={{ pointerEvents: "none", textAlign: "center" }}
        >
          <div
            className="semantic-map__cluster-label"
            style={{ opacity: dimmed ? 0.45 : 1 }}
          >
            <div className="semantic-map__cluster-label-title">
              {cluster.label.length > 40 ? `${cluster.label.slice(0, 38)}…` : cluster.label}
            </div>
            <div className="semantic-map__cluster-label-count">
              {cluster.member_count.toLocaleString()} chunks
            </div>
          </div>
        </Html>
      )}
      {hovered && !showLabel && (
        <Html
          position={[0, r * 1.18, 0]}
          center
          zIndexRange={[200, 100]}
          style={{ pointerEvents: "none", textAlign: "center" }}
        >
          <div className="semantic-map__cluster-label semantic-map__cluster-label--hover">
            <div className="semantic-map__cluster-label-title">
              {cluster.label.length > 40 ? `${cluster.label.slice(0, 38)}…` : cluster.label}
            </div>
            <div className="semantic-map__cluster-label-count">
              {cluster.member_count.toLocaleString()} chunks
            </div>
          </div>
        </Html>
      )}
      {hovered && (
        <Html
          position={[0, -r * 1.18, 0]}
          center
          zIndexRange={[200, 100]}
          style={{ pointerEvents: "none" }}
        >
          <div className="semantic-map__tooltip">
            {cluster.member_count_filtered !== cluster.member_count
              ? `${cluster.member_count_filtered.toLocaleString()} of ${cluster.member_count.toLocaleString()} match filters`
              : "Click to drill in"}
          </div>
        </Html>
      )}
    </group>
  );
}

interface EdgesLayerProps {
  edges: Array<{ src: ClusterRow; dst: ClusterRow; similarity: number }>;
  hoveredId: number | null;
}

function EdgesLayer({ edges, hoveredId }: EdgesLayerProps) {
  // Render each edge as a single drei <Line>. Edges incident to the
  // hovered cluster pop bright; the rest fade so they read as "context"
  // rather than competing with the active cluster.
  return (
    <group>
      {edges.map(({ src, dst, similarity }) => {
        const incidentToHover =
          hoveredId != null && (src.id === hoveredId || dst.id === hoveredId);
        const someoneHovered = hoveredId != null;
        const baseAlpha = 0.18 + 0.45 * similarity;
        const opacity = incidentToHover
          ? 0.85
          : someoneHovered
          ? baseAlpha * 0.25
          : baseAlpha;
        return (
          <Line
            key={`${src.id}-${dst.id}`}
            points={[
              [spread(src.centroid_x!), spread(src.centroid_y!), spread(src.centroid_z!)],
              [spread(dst.centroid_x!), spread(dst.centroid_y!), spread(dst.centroid_z!)],
            ]}
            color={incidentToHover ? "#ffffff" : "#94a3b8"}
            lineWidth={incidentToHover ? 1.6 : 0.8}
            transparent
            opacity={opacity}
            depthWrite={false}
          />
        );
      })}
    </group>
  );
}

interface PointsLayerProps {
  points: PointRow[];
  baseRadius: number;
}

function PointsLayer({ points, baseRadius }: PointsLayerProps) {
  // Use InstancedMesh for thousands of small spheres — one draw call
  // instead of N. Each instance shares the same geometry/material;
  // we only set per-instance position via the matrix.
  const meshRef = useRef<THREE.InstancedMesh>(null);
  const dummy = useMemo(() => new THREE.Object3D(), []);
  useEffect(() => {
    if (!meshRef.current) return;
    points.forEach((p, i) => {
      dummy.position.set(spread(p.x), spread(p.y), spread(p.z));
      dummy.updateMatrix();
      meshRef.current!.setMatrixAt(i, dummy.matrix);
    });
    meshRef.current.instanceMatrix.needsUpdate = true;
  }, [points, dummy]);
  return (
    <instancedMesh ref={meshRef} args={[undefined, undefined, points.length]}>
      <sphereGeometry args={[baseRadius * 0.16, 10, 8]} />
      <meshStandardMaterial
        color="#7dd3fc"
        emissive="#38bdf8"
        emissiveIntensity={0.4}
        transparent
        opacity={0.7}
      />
    </instancedMesh>
  );
}

interface ClusterDotsLayerProps {
  dots: ClusterRow[];
  baseRadius: number;
}

// Renders the "galaxy of topics" backdrop — every cluster whose
// apparent size is too small for a full mesh sphere but big enough to
// contribute a visible point. Each instance gets a per-cluster colour
// so the backdrop reads as a meaningfully-coloured field rather than a
// uniform haze. One draw call regardless of how many dots are present.
function ClusterDotsLayer({ dots, baseRadius }: ClusterDotsLayerProps) {
  const meshRef = useRef<THREE.InstancedMesh>(null);
  const dummy = useMemo(() => new THREE.Object3D(), []);
  const colorObj = useMemo(() => new THREE.Color(), []);
  useEffect(() => {
    const mesh = meshRef.current;
    if (!mesh) return;
    dots.forEach((c, i) => {
      if (c.centroid_x == null || c.centroid_y == null || c.centroid_z == null) return;
      dummy.position.set(spread(c.centroid_x), spread(c.centroid_y), spread(c.centroid_z));
      dummy.updateMatrix();
      mesh.setMatrixAt(i, dummy.matrix);
      colorObj.set(colorFor(c.id));
      mesh.setColorAt(i, colorObj);
    });
    mesh.instanceMatrix.needsUpdate = true;
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
  }, [dots, dummy, colorObj]);
  if (dots.length === 0) return null;
  return (
    <instancedMesh
      ref={meshRef}
      args={[undefined, undefined, dots.length]}
      // key forces a remount when the dot count changes — InstancedMesh
      // pre-allocates instance buffers, so adding instances after mount
      // requires a new mesh.
      key={dots.length}
    >
      <sphereGeometry args={[baseRadius * 0.32, 8, 6]} />
      <meshBasicMaterial
        transparent
        opacity={0.55}
        toneMapped={false}
      />
    </instancedMesh>
  );
}

interface CameraFitterProps {
  clusters: ClusterRow[];
  points?: PointRow[];
  baseRadius: number;
  rootRanges: RootRangeByLevel;
  resetSignal: number;
}

// Smoothly interpolate the camera so it frames the current data each
// time it changes. Without this, drilling into a cluster leaves the
// camera at the old global zoom and the user can't see the children.
//
// Framing is FOV-aware and accounts for both the cluster centroid bbox
// AND each cluster's render radius — so the camera never crops a sphere
// because it framed only the centroid points. We also pad for the
// horizontal axis when the canvas is wider than tall.
interface OrbitLikeControls {
  target: THREE.Vector3;
  update: () => void;
  addEventListener: (event: string, listener: () => void) => void;
  removeEventListener: (event: string, listener: () => void) => void;
}

function CameraFitter({ clusters, points, baseRadius, rootRanges, resetSignal }: CameraFitterProps) {
  const { camera, controls, size } = useThree() as unknown as {
    camera: THREE.PerspectiveCamera;
    controls: OrbitLikeControls | null;
    size: { width: number; height: number };
  };
  const targetRef = useRef<{ center: THREE.Vector3; dist: number }>({
    center: new THREE.Vector3(),
    dist: 10,
  });
  const initRef = useRef(false);
  // Lerp is event-driven, not continuous. We set transitioning=true
  // when the cluster set changes (drilldown, breadcrumb, filter), and
  // useFrame only lerps while it's true. Once the camera is close
  // enough OR the user grabs the OrbitControls, we stop lerping so
  // their zoom/pan/orbit isn't stolen on the next frame.
  const transitioningRef = useRef(false);

  useEffect(() => {
    let xMin = Infinity, xMax = -Infinity;
    let yMin = Infinity, yMax = -Infinity;
    let zMin = Infinity, zMax = -Infinity;
    let any = false;
    // Frame to L1 only on initial mount — the broad-topic landmarks set
    // the "starting altitude" for the LOD-zoom flow. L2-L4 are spatially
    // contained within L1's bbox anyway (UMAP coordinates are shared
    // across levels), so a tighter L1 fit means each scroll-zoom step
    // reveals real new structure instead of just shrinking distant dots.
    const fitClusters = clusters.filter((c) => c.level === 1);
    const targetSet = fitClusters.length > 0 ? fitClusters : clusters;
    for (const c of targetSet) {
      if (c.centroid_x == null || c.centroid_y == null || c.centroid_z == null) continue;
      const r = clusterRadius(c, baseRadius, rootRanges);
      const cx = spread(c.centroid_x);
      const cy = spread(c.centroid_y);
      const cz = spread(c.centroid_z);
      xMin = Math.min(xMin, cx - r); xMax = Math.max(xMax, cx + r);
      yMin = Math.min(yMin, cy - r); yMax = Math.max(yMax, cy + r);
      zMin = Math.min(zMin, cz - r); zMax = Math.max(zMax, cz + r);
      any = true;
    }
    for (const p of points ?? []) {
      xMin = Math.min(xMin, spread(p.x)); xMax = Math.max(xMax, spread(p.x));
      yMin = Math.min(yMin, spread(p.y)); yMax = Math.max(yMax, spread(p.y));
      zMin = Math.min(zMin, spread(p.z)); zMax = Math.max(zMax, spread(p.z));
      any = true;
    }
    if (!any) return;
    const cx = (xMin + xMax) / 2;
    const cy = (yMin + yMax) / 2;
    const cz = (zMin + zMax) / 2;
    const halfX = Math.max(0.4, (xMax - xMin) / 2);
    const halfY = Math.max(0.4, (yMax - yMin) / 2);
    const halfZ = Math.max(0.4, (zMax - zMin) / 2);
    // FOV-aware fit assuming the camera looks roughly along its own
    // forward axis at the centre. For a perspective camera with vertical
    // FOV θ and aspect a, the minimum distance that contains a bbox of
    // half-extents (hx, hy, hz) is: max(hy / tan(θ/2), hx / (a tan(θ/2)))
    // plus hz so the near corner doesn't end up behind the camera.
    const vfov = (camera.fov * Math.PI) / 180;
    const aspect = size.width > 0 && size.height > 0 ? size.width / size.height : 1;
    const tanHalfV = Math.tan(vfov / 2);
    const distY = halfY / tanHalfV;
    const distX = halfX / (aspect * tanHalfV);
    // 1.15 padding so spheres don't kiss the viewport edges; +halfZ so
    // the closest sphere face still clears the near plane on rotation.
    const dist = Math.max(distY, distX) * 1.15 + halfZ;
    const center = new THREE.Vector3(cx, cy, cz);
    targetRef.current = { center, dist };
    // Snap on first fit. After that, kick off a lerp transition so
    // drilldown / breadcrumb feel smooth instead of jump-cut.
    if (!initRef.current) {
      const dir = new THREE.Vector3(0, 0.25, 1).normalize();
      camera.position.set(
        center.x + dir.x * dist,
        center.y + dir.y * dist,
        center.z + dir.z * dist,
      );
      camera.lookAt(center);
      if (controls && controls.target) {
        controls.target.copy(center);
        controls.update();
      }
      initRef.current = true;
      transitioningRef.current = false;
    } else {
      transitioningRef.current = true;
    }
  }, [clusters, points, baseRadius, rootRanges, camera, controls, size.width, size.height]);

  // Reset view: when the parent bumps `resetSignal`, snap the camera
  // back to the fit position regardless of where the user has orbited.
  // Skip the first run (resetSignal=0 on mount → no-op).
  const lastResetRef = useRef(resetSignal);
  useEffect(() => {
    if (resetSignal === lastResetRef.current) return;
    lastResetRef.current = resetSignal;
    const t = targetRef.current;
    if (!t) return;
    const dir = new THREE.Vector3(0, 0.25, 1).normalize();
    camera.position.set(
      t.center.x + dir.x * t.dist,
      t.center.y + dir.y * t.dist,
      t.center.z + dir.z * t.dist,
    );
    camera.lookAt(t.center);
    if (controls && controls.target) {
      controls.target.copy(t.center);
      controls.update();
    }
    transitioningRef.current = false;
  }, [resetSignal, camera, controls]);

  // Stop the lerp the moment the user touches OrbitControls. Without
  // this, scroll-zoom is fought by the next frame's lerp pulling the
  // camera back to `targetRef.current.dist`.
  useEffect(() => {
    if (!controls) return;
    const onStart = () => { transitioningRef.current = false; };
    controls.addEventListener("start", onStart);
    return () => controls.removeEventListener("start", onStart);
  }, [controls]);

  useFrame(() => {
    if (!transitioningRef.current) return;
    const t = targetRef.current;
    if (!t) return;
    const desired = t.center.clone().add(
      camera.position.clone().sub(t.center).normalize().multiplyScalar(t.dist),
    );
    camera.position.lerp(desired, 0.06);
    if (controls && controls.target) {
      controls.target.lerp(t.center, 0.06);
      controls.update();
    }
    // Stop the transition once we're close enough — keeps the lerp
    // from running forever (which would still steal user input).
    const posErr = camera.position.distanceTo(desired);
    const tgtErr = controls?.target ? controls.target.distanceTo(t.center) : 0;
    if (posErr < t.dist * 0.005 && tgtErr < t.dist * 0.005) {
      transitioningRef.current = false;
    }
  });
  return null;
}

// LOD render thresholds — tuned for the apparent diameter of a cluster
// sphere on screen, in pixels. There are two render bands:
//
//   sphere band [SPHERE_MIN, SPHERE_MAX]:
//     full glossy mesh sphere + edge web + label-if-big-enough.
//     The "in focus" granularity at the current zoom.
//
//   dot band [DOT_MIN, SPHERE_MIN):
//     instanced colored point. Cheap, no label, no halo. Gives the
//     zoomed-out view a "galaxy of topics" feel — every cluster's
//     centroid contributes a faint star, even though most are below
//     the legibility floor for full sphere rendering.
//
// Above SPHERE_MAX a cluster has been "zoomed past" and its children
// take over via the parent-gating logic. Below DOT_MIN it disappears.
const LOD_DOT_MIN_PX = 2;
const LOD_SPHERE_MIN_PX = 30;
const LOD_LABEL_MIN_PX = 38;
const LOD_SPHERE_MAX_PX = 280;

// Lives inside <Canvas>. Computes which cluster IDs to render and label
// based on each cluster's apparent screen diameter (a function of its
// world-space radius, distance to camera, FOV, and viewport height).
// Updates the visible / labelled sets at 5 Hz so a continuous-zoom
// gesture feels smooth without thrashing React state every frame.
interface LODControllerProps {
  clusters: ClusterRow[];
  baseRadius: number;
  rootRanges: RootRangeByLevel;
  onUpdate: (ids: {
    rendered: Set<number>;
    labelled: Set<number>;
    dotted: Set<number>;
  }) => void;
}
// Greedy screen-space label collision avoidance. Inputs:
//   - candidates sorted highest-priority-first
//   - projected: Map<id, {sx, sy}> screen-space anchor of each label
//   - labelHeightPx: max vertical extent we reserve per label (~ two
//     stacked text lines)
// Output: Set<id> of labels that fit without bbox overlap. Lower-
// priority candidates whose rect collides with an already-accepted
// one are silently dropped — this is the simplest deconfliction
// (greedy "show until something would collide", no force layout).
function pruneCollidingLabels(
  candidates: ClusterRow[],
  projected: Map<number, { sx: number; sy: number }>,
  labelHeightPx: number,
  labelGapPx: number,
): Set<number> {
  const accepted = new Set<number>();
  const acceptedRects: Array<{ x0: number; y0: number; x1: number; y1: number }> = [];
  for (const c of candidates) {
    const p = projected.get(c.id);
    if (!p) continue;
    // Width estimate: ~6.6px per character, two-line label means we
    // measure the longer line. Use the label as the rough proxy.
    const w = Math.max(70, Math.min(c.label.length, 60) * 6.6);
    const x0 = p.sx - w * 0.5;
    const x1 = p.sx + w * 0.5;
    // Label sits above the sphere; reserve labelHeightPx upward.
    const y0 = p.sy - labelHeightPx - 6;
    const y1 = p.sy - 6;
    let collides = false;
    for (const r of acceptedRects) {
      if (
        x0 < r.x1 + labelGapPx
        && x1 > r.x0 - labelGapPx
        && y0 < r.y1 + labelGapPx
        && y1 > r.y0 - labelGapPx
      ) {
        collides = true;
        break;
      }
    }
    if (collides) continue;
    accepted.add(c.id);
    acceptedRects.push({ x0, y0, x1, y1 });
  }
  return accepted;
}

function LODController({ clusters, baseRadius, rootRanges, onUpdate }: LODControllerProps) {
  const { camera, size } = useThree() as unknown as {
    camera: THREE.PerspectiveCamera;
    size: { width: number; height: number };
  };
  const lastRunRef = useRef(0);
  const prevRenderedRef = useRef<Set<number>>(new Set());
  const prevLabelledRef = useRef<Set<number>>(new Set());
  const prevDottedRef = useRef<Set<number>>(new Set());
  const projectVecRef = useRef(new THREE.Vector3());

  useFrame(() => {
    const now = performance.now();
    if (now - lastRunRef.current < 200) return;
    lastRunRef.current = now;

    // In focused mode the parent has already pre-filtered the cluster
    // set to a small subset (children of a single cluster). LOD culling
    // is the wrong move here — render everything passed in. Labels go
    // to the top-N children by member_count regardless of apparent
    // pixel size, since the children-only camera fit usually keeps
    // every sphere just under the global label threshold. The render
    // threshold (≤120) is generous enough to cover typical L1 child
    // counts (1–53 in our current run) plus some headroom.
    if (clusters.length <= 120) {
      const rendered = new Set<number>(clusters.map((c) => c.id));
      // Project labelled candidates to screen space and prune those
      // whose rects would overlap a higher-priority (more populous)
      // label already accepted.
      const projected = new Map<number, { sx: number; sy: number }>();
      const v = projectVecRef.current;
      const w = size.width || 600;
      const h = size.height || 600;
      for (const c of clusters) {
        if (c.centroid_x == null || c.centroid_y == null || c.centroid_z == null) continue;
        v.set(spread(c.centroid_x), spread(c.centroid_y), spread(c.centroid_z));
        v.project(camera);
        projected.set(c.id, {
          sx: (v.x * 0.5 + 0.5) * w,
          sy: (-v.y * 0.5 + 0.5) * h,
        });
      }
      const sortedByCount = [...clusters].sort(
        (a, b) => b.member_count - a.member_count,
      );
      const initialCap = clusters.length <= 6 ? clusters.length : 12;
      const candidates = sortedByCount.slice(0, initialCap);
      const labelled = pruneCollidingLabels(candidates, projected, 38, 6);
      if (!setEquals(rendered, prevRenderedRef.current) ||
          !setEquals(labelled, prevLabelledRef.current) ||
          prevDottedRef.current.size > 0) {
        prevRenderedRef.current = rendered;
        prevLabelledRef.current = labelled;
        prevDottedRef.current = new Set();
        onUpdate({ rendered, labelled, dotted: new Set() });
      }
      return;
    }

    const heightPx = size.height || 600;
    const fovRad = (camera.fov * Math.PI) / 180;
    const tanHalfFov = Math.tan(fovRad / 2);
    const camPos = camera.position;

    // Pass 1: compute per-cluster apparent diameter in pixels.
    // r is the world-space radius so 2r is the diameter; the perspective
    // formula maps a vertical extent of size 2r at distance dist to
    // (2r / (dist * tanHalfFov)) of the half-viewport, hence × heightPx
    // / 2 → ×heightPx for the full diameter projection.
    const apparentPx = new Map<number, number>();
    for (const c of clusters) {
      if (c.centroid_x == null || c.centroid_y == null || c.centroid_z == null) continue;
      const r = clusterRadius(c, baseRadius, rootRanges);
      const cx = spread(c.centroid_x);
      const cy = spread(c.centroid_y);
      const cz = spread(c.centroid_z);
      const dx = camPos.x - cx;
      const dy = camPos.y - cy;
      const dz = camPos.z - cz;
      const dist = Math.sqrt(dx * dx + dy * dy + dz * dz) || 0.001;
      apparentPx.set(c.id, (r * heightPx) / (dist * tanHalfFov));
    }

    // Pass 2: decide visibility with parent-gating.
    // A cluster shows iff its own apparent size sits in the sphere
    // band [SPHERE_MIN, SPHERE_MAX] AND its parent (if any) is *not*
    // in the sphere band — i.e. the parent has either been zoomed past
    // (px > SPHERE_MAX) or hasn't reached the band yet (px < SPHERE_MIN).
    // Without this gate every level renders simultaneously and the
    // scene becomes a chaotic stack of L1+L2+L3+L4 spheres at the same
    // screen point.
    const candidates: ClusterRow[] = [];
    for (const c of clusters) {
      const myPx = apparentPx.get(c.id);
      if (myPx == null) continue;
      if (myPx < LOD_SPHERE_MIN_PX || myPx > LOD_SPHERE_MAX_PX) continue;
      if (c.parent_id != null) {
        const parentPx = apparentPx.get(c.parent_id);
        if (
          parentPx != null
          && parentPx >= LOD_SPHERE_MIN_PX
          && parentPx <= LOD_SPHERE_MAX_PX
        ) {
          continue; // parent is currently visible — let it stand in for us
        }
      }
      candidates.push(c);
    }

    // Pass 3: per-level top-N cap. Even after LOD + parent-gating, a
    // dense UMAP knot can put 100+ same-size spheres in the band at
    // once. Cap each level to its render budget by member_count so the
    // headline clusters dominate the default view; tail clusters
    // appear only as the user zooms into their specific region.
    const byLevel = new Map<number, ClusterRow[]>();
    for (const c of candidates) {
      const arr = byLevel.get(c.level) ?? [];
      arr.push(c);
      byLevel.set(c.level, arr);
    }
    const rendered = new Set<number>();
    const labelCandidates: ClusterRow[] = [];
    for (const [lvl, arr] of byLevel) {
      const cap = LEVEL_RENDER_CAP[lvl] ?? 100;
      const kept = arr.length <= cap
        ? arr
        : [...arr].sort((a, b) => b.member_count - a.member_count).slice(0, cap);
      for (const c of kept) {
        rendered.add(c.id);
        const px = apparentPx.get(c.id) ?? 0;
        if (px >= LOD_LABEL_MIN_PX) labelCandidates.push(c);
      }
    }

    // Pass 3b: screen-space label deconfliction. Project each
    // candidate label's anchor and greedily accept by member_count
    // — drop any whose rect would overlap a higher-priority label.
    // Without this, semantically clustered topics in the UMAP knot
    // (where 4-6 spheres sit at nearly identical screen coords)
    // produce stacked labels that read as a glob of overlapping
    // text.
    const projected = new Map<number, { sx: number; sy: number }>();
    const v = projectVecRef.current;
    const screenW = size.width || 600;
    const screenH = size.height || 600;
    for (const c of labelCandidates) {
      if (c.centroid_x == null || c.centroid_y == null || c.centroid_z == null) continue;
      v.set(spread(c.centroid_x), spread(c.centroid_y), spread(c.centroid_z));
      v.project(camera);
      projected.set(c.id, {
        sx: (v.x * 0.5 + 0.5) * screenW,
        sy: (-v.y * 0.5 + 0.5) * screenH,
      });
    }
    const sortedByCount = [...labelCandidates].sort(
      (a, b) => b.member_count - a.member_count,
    );
    const labelled = pruneCollidingLabels(sortedByCount, projected, 38, 6);

    // Pass 4: starfield. Every cluster whose apparent size sits below
    // the sphere floor but above LOD_DOT_MIN_PX gets rendered as a
    // tiny instanced point — the "galaxy of topics" backdrop that
    // makes the zoomed-out view feel populated rather than sparse.
    // Skip clusters already in the rendered set so a sphere doesn't
    // get a redundant dot at its centre.
    const dotted = new Set<number>();
    for (const c of clusters) {
      if (rendered.has(c.id)) continue;
      const px = apparentPx.get(c.id);
      if (px == null) continue;
      if (px >= LOD_DOT_MIN_PX && px < LOD_SPHERE_MIN_PX) dotted.add(c.id);
    }

    if (!setEquals(rendered, prevRenderedRef.current) ||
        !setEquals(labelled, prevLabelledRef.current) ||
        !setEquals(dotted, prevDottedRef.current)) {
      prevRenderedRef.current = rendered;
      prevLabelledRef.current = labelled;
      prevDottedRef.current = dotted;
      onUpdate({ rendered, labelled, dotted });
    }
  });
  return null;
}

function setEquals(a: Set<number>, b: Set<number>): boolean {
  if (a.size !== b.size) return false;
  for (const v of a) if (!b.has(v)) return false;
  return true;
}

export default function ClusterCloud3D({
  clusters: rawClusters, points, onClusterClick, hoveredId, onHover,
  onBackgroundClick, resetSignal = 0,
}: Props) {
  // Per-scene cube-root range used by clusterRadius to map members to
  // per-level visual radius bands — see LEVEL_RADIUS_BANDS / clusterRadius.
  const rootRanges = useMemo(() => computeRootRangesByLevel(rawClusters), [rawClusters]);

  // Compute a baseRadius from the cluster spread so spheres stay at a
  // legible size at any zoom level. Floor at 0.4 so 1- or 2-cluster
  // scenes (sparse smoke runs) still get visibly sized spheres. With
  // multi-level data the L1 clusters dominate the bbox, which is fine —
  // baseRadius scales with the broadest cluster set. We compute this
  // from the *raw* centroids so the radius is stable regardless of
  // the relaxation pass that follows.
  const baseRadius = useMemo(() => {
    const xs: number[] = [];
    const ys: number[] = [];
    const zs: number[] = [];
    for (const c of rawClusters) {
      if (c.centroid_x != null && c.centroid_y != null && c.centroid_z != null) {
        xs.push(c.centroid_x); ys.push(c.centroid_y); zs.push(c.centroid_z);
      }
    }
    if (xs.length === 0) return 0.4;
    const span = Math.max(
      Math.max(...xs) - Math.min(...xs),
      Math.max(...ys) - Math.min(...ys),
      Math.max(...zs) - Math.min(...zs),
    ) || 4;
    // Scale factor 0.05 keeps L1 spheres comfortably legible at the
    // ~35-unit galaxy bbox AND keeps focused-mode spheres readable
    // when the children-only bbox is much smaller (10–15 units).
    return Math.max(0.25, span * 0.05);
  }, [rawClusters]);

  // Force-directed relaxation: nudges same-level spheres apart so
  // semantically-similar clusters in UMAP knots don't visually fuse.
  // Runs once per cluster set; result is fed to all downstream
  // components so the displaced positions are the single source of
  // truth.
  const clusters = useMemo(
    () => relaxOverlaps(rawClusters, baseRadius, rootRanges),
    [rawClusters, baseRadius, rootRanges],
  );

  // LOD-driven render set + label set + starfield dot set, updated at
  // 5Hz by LODController.
  const [lod, setLod] = useState<{
    rendered: Set<number>;
    labelled: Set<number>;
    dotted: Set<number>;
  }>({
    rendered: new Set(),
    labelled: new Set(),
    dotted: new Set(),
  });
  const onLodUpdate = useCallback(
    (ids: { rendered: Set<number>; labelled: Set<number>; dotted: Set<number> }) =>
      setLod(ids),
    [],
  );

  // Materialize the dotted-cluster array for the InstancedMesh layer.
  // This is the "galaxy of topics" backdrop — every cluster too small
  // to render as a full sphere but big enough to see as a point.
  const dotClusters = useMemo(
    () => clusters.filter((c) => lod.dotted.has(c.id)),
    [clusters, lod.dotted],
  );

  // Halo helps in sparse scenes, hurts in dense ones (every cluster's
  // halo bleeds into its neighbours and the whole thing reads as a
  // glow blob). Use the LOD-rendered count, not the total — a zoomed-in
  // view with a handful of visible clusters should get halos.
  const drawHalo = lod.rendered.size <= 12;
  const someoneHovered = hoveredId != null;

  // Spider-web edges: K-nearest in UMAP centroid space, computed only
  // among currently-rendered clusters so the web reflects what's on
  // screen (not the global topology, which would be 4400 nodes).
  const edges = useMemo(() => {
    const visibleClusters = clusters.filter((c) => lod.rendered.has(c.id));
    const k = visibleClusters.length <= 12 ? 4 : visibleClusters.length <= 30 ? 3 : 2;
    return computeClusterEdges(visibleClusters, k);
  }, [clusters, lod.rendered]);

  const [ready, setReady] = useState(false);
  useEffect(() => { setReady(true); }, []);
  if (!ready) return null;

  return (
    <Canvas
      className="semantic-map__canvas"
      camera={{ position: [0, 0, 12], fov: 50, near: 0.01, far: 1000 }}
      style={{ width: "100%", height: "100%" }}
      gl={{ antialias: true, alpha: true }}
      onPointerMissed={() => onBackgroundClick?.()}
    >
      {/* Stars give the empty space depth without expensive bloom. The
          radius is large enough to sit beyond any reasonable cluster
          extent (UMAP coords are O(10s)). */}
      <Stars radius={120} depth={60} count={2000} factor={3} saturation={0} fade speed={0.4} />

      {/* Three-point lighting: warm key, cool fill, subtle rim. */}
      <ambientLight intensity={0.45} />
      <directionalLight position={[10, 12, 8]} intensity={0.9} color="#fef3c7" />
      <directionalLight position={[-12, -6, -8]} intensity={0.55} color="#7dd3fc" />
      <pointLight position={[0, 0, 20]} intensity={0.35} color="#ffffff" />

      {/* Edges first so spheres render on top. */}
      <EdgesLayer edges={edges} hoveredId={hoveredId} />

      {/* Galaxy backdrop — clusters too small to render as full
          spheres still contribute a faint coloured point so the
          zoomed-out view feels populated rather than sparse. */}
      <ClusterDotsLayer dots={dotClusters} baseRadius={baseRadius} />

      <LODController
        clusters={clusters}
        baseRadius={baseRadius}
        rootRanges={rootRanges}
        onUpdate={onLodUpdate}
      />

      {clusters.map((c) => (
        lod.rendered.has(c.id) ? (
          <ClusterMesh
            key={c.id}
            cluster={c}
            baseRadius={baseRadius}
            rootRanges={rootRanges}
            hovered={hoveredId === c.id}
            dimmed={someoneHovered && hoveredId !== c.id}
            drawHalo={drawHalo}
            showLabel={lod.labelled.has(c.id)}
            onClick={onClusterClick}
            onHover={onHover}
          />
        ) : null
      ))}

      {points && points.length > 0 && (
        <PointsLayer points={points} baseRadius={baseRadius} />
      )}

      <OrbitControls makeDefault enablePan enableZoom enableRotate dampingFactor={0.1} />
      <CameraFitter
        clusters={clusters} points={points}
        baseRadius={baseRadius} rootRanges={rootRanges}
        resetSignal={resetSignal}
      />
    </Canvas>
  );
}
