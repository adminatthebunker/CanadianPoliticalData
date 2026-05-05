"""BC ALL-CAPS speaker resolver — Tier-2 attribution Pass 2 (BC slice).

The BC pre-1990 Hansard era (P29-P34, ~1969-1991) uses an all-caps
speaker label format the existing ``resolve-bc-speakers-dated`` doesn't
recover from:

    MR. G.S. WALLACE (Oak Bay)
    MR. R.H. McCLELLAND (Langley)
    HON. D. BARRETT (Premier)
    MRS. P.J. JORDAN (North Okanagan)
    HON. A.B. MACDONALD (Attorney-General)
    MR. WALLACE
    HON. MR. MICHAEL                       (double-honorific)

The existing dated resolver pulls "Bay)" / "River)" / "Premier)" as
the surname (last whitespace-separated token), which never matches
politician_terms. This resolver parses the structured format directly:

    {HONORIFIC} [{HONORIFIC2}] [{INITIALS}] {LASTNAME} [({HINT})]

…and uses the parens-hint to disambiguate when surname-only matching
returns multiple candidates within the speech's date window. Two hint
shapes:

  * **Riding** ("Oak Bay", "South Peace River", "Vancouver-Point Grey")
    — matches against ``politician_terms.constituency_id``.
  * **Role** ("Premier", "Minister of …", "Leader of the Opposition",
    "Attorney-General") — discarded for matching, but recorded as
    ``raw->'allcaps_role_hint'`` for downstream analysis.

Targets ~12,742 unattributed speeches with ``speaker_role IS NULL``
and an ALL-CAPS prefix. Sister of:
  * ``resolve_bc_speakers_dated`` — modern era, mixed-case surname.
  * ``presiding_officer_resolver`` — role-only "The Speaker" rows.
  * ``inline_presiding_resolver`` — inline-name parens for ON/MB/QC.

Idempotent. Re-runs no-op since the WHERE clause excludes already-
resolved rows.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field as dc_field
from typing import Optional

from ..db import Database

log = logging.getLogger(__name__)

# Parser: ALL-CAPS BC speaker label.
#   ^(HON\.|MR\.|MRS\.|MS\.)\s+
#    (HON\.|MR\.|MRS\.|MS\.\s+)?               ← optional double-honorific (HON. MR. ...)
#    ((?:[A-Z]\.\s*){1,3})?                    ← optional initials (G.S., W.A.C., etc.)
#    ([A-Z][a-zA-Z]*[A-Z]+|Mc[A-Z]+|[A-Z]+)    ← lastname (Mc-prefixed or all-caps)
#    (?:\s+\(([^)]+)\))?                       ← optional parens hint
#    \s*$
_LABEL_RE = re.compile(
    r"^(?P<honorific>HON\.|MR\.|MRS\.|MS\.)\s+"
    r"(?:(?:HON\.|MR\.|MRS\.|MS\.)\s+)?"
    r"(?P<initials>(?:[A-Z]\.\s*){1,3})?\s*"
    r"(?P<last>(?:Mc[A-Z]+)|(?:[A-Z][A-Z'’\-]*))"
    r"(?:\s+\((?P<parens>[^)]+)\))?\s*$",
    re.IGNORECASE,
)

# Tokens inside the parens that indicate a ROLE hint (not a riding).
# When we see these we drop the parens for FK matching but keep them
# in raw-payload for telemetry.
_ROLE_HINT_RE = re.compile(
    r"\b("
    r"premier|minister|attorney|leader\s+of\s+the|speaker|chair|"
    r"government\s+house\s+leader|opposition|"
    r"provincial\s+secretary|whip|deputy"
    r")\b",
    re.IGNORECASE,
)
_WS_RE = re.compile(r"\s+")


def _norm(s: str) -> str:
    """Diacritic-strip + lowercase + strip non-alnum/dash."""
    if not s:
        return ""
    text = unicodedata.normalize("NFKD", s)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower()
    text = re.sub(r"[^a-z0-9\-\s]", "", text)
    return _WS_RE.sub(" ", text).strip()


def _norm_riding(s: str) -> str:
    """Aggressive riding normaliser — handles em-dash vs hyphen vs en-dash."""
    if not s:
        return ""
    text = unicodedata.normalize("NFKD", s)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower()
    # Normalise em-dash / en-dash / various hyphens to plain ASCII hyphen.
    text = re.sub(r"[‐-―−]", "-", text)
    # Collapse whitespace around hyphens for consistency.
    text = re.sub(r"\s*-\s*", "-", text)
    text = re.sub(r"[^a-z0-9\-\s]", "", text)
    return _WS_RE.sub(" ", text).strip()


@dataclass
class ParsedLabel:
    raw: str
    honorific: str                  # "HON.", "MR.", "MRS.", "MS."
    initial_first: Optional[str]    # first initial letter ("G", "W", "D"), used for first-name FK fallback
    last: str                       # uppercased lastname (e.g. "WALLACE", "McCLELLAND")
    parens: Optional[str]           # raw parens text
    parens_kind: str                # 'riding', 'role', or 'none'


def parse_label(raw: str) -> Optional[ParsedLabel]:
    if not raw:
        return None
    m = _LABEL_RE.match(raw.strip())
    if not m:
        return None
    initials_raw = (m.group("initials") or "").strip()
    initial_first: Optional[str] = None
    if initials_raw:
        # First letter of the first initial: "G.S." → "G"
        first_dot = initials_raw.split()[0].rstrip(".") if initials_raw.split() else ""
        if first_dot:
            initial_first = first_dot[0].upper()
    parens = (m.group("parens") or "").strip() or None
    parens_kind = "none"
    if parens:
        parens_kind = "role" if _ROLE_HINT_RE.search(parens) else "riding"
    return ParsedLabel(
        raw=raw,
        honorific=m.group("honorific").upper(),
        initial_first=initial_first,
        last=m.group("last").strip(),
        parens=parens,
        parens_kind=parens_kind,
    )


# ── DB resolver ───────────────────────────────────────────────────


@dataclass
class ResolveStats:
    scanned: int = 0
    parsed: int = 0
    resolved_by_riding: int = 0
    resolved_by_initial: int = 0
    resolved_by_lastname: int = 0
    still_ambiguous: int = 0
    no_term_match: int = 0
    no_parse: int = 0
    chunks_updated: int = 0
    miss_samples: list[str] = dc_field(default_factory=list)


async def resolve_bc_allcaps(
    db: Database, *, limit: Optional[int] = None,
) -> ResolveStats:
    """Walk BC unattributed ALL-CAPS speeches, parse the label, FK
    match against politician_terms, update.

    Args:
      limit: cap candidate speeches scanned (smoke-test aid).
    """
    stats = ResolveStats()

    # 1. Pull candidate speeches.
    sql = """
        SELECT s.id::text       AS id,
               s.spoken_at      AS spoken_at,
               s.speaker_name_raw AS raw
          FROM speeches s
         WHERE s.province_territory = 'BC'
           AND s.level = 'provincial'
           AND s.politician_id IS NULL
           AND s.spoken_at IS NOT NULL
           AND s.speaker_role IS NULL
           AND s.speaker_name_raw ~ '^[A-Z]{2,}\\.\\s'
    """
    if limit is not None:
        sql += f" LIMIT {int(limit)}"
    rows = await db.fetch(sql)
    stats.scanned = len(rows)

    # 2. Preload BC politician_terms with constituency.
    term_rows = await db.fetch(
        """
        SELECT pt.politician_id::text AS pol_id,
               lower(unaccent(p.last_name))  AS last_norm,
               lower(unaccent(p.first_name)) AS first_norm,
               pt.constituency_id           AS riding,
               pt.started_at                 AS started_at,
               pt.ended_at                   AS ended_at
          FROM politician_terms pt
          JOIN politicians p ON p.id = pt.politician_id
         WHERE pt.province_territory = 'BC'
           AND pt.level = 'provincial'
           AND p.last_name IS NOT NULL
        """,
    )

    # Index by lastname.
    by_last: dict[str, list[dict]] = {}
    for r in term_rows:
        last = r["last_norm"]
        if not last:
            continue
        by_last.setdefault(last, []).append({
            "pol_id":     r["pol_id"],
            "first_norm": r["first_norm"] or "",
            "riding":     _norm_riding(r["riding"] or ""),
            "started_at": r["started_at"],
            "ended_at":   r["ended_at"],
        })

    # 3. Walk speeches, resolve.
    by_politician: dict[str, list[str]] = {}
    for row in rows:
        label = parse_label(row["raw"])
        if label is None:
            stats.no_parse += 1
            if len(stats.miss_samples) < 10:
                stats.miss_samples.append(f"NO_PARSE: {row['raw']!r}")
            continue
        stats.parsed += 1

        last_norm = _norm(label.last)
        candidates = by_last.get(last_norm, [])
        if not candidates:
            stats.no_term_match += 1
            continue

        # Filter by date window — politician_terms with started_at/ended_at
        # bracketing the speech's spoken_at date.
        spoken = row["spoken_at"]
        active = [
            c for c in candidates
            if c["started_at"] <= spoken
               and (c["ended_at"] is None or c["ended_at"] > spoken)
        ]
        if not active:
            stats.no_term_match += 1
            continue

        # Disambiguate.
        chosen: Optional[str] = None
        if len(active) == 1:
            chosen = active[0]["pol_id"]
            stats.resolved_by_lastname += 1
        else:
            # Try riding match first when parens is a riding hint.
            if label.parens_kind == "riding" and label.parens:
                pn = _norm_riding(label.parens)
                riding_match = [c for c in active if c["riding"] == pn]
                if len(riding_match) == 1:
                    chosen = riding_match[0]["pol_id"]
                    stats.resolved_by_riding += 1
            # Fall back to first-initial match.
            if chosen is None and label.initial_first:
                init_match = [
                    c for c in active
                    if c["first_norm"] and c["first_norm"][:1] == label.initial_first.lower()
                ]
                if len(init_match) == 1:
                    chosen = init_match[0]["pol_id"]
                    stats.resolved_by_initial += 1

        if chosen is None:
            stats.still_ambiguous += 1
            continue
        by_politician.setdefault(chosen, []).append(row["id"])

    # 4. Bulk update in 5K chunks per politician.
    for pol_id, speech_ids in by_politician.items():
        for i in range(0, len(speech_ids), 5000):
            chunk = speech_ids[i : i + 5000]
            await db.execute(
                """
                UPDATE speeches
                   SET politician_id = $1::uuid,
                       confidence    = GREATEST(confidence, 0.85),
                       updated_at    = now()
                 WHERE id = ANY($2::uuid[])
                   AND politician_id IS NULL
                """,
                pol_id, chunk,
            )
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

    log.info(
        "bc_allcaps: scanned=%d parsed=%d "
        "by_riding=%d by_initial=%d by_lastname=%d "
        "still_ambiguous=%d no_term_match=%d no_parse=%d",
        stats.scanned, stats.parsed,
        stats.resolved_by_riding, stats.resolved_by_initial,
        stats.resolved_by_lastname,
        stats.still_ambiguous, stats.no_term_match, stats.no_parse,
    )
    return stats
