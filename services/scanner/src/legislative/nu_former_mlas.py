"""NU historical-MLA roster (6th Legislative Assembly, 2021-2025).

Same shape as `nb_former_mlas` / `ns_former_mlas` / `nl_former_mlas`.
NU Hansard PDFs reachable via assembly.nu.ca/hansard span 2021-02-24
to 2024-05-31 — almost entirely the **6th Assembly** plus the very
last days of the 5th. The existing direct-scraper that populated 22
current 7th Assembly MLAs (sworn in Nov 2025) doesn't see the 6th
Assembly cohort, so any pre-Nov-2025 NU Hansard speech from a 6th-
Assembly MLA who didn't also win in 2025 stays unattributed.

Data sourced from Wikipedia's `6th Nunavut Legislature` article, table
of members per constituency (English page, 22 MLAs). Mid-term changes
(by-elections / floor-crossings / deaths) are recorded as overrides
on individual ``_RosterEntry`` items where known.

## Match heuristic for "already in DB"

NU has multi-word surnames common in Inuit-language naming
(``Pitsiulaaq Brewster``, ``Healey Akearok``, ``Nelvana Lyall``). The
current-MLA scrape stored the full multi-word string in
``last_name``; this seed-from-literal carries the shorter Wikipedia
form (``Brewster``). The pre-check tolerates either pattern by
matching when:

  - ``last_name`` equals the Wikipedia form, OR
  - ``last_name`` contains the Wikipedia form as a whitespace-
    delimited token (catches Pitsiulaaq Brewster ⊇ Brewster).

The first-name pre-check is on the leading token only (also accent-
stripped) — catches ``Honourable Janet`` in the existing row vs
``Janet`` in the literal.
"""

from __future__ import annotations

import logging
import unicodedata
from dataclasses import dataclass
from datetime import date
from typing import Optional

from ..db import Database

log = logging.getLogger(__name__)

SOURCE_TAG = "wikipedia:nu-assembly"


# Assembly date spans.
#   5th: Oct 30 2017 election → Oct 18 2021 election (writ drop).
#       Sworn-in date Nov 21 2017; Hansard runs through Oct 2021.
#   6th: Oct 25 2021 election → Sep 22 2025 dissolution.
NU_ASSEMBLY_DATES: dict[int, tuple[date, date]] = {
    5: (date(2017, 11, 21), date(2021, 10, 18)),
    6: (date(2021, 11, 19), date(2025, 9, 22)),
}


@dataclass
class _RosterEntry:
    full_name: str
    first_name: str
    last_name: str
    constituency: str
    started_override: Optional[date] = None
    ended_override: Optional[date] = None


# 6th Nunavut Legislature (2021-11-19 → 2025-09-22).
# Source: https://en.wikipedia.org/wiki/6th_Nunavut_Legislature
# Consensus government; no party affiliation modelled.
NU_6L: list[_RosterEntry] = [
    _RosterEntry("Joanna Quassa",     "Joanna",     "Quassa",     "Aggu"),
    _RosterEntry("Solomon Malliki",   "Solomon",    "Malliki",    "Aivilik"),
    _RosterEntry("Joelie Kaernerk",   "Joelie",     "Kaernerk",   "Amittuq"),
    _RosterEntry("John Main",         "John",       "Main",       "Arviat North-Whale Cove"),
    _RosterEntry("Joe Savikataaq",    "Joe",        "Savikataaq", "Arviat South"),
    _RosterEntry("Craig Simailak",    "Craig",      "Simailak",   "Baker Lake"),
    _RosterEntry("Pamela Gross",      "Pamela",     "Gross",      "Cambridge Bay"),
    _RosterEntry("Tony Akoak",        "Tony",       "Akoak",      "Gjoa Haven"),
    _RosterEntry("Daniel Qavvik",     "Daniel",     "Qavvik",     "Hudson Bay"),
    _RosterEntry("Adam Lightstone",   "Adam",       "Lightstone", "Iqaluit-Manirajak"),
    _RosterEntry("P. J. Akeeagok",    "P. J.",      "Akeeagok",   "Iqaluit-Niaqunnguu"),
    _RosterEntry("Janet Brewster",    "Janet",      "Brewster",   "Iqaluit-Sinaa"),
    _RosterEntry("George Hickes",     "George",     "Hickes",     "Iqaluit-Tasiluk"),
    _RosterEntry("Bobby Anavilok",    "Bobby",      "Anavilok",   "Kugluktuk"),
    _RosterEntry("Inagayuk Quqqiaq",  "Inagayuk",   "Quqqiaq",    "Netsilik"),
    _RosterEntry("Margaret Nakashuk", "Margaret",   "Nakashuk",   "Pangnirtung"),
    _RosterEntry("David Akeeagok",    "David",      "Akeeagok",   "Quttiktuq"),
    _RosterEntry("Alexander Sammurtok", "Alexander", "Sammurtok", "Rankin Inlet North-Chesterfield Inlet"),
    _RosterEntry("Lorne Kusugak",     "Lorne",      "Kusugak",    "Rankin Inlet South"),
    _RosterEntry("David Joanasie",    "David",      "Joanasie",   "South Baffin"),
    _RosterEntry("Karen Nutarak",     "Karen",      "Nutarak",    "Tununiq"),
    _RosterEntry("Mary Killiktee",    "Mary",       "Killiktee",  "Uqqummiut"),
]


# 5th Nunavut Legislature (2017-11-21 → 2021-10-18).
# Source: https://en.wikipedia.org/wiki/5th_Nunavut_Legislature
# 22 seats; three by-election replacements captured as started/ended
# overrides on the affected pair of entries.
NU_5L: list[_RosterEntry] = [
    _RosterEntry("Paul Quassa",         "Paul",      "Quassa",      "Aggu"),
    _RosterEntry("Patterk Netser",      "Patterk",   "Netser",      "Aivilik"),
    _RosterEntry("Joelie Kaernerk",     "Joelie",    "Kaernerk",    "Amittuq"),
    _RosterEntry("John Main",           "John",      "Main",        "Arviat North-Whale Cove"),
    _RosterEntry("Joe Savikataaq",      "Joe",       "Savikataaq",  "Arviat South"),
    # Baker Lake: Mikkungwak resigned 2020-02-25; Simailak elected 2020-08-24.
    _RosterEntry("Simeon Mikkungwak",   "Simeon",    "Mikkungwak",  "Baker Lake",
                 ended_override=date(2020, 2, 25)),
    _RosterEntry("Craig Simailak",      "Craig",     "Simailak",    "Baker Lake",
                 started_override=date(2020, 8, 24)),
    _RosterEntry("Jeannie Ehaloak",     "Jeannie",   "Ehaloak",     "Cambridge Bay"),
    _RosterEntry("Tony Akoak",          "Tony",      "Akoak",       "Gjoa Haven"),
    _RosterEntry("Allan Rumbolt",       "Allan",     "Rumbolt",     "Hudson Bay"),
    _RosterEntry("Adam Lightstone",     "Adam",      "Lightstone",  "Iqaluit-Manirajak"),
    _RosterEntry("Pat Angnakak",        "Pat",       "Angnakak",    "Iqaluit-Niaqunnguu"),
    _RosterEntry("Elisapee Sheutiapik", "Elisapee",  "Sheutiapik",  "Iqaluit-Sinaa"),
    _RosterEntry("George Hickes",       "George",    "Hickes",      "Iqaluit-Tasiluk"),
    # Kugluktuk: Kamingoak resigned 2020-04-03; Pedersen elected 2020-08-24.
    _RosterEntry("Mila Adjukak Kamingoak", "Mila Adjukak", "Kamingoak", "Kugluktuk",
                 ended_override=date(2020, 4, 3)),
    _RosterEntry("Calvin Pedersen",     "Calvin",    "Pedersen",    "Kugluktuk",
                 started_override=date(2020, 8, 24)),
    _RosterEntry("Emiliano Qirngnuq",   "Emiliano",  "Qirngnuq",    "Netsilik"),
    _RosterEntry("Margaret Nakashuk",   "Margaret",  "Nakashuk",    "Pangnirtung"),
    _RosterEntry("David Akeeagok",      "David",     "Akeeagok",    "Quttiktuq"),
    _RosterEntry("Cathy Towtongie",     "Cathy",     "Towtongie",   "Rankin Inlet North-Chesterfield Inlet"),
    _RosterEntry("Lorne Kusugak",       "Lorne",     "Kusugak",     "Rankin Inlet South"),
    _RosterEntry("David Joanasie",      "David",     "Joanasie",    "South Baffin"),
    # Tununiq: Enook died in office 2019-03-29; Qamaniq elected 2019-09-16.
    _RosterEntry("Joe Enook",           "Joe",       "Enook",       "Tununiq",
                 ended_override=date(2019, 3, 29)),
    _RosterEntry("David Qamaniq",       "David",     "Qamaniq",     "Tununiq",
                 started_override=date(2019, 9, 16)),
    _RosterEntry("Pauloosie Keyootak",  "Pauloosie", "Keyootak",    "Uqqummiut"),
]


NU_ROSTER: dict[int, list[_RosterEntry]] = {
    5: NU_5L,
    6: NU_6L,
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


async def ingest_nu_former_mlas(db: Database) -> Stats:
    stats = Stats()
    unique_keys: set[tuple[str, str]] = set()

    for asm_n, entries in NU_ROSTER.items():
        asm_start, asm_end = NU_ASSEMBLY_DATES[asm_n]
        stats.legislatures_processed += 1
        for entry in entries:
            unique_keys.add((
                _strip_accents(entry.first_name).lower(),
                _strip_accents(entry.last_name).lower(),
            ))

            # Fuzzier match — first-name leading token, and last_name
            # either matches exactly OR contains the Wikipedia form as
            # a whitespace-delimited token (catches multi-word surnames
            # like "Pitsiulaaq Brewster" containing "Brewster").
            pol = await db.fetchrow(
                """
                SELECT id FROM politicians
                 WHERE level='provincial' AND province_territory='NU'
                   AND lower(unaccent(split_part(first_name, ' ', 1)))
                       = lower(unaccent($1))
                   AND (
                         lower(unaccent(last_name)) = lower(unaccent($2))
                      OR lower(unaccent($2)) = ANY(
                           string_to_array(lower(unaccent(last_name)), ' ')
                         )
                       )
                 LIMIT 1
                """,
                entry.first_name.split()[0] if entry.first_name else "",
                entry.last_name,
            )
            if pol is not None:
                pol_id = pol["id"]
                stats.politicians_matched_existing += 1
                # If we matched a multi-word last_name, also stamp the
                # 6th Assembly constituency so the Hansard resolver's
                # constituency_name disambiguation works historically.
                # (Current 7th-Assembly constituency stays primary; we
                # write only when missing.)
                await db.execute(
                    """
                    UPDATE politicians
                       SET constituency_name = COALESCE(constituency_name, $2)
                     WHERE id = $1
                    """,
                    pol_id, entry.constituency,
                )
            else:
                source_id = (
                    f"wikipedia:nu-assembly:"
                    f"{_strip_accents(entry.last_name).lower().replace(' ', '-')}-"
                    f"{_strip_accents(entry.first_name).lower().replace(' ', '-').replace('.', '')}"
                )
                row = await db.fetchrow(
                    """
                    INSERT INTO politicians
                        (name, first_name, last_name,
                         level, province_territory,
                         constituency_name,
                         is_active, source_id, social_urls, extras)
                    VALUES ($1, $2, $3, 'provincial', 'NU',
                            $4, false, $5, '{}'::jsonb, '{}'::jsonb)
                    RETURNING id
                    """,
                    entry.full_name, entry.first_name, entry.last_name,
                    entry.constituency, source_id,
                )
                pol_id = row["id"]
                stats.politicians_inserted += 1

            started_at = entry.started_override or asm_start
            ended_at = entry.ended_override or asm_end
            existing_term = await db.fetchrow(
                """
                SELECT id FROM politician_terms
                 WHERE politician_id = $1
                   AND office = 'MLA'
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
                VALUES ($1, 'MLA', 'provincial', 'NU', $2, $3, $4)
                """,
                pol_id, started_at, ended_at, SOURCE_TAG,
            )
            stats.terms_inserted += 1

    stats.unique_mlas = len(unique_keys)
    log.info(
        "ingest_nu_former_mlas: leg=%d unique=%d new=%d matched=%d "
        "terms_inserted=%d terms_skipped=%d",
        stats.legislatures_processed, stats.unique_mlas,
        stats.politicians_inserted, stats.politicians_matched_existing,
        stats.terms_inserted, stats.terms_skipped_existing,
    )
    return stats
