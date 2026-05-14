import { useEffect } from "react";

/**
 * Injects a `<link rel="alternate" type="application/rss+xml">` into
 * <head> while the component is mounted, then removes it on unmount.
 * Lets RSS readers and the browser's "feed" affordance auto-discover
 * the feed without a visible UI element on the page.
 *
 * Pair with the public RSS endpoints in services/api/src/routes/feeds.ts —
 * the politician-profile page wires this up for the per-politician feed.
 */
export function useRssAutoDiscovery(href: string | null, title?: string) {
  useEffect(() => {
    if (!href) return;
    const link = document.createElement("link");
    link.rel = "alternate";
    link.type = "application/rss+xml";
    link.href = href;
    if (title) link.title = title;
    document.head.appendChild(link);
    return () => {
      document.head.removeChild(link);
    };
  }, [href, title]);
}
