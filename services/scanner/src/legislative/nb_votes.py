"""NB votes extractor — Hansard-text regex over already-ingested NB speeches.

Pattern coverage (probe 2026-04-30): 23 inline motion outcomes,
167 division calls, 0 numerical tallies. Sparse but bilingual.

Uses source_system='legnb-hansard' (NB convention differs from
hansard-{prov} elsewhere). Idempotency: `(source_system='votes-nb', source_url)`.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field as dc_field
from typing import Optional

import orjson

from ..db import Database

log = logging.getLogger(__name__)

SOURCE_SYSTEM = "votes-nb"

# English + French outcome patterns (NB is bilingual).
_INLINE_OUTCOME_RE = re.compile(
    r'\b(?:Motion|Amendment|Bill|Question|Motion|Amendement|Projet)\s+(?:is\s+|est\s+)?'
    r'(?P<outcome>'
    r'carried|defeated|adopted|negatived|withdrawn|agreed\s+to|lost|passed|'
    r'adopt[ée]e?|rejet[ée]e?|retir[ée]e?)\b',
    re.IGNORECASE,
)
_QUESTION_CALL_RE = re.compile(
    r'\b(?:all (?:those|in) (?:in\s+)?favou?r|all (?:those )?opposed|on division|'
    r'mise aux voix|que les députés|veuillez vous lever|division called|'
    r'vote nominal)\b',
    re.IGNORECASE,
)
_BILL_REF_RE = re.compile(
    r'\bBill\s+(\d+)\b|\bprojet\s+de\s+loi\s+(?:n[°ºo]?\s*)?(\d+)\b',
    re.IGNORECASE,
)
_RESULT_BY_OUTCOME = {
    "carried": "passed", "adopted": "passed", "passed": "passed", "agreed to": "passed",
    "adopté": "passed", "adoptée": "passed",
    "defeated": "defeated", "negatived": "defeated", "lost": "defeated",
    "rejeté": "defeated", "rejetée": "defeated",
    "withdrawn": "withdrawn",
    "retiré": "withdrawn", "retirée": "withdrawn",
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


def _classify(text: str) -> Optional[_Detected]:
    if not text or not _QUESTION_CALL_RE.search(text):
        return None
    m = _INLINE_OUTCOME_RE.search(text)
    if not m:
        return None
    outcome = re.sub(r'\s+', ' ', m.group("outcome").lower().strip())
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    motion = " ".join(sentences[-3:])[:500] if sentences else None
    return _Detected(vote_type="consensus",
                     result=_RESULT_BY_OUTCOME.get(outcome, "passed"),
                     motion_text=motion)


def _find_bill_id_for(raw: dict, body: str, idx: dict[str, str]) -> Optional[str]:
    if not idx:
        return None
    topic = (raw or {}).get("nb_hansard", {}).get("topic") or ""
    for src in (topic, body):
        for m in _BILL_REF_RE.finditer(src):
            num = m.group(1) or m.group(2)
            if num and num in idx:
                return idx[num]
    return None


async def _load_bill_index(db: Database) -> dict[str, str]:
    rows = await db.fetch(
        "SELECT b.id::text AS id, b.bill_number FROM bills b "
        "JOIN legislative_sessions ls ON ls.id=b.session_id "
        "WHERE ls.province_territory='NB' AND ls.level='provincial'"
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
        "extractor": "nb_votes/v1",
        "speech_id": speech_row["id"],
        "speaker_role": speech_row["speaker_role"],
    }).decode("utf-8")
    result = await db.fetchrow(
        """
        INSERT INTO votes (session_id, level, province_territory,
                           bill_id, speech_id, vote_type, occurred_at, result,
                           ayes, nays, abstentions, motion_text,
                           source_system, source_url, raw)
        VALUES ($1::uuid, 'provincial', 'NB', $2, $3::uuid, $4, $5, $6,
                NULL, NULL, NULL, $7, $8, $9, $10::jsonb)
        ON CONFLICT (source_system, source_url) DO UPDATE SET
          bill_id=EXCLUDED.bill_id, vote_type=EXCLUDED.vote_type,
          occurred_at=EXCLUDED.occurred_at, result=EXCLUDED.result,
          motion_text=EXCLUDED.motion_text, raw=EXCLUDED.raw, updated_at=now()
        RETURNING (xmax = 0) AS inserted
        """,
        speech_row["session_id"], bill_id, speech_row["id"], detected.vote_type,
        speech_row["spoken_at"], detected.result, detected.motion_text,
        SOURCE_SYSTEM, vote_source_url, raw_json,
    )
    inserted = bool(result and result["inserted"])
    stats.by_type[detected.vote_type] = stats.by_type.get(detected.vote_type, 0) + 1
    if detected.result:
        stats.by_result[detected.result] = stats.by_result.get(detected.result, 0) + 1
    if bill_id:
        stats.bill_linkage_hits += 1
    return "inserted" if inserted else "updated"


async def extract_nb_votes(db: Database, *, limit_sittings: Optional[int] = None) -> IngestStats:
    stats = IngestStats()
    bill_index = await _load_bill_index(db)
    log.info("nb_votes: loaded %d NB bill references", len(bill_index))
    where_sittings = ""
    if limit_sittings is not None:
        where_sittings = f"""
        AND s.spoken_at::date IN (SELECT spoken_at::date FROM speeches
          WHERE source_system='legnb-hansard' GROUP BY 1 ORDER BY 1 DESC LIMIT {int(limit_sittings)})
        """
    rows = await db.fetch(f"""
        SELECT s.id::text AS id, s.session_id::text AS session_id,
               s.source_url, s.sequence, s.spoken_at, s.speaker_role, s.text, s.raw
          FROM speeches s
         WHERE s.source_system='legnb-hansard' AND s.text IS NOT NULL
           AND s.text ~* 'motion (is\\s+)?(carried|defeated|adopted|agreed to|lost|adopt[ée]e?|rejet[ée]e?)'
           AND s.text ~* 'all (those|in) in favou?r|all (those )?opposed|mise aux voix|on division|division called'
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
    log.info("nb_votes: scanned=%d inserted=%d updated=%d skipped=%d by_type=%s by_result=%s bill_links=%d",
             stats.speeches_scanned, stats.votes_inserted, stats.votes_updated,
             stats.votes_skipped_no_outcome, stats.by_type, stats.by_result, stats.bill_linkage_hits)
    return stats
