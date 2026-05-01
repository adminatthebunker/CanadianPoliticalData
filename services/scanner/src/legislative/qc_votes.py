"""QC votes extractor — French Hansard-text regex over already-ingested QC speeches.

QC's Journal des débats publishes vote outcomes in French with a
distinctive structured-tally convention:

    Pour : 54
    Contre : 0
    Abstentions : 30

Each line on its own paragraph. Plus inline French outcome statements
("La motion est adoptée", "Cette motion est rejetée", "adoptée à
l'unanimité") for consensus/voice votes that lack numerical tallies.

Pattern coverage in the corpus (probe 2026-04-30):
- 4,438 inline `motion (est) (adoptée|rejetée|retirée)` outcomes
- 1,846 numerical `Pour: N` tallies + matching 1,846 `Contre: N` (paired)
- 677 explicit `adoptée à l'unanimité` / `à la majorité` indicators
- 275 `vote nominal` (recorded vote) calls
- 1,082 `vote par appel nominal | vote enregistré` mentions

QC is the **second-richest division-shape corpus** after federal — and
the only French-language one. The schema's `motion_text` field carries
French strings without any code change required.

Per-MNA position lists are NOT in the body text — only aggregate Pour /
Contre / Abstentions counts. So `vote_positions` stays empty for QC,
matching BC and NT consensus behavior.

Idempotency: upsert on `(source_system='votes-qc', source_url)` where
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

SOURCE_SYSTEM = "votes-qc"

# ── Outcome detection ───────────────────────────────────────────────

# Numerical tally — "Pour : 54" + "Contre : 0" + optional "Abstentions : N"
# (the QC convention; colons may be space-separated or tight).
_DIVISION_TALLY_RE = re.compile(
    r'\bPour\s*[: ]?\s*(?P<ayes>\d+)\s*[\r\n]+'
    r'\s*Contre\s*[: ]?\s*(?P<nays>\d+)'
    r'(?:\s*[\r\n]+\s*Abstentions?\s*[: ]?\s*(?P<abst>\d+))?',
    re.IGNORECASE,
)

# Inline French outcome — "(la|cette) motion est adoptée/rejetée/retirée".
# Also covers "adopté(e) à l'unanimité" / "à la majorité" without prefix.
_INLINE_OUTCOME_RE = re.compile(
    r'\b(?:(?:la|cette|le)\s+)?(?:motion|amendement|projet\s+de\s+loi)\s+est\s+'
    r'(?P<outcome>adopt[ée]e?|rejet[ée]e?|retir[ée]e?|battue?)\b'
    r'(?:\s+à\s+(?:l[\'’]unanimit[ée]|la\s+majorit[ée]))?',
    re.IGNORECASE,
)

# Standalone "adoptée à l'unanimité" without prefix — common short form.
_UNANIMOUS_RE = re.compile(
    r'\badopt[ée]e?\s+à\s+l[\'’]unanimit[ée]\b',
    re.IGNORECASE,
)

# Procedural French question-call (mise aux voix, vote nominal demandé, etc.)
_QUESTION_CALL_RE = re.compile(
    r'\b(?:mise aux voix|vote (?:nominal|par appel nominal|enregistré)|'
    r'le vote.*?(?:est|sera) (?:tenu|pris)|'
    r'que les députés en faveur|veuillez vous lever|nous allons procéder au vote)\b',
    re.IGNORECASE | re.DOTALL,
)

# Bill reference: "projet de loi n° 29" or "projet de loi 29".
_BILL_REF_RE = re.compile(
    r'\bprojet\s+de\s+loi\s+(?:n[°ºo]?\s*)?(\d+)\b',
    re.IGNORECASE,
)

_RESULT_BY_OUTCOME = {
    "adopté": "passed",
    "adoptée": "passed",
    "adoptees": "passed",
    "rejeté": "defeated",
    "rejetée": "defeated",
    "battu": "defeated",
    "battue": "defeated",
    "retiré": "withdrawn",
    "retirée": "withdrawn",
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
    ayes: Optional[int]
    nays: Optional[int]
    abstentions: Optional[int]


# ── Detection ───────────────────────────────────────────────────────


def _classify(text: str) -> Optional[_Detected]:
    """QC priority:
      1. Numerical Pour/Contre tally → vote_type='division'
      2. "adoptée à l'unanimité" → vote_type='acclamation'
      3. Inline outcome + question-call → vote_type='consensus'
    """
    if not text:
        return None

    tally = _DIVISION_TALLY_RE.search(text)
    if tally:
        ayes = int(tally.group("ayes"))
        nays = int(tally.group("nays"))
        abst = int(tally.group("abst")) if tally.group("abst") else None
        if ayes > nays:
            result = "passed"
        elif ayes < nays:
            result = "defeated"
        else:
            result = "tied"
        return _Detected(
            vote_type="division", result=result,
            motion_text=_extract_motion_text(text, tally.start()),
            ayes=ayes, nays=nays, abstentions=abst,
        )

    if _UNANIMOUS_RE.search(text):
        return _Detected(
            vote_type="acclamation", result="passed",
            motion_text=_extract_motion_text(text),
            ayes=None, nays=None, abstentions=None,
        )

    if _QUESTION_CALL_RE.search(text):
        m = _INLINE_OUTCOME_RE.search(text)
        if m:
            outcome = _normalise_outcome(m.group("outcome"))
            result = _RESULT_BY_OUTCOME.get(outcome, "passed")
            return _Detected(
                vote_type="consensus", result=result,
                motion_text=_extract_motion_text(text),
                ayes=None, nays=None, abstentions=None,
            )

    return None


def _normalise_outcome(s: str) -> str:
    """Lower + strip combining-accents-tolerant key (e.g. 'Adoptée' → 'adoptée')."""
    return s.lower().strip()


def _extract_motion_text(text: str, end: Optional[int] = None) -> Optional[str]:
    if not text:
        return None
    body = text[:end] if end is not None else text
    body = re.sub(r'Pour\s*[: ]?\s*\d+.*', '', body, flags=re.DOTALL)
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


async def _load_qc_bill_index(db: Database) -> dict[str, str]:
    rows = await db.fetch(
        """
        SELECT b.id::text AS id, b.bill_number
          FROM bills b
          JOIN legislative_sessions ls ON ls.id = b.session_id
         WHERE ls.province_territory = 'QC'
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
        "extractor": "qc_votes/v1",
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
            $1::uuid, 'provincial', 'QC',
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


async def extract_qc_votes(
    db: Database, *, limit_sittings: Optional[int] = None,
) -> IngestStats:
    stats = IngestStats()

    bill_index = await _load_qc_bill_index(db)
    log.info("qc_votes: loaded %d QC bill references", len(bill_index))

    where_sittings = ""
    if limit_sittings is not None:
        where_sittings = f"""
        AND s.spoken_at::date IN (
            SELECT spoken_at::date FROM speeches
             WHERE source_system = 'hansard-qc'
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
         WHERE s.source_system = 'hansard-qc'
           AND s.text IS NOT NULL
           AND (
             s.text ~* 'pour\\s*[:\\s]\\s*\\d.*[\r\n]+\\s*contre\\s*[:\\s]\\s*\\d'
             OR s.text ~* 'adopt[ée]e?\\s+à\\s+l.unanimit'
             OR (s.text ~* 'motion est (adopt|rejet|retir|battu)'
                 AND s.text ~* 'mise aux voix|vote (nominal|par appel|enregistré)|veuillez vous lever')
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
        "qc_votes: scanned=%d inserted=%d updated=%d skipped=%d "
        "by_type=%s by_result=%s bill_links=%d",
        stats.speeches_scanned, stats.votes_inserted, stats.votes_updated,
        stats.votes_skipped_no_outcome,
        stats.by_type, stats.by_result, stats.bill_linkage_hits,
    )
    return stats
