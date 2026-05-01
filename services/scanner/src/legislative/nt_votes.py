"""NT votes extractor — derives `votes` rows from already-ingested NT Hansard
speeches.

NT runs consensus government — no party whip, no per-member roll calls. Vote
outcomes appear in Hansard as Speaker statements followed by a Hansard
convention annotation:

    Question has been called. All those in favour? All those opposed?
    Motion carried.

    ---Carried

The body of a Speaker-attributed speech contains both the procedural
question-and-call ("Question has been called...") and the canonical
annotation (`---Carried`, `---Defeated`, `---Carried unanimously`). The
annotation is the load-bearing signal: regex `^---(Carried|Defeated|...)`
on multiline text, with PostgreSQL POSIX regex semantics in mind.

Per the migration 0018 docstring, NT votes will populate as `vote_type='consensus'`
with NULL `ayes`/`nays`/`abstentions` (NT doesn't publish numerical tallies)
and an empty `vote_positions` table. This is the schema's anticipated shape.

Bill linkage: opportunistic. If the speech's `raw->'nt_hansard'->>'topic'`
contains `Bill N` or the body text mentions `Bill N`, look for a matching
`bills` row in the same legislative_session. Most NT votes are procedural
motions or committee reports without a bill linkage; `bill_id` stays NULL
in those cases.

Speech FK: `votes.speech_id` points at the Speaker's announcement row — the
canonical anchor for "this is when the vote was decided".

Idempotency: upsert keyed on `(source_system, source_url)`. The source URL
is composed as `{canonical_sitting_url}#vote-{sequence}` where sequence is
the speech sequence within the sitting that recorded the vote.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field as dc_field
from typing import Optional

import orjson

from ..db import Database

log = logging.getLogger(__name__)

SOURCE_SYSTEM = "votes-nt"

# ── Outcome detection ───────────────────────────────────────────────

# The Hansard convention markers are the strongest vote-outcome signal.
# These appear as their own paragraph after the Speaker's announcement —
# the body_text we stored joins paragraphs with "\n\n".
_OUTCOME_MARKER_RE = re.compile(
    r'(?m)^---\s*(?P<marker>Carried\s+unanimously|Carried|Defeated|Withdrawn|Negatived|Tied)\b',
    re.IGNORECASE,
)

# Inline phrasing inside the Speaker's body text — fallback when the
# marker is absent. Less common but observed in older transcripts.
_INLINE_OUTCOME_RE = re.compile(
    r'\b(?:motion (?:is\s+)?|the\s+amendment\s+is\s+)'
    r'(?P<outcome>carried|defeated|adopted|negatived|withdrawn|tied)\b',
    re.IGNORECASE,
)

# Procedural question-call (presence makes this row a vote-outcome row,
# not just commentary that mentions "carried" in passing).
_QUESTION_CALL_RE = re.compile(
    r'\b(?:question (?:has been|is) called|all (?:those|in) (?:in\s+)?favou?r|'
    r'all (?:those )?opposed|recorded vote)\b',
    re.IGNORECASE,
)

# Bill reference inside speech text or topic field — `Bill 29` / `Bill 6`.
_BILL_REF_RE = re.compile(r'\bBill\s+(\d+)\b', re.IGNORECASE)

# Numerical tally — kept for completeness, not expected to fire on NT.
_TALLY_RE = re.compile(
    r'(?:Yeas|Ayes)\s*[:.]?\s*(?P<ayes>\d+).*?'
    r'Nays\s*[:.]?\s*(?P<nays>\d+)'
    r'(?:.*?Abstentions?\s*[:.]?\s*(?P<abst>\d+))?',
    re.IGNORECASE | re.DOTALL,
)

_RESULT_BY_MARKER = {
    "carried": "passed",
    "carried unanimously": "passed",
    "defeated": "defeated",
    "negatived": "defeated",
    "withdrawn": "withdrawn",
    "tied": "tied",
    # Inline-fallback values.
    "adopted": "passed",
}


# ── Models ──────────────────────────────────────────────────────────


@dataclass
class IngestStats:
    speeches_scanned: int = 0
    votes_inserted: int = 0
    votes_updated: int = 0
    votes_skipped_no_outcome: int = 0
    by_type: dict[str, int] = dc_field(default_factory=dict)
    by_result: dict[str, int] = dc_field(default_factory=dict)
    bill_linkage_hits: int = 0


# ── Detection ───────────────────────────────────────────────────────


@dataclass
class _Detected:
    vote_type: str            # 'consensus' | 'division' | 'voice' | 'acclamation'
    result: Optional[str]     # 'passed' | 'defeated' | 'tied' | 'withdrawn' | None
    motion_text: Optional[str]
    ayes: Optional[int]
    nays: Optional[int]
    abstentions: Optional[int]


def _classify(text: str) -> Optional[_Detected]:
    """Return _Detected if this speech text records a vote outcome, else None.

    Outcome detection priority:
      1. `---Carried unanimously` annotation → acclamation, passed
      2. `---Carried` / `---Defeated` / etc. annotation → consensus, mapped result
      3. Inline `motion is carried` / `motion defeated` text + question-call
         context → consensus
      4. Numerical `Yeas: N Nays: M` tally → division, mapped result, with counts
    """
    if not text:
        return None

    # Numerical tally first — strongest signal for `division`.
    m = _TALLY_RE.search(text)
    if m:
        ayes = int(m.group("ayes"))
        nays = int(m.group("nays"))
        abst = int(m.group("abst")) if m.group("abst") else None
        if ayes > nays:
            result = "passed"
        elif ayes < nays:
            result = "defeated"
        else:
            result = "tied"
        motion_text = _extract_motion_text(text)
        return _Detected(
            vote_type="division", result=result,
            motion_text=motion_text,
            ayes=ayes, nays=nays, abstentions=abst,
        )

    # Hansard annotation (the load-bearing NT pattern).
    m = _OUTCOME_MARKER_RE.search(text)
    if m:
        marker = m.group("marker").lower().strip()
        # "Carried unanimously" → acclamation; everything else → consensus
        if "unanimously" in marker:
            vt = "acclamation"
        else:
            vt = "consensus"
        result = _RESULT_BY_MARKER.get(marker, "passed")
        return _Detected(
            vote_type=vt, result=result,
            motion_text=_extract_motion_text(text),
            ayes=None, nays=None, abstentions=None,
        )

    # Inline-text fallback — only when paired with a procedural question call.
    if _QUESTION_CALL_RE.search(text):
        m = _INLINE_OUTCOME_RE.search(text)
        if m:
            outcome = m.group("outcome").lower()
            result = _RESULT_BY_MARKER.get(outcome, "passed")
            return _Detected(
                vote_type="consensus", result=result,
                motion_text=_extract_motion_text(text),
                ayes=None, nays=None, abstentions=None,
            )

    return None


def _extract_motion_text(text: str) -> Optional[str]:
    """Best-effort: pick a representative motion sentence.

    Speaker bodies usually run "Question has been called. All those in
    favour? All those opposed? Motion carried." — the actual motion
    being voted on was moved by a Member in a preceding speech, which
    we don't easily reach from here. Use the Speaker text itself as
    motion_text; the Hansard topic (in raw->'nt_hansard'->>'topic')
    carries the higher-level subject. Truncate to 500 chars for sanity.
    """
    if not text:
        return None
    cleaned = re.sub(r"---\s*\w+", "", text).strip()
    # Strip the trailing procedural noise after a sentence boundary.
    sentences = re.split(r"(?<=[.!?])\s+", cleaned)
    if not sentences:
        return cleaned[:500] if cleaned else None
    # Pick up to first 3 sentences for context.
    motion = " ".join(sentences[:3]).strip()
    return motion[:500] if motion else None


def _find_bill_id_for(
    raw: dict, body_text: str, bill_index: dict[str, str],
) -> Optional[str]:
    """Match `Bill N` mentions in the topic or body text against the
    pre-loaded bill index for this jurisdiction.
    """
    if not bill_index:
        return None
    candidates: list[str] = []
    topic = (raw or {}).get("nt_hansard", {}).get("topic") or ""
    for source in (topic, body_text):
        for m in _BILL_REF_RE.finditer(source):
            num = m.group(1)
            if num in bill_index:
                candidates.append(bill_index[num])
    if not candidates:
        return None
    # Return the first match (most likely the topic-level reference).
    return candidates[0]


# ── DB helpers ──────────────────────────────────────────────────────


async def _load_nt_bill_index(db: Database) -> dict[str, str]:
    """{ bill_number_str → bill_id::text } for NT bills, current session."""
    rows = await db.fetch(
        """
        SELECT b.id::text AS id, b.bill_number
          FROM bills b
          JOIN legislative_sessions ls ON ls.id = b.session_id
         WHERE ls.province_territory = 'NT'
           AND ls.level = 'provincial'
        """
    )
    out: dict[str, str] = {}
    for r in rows:
        bn = (r["bill_number"] or "").strip()
        if bn:
            # Strip non-numeric prefix ("Bill 29" → "29")
            mnum = re.search(r"\d+", bn)
            if mnum:
                out[mnum.group(0)] = r["id"]
    return out


async def _upsert_vote(
    db: Database, *,
    speech_row: dict, detected: _Detected, bill_id: Optional[str],
    stats: IngestStats,
) -> str:
    """Insert or update one vote row. Returns 'inserted' | 'updated'."""
    canonical_url = speech_row["source_url"]
    sequence = speech_row["sequence"]
    vote_source_url = f"{canonical_url}#vote-{sequence}"

    raw_payload = {
        "extractor": "nt_votes/v1",
        "speech_id": speech_row["id"],
        "speaker_role": speech_row["speaker_role"],
        "marker_signal": detected.vote_type,
    }
    raw_json = orjson.dumps(raw_payload).decode("utf-8")

    result = await db.fetchrow(
        """
        INSERT INTO votes (
            session_id, level, province_territory,
            bill_id, speech_id,
            vote_type, occurred_at, result,
            ayes, nays, abstentions, motion_text,
            source_system, source_url, raw
        ) VALUES (
            $1::uuid, 'provincial', 'NT',
            $2, $3::uuid,
            $4, $5, $6,
            $7, $8, $9, $10,
            $11, $12, $13::jsonb
        )
        ON CONFLICT (source_system, source_url)
        DO UPDATE SET
            bill_id = EXCLUDED.bill_id,
            vote_type = EXCLUDED.vote_type,
            occurred_at = EXCLUDED.occurred_at,
            result = EXCLUDED.result,
            ayes = EXCLUDED.ayes,
            nays = EXCLUDED.nays,
            abstentions = EXCLUDED.abstentions,
            motion_text = EXCLUDED.motion_text,
            raw = EXCLUDED.raw,
            updated_at = now()
        RETURNING (xmax = 0) AS inserted
        """,
        speech_row["session_id"],
        bill_id,
        speech_row["id"],
        detected.vote_type,
        speech_row["spoken_at"],
        detected.result,
        detected.ayes, detected.nays, detected.abstentions,
        detected.motion_text,
        SOURCE_SYSTEM,
        vote_source_url,
        raw_json,
    )
    inserted = bool(result and result["inserted"])
    stats.by_type[detected.vote_type] = stats.by_type.get(detected.vote_type, 0) + 1
    if detected.result:
        stats.by_result[detected.result] = stats.by_result.get(detected.result, 0) + 1
    if bill_id:
        stats.bill_linkage_hits += 1
    return "inserted" if inserted else "updated"


# ── Public entry point ──────────────────────────────────────────────


async def extract_nt_votes(
    db: Database,
    *,
    limit_sittings: Optional[int] = None,
) -> IngestStats:
    """Scan NT Hansard speeches for vote outcomes and upsert `votes` rows.

    `limit_sittings` caps to N most-recent sittings (smoke-test aid). Each
    sitting may yield 0..N votes — most procedural sittings yield zero;
    motion-heavy sittings (e.g., end-of-session days) may yield 5–10.
    """
    stats = IngestStats()

    bill_index = await _load_nt_bill_index(db)
    log.info("nt_votes: loaded %d NT bill references", len(bill_index))

    # Restrict to Speaker-attributed rows when possible — those carry the
    # canonical announcement. Fall back to any row if the marker appears
    # in non-Speaker text (rare; older transcripts).
    where_sittings = ""
    if limit_sittings is not None:
        where_sittings = f"""
        AND s.spoken_at::date IN (
            SELECT spoken_at::date FROM speeches
             WHERE source_system = 'hansard-nt'
             GROUP BY 1
             ORDER BY 1 DESC
             LIMIT {int(limit_sittings)}
        )
        """

    rows = await db.fetch(
        f"""
        SELECT s.id::text AS id,
               s.session_id::text AS session_id,
               s.source_url, s.sequence, s.spoken_at,
               s.speaker_role, s.text, s.raw
          FROM speeches s
         WHERE s.source_system = 'hansard-nt'
           AND s.text IS NOT NULL
           AND (
             s.text ~ '(?m)^---'
             OR (s.text ~* 'motion (is\\s+)?(carried|defeated|adopted|negatived|withdrawn)'
                 AND s.text ~* 'question (has been|is) called|all (those|in) in favou?r|recorded vote')
             OR s.text ~* 'Yeas\\s*[:.]?\\s*\\d'
           )
         ORDER BY s.spoken_at, s.sequence
        """
    )

    for r in rows:
        stats.speeches_scanned += 1
        # raw column comes back as dict in asyncpg; jsonb handler.
        raw = r["raw"] if isinstance(r["raw"], dict) else (orjson.loads(r["raw"]) if r["raw"] else {})
        detected = _classify(r["text"])
        if not detected:
            stats.votes_skipped_no_outcome += 1
            continue
        bill_id = _find_bill_id_for(raw, r["text"], bill_index)
        result = await _upsert_vote(
            db,
            speech_row={
                "id": r["id"],
                "session_id": r["session_id"],
                "source_url": r["source_url"],
                "sequence": r["sequence"],
                "spoken_at": r["spoken_at"],
                "speaker_role": r["speaker_role"],
            },
            detected=detected,
            bill_id=bill_id,
            stats=stats,
        )
        if result == "inserted":
            stats.votes_inserted += 1
        else:
            stats.votes_updated += 1

    log.info(
        "nt_votes: scanned=%d inserted=%d updated=%d skipped=%d "
        "by_type=%s by_result=%s bill_links=%d",
        stats.speeches_scanned, stats.votes_inserted, stats.votes_updated,
        stats.votes_skipped_no_outcome,
        stats.by_type, stats.by_result, stats.bill_linkage_hits,
    )
    return stats
