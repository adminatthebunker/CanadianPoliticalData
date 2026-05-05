"""reports-worker daemon — runs queued report_jobs through an LLM
map-reduce against every speech_chunk matching (politician_id, query),
persists the rendered HTML, commits or releases the credit hold, and
emails the user a "report ready" link.

Mirrors services/scanner/src/alerts_worker.py in shape: poll loop,
graceful SIGTERM, stub-on-missing-SMTP. The map-reduce prompt strings
are kept char-for-char identical to services/api/src/lib/reports.ts so
the model behaviour is a function of the prompt, not the entry point.

Two ledger interactions, both inline SQL UPDATE statements (no import
of the TS lib — we replicate the exact statements the lib emits):

  Success → credit_ledger row with kind='report_hold' and reference_id=jobId
            flips state 'held' → 'committed'. balance now reflects a real debit.
  Failure → same row flips 'held' → 'refunded'. delta drops out of balance.

Stale-claim re-queue: a job in 'running' state with claimed_at older
than 15 minutes is considered abandoned by a crashed worker and gets
re-queued. The hold stays in place, so the same job runs to completion
exactly once across re-queues — no double-debit.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import signal
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Any, Callable, Awaitable

import bleach
import httpx

from .db import Database, get_dsn

log = logging.getLogger("reports_worker")

POLL_INTERVAL = int(os.environ.get("REPORTS_POLL_INTERVAL", "5"))
STALE_CLAIM_MINUTES = int(os.environ.get("REPORTS_STALE_CLAIM_MINUTES", "15"))

OPENROUTER_BASE_URL = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_REPORT_MODEL = os.environ.get("OPENROUTER_REPORT_MODEL", "anthropic/claude-sonnet-4.6")
OPENROUTER_REPORT_TIMEOUT_MS = int(os.environ.get("OPENROUTER_REPORT_TIMEOUT_MS", "120000"))
OPENROUTER_SITE_URL = os.environ.get("OPENROUTER_SITE_URL", "https://canadianpoliticaldata.org")
OPENROUTER_APP_NAME = os.environ.get("OPENROUTER_APP_NAME", "Canadian Political Data")

REPORT_BUCKET_SIZE = int(os.environ.get("REPORT_BUCKET_SIZE", "10"))
REPORT_MAX_CHUNKS = int(os.environ.get("REPORT_MAX_CHUNKS", "300"))
REPORT_HNSW_EF_SEARCH = int(os.environ.get("REPORT_HNSW_EF_SEARCH", "1000"))

EMBED_URL = os.environ.get("EMBED_URL", "http://tei:80").rstrip("/")
INSTRUCT_PREFIX = "Instruct: Retrieve relevant Canadian political speeches.\nQuery: "

SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.protonmail.ch")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SMTP_FROM = os.environ.get("SMTP_FROM", "")
PUBLIC_SITE_URL = os.environ.get("PUBLIC_SITE_URL", "http://localhost:5173").rstrip("/")


# ── Prompts (KEEP IN SYNC with services/api/src/lib/reports.ts) ─────

SYSTEM_PROMPT_MAP = """You are a careful research analyst. You will be shown N quotes from a single Canadian politician on a specific topic. Extract the politician's positions and themes from these quotes. Output strictly valid JSON of this exact shape:

{
  "themes": [
    {
      "label": "<short noun-phrase label, < 60 chars>",
      "positions": [
        {
          "summary": "<one neutral sentence describing the politician's stated position>",
          "chunk_ids": ["<chunk_id from input, copied verbatim>", ...]
        }
      ]
    }
  ]
}

Rules:
- "chunk_ids" MUST be copied verbatim from the input. Never invent IDs.
- Every position must reference at least one input chunk_id.
- "summary" must be neutral and observational — do not editorialise, do not draw conclusions, do not call statements right or wrong.
- If a quote is the politician quoting an opponent ("the member opposite said…"), treat it as rhetorical framing, not their own position. Do not include such quotes as positions.
- Some quotes may be only tangentially related to the query topic — the retrieval system errs on the side of recall, so a few off-topic chunks may slip in. Omit any chunk where the politician is not actually speaking about the topic in a substantive way. Producing fewer, well-evidenced themes is preferred over many themes built on weak evidence.
- If multiple quotes express the same position, group them under one "positions" entry with multiple chunk_ids.
- Themes should be granular but not redundant: prefer 2-5 themes per bucket."""

SYSTEM_PROMPT_REDUCE = """You are synthesising the work of multiple analysts who each read a subset of a politician's quotes on a topic. You will be shown each analyst's themes and positions in JSON form. Produce a single coherent HTML report.

Output strictly valid JSON of this exact shape:

{
  "summary": "<one paragraph (60-120 words) framing what the politician's record shows on this topic, in neutral observational tone>",
  "html": "<HTML body, see allowed tags below>"
}

Allowed HTML tags ONLY: <p>, <h2>, <h3>, <ul>, <ol>, <li>, <blockquote>, <em>, <strong>, <a href="…">. Any other tag will be stripped server-side.

Rules:
- Structure the HTML with <h2> sections per theme; under each theme, group positions and reference quotes inline.
- Every claim that asserts a position MUST link to at least one source quote. Format the link as <a href="CHUNK:<chunk_id>">…</a> using the literal token CHUNK: followed by a chunk_id from the input. The system will rewrite these to real anchored URLs after you respond. Never output a real URL — only the CHUNK:<id> token form.
- Preserve the chunk_ids verbatim from the input analyst output. Never invent IDs.
- Neutral observational tone throughout. Frame as "the politician has said X (link)", never as "the politician is wrong about X" or "the politician contradicts themselves on X".
- If the analyst output includes contradictory positions across time, describe them descriptively — "in <year> they said X (link); in <later year> they said Y (link)" — without using the word "contradiction".
- The summary paragraph is the FIRST thing the user reads. Make it factual and substantive; avoid filler like "this report covers…".
- Do not include a top-level <h1> — the page chrome supplies the title. Start with a <p> or <h2>."""


# ── Prompts (search_synthesis + stance_map) ────────────────────────
#
# These are search-result-set analyses, not per-politician analyses, so
# the input is multi-speaker and chunks come from the frontend's top-K
# ranking rather than HNSW-against-one-politician. Each chunk's prompt
# entry includes the speaker name so the model can attribute claims
# without confusing two MPs talking about the same topic.

SYSTEM_PROMPT_SYNTHESIZE_MAP = """You are a careful research analyst. You will be shown N quotes from various Canadian politicians, retrieved by a search on a topic. Extract the substantive claims and themes evidenced by these quotes. Output strictly valid JSON of this exact shape:

{
  "claims": [
    {
      "text": "<one neutral sentence stating a claim or position evidenced by the quotes>",
      "supporting_chunk_ids": ["<chunk_id from input, copied verbatim>", ...]
    }
  ]
}

Rules:
- "supporting_chunk_ids" MUST be copied verbatim from the input. Never invent IDs.
- Every claim must reference at least one input chunk_id.
- Neutral observational tone — describe what speakers said, do not editorialise.
- If a chunk is too tangential to the topic to support a substantive claim, omit it. The retrieval system errs on recall; fewer well-evidenced claims beats many speculative ones.
- If multiple chunks express the same claim from different speakers, group them under one entry with multiple supporting_chunk_ids.
- If a chunk is the speaker quoting an opponent, treat it as rhetorical framing — do not extract that as the speaker's own claim.
- Prefer 3-7 claims per bucket. Be selective."""

SYSTEM_PROMPT_SYNTHESIZE_REDUCE = """You are synthesizing search results into a brief for a journalist or researcher. You will be shown the claims extracted by multiple analysts who each read a subset of the search results, plus pre-computed aggregations over the same set (party / speaker / year / language counts). Produce a single coherent brief that ALSO surfaces the structural shape of the result set.

Output strictly valid JSON of this exact shape:

{
  "summary": "<one paragraph (60-100 words) framing what the search results collectively show on this topic, in neutral observational tone>",
  "html": "<HTML body, see allowed tags below>"
}

The HTML body must, IN THIS ORDER:
1. A <p> with the headline framing (1-2 sentences).
2. A <h3>Who's saying it</h3> followed by a <table> rendering the aggregations. Use this exact shape:
   <table class="report-stats">
     <thead><tr><th>Party</th><th>Quotes</th><th>%</th></tr></thead>
     <tbody>
       <tr><td>Conservative</td><td>33</td><td>33%</td></tr>
       …rows for the top 5 parties from `aggregations.by_party`, omit "Unresolved / Chair" only if it's not the largest segment…
     </tbody>
   </table>
   Then a second <table class="report-stats"> with <th>Speaker</th><th>Quotes</th> showing the top 5 from `aggregations.top_speakers` (skip rows where name is "Unknown" if other speakers exist).
   Then a single <p> noting the time range: e.g. "Spans <strong>{first_year}–{last_year}</strong>" using `aggregations.by_year`. Skip if <2 distinct years.
3. A <h3>Findings</h3> followed by a <ul> of exactly 5 <li> bullets, each containing one substantive finding from the analyst output.
   Each <li> MUST end with at least one <a href="CHUNK:<chunk_id>">[source]</a> link. The literal token CHUNK:<id> will be rewritten server-side to a real /speeches/... URL — never output a real URL yourself.

Allowed HTML tags ONLY: <p>, <h2>, <h3>, <ul>, <ol>, <li>, <blockquote>, <em>, <strong>, <a href="…">, <table>, <thead>, <tbody>, <tr>, <th>, <td>. Any other tag will be stripped server-side.

Rules:
- Preserve chunk_ids verbatim from the input analyst output. Never invent IDs.
- Neutral observational tone throughout. Frame as "speakers said X (link)", not "speakers were wrong about X".
- Computed numbers in the tables MUST come from the aggregations input — do not invent counts.
- The summary paragraph is the FIRST thing the user reads. Make it factual and substantive; avoid filler like "this brief covers…".
- Do not include a top-level <h1> — the page chrome supplies the title."""

SYSTEM_PROMPT_STANCE_MAP = """You are a careful research analyst. You will be shown N quotes from various Canadian politicians on a search topic. For each quote, classify the speaker's stance toward the topic. Output strictly valid JSON of this exact shape:

{
  "classifications": [
    {
      "chunk_id": "<chunk_id from input, copied verbatim>",
      "stance": "for",
      "rationale": "<one neutral sentence describing why this stance>"
    }
  ]
}

The "stance" field must be one of: "for", "against", "conditional", "unrelated", "unclear".

- "for": speaker advocates or supports the topic.
- "against": speaker opposes the topic.
- "conditional": speaker supports/opposes only under specific conditions.
- "unrelated": chunk is not actually about the topic (retrieval miss).
- "unclear": chunk is ambiguous, or speaker is quoting another, or stance cannot be determined.

Rules:
- Classify EVERY input chunk_id; do not omit any.
- chunk_id MUST be copied verbatim from the input. Never invent IDs.
- Neutral analytical tone — describe what the speaker said, do not judge.
- If a chunk is the speaker quoting an opponent ("the member opposite said…"), classify as "unclear" — that is not the speaker's own stance."""

SYSTEM_PROMPT_STANCE_MAP_REDUCE = """You are synthesizing stance classifications from multiple analysts into a stance map. You will be shown the classifications grouped per-bucket, the chunk metadata (speaker name + party + a short text excerpt), and pre-computed aggregations over the chunk set. Group speakers by their predominant stance and produce HTML.

Output strictly valid JSON of this exact shape:

{
  "summary": "<one paragraph (60-100 words) framing the stance landscape on this topic, neutral observational tone>",
  "html": "<HTML body, see allowed tags below>"
}

The HTML body must, IN THIS ORDER:
1. A <h3>Who's in the room</h3> followed by a <table class="report-stats"> with <th>Party</th><th>Quotes</th> showing the top 5 from `aggregations.by_party` (skip "Unresolved / Chair" only if not largest).
2. For each non-empty stance group in this order — "For", "Against", "Conditional" — produce an <h3> with the stance label, followed by a <ul> listing speakers.
3. Each <li> contains the speaker name (in <strong>), followed by a short <em>exemplar quote</em> (under 30 words, a faithful excerpt of one of their classified chunks), followed by <a href="CHUNK:<chunk_id>">[source]</a>.
4. "unrelated" and "unclear" classifications are EXCLUDED from the visible map (they're noise). Do not produce sections for them.

Rules:
- If a speaker has multiple chunks classified the same way, list them once under their predominant stance using the most representative quote.
- If a speaker has chunks classified differently across buckets, use the predominant classification (most chunks); if tied, use "conditional".
- Counts in the stats table MUST come from the aggregations input — do not invent counts.
- Allowed HTML tags ONLY: <p>, <h2>, <h3>, <ul>, <ol>, <li>, <blockquote>, <em>, <strong>, <a href="…">, <table>, <thead>, <tbody>, <tr>, <th>, <td>.
- Use the literal token CHUNK:<id> for href values — the system rewrites them server-side.
- Preserve chunk_ids verbatim. Never invent IDs.
- Neutral analytical tone throughout."""


def _ordinal_suffix(n: int) -> str:
    mod100 = n % 100
    if 11 <= mod100 <= 13:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")


def _format_date(d: Any) -> str:
    if d is None:
        return "unknown"
    return d.date().isoformat() if hasattr(d, "date") else str(d)[:10]


def build_map_prompt(politician_name: str, party: str | None, topic: str, chunks: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    party_fragment = f" ({party})" if party else ""
    lines.append(f"Politician: {politician_name}{party_fragment}")
    lines.append(f"Query topic: {topic}")
    lines.append("")
    for c in chunks:
        text = c["text"] or ""
        truncated = text[:1200] + "…[truncated]" if len(text) > 1200 else text
        lines.append(f"Quote (chunk_id={c['id']}):")
        lines.append(f"  Date: {_format_date(c.get('spoken_at'))}")
        if c.get("parliament_number") is not None and c.get("session_number") is not None:
            lines.append(
                f"  Parliament: {c['parliament_number']}{_ordinal_suffix(c['parliament_number'])}, Session {c['session_number']}"
            )
        if c.get("party_at_time"):
            lines.append(f"  Party at time: {c['party_at_time']}")
        lines.append(f"  Text: {truncated}")
        lines.append("")
    lines.append("Return the JSON object described in the system prompt.")
    return "\n".join(lines)


def build_search_chunk_block(c: dict[str, Any], text_truncate: int = 1200) -> list[str]:
    """Render one chunk for the search_synthesis / stance_map map prompt.
    Differs from the per-politician build_map_prompt block by including
    the speaker's name and party — the search-result analyses are
    multi-speaker by definition."""
    text = c["text"] or ""
    truncated = text[:text_truncate] + "…[truncated]" if len(text) > text_truncate else text
    speaker = c.get("politician_name") or "Unknown speaker"
    party = c.get("politician_party")
    party_at_time = c.get("party_at_time")
    speaker_label = f"{speaker} ({party})" if party else speaker
    block: list[str] = [f"Quote (chunk_id={c['id']}):"]
    block.append(f"  Speaker: {speaker_label}")
    block.append(f"  Date: {_format_date(c.get('spoken_at'))}")
    if c.get("parliament_number") is not None and c.get("session_number") is not None:
        block.append(
            f"  Parliament: {c['parliament_number']}{_ordinal_suffix(c['parliament_number'])}, Session {c['session_number']}"
        )
    if party_at_time and party_at_time != party:
        block.append(f"  Party at time: {party_at_time}")
    block.append(f"  Text: {truncated}")
    block.append("")
    return block


def build_synthesize_map_prompt(topic: str, chunks: list[dict[str, Any]]) -> str:
    lines: list[str] = [f"Search topic: {topic}", ""]
    for c in chunks:
        lines.extend(build_search_chunk_block(c))
    lines.append("Return the JSON object described in the system prompt.")
    return "\n".join(lines)


def build_synthesize_reduce_prompt(
    topic: str, bucket_outputs: list[Any], aggregations: dict[str, Any]
) -> str:
    return "\n".join([
        f"Search topic: {topic}",
        "",
        "Aggregations over the analysed chunk set (use these to render the stats table at the top of your HTML output):",
        json.dumps(aggregations, indent=2),
        "",
        "Per-bucket analyst output (JSON array, each element is one analyst's claims):",
        json.dumps(bucket_outputs, indent=2),
        "",
        "Return the synthesised JSON object described in the system prompt.",
    ])


def build_stance_map_prompt(topic: str, chunks: list[dict[str, Any]]) -> str:
    """Map prompt for stance_map. Same chunk format as synthesize but
    with a shorter text truncation — the model only needs enough text
    to classify the stance, not to extract substantive claims."""
    lines: list[str] = [f"Topic: {topic}", ""]
    for c in chunks:
        lines.extend(build_search_chunk_block(c, text_truncate=800))
    lines.append("Classify EVERY chunk_id. Return the JSON object described in the system prompt.")
    return "\n".join(lines)


def build_stance_map_reduce_prompt(
    topic: str, bucket_outputs: list[Any], chunks: list[dict[str, Any]],
    aggregations: dict[str, Any],
) -> str:
    """Reduce prompt for stance_map. Carries the chunk metadata forward
    so the model can attribute exemplar quotes to speakers without
    cross-referencing back to the map output. Aggregations are passed
    so the model can render a stats table at the top of the output."""
    chunk_metadata = [
        {
            "chunk_id": str(c["id"]),
            "speaker": c.get("politician_name") or "Unknown",
            "party": c.get("politician_party"),
            "excerpt": ((c["text"] or "")[:200]).replace("\n", " "),
        }
        for c in chunks
    ]
    return "\n".join([
        f"Topic: {topic}",
        "",
        "Aggregations over the classified chunk set (use these to render the stats table at the top of your HTML output):",
        json.dumps(aggregations, indent=2),
        "",
        "Chunk metadata (speaker + short excerpt) for attribution:",
        json.dumps(chunk_metadata, indent=2),
        "",
        "Per-bucket analyst classifications (JSON array, each element is one analyst's classifications):",
        json.dumps(bucket_outputs, indent=2),
        "",
        "Return the synthesised JSON object described in the system prompt.",
    ])


def build_reduce_prompt(politician_name: str, party: str | None, topic: str, bucket_summaries: list[Any]) -> str:
    return "\n".join([
        f"Politician: {politician_name}{f' ({party})' if party else ''}",
        f"Query topic: {topic}",
        "",
        "Per-bucket analyst output (JSON array, each element is one analyst's themes):",
        json.dumps(bucket_summaries, indent=2),
        "",
        "Return the synthesised JSON object described in the system prompt.",
    ])


# ── OpenRouter ──────────────────────────────────────────────────────


class OpenRouterError(RuntimeError):
    def __init__(self, kind: str, status: int | None = None, body: str = ""):
        super().__init__(f"openrouter {kind} status={status} body={body[:200]}")
        self.kind = kind
        self.status = status
        self.body = body


async def call_json_object_model(
    client: httpx.AsyncClient, system: str, user: str
) -> tuple[dict[str, Any], int, int, str]:
    """Returns (parsed_json, tokens_in, tokens_out, model_used).
    Raises OpenRouterError on auth/rate_limit/timeout/upstream/non_json."""
    if not OPENROUTER_API_KEY:
        raise OpenRouterError("auth", status=401)
    try:
        resp = await client.post(
            f"{OPENROUTER_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "HTTP-Referer": OPENROUTER_SITE_URL,
                "X-Title": OPENROUTER_APP_NAME,
                "Content-Type": "application/json",
            },
            json={
                "model": OPENROUTER_REPORT_MODEL,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "response_format": {"type": "json_object"},
                "plugins": [{"id": "response-healing"}],
                "temperature": 0.2,
            },
            timeout=OPENROUTER_REPORT_TIMEOUT_MS / 1000.0,
        )
    except httpx.TimeoutException as e:
        raise OpenRouterError("timeout") from e
    except httpx.HTTPError as e:
        raise OpenRouterError("network", body=str(e)) from e

    if resp.status_code == 401:
        raise OpenRouterError("auth", status=401, body=resp.text[:500])
    if resp.status_code == 429:
        raise OpenRouterError("rate_limit", status=429, body=resp.text[:500])
    if resp.status_code >= 400:
        raise OpenRouterError("upstream", status=resp.status_code, body=resp.text[:500])

    try:
        body = resp.json()
    except json.JSONDecodeError as e:
        raise OpenRouterError("non_json", body=resp.text[:500]) from e

    content = (body.get("choices") or [{}])[0].get("message", {}).get("content")
    if not isinstance(content, str):
        raise OpenRouterError("bad_shape", body=str(body)[:500])

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as e:
        raise OpenRouterError("bad_json", body=content[:500]) from e

    usage = body.get("usage") or {}
    return (
        parsed,
        int(usage.get("prompt_tokens") or 0),
        int(usage.get("completion_tokens") or 0),
        body.get("model") or OPENROUTER_REPORT_MODEL,
    )


# ── HTML sanitise + chunk-link rewrite ──────────────────────────────

ALLOWED_TAGS = [
    "p", "h2", "h3", "ul", "ol", "li", "blockquote", "em", "strong", "a",
    # Table tags permitted so the new chunk-driven kinds (search_synthesis,
    # stance_map) can render the dashboard-style aggregation table at the
    # top of the report. The model is constrained by prompt to use these
    # only for the stats <table>; bleach strips anything else.
    "table", "thead", "tbody", "tr", "th", "td",
]
ALLOWED_ATTRS = {"a": ["href"], "table": ["class"], "th": ["scope"]}
ALLOWED_PROTOCOLS = ["http", "https"]

_CHUNK_HREF_RE = re.compile(r"""href=(["'])CHUNK:([0-9a-f-]{36})\1""", re.IGNORECASE)


def rewrite_chunk_links(html: str, chunks: list[dict[str, Any]]) -> str:
    by_id = {str(c["id"]): c for c in chunks}

    def _repl(m: re.Match[str]) -> str:
        quote = m.group(1)
        chunk_id = m.group(2)
        c = by_id.get(chunk_id)
        if not c:
            return ""  # strip unknown href entirely
        return f"href={quote}/speeches/{c['speech_id']}#chunk-{chunk_id}{quote}"

    return _CHUNK_HREF_RE.sub(_repl, html)


def sanitise_html(html: str) -> str:
    cleaned = bleach.clean(
        html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRS,
        protocols=ALLOWED_PROTOCOLS,
        strip=True,
    )
    # Internal-paths-only allowlist on <a href>: anything that doesn't
    # start with /speeches/ has its href stripped. The link text remains.
    return re.sub(
        r'<a\s+([^>]*?)href=("[^"]*"|\'[^\']*\')([^>]*)>',
        lambda m: _enforce_internal_href(m),
        cleaned,
    )


def _enforce_internal_href(m: re.Match[str]) -> str:
    pre = m.group(1)
    href = m.group(2).strip("\"'")
    post = m.group(3)
    if href.startswith("/speeches/"):
        return f'<a {pre}href="{href}"{post}>'
    return f"<a {pre}{post}>"


# ── Embedding (TEI) ─────────────────────────────────────────────────


async def embed_query(client: httpx.AsyncClient, text: str) -> list[float]:
    wrapped = INSTRUCT_PREFIX + text
    r = await client.post(
        f"{EMBED_URL}/embed",
        json={"inputs": [wrapped], "normalize": True},
        timeout=30.0,
    )
    r.raise_for_status()
    data = r.json()
    if isinstance(data, list) and isinstance(data[0], list):
        return data[0]
    if isinstance(data, dict) and "data" in data:
        return data["data"][0]["embedding"]
    raise RuntimeError("Unexpected TEI /embed response shape")


def to_pgvector(vec: list[float]) -> str:
    return "[" + ",".join(str(x) for x in vec) + "]"


# ── DB ──────────────────────────────────────────────────────────────


async def claim_next_job(db: Database) -> dict[str, Any] | None:
    """Atomically claim the oldest queued job. Also re-queues any
    'running' job whose claim has gone stale (worker crashed mid-run)."""
    # First sweep: re-queue stale 'running' rows so they become claimable.
    await db.execute(
        f"""UPDATE private.report_jobs
              SET status = 'queued', claimed_at = NULL
            WHERE status = 'running'
              AND claimed_at IS NOT NULL
              AND claimed_at < now() - interval '{STALE_CLAIM_MINUTES} minutes'""",
    )
    row = await db.fetchrow(
        """UPDATE private.report_jobs
              SET status = 'running',
                  claimed_at = now(),
                  started_at = COALESCE(started_at, now())
            WHERE id = (
              SELECT id FROM private.report_jobs
               WHERE status = 'queued'
               ORDER BY priority DESC, created_at
               LIMIT 1
               FOR UPDATE SKIP LOCKED
            )
            RETURNING id, kind, user_id, politician_id, query, inputs,
                      estimated_chunks, estimated_credits, hold_ledger_id"""
    )
    if not row:
        return None
    out = dict(row)
    # asyncpg returns jsonb as text unless a codec is registered. Decode
    # defensively so handlers can always assume `inputs` is a dict.
    raw_inputs = out.get("inputs")
    if isinstance(raw_inputs, str):
        try:
            out["inputs"] = json.loads(raw_inputs)
        except json.JSONDecodeError:
            out["inputs"] = {}
    elif raw_inputs is None:
        out["inputs"] = {}
    return out


async def commit_hold(db: Database, hold_ledger_id: Any) -> None:
    """Mirror of services/api/src/lib/credits.ts:commitHold (idempotent state-flip)."""
    if hold_ledger_id is None:
        return
    await db.execute(
        """UPDATE private.credit_ledger
              SET state = 'committed'
            WHERE id = $1
              AND state = 'held'
              AND kind = 'report_hold'""",
        hold_ledger_id,
    )


async def release_hold(db: Database, hold_ledger_id: Any, reason: str) -> None:
    """Mirror of services/api/src/lib/credits.ts:releaseHold."""
    if hold_ledger_id is None:
        return
    await db.execute(
        """UPDATE private.credit_ledger
              SET state = 'refunded',
                  reason = $2
            WHERE id = $1
              AND state = 'held'
              AND kind = 'report_hold'""",
        hold_ledger_id,
        reason,
    )


async def select_chunks_by_ids(db: Database, chunk_ids: list[str]) -> list[dict[str, Any]]:
    """Fetch chunk metadata + text by IDs. Used by search_synthesis and
    stance_map: the frontend already ran the search and supplied the
    top-K chunk_ids, so we just SELECT them with the metadata the prompts
    need (politician name + party for stance attribution, session number
    for context). Order is preserved relative to the input list — the
    frontend's relevance ranking carries through."""
    if not chunk_ids:
        return []
    async with db.pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT sc.id, sc.speech_id, sc.text, sc.spoken_at, sc.party_at_time,
                      sc.politician_id,
                      p.name  AS politician_name,
                      p.party AS politician_party,
                      ls.parliament_number, ls.session_number,
                      s.source_url, s.source_anchor
                 FROM speech_chunks sc
                 JOIN speeches s ON s.id = sc.speech_id
                 LEFT JOIN politicians p ON p.id = sc.politician_id
                 LEFT JOIN legislative_sessions ls ON ls.id = s.session_id
                WHERE sc.id = ANY($1::uuid[])""",
            chunk_ids,
        )
    by_id = {str(r["id"]): dict(r) for r in rows}
    return [by_id[cid] for cid in chunk_ids if cid in by_id]


async def select_chunks(
    db: Database, politician_id: Any, vec_literal: str, limit: int
) -> list[dict[str, Any]]:
    """SET LOCAL hnsw.ef_search must live inside a transaction or it has
    no effect. Acquire a dedicated connection so the SET applies to the
    SELECT that follows it."""
    async with db.pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(f"SET LOCAL hnsw.ef_search = {REPORT_HNSW_EF_SEARCH}")
            rows = await conn.fetch(
                """SELECT sc.id, sc.speech_id, sc.text, sc.spoken_at, sc.party_at_time,
                          ls.parliament_number, ls.session_number,
                          s.source_url, s.source_anchor
                     FROM speech_chunks sc
                     JOIN speeches s ON s.id = sc.speech_id
                     LEFT JOIN legislative_sessions ls ON ls.id = s.session_id
                    WHERE sc.embedding IS NOT NULL
                      AND sc.politician_id = $1
                      AND (sc.embedding <=> $2::vector) <= 0.55
                    ORDER BY sc.embedding <=> $2::vector
                    LIMIT $3""",
                politician_id,
                vec_literal,
                limit,
            )
    return [dict(r) for r in rows]


# ── Email (mirrors api/lib/email.ts:sendReportReadyEmail) ───────────


def smtp_is_configured() -> bool:
    return bool(SMTP_USERNAME and SMTP_PASSWORD and SMTP_FROM)


def send_smtp(to: str, subject: str, text: str, html: str | None = None) -> None:
    msg = EmailMessage()
    msg["From"] = SMTP_FROM
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(text)
    if html is not None:
        msg.add_alternative(html, subtype="html")
    ctx = ssl.create_default_context()
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as s:
        s.ehlo()
        s.starttls(context=ctx)
        s.ehlo()
        s.login(SMTP_USERNAME, SMTP_PASSWORD)
        s.send_message(msg)


async def deliver_email(to: str, subject: str, text: str, html: str) -> None:
    if not smtp_is_configured():
        log.info("[smtp:stub] would send to=%s subject=%r\n--- body ---\n%s\n--- end ---", to, subject, text)
        return
    await asyncio.to_thread(send_smtp, to, subject, text, html)


# ── Job runner ─────────────────────────────────────────────────────


# ── Generic map-reduce + handler dispatch ──────────────────────────


@dataclass(slots=True)
class HandlerOutput:
    """What every per-kind handler returns to the dispatcher. Common
    shape lets process_job's persist + email logic stay kind-agnostic."""
    html: str
    summary: str
    chunks: list[dict[str, Any]]  # carried for chunk-link rewriting
    tokens_in: int
    tokens_out: int
    model_used: str


class HandlerError(RuntimeError):
    """User-facing error raised inside a handler. Message is shown to
    the user on the failure page + email; never includes internal
    stack-trace details. The dispatcher catches and routes to fail_job
    with the message verbatim."""


async def run_map_reduce_pipeline(
    client: httpx.AsyncClient,
    chunks: list[dict[str, Any]],
    bucket_size: int,
    map_system_prompt: str,
    reduce_system_prompt: str,
    build_map_user_prompt: Callable[[list[dict[str, Any]]], str],
    build_reduce_user_prompt: Callable[[list[Any]], str],
) -> tuple[dict[str, Any], int, int, str]:
    """Generic map-reduce skeleton shared by every kind handler.

    Buckets the chunks at bucket_size, fans out concurrent map calls
    (semaphore 2 to be polite to OpenRouter burst limits), then runs a
    single reduce on the combined outputs. Returns (parsed_reduce_output,
    total_tokens_in, total_tokens_out, model_used_in_reduce).

    OpenRouterError propagates — caller (the kind handler) decides
    whether to wrap it. HandlerError-style user-facing wrapping happens
    in the dispatcher, not here."""
    buckets = [chunks[i : i + bucket_size] for i in range(0, len(chunks), bucket_size)]
    # Concurrency 4 keeps K=500 (50 buckets) under ~3min round-trip
    # without exhausting OpenRouter's per-provider per-account limits.
    # If we ever bump higher, watch for 429s in the worker logs.
    sem = asyncio.Semaphore(4)

    async def run_map(bucket: list[dict[str, Any]]) -> Any:
        async with sem:
            return await call_json_object_model(
                client, map_system_prompt, build_map_user_prompt(bucket)
            )

    map_results = await asyncio.gather(*[run_map(b) for b in buckets])
    bucket_outputs: list[Any] = []
    tokens_in = 0
    tokens_out = 0
    model_used = OPENROUTER_REPORT_MODEL
    for parsed, ti, tout, model in map_results:
        tokens_in += ti
        tokens_out += tout
        model_used = model
        bucket_outputs.append(parsed)

    reduce_parsed, ri, ro, reduce_model = await call_json_object_model(
        client, reduce_system_prompt, build_reduce_user_prompt(bucket_outputs)
    )
    return reduce_parsed, tokens_in + ri, tokens_out + ro, reduce_model


def _validate_reduce_output(parsed: dict[str, Any]) -> tuple[str, str]:
    """Common shape validation: every reduce step returns {html, summary}."""
    raw_html = parsed.get("html")
    summary = parsed.get("summary")
    if not isinstance(raw_html, str) or not isinstance(summary, str):
        raise HandlerError("AI synthesis returned unexpected shape")
    return raw_html, summary


# ── Per-kind handlers ──────────────────────────────────────────────


async def handle_full_report(
    db: Database, job: dict[str, Any], client: httpx.AsyncClient, _user: Any
) -> HandlerOutput:
    """Phase 1b's existing per-politician + topic report. Lifted from
    the original process_job body unchanged; behaviour is bit-for-bit
    identical so existing flows keep working."""
    if not job.get("politician_id") or not job.get("query"):
        raise HandlerError("full_report job missing politician_id or query")

    pol = await db.fetchrow(
        "SELECT name, party FROM politicians WHERE id = $1", job["politician_id"]
    )
    if not pol:
        raise HandlerError("politician not found")
    politician_name = pol["name"] or "Unknown politician"
    party = pol["party"]
    topic = job["query"]

    try:
        vec = await embed_query(client, topic)
    except Exception as e:  # noqa: BLE001
        log.exception("embed failed for job=%s: %s", job["id"], e)
        raise HandlerError("Failed to embed query") from e
    vec_literal = to_pgvector(vec)

    try:
        chunks = await select_chunks(db, job["politician_id"], vec_literal, REPORT_MAX_CHUNKS)
    except Exception as e:  # noqa: BLE001
        log.exception("chunk fetch failed for job=%s: %s", job["id"], e)
        raise HandlerError("Failed to retrieve speech chunks") from e
    if not chunks:
        raise HandlerError("No matching quotes found for this politician + query")

    parsed, tokens_in, tokens_out, model_used = await run_map_reduce_pipeline(
        client,
        chunks,
        REPORT_BUCKET_SIZE,
        SYSTEM_PROMPT_MAP,
        SYSTEM_PROMPT_REDUCE,
        lambda bucket: build_map_prompt(politician_name, party, topic, bucket),
        lambda outputs: build_reduce_prompt(politician_name, party, topic, outputs),
    )
    raw_html, summary = _validate_reduce_output(parsed)
    return HandlerOutput(
        html=raw_html,
        summary=summary,
        chunks=chunks,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        model_used=model_used,
    )


def compute_chunk_aggregations(chunks: list[dict[str, Any]]) -> dict[str, Any]:
    """Roll up chunk metadata into the same facet shape the dashboard
    tiles render. Passed into the reduce prompt as JSON so the model
    can include a 'who, what, when' stats table at the top of the
    output — matching the dashboard view the user just looked at on
    the Analysis tab.

    Aggregations match `services/api/src/routes/search.ts` /facets
    response shape (party / politician / year / language) so the
    worker output is consistent with the dashboard the user saw."""
    by_party: dict[str | None, int] = {}
    by_speaker: dict[tuple[str | None, str | None], int] = {}
    by_year: dict[int | None, int] = {}
    by_language: dict[str | None, int] = {}
    for c in chunks:
        party = c.get("party_at_time") or c.get("politician_party")
        by_party[party] = by_party.get(party, 0) + 1
        speaker_key = (
            c.get("politician_id"),
            c.get("politician_name") or c.get("speaker_name_raw"),
        )
        by_speaker[speaker_key] = by_speaker.get(speaker_key, 0) + 1
        spoken = c.get("spoken_at")
        year = spoken.year if spoken is not None and hasattr(spoken, "year") else None
        by_year[year] = by_year.get(year, 0) + 1
        lang = c.get("language")
        by_language[lang] = by_language.get(lang, 0) + 1

    party_rows = sorted(
        ({"party": k or "Unresolved / Chair", "count": v} for k, v in by_party.items()),
        key=lambda r: (-r["count"], r["party"] or ""),
    )
    speaker_rows = sorted(
        (
            # asyncpg returns politician_id as a uuid.UUID; stringify
            # so json.dumps in the reduce prompt doesn't choke.
            {"politician_id": str(pid) if pid is not None else None,
             "name": name or "Unknown",
             "count": v}
            for (pid, name), v in by_speaker.items()
        ),
        key=lambda r: (-r["count"], r["name"]),
    )[:10]
    year_rows = sorted(
        ({"year": y, "count": v} for y, v in by_year.items() if y is not None),
        key=lambda r: r["year"],
    )
    lang_rows = sorted(
        ({"language": l, "count": v} for l, v in by_language.items() if l is not None),
        key=lambda r: -r["count"],
    )
    return {
        "total_chunks": len(chunks),
        "by_party": party_rows,
        "top_speakers": speaker_rows,
        "by_year": year_rows,
        "by_language": lang_rows,
    }


async def _handle_chunk_driven_kind(
    db: Database,
    job: dict[str, Any],
    client: httpx.AsyncClient,
    map_system_prompt: str,
    reduce_system_prompt: str,
    build_map: Callable[[str, list[dict[str, Any]]], str],
    build_reduce: Callable[[str, list[Any], list[dict[str, Any]], dict[str, Any]], str],
) -> HandlerOutput:
    """Shared body for kinds whose chunks come from inputs.chunk_ids
    (search_synthesis, stance_map). Differs from full_report only in
    where the chunks come from + which prompts drive the map-reduce.

    The reduce builder takes (topic, bucket_outputs, chunks) so kinds
    that need chunk metadata in the reduce step (stance_map for speaker
    attribution) can read it without re-fetching."""
    inputs = job.get("inputs") or {}
    raw_chunk_ids = inputs.get("chunk_ids") or []
    chunk_ids = [str(cid) for cid in raw_chunk_ids if cid]
    topic = inputs.get("query") or ""
    if not chunk_ids:
        raise HandlerError("No chunk_ids supplied")

    try:
        chunks = await select_chunks_by_ids(db, chunk_ids)
    except Exception as e:  # noqa: BLE001
        log.exception("chunk fetch failed for job=%s: %s", job["id"], e)
        raise HandlerError("Failed to retrieve speech chunks") from e
    if not chunks:
        raise HandlerError("No matching speech chunks for the supplied IDs")

    aggregations = compute_chunk_aggregations(chunks)

    parsed, tokens_in, tokens_out, model_used = await run_map_reduce_pipeline(
        client,
        chunks,
        REPORT_BUCKET_SIZE,
        map_system_prompt,
        reduce_system_prompt,
        lambda bucket: build_map(topic, bucket),
        lambda outputs: build_reduce(topic, outputs, chunks, aggregations),
    )
    raw_html, summary = _validate_reduce_output(parsed)
    return HandlerOutput(
        html=raw_html,
        summary=summary,
        chunks=chunks,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        model_used=model_used,
    )


async def handle_search_synthesis(
    db: Database, job: dict[str, Any], client: httpx.AsyncClient, _user: Any
) -> HandlerOutput:
    return await _handle_chunk_driven_kind(
        db,
        job,
        client,
        SYSTEM_PROMPT_SYNTHESIZE_MAP,
        SYSTEM_PROMPT_SYNTHESIZE_REDUCE,
        build_synthesize_map_prompt,
        # Synthesize reduce doesn't need chunk metadata — drop the third arg.
        lambda topic, outputs, _chunks, agg: build_synthesize_reduce_prompt(topic, outputs, agg),
    )


async def handle_stance_map(
    db: Database, job: dict[str, Any], client: httpx.AsyncClient, _user: Any
) -> HandlerOutput:
    return await _handle_chunk_driven_kind(
        db,
        job,
        client,
        SYSTEM_PROMPT_STANCE_MAP,
        SYSTEM_PROMPT_STANCE_MAP_REDUCE,
        build_stance_map_prompt,
        build_stance_map_reduce_prompt,
    )


KindHandler = Callable[
    [Database, dict[str, Any], httpx.AsyncClient, Any], Awaitable[HandlerOutput]
]

KIND_HANDLERS: dict[str, KindHandler] = {
    "full_report": handle_full_report,
    "search_synthesis": handle_search_synthesis,
    "stance_map": handle_stance_map,
    # Adding a new kind: register the handler here AND extend the
    # report_jobs_kind_check CHECK constraint in a new migration AND
    # extend KIND_COST_FORMULA in services/api/src/lib/reports.ts.
}


def kind_label(kind: str) -> str:
    """Display label for emails / failed messages."""
    return {
        "full_report": "report",
        "search_synthesis": "search synthesis",
        "stance_map": "stance map",
    }.get(kind, "analysis")


def _kind_subject(kind: str, politician_name: str | None, topic: str) -> str:
    """Email subject line per kind."""
    label = kind_label(kind)
    if kind == "full_report" and politician_name:
        return f"Your {label} on {politician_name} is ready"
    snippet = (topic or "").strip()
    if len(snippet) > 60:
        snippet = snippet[:60].rstrip() + "…"
    if snippet:
        return f"Your {label} on '{snippet}' is ready"
    return f"Your {label} is ready"


def _ready_subject_target(kind: str, politician_name: str | None, topic: str) -> str:
    """Inline label used in the ready-email body — e.g. 'on Jane Doe' for
    full_report, "on 'carbon tax'" for search-driven kinds."""
    if kind == "full_report" and politician_name:
        return f"on {politician_name} ({topic})"
    return f"on '{topic[:60]}'" if topic else ""


# ── Dispatcher ──────────────────────────────────────────────────────


async def process_job(db: Database, job: dict[str, Any]) -> None:
    """Dispatch on `kind`, run the matching handler, persist + commit on
    success, fail+refund on error."""
    job_id = job["id"]
    kind = job.get("kind") or "full_report"
    log.info("processing job=%s kind=%s user=%s", job_id, kind, job["user_id"])

    handler = KIND_HANDLERS.get(kind)
    if handler is None:
        await fail_job(db, job, f"Unknown analysis kind: {kind}")
        return

    user = await db.fetchrow(
        "SELECT email, display_name, email_bounced_at FROM private.users WHERE id = $1",
        job["user_id"],
    )
    if not user:
        await fail_job(db, job, "missing user row")
        return

    # Display fields used in emails. politician_name is only meaningful
    # for full_report; for chunk-driven kinds the topic comes from
    # inputs.query (not the column).
    inputs = job.get("inputs") or {}
    topic = job.get("query") or inputs.get("query") or ""
    politician_name: str | None = None
    if job.get("politician_id"):
        pol = await db.fetchrow(
            "SELECT name FROM politicians WHERE id = $1", job["politician_id"]
        )
        if pol:
            politician_name = pol["name"]

    async with httpx.AsyncClient() as client:
        try:
            output = await handler(db, job, client, user)
        except HandlerError as e:
            log.info("handler raised user-facing error job=%s kind=%s: %s", job_id, kind, e)
            await fail_job(db, job, str(e))
            await maybe_send_failed_email(user, politician_name, topic, job_id, kind)
            return
        except OpenRouterError as e:
            log.warning("openrouter failed job=%s kind=%s: %s", job_id, kind, e)
            await fail_job(db, job, _user_facing_openrouter_error(e))
            await maybe_send_failed_email(user, politician_name, topic, job_id, kind)
            return
        except Exception as e:  # noqa: BLE001
            log.exception("unexpected handler failure job=%s kind=%s: %s", job_id, kind, e)
            await fail_job(db, job, "Worker error during analysis")
            await maybe_send_failed_email(user, politician_name, topic, job_id, kind)
            return

    # Rewrite chunk links → real URLs, then sanitise. Common to all kinds.
    rewritten = rewrite_chunk_links(output.html, output.chunks)
    clean_html = sanitise_html(rewritten)

    # Persist + commit hold.
    await db.execute(
        """UPDATE private.report_jobs
              SET status = 'succeeded',
                  html = $2,
                  summary = $3,
                  chunk_count_actual = $4,
                  model_used = $5,
                  tokens_in = $6,
                  tokens_out = $7,
                  finished_at = now(),
                  error = NULL
            WHERE id = $1""",
        job_id,
        clean_html,
        output.summary,
        len(output.chunks),
        output.model_used,
        output.tokens_in,
        output.tokens_out,
    )
    await commit_hold(db, job["hold_ledger_id"])
    log.info(
        "job=%s kind=%s succeeded chunks=%d tokens=%d/%d",
        job_id, kind, len(output.chunks), output.tokens_in, output.tokens_out,
    )

    # Email.
    if user["email_bounced_at"] is None:
        report_url = f"{PUBLIC_SITE_URL}/reports/{job_id}"
        subject = _kind_subject(kind, politician_name, topic)
        target = _ready_subject_target(kind, politician_name, topic)
        try:
            await deliver_email(
                to=user["email"],
                subject=subject,
                text=render_ready_text_kind(kind, target, output.summary, report_url),
                html=render_ready_html_kind(kind, target, output.summary, report_url),
            )
        except Exception as e:  # noqa: BLE001
            log.warning("ready email send failed for job=%s: %s", job_id, e)


def render_ready_text_kind(kind: str, target: str, summary: str | None, report_url: str) -> str:
    label = kind_label(kind)
    target_part = f" {target}" if target else ""
    return (
        f"Your {label}{target_part} is ready.\n"
        f"\n"
        f"{(summary or '').strip()}\n"
        f"\n"
        f"Read the full {label}: {report_url}\n"
        f"\n"
        f"Every claim links back to a source quote. Read the quotes before\n"
        f"drawing conclusions — the synthesis is generative and can omit,\n"
        f"misweight, or mischaracterise.\n"
        f"\n"
        f"Canadian Political Data\n"
    )


def render_ready_html_kind(kind: str, target: str, summary: str | None, report_url: str) -> str:
    label = kind_label(kind)
    safe_summary = (summary or "").replace("<", "&lt;").replace(">", "&gt;")
    safe_target = target.replace("<", "&lt;").replace(">", "&gt;")
    target_part = f" <em>{safe_target}</em>" if safe_target else ""
    return f"""<p>Your <strong>{label}</strong>{target_part} is ready.</p>
<blockquote style="border-left:3px solid #e11d48;padding-left:1em;color:#444">
{safe_summary}
</blockquote>
<p><a href="{report_url}" style="background:#e11d48;color:white;padding:10px 18px;
border-radius:6px;text-decoration:none">Read the full {label}</a></p>
<p style="color:#666;font-size:.9em">Every claim links back to a source quote. The
synthesis is generative — read the quotes before drawing conclusions.</p>
<p style="color:#888;font-size:.8em">Canadian Political Data</p>"""


def _user_facing_openrouter_error(e: OpenRouterError) -> str:
    if e.kind == "rate_limit":
        return "AI service is currently rate-limited. Please try again later."
    if e.kind == "auth":
        return "AI service authentication failed. Operator has been notified."
    if e.kind == "timeout":
        return "AI service timed out while generating the report."
    if e.kind == "upstream":
        return "AI service returned an error."
    return "AI service error during report generation."


async def fail_job(db: Database, job: dict[str, Any], message: str) -> None:
    await db.execute(
        """UPDATE private.report_jobs
              SET status = 'failed',
                  error = $2,
                  finished_at = now()
            WHERE id = $1""",
        job["id"],
        message,
    )
    await release_hold(db, job["hold_ledger_id"], f"report failed: {message[:200]}")
    log.info("job=%s failed: %s", job["id"], message)


async def maybe_send_failed_email(
    user_row: Any,
    politician_name: str | None,
    topic: str,
    job_id: Any,
    kind: str = "full_report",
) -> None:
    if user_row is None or user_row["email_bounced_at"] is not None:
        return
    bug_url = f"{PUBLIC_SITE_URL}/reports/{job_id}"
    label = kind_label(kind)
    target = _ready_subject_target(kind, politician_name, topic)
    subject = f"Your {label} couldn't be generated"
    try:
        await deliver_email(
            to=user_row["email"],
            subject=subject,
            text=render_failed_text_kind(label, target, bug_url),
            html=render_failed_html_kind(label, target, bug_url),
        )
    except Exception as e:  # noqa: BLE001
        log.warning("failed-email send failed for job=%s: %s", job_id, e)


def render_failed_text_kind(label: str, target: str, bug_url: str | None) -> str:
    target_part = f" {target}" if target else ""
    parts = [
        f"Your {label}{target_part} couldn't be generated.",
        "",
        "Your credits have been refunded automatically.",
        "",
    ]
    if bug_url:
        parts.append(f"Tell us what went wrong: {bug_url}")
        parts.append("")
    parts.append("Canadian Political Data")
    return "\n".join(parts)


def render_failed_html_kind(label: str, target: str, bug_url: str | None) -> str:
    safe_target = target.replace("<", "&lt;").replace(">", "&gt;")
    target_part = f" <em>{safe_target}</em>" if safe_target else ""
    bug_section = (
        f'<p><a href="{bug_url}">Tell us what went wrong →</a></p>' if bug_url else ""
    )
    return f"""<p>Your <strong>{label}</strong>{target_part} couldn't be generated.</p>
<p><strong>Your credits have been refunded automatically.</strong></p>
{bug_section}
<p style="color:#888;font-size:.8em">Canadian Political Data</p>"""


# ── Main loop ──────────────────────────────────────────────────────


_stop = asyncio.Event()


def _handle_signal(sig: int) -> None:
    log.info("signal %d — shutting down", sig)
    _stop.set()


async def main() -> None:
    logging.basicConfig(
        level=os.environ.get("REPORTS_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s reports-worker %(message)s",
    )
    log.info(
        "reports-worker starting poll=%ds model=%s smtp_configured=%s site=%s",
        POLL_INTERVAL, OPENROUTER_REPORT_MODEL, smtp_is_configured(), PUBLIC_SITE_URL,
    )
    if not OPENROUTER_API_KEY:
        log.warning("OPENROUTER_API_KEY unset — every job will fail at the map step until configured")

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _handle_signal, sig)

    db = Database(get_dsn())
    await db.connect()
    try:
        while not _stop.is_set():
            try:
                job = await claim_next_job(db)
                if job:
                    await process_job(db, job)
                    continue
            except Exception as e:  # noqa: BLE001
                log.exception("tick failed: %s", e)
            for _ in range(POLL_INTERVAL):
                if _stop.is_set():
                    break
                await asyncio.sleep(1)
    finally:
        await db.close()
