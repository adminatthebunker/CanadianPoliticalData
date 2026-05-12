import type { FastifyInstance } from "fastify";
import { createReadStream } from "node:fs";
import { stat, readdir } from "node:fs/promises";
import { join } from "node:path";
import { z } from "zod";
import { requireApiKey } from "../../middleware/api-key-auth.js";
import { requireScope } from "../../middleware/api-scope-gate.js";
import { publicRateLimitConfig } from "../../middleware/api-rate-limit.js";
import { config } from "../../config.js";

/**
 * Bulk-export endpoints (/api/public/v1/exports/*).
 *
 * Phase 1e (lean MVP): two endpoints over the same dump artifacts
 * nginx serves anonymously at /datasets/. The value-add of this
 * surface vs. /datasets/ is auth-gated metered access — usage is
 * recorded in api_key_events when phase 1c's analytics writer
 * lands; quotas can be enforced later without re-architecting.
 *
 *   GET /exports/dumps             — list current full-dataset
 *                                    dumps (filename, size, mtime,
 *                                    sha256_filename if present).
 *   GET /exports/dumps/:filename   — stream a specific dump file.
 *
 * Both require requireApiKey + requireScope('read:bulk'). Free-tier
 * keys CAN have read:bulk (cheap-but-allowed bulk download); pro-
 * tier keys without read:bulk can hammer search but can't download
 * dumps. Two orthogonal axes (tier vs scope) by design.
 *
 * Phase 1f (deferred): per-jurisdiction-month Parquet slices via a
 * scanner snapshot generator. The slicing API would mount under
 * /exports/slices/{table}/{jurisdiction}/{year-month}.parquet.
 *
 * SECURITY: filename regex forbids any path-traversal vector. We
 * never construct a path from user-controlled input without first
 * matching against ^cpd-public-[A-Za-z0-9_-]+\.(pgcustom|sha256|
 * manifest\.tsv)$. Even within that allowlist we resolve+normalize
 * the final path and refuse anything that escapes the dumps
 * directory.
 */

// Cpd-public-{ts}-{git-sha}.{pgcustom|sha256|manifest.tsv} — the
// shape produced by scripts/make-public-dump.sh. Anything outside
// this is refused.
const FILENAME_RE = /^cpd-public-[A-Za-z0-9_-]+\.(pgcustom|sha256|manifest\.tsv)$/;

const filenameParam = z.object({
  filename: z
    .string()
    .max(200)
    .regex(FILENAME_RE)
    .describe(
      "Dump filename. Format: cpd-public-<timestamp>-<git-sha>." +
      "{pgcustom|sha256|manifest.tsv}",
    ),
});

interface DumpEntry {
  filename: string;
  size_bytes: number;
  modified_at: string;
  kind: "pgcustom" | "sha256" | "manifest";
}

function ensureConfigured(reply: import("fastify").FastifyReply): boolean {
  if (config.publicDumpsDir) return true;
  reply.code(503).send({
    code: "exports_unavailable",
    error: "Service Unavailable",
    message: "PUBLIC_DUMPS_DIR not configured on server",
  });
  return false;
}

function classify(filename: string): DumpEntry["kind"] | null {
  if (filename.endsWith(".pgcustom")) return "pgcustom";
  if (filename.endsWith(".sha256")) return "sha256";
  if (filename.endsWith(".manifest.tsv")) return "manifest";
  return null;
}

function contentTypeFor(filename: string): string {
  if (filename.endsWith(".pgcustom")) return "application/octet-stream";
  if (filename.endsWith(".sha256")) return "text/plain; charset=utf-8";
  if (filename.endsWith(".manifest.tsv")) return "text/tab-separated-values; charset=utf-8";
  return "application/octet-stream";
}

export default async function publicV1ExportsRoutes(app: FastifyInstance) {
  // ── GET /api/public/v1/exports/dumps ──────────────────────────
  app.get(
    "/exports/dumps",
    {
      preHandler: [requireApiKey, requireScope("read:bulk")],
      config: { rateLimit: publicRateLimitConfig },
      schema: {
        tags: ["Bulk export"],
        summary: "List current full-dataset dump artifacts (BULK)",
        description:
          "Returns the full-database public-schema dumps available for " +
          "download. Each dump set is three files: a .pgcustom (Postgres " +
          "custom-format archive, restorable via pg_restore), a .sha256 " +
          "(integrity check), and a .manifest.tsv (table inventory). " +
          "Same files served anonymously at /datasets/ — this surface " +
          "adds auth + per-key usage metering. Requires read:bulk scope. " +
          "Cache-Control: public, max-age=60.",
      },
    },
    async (_req, reply) => {
      if (!ensureConfigured(reply)) return;
      try {
        const names = await readdir(config.publicDumpsDir);
        const entries: DumpEntry[] = [];
        for (const filename of names) {
          if (!FILENAME_RE.test(filename)) continue;
          const kind = classify(filename);
          if (!kind) continue;
          const s = await stat(join(config.publicDumpsDir, filename));
          if (!s.isFile()) continue;
          entries.push({
            filename,
            size_bytes: s.size,
            modified_at: s.mtime.toISOString(),
            kind,
          });
        }
        // Newest first.
        entries.sort((a, b) => (a.modified_at < b.modified_at ? 1 : -1));
        reply.header("Cache-Control", "public, max-age=60");
        return { dumps: entries };
      } catch (err) {
        const code = (err as NodeJS.ErrnoException).code;
        if (code === "ENOENT") {
          // Configured directory doesn't exist on disk yet — empty
          // result is more useful than a 500.
          return { dumps: [] };
        }
        throw err;
      }
    },
  );

  // ── GET /api/public/v1/exports/dumps/:filename ────────────────
  app.get(
    "/exports/dumps/:filename",
    {
      preHandler: [requireApiKey, requireScope("read:bulk")],
      config: { rateLimit: publicRateLimitConfig },
      schema: {
        tags: ["Bulk export"],
        summary: "Stream a specific dump file (BULK)",
        description:
          "Streams the named dump file. 404 if the filename doesn't " +
          "match the cpd-public-<ts>-<sha>.{pgcustom|sha256|manifest.tsv} " +
          "pattern, or if the file isn't present on disk. " +
          "Content-Disposition: attachment with the original filename. " +
          "Streamed (no full-buffer load) so multi-GB pgcustom files " +
          "don't blow the API container's memory.",
        params: filenameParam,
      },
    },
    async (req, reply) => {
      if (!ensureConfigured(reply)) return;
      const { filename } = req.params as { filename: string };
      // Defence in depth — zod already enforced the regex at the
      // route boundary, but re-validate here so a downstream refactor
      // that swaps the schema can't accidentally open the door.
      if (!FILENAME_RE.test(filename)) {
        return reply.code(404).send({
          statusCode: 404,
          error: "Not Found",
          message: "filename doesn't match the dump-artifact pattern",
        });
      }
      const fullPath = join(config.publicDumpsDir, filename);
      // Resolved path must still live under the configured dumps dir.
      // (No traversal possible because the regex doesn't permit "/"
      // or ".", but belt + braces.)
      if (!fullPath.startsWith(config.publicDumpsDir)) {
        return reply.code(404).send({
          statusCode: 404,
          error: "Not Found",
          message: "filename escapes the dumps directory",
        });
      }
      let s: Awaited<ReturnType<typeof stat>>;
      try {
        s = await stat(fullPath);
      } catch (err) {
        const code = (err as NodeJS.ErrnoException).code;
        if (code === "ENOENT") {
          return reply.code(404).send({
            statusCode: 404,
            error: "Not Found",
            message: `dump file not found: ${filename}`,
          });
        }
        throw err;
      }
      if (!s.isFile()) {
        return reply.code(404).send({
          statusCode: 404,
          error: "Not Found",
          message: `not a file: ${filename}`,
        });
      }
      reply.header("Content-Type", contentTypeFor(filename));
      reply.header("Content-Length", String(s.size));
      reply.header(
        "Content-Disposition",
        `attachment; filename="${filename}"`,
      );
      reply.header("Cache-Control", "public, max-age=300");
      return reply.send(createReadStream(fullPath));
    },
  );
}
