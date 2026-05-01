"""BC votes extractor — Hansard-text regex over already-ingested BC speeches.

BC Hansard records vote outcomes with a distinctive Westminster-style
formatting convention: the action statement followed by a colon, then
`YEAS-N` and `NAYS-M` on separate lines.

Examples observed in the corpus:

    By leave of the House, Bill No. 9 read a third time and passed on
    the following division:

    YEAS-40

    NAYS-10

    --

    Amendment negatived on the following division:

    YEAS-10

    NAYS-41

    --

    Mr. Chairman's ruling sustained on the following division:

    YEAS-29

    NAYS-16

Plus inline "Motion approved" / "Motion negatived" statements without a
numerical tally — those map to `vote_type='consensus'` (BC version of
NT's same shape).

Per-MLA position lists are **not present** in BC Hansard — only aggregate
counts. So `vote_positions` stays empty for BC, same as NT consensus
votes. The schema's docstring explicitly anticipates this shape.

Pattern coverage in the corpus (probe 2026-04-30):
- 47 numerical YEAS-N / NAYS-M tally pairs (division-shape)
- 555 inline "motion {carried/defeated/approved}" outcomes
- 420 division calls
- ~600 expected total votes after dedup

Idempotency: upsert on `(source_system='votes-bc', source_url)` where
source_url is `{canonical_sitting_url}#vote-{sequence}`.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field as dc_field
from typing import Optional

import orjson

from ..db import Database

log = logging.getLogger(__name__)

SOURCE_SYSTEM = "votes-bc"

# ── Outcome detection ───────────────────────────────────────────────

# Numerical division — "YEAS-30" + "NAYS-19" on separate paragraphs
# (the BC convention), or with colon variants. Captures both numbers.
_DIVISION_TALLY_RE = re.compile(
    r'\bYEAS\s*[-:]\s*(?P<ayes>\d+)\s*[\r\n]+'
    r'(?:\s*NAYS\s*[-:]\s*(?P<nays>\d+))',
    re.IGNORECASE,
)

# Action verb that triggers a division — "{X} on the following division:".
_DIVISION_HEADER_RE = re.compile(
    r'(?P<action>(?:Bill\s+No\.\s*\d+\s+(?:read\s+a\s+third\s+time\s+and\s+)?passed|'
    r'Motion\s+approved|Motion\s+negatived|Motion\s+defeated|'
    r'Amendment\s+approved|Amendment\s+negatived|Amendment\s+defeated|'
    r'Section\s+\d+(?:\(\d+\))?\s+approved|Section\s+\d+(?:\(\d+\))?\s+negatived|'
    r'Title\s+approved|'
    r'Mr\.\s+Chairman\'s\s+ruling\s+sustained|'
    r'Ruling\s+of\s+the\s+(?:Speaker|Chair)\s+sustained))'
    r'\s+on\s+the\s+following\s+division\s*:',
    re.IGNORECASE,
)

# Inline motion-outcome (consensus-shape, no numerical tally).
_INLINE_OUTCOME_RE = re.compile(
    r'\b(?:Motion|Amendment|Bill)\s+(?:is\s+)?(?P<outcome>'
    r'approved|carried|adopted|passed|'
    r'defeated|negatived|withdrawn|rejected)\b',
    re.IGNORECASE,
)

# Procedural question-call (presence makes inline-outcome a real vote
# rather than narrative mention).
_QUESTION_CALL_RE = re.compile(
    r'\b(?:question (?:has been|is) called|all (?:those|in) (?:in\s+)?favou?r|'
    r'all (?:those )?opposed|on division)\b',
    re.IGNORECASE,
)

# Bill reference for opportunistic linkage.
_BILL_REF_RE = re.compile(r'\bBill\s+(?:No\.\s*)?(\d+)\b', re.IGNORECASE)

# Action → result mapping.
_RESULT_BY_ACTION = {
    "approved": "passed",
    "carried": "passed",
    "adopted": "passed",
    "passed": "passed",
    "sustained": "passed",
    "defeated": "defeated",
    "negatived": "defeated",
    "rejected": "defeated",
    "withdrawn": "withdrawn",
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


@dataclass
class _Detected:
    vote_type: str           # 'division' | 'consensus'
    result: Optional[str]
    motion_text: Optional[str]
    ayes: Optional[int]
    nays: Optional[int]


# ── Detection ───────────────────────────────────────────────────────


def _classify(text: str) -> Optional[_Detected]:
    """Return _Detected if this BC speech text records a vote outcome.

    Priority:
      1. Numerical division (YEAS-N / NAYS-M) → vote_type='division'
      2. Inline motion outcome + question-call context → vote_type='consensus'
    """
    if not text:
        return None

    # Numerical division.
    tally = _DIVISION_TALLY_RE.search(text)
    if tally:
        ayes = int(tally.group("ayes"))
        nays = int(tally.group("nays"))
        # Find the action verb just before the YEAS line.
        header = _DIVISION_HEADER_RE.search(text[: tally.start()])
        action_word = "approved"
        if header:
            action_text = header.group("action").lower()
            for word in ("approved", "negatived", "defeated", "passed",
                         "sustained", "carried", "adopted"):
                if word in action_text:
                    action_word = word
                    break
        result = _RESULT_BY_ACTION.get(action_word, "passed" if ayes > nays else "defeated")
        # Override with arithmetic if action ambiguous.
        if ayes > nays and result not in ("passed",):
            result = "passed"
        elif ayes < nays:
            result = "defeated"
        elif ayes == nays:
            result = "tied"
        motion_text = _extract_motion_text(text, tally.start())
        return _Detected(
            vote_type="division", result=result,
            motion_text=motion_text,
            ayes=ayes, nays=nays,
        )

    # Inline outcome + question-call.
    if _QUESTION_CALL_RE.search(text):
        m = _INLINE_OUTCOME_RE.search(text)
        if m:
            outcome = m.group("outcome").lower()
            result = _RESULT_BY_ACTION.get(outcome, "passed")
            return _Detected(
                vote_type="consensus", result=result,
                motion_text=_extract_motion_text(text),
                ayes=None, nays=None,
            )

    return None


def _extract_motion_text(text: str, end: Optional[int] = None) -> Optional[str]:
    """Pick a representative motion sentence from before the outcome marker."""
    if not text:
        return None
    body = text[:end] if end is not None else text
    # Strip the YEAS/NAYS block + Hansard footer noise.
    body = re.sub(r'YEAS\s*[-:]\s*\d+.*', '', body, flags=re.DOTALL)
    body = re.sub(r'\[\s*Return to.*$', '', body, flags=re.DOTALL)
    sentences = re.split(r'(?<=[.!?])\s+', body.strip())
    if not sentences:
        return body[:500] if body else None
    motion = " ".join(sentences[-3:]).strip()
    return motion[:500] if motion else None


def _find_bill_id_for(
    raw: dict, body_text: str, bill_index: dict[str, str],
) -> Optional[str]:
    if not bill_index:
        return None
    candidates: list[str] = []
    topic = (raw or {}).get("bc_hansard", {}).get("subject") or ""
    for source in (topic, body_text):
        for m in _BILL_REF_RE.finditer(source):
            num = m.group(1)
            if num in bill_index:
                candidates.append(bill_index[num])
    return candidates[0] if candidates else None


# ── DB helpers ──────────────────────────────────────────────────────


async def _load_bc_bill_index(db: Database) -> dict[str, str]:
    """{ bill_number_str → bill_id::text } for BC bills (current session)."""
    rows = await db.fetch(
        """
        SELECT b.id::text AS id, b.bill_number
          FROM bills b
          JOIN legislative_sessions ls ON ls.id = b.session_id
         WHERE ls.province_territory = 'BC'
           AND ls.level = 'provincial'
        """
    )
    out: dict[str, str] = {}
    for r in rows:
        bn = (r["bill_number"] or "").strip()
        if not bn:
            continue
        mnum = re.search(r"\d+", bn)
        if mnum:
            out[mnum.group(0)] = r["id"]
    return out


async def _upsert_vote(
    db: Database, *, speech_row: dict, detected: _Detected,
    bill_id: Optional[str], stats: IngestStats,
) -> str:
    canonical_url = speech_row["source_url"]
    sequence = speech_row["sequence"]
    vote_source_url = f"{canonical_url}#vote-{sequence}"

    raw_payload = {
        "extractor": "bc_votes/v1",
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
            $1::uuid, 'provincial', 'BC',
            $2, $3::uuid,
            $4, $5, $6,
            $7, $8, NULL, $9,
            $10, $11, $12::jsonb
        )
        ON CONFLICT (source_system, source_url)
        DO UPDATE SET
            bill_id = EXCLUDED.bill_id,
            vote_type = EXCLUDED.vote_type,
            occurred_at = EXCLUDED.occurred_at,
            result = EXCLUDED.result,
            ayes = EXCLUDED.ayes,
            nays = EXCLUDED.nays,
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
        detected.ayes, detected.nays,
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


async def extract_bc_votes(
    db: Database, *, limit_sittings: Optional[int] = None,
) -> IngestStats:
    """Scan BC Hansard speeches for vote outcomes and upsert `votes` rows."""
    stats = IngestStats()

    bill_index = await _load_bc_bill_index(db)
    log.info("bc_votes: loaded %d BC bill references", len(bill_index))

    where_sittings = ""
    if limit_sittings is not None:
        where_sittings = f"""
        AND s.spoken_at::date IN (
            SELECT spoken_at::date FROM speeches
             WHERE source_system = 'hansard-bc'
             GROUP BY 1 ORDER BY 1 DESC LIMIT {int(limit_sittings)}
        )
        """

    rows = await db.fetch(
        f"""
        SELECT s.id::text AS id,
               s.session_id::text AS session_id,
               s.source_url, s.sequence, s.spoken_at,
               s.speaker_role, s.text, s.raw
          FROM speeches s
         WHERE s.source_system = 'hansard-bc'
           AND s.text IS NOT NULL
           AND (
             s.text ~ 'YEAS\\s*[-:]\\s*\\d'
             OR (s.text ~* 'Motion (is\\s+)?(approved|carried|defeated|negatived|withdrawn|adopted|rejected)'
                 AND s.text ~* 'question (has been|is) called|all (those|in) in favou?r|on division')
           )
           {where_sittings}
         ORDER BY s.spoken_at, s.sequence
        """
    )

    for r in rows:
        stats.speeches_scanned += 1
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
        "bc_votes: scanned=%d inserted=%d updated=%d skipped=%d "
        "by_type=%s by_result=%s bill_links=%d",
        stats.speeches_scanned, stats.votes_inserted, stats.votes_updated,
        stats.votes_skipped_no_outcome,
        stats.by_type, stats.by_result, stats.bill_linkage_hits,
    )
    return stats
