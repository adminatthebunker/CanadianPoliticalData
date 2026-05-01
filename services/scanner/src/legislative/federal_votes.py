"""Federal votes extractor — openparliament.ca structured-JSON pipeline.

Where NT votes (`nt_votes.py`) parse Hansard-text annotations to derive
consensus-government vote outcomes, federal votes consume two structured
JSON endpoints from openparliament.ca:

    Vote list:    GET /votes/?session={S}&format=json&limit=500
                  → paginated list of summary objects with
                    {bill_url, session, number, date, description,
                     result, yea_total, nay_total, paired_total, url}

    Per-vote ballots: GET /votes/ballots/?vote={vote_url}&format=json&limit=500
                  → paginated per-MP records with
                    {vote_url, politician_url, politician_membership_url, ballot}

The list endpoint already carries every field we need for the `votes`
table — there's no need for a second per-vote detail fetch unless we
later want `context_statement` (debate URL) for speech_id linkage.

This is the cleanest votes-data path of any jurisdiction: politician
attribution is by exact-string FK match against
`politicians.openparliament_slug` (the slug embedded in `politician_url`),
no name fuzz, no date-windowed disambiguation. Bill linkage is by
`bill_url` substring against bills' raw URL.

Schema mapping:
- `votes.vote_type = 'division'` — every openparliament.ca vote is a
  recorded division. Voice/acclamation/consensus shapes don't appear.
- `votes.result` — "Passed" → "passed", "Failed" → "defeated",
  "Tied" → "tied" (case-folded).
- `vote_positions.position` — "Yes" → "yea", "No" → "nay",
  "Paired" → "paired", anything else → "absent" (defensive).
- `votes.bill_id` — populated when `bill_url` matches a bills row;
  NULL otherwise (procedural motions, supply days).
- `votes.speech_id` — NULL for v1. A future post-pass can match
  `context_statement` (debate URL) to the federal speech announcing
  the result.

Idempotency: votes upsert on (source_system='votes-federal', source_url);
vote_positions upsert on (vote_id, politician_name_raw). Re-runs UPDATE in
place; politician resolution can lift on subsequent passes if the
roster fills in.
"""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field as dc_field
from datetime import datetime, time, timezone
from typing import Optional

import httpx
import orjson

from ..db import Database

log = logging.getLogger(__name__)

API_BASE = "https://api.openparliament.ca"
SOURCE_SYSTEM = "votes-federal"

REQUEST_TIMEOUT = 30
HEADERS = {
    "User-Agent": "CanadianPoliticalDataBot/1.0 (+https://canadianpoliticaldata.ca; admin@thebunkerops.ca)",
    "Accept": "application/json",
    "API-Version": "v1",
}

# OpenParliament ballot enum → our schema enum.
_BALLOT_TO_POSITION = {
    "Yes": "yea",
    "No": "nay",
    "Paired": "paired",
    "Didn't vote": "absent",
    "Absent": "absent",
}

# OpenParliament result string → our schema result.
_RESULT_MAP = {
    "Passed": "passed",
    "Failed": "defeated",
    "Tied": "tied",
    "Withdrawn": "withdrawn",
}


# ── Models ──────────────────────────────────────────────────────────


@dataclass
class IngestStats:
    sessions_seen: int = 0
    votes_seen: int = 0
    votes_inserted: int = 0
    votes_updated: int = 0
    positions_inserted: int = 0
    positions_updated: int = 0
    bill_links: int = 0
    politician_links: int = 0
    politicians_unresolved: int = 0
    api_calls: int = 0
    failures: list[str] = dc_field(default_factory=list)


# ── HTTP helpers ────────────────────────────────────────────────────


async def _get_json(client: httpx.AsyncClient, path: str) -> Optional[dict]:
    """GET an openparliament.ca path → JSON dict, or None on failure."""
    url = f"{API_BASE}{path}" if path.startswith("/") else path
    try:
        r = await client.get(url, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        log.warning("federal_votes: GET %s failed: %s", url, exc)
        return None


async def _paginate(
    client: httpx.AsyncClient, path: str, *, page_limit: int = 500,
    delay: float = 0.5, stats: Optional[IngestStats] = None,
) -> list[dict]:
    """Walk a paginated openparliament.ca endpoint, returning all objects."""
    out: list[dict] = []
    sep = "&" if "?" in path else "?"
    next_path: Optional[str] = f"{path}{sep}format=json&limit={page_limit}"
    while next_path:
        if stats is not None:
            stats.api_calls += 1
        data = await _get_json(client, next_path)
        if not data:
            break
        out.extend(data.get("objects", []))
        next_url = data.get("pagination", {}).get("next_url")
        if not next_url:
            break
        # next_url is path-relative; pass through to _get_json which
        # accepts both absolute and path-relative.
        next_path = next_url
        await asyncio.sleep(delay)
    return out


# ── DB helpers ──────────────────────────────────────────────────────


async def _load_federal_session_index(db: Database) -> dict[str, str]:
    """{ '44-1' → legislative_sessions.id } for federal sessions.

    openparliament.ca's `session` field uses the format
    "{parliament}-{session}" (e.g. "44-1") which we map to our
    `parliament_number` + `session_number` columns.
    """
    rows = await db.fetch(
        """
        SELECT id::text AS id, parliament_number, session_number
          FROM legislative_sessions
         WHERE level = 'federal'
        """
    )
    return {f"{r['parliament_number']}-{r['session_number']}": r["id"] for r in rows}


async def _ensure_federal_session(
    db: Database, session_str: str,
) -> Optional[str]:
    """Ensure a federal session row exists; return its UUID."""
    m = re.match(r"^(\d+)-(\d+)$", session_str)
    if not m:
        return None
    parl, sess = int(m.group(1)), int(m.group(2))
    row = await db.fetchrow(
        """
        INSERT INTO legislative_sessions
            (level, province_territory, parliament_number, session_number,
             name, source_system)
        VALUES ('federal', NULL, $1, $2, $3, 'openparliament')
        ON CONFLICT (level, province_territory, parliament_number, session_number)
        DO UPDATE SET updated_at = now()
        RETURNING id::text AS id
        """,
        parl, sess, f"{parl}th Parliament, {sess}{_ord_suffix(sess)} Session",
    )
    return row["id"]


def _ord_suffix(n: int) -> str:
    if 10 < n % 100 < 20:
        return "th"
    return ["th", "st", "nd", "rd", "th", "th", "th", "th", "th", "th"][n % 10]


async def _load_federal_bill_index(db: Database) -> dict[str, str]:
    """{ '/bills/44-1/C-9/' → bills.id } for federal bills.

    The URL is the substring openparliament.ca returns in vote.bill_url;
    our `bills.raw->>'url'` holds exactly the same path-relative string.
    """
    rows = await db.fetch(
        """
        SELECT id::text AS id, raw->>'url' AS bill_url
          FROM bills
         WHERE level = 'federal'
           AND raw->>'url' IS NOT NULL
        """
    )
    return {r["bill_url"]: r["id"] for r in rows if r["bill_url"]}


async def _load_federal_slug_lookup(db: Database) -> dict[str, str]:
    """{ openparliament_slug → politicians.id }."""
    rows = await db.fetch(
        """
        SELECT id::text AS id, openparliament_slug
          FROM politicians
         WHERE openparliament_slug IS NOT NULL
        """
    )
    return {r["openparliament_slug"]: r["id"] for r in rows}


def _slug_from_politician_url(url: Optional[str]) -> Optional[str]:
    """`/politicians/ziad-aboultaif/` → `ziad-aboultaif`."""
    if not url:
        return None
    m = re.match(r"^/politicians/([a-z0-9-]+)/?", url)
    return m.group(1) if m else None


# ── Upsert ──────────────────────────────────────────────────────────


async def _upsert_vote(
    db: Database, *,
    session_id: str,
    vote_obj: dict,
    bill_id: Optional[str],
    stats: IngestStats,
) -> tuple[str, str]:
    """Upsert a votes row. Returns (vote_id, 'inserted' | 'updated')."""
    vote_url_path = vote_obj["url"]                # "/votes/44-1/206/"
    canonical_url = f"{API_BASE}{vote_url_path}"

    result_raw = (vote_obj.get("result") or "").strip()
    result = _RESULT_MAP.get(result_raw, result_raw.lower() or None)

    description = vote_obj.get("description") or {}
    motion_text = (description.get("en") or "").strip() or None

    # spoken_at floor — noon UTC of the vote date; ordering within
    # day uses vote.number implicitly.
    occurred_at = None
    if vote_obj.get("date"):
        try:
            d = datetime.fromisoformat(vote_obj["date"]).date()
            occurred_at = datetime.combine(d, time(12, 0), tzinfo=timezone.utc)
        except ValueError:
            pass

    raw_payload = {
        "openparliament_vote": {
            "url": vote_url_path,
            "session": vote_obj.get("session"),
            "number": vote_obj.get("number"),
            "result_raw": result_raw,
            "yea_total": vote_obj.get("yea_total"),
            "nay_total": vote_obj.get("nay_total"),
            "paired_total": vote_obj.get("paired_total"),
            "bill_url": vote_obj.get("bill_url"),
            "description_fr": description.get("fr"),
        }
    }
    raw_json = orjson.dumps(raw_payload).decode("utf-8")

    row = await db.fetchrow(
        """
        INSERT INTO votes (
            session_id, level, province_territory,
            bill_id, speech_id,
            vote_type, occurred_at, result,
            ayes, nays, abstentions, motion_text,
            source_system, source_url, raw
        ) VALUES (
            $1::uuid, 'federal', NULL,
            $2, NULL,
            'division', $3, $4,
            $5, $6, $7, $8,
            $9, $10, $11::jsonb
        )
        ON CONFLICT (source_system, source_url)
        DO UPDATE SET
            bill_id     = EXCLUDED.bill_id,
            occurred_at = EXCLUDED.occurred_at,
            result      = EXCLUDED.result,
            ayes        = EXCLUDED.ayes,
            nays        = EXCLUDED.nays,
            abstentions = EXCLUDED.abstentions,
            motion_text = EXCLUDED.motion_text,
            raw         = EXCLUDED.raw,
            updated_at  = now()
        RETURNING id::text AS id, (xmax = 0) AS inserted
        """,
        session_id,
        bill_id,
        occurred_at,
        result,
        vote_obj.get("yea_total"),
        vote_obj.get("nay_total"),
        vote_obj.get("paired_total"),
        motion_text,
        SOURCE_SYSTEM,
        canonical_url,
        raw_json,
    )
    if row["inserted"]:
        stats.votes_inserted += 1
    else:
        stats.votes_updated += 1
    if bill_id:
        stats.bill_links += 1
    return row["id"], "inserted" if row["inserted"] else "updated"


async def _upsert_vote_positions(
    db: Database, *,
    vote_id: str,
    ballots: list[dict],
    slug_lookup: dict[str, str],
    stats: IngestStats,
) -> None:
    """Upsert per-MP vote positions for one vote."""
    for b in ballots:
        pol_url = b.get("politician_url") or ""
        slug = _slug_from_politician_url(pol_url)
        ballot_raw = b.get("ballot") or ""
        position = _BALLOT_TO_POSITION.get(ballot_raw)
        if position is None:
            stats.failures.append(
                f"unknown ballot value {ballot_raw!r} on vote {vote_id}"
            )
            continue
        politician_id = slug_lookup.get(slug) if slug else None
        if politician_id:
            stats.politician_links += 1
        else:
            stats.politicians_unresolved += 1

        # politician_name_raw is the slug — openparliament.ca doesn't
        # ship a display name on the ballot record; the slug uniquely
        # identifies the MP and the UNIQUE constraint needs a stable
        # string. The display name is recoverable via politicians table
        # join when politician_id is set.
        name_raw = slug or pol_url

        row = await db.fetchrow(
            """
            INSERT INTO vote_positions (
                vote_id, politician_id, politician_name_raw,
                party_at_time, constituency_at_time, position
            ) VALUES (
                $1::uuid, $2, $3, NULL, NULL, $4
            )
            ON CONFLICT (vote_id, politician_name_raw)
            DO UPDATE SET
                politician_id = EXCLUDED.politician_id,
                position = EXCLUDED.position
            RETURNING (xmax = 0) AS inserted
            """,
            vote_id, politician_id, name_raw, position,
        )
        if row["inserted"]:
            stats.positions_inserted += 1
        else:
            stats.positions_updated += 1


# ── Public entry point ──────────────────────────────────────────────


async def extract_federal_votes(
    db: Database,
    *,
    session: Optional[str] = None,
    limit_votes: Optional[int] = None,
    delay: float = 0.5,
) -> IngestStats:
    """Extract federal votes + per-MP positions from openparliament.ca.

    `session` like "44-1"; default = current sitting session. `limit_votes`
    caps the number of votes processed (newest-first; smoke-test aid).
    """
    stats = IngestStats()

    bill_index = await _load_federal_bill_index(db)
    slug_lookup = await _load_federal_slug_lookup(db)
    log.info(
        "federal_votes: loaded %d federal bills, %d openparliament slugs",
        len(bill_index), len(slug_lookup),
    )

    # Resolve target session.
    if not session:
        # Default: current sitting from federal legislative_sessions.
        cur = await db.fetchrow(
            """
            SELECT parliament_number, session_number
              FROM legislative_sessions
             WHERE level = 'federal'
             ORDER BY parliament_number DESC, session_number DESC
             LIMIT 1
            """
        )
        if not cur:
            stats.failures.append("no federal legislative_sessions row found")
            return stats
        session = f"{cur['parliament_number']}-{cur['session_number']}"

    session_id = await _ensure_federal_session(db, session)
    if not session_id:
        stats.failures.append(f"could not resolve session {session!r}")
        return stats
    stats.sessions_seen = 1

    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True) as client:
        # Pass A — paginate the vote list for this session.
        votes_path = f"/votes/?session={session}"
        all_votes = await _paginate(
            client, votes_path, page_limit=500, delay=delay, stats=stats,
        )
        log.info("federal_votes: discovered %d votes for session %s",
                 len(all_votes), session)
        stats.votes_seen = len(all_votes)

        if limit_votes is not None:
            all_votes = all_votes[: int(limit_votes)]

        # Pass B — per-vote upsert + ballot fetch.
        for v in all_votes:
            bill_id = bill_index.get(v.get("bill_url")) if v.get("bill_url") else None
            vote_id, _ = await _upsert_vote(
                db, session_id=session_id,
                vote_obj=v, bill_id=bill_id, stats=stats,
            )
            ballots_path = f"/votes/ballots/?vote={v['url']}"
            ballots = await _paginate(
                client, ballots_path, page_limit=500, delay=delay, stats=stats,
            )
            await _upsert_vote_positions(
                db, vote_id=vote_id, ballots=ballots,
                slug_lookup=slug_lookup, stats=stats,
            )
            await asyncio.sleep(delay)

    log.info(
        "federal_votes: votes seen=%d inserted=%d updated=%d "
        "positions inserted=%d updated=%d "
        "bill_links=%d pol_links=%d pol_unresolved=%d "
        "api_calls=%d failures=%d",
        stats.votes_seen, stats.votes_inserted, stats.votes_updated,
        stats.positions_inserted, stats.positions_updated,
        stats.bill_links, stats.politician_links, stats.politicians_unresolved,
        stats.api_calls, len(stats.failures),
    )
    return stats


# ── Re-link pass (no API calls) ─────────────────────────────────────


@dataclass
class RelinkStats:
    candidates: int = 0           # federal votes with bill_url in raw
    already_linked: int = 0       # bill_id was already populated
    newly_linked: int = 0         # bill_id flipped NULL → uuid this run
    unchanged: int = 0            # bill_url has no matching bills row
    bill_index_size: int = 0      # how many federal bills available for matching


async def relink_federal_votes(db: Database) -> RelinkStats:
    """Re-derive `votes.bill_id` for federal votes against the current bills table.

    Pure-SQL UPDATE pass — no openparliament.ca API calls. Each vote's
    `raw->'openparliament_vote'->>'bill_url'` is matched against
    `bills.raw->>'url'` (the same key the live extractor uses to build
    its in-memory `bill_index`). Run this whenever federal bills are
    added (e.g. after `ingest-federal-bills --all-sessions`) to lift
    the linkage rate without re-fetching ballots.

    Idempotent: votes that already have the correct bill_id are left
    alone (the UPDATE sets `bill_id` only where it differs).
    """
    stats = RelinkStats()

    stats.bill_index_size = await db.fetchval(
        """
        SELECT count(*) FROM bills
         WHERE level = 'federal' AND raw->>'url' IS NOT NULL
        """
    )

    counts = await db.fetchrow(
        """
        SELECT
          count(*) FILTER (WHERE raw->'openparliament_vote'->>'bill_url' IS NOT NULL)
            AS candidates,
          count(*) FILTER (WHERE bill_id IS NOT NULL)
            AS already_linked
        FROM votes
        WHERE level = 'federal'
        """
    )
    stats.candidates = counts["candidates"] or 0
    stats.already_linked = counts["already_linked"] or 0

    # Match votes to bills via the raw payload's bill_url.
    result = await db.fetchrow(
        """
        WITH matches AS (
            SELECT v.id AS vote_id, b.id AS new_bill_id
              FROM votes v
              JOIN bills b
                ON b.level = 'federal'
               AND b.raw->>'url' = v.raw->'openparliament_vote'->>'bill_url'
             WHERE v.level = 'federal'
               AND v.raw->'openparliament_vote'->>'bill_url' IS NOT NULL
               AND v.bill_id IS DISTINCT FROM b.id
        ),
        applied AS (
            UPDATE votes v
               SET bill_id = m.new_bill_id,
                   updated_at = now()
              FROM matches m
             WHERE v.id = m.vote_id
            RETURNING 1
        )
        SELECT count(*) AS updated FROM applied
        """
    )
    stats.newly_linked = result["updated"] or 0

    # Anything left that has bill_url but still no bill_id → no
    # matching bill in our table (pre-37-1 corpus floor or a renamed
    # / withdrawn bill openparliament still references).
    stats.unchanged = await db.fetchval(
        """
        SELECT count(*) FROM votes
         WHERE level = 'federal'
           AND bill_id IS NULL
           AND raw->'openparliament_vote'->>'bill_url' IS NOT NULL
        """
    )

    log.info(
        "relink_federal_votes: bills available=%d, candidates=%d, "
        "already_linked=%d, newly_linked=%d, no_match=%d",
        stats.bill_index_size, stats.candidates,
        stats.already_linked, stats.newly_linked, stats.unchanged,
    )
    return stats
