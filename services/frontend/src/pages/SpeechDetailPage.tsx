import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation, useParams, useSearchParams } from "react-router-dom";
import { useDocumentTitle } from "../hooks/useDocumentTitle";
import { useRelatedSpeeches, useSpeech, useSpeechContext } from "../hooks/useSpeech";
import { CitationButton } from "../components/CitationButton";
import { ExchangeSpeechRow } from "../components/ExchangeSpeechRow";
import { RelatedSpeechesPanel } from "../components/RelatedSpeechesPanel";
import { isProcedural } from "../lib/speechHelpers";
import { tokenizeQuery } from "../lib/textHighlight";
import "../styles/speech-detail.css";

const DEFAULT_WINDOW = 5;
const STEP = 5;

function formatDate(iso: string | null): string | null {
  if (!iso) return null;
  try {
    return new Date(iso).toLocaleDateString("en-CA", {
      year: "numeric",
      month: "long",
      day: "numeric",
    });
  } catch {
    return iso.slice(0, 10);
  }
}

export default function SpeechDetailPage() {
  const { id } = useParams<{ id: string }>();
  const speechId = id ?? "";
  const { hash } = useLocation();
  const [searchParams] = useSearchParams();
  const highlightChunkId = hash.startsWith("#chunk-") ? hash.slice("#chunk-".length) : null;

  // Cross-row query highlight when the user came from /search?q=...
  const queryTerms = useMemo(
    () => tokenizeQuery(searchParams.get("q") ?? ""),
    [searchParams],
  );

  // Reset window state when navigating between speeches.
  const [before, setBefore] = useState(DEFAULT_WINDOW);
  const [after, setAfter] = useState(DEFAULT_WINDOW);
  const [all, setAll] = useState(false);
  const [hideProcedural, setHideProcedural] = useState(false);
  useEffect(() => {
    setBefore(DEFAULT_WINDOW);
    setAfter(DEFAULT_WINDOW);
    setAll(false);
  }, [speechId]);

  const ctxOpts = useMemo(() => ({ before, after, all }), [before, after, all]);

  const focalState = useSpeech(speechId);
  const contextState = useSpeechContext(speechId, ctxOpts);
  const relatedState = useRelatedSpeeches(speechId, highlightChunkId, 5);

  const focalRef = useRef<HTMLElement | null>(null);
  const relatedRef = useRef<HTMLElement | null>(null);
  const [pulseRelated, setPulseRelated] = useState(false);

  const jumpToRelated = () => {
    relatedRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    setPulseRelated(true);
    window.setTimeout(() => setPulseRelated(false), 1400);
  };

  useDocumentTitle(
    focalState.data?.speech ? `${focalState.data.speech.speaker_name_raw} — speech` : null,
  );

  // Scroll focal speech (or its highlighted chunk) into view once both
  // fetches resolve. Doing this only after surrounding rows mount avoids
  // the focal row jumping after the initial scroll fires.
  useEffect(() => {
    if (!focalState.data || contextState.loading) return;
    const target = highlightChunkId
      ? document.getElementById(`chunk-${highlightChunkId}`)
      : focalRef.current;
    if (!target) return;
    const id = requestAnimationFrame(() => {
      target.scrollIntoView({ behavior: "smooth", block: "center" });
    });
    return () => cancelAnimationFrame(id);
  }, [focalState.data, contextState.loading, highlightChunkId]);

  // Keyboard nav: j/k step focus between exchange rows; ? toggles help.
  const [showHelp, setShowHelp] = useState(false);
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      // Don't intercept while the user is typing in a control.
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable)) return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === "j" || e.key === "k") {
        e.preventDefault();
        const rows = Array.from(document.querySelectorAll<HTMLElement>(".exchange-row"));
        if (rows.length === 0) return;
        const mid = window.innerHeight / 2;
        const idx = rows.findIndex((r) => {
          const rect = r.getBoundingClientRect();
          return rect.top + rect.height / 2 > mid;
        });
        const cur = idx === -1 ? rows.length - 1 : idx;
        const next = e.key === "j" ? Math.min(rows.length - 1, cur + 1) : Math.max(0, cur - 1);
        rows[next]?.scrollIntoView({ behavior: "smooth", block: "center" });
      } else if (e.key === "?") {
        setShowHelp((v) => !v);
      } else if (e.key === "Escape") {
        setShowHelp(false);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  if (focalState.loading) {
    return <div className="speech-detail speech-detail--state">Loading speech…</div>;
  }
  if (focalState.notFound) {
    return (
      <div className="speech-detail speech-detail--state">
        <Link to="/search" className="speech-detail__back">← Back to search</Link>
        <h1>Speech not found</h1>
        <p>No speech record with ID <code>{speechId}</code>.</p>
      </div>
    );
  }
  if (focalState.error) {
    return (
      <div className="speech-detail speech-detail--state">
        <Link to="/search" className="speech-detail__back">← Back to search</Link>
        <h1>Couldn't load speech</h1>
        <p>{focalState.error.message}</p>
      </div>
    );
  }
  if (!focalState.data) return null;

  const { speech, chunks } = focalState.data;
  const date = formatDate(speech.spoken_at);
  const ctx = contextState.data;

  // Apply the procedural-mute filter to context arrays only — never hide the
  // focal speech (the user clicked through to it on purpose).
  const beforeRows = ctx?.before ?? [];
  const afterRows = ctx?.after ?? [];
  const filteredBefore = hideProcedural ? beforeRows.filter((s) => !isProcedural(s)) : beforeRows;
  const filteredAfter = hideProcedural ? afterRows.filter((s) => !isProcedural(s)) : afterRows;
  const hiddenCount =
    (beforeRows.length - filteredBefore.length) + (afterRows.length - filteredAfter.length);

  return (
    <article className="speech-detail">
      <Link to="/search" className="speech-detail__back">← Back to search</Link>

      <header className="speech-detail__header">
        <div className="speech-detail__meta-row">
          {date && (
            <span className="speech-detail__meta-pill">
              <time dateTime={speech.spoken_at ?? ""}>{date}</time>
            </span>
          )}
          {speech.session && (
            <span className="speech-detail__meta-pill">
              {speech.session.parliament_number}th Parl., Sess. {speech.session.session_number}
            </span>
          )}
          <span className="speech-detail__meta-pill">
            {speech.level}
            {speech.province_territory ? ` · ${speech.province_territory}` : ""}
          </span>
          <span className="speech-detail__meta-pill">{speech.language.toUpperCase()}</span>
          <button
            type="button"
            className={
              hideProcedural
                ? "speech-detail__toggle speech-detail__toggle--on"
                : "speech-detail__toggle"
            }
            onClick={() => setHideProcedural((v) => !v)}
            title="Hide Speaker / Some hon. members / chair interruptions"
          >
            {hideProcedural ? `Procedural rows hidden${hiddenCount ? ` (${hiddenCount})` : ""}` : "Hide procedural"}
          </button>
          <button
            type="button"
            className="speech-detail__toggle"
            onClick={() => setShowHelp((v) => !v)}
            title="Keyboard shortcuts"
            aria-label="Show keyboard shortcuts"
          >
            ?
          </button>
          <CitationButton speech={speech} />
        </div>
      </header>

      {showHelp && (
        <div className="speech-detail__help" role="dialog" aria-label="Keyboard shortcuts">
          <div className="speech-detail__help-row"><kbd>j</kbd> / <kbd>k</kbd> next / previous speech</div>
          <div className="speech-detail__help-row"><kbd>?</kbd> toggle this help</div>
          <div className="speech-detail__help-row"><kbd>Esc</kbd> close</div>
        </div>
      )}

      <section className="speech-detail__exchange" aria-label="Hansard exchange">
        <div className="speech-detail__expand-bar speech-detail__expand-bar--top">
          {ctx?.has_more_before && !all && (
            <button
              type="button"
              className="speech-detail__expand-btn"
              onClick={() => setBefore((n) => n + STEP)}
              disabled={contextState.loading}
            >
              ↑ Show {STEP} earlier
            </button>
          )}
          {ctx && !all && (ctx.has_more_before || ctx.has_more_after) && (
            <button
              type="button"
              className="speech-detail__expand-btn speech-detail__expand-btn--strong"
              onClick={() => setAll(true)}
              disabled={contextState.loading}
            >
              Load full sitting
            </button>
          )}
        </div>

        {filteredBefore.map((s) => (
          <ExchangeSpeechRow key={s.id} kind="context" speech={s} queryTerms={queryTerms} />
        ))}

        <ExchangeSpeechRow
          ref={focalRef}
          kind="focal"
          speech={speech}
          chunks={chunks}
          highlightChunkId={highlightChunkId}
          queryTerms={queryTerms}
          similarCount={relatedState.data?.items.length ?? 0}
          onJumpToSimilar={jumpToRelated}
        />

        {filteredAfter.map((s) => (
          <ExchangeSpeechRow key={s.id} kind="context" speech={s} queryTerms={queryTerms} />
        ))}

        <div className="speech-detail__expand-bar speech-detail__expand-bar--bottom">
          {ctx?.has_more_after && !all && (
            <button
              type="button"
              className="speech-detail__expand-btn"
              onClick={() => setAfter((n) => n + STEP)}
              disabled={contextState.loading}
            >
              ↓ Show {STEP} later
            </button>
          )}
          {all && (ctx?.has_more_before || ctx?.has_more_after) && (
            <span className="speech-detail__expand-note">
              Sitting truncated — view the full transcript on{" "}
              <a href={speech.source_url} target="_blank" rel="noopener noreferrer">
                Hansard ↗
              </a>
            </span>
          )}
        </div>

        {contextState.loading && !ctx && (
          <div className="speech-detail__context-loading">Loading exchange context…</div>
        )}
      </section>

      <RelatedSpeechesPanel
        ref={relatedRef}
        items={relatedState.data?.items ?? []}
        loading={relatedState.loading}
        focal={{
          speakerName: speech.politician?.name ?? speech.speaker_name_raw,
          party: speech.party_at_time ?? speech.politician?.party ?? null,
          photoUrl: speech.politician?.photo_url ?? null,
        }}
        pulse={pulseRelated}
      />
    </article>
  );
}
