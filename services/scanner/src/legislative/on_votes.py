"""ON votes extractor — Hansard-text regex over already-ingested ON speeches.

ON Hansard publishes vote outcomes as inline statements within Speaker
turns ("Motion agreed to.", "Motion lost.") + ~13 numerical "nays" tally
references corpus-wide. Predominantly consensus-shape.

Pattern coverage in the corpus (probe 2026-04-30):
- 6,396 inline `motion (is) (carried|defeated|adopted|agreed to|lost)` outcomes
- 13 numerical `nays:` tallies (rare division-shape)
- 200 division calls
- 7,408 question-call phrases ("all in favour"/"all opposed")

Largest provincial votes corpus by raw outcome count. Mostly consensus.
Idempotency: `(source_system='votes-on', source_url)`.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field as dc_field
from typing import Optional

import orjson

from ..db import Database

log = logging.getLogger(__name__)

SOURCE_SYSTEM = "votes-on"

_INLINE_OUTCOME_RE = re.compile(
    r'\b(?:Motion|Amendment|Bill|Question)\s+(?:is\s+)?(?P<outcome>'
    r'carried|defeated|adopted|negatived|withdrawn|agreed\s+to|lost|passed)\b',
    re.IGNORECASE,
)
_QUESTION_CALL_RE = re.compile(
    r'\b(?:all (?:those|in) (?:in\s+)?favou?r|all (?:those )?opposed|on division|'
    r'is it the pleasure of the House|division called)\b',
    re.IGNORECASE,
)
_TALLY_RE = re.compile(
    r'(?:Yeas|Ayes)\s*[:.]?\s*(?P<ayes>\d+).*?Nays\s*[:.]?\s*(?P<nays>\d+)',
    re.IGNORECASE | re.DOTALL,
)
_BILL_REF_RE = re.compile(r'\bBill\s+(\d+)\b', re.IGNORECASE)
_RESULT_BY_OUTCOME = {
    "carried": "passed", "adopted": "passed", "passed": "passed", "agreed to": "passed",
    "defeated": "defeated", "negatived": "defeated", "lost": "defeated",
    "withdrawn": "withdrawn",
}


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
    ayes: Optional[int] = None
    nays: Optional[int] = None


def _classify(text: str) -> Optional[_Detected]:
    if not text:
        return None
    tally = _TALLY_RE.search(text)
    if tally:
        ayes = int(tally.group("ayes")); nays = int(tally.group("nays"))
        result = "passed" if ayes > nays else ("defeated" if ayes < nays else "tied")
        return _Detected(vote_type="division", result=result,
                         motion_text=_motion_text(text, tally.start()),
                         ayes=ayes, nays=nays)
    if _QUESTION_CALL_RE.search(text):
        m = _INLINE_OUTCOME_RE.search(text)
        if m:
            outcome = re.sub(r'\s+', ' ', m.group("outcome").lower().strip())
            return _Detected(vote_type="consensus",
                             result=_RESULT_BY_OUTCOME.get(outcome, "passed"),
                             motion_text=_motion_text(text))
    return None


def _motion_text(text: str, end: Optional[int] = None) -> Optional[str]:
    body = text[:end] if end is not None else text
    sentences = re.split(r'(?<=[.!?])\s+', body.strip())
    motion = " ".join(sentences[-3:]).strip() if sentences else body
    return (motion[:500] or None) if motion else None


def _find_bill_id_for(raw: dict, body: str, idx: dict[str, str]) -> Optional[str]:
    if not idx:
        return None
    topic = (raw or {}).get("on_hansard", {}).get("topic") or ""
    for src in (topic, body):
        for m in _BILL_REF_RE.finditer(src):
            if m.group(1) in idx:
                return idx[m.group(1)]
    return None


async def _load_bill_index(db: Database) -> dict[str, str]:
    rows = await db.fetch(
        "SELECT b.id::text AS id, b.bill_number FROM bills b "
        "JOIN legislative_sessions ls ON ls.id=b.session_id "
        "WHERE ls.province_territory='ON' AND ls.level='provincial'"
    )
    out: dict[str, str] = {}
    for r in rows:
        bn = (r["bill_number"] or "").strip()
        mnum = re.search(r"\d+", bn)
        if mnum:
            out[mnum.group(0)] = r["id"]
    return out


async def _upsert_vote(db: Database, *, speech_row: dict, detected: _Detected,
                      bill_id: Optional[str], stats: IngestStats) -> str:
    canonical_url = speech_row["source_url"]
    vote_source_url = f"{canonical_url}#vote-{speech_row['sequence']}"
    raw_json = orjson.dumps({
        "extractor": "on_votes/v1",
        "speech_id": speech_row["id"],
        "speaker_role": speech_row["speaker_role"],
        "marker_signal": detected.vote_type,
    }).decode("utf-8")
    result = await db.fetchrow(
        """
        INSERT INTO votes (session_id, level, province_territory,
                           bill_id, speech_id, vote_type, occurred_at, result,
                           ayes, nays, abstentions, motion_text,
                           source_system, source_url, raw)
        VALUES ($1::uuid, 'provincial', 'ON', $2, $3::uuid, $4, $5, $6,
                $7, $8, NULL, $9, $10, $11, $12::jsonb)
        ON CONFLICT (source_system, source_url) DO UPDATE SET
          bill_id=EXCLUDED.bill_id, vote_type=EXCLUDED.vote_type,
          occurred_at=EXCLUDED.occurred_at, result=EXCLUDED.result,
          ayes=EXCLUDED.ayes, nays=EXCLUDED.nays,
          motion_text=EXCLUDED.motion_text, raw=EXCLUDED.raw, updated_at=now()
        RETURNING (xmax = 0) AS inserted
        """,
        speech_row["session_id"], bill_id, speech_row["id"], detected.vote_type,
        speech_row["spoken_at"], detected.result,
        detected.ayes, detected.nays, detected.motion_text,
        SOURCE_SYSTEM, vote_source_url, raw_json,
    )
    inserted = bool(result and result["inserted"])
    stats.by_type[detected.vote_type] = stats.by_type.get(detected.vote_type, 0) + 1
    if detected.result:
        stats.by_result[detected.result] = stats.by_result.get(detected.result, 0) + 1
    if bill_id:
        stats.bill_linkage_hits += 1
    return "inserted" if inserted else "updated"


async def extract_on_votes(db: Database, *, limit_sittings: Optional[int] = None) -> IngestStats:
    stats = IngestStats()
    bill_index = await _load_bill_index(db)
    log.info("on_votes: loaded %d ON bill references", len(bill_index))
    where_sittings = ""
    if limit_sittings is not None:
        where_sittings = f"""
        AND s.spoken_at::date IN (SELECT spoken_at::date FROM speeches
          WHERE source_system='hansard-on' GROUP BY 1 ORDER BY 1 DESC LIMIT {int(limit_sittings)})
        """
    rows = await db.fetch(f"""
        SELECT s.id::text AS id, s.session_id::text AS session_id,
               s.source_url, s.sequence, s.spoken_at, s.speaker_role, s.text, s.raw
          FROM speeches s
         WHERE s.source_system='hansard-on' AND s.text IS NOT NULL
           AND ((s.text ~* 'motion (is\\s+)?(carried|defeated|adopted|agreed to|lost|negatived|withdrawn)'
                 AND s.text ~* 'all (those|in) in favou?r|all (those )?opposed|on division|division called')
                OR s.text ~* 'Yeas\\s*[:.]?\\s*\\d')
           {where_sittings}
         ORDER BY s.spoken_at, s.sequence
    """)
    for r in rows:
        stats.speeches_scanned += 1
        raw = r["raw"] if isinstance(r["raw"], dict) else (orjson.loads(r["raw"]) if r["raw"] else {})
        detected = _classify(r["text"])
        if not detected:
            stats.votes_skipped_no_outcome += 1
            continue
        bill_id = _find_bill_id_for(raw, r["text"], bill_index)
        result = await _upsert_vote(db,
            speech_row={"id": r["id"], "session_id": r["session_id"],
                        "source_url": r["source_url"], "sequence": r["sequence"],
                        "spoken_at": r["spoken_at"], "speaker_role": r["speaker_role"]},
            detected=detected, bill_id=bill_id, stats=stats)
        if result == "inserted":
            stats.votes_inserted += 1
        else:
            stats.votes_updated += 1
    log.info("on_votes: scanned=%d inserted=%d updated=%d skipped=%d by_type=%s by_result=%s bill_links=%d",
             stats.speeches_scanned, stats.votes_inserted, stats.votes_updated,
             stats.votes_skipped_no_outcome, stats.by_type, stats.by_result, stats.bill_linkage_hits)
    return stats
