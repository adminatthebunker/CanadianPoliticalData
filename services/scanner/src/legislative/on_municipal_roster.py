"""Ontario municipal roster from AMO's election-results API.

★ WHAT THIS SOURCE ACTUALLY IS
──────────────────────────────
The Association of Municipalities of Ontario runs one site per election cycle:

    https://elections2018.amo.on.ca      https://elections2022.amo.on.ca
    https://elections2026.amo.on.ca

each exposing the same unauthenticated shape:

    /api/public/Municipalities        -> 444 rows (urlId, name, frenchName,
                                        electionResultsAvailable)
    /api/public/municipality/<urlId>  -> tier, population, isWard, turnout,
                                        members[] {name, position, positionWard,
                                                   votes, votePercent,
                                                   incumbency, elected}

⛔ `members[]` IS NOT A ROSTER. It is the CANDIDATE list, and only becomes a
roster once `elected` is populated. Toronto's 2026 row carries 243 members for a
26-seat council, six of them running for mayor, every one `elected: false`.
Filter on `elected` or you will ingest everyone who filed papers.

⚠ `urlId` IS stable across cycles (Ottawa is 19441 on both the 2022 and 2026
sites) but `position` IS NOT: 2022 encodes Councillor=1/Mayor=6 while 2026
encodes 0/5. Key on the `positionWard` TEXT, never on the numeric code.

⛔ AND THE OBVIOUS USE OF THIS SOURCE IS A TRAP
──────────────────────────────────────────────
"Our Ontario roster is frozen, AMO has the 2022 result, ingest it" is wrong, and
measurably so. A general election result is an ELECTION-NIGHT SNAPSHOT; it knows
nothing about the four years of by-elections, resignations and deaths that
follow. Measured 2026-08-28 against what we hold:

    toronto    we hold Olivia Chow, Parthi Kandavel, Rachel Chernos Lin
               (2023 by-elections). AMO 2022 still says John Tory, Gary
               Crawford, Jaye Robinson. OUR DATA IS NEWER.
    hamilton   identical, 16 of 16.
    brampton   we hold Bowman / Whillans / Dhillon, none of whom won in 2022.
               OUR DATA IS A 2018-2022 ROSTER.
    kitchener  same shape — Gazzola / Galloway-Sealock / Marsh.

So the retired mirror's Ontario roster is INCONSISTENTLY VINTAGED, and a blanket
ingest in either direction corrupts half of it. Applying 2022 wholesale would
have reverted Toronto's mayor to John Tory — a confident error replacing correct
data, which is the exact failure this programme keeps finding.

Hence: comparison is the default and writing is the exception. `--apply` is
allowed without argument only for the CURRENT cycle, because a general election
genuinely does replace every seat at once; for a superseded cycle it demands the
operator name the councils, after reading the diff.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

import httpx

from ..db import Database

SOURCE_PREFIX = "amo-on"
REQUEST_TIMEOUT = 45
HEADERS = {
    "User-Agent": "SovereignWatch/1.0 (Canadian Political Data; admin@thebunkerops.ca)",
    "Accept": "application/json",
}

AMO_HOSTS = {
    2018: "elections2018.amo.on.ca",
    2022: "elections2022.amo.on.ca",
    2026: "elections2026.amo.on.ca",
}

# Ontario municipal general elections: fourth Monday of October, every 4 years.
ELECTION_DATES = {
    2018: date(2018, 10, 22),
    2022: date(2022, 10, 24),
    2026: date(2026, 10, 26),
}

# ⛔ Keyed on AMO's urlId, never on name. Ontario reuses municipality names
# across tiers — `Hamilton, Township of` is 10173 in Northumberland County while
# `Hamilton, City of` is 19430 — so a name match silently grabs the wrong one.
# Same hazard for Kingston, Norwich and Lincoln.
#
# `council` must match the middle field of the existing source_id
# (`opennorth:<council>:<slug>`), because that is the key every downstream join
# groups on: reattach-municipal-roster, the sentinel's detached-council check,
# and the frozen-roster report all use split_part(source_id, ':', 2).
TIER1: dict[int, tuple[str, str, str]] = {
    # urlId: (council slug, boundary source_set, expected AMO name)
    15614: ("toronto-city-council", "toronto-wards", "Toronto, City of"),
    19441: ("ottawa-city-council", "ottawa-wards", "Ottawa, City of"),
    10469: ("mississauga-city-council", "mississauga-wards", "Mississauga, City of"),
    10108: ("brampton-city-council", "brampton-wards", "Brampton, City of"),
    19430: ("hamilton-city-council", "hamilton-wards", "Hamilton, City of"),
    10401: ("london-city-council", "london-wards", "London, City of"),
    10428: ("markham-city-council", "markham-wards", "Markham, City of"),
    10424: ("vaughan-city-council", "vaughan-wards", "Vaughan, City of"),
    10375: ("kitchener-city-council", "kitchener-wards", "Kitchener, City of"),
    10824: ("windsor-city-council", "windsor-wards", "Windsor, City of"),
    19426: ("greater-sudbury-city-council", "greater-sudbury-wards", "Greater Sudbury, City of"),
    10367: ("kingston-city-council", "kingston-wards", "Kingston, City of"),
    10579: ("oshawa-city-council", "oshawa-wards", "Oshawa, City of"),
    10128: ("burlington-city-council", "burlington-wards", "Burlington, City of"),
}


async def verify_mapping(client: httpx.AsyncClient, host: str) -> list[str]:
    """Assert every hardcoded urlId still names the municipality we think.

    ⛔ THIS GUARD EXISTS BECAUSE THE AUTHOR TRIPPED THE VERY TRAP DOCUMENTED
    ABOVE. Eight of the fourteen ids in the first draft of TIER1 were wrong, and
    three of them pointed at a REAL BUT DIFFERENT municipality: 10424 is
    Vaughan (written as Markham), 10600 is McDougall (written as Vaughan),
    10125 is Burk's Falls (written as Burlington). None of those would have
    errored. Each would have quietly ingested another council's roster under
    Markham's or Burlington's name.

    A hardcoded id table cannot be trusted on the strength of the comment
    telling you to be careful with it. It has to check itself against the
    publisher, every run, before a single row is read.
    """
    r = await client.get(f"https://{host}/api/public/Municipalities")
    r.raise_for_status()
    by_id = {row["urlId"]: row["name"] for row in r.json()}
    problems: list[str] = []
    for url_id, (council, _set, expected) in sorted(TIER1.items()):
        actual = by_id.get(url_id)
        if actual is None:
            problems.append(f"{council}: urlId {url_id} not in AMO {host}")
        elif actual.strip() != expected:
            problems.append(
                f"{council}: urlId {url_id} is '{actual}', expected '{expected}' "
                f"— the id table is stale or AMO renumbered; REFUSING"
            )
    return problems


# Seats that are city-wide by definition -> the municipality polygon, not a ward.
_AT_LARGE = re.compile(
    r"^(mayor|maire|deputy\s+mayor|head\s+of\s+council|chair|warden)\b", re.I
)


def slugify(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def norm_name(s: str) -> str:
    """Loose key for comparing a person across two publishers.

    ⚠ Deliberately lossy — AMO writes `Matthew Luloff` in 2022 and `Matt Luloff`
    in 2026 for the same person, so this cannot be an identity function. It is
    used for REPORTING a diff, never for deciding to overwrite a row.
    """
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


@dataclass
class Seat:
    name: str
    office: str
    wards: list[int]
    ward_label: Optional[str]
    at_large: bool
    votes: Optional[int]
    acclaimed: bool


def parse_position(position_ward: str) -> tuple[str, list[int], bool]:
    """`positionWard` -> (office, ward numbers, is_at_large).

    ⛔ Four shapes, all real, all seen in production data:

        ' Mayor'
        ' Councillor, Ward 12'
        ' Councillor, Ward 1 Orleans East Cumberland'   <- Ottawa/Kingston put
                                                           the NAME after the
                                                           number, so a rule
                                                           that reads a TRAILING
                                                           number finds none and
                                                           the council reads as
                                                           at-large
        ' Councillor, Ward 3, 4'                        <- Brampton: ONE seat
                                                           covering TWO wards
        ' Councillor (Regional And City), Ward 9, 10'

    So: take the digits that FOLLOW the token `Ward` (optionally
    `Ward District`), and take all of them, not the first.
    """
    raw = (position_ward or "").strip()
    if not raw:
        return ("Councillor", [], False)

    office = re.split(r",\s*Ward\b", raw, maxsplit=1, flags=re.I)[0].strip()
    office = re.sub(r"\s+", " ", office)

    if _AT_LARGE.match(raw):
        return (office or "Mayor", [], True)

    m = re.search(r"\bWard(?:\s+District)?\s+(.+)$", raw, re.I)
    if not m:
        # No ward token at all: `Councillor At Large`, `Regional Councillor`.
        return (office or "Councillor", [], True)

    tail = m.group(1)
    # ⚠ Stop at the first token that is not a number/separator, so Ottawa's
    # `1 Orleans East Cumberland` yields [1] and not a parse of the name.
    nums: list[int] = []
    for tok in re.split(r"[,\s]+", tail):
        if re.fullmatch(r"\d+", tok):
            nums.append(int(tok))
        elif nums:
            break
        elif re.fullmatch(r"[-&]|and", tok, re.I):
            continue
        else:
            break
    return (office or "Councillor", nums, not nums)


def parse_votes(v) -> Optional[int]:
    """`"161,679"` -> 161679; `""` -> None (acclaimed or not yet counted)."""
    s = str(v or "").strip().replace(",", "")
    return int(s) if s.isdigit() else None


def extract_seats(members: list[dict]) -> list[Seat]:
    out: list[Seat] = []
    for m in members:
        if not m.get("elected"):
            continue
        office, wards, at_large = parse_position(m.get("positionWard", ""))
        votes = parse_votes(m.get("votes"))
        out.append(Seat(
            name=(m.get("name") or "").strip(),
            office=office,
            wards=wards,
            ward_label=(m.get("positionWard") or "").strip() or None,
            at_large=at_large,
            votes=votes,
            acclaimed=votes is None,
        ))
    return out


async def fetch_municipality(client: httpx.AsyncClient, host: str, url_id: int) -> dict:
    r = await client.get(f"https://{host}/api/public/municipality/{url_id}")
    r.raise_for_status()
    return r.json()


@dataclass
class CouncilDiff:
    council: str
    url_id: int
    amo_seats: list[Seat]
    held: dict[str, tuple[str, str]]          # norm_name -> (name, office)
    results_available: bool

    @property
    def amo_keys(self) -> set[str]:
        return {norm_name(s.name) for s in self.amo_seats}

    @property
    def only_amo(self) -> list[Seat]:
        h = set(self.held)
        return [s for s in self.amo_seats if norm_name(s.name) not in h]

    @property
    def only_held(self) -> list[tuple[str, str]]:
        a = self.amo_keys
        return [v for k, v in sorted(self.held.items()) if k not in a]

    @property
    def verdict(self) -> str:
        """What the diff MEANS — the whole point of comparing before writing."""
        if not self.results_available:
            return "no results yet"
        if not self.only_amo and not self.only_held:
            return "identical"
        if not self.only_amo:
            return "we hold extra seats — check tiering, not staleness"
        if not self.only_held:
            return "we are missing seats"
        return "diverged — adjudicate per seat"


@dataclass
class RosterStats:
    cycle: int = 0
    councils: int = 0
    seats: int = 0
    identical: int = 0
    diverged: int = 0
    problems: list[str] = field(default_factory=list)


async def compare_on_municipal_roster(
    db: Database, cycle: int = 2026, councils: Optional[list[str]] = None,
) -> tuple[RosterStats, list[CouncilDiff]]:
    """Read-only. Fetch AMO for `cycle` and diff it against what we hold."""
    if cycle not in AMO_HOSTS:
        raise ValueError(f"unknown cycle {cycle}; known: {sorted(AMO_HOSTS)}")
    host = AMO_HOSTS[cycle]
    st = RosterStats(cycle=cycle)
    diffs: list[CouncilDiff] = []

    targets = {
        uid: v for uid, v in TIER1.items()
        if councils is None or v[0] in councils
    }

    held_rows = await db.fetch(
        """
        SELECT split_part(source_id, ':', 2) AS council,
               name, COALESCE(elected_office, '') AS office
          FROM politicians
         WHERE is_active AND level = 'municipal' AND province_territory = 'ON'
           AND source_id LIKE '%:%:%'
        """
    )
    held: dict[str, dict[str, tuple[str, str]]] = {}
    for r in held_rows:
        held.setdefault(r["council"], {})[norm_name(r["name"])] = (r["name"], r["office"])

    async with httpx.AsyncClient(
        headers=HEADERS, timeout=REQUEST_TIMEOUT, follow_redirects=True
    ) as client:
        # ⛔ Verify the id table against the publisher BEFORE reading a single
        # council, and refuse the whole run on any mismatch — not just the bad
        # rows. A stale id does not error, it silently returns another
        # municipality's council. See verify_mapping().
        bad = await verify_mapping(client, host)
        if bad:
            st.problems.extend(bad)
            return st, diffs
        for url_id, (council, _set, _name) in sorted(targets.items(), key=lambda t: t[1][0]):
            try:
                d = await fetch_municipality(client, host, url_id)
            except Exception as exc:
                st.problems.append(f"{council}: fetch failed — {exc}")
                continue
            seats = extract_seats(d.get("members") or [])
            diff = CouncilDiff(
                council=council, url_id=url_id, amo_seats=seats,
                held=held.get(council, {}),
                results_available=bool(seats),
            )
            diffs.append(diff)
            st.councils += 1
            st.seats += len(seats)
            if diff.verdict == "identical":
                st.identical += 1
            elif diff.verdict != "no results yet":
                st.diverged += 1
    return st, diffs
