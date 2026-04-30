import { useEffect, useState } from "react";

/**
 * Subscribes to a CSS media query and returns whether it currently matches.
 * SSR-safe: returns `false` during the first render on environments without
 * `window` (the matchMedia subscription wires up after mount).
 */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState<boolean>(() => {
    if (typeof window === "undefined") return false;
    return window.matchMedia(query).matches;
  });

  useEffect(() => {
    if (typeof window === "undefined") return;
    const mql = window.matchMedia(query);
    const handler = (e: MediaQueryListEvent) => setMatches(e.matches);
    setMatches(mql.matches);
    mql.addEventListener("change", handler);
    return () => mql.removeEventListener("change", handler);
  }, [query]);

  return matches;
}

/**
 * Canonical breakpoints. Mirror these in CSS @media rules so the JS-side
 * branching in components matches the layout the user actually sees.
 *
 * - sm: phone (single column)
 * - md: large phone / small tablet (key transition for nav, filters, tables)
 * - lg: tablet → desktop hand-off
 */
export const BP = {
  sm: "(max-width: 480px)",
  md: "(max-width: 640px)",
  lg: "(max-width: 900px)",
  touch: "(hover: none)",
} as const;

export const useIsMobile = () => useMediaQuery(BP.md);
export const useIsNarrow = () => useMediaQuery(BP.lg);
export const useIsTouch = () => useMediaQuery(BP.touch);
