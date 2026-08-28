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
    # ⛔ BRANCH ORDER IS LOad-BEARING, and the first draft had it wrong.
    # AMO changed its own separator between cycles: 2018 writes
    # `Ward 3 and 4`, 2022 writes `Ward 3, 4`. With `elif nums: break` ahead of
    # the separator test, the word "and" ended the scan and the seat came back
    # covering ward 3 only. Half of Brampton's previous-cycle wards went
    # missing, which made three genuinely STALE seats report as
    # "unknown-holder" — a parser bug wearing the costume of a data question.
    # Separators must be consumed BEFORE the "we already have digits" bail-out;
    # the bail-out is what stops Ottawa's `1 Orleans East Cumberland` from
    # parsing the ward NAME.
    nums: list[int] = []
    for tok in re.split(r"[,\s]+", tail):
        if re.fullmatch(r"\d+", tok):
            nums.append(int(tok))
        elif re.fullmatch(r"[-&/]|and|et", tok, re.I):
            continue
        elif nums:
            break
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


# ── Per-ward comparison ──────────────────────────────────────────────────────
#
# ★ WHY SEAT-ANCHORING, AND WHY IT ALSO FIXES THE NAME MATCHING
# ─────────────────────────────────────────────────────────────
# The first comparison compared SETS OF NAMES per council: everyone AMO lists as
# elected against everyone we hold. That answers "who is on this council?" but
# not "who holds this seat?", and it failed twice in ways that were only visible
# once measured:
#
#   1. A held member absent from cycle C is either a later by-election winner
#      (we are ahead) or an earlier holdover (we are behind), and set membership
#      cannot tell those apart. Neethan Shan sat 2016-2018 and LOST in 2018;
#      set-comparison scored him as post-2022.
#   2. Set comparison forces a STRICT name match, because a loose one across a
#      whole council will collide. Strict then breaks on ordinary variance —
#      AMO 2018 writes `Gurpreet Singh Dhillon`, we hold `Gurpreet Dhillon`, and
#      he was scored post-2022 when he is a 2018 holdover.
#
# Anchoring on the ward fixes both. A ward's candidate pool is one or two
# people, so a LOOSE name match is safe there in a way it never is across a
# council — `Matt` vs `Matthew Luloff` resolves correctly because there is
# nobody else in Ward 1 to confuse him with. And comparing the same seat across
# two cycles distinguishes "we hold the previous cycle's winner" (stale) from
# "we hold somebody neither cycle elected" (a by-election, or pre-2018 residue).
#
# ⚠ The residual ambiguity is honest and is NOT guessed at. With no
# elections2014 API (DNS does not resolve), a holder in neither cycle cannot be
# dated from AMO alone, and politician_terms.started_at cannot break the tie
# either — the Open North ingest stamped it with the INGEST date rather than the
# election date, a defect already recorded in the timeline. Those seats are
# reported as `unknown-holder` and left for a human. After 2026-10-26 the
# ambiguity disappears by construction, because the cycle being compared is then
# the most recent one and there is no "later" to be ahead of.

_STOP_PARTICLES = {"de", "van", "von", "del", "della", "di", "la", "le", "st",
                   "ste", "saint", "mac", "mc", "singh", "kaur", "jr", "sr"}


def name_tokens(n: str) -> list[str]:
    return [t for t in norm_name(n).split() if t]


def loose_same_person(a: str, b: str) -> bool:
    """Is this the same person, judged WITHIN one ward?

    ⛔ Only ever call this seat-anchored. Across a whole council the surname +
    first-initial rule is far too loose; inside a single ward the pool is one or
    two people and it is exactly right.

    Handles, all from real data:
        `Matt Luloff`            vs `Matthew Luloff`          (diminutive)
        `Gurpreet Dhillon`       vs `Gurpreet Singh Dhillon`  (dropped middle)
        `Amanda Yeung Collucci`  vs `Amanda Collucci`         (compound surname)
    """
    ta, tb = name_tokens(a), name_tokens(b)
    if not ta or not tb:
        return False
    if ta == tb:
        return True
    # Surname = last token; particles and patronymics are not surnames on their
    # own, so fall back through them.
    def surname(t: list[str]) -> str:
        for tok in reversed(t):
            if tok not in _STOP_PARTICLES:
                return tok
        return t[-1]
    sa, sb = surname(ta), surname(tb)
    if sa != sb:
        # Compound surname on one side only: `Yeung Collucci` vs `Collucci`.
        if not (sa in tb or sb in ta):
            return False
    # Same surname — now the given name, allowing a diminutive or an initial.
    ga, gb = ta[0], tb[0]
    if ga == gb:
        return True
    if ga.startswith(gb) or gb.startswith(ga):
        return True          # Matt / Matthew
    return ga[0] == gb[0]    # M. / Matthew, inside one ward


def near_same_person(a: str, b: str) -> bool:
    """Same given name, surname differing only by a trailing letter or two.

    ⚠ Deliberately NOT folded into loose_same_person. Kingston's Sydenham seat
    has AMO writing `Conny Glenn` against our `Conny Glen` — almost certainly
    one person and one publisher's typo, but "almost certainly" is not the same
    claim as a match, and quietly upgrading it to `agree` would hide a real
    disagreement if it ever turned out to be two people. It gets its own status
    so a human sees it.
    """
    ta, tb = name_tokens(a), name_tokens(b)
    if not ta or not tb or ta == tb:
        return False
    if ta[0] != tb[0]:
        return False
    sa, sb = ta[-1], tb[-1]
    lo, hi = sorted((sa, sb), key=len)
    return len(lo) >= 4 and hi.startswith(lo) and len(hi) - len(lo) <= 2


@dataclass
class WardVerdict:
    ward: int
    constituency_id: str
    ward_name: str
    amo_now: list[str]
    amo_prev: list[str]
    held: list[str]
    status: str
    # ⛔ Per-SEAT residue, not per-ward. A ward is not one seat everywhere:
    # Brampton elects a city and a regional councillor per ward pair, Oshawa
    # two per ward. With an any-match rule, ward 9 reported `agree` because
    # Harkirat Singh matched — while the second seat we held (Gurpreet
    # Dhillon, the 2018 winner) was stale and invisible. Holding the right
    # person for one seat says nothing about the other.
    unmatched_held: list[str] = field(default_factory=list)
    unmatched_amo: list[str] = field(default_factory=list)

    def line(self) -> str:
        def j(v): return ", ".join(v) if v else "—"
        extra = ""
        if self.unmatched_held or self.unmatched_amo:
            # ⚠ Angle brackets, not square. The console renders through Rich,
            # which parses [...] as a style tag and silently swallows the
            # contents — the unmatched names printed as empty space.
            extra = f"  <ours: {j(self.unmatched_held)} | amo: {j(self.unmatched_amo)}>"
        return (f"ward {self.ward:>3} {self.ward_name[:22]:22s} "
                f"seats={len(self.amo_now)} {self.status}{extra}")


async def ward_index(db: Database, source_set: str) -> dict[int, tuple[str, str]]:
    """ward number -> (constituency_id, ward name), from the boundary table.

    ⚠ `authority_district_id` is the bridge and its FORMAT VARIES by publisher:
    Toronto zero-pads (`09`), Brampton writes `WARD 1`, Kingston and Greater
    Sudbury use bare integers. All 157 tier-1 wards carry one, so this is a
    complete index rather than a best-effort one — but parse it, never compare
    it as a string.

    ⛔ Do NOT derive the number from the slug instead. Kingston's wards are
    NAMED (`kingston-wards/sydenham`), as are Toronto's, so a slug-derived
    number finds nothing for two of the fourteen councils.
    """
    out: dict[int, tuple[str, str]] = {}
    for r in await db.fetch(
        """
        SELECT constituency_id, name, authority_district_id
          FROM constituency_boundaries
         WHERE source_set = $1 AND boundary_kind = 'district'
           AND effective_from <= CURRENT_DATE
           AND (effective_to IS NULL OR effective_to >= CURRENT_DATE)
        """,
        source_set,
    ):
        m = re.search(r"(\d+)", str(r["authority_district_id"] or ""))
        if m:
            out[int(m.group(1))] = (r["constituency_id"], r["name"])
    return out


async def compare_wards(
    db: Database, cycle: int = 2026, councils: Optional[list[str]] = None,
) -> tuple[RosterStats, dict[str, list[WardVerdict]]]:
    """Seat-by-seat diff of AMO against what we hold, with the previous cycle
    as the tie-breaker for who is ahead of whom."""
    prev = max((c for c in AMO_HOSTS if c < cycle), default=None)
    st = RosterStats(cycle=cycle)
    results: dict[str, list[WardVerdict]] = {}

    targets = {uid: v for uid, v in TIER1.items()
               if councils is None or v[0] in councils}

    async with httpx.AsyncClient(
        headers=HEADERS, timeout=REQUEST_TIMEOUT, follow_redirects=True
    ) as client:
        bad = await verify_mapping(client, AMO_HOSTS[cycle])
        if bad:
            st.problems.extend(bad)
            return st, results

        for url_id, (council, source_set, _n) in sorted(
            targets.items(), key=lambda t: t[1][0]
        ):
            try:
                now = extract_seats(
                    (await fetch_municipality(client, AMO_HOSTS[cycle], url_id))
                    .get("members") or [])
                before = extract_seats(
                    (await fetch_municipality(client, AMO_HOSTS[prev], url_id))
                    .get("members") or []) if prev else []
            except Exception as exc:
                st.problems.append(f"{council}: fetch failed — {exc}")
                continue

            idx = await ward_index(db, source_set)
            if not idx:
                st.problems.append(
                    f"{council}: no ward index for {source_set} — cannot compare "
                    f"by seat")
                continue

            held_rows = await db.fetch(
                """
                SELECT p.name, p.constituency_id
                  FROM politicians p
                 WHERE p.is_active AND p.level = 'municipal'
                   AND split_part(p.source_id, ':', 2) = $1
                   AND p.constituency_id IS NOT NULL
                """,
                council,
            )
            held_by_cid: dict[str, list[str]] = {}
            for r in held_rows:
                held_by_cid.setdefault(r["constituency_id"], []).append(r["name"])

            def by_ward(seats: list[Seat]) -> dict[int, list[str]]:
                d: dict[int, list[str]] = {}
                for s in seats:
                    for w in s.wards:          # a seat may cover two wards
                        d.setdefault(w, []).append(s.name)
                return d

            n_by, p_by = by_ward(now), by_ward(before)
            verdicts: list[WardVerdict] = []
            for ward in sorted(idx):
                cid, wname = idx[ward]
                a_now, a_prev = n_by.get(ward, []), p_by.get(ward, [])
                h = held_by_cid.get(cid, [])
                if not a_now and not h:
                    continue

                # Match seat-wise, not ward-wise. Exact/loose first, then the
                # spelling-variant pass, so a typo does not consume a slot a
                # real match wanted.
                rem_amo = list(a_now)
                rem_held: list[str] = []
                spelling: list[tuple[str, str]] = []
                for x in h:
                    hit = next((y for y in rem_amo if loose_same_person(x, y)), None)
                    if hit is None:
                        rem_held.append(x)
                    else:
                        rem_amo.remove(hit)
                still: list[str] = []
                for x in rem_held:
                    hit = next((y for y in rem_amo if near_same_person(x, y)), None)
                    if hit is None:
                        still.append(x)
                    else:
                        rem_amo.remove(hit)
                        spelling.append((x, hit))
                rem_held = still

                if not h:
                    status = "gap — we hold nobody"
                elif not a_now:
                    status = "extra — AMO elected nobody here"
                elif not rem_held and not rem_amo:
                    status = ("agree" if not spelling else
                              "spelling differs — verify, probably the same person")
                elif rem_held and a_prev and all(
                        any(loose_same_person(x, y) for y in a_prev) for x in rem_held):
                    status = (f"STALE — we hold the {prev} winner"
                              + (f" in {len(rem_held)} of {len(a_now)} seats"
                                 if len(a_now) > 1 else ""))
                elif not rem_held:
                    status = f"incomplete — {len(rem_amo)} seat(s) we do not hold"
                else:
                    status = "unknown-holder — by-election or pre-cycle residue"
                verdicts.append(WardVerdict(
                    ward, cid, wname, a_now, a_prev, h, status,
                    unmatched_held=rem_held, unmatched_amo=rem_amo))
            results[council] = verdicts
            st.councils += 1
            st.seats += len(verdicts)
            st.identical += sum(1 for v in verdicts if v.status == "agree")
            st.diverged += sum(1 for v in verdicts if v.status != "agree")
    return st, results
