import { useEffect, useMemo, useState } from "react";
import type { ClusterRow } from "../../hooks/useSemanticMap";

// Search across all 4,381 cluster labels client-side. The
// /clusters/all endpoint already loaded everything, so this is pure
// in-memory string matching — sub-millisecond on a 1MB payload.
//
// Scoring (highest → lowest):
//   1. Label starts with the query
//   2. Any whitespace-separated word starts with the query
//   3. Label contains the query as a substring
//
// Within each tier, more populous clusters rank ahead of smaller
// ones, so a generic query like "education" surfaces the L1 anchor
// before its L4 grandchildren.

interface Props {
  allClusters: ClusterRow[];
  onJump: (cluster: ClusterRow) => void;
}

interface Match {
  cluster: ClusterRow;
  score: number;
}

function scoreMatch(label: string, q: string): number {
  if (label === q) return 1000;
  if (label.startsWith(q)) return 500;
  // Word-prefix
  for (const word of label.split(/[\s,]+/)) {
    if (word.startsWith(q)) return 300;
  }
  if (label.includes(q)) return 100;
  return 0;
}

const MAX_RESULTS = 25;
const DEBOUNCE_MS = 120;

export default function SemanticMapSearch({ allClusters, onJump }: Props) {
  const [raw, setRaw] = useState("");
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [activeIdx, setActiveIdx] = useState(0);

  // Debounce so each keystroke doesn't re-scan the whole list.
  useEffect(() => {
    if (!raw.trim()) {
      setQuery("");
      return;
    }
    const t = window.setTimeout(() => setQuery(raw.trim().toLowerCase()), DEBOUNCE_MS);
    return () => window.clearTimeout(t);
  }, [raw]);

  const matches = useMemo<Match[]>(() => {
    if (!query) return [];
    const out: Match[] = [];
    for (const c of allClusters) {
      const label = c.label.toLowerCase();
      const s = scoreMatch(label, query);
      if (s > 0) out.push({ cluster: c, score: s });
    }
    out.sort((a, b) => {
      if (b.score !== a.score) return b.score - a.score;
      return b.cluster.member_count - a.cluster.member_count;
    });
    return out.slice(0, MAX_RESULTS);
  }, [allClusters, query]);

  // Reset highlight when results change.
  useEffect(() => {
    setActiveIdx(0);
  }, [matches]);

  const choose = (m: Match) => {
    onJump(m.cluster);
    setRaw("");
    setQuery("");
    setOpen(false);
  };

  return (
    <div className="semantic-map__search">
      <input
        type="search"
        className="semantic-map__search-input"
        placeholder="Search topics…"
        value={raw}
        onChange={(e) => {
          setRaw(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => {
          // Delay so an in-progress click on a result registers first.
          window.setTimeout(() => setOpen(false), 120);
        }}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") {
            e.preventDefault();
            setActiveIdx((i) => Math.min(i + 1, matches.length - 1));
          } else if (e.key === "ArrowUp") {
            e.preventDefault();
            setActiveIdx((i) => Math.max(i - 1, 0));
          } else if (e.key === "Enter") {
            e.preventDefault();
            const m = matches[activeIdx];
            if (m) choose(m);
          } else if (e.key === "Escape") {
            setRaw("");
            setQuery("");
            setOpen(false);
            (e.currentTarget as HTMLInputElement).blur();
          }
        }}
        aria-label="Search topics"
      />
      {open && query && matches.length > 0 && (
        <ul className="semantic-map__search-results" role="listbox">
          {matches.map((m, i) => {
            const truncated = m.cluster.label.length > 56
              ? `${m.cluster.label.slice(0, 54)}…`
              : m.cluster.label;
            return (
              <li
                key={m.cluster.id}
                role="option"
                aria-selected={i === activeIdx}
                className={
                  "semantic-map__search-result" +
                  (i === activeIdx ? " is-active" : "")
                }
                // onMouseDown fires before onBlur of the input — important
                // so the input's blur-induced close doesn't tear down
                // before the click is processed.
                onMouseDown={(e) => {
                  e.preventDefault();
                  choose(m);
                }}
                onMouseEnter={() => setActiveIdx(i)}
              >
                <span className="semantic-map__search-result-label">
                  {truncated}
                </span>
                <span className="semantic-map__search-result-meta">
                  L{m.cluster.level} · {m.cluster.member_count.toLocaleString()}
                </span>
              </li>
            );
          })}
        </ul>
      )}
      {open && query && matches.length === 0 && (
        <div className="semantic-map__search-results semantic-map__search-empty">
          No topics match "{query}"
        </div>
      )}
    </div>
  );
}
