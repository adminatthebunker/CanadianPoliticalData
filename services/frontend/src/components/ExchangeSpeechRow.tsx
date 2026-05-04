import { forwardRef, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import type { ContextSpeech, SpeechChunkSummary, SpeechDetail } from "../hooks/useSpeech";
import { ourcommonsVideoUrl } from "../lib/videoEmbedUrl";
import { highlightQuery, sanitizeHighlighted } from "../lib/textHighlight";
import { readingTimeMinutes } from "../lib/speechHelpers";
import { QuoteShareMenu } from "./QuoteShareMenu";

// One row in the Hansard exchange view. Two shapes — a "context" speech
// (lightweight, plain text body) and the "focal" speech (full text with
// chunk anchors so deep-links from search results still highlight the
// matched span). The row layout matches openparliament.ca's debate page:
// left margin = topic-ish info (we surface speech_type + time), middle =
// speaker + body, right column = a compact share trigger.

interface Segment {
  chunk: SpeechChunkSummary | null;
  text: string;
}

function segmentsFromChunks(fullText: string, chunks: SpeechChunkSummary[]): Segment[] {
  if (chunks.length === 0) return [{ chunk: null, text: fullText }];
  const ordered = [...chunks].sort((a, b) => a.chunk_index - b.chunk_index);
  const out: Segment[] = [];
  let cursor = 0;
  for (const c of ordered) {
    if (c.char_start < cursor || c.char_end > fullText.length || c.char_end < c.char_start) {
      return [{ chunk: null, text: fullText }];
    }
    if (c.char_start > cursor) {
      out.push({ chunk: null, text: fullText.slice(cursor, c.char_start) });
    }
    out.push({ chunk: c, text: fullText.slice(c.char_start, c.char_end) });
    cursor = c.char_end;
  }
  if (cursor < fullText.length) {
    out.push({ chunk: null, text: fullText.slice(cursor) });
  }
  return out;
}

/** Pick the chunk to anchor a corpus search on when no chunk anchor is in
 *  the URL. The longest chunk usually carries the most semantic content,
 *  so its embedding is the strongest "what is this speech about?" signal. */
function pickAnchorChunkId(chunks: SpeechChunkSummary[]): string {
  if (chunks.length === 0) return "";
  let best = chunks[0]!;
  for (const c of chunks) {
    if (c.text.length > best.text.length) best = c;
  }
  return best.id;
}

function formatTime(iso: string | null): string | null {
  if (!iso) return null;
  try {
    return new Date(iso).toLocaleTimeString("en-CA", { hour: "numeric", minute: "2-digit" });
  } catch {
    return null;
  }
}

function speechTypeLabel(t: string | null): string | null {
  if (!t) return null;
  if (t === "floor") return "Floor";
  if (t === "committee") return "Committee";
  return t.replace(/_/g, " ");
}

const PREVIEW_CAP = 1200;

interface FocalRowProps {
  kind: "focal";
  speech: SpeechDetail;
  chunks: SpeechChunkSummary[];
  highlightChunkId: string | null;
  /** Lowercased token list for cross-row query highlight (when user came
   *  from a search). Empty list disables highlighting. */
  queryTerms?: string[];
  /** Number of related speeches available — drives the "Similar speeches"
   *  pill in the focal action bar. 0 hides the pill. */
  similarCount?: number;
  onJumpToSimilar?: () => void;
}

interface ContextRowProps {
  kind: "context";
  speech: ContextSpeech;
  queryTerms?: string[];
}

type ExchangeSpeechRowProps = FocalRowProps | ContextRowProps;

export const ExchangeSpeechRow = forwardRef<HTMLElement, ExchangeSpeechRowProps>(
  function ExchangeSpeechRow(props, ref) {
    const focal = props.kind === "focal";
    const speech = props.speech;
    const pol = speech.politician;
    const time = formatTime(speech.spoken_at);
    const typeLabel = speechTypeLabel(speech.speech_type);

    const internalUrl = focal
      ? `/speeches/${speech.id}${
          props.kind === "focal" && props.highlightChunkId
            ? `#chunk-${props.highlightChunkId}`
            : ""
        }`
      : `/speeches/${speech.id}`;

    const hansardUrl = speech.source_anchor
      ? `${speech.source_url}#${speech.source_anchor}`
      : speech.source_url;

    const videoUrl = ourcommonsVideoUrl({
      source_system: speech.source_system,
      source_anchor: speech.source_anchor,
      level: speech.level,
      language: speech.language,
    });

    return (
      <article
        ref={ref}
        className={focal ? "exchange-row exchange-row--focal" : "exchange-row"}
        id={`speech-${speech.id}`}
      >
        <div className="exchange-row__sidebar">
          {typeLabel && <div className="exchange-row__topic">{typeLabel}</div>}
          {time && (
            <time className="exchange-row__time" dateTime={speech.spoken_at ?? ""}>
              {time}
            </time>
          )}
          {speech.party_at_time && (
            <span
              className="exchange-row__party"
              data-party={speech.party_at_time.toLowerCase()}
            >
              {speech.party_at_time}
            </span>
          )}
        </div>

        <div className="exchange-row__main">
          <div className="exchange-row__speaker">
            {pol?.photo_url ? (
              <img
                src={pol.photo_url}
                alt=""
                className="exchange-row__photo"
                loading="lazy"
                width={48}
                height={48}
              />
            ) : (
              <div
                className="exchange-row__photo exchange-row__photo--placeholder"
                aria-hidden="true"
              >
                {(pol?.name ?? speech.speaker_name_raw).slice(0, 1)}
              </div>
            )}
            <div className="exchange-row__speaker-meta">
              {pol ? (
                <Link to={`/politicians/${pol.id}`} className="exchange-row__speaker-name">
                  {pol.name ?? speech.speaker_name_raw}
                </Link>
              ) : (
                <span className="exchange-row__speaker-name exchange-row__speaker-name--unresolved">
                  {speech.speaker_name_raw}
                </span>
              )}
              {speech.constituency_at_time && (
                <span className="exchange-row__constituency">
                  {speech.constituency_at_time}
                </span>
              )}
              {speech.speaker_role && !speech.constituency_at_time && (
                <span className="exchange-row__constituency">
                  {speech.speaker_role}
                </span>
              )}
            </div>
          </div>

          {focal ? (
            <FocalBody
              text={speech.text}
              chunks={(props as FocalRowProps).chunks}
              highlightChunkId={(props as FocalRowProps).highlightChunkId}
              queryTerms={(props as FocalRowProps).queryTerms ?? []}
            />
          ) : (
            <ContextBody text={speech.text} queryTerms={props.queryTerms ?? []} />
          )}

          {focal && readingTimeMinutes((props as FocalRowProps).speech.word_count) !== null && (
            <div className="exchange-row__reading-time">
              {readingTimeMinutes((props as FocalRowProps).speech.word_count)} min read · {(props as FocalRowProps).speech.word_count} words
            </div>
          )}

          <div className="exchange-row__actions">
            {!focal && (
              <Link to={internalUrl} className="exchange-row__action">
                View speech →
              </Link>
            )}
            {focal && (props as FocalRowProps).similarCount! > 0 && (
              <button
                type="button"
                className="exchange-row__action exchange-row__action--similar"
                onClick={() => (props as FocalRowProps).onJumpToSimilar?.()}
                title="Jump to semantically-similar speeches from other sittings"
              >
                <span aria-hidden="true">◉</span> Similar speeches ({(props as FocalRowProps).similarCount})
              </button>
            )}
            {focal && (props as FocalRowProps).chunks.length > 0 && (
              <Link
                to={`/search?anchor_chunk_id=${(props as FocalRowProps).highlightChunkId ?? pickAnchorChunkId((props as FocalRowProps).chunks)}`}
                className="exchange-row__action exchange-row__action--secondary"
                title="Use this chunk as your search across the whole corpus"
              >
                Search corpus →
              </Link>
            )}
            {videoUrl && (
              <a
                href={videoUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="exchange-row__action exchange-row__action--video"
                title="Watch on Parliament's site"
              >
                <span aria-hidden="true">▶</span> Video ↗
              </a>
            )}
            <a
              href={hansardUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="exchange-row__action exchange-row__action--secondary"
            >
              Hansard ↗
            </a>
            <QuoteShareMenu
              speakerName={pol?.name ?? speech.speaker_name_raw}
              dateIso={speech.spoken_at}
              quoteText={speech.text}
              internalUrl={internalUrl}
              videoUrl={videoUrl}
              hansardUrl={hansardUrl}
              compact={!focal}
            />
          </div>
        </div>
      </article>
    );
  },
);

function FocalBody({
  text,
  chunks,
  highlightChunkId,
  queryTerms,
}: {
  text: string;
  chunks: SpeechChunkSummary[];
  highlightChunkId: string | null;
  queryTerms: string[];
}) {
  const segments = segmentsFromChunks(text, chunks);
  return (
    <div className="exchange-row__body">
      {segments.map((seg, i) => {
        const isHighlight = seg.chunk && seg.chunk.id === highlightChunkId;
        return (
          <span
            key={i}
            id={seg.chunk ? `chunk-${seg.chunk.id}` : undefined}
            className={
              isHighlight
                ? "exchange-row__segment exchange-row__segment--highlight"
                : "exchange-row__segment"
            }
            dangerouslySetInnerHTML={
              queryTerms.length > 0
                ? sanitizeHighlighted(highlightQuery(seg.text, queryTerms))
                : undefined
            }
          >
            {queryTerms.length === 0 ? seg.text : null}
          </span>
        );
      })}
    </div>
  );
}

function ContextBody({ text, queryTerms }: { text: string; queryTerms: string[] }) {
  const [expanded, setExpanded] = useState(false);
  const overflow = text.length > PREVIEW_CAP;
  const display = overflow && !expanded ? `${text.slice(0, PREVIEW_CAP)}…` : text;
  const highlighted = useMemo(
    () => (queryTerms.length > 0 ? sanitizeHighlighted(highlightQuery(display, queryTerms)) : null),
    [display, queryTerms],
  );
  return (
    <div className="exchange-row__body exchange-row__body--context">
      {highlighted ? <span dangerouslySetInnerHTML={highlighted} /> : display}
      {overflow && (
        <button
          type="button"
          className="exchange-row__expand"
          onClick={() => setExpanded((v) => !v)}
        >
          {expanded ? "Show less" : "Show full speech"}
        </button>
      )}
    </div>
  );
}

