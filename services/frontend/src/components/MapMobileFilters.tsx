import { useEffect, useState, type ReactNode } from "react";
import { useIsNarrow } from "../hooks/useMediaQuery";

/**
 * Wraps the PartyFilter + Filters block on the Map page. On viewports
 * where the toolbar reflows to multiple stacked rows (<= 900px), shows a
 * single "Filters" button that reveals the controls in a bottom sheet.
 * On wider screens the children are rendered inline as before.
 *
 * Children are always rendered (never unmounted) so internal control
 * state in PartyFilter / Filters survives a sheet open/close.
 */
interface Props {
  children: ReactNode;
}

export function MapMobileFilters({ children }: Props) {
  const collapse = useIsNarrow();
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!collapse) setOpen(false);
  }, [collapse]);

  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  if (!collapse) {
    return <>{children}</>;
  }

  return (
    <>
      <button
        type="button"
        className="map-mobile-filters__trigger"
        onClick={() => setOpen(true)}
        aria-haspopup="dialog"
        aria-expanded={open}
      >
        <span aria-hidden="true">⚙</span> Filters
      </button>

      {open && (
        <div
          className="mobile-more-sheet__backdrop"
          onClick={() => setOpen(false)}
          role="presentation"
        >
          <div
            className="mobile-more-sheet map-mobile-filters__sheet"
            role="dialog"
            aria-modal="true"
            aria-label="Map filters"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mobile-more-sheet__handle" aria-hidden="true" />
            <h2 className="mobile-more-sheet__title">Map filters</h2>
            <div className="map-mobile-filters__body">{children}</div>
            <button
              type="button"
              className="mobile-more-sheet__close"
              onClick={() => setOpen(false)}
            >
              Done
            </button>
          </div>
        </div>
      )}
    </>
  );
}
