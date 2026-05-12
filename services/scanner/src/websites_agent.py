"""Tier-3 Sonnet agent for discovering politician personal/party websites.

Mirror of `socials_agent.py`. One agent call handles a batch of
politicians (default 10). The Anthropic web_search tool is hard-capped at
3 searches per politician via the `max_uses` parameter on the tool
definition itself — the prompt's "≤3 searches" guidance is reinforced by
that hard cap so the model can't spiral.

Output shape per politician (the agent returns the best single hit):

  kind        — "personal" (own site / campaign / constituency office),
                "campaign" (explicit campaign domain),
                "party_lander" (party's MP/MLA listing page that names them);
                fallback when no personal site is findable in 3 searches.
  url         — the canonical URL of the page itself.
  confidence  — agent self-reported [0, 1]. <0.85 lands in review queue.
  evidence_url— page that proves the site belongs to this person.

Insertion thresholds (see `websites.py::_should_flag`):
  agent_sonnet rows are flagged_low_confidence=true below 0.85.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any, Optional

import orjson
from rich.console import Console
from rich.table import Table

from .db import Database
from .websites import ALLOWED_LABELS, upsert_website

log = logging.getLogger(__name__)
console = Console()


DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_MAX_TOKENS = 4096
DEFAULT_BATCH_SIZE = 10
MAX_BATCH_SIZE = 25
PER_POLITICIAN_SEARCH_BUDGET = 3  # the user-mandated hard cap

AGENT_PROMOTE_THRESHOLD = 0.85
AGENT_MIN_WRITE = 0.60


SYSTEM_PROMPT = """You are auditing personal websites for Canadian politicians.

For each politician in the batch, use the web_search tool to find ONE best website that represents them. Return one JSON object for the whole batch:

{
  "results": [
    {
      "politician_id": "<uuid from the batch>",
      "kind": "personal" | "campaign" | "party_lander",
      "url": "https://...",
      "confidence": 0.0,
      "evidence_url": "https://...",
      "reasoning": "<one short line>"
    },
    ...
  ]
}

Hard rules:

- Return **only** the JSON object — no prose before or after.
- Return at most ONE hit per politician. If you can't find anything,
  omit that politician.
- **Up to 3 web_searches per politician.** Do not spiral. The tool will
  reject further searches once the budget is exhausted.

Preference order (try in this order):

1. **personal** — the politician's own website, campaign site, or
   constituency-office page. Examples: justintrudeau.ca,
   pierrepoilievre.ca, jagmeetsingh.ca, votenameXYZ.ca. **Strongly
   preferred.** confidence 0.85-1.0 if URL is clearly theirs.

2. **campaign** — an explicit campaign-only domain (often seasonal,
   sometimes party-co-branded). confidence 0.75-0.95.

3. **party_lander** — the politician's party's MP/MLA listing page that
   names them, e.g. https://www.conservative.ca/team/<name>,
   https://liberal.ca/your-liberal-mps/<slug>,
   https://www.ndp.ca/team/<slug>. **Fallback only** — use when 1-2
   yield no result within budget. confidence 0.50-0.85.

Hard rules on accuracy:

- **Do NOT invent URLs.** If web_search doesn't surface a clear hit,
  omit. A correctly-omitted politician is better than a wrong URL.
- **Match the specific person**, not someone with a similar name. Use
  party + jurisdiction + constituency from the brief to disambiguate.
- `evidence_url` MUST be a page you actually visited via web_search
  that names the politician + their role + links/refers to the URL.
  Their parliamentary bio (parl.gc.ca, ola.org, leg.bc.ca, etc.),
  Wikipedia, or the party page itself are all valid evidence.
- Defeated/retired politicians may have archived sites — that's OK,
  but cap confidence at 0.75.
- Skip social-media profiles (twitter.com, facebook.com, linkedin.com,
  bsky.app, etc.) — those are tracked in a separate system. Only
  return websites here.

Confidence scale:
  0.95-1.00  evidence page directly links the URL and names the person
  0.85-0.94  strong circumstantial match (bio + jurisdiction + party)
  0.60-0.84  party_lander fallback or some ambiguity
  <0.60      do not return (just omit)
"""


@dataclass
class PoliticianContext:
    id: str
    name: str
    party: Optional[str]
    level: str
    province_territory: Optional[str]
    constituency_name: Optional[str]
    openparliament_slug: Optional[str] = None
    ola_slug: Optional[str] = None
    nslegislature_slug: Optional[str] = None


@dataclass
class AgentHit:
    politician_id: str
    kind: str
    url: str
    confidence: float
    evidence_url: Optional[str]
    reasoning: Optional[str]


# ── Data assembly ────────────────────────────────────────────────────


async def _fetch_batch_contexts(
    db: Database,
    *,
    batch_size: int,
    offset: int,
) -> list[PoliticianContext]:
    rows = await db.fetch(
        """
        SELECT politician_id, name, level, province_territory, party,
               constituency_name, openparliament_slug, ola_slug,
               nslegislature_slug
          FROM v_websites_missing
         ORDER BY politician_id
         OFFSET $1 LIMIT $2
        """,
        int(offset), int(batch_size),
    )
    return [
        PoliticianContext(
            id=str(r["politician_id"]),
            name=r["name"] or "",
            party=r["party"],
            level=r["level"],
            province_territory=r["province_territory"],
            constituency_name=r["constituency_name"],
            openparliament_slug=r["openparliament_slug"],
            ola_slug=r["ola_slug"],
            nslegislature_slug=r["nslegislature_slug"],
        )
        for r in rows
    ]


def _ctx_to_brief(ctx: PoliticianContext) -> dict[str, Any]:
    d: dict[str, Any] = {
        "politician_id": ctx.id,
        "name": ctx.name,
        "level": ctx.level,
        "province_territory": ctx.province_territory,
        "party": ctx.party,
    }
    if ctx.constituency_name:
        d["constituency_name"] = ctx.constituency_name
    if ctx.openparliament_slug:
        d["openparliament_slug"] = ctx.openparliament_slug
    if ctx.ola_slug:
        d["ola_slug"] = ctx.ola_slug
    if ctx.nslegislature_slug:
        d["nslegislature_slug"] = ctx.nslegislature_slug
    return d


def _build_user_message(contexts: list[PoliticianContext]) -> str:
    payload = [_ctx_to_brief(c) for c in contexts]
    return (
        "Find the best representative website (personal / campaign / "
        "party_lander) for each politician below. Up to 3 web_searches "
        "per politician.\n\n"
        "```json\n"
        + orjson.dumps(payload, option=orjson.OPT_INDENT_2).decode()
        + "\n```\n\n"
        "Return a single JSON object as specified in the system prompt."
    )


# ── Response parsing ─────────────────────────────────────────────────


_JSON_OBJ_RE = re.compile(r"\{[\s\S]*\}", re.MULTILINE)


def _parse_response(text: str) -> list[AgentHit]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```\s*$", "", text)
    m = _JSON_OBJ_RE.search(text)
    if not m:
        return []
    try:
        obj = orjson.loads(m.group(0))
    except Exception as exc:
        log.warning("agent returned unparseable JSON: %s", exc)
        return []
    if not isinstance(obj, dict):
        return []
    results = obj.get("results") or []
    if not isinstance(results, list):
        return []
    hits: list[AgentHit] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        pid = item.get("politician_id")
        kind = item.get("kind")
        url = item.get("url")
        if not (pid and kind and url):
            continue
        if kind not in ALLOWED_LABELS:
            continue
        conf = item.get("confidence")
        try:
            conf = float(conf)
        except (TypeError, ValueError):
            continue
        conf = max(0.0, min(1.0, conf))
        hits.append(AgentHit(
            politician_id=str(pid),
            kind=kind,
            url=str(url),
            confidence=conf,
            evidence_url=item.get("evidence_url") if isinstance(item.get("evidence_url"), str) else None,
            reasoning=item.get("reasoning") if isinstance(item.get("reasoning"), str) else None,
        ))
    return hits


# ── Agent call ───────────────────────────────────────────────────────


async def _call_agent(
    client: Any,
    *,
    model: str,
    contexts: list[PoliticianContext],
    max_tokens: int,
) -> tuple[list[AgentHit], dict[str, int]]:
    messages = [{"role": "user", "content": _build_user_message(contexts)}]
    # Hard cap: 3 searches per politician × N politicians in this batch.
    # Floor at 3 in case len(contexts)==1 to avoid a degenerate cap.
    budget = max(PER_POLITICIAN_SEARCH_BUDGET,
                 PER_POLITICIAN_SEARCH_BUDGET * len(contexts))
    tools = [{
        "type": "web_search_20250305",
        "name": "web_search",
        "max_uses": budget,
    }]
    try:
        resp = await client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=SYSTEM_PROMPT,
            tools=tools,
            messages=messages,
        )
    except Exception as exc:
        log.error("anthropic call failed: %s", exc)
        return [], {"input_tokens": 0, "output_tokens": 0, "error": 1}

    text_chunks: list[str] = []
    for block in resp.content:
        if getattr(block, "type", None) == "text":
            text_chunks.append(block.text)
    final_text = "\n".join(text_chunks).strip()
    hits = _parse_response(final_text)

    usage = getattr(resp, "usage", None)
    usage_summary = {
        "input_tokens": getattr(usage, "input_tokens", 0) if usage else 0,
        "output_tokens": getattr(usage, "output_tokens", 0) if usage else 0,
        "error": 0,
    }
    if usage is not None:
        stu = getattr(usage, "server_tool_use", None)
        if stu is not None:
            usage_summary["web_searches"] = getattr(stu, "web_search_requests", 0)

    return hits, usage_summary


# ── Insertion ────────────────────────────────────────────────────────


async def _ingest_hits(
    db: Database,
    hits: list[AgentHit],
    *,
    dry_run: bool,
) -> dict[str, int]:
    stats: Counter = Counter()
    for h in hits:
        if h.confidence < AGENT_MIN_WRITE:
            stats["below_min_write"] += 1
            continue
        if dry_run:
            stats["dry_run"] += 1
            continue
        try:
            canon = await upsert_website(
                db, h.politician_id, h.url,
                label=h.kind,
                source="agent_sonnet",
                confidence=h.confidence,
                evidence_url=h.evidence_url,
                notes=h.reasoning,
            )
        except Exception as exc:
            log.warning("agent upsert failed for %s %s: %s",
                        h.politician_id, h.url, exc)
            stats["insert_error"] += 1
            continue
        if canon is None:
            stats["upsert_rejected"] += 1
            continue
        if h.confidence >= AGENT_PROMOTE_THRESHOLD:
            stats["auto_inserted"] += 1
        else:
            stats["flagged_inserted"] += 1
    return dict(stats)


# ── Driver ───────────────────────────────────────────────────────────


async def agent_find_websites(
    db: Database,
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
    max_batches: int = 20,
    model: str = DEFAULT_MODEL,
    dry_run: bool = False,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> None:
    """Run the Tier-3 websites agent loop."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        console.print("[red]ANTHROPIC_API_KEY is not set. Aborting.[/red]")
        return

    try:
        import anthropic  # type: ignore
    except ImportError:
        console.print("[red]The 'anthropic' package is not installed.[/red]")
        return

    batch_size = max(1, min(batch_size, MAX_BATCH_SIZE))
    client = anthropic.AsyncAnthropic(api_key=api_key)

    running_tokens = {"input_tokens": 0, "output_tokens": 0,
                      "web_searches": 0, "error": 0}
    running_ingest: Counter = Counter()
    all_hits: list[AgentHit] = []

    console.print(
        f"[cyan]agent-missing-websites:[/cyan] batch_size={batch_size} "
        f"max_batches={max_batches} model={model} dry_run={dry_run} "
        f"per-politician-search-budget={PER_POLITICIAN_SEARCH_BUDGET}"
    )

    offset = 0
    batch_n = 0
    while batch_n < max_batches:
        contexts = await _fetch_batch_contexts(
            db, batch_size=batch_size, offset=offset,
        )
        if not contexts:
            console.print("[yellow]no more politicians to process — stopping[/yellow]")
            break
        offset += len(contexts)
        batch_n += 1

        console.print(
            f"[cyan]batch {batch_n}/{max_batches}:[/cyan] {len(contexts)} politicians "
            f"(search cap = {PER_POLITICIAN_SEARCH_BUDGET * len(contexts)})"
        )
        hits, usage = await _call_agent(
            client, model=model, contexts=contexts, max_tokens=max_tokens,
        )
        running_tokens["input_tokens"] += usage.get("input_tokens", 0)
        running_tokens["output_tokens"] += usage.get("output_tokens", 0)
        running_tokens["web_searches"] += usage.get("web_searches", 0)
        running_tokens["error"] += usage.get("error", 0)

        all_hits.extend(hits)
        if hits:
            console.print(
                f"  → {len(hits)} hits "
                f"(tokens: in={usage.get('input_tokens', 0)} "
                f"out={usage.get('output_tokens', 0)} "
                f"searches={usage.get('web_searches', 0)})"
            )
        else:
            console.print("  → no hits returned for this batch")

        ingest_stats = await _ingest_hits(db, hits, dry_run=dry_run)
        for k, v in ingest_stats.items():
            running_ingest[k] += v

    _print_summary(all_hits, running_tokens, running_ingest, dry_run=dry_run)


def _print_summary(
    hits: list[AgentHit],
    tokens: dict[str, int],
    ingest: Counter,
    *,
    dry_run: bool,
) -> None:
    console.print()
    console.print(
        f"[green]✓ websites agent run complete[/green] — "
        f"{len(hits)} hits, "
        f"input={tokens.get('input_tokens', 0):,} tokens, "
        f"output={tokens.get('output_tokens', 0):,} tokens, "
        f"web_searches={tokens.get('web_searches', 0)}, "
        f"errors={tokens.get('error', 0)}"
    )

    if ingest:
        tbl = Table(title="Ingestion outcome" + (" (dry-run)" if dry_run else ""))
        tbl.add_column("bucket", style="cyan")
        tbl.add_column("n", justify="right")
        for k, v in ingest.most_common():
            style = "green" if k == "auto_inserted" else "yellow" if k == "flagged_inserted" else None
            tbl.add_row(
                f"[{style}]{k}[/{style}]" if style else k,
                str(v),
            )
        console.print(tbl)

    auto = [h for h in hits if h.confidence >= AGENT_PROMOTE_THRESHOLD]
    flagged = [h for h in hits if AGENT_MIN_WRITE <= h.confidence < AGENT_PROMOTE_THRESHOLD]
    if auto:
        console.print(f"[green]Auto-inserted samples ({len(auto)}):[/green]")
        for h in auto[:15]:
            console.print(
                f"  {h.kind:<13} {h.url}  conf={h.confidence:.2f}  "
                f"ev={(h.evidence_url or '')[:80]}"
            )
    if flagged:
        console.print(f"[yellow]Flagged samples ({len(flagged)}):[/yellow]")
        for h in flagged[:15]:
            console.print(
                f"  {h.kind:<13} {h.url}  conf={h.confidence:.2f}  "
                f"ev={(h.evidence_url or '')[:80]}"
            )
