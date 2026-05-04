import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import type { SpeechSearchItem } from "../hooks/useSpeechSearch";
import { useChunkInfo, useProjectionCoords, useRelatedSpeeches } from "../hooks/useSpeech";

// "Map" tab on /search — turns the top-K results into a clickable mind-graph
// rooted on the query. Click any satellite to *re-centre* the graph on that
// chunk and fetch its semantic neighbours (via the existing
// `/speeches/:id/related` endpoint), with a breadcrumb back. The walk lets
// the user explore the embedding space without leaving the page; a "→"
// affordance on each node still escapes to the full speech.

const GRAPH_W = 900;
const GRAPH_H = 560;
const CENTRE_X = GRAPH_W / 2;
const CENTRE_Y = GRAPH_H / 2;
const RADIUS_MIN = 150;
const RADIUS_MAX = 250;
const MAX_SATELLITES = 8;

const PARTY_HEX: Record<string, string> = {
  lib: "#d71920",
  liberal: "#d71920",
  cpc: "#1a4782",
  con: "#1a4782",
  conservative: "#1a4782",
  ndp: "#f37021",
  npd: "#f37021",
  bq: "#33b2cc",
  gp: "#3d9b35",
  grn: "#3d9b35",
  green: "#3d9b35",
  ppc: "#4a3590",
};

function partyColour(p: string | null): string {
  if (!p) return "#64748b";
  return PARTY_HEX[p.toLowerCase()] ?? "#64748b";
}

function formatDate(iso: string | null): string | null {
  if (!iso) return null;
  try {
    return new Date(iso).toLocaleDateString("en-CA", {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  } catch {
    return null;
  }
}

function previewSnippet(text: string): string {
  const t = text.trim();
  if (t.length <= 240) return t;
  return t.slice(0, 237) + "…";
}

function lastNames(name: string): string {
  return name.split(" ").slice(-2).join(" ");
}

interface MapNode {
  chunkId: string;
  speechId: string;
  text: string;
  speakerName: string;
  party: string | null;
  photoUrl: string | null;
  spokenAt: string | null;
  similarity: number;
}

type WalkAnchor =
  | { kind: "query"; label: string }
  | {
      kind: "chunk";
      chunkId: string;
      speechId: string;
      label: string;
      party: string | null;
      photoUrl: string | null;
    };

interface Props {
  query: string;
  searchItems: SpeechSearchItem[];
  searchLoading: boolean;
  /** When the search is anchored on a chunk (URL `?anchor_chunk_id=...`),
   *  pre-push that chunk onto the walk so the graph centre is the anchor
   *  rather than the synthetic query node. */
  anchorChunkId?: string | null;
}

function searchItemToNode(item: SpeechSearchItem): MapNode {
  return {
    chunkId: item.chunk_id,
    speechId: item.speech_id,
    text: item.text,
    speakerName: item.politician?.name ?? item.speech.speaker_name_raw,
    party: item.party_at_time ?? item.politician?.party ?? null,
    photoUrl: item.politician?.photo_url ?? null,
    spokenAt: item.spoken_at,
    similarity: item.similarity ?? 0,
  };
}

export function SearchMapView({ query, searchItems, searchLoading, anchorChunkId }: Props) {
  // The walk: empty stack = sitting on the query node. Push a chunk to
  // re-centre. Pop (via breadcrumb) to back up.
  const [walk, setWalk] = useState<WalkAnchor[]>([]);
  // Reset on query change so the walk doesn't carry over to a different topic.
  useEffect(() => {
    setWalk([]);
  }, [query, anchorChunkId]);

  // Pre-push the anchor chunk onto the walk when the search is in anchor
  // mode — graph centre then renders the anchor, satellites = its
  // /related neighbours rather than the (anchor-excluded) timeline items.
  const anchorInfo = useChunkInfo(anchorChunkId ?? null);
  useEffect(() => {
    if (!anchorChunkId || !anchorInfo.data) return;
    setWalk((w) => {
      // Don't double-push if already at this anchor.
      const head = w[w.length - 1];
      if (head && head.kind === "chunk" && head.chunkId === anchorChunkId) return w;
      const c = anchorInfo.data!;
      return [
        {
          kind: "chunk",
          chunkId: c.chunk_id,
          speechId: c.speech_id,
          label: c.politician?.name ?? c.speaker_name_raw,
          party: c.party_at_time ?? c.politician?.party ?? null,
          photoUrl: c.politician?.photo_url ?? null,
        },
      ];
    });
  }, [anchorChunkId, anchorInfo.data]);

  const head = walk.length === 0 ? null : walk[walk.length - 1];
  const isQueryAnchor = head === null;

  // When the head is a chunk, fetch its neighbours. Hook is hard-wired to
  // 8 to match the satellite cap.
  const anchorChunk = head && head.kind === "chunk" ? head : null;
  const related = useRelatedSpeeches(
    anchorChunk?.speechId ?? null,
    anchorChunk?.chunkId ?? null,
    MAX_SATELLITES,
  );

  // Build the satellite list for the current head.
  const satellites: MapNode[] = useMemo(() => {
    if (isQueryAnchor) {
      return searchItems
        .filter((it) => it.similarity !== null)
        .slice(0, MAX_SATELLITES)
        .map(searchItemToNode);
    }
    if (!related.data) return [];
    return related.data.items.map((it) => ({
      chunkId: it.chunk_id,
      speechId: it.speech_id,
      text: it.chunk_text,
      speakerName: it.politician?.name ?? it.speaker_name_raw,
      party: it.party_at_time ?? it.politician?.party ?? null,
      photoUrl: it.politician?.photo_url ?? null,
      spokenAt: it.spoken_at,
      similarity: it.similarity,
    }));
  }, [isQueryAnchor, searchItems, related.data]);

  // Pull UMAP coords for the satellites + (when re-centred) the anchor.
  // When all satellites have coords, layout uses real semantic positions —
  // distance from centre reflects actual UMAP distance, edges are still
  // drawn radially. Falls back to synthetic similarity-radial when the
  // projection run is unavailable or any satellite is missing coords.
  const lookupIds = useMemo(() => {
    const ids = satellites.map((n) => n.chunkId);
    if (anchorChunk) ids.push(anchorChunk.chunkId);
    return ids;
  }, [satellites, anchorChunk]);

  const projection = useProjectionCoords(lookupIds);

  const placedNodes = useMemo(() => {
    const sims = satellites.map((n) => n.similarity);
    const sMin = Math.min(...sims);
    const sMax = Math.max(...sims);
    const sRange = Math.max(0.0001, sMax - sMin);

    // Synthetic radial fallback — used when projection data isn't available
    // or doesn't cover the full satellite set.
    const synthetic = () =>
      satellites.map((n, i) => {
        const angle = (i / satellites.length) * Math.PI * 2 - Math.PI / 2;
        const norm = (sMax - n.similarity) / sRange;
        const radius = RADIUS_MIN + norm * (RADIUS_MAX - RADIUS_MIN);
        const x = CENTRE_X + Math.cos(angle) * radius;
        const y = CENTRE_Y + Math.sin(angle) * radius;
        return { n, x, y };
      });

    if (!projection.data || projection.data.items.length === 0) {
      return { nodes: synthetic(), source: "radial" as const };
    }

    const coordById = new Map(projection.data.items.map((c) => [c.chunk_id, c]));
    const satCoords = satellites.map((n) => coordById.get(n.chunkId));
    if (satCoords.some((c) => !c)) {
      return { nodes: synthetic(), source: "radial" as const };
    }

    // Pick the centre origin: anchor's UMAP coord when re-centred, else the
    // centroid of the satellites for the query view.
    let originX: number;
    let originY: number;
    if (anchorChunk) {
      const anchorCoord = coordById.get(anchorChunk.chunkId);
      if (!anchorCoord) return { nodes: synthetic(), source: "radial" as const };
      originX = anchorCoord.x2;
      originY = anchorCoord.y2;
    } else {
      originX = satCoords.reduce((s, c) => s + c!.x2, 0) / satCoords.length;
      originY = satCoords.reduce((s, c) => s + c!.y2, 0) / satCoords.length;
    }

    // Hybrid layout — UMAP for *radius* (real semantic distance from anchor)
    // but uniform angular distribution to prevent label collisions when
    // semantically-similar speeches pile up in the same corner of UMAP
    // space. The radius difference is what conveys the topology; the
    // angles are just spaced for legibility.
    const dists = satCoords.map((c) => Math.hypot(c!.x2 - originX, c!.y2 - originY));
    const dMin = Math.min(...dists);
    const dMax = Math.max(0.0001, ...dists);
    const dRange = Math.max(0.0001, dMax - dMin);

    // Sort indices by ascending UMAP distance so the closest satellite gets
    // the smallest angular index — when angle-distance is uniform, this
    // doesn't matter visually, but it keeps the layout deterministic.
    const order = satellites
      .map((_, i) => i)
      .sort((a, b) => dists[a]! - dists[b]!);

    const placed = new Array<{ n: MapNode; x: number; y: number }>(satellites.length);
    order.forEach((origIdx, slot) => {
      const angle = (slot / satellites.length) * Math.PI * 2 - Math.PI / 2;
      const norm = (dists[origIdx]! - dMin) / dRange;
      const radius = RADIUS_MIN + norm * (RADIUS_MAX - RADIUS_MIN);
      placed[origIdx] = {
        n: satellites[origIdx]!,
        x: CENTRE_X + Math.cos(angle) * radius,
        y: CENTRE_Y + Math.sin(angle) * radius,
      };
    });

    return { nodes: placed, source: "umap" as const };
  }, [satellites, projection.data, anchorChunk]);

  const loading =
    isQueryAnchor ? searchLoading && searchItems.length === 0 : related.loading && satellites.length === 0;

  // Hover state for the inline preview drawer. Must be declared before any
  // early return so hook order is stable across renders.
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);

  const recenter = (n: MapNode) =>
    setWalk((w) => [
      ...w,
      {
        kind: "chunk",
        chunkId: n.chunkId,
        speechId: n.speechId,
        label: n.speakerName,
        party: n.party,
        photoUrl: n.photoUrl,
      },
    ]);

  const popTo = (idx: number) => setWalk((w) => w.slice(0, idx));

  // Empty / loading guards. All hooks are above this point so render-order
  // is stable regardless of which branch fires.
  if (!query.trim() && walk.length === 0) {
    return (
      <div className="search-map search-map--empty">
        <p>
          Type a query above to start exploring. The map renders the top results as a graph; click
          any node to re-centre on that speech and walk through its semantic neighbours.
        </p>
      </div>
    );
  }

  if (loading && satellites.length === 0) {
    return (
      <div className="search-map search-map--empty">
        <p>Loading semantic neighbours…</p>
      </div>
    );
  }

  if (!loading && satellites.length === 0) {
    return (
      <div className="search-map search-map--empty">
        <p>No semantic neighbours to map for this anchor.</p>
        {walk.length > 0 && (
          <button type="button" className="search-map__back-btn" onClick={() => setWalk((w) => w.slice(0, -1))}>
            ← back
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="search-map" aria-label="Semantic exploration map">
      <div className="search-map__breadcrumb" role="navigation" aria-label="Exploration history">
        <button
          type="button"
          className={
            walk.length === 0
              ? "search-map__crumb search-map__crumb--current"
              : "search-map__crumb"
          }
          onClick={() => popTo(0)}
          disabled={walk.length === 0}
          title={query ? `Back to "${query}"` : "Back to anchor"}
        >
          {query ? `“${query}”` : (anchorChunkId ? "anchor" : "search")}
        </button>
        {walk.map((a, i) => (
          <span key={i} className="search-map__crumb-row">
            <span className="search-map__crumb-arrow" aria-hidden="true">›</span>
            <button
              type="button"
              className={
                i === walk.length - 1
                  ? "search-map__crumb search-map__crumb--current"
                  : "search-map__crumb"
              }
              onClick={() => popTo(i + 1)}
              disabled={i === walk.length - 1}
            >
              {a.kind === "chunk" ? lastNames(a.label) : a.label}
            </button>
          </span>
        ))}
      </div>

      <svg
        viewBox={`0 0 ${GRAPH_W} ${GRAPH_H}`}
        className="search-map__svg"
        role="img"
        aria-label="Semantic mind-graph of search results"
      >
        {placedNodes.nodes.map(({ n, x, y }, i) => (
          <line
            key={`edge-${n.chunkId}`}
            x1={CENTRE_X}
            y1={CENTRE_Y}
            x2={x}
            y2={y}
            stroke={hoverIdx === i ? "var(--accent)" : partyColour(n.party)}
            strokeWidth={hoverIdx === i ? 2.5 : 1.5}
            strokeOpacity={0.25 + n.similarity * 0.6}
          />
        ))}

        {isQueryAnchor ? (
          <CentreQueryNode label={query || "your search"} />
        ) : (
          <CentreChunkNode
            label={head!.kind === "chunk" ? head!.label : ""}
            party={head!.kind === "chunk" ? head!.party : null}
            photoUrl={head!.kind === "chunk" ? head!.photoUrl : null}
          />
        )}

        {placedNodes.nodes.map(({ n, x, y }, i) => (
          <g
            key={n.chunkId}
            className="search-map__node"
            transform={`translate(${x}, ${y})`}
            onClick={() => recenter(n)}
            onMouseEnter={() => setHoverIdx(i)}
            onMouseLeave={() => setHoverIdx(null)}
            tabIndex={0}
            role="button"
            aria-label={`Re-centre on ${n.speakerName}`}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                recenter(n);
              }
            }}
          >
            <circle
              r={32}
              fill="#0b1220"
              stroke={partyColour(n.party)}
              strokeWidth={hoverIdx === i ? 3 : 2}
            />
            {n.photoUrl ? (
              <>
                <defs>
                  <clipPath id={`smclip-${n.chunkId}`}>
                    <circle r={30} />
                  </clipPath>
                </defs>
                <image
                  href={n.photoUrl}
                  x={-30}
                  y={-30}
                  width={60}
                  height={60}
                  clipPath={`url(#smclip-${n.chunkId})`}
                />
              </>
            ) : (
              <text
                textAnchor="middle"
                dominantBaseline="central"
                fontSize="22"
                fontWeight="700"
                fill="#e2e8f0"
              >
                {n.speakerName.slice(0, 1)}
              </text>
            )}
            <g transform="translate(22, -26)">
              <rect width={44} height={20} rx={10} ry={10} fill="#020617" stroke="var(--border)" />
              <text
                x={22}
                y={10}
                textAnchor="middle"
                dominantBaseline="central"
                fontSize="11"
                fontWeight="700"
                fill="#e2e8f0"
              >
                {Math.round(n.similarity * 100)}%
              </text>
            </g>
            <text x={0} y={50} textAnchor="middle" fontSize="13" fontWeight="600" fill="#e2e8f0">
              {lastNames(n.speakerName)}
            </text>
            <text x={0} y={66} textAnchor="middle" fontSize="11" fill="#94a3b8">
              {formatDate(n.spokenAt) ?? ""}
            </text>
          </g>
        ))}
      </svg>

      <div className="search-map__hover" aria-live="polite">
        {hoverIdx !== null && placedNodes.nodes[hoverIdx] ? (
          <>
            <div className="search-map__hover-head">
              <span className="search-map__hover-name">
                {placedNodes.nodes[hoverIdx]!.n.speakerName}
              </span>
              <span className="search-map__hover-sub">
                {" · "}
                {placedNodes.nodes[hoverIdx]!.n.party ?? "—"}
                {placedNodes.nodes[hoverIdx]!.n.spokenAt
                  ? ` · ${formatDate(placedNodes.nodes[hoverIdx]!.n.spokenAt)}`
                  : ""}
              </span>
              <Link
                to={`/speeches/${placedNodes.nodes[hoverIdx]!.n.speechId}#chunk-${placedNodes.nodes[hoverIdx]!.n.chunkId}`}
                className="search-map__hover-link"
                onClick={(e) => e.stopPropagation()}
              >
                Open speech →
              </Link>
              <Link
                to={`/search?anchor_chunk_id=${placedNodes.nodes[hoverIdx]!.n.chunkId}`}
                className="search-map__hover-link search-map__hover-link--secondary"
                onClick={(e) => e.stopPropagation()}
                title="Pivot the standard search to use this chunk as the query"
              >
                Search corpus →
              </Link>
            </div>
            <div className="search-map__hover-snippet">
              {placedNodes.nodes[hoverIdx]!.n.text}
            </div>
          </>
        ) : (
          <span className="search-map__hover-hint">
            Hover any node to preview · click to re-centre on it · the “→” opens the full speech
          </span>
        )}
      </div>

      <p className="search-map__legend">
        <span className="search-map__legend-dot search-map__legend-dot--query" />
        Anchor (centre)
        <span className="search-map__legend-sep" />
        {placedNodes.source === "umap"
          ? "Position = UMAP coordinates from the corpus map"
          : "Position = synthetic radial (similarity)"}
        <span className="search-map__legend-sep" />
        Edge colour = speaker's party
        {related.error && walk.length > 0 && (
          <>
            <span className="search-map__legend-sep" />
            <span className="search-map__legend-error">couldn't fetch neighbours: {related.error.message}</span>
          </>
        )}
      </p>

    </div>
  );
}

function CentreQueryNode({ label }: { label: string }) {
  return (
    <g transform={`translate(${CENTRE_X}, ${CENTRE_Y})`}>
      <circle r={56} fill="var(--accent)" fillOpacity={0.12} stroke="var(--accent)" strokeWidth={2} strokeDasharray="3 3" />
      <circle r={42} fill="#0b1220" stroke="var(--accent)" strokeWidth={2.5} />
      <text
        textAnchor="middle"
        dominantBaseline="central"
        fontSize="16"
        fontWeight="700"
        fill="#e2e8f0"
      >
        “…”
      </text>
      <text x={0} y={68} textAnchor="middle" fontSize="13" fontWeight="700" fill="#e2e8f0">
        {label.length > 28 ? label.slice(0, 27) + "…" : label}
      </text>
      <text x={0} y={84} textAnchor="middle" fontSize="11" fill="#94a3b8">
        your query
      </text>
    </g>
  );
}

function CentreChunkNode({
  label,
  party,
  photoUrl,
}: {
  label: string;
  party: string | null;
  photoUrl: string | null;
}) {
  const colour = partyColour(party);
  return (
    <g transform={`translate(${CENTRE_X}, ${CENTRE_Y})`}>
      <circle r={56} fill={colour} fillOpacity={0.18} stroke={colour} strokeWidth={2} strokeDasharray="3 3" />
      <circle r={42} fill="#0b1220" stroke={colour} strokeWidth={2.5} />
      {photoUrl ? (
        <>
          <defs>
            <clipPath id="clip-search-centre">
              <circle r={40} />
            </clipPath>
          </defs>
          <image
            href={photoUrl}
            x={-40}
            y={-40}
            width={80}
            height={80}
            clipPath="url(#clip-search-centre)"
          />
        </>
      ) : (
        <text
          textAnchor="middle"
          dominantBaseline="central"
          fontSize="28"
          fontWeight="700"
          fill="#e2e8f0"
        >
          {label.slice(0, 1)}
        </text>
      )}
      <text x={0} y={68} textAnchor="middle" fontSize="13" fontWeight="700" fill="#e2e8f0">
        {label}
      </text>
      <text x={0} y={84} textAnchor="middle" fontSize="11" fill="#94a3b8">
        re-centred
      </text>
    </g>
  );
}
