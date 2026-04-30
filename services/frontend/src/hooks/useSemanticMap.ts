import { useEffect, useState } from "react";
import { fetchJson } from "../api";

// Filter shape consumed by /projections/clusters and /projections/points.
// Mirrors the subset of search.ts:baseFilterSchema that maps to spatial
// drilldown — no q, no min_similarity, no parliament/session pair (those
// are search-time concerns, not "where in topic-space am I" concerns).
export type SpeechType =
  | "floor"
  | "committee"
  | "question_period"
  | "statement"
  | "point_of_order"
  | "group";

export interface SemanticFilter {
  lang?: "en" | "fr" | "any";
  level?: "federal" | "provincial" | "municipal";
  province_territory?: string;
  party?: string;
  from?: string;
  to?: string;
  exclude_presiding?: boolean;
  speech_types?: SpeechType[];
}

export interface ClusterRow {
  id: number;
  parent_id: number | null;
  level: number;
  label: string;
  top_terms: Array<{ term: string; weight: number }> | null;
  member_count: number;
  member_count_filtered: number;
  centroid_x: number | null;
  centroid_y: number | null;
  centroid_z: number | null;
  centroid_x2: number | null;
  centroid_y2: number | null;
  top_chunk_ids: string[];
}

export interface ClustersResponse {
  run_id: string | null;
  cluster_level: number;
  parent_cluster_id: number | null;
  clusters: ClusterRow[];
  message?: string;
}

export interface PointRow {
  chunk_id: string;
  speech_id: string;
  politician_id: string | null;
  party_at_time: string | null;
  spoken_at: string | null;
  level: string | null;
  province_territory: string | null;
  x: number;
  y: number;
  z: number;
  x2: number;
  y2: number;
  snippet: string;
}

export interface PointsResponse {
  run_id: string | null;
  cluster_id: number;
  cluster_level: number;
  points: PointRow[];
}

function buildFilterParams(f: SemanticFilter): URLSearchParams {
  const p = new URLSearchParams();
  if (f.lang && f.lang !== "any") p.set("lang", f.lang);
  if (f.level) p.set("level", f.level);
  if (f.province_territory) p.set("province_territory", f.province_territory);
  if (f.party) p.set("party", f.party);
  if (f.from) p.set("from", f.from);
  if (f.to) p.set("to", f.to);
  if (f.exclude_presiding) p.set("exclude_presiding", "true");
  if (f.speech_types && f.speech_types.length > 0) {
    for (const t of f.speech_types) p.append("speech_type", t);
  }
  return p;
}

// Response shape for /projections/clusters/all — all 4 levels in one
// response. The bulk response strips top_terms / top_chunk_ids; those
// load on demand via /clusters when a user opens the drawer.
export interface AllClustersResponse {
  run_id: string | null;
  cluster_counts: { l1: number | null; l2: number | null; l3: number | null; l4: number | null } | null;
  clusters: ClusterRow[];
  message?: string;
}

export interface UseAllClustersArgs {
  filter: SemanticFilter;
  enabled?: boolean;
}

// Loads all 4 cluster levels in a single request. Backs the zoom-as-LOD
// renderer: client gates rendering by camera-distance/apparent-screen-size,
// so we want every level cached locally to avoid network round-trips on
// continuous zoom.
export function useAllClusters(args: UseAllClustersArgs) {
  const { filter, enabled = true } = args;
  const [data, setData] = useState<AllClustersResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const key = JSON.stringify({ filter, enabled });

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    const params = buildFilterParams(filter);
    setLoading(true);
    setError(null);
    fetchJson<AllClustersResponse>(`/projections/clusters/all?${params.toString()}`)
      .then((res) => {
        if (cancelled) return;
        setData(res);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  return { data, loading, error };
}

export interface UseClustersArgs {
  filter: SemanticFilter;
  level: number;
  parentClusterId: number | null;
  enabled?: boolean;
}

export function useClusters(args: UseClustersArgs) {
  const { filter, level, parentClusterId, enabled = true } = args;
  const [data, setData] = useState<ClustersResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Stable key from the inputs that actually trigger a refetch.
  const key = JSON.stringify({ filter, level, parentClusterId, enabled });

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    const params = buildFilterParams(filter);
    params.set("cluster_level", String(level));
    if (parentClusterId != null) {
      params.set("parent_cluster_id", String(parentClusterId));
    }
    setLoading(true);
    setError(null);
    fetchJson<ClustersResponse>(`/projections/clusters?${params.toString()}`)
      .then((res) => {
        if (cancelled) return;
        setData(res);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  return { data, loading, error };
}

export interface UsePointsArgs {
  filter: SemanticFilter;
  clusterLevel: number;
  clusterId: number | null;
  limit?: number;
  enabled?: boolean;
}

export function usePoints(args: UsePointsArgs) {
  const { filter, clusterLevel, clusterId, limit = 500, enabled = true } = args;
  const [data, setData] = useState<PointsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const key = JSON.stringify({ filter, clusterLevel, clusterId, limit, enabled });

  useEffect(() => {
    if (!enabled || clusterId == null) {
      setData(null);
      return;
    }
    let cancelled = false;
    const params = buildFilterParams(filter);
    params.set("cluster_level", String(clusterLevel));
    params.set("cluster_id", String(clusterId));
    params.set("limit", String(limit));
    setLoading(true);
    setError(null);
    fetchJson<PointsResponse>(`/projections/points?${params.toString()}`)
      .then((res) => {
        if (cancelled) return;
        setData(res);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  return { data, loading, error };
}
