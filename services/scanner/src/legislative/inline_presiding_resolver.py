"""Inline-name presiding-officer resolver — Tier-2 attribution Pass 1.

Some provincial Hansards (notably ON and MB) print presiding-officer
turns with the chair-holder's name embedded in the raw speaker label:

    The Deputy Speaker (Mr. Bas Balkissoon)
    The Deputy Speaker (Ms. Soo Wong)
    The Chair (Mr. Gilles E. Morin)
    Mr. Deputy Speaker (Doyle Piwniuk)

The chamber's primary parser usually catches these, but a long tail
slips through unattributed when:
- The Deputy Speaker / Chair role doesn't trigger the parser's
  Speaker-only fallback path (e.g., ON parser handles "The Speaker"
  inline-name but not "The Deputy Speaker (Mr. X)").
- The inline name has a typo / variant spelling that fails exact FK.
- The MLA roster missed the historical member when the parser ran.

Pass 1 of the cross-jurisdictional Tier-2 work: scan every
politician_id=NULL speech whose raw text contains a parenthesised
honorific+name, extract the name, FK-match against `politicians`
within the same province, and update.

Idempotent — running again is a no-op (the WHERE clause excludes
rows we've already resolved).

Sister module: ``presiding_officer_resolver.py`` (Tier-1, role-only
"The Speaker" turns resolved via SPEAKER_ROSTER + date-windowed
terms). The two resolvers can run in either order; they target
disjoint row sets.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field as dc_field
from datetime import date as date_type
from typing import Optional

from ..db import Database
from .presiding_officer_resolver import DEPUTY_SOURCE_TAG, SOURCE_TAG

log = logging.getLogger(__name__)

# Match `(Honorific Name)` inside the speaker_name_raw text. The
# honorific list covers AB / ON / MB / QC Hansard conventions —
# English (Hon., Mr., Mrs., Ms., Dr., Madam) plus French (M., Mme,
# Mlle, M. for monsieur — note the trailing period is required for
# "M.", otherwise it'd match every capital-M word).
_PARENS_HONORIFIC_NAME_RE = re.compile(
    r"\((?P<honorific>Hon\.?|Mr\.?|Mrs\.?|Ms\.?|Dr\.?|Madam|Mme|Mlle|M\.)\s+"
    r"(?P<name>[^)]+?)\s*\)",
    re.IGNORECASE,
)
# Match `(Firstname Lastname)` bare-name parens — multi-word, all words
# starting with a capital letter. Used for MB/some-ON shapes like
# `The Acting Speaker (Dennis Smook)` where the parens carries the
# name without an honorific. Multi-word requirement excludes
# single-word constituency names like `(Oak Bay)` or role titles
# like `(Premier)`. Diacritics allowed.
_PARENS_BARE_NAME_RE = re.compile(
    r"\((?P<name>[A-ZÀ-Ý][a-zà-öø-ÿ'\-]+"
    r"(?:\s+[A-ZÀ-Ý][a-zà-öø-ÿ'\-]+){1,3})\)",
)
# Outer prefix classifier — speech qualifies for bare-name parens
# extraction only when the prefix is a known presiding-officer label.
# (Without this gate, `M. Paradis (Lévis)` would mis-attribute Paradis
# to whoever has lastname "Lévis".)
_PRESIDING_PREFIX_RE = re.compile(
    r"^(?:"
    r"(?:The\s+)?"
    r"(?:Madam\s+|Mr\.?\s+|Mme\s+|Mlle\s+|M\.\s+|Hon\.?\s+)?"
    r"(?:Acting\s+|Deputy\s+|Assistant\s+Deputy\s+|Vice[- ])?\s*"
    r"(?:Speaker|Chair(?:person|man)?|Pr[ée]sident(?:e)?|Clerk(?:\s+Assistant)?)"
    r")\b",
    re.IGNORECASE,
)
_WS_RE = re.compile(r"\s+")


def _norm(s: str) -> str:
    """Diacritic-strip + lowercase + collapse whitespace, for FK matching."""
    if not s:
        return ""
    text = unicodedata.normalize("NFKD", s)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return _WS_RE.sub(" ", text.lower()).strip()


@dataclass
class _Extracted:
    first: Optional[str]
    last: str
    honorific: Optional[str]


def _split_name(raw: str) -> Optional[_Extracted]:
    """Return (first, last) parsed from the parens-name body.

    Examples:
      "Bas Balkissoon"          → first="Bas",  last="Balkissoon"
      "Gilles E. Morin"         → first="Gilles", last="Morin" (drop middle initial)
      "Effie J. Triantafilopoulos" → first="Effie", last="Triantafilopoulos"
      "Altemeyer"               → first=None, last="Altemeyer" (surname-only)
      "Doyle Piwniuk"           → first="Doyle", last="Piwniuk"
    """
    text = _WS_RE.sub(" ", raw).strip().rstrip(".")
    if not text:
        return None
    # Drop trailing initial (single uppercase + period) tokens.
    tokens = text.split()
    cleaned = [t for t in tokens if not (len(t) <= 2 and t.endswith("."))]
    if not cleaned:
        cleaned = tokens  # all tokens were initials — keep something
    if len(cleaned) == 1:
        return _Extracted(first=None, last=cleaned[0], honorific=None)
    # Last token is surname; first token is firstname.
    return _Extracted(first=cleaned[0], last=cleaned[-1], honorific=None)


@dataclass
class ResolveStats:
    candidates: int = 0
    extracted: int = 0
    fk_hits: int = 0
    fk_hits_pass2: int = 0
    fk_misses: int = 0
    speeches_updated: int = 0
    chunks_updated: int = 0
    misses_sample: list[tuple[str, str]] = dc_field(default_factory=list)


async def resolve_inline_presiding(
    db: Database, *, province: Optional[str] = None,
    limit: Optional[int] = None,
) -> ResolveStats:
    """Walk speeches with politician_id=NULL whose speaker_name_raw
    contains a parens-name, extract the name, FK-match, update.

    Args:
      province: optional 2-letter code to scope the run. None = all
                provinces. Federal-level rows are always excluded
                (federal Hansard uses different conventions).
      limit: cap candidate speeches scanned (smoke-test aid).
    """
    stats = ResolveStats()

    # Pre-filter: any parens content. The regex match in Python below
    # decides whether the row qualifies (honorific-form, or bare-name
    # form gated on presiding-prefix outer text).
    sql = """
        SELECT s.id::text AS id,
               s.province_territory AS prov,
               s.speaker_name_raw   AS raw,
               s.spoken_at::date    AS spoken_date
          FROM speeches s
         WHERE s.level = 'provincial'
           AND s.politician_id IS NULL
           AND s.speaker_name_raw ~ '\\(.+\\)'
    """
    params: list = []
    if province:
        sql += " AND s.province_territory = $1"
        params.append(province)
    if limit is not None:
        sql += f" LIMIT {int(limit)}"

    rows = await db.fetch(sql, *params)
    stats.candidates = len(rows)

    # Per-province (lowercased lastname → list[(politician_id,
    # firstname_lower)]) cache. Built lazily per province on demand.
    cache: dict[str, dict[str, list[tuple[str, str]]]] = {}

    async def _load_cache(prov: str) -> dict[str, list[tuple[str, str]]]:
        if prov in cache:
            return cache[prov]
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
            idx.setdefault(key, []).append((r["id"], _norm(r["first_name"] or "")))
        cache[prov] = idx
        return idx

    # Per-province cache of presiding-officer terms for Pass-2 date-
    # windowed narrowing. Each entry is (politician_id, started_at,
    # ended_at). Loaded lazily once per province.
    presiding_cache: dict[str, list[tuple[str, date_type, Optional[date_type]]]] = {}

    async def _load_presiding_terms(prov: str) -> list[tuple[str, date_type, Optional[date_type]]]:
        if prov in presiding_cache:
            return presiding_cache[prov]
        trows = await db.fetch(
            """
            SELECT politician_id::text AS politician_id,
                   started_at::date    AS started_at,
                   ended_at::date      AS ended_at
              FROM politician_terms
             WHERE level = 'provincial'
               AND province_territory = $1
               AND office IN ('Speaker', 'Deputy Speaker')
               AND source IN ($2, $3)
            """,
            prov, SOURCE_TAG, DEPUTY_SOURCE_TAG,
        )
        out = [(r["politician_id"], r["started_at"], r["ended_at"]) for r in trows]
        presiding_cache[prov] = out
        return out

    def _presiding_on(terms: list[tuple[str, date_type, Optional[date_type]]],
                     d: Optional[date_type]) -> set[str]:
        if d is None:
            return set()
        return {pid for (pid, started, ended) in terms
                if d >= started and (ended is None or d < ended)}

    # Bucket speech_ids by resolved politician_id for bulk UPDATE.
    # Pass-1 hits land at confidence 0.85; Pass-2 (date-windowed
    # narrowing) hits land at 0.80 — separate buckets to keep the
    # UPDATE confidence values distinct.
    by_politician: dict[str, list[str]] = {}
    by_politician_pass2: dict[str, list[str]] = {}

    for row in rows:
        raw = row["raw"] or ""
        # Reject all-caps speaker labels (BC P29-P34 era uses `MR. G.S.
        # WALLACE (Oak Bay)` — an MLA turn with constituency in parens,
        # not a presiding-officer turn). Detect via "all alphabetic chars
        # uppercase" — French diacritics are mixed-case so they'd pass.
        alpha_only = "".join(c for c in raw if c.isalpha())
        if alpha_only and alpha_only == alpha_only.upper():
            continue

        # Try honorific-name parens first (most specific).
        m = _PARENS_HONORIFIC_NAME_RE.search(raw)
        bare_match = None
        if m is None:
            # Fall back to bare-name parens, but only when the speaker
            # label PREFIX is a presiding-officer role (otherwise the
            # parens content is likely a constituency or title, not a
            # name — e.g. `Mr. Hugh McFadyen (Leader of the Official
            # Opposition)` has bare-text parens but the prefix isn't
            # a presiding role, so we skip it).
            if not _PRESIDING_PREFIX_RE.match(raw):
                continue
            bare_match = _PARENS_BARE_NAME_RE.search(raw)
            if bare_match is None:
                continue
        name_text = (m.group("name") if m else bare_match.group("name"))
        ext = _split_name(name_text)
        if ext is None or not ext.last:
            continue
        stats.extracted += 1

        prov = row["prov"]
        if not prov:
            continue
        prov_idx = await _load_cache(prov)
        last_key = _norm(ext.last)
        candidates_pol = prov_idx.get(last_key, [])

        pol_id: Optional[str] = None
        pass2_hit = False
        if len(candidates_pol) == 1:
            pol_id = candidates_pol[0][0]
        elif len(candidates_pol) > 1 and ext.first:
            first_key = _norm(ext.first)
            narrowed = [c for c in candidates_pol if c[1].startswith(first_key[:1])]
            if len(narrowed) == 1:
                pol_id = narrowed[0][0]
            else:
                # Try exact firstname match.
                exact = [c for c in candidates_pol if c[1] == first_key]
                if len(exact) == 1:
                    pol_id = exact[0][0]

        # Pass-2 narrowing: when surname/first-name still leaves multiple
        # candidates, intersect with the set of politicians who held a
        # Speaker / Deputy-Speaker term on the speech date. QC's parens
        # labels often carry only an honorific + surname (`M. Lévesque`),
        # which is ambiguous across QC's full politician history; date-
        # windowed presiding-role membership disambiguates.
        if pol_id is None and len(candidates_pol) > 1:
            terms = await _load_presiding_terms(prov)
            active = _presiding_on(terms, row["spoken_date"])
            if active:
                overlap = [c for c in candidates_pol if c[0] in active]
                if len(overlap) == 1:
                    pol_id = overlap[0][0]
                    pass2_hit = True

        if pol_id is None:
            stats.fk_misses += 1
            if len(stats.misses_sample) < 10:
                stats.misses_sample.append((prov, (m.group("name") if m else bare_match.group("name")).strip()))
            continue
        if pass2_hit:
            stats.fk_hits_pass2 += 1
            by_politician_pass2.setdefault(pol_id, []).append(row["id"])
        else:
            stats.fk_hits += 1
            by_politician.setdefault(pol_id, []).append(row["id"])

    # Bulk UPDATE in 5K-row chunks per politician. Pass-1 hits at 0.85,
    # Pass-2 (date-windowed) hits at 0.80 — separate UPDATEs so the
    # confidence floor is correct on each row.
    async def _apply_updates(buckets: dict[str, list[str]], confidence: float) -> None:
        for pol_id, speech_ids in buckets.items():
            for i in range(0, len(speech_ids), 5000):
                chunk = speech_ids[i : i + 5000]
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
                # Reconcile speech_chunks.politician_id (chunks created
                # before this resolver ran hold the NULL copy). speech_chunks
                # has no updated_at column — only set politician_id.
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

    await _apply_updates(by_politician, 0.85)
    await _apply_updates(by_politician_pass2, 0.80)

    log.info(
        "inline_presiding_resolver: candidates=%d extracted=%d "
        "fk_hits=%d fk_hits_pass2=%d fk_misses=%d "
        "speeches_updated=%d chunks_updated=%d",
        stats.candidates, stats.extracted,
        stats.fk_hits, stats.fk_hits_pass2, stats.fk_misses,
        stats.speeches_updated, stats.chunks_updated,
    )
    return stats
