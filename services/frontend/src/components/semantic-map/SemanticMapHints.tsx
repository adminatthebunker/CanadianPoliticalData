import { useEffect, useState } from "react";
import type { ViewMode } from "../../pages/SemanticMapPage";

interface Props {
  mode: ViewMode;
  level: 1 | 2 | 3 | 4;
  onResetView: () => void;
}

// Floating overlay rendered inside the stage that explains the controls
// and offers a "Reset view" action. Auto-collapses to a single button
// after a short timeout OR the first time the user interacts with the
// stage — once people know the controls, the hints become noise.
export default function SemanticMapHints({ mode, level, onResetView }: Props) {
  const [open, setOpen] = useState(true);

  // Auto-collapse after 8s on first mount of each level. We watch
  // `level` so the hints reappear briefly when the user drills in,
  // since the available actions change ("click to drill in" stops
  // working once you're at L3).
  useEffect(() => {
    setOpen(true);
    const t = window.setTimeout(() => setOpen(false), 8000);
    return () => window.clearTimeout(t);
  }, [level, mode]);

  const drillHint = level < 4 ? "Drill into cluster" : "View speeches";

  return (
    <div className={`semantic-map__hints${open ? " is-open" : ""}`}>
      <button
        type="button"
        className="semantic-map__hints-toggle"
        onClick={() => setOpen((v) => !v)}
        aria-label={open ? "Hide controls" : "Show controls"}
        aria-expanded={open}
      >
        {open ? "×" : "?"}
      </button>
      {open && (
        <div className="semantic-map__hints-body">
          <div className="semantic-map__hints-title">How to navigate</div>
          <ul className="semantic-map__hints-list">
            {mode === "3d" && (
              <>
                <li>
                  <kbd>Drag</kbd>
                  <span>Orbit the cloud</span>
                </li>
                <li>
                  <kbd>Scroll</kbd>
                  <span>Zoom in / out</span>
                </li>
                <li>
                  <kbd>Right-drag</kbd>
                  <span>Pan</span>
                </li>
              </>
            )}
            <li>
              <kbd>Hover</kbd>
              <span>Focus a cluster + its connections</span>
            </li>
            <li>
              <kbd>Click</kbd>
              <span>{drillHint}</span>
            </li>
          </ul>
          {mode === "3d" && (
            <button
              type="button"
              className="semantic-map__hints-reset"
              onClick={onResetView}
            >
              ↻ Reset view
            </button>
          )}
        </div>
      )}
    </div>
  );
}
