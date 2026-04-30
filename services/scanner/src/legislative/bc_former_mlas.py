"""BC pre-1992 MLA roster backfill from Wikipedia per-parliament tables.

Closes the pre-P35 gap left by `bc_member_parliaments.py` (which sources
from LIMS `allMemberParliaments` — LIMS only knows P35+, 1992+).

Wikipedia maintains per-parliament list articles for every BC parliament,
e.g. ``30th_Parliament_of_British_Columbia``. Each article has a Members
section with a ``wikitable sortable`` that exposes:

  * Member name (wikilinked)
  * Electoral district (wikilinked)
  * Party (wikilinked, with optional rowspan when MLAs change party
    mid-parliament)
  * First elected year(s) (comma-separated when service was
    interrupted, e.g. "1949, 1960")
  * Term count + interrupted-flag (e.g. "8th term*")

We fetch the wikitext via MediaWiki ``action=parse&prop=wikitext``, parse
the table, upsert one ``politicians`` row per unique MLA, and one
``politician_terms`` row per (politician, parliament). Re-runs are
no-ops via partial UNIQUE on ``politicians.source_id`` and an existence
check on ``politician_terms`` keyed by (politician_id, source).

Why Wikipedia (not the legislature directly): ``leg.bc.ca/members/...``
pages are JS-rendered with no static data, and Elections BC only
publishes PDFs. Wikipedia has clean, complete, structured tables for
every BC parliament back to 1871 and the wikilink targets give us a
stable canonical key per MLA.

Scope: parliaments 29-34 (1969-1991), the unresolved-Hansard window. The
ingester accepts ``--parliaments`` to override; CLI default is the full
29-34 range.
"""
from __future__ import annotations

import asyncio
import logging
import re
import unicodedata
from dataclasses import dataclass, field as dc_field
from datetime import date, datetime, timezone
from typing import Optional

import httpx

from ..db import Database
from .ab_former_mlas import _get_with_retry

log = logging.getLogger(__name__)

WIKI_API = "https://en.wikipedia.org/w/api.php"

# BC parliaments 29-34, sitting windows (election → next election day).
# Sources: Elections BC general-election register + per-parliament
# Wikipedia ledes. Election dates are conservative — first sittings are
# weeks later, but a wider window doesn't harm the date-windowed resolver
# (no Hansard exists outside actual sittings).
BC_PARLIAMENT_DATES: dict[int, tuple[date, date]] = {
    29: (date(1969,  8, 27), date(1972,  8, 30)),
    30: (date(1972,  8, 30), date(1975, 12, 11)),
    31: (date(1975, 12, 11), date(1979,  5, 10)),
    32: (date(1979,  5, 10), date(1983,  5,  5)),
    33: (date(1983,  5,  5), date(1986, 10, 22)),
    34: (date(1986, 10, 22), date(1991, 10, 17)),
}

DEFAULT_PARLIAMENTS: tuple[int, ...] = (29, 30, 31, 32, 33, 34)


# ── Models ──────────────────────────────────────────────────────────


@dataclass
class BCMember:
    parliament_number: int
    canonical_name: str          # display form ("Robert Evans Skelly")
    wikipedia_slug: str          # wikilink target ("Bob_Skelly")
    first_name: str
    last_name: str
    district: Optional[str]
    party: Optional[str]
    first_elected_years: list[int]
    term_index: Optional[int]    # "8th term" → 8
    interrupted: bool
    by_election_year: Optional[int] = None  # for "(1988)" annotations


@dataclass
class IngestStats:
    parliaments_seen: int = 0
    rows_parsed: int = 0
    rows_skipped: int = 0
    unique_members: int = 0
    politicians_inserted: int = 0
    politicians_updated: int = 0
    politicians_name_matched: int = 0
    terms_inserted: int = 0
    terms_skipped_existing: int = 0
    parse_failures: list[str] = dc_field(default_factory=list)


# ── Helpers ─────────────────────────────────────────────────────────


def _ordinal(n: int) -> str:
    if 10 < n % 100 < 20:
        return f"{n}th"
    return f"{n}{['th','st','nd','rd','th','th','th','th','th','th'][n%10]}"


def _norm(s: str) -> str:
    if not s:
        return ""
    t = unicodedata.normalize("NFKD", s)
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.lower()
    t = re.sub(r"[^\w\s-]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _split_canonical_name(canonical: str) -> tuple[str, str]:
    """Split 'Robert Evans Skelly' → ('Robert', 'Skelly').

    Compound surnames (with hyphens / particles) are kept as the trailing
    multi-token tail when applicable; the conservative implementation
    just takes the first token as first-name and the last token as
    last-name. The dated resolver uses last-token matching anyway.
    """
    parts = canonical.strip().split()
    if not parts:
        return "", ""
    if len(parts) == 1:
        return "", parts[0]
    return parts[0], parts[-1]


# ── Wikitext parsing ────────────────────────────────────────────────

_ROW_START_RE = re.compile(
    r"\{\{\s*Canadian party colou?r\s*\|[^|]+\|([^|}]+)\|row\s*\}\}",
    re.IGNORECASE,
)
_WIKILINK_RE = re.compile(r"\[\[([^\]|]+?)(?:\|([^\]]+?))?\]\]")
_TERM_INDEX_RE = re.compile(r"(\d+)\s*(?:st|nd|rd|th)?\s*term", re.IGNORECASE)
_BY_ELECTION_RE = re.compile(r"\((\d{4})\)")


def _strip_wikilinks(s: str) -> str:
    """Replace [[link|display]] with display, [[link]] with link."""
    return _WIKILINK_RE.sub(lambda m: m.group(2) or m.group(1), s)


def _extract_first_wikilink(s: str) -> tuple[Optional[str], Optional[str]]:
    """Return (target, display_or_None) of first wikilink, or (None, None)."""
    m = _WIKILINK_RE.search(s)
    if not m:
        return None, None
    target, display = m.group(1), m.group(2)
    return target.strip(), (display.strip() if display else None)


def _normalise_party(s: str) -> Optional[str]:
    if not s:
        return None
    s = _strip_wikilinks(s).strip()
    s = re.sub(r"^\s*British Columbia\s+", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s+Party\s+of\s+British\s+Columbia$", "", s, flags=re.IGNORECASE)
    s = re.sub(r"^Independent.*$", "Independent", s, flags=re.IGNORECASE)
    return s.strip() or None


_CELL_ATTR_RE = re.compile(r"^[a-z0-9_=\"' -]+\|(.*)$", re.IGNORECASE)
_ROWSPAN_RE = re.compile(r"rowspan\s*=\s*\"?(\d+)", re.IGNORECASE)


def _parse_row_cells(body: str) -> list[tuple[str, int]]:
    """Split a row body into [(cell_value, rowspan), ...].

    Strips ``rowspan=N |`` / ``align="right" |`` attribute prefixes,
    capturing the rowspan integer when present (default 1). Stops at
    the next row separator or table close.
    """
    cells: list[tuple[str, int]] = []
    for line in body.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        if line.startswith("|-") or line.startswith("|}"):
            break
        line = line.lstrip("|").strip()
        m = _CELL_ATTR_RE.match(line)
        if m:
            attr_str = line[: line.index("|")]
            rs_m = _ROWSPAN_RE.search(attr_str)
            rowspan = int(rs_m.group(1)) if rs_m else 1
            value = m.group(1).strip()
        else:
            rowspan = 1
            value = line.strip()
        cells.append((value, rowspan))
    return cells


def _parse_members(wikitext: str, parl: int) -> tuple[list[BCMember], list[str]]:
    """Parse the Members section wikitable into BCMember rows.

    Returns (members, parse_warnings).
    """
    members: list[BCMember] = []
    warnings: list[str] = []

    # Split on each `{{Canadian party colour|...|row}}` template — they
    # delimit member rows. Output: [pre, party1, body1, party2, body2, ...]
    chunks = _ROW_START_RE.split(wikitext)
    if len(chunks) < 3:
        warnings.append(f"P{parl}: no party-colour row templates found; table shape unrecognised")
        return [], warnings

    # Per-position rowspan carry-over: cell-position → (value, rows_remaining).
    # BC tables rowspan district + party for multi-member ridings (e.g.
    # Vancouver Centre had 2 reps), and rowspan name+district+first+terms
    # for party-switchers (Frank Calder NDP→Social Credit mid-P30).
    carryover: dict[int, tuple[str, int]] = {}

    i = 1
    while i + 1 < len(chunks):
        party_token = chunks[i].strip()
        body = chunks[i + 1]
        i += 2

        raw_cells = _parse_row_cells(body)

        # Apply existing carryovers into a 5-slot row, then decrement.
        full: list[Optional[str]] = [None, None, None, None, None]
        for pos in list(carryover.keys()):
            val, rem = carryover[pos]
            if pos < 5:
                full[pos] = val
            rem -= 1
            if rem <= 0:
                del carryover[pos]
            else:
                carryover[pos] = (val, rem)

        # Fill the remaining slots from raw_cells, recording new rowspans
        # for downstream rows. raw_cells appear in left-to-right order,
        # filling whichever positions are still None.
        actual_idx = 0
        for pos in range(5):
            if full[pos] is None and actual_idx < len(raw_cells):
                val, rs = raw_cells[actual_idx]
                full[pos] = val
                if rs > 1:
                    carryover[pos] = (val, rs - 1)
                actual_idx += 1

        if any(c is None for c in full):
            # Underfilled even after carryover application — typically a
            # solo party-switcher row whose carryovers from row N-1 only
            # supplied 4 of 5 slots and there's no party cell here either.
            # Defensive skip; not expected on BC tables.
            continue

        name_cell, district_cell, party_cell, first_elected_cell, terms_cell = full

        # Some 1980s-era rows put a (YYYY) by-election annotation on the
        # name cell, e.g. "[[Gerard Janssen|Gerard A. Janssen]] (1988)".
        be_year_match = _BY_ELECTION_RE.search(name_cell)
        by_election_year = int(be_year_match.group(1)) if be_year_match else None

        target, display = _extract_first_wikilink(name_cell)
        if target:
            canonical = (display or target).strip()
            slug = target.replace(" ", "_")
        else:
            canonical = _strip_wikilinks(name_cell).strip()
            # Strip the (YYYY) annotation if present — it's not part of the name
            canonical = _BY_ELECTION_RE.sub("", canonical).strip()
            if not canonical:
                warnings.append(f"P{parl}: empty name cell, skipping")
                continue
            slug = canonical.replace(" ", "_")

        # Strip the (YYYY) annotation from canonical when it slipped through
        canonical = _BY_ELECTION_RE.sub("", canonical).strip()

        first_name, last_name = _split_canonical_name(canonical)

        district_target, district_display = _extract_first_wikilink(district_cell)
        district = (district_display or district_target or _strip_wikilinks(district_cell)).strip() or None

        party_in_cell = _normalise_party(party_cell)
        party = party_in_cell or _normalise_party(party_token) or None

        first_elected_years: list[int] = [
            int(y) for y in re.findall(r"\b(1[89]\d{2}|20\d{2})\b", first_elected_cell)
        ]

        term_match = _TERM_INDEX_RE.search(terms_cell)
        term_index = int(term_match.group(1)) if term_match else None
        interrupted = "*" in terms_cell

        members.append(BCMember(
            parliament_number=parl,
            canonical_name=canonical,
            wikipedia_slug=slug,
            first_name=first_name,
            last_name=last_name,
            district=district,
            party=party,
            first_elected_years=first_elected_years,
            term_index=term_index,
            interrupted=interrupted,
            by_election_year=by_election_year,
        ))

    return members, warnings


# ── Wikipedia API ───────────────────────────────────────────────────


async def _fetch_members_section(
    client: httpx.AsyncClient, parl: int,
) -> Optional[str]:
    """Fetch the wikitext of the 'Members' section for a BC parliament.

    Returns None if the article or section is missing.
    """
    page = f"{_ordinal(parl)}_Parliament_of_British_Columbia"

    # Find the Members section index.
    sections_url = (
        f"{WIKI_API}?action=parse&format=json"
        f"&page={page}&prop=sections"
    )
    r = await _get_with_retry(client, sections_url)
    data = r.json()
    if "error" in data:
        log.warning("bc_former_mlas: P%d sections lookup failed: %s",
                    parl, data["error"].get("info"))
        return None
    sections = data.get("parse", {}).get("sections", [])
    members_idx = next(
        (s["index"] for s in sections if "Members" in s.get("line", "")),
        None,
    )
    if members_idx is None:
        log.warning("bc_former_mlas: P%d has no Members section", parl)
        return None

    wt_url = (
        f"{WIKI_API}?action=parse&format=json"
        f"&page={page}&prop=wikitext&section={members_idx}"
    )
    r = await _get_with_retry(client, wt_url)
    data = r.json()
    if "error" in data:
        log.warning("bc_former_mlas: P%d wikitext fetch failed: %s",
                    parl, data["error"].get("info"))
        return None
    return data.get("parse", {}).get("wikitext", {}).get("*", "") or None


# ── DB upserts ──────────────────────────────────────────────────────


async def _load_existing_bc_politicians(db: Database) -> dict[str, dict]:
    """Index BC provincial politicians by normalised 'first last' name.

    Used to merge new Wikipedia rows onto existing roster (LIMS-keyed
    P35+ MLAs whose careers extend back into P34).
    """
    rows = await db.fetch(
        """
        SELECT id::text AS id, name, first_name, last_name,
               source_id, lims_member_id
          FROM politicians
         WHERE province_territory = 'BC' AND level = 'provincial'
        """
    )
    by_name: dict[str, dict] = {}
    for r in rows:
        key = _norm(f"{r['first_name'] or ''} {r['last_name'] or ''}")
        if key:
            by_name.setdefault(key, dict(r))
    return by_name


async def _upsert_politician(
    db: Database, m: BCMember, existing_by_name: dict[str, dict],
    stats: IngestStats,
) -> Optional[str]:
    """Return politicians.id (uuid as text), or None if upsert failed."""
    source_id = f"wikipedia:bc-mla:{m.wikipedia_slug}"

    # 1. Idempotent re-run: source_id already exists.
    row = await db.fetchrow(
        "SELECT id::text AS id FROM politicians WHERE source_id = $1",
        source_id,
    )
    if row:
        return row["id"]

    # 2. Name-merge against existing roster (LIMS-keyed modern MLAs whose
    #    career extended pre-P35). Stamp source_id on the existing row.
    full_norm = _norm(f"{m.first_name} {m.last_name}")
    nm_hit = existing_by_name.get(full_norm) if full_norm else None
    if nm_hit is not None:
        await db.execute(
            """
            UPDATE politicians
               SET source_id = COALESCE(source_id, $2),
                   updated_at = now()
             WHERE id = $1::uuid
            """,
            nm_hit["id"], source_id,
        )
        stats.politicians_name_matched += 1
        return nm_hit["id"]

    # 3. Fresh insert.
    row = await db.fetchrow(
        """
        INSERT INTO politicians
            (name, first_name, last_name, level, province_territory,
             is_active, source_id)
        VALUES
            ($1, $2, $3, 'provincial', 'BC', false, $4)
        ON CONFLICT (source_id) DO UPDATE SET updated_at = now()
        RETURNING id::text AS id, (xmax = 0) AS inserted
        """,
        m.canonical_name, m.first_name, m.last_name, source_id,
    )
    if row["inserted"]:
        stats.politicians_inserted += 1
    else:
        stats.politicians_updated += 1
    # Cache in existing_by_name so within-run later parliaments merge.
    if full_norm:
        existing_by_name[full_norm] = {
            "id": row["id"],
            "name": m.canonical_name,
            "first_name": m.first_name,
            "last_name": m.last_name,
            "source_id": source_id,
            "lims_member_id": None,
        }
    return row["id"]


async def _upsert_term(
    db: Database, politician_id: str, m: BCMember, stats: IngestStats,
) -> None:
    parl = m.parliament_number
    source = f"wikipedia:bc-{_ordinal(parl)}-parliament"
    started_d, ended_d = BC_PARLIAMENT_DATES[parl]

    # By-election members start at the by-election year (Jan 1, conservative)
    if m.by_election_year and m.by_election_year > started_d.year:
        started_d = date(m.by_election_year, 1, 1)

    started_at = datetime(started_d.year, started_d.month, started_d.day,
                          tzinfo=timezone.utc)
    ended_at = datetime(ended_d.year, ended_d.month, ended_d.day,
                        23, 59, 59, tzinfo=timezone.utc)

    existing = await db.fetchrow(
        """
        SELECT 1 FROM politician_terms
         WHERE politician_id = $1::uuid
           AND source = $2
        """,
        politician_id, source,
    )
    if existing is not None:
        stats.terms_skipped_existing += 1
        return

    await db.execute(
        """
        INSERT INTO politician_terms
            (politician_id, office, party, level, province_territory,
             constituency_id, started_at, ended_at, source)
        VALUES
            ($1::uuid, 'MLA', $2, 'provincial', 'BC',
             $3, $4, $5, $6)
        """,
        politician_id, m.party, m.district, started_at, ended_at, source,
    )
    stats.terms_inserted += 1


# ── Public entry point ──────────────────────────────────────────────


async def ingest_bc_former_mlas(
    db: Database,
    *,
    parliaments: Optional[tuple[int, ...]] = None,
    delay: float = 1.5,
) -> IngestStats:
    """Backfill BC pre-1992 MLA roster from Wikipedia.

    For each parliament in ``parliaments`` (default: 29-34), fetch the
    Members section, parse the wikitable, upsert one politicians row per
    unique MLA, and one politician_terms row per (politician, parliament).
    """
    stats = IngestStats()
    parls = parliaments or DEFAULT_PARLIAMENTS

    existing_by_name = await _load_existing_bc_politicians(db)

    headers = {
        "User-Agent": "SovereignWatch/1.0 (canadianpoliticaldata.ca; admin@thebunkerops.ca)",
        "Accept": "application/json",
    }
    seen_slugs: set[str] = set()

    async with httpx.AsyncClient(headers=headers, timeout=30.0) as client:
        for parl in parls:
            stats.parliaments_seen += 1
            wt = await _fetch_members_section(client, parl)
            if not wt:
                stats.parse_failures.append(f"P{parl}: members section unfetchable")
                await asyncio.sleep(delay)
                continue
            members, warnings = _parse_members(wt, parl)
            stats.parse_failures.extend(warnings)
            stats.rows_parsed += len(members)
            log.info("bc_former_mlas: P%d parsed %d members", parl, len(members))

            for m in members:
                seen_slugs.add(m.wikipedia_slug)
                pol_id = await _upsert_politician(db, m, existing_by_name, stats)
                if pol_id is None:
                    stats.rows_skipped += 1
                    continue
                await _upsert_term(db, pol_id, m, stats)

            await asyncio.sleep(delay)

    stats.unique_members = len(seen_slugs)
    log.info(
        "bc_former_mlas: parliaments=%d rows=%d unique=%d "
        "pols_inserted=%d pols_updated=%d pols_name_matched=%d "
        "terms_inserted=%d terms_skipped=%d failures=%d",
        stats.parliaments_seen, stats.rows_parsed, stats.unique_members,
        stats.politicians_inserted, stats.politicians_updated,
        stats.politicians_name_matched,
        stats.terms_inserted, stats.terms_skipped_existing,
        len(stats.parse_failures),
    )
    return stats
