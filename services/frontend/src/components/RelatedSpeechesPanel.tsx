import { forwardRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import type { RelatedSpeechItem } from "../hooks/useSpeech";

// Surfaces semantically-similar speeches *from other sittings* below the
// focal row. Anchored on either a specific chunk (when the user came from a
// search hit) or the longest chunk in the focal speech (cold-load case).
//
// Two render modes:
//   - "list": vertical card list (default).
//   - "graph": radial mind-graph with focal at centre, related speakers on
//     a ring, edge length inversely proportional to cosine similarity.

interface FocalSummary {
  speakerName: string;
  party: string | null;
  photoUrl: string | null;
}

interface Props {
  items: RelatedSpeechItem[];
  loading: boolean;
  focal: FocalSummary;
  pulse?: boolean;
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
  const trimmed = text.trim();
  if (trimmed.length <= 280) return trimmed;
  return trimmed.slice(0, 277) + "…";
}

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

function partyColour(party: string | null): string {
  if (!party) return "#64748b";
  return PARTY_HEX[party.toLowerCase()] ?? "#64748b";
}

export const RelatedSpeechesPanel = forwardRef<HTMLElement, Props>(
  function RelatedSpeechesPanel({ items, loading, focal, pulse = false }, ref) {
    const [mode, setMode] = useState<"list" | "graph">("list");

    if (loading && items.length === 0) {
      return (
        <section
          ref={ref}
          className={
            pulse
              ? "related-speeches related-speeches--loading related-speeches--pulse"
              : "related-speeches related-speeches--loading"
          }
        >
          <h2 className="related-speeches__title">Speeches making similar points</h2>
          <p className="related-speeches__hint">Searching the corpus…</p>
        </section>
      );
    }
    if (items.length === 0) return null;

    return (
      <section
        ref={ref}
        className={pulse ? "related-speeches related-speeches--pulse" : "related-speeches"}
        aria-label="Related speeches"
      >
        <div className="related-speeches__head">
          <div>
            <h2 className="related-speeches__title">Speeches making similar points</h2>
            <p className="related-speeches__hint">
              Other Hansard speeches whose semantic content overlaps with this one — drawn from the
              full embedding corpus, not keyword-matched.
            </p>
          </div>
          <div className="related-speeches__mode-toggle" role="tablist" aria-label="View mode">
            <button
              type="button"
              role="tab"
              aria-selected={mode === "list"}
              className={
                mode === "list"
                  ? "related-speeches__mode related-speeches__mode--on"
                  : "related-speeches__mode"
              }
              onClick={() => setMode("list")}
            >
              List
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={mode === "graph"}
              className={
                mode === "graph"
                  ? "related-speeches__mode related-speeches__mode--on"
                  : "related-speeches__mode"
              }
              onClick={() => setMode("graph")}
              title="Radial mind-graph view"
            >
              Graph
            </button>
          </div>
        </div>

        {mode === "list" ? <ListView items={items} /> : <GraphView items={items} focal={focal} />}
      </section>
    );
  },
);

function ListView({ items }: { items: RelatedSpeechItem[] }) {
  return (
    <ul className="related-speeches__list">
      {items.map((it) => {
        const date = formatDate(it.spoken_at);
        const url = `/speeches/${it.speech_id}#chunk-${it.chunk_id}`;
        const snippet = previewSnippet(it.chunk_text);
        return (
          <li key={it.chunk_id} className="related-speeches__card">
            <Link to={url} className="related-speeches__card-link">
              <div className="related-speeches__card-head">
                {it.politician?.photo_url ? (
                  <img
                    src={it.politician.photo_url}
                    alt=""
                    className="related-speeches__photo"
                    loading="lazy"
                    width={36}
                    height={36}
                  />
                ) : (
                  <div
                    className="related-speeches__photo related-speeches__photo--placeholder"
                    aria-hidden="true"
                  >
                    {(it.politician?.name ?? it.speaker_name_raw).slice(0, 1)}
                  </div>
                )}
                <div className="related-speeches__meta">
                  <span className="related-speeches__name">
                    {it.politician?.name ?? it.speaker_name_raw}
                  </span>
                  <span className="related-speeches__sub">
                    {it.party_at_time ?? it.politician?.party ?? "—"}
                    {date ? ` · ${date}` : ""}
                  </span>
                </div>
                <span className="related-speeches__similarity" title="Cosine similarity">
                  {Math.round(it.similarity * 100)}%
                </span>
              </div>
              <p className="related-speeches__snippet">{snippet}</p>
            </Link>
          </li>
        );
      })}
    </ul>
  );
}

// ── Graph view ──────────────────────────────────────────────────────
//
// Radial layout: focal node at centre; each related speech is a satellite
// node positioned at an angle around the ring with a radius derived from
// (1 - similarity). Edges drawn from centre outward, opacity scales with
// similarity. Click any node → navigate to that speech.
//
// SVG-only (no extra deps). viewBox-based so it scales fluidly to any
// container width; the parent CSS clamps height for visual balance.

const GRAPH_W = 800;
const GRAPH_H = 520;
const CENTRE_X = GRAPH_W / 2;
const CENTRE_Y = GRAPH_H / 2;
const RADIUS_MIN = 130;
const RADIUS_MAX = 230;

function GraphView({
  items,
  focal,
}: {
  items: RelatedSpeechItem[];
  focal: FocalSummary;
}) {
  const navigate = useNavigate();
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);

  // Map similarity → radius. Higher similarity = closer to centre.
  // Use min/max similarity in the displayed set so the spread is visible
  // regardless of absolute scale.
  const sims = items.map((it) => it.similarity);
  const sMin = Math.min(...sims);
  const sMax = Math.max(...sims);
  const sRange = Math.max(0.0001, sMax - sMin);

  const nodes = items.map((it, i) => {
    const angle = (i / items.length) * Math.PI * 2 - Math.PI / 2; // start at top
    // Closer to centre when similarity is higher.
    const norm = (sMax - it.similarity) / sRange;
    const radius = RADIUS_MIN + norm * (RADIUS_MAX - RADIUS_MIN);
    const x = CENTRE_X + Math.cos(angle) * radius;
    const y = CENTRE_Y + Math.sin(angle) * radius;
    return { it, x, y, angle, radius };
  });

  return (
    <div className="related-speeches__graph">
      <svg
        viewBox={`0 0 ${GRAPH_W} ${GRAPH_H}`}
        className="related-speeches__svg"
        role="img"
        aria-label="Mind-graph of related speeches"
      >
        {/* Edges first so nodes layer on top */}
        {nodes.map(({ it, x, y }, i) => {
          const isHover = hoverIdx === i;
          return (
            <line
              key={`edge-${it.chunk_id}`}
              x1={CENTRE_X}
              y1={CENTRE_Y}
              x2={x}
              y2={y}
              stroke={isHover ? "var(--accent)" : partyColour(it.party_at_time ?? it.politician?.party ?? null)}
              strokeWidth={isHover ? 2.5 : 1.5}
              strokeOpacity={0.25 + it.similarity * 0.6}
            />
          );
        })}

        {/* Centre (focal) node */}
        <FocalNode focal={focal} />

        {/* Outer nodes */}
        {nodes.map(({ it, x, y }, i) => (
          <g
            key={it.chunk_id}
            className="related-speeches__graph-node"
            transform={`translate(${x}, ${y})`}
            onClick={() => navigate(`/speeches/${it.speech_id}#chunk-${it.chunk_id}`)}
            onMouseEnter={() => setHoverIdx(i)}
            onMouseLeave={() => setHoverIdx(null)}
            tabIndex={0}
            role="link"
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                navigate(`/speeches/${it.speech_id}#chunk-${it.chunk_id}`);
              }
            }}
          >
            <circle
              r={28}
              fill="#0b1220"
              stroke={partyColour(it.party_at_time ?? it.politician?.party ?? null)}
              strokeWidth={hoverIdx === i ? 3 : 2}
            />
            {it.politician?.photo_url ? (
              <>
                <defs>
                  <clipPath id={`clip-${it.chunk_id}`}>
                    <circle r={26} />
                  </clipPath>
                </defs>
                <image
                  href={it.politician.photo_url}
                  x={-26}
                  y={-26}
                  width={52}
                  height={52}
                  clipPath={`url(#clip-${it.chunk_id})`}
                />
              </>
            ) : (
              <text
                textAnchor="middle"
                dominantBaseline="central"
                fontSize="20"
                fontWeight="700"
                fill="#e2e8f0"
              >
                {(it.politician?.name ?? it.speaker_name_raw).slice(0, 1)}
              </text>
            )}
            {/* Similarity badge */}
            <g transform="translate(20, -22)">
              <rect width={42} height={18} rx={9} ry={9} fill="#020617" stroke="var(--border)" />
              <text
                x={21}
                y={9}
                textAnchor="middle"
                dominantBaseline="central"
                fontSize="11"
                fontWeight="700"
                fill="#e2e8f0"
              >
                {Math.round(it.similarity * 100)}%
              </text>
            </g>
            {/* Label */}
            <text
              x={0}
              y={48}
              textAnchor="middle"
              fontSize="12"
              fontWeight="600"
              fill="#e2e8f0"
            >
              {(it.politician?.name ?? it.speaker_name_raw).split(" ").slice(-2).join(" ")}
            </text>
            <text x={0} y={62} textAnchor="middle" fontSize="10" fill="#94a3b8">
              {formatDate(it.spoken_at) ?? ""}
            </text>
          </g>
        ))}
      </svg>

      {/* Hover preview drawer */}
      <div className="related-speeches__hover-preview" aria-live="polite">
        {hoverIdx !== null ? (
          <>
            <div className="related-speeches__hover-name">
              {nodes[hoverIdx]!.it.politician?.name ?? nodes[hoverIdx]!.it.speaker_name_raw}
              {" · "}
              <span className="related-speeches__hover-sub">
                {nodes[hoverIdx]!.it.party_at_time ?? nodes[hoverIdx]!.it.politician?.party ?? "—"}
                {nodes[hoverIdx]!.it.spoken_at
                  ? ` · ${formatDate(nodes[hoverIdx]!.it.spoken_at)}`
                  : ""}
              </span>
            </div>
            <div className="related-speeches__hover-snippet">
              {previewSnippet(nodes[hoverIdx]!.it.chunk_text)}
            </div>
          </>
        ) : (
          <span className="related-speeches__hover-hint">
            Hover or focus a node to preview · click to open the speech
          </span>
        )}
      </div>
    </div>
  );
}

function FocalNode({ focal }: { focal: FocalSummary }) {
  const colour = partyColour(focal.party);
  return (
    <g transform={`translate(${CENTRE_X}, ${CENTRE_Y})`}>
      <circle r={48} fill={colour} fillOpacity={0.18} stroke={colour} strokeWidth={2} strokeDasharray="3 3" />
      <circle r={36} fill="#0b1220" stroke={colour} strokeWidth={2.5} />
      {focal.photoUrl ? (
        <>
          <defs>
            <clipPath id="clip-focal">
              <circle r={34} />
            </clipPath>
          </defs>
          <image
            href={focal.photoUrl}
            x={-34}
            y={-34}
            width={68}
            height={68}
            clipPath="url(#clip-focal)"
          />
        </>
      ) : (
        <text
          textAnchor="middle"
          dominantBaseline="central"
          fontSize="26"
          fontWeight="700"
          fill="#e2e8f0"
        >
          {focal.speakerName.slice(0, 1)}
        </text>
      )}
      <text
        x={0}
        y={62}
        textAnchor="middle"
        fontSize="13"
        fontWeight="700"
        fill="#e2e8f0"
      >
        {focal.speakerName}
      </text>
      <text x={0} y={78} textAnchor="middle" fontSize="10" fill="#94a3b8">
        this speech
      </text>
    </g>
  );
}
