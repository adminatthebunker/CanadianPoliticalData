/**
 * Tiny in-tab event bus for async-job lifecycle nudges.
 *
 * Problem: ActiveJobsIndicator polls /me/scrape-jobs?active=true and
 * /me/reports?active=true every 25s when idle, every 3.5s when ≥1 job
 * is running. A user who kicks off a scrape or report right after the
 * idle tick can wait up to 25s before the pill appears — a UX wart
 * that makes the system feel unresponsive.
 *
 * Fix: any code that successfully enqueues a job calls
 * `notifyJobStarted()`. The indicator listens for the event and forces
 * an immediate poll. Cross-tab is intentionally NOT covered here —
 * the existing 25s idle cadence handles that case; the bus only solves
 * the same-tab latency.
 *
 * Why a window event and not a React context: every job-trigger site
 * is a leaf component (button, hook). Threading a context through
 * every one of them would bloat the trigger surface for no benefit.
 * A global event keeps the trigger contract to one line: `import +
 * call`. The indicator is a singleton (mounted once in Layout), so
 * there's no listener-fanout concern.
 */

const EVENT_NAME = "cpd:job-started";

/** Fire after a successful POST that enqueues a new background job. */
export function notifyJobStarted(): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent(EVENT_NAME));
}

/**
 * Subscribe to job-started events. Returns an unsubscribe function;
 * call it in a useEffect cleanup.
 */
export function subscribeJobStarted(cb: () => void): () => void {
  if (typeof window === "undefined") return () => {};
  const handler = () => cb();
  window.addEventListener(EVENT_NAME, handler);
  return () => window.removeEventListener(EVENT_NAME, handler);
}
