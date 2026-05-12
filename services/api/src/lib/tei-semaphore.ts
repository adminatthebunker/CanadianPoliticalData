import pLimit from "p-limit";
import { config } from "../config.js";

/**
 * Concurrency-control wrapper around the TEI embedding fetch for the
 * public /api/public/v1/search/* surface.
 *
 * Why: TEI runs on a single GPU and serves both ingest (background)
 * and interactive (search) workloads. A flood of public-API search
 * traffic can starve scanner ingest or push GPU temps; we cap
 * simultaneous embed requests AND refuse early when the queue is
 * deep, so callers fail fast (503 + Retry-After) rather than waiting
 * minutes for a slot.
 *
 * The internal /api/v1/search/* routes don't go through this — they
 * call encodeQuery directly. The reason: those routes back the
 * authenticated frontend where a brief queue is acceptable; the
 * public surface needs to be polite about backpressure to third-party
 * integrations.
 *
 * Knobs: PUBLIC_TEI_MAX_CONCURRENT (default 2), PUBLIC_TEI_MAX_QUEUE
 * (default 6). Total slots = concurrent + queue; past that we 503.
 */

const limit = pLimit(config.publicTei.maxConcurrent);

export class PublicSearchOverloadedError extends Error {
  readonly statusCode = 503;
  readonly code = "search_overloaded";
  /** Seconds the caller should wait before retrying. */
  readonly retryAfterSeconds: number;
  constructor(retryAfterSeconds = 5) {
    super("public search service is at capacity, retry shortly");
    this.name = "PublicSearchOverloadedError";
    this.retryAfterSeconds = retryAfterSeconds;
  }
}

/**
 * Wrap an async fn so it runs through the public-API TEI semaphore.
 * Refuses with PublicSearchOverloadedError when the queue is at capacity
 * (active + pending exceeds maxConcurrent + maxQueue). Otherwise queues
 * and runs in FIFO order.
 *
 * Callers should catch PublicSearchOverloadedError + map it to a
 * Fastify reply with the appropriate Retry-After header.
 */
export async function withPublicTeiSlot<T>(
  fn: () => Promise<T>,
): Promise<T> {
  const totalSlots = config.publicTei.maxConcurrent + config.publicTei.maxQueue;
  if (limit.activeCount + limit.pendingCount >= totalSlots) {
    throw new PublicSearchOverloadedError();
  }
  return limit(fn);
}

/** Telemetry probe — surface in /admin/usage or similar later. */
export function publicTeiStats(): {
  active: number;
  pending: number;
  maxConcurrent: number;
  maxQueue: number;
} {
  return {
    active: limit.activeCount,
    pending: limit.pendingCount,
    maxConcurrent: config.publicTei.maxConcurrent,
    maxQueue: config.publicTei.maxQueue,
  };
}
