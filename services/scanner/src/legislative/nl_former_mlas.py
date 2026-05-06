"""NL historical-MLA roster (50th General Assembly, 2021-2025).

Same shape as `nb_former_mlas` / `ns_former_mlas`. NL Hansard span is
2022-2026 — almost entirely the 50th General Assembly + the start of
the 51st (current). The existing `direct:legnl-ca` ingester only knows
the sitting 51st GA, so any 2022-2025 speech from a 50th-GA MLA who
didn't also win in 2025 stays unattributed.

Pass 4 also needs a NL-specific regex extension because NL Hansard
uses an initial-prefix label shape (`J. BROWN:`, `A. FUREY:`, `H.
CONWAY OTTENHEIMER:`) without honorifics — handled in
`named_speaker_resolver._NAMED_INITIAL_RE`.
"""
from __future__ import annotations

import logging
import unicodedata
from dataclasses import dataclass
from datetime import date
from typing import Optional

from ..db import Database

log = logging.getLogger(__name__)

SOURCE_TAG = "wikipedia:nl-assembly"


# 50th GA: 2021 election (March 27 vote, sworn in April 15) → 2025
# election (April 23 dissolution / writ drop). Mid-Assembly events
# captured per-MLA below.
NL_ASSEMBLY_DATES: dict[int, tuple[date, date]] = {
    50: (date(2021,  4, 15), date(2025,  4, 23)),
}


@dataclass
class _RosterEntry:
    full_name: str
    first_name: str
    last_name: str
    started_override: Optional[date] = None
    ended_override: Optional[date] = None


# 50th General Assembly (2021-04-15 → 2025-04-23) — Furey Liberal majority
NL_50L: list[_RosterEntry] = [
    # Liberal
    _RosterEntry("Brian Warr",            "Brian",      "Warr",            ended_override=date(2024,  1,  1)),  # resigned 2024 (mid-year, exact date TBD)
    _RosterEntry("Andrew Parsons",        "Andrew",     "Parsons",         ended_override=date(2025,  1,  1)),  # resigned 2025
    _RosterEntry("Paul Pike",             "Paul",       "Pike"),
    _RosterEntry("Steve Crocker",         "Steve",      "Crocker"),
    _RosterEntry("Lisa Dempster",         "Lisa",       "Dempster"),
    _RosterEntry("Fred Hutton",           "Fred",       "Hutton",          started_override=date(2024,  1, 30)),  # by-election
    _RosterEntry("Gerry Byrne",           "Gerry",      "Byrne"),
    _RosterEntry("Derrick Bragg",         "Derrick",    "Bragg",           ended_override=date(2024,  1,  1)),  # died 2024
    _RosterEntry("Elvis Loveless",        "Elvis",      "Loveless"),
    _RosterEntry("John Haggie",           "John",       "Haggie"),
    _RosterEntry("Pam Parsons",           "Pam",        "Parsons"),
    _RosterEntry("Andrew Furey",          "Andrew",     "Furey"),
    _RosterEntry("Derek Bennett",         "Derek",      "Bennett"),
    _RosterEntry("Lucy Stoyles",          "Lucy",       "Stoyles"),
    _RosterEntry("Sarah Stoodley",        "Sarah",      "Stoodley"),
    _RosterEntry("Sherry Gambin-Walsh",   "Sherry",     "Gambin-Walsh"),
    _RosterEntry("Krista Howell",         "Krista",     "Howell"),
    _RosterEntry("Scott Reid",            "Scott",      "Reid"),
    _RosterEntry("John Abbott",           "John",       "Abbott",          ended_override=date(2025,  1,  1)),  # resigned 2025
    _RosterEntry("Siobhan Coady",         "Siobhan",    "Coady"),
    _RosterEntry("Bernard Davis",         "Bernard",    "Davis"),
    _RosterEntry("Tom Osborne",           "Tom",        "Osborne",         ended_override=date(2024,  1,  1)),  # resigned 2024
    _RosterEntry("Jamie Korab",           "Jamie",      "Korab",           started_override=date(2024,  8, 22)),  # by-election
    _RosterEntry("John Hogan",            "John",       "Hogan"),
    # Progressive Conservative
    _RosterEntry("Lin Paddock",           "Lin",        "Paddock",         started_override=date(2024,  5, 27)),  # by-election
    _RosterEntry("Craig Pardy",           "Craig",      "Pardy"),
    _RosterEntry("Joedy Wall",            "Joedy",      "Wall"),
    _RosterEntry("David Brazil",          "David",      "Brazil",          ended_override=date(2023,  1,  1)),  # resigned 2023
    _RosterEntry("Barry Petten",          "Barry",      "Petten"),
    _RosterEntry("Pleaman Forsey",        "Pleaman",    "Forsey"),
    _RosterEntry("Loyola O'Driscoll",     "Loyola",     "O'Driscoll"),
    _RosterEntry("Jim McKenna",           "Jim",        "McKenna",         started_override=date(2024,  4, 15)),  # by-election
    _RosterEntry("Chris Tibbs",           "Chris",      "Tibbs"),
    _RosterEntry("Helen Conway-Ottenheimer", "Helen Conway", "Ottenheimer"),  # surname stored as "Ottenheimer" with first="Helen Conway"
    _RosterEntry("Jeff Dwyer",            "Jeff",       "Dwyer"),
    _RosterEntry("Tony Wakeham",          "Tony",       "Wakeham"),
    _RosterEntry("Lloyd Parrott",         "Lloyd",      "Parrott"),
    _RosterEntry("Paul Dinn",             "Paul",       "Dinn"),
    _RosterEntry("Lela Evans",            "Lela",       "Evans"),
    # NDP
    _RosterEntry("Jim Dinn",              "Jim",        "Dinn"),
    _RosterEntry("Jordan Brown",          "Jordan",     "Brown",           ended_override=date(2025,  1,  1)),  # resigned 2025
    # Independent
    _RosterEntry("Eddie Joyce",           "Eddie",      "Joyce"),
    _RosterEntry("Perry Trimper",         "Perry",      "Trimper"),
    _RosterEntry("Paul Lane",             "Paul",       "Lane"),
]


NL_ROSTER: dict[int, list[_RosterEntry]] = {
    50: NL_50L,
}


@dataclass
class Stats:
    legislatures_processed: int = 0
    unique_mlas: int = 0
    politicians_inserted: int = 0
    politicians_matched_existing: int = 0
    terms_inserted: int = 0
    terms_skipped_existing: int = 0


def _strip_accents(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )


async def ingest_nl_former_mlas(db: Database) -> Stats:
    stats = Stats()
    unique_keys: set[tuple[str, str]] = set()

    for asm_n, entries in NL_ROSTER.items():
        asm_start, asm_end = NL_ASSEMBLY_DATES[asm_n]
        stats.legislatures_processed += 1
        for entry in entries:
            unique_keys.add((
                _strip_accents(entry.first_name).lower(),
                _strip_accents(entry.last_name).lower(),
            ))

            pol = await db.fetchrow(
                """
                SELECT id FROM politicians
                 WHERE level='provincial' AND province_territory='NL'
                   AND lower(unaccent(split_part(first_name, ' ', 1)))
                       = lower(unaccent($1))
                   AND lower(unaccent(last_name)) = lower(unaccent($2))
                 LIMIT 1
                """,
                entry.first_name, entry.last_name,
            )
            if pol is not None:
                pol_id = pol["id"]
                stats.politicians_matched_existing += 1
            else:
                source_id = (
                    f"wikipedia:nl-assembly:"
                    f"{_strip_accents(entry.last_name).lower()}-"
                    f"{_strip_accents(entry.first_name).lower()}"
                )
                row = await db.fetchrow(
                    """
                    INSERT INTO politicians
                        (name, first_name, last_name,
                         level, province_territory,
                         is_active, source_id, social_urls, extras)
                    VALUES ($1, $2, $3, 'provincial', 'NL',
                            false, $4, '{}'::jsonb, '{}'::jsonb)
                    RETURNING id
                    """,
                    entry.full_name, entry.first_name, entry.last_name,
                    source_id,
                )
                pol_id = row["id"]
                stats.politicians_inserted += 1

            started_at = entry.started_override or asm_start
            ended_at = entry.ended_override or asm_end
            existing_term = await db.fetchrow(
                """
                SELECT id FROM politician_terms
                 WHERE politician_id = $1
                   AND office = 'MHA'
                   AND started_at = $2
                   AND source = $3
                """,
                pol_id, started_at, SOURCE_TAG,
            )
            if existing_term is not None:
                stats.terms_skipped_existing += 1
                continue
            await db.execute(
                """
                INSERT INTO politician_terms
                    (politician_id, office, level, province_territory,
                     started_at, ended_at, source)
                VALUES ($1, 'MHA', 'provincial', 'NL', $2, $3, $4)
                """,
                pol_id, started_at, ended_at, SOURCE_TAG,
            )
            stats.terms_inserted += 1

    stats.unique_mlas = len(unique_keys)
    log.info(
        "ingest_nl_former_mlas: leg=%d unique=%d new=%d matched=%d "
        "terms_inserted=%d terms_skipped=%d",
        stats.legislatures_processed, stats.unique_mlas,
        stats.politicians_inserted, stats.politicians_matched_existing,
        stats.terms_inserted, stats.terms_skipped_existing,
    )
    return stats
