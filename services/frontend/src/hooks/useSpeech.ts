import { useEffect, useMemo, useState } from "react";
import type { SpeechSearchPolitician, SpeechSearchSession } from "./useSpeechSearch";

export interface ContextSpeech {
  id: string;
  sequence: number | null;
  spoken_at: string | null;
  speaker_name_raw: string;
  speaker_role: string | null;
  party_at_time: string | null;
  constituency_at_time: string | null;
  speech_type: string | null;
  language: string;
  text: string;
  source_url: string;
  source_anchor: string | null;
  source_system: string;
  level: string;
  province_territory: string | null;
  politician: SpeechSearchPolitician | null;
}

export interface SpeechContextResponse {
  before: ContextSpeech[];
  after: ContextSpeech[];
  has_more_before: boolean;
  has_more_after: boolean;
}

export interface SpeechContextOpts {
  before?: number;
  after?: number;
  all?: boolean;
}

export interface SpeechContextState {
  data: SpeechContextResponse | null;
  error: Error | null;
  loading: boolean;
}

export interface SpeechDetail {
  id: string;
  session_id: string;
  level: string;
  province_territory: string | null;
  speaker_name_raw: string;
  speaker_role: string | null;
  party_at_time: string | null;
  constituency_at_time: string | null;
  speech_type: string | null;
  spoken_at: string | null;
  sequence: number | null;
  language: string;
  text: string;
  word_count: number | null;
  source_system: string;
  source_url: string;
  source_anchor: string | null;
  politician: SpeechSearchPolitician | null;
  session: SpeechSearchSession | null;
}

export interface SpeechChunkSummary {
  id: string;
  chunk_index: number;
  text: string;
  char_start: number;
  char_end: number;
  language: string;
}

export interface SpeechDetailResponse {
  speech: SpeechDetail;
  chunks: SpeechChunkSummary[];
}

export interface SpeechDetailState {
  data: SpeechDetailResponse | null;
  error: Error | null;
  loading: boolean;
  notFound: boolean;
}

export function useSpeech(id: string | null): SpeechDetailState {
  const [state, setState] = useState<SpeechDetailState>({
    data: null,
    error: null,
    loading: !!id,
    notFound: false,
  });

  useEffect(() => {
    if (!id) {
      setState({ data: null, error: null, loading: false, notFound: false });
      return;
    }
    let cancelled = false;
    setState((s) => ({ ...s, loading: true, error: null, notFound: false }));

    const base = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "/api/v1";
    fetch(`${base}/speeches/${encodeURIComponent(id)}`, { headers: { Accept: "application/json" } })
      .then(async (res) => {
        if (cancelled) return;
        if (res.status === 404) {
          setState({ data: null, error: null, loading: false, notFound: true });
          return;
        }
        if (!res.ok) {
          setState({
            data: null,
            error: new Error(`${res.status} ${res.statusText}`),
            loading: false,
            notFound: false,
          });
          return;
        }
        const data = (await res.json()) as SpeechDetailResponse;
        setState({ data, error: null, loading: false, notFound: false });
      })
      .catch((err: Error) => {
        if (cancelled) return;
        setState({ data: null, error: err, loading: false, notFound: false });
      });

    return () => {
      cancelled = true;
    };
  }, [id]);

  return state;
}

// ── Anchor-chunk lookup ────────────────────────────────────────────
// Single-fetch shape used by /search's anchor banner and Map pre-push:
// chunk text + parent speech metadata in one round trip.

export interface ChunkInfo {
  chunk_id: string;
  speech_id: string;
  text: string;
  char_start: number;
  char_end: number;
  language: string;
  speaker_name_raw: string;
  party_at_time: string | null;
  spoken_at: string | null;
  level: string;
  province_territory: string | null;
  source_url: string;
  source_anchor: string | null;
  source_system: string;
  politician: SpeechSearchPolitician | null;
}

export interface ChunkInfoState {
  data: ChunkInfo | null;
  error: Error | null;
  loading: boolean;
}

export function useChunkInfo(chunkId: string | null): ChunkInfoState {
  const [state, setState] = useState<ChunkInfoState>({
    data: null,
    error: null,
    loading: !!chunkId,
  });

  useEffect(() => {
    if (!chunkId) {
      setState({ data: null, error: null, loading: false });
      return;
    }
    let cancelled = false;
    setState((s) => ({ ...s, loading: true, error: null }));
    const base = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "/api/v1";
    fetch(`${base}/search/chunks/${encodeURIComponent(chunkId)}`, {
      headers: { Accept: "application/json" },
    })
      .then(async (res) => {
        if (cancelled) return;
        if (!res.ok) {
          setState({ data: null, error: new Error(`${res.status} ${res.statusText}`), loading: false });
          return;
        }
        const j = (await res.json()) as ChunkInfo;
        setState({ data: j, error: null, loading: false });
      })
      .catch((err: Error) => {
        if (cancelled) return;
        setState({ data: null, error: err, loading: false });
      });
    return () => {
      cancelled = true;
    };
  }, [chunkId]);

  return state;
}

export interface RelatedSpeechItem {
  chunk_id: string;
  speech_id: string;
  chunk_text: string;
  char_start: number;
  char_end: number;
  similarity: number;
  spoken_at: string | null;
  speaker_name_raw: string;
  party_at_time: string | null;
  level: string;
  province_territory: string | null;
  politician: SpeechSearchPolitician | null;
}

export interface RelatedSpeechesResponse {
  items: RelatedSpeechItem[];
}

export interface RelatedSpeechesState {
  data: RelatedSpeechesResponse | null;
  error: Error | null;
  loading: boolean;
}

// ── Projection coords (semantic-map UMAP positions) ────────────────
// Backs the search Map tab so satellites are laid out at their actual
// (x2, y2) in semantic space rather than a synthetic radial ring. Returns
// an empty map when no projection run is current.

export interface ProjectionCoord {
  chunk_id: string;
  x: number;
  y: number;
  z: number;
  x2: number;
  y2: number;
  cluster_id_l3: number | null;
}

export interface ProjectionCoordsResponse {
  run_id: string | null;
  items: ProjectionCoord[];
}

export interface ProjectionCoordsState {
  data: ProjectionCoordsResponse | null;
  error: Error | null;
  loading: boolean;
}

export function useProjectionCoords(chunkIds: string[]): ProjectionCoordsState {
  // Stabilise the cache key so identical sets (regardless of order) don't
  // refetch.
  const cacheKey = useMemo(() => {
    const sorted = [...chunkIds].sort();
    return sorted.join(",");
  }, [chunkIds]);

  const [state, setState] = useState<ProjectionCoordsState>({
    data: null,
    error: null,
    loading: false,
  });

  useEffect(() => {
    if (!cacheKey) {
      setState({ data: null, error: null, loading: false });
      return;
    }
    let cancelled = false;
    setState((s) => ({ ...s, loading: true, error: null }));

    const base = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "/api/v1";
    const url = `${base}/projections/coords?ids=${encodeURIComponent(cacheKey)}`;

    fetch(url, { headers: { Accept: "application/json" } })
      .then(async (res) => {
        if (cancelled) return;
        if (!res.ok) {
          setState({
            data: null,
            error: new Error(`${res.status} ${res.statusText}`),
            loading: false,
          });
          return;
        }
        const data = (await res.json()) as ProjectionCoordsResponse;
        setState({ data, error: null, loading: false });
      })
      .catch((err: Error) => {
        if (cancelled) return;
        setState({ data: null, error: err, loading: false });
      });

    return () => {
      cancelled = true;
    };
  }, [cacheKey]);

  return state;
}

export function useRelatedSpeeches(
  speechId: string | null,
  chunkId: string | null,
  limit = 5,
): RelatedSpeechesState {
  const [state, setState] = useState<RelatedSpeechesState>({
    data: null,
    error: null,
    loading: !!speechId,
  });

  useEffect(() => {
    if (!speechId) {
      setState({ data: null, error: null, loading: false });
      return;
    }
    let cancelled = false;
    setState((s) => ({ ...s, loading: true, error: null }));

    const base = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "/api/v1";
    const params = new URLSearchParams();
    params.set("limit", String(limit));
    if (chunkId) params.set("chunk", chunkId);
    const url = `${base}/speeches/${encodeURIComponent(speechId)}/related?${params.toString()}`;

    fetch(url, { headers: { Accept: "application/json" } })
      .then(async (res) => {
        if (cancelled) return;
        if (!res.ok) {
          setState({
            data: null,
            error: new Error(`${res.status} ${res.statusText}`),
            loading: false,
          });
          return;
        }
        const data = (await res.json()) as RelatedSpeechesResponse;
        setState({ data, error: null, loading: false });
      })
      .catch((err: Error) => {
        if (cancelled) return;
        setState({ data: null, error: err, loading: false });
      });

    return () => {
      cancelled = true;
    };
  }, [speechId, chunkId, limit]);

  return state;
}

export function useSpeechContext(
  id: string | null,
  opts: SpeechContextOpts,
): SpeechContextState {
  const url = useMemo(() => {
    if (!id) return null;
    const base = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "/api/v1";
    const params = new URLSearchParams();
    if (opts.all) {
      params.set("all", "true");
    } else {
      if (opts.before !== undefined) params.set("before", String(opts.before));
      if (opts.after !== undefined) params.set("after", String(opts.after));
    }
    const q = params.toString();
    return `${base}/speeches/${encodeURIComponent(id)}/context${q ? `?${q}` : ""}`;
  }, [id, opts.before, opts.after, opts.all]);

  const [state, setState] = useState<SpeechContextState>({
    data: null,
    error: null,
    loading: !!url,
  });

  useEffect(() => {
    if (!url) {
      setState({ data: null, error: null, loading: false });
      return;
    }
    let cancelled = false;
    setState((s) => ({ ...s, loading: true, error: null }));

    fetch(url, { headers: { Accept: "application/json" } })
      .then(async (res) => {
        if (cancelled) return;
        if (!res.ok) {
          setState({
            data: null,
            error: new Error(`${res.status} ${res.statusText}`),
            loading: false,
          });
          return;
        }
        const data = (await res.json()) as SpeechContextResponse;
        setState({ data, error: null, loading: false });
      })
      .catch((err: Error) => {
        if (cancelled) return;
        setState({ data: null, error: err, loading: false });
      });

    return () => {
      cancelled = true;
    };
  }, [url]);

  return state;
}
