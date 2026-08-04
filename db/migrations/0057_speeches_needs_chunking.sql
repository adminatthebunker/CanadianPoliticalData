-- 0057: work-queue flag for the speech chunker.
--
-- The daily chunk-and-embed-speeches job found unchunked speeches via an
-- anti-join (speeches LEFT JOIN speech_chunks ... WHERE c.id IS NULL). That
-- query is O(corpus): it seq-scans both tables (~15M rows / ~24 GB of buffer
-- reads) regardless of backlog size, and on 2026-08-03 the corpus grew past
-- the point where it finishes inside the pool's 60 s command_timeout — the
-- job failed two mornings running. Same class of fix as the existing
-- idx_chunks_needs_embedding partial index on the embed side: a flag column
-- + partial index makes the candidate scan O(backlog) forever.
--
-- Two-step default trick avoids a 7M-row table rewrite:
--   1. add with DEFAULT false  -> metadata-only; every existing row reads false
--   2. flip default to true    -> applies to future inserts only
--   3. one-shot anti-join      -> flags the current real backlog
--
-- The chunker clears the flag transactionally per speech (including
-- splitter-skipped tiny turns, replacing the old skipped_ids bookkeeping).
-- Re-chunking after a code change is now: delete the speech's chunks, then
-- UPDATE speeches SET needs_chunking = true WHERE ... . Parity note: a
-- re-ingest that revises text never re-chunked under the anti-join either;
-- the flag preserves that behaviour.

alter table speeches
    add column needs_chunking boolean not null default false;

alter table speeches
    alter column needs_chunking set default true;

-- Matches chunk_pending's ORDER BY spoken_at DESC NULLS LAST, id.
create index idx_speeches_needs_chunking
    on speeches (spoken_at desc nulls last, id)
    where needs_chunking;

-- Flag the current backlog (the one-time O(corpus) pass this migration
-- retires; ~60-90 s). Short procedural turns (< 27 chars, the splitter's
-- MIN_CHUNK_TOKENS floor) are left false — the splitter would only skip them.
update speeches s
   set needs_chunking = true
 where length(btrim(s.text)) >= 27
   and not exists (select 1 from speech_chunks c where c.speech_id = s.id);
