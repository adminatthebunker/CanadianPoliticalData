import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import ClusterCloud2D from "../components/semantic-map/ClusterCloud2D";
import ClusterCloud3D from "../components/semantic-map/ClusterCloud3D";
import ClusterDrawer from "../components/semantic-map/ClusterDrawer";
import ClusterListPanel from "../components/semantic-map/ClusterListPanel";
import ModeToggle from "../components/semantic-map/ModeToggle";
import SemanticMapFilters from "../components/semantic-map/SemanticMapFilters";
import SemanticMapHints from "../components/semantic-map/SemanticMapHints";
import SemanticMapSearch from "../components/semantic-map/SemanticMapSearch";
import { useIsTouch } from "../hooks/useMediaQuery";
import {
  useAllClusters, usePoints,
  type ClusterRow, type SemanticFilter, type SpeechType,
} from "../hooks/useSemanticMap";
import "../styles/semantic-map.css";

// Render mode is part of the URL so deep-links into /semantic-map keep
// the user's chosen renderer. Default is touch-based (2D on phones,
// 3D on desktop), readable from useIsTouch().
export type ViewMode = "2d" | "3d";

const SPEECH_TYPE_VALUES = new Set<SpeechType>([
  "floor", "committee", "question_period", "statement", "point_of_order", "group",
]);

function readMode(p: URLSearchParams, fallback: ViewMode): ViewMode {
  const m = p.get("mode");
  return m === "2d" || m === "3d" ? m : fallback;
}

function readSelected(p: URLSearchParams): number | null {
  const sel = Number(p.get("selected"));
  return Number.isFinite(sel) && sel > 0 ? sel : null;
}

function readFocused(p: URLSearchParams): number | null {
  const f = Number(p.get("focused"));
  return Number.isFinite(f) && f > 0 ? f : null;
}

function readFilter(p: URLSearchParams): SemanticFilter {
  const lang = p.get("lang");
  const level = p.get("level_jur"); // distinct from cluster level
  const types = p.getAll("speech_type").filter((t): t is SpeechType =>
    SPEECH_TYPE_VALUES.has(t as SpeechType));
  return {
    lang: lang === "en" || lang === "fr" || lang === "any" ? lang : undefined,
    level: level === "federal" || level === "provincial" || level === "municipal"
      ? level
      : undefined,
    province_territory: p.get("province") ?? undefined,
    party: p.get("party") ?? undefined,
    from: p.get("from") ?? undefined,
    to: p.get("to") ?? undefined,
    exclude_presiding: p.get("exclude_presiding") === "true" ? true : undefined,
    speech_types: types.length > 0 ? types : undefined,
  };
}

function writeUrl(
  filter: SemanticFilter,
  selected: number | null,
  focused: number | null,
  mode: ViewMode,
): URLSearchParams {
  const p = new URLSearchParams();
  if (filter.lang && filter.lang !== "any") p.set("lang", filter.lang);
  if (filter.level) p.set("level_jur", filter.level);
  if (filter.province_territory) p.set("province", filter.province_territory);
  if (filter.party) p.set("party", filter.party);
  if (filter.from) p.set("from", filter.from);
  if (filter.to) p.set("to", filter.to);
  if (filter.exclude_presiding) p.set("exclude_presiding", "true");
  for (const t of filter.speech_types ?? []) p.append("speech_type", t);
  if (selected != null) p.set("selected", String(selected));
  if (focused != null) p.set("focused", String(focused));
  // Always write mode — the default depends on isTouch, so we can't
  // safely skip a particular value as "the default". Writing both 2d
  // and 3d keeps the toggle deterministic across devices.
  p.set("mode", mode);
  return p;
}

export default function SemanticMapPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const isTouch = useIsTouch();
  const defaultMode: ViewMode = isTouch ? "2d" : "3d";

  const filter = useMemo(() => readFilter(searchParams), [searchParams]);
  const selectedId = useMemo(() => readSelected(searchParams), [searchParams]);
  const focusedId = useMemo(() => readFocused(searchParams), [searchParams]);
  const mode = useMemo(() => readMode(searchParams, defaultMode), [searchParams, defaultMode]);

  // 3D feasibility: feature-detect WebGL once. If unavailable (rare —
  // antiquated browser), keep the user in 2D and disable the toggle.
  const [webglOk, setWebglOk] = useState(true);
  useEffect(() => {
    try {
      const c = document.createElement("canvas");
      const gl = c.getContext("webgl2") || c.getContext("webgl");
      setWebglOk(Boolean(gl));
    } catch {
      setWebglOk(false);
    }
  }, []);

  // ESC anywhere on the page steps out of focus mode (or closes the
  // drawer if it's open). Skipped while typing in an input so the
  // search field's own ESC handler still clears its query first.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      const ae = document.activeElement;
      if (ae && (ae.tagName === "INPUT" || ae.tagName === "TEXTAREA")) return;
      const sp = new URLSearchParams(window.location.search);
      const sel = sp.get("selected");
      const foc = sp.get("focused");
      if (sel) {
        sp.delete("selected");
        setSearchParams(sp, { replace: true });
        return;
      }
      if (foc) {
        sp.delete("focused");
        setSearchParams(sp, { replace: true });
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [setSearchParams]);
  const effectiveMode: ViewMode = webglOk ? mode : "2d";

  const setUrl = (
    nextFilter: SemanticFilter,
    nextSelected: number | null,
    nextFocused: number | null,
    nextMode: ViewMode,
  ) => {
    setSearchParams(writeUrl(nextFilter, nextSelected, nextFocused, nextMode));
  };

  const onFilterChange = (patch: Partial<SemanticFilter>) => {
    setUrl({ ...filter, ...patch }, selectedId, focusedId, mode);
  };
  const onFilterReset = () => {
    setUrl({}, selectedId, focusedId, mode);
  };
  const onModeChange = (next: ViewMode) => {
    setUrl(filter, selectedId, focusedId, next);
  };

  // Walks past singleton-only parent → child edges so a click never
  // lands on a focused view that's "just one sphere stuck in space".
  // The hierarchy was built with majority-vote-parent linkage and at
  // mcs ratios near 2× ~half of L1→L2 edges are singletons (and the
  // chain can keep going). Returns the original cluster unchanged
  // when it already branches (≥2 children) — this only kicks in for
  // dead-end navigation paths.
  const findFocusTarget = (start: ClusterRow): ClusterRow => {
    let current = start;
    // Hard cap: max chain length is the hierarchy depth (currently 4,
    // soon 5). 6 is a defensive ceiling.
    for (let i = 0; i < 6; i++) {
      if (current.level >= 5) return current;
      const children = allClusters.filter((c) => c.parent_id === current.id);
      if (children.length !== 1) return current; // 0=leaf, ≥2=branch
      current = children[0];
    }
    return current;
  };

  // Focus navigation. Tapping a cluster:
  //   - If the cluster (after auto-skipping singleton chains) has
  //     children at a deeper level → focus on it (camera flies in,
  //     scene shows only those children).
  //   - If it resolves to a leaf → open the drawer for its chunks.
  // Click on background or back button → step out of focus.
  const onClusterClick = (c: ClusterRow) => {
    const target = findFocusTarget(c);
    const targetChildren = allClusters.filter((x) => x.parent_id === target.id);
    if (target.level >= 5 || targetChildren.length === 0) {
      // Leaf — open drawer at the resolved cluster, not the click
      // origin. Parent set to target.parent_id so closing the drawer
      // returns to the deepest branching ancestor instead of all the
      // way back to where the user clicked.
      setUrl(filter, target.id, target.parent_id, mode);
      return;
    }
    setUrl(filter, null, target.id, mode);
  };
  const closeDrawer = () => {
    setUrl(filter, null, focusedId, mode);
  };
  const exitFocus = () => {
    setUrl(filter, null, null, mode);
  };
  // Background-click handler for the canvas. We only want
  // tap-to-exit-focus when the user is *in* focus mode — outside of
  // it, an empty-space tap should do nothing rather than become a
  // surprising no-op. Pinned via ref to avoid stale-closure issues
  // with the renderer's onPointerMissed listener.
  const onBackgroundClick = () => {
    if (focusedId != null) exitFocus();
  };
  const focusUp = (currentFocused: ClusterRow | null) => {
    if (!currentFocused) return;
    setUrl(filter, null, currentFocused.parent_id, mode);
  };

  // Search-to-jump: same auto-skip semantics as clicking a cluster on
  // the map. If the target's descent chain is all singletons we walk
  // past them so the user lands at a branching descendant or the
  // deepest leaf, not the search-hit's exact level.
  const onSearchJump = (c: ClusterRow) => {
    const target = findFocusTarget(c);
    const targetChildren = allClusters.filter((x) => x.parent_id === target.id);
    if (target.level >= 5 || targetChildren.length === 0) {
      setUrl(filter, target.id, target.parent_id, mode);
      return;
    }
    setUrl(filter, null, target.id, mode);
  };

  const [hoveredId, setHoveredId] = useState<number | null>(null);
  // Bumped by the "Reset view" hint button — ClusterCloud3D snaps the
  // camera back to fit when this changes.
  const [resetSignal, setResetSignal] = useState(0);

  const { data: clusterData, loading: clustersLoading, error: clusterError } =
    useAllClusters({ filter });

  const allClusters = clusterData?.clusters ?? [];

  // Focused cluster lookup (for breadcrumb + camera target). Computed
  // before clusters3D so the focus filter can use its level/centroid.
  const focusedCluster = useMemo<ClusterRow | null>(() => {
    if (focusedId == null) return null;
    return allClusters.find((c) => c.id === focusedId) ?? null;
  }, [allClusters, focusedId]);

  // Focused vs galaxy view:
  //   - Galaxy (no focus): renderer sees all 4,000+ clusters and uses
  //     LOD + dot field to populate the scene.
  //   - Focused: renderer sees only the children of the focused cluster.
  //     Massively reduces visual clutter and gives the user a clean
  //     "I'm inside this region" mental model.
  const clusters3D = useMemo(() => {
    if (focusedCluster == null) return allClusters;
    const children = allClusters.filter((c) => c.parent_id === focusedCluster.id);
    // Fallback for leaf / hierarchy gap: render the focused cluster
    // itself so the user sees something tappable rather than an empty
    // canvas. Tapping it again opens the drawer per onClusterClick.
    return children.length > 0 ? children : [focusedCluster];
  }, [allClusters, focusedCluster]);

  // 2D fallback renderer keeps a click-to-drill mental model for now,
  // so it consumes only the L1 clusters out of the all-levels payload
  // (or the focused cluster's children if the user has focused).
  const clusters2D = useMemo(() => {
    if (focusedCluster != null) {
      return allClusters.filter((c) => c.parent_id === focusedCluster.id);
    }
    return allClusters.filter((c) => c.level === 1);
  }, [allClusters, focusedCluster]);

  // List-panel cluster set — the indexed counterpart to whatever's on
  // the spatial canvas. Galaxy mode shows top-N L1 by member_count
  // (matches the renderer's L1 cap). Focused mode shows every direct
  // child of the focused cluster, sorted big → small. Cap is N=60 so
  // the list itself stays scannable; deeper exploration uses search
  // or zoom.
  const panelClusters = useMemo(() => {
    if (focusedCluster != null) {
      return allClusters
        .filter((c) => c.parent_id === focusedCluster.id)
        .sort((a, b) => b.member_count - a.member_count);
    }
    return allClusters
      .filter((c) => c.level === 1)
      .sort((a, b) => b.member_count - a.member_count)
      .slice(0, 60);
  }, [allClusters, focusedCluster]);
  const panelHeading = focusedCluster
    ? `Inside "${focusedCluster.label.length > 36
        ? focusedCluster.label.slice(0, 34) + "…"
        : focusedCluster.label}"`
    : "Top topics";

  // Selected cluster's level is needed to fetch its points (each level
  // has its own cluster_id_lN column on the projection rows).
  const selected = useMemo<ClusterRow | null>(() => {
    if (selectedId == null) return null;
    return clusterData?.clusters.find((c) => c.id === selectedId) ?? null;
  }, [clusterData, selectedId]);

  // Two situations want the points payload:
  //   1. The user opened a cluster's drawer (selected != null) — list
  //      representative chunks in the side drawer.
  //   2. The focused cluster is L5 — render its individual chunks as
  //      points in the canvas, the deepest LOD layer ("right down to
  //      the quotes themselves").
  // L5-focus takes priority since it's what the canvas renders. The
  // drawer can only open for L5 if the user has *also* selected that
  // L5 — same cluster, same hook call, no conflict.
  const pointsTarget = useMemo<ClusterRow | null>(() => {
    if (focusedCluster?.level === 5) return focusedCluster;
    return selected;
  }, [focusedCluster, selected]);
  const { data: pointsData, loading: pointsLoading } = usePoints({
    filter,
    clusterLevel: pointsTarget?.level ?? 1,
    clusterId: pointsTarget?.id ?? null,
    limit: focusedCluster?.level === 5 ? 2000 : 500,
    enabled: pointsTarget != null,
  });

  const noRun = clusterData != null && clusterData.run_id == null;
  const totalCount = clusterData?.clusters.length ?? 0;

  return (
    <div className="semantic-map">
      <header className="semantic-map__header">
        <div>
          <h1 className="semantic-map__title">Semantic explorer</h1>
          <p className="semantic-map__subtitle">
            Hansard speech-chunks projected into{" "}
            {effectiveMode === "3d" ? "3D" : "2D"} space and clustered by topic.
            {effectiveMode === "3d"
              ? " Tap a topic to explore inside it; orbit and pinch to navigate."
              : " Click a cluster to view representative speeches."}
            {" "}
            <a
              className="semantic-map__how-link"
              href="https://docs.canadianpoliticaldata.org/explore/how-it-works/"
              target="_blank"
              rel="noopener noreferrer"
            >
              How it works ↗
            </a>
          </p>
        </div>
        <div className="semantic-map__header-actions">
          <ModeToggle
            mode={effectiveMode}
            onChange={onModeChange}
            disabled3d={!webglOk}
          />
        </div>
      </header>

      <SemanticMapFilters
        filter={filter}
        onChange={onFilterChange}
        onReset={onFilterReset}
      />

      <div className="semantic-map__breadcrumbs">
        {focusedCluster ? (
          <>
            <button
              type="button"
              onClick={exitFocus}
              className="semantic-map__crumb-btn"
              aria-label="Back to all topics"
            >
              ← All topics
            </button>
            {focusedCluster.parent_id != null && (
              <button
                type="button"
                onClick={() => focusUp(focusedCluster)}
                className="semantic-map__crumb-btn"
                aria-label="Up one level"
              >
                ↑ Up one level
              </button>
            )}
            <span className="semantic-map__crumb-meta">
              <strong>{focusedCluster.label}</strong>
              {" · "}
              {focusedCluster.member_count.toLocaleString()} chunks
              {clusters3D.length > 0 &&
                ` · ${clusters3D.length} child${clusters3D.length === 1 ? "" : "ren"}`}
            </span>
          </>
        ) : (
          <span className="semantic-map__crumb-meta">
            {!clustersLoading && clusterData && (
              effectiveMode === "3d"
                ? `${totalCount.toLocaleString()} clusters across 5 levels — tap a topic to explore`
                : `${clusters2D.length.toLocaleString()} top-level topics`
            )}
          </span>
        )}
      </div>

      <div className="semantic-map__workspace">
        <div className="semantic-map__stage">
          {noRun && (
            <div className="semantic-map__empty">
              <p>
                No projection has been published yet. An admin needs to run{" "}
                <code>project-embeddings</code> and promote the run.
              </p>
              <p className="semantic-map__empty-hint">
                {clusterData?.message ?? ""}
              </p>
            </div>
          )}
          {!noRun && clusterError && (
            <div className="semantic-map__empty">
              <p>Failed to load clusters: {clusterError}</p>
            </div>
          )}
          {!noRun && !clusterError && clusterData && (
            effectiveMode === "3d" ? (
              <ClusterCloud3D
                clusters={clusters3D}
                points={pointsData?.points}
                onClusterClick={onClusterClick}
                onBackgroundClick={onBackgroundClick}
                hoveredId={hoveredId}
                onHover={setHoveredId}
                resetSignal={resetSignal}
              />
            ) : (
              <ClusterCloud2D
                clusters={clusters2D}
                points={pointsData?.points}
                onClusterClick={onClusterClick}
                hoveredId={hoveredId}
                onHover={setHoveredId}
              />
            )
          )}
          {!noRun && !clusterError && clusterData && (
            <SemanticMapHints
              mode={effectiveMode}
              level={1}
              onResetView={() => setResetSignal((n) => n + 1)}
            />
          )}
          {!noRun && !clusterError && clustersLoading && !clusterData && (
            <div className="mapview__loading" role="status" aria-live="polite">
              <span className="mapview__leaf" aria-hidden>🍁</span>
              <span className="mapview__loading-text">Loading semantic map…</span>
            </div>
          )}
        </div>
        {!noRun && !clusterError && (
          <div className="semantic-map__panel-column">
            <SemanticMapSearch
              allClusters={allClusters}
              onJump={onSearchJump}
            />
            <ClusterListPanel
              clusters={panelClusters}
              hoveredId={hoveredId}
              onHover={setHoveredId}
              onClusterClick={onClusterClick}
              heading={panelHeading}
              loading={clustersLoading}
              emptyHint={focusedCluster
                ? "This topic has no sub-topics. Tap it again to view chunks."
                : undefined}
            />
          </div>
        )}
      </div>

      {selected && (
        <ClusterDrawer
          cluster={selected}
          points={pointsData?.points ?? null}
          pointsLoading={pointsLoading}
          onClose={closeDrawer}
        />
      )}
    </div>
  );
}
