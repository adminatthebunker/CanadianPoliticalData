import { useEffect, useMemo, useState } from "react";
import { Link, useLocation, useSearchParams } from "react-router-dom";
import { useDocumentTitle } from "../hooks/useDocumentTitle";
import {
  buildSpeechSearchQuery,
  effectivePoliticianIds,
  getRecentSearchLatencyMs,
  MAX_POLITICIAN_PINS,
  SPEECH_TYPE_VALUES,
  useSpeechSearch,
  useSpeechSearchCount,
  useSpeechSearchMeta,
  type PoliticianSort,
  type SpeechSearchFilter,
  type SpeechType,
} from "../hooks/useSpeechSearch";
import { MapleLeafLoader } from "../components/MapleLeafLoader";
import { SpeechFilters } from "../components/SpeechFilters";
import { SpeechResultCard } from "../components/SpeechResultCard";
import { SearchDashboard } from "../components/SearchDashboard";
import { SaveSearchButton } from "../components/SaveSearchButton";
import { SearchScrollFab } from "../components/SearchScrollFab";
import { PoliticianResultGroup } from "../components/PoliticianResultGroup";
import { PoliticianQuickNav } from "../components/PoliticianQuickNav";
import { PoliticianPinChips } from "../components/PoliticianPinChips";
import { AIContradictionAnalysis } from "../components/AIContradictionAnalysis";
import { AnchorChunkBanner } from "../components/AnchorChunkBanner";
import { SearchMapView } from "../components/SearchMapView";
import { AIFullReportButton } from "../components/AIFullReportButton";
import { useAIAnalyzeMeta } from "../hooks/useAIAnalyzeMeta";
import { useReportsMeta } from "../hooks/useReportsMeta";
import { useUserAuth } from "../hooks/useUserAuth";
import "../styles/hansard-search.css";

type ViewMode = "timeline" | "politician" | "analysis" | "map";

function readView(params: URLSearchParams): ViewMode {
  const v = params.get("view");
  if (v === "politician") return "politician";
  if (v === "analysis") return "analysis";
  if (v === "map") return "map";
  return "timeline";
}

const POLITICIAN_SORTS: readonly PoliticianSort[] = [
  "mentions",
  "best_match",
  "avg_match",
  "keyword_hits",
] as const;

function readSort(params: URLSearchParams): PoliticianSort {
  const s = params.get("sort");
  return (POLITICIAN_SORTS as readonly string[]).includes(s ?? "")
    ? (s as PoliticianSort)
    : "mentions";
}

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function parseMinSimilarity(raw: string | null): number | undefined {
  if (raw == null) return undefined;
  const n = Number(raw);
  // 0 is meaningful — explicit "all matches" override of the server's
  // 0.5 default. Without accepting 0 here the URL-roundtrip would
  // silently re-apply the default on the next page-load.
  if (!Number.isFinite(n) || n < 0 || n > 1) return undefined;
  return n;
}

// Server-side default applied by /speeches and /facets when
// min_similarity is omitted. Mirrored on the frontend so the slider
// and chip can render the implicit value without forcing every URL to
// carry it. Keep this in sync with the API constant.
const DEFAULT_MIN_SIMILARITY = 0.5;

function parsePositiveInt(raw: string | null): number | undefined {
  if (!raw) return undefined;
  const n = Number(raw);
  if (!Number.isInteger(n) || n <= 0) return undefined;
  return n;
}

function parseSpeechTypes(params: URLSearchParams): SpeechType[] | undefined {
  const allowed = new Set<string>(SPEECH_TYPE_VALUES);
  const seen = new Set<SpeechType>();
  const out: SpeechType[] = [];
  for (const v of params.getAll("speech_type")) {
    if (allowed.has(v) && !seen.has(v as SpeechType)) {
      seen.add(v as SpeechType);
      out.push(v as SpeechType);
    }
  }
  return out.length > 0 ? out : undefined;
}

function readFilter(params: URLSearchParams): SpeechSearchFilter {
  const lang = params.get("lang");
  const level = params.get("level");
  const view = readView(params);
  const rawIds = params.getAll("politician_id").filter(v => UUID_RE.test(v));
  // Dedupe while preserving order; cap at 10 to match API.
  const seen = new Set<string>();
  const politician_ids: string[] = [];
  for (const id of rawIds) {
    if (!seen.has(id) && politician_ids.length < 10) {
      seen.add(id);
      politician_ids.push(id);
    }
  }
  // Parliament + session must arrive together; one without the other is
  // ambiguous (which session of which parliament?) so drop both.
  const parliament = parsePositiveInt(params.get("parliament"));
  const session = parsePositiveInt(params.get("session"));
  const havePair = parliament != null && session != null;
  const rawAnchor = params.get("anchor_chunk_id");
  const anchor_chunk_id = rawAnchor && UUID_RE.test(rawAnchor) ? rawAnchor : undefined;
  return {
    q: params.get("q") ?? "",
    anchor_chunk_id,
    lang: (lang === "en" || lang === "fr" || lang === "any" ? lang : "any") as SpeechSearchFilter["lang"],
    level: (level === "federal" || level === "provincial" || level === "municipal"
      ? level
      : undefined) as SpeechSearchFilter["level"],
    province_territory: params.get("province") ?? undefined,
    politician_ids: politician_ids.length > 0 ? politician_ids : undefined,
    party: params.get("party") ?? undefined,
    from: params.get("from") ?? undefined,
    to: params.get("to") ?? undefined,
    exclude_presiding: params.get("exclude_presiding") === "true" ? true : undefined,
    min_similarity: parseMinSimilarity(params.get("min_similarity")),
    parliament_number: havePair ? parliament : undefined,
    session_number: havePair ? session : undefined,
    speech_types: parseSpeechTypes(params),
    page: Number(params.get("page")) || 1,
    limit: 20,
    group_by: view === "politician" ? "politician" : "timeline",
    per_group_limit: view === "politician" ? 5 : undefined,
    sort: view === "politician" ? readSort(params) : undefined,
  };
}

function writeFilter(f: SpeechSearchFilter, view: ViewMode): URLSearchParams {
  const p = new URLSearchParams();
  if (f.q) p.set("q", f.q);
  if (f.lang && f.lang !== "any") p.set("lang", f.lang);
  if (f.level) p.set("level", f.level);
  if (f.province_territory) p.set("province", f.province_territory);
  if (f.party) p.set("party", f.party);
  if (f.from) p.set("from", f.from);
  if (f.to) p.set("to", f.to);
  if (f.exclude_presiding) p.set("exclude_presiding", "true");
  // Emit min_similarity whenever the caller explicitly set it AND the
  // value differs from the implicit server default. This keeps the URL
  // clean for default searches while preserving explicit overrides
  // (including "all matches" → 0).
  if (f.min_similarity != null && f.min_similarity !== DEFAULT_MIN_SIMILARITY) {
    p.set("min_similarity", String(f.min_similarity));
  }
  if (f.parliament_number != null && f.session_number != null) {
    p.set("parliament", String(f.parliament_number));
    p.set("session", String(f.session_number));
  }
  if (f.speech_types && f.speech_types.length > 0) {
    for (const t of f.speech_types) p.append("speech_type", t);
  }
  if (f.anchor_chunk_id) p.set("anchor_chunk_id", f.anchor_chunk_id);
  if (f.politician_ids && f.politician_ids.length > 0) {
    for (const id of f.politician_ids) p.append("politician_id", id);
  } else if (f.politician_id) {
    p.set("politician_id", f.politician_id);
  }
  if (f.page && f.page > 1) p.set("page", String(f.page));
  if (view === "politician") p.set("view", "politician");
  if (view === "analysis") p.set("view", "analysis");
  if (view === "map") p.set("view", "map");
  if (view === "politician" && f.sort && f.sort !== "mentions") p.set("sort", f.sort);
  return p;
}

const SORT_LABELS: Record<PoliticianSort, string> = {
  mentions: "Most mentions",
  best_match: "Strongest match",
  avg_match: "Avg quality",
  keyword_hits: "Keyword hits",
};

const SORT_DESCRIPTORS: Record<PoliticianSort, string> = {
  mentions: "ranked by number of on-topic quotes",
  best_match: "ranked by strongest single match",
  avg_match: "ranked by average match quality",
  keyword_hits: "ranked by exact keyword hits",
};

export default function HansardSearchPage() {
  useDocumentTitle("Hansard Search");
  const [searchParams, setSearchParams] = useSearchParams();
  const location = useLocation();
  const view = useMemo(() => readView(searchParams), [searchParams]);
  // What's been searched: derived from the URL. The network query, the
  // result rendering, and SaveSearch all hang off this.
  const appliedFilter = useMemo(() => readFilter(searchParams), [searchParams]);

  // What the user is currently editing. All filter inputs (text box,
  // chips, pickers, pin chips) write here; the URL only updates when the
  // user clicks "Search". Initialised from the URL so deep-linked /
  // reloaded searches arrive with their inputs pre-populated.
  const [draftFilter, setDraftFilter] = useState<SpeechSearchFilter>(appliedFilter);

  // Bumped by the "Search" button to force a cache-busting refetch even
  // when the canonical filter signature is unchanged. The module-level
  // LRU in useSpeechSearch keys on `qs`, so without this a re-search
  // with no filter delta would just re-read the cache.
  const [refreshEpoch, setRefreshEpoch] = useState(0);

  // External URL changes (back/forward, our own commits) re-seed the
  // draft. Our own commits already match what we're about to write, so
  // this is a no-op in that case; for back/forward it correctly snaps
  // the draft to the URL the user just navigated to.
  const appliedSig = searchParams.toString();
  useEffect(() => {
    setDraftFilter(appliedFilter);
    // appliedSig changes whenever any URL param does — finer-grained than
    // depending on appliedFilter (object identity flips every render).
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [appliedSig]);

  // Stage a partial update to the draft without touching the URL. Used
  // by every filter input that should *not* fire a new search until the
  // user explicitly commits.
  const stagePatch = (patch: Partial<SpeechSearchFilter>) => {
    setDraftFilter((prev) => ({ ...prev, ...patch }));
  };

  // Commit a partial update to the URL immediately. Used by post-search
  // operations (pagination, view tab, politician sort) where the user's
  // intent is "act on the current search now". Folds the patch into the
  // existing draft so any pending staged edits travel along with it.
  const commitPatch = (patch: Partial<SpeechSearchFilter>, viewOverride?: ViewMode) => {
    const next = { ...draftFilter, ...patch };
    setDraftFilter(next);
    setSearchParams(writeFilter(next, viewOverride ?? view), { replace: false });
  };

  // Commit the entire draft as the new searched-state. Resets to page 1
  // since the result set changes. Always bumps the refresh epoch so a
  // press of "Search" with unchanged filters still re-runs the query
  // (useful after new data has been ingested).
  const commitDraft = () => {
    const next = { ...draftFilter, page: 1 };
    setDraftFilter(next);
    setSearchParams(writeFilter(next, view), { replace: false });
    setRefreshEpoch((n) => n + 1);
  };

  const setView = (next: ViewMode) => {
    if (next === view) return;
    // Reset to page 1 on view change so users don't land on a p>1 that
    // happens to be empty in the other view.
    commitPatch({ page: 1 }, next);
  };

  const onQSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    commitDraft();
  };

  // Display-side IDs reflect the *draft* so the user sees pin edits in
  // the chip row immediately. Cap and dedupe still apply.
  const pinnedIds = effectivePoliticianIds(draftFilter);
  const pinnedSet = useMemo(() => new Set(pinnedIds), [pinnedIds.join(",")]);
  const pinCapReached = pinnedIds.length >= MAX_POLITICIAN_PINS;

  const togglePin = (id: string) => {
    const next = pinnedSet.has(id)
      ? pinnedIds.filter(p => p !== id)
      : pinnedIds.length < MAX_POLITICIAN_PINS
        ? [...pinnedIds, id]
        : pinnedIds;
    stagePatch({
      politician_ids: next.length > 0 ? next : undefined,
      politician_id: undefined,
      page: 1,
    });
  };

  const clearPins = () => {
    stagePatch({ politician_ids: undefined, politician_id: undefined, page: 1 });
  };

  // Search-enabled / dirty signals are computed off the *applied* filter
  // so the network call only runs once the user has clicked Search.
  const appliedPinnedIds = effectivePoliticianIds(appliedFilter);
  const hasAnyFilter = Boolean(
    appliedFilter.level ||
      appliedFilter.province_territory ||
      appliedFilter.party ||
      appliedFilter.from ||
      appliedFilter.to ||
      appliedPinnedIds.length > 0 ||
      (appliedFilter.parliament_number != null && appliedFilter.session_number != null) ||
      (appliedFilter.speech_types && appliedFilter.speech_types.length > 0),
  );
  const hasQuery = Boolean(appliedFilter.q && appliedFilter.q.trim());
  const hasAnchor = Boolean(appliedFilter.anchor_chunk_id);
  // Grouped mode is semantic-only (the API 400s on a q-less grouped call) —
  // anchor mode satisfies that since it provides a vector via the chunk.
  // Timeline still allows filter-only searches.
  const enabled =
    view === "politician"
      ? (hasQuery || hasAnchor)
      : (hasQuery || hasAnchor || hasAnyFilter);
  // Compare canonical query strings to detect "user has staged changes
  // not yet searched". Cheaper and more robust than a deep object diff,
  // and naturally ignores ordering of repeated params.
  const isDirty = useMemo(
    () => buildSpeechSearchQuery(draftFilter) !== buildSpeechSearchQuery(appliedFilter),
    [draftFilter, appliedFilter],
  );
  // Pins filter all three views so the results visibly narrow. To keep
  // "I can add more pins" possible even when the grid has collapsed to
  // just the pinned cards, the chip row hosts a typeahead picker
  // (PoliticianPinChips → PoliticianPinPicker).
  const { data, loading, error } = useSpeechSearch(appliedFilter, enabled, refreshEpoch);
  // Stage the count off in parallel — only meaningful for timeline /
  // analysis (grouped reports `total_politicians` instead) so we gate
  // by view to avoid a useless second request on the politician tab.
  const countEnabled = enabled && view !== "politician";
  const { data: countData, loading: countLoading } = useSpeechSearchCount(
    appliedFilter,
    countEnabled,
    refreshEpoch,
  );
  const meta = useSpeechSearchMeta();
  // Single meta fetch for the whole page (cached module-level), so
  // rendering 20 grouped cards doesn't produce 20 /contradictions/meta
  // calls. Only gets used on the politician view.
  const { meta: aiMeta } = useAIAnalyzeMeta();
  const { meta: reportsMeta } = useReportsMeta();
  // Auth state drives the anon "sign in to expand" banner above the
  // politician-grouped results, plus the per-card expand affordance
  // inside PoliticianResultGroup itself. `disabled` is true when the
  // server has accounts off (JWT_SECRET unset) — match SaveSearchButton's
  // posture and render no auth UI in that case.
  const { user, disabled: authDisabled } = useUserAuth();

  const page = appliedFilter.page ?? 1;
  const timeline = data && data.mode !== "grouped" ? data : null;
  const grouped = data && data.mode === "grouped" ? data : null;
  // Count is now staged: prefer the dedicated /speeches/count response
  // when it has landed, fall back to whatever shipped with the results
  // (always null with the new include_count=false path), and treat
  // "still pending" as null so the UI can render a "Counting…" cue.
  const total: number | null =
    countData?.total ?? timeline?.total ?? null;
  const limit = timeline?.limit ?? 20;
  const pages: number | null =
    total != null ? Math.max(1, Math.ceil(total / limit)) : null;
  const dashboardTotal =
    total ?? (grouped ? grouped.total_politicians : undefined);

  // Compact match-count line shown inline with the view tabs. View-aware
  // because timeline counts chunks whereas grouped counts politicians;
  // analysis surfaces the same chunk total as timeline so the user can
  // see at a glance how their filters narrow the corpus regardless of
  // which tab they're on.
  //
  // Returns a ReactNode (not a plain string) so the count-pending state
  // can swap in <MapleLeafLoader>: same spinning-leaf + Canadian pun
  // + bnkops.ca attribution that the main "Searching…" loader uses.
  const summaryNode: React.ReactNode = (() => {
    if (!enabled) return null;
    if (loading && !data) return "Searching…";
    if (error) return null;
    if (view === "timeline" || view === "analysis") {
      if (!timeline) return null;
      if (timeline.items.length === 0 && view === "timeline" && total === 0) {
        return "No matches";
      }
      const order =
        view === "analysis"
          ? null
          : timeline.mode === "semantic"
            ? "ranked by similarity"
            : "most recent first";
      // Page rows are in but the COUNT may still be running — render
      // the maple-leaf loader (sm) inline so the wait gets the same
      // pun rotation + attribution treatment the main search loader
      // uses. Once total lands the loader is replaced with the count.
      if (total == null && countLoading) {
        return (
          <>
            <MapleLeafLoader size="sm" label="Counting matches" />
            {order ? ` · ${order}` : null}
          </>
        );
      }
      const countFragment =
        total != null
          ? `${total.toLocaleString()} ${total === 1 ? "match" : "matches"}`
          : "Many matches";
      return order ? `${countFragment} · ${order}` : countFragment;
    }
    if (view === "politician" && grouped) {
      const n = grouped.groups.length;
      if (n === 0) return "No politicians matched";
      return `${n} ${n === 1 ? "politician" : "politicians"}`;
    }
    return null;
  })();

  return (
    <section className="hansard-search">
      <header className="hansard-search__header">
        <h2 className="hansard-search__title">
          <abbr title="The official transcript of what was said in Parliament">Hansard</abbr>{" "}
          Search
        </h2>
        <p className="hansard-search__subtitle">
          Search Canadian parliamentary speeches by meaning, not just exact words. Try{" "}
          <em>"rising cost of groceries"</em> — you'll find speeches that say "food prices" too.
          {" "}
          <a
            className="hansard-search__how-link"
            href="https://docs.canadianpoliticaldata.org/searching/how-it-works/"
            target="_blank"
            rel="noopener noreferrer"
          >
            How it works ↗
          </a>
        </p>
        {meta.data && meta.data.coverage < 0.99 && (
          <p className="hansard-search__banner" role="status">
            Backfill in progress: {(meta.data.coverage * 100).toFixed(0)}% of{" "}
            {meta.data.total_chunks.toLocaleString()} chunks searchable
            ({meta.data.embedded_chunks.toLocaleString()} indexed). Historical Parliaments are
            being embedded now.
          </p>
        )}
      </header>

      {appliedFilter.anchor_chunk_id && (
        <AnchorChunkBanner
          chunkId={appliedFilter.anchor_chunk_id}
          onClear={() => commitPatch({ anchor_chunk_id: undefined, page: 1 })}
        />
      )}

      <div className="hansard-search__search-row">
        <form className="hansard-search__form" onSubmit={onQSubmit} role="search">
          <label className="hansard-search__label" htmlFor="hansard-search-input">
            Search speeches
          </label>
          <input
            id="hansard-search-input"
            type="search"
            className="hansard-search__input"
            placeholder={
              appliedFilter.anchor_chunk_id
                ? "Type to switch to text search…"
                : 'e.g. "carbon pricing policy"'
            }
            value={draftFilter.q ?? ""}
            onChange={(e) => {
              const value = e.target.value;
              // Typing a query while anchor mode is active swaps back to
              // text mode — clear the anchor in the staged filter so the
              // next commit drops it from the URL.
              if (value && draftFilter.anchor_chunk_id) {
                stagePatch({ q: value, anchor_chunk_id: undefined });
              } else {
                stagePatch({ q: value });
              }
            }}
            autoFocus
          />
        </form>
        <button
          type="button"
          className={
            "hansard-search__update-btn" +
            (isDirty ? " hansard-search__update-btn--dirty" : "")
          }
          onClick={commitDraft}
          disabled={loading}
          title={
            isDirty
              ? "Run the search with your staged filters"
              : "Re-run the current search"
          }
        >
          {loading ? "Searching…" : isDirty ? "Search" : "Update search"}
        </button>
        {enabled && <SaveSearchButton filter={appliedFilter} />}
      </div>

      <div className="hansard-search__filter-row">
        <PoliticianPinChips
          ids={pinnedIds}
          onAdd={togglePin}
          onRemove={togglePin}
          onClearAll={clearPins}
        />
        <SpeechFilters
          value={draftFilter}
          onChange={stagePatch}
          alwaysShow={["min_similarity"]}
        />
      </div>

      <div className="hansard-search__tab-row">
        <div
          className="hansard-search__view-tabs"
          role="tablist"
          aria-label="Result view"
        >
          <button
            type="button"
            role="tab"
            aria-selected={view === "timeline"}
            className={
              "hansard-search__view-tab" +
              (view === "timeline" ? " hansard-search__view-tab--active" : "")
            }
            onClick={() => setView("timeline")}
          >
            Timeline
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={view === "politician"}
            className={
              "hansard-search__view-tab" +
              (view === "politician" ? " hansard-search__view-tab--active" : "")
            }
            onClick={() => setView("politician")}
            title="Group results by politician to see each speaker's statements on the topic side-by-side"
          >
            By politician
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={view === "analysis"}
            className={
              "hansard-search__view-tab" +
              (view === "analysis" ? " hansard-search__view-tab--active" : "")
            }
            onClick={() => setView("analysis")}
            title="See charts summarising who, what, and when for this search"
          >
            Analysis
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={view === "map"}
            className={
              "hansard-search__view-tab" +
              (view === "map" ? " hansard-search__view-tab--active" : "")
            }
            onClick={() => setView("map")}
            title="Explore results as a clickable mind-graph in semantic space"
          >
            Map
          </button>
        </div>

        {summaryNode && (
          <p className="hansard-search__summary-inline" aria-live="polite">
            {summaryNode}
          </p>
        )}

        {view === "politician" && (
          <div
            className="politician-sort-chips"
            role="tablist"
            aria-label="Sort politicians by"
          >
            {POLITICIAN_SORTS.map((s) => {
              const active = (appliedFilter.sort ?? "mentions") === s;
              return (
                <button
                  key={s}
                  type="button"
                  role="tab"
                  aria-selected={active}
                  className={
                    "politician-sort-chips__chip" +
                    (active ? " politician-sort-chips__chip--active" : "")
                  }
                  onClick={() => commitPatch({ sort: s, page: 1 })}
                >
                  {SORT_LABELS[s]}
                </button>
              );
            })}
          </div>
        )}
      </div>

      {view === "analysis" && (
        <SearchDashboard
          filter={appliedFilter}
          enabled={enabled}
          totalMatches={dashboardTotal}
          defaultOpen
        />
      )}

      {view === "map" && (
        <SearchMapView
          query={appliedFilter.q ?? ""}
          searchItems={timeline?.items ?? []}
          searchLoading={loading}
          anchorChunkId={appliedFilter.anchor_chunk_id ?? null}
        />
      )}

      <div className="hansard-search__results" hidden={view === "map"}>
        {!enabled && view !== "analysis" && view !== "map" && (
          <p className="hansard-search__hint">
            {view === "politician"
              ? "Type a search query above and press Search to group results by politician."
              : "Type a phrase or set a filter above, then press Search."}
          </p>
        )}

        {view === "analysis" && !enabled && (
          <p className="hansard-search__hint">
            Type a search query above and press Search to see analysis charts.
          </p>
        )}

        {enabled && loading && !data && (
          <MapleLeafLoader
            label="Searching…"
            hint={(() => {
              const ms = getRecentSearchLatencyMs();
              if (ms == null) return null;
              const s = ms / 1000;
              return s < 1 ? `typically ~${ms}ms` : `typically ~${s.toFixed(1)}s`;
            })()}
          />
        )}

        {error && (
          <p className="hansard-search__error" role="alert">
            Couldn't run that search: {error.message}
          </p>
        )}

        {enabled && view === "timeline" && timeline && timeline.items.length === 0 && !loading && (
          <p className="hansard-search__hint">
            {page > 1
              ? "No more results — try going back a page."
              : "No speeches match these filters."}
          </p>
        )}

        {enabled && view === "politician" && grouped && grouped.groups.length === 0 && !loading && (
          <p className="hansard-search__hint">
            No politicians matched this query.{" "}
            <button
              type="button"
              className="hansard-search__link-button"
              onClick={() => setView("timeline")}
            >
              Switch to Timeline
            </button>{" "}
            to see individual results, including unresolved speakers.
          </p>
        )}

        {view === "timeline" && timeline && timeline.items.length > 0 && (
          <>
            <ol className="hansard-search__list" aria-label="Search results">
              {timeline.items.map((item) => (
                <li key={item.chunk_id} className="hansard-search__item">
                  <SpeechResultCard item={item} />
                </li>
              ))}
            </ol>

            {/* Render the pager whenever there's a page-2 to reach. With
             * staged counting, `pages` may still be null while the count
             * is in flight; in that case we hide the upper bound but
             * keep Next enabled until the API actually returns a short
             * page. The `timeline.items.length >= limit` heuristic
             * means "there's likely a next page" without needing total. */}
            {(pages != null ? pages > 1 : timeline.items.length >= limit || page > 1) && (
              <nav className="hansard-search__pager" aria-label="Pagination">
                <button
                  type="button"
                  disabled={page <= 1}
                  onClick={() => commitPatch({ page: Math.max(1, page - 1) })}
                >
                  ← Previous
                </button>
                <span className="hansard-search__pager-label">
                  {pages != null ? `Page ${page} of ${pages}` : `Page ${page}`}
                </span>
                <button
                  type="button"
                  disabled={
                    pages != null
                      ? page >= pages
                      : timeline.items.length < limit
                  }
                  onClick={() => commitPatch({ page: page + 1 })}
                >
                  Next →
                </button>
              </nav>
            )}
          </>
        )}

        {view === "politician" && grouped && grouped.groups.length > 0 && (
          <>
            <PoliticianQuickNav
              groups={grouped.groups}
              sort={appliedFilter.sort ?? "mentions"}
              pinnedIds={pinnedSet}
              onTogglePin={togglePin}
              pinCapReached={pinCapReached}
            />

            {/*
             * Anon-user advert: surface the gated "expand any card to
             * read all that politician's quotes" feature so it's visible
             * before the user has to click into a card to discover it.
             * Only renders when (a) accounts are enabled server-side,
             * (b) the visitor is signed out, and (c) at least one card
             * actually has more quotes than its initial 5 — otherwise
             * the CTA promises something the page can't deliver.
             */}
            {!user && !authDisabled && grouped.groups.some(g => g.mention_count > g.chunks.length) && (
              <div className="hansard-search__expand-advert" role="note">
                <span className="hansard-search__expand-advert-body">
                  <strong>Signed-in users can expand any card</strong> to read every matching quote
                  from that politician — not just the top 5.
                </span>
                <Link
                  to={`/login?from=${encodeURIComponent(location.pathname + location.search)}`}
                  className="hansard-search__expand-advert-cta"
                >
                  Sign in to unlock →
                </Link>
              </div>
            )}

            <div className="hansard-search__summary">
              {grouped.total_politicians} {grouped.total_politicians === 1 ? "politician" : "politicians"}
              {" · "}
              {SORT_DESCRIPTORS[appliedFilter.sort ?? "mentions"]}
              {" · oldest quote first within each card"}
            </div>

            <ol className="hansard-search__groups" aria-label="Politicians with matching speeches">
              {grouped.groups.map((g) => {
                // Key on politician id + everything that changes what
                // "matching quotes for this politician" means. Ensures
                // any expanded card with cached pageData invalidates
                // when the parent filter shifts underneath it.
                const cardKey = [
                  g.politician.id,
                  appliedFilter.q ?? "",
                  appliedFilter.lang ?? "",
                  appliedFilter.level ?? "",
                  appliedFilter.province_territory ?? "",
                  appliedFilter.party ?? "",
                  appliedFilter.from ?? "",
                  appliedFilter.to ?? "",
                  appliedFilter.exclude_presiding ? "1" : "0",
                ].join("|");
                return (
                <li key={cardKey} className="hansard-search__group-item">
                  <PoliticianResultGroup
                    group={g}
                    parentFilter={appliedFilter}
                    footer={
                      <AIContradictionAnalysis
                        politicianId={g.politician.id}
                        politicianName={g.politician.name ?? "this politician"}
                        query={appliedFilter.q ?? ""}
                        chunks={g.chunks}
                        meta={aiMeta}
                        reportsMeta={reportsMeta}
                        actionSlot={
                          <AIFullReportButton
                            politicianId={g.politician.id}
                            query={appliedFilter.q ?? ""}
                            meta={reportsMeta}
                          />
                        }
                      />
                    }
                  />
                </li>
                );
              })}
            </ol>

            <nav className="hansard-search__pager" aria-label="Pagination">
              <button
                type="button"
                disabled={page <= 1}
                onClick={() => commitPatch({ page: Math.max(1, page - 1) })}
              >
                ← Previous
              </button>
              <span className="hansard-search__pager-label">Page {page}</span>
              <button
                type="button"
                disabled={grouped.groups.length < grouped.limit}
                onClick={() => commitPatch({ page: page + 1 })}
              >
                Next →
              </button>
            </nav>
          </>
        )}
      </div>
      <SearchScrollFab />
    </section>
  );
}
