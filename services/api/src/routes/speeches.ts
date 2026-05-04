import type { FastifyInstance } from "fastify";
import { z } from "zod";
import { query, queryOne } from "../db.js";
import { resolvePhotoUrl } from "../lib/photos.js";

const ID_RE = /^[0-9a-f-]{36}$/i;

// Hard server cap. Federal QP days are 300–500 floor speeches; budget-day
// debates push 800+. 500 each side / 1000 total covers the realistic upper
// bound; anything beyond paginates via `before`/`after` increments.
const MAX_WINDOW = 500;

const contextQuerySchema = z.object({
  before: z.coerce.number().int().min(0).max(MAX_WINDOW).optional(),
  after: z.coerce.number().int().min(0).max(MAX_WINDOW).optional(),
  all: z
    .union([z.literal("true"), z.literal("false"), z.literal("1"), z.literal("0")])
    .optional()
    .transform((v) => v === "true" || v === "1"),
});

interface ContextRow {
  id: string;
  sequence: number | null;
  spoken_at: string | null;
  speaker_name_raw: string;
  speaker_role: string | null;
  party_at_time: string | null;
  constituency_at_time: string | null;
  speech_type: string | null;
  language: string;
  text: string;
  source_url: string;
  source_anchor: string | null;
  source_system: string;
  level: string;
  province_territory: string | null;
  politician_id: string | null;
  politician_name: string | null;
  politician_slug: string | null;
  politician_photo_url: string | null;
  politician_photo_path: string | null;
  politician_party: string | null;
}

function shapeContextRow(r: ContextRow) {
  return {
    id: r.id,
    sequence: r.sequence,
    spoken_at: r.spoken_at,
    speaker_name_raw: r.speaker_name_raw,
    speaker_role: r.speaker_role,
    party_at_time: r.party_at_time,
    constituency_at_time: r.constituency_at_time,
    speech_type: r.speech_type,
    language: r.language,
    text: r.text,
    source_url: r.source_url,
    source_anchor: r.source_anchor,
    source_system: r.source_system,
    level: r.level,
    province_territory: r.province_territory,
    politician: r.politician_id
      ? {
          id: r.politician_id,
          name: r.politician_name,
          slug: r.politician_slug,
          photo_url: resolvePhotoUrl({
            photo_path: r.politician_photo_path,
            photo_url: r.politician_photo_url,
          }),
          party: r.politician_party,
        }
      : null,
  };
}

const CONTEXT_SELECT = `
  s.id, s.sequence, s.spoken_at,
  s.speaker_name_raw, s.speaker_role,
  s.party_at_time, s.constituency_at_time,
  s.speech_type, s.language, s.text,
  s.source_url, s.source_anchor, s.source_system,
  s.level, s.province_territory,
  s.politician_id,
  p.name                AS politician_name,
  p.openparliament_slug AS politician_slug,
  p.photo_url           AS politician_photo_url,
  p.photo_path          AS politician_photo_path,
  p.party               AS politician_party
`;

export default async function speechRoutes(app: FastifyInstance) {
  app.get("/:id", async (req, reply) => {
    const { id } = req.params as { id: string };
    if (!ID_RE.test(id)) return reply.badRequest("invalid id");

    const speech = await queryOne<{
      id: string;
      session_id: string;
      politician_id: string | null;
      level: string;
      province_territory: string | null;
      speaker_name_raw: string;
      speaker_role: string | null;
      party_at_time: string | null;
      constituency_at_time: string | null;
      speech_type: string | null;
      spoken_at: string | null;
      sequence: number | null;
      language: string;
      text: string;
      word_count: number | null;
      source_system: string;
      source_url: string;
      source_anchor: string | null;
      politician_name: string | null;
      politician_slug: string | null;
      politician_photo_url: string | null;
      politician_photo_path: string | null;
      politician_party: string | null;
      parliament_number: number | null;
      session_number: number | null;
    }>(
      `
      SELECT s.id, s.session_id, s.politician_id, s.level, s.province_territory,
             s.speaker_name_raw, s.speaker_role, s.party_at_time, s.constituency_at_time,
             s.speech_type, s.spoken_at, s.sequence, s.language, s.text, s.word_count,
             s.source_system, s.source_url, s.source_anchor,
             p.name                AS politician_name,
             p.openparliament_slug AS politician_slug,
             p.photo_url           AS politician_photo_url,
             p.photo_path          AS politician_photo_path,
             p.party               AS politician_party,
             ls.parliament_number,
             ls.session_number
        FROM speeches s
        LEFT JOIN politicians p           ON p.id  = s.politician_id
        LEFT JOIN legislative_sessions ls ON ls.id = s.session_id
       WHERE s.id = $1
      `,
      [id],
    );
    if (!speech) return reply.notFound();

    const chunks = await query<{
      id: string;
      chunk_index: number;
      text: string;
      char_start: number;
      char_end: number;
      language: string;
    }>(
      `
      SELECT id, chunk_index, text, char_start, char_end, language
        FROM speech_chunks
       WHERE speech_id = $1
       ORDER BY chunk_index ASC
      `,
      [id],
    );

    return {
      speech: {
        id: speech.id,
        session_id: speech.session_id,
        level: speech.level,
        province_territory: speech.province_territory,
        speaker_name_raw: speech.speaker_name_raw,
        speaker_role: speech.speaker_role,
        party_at_time: speech.party_at_time,
        constituency_at_time: speech.constituency_at_time,
        speech_type: speech.speech_type,
        spoken_at: speech.spoken_at,
        sequence: speech.sequence,
        language: speech.language,
        text: speech.text,
        word_count: speech.word_count,
        source_system: speech.source_system,
        source_url: speech.source_url,
        source_anchor: speech.source_anchor,
        politician: speech.politician_id
          ? {
              id: speech.politician_id,
              name: speech.politician_name,
              slug: speech.politician_slug,
              photo_url: resolvePhotoUrl({
                photo_path: speech.politician_photo_path,
                photo_url: speech.politician_photo_url,
              }),
              party: speech.politician_party,
            }
          : null,
        session:
          speech.parliament_number !== null && speech.session_number !== null
            ? { parliament_number: speech.parliament_number, session_number: speech.session_number }
            : null,
      },
      chunks,
    };
  });

  // Surrounding speeches in the same legislative session, ordered by
  // (spoken_at, sequence). Used by the "exchange" view on /speeches/:id.
  // Hansard `sequence` is monotonic across speakers within a sitting, so
  // bracketing on the focal row's sequence yields a chronological window.
  app.get("/:id/context", async (req, reply) => {
    const { id } = req.params as { id: string };
    if (!ID_RE.test(id)) return reply.badRequest("invalid id");

    const parsed = contextQuerySchema.safeParse(req.query ?? {});
    if (!parsed.success) return reply.badRequest(parsed.error.message);

    const { all } = parsed.data;
    const before = all ? MAX_WINDOW : Math.min(parsed.data.before ?? 5, MAX_WINDOW);
    const after = all ? MAX_WINDOW : Math.min(parsed.data.after ?? 5, MAX_WINDOW);

    const focal = await queryOne<{
      session_id: string;
      sequence: number | null;
      spoken_at: string | null;
    }>(
      `SELECT session_id, sequence, spoken_at FROM speeches WHERE id = $1`,
      [id],
    );
    if (!focal) return reply.notFound();

    // Unsequenced speeches have no defined "exchange" context. `sequence`
    // resets every sitting day, so we also need a sitting-date scope —
    // without it, `sequence < N` matches earlier sittings of the same
    // session and the window leaks across days.
    if (focal.sequence === null || focal.spoken_at === null) {
      return { before: [], after: [], has_more_before: false, has_more_after: false };
    }

    // Date string in UTC (matches how `spoken_at::date` is computed in PG
    // since the column is timestamptz). Pulling the date out of focal.spoken_at
    // and casting to ::date in PG ensures a stable comparison regardless of
    // session timezone settings.
    const focalDate = focal.spoken_at;

    const beforeRows = before > 0
      ? await query<ContextRow>(
          `
          SELECT ${CONTEXT_SELECT}
            FROM speeches s
            LEFT JOIN politicians p ON p.id = s.politician_id
           WHERE s.session_id = $1
             AND s.spoken_at::date = ($2::timestamptz)::date
             AND s.sequence < $3
           ORDER BY s.sequence DESC
           LIMIT $4
          `,
          [focal.session_id, focalDate, focal.sequence, before + 1],
        )
      : [];

    const afterRows = after > 0
      ? await query<ContextRow>(
          `
          SELECT ${CONTEXT_SELECT}
            FROM speeches s
            LEFT JOIN politicians p ON p.id = s.politician_id
           WHERE s.session_id = $1
             AND s.spoken_at::date = ($2::timestamptz)::date
             AND s.sequence > $3
           ORDER BY s.sequence ASC
           LIMIT $4
          `,
          [focal.session_id, focalDate, focal.sequence, after + 1],
        )
      : [];

    const has_more_before = beforeRows.length > before;
    const has_more_after = afterRows.length > after;

    const trimmedBefore = has_more_before ? beforeRows.slice(0, before) : beforeRows;
    const trimmedAfter = has_more_after ? afterRows.slice(0, after) : afterRows;

    // `before` was fetched DESC for LIMIT; flip to chronological for the UI.
    return {
      before: trimmedBefore.slice().reverse().map(shapeContextRow),
      after: trimmedAfter.map(shapeContextRow),
      has_more_before,
      has_more_after,
    };
  });

  // Semantic "related speeches" — for a focal speech (or a specific chunk in
  // it), find the top-K most similar chunks from OTHER speeches via the HNSW
  // index on speech_chunks.embedding. Deduped to one chunk per speech (the
  // closest one) so the panel shows variety, not 5 chunks from the same MP.
  app.get("/:id/related", async (req, reply) => {
    const { id } = req.params as { id: string };
    if (!ID_RE.test(id)) return reply.badRequest("invalid id");

    const qSchema = z.object({
      chunk: z.string().regex(ID_RE).optional(),
      limit: z.coerce.number().int().min(1).max(20).optional(),
    });
    const parsed = qSchema.safeParse(req.query ?? {});
    if (!parsed.success) return reply.badRequest(parsed.error.message);

    const limit = parsed.data.limit ?? 5;

    // Anchor vector: the requested chunk if provided, otherwise the longest
    // chunk in the focal speech (most semantic content).
    const anchor = await queryOne<{ embedding: string }>(
      parsed.data.chunk
        ? `SELECT embedding::text AS embedding FROM speech_chunks WHERE id = $1 AND embedding IS NOT NULL`
        : `SELECT embedding::text AS embedding FROM speech_chunks
           WHERE speech_id = $1 AND embedding IS NOT NULL
           ORDER BY token_count DESC NULLS LAST
           LIMIT 1`,
      [parsed.data.chunk ?? id],
    );
    if (!anchor) return { items: [] };

    // Over-fetch to allow dedupe-by-speech without a second round trip.
    // HNSW ANN top-K is sub-millisecond on this index.
    const overFetch = Math.min(limit * 6, 60);

    const rows = await query<{
      chunk_id: string;
      speech_id: string;
      chunk_text: string;
      char_start: number;
      char_end: number;
      distance: number;
      sequence: number | null;
      spoken_at: string | null;
      speaker_name_raw: string;
      party_at_time: string | null;
      level: string;
      province_territory: string | null;
      politician_id: string | null;
      politician_name: string | null;
      politician_slug: string | null;
      politician_photo_url: string | null;
      politician_photo_path: string | null;
      politician_party: string | null;
    }>(
      `
      WITH candidates AS (
        SELECT sc.id              AS chunk_id,
               sc.speech_id,
               sc.text             AS chunk_text,
               sc.char_start,
               sc.char_end,
               (sc.embedding <=> $1::vector) AS distance
          FROM speech_chunks sc
         WHERE sc.embedding IS NOT NULL
           AND sc.speech_id <> $2
         ORDER BY sc.embedding <=> $1::vector
         LIMIT $3
      ),
      best_per_speech AS (
        SELECT DISTINCT ON (speech_id) chunk_id, speech_id, chunk_text, char_start, char_end, distance
          FROM candidates
         ORDER BY speech_id, distance
      )
      SELECT bps.chunk_id,
             bps.speech_id,
             bps.chunk_text,
             bps.char_start,
             bps.char_end,
             bps.distance,
             s.sequence,
             s.spoken_at,
             s.speaker_name_raw,
             s.party_at_time,
             s.level,
             s.province_territory,
             s.politician_id,
             p.name                AS politician_name,
             p.openparliament_slug AS politician_slug,
             p.photo_url           AS politician_photo_url,
             p.photo_path          AS politician_photo_path,
             p.party               AS politician_party
        FROM best_per_speech bps
        JOIN speeches s          ON s.id = bps.speech_id
        LEFT JOIN politicians p  ON p.id = s.politician_id
       ORDER BY bps.distance ASC
       LIMIT $4
      `,
      [anchor.embedding, id, overFetch, limit],
    );

    return {
      items: rows.map((r) => ({
        chunk_id: r.chunk_id,
        speech_id: r.speech_id,
        chunk_text: r.chunk_text,
        char_start: r.char_start,
        char_end: r.char_end,
        similarity: 1 - r.distance,
        spoken_at: r.spoken_at,
        speaker_name_raw: r.speaker_name_raw,
        party_at_time: r.party_at_time,
        level: r.level,
        province_territory: r.province_territory,
        politician: r.politician_id
          ? {
              id: r.politician_id,
              name: r.politician_name,
              slug: r.politician_slug,
              photo_url: resolvePhotoUrl({
                photo_path: r.politician_photo_path,
                photo_url: r.politician_photo_url,
              }),
              party: r.politician_party,
            }
          : null,
      })),
    };
  });
}
