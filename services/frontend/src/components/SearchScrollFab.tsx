import { useEffect, useState } from "react";
import { useIsMobile } from "../hooks/useMediaQuery";

/**
 * Phone-only floating action button for the search results page. After
 * the user has scrolled past the search input + filters, surfaces a
 * "scroll to top" affordance so they can re-edit the query / open the
 * SaveSearch / Report buttons without finger-walking back up the list.
 *
 * Hidden on desktop — the page is short enough there that a FAB would
 * just be visual clutter.
 */
export function SearchScrollFab() {
  const isMobile = useIsMobile();
  const [show, setShow] = useState(false);

  useEffect(() => {
    if (!isMobile) {
      setShow(false);
      return;
    }
    function onScroll() {
      // Show once the user is meaningfully past the toolbar (~3 viewport heights).
      setShow(window.scrollY > window.innerHeight * 0.6);
    }
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
    return () => window.removeEventListener("scroll", onScroll);
  }, [isMobile]);

  if (!isMobile || !show) return null;

  return (
    <button
      type="button"
      className="search-scroll-fab"
      onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}
      aria-label="Back to search bar"
      title="Back to search bar"
    >
      <span aria-hidden="true">↑</span>
    </button>
  );
}
