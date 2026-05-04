import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useChunkInfo } from "../hooks/useSpeech";

// Header card that surfaces the active anchor chunk on /search when
// anchor_chunk_id is set in the URL. Renders the chunk text in full so
// the user can see what's driving the ranking; the × clears the anchor.

interface Props {
  chunkId: string;
  onClear: () => void;
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

const TEXT_PREVIEW_CAP = 600;

export function AnchorChunkBanner({ chunkId, onClear }: Props) {
  const { data, error, loading } = useChunkInfo(chunkId);
  const [expanded, setExpanded] = useState(false);
  // Reset expand state when the anchor changes.
  useEffect(() => {
    setExpanded(false);
  }, [chunkId]);

  if (loading && !data) {
    return (
      <div className="anchor-banner anchor-banner--loading">
        <span>Loading anchor chunk…</span>
        <button type="button" className="anchor-banner__clear" onClick={onClear} aria-label="Clear anchor">×</button>
      </div>
    );
  }
  if (error || !data) {
    return (
      <div className="anchor-banner anchor-banner--error">
        <span>Couldn't load anchor chunk: {error?.message ?? "not found"}</span>
        <button type="button" className="anchor-banner__clear" onClick={onClear} aria-label="Clear anchor">×</button>
      </div>
    );
  }

  const overflow = data.text.length > TEXT_PREVIEW_CAP;
  const display = overflow && !expanded ? data.text.slice(0, TEXT_PREVIEW_CAP) + "…" : data.text;
  const speaker = data.politician?.name ?? data.speaker_name_raw;
  const date = formatDate(data.spoken_at);
  const party = data.party_at_time ?? data.politician?.party ?? null;

  return (
    <div className="anchor-banner" aria-label="Active anchor chunk">
      <div className="anchor-banner__head">
        <span className="anchor-banner__label">Anchored on</span>
        {data.politician ? (
          <Link to={`/politicians/${data.politician.id}`} className="anchor-banner__speaker">
            {speaker}
          </Link>
        ) : (
          <span className="anchor-banner__speaker anchor-banner__speaker--unresolved">{speaker}</span>
        )}
        {party && <span className="anchor-banner__party">{party}</span>}
        {date && <span className="anchor-banner__date">· {date}</span>}
        <Link
          to={`/speeches/${data.speech_id}#chunk-${data.chunk_id}`}
          className="anchor-banner__open"
        >
          Open speech →
        </Link>
        <button
          type="button"
          className="anchor-banner__clear"
          onClick={onClear}
          title="Clear anchor and return to text search"
          aria-label="Clear anchor"
        >
          × Clear
        </button>
      </div>
      <p className="anchor-banner__text">
        {display}
        {overflow && (
          <button
            type="button"
            className="anchor-banner__expand"
            onClick={() => setExpanded((v) => !v)}
          >
            {expanded ? "Show less" : "Show full chunk"}
          </button>
        )}
      </p>
      <p className="anchor-banner__hint">
        Showing speeches whose embedding is closest to this chunk. Type a query above to switch to text search.
      </p>
    </div>
  );
}
