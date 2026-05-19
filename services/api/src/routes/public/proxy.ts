import type { FastifyInstance, FastifyReply, FastifyRequest } from "fastify";
import {
  withPublicTeiSlot,
  PublicSearchOverloadedError,
} from "../../lib/tei-semaphore.js";

/**
 * Shared `app.inject()` proxy helper for public-API routes.
 *
 * Each public route forwards its query string + path to the
 * corresponding internal /api/v1/* handler. Keeps route logic
 * single-source-of-truth in the internal route file and lets us
 * layer public-specific concerns (auth, scope, rate-limit, TEI
 * semaphore, OpenAPI metadata) on the outside without touching
 * internal handlers.
 *
 * Extracted from public/search.ts so bills / votes / committee
 * routes can reuse the same proxy shape.
 */

function buildQuery(req: FastifyRequest): string {
  const q = req.query as Record<string, unknown> | undefined;
  if (!q) return "";
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(q)) {
    if (value === undefined || value === null) continue;
    if (Array.isArray(value)) {
      for (const v of value) {
        if (v !== undefined && v !== null) params.append(key, String(v));
      }
    } else {
      params.append(key, String(value));
    }
  }
  const s = params.toString();
  return s ? `?${s}` : "";
}

export interface ProxyOptions {
  app: FastifyInstance;
  internalUrl: string;
  /** When true, wrap the inject in the TEI semaphore (search.ts only). */
  needsTei?: boolean;
}

export async function proxyToInternal(
  req: FastifyRequest,
  reply: FastifyReply,
  opts: ProxyOptions,
) {
  const { app, internalUrl, needsTei = false } = opts;
  const url = `${internalUrl}${buildQuery(req)}`;

  const doInject = async () => {
    return app.inject({
      method: "GET",
      url,
      // Don't forward Authorization — internal routes are public-already
      // for the read-only endpoints we proxy, and the user's API key
      // would be meaningless to them.
    });
  };

  try {
    const res = needsTei ? await withPublicTeiSlot(doInject) : await doInject();
    if (res.headers["cache-control"]) {
      reply.header("Cache-Control", res.headers["cache-control"]);
    }
    reply.code(res.statusCode);
    return res.json();
  } catch (err) {
    if (err instanceof PublicSearchOverloadedError) {
      reply.header("Retry-After", String(err.retryAfterSeconds));
      reply.code(err.statusCode);
      return {
        code: err.code,
        error: "Service Unavailable",
        message: err.message,
      };
    }
    throw err;
  }
}
