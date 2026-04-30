import type { ViewMode } from "../../pages/SemanticMapPage";

interface Props {
  mode: ViewMode;
  onChange: (next: ViewMode) => void;
  disabled3d?: boolean;
}

export default function ModeToggle({ mode, onChange, disabled3d }: Props) {
  return (
    <div className="semantic-map__mode-toggle" role="tablist" aria-label="Render mode">
      <button
        type="button"
        role="tab"
        aria-selected={mode === "2d"}
        className={`semantic-map__mode-btn${mode === "2d" ? " is-active" : ""}`}
        onClick={() => onChange("2d")}
      >
        2D
      </button>
      <button
        type="button"
        role="tab"
        aria-selected={mode === "3d"}
        className={`semantic-map__mode-btn${mode === "3d" ? " is-active" : ""}`}
        onClick={() => onChange("3d")}
        disabled={disabled3d}
        title={disabled3d ? "3D unavailable on this device" : "Switch to 3D"}
      >
        3D
      </button>
    </div>
  );
}
