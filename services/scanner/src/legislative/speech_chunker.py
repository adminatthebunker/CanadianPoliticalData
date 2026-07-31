"""Speech → speech_chunks splitter.

Turns rows in `speeches` into retrievable units in `speech_chunks`
(one per speaker turn by default, paragraph-split on long turns).

This module is jurisdiction-agnostic: it chunks any speeches row,
whether the upstream source was openparliament (federal), Hansard
scrape (provincial), or committee transcript. The `speech_chunks`
table's discriminator columns (level, province_territory) are copied
from the parent speech.

## Rules

- **One speaker turn = one chunk** by default (the simplest, most
  informative unit — politician_id attaches cleanly).
- **Long turns split at paragraph boundary** with a 50-token overlap.
  The splitter targets `CHUNK_TARGET_TOKENS` (default 480) so we stay
  safely under BGE-M3's 512-tok practical window; the embed service
  will still accept up to 8192 but throughput drops.
- **Tiny turns skipped** (< `MIN_TOKENS`, default 8). Procedural
  "Mr. Speaker" / "Thank you" entries stay in `speeches` for timeline
  continuity but don't clutter the retrieval index.
- **Token estimation is approximate** — 1 token ≈ 3.5 chars for
  XLMR-family tokenizers on EN/FR mixed corpora. Under-counting leads
  to slightly larger-than-ideal chunks; over-counting leads to more
  splits than needed. Good enough for v0; we can call the embed
  service's tokenizer later for exact counts if it matters.

## tsvector setup

`speech_chunks.tsv` is the BM25 index. We set `tsv_config` per-language
(`english` / `french` / `simple`) so the tsvector normalises sensibly.
`unaccent` is installed (migration 0014) but we don't apply it in the
config here — exact accent-preserving match matters for FR names /
ridings. Re-evaluate after first retrieval tuning pass.
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from typing import Any, Optional

from ..db import Database

log = logging.getLogger(__name__)

CHUNK_TARGET_TOKENS = 480
CHUNK_OVERLAP_TOKENS = 50
MIN_CHUNK_TOKENS = 8
# Speeches per pending-queue fetch in chunk_pending. Bounded so the
# full-text fetch stays well under the pool's command_timeout=60 at any
# backlog size (a fetch-all of the 2.7M-speech committee backfill timed
# out on 2026-07-27). ~20K speeches ≈ 2m19s end-to-end per pass, fetch
# itself is seconds.
CHUNK_DB_FETCH_BATCH = int(os.environ.get("CHUNK_DB_FETCH_BATCH", "20000"))
# XLMR tokenizers average ~3.5 chars/token on mixed EN/FR corpora.
CHARS_PER_TOKEN = 3.5

LANG_TO_TSCONFIG = {
    "en": "english",
    "fr": "french",
    # Inuktitut / other: simple normaliser (no stemmer).
}


def _estimate_tokens(text: str) -> int:
    return max(1, int(round(len(text) / CHARS_PER_TOKEN)))


def _tsconfig_for(language: str) -> str:
    return LANG_TO_TSCONFIG.get(language.lower(), "simple")


@dataclass
class Chunk:
    text: str
    char_start: int
    char_end: int
    token_count: int


def split_into_chunks(text: str) -> list[Chunk]:
    """Split a speaker turn into embeddable chunks.

    Returns an empty list if the input is empty or below the minimum
    token threshold.
    """
    text = text.strip()
    if not text:
        return []
    total_tokens = _estimate_tokens(text)
    if total_tokens < MIN_CHUNK_TOKENS:
        return []
    if total_tokens <= CHUNK_TARGET_TOKENS:
        return [
            Chunk(
                text=text,
                char_start=0,
                char_end=len(text),
                token_count=total_tokens,
            )
        ]

    # Long turn: split at paragraph boundaries, greedy-pack up to target.
    # openparliament's html_to_text joined paragraphs with "\n" so we
    # split on blank lines or single \n — both work because we
    # collapsed whitespace earlier.
    paragraphs = [p for p in re.split(r"\n+", text) if p.strip()]
    if len(paragraphs) == 1:
        # No paragraph boundaries — hard-split on sentence boundaries.
        # Cheap heuristic: split on ".  " or ". " followed by uppercase.
        paragraphs = re.split(r"(?<=[.!?])\s+(?=[A-ZÀ-Ý])", text)

    chunks: list[Chunk] = []
    buf: list[str] = []
    buf_tokens = 0
    # Track char offset into original text for provenance.
    offset = 0
    char_cursor = 0
    for para in paragraphs:
        para_tokens = _estimate_tokens(para)
        # If adding this paragraph would overflow, flush current buf.
        if buf and buf_tokens + para_tokens > CHUNK_TARGET_TOKENS:
            chunk_text = "\n".join(buf).strip()
            if chunk_text:
                # Find chunk_text inside original text from cursor onwards.
                pos = text.find(chunk_text, offset)
                if pos < 0:
                    pos = offset
                chunks.append(
                    Chunk(
                        text=chunk_text,
                        char_start=pos,
                        char_end=pos + len(chunk_text),
                        token_count=_estimate_tokens(chunk_text),
                    )
                )
                offset = chunks[-1].char_end
            # Start next buffer with overlap from the tail of this one.
            if CHUNK_OVERLAP_TOKENS and chunks:
                tail_chars = int(CHUNK_OVERLAP_TOKENS * CHARS_PER_TOKEN)
                tail = chunks[-1].text[-tail_chars:]
                buf = [tail, para]
                buf_tokens = _estimate_tokens(tail) + para_tokens
            else:
                buf = [para]
                buf_tokens = para_tokens
        else:
            buf.append(para)
            buf_tokens += para_tokens
        char_cursor += len(para) + 1  # +1 for the joining newline

    if buf:
        chunk_text = "\n".join(buf).strip()
        if chunk_text and _estimate_tokens(chunk_text) >= MIN_CHUNK_TOKENS:
            pos = text.find(chunk_text, offset) if offset < len(text) else offset
            if pos < 0:
                pos = offset
            chunks.append(
                Chunk(
                    text=chunk_text,
                    char_start=pos,
                    char_end=pos + len(chunk_text),
                    token_count=_estimate_tokens(chunk_text),
                )
            )
    return chunks


@dataclass
class ChunkStats:
    speeches_seen: int = 0
    speeches_chunked: int = 0
    speeches_skipped: int = 0
    chunks_inserted: int = 0


@dataclass
class DenormSyncStats:
    chunks_synced: int = 0


async def sync_chunk_denorm(
    db: Database,
    *,
    since_days: int = 30,
) -> DenormSyncStats:
    """Re-derive denormalized columns on speech_chunks from their parent speech.

    speech_chunks copies politician_id / party_at_time / level /
    province_territory / spoken_at / session_id from the parent speech
    at insert time (see chunk_pending below), so /search filters can
    prune before the HNSW scan. But every downstream code path that
    UPDATEs a speech — speaker resolvers, session retags, late
    attribution fixes — touches only the speeches row, leaving the
    chunks behind with stale values. This is the sync step the
    migration's "Keep in sync with parent speech on updates; treat as
    derived state" comment implies should run.

    Scope: `since_days` (default 30) limits the join to speeches with
    `spoken_at >= NOW() - INTERVAL '<since_days> days'`, which uses
    idx_speeches_spoken_at and bounds the working set to the rolling
    recent corpus. Without this scope the join scans every speech in
    the corpus on every nightly run and times out — the historical
    backfill (1.4M chunks across 37 years) was a one-time event done
    via a per-session bash loop, not via this function. Operators
    re-running a historical retag should bump since_days to the
    relevant horizon for that retag.

    Plan note: forces enable_seqscan=off for the transaction so the
    planner uses idx_speeches_spoken_at + speech_chunks_speech_id_chunk_index_key
    (nested loop) instead of seq-scanning the 5M-row chunks table.
    """
    stats = DenormSyncStats()
    # Generous per-statement timeout: the pool default is 60s (db.py),
    # which is fine for daily steady-state drift (1k-10k rows in seconds)
    # but too tight if a session retag or roster backfill just landed
    # tens of thousands of newly-resolvable chunks within the since
    # window. 10 minutes used to cover everything short of a corpus-wide
    # retag, but the 2026-05-15 daily run hit 603s (just past the cap)
    # after a Tier-2 attribution roster burst — bumped to 30 min.
    async with db.pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("SET LOCAL enable_seqscan = off")
            tag = await conn.execute(
                f"""
                UPDATE speech_chunks sc
                   SET session_id = sp.session_id,
                       spoken_at = sp.spoken_at,
                       politician_id = sp.politician_id,
                       party_at_time = sp.party_at_time,
                       level = sp.level,
                       province_territory = sp.province_territory
                  FROM speeches sp
                 WHERE sp.id = sc.speech_id
                   AND sp.spoken_at >= NOW() - INTERVAL '{int(since_days)} days'
                   AND (sc.session_id IS DISTINCT FROM sp.session_id
                        OR sc.spoken_at IS DISTINCT FROM sp.spoken_at
                        OR sc.politician_id IS DISTINCT FROM sp.politician_id
                        OR sc.party_at_time IS DISTINCT FROM sp.party_at_time
                        OR sc.level IS DISTINCT FROM sp.level
                        OR sc.province_territory IS DISTINCT FROM sp.province_territory)
                """,
                timeout=1800,
            )
            try:
                stats.chunks_synced = int(tag.rsplit(" ", 1)[-1])
            except (ValueError, AttributeError):
                stats.chunks_synced = 0
    log.info(
        "sync_chunk_denorm: chunks_synced=%d (since_days=%d)",
        stats.chunks_synced, since_days,
    )
    return stats


async def chunk_pending(
    db: Database,
    *,
    limit_speeches: Optional[int] = None,
    source_system: Optional[str] = None,
    speech_type: Optional[str] = None,
) -> ChunkStats:
    """Find speeches without chunks and produce them.

    Idempotent via (speech_id, chunk_index) unique; callers can re-run
    safely. Existing speech_chunks rows are never deleted here —
    re-chunking after a code change is a separate admin task.

    Optional `source_system` / `speech_type` filters bypass the
    spoken_at-DESC global queue — useful for getting a freshly-ingested
    provincial pipeline searchable end-of-day without waiting for the
    daily cron to drain the corpus-wide unchunked backlog.
    """
    stats = ChunkStats()
    # Mirror split_into_chunks' tiny-turn skip (MIN_CHUNK_TOKENS=8 at
    # CHARS_PER_TOKEN=3.5 → keep iff trimmed length >= 27 chars) in SQL so
    # the ~440K procedural "Agreed." turns aren't re-fetched and re-skipped
    # in Python on every run. Python's round() half-even at exactly 7.5
    # tokens (26.25 chars) can't occur on integer lengths, so >= 27 is an
    # exact mirror, not an approximation.
    where_clauses = [
        "c.id IS NULL",
        "length(btrim(s.text)) >= 27",
    ]
    params: list = []
    if source_system is not None:
        params.append(source_system)
        where_clauses.append(f"s.source_system = ${len(params)}")
    if speech_type is not None:
        params.append(speech_type)
        where_clauses.append(f"s.speech_type = ${len(params)}")
    # Stream the pending queue in DB-side batches. A single fetch-all of a
    # multi-million-row backlog (full speech texts) exceeds the pool's
    # command_timeout=60 — hit 2026-07-27 on the 2.7M-speech committee
    # backfill. Chunked speeches drop out of the anti-join, so refetching
    # naturally advances; speeches the splitter skips are excluded
    # explicitly so a skip can't be refetched in a loop. (The >= 27 SQL
    # floor should make skips impossible, but the exclusion costs nothing
    # and keeps the loop terminating if the two filters ever drift.)
    skipped_ids: list = []
    while True:
        fetch_n = CHUNK_DB_FETCH_BATCH
        if limit_speeches:
            remaining = int(limit_speeches) - stats.speeches_seen
            if remaining <= 0:
                break
            fetch_n = min(fetch_n, remaining)
        batch_where = list(where_clauses)
        batch_params = list(params)
        if skipped_ids:
            batch_params.append(skipped_ids)
            batch_where.append(f"NOT (s.id = ANY(${len(batch_params)}))")
        query = f"""
            SELECT s.id, s.text, s.language, s.politician_id, s.level,
                   s.province_territory, s.spoken_at, s.session_id,
                   s.party_at_time
            FROM speeches s
            LEFT JOIN speech_chunks c ON c.speech_id = s.id
            WHERE {' AND '.join(batch_where)}
            ORDER BY s.spoken_at DESC NULLS LAST, s.id
            LIMIT {fetch_n}
        """
        rows = await db.fetch(query, *batch_params)
        if not rows:
            break
        for row in rows:
            stats.speeches_seen += 1
            chunks = split_into_chunks(row["text"] or "")
            if not chunks:
                stats.speeches_skipped += 1
                skipped_ids.append(row["id"])
                continue
            tsconfig = _tsconfig_for(row["language"] or "en")
            async with db.pool.acquire() as conn:
                async with conn.transaction():
                    for idx, ch in enumerate(chunks):
                        await conn.execute(
                            """
                            INSERT INTO speech_chunks (
                                speech_id, chunk_index, text, token_count,
                                char_start, char_end, language,
                                politician_id, party_at_time, level,
                                province_territory, spoken_at, session_id,
                                embedding, tsv, tsv_config
                            ) VALUES (
                                $1, $2, $3, $4,
                                $5, $6, $7,
                                $8, $9, $10,
                                $11, $12, $13,
                                NULL, to_tsvector($14::regconfig, $3), $14
                            )
                            ON CONFLICT (speech_id, chunk_index) DO NOTHING
                            """,
                            row["id"],
                            idx,
                            ch.text,
                            ch.token_count,
                            ch.char_start,
                            ch.char_end,
                            row["language"],
                            row["politician_id"],
                            row["party_at_time"],
                            row["level"],
                            row["province_territory"],
                            row["spoken_at"],
                            row["session_id"],
                            tsconfig,
                        )
                        stats.chunks_inserted += 1
            stats.speeches_chunked += 1
        if len(rows) < fetch_n:
            break

    log.info(
        "chunk-speeches: seen=%d chunked=%d skipped=%d chunks=%d",
        stats.speeches_seen,
        stats.speeches_chunked,
        stats.speeches_skipped,
        stats.chunks_inserted,
    )
    return stats
