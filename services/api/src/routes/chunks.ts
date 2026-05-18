import type { FastifyInstance } from "fastify";
import { queryOne } from "../db.js";

const ID_RE = /^[0-9a-f-]{36}$/i;

export default async function chunkRoutes(app: FastifyInstance) {
  app.get("/:id", async (req, reply) => {
    const { id } = req.params as { id: string };
    if (!ID_RE.test(id)) return reply.badRequest("invalid id");

    const row = await queryOne<{ speech_id: string; chunk_index: number }>(
      `SELECT speech_id, chunk_index FROM speech_chunks WHERE id = $1`,
      [id],
    );
    if (!row) return reply.notFound();
    return row;
  });
}
