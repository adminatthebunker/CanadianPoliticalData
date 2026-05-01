"""AB votes extractor — Hansard-text regex over already-ingested AB speeches.

AB Hansard records vote outcomes with a distinctive Hansard-editor-style
square-bracket annotation embedded **inside the body text** of a speech:

    Mr. Speaker, I move that we adjourn to 1:30 p.m. on May 5.
    [Motion carried; the Assembly adjourned at 4:09 p.m. to Monday, May 5,
    at 1:30 p.m.]

Different from BC's "{action} on the following division: YEAS-N NAYS-M"
post-statement block. AB embeds the outcome inside the moving-MLA's same
speech rather than as a separate Speaker-attributed turn.

Pattern coverage in the corpus (probe 2026-04-30):
- 743 inline `Motion (is) (carried|defeated|...)` outcomes
- 0 numerical YEAS-N / NAYS-M tallies (AB doesn't publish per-division counts)
- 246 division calls
- 439 question-call phrases
- 849 "hon. members ... aye" voice-vote markers

AB votes are predominantly **consensus-shape** — Speaker calls verbal
ayes/nays, Hansard records the outcome inside square brackets, no
numerical tally, no per-MLA list. Same shape NT uses, but with a
different annotation convention.

Idempotency: upsert on `(source_system='votes-ab', source_url)` where
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

SOURCE_SYSTEM = "votes-ab"

# ── Outcome detection ───────────────────────────────────────────────

# AB's signature: "[Motion carried; ...]" or "[Motion defeated; ...]"
# embedded mid-speech. Captures the outcome word.
_BRACKET_OUTCOME_RE = re.compile(
    r'\[\s*(?:The\s+)?(?:Motion|Amendment|Bill|Question)\s+'
    r'(?:is\s+)?(?P<outcome>'
    r'carried|defeated|adopted|negatived|withdrawn|agreed\s+to|lost|passed)'
    r'\b[^\]]*\]',
    re.IGNORECASE,
)

# Inline-text fallback (no brackets) — older transcripts may use plain prose.
_INLINE_OUTCOME_RE = re.compile(
    r'\b(?:Motion|Amendment|Bill|Question)\s+(?:is\s+)?(?P<outcome>'
    r'carried|defeated|adopted|negatived|withdrawn|agreed\s+to|lost|passed)\b',
    re.IGNORECASE,
)

# Procedural question-call (presence makes inline-outcome a real vote).
_QUESTION_CALL_RE = re.compile(
    r'\b(?:question (?:has been|is) called|all (?:those|in) (?:in\s+)?favou?r|'
    r'all (?:those )?opposed|on division|hon\.?\s+members.*?(?:aye|yes|nay|no))\b',
    re.IGNORECASE | re.DOTALL,
)

_BILL_REF_RE = re.compile(r'\bBill\s+(\d+)\b', re.IGNORECASE)

_RESULT_BY_OUTCOME = {
    "carried": "passed",
    "adopted": "passed",
    "passed": "passed",
    "agreed to": "passed",
    "agreed": "passed",
    "defeated": "defeated",
    "negatived": "defeated",
    "lost": "defeated",
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
    vote_type: str
    result: Optional[str]
    motion_text: Optional[str]


# ── Detection ───────────────────────────────────────────────────────


def _classify(text: str) -> Optional[_Detected]:
    """AB's load-bearing signal is the [Motion carried; ...] bracket.

    Priority:
      1. Bracket-annotation outcome → vote_type='consensus'
      2. Inline outcome + question-call → vote_type='consensus' (older eras)
    """
    if not text:
        return None

    m = _BRACKET_OUTCOME_RE.search(text)
    if m:
        outcome = re.sub(r'\s+', ' ', m.group("outcome").lower().strip())
        result = _RESULT_BY_OUTCOME.get(outcome, "passed")
        return _Detected(
            vote_type="consensus", result=result,
            motion_text=_extract_motion_text(text, m.start()),
        )

    if _QUESTION_CALL_RE.search(text):
        m = _INLINE_OUTCOME_RE.search(text)
        if m:
            outcome = re.sub(r'\s+', ' ', m.group("outcome").lower().strip())
            result = _RESULT_BY_OUTCOME.get(outcome, "passed")
            return _Detected(
                vote_type="consensus", result=result,
                motion_text=_extract_motion_text(text),
            )

    return None


def _extract_motion_text(text: str, end: Optional[int] = None) -> Optional[str]:
    if not text:
        return None
    body = text[:end] if end is not None else text
    body = re.sub(r'\[\s*(?:The\s+)?(?:Motion|Amendment).*?\]', '', body, flags=re.DOTALL)
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
    for source in (body_text,):
        for m in _BILL_REF_RE.finditer(source):
            num = m.group(1)
            if num in bill_index:
                return bill_index[num]
    return None


# ── DB helpers ──────────────────────────────────────────────────────


async def _load_ab_bill_index(db: Database) -> dict[str, str]:
    rows = await db.fetch(
        """
        SELECT b.id::text AS id, b.bill_number
          FROM bills b
          JOIN legislative_sessions ls ON ls.id = b.session_id
         WHERE ls.province_territory = 'AB'
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
        "extractor": "ab_votes/v1",
        "speech_id": speech_row["id"],
        "speaker_role": speech_row["speaker_role"],
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
            $1::uuid, 'provincial', 'AB',
            $2, $3::uuid,
            $4, $5, $6,
            NULL, NULL, NULL, $7,
            $8, $9, $10::jsonb
        )
        ON CONFLICT (source_system, source_url)
        DO UPDATE SET
            bill_id = EXCLUDED.bill_id,
            vote_type = EXCLUDED.vote_type,
            occurred_at = EXCLUDED.occurred_at,
            result = EXCLUDED.result,
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


async def extract_ab_votes(
    db: Database, *, limit_sittings: Optional[int] = None,
) -> IngestStats:
    stats = IngestStats()

    bill_index = await _load_ab_bill_index(db)
    log.info("ab_votes: loaded %d AB bill references", len(bill_index))

    where_sittings = ""
    if limit_sittings is not None:
        where_sittings = f"""
        AND s.spoken_at::date IN (
            SELECT spoken_at::date FROM speeches
             WHERE source_system = 'assembly.ab.ca'
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
         WHERE s.source_system = 'assembly.ab.ca'
           AND s.text IS NOT NULL
           AND (
             s.text ~* '\\[\\s*(?:the\\s+)?(?:motion|amendment|bill|question)\\s+(?:is\\s+)?(?:carried|defeated|adopted|negatived|withdrawn|agreed|lost|passed)'
             OR (s.text ~* 'motion (is\\s+)?(carried|defeated|adopted|agreed to|lost)'
                 AND s.text ~* 'question (has been|is) called|all (those|in) in favou?r')
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
        "ab_votes: scanned=%d inserted=%d updated=%d skipped=%d "
        "by_type=%s by_result=%s bill_links=%d",
        stats.speeches_scanned, stats.votes_inserted, stats.votes_updated,
        stats.votes_skipped_no_outcome,
        stats.by_type, stats.by_result, stats.bill_linkage_hits,
    )
    return stats
