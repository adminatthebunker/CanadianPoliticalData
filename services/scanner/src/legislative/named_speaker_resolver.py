"""Named-speaker resolver — Tier-2 attribution Pass 4.

Some provincial Hansards leave the chamber parser unable to FK-resolve
named-MLA speeches because the speaker label carries only a surname or
an honorific + surname, and the surname is shared by multiple historical
politicians (or the politician was missing from the roster). Examples:

    Mrs. Driedger
    Mr. McFadyen
    Hon. Erin Selby (Minister of Health)
    Mr. Jack Penner (Emerson)
    MLA David Pankratz (Waverley)

These are NOT presiding-officer turns (Pass 1 / 3 territory). They're
regular MLA speeches the chamber parser captured the surname on but
left ``politician_id`` NULL.

Pass 4: scan ``politician_id IS NULL`` speeches with name-bearing
``speaker_name_raw`` and missing/empty ``speaker_role``, extract the
name, FK-match against ``politicians`` with date-windowed narrowing
when surnames collide. Cross-jurisdictional, idempotent.

Sister modules:
  * ``presiding_officer_resolver`` (Tier 1, Pass 3) — role-only
    presiding turns by SPEAKER_ROSTER lookup.
  * ``inline_presiding_resolver`` (Pass 1+2) — parens-name presiding
    labels with first-name + date-window narrowing.

Pass 4 reuses the candidate-narrowing pipeline from Pass 1 (surname
→ first-initial → exact-first-name) plus the date-window step from
Pass 2, but doesn't gate on a presiding-prefix — any name-bearing
label with NULL/empty ``speaker_role`` is in scope.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field as dc_field
from datetime import date as date_type
from typing import Optional

from ..db import Database

log = logging.getLogger(__name__)


# Match the leading honorific + name pattern. Captures the surname plus
# (optionally) a first name. Handles:
#   "Mr. Driedger"                          → first=None,  last="Driedger"
#   "Hon. Erin Selby (Minister of Health)"  → first="Erin", last="Selby"
#   "Mr. Hugh McFadyen (Leader of the Opposition)" → first="Hugh", last="McFadyen"
#   "MLA David Pankratz (Waverley)"         → first="David", last="Pankratz"
#   "Mr. R. Miller"                          → first="R", last="Miller"  (AB initial)
#   "Mr. Schow moved"                        → first=None,  last="Schow"  (trailing verb)
#   "Ms Sigurdson"                          → first=None,  last="Sigurdson" (AB sometimes drops period)
# Not anchored at $ so trailing text after the name doesn't break matching.
_NAMED_RE = re.compile(
    r"""^
    \s*
    (?:Hon\.?\s+)?                                           # optional Hon. prefix
    (?:Mr\.?|Mrs\.?|Ms\.?|Madam|Mme|Mlle|Dr\.?|MLA|Member)\s+ # honorific (required)
    (?:                                                      # optional first name
       (?P<first>
          [A-ZÀ-Þ](?:[a-zà-öø-ÿA-ZÀ-Þ'\-]+|\.)               # first: full name OR single-letter+period
          (?:\s+[A-Z]\.?)?                                   # optional middle initial
       )
       \s+
    )?
    (?P<last>[A-ZÀ-Þ][a-zà-öø-ÿA-ZÀ-Þ'\-]+(?:\s+[A-ZÀ-Þ][a-zà-öø-ÿA-ZÀ-Þ'\-]+)?)   # surname (allows compound)
    (?:\s+\([^)]+\))?                                        # optional (Riding) / (Portfolio)
    (?:\s+(?:moved|asked|said|presented|introduced).*)?      # AB-style trailing verb tail
    \s*$""",
    re.VERBOSE,
)

# Pre-filter to skip rows that are vocatives, presiding officers, or
# parliamentary staff. These should never make it into the FK pipeline.
_SKIP_RAW_RE = re.compile(
    r"""^\s*
    (?:
        (?:Mr|Madam|Mme|Mlle|Hon)\.?\s+    # honorific
        (?:Deputy\s+)?
        (?:Speaker|Chairperson|Chair(?:man|woman)?|Pr[ée]sident(?:e)?|
           Clerk(?:\s+Assistant)?|Sergeant[\s\-]at[\s\-]Arms)
    |   (?:An|Some)\s+(?:Honourable|Hon\.?)\s+Members?
    |   (?:Madam\s+|Mr\.?\s+|Hon\.?\s+)?Clerk\b
    |   Clerk(?:\s+Assistant)?\b
    |   (?:Madam\s+|Mr\.?\s+)?Deputy\s+Clerk\b
    |   Deputy\s+Sergeant
    |   The\s+(?:Speaker|Chair(?:person|man)?|Deputy\s+Speaker|Acting\s+Speaker|Deputy\s+Chair)
    |   A\s+Voice
    )
    """,
    re.VERBOSE | re.IGNORECASE,
)

# Words a "first name" extraction should never produce (would mean the
# regex misfired on a pseudo-honorific phrase like "Hon Members").
_FIRST_NAME_BLOCKLIST = {"members", "member", "speaker", "chair", "chairperson", "chairman"}

_WS_RE = re.compile(r"\s+")


def _norm(s: Optional[str]) -> str:
    if not s:
        return ""
    text = unicodedata.normalize("NFKD", s)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return _WS_RE.sub(" ", text.lower()).strip()


@dataclass
class _Extracted:
    first: Optional[str]
    last: str


def _extract_name(raw: str) -> Optional[_Extracted]:
    """Parse the speaker_name_raw into (optional first, surname).

    Returns None for vocatives, parliamentary staff, generic placeholders,
    and rows that don't match the honorific+name shape.
    """
    if not raw:
        return None
    if _SKIP_RAW_RE.match(raw):
        return None
    m = _NAMED_RE.match(raw)
    if m is None:
        return None
    last = m.group("last")
    first = m.group("first")
    if not last:
        return None
    if first and first.lower() in _FIRST_NAME_BLOCKLIST:
        first = None
    return _Extracted(first=first, last=last)


@dataclass
class ResolveStats:
    candidates: int = 0
    extracted: int = 0
    fk_hits_full: int = 0     # surname + first-name match, single
    fk_hits_initial: int = 0  # surname + first-initial narrowing
    fk_hits_surname: int = 0  # surname-only single match
    fk_hits_dated: int = 0    # date-windowed narrowing closed ambiguity
    fk_misses: int = 0        # multi-candidate after all narrowings
    speeches_updated: int = 0
    chunks_updated: int = 0
    misses_sample: list[tuple[str, str]] = dc_field(default_factory=list)


async def resolve_named_speakers(
    db: Database, *, province: Optional[str] = None,
    limit: Optional[int] = None,
) -> ResolveStats:
    """Walk speeches with politician_id IS NULL + (NULL or empty)
    speaker_role + name-bearing speaker_name_raw, extract the name,
    FK-match with date-windowed narrowing.
    """
    stats = ResolveStats()

    sql = """
        SELECT s.id::text             AS id,
               s.province_territory   AS prov,
               s.speaker_name_raw     AS raw,
               s.spoken_at::date      AS spoken_date
          FROM speeches s
         WHERE s.level = 'provincial'
           AND s.politician_id IS NULL
           AND (s.speaker_role IS NULL OR s.speaker_role = '')
    """
    params: list = []
    if province:
        sql += " AND s.province_territory = $1"
        params.append(province)
    if limit is not None:
        sql += f" LIMIT {int(limit)}"

    rows = await db.fetch(sql, *params)
    stats.candidates = len(rows)

    # Per-province surname index: { norm(last) → [(politician_id, norm(first))] }
    surname_cache: dict[str, dict[str, list[tuple[str, str]]]] = {}
    # Per-province term cache: [(politician_id, started_at, ended_at)]
    # Only MLA-style offices count for active-on-date checks.
    term_cache: dict[str, list[tuple[str, date_type, Optional[date_type]]]] = {}

    async def _load_surnames(prov: str) -> dict[str, list[tuple[str, str]]]:
        if prov in surname_cache:
            return surname_cache[prov]
        rrows = await db.fetch(
            """
            SELECT id::text AS id, first_name, last_name
              FROM politicians
             WHERE level = 'provincial'
               AND province_territory = $1
               AND last_name IS NOT NULL
            """,
            prov,
        )
        idx: dict[str, list[tuple[str, str]]] = {}
        for r in rrows:
            key = _norm(r["last_name"])
            if not key:
                continue
            idx.setdefault(key, []).append(
                (r["id"], _norm(r["first_name"] or ""))
            )
        surname_cache[prov] = idx
        return idx

    async def _load_terms(prov: str) -> list[tuple[str, date_type, Optional[date_type]]]:
        if prov in term_cache:
            return term_cache[prov]
        # MLA-track offices for date-windowed narrowing. We include
        # Speaker, Deputy Speaker etc. as well — those politicians were
        # also MLAs during their presiding tenure.
        trows = await db.fetch(
            """
            SELECT politician_id::text AS politician_id,
                   started_at::date    AS started_at,
                   ended_at::date      AS ended_at
              FROM politician_terms
             WHERE level = 'provincial'
               AND province_territory = $1
            """,
            prov,
        )
        out = [(r["politician_id"], r["started_at"], r["ended_at"]) for r in trows]
        term_cache[prov] = out
        return out

    def _active_on(terms: list[tuple[str, date_type, Optional[date_type]]],
                   d: Optional[date_type]) -> set[str]:
        if d is None:
            return set()
        return {pid for (pid, started, ended) in terms
                if d >= started and (ended is None or d < ended)}

    # Bucket speech_ids by (politician_id, confidence) for bulk UPDATE.
    by_pol_full: dict[str, list[str]] = {}     # 0.85 — surname + first-name
    by_pol_surname: dict[str, list[str]] = {}  # 0.80 — surname single match
    by_pol_dated: dict[str, list[str]] = {}    # 0.75 — needed date-window narrowing

    for row in rows:
        ext = _extract_name(row["raw"] or "")
        if ext is None:
            continue
        stats.extracted += 1

        prov = row["prov"]
        if not prov:
            continue
        idx = await _load_surnames(prov)
        last_key = _norm(ext.last)
        candidates = idx.get(last_key, [])
        if not candidates:
            stats.fk_misses += 1
            if len(stats.misses_sample) < 10:
                stats.misses_sample.append((prov, row["raw"][:80]))
            continue

        pol_id: Optional[str] = None
        bucket: Optional[dict[str, list[str]]] = None

        if len(candidates) == 1 and ext.first is None:
            # Surname-only, single candidate
            pol_id = candidates[0][0]
            bucket = by_pol_surname
            stats.fk_hits_surname += 1
        elif len(candidates) == 1 and ext.first is not None:
            # Single candidate; first name confirms
            pol_id = candidates[0][0]
            bucket = by_pol_full
            stats.fk_hits_full += 1
        elif ext.first is not None:
            # Multiple surname candidates, narrow by first name
            first_key = _norm(ext.first)
            exact = [c for c in candidates if c[1] == first_key]
            if len(exact) == 1:
                pol_id = exact[0][0]
                bucket = by_pol_full
                stats.fk_hits_full += 1
            else:
                initial = [c for c in candidates if c[1] and c[1].startswith(first_key[:1])]
                if len(initial) == 1:
                    pol_id = initial[0][0]
                    bucket = by_pol_full
                    stats.fk_hits_initial += 1

        # Date-windowed narrowing as final tiebreaker
        if pol_id is None and len(candidates) > 1:
            terms = await _load_terms(prov)
            active = _active_on(terms, row["spoken_date"])
            survivors = [c for c in candidates if c[0] in active]
            if ext.first is not None:
                first_key = _norm(ext.first)
                first_match = [c for c in survivors if c[1] == first_key]
                if len(first_match) == 1:
                    pol_id = first_match[0][0]
                    bucket = by_pol_dated
                    stats.fk_hits_dated += 1
                else:
                    initial_match = [c for c in survivors if c[1] and c[1].startswith(first_key[:1])]
                    if len(initial_match) == 1:
                        pol_id = initial_match[0][0]
                        bucket = by_pol_dated
                        stats.fk_hits_dated += 1
            elif len(survivors) == 1:
                pol_id = survivors[0][0]
                bucket = by_pol_dated
                stats.fk_hits_dated += 1

        if pol_id is None or bucket is None:
            stats.fk_misses += 1
            if len(stats.misses_sample) < 10:
                stats.misses_sample.append((prov, row["raw"][:80]))
            continue

        bucket.setdefault(pol_id, []).append(row["id"])

    BATCH = 5000
    async def _apply(buckets: dict[str, list[str]], confidence: float) -> None:
        for pol_id, speech_ids in buckets.items():
            for i in range(0, len(speech_ids), BATCH):
                chunk = speech_ids[i : i + BATCH]
                await db.execute(
                    """
                    UPDATE speeches
                       SET politician_id = $1::uuid,
                           confidence    = GREATEST(confidence, $3::numeric),
                           updated_at    = now()
                     WHERE id = ANY($2::uuid[])
                       AND politician_id IS NULL
                    """,
                    pol_id, chunk, confidence,
                )
                stats.speeches_updated += len(chunk)
                await db.execute(
                    """
                    UPDATE speech_chunks sc
                       SET politician_id = $1::uuid
                      FROM speeches s
                     WHERE s.id = sc.speech_id
                       AND s.id = ANY($2::uuid[])
                       AND sc.politician_id IS DISTINCT FROM $1::uuid
                    """,
                    pol_id, chunk,
                )
                stats.chunks_updated += 1

    await _apply(by_pol_full, 0.85)
    await _apply(by_pol_surname, 0.80)
    await _apply(by_pol_dated, 0.75)

    log.info(
        "named_speaker_resolver: candidates=%d extracted=%d "
        "fk_hits_full=%d fk_hits_initial=%d fk_hits_surname=%d fk_hits_dated=%d "
        "fk_misses=%d speeches_updated=%d",
        stats.candidates, stats.extracted,
        stats.fk_hits_full, stats.fk_hits_initial, stats.fk_hits_surname,
        stats.fk_hits_dated, stats.fk_misses, stats.speeches_updated,
    )
    return stats
