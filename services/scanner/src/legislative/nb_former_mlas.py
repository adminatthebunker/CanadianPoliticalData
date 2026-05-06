"""NB historical-MLA roster (58th-60th Legislatures).

The Legislative Assembly of New Brunswick does not publish a machine-
readable former-members directory; legnb.ca's `/en/members/former-
members` URL 404s and the legacy gnb.ca `/legis/bios/{N}/index-e.asp`
endpoints return 500. The current-roster ingesters (`direct:legnb-ca`
+ `opennorth:new-brunswick-legislature`) only know the sitting 61st
Legislature, so any speech before 2024-10-21 from an MLA who didn't
also win in 2024 stays unattributed.

This module fills the gap with a hand-curated Python literal sourced
from the Wikipedia articles for the 58th, 59th, and 60th Legislatures
(election results + mid-Legislature changes). One ``politician_terms``
row per (MLA, Legislature) with the Legislature's start and end
dates as the term window. Multi-Legislature MLAs end up with multiple
term rows, all attached to the same ``politicians`` row (deduped by
``(first_name, last_name)`` against the existing roster).

Idempotency: politicians are upserted on ``(first_name, last_name)``
match within NB; politician_terms are inserted only when no row exists
for the same ``(politician_id, started_at)`` pair under our source
tag.
"""
from __future__ import annotations

import logging
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from ..db import Database

log = logging.getLogger(__name__)

SOURCE_TAG = "wikipedia:nb-legislature"


# ── Legislature date windows ────────────────────────────────────────
#
# Election dates anchor the Legislature start. End date = the next
# Legislature's election day (when the predecessor's mandate formally
# ends in NB convention). Mid-Legislature events (resignations, by-
# elections, party changes, deaths) are captured per-MLA below.

NB_LEGISLATURE_DATES: dict[int, tuple[date, date]] = {
    58: (date(2014,  9, 22), date(2018,  9, 24)),  # 2014 → 2018 election
    59: (date(2018,  9, 24), date(2020,  9, 14)),  # 2018 → 2020 election
    60: (date(2020,  9, 14), date(2024, 10, 21)),  # 2020 → 2024 election
}


# ── Per-Legislature MLA rosters ─────────────────────────────────────
#
# Format: (full_name, first_name, last_name, started_override, ended_override)
# - full_name: as it should appear in `politicians.name` (with diacritics)
# - first_name / last_name: separate fields for FK matching
# - started_override: None = use Legislature start; date = late arrival
#   (by-election, mid-Legislature appointment)
# - ended_override: None = use Legislature end; date = early departure
#   (resignation, death, defeat in by-election)
#
# Sources: Wikipedia "Nth New Brunswick Legislature" articles, cross-
# referenced for spelling variants and accent restoration.

@dataclass
class _RosterEntry:
    full_name: str
    first_name: str
    last_name: str
    started_override: Optional[date] = None
    ended_override: Optional[date] = None


# 58th Legislature (2014-09-22 → 2018-09-24): Liberal majority under Brian Gallant.
NB_58L: list[_RosterEntry] = [
    # Liberal (27 elected, varied to 24)
    _RosterEntry("Denis Landry",       "Denis",       "Landry"),
    _RosterEntry("Brian Kenny",        "Brian",       "Kenny"),
    _RosterEntry("Donald Arseneault",  "Donald",      "Arseneault", ended_override=date(2017, 11, 30)),
    _RosterEntry("Hédard Albert",      "Hédard",      "Albert"),
    _RosterEntry("Andrew Harvey",      "Andrew",      "Harvey"),
    _RosterEntry("John Ames",          "John",        "Ames"),
    _RosterEntry("Roger Melanson",     "Roger",       "Melanson"),
    _RosterEntry("Stephen Horsman",    "Stephen",     "Horsman"),
    _RosterEntry("Rick Doucet",        "Rick",        "Doucet"),
    _RosterEntry("Bertrand LeBlanc",   "Bertrand",    "LeBlanc"),
    _RosterEntry("Benoît Bourque",     "Benoît",      "Bourque"),
    _RosterEntry("Francine Landry",    "Francine",    "Landry"),
    _RosterEntry("Bernard LeBlanc",    "Bernard",     "LeBlanc"),
    _RosterEntry("Bill Fraser",        "Bill",        "Fraser"),
    _RosterEntry("Lisa Harris",        "Lisa",        "Harris"),
    _RosterEntry("Chris Collins",      "Chris",       "Collins",    ended_override=date(2018, 5, 10)),
    _RosterEntry("Monique LeBlanc",    "Monique",     "LeBlanc"),
    _RosterEntry("Cathy Rogers",       "Cathy",       "Rogers"),
    _RosterEntry("Daniel Guitard",     "Daniel",      "Guitard"),
    _RosterEntry("Gilles LePage",      "Gilles",      "LePage"),
    _RosterEntry("Gary Keating",       "Gary",        "Keating",    ended_override=date(2014, 10, 14)),
    _RosterEntry("Ed Doherty",         "Ed",          "Doherty"),
    _RosterEntry("Brian Gallant",      "Brian",       "Gallant"),
    _RosterEntry("Victor Boudreau",    "Victor",      "Boudreau"),
    _RosterEntry("Wilfred Roussel",    "Wilfred",     "Roussel"),
    _RosterEntry("Serge Rousselle",    "Serge",       "Rousselle"),
    _RosterEntry("Chuck Chiasson",     "Chuck",       "Chiasson"),
    # Progressive Conservative (21 elected, varied to 22)
    _RosterEntry("Brian Keirstead",    "Brian",       "Keirstead"),
    _RosterEntry("David Alward",       "David",       "Alward",     ended_override=date(2015, 5, 22)),
    _RosterEntry("Stewart Fairgrieve", "Stewart",     "Fairgrieve", started_override=date(2015, 10, 5)),
    _RosterEntry("Carl Urquhart",      "Carl",        "Urquhart"),
    _RosterEntry("Madeleine Dubé",     "Madeleine",   "Dubé",       ended_override=date(2018, 7, 1)),
    _RosterEntry("Pam Lynch",          "Pam",         "Lynch"),
    _RosterEntry("Brian Macdonald",    "Brian",       "Macdonald"),
    _RosterEntry("Kirk MacDonald",     "Kirk",        "MacDonald"),
    _RosterEntry("Ross Wetmore",       "Ross",        "Wetmore"),
    _RosterEntry("Gary Crossman",      "Gary",        "Crossman"),
    _RosterEntry("Bill Oliver",        "Bill",        "Oliver"),
    _RosterEntry("Ernie Steeves",      "Ernie",       "Steeves"),
    _RosterEntry("Sherry Wilson",      "Sherry",      "Wilson"),
    _RosterEntry("Jeff Carr",          "Jeff",        "Carr"),
    _RosterEntry("Jody Carr",          "Jody",        "Carr"),
    _RosterEntry("Trevor Holder",      "Trevor",      "Holder"),
    _RosterEntry("Blaine Higgs",       "Blaine",      "Higgs"),
    _RosterEntry("Bruce Fitch",        "Bruce",       "Fitch"),
    _RosterEntry("Ted Flemming",       "Ted",         "Flemming"),
    _RosterEntry("Dorothy Shephard",   "Dorothy",     "Shephard"),
    _RosterEntry("Jake Stewart",       "Jake",        "Stewart"),
    _RosterEntry("Bruce Northrup",     "Bruce",       "Northrup"),
    _RosterEntry("Glen Savoie",        "Glen",        "Savoie",     started_override=date(2014, 11, 17)),
    # Green
    _RosterEntry("David Coon",         "David",       "Coon"),
]

# 59th Legislature (2018-09-24 → 2020-09-14): PC minority under Higgs.
NB_59L: list[_RosterEntry] = [
    # Progressive Conservative (22 elected)
    _RosterEntry("Mike Holland",       "Mike",        "Holland"),
    _RosterEntry("Stewart Fairgrieve", "Stewart",     "Fairgrieve"),
    _RosterEntry("Carl Urquhart",      "Carl",        "Urquhart"),
    _RosterEntry("Dominic Cardy",      "Dominic",     "Cardy"),
    _RosterEntry("Andrea Anderson-Mason", "Andrea",   "Anderson-Mason"),
    _RosterEntry("Ross Wetmore",       "Ross",        "Wetmore"),
    _RosterEntry("Gary Crossman",      "Gary",        "Crossman"),
    _RosterEntry("Bill Oliver",        "Bill",        "Oliver"),
    _RosterEntry("Ernie Steeves",      "Ernie",       "Steeves"),
    _RosterEntry("Sherry Wilson",      "Sherry",      "Wilson"),
    _RosterEntry("Jeff Carr",          "Jeff",        "Carr"),
    _RosterEntry("Mary Wilson",        "Mary",        "Wilson"),
    _RosterEntry("Trevor Holder",      "Trevor",      "Holder"),
    _RosterEntry("Blaine Higgs",       "Blaine",      "Higgs"),
    _RosterEntry("Bruce Fitch",        "Bruce",       "Fitch"),
    _RosterEntry("Ted Flemming",       "Ted",         "Flemming"),
    _RosterEntry("Greg Thompson",      "Greg",        "Thompson",   ended_override=date(2019, 9, 10)),
    _RosterEntry("Glen Savoie",        "Glen",        "Savoie"),
    _RosterEntry("Dorothy Shephard",   "Dorothy",     "Shephard"),
    _RosterEntry("Robert Gauvin",      "Robert",      "Gauvin"),  # Changed to Independent 2020-02-14
    _RosterEntry("Jake Stewart",       "Jake",        "Stewart"),
    _RosterEntry("Bruce Northrup",     "Bruce",       "Northrup"),
    # Liberal (21 elected)
    _RosterEntry("Denis Landry",       "Denis",       "Landry"),
    _RosterEntry("Brian Kenny",        "Brian",       "Kenny"),
    _RosterEntry("Guy Arseneault",     "Guy",         "Arseneault"),
    _RosterEntry("Isabelle Thériault", "Isabelle",    "Thériault"),
    _RosterEntry("Andrew Harvey",      "Andrew",      "Harvey"),
    _RosterEntry("Roger Melanson",     "Roger",       "Melanson"),
    _RosterEntry("Jean-Claude D'Amours", "Jean-Claude", "D'Amours"),
    _RosterEntry("Stephen Horsman",    "Stephen",     "Horsman"),
    _RosterEntry("Benoît Bourque",     "Benoît",      "Bourque"),
    _RosterEntry("Francine Landry",    "Francine",    "Landry"),
    _RosterEntry("Lisa Harris",        "Lisa",        "Harris"),
    _RosterEntry("Rob McKee",          "Rob",         "McKee"),
    _RosterEntry("Monique LeBlanc",    "Monique",     "LeBlanc"),
    _RosterEntry("Cathy Rogers",       "Cathy",       "Rogers"),
    _RosterEntry("Daniel Guitard",     "Daniel",      "Guitard"),
    _RosterEntry("Gilles LePage",      "Gilles",      "LePage"),
    _RosterEntry("Gerry Lowe",         "Gerry",       "Lowe"),
    _RosterEntry("Brian Gallant",      "Brian",       "Gallant",    ended_override=date(2019, 10, 7)),
    _RosterEntry("Jacques LeBlanc",    "Jacques",     "LeBlanc"),
    _RosterEntry("Keith Chiasson",     "Keith",       "Chiasson"),
    _RosterEntry("Chuck Chiasson",     "Chuck",       "Chiasson"),
    # Green (3)
    _RosterEntry("David Coon",         "David",       "Coon"),
    _RosterEntry("Kevin Arseneau",     "Kevin",       "Arseneau"),
    _RosterEntry("Megan Mitton",       "Megan",       "Mitton"),
    # People's Alliance (3)
    _RosterEntry("Kris Austin",        "Kris",        "Austin"),
    _RosterEntry("Rick DeSaulniers",   "Rick",        "DeSaulniers"),
    _RosterEntry("Michelle Conroy",    "Michelle",    "Conroy"),
]

# 60th Legislature (2020-09-14 → 2024-10-21): PC majority under Higgs.
NB_60L: list[_RosterEntry] = [
    # Progressive Conservative (26-28 across mid-Leg shifts)
    _RosterEntry("Blaine Higgs",       "Blaine",      "Higgs"),
    _RosterEntry("Mike Holland",       "Mike",        "Holland"),
    _RosterEntry("Bill Hogan",         "Bill",        "Hogan"),
    _RosterEntry("Margaret Johnson",   "Margaret",    "Johnson"),
    _RosterEntry("Richard Ames",       "Richard",     "Ames"),
    _RosterEntry("Jill Green",         "Jill",        "Green"),
    _RosterEntry("Dominic Cardy",      "Dominic",     "Cardy"),
    _RosterEntry("Ryan Cullins",       "Ryan",        "Cullins"),
    _RosterEntry("Andrea Anderson-Mason", "Andrea",   "Anderson-Mason"),
    _RosterEntry("Ross Wetmore",       "Ross",        "Wetmore"),
    _RosterEntry("Gary Crossman",      "Gary",        "Crossman"),
    _RosterEntry("Bill Oliver",        "Bill",        "Oliver"),
    _RosterEntry("Bruce Fitch",        "Bruce",       "Fitch"),
    _RosterEntry("Ted Flemming",       "Ted",         "Flemming"),
    _RosterEntry("Kathy Bockus",       "Kathy",       "Bockus"),
    _RosterEntry("Glen Savoie",        "Glen",        "Savoie"),
    _RosterEntry("Arlene Dunn",        "Arlene",      "Dunn"),
    _RosterEntry("Dorothy Shephard",   "Dorothy",     "Shephard"),
    _RosterEntry("Jake Stewart",       "Jake",        "Stewart"),
    _RosterEntry("Michael Dawson",     "Michael",     "Dawson",     started_override=date(2022, 6, 20)),
    _RosterEntry("Tammy Scott-Wallace", "Tammy",      "Scott-Wallace"),
    _RosterEntry("Ernie Steeves",      "Ernie",       "Steeves"),
    _RosterEntry("Daniel Allain",      "Daniel",      "Allain"),
    _RosterEntry("Greg Turner",        "Greg",        "Turner"),
    _RosterEntry("Sherry Wilson",      "Sherry",      "Wilson"),
    _RosterEntry("Jeff Carr",          "Jeff",        "Carr"),
    _RosterEntry("Mary Wilson",        "Mary",        "Wilson"),
    _RosterEntry("Trevor Holder",      "Trevor",      "Holder"),
    # Liberal (17 elected)
    _RosterEntry("Susan Holt",         "Susan",       "Holt"),
    _RosterEntry("Denis Landry",       "Denis",       "Landry"),
    _RosterEntry("René Legacy",        "René",        "Legacy"),
    _RosterEntry("Guy Arseneault",     "Guy",         "Arseneault"),
    _RosterEntry("Isabelle Thériault", "Isabelle",    "Thériault"),
    _RosterEntry("Roger Melanson",     "Roger",       "Melanson"),
    _RosterEntry("Richard Losier",     "Richard",     "Losier",     started_override=date(2023, 6, 19)),
    _RosterEntry("Jean-Claude D'Amours", "Jean-Claude", "D'Amours"),
    _RosterEntry("Francine Landry",    "Francine",    "Landry"),
    _RosterEntry("Benoît Bourque",     "Benoît",      "Bourque"),
    _RosterEntry("Lisa Harris",        "Lisa",        "Harris"),
    _RosterEntry("Rob McKee",          "Rob",         "McKee"),
    _RosterEntry("Robert Gauvin",      "Robert",      "Gauvin"),
    _RosterEntry("Jacques LeBlanc",    "Jacques",     "LeBlanc"),
    _RosterEntry("Eric Mallet",        "Eric",        "Mallet"),
    _RosterEntry("Keith Chiasson",     "Keith",       "Chiasson"),
    _RosterEntry("Chuck Chiasson",     "Chuck",       "Chiasson"),
    _RosterEntry("Daniel Guitard",     "Daniel",      "Guitard"),
    _RosterEntry("Marco LeBlanc",      "Marco",       "LeBlanc",    started_override=date(2023, 6, 19)),
    _RosterEntry("Gilles LePage",      "Gilles",      "LePage"),
    # Green (3)
    _RosterEntry("David Coon",         "David",       "Coon"),
    _RosterEntry("Kevin Arseneau",     "Kevin",       "Arseneau"),
    _RosterEntry("Megan Mitton",       "Megan",       "Mitton"),
    # People's Alliance (2)
    _RosterEntry("Kris Austin",        "Kris",        "Austin"),
    _RosterEntry("Michelle Conroy",    "Michelle",    "Conroy"),
]


NB_ROSTER: dict[int, list[_RosterEntry]] = {
    58: NB_58L,
    59: NB_59L,
    60: NB_60L,
}


# ── Stats / ingest ──────────────────────────────────────────────────


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


async def ingest_nb_former_mlas(db: Database) -> Stats:
    """Ingest NB roster from the curated NB_ROSTER literal.

    For each (Legislature, entry):
      1. Look up an existing NB politician by lowercased+accent-stripped
         (first_name, last_name). If found, attach a term to that row.
      2. If not found, INSERT a new ``politicians`` row with NB_ROSTER
         as source.
      3. Upsert ``politician_terms`` for the (politician, started_at)
         pair — skip if exists, otherwise insert with the Legislature's
         start/end dates (overridden by per-entry started/ended dates
         when present).
    """
    stats = Stats()
    unique_keys: set[tuple[str, str]] = set()

    for leg_n, entries in NB_ROSTER.items():
        leg_start, leg_end = NB_LEGISLATURE_DATES[leg_n]
        stats.legislatures_processed += 1
        for entry in entries:
            unique_keys.add((
                _strip_accents(entry.first_name).lower(),
                _strip_accents(entry.last_name).lower(),
            ))

            # 1. Find or create politician
            pol = await db.fetchrow(
                """
                SELECT id FROM politicians
                 WHERE level='provincial' AND province_territory='NB'
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
                    f"wikipedia:nb-legislature:"
                    f"{_strip_accents(entry.last_name).lower()}-"
                    f"{_strip_accents(entry.first_name).lower()}"
                )
                row = await db.fetchrow(
                    """
                    INSERT INTO politicians
                        (name, first_name, last_name,
                         level, province_territory,
                         is_active, source_id, social_urls, extras)
                    VALUES ($1, $2, $3, 'provincial', 'NB',
                            false, $4, '{}'::jsonb, '{}'::jsonb)
                    RETURNING id
                    """,
                    entry.full_name, entry.first_name, entry.last_name,
                    source_id,
                )
                pol_id = row["id"]
                stats.politicians_inserted += 1

            # 2. Upsert politician_terms row
            started_at = entry.started_override or leg_start
            ended_at = entry.ended_override or leg_end
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
                VALUES ($1, 'MLA', 'provincial', 'NB', $2, $3, $4)
                """,
                pol_id, started_at, ended_at, SOURCE_TAG,
            )
            stats.terms_inserted += 1

    stats.unique_mlas = len(unique_keys)
    log.info(
        "ingest_nb_former_mlas: leg=%d unique=%d new=%d matched=%d "
        "terms_inserted=%d terms_skipped=%d",
        stats.legislatures_processed, stats.unique_mlas,
        stats.politicians_inserted, stats.politicians_matched_existing,
        stats.terms_inserted, stats.terms_skipped_existing,
    )
    return stats
