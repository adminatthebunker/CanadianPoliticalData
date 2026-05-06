"""NS historical-MLA roster (62nd-64th General Assemblies, 2013-2024).

Same shape as `nb_former_mlas`: hand-curated Python literal sourced
from per-Assembly Wikipedia articles, ingested via Click command.
NS does not publish a clean former-members directory either.

Required for Pass 4 surname-only resolution to fire on NS Hansard
pre-2024 — the existing `ingest-ns-mlas` ingester only knows the
sitting 65th General Assembly.
"""
from __future__ import annotations

import logging
import unicodedata
from dataclasses import dataclass
from datetime import date
from typing import Optional

from ..db import Database

log = logging.getLogger(__name__)

SOURCE_TAG = "wikipedia:ns-assembly"


# Election day → next election day. Mid-Assembly events captured per-MLA.
NS_ASSEMBLY_DATES: dict[int, tuple[date, date]] = {
    62: (date(2013, 10,  8), date(2017,  5, 30)),
    63: (date(2017,  5, 30), date(2021,  8, 17)),
    64: (date(2021,  8, 17), date(2024, 11, 26)),
}


@dataclass
class _RosterEntry:
    full_name: str
    first_name: str
    last_name: str
    started_override: Optional[date] = None
    ended_override: Optional[date] = None


# 62nd Assembly (2013-10-08 → 2017-05-30) — McNeil Liberal majority
NS_62L: list[_RosterEntry] = [
    # Liberal (33)
    _RosterEntry("Stephen McNeil",        "Stephen",   "McNeil"),
    _RosterEntry("Randy Delorey",         "Randy",     "Delorey"),
    _RosterEntry("Kelly Regan",           "Kelly",     "Regan"),
    _RosterEntry("Diana Whalen",          "Diana",     "Whalen"),
    _RosterEntry("Karen Casey",           "Karen",     "Casey"),
    _RosterEntry("Joyce Treen",           "Joyce",     "Treen"),
    _RosterEntry("Tony Ince",             "Tony",      "Ince"),
    _RosterEntry("Terry Farrell",         "Terry",     "Farrell"),
    _RosterEntry("Joanne Bernard",        "Joanne",    "Bernard"),
    _RosterEntry("Allan Rowe",            "Allan",     "Rowe",            ended_override=date(2015,  3, 16)),
    _RosterEntry("Kevin Murphy",          "Kevin",     "Murphy"),
    _RosterEntry("Patricia Arab",         "Patricia",  "Arab"),
    _RosterEntry("Geoff MacLellan",       "Geoff",     "MacLellan"),
    _RosterEntry("Lloyd Hines",           "Lloyd",     "Hines"),
    _RosterEntry("Lena Diab",             "Lena",      "Diab"),
    _RosterEntry("Brendan Maguire",       "Brendan",   "Maguire"),
    _RosterEntry("Joachim Stroink",       "Joachim",   "Stroink"),
    _RosterEntry("Labi Kousoulis",        "Labi",      "Kousoulis"),
    _RosterEntry("Margaret Miller",       "Margaret",  "Miller"),
    _RosterEntry("Keith Irving",          "Keith",     "Irving"),
    _RosterEntry("Leo Glavine",           "Leo",       "Glavine"),
    _RosterEntry("Suzanne Lohnes-Croft",  "Suzanne",   "Lohnes-Croft"),
    _RosterEntry("Mark Furey",            "Mark",      "Furey"),
    _RosterEntry("Keith Colwell",         "Keith",     "Colwell"),
    _RosterEntry("Stephen Gough",         "Stephen",   "Gough"),
    _RosterEntry("Iain Rankin",           "Iain",      "Rankin"),
    _RosterEntry("Pam Eyking",            "Pam",       "Eyking"),
    _RosterEntry("Bill Horne",            "Bill",      "Horne"),
    _RosterEntry("Gordon Wilson",         "Gordon",    "Wilson"),
    _RosterEntry("Michel Samson",         "Michel",    "Samson"),
    _RosterEntry("Zach Churchill",        "Zach",      "Churchill"),
    _RosterEntry("Andrew Younger",        "Andrew",    "Younger",         ended_override=date(2015, 11,  5)),
    # By-election winners (62L)
    _RosterEntry("David Wilton",          "David",     "Wilton",          started_override=date(2015,  7, 14)),
    _RosterEntry("Marian Mancini",        "Marian",    "Mancini",         started_override=date(2015,  7, 14), ended_override=date(2017,  4, 23)),
    _RosterEntry("Derek Mombourquette",   "Derek",     "Mombourquette",   started_override=date(2015,  7, 14)),
    _RosterEntry("Lisa Roberts",          "Lisa",      "Roberts",         started_override=date(2016,  8, 30)),
    # Progressive Conservative (11)
    _RosterEntry("Jamie Baillie",         "Jamie",     "Baillie"),
    _RosterEntry("Chris d'Entremont",     "Chris",     "d'Entremont"),
    _RosterEntry("Larry Harrison",        "Larry",     "Harrison"),
    _RosterEntry("John Lohr",             "John",      "Lohr"),
    _RosterEntry("Allan MacMaster",       "Allan",     "MacMaster"),
    _RosterEntry("Eddie Orrell",          "Eddie",     "Orrell"),
    _RosterEntry("Pat Dunn",              "Pat",       "Dunn"),
    _RosterEntry("Tim Houston",           "Tim",       "Houston"),
    _RosterEntry("Karla MacFarlane",      "Karla",     "MacFarlane"),
    _RosterEntry("Alfie MacLeod",         "Alfie",     "MacLeod"),
    _RosterEntry("Chuck Porter",          "Chuck",     "Porter"),
    # NDP (7)
    _RosterEntry("Frank Corbett",         "Frank",     "Corbett",         ended_override=date(2015,  4,  2)),
    _RosterEntry("Denise Peterson-Rafuse","Denise",    "Peterson-Rafuse"),
    _RosterEntry("Dave Wilson",           "Dave",      "Wilson"),
    _RosterEntry("Sterling Belliveau",    "Sterling",  "Belliveau"),
    _RosterEntry("Gordie Gosse",          "Gordie",    "Gosse",           ended_override=date(2015,  4,  2)),
    _RosterEntry("Maureen MacDonald",     "Maureen",   "MacDonald",       ended_override=date(2016,  4, 12)),
    _RosterEntry("Lenore Zann",           "Lenore",    "Zann"),
]

# 63rd Assembly (2017-05-30 → 2021-08-17) — McNeil/Rankin Liberal
NS_63L: list[_RosterEntry] = [
    # Liberal (27)
    _RosterEntry("Stephen McNeil",        "Stephen",   "McNeil",          ended_override=date(2021,  5,  3)),
    _RosterEntry("Randy Delorey",         "Randy",     "Delorey"),
    _RosterEntry("Kelly Regan",           "Kelly",     "Regan"),
    _RosterEntry("Rafah DiCostanzo",      "Rafah",     "DiCostanzo"),
    _RosterEntry("Zach Churchill",        "Zach",      "Churchill"),
    _RosterEntry("Kevin Murphy",          "Kevin",     "Murphy"),
    _RosterEntry("Patricia Arab",         "Patricia",  "Arab"),
    _RosterEntry("Geoff MacLellan",       "Geoff",     "MacLellan"),
    _RosterEntry("Lloyd Hines",           "Lloyd",     "Hines"),
    _RosterEntry("Lena Diab",             "Lena",      "Diab"),
    _RosterEntry("Brendan Maguire",       "Brendan",   "Maguire"),
    _RosterEntry("Labi Kousoulis",        "Labi",      "Kousoulis"),
    _RosterEntry("Ben Jessome",           "Ben",       "Jessome"),
    _RosterEntry("Keith Irving",          "Keith",     "Irving"),
    _RosterEntry("Leo Glavine",           "Leo",       "Glavine"),
    _RosterEntry("Suzanne Lohnes-Croft",  "Suzanne",   "Lohnes-Croft"),
    _RosterEntry("Mark Furey",            "Mark",      "Furey"),
    _RosterEntry("Keith Colwell",         "Keith",     "Colwell"),
    _RosterEntry("Derek Mombourquette",   "Derek",     "Mombourquette"),
    _RosterEntry("Gordon Wilson",         "Gordon",    "Wilson"),
    _RosterEntry("Chuck Porter",          "Chuck",     "Porter"),
    _RosterEntry("Bill Horne",            "Bill",      "Horne"),
    _RosterEntry("Iain Rankin",           "Iain",      "Rankin"),
    _RosterEntry("Karen Casey",           "Karen",     "Casey"),
    _RosterEntry("Tony Ince",             "Tony",      "Ince"),
    _RosterEntry("Margaret Miller",       "Margaret",  "Miller",          ended_override=date(2021,  6,  1)),
    # PC (17)
    _RosterEntry("Jamie Baillie",         "Jamie",     "Baillie",         ended_override=date(2018,  1, 24)),
    _RosterEntry("Tory Rushton",          "Tory",      "Rushton",         started_override=date(2018,  6, 19)),
    _RosterEntry("Barbara Adams",         "Barbara",   "Adams"),
    _RosterEntry("Larry Harrison",        "Larry",     "Harrison"),
    _RosterEntry("Tim Halman",            "Tim",       "Halman"),
    _RosterEntry("Pat Dunn",              "Pat",       "Dunn"),
    _RosterEntry("Tim Houston",           "Tim",       "Houston"),
    _RosterEntry("Karla MacFarlane",      "Karla",     "MacFarlane"),
    _RosterEntry("John Lohr",             "John",      "Lohr"),
    _RosterEntry("Brad Johns",            "Brad",      "Johns"),
    _RosterEntry("Kim Masland",           "Kim",       "Masland"),
    _RosterEntry("Allan MacMaster",       "Allan",     "MacMaster"),
    _RosterEntry("Keith Bain",            "Keith",     "Bain"),
    _RosterEntry("Chris d'Entremont",     "Chris",     "d'Entremont",     ended_override=date(2019,  7, 31)),
    _RosterEntry("Eddie Orrell",          "Eddie",     "Orrell",          ended_override=date(2019,  7, 31)),
    _RosterEntry("Alfie MacLeod",         "Alfie",     "MacLeod",         ended_override=date(2019,  7, 31)),
    _RosterEntry("Alana Paon",            "Alana",     "Paon"),
    _RosterEntry("Elizabeth Smith-McCrossin", "Elizabeth", "Smith-McCrossin"),
    # NDP (7)
    _RosterEntry("Gary Burrill",          "Gary",      "Burrill"),
    _RosterEntry("Claudia Chender",       "Claudia",   "Chender"),
    _RosterEntry("Susan Leblanc",         "Susan",     "Leblanc"),
    _RosterEntry("Lisa Roberts",          "Lisa",      "Roberts"),
    _RosterEntry("Dave Wilson",           "Dave",      "Wilson",          ended_override=date(2018, 11, 16)),
    _RosterEntry("Steve Craig",           "Steve",     "Craig",           started_override=date(2019,  6, 19)),
    _RosterEntry("Tammy Martin",          "Tammy",     "Martin"),
]

# 64th Assembly (2021-08-17 → 2024-11-26) — Houston PC majority
NS_64L: list[_RosterEntry] = [
    # PC (31+)
    _RosterEntry("Tim Houston",           "Tim",       "Houston"),
    _RosterEntry("Michelle Thompson",     "Michelle",  "Thompson"),
    _RosterEntry("Colton LeBlanc",        "Colton",    "LeBlanc"),
    _RosterEntry("Brian Comer",           "Brian",     "Comer"),
    _RosterEntry("Danielle Barkhouse",    "Danielle",  "Barkhouse"),
    _RosterEntry("Larry Harrison",        "Larry",     "Harrison"),
    _RosterEntry("Tom Taggart",           "Tom",       "Taggart"),
    _RosterEntry("Tory Rushton",          "Tory",      "Rushton"),
    _RosterEntry("Tim Halman",            "Tim",       "Halman"),
    _RosterEntry("Barbara Adams",         "Barbara",   "Adams"),
    _RosterEntry("Kent Smith",            "Kent",      "Smith"),
    _RosterEntry("John White",            "John",      "White"),
    _RosterEntry("Greg Morrow",           "Greg",      "Morrow"),
    _RosterEntry("Jill Balser",           "Jill",      "Balser"),
    _RosterEntry("John A. MacDonald",     "John",      "MacDonald"),
    _RosterEntry("Melissa Sheehy-Richard","Melissa",   "Sheehy-Richard"),
    _RosterEntry("Allan MacMaster",       "Allan",     "MacMaster"),
    _RosterEntry("John Lohr",             "John",      "Lohr"),
    _RosterEntry("Chris Palmer",          "Chris",     "Palmer"),
    _RosterEntry("Susan Corkum-Greek",    "Susan",     "Corkum-Greek"),
    _RosterEntry("Becky Druhan",          "Becky",     "Druhan"),
    _RosterEntry("Kim Masland",           "Kim",       "Masland"),
    _RosterEntry("Trevor Boudreau",       "Trevor",    "Boudreau"),
    _RosterEntry("Steve Craig",           "Steve",     "Craig"),
    _RosterEntry("Brad Johns",            "Brad",      "Johns"),
    _RosterEntry("Nolan Young",           "Nolan",     "Young"),
    _RosterEntry("Dave Ritcey",           "Dave",      "Ritcey"),
    _RosterEntry("Keith Bain",            "Keith",     "Bain"),
    _RosterEntry("Brian Wong",            "Brian",     "Wong"),
    _RosterEntry("Karla MacFarlane",      "Karla",     "MacFarlane",      ended_override=date(2024,  4, 12)),
    _RosterEntry("Marco MacLeod",         "Marco",     "MacLeod",         started_override=date(2024,  5, 21)),
    _RosterEntry("Twila Grosse",          "Twila",     "Grosse",          started_override=date(2023,  8,  8)),
    # Liberal (14-17)
    _RosterEntry("Zach Churchill",        "Zach",      "Churchill"),
    _RosterEntry("Carman Kerr",           "Carman",    "Kerr"),
    _RosterEntry("Kelly Regan",           "Kelly",     "Regan"),
    _RosterEntry("Braedon Clark",         "Braedon",   "Clark"),
    _RosterEntry("Ronnie LeBlanc",        "Ronnie",    "LeBlanc"),
    _RosterEntry("Rafah DiCostanzo",      "Rafah",     "DiCostanzo"),
    _RosterEntry("Lorelei Nicoll",        "Lorelei",   "Nicoll"),
    _RosterEntry("Tony Ince",             "Tony",      "Ince"),
    _RosterEntry("Ali Duale",             "Ali",       "Duale"),
    _RosterEntry("Brendan Maguire",       "Brendan",   "Maguire",         ended_override=date(2024,  2, 22)),
    _RosterEntry("Ben Jessome",           "Ben",       "Jessome"),
    _RosterEntry("Keith Irving",          "Keith",     "Irving"),
    _RosterEntry("Patricia Arab",         "Patricia",  "Arab"),
    _RosterEntry("Derek Mombourquette",   "Derek",     "Mombourquette"),
    _RosterEntry("Iain Rankin",           "Iain",      "Rankin"),
    _RosterEntry("Fred Tilley",           "Fred",      "Tilley",          ended_override=date(2024, 10, 22)),
    _RosterEntry("Angela Simmonds",       "Angela",    "Simmonds",        ended_override=date(2023,  4,  1)),
    # NDP (6)
    _RosterEntry("Claudia Chender",       "Claudia",   "Chender"),
    _RosterEntry("Susan Leblanc",         "Susan",     "Leblanc"),
    _RosterEntry("Gary Burrill",          "Gary",      "Burrill"),
    _RosterEntry("Lisa Lachance",         "Lisa",      "Lachance"),
    _RosterEntry("Suzy Hansen",           "Suzy",      "Hansen"),
    _RosterEntry("Kendra Coombes",        "Kendra",    "Coombes"),
    # Independent
    _RosterEntry("Elizabeth Smith-McCrossin", "Elizabeth", "Smith-McCrossin"),
]


NS_ROSTER: dict[int, list[_RosterEntry]] = {
    62: NS_62L,
    63: NS_63L,
    64: NS_64L,
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


async def ingest_ns_former_mlas(db: Database) -> Stats:
    """Mirror of nb_former_mlas.ingest_nb_former_mlas. Same upsert
    discipline: name-match against existing NS roster first, then
    INSERT new politicians; one politician_terms row per (MLA,
    Assembly), idempotent on (politician_id, started_at, source).
    """
    stats = Stats()
    unique_keys: set[tuple[str, str]] = set()

    for asm_n, entries in NS_ROSTER.items():
        asm_start, asm_end = NS_ASSEMBLY_DATES[asm_n]
        stats.legislatures_processed += 1
        for entry in entries:
            unique_keys.add((
                _strip_accents(entry.first_name).lower(),
                _strip_accents(entry.last_name).lower(),
            ))

            pol = await db.fetchrow(
                """
                SELECT id FROM politicians
                 WHERE level='provincial' AND province_territory='NS'
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
                    f"wikipedia:ns-assembly:"
                    f"{_strip_accents(entry.last_name).lower()}-"
                    f"{_strip_accents(entry.first_name).lower()}"
                )
                row = await db.fetchrow(
                    """
                    INSERT INTO politicians
                        (name, first_name, last_name,
                         level, province_territory,
                         is_active, source_id, social_urls, extras)
                    VALUES ($1, $2, $3, 'provincial', 'NS',
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
                VALUES ($1, 'MLA', 'provincial', 'NS', $2, $3, $4)
                """,
                pol_id, started_at, ended_at, SOURCE_TAG,
            )
            stats.terms_inserted += 1

    stats.unique_mlas = len(unique_keys)
    log.info(
        "ingest_ns_former_mlas: leg=%d unique=%d new=%d matched=%d "
        "terms_inserted=%d terms_skipped=%d",
        stats.legislatures_processed, stats.unique_mlas,
        stats.politicians_inserted, stats.politicians_matched_existing,
        stats.terms_inserted, stats.terms_skipped_existing,
    )
    return stats
