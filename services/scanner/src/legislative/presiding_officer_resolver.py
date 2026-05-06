"""Resolve politician_id on presiding-officer (Speaker) turns in
provincial Hansard by date-ranged lookup into `politician_terms`.

Problem: rows like `speaker_role='The Speaker'` with `politician_id=NULL`
don't carry a name in the speaker line — only the role title. The actual
person holding the Speaker's chair on any given sitting day is knowable
from the Legislature's public records, but it's external data we have
to seed.

Approach:
  1. A small hand-curated roster (SPEAKER_ROSTER) lists every Speaker of
     the House for each jurisdiction with exact start/end dates. The
     roster is intentionally **data-only** — if a Speaker changes, we
     amend this file, re-run, and the backfill is idempotent.
  2. `ensure_speaker_politicians` inserts any roster name that's not
     already in `politicians` as a minimal row (level=provincial,
     is_active=false). Historical Speakers (retired, deceased) are
     otherwise absent from the current-roster-only politician tables.
  3. `ensure_speaker_terms` upserts rows into `politician_terms` with
     `office='Speaker'` and the roster's start/end dates. The `source`
     column is set to 'presiding_officer_seed' so re-runs can delete
     and re-insert cleanly (no unique constraint on politician_terms).
  4. `resolve_speakers` walks `speeches` WHERE `politician_id IS NULL`
     AND the role/name line indicates "The Speaker", joins against
     `politician_terms` by date range, and updates speeches +
     speech_chunks in one pass.

Scope: Tier 1 only (the Speaker). Deputy Speaker, Acting Speaker, and
Committee-of-the-Whole Chair are separate workstreams — the Speaker
role is single-person-at-a-time and fully date-determinable, which the
other roles are not.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Optional

from ..db import Database

log = logging.getLogger(__name__)


# ── Speaker rosters ─────────────────────────────────────────────────
#
# Dates sourced from Wikipedia + official Legislature pages. End date
# of one Speaker is the start date of the next — the brief gaps between
# sessions contain no Hansard speeches. `None` ended_at means still
# serving.
#
# Adding a new Speaker:
#   1. Append a tuple to the relevant list.
#   2. Update the previous Speaker's ended_at to the new one's start.
#   3. Re-run `resolve-presiding-speakers` — it's idempotent.

@dataclass(frozen=True)
class SpeakerTerm:
    full_name: str      # as it should appear in `politicians.name`
    first_name: str
    last_name: str
    started_at: date
    ended_at: Optional[date]


SPEAKER_ROSTER: dict[str, list[SpeakerTerm]] = {
    # Alberta: Speakers #11 through current (covers Hansard corpus
    # from 2000-02-17). Source: Wikipedia "Speaker of the Legislative
    # Assembly of Alberta" + assembly.ab.ca.
    "AB": [
        # First-names below match the assembly.ab.ca member-info pages
        # (legal names, not colloquial). The `_find_politician_id`
        # fallback handles legacy rows with colloquial first names; the
        # legal form is what `ingest-ab-former-mlas` writes to the DB.
        SpeakerTerm("Kenneth R. Kowalski", "Kenneth", "Kowalski",  date(1997, 4, 14), date(2012, 5, 23)),
        SpeakerTerm("Gene Zwozdesky",      "Gene",    "Zwozdesky", date(2012, 5, 23), date(2015, 6, 11)),
        SpeakerTerm("Robert E. Wanner",    "Robert",  "Wanner",    date(2015, 6, 11), date(2019, 5, 20)),
        SpeakerTerm("Nathan Cooper",       "Nathan",  "Cooper",    date(2019, 5, 21), date(2025, 5, 13)),
        SpeakerTerm("Ric McIver",          "Ric",     "McIver",    date(2025, 5, 13), None),
    ],
    # British Columbia: Speakers spanning P29 (1969) through current,
    # covering the entire Hansard corpus we ingest (P29-P43). Sources:
    # Wikipedia "Speaker of the Legislative Assembly of British Columbia",
    # per-parliament Wikipedia articles, and 41st Parliament of BC.
    # The 41st Parliament had three Speakers: Thomson resigned after
    # one week (June 22–29, 2017); the chair sat vacant through summer
    # recess until Plecas was acclaimed September 8, 2017.
    #
    # Pre-2005 dates are year-only on Wikipedia — boundaries below use
    # parliament-transition dates from BC_PARLIAMENT_DATES (election
    # day) plus Jan 1 of within-parliament transition years. The date-
    # windowed resolver tolerates this approximation: BC sittings
    # cluster Spring+Fall, and any speech given on a transition day
    # itself attributes to the new Speaker (start <= d < end).
    #
    # Names match the politicians.name strings produced by
    # ingest-bc-former-mlas (Wikipedia-canonical full names): "Stephen
    # Rogers" appears in DB as "Charles Stephen Rogers" because his
    # full Wikipedia article title uses the legal first name.
    "BC": [
        SpeakerTerm("William Harvey Murray",   "William",  "Murray",    date(1969,  8, 27), date(1972,  8, 30)),  # P29
        SpeakerTerm("Gordon Dowding",          "Gordon",   "Dowding",   date(1972,  8, 30), date(1975, 12, 11)),  # P30
        SpeakerTerm("Dean Edward Smith",       "Dean",     "Smith",     date(1975, 12, 11), date(1979,  5, 10)),  # P31 — "Ed Smith" on WP
        SpeakerTerm("Harvey Schroeder",        "Harvey",   "Schroeder", date(1979,  5, 10), date(1983,  5,  5)),  # P32
        SpeakerTerm("Kenneth Walter Davidson", "Kenneth",  "Davidson",  date(1983,  5,  5), date(1986, 10, 22)),  # P33 — "Walter Davidson" on WP
        SpeakerTerm("John Douglas Reynolds",   "John",     "Reynolds",  date(1986, 10, 22), date(1990,  1,  1)),  # P34a
        SpeakerTerm("Charles Stephen Rogers",  "Charles",  "Rogers",    date(1990,  1,  1), date(1991, 10, 17)),  # P34b — "Stephen Rogers" on WP
        SpeakerTerm("Joan Sawicki",            "Joan",     "Sawicki",   date(1991, 10, 17), date(1994,  1,  1)),  # P35a
        SpeakerTerm("Emery Barnes",            "Emery",    "Barnes",    date(1994,  1,  1), date(1996,  5, 28)),  # P35b
        SpeakerTerm("Dale Lovick",             "Dale",     "Lovick",    date(1996,  5, 28), date(1998,  1,  1)),  # P36a
        SpeakerTerm("Gretchen Mann Brewin",    "Gretchen", "Brewin",    date(1998,  1,  1), date(2000,  1,  1)),  # P36b — "Gretchen Brewin" on WP
        SpeakerTerm("Bill Hartley",            "Bill",     "Hartley",   date(2000,  1,  1), date(2001,  5, 16)),  # P36c
        SpeakerTerm("Claude Richmond",         "Claude",   "Richmond",  date(2001,  5, 16), date(2005,  5, 17)),  # P37
        SpeakerTerm("Bill Barisoff",           "Bill",     "Barisoff",  date(2005,  5, 17), date(2013,  5, 14)),  # P38-P39
        SpeakerTerm("Linda Reid",              "Linda",    "Reid",      date(2013,  5, 14), date(2017,  6, 22)),  # P40
        SpeakerTerm("Steve Thomson",           "Steve",    "Thomson",   date(2017,  6, 22), date(2017,  6, 29)),  # P41 (1 week)
        SpeakerTerm("Darryl Plecas",           "Darryl",   "Plecas",    date(2017,  9,  8), date(2020, 12,  7)),  # P41
        SpeakerTerm("Raj Chouhan",             "Raj",      "Chouhan",   date(2020, 12,  7), None),                # P42-P43
    ],
    # Quebec: Presidents of the Assemblée nationale. "Le Président" /
    # "La Présidente" is the QC equivalent of "The Speaker". Roster
    # covers current 43rd legislature plus historical sessions back to
    # the 38th (2007+) — the range Wayback CDX surfaces transcript URLs
    # for. Earlier sessions would need additional roster entries + a
    # historical MNA backfill to be worth resolving.
    # Source: Wikipedia "Président de l'Assemblée nationale du Québec"
    # + assnat.qc.ca historical records.
    "QC": [
        SpeakerTerm("Michel Bissonnet",  "Michel",   "Bissonnet", date(2003,  5, 13), date(2008,  4,  8)),
        SpeakerTerm("Yvon Vallières",    "Yvon",     "Vallières", date(2008,  4,  8), date(2011,  4,  5)),
        SpeakerTerm("Jacques Chagnon",   "Jacques",  "Chagnon",   date(2011,  4,  5), date(2018, 10,  1)),
        SpeakerTerm("François Paradis",  "François", "Paradis",   date(2018, 11, 28), date(2022, 11, 29)),
        SpeakerTerm("Nathalie Roy",      "Nathalie", "Roy",       date(2022, 11, 29), None),
    ],
    # Manitoba: covers the 37th Legislature (1999-2003) through the
    # current 43rd Legislature, aligned with the Hansard backfill
    # depth on gov.mb.ca (URL pattern holds to 1958 but the 2000→
    # present ingest draws the line at Leg 37). Transition dates
    # are election-boundary approximations — Speaker elections
    # typically happen on the first sitting day of a new
    # legislature, so month precision is sufficient for the date-
    # windowed resolver.
    # Source: Wikipedia "Speaker of the Legislative Assembly of
    # Manitoba" + gov.mb.ca/legislature/members.
    "MB": [
        SpeakerTerm("George Hickes",    "George",  "Hickes",    date(1999, 10,  6), date(2012, 11, 20)),
        SpeakerTerm("Daryl Reid",       "Daryl",   "Reid",      date(2012, 11, 20), date(2016,  5, 16)),
        SpeakerTerm("Myrna Driedger",   "Myrna",   "Driedger",  date(2016,  5, 16), date(2023, 10,  3)),
        SpeakerTerm("Tom Lindsey",      "Tom",     "Lindsey",   date(2023, 11, 21), None),
    ],
    # New Brunswick: covers Leg 58-61 (digital Hansard depth on
    # legnb.ca starts at 58/3, 2016). Chris Collins was removed from
    # the Liberal caucus in 2018 but remained Speaker; the role was
    # effectively vacant between the 58th's summer 2018 recess and
    # Guitard's election on 2018-11-20. "Mr. Speaker" / "Madam
    # Speaker" in NB Hansard resolves via this roster + the spoken_at
    # date.
    # Source: legnb.ca /en/members/speakers + Wikipedia
    # "Speaker of the New Brunswick Legislative Assembly".
    "NB": [
        SpeakerTerm("Chris Collins",    "Chris",    "Collins",  date(2014, 10, 23), date(2018,  8, 29)),
        SpeakerTerm("Daniel Guitard",   "Daniel",   "Guitard",  date(2018, 11, 20), date(2020,  8, 17)),
        SpeakerTerm("Bill Oliver",      "Bill",     "Oliver",   date(2020, 11, 17), date(2024,  8, 14)),
        SpeakerTerm("Francine Landry",  "Francine", "Landry",   date(2024, 11, 19), None),
    ],
    # Nova Scotia: covers General Assemblies 58 (1999-2003) through
    # 65 (current). Sittings list the Speaker directly in a
    # <p class="hsd_center">Hon. Danielle Barkhouse</p> block at the
    # top of each day's Hansard (modern markup, 62-1 onward). Legacy-
    # markup sittings (58-1 through 61-5) use plaintext "MR. SPEAKER:"
    # lines, which still resolve via the date-ranged term lookup here
    # regardless of markup shape.
    # Sources: Wikipedia "Speaker of the Nova Scotia House of Assembly"
    # + nslegislature.ca historical records.
    "NS": [
        SpeakerTerm("Ronald Russell",     "Ronald",   "Russell",   date(1999,  9,  9), date(2003,  7,  8)),
        SpeakerTerm("Murray Scott",       "Murray",   "Scott",     date(2003,  9,  9), date(2006,  9, 14)),
        SpeakerTerm("Cecil Clarke",       "Cecil",    "Clarke",    date(2006,  9, 14), date(2008,  1, 16)),
        SpeakerTerm("Alfie MacLeod",      "Alfie",    "MacLeod",   date(2008,  1, 16), date(2009,  6,  9)),
        SpeakerTerm("Charlie Parker",     "Charlie",  "Parker",    date(2009,  6,  9), date(2009,  9, 23)),
        SpeakerTerm("Gordie Gosse",       "Gordie",   "Gosse",     date(2009,  9, 23), date(2013, 10, 24)),
        SpeakerTerm("Kevin Murphy",       "Kevin",    "Murphy",    date(2013, 10, 24), date(2021,  8, 19)),
        SpeakerTerm("Keith Bain",         "Keith",    "Bain",      date(2021,  8, 19), date(2024, 12,  9)),
        SpeakerTerm("Danielle Barkhouse", "Danielle", "Barkhouse", date(2024, 12, 10), None),
    ],
    # Newfoundland & Labrador: covers GA 48–51 (2015+), the range the
    # Hansard backfill is expected to reach. Dates are year-boundary
    # approximations — assembly.nl.ca's FormerSpeakers.aspx only
    # publishes year ranges ("2021–2025 Derek Bennett"), and transitions
    # typically happen at the start of a new GA so month precision
    # rarely matters for date-windowed resolution. Transition dates
    # align with known GA dissolutions / elections:
    #   - 2017-11-15: Osborne → Trimper (mid-GA 48, Trimper elected
    #                  Speaker after Osborne was appointed minister).
    #   - 2019-05-31: Trimper → Reid (post-2019 election, GA 49).
    #   - 2021-04-15: Reid → Bennett (post-2021 election, GA 50 opening).
    #   - 2025-11-03: Bennett → Lane (verified from assembly.nl.ca).
    # NL Hansard emits "SPEAKER:" (modern, Word-exported) and
    # "MR. SPEAKER:" (legacy, FrontPage-era); both normalise to
    # "The Speaker".
    "NL": [
        SpeakerTerm("Tom Osborne",      "Tom",      "Osborne",  date(2015, 12,  7), date(2017, 11, 15)),
        SpeakerTerm("Perry Trimper",    "Perry",    "Trimper",  date(2017, 11, 15), date(2019,  5, 31)),
        SpeakerTerm("Scott Reid",       "Scott",    "Reid",     date(2019,  5, 31), date(2021,  4, 15)),
        SpeakerTerm("Derek Bennett",    "Derek",    "Bennett",  date(2021,  4, 15), date(2025, 11,  3)),
        SpeakerTerm("Paul Lane",        "Paul",     "Lane",     date(2025, 11,  3), None),
    ],
    # Ontario: parliament 44 onwards. Modern ON Hansard markup includes
    # the actual Speaker's name inline as parens — `<strong>The Speaker
    # (Hon. Donna Skelly):</strong>` — so the on_hansard parser resolves
    # most presiding-officer turns directly via the parens-name path.
    # This roster only matters for the rarer bare "The Speaker:" rows.
    # Initial scope: parliament 44 only. Backfill earlier Speakers as
    # historical-Hansard ingest expands.
    "ON": [
        SpeakerTerm("Donna Skelly",     "Donna",    "Skelly",   date(2025, 4, 15), None),
    ],
    # Northwest Territories: covers the 13th Assembly (1995) through
    # current 20th Assembly. NT runs consensus government — Speakers
    # are independents (no party). The Hansard backfill covers 2002+
    # but the roster goes a bit earlier in case archived transcripts
    # surface. Year-only dates from Wikipedia "Speaker of the
    # Northwest Territories Legislative Assembly"; transitions land at
    # Assembly boundaries except Krutko → Delorey mid-15th Assembly.
    "NT": [
        SpeakerTerm("Samuel Gargan",       "Samuel",     "Gargan",   date(1995,  1,  1), date(2000,  1,  1)),  # 13th
        SpeakerTerm("Tony Whitford",       "Tony",       "Whitford", date(2000,  1,  1), date(2003,  1,  1)),  # 14th
        SpeakerTerm("David Krutko",        "David",      "Krutko",   date(2003,  1,  1), date(2004,  1,  1)),  # 15th
        SpeakerTerm("Paul Delorey",        "Paul",       "Delorey",  date(2004,  1,  1), date(2011,  1,  1)),  # 15th-16th
        SpeakerTerm("Jackie Jacobson",     "Jackie",     "Jacobson", date(2011,  1,  1), date(2015,  1,  1)),  # 17th
        SpeakerTerm("Jackson Lafferty",    "Jackson",    "Lafferty", date(2015,  1,  1), date(2019,  1,  1)),  # 18th
        SpeakerTerm("Frederick Blake Jr.", "Frederick",  "Blake",    date(2019,  1,  1), date(2023, 12,  7)),  # 19th
        SpeakerTerm("Shane Thompson",      "Shane",      "Thompson", date(2023, 12,  7), None),                # 20th
    ],
    # Saskatchewan: Speakers since the 23rd Legislative Assembly (1995-).
    # Pre-30th-leg Hansard uses role-only "The Speaker" labels — this
    # roster provides date-windowed FK attribution. Year-precision dates
    # for older entries (Wikipedia gives only year-level transitions);
    # 29L+30L use first-sitting-day precision for accuracy on ingested
    # speeches. Source: Wikipedia "Speaker of the Legislative Assembly
    # of Saskatchewan" + cross-checked against politicians.extras
    # ->>'cabinet_role'='Speaker' from the speaker-index ingester.
    "SK": [
        SpeakerTerm("Glenn Hagel",     "Glenn",   "Hagel",      date(1996,  1,  1), date(1999,  1,  1)),  # 23L
        SpeakerTerm("Ron Osika",       "Ron",     "Osika",      date(1999,  1,  1), date(2001,  1,  1)),  # 24L
        SpeakerTerm("Myron Kowalsky",  "Myron",   "Kowalsky",   date(2001,  1,  1), date(2007,  1,  1)),  # 25L
        SpeakerTerm("Don Toth",        "Don",     "Toth",       date(2007,  1,  1), date(2011,  1,  1)),  # 26L
        SpeakerTerm("Dan D'Autremont", "Dan",     "D'Autremont", date(2011,  1,  1), date(2016,  1,  1)),  # 27L
        SpeakerTerm("Corey Tochor",    "Corey",   "Tochor",     date(2016,  1,  1), date(2018,  1,  1)),  # 28L (1st)
        SpeakerTerm("Mark Docherty",   "Mark",    "Docherty",   date(2018,  1,  1), date(2020, 12,  7)),  # 28L (2nd)
        SpeakerTerm("Randy Weekes",    "Randy",   "Weekes",     date(2020, 12,  7), date(2024, 11, 25)),  # 29L
        SpeakerTerm("Todd Goudy",      "Todd",    "Goudy",      date(2024, 11, 25), None),                # 30L
    ],
}


SOURCE_TAG = "presiding_officer_seed"


# ── Deputy-presiding rosters (Tier-2 Pass 2) ────────────────────────
#
# Same shape as SPEAKER_ROSTER but for Deputy Speaker / Vice-Président
# entries. Used by `inline_presiding_resolver` to disambiguate parens-
# extracted surnames when multiple candidates share a last name — only
# the candidate who held a presiding role on the speech date wins.
#
# Unlike SPEAKER_ROSTER, windows here may overlap by design: jurisdictions
# such as QC have multiple simultaneous Vice-Présidents (1er / 2e / 3e),
# all collapsed by the parser into a single role string. The narrowing
# step in inline_presiding_resolver only needs *set membership* — "was
# this politician among the active deputy presiding officers on date d?"
# — so overlap is the right shape, not a problem to deduplicate.
#
# Office is the English canonical 'Deputy Speaker' regardless of source-
# language label, matching how 'Speaker' covers QC's "Le Président".

DEPUTY_PRESIDING_ROSTER: dict[str, list[SpeakerTerm]] = {
    # Quebec: Vice-Présidents (1er / 2e / 3e) of the Assemblée nationale,
    # 37L (2003-06-04) onward — matches SPEAKER_ROSTER["QC"] floor.
    # Source: French Wikipedia "Vice-président de l'Assemblée nationale
    # du Québec". Pre-2003 entries deferred (existing QC Hansard ingest
    # is sparse below the 37L floor).
    "QC": [
        # 37L (2003-06-04 → 2007-05-08) — Charest I
        SpeakerTerm("Christos Sirros",       "Christos",  "Sirros",      date(2003,  6,  4), date(2004,  6, 17)),
        SpeakerTerm("William Cusano",        "William",   "Cusano",      date(2004, 10, 19), date(2007,  5,  8)),
        SpeakerTerm("Diane Leblanc",         "Diane",     "Leblanc",     date(2003,  6,  4), date(2007,  5,  8)),
        SpeakerTerm("François Gendron",      "François",  "Gendron",     date(2003,  6,  4), date(2007,  5,  8)),
        # 38L+39L (2007-05-08 → 2011/2012) — Charest II minority + III majority
        SpeakerTerm("Jacques Chagnon",       "Jacques",   "Chagnon",     date(2007,  5,  8), date(2011,  4,  5)),
        SpeakerTerm("Fatima Houda-Pepin",    "Fatima",    "Houda-Pepin", date(2007,  5,  8), date(2012, 10, 30)),
        SpeakerTerm("François Gendron",      "François",  "Gendron",     date(2007,  5,  8), date(2012,  9, 19)),
        SpeakerTerm("François Ouimet",       "François",  "Ouimet",      date(2011,  4,  5), date(2012, 10, 30)),
        # 40L (2012-10-30 → 2014-05-20) — Marois minority (PQ)
        SpeakerTerm("Carole Poirier",        "Carole",    "Poirier",     date(2012, 10, 30), date(2014,  5, 20)),
        SpeakerTerm("Claude Cousineau",      "Claude",    "Cousineau",   date(2012, 10, 30), date(2014,  5, 20)),
        SpeakerTerm("François Ouimet",       "François",  "Ouimet",      date(2012, 10, 30), date(2014,  5, 20)),
        # 41L (2014-05-20 → 2018-11-27) — Couillard majority
        SpeakerTerm("François Ouimet",       "François",  "Ouimet",      date(2014,  5, 20), date(2018, 11, 27)),
        SpeakerTerm("Maryse Gaudreault",     "Maryse",    "Gaudreault",  date(2014,  5, 20), date(2018, 11, 27)),
        SpeakerTerm("François Gendron",      "François",  "Gendron",     date(2014,  5, 20), date(2018, 11, 27)),
        # 42L (2018-11-27 → 2022-11-29) — Legault I (CAQ majority)
        SpeakerTerm("Marc Picard",           "Marc",      "Picard",      date(2018, 11, 27), date(2022, 11, 29)),
        SpeakerTerm("Maryse Gaudreault",     "Maryse",    "Gaudreault",  date(2018, 11, 27), date(2022, 11, 29)),
        SpeakerTerm("François Gendron",      "François",  "Gendron",     date(2018, 11, 27), date(2022, 11, 29)),
        # 43L (2022-11-29 → present) — Legault II (CAQ majority).
        # Sylvain Lévesque was 2e VP from session opening; he resigned
        # 2024-11-06 after an ethics-commissioner finding (Le Devoir,
        # Radio-Canada). Sylvie D'Amours was elected to the same seat
        # 2024-11-07. Picard / Soucy / Benjamin run open-ended — Pass-2
        # narrowing keys on set-membership of active deputies, not on
        # which numbered VP rank, so 1er/2e/3e drift is harmless.
        SpeakerTerm("Marc Picard",           "Marc",      "Picard",      date(2022, 11, 29), None),
        SpeakerTerm("Chantal Soucy",         "Chantal",   "Soucy",       date(2022, 11, 29), None),
        SpeakerTerm("Frantz Benjamin",       "Frantz",    "Benjamin",    date(2022, 11, 29), None),
        SpeakerTerm("Sylvain Lévesque",      "Sylvain",   "Lévesque",    date(2022, 11, 29), date(2024, 11,  6)),
        SpeakerTerm("Sylvie D'Amours",       "Sylvie",    "D'Amours",    date(2024, 11,  7), None),
    ],
}


DEPUTY_SOURCE_TAG = "deputy_presiding_seed"


# ── Seeding politicians + politician_terms ─────────────────────────

async def _find_politician_id(
    db: Database, *, province: str, first_name: str, last_name: str,
) -> Optional[str]:
    """Case-insensitive lookup by (first_name, last_name) within a province.

    Falls back to last-name-only when the exact match misses *and* the
    last-name match is unique within the province. This handles the
    colloquial-vs-legal first-name drift that bit AB pre-2026-04-23
    (roster says "Ken Kowalski"; DB has "Kenneth R. Kowalski"). Logs
    fallback hits so first-name drift surfaces on review.
    """
    row = await db.fetchrow(
        """
        SELECT id::text AS id
          FROM politicians
         WHERE level = 'provincial'
           AND province_territory = $1
           AND lower(first_name) = lower($2)
           AND lower(last_name)  = lower($3)
         LIMIT 1
        """,
        province, first_name, last_name,
    )
    if row is not None:
        return row["id"]

    # Last-name-only fallback: accept only when exactly one provincial
    # politician has this surname. Anything ambiguous → return None so
    # the caller falls through to seeding a stub (existing behaviour).
    fallback_rows = await db.fetch(
        """
        SELECT id::text AS id, name, first_name, last_name
          FROM politicians
         WHERE level = 'provincial'
           AND province_territory = $1
           AND lower(last_name) = lower($2)
        """,
        province, last_name,
    )
    if len(fallback_rows) == 1:
        log.warning(
            "presiding_resolver: first-name fallback hit for "
            "province=%s roster=(%s, %s) → DB=(%s) [%s]",
            province, first_name, last_name,
            fallback_rows[0]["name"], fallback_rows[0]["id"],
        )
        return fallback_rows[0]["id"]
    return None


async def _insert_minimal_politician(
    db: Database, *, province: str, term: SpeakerTerm,
) -> str:
    """Insert a retired Speaker as a minimal politicians row and return UUID.

    Matches the field set used by `scripts/bc-enrich-historical-mlas.py`:
    name + first_name + last_name + level + province_territory +
    is_active=false, with empty jsonb for social_urls/extras and a
    `source_id` tag so operators can trace origin.
    """
    row = await db.fetchrow(
        """
        INSERT INTO politicians (
            name, first_name, last_name,
            level, province_territory,
            is_active, social_urls, extras, source_id
        )
        VALUES ($1, $2, $3, 'provincial', $4,
                false, '{}'::jsonb, '{}'::jsonb, $5)
        RETURNING id::text AS id
        """,
        term.full_name, term.first_name, term.last_name,
        province,
        f"presiding-officer-seed:{province}:{term.last_name.lower()}",
    )
    log.info("inserted %s (%s) → politicians.%s", term.full_name, province, row["id"])
    return row["id"]


async def ensure_speaker_politicians(
    db: Database, province: str,
) -> dict[str, str]:
    """Ensure every Speaker in the roster exists in `politicians`.
    Returns {full_name: politician_id}.
    """
    roster = SPEAKER_ROSTER.get(province, [])
    out: dict[str, str] = {}
    inserted = 0
    for term in roster:
        pid = await _find_politician_id(
            db, province=province,
            first_name=term.first_name, last_name=term.last_name,
        )
        if pid is None:
            pid = await _insert_minimal_politician(db, province=province, term=term)
            inserted += 1
        out[term.full_name] = pid
    log.info(
        "ensure_speaker_politicians(%s): roster=%d inserted=%d",
        province, len(roster), inserted,
    )
    return out


async def ensure_speaker_terms(
    db: Database, province: str, *, name_to_id: dict[str, str],
) -> int:
    """Upsert Speaker-office rows into `politician_terms` for this province.

    Idempotent: deletes any rows with our source tag for this
    province+level+office='Speaker' first, then re-inserts. This avoids
    needing a unique constraint migration for a small, curated dataset.
    """
    await db.execute(
        """
        DELETE FROM politician_terms
         WHERE level = 'provincial'
           AND province_territory = $1
           AND office = 'Speaker'
           AND source = $2
        """,
        province, SOURCE_TAG,
    )
    roster = SPEAKER_ROSTER.get(province, [])
    inserted = 0
    for term in roster:
        pid = name_to_id[term.full_name]
        await db.execute(
            """
            INSERT INTO politician_terms (
                politician_id, office, level, province_territory,
                started_at, ended_at, source
            )
            VALUES ($1::uuid, 'Speaker', 'provincial', $2, $3, $4, $5)
            """,
            pid,
            province,
            term.started_at, term.ended_at,
            SOURCE_TAG,
        )
        inserted += 1
    log.info("ensure_speaker_terms(%s): %d rows", province, inserted)
    return inserted


async def ensure_deputy_presiding_politicians(
    db: Database, province: str,
) -> dict[str, str]:
    """Like `ensure_speaker_politicians`, but for the Deputy Speaker /
    Vice-Président roster (Tier-2 Pass 2). Returns {full_name: politician_id}.
    Idempotent: existing politicians are reused; absent ones inserted as
    minimal stubs with `is_active=false`.
    """
    roster = DEPUTY_PRESIDING_ROSTER.get(province, [])
    out: dict[str, str] = {}
    inserted = 0
    for term in roster:
        if term.full_name in out:
            continue
        pid = await _find_politician_id(
            db, province=province,
            first_name=term.first_name, last_name=term.last_name,
        )
        if pid is None:
            pid = await _insert_minimal_politician(db, province=province, term=term)
            inserted += 1
        out[term.full_name] = pid
    log.info(
        "ensure_deputy_presiding_politicians(%s): roster=%d inserted=%d",
        province, len(roster), inserted,
    )
    return out


async def ensure_deputy_presiding_terms(
    db: Database, province: str, *, name_to_id: dict[str, str],
) -> int:
    """Upsert Deputy-Speaker rows into `politician_terms` for this province.

    Idempotent: deletes any rows tagged with DEPUTY_SOURCE_TAG for this
    province+level+office='Deputy Speaker' first, then re-inserts.
    Distinct from SOURCE_TAG so re-runs don't churn the main Speaker rows.
    """
    await db.execute(
        """
        DELETE FROM politician_terms
         WHERE level = 'provincial'
           AND province_territory = $1
           AND office = 'Deputy Speaker'
           AND source = $2
        """,
        province, DEPUTY_SOURCE_TAG,
    )
    roster = DEPUTY_PRESIDING_ROSTER.get(province, [])
    inserted = 0
    for term in roster:
        pid = name_to_id[term.full_name]
        await db.execute(
            """
            INSERT INTO politician_terms (
                politician_id, office, level, province_territory,
                started_at, ended_at, source
            )
            VALUES ($1::uuid, 'Deputy Speaker', 'provincial', $2, $3, $4, $5)
            """,
            pid,
            province,
            term.started_at, term.ended_at,
            DEPUTY_SOURCE_TAG,
        )
        inserted += 1
    log.info("ensure_deputy_presiding_terms(%s): %d rows", province, inserted)
    return inserted


# ── Resolution ──────────────────────────────────────────────────────

@dataclass
class ResolveStats:
    scanned: int = 0
    resolved: int = 0
    no_term_match: int = 0
    chunks_updated: int = 0


# Which `speeches.speaker_role` values indicate the presiding Speaker for
# each jurisdiction. Tier 1 only — Deputy Speaker / Chair are NOT covered.
# Parser modules must emit these exact strings; if you add a new
# jurisdiction, check which canonical role(s) its parser emits for the
# main Speaker chair and add them here.
_SPEAKER_ROLE_BY_PROVINCE: dict[str, tuple[str, ...]] = {
    "AB": ("The Speaker", "Speaker"),
    "BC": ("The Speaker", "Speaker"),
    # Quebec: Journal des débats labels the Speaker "Le Président" /
    # "La Présidente"; the qc_hansard parser normalises both to
    # "Le Président". "Le Vice-Président" (Deputy) is Tier 2 and
    # intentionally excluded.
    "QC": ("Le Président",),
    # Manitoba: the mb_hansard parser normalises "Madam Speaker",
    # "Mister Speaker", and "The Speaker" all to "The Speaker".
    "MB": ("The Speaker",),
    # New Brunswick: nb_hansard parser matches English role lines
    # verbatim ("Mr. Speaker", "Madam Speaker"). "The Speaker" appears
    # as a rarer alternative form. The French label "Le président :"
    # is treated as body text by the parser (bilingual duplicate).
    "NB": ("Mr. Speaker", "Madam Speaker", "Madame Speaker", "The Speaker"),
    # Nova Scotia: ns_hansard parser normalises every presiding-officer
    # anchor form ("THE SPEAKER", "MADAM SPEAKER", "MR. SPEAKER") to
    # the canonical "The Speaker" role string.
    "NS": ("The Speaker",),
    # Newfoundland & Labrador: nl_hansard parser normalises both
    # "SPEAKER:" (modern Word-exported era) and "MR. SPEAKER:" (legacy
    # FrontPage era) to the canonical "The Speaker" role.
    "NL": ("The Speaker",),
    # Ontario: on_hansard parser normalises "The Speaker", "Madam
    # Speaker", "Mr. Speaker", and "Mister Speaker" to "The Speaker".
    # Acting / Deputy Speaker rows (Tier 2) are intentionally excluded
    # — they're rare in modern transcripts and the parens-name path
    # resolves them directly when the markup includes the name inline.
    "ON": ("The Speaker",),
    # Saskatchewan: sk_hansard parser emits 'speaker' (lowercase) for
    # the main Speaker chair — both name-bearing ("Speaker Goudy", 30L)
    # and role-only ("The Speaker", 29L). 'deputy_speaker' / 'chair' /
    # 'deputy_chair' are deliberately excluded — they're separate
    # rotating-role people whose attribution requires its own roster.
    "SK": ("speaker",),
}

# Back-compat default for any province without an explicit mapping.
_DEFAULT_SPEAKER_ROLE_VALUES: tuple[str, ...] = ("The Speaker", "Speaker")

# Speaker_name_raw fallbacks for rows where `speaker_role` is NULL but the
# raw attribution line clearly indicates the Speaker. AB Hansard occasionally
# stores "Mr. Speaker" directly in speaker_name_raw for older eras
# (~40 rows observed). These are added to the OR-match regardless of
# province — they're English-only and harmless on QC rows.
_SPEAKER_NAME_PATTERNS = (
    "Mr. Speaker", "Madam Speaker", "Madame Speaker",
    "The Speaker",
)


def _speaker_role_values(province: str) -> tuple[str, ...]:
    return _SPEAKER_ROLE_BY_PROVINCE.get(province, _DEFAULT_SPEAKER_ROLE_VALUES)


# ── Role-only presiding rosters (Tier-2 Pass 3) ─────────────────────
#
# Some provincial Hansards (notably AB) emit pure role-only speaker
# labels for non-Speaker presiding officers — e.g., `The Deputy Speaker`
# with no inline name, where Pass 1 (parens-name) and Pass 2 (parens-
# name + date narrowing) can't apply. AB alone has ~60K such rows
# across `The Deputy Speaker` / `The Deputy Chair` / `The Acting
# Speaker` / `The Chair`.
#
# Pass 3 covers the **single-person date-windowed** subset only —
# offices held by one named MLA per Legislature (Deputy Speaker, Deputy
# Chair of Committees). Rotating roles (Acting Speaker, generic Chair)
# need a different mechanism (same-document name propagation or
# external rotation source) and are out of scope here.
#
# Structure: `ROLE_ONLY_PRESIDING_ROSTER[province][office]` → list of
# SpeakerTerm. `ROLE_ONLY_OFFICE_MAP[province][speaker_role]` → office,
# linking the parser's role string back to the office key.

ROLE_ONLY_PRESIDING_ROSTER: dict[str, dict[str, list[SpeakerTerm]]] = {
    # Alberta: Deputy Speaker and Chair of Committees + Deputy Chair of
    # Committees. Both are single-person date-determined roles per AB
    # Standing Orders. Dates mined from `politicians.extras.ab_member_info.offices`
    # (the assembly.ab.ca structured member records ingested by enrich-
    # ab-mlas) and cross-checked against in-Hansard election announcements.
    # Two short Deputy-Chair gaps acknowledged where the role was vacant
    # between cabinet-promotion of the incumbent and election of a
    # successor (2016-02-08→2016-03-09, 2022-06-27→2022-11-30).
    "AB": {
        "Deputy Speaker": [
            SpeakerTerm("Donald A. Tannas", "Donald A.", "Tannas",  date(1993,  8, 30), date(2005,  3,  1)),  # 23L+24L+25L
            SpeakerTerm("Richard Marz",     "Richard",   "Marz",    date(2005,  3,  1), date(2008,  4, 14)),  # 26L
            SpeakerTerm("Wayne Cao",        "Wayne",     "Cao",     date(2008,  4, 14), date(2012,  5, 23)),  # 27L
            SpeakerTerm("George Rogers",    "George",    "Rogers",  date(2012,  5, 23), date(2015,  6, 11)),  # 28L
            SpeakerTerm("Debbie Jabbour",   "Debbie",    "Jabbour", date(2015,  6, 11), date(2019,  5, 21)),  # 29L
            SpeakerTerm("Angela Pitt",      "Angela",    "Pitt",    date(2019,  5, 21), None),                # 30L+31L
        ],
        "Deputy Chair of Committees": [
            SpeakerTerm("Judith D. Gordon",     "Judith",    "Gordon",    date(1997,  4, 14), date(2001,  3, 11)),  # 24L
            SpeakerTerm("Shiraz Shariff",       "Shiraz",    "Shariff",   date(2001,  4,  9), date(2008,  3,  2)),  # 25L+26L
            SpeakerTerm("Leonard W. Mitzel",    "Leonard",   "Mitzel",    date(2008,  4, 14), date(2011, 10, 26)),  # 27L early
            SpeakerTerm("Gene Zwozdesky",       "Gene",      "Zwozdesky", date(2011, 11, 21), date(2012,  4, 22)),  # 27L late (became Speaker for 28L)
            SpeakerTerm("Mary Anne Jablonski",  "Mary Anne", "Jablonski", date(2012,  5, 23), date(2015,  5,  4)),  # 28L
            SpeakerTerm("Richard Feehan",       "Richard",   "Feehan",    date(2015,  6, 11), date(2016,  2,  8)),  # 29L early (then cabinet)
            SpeakerTerm("Heather Sweet",        "Heather",   "Sweet",     date(2016,  3,  9), date(2019,  4, 15)),  # 29L late
            SpeakerTerm("Nicholas Milliken",    "Nicholas",  "Milliken",  date(2019,  5, 21), date(2022,  6, 27)),  # 30L early (then cabinet)
            SpeakerTerm("Roger Reid",           "Roger",     "Reid",      date(2022, 11, 30), date(2023,  5, 28)),  # 30L late
            SpeakerTerm("Glenn van Dijken",     "Glenn",     "van Dijken", date(2023,  6, 20), None),               # 31L
        ],
    },
    # British Columbia: Deputy Speaker, single-person date-determined.
    # BC's chamber parser tags these as bare `Deputy Speaker` (no "The"
    # prefix). Coverage is 39L (2009) → 43L (current); 38L (2008, ~115
    # rows) and 40L (2013-2017, ~700 rows) gaps acknowledged where the
    # Deputy Speaker holder couldn't be confirmed from public sources.
    # Sourced from 41st/42nd/43rd Parliament Wikipedia pages plus search
    # confirmation for Linda Reid 2009 and Mable Elmore 2025-03 appointment.
    "BC": {
        "Deputy Speaker": [
            SpeakerTerm("Linda Reid",              "Linda",            "Reid",    date(2009,  8, 25), date(2013,  6, 26)),  # 39L
            SpeakerTerm("Raj Chouhan",             "Raj",              "Chouhan", date(2017,  6, 22), date(2020, 12,  7)),  # 41L
            SpeakerTerm("Spencer Chandra Herbert", "Spencer Chandra",  "Herbert", date(2020, 12,  7), date(2024, 10, 19)),  # 42L
            SpeakerTerm("Mable Elmore",            "Mable",            "Elmore",  date(2025,  3,  1), None),                 # 43L
        ],
    },
    # Manitoba: Deputy Speaker. The MB chamber parser only emits the
    # role-only `The Deputy Speaker` shape for the 43rd Legislature
    # (2023+); pre-43L Deputy Speaker turns came with inline names
    # (`Madam Deputy Speaker (NAME)` / `Mr. Deputy Speaker (NAME)`)
    # already caught by Pass 1. Single-entry roster covers the entire
    # 43L role-only bucket (~1,027 rows). Source: confirmed via in-
    # Hansard attributed turns + media reporting on the appointment.
    "MB": {
        "Deputy Speaker": [
            SpeakerTerm("Tyler Blashko", "Tyler", "Blashko", date(2023, 11, 21), None),  # 43L
        ],
    },
}

# Per-province map from `speeches.speaker_role` → `politician_terms.office`
# so the resolver knows which office to look up for each role token.
ROLE_ONLY_OFFICE_MAP: dict[str, dict[str, str]] = {
    "AB": {
        "The Deputy Speaker": "Deputy Speaker",
        "The Deputy Chair":   "Deputy Chair of Committees",
    },
    "BC": {
        # BC parser emits bare "Deputy Speaker" (no "The" prefix), unlike AB.
        "Deputy Speaker": "Deputy Speaker",
    },
    "MB": {
        # MB parser emits "The Deputy Speaker" (43L+ only).
        "The Deputy Speaker": "Deputy Speaker",
    },
}

ROLE_ONLY_SOURCE_TAG = "role_only_presiding_seed"


async def ensure_role_only_presiding_politicians(
    db: Database, province: str,
) -> dict[str, str]:
    """Ensure every politician in `ROLE_ONLY_PRESIDING_ROSTER[province]`
    exists in `politicians`, across all offices for the province.
    Returns {full_name: politician_id}.
    """
    by_office = ROLE_ONLY_PRESIDING_ROSTER.get(province, {})
    out: dict[str, str] = {}
    inserted = 0
    for terms in by_office.values():
        for term in terms:
            if term.full_name in out:
                continue
            pid = await _find_politician_id(
                db, province=province,
                first_name=term.first_name, last_name=term.last_name,
            )
            if pid is None:
                pid = await _insert_minimal_politician(db, province=province, term=term)
                inserted += 1
            out[term.full_name] = pid
    log.info(
        "ensure_role_only_presiding_politicians(%s): unique=%d inserted=%d",
        province, len(out), inserted,
    )
    return out


async def ensure_role_only_presiding_terms(
    db: Database, province: str, *, name_to_id: dict[str, str],
) -> int:
    """Upsert role-only presiding rows into `politician_terms`. One
    `politician_terms` row per (politician, office) span. DELETE-then-
    INSERT keyed on ROLE_ONLY_SOURCE_TAG keeps the audit trail distinct.
    """
    await db.execute(
        """
        DELETE FROM politician_terms
         WHERE level = 'provincial'
           AND province_territory = $1
           AND source = $2
        """,
        province, ROLE_ONLY_SOURCE_TAG,
    )
    by_office = ROLE_ONLY_PRESIDING_ROSTER.get(province, {})
    inserted = 0
    for office, terms in by_office.items():
        for term in terms:
            pid = name_to_id[term.full_name]
            await db.execute(
                """
                INSERT INTO politician_terms (
                    politician_id, office, level, province_territory,
                    started_at, ended_at, source
                )
                VALUES ($1::uuid, $2, 'provincial', $3, $4, $5, $6)
                """,
                pid, office, province,
                term.started_at, term.ended_at,
                ROLE_ONLY_SOURCE_TAG,
            )
            inserted += 1
    log.info("ensure_role_only_presiding_terms(%s): %d rows", province, inserted)
    return inserted


async def resolve_speakers(
    db: Database, province: str, *, limit: Optional[int] = None,
) -> ResolveStats:
    """Update speeches (and chunks) where speaker_role indicates 'The Speaker'
    and politician_id is NULL, by looking up the active Speaker term for
    the spoken_at date.

    Updates speech_chunks.politician_id as well so retrieval-side joins
    stay consistent (chunks created pre-resolution held the NULL copy).
    """
    stats = ResolveStats()

    where = """
        s.level = 'provincial'
        AND s.province_territory = $1
        AND s.politician_id IS NULL
        AND (
            s.speaker_role = ANY($2::text[])
            OR (
                (s.speaker_role IS NULL OR s.speaker_role = '')
                AND s.speaker_name_raw = ANY($3::text[])
            )
        )
    """
    sql = f"""
        SELECT s.id::text AS id,
               s.spoken_at::date AS spoken_date
          FROM speeches s
         WHERE {where}
    """
    params: list = [province, list(_speaker_role_values(province)), list(_SPEAKER_NAME_PATTERNS)]
    if limit is not None:
        sql += f" LIMIT {int(limit)}"

    rows = await db.fetch(sql, *params)
    stats.scanned = len(rows)

    # Load Speaker terms once. For Tier 1 there are <=10 rows per province.
    term_rows = await db.fetch(
        """
        SELECT politician_id::text AS politician_id,
               started_at::date    AS started_at,
               ended_at::date      AS ended_at
          FROM politician_terms
         WHERE level = 'provincial'
           AND province_territory = $1
           AND office = 'Speaker'
           AND source = $2
         ORDER BY started_at
        """,
        province, SOURCE_TAG,
    )

    def find_speaker_for(d: date) -> Optional[str]:
        for t in term_rows:
            started = t["started_at"]
            ended = t["ended_at"]
            if d >= started and (ended is None or d < ended):
                return t["politician_id"]
        return None

    # Bucket updates by politician_id for bulk updates.
    by_politician: dict[str, list[str]] = {}
    for r in rows:
        d = r["spoken_date"]
        if d is None:
            stats.no_term_match += 1
            continue
        pid = find_speaker_for(d)
        if pid is None:
            stats.no_term_match += 1
            continue
        by_politician.setdefault(pid, []).append(r["id"])

    # Flush in 5k-row batches — passing 100k+ UUIDs to ANY($1::uuid[]) in
    # a single statement times out asyncpg. Confidence 0.9 (below full-name
    # match's 1.0, above ambiguous surname's 0.5) — we're certain of the
    # date window but not of any per-speech semantic check.
    BATCH = 5000
    for pid, speech_ids in by_politician.items():
        for i in range(0, len(speech_ids), BATCH):
            batch = speech_ids[i : i + BATCH]
            await db.execute(
                """
                UPDATE speeches
                   SET politician_id = $1::uuid,
                       confidence    = GREATEST(confidence, 0.9),
                       updated_at    = now()
                 WHERE id = ANY($2::uuid[])
                   AND politician_id IS NULL
                """,
                pid, batch,
            )
            result = await db.execute(
                """
                UPDATE speech_chunks
                   SET politician_id = $1::uuid
                 WHERE speech_id = ANY($2::uuid[])
                   AND politician_id IS DISTINCT FROM $1::uuid
                """,
                pid, batch,
            )
            stats.resolved += len(batch)
            # asyncpg returns a command tag like "UPDATE 123" — parse the count.
            try:
                stats.chunks_updated += int(result.split()[-1])
            except (ValueError, AttributeError):
                pass

    # Final reconcile: catch any speech_chunks whose politician_id drifted
    # from the parent speech. This guards against timeout-aborted prior
    # runs where the speech UPDATE committed but the matching chunk
    # UPDATE never did — on re-run, the speech is no longer NULL so it
    # falls out of `rows` above, and the chunk desync persists. One
    # targeted sweep closes the loop regardless of run history.
    reconcile = await db.execute(
        """
        UPDATE speech_chunks sc
           SET politician_id = s.politician_id
          FROM speeches s
         WHERE sc.speech_id = s.id
           AND s.level = 'provincial'
           AND s.province_territory = $1
           AND s.speaker_role = ANY($2::text[])
           AND s.politician_id IS NOT NULL
           AND sc.politician_id IS DISTINCT FROM s.politician_id
        """,
        province, list(_speaker_role_values(province)),
    )
    try:
        stats.chunks_updated += int(reconcile.split()[-1])
    except (ValueError, AttributeError):
        pass

    log.info(
        "resolve_speakers(%s): scanned=%d resolved=%d no_term_match=%d chunks_updated=%d",
        province, stats.scanned, stats.resolved, stats.no_term_match, stats.chunks_updated,
    )
    return stats


async def resolve_role_only_presiding(
    db: Database, province: str, *, limit: Optional[int] = None,
) -> ResolveStats:
    """Tier-2 Pass 3 — resolve role-only presiding labels (e.g., AB's
    `The Deputy Speaker` with no inline name) by looking up the active
    holder of the corresponding office on the speech date.

    Iterates over every (speaker_role → office) pair in
    ROLE_ONLY_OFFICE_MAP[province], joining `politician_terms` where
    source = ROLE_ONLY_SOURCE_TAG. Confidence 0.85 (single-person
    date-determined attribution; below the chamber parser's name-bearing
    primary path).
    """
    stats = ResolveStats()

    role_map = ROLE_ONLY_OFFICE_MAP.get(province, {})
    if not role_map:
        log.info("resolve_role_only_presiding(%s): no role map configured", province)
        return stats

    # Load all role-only terms for the province in one query, indexed by office.
    term_rows = await db.fetch(
        """
        SELECT office,
               politician_id::text AS politician_id,
               started_at::date    AS started_at,
               ended_at::date      AS ended_at
          FROM politician_terms
         WHERE level = 'provincial'
           AND province_territory = $1
           AND source = $2
         ORDER BY office, started_at
        """,
        province, ROLE_ONLY_SOURCE_TAG,
    )
    terms_by_office: dict[str, list[dict]] = {}
    for r in term_rows:
        terms_by_office.setdefault(r["office"], []).append(dict(r))

    def find_holder_for(office: str, d: date) -> Optional[str]:
        for t in terms_by_office.get(office, []):
            started = t["started_at"]
            ended = t["ended_at"]
            if d >= started and (ended is None or d < ended):
                return t["politician_id"]
        return None

    by_politician: dict[str, list[str]] = {}

    for speaker_role, office in role_map.items():
        if office not in terms_by_office:
            continue
        sql = """
            SELECT s.id::text AS id,
                   s.spoken_at::date AS spoken_date
              FROM speeches s
             WHERE s.level = 'provincial'
               AND s.province_territory = $1
               AND s.politician_id IS NULL
               AND s.speaker_role = $2
        """
        params: list = [province, speaker_role]
        if limit is not None:
            sql += f" LIMIT {int(limit)}"
        rows = await db.fetch(sql, *params)
        stats.scanned += len(rows)
        for r in rows:
            d = r["spoken_date"]
            if d is None:
                stats.no_term_match += 1
                continue
            pid = find_holder_for(office, d)
            if pid is None:
                stats.no_term_match += 1
                continue
            by_politician.setdefault(pid, []).append(r["id"])

    BATCH = 5000
    for pid, speech_ids in by_politician.items():
        for i in range(0, len(speech_ids), BATCH):
            batch = speech_ids[i : i + BATCH]
            await db.execute(
                """
                UPDATE speeches
                   SET politician_id = $1::uuid,
                       confidence    = GREATEST(confidence, 0.85),
                       updated_at    = now()
                 WHERE id = ANY($2::uuid[])
                   AND politician_id IS NULL
                """,
                pid, batch,
            )
            result = await db.execute(
                """
                UPDATE speech_chunks
                   SET politician_id = $1::uuid
                 WHERE speech_id = ANY($2::uuid[])
                   AND politician_id IS DISTINCT FROM $1::uuid
                """,
                pid, batch,
            )
            stats.resolved += len(batch)
            try:
                stats.chunks_updated += int(result.split()[-1])
            except (ValueError, AttributeError):
                pass

    log.info(
        "resolve_role_only_presiding(%s): scanned=%d resolved=%d "
        "no_term_match=%d chunks_updated=%d",
        province, stats.scanned, stats.resolved,
        stats.no_term_match, stats.chunks_updated,
    )
    return stats


async def seed_and_resolve(
    db: Database, province: str, *, limit: Optional[int] = None,
) -> dict:
    """End-to-end convenience: ensure politicians + terms, then resolve.

    Idempotent. Safe to re-run after adding a new Speaker row to
    SPEAKER_ROSTER — the backfill picks up the change.
    """
    name_to_id = await ensure_speaker_politicians(db, province)
    terms_count = await ensure_speaker_terms(db, province, name_to_id=name_to_id)
    stats = await resolve_speakers(db, province, limit=limit)
    return {
        "province": province,
        "roster": len(name_to_id),
        "terms": terms_count,
        "scanned": stats.scanned,
        "resolved": stats.resolved,
        "no_term_match": stats.no_term_match,
        "chunks_updated": stats.chunks_updated,
    }
